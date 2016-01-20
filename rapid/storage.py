__author__ = 'Damon Lynch'

# Copyright (C) 2015 Damon Lynch <damonlynch@gmail.com>
# Copyright (C) 2008-2015 Canonical Ltd.
# Copyright (C) 2013 Bernard Baeyens

# This file is part of Rapid Photo Downloader.
#
# Rapid Photo Downloader is free software: you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Rapid Photo Downloader is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Rapid Photo Downloader.  If not,
# see <http://www.gnu.org/licenses/>.

"""
The primary task of this module is to handle addition and removal of
(1) cameras and (2) devices with file systems.

There are two scenarios:

1) User is running under a Gnome-like environment in which GVFS will
automatically mount cameras and devices. We can monitor mounts and
send a signal when something is mounted. The camera must be
unmounted before libgphoto2 can access it, so we must handle that too.

2) User is running under a non Gnome-like environment (e.g. KDE) in
which GVFS may or may not be running. However we can assume GVFS will
not automatically mount cameras and devices. In this case, using GIO
to monitor mounts is useless, as the mounts may not occur. So we must
monitor when cameras and other devices are added or removed ourselvs.
To do this, use udev for cameras, and udisks2 for devices with file
systems. When a device with a file system is inserted, if it is not
already mounted, attempt to mount it.

The secondary task of this module is to provide miscellaneous services
regarding mount points.
"""

import logging
import os
import re
import sys
import time
import subprocess
import shlex
from collections import namedtuple
from typing import Optional, Tuple, List

from PyQt5.QtCore import (QStorageInfo, QObject, pyqtSignal)
from gi.repository import GUdev, UDisks, GLib
from xdg.DesktopEntry import DesktopEntry
from xdg import BaseDirectory

from constants import Desktop

logging_level = logging.DEBUG
logging.basicConfig(format='%(levelname)s:%(asctime)s:%(message)s',
                    datefmt='%H:%M:%S',
                    level=logging_level)

try:
    from gi.repository import Gio
    have_gio = True
except ImportError:
    have_gio = False

StorageSpace = namedtuple('StorageSpace', 'bytes_free, bytes_total, path')
UdevAttr = namedtuple('UdevAttr', 'is_mtp_device, vendor, model')

PROGRAM_DIRECTORY = 'rapid-photo-downloader'

class ValidMounts():
    r"""
    Operations to find 'valid' mount points, i.e. the places in which
    it's sensible for a user to mount a partition. Valid mount points:
    include /home/<USER> , /media/<USER>, and /run/media/<USER>
    include directories in /etc/fstab, except /, /home, and swap
    However if only considering external mounts, the the mount must be
    under /media/<USER> or /run/media/<user>
    """
    def __init__(self, onlyExternalMounts: bool):
        """
        :param onlyExternalMounts: if True, valid mounts must be under
        /media/<USER> or /run/media/<user>
        """
        self.validMountFolders = None # type: Tuple[str]
        self.onlyExternalMounts = onlyExternalMounts
        self._setValidMountFolders()
        assert '/' not in self.validMountFolders
        if logging_level == logging.DEBUG:
            self.logValidMountFolders()

    def isValidMountPoint(self, mount: QStorageInfo) -> bool:
        """
        Determine if the path of the mount point starts with a valid
        path
        :param mount: QStorageInfo to be tested
        :return:True if mount is a mount under a valid mount, else False
        """
        for m in self.validMountFolders:
            if mount.rootPath().startswith(m):
                return True
        return False

    def pathIsValidMountPoint(self, path: str) -> bool:
        """
        Determine if path indicates a mount point under a valid mount
        point
        :param path: path to be tested
        :return:True if path is a mount under a valid mount, else False
        """
        for m in self.validMountFolders:
            if path.startswith(m):
                return True
        return False

    def mountedValidMountPointPaths(self):
        """
        Return paths of all the currently mounted partitions that are
        valid
        :return: tuple of currently mounted valid partition paths
        :rtype Tuple(str)
        """
        return tuple(filter(self.pathIsValidMountPoint, mountPaths()))

    def mountedValidMountPoints(self):
        """
        Return mount points of all the currently mounted partitions
        that are valid
        :return: tuple of currently mounted valid partition
        :rtype Tuple(QStorageInfo)
        """
        return tuple(filter(self.isValidMountPoint,
                            QStorageInfo.mountedVolumes()))

    def _setValidMountFolders(self):
        """
        Determine the valid mount point folders and set them in
        self.validMountFolders, e.g. /media/<USER>, etc.
        """
        if sys.platform.startswith('linux'):
            try:
                # this next line fails on some sessions
                media_dir = '/media/{}'.format(os.getlogin())
            except FileNotFoundError:
                media_dir = '/media/{}'.format(os.getenv('USER', ''))
            if self.onlyExternalMounts:
                self.validMountFolders = (media_dir,'/run{}'.format(media_dir))
            else:
                home_dir = os.path.expanduser('~')
                validPoints = [home_dir, media_dir,'/run{}'.format(media_dir)]
                for point in self.mountPointInFstab():
                    validPoints.append(point)
                self.validMountFolders = tuple(validPoints)
        else:
            raise("Mounts.setValidMountPoints() not implemented on %s",
                  sys.platform())

    def mountPointInFstab(self):
        """
        Yields a list of mount points in /etc/fstab
        The mount points will exclude /, /home, and swap
        """
        with open('/etc/fstab') as f:
            l = []
            for line in f:
                # As per fstab specs: white space is either Tab or space
                # Ignore comments, blank lines
                # Also ignore swap file (mount point none), root, and /home
                m = re.match(r'^(?![\t ]*#)\S+\s+(?!(none|/[\t ]|/home))('
                             r'?P<point>\S+)',
                             line)
                if m is not None:
                    yield (m.group('point'))

    def logValidMountFolders(self):
        """
        Output nicely formatted debug logging message
        """
        assert len(self.validMountFolders) > 0
        if logging_level == logging.DEBUG:
            msg = "To be recognized, partitions must be mounted under "
            if len(self.validMountFolders) > 2:
                msg += "one of "
                for p in self.validMountFolders[:-2]:
                    msg += "{}, ".format(p)
                msg += "{} or {}".format(self.validMountFolders[-2],
                                             self.validMountFolders[-1])
            elif len(self.validMountFolders) == 2:
                msg += "{} or {}".format(self.validMountFolders[0],
                                         self.validMountFolders[1])
            else:
                msg += self.validMountFolders[0]
            logging.debug(msg)


def mountPaths():
    """
    Yield all the mount paths returned by QStorageInfo
    """
    for m in QStorageInfo.mountedVolumes():
        yield m.rootPath()

def has_non_empty_dcim_folder(path: str) -> bool:
    """
    Checks to see if below the path there is a DCIM folder,
    if the folder is readable, and if it has any contents
    :param path: path to check
    :return: True if has valid DCIM, False otherwise
    """
    try:
        has_dcim = "DCIM" in os.listdir(path)
    except PermissionError:
        return False
    except FileNotFoundError:
        return False
    if has_dcim:
        dcim_folder = os.path.join(path, 'DCIM')
        if os.path.isdir(dcim_folder) and os.access(dcim_folder, os.R_OK):
            return len(os.listdir(dcim_folder)) > 0
    return False

def get_desktop_environment():
    #TODO confirm if cinnamon really is x-cinnamon
    return os.getenv('XDG_CURRENT_DESKTOP')

desktop = dict(gnome=Desktop.gnome, unity=Desktop.unity, xfce=Desktop.xfce, kde=Desktop.kde)
desktop['x-cinnamon']=Desktop.cinnamon

def get_desktop() -> Desktop:
    env = get_desktop_environment().lower()
    return desktop.get(env, Desktop.unknown)

def gvfs_controls_mounts() -> bool:
    return get_desktop() in (Desktop.gnome, Desktop.unity,Desktop.cinnamon, Desktop.xfce)

def xdg_photos_directory() -> str:
    """
    Get localized version of /home/<USER>/Pictures
    :return: the directory
    """
    return GLib.get_user_special_dir(GLib.USER_DIRECTORY_PICTURES)

def xdg_videos_directory() -> str:
    """
    Get localized version of /home/<USER>/Videos
    :return: the directory
    """
    return GLib.get_user_special_dir(GLib.USER_DIRECTORY_VIDEOS)

def make_program_directory(path: str) -> str:
    """
    Creates a subfolder used by Rapid Photo Downloader.

    Does not catch errors.

    :param path: location where the subfolder should be
    :return: the full path of the new directory
    """
    program_dir = os.path.join(path, 'rapid-photo-downloader')
    if not os.path.exists(program_dir):
        os.mkdir(program_dir)
    elif not os.path.isdir(program_dir):
        os.remove(program_dir)
        os.mkdir(program_dir)
    return program_dir

def get_program_cache_directory(create_if_not_exist=False) -> Optional[str]:
    """
    Get Rapid Photo Downloader cache directory, which is assumed to be
    under $XDG_CACHE_HOME or if that doesn't exist, ~/.cache.
    :param create_if_not_exist: creates directory if it does not exist.
    :return: the full path of the cache directory, or None on error
    """
    try:
        cache_directory = BaseDirectory.xdg_cache_home
        if not create_if_not_exist:
            return os.path.join(cache_directory, PROGRAM_DIRECTORY)
        else:
            return make_program_directory(cache_directory)
    except OSError:
        logging.error("An error occurred while creating the cache directory")
        return None

def get_program_data_directory(create_if_not_exist=False) -> Optional[str]:
    """
    Get Rapid Photo Downloader data directory, which is assumed to be
    under $XDG_DATA_HOME or if that doesn't exist,  ~/.local/share
    :param create_if_not_exist: creates directory if it does not exist.
    :return: the full path of the data directory, or None on error
    """
    try:
        data_directory = BaseDirectory.xdg_data_dirs[0]
        if not create_if_not_exist:
            return os.path.join(data_directory, PROGRAM_DIRECTORY)
        else:
            return make_program_directory(data_directory)
    except OSError:
        logging.error("An error occurred while creating the data directory")
        return None

def get_fdo_cache_thumb_base_directory() -> str:
    return os.path.join(BaseDirectory.xdg_cache_home, 'thumbnails')

def get_default_file_manager(remove_args=True) -> str:
    """
    Attempt to determine the default file manager for the system
    :param remove_args: if True, remove any arguments such as %U from
     the returned command
    :return: command (without path) if found, else None
    """
    assert sys.platform.startswith('linux')
    cmd = shlex.split('xdg-mime query default inode/directory')
    try:
        desktop_file = subprocess.check_output(cmd, universal_newlines=True)
    except:
        return None
    # Remove new line character from output
    desktop_file = desktop_file[:-1]
    path = os.path.join('/usr/share/applications/', desktop_file)
    desktop_entry = DesktopEntry(path)
    try:
        desktop_entry.parse(path)
    except:
        return None
    fm = desktop_entry.getExec()
    if remove_args:
        return fm.split()[0]
    else:
        return fm

def udev_attributes(devname: str) -> Optional[UdevAttr]:
    """
    Query udev to see if device is an MTP device.

    :param devname: udev DEVNAME e.g. '/dev/bus/usb/001/003'
    :return True if udev property ID_MTP_DEVICE == '1', else False
    """

    client = GUdev.Client(subsystems=['usb', 'block'])
    enumerator = GUdev.Enumerator.new(client)
    enumerator.add_match_property('DEVNAME', devname)
    for device in enumerator.execute():
        model = device.get_property('ID_MODEL') # type: str
        if model is not None:
            is_mtp = device.get_property('ID_MTP_DEVICE') == '1'
            vendor = device.get_property('ID_VENDOR') # type: str
            model = model.replace('_', ' ').strip()
            vendor = vendor.replace('_', ' ').strip()
            return UdevAttr(is_mtp, vendor, model)
    return None


class CameraHotplug(QObject):
    cameraAdded = pyqtSignal()
    cameraRemoved = pyqtSignal()

    def __init__(self):
        super(CameraHotplug, self).__init__()
        self.cameras = {}

    def startMonitor(self):
        self.client = GUdev.Client(subsystems=['usb', 'block'])
        self.client.connect('uevent', self.ueventCallback)

    def enumerateCameras(self):
        """
        Query udev to get the list of cameras store their path and
        model in our internal dict, which is useful when responding to
        camera removal.
        """
        enumerator = GUdev.Enumerator.new(self.client)
        enumerator.add_match_property('ID_GPHOTO2', '1')
        for device in enumerator.execute():
            model = device.get_property('ID_MODEL')
            if model is not None:
                path = device.get_sysfs_path()
                self.cameras[path] = model

    def ueventCallback(self, client: GUdev.Client, action: str, device: GUdev.Device) -> None:

        # for key in device.get_property_keys():
        #     print(key, device.get_property(key))
        if device.get_property('ID_GPHOTO2') == '1':
            self.camera(action, device)

    def camera(self, action: str, device: GUdev.Device) -> None:
        # For some reason, the add and remove camera event is triggered twice.
        # The second time the device information is a variation on information
        # from the first time.
        path = device.get_sysfs_path()
        parent_device = device.get_parent()
        parent_path = parent_device.get_sysfs_path()
        logging.debug("Device change: %s. Path: %s Parent Device: %s Parent path: %s",
                      action, path, parent_device, parent_path)

        if action == 'add':
            if parent_path not in self.cameras:
                model = device.get_property('ID_MODEL')
                logging.debug("Hotplug: new camera: %s", model)
                self.cameras[path] = model
                self.cameraAdded.emit()
            else:
                logging.debug("Hotplug: already know about %s", self.cameras[
                    parent_path])

        elif action == 'remove':
            emit_remove = False
            name = ''
            if path in self.cameras:
                name = self.cameras[path]
                del self.cameras[path]
                emit_remove = True
            elif device.get_property('ID_GPHOTO2') == '1':
                # This should not need to be called. However,
                # self.enumerateCameras may not have been called earlier
                name = device.get_property('ID_MODEL')
                if name is not None:
                    emit_remove = True
            if emit_remove:
                logging.debug("Hotplug: %s has been removed", name)
                self.cameraRemoved.emit()


class UDisks2Monitor(QObject):
    #Most of this class is Copyright 2008-2015 Canonical

    partitionMounted = pyqtSignal(str, list, bool)
    partitionUnmounted = pyqtSignal(str)

    loop_prefix = '/org/freedesktop/UDisks2/block_devices/loop'
    not_interesting = (
    '/org/freedesktop/UDisks2/block_devices/dm_',
    '/org/freedesktop/UDisks2/block_devices/ram',
    '/org/freedesktop/UDisks2/block_devices/zram',
    )

    def __init__(self, validMounts: ValidMounts) -> None:
        super().__init__()
        self.validMounts = validMounts

    def startMonitor(self) -> None:
        self.udisks = UDisks.Client.new_sync(None)
        self.manager = self.udisks.get_object_manager()
        self.manager.connect('object-added',
                             lambda man, obj: self._udisks_obj_added(obj))
        self.manager.connect('object-removed',
                             lambda man, obj: self._device_removed(obj))

        # Track the paths of the mount points, which is useful when unmounting
        # objects.
        self.known_mounts = {}
        for obj in self.manager.get_objects():
            path = obj.get_object_path()
            fs = obj.get_filesystem()
            if fs:
                mount_points = fs.get_cached_property(
                    'MountPoints').get_bytestring_array()
                if mount_points:
                    self.known_mounts[path] = mount_points[0]

    def _udisks_obj_added(self, obj) -> None:
        path = obj.get_object_path()
        for boring in self.not_interesting:
            if path.startswith(boring):
                return
        block = obj.get_block()
        if not block:
            return

        drive = self._get_drive(block)

        part = obj.get_partition()
        is_system = block.get_cached_property('HintSystem').get_boolean()
        is_loop = path.startswith(self.loop_prefix) and not \
            block.get_cached_property('ReadOnly').get_boolean()
        if not is_system or is_loop:
            if part:
                self._udisks_partition_added(obj, block, drive, path)

    def _get_drive(self, block) -> Optional[UDisks.Drive]:
        drive_name = block.get_cached_property('Drive').get_string()
        if drive_name != '/':
            return self.udisks.get_object(drive_name).get_drive()
        else:
            return None

    def _udisks_partition_added(self, obj, block, drive, path) -> None:
        logging.debug('UDisks: partition added: %s' % path)
        fstype = block.get_cached_property('IdType').get_string()
        logging.debug('Udisks: id-type: %s' % fstype)

        fs = obj.get_filesystem()

        if fs:
            icon_names = self.get_icon_names(obj)

            if drive is not None:
                ejectable = drive.get_property('ejectable')
            else:
                ejectable = False
            mount_point = ''
            mount_points = fs.get_cached_property(
                'MountPoints').get_bytestring_array()
            if len(mount_points) == 0:
                try:
                    logging.debug("UDisks: attempting to mount %s", path)
                    mount_point = self.retry_mount(fs, fstype)
                    if not mount_point:
                        raise
                    else:
                        logging.debug("UDisks: successfully mounted at %s", mount_point)
                except:
                    logging.error('UDisks: could not mount the device: %s', path)
                    return
            else:
                mount_point = mount_points[0]
                logging.debug("UDisks: already mounted at %s", mount_point)

            self.known_mounts[path] = mount_point
            if self.validMounts.pathIsValidMountPoint(mount_point):
                self.partitionMounted.emit(mount_point, icon_names, ejectable)

        else:
            logging.debug("Udisks: partition has no file system %s", path)

    def retry_mount(self, fs, fstype) -> str:
        # Variant paramater construction Copyright Bernard Baeyens, and is
        # licensed under GNU General Public License Version 2 or higher.
        # https://github.com/berbae/udisksvm
        list_options = ''
        if fstype == 'vfat':
            list_options = 'flush'
        elif fstype == 'ext2':
            list_options = 'sync'
        G_VARIANT_TYPE_VARDICT = GLib.VariantType.new('a{sv}')
        param_builder = GLib.VariantBuilder.new(G_VARIANT_TYPE_VARDICT)
        optname = GLib.Variant.new_string('fstype') # s
        value = GLib.Variant.new_string(fstype)
        vvalue = GLib.Variant.new_variant(value) # v
        newsv = GLib.Variant.new_dict_entry(optname, vvalue) # {sv}
        param_builder.add_value(newsv)
        optname = GLib.Variant.new_string('options')
        value = GLib.Variant.new_string(list_options)
        vvalue = GLib.Variant.new_variant(value)
        newsv = GLib.Variant.new_dict_entry(optname, vvalue)
        param_builder.add_value(newsv)
        vparam = param_builder.end() # a{sv}

        # Try to mount until it does not fail with "Busy"
        timeout = 10
        while timeout >= 0:
            try:
                return fs.call_mount_sync(vparam, None)
            except GLib.GError as e:
                if not 'UDisks2.Error.DeviceBusy' in e.message:
                    raise
                logging.debug('Udisks: Device busy.')
                time.sleep(0.3)
                timeout -= 1
        return ''

    def get_icon_names(self, obj: UDisks.Object) -> List[str]:
        # Get icon information, if possible
        icon_names = []
        if have_gio:
            info = self.udisks.get_object_info(obj)
            icon = info.get_icon()
            if isinstance(icon, Gio.ThemedIcon):
                icon_names = icon.get_names()
        return icon_names

    # Next three class member functions from Damon Lynch, not Canonical
    def _device_removed(self, obj: UDisks.Object) -> None:
        # path here refers to the udev / udisks path, not the mount point
        path = obj.get_object_path()
        if path in self.known_mounts:
            mount_point = self.known_mounts[path]
            del self.known_mounts[path]
            self.partitionUnmounted.emit(mount_point)

    def get_can_eject(self, obj: UDisks.Object) -> bool:
        block = obj.get_block()
        drive = self._get_drive(block)
        if drive is not None:
            return drive.get_property('ejectable')
        return False

    def get_device_props(self, device_path: str) -> Tuple[List[str], bool]:
        """
        Given a device, get the icon names suggested by udev, and
        determine whether the mount is ejectable or not.
        :param device_path: system path of the device to check,
        e.g. /dev/sdc1
        :return: icon names and eject boolean
        """

        object_path = '/org/freedesktop/UDisks2/block_devices/{}'.format(
            os.path.split(device_path)[1])
        obj = self.udisks.get_object(object_path)
        icon_names = self.get_icon_names(obj)
        can_eject = self.get_can_eject(obj)
        return (icon_names, can_eject)


if have_gio:
    class GVolumeMonitor(QObject):
        r"""
        Monitor the mounting or unmounting of cameras or partitions
        using Gnome's GIO/GVFS. Unmount cameras automatically mounted
        by GVFS.

        Raises a signal if a volume has been inserted, but will not be
        automatically mounted. This is important because this class
        is monitoring mounts, and if the volume is not mounted, it will
        go unnoticed.
        """

        cameraUnmounted = pyqtSignal(bool, str, str, bool)
        cameraMounted = pyqtSignal()
        partitionMounted = pyqtSignal(str, list, bool)
        partitionUnmounted = pyqtSignal(str)
        volumeAddedNoAutomount = pyqtSignal()
        cameraPossiblyRemoved = pyqtSignal()

        def __init__(self, validMounts: ValidMounts):
            super(GVolumeMonitor, self).__init__()
            self.vm = Gio.VolumeMonitor.get()
            self.vm.connect('mount-added', self.mountAdded)
            self.vm.connect('volume-added', self.volumeAdded)
            self.vm.connect('mount-removed', self.mountRemoved)
            self.vm.connect('volume-removed', self.volumeRemoved)
            self.portSearch = re.compile(r'usb:([\d]+),([\d]+)')
            self.validMounts = validMounts

        def cameraMountPoint(self, model: str, port: str) -> Gio.Mount:
            """
            :return: the mount point of the camera, if it is mounted,
             else None
            """
            p = self.portSearch.match(port)
            assert p is not None
            p1 = p.group(1)
            p2 = p.group(2)
            pattern = re.compile(r'%\S\Susb%\S\S{}%\S\S{}%\S\S'.format(p1, p2))
            to_unmount = None

            for mount in self.vm.get_mounts():
                folder_extract = self.mountIsCamera(mount)
                if folder_extract is not None:
                    if pattern.match(folder_extract):
                        to_unmount = mount
                        break
            return to_unmount

        def unmountCamera(self, model: str, port: str, download_starting:
                          bool=False, mount_point: Gio.Mount=None) -> bool:
            """
            Unmount camera mounted on gvfs mount point, if it is
            mounted. If not mounted, ignore.
            :param model: model as returned by libgphoto2
            :param port: port as returned by libgphoto2, in format like
             usb:001,004
            :param mount_point: if not None, try umounting from this
             mount point without scanning for it first
            :return: True if an unmount operation has been initiated,
             else returns False.
            """
            if mount_point is None:
                to_unmount = self.cameraMountPoint(model, port)
            else:
                to_unmount = mount_point

            if to_unmount is not None:
                logging.debug("GIO: Attempting to unmount %s...", model)
                to_unmount.unmount_with_operation(0,
                      None, None, self.unmountCallback,
                      (model, port, download_starting))
                return True

            return False

        def unmountCallback(self, mount: Gio.Mount, result: Gio.AsyncResult,
                             userData):
            """
            Called by the asynchronous unmount operation.
            When complete, emits a signal indicating operation
            success, and the camera model and port
            :param mount: camera mount
            :param result: result of the unmount process
            :param userData: model and port of the camera being
            unmounted, in the format of libgphoto2
            :type userData: Tuple[str,str,bool]
            """
            icon_names = self.getIconNames(mount)
            if mount.unmount_with_operation_finish(result):
                logging.debug("...successfully unmounted {}".format(
                    userData[0]))
                self.cameraUnmounted.emit(True, userData[0], userData[1],
                                          userData[2])
            else:
                logging.debug("...failed to unmount {}".format(
                    userData[0]))
                self.cameraUnmounted.emit(False, userData[0], userData[1],
                                          userData[2])

        def mountIsCamera(self, mount: Gio.Mount) -> str:
            """
            Determine if the mount point is that of a camera
            :param mount: the mount to examine
            :return: None if not a camera, or the component of the
            folder name that indicates on which port it is mounted
            """
            root = mount.get_root()
            if root is not None:
                path = root.get_path()
                if path:
                    # logging.debug("GIO: Looking for camera at mount {}".format(path))
                    folder_name = os.path.split(path)[1]
                    for s in ('gphoto2:host=', 'mtp:host='):
                        if folder_name.startswith(s):
                            return folder_name[len(s):]
            # if path is not None:
            #     logging.debug("GIO: camera not found at {}".format(path))
            return None

        def mountIsPartition(self, mount: Gio.Mount) -> bool:
            """
            Determine if the mount point is that of a valid partition,
            i.e. is mounted in a valid location, which is under one of
            self.validMountDirs
            :param mount: the mount to examine
            :return: True if the mount is a valid partiion
            """
            root = mount.get_root()
            if root is not None:
                path = root.get_path()
                if path:
                    # logging.debug("GIO: Looking for valid partition at mount {}".format(path))
                    if self.validMounts.pathIsValidMountPoint(path):
                        # logging.debug("GIO: partition found at {}".format(path))
                        return True
            # if path is not None:
            #     logging.debug("GIO: partition is not valid: {}".format(path))
            return False

        def mountAdded(self, volumeMonitor, mount: Gio.Mount):
            if self.mountIsCamera(mount):
                self.cameraMounted.emit()
            elif self.mountIsPartition(mount):
                icon_names = self.getIconNames(mount)
                self.partitionMounted.emit(mount.get_root().get_path(),
                                           icon_names,
                                           mount.can_eject())

        def mountRemoved(self, volumeMonitor, mount: Gio.Mount):
            if not self.mountIsCamera(mount):
                if self.mountIsPartition(mount):
                    logging.debug("GIO: %s has been unmounted", mount.get_name())
                    self.partitionUnmounted.emit(mount.get_root().get_path())

        def volumeAdded(self, volumeMonitor, volume: Gio.Volume):
            logging.debug("GIO: Volume added %s. Automount: %s",
                          volume.get_name(),
                          volume.should_automount())
            if not volume.should_automount():
                #TODO is it possible to determine the device type?
                self.volumeAddedNoAutomount.emit()

        def volumeRemoved(self, volumeMonitor, volume: Gio.Volume):
            logging.debug("GIO: %s volume removed", volume.get_name())
            if volume.get_activation_root() is not None:
                # logging.debug("GIO: %s might be a camera", volume.get_name())
                self.cameraPossiblyRemoved.emit()

        def getIconNames(self, mount: Gio.Mount) -> List[str]:
            icon_names = []
            icon = mount.get_icon()
            if isinstance(icon, Gio.ThemedIcon):
                icon_names = icon.get_names()

            return icon_names

        def getProps(self, path: str) -> Optional[Tuple[List[str], bool]]:
            """
            Given a mount's path, get the icon names suggested by the
            volume monitor, and determine whether the mount is
            ejectable or not.
            :param path: the path of mount to check
            :return: icon names and eject boolean
            """

            for mount in self.vm.get_mounts():
                root = mount.get_root()
                if root is not None:
                    p = root.get_path()
                    if path == p:
                        icon_names = self.getIconNames(mount)
                        return (icon_names, mount.can_eject())
            return (None, None)
