#!/usr/bin/python3
__author__ = 'Damon Lynch'

# Copyright (C) 2011-2015 Damon Lynch <damonlynch@gmail.com>

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
Scans directory looking for photos and videos, and any associated files
external to the actual photo/video including thumbnail files, XMP files, and
audio files that are linked to a photo.

Returns results using the 0mq pipeline pattern.
"""

import os
import pickle
import logging
from collections import (namedtuple, defaultdict)

import scandir


# Instances of classes ScanArguments and ScanPreferences are passed via pickle
# Thus do not remove these two imports
from interprocess import ScanArguments
from preferences import ScanPreferences
from interprocess import WorkerInPublishPullPipeline
from camera import Camera
import rpdfile

FileInfo = namedtuple('FileInfo', ['path', 'modification_time', 'size',
                                   'ext_lower', 'base_name', 'file_type'])

logging.basicConfig(format='%(levelname)s:%(asctime)s:%(message)s',
                    datefmt='%H:%M:%S',
                    level=logging.DEBUG)

#FIXME free camera in case of early termination

class ScanWorker(WorkerInPublishPullPipeline):

    def __init__(self):
        super(ScanWorker, self).__init__('Scan')

    def do_work(self):
        scan_arguments = pickle.loads(self.content)
        self.scan_preferences = scan_arguments.scan_preferences
        self.download_from_camera = scan_arguments.device.download_from_camera

        # FIXME send file size sum
        self.file_size_sum = 0
        self.files_scanned = 0
        self.file_type_counter = rpdfile.FileTypeCounter()

        if not self.download_from_camera:
            # Download from file system
            path = scan_arguments.device.path
            self.camera = None
            # Scan the files using lightweight high-performance scandir
            if self.scan_preferences.scan_this_path(path):
                for self.dir_name, subdirs, self.file_list in scandir.walk(
                        path):
                    if len(subdirs) > 0:
                        if self.scan_preferences.ignored_paths:
                            # Don't inspect paths the user wants ignored
                            # Altering subdirs in place controls the looping
                            # [:] ensures the list is altered in place
                            # (mutating slice method)
                            subdirs[:] = filter(
                                self.scan_preferences.scan_this_path, subdirs)

                    for self.file_name in self.file_list:
                        self.process_file()

        else:
            # scanning directly from camera
            self.camera = Camera(scan_arguments.device.camera_model,
                                 scan_arguments.device.camera_port)
            # Download only from the DCIM folder(s) in the camera.
            # Phones especially have many directories with images, which we
            # must ignore
            if self.camera.camera_has_dcim():
                self._camera_folders_and_files = []
                self._camera_file_names = defaultdict(list)
                self._camera_audio_files = {}
                self._camera_video_thumbnails = {}

                # locate photos and videos, filtering out duplicate files
                for dcim_folder in self.camera.dcim_folders:
                    logging.debug("Scanning %s on %s", dcim_folder,
                                  self.camera.model)
                    self.locate_files_on_camera(dcim_folder)

                for self.dir_name, self.file_name in \
                        self._camera_folders_and_files:
                    self.process_file()
            else:
                logging.warning("Unable to detect any DCIM folders on %s",
                                self.camera.model)

            self.camera.free_camera()

        if self.files_scanned > 0 and not (self.files_scanned == 0 and
                                                   self.download_from_camera):
            logging.debug("{} total files scanned".format(
                self.files_scanned))

        self.send_finished_command()

    def locate_files_on_camera(self, path):
        """
        Scans the memory card(s) on the camera for photos, videos,
        audio files, and video thumbnail (THM) files. Looks only in the
        camera's DCIM folders, which are assumed to have already been
        located.

        For cameras with two memory cards, there are two broad
        possibilities:

        (!) the cards' contents mirror each other, because the camera
        writes the same files to both cards simultaneously

        (2) each card has a different set of files, e.g. because a
        different file type is written to each card, or the 2nd card is
        used only when the first is full

        In practice, we have to assume that if there are two memory
        cards, some files will be identical, and others different. Thus
        we have to scan the contents of both cards, analyzing file
        names, file modification times and file sizes.
        """

        for name, value in self.camera.camera.folder_list_files(path,
                                                         self.camera.context):
            # Check to see if the process has received a command to terminate
            # or pause
            self.check_for_command()

            base_name, ext = os.path.splitext(name)
            ext_lower = ext.lower()[1:]
            file_type = rpdfile.file_type(ext_lower)

            if file_type is not None:
                # file is a photo or video
                file_is_unique = True
                modification_time, size = self.camera.get_file_info(
                    path, name)

                if name in self._camera_file_names:
                    for existing_file_info in self._camera_file_names[name]:
                        if (existing_file_info.modification_time ==
                                    modification_time and
                                    existing_file_info.size == size):
                            file_is_unique = False
                            break
                if file_is_unique:
                    file_info = FileInfo(path=path,
                                         modification_time=modification_time,
                                         size=size, file_type=file_type,
                                         base_name=base_name,
                                         ext_lower=ext_lower)
                    self._camera_file_names[name].append(file_info)
                    self._camera_folders_and_files.append([path, name])
            else:
                # file on camera is not a known photo or video
                if ext_lower in rpdfile.AUDIO_EXTENSIONS:
                    self._camera_audio_files[path+base_name] = ext
                elif ext_lower in rpdfile.VIDEO_THUMBNAIL_EXTENSIONS:
                    self._camera_video_thumbnails[path+base_name] = ext
                else:
                    logging.debug("Ignoring unknown file %s on %s",
                                  os.path.join(path, name), self.camera.model)

        folders = []
        for name, value in self.camera.camera.folder_list_folders(path,
                                                    self.camera.context):
            if self.scan_preferences.scan_this_path(os.path.join(path,
                                                                 name)):
                    folders.append(name)

        # recurse over subfolders
        for name in folders:
            self.locate_files_on_camera(os.path.join(path, name))


    def process_file(self):
        # Check to see if the process has received a command to terminate or
        # pause
        self.check_for_command()

        file = os.path.join(self.dir_name, self.file_name)

        # do we have permission to read the file?
        if self.download_from_camera or os.access(file, os.R_OK):

            # count how many files of each type are included
            # i.e. how many photos and videos
            self.files_scanned += 1
            if not self.files_scanned % 100:
                logging.debug("Scanned {} files".format(
                    self.files_scanned))


            if not self.download_from_camera:
                base_name, ext = os.path.splitext(self.file_name)
                ext = ext.lower()[1:]
                file_type = rpdfile.file_type(ext)
            else:
                base_name = None
                for file_info in self._camera_file_names[self.file_name]:
                    if file_info.path == self.dir_name:
                        base_name = file_info.base_name
                        ext = file_info.ext_lower
                        file_type = file_info.file_type
                        break
                assert base_name is not None

            if file_type is not None:
                self.file_type_counter.add(file_type)

                if self.download_from_camera:
                    modification_time = file_info.modification_time
                    size = file_info.size
                else:
                    size = os.path.getsize(file)
                    modification_time = os.path.getmtime(file)

                self.file_size_sum += size

                # look for thumbnail file (extension THM) for videos
                if file_type == rpdfile.FILE_TYPE_VIDEO:
                    thm_full_name = self.get_video_THM_file(base_name)
                else:
                    thm_full_name = None


                # check if an audio file is associated with the photo or video
                audio_file_full_name = self.get_audio_file(base_name)

                rpd_file = rpdfile.get_rpdfile(ext,
                                               self.file_name,
                                               self.dir_name,
                                               size,
                                               modification_time,
                                               thm_full_name,
                                               audio_file_full_name,
                                               self.worker_id,
                                               file_type,
                                               self.download_from_camera)
                self.content = pickle.dumps(rpd_file)
                self.send_message_to_sink()

    def get_video_THM_file(self, base_name: str) -> str:
        """
        Checks to see if a thumbnail file (THM) with the same base name
        is in the same directory as the file.

        :param base_name: the file name without the extension
        :return: filename, including path, if found, else returns None
        """

        if self.download_from_camera:
            video_ext = self._camera_video_thumbnails.get(
                self.dir_name+base_name)
            if video_ext is not None:
                return '{}.{}'.format(
                    os.path.join(self.dir_name, base_name),
                    video_ext)
        else:
            return self._get_associated_file(
                base_name, rpdfile.VIDEO_THUMBNAIL_EXTENSIONS)

        return None

    def get_audio_file(self, base_name: str) -> str:
        """
        Checks to see if an audio file with the same base name
        is in the same directory as the file.

        :param base_name: the file name without the extension
        :return: filename, including path, if found, else returns None
        """

        if self.download_from_camera:
            audio_ext = self._camera_audio_files.get(
                self.dir_name+base_name)
            if audio_ext is not None:
                return '{}.{}'.format(
                    os.path.join(self.dir_name, base_name),
                    audio_ext)
        else:
            return self._get_associated_file(
                base_name, rpdfile.AUDIO_EXTENSIONS)

        return None

    def _get_associated_file(self, base_name: str, extensions_to_check: str):
        full_file_name_no_ext = os.path.join(self.dir_name, base_name)
        for e in extensions_to_check:
            possible_file = '{}.{}'.format(full_file_name_no_ext, e)
            if os.path.exists(possible_file):
                return  possible_file
            possible_file = '{}.{}'.format(full_file_name_no_ext, e.upper())
            if os.path.exists(possible_file):
                return possible_file
        return None

if __name__ == "__main__":
    scan = ScanWorker()


