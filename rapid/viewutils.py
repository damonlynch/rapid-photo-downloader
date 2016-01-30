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

from typing import List, Dict


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
    def __init__(self, id_value, modification_time: float) -> None:
        self.id_value = id_value
        self.modification_time = modification_time

    def __repr__(self) -> str:
        return '%r:%r' % (self.id_value, self.modification_time)

    def __eq__(self, other) -> bool:
        return (self.id_value == other.id_value and
                self.modification_time == other.modification_time)

    def __hash__(self):
        return hash((self.id_value, self.modification_time))
