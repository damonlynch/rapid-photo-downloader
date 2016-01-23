#!/usr/bin/python3

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

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2015-2016, Damon Lynch"

import sqlite3
import os
import datetime
from collections import namedtuple
from typing import Optional
import sys

from storage import (get_program_data_directory, get_program_cache_directory)
from utilities import divide_list_on_length
from photoattributes import PhotoAttributes

FileDownloaded = namedtuple('FileDownloaded', 'download_name, download_datetime')

InCache = namedtuple('InCache', 'md5_name, orientation_unknown, failure')

class DownloadedSQL:
    """
    Previous file download detection.

    Used to detect if a file has been downloaded before. A file is the
    same if the file name (excluding path), size and modification time
    are the same. For performance reasons, Exif information is never
    checked.
    """
    def __init__(self, data_dir: str=None) -> None:
        """
        :param data_dir: where the database is saved. If None, use
         default
        """
        if data_dir is None:
            data_dir = get_program_data_directory(create_if_not_exist=True)

        self.db = os.path.join(data_dir, 'downloaded_files.sqlite')
        self.table_name = 'downloaded'
        self.update_table()

    def update_table(self, reset: bool=False) -> None:
        """
        Create or update the database table
        :param reset: if True, delete the contents of the table and
         build it
        """

        conn = sqlite3.connect(self.db, detect_types=sqlite3.PARSE_DECLTYPES)

        if reset:
            conn.execute(r"""DROP TABLE IF EXISTS {tn}""".format(
                tn=self.table_name))
            conn.execute("VACUUM")

        conn.execute("""CREATE TABLE IF NOT EXISTS {tn} (
        file_name TEXT NOT NULL,
        mtime REAL NOT NULL,
        size INTEGER NOT NULL,
        download_name TEXT NOT NULL,
        download_datetime timestamp,
        PRIMARY KEY (file_name, mtime, size)
        )""".format(tn=self.table_name))

        conn.execute("""CREATE INDEX IF NOT EXISTS download_datetime_idx ON
        {tn} (download_name)""".format(tn=self.table_name))

        conn.commit()
        conn.close()

    def add_downloaded_file(self, name: str, size: int,
                            modification_time: float, download_full_file_name: str) -> None:
        """
        Add file to database of downloaded files
        :param name: original filename of photo / video, without path
        :param size: file size
        :param modification_time: file modification time
        :param download_full_file_name: renamed file including path
        """
        conn = sqlite3.connect(self.db)

        conn.execute(r"""INSERT OR REPLACE INTO {tn} (file_name, size, mtime,
        download_name, download_datetime) VALUES (?,?,?,?,?)""".format(
            tn=self.table_name), (name, size, modification_time,
            download_full_file_name, datetime.datetime.now()))

        conn.commit()
        conn.close()

    def file_downloaded(self, name: str, size: int, modification_time: float) -> FileDownloaded:
        """
        Returns download path and filename if a file with matching
        name, modification time and size has previously been downloaded
        :param name: file name, not including path
        :param size: file size in bytes
        :param modification_time: file modification time
        :return: download name (including path) and when it was
         downloaded, else None if never downloaded
        """
        conn = sqlite3.connect(self.db, detect_types=sqlite3.PARSE_DECLTYPES)
        c = conn.cursor()
        c.execute("""SELECT download_name, download_datetime as [timestamp] FROM {tn} WHERE
        file_name=? AND size=? AND mtime=?""".format(
            tn=self.table_name), (name, size, modification_time))
        row = c.fetchone()
        if row is not None:
            return FileDownloaded._make(row)
        else:
            return None

class CacheSQL:
    def __init__(self, location: str=None) -> None:
        if location is None:
            location = get_program_cache_directory(create_if_not_exist=True)
        self.db = os.path.join(location, 'thumbnail_cache.sqlite')
        self.table_name = 'cache'
        self.update_table()

    def update_table(self, reset: bool=False) -> None:
        """
        Create or update the database table
        :param reset: if True, delete the contents of the table and
         build it
        """
        conn = sqlite3.connect(self.db)

        if reset:
            conn.execute(r"""DROP TABLE IF EXISTS {tn}""".format(
                tn=self.table_name))
            conn.execute("VACUUM")

        conn.execute("""CREATE TABLE IF NOT EXISTS {tn} (
        uri TEXT NOT NULL,
        mtime REAL NOT NULL,
        size INTEGER NOT NULL,
        md5_name INTEGER NOT NULL,
        orientation_unknown INTEGER NOT NULL,
        failure INTEGER NOT NULL,
        PRIMARY KEY (uri, mtime, size)
        )""".format(tn=self.table_name))

        conn.execute("""CREATE INDEX IF NOT EXISTS md5_name_idx ON
        {tn} (md5_name)""".format(tn=self.table_name))

        conn.commit()
        conn.close()

    def add_thumbnail(self, uri: str, size: int, modification_time: float, md5_name: str,
                      orientation_unknown: bool,
                      failure: bool) -> None:
        """
        Add file to database of downloaded files
        :param uri: original filename of photo / video with path
        :param size: file size
        :param modification_time: file modification time
        :param md5_name: full file name converted to md5
        :param orientation_unknown: if True, the orientation of the
         file could not be determined, else False
        :param failure: if True, indicates the thumbnail could not be
         generated, otherwise False
        """
        conn = sqlite3.connect(self.db)

        failure = int(failure)

        conn.execute(r"""INSERT OR REPLACE INTO {tn} (uri, size, mtime,
        md5_name, orientation_unknown, failure) VALUES (?,?,?,?,?,?)""".format(
            tn=self.table_name), (uri, size, modification_time, md5_name, orientation_unknown,
                                  failure))

        conn.commit()
        conn.close()

    def have_thumbnail(self, uri: str, size: int, modification_time: float) -> Optional[InCache]:
        """
        Returns download path and filename if a file with matching
        name, modification time and size has previously been downloaded
        :param uri: file name, including path
        :param size: file size in bytes
        :param modification_time: file modification time
        :return: md5 name (excluding path) and if the value indicates a
         thumbnail generation failure, else None if thumbnail not
         present
        """
        conn = sqlite3.connect(self.db)
        c = conn.cursor()
        c.execute("""SELECT md5_name, orientation_unknown, failure FROM {tn} WHERE
        uri=? AND size=? AND mtime=?""".format(
            tn=self.table_name), (uri, size, modification_time))
        row = c.fetchone()
        if row is not None:
            # convert integer to bool
            row = (row[0], bool(row[1]), bool(row[2]))
            return InCache._make(row)
        else:
            return None

    def delete_thumbnails(self, md5_names: list) -> None:
        """
        Deletes thumbnails from SQL cache
        :param md5_names: list of names, without path
        """
        def delete(names):
            conn.execute("""DELETE FROM {tn} WHERE md5_name IN ({values})""".format(
                tn=self.table_name, values=','.join('?' * len(names))), names)
        if len(md5_names) == 0:
            return

        conn = sqlite3.connect(self.db)
        # Limit to number of parameters: 999
        # See https://www.sqlite.org/limits.html
        if len(md5_names) > 999:
            name_chunks = divide_list_on_length(md5_names, 999)
            for chunk in name_chunks:
                delete(chunk)
        else:
            delete(md5_names)
        conn.commit()
        conn.close()


class FileFormatSQL:
    def __init__(self, data_dir: str=None) -> None:
        """
        :param data_dir: where the database is saved. If None, use
         default
        """
        if data_dir is None:
            data_dir = get_program_data_directory(create_if_not_exist=True)

        self.db = os.path.join(data_dir, 'file_formats.sqlite')
        self.table_name = 'formats'
        self.update_table()

    def update_table(self, reset: bool=False) -> None:
        """
        Create or update the database table
        :param reset: if True, delete the contents of the table and
         build it
        """

        conn = sqlite3.connect(self.db, detect_types=sqlite3.PARSE_DECLTYPES)

        if reset:
            conn.execute(r"""DROP TABLE IF EXISTS {tn}""".format(
                tn=self.table_name))
            conn.execute("VACUUM")

        conn.execute("""CREATE TABLE IF NOT EXISTS {tn} (
        id INTEGER PRIMARY KEY,
        extension TEXT NOT NULL,
        camera TEXT NOT NULL,
        size INTEGER NOT NULL,
        orientation_offset INTEGER,
        datetime_offset INTEGER,
        cache INTEGER NOT NULL,
        app0 INTEGER,
        orientation TEXT,
        exif_thumbnail TEXT,
        thumbnail_preview_same INTEGER,
        preview_source TEXT,
        previews TEXT
        )""".format(tn=self.table_name))

        conn.execute("""CREATE INDEX IF NOT EXISTS extension_idx ON
        {tn} (extension)""".format(tn=self.table_name))
        conn.execute("""CREATE INDEX IF NOT EXISTS camera_idx ON
        {tn} (camera)""".format(tn=self.table_name))

        conn.commit()
        conn.close()

    def add_format(self, pa: PhotoAttributes) -> None:
        conn = sqlite3.connect(self.db)
        c = conn.cursor()
        c.execute("""INSERT OR IGNORE INTO {tn} (extension, camera, size, orientation_offset,
        datetime_offset, cache, app0, orientation, exif_thumbnail, thumbnail_preview_same,
        preview_source, previews)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""".format(tn=self.table_name),
                                 (pa.ext,
                                  pa.model,
                                  pa.total,
                                  pa.minimum_exif_read_size_in_bytes_orientation,
                                  pa.minimum_exif_read_size_in_bytes_datetime,
                                  pa.bytes_cached_post_thumb,
                                  pa.has_app0,
                                  pa.orientation,
                                  pa.exif_thumbnail_details,
                                  pa.exif_thumbnail_and_preview_identical,
                                  pa.preview_source,
                                  pa.preview_size_and_types))

        conn.commit()
        conn.close()

    def get_orientation_bytes(self, extension: str) -> Optional[int]:
        conn = sqlite3.connect(self.db)
        c = conn.cursor()
        c.execute("""SELECT max(orientation_offset) FROM {tn} WHERE extension=(?)""".format(
            tn=self.table_name), (extension,))
        row = c.fetchone()
        if row is not None:
            return row[0]
        return None

    def get_datetime_bytes(self, extension: str) -> Optional[int]:
        conn = sqlite3.connect(self.db)
        c = conn.cursor()
        c.execute("""SELECT max(datetime_offset) FROM {tn} WHERE extension=(?)""".format(
            tn=self.table_name), (extension,))
        row = c.fetchone()
        if row is not None:
            return row[0]
        return None


if __name__ == '__main__':
    reset = False
    try:
        if sys.argv[1] == '--reset':
            reset = True
            print("Resetting")
    except IndexError:
        pass
    if False:
        d = DownloadedSQL()
        d.update_table(reset=True)
        c = CacheSQL()
        c.update_table(reset=True)
    f = FileFormatSQL()
    if reset:
        f.update_table(reset=True)
    else:
        print(f.get_orientation_bytes('CR2'))