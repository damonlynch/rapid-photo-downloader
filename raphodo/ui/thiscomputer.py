# SPDX-FileCopyrightText: Copyright 2016-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
from collections import defaultdict

from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from raphodo.constants import DeviceState, SourceState
from raphodo.devices import Device
from raphodo.ui.computerview import ComputerWidget
from raphodo.ui.devicedisplay import ThisComputerDeviceRows
from raphodo.ui.filebrowse import FileSystemView
from raphodo.ui.source import usage_details


class ThisComputerWidget(ComputerWidget):
    def __init__(
        self,
        deviceRows: ThisComputerDeviceRows,
        fileSystemView: FileSystemView,
        parent: QWidget = None,
    ) -> None:
        super().__init__(
            object_name="thisComputerWidget",
            deviceRows=deviceRows,
            fileSystemView=fileSystemView,
            parent=parent,
        )
        layout: QVBoxLayout = self.layout()
        layout.insertWidget(0, self.deviceRows)

        self.device: Device | None = None
        # TODO may need to change this
        self.percent_complete: dict[int, float] = defaultdict(float)

    def insertSourcePaths(self, paths: list[str]):
        self.deviceRows.headerWidget.insertPaths(paths)
        self.deviceRows.setHeaderToolTip(paths[0])

    def addDevice(self, scan_id: int, device: Device) -> None:
        self.device = device
        has_storage = len(device.storage_space) > 0
        if has_storage:
            storage_space = self.device.get_storage_space()
            details = usage_details(device, storage_space)
            self.deviceRows.setUsage(details)
        self.deviceRows.setUsageVisible(has_storage)
        self.deviceRows.setSourceWidgetVisible(True)
        self.deviceRows.setSourceWidget(SourceState.checkbox)

    def removeDevice(self, scan_id: int) -> None:
        self.device = None
        self.deviceRows.setUsageVisible(False)
        self.deviceRows.setSourceWidgetVisible(False)

    def updateDeviceScan(self, scan_id: int) -> None:
        device = self.device
        storage_space = self.device.get_storage_space()
        details = usage_details(device, storage_space)
        self.deviceRows.setUsage(details)

    def setSpinnerState(self, scan_id: int, state: DeviceState) -> None:
        pass

    def setSourceWidget(self, sourceState: SourceState)-> None:
        self.deviceRows.setSourceWidget(sourceState)

    def setCheckedValue(
        self,
        checked: Qt.CheckState,
        scan_id: int,
        row: int | None = None,
        log_state_change: bool | None = True,
    ) -> None:
        pass

    @pyqtSlot(int)
    def rotate(self, rotation_position: int) -> None:
        self.deviceRows.headerWidget.spinnerWidget.rotation = rotation_position
