#!/usr/bin/env python3

# Copyright (C) 2015-2019 Damon Lynch <damonlynch@gmail.com>

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
__copyright__ = "Copyright 2015-2019, Damon Lynch"

import sys
import logging
from urllib.request import pathname2url
import pickle
import os
from collections import namedtuple
import tempfile
from datetime import datetime
from typing import Optional, Set, Union, Tuple

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

from PyQt5.QtGui import QImage, QTransform
from PyQt5.QtCore import QSize, Qt, QIODevice, QBuffer
try:
    import rawkit
    import rawkit.options
    import rawkit.raw
    have_rawkit = True
except ImportError:
    have_rawkit = False

from raphodo.interprocess import (
    LoadBalancerWorker, ThumbnailExtractorArgument, GenerateThumbnailsResults
)

from raphodo.constants import (
    ThumbnailSize, ExtractionTask, ExtractionProcessing, ThumbnailCacheStatus,
    ThumbnailCacheDiskStatus
)
from raphodo.rpdfile import RPDFile, Video, Photo
from raphodo.constants import FileType
from raphodo.utilities import stdchannel_redirected, show_errors, image_large_enough_fdo
from raphodo.filmstrip import add_filmstrip
from raphodo.cache import ThumbnailCacheSql, FdoCacheLarge, FdoCacheNormal
import raphodo.exiftool as exiftool


have_gst = Gst.init_check(None)


def gst_version() -> str:
    """
    :return: version of gstreamer, if it exists and is functioning, else ''
    """

    if have_gst:
        try:
            return Gst.version_string().replace('GStreamer ', '')
        except Exception:
            pass
    return ''


def libraw_version(suppress_errors: bool=True) -> str:
    """
    Return version number of libraw, using rawkit

    :param suppress_errors:
    :return: version number if available, else ''
    """

    if not have_rawkit:
        return ''

    import libraw.bindings
    try:
        return libraw.bindings.LibRaw().version
    except ImportError as e:
        if not suppress_errors:
            raise
        v = str(e)
        if v.startswith('Unsupported'):
            import re
            v = ''.join(re.findall(r'\d+\.?', str(e)))
            return v[:-1] if v.endswith('.') else v
        return v
    except Exception:
        if not suppress_errors:
            raise
        return ''


if not have_rawkit:
    have_functioning_rawkit = False
else:
    try:
        have_functioning_rawkit = bool(libraw_version(suppress_errors=False))
    except Exception:
        have_functioning_rawkit = False


def rawkit_version() -> str:
    if have_rawkit:
        if have_functioning_rawkit:
            return rawkit.VERSION
        else:
            return '{} (not functional)'.format(rawkit.VERSION)
    return ''


def get_video_frame(full_file_name: str,
                    offset: Optional[float]=5.0,
                    caps=Gst.Caps.from_string('image/png')) -> Optional[bytes]:
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
    offset = max(
        min(
            pipeline.query_duration(Gst.Format.TIME)[1] - Gst.SECOND / 4, offset * Gst.SECOND
        ), 0
    )

    try:
        assert pipeline.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH, offset)
    except AssertionError:
        logging.warning(
            'seek_simple() failed for %s. Is the necessary gstreamer plugin installed for this '
            'file format?', full_file_name
        )
        return None
    # Wait for seek to finish.
    pipeline.get_state(Gst.CLOCK_TIME_NONE)  # alternative is Gst.SECOND * 10
    sample = pipeline.emit('convert-sample', caps)
    if sample is not None:
        buffer = sample.get_buffer()
        pipeline.set_state(Gst.State.NULL)
        return buffer.extract_dup(0, buffer.get_size())
    else:
        return None

PhotoDetails = namedtuple('PhotoDetails', 'thumbnail, orientation')

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

    maxStandardSize = QSize(
        max(ThumbnailSize.width, ThumbnailSize.height),
        max(ThumbnailSize.width, ThumbnailSize.height)
    )

    def __init__(self) -> None:
        self.thumbnailSizeNeeded = QSize(ThumbnailSize.width, ThumbnailSize.height)
        self.thumbnail_cache = ThumbnailCacheSql(create_table_if_not_exists=False)
        self.fdo_cache_large = FdoCacheLarge()
        self.fdo_cache_normal = FdoCacheNormal()

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

        return (
            size.width() >= self.thumbnailSizeNeeded.width() or
            size.height() >= self.thumbnailSizeNeeded.height()
        )

    def _extract_256_thumb(self, rpd_file: RPDFile,
                          processing: Set[ExtractionProcessing],
                          orientation: Optional[str]) -> PhotoDetails:

        thumbnail = None
        data = rpd_file.metadata.get_preview_256()
        if isinstance(data, bytes):
            thumbnail = QImage.fromData(data)
            if thumbnail.isNull():
                thumbnail = None
            else:
                if thumbnail.width() > 160 or thumbnail.height() > 120:
                    processing.add(ExtractionProcessing.resize)

        return PhotoDetails(thumbnail, orientation)

    def _extract_metadata(self, rpd_file: RPDFile,
                          processing: Set[ExtractionProcessing]) -> PhotoDetails:

        thumbnail = orientation = None
        try:
            orientation = rpd_file.metadata.orientation()
        except Exception:
            pass

        rpd_file.mdatatime = rpd_file.metadata.timestamp(missing=0.0)

        # Not all files have an exif preview, but some do
        # (typically CR2, ARW, PEF, RW2).
        # If they exist, they are (almost!) always 160x120

        # TODO how about thumbnail_cache_status?
        if self.write_fdo_thumbnail and rpd_file.fdo_thumbnail_256 is None:
            photo_details = self._extract_256_thumb(
                rpd_file=rpd_file, processing=processing, orientation=orientation
            )
            if photo_details.thumbnail is not None:
                return photo_details
            # if no valid preview found, fall back to the code below and make do with the best
            # we can get

        preview = rpd_file.metadata.get_small_thumbnail_or_first_indexed_preview()
        if preview:
            thumbnail = QImage.fromData(preview)
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
        return PhotoDetails(thumbnail, orientation)

    def get_disk_photo_thumb(self, rpd_file: Photo,
                             full_file_name: str,
                             processing: Set[ExtractionProcessing]) -> PhotoDetails:
        """
        Get the photo's thumbnail from a file that is on disk.

        Sets rpd_file's mdatatime.

        :param rpd_file: file details
        :param full_file_name: full name of the file from which to get the metadata
        :param processing: processing extraction tasks to complete
        :return: thumbnail and its orientation
        """

        orientation = None
        thumbnail = None
        photo_details = PhotoDetails(thumbnail, orientation)
        if rpd_file.load_metadata(full_file_name=full_file_name, et_process=self.exiftool_process):
            photo_details = self._extract_metadata(rpd_file, processing)
            thumbnail = photo_details.thumbnail

        if thumbnail is not None:
            return photo_details
        elif rpd_file.is_raw() and have_functioning_rawkit:
            try:
                with rawkit.raw.Raw(filename=full_file_name) as raw:
                    raw.options.white_balance = rawkit.options.WhiteBalance(camera=True, auto=False)
                    if rpd_file.cache_full_file_name and not rpd_file.download_full_file_name:
                        temp_file = '{}.tiff'.format(os.path.splitext(full_file_name)[0])
                        cache_dir = os.path.dirname(rpd_file.cache_full_file_name)
                        if os.path.isdir(cache_dir):
                            temp_file = os.path.join(cache_dir, temp_file)
                            temp_dir = None
                        else:
                            temp_dir = tempfile.mkdtemp(prefix="rpd-tmp-")
                            temp_file = os.path.join(temp_dir, temp_file)
                    else:
                        temp_dir = tempfile.mkdtemp(prefix="rpd-tmp-")
                        name = os.path.basename(full_file_name)
                        temp_file = '{}.tiff'.format(os.path.splitext(name)[0])
                        temp_file = os.path.join(temp_dir, temp_file)
                    try:
                        logging.debug("Saving temporary rawkit render to %s", temp_file)
                        raw.save(filename=temp_file)
                    except Exception:
                        logging.exception(
                            "Rendering %s failed. Exception:", rpd_file.full_file_name
                        )
                    else:
                        thumbnail = QImage(temp_file)
                        os.remove(temp_file)
                        if thumbnail.isNull():
                            logging.debug("Qt failed to load rendered %s", rpd_file.full_file_name)
                            thumbnail = None
                        else:
                            logging.debug("Rendered %s using libraw", rpd_file.full_file_name)
                            processing.add(ExtractionProcessing.resize)

                            # libraw already correctly oriented the thumbnail
                            processing.remove(ExtractionProcessing.orient)
                            orientation = '1'
                if temp_dir:
                    os.rmdir(temp_dir)
            except ImportError as e:
                logging.warning(
                    'Cannot use rawkit to render thumbnail for %s', rpd_file.full_file_name
                )
            except Exception as e:
                logging.exception(
                    "Rendering thumbnail for %s not supported. Exception:", rpd_file.full_file_name
                )

        if thumbnail is None and rpd_file.is_loadable():
            thumbnail = QImage(full_file_name)
            processing.add(ExtractionProcessing.resize)
            if not rpd_file.from_camera:
                processing.remove(ExtractionProcessing.orient)
            if thumbnail.isNull():
                thumbnail = None
                logging.warning(
                    "Unable to create a thumbnail out of the file: {}".format(full_file_name)
                )

        return PhotoDetails(thumbnail, orientation)

    def get_from_buffer(self, rpd_file: Photo,
                        raw_bytes: bytearray,
                        processing: Set[ExtractionProcessing]) -> PhotoDetails:
        if not rpd_file.load_metadata(raw_bytes=raw_bytes, et_process=self.exiftool_process):
            # logging.warning("Extractor failed to load metadata from extract of %s", rpd_file.name)
            return PhotoDetails(None, None)
        else:
            return self._extract_metadata(rpd_file, processing)

    def get_photo_orientation(self, rpd_file: Photo,
                              full_file_name: Optional[str]=None,
                              raw_bytes: Optional[bytearray]=None) -> Optional[str]:

        if rpd_file.metadata is None:
            self.load_photo_metadata(
                rpd_file=rpd_file, full_file_name=full_file_name, raw_bytes=raw_bytes
            )

        if rpd_file.metadata is not None:
            try:
                return rpd_file.metadata.orientation()
            except Exception:
                pass
        return None

    def assign_mdatatime(self, rpd_file: Union[Photo, Video],
                         full_file_name: Optional[str]=None,
                         raw_bytes: Optional[bytearray]=None) -> None:
        """
        Load the file's metadata and assign the metadata time to the rpd file
        """

        if rpd_file.file_type == FileType.photo:
            self.assign_photo_mdatatime(
                rpd_file=rpd_file, full_file_name=full_file_name, raw_bytes=raw_bytes
            )
        else:
            self.assign_video_mdatatime(rpd_file=rpd_file, full_file_name=full_file_name)

    def assign_photo_mdatatime(self, rpd_file: Photo,
                               full_file_name: Optional[str]=None,
                               raw_bytes: Optional[bytearray]=None) -> None:
        """
        Load the photo's metadata and assign the metadata time to the rpd file
        """

        self.load_photo_metadata(
            rpd_file=rpd_file, full_file_name=full_file_name, raw_bytes=raw_bytes
        )
        if rpd_file.metadata is not None and rpd_file.date_time() is None:
            rpd_file.mdatatime = 0.0

    def load_photo_metadata(self, rpd_file: Photo,
                        full_file_name: Optional[str]=None,
                        raw_bytes: Optional[bytearray]=None) -> None:
        """
        Load the photo's metadata into the rpd file
        """

        if raw_bytes is not None:
            if rpd_file.is_jpeg_type():
                rpd_file.load_metadata(app1_segment=raw_bytes, et_process=self.exiftool_process)
            else:
                rpd_file.load_metadata(raw_bytes=raw_bytes, et_process=self.exiftool_process)
        else:
            rpd_file.load_metadata(full_file_name=full_file_name, et_process=self.exiftool_process)

    def assign_video_mdatatime(self, rpd_file: Video, full_file_name: str) -> None:
        """
        Load the video's metadata and assign the metadata time to the rpd file
        """

        if rpd_file.metadata is None:
            rpd_file.load_metadata(full_file_name=full_file_name, et_process=self.exiftool_process)
        if rpd_file.date_time() is None:
            rpd_file.mdatatime = 0.0

    def get_video_rotation(self, rpd_file: Video, full_file_name: str) -> Optional[str]:
        """
        Some videos have a rotation tag. If this video does, return it.
        """

        if rpd_file.metadata is None:
            rpd_file.load_metadata(full_file_name=full_file_name, et_process=self.exiftool_process)
        orientation = rpd_file.metadata.rotation(missing=None)
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

    def extract_thumbnail(self, task: ExtractionTask,
                          rpd_file: Union[Photo, Video],
                          processing: Set[ExtractionProcessing],
                          data: ThumbnailExtractorArgument
                          ) -> Tuple[Optional[QImage], Optional[str]]:
        """
        Extract the thumbnail using one of a variety of methods,
        depending on the file

        :param task: extraction task to perform
        :param rpd_file: rpd_file to work on
        :param processing: processing tasks
        :param data: some other processing arguments passed to this process
        :return: thumbnail and its orientation, if found
        """

        orientation = None

        if task == ExtractionTask.load_from_exif:
            thumbnail_details = self.get_disk_photo_thumb(
                rpd_file, data.full_file_name_to_work_on, processing
            )
            thumbnail = thumbnail_details.thumbnail
            if thumbnail is not None:
                orientation = thumbnail_details.orientation

        elif task in (ExtractionTask.load_file_directly,
                      ExtractionTask.load_file_and_exif_directly,
                      ExtractionTask.load_file_directly_metadata_from_secondary):
            thumbnail = QImage(data.full_file_name_to_work_on)

            if task == ExtractionTask.load_file_and_exif_directly:
                self.assign_photo_mdatatime(
                    rpd_file=rpd_file, full_file_name=data.full_file_name_to_work_on
                )
            elif task == ExtractionTask.load_file_directly_metadata_from_secondary:
                self.assign_mdatatime(
                    rpd_file=rpd_file, full_file_name=data.secondary_full_file_name
                )

            if ExtractionProcessing.orient in processing:
                orientation = self.get_photo_orientation(
                    rpd_file=rpd_file, full_file_name=data.full_file_name_to_work_on
                )

        elif task in (ExtractionTask.load_from_bytes,
                      ExtractionTask.load_from_bytes_metadata_from_temp_extract):
            try:
                assert data.thumbnail_bytes is not None
            except AssertionError:
                logging.error(
                    "Thumbnail bytes not extracted for %s (value is None)",
                    rpd_file.get_current_full_file_name()
                )
            thumbnail = QImage.fromData(data.thumbnail_bytes)
            if thumbnail.width() > self.thumbnailSizeNeeded.width() or thumbnail.height()\
                    > self.thumbnailSizeNeeded.height():
                processing.add(ExtractionProcessing.resize)
                processing.remove(ExtractionProcessing.strip_bars_photo)
            if data.exif_buffer and ExtractionProcessing.orient in processing:
                orientation = self.get_photo_orientation(
                    rpd_file=rpd_file, raw_bytes=data.exif_buffer
                )
            if task == ExtractionTask.load_from_bytes_metadata_from_temp_extract:
                self.assign_mdatatime(
                    rpd_file=rpd_file, full_file_name=data.secondary_full_file_name
                )
                orientation = rpd_file.metadata.orientation()
                os.remove(data.secondary_full_file_name)
                rpd_file.temp_cache_full_file_chunk = ''

        elif task == ExtractionTask.load_from_exif_buffer:
            thumbnail_details = self.get_from_buffer(rpd_file, data.exif_buffer, processing)
            thumbnail = thumbnail_details.thumbnail
            if thumbnail is not None:
                orientation = thumbnail_details.orientation
        else:
            assert task in (
                ExtractionTask.extract_from_file, ExtractionTask.extract_from_file_and_load_metadata
            )
            if rpd_file.file_type == FileType.photo:
                self.assign_photo_mdatatime(
                    rpd_file=rpd_file, full_file_name=data.full_file_name_to_work_on
                )
                thumbnail_bytes = rpd_file.metadata.get_small_thumbnail_or_first_indexed_preview()
                if thumbnail_bytes:
                    thumbnail = QImage.fromData(thumbnail_bytes)
                    orientation = rpd_file.metadata.orientation()
            else:
                assert rpd_file.file_type == FileType.video

                if ExtractionTask.extract_from_file_and_load_metadata:
                    self.assign_video_mdatatime(
                        rpd_file=rpd_file, full_file_name=data.full_file_name_to_work_on
                    )
                if not have_gst:
                    thumbnail = None
                else:
                    png = get_video_frame(data.full_file_name_to_work_on, 0.0)
                    if not png:
                        thumbnail = None
                        logging.warning(
                            "Could not extract video thumbnail from %s",
                            data.rpd_file.get_display_full_name()
                        )
                    else:
                        thumbnail = QImage.fromData(png)
                        if thumbnail.isNull():
                            thumbnail = None
                        else:
                            processing.add(ExtractionProcessing.add_film_strip)
                            orientation = self.get_video_rotation(
                                rpd_file, data.full_file_name_to_work_on
                            )
                            if orientation is not None:
                                processing.add(ExtractionProcessing.orient)
                            processing.add(ExtractionProcessing.resize)

        return thumbnail, orientation

    def process_files(self):
        """
        Loop continuously processing photo and video thumbnails
        """

        logging.debug("{} worker started".format(self.requester.identity.decode()))

        while True:
            directive, content = self.requester.recv_multipart()
            if self.check_for_stop(directive, content):
                break

            data = pickle.loads(content) # type: ThumbnailExtractorArgument

            thumbnail_256 = png_data = None
            task = data.task
            processing = data.processing
            rpd_file = data.rpd_file

            logging.debug(
                "Working on task %s for %s", task.name, rpd_file.download_name or rpd_file.name
            )

            self.write_fdo_thumbnail = data.write_fdo_thumbnail

            try:
                if rpd_file.fdo_thumbnail_256 is not None and data.write_fdo_thumbnail:
                    if rpd_file.thumbnail_status != ThumbnailCacheStatus.fdo_256_ready:
                        logging.error(
                            "Unexpected thumbnail cache status for %s: %s",
                            rpd_file.full_file_name, rpd_file.thumbnail_status.name
                        )
                    thumbnail = thumbnail_256 = QImage.fromData(rpd_file.fdo_thumbnail_256)
                    orientation_unknown = False
                else:
                    thumbnail, orientation = self.extract_thumbnail(
                        task, rpd_file, processing, data
                    )

                    if data.file_to_work_on_is_temporary:
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
                                    self.maxStandardSize,
                                    Qt.KeepAspectRatio,
                                    Qt.SmoothTransformation
                                )
                            else:
                                if rpd_file.should_write_fdo() and \
                                        image_large_enough_fdo(thumbnail.size()) \
                                        and max(thumbnail.height(), thumbnail.width()) > 256:
                                    thumbnail_256 = thumbnail.scaled(
                                        QSize(256, 256),
                                        Qt.KeepAspectRatio,
                                        Qt.SmoothTransformation
                                    )
                                    thumbnail = thumbnail_256
                                if data.send_thumb_to_main:
                                    thumbnail = thumbnail.scaled(
                                        self.thumbnailSizeNeeded,
                                        Qt.KeepAspectRatio,
                                        Qt.SmoothTransformation
                                    )
                                else:
                                    thumbnail = None

                            if not thumbnail is None and thumbnail.isNull():
                                thumbnail = None

                    if orientation is not None:
                        if thumbnail is not None:
                            thumbnail =  self.rotate_thumb(thumbnail, orientation)
                        if thumbnail_256 is not None:
                            thumbnail_256 = self.rotate_thumb(thumbnail_256, orientation)

                    if ExtractionProcessing.add_film_strip in processing:
                        if thumbnail is not None:
                            thumbnail = add_filmstrip(thumbnail)
                        if thumbnail_256 is not None:
                            thumbnail = add_filmstrip(thumbnail_256)

                    if thumbnail is not None:
                        buffer = qimage_to_png_buffer(thumbnail)
                        png_data = buffer.data()

                    orientation_unknown = (
                        ExtractionProcessing.orient in processing and orientation is None
                    )

                    if data.send_thumb_to_main and data.use_thumbnail_cache and \
                            rpd_file.thumbnail_cache_status == ThumbnailCacheDiskStatus.not_found:
                        self.thumbnail_cache.save_thumbnail(
                            full_file_name=rpd_file.full_file_name,
                            size=rpd_file.size,
                            mtime=rpd_file.modification_time,
                            mdatatime=rpd_file.mdatatime,
                            generation_failed=thumbnail is None,
                            orientation_unknown=orientation_unknown,
                            thumbnail=thumbnail,
                            camera_model=rpd_file.camera_model
                        )

                if (thumbnail is not None or thumbnail_256 is not None) and \
                        rpd_file.should_write_fdo():
                    if self.write_fdo_thumbnail:
                        # The modification time of the file may have changed when the file was saved
                        # Ideally it shouldn't, but it does sometimes, e.g. on NTFS!
                        # So need to get the modification time from the saved file.
                        mtime = os.path.getmtime(rpd_file.download_full_file_name)

                        if thumbnail_256 is not None:
                            rpd_file.fdo_thumbnail_256_name = self.fdo_cache_large.save_thumbnail(
                                full_file_name=rpd_file.download_full_file_name,
                                size=rpd_file.size,
                                modification_time=mtime,
                                generation_failed=False,
                                thumbnail=thumbnail_256,
                                free_desktop_org=False
                            )
                            thumbnail_128 = thumbnail_256.scaled(
                                    QSize(128, 128),
                                    Qt.KeepAspectRatio,
                                    Qt.SmoothTransformation
                            )
                        else:
                            thumbnail_128 = thumbnail.scaled(
                                QSize(128, 128),
                                Qt.KeepAspectRatio,
                                Qt.SmoothTransformation
                            )
                        rpd_file.fdo_thumbnail_128_name = self.fdo_cache_normal.save_thumbnail(
                            full_file_name=rpd_file.download_full_file_name,
                            size=rpd_file.size,
                            modification_time=mtime,
                            generation_failed=False,
                            thumbnail=thumbnail_128,
                            free_desktop_org=False
                        )
                    elif thumbnail_256 is not None and rpd_file.fdo_thumbnail_256 is None:
                        rpd_file.fdo_thumbnail_256 = qimage_to_png_buffer(thumbnail).data()

                if thumbnail is not None:
                    if orientation_unknown:
                        rpd_file.thumbnail_status = ThumbnailCacheStatus.orientation_unknown
                    elif rpd_file.fdo_thumbnail_256 is not None:
                        rpd_file.thumbnail_status = ThumbnailCacheStatus.fdo_256_ready
                    else:
                        rpd_file.thumbnail_status = ThumbnailCacheStatus.ready

            except SystemExit as e:
                self.exiftool_process.terminate()
                sys.exit(e)
            except:
                logging.error("Exception working on file %s", rpd_file.full_file_name)
                logging.error("Task: %s", task)
                logging.error("Processing tasks: %s", processing)
                logging.exception("Traceback:")

            # Purge metadata, as it cannot be pickled
            if not data.send_thumb_to_main:
                png_data = None
            rpd_file.metadata = None
            self.sender.send_multipart(
                [
                    b'0', b'data',
                    pickle.dumps(
                        GenerateThumbnailsResults(rpd_file=rpd_file, thumbnail_bytes=png_data),
                        pickle.HIGHEST_PROTOCOL
                    )
                ]
            )
            self.requester.send_multipart([b'', b'', b'OK'])

    def do_work(self):
        if False:
            # exiv2 pumps out a LOT to stderr - use cautiously!
            context = show_errors()
            self.error_stream = sys.stderr
        else:
            # Redirect stderr, hiding error output from exiv2
            context = stdchannel_redirected(sys.stderr, os.devnull)
            self.error_stream = sys.stdout
        with context:
            # In some situations, using a context manager for exiftool can
            # result in exiftool processes not being terminated. So let's
            # handle starting and terminating it manually.
            self.exiftool_process = exiftool.ExifTool()
            self.exiftool_process.start()
            self.process_files()
            self.exit()

    def cleanup_pre_stop(self) -> None:
        logging.debug(
            "Terminating thumbnail extractor ExifTool process for %s", self.identity.decode()
        )
        self.exiftool_process.terminate()

if __name__ == "__main__":
    thumbnail_extractor = ThumbnailExtractor()