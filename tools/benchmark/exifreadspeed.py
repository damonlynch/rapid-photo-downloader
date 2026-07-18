#  SPDX-FileCopyrightText: 2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: GPL-3.0-or-later
"""
Benchmark how long it takes Exiv2 and ExifTool to open the same collection of HEIF
files.

Expected use case: a large number of HEIF files on a memory card.

Instructions: Mount the memory card, don't access any of the files, run the program,
and then when prompted, eject the card, and remount it.

If the program crashes because of too many open files, increase the open files limit,
e.g. for 65535 files:

ulimit -Sn 65535
"""

import contextlib
import os
import sys
import time
from pathlib import Path

import gi

try:
    gi.require_version("GExiv2", "0.16")
except ValueError:
    gi.require_version("GExiv2", "0.10")
from gi.repository import GExiv2  # noqa: E402

from raphodo.metadata.exiftool import ExifTool
from raphodo.metadata.fileformats import HEIF_EXTENSIONS
from raphodo.metadata.metadataexiftool import MetadataExiftool
from raphodo.tools.utilities import find_files_by_extensions, stdchannel_redirected


def show_execution_time(num_files: int, start_time: float, end_time: float):
    execution_time = end_time - start_time
    print(f"Execution time: {execution_time:.6f} seconds")
    if num_files > 1:
        print(f"Execution time per file: {execution_time / num_files:.6f} seconds")


def exiv2_vs_exiftool_hief(path: Path, et_process: ExifTool) -> None:
    """
    Time how long it takes Exiv2 and ExifTool to open the same collection of HEIF files.
    """

    files = find_files_by_extensions(base_path=path, extensions=HEIF_EXTENSIONS)
    print(f"Working with {len(files)} HEIF files")

    metadata = GExiv2.Metadata()

    print("Exiv2")
    start_time = time.perf_counter()
    tag = "Exif.Photo.DateTimeOriginal"
    for f in files:
        with stdchannel_redirected(sys.stderr, os.devnull):
            metadata.open_path(f)
            dt_string = metadata.get_tag_string(tag)
    end_time = time.perf_counter()

    show_execution_time(len(files), start_time, end_time)
    input(
        "\nEject and reinsert the source volume (if necessary), then press Enter "
        "to continue...\n"
    )

    print("ExifTool")
    start_time = time.perf_counter()
    metadata = MetadataExiftool(full_file_name=None, et_process=et_process)
    tag = "DateTimeOriginal"
    for f in files:
        with stdchannel_redirected(sys.stderr, os.devnull):
            metadata.open_path_with_exiftool(f)
            dt_string = metadata._get(tag, "")
            metadata.clear()
    end_time = time.perf_counter()
    show_execution_time(len(files), start_time, end_time)


if __name__ == "__main__":
    valid_directory = False
    if len(sys.argv) > 1:
        with contextlib.suppress(Exception):
            path = Path(sys.argv[1]).resolve()
            valid_directory = path.is_dir()

    if not valid_directory:
        print("Usage: exifreadspeed.py <directory>")
        sys.exit(1)

    with ExifTool() as et_process:
        exiv2_vs_exiftool_hief(path, et_process)
