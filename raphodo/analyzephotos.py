#!/usr/bin/env python3

# Copyright (C) 2015-2018 Damon Lynch <damonlynch@gmail.com>

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
Analyze the location of exif data in a variety of RAW and jpeg files.

Two goals:
 1) Analyze what part of a file is loaded from disk when exif metadata
    is read:
        1a) When reading only the exif.
        2a) When extracting a preview.
    Need to know how much to read, and where to read it from. The disk
    cache is a proxy to that.
 2) Determine the minimum amount of the file that can be read to get
    the exif orientation and the exif date time.
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2015-2018, Damon Lynch"

import sys
import os

if sys.version_info < (3,5):
    import scandir
    walk = scandir.walk
else:
    walk = os.walk
import textwrap
import subprocess
import argparse
import shutil
import pickle
import shlex
from collections import defaultdict, Counter
import time
import threading
import datetime
from typing import List, Tuple

import gi
gi.require_version('GExiv2', '0.10')
from gi.repository import GExiv2

from raphodo.photoattributes import (
    PhotoAttributes, vmtouch_output, PreviewSource, ExifToolPhotoAttributes
)
from raphodo.utilities import stdchannel_redirected, show_errors, confirm
from raphodo.rpdsql import FileFormatSQL
from raphodo.exiftool import ExifTool
from raphodo.videoattributes import VideoAttributes
from raphodo.utilities import format_size_for_user
import raphodo.metadataphoto as mp
from raphodo.fileformats import (
    RAW_EXTENSIONS, JPEG_TYPE_EXTENSIONS, VIDEO_EXTENSIONS,
    extract_extension, use_exiftool_on_photo
)

try:
    import pyprind
    have_progressbar = True
except ImportError:
    have_progressbar = False


JPEG_EXTENSIONS = JPEG_TYPE_EXTENSIONS

PHOTO_EXTENSIONS = RAW_EXTENSIONS + JPEG_EXTENSIONS



class progress_bar_scanning(threading.Thread):
    # Adapted from http://thelivingpearl.com/2012/12/31/
    # creating-progress-bars-with-python/
    def run(self):
            print('Scanning....  ', end='', flush=True)
            i = 0
            while stop != True:
                    if (i%4) == 0:
                        sys.stdout.write('\b/')
                    elif (i%4) == 1:
                        sys.stdout.write('\b-')
                    elif (i%4) == 2:
                        sys.stdout.write('\b\\')
                    elif (i%4) == 3:
                        sys.stdout.write('\b|')

                    sys.stdout.flush()
                    time.sleep(0.2)
                    i+=1

            if kill == True:
                print('\b\b\b\b ABORT!', flush=True)
            else:
                print('\b\b done!', flush=True)


def scan(folder: str,
         disk_cach_cleared: bool,
         scan_types: List[str],
         errors: bool,
         outfile: str,
         keep_file_names: bool,
         analyze_previews: bool) -> Tuple[
            List[PhotoAttributes], List[VideoAttributes]]:

    global stop
    global kill

    problematic_files = (
        'RAW_LEICA_M8.DNG'
    )

    stop = kill = False

    pbs = progress_bar_scanning()
    pbs.start()

    test_files = []
    not_tested = []
    # Phase 1
    # Determine which files are safe to test i.e. are not cached

    if analyze_previews:
        disk_cach_cleared = True

    for dir_name, subdirs, filenames in walk(folder):
        for filename in filenames:
            if filename not in problematic_files:
                ext = extract_extension(filename)
                if ext in scan_types:
                    full_file_name = os.path.join(dir_name, filename)

                    if disk_cach_cleared:
                        test_files.append((full_file_name, ext.upper()))
                    else:
                        bytes_cached, total, in_memory = vmtouch_output(full_file_name)
                        if bytes_cached == 0:
                            test_files.append((full_file_name, ext.upper()))
                        else:
                            not_tested.append(full_file_name)

    stop = True
    pbs.join()

    if not_tested:
        print()
        if len(not_tested) > 20:
            for line in textwrap.wrap(
                    "WARNING: {:,} files will not be analyzed because they are already in the "
                    "kernel disk cache.".format(len(not_tested)), width=80
            ):
                print(line)
        else:
            print(
                "WARNING: these files will not be analyzed because they are already in the "
                "kernel disk cache:"
            )
            for name in not_tested:
                print(name)
        print()
        for line in textwrap.wrap(
                "Run this script as super user and use command line option -c or --clear to safely "
                "clear the disk cache.", width=80
        ):
            print(line)

        if confirm(prompt='\nDo you want to exit?', resp=True):
            sys.exit(0)

    photos = []
    videos = []

    if test_files:
        print("\nAnalyzing {:,} files:".format(len(test_files)))
        if have_progressbar and not errors:
            bar = pyprind.ProgBar(iterations=len(test_files), stream=1, track_time=False, width=80)
    else:
        print("\nNothing to analyze")

    # Phase 2
    # Get info from files

    if errors:
        context = show_errors()
    else:
        # Redirect stderr, hiding error output from exiv2
        context = stdchannel_redirected(sys.stderr, os.devnull)

    metadata_fail = []

    with context:
        with ExifTool() as exiftool_process:
            for full_file_name, ext in test_files:
                if ext.lower() in VIDEO_EXTENSIONS:
                    va = VideoAttributes(full_file_name, ext, exiftool_process)
                    videos.append(va)
                else:
                    #TODO think about how to handle HEIF files!
                    if use_exiftool_on_photo(ext.lower(), preview_extraction_irrelevant=False):
                        pa = ExifToolPhotoAttributes(
                            full_file_name, ext, exiftool_process, analyze_previews
                        )
                        pa.process(analyze_previews)
                        photos.append(pa)
                    else:
                        try:
                            metadata = mp.MetaData(
                                full_file_name=full_file_name, et_process=exiftool_process
                            )
                        except:
                            metadata_fail.append(full_file_name)
                        else:
                            pa = PhotoAttributes(
                                full_file_name, ext, exiftool_process, analyze_previews
                            )
                            pa.metadata = metadata
                            pa.process(analyze_previews)
                            photos.append(pa)

                if have_progressbar and not errors:
                    bar.update()

    if metadata_fail:
        print()
        for full_file_name in metadata_fail:
            print("Could not read metadata from {}".format(full_file_name))

    if outfile is not None:
        if not keep_file_names:
            for pa in photos:
                pa.file_name = None
            for va in videos:
                va.file_name = None

        with open(outfile, 'wb') as save_to:
            pickle.dump((photos, videos), save_to, pickle.HIGHEST_PROTOCOL)

    return photos, videos


def analyze_photos(photos: List[PhotoAttributes],
                   verbose: bool,
                   analyze_previews: bool) -> None:

    if analyze_previews:
        previews_by_extension = defaultdict(list)
        for pa in photos:  # type: PhotoAttributes
            previews_by_extension[pa.ext].append((pa.preview_size_and_types, pa.has_exif_thumbnail))
        exts = list(previews_by_extension.keys())
        exts.sort()
        print("\nImage previews:")
        for ext in exts:
            print(ext, Counter(previews_by_extension[ext]).most_common())
            print()
        if verbose:
            print()
            for pa in photos:
                print(pa)
        return

    size_by_extension= defaultdict(list)
    orientation_read = defaultdict(list)
    datetime_read = defaultdict(list)
    variety_read = defaultdict(list)
    thumbnail_read = defaultdict(list)

    for pa in photos: # type: PhotoAttributes
        size_by_extension[pa.ext].append(pa.bytes_cached_post_thumb)
        if pa.minimum_exif_read_size_in_bytes_orientation is not None:
            orientation_read[pa.ext].append(pa.minimum_exif_read_size_in_bytes_orientation)
        if pa.minimum_exif_read_size_in_bytes_datetime is not None:
            datetime_read[pa.ext].append(pa.minimum_exif_read_size_in_bytes_datetime)
        if pa.minimum_metadata_read_size_in_bytes_all is not None:
            variety_read[pa.ext].append(pa.minimum_metadata_read_size_in_bytes_all)
        if pa.minimum_exif_read_size_in_bytes_thumbnail is not None:
            thumbnail_read[pa.ext].append(pa.minimum_exif_read_size_in_bytes_thumbnail)

    exts = list(size_by_extension.keys())
    exts.sort()
    print("\nKB cached after thumbnail extraction:")
    for ext in exts:
        print(ext, Counter(size_by_extension[ext]).most_common())


    exts = list(thumbnail_read.keys())
    exts.sort()
    print("\nThumbnail or preview read:")
    for ext in exts:
        print(ext, Counter(thumbnail_read[ext]).most_common())
        m = max(thumbnail_read[ext])
        max_bytes = round(int(m) * 1.2)
        print(ext, 'max ({}) + 20%: {} {}'.format(m, max_bytes, format_size_for_user(max_bytes)))

    exts = list(orientation_read.keys())
    exts.sort()
    print("\nOrientation tag read:")
    for ext in exts:
        print(ext, Counter(orientation_read[ext]).most_common())

    exts = list(datetime_read.keys())
    exts.sort()
    print("\nDate time tag read:")
    for ext in exts:
        print(ext, Counter(datetime_read[ext]).most_common())

    exts = list(variety_read.keys())
    exts.sort()
    print("\nVariety of tags read:")
    for ext in exts:
        print(ext, Counter(variety_read[ext]).most_common())
        m = max(variety_read[ext])
        print(ext, 'max + 20%:', round(int(m) * 1.2))

    print()
    if verbose:
        for pa in photos:
            print(pa)

    file_formats = FileFormatSQL()
    for pa in photos: # type: PhotoAttributes
        file_formats.add_format(pa)

def analyze_videos(videos: List[VideoAttributes], verbose: bool) -> None:
    size_by_extension= defaultdict(list)
    datetime_read = defaultdict(list)
    thumbnail_extract = defaultdict(list)
    variety_read = defaultdict(list)
    variety_read_raw = defaultdict(list)

    for va in videos:
        print ('%s' % va)
        size_by_extension[va.ext].append(va.bytes_cached)
        total = format_size_for_user(va.file_size)
        if va.minimum_read_size_in_bytes_datetime is not None:
            # size = format_size_for_user(va.minimum_read_size_in_bytes_datetime)
            # datetime_read[va.ext].append('{} of {}'.format(size, total))
            datetime_read[va.ext].append(va.minimum_read_size_in_bytes_datetime)
        if va.minimum_read_size_in_bytes_thumbnail is not None:
            # size =  format_size_for_user(va.minimum_read_size_in_bytes_thumbnail)
            # thumbnail_extract[va.ext].append('{} of {}'.format(size, total))
            thumbnail_extract[va.ext].append(va.minimum_read_size_in_bytes_thumbnail)
        if va.minimum_metadata_read_size_in_bytes_all is not None:
            # size =  format_size_for_user(va.minimum_metadata_read_size_in_bytes_all)
            # variety_read[va.ext].append('{} of {}'.format(size, total))
            variety_read_raw[va.ext].append(va.minimum_metadata_read_size_in_bytes_all)

    exts = list(size_by_extension.keys())
    exts.sort()
    print("\nKB cached after date time extraction:")
    for ext in exts:
        print(ext, Counter(size_by_extension[ext]).most_common())

    exts = list(thumbnail_extract.keys())
    exts.sort()
    print("\nThumbnail extract:")
    for ext in exts:
        print(ext, Counter(thumbnail_extract[ext]).most_common())

    exts = list(datetime_read.keys())
    exts.sort()
    print("\nDate time read:")
    for ext in exts:
        print(ext, Counter(datetime_read[ext]).most_common())

    exts = list(variety_read.keys())
    exts.sort()
    print("\nVariety of tags read:")
    for ext in exts:
        print(ext, Counter(variety_read[ext]).most_common())
        m = max(variety_read_raw[ext])
        print(ext, 'max + 20% (bytes):', round(int(m) * 1.2))

    print()
    if verbose:
        for va in videos:
            print(va)

def main():
    parser = argparse.ArgumentParser(
        description='Analyze the location of metadata in a variety of RAW, jpeg and video files.'
    )
    parser.add_argument(
        'source', action='store',
        help="Folder in which to recursively scan for photos and videos, or a previously saved "
             "outfile."
    )
    parser.add_argument('outfile',  nargs='?', help="Optional file in which to save the analysis")
    parser.add_argument(
        '--clear', '-c', action='store_true',
        help="To work, this program requires that the scanned photos and videos not be in the "
             "Linux kernel's disk cache. This command instructs the kernel to sync and then drop "
             "clean caches, as well as reclaimable slab objects like dentries and inodes. This is "
             "a non-destructive operation and will not free any dirty objects. See "
             "https://www.kernel.org/doc/Documentation/sysctl/vm.txt"
    )
    parser.add_argument(
        '--verbose', '-v', dest='verbose', action='store_true', help="Show more detailed output"
    )
    parser.add_argument(
        '--load', '-l', dest='load', action='store_true',
        help="Don't scan. Instead use previously generated outfile as input."
    )
    parser.add_argument(
        '--keep-names', '-k', dest='keep', action='store_true',
        help="If saving the analysis to file, don't first remove the file names and paths from the "
             "analysis. Don't specify this option if you want to keep this information private "
             "when sharing the analysis with others."
    )
    parser.add_argument(
        '--no-dng', '-d', dest='dng', action='store_true', help="Don't scan DNG files"
    )
    parser.add_argument('--video', action='store_true', help="Scan videos")
    parser.add_argument(
        '--only-video', dest='only_video', action='store_true', help='Scan only videos'
    )
    parser.add_argument(
        '--include-jpeg', '-j', dest='jpeg', action='store_true', help="Scan jpeg images"
    )
    parser.add_argument(
        '--only-jpeg', '-J', dest='onlyjpeg', action='store_true', help="Scan only jpeg images"
    )
    parser.add_argument(
        '--show-errors', '-e', dest='errors', action='store_true',
        help="Don't show progress bar while scanning, and instead show all errors output by exiv2 "
             "(useful if exiv2 crashes, which takes down this script too)"
    )
    parser.add_argument(
        '--analyze-previews', dest='analyze_previews', action='store_true',
        help="Analyze the previews sizes found in photos, do nothing else, and exit. "
             "Output is set to verbose."
    )

    args = parser.parse_args()

    # if args.analyze_previews:
    #     args.verbose = True

    if not have_progressbar:
        print(
            "To see an optional but helpful progress bar, install pyprind: "
            "https://github.com/rasbt/pyprind"
        )

    if not shutil.which('vmtouch') and not args.analyze_previews:
        print(
            'To run this program, you need to install vmtouch. Get it at '
            'http://hoytech.com/vmtouch/'
        )
        sys.exit(1)

    if args.analyze_previews and args.only_video:
        print("Cannot examine videos while also examining photo previews")
        sys.exit(1)

    if args.load:
        with open(args.source, 'rb') as infile:
            photos, videos = pickle.load(infile)
        analyze_photos(photos, args.verbose)
        analyze_videos(videos, args.verbose)
    else:
        if args.clear:
            subprocess.check_call('sync')
            sh_cmd = shutil.which('sh')
            command_line = 'sudo {} -c {}'.format(
                sh_cmd, shlex.quote("echo 3 > /proc/sys/vm/drop_caches")
            )
            cmd = shlex.split(command_line)
            try:
                print(
                    "Super user permission is needed to drop caches.\nYou may be required to enter "
                    "the super user's password."
                )
                subprocess.check_call(cmd)
            except subprocess.CalledProcessError:
                sys.stderr.write("Failed to drop caches: exiting\n")
                sys.exit(1)

        if args.only_video:
            scan_types = VIDEO_EXTENSIONS
        else:

            if args.dng:
                RAW_EXTENSIONS.remove('dng')
                PHOTO_EXTENSIONS.remove('dng')

            if args.jpeg:
                scan_types = PHOTO_EXTENSIONS
            elif args.onlyjpeg:
                scan_types = JPEG_EXTENSIONS
            else:
                scan_types = RAW_EXTENSIONS

            if args.video:
                scan_types.extend(VIDEO_EXTENSIONS)

        photos, videos = scan(
            args.source, args.clear, scan_types, args.errors, args.outfile, args.keep,
            args.analyze_previews
        )
        if photos:
            print("\nPhotos\n======")
            analyze_photos(photos, args.verbose, args.analyze_previews)
        if videos:
            print("\nVideos\n======")
            analyze_videos(videos, args.verbose)

if __name__ == "__main__":
    main()


