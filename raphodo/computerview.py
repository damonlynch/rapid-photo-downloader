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

from typing import Union
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QSplitter, QSizePolicy, QFrame)

from raphodo.devicedisplay import DeviceView, EmulatedHeaderRow, device_header_row_height
from raphodo.filebrowse import FileSystemView
from raphodo.destinationdisplay import DestinationDisplay
from raphodo.constants import minFileSystemViewHeight
from raphodo.viewutils import QFramedWidget


class ComputerWidget(QFramedWidget):
    """
    Combines a device view or destination display, and a file system view, into one widget.

    Also contains an empty header row that emulates the look of an actual header row for a
    a device view or destination display -- it's used when a valid destination or source is
    not yet specified.
    """

    def __init__(self, objectName: str,
                 view: Union[DeviceView, DestinationDisplay],
                 fileSystemView: FileSystemView,
                 select_text: str,
                 parent: QWidget=None) -> None:

        super().__init__(parent)
        self.setObjectName(objectName)
        layout = QVBoxLayout()
        border_width = QSplitter().lineWidth()
        layout.setContentsMargins(border_width, border_width, border_width, border_width)
        layout.setSpacing(0)
        self.setLayout(layout)

        self.view = view
        self.view.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
        self.fileSystemView = fileSystemView
        self.emulatedHeader = EmulatedHeaderRow(select_text)
        self.emulatedHeader.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Maximum)

        layout.addWidget(self.emulatedHeader)
        layout.addWidget(self.view)
        layout.addStretch()
        layout.addWidget(self.fileSystemView, 5)
        self.view.setStyleSheet('QListView {border: none;}')
        self.fileSystemView.setStyleSheet('FileSystemView {border: none;}')

    def setViewVisible(self, visible: bool) -> None:
        self.view.setVisible(visible)
        self.emulatedHeader.setVisible(not visible)
        self.view.updateGeometry()

    def minimumHeight(self) -> int:
        if self.view.isVisible():
            height = self.view.minimumHeight()
        else:
            height = device_header_row_height()
        height += minFileSystemViewHeight()
        return height


