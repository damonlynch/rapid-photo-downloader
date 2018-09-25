# Copyright (C) 2015-2018 Damon Lynch <damonlynch@gmail.com>

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
Handle Devices and Device Collections.

In Rapid Photo Downloader, "Device" has two meanings, depending on the
context:
1. In the GUI, a Device is a camera or a volume (external drive)
2. In code, a Device is one of a camera, volume, or path
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2015-2018, Damon Lynch"

import sys
import shutil
import os
import logging
import itertools
from collections import namedtuple, Counter, defaultdict
from typing import Tuple, List, Optional, Set, Dict, Union, DefaultDict

from gettext import gettext as _

from PyQt5.QtCore import QStorageInfo, QSize
from PyQt5.QtWidgets import QFileIconProvider
from PyQt5.QtGui import QIcon, QPixmap

import raphodo.qrc_resources as qrc_resources
from raphodo.constants import (
    DeviceType, BackupLocationType, FileType, DeviceState, DownloadStatus, ExifSource,
    DownloadingFileTypes, BackupFailureType
)
from raphodo.rpdfile import FileTypeCounter, FileSizeSum, Photo, Video, RPDFile
from raphodo.storage import (
    StorageSpace, udev_attributes, UdevAttr, get_path_display_name, validate_download_folder,
    ValidatedFolder, CameraDetails, get_uri, fs_device_details
)
from raphodo.camera import generate_devname
from raphodo.utilities import (
    number, make_internationalized_list, stdchannel_redirected, same_device
)
import raphodo.exiftool as exiftool
from raphodo.problemnotification import FsMetadataWriteProblem

display_devices = (DeviceType.volume, DeviceType.camera)
sample_file_complete = namedtuple('sample_file_complete', 'full_file_name, file_type')
device_name_uri = namedtuple('device_name_uri', 'name uri')



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
    ...     isinstance(c.display_name, str)
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
        self.camera_model = None  # type: str
        self.camera_port = None  # type: str
        # Assume an MTP device is likely a smart phone or tablet
        self.is_mtp_device = False
        self.udev_name = None  # type: str
        self.storage_space = []  # type: List[StorageSpace]
        # Name of storage on a camera
        self.storage_descriptions = []  # type: List[str]

        self.path = None  # type: str
        self.display_name = None  # type: str
        self.have_optimal_display_name = False
        self.device_type = None  # type: DeviceType
        self.icon_name = None  # type: str
        self.can_eject = None  # type: bool
        self.photo_cache_dir = None  # type: str
        self.video_cache_dir = None  # type: str
        self.file_size_sum = FileSizeSum()
        self.file_type_counter = FileTypeCounter()
        self.download_statuses = set()  # type: Set[DownloadStatus]
        self._uri = ''
        # If the entire video or photo is required to extract metadata
        # (which affects thumbnail generation too).
        # Set only if downloading from a camera / phone.
        self.entire_video_required = None  # type: bool
        self.entire_photo_required = None  # type: bool

    def __repr__(self):
        if self.device_type == DeviceType.camera:
            return "%r:%r" % (self.camera_model, self.camera_port)
        elif self.device_type == DeviceType.volume:
            return "%r:%r" % (self.display_name, self.path)
        else:
            return "%r" % self.path

    def __str__(self):
        if self.device_type == DeviceType.camera:
            return '{} on port {}. Udev: {}; Display name: {} (optimal: {}); MTP: {}'.format(
                              self.camera_model, self.camera_port, self.udev_name,
                              self.display_name, self.have_optimal_display_name, self.is_mtp_device)
        elif self.device_type == DeviceType.volume:
            if self.path != self.display_name:
                return "%s (%s)" % (self.path, self.display_name)
            else:
                return "%s" % (self.path)
        else:
            return "%s" % (self.path)

    def __eq__(self, other):
        for attr in ('device_type', 'camera_model', 'camera_port', 'path'):
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

    @property
    def uri(self) -> str:
        if self._uri:
            return self._uri

        if self.device_type == DeviceType.camera:
            if self.storage_descriptions:
                storage_desc = self.storage_descriptions[0]
            else:
                storage_desc = ''
            camera_details = CameraDetails(
                model=self.camera_model, port=self.camera_port, display_name=self.display_name,
                is_mtp=self.is_mtp_device, storage_desc=storage_desc
            )
            self._uri = get_uri(camera_details=camera_details)
        else:
            self._uri = get_uri(path=self.path)

        return self._uri

    def set_download_from_camera(self, camera_model: str, camera_port: str) -> None:
        self.clear()
        self.device_type = DeviceType.camera
        self.camera_model = camera_model
        # Set default display name, for when all else fails.
        # Try to override this value below
        self.display_name = camera_model
        self.camera_port = camera_port
        self.icon_name = self._get_valid_icon_name(('camera-photo', 'camera'))

        # Assign default udev name if cannot determine from udev itself
        self.udev_name = camera_model

        devname = generate_devname(camera_port)
        if devname is not None:
            udev_attr = udev_attributes(devname)
            if udev_attr is not None:
                self.is_mtp_device = udev_attr.is_mtp_device
                self.udev_name = udev_attr.model
                self.display_name = udev_attr.model
        else:
            logging.error("Could not determine udev values for %s %s",
                          self.camera_model, camera_port)

    def update_camera_attributes(self, display_name: str,
                                 storage_space: List[StorageSpace],
                                 storage_descriptions: List[str]) -> None:
        self.display_name = display_name
        self.have_optimal_display_name = True
        self.storage_space = storage_space
        self.storage_descriptions = storage_descriptions

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

    def get_pixmap(self, size: QSize=QSize(30, 30)) -> QPixmap:
        icon = self.get_icon()
        return icon.pixmap(size)

    def _delete_cache_dir(self, cache_dir) -> None:
        if cache_dir:
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
    >>> len(dc.volumes_and_cameras)
    1
    >>> len(dc.this_computer)
    0
    >>> dc.known_path('/root', DeviceType.path)
    False
    >>> dc.known_path('/root')
    False
    >>> c_scan_id = dc.add_device(c)
    >>> c_scan_id
    1
    >>> len(dc)
    2
    >>> len(dc.volumes_and_cameras)
    2
    >>> len(dc.this_computer)
    0
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
    >>> len(dc.volumes_and_cameras)
    1
    >>> len(dc.this_computer)
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
    >>> len(dc.volumes_and_cameras)
    0
    >>> len(dc.this_computer)
    0
    >>> dc.delete_device(e)
    False
    """
    def __init__(self, exiftool_process: Optional[exiftool.ExifTool]=None,
                 rapidApp=None) -> None:

        self.rapidApp = rapidApp

        self.devices = {}  # type: Dict[int, Device]
        # port: model
        self.cameras = {}  # type: Dict[str, str]

        # Track device names and uris to be able to report this information
        # after a device has been removed
        # scan_id: name uri
        self.device_archive = {}  # type: Dict[int, device_name_uri]

        # Used to assign scan ids
        self.scan_counter = 0  # type: int

        # scan_id: DeviceState
        self.device_state = {}  # type: Dict[int, DeviceState]

        # Track which devices are being scanned, by scan_id
        self.scanning = set()  # type: Set[int]
        # Track which downloads are running, by scan_id

        self.downloading = set()  # type: Set[int]
        # Track which devices have been downloaded from during one
        # download, by display name. Must do it by display name
        # because some devices could be removed before all devices
        # have been downloaded from.
        self.have_downloaded_from = set()  # type: Set[str]

        # Track which devices are thumbnailing, by scan_id
        self.thumbnailing = set()  # type: Set[int]

        # Track the unmounting of unscanned cameras by port and model
        # port: model
        self.cameras_to_gvfs_unmount_for_scan = {}  # type: Dict[str, str]

        # Which scanned cameras need to be unmounted for a download to start, by scan_id
        self.cameras_to_gvfs_unmount_for_download = set()  # type: Set[int]
        self.cameras_to_stop_thumbnailing = set()

        # Automatically detected devices where the user has explicitly said to ignore it
        # port: model
        self.ignored_cameras = {}  # type: Dict[str, str]
        # List[path]
        self.ignored_volumes = []  # type: List[str]

        # Devices that were set to autodownload while the program
        # is in a paused state
        self.queued_to_download = set()  # type: Set[int]

        self.volumes_and_cameras = set()  # type: Set[int]
        self.this_computer = set()  # type: Set[int]

        # List of devices that were detected at program startup
        # scan_id
        self.startup_devices = []  # type: List[int]

        # Sample exif bytes of photo on most recent device scanned
        self._sample_photo = None  # type: Optional[Photo]
        self._sample_video = None  # type: Optional[Video]
        self._sample_files_complete = []  # type: List[sample_file_complete]
        self.exiftool_process = exiftool_process

        self._map_set = {
            DeviceType.path: self.this_computer,
            DeviceType.camera: self.volumes_and_cameras,
            DeviceType.volume: self.volumes_and_cameras
        }
        self._map_plural_types = {
            DeviceType.camera: _('Cameras'),
            DeviceType.volume: _('Devices')
        }

    def download_start_blocked(self) -> bool:
        """
        Determine if a camera needs to be unmounted or thumbnailing needs to be
        terminated for a camera in order for a download to proceed
        :return: True if so, else False
        """

        if len(self.cameras_to_gvfs_unmount_for_download) > 0 and len(
                self.cameras_to_stop_thumbnailing):
            logging.debug(
                "Download is blocked because %s camera(s) are being unmounted from GVFS "
                "and %s camera(s) are having their thumbnailing terminated",
                len(self.cameras_to_gvfs_unmount_for_download),
                len(self.cameras_to_stop_thumbnailing)
            )
        elif len(self.cameras_to_gvfs_unmount_for_download) > 0:
            logging.debug(
                "Download is blocked because %s camera(s) are being unmounted from GVFS",
                len(self.cameras_to_gvfs_unmount_for_download)
            )
        elif len(self.cameras_to_stop_thumbnailing) > 0:
            logging.debug(
                "Download is blocked because %s camera(s) are having their thumbnailing "
                "terminated", len(self.cameras_to_stop_thumbnailing)
            )

        return len(self.cameras_to_gvfs_unmount_for_download) > 0 or len(
                    self.cameras_to_stop_thumbnailing) > 0

    def logState(self) -> None:
        logging.debug("-- Device Collection --")
        logging.debug(
            '%s devices: %s volumes/cameras (%s cameras), %s this computer',
            len(self.devices), len(self.volumes_and_cameras), len(self.cameras),
            len(self.this_computer)
        )
        logging.debug("Device states: %s", ', '.join(
            '%s: %s' % (self[scan_id].display_name, self.device_state[scan_id].name)
            for scan_id in self.device_state))
        if len(self.scanning):
            scanning = ('%s' % ', '.join(self[scan_id].display_name for scan_id in self.scanning))
            logging.debug("Scanning: %s", scanning)
        else:
            logging.debug("No devices scanning")
        if len(self.downloading):
            downloading = (
                    '%s' % ', '.join(self[scan_id].display_name for scan_id in self.downloading)
            )
            logging.debug("Downloading: %s", downloading)
        else:
            logging.debug("No devices downloading")
        if len(self.thumbnailing):
            thumbnailing = (
                    '%s' % ', '.join(self[scan_id].display_name for scan_id in self.thumbnailing)
            )
            logging.debug("Thumbnailing: %s", thumbnailing)
        else:
            logging.debug("No devices thumbnailing")

    def add_device(self, device: Device, on_startup: bool=False) -> int:
        """
        Add a new device to the device collection
        :param device: device to add
        :param on_startup: if True, the device is being added during
         the program's startup phase
        :return: the scan id assigned to the device
        """

        scan_id = self.scan_counter
        self.scan_counter += 1
        self.devices[scan_id] = device
        self.device_state[scan_id] = DeviceState.pre_scan
        if on_startup:
            self.startup_devices.append(scan_id)
        if device.camera_port:
            port = device.camera_port
            assert port not in self.cameras
            self.cameras[port] = device.camera_model
        if device.device_type in display_devices:
            self.volumes_and_cameras.add(scan_id)
        else:
            self.this_computer.add(scan_id)

        self.device_archive[scan_id] = device_name_uri(device.display_name, device.uri)
        return scan_id

    def set_device_state(self, scan_id: int, state: DeviceState) -> None:
        logging.debug("Setting device state for %s to %s",
                      self.devices[scan_id].display_name, state.name)
        self.device_state[scan_id] = state
        if state == DeviceState.scanning:
            self.scanning.add(scan_id)
        elif state == DeviceState.downloading:
            self.downloading.add(scan_id)
            self.have_downloaded_from.add(self.devices[scan_id].display_name)
        elif state == DeviceState.thumbnailing:
            self.thumbnailing.add(scan_id)

        if state != DeviceState.scanning and scan_id in self.scanning:
            self.scanning.remove(scan_id)
        if state != DeviceState.downloading and scan_id in self.downloading:
            self.downloading.remove(scan_id)
        if state != DeviceState.thumbnailing and scan_id in self.thumbnailing:
            self.thumbnailing.remove(scan_id)

    def ignore_device(self, scan_id: int) -> None:
        """
        For the remainder of this program's instantiation, don't
        automatically detect this device.

        A limitation of this is that when a camera is physically removed
        and plugged in again, it gets a new port. In which casae it's a
        "different" device.

        :param scan_id: scan id of the device to ignore
        """

        device = self.devices[scan_id]
        if device.device_type == DeviceType.camera:
            logging.debug("Marking camera %s on port %s as explicitly removed. Will ignore it "
                          "until program exit.", device.camera_model, device.camera_port)
            self.ignored_cameras[device.camera_port] = device.camera_model
        elif device.device_type == DeviceType.volume:
            logging.debug("Marking volume %s as explicitly removed. Will ignore it "
                          "until program exit.", device.path)
            self.ignored_volumes.append(device.path)
        else:
            logging.error("Device collection unexpectedly received path to ignore: ignoring")

    def user_marked_camera_as_ignored(self, model: str, port: str) -> bool:
        """
        Check if camera is in set of devices to ignore because they were explicitly
        removed by the user

        :param model: camera model
        :param port:  camera port
        :return: return True if camera is in set of devices to ignore
        """

        if port in self.ignored_cameras:
            return self.ignored_cameras[port] == model
        return False

    def user_marked_volume_as_ignored(self, path: str) -> bool:
        """
        Check if volume's path is in list of devices to ignore because they were explicitly
        removed by the user

        :param: path: the device's path
        :return: return True if camera is in set of devices to ignore
        """

        return path in self.ignored_volumes

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
                if device_type is None or device.device_type == device_type:
                    return True
        return False

    def known_device(self, device: Device) -> bool:
        return device in list(self.devices.values())

    def scan_id_from_path(self, path: str, device_type: Optional[DeviceType]=None) -> Optional[int]:
        for scan_id, device in self.devices.items():
            if device.path == path:
                if device_type is None or device.device_type == device_type:
                    return scan_id
        return None

    def scan_id_from_camera_model_port(self, model: str, port: str) -> Optional[int]:
        """

        :param model: model name of camera being searched for
        :param port: port of camera being searched for
        :return: scan id of camera if known, else None
        """

        for scan_id, device in self.devices.items():
            if (device.device_type == DeviceType.camera and device.camera_model == model and
                    device.camera_port == port):
                return scan_id
        return None

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

    def delete_cache_dirs_and_sample_video(self) -> None:
        """
        Delete all Download Caches and their contents any devices might
        have, as well as any sample video.
        """
        for device in self.devices.values():
            device.delete_cache_dirs()
        self._delete_sample_photo_video(at_program_close=True)

    def _add_complete_sample_file(self, sample_photo_video: RPDFile) -> None:
        """
        Don't delete this fully downloaded file, as it might be downloaded by the user,
        in which case it's already been recorded as a RPDFile.cache_full_file_name
        Instead add it to a list of files to possibly expunge at program exit.

        :param sample_photo_video: sample photo or video
        """

        logging.debug(
            "Adding %s to list of complete sample %s files to potentially delete "
            "at program exit",
            sample_photo_video.temp_sample_full_file_name, sample_photo_video.file_type.name
        )
        self._sample_files_complete.append(
            sample_file_complete(
                sample_photo_video.temp_sample_full_file_name,
                sample_photo_video.file_type.name
            )
        )

    def _do_delete__sample_photo_video(self, sample_photo_video: RPDFile) -> None:
        """
        Delete a temporary sample photo or video from the file system
        :param sample_photo_video: file to delete
        :param sample_type: "photo" or "video"
        """

        if (sample_photo_video is not None and
                sample_photo_video.temp_sample_full_file_name is not None and
                sample_photo_video.from_camera):
            try:
                sample_type = sample_photo_video.file_type.name
            except Exception:
                sample_type = 'unknown'
            try:
                assert sample_photo_video.temp_sample_full_file_name
            except:
                logging.error("Expected sample file name in sample %s", sample_type)
            else:
                if os.path.isfile(sample_photo_video.temp_sample_full_file_name):
                    logging.info(
                        "Removing temporary sample %s %s",
                        sample_type,
                        sample_photo_video.temp_sample_full_file_name
                    )
                    try:
                        os.remove(sample_photo_video.temp_sample_full_file_name)
                    except Exception:
                        logging.exception(
                            "Error removing temporary sample %s file %s",
                            sample_type,
                            sample_photo_video.temp_sample_full_file_name
                        )

    def _delete_sample_photo_video(self, at_program_close: bool,
                                   file_type: Optional[FileType]=None) -> None:
        """
        Delete sample photo or video that is used for metadata extraction
        to provide example for file renaming.

        :param at_program_close: if True, the program is exiting
        :param file_type: if specified, delete sample file of this type
         regardless of whether the program is exiting
        """

        if file_type == FileType.photo:
            samples = self._sample_photo,
        elif file_type == FileType.video:
            samples = self._sample_video,
        else:
            samples = self._sample_photo, self._sample_video

        for sample in samples:
            self._do_delete__sample_photo_video(sample)

        if at_program_close and self._sample_files_complete:
            remaining_files = (
                photo_video for photo_video in self._sample_files_complete
                if os.path.isfile(photo_video.full_file_name)
            )
            for photo_video in remaining_files:
                logging.info(
                    "Removing temporary sample %s %s",
                    photo_video.file_type.name, photo_video.full_file_name
                )
                try:
                    os.remove(photo_video.full_file_name)
                except Exception:
                    logging.exception(
                        "Error removing temporary sample %s file %s",
                        photo_video.file_type.name, photo_video
                    )

    def map_set(self, device: Device) -> Set:
        return self._map_set[device.device_type]

    def downloading_from(self) -> str:
        """
        :return: string showing which devices are being downloaded from
        """

        display_names = [self.devices[scan_id].display_name for scan_id in self.downloading]
        return _('Downloading from %(device_names)s') % dict(
            device_names=make_internationalized_list(display_names))

    def reset_and_return_have_downloaded_from(self) -> str:
        """
        Reset the set of devices that have been downloaded from,
        and return the string that
        :return: string showing which devices have been downloaded from
         during this download
        """
        display_names = make_internationalized_list(list(self.have_downloaded_from))
        self.have_downloaded_from = set()  # type: Set[str]
        return display_names

    def __delitem__(self, scan_id: int):
        d = self.devices[scan_id]  # type: Device
        if d.device_type == DeviceType.camera:
            del self.cameras[d.camera_port]
            if d.camera_port in self.cameras_to_gvfs_unmount_for_scan:
                del self.cameras_to_gvfs_unmount_for_scan[d.camera_port]

        self.map_set(d).remove(scan_id)
        d.delete_cache_dirs()
        del self.devices[scan_id]
        if scan_id in self.scanning:
            self.scanning.remove(scan_id)
        if scan_id in self.downloading:
            self.downloading.remove(scan_id)
        if scan_id in self.queued_to_download:
            self.queued_to_download.remove(scan_id)
        if scan_id in self.thumbnailing:
            self.thumbnailing.remove(scan_id)
        if scan_id in self.cameras_to_gvfs_unmount_for_download:
            self.cameras_to_gvfs_unmount_for_download.remove(scan_id)
        if scan_id in self.cameras_to_stop_thumbnailing:
            self.cameras_to_stop_thumbnailing.remove(scan_id)
        if scan_id in self.this_computer:
            self.this_computer.remove(scan_id)
        if scan_id in self.volumes_and_cameras:
            self.volumes_and_cameras.remove(scan_id)
        del self.device_state[scan_id]

    def __getitem__(self, scan_id: int) -> Device:
        return self.devices[scan_id]

    def __len__(self) -> int:
        return len(self.devices)

    def __contains__(self, scan_id: int) -> bool:
        return scan_id in self.devices

    def __iter__(self):
        return iter(self.devices)

    def _mixed_devices(self, device_type_text: str) -> str:
        try:
            text_number = number(len(self.volumes_and_cameras)).number.capitalize()
        except KeyError:
            text_number = len(self.volumes_and_cameras)
        # Translators: e.g. Three Devices
        return _('%(no_devices)s %(device_type)s') % dict(
            no_devices=text_number, device_type=device_type_text)

    def _update_sample_file(self, file_type: FileType) -> None:

        if file_type == FileType.photo:
            assert self._sample_photo.file_type == FileType.photo
            full_file_name = self._sample_photo.get_current_sample_full_file_name()
            rpd_file = self._sample_photo
        else:
            assert self._sample_video.file_type == FileType.video
            full_file_name = self._sample_video.get_current_sample_full_file_name()
            rpd_file = self._sample_video

        if not os.path.isfile(full_file_name):
            # file no longer exists - it may have been downloaded or deleted
            # attempt to find an appropriate file from the in memory sql database of displayed
            # files
            scan_id = rpd_file.scan_id
            if not scan_id in self.devices:
                logging.debug('Failed to set a new sample because the device no longer exists')
                return
            rpd_file = self.rapidApp.thumbnailModel.getSampleFile(
                scan_id=scan_id, device_type=self[scan_id].device_type, file_type=file_type
            )
            if rpd_file is None:
                logging.debug(
                    'Failed to set new sample %s because suitable sample does not exist',
                    file_type.name
                )
            else:
                sample_full_file_name = rpd_file.get_current_full_file_name()
                if file_type == FileType.photo:
                    logging.debug('Updated sample photo with %s', sample_full_file_name)
                    self.sample_photo = rpd_file
                else:
                    logging.debug('Updated sample video with %s', sample_full_file_name)
                    self.sample_video = rpd_file

    @property
    def sample_photo(self) -> Optional[Photo]:
        """
        Sample photos can be:
        (1) excerpts of a photo from a camera, saved on the file system in a
            temp file (used by ExifTool)
        (2) bytes saved in memory i.e. raw_exif_bytes (exiv2)
        (3) actual complete photos already on the file system (ExifTool or
            exiv2)
        """

        if self._sample_photo is None:
            return None

        # does the photo still exist?
        if self._sample_photo.exif_source == ExifSource.actual_file:
            self._update_sample_file(file_type=FileType.photo)

        if self._sample_photo.metadata is None and not self._sample_photo.metadata_failure:
            with stdchannel_redirected(sys.stderr, os.devnull):
                if self._sample_photo.exif_source == ExifSource.raw_bytes:
                    self._sample_photo.load_metadata(
                        raw_bytes=bytearray(self._sample_photo.raw_exif_bytes)
                    )
                elif self._sample_photo.exif_source == ExifSource.app1_segment:
                    self._sample_photo.load_metadata(
                        app1_segment=bytearray(self._sample_photo.raw_exif_bytes)
                    )
                else:
                    assert self._sample_photo.exif_source == ExifSource.actual_file
                    full_file_name = self._sample_photo.get_current_sample_full_file_name()
                    self._sample_photo.load_metadata(
                        full_file_name=full_file_name, et_process=self.exiftool_process
                    )
        return self._sample_photo

    @sample_photo.setter
    def sample_photo(self, photo: Photo) -> None:
        if self._sample_photo is not None:
            if self._sample_photo.temp_sample_is_complete_file:
                self._add_complete_sample_file(self._sample_photo)
            elif self._sample_photo.temp_sample_full_file_name:
                self._delete_sample_photo_video(file_type=FileType.photo, at_program_close=False)
        self._sample_photo = photo
        
    @property
    def sample_video(self) -> Optional[Video]:
        """
        Sample videos can be either excerpts of a video from a camera or
        actual videos already on the file system.
        """

        if self._sample_video is None:
            return None

        self._update_sample_file(file_type=FileType.video)

        if self._sample_video.metadata is None and not self._sample_video.metadata_failure:

            try:
                assert self._sample_video.temp_sample_full_file_name or os.path.isfile(
                    self._sample_video.full_file_name)

                full_file_name = self._sample_video.get_current_sample_full_file_name()

                self._sample_video.load_metadata(
                    full_file_name=full_file_name,
                    et_process=self.exiftool_process)
                if self._sample_video.metadata_failure:
                    logging.error("Failed to load sample video metadata")
            except AssertionError:
                logging.error("Expected sample file name in sample video")
            except:
                logging.error("Exception while attempting to load sample video metadata")
        return self._sample_video

    @sample_video.setter
    def sample_video(self, video: Video) -> None:
        if self._sample_video is not None and self._sample_video.temp_sample_is_complete_file:
            self._add_complete_sample_file(self._sample_video)
        else:
            self._delete_sample_photo_video(file_type=FileType.video, at_program_close=False)
        self._sample_video = video

    def get_main_window_display_name_and_icon(self) -> Tuple[str, QIcon]:
        """
        Generate the name to display at the top left of the main
        window, indicating the source of the files.

        :return: string to display and associated icon
        """

        if not len(self):
            return _('Select Source'), QIcon(':/icons/computer.svg')
        elif len(self) == 1:
            # includes case where path is the only device
            device = list(self.devices.values())[0]
            return device.display_name, device.get_icon()
        else:
            non_pc_devices = [device for device in self.devices.values()
                              if device.device_type != DeviceType.path]   # type: List[Device]
            assert len(non_pc_devices) == len(self.volumes_and_cameras)
            device_types = Counter(d.device_type for d in non_pc_devices)
            if len(device_types) == 1:
                device_type = list(device_types)[0]
                device_type_text = self._map_plural_types[device_type]
            else:
                device_type = None
                device_type_text = _('Devices')

            if len(self.this_computer) == 1:
                assert len(self.this_computer) < 2
                assert len(self.this_computer) > 0

                icon = QIcon(':/icons/computer.svg')
                devices = list(self.volumes_and_cameras)
                computer_display_name=self.devices[list(self.this_computer)[0]].display_name

                if len(self.volumes_and_cameras) == 1:
                    device_display_name = self.devices[devices[0]].display_name
                else:
                    assert len(self.volumes_and_cameras) > 1
                    device_display_name = self._mixed_devices(device_type_text)

                text = _('%(device1)s + %(device2)s') % {'device1': device_display_name,
                                                                'device2': computer_display_name}
                return text, icon
            else:
                assert len(self.this_computer) == 0

                mtp_devices = [d for d in non_pc_devices if d.is_mtp_device]

                if len(device_types) == 1:
                    if len(self) == 2:
                        devices = non_pc_devices
                        text = _('%(device1)s + %(device2)s') % {'device1': devices[0].display_name,
                                                                'device2': devices[1].display_name}
                        if device_type == DeviceType.camera and len(mtp_devices) != 2:
                            return text, QIcon(':/icons/camera.svg')
                        return text, devices[0].get_icon()
                    try:
                        text_number = number(len(self.volumes_and_cameras)).number.capitalize()
                    except KeyError:
                        text_number = len(self.volumes_and_cameras)
                    if device_type == DeviceType.camera:
                        # Number of cameras e.g. 3 Cameras
                        text = _('%(no_cameras)s Cameras') % {'no_cameras': text_number}
                        if len(mtp_devices) == len(self.volumes_and_cameras):
                            return text, non_pc_devices[0].get_icon()
                        return text, QIcon(':/icons/camera.svg')
                    elif device_type == DeviceType.volume:
                        text = _('%(no_devices)s Devices') % dict(no_devices=text_number)
                        return text, QIcon(':/icons/drive-removable-media.svg')
                else:
                    device_display_name = self._mixed_devices(device_type_text)
                    icon = QIcon(':/icons/computer.svg')
                    return device_display_name, icon


# QStorageInfo, BackupLocationType
BackupDevice = namedtuple('BackupDevice', 'mount, backup_type')

# QStorageInfo, str, str, BackupLocationType
BackupVolumeDetails = namedtuple('BackupVolumeDetails', 'mount name path backup_type '
                                                        'os_stat_device')


def nth(iterable, n, default=None):
    "Returns the nth item or a default value"

    return next(itertools.islice(iterable, n, None), default)


class BackupDeviceCollection:
    r"""
    Track and manage devices (and manual paths) used for backing up.
    Photos can be backed up to one location, and videos to another; or
    they can be backed up to the same location.

    If a BackupDevice's mount is None, then it is assumed to be
    a manually specified path.

    Backup devices are indexed by path, not id

    >>> b = BackupDeviceCollection()
    >>> len(b)
    0
    >>> p = BackupDevice(mount=None, backup_type=BackupLocationType.photos)
    >>> p2 = BackupDevice(mount=None, backup_type=BackupLocationType.photos)
    >>> v = BackupDevice(mount=None, backup_type=BackupLocationType.videos)
    >>> pv = BackupDevice(mount=None,
    ...                   backup_type=BackupLocationType.photos_and_videos)
    >>> pv2 = BackupDevice(mount=None,
    ...                   backup_type=BackupLocationType.photos_and_videos)
    >>> b['/some/photo/path'] = p
    >>> b
    {'/some/photo/path':None <BackupLocationType.photos: 1> 0}
    >>> b.device_id('/some/photo/path')
    0
    >>> b['/some/other/photo/path'] = p2
    >>> del b['/some/other/photo/path']
    >>> b['/some/video/path'] = v
    >>> len(b)
    2
    >>> b.device_id('/some/video/path')
    2
    >>> b.device_id('/unknown/path')
    >>>
    >>> '/some/photo/path' in b
    True
    >>> b['/some/photo/path']
    BackupDevice(mount=None, backup_type=<BackupLocationType.photos: 1>)
    >>> len(b.photo_backup_devices)
    1
    >>> len(b.video_backup_devices)
    1
    >>> b['/some/photo/video/path'] = pv
    >>> len(b.photo_backup_devices)
    2
    >>> len(b.video_backup_devices)
    2
    >>> del b['/some/photo/path']
    >>> len(b.photo_backup_devices)
    1
    >>> len(b.video_backup_devices)
    2
    >>> b['/some/video/path'] = pv2
    >>> len(b.photo_backup_devices)
    2
    >>> len(b.video_backup_devices)
    2
    >>> del b['/some/video/path']
    >>> del b['/some/photo/video/path']
    >>> len(b)
    0
    >>> len(b.photo_backup_devices)
    0
    >>> len(b.video_backup_devices)
    0
    """
    def __init__(self, rapidApp=None):
        self.rapidApp = rapidApp
        self.devices = dict()  # type: Dict[str, BackupDevice]
        # Set[path]
        self.photo_backup_devices = set()  # type: Set[str]
        self.video_backup_devices = set()  # type: Set[str]

        self._device_ids = {}
        self._device_id = 0

    def __setitem__(self, path: str, device: BackupDevice):
        if path in self.devices:
            del self[path]
        self.devices[path] = device
        backup_type = device.backup_type
        if backup_type in [BackupLocationType.photos,
                           BackupLocationType.photos_and_videos]:
            self.photo_backup_devices.add(path)
        if backup_type in [BackupLocationType.videos,
                           BackupLocationType.photos_and_videos]:
            self.video_backup_devices.add(path)
        self._device_ids[path] = self._device_id
        self._device_id += 1


    def __delitem__(self, path):
        backup_type = self.devices[path].backup_type
        if backup_type in (BackupLocationType.photos, BackupLocationType.photos_and_videos):
            self.photo_backup_devices.remove(path)
        if backup_type in (BackupLocationType.videos, BackupLocationType.photos_and_videos):
            self.video_backup_devices.remove(path)
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

    def all_paths(self) -> List[str]:
        return list(self.devices.keys())

    def device_id(self, path: str) -> Optional[int]:
        if path in self:
            return self._device_ids[path]
        return None

    def name(self, path: str, shorten: bool=False) -> str:
        """
        :param path:
        :param shorten: if True, and backup type is not an
         automatically detected device, return the path basename
        :return: device mount name, or path / path basename
        """

        if self.devices[path].mount is None:
            if shorten:
                return get_path_display_name(path)[0]
            else:
                return path
        else:
            mount = self.devices[path].mount  # type:  QStorageInfo
            if not shorten:
                return mount.displayName()
            else:
                name = mount.name()
                if name:
                    return name
                else:
                    return get_path_display_name(mount.rootPath())[0]

    def backup_type(self, path) -> BackupLocationType:
        return self.devices[path].backup_type

    def multiple_backup_devices(self, file_type: FileType) -> bool:
        """

        :param file_type: whether the file is a photo or video
        :return: True if more than one backup device is being used for
        the file type
        """
        return ((file_type == FileType.photo and len(self.photo_backup_devices) > 1) or
                (file_type == FileType.video and len(self.video_backup_devices) > 1))

    def get_download_backup_device_overlap(self,
               photo_download_folder: str,
               video_download_folder: str) -> DefaultDict[int, Set[FileType]]:
        """
        Determine if the photo/video download locations and the backup locations
        are going to the same partitions.

        :param photo_download_folder: where photos are downloaded
        :param video_download_folder: where videos are downloaded
        :return: partitions that are downloaded and backed up to,
         referred to by os.stat.st_dev
        """

        try:
            photo_device = os.stat(photo_download_folder).st_dev
        except FileNotFoundError:
            photo_device = 0
        try:
            video_device = os.stat(video_download_folder).st_dev
        except:
            video_device = 0

        downloading_to = defaultdict(set)  # type: DefaultDict[int, Set[FileType]]

        if photo_device != video_device:
            download_dests = (photo_device, video_device)
        else:
            download_dests = (photo_device, )

        for path in self.devices:
            try:
                backup_device = os.stat(path).st_dev
            except:
                backup_device = 0
            if backup_device != 0:
                d = self.devices[path]
                backup_type = d.backup_type
                for download_device  in download_dests:
                    if backup_device == download_device:
                        if backup_type in (BackupLocationType.photos,
                                           BackupLocationType.photos_and_videos):
                            downloading_to[backup_device].add(FileType.photo)
                        if backup_type in (BackupLocationType.videos,
                                           BackupLocationType.photos_and_videos):
                            downloading_to[backup_device].add(FileType.video)
        return downloading_to

    def get_manual_mounts(self) -> Optional[Tuple[BackupVolumeDetails, ...]]:
        """
        Get QStorageInfo, display name, and path for each backup
        destination for manually specified backup destinations.

        Display name is the path basename.

        Lists photo backup destination before video backup destination.

        Exceptions are not caught, however invalid destinations are accounted
        for.

        :return: Tuple of one or two Tuples containing QStorageInfo, display name,
         and path. If no valid backup destinations are found, returns None.
        """

        assert len(self.devices)

        paths = tuple(self.devices.keys())

        if len(paths) == 1:
            if not os.path.isdir(paths[0]):
                return None
            same_path = True
            path = paths[0]
            backup_type = BackupLocationType.photos_and_videos
        else:
            assert len(paths) == 2
            photo_path = tuple(self.photo_backup_devices)[0]
            video_path = tuple(self.video_backup_devices)[0]

            photo_path_valid = os.path.isdir(photo_path)
            video_path_valid = os.path.isdir(video_path)

            if photo_path_valid and video_path_valid:
                same_path = False
            elif photo_path_valid:
                same_path = True
                path = photo_path
                backup_type = BackupLocationType.photos
            elif video_path_valid:
                same_path = True
                path = video_path
                backup_type = BackupLocationType.videos
            else:
                return None

        if same_path:
            name = self.name(path, shorten=True)
            mount = QStorageInfo(path)
            os_stat_device = os.stat(path).st_dev
            return (BackupVolumeDetails(mount, name, path, backup_type, os_stat_device), )
        else:
            photo_name = self.name(photo_path, shorten=True)
            video_name = self.name(video_path, shorten=True)
            photo_mount = QStorageInfo(photo_path)
            photo_os_stat_device = os.stat(photo_path).st_dev

            if same_device(photo_path, video_path):
                # Translators: two folder names, separated by a plus sign
                names = _('%s + %s') % (photo_name, video_name)
                paths = '%s\n%s' % (photo_path, video_path)
                return (BackupVolumeDetails(photo_mount, names, paths,
                                            BackupLocationType.photos_and_videos,
                                            photo_os_stat_device),)
            else:
                video_mount = QStorageInfo(video_path)
                video_os_stat_device = os.stat(video_path).st_dev
                return (BackupVolumeDetails(photo_mount, photo_name, photo_path,
                                            BackupLocationType.photos,
                                            photo_os_stat_device),
                        BackupVolumeDetails(video_mount, video_name, video_path,
                                            BackupLocationType.videos,
                                            video_os_stat_device))

    def get_backup_volume_details(self, path: str) -> BackupVolumeDetails:
        """
        For now only used in case of external mounts i.e. not auto-detected.

        :param path: backup path
        :return: named tuple of details of the backup volume
        """

        name = self.name(path, shorten=True)
        device = self.devices[path]
        if device.mount is not None:
            mount = device.mount
        else:
            mount = QStorageInfo(path)
        backup_type = device.backup_type
        os_stat_device = os.stat(path).st_dev
        return BackupVolumeDetails(mount, name, path, backup_type, os_stat_device)

    def backup_possible(self, file_type: FileType) -> bool:
        """

        :param file_type: whether the file is a photo or video
        :return: True if more a backup device is being used for
        the file type
        """
        if file_type == FileType.photo:
            return len(self.photo_backup_devices) > 0
        elif file_type == FileType.video:
            return len(self.video_backup_devices) > 0
        else:
            logging.critical("Unrecognized file type when determining if backup is possible")

    def _add_identifier(self, path: Optional[str], file_type: FileType) -> Optional[str]:
        if path is None:
            return None
        if file_type == FileType.photo:
            return os.path.join(path, self.rapidApp.prefs.photo_backup_identifier)
        else:
            return os.path.join(path, self.rapidApp.prefs.video_backup_identifier)

    def sample_device_paths(self) -> List[str]:
        """
        Return a sample of up to three paths on detected backup devices.

        Includes the folder identifier (specified in the user prefs)
        used to identify the backup drive.

        Illustrates backup destinations for each of photo, video, such
        that:
        - If photos are being backed up to a device, show it.
        - If videos are being backed up to a device, show it.
        - If photos and videos are being backed up to the same device,
          show that they are.

        :return: sorted list of the paths
        """

        # Prioritize display of drives that are backing up only one type
        both_types = self.photo_backup_devices & self.video_backup_devices
        photo_only = self.photo_backup_devices - both_types
        video_only = self.video_backup_devices - both_types

        photo0 = nth(iter(photo_only), 0)
        video0 = nth(iter(video_only), 0)
        both0, both1 = tuple(itertools.chain(itertools.islice(both_types, 2),
                                                           itertools.repeat(None, 2)))[:2]

        # Add the identifier specified in the user's prefs
        photo0id, photo1id, photo2id = (self._add_identifier(path, FileType.photo)
                                        for path in (photo0, both0, both1))
        video0id, video1id, video2id = (self._add_identifier(path, FileType.video)
                                        for path in (video0, both0, both1))

        paths = [path for path in (photo0id, video0id, photo1id, video1id, photo2id, video2id)
                 if path is not None][:3]

        if len(paths) < 3:

            unused_photo = self.photo_backup_devices - {path for path in (photo0, both0, both1)
                                                        if path is not None}
            unused_video =  self.video_backup_devices - {path for path in (video0, both0, both1)
                                                         if path is not None}
            photo1, photo2 = tuple(itertools.chain(itertools.islice(unused_photo, 2),
                                                               itertools.repeat(None, 2)))[:2]
            video1, video2 =  tuple(itertools.chain(itertools.islice(unused_video, 2),
                                                               itertools.repeat(None, 2)))[:2]
            photo3id, photo4id = (self._add_identifier(path, FileType.photo)
                                        for path in (photo1, photo2))
            video3id, video4id = (self._add_identifier(path, FileType.video)
                                        for path in (video1, video2))

            paths += [path for path in (photo3id, video3id, photo4id, video4id)
                      if path is not None][:3 - len(paths)]

        return sorted(paths)

    def backup_destinations_missing(self,
                                downloading: DownloadingFileTypes) -> Optional[BackupFailureType]:
        """
        Checks if there are backup destinations matching the files
        going to be downloaded
        :param downloading: the types of file that will be downloaded
        :return: None if no problems, or BackupFailureType
        """
        prefs = self.rapidApp.prefs
        if prefs.backup_files:
            photos = downloading in (DownloadingFileTypes.photos,
                                     DownloadingFileTypes.photos_and_videos)
            videos = downloading in (DownloadingFileTypes.videos,
                                     DownloadingFileTypes.photos_and_videos)

            if prefs.backup_device_autodetection:
                photo_backup_problem = photos and not self.backup_possible(FileType.photo)
                video_backup_problem = videos and not self.backup_possible(FileType.video)
            else:
                photo_backup_problem = photos and not validate_download_folder(
                    path=prefs.backup_photo_location,
                    write_on_waccesss_failure=True
                ).valid
                video_backup_problem = videos and not validate_download_folder(
                    path=prefs.backup_video_location,
                    write_on_waccesss_failure=True
                ).valid

            if photo_backup_problem:
                if video_backup_problem:
                    return BackupFailureType.photos_and_videos
                else:
                    return BackupFailureType.photos
            elif video_backup_problem:
                return BackupFailureType.videos
            else:
                return None
        return None


class FSMetadataErrors:
    """
    When downloading and backing up, filesystem metadata needs to be copied.
    Sometimes it's not possible. Track which devices (computer devices,
    according to the OS, that is, not the same as above) have problems.
    """

    def __init__(self) -> None:
        # A 'device' in this class is the st_dev value returned by os.stat
        self.devices = set()  # type: Set[int]
        self.archived_devices = set()  # type: Set[int]
        # device: FsMetadataWriteProblem
        self.metadata_errors = dict()  # type: Dict[int, FsMetadataWriteProblem]
        # scan_id / device_id: Set[device]
        self.worker_id_devices = defaultdict(set)  # type: DefaultDict[int, Set[int]]

    def add_problem(self, worker_id: int,
                    path: str,
                    mdata_exceptions: Tuple[Exception]) -> None:

        dev = os.stat(path).st_dev

        if dev not in self.devices:
            self.devices.add(dev)

            name, uri, root_path, fstype = fs_device_details(path)

            problem = FsMetadataWriteProblem(
                name=name, uri=uri, mdata_exceptions=mdata_exceptions
            )

            self.metadata_errors[dev] = problem

            if worker_id is not None:
                self.worker_id_devices[worker_id].add(dev)

    def problems(self, worker_id: int) -> List[FsMetadataWriteProblem]:
        problems = []
        for dev in self.worker_id_devices[worker_id]:
            if dev not in self.archived_devices:
                problems.append(self.metadata_errors[dev])
                self.archived_devices.add(dev)
        return problems
