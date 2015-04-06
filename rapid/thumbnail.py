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
import logging
import pickle
import tempfile
import subprocess
import shlex


from PyQt5.QtGui import QImage, QTransform
from PyQt5.QtCore import QSize, Qt, QIODevice, QBuffer
from gi.repository import GExiv2


from rpdfile import RPDFile

from interprocess import (WorkerInPublishPullPipeline,
                          GenerateThumbnailsArguments,
                          GenerateThumbnailsResults)

from filmstrip import add_filmstrip

from constants import (Downloaded, FileType, ThumbnailSize)
from camera import (Camera, CopyChunks)
from utilities import (GenerateRandomFileName, create_temp_dir, CacheDirs)

#FIXME free camera in case of early termination

logging.basicConfig(format='%(levelname)s:%(asctime)s:%(message)s',
                    datefmt='%H:%M:%S',
                    level=logging.DEBUG)


# def get_stock_photo_image():
#     length = min(gtk.gdk.screen_width(), gtk.gdk.screen_height())
#     pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(paths.share_dir('glade3/photo.svg'), length, length)
#     image = pixbuf_to_image(pixbuf)
#     return image
#
# def get_stock_photo_image_icon():
#     image = Image.open(paths.share_dir('glade3/photo66.png'))
#     image = image.convert("RGBA")
#     return image
#
# def get_stock_video_image():
#     length = min(gtk.gdk.screen_width(), gtk.gdk.screen_height())
#     pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(paths.share_dir('glade3/video.svg'), length, length)
#     image = pixbuf_to_image(pixbuf)
#     return image
#
# def get_stock_video_image_icon():
#     image = Image.open(paths.share_dir('glade3/video66.png'))
#     image = image.convert("RGBA")
#     return image
#
#
# class PhotoIcons():
#     stock_thumbnail_image_icon = get_stock_photo_image_icon()
#
# class VideoIcons():
#     stock_thumbnail_image_icon = get_stock_video_image_icon()

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

class Thumbnail:
    """
    Extract thumbnails from a photo or video in QImage format
    """

    # file types from which to remove letterboxing (black bands in the
    # thumbnail previews)
    crop_thumbnails = ('cr2', 'dng', 'raf', 'orf', 'pef', 'arw')

    # Exif rotation constants
    rotate_90 = '6'
    rotate_180 = '3'
    rotate_270 = '8'
    stock_photo = QImage("images/photo66.png")
    stock_video = QImage("images/video66.png")

    def __init__(self, rpd_file: RPDFile, camera: Camera,
                 thumbnail_quality_lower: bool,
                 cache_file_from_camera: bool=False,
                 photo_cache_dir: str=None,
                 video_cache_dir: str=None,
                 check_for_command=None):
        """
        :param rpd_file: file from which to extract the thumbnails
        :param camera: if not None, the camera from which to get the
         thumbnails
        :param thumbnail_quality_lower: whether to generate the
         thumbnail high or low quality as it is scaled by Qt
        :param cache_file_from_camera: if True, get the file from the
         camera, save it in cache directory, and extract thumbnail from
         it. Otherwise,
        :param photo_cache_dir: if specified, the folder in which
         full size photos from a camera should be cached
        :param video_cache_dir: if specified, the folder in which
         videos from a camera should be cached
        """
        self.rpd_file = rpd_file
        self.metadata = None
        self.camera = camera
        if thumbnail_quality_lower:
            self.thumbnail_transform = Qt.FastTransformation
        else:
            self.thumbnail_transform = Qt.SmoothTransformation
        self.cache_file_from_camera = cache_file_from_camera
        if cache_file_from_camera:
            assert photo_cache_dir is not None
            assert video_cache_dir is not None
        self.photo_cache_dir = photo_cache_dir
        self.video_cache_dir = video_cache_dir
        if photo_cache_dir is not None or video_cache_dir is not None:
            self.random_filename = GenerateRandomFileName()
        self.check_for_command = check_for_command


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
        Returns a correctly sized and rotated thumbnail for the file

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
        # we need the maximum size, or there is no metadata
        if self.rpd_file.is_jpeg():
            if not self.metadata or size is None:
                thumbnail = QImage(file_name)
                if thumbnail.isNull():
                    could_not_load_jpeg = True
                    logging.error(
                        "Unable to create a thumbnail out of the jpeg "
                        "{}".format(file_name))

        if self.metadata and thumbnail is None:
            ignore_embedded_thumbnail = not try_to_use_embedded_thumbnail(size)
            self.previews = self.metadata.get_preview_properties()
            self.is_jpeg = self.metadata.get_mime_type() == "image/jpeg"

            # Check for special case of a RAW file with no previews and
            # only an embedded thumbnail. We need that embedded thumbnail
            # no matter how small it is
            if not self.rpd_file.is_raw() and not self.previews:
                if self.metadata.get_exif_thumbnail():
                    ignore_embedded_thumbnail = False

            if not ignore_embedded_thumbnail:
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
                # displaying that (very dark image)
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
            if orientation == self.rotate_90:
                thumbnail = thumbnail.transformed(QTransform().rotate(90))
            elif orientation == self.rotate_270:
                thumbnail = thumbnail.transformed(QTransform().rotate(270))
            elif orientation == self.rotate_180:
                thumbnail = thumbnail.transformed(QTransform().rotate(180))

            if size is not None:
                thumbnail = thumbnail.scaled(size, Qt.KeepAspectRatio,
                                             self.thumbnail_transform)
        else:
            thumbnail = self.stock_photo
        return thumbnail

    def _cache_full_size_file_from_camera(self) -> bool:
        """
        Get the file from the camera chunk by chunk and cache it in
        local cache dir
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

        thumbnail = None

        file_name = os.path.join(self.rpd_file.full_file_name)

        thumbnail = self.camera.get_thumbnail(self.rpd_file.path,
                                              self.rpd_file.name)
        if thumbnail is None:
            logging.error("Unable to get thumbnail from %s for %s",
                          self.camera.model, file_name)
        elif thumbnail.isNull():
            thumbnail = None
            logging.error(
                "Unable to get thumbnail from %s for %s",
                self.camera.model, file_name)

        if self.rpd_file.extension in \
                self.crop_thumbnails and thumbnail is not None:
            thumbnail = self._crop_160x120_thumbnail(thumbnail, 8)

        if size is not None and thumbnail is not None:
            thumbnail = thumbnail.scaled(size, Qt.KeepAspectRatio,
                                         self.thumbnail_transform)

        if thumbnail is None:
            return self.stock_photo
        else:
            return  thumbnail

    def _get_video_thumbnail(self, file_name: str, size: QSize, downloaded: \
                             bool) -> QImage:
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
        if self.rpd_file.thm_full_name is not None and size is not None:
            use_thm = size.width() <= 160

        if use_thm:
            if downloaded:
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


        if thumbnail is None and (downloaded or self.cache_file_from_camera or
            not self.rpd_file.from_camera):
            # extract a frame from the video file and scale it
            #FIXME haven't handled case of missing ffmpegthumbnailer
            try:
                if size is None:
                    thumbnail_size = 0
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

        if thumbnail is None or thumbnail.isNull():
            thumbnail = self.stock_video

        return thumbnail

    def get_thumbnail(self, size: QSize=None) -> QImage:
        """
        :param size: size of the thumbnail needed (maximum height and
         width). If size is None, return maximum size
         available.
         :return the thumbnail, or stock image if generation failed
        """

        if self.cache_file_from_camera:
            downloaded = False
            if self._cache_full_size_file_from_camera():
                file_name = self.rpd_file.cache_full_file_name
            elif self.rpd_file.file_type == FileType.photo:
                return self.stock_photo
            else:
                return self.stock_video
        else:
            # If the file is already downloaded, get the thumbnail from it
            downloaded = self.rpd_file.status in Downloaded
            if downloaded:
                file_name = self.rpd_file.download_full_file_name
            else:
                file_name = self.rpd_file.full_file_name


        if self.rpd_file.file_type == FileType.photo:
            if self.rpd_file.from_camera and not (downloaded or
                                                  self.cache_file_from_camera):
                return self._get_photo_thumbnail_from_camera(size)
            else:
                return self._get_photo_thumbnail(file_name, size)
        else:
            return self._get_video_thumbnail(file_name, size, downloaded)


class GenerateThumbnails(WorkerInPublishPullPipeline):

    def __init__(self):
        super(GenerateThumbnails, self).__init__('Thumbnails')

    def do_work(self):
        arguments = pickle.loads(self.content)
        """ :type : GenerateThumbnailsArguments"""
        logging.debug("Generating thumbnails for %s...", arguments.name)

        thumbnail_size_needed =  QSize(ThumbnailSize.width,
                                       ThumbnailSize.height)


        photo_cache_dir = video_cache_dir = None
        cache_file_from_camera = False

        if arguments.camera:
            camera = Camera(arguments.camera, arguments.port)
            if not camera.camera_initialized:
                # There is nothing to do here: exit!
                logging.debug("Prematurely exiting thumbnail generation due "
                              "to lack of access to camera %s",
                              arguments.camera)
                self.send_finished_command()
                sys.exit(0)

            if (not camera.can_fetch_thumbnails
                or not try_to_use_embedded_thumbnail(thumbnail_size_needed)
                or cache_file_from_camera):
                # Need to download complete copy of the files to
                # generate previews.
                # May as well cache them to speed up the download process
                cache_file_from_camera = True
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

        for rpd_file in arguments.rpd_files:

            # Check to see if the process has received a command
            self.check_for_command()

            thumbnail = Thumbnail(rpd_file, camera,
                              arguments.thumbnail_quality_lower,
                              cache_file_from_camera=cache_file_from_camera,
                              photo_cache_dir=photo_cache_dir,
                              video_cache_dir=video_cache_dir,
                              check_for_command=self.check_for_command)
            thumbnail_icon = thumbnail.get_thumbnail(
                size=thumbnail_size_needed)

            buffer = QBuffer()
            buffer.open(QIODevice.WriteOnly)
            thumbnail_icon.save(buffer, "PNG")

            self.content= pickle.dumps(GenerateThumbnailsResults(
                rpd_file=rpd_file, png_data=buffer.data()),
                pickle.HIGHEST_PROTOCOL)
            self.send_message_to_sink()

        if arguments.camera:
            camera.free_camera()
            # Delete our temporary cache directory only if it's empty
            if not os.listdir(photo_cache_dir):
                os.rmdir(photo_cache_dir)

        logging.debug("...finished thumbnail generation for %s",
                      arguments.name)
        self.send_finished_command()


if __name__ == "__main__":
    generate_thumbnails = GenerateThumbnails()