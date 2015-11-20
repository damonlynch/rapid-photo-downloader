#!/usr/bin/python3
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
    the exif orientation.
"""

import scandir
import os
import textwrap
import subprocess
import shlex
import argparse
import resource
import shutil
import pickle
from collections import defaultdict, Counter
from enum import IntEnum
import sys
import time
import threading
import contextlib

from gi.repository import GExiv2
from PyQt5.QtGui import QImage

try:
    import pyprind
    have_progresbar = True
except ImportError:
    print("To see a progress bar install pyprind: https://github.com/rasbt/pyprind")
    have_progresbar = False

if not shutil.which('vmtouch'):
    print('You need to install vmtouch. Get it at http://hoytech.com/vmtouch/')
    sys.exit(0)


class PreviewSource(IntEnum):
    preview_1 = 0
    preview_2 = 1
    preview_3 = 2
    preview_4 = 3
    preview_5 = 4
    preview_6 = 5
    

page_size = resource.getpagesize()
to_kb = page_size // 1024

vmtouch_cmd = 'vmtouch -v "{}"'

RAW_EXTENSIONS = ['arw', 'dcr', 'cr2', 'crw',  'dng', 'mos', 'mef', 'mrw',
                  'nef', 'nrw', 'orf', 'pef', 'raf', 'raw', 'rw2', 'sr2',
                  'srw']

JPEG_EXTENSIONS = ['jpg', 'jpe', 'jpeg']

PHOTO_EXTENSIONS = RAW_EXTENSIONS + JPEG_EXTENSIONS

class PhotoAttributes:
    def __init__(self, full_file_name: str, ext: str, metadata: GExiv2.Metadata) -> None:

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
        self.preview_source = None # type: PreviewSource
        self.preview_width = None # type: int
        self.preview_height = None # type: int
        self.preview_extension = None  # type: str
        self.exif_thumbnail_and_preview_identical = None # type: bool
        self.minimum_exif_read_size_in_bytes = None # type: int

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
        if self.orientation is not None:
            self.minimum_extract_for_orientation()

    def assign_photo_attributes(self, metadata: GExiv2.Metadata) -> None:
        # I don't know how GExiv2 gets these values:
        self.width = metadata.get_pixel_width()
        self.height = metadata.get_pixel_height()
        # try:
        #     self.width = metadata['Xmp.exif.PixelXDimension']
        #     self.height = metadata['Xmp.exif.PixelYDimension']
        # except KeyError:
        #     if 'Exif.Photo.PixelXDimension' in metadata:
        #         self.width = metadata['Exif.Photo.PixelXDimension']
        #         self.height = metadata['Exif.Photo.PixelYDimension']
        #     else:
        #         try:
        #             self.width = metadata['Exif.Image.ImageWidth']
        #             self.height = metadata['Exif.Image.ImageLength']
        #         except KeyError:
        #             pass
        try:
            self.orientation = metadata['Exif.Image.Orientation']
        except KeyError:
            pass
        if 'Exif.Image.Make' in metadata and 'Exif.Image.Model' in metadata:
            model = '{} {}'.format(metadata['Exif.Image.Make'],
                                   metadata['Exif.Image.Model']).strip()
            self.model = '{} ({})'.format(model, self.ext)
    
        self.has_gps = metadata.get_gps_info()[0]
        self.iso = metadata.get_iso_speed()
    
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
    
        previews = metadata.get_preview_properties()
        self.no_previews = len(previews)
    
        for idx, preview in enumerate(previews):
            image = metadata.get_preview_image(preview)
            if image.get_width() >= 160 and image.get_height() >= 120:
                # Get the thumbnail but don't save it
                preview_thumbnail = metadata.get_preview_image(preview).get_data()
                if self.has_exif_thumbnail:
                    self.exif_thumbnail_and_preview_identical = preview_thumbnail == exif_thumbnail
                self.preview_source = PreviewSource(idx)
                self.preview_width = image.get_width()
                self.preview_height = image.get_height()
                self.preview_extension = image.get_extension()
                return

    def minimum_extract_for_orientation(self):
        if self.ext == 'CRW':
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
                        assert metadata['Exif.Image.Orientation'] == self.orientation
                    except KeyError:
                        pass
                    else:
                        self.minimum_exif_read_size_in_bytes = size_in_bytes
                        break

    def __str__(self):
        s = ''
        if self.model is not None:
            s += '{}\n'.format(self.model)
        elif self.file_name is not None:
            s += '{}\n'.format(os.path.split(self.file_name)[1])
        if self.width is not None:
            s += '{}x{}\n'.format(self.width, self.height)
        if self.iso:
            s += 'ISO: {}\n'.format(self.iso)
        if self.orientation is not None:
            s += 'Orientation: {}\n'.format(self.orientation)
        if self.has_gps:
            s += 'Has GPS tag: True\n'
        if self.has_exif_thumbnail:
            s += 'Exif thumbnail: {}x{}\n'.format(self.exif_thumbnail_width,
                                                 self.exif_thumbnail_height)
        if self.preview_source is not None:
            s += '{} of {}: {}x{} {}\n'.format(
                              self.preview_source.name.replace('_', ' ').capitalize(),
                              self.no_previews,
                              self.preview_width, self.preview_height,
                              self.preview_extension[1:])
        if self.exif_thumbnail_and_preview_identical is not None:
            s += 'Exif thumbnail is identical to preview: {}\n'.format(
                self.exif_thumbnail_and_preview_identical)
        s += 'Disk cache after exif read:\n[{}]\n'.format(self.in_memory)
        if self.in_memory != self.in_memory_post_thumb:
            s += 'Disk cache after thumbnail / preview extraction:\n[{}]\n'.format(
                self.in_memory_post_thumb)
        if self.bytes_cached == self.bytes_cached_post_thumb:
            s += 'Cached: {:,}KB of {:,}KB\n'.format(self.bytes_cached, self.total)
        else:
            s += 'Cached: {:,}KB(+{:,}KB after extraction) of {:,}KB\n'.format(
                self.bytes_cached, self.bytes_cached_post_thumb, self.total)
        if self.minimum_exif_read_size_in_bytes is not None:
            s += 'Minimum read size to extract orientation tag: {}\n'.format(
                format_size_for_user(self.minimum_exif_read_size_in_bytes, with_decimals=False))
        if self.minimum_exif_read_size_in_bytes is None and self.orientation is not None:
            s += 'Could not extract orientation tag with minimal read\n'
        return s


def exif_scan_range() -> int:
    stop = 20
    for iterations, step in ((108, 1), (97, 4), (16, 32), (16, 256), (16, 512), (8, 1024),
                             (8, 2048 * 4), (32, 2048 * 16)):
        start = stop
        stop = start + step * iterations
        for b in range(start, stop, step):
            yield b

def confirm(prompt: str=None, resp: bool=False) -> bool:
    r"""
    Prompts for yes or no response from the user.

    :param prompt: prompt displayed to user
    :param resp: the default value assumed by the caller when user
     simply types ENTER.
    :return: True for yes and False for no.

    >>> confirm(prompt='Create Directory?', resp=True)
    Create Directory? [y]|n:
    True
    >>> confirm(prompt='Create Directory?', resp=False)
    Create Directory? [n]|y:
    False
    >>> confirm(prompt='Create Directory?', resp=False)
    Create Directory? [n]|y: y
    True
    """

    if prompt is None:
        prompt = 'Confirm'

    if resp:
        prompt = '%s [%s]|%s: ' % (prompt, 'y', 'n')
    else:
        prompt = '%s [%s]|%s: ' % (prompt, 'n', 'y')

    while True:
        ans = input(prompt)
        if not ans:
            return resp
        if ans not in ['y', 'Y', 'n', 'N']:
            print('please enter y or n.')
            continue
        return ans in ['y', 'Y']

def format_size_for_user(size: int, zero_string='', with_decimals=True, kb_only=False) -> str:
    """
    Format an int containing the number of bytes into a string
    suitable for displaying to the user.

    source: https://develop.participatoryculture.org/trac/
    democracy/browser/trunk/tv/portable/util.py?rev=3993

    :param size: size in bytes
    :param zero_string: string to use if size == 0
    :param kb_only: display in KB or B
    """
    if size > (1 << 40) and not kb_only:
        value = (size / (1024.0 * 1024.0 * 1024.0 * 1024.0))
        if with_decimals:
            format = "%1.1fTB"
        else:
            format = "%dTB"
    elif size > (1 << 30) and not kb_only:
        value = (size / (1024.0 * 1024.0 * 1024.0))
        if with_decimals:
            format = "%1.1fGB"
        else:
            format = "%dGB"
    elif size > (1 << 20) and not kb_only:
        value = (size / (1024.0 * 1024.0))
        if with_decimals:
            format = "%1.1fMB"
        else:
            format = "%dMB"
    elif size > (1 << 10):
        value = (size / 1024.0)
        if with_decimals:
            format = "%1.1fKB"
        else:
            format = "%dKB"
    elif size > 1:
        value = size
        if with_decimals:
            format = "%1.1fB"
        else:
            format = "%dB"
    else:
        return zero_string
    return format % value

@contextlib.contextmanager
def stdchannel_redirected(stdchannel, dest_filename):
    """
    A context manager to temporarily redirect stdout or stderr

    Usage:
    with stdchannel_redirected(sys.stderr, os.devnull):
       do_work()

    Source: http://marc-abramowitz.com/archives/2013/07/19/
    python-context-manager-for-redirected-stdout-and-stderr/
    """
    oldstdchannel = dest_file = None
    try:
        oldstdchannel = os.dup(stdchannel.fileno())
        dest_file = open(dest_filename, 'w')
        os.dup2(dest_file.fileno(), stdchannel.fileno())

        yield
    finally:
        if oldstdchannel is not None:
            os.dup2(oldstdchannel, stdchannel.fileno())
        if dest_file is not None:
            dest_file.close()

@contextlib.contextmanager
def show_errors():
    print()
    yield
    print()

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

def main(folder: str, disk_cach_cleared: bool, scan_types: list, errors: bool,
         outfile: str, keep_file_names: bool) -> None:

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
                  "kerel disk cache:")
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

    with context:
        for full_file_name, ext in test_files:
            try:
                metadata = GExiv2.Metadata(full_file_name)
            except:
                print("Could not read metadata from {}".format(full_file_name))
            else:
                pa = PhotoAttributes(full_file_name, ext, metadata)
                photos.append(pa)

            if have_progresbar and not errors:
                bar.update()

    print()
    for pa in photos: # type: PhotoAttributes
        print(pa)

    if outfile is not None:
        if not keep_file_names:
            for pa in photos:
                pa.file_name = None

        with open(outfile, 'wb') as save_to:
            pickle.dump(photos, save_to, pickle.HIGHEST_PROTOCOL)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Analyze the location of exif data in a variety of RAW and jpeg files.')
    parser.add_argument('directory', action='store', help="Folder in which to recursively scan "
                                                          "for photos")
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
    parser.add_argument('--show-errors', '-e', dest='errors', action='store_true',
                        help="Don't show progress bar, and instead show all errors output by "
                             "exiv2 (useful if exiv2 crashes, which takes down this script too)")
    args = parser.parse_args()

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
    else:
        scan_types = RAW_EXTENSIONS

    main(args.directory, args.clear, scan_types, args.errors, args.outfile, args.keep)

