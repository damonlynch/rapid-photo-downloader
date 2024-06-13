# SPDX-FileCopyrightText: Copyright 2016-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Combines a deviceview and a file system view into one widget
"""

from PyQt5.QtWidgets import QFrame, QSplitter, QVBoxLayout, QWidget

from raphodo.constants import (
    DeviceDisplayPadding,
    minFileSystemViewHeight,
)
from raphodo.ui.devicedisplay import (
    DeviceRows,
    PhotoOrVideoDestDeviceRows,
)
from raphodo.ui.filebrowse import FileSystemView
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
        object_name: str,
        deviceRows: DeviceRows,
        fileSystemView: FileSystemView,
        parent: QWidget = None,
    ) -> None:
        super().__init__(parent=parent)
        self.setObjectName(object_name)
        layout: QVBoxLayout = self.layout()
        border_width = QSplitter().lineWidth()
        layout.setContentsMargins(
            border_width, border_width, border_width, border_width
        )
        layout.setSpacing(DeviceDisplayPadding)
        self.fileSystemView = fileSystemView
        self.deviceRows = deviceRows

        layout.addWidget(self.fileSystemView, 100)
        self.fileSystemView.setFrameShape(QFrame.NoFrame)

    def height(self) -> int:
        return self.layout().geometry().height() + minFileSystemViewHeight()


class DestComputerWidget(ComputerWidget):
    def __init__(
        self,
        object_name: str,
        deviceRows: PhotoOrVideoDestDeviceRows,
        fileSystemView: FileSystemView,
        parent: QWidget = None,
    ) -> None:
        super().__init__(
            object_name=object_name,
            deviceRows=deviceRows,
            fileSystemView=fileSystemView,
            parent=parent,
        )
        layout: QVBoxLayout = self.layout()
        layout.insertWidget(0, self.deviceRows)
