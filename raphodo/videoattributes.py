# Copyright (C) 2016 Damon Lynch <damonlynch@gmail.com>

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
Collects attributes about varieties of video formats, including how much of the file
has to be read in order to extract metadata information or generate a thumbnail.
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2016, Damon Lynch"


from tempfile import NamedTemporaryFile, TemporaryDirectory
import os
import datetime
from typing import Dict, Union
import raphodo.exiftool as exiftool
from raphodo.metadatavideo import MetaData
from raphodo.utilities import format_size_for_user, datetime_roughly_equal
from raphodo.thumbnailextractor import get_video_frame
from raphodo.constants import FileType
from raphodo.photoattributes import ExifToolMixin, vmtouch_output


class VideoAttributes(ExifToolMixin):
    def __init__(self, full_file_name: str, ext: str, et_process: exiftool.ExifTool) -> None:
        all_metadata_tags = 'date_time timestamp file_number width height length ' \
                            'frames_per_second codec fourcc rotation'
        super().__init__(
            FileType.video, full_file_name, et_process, video_metadata_scan_range,
            all_metadata_tags, MetaData
        )
        self.datetime = None # type: datetime.datetime
        self.file_name = full_file_name
        self.ext = ext
        self.et_process = et_process
        self.minimum_read_size_in_bytes_datetime = None  # type: int
        self.minimum_read_size_in_bytes_thumbnail = None  # type: int
        self.minimum_metadata_read_size_in_bytes_all = None  # type: int
        self.thumbnail_offset = 0.0

        self.assign_video_attributes(et_process)

        # Before doing further processing, understand what has already
        # been cached after simply reading the datetime metadata
        self.bytes_cached, self.total, self.in_memory = vmtouch_output(full_file_name)

        self.thumbnail = get_video_frame(full_file_name, self.thumbnail_offset)

        if self.datetime is not None:
            self.minimum_extract_for_tag(self.datetime_extract)

        if self.thumbnail:
            self.minimum_extract_for_thumbnail()

        self.minimum_extract_for_all()


    def assign_video_attributes(self, et_process: exiftool.ExifTool) -> None:
        m = MetaData(self.file_name, et_process)
        self.datetime = m.date_time(missing=None)

    def datetime_extract(self, metadata: MetaData, size_in_bytes):
        if metadata.date_time() == self.datetime:
            self.minimum_read_size_in_bytes_datetime = min(size_in_bytes, self.file_size)
            return True
        return False

    def minimum_extract_for_thumbnail(self):
        name = os.path.split(self.file_name)[1]
        with TemporaryDirectory(dir='/tmp') as tmpdirname:
            with open(self.file_name, 'rb') as video:
                tempname = os.path.join(tmpdirname, name)
                for size_in_bytes in thumbnail_scan_range(self.file_size):
                    video.seek(0)
                    video_extract = video.read(size_in_bytes)
                    with open(tempname, 'wb') as f:
                        f.write(video_extract)
                    try:
                        if get_video_frame(tempname, self.thumbnail_offset) == self.thumbnail:
                            self.minimum_read_size_in_bytes_thumbnail = min(
                                size_in_bytes, self.file_size
                            )
                            break
                    except AssertionError:
                        pass


    def minimum_extract_for_tag(self, check_extract):
        with open(self.file_name, 'rb') as video:
            for size_in_bytes in video_metadata_scan_range(self.file_size):
                video.seek(0)
                video_extract = video.read(size_in_bytes)
                with NamedTemporaryFile('w+b', delete=False) as f:
                    f.write(video_extract)
                    name = f.name
                metadata = MetaData(name, self.et_process)
                if check_extract(metadata, size_in_bytes):
                    os.remove(name)
                    break
                os.remove(name)

    def minimum_extract_for_all_tags(self):
        funcs = 'date_time timestamp file_number width height length frames_per_second codec ' \
                'fourcc rotation'.split()

        metadata = MetaData(self.file_name, self.et_process)
        for f in funcs:
            v = getattr(metadata, f)()
            if v:
                self.all_metadata_values[f] = v

        found = set()

        with open(self.file_name, 'rb') as video:
            for size_in_bytes in video_metadata_scan_range(self.file_size):
                video.seek(0)
                video_extract = video.read(size_in_bytes)
                with NamedTemporaryFile('w+b', delete=False) as f:
                    f.write(video_extract)
                    name = f.name
                metadata_extract = MetaData(name, self.et_process)
                for tag in self.all_metadata_values:
                    if (tag not in found and
                                getattr(metadata_extract, tag)() == self.all_metadata_values[tag]):
                        found.add(tag)
                        if len(found) == len(self.all_metadata_values):
                            self.minimum_metadata_read_size_in_bytes_all = size_in_bytes
                            os.remove(name)
                            return
                os.remove(name)

    def __repr__(self):
        if self.file_name:
            s = os.path.split(self.file_name)[1]
        else:
            s = self.ext
        if self.datetime:
            s += ' {}'.format(self.datetime)
        if self.minimum_read_size_in_bytes_datetime:
            s += ' {} (datetime)'.format(self.minimum_read_size_in_bytes_datetime)
        if self.minimum_read_size_in_bytes_thumbnail:
            s += ' {} (thumb)'.format(self.minimum_read_size_in_bytes_thumbnail)
        if self.minimum_metadata_read_size_in_bytes_all:
            s += ' {} (variety)'.format(self.minimum_metadata_read_size_in_bytes_all)
        return s


    def __str__(self):
        if self.file_name is not None:
            s = '{}\n'.format(os.path.split(self.file_name)[1])
        else:
            s = self.ext
        if self.datetime: # type: datetime.datetime
            s += 'Datetime in metadata: {}\n'.format(self.datetime.strftime('%c'))
            if not datetime_roughly_equal(self.datetime, self.fs_datetime):
                s += 'Differs from datetime on file system: {}\n'.format(
                    self.fs_datetime.strftime('%c'))
        else:
            s += 'Datetime on file system: {}\n'.format(self.fs_datetime.strftime('%c'))

        s += 'Disk cache after metadata read:\n[{}]\n'.format(self.in_memory)
        if self.minimum_read_size_in_bytes_datetime is not None:
            s += 'Minimum read size to extract datetime: {} of {}\n'.format(
                format_size_for_user(self.minimum_read_size_in_bytes_datetime),
                format_size_for_user(self.file_size))
        if self.minimum_read_size_in_bytes_thumbnail:
            s += 'Minimum read size to extract thumbnail: {} of {}\n'.format(
                format_size_for_user(self.minimum_read_size_in_bytes_thumbnail),
                format_size_for_user(self.file_size))
        if self.minimum_metadata_read_size_in_bytes_all is not None:
            s += 'Minimum read size to extract variety of tags: {}\n'.format(
                format_size_for_user(self.minimum_metadata_read_size_in_bytes_all))
        else:
            s += 'Could not extract variety of tags with minimal read\n'
        return s


def video_metadata_scan_range(size: int) -> iter:
    stop = 20
    for iterations, step in ((108, 1), (97, 4), (16, 32), (16, 256), (16, 512), (8, 1024),
                             (8, 2048 * 4), (32, 2048 * 16), (128, 2048 * 32)):
        start = stop
        stop = start + step * iterations
        for b in range(start, stop, step):
            yield b
    yield size

def thumbnail_scan_range(size: int) -> iter:
    stop = 100 * 1024
    for iterations, step in ((10, 100 * 1024), (64, 1024 * 1024),):
        start = stop
        stop = start + step * iterations
        for b in range(start, stop, step):
            yield b
    yield size

