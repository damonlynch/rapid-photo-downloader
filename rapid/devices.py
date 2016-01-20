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
from collections import namedtuple, Counter
import re
from typing import Tuple, List, Optional

from gettext import gettext as _

from PyQt5.QtCore import QStorageInfo, QSize
from PyQt5.QtWidgets import QFileIconProvider
from PyQt5.QtGui import QIcon, QPixmap
import qrc_resources

from constants import (DeviceType, BackupLocationType, FileType)
from rpdfile import FileTypeCounter, FileSizeSum
from storage import StorageSpace, udev_attributes, UdevAttr
from camera import Camera, generate_devname

logging.basicConfig(format='%(levelname)s:%(asctime)s:%(message)s',
                    datefmt='%H:%M:%S',
                    level=logging.DEBUG)


class Device:
    r"""
    Representation of a camera, or a device, or a path.
    Files will be downloaded from it.

    To run the doctests, ensure at least one camera is plugged in
    but not mounted!

    >>> d = Device()
    >>> d.set_download_from_volume('/media/damon/EOS_DIGITAL', 'EOS_DIGITAL')
    >>> d
    'EOS_DIGITAL':'/media/damon/EOS_DIGITAL'
    >>> str(d)
    '/media/damon/EOS_DIGITAL (EOS_DIGITAL)'
    >>> d.display_name
    'EOS_DIGITAL'
    >>> d.camera_model
    >>> d.camera_port

    >>> import gphoto2 as gp
    >>> gp_context = gp.Context()
    >>> cameras = gp_context.camera_autodetect()
    >>> c = Device()
    >>> for model, port in cameras:
    ...     c.set_download_from_camera(model, port)
    ...     isinstance(c.no_storage_media, int)
    ...     isinstance(c.display_name, str)
    False
    True
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
        self.camera_model = None # type: str
        self.camera_port = None # type: str
        # Assume an MTP device is likely a smart phone or tablet
        self.is_mtp_device = False
        self.udev_name = None # type: str
        self.no_storage_media = None # type: int
        self.storage_space = [] # type: List[StorageSpace]
        self.path = None # type: str
        self.display_name = None # type: str
        self.have_optimal_display_name = False
        self.device_type = None # type: DeviceType
        self.icon_name = None # type: str
        self.can_eject = None # type: bool
        self.photo_cache_dir = None # type: str
        self.video_cache_dir = None # type: str
        self.file_size_sum = FileSizeSum()
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
            return '{} on port {}. Udev: {}; Display name: {} (optimal: {}); MTP: {' \
                   '}'.format(self.camera_model, self.camera_port, self.udev_name,
                              self.display_name, self.have_optimal_display_name, self.is_mtp_device)
        elif self.device_type == DeviceType.volume:
            if self.path != self.display_name:
                return "%s (%s)" % (self.path, self.display_name)
            else:
                return "%s" % (self.path)
        else:
            return "%s" % (self.path)

    def __eq__(self, other):
        for attr in ('device_type', 'camera_model', 'camera_port',
                     'path'):
            if getattr(self, attr) != getattr(other, attr):
                return False
        return True

    def __hash__(self):
        return hash((self.device_type, self.camera_model, self.camera_port, self.path))

    def __ne__(self, other):
        return not self.__eq__(other)

    def _get_valid_icon_name(self, possible_names):
        if possible_names is not None:
            for icon_name in possible_names:
                if QIcon.hasThemeIcon(icon_name):
                    return icon_name
        return None

    def set_download_from_camera(self, camera_model: str, camera_port: str) -> None:
        self.clear()
        self.device_type = DeviceType.camera
        self.camera_model = camera_model
        # Set default display name, for when all else fails.
        # Try to override this value below
        self.display_name = camera_model
        self.camera_port = camera_port
        self.icon_name = self._get_valid_icon_name(('camera-photo', 'camera'))

        devname = generate_devname(camera_port)
        if devname is not None:
            udev_attr = udev_attributes(devname)
            if udev_attr is not None:
                self.is_mtp_device = udev_attr.is_mtp_device
                self.udev_name = udev_attr.model
                self.display_name = udev_attr.model
        else:
            logging.error("Could not determine port values for %s %s", self.camera_model,
                          camera_port)

    def update_camera_attributes(self, display_name: str,
                                 storage_space: List[StorageSpace]) -> None:
        self.display_name = display_name
        self.have_optimal_display_name = True
        self.no_storage_media = len(storage_space)
        self.storage_space = storage_space

    def set_download_from_volume(self, path: str, display_name: str,
                                 icon_names=None, can_eject=None,
                                 mount: QStorageInfo=None) -> None:
        self.clear()
        self.device_type = DeviceType.volume
        self.path = path
        self.icon_name = self._get_valid_icon_name(icon_names)
        if not display_name.find(os.sep) >= 0:
            self.display_name = display_name
        else:
            self.display_name = os.path.basename(display_name)
        self.have_optimal_display_name = True
        self.can_eject = can_eject
        if not mount:
            mount = QStorageInfo(path)
        self.storage_space.append(StorageSpace(
                        bytes_free=mount.bytesAvailable(),
                        bytes_total=mount.bytesTotal(),
                        path=path))

    def set_download_from_path(self, path: str) -> None:
        self.clear()
        self.device_type = DeviceType.path
        self.path = path
        if path.endswith(os.sep):
            path = path[:-1]
        display_name = os.path.basename(path)
        if display_name:
            self.display_name = display_name
            self.have_optimal_display_name = True
        else:
            self.display_name = path
        # the next value is almost certainly ("folder",), but I guess it's
        # better to generate it from code
        self.icon_name = ('{}'.format(QFileIconProvider().icon(
            QFileIconProvider.Folder).name()))
        mount = QStorageInfo(path)
        self.storage_space.append(StorageSpace(
                        bytes_free=mount.bytesAvailable(),
                        bytes_total=mount.bytesTotal(),
                        path=path))

    def get_storage_space(self, index: int=0) -> StorageSpace:
        """
        Convenience function to retrieve information about bytes
        free and bytes total (capacity of the media). Almost all
        devices have only one storage media, but some cameras have
        more than one
        :param index: the storage media to get the values from
        :return: tuple of bytes free and bytes total
        """
        return self.storage_space[index]

    def name(self) -> str:
        """
        Get the name of the device, suitable to be displayed to the
        user. If the device is a path, return the path name
        :return  str containg the name
        """
        if self.device_type == DeviceType.camera:
            return self.display_name
        elif self.device_type == DeviceType.volume:
            return self.display_name
        else:
            return self.path

    def get_icon(self) -> QIcon:
        """Return icon for the device."""

        if self.device_type == DeviceType.volume:
            return QIcon(':icons/drive-removable-media.svg')
        elif self.device_type == DeviceType.path:
            return QIcon(':/icons/folder.svg')
        else:
            assert self.device_type == DeviceType.camera
            if self.is_mtp_device:
                if self.camera_model.lower().find('tablet') >= 0:
                    #TODO use tablet icon
                    pass
                return QIcon(':icons/smartphone.svg')
            return QIcon(':/icons/camera.svg')

    def get_pixmap(self, size: QSize) -> QPixmap:
        icon = self.get_icon()
        return icon.pixmap(size)

    def _delete_cache_dir(self, cache_dir) -> None:
        if cache_dir is not None:
            if os.path.isdir(cache_dir):
                assert cache_dir != os.path.expanduser('~')
                try:
                    shutil.rmtree(cache_dir, ignore_errors=True)
                except:
                    logging.error("Unknown error deleting cache directory %s", cache_dir)

    def delete_cache_dirs(self) -> None:
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
    >>> dc.known_path(d.path, DeviceType.volume)
    True
    >>> dc.known_path(d.path)
    True
    >>> dc[d_scan_id] == d
    True
    >>> dc.known_path('/root', DeviceType.path)
    False
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
    def __init__(self) -> None:
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

    def known_path(self, path: str, device_type: Optional[DeviceType]=None) -> bool:
        """
        Check if the path is already in the list of devices
        :param path: path to check
        :return: True if the path is already being processed, else False
        """
        for scan_id in self.devices:
            device = self.devices[scan_id]  # type: Device
            if device.path == path:
                if device_type is None:
                    return True
                elif device.device_type == device_type:
                    return True
        return False

    def known_device(self, device: Device) -> bool:
        return device in list(self.devices.values())

    def scan_id_from_path(self, path: str, device_type: Optional[DeviceType]=None) -> Optional[int]:
        for scan_id in self.devices:
            device = self.devices[scan_id]  # type: Device
            if device.path == path:
                if device_type is None:
                    return scan_id
                elif device.device_type == device_type:
                    return scan_id
        return None

    def scan_id_from_camera_model_port(self, model: str, port: str) -> int:
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

    def delete_cache_dirs(self) -> None:
        """
        Delete all Download Caches and their contents any devices might have
        """
        for device in self.devices.values():
            device.delete_cache_dirs()

    def __delitem__(self, scan_id):
        d = self.devices[scan_id] # type: Device
        if d.device_type == DeviceType.camera:
            del self.cameras[d.camera_port]
        d.delete_cache_dirs()
        del self.devices[scan_id]

    def __getitem__(self, scan_id) -> Device:
        return self.devices[scan_id]

    def __len__(self) -> int:
        return len(self.devices)

    def __contains__(self, scan_id) -> bool:
        return scan_id in self.devices

    def __iter__(self):
        return iter(self.devices)

    def get_main_window_display_name_and_icon(self) -> Tuple[str, QIcon]:
        """
        Generate the name to display at the top left of the main
        window, indicating the source of the files
        :return: string to display
        """

        if not len(self):
            return _('Select Source'), QIcon(':/icons/folder.svg')
        elif len(self) == 1:
            device = list(self.devices.values())[0]
            return device.display_name, device.get_icon()
        else:
            device_types = Counter(d.device_type for d in self.devices.values())
            mtp_devices = [d for d in self.devices.values() if d.is_mtp_device]
            assert len(device_types)
            if len(device_types) == 1:
                device_type = list(device_types)[0]
                if len(self) == 2:
                    devices = list(self.devices.values())  # type: List[Device]
                    text = _('%(device1)s + %(device2)s') % {'device1': devices[0].display_name,
                                                            'device2': devices[1].display_name}
                    if device_type == DeviceType.camera and len(mtp_devices) != 2:
                        return text, QIcon(':/icons/camera.svg')
                    return text, devices[0].get_icon()
                if device_type == DeviceType.camera:
                    # Number of cameras e.g. 3 Cameras
                    text = _('%(no_cameras)s Cameras') % {'no_cameras':
                                                              device_types[DeviceType.camera]}
                    return text, QIcon(':/icons/camera.svg')
                elif device_type == DeviceType.volume:
                    text = _('%(no_volumes)s Volumes') % {'no_volumes':
                                                              device_types[DeviceType.volume]}
                    return text, QIcon(':/icons/drive-removable-media.svg')
            # Mixed devices (e.g. cameras, card readers), or only external
            # volumes
            return _('%(no_devices)s Devices') % {'no_devices': len(self)}, \
                   QIcon(':/icons/computer.svg')


BackupDevice = namedtuple('BackupDevice', ['mount', 'backup_type'])


class BackupDeviceCollection:
    r"""
    Track and manage devices (and manual paths) used for backing up.
    Photos can be backed up to one location, and videos to another; or
    they can be backed up to the same location.

    >>> b = BackupDeviceCollection()
    >>> len(b)
    0
    >>> p = BackupDevice(mount=None, backup_type=BackupLocationType.photos)
    >>> v = BackupDevice(mount=None, backup_type=BackupLocationType.videos)
    >>> pv = BackupDevice(mount=None,
    ...                   backup_type=BackupLocationType.photos_and_videos)
    >>> pv2 = BackupDevice(mount=None,
    ...                   backup_type=BackupLocationType.photos_and_videos)
    >>> b['/some/path'] = p
    >>> b
    {'/some/path':None <BackupLocationType.photos: 1> 0}
    >>> b.device_id('/some/path')
    0
    >>> b['/some/other/path'] = v
    >>> len(b)
    2
    >>> b.device_id('/some/other/path')
    1
    >>> b.device_id('/unknown/path')
    >>>
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
        self._device_ids = {}
        self._device_id = 0

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
        self._device_ids[path] = self._device_id
        self._device_id += 1


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
        del self._device_ids[path]

    def __repr__(self):
        s = '{'
        for key, value in self.devices.items():
            s += r'%r:%r %r %s, ' % (key, value.mount, value.backup_type,
                                     self._device_ids[key])
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

    def device_id(self, path: str) -> int:
        if path in self:
            return self._device_ids[path]
        return None

    def name(self, path) -> str:
        if self.devices[path].mount is None:
            return path
        else:
            mount = self.devices[path].mount # type:  QStorageInfo
            return mount.displayName()

    def backup_type(self, path) -> BackupLocationType:
        return self.devices[path].backup_type

    def multiple_backup_devices(self, file_type: FileType) -> bool:
        """

        :param file_type: whether the file is a photo or video
        :return: True if more than one backup device is being used for
        the file type
        """
        return ((file_type == FileType.photo and self.no_photo_backup_devices > 1) or
                (file_type == FileType.video and self.no_video_backup_devices > 1))

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
            logging.critical("Unrecognized file type when determining if backup is possible")

