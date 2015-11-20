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
import shutil
import logging
import pickle
from collections import deque
from operator import attrgetter

import zmq
from PyQt5.QtGui import QImage, QTransform
from PyQt5.QtCore import QSize, Qt, QIODevice, QBuffer
import psutil

import qrc_resources

from rpdfile import RPDFile
from interprocess import (WorkerInPublishPullPipeline,
                          GenerateThumbnailsArguments,
                          GenerateThumbnailsResults,
                          ThumbnailExtractorArgument)
from constants import (Downloaded, FileType, ThumbnailSize, ThumbnailCacheStatus,
                       ThumbnailCacheDiskStatus, FileSortPriority, ExtractionTask)
from camera import (Camera, CopyChunks)
from cache import ThumbnailCacheSql, FdoCacheNormal, FdoCacheLarge
from utilities import (GenerateRandomFileName, create_temp_dir, CacheDirs)
from preferences import Preferences
from thumbnailextractor import qimage_to_png_buffer

# FIXME free camera in case of early termination

logging.basicConfig(format='%(levelname)s:%(asctime)s:%(message)s',
                    datefmt='%H:%M:%S',
                    level=logging.DEBUG)

stock_photo = QImage(":/photo.png")
stock_video = QImage(":/video.png")



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


def try_to_use_embedded_thumbnail(size: QSize,
                                  ignore_orientation: bool = True,
                                  image_to_be_rotated: bool = False,
                                  ignore_letterbox: bool = True) -> bool:
    r"""
    Most photos contain a 160x120 thumbnail as part of the exif
    metadata.

    Determine if size of thumbnail requested is greater than the size
    of embedded thumbnails.

    :param size: size needed. If None, assume the size needed is the
     biggest available (and return False).
    :param ignore_orientation: ignore the fact the image might be
     rotated e.g. if an image will be only 120px wide after rotation,
     and the width required is 160px, then still use the embedded
     thumbnail. This is useful when displaying the image in a 160x160px
     square.
    :param image_to_be_rotated: if True, base calculations on the fact
     the image will be rotated 90 or 270 degrees
    :param ignore_letterbox: 160//1.5 is 106, therefore embedded
     thumbnails have a letterbox on them. If True, ignore this in the
     height and width required calculation
    :return: True if should try to use embedded thumbnail,otherwise
     False

    >>> try_to_use_embedded_thumbnail(None)
    False
    >>> try_to_use_embedded_thumbnail(QSize(100,100))
    True
    >>> try_to_use_embedded_thumbnail(QSize(160,120))
    True
    >>> try_to_use_embedded_thumbnail(QSize(160,160))
    False
    >>> try_to_use_embedded_thumbnail(QSize(120,120), False, True)
    True
    >>> try_to_use_embedded_thumbnail(QSize(160,120), False, True)
    False
    >>> try_to_use_embedded_thumbnail(QSize(160,120), False, False)
    True
    >>> try_to_use_embedded_thumbnail(QSize(160,106), ignore_letterbox=False)
    True
    >>> try_to_use_embedded_thumbnail(QSize(160,120), ignore_letterbox=False)
    False
    >>> try_to_use_embedded_thumbnail(QSize(160,106), False, False, False)
    True
    >>> try_to_use_embedded_thumbnail(QSize(160,106), False, True, False)
    False
    >>> try_to_use_embedded_thumbnail(QSize(106,160), False, True, False)
    True
    >>> try_to_use_embedded_thumbnail(QSize(120,160), False, True, False)
    False
    """
    if size is None:
        return False

    if image_to_be_rotated and not ignore_orientation:
        width_sought = size.height()
        height_sought = size.width()
    else:
        width_sought = size.width()
        height_sought = size.height()

    if ignore_letterbox:
        thumbnail_width = 160
        thumbnail_height = 120
    else:
        thumbnail_width = 160
        thumbnail_height = 106

    return width_sought <= thumbnail_width and height_sought <= \
                                               thumbnail_height


class GenerateThumbnails(WorkerInPublishPullPipeline):
    cached_read = dict(
        cr2=260 * 1024,
        dng=504 * 1024,
        nef=400* 1024
    )
    exif_extract = dict(
        crw=114,
        dng=144,
        nef=132
    )

    def __init__(self) -> None:
        super().__init__('Thumbnails')

    def image_large_enough(self, size: QSize) -> bool:
        """Check if image is equal or bigger than thumbnail size."""
        return (size.width() >= self.thumbnail_size_needed.width() or
                size.height() >= self.thumbnail_size_needed.height())

    def do_work(self) -> None:
        arguments = pickle.loads(self.content) # type: GenerateThumbnailsArguments
        logging.debug("Generating thumbnails for %s", arguments.name)

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
        fdo_cache_normal = FdoCacheNormal()
        fdo_cache_large = FdoCacheLarge()

        have_ffmpeg_thumbnailer = shutil.which('ffmpegthumbnailer')

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
            camera = Camera(arguments.camera, arguments.port)
            if not camera.camera_initialized:
                # There is nothing to do here: exit!
                logging.debug("Prematurely exiting thumbnail generation due "
                              "to lack of access to camera %s",
                              arguments.camera)
                self.send_finished_command()
                sys.exit(0)

            must_make_cache_dirs = (not camera.can_fetch_thumbnails
                                    or not try_to_use_embedded_thumbnail(
                self.thumbnail_size_needed)
                                    or cache_file_from_camera)

            if must_make_cache_dirs or might_need_video_cache_dir:
                # If downloading complete copy of the files to
                # generate previews, then may as well cache them to speed up
                # the download process
                cache_file_from_camera = must_make_cache_dirs
                photo_cache_dir = create_temp_dir(
                    folder=arguments.cache_dirs.photo_cache_dir,
                    prefix='rpd-cache-{}-'.format(arguments.name[:10]))
                video_cache_dir = create_temp_dir(
                    folder=arguments.cache_dirs.video_cache_dir,
                    prefix='rpd-cache-{}-'.format(arguments.name[:10]))
                cache_dirs = CacheDirs(photo_cache_dir, video_cache_dir)
                self.content = pickle.dumps(GenerateThumbnailsResults(
                    scan_id=arguments.scan_id,
                    cache_dirs=cache_dirs), pickle.HIGHEST_PROTOCOL)
                self.send_message_to_sink()
        else:
            camera = None

        from_thumb_cache = 0
        from_fdo_cache = 0

        for rpd_file in rpd_files: # type: RPDFile
            # Check to see if the process has received a command
            self.check_for_controller_directive()

            exif_buffer = None
            thumbnail_bytes = None
            full_file_name_to_send = ''
            task = ExtractionTask.undetermined

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
                elif get_thumbnail.disk_status == ThumbnailCacheDiskStatus.found:
                    #TODO fix this logic when we're able to get orientation from the camera
                    if camera is not None and camera.can_fetch_thumbnails:
                        rpd_file.thumbnail_status = \
                            ThumbnailCacheStatus.from_rpd_cache_fdo_write_invalid
                    else:
                        rpd_file.thumbnail_status = \
                            ThumbnailCacheStatus.suitable_for_fdo_cache_write
                    with open(get_thumbnail.path, 'rb') as thumbnail:
                        thumbnail_bytes = thumbnail.readall()
                    task = ExtractionTask.bypass

            # Attempt to get thumbnails from the two FDO Caches.
            # If it's not found, we're going to generate it anyway.
            # So load it here.
            get_thumbnail = fdo_cache_normal.get_thumbnail(
                full_file_name=rpd_file.full_file_name,
                modification_time=rpd_file.modification_time,
                size=rpd_file.size,
                camera_model=arguments.camera)
            if get_thumbnail.disk_status == ThumbnailCacheDiskStatus.found:
                rpd_file.fdo_thumbnail_128_name = get_thumbnail.path
                rpd_file.thumbnail_status = ThumbnailCacheStatus.suitable_for_fdo_cache_write

            get_thumbnail = fdo_cache_large.get_thumbnail(
                full_file_name=rpd_file.full_file_name,
                modification_time=rpd_file.modification_time,
                size=rpd_file.size,
                camera_model=arguments.camera)
            if get_thumbnail.disk_status == ThumbnailCacheDiskStatus.found:
                rpd_file.fdo_thumbnail_256_name = get_thumbnail.path
                rpd_file.thumbnail_status = ThumbnailCacheStatus.suitable_for_fdo_cache_write

                if task == ExtractionTask.undetermined:
                    thumb = get_thumbnail.thumbnail  # type: QImage
                    if thumb is not None:
                        if self.image_large_enough(thumb):
                            task = ExtractionTask.load_file_directly
                            full_file_name_to_send = get_thumbnail.path
                            from_fdo_cache += 1

            if task == ExtractionTask.undetermined:
                # Thumbnail was not found in any cache: extract it
                if camera:
                    if rpd_file.file_type == FileType.photo:
                        task = ExtractionTask.load_from_bytes
                        bytes_to_read = self.exif_extract.get(rpd_file.extension, 400)
                        exif_buffer = camera.get_exif_extract(rpd_file.path, rpd_file.name,
                                                              bytes_to_read)
                        thumbnail_bytes = camera.get_thumbnail(rpd_file.path, rpd_file.name)
                else:
                    if rpd_file.file_type == FileType.photo:
                        task = ExtractionTask.load_from_exif
                        if rpd_file.is_tiff():
                            availabe = psutil.virtual_memory().available
                            if rpd_file.size <= availabe:
                                bytes_to_read = rpd_file.size
                            else:
                                bytes_to_read = 0
                                #TODO: handle very large TIFFs with no disk thrashing
                        else:
                            bytes_to_read = self.cached_read.get(rpd_file.extension, 400 * 1024)
                        if bytes_to_read:
                            with open(rpd_file.full_file_name, 'rb') as photo:
                                # Bring the file into the disk cache
                                photo.read(bytes_to_read)

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
                    thumbnail_full_file_name=full_file_name_to_send,
                    thumbnail_quality_lower=arguments.thumbnail_quality_lower,
                    exif_buffer=exif_buffer,
                    thumbnail_bytes = thumbnail_bytes),
                    pickle.HIGHEST_PROTOCOL)
                self.frontend.send_multipart([b'data', self.content])




        if arguments.camera:
            camera.free_camera()
            # Delete our temporary cache directories if they are empty
            if photo_cache_dir is not None:
                if not os.listdir(photo_cache_dir):
                    os.rmdir(photo_cache_dir)
            if video_cache_dir is not None:
                if not os.listdir(video_cache_dir):
                    os.rmdir(video_cache_dir)

        logging.debug("Finished phase 1 of thumbnail generation for %s", arguments.name)
        if from_thumb_cache:
            logging.debug("{} thumbnails came from thumbnail cache".format(from_thumb_cache))
        if from_fdo_cache:
            logging.debug("{} thumbnails came from FDO cache".format(from_fdo_cache))

        self.send_finished_command()


if __name__ == "__main__":
    generate_thumbnails = GenerateThumbnails()
