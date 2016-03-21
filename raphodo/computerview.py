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
Combines a deviceview and a file system view into one widget
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2016, Damon Lynch"

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QSplitter, QStyleOptionFrame, QStyle,
                             QApplication)
from PyQt5.QtGui import QPainter

from raphodo.devicedisplay import DeviceView
from raphodo.filebrowse import FileSystemView
from raphodo.constants import minFileSystemViewHeight


class QFramedWidget(QWidget):
    """
    Draw a Frame around the widget in the style of the application.
    """
    def paintEvent(self, *opts):
        painter = QPainter(self)
        option = QStyleOptionFrame()
        option.initFrom(self)
        style = QApplication.style()  # type: QStyle
        style.drawPrimitive(QStyle.PE_Frame, option, painter)
        super().paintEvent(*opts)


class ComputerWidget(QFramedWidget):
    """
    Combines a deviceview and a file system view into one widget
    """
    def __init__(self, objectName: str,
                 view: DeviceView,
                 fileSystemView: FileSystemView,
                 parent: QWidget=None) -> None:

        super().__init__(parent)
        self.setObjectName(objectName)
        layout = QVBoxLayout()
        border_width = QSplitter().lineWidth()
        layout.setContentsMargins(border_width, border_width, border_width, border_width)
        layout.setSpacing(0)
        self.setLayout(layout)

        self.view = view
        self.fileSystemView = fileSystemView
        layout.addWidget(self.view)
        layout.addStretch()
        layout.addWidget(self.fileSystemView, 5)
        self.view.setStyleSheet('QListView {border: none;}')
        self.fileSystemView.setStyleSheet('FileSystemView {border: none;}')

    def setViewVisible(self, visible: bool) -> None:
        self.view.setVisible(visible)

    def minimumHeight(self) -> int:
        if self.view.isVisible():
            height = self.view.minimumHeight()
        else:
            height = 0
        height += minFileSystemViewHeight()
        return height

