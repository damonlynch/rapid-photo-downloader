# Copyright (C) 2017-2022 Damon Lynch <damonlynch@gmail.com>

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
Display photo and video destinations
"""

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2017-2022, Damon Lynch"


from typing import DefaultDict, Optional, Set
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QSplitter, QWidget, QVBoxLayout

from raphodo.ui.computerview import ComputerWidget
from raphodo.ui.destinationdisplay import (
    DestinationDisplay,
    DisplayingFilesOfType,
    DestinationDisplayType,
)
from raphodo.ui.panelview import QPanelView
from raphodo.rpdfile import FileType
from raphodo.thumbnaildisplay import MarkedSummary
from raphodo.ui.viewutils import ScrollAreaNoFrame


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
        self.photoDestinationDisplay.setDestination(self.prefs.photo_download_folder)
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
        self.videoDestinationDisplay.setObjectName("videoDestinationDisplay")
        self.videoDestinationDisplay.setDestination(self.prefs.video_download_folder)
        self.videoDestinationWidget = ComputerWidget(
            objectName="videoDestination",
            view=self.videoDestinationDisplay,
            fileSystemView=self.rapidApp.videoDestinationFSView,
            select_text=_("Select a destination folder"),
        )

        self.photoDestination.addWidget(self.photoDestinationWidget)
        self.videoDestination.addWidget(self.videoDestinationWidget)

        for widget in (self.photoDestinationWidget, self.videoDestinationWidget, self.combinedDestinationDisplay):
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

    def updateDestinationPanelViews(
        self,
        same_dev: bool,
        merge: bool,
        marked_summary: MarkedSummary,
        downloading_to: Optional[DefaultDict[int, Set[FileType]]] = None,
    ) -> bool:
        """
        Updates the header bar and storage space view for the
        photo and video download destinations.

        :return True if destinations required for the download exist,
         and there is sufficient space on them, else False.
        """

        size_photos_marked = marked_summary.size_photos_marked
        size_videos_marked = marked_summary.size_videos_marked
        marked = marked_summary.marked

        destinations_good = True

        if same_dev:
            files_to_display = DisplayingFilesOfType.photos_and_videos
            self.combinedDestinationDisplay.downloading_to = downloading_to
            self.combinedDestinationDisplay.setDestination(
                self.prefs.photo_download_folder
            )
            self.combinedDestinationDisplay.setDownloadAttributes(
                marked=marked,
                photos_size=size_photos_marked,
                videos_size=size_videos_marked,
                files_to_display=files_to_display,
                display_type=DestinationDisplayType.usage_only,
                merge=merge,
            )
            display_type = DestinationDisplayType.folder_only
            self.combinedDestinationDisplayContainer.setVisible(True)
            destinations_good = (
                self.combinedDestinationDisplay.sufficientSpaceAvailable()
            )
        else:
            files_to_display = DisplayingFilesOfType.photos
            display_type = DestinationDisplayType.folders_and_usage
            self.combinedDestinationDisplayContainer.setVisible(False)

        if self.prefs.photo_download_folder:
            self.photoDestinationDisplay.downloading_to = downloading_to
            self.photoDestinationDisplay.setDownloadAttributes(
                marked=marked,
                photos_size=size_photos_marked,
                videos_size=0,
                files_to_display=files_to_display,
                display_type=display_type,
                merge=merge,
            )
            self.photoDestinationWidget.setViewVisible(True)
            if display_type == DestinationDisplayType.folders_and_usage:
                destinations_good = (
                    self.photoDestinationDisplay.sufficientSpaceAvailable()
                )
        else:
            # Photo download folder was invalid or simply not yet set
            self.photoDestinationWidget.setViewVisible(False)
            if size_photos_marked:
                destinations_good = False

        if not same_dev:
            files_to_display = DisplayingFilesOfType.videos
        if self.prefs.video_download_folder:
            self.videoDestinationDisplay.downloading_to = downloading_to
            self.videoDestinationDisplay.setDownloadAttributes(
                marked=marked,
                photos_size=0,
                videos_size=size_videos_marked,
                files_to_display=files_to_display,
                display_type=display_type,
                merge=merge,
            )
            self.videoDestinationWidget.setViewVisible(True)
            if display_type == DestinationDisplayType.folders_and_usage:
                destinations_good = (
                    self.videoDestinationDisplay.sufficientSpaceAvailable()
                    and destinations_good
                )
        else:
            # Video download folder was invalid or simply not yet set
            self.videoDestinationWidget.setViewVisible(False)
            if size_videos_marked:
                destinations_good = False

        return destinations_good
