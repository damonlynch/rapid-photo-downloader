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

"""
Collects attributes about varieties of photo formats, including how much of the file
has to be read in order to extract exif information or a preview.
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2015-2016, Damon Lynch"

import shlex
import subprocess
from enum import IntEnum
import os
import datetime
import resource
from typing import Optional, Dict, Union

import gi
gi.require_version('GExiv2', '0.10')
from gi.repository import GExiv2
from PyQt5.QtGui import QImage

from raphodo.utilities import format_size_for_user
from raphodo.metadataphoto import MetaData

page_size = resource.getpagesize()
to_kb = page_size // 1024

vmtouch_cmd = 'vmtouch -v "{}"'

JPEG_EXTENSIONS = ['jpg', 'jpe', 'jpeg']

class PreviewSource(IntEnum):
    preview_1 = 0
    preview_2 = 1
    preview_3 = 2
    preview_4 = 3
    preview_5 = 4
    preview_6 = 5


class PhotoAttributes:
    def __init__(self, full_file_name: str, ext: str, metadata: GExiv2.Metadata,
                 exiftool_process) -> None:
        self.exiftool_process = exiftool_process
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
        self.all_exif_values = dict()  # type: Dict[str, Union[int, str, float, datetime.datetime]]
        self.has_app0 = None
        self.preview_source = None # type: PreviewSource
        self.preview_width = None # type: int
        self.preview_height = None # type: int
        self.preview_extension = None  # type: str
        self.exif_thumbnail_and_preview_identical = None  # type: bool
        self.preview_size_and_types = []
        self.minimum_exif_read_size_in_bytes_orientation = None  # type: int
        self.minimum_exif_read_size_in_bytes_datetime = None  # type: int
        self.minimum_exif_read_size_in_bytes_all = None  # type: int
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

        if self.orientation is not None or self.ext.lower() in JPEG_EXTENSIONS:
            self.minimum_extract_for_tag(self.orientation_extract)

        if self.datetime is not None:
            self.minimum_extract_for_tag(self.datetime_extract)

        self.minimum_extract_for_all(metadata)

    def assign_photo_attributes(self, metadata: GExiv2.Metadata) -> None:
        # I don't know how GExiv2 gets these values:
        self.width = metadata.get_pixel_width()
        self.height = metadata.get_pixel_height()
        try:
            self.orientation = metadata.get_tag_string('Exif.Image.Orientation')
        except KeyError:
            pass
        if metadata.has_tag('Exif.Image.Make') and metadata.has_tag('Exif.Image.Model'):
            self.model = '{} {}'.format(metadata.get_tag_string('Exif.Image.Make').strip(),
                                   metadata.get_tag_string('Exif.Image.Model').strip())
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
        elif self.ext.lower() in JPEG_EXTENSIONS:
            return self.read_jpeg_2(check_extract)

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

    def minimum_extract_for_all(self, metadata: MetaData) -> None:
        if self.ext == 'CRW':
            # Exiv2 can crash while scanning for exif in a very small
            # extract of a CRW file
            return

        funcs = 'aperture iso exposure_time focal_length camera_make camera_model camera_serial ' \
                 'shutter_count owner_name copyright artist short_camera_model ' \
                 'date_time timestamp sub_seconds orientation'.split()
        for f in funcs:
            v = getattr(metadata, f)()
            if v:
                self.all_exif_values[f] = v

        found = set()

        for size_in_bytes in exif_scan_range():
            with open(self.file_name, 'rb') as photo:
                photo_extract = photo.read(size_in_bytes)
                try:
                    metadata_extract = MetaData(raw_bytes=bytearray(photo_extract),
                                                et_process=self.exiftool_process)
                except:
                    pass
                else:
                    try:
                        for tag in self.all_exif_values:
                            if (tag not in found and
                                    getattr(metadata_extract, tag)() == self.all_exif_values[tag]):
                                found.add(tag)
                                if len(found) == len(self.all_exif_values):
                                    self.minimum_exif_read_size_in_bytes_all = size_in_bytes
                                    return
                    except KeyError:
                        pass



    def get_jpeg_exif_length(self) -> Optional[int]:
        app0_data_length = 0
        soi_marker_length = 2
        marker_length = 2
        with open(self.file_name, 'rb') as jpeg:
            soi_marker = jpeg.read(2)
            if soi_marker != b'\xff\xd8':
                print("Not a jpeg image: no SOI marker")
                return None

            app_marker = jpeg.read(2)
            if app_marker == b'\xff\xe0':
                # Don't neeed the content of APP0
                app0_data_length = jpeg.read(1)[0] * 256 + jpeg.read(1)[0]
                app0 = jpeg.read(app0_data_length - 2)
                app_marker = jpeg.read(2)
                app0_data_length = app0_data_length + marker_length

            if app_marker != b'\xff\xe1':
                print("Could not locate APP1 marker")
                return None

            header = jpeg.read(8)
            if header[2:6] != b'Exif' or header[6:8] != b'\x00\x00':
                print("APP1 is malformed")
                return None
        app1_data_length = header[0] * 256 + header[1]
        return soi_marker_length + marker_length + app1_data_length + app0_data_length

    def read_jpeg(self, check_extract) -> Optional[int]:
        length = self.get_jpeg_exif_length()
        # print("Got exif length of", length)
        if length is not None:
            metadata = GExiv2.Metadata()
            with open(self.file_name, 'rb') as photo:
                photo_extract = photo.read(length)
                try:
                    metadata.open_buf(photo_extract)
                    # print("read exif okay :-)")
                except:
                    print("Failed to read exif!")
                else:
                    try:
                        if not check_extract(metadata, length):
                            print("Read exif okay, but failed to get value from exif!")
                    except KeyError:
                        print("Read exif okay, but failed to get value from exif!")

    def read_jpeg_2(self, check_extract) -> None:

        # Step 1: determine the location of APP1 in the jpeg file
        # See http://dev.exiv2.org/projects/exiv2/wiki/The_Metadata_in_JPEG_files

        app0_data_length = 0

        soi_marker_length = 2
        marker_length = 2
        exif_header_length = 8
        read0_size = soi_marker_length + marker_length + exif_header_length
        app_length_length = 2

        with open(self.file_name, 'rb') as jpeg:
            jpeg_header = jpeg.read(read0_size)


            if jpeg_header[0:2] != b'\xff\xd8':
                print("%s not a jpeg image: no SOI marker" % self.file_name)
                return None

            app_marker = jpeg_header[2:4]

            # Step 2: handle presence of APP0 - it's optional
            if app_marker == b'\xff\xe0':
                self.has_app0 = True
                # There is an APP0 before the probable APP1
                # Don't neeed the content of the APP0
                app0_data_length = jpeg_header[4] * 256 + jpeg_header[5]
                # We've already read twelve bytes total, going into the APP1 data.
                # Now we want to download the rest of the APP1, along with the app0 marker
                # and the app0 exif header
                read1_size = app0_data_length + 2
                app0 = jpeg.read(read1_size)
                app_marker = app0[(exif_header_length + 2) * -1:exif_header_length * -1]
                exif_header = app0[exif_header_length * -1:]
                jpeg_header = jpeg_header + app0

            else:
                exif_header = jpeg_header[exif_header_length * -1:]

            # Step 3: process exif header
            if app_marker != b'\xff\xe1':
                print("Could not locate APP1 marker in %s" % self.file_name)
                return None
            if exif_header[2:6] != b'Exif' or exif_header[6:8] != b'\x00\x00':
                print("APP1 is malformed in %s" % self.file_name)
                return None
            app1_data_length = exif_header[0] * 256 + exif_header[1]

            # Step 4: read APP1
            view = jpeg.read(app1_data_length)
            photo_extract = jpeg_header + view

        metadata = GExiv2.Metadata()
        length = app1_data_length + app0_data_length

        try:
            metadata.open_buf(photo_extract)
            # print("read exif okay :-)")
        except:
            print("Failed to read exif!")
        else:
            try:
                if not check_extract(metadata, length):
                    pass
                    # print("Read exif okay, but failed to get value from exif!")
            except KeyError:
                pass
                # print("Read exif okay, but failed to get value from exif!")


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
                format_size_for_user(self.minimum_exif_read_size_in_bytes_orientation))
        if self.minimum_exif_read_size_in_bytes_orientation is None and self.orientation is not \
                None:
            s += 'Could not extract orientation tag with minimal read\n'
        if self.minimum_exif_read_size_in_bytes_datetime is not None:
            s += 'Minimum read size to extract datetime tag: {}\n'.format(
                format_size_for_user(self.minimum_exif_read_size_in_bytes_datetime))
        if self.minimum_exif_read_size_in_bytes_datetime is None and self.datetime is not None:
            s += 'Could not extract datetime tag with minimal read\n'
        if self.minimum_exif_read_size_in_bytes_all is not None:
            s += 'Minimum read size to extract variety of tags: {}\n'.format(
                format_size_for_user(self.minimum_exif_read_size_in_bytes_all))
        else:
            s += 'Could not extract variety of tags with minimal read\n'
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