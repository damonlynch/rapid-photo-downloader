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
Rapid Photo Downloader deals with three types of cache:

1. An image cache whose sole purpose is to store thumbnails of scanned images
   that have not necessarily been downloaded, but may have. This is only used
   by Rapid Photo Downloader.
   Name: thumbnail cache

2. A cache of actual full files downloaded from a camera, which are then used
   to extract the thumbnail from. Since these same files could be downloaded,
   it makes sense to keep them cached until the program exits.
   Name: download cache

3. The freedesktop.org thumbnail cache, for files that have been downloaded.
   Name: fdo cache

For the fdo cache specs, see:
http://specifications.freedesktop.org/thumbnail-spec/thumbnail-spec-latest.html
"""

import os
import sys
import logging
import hashlib
from urllib.request import pathname2url

from PyQt5.QtGui import QImage

from storage import get_program_cache_directory, get_fdo_cache_thumb_base_directory
from utilities import GenerateRandomFileName

logging.basicConfig(format='%(levelname)s:%(asctime)s:%(message)s',
                    datefmt='%H:%M:%S',
                    level=logging.DEBUG)

class Cache:
    def __init__(self, cache_dir):
        assert sys.platform.startswith('linux')
        self.cache_dir = cache_dir
        self.valid = self.cache_dir is not None
        if self.valid:
            self.random_filename = GenerateRandomFileName()
            self.fs_encoding = sys.getfilesystemencoding()
        else:
            self.random_filename = self.fs_encoding = None

    def md5_hash_name(self, full_file_name: str, camera_model: str=None):
        if camera_model is None:
            prefix = 'file://'
            path = os.path.abspath(full_file_name)
        else:
            # This is not a system standard: I'm using this for my own
            # purposes (the port is not included, because it could easily vary)
            prefix = 'gphoto2://'
            path = '{}/{}'.format(camera_model, full_file_name)

        uri = '{}{}'.format(prefix, pathname2url(path))
        return '{}.png'.format(hashlib.md5(uri.encode(
            self.fs_encoding)).hexdigest())

    def save_thumbnail(self, full_file_name: str, size: int,
                       modification_time, thumbnail: QImage,
                       camera_model: str=None,
                       free_desktop_org: bool=False) -> str:
        """
        Save a thumbnail in the thumbnail cache.
        :param full_file_name: full path of the file (including file
        name). Will be turned into an absolute path if it is a file
        system path
        :param size: size of the file in bytes
        :param modification_time: file modification time, to be turned
         into a float if it's not already
        :param thumbnail: the thumbnail to be saved. Will not be
         resized.
        :param camera_model: optional camera model. If the thumbnail is
         not from a camera, then should be None.
        :param free_desktop_org: if True, then image will be convereted
         to 8bit mode if neccessary
        :return the path of the saved file, else None if operation
        failed
        """
        if not self.valid:
            return None

        path = os.path.join(self.cache_dir,
                            self.md5_hash_name(full_file_name, camera_model))
        thumbnail.setText('Thumb::URI', path)
        thumbnail.setText('Thumb::MTime', str(float(modification_time)))
        thumbnail.setText('Thumb::Size', str(size))

        if free_desktop_org:
            if thumbnail.depth() != 8:
                thumbnail = thumbnail.convertToFormat(QImage.Format_Indexed8)
        temp_path = os.path.join(self.cache_dir, self.random_filename.name(
            extension='png'))
        if thumbnail.save(temp_path):
            os.rename(temp_path, path)
            os.chmod(path, 0o600)
            logging.debug("Wrote {}x{} thumbnail {}".format(thumbnail.width(),
                           thumbnail.height(), path))
            return path
        else:
            return None

    def get_thumbnail(self, full_file_name: str, modification_time,
                      camera_model: str=None) -> QImage:
        """
        Attempt to retrieve a thumbnail from the thumbnail cache.
        :param full_file_name: full path of the file (including file
        name). Will be turned into an absolute path if it is a file
        system path
        :param modification_time: file modification time, to be turned
         into a float if it's not already
        :param camera_model: optional camera model. If the thumbnail is
         not from a camera, then should be None.
        :return the thumbnail if it was found, else None
        """

        if not self.valid:
            return None
        path = os.path.join(self.cache_dir,
                            self.md5_hash_name(full_file_name, camera_model))
        if os.path.exists(path):
            png = QImage(path)
            if not png.isNull():
                mtime = float(png.text('Thumb::MTime'))
                if mtime == float(modification_time):
                    return png
        return None


class FdoCacheNormal(Cache):
    """
    Freedesktop.org thumbnail cache for thumbnails <= 128x128
    """
    def __init__(self, path=None):
        if path is None:
            path = os.path.join(get_fdo_cache_thumb_base_directory(), 'normal')
        super().__init__(path)

class FdoCacheLarge(FdoCacheNormal):
    """
    Freedesktop.org thumbnail cache for thumbnails > 128x128 & <= 256x256
    """
    def __init__(self):
        path = os.path.join(get_fdo_cache_thumb_base_directory(), 'large')
        super().__init__(path)


class ThumbnailCache(Cache):
    """
    Creates a thumbnail cache in the Rapid Photo Downloader cache
    directory. Saves and checks for presence of thumbnails in it.
    """
    def __init__(self):
        cache_dir = get_program_cache_directory(create_if_not_exist=True)
        super().__init__(cache_dir)
        if self.valid:
            self.cache_dir = os.path.join(self.cache_dir, 'thumbnails/normal')
            try:
                if not os.path.exists(self.cache_dir):
                    os.makedirs(self.cache_dir, 0o700)
                    logging.info("Created thumbnails cache %s", self.cache_dir)
                elif not os.path.isdir(self.cache_dir):
                    os.remove(self.cache_dir)
                    logging.warning("Removed file %s", self.cache_dir)
                    os.makedirs(self.cache_dir, 0o700)
                    logging.info("Created thumbnails cache %s", self.cache_dir)
            except:
                logging.error("Failed to create Rapid Photo "
                              "Downloader thumbnail cache %s",
                              self.cache_dir)
                self.valid = False
                self.cache_dir = None
                self.random_filename = None
                self.fs_encoding = None
