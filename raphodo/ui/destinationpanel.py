# SPDX-FileCopyrightText: Copyright 2017-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Display photo and video destinations
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QSplitter, QVBoxLayout, QWidget

from raphodo.constants import DeviceDisplayStatus, DisplayFileType
from raphodo.customtypes import DownloadFilesSizeAndNum
from raphodo.internationalisation.install import install_gettext
from raphodo.rpdfile import FileType
from raphodo.storage.storage import StorageSpace
from raphodo.ui.computerview import DestComputerWidget
from raphodo.ui.destinationdisplay import (
    CombinedDestinationDisplay,
    IndividualDestinationDisplay,
)
from raphodo.ui.panelview import QPanelView
from raphodo.ui.viewutils import ScrollAreaNoFrame

install_gettext()


class DestinationPanel(ScrollAreaNoFrame):
    def __init__(self, parent) -> None:
        super().__init__(name="destinationPanel", parent=parent)
        assert parent is not None
        self.rapidApp = parent
        self.prefs = self.rapidApp.prefs

        self.setObjectName("destinationPanelScrollArea")

        self.splitter = QSplitter(parent=self)

        self.splitter.setObjectName("destinationPanelSplitter")
        self.splitter.setOrientation(Qt.Vertical)

        self.createDestinationViews()
        self.splitter.addWidget(self.photoDestinationContainer)
        self.splitter.addWidget(self.videoDestination)

        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.setWidget(self.splitter)
        self.setWidgetResizable(True)

    def createDestinationViews(self) -> None:
        """
        Create the widgets that let the user choose where to download photos and videos
        to, and that show them how much storage space there is available for their
        files.
        """

        self.photoDestination = QPanelView(
            label=_("Photos"),
        )
        self.photoDestination.setObjectName("photoDestinationPanelView")
        self.videoDestination = QPanelView(
            label=_("Videos"),
        )
        self.videoDestination.setObjectName("videoDestinationPanelView")

        # Display storage space when photos and videos are being downloaded to the same
        # partition. That is, "combined" means not combined widgets, but combined
        # display of destination download stats the user sees

        self.combinedDestinationDisplay = CombinedDestinationDisplay(
            rapidApp=self.rapidApp
        )

        self.combinedDestinationDisplayContainer = QPanelView(
            _("Projected Storage Use"),
        )
        self.combinedDestinationDisplayContainer.addWidget(
            self.combinedDestinationDisplay
        )
        self.combinedDestinationDisplayContainer.setObjectName(
            "combinedDestinationDisplayContainer"
        )

        # Display storage space when photos and videos are being downloaded to different
        # partitions.
        # Also display the file system folder chooser for both destinations.

        self.photoDestinationDisplay = IndividualDestinationDisplay(
            display_type=DisplayFileType.photos, rapidApp=self.rapidApp
        )
        self.photoDestinationWidget = DestComputerWidget(
            object_name="photoDestination",
            deviceRows=self.photoDestinationDisplay.deviceRows,
            fileSystemView=self.rapidApp.photoDestinationFSView,
        )

        self.videoDestinationDisplay = IndividualDestinationDisplay(
            display_type=DisplayFileType.videos, rapidApp=self.rapidApp
        )
        self.videoDestinationWidget = DestComputerWidget(
            object_name="videoDestination",
            deviceRows=self.videoDestinationDisplay.deviceRows,
            fileSystemView=self.rapidApp.videoDestinationFSView,
        )

        self.MAP_DESTINATION_DISPLAY = {
            FileType.photo: self.photoDestinationDisplay,
            FileType.video: self.videoDestinationDisplay,
        }
        self.MAP_DESTINATION_WIDGET = {
            FileType.photo: self.photoDestinationWidget,
            FileType.video: self.videoDestinationWidget,
        }
        self.MAP_DESTINATION_DISPLAY_BY_DISPLAY_TYPE = {
            DisplayFileType.photos_and_videos: self.combinedDestinationDisplay,
            DisplayFileType.photos: self.photoDestinationDisplay,
            DisplayFileType.videos: self.videoDestinationDisplay,
        }

        self.photoDestination.addWidget(self.photoDestinationWidget)
        self.videoDestination.addWidget(self.videoDestinationWidget)

        for widget in (
            self.photoDestinationWidget,
            self.videoDestinationWidget,
            self.combinedDestinationDisplay,
        ):
            self.verticalScrollBarVisible.connect(widget.containerVerticalScrollBar)
        self.horizontalScrollBarVisible.connect(
            self.videoDestinationWidget.containerHorizontalScrollBar
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.splitter.handleWidth())
        layout.addWidget(self.combinedDestinationDisplayContainer)
        layout.addWidget(self.photoDestination)

        self.photoDestinationContainer = QWidget()
        self.photoDestinationContainer.setObjectName("photoDestinationContainer")
        self.photoDestinationContainer.setLayout(layout)

    def setDestinationDisplayVisibilityAndType(self, same_device: bool) -> None:
        self.combinedDestinationDisplayContainer.setVisible(same_device)
        self.photoDestinationDisplay.deviceRows.setUsageVisible(not same_device)
        self.videoDestinationDisplay.deviceRows.setUsageVisible(not same_device)
        if same_device:
            self.photoDestinationDisplay.setNoSpace(False)
            self.videoDestinationDisplay.setNoSpace(False)

    def setMountSpaceAttributes(
        self, display_type: DisplayFileType, storage_space: StorageSpace
    ) -> None:
        self.MAP_DESTINATION_DISPLAY_BY_DISPLAY_TYPE[display_type].setStorage(
            storage_space
        )

    def setUsageAttributes(
        self,
        display_type: DisplayFileType,
        sizeAndNum: DownloadFilesSizeAndNum,
        merge: bool,
    ) -> None:
        self.MAP_DESTINATION_DISPLAY_BY_DISPLAY_TYPE[display_type].setFilesToDownload(
            sizeAndNum, merge, display_type
        )

    def setDestinationPath(self, file_type: FileType, path: str) -> None:
        self.MAP_DESTINATION_DISPLAY[file_type].setPath(path)

    def setDestinationDisplayStatus(
        self, file_type: FileType, status: DeviceDisplayStatus
    ) -> None:
        self.MAP_DESTINATION_DISPLAY[file_type].setStatus(status)

    def setDestinationDisplayNoSpaceStatus(
        self, display_type: DisplayFileType, no_space: bool
    ) -> None:
        self.MAP_DESTINATION_DISPLAY_BY_DISPLAY_TYPE[display_type].setNoSpace(no_space)

    def updateDestinationDisplayUsage(self, display_type: DisplayFileType)-> None:
        self.MAP_DESTINATION_DISPLAY_BY_DISPLAY_TYPE[display_type].updateUsage()
