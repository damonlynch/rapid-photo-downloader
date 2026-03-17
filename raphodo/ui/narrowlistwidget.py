#  SPDX-FileCopyrightText: 2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: GPL-3.0-or-later

from typing import cast

from PyQt6.QtCore import QModelIndex, QRect, QRectF, QSize, Qt, pyqtSlot
from PyQt6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPainterPath, QPalette
from PyQt6.QtWidgets import (
    QFrame,
    QListWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from raphodo.application import Application
from raphodo.ui.viewutils import ProxyStyleNoFocusRectangle


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
        self.app = cast(Application, QGuiApplication.instance())
        self.app.applicationPaletteChanged.connect(self.applicationPaletteChanged)
        self._flat_look = flat_look
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._minimum_rows = minimum_rows
        self._minimum_width = minimum_width

        if no_focus_rectangle:
            self.setStyle(ProxyStyleNoFocusRectangle())
        if flat_look:
            self.setFrameShape(QFrame.Shape.NoFrame)
            self.right_padding = 60
            self.setSpacing(2)
            # Enable hover effect in delegate
            self.viewport().setMouseTracking(True)
            self.applicationPaletteChanged(self.app.darkMode)
        else:
            self.right_padding = 0

    @pyqtSlot(bool)
    def applicationPaletteChanged(self, dark_mode: bool) -> None:
        if self._flat_look:
            palette = QPalette()
            color = palette.window().color()
            palette.setColor(QPalette.ColorRole.Base, color)
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
