__author__ = 'Damon Lynch'

# Copyright (C) 2015 Damon Lynch <damonlynch@gmail.com>

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

import shutil
import os
import logging
from collections import namedtuple
from PyQt5.QtCore import QStorageInfo
from PyQt5.QtWidgets import QFileIconProvider
from PyQt5.QtGui import QIcon

from constants import DeviceType, BackupLocationType, FileType
from rpdfile import FileTypeCounter

logging.basicConfig(format='%(levelname)s:%(asctime)s:%(message)s',
                    datefmt='%H:%M:%S',
                    level=logging.DEBUG)


class Device:
    r"""
    Representation of a camera or an object with a file system that
    will have files downloaded from it

    >>> d = Device()
    >>> d.set_download_from_volume('/media/damon/EOS_DIGITAL', 'EOS_DIGITAL')
    >>> d
    'EOS_DIGITAL':'/media/damon/EOS_DIGITAL'
    >>> str(d)
    '/media/damon/EOS_DIGITAL (EOS_DIGITAL)'
    >>> d.camera_model
    >>> d.camera_port

    >>> c = Device()
    >>> c.set_download_from_camera('Canon EOS 1D X', 'usb:001,002')
    >>> c
    'Canon EOS 1D X':'usb:001,002'
    >>> str(c)
    'Canon EOS 1D X on port usb:001,002'
    >>> c.path
    >>> c.display_name

    >>> e = Device()
    >>> e.set_download_from_volume('/media/damon/EOS_DIGITAL', 'EOS_DIGITAL')
    >>> e == d
    True
    >>> e != c
    True
    >>> c == d
    False
    >>> c != d
    True
    """
    def __init__(self):
        self.clear()

    def clear(self):
        self.camera_model = None
        self.camera_port = None
        self.path = None
        self.display_name = None
        self.device_type = None
        self.icon_name = None
        self.can_eject = None
        self.photo_cache_dir = None
        self.video_cache_dir = None
        self.file_size_sum = 0
        self.file_type_counter = FileTypeCounter()

    def __repr__(self):
        if self.device_type == DeviceType.camera:
            return "%r:%r" % (self.camera_model, self.camera_port)
        elif self.device_type == DeviceType.volume:
            return "%r:%r" % (self.display_name, self.path)
        else:
            return "%r" % self.path

    def __str__(self):
        if self.device_type == DeviceType.camera:
            return "%s on port %s" % (self.camera_model, self.camera_port)
        elif self.device_type == DeviceType.volume:
            if self.path != self.display_name:
                return "%s (%s)" % (self.path, self.display_name)
            else:
                return "%s" % (self.path)
        else:
            return "%s" % (self.path)

    def __eq__(self, other):
        for attr in ('device_type', 'camera_model', 'camera_port',
                     'path', 'display_name', 'icon_name', 'can_eject'):
            if getattr(self, attr) != getattr(other, attr):
                return False
        return True

    def __ne__(self, other):
        return not self.__eq__(other)

    def _get_valid_icon_name(self, possible_names):
        for icon_name in possible_names:
            if QIcon.hasThemeIcon(icon_name):
                return icon_name
        return None

    def set_download_from_camera(self, camera_model: str, camera_port: str):
        self.clear()
        self.device_type = DeviceType.camera
        self.camera_model = camera_model
        self.camera_port = camera_port
        self.icon_name = self._get_valid_icon_name(('camera-photo', 'camera'))

    def set_download_from_volume(self, path: str, display_name: str,
                                 icon_names=None, can_eject=None):
        self.clear()
        self.device_type = DeviceType.volume
        self.path = path
        self.icon_name = self._get_valid_icon_name(icon_names)
        self.display_name = display_name
        self.can_eject = can_eject

    def set_download_from_path(self, path: str):
        self.clear()
        self.device_type = DeviceType.path
        self.path = path
        # the next value is almost certainly ("folder",), but I guess it's
        # better to generate it from code
        self.icon_name = ('{}'.format(QFileIconProvider().icon(
            QFileIconProvider.Folder).name()))

    def name(self) -> str:
        """
        Get the name of the device, suitable to be displayed to the
        user. If the device is a path, return the path name
        :return  str containg the name
        """
        if self.device_type == DeviceType.camera:
            return self.camera_model
        elif self.device_type == DeviceType.volume:
            return self.display_name
        else:
            return self.path

    def _delete_cache_dir(self, cache_dir):
        if cache_dir is not None:
            if os.path.isdir(cache_dir):
                assert cache_dir != os.path.expanduser('~')
                try:
                    shutil.rmtree(cache_dir, ignore_errors=True)
                except:
                    logging.error("Unknown error deleting cache "
                                      "directory %s", cache_dir)

    def delete_cache_dirs(self):
        self._delete_cache_dir(self.photo_cache_dir)
        self._delete_cache_dir(self.video_cache_dir)

class DeviceCollection:
    """
    Maintain collection of devices that are being scanned, where a
    device is of type Device.

    When a device is added, a scan_id is generated and returned.

    >>> d = Device()
    >>> d.set_download_from_volume('/media/damon/EOS_DIGITAL', 'EOS_DIGITAL')
    >>> c = Device()
    >>> c.set_download_from_camera('Canon EOS 1D X', 'usb:001,002')
    >>> e = Device()
    >>> e.set_download_from_volume('/media/damon/EOS_DIGITAL', 'EOS_DIGITAL')
    >>> dc = DeviceCollection()
    >>> d_scan_id = dc.add_device(d)
    >>> d_scan_id
    0
    >>> d_scan_id in dc
    True
    >>> dc.known_path(d.path)
    True
    >>> dc[d_scan_id] == d
    True
    >>> dc.known_path('/root')
    False
    >>> c_scan_id = dc.add_device(c)
    >>> c_scan_id
    1
    >>> len(dc)
    2
    >>> dc[d_scan_id] == dc[c_scan_id]
    False
    >>> dc.known_camera('Canon EOS 1D X', 'usb:001,002')
    True
    >>> dc.known_camera('Canon EOS 1D X', 'usb:001,003')
    False
    >>> dc.delete_device(c)
    True
    >>> len(dc.cameras)
    0
    >>> dc.known_camera('Canon EOS 1D X', 'usb:001,002')
    False
    >>> len(dc)
    1
    >>> dc.known_device(e)
    True
    >>> del dc[d_scan_id]
    >>> len(dc)
    0
    >>> dc.delete_device(e)
    False
    """
    def __init__(self):
        self.devices = {} # type Dict[int, Device]
        self.cameras = {} # type Dict[str, str]
        self.scan_counter = 0

    def add_device(self, device: Device) -> int:
        scan_id = self.scan_counter
        self.scan_counter += 1
        self.devices[scan_id] = device
        if device.camera_port:
            port = device.camera_port
            assert port not in self.cameras
            self.cameras[port] = device.camera_model
        return scan_id

    def known_camera(self, model: str, port: str) -> bool:
        """
        Check if the camera is already in the list of devices
        :param model: camera model as specified by libgohoto2
        :param port: camera port as specified by libgohoto2
        :return: True if this camera is already being processed, else False
        """
        if port in self.cameras:
            assert self.cameras[port] == model
            return True
        return False

    def known_path(self, path: str) -> bool:
        """
        Check if the path is already in the list of devices
        :param path: path to check
        :return: True if the path is already being processed, else False
        """
        for scan_id in self.devices:
            if self.devices[scan_id].path == path:
                return True
        return False

    def known_device(self, device: Device) -> bool:
        return device in list(self.devices.values())

    def scan_id_from_path(self, path: str):
        for scan_id in self.devices:
            if self.devices[scan_id].path == path:
                return scan_id
        return None

    def scan_id_from_camera_model_port(self, model: str, port: str):
        camera = Device()
        camera.set_download_from_camera(model, port)
        for scan_id in self.devices:
            if self.devices[scan_id] == camera:
                return scan_id

    def delete_device(self, device: Device) -> bool:
        """
        Delete the device from the collection.
        :param device: the device to delete
        :return: True if device was deleted, else return False
        """
        for scan_id in self.devices:
            if self.devices[scan_id] == device:
                del self[scan_id]
                return True
        return False

    def delete_cache_dirs(self):
        """
        Delete all Download Caches and their contents any devices might have
        """
        for device in self.devices.values():
            device.delete_cache_dirs()

    def __delitem__(self, scan_id):
        d = self.devices[scan_id]
        """ :type : Device"""
        if d.device_type == DeviceType.camera:
            del self.cameras[d.camera_port]
        d.delete_cache_dirs()
        del self.devices[scan_id]

    def __getitem__(self, scan_id):
        return self.devices[scan_id]

    def __len__(self):
        return len(self.devices)

    def __contains__(self, scan_id):
        return scan_id in self.devices

    def __iter__(self):
        return iter(self.devices)


BackupDevice = namedtuple('BackupDevice', ['mount', 'backup_type'])

class BackupDeviceCollection:
    r"""
    Track and manage devices (and manual paths) used for backing up.
    Photos can be backed up to one location, and videos to another; or
    they can be backed up to the same location.

    >>> b = BackupDeviceCollection()
    >>> p = BackupDevice(mount=None, backup_type=BackupLocationType.photos)
    >>> v = BackupDevice(mount=None, backup_type=BackupLocationType.videos)
    >>> pv = BackupDevice(mount=None,
    ...                   backup_type=BackupLocationType.photos_and_videos)
    >>> pv2 = BackupDevice(mount=None,
    ...                   backup_type=BackupLocationType.photos_and_videos)
    >>> b['/some/path'] = p
    >>> b['/some/other/path'] = v
    >>> len(b)
    2
    >>> '/some/path' in b
    True
    >>> b['/some/path']
    BackupDevice(mount=None, backup_type=<BackupLocationType.photos: 1>)
    >>> b.no_photo_backup_devices
    1
    >>> b.no_video_backup_devices
    1
    >>> b['/yet/another/path'] = pv
    >>> b.no_photo_backup_devices
    2
    >>> b.no_video_backup_devices
    2
    >>> del b['/some/path']
    >>> b.no_photo_backup_devices
    1
    >>> b.no_video_backup_devices
    2
    >>> b['/some/other/path'] = pv2
    >>> b.no_photo_backup_devices
    2
    >>> b.no_video_backup_devices
    2
    >>> del b['/some/other/path']
    >>> del b['/yet/another/path']
    >>> len(b)
    0
    >>> b.no_photo_backup_devices
    0
    >>> b.no_video_backup_devices
    0
    """
    def __init__(self):
        self.devices = {}
        self.no_photo_backup_devices = 0
        self.no_video_backup_devices = 0

    def __setitem__(self, path: str, device: BackupDevice):
        if path in self.devices:
            del self[path]
        self.devices[path] = device
        backup_type = device.backup_type
        if backup_type in [BackupLocationType.photos,
                           BackupLocationType.photos_and_videos]:
            self.no_photo_backup_devices += 1
        if backup_type in [BackupLocationType.videos,
                           BackupLocationType.photos_and_videos]:
            self.no_video_backup_devices += 1


    def __delitem__(self, path):
        backup_type = self.devices[path].backup_type
        if backup_type in [BackupLocationType.photos,
                           BackupLocationType.photos_and_videos]:
            self.no_photo_backup_devices -= 1
        if backup_type in [BackupLocationType.videos,
                                   BackupLocationType.photos_and_videos]:
            self.no_video_backup_devices -= 1
        assert self.no_video_backup_devices >= 0
        assert self.no_photo_backup_devices >= 0
        del self.devices[path]

    def __repr__(self):
        s = '{'
        for key, value in self.devices.items():
            s += r'%r:%r %r, ' % (key, value.mount, value.backup_type)
        s = s[:-2] + '}'
        return s

    def __contains__(self, key):
        return key in self.devices

    def __len__(self):
        return len(self.devices)

    def __getitem__(self, path):
        return self.devices[path]

    def __iter__(self):
        return iter(self.devices)

    def name(self, path):
        if self.devices[path].mount is None:
            return path
        else:
            mount = self.devices[path].mount
            """ :type : QStorageInfo"""
            return mount.displayName()

    def backup_type(self, path):
        return self.devices[path].backup_type

    def multiple_backup_devices(self, file_type: FileType) -> bool:
        """

        :param file_type: whether the file is a photo or video
        :return: True if more than one backup device is being used for
        the file type
        """
        return ((file_type == FileType.photo and
                 self.no_photo_backup_devices > 1) or
                (file_type == FileType.video and
                 self.no_video_backup_devices > 1))

    def backup_possible(self, file_type: FileType) -> bool:
        """

        :param file_type: whether the file is a photo or video
        :return: True if more a backup device is being used for
        the file type
        """
        if file_type == FileType.photo:
            return self.no_photo_backup_devices > 0
        elif file_type == FileType.video:
            return self.no_video_backup_devices > 0
        else:
            logging.critical("Unrecognized file type when determining if "
                           "backup is possible")

