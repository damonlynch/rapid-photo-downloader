# SPDX-FileCopyrightText: Copyright 2017-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Display photo and video destinations
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QSplitter, QVBoxLayout, QWidget

from raphodo.constants import DeviceDisplayStatus
from raphodo.customtypes import DownloadFilesSizeAndNum
from raphodo.internationalisation.install import install_gettext
from raphodo.rpdfile import FileType
from raphodo.storage.storage import StorageSpace
from raphodo.ui.computerview import ComputerWidget
from raphodo.ui.destinationdisplay import (
    DestDisplayType,
    DestinationDisplay,
    DisplayFileType,
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

        self.combinedDestinationDisplay = DestinationDisplay(
            parent=self, rapidApp=self.rapidApp
        )
        self.combinedDestinationDisplay.display_type = DisplayFileType.photos_and_videos
        # Unlike with the individual photo and video destination displays, this will
        # never change:
        self.combinedDestinationDisplay.dest_display_type = DestDisplayType.usage_only

        self.combinedDestinationDisplayContainer = QPanelView(
            _("Projected Storage Use"),
        )
        self.combinedDestinationDisplay.setObjectName("combinedDestinationDisplay")
        self.combinedDestinationDisplayContainer.addWidget(
            self.combinedDestinationDisplay
        )
        self.combinedDestinationDisplayContainer.setObjectName(
            "combinedDestinationDisplayContainer"
        )

        # Display storage space when photos and videos are being downloaded to different
        # partitions.
        # Also display the file system folder chooser for both destinations.

        self.photoDestinationDisplay = DestinationDisplay(
            menu=True, file_type=FileType.photo, parent=self, rapidApp=self.rapidApp
        )
        self.photoDestinationDisplay.display_type = DisplayFileType.photos
        self.photoDestinationDisplay.setObjectName("photoDestinationDisplay")
        self.photoDestinationWidget = ComputerWidget(
            objectName="photoDestination",
            view=self.photoDestinationDisplay,
            fileSystemView=self.rapidApp.photoDestinationFSView,
            select_text=_("Select a destination folder"),
        )

        self.videoDestinationDisplay = DestinationDisplay(
            menu=True, file_type=FileType.video, parent=self, rapidApp=self.rapidApp
        )
        self.videoDestinationDisplay.display_type = DisplayFileType.videos
        self.videoDestinationDisplay.setObjectName("videoDestinationDisplay")
        self.videoDestinationWidget = ComputerWidget(
            objectName="videoDestination",
            view=self.videoDestinationDisplay,
            fileSystemView=self.rapidApp.videoDestinationFSView,
            select_text=_("Select a destination folder"),
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
        dest_display_type = (
            DestDisplayType.folder_only
            if same_device
            else DestDisplayType.folders_and_usage
        )
        self.photoDestinationDisplay.dest_display_type = dest_display_type
        self.videoDestinationDisplay.dest_display_type = dest_display_type

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

    def setSelectDestinationFolderVisible(
        self, file_type: FileType, visible: bool
    ) -> None:
        self.MAP_DESTINATION_WIDGET[file_type].setViewVisible(visible)

    def setDestinationDisplayStatus(
        self, file_type: FileType, status: DeviceDisplayStatus
    ) -> None:
        self.MAP_DESTINATION_DISPLAY[file_type].setStatus(status)

    def setDestinationDisplayNoSpaceStatus(
        self, display_type: DisplayFileType, enough_space: bool
    ) -> None:
        self.MAP_DESTINATION_DISPLAY_BY_DISPLAY_TYPE[
            display_type
        ].enough_space = enough_space

    def updateDestinationView(self, file_type: FileType) -> None:
        self.MAP_DESTINATION_DISPLAY[file_type].update()

    def updateDestinationViewGeometry(self, display_type: DisplayFileType) -> None:
        self.MAP_DESTINATION_DISPLAY_BY_DISPLAY_TYPE[display_type].updateGeometry()
