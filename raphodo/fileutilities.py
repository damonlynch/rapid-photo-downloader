#!/usr/bin/env python3

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
Utility code to aid main code development -- not called from main code
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2015-2016, Damon Lynch"

import sys
import os
if sys.version_info < (3,5):
    import scandir
    walk = scandir.walk
else:
    walk = os.walk
import datetime
import time

import raphodo.metadataphoto as metadataphoto
import raphodo.metadatavideo as metadatavideo
from raphodo.constants import FileType
import raphodo.rpdfile as rpdfile
import raphodo.exiftool as exiftool


def set_file_modified_time_from_metadata(path: str):
    """
    Traverse a path, seeking photos & videos, and when located,
    set the file's modification time on the file system to match the
    metadata value in the file (e.g. exif, or video metadata (if
    valid)).

    Preserves access time.

    :param path: the folder which to walk
    """
    with exiftool.ExifTool() as exiftool_process:
        for dir_name, subdirs, file_list in walk(path):
            for file_name in file_list:
                base_name, ext = os.path.splitext(file_name)
                ext = ext.lower()[1:]
                file_type = rpdfile.file_type(ext)
                if file_type is not None:
                    file = os.path.join(dir_name, file_name)
                    modification_time = os.path.getmtime(file)
                    try:
                        if file_type == FileType.photo:
                            metadata = metadataphoto.MetaData(full_file_name=file,
                                                              et_process=exiftool_process)
                        else:
                            metadata = metadatavideo.MetaData(full_file_name=file,
                                                              et_process=exiftool_process)
                    except:
                        print("Could not load metadata for %s" % file)
                        break

                    dt = metadata.date_time(missing=None)
                    if dt is not None:
                        ts = time.mktime(dt.timetuple())
                        if ts != modification_time:
                            statinfo = os.stat(file)
                            access_time = statinfo.st_atime
                            print("Setting modification time for %s to %s"
                                  %(file_name, dt.strftime('%c')))
                            try:
                                os.utime(file, times=(access_time, ts))
                                print("Set modification time for %s to %s"
                                  %(file_name, dt.strftime('%c')))
                            except:
                                print("Setting file modificaiton time failed "
                                      "for %s" % file_name)

if __name__ == '__main__':
    set_file_modified_time_from_metadata(sys.argv[1])