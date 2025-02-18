# SPDX-FileCopyrightText: Copyright 2016-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from PyQt5.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from raphodo.constants import DeviceState
from raphodo.ui.spinnerwidget import number_spinner_lines, revolutions_per_second


class Spinner(QObject):
    rotate = pyqtSignal(int)

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.rotation_position: int = 0
        self.timer = QTimer(self)
        self.timer.setInterval(
            round(1000 / (number_spinner_lines * revolutions_per_second))
        )
        self.timer.timeout.connect(self.rotateSpinner)
        self.is_spinning = False

    def startSpinners(self):
        self.is_spinning = True

        if not self.timer.isActive():
            logging.debug("Starting spinner timer")
            self.timer.start()
            self.rotation_position = 0

    def stopSpinners(self):
        self.is_spinning = False

        if self.timer.isActive():
            logging.debug("Stopping spinner timer")
            self.timer.stop()
            self.rotation_position = 0

    @pyqtSlot()
    def rotateSpinner(self):
        self.rotation_position += 1
        if self.rotation_position >= number_spinner_lines:
            self.rotation_position = 0

        self.rotate.emit(self.rotation_position)


class SpinnerController:
    def __init__(self, parent) -> None:
        self.spinner = Spinner(parent=parent)
        # scan_id
        self.spinning: set[int] = set()

    def set_spinner_state(self, scan_id: int, device_state: DeviceState) -> None:
        if device_state in (DeviceState.scanning, DeviceState.downloading):
            self.spinning.add(scan_id)
        elif scan_id in self.spinning:
            self.spinning.remove(scan_id)

        should_spin = len(self.spinning) > 0
        if should_spin and not self.spinner.is_spinning:
            self.spinner.startSpinners()
        elif not should_spin and self.spinner.is_spinning:
            self.spinner.stopSpinners()
