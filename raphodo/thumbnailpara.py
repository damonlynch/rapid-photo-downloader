# SPDX-FileCopyrightText: Copyright 2011-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Worker process to get thumbnails from Thumbnail or FDO cache, or
read thumbnail / file from the device being downloaded from.

For each device, there is one of these workers.

Sends thumbnail processing tasks to load balancer, which will in turn
send it to extractors.

By default, will set extractors to get the file's metadata time if
the metadata time is not already found in the rpd_file.
"""

# try:
#     using_injected = "profile" in dict(__builtins__)
# except Exception:
#     using_injected = False
# finally:
#     if not using_injected:
#         # use of line_profiler not detected
#         def profile(func):
#             def inner(*args, **kwargs):
#                 return func(*args, **kwargs)
#
#             return inner

import logging
import os
import pickle
import sys
from collections import Counter, deque
from operator import attrgetter
from typing import NamedTuple

import psutil
import zmq
from PyQt5.QtCore import QSize
from PyQt5.QtGui import QImage

from raphodo.cache import FdoCacheLarge, ThumbnailCacheSql
from raphodo.camera import Camera, CameraProblemEx, gphoto2_python_logging
from raphodo.constants import (
    ExtractionProcessing,
    ExtractionTask,
    FileType,
    ThumbnailCacheDiskStatus,
    ThumbnailCacheOrigin,
    ThumbnailCacheStatus,
    ThumbnailSize,
    datetime_offset,
    datetime_offset_exiftool,
    orientation_offset,
    thumbnail_offset,
    thumbnail_offset_exiftool,
)
from raphodo.heif import have_heif_module
from raphodo.interprocess import (
    GenerateThumbnailsArguments,
    GenerateThumbnailsResults,
    ThumbnailExtractorArgument,
    WorkerInPublishPullPipeline,
)
from raphodo.metadata.fileformats import use_exiftool_on_photo
from raphodo.prefs.preferences import Preferences
from raphodo.rescan import RescanCamera
from raphodo.rpdfile import RPDFile
from raphodo.tools.utilities import CacheDirs, GenerateRandomFileName, create_temp_dir


class ThumbnailCacheSearch(NamedTuple):
    task: ExtractionTask
    thumbnail_bytes: bytes
    full_file_name_to_work_on: str
    origin: ThumbnailCacheOrigin


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
    it works, and for now that's the main thing.

    :param length: The length of the list i.e., the number of indexes
     to be created
    :return: the list of indexes
    """

    n = []
    master = deque([list(range(length))])
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
    get all the photos that were taken more than an hour after the
    previous photo, and those that were taken within an hour of the
    previous photo.

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
    ) -> ThumbnailCacheSearch:
        """
        Attempt to get a thumbnail for the file from the Rapid Photo Downloader
        thumbnail cache or from the FreeDesktop.org 256x256 thumbnail cache.
        """

        task = ExtractionTask.undetermined
        thumbnail_bytes: bytes | None = None
        full_file_name_to_work_on = ""
        origin: ThumbnailCacheOrigin | None = None

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
                thumb: QImage = get_thumbnail.thumbnail
                if thumb is not None and self.image_large_enough(thumb.size()):
                    task = ExtractionTask.load_file_directly
                    full_file_name_to_work_on = get_thumbnail.path
                    origin = ThumbnailCacheOrigin.fdo_cache
                    rpd_file.thumbnail_status = ThumbnailCacheStatus.fdo_256_ready

        return ThumbnailCacheSearch(
            task=task,
            thumbnail_bytes=thumbnail_bytes,
            full_file_name_to_work_on=full_file_name_to_work_on,
            origin=origin,
        )


# How much of the file should be read in from local disk and thus cached
# by they kernel
cached_read = dict(cr2=260 * 1024, dng=504 * 1024, nef=400 * 1024)


def preprocess_thumbnail_from_disk(
    rpd_file: RPDFile, processing: set[ExtractionProcessing]
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

        if bytes_to_read and not rpd_file.download_full_file_name:
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
                # It's the responsibility of the calling code to assign to
                # self.secondary_full_file_name
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
        self.counter = Counter()

        self.camera: Camera | None = None

        self.exif_buffer: bytearray | None = None
        self.file_to_work_on_is_temporary: bool = False
        self.secondary_full_file_name: str = ""
        self.processing: set[ExtractionProcessing] = set()

        self.task: ExtractionTask | None = None
        self.thumbnail_bytes: bytes | None = None
        self.full_file_name_to_work_on: str = ""
        self.origin: ThumbnailCacheOrigin | None = None

        self.rpd_file: RPDFile | None = None

        self.force_exiftool: bool = False

        self.entire_photo_required: bool | None = None
        self.entire_video_required: bool | None = None

        self.photo_cache_dir: str | None = None
        self.video_cache_dir: str | None = None

        super().__init__("Thumbnails")

    def cache_full_size_file_from_camera(self) -> bool:
        """
        Get the file from the camera chunk by chunk and cache it.

        :return: True if operation succeeded, False otherwise
        """
        if self.rpd_file.file_type == FileType.photo:
            cache_dir = self.photo_cache_dir
        else:
            cache_dir = self.video_cache_dir
        cache_full_file_name = os.path.join(
            cache_dir, self.random_file_name.name(extension=self.rpd_file.extension)
        )
        try:
            self.camera.save_file_by_chunks(
                dir_name=self.rpd_file.path,
                file_name=self.rpd_file.name,
                size=self.rpd_file.size,
                dest_full_filename=cache_full_file_name,
                progress_callback=None,
                check_for_command=self.check_for_controller_directive,
                return_file_bytes=False,
            )
        except CameraProblemEx:
            # TODO report error
            return False
        else:
            self.rpd_file.cache_full_file_name = cache_full_file_name
            return True

    def cache_file_chunk_from_camera(self, offset: int) -> bool:
        if self.rpd_file.file_type == FileType.photo:
            cache_dir = self.photo_cache_dir
        else:
            cache_dir = self.video_cache_dir
        cache_full_file_name = os.path.join(
            cache_dir, self.random_file_name.name(extension=self.rpd_file.extension)
        )
        try:
            self.camera.save_file_chunk(
                dir_name=self.rpd_file.path,
                file_name=self.rpd_file.name,
                chunk_size_in_bytes=min(offset, self.rpd_file.size),
                dest_full_filename=cache_full_file_name,
            )
            self.rpd_file.temp_cache_full_file_chunk = cache_full_file_name
            return True
        except CameraProblemEx:
            # TODO problem reporting
            return False

    def extract_photo_video_from_camera_partial(self, using_exiftool: bool) -> None:
        # For many photos videos, extract a small part of the file and use
        # that to get the metadata
        if using_exiftool:
            offset = thumbnail_offset_exiftool.get(self.rpd_file.extension)
        else:
            offset = thumbnail_offset.get(self.rpd_file.extension)
        if offset:
            if using_exiftool:
                offset = max(
                    offset, datetime_offset_exiftool.get(self.rpd_file.extension)
                )
            else:
                offset = max(offset, datetime_offset.get(self.rpd_file.extension))

        if offset and self.cache_file_chunk_from_camera(offset):
            if self.rpd_file.file_type == FileType.photo:
                self.task = ExtractionTask.load_from_bytes_metadata_from_temp_extract
            else:
                self.task = ExtractionTask.extract_from_file_and_load_metadata
                self.file_to_work_on_is_temporary = True
            self.full_file_name_to_work_on = self.rpd_file.temp_cache_full_file_chunk

    def extract_photo_video_from_camera(
        self, entire_file_required: bool, using_exiftool: bool
    ) -> None:
        """
        Extract part of a photo of video to be able to get the orientation
        and date time metadata, if and only if we know how much of the file
        is needed to get the thumbnail.

        Otherwise, download the entire photo or video from the camera to be able
        to generate the thumbnail and cache it.

        :param entire_file_required: whether we already know (from scanning) that
         the entire file is required
        :param using_exiftool: if all the metadata extraction is done using ExifTool
        """

        self.task = ExtractionTask.undetermined
        self.file_to_work_on_is_temporary = False

        if self.rpd_file.is_mtp_device and self.rpd_file.file_type == FileType.video:
            entire_file_required = True

        if not entire_file_required:
            self.extract_photo_video_from_camera_partial(using_exiftool=using_exiftool)

        if self.task == ExtractionTask.undetermined:
            if self.cache_full_size_file_from_camera():
                self.task = ExtractionTask.extract_from_file_and_load_metadata
                self.full_file_name_to_work_on = self.rpd_file.cache_full_file_name
            else:
                # Failed to generate thumbnail
                self.task = ExtractionTask.bypass

    def prioritise_thumbnail_order(
        self, arguments: GenerateThumbnailsArguments
    ) -> list[RPDFile]:
        """
        Determine files to prioritise generating thumbnails for based on the time they
        were taken

        :param arguments: the arguments passed to this process
        :return: list of RPDFile sorted by priority to generate thumbnails
        """

        rpd_files = arguments.rpd_files

        # Must sort files by modification time prior to temporal analysis needed to
        # figure out which thumbnails to prioritize
        rpd_files = sorted(rpd_files, key=attrgetter("modification_time"))

        time_span = arguments.proximity_seconds

        rpd_files2 = []

        if rpd_files:
            gaps, sequences = get_temporal_gaps_and_sequences(rpd_files, time_span)

            rpd_files2.extend(gaps)

            indexes = split_indexes(len(sequences))
            rpd_files2.extend([sequences[idx] for idx in indexes])

        assert len(rpd_files) == len(rpd_files2)
        return rpd_files2

    def prepare_for_camera_thumbnail_extraction(
        self,
        arguments: GenerateThumbnailsArguments,
        cache_file_from_camera: bool,
        rpd_files: list[RPDFile],
    ) -> list[RPDFile]:
        """
        Prepare the camera for thumbnail extraction

        :param arguments: the arguments passed to this process
        :param cache_file_from_camera: Whether to cache files from camera  on the
         file system
        :param rpd_files: the list of RPDFiles to generate thumbnails for, already
         sorted by priority
        :return: list of RPDFiles to generate thumbnails for
        """

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

        rescan = RescanCamera(camera=self.camera, prefs=self.prefs)
        rescan.rescan_camera(rpd_files)
        if rescan.missing_rpd_files:
            logging.error(
                "%s files could not be relocated on %s",
                len(rescan.missing_rpd_files),
                self.camera.display_name,
            )
            for rpd_file in rescan.missing_rpd_files:
                self.content = pickle.dumps(
                    GenerateThumbnailsResults(rpd_file=rpd_file, thumbnail_bytes=None),
                    pickle.HIGHEST_PROTOCOL,
                )
                self.send_message_to_sink()

        return rescan.rpd_files

    def task_cache_extract(self) -> None:
        if self.origin == ThumbnailCacheOrigin.thumbnail_cache:
            self.counter["thumb_cache"] += 1
        else:
            assert self.origin == ThumbnailCacheOrigin.fdo_cache
            logging.debug(
                "Thumbnail for %s found in large FDO cache",
                self.rpd_file.full_file_name,
            )
            self.counter["fdo_cache"] += 1
            self.processing.add(ExtractionProcessing.resize)
            if not self.rpd_file.mdatatime:
                # Since we're extracting the thumbnail from the FDO cache,
                # need to grab its metadata too.
                # Reassign the task
                self.task = ExtractionTask.load_file_directly_metadata_from_secondary
                # It's not being downloaded from a camera, so nothing
                # special to do except assign the name of the file from which
                # to extract the metadata
                self.secondary_full_file_name = self.rpd_file.full_file_name
                logging.debug(
                    "Although thumbnail found in the cache, tasked to extract "
                    "file time recorded in metadata from %s",
                    self.secondary_full_file_name,
                )

    def task_camera_extract_photo_heif(self) -> None:
        # Load HEIF / HEIC using the entire file.
        # We are assuming that there is no tool to extract a
        # preview image from an HEIF / HEIC, or the file simply
        # does not have one to extract.
        if self.cache_full_size_file_from_camera():
            self.task = ExtractionTask.load_heif_and_exif_directly
            self.processing.add(ExtractionProcessing.resize)
            self.full_file_name_to_work_on = self.rpd_file.cache_full_file_name

            # For now, do not orient, as pyheif or libheif do that automatically.

    def task_camera_extract_photo_fetch_thumbnail_jpeg(self) -> None:
        # gPhoto2 knows how to get jpeg thumbnails
        try:
            self.thumbnail_bytes = self.camera.get_thumbnail(
                self.rpd_file.path, self.rpd_file.name
            )
        except CameraProblemEx:
            # TODO handle error?
            self.thumbnail_bytes = None

    def task_camera_extract_photo_fetch_thumbnail_non_jpeg(self) -> None:
        if self.force_exiftool or use_exiftool_on_photo(
            self.rpd_file.extension,
            preview_extraction_irrelevant=False,
        ):
            self.extract_photo_video_from_camera(
                entire_file_required=self.entire_photo_required,
                using_exiftool=True,
            )
            if self.task == ExtractionTask.load_from_bytes_metadata_from_temp_extract:
                self.secondary_full_file_name = self.full_file_name_to_work_on
                self.file_to_work_on_is_temporary = False

        else:
            # gPhoto2 does not know how to get RAW thumbnails,
            # so we do that part ourselves
            if self.rpd_file.extension == "crw":
                # Could cache this file, since reading its
                # entirety But does anyone download a CRW file
                # from the camera these days?!
                bytes_to_read = self.rpd_file.size
            else:
                bytes_to_read = min(
                    self.rpd_file.size,
                    orientation_offset.get(self.rpd_file.extension, 500),
                )
            self.exif_buffer = self.camera.get_exif_extract(
                self.rpd_file.path, self.rpd_file.name, bytes_to_read
            )
        try:
            self.thumbnail_bytes = self.camera.get_thumbnail(
                self.rpd_file.path, self.rpd_file.name
            )
        except CameraProblemEx:
            # TODO report error
            self.thumbnail_bytes = None

    def task_camera_extract_photo_fetch_thumbnail(self):
        self.task = ExtractionTask.load_from_bytes
        if self.rpd_file.is_jpeg_type():
            self.task_camera_extract_photo_fetch_thumbnail_jpeg()
        else:
            self.task_camera_extract_photo_fetch_thumbnail_non_jpeg()

        self.processing.add(ExtractionProcessing.strip_bars_photo)
        self.processing.add(ExtractionProcessing.orient)

    def task_camera_extract_photo(self):
        if self.rpd_file.is_heif():
            self.task_camera_extract_photo_heif()
            return

        if self.camera.can_fetch_thumbnails:
            self.task_camera_extract_photo_fetch_thumbnail()
            return

        # Many (all?) jpegs from phones don't include jpeg previews,
        # so need to render from the entire jpeg itself. Slow!

        # For raw, extract merely a part of phone's raw format, and
        # try to extract the jpeg preview from it (which probably
        # doesn't exist!). This is fast.

        if not self.rpd_file.is_jpeg():
            bytes_to_read = thumbnail_offset.get(self.rpd_file.extension)
            if bytes_to_read:
                self.exif_buffer = self.camera.get_exif_extract(
                    self.rpd_file.path, self.rpd_file.name, bytes_to_read
                )
                self.task = ExtractionTask.load_from_exif_buffer
                self.processing.add(ExtractionProcessing.orient)
        if (
            self.task == ExtractionTask.undetermined
            and self.cache_full_size_file_from_camera()
        ):
            if self.rpd_file.is_jpeg():
                self.task = ExtractionTask.load_file_and_exif_directly
                self.processing.add(ExtractionProcessing.resize)
                self.processing.add(ExtractionProcessing.orient)
            else:
                self.task = ExtractionTask.load_from_exif
                self.processing.add(ExtractionProcessing.resize)
                self.processing.add(ExtractionProcessing.orient)
            self.full_file_name_to_work_on = self.rpd_file.cache_full_file_name
        else:
            # Failed to generate thumbnail
            self.task = ExtractionTask.bypass

    def task_camera_extract_video_have_thm(self) -> None:
        # Fortunately, we have a special video thumbnail file
        # Still need to get metadata time, however.

        if self.entire_video_required:
            offset = self.rpd_file.size
        else:
            offset = datetime_offset.get(self.rpd_file.extension)
            # If there is no offset, there is no point trying to
            # extract the metadata time from part of the video. It's
            # not ideal, but if this is from a camera on which there
            # were any other files we can assume we've got a
            # somewhat accurate date time for it from the
            # modification time. The only exception is if the video
            # file is not that big, in which case it's worth reading
            # in its entirety:
            if offset is None and self.rpd_file.size < 4000000:
                offset = self.rpd_file.size

        if self.rpd_file.mdatatime or not offset:
            self.task = ExtractionTask.load_from_bytes
        elif self.cache_file_chunk_from_camera(offset):
            self.task = ExtractionTask.load_from_bytes_metadata_from_temp_extract
            self.secondary_full_file_name = self.rpd_file.temp_cache_full_file_chunk
        else:
            # For some reason was unable to download part of the
            # video file
            self.task = ExtractionTask.load_from_bytes

        try:
            self.thumbnail_bytes = self.camera.get_THM_file(self.rpd_file.thm_full_name)
        except CameraProblemEx:
            # TODO report error
            self.thumbnail_bytes = None
        self.processing.add(ExtractionProcessing.strip_bars_video)
        self.processing.add(ExtractionProcessing.add_film_strip)

    def task_camera_extract_video(self) -> None:
        if self.rpd_file.thm_full_name is not None:
            self.task_camera_extract_video_have_thm()
        else:
            self.extract_photo_video_from_camera(
                entire_file_required=self.entire_video_required,
                using_exiftool=False,
            )

    def task_camera_extract(self) -> None:
        assert self.camera
        if self.rpd_file.file_type == FileType.photo:
            self.task_camera_extract_photo()
        else:
            self.task_camera_extract_video()

    def task_disk_extract_have_thm(self) -> None:
        self.full_file_name_to_work_on = self.rpd_file.thm_full_name
        if self.task == ExtractionTask.load_file_directly_metadata_from_secondary:
            self.secondary_full_file_name = self.rpd_file.full_file_name

    def task_disk_extract(self) -> None:
        assert self.camera is None
        self.task = preprocess_thumbnail_from_disk(
            rpd_file=self.rpd_file, processing=self.processing
        )
        if self.task != ExtractionTask.bypass:
            if self.rpd_file.thm_full_name is not None:
                self.task_disk_extract_have_thm()
            else:
                self.full_file_name_to_work_on = self.rpd_file.full_file_name

    def do_work(self) -> None:
        try:
            self.generate_thumbnails()
        except SystemExit as e:
            sys.exit(e.code)
        except Exception:
            if hasattr(self, "device_name"):
                logging.error(
                    "Exception generating thumbnails for %s", self.device_name
                )
            else:
                logging.error("Exception generating thumbnails")
            logging.exception("Traceback:")

    def generate_thumbnails(self) -> None:
        self.camera: Camera | None = None
        arguments: GenerateThumbnailsArguments = pickle.loads(self.content)
        self.device_name = arguments.name
        logging.info(
            "Generating %s thumbnails for %s", len(arguments.rpd_files), arguments.name
        )
        if arguments.log_gphoto2:
            self.gphoto2_logging = gphoto2_python_logging()

        self.frontend = self.context.socket(zmq.PUSH)
        self.frontend.connect(f"tcp://localhost:{arguments.frontend_port}")

        self.prefs = Preferences()

        # Whether we must use ExifTool to read photo metadata
        self.force_exiftool = self.prefs.force_exiftool

        # If the entire photo or video is required to extract the thumbnail, which is
        # determined when extracting sample metadata from a photo or video during the
        # device scan
        self.entire_photo_required = arguments.entire_photo_required
        self.entire_video_required = arguments.entire_video_required

        # Access and generate Rapid Photo Downloader thumbnail cache
        use_thumbnail_cache = self.prefs.use_thumbnail_cache

        thumbnail_caches = GetThumbnailFromCache(
            use_thumbnail_cache=use_thumbnail_cache
        )

        self.photo_cache_dir = None
        self.video_cache_dir = None
        cache_file_from_camera = self.force_exiftool

        rpd_files = self.prioritise_thumbnail_order(arguments=arguments)

        if arguments.camera is not None:
            rpd_files = self.prepare_for_camera_thumbnail_extraction(
                arguments=arguments,
                cache_file_from_camera=cache_file_from_camera,
                rpd_files=rpd_files,
            )
        else:
            self.camera = None

        self.counter.clear()

        for self.rpd_file in rpd_files:
            # Check to see if the process has received a command
            self.check_for_controller_directive()

            self.exif_buffer = None
            self.file_to_work_on_is_temporary = False
            self.secondary_full_file_name = ""
            self.processing = set()

            # Attempt to get thumbnail from Thumbnail Cache
            # (see cache.py for definitions of various caches)

            cache_search = thumbnail_caches.get_from_cache(self.rpd_file)
            self.task = cache_search.task
            self.thumbnail_bytes = cache_search.thumbnail_bytes
            self.full_file_name_to_work_on = cache_search.full_file_name_to_work_on
            self.origin = cache_search.origin

            if self.task != ExtractionTask.undetermined:
                self.task_cache_extract()

            if self.task == ExtractionTask.undetermined:
                # Thumbnail was not found in any cache: extract it
                if self.camera:
                    self.task_camera_extract()
                else:
                    self.task_disk_extract()

            if self.task == ExtractionTask.bypass:
                self.content = pickle.dumps(
                    GenerateThumbnailsResults(
                        rpd_file=self.rpd_file, thumbnail_bytes=self.thumbnail_bytes
                    ),
                    pickle.HIGHEST_PROTOCOL,
                )
                self.send_message_to_sink()

            elif self.task != ExtractionTask.undetermined:
                # Send data to load balancer, which will send to one of its
                # workers

                self.content = pickle.dumps(
                    ThumbnailExtractorArgument(
                        rpd_file=self.rpd_file,
                        task=self.task,
                        processing=self.processing,
                        full_file_name_to_work_on=self.full_file_name_to_work_on,
                        secondary_full_file_name=self.secondary_full_file_name,
                        exif_buffer=self.exif_buffer,
                        thumbnail_bytes=self.thumbnail_bytes,
                        use_thumbnail_cache=use_thumbnail_cache,
                        file_to_work_on_is_temporary=self.file_to_work_on_is_temporary,
                        write_fdo_thumbnail=False,
                        send_thumb_to_main=True,
                        force_exiftool=self.force_exiftool,
                    ),
                    pickle.HIGHEST_PROTOCOL,
                )
                self.frontend.send_multipart([b"data", self.content])

        if self.camera:
            self.camera.free_camera()
            # Delete our temporary cache directories if they are empty
            if self.photo_cache_dir is not None and not os.listdir(
                self.photo_cache_dir
            ):
                os.rmdir(self.photo_cache_dir)
            if self.video_cache_dir is not None and not os.listdir(
                self.video_cache_dir
            ):
                os.rmdir(self.video_cache_dir)

        logging.debug(
            "Finished phase 1 of thumbnail generation for %s", self.device_name
        )
        if self.counter["thumb_cache"]:
            logging.info(
                f"{self.counter['thumb_cache']} of {len(rpd_files)} thumbnails for "
                f"{self.device_name} came from thumbnail cache"
            )
        if self.counter["fdo_cache"]:
            logging.info(
                f"{self.counter['fdo_cache']} of {len(rpd_files)} thumbnails of for "
                f"{self.device_name} came from Free Desktop cache"
            )

        self.disconnect_logging()
        self.send_finished_command()

    def cleanup_pre_stop(self):
        if self.camera is not None:
            self.camera.free_camera()


if __name__ == "__main__":
    generate_thumbnails = GenerateThumbnails()
