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
Display photo and video sources -- Devices and This Computer, as well as the Timeline
"""

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2017-2022, Damon Lynch"

import logging

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QSplitter, QWidget, QVBoxLayout, QScrollArea, QSizePolicy


class SourcePanel(QScrollArea):
    """
    Display Devices and This Computer sources, as well as the timeline
    """
    def __init__(self, parent) -> None:
        super().__init__(parent)
        assert parent is not None
        self.rapidApp = parent
        self.prefs = self.rapidApp.prefs

        self.setObjectName("sourcePanelScrollArea")

        self.sourcePanelWidget = QWidget(parent=self)
        self.sourcePanelWidget.setObjectName("sourcePanelWidget")

        self.splitter = QSplitter(parent=self.sourcePanelWidget)
        self.splitter.setObjectName("sourcePanelSplitter")
        self.splitter.setOrientation(Qt.Vertical)
        self.setWidget(self.sourcePanelWidget)
        self.setWidgetResizable(True)

        self.sourcePanelWidgetLayout = QVBoxLayout()
        self.sourcePanelWidgetLayout.setContentsMargins(0, 0, 0, 0)
        self.sourcePanelWidgetLayout.setSpacing(self.splitter.handleWidth())
        self.sourcePanelWidget.setLayout(self.sourcePanelWidgetLayout)

    def addSourceViews(self) -> None:
        """
        Add source widgets and timeline
        """

        self.rapidApp.deviceToggleView.setSizePolicy(
            QSizePolicy.MinimumExpanding, QSizePolicy.Fixed
        )
        self.sourcePanelWidgetLayout.addWidget(self.rapidApp.deviceToggleView)

        self.splitter.addWidget(self.rapidApp.thisComputerToggleView)
        self.splitter.addWidget(self.rapidApp.temporalProximity)
        self.sourcePanelWidgetLayout.addWidget(self.splitter)

        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
