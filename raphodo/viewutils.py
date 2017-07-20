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

from typing import List, Dict
from collections import namedtuple

from gettext import gettext as _

from PyQt5.QtWidgets import (
    QStyleOptionFrame, QStyle, QStylePainter, QWidget, QLabel, QListWidget, QProxyStyle,
    QStyleOption, QDialogButtonBox
)
from PyQt5.QtGui import QFontMetrics, QFont, QPainter
from PyQt5.QtCore import QSize, Qt


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
        :param id_value: the ID, e.g. scan_id, uid, row_id
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


ThumbnailDataForProximity = namedtuple(
    'ThumbnailDataForProximity', 'uid, ctime, file_type, previously_downloaded'
)


class QFramedWidget(QWidget):
    """
    Draw a Frame around the widget in the style of the application.

    Use this instead of using a stylesheet to draw a widget's border.
    """

    def paintEvent(self, *opts):
        painter = QStylePainter(self)
        option = QStyleOptionFrame()
        option.initFrom(self)
        painter.drawPrimitive(QStyle.PE_Frame, option)
        super().paintEvent(*opts)


class QFramedLabel(QLabel):
    """
    Draw a Frame around the label in the style of the application.

    Use this instead of using a stylesheet to draw a label's border.
    """

    def paintEvent(self, *opts):
        painter = QStylePainter(self)
        option = QStyleOptionFrame()
        option.initFrom(self)
        painter.drawPrimitive(QStyle.PE_Frame, option)
        super().paintEvent(*opts)


class ProxyStyleNoFocusRectangle(QProxyStyle):
    """
    Remove the focus rectangle from a widget
    """

    def drawPrimitive(self, element: QStyle.PrimitiveElement,
                      option: QStyleOption, painter: QPainter,
                      widget: QWidget) -> None:

        if QStyle.PE_FrameFocusRect == element:
            pass
        else:
            super().drawPrimitive(element, option, painter, widget)


class QNarrowListWidget(QListWidget):
    """
    Create a list widget that is not by default enormously wide.

    See http://stackoverflow.com/questions/6337589/qlistwidget-adjust-size-to-content
    """

    def __init__(self, minimum_rows: int=0,
                 minimum_width: int=0,
                 no_focus_recentangle: bool=False,
                 parent=None) -> None:
        super().__init__(parent=parent)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._minimum_rows = minimum_rows
        self._minimum_width = minimum_width
        if no_focus_recentangle:
            self.setStyle(ProxyStyleNoFocusRectangle())

    @property
    def minimum_width(self) -> int:
        return self._minimum_width

    @minimum_width.setter
    def minimum_width(self, width: int) -> None:
        self._minimum_width = width
        self.updateGeometry()

    def sizeHint(self):
        s = QSize()
        if self._minimum_rows:
            s.setHeight(self.count() * self.sizeHintForRow(0) + self.frameWidth() * 2)
        else:
            s.setHeight(super().sizeHint().height())
        s.setWidth(max(self.sizeHintForColumn(0) + self.frameWidth() * 2, self._minimum_width))
        return s


def standardIconSize() -> QSize:
    size = QFontMetrics(QFont()).height() * 6
    return QSize(size, size)


def translateButtons(buttonBox: QDialogButtonBox) -> None:
    buttons = (
        (QDialogButtonBox.Ok, _('&OK')),
        (QDialogButtonBox.Close, _('&Close') ),
        (QDialogButtonBox.Cancel, _('&Cancel')),
        (QDialogButtonBox.Save, _('&Save')),
        (QDialogButtonBox.Help, _('&Help')),
        (QDialogButtonBox.RestoreDefaults, _('Restore Defaults')),
        (QDialogButtonBox.Yes, _('&Yes')),
        (QDialogButtonBox.No, _('&No')),
    )
    for role, text in buttons:
        button = buttonBox.button(role)
        if button:
            button.setText(text)