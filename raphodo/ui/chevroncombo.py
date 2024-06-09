# SPDX-FileCopyrightText: Copyright 2016-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Combo box with a chevron selector
"""

from PyQt5.QtCore import QPointF, QSize, Qt, QEvent, QRect, QSize
from PyQt5.QtGui import QFont, QFontMetricsF, QPainter, QPaintEvent, QColor, QPixmap
from PyQt5.QtWidgets import QComboBox, QLabel, QSizePolicy

from raphodo.constants import DeviceDisplayPadding
from raphodo.ui.viewutils import darkModePixmap


class ChevronCombo(QComboBox):
    """
    Combo box with a chevron selector
    """

    def __init__(self, font: QFont, parent=None) -> None:
        """
        :param in_panel: if True, widget color set to background color,
         else set to window color
        """
        super().__init__(parent)
        self._font = font
        self.fm = QFontMetricsF(font)
        self.chevron_width = int(self.fm.height() * (2 / 3))
        size = QSize(self.chevron_width, self.chevron_width)
        self.chevron = darkModePixmap(path="icons/chevron-down.svg", size=size)
        self.text_x = 0
        # Set self.hovered to True to show the chevron selector
        self.hovered = True

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        text = self.currentText()
        text_width = self.fm.boundingRect(text).width()

        # Draw text
        painter.setPen(self.palette().windowText().color())
        rect = self.rect().adjusted(self.text_x, 0, -self.text_x, 0)
        painter.drawText(rect, int(Qt.AlignVCenter | Qt.AlignLeft), text)

        if not self.hovered:
            return

        # Draw chevron (down arrow)
        x = text_width + DeviceDisplayPadding + self.text_x
        y = self.rect().center().y() - self.chevron_width / 3
        p = QPointF(x, y)
        painter.drawPixmap(p, self.chevron)

    def makeLabel(self, text: str) -> QLabel:
        """
        Render a label to attach to this widget
        """
        label = QLabel(text)
        label.setAlignment(Qt.AlignBottom)
        label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Maximum)
        return label

class ChevronComboSpaced(ChevronCombo):
    """
    Combo box with a chevron selector
    """

    def __init__(self, font: QFont, parent=None) -> None:
        super().__init__(font, parent)
        self.text_x = DeviceDisplayPadding
        self.hovered = False
