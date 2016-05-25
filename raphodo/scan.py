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
import tempfile

if sys.version_info < (3,5):
    import scandir
    walk = scandir.walk
else:
    walk = os.walk
from typing import List, Dict, Union, Tuple

import gphoto2 as gp

# Instances of classes ScanArguments and ScanPreferences are passed via pickle
# Thus do not remove these two imports
from raphodo.interprocess import ScanArguments
from raphodo.preferences import ScanPreferences
from raphodo.interprocess import (WorkerInPublishPullPipeline, ScanResults,
                          ScanArguments)
from raphodo.camera import Camera, CameraError
import raphodo.rpdfile as rpdfile
from raphodo.constants import (DeviceType, FileType, DeviceTimestampTZ, datetime_offset, CameraErrorCode,
                               FileExtension, ThumbnailCacheDiskStatus)
from raphodo.rpdsql import DownloadedSQL, FileDownloaded
from raphodo.cache import ThumbnailCacheSql
from raphodo.utilities import stdchannel_redirected, datetime_roughly_equal
from raphodo.exiftool import ExifTool
import raphodo.metadatavideo as metadatavideo
import raphodo.metadataphoto as metadataphoto


FileInfo = namedtuple('FileInfo', ['path', 'modification_time', 'size',
                                   'ext_lower', 'base_name', 'file_type'])
CameraFile = namedtuple('CameraFile', 'name, size')
SampleDatetime = namedtuple('SampleDatetime', 'datetime, determined_by')


class ScanWorker(WorkerInPublishPullPipeline):

    def __init__(self):
        self.downloaded = DownloadedSQL()
        self.thumbnail_cache = ThumbnailCacheSql()
        self.no_previously_downloaded = 0
        self.file_batch = []
        self.batch_size = 50
        self.file_type_counter = rpdfile.FileTypeCounter()
        self.file_size_sum = rpdfile.FileSizeSum()
        self.device_timestamp_type = DeviceTimestampTZ.undetermined

        # full_file_name (path+name):timestamp
        self.file_mdatatime = {}  # type: Dict[str, float]

        super().__init__('Scan')

    def do_work(self) -> None:
        logging.debug("Scan {} worker started".format(self.worker_id.decode()))

        scan_arguments = pickle.loads(self.content)  # type: ScanArguments
        self.scan_preferences = scan_arguments.scan_preferences
        if scan_arguments.log_gphoto2:
            gp.use_python_logging()

        if scan_arguments.ignore_other_types:
            rpdfile.PHOTO_EXTENSIONS_SCAN = rpdfile.PHOTO_EXTENSIONS_WITHOUT_OTHER

        self.use_thumbnail_cache = scan_arguments.use_thumbnail_cache

        self.download_from_camera = scan_arguments.device.device_type == DeviceType.camera
        if self.download_from_camera:
            self.camera_model = scan_arguments.device.camera_model
            self.camera_port = scan_arguments.device.camera_port
            self.is_mtp_device = scan_arguments.device.is_mtp_device
            self.camera_display_name = scan_arguments.device.display_name
            self.display_name = self.camera_display_name
            self.ignore_mdatatime_for_mtp_dng = self.is_mtp_device and \
                                              scan_arguments.ignore_mdatatime_for_mtp_dng
        else:
            self.camera_port = self.camera_model = self.is_mtp_device = None
            self.ignore_mdatatime_for_mtp_dng = False
            self.camera_display_name = None

        self.files_scanned = 0
        self.camera = None

        if not self.download_from_camera:
            # Download from file system
            path = os.path.abspath(scan_arguments.device.path)
            if scan_arguments.scan_only_DCIM and \
                            scan_arguments.device.device_type == DeviceType.volume:
                path = os.path.join(path, "DCIM")
            self.display_name = scan_arguments.device.display_name
            # Scan the files using lightweight high-performance scandir
            logging.info("Scanning {}".format(self.display_name))
            if self.scan_preferences.scan_this_path(path):
                for self.dir_name, subdirs, self.file_list in walk(path):
                    if len(subdirs) > 0:
                        if self.scan_preferences.ignored_paths:
                            # Don't inspect paths the user wants ignored
                            # Altering subdirs in place controls the looping
                            # [:] ensures the list is altered in place
                            # (mutating slice method)
                            subdirs[:] = filter(self.scan_preferences.scan_this_path, subdirs)

                    if (self.file_list and
                            self.device_timestamp_type == DeviceTimestampTZ.undetermined):
                        self.distingish_non_camera_device_timestamp()

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
                        self.display_name = self.camera_display_name
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

            if self.ignore_mdatatime_for_mtp_dng:
                logging.info("For any DNG files on the %s, when determining the creation date/"
                             "time, the metadata date/time will be ignored, and the file "
                             "modification date/time used instead", self.display_name)

            # Download only from the DCIM folder(s) in the camera.
            # Phones especially have many directories with images, which we
            # must ignore
            if self.camera.camera_has_dcim():
                logging.info("Scanning {}".format(self.display_name))
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
                logging.warning("Unable to detect any DCIM folders on %s", self.display_name)

            self.camera.free_camera()

        if self.file_batch:
            # Send any remaining files
            self.content = pickle.dumps(ScanResults(self.file_batch,
                                        self.file_type_counter,
                                        self.file_size_sum),
                                        pickle.HIGHEST_PROTOCOL)
            self.send_message_to_sink()
        if self.files_scanned > 0 and not (self.files_scanned == 0 and self.download_from_camera):
            logging.info("{} total files scanned on {}".format(self.files_scanned,
                                                               self.display_name))

        self.disconnect_logging()
        self.send_finished_command()

    def locate_files_on_camera(self, path: str, folder_identifier: int, basedir: str) -> None:
        """
        Scans the memory card(s) on the camera for photos, videos,
        audio files, and video thumbnail (THM) files. Looks only in the
        camera's DCIM folders, which are assumed to have already been
        located.

        We cannot assume file names are unique on any one memory card,
        as although it's unlikely, it's possible that a file with
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

        files_in_folder = []
        names = []
        try:
            files_in_folder = self.camera.camera.folder_list_files(path, self.camera.context)
        except gp.GPhoto2Error as e:
            logging.error("Unable to scan files on camera: error %s", e.code)

        if files_in_folder:
            # Distinguish the file type for every file in the folder
            names = [name for name, value in files_in_folder]
            split_names = [os.path.splitext(name) for name in names]
            # Remove the period from the extension
            exts = [ext[1:] for name, ext in split_names]
            exts_lower = [ext.lower() for ext in exts]
            ext_types = [rpdfile.extension_type(ext) for ext in exts_lower]

            if self.device_timestamp_type == DeviceTimestampTZ.undetermined:
                # Insert preferred type of file at front of file lists, because this
                # will be the file used to extract metadata time from.
                # When determining how a camera reports modification time, extraction order
                # of preference is (1) jpeg, (2) RAW, and finally least preferred is (3) video
                # However, if ignore_mdatatime_for_mtp_dng is set, put RAW at the end
                if not self.ignore_mdatatime_for_mtp_dng:
                    order = (FileExtension.jpeg, FileExtension.raw, FileExtension.video)
                else:
                    order = (FileExtension.jpeg, FileExtension.video, FileExtension.raw)
                for e in order:
                    if ext_types[0] == e:
                        break
                    try:
                        index = ext_types.index(e)
                    except ValueError:
                        continue
                    names.insert(0, names.pop(index))
                    split_names.insert(0, split_names.pop(index))
                    exts.insert(0, exts.pop(index))
                    exts_lower.insert(0, exts_lower.pop(index))
                    ext_types.insert(0, ext_types.pop(index))
                    break

        for idx, name in enumerate(names):
            # Check to see if the process has received a command to terminate
            # or pause
            self.check_for_controller_directive()

            # Get the information we extracted above
            base_name = split_names[idx][0]
            ext = exts[idx]
            ext_lower = exts_lower[idx]
            ext_type = ext_types[idx]
            file_type = rpdfile.file_type(ext_lower)

            if file_type is not None:
                # file is a photo or video
                file_is_unique = True
                try:
                    modification_time, size = self.camera.get_file_info(path, name)
                except gp.GPhoto2Error as e:
                    logging.error("Unable to access modification_time or size from %s on %s. "
                                  "Error code: %s", os.path.join(path, name), self.display_name,
                                  e.code)

                key = rpdfile.make_key(file_type, basedir)
                self.file_type_counter[key] += 1
                self.file_size_sum[key] += size

                if self.device_timestamp_type == DeviceTimestampTZ.undetermined and not (
                        self.ignore_mdatatime_for_mtp_dng and ext_type == FileExtension.raw):
                    logging.info("Using %s to determine camera time zone type for %s",
                                 ext_type.name, self.camera_display_name)
                    sample = self.sample_camera_datetime(path, name, ext_lower, ext_type, size)
                    self.determine_device_timestamp_tz(sample.datetime, modification_time,
                                                       sample.determined_by)

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
        try:
            for name, value in self.camera.camera.folder_list_folders(path, self.camera.context):
                if self.scan_preferences.scan_this_path(os.path.join(path, name)):
                        folders.append(name)
        except gp.GPhoto2Error as e:
                logging.error("Unable to scan files on %s. Error code: %s", self.display_name,
                              e.code)

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
                logging.info("Scanned {} files".format(
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
                    camera_file = CameraFile(name=self.file_name, size=size)
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
                # note: we should use the adjusted mtime, not the raw one
                adjusted_mtime = self.adjusted_mtime(modification_time)

                downloaded = self.downloaded.file_downloaded(
                                        name=self.file_name,
                                        size=size,
                                        modification_time=adjusted_mtime)

                thumbnail_cache_status = ThumbnailCacheDiskStatus.unknown

                # Assign metadata time, if we have it
                # If we don't, it will be extracted when thumbnails are generated
                mdatatime = self.file_mdatatime.get(file, 0.0)

                ignore_mdatatime = self.ignore_mdatatime_for_mtp_dng and ext == 'dng'

                if not mdatatime and self.use_thumbnail_cache and not ignore_mdatatime:
                    # Was there a thumbnail generated for the file?
                    # If so, get the metadata date time from that
                    get_thumbnail = self.thumbnail_cache.get_thumbnail_path(
                                            full_file_name=file,
                                            mtime=adjusted_mtime,
                                            size=size,
                                            camera_model=self.camera_model
                                            )
                    thumbnail_cache_status = get_thumbnail.disk_status
                    if thumbnail_cache_status in (ThumbnailCacheDiskStatus.found,
                                                     ThumbnailCacheDiskStatus.failure):
                        mdatatime = get_thumbnail.mdatatime

                if downloaded is not None:
                    self.no_previously_downloaded += 1
                    prev_full_name = downloaded.download_name
                    prev_datetime = downloaded.download_datetime
                else:
                    prev_full_name = prev_datetime = None

                if self.download_from_camera:
                    camera_memory_card_identifiers = self._folder_identifers_for_file[camera_file]
                    if not camera_memory_card_identifiers:
                        camera_memory_card_identifiers = None
                else:
                    camera_memory_card_identifiers = None

                rpd_file = rpdfile.get_rpdfile(
                    name=self.file_name,
                    path=self.dir_name,
                    size=size,
                    prev_full_name=prev_full_name,
                    prev_datetime=prev_datetime,
                    device_timestamp_type=self.device_timestamp_type,
                    mtime=modification_time,
                    mdatatime=mdatatime,
                    thumbnail_cache_status=thumbnail_cache_status,
                    thm_full_name=thm_full_name,
                    audio_file_full_name=audio_file_full_name,
                    xmp_file_full_name=xmp_file_full_name,
                    scan_id=self.worker_id,
                    file_type=file_type,
                    from_camera=self.download_from_camera,
                    camera_model=self.camera_model,
                    camera_port=self.camera_port,
                    camera_display_name=self.camera_display_name,
                    is_mtp_device=self.is_mtp_device,
                    camera_memory_card_identifiers=camera_memory_card_identifiers,
                    never_read_mdatatime=ignore_mdatatime,
                )

                self.file_batch.append(rpd_file)
                if len(self.file_batch) == self.batch_size:
                    self.content = pickle.dumps(ScanResults(
                                                rpd_files=self.file_batch,
                                                file_type_counter=self.file_type_counter,
                                                file_size_sum=self.file_size_sum),
                                                pickle.HIGHEST_PROTOCOL)
                    self.send_message_to_sink()
                    self.file_batch = []

    def sample_camera_datetime(self, path: str,
                               name: str,
                               extension: str,
                               ext_type: FileExtension,
                               size: int) -> SampleDatetime:
        """
        Extract sample metadata datetime from a photo or video on a camera
        """

        dt = determined_by = None
        use_app1 = save_chunk = exif_extract = False
        if ext_type == FileExtension.jpeg:
            determined_by = 'jpeg'
            if self.camera.can_fetch_thumbnails:
                use_app1 = True
            else:
                exif_extract = True
        elif ext_type == FileExtension.raw:
            determined_by = 'RAW'
            exif_extract = True
        elif ext_type == FileExtension.video:
            determined_by = 'video'
            save_chunk = True

        if use_app1:
            raw_bytes = self.camera.get_exif_extract_from_jpeg(path, name)
            if raw_bytes is not None:
                try:
                    with stdchannel_redirected(sys.stderr, os.devnull):
                        metadata = metadataphoto.MetaData(app1_segment=raw_bytes)
                except:
                    logging.warning("Scanner failed to load metadata from %s on %s", name,
                                  self.camera.display_name)
                else:
                    dt = metadata.date_time(missing=None)  # type: datetime
        elif exif_extract:
            offset = datetime_offset.get(extension)
            if offset is None:
                offset = size
            raw_bytes = self.camera.get_exif_extract(path, name, offset)
            if raw_bytes is not None:
                try:
                    with stdchannel_redirected(sys.stderr, os.devnull):
                        metadata = metadataphoto.MetaData(raw_bytes=raw_bytes)
                except:
                    logging.warning("Scanner failed to load metadata from %s on %s", name,
                                  self.camera.display_name)
                else:
                    dt = metadata.date_time(missing=None)  # type: datetime
        elif save_chunk:
            offset = datetime_offset.get(extension)
            if offset is None:
                max_size =  1024**2 * 20  # approx 21 MB
                offset = min(size, max_size)
            if offset is not None:
                with tempfile.TemporaryDirectory() as tempdir:
                    temp_name = os.path.join(tempdir, name)
                    if self.camera.save_file_chunk(path, name, offset, temp_name):
                        with ExifTool() as et_process:
                            metadata = metadatavideo.MetaData(temp_name, et_process)
                            dt = metadata.date_time(missing=None)
        if dt is None:
            logging.warning("Scanner failed to extract date time metadata from %s on %s",
                              name, self.camera.display_name)
        else:
            self.file_mdatatime[os.path.join(path, name)] = float(dt.timestamp())
        return SampleDatetime(dt, determined_by)

    def sample_non_camera_datetime(self, path: str,
                               name: str,
                               ext_type: FileExtension) -> SampleDatetime:
        """
        Extract sample metadata datetime from a photo or video not on a camera
        """

        dt = determined_by = None
        if ext_type == FileExtension.jpeg:
            determined_by = 'jpeg'
        elif ext_type == FileExtension.raw:
            determined_by = 'RAW'
        elif ext_type == FileExtension.video:
            determined_by = 'video'

        full_file_name = os.path.join(path, name)
        if ext_type == FileExtension.video:
            with ExifTool() as et_process:
                metadata = metadatavideo.MetaData(full_file_name, et_process)
                dt = metadata.date_time(missing=None)
        else:
           # photo - we don't care if jpeg or RAW
            try:
                with stdchannel_redirected(sys.stderr, os.devnull):
                    metadata = metadataphoto.MetaData(full_file_name=full_file_name)
            except:
                logging.warning("Scanner failed to load metadata from %s on %s", name,
                              self.camera.display_name)
            else:
                dt = metadata.date_time(missing=None)  # type: datetime

        if dt is None:
            logging.warning("Scanner failed to extract date time metadata from %s on %s",
                              name, self.camera.display_name)
        else:
            self.file_mdatatime[full_file_name] = dt.timestamp()
        return SampleDatetime(dt, determined_by)

    def distingish_non_camera_device_timestamp(self) -> None:
        """
        Attempt to determine the device's approach to timezones when it
        store timestamps.
        When determining how this device reports modification time, file
        preference is (1) RAW, (2)jpeg, and finally least preferred is (3)
        video. A RAW is the least likely to be modified.
        """

        logging.debug("Distinguishing approach to timestamp time zones on %s", self.display_name)
        attempts = 0
        for e in (FileExtension.raw, FileExtension.jpeg, FileExtension.video):
            for file in self.file_list:
                if rpdfile.extension_type(os.path.splitext(file)[1].lower()[1:]) == e:
                    logging.debug("Examining sample %s", os.path.join(self.dir_name, file))
                    sample = self.sample_non_camera_datetime(self.dir_name, file, e)
                    attempts += 1
                    if sample.datetime is not None:
                        full_file_name = os.path.join(self.dir_name, file)
                        self.file_mdatatime[full_file_name] = sample.datetime.timestamp()
                        try:
                            mtime = os.path.getmtime(full_file_name)
                        except OSError:
                            logging.warning("Could not determine modification "
                                "time for %s", full_file_name)
                        else:
                            self.determine_device_timestamp_tz(
                                sample.datetime, mtime, sample.determined_by)
                            return
                    elif attempts == 5:
                        self.device_timestamp_type = DeviceTimestampTZ.unknown
                        return

    def determine_device_timestamp_tz(self, mdatatime: datetime,
                                      modification_time: Union[int, float],
                                      determined_by: str) -> None:
        """
        Compare metadata time with file modification time in an attempt
        to determine the device's approach to timezones when it stores timestamps.

        :param mdatatime: file's metadata time
        :param modification_time: file's file system modification time
        :param determined_by: simple string used in log messages
        """

        if mdatatime is None:
            logging.debug("Could not determine Device timezone setting for %s",
                            self.display_name)
            self.device_timestamp_type = DeviceTimestampTZ.unknown

        # Must not compare exact times, as there can be a few seconds difference between
        # when a file was saved to the flash memory and when it was created in the
        # camera's memory. Allow for two minutes, to be safe.
        if datetime_roughly_equal(dt1=datetime.utcfromtimestamp(modification_time),
                                  dt2=mdatatime):
            logging.info("Device timezone setting for %s is UTC, as indicated by %s file",
                          self.display_name, determined_by)
            self.device_timestamp_type = DeviceTimestampTZ.is_utc
        elif datetime_roughly_equal(dt1=datetime.fromtimestamp(modification_time),
                                  dt2=mdatatime):
            logging.info("Device timezone setting for %s is local time, as indicated by "
                          "%s file", self.display_name, determined_by)
            self.device_timestamp_type = DeviceTimestampTZ.is_local
        else:
            logging.info("Device timezone setting for %s is unknown, because the file "
                          "modification time and file's time as recorded in metadata differ for "
                          "sample file %s",
                          self.display_name, determined_by)
            self.device_timestamp_type = DeviceTimestampTZ.unknown

    def adjusted_mtime(self, mtime: float) -> float:
        """
        Use the same calculated mtime that will be applied when the mtime
        is saved in the rpd_file

        :param mtime: raw modification time
        :return: modification time adjusted, if needed
        """

        if self.device_timestamp_type == DeviceTimestampTZ.is_utc:
            return datetime.utcfromtimestamp(mtime).timestamp()
        else:
            return mtime

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

    def cleanup_pre_stop(self):
        if self.camera is not None:
            self.camera.free_camera()

def trace_lines(frame, event, arg):
    if event != 'line':
        return
    co = frame.f_code
    func_name = co.co_name
    line_no = frame.f_lineno
    print('%s >>>>>>>>>>>>> At %s line %s' % (datetime.now().ctime(), func_name, line_no))

def trace_calls(frame, event, arg):
    if event != 'call':
        return
    co = frame.f_code
    func_name = co.co_name
    if func_name in ('write', '__getattribute__'):
        return
    func_line_no = frame.f_lineno
    func_filename = co.co_filename
    caller = frame.f_back
    if caller is not None:
        caller_line_no = caller.f_lineno
        caller_filename = caller.f_code.co_filename
    else:
        caller_line_no = caller_filename = ''
    print('% s Call to %s on line %s of %s from line %s of %s'  %
        (datetime.now().ctime(), func_name, func_line_no, func_filename, caller_line_no,
         caller_filename))

    for f in ('distingish_non_camera_device_timestamp','determine_device_timestamp_tz'):
        if func_name.find(f) >= 0:
            # Trace into this function
            return trace_lines

if __name__ == "__main__":
    if os.getenv('RPD_SCAN_DEBUG') is not None:
        sys.settrace(trace_calls)
    scan = ScanWorker()


