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

from constants import (Downloaded, FileType)
from camera import Camera
from utilities import (GenerateRandomFileName, create_temp_dir)

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
                 use_temp_file: bool, photo_cache_dir=None):
        """
        :param rpd_file: file from which to extract the thumbnails
        :param camera: if not None, the camera from which to get the
        thumbnails
        :param thumbnail_quality_lower: whether to generate the
        thumbnail high or low quality as it is scaled by Qt
        :param use_temp_file: if True, generate the thumbnail from the
        temporary file that has been downloaded
        :param photo_cache_dir: if specified, the folder in which
        full size photos from a camera should be cached
        :type photo_cache_dir: str
        """
        self.rpd_file = rpd_file
        self.metadata = None
        self.camera = camera
        if thumbnail_quality_lower:
            self.thumbnail_transform = Qt.FastTransformation
        else:
            self.thumbnail_transform = Qt.SmoothTransformation
        self.use_temp_file = use_temp_file
        self.photo_cache_dir = photo_cache_dir
        if photo_cache_dir is not None:
            self.random_filename = GenerateRandomFileName()

    def _ignore_embedded_160x120_thumbnail(self) -> bool:
        """
        Most photos contain a 160x120 thumbnail as part of the exif
        metadata. If the size of the thumbnail being sought is bigger,
        or it's missing, then it should be ignored.

        :return: True if the embedded exif thumbnail should be ignored
        """

        if self.width_sought is None:
            return True
        # height is compared against 106 because we're going to crop the
        # thumbnail to remove the black bands
        # 106 = 160 // 1.5
        return (self.width_sought > 160 or self.height_sought > 106 or
                not self.metadata.get_exif_thumbnail())

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
        if self.metadata is None:
            try:
                self.metadata = GExiv2.Metadata(file_name)
            except:
                logging.warning("Could not read metadata from %s", file_name)

            if self.metadata:
                try:
                    self.orientation = self.metadata['Exif.Image.Orientation']
                except KeyError:
                    self.orientation = None

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
            # Get preliminary information about what we need and what
            # metadata we have
            if size is not None:
                self.width_sought = size.width()
                self.height_sought = size.height()
            else:
                self.width_sought = self.height_sought = None

            # Orientation is important because it affects calculations
            # around image width and height
            if self.orientation in (self.rotate_90, self.rotate_270):
                if size is not None:
                    self.width_sought = size.height()
                    self.height_sought = size.width()


            self.ignore_embedded_thumbnail = \
                self._ignore_embedded_160x120_thumbnail()
            self.previews = self.metadata.get_preview_properties()
            self.is_jpeg = self.metadata.get_mime_type() == "image/jpeg"

            # Check for special case of a RAW file with no previews and
            # only an embedded thumbnail. We need that embedded thumbnail
            # no matter how small it is
            if not self.is_jpeg and not self.previews:
                if self.metadata.get_exif_thumbnail():
                    self.ignore_embedded_thumbnail = False

            if not self.ignore_embedded_thumbnail:
                thumbnail = QImage.fromData(self.metadata.get_exif_thumbnail())
                if thumbnail.isNull():
                    logging.warning("Could not extract thumbnail from {"
                                    "}".format(file_name))
                    thumbnail = None
                if (self.rpd_file.extension in self.crop_thumbnails and
                            thumbnail is not None):
                    # args: x, y, image width, image height
                    thumbnail = self._crop_160x120_thumbnail(thumbnail, 8)

            if self.previews and thumbnail is None:
                if size is None:
                    # Use the largest preview we have access to
                    preview = self.previews[-1]
                else:
                    # Get the biggest preview we need
                    for preview in self.previews:
                        if (preview.get_width() >= self.width_sought and
                                preview.get_height() >= self.height_sought):
                            break

                data = self.metadata.get_preview_image(preview).get_data()
                if isinstance(data, bytes):
                    try:
                        thumbnail = QImage.fromData(data)
                    except:
                        logging.warning("Could not load thumbnail from "
                                        "metadata preview for {}".format(
                                        file_name))

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
            if self.orientation == self.rotate_90:
                thumbnail = thumbnail.transformed(QTransform().rotate(90))
            elif self.orientation == self.rotate_270:
                thumbnail = thumbnail.transformed(QTransform().rotate(270))
            elif self.orientation == self.rotate_180:
                thumbnail = thumbnail.transformed(QTransform().rotate(180))

            if size is not None:
                thumbnail = thumbnail.scaled(size, Qt.KeepAspectRatio,
                                             self.thumbnail_transform)
        else:
            thumbnail = self.stock_photo
        return thumbnail

    def _get_photo_thumbnail_from_camera(self, file_name: str,
                                         size: QSize) -> QImage:

        thumbnail = None
        ignore_embedded_thumbnail = True
        is_raw_image =  self.rpd_file.is_raw()
        if self.camera.can_fetch_thumbnails:
            if is_raw_image:
                # without first downloading the photo, there is no way to get
                # a bigger preview
                ignore_embedded_thumbnail = False
            else:
                # we don't know the image orientation and it seems gphoto2
                # provides no way of knowing it without downloading the file
                if size is not None:
                    ignore_embedded_thumbnail = size.width() > 160

        if not (is_raw_image and not self.camera.can_fetch_thumbnails):
            if ignore_embedded_thumbnail:
                # locally cache the full size image
                cache_full_file_name = os.path.join(
                    self.photo_cache_dir, '{}.{}'.format(
                        self.random_filename.name(), self.rpd_file.extension))
            else:
                cache_full_file_name = None
            thumbnail = self.camera.get_thumbnail(self.rpd_file.path,
                                                  self.rpd_file.name,
                                                  ignore_embedded_thumbnail,
                                                  cache_full_file_name)
            if thumbnail is None:
                logging.error("Unable to get thumbnail from %s for %s",
                              self.camera.model, file_name)
            elif thumbnail.isNull():
                thumbnail = None
                logging.error(
                    "Unable to get thumbnail from %s for %s",
                    self.camera.model, file_name)
            else:
                self.rpd_file.cache_full_file_name = cache_full_file_name


            if not ignore_embedded_thumbnail and self.rpd_file.extension in \
                    self.crop_thumbnails and thumbnail is not None:
                thumbnail = self._crop_160x120_thumbnail(thumbnail, 8)

            if size is not None and thumbnail is not None:
                thumbnail = thumbnail.scaled(size, Qt.KeepAspectRatio,
                                             self.thumbnail_transform)

        if thumbnail is None:
            return self.stock_photo
        else:
            return  thumbnail


    def _get_video_thumbnail(self, file_name: str, size: QSize, downloaded:
                             bool) -> QImage:
        """
        Returns a correctly sized thumbnail for the file.
        Assumes a horizontal orientation

        :param file_name: file from which to extract the thumnbnail
        :param size: size of the thumbnail needed (maximum height and
                     width). If size is None, return maximum size.
        :param downloaded: if True, the file has already been downloaded
        :return a QImage of the thumbnail
        """

        thumbnail = None

        use_thm = False
        if self.rpd_file.thm_full_name is not None:
            if self.rpd_file.from_camera and not (downloaded or
                                                      self.use_temp_file):
                use_thm = True
            elif size is not None:
                if size.width() <= 160:
                    use_thm = True

        if use_thm:
            if self.use_temp_file:
                thumbnail = QImage(self.rpd_file.temp_thm_full_name)
            elif downloaded:
                thumbnail = QImage(self.rpd_file.download_thm_full_name)
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


        if thumbnail is None and (downloaded or self.use_temp_file or (not
                                                   self.rpd_file.from_camera)):
            # extract a frame from the video file and scale it
            #FIXME haven't handled case of missing program
            try:
                if size is None:
                    thumbnail_size = 0
                else:
                    thumbnail_size = size.width()
                tmp_dir = tempfile.mkdtemp(prefix="rpd-tmp")
                thm = os.path.join(tmp_dir, 'thumbnail.jpg')
                command = shlex.split('ffmpegthumbnailer -i {} -t 10 -f -o {'
                                      '} -s {}'.format(file_name, thm,
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

    def get_thumbnail(self, size=None) -> QImage:
        """
        :param size: size of the thumbnail needed (maximum height and
                     width). If size is None, return maximum size.
        :type size: QSize
        """

        if self.use_temp_file:
            file_name = self.rpd_file.temp_full_file_name
            downloaded = False
        else:
            # If the file is already downloaded, cannot assume the source
            # file is still available
            downloaded = self.rpd_file.status in Downloaded
            if downloaded:
                file_name = self.rpd_file.download_full_file_name
            else:
                file_name = self.rpd_file.full_file_name

        if self.rpd_file.file_type == FileType.photo:
            if (self.rpd_file.from_camera and not (downloaded or
                self.use_temp_file)):
                return self._get_photo_thumbnail_from_camera(file_name, size)
            else:
                return self._get_photo_thumbnail(file_name, size)
        else:
            return self._get_video_thumbnail(file_name, size, downloaded)


# class GetPreviewImage(multiprocessing.Process):
#     def __init__(self, results_pipe):
#         multiprocessing.Process.__init__(self)
#         self.daemon = True
#         self.results_pipe = results_pipe
#         self.thumbnail_maker = Thumbnail()
#         self.stock_photo_thumbnail_image = None
#         self.stock_video_thumbnail_image = None
#
#     def get_stock_image(self, file_type):
#         """
#         Get stock image for file type scaled to the current size of the screen
#         """
#         if file_type == rpdfile.FILE_TYPE_PHOTO:
#             if self.stock_photo_thumbnail_image is None:
#                 self.stock_photo_thumbnail_image = PicklablePIL(get_stock_photo_image())
#             return self.stock_photo_thumbnail_image
#         else:
#             if self.stock_video_thumbnail_image is None:
#                 self.stock_video_thumbnail_image = PicklablePIL(get_stock_video_image())
#             return self.stock_video_thumbnail_image
#
#     def run(self):
#         while True:
#             unique_id, full_file_name, thm_full_name, file_type, size_max = self.results_pipe.recv()
#             full_size_preview, reduced_size_preview = self.thumbnail_maker.get_thumbnail(full_file_name, thm_full_name, file_type, size_max=size_max, size_reduced=(100,100))
#             if full_size_preview is None:
#                 full_size_preview = self.get_stock_image(file_type)
#             self.results_pipe.send((unique_id, full_size_preview, reduced_size_preview))


class GenerateThumbnails(WorkerInPublishPullPipeline):

    def __init__(self):
        super(GenerateThumbnails, self).__init__('Thumbnails')

    def do_work(self):
        arguments = pickle.loads(self.content)
        """ :type : GenerateThumbnailsArguments"""
        logging.debug("Generating thumbnails for %s...", arguments.name)


        photo_cache_dir = None
        if arguments.camera:
            camera = Camera(arguments.camera, arguments.port)
            if not camera.camera_initialized:
                # There is nothing to do here: exit!
                logging.debug("Prematurely exiting thumbnail generation due "
                              "to lack of access to camera %s",
                              arguments.camera)
                self.send_finished_command()
                sys.exit(0)
            # Sometimes need to download complete copy of the files to
            # generate previews.
            # May as well cache them to speed up the download process
            photo_cache_dir = create_temp_dir(
                folder=arguments.photo_cache_folder,
                prefix='rpd-cache-{}-'.format(arguments.name[:10]))
            self.content = pickle.dumps(GenerateThumbnailsResults(
                    scan_id=arguments.scan_id,
                    photo_cache_dir=photo_cache_dir), pickle.HIGHEST_PROTOCOL)
            self.send_message_to_sink()
        else:
            camera = None

        for rpd_file in arguments.rpd_files:

            # Check to see if the process has received a command
            self.check_for_command()

            # The maximum size of the embedded exif thumbnail is typically
            # 160x120.
            thumbnail = Thumbnail(rpd_file, camera,
                                  arguments.thumbnail_quality_lower,
                                  use_temp_file=False,
                                  photo_cache_dir=photo_cache_dir)
            thumbnail_icon = thumbnail.get_thumbnail(size=QSize(100,100))

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