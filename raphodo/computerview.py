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

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QSplitter

from raphodo.devicedisplay import DeviceView
from raphodo.filebrowse import FileSystemView


class ComputerWidget(QWidget):
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
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        self.setLayout(layout)

        if QSplitter().lineWidth():
            style = 'QWidget#%(objectName)s {border: %(size)spx solid palette(shadow);}' % dict(
                objectName=objectName, size=QSplitter().lineWidth())
            self.setStyleSheet(style)

        self.view = view
        self.fileSystemView = fileSystemView
        layout.addWidget(self.view)
        layout.addStretch()
        layout.addWidget(self.fileSystemView, 5)
        self.view.setStyleSheet('QListView {border: 0px solid red;}')
        self.fileSystemView.setStyleSheet('FileSystemView {border: 0px solid red;}')

    def setViewVisible(self, visible: bool) -> None:
        self.view.setVisible(visible)

