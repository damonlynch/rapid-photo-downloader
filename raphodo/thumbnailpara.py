#!/usr/bin/env python3

# Copyright (C) 2011-2022 Damon Lynch <damonlynch@gmail.com>

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
Worker process to get thumbnails from Thumbnail or FDO cache, or
read thumbnail / file from the device being downloaded from.

For each device, there is one of these workers.

Sends thumbnail processing tasks to load balancer, which will in turn
send it to extractors.

By default, will set extractors to get the file's metadata time if
the metadata time is not already found in the rpd_file.
"""

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2011-2022, Damon Lynch"

try:
    using_injected = "profile" in dict(__builtins__)
except:
    using_injected = False
finally:
    if not using_injected:
        # use of line_profiler not detected
        def profile(func):
            def inner(*args, **kwargs):
                return func(*args, **kwargs)

            return inner


import os
import sys
import logging
import pickle
from collections import deque
from operator import attrgetter
from typing import Optional, Tuple, Set

import zmq
from PyQt5.QtGui import QImage
from PyQt5.QtCore import QSize
import psutil

from raphodo.rpdfile import RPDFile
from raphodo.interprocess import (
    WorkerInPublishPullPipeline,
    GenerateThumbnailsArguments,
    GenerateThumbnailsResults,
    ThumbnailExtractorArgument,
)
from raphodo.constants import (
    FileType,
    ThumbnailSize,
    ThumbnailCacheStatus,
    ThumbnailCacheDiskStatus,
    ExtractionTask,
    ExtractionProcessing,
    orientation_offset,
    thumbnail_offset,
    ThumbnailCacheOrigin,
    datetime_offset,
    datetime_offset_exiftool,
    thumbnail_offset_exiftool,
)
from raphodo.camera import Camera, CameraProblemEx, gphoto2_python_logging
from raphodo.cache import ThumbnailCacheSql, FdoCacheLarge
from raphodo.utilities import GenerateRandomFileName, create_temp_dir, CacheDirs
from raphodo.prefs.preferences import Preferences
from raphodo.rescan import RescanCamera
from raphodo.metadata.fileformats import use_exiftool_on_photo
from raphodo.heif import have_heif_module


def cache_dir_name(device_name: str) -> str:
    """Generate a directory name for a temporary file cache"""
    return "rpd-cache-{}-".format(device_name[:10].replace(" ", "_"))


def split_list(alist: list, wanted_parts=2):
    """
    Split list into smaller parts
    http://stackoverflow.com/questions/752308/split-list-into-smaller-lists
    :param alist: the list
    :param wanted_parts: how many lists it should be split into
    :return: the split lists
    """
    length = len(alist)
    return [
        alist[i * length // wanted_parts : (i + 1) * length // wanted_parts]
        for i in range(wanted_parts)
    ]


def split_indexes(length: int):
    """
    For the length of a list, return a list of indexes into it such
    that the indexes start with the middle item, then the middle item
    of the remaining two parts of the list, and so forth.

    Perhaps this algorithm could be optimized, as I did it myself. But
    hey it works and for now that's the main thing.

    :param length: the length of the list i.e. the number of indexes
     to be created
    :return: the list of indexes
    """
    l = list(range(length))
    n = []
    master = deque([l])
    while master:
        l1, l2 = split_list(master.popleft())
        if l2:
            n.append(l2[0])
            l2 = l2[1:]
        if l1:
            master.append(l1)
        if l2:
            master.append(l2)
    return n


def get_temporal_gaps_and_sequences(rpd_files, temporal_span):
    """
    For a sorted list of rpd_files, identify those rpd_files which are
    more than the temporal span away from each other, and those which are
    less than the temporal span from each other.

    Does not analyze clusters.

    For instance, you have 1000 photos from a day's photography. You
    sort them into a list ordered by time, earliest to latest. You then
    get all the photos that were take more than an hour after the
    previous photo, and those that were taken within an hour of the
    previous photo.
    .
    :param rpd_files: the sorted list of rpd_files, earliest first
    :param temporal_span: the time span that triggers a gap
    :return: the rpd_files that signify gaps, and all the rest of the
    rpd_files (which are in sequence)
    """
    if rpd_files:
        prev = rpd_files[0]
        gaps = [prev]
        sequences = []
        for i, rpd_file in enumerate(rpd_files[1:]):
            if rpd_file.modification_time - prev.modification_time > temporal_span:
                gaps.append(rpd_file)
            else:
                sequences.append(rpd_file)
            prev = rpd_file
        return (gaps, sequences)
    return None


class GetThumbnailFromCache:
    """
    Try to get thumbnail from Rapid Photo Downloader's thumbnail cache
    or from the FreeDesktop.org cache.
    """

    def __init__(self, use_thumbnail_cache: bool) -> None:

        if use_thumbnail_cache:
            self.thumbnail_cache = ThumbnailCacheSql(create_table_if_not_exists=False)
        else:
            self.thumbnail_cache = None

        # Access large size Freedesktop.org thumbnail cache
        self.fdo_cache_large = FdoCacheLarge()

        self.thumbnail_size_needed = QSize(ThumbnailSize.width, ThumbnailSize.height)

    def image_large_enough(self, size: QSize) -> bool:
        """Check if image is equal or bigger than thumbnail size."""
        return (
            size.width() >= self.thumbnail_size_needed.width()
            or size.height() >= self.thumbnail_size_needed.height()
        )

    def get_from_cache(
        self, rpd_file: RPDFile, use_thumbnail_cache: bool = True
    ) -> Tuple[ExtractionTask, bytes, str, ThumbnailCacheOrigin]:
        """
        Attempt to get a thumbnail for the file from the Rapid Photo Downloader
        thumbnail cache or from the FreeDesktop.org 256x256 thumbnail cache.

        :param rpd_file:
        :param use_thumbnail_cache: whether to use the
        :return:
        """

        task = ExtractionTask.undetermined
        thumbnail_bytes = None
        full_file_name_to_work_on = ""
        origin = None  # type: Optional[ThumbnailCacheOrigin]

        # Attempt to get thumbnail from Thumbnail Cache
        # (see cache.py for definitions of various caches)
        if self.thumbnail_cache is not None and use_thumbnail_cache:
            get_thumbnail = self.thumbnail_cache.get_thumbnail_path(
                full_file_name=rpd_file.full_file_name,
                mtime=rpd_file.modification_time,
                size=rpd_file.size,
                camera_model=rpd_file.camera_model,
            )
            rpd_file.thumbnail_cache_status = get_thumbnail.disk_status
            if get_thumbnail.disk_status != ThumbnailCacheDiskStatus.not_found:
                origin = ThumbnailCacheOrigin.thumbnail_cache
                task = ExtractionTask.bypass
                if get_thumbnail.disk_status == ThumbnailCacheDiskStatus.failure:
                    rpd_file.thumbnail_status = ThumbnailCacheStatus.generation_failed
                    rpd_file.thumbnail_cache_status = ThumbnailCacheDiskStatus.failure
                elif get_thumbnail.disk_status == ThumbnailCacheDiskStatus.found:
                    rpd_file.thumbnail_cache_status = ThumbnailCacheDiskStatus.found
                    if get_thumbnail.orientation_unknown:
                        rpd_file.thumbnail_status = (
                            ThumbnailCacheStatus.orientation_unknown
                        )
                    else:
                        rpd_file.thumbnail_status = ThumbnailCacheStatus.ready
                    with open(get_thumbnail.path, "rb") as thumbnail:
                        thumbnail_bytes = thumbnail.read()

        # Attempt to get thumbnail from large FDO Cache if not found in Thumbnail Cache
        # and it's not being downloaded directly from a camera (if it's from a camera,
        # it's not going to be in the FDO cache)

        if task == ExtractionTask.undetermined and not rpd_file.from_camera:
            get_thumbnail = self.fdo_cache_large.get_thumbnail(
                full_file_name=rpd_file.full_file_name,
                modification_time=rpd_file.modification_time,
                size=rpd_file.size,
                camera_model=rpd_file.camera_model,
            )
            if get_thumbnail.disk_status == ThumbnailCacheDiskStatus.found:
                rpd_file.fdo_thumbnail_256_name = get_thumbnail.path
                thumb = get_thumbnail.thumbnail  # type: QImage
                if thumb is not None:
                    if self.image_large_enough(thumb.size()):
                        task = ExtractionTask.load_file_directly
                        full_file_name_to_work_on = get_thumbnail.path
                        origin = ThumbnailCacheOrigin.fdo_cache
                        rpd_file.thumbnail_status = ThumbnailCacheStatus.fdo_256_ready

        return task, thumbnail_bytes, full_file_name_to_work_on, origin


# How much of the file should be read in from local disk and thus cached
# by they kernel
cached_read = dict(cr2=260 * 1024, dng=504 * 1024, nef=400 * 1024)


def preprocess_thumbnail_from_disk(
    rpd_file: RPDFile, processing: Set[ExtractionProcessing]
) -> ExtractionTask:
    """
    Determine how to get a thumbnail from a photo or video that is not on a camera
    (although it may have directly come from there during the download process)

    Does not return the name of the file to be worked on -- that's the responsibility
    of the method calling it.

    :param rpd_file: details about file from which to get thumbnail from
    :param processing: set that holds processing tasks for the extractors to perform
    :return: extraction task required
    """

    if rpd_file.file_type == FileType.photo:
        if rpd_file.is_heif():
            if have_heif_module:
                bytes_to_read = rpd_file.size
                if rpd_file.mdatatime:
                    task = ExtractionTask.load_heif_directly
                else:
                    task = ExtractionTask.load_heif_and_exif_directly
                processing.add(ExtractionProcessing.resize)
                # For now, do not orient, as it seems pyheif or libheif does that
                # automatically processing.add(ExtractionProcessing.orient)
            else:
                # We have no way to convert the file
                task = ExtractionTask.bypass
                bytes_to_read = 0
        elif rpd_file.is_tiff():
            available = psutil.virtual_memory().available
            if rpd_file.size <= available:
                bytes_to_read = rpd_file.size
                if rpd_file.mdatatime:
                    task = ExtractionTask.load_file_directly
                else:
                    task = ExtractionTask.load_file_and_exif_directly
                processing.add(ExtractionProcessing.resize)
            else:
                # Don't try to extract a thumbnail from
                # a file that is larger than available
                # memory
                task = ExtractionTask.bypass
                bytes_to_read = 0
        else:
            if rpd_file.is_jpeg() and rpd_file.from_camera and rpd_file.is_mtp_device:
                # jpeg photos from smartphones don't have embedded thumbnails
                task = ExtractionTask.load_file_and_exif_directly
                processing.add(ExtractionProcessing.resize)
            else:
                task = ExtractionTask.load_from_exif
            processing.add(ExtractionProcessing.orient)
            bytes_to_read = cached_read.get(rpd_file.extension, 400 * 1024)

        if bytes_to_read:
            if not rpd_file.download_full_file_name:
                try:
                    with open(rpd_file.full_file_name, "rb") as photo:
                        # Bring the file into the operating system's disk cache
                        photo.read(bytes_to_read)
                except FileNotFoundError:
                    logging.error(
                        "The download file %s does not exist",
                        rpd_file.download_full_file_name,
                    )
    else:
        # video
        if rpd_file.thm_full_name is not None:
            if not rpd_file.mdatatime:
                task = ExtractionTask.load_file_directly_metadata_from_secondary
                # It's the responsibility of the calling code to assign the
                # secondary_full_file_name
            else:
                task = ExtractionTask.load_file_directly
            processing.add(ExtractionProcessing.strip_bars_video)
            processing.add(ExtractionProcessing.add_film_strip)
        else:
            if rpd_file.mdatatime:
                task = ExtractionTask.extract_from_file
            else:
                task = ExtractionTask.extract_from_file_and_load_metadata

    return task


class GenerateThumbnails(WorkerInPublishPullPipeline):
    def __init__(self) -> None:
        self.random_file_name = GenerateRandomFileName()
        super().__init__("Thumbnails")

    def cache_full_size_file_from_camera(self, rpd_file: RPDFile) -> bool:
        """
        Get the file from the camera chunk by chunk and cache it.

        :return: True if operation succeeded, False otherwise
        """
        if rpd_file.file_type == FileType.photo:
            cache_dir = self.photo_cache_dir
        else:
            cache_dir = self.video_cache_dir
        cache_full_file_name = os.path.join(
            cache_dir, self.random_file_name.name(extension=rpd_file.extension)
        )
        try:
            self.camera.save_file_by_chunks(
                dir_name=rpd_file.path,
                file_name=rpd_file.name,
                size=rpd_file.size,
                dest_full_filename=cache_full_file_name,
                progress_callback=None,
                check_for_command=self.check_for_controller_directive,
                return_file_bytes=False,
            )
        except CameraProblemEx as e:
            # TODO report error
            return False
        else:
            rpd_file.cache_full_file_name = cache_full_file_name
            return True

    def cache_file_chunk_from_camera(self, rpd_file: RPDFile, offset: int) -> bool:
        if rpd_file.file_type == FileType.photo:
            cache_dir = self.photo_cache_dir
        else:
            cache_dir = self.video_cache_dir
        cache_full_file_name = os.path.join(
            cache_dir, self.random_file_name.name(extension=rpd_file.extension)
        )
        try:
            self.camera.save_file_chunk(
                dir_name=rpd_file.path,
                file_name=rpd_file.name,
                chunk_size_in_bytes=min(offset, rpd_file.size),
                dest_full_filename=cache_full_file_name,
            )
            rpd_file.temp_cache_full_file_chunk = cache_full_file_name
            return True
        except CameraProblemEx as e:
            # TODO problem reporting
            return False

    def extract_photo_video_from_camera(
        self,
        rpd_file: RPDFile,
        entire_file_required: bool,
        full_file_name_to_work_on,
        using_exiftool: bool,
    ) -> Tuple[ExtractionTask, str, bool]:
        """
        Extract part of a photo of video to be able to get the orientation
        and date time metadata, if and only if we know how much of the file
        is needed to get the thumbnail.

        Otherwise, download the entire photo or video from the camera to be able
        to generate the thumbnail and cache it.

        :param rpd_file: photo or video
        :param entire_file_required: whether we already know (from scanning) that
         the entire file is required
        :param full_file_name_to_work_on: file name and path of the photo or video
        :param using_exiftool: if all the metadata extraction is done using ExifTool
        :return: extraction task, full file name, and whether the full file name
         refers to a temporary file that should be deleted
        """

        task = ExtractionTask.undetermined
        file_to_work_on_is_temporary = False

        if rpd_file.is_mtp_device and rpd_file.file_type == FileType.video:
            entire_file_required = True

        if not entire_file_required:
            # For many photos videos, extract a small part of the file and use
            # that to get the metadata
            if using_exiftool:
                offset = thumbnail_offset_exiftool.get(rpd_file.extension)
            else:
                offset = thumbnail_offset.get(rpd_file.extension)
            if offset:
                if using_exiftool:
                    offset = max(
                        offset, datetime_offset_exiftool.get(rpd_file.extension)
                    )
                else:
                    offset = max(offset, datetime_offset.get(rpd_file.extension))

            if offset and self.cache_file_chunk_from_camera(rpd_file, offset):
                if rpd_file.file_type == FileType.photo:
                    task = ExtractionTask.load_from_bytes_metadata_from_temp_extract
                else:
                    task = ExtractionTask.extract_from_file_and_load_metadata
                    file_to_work_on_is_temporary = True
                full_file_name_to_work_on = rpd_file.temp_cache_full_file_chunk
        if task == ExtractionTask.undetermined:
            if self.cache_full_size_file_from_camera(rpd_file):
                task = ExtractionTask.extract_from_file_and_load_metadata
                full_file_name_to_work_on = rpd_file.cache_full_file_name
            else:
                # Failed to generate thumbnail
                task = ExtractionTask.bypass

        return task, full_file_name_to_work_on, file_to_work_on_is_temporary

    def do_work(self) -> None:
        try:
            self.generate_thumbnails()
        except SystemExit as e:
            sys.exit(e)
        except Exception:
            if hasattr(self, "device_name"):
                logging.error(
                    "Exception generating thumbnails for %s", self.device_name
                )
            else:
                logging.error("Exception generating thumbnails")
            logging.exception("Traceback:")

    def generate_thumbnails(self) -> None:
        self.camera = None
        arguments = pickle.loads(self.content)  # type: GenerateThumbnailsArguments
        self.device_name = arguments.name
        logging.info(
            "Generating %s thumbnails for %s", len(arguments.rpd_files), arguments.name
        )
        if arguments.log_gphoto2:
            self.gphoto2_logging = gphoto2_python_logging()

        self.frontend = self.context.socket(zmq.PUSH)
        self.frontend.connect("tcp://localhost:{}".format(arguments.frontend_port))

        self.prefs = Preferences()

        # Whether we must use ExifTool to read photo metadata
        force_exiftool = self.prefs.force_exiftool

        # If the entire photo or video is required to extract the thumbnail, which is
        # determined when extracting sample metadata from a photo or video during the
        # device scan
        entire_photo_required = arguments.entire_photo_required
        entire_video_required = arguments.entire_video_required

        # Access and generate Rapid Photo Downloader thumbnail cache
        use_thumbnail_cache = self.prefs.use_thumbnail_cache

        thumbnail_caches = GetThumbnailFromCache(
            use_thumbnail_cache=use_thumbnail_cache
        )

        photo_cache_dir = video_cache_dir = None
        cache_file_from_camera = force_exiftool

        rpd_files = arguments.rpd_files

        # with open('tests/thumbnail_data_medium_no_tiff', 'wb') as f:
        #     pickle.dump(rpd_files, f)

        # Must sort files by modification time prior to temporal analysis needed to figure out
        # which thumbnails to prioritize
        rpd_files = sorted(rpd_files, key=attrgetter("modification_time"))

        time_span = arguments.proximity_seconds

        rpd_files2 = []

        if rpd_files:
            gaps, sequences = get_temporal_gaps_and_sequences(rpd_files, time_span)

            rpd_files2.extend(gaps)

            indexes = split_indexes(len(sequences))
            rpd_files2.extend([sequences[idx] for idx in indexes])

        assert len(rpd_files) == len(rpd_files2)
        rpd_files = rpd_files2

        if arguments.camera is not None:
            self.camera = Camera(
                model=arguments.camera,
                port=arguments.port,
                is_mtp_device=arguments.is_mtp_device,
                specific_folders=self.prefs.folders_to_scan,
            )

            if not self.camera.camera_initialized:
                # There is nothing to do here: exit!
                logging.debug(
                    "Prematurely exiting thumbnail generation due to lack of access to "
                    "camera %s",
                    arguments.camera,
                )
                self.content = pickle.dumps(
                    GenerateThumbnailsResults(
                        scan_id=arguments.scan_id,
                        camera_removed=True,
                    ),
                    pickle.HIGHEST_PROTOCOL,
                )
                self.send_message_to_sink()
                self.disconnect_logging()
                self.send_finished_command()
                sys.exit(0)

            if not cache_file_from_camera:
                for rpd_file in rpd_files:
                    if use_exiftool_on_photo(
                        rpd_file.extension, preview_extraction_irrelevant=False
                    ):
                        cache_file_from_camera = True
                        break

            must_make_cache_dirs = (
                not self.camera.can_fetch_thumbnails or cache_file_from_camera
            )

            if (
                must_make_cache_dirs
                or arguments.need_video_cache_dir
                or arguments.need_photo_cache_dir
            ):
                # If downloading complete copy of the files to
                # generate previews, then may as well cache them to speed up
                # the download process
                self.photo_cache_dir = create_temp_dir(
                    folder=arguments.cache_dirs.photo_cache_dir,
                    prefix=cache_dir_name(self.device_name),
                )
                self.video_cache_dir = create_temp_dir(
                    folder=arguments.cache_dirs.video_cache_dir,
                    prefix=cache_dir_name(self.device_name),
                )
                cache_dirs = CacheDirs(self.photo_cache_dir, self.video_cache_dir)
                self.content = pickle.dumps(
                    GenerateThumbnailsResults(
                        scan_id=arguments.scan_id, cache_dirs=cache_dirs
                    ),
                    pickle.HIGHEST_PROTOCOL,
                )
                self.send_message_to_sink()

        from_thumb_cache = 0
        from_fdo_cache = 0

        if self.camera:
            rescan = RescanCamera(camera=self.camera, prefs=self.prefs)
            rescan.rescan_camera(rpd_files)
            rpd_files = rescan.rpd_files
            if rescan.missing_rpd_files:
                logging.error(
                    "%s files could not be relocated on %s",
                    len(rescan.missing_rpd_files),
                    self.camera.display_name,
                )
                for rpd_file in rescan.missing_rpd_files:  # type: RPDFile
                    self.content = pickle.dumps(
                        GenerateThumbnailsResults(
                            rpd_file=rpd_file, thumbnail_bytes=None
                        ),
                        pickle.HIGHEST_PROTOCOL,
                    )
                    self.send_message_to_sink()

        for rpd_file in rpd_files:  # type: RPDFile
            # Check to see if the process has received a command
            self.check_for_controller_directive()

            exif_buffer = None
            file_to_work_on_is_temporary = False
            secondary_full_file_name = ""
            processing = set()  # type: Set[ExtractionProcessing]

            # Attempt to get thumbnail from Thumbnail Cache
            # (see cache.py for definitions of various caches)

            cache_search = thumbnail_caches.get_from_cache(rpd_file)
            task, thumbnail_bytes, full_file_name_to_work_on, origin = cache_search
            if task != ExtractionTask.undetermined:
                if origin == ThumbnailCacheOrigin.thumbnail_cache:
                    from_thumb_cache += 1
                else:
                    assert origin == ThumbnailCacheOrigin.fdo_cache
                    logging.debug(
                        "Thumbnail for %s found in large FDO cache",
                        rpd_file.full_file_name,
                    )
                    from_fdo_cache += 1
                    processing.add(ExtractionProcessing.resize)
                    if not rpd_file.mdatatime:
                        # Since we're extracting the thumbnail from the FDO cache,
                        # need to grab its metadata too.
                        # Reassign the task
                        task = ExtractionTask.load_file_directly_metadata_from_secondary
                        # It's not being downloaded from a camera, so nothing
                        # special to do except assign the name of the file from which
                        # to extract the metadata
                        secondary_full_file_name = rpd_file.full_file_name
                        logging.debug(
                            "Although thumbnail found in the cache, tasked to extract "
                            "file time recorded in metadata from %s",
                            secondary_full_file_name,
                        )
            if task == ExtractionTask.undetermined:
                # Thumbnail was not found in any cache: extract it
                if self.camera:  # type: Camera
                    if rpd_file.file_type == FileType.photo:
                        if rpd_file.is_heif():
                            # Load HEIF / HEIC using entire file.
                            # We are assuming that there is no tool to extract a
                            # preview image from an HEIF / HEIC, or the file simply
                            # does not have one to extract.
                            if self.cache_full_size_file_from_camera(rpd_file):
                                task = ExtractionTask.load_heif_and_exif_directly
                                processing.add(ExtractionProcessing.resize)
                                full_file_name_to_work_on = (
                                    rpd_file.cache_full_file_name
                                )
                                # For now, do not orient, as it seems pyheif or libheif does
                                # that automatically.
                                # processing.add(ExtractionProcessing.orient)

                        elif self.camera.can_fetch_thumbnails:
                            task = ExtractionTask.load_from_bytes
                            if rpd_file.is_jpeg_type():
                                # gPhoto2 knows how to get jpeg thumbnails
                                try:
                                    thumbnail_bytes = self.camera.get_thumbnail(
                                        rpd_file.path, rpd_file.name
                                    )
                                except CameraProblemEx as e:
                                    # TODO handle error?
                                    thumbnail_bytes = None
                            else:

                                if force_exiftool or use_exiftool_on_photo(
                                    rpd_file.extension,
                                    preview_extraction_irrelevant=False,
                                ):
                                    (
                                        task,
                                        full_file_name_to_work_on,
                                        file_to_work_on_is_temporary,
                                    ) = self.extract_photo_video_from_camera(
                                        rpd_file,
                                        entire_photo_required,
                                        full_file_name_to_work_on,
                                        True,
                                    )
                                    if (
                                        task
                                        == ExtractionTask.load_from_bytes_metadata_from_temp_extract
                                    ):
                                        secondary_full_file_name = (
                                            full_file_name_to_work_on
                                        )
                                        file_to_work_on_is_temporary = False

                                else:
                                    # gPhoto2 does not know how to get RAW thumbnails,
                                    # so we do that part ourselves
                                    if rpd_file.extension == "crw":
                                        # Could cache this file, since reading its
                                        # entirety But does anyone download a CRW file
                                        # from the camera these days?!
                                        bytes_to_read = rpd_file.size
                                    else:
                                        bytes_to_read = min(
                                            rpd_file.size,
                                            orientation_offset.get(
                                                rpd_file.extension, 500
                                            ),
                                        )
                                    exif_buffer = self.camera.get_exif_extract(
                                        rpd_file.path, rpd_file.name, bytes_to_read
                                    )
                                try:
                                    thumbnail_bytes = self.camera.get_thumbnail(
                                        rpd_file.path, rpd_file.name
                                    )
                                except CameraProblemEx as e:
                                    # TODO report error
                                    thumbnail_bytes = None
                            processing.add(ExtractionProcessing.strip_bars_photo)
                            processing.add(ExtractionProcessing.orient)
                        else:
                            # Many (all?) jpegs from phones don't include jpeg previews,
                            # so need to render from the entire jpeg itself. Slow!

                            # For raw, extract merely a part of phone's raw format, and
                            # try to extract the jpeg preview from it (which probably
                            # doesn't exist!). This is fast.

                            if not rpd_file.is_jpeg():
                                bytes_to_read = thumbnail_offset.get(rpd_file.extension)
                                if bytes_to_read:
                                    exif_buffer = self.camera.get_exif_extract(
                                        rpd_file.path, rpd_file.name, bytes_to_read
                                    )
                                    task = ExtractionTask.load_from_exif_buffer
                                    processing.add(ExtractionProcessing.orient)
                            if (
                                task == ExtractionTask.undetermined
                                and self.cache_full_size_file_from_camera(rpd_file)
                            ):
                                if rpd_file.is_jpeg():
                                    task = ExtractionTask.load_file_and_exif_directly
                                    processing.add(ExtractionProcessing.resize)
                                    processing.add(ExtractionProcessing.orient)
                                else:
                                    task = ExtractionTask.load_from_exif
                                    processing.add(ExtractionProcessing.resize)
                                    processing.add(ExtractionProcessing.orient)
                                full_file_name_to_work_on = (
                                    rpd_file.cache_full_file_name
                                )
                            else:
                                # Failed to generate thumbnail
                                task = ExtractionTask.bypass
                    else:
                        # video from camera
                        if rpd_file.thm_full_name is not None:
                            # Fortunately, we have a special video thumbnail file
                            # Still need to get metadata time, however.

                            if entire_video_required:
                                offset = rpd_file.size
                            else:
                                offset = datetime_offset.get(rpd_file.extension)
                                # If there is no offset, there is no point trying to
                                # extract the metadata time from part of the video. It's
                                # not ideal, but if this is from a camera on which there
                                # were any other files we can assume we've got a
                                # somewhat accurate date time for it from the
                                # modification time. The only exception is if the video
                                # file is not that big, in which case it's worth reading
                                # in its entirety:
                                if offset is None and rpd_file.size < 4000000:
                                    offset = rpd_file.size

                            if rpd_file.mdatatime or not offset:
                                task = ExtractionTask.load_from_bytes
                            elif self.cache_file_chunk_from_camera(rpd_file, offset):
                                task = (
                                    ExtractionTask.load_from_bytes_metadata_from_temp_extract
                                )
                                secondary_full_file_name = (
                                    rpd_file.temp_cache_full_file_chunk
                                )
                            else:
                                # For some reason was unable to download part of the
                                # video file
                                task = ExtractionTask.load_from_bytes

                            try:
                                thumbnail_bytes = self.camera.get_THM_file(
                                    rpd_file.thm_full_name
                                )
                            except CameraProblemEx as e:
                                # TODO report error
                                thumbnail_bytes = None
                            processing.add(ExtractionProcessing.strip_bars_video)
                            processing.add(ExtractionProcessing.add_film_strip)
                        else:
                            (
                                task,
                                full_file_name_to_work_on,
                                file_to_work_on_is_temporary,
                            ) = self.extract_photo_video_from_camera(
                                rpd_file,
                                entire_video_required,
                                full_file_name_to_work_on,
                                False,
                            )
                else:
                    # File is not on a camera
                    task = preprocess_thumbnail_from_disk(
                        rpd_file=rpd_file, processing=processing
                    )
                    if task != ExtractionTask.bypass:
                        if rpd_file.thm_full_name is not None:
                            full_file_name_to_work_on = rpd_file.thm_full_name
                            if (
                                task
                                == ExtractionTask.load_file_directly_metadata_from_secondary
                            ):
                                secondary_full_file_name = rpd_file.full_file_name
                        else:
                            full_file_name_to_work_on = rpd_file.full_file_name

            if task == ExtractionTask.bypass:
                self.content = pickle.dumps(
                    GenerateThumbnailsResults(
                        rpd_file=rpd_file, thumbnail_bytes=thumbnail_bytes
                    ),
                    pickle.HIGHEST_PROTOCOL,
                )
                self.send_message_to_sink()

            elif task != ExtractionTask.undetermined:
                # Send data to load balancer, which will send to one of its
                # workers

                self.content = pickle.dumps(
                    ThumbnailExtractorArgument(
                        rpd_file=rpd_file,
                        task=task,
                        processing=processing,
                        full_file_name_to_work_on=full_file_name_to_work_on,
                        secondary_full_file_name=secondary_full_file_name,
                        exif_buffer=exif_buffer,
                        thumbnail_bytes=thumbnail_bytes,
                        use_thumbnail_cache=use_thumbnail_cache,
                        file_to_work_on_is_temporary=file_to_work_on_is_temporary,
                        write_fdo_thumbnail=False,
                        send_thumb_to_main=True,
                        force_exiftool=force_exiftool,
                    ),
                    pickle.HIGHEST_PROTOCOL,
                )
                self.frontend.send_multipart([b"data", self.content])

        if arguments.camera:
            self.camera.free_camera()
            # Delete our temporary cache directories if they are empty
            if photo_cache_dir is not None:
                if not os.listdir(self.photo_cache_dir):
                    os.rmdir(self.photo_cache_dir)
            if video_cache_dir is not None:
                if not os.listdir(self.video_cache_dir):
                    os.rmdir(self.video_cache_dir)

        logging.debug(
            "Finished phase 1 of thumbnail generation for %s", self.device_name
        )
        if from_thumb_cache:
            logging.info(
                "{} of {} thumbnails for {} came from thumbnail cache".format(
                    from_thumb_cache, len(rpd_files), self.device_name
                )
            )
        if from_fdo_cache:
            logging.info(
                "{} of {} thumbnails of for {} came from Free Desktop cache".format(
                    from_fdo_cache, len(rpd_files), self.device_name
                )
            )

        self.disconnect_logging()
        self.send_finished_command()

    def cleanup_pre_stop(self):
        if self.camera is not None:
            self.camera.free_camera()


if __name__ == "__main__":
    generate_thumbnails = GenerateThumbnails()
