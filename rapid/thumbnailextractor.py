#!/usr/bin/python3
__author__ = 'Damon Lynch'
# Copyright (C) 2015 Damon Lynch <damonlynch@gmail.com>

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

import logging
import pickle
import os

from PyQt5.QtGui import QImage, QTransform
from PyQt5.QtCore import QSize, Qt, QIODevice, QBuffer

from interprocess import (LoadBalancerWorker, ThumbnailExtractorArgument,
                          GenerateThumbnailsResults)
from constants import ThumbnailSize

def qimage_to_png_buffer(image: QImage) -> QBuffer:
    """
    Save the image data in PNG format in a QBuffer, whose data can then
    be extracted using the data() member function.
    :param image: the image to be converted
    :return: the buffer
    """
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    # Quality 100 means uncompressed.
    image.save(buffer, "PNG", quality=100)
    return buffer

def crop_160x120_thumbnail(thumbnail: QImage, vertical_space: int=8) -> QImage:
    """
    Remove black bands from the top and bottom of thumbnail
    :param thumbnail: thumbnail to crop
    :param vertical_space: how much to remove from the top and bottom
    :return: cropped thumbnail
    """
    return thumbnail.copy(0, vertical_space, 160, 120 - vertical_space * 2)

class ThumbnailExtractor(LoadBalancerWorker):

    # Exif rotation constants
    rotate_90 = '6'
    rotate_180 = '3'
    rotate_270 = '8'

    def __init__(self):
        self.thumbnail_size_needed = QSize(ThumbnailSize.width, ThumbnailSize.height)
        super().__init__('Thumbnail Extractor')

    def rotate_thumb(self, thumbnail: QImage, orientation: str) -> QImage:
        """
        If required return a rotated copy the thumbnail
        :param thumbnail: thumbnail to rotate
        :param orientation: EXIF orientation tag
        :return: possibly rotated thumbnail
        """
        if orientation == self.rotate_90:
            thumbnail = thumbnail.transformed(QTransform().rotate(90))
        elif orientation == self.rotate_270:
            thumbnail = thumbnail.transformed(QTransform().rotate(270))
        elif orientation == self.rotate_180:
            thumbnail = thumbnail.transformed(QTransform().rotate(180))
        return thumbnail

    def do_work(self):
        while True:
            directive, content = self.requester.recv_multipart()
            self.check_for_command(directive, content)
            #
            data = pickle.loads(content) # type: ThumbnailExtractorArgument

            logging.debug("%s is working on %s", self.requester.identity.decode(),
                          data.rpd_file.name)

            final_thumbnail = None
            png_data = None
            resize = False

            if data.thumbnail_full_file_name:
                logging.debug("Attempting to get QImage from file %s",
                              data.thumbnail_full_file_name)
                assert isinstance(data.thumbnail_full_file_name, str)
                thumbnail = QImage(data.thumbnail_full_file_name)
                resize = True
            else:
                assert data.thumbnail is not None
                thumbnail = QImage.fromData(data.thumbnail)
                if data.crop160x120:
                    #TODO don't crop from jpegs
                    final_thumbnail = crop_160x120_thumbnail(thumbnail)
                else:
                    resize = True

            if resize:
                #TODO resizing of thumbnails from cellphones
                final_thumbnail = thumbnail.scaled(
                    self.thumbnail_size_needed,
                    Qt.KeepAspectRatio,
                    data.thumbnail_quality_lower)
                if final_thumbnail.isNull():
                    final_thumbnail = None

            if data.orientation is not None and final_thumbnail is not None:
                final_thumbnail =  self.rotate_thumb(final_thumbnail, data.orientation)

            if final_thumbnail is not None:
                buffer = qimage_to_png_buffer(final_thumbnail)
                png_data = buffer.data()

            self.sender.send_multipart([b'0', b'data',
                    pickle.dumps(
                    GenerateThumbnailsResults(
                        rpd_file=data.rpd_file,
                        png_data=png_data),
                    pickle.HIGHEST_PROTOCOL)])
            self.requester.send_multipart([b'', b'', b'OK'])

if __name__ == "__main__":
    thumbnail_extractor = ThumbnailExtractor()