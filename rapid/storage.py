__author__ = 'Damon Lynch'

# Copyright (C) 2015 Damon Lynch <damonlynch@gmail.com>
#TODO add copyright for code from other projects - probably essential

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
Handle addition and removal of cameras and devices with file systems.
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
"""

import logging
import os
import re
import sys
import time

from PyQt5.QtCore import (QStorageInfo, QObject, pyqtSignal)
from gi.repository import GUdev, UDisks, GLib

logging_level = logging.DEBUG
logging.basicConfig(format='%(levelname)s:%(asctime)s:%(message)s',
                    datefmt='%H:%M:%S',
                    level=logging_level)

try:
    from gi.repository import Gio
    have_gio = True
except ImportError:
    have_gio = False

def mounted_volumes():
    for q in QStorageInfo.mountedVolumes():
        print(q.rootPath(), q.displayName())


def mountPaths():
    """
    Yield all the mounts returned by QStorageInfo
    """
    for m in QStorageInfo.mountedVolumes():
        yield m.rootPath()

def contains_dcim_folder(path):
    if "DCIM" in os.listdir(path):
        return os.path.isdir(os.path.join(path, 'DCIM'))
    return False

def mount_points_in_fstab():
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

def get_valid_mount_points():
    """
    Get the places in which it's sensible for a user to mount a
    partition.
    Includes /home/<USER> , /media/<USER>, and /run/media/<USER>
    Includes directories in /etc/fstab, except /, /home, and swap

    :return: tuple of the valid mount points
    :rtype: Tuple(str)
    """
    if sys.platform.startswith('linux'):
        home_dir = os.path.expanduser('~')
        try:
            # this next line fails on some sessions
            media_dir = '/media/{}'.format(os.getlogin())
        except FileNotFoundError:
            media_dir = '/media/{}'.format(os.getenv('USER', ''))
        valid_points = [home_dir, media_dir,'/run{}'.format(media_dir)]
        for point in mount_points_in_fstab():
            valid_points.append(point)
        return tuple(valid_points)
    else:
        raise("get_valid_mount_points() not implemented on %s", sys.platform())

def log_valid_mount_points(validMountPoints):
    """
    Output nicely formatted debug logging message
    :param validMountPoints: the mount points, of which there must be
    at least three
    """
    if logging_level == logging.DEBUG:
        msg = "Valid partitions must be mounted under one of "
        for p in validMountPoints[:-2]:
            msg += "{}, ".format(p)
        msg += "{} or {}".format(validMountPoints[-2],
                                     validMountPoints[-1])
        logging.debug(msg)

def get_desktop_environment():
    return os.getenv('XDG_CURRENT_DESKTOP')

#TODO confirm if cinnamon really is x-cinnamon
def gvfs_controls_mounts():
    return get_desktop_environment().lower() in ('gnome', 'unity',
                                                 'x-cinnamon')

class CameraHotplug(QObject):
    cameraAdded = pyqtSignal()
    cameraRemoved = pyqtSignal()
    # partitionAdded = pyqtSignal()
    # partitionRemoved = pyqtSignal()

    def __init__(self):
        super(CameraHotplug, self).__init__()
        self.cameras = {}

    def startMonitor(self):
        self.client = GUdev.Client(subsystems=['usb', 'block']) #
        self.client.connect('uevent', self.ueventCallback)

    def ueventCallback(self, client: GUdev.Client, action: str, device:
    GUdev.Device):

        if device.get_property('ID_GPHOTO2') == '1':
            self.camera(action, device)

    def camera(self, action: str, device: GUdev.Device):
        # For some reason, the add and remove camera event is triggered twice.
        # The second time the device information is a variation on information
        # from the first time.
        logging.debug("%s camera", action.capitalize())
        path = device.get_sysfs_path()
        parent_device = device.get_parent()
        parent_path = parent_device.get_sysfs_path()

        if action == 'add':
            if parent_path not in self.cameras:
                model = device.get_property('ID_MODEL')
                logging.debug("New camera: %s", model)
                self.cameras[path] = model
                self.cameraAdded.emit()
            else:
                logging.debug("Already know about %s", self.cameras[
                    parent_path])

        elif action == 'remove':
            if path in self.cameras:
                logging.debug("%s has been removed", self.cameras[path])
                del self.cameras[path]
                self.cameraRemoved.emit()

    def printDevice(self, device: GUdev.Device):
        # from Canonical's udev-usb-speed.py
        for func in ('get_action', 'get_device_file', 'get_device_file_symlinks',
                 'get_device_number', 'get_device_type', 'get_devtype',
                 'get_driver', 'get_is_initialized', 'get_name', 'get_number',
                 'get_parent',
                 # skipping get_parent_with_subsystem()
                 # skipping get_property*()
                 'get_seqnum', 'get_subsystem',
                 # skipping get_syfs_attr*()
                 'get_sysfs_path', 'get_tags', 'get_usec_since_initialized'):
            func_ret_value = getattr(device, func)()
            print("  {}(): {!r}".format(func, func_ret_value))
        for prop_name in device.get_property_keys():
            prop_value = device.get_property(prop_name)
            print("  get_property({!r}): {!r}".format(prop_name, prop_value))


class UDisks2Monitor(QObject):
    #TODO credit usb-creator
    partitionMounted = pyqtSignal(str)
    partitionUnmounted = pyqtSignal(str)
    #TODO partition unmounted code

    loop_prefix = '/org/freedesktop/UDisks2/block_devices/loop'
    not_interesting = (
    '/org/freedesktop/UDisks2/block_devices/dm_',
    '/org/freedesktop/UDisks2/block_devices/ram',
    '/org/freedesktop/UDisks2/block_devices/zram',
    )

    def __init__(self):
        super(UDisks2Monitor, self).__init__()
        self.validMountPoints = get_valid_mount_points()
        assert '/' not in self.validMountPoints
        log_valid_mount_points(self.validMountPoints)

    def startMonitor(self):
        self.udisks = UDisks.Client.new_sync(None)
        self.manager = self.udisks.get_object_manager()
        self.manager.connect('object-added',
                             lambda man, obj: self._udisks_obj_added(obj))

    def _udisks_obj_added(self, obj):
        path = obj.get_object_path()
        for boring in self.not_interesting:
            if path.startswith(boring):
                return
        block = obj.get_block()
        if not block:
            return

        drive_name = block.get_cached_property('Drive').get_string()
        if drive_name != '/':
            drive = self.udisks.get_object(drive_name).get_drive()
        else:
            drive = None

        part = obj.get_partition()
        is_system = block.get_cached_property('HintSystem').get_boolean()
        is_loop = path.startswith(self.loop_prefix) and not \
            block.get_cached_property('ReadOnly').get_boolean()
        if not is_system or is_loop:
            if part:
                self._udisks_partition_added(obj, block, drive, path)

    def _udisks_partition_added(self, obj, block, drive, path):
        logging.debug('UDisks: partition added: %s' % path)
        fstype = block.get_cached_property('IdType').get_string()
        logging.debug('Udisks: id-type: %s' % fstype)

        fs = obj.get_filesystem()

        if fs:
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
                        logging.debug("UDisks: successfully mounted at %s",
                                      mount_point)
                except:
                    logging.error('UDisks: could not mount the device: %s' %
                                  path)
                    return
            else:
                mount_point = mount_points[0]
                logging.debug("UDisks: already mounted at %s", mount_point)

            for s in get_valid_mount_points():
                if mount_point.startswith(s):
                    self.partitionMounted.emit(mount_point)

        else:
            logging.debug("Udisks: partition has no file system %s", path)

    def retry_mount(self, fs, fstype):
        #TODO: credit berbae and usb-creator
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

        cameraUnmounted = pyqtSignal(bool, str, str)
        cameraMounted = pyqtSignal()
        partitionMounted = pyqtSignal(str)
        partitionUnmounted = pyqtSignal(str)
        volumeAddedNoAutomount = pyqtSignal()


        def __init__(self):
            super(GVolumeMonitor, self).__init__()
            self.vm = Gio.VolumeMonitor.get()
            self.vm.connect('mount-added', self.mountAdded)
            self.vm.connect('volume-added', self.volumeAdded)
            self.vm.connect('mount-removed', self.mountRemoved)
            self.portSearch = re.compile(r'usb:([\d]+),([\d]+)')
            self.validMountPoints = get_valid_mount_points()
            assert '/' not in self.validMountPoints
            log_valid_mount_points(self.validMountPoints)


        def unmountCamera(self, model: str, port: str) -> bool:
            """
            Unmount camera mounted on gvfs mount point, if it is
            mounted. If not mounted, ignore.
            :param model: model as returned by libgphoto2
            :param port: port as returned by libgphoto2, in format like
             usb:001,004
             :return: True if an unmount operation has been initiated,
             else returns False.
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

            if to_unmount is not None:
                logging.debug("GIO: Attempting to unmount %s...", model)
                to_unmount.unmount_with_operation(0,
                                                  None,
                                                  None,
                                                  self.unmountCallback,
                                                  (model, port))
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
            :type userData: Tuple[str,str]
            """
            if mount.unmount_with_operation_finish(result):
                logging.debug("...successfully unmounted {}".format(
                    userData[0]))
                self.cameraUnmounted.emit(True, userData[0], userData[1])
            else:
                logging.debug("...failed to unmount {}".format(
                    userData[0]))
                self.cameraUnmounted.emit(False, userData[0], userData[1])

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
                    logging.debug("GIO: Looking for camera at mount {}"
                                  "".format(
                        path))
                    folder_name = os.path.split(path)[1]
                    for s in ('gphoto2:host=', 'mtp:host='):
                        if folder_name.startswith(s):
                            return folder_name[len(s):]
            logging.debug("GIO: camera not found at {}".format(path))
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
                    logging.debug("GIO: Looking for partition at mount {"
                                  "}".format(
                        path))
                    for s in self.validMountPoints:
                        if path.startswith(s):
                            return True
            logging.debug("GIO: partition is not valid: {}".format(path))
            return False

        def mountAdded(self, volumeMonitor, mount: Gio.Mount):
            if self.mountIsCamera(mount):
                self.cameraMounted.emit()
            elif self.mountIsPartition(mount):
                self.partitionMounted.emit(mount.get_root().get_path())

        def mountRemoved(self, volumeMonitor, mount: Gio.Mount):
            if not self.mountIsCamera(mount):
                if self.mountIsPartition(mount):
                    logging.debug("%s has been unmounted", mount.get_name())
                    self.partitionUnmounted.emit(mount.get_root().get_path())

        def volumeAdded(self, volumeMonitor, volume: Gio.Volume):
            logging.debug("GIO: Volume added %s. Automount: %s",
                          volume.get_name(),
                          volume.should_automount())
            if not volume.should_automount():
                self.volumeAddedNoAutomount.emit()
