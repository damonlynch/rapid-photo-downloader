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

import shlex
import subprocess
from enum import IntEnum
import os
import datetime
import resource

from gi.repository import GExiv2
from PyQt5.QtGui import QImage

from utilities import format_size_for_user


page_size = resource.getpagesize()
to_kb = page_size // 1024

vmtouch_cmd = 'vmtouch -v "{}"'


class PreviewSource(IntEnum):
    preview_1 = 0
    preview_2 = 1
    preview_3 = 2
    preview_4 = 3
    preview_5 = 4
    preview_6 = 5


class PhotoAttributes:
    def __init__(self, full_file_name: str, ext: str, metadata: GExiv2.Metadata) -> None:

        self.datetime = None # type: datetime.datetime
        self.iso = None # type: int
        self.height = None # type: int
        self.width = None # type: int
        self.model = None  # type: str
        self.has_gps = False  # type: bool
        self.orientation = None # type: str
        self.no_previews = None # type: int
        self.has_exif_thumbnail = False # type: bool
        self.exif_thumbnail_height = None # type: int
        self.exif_thumbnail_width = None # type: int
        self.exif_thumbnail_details = None # type: str
        self.preview_source = None # type: PreviewSource
        self.preview_width = None # type: int
        self.preview_height = None # type: int
        self.preview_extension = None  # type: str
        self.exif_thumbnail_and_preview_identical = None # type: bool
        self.preview_size_and_types = []
        self.minimum_exif_read_size_in_bytes_orientation = None # type: int
        self.minimum_exif_read_size_in_bytes_datetime = None # type: int
        self.bytes_cached_post_previews = None
        self.in_memory_post_previews = None

        self.file_name = full_file_name
        self.ext = ext

        # Before doing anything else, understand what has already
        # been cached after simply reading the exif
        self.bytes_cached, self.total, self.in_memory = vmtouch_output(full_file_name)

        # Get information about the photo
        self.assign_photo_attributes(metadata)
        self.extract_thumbnail(metadata)
        self.bytes_cached_post_thumb, total, self.in_memory_post_thumb = vmtouch_output(
            full_file_name)
        self.get_preview_sizes(metadata)
        self.bytes_cached_post_previews, total, self.in_memory_post_previews = vmtouch_output(
            full_file_name)

        if self.orientation is not None:
            self.minimum_extract_for_tag(self.orientation_extract)
        if self.datetime is not None:
            self.minimum_extract_for_tag(self.datetime_extract)

    def assign_photo_attributes(self, metadata: GExiv2.Metadata) -> None:
        # I don't know how GExiv2 gets these values:
        self.width = metadata.get_pixel_width()
        self.height = metadata.get_pixel_height()
        try:
            self.orientation = metadata['Exif.Image.Orientation']
        except KeyError:
            pass
        if 'Exif.Image.Make' in metadata and 'Exif.Image.Model' in metadata:
            self.model = '{} {}'.format(metadata['Exif.Image.Make'].strip(),
                                   metadata['Exif.Image.Model'].strip())
        self.has_gps = metadata.get_gps_info()[0]
        self.iso = metadata.get_iso_speed()
        try:
            self.datetime = metadata.get_date_time()
        except (KeyError, ValueError):
            pass

    def extract_thumbnail(self, metadata: GExiv2.Metadata) -> None:
        # not all files have an exif preview, but all CR2 seem to
        exif_thumbnail = metadata.get_exif_thumbnail()
        if exif_thumbnail:
            # Get the thumbnail but don't save it
            self.has_exif_thumbnail = True
            qimage = QImage.fromData(exif_thumbnail)
            if not qimage.isNull():
                self.exif_thumbnail_width = qimage.width()
                self.exif_thumbnail_height = qimage.height()
                self.exif_thumbnail_details = '{}x{}'.format(self.exif_thumbnail_width,
                                                 self.exif_thumbnail_height)

        previews = metadata.get_preview_properties()
        self.no_previews = len(previews)

        for idx, preview in enumerate(previews):
            image = metadata.get_preview_image(preview)
            if image.get_width() >= 160 and image.get_height() >= 120:
                # Get the thumbnail but don't save it
                preview_thumbnail = metadata.get_preview_image(preview).get_data()
                if self.has_exif_thumbnail:
                    self.exif_thumbnail_and_preview_identical = preview_thumbnail == exif_thumbnail
                self.preview_source = PreviewSource(idx).name.replace('_', ' ').capitalize()
                self.preview_width = image.get_width()
                self.preview_height = image.get_height()
                self.preview_extension = image.get_extension()
                return

    def get_preview_sizes(self, metadata: GExiv2.Metadata):
        previews = metadata.get_preview_properties()
        sizes_and_types = []
        for idx, preview in enumerate(previews):
            image = metadata.get_preview_image(preview)
            sizes_and_types.append((image.get_width(), image.get_height(),
                                                image.get_extension()))
        self.preview_size_and_types = '; '.join(['{}x{} {}'.format(width, height, ext[1:]) for
                                                 width, height, ext in sizes_and_types])

    def orientation_extract(self, metadata: GExiv2.Metadata, size_in_bytes):
        if metadata['Exif.Image.Orientation'] == self.orientation:
            self.minimum_exif_read_size_in_bytes_orientation = size_in_bytes
            return True
        return False

    def datetime_extract(self, metadata: GExiv2.Metadata, size_in_bytes):
        if metadata.get_date_time() == self.datetime:
            self.minimum_exif_read_size_in_bytes_datetime = size_in_bytes
            return True
        return False

    def minimum_extract_for_tag(self, check_extract):
        if self.ext == 'CRW':
            # Exiv2 can crash while scanning for exif in a very small
            # extract of a CRW file
            return
        metadata = GExiv2.Metadata()
        for size_in_bytes in exif_scan_range():
            with open(self.file_name, 'rb') as photo:
                photo_extract = photo.read(size_in_bytes)
                try:
                    metadata.open_buf(photo_extract)
                except:
                    pass
                else:
                    try:
                        if check_extract(metadata, size_in_bytes):
                            break
                    except KeyError:
                        pass

    def __repr__(self):
        if self.model:
            s = self.model
        elif self.file_name:
            s = os.path.split(self.file_name)[1]
        else:
            return "Unknown photo"
        if self.width:
            s += ' {}x{}'.format(self.width, self.height)
        if self.ext:
            s += ' {}'.format(self.ext)
        return s

    def __str__(self):
        s = ''
        if self.model is not None:
            s += '{}\n'.format(self.model)
        elif self.file_name is not None:
            s += '{}\n'.format(os.path.split(self.file_name)[1])
        if self.width is not None:
            s += '{}x{}\n'.format(self.width, self.height)
        if self.datetime: # type: datetime.datetime
            s += '{}\n'.format(self.datetime.strftime('%c'))
        if self.iso:
            s += 'ISO: {}\n'.format(self.iso)
        if self.orientation is not None:
            s += 'Orientation: {}\n'.format(self.orientation)
        if self.has_gps:
            s += 'Has GPS tag: True\n'
        if self.has_exif_thumbnail:
            s += 'Exif thumbnail: {}\n'.format(self.exif_thumbnail_details)
        if self.preview_source is not None:
            s += '{} of {}: {}x{} {}\n'.format(
                              self.preview_source,
                              self.no_previews,
                              self.preview_width, self.preview_height,
                              self.preview_extension[1:])
        if self.exif_thumbnail_and_preview_identical == False:
            # Check against False as value is one of None, True or
            # False
            s += 'Exif thumbnail differs from smallest preview\n'
        if self.preview_size_and_types:
            s += 'All preview images: {}\n'.format(self.preview_size_and_types)
        s += 'Disk cache after exif read:\n[{}]\n'.format(self.in_memory)
        if self.in_memory != self.in_memory_post_thumb:
            s += 'Disk cache after thumbnail / preview extraction:\n[{}]\n'.format(
                self.in_memory_post_thumb)
        if self.bytes_cached == self.bytes_cached_post_thumb:
            s += 'Cached: {:,}KB of {:,}KB\n'.format(self.bytes_cached, self.total)
        else:
            s += 'Cached: {:,}KB(+{:,}KB after extraction) of {:,}KB\n'.format(
                self.bytes_cached, self.bytes_cached_post_thumb, self.total)
        if self.minimum_exif_read_size_in_bytes_orientation is not None:
            s += 'Minimum read size to extract orientation tag: {}\n'.format(
                format_size_for_user(self.minimum_exif_read_size_in_bytes_orientation,
                                     with_decimals=False))
        if self.minimum_exif_read_size_in_bytes_orientation is None and self.orientation is not \
                None:
            s += 'Could not extract orientation tag with minimal read\n'
        if self.minimum_exif_read_size_in_bytes_datetime is not None:
            s += 'Minimum read size to extract datetime tag: {}\n'.format(
                format_size_for_user(self.minimum_exif_read_size_in_bytes_datetime,
                                     with_decimals=False))
        if self.minimum_exif_read_size_in_bytes_datetime is None and self.datetime is not None:
            s += 'Could not extract datetime tag with minimal read\n'
        return s


def exif_scan_range() -> iter:
    stop = 20
    for iterations, step in ((108, 1), (97, 4), (16, 32), (16, 256), (16, 512), (8, 1024),
                             (8, 2048 * 4), (32, 2048 * 16)):
        start = stop
        stop = start + step * iterations
        for b in range(start, stop, step):
            yield b

def vmtouch_output(full_file_name: str) -> tuple:
    command = shlex.split(vmtouch_cmd.format(full_file_name))
    output = subprocess.check_output(command, universal_newlines=True) # type: str
    for line in output.split('\n'):
        line = line.strip()
        if line.startswith('['):
            in_memory = line[1:line.find(']')]
            currently_paged_percent = line.rsplit(' ', 1)[-1]
            num, denom = map(int, currently_paged_percent.split('/'))
            return (num * to_kb, denom * to_kb, in_memory)