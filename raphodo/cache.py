#!/usr/bin/env python3

# Copyright (C) 2015-2021 Damon Lynch <damonlynch@gmail.com>

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
   Location: /home/USER/.cache/rapid-photo-downloader/thumbnails/
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

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2015-2021, Damon Lynch"

import os
import sys
import logging
import hashlib
from urllib.request import pathname2url
import time
import shutil
from collections import namedtuple
from typing import Optional, Tuple, Union
import sqlite3

from PyQt5.QtCore import QSize
from PyQt5.QtGui import QImage

from raphodo.storage.storage import (
    get_program_cache_directory,
    get_fdo_cache_thumb_base_directory,
)
from raphodo.utilities import GenerateRandomFileName, format_size_for_user
from raphodo.constants import ThumbnailCacheDiskStatus
from raphodo.rpdsql import CacheSQL


GetThumbnail = namedtuple("GetThumbnail", "disk_status, thumbnail, path")
GetThumbnailPath = namedtuple(
    "GetThumbnailPath", "disk_status, path, mdatatime, orientation_unknown"
)


class MD5Name:
    """Generate MD5 hashes for file names."""

    def __init__(self) -> None:
        self.fs_encoding = sys.getfilesystemencoding()

    def get_uri(self, full_file_name: str, camera_model: Optional[str] = None) -> str:
        """
        :param full_file_name: path and file name of the file
        :param camera_model: if file is on a camera, the model of the
         camera
        :return: uri
        """
        if camera_model is None:
            prefix = "file://"
            path = os.path.abspath(full_file_name)
        else:
            # This is not a system standard: I'm using this for my own
            # purposes (the port is not included, because it could easily vary)
            prefix = "gphoto2://"
            path = "{}/{}".format(camera_model, full_file_name)

        return "{}{}".format(prefix, pathname2url(path))

    def md5_hash_name(
        self,
        full_file_name: str,
        camera_model: str = None,
        extension: Optional[str] = "png",
    ) -> Tuple[str, str]:
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
        return (
            "{md5}.{extension}".format(
                md5=hashlib.md5(uri.encode(self.fs_encoding)).hexdigest(),
                extension=extension,
            ),
            uri,
        )


class Cache:
    """
    Base class with which to write and read cache thumbnails.
    Create cache if it doesn't exist; checks validity.
    """

    def __init__(self, cache_dir: str, failure_dir: Optional[str]) -> None:
        """
        Create cache if it doesn't exist; checks validity.

        :param cache_dir: full path of the directory into which
         thumbnails will be saved / read.
        :param failure_dir: full path of the directory into which
         failed thumbnails will be saved / read (thumbnails that could
         not be generated)
        """

        assert sys.platform.startswith("linux")
        self.cache_dir = cache_dir
        self.failure_dir = failure_dir
        assert self.cache_dir

        self.valid = self._create_directory(self.cache_dir, "Freedesktop.org thumbnail")

        if self.valid:
            self.random_filename = GenerateRandomFileName()
            self.md5 = MD5Name()
            if self.failure_dir is not None:
                self.valid = self._create_directory(
                    self.failure_dir, "thumbnails failure"
                )

        if not self.valid:
            self.random_filename = self.fs_encoding = None

    def _create_directory(self, dir: str, descrtiption: str) -> bool:
        try:
            if not os.path.exists(dir):
                os.makedirs(dir, 0o700)
                logging.debug("Created %s cache at %s", descrtiption, dir)
            elif not os.path.isdir(dir):
                os.remove(dir)
                logging.warning("Removed file %s", dir)
                os.makedirs(dir, 0o700)
                logging.debug("Created %s cache at %s", descrtiption, dir)
        except OSError:
            logging.error("Failed to create %s cache at %s", descrtiption, dir)
            return False
        return True

    def save_thumbnail(
        self,
        full_file_name: str,
        size: int,
        modification_time: Union[float, int],
        generation_failed: bool,
        thumbnail: QImage,
        camera_model: str = None,
        free_desktop_org: bool = True,
    ) -> Optional[str]:
        """
        Save a thumbnail in the thumbnail cache.

        :param full_file_name: full path of the file (including file
         name). If the path contains symbolic links, two thumbnails will be
         saved: the canonical path (without symlinks), and the path as
         passed.
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
         to 8bit mode if necessary
        :return the md5_name of the saved file, else None if operation
        failed
        """

        if not self.valid:
            return None

        # Save to both the real path and the path passed, which may include
        # symbolic links
        full_file_name_real_path = os.path.realpath(full_file_name)
        if full_file_name_real_path != full_file_name:
            self.save_thumbnail(
                full_file_name_real_path,
                size,
                modification_time,
                generation_failed,
                thumbnail,
                camera_model,
                free_desktop_org,
            )

        md5_name, uri = self.md5.md5_hash_name(full_file_name, camera_model)
        if generation_failed:
            thumbnail = QImage(QSize(1, 1), QImage.Format_Indexed8)
            save_dir = self.failure_dir
        else:
            save_dir = self.cache_dir
        path = os.path.join(save_dir, md5_name)

        thumbnail.setText("Thumb::URI", uri)
        thumbnail.setText("Thumb::MTime", str(float(modification_time)))
        thumbnail.setText("Thumb::Size", str(size))

        if free_desktop_org and not generation_failed:
            if thumbnail.depth() != 8:
                thumbnail = thumbnail.convertToFormat(QImage.Format_Indexed8)

        temp_path = os.path.join(save_dir, self.random_filename.name(extension="png"))
        if thumbnail.save(temp_path):
            os.rename(temp_path, path)
            os.chmod(path, 0o600)
            if generation_failed:
                logging.debug(
                    "Wrote {}x{} thumbnail {} for {}".format(
                        thumbnail.width(), thumbnail.height(), path, uri
                    )
                )
            return md5_name
        else:
            return None

    def _get_thumbnail(
        self, path: str, modification_time: float, size: int
    ) -> Optional[bytes]:
        if os.path.exists(path):
            png = QImage(path)
            if not png.isNull():
                try:
                    mtime = float(png.text("Thumb::MTime"))
                    thumb_size = int(png.text("Thumb::Size"))
                except ValueError:
                    return None
                if mtime == float(modification_time) and thumb_size == size:
                    return png
        return None

    def get_thumbnail_md5_name(
        self, full_file_name: str, camera_model: Optional[str] = None
    ) -> str:
        """
        Returns the md5 name for the photo or video. Does not check if the file exists
        on the file system in the cache.

        :param full_file_name: full_file_name: full path of the file (including file
        name). Will be turned into an absolute path if it is a file
        system path
        :param camera_model: optional camera model. If the thumbnail is
         not from a camera, then should be None.
        :return: the md5 name
        """

        return self.md5.md5_hash_name(
            full_file_name=full_file_name, camera_model=camera_model
        )[0]

    def get_thumbnail(
        self,
        full_file_name: str,
        modification_time,
        size: int,
        camera_model: Optional[str] = None,
    ) -> GetThumbnail:
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

        if not self.valid:
            return GetThumbnail(ThumbnailCacheDiskStatus.not_found, None, None)
        md5_name, uri = self.md5.md5_hash_name(
            full_file_name=full_file_name, camera_model=camera_model
        )
        path = os.path.join(self.cache_dir, md5_name)
        png = self._get_thumbnail(path, modification_time, size)
        if png is not None:
            return GetThumbnail(ThumbnailCacheDiskStatus.found, png, path)
        if self.failure_dir is not None:
            path = os.path.join(self.failure_dir, md5_name)
            png = self._get_thumbnail(path, modification_time, size)
            if png is not None:
                return GetThumbnail(ThumbnailCacheDiskStatus.failure, None, None)
        return GetThumbnail(ThumbnailCacheDiskStatus.not_found, None, None)

    def modify_existing_thumbnail_and_save_copy(
        self,
        existing_cache_thumbnail: str,
        full_file_name: str,
        modification_time,
        size: int,
        error_on_missing_thumbnail: bool,
    ) -> Optional[str]:
        """

        :param existing_cache_thumbnail: the md5 name of the cache thumbnail,
         without the path to the cache
        :param full_file_name: full path of the file (including file
        name). Will be turned into an absolute path if need be
        :param size: size of the file in bytes
        :param modification_time: file modification time, to be turned
         into a float if it's not already
        :param error_on_missing_thumbnail: if True, issue error if thumbnail is
         not located (useful when dealing with FDO 128 cache, but not helpful
         with FDO 256 cache as not all RAW files have thumbnails large enough)
        :return: the path of the saved file, else None if operation
        failed
        """

        existing_cache_thumbnail_full_path = os.path.join(
            self.cache_dir, existing_cache_thumbnail
        )
        if not os.path.isfile(existing_cache_thumbnail_full_path):
            if error_on_missing_thumbnail:
                logging.error("No FDO thumbnail to copy for %s", full_file_name)
            return None
        thumbnail = QImage(existing_cache_thumbnail_full_path)
        if not thumbnail.isNull():
            return self.save_thumbnail(
                full_file_name=full_file_name,
                size=size,
                modification_time=modification_time,
                generation_failed=False,
                thumbnail=thumbnail,
                camera_model=None,
                free_desktop_org=False,
            )
        else:
            return None


class FdoCacheNormal(Cache):
    """
    Freedesktop.org thumbnail cache for thumbnails <= 128x128
    """

    def __init__(self):
        path = get_fdo_cache_thumb_base_directory()
        cache_dir = os.path.join(path, "normal")
        failure_dir = None
        super().__init__(cache_dir, failure_dir)


class FdoCacheLarge(Cache):
    """
    Freedesktop.org thumbnail cache for thumbnails > 128x128 & <= 256x256
    """

    def __init__(self):
        path = get_fdo_cache_thumb_base_directory()
        cache_dir = os.path.join(path, "large")
        failure_dir = None
        super().__init__(cache_dir, failure_dir)


class ThumbnailCacheSql:

    not_found = GetThumbnailPath(ThumbnailCacheDiskStatus.not_found, None, None, None)

    def __init__(self, create_table_if_not_exists: bool) -> None:
        self.cache_dir = get_program_cache_directory(create_if_not_exist=True)
        self.valid = self.cache_dir is not None
        if not self.valid:
            return

        assert self.cache_dir is not None
        self.cache_dir = os.path.join(self.cache_dir, "thumbnails")
        try:
            if not os.path.exists(self.cache_dir):
                os.makedirs(self.cache_dir, 0o700)
                logging.debug("Created thumbnails cache %s", self.cache_dir)
            elif not os.path.isdir(self.cache_dir):
                os.remove(self.cache_dir)
                logging.warning("Removed file %s", self.cache_dir)
                os.makedirs(self.cache_dir, 0o700)
                logging.debug("Created thumbnails cache %s", self.cache_dir)
        except:
            logging.error(
                "Failed to create Rapid Photo Downloader Thumbnail Cache at %s",
                self.cache_dir,
            )
            self.valid = False
            self.cache_dir = None
            self.random_filename = None
            self.fs_encoding = None
        else:
            self.random_filename = GenerateRandomFileName()
            self.md5 = MD5Name()
            self.thumb_db = CacheSQL(self.cache_dir, create_table_if_not_exists)

    def save_thumbnail(
        self,
        full_file_name: str,
        size: int,
        mtime: float,
        mdatatime: float,
        generation_failed: bool,
        orientation_unknown: bool,
        thumbnail: Optional[QImage],
        camera_model: Optional[str] = None,
    ) -> Optional[str]:
        """
        Save in the thumbnail cache using jpeg 75% compression.

        :param full_file_name: full path of the file (including file
        name). Will be turned into an absolute path if it is a file
        system path
        :param size: size of the file in bytes
        :param mtime: file modification time
        :param mdatatime: file time recorded in metadata
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

        md5_name, uri = self.md5.md5_hash_name(
            full_file_name=full_file_name, camera_model=camera_model, extension="jpg"
        )

        if generation_failed:
            logging.debug("Marking thumbnail for %s as 'generation failed'", uri)
        else:
            logging.debug("Saving thumbnail for %s in RPD thumbnail cache", uri)

        try:
            self.thumb_db.add_thumbnail(
                uri=uri,
                size=size,
                mtime=mtime,
                mdatatime=mdatatime,
                md5_name=md5_name,
                orientation_unknown=orientation_unknown,
                failure=generation_failed,
            )
        except sqlite3.OperationalError as e:
            logging.error(
                "Database error adding thumbnail for %s: %s. Will not retry.", uri, e
            )
            return None

        if generation_failed:
            return None

        md5_full_name = os.path.join(self.cache_dir, md5_name)

        temp_path = os.path.join(
            self.cache_dir, self.random_filename.name(extension="jpg")
        )

        if thumbnail.save(temp_path, format="jpg", quality=75):
            try:
                os.rename(temp_path, md5_full_name)
                os.chmod(md5_full_name, 0o600)
            except OSError:
                return None

            return md5_full_name
        return None

    def get_thumbnail_path(
        self, full_file_name: str, mtime, size: int, camera_model: str = None
    ) -> GetThumbnailPath:
        """
        Attempt to get a thumbnail's path from the thumbnail cache.

        :param full_file_name: full path of the file (including file
        name). Will be turned into an absolute path if it is a file
        system path
        :param size: size of the file in bytes
        :param mtime: file modification time, to be turned
         into a float if it's not already
        :param camera_model: optional camera model. If the thumbnail is
         not from a camera, then should be None.
        :return a GetThumbnailPath tuple of (1) ThumbnailCacheDiskStatus,
         to indicate whether the thumbnail was found, a failure, or
         missing, (2) the path (including the md5 name), else None,
         (3) the file's metadata time, and (4) a bool indicating whether
         the orientation of the thumbnail is unknown
        """

        if not self.valid:
            return self.not_found

        uri = self.md5.get_uri(full_file_name, camera_model)
        in_cache = self.thumb_db.have_thumbnail(uri, size, mtime)

        if in_cache is None:
            return self.not_found

        if in_cache.failure:
            return GetThumbnailPath(
                ThumbnailCacheDiskStatus.failure, None, in_cache.mdatatime, None
            )

        path = os.path.join(self.cache_dir, in_cache.md5_name)
        if not os.path.exists(path):
            self.thumb_db.delete_thumbnails([in_cache.md5_name])
            return self.not_found

        return GetThumbnailPath(
            ThumbnailCacheDiskStatus.found,
            path,
            in_cache.mdatatime,
            in_cache.orientation_unknown,
        )

    def cleanup_cache(self, days: int = 30) -> None:
        """
        Remove all thumbnails that have not been accessed for x days

        :param how many days to remove from
        """
        time_period = 60 * 60 * 24 * days
        if self.valid:
            i = 0
            now = time.time()
            deleted_thumbnails = []
            for name in os.listdir(self.cache_dir):
                thumbnail = os.path.join(self.cache_dir, name)
                if (
                    os.path.isfile(thumbnail)
                    and os.path.getatime(thumbnail) < now - time_period
                ):
                    os.remove(thumbnail)
                    deleted_thumbnails.append(name)
            if len(deleted_thumbnails):
                if self.thumb_db.cache_exists():
                    self.thumb_db.delete_thumbnails(deleted_thumbnails)
                logging.debug(
                    "Deleted {} thumbnail files that had not been accessed for {} "
                    "or more days".format(len(deleted_thumbnails), days)
                )

    def purge_cache(self) -> None:
        """
        Delete the entire cache of all contents and remove the
        directory
        """
        if self.valid:
            if self.cache_dir is not None and os.path.isdir(self.cache_dir):
                # Delete the sqlite3 database too
                shutil.rmtree(self.cache_dir)

    def no_thumbnails(self) -> int:
        """
        :return: how many thumbnails there are in the thumbnail database
        """

        if not self.valid:
            return 0
        return self.thumb_db.no_thumbnails()

    def cache_size(self) -> int:
        """
        :return: the size of the entire cache (include the database) in bytes
        """

        if not self.valid:
            return 0
        cwd = os.getcwd()
        os.chdir(self.cache_dir)
        s = sum(os.path.getsize(f) for f in os.listdir(".") if os.path.isfile(f))
        os.chdir(cwd)
        return s

    def db_size(self) -> int:
        """
        :return: the size in bytes of the sql database file
        """

        if not self.valid:
            return 0
        return os.path.getsize(self.thumb_db.db)

    def optimize(self) -> Tuple[int, int, int]:
        """
        Check for any thumbnails in the db that are not in the file system
        Check for any thumbnails exist on the file system that are not in the db
        Vacuum the db

        :return db rows removed, file system photos removed, db size reduction in bytes
        """

        rows = self.thumb_db.md5_names()
        rows = {row[0] for row in rows}
        cwd = os.getcwd()
        os.chdir(self.cache_dir)

        to_delete_from_db = {md5 for md5 in rows if not os.path.exists(md5)}
        if len(to_delete_from_db):
            self.thumb_db.delete_thumbnails(list(to_delete_from_db))

        md5s = {md5 for md5 in os.listdir(".")} - {self.thumb_db.db_fs_name()}
        to_delete_from_fs = md5s - rows
        if len(to_delete_from_fs):
            for md5 in to_delete_from_fs:
                os.remove(md5)

        os.chdir(cwd)

        size = self.db_size()
        self.thumb_db.vacuum()

        return len(to_delete_from_db), len(to_delete_from_fs), size - self.db_size()


if __name__ == "__main__":
    db = ThumbnailCacheSql(create_table_if_not_exists=True)
    db.optimize()
