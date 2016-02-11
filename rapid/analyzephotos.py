#!/usr/bin/env python3
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

import scandir
import os
import textwrap
import subprocess
import argparse
import shutil
import pickle
from collections import defaultdict, Counter
import sys
import time
import threading
import datetime
from typing import List

import gi
gi.require_version('GExiv2', '0.10')
from gi.repository import GExiv2

from photoattributes import PhotoAttributes, vmtouch_output, PreviewSource
from utilities import stdchannel_redirected, show_errors, confirm
from rpdsql import FileFormatSQL

try:
    import pyprind
    have_progresbar = True
except ImportError:
    print("To see a progress bar install pyprind: https://github.com/rasbt/pyprind")
    have_progresbar = False

if not shutil.which('vmtouch'):
    print('You need to install vmtouch. Get it at http://hoytech.com/vmtouch/')
    sys.exit(1)

RAW_EXTENSIONS = ['arw', 'dcr', 'cr2', 'crw',  'dng', 'mos', 'mef', 'mrw',
                  'nef', 'nrw', 'orf', 'pef', 'raf', 'raw', 'rw2', 'sr2',
                  'srw']

JPEG_EXTENSIONS = ['jpg', 'jpe', 'jpeg', 'mpo']

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


def scan(folder: str, disk_cach_cleared: bool, scan_types: List[str], errors: bool,
                outfile: str, keep_file_names: bool) -> List[PhotoAttributes]:

    global stop
    global kill

    stop = kill = False

    pbs = progress_bar_scanning()
    pbs.start()

    test_files = []
    not_tested = []
    # Phase 1
    # Determine which files are safe to test i.e. are not cached

    for dir_name, subdirs, filenames in scandir.walk(folder):
        for filename in filenames:
            ext = os.path.splitext(filename)[1][1:].lower()
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
            for line in textwrap.wrap("WARNING: {:,} files will not be analyzed because they are "
                                      "already in the kernel disk cache.".format(len(not_tested)),
                                      width=80):
                print(line)
        else:
            print("WARNING: these files will not be analyzed because they are already in the "
                  "kernel disk cache:")
            for name in not_tested:
                print(name)
        print()
        for line in textwrap.wrap("Run this script as super user and use command line option -c "
                                  "or "
                            "--clear to safely clear the disk cache.", width=80):
            print(line)

        if confirm(prompt='\nDo you want to exit?', resp=True):
            sys.exit(0)

    photos = []

    if test_files:
        print("\nAnalyzing {:,} files:".format(len(test_files)))
        if have_progresbar and not errors:
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
        for full_file_name, ext in test_files:
            try:
                metadata = GExiv2.Metadata(full_file_name)
            except:
                metadata_fail.append(full_file_name)
            else:
                pa = PhotoAttributes(full_file_name, ext, metadata)
                photos.append(pa)

            if have_progresbar and not errors:
                bar.update()

    if metadata_fail:
        print()
        for full_file_name in metadata_fail:
            print("Could not read metadata from {}".format(full_file_name))

    if outfile is not None:
        if not keep_file_names:
            for pa in photos:
                pa.file_name = None

        with open(outfile, 'wb') as save_to:
            pickle.dump(photos, save_to, pickle.HIGHEST_PROTOCOL)

    return photos

def analyze(photos: list, verbose: bool) -> None:
    size_by_extension= defaultdict(list)
    orientation_read = defaultdict(list)
    datetime_read = defaultdict(list)
    for pa in photos: # type: PhotoAttributes
        size_by_extension[pa.ext].append(pa.bytes_cached_post_thumb)
        if pa.minimum_exif_read_size_in_bytes_orientation is not None:
            orientation_read[pa.ext].append(pa.minimum_exif_read_size_in_bytes_orientation)
        if pa.minimum_exif_read_size_in_bytes_datetime is not None:
            datetime_read[pa.ext].append(pa.minimum_exif_read_size_in_bytes_datetime)

    exts = list(size_by_extension.keys())
    exts.sort()
    print("\nKB cached after thumbnail extraction:")
    for ext in exts:
        print(ext, Counter(size_by_extension[ext]).most_common())

    exts = list(orientation_read.keys())
    exts.sort()
    print("\nOrientation tag read:")
    for ext in exts:
        print(ext, Counter(orientation_read[ext]).most_common())

    exts = list(orientation_read.keys())
    exts.sort()
    print("\nDate time tag read:")
    for ext in exts:
        print(ext, Counter(datetime_read[ext]).most_common())

    print()
    if verbose:
        for pa in photos:
            print(pa)

    file_formats = FileFormatSQL()
    for pa in photos: # type: PhotoAttributes
        file_formats.add_format(pa)

def main():
    parser = argparse.ArgumentParser(
        description='Analyze the location of exif data in a variety of RAW and jpeg files.')
    parser.add_argument('source', action='store', help="Folder in which to recursively scan "
                            "for photos, or previously saved outfile.")
    parser.add_argument('outfile',  nargs='?', help="Optional file in which to save the analysis")
    parser.add_argument('--clear', '-c', action='store_true',
                        help="To work, this program requires that the scanned photos not "
                             "be in the Linux kernel's disk cache. This command instructs the "
                             "kernel to sync and then drop clean caches, as well as "
                        "reclaimable slab objects like dentries and inode. This is a "
                        "non-destructive operation and will not free any dirty objects. "
                        "See https://www.kernel.org/doc/Documentation/sysctl/vm.txt")
    parser.add_argument('--keep-names', '-k', dest='keep', action='store_true',
                        help="If saving the analysis to file, don't first remove the file names "
                             "and paths from the analysis. Don't specify this option if you want "
                             "to keep this information private when sharing the analysis with "
                             "others.")
    parser.add_argument('--no-dng', '-d', dest='dng', action='store_true',
                        help="Don't scan DNG files")
    parser.add_argument('--include-jpeg', '-j', dest='jpeg', action='store_true',
                        help="Scan jpeg images")
    parser.add_argument('--only-jpeg', '-J', dest='onlyjpeg', action='store_true',
                        help="Scan jpeg images")
    parser.add_argument('--show-errors', '-e', dest='errors', action='store_true',
                        help="Don't show progress bar while scanning, and instead show all errors "
                             "output by exiv2 (useful if exiv2 crashes, which takes down this "
                             "script too)")
    parser.add_argument('--load', '-l', dest='load', action='store_true',
                        help="Don't scan. Instead use previously generated outfile as input.")
    parser.add_argument('--verbose', '-v', dest='verbose', action='store_true',
                        help="Show more detailed output")
    args = parser.parse_args()

    if args.load:
        with open(args.source, 'rb') as infile:
            photos = pickle.load(infile)
        analyze(photos, args.verbose)
    else:
        if args.clear:
            subprocess.check_call('sync')
            try:
                with open('/proc/sys/vm/drop_caches', 'w') as stream:
                    stream.write('3\n')
            except PermissionError as e:
                print("You need superuser permission to run this script with the --clear option",
                      file=sys.stderr)
                sys.exit(1)


        if args.dng:
            RAW_EXTENSIONS.remove('dng')
            PHOTO_EXTENSIONS.remove('dng')

        if args.jpeg:
            scan_types = PHOTO_EXTENSIONS
        elif args.onlyjpeg:
            scan_types = JPEG_EXTENSIONS
        else:
            scan_types = RAW_EXTENSIONS

        photos = scan(args.source, args.clear, scan_types, args.errors, args.outfile,
                            args.keep)
        analyze(photos, args.verbose)

if __name__ == "__main__":
    main()


