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
import sys
import os
from collections import namedtuple
from typing import Optional

from gi.repository import GExiv2, Gst

from PyQt5.QtGui import QImage, QTransform
from PyQt5.QtCore import QSize, Qt, QIODevice, QBuffer

from interprocess import (LoadBalancerWorker, ThumbnailExtractorArgument,
                          GenerateThumbnailsResults)
from constants import ThumbnailSize, ExtractionTask, ExtractionProcessing
from rpdfile import RPDFile
from utilities import stdchannel_redirected, show_errors
from filmstrip import add_filmstrip

have_gst = Gst.init_check(None)

def get_video_frame(full_file_name: str,
                    offset: Optional[int]=5,
                    caps=Gst.Caps.from_string('image/png')) -> bytes:
    """
    Source: https://gist.github.com/dplanella/5563018

    :param full_file_name: file and path of the video
    :param offset:
    :param caps:
    :return: gstreamer buffer
    """
    pipeline = Gst.parse_launch('playbin')
    pipeline.props.uri = 'file://' + os.path.abspath(full_file_name)
    pipeline.props.audio_sink = Gst.ElementFactory.make('fakesink', 'fakeaudio')
    pipeline.props.video_sink = Gst.ElementFactory.make('fakesink', 'fakevideo')
    pipeline.set_state(Gst.State.PAUSED)
    # Wait for state change to finish.
    pipeline.get_state(Gst.CLOCK_TIME_NONE)

    # Seek offset seconds into the video, if the video is long enough
    # If video is shorter than offset, seek 0.25 seconds less than the duration,
    # but always at least zero.
    offset=max(min(pipeline.query_duration(Gst.Format.TIME)[1] - Gst.SECOND / 4, offset *
                   Gst.SECOND), 0)

    assert pipeline.seek_simple(
        Gst.Format.TIME, Gst.SeekFlags.FLUSH, offset)
    # Wait for seek to finish.
    pipeline.get_state(Gst.CLOCK_TIME_NONE)
    sample = pipeline.emit('convert-sample', caps)
    buffer = sample.get_buffer()
    pipeline.set_state(Gst.State.NULL)
    return buffer.extract_dup(0, buffer.get_size())

PhotoDetails = namedtuple('PhotoDetails', 'thumbnail orientation')

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

    def image_large_enough(self, size: QSize) -> bool:
        """Check if image is equal or bigger than thumbnail size."""
        return (size.width() >= self.thumbnail_size_needed.width() or
                size.height() >= self.thumbnail_size_needed.height())

    def get_disk_photo_thumb(self, rpd_file: RPDFile,
                             processing: ExtractionProcessing) -> PhotoDetails:

        full_file_name = rpd_file.full_file_name

        orientation = None
        thumbnail = None
        try:
            metadata = GExiv2.Metadata(full_file_name)
        except:
            logging.warning("Could not read metadata from %s", full_file_name)
            metadata = None

        if metadata:
            try:
                orientation = metadata['Exif.Image.Orientation']
                processing.add(ExtractionProcessing.orient)
            except KeyError:
                pass

            # Not all files have an exif preview, but some do
            # (typically CR2, ARW, PEF, RW2).
            # If they exist, they are (almost!) always 160x120

            ep = metadata.get_exif_thumbnail()
            if ep:
                thumbnail = QImage.fromData(metadata.get_exif_thumbnail())
                if thumbnail.isNull():
                    thumbnail = None
                elif thumbnail.width() == 120 and thumbnail.height() == 160:
                    # The Samsung Pro815 can store its thumbnails this way!
                    # Perhaps some other obscure cameras also do this too.
                    # The orientation has already been applied to the thumbnail
                    orientation = '1'
                elif not rpd_file.is_jpeg():
                    processing.add(ExtractionProcessing.strip_bars_photo)
            else:
                previews = metadata.get_preview_properties()
                if previews:
                    # In every RAW file I've analyzed, the smallest preview is always first
                    preview = previews[0]
                    data = metadata.get_preview_image(preview).get_data()
                    if isinstance(data, bytes):
                        thumbnail = QImage.fromData(data)
                        if thumbnail.isNull():
                            thumbnail = None
                        else:
                            if thumbnail.width() > 160 or thumbnail.height() > 120:
                                processing.add(ExtractionProcessing.resize)
                            if not rpd_file.is_jpeg():
                                processing.add(ExtractionProcessing.strip_bars_photo)

        if thumbnail is None and rpd_file.is_loadable():
            thumbnail = QImage(full_file_name)
            processing.add(ExtractionProcessing.resize)
            if thumbnail.isNull():
                thumbnail = None
                logging.error(
                    "Unable to create a thumbnail out of the file: {}".format(full_file_name))

        return PhotoDetails(thumbnail, orientation)

    def get_orientation(self, rpd_file: RPDFile, full_file_name: Optional[str]=None,
                        raw_bytes: Optional[bytearray]=None) -> Optional[str]:
        metadata = None
        if raw_bytes is not None:
            metadata = GExiv2.Metadata()
            try:
                metadata.open_buf(raw_bytes)
            except:
                logging.error("Extractor failed to load metadata from %s", rpd_file.name)
        else:
            try:
                metadata = GExiv2.Metadata(full_file_name)
            except:
                logging.error("Extractor failed to load metadata from %s", rpd_file.name)
        if metadata is not None:
            try:
                return metadata['Exif.Image.Orientation']
            except KeyError:
                pass
        return None

    def do_work(self):
        if True:
            context = show_errors()
        else:
            # Redirect stderr, hiding error output from exiv2
            context = stdchannel_redirected(sys.stderr, os.devnull)
        with context:
            while True:
                directive, content = self.requester.recv_multipart()
                self.check_for_command(directive, content)
                #
                data = pickle.loads(content) # type: ThumbnailExtractorArgument

                logging.debug("%s is working on %s", self.requester.identity.decode(),
                              data.rpd_file.name)

                png_data = None
                orientation = None
                task = data.task
                processing = data.processing
                add_film_strip_to_thumb = False

                if task == ExtractionTask.load_from_exif:
                    thumbnail_details = self.get_disk_photo_thumb(data.rpd_file, processing)
                    thumbnail = thumbnail_details.thumbnail
                    if thumbnail is not None:
                        orientation = thumbnail_details.orientation

                elif task == ExtractionTask.load_file_directly:
                    logging.debug("Getting QImage from file %s",
                                  data.full_file_name_to_work_on)
                    thumbnail = QImage(data.full_file_name_to_work_on)
                    if ExtractionProcessing.orient in processing:
                        orientation = self.get_orientation(rpd_file=data.rpd_file,
                                                   full_file_name=data.full_file_name_to_work_on)

                elif task == ExtractionTask.load_from_bytes:
                    thumbnail = QImage.fromData(data.thumbnail_bytes)
                    if data.exif_buffer and ExtractionProcessing.orient in processing:
                        orientation = self.get_orientation(rpd_file=data.rpd_file,
                                                           raw_bytes=data.exif_buffer)
                else:
                    assert task == ExtractionTask.extract_from_file
                    if not have_gst:
                        thumbnail = None
                    else:
                        png = get_video_frame(data.full_file_name_to_work_on)
                        thumbnail = QImage.fromData(png)
                        if thumbnail.isNull():
                            thumbnail = None
                        else:
                            add_film_strip_to_thumb = True
                            processing.add(ExtractionProcessing.resize)

                if ExtractionProcessing.strip_bars_photo in processing:
                    thumbnail = crop_160x120_thumbnail(thumbnail)
                elif ExtractionProcessing.strip_bars_video in processing:
                    thumbnail = crop_160x120_thumbnail(thumbnail, 15)
                elif ExtractionProcessing.resize in processing:
                    # TODO properly handle thumbnail resizing from cellphoens
                    thumbnail = thumbnail.scaled(
                        self.thumbnail_size_needed,
                        Qt.KeepAspectRatio,
                        data.thumbnail_quality_lower)
                    if thumbnail.isNull():
                        thumbnail = None

                if add_film_strip_to_thumb:
                    thumbnail = add_filmstrip(thumbnail)

                if orientation is not None and thumbnail is not None:
                    thumbnail =  self.rotate_thumb(thumbnail, orientation)

                if thumbnail is not None:
                    buffer = qimage_to_png_buffer(thumbnail)
                    png_data = buffer.data()

                self.sender.send_multipart([b'0', b'data',
                        pickle.dumps(
                        GenerateThumbnailsResults(
                            rpd_file=data.rpd_file,
                            thumbnail_bytes=png_data),
                        pickle.HIGHEST_PROTOCOL)])
                self.requester.send_multipart([b'', b'', b'OK'])

if __name__ == "__main__":
    thumbnail_extractor = ThumbnailExtractor()