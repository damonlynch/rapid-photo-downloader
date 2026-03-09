#  SPDX-FileCopyrightText: 2015-2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: GPL-3.0-or-later

import functools
import sys
from collections import namedtuple

from packaging.version import parse
from PyQt6.QtCore import (
    QT_VERSION_STR,
    QAbstractItemModel,
    QBuffer,
    QEvent,
    QIODevice,
    QModelIndex,
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QIcon,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPalette,
    QPen,
    QPixmap,
    QResizeEvent,
    QShowEvent,
)
from PyQt6.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QFrame,
    QItemDelegate,
    QLabel,
    QListView,
    QListWidget,
    QMessageBox,
    QProxyStyle,
    QScrollArea,
    QScrollBar,
    QSplitter,
    QSplitterHandle,
    QStyle,
    QStyledItemDelegate,
    QStyleOption,
    QStyleOptionButton,
    QStyleOptionSlider,
    QStyleOptionViewItem,
    QStylePainter,
    QVBoxLayout,
    QWidget,
)

from raphodo.constants import HeaderBackgroundName
from raphodo.internationalisation.install import install_gettext
from raphodo.tools.utilities import data_file_path

install_gettext()

QT6_VERSION = parse(QT_VERSION_STR)


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
        self.row_to_id: dict[int, int] = {}
        self.id_to_row: dict[int, int] = {}

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
        return f"{self.row_to_id!r} {self.id_to_row!r}"

    def __str__(self) -> str:
        return f"Row to id: {self.row_to_id!r}\nId to row: {self.id_to_row!r}"

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

    def remove_rows(self, position: int, rows=1) -> list[int]:
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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent=parent)
        self.previous_height = 0
        self.setObjectName("mainWindowHorizontalSplitter")
        self.setOrientation(Qt.Orientation.Horizontal)

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
        return SourceSplitterHandle(Qt.Orientation.Vertical, self)


class ScrollBarEmitsVisible(QScrollBar):
    """
    Emits a signal when it appears or disappears. Shares same code
    with FramedScrollBar, which is unavoidable due to rules around
    PyQt multiple inheritance.
    """

    scrollBarVisible = pyqtSignal(bool)

    def __init__(self, orientation, parent: QWidget | None = None) -> None:
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

    def __init__(self, orientation, name: str, parent: QWidget | None = None) -> None:
        super().__init__(orientation=orientation, parent=parent)
        self.frame_width = self.style().pixelMetric(
            QStyle.PixelMetric.PM_DefaultFrameWidth
        )
        orientation = (
            "Vertical" if orientation == Qt.Orientation.Vertical else "Horizontal"
        )
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
        if self.orientation() == Qt.Orientation.Vertical:
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
        if self.orientation() == Qt.Orientation.Vertical:
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
        if self.orientation() == Qt.Orientation.Horizontal:
            option.state |= QStyle.StateFlag.State_Horizontal

        rect = self.renderRect()

        option.rect = rect
        option.palette = self.palette()
        option.subControls = (
            QStyle.SubControl.SC_ScrollBarAddLine
            | QStyle.SubControl.SC_ScrollBarSubLine
            | QStyle.SubControl.SC_ScrollBarAddPage
            | QStyle.SubControl.SC_ScrollBarSubPage
            | QStyle.SubControl.SC_ScrollBarFirst
            | QStyle.SubControl.SC_ScrollBarLast
        )

        painter.fillRect(
            option.rect, QApplication.palette().window().color().darker(102)
        )
        self.style().drawComplexControl(
            QStyle.ComplexControl.CC_ScrollBar, option, painter
        )

        # Highlight the handle (slider) on mouse over, otherwise render it as normal
        option.subControls = QStyle.SubControl.SC_ScrollBarSlider
        if (
            option.state & QStyle.StateFlag.State_MouseOver
            == QStyle.StateFlag.State_MouseOver
        ):
            palette = self.palette()
            if sys.platform == "win32":
                color = self.palette().base().color()
            else:
                color = self.palette().button().color().lighter(102)
            palette.setColor(QPalette.ColorRole.Button, color)
            option.palette = palette
        self.style().drawComplexControl(
            QStyle.ComplexControl.CC_ScrollBar, option, painter
        )

        # Render the borders
        painter.resetTransform()
        painter.setPen(self.midPen)
        self.renderEdges(painter)

    def renderRect(self) -> QRect:
        rect = QRect(self.rect())
        if self.orientation() == Qt.Orientation.Vertical:
            rect.adjust(self.frame_width, self.frame_width * 2, 0, 0)
        else:
            rect.adjust(self.frame_width * 2, self.frame_width, 0, 0)
        return rect

    def renderEdges(self, painter: QStylePainter) -> None:
        rect = self.rect()
        if self.orientation() == Qt.Orientation.Vertical:
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
    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__(orientation=Qt.Orientation.Vertical, name=name, parent=parent)

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
        self.setFrameShape(QFrame.Shape.NoFrame)
        sbv = FramedScrollBar(orientation=Qt.Orientation.Vertical, name=name)
        sbh = FramedScrollBar(orientation=Qt.Orientation.Horizontal, name=name)
        self.setVerticalScrollBar(sbv)
        self.setHorizontalScrollBar(sbh)
        sbv.scrollBarVisible.connect(self.verticalScrollBarVisible)
        sbh.scrollBarVisible.connect(self.horizontalScrollBarVisible)


class FlexiFrameObject:
    def __init__(self, **kwds):
        super().__init__(**kwds)
        self.frame_width = QApplication.style().pixelMetric(
            QStyle.PixelMetric.PM_DefaultFrameWidth
        )
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
        self, render_top_edge: bool = False, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent=parent)
        self.render_top_edge = render_top_edge
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), palette.color(palette.ColorRole.Base))
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
        self, render_top_edge: bool = False, parent: QWidget | None = None
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
        self, frame_enabled: bool | None = True, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
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
        palette.setColor(
            QPalette.ColorRole.Window, palette.color(palette.ColorRole.Base)
        )
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
        if QStyle.PrimitiveElement.PE_FrameFocusRect == element:
            pass
        else:
            super().drawPrimitive(element, option, painter, widget)


_is_dark_mode = False


def is_dark_mode() -> bool:
    return _is_dark_mode


def set_dark_mode(mode: bool) -> None:
    global _is_dark_mode
    _is_dark_mode = mode


def validate_dark_mode():
    app = QGuiApplication.instance()
    if app is None:
        return False
    palette = app.palette()
    mode = (
        palette.color(QPalette.ColorRole.Window).lightnessF()
        < palette.color(QPalette.ColorRole.WindowText).lightnessF()
    )
    assert mode == _is_dark_mode


def highlight_is_dark() -> bool:
    highlight_hsv_value = (
        QApplication.palette().color(QPalette.ColorRole.Highlight).value()
    )
    return highlight_hsv_value < 128


class NarrowListWidget(QListWidget):
    """
    Create a list widget that is not by default enormously wide.

    See http://stackoverflow.com/questions/6337589/qlistwidget-adjust-size-to-content
    """

    def __init__(
        self,
        minimum_rows: int = 0,
        minimum_width: int = 0,
        no_focus_rectangle: bool = False,
        flat_look: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent=parent)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._minimum_rows = minimum_rows
        self._minimum_width = minimum_width
        palette = QPalette()

        if no_focus_rectangle:
            self.setStyle(ProxyStyleNoFocusRectangle())
        if flat_look:
            self.setFrameShape(QFrame.Shape.NoFrame)
            color = palette.window().color()  # type: QColor
            palette.setColor(QPalette.ColorRole.Base, color)
            self.right_padding = 60
            self.setSpacing(2)
            # Enable hover effect in delegate
            self.viewport().setMouseTracking(True)
        else:
            self.right_padding = 0
        self.setPalette(palette)

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
            max(
                self.sizeHintForColumn(0) + self.frameWidth() * 2 + self.right_padding,
                self._minimum_width,
            )
        )
        return s


class NarrowListDelegate(QStyledItemDelegate):
    def paint(
        self, painter: QPainter, inOption: QStyleOptionViewItem, index: QModelIndex
    ) -> None:

        option = QStyleOptionViewItem(inOption)
        self.initStyleOption(option, index)

        painter.save()
        rect = option.rect  # type: QRect
        icon = option.icon  # type: QIcon

        if (
            QStyle.StateFlag.State_MouseOver in option.state
            or QStyle.StateFlag.State_Selected in option.state
        ):
            painter.fillRect(
                rect,
                option.palette.color(
                    QPalette.ColorGroup.Active, QPalette.ColorRole.Midlight
                ),
            )

        icon_width = option.decorationSize.width()
        bar_width = 4
        padding = 12
        icon.paint(
            painter,
            rect.x() + bar_width + padding,
            rect.y(),
            icon_width,
            rect.height(),
            alignment=Qt.AlignmentFlag.AlignVCenter,
        )
        text_x = rect.x() + bar_width + padding * 2 + icon_width
        textRect = rect.adjusted(text_x, 0, 0, 0)

        if QStyle.StateFlag.State_Selected in option.state:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            path = QPainterPath()
            highlightRect = QRect(rect.x(), rect.y(), bar_width, rect.height())
            vertical_crop = 7
            highlightRect.adjust(0, vertical_crop, 0, -vertical_crop)
            highlightRect = QRectF(highlightRect)
            path.addRoundedRect(highlightRect, 2.0, 2.0)
            painter.fillPath(
                path,
                option.palette.color(
                    QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight
                ),
            )

        painter.drawText(
            textRect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            option.text,
        )

        painter.restore()


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
        (QDialogButtonBox.StandardButton.Ok, _("&OK")),
        (QDialogButtonBox.StandardButton.Close, _("&Close")),
        (QDialogButtonBox.StandardButton.Cancel, _("&Cancel")),
        (QDialogButtonBox.StandardButton.Save, _("&Save")),
        (QDialogButtonBox.StandardButton.Help, _("&Help")),
        (QDialogButtonBox.StandardButton.RestoreDefaults, _("Restore Defaults")),
        (QDialogButtonBox.StandardButton.Yes, _("&Yes")),
        (QDialogButtonBox.StandardButton.No, _("&No")),
    )
    for role, text in buttons:
        button = buttonBox.button(role)
        if button:
            button.setText(text)


def translateMessageBoxButtons(messageBox: QMessageBox) -> None:
    if not Do_Message_And_Dialog_Box_Button_Translation:
        return

    buttons = (
        (QMessageBox.StandardButton.Ok, _("&OK")),
        (QMessageBox.StandardButton.Close, _("&Close")),
        (QMessageBox.StandardButton.Cancel, _("&Cancel")),
        (QMessageBox.StandardButton.Save, _("&Save")),
        (QMessageBox.StandardButton.Yes, _("&Yes")),
        (QMessageBox.StandardButton.No, _("&No")),
    )
    for role, text in buttons:
        button = messageBox.button(role)
        if button:
            button.setText(text)


def standardMessageBox(
    message: str,
    rich_text: bool,
    standardButtons: QMessageBox.StandardButton,
    defaultButton: QMessageBox.StandardButton | None = None,
    parent=None,
    title: str | None = None,
    icon: QIcon | None = None,
    iconPixmap: QPixmap | None = None,
    iconType: QMessageBox.Icon | None = None,
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
     are equal to QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, then QMessageBox.Icon.Question
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
        msgBox.setTextFormat(Qt.TextFormat.RichText)
    msgBox.setWindowTitle(title)
    msgBox.setText(message)

    msgBox.setStandardButtons(standardButtons)
    if defaultButton:
        msgBox.setDefaultButton(defaultButton)
    translateMessageBoxButtons(messageBox=msgBox)

    if (
        iconType is None
        and standardButtons
        == QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    ):
        iconType = QMessageBox.Icon.Question

    if iconType:
        msgBox.setIcon(iconType)
    else:
        if iconPixmap is None:
            if icon:
                iconPixmap = icon.pixmap(standardIconSize())
            else:
                iconPixmap = QIcon(data_file_path("rapid-photo-downloader.svg")).pixmap(
                    standardIconSize()
                )
        msgBox.setIconPixmap(iconPixmap)

    return msgBox


def validateWindowSizeLimit(available: QSize, desired: QSize) -> tuple[bool, QSize]:
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
) -> tuple[bool, QPoint]:
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
        pixmap = pixmap.scaledToWidth(
            pixmap.width() * scale, Qt.TransformationMode.SmoothTransformation
        )
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


def scaledIcon(path: str, size: QSize | None = None) -> QIcon:
    """
    Create a QIcon that scales well
    Uses .addFile()
    """
    i = QIcon()
    if size is None:
        s = standard_font_size()
        size = QSize(s, s)
    i.addFile(path, size)
    return i


def coloredPixmap(
    color: str | QColor,
    path: str | None = None,
    pixmap: QPixmap | None = None,
    size: QSize | None = None,
) -> QPixmap:
    if isinstance(color, str):
        color = QColor(color)
    if path is not None:
        pixmap = (
            QIcon(data_file_path(path)).pixmap(size)
            if size
            else QPixmap(data_file_path(path))
        )
    else:
        assert pixmap is not None

    painter = QPainter(pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), color)
    painter.end()
    return pixmap


def darkModePixmap(
    path: str | None = None,
    pixmap: QPixmap | None = None,
    size: QSize | None = None,
    soften_regular_mode_color: bool | None = False,
) -> QPixmap:
    """
    Inverts pixmap when in dark mode
    """
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
            return QIcon(data_file_path(path)).pixmap(size)
        else:
            return QPixmap(data_file_path(path))


def darkModeIcon(
    icon: QIcon | None = None,
    path: str | None = None,
    size: QSize | None = None,
    soften_regular_mode_color: bool | None = False,
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
            return QIcon(data_file_path(path))


def menuHoverColor() -> QColor:
    if is_dark_mode():
        return QGuiApplication.palette().color(QPalette.ColorRole.Highlight)
    else:
        return QGuiApplication.palette().color(QPalette.ColorRole.Window).darker(110)


class CheckBoxDelegate(QItemDelegate):
    """
    A delegate that places a fully functioning centered QCheckBox cell in the column
    to which it's applied.
    """

    def __init__(self, parent):
        QItemDelegate.__init__(self, parent)

        checkboxRect = QRect(
            QApplication.style().subElementRect(
                QStyle.SubElement.SE_CheckBoxIndicator, QStyleOptionButton(), None
            )
        )
        self.checkboxHalfWidth = int(checkboxRect.width() / 2)

    def createEditor(
        self, parent, option: QStyleOptionViewItem, indexindex: QModelIndex
    ) -> QWidget | None:
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

        checked = index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
        enabled = int(index.flags() & Qt.ItemFlag.ItemIsEditable) > 0

        if not checked and not enabled:
            return

        painter.save()

        checkboxStyleOption = QStyleOptionButton()
        if checked:
            checkboxStyleOption.state |= QStyle.StateFlag.State_On
        else:
            checkboxStyleOption.state |= QStyle.StateFlag.State_Off

        if enabled:
            checkboxStyleOption.state |= QStyle.StateFlag.State_Enabled
            checkboxStyleOption.state &= ~QStyle.StateFlag.State_ReadOnly
        else:
            checkboxStyleOption.state &= ~QStyle.StateFlag.State_Enabled
            checkboxStyleOption.state |= QStyle.StateFlag.State_ReadOnly
            color = checkboxStyleOption.palette.color(QPalette.ColorRole.Window).darker(
                130
            )
            checkboxStyleOption.palette.setColor(QPalette.ColorRole.Text, color)

        checkboxStyleOption.rect = option.rect
        checkboxStyleOption.rect.setX(
            option.rect.x() + round(option.rect.width() / 2) - self.checkboxHalfWidth
        )

        QApplication.style().drawControl(
            QStyle.ControlElement.CE_CheckBox, checkboxStyleOption, painter
        )
        painter.restore()

    def editorEvent(
        self,
        event: QEvent,
        model: QAbstractItemModel,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> bool:
        if not int(index.flags() & Qt.ItemFlag.ItemIsEditable) > 0:
            return False

        if (
            event.type() == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self.setModelData(None, model, index)
            return True
        elif event.type() == QEvent.Type.KeyPress:
            if event.key() != Qt.Key.Key_Space and event.key() != Qt.Key.Key_Select:
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
            Qt.CheckState.Unchecked
            if (index.data(Qt.ItemDataRole.CheckStateRole)) == Qt.CheckState.Checked
            else Qt.CheckState.Checked,
            Qt.ItemDataRole.CheckStateRole,
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

    pixmap = pixmap.scaled(
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    # Quality 100 means uncompressed, which is faster.
    pixmap.save(buffer, "PNG", quality=100)
    return bytes(buffer.data().toBase64()).decode()
