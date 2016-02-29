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
Worker process to get thumbnails from Thumbnail or FDO cache, or
read thumbnail / file from the device being downloaded from.

For each device, there is one of these workers.

Sends thumbnail processing tasks to load balancer.
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2011-2016, Damon Lynch"

try:
    using_injected = 'profile' in dict(__builtins__)
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

import zmq
from PyQt5.QtGui import QImage
from PyQt5.QtCore import QSize
import psutil

from raphodo.rpdfile import RPDFile
from raphodo.interprocess import (WorkerInPublishPullPipeline,
                          GenerateThumbnailsArguments,
                          GenerateThumbnailsResults,
                          ThumbnailExtractorArgument)
from raphodo.constants import (FileType, ThumbnailSize, ThumbnailCacheStatus,
                       ThumbnailCacheDiskStatus, FileSortPriority, ExtractionTask,
                       ExtractionProcessing, orientation_offset, thumbnail_offset)
from raphodo.camera import (Camera, CopyChunks)
from raphodo.cache import ThumbnailCacheSql, FdoCacheLarge
from raphodo.utilities import (GenerateRandomFileName, create_temp_dir, CacheDirs)
from raphodo.preferences import Preferences

# FIXME free camera in case of early termination


def split_list(alist: list, wanted_parts=2):
    """
    Split list into smaller parts
    http://stackoverflow.com/questions/752308/split-list-into-smaller-lists
    :param alist: the list
    :param wanted_parts: how many lists it should be split into
    :return: the split lists
    """
    length = len(alist)
    return [alist[i * length // wanted_parts: (i + 1) * length // wanted_parts]
            for i in range(wanted_parts)]


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
            if rpd_file.modification_time - prev.modification_time > \
                    temporal_span:
                gaps.append(rpd_file)
            else:
                sequences.append(rpd_file)
            prev = rpd_file
        return (gaps, sequences)
    return None



class GenerateThumbnails(WorkerInPublishPullPipeline):

    # How much of the file should be read in from local disk and thus cached
    # by they kernel
    cached_read = dict(
        cr2=260 * 1024,
        dng=504 * 1024,
        nef=400* 1024
    )

    def __init__(self) -> None:
        # self.offsets = Offsets()
        self.random_filename = GenerateRandomFileName()
        super().__init__('Thumbnails')

    def image_large_enough(self, size: QSize) -> bool:
        """Check if image is equal or bigger than thumbnail size."""
        return (size.width() >= self.thumbnail_size_needed.width() or
                size.height() >= self.thumbnail_size_needed.height())

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
            cache_dir, '{}.{}'.format(
                self.random_filename.name(), rpd_file.extension))
        copy_chunks = self.camera.save_file_by_chunks(
            dir_name=rpd_file.path,
            file_name=rpd_file.name,
            size=rpd_file.size,
            dest_full_filename=cache_full_file_name,
            progress_callback=None,
            check_for_command=self.check_for_controller_directive,
            return_file_bytes=False) # type:  CopyChunks
        if copy_chunks.copy_succeeded:
            rpd_file.cache_full_file_name = cache_full_file_name
            return True
        else:
            return False

    def cache_file_chunk_from_camera(self, rpd_file: RPDFile, offset: int) -> bool:
        if rpd_file.file_type == FileType.photo:
            cache_dir = self.photo_cache_dir
        else:
            cache_dir = self.video_cache_dir
        cache_full_file_name = os.path.join(
            cache_dir, '{}.{}'.format(
                self.random_filename.name(), rpd_file.extension))
        if self.camera.save_file_chunk(
            dir_name=rpd_file.path,
            file_name=rpd_file.name,
            chunk_size_in_bytes=offset,
            dest_full_filename=cache_full_file_name
        ):
            rpd_file.temp_cache_full_file_chunk = cache_full_file_name
            return True
        return False

# TODO notfiy this worker if cannot process certain types of thumbnail, e.g. DNG from cellphone
# TODO notify this worker if could not extract thumbnail from small chunk of file, e.g. video
# TODO improve extraction order of photos, videos
# TODO make cache dirs on demand?

    def do_work(self) -> None:
        arguments = pickle.loads(self.content) # type: GenerateThumbnailsArguments
        logging.info("Generating %s thumbnails for %s", len(arguments.rpd_files), arguments.name)

        self.frontend = self.context.socket(zmq.PUSH)
        self.frontend.connect("tcp://localhost:{}".format(arguments.frontend_port))

        self.prefs = Preferences()

        self.thumbnail_size_needed = QSize(ThumbnailSize.width, ThumbnailSize.height)

        # Access and generate Rapid Photo Downloader thumbnail cache
        if self.prefs.use_thumbnail_cache:
            thumbnail_cache = ThumbnailCacheSql()
        else:
            thumbnail_cache = None

        # Access and generate Freedesktop.org thumbnail caches
        fdo_cache_large = FdoCacheLarge()

        photo_cache_dir = video_cache_dir = None
        cache_file_from_camera = False

        rpd_files = arguments.rpd_files

        # with open('tests/thumbnail_data_medium_no_tiff', 'wb') as f:
        #     pickle.dump(rpd_files, f)


        # Classify files by type:
        # get thumbnails for core (non-other) photos first, then
        # videos, then other photos

        photos = []
        videos = []
        other_photos = []
        for rpd_file in rpd_files: # type: RPDFile
            if rpd_file.file_type == FileType.photo:
                if rpd_file.sort_priority == FileSortPriority.high:
                    photos.append(rpd_file)
                else:
                    other_photos.append(rpd_file)
            else:
                videos.append(rpd_file)

        photos = sorted(photos,  key=attrgetter('modification_time'))
        videos = sorted(videos,  key=attrgetter('modification_time'))
        other_photos = sorted(other_photos,  key=attrgetter('modification_time'))

        might_need_video_cache_dir = (len(videos) and arguments.camera)

        # 60 seconds * 60 minutes i.e. one hour
        photo_time_span = video_time_span = 60 * 60

        # Prioritize the order in which we generate the thumbnails
        rpd_files2 = []
        for file_list, time_span in ((photos, photo_time_span),
                                     (videos, video_time_span),
                                     (other_photos, photo_time_span)):
            if file_list:
                gaps, sequences = get_temporal_gaps_and_sequences(
                    file_list, time_span)

                rpd_files2.extend(gaps)

                indexes = split_indexes(len(sequences))
                rpd_files2.extend([sequences[idx] for idx in indexes])

        assert len(rpd_files) == len(rpd_files2)
        rpd_files = rpd_files2

        if arguments.camera is not None:
            self.camera = Camera(arguments.camera, arguments.port)

            if not self.camera.camera_initialized:
                # There is nothing to do here: exit!
                logging.debug("Prematurely exiting thumbnail generation due "
                              "to lack of access to camera %s",
                              arguments.camera)
                self.disconnect_logging()
                self.send_finished_command()
                sys.exit(0)

            must_make_cache_dirs = (not self.camera.can_fetch_thumbnails
                                    or cache_file_from_camera)

            if must_make_cache_dirs or might_need_video_cache_dir:
                # If downloading complete copy of the files to
                # generate previews, then may as well cache them to speed up
                # the download process
                cache_file_from_camera = must_make_cache_dirs
                self.photo_cache_dir = create_temp_dir(
                    folder=arguments.cache_dirs.photo_cache_dir,
                    prefix='rpd-cache-{}-'.format(arguments.name[:10]))
                self.video_cache_dir = create_temp_dir(
                    folder=arguments.cache_dirs.video_cache_dir,
                    prefix='rpd-cache-{}-'.format(arguments.name[:10]))
                cache_dirs = CacheDirs(self.photo_cache_dir, self.video_cache_dir)
                self.content = pickle.dumps(GenerateThumbnailsResults(
                    scan_id=arguments.scan_id,
                    cache_dirs=cache_dirs), pickle.HIGHEST_PROTOCOL)
                self.send_message_to_sink()
        else:
            self.camera = None

        from_thumb_cache = 0
        from_fdo_cache = 0

        for rpd_file in rpd_files: # type: RPDFile
            # Check to see if the process has received a command
            self.check_for_controller_directive()

            exif_buffer = None
            thumbnail_bytes = None
            full_file_name_to_work_on = ''
            task = ExtractionTask.undetermined
            processing = set()

            # Attempt to get thumbnail from Thumbnail Cache
            # (see cache.py for definitions of various caches)
            if thumbnail_cache is not None:
                get_thumbnail = thumbnail_cache.get_thumbnail_path(
                    full_file_name=rpd_file.full_file_name,
                    modification_time=rpd_file.modification_time,
                    size=rpd_file.size,
                    camera_model=arguments.camera)
                if get_thumbnail.disk_status == ThumbnailCacheDiskStatus.failure:
                    rpd_file.thumbnail_status = ThumbnailCacheStatus.generation_failed
                    task = ExtractionTask.bypass
                elif get_thumbnail.disk_status == ThumbnailCacheDiskStatus.found:
                    if get_thumbnail.orientation_unknown:
                        rpd_file.thumbnail_status = \
                            ThumbnailCacheStatus.from_rpd_cache_fdo_write_invalid
                    else:
                        rpd_file.thumbnail_status = \
                            ThumbnailCacheStatus.suitable_for_fdo_cache_write
                    with open(get_thumbnail.path, 'rb') as thumbnail:
                        thumbnail_bytes = thumbnail.read()
                    task = ExtractionTask.bypass

            # Attempt to get thumbnail from large FDO Cache if not found in Thumbnail Cache

            if task == ExtractionTask.undetermined:
                get_thumbnail = fdo_cache_large.get_thumbnail(
                    full_file_name=rpd_file.full_file_name,
                    modification_time=rpd_file.modification_time,
                    size=rpd_file.size,
                    camera_model=arguments.camera)
                if get_thumbnail.disk_status == ThumbnailCacheDiskStatus.found:
                    rpd_file.fdo_thumbnail_256_name = get_thumbnail.path
                    rpd_file.thumbnail_status = ThumbnailCacheStatus.suitable_for_fdo_cache_write

                    thumb = get_thumbnail.thumbnail  # type: QImage
                    if thumb is not None:
                        if self.image_large_enough(thumb.size()):
                            task = ExtractionTask.load_file_directly
                            full_file_name_to_work_on = get_thumbnail.path
                            from_fdo_cache += 1

            if task == ExtractionTask.undetermined:
                # Thumbnail was not found in any cache: extract it
                if self.camera:  # type: Camera
                    if rpd_file.file_type == FileType.photo:
                        if self.camera.can_fetch_thumbnails:
                            task = ExtractionTask.load_from_bytes
                            if rpd_file.is_jpeg_type():
                                # gPhoto2 knows how to get jpeg thumbnails
                                exif_buffer = self.camera.get_exif_extract_from_jpeg(
                                    rpd_file.path, rpd_file.name)
                            else:
                                # gPhoto2 does not know how to get RAW thumbnails, so we do that
                                # part ourselves
                                if rpd_file.extension == 'crw':
                                    # TODO should be caching this file, since reading its entirety
                                    bytes_to_read = rpd_file.size
                                else:
                                    bytes_to_read = min(rpd_file.size,
                                        orientation_offset.get(rpd_file.extension, 500))
                                exif_buffer = self.camera.get_exif_extract_from_raw(
                                    rpd_file.path, rpd_file.name, bytes_to_read)
                            thumbnail_bytes = self.camera.get_thumbnail(rpd_file.path,
                                                                        rpd_file.name)
                            processing.add(ExtractionProcessing.strip_bars_photo)
                            processing.add(ExtractionProcessing.orient)
                        elif self.cache_full_size_file_from_camera(rpd_file):
                            task = ExtractionTask.load_file_directly
                            processing.add(ExtractionProcessing.resize)
                            processing.add(ExtractionProcessing.orient)
                            full_file_name_to_work_on = rpd_file.cache_full_file_name
                        else:
                            # Failed to generate thumbnail
                            task == ExtractionTask.bypass
                    else:
                        # video
                        if rpd_file.thm_full_name is not None:
                            # Fortunately, we have a special video thumbnail file
                            task = ExtractionTask.load_from_bytes
                            thumbnail_bytes = self.camera.get_THM_file(rpd_file.thm_full_name)
                            processing.add(ExtractionProcessing.strip_bars_video)
                            processing.add(ExtractionProcessing.add_film_strip)
                        else:
                            # For most videos, extract a small part of the video and use
                            # that to generate thumbnail
                            offset = thumbnail_offset.get(rpd_file.extension)
                            if offset and self.cache_file_chunk_from_camera(rpd_file, offset):
                                task = ExtractionTask.extract_from_temp_file
                                full_file_name_to_work_on = rpd_file.temp_cache_full_file_chunk
                            elif self.cache_full_size_file_from_camera(rpd_file):
                                task = ExtractionTask.extract_from_file
                                full_file_name_to_work_on = rpd_file.cache_full_file_name
                            else:
                                # Failed to generate thumbnail
                                task == ExtractionTask.bypass
                else:
                    # File is not on a camera
                    if rpd_file.file_type == FileType.photo:
                        if rpd_file.is_tiff():
                            availabe = psutil.virtual_memory().available
                            if rpd_file.size <= availabe:
                                bytes_to_read = rpd_file.size
                                task = ExtractionTask.load_file_directly
                                full_file_name_to_work_on = rpd_file.full_file_name
                                processing.add(ExtractionProcessing.resize)
                            else:
                                # Don't try to extract a thumbnail from
                                # a file that is larger than available
                                # memory
                                task == ExtractionTask.bypass
                                bytes_to_read = 0
                        else:
                            task = ExtractionTask.load_from_exif
                            processing.add(ExtractionProcessing.orient)
                            # TODO put a proper value here
                            bytes_to_read = self.cached_read.get(rpd_file.extension, 400 * 1024)
                        if bytes_to_read:
                            with open(rpd_file.full_file_name, 'rb') as photo:
                                # Bring the file into the disk cache
                                photo.read(bytes_to_read)
                    else:
                        # video
                        if rpd_file.thm_full_name is not None:
                            task = ExtractionTask.load_file_directly
                            processing.add(ExtractionProcessing.strip_bars_video)
                            processing.add(ExtractionProcessing.add_film_strip)
                            full_file_name_to_work_on = rpd_file.thm_full_name
                        else:
                            task = ExtractionTask.extract_from_file
                            full_file_name_to_work_on = rpd_file.full_file_name

            if task == ExtractionTask.bypass:
                self.content = pickle.dumps(GenerateThumbnailsResults(
                    rpd_file=rpd_file, thumbnail_bytes=thumbnail_bytes),
                    pickle.HIGHEST_PROTOCOL)
                self.send_message_to_sink()

            elif task != ExtractionTask.undetermined:
                # Send data to load balancer, which will send to one of its
                # workers

                self.content = pickle.dumps(ThumbnailExtractorArgument(
                    rpd_file=rpd_file,
                    task=task,
                    processing=processing,
                    full_file_name_to_work_on=full_file_name_to_work_on,
                    exif_buffer=exif_buffer,
                    thumbnail_bytes = thumbnail_bytes,
                    use_thumbnail_cache=thumbnail_cache is not None),
                    pickle.HIGHEST_PROTOCOL)
                self.frontend.send_multipart([b'data', self.content])


        if arguments.camera:
            self.camera.free_camera()
            # Delete our temporary cache directories if they are empty
            if photo_cache_dir is not None:
                if not os.listdir(self.photo_cache_dir):
                    os.rmdir(self.photo_cache_dir)
            if video_cache_dir is not None:
                if not os.listdir(self.video_cache_dir):
                    os.rmdir(self.video_cache_dir)

        logging.debug("Finished phase 1 of thumbnail generation for %s", arguments.name)
        if from_thumb_cache:
            logging.info("{} thumbnails for {} came from thumbnail cache".format(
                arguments.name, from_thumb_cache))
        if from_fdo_cache:
            logging.info("{} thumbnails for {} came from Free Desktop cache".format(
                arguments.name, from_fdo_cache))

        self.disconnect_logging()
        self.send_finished_command()


if __name__ == "__main__":
    generate_thumbnails = GenerateThumbnails()
