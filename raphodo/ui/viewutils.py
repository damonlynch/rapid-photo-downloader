# Copyright (C) 2015-2022 Damon Lynch <damonlynch@gmail.com>

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

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2015-2022, Damon Lynch"

import functools
import logging
from typing import List, Dict, Tuple, Optional, Union
from collections import namedtuple
from pkg_resources import parse_version
import sys

from PyQt5.QtWidgets import (
    QStyle,
    QStylePainter,
    QWidget,
    QListWidget,
    QProxyStyle,
    QStyleOption,
    QDialogButtonBox,
    QMessageBox,
    QItemDelegate,
    QStyleOptionButton,
    QApplication,
    QStyleOptionViewItem,
    QScrollArea,
    QFrame,
    QListView,
    QVBoxLayout,
    QScrollBar,
    QSplitter,
    QSplitterHandle,
    QStyleOptionSlider,
    QLabel,
)
from PyQt5.QtGui import (
    QFontMetrics,
    QFont,
    QPainter,
    QPixmap,
    QIcon,
    QGuiApplication,
    QPalette,
    QColor,
    QPaintEvent,
    QPen,
    QMouseEvent,
    QResizeEvent,
    QShowEvent,
)
from PyQt5.QtCore import (
    QSize,
    Qt,
    QT_VERSION_STR,
    QPoint,
    QEvent,
    QModelIndex,
    QRect,
    QAbstractItemModel,
    pyqtSlot,
    pyqtSignal,
    QBuffer,
    QIODevice,
)

QT5_VERSION = parse_version(QT_VERSION_STR)

from raphodo.constants import ScalingDetected, HeaderBackgroundName
import raphodo.xsettings as xsettings


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
        return "%r %r" % (self.row_to_id, self.id_to_row)

    def __str__(self) -> str:
        return "Row to id: %r\nId to row: %r" % (self.row_to_id, self.id_to_row)

    def row(self, id_value) -> int:
        """
        :param id_value: the ID, e.g. scan_id, uid, row_id
        :return: the row associated with the ID
        """
        return self.id_to_row[id_value]

    def insert_row(self, position: int, id_value) -> None:
        """
        Inserts row into the model at the given position, assigning
        the id_id_value.

        :param position: the position of the first row to insert
        :param id_value: the id to be associated with the new row
        """

        ids = [id_value for row, id_value in self.row_to_id.items() if row < position]
        ids_to_move = [
            id_value for row, id_value in self.row_to_id.items() if row >= position
        ]
        ids.append(id_value)
        ids.extend(ids_to_move)
        self.row_to_id = dict(enumerate(ids))
        self.id_to_row = dict(((y, x) for x, y in list(enumerate(ids))))

    def remove_rows(self, position: int, rows=1) -> List[int]:
        """
        :param position: the position of the first row to remove
        :param rows: how many rows to remove
        :return: the ids of those rows which were removed
        """
        final_pos = position + rows - 1
        ids_to_keep = [
            id_value
            for row, id_value in self.row_to_id.items()
            if row < position or row > final_pos
        ]
        ids_to_remove = [
            idValue
            for row, idValue in self.row_to_id.items()
            if row >= position and row <= final_pos
        ]
        self.row_to_id = dict(enumerate(ids_to_keep))
        self.id_to_row = dict(((y, x) for x, y in list(enumerate(ids_to_keep))))
        return ids_to_remove


ThumbnailDataForProximity = namedtuple(
    "ThumbnailDataForProximity", "uid, ctime, file_type, previously_downloaded"
)


def paletteMidPen() -> QPen:
    if sys.platform == "win32":
        return QPen(QApplication.palette().mid().color().lighter(120))
    else:
        return QPen(QApplication.palette().mid().color())


class MainWindowSplitter(QSplitter):

    heightChanged = pyqtSignal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent=parent)
        self.previous_height = 0
        self.setObjectName("mainWindowHorizontalSplitter")
        self.setOrientation(Qt.Horizontal)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        height = self.height()
        if height != self.previous_height:
            self.heightChanged.emit(height)
            self.previous_height = height


class SourceSplitterHandle(QSplitterHandle):
    """
    Splitter handle for Download Source Splitter
    """

    mousePress = pyqtSignal()
    mouseReleased = pyqtSignal()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        super().mousePressEvent(event)
        self.mousePress.emit()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        self.mouseReleased.emit()


class SourceSplitter(QSplitter):
    """
    Download Source Splitter

    Emits a signal when handle mouse pressed, and another when released
    """

    def createHandle(self) -> QSplitterHandle:
        return SourceSplitterHandle(Qt.Vertical, self)


class ScrollBarEmitsVisible(QScrollBar):
    """
    Emits a signal when it appears or disappears. Shares same code
    with FramedScrollBar, which is unavoidable due to rules around
    PyQt multiple inheritance.
    """

    scrollBarVisible = pyqtSignal(bool)

    def __init__(self, orientation, parent: Optional[QWidget] = None) -> None:
        super().__init__(orientation=orientation, parent=parent)
        self.rangeChanged.connect(self.scrollBarChange)
        self.visible_state = None

    @pyqtSlot(int, int)
    def scrollBarChange(self, min: int, max: int) -> None:
        visible = max != 0
        if visible != self.visible_state:
            self.visible_state = visible
            self.scrollBarVisible.emit(visible)


class FramedScrollBar(QScrollBar):
    """
    QScrollBar for use with Fusion widgets which expect to be framed
    e.g. QScrollArea, but are not, typically because their children already
    have a frame.
    """

    scrollBarVisible = pyqtSignal(bool)

    def __init__(self, orientation, name: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(orientation=orientation, parent=parent)
        self.frame_width = self.style().pixelMetric(QStyle.PM_DefaultFrameWidth)
        orientation = "Vertical" if orientation == Qt.Vertical else "Horizontal"
        self.setObjectName(f"{name}{orientation}ScrollBar")
        self.midPen = paletteMidPen()

        self.rangeChanged.connect(self.scrollBarChange)
        self.visible_state = None

    @pyqtSlot(int, int)
    def scrollBarChange(self, min: int, max: int) -> None:
        visible = max != 0
        if not visible and visible != self.visible_state:
            self.visible_state = visible
            self.scrollBarVisible.emit(visible)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self.visible_state:
            self.visible_state = self.maximum() != 0
            self.scrollBarVisible.emit(self.visible_state)

    def sizeHint(self) -> QSize:
        """
        Increase the size of the scrollbar to account for the width of the frames
        """

        size = super().sizeHint()
        if self.orientation() == Qt.Vertical:
            return QSize(
                size.width() + self.frame_width, size.height() + self.frame_width * 2
            )
        else:
            return QSize(
                size.width() + self.frame_width * 2, size.height() + self.frame_width
            )

    def paintEvent(self, event: QPaintEvent) -> None:
        """
        Render the scrollbars using Qt's draw control, and render the frame elements
        dependent on whether the partner horizontal / vertical scrollbar is also visible
        """

        painter = QStylePainter(self)
        if self.orientation() == Qt.Vertical:
            painter.translate(0.0, self.frame_width)
        else:
            painter.translate(self.frame_width, 0.0)

        option = QStyleOptionSlider()
        option.initFrom(self)
        option.maximum = self.maximum()
        option.minimum = self.minimum()
        option.pageStep = self.pageStep()
        option.singleStep = self.singleStep()
        option.sliderPosition = self.sliderPosition()
        option.orientation = self.orientation()
        if self.orientation() == Qt.Horizontal:
            option.state |= QStyle.State_Horizontal

        rect = self.renderRect()

        option.rect = rect
        option.palette = self.palette()
        option.subControls = (
            QStyle.SC_ScrollBarAddLine
            | QStyle.SC_ScrollBarSubLine
            | QStyle.SC_ScrollBarAddPage
            | QStyle.SC_ScrollBarSubPage
            | QStyle.SC_ScrollBarFirst
            | QStyle.SC_ScrollBarLast
        )

        painter.fillRect(
            option.rect, QApplication.palette().window().color().darker(102)
        )
        self.style().drawComplexControl(QStyle.CC_ScrollBar, option, painter)

        # Highlight the handle (slider) on mouse over, otherwise render it as normal
        option.subControls = QStyle.SC_ScrollBarSlider
        if option.state & QStyle.State_MouseOver == QStyle.State_MouseOver:
            palette = self.palette()
            if sys.platform == "win32":
                color = self.palette().base().color()
            else:
                color = self.palette().button().color().lighter(102)
            palette.setColor(QPalette.Button, color)
            option.palette = palette
        self.style().drawComplexControl(QStyle.CC_ScrollBar, option, painter)

        # Render the borders
        painter.resetTransform()
        painter.setPen(self.midPen)
        self.renderEdges(painter)

    def renderRect(self) -> QRect:
        rect = QRect(self.rect())
        if self.orientation() == Qt.Vertical:
            rect.adjust(self.frame_width, self.frame_width * 2, 0, 0)
        else:
            rect.adjust(self.frame_width * 2, self.frame_width, 0, 0)
        return rect

    def renderEdges(self, painter: QStylePainter) -> None:
        rect = self.rect()
        if self.orientation() == Qt.Vertical:
            painter.drawLine(rect.topLeft(), rect.topRight())
            painter.drawLine(rect.topRight(), rect.bottomRight())
            painter.drawLine(rect.topLeft(), rect.bottomLeft())
            if not self.parent().parent().horizontalScrollBar().isVisible():
                painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        else:
            painter.drawLine(rect.topLeft(), rect.bottomLeft())
            painter.drawLine(rect.bottomLeft(), rect.bottomRight())
            painter.drawLine(rect.topLeft(), rect.topRight())
            if not self.parent().parent().verticalScrollBar().isVisible():
                painter.drawLine(rect.bottomRight(), rect.topRight())


class TopFramedVerticalScrollBar(FramedScrollBar):
    def __init__(self, name: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(orientation=Qt.Vertical, name=name, parent=parent)

    def sizeHint(self) -> QSize:
        """
        Increase the size of the scrollbar to account for the extra height
        """

        size = super().sizeHint()
        return QSize(size.width(), size.height() + self.frame_width)

    def renderRect(self) -> QRect:
        rect = QRect(self.rect())
        rect.adjust(0, self.frame_width, 0, 0)
        return rect

    def renderEdges(self, painter: QStylePainter) -> None:
        rect = self.rect()
        painter.drawLine(rect.topLeft(), rect.topRight())
        painter.drawLine(rect.topLeft(), rect.bottomLeft())


class ScrollAreaNoFrame(QScrollArea):
    """
    Scroll Area with no frame and scrollbars that frame themselves
    """

    horizontalScrollBarVisible = pyqtSignal(bool)
    verticalScrollBarVisible = pyqtSignal(bool)

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent=parent)
        self.setFrameShape(QFrame.NoFrame)
        sbv = FramedScrollBar(orientation=Qt.Vertical, name=name)
        sbh = FramedScrollBar(orientation=Qt.Horizontal, name=name)
        self.setVerticalScrollBar(sbv)
        self.setHorizontalScrollBar(sbh)
        sbv.scrollBarVisible.connect(self.verticalScrollBarVisible)
        sbh.scrollBarVisible.connect(self.horizontalScrollBarVisible)


class FlexiFrameObject:
    def __init__(self, **kwds):
        super().__init__(**kwds)
        self.frame_width = QApplication.style().pixelMetric(QStyle.PM_DefaultFrameWidth)
        self.container_vertical_scrollbar_visible = None
        self.container_horizontal_scrollbar_visible = None
        self.midPen = paletteMidPen()
        self.quirk_mode = False
        self.quirkPen = QPen(device_name_highlight_color())

    def paintBorders(self, painter: QPainter, rect: QRect) -> None:
        if self.quirk_mode:
            painter.setPen(self.quirkPen)
            painter.drawLine(rect.topLeft(), rect.topRight())
        painter.setPen(self.midPen)
        painter.drawLine(rect.topLeft(), rect.bottomLeft())
        if (
            self.container_horizontal_scrollbar_visible is None
            or not self.container_horizontal_scrollbar_visible
        ):
            painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        if (
            self.container_vertical_scrollbar_visible is None
            or not self.container_vertical_scrollbar_visible
        ):
            painter.drawLine(rect.topRight(), rect.bottomRight())


class FlexiFrame(QWidget, FlexiFrameObject):
    def __init__(
        self, render_top_edge: bool = False, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent=parent)
        self.render_top_edge = render_top_edge
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), palette.color(palette.Base))
        self.setPalette(palette)
        layout = QVBoxLayout()
        self.setLayout(layout)

    @pyqtSlot(bool)
    def containerVerticalScrollBar(self, visible: bool) -> None:
        self.container_vertical_scrollbar_visible = visible

    @pyqtSlot(bool)
    def containerHorizontalScrollBar(self, visible: bool) -> None:
        self.container_horizontal_scrollbar_visible = visible

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        rect = self.rect()
        painter = QPainter(self)
        self.paintBorders(painter=painter, rect=rect)
        if self.render_top_edge:
            painter.drawLine(rect.topLeft(), rect.topRight())


class TightFlexiFrame(FlexiFrame):
    def __init__(
        self, render_top_edge: bool = False, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(render_top_edge=render_top_edge, parent=parent)
        top_margin = self.frame_width if render_top_edge else 0
        self.layout().setContentsMargins(
            self.frame_width, top_margin, self.frame_width, self.frame_width
        )
        if not render_top_edge:
            self.quirk_mode = True

    @pyqtSlot(bool)
    def containerVerticalScrollBar(self, visible: bool) -> None:
        width = 0 if visible else self.frame_width
        margins = self.layout().contentsMargins()
        margins.setRight(width)
        self.layout().setContentsMargins(margins)
        self.container_vertical_scrollbar_visible = visible

    @pyqtSlot(bool)
    def containerHorizontalScrollBar(self, visible: bool) -> None:
        height = 0 if visible else self.frame_width
        margins = self.layout().contentsMargins()
        margins.setBottom(height)
        self.layout().setContentsMargins(margins)
        self.container_horizontal_scrollbar_visible = visible


class ListViewFlexiFrame(QListView, FlexiFrameObject):
    def __init__(
        self, frame_enabled: Optional[bool] = True, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.frame_enabled = frame_enabled

    @pyqtSlot(bool)
    def containerVerticalScrollBar(self, visible: bool) -> None:
        self.container_vertical_scrollbar_visible = visible

    @pyqtSlot(bool)
    def containerHorizontalScrollBar(self, visible: bool) -> None:
        self.container_horizontal_scrollbar_visible = visible

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        if self.frame_enabled:
            painter = QPainter(self.viewport())
            self.paintBorders(painter=painter, rect=self.viewport().rect())


class BlankWidget(FlexiFrame):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        palette = QPalette()
        palette.setColor(QPalette.Window, palette.color(palette.Base))
        self.setAutoFillBackground(True)
        self.setPalette(palette)


class StyledLinkLabel(QLabel):
    """
    Setting a link style this way works. It does not work with regular style sheets.
    """

    def setLink(self, url: str, text: str) -> None:
        super().setText(
            f"""
            <a 
            style="text-decoration:none; font-weight: bold; color: palette(highlight);" 
            href="{url}"
            >
            {text}
            </a>
            """
        )


class ProxyStyleNoFocusRectangle(QProxyStyle):
    """
    Remove the focus rectangle from a widget
    """

    def drawPrimitive(
        self,
        element: QStyle.PrimitiveElement,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget,
    ) -> None:

        if QStyle.PE_FrameFocusRect == element:
            pass
        else:
            super().drawPrimitive(element, option, painter, widget)


@functools.lru_cache(maxsize=None)
def is_dark_mode() -> bool:
    text_hsv_value = QApplication.palette().color(QPalette.WindowText).value()
    bg_hsv_value = QApplication.palette().color(QPalette.Background).value()
    return text_hsv_value > bg_hsv_value


class QNarrowListWidget(QListWidget):
    """
    Create a list widget that is not by default enormously wide.

    See http://stackoverflow.com/questions/6337589/qlistwidget-adjust-size-to-content
    """

    def __init__(
        self,
        minimum_rows: int = 0,
        minimum_width: int = 0,
        no_focus_recentangle: bool = False,
        parent=None,
    ) -> None:
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
        s.setWidth(
            max(self.sizeHintForColumn(0) + self.frameWidth() * 2, self._minimum_width)
        )
        return s


def standardIconSize() -> QSize:
    size = QFontMetrics(QFont()).height() * 6
    return QSize(size, size)


# If set to True, do translation of QMessageBox and QDialogButtonBox buttons
# Set at program startup
Do_Message_And_Dialog_Box_Button_Translation = True


def translateDialogBoxButtons(buttonBox: QDialogButtonBox) -> None:
    if not Do_Message_And_Dialog_Box_Button_Translation:
        return

    buttons = (
        (QDialogButtonBox.Ok, _("&OK")),
        (QDialogButtonBox.Close, _("&Close")),
        (QDialogButtonBox.Cancel, _("&Cancel")),
        (QDialogButtonBox.Save, _("&Save")),
        (QDialogButtonBox.Help, _("&Help")),
        (QDialogButtonBox.RestoreDefaults, _("Restore Defaults")),
        (QDialogButtonBox.Yes, _("&Yes")),
        (QDialogButtonBox.No, _("&No")),
    )
    for role, text in buttons:
        button = buttonBox.button(role)
        if button:
            button.setText(text)


def translateMessageBoxButtons(messageBox: QMessageBox) -> None:
    if not Do_Message_And_Dialog_Box_Button_Translation:
        return

    buttons = (
        (QMessageBox.Ok, _("&OK")),
        (QMessageBox.Close, _("&Close")),
        (QMessageBox.Cancel, _("&Cancel")),
        (QMessageBox.Save, _("&Save")),
        (QMessageBox.Yes, _("&Yes")),
        (QMessageBox.No, _("&No")),
    )
    for role, text in buttons:
        button = messageBox.button(role)
        if button:
            button.setText(text)


def standardMessageBox(
    message: str,
    rich_text: bool,
    standardButtons: QMessageBox.StandardButton,
    defaultButton: Optional[QMessageBox.StandardButton] = None,
    parent=None,
    title: Optional[str] = None,
    icon: Optional[QIcon] = None,
    iconPixmap: Optional[QPixmap] = None,
    iconType: Optional[QMessageBox.Icon] = None,
) -> QMessageBox:
    """
    Create a QMessageBox to be displayed to the user.

    :param message: the text to display
    :param rich_text: whether it text to display is in HTML format
    :param standardButtons: or'ed buttons or button to display (Qt style)
    :param defaultButton: if specified, set this button to be the default
    :param parent: parent widget,
    :param title: optional title for message box, else defaults to
     localized 'Rapid Photo Downloader'
    :param iconType: type of QMessageBox.Icon to display. If standardButtons
     are equal to QMessageBox.Yes | QMessageBox.No, then QMessageBox.Question
     will be assigned to iconType
    :param iconPixmap: icon to display, in QPixmap format. Used only if
    iconType is None
    :param icon: icon to display, in QIcon format. Used only if iconType is
    None
    :return: the message box
    """

    msgBox = QMessageBox(parent)
    if title is None:
        title = _("Rapid Photo Downloader")
    if rich_text:
        msgBox.setTextFormat(Qt.RichText)
    msgBox.setWindowTitle(title)
    msgBox.setText(message)

    msgBox.setStandardButtons(standardButtons)
    if defaultButton:
        msgBox.setDefaultButton(defaultButton)
    translateMessageBoxButtons(messageBox=msgBox)

    if iconType is None:
        if standardButtons == QMessageBox.Yes | QMessageBox.No:
            iconType = QMessageBox.Question

    if iconType:
        msgBox.setIcon(iconType)
    else:
        if iconPixmap is None:
            if icon:
                iconPixmap = icon.pixmap(standardIconSize())
            else:
                iconPixmap = QIcon(":/rapid-photo-downloader.svg").pixmap(
                    standardIconSize()
                )
        msgBox.setIconPixmap(iconPixmap)

    return msgBox


def qt5_screen_scale_environment_variable() -> str:
    """
    Get application scaling environment variable applicable to version of Qt 5
    See https://doc.qt.io/qt-5/highdpi.html#high-dpi-support-in-qt

    Assumes Qt >= 5.4

    :return: correct variable
    """

    if QT5_VERSION < parse_version("5.14.0"):
        return "QT_AUTO_SCREEN_SCALE_FACTOR"
    else:
        return "QT_ENABLE_HIGHDPI_SCALING"


def validateWindowSizeLimit(available: QSize, desired: QSize) -> Tuple[bool, QSize]:
    """
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
            min(desired.width(), available.width()),
            min(desired.height(), available.height()),
        )


def validateWindowPosition(
    pos: QPoint, available: QSize, size: QSize
) -> Tuple[bool, QPoint]:
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


def standard_font_size(shrink_on_odd: bool = True) -> int:
    h = QFontMetrics(QFont()).height()
    if h % 2 == 1:
        if shrink_on_odd:
            h -= 1
        else:
            h += 1
    return h


def scaledIcon(path: str, size: Optional[QSize] = None) -> QIcon:
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


def coloredPixmap(
    color: Union[str, QColor],
    path: Optional[str] = None,
    pixmap: Optional[QPixmap] = None,
    size: Optional[QSize] = None,
) -> QPixmap:
    if isinstance(color, str):
        color = QColor(color)
    if path is not None:
        if size:
            pixmap = QIcon(path).pixmap(size)
        else:
            pixmap = QPixmap(path)
    else:
        assert pixmap is not None

    painter = QPainter(pixmap)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), color)
    painter.end()
    return pixmap


def darkModePixmap(
    path: Optional[str] = None,
    pixmap: Optional[QPixmap] = None,
    size: Optional[QSize] = None,
    soften_regular_mode_color: Optional[bool] = False,
) -> QPixmap:
    if is_dark_mode():
        color = QApplication.palette().windowText().color()
        return coloredPixmap(path=path, pixmap=pixmap, color=color, size=size)
    elif soften_regular_mode_color:
        color = QColor(HeaderBackgroundName)
        return coloredPixmap(path=path, pixmap=pixmap, color=color, size=size)
    else:
        if pixmap:
            return pixmap
        if size:
            return QIcon(path).pixmap(size)
        else:
            return QPixmap(path)


def darkModeIcon(
    icon: Optional[QIcon] = None,
    path: Optional[str] = None,
    size: Optional[QSize] = None,
    soften_regular_mode_color: Optional[bool] = False,
) -> QIcon:
    if is_dark_mode() or soften_regular_mode_color:
        if is_dark_mode():
            color = QApplication.palette().windowText().color()
        else:
            color = QColor(HeaderBackgroundName)
        if icon:
            pixmap = icon.pixmap(size)
            pixmap = coloredPixmap(pixmap=pixmap, color=color)
        else:
            assert str
            pixmap = darkModePixmap(path=path, size=size)
        icon = QIcon()
        icon.addPixmap(pixmap)
        return icon
    else:
        if icon:
            return icon
        else:
            return QIcon(path)


def menuHoverColor() -> QColor:
    if is_dark_mode():
        return QGuiApplication.palette().color(QPalette.Highlight)
    else:
        return QGuiApplication.palette().color(QPalette.Background).darker(110)


def screen_scaled_xsettings() -> bool:
    """
    Use xsettings to detect if screen scaling is on.

    No error checking.

    :return: True if detected, False otherwise
    """

    x11 = xsettings.get_xsettings()
    return x11.get(b"Gdk/WindowScalingFactor", 1) > 1


def any_screen_scaled_qt() -> bool:
    """
    Detect if any of the screens on this system have scaling enabled.

    Call before QApplication is initialized. Uses temporary QGuiApplication.

    :return: True if found, else False
    """

    app = QGuiApplication(sys.argv)
    ratio = app.devicePixelRatio()
    del app

    return ratio > 1.0


def any_screen_scaled() -> Tuple[ScalingDetected, bool]:
    """
    Detect if any of the screens on this system have scaling enabled.

    Uses Qt and xsettings to do detection.

    :return: True if found, else False
    """

    qt_detected_scaling = any_screen_scaled_qt()
    try:
        xsettings_detected_scaling = screen_scaled_xsettings()
        xsettings_running = True
    except:
        xsettings_detected_scaling = False
        xsettings_running = False

    if qt_detected_scaling:
        if xsettings_detected_scaling:
            return ScalingDetected.Qt_and_Xsetting, xsettings_running
        return ScalingDetected.Qt, xsettings_running
    if xsettings_detected_scaling:
        return ScalingDetected.Xsetting, xsettings_running
    return ScalingDetected.undetected, xsettings_running


class CheckBoxDelegate(QItemDelegate):
    """
    A delegate that places a fully functioning centered QCheckBox cell in the column
    to which it's applied.
    """

    def __init__(self, parent):
        QItemDelegate.__init__(self, parent)

        checkboxRect = QRect(
            QApplication.style().subElementRect(
                QStyle.SE_CheckBoxIndicator, QStyleOptionButton(), None
            )
        )
        self.checkboxHalfWidth = int(checkboxRect.width() / 2)

    def createEditor(
        self, parent, option: QStyleOptionViewItem, indexindex: QModelIndex
    ) -> Optional[QWidget]:
        """
        Important, otherwise an editor is created if the user clicks in this cell.
        """

        return None

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        """
        Paint a checkbox without a label
        """

        checked = index.data(Qt.CheckStateRole) == Qt.Checked
        enabled = int(index.flags() & Qt.ItemIsEditable) > 0

        if not checked and not enabled:
            return

        painter.save()

        checkboxStyleOption = QStyleOptionButton()
        if checked:
            checkboxStyleOption.state |= QStyle.State_On
        else:
            checkboxStyleOption.state |= QStyle.State_Off

        if enabled:
            checkboxStyleOption.state |= QStyle.State_Enabled
            checkboxStyleOption.state &= ~QStyle.State_ReadOnly
        else:
            checkboxStyleOption.state &= ~QStyle.State_Enabled
            checkboxStyleOption.state |= QStyle.State_ReadOnly
            color = checkboxStyleOption.palette.color(QPalette.Window).darker(130)
            checkboxStyleOption.palette.setColor(QPalette.Text, color)

        checkboxStyleOption.rect = option.rect
        checkboxStyleOption.rect.setX(
            option.rect.x() + round(option.rect.width() / 2) - self.checkboxHalfWidth
        )

        QApplication.style().drawControl(
            QStyle.CE_CheckBox, checkboxStyleOption, painter
        )
        painter.restore()

    def editorEvent(
        self,
        event: QEvent,
        model: QAbstractItemModel,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> bool:
        if not int(index.flags() & Qt.ItemIsEditable) > 0:
            return False

        if (
            event.type() == QEvent.MouseButtonRelease
            and event.button() == Qt.LeftButton
        ):
            self.setModelData(None, model, index)
            return True
        elif event.type() == QEvent.KeyPress:
            if event.key() != Qt.Key_Space and event.key() != Qt.Key_Select:
                return False
            self.setModelData(None, model, index)
            return True
        return False

    def setModelData(
        self, editor: QWidget, model: QAbstractItemModel, index: QModelIndex
    ) -> None:
        """
        The user wants the opposite state
        """
        model.setData(
            index,
            Qt.Unchecked
            if (index.data(Qt.CheckStateRole)) == Qt.Checked
            else Qt.Checked,
            Qt.CheckStateRole,
        )


def device_name_highlight_color() -> QColor:
    palette = QApplication.palette()
    if is_dark_mode():
        return QColor("#393939")
    else:
        alternate_color = palette.alternateBase().color()
        return QColor(alternate_color).darker(105)


def base64_thumbnail(pixmap: QPixmap, size: QSize) -> str:
    """
    Convert image into format useful for HTML data URIs.

    See https://css-tricks.com/data-uris/

    :param pixmap: image to convert
    :param size: size to scale to
    :return: data in base 64 format
    """

    pixmap = pixmap.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    # Quality 100 means uncompressed, which is faster.
    pixmap.save(buffer, "PNG", quality=100)
    return bytes(buffer.data().toBase64()).decode()
