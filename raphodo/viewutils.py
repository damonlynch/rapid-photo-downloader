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

from operator import attrgetter
from typing import List, Dict, Set

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QStyleOptionFrame, QStyle, QStylePainter, QWidget)

from sortedcontainers import SortedListWithKey

from raphodo.constants import Sort
from raphodo.rpdfile import RPDFile, FileType
from raphodo.devices import DeviceCollection, Device

class RowTracker:
    r"""
    Simple class to map model rows to ids and vice versa, used in
    table and list views.

    >>> r = RowTracker()
    >>> r[0] = 100
    >>> r
    {0: 100} {100: 0}
    >>> r[1] = 110
    >>> r[2] = 120
    >>> len(r)
    3
    >>> r.insert_row(1, 105)
    >>> r[1]
    105
    >>> r[2]
    110
    >>> len(r)
    4
    >>> 1 in r
    True
    >>> 3 in r
    True
    >>> 4 in r
    False
    >>> r.remove_rows(1)
    [105]
    >>> len(r)
    3
    >>> r[0]
    100
    >>> r[1]
    110
    >>> r.remove_rows(100)
    []
    >>> len(r)
    3
    >>> r.insert_row(0, 90)
    >>> r[0]
    90
    >>> r[1]
    100
    """
    def __init__(self) -> None:
        self.row_to_id = {}  # type: Dict[int, int]
        self.id_to_row = {}  # type: Dict[int, int]

    def __getitem__(self, row) -> int:
        return self.row_to_id[row]

    def __setitem__(self, row, id_value) -> None:
        self.row_to_id[row] = id_value
        self.id_to_row[id_value] = row

    def __len__(self) -> int:
        return len(self.row_to_id)

    def __contains__(self, row) -> bool:
        return row in self.row_to_id

    def __delitem__(self, row) -> None:
        id_value = self.row_to_id[row]
        del self.row_to_id[row]
        del self.id_to_row[id_value]

    def __repr__(self) -> str:
        return '%r %r' % (self.row_to_id, self.id_to_row)

    def __str__(self) -> str:
        return 'Row to id: %r\nId to row: %r' % (self.row_to_id, self.id_to_row)

    def row(self, id_value) -> int:
        """
        :param id_value: the ID, e.g. scan_id, unique_id, row_id
        :return: the row associated with the ID
        """
        return self.id_to_row[id_value]

    def insert_row(self, position: int, id_value) -> List:
        """
        Inserts row into the model at the given position, assigning
        the id_id_value.

        :param position: the position of the first row to insert
        :param id_value: the id to be associated with the new row
        """

        ids = [id_value for row, id_value in self.row_to_id.items() if row < position]
        ids_to_move = [id_value for row, id_value in self.row_to_id.items() if row >= position]
        ids.append(id_value)
        ids.extend(ids_to_move)
        self.row_to_id = dict(enumerate(ids))
        self.id_to_row =  dict(((y, x) for x, y in list(enumerate(ids))))

    def remove_rows(self, position, rows=1) -> List:
        """
        :param position: the position of the first row to remove
        :param rows: how many rows to remove
        :return: the ids of those rows which were removed
        """
        final_pos = position + rows - 1
        ids_to_keep = [id_value for row, id_value in self.row_to_id.items() if
                       row < position or row > final_pos]
        ids_to_remove = [idValue for row, idValue in self.row_to_id.items() if
                         row >= position and row <= final_pos]
        self.row_to_id = dict(enumerate(ids_to_keep))
        self.id_to_row =  dict(((y, x) for x, y in list(enumerate(ids_to_keep))))
        return ids_to_remove


class SortedListItem:
    def __init__(self, unique_id: str,
                 modification_time: float,
                 marked: bool,
                 filename: str,
                 extension: str,
                 file_type: FileType,
                 device_name: str) -> None:
        self.unique_id = unique_id
        self.modification_time = modification_time
        self.marked = marked
        self.filename = filename
        self.extension = extension
        self.file_type = file_type
        self.device_name = device_name

    def __repr__(self) -> str:
        return '%r:%r' % (self.unique_id, self.filename)

    def __eq__(self, other: 'SortedListItem') -> bool:
        return (self.unique_id == other.unique_id and
                self.modification_time == other.modification_time and
                self.marked == other.marked and
                self.filename == other.filename and
                self.extension == other.extension and
                self.file_type == other.file_type and
                self.device_name == other.device_name)

    def __hash__(self):
        return hash((self.unique_id, self.modification_time, self.marked, self.filename,
                     self.extension, self.file_type, self.device_name))


class SortedRows:

    keymap = {Sort.modification_time: attrgetter('modification_time'),
           Sort.checked_state: attrgetter('marked', 'modification_time'),
           Sort.filename: attrgetter('filename', 'modification_time'),
           Sort.extension: attrgetter('extension', 'modification_time'),
           Sort.file_type: attrgetter('file_type', 'modification_time'),
           Sort.device: attrgetter('device_name', 'modification_time'),
           }

    def __init__(self, rpd_files: Dict[str, RPDFile],
                 devices: DeviceCollection,
                 marked: Set[str],
                 key=Sort.modification_time,
                 order: Qt.SortOrder=Qt.AscendingOrder,
                 iterable=None) -> None:
        self.key = key
        self.order = order
        self.rows = SortedListWithKey(iterable, key=self.keymap[key])
        self.rpd_files = rpd_files
        self.devices = devices
        self.marked = marked

    def add(self, rpd_file: RPDFile):
        unique_id = rpd_file.unique_id
        list_item = SortedListItem(unique_id=unique_id,
                                   modification_time=self.rpd_files[unique_id].modification_time,
                                   marked=unique_id in self.marked,
                                   filename=rpd_file.name,
                                   extension=rpd_file.extension,
                                   file_type=rpd_file.file_type,
                                   device_name=self.devices[rpd_file.scan_id].display_name)
        self.rows.add(list_item)
        return self.rows.index(list_item)

    def row_from_id(self, unique_id) -> int:
        rpd_file = self.rpd_files[unique_id]
        list_item = SortedListItem(unique_id=unique_id,
                                   modification_time=self.rpd_files[unique_id].modification_time,
                                   marked=unique_id in self.marked,
                                   filename=rpd_file.name,
                                   extension=rpd_file.extension,
                                   file_type=rpd_file.file_type,
                                   device_name=self.devices[rpd_file.scan_id].display_name)
        return self.rows.index(list_item)

    def set_key(self, key: Sort) -> None:
        if key != self.key:
            rows = SortedListWithKey(self.rows, key=self.keymap[key])
            self.rows = rows
            self.key = key

    def set_order(self, order: Qt.SortOrder) -> None:
        self.order = order

    def unique_id(self, row) -> str:
        return self[row].unique_id

    def __getitem__(self, row: int) -> SortedListItem:
        # if self.order == Qt.DescendingOrder:
        #     row = -1 - row
        return self.rows.__getitem__(row)

    def __len__(self):
        return len(self.rows)

    def __delitem__(self, idx):
        self.rows.__delitem__(idx)

    def rpd_file(self, row: int) -> RPDFile:
        return self.rpd_files[self.rows[row]]


class QFramedWidget(QWidget):
    """
    Draw a Frame around the widget in the style of the application.
    """
    def paintEvent(self, *opts):
        painter = QStylePainter(self)
        option = QStyleOptionFrame()
        option.initFrom(self)
        painter.drawPrimitive(QStyle.PE_Frame, option)
        super().paintEvent(*opts)