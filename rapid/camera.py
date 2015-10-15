#!/usr/bin/python3
__author__ = 'Damon Lynch'

# Copyright (C) 2015 Damon Lynch <damonlynch@gmail.com>
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

import logging
import os
import io
from collections import namedtuple

from PyQt5.QtGui import QImage

import gphoto2 as gp


logging.basicConfig(format='%(levelname)s:%(asctime)s:%(message)s',
                    datefmt='%H:%M:%S',
                    level=logging.DEBUG)

def python_gphoto2_version():
    return  gp.__version__

def gphoto2_version():
    return gp.gp_library_version(0)[0]

CopyChunks = namedtuple('CopyChunks', 'copy_succeeded, src_bytes')

class Camera:
    def __init__(self, model: str, port:str):
        """

        :param model: camera model, as returned by camera_autodetect()
        :param port: camera port, as returned by camera_autodetect()
        :return:
        """
        self.model = model
        self.port = port

        self.context = gp.Context()
        self._select_camera(model, port)

        self.dcim_folders = None # type: List[str]
        self.camera_initialized = False
        try:
            self.camera.init(self.context)
            self.camera_initialized = True
        except gp.GPhoto2Error as e:
            if e.code == gp.GP_ERROR_IO_USB_CLAIM:
                logging.error("{} is already mounted".format(model))
                return
            elif e.code == gp.GP_ERROR:
                logging.error("An error occurred initializing the "
                              "camera using libgphoto2")
            else:
                logging.error("Unable to access camera: error %s",
                              e.code)
            return

        self.dcim_folders = self._locate_DCIM_folders('/')
        self.folders_and_files = []
        self.audio_files = {}
        self.video_thumbnails = []
        abilities = self.camera.get_abilities()

        self.can_fetch_thumbnails = abilities.file_operations & \
                   gp.GP_FILE_OPERATION_PREVIEW != 0

    def camera_has_dcim(self) -> bool:
        """
        Check whether the camera has been initialized and if a DCIM folder
        has been located

        :return: True if the camera is initialized and a DCIM folder has
                 been located
        """
        if self.camera_initialized:
            if self.dcim_folders is not None:
                return True
        return False

    def get_file_info(self, folder, file_name) -> tuple:
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
        return (modification_time, size)


    def _get_file(self, dir_name: str, file_name: str,
                  dest_full_filename:str=None,
                  file_type:int=gp.GP_FILE_TYPE_NORMAL):

        camera_file = None
        succeeded = False
        try:
            camera_file = gp.check_result(gp.gp_camera_file_get(
                         self.camera, dir_name, file_name,
                         file_type, self.context))
            succeeded = True
        except gp.GPhoto2Error as ex:
            logging.error('Error reading %s from camera. Code: %s',
                          os.path.join(dir_name, file_name), ex.code)

        if succeeded and dest_full_filename is not None:
            try:
                gp.check_result(gp.gp_file_save(camera_file,
                                              dest_full_filename))
            except gp.GPhoto2Error as ex:
                logging.error('Error saving %s from camera. Code: %s',
                          os.path.join(dir_name, file_name), ex.code)
                succeeded = False

        return (succeeded, camera_file)

    def save_file(self, dir_name: str, file_name: str,
                  dest_full_filename: str) -> bool:
        """
        Save the file from the camera to a local destination

        :param dir_name: directory on the camera
        :param file_name: the photo or video
        :param dest_full_filename: full path including filename where
        the file will be saved.
        :return: True if the file was successfully saved, else False
        """

        succeeded, camera_file = self._get_file(dir_name, file_name,
                                        dest_full_filename)
        return succeeded

    def save_file_by_chunks(self, dir_name: str, file_name: str, size: int,
                  dest_full_filename: str,
                  progress_callback,
                  check_for_command,
                  return_file_bytes = False,
                  chunk_size=1048576) -> CopyChunks:
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
        copy_succeeded = True
        src_bytes = None
        view = memoryview(bytearray(size))
        amount_downloaded = 0
        for offset in range(0, size, chunk_size):
            check_for_command()
            stop = min(offset + chunk_size, size)
            try:
                bytes_read = gp.check_result(self.camera.file_read(
                    dir_name, file_name, gp.GP_FILE_TYPE_NORMAL,
                    offset, view[offset:stop], self.context))
                amount_downloaded += bytes_read
                if progress_callback is not None:
                    progress_callback(amount_downloaded, size)
            except gp.GPhoto2Error as ex:
                logging.error('Error copying file %s from camera %s. Code '
                              '%s', os.path.join(dir_name, file_name),
                              self.camera.model, ex.code)
                copy_succeeded = False
                break
        if copy_succeeded:
            dest_file = None
            try:
                dest_file = io.open(dest_full_filename, 'wb')
                src_bytes = view.tobytes()
                dest_file.write(src_bytes)
                dest_file.close()
            except OSError as ex:
                logging.error('Error saving file %s from camera %s. Code '
                              '%s', os.path.join(dir_name, file_name),
                              self.camera.model, ex.code)
                if dest_file is not None:
                    dest_file.close()
                copy_succeeded = False
        if return_file_bytes:
            return CopyChunks(copy_succeeded, src_bytes)
        else:
            return CopyChunks(copy_succeeded, None)


    def get_thumbnail(self, dir_name: str, file_name: str,
                      ignore_embedded_thumbnail=False,
                      cache_full_filename:str=None) -> \
                      QImage:
        """

        :param dir_name: directory on the camera
        :param file_name: the photo or video
        :param ignore_embedded_thumbnail: if True, do not retrieve the
        embedded thumbnail
        :param cache_full_filename: full path including filename where the
        thumbnail will be saved. If none, will not save it.
        :return: QImage of the thumbnail, which will be full resolution
        if the embedded thumbnail is not selected
        """
        if self.can_fetch_thumbnails and not ignore_embedded_thumbnail:
            get_file_type = gp.GP_FILE_TYPE_PREVIEW
        else:
            get_file_type = gp.GP_FILE_TYPE_NORMAL

        succeeded, camera_file = self._get_file(dir_name, file_name,
                                      cache_full_filename, get_file_type)

        if succeeded:
            thumbnail_data = None
            try:
                thumbnail_data = gp.check_result(gp.gp_file_get_data_and_size(
                    camera_file))
            except gp.GPhoto2Error as ex:
                logging.error('Error getting image %s from camera. Code: '
                              '%s',
                          os.path.join(dir_name, file_name), ex.code)
            if thumbnail_data:
                data = memoryview(thumbnail_data)
                image = QImage.fromData(data.tobytes())
                return image
            else:
                return None
        else:
            return None

    def get_THM_file(self, full_THM_name) -> QImage:
        dir_name, file_name = os.path.split(full_THM_name)
        succeeded, camera_file = self._get_file(dir_name, file_name)
        if succeeded:
            thumbnail_data = None
            try:
                thumbnail_data = gp.check_result(gp.gp_file_get_data_and_size(
                    camera_file))
            except gp.GPhoto2Error as ex:
                logging.error('Error getting THM file %s from camera. Code: '
                              '%s',
                              os.path.join(dir_name, file_name), ex.code)

            if thumbnail_data:
                data = memoryview(thumbnail_data)
                image = QImage.fromData(data.tobytes())
                return image
            else:
                return None
        else:
            return None


    def _locate_DCIM_folders(self, path: str):
        """
        Scan camera looking for a DCIM folder in either the root of the
        path passed, or in one of the root folders subfolders (it does
        not scan subfolders of those subfolders). Returns all instances
        of a DCIM folder, which is helpful for cameras that have more
        than one card memory card slot.

        :param path: the root folder to start scanning in
        :type path: str
        :return: the paths including the DCIM folders (if found), or None
        :rtype: List[str]
        """

        dcim_folders = [] # type: List[str]
        # turn list of two items into a dictionary, for easier access
        folders = dict(self.camera.folder_list_folders(path, self.context))
        if 'DCIM' in folders:
            return os.path.join(path, 'DCIM')
        else:
            for subfolder in folders:
                subpath = os.path.join(path, subfolder)
                subfolders = dict(self.camera.folder_list_folders(subpath,
                                                              self.context))
                if 'DCIM' in subfolders:
                    dcim_folders.append(os.path.join(subpath, 'DCIM'))
        if not dcim_folders:
            return None
        else:
            return dcim_folders

    def _select_camera(self, model, port_name):
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

    def free_camera(self):
        """
        Disconnects the camera gphoto2
        """
        if self.camera_initialized:
            self.camera.exit(self.context)
            self.camera_initialized = False


if __name__ == "__main__":

    #Test stub
    gp_context = gp.Context()
    # Assume gphoto2 version 2.5 or greater
    cameras = gp_context.camera_autodetect()
    for name, value in cameras:
        camera = name
        port = value
        # print(port)
        c = Camera(model=camera, port=port)
        print(c.dcim_folders)

        dir = '/store_00010001/DCIM/100EOS1D'
        photo = '_K0V4925.CR2'

        info = c.camera.file_get_info(dir, photo, c.context)
        # finfo = gp.gp_camera_file_get_info(c.camera, dir, photo ,c.context)

        c.free_camera()




