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
    >>> r.removeRows(1)
    [110]
    >>> len(r)
    2
    >>> r[0]
    100
    >>> r[1]
    120
    >>> r.removeRows(100)
    []
    >>> len(r)
    2
    """
    def __init__(self):
        self.rowToId = {} # type: Dict[int, int]
        self.idToRow = {} # type: Dict[int, int]

    def __getitem__(self, row):
        return self.rowToId[row]

    def __setitem__(self, row, idValue):
        self.rowToId[row] = idValue
        self.idToRow[idValue] = row

    def __len__(self):
        return len(self.rowToId)

    def __contains__(self, row):
        return row in self.rowToId

    def __delitem__(self, row):
        id_value = self.rowToId[row]
        del self.rowToId[row]
        del self.idToRow[id_value]

    def __repr__(self):
        return '%r %r' % (self.rowToId, self.idToRow)

    def row(self, idValue):
        """
        :param idValue: the ID, e.g. scan_id, unique_id
        :return: the row associated with the ID
        """
        return self.idToRow[idValue]

    def removeRows(self, position, rows=1):
        """
        :param position: the position of the first row to remove
        :param rows: how many rows to remove
        :return: the ids of those rows which were removed
        """
        finalPos = position + rows - 1
        idsToKeep = [idValue for row, idValue in self.rowToId.items() if
                    row < position or row > finalPos]
        idsToRemove = [idValue for row, idValue in self.rowToId.items() if
                       row >= position and row <= finalPos]
        self.rowToId = dict(enumerate(idsToKeep))
        self.idToRow =  dict(((y,x) for x, y in list(enumerate(idsToKeep))))
        return idsToRemove
