# Copyright (C) 2016 Damon Lynch <damonlynch@gmail.com>

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
Widget containing Header with Toggle Switch, and contains widget that appears or
disappears depending on the toggle switch's state.

Portions modeled on Canonical's QExpander, which is an 'Expander widget
similar to the GtkExpander', Copyright 2012 Canonical Ltd
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2016, Damon Lynch"

from typing import Optional
from PyQt5.QtCore import pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout,
                             QWidget)

from raphodo.toggleswitch import QToggleSwitch

class QToggleView(QWidget):
    """
    A header bar with tooggle switch over a widget that is switched on/off.
    """

    valueChanged = pyqtSignal(bool)

    def __init__(self, label: str,
                 toggleToolTip: Optional[str],
                 headerColor: Optional[QColor]=None,
                 headerFontColor: Optional[QColor]=None,
                 on: bool=True,
                 parent: QWidget=None) -> None:

        super().__init__(parent)

        self.header = QWidget(self)
        if headerColor is not None:
            headerStyle = """QWidget { background-color: %s; }""" % headerColor.name()
            self.header.setStyleSheet(headerStyle)
        self.header.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)

        headerLayout = QHBoxLayout()
        headerLayout.setContentsMargins(5, 0, 5, 0)

        self.label = QLabel(label.upper())
        if headerFontColor is not None:
            headerFontStyle =  "QLabel {color: %s;}" % headerFontColor.name()
            self.label.setStyleSheet(headerFontStyle)

        self.toggleSwitch = QToggleSwitch(background=headerColor, parent=self)
        self.toggleSwitch.valueChanged.connect(self.toggled)
        if toggleToolTip:
            self.toggleSwitch.setToolTip(toggleToolTip)

        self.header.setLayout(headerLayout)
        headerLayout.addWidget(self.label)
        headerLayout.addStretch()
        headerLayout.addWidget(self.toggleSwitch)

        self.content = None
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)
        layout.addWidget(self.header)
        self.toggleSwitch.setOn(on)

    def addWidget(self, widget: QWidget) -> None:
        """
        Add a widget to the expander.

        The previous widget will be removed.
        """
        if self.content is not None:
            self.layout().removeWidget(self.content)
        self.content = widget
        self.layout().addWidget(self.content)
        self.toggled(0)

    def text(self) -> str:
        """Return the text of the label."""
        return self.label.text()

    def setText(self, text: str) -> None:
        """Set the text of the label."""
        self.label.setText(text)

    def on(self):
        """Return if widget is expanded."""
        return self.toggleSwitch.on()

    def setOn(self, isOn: bool) -> None:
        """Expand the widget or not."""

        self.toggleSwitch.setOn(isOn)

    @pyqtSlot(int)
    def toggled(self, value: int) -> None:
        if self.content is not None:
            self.content.setVisible(self.on())

        self.valueChanged.emit(self.on())



