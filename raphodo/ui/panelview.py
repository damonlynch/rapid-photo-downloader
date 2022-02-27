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
Widget containing header, which can have an optional widget
attached to the right side.

Portions modeled on Canonical's QExpander, which is an 'Expander widget
similar to the GtkExpander', Copyright 2012 Canonical Ltd
"""

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2016-2022, Damon Lynch"

from typing import Optional

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QColor, QFontMetrics, QFont, QPalette
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from raphodo.constants import (
    minPanelWidth,
    HeaderBackgroundName,
    DarkModeHeaderBackgroundName,
)
from raphodo.ui.viewutils import is_dark_mode


class QPanelView(QWidget):

    """
    A header bar with a child widget.
    """

    def __init__(
        self,
        label: str,
        headerColor: Optional[QColor] = None,
        headerFontColor: Optional[QColor] = None,
        parent: QWidget = None,
    ) -> None:
        super().__init__(parent=parent)
        self.header = QWidget(self)

        if headerColor is None:
            if is_dark_mode():
                headerColor = QColor(DarkModeHeaderBackgroundName)
            else:
                headerColor = QColor(HeaderBackgroundName)
        palette = self.header.palette()
        palette.setColor(QPalette.Window, headerColor)
        self.header.setAutoFillBackground(True)
        self.header.setPalette(palette)
        self.header.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)

        self.headerLayout = QHBoxLayout()
        self.headerLayout.setContentsMargins(5, 2, 5, 2)

        self.label = QLabel(label.upper())
        if headerFontColor is None:
            headerFontColor = QColor(Qt.white)
        palette = self.label.palette()
        palette.setColor(QPalette.WindowText, headerFontColor)
        self.label.setPalette(palette)

        self.header.setLayout(self.headerLayout)
        self.headerLayout.addWidget(self.label)
        self.headerLayout.addStretch()

        self.headerWidget = None

        self.content = None
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)
        layout.addWidget(self.header)

    def addWidget(self, widget: QWidget) -> None:
        """
        Add a widget to the Panel View.

        Any previous widget will be removed.

        :param widget: widget to add
        """

        if self.content is not None:
            self.layout().removeWidget(self.content)
        self.content = widget
        self.layout().addWidget(self.content)

    def addHeaderWidget(self, widget: QWidget) -> None:
        """
        Add a widget to the header bar, on the right side.

        Any previous widget will be removed.

        :param widget: widget to add
        """
        if self.headerWidget is not None:
            self.headerLayout.removeWidget(self.headerWidget)
        self.headerWidget = widget
        self.headerLayout.addWidget(widget)

    def text(self) -> str:
        """Return the text of the label."""
        return self.label.text()

    def setText(self, text: str) -> None:
        """Set the text of the label."""
        self.label.setText(text)

    def minimumSize(self) -> QSize:
        if self.content is None:
            font_height = QFontMetrics(QFont).height()
            width = minPanelWidth()
            height = font_height * 2
        else:
            width = self.content.minimumWidth()
            height = self.content.minimumHeight()
        return QSize(width, self.header.height() + height)
