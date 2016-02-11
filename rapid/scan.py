#!/usr/bin/env python3

# Copyright (C) 2011-2016 Damon Lynch <damonlynch@gmail.com>

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

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2011-2016, Damon Lynch"

import os
import sys
import pickle
import logging
from collections import (namedtuple, defaultdict)
from datetime import datetime
from time import sleep

if sys.version_info < (3,5):
    import scandir
    walk = scandir.walk
else:
    walk = os.walk
from typing import List, Dict

import gi
gi.require_version('GExiv2', '0.10')
from gi.repository import GExiv2
import gphoto2 as gp

# Instances of classes ScanArguments and ScanPreferences are passed via pickle
# Thus do not remove these two imports
from interprocess import ScanArguments
from preferences import ScanPreferences
from interprocess import (WorkerInPublishPullPipeline, ScanResults,
                          ScanArguments)
from camera import Camera, CameraError
import rpdfile
from constants import (DeviceType, FileType, GphotoMTime, datetime_offset, CameraErrorCode,
                       logging_format, logging_date_format)
from rpdsql import DownloadedSQL, FileDownloaded
from utilities import stdchannel_redirected

FileInfo = namedtuple('FileInfo', ['path', 'modification_time', 'size',
                                   'ext_lower', 'base_name', 'file_type'])
CameraFile = namedtuple('CameraFile', 'name size')

#FIXME free camera in case of early termination

class ScanWorker(WorkerInPublishPullPipeline):

    def __init__(self):
        self.downloaded = DownloadedSQL()
        self.no_previously_downloaded = 0
        self.file_batch = []
        self.batch_size = 50
        self.file_type_counter = rpdfile.FileTypeCounter()
        self.file_size_sum = rpdfile.FileSizeSum()
        self.gphoto_mtime = GphotoMTime.undetermined
        super().__init__('Scan')

    def do_work(self) -> None:
        logging.basicConfig(format=logging_format,
                    datefmt=logging_date_format,
                    level=self.logging_level)

        logging.debug("Scan {} worker started".format(self.worker_id.decode()))

        scan_arguments = pickle.loads(self.content) # type: ScanArguments
        self.scan_preferences = scan_arguments.scan_preferences

        if scan_arguments.ignore_other_types:
            rpdfile.PHOTO_EXTENSIONS_SCAN = rpdfile.PHOTO_EXTENSIONS_WITHOUT_OTHER

        self.download_from_camera = scan_arguments.device.device_type == DeviceType.camera
        if self.download_from_camera:
            self.camera_model = scan_arguments.device.camera_model
            self.camera_port = scan_arguments.device.camera_port
            self.is_mtp_device = scan_arguments.device.is_mtp_device
            self.camera_display_name = scan_arguments.device.display_name
        else:
            self.camera_port = self.camera_model = self.is_mtp_device = None
            self.camera_display_name = None

        self.files_scanned = 0

        if not self.download_from_camera:
            # Download from file system
            path = scan_arguments.device.path
            self.camera = None
            # Scan the files using lightweight high-performance scandir
            if self.scan_preferences.scan_this_path(path):
                for self.dir_name, subdirs, self.file_list in walk(path):
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
            have_optimal_display_name = scan_arguments.device.have_optimal_display_name
            while True:
                try:
                    self.camera = Camera(model=scan_arguments.device.camera_model,
                                         port=scan_arguments.device.camera_port,
                                         raise_errors=True)
                    if not have_optimal_display_name:
                        # Update the GUI with the real name of the camera
                        # and its storage information
                        have_optimal_display_name = True
                        self.camera_display_name = self.camera.display_name
                        storage_space = self.camera.get_storage_media_capacity(refresh=True)
                        self.content = pickle.dumps(ScanResults(
                                                    optimal_display_name=self.camera_display_name,
                                                    storage_space=storage_space,
                                                    scan_id=int(self.worker_id)),
                                                    pickle.HIGHEST_PROTOCOL)
                        self.send_message_to_sink()
                    break
                except CameraError as e:
                    self.content = pickle.dumps(ScanResults(
                                                error_code=e.code,
                                                scan_id=int(self.worker_id)),
                                                pickle.HIGHEST_PROTOCOL)
                    self.send_message_to_sink()
                    # Wait for command to resume or halt processing
                    self.resume_work()

            # Download only from the DCIM folder(s) in the camera.
            # Phones especially have many directories with images, which we
            # must ignore
            if self.camera.camera_has_dcim():
                self._camera_folders_and_files = []
                self._camera_file_names = defaultdict(list)
                self._camera_audio_files = defaultdict(list)
                self._camera_video_thumbnails = defaultdict(list)
                self._camera_xmp_files = defaultdict(list)
                self._folder_identifiers = {}
                self._folder_identifers_for_file = defaultdict(list) # type: Dict[int, List[int]]
                self._camera_directories_for_file = defaultdict(list)

                dcim_folders = self.camera.dcim_folders

                if len(dcim_folders) > 1:
                    # This camera has dual memory cards.
                    # Give each folder an numeric identifier that will be
                    # used to identify which card a given file comes from
                    dcim_folders.sort()
                    for idx, folder in enumerate(dcim_folders):
                        self._folder_identifiers[folder] = idx + 1

                # locate photos and videos, identifying duplicate files
                for dcim_folder in dcim_folders:
                    logging.debug("Scanning %s on %s", dcim_folder, self.camera.display_name)
                    folder_identifier = self._folder_identifiers.get(dcim_folder)
                    basedir = dcim_folder[:-len('/DCIM')]
                    self.locate_files_on_camera(dcim_folder, folder_identifier, basedir)

                for self.dir_name, self.file_name in self._camera_folders_and_files:
                    self.process_file()
            else:
                logging.warning("Unable to detect any DCIM folders on %s", self.camera.model)

            self.camera.free_camera()

        if self.file_batch:
            # Send any remaining files
            self.content = pickle.dumps(ScanResults(self.file_batch,
                                        self.file_type_counter,
                                        self.file_size_sum),
                                        pickle.HIGHEST_PROTOCOL)
            self.send_message_to_sink()
        if self.files_scanned > 0 and not (self.files_scanned == 0 and self.download_from_camera):
            logging.debug("{} total files scanned".format(
                self.files_scanned))

        self.send_finished_command()

    def locate_files_on_camera(self, path: str, folder_identifier: int, basedir: str) -> None:
        """
        Scans the memory card(s) on the camera for photos, videos,
        audio files, and video thumbnail (THM) files. Looks only in the
        camera's DCIM folders, which are assumed to have already been
        located.

        We cannot assume file names are unique on any one memory card,
        as although it's very unlikely, it's possible that a file with
        the same name might be in different subfolders.

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

        If a camera has more than one memory card, we store which
        card the file came from using a simple numeric identifier i.e.
        1 or 2.

        For duplicate files, we record both directories the file is
        stored on.

        :param path: the path on the camera to analyze for files and
         folders
        :param folder_identifier: if not None, then indicates (1) the
         camera being scanned has more than one memory card, and (2)
         the simple numeric identifier of the memory card being
         scanned right now
        :param basedir: the base directory of the path, as reported by
         libgphoto2
        """

        folders_and_files = []
        try:
            folders_and_files = self.camera.camera.folder_list_files(path, self.camera.context)
        except gp.GPhoto2Error as e:
            logging.error("Unable to scan files on camera: error %s", e.code)

        for name, value in folders_and_files:
            # Check to see if the process has received a command to terminate
            # or pause
            self.check_for_controller_directive()

            base_name, ext = os.path.splitext(name)
            # remove the period from the extension
            ext = ext[1:]
            ext_lower = ext.lower()
            file_type = rpdfile.file_type(ext_lower)

            if file_type is not None:
                # file is a photo or video
                file_is_unique = True
                modification_time, size = self.camera.get_file_info(path, name)

                key = rpdfile.make_key(file_type, basedir)
                self.file_type_counter[key] += 1
                self.file_size_sum[key] += size

                if file_type == FileType.photo and self.gphoto_mtime == GphotoMTime.undetermined:
                    self.set_gphoto_mtime_(path, name, ext_lower, modification_time, size)

                modification_time = self.get_camera_modification_time(modification_time)

                # Store the directory this file is stored in, used when
                # determining if associate files are part of the download
                cf = CameraFile(name=name, size=size)
                self._camera_directories_for_file[cf].append(path)

                if folder_identifier is not None:
                    # Store which which card the file came from using a
                    # simple numeric identifier i.e. 1 or 2.
                    self._folder_identifers_for_file[cf].append(folder_identifier)

                if name in self._camera_file_names:
                    for existing_file_info in self._camera_file_names[name]:
                        # Don't compare file modification time in this
                        # comparison, because files can be written to
                        # different cards several seconds apart when
                        # the write speeds of the cards differ
                        if existing_file_info.size == size:
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
                # this file on the camera is not a photo or video
                if ext_lower in rpdfile.AUDIO_EXTENSIONS:
                    self._camera_audio_files[base_name].append((path, ext))
                elif ext_lower in rpdfile.VIDEO_THUMBNAIL_EXTENSIONS:
                    self._camera_video_thumbnails[base_name].append((path, ext))
                elif ext_lower == 'xmp':
                    self._camera_xmp_files[base_name].append((path, ext))
                else:
                    logging.debug("Ignoring unknown file %s on %s",
                                  os.path.join(path, name), self.camera.model)

        folders = []
        for name, value in self.camera.camera.folder_list_folders(path, self.camera.context):
            if self.scan_preferences.scan_this_path(os.path.join(path, name)):
                    folders.append(name)

        # recurse over subfolders
        for name in folders:
            self.locate_files_on_camera(os.path.join(path, name), folder_identifier, basedir)


    def process_file(self):
        # Check to see if the process has received a command to terminate or
        # pause
        self.check_for_controller_directive()

        file = os.path.join(self.dir_name, self.file_name)

        # do we have permission to read the file?
        if self.download_from_camera or os.access(file, os.R_OK):

            # count how many files of each type are included
            # i.e. how many photos and videos
            self.files_scanned += 1
            if not self.files_scanned % 10000:
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
                self.file_type_counter[file_type] += 1

                if self.download_from_camera:
                    modification_time = file_info.modification_time
                    size = file_info.size
                    camera_file = CameraFile(name=self.file_name,size=size)
                else:
                    stat = os.stat(file)
                    size = stat.st_size
                    modification_time = stat.st_mtime
                    camera_file = None

                self.file_size_sum[file_type] += size

                # look for thumbnail file (extension THM) for videos
                if file_type == FileType.video:
                    thm_full_name = self.get_video_THM_file(base_name, camera_file)
                else:
                    thm_full_name = None

                # check if an XMP file is associated with the photo or video
                xmp_file_full_name = self.get_xmp_file(base_name, camera_file)


                # check if an audio file is associated with the photo or video
                audio_file_full_name = self.get_audio_file(base_name, camera_file)

                # has the file been downloaded previously?
                downloaded = self.downloaded.file_downloaded(
                                        name=self.file_name,
                                        size=size,
                                        modification_time=modification_time)

                if downloaded is not None:
                    self.no_previously_downloaded += 1
                    prev_full_name = downloaded.download_name
                    prev_datetime = downloaded.download_datetime
                    # logging.debug('{} previously downloaded on {} to {'
                    #               '}'.format(self.file_name, prev_datetime,
                    #                          prev_full_name))
                else:
                    prev_full_name = prev_datetime = None

                if self.download_from_camera:
                    camera_memory_card_identifiers = self._folder_identifers_for_file[camera_file]
                    if not camera_memory_card_identifiers:
                        camera_memory_card_identifiers = None
                else:
                    camera_memory_card_identifiers = None

                rpd_file = rpdfile.get_rpdfile(self.file_name,
                                               self.dir_name,
                                               size,
                                               prev_full_name,
                                               prev_datetime,
                                               modification_time,
                                               thm_full_name,
                                               audio_file_full_name,
                                               xmp_file_full_name,
                                               self.worker_id,
                                               file_type,
                                               self.download_from_camera,
                                               self.camera_model,
                                               self.camera_port,
                                               self.camera_display_name,
                                               self.is_mtp_device,
                                               camera_memory_card_identifiers)
                self.file_batch.append(rpd_file)
                if len(self.file_batch) == self.batch_size:
                    self.content = pickle.dumps(ScanResults(
                                                rpd_files=self.file_batch,
                                                file_type_counter=self.file_type_counter,
                                                file_size_sum=self.file_size_sum),
                                                pickle.HIGHEST_PROTOCOL)
                    self.send_message_to_sink()
                    self.file_batch = []

    def get_camera_modification_time(self, modification_time) -> float:
        if self.gphoto_mtime == GphotoMTime.is_utc:
            return datetime.utcfromtimestamp(modification_time).timestamp()
        else:
            return float(modification_time)

    def set_gphoto_mtime_(self, path: str,
                          name: str,
                          extension: str,
                          modification_time: int,
                          size: int) -> None:
        """
        Determine how libgphoto2 reports modification time.

        gPhoto2 can give surprising results for the file modification
        time, such that it's off by exactly the time zone.
        For example, if we're at UTC + 5, the time stamp is five hours
        in advance of what is recorded on the memory card
        """
        metadata = None
        if extension in rpdfile.JPEG_TYPE_EXTENSIONS:
            raw_bytes = self.camera.get_exif_extract_from_jpeg(path, name)
            if raw_bytes is not None:
                metadata = GExiv2.Metadata()
                try:
                    with stdchannel_redirected(sys.stderr, os.devnull):
                        metadata.from_app1_segment(raw_bytes)
                except:
                    logging.error("Scanner failed to load metadata from %s on %s", name,
                                  self.camera.display_name)
        else:
            offset = datetime_offset.get(extension)
            if offset is None:
                offset = size
            raw_bytes = self.camera.get_exif_extract_from_raw(path, name, offset)
            if raw_bytes is not None:
                metadata = GExiv2.Metadata()
                try:
                    with stdchannel_redirected(sys.stderr, os.devnull):
                        metadata.open_buf(raw_bytes)
                except:
                    logging.error("Scanner failed to load metadata from %s on %s", name,
                                  self.camera.display_name)
        if metadata is not None:
            dt = None
            try:
                dt = metadata.get_date_time() # type: datetime
            except:
                logging.warning("Scanner failed to extract date time metadata from %s on %s",
                              name, self.camera.display_name)
                logging.warning("Could not determine gPhoto2 timezone setting for %s",
                                self.camera.display_name)
                self.gphoto_mtime = GphotoMTime.unknown
            else:
                if datetime.utcfromtimestamp(modification_time) == dt:
                    logging.debug("gPhoto2 timezone setting for %s is UTC",
                                self.camera.display_name)
                    self.gphoto_mtime = GphotoMTime.is_utc
                else:
                    logging.debug("gPhoto2 timezone setting for %s is local time",
                                self.camera.display_name)
                    self.gphoto_mtime = GphotoMTime.is_local
        else:
            logging.warning("Could not determine gPhoto2 timezone setting for %s",
                                self.camera.display_name)
            self.gphoto_mtime = GphotoMTime.unknown

    def _get_associate_file_from_camera(self, base_name: str,
                associate_files: defaultdict, camera_file: CameraFile) -> str:
        for path, ext in associate_files[base_name]:
            if path in self._camera_directories_for_file[camera_file]:
                return '{}.{}'.format(
                    os.path.join(path, base_name),ext)
        return None

    def get_video_THM_file(self, base_name: str, camera_file: CameraFile) -> str:
        """
        Checks to see if a thumbnail file (THM) with the same base name
        is in the same directory as the file.

        :param base_name: the file name without the extension
        :return: filename, including path, if found, else returns None
        """

        if self.download_from_camera:
            return  self._get_associate_file_from_camera(base_name,
                     self._camera_video_thumbnails, camera_file)
        else:
            return self._get_associated_file(base_name, rpdfile.VIDEO_THUMBNAIL_EXTENSIONS)

    def get_audio_file(self, base_name: str, camera_file: CameraFile) -> str:
        """
        Checks to see if an audio file with the same base name
        is in the same directory as the file.

        :param base_name: the file name without the extension
        :return: filename, including path, if found, else returns None
        """

        if self.download_from_camera:
            return  self._get_associate_file_from_camera(base_name,
                     self._camera_audio_files, camera_file)
        else:
            return self._get_associated_file(base_name, rpdfile.AUDIO_EXTENSIONS)

    def get_xmp_file(self, base_name: str, camera_file: CameraFile) -> str:
        """
        Checks to see if an XMP file with the same base name
        is in the same directory as tthe file.

        :param base_name: the file name without the extension
        :return: filename, including path, if found, else returns None
        """
        if self.download_from_camera:
            return  self._get_associate_file_from_camera(base_name,
                     self._camera_xmp_files, camera_file)
        else:
            return self._get_associated_file(base_name, ['XMP'])

    def _get_associated_file(self, base_name: str, extensions_to_check: List[str]) -> str:
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


