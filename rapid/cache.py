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

1. An image cache whose sole purpose is to store thumbnails of scanned files
   that have not necessarily been downloaded, but may have. This is only used
   by Rapid Photo Downloader. It's needed because it's important to save
   thumbnails that are not degraded by image resizing.
   Name: Thumbnail Cache
   Location: /home/USER/.cache/rapid-photo-downloader/thumbnails/normal
   (Actual location may vary depending on value of environment variable
   XDG_CACHE_HOME)

2. A cache of actual full files downloaded from a camera, which are then used
   to extract the thumbnail from. Since these same files could be downloaded,
   it makes sense to keep them cached until the program exits.
   Name: Download Cache
   Location: temporary subfolder in user specified download folder

3. The freedesktop.org thumbnail cache, for files that have been downloaded.
   Name: FDO Cache
   Location: /home/USER/.cache/thumbnails/
   (Actual location may vary depending on value of environment variable
   XDG_CACHE_HOME)

For the fdo cache specs, see:
http://specifications.freedesktop.org/thumbnail-spec/thumbnail-spec-latest.html
"""

import os
import sys
import logging
import hashlib
from urllib.request import pathname2url
import time
import shutil
from collections import namedtuple
from typing import Optional, Tuple

from PyQt5.QtCore import QSize
from PyQt5.QtGui import QImage

from storage import get_program_cache_directory, get_fdo_cache_thumb_base_directory
from utilities import GenerateRandomFileName
from constants import ThumbnailCacheDiskStatus
from rpdsql import CacheSQL


GetThumbnail = namedtuple('GetThumbnail', 'disk_status, thumbnail, path')
GetThumbnailPath = namedtuple('GetThumbnailPath', 'disk_status, path, orientation_unknown')

class MD5Name:
    """Generate MD5 hashes for file names."""
    def __init__(self) -> None:
        self.fs_encoding = sys.getfilesystemencoding()

    def get_uri(self, full_file_name: str, camera_model: Optional[str]=None) -> str:
        """
        :param full_file_name: path and file name of the file
        :param camera_model: if file is on a camera, the model of the
         camera
        :return: uri
        """
        if camera_model is None:
            prefix = 'file://'
            path = os.path.abspath(full_file_name)
        else:
            # This is not a system standard: I'm using this for my own
            # purposes (the port is not included, because it could easily vary)
            prefix = 'gphoto2://'
            path = '{}/{}'.format(camera_model, full_file_name)

        return '{}{}'.format(prefix, pathname2url(path))

    def md5_hash_name(self, full_file_name: str, camera_model: str=None,
                      extension: Optional[str]='png') -> Tuple[str, str]:
        """
        Generate MD5 hash for the file name.

        Uses file system encoding.

        :param full_file_name: path and file name of the file
        :param camera_model: if file is on a camera, the model of the
         camera
        :param extension: the extension to use in the file name
        :return: hash name and uri that was used to generate the hash
        """
        uri = self.get_uri(full_file_name, camera_model)
        return ('{md5}.{extension}'.format(
            md5=hashlib.md5(uri.encode(self.fs_encoding)).hexdigest(),
            extension=extension), uri)


class Cache:
    """
    Base class with which to write and read cache thumbnails.
    Creates fail directory if it doesn't exist, but does not create
    regular cache directory.
    """
    def __init__(self, cache_dir, failure_dir):
        """
        :param cache_dir: full path of the directory into which
         thumbnails will be saved / read
        :param failure_dir: full path of the directory into which
         failed thumbnails will be saved / read (thumbnails that could
         not be generated)
        """
        assert sys.platform.startswith('linux')
        self.cache_dir = cache_dir
        self.failure_dir = failure_dir
        self.valid = self.cache_dir is not None and self.failure_dir is not None
        if self.valid:
            self.random_filename = GenerateRandomFileName()
            self.md5 = MD5Name()
            try:
                if not os.path.exists(self.failure_dir):
                    os.makedirs(self.failure_dir, 0o700)
                    logging.debug("Created thumbnails failure cache %s",
                                  self.failure_dir)
                elif not os.path.isdir(self.failure_dir):
                    os.remove(self.failure_dir)
                    logging.warning("Removed file %s", self.failure_dir)
                    os.makedirs(self.failure_dir, 0o700)
                    logging.debug("Created thumbnails failure cache %s",
                                  self.failure_dir)
            except:
                logging.error("Failed to create Rapid Photo "
                              "Downloader thumbnail cache at %s",
                              self.failure_dir)
                self.valid = False

        if not self.valid:
            self.random_filename = self.fs_encoding = None


    def save_thumbnail(self, full_file_name: str, size: int,
                       modification_time, generation_failed: bool,
                       thumbnail: QImage,
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
        :param generation_failed: True if the thumbnail is meant to
         signify the application failed to generate the thumbnail. If
         so, it will be saved as an empty PNG in the application
         subdirectory in the fail cache directory.
        :param thumbnail: the thumbnail to be saved. Will not be
         resized. Will be ignored if generation_failed is True.
        :param camera_model: optional camera model. If the thumbnail is
         not from a camera, then should be None.
        :param free_desktop_org: if True, then image will be convereted
         to 8bit mode if neccessary
        :return the path of the saved file, else None if operation
        failed
        """
        if not self.valid:
            return None

        md5_name, uri = self.md5.md5_hash_name(full_file_name, camera_model)
        if generation_failed:
            thumbnail = QImage(QSize(1,1), QImage.Format_Indexed8)
            save_dir = self.failure_dir
        else:
            save_dir = self.cache_dir
        path = os.path.join(save_dir, md5_name)

        thumbnail.setText('Thumb::URI', uri)
        thumbnail.setText('Thumb::MTime', str(float(modification_time)))
        thumbnail.setText('Thumb::Size', str(size))

        if free_desktop_org and not generation_failed:
            if thumbnail.depth() != 8:
                thumbnail = thumbnail.convertToFormat(QImage.Format_Indexed8)

        temp_path = os.path.join(save_dir, self.random_filename.name(
            extension='png'))
        if thumbnail.save(temp_path):
            os.rename(temp_path, path)
            os.chmod(path, 0o600)
            if generation_failed:
                logging.debug("Wrote {}x{} thumbnail {} for {}".format(
                    thumbnail.width(), thumbnail.height(), path, uri))
            return path
        else:
            return None

    def get_thumbnail(self, full_file_name: str, modification_time, size: int,
                      camera_model: str=None) -> GetThumbnail:
        """
        Attempt to retrieve a thumbnail from the thumbnail cache.
        :param full_file_name: full path of the file (including file
        name). Will be turned into an absolute path if it is a file
        system path
        :param size: size of the file in bytes
        :param modification_time: file modification time, to be turned
         into a float if it's not already
        :param camera_model: optional camera model. If the thumbnail is
         not from a camera, then should be None.
        :return a GetThumbnail tuple of (1) ThumbnailCacheDiskStatus,
         to indicate whether the thumbnail was found, a failure, or
         missing (2) the thumbnail as QImage, if found (or None), and
         (3) the path (including the md5 name), else None,
        """

        def _get_thumbnail():
            if os.path.exists(path):
                png = QImage(path)
                if not png.isNull():
                    try:
                        mtime = float(png.text('Thumb::MTime'))
                        thumb_size = int(png.text('Thumb::Size'))
                    except ValueError:
                        return None
                    if (mtime == float(modification_time) and
                            thumb_size == size):
                        return png
            return None

        if not self.valid:
            return GetThumbnail(ThumbnailCacheDiskStatus.not_foud, None, None)
        md5_name, uri = self.md5.md5_hash_name(full_file_name=full_file_name,
                                               camera_model=camera_model)
        path = os.path.join(self.cache_dir, md5_name)
        png = _get_thumbnail()
        if png is not None:
            return GetThumbnail(ThumbnailCacheDiskStatus.found,
                                        png, path)
        path = os.path.join(self.failure_dir, md5_name)
        png = _get_thumbnail()
        if png is not None:
            return GetThumbnail(ThumbnailCacheDiskStatus.failure, None, None)
        return GetThumbnail(ThumbnailCacheDiskStatus.not_foud, None, None)

    def modify_existing_thumbnail_and_save_copy(self,
                              existing_cache_thumbnail: str,
                              full_file_name: str, modification_time,
                              size: int, generation_failed: bool) -> str:
        if generation_failed:
            #TODO account for failure here
            #should this ever happen?
            pass
        else:
            thumbnail = QImage(existing_cache_thumbnail)
            if not thumbnail.isNull():
                return self.save_thumbnail(full_file_name=full_file_name,
                       size=size, modification_time=modification_time,
                       generation_failed=False, thumbnail=thumbnail,
                       camera_model=None, free_desktop_org=False)
            else:
                return None

    def delete_thumbnail(self, full_file_name: str, camera_model: str=None):
        """
        Delete the thumbnail associated with the file if it exists
        """
        if not self.valid:
            return None
        md5_name, uri = self.md5_hash_name(full_file_name, camera_model)
        path = os.path.join(self.cache_dir, md5_name)
        if os.path.isfile(path):
            os.remove(path)
        else:
            path = os.path.join(self.failure_dir, md5_name)
            if os.path.isfile(path):
                os.remove(path)


class FdoCacheNormal(Cache):
    """
    Freedesktop.org thumbnail cache for thumbnails <= 128x128
    """
    def __init__(self):
        path = get_fdo_cache_thumb_base_directory()
        cache_dir = os.path.join(path, 'normal')
        failure_dir = os.path.join(path, 'fail/rapid-photo-downloader')
        super().__init__(cache_dir, failure_dir)


class FdoCacheLarge(Cache):
    """
    Freedesktop.org thumbnail cache for thumbnails > 128x128 & <= 256x256
    """
    def __init__(self):
        path = get_fdo_cache_thumb_base_directory()
        cache_dir = os.path.join(path, 'large')
        failure_dir = os.path.join(path, 'fail/rapid-photo-downloader')
        super().__init__(cache_dir, failure_dir)


class BaseThumbnailCache(Cache):
    """
    Creates a thumbnail cache in the Rapid Photo Downloader cache
    directory. Saves and checks for presence of thumbnails in it.
    """
    def __init__(self, cache_subfolder, failure_subfolder):
        cache_dir = get_program_cache_directory(create_if_not_exist=True)
        failure_dir = os.path.join(cache_dir, failure_subfolder)
        super().__init__(cache_dir, failure_dir)
        if self.valid:
            self.cache_dir = os.path.join(self.cache_dir, cache_subfolder)
            try:
                if not os.path.exists(self.cache_dir):
                    os.makedirs(self.cache_dir, 0o700)
                    logging.debug("Created thumbnails cache %s",
                                  self.cache_dir)
                elif not os.path.isdir(self.cache_dir):
                    os.remove(self.cache_dir)
                    logging.warning("Removed file %s", self.cache_dir)
                    os.makedirs(self.cache_dir, 0o700)
                    logging.debug("Created thumbnails cache %s",
                                  self.cache_dir)
            except:
                logging.error("Failed to create Rapid Photo "
                              "Downloader thumbnail cache at %s",
                              cache_dir)
                self.valid = False
                self.cache_dir = None
                self.random_filename = None
                self.fs_encoding = None

    def cleanup_cache(self):
        """
        Remove all thumbnails that have not been accessed for 30 days
        """
        if self.valid:
            i = 0
            now = time.time()
            for cache_dir in (self.cache_dir, self.failure_dir):
                for f in os.listdir(cache_dir ):
                    png = os.path.join(cache_dir , f)
                    if (os.path.isfile(png) and
                            os.path.getatime(png) < now - 2592000):
                        os.remove(png)
                        i += 1
                if i:
                    logging.debug('Deleted {} thumbnail files that had not been '
                              'accessed for 30 or more days'.format(i))

    def purge_cache(self):
        """
        Delete the entire cache of all contents and remvoe the
        directory
        """
        if self.valid:
            if self.cache_dir is not None and os.path.isdir(self.cache_dir):
                shutil.rmtree(self.cache_dir)
            if self.failure_dir is not None and os.path.isdir(self.failure_dir):
                shutil.rmtree(self.failure_dir)


class ThumbnailCache(BaseThumbnailCache):
    def __init__(self):
        super().__init__('thumbnails/normal', 'thumbnails/fail')


class ThumbnailCacheSql:

    not_found = GetThumbnail(ThumbnailCacheDiskStatus.not_foud, None, None)

    def __init__(self):
        self.cache_dir = get_program_cache_directory(create_if_not_exist=True)
        self.valid = self.cache_dir is not None
        if not self.valid:
            return

        assert self.cache_dir is not None
        self.cache_dir = os.path.join(self.cache_dir, 'thumbnails')
        try:
            if not os.path.exists(self.cache_dir):
                os.makedirs(self.cache_dir, 0o700)
                logging.debug("Created thumbnails cache %s",
                              self.cache_dir)
            elif not os.path.isdir(self.cache_dir):
                os.remove(self.cache_dir)
                logging.warning("Removed file %s", self.cache_dir)
                os.makedirs(self.cache_dir, 0o700)
                logging.debug("Created thumbnails cache %s",
                              self.cache_dir)
        except:
            logging.error("Failed to create Rapid Photo "
                          "Downloader thumbnail cache at %s",
                          self.cache_dir)
            self.valid = False
            self.cache_dir = None
            self.random_filename = None
            self.fs_encoding = None
        else:
            self.random_filename = GenerateRandomFileName()
            self.md5 = MD5Name()
            self.thumb_db = CacheSQL(self.cache_dir)

    def save_thumbnail(self, full_file_name: str, size: int,
                       modification_time: float,
                       generation_failed: bool,
                       orientation_unknown: bool,
                       thumbnail: Optional[QImage],
                       camera_model: Optional[str]=None) -> Optional[str]:
        """
        Save in the thumbnail cache using jpeg 75% compression.

        :param full_file_name: full path of the file (including file
        name). Will be turned into an absolute path if it is a file
        system path
        :param size: size of the file in bytes
        :param modification_time: file modification time, to be turned
         into a float if it's not already
        :param generation_failed: True if the thumbnail is meant to
         signify the application failed to generate the thumbnail. If
         so, it will be saved as an empty PNG in the application
         subdirectory in the fail cache directory.
        :param thumbnail: the thumbnail to be saved. Will not be
         resized. Will be ignored if generation_failed is True.
        :param camera_model: optional camera model. If the thumbnail is
         not from a camera, then should be None.
        :return the path of the saved file, else None if operation
        failed
        """

        if not self.valid:
            return None

        md5_name, uri = self.md5.md5_hash_name(full_file_name=full_file_name,
                                               camera_model=camera_model, extension='jpg')

        self.thumb_db.add_thumbnail(uri=uri, size=size, modification_time=modification_time,
                                    md5_name=md5_name, orientation_unknown=orientation_unknown,
                                    failure=generation_failed)
        if generation_failed:
            return None

        md5_full_name = os.path.join(self.cache_dir, md5_name)

        # thumbnail = thumbnail.convertToFormat()

        temp_path = os.path.join(self.cache_dir, self.random_filename.name(
            extension='jpg'))

        if thumbnail.save(temp_path, format='jpg', quality=75):
            try:
                os.rename(temp_path, md5_full_name)
                os.chmod(md5_full_name, 0o600)
            except OSError:
                return None

            return md5_full_name
        return None

    def get_thumbnail_path(self, full_file_name: str, modification_time, size: int,
                      camera_model: str=None) -> GetThumbnailPath:
        """
        Attempt to get a thumbnail's path from the thumbnail cache.

        :param full_file_name: full path of the file (including file
        name). Will be turned into an absolute path if it is a file
        system path
        :param size: size of the file in bytes
        :param modification_time: file modification time, to be turned
         into a float if it's not already
        :param camera_model: optional camera model. If the thumbnail is
         not from a camera, then should be None.
        :return a GetThumbnailPath tuple of (1) ThumbnailCacheDiskStatus,
         to indicate whether the thumbnail was found, a failure, or
         missing, (2) the path (including the md5 name), else None, and
         (3) a bool indicating whether the orientation of the thumbnail
          is unknown,
        """

        if not self.valid:
            return self.not_found

        uri = self.md5.get_uri(full_file_name, camera_model)
        in_cache = self.thumb_db.have_thumbnail(uri, size, modification_time)

        if in_cache is None:
            return self.not_found

        if in_cache.failure:
            return GetThumbnailPath(ThumbnailCacheDiskStatus.failure, None, None)

        path= os.path.join(self.cache_dir, in_cache.md5_name)
        if not os.path.exists(path):
            self.thumb_db.delete_thumbnails([in_cache.md5_name])
            return self.not_found

        return GetThumbnailPath(ThumbnailCacheDiskStatus.found, path, in_cache.orientation_unknown)


    def cleanup_cache(self):
        """
        Remove all thumbnails that have not been accessed for 30 days
        """
        time_period = 60 * 60 * 24 * 30
        if self.valid:
            i = 0
            now = time.time()
            deleted_thumbnails = []
            for name in os.listdir(self.cache_dir ):
                thumbnail = os.path.join(self.cache_dir , name)
                if (os.path.isfile(thumbnail) and
                        os.path.getatime(thumbnail) < now - time_period):
                    os.remove(thumbnail)
                    deleted_thumbnails.append(name)
            if len(deleted_thumbnails):
                self.thumb_db.delete_thumbnails(deleted_thumbnails)
                logging.debug('Deleted {} thumbnail files that had not been '
                          'accessed for 30 or more days'.format(len(deleted_thumbnails)))

    def purge_cache(self):
        """
        Delete the entire cache of all contents and remvoe the
        directory
        """
        if self.valid:
            if self.cache_dir is not None and os.path.isdir(self.cache_dir):
                # Delete the sqlite3 database too
                shutil.rmtree(self.cache_dir)


"""
Thumbnail cache goals:

if need to resize original to save, save 75% jpeg

Issues:

sqlite might grow big - vacuum


"""