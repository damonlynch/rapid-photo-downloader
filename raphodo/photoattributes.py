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

"""
Collects attributes about varieties of photo formats, including how much of the file
has to be read in order to extract exif information or a preview.
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2015-2019, Damon Lynch"

import resource
import shlex
import subprocess
from enum import IntEnum
import os
import datetime
from typing import Optional, Dict, Union, Tuple
from tempfile import NamedTemporaryFile

import gi
gi.require_version('GExiv2', '0.10')
from gi.repository import GExiv2
from PyQt5.QtGui import QImage

from raphodo.utilities import format_size_for_user, stdchannel_redirected
from raphodo.metadataphoto import MetaData, photo_date_time
from raphodo.metadataexiftool import MetadataExiftool
from raphodo.fileformats import FileType


vmtouch_cmd = 'vmtouch -v "{}"'
page_size = resource.getpagesize()
to_kb = page_size // 1024

JPEG_EXTENSIONS = ['jpg', 'jpe', 'jpeg']

class PreviewSource(IntEnum):
    preview_1 = 0
    preview_2 = 1
    preview_3 = 2
    preview_4 = 3
    preview_5 = 4
    preview_6 = 5


all_metadata_tags = 'aperture iso exposure_time focal_length camera_make camera_model ' \
                    'camera_serial shutter_count owner_name copyright artist short_camera_model ' \
                    'date_time timestamp sub_seconds orientation'


class ExifToolMixin:
    def __init__(self, file_type: FileType,
                 full_file_name: str,
                 et_process,
                 scan_func,
                 all_metadata_tags: str,
                 metadata,) -> None:

        stat = os.stat(full_file_name)
        self.fs_datetime = datetime.datetime.fromtimestamp(stat.st_mtime)
        self.file_size = stat.st_size

        self.file_type = file_type
        self.file_name = full_file_name
        self.scan_func = scan_func
        self.et_process = et_process
        self.all_metadata_values = dict()  # type: Dict[str, Union[int, str, float, datetime.datetime]]
        self.all_metadata_tags = all_metadata_tags
        self._metadata = metadata

    def minimum_extract_for_tag(self, check_extract):
        with open(self.file_name, 'rb') as photo_video:
            for size_in_bytes in self.scan_func(self.file_size):
                photo_video.seek(0)
                photo_video_extract = photo_video.read(size_in_bytes)
                with NamedTemporaryFile('w+b', delete=False) as f:
                    f.write(photo_video_extract)
                    name = f.name
                metadata = self._metadata(name, self.et_process, self.file_type)
                if check_extract(metadata, size_in_bytes):
                    os.remove(name)
                    break
                os.remove(name)

    def minimum_extract_for_all(self):
        funcs = self.all_metadata_tags.split()

        metadata = self._metadata(self.file_name, self.et_process)
        for f in funcs:
            v = getattr(metadata, f)()
            if v:
                self.all_metadata_values[f] = v

        found = set()

        with open(self.file_name, 'rb') as photo_video:
            for size_in_bytes in self.scan_func(self.file_size):
                photo_video.seek(0)
                photo_video_extract = photo_video.read(size_in_bytes)
                with NamedTemporaryFile('w+b', delete=False) as f:
                    f.write(photo_video_extract)
                    name = f.name
                metadata_extract = self._metadata(name, self.et_process, self.file_type)
                try:
                    for tag in self.all_metadata_values:
                        if (tag not in found and
                                getattr(metadata_extract, tag)() == self.all_metadata_values[tag]):
                            found.add(tag)
                            if len(found) == len(self.all_metadata_values):
                                self.minimum_metadata_read_size_in_bytes_all = size_in_bytes
                                os.remove(name)
                                return
                except:
                    pass
                finally:
                    if os.path.exists(name):
                        os.remove(name)


class PhotoAttributes:
    def __init__(self, full_file_name: str, ext: str, et_process, analyze_previews: bool) -> None:
        self.et_process = et_process
        self.datetime = None # type: datetime.datetime
        self.iso = None # type: int
        self.height = None # type: int
        self.width = None # type: int
        self.model = None  # type: str
        self.has_gps = False  # type: bool
        self.orientation = None # type: str
        self.no_previews = None # type: int
        self.has_exif_thumbnail = False # type: bool
        self.exif_thumbnail_or_preview = None  # type: bytes
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
        self.minimum_exif_read_size_in_bytes_thumbnail = None   # type: int
        self.minimum_metadata_read_size_in_bytes_all = None  # type: int
        self.bytes_cached_post_previews = None
        self.in_memory_post_previews = None
        self.in_memory_post_thumb = None
        self.in_memory = None
        self.bytes_cached = None
        self.bytes_cached_post_thumb = None

        self.file_name = full_file_name
        self.ext = ext
        self.analyze_previews = analyze_previews

        if not analyze_previews:
            # Before doing anything else, understand what has already
            # been cached after simply reading the exif
            self.bytes_cached, self.total, self.in_memory = vmtouch_output(full_file_name)

        self.metadata = None

        stat = os.stat(full_file_name)
        self.fs_datetime = datetime.datetime.fromtimestamp(stat.st_mtime)
        self.file_size = stat.st_size

    def process(self, analyze_previews: bool):

        # Get information about the photo
        self.assign_photo_attributes(self.metadata)
        self.extract_thumbnail(self.metadata)
        if not analyze_previews:
            self.bytes_cached_post_thumb, total, self.in_memory_post_thumb = vmtouch_output(
                self.file_name
            )
        self.get_preview_sizes(self.metadata)

        if not analyze_previews:
            self.bytes_cached_post_previews, total, self.in_memory_post_previews = vmtouch_output(
                self.file_name
            )

        if not analyze_previews:
            if self.orientation is not None or self.ext.lower() in JPEG_EXTENSIONS:
                self.minimum_extract_for_tag(self.orientation_extract)

            if self.datetime is not None:
                self.minimum_extract_for_tag(self.datetime_extract)

            if self.exif_thumbnail_or_preview is not None:
                self.minimum_extract_for_tag(self.thumbnail_extract)

            self.minimum_extract_for_all()

    def assign_photo_attributes(self, metadata: GExiv2.Metadata) -> None:
        # I don't know how GExiv2 gets these values:
        self.width = metadata.get_pixel_width()
        self.height = metadata.get_pixel_height()
        try:
            self.orientation = metadata.get_tag_string('Exif.Image.Orientation')
        except KeyError:
            pass
        if metadata.has_tag('Exif.Image.Make') and metadata.has_tag('Exif.Image.Model'):
            self.model = '{} {}'.format(
                metadata.get_tag_string('Exif.Image.Make').strip(),
                metadata.get_tag_string('Exif.Image.Model').strip()
            )
        self.has_gps = metadata.get_gps_info()[0]
        self.iso = metadata.get_iso_speed()
        self.datetime = photo_date_time(metadata)

    def image_height_width(self, thumbnail: bytes) -> Optional[Tuple[int, int]]:
        qimage = QImage.fromData(thumbnail)
        if not qimage.isNull():
            return qimage.width(), qimage.height()

    def process_exif_thumbnail(self, thumbnail: bytes) -> None:
        if thumbnail:
            self.has_exif_thumbnail = True
            self.exif_thumbnail_or_preview = thumbnail
            width_height = self.image_height_width(thumbnail)
            if width_height is not None:
                self.exif_thumbnail_width = width_height[0]
                self.exif_thumbnail_height = width_height[1]
                self.exif_thumbnail_details = '{}x{}'.format(
                    self.exif_thumbnail_width, self.exif_thumbnail_height
                )

    def extract_thumbnail(self, metadata: GExiv2.Metadata) -> None:
        # not all files have an exif preview, but all CR2 & CR3 seem to
        exif_thumbnail = metadata.get_exif_thumbnail()
        self.process_exif_thumbnail(thumbnail=exif_thumbnail)

        previews = metadata.get_preview_properties()
        self.no_previews = len(previews)

        for idx, preview in enumerate(previews):
            image = metadata.get_preview_image(preview)
            if image.get_width() >= 160 and image.get_height() >= 120:
                preview_thumbnail = metadata.get_preview_image(preview).get_data()
                if self.has_exif_thumbnail:
                    self.exif_thumbnail_and_preview_identical = preview_thumbnail == exif_thumbnail
                else:
                    self.exif_thumbnail_or_preview = preview_thumbnail
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
            sizes_and_types.append(
                (image.get_width(), image.get_height(), image.get_extension())
            )
        self.preview_size_and_types = '; '.join(
            ['{}x{} {}'.format(width, height, ext[1:]) for width, height, ext in sizes_and_types]
        )

    def orientation_extract(self, metadata: GExiv2.Metadata, size_in_bytes) -> bool:
        if metadata['Exif.Image.Orientation'] == self.orientation:
            self.minimum_exif_read_size_in_bytes_orientation = size_in_bytes
            return True
        return False

    def datetime_extract(self, metadata: GExiv2.Metadata, size_in_bytes) -> bool:
        if photo_date_time(metadata) == self.datetime:
            self.minimum_exif_read_size_in_bytes_datetime = size_in_bytes
            return True
        return False

    def thumbnail_extract(self, metadata: GExiv2.Metadata, size_in_bytes) -> bool:
        thumbnail = metadata.get_exif_thumbnail()
        if not thumbnail:
            previews = metadata.get_preview_properties()
            if previews:
                # In every RAW file I've analyzed, the smallest preview is always first
                preview = previews[0]
                thumbnail = metadata.get_preview_image(preview).get_data()

        if thumbnail == self.exif_thumbnail_or_preview:
            self.minimum_exif_read_size_in_bytes_thumbnail = size_in_bytes
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
        with open(self.file_name, 'rb') as photo:
            for size_in_bytes in exif_scan_range(self.file_size):
                photo.seek(0)
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

    def minimum_extract_for_all(self) -> None:
        if self.ext == 'CRW':
            # Exiv2 can crash while scanning for exif in a very small
            # extract of a CRW file
            return

        funcs = all_metadata_tags.split()
        for f in funcs:
            v = getattr(self.metadata, f)()
            if v:
                self.all_exif_values[f] = v

        found = set()

        # with stdchannel_redirected(sys.stdout, os.devnull):
        for size_in_bytes in exif_scan_range(self.file_size):
            with open(self.file_name, 'rb') as photo:
                photo_extract = photo.read(size_in_bytes)
                try:
                    metadata_extract = MetaData(
                        raw_bytes=bytearray(photo_extract), et_process=self.et_process
                    )
                except:
                    pass
                else:
                    try:
                        for tag in self.all_exif_values:
                            if (tag not in found and
                                    getattr(metadata_extract, tag)() == self.all_exif_values[tag]):

                                found.add(tag)
                                if len(found) == len(self.all_exif_values):
                                    self.minimum_metadata_read_size_in_bytes_all = size_in_bytes
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

    def show_preview_source(self) -> str:
        return '{} of {}: {}x{} {}\n'.format(
            self.preview_source,
            self.no_previews,
            self.preview_width, self.preview_height,
            self.preview_extension[1:]
        )

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
            s += self.show_preview_source()
        if self.exif_thumbnail_and_preview_identical == False:
            # Check against False as value is one of None, True or
            # False
            s += 'Exif thumbnail differs from smallest preview\n'
        if self.preview_size_and_types:
            s += 'All preview images: {}\n'.format(self.preview_size_and_types)

        if self.in_memory is not None:
            s += 'Disk cache after exif read:\n[{}]\n'.format(self.in_memory)

        if self.in_memory is not None and self.in_memory_post_thumb is not None:
            if self.in_memory != self.in_memory_post_thumb:
                s += 'Disk cache after thumbnail / preview extraction:\n[{}]\n'.format(
                    self.in_memory_post_thumb
                )
        if self.bytes_cached is not None and self.bytes_cached_post_thumb is not None:
            if self.bytes_cached == self.bytes_cached_post_thumb:
                s += 'Cached: {:,}KB of {:,}KB\n'.format(self.bytes_cached, self.total)
            else:
                s += 'Cached: {:,}KB(+{:,}KB after extraction) of {:,}KB\n'.format(
                    self.bytes_cached, self.bytes_cached_post_thumb, self.total
                )

        if self.minimum_exif_read_size_in_bytes_thumbnail is not None:
            s += 'Minimum read size for thumbnail or first preview: {}\n'.format(
                format_size_for_user(self.minimum_exif_read_size_in_bytes_thumbnail)
            )
        if self.minimum_exif_read_size_in_bytes_orientation is not None:
            s += 'Minimum read size to extract orientation tag: {}\n'.format(
                format_size_for_user(self.minimum_exif_read_size_in_bytes_orientation)
            )
        if self.minimum_exif_read_size_in_bytes_orientation is None and self.orientation is not \
                None and not self.analyze_previews:
            s += 'Could not extract orientation tag with minimal read\n'
        if self.minimum_exif_read_size_in_bytes_datetime is not None:
            s += 'Minimum read size to extract datetime tag: {}\n'.format(
                format_size_for_user(self.minimum_exif_read_size_in_bytes_datetime)
            )
        if self.minimum_exif_read_size_in_bytes_datetime is None and self.datetime is not None \
                and not self.analyze_previews:
            s += 'Could not extract datetime tag with minimal read\n'
        if self.minimum_metadata_read_size_in_bytes_all is not None:
            s += 'Minimum read size to extract variety of tags: {}\n'.format(
                format_size_for_user(self.minimum_metadata_read_size_in_bytes_all)
            )
        elif self.in_memory is not None:
            s += 'Could not extract variety of tags with minimal read\n'
        return s


class ExifToolPhotoAttributes(ExifToolMixin, PhotoAttributes):
    def __init__(self, full_file_name: str, ext: str, et_process, analyze_previews: bool) -> None:
        super().__init__(
            FileType.video, full_file_name, et_process, exif_scan_range, all_metadata_tags,
            MetadataExiftool
        )
        ext = os.path.splitext(full_file_name)[1][1:].upper()
        PhotoAttributes.__init__(self, full_file_name, ext, et_process, analyze_previews)
        self.metadata = MetadataExiftool(full_file_name, et_process, FileType.photo)

        # create reverse lookup for preview names
        self.index_preview_inverse = {
            value: key for key, value in self.metadata.index_preview.items()
        }

    def assign_photo_attributes(self, metadata: MetadataExiftool) -> None:
        self.width = metadata.width()
        self.height = metadata.height()
        try:
            self.orientation = metadata.orientation()
        except Exception:
            pass

        self.model = '{} {}'.format(
            metadata.camera_make(),
            metadata.camera_model()
        )
        self.iso = metadata.iso()
        self.datetime = metadata.date_time(ignore_file_modify_date=True)

    def extract_thumbnail(self, metadata: MetadataExiftool) -> None:
        exif_thumbnail = metadata.get_small_thumbnail()
        self.process_exif_thumbnail(thumbnail=exif_thumbnail)

        for index in (0, 3, 4):  # PreviewImage, PreviewTIFF, ThumbnailTIFF
            preview_thumbnail = metadata.get_indexed_preview(index)
            if preview_thumbnail:
                if self.has_exif_thumbnail:
                    self.exif_thumbnail_and_preview_identical = preview_thumbnail == exif_thumbnail
                width_height = self.image_height_width(preview_thumbnail)
                if width_height is not None:
                    self.preview_source = metadata.index_preview[index]
                    self.preview_width = width_height[0]
                    self.preview_height = width_height[1]
                    self.preview_extension = 'jpg' if 'TIFF' not in self.preview_source else 'tiff'
                    return

    def get_preview_sizes(self, metadata: MetadataExiftool):
        preview_names = metadata.preview_names()
        self.no_previews = 0
        sizes_and_types = []
        for name in preview_names:
            preview = metadata.get_indexed_preview(self.index_preview_inverse[name])
            if preview:
                width_height = self.image_height_width(preview)
                if width_height is not None:
                    sizes_and_types.append(
                        (width_height[0], width_height[1], name)
                    )
                    self.no_previews += 1
        self.preview_size_and_types = '; '.join(
            ['{}x{} {}'.format(width, height, name) for width, height, name in sizes_and_types]
        )
        # self.preview_size_and_types = '; '.join(
        #     [name for width, height, name in sizes_and_types]
        # )


    def show_preview_source(self) -> str:
        return '{} of {}: {}x{}\n'.format(
            self.preview_source,
            self.no_previews,
            self.preview_width, self.preview_height,
        )

    def orientation_extract(self, metadata: MetadataExiftool, size_in_bytes):
        if metadata.orientation() == self.orientation:
            self.minimum_exif_read_size_in_bytes_orientation = size_in_bytes
            return True
        return False

    def datetime_extract(self, metadata: MetadataExiftool, size_in_bytes):
        if metadata.date_time(ignore_file_modify_date=True) == self.datetime:
            self.minimum_exif_read_size_in_bytes_datetime = size_in_bytes
            return True
        return False

    def thumbnail_extract(self, metadata: MetadataExiftool, size_in_bytes):
        thumbnail = metadata.get_small_thumbnail_or_first_indexed_preview()
        if thumbnail == self.exif_thumbnail_or_preview:
            self.minimum_exif_read_size_in_bytes_thumbnail = size_in_bytes
            return True
        return False


def exif_scan_range(size) -> iter:
    stop = 20
    for iterations, step in ((108, 1), (97, 4), (16, 32), (16, 256), (16, 512), (8, 1024),
                             (8, 2048 * 4), (32, 2048 * 16)):
        start = stop
        stop = start + step * iterations
        for b in range(start, stop, step):
            yield b
    yield size


def vmtouch_output(full_file_name: str) -> tuple:
    command = shlex.split(vmtouch_cmd.format(full_file_name))
    output = subprocess.check_output(command, universal_newlines=True) # type: str
    for line in output.split('\n'):
        line = line.strip()
        if line.startswith('['):
            in_memory = line[1:line.find(']')]
            currently_paged_percent = line.rsplit(' ', 1)[-1]
            num, denom = map(int, currently_paged_percent.split('/'))
            return num * to_kb, denom * to_kb, in_memory