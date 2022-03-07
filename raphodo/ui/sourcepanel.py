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

from PyQt5.QtCore import Qt, QSettings, pyqtSlot, QPoint
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QSizePolicy, QApplication, QStyle

from raphodo.ui.viewutils import ScrollAreaNoFrame, SourceSplitter
from raphodo.proximity import TemporalProximityControls
from raphodo.constants import TemporalProximityState


class SourcePanel(ScrollAreaNoFrame):
    """
    Display Devices and This Computer sources, as well as the timeline
    """

    def __init__(self, rapidApp) -> None:
        super().__init__(name="sourcePanel", parent=rapidApp)
        assert rapidApp is not None
        self.rapidApp = rapidApp
        self.prefs = self.rapidApp.prefs

        self.settings = QSettings()
        self.settings.beginGroup("MainWindow")

        self.setObjectName("sourcePanelScrollArea")

        self.sourcePanelWidget = QWidget(parent=self)
        self.sourcePanelWidget.setObjectName("sourcePanelWidget")

        self.splitter = SourceSplitter(parent=self.sourcePanelWidget)
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

        self.frame_width = QApplication.style().pixelMetric(QStyle.PM_DefaultFrameWidth)

    def sourcesIsChecked(self) -> bool:
        """
        Determine if download sources are to be visible.
        :return: True if only widget to be displayed is the Timeline, else False
        """

        return self.rapidApp.sourceButton.isChecked() or (
            self.rapidApp.on_startup and self.rapidApp.sourceButtonSetting()
        )

    def temporalProximityIsChecked(self) -> bool:
        """
        Determine if the Timeline is or is going to be visible. Works during startup.
        :return: True if the Timeline is or will be visible, else False
        """

        return self.rapidApp.proximityButton.isChecked() or (
            self.rapidApp.on_startup and self.rapidApp.proximityButtonSetting()
        )

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
            if self.splitter.isVisible():
                self.settings.setValue(
                    "leftPanelSplitterSizes", self.splitter.saveState()
                )
                self.settings.sync()
            layout.addWidget(self.thisComputerToggleView)
            layout.addWidget(self.temporalProximity)
            layout.addWidget(self.splitter)
            self.splitter.setVisible(False)
        else:
            layout.addWidget(self.splitter)
            self.splitter.addWidget(self.thisComputerToggleView)
            self.splitter.addWidget(self.temporalProximity)
            for index in range(self.splitter.count()):
                self.splitter.setCollapsible(index, False)
            self.handle = self.splitter.handle(1)
            self.handle.mousePress.connect(self.splitterHandleMousePress)
            self.handle.mouseReleased.connect(self.splitterHandleMouseRelease)
            self.splitter.setVisible(True)

            splitterSetting = self.settings.value("leftPanelSplitterSizes")
            if splitterSetting is not None:
                if not self.splitter.restoreState(splitterSetting):
                    logging.debug(
                        "Did not restore left splitter sizing because it is no "
                        "longer valid"
                    )

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
        if visible:
            # scroll up to make Devices and This Computer, if necessary
            if self.verticalScrollBar().isVisible():
                auto_scroll = self.prefs.auto_scroll
                if auto_scroll:
                    self.rapidApp.temporalProximityControls.setTimelineThumbnailAutoScroll(
                        on=False
                    )
                self.verticalScrollBar().setValue(self.verticalScrollBar().minimum())
                if auto_scroll:
                    self.rapidApp.temporalProximityControls.setTimelineThumbnailAutoScroll(
                        on=True
                    )

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

    @pyqtSlot()
    def splitterHandleMousePress(self) -> None:
        y = self.handle.pos().y()
        if self.temporalProximity.state == TemporalProximityState.generated:
            self.temporalProximity.temporalProximityView.setMinimumHeight(20)
        else:
            stackedWidget = self.temporalProximity.stackedWidget
            if self.temporalProximity.state == TemporalProximityState.empty:
                self.temporalProximity.explanation.setChildPositions(fixed=True)
            height = max(self.splitter.height(), self.height())
            self.splitter.setFixedHeight(height + stackedWidget.minimumSizeHint().height())
        self.handle.moveSplitter(y)

    @pyqtSlot()
    def splitterHandleMouseRelease(self) -> None:
        y = self.handle.pos().y()
        if self.temporalProximity.state == TemporalProximityState.generated:
            self.temporalProximity.setProximityHeight()
        else:
            self.temporalProximity.explanation.setChildPositions(fixed=False)
            self.temporalProximity.stackedWidget.onCurrentChanged(self.temporalProximity.state)
        self.setSplitterSize()
        self.handle.moveSplitter(y)

    def setSplitterSize(self) -> None:
        if self.needSplitter():
            bottom_frame = (
                0 if self.horizontalScrollBar().isVisible() else self.frame_width
            )

            if self.temporalProximity.state == TemporalProximityState.generated:
                self.splitter.setFixedHeight(
                    + self.splitter.sizes()[0]  # handle position
                    + self.splitter.handleWidth()
                    + self.frame_width
                    + self.temporalProximity.temporalProximityView.contentHeight()
                    + bottom_frame
                )
            else:
                stackedWidget = self.temporalProximity.stackedWidget
                devices_y = abs(self.deviceToggleView.mapTo(self, QPoint(0, 0)).y())
                devices_height = self.splitter.mapTo(self, QPoint(0, 0)).y() + devices_y
                # handle position + handle width:
                y = self.splitter.sizes()[0] + self.splitter.handleWidth()
                min_height = stackedWidget.minimumSizeHint().height()
                if self.height() - devices_height > y + min_height:
                    height = self.height() - y - devices_height
                else:
                    height = min_height

                self.splitter.setFixedHeight(y + height)


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
