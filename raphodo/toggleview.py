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
from PyQt5.QtCore import pyqtSignal, pyqtSlot, QSize
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import (QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout,
                             QWidget)

from raphodo.toggleswitch import QToggleSwitch
from raphodo.panelview import QPanelView
from raphodo.viewutils import QFramedWidget


class BlankWidget(QFramedWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        palette = QPalette()
        palette.setColor(QPalette.Window, palette.color(palette.Base))
        self.setAutoFillBackground(True)
        self.setPalette(palette)


class QToggleView(QPanelView):
    """
    A header bar with tooggle switch over a widget that is switched on/off.
    """

    valueChanged = pyqtSignal(bool)

    def __init__(self, label: str,
                 display_alternate: bool,
                 toggleToolTip: Optional[str],
                 headerColor: Optional[QColor]=None,
                 headerFontColor: Optional[QColor]=None,
                 on: bool=True,
                 parent: QWidget=None) -> None:

        super().__init__(label=label, headerColor=headerColor, headerFontColor=headerFontColor,
                         parent=parent)
        # Override base class definition:
        self.headerLayout.setContentsMargins(5, 0, 5, 0)

        if display_alternate:
            self.alternateWidget = BlankWidget()
            layout = self.layout()  # type: QVBoxLayout
            layout.addWidget(self.alternateWidget)
        else:
            self.alternateWidget = None


        self.toggleSwitch = QToggleSwitch(background=headerColor, parent=self)
        self.toggleSwitch.valueChanged.connect(self.toggled)
        if toggleToolTip:
            self.toggleSwitch.setToolTip(toggleToolTip)
        self.addHeaderWidget(self.toggleSwitch)
        self.toggleSwitch.setOn(on)

    def addWidget(self, widget: QWidget) -> None:
        super().addWidget(widget)
        self.toggled(0)

    def on(self) -> bool:
        """Return if widget is expanded."""

        return self.toggleSwitch.on()

    def setOn(self, isOn: bool) -> None:
        """Expand the widget or not."""

        self.toggleSwitch.setOn(isOn)

    @pyqtSlot(int)
    def toggled(self, value: int) -> None:
        if self.content is not None:
            self.content.setVisible(self.on())
            if self.alternateWidget is not None:
                self.alternateWidget.setVisible(not self.on())

        self.valueChanged.emit(self.on())

    def minimumSize(self) -> QSize:
        size = super().minimumSize()
        width = size.width()
        height = self.minimumHeight()
        return QSize(width, height)

    def minimumHeight(self) -> int:
        if not self.toggleSwitch.on():
            return self.header.height()
        else:
            return super().minimumSize().height()





