# SPDX-FileCopyrightText: Copyright 2016-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Collects attributes about varieties of video formats, including how much of the file
has to be read in order to extract metadata information or generate a thumbnail.
"""

import datetime  # noqa: F401
import os
from tempfile import NamedTemporaryFile, TemporaryDirectory

import raphodo.metadata.exiftool as exiftool
from raphodo.constants import FileType
from raphodo.metadata.analysis.photoattributes import ExifToolMixin, vmtouch_output
from raphodo.metadata.metadatavideo import MetaData
from raphodo.thumbnailextractor import get_video_frame
from raphodo.tools.utilities import datetime_roughly_equal
from raphodo.tools.utilities import format_size_for_user as format_size


class VideoAttributes(ExifToolMixin):
    def __init__(
        self, full_file_name: str, ext: str, et_process: exiftool.ExifTool
    ) -> None:
        all_metadata_tags = (
            "date_time timestamp file_number width height length "
            "frames_per_second codec fourcc rotation"
        )
        super().__init__(
            FileType.video,
            full_file_name,
            et_process,
            video_metadata_scan_range,
            all_metadata_tags,
            MetaData,
        )
        self.datetime = None  # type: datetime.datetime | None
        self.file_name = full_file_name
        self.ext = ext
        self.et_process = et_process
        self.minimum_read_size_in_bytes_datetime = None  # type: int | None
        self.minimum_read_size_in_bytes_thumbnail = None  # type: int | None
        self.minimum_metadata_read_size_in_bytes_all = None  # type: int | None
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
            self.minimum_read_size_in_bytes_datetime = min(
                size_in_bytes, self.file_size
            )
            return True
        return False

    def minimum_extract_for_thumbnail(self):
        name = os.path.split(self.file_name)[1]
        with TemporaryDirectory(dir="/tmp") as tmpdirname:  # noqa: SIM117
            with open(self.file_name, "rb") as video:
                tempname = os.path.join(tmpdirname, name)
                for size_in_bytes in thumbnail_scan_range(self.file_size):
                    video.seek(0)
                    video_extract = video.read(size_in_bytes)
                    with open(tempname, "wb") as f:
                        f.write(video_extract)
                    try:
                        if (
                            get_video_frame(tempname, self.thumbnail_offset)
                            == self.thumbnail
                        ):
                            self.minimum_read_size_in_bytes_thumbnail = min(
                                size_in_bytes, self.file_size
                            )
                            break
                    except AssertionError:
                        pass

    def minimum_extract_for_tag(self, check_extract):
        with open(self.file_name, "rb") as video:
            for size_in_bytes in video_metadata_scan_range(self.file_size):
                video.seek(0)
                video_extract = video.read(size_in_bytes)
                with NamedTemporaryFile("w+b", delete=False) as f:
                    f.write(video_extract)
                    name = f.name
                metadata = MetaData(name, self.et_process)
                if check_extract(metadata, size_in_bytes):
                    os.remove(name)
                    break
                os.remove(name)

    def minimum_extract_for_all_tags(self):
        funcs = (
            "date_time timestamp file_number width height length frames_per_second "
            "codec fourcc rotation".split()
        )

        metadata = MetaData(self.file_name, self.et_process)
        for f in funcs:
            v = getattr(metadata, f)()
            if v:
                self.all_metadata_values[f] = v

        found = set()

        with open(self.file_name, "rb") as video:
            for size_in_bytes in video_metadata_scan_range(self.file_size):
                video.seek(0)
                video_extract = video.read(size_in_bytes)
                with NamedTemporaryFile("w+b", delete=False) as f:
                    f.write(video_extract)
                    name = f.name
                metadata_extract = MetaData(name, self.et_process)
                for tag in self.all_metadata_values:
                    if (
                        tag not in found
                        and getattr(metadata_extract, tag)()
                        == self.all_metadata_values[tag]
                    ):
                        found.add(tag)
                        if len(found) == len(self.all_metadata_values):
                            self.minimum_metadata_read_size_in_bytes_all = size_in_bytes
                            os.remove(name)
                            return
                os.remove(name)

    def __repr__(self):
        s = os.path.split(self.file_name)[1] if self.file_name else self.ext
        if self.datetime:
            s += f" {self.datetime}"
        if self.minimum_read_size_in_bytes_datetime:
            s += f" {self.minimum_read_size_in_bytes_datetime} (datetime)"
        if self.minimum_read_size_in_bytes_thumbnail:
            s += f" {self.minimum_read_size_in_bytes_thumbnail} (thumb)"
        if self.minimum_metadata_read_size_in_bytes_all:
            s += f" {self.minimum_metadata_read_size_in_bytes_all} (variety)"
        return s

    def __str__(self):
        if self.file_name is not None:
            s = f"{os.path.split(self.file_name)[1]}\n"
        else:
            s = self.ext
        if self.datetime:  # type: datetime.datetime
            s += "Datetime in metadata: {}\n".format(self.datetime.strftime("%c"))
            if not datetime_roughly_equal(self.datetime, self.fs_datetime):
                s += "Differs from datetime on file system: {}\n".format(
                    self.fs_datetime.strftime("%c")
                )
        else:
            s += "Datetime on file system: {}\n".format(self.fs_datetime.strftime("%c"))

        s += f"Disk cache after metadata read:\n[{self.in_memory}]\n"
        if self.minimum_read_size_in_bytes_datetime is not None:
            s += (
                "Minimum read size to extract datetime: "
                f"{format_size(self.minimum_read_size_in_bytes_datetime)} of "
                f"{format_size(self.file_size)}\n"
            )
        if self.minimum_read_size_in_bytes_thumbnail:
            s += (
                "Minimum read size to extract thumbnail: "
                f"{format_size(self.minimum_read_size_in_bytes_thumbnail)} of "
                f"{format_size(self.file_size)}\n"
            )
        if self.minimum_metadata_read_size_in_bytes_all is not None:
            s += (
                f"Minimum read size to extract variety of tags: "
                f"{format_size(self.minimum_metadata_read_size_in_bytes_all)}\n"
            )
        else:
            s += "Could not extract variety of tags with minimal read\n"
        return s


def video_metadata_scan_range(size: int) -> iter:
    stop = 20
    for iterations, step in (
        (108, 1),
        (97, 4),
        (16, 32),
        (16, 256),
        (16, 512),
        (8, 1024),
        (8, 2048 * 4),
        (32, 2048 * 16),
        (128, 2048 * 32),
    ):
        start = stop
        stop = start + step * iterations
        yield from range(start, stop, step)
    yield size


def thumbnail_scan_range(size: int) -> iter:
    stop = 100 * 1024
    for iterations, step in (
        (10, 100 * 1024),
        (64, 1024 * 1024),
    ):
        start = stop
        stop = start + step * iterations
        yield from range(start, stop, step)
    yield size
