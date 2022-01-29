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
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QSplitter, QWidget, QVBoxLayout, QSizePolicy

from raphodo.viewutils import ScrollAreaNoFrame
from raphodo.proximity import TemporalProximityControls


class SourcePanel(ScrollAreaNoFrame):
    """
    Display Devices and This Computer sources, as well as the timeline
    """

    def __init__(self, rapidApp) -> None:
        super().__init__()
        assert rapidApp is not None
        self.rapidApp = rapidApp
        self.prefs = self.rapidApp.prefs

        self.setObjectName("sourcePanelScrollArea")

        self.sourcePanelWidget = QWidget(parent=self)
        self.sourcePanelWidget.setObjectName("sourcePanelWidget")

        self.splitter = QSplitter(parent=self.sourcePanelWidget)
        self.splitter.setObjectName("sourcePanelSplitter")
        self.splitter.setOrientation(Qt.Vertical)
        self.setWidget(self.sourcePanelWidget)
        self.setWidgetResizable(True)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.splitter.handleWidth())
        self.sourcePanelWidget.setLayout(layout)

        self.thisComputerBottomFrameConnection = None
        self.thisComputerAltBottomFrameConnection = None

    def sourcesIsChecked(self) -> bool:
        """
        Determine if download sources are to be visible.
        :return: True if only widget to be displayed is the Timeline, else False
        """

        return self.rapidApp.sourceButton.isChecked()

    def needSplitter(self) -> bool:
        """
        A splitter is used if the Timeline should be showed, and This Computer is
        toggled on and is to be shown.

        :return: True if splitter should be used, else False
        """
        return (
            self.temporalProximityIsChecked()
            and self.thisComputerToggleView.on()
            and self.sourcesIsChecked()
        )

    def temporalProximityIsChecked(self) -> bool:
        """
        Determine if the Timeline is or is going to be visible. Works during startup.
        :return: True if the Timeline is or will be visible, else False
        """

        return self.rapidApp.proximityButton.isChecked()

    def addSourceViews(self) -> None:
        """
        Add source widgets and timeline
        """

        self.deviceToggleView = self.rapidApp.deviceToggleView
        self.deviceView = self.rapidApp.deviceView
        self.thisComputerToggleView = self.rapidApp.thisComputerToggleView
        self.thisComputer = self.rapidApp.thisComputer
        self.temporalProximity = self.rapidApp.temporalProximity

        self.deviceToggleView.setSizePolicy(
            QSizePolicy.MinimumExpanding, QSizePolicy.Fixed
        )
        self.temporalProximity.setSizePolicy(
            QSizePolicy.Preferred, QSizePolicy.MinimumExpanding
        )

        layout = self.sourcePanelWidget.layout()  # type: QVBoxLayout
        layout.addWidget(self.deviceToggleView, 0)

        for widget in (
            self.deviceView,
            self.thisComputer,
            self.thisComputerToggleView.alternateWidget,
        ):
            self.verticalScrollBarVisible.connect(widget.containerVerticalScrollBar)

        for widget in self.temporalProximity.flexiFrameWidgets():
            self.verticalScrollBarVisible.connect(widget.containerVerticalScrollBar)
            self.horizontalScrollBarVisible.connect(widget.containerHorizontalScrollBar)

    def placeWidgets(self) -> None:
        """
        Place This Computer and Timeline widgets in the correct container
        """

        # Scenarios:
        # TL = Timeline (temporal proximity)
        # D = Device Toggle View
        # TC = This Computer Toggle View
        # TL only: TL in panel, D & TC hidden, splitter hidden
        # Sources showing only: D & TC in panel, TL hidden, splitter hidden
        # All showing: D in panel, and:
        #   if TC on, TC and TL in splitter, splitter showing
        #   if TC off, TC and TL in panel, splitter hidden

        layout = self.sourcePanelWidget.layout()  # type: QVBoxLayout
        if not self.needSplitter():
            layout.addWidget(self.thisComputerToggleView)
            layout.addWidget(self.temporalProximity)
            layout.addWidget(self.splitter)
            self.splitter.setVisible(False)
        else:
            layout.addWidget(self.splitter)
            self.splitter.addWidget(self.thisComputerToggleView)
            self.splitter.addWidget(self.temporalProximity)
            for index in range(self.splitter.count()):
                self.splitter.setStretchFactor(index, 1)
                self.splitter.setCollapsible(index, False)
            self.splitter.setVisible(True)

        self.setThisComputerToggleViewSizePolicy()

    def setThisComputerToggleViewSizePolicy(self) -> None:

        if self.thisComputerToggleView.on():
            if self.temporalProximityIsChecked():
                self.thisComputerToggleView.setSizePolicy(
                    QSizePolicy.Preferred, QSizePolicy.Preferred
                )
            else:
                self.thisComputerToggleView.setSizePolicy(
                    QSizePolicy.Preferred, QSizePolicy.MinimumExpanding
                )
        else:
            if self.temporalProximityIsChecked():
                self.thisComputerToggleView.setSizePolicy(
                    QSizePolicy.Preferred, QSizePolicy.Fixed
                )
            else:
                self.thisComputerToggleView.setSizePolicy(
                    QSizePolicy.Preferred, QSizePolicy.MinimumExpanding
                )

    def setSourcesVisible(self, visible: bool) -> None:
        self.deviceToggleView.setVisible(visible)
        self.thisComputerToggleView.setVisible(visible)
        self.splitter.setVisible(self.needSplitter())

    def setThisComputerBottomFrame(self, temporalProximityVisible: bool) -> None:
        """
        Connect or disconnect reaction of This Computer widget to the Scroll Area
        horizontal scroll bar becoming visible or not.

        Idea is to not react when the Timeline is visible, and react when it is hidden,
        which is when the This Computer widget is the bottommost widget.
        :param temporalProximityVisible: whether the timeline is visible
        """

        if temporalProximityVisible:
            if self.thisComputerBottomFrameConnection:
                self.horizontalScrollBarVisible.disconnect(
                    self.thisComputerBottomFrameConnection
                )
                self.thisComputerBottomFrameConnection = None
            if self.thisComputerAltBottomFrameConnection:
                self.horizontalScrollBarVisible.disconnect(
                    self.thisComputerAltBottomFrameConnection
                )
                self.thisComputerAltBottomFrameConnection = None
            # Always show the bottom edge frame, regardless of what the scroll area
            # scrollbar is doing
            self.thisComputer.containerHorizontalScrollBar(False)
            self.thisComputerToggleView.alternateWidget.containerHorizontalScrollBar(
                False
            )
        else:
            if self.thisComputerBottomFrameConnection is None:
                self.thisComputerBottomFrameConnection = (
                    self.horizontalScrollBarVisible.connect(
                        self.thisComputer.containerHorizontalScrollBar
                    )
                )
            if self.thisComputerAltBottomFrameConnection is None:
                self.thisComputerAltBottomFrameConnection = self.horizontalScrollBarVisible.connect(
                    self.thisComputerToggleView.alternateWidget.containerHorizontalScrollBar
                )
            self.thisComputer.containerHorizontalScrollBar(
                self.horizontalScrollBar().isVisible()
            )
            self.thisComputerToggleView.alternateWidget.containerHorizontalScrollBar(
                self.horizontalScrollBar().isVisible()
            )

    def setTemporalProximityVisible(self, visible: bool) -> None:
        self.placeWidgets()
        self.setThisComputerBottomFrame(visible)
        self.temporalProximity.setVisible(visible)
        self.setThisComputerAltWidgetVisible(visible)

    def setThisComputerAltWidgetVisible(self, temporalProximityVisible: bool) -> None:
        if not self.thisComputerToggleView.on():
            self.thisComputerToggleView.alternateWidget.setVisible(
                not temporalProximityVisible
            )

    def setThisComputerState(self) -> None:
        self.placeWidgets()
        self.setThisComputerAltWidgetVisible(self.temporalProximityIsChecked())
        self.setThisComputerToggleViewSizePolicy()


class LeftPanelContainer(QWidget):
    def __init__(
        self,
        sourcePanel: SourcePanel,
        temporalProximityControls: TemporalProximityControls,
    ) -> None:
        super().__init__()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(sourcePanel)
        layout.addWidget(temporalProximityControls)
        self.setLayout(layout)
