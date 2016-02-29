#!/usr/bin/env python3

# Copyright (C) 2015-2016 Damon Lynch <damonlynch@gmail.com>

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

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2015-2016, Damon Lynch"

import sys
import logging
from urllib.request import pathname2url
import pickle
import os
from collections import namedtuple
from typing import Optional

import gi
gi.require_version('GExiv2', '0.10')
gi.require_version('Gst', '1.0')
from gi.repository import GExiv2, Gst

from PyQt5.QtGui import QImage, QTransform
from PyQt5.QtCore import QSize, Qt, QIODevice, QBuffer


from raphodo.interprocess import (LoadBalancerWorker, ThumbnailExtractorArgument,
                          GenerateThumbnailsResults)

from raphodo.constants import (ThumbnailSize, ExtractionTask, ExtractionProcessing)
from raphodo.rpdfile import RPDFile, Video
from raphodo.utilities import stdchannel_redirected, show_errors
from raphodo.filmstrip import add_filmstrip
from raphodo.cache import ThumbnailCacheSql
import raphodo.exiftool as exiftool

have_gst = Gst.init_check(None)

def get_video_frame(full_file_name: str,
                    offset: Optional[float]=5.0,
                    caps=Gst.Caps.from_string('image/png')) -> bytes:
    """
    Source: https://gist.github.com/dplanella/5563018

    :param full_file_name: file and path of the video
    :param offset:
    :param caps:
    :return: gstreamer buffer
    """
    logging.debug("Using gstreamer to generate thumbnail from %s", full_file_name)
    pipeline = Gst.parse_launch('playbin')
    pipeline.props.uri = 'file://{}'.format(pathname2url(os.path.abspath(full_file_name)))
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
    if sample is not None:
        buffer = sample.get_buffer()
        pipeline.set_state(Gst.State.NULL)
        return buffer.extract_dup(0, buffer.get_size())
    else:
        return None

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

    max_size = QSize(max(ThumbnailSize.width, ThumbnailSize.height),
                     max(ThumbnailSize.width, ThumbnailSize.height))

    def __init__(self) -> None:
        self.thumbnail_size_needed = QSize(ThumbnailSize.width, ThumbnailSize.height)
        self.thumbnail_cache = ThumbnailCacheSql()
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
                             processing: set) -> PhotoDetails:

        full_file_name = rpd_file.full_file_name

        orientation = None
        thumbnail = None
        try:
            metadata = GExiv2.Metadata(full_file_name)
        except:
            logging.warning("Could not read metadata from %s", full_file_name)
            metadata = None

        if metadata is not None:
            try:
                orientation = metadata['Exif.Image.Orientation']
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
                elif thumbnail.width() > 160 or thumbnail.height() > 120:
                                processing.add(ExtractionProcessing.resize)
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
            processing.remove(ExtractionProcessing.orient)
            if thumbnail.isNull():
                thumbnail = None
                logging.warning(
                    "Unable to create a thumbnail out of the file: {}".format(full_file_name))

        return PhotoDetails(thumbnail, orientation)

    def get_orientation(self, rpd_file: RPDFile,
                        full_file_name: Optional[str]=None,
                        raw_bytes: Optional[bytearray]=None) -> Optional[str]:
        metadata = None
        if raw_bytes is not None:
            metadata = GExiv2.Metadata()
            try:
                if rpd_file.is_jpeg_type():
                    metadata.from_app1_segment(raw_bytes)
                else:
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

    def get_video_rotation(self, rpd_file: Video, file_source: str) -> Optional[str]:
        if rpd_file.load_metadata(self.exiftool_process, file_source=file_source):
            orientation = rpd_file.metadata.rotation(missing=None)
            # purge metadata, as it cannot be pickled
            rpd_file.metadata = None
            if orientation == 180:
                return self.rotate_180
            elif orientation == 90:
                return self.rotate_90
            elif orientation == 270:
                return self.rotate_270
        return None

    def check_for_stop(self, directive: bytes, content: bytes):
        if directive == b'cmd':
            assert content == b'STOP'
            return True
        return False

    def process_files(self):

        logging.debug("{} worker started".format(self.requester.identity.decode()))

        while True:
            directive, content = self.requester.recv_multipart()
            if self.check_for_stop(directive, content):
                break

            data = pickle.loads(content) # type: ThumbnailExtractorArgument

            # logging.debug("%s is working on %s", self.requester.identity.decode(),
            #               data.rpd_file.name)

            png_data = None
            orientation = None
            task = data.task
            processing = data.processing
            rpd_file = data.rpd_file

            try:
                if task == ExtractionTask.load_from_exif:
                    thumbnail_details = self.get_disk_photo_thumb(rpd_file, processing)
                    thumbnail = thumbnail_details.thumbnail
                    if thumbnail is not None:
                        orientation = thumbnail_details.orientation

                elif task == ExtractionTask.load_file_directly:
                    thumbnail = QImage(data.full_file_name_to_work_on)
                    if ExtractionProcessing.orient in processing:
                        orientation = self.get_orientation(rpd_file=rpd_file,
                                                   full_file_name=data.full_file_name_to_work_on)

                elif task == ExtractionTask.load_from_bytes:
                    thumbnail = QImage.fromData(data.thumbnail_bytes)
                    if thumbnail.width() > 160 or thumbnail.height() > 120:
                        processing.add(ExtractionProcessing.resize)
                        processing.remove(ExtractionProcessing.strip_bars_photo)
                    if data.exif_buffer and ExtractionProcessing.orient in processing:
                        orientation = self.get_orientation(rpd_file=rpd_file,
                                                           raw_bytes=data.exif_buffer)
                else:
                    assert task in (ExtractionTask.extract_from_file,
                                    ExtractionTask.extract_from_temp_file)
                    if not have_gst:
                        thumbnail = None
                    else:
                        png = get_video_frame(data.full_file_name_to_work_on, 0.0)
                        if png is None:
                            thumbnail = None
                            logging.warning("Could not extract video thumbnail from %s",
                                            data.rpd_file.get_display_full_name())
                        else:
                            thumbnail = QImage.fromData(png)
                            if thumbnail.isNull():
                                thumbnail = None
                            else:
                                processing.add(ExtractionProcessing.add_film_strip)
                                orientation = self.get_video_rotation(rpd_file,
                                                                    data.full_file_name_to_work_on)
                                if orientation is not None:
                                    processing.add(ExtractionProcessing.orient)
                                processing.add(ExtractionProcessing.resize)
                        if task == ExtractionTask.extract_from_temp_file:
                            os.remove(data.full_file_name_to_work_on)
                            rpd_file.temp_cache_full_file_chunk = ''

                if thumbnail is not None:
                    if ExtractionProcessing.strip_bars_photo in processing:
                        thumbnail = crop_160x120_thumbnail(thumbnail)
                    elif ExtractionProcessing.strip_bars_video in processing:
                        thumbnail = crop_160x120_thumbnail(thumbnail, 15)
                    elif ExtractionProcessing.resize in processing:
                        # Resize the thumbnail before rotating
                        if ((orientation == '1' or orientation is None) and
                                    thumbnail.height() > thumbnail.width()):
                            # Special case: pictures from some cellphones have already
                            # been rotated
                            thumbnail = thumbnail.scaled(
                                self.max_size,
                                Qt.KeepAspectRatio,
                                Qt.SmoothTransformation)
                        else:
                            thumbnail = thumbnail.scaled(
                                self.thumbnail_size_needed,
                                Qt.KeepAspectRatio,
                                Qt.SmoothTransformation)
                        if thumbnail.isNull():
                            thumbnail = None

                if orientation is not None and thumbnail is not None:
                    thumbnail =  self.rotate_thumb(thumbnail, orientation)

                if ExtractionProcessing.add_film_strip in processing and thumbnail is not None:
                    thumbnail = add_filmstrip(thumbnail)

                if thumbnail is not None:
                    buffer = qimage_to_png_buffer(thumbnail)
                    png_data = buffer.data()

                if data.use_thumbnail_cache:
                    orientation_unknown = (ExtractionProcessing.orient in processing and
                                         orientation is None)
                    self.thumbnail_cache.save_thumbnail(
                        full_file_name=rpd_file.full_file_name,
                        size=rpd_file.size,
                        modification_time=rpd_file.modification_time,
                        generation_failed=thumbnail is None,
                        orientation_unknown=orientation_unknown,
                        thumbnail=thumbnail,
                        camera_model=rpd_file.camera_model)
            except Exception as e:
                logging.error("Exception working on file %s", rpd_file.full_file_name)
                logging.error("Task: %s", task)
                logging.error("Processing tasks: %s", processing)
                logging.exception("Traceback:")

            self.sender.send_multipart([b'0', b'data',
                    pickle.dumps(
                    GenerateThumbnailsResults(
                        rpd_file=rpd_file,
                        thumbnail_bytes=png_data),
                    pickle.HIGHEST_PROTOCOL)])
            self.requester.send_multipart([b'', b'', b'OK'])

    def do_work(self):
        if False:
            context = show_errors()
            self.error_stream = sys.stderr
        else:
            # Redirect stderr, hiding error output from exiv2
            context = stdchannel_redirected(sys.stderr, os.devnull)
            self.error_stream = sys.stdout
        with context:
            with exiftool.ExifTool() as self.exiftool_process:
                self.process_files()
            self.exit()

if __name__ == "__main__":
    thumbnail_extractor = ThumbnailExtractor()