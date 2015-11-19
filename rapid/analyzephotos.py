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
Analyze various exif attributes of RAW and jpeg files.


Two goals:
 1) Analyze what part of a file is loaded from disk when exif metadata
    is read:
        1a) When reading only the exif.
        2a) When extracting a preview.
    Need to know how much to read, and where to read it from.
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
    

class PreviewSource(IntEnum):
    preview_1 = 0
    preview_2 = 1
    preview_3 = 2
    preview_4 = 3
    preview_5 = 4
    preview_6 = 5
    

page_size =  resource.getpagesize()
to_kb = page_size // 1024

vmtouch_cmd = 'vmtouch -v "{}"'

RAW_EXTENSIONS = ['arw', 'dcr', 'cr2', 'crw',  'dng', 'mos', 'mef', 'mrw',
                  'nef', 'nrw', 'orf', 'pef', 'raf', 'raw', 'rw2', 'sr2',
                  'srw']

JPEG_EXTENSIONS = ['jpg', 'jpe', 'jpeg']

PHOTO_EXTENSIONS = RAW_EXTENSIONS + RAW_EXTENSIONS

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
        self.exif_thumbnail = None # type: bytes
        self.exif_thumbnail_height = None # type: int
        self.exif_thumbnail_width = None # type: int
        self.preview = None # type: bytes
        self.preview_source = None # type: PreviewSource
        self.preview_width = None # type: int
        self.preview_height = None # type: int
        self.preview_extension = None  # type: str

        self.file_name = full_file_name
        self.ext = ext
        # Before doing anything else, get these values
        self.bytes_cached, self.total, self.in_memory = vmtouch_output(full_file_name)
        self.assignPhotoAttributes(metadata)
        self.extractThumbnail(metadata)
        self.bytes_cached_post_thumb, total, self.in_memory_post_thumb = vmtouch_output(
            full_file_name)

    def assignPhotoAttributes(self, metadata: GExiv2.Metadata) -> None:
        # I don't know how it gets these values:
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
    
    def extractThumbnail(self, metadata: GExiv2.Metadata) -> None:
        # not all files have an exif preview, but all CR2 seem to
        ep = metadata.get_exif_thumbnail()
        if ep:
            # Get the thumbnail but don't save it
            self.exif_thumbnail = metadata.get_exif_thumbnail()
            self.has_exif_thumbnail = True
            qimage = QImage.fromData(self.exif_thumbnail)
            if not qimage.isNull():
                self.exif_thumbnail_width = qimage.width()
                self.exif_thumbnail_height = qimage.height()
    
        previews = metadata.get_preview_properties()
        self.no_previews = len(previews)
    
        for idx, preview in enumerate(previews):
            image = metadata.get_preview_image(preview)
            if image.get_width() >= 160 and image.get_height() >= 120:
                # Get the thumbnail but don't save it
                self.preview = metadata.get_preview_image(preview).get_data()
                self.preview_source = PreviewSource(idx)
                self.preview_width = image.get_width()
                self.preview_height = image.get_height()
                self.preview_extension = image.get_extension()
                return

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
            s += 'Has GPS tag\n'
        if self.has_exif_thumbnail:
            s += 'Exif thumbnail {}x{}\n'.format(self.exif_thumbnail_width,
                                                 self.exif_thumbnail_height)
        if self.preview_source is not None:
            s += '{} of {} ({}x{} {})\n'.format(
                              self.preview_source.name.replace('_', ' ').capitalize(),
                              self.no_previews,
                              self.preview_width, self.preview_height,
                              self.preview_extension[1:])
        if self.exif_thumbnail is not None and self.preview is not None:
            s += 'Exif thumbnail is identical to preview: {}\n'.format(self.exif_thumbnail ==
                                                                      self.preview)
        s += 'Disk cache after exif read:\n[{}]\n'.format(self.in_memory)
        if self.in_memory != self.in_memory_post_thumb:
            s += 'Disk cache after thumbnail / preview extraction:\n[{}]\n'.format(
                self.in_memory_post_thumb)
        if self.bytes_cached == self.bytes_cached_post_thumb:
            s += 'Cached: {:,} Kb of {:,} Kb\n'.format(self.bytes_cached, self.total)
        else:
            s += 'Cached: {:,} Kb(+{:,} Kb after extraction) of {:,}Kb\n'.format(
                self.bytes_cached, self.bytes_cached_post_thumb, self.total)
        return s


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

class progress_bar_scanning(threading.Thread):
    # Adapted from from http://thelivingpearl.com/2012/12/31/
    # creating-progress-bars-with-python/
    def run(self):
            # global stop
            # global kill
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

def main(folder: str, disk_cach_cleared: bool) -> None:

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
            if ext in RAW_EXTENSIONS:
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
                                      "already in the disk cache.".format(len(not_tested)),
                                      width=80):
                print(line)
        else:
            print("WARNING: these files will not be analyzed because they are already in the disk "
                  "cache:")
            for name in not_tested:
                print(name)
        for line in textwrap.wrap("Run this script as super user and use command line option -c or "
                            "--clear to safely clear the disk cache.", width=80):
            print(line)

    photos = []

    if test_files:
        print("\nAnalyzing {:,} files:".format(len(test_files)))
        if have_progresbar:
            bar = pyprind.ProgBar(iterations=len(test_files), stream=1, track_time=False, width=80)

    # Phase 2
    # Get info from files

    # Redirect stderr, hiding error output from exiv2
    with stdchannel_redirected(sys.stderr, os.devnull):
        for full_file_name, ext in test_files:
            try:
                metadata = GExiv2.Metadata(full_file_name)
            except:
                print("Could not read metadata from {}".format(full_file_name))
            else:
                pa = PhotoAttributes(full_file_name, ext, metadata)
                photos.append(pa)

            if have_progresbar:
                bar.update()

    print()
    for pa in photos: # type: PhotoAttributes
        print(pa)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', action = 'store', nargs = '+')
    parser.add_argument('--clear', '-c', action='store_true')
    parser.add_argument('--no-dng', '-d', dest='dng', action='store_true')
    args = parser.parse_args()

    if args.clear:
        subprocess.check_call('sync')
        with open('/proc/sys/vm/drop_caches', 'w') as stream:
            stream.write('3\n')

    if args.dng:
        RAW_EXTENSIONS.remove('dng')

    main(args.directory[0], args.clear)

