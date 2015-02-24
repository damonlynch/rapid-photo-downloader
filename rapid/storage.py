__author__ = 'Damon Lynch'

import logging
import os
import re
import sys

from PyQt5.QtCore import (QStorageInfo, QObject, pyqtSignal)
from gi.repository.GUdev import Client, Device

logging_level = logging.DEBUG
logging.basicConfig(format='%(levelname)s:%(asctime)s:%(message)s',
                    datefmt='%H:%M:%S',
                    level=logging_level)

try:
    from gi.repository import Gio
    using_gio = True
except ImportError:
    using_gio = False
logging.debug("Using GIO: %s", using_gio)


def mounted_volumes():
    # QStorageInfo.refresh()
    for q in QStorageInfo.mountedVolumes():
        print(q.rootPath(), q.displayName())

def contains_dcim_folder(path):
    if "DCIM" in os.listdir(path):
        return os.path.isdir(os.path.join(path, 'DCIM'))

def mount_points_in_fstab():
    """
    Yields a list of mount points in /etc/fstab
    The mount points will exclude /, /home, and swap
    """
    with open('/etc/fstab') as f:
        l = []
        for line in f:
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
    home_dir = os.path.expanduser('~')
    if sys.platform.startswith('linux'):
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

class DeviceHotplug(QObject):
    cameraAdded = pyqtSignal()
    cameraRemoved = pyqtSignal()
    partitionAdded = pyqtSignal()
    partitionRemoved = pyqtSignal()

    def __init__(self):
        super(DeviceHotplug, self).__init__()
        self.cameras = {}

    def startMonitor(self):
        self.client = Client(subsystems=['usb', 'block']) #
        self.client.connect('uevent', self.ueventCallback)

    def ueventCallback(self, client: Client, action: str, device: Device):

        if device.get_property('ID_GPHOTO2') == '1':
            self.camera(action, device)
        elif device.get_devtype() == 'partition':
            self.partition(action, device)


    def camera(self, action: str, device: Device):
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

    def partition(self, action: str, device: Device):
        logging.debug("%s partition", action.capitalize())
        if action == 'add':
            self.partitionAdded.emit()
        elif action == 'remove':
            self.partitionRemoved.emit()

    def printDevice(self, device: Device):
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


if using_gio:
    class GVolumeMonitor(QObject):
        r"""
        Monitor the addition or removal of cameras or partitions
        using Gnome's GIO/GVFS.
        Unmount cameras automatically mounted by GVFS.
        """

        cameraUnmounted = pyqtSignal(bool, str, str)
        cameraMounted = pyqtSignal()
        partitionMounted = pyqtSignal(str)
        partitionUnmounted = pyqtSignal(str)


        def __init__(self):
            super(GVolumeMonitor, self).__init__()
            self.vm = Gio.VolumeMonitor.get()
            self.vm.connect('mount-added', self.mountAdded)
            self.vm.connect('volume-added', self.volumeAdded)
            self.vm.connect('mount-removed', self.mountRemoved)
            self.portSearch = re.compile(r'usb:([\d]+),([\d]+)')
            self.validMountPoints = get_valid_mount_points()
            assert '/' not in self.validMountPoints
            msg = "Valid partitions must be mounted under one of "
            for p in self.validMountPoints[:-2]:
                msg += "{}, ".format(p)
            msg += "{} or {}".format(self.validMountPoints[-2],
                                         self.validMountPoints[-1])
            logging.debug(msg)



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
                logging.debug("Attempting to unmount %s...", model)
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
                    logging.debug("Looking for camera at mount {}".format(
                        path))
                    folder_name = os.path.split(path)[1]
                    for s in ('gphoto2:host=', 'mtp:host='):
                        if folder_name.startswith(s):
                            return folder_name[len(s):]
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
                    logging.debug("Looking for partition at mount {}".format(
                        path))
                    for s in self.validMountPoints:
                        if path.startswith(s):
                            return True
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
            logging.debug("Volume added %s", volume.get_name())