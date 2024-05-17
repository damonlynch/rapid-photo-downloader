# SPDX-FileCopyrightText: Copyright 2015-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from collections import defaultdict
from dataclasses import dataclass
from typing import NamedTuple

from raphodo.constants import DisplayFileType, FileType, FileTypeFlag
from raphodo.rpdfile import FileTypeCounter, RPDFile


class DownloadStats:
    def __init__(self):
        self.no_photos = 0
        self.no_videos = 0
        self.photos_size_in_bytes = 0
        self.videos_size_in_bytes = 0
        self.post_download_thumb_generation = 0


class DownloadFiles(NamedTuple):
    files: defaultdict[int, list[RPDFile]]
    download_types: FileTypeFlag
    download_stats: defaultdict[int, DownloadStats]
    camera_access_needed: defaultdict[int, bool]


class MarkedSummary(NamedTuple):
    marked: FileTypeCounter
    size_photos_marked: int
    size_videos_marked: int


@dataclass
class DownloadFilesSizeAndNum:
    marked: FileTypeCounter
    size_photos_marked: int
    size_videos_marked: int

    def sum_size_marked(self) -> int:
        return self.size_photos_marked + self.size_videos_marked

    def sum_num_marked(self) -> int:
        return self.marked.total()

    def size_marked(self, display_type: DisplayFileType) -> int:
        match display_type:
            case DisplayFileType.photos_and_videos:
                return self.sum_size_marked()
            case DisplayFileType.photos:
                return self.size_photos_marked
            case DisplayFileType.videos:
                return self.size_videos_marked
            case _:
                raise NotImplementedError(f"Unexpected type {display_type}")


def file_types_tuple(file_type: FileType | None = None) -> tuple[FileType, ...]:
    return tuple(FileType) if file_type is None else (file_type,)


def display_types_tuple(same_destination: bool) -> tuple[DisplayFileType, ...]:
    return (
        (DisplayFileType.photos_and_videos,)
        if same_destination
        else (DisplayFileType.photos, DisplayFileType.videos)
    )
