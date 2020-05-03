#!/usr/bin/env python3

# Copyright (C) 2011-2020 Damon Lynch <damonlynch@gmail.com>

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

Returns results using the 0MQ pipeline pattern.

Photo and movie metadata is (for the most part) not read during this
scan process, because doing so is too slow. However, as part of scanning a
device, there are two aspects to metadata that are in fact needed:

1. A sample of photo and video metadata, that is used to demonstrate file
   renaming. That is one sample photo, and one sample video.

2. The device's time zone must be determined, as cameras handle their time
   zone setting differently from phones, and results can be unpredictable.
   Therefore need to analyze the created date time metadata of a file the
   device and compare it against the file modification time on the file system
   or more importantly, gphoto2. It's not an exact science and there are
   problems, but doing this is better than not doing it at all.

A sample photo or video for (1) can be used for (2)

"""
__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2011-2020, Damon Lynch"

import os
import sys
import pickle
import logging
from collections import (namedtuple, defaultdict, deque)
from datetime import datetime
import tempfile
import operator
import locale
try:
    # Use the default locale as defined by the LANG variable
    locale.setlocale(locale.LC_ALL, '')
except locale.Error:
    pass

if sys.version_info < (3,5):
    import scandir
    walk = scandir.walk
else:
    walk = os.walk
from typing import List, Dict, Union, Optional, Iterator, Tuple, DefaultDict

import gphoto2 as gp

# Instances of classes ScanArguments and ScanPreferences are passed via pickle
# Thus do not remove these two imports
from raphodo.interprocess import ScanArguments
from raphodo.preferences import ScanPreferences, Preferences
from raphodo.interprocess import (
    WorkerInPublishPullPipeline, ScanResults, ScanArguments
)
from raphodo.camera import (
    Camera, CameraError, CameraProblemEx, gphoto2_python_logging, gphoto2_named_error
)
import raphodo.rpdfile as rpdfile
from raphodo.constants import (
    DeviceType, FileType, DeviceTimestampTZ, CameraErrorCode, FileExtension,
    ThumbnailCacheDiskStatus, all_tags_offset, ExifSource, all_tags_offset_exiftool
)
from raphodo.rpdsql import DownloadedSQL, FileDownloaded
from raphodo.cache import ThumbnailCacheSql
from raphodo.utilities import (
    stdchannel_redirected, datetime_roughly_equal, GenerateRandomFileName, format_size_for_user,
    is_snap
)
from raphodo.exiftool import ExifTool
import raphodo.metadatavideo as metadatavideo
import raphodo.metadataphoto as metadataphoto
import raphodo.metadataexiftool as metadataexiftool
from raphodo.problemnotification import (
    ScanProblems, UnhandledFileProblem, CameraDirectoryReadProblem, CameraFileInfoProblem,
    CameraFileReadProblem, FileMetadataLoadProblem, FileWriteProblem, FsMetadataReadProblem,
    FileZeroLengthProblem
)
from raphodo.storage import get_uri, CameraDetails, gvfs_gphoto2_path
import raphodo.fileformats as fileformats


FileInfo = namedtuple('FileInfo', 'path modification_time size ext_lower base_name file_type')
CameraFile = namedtuple('CameraFile', 'name size')
CameraMetadataDetails = namedtuple(
    'CameraMetadataDetails', 'path name size extension mtime file_type'
)
SampleMetadata = namedtuple('SampleMetadata', 'datetime determined_by')


class ScanWorker(WorkerInPublishPullPipeline):

    def __init__(self):
        self.downloaded = DownloadedSQL()
        self.thumbnail_cache = ThumbnailCacheSql(create_table_if_not_exists=False)
        self.no_previously_downloaded = 0
        self.file_batch = []
        self.batch_size = 50
        self.file_type_counter = rpdfile.FileTypeCounter()
        self.file_size_sum = rpdfile.FileSizeSum()
        self.device_timestamp_type = DeviceTimestampTZ.undetermined

        # full_file_name (path+name):timestamp
        self.file_mdatatime = {}  # type: Dict[str, float]

        self.sample_exif_bytes = None  # type: bytes
        self.sample_exif_source = None  # type: ExifSource
        self.sample_photo = None  # type: rpdfile.Photo
        self.sample_video = None  # type: rpdfile.Video
        self.sample_photo_source_is_extract = None  # type: Optional[bool]
        self.sample_photo_extract_full_file_name = None  # type: Optional[str]
        self.sample_video_extract_full_file_name = None  # type: Optional[str]
        self.sample_photo_file_full_file_name = None  # type: Optional[str]
        self.sample_photo_full_file_downloaded = None  # type: Optional[bool]
        self.sample_video_file_full_file_name = None  # type: Optional[str]
        self.sample_video_full_file_downloaded = None  # type: Optional[bool]
        self.located_sample_photo = False
        self.located_sample_video = False
        self.prepared_sample_photo = False
        self.prepared_sample_video = False
        # If the entire video or photo is required to extract metadata
        # (which affects thumbnail generation too).
        # Set only if downloading from a camera / phone.
        self.entire_photo_required = False
        self.entire_video_required = False

        self.prefs = Preferences()
        self.scan_preferences = ScanPreferences(self.prefs.ignored_paths)

        self.problems = ScanProblems()

        self._camera_details = None  # type: Optional[CameraDetails]

        self._et_process = None  # type: Optional[ExifTool]

        super().__init__('Scan')

    @property
    def et_process(self) -> ExifTool:
        """
        Instead of using with statement, which starts a new instance of ExifTool every time,
        start it once for this scan process, if needed
        :return: ExifTool process
        """
        if self._et_process is None:
            self._et_process = ExifTool()
            self._et_process.start()
        return self._et_process

    def exit_exiftool(self):
        if self._et_process is not None:
            # explicitly terminate the process right away, not relying on
            # python's garbage collection (which as the docs indicate, is a bad idea)
            self._et_process.terminate()
            self._et_process = None

    def do_work(self) -> None:
        try:
            self.do_scan()
        except Exception as e:
            try:
                device = self.display_name
            except AttributeError:
                device = ''
            logging.exception("Unexpected exception while scanning %s", device)

            self.content = pickle.dumps(
                ScanResults(scan_id=int(self.worker_id), fatal_error=True),
                pickle.HIGHEST_PROTOCOL
            )
            self.exit_exiftool()
            self.send_message_to_sink()
            self.disconnect_logging()
            self.send_finished_command()

    def do_scan(self) -> None:
        logging.debug("Scan {} worker started".format(self.worker_id.decode()))

        scan_arguments = pickle.loads(self.content)  # type: ScanArguments
        if scan_arguments.log_gphoto2:
            self.gphoto2_logging = gphoto2_python_logging()

        if scan_arguments.ignore_other_types:
            fileformats.PHOTO_EXTENSIONS_SCAN = fileformats.PHOTO_EXTENSIONS_WITHOUT_OTHER

        self.device = scan_arguments.device

        self.download_from_camera = scan_arguments.device.device_type == DeviceType.camera
        self.camera_storage_descriptions = []
        if self.download_from_camera:
            self.camera_model = scan_arguments.device.camera_model
            self.camera_port = scan_arguments.device.camera_port
            self.is_mtp_device = scan_arguments.device.is_mtp_device
            self.camera_display_name = scan_arguments.device.display_name
            self.display_name = self.camera_display_name
            self.ignore_mdatatime_for_mtp_dng = self.is_mtp_device and \
                                                self.prefs.ignore_mdatatime_for_mtp_dng
        else:
            self.camera_port = self.camera_model = self.is_mtp_device = None
            self.ignore_mdatatime_for_mtp_dng = False
            self.camera_display_name = None

        self.files_scanned = 0
        self.camera = None
        terminated = False

        if not self.download_from_camera:
            self.scan_file_system(scan_arguments)
        else:
            try:
                self.scan_camera(scan_arguments)
                # Sanity check: ensure file contents are still accessible
                try:
                    self.camera.camera.folder_list_files('/', self.camera.context)
                except gp.GPhoto2Error as e:
                    raise CameraError(CameraErrorCode.inaccessible)
                else:
                    self.camera.free_camera()

            except CameraError as e:
                if e.code == CameraErrorCode.inaccessible:
                    terminated = True
                    logging.info("Terminating scan of %s", self.display_name)
                    if self.is_mtp_device:
                        logging.debug("%s is an MTP device", self.display_name)
                    if self.camera is not None:
                        self.camera.free_camera()
                else:
                    raise

        if not terminated:
            if self.file_batch:
                # Send any remaining files, including the sample photo or video
                self.content = pickle.dumps(
                    ScanResults(
                        self.file_batch,
                        self.file_type_counter,
                        self.file_size_sum,
                        sample_photo=self.sample_photo,
                        sample_video=self.sample_video,
                        entire_video_required=self.entire_video_required,
                        entire_photo_required=self.entire_photo_required,
                    ),
                    pickle.HIGHEST_PROTOCOL
                )
                self.send_message_to_sink()
        elif self.download_from_camera:
            self.content = pickle.dumps(
                ScanResults(
                    scan_id=int(self.worker_id), camera_removed=True
                ),
                pickle.HIGHEST_PROTOCOL
            )
            self.send_message_to_sink()

        self.send_problems()

        if self.files_scanned > 0 and not (self.files_scanned == 0 and self.download_from_camera):
            logging.info(
                "{} total files scanned on {}".format(self.files_scanned, self.display_name)
            )

        self.exit_exiftool()
        self.disconnect_logging()
        self.send_finished_command()

    def send_problems(self) -> None:
        if self.problems:
            self.content = pickle.dumps(
                ScanResults(
                    scan_id=int(self.worker_id), problems=self.problems
                ),
                pickle.HIGHEST_PROTOCOL
            )
            self.send_message_to_sink()

    def walk_file_system(self, path_to_walk: str) -> Iterator[Tuple[str, str]]:
        """
        Return files on local file system, ignoring those in directories
        the user doesn't want scanned
        :param path_to_walk: the path to scan
        """

        for dir_name, dir_list, file_list in walk(path_to_walk):
            if len(dir_list) > 0:
                # Do not scan gvfs gphoto2 mount
                dir_list[:] = (d for d in dir_list if not gvfs_gphoto2_path(dir_name + d))

                if self.scan_preferences.ignored_paths:
                    # Don't inspect paths the user wants ignored
                    # Altering subdirs in place controls the looping
                    # [:] ensures the list is altered in place
                    # (mutating slice method)
                    dir_list[:] = filter(self.scan_preferences.scan_this_path, dir_list)
            for name in file_list:
                yield dir_name, name

    def scan_file_system(self, scan_arguments: ScanArguments):
        """
        Download from file system - either on This Computer, or an external volume like a
        # memory card or USB Flash or external drive of some kind

        :param scan_arguments: scan configuration
        """

        path = os.path.abspath(scan_arguments.device.path)
        self.display_name = scan_arguments.device.display_name

        scanning_specific_path = self.prefs.scan_specific_folders and \
                                 scan_arguments.device.device_type == DeviceType.volume
        if scanning_specific_path:
            specific_folder_prefs = self.prefs.folders_to_scan
            paths = tuple(
                os.path.join(path, folder) for folder in os.listdir(path)
                if folder in specific_folder_prefs and os.path.isdir(os.path.join(path, folder))
            )
            logging.info(
                "For device %s, identified paths: %s", self.display_name, ', '.join(paths)
            )
        else:
            paths = path,

        if scan_arguments.device.device_type == DeviceType.volume:
            device_type = 'device'
        else:
            device_type = 'This Computer path'
        logging.info("Scanning {} {}".format(device_type, self.display_name))

        self.problems.uri = get_uri(path=path)
        self.problems.name = self.display_name

        # Before doing anything else, determine time zone approach
        # Need two different walks because first folder of files
        # might be videos, then the 2nd folder photos, etc.
        for path in paths:
            self.distinguish_non_camera_device_timestamp(path)
            if self.device_timestamp_type != DeviceTimestampTZ.undetermined:
                break

        for path in paths:
            if scanning_specific_path:
                logging.info("Scanning {} on {}".format(path, self.display_name))
            for dir_name, name in self.walk_file_system(path):
                self.dir_name = dir_name
                self.file_name = name
                self.process_file()

    def scan_camera(self, scan_arguments: ScanArguments) -> None:
        """
        Scan camera for files.

        Raises error if camera becomes inaccessible

        :param scan_arguments: scan configuration
        """

        have_optimal_display_name = scan_arguments.device.have_optimal_display_name
        if self.prefs.scan_specific_folders:
            specific_folder_prefs = self.prefs.folders_to_scan
        else:
            specific_folder_prefs = None
        while True:
            try:
                self.camera = Camera(
                    model=scan_arguments.device.camera_model,
                    port=scan_arguments.device.camera_port,
                    raise_errors=True,
                    specific_folders=specific_folder_prefs
                )
                if not have_optimal_display_name:
                    # Update the GUI with the real name of the camera
                    # and its storage information
                    have_optimal_display_name = True
                    self.camera_display_name = self.camera.display_name
                    self.display_name = self.camera_display_name
                    storage_space = self.camera.get_storage_media_capacity(refresh=True)
                    storage_descriptions = self.camera.get_storage_descriptions()
                    self.content = pickle.dumps(
                        ScanResults(
                            optimal_display_name=self.camera_display_name,
                            storage_space=storage_space,
                            storage_descriptions=storage_descriptions,
                            scan_id=int(self.worker_id),
                        ),
                        pickle.HIGHEST_PROTOCOL
                    )
                    self.send_message_to_sink()
                break
            except CameraProblemEx as e:
                self.content = pickle.dumps(
                    ScanResults(
                        error_code=e.code, scan_id=int(self.worker_id)
                    ),
                    pickle.HIGHEST_PROTOCOL
                )
                self.send_message_to_sink()
                # Wait for command to resume or halt processing
                self.resume_work()

        self.camera_details = 0
        self.problems.uri = get_uri(camera_details=self.camera_details)
        self.problems.name = self.display_name

        if self.ignore_mdatatime_for_mtp_dng:
            logging.info(
                "For any DNG files on the %s, when determining the creation date/"
                "time, the metadata date/time will be ignored, and the file "
                "modification date/time used instead", self.display_name
            )

        # Download only from the DCIM type folder(s) in the camera,
        # if that's what the user has specified. Otherwise, try to download from everything we
        # can find.
        if self.camera.camera_has_folders_to_scan():
            logging.info("Scanning {}".format(self.display_name))
            self._camera_folders_and_files = []
            self._camera_file_names = defaultdict(list)
            self._camera_audio_files = defaultdict(list)
            self._camera_video_thumbnails = defaultdict(list)
            self._camera_xmp_files = defaultdict(list)
            self._camera_log_files = defaultdict(list)
            self._folder_identifiers = {}
            self._folder_identifers_for_file = \
                defaultdict(list)  # type: DefaultDict[int, List[int]]
            self._camera_directories_for_file = defaultdict(list)
            self._camera_photos_videos_by_type = \
                defaultdict(list)  # type: DefaultDict[FileExtension, List[CameraMetadataDetails]]

            specific_folders = self.camera.specific_folders

            if self.camera.dual_slots_active:
                # This camera has dual memory cards in use.
                # Give each folder an numeric identifier that will be
                # used to identify which card a given file comes from
                for idx, folders in enumerate(specific_folders):
                    for folder in folders:
                        self._folder_identifiers[folder] = idx + 1

            # locate photos and videos, identifying duplicate files
            # identify candidates for extracting metadata
            for idx, folders in enumerate(specific_folders):
                # Setup camera details for each storage space in the camera
                self.camera_details = idx
                # Now initialize the problems container, if not already done so
                if idx:
                    self.problems.name = self.camera_display_name
                    self.problems.uri = get_uri(camera_details=self.camera_details)

                for specific_folder in folders:
                    logging.debug(
                        "Scanning %s on %s", specific_folder, self.camera.display_name
                    )
                    folder_identifier = self._folder_identifiers.get(specific_folder)
                    if specific_folder_prefs is None:
                        basedir = specific_folder
                    else:
                        basedir = os.path.dirname(specific_folder)
                    self.locate_files_on_camera(specific_folder, folder_identifier, basedir)

            # extract camera metadata
            if self._camera_photos_videos_by_type:
                self.identify_camera_tz_and_sample_files()

            # now, process each file
            for self.dir_name, self.file_name in self._camera_folders_and_files:
                self.process_file()
        else:
            logging.warning(
                "Unable to detect any specific folders (like DCIM) on %s", self.display_name
            )

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

        We ignore all folders that contain a file .nomedia

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
            logging.error(
                "Unable to scan files on %s: %s", self.display_name, gphoto2_named_error(e.code)
            )
            uri = get_uri(path=path, camera_details=self.camera_details)
            self.problems.append(CameraDirectoryReadProblem(uri=uri, name=path, gp_code=e.code))
            if e.code in (gp.GP_ERROR_IO_USB_FIND, gp.GP_ERROR_BAD_PARAMETERS):
                logging.error("%s removed while listing files during scan", self.display_name)
                raise CameraError(CameraErrorCode.inaccessible)

        if files_in_folder:
            # Distinguish the file type for every file in the folder
            names = [name for name, value in files_in_folder]
            if '.nomedia' in names:
                # do nothing with this folder
                logging.debug("Ignoring %s because it contains a .nomedia file", path)
                return
            split_names = [os.path.splitext(name) for name in names]
            # Remove the period from the extension
            exts = [ext[1:] for name, ext in split_names]
            exts_lower = [ext.lower() for ext in exts]
            ext_types = [fileformats.extension_type(ext) for ext in exts_lower]

        for idx, name in enumerate(names):
            # Check to see if the process has received a command to terminate
            # or pause
            self.check_for_controller_directive()

            # Get the information we extracted above
            base_name = split_names[idx][0]
            ext = exts[idx]
            ext_lower = exts_lower[idx]
            ext_type = ext_types[idx]
            file_type = fileformats.file_type(ext_lower)

            if file_type is not None:
                # file is a photo or video
                file_is_unique = True
                try:
                    modification_time, size = self.camera.get_file_info(path, name)
                except gp.GPhoto2Error as e:
                    logging.error(
                        "Unable to access modification_time or size from %s on %s. Error: %s",
                        os.path.join(path, name), self.display_name, gphoto2_named_error(e.code)
                    )
                    modification_time, size = 0, 0
                    uri = get_uri(
                        full_file_name=os.path.join(path, name), camera_details=self.camera_details
                    )
                    self.problems.append(CameraFileInfoProblem(uri=uri, gp_code=e.code))
                else:
                    if size <= 0:
                        full_file_name = os.path.join(path, name)
                        logging.error(
                            "Zero length file %s will not be downloaded from %s",
                            full_file_name, self.display_name
                        )
                        uri = get_uri(
                            full_file_name=full_file_name, camera_details=self.camera_details
                        )
                        self.problems.append(FileZeroLengthProblem(name=name, uri=uri))

                if size > 0:
                    key = rpdfile.make_key(file_type, basedir)
                    self.file_type_counter[key] += 1
                    self.file_size_sum[key] += size

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
                        file_info = FileInfo(
                            path=path, modification_time=modification_time,
                            size=size, file_type=file_type, base_name=base_name,
                            ext_lower=ext_lower
                        )
                        metadata_details = CameraMetadataDetails(
                            path=path, name=name, size=size, extension=ext_lower,
                            mtime=modification_time, file_type=file_type
                        )
                        self._camera_file_names[name].append(file_info)
                        self._camera_folders_and_files.append([path, name])
                        self._camera_photos_videos_by_type[ext_type].append(metadata_details)
            else:
                # this file on the camera is not a photo or video
                if ext_lower in fileformats.AUDIO_EXTENSIONS:
                    self._camera_audio_files[base_name].append((path, ext))
                elif ext_lower in fileformats.VIDEO_THUMBNAIL_EXTENSIONS:
                    self._camera_video_thumbnails[base_name].append((path, ext))
                elif ext_lower == 'xmp':
                    self._camera_xmp_files[base_name].append((path, ext))
                elif ext_lower == 'log':
                    self._camera_log_files[base_name].append((path, ext))
                else:
                    logging.info(
                        "Ignoring unknown file %s on %s",
                        os.path.join(path, name), self.display_name
                    )
                    if self.prefs.warn_about_unknown_file(ext=ext):
                        uri = get_uri(
                            full_file_name=os.path.join(path, name),
                            camera_details=self.camera_details
                        )
                        self.problems.append(UnhandledFileProblem(name=name, uri=uri))
        folders = []
        try:
            for name, value in self.camera.camera.folder_list_folders(path, self.camera.context):
                if self.scan_preferences.scan_this_path(os.path.join(path, name)):
                    folders.append(name)
        except gp.GPhoto2Error as e:
            logging.error(
                "Unable to list folders on %s: %s", self.display_name,
                gphoto2_named_error(e.code)
            )
            uri = get_uri(path=path, camera_details=self.camera_details)
            self.problems.append(CameraDirectoryReadProblem(uri=uri, name=path, gp_code=e.code))
            if e.code in (gp.GP_ERROR_IO_USB_FIND, gp.GP_ERROR_BAD_PARAMETERS):
                logging.error("%s removed while listing folders during scan", self.display_name)
                raise CameraError(code=CameraErrorCode.inaccessible)

        # recurse over subfolders
        for name in folders:
            self.locate_files_on_camera(os.path.join(path, name), folder_identifier, basedir)

    def identify_camera_tz_and_sample_files(self) -> None:
        """
        Get sample metadata for photos and videos, and determine device timezone setting.
        """

        # do in place sort of jpegs, RAWs and videos by file size
        for files in self._camera_photos_videos_by_type.values():
            files.sort(key=operator.attrgetter('size'))

        # When determining how a camera reports modification time, extraction order
        # of preference is (1) heif, (2) jpeg, (3) RAW, and finally least preferred
        # is (4) video. However, if ignore_mdatatime_for_mtp_dng is set, ignore the RAW files

        if not self.ignore_mdatatime_for_mtp_dng:
            order = (FileExtension.heif, FileExtension.jpeg, FileExtension.raw, FileExtension.video)
        else:
            order = (FileExtension.heif, FileExtension.jpeg, FileExtension.video, FileExtension.raw)

        if not fileformats.heif_capable():
            order = order[1:]

        have_photos = len(self._camera_photos_videos_by_type[FileExtension.raw]) > 0 or \
                      len(self._camera_photos_videos_by_type[FileExtension.jpeg]) > 0
        if not have_photos and fileformats.heif_capable():
            have_photos = len(self._camera_photos_videos_by_type[FileExtension.heif]) > 0
        have_videos = len(self._camera_photos_videos_by_type[FileExtension.video]) > 0

        max_attempts = 5
        for ext_type in order:
            for file in self._camera_photos_videos_by_type[ext_type][:max_attempts]: \
                    # type: CameraMetadataDetails
                get_tz = self.device_timestamp_type == DeviceTimestampTZ.undetermined and not (
                    self.ignore_mdatatime_for_mtp_dng and ext_type == FileExtension.raw
                )
                get_sample_metadata = (
                    file.file_type == FileType.photo and not self.located_sample_photo
                ) or (
                    file.file_type == FileType.video and not self.located_sample_video
                )

                if get_tz or get_sample_metadata:
                    logging.info(
                        "Extracting sample %s metadata for %s",
                        file.file_type.name, self.camera_display_name
                    )
                    sample = self.sample_camera_metadata(
                        path=file.path, name=file.name, ext_type=ext_type, extension=file.extension,
                        modification_time=file.mtime, size=file.size, file_type=file.file_type
                    )
                    if get_tz:
                        self.determine_device_timestamp_tz(
                            sample.datetime, file.mtime, sample.determined_by
                        )
                need_sample_photo = not self.located_sample_photo and have_photos
                need_sample_video = not self.located_sample_video and have_videos
                if not (need_sample_photo or need_sample_video):
                    break

    def process_file(self) -> None:
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
                logging.info("Scanned {} files".format(self.files_scanned))

            if not self.download_from_camera:
                base_name, ext = os.path.splitext(self.file_name)
                ext = ext[1:].lower()
                file_type = fileformats.file_type(ext)

                # For next code block, see comment in
                # self.distinguish_non_camera_device_timestamp()
                # This only applies to files being scanned on the file system, not
                # cameras / phones.
                if file_type == FileType.photo and not self.located_sample_photo:
                    # this should never happen due to photos being prioritized over videos
                    # with respect to time zone determination
                    logging.error(
                        "Sample metadata not extracted from photo %s although it should have "
                        "been used to determine the device timezone", self.file_name
                    )
                elif file_type == FileType.video and not self.located_sample_video:
                    extension = fileformats.extract_extension(self.file_name)
                    self.sample_non_camera_metadata(
                        self.dir_name, self.file_name, file, FileExtension.video, extension,
                        file_type
                    )
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
                    # zero length files have already been filtered out
                    size = file_info.size
                    camera_file = CameraFile(name=self.file_name, size=size)
                else:
                    stat = os.stat(file)
                    size = stat.st_size
                    if size <= 0:
                        logging.error(
                            "Zero length file %s will not be downloaded from %s",
                            file, self.display_name
                        )
                        uri = get_uri(full_file_name=file)
                        self.problems.append(FileZeroLengthProblem(name=self.file_name, uri=uri))
                        return
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

                # check if a Magic Lantern LOG file is associated with the video
                log_file_full_name = self.get_log_file(base_name, camera_file)

                # check if an audio file is associated with the photo or video
                audio_file_full_name = self.get_audio_file(base_name, camera_file)

                # has the file been downloaded previously?
                # note: we should use the adjusted mtime, not the raw one
                adjusted_mtime = self.adjusted_mtime(modification_time)

                downloaded = self.downloaded.file_downloaded(
                    name=self.file_name, size=size, modification_time=adjusted_mtime
                )

                thumbnail_cache_status = ThumbnailCacheDiskStatus.unknown

                # Assign metadata time, if we have it
                # If we don't, it will be extracted when thumbnails are generated
                mdatatime = self.file_mdatatime.get(file, 0.0)

                ignore_mdatatime = self.ignore_mdatatime(ext=ext)

                if not mdatatime and self.prefs.use_thumbnail_cache and not ignore_mdatatime:
                    # Was there a thumbnail generated for the file?
                    # If so, get the metadata date time from that
                    get_thumbnail = self.thumbnail_cache.get_thumbnail_path(
                        full_file_name=file, mtime=adjusted_mtime,
                        size=size, camera_model=self.camera_model
                    )
                    thumbnail_cache_status = get_thumbnail.disk_status
                    if thumbnail_cache_status in (
                            ThumbnailCacheDiskStatus.found, ThumbnailCacheDiskStatus.failure):
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

                problem=None

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
                    log_file_full_name=log_file_full_name,
                    scan_id=self.worker_id,
                    file_type=file_type,
                    from_camera=self.download_from_camera,
                    camera_details=self.camera_details,
                    camera_memory_card_identifiers=camera_memory_card_identifiers,
                    never_read_mdatatime=ignore_mdatatime,
                    device_display_name=self.display_name,
                    device_uri=self.device.uri,
                    raw_exif_bytes=None,
                    exif_source=None,
                    problem=problem
                )

                self.file_batch.append(rpd_file)

                if (not self.prepared_sample_photo and
                        file == self.sample_photo_file_full_file_name and
                        self.located_sample_photo):
                    self.sample_photo = self.create_sample_rpdfile(
                        name=self.file_name,
                        path=self.dir_name,
                        size=size,
                        mdatatime=mdatatime,
                        file_type=FileType.photo,
                        mtime=modification_time,
                        ignore_mdatatime=ignore_mdatatime
                    )
                    self.sample_exif_bytes = None
                    if self.sample_photo_full_file_downloaded:
                        rpd_file.cache_full_file_name = self.sample_photo_extract_full_file_name
                    self.sample_photo_extract_full_file_name = None
                    self.prepared_sample_photo = True

                if (not self.prepared_sample_video and
                        file == self.sample_video_file_full_file_name and
                        self.located_sample_video):
                    self.sample_video = self.create_sample_rpdfile(
                        name=self.file_name,
                        path=self.dir_name,
                        size=size,
                        mdatatime=mdatatime,
                        file_type=FileType.video,
                        mtime=modification_time,
                        ignore_mdatatime=ignore_mdatatime
                    )
                    if self.sample_video_full_file_downloaded:
                        rpd_file.cache_full_file_name = self.sample_video_extract_full_file_name
                    self.sample_video_extract_full_file_name = None
                    self.prepared_sample_video = True

                if len(self.file_batch) == self.batch_size:
                    self.content = pickle.dumps(
                        ScanResults(
                            rpd_files=self.file_batch,
                            file_type_counter=self.file_type_counter,
                            file_size_sum=self.file_size_sum,
                            sample_photo=self.sample_photo,
                            sample_video=self.sample_video,
                            entire_video_required=self.entire_video_required,
                            entire_photo_required=self.entire_photo_required,
                        ),
                        pickle.HIGHEST_PROTOCOL
                    )
                    self.send_message_to_sink()
                    self.file_batch = []
                    self.sample_photo = None
                    self.sample_video = None

    def send_message_to_sink(self) -> None:
        try:
            logging.debug(
                "Sending %s scanned files from %s to sink", len(self.file_batch), self.display_name
            )
        except AttributeError:
            pass
        super().send_message_to_sink()

    def ignore_mdatatime(self, ext: str) -> bool:
        return self.ignore_mdatatime_for_mtp_dng and ext == 'dng'

    def create_sample_rpdfile(self, path: str,
                              name: str,
                              size: int,
                              mdatatime: float,
                              file_type: FileType,
                              mtime: float,
                              ignore_mdatatime: bool) -> Union[rpdfile.Photo, rpdfile.Video]:
        assert (
            self.sample_exif_source is not None and self.sample_photo_file_full_file_name or
            self.sample_video_file_full_file_name is not None
        )
        assert self.located_sample_photo or self.located_sample_video
        logging.info(
            "Successfully extracted sample %s metadata from %s", file_type.name, self.display_name
        )
        problem=None
        rpd_file = rpdfile.get_rpdfile(
            name=name,
            path=path,
            size=size,
            prev_full_name=None,
            prev_datetime=None,
            device_timestamp_type=self.device_timestamp_type,
            mtime=mtime,
            mdatatime=mdatatime,
            thumbnail_cache_status=ThumbnailCacheDiskStatus.unknown,
            thm_full_name=None,
            audio_file_full_name=None,
            xmp_file_full_name=None,
            log_file_full_name=None,
            scan_id=self.worker_id,
            file_type=file_type,
            from_camera=self.download_from_camera,
            camera_details=self.camera_details,
            camera_memory_card_identifiers=None,
            never_read_mdatatime=ignore_mdatatime,
            device_display_name=self.display_name,
            device_uri=self.device.uri,
            raw_exif_bytes=self.sample_exif_bytes,
            exif_source=self.sample_exif_source,
            problem=problem
        )
        if file_type == FileType.photo and self.download_from_camera \
                and self.sample_photo_source_is_extract:
            rpd_file.temp_sample_full_file_name = self.sample_photo_extract_full_file_name
            rpd_file.temp_sample_is_complete_file = self.sample_photo_full_file_downloaded

        elif file_type == FileType.video and self.download_from_camera:
            # relevant only when downloading from a camera
            rpd_file.temp_sample_full_file_name = self.sample_video_extract_full_file_name
            rpd_file.temp_sample_is_complete_file = self.sample_video_full_file_downloaded

        return rpd_file

    def download_chunk_from_camera(self, offset: int,
                                   size: int,
                                   extension: str,
                                   modification_time: int,
                                   path: str,
                                   name: str,
                                   file_type:FileType) -> Tuple[bool, Optional[datetime]]:

        dt = None
        entire_file_required = False
        # First try offset value, and if it fails, read the entire video
        # Reading the metadata on some videos will fail if the entire video
        # is not read, e.g. an iPhone 5 video
        temp_name = os.path.join(
            tempfile.gettempdir(), GenerateRandomFileName().name(extension=extension)
        )
        looped = False
        for chunk_size in (offset, size):
            if chunk_size == size:
                logging.debug(
                    "Downloading entire %s for metadata sample (%s)",
                    file_type.name, format_size_for_user(size)
                )
                if not looped:
                    entire_file_required = True
                    logging.debug(
                        "Unknown if entire %s is required to extract metadata and "
                        "thumbnails from %s, but setting it to required in case it is",
                        file_type.name, self.display_name
                    )

            mtime = int(self.adjusted_mtime(float(modification_time)))
            try:
                self.camera.save_file_chunk(path, name, chunk_size, temp_name, mtime)
            except CameraProblemEx as e:
                if e.code == CameraErrorCode.read:
                    uri = get_uri(
                        os.path.join(path, name), camera_details=self.camera_details
                    )
                    self.problems.append(
                        CameraFileReadProblem(uri=uri, name=name, gp_code=e.gp_code)
                    )
                elif e.code == CameraErrorCode.write:
                    uri = get_uri(path=os.path.dirname(temp_name))
                    self.problems.append(
                        FileWriteProblem(uri=uri, name=temp_name, exception=e.py_exception)
                    )
                else:
                    if e.gp_code in (gp.GP_ERROR_IO_USB_FIND, gp.GP_ERROR_BAD_PARAMETERS):
                        raise CameraError(code=CameraErrorCode.inaccessible)
            else:
                if file_type == FileType.video:
                    metadata = metadatavideo.MetaData(temp_name, self.et_process)
                    dt = metadata.date_time(missing=None, ignore_file_modify_date=True)
                    width = metadata.width(missing=None)
                    height = metadata.height(missing=None)
                    if dt is not None and width is not None and height is not None:
                        self.sample_video_full_file_downloaded = chunk_size == size
                        self.sample_video_extract_full_file_name = temp_name
                        self.sample_video_file_full_file_name = os.path.join(path, name)
                        if not entire_file_required:
                            logging.debug(
                                "Was able to extract video metadata from %s without "
                                "downloading the entire video", self.display_name
                            )
                        break
                else:
                    # photo using ExifTool
                    metadata = metadataexiftool.MetadataExiftool(
                        temp_name, self.et_process, file_type=file_type
                    )
                    dt = metadata.date_time(missing=None, ignore_file_modify_date=True)
                    if dt is not None:
                        self.sample_photo_full_file_downloaded = chunk_size == size
                        self.sample_photo_extract_full_file_name = temp_name
                        self.sample_photo_file_full_file_name = os.path.join(path, name)
                        self.sample_photo_source_is_extract = True
                        self.sample_exif_source = ExifSource.actual_file
                        if not entire_file_required:
                            logging.debug(
                                "Was able to extract photo metadata from %s without "
                                "downloading the entire photo", self.display_name
                            )
                        break

            entire_file_required = True
            logging.debug(
                "Entire %s is required to extract metadata and thumbnails from %s",
                file_type.name, self.display_name
            )
            looped = True
        return entire_file_required, dt

    def sample_camera_metadata(self, path: str,
                               name: str,
                               extension: str,
                               ext_type: FileExtension,
                               size: int,
                               modification_time: int,
                               file_type: FileType) -> SampleMetadata:
        """
        Extract sample metadata, including specifically datetime, from a photo or video on a camera
        Video files are special in that sometimes the entire file has to be read in order to extract
        its metadata.
        """

        dt = determined_by = None
        use_app1 = save_chunk = exif_extract = use_exiftool = False

        if ext_type == FileExtension.jpeg:
            determined_by = 'jpeg'
            if self.prefs.force_exiftool:
                exif_extract = True
                use_exiftool = True
                save_chunk = True
            else:
                if self.camera.can_fetch_thumbnails:
                    use_app1 = True
                else:
                    exif_extract = True

        elif ext_type == FileExtension.raw:
            determined_by = 'RAW'
            exif_extract = True
            use_exiftool = self.prefs.force_exiftool or fileformats.use_exiftool_on_photo(
                extension, preview_extraction_irrelevant=True
            )
            save_chunk = use_exiftool
        elif ext_type == FileExtension.video:
            determined_by = 'video'
            save_chunk = True
        elif ext_type == FileExtension.heif:
            determined_by = 'HEIF / HEIC'
            exif_extract = True
            use_exiftool = self.prefs.force_exiftool or fileformats.use_exiftool_on_photo(
                extension, preview_extraction_irrelevant=True
            )
            save_chunk = True

        if use_app1:
            try:
                self.sample_exif_bytes = self.camera.get_exif_extract_from_jpeg(path, name)
            except CameraProblemEx as e:
                uri = get_uri(
                    full_file_name=os.path.join(path, name), camera_details=self.camera_details
                )
                self.problems.append(CameraFileReadProblem(uri=uri, name=name, gp_code=e.gp_code))
                if e.gp_code in (gp.GP_ERROR_IO_USB_FIND, gp.GP_ERROR_BAD_PARAMETERS):
                    raise CameraError(code=CameraErrorCode.inaccessible)

            else:
                try:
                    with stdchannel_redirected(sys.stderr, os.devnull):
                        metadata = metadataphoto.MetaData(
                            app1_segment=self.sample_exif_bytes, et_process=self.et_process)
                except:
                    logging.warning(
                        "Scanner failed to load metadata from %s on %s",
                        name, self.camera.display_name
                    )
                    self.sample_exif_bytes = None
                    uri = get_uri(
                        full_file_name=os.path.join(path, name), camera_details=self.camera_details
                    )
                    self.problems.append(FileMetadataLoadProblem(uri=uri, name=name))
                else:
                    self.sample_exif_source = ExifSource.app1_segment
                    self.sample_photo_file_full_file_name = os.path.join(path, name)
                    dt = metadata.date_time(missing=None)  # type: datetime
        elif exif_extract:
            if use_exiftool:
                assert save_chunk
                offset = all_tags_offset_exiftool.get(extension)
                if offset is None:
                    max_size = 1024 ** 2 * 2  # approx 2 MB
                    offset = min(size, max_size)
                self.entire_photo_required, dt = self.download_chunk_from_camera(
                    offset=offset, size=size, extension=extension,
                    modification_time=modification_time, path=path, name=name,
                    file_type=FileType.photo
                )
            else:
                offset = all_tags_offset.get(extension)
                if offset is None:
                    offset = size
                offset = min(size, offset)
                try:
                    self.sample_exif_bytes = self.camera.get_exif_extract(path, name, offset)
                except CameraProblemEx as e:
                    self.sample_exif_bytes = None
                    if e.gp_code in (gp.GP_ERROR_IO_USB_FIND, gp.GP_ERROR_BAD_PARAMETERS):
                        raise CameraError(code=CameraErrorCode.inaccessible)

                if self.sample_exif_bytes is not None:
                    try:
                        with stdchannel_redirected(sys.stderr, os.devnull):
                            metadata = metadataphoto.MetaData(
                                raw_bytes=self.sample_exif_bytes, et_process=self.et_process
                            )
                    except Exception:
                        logging.warning(
                            "Scanner failed to load metadata from %s on %s",
                            name, self.camera.display_name
                        )
                        self.sample_exif_bytes = None
                        uri = get_uri(
                            full_file_name=os.path.join(path, name),
                            camera_details=self.camera_details
                        )
                        self.problems.append(FileMetadataLoadProblem(uri=uri, name=name))
                    else:
                        self.sample_exif_source = ExifSource.raw_bytes
                        self.sample_photo_file_full_file_name = os.path.join(path, name)
                        self.sample_photo_source_is_extract = False
                        dt = metadata.date_time(missing=None)  # type: datetime
        else:
            assert save_chunk
            # video
            offset = all_tags_offset_exiftool.get(extension)
            if offset is None:
                max_size =  1024**2 * 20  # approx 21 MB
                offset = min(size, max_size)
            self.entire_video_required, dt = self.download_chunk_from_camera(
                offset=offset, size=size, extension=extension,
                modification_time=modification_time, path=path, name=name,
                file_type=FileType.video
            )

        if dt is None:
            logging.warning(
                "Scanner failed to extract date time metadata from %s on %s",
                name, self.camera.display_name
            )
        else:
            self.file_mdatatime[os.path.join(path, name)] = float(dt.timestamp())
            if file_type == FileType.photo:
                self.located_sample_photo = True
            else:
                self.located_sample_video = True
            logging.info(
                "Extracted date time value %s for %s on %s", dt, name, self.camera_display_name
            )

        return SampleMetadata(dt, determined_by)

    def sample_non_camera_metadata(self, path: str,
                                   name: str,
                                   full_file_name: str,
                                   ext_type: FileExtension,
                                   extension: str,
                                   file_type: FileType) -> SampleMetadata:
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
        elif ext_type == FileExtension.heif:
            determined_by = 'HEIF / HEIC'

        if ext_type == FileExtension.video:
            metadata = metadatavideo.MetaData(
                full_file_name=full_file_name, et_process=self.et_process
            )
            self.sample_video_file_full_file_name = os.path.join(path, name)
            dt = metadata.date_time(missing=None)
        else:
            # photo - we don't care if jpeg or RAW
            if self.prefs.force_exiftool or fileformats.use_exiftool_on_photo(
                    extension, preview_extraction_irrelevant=True):

                metadata = metadataexiftool.MetadataExiftool(
                    full_file_name=full_file_name, et_process=self.et_process,
                    file_type=file_type
                )
                self.sample_exif_source = ExifSource.actual_file
                self.sample_photo_file_full_file_name = os.path.join(path, name)
                dt = metadata.date_time(missing=None)  # type: datetime
            else:
                try:
                    with stdchannel_redirected(sys.stderr, os.devnull):
                        metadata = metadataphoto.MetaData(
                            full_file_name=full_file_name, et_process=self.et_process
                        )
                except Exception:
                    logging.warning(
                        "Scanner failed to load metadata from %s on %s", name, self.display_name
                    )
                    uri = get_uri(full_file_name=full_file_name)
                    self.problems.append(FileMetadataLoadProblem(uri=uri, name=name))
                else:
                    self.sample_exif_source = ExifSource.actual_file
                    self.sample_photo_file_full_file_name = os.path.join(path, name)
                    dt = metadata.date_time(missing=None)  # type: datetime

        if dt is None:
            logging.warning(
                "Scanner failed to extract date time metadata from %s on %s",
                name, self.display_name
            )
        else:
            self.file_mdatatime[full_file_name] = dt.timestamp()
            if file_type == FileType.photo:
                self.located_sample_photo = True
            else:
                self.located_sample_video = True
        return SampleMetadata(dt, determined_by)

    def examine_sample_non_camera_file(self, dirname: str,
                                       name: str,
                                       full_file_name: str,
                                       ext_type: FileExtension,
                                       extension: str,
                                       file_type: FileType) -> bool:
        """
        Examine the the sample file to extract its metadata and compare it
        against the file system modification time
        """

        logging.debug("Examining sample %s", full_file_name)
        sample = self.sample_non_camera_metadata(
            dirname, name, full_file_name, ext_type, extension, file_type
        )
        if sample.datetime is not None:
            self.file_mdatatime[full_file_name] = sample.datetime.timestamp()
            try:
                mtime = os.path.getmtime(full_file_name)
            except (OSError, PermissionError) as e:
                logging.warning(
                    "Could not determine modification time for %s", full_file_name
                )
                uri = get_uri(full_file_name=full_file_name)
                self.problems.append(FsMetadataReadProblem(uri=uri, name=name, exception=e))
                return False
            else:
                # Located sample file: examine
                self.determine_device_timestamp_tz(sample.datetime, mtime, sample.determined_by)
                return True

    def distinguish_non_camera_device_timestamp(self, path: str) -> None:
        """
        Attempt to determine the device's approach to timezones when it
        store timestamps.
        When determining how this device reports modification time, file
        preference is (1) RAW, (2) jpeg, (3) heif / heic, and finally least
        preferred is (4) video -- a RAW is the least likely to be modified.

        NOTE: this creates a sample file for one type of file (RAW if present,
        if not, then jpeg, if jpeg also not present, then heif / heic, if that
        not present, then video). However if a photo is found, then still need
        to create a sample file for video.
        """

        logging.debug("Distinguishing approach to timestamp time zones on %s", self.display_name)

        self.device_timestamp_type = DeviceTimestampTZ.unknown

        max_attempts = 10
        raw_attempts = 0
        jpegs_heifs_and_videos = defaultdict(deque)

        # Only use HEIF files if we can read their metadata
        if fileformats.heif_capable():
            extensions = (
                FileExtension.raw, FileExtension.jpeg, FileExtension.heif, FileExtension.video
            )
        else:
            extensions = (FileExtension.raw, FileExtension.jpeg, FileExtension.video)
        non_raw_extensions = extensions[1:]

        for dir_name, name in self.walk_file_system(path):
            full_file_name = os.path.join(dir_name, name)
            extension = fileformats.extract_extension(full_file_name)
            ext_type = fileformats.extension_type(extension)
            if ext_type in extensions:
                file_type = fileformats.file_type(extension)
                if ext_type == FileExtension.raw and raw_attempts < max_attempts:
                    # examine right away
                    raw_attempts += 1
                    if self.examine_sample_non_camera_file(
                            dirname=dir_name, name=name, full_file_name=full_file_name,
                            ext_type=ext_type, extension=extension, file_type=file_type):
                        return
                else:
                    if len(jpegs_heifs_and_videos[ext_type]) < max_attempts:
                        jpegs_heifs_and_videos[ext_type].append(
                            (dir_name, name, full_file_name, extension)
                        )

                    if len(jpegs_heifs_and_videos[FileExtension.jpeg]) == max_attempts:
                        break

        # Couldn't locate sample raw file. Are left with up to max_attempts jpeg and video files
        for ext_type in non_raw_extensions:
            for dir_name, name, full_file_name, extension in jpegs_heifs_and_videos[ext_type]:
                file_type = fileformats.file_type(extension)
                if self.examine_sample_non_camera_file(
                        dirname=dir_name, name=name, full_file_name=full_file_name,
                        ext_type=ext_type, extension=extension, file_type=file_type):
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
            logging.debug(
                "Could not determine Device timezone setting for %s", self.display_name
            )
            self.device_timestamp_type = DeviceTimestampTZ.unknown

        # Must not compare exact times, as there can be a few seconds difference between
        # when a file was saved to the flash memory and when it was created in the
        # camera's memory. Allow for two minutes, to be safe.
        if datetime_roughly_equal(dt1=datetime.utcfromtimestamp(modification_time),
                                  dt2=mdatatime):
            logging.info(
                "Device timezone setting for %s is UTC, as indicated by %s file",
                self.display_name, determined_by
            )
            self.device_timestamp_type = DeviceTimestampTZ.is_utc
        elif datetime_roughly_equal(dt1=datetime.fromtimestamp(modification_time),
                                  dt2=mdatatime):
            logging.info(
                "Device timezone setting for %s is local time, as indicated by "
                "%s file", self.display_name, determined_by
            )
            self.device_timestamp_type = DeviceTimestampTZ.is_local
        else:
            logging.info(
                "Device timezone setting for %s is unknown, because the file "
                "modification time and file's time as recorded in metadata differ for "
                "sample file %s", self.display_name, determined_by
            )
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

    def _get_associate_file_from_camera(self,
                                        base_name: str,
                                        associate_files: DefaultDict,
                                        camera_file: CameraFile) -> Optional[str]:
        for path, ext in associate_files[base_name]:
            if path in self._camera_directories_for_file[camera_file]:
                return '{}.{}'.format(os.path.join(path, base_name),ext)
        return None

    def get_video_THM_file(self, base_name: str, camera_file: CameraFile) -> Optional[str]:
        """
        Checks to see if a thumbnail file (THM) with the same base name
        is in the same directory as the file.

        :param base_name: the file name without the extension
        :return: filename, including path, if found, else returns None
        """

        if self.download_from_camera:
            return self._get_associate_file_from_camera(
                base_name, self._camera_video_thumbnails, camera_file
            )
        else:
            return self._get_associate_file(base_name, fileformats.VIDEO_THUMBNAIL_EXTENSIONS)

    def get_audio_file(self, base_name: str, camera_file: CameraFile) -> Optional[str]:
        """
        Checks to see if an audio file with the same base name
        is in the same directory as the file.

        :param base_name: the file name without the extension
        :return: filename, including path, if found, else returns None
        """

        if self.download_from_camera:
            return self._get_associate_file_from_camera(
                base_name, self._camera_audio_files, camera_file
            )
        else:
            return self._get_associate_file(base_name, fileformats.AUDIO_EXTENSIONS)

    def get_log_file(self, base_name: str, camera_file: CameraFile) -> Optional[str]:
        """
        Checks to see if an XMP file with the same base name
        is in the same directory as the file.

        :param base_name: the file name without the extension
        :return: filename, including path, if found, else returns None
        """
        if self.download_from_camera:
            return self._get_associate_file_from_camera(
                base_name, self._camera_log_files, camera_file
            )
        else:
            return self._get_associate_file(base_name, ['log'])

    def get_xmp_file(self, base_name: str, camera_file: CameraFile) -> Optional[str]:
        """
        Checks to see if an XMP file with the same base name
        is in the same directory as the file.

        :param base_name: the file name without the extension
        :return: filename, including path, if found, else returns None
        """
        if self.download_from_camera:
            return self._get_associate_file_from_camera(
                base_name, self._camera_xmp_files, camera_file
            )
        else:
            return self._get_associate_file(base_name, ['xmp'])

    def _get_associate_file(self, base_name: str, extensions_to_check: List[str]) -> Optional[str]:
        """
        :param base_name: base name of file, without directory
        :param extensions_to_check: list of extensions in lower case without leading period
        :return: full file path if found, else None
        """

        full_file_name_no_ext = os.path.join(self.dir_name, base_name)
        for e in extensions_to_check:
            possible_file = '{}.{}'.format(full_file_name_no_ext, e)
            if os.path.exists(possible_file):
                return possible_file
            possible_file = '{}.{}'.format(full_file_name_no_ext, e.upper())
            if os.path.exists(possible_file):
                return possible_file
        return None

    def cleanup_pre_stop(self):
        self.exit_exiftool()
        if self.camera is not None:
            self.camera.free_camera()
        self.send_problems()

    @property
    def camera_details(self) -> Optional[CameraDetails]:
        return self._camera_details

    @camera_details.setter
    def camera_details(self, index: Optional[int]) -> None:
        """
        :param index: index into the storage details, for cameras with more than one
         storage
        """

        if not self.camera_storage_descriptions:
            self.camera_storage_descriptions = self.camera.get_storage_descriptions()

        if not self.camera_storage_descriptions:
            # Problem: there are no descriptions for the storage
            self._camera_details = CameraDetails(
                model=self.camera_model, port=self.camera_port,
                display_name=self.camera_display_name,
                is_mtp=self.is_mtp_device, storage_desc=[]
            )
            return

        index = index or 0

        self._camera_details = CameraDetails(
            model=self.camera_model, port=self.camera_port, display_name=self.camera_display_name,
            is_mtp=self.is_mtp_device, storage_desc=self.camera_storage_descriptions[index]
        )


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
    print(
        '% s Call to %s on line %s of %s from line %s of %s' % (
            datetime.now().ctime(), func_name, func_line_no, func_filename, caller_line_no,
            caller_filename)
    )

    for f in ('distinguish_non_camera_device_timestamp','determine_device_timestamp_tz'):
        if func_name.find(f) >= 0:
            # Trace into this function
            return trace_lines


if __name__ == "__main__":
    if os.getenv('RPD_SCAN_DEBUG') is not None:
        sys.settrace(trace_calls)
    scan = ScanWorker()


