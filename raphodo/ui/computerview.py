# SPDX-FileCopyrightText: Copyright 2016-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Combines a deviceview and a file system view into one widget
"""

from PyQt5.QtWidgets import QFrame, QSizePolicy, QSplitter, QWidget, QLabel, QVBoxLayout

from raphodo.constants import DeviceDisplayStatus, minFileSystemViewHeight, DeviceDisplayPadding
from raphodo.ui.destinationdisplay import DestinationDisplay
from raphodo.ui.devicedisplay import (
    DeviceView,
    EmulatedHeaderRow,
    device_header_row_height,
)
from raphodo.ui.filebrowse import FileSystemView
from raphodo.ui.stackedwidget import ResizableStackedWidget
from raphodo.ui.viewutils import TightFlexiFrame


class ComputerWidget(TightFlexiFrame):
    """
    Combines a device view or destination display, and a file system view, into one
    widget.

    Also contains an empty header row that emulates the look of an actual header row
    for a device view or destination display -- it's used when a valid destination or
    source is not yet specified.
    """

    def __init__(
        self,
        objectName: str,
        view: DeviceView | DestinationDisplay,
        fileSystemView: FileSystemView,
        select_text: str,
        parent: QWidget = None,
    ) -> None:
        super().__init__(parent=parent)
        self.setObjectName(objectName)
        layout: QVBoxLayout = self.layout()
        border_width = QSplitter().lineWidth()
        layout.setContentsMargins(
            border_width, border_width, border_width, border_width
        )
        layout.setSpacing(DeviceDisplayPadding)
        self.setLayout(layout)

        self.view = view
        self.view.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
        self.fileSystemView = fileSystemView
        self.emulatedHeader = EmulatedHeaderRow(select_text, self)
        self.stackedWidget=ResizableStackedWidget(self)
        self.stackedWidget.addWidget(self.emulatedHeader)
        self.stackedWidget.addWidget(self.view)
        layout.addWidget(self.stackedWidget)
        layout.addWidget(self.fileSystemView, 100)
        self.view.setStyleSheet("QListView {border: none;}")
        self.fileSystemView.setFrameShape(QFrame.NoFrame)

    def setViewVisible(self, visible: bool) -> None:
        if visible:
            self.stackedWidget.setCurrentIndex(1)
        else:
            self.stackedWidget.setCurrentIndex(0)

    def setDeviceDisplayStatus(self, status: DeviceDisplayStatus) -> None:
        self.emulatedHeader.setDeviceDisplayStatus(status)

    def setDevicePath(self, path: str) -> None:
        self.emulatedHeader.setPath(path)

    def height(self) -> int:
        return self.stackedWidget.height() + minFileSystemViewHeight()
