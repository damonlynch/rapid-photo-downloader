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


import os
import sys
import shutil
import logging
import pickle
import tempfile
import subprocess
import shlex
from operator import attrgetter
from collections import deque

from PyQt5.QtGui import QImage, QTransform
from PyQt5.QtCore import QSize, Qt, QIODevice, QBuffer
from gi.repository import GExiv2

from rpdfile import RPDFile

from interprocess import (WorkerInPublishPullPipeline,
                          GenerateThumbnailsArguments,
                          GenerateThumbnailsResults)

from filmstrip import add_filmstrip

from constants import (Downloaded, FileType, ThumbnailSize, ThumbnailCacheStatus)
from camera import (Camera, CopyChunks)
from cache import ThumbnailCache, FdoCacheNormal, FdoCacheLarge
from utilities import (GenerateRandomFileName, create_temp_dir, CacheDirs)
from preferences import Preferences

#FIXME free camera in case of early termination

logging.basicConfig(format='%(levelname)s:%(asctime)s:%(message)s',
                    datefmt='%H:%M:%S',
                    level=logging.DEBUG)


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
                                  ignore_orientation: bool=True,
                                  image_to_be_rotated: bool=False,
                                  ignore_letterbox: bool=True) -> bool:
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

def qimage_to_png_buffer(image: QImage) -> QBuffer:
    """
    Save the image data in PNG format in a QBuffer, whose data can then
    be extracted using the data() member function.
    :param image: the image to be converted
    :return: the buffer
    """
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return buffer

class Thumbnail:
    """
    Extract thumbnails from a photo or video in QImage format, and
    optionally generate thumbnails to be cached
    """

    # file types from which to remove letterboxing (black bands in the
    # thumbnail previews)
    crop_thumbnails = ('cr2', 'dng', 'raf', 'orf', 'pef', 'arw')

    # Exif rotation constants
    rotate_90 = '6'
    rotate_180 = '3'
    rotate_270 = '8'
    stock_photo = QImage("images/photo106.png")
    stock_video = QImage("images/video106.png")

    def __init__(self, rpd_file: RPDFile, camera: Camera,
                 thumbnail_quality_lower: bool,
                 thumbnail_cache: ThumbnailCache,
                 fdo_cache_normal: FdoCacheNormal,
                 fdo_cache_large: FdoCacheLarge,
                 generate_fdo_thumbs_only_if_optimal: bool=False,
                 must_generate_fdo_thumbs: bool=False,
                 cache_file_from_camera: bool=False,
                 photo_cache_dir: str=None,
                 video_cache_dir: str=None,
                 check_for_command=None,
                 have_ffmpeg_thumbnailer: bool=True,
                 modification_time=None):
        """
        For definitions of the three different types of cache, see
        cache.py
        :param rpd_file: file from which to extract the thumbnails
        :param camera: if not None, the camera from which to get the
         thumbnails
        :param thumbnail_quality_lower: whether to generate the
         thumbnail high or low quality as it is scaled by Qt
        :param thumbnail_cache: used to cache thumbnails on the file
         system. Not to be confused with caching files for use in the
         download process. If None, don't cache.
        :param generate_fdo_thumbs_only_if_optimal: If True,
         attempt to generate image previews for eventual storage in the
         freedesktop.org thumbnail directory i.e.
         $XDG_CACHE_HOME/thumbnails/normal and
         $XDG_CACHE_HOME/thumbnails/large. However only generate them
         if and only if performance will not be overly impacted. For
         example, if a 160x120 thumbnails is embedded in a file with
         horizontal alignment, then generate a 128x102 thumbnail but
         not a 256x204. thumbnail. If generated, they will be  stored
         in the rpd_file as raw PNG image data. If not, their value
         will be unchanged.
        :param must_generate_fdo_thumbs: If True, attempt to generate
         image previews for eventual storage in the freedesktop.org
         thumbnail directory (as with previous option), but in both
         large and normal sizes
        :param cache_file_from_camera: if True, get the file from the
         camera, save it in download cache, and extract thumbnail
         from it.
        :param photo_cache_dir: if specified, the folder in which
         full size photos from a camera should be cached
        :param video_cache_dir: if specified, the folder in which
         videos from a camera should be cached
        :param have_ffmpeg_thumbnailer: If True the program
         ffmpegthumbnailer is assumed to exist
        :param modification_time: the file modification time to be
         written to the FDO Cache and/or Thumbnail Cache. If none,
         the modification time will be assumed to be in the RPDFile
        """
        self.rpd_file = rpd_file
        self.metadata = None
        self.camera = camera
        if camera is not None or rpd_file.from_camera:
            self.camera_model = rpd_file.camera_model
        else:
            self.camera_model= None
        self.thumbnail_cache =  thumbnail_cache
        self.fdo_cache_normal = fdo_cache_normal
        self.fdo_cache_large = fdo_cache_large
        self.generate_fdo_thumbs_only_if_optimal = \
            generate_fdo_thumbs_only_if_optimal
        self.must_generate_fdo_thumbs = must_generate_fdo_thumbs
        self.cache_file_from_camera = cache_file_from_camera
        if cache_file_from_camera:
            assert photo_cache_dir is not None
            assert video_cache_dir is not None
        if generate_fdo_thumbs_only_if_optimal or must_generate_fdo_thumbs \
                or not thumbnail_quality_lower:
            self.thumbnail_transform = Qt.SmoothTransformation
        else:
            self.thumbnail_transform = Qt.FastTransformation
        self.photo_cache_dir = photo_cache_dir
        self.video_cache_dir = video_cache_dir
        self.random_filename = GenerateRandomFileName()
        self.check_for_command = check_for_command
        self.have_ffmpeg_thumbnailer = have_ffmpeg_thumbnailer
        if modification_time is not None:
            self.modification_time = modification_time
        else:
            self.modification_time = rpd_file.modification_time


    def _crop_160x120_thumbnail(self, thumbnail: QImage,
                                vertical_space: int) -> QImage:
        """
        Remove black bands from the top and bottom of thumbnail
        :param thumbnail: thumbnail to crop
        :param vertical_space: how much to remove from the top and bottom
        :return: cropped thumbnail
        """
        return thumbnail.copy(0, vertical_space, 160, 120 - vertical_space*2)

    def _get_photo_thumbnail(self, file_name, size: QSize) -> QImage:
        """
        Returns a correctly sized and rotated thumbnail for the file,
        which is asssumed to be on a directly readable file system

        :param file_name: photo from which to get the thumbnail
        :param size: size of the thumbnail needed (maximum height and
                     width). If size is None, return maximum size.
        :return a QImage of the thumbnail
        """

        thumbnail = None
        could_not_load_jpeg = False

        # Even for jpeg, need to read the metadata, so as to get the
        # orientation tag
        orientation = None
        if self.metadata is None:
            try:
                self.metadata = GExiv2.Metadata(file_name)
            except:
                logging.warning("Could not read metadata from %s", file_name)

            if self.metadata:
                try:
                    orientation = self.metadata['Exif.Image.Orientation']
                except KeyError:
                    pass

        # Create a thumbnail out of the file itself if it's a jpeg and
        # we need the maximum size, or there is no metadata, or it's from
        # a phone or camera and we have cached the jpeg (sometimes the
        # embedded thumbnails are corrupt)
        if self.rpd_file.is_jpeg():
            if not self.metadata or size is None or (
                    self.rpd_file.from_camera and self.cache_file_from_camera):
                thumbnail = QImage(file_name)
                could_not_load_jpeg = thumbnail.isNull()
                if could_not_load_jpeg:
                    logging.error(
                        "Unable to create a thumbnail out of the jpeg "
                        "{}".format(file_name))

        if self.metadata and (thumbnail is None or
                                  self.must_generate_fdo_thumbs):
            ignore_embedded_thumbnail = not try_to_use_embedded_thumbnail(size)
            self.previews = self.metadata.get_preview_properties()
            self.is_jpeg = self.metadata.get_mime_type() == "image/jpeg"

            # Check for special case of a RAW file with no previews and
            # only an embedded thumbnail. We need that embedded thumbnail
            # no matter how small it is
            if not self.rpd_file.is_raw() and not self.previews:
                if self.metadata.get_exif_thumbnail():
                    ignore_embedded_thumbnail = False

            if not ignore_embedded_thumbnail and not (self.previews and
                    self.must_generate_fdo_thumbs):
                thumbnail = QImage.fromData(self.metadata.get_exif_thumbnail())
                if thumbnail.isNull():
                    logging.warning("Could not extract thumbnail from {"
                                    "}".format(file_name))
                    thumbnail = None
                if (self.rpd_file.extension in self.crop_thumbnails and
                            thumbnail is not None):
                    thumbnail = self._crop_160x120_thumbnail(thumbnail, 8)

            if self.previews and thumbnail is None:
                # Use the largest preview we have access to
                # Let's hope it's not a TIFF, as there seem to be problems
                # displaying that (get a very dark image)
                preview = self.previews[-1]

                data = self.metadata.get_preview_image(preview).get_data()
                if isinstance(data, bytes):
                    thumbnail = QImage.fromData(data)
                    if thumbnail.isNull():
                        logging.warning("Could not load thumbnail from "
                                        "metadata preview for {}".format(
                                        file_name))
                        thumbnail = None

        if thumbnail is None and self.rpd_file.is_jpeg() and not \
                could_not_load_jpeg:
            # Unable to get thumbnail from metadata
            logging.debug("Creating thumbnail from the jpeg "
                          "itself: {}".format(file_name))
            thumbnail = QImage(file_name)
            if thumbnail.isNull():
                thumbnail = None
                logging.error(
                    "Unable to create a thumbnail out of the jpeg: "
                    "{}".format(file_name))

        if thumbnail is not None and not thumbnail.isNull():
            if size is not None:
                sized_thumbnail = thumbnail.scaled(size, Qt.KeepAspectRatio,
                                             self.thumbnail_transform)
            else:
                sized_thumbnail = thumbnail

            sized_thumbnail = self.rotate_thumb(sized_thumbnail, orientation)

            if self.generate_fdo_thumbs_only_if_optimal or \
                    self.must_generate_fdo_thumbs:
                if self.cache_file_from_camera and not self.downloaded:
                    file_name = self.rpd_file.full_file_name
                self._save_fdo_cache_thumbs(file_name, thumbnail,
                                              sized_thumbnail, orientation)

            if self.thumbnail_cache is not None and ((self.downloaded and
                    self.rpd_file.from_camera) or not self.downloaded):
                if self.downloaded:
                    file_name = self.rpd_file.download_full_file_name
                    camera_model = None
                else:
                    file_name = self.rpd_file.full_file_name
                    camera_model = self.rpd_file.camera_model
                self.thumbnail_cache.save_thumbnail(
                    file_name, self.rpd_file.size,
                    self.modification_time, sized_thumbnail,
                    camera_model)

            self.rpd_file.thumbnail_status = \
                ThumbnailCacheStatus.suitable_for_fdo_cache_write

        else:
            sized_thumbnail = self.stock_photo
        return sized_thumbnail

    def rotate_thumb(self, thumbnail: QImage, orientation: str) -> QImage:
        """
        If required return a rotated copy the thumbnail
        :param thumbnail: thumbnail to rotate
        :param orientation: EXIF orientation tag
        :return: possibly rotated thumbnail
        """
        if orientation == self.rotate_90:
            thumbnail = thumbnail.transformed(QTransform(
            ).rotate(90))
        elif orientation == self.rotate_270:
            thumbnail = thumbnail.transformed(QTransform(
            ).rotate(270))
        elif orientation == self.rotate_180:
            thumbnail = thumbnail.transformed(QTransform(
            ).rotate(180))
        return thumbnail

    def _save_fdo_cache_thumbs(self, file_name: str, thumbnail: QImage,
                                     sized_thumbnail: QImage,
                                     orientation: str):
        """
        Create a freedesktop.org cache thumbnail, i.e. one available to
        file managers etc.
        """

        # The larger thumbnail is maximum 256x256
        fdo_256 = fdo_128 = None
        if not self.rpd_file.fdo_thumbnail_256_name:
            if (sized_thumbnail.width() >= 256 or sized_thumbnail.height() >=
                    256):
                # No need to rotate when scaling the this thumbnail: it's
                # already been rotated
                fdo_256 = sized_thumbnail.scaled(256, 256, Qt.KeepAspectRatio,
                                                 Qt.SmoothTransformation)
            elif thumbnail.width() >= 256 or thumbnail.height() >= 256:
                fdo_256 = thumbnail.scaled(256, 256, Qt.KeepAspectRatio,
                                           Qt.SmoothTransformation)
                fdo_256 = self.rotate_thumb(fdo_256, orientation)

        # The smaller thumbnail size is maximum 128x128
        if not self.rpd_file.fdo_thumbnail_128_name:
            if fdo_256 is not None:
                # It's faster to scale down a smaller image
                fdo_128= fdo_256.scaled(128, 128, Qt.KeepAspectRatio,
                                        Qt.SmoothTransformation)

            elif sized_thumbnail.width() >= 128 or sized_thumbnail.height(
                ) >= 128:
                fdo_128 = sized_thumbnail.scaled(128, 128, Qt.KeepAspectRatio,
                                                 Qt.SmoothTransformation)

            elif thumbnail.width() >= 128 or thumbnail.height(
                ) > 128:
                fdo_128 = thumbnail.scaled(128, 128, Qt.KeepAspectRatio,
                                           Qt.SmoothTransformation)
                fdo_128 = self.rotate_thumb(fdo_128, orientation)
            else:
                fdo_128 = sized_thumbnail

        if self.downloaded:
            camera_model = None
        else:
            camera_model = self.rpd_file.camera_model
        if fdo_128 is not None:
            self.rpd_file.fdo_thumbnail_128_name = \
                self.fdo_cache_normal.save_thumbnail(file_name,
                             self.rpd_file.size,
                             self.modification_time, fdo_128,
                             camera_model, True)
        if fdo_256 is not None:
            self.rpd_file.fdo_thumbnail_256_name = \
                self.fdo_cache_large.save_thumbnail(file_name,
                             self.rpd_file.size,
                             self.modification_time, fdo_256,
                             camera_model, True)

    def _cache_full_size_file_from_camera(self) -> bool:
        """
        Get the file from the camera chunk by chunk and cache it in
        download cache dir
        :return: True if operation succeeded, False otherwise
        """
        if self.rpd_file.file_type == FileType.photo:
            cache_dir = self.photo_cache_dir
        else:
            cache_dir = self.video_cache_dir
        cache_full_file_name = os.path.join(
            cache_dir, '{}.{}'.format(
                self.random_filename.name(), self.rpd_file.extension))
        copy_chunks = self.camera.save_file_by_chunks(
                        dir_name=self.rpd_file.path,
                        file_name=self.rpd_file.name,
                        size=self.rpd_file.size,
                        dest_full_filename=cache_full_file_name,
                        progress_callback=None,
                        check_for_command=self.check_for_command,
                        return_file_bytes=False)
        """:type : CopyChunks"""
        if copy_chunks.copy_succeeded:
            self.rpd_file.cache_full_file_name = cache_full_file_name
            return True
        else:
            return False

    def _get_photo_thumbnail_from_camera(self, size: QSize) -> QImage:
        """
        Assumes (1) camera can provide thumbnails without downloading
        the entire file, and (2) the size requested is not bigger
        than an embedded thumbnail
        :param size: the size needed
        :return:the thumbnail
        """

        assert self.camera.can_fetch_thumbnails
        assert size is not None

        thumbnail = self.camera.get_thumbnail(self.rpd_file.path,
                                              self.rpd_file.name)
        if thumbnail is None:
            logging.error("Unable to get thumbnail from %s for %s",
                          self.camera.model, self.rpd_file.full_file_name)
        elif thumbnail.isNull():
            thumbnail = None
            logging.error(
                "Unable to get thumbnail from %s for %s",
                self.camera.model, self.rpd_file.full_file_name)

        if self.rpd_file.extension in \
                self.crop_thumbnails and thumbnail is not None:
            thumbnail = self._crop_160x120_thumbnail(thumbnail, 8)

        if size is not None and thumbnail is not None:
            thumbnail = thumbnail.scaled(size, Qt.KeepAspectRatio,
                                         self.thumbnail_transform)

        if thumbnail is None:
            return self.stock_photo
        else:
            self.rpd_file.thumbnail_status = \
                ThumbnailCacheStatus.suitable_for_thumb_cache_write
            if self.thumbnail_cache is not None:
                self.thumbnail_cache.save_thumbnail(
                    self.rpd_file.full_file_name,self. rpd_file.size,
                    self.modification_time, thumbnail,
                    self.camera_model)
            return  thumbnail

    def _get_video_thumbnail(self, file_name: str, size: QSize) -> QImage:
        """
        Returns a correctly sized thumbnail for the file.
        Prefers to get thumbnail from THM if it's available and it's
        big enough.
        Assumes a horizontal orientation.

        :param file_name: file from which to extract the thumnbnail
        :param size: size of the thumbnail needed (maximum height and
                     width). If size is None, return maximum size.
        :param downloaded: if True, the file has already been downloaded
        :return a QImage of the thumbnail
        """

        thumbnail = None

        use_thm = False
        if self.rpd_file.thm_full_name is not None and size is not None and \
                not self.must_generate_fdo_thumbs:
            use_thm = size.width() <= 160

        if use_thm:
            if self.downloaded:
                thm_file = self.rpd_file.download_thm_full_name
                thumbnail = QImage(thm_file)
            else:
                thm_file = self.rpd_file.thm_full_name
                if self.rpd_file.from_camera:
                    thumbnail = self.camera.get_THM_file(thm_file)
                else:
                    thumbnail = QImage(thm_file)

            if thumbnail is None:
                logging.error("Could not get THM file from %s for %s",
                              self.camera.model, file_name)
                logging.error("Thumbnail file is %s", thm_file)
            elif thumbnail.isNull():
                logging.error("Could not open THM file for %s",
                              file_name)
                logging.error("Thumbnail file is %s", thm_file)
                thumbnail = None
            else:
                thumbnail = self._crop_160x120_thumbnail(thumbnail, 15)
                if size.width() != 160:
                    thumbnail = thumbnail.scaled(size,
                                                 Qt.KeepAspectRatio,
                                                 self.thumbnail_transform)
                thumbnail = add_filmstrip(thumbnail)
                self.rpd_file.thumbnail_status = \
                    ThumbnailCacheStatus.suitable_for_thumb_cache_write


        if (thumbnail is None and (self.downloaded or
                    self.cache_file_from_camera or not
                    self.rpd_file.from_camera) and
                    self.have_ffmpeg_thumbnailer):
            # extract a frame from the video file and scale it
            try:
                if size is None:
                    thumbnail_size = 0
                elif (self.must_generate_fdo_thumbs or
                            self.generate_fdo_thumbs_only_if_optimal):
                        thumbnail_size = max(size.width(), 256)
                else:
                    thumbnail_size = size.width()
                tmp_dir = tempfile.mkdtemp(prefix="rpd-tmp")
                thm = os.path.join(tmp_dir, 'thumbnail.jpg')
                command = shlex.split('ffmpegthumbnailer -i {} -t 10 -f -o "{'
                                      '}" -s {}'.format(shlex.quote(file_name),
                                                        thm,
                                                        thumbnail_size))
                subprocess.check_call(command)
                thumbnail = QImage(thm)
                os.unlink(thm)
                os.rmdir(tmp_dir)
            except:
                thumbnail = None
                logging.error("Error generating thumbnail for {}".format(
                    file_name))
            else:
                if not thumbnail.isNull():
                    self.rpd_file.thumbnail_status = \
                        ThumbnailCacheStatus.suitable_for_fdo_cache_write

                    if self.generate_fdo_thumbs_only_if_optimal or \
                            self.must_generate_fdo_thumbs:
                        self._save_fdo_cache_thumbs(file_name, thumbnail,
                                                thumbnail, '')
                    if size is not None:
                        if thumbnail.width() > size.width():
                            thumbnail = thumbnail.scaled(size,
                                                 Qt.KeepAspectRatio,
                                                 self.thumbnail_transform)

        if thumbnail is None or thumbnail.isNull():
            thumbnail = self.stock_video
        else:
            if self.thumbnail_cache is not None:
                self.thumbnail_cache.save_thumbnail(
                    self.rpd_file.full_file_name,self. rpd_file.size,
                    self.modification_time, thumbnail,
                    self.camera_model)
            if (self.must_generate_fdo_thumbs or
                            self.generate_fdo_thumbs_only_if_optimal):
                self._save_fdo_cache_thumbs(file_name, thumbnail, thumbnail,
                                            '')
        return thumbnail

    def get_thumbnail(self, size: QSize=None) -> QImage:
        """
        :param size: size of the thumbnail needed (maximum height and
         width). If size is None, return maximum size
         available.
         :return the thumbnail, or stock image if generation failed
        """
        self.downloaded = self.rpd_file.status in Downloaded
        # logging.debug("File status: %s; Downloaded: %s", self.rpd_file.status,
        #               self.downloaded)

        # Special case: video on camera. Even if libgphoto2 can provide
        # thumbnails from the camera, it probably can't do it for videos
        if (not self.downloaded and self.rpd_file.from_camera and
                 self.rpd_file.file_type == FileType.video):
            # However, if we can get the THM file and it's big enough, there is
            # no need to locally cache the video.
            self.cache_file_from_camera = not (try_to_use_embedded_thumbnail(
                size) and self.rpd_file.thm_full_name is not None)

        if self.cache_file_from_camera:

            if self._cache_full_size_file_from_camera():
                file_name = self.rpd_file.cache_full_file_name
            elif self.rpd_file.file_type == FileType.photo:
                return self.stock_photo
            else:
                return self.stock_video
        else:
            # If the file is already downloaded, get the thumbnail from it
            if self.downloaded:
                file_name = self.rpd_file.download_full_file_name
            else:
                file_name = self.rpd_file.full_file_name


        if self.rpd_file.file_type == FileType.photo:
            if self.rpd_file.from_camera and not (self.downloaded or
                                                  self.cache_file_from_camera):
                return self._get_photo_thumbnail_from_camera(size)
            else:
                return self._get_photo_thumbnail(file_name, size)
        else:
            return self._get_video_thumbnail(file_name, size)


class GenerateThumbnails(WorkerInPublishPullPipeline):

    def __init__(self):
        super(GenerateThumbnails, self).__init__('Thumbnails')

    def do_work(self):
        arguments = pickle.loads(self.content)
        """ :type : GenerateThumbnailsArguments"""
        logging.debug("Generating thumbnails for %s...", arguments.name)

        self.prefs = Preferences()

        thumbnail_size_needed =  QSize(ThumbnailSize.width,
                                       ThumbnailSize.height)

        # Access and generate Rapid Photo Downloader thumbnail cache
        if self.prefs.use_thumbnail_cache:
            thumbnail_cache = ThumbnailCache()
        else:
            thumbnail_cache = None

        # Access and generate Freedesktop.org thumbnail caches
        fdo_cache_normal = FdoCacheNormal()
        fdo_cache_large = FdoCacheLarge()

        have_ffmpeg_thumbnailer = shutil.which('ffmpegthumbnailer')

        photo_cache_dir = video_cache_dir = None
        cache_file_from_camera = False

        rpd_files = arguments.rpd_files

        # Get thumbnails for photos first, then videos
        # Are relying on the file type for photos being an int smaller than
        # that for videos
        rpd_files = sorted(rpd_files, key=attrgetter('file_type',
                                              'modification_time'))

        # Rely on fact that videos are now at the end, if they are there at all
        have_video = rpd_files[-1].file_type == FileType.video
        have_photo = rpd_files[0].file_type == FileType.photo
        might_need_video_cache_dir = (have_video and arguments.camera)

        if have_video and not have_photo:
            videos = rpd_files
            photos = []
        elif have_video:
            # find the first video and split the list into two
            first_video = [rpd_file.file_type for rpd_file in rpd_files].index(
                FileType.video)
            photos = rpd_files[:first_video]
            videos = rpd_files[first_video:]
        else:
            photos = rpd_files
            videos = []

        # 60 seconds * 60 minutes i.e. one hour
        photo_time_span = video_time_span = 60 * 60

        # Prioritize the order in which we generate the thumbnails
        rpd_files2 = []
        for file_list, time_span in ((photos, photo_time_span),
                                     (videos, video_time_span)):
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
                or not try_to_use_embedded_thumbnail(thumbnail_size_needed)
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
        for rpd_file in rpd_files:
            """:type : RPDFile"""
            # Check to see if the process has received a command
            self.check_for_command()

            if thumbnail_cache is not None:
                thumbnail_icon, thumbnail_path = thumbnail_cache.get_thumbnail(
                    rpd_file.full_file_name, rpd_file.modification_time,
                    arguments.camera)
            else:
                thumbnail_icon = None

            if thumbnail_icon is not None:
                if camera is not None and camera.can_fetch_thumbnails:
                    rpd_file.thumbnail_status = \
                        ThumbnailCacheStatus.from_rpd_cache_fdo_write_invalid
                else:
                    rpd_file.thumbnail_status = \
                        ThumbnailCacheStatus.suitable_for_fdo_cache_write
                    png, thumbnail_path = fdo_cache_normal.get_thumbnail(
                        rpd_file.full_file_name, rpd_file.modification_time,
                        arguments.camera)
                    if thumbnail_path:
                        # logging.debug("For %s located FDO thumbnail %s",
                        #               rpd_file.full_file_name, thumbnail_path)
                        rpd_file.fdo_thumbnail_128_name = thumbnail_path
                    png, thumbnail_path = fdo_cache_large.get_thumbnail(
                        rpd_file.full_file_name, rpd_file.modification_time,
                        arguments.camera)
                    if thumbnail_path:
                        # logging.debug("For %s located FDO thumbnail %s",
                        #               rpd_file.full_file_name, thumbnail_path)
                        rpd_file.fdo_thumbnail_256_name = thumbnail_path
                from_thumb_cache += 1
            else:
                thumbnail = Thumbnail(rpd_file, camera,
                              arguments.thumbnail_quality_lower,
                              thumbnail_cache=thumbnail_cache,
                              fdo_cache_normal=fdo_cache_normal,
                              fdo_cache_large=fdo_cache_large,
                              generate_fdo_thumbs_only_if_optimal=\
                                          self.prefs.save_fdo_thumbnails,
                              cache_file_from_camera=cache_file_from_camera,
                              photo_cache_dir=photo_cache_dir,
                              video_cache_dir=video_cache_dir,
                              check_for_command=self.check_for_command,
                              have_ffmpeg_thumbnailer=have_ffmpeg_thumbnailer)
                thumbnail_icon = thumbnail.get_thumbnail(
                    size=thumbnail_size_needed)

            buffer = qimage_to_png_buffer(thumbnail_icon)

            self.content= pickle.dumps(GenerateThumbnailsResults(
                rpd_file=rpd_file, png_data=buffer.data()),
                pickle.HIGHEST_PROTOCOL)
            self.send_message_to_sink()

        if arguments.camera:
            camera.free_camera()
            # Delete our temporary cache directories if they are empty
            if photo_cache_dir is not None:
                if not os.listdir(photo_cache_dir):
                    os.rmdir(photo_cache_dir)
            if video_cache_dir is not None:
                if not os.listdir(video_cache_dir):
                    os.rmdir(video_cache_dir)

        logging.debug("...finished thumbnail generation for %s",
                      arguments.name)
        if from_thumb_cache:
            logging.debug("{} thumbnails came from thumbnail cache".format(
                from_thumb_cache))
        self.send_finished_command()


if __name__ == "__main__":
    generate_thumbnails = GenerateThumbnails()