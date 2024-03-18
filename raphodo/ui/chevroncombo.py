# SPDX-FileCopyrightText: Copyright 2016-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Combo box with a chevron selector
"""

from PyQt5.QtCore import QPointF, QSize, Qt
from PyQt5.QtGui import QFont, QFontMetrics, QPainter
from PyQt5.QtWidgets import QComboBox, QLabel, QSizePolicy

from raphodo.ui.viewutils import darkModePixmap


class ChevronCombo(QComboBox):
    """
    Combo box with a chevron selector
    """

    def __init__(self, in_panel: bool = False, parent=None) -> None:
        """
        :param in_panel: if True, widget color set to background color,
         else set to window color
        """
        super().__init__(parent)

    def paintEvent(self, event):
        painter = QPainter(self)

        # Draw chevron (down arrow)
        width = int(QFontMetrics(QFont()).height() * (2 / 3))
        size = QSize(width, width)
        pixmap = darkModePixmap(path="icons/chevron-down.svg", size=size)
        x = self.rect().width() - width - 6
        y = self.rect().center().y() - width / 2
        p = QPointF(x, y)
        painter.drawPixmap(p, pixmap)

        # Draw text
        painter.setPen(self.palette().windowText().color())
        painter.drawText(
            self.rect(), Qt.AlignVCenter | Qt.AlignLeft, self.currentText()
        )

    def makeLabel(self, text: str) -> QLabel:
        """
        Render a label to attach to this widget
        """
        label = QLabel(text)
        label.setAlignment(Qt.AlignBottom)
        label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Maximum)
        return label
