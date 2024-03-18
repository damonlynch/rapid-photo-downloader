# SPDX-FileCopyrightText: Copyright 2016-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Combines a deviceview and a file system view into one widget
"""

from PyQt5.QtWidgets import QFrame, QSizePolicy, QSplitter, QWidget

from raphodo.constants import minFileSystemViewHeight
from raphodo.ui.destinationdisplay import DestinationDisplay
from raphodo.ui.devicedisplay import (
    DeviceView,
    EmulatedHeaderRow,
    device_header_row_height,
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
        objectName: str,
        view: DeviceView | DestinationDisplay,
        fileSystemView: FileSystemView,
        select_text: str,
        parent: QWidget = None,
    ) -> None:
        super().__init__(parent=parent)
        self.setObjectName(objectName)
        layout = self.layout()
        border_width = QSplitter().lineWidth()
        layout.setContentsMargins(
            border_width, border_width, border_width, border_width
        )
        layout.setSpacing(0)
        self.setLayout(layout)

        self.view = view
        self.view.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
        self.fileSystemView = fileSystemView
        self.emulatedHeader = EmulatedHeaderRow(select_text)
        self.emulatedHeader.setSizePolicy(
            QSizePolicy.MinimumExpanding, QSizePolicy.Maximum
        )

        layout.addWidget(self.emulatedHeader)
        layout.addWidget(self.view)
        layout.addStretch()
        # the value 5 ensures there is a standard gap between the device view and the
        # file system view
        layout.addWidget(self.fileSystemView, 5)
        self.view.setStyleSheet("QListView {border: none;}")
        self.fileSystemView.setFrameShape(QFrame.NoFrame)

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
