#  SPDX-FileCopyrightText: 2022-2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: GPL-3.0-or-later

from PyQt6.QtCore import QRect, pyqtSlot
from PyQt6.QtGui import QPainter, QPaintEvent, QPalette, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QListView,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from raphodo.ui.scrollbarfusion import paletteMidPen
from raphodo.ui.viewutils import device_name_highlight_color


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
        # FIXME
        self.quirkPen = QPen(device_name_highlight_color(False))

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
