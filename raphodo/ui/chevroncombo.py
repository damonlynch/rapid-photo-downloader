# SPDX-FileCopyrightText: Copyright 2016-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Combo box with a chevron selector
"""

from PyQt5.QtCore import QPointF, QSize, Qt
from PyQt5.QtGui import QFont, QFontMetricsF, QPainter, QPaintEvent
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
        self._italicsFont = QFont(font)
        self._italicsFont.setItalic(True)
        self.fm = QFontMetricsF(font)
        self.fmItalics = QFontMetricsF(self._italicsFont)

        self.chevron_width = int(self.fm.height() * (2 / 3))
        size = QSize(self.chevron_width, self.chevron_width)
        self.chevron = darkModePixmap(path="icons/chevron-down.svg", size=size)
        self.text_x = 0
        # Set self.hovered to True to show the chevron selector
        self.hovered = True
        # Set self.initial_state to True to show the initial text
        self._initial_state = False
        self.initial_text = ""


    @property
    def initial_state(self)-> bool:
        return self._initial_state

    @initial_state.setter
    def initial_state(self, state: bool) -> None:
        current = self._initial_state
        self._initial_state = state
        if current != state:
            self.adjustSize()

    # TODO elide lengthy text
    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        if self.initial_state:
            text = self.initial_text
            text_width = self.fmItalics.boundingRect(text).width()
            font = self._italicsFont
        else:
            text = self.currentText()
            text_width = self.fm.boundingRect(text).width()
            font = self._font

        # ic(self.rect().width(), text_width, text)

        # Draw text
        painter.setPen(self.palette().windowText().color())
        painter.setFont(font)
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

    # def sizeHint(self) -> QSize:
    #     width = self.chevron_width


class ChevronComboSpaced(ChevronCombo):
    """
    Combo box with a chevron selector
    """

    def __init__(self, font: QFont, initial_text:str, parent=None) -> None:
        super().__init__(font, parent)
        self.text_x = DeviceDisplayPadding
        self.hovered = False
        self.initial_text = initial_text

    def sizeHint(self) -> QSize:
        if not self.initial_state:
            return  super().sizeHint()

        text_width = self.fmItalics.boundingRect(self.initial_text).width()
        width = DeviceDisplayPadding * 2 + text_width + self.chevron_width
        return QSize(int(width), super().sizeHint().height())
