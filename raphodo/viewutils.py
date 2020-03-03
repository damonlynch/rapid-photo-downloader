# Copyright (C) 2015-2020 Damon Lynch <damonlynch@gmail.com>

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
__copyright__ = "Copyright 2015-2020, Damon Lynch"

from typing import List, Dict, Tuple, Optional
from collections import namedtuple
from distutils.version import LooseVersion

from gettext import gettext as _

from PyQt5.QtWidgets import (
    QStyleOptionFrame, QStyle, QStylePainter, QWidget, QLabel, QListWidget, QProxyStyle,
    QStyleOption, QDialogButtonBox
)
from PyQt5.QtGui import QFontMetrics, QFont, QPainter, QPixmap, QIcon
from PyQt5.QtCore import QSize, Qt, QT_VERSION_STR, QPoint

QT5_VERSION = LooseVersion(QT_VERSION_STR)


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


def qt5_screen_scale_environment_variable() -> str:
    """
    Get application scaling environment variable applicable to version of Qt 5
    See https://doc.qt.io/qt-5/highdpi.html#high-dpi-support-in-qt

    Assumes Qt >= 5.4

    :return: correct variable
    """

    if QT5_VERSION < LooseVersion('5.14.0'):
        return 'QT_AUTO_SCREEN_SCALE_FACTOR'
    else:
        return 'QT_ENABLE_HIGHDPI_SCALING'


def validateWindowSizeLimit(available: QSize, desired: QSize) -> Tuple[bool, QSize]:
    """"
    Validate the window size to ensure it fits within the available screen size.

    Important if scaling makes the saved values invalid.

    :param available: screen geometry available for use by applications
    :param desired: size as requested by Rapid Photo Downloader
    :return: bool indicating whether size was valid, and the (possibly
     corrected) size
    """

    width_valid = desired.width() <= available.width()
    height_valid = desired.height() <= available.height()
    if width_valid and height_valid:
        return True, desired
    else:
        return False, QSize(
            min(desired.width(), available.width()), min(desired.height(), available.height())
        )


def validateWindowPosition(pos: QPoint, available: QSize, size: QSize) -> Tuple[bool, QPoint]:
    """
    Validate the window position to ensure it will be displayed in the screen.

    Important if scaling makes the saved values invalid.

    :param pos: saved position
    :param available: screen geometry available for use by applications
    :param size: main window size
    :return: bool indicating whether the position was valid, and the
     (possibly corrected) position
    """

    x_valid = available.width() - size.width() >= pos.x()
    y_valid = available.height() - size.height() >= pos.y()
    if x_valid and y_valid:
        return True, pos
    else:
        return False, QPoint(
            available.width() - size.width(), available.height() - size.height()
        )


def scaledPixmap(path: str, scale: float) -> QPixmap:
    pixmap = QPixmap(path)
    if scale > 1.0:
        pixmap = pixmap.scaledToWidth(pixmap.width() * scale, Qt.SmoothTransformation)
        pixmap.setDevicePixelRatio(scale)
    return pixmap


def standard_font_size(shrink_on_odd: bool=True) -> int:
    h = QFontMetrics(QFont()).height()
    if h % 2 == 1:
        if shrink_on_odd:
            h -= 1
        else:
            h += 1
    return h


def scaledIcon(path: str, size: Optional[QSize]=None) -> QIcon:
    """
    Create a QIcon that scales well
    Uses .addFile()

    :param path:
    :param scale:
    :param size:
    :return:
    """
    i = QIcon()
    if size is None:
        s = standard_font_size()
        size = QSize(s, s)
    i.addFile(path, size)
    return i