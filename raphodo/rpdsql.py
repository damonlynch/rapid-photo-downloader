#!/usr/bin/env python3

# Copyright (C) 2015-2017 Damon Lynch <damonlynch@gmail.com>

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
__copyright__ = "Copyright 2015-2017, Damon Lynch"

import sqlite3
import os
import datetime
from collections import namedtuple
from typing import Optional, List, Tuple, Any, Sequence
import logging

from PyQt5.QtCore import Qt

from raphodo.storage import (get_program_data_directory, get_program_cache_directory)
from raphodo.utilities import divide_list_on_length
from raphodo.photoattributes import PhotoAttributes
from raphodo.constants import FileType, Sort, Show
from raphodo.utilities import runs

FileDownloaded = namedtuple('FileDownloaded', 'download_name, download_datetime')

InCache = namedtuple('InCache', 'md5_name, mdatatime, orientation_unknown, failure')

ThumbnailRow = namedtuple('ThumbnailRow', 'uid, scan_id, mtime, marked, file_name, extension, '
                                          'file_type, downloaded, previously_downloaded, '
                                          'job_code, proximity_col1, proximity_col2')

sqlite3.register_adapter(bool, int)
sqlite3.register_converter("BOOLEAN", lambda v: bool(int(v)))
sqlite3.register_adapter(FileType, int)
sqlite3.register_converter("FILETYPE", lambda v: FileType(int(v)))


class ThumbnailRowsSQL:
    """
    In memory database of thumbnail rows displayed in main window.
    """

    def __init__(self) -> None:
        """

        """

        self.db = ':memory:'

        self.sort_order_map = {Qt.AscendingOrder: 'ASC', Qt.DescendingOrder: 'DESC'}
        self.sort_map = {Sort.checked_state: 'marked', Sort.filename: 'file_name',
                         Sort.extension: 'extension', Sort.file_type: 'file_type',
                         Sort.device: 'device_name'}

        self.conn = sqlite3.connect(self.db, detect_types=sqlite3.PARSE_DECLTYPES)

        self.conn.execute("""CREATE TABLE devices (
            scan_id INTEGER NOT NULL,
            device_name TEXT NOT NULL,
            PRIMARY KEY (scan_id)
            )""")

        self.conn.execute("""CREATE TABLE files (
            uid BLOB PRIMARY KEY,
            scan_id INTEGER NOT NULL,
            mtime REAL NOT NULL,
            marked BOOLEAN NOT NULL,
            file_name TEXT NOT NULL,
            extension TEXT NOT NULL,
            file_type FILETYPE NOT NULL,
            downloaded BOOLEAN NOT NULL,
            previously_downloaded BOOLEAN NOT NULL,
            job_code BOOLEAN NOT NULL,
            proximity_col1 INTEGER NOT NULL,
            proximity_col2 INTEGER NOT NULL,
            FOREIGN KEY (scan_id) REFERENCES devices (scan_id)
            )""")

        self.conn.execute('CREATE INDEX IF NOT EXISTS scand_id_idx ON devices (scan_id)')

        self.conn.execute('CREATE INDEX IF NOT EXISTS marked_idx ON files (marked)')

        self.conn.execute('CREATE INDEX IF NOT EXISTS file_type_idx ON files (file_type)')

        self.conn.execute('CREATE INDEX IF NOT EXISTS downloaded_idx ON files (downloaded)')

        self.conn.execute("""CREATE INDEX IF NOT EXISTS previously_downloaded_idx ON files 
            (previously_downloaded)""")

        self.conn.execute("""CREATE INDEX IF NOT EXISTS job_code_idx ON files
            (job_code)""")

        self.conn.execute("""CREATE INDEX IF NOT EXISTS proximity_col1_idx ON files
            (proximity_col1)""")

        self.conn.execute("""CREATE INDEX IF NOT EXISTS proximity_col2_idx ON files
            (proximity_col2)""")

        self.conn.commit()

    def add_or_update_device(self, scan_id: int, device_name: str) -> None:
        query = 'INSERT OR REPLACE INTO devices (scan_id, device_name) VALUES (?,?)'
        logging.debug('%s (%s, %s)', query, scan_id, device_name)
        self.conn.execute(query, (scan_id, device_name))

        self.conn.commit()

    def get_all_devices(self) -> List[int]:
        query = 'SELECT scan_id FROM devices'
        rows = self.conn.execute(query).fetchall()
        return [row[0] for row in rows]

    def add_thumbnail_rows(self, thumbnail_rows: Sequence[ThumbnailRow]) -> None:
        """
        Add a list of rows to database of thumbnail rows
        """

        logging.debug("Adding %s rows to db", len(thumbnail_rows))
        self.conn.executemany(r"""INSERT INTO files (uid, scan_id, mtime, marked, file_name,
        extension, file_type, downloaded, previously_downloaded, job_code, proximity_col1,
        proximity_col2)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", thumbnail_rows)

        self.conn.commit()

    def _build_where(self, scan_id: Optional[int]=None,
                     show: Optional[Show]=None,
                     previously_downloaded: Optional[bool]=None,
                     downloaded: Optional[bool]=None,
                     job_code: Optional[bool]=None,
                     file_type: Optional[FileType]=None,
                     marked: Optional[bool]=None,
                     extensions: Optional[List[str]]=None,
                     proximity_col1: Optional[List[int]]=None,
                     proximity_col2: Optional[List[int]]=None,
                     exclude_scan_ids: Optional[List[int]]=None,
                     uids: Optional[List[bytes]]=None,) -> Tuple[str, List[Any]]:

        where_clauses = []
        where_values = []

        if scan_id is not None:
            where_clauses.append('scan_id=?')
            where_values.append(scan_id)

        if marked is not None:
            where_clauses.append('marked=?')
            where_values.append(marked)

        if file_type is not None:
            where_clauses.append('file_type=?')
            where_values.append(file_type)

        if show == Show.new_only:
            where_clauses.append('previously_downloaded=0')
        elif previously_downloaded is not None:
            where_clauses.append('previously_downloaded=?')
            where_values.append(previously_downloaded)

        if downloaded is not None:
            where_clauses.append('downloaded=?')
            where_values.append(downloaded)

        if job_code is not None:
            where_clauses.append('job_code=?')
            where_values.append(job_code)

        if extensions is not None:
            if len(extensions) == 1:
                where_clauses.append('extension=?')
                where_values.append(extensions[0])
            else:
                where_clauses.append('extension IN ({})'.format(','.join('?' * len(extensions))))
                where_values.extend(extensions)

        if uids is not None:
            if len(uids) == 1:
                where_clauses.append('uid=?')
                where_values.append(uids[0])
            else:
                # assume max host parameters in a single SQL statement is 999
                if len(uids) > 900:
                    uids = uids[:900]
                where_clauses.append('uid IN ({})'.format(','.join('?' * len(uids))))
                where_values.extend(uids)

        if exclude_scan_ids is not None:
            if len(exclude_scan_ids) == 1:
                where_clauses.append(('scan_id!=?'))
                where_values.append(exclude_scan_ids[0])
            else:
                where_clauses.append('scan_id NOT IN ({})'.format(','.join('?' * len(
                                                                            exclude_scan_ids))))
                where_values.extend(exclude_scan_ids)

        for p, col_name in ((proximity_col1, 'proximity_col1'), (proximity_col2, 'proximity_col2')):
            if not p:
                continue
            if len(p) == 1:
                where_clauses.append('{}=?'.format(col_name))
                where_values.append(p[0])
            else:
                p.sort()
                or_clauses = []
                for first, last in runs(p):
                    if first == last:
                        or_clauses.append('{}=?'.format(col_name))
                        where_values.append(first)
                    else:
                        or_clauses.append('({} BETWEEN ? AND ?)'.format(col_name, first,
                                                                              last))
                        where_values.extend((first, last))
                where_clauses.append('({})'.format(' OR '.join(or_clauses)))

        where = ' AND '.join(where_clauses)
        return where, where_values

    def _build_sort(self, sort_by: Sort, sort_order: Qt.SortOrder) -> str:
        if sort_by == Sort.modification_time:
            sort = 'ORDER BY mtime {}'.format(self.sort_order_map[sort_order])
        else:
            sort = 'ORDER BY {0} {1}, mtime {1}'.format(
                self.sort_map[sort_by], self.sort_order_map[sort_order]
            )
        return sort

    def get_view(self, sort_by: Sort,
                 sort_order: Qt.SortOrder,
                 show: Show,
                 proximity_col1: Optional[List[int]] = None,
                 proximity_col2: Optional[List[int]] = None) -> List[Tuple[bytes, bool]]:

        where, where_values = self._build_where(
            show=show, proximity_col1=proximity_col1, proximity_col2=proximity_col2
        )

        sort = self._build_sort(sort_by, sort_order)

        query = 'SELECT uid, marked FROM files'

        if sort_by == Sort.device:
            query = '{} NATURAL JOIN devices'.format(query)

        if where:
            query = '{} WHERE {}'.format(query, where)

        query = '{} {}'.format(query, sort)

        if where:
            logging.debug('%s %s', query, where_values)
            return self.conn.execute(query, tuple(where_values)).fetchall()
        else:
            logging.debug('%s', query)
            return self.conn.execute(query).fetchall()

    def get_first_uid_from_uid_list(self, sort_by: Sort,
                                    sort_order: Qt.SortOrder,
                                    show: Show,
                                    uids: List[bytes],
                                    proximity_col1: Optional[List[int]] = None,
                                    proximity_col2: Optional[List[int]] = None) -> Optional[bytes]:
        """
        Given a list of uids, and sort and filtering criteria, return the first
        uid that the user will have displayed -- if any are displayed.
        """

        where, where_values = self._build_where(
            show=show, proximity_col1=proximity_col1, proximity_col2=proximity_col2, uids=uids
        )

        sort = self._build_sort(sort_by, sort_order)

        query = 'SELECT uid FROM files'

        if sort_by == Sort.device:
            query = '{} NATURAL JOIN devices'.format(query)

        query = '{} WHERE {}'.format(query, where)

        query = '{} {}'.format(query, sort)

        logging.debug('%s (using %s where values)', query, len(where_values))
        row = self.conn.execute(query, tuple(where_values)).fetchone()
        if row:
            return row[0]
        return None

    def get_uids(self, scan_id: Optional[int]=None,
                 show: Optional[Show]=None,
                 previously_downloaded: Optional[bool]=None,
                 downloaded: Optional[bool]=None,
                 job_code: Optional[bool]=None,
                 file_type: Optional[FileType]=None,
                 marked: Optional[bool]=None,
                 proximity_col1: Optional[List[int]]=None,
                 proximity_col2: Optional[List[int]]=None,
                 exclude_scan_ids: Optional[List[int]]=None,
                 return_file_name=False) -> List[bytes]:

        where, where_values = self._build_where(scan_id=scan_id, show=show,
                                                previously_downloaded=previously_downloaded,
                                                downloaded=downloaded, file_type=file_type,
                                                job_code=job_code,
                                                marked=marked, proximity_col1=proximity_col1,
                                                proximity_col2=proximity_col2,
                                                exclude_scan_ids=exclude_scan_ids)

        if return_file_name:
            query = 'SELECT file_name FROM files'
        else:
            query = 'SELECT uid FROM files'

        if where:
            query = '{} WHERE {}'.format(query, where)

        if where_values:
            logging.debug('%s %s', query, where_values)
            rows = self.conn.execute(query, tuple(where_values)).fetchall()
        else:
            logging.debug('%s', query)
            rows = self.conn.execute(query).fetchall()
        return [row[0] for row in rows]

    def get_count(self, scan_id: Optional[int]=None,
                  show: Optional[Show]=None,
                  previously_downloaded: Optional[bool]=None,
                  downloaded: Optional[bool]=None,
                  job_code: Optional[bool]=None,
                  file_type: Optional[FileType]=None,
                  marked: Optional[bool] = None,
                  proximity_col1: Optional[List[int]]=None,
                  proximity_col2: Optional[List[int]]=None) -> int:

        where, where_values = self._build_where(scan_id=scan_id, show=show,
                                                previously_downloaded=previously_downloaded,
                                                downloaded=downloaded, job_code=job_code,
                                                file_type=file_type,
                                                marked=marked, proximity_col1=proximity_col1,
                                                proximity_col2=proximity_col2)

        query = 'SELECT COUNT(*) FROM files'

        if where:
            query = '{} WHERE {}'.format(query, where)

        if where_values:
            # logging.debug('%s %s', query, where_values)
            rows = self.conn.execute(query, tuple(where_values)).fetchone()
        else:
            # logging.debug('%s', query)
            rows = self.conn.execute(query).fetchone()
        return rows[0]

    def validate_uid(self, uid: bytes) -> None:
        rows = self.conn.execute('SELECT uid FROM files WHERE uid=?', (uid, )).fetchall()
        if not rows:
            raise KeyError('UID does not exist in database')

    def set_marked(self, uid: bytes, marked: bool) -> None:
        query = 'UPDATE files SET marked=? WHERE uid=?'
        logging.debug('%s (%s, %s)', query, marked, uid)
        self.conn.execute(query, (marked, uid))
        self.conn.commit()

    def set_all_marked_as_unmarked(self, scan_id: int=None) -> None:
        if scan_id is None:
            query = 'UPDATE files SET marked=0 WHERE marked=1'
            logging.debug(query)
            self.conn.execute(query)
        else:
            query = 'UPDATE files SET marked=0 WHERE marked=1 AND scan_id=?'
            logging.debug('%s (%s)', query, scan_id)
            self.conn.execute(query, (scan_id, ))
        self.conn.commit()

    def _update_marked(self, uids: List[bytes], marked: bool) -> None:
        query = 'UPDATE files SET marked=? WHERE uid IN ({})'
        logging.debug('%s (%s on %s uids)', query, marked, len(uids))
        self.conn.execute(query.format(','.join('?' * len(uids))), [marked] + uids)

    def _update_previously_downloaded(self, uids: List[bytes], previously_downloaded: bool) -> None:
        query = 'UPDATE files SET previously_downloaded=? WHERE uid IN ({})'
        logging.debug('%s (%s on %s uids)', query, previously_downloaded, len(uids))
        self.conn.execute(query.format(','.join('?' * len(uids))), [previously_downloaded] + uids)

    def _set_list_values(self, uids: List[bytes], update_value, value) -> None:
        if len(uids) == 0:
            return

        # Limit to number of parameters: 900
        # See https://www.sqlite.org/limits.html
        if len(uids) > 900:
            uid_chunks = divide_list_on_length(uids, 900)
            for chunk in uid_chunks:
                update_value(chunk, value)
        else:
            update_value(uids, value)
        self.conn.commit()

    def set_list_marked(self, uids: List[bytes], marked: bool) -> None:
        self._set_list_values(uids=uids, update_value=self._update_marked, value=marked)

    def set_list_previously_downloaded(self, uids: List[bytes],
                                       previously_downloaded: bool) -> None:
        self._set_list_values(
            uids=uids, update_value=self._update_previously_downloaded, value=previously_downloaded
        )

    def set_downloaded(self, uid: bytes, downloaded: bool) -> None:
        query = 'UPDATE files SET downloaded=? WHERE uid=?'
        logging.debug('%s (%s, <uid>)', query, downloaded)
        self.conn.execute(query, (downloaded, uid))
        self.conn.commit()

    def set_job_code_assigned(self, uids: List[bytes], job_code: bool) -> None:
        if len(uids) == 1:
            query = 'UPDATE files SET job_code=? WHERE uid=?'
            # logging.debug('%s (%s, <uid>)', query, job_code)
            self.conn.execute(query, (job_code, uids[0]))
        else:
            # Limit to number of parameters: 900
            # See https://www.sqlite.org/limits.html
            if len(uids) > 900:
                name_chunks = divide_list_on_length(uids, 900)
                for chunk in name_chunks:
                    self._mass_set_job_code_assigned(chunk, job_code)
            else:
                self._mass_set_job_code_assigned(uids, job_code)
        self.conn.commit()

    def _mass_set_job_code_assigned(self, uids: List[bytes], job_code: bool) -> None:
        query = 'UPDATE files SET job_code=? WHERE uid IN ({})'
        logging.debug('%s (%s files)', query, len(uids))
        self.conn.execute(query.format(
            ','.join('?' * len(uids))), [job_code] + uids)

    def assign_proximity_groups(self, groups: Sequence[Tuple[int, int, bytes]]) -> None:
        query = 'UPDATE files SET proximity_col1=?, proximity_col2=? WHERE uid=?'
        logging.debug('%s (%s operations)', query, len(groups))
        self.conn.executemany(query, groups)
        self.conn.commit()

    def get_uids_for_device(self, scan_id: int) -> List[int]:
        query = 'SELECT uid FROM files WHERE scan_id=?'
        logging.debug('%s (%s, )', query, scan_id)
        rows = self.conn.execute(query, (scan_id, )).fetchall()
        return [row[0] for row in rows]

    def any_files_marked(self, scan_id: Optional[int]=None) -> bool:
        if scan_id is None:
            row = self.conn.execute('SELECT uid FROM files WHERE marked=1 LIMIT 1').fetchone()
        else:
            row = self.conn.execute('SELECT uid FROM files WHERE marked=1 AND scan_id=? LIMIT 1',
                                    (scan_id, )).fetchone()
        return row is not None

    def any_files_to_download(self, scan_id: Optional[int]=None) -> bool:
        if scan_id is not None:
            row = self.conn.execute('SELECT uid FROM files WHERE downloaded=0 AND scan_id=? '
                                    'LIMIT 1', (scan_id,)).fetchone()
        else:
            row = self.conn.execute('SELECT uid FROM files WHERE downloaded=0 LIMIT 1').fetchone()
        return row is not None

    def any_files_download_completed(self) -> bool:
        row = self.conn.execute('SELECT uid FROM files WHERE downloaded=1 LIMIT 1').fetchone()
        return row is not None

    def any_files(self, scan_id: Optional[int]=None) -> bool:
        """
        Determine if there are any files associated with this scan_id, of if no scan_id
        is specified, any file at all

        :param scan_id: optional device to check
        :return: True if found, else False
        """

        if scan_id is not None:
            row = self.conn.execute('SELECT uid FROM files WHERE scan_id=? LIMIT 1',
                                    (scan_id,)).fetchone()
        else:
            row = self.conn.execute('SELECT uid FROM files LIMIT 1').fetchone()
        return row is not None

    def any_files_with_extensions(self, scan_id: int, extensions: List[str]) -> bool:
        where, where_values = self._build_where(scan_id=scan_id, extensions=extensions)
        query = 'SELECT uid FROM files'

        if where:
            query = '{} WHERE {}'.format(query, where)

        if where_values:
            logging.debug('%s %s', query, where_values)
            row = self.conn.execute(query, tuple(where_values)).fetchone()
        else:
            logging.debug('%s', query)
            row = self.conn.execute(query).fetchone()
        return row is not None

    def any_files_of_type(self, scan_id: int, file_type: FileType) -> bool:
        where, where_values = self._build_where(scan_id=scan_id, file_type=file_type)
        query = 'SELECT uid FROM files'
        if where:
            query = '{} WHERE {}'.format(query, where)

        if where_values:
            logging.debug('%s %s', query, where_values)
            row = self.conn.execute(query, tuple(where_values)).fetchone()
        else:
            logging.debug('%s', query)
            row = self.conn.execute(query).fetchone()
        return row is not None

    def get_single_file_of_type(self, file_type: FileType,
                            downloaded: Optional[bool] = None,
                            scan_id: Optional[int]=None,
                            exclude_scan_ids: Optional[List[int]] = None) -> Optional[bytes]:
        where, where_values = self._build_where(
            scan_id=scan_id, downloaded=downloaded, file_type=file_type,
            exclude_scan_ids=exclude_scan_ids
        )
        query = 'SELECT uid FROM files'

        if where:
            query = '{} WHERE {}'.format(query, where)

        if where_values:
            logging.debug('%s %s', query, where_values)
            row = self.conn.execute(query, tuple(where_values)).fetchone()
        else:
            logging.debug('%s', query)
            row = self.conn.execute(query).fetchone()

        if row is None:
            return None
        return row[0]

    def any_marked_file_no_job_code(self) -> bool:
        row = self.conn.execute(
            'SELECT uid FROM files WHERE marked=1 AND job_code=0 LIMIT 1'
        ).fetchone()
        return row is not None

    def _any_not_previously_downloaded(self, uids: List[bytes]) -> bool:
        query = 'SELECT uid FROM files WHERE uid IN ({}) AND previously_downloaded=0 LIMIT 1'
        logging.debug('%s (%s files)', query, len(uids))
        row = self.conn.execute(query.format(','.join('?' * len(uids))), uids).fetchone()
        return row is not None

    def any_not_previously_downloaded(self, uids: List[bytes]) -> bool:
        """

        :param uids: list of UIDs to check
        :return: True if any of the files associated with the UIDs have not been
         previously downloaded
        """
        if len(uids) > 900:
            uid_chunks = divide_list_on_length(uids, 900)
            for chunk in uid_chunks:
                if self._any_not_previously_downloaded(uids=uid_chunks):
                    return True
            return False
        else:
            return self._any_not_previously_downloaded(uids=uids)

    def _delete_uids(self, uids: List[bytes]) -> None:
        query = 'DELETE FROM files WHERE uid IN ({})'
        logging.debug('%s (%s files)', query, len(uids))
        self.conn.execute(query.format(','.join('?' * len(uids))), uids)

    def delete_uids(self, uids: List[bytes]) -> None:
        """
        Deletes thumbnails from SQL cache
        :param uids: list of uids to delete
        """

        if len(uids) == 0:
            return

        # Limit to number of parameters: 900
        # See https://www.sqlite.org/limits.html
        if len(uids) > 900:
            name_chunks = divide_list_on_length(uids, 900)
            for chunk in name_chunks:
                self._delete_uids(chunk)
        else:
            self._delete_uids(uids)
        self.conn.commit()

    def delete_files_by_scan_id(self, scan_id: int, downloaded: Optional[bool]=None) -> None:
        query = 'DELETE FROM files'
        where, where_values = self._build_where(scan_id=scan_id, downloaded=downloaded)
        query = '{} WHERE {}'.format(query, where)
        logging.debug('%s (%s)', query, where_values)
        self.conn.execute(query, where_values)
        self.conn.commit()

    def delete_device(self, scan_id: int) -> None:
        query = 'DELETE FROM devices WHERE scan_id=?'
        logging.debug('%s (%s, )', query, scan_id)
        self.conn.execute(query, (scan_id, ))
        self.conn.commit()


class DownloadedSQL:
    """
    Previous file download detection.

    Used to detect if a file has been downloaded before. A file is the
    same if the file name (excluding path), size and modification time
    are the same. For performance reasons, Exif information is never
    checked.
    """

    def __init__(self, data_dir: str = None) -> None:
        """
        :param data_dir: where the database is saved. If None, use
         default
        """
        if data_dir is None:
            data_dir = get_program_data_directory(create_if_not_exist=True)

        self.db = os.path.join(data_dir, 'downloaded_files.sqlite')
        self.table_name = 'downloaded'
        self.update_table()


    def update_table(self, reset: bool = False) -> None:
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

        # Use the character . to for download_name and path to indicate the user manually marked a
        # file as previously downloaded

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
        :param download_full_file_name: renamed file including path,
         or the character . that the user manually marked the file
         as previously downloaded
        """
        conn = sqlite3.connect(self.db)

        logging.debug('Adding %s to downloaded files', name)

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
    def __init__(self, location: str=None, create_table_if_not_exists: bool=True) -> None:
        """

        :param location: path on the file system where the Table exists
        :param create_table_if_not_exists:
        """
        if location is None:
            location = get_program_cache_directory(create_if_not_exist=True)
        self.db = os.path.join(location, self.db_fs_name())
        self.table_name = 'cache'
        if create_table_if_not_exists:
            self.update_table()

    def db_fs_name(self) -> str:
        return 'thumbnail_cache.sqlite'

    def update_table(self, reset: bool=False) -> None:
        """
        Create or update the database table
        :param reset: if True, delete the contents of the table and
         build it
        """
        conn = sqlite3.connect(self.db, detect_types=sqlite3.PARSE_DECLTYPES)

        if reset:
            conn.execute(r"""DROP TABLE IF EXISTS {tn}""".format(tn=self.table_name))
            conn.execute("VACUUM")

        conn.execute("""CREATE TABLE IF NOT EXISTS {tn} (
        uri TEXT NOT NULL,
        mtime REAL NOT NULL,
        mdatatime REAL,
        size INTEGER NOT NULL,
        md5_name TEXT NOT NULL,
        orientation_unknown BOOLEAN NOT NULL,
        failure BOOLEAN NOT NULL,
        PRIMARY KEY (uri, mtime, size)
        )""".format(tn=self.table_name))

        conn.execute("""CREATE INDEX IF NOT EXISTS md5_name_idx ON
        {tn} (md5_name)""".format(tn=self.table_name))

        conn.commit()
        conn.close()

    def add_thumbnail(self, uri: str, size: int,
                      mtime: float,
                      mdatatime: float,
                      md5_name: str,
                      orientation_unknown: bool,
                      failure: bool) -> None:
        """
        Add file to database of downloaded files
        :param uri: original filename of photo / video with path
        :param size: file size
        :param mtime: file modification time
        :param mdatatime: file time recorded in metadata
        :param md5_name: full file name converted to md5
        :param orientation_unknown: if True, the orientation of the
         file could not be determined, else False
        :param failure: if True, indicates the thumbnail could not be
         generated, otherwise False
        """

        conn = sqlite3.connect(self.db)

        conn.execute(
            r"""INSERT OR REPLACE INTO {tn} (uri, size, mtime, mdatatime,
            md5_name, orientation_unknown, failure) VALUES (?,?,?,?,?,?,?)""".format(
                tn=self.table_name
            ), (uri, size, mtime, mdatatime, md5_name, orientation_unknown, failure)
        )

        conn.commit()
        conn.close()

    def have_thumbnail(self, uri: str, size: int, mtime: float) -> Optional[InCache]:
        """
        Returns download path and filename if a file with matching
        name, modification time and size has previously been downloaded
        :param uri: file name, including path
        :param size: file size in bytes
        :param mtime: file modification time
        :return: md5 name (excluding path) and if the value indicates a
         thumbnail generation failure, else None if thumbnail not
         present
        """

        conn = sqlite3.connect(self.db)
        c = conn.cursor()
        c.execute("""SELECT md5_name, mdatatime, orientation_unknown, failure FROM {tn} WHERE
        uri=? AND size=? AND mtime=?""".format(tn=self.table_name), (uri, size, mtime))
        row = c.fetchone()
        if row is not None:
            return InCache._make(row)
        else:
            return None

    def _delete(self, names: List[str], conn):
        conn.execute("""DELETE FROM {tn} WHERE md5_name IN ({values})""".format(
            tn=self.table_name, values=','.join('?' * len(names))), names)

    def delete_thumbnails(self, md5_names: List[str]) -> None:
        """
        Deletes thumbnails from SQL cache
        :param md5_names: list of names, without path
        """

        if len(md5_names) == 0:
            return

        conn = sqlite3.connect(self.db)
        # Limit to number of parameters: 900
        # See https://www.sqlite.org/limits.html
        if len(md5_names) > 900:
            name_chunks = divide_list_on_length(md5_names, 900)
            for chunk in name_chunks:
                self._delete(chunk, conn)
        else:
            self._delete(md5_names, conn)
        conn.commit()
        conn.close()


    def no_thumbnails(self) -> int:
        """
        :return: how many thumbnails are in the db
        """

        conn = sqlite3.connect(self.db)
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM {tn}'.format(tn=self.table_name))
        count = c.fetchall()
        return count[0][0]

    def md5_names(self) -> List[Tuple[str]]:
        conn = sqlite3.connect(self.db)
        c = conn.cursor()
        c.execute('SELECT md5_name FROM {tn}'.format(tn=self.table_name))
        rows = c.fetchall()
        return rows

    def vacuum(self) -> None:
        conn = sqlite3.connect(self.db)
        conn.execute("VACUUM")
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
    import uuid
    d = ThumbnailRowsSQL()
    uid = uuid.uuid4().bytes
    scan_id = 0
    device_name = '1D X'
    mtime = datetime.datetime.now().timestamp()
    marked = True
    file_name = 'image.cr2'
    extension= 'cr2'
    file_type = FileType.photo
    downloaded = False
    previously_downloaded = True
    proximity_col1 = -1
    proximity_col2 = -1

    d.add_or_update_device(scan_id=scan_id, device_name=device_name)

    tr = ThumbnailRow(uid=uid, scan_id=scan_id, marked=marked, mtime=mtime, file_name=file_name,
                      file_type=file_type, extension=extension, downloaded=downloaded,
                      previously_downloaded=previously_downloaded, job_code=False,
                      proximity_col1=proximity_col1, proximity_col2=proximity_col2
                      )

    uid = uuid.uuid4().bytes
    scan_id = 1
    device_name = 'NEXUS 5X'
    mtime = datetime.datetime.now().timestamp()
    marked = True
    file_name = 'image.dng'
    extension= 'dng'
    file_type = FileType.photo
    downloaded = False
    previously_downloaded = False

    d.add_or_update_device(scan_id=scan_id, device_name=device_name)

    tr2 = ThumbnailRow(uid=uid, scan_id=scan_id, marked=marked, mtime=mtime, file_name=file_name,
                       file_type=file_type, extension=extension, downloaded=downloaded,
                       previously_downloaded=previously_downloaded, job_code=False,
                       proximity_col1=proximity_col1, proximity_col2=proximity_col2
                      )


    uid = uuid.uuid4().bytes
    mtime = datetime.datetime.now().timestamp()
    marked = False
    file_name = 'image.mp4'
    extension= 'mp4'
    file_type = FileType.video
    downloaded = False
    previously_downloaded = True

    tr3 = ThumbnailRow(uid=uid, scan_id=scan_id, marked=marked, mtime=mtime, file_name=file_name,
                       file_type=file_type, extension=extension, downloaded=downloaded,
                       previously_downloaded=previously_downloaded, job_code=False,
                       proximity_col1=proximity_col1, proximity_col2=proximity_col2
                       )

    d.add_thumbnail_rows([tr, tr2, tr3])

    cursor = d.conn.cursor()
    cursor.execute('SELECT * FROM files')
    for row in map(ThumbnailRow._make, cursor.fetchall()):
        print(row)

    d.set_marked(uid, False)
    d.set_downloaded(uid, True)

    print(d.get_view(sort_by=Sort.device, sort_order=Qt.DescendingOrder, show=Show.all))

    print(d.get_uids_for_device(0))
    print(d.get_uids_for_device(1))
    print(d.any_files_marked())

    print(d.get_uids(marked=True, return_file_name=True))
    print(d.get_uids(marked=False, return_file_name=True))
    print(d.get_uids(downloaded=False, return_file_name=True))
    print(d.get_uids(downloaded=True, return_file_name=True))
    print(d.get_uids(file_type=FileType.video, return_file_name=True))
    print("next two lines should be identical")
    print(d.get_uids(scan_id=0, file_type=FileType.photo, return_file_name=True))
    print(d.get_uids(exclude_scan_ids=[1,], file_type=FileType.photo, return_file_name=True))
    print(d.get_uids(previously_downloaded=False, return_file_name=True))
    print(d.get_count(scan_id=0))
    print(d.get_count(previously_downloaded=True))
    print(d.get_count(show=Show.new_only))
    print(d.get_count(marked=True))
    uids = d.get_uids(downloaded=False)
    print("UIDs", len(uids), "; available to download?", d.any_files_to_download())
    d.set_list_marked(uids, marked=False)
    print(d.get_count(marked=True))
    d.set_list_marked(uids, marked=True)
    print(d.get_count(marked=True))
    print(d.any_files_with_extensions(scan_id=0, extensions=['cr2', 'dng']))
    print(d.any_files_with_extensions(scan_id=0, extensions=['nef', 'dng']))
    print(d.any_files_with_extensions(scan_id=0, extensions=['nef']))
    print(d.any_files_with_extensions(scan_id=0, extensions=['cr2']))

