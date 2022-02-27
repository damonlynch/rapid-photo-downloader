# Copyright (C) 2016-2022 Damon Lynch <damonlynch@gmail.com>

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

"""
Combo box with a chevron selector
"""

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2011-2022, Damon Lynch"

from PyQt5.QtWidgets import QComboBox, QLabel, QSizePolicy
from PyQt5.QtGui import QFontMetrics, QFont, QPainter
from PyQt5.QtCore import Qt, QSize, QPointF

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
        pixmap = darkModePixmap(path=":/icons/chevron-down.svg", size=size)
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
