#!/usr/bin/env python3

# Copyright (C) 2015-2019 Damon Lynch <damonlynch@gmail.com>
# Copyright (C) 2012-2015 Jim Easterbrook <jim@jim-easterbrook.me.uk>

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

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2015-2019, Damon Lynch. Copyright 2012-2015 Jim Easterbrook."

import logging
import os
import io
from collections import namedtuple
import re
from typing import Optional, List, Tuple

import gphoto2 as gp
from raphodo.storage import StorageSpace
from raphodo.constants import CameraErrorCode
from raphodo.utilities import format_size_for_user


def python_gphoto2_version():
    return  gp.__version__

def gphoto2_version():
    return gp.gp_library_version(0)[0]


# convert error codes to error names
gphoto2_error_codes = {
    code: name for code, name in (
        ((getattr(gp, attr), attr) for attr in dir(gp) if attr.startswith('GP_ERROR'))
    )
}


def gphoto2_named_error(code: int) -> str:
    return gphoto2_error_codes.get(code, 'Unknown gphoto2 error')


class CameraError(Exception):
    def __init__(self, code: CameraErrorCode) -> None:
        self.code = code

    def __repr__(self) -> str:
        if self.code == CameraErrorCode.inaccessible:
            return "inaccessible"
        else:
            return "locked"

    def __str__(self) -> str:
        if self.code == CameraErrorCode.inaccessible:
            return "The camera is inaccessible"
        else:
            return "The camera is locked"


class CameraProblemEx(CameraError):
    def __init__(self, code: CameraErrorCode,
                 gp_exception: Optional[gp.GPhoto2Error]=None,
                 py_exception: Optional[Exception]=None) -> None:
        super().__init__(code)
        if gp_exception is not None:
            self.gp_code = gp_exception.code
        else:
            self.gp_code = None
        self.py_exception = py_exception

    def __repr__(self) -> str:
        if self.code == CameraErrorCode.read:
            return "read error"
        elif self.code == CameraErrorCode.write:
            return 'write error'
        else:
            return repr(super())

    def __str__(self) -> str:
        if self.code == CameraErrorCode.read:
            return "Could not read file from camera"
        elif self.code == CameraErrorCode.write:
            return 'Could not write file from camera'
        else:
            return str(super())


def generate_devname(camera_port: str) -> Optional[str]:
    """
     Generate udev DEVNAME.

     >>> generate_devname('usb:001,003')
     '/dev/bus/usb/001/003'

     >>> generate_devname('usb::001,003')

    :param camera_port:
    :return: devname if it could be generated, else None
    """

    match = re.match('usb:([0-9]+),([0-9]+)', camera_port)
    if match is not None:
        p1, p2 = match.groups()
        return '/dev/bus/usb/{}/{}'.format(p1, p2)
    return None


class Camera:

    """Access a camera via libgphoto2."""

    def __init__(self, model: str,
                 port:str,
                 get_folders: bool=True,
                 raise_errors: bool=False,
                 context: gp.Context=None,
                 specific_folders: Optional[List[str]]=None) -> None:
        """
        Initialize a camera via libgphoto2.

        :param model: camera model, as returned by camera_autodetect()
        :param port: camera port, as returned by camera_autodetect()
        :param get_folders: whether to detect the DCIM folders on the
         camera
        :param raise_errors: if True, if necessary free camera,
         and raise error that occurs during initialization
        :param specific_folders: folders such as DCIM,  PRIVATE,
         and MP_ROOT that are searched for if get_folders is True.
         If None, the root level folders are returned -- one for each
         storage slot.
        """

        self.model = model
        self.port = port
        # class method _concise_model_name discusses why a display name is
        # needed
        self.display_name = model
        self.camera_config = None

        if context is None:
            self.context = gp.Context()
        else:
            self.context = context

        self._select_camera(model, port)

        self.specific_folders = None # type: List[str]
        self.specific_folder_located = False
        self._dual_slots_active = False

        self.storage_info = []

        self.camera_initialized = False
        try:
            self.camera.init(self.context)
            self.camera_initialized = True
        except gp.GPhoto2Error as e:
            if e.code == gp.GP_ERROR_IO_USB_CLAIM:
                error_code = CameraErrorCode.inaccessible
                logging.error("{} is already mounted".format(model))
            elif e.code == gp.GP_ERROR:
                logging.error("An error occurred initializing the camera using libgphoto2")
                error_code = CameraErrorCode.inaccessible
            else:
                logging.error("Unable to access camera: %s", gphoto2_named_error(e.code))
                error_code = CameraErrorCode.locked
            if raise_errors:
                raise CameraProblemEx(error_code, gp_exception=e)
            return

        concise_model_name = self._concise_model_name()
        if concise_model_name:
            self.display_name = concise_model_name

        if get_folders:
            try:
                self.specific_folders = self._locate_specific_folders(
                    path='/', specific_folders=specific_folders
                )
                self.specific_folder_located = len(self.specific_folders) > 0
            except gp.GPhoto2Error as e:
                logging.error(
                    "Unable to access camera %s: %s. Is it locked?",
                    self.display_name, gphoto2_named_error(e.code)
                )
                if raise_errors:
                    self.free_camera()
                    raise CameraProblemEx(CameraErrorCode.locked, gp_exception=e)

        self.folders_and_files = []
        self.audio_files = {}
        self.video_thumbnails = []
        abilities = self.camera.get_abilities()
        self.can_fetch_thumbnails = abilities.file_operations & gp.GP_FILE_OPERATION_PREVIEW != 0

    def camera_has_dcim_like_folder(self) -> bool:
        """
        Check whether the camera has been initialized and if a DCIM or other specific folder
        has been located

        :return: True if the camera is initialized and a DCIM or other specific folder has
                 been located
        """
        return self.camera_initialized and self.specific_folder_located

    def _locate_specific_folders(self,
                     path: str,
                     specific_folders: Optional[List[str]]) -> List[Optional[List[str]]]:
        """
        Scan camera looking for folders such as DCIM,  PRIVATE, and MP_ROOT.

        Looks in either the root of the path passed, or in one of the root
        folders subfolders (it does not scan subfolders of those subfolders).

        Returns all instances of the specific folders, which is helpful for
        cameras that have more than one storage (memory card / internal memory)
        slot.

        No error checking: exceptions must be caught by the caller

        :param path: the root folder to start scanning in
        :param specific_folders: the subfolders to look for. If None, return the
         root of each storage device
        :return: the paths including the specific folders (if found), or empty list
        """

        # turn list of two items into a dictionary, for easier access
        # no error checking as exceptions are caught by the caller
        folders = dict(self.camera.folder_list_folders(path, self.context))

        if specific_folders is None:
            found_folders = [[path + folder] for folder in folders]
        else:
            found_folders = []

            # look for the folders one level down from the root folder
            # it is at this level that specific folders like DCIM will be found
            for subfolder in folders:
                subpath = os.path.join(path, subfolder)
                subfolders = dict(self.camera.folder_list_folders(subpath, self.context))
                ff = [
                    os.path.join(subpath, folder) for folder in specific_folders
                    if folder in subfolders
                ]
                if ff:
                    found_folders.append(ff)

        self._dual_slots_active = len(found_folders) > 1

        return found_folders

    def get_file_info(self, folder, file_name) -> Tuple[int, int]:
        """
        Returns modification time and file size

        :type folder: str
        :type file_name: str
        :param folder: full path where file is located
        :param file_name:
        :return: tuple of modification time and file size
        """
        info = self.camera.file_get_info(folder, file_name, self.context)
        modification_time = info.file.mtime
        size = info.file.size
        return modification_time, size

    def get_exif_extract(self, folder: str,
                         file_name: str,
                         size_in_bytes: int=200) -> bytearray:
        """"
        Attempt to read only the exif portion of the file.

        Assumes exif is located at the beginning of the file.
        Use the result like this:
        metadata = GExiv2.Metadata()
        metadata.open_buf(buf)

        :param folder: directory on the camera the file is stored
        :param file_name: the photo's file name
        :param size_in_bytes: how much of the photo to read, starting
         from the front of the file
        """

        buffer = bytearray(size_in_bytes)
        try:
            self.camera.file_read(
                folder, file_name, gp.GP_FILE_TYPE_NORMAL, 0, buffer, self.context
            )
        except gp.GPhoto2Error as e:
            logging.error(
                "Unable to extract portion of file from camera %s: %s",
                self.display_name, gphoto2_named_error(e.code)
            )
            raise CameraProblemEx(code=CameraErrorCode.read, gp_exception=e)
        else:
            return buffer

    def get_exif_extract_from_jpeg(self, folder: str, file_name: str) -> bytearray:
        """
        Extract strictly the app1 (exif) section of a jpeg.

        Uses libgphoto2 to extract the exif header.

        Assumes jpeg on camera is straight from the camera, i.e. not
        modified by an exif altering program off the camera.

        :param folder: directory on the camera where the jpeg is stored
        :param file_name: name of the jpeg
        :return: first section of jpeg such that it can be read by
         exiv2 or similar

        """

        camera_file = self._get_file(folder, file_name, None, gp.GP_FILE_TYPE_EXIF)

        try:
            exif_data = gp.check_result(gp.gp_file_get_data_and_size(camera_file))
        except gp.GPhoto2Error as ex:
            logging.error(
                'Error getting exif info for %s from camera %s: %s',
                os.path.join(folder, file_name), self.display_name, gphoto2_named_error(ex.code)
            )
            raise CameraProblemEx(code=CameraErrorCode.read, gp_exception=ex)
        return bytearray(exif_data)

    def get_exif_extract_from_jpeg_manual_parse(self, folder: str,
                                            file_name: str) -> Optional[bytes]:
        """
        Extract exif section of a jpeg.

        I wrote this before I understood that libpghoto2 provides the
        same functionality!

        Reads first few bytes of jpeg on camera to determine the
        location and length of the exif header, then reads in the
        header.

        Assumes jpeg on camera is straight from the camera, i.e. not
        modified by an exif altering program off the camera.

        :param folder: directory on the camera where the jpeg is stored
        :param file_name: name of the jpeg
        :return: first section of jpeg such that it can be read by
         exiv2 or similar

        """

        # Step 1: determine the location of APP1 in the jpeg file
        # See http://dev.exiv2.org/projects/exiv2/wiki/The_Metadata_in_JPEG_files

        soi_marker_length = 2
        marker_length = 2
        exif_header_length = 8
        read0_size = soi_marker_length + marker_length + exif_header_length

        view = memoryview(bytearray(read0_size))
        try:
            bytes_read = gp.check_result(self.camera.file_read(
                folder, file_name, gp.GP_FILE_TYPE_NORMAL,
                0, view, self.context))
        except gp.GPhoto2Error as ex:
            logging.error(
                'Error reading %s from camera: %s',
                os.path.join(folder, file_name), gphoto2_named_error(ex.code)
            )
            return None

        jpeg_header = view.tobytes()
        view.release()

        if jpeg_header[0:2] != b'\xff\xd8':
            logging.error("%s not a jpeg image: no SOI marker", file_name)
            return None

        app_marker = jpeg_header[2:4]

        # Step 2: handle presence of APP0 - it's optional
        if app_marker == b'\xff\xe0':
            # There is an APP0 before the probable APP1
            # Don't neeed the content of the APP0
            app0_data_length = jpeg_header[4] * 256 + jpeg_header[5]
            # We've already read twelve bytes total, going into the APP1 data.
            # Now we want to download the rest of the APP1, along with the app0 marker
            # and the app0 exif header
            read1_size = app0_data_length + 2
            app0_view = memoryview(bytearray(read1_size))
            try:
                bytes_read = gp.check_result(self.camera.file_read(
                    folder, file_name, gp.GP_FILE_TYPE_NORMAL,
                    read0_size, app0_view, self.context))
            except gp.GPhoto2Error as ex:
                logging.error(
                    'Error reading %s from camera: %s',
                    os.path.join(folder, file_name), gphoto2_named_error(ex.code)
                )
            app0 = app0_view.tobytes()
            app0_view.release()
            app_marker = app0[(exif_header_length + 2) * -1:exif_header_length * -1]
            exif_header = app0[exif_header_length * -1:]
            jpeg_header = jpeg_header + app0
            offset = read0_size + read1_size
        else:
            exif_header = jpeg_header[exif_header_length * -1:]
            offset = read0_size

        # Step 3: process exif header
        if app_marker != b'\xff\xe1':
            logging.error("Could not locate APP1 marker in %s", file_name)
            return None
        if exif_header[2:6] != b'Exif' or exif_header[6:8] != b'\x00\x00':
            logging.error("APP1 is malformed in %s", file_name)
            return None
        app1_data_length = exif_header[0] * 256 + exif_header[1]

        # Step 4: read APP1
        view = memoryview(bytearray(app1_data_length))
        try:
            bytes_read = gp.check_result(
                self.camera.file_read(
                    folder, file_name, gp.GP_FILE_TYPE_NORMAL, offset, view, self.context
                )
            )
        except gp.GPhoto2Error as ex:
            logging.error(
                'Error reading %s from camera: %s',
                os.path.join(folder, file_name), gphoto2_named_error(ex.code)
            )
            return None
        return jpeg_header + view.tobytes()

    def _get_file(self, dir_name: str,
                  file_name: str,
                  dest_full_filename: Optional[str]=None,
                  file_type: int=gp.GP_FILE_TYPE_NORMAL) -> gp.CameraFile:

        try:
            camera_file = gp.check_result(
                gp.gp_camera_file_get(self.camera, dir_name, file_name, file_type, self.context)
            )
        except gp.GPhoto2Error as ex:
            logging.error(
                'Error reading %s from camera %s: %s',
                os.path.join(dir_name, file_name), self.display_name, gphoto2_named_error(ex.code)
            )
            raise CameraProblemEx(code=CameraErrorCode.read, gp_exception=ex)

        if dest_full_filename is not None:
            try:
                gp.check_result(gp.gp_file_save(camera_file, dest_full_filename))
            except gp.GPhoto2Error as ex:
                logging.error(
                    'Error saving %s from camera %s: %s',
                    os.path.join(dir_name, file_name), self.display_name,
                    gphoto2_named_error(ex.code)
                )
                raise CameraProblemEx(code=CameraErrorCode.write, gp_exception=ex)

        return camera_file

    def save_file(self, dir_name: str,
                  file_name: str,
                  dest_full_filename: str) -> None:
        """
        Save the file from the camera to a local destination.

        :param dir_name: directory on the camera
        :param file_name: the photo or video
        :param dest_full_filename: full path including filename where
        the file will be saved.
        """

        self._get_file(dir_name, file_name, dest_full_filename)

    def save_file_chunk(self, dir_name: str,
                        file_name: str,
                        chunk_size_in_bytes: int,
                        dest_full_filename: str,
                        mtime: int=None) -> None:
        """
        Save the file from the camera to a local destination.

        :param dir_name: directory on the camera
        :param file_name: the photo or video
        :param chunk_size_in_bytes: how much of the file to read, starting
         from the front of the file
        :param dest_full_filename: full path including filename where
        the file will be saved.
        :param mtime: if specified, set the file modification time to this value
        """

        # get_exif_extract() can raise CameraProblemEx(code=CameraErrorCode.read):
        buffer = self.get_exif_extract(dir_name, file_name, chunk_size_in_bytes)

        view = memoryview(buffer)
        dest_file = None
        try:
            dest_file = io.open(dest_full_filename, 'wb')
            src_bytes = view.tobytes()
            dest_file.write(src_bytes)
            dest_file.close()
            if mtime is not None:
                os.utime(dest_full_filename, times=(mtime, mtime))
        except (OSError, PermissionError) as ex:
            logging.error(
                'Error saving file %s from camera %s: %s',
                os.path.join(dir_name, file_name), self.display_name, gphoto2_named_error(ex.errno)
            )
            if dest_file is not None:
                dest_file.close()
            raise CameraProblemEx(code=CameraErrorCode.write, py_exception=ex)

    def save_file_by_chunks(self, dir_name: str,
                            file_name: str,
                            size: int,
                            dest_full_filename: str,
                            progress_callback,
                            check_for_command,
                            return_file_bytes = False,
                            chunk_size=1048576) -> Optional[bytes]:
        """
        :param dir_name: directory on the camera
        :param file_name: the photo or video
        :param size: the size of the file in bytes
        :param dest_full_filename: full path including filename where
         the file will be saved
        :param progress_callback: a function with which to update
         copy progress
        :param check_for_command: a function with which to check to see
         if the execution should pause, resume or stop
        :param return_file_bytes: if True, return a copy of the file's
         bytes, else make that part of the return value None
        :param chunk_size: the size of the chunks to copy. The default
         is 1MB.
        :return: True if the file was successfully saved, else False,
         and the bytes that were copied
        """

        src_bytes = None
        view = memoryview(bytearray(size))
        amount_downloaded = 0
        for offset in range(0, size, chunk_size):
            check_for_command()
            stop = min(offset + chunk_size, size)
            try:
                bytes_read = gp.check_result(
                    self.camera.file_read(
                        dir_name, file_name, gp.GP_FILE_TYPE_NORMAL, offset, view[offset:stop],
                        self.context
                    )
                )
                amount_downloaded += bytes_read
                if progress_callback is not None:
                    progress_callback(amount_downloaded, size)
            except gp.GPhoto2Error as ex:
                logging.error(
                    'Error copying file %s from camera %s: %s',
                    os.path.join(dir_name, file_name), self.display_name,
                    gphoto2_named_error(ex.code)
                )
                if progress_callback is not None:
                    progress_callback(size, size)
                raise CameraProblemEx(code=CameraErrorCode.read, gp_exception=ex)

        dest_file = None
        try:
            dest_file = io.open(dest_full_filename, 'wb')
            src_bytes = view.tobytes()
            dest_file.write(src_bytes)
            dest_file.close()
        except (OSError, PermissionError) as ex:
            logging.error(
                'Error saving file %s from camera %s. Error %s: %s',
                os.path.join(dir_name, file_name), self.display_name, ex.errno, ex.strerror
            )
            if dest_file is not None:
                dest_file.close()
            raise CameraProblemEx(code=CameraErrorCode.write, py_exception=ex)

        if return_file_bytes:
            return src_bytes

    def get_thumbnail(self, dir_name: str,
                      file_name: str,
                      ignore_embedded_thumbnail=False,
                      cache_full_filename: Optional[str]=None) -> Optional[bytes]:
        """
        :param dir_name: directory on the camera
        :param file_name: the photo or video
        :param ignore_embedded_thumbnail: if True, do not retrieve the
        embedded thumbnail
        :param cache_full_filename: full path including filename where the
        thumbnail will be saved. If none, will not save it.
        :return: thumbnail in bytes format, which will be full
        resolution if the embedded thumbnail is not selected
        """

        if self.can_fetch_thumbnails and not ignore_embedded_thumbnail:
            get_file_type = gp.GP_FILE_TYPE_PREVIEW
        else:
            get_file_type = gp.GP_FILE_TYPE_NORMAL

        camera_file = self._get_file(
            dir_name, file_name, cache_full_filename, get_file_type
        )

        try:
            thumbnail_data = gp.check_result(gp.gp_file_get_data_and_size(camera_file))
        except gp.GPhoto2Error as ex:
            logging.error(
                'Error getting image %s from camera %s: %s',
                os.path.join(dir_name, file_name), self.display_name,
                gphoto2_named_error(ex.code)
            )
            raise CameraProblemEx(code=CameraErrorCode.read, gp_exception=ex)

        if thumbnail_data:
            data = memoryview(thumbnail_data)
            return data.tobytes()

    def get_THM_file(self, full_THM_name: str) -> Optional[bytes]:
        """
        Get THM thumbnail from camera

        :param full_THM_name: path and file name of the THM file
        :return: THM in raw bytes
        """
        dir_name, file_name = os.path.split(full_THM_name)
        camera_file = self._get_file(dir_name, file_name)
        try:
            thumbnail_data = gp.check_result(gp.gp_file_get_data_and_size(camera_file))
        except gp.GPhoto2Error as ex:
            logging.error(
                'Error getting THM file %s from camera %s: %s',
                 os.path.join(dir_name, file_name), self.display_name, gphoto2_named_error(ex.code)
            )
            raise CameraProblemEx(code=CameraErrorCode.read, gp_exception=ex)

        if thumbnail_data:
            data = memoryview(thumbnail_data)
            return data.tobytes()

    def _select_camera(self, model, port_name)  -> None:
        # Code from Jim Easterbrook's Photoini
        # initialise camera
        self.camera = gp.Camera()
        # search abilities for camera model
        abilities_list = gp.CameraAbilitiesList()
        abilities_list.load(self.context)
        idx = abilities_list.lookup_model(str(model))
        self.camera.set_abilities(abilities_list[idx])
        # search ports for camera port name
        port_info_list = gp.PortInfoList()
        port_info_list.load()
        idx = port_info_list.lookup_path(str(port_name))
        self.camera.set_port_info(port_info_list[idx])

    def free_camera(self) -> None:
        """
        Disconnects the camera in gphoto2.
        """
        if self.camera_initialized:
            self.camera.exit(self.context)
            self.camera_initialized = False

    def _concise_model_name(self) -> str:
        """
        Workaround the fact that the standard model name generated by
        gphoto2 can be extremely verbose, e.g.
        "Google Inc (for LG Electronics/Samsung) Nexus 4/5/7/10 (MTP)",
        which is what is generated for a Nexus 4!!
        :return: the model name as detected by gphoto2's camera
         information, e.g. in the case above, a Nexus 4. Empty string
         if not found.
        """
        if self.camera_config is None:
            try:
                self.camera_config = self.camera.get_config(self.context)
            except gp.GPhoto2Error as e:
                if e.code == gp.GP_ERROR_NOT_SUPPORTED:
                    logging.error(
                        "Getting camera configuration not supported for %s",
                        self.display_name
                    )
                else:
                    logging.error(
                        "Unknown error getting camera configuration for %s",
                        self.display_name
                    )
                return ''

        # Here we really see the difference between C and python!
        child_count = self.camera_config.count_children()
        for i in range(child_count):
            child1 = self.camera_config.get_child(i)
            child_type = child1.get_type()
            if child1.get_name() == 'status' and child_type == gp.GP_WIDGET_SECTION:
                child1_count = child1.count_children()
                for j in range(child1_count):
                    child2 = child1.get_child(j)
                    if child2.get_name() == 'cameramodel':
                        return child2.get_value()
        return ''

    def get_storage_media_capacity(self, refresh: bool=False) -> List[StorageSpace]:
        """
        Determine the bytes free and bytes total (media capacity)
        :param refresh: if True, get updated instead of cached values
        :return: list of StorageSpace tuple. If could not be
        determined due to an error, return value is None.
        """

        self._get_storage_info(refresh)
        storage_capacity = []
        for media_index in range(len(self.storage_info)):
            info = self.storage_info[media_index]
            if not (info.fields & gp.GP_STORAGEINFO_MAXCAPACITY and
                    info.fields & gp.GP_STORAGEINFO_FREESPACEKBYTES):
                logging.error('Could not locate storage on %s', self.display_name)
            else:
                storage_capacity.append(
                    StorageSpace(
                        bytes_free=info.freekbytes * 1024,
                        bytes_total=info.capacitykbytes * 1024,
                        path=info.basedir
                    )
                )
        return storage_capacity

    def get_storage_descriptions(self, refresh: bool=False) -> List[str]:
        """
        Storage description is used in MTP path names by gvfs and KDE.

        :param refresh: if True, get updated instead of cached values
        :return: the storage description
        """
        self._get_storage_info(refresh)
        descriptions = []
        for media_index in range(len(self.storage_info)):
            info = self.storage_info[media_index]
            if info.fields & gp.GP_STORAGEINFO_DESCRIPTION:
                descriptions.append(info.description)
        return descriptions

    def no_storage_media(self, refresh: bool=False) -> int:
        """
        Return the number of storage media (e.g. memory cards) the
        camera has
        :param refresh: if True, refresh the storage information
        :return: the number of media
        """
        self._get_storage_info(refresh)
        return len(self.storage_info)

    def _get_storage_info(self, refresh: bool):
        """
        Load the gphoto2 storage information
        :param refresh: if True, refresh the storage information, i.e.
         load it
        """
        if not self.storage_info or refresh:
            try:
                self.storage_info = self.camera.get_storageinfo(self.context)
            except gp.GPhoto2Error as e:
                logging.error(
                    "Unable to determine storage info for camera %s: %s",
                    self.display_name, gphoto2_named_error(e.code)
                )
                self.storage_info = []

    @property
    def dual_slots_active(self) -> bool:
        """
        :return: True if the camera has dual storage slots and both have specific
        folders (e.g. DCIM etc.)
        """

        if self.specific_folders is None:
            logging.warning(
                "dual_slots_active() called before camera's folders scanned for %s",
                self.display_name
            )
            return False
        if not self.specific_folder_located:
            logging.warning(
                "dual_slots_active() called when no specific folders found for %s",
                self.display_name
            )
            return False
        return self.no_storage_media() > 1 and self._dual_slots_active

    def unlocked(self) -> bool:
        """
        Smart phones can be in a locked state, such that their
        contents cannot be accessed by gphoto2. Determine if
        the device is unlocked by attempting to locate its
        folders.
        :return: True if unlocked, else False
        """
        try:
            self.camera.folder_list_folders('/', self.context)
        except gp.GPhoto2Error as e:
            logging.error(
                "Unable to access camera %s: %s. Is it locked?",
                self.display_name, gphoto2_named_error(e.code)
            )
            return False
        else:
            return True



def dump_camera_details() -> None:
    import itertools
    context = gp.Context()
    cameras = context.camera_autodetect()
    for model, port in cameras:
        c = Camera(model=model, port=port, context=context)
        if not c.camera_initialized:
            logging.error("Camera %s could not be initialized", model)
        else:
            print()
            print(c.display_name)
            print('=' * len(c.display_name))
            print()
            if not c.specific_folder_located:
                print("Speicifc folder was not located")
            else:
                print(
                    "Specific folders:", ', '.join(
                        itertools.chain.from_iterable(c.specific_folders)
                    )
                )
                print("Can fetch thumbnails:", c.can_fetch_thumbnails)

                sc = c.get_storage_media_capacity()
                if not sc:
                    print("Unable to determine storage media capacity")
                else:
                    title = 'Storage capacity'
                    print('\n{}\n{}'.format(title, '-' * len(title)))
                    for ss in sc:
                        print(
                            '\nPath: {}\nCapacity: {}\nFree {}'.format(
                                ss.path,
                                format_size_for_user(ss.bytes_total),
                                format_size_for_user(ss.bytes_free)
                            )
                        )
                sd = c.get_storage_descriptions()
                if not sd:
                    print("Unable to determine storage descriptions")
                else:
                    title = 'Storage description(s)'
                    print('\n{}\n{}'.format(title, '-' * len(title)))
                    for ss in sd:
                        print('\n{}'.format(ss))

        c.free_camera()


if __name__ == "__main__":

    if False:
        dump_camera_details()

    if True:

        #Test stub
        gp_context = gp.Context()
        # Assume gphoto2 version 2.5 or greater
        cameras = gp_context.camera_autodetect()
        for name, value in cameras:
            camera = name
            port = value
            # print(port)
            c = Camera(model=camera, port=port, specific_folders=['DCIM', 'MISC'])
            # c = Camera(model=camera, port=port)
            print(c.no_storage_media(), c.dual_slots_active, c.specific_folders)

            for name, value in c.camera.folder_list_files('/', c.context):
                print(name, value)

            c.free_camera()




