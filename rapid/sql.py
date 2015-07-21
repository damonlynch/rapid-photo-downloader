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

import sqlite3
import os
import datetime
from collections import namedtuple
from storage import get_program_data_directory

FileDownloaded = namedtuple('FileDownloaded', 'download_name, '
                                              'download_datetime')

class DownloadedSQL:
    """
    Used to detect if a file has been downloaded before. A file is the
    same if the file name (excluding path), size and modification time
    are the same. For performance reasons, Exif information is never
    checked.
    """
    def __init__(self, data_dir: str=None):
        """
        :param data_dir: where the database is saved. If None, use
         default
        """
        if data_dir is None:
            data_dir = get_program_data_directory(create_if_not_exist=True)

        self.db = os.path.join(data_dir, 'downloaded_files.sqlite')
        self.table_name = 'downloaded'
        self.update_table()

    def update_table(self, reset: bool=False):
        """
        Create or update the database table
        :param reset: if True, delete the contents of the table and
         build it
        """

        conn = sqlite3.connect(self.db,
                   detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
        c = conn.cursor()

        if reset:
            c.execute(r"""DROP TABLE IF EXISTS {tn}""".format(
                tn=self.table_name))

        c.execute("""CREATE TABLE IF NOT EXISTS {tn} (
        file_name TEXT NOT NULL,
        mtime REAL NOT NULL,
        size INTEGER NOT NULL,
        download_name TEXT NOT NULL,
        download_datetime timestamp,
        PRIMARY KEY (file_name, mtime, size)
        )""".format(tn=self.table_name))

        c.execute("""CREATE INDEX IF NOT EXISTS download_datetime_idx ON
        {tn} (download_name)""".format(tn=self.table_name))

        conn.commit()
        conn.close()

    def add_downloaded_file(self, name: str, size: int, modification_time:
                            float, download_full_file_name: str):
        """
        Add file to database of downloaded files
        :param name: original filename of photo / video, without path
        :param size: file size
        :param modification_time: file modification time
        :param download_full_file_name: renamed file including path
        """
        conn = sqlite3.connect(self.db)
        c = conn.cursor()

        c.execute(r"""INSERT OR REPLACE INTO {tn} (file_name, size, mtime,
        download_name, download_datetime) VALUES (?,?,?,?,?)""".format(
            tn=self.table_name), (name, size, modification_time,
            download_full_file_name, datetime.datetime.now()))

        conn.commit()
        conn.close()

    def file_downloaded(self, name: str, size: int, modification_time:
                            float) -> FileDownloaded:
        """
        Returns download path and filename if a file with matching
        name, modification time and size has previously been downloaded
        :param name: file name, not including path
        :param size: file size in bytes
        :param modification_time: file modification time
        :return: download name (including path) and when it was
         downloaded, else None if never downloaded
        """
        conn = sqlite3.connect(self.db)
        c = conn.cursor()
        c.execute("""SELECT download_name, download_datetime FROM {tn} WHERE
        file_name=? AND size=? AND mtime=?""".format(
            tn=self.table_name), (name, size, modification_time))
        row = c.fetchone()
        if row is not None:
            return FileDownloaded._make(row)
        else:
            return None


if __name__ == '__main__':
    d = DownloadedSQL()
    d.update_table(reset=True)