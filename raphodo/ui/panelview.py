#  SPDX-FileCopyrightText: 2016-2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: GPL-3.0-or-later

"""
Widget containing header, which can have an optional widget
attached to the right side.

Portions modeled on Canonical's QExpander, which is an 'Expander widget
similar to the GtkExpander', Copyright 2012 Canonical Ltd
"""

from typing import cast

from PyQt6.QtCore import QSize, Qt, pyqtSlot
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPalette
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from raphodo.application import Application
from raphodo.constants import (
    DarkModeHeaderBackgroundName,
    HeaderBackgroundName,
    minPanelWidth,
)
from raphodo.internationalisation.install import install_gettext

install_gettext()


class QPanelView(QWidget):
    """
    A header bar with a child widget.
    """

    def __init__(
        self,
        label: str,
        headerColor: QColor | None = None,
        headerFontColor: QColor | None = None,
        parent: QWidget = None,
    ) -> None:
        super().__init__(parent=parent)
        self.app = cast(Application, QGuiApplication.instance())
        self.app.applicationPaletteChanged.connect(self.setDarkMode)
        self.header = QWidget(self)

        if headerColor is not None:
            self.headerColor = self.headerColorDark = headerColor
        else:
            self.headerColorDark = QColor(DarkModeHeaderBackgroundName)
            self.headerColor = QColor(HeaderBackgroundName)

        self.setDarkMode(self.app.darkMode)
        self.header.setAutoFillBackground(True)
        self.header.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed
        )

        self.headerLayout = QHBoxLayout()
        self.headerLayout.setContentsMargins(5, 2, 5, 2)

        self.label = QLabel(label.upper())
        if headerFontColor is None:
            headerFontColor = QColor(Qt.GlobalColor.white)
        palette = self.label.palette()
        palette.setColor(QPalette.ColorRole.WindowText, headerFontColor)
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

    @pyqtSlot(bool)
    def setDarkMode(self, dark_mode) -> None:
        headerColor = self.headerColorDark if dark_mode else self.headerColor
        palette = self.header.palette()
        palette.setColor(QPalette.ColorRole.Window, headerColor)
        self.header.setPalette(palette)

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
            font_height = QFontMetrics(QFont()).height()
            width = minPanelWidth()
            height = font_height * 2
        else:
            width = self.content.minimumWidth()
            height = self.content.minimumHeight()
        return QSize(width, self.header.height() + height)
