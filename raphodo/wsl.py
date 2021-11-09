# Copyright (C) 2021 Damon Lynch <damonlynch@gmail.com>

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


__author__ = "Damon Lynch"
__copyright__ = "Copyright 2021, Damon Lynch."

import logging
import os
import re
import shlex
import subprocess
from typing import NamedTuple, Optional, Tuple, Set, List
import webbrowser

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer, Qt
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QGridLayout,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QAbstractScrollArea,
    QDialogButtonBox,
    QPushButton,
    QCheckBox,
    QRadioButton,
    QButtonGroup,
    QAbstractButton,
)

from raphodo.constants import WindowsDriveType
from raphodo.viewutils import translateDialogBoxButtons, CheckBoxDelegate
from raphodo.preferences import Preferences


class WindowsDrive(NamedTuple):
    drive_letter: str
    label: str
    drive_type: WindowsDriveType


class WindowsDriveMount(NamedTuple):
    drive_letter: str
    label: str
    mount_point: str


class WslMountDriveDialog(QDialog):
    def __init__(
        self,
        drives: List[WindowsDriveMount],
        prefs: Preferences,
        parent: "RapidWindow" = None,
    ) -> None:
        super().__init__(parent=parent)

        self.prefs = prefs
        self.driveTable = None  # type: Optional[QTableWidget]

        self.setWindowTitle(_("Removable Windows Drives"))
        layout = QVBoxLayout()
        self.setLayout(layout)
        margin = layout.contentsMargins().left() + 2
        layout.setSpacing(margin)
        layout.setContentsMargins(18, 18, 18, 18)

        self.autoMount = QCheckBox(
            _("Enable automatic mounting of removable Windows drives")
        )
        self.autoMountAll = QRadioButton(
            _("Automatically mount all removable Windows drives")
        )
        self.autoMountManual = QRadioButton(
            _(
                "Only automatically mount removable Windows drives that are "
                "configured below"
            )
        )
        self.autoMountGroup = QButtonGroup()
        self.autoMountGroup.addButton(self.autoMountAll)
        self.autoMountGroup.addButton(self.autoMountManual)
        self.setAutoMountWidgetValues()
        self.autoMount.stateChanged.connect(self.autoMountChanged)
        self.autoMountGroup.buttonToggled.connect(self.autoMountGroupToggled)

        autoMountLayout = QGridLayout()
        autoMountLayout.addWidget(self.autoMount, 0, 0, 1, 2)
        autoMountLayout.addWidget(self.autoMountAll, 1, 1, 1, 1)
        autoMountLayout.addWidget(self.autoMountManual, 2, 1, 1, 1)
        checkbox_width = self.autoMount.style().pixelMetric(QStyle.PM_IndicatorWidth)
        autoMountLayout.setColumnMinimumWidth(0, checkbox_width)

        self.driveTable = QTableWidget(len(drives), 5, self)
        self.driveTable.setHorizontalHeaderLabels(
            [
                _("Mounted"),
                _("Mount Point"),
                _("Drive"),
                _("Automatic Mount"),
                _("Automatic Unmount"),
            ]
        )
        self.driveTable.verticalHeader().setVisible(False)
        delegate = CheckBoxDelegate(None)
        self.driveTable.setItemDelegateForColumn(0, delegate)
        self.driveTable.setItemDelegateForColumn(3, delegate)
        self.driveTable.setItemDelegateForColumn(4, delegate)

        self.driveTable.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
        row = 0
        for drive in drives:
            self.addDriveAtRow(row, drive)
            row += 1

        self.setDriveAutoMountColStates(
            enabled=self.prefs.wsl_automount_removable_drives
        )
        self.driveTable.resizeColumnsToContents()

        buttonBox = QDialogButtonBox(
            QDialogButtonBox.Apply | QDialogButtonBox.Close | QDialogButtonBox.Help
        )
        translateDialogBoxButtons(buttonBox)
        buttonBox.rejected.connect(self.reject)
        self.helpButton = buttonBox.button(QDialogButtonBox.Help)  # type: QPushButton
        self.helpButton.clicked.connect(self.helpButtonClicked)
        self.helpButton.setToolTip(_("Get help online..."))
        self.applyButton = buttonBox.button(QDialogButtonBox.Apply)  # type: QPushButton
        self.applyButton.clicked.connect(self.applyButtonClicked)

        layout.addLayout(autoMountLayout)
        layout.addWidget(self.driveTable)
        layout.addWidget(buttonBox)

    @pyqtSlot()
    def helpButtonClicked(self) -> None:
        webbrowser.open_new_tab("https://damonlynch.net/rapid/documentation/#wslmount")

    @pyqtSlot()
    def applyButtonClicked(self) -> None:
        for drive in self.drives():
            print(f"sudo mount -t drvfs {drive.drive_letter}: {drive.mount_point}")

    @pyqtSlot(int)
    def autoMountChanged(self, state: int) -> None:
        auto_mount = state == Qt.Checked
        self.prefs.wsl_automount_removable_drives = auto_mount
        self.setAutoMountGroupState()

    @pyqtSlot(QAbstractButton, bool)
    def autoMountGroupToggled(self, button: QAbstractButton, checked: bool) -> None:
        self.prefs.wsl_automount_all_removable_drives = self.autoMountAll.isChecked()
        self.driveTable.setEnabled(not self.prefs.wsl_automount_all_removable_drives)

    def setAutoMountWidgetValues(self) -> None:
        self.autoMount.setChecked(self.prefs.wsl_automount_removable_drives)
        self.setAutoMountGroupState()

    def setAutoMountGroupState(self):
        if self.prefs.wsl_automount_removable_drives:
            self.autoMountAll.setEnabled(True)
            self.autoMountManual.setEnabled(True)
            self.autoMountGroup.setExclusive(True)
            self.autoMountAll.setChecked(self.prefs.wsl_automount_all_removable_drives)
            self.autoMountManual.setChecked(
                not self.prefs.wsl_automount_all_removable_drives
            )
            self.setDriveAutoMountColStates(enabled=True)
        else:
            self.autoMountAll.setEnabled(False)
            self.autoMountManual.setEnabled(False)
            self.autoMountGroup.setExclusive(False)
            self.autoMountAll.setChecked(False)
            self.autoMountManual.setChecked(False)
            self.setDriveAutoMountColStates(enabled=False)

    def setDriveAutoMountColStates(self, enabled: bool) -> None:
        if self.driveTable is not None:
            self.driveTable.setEnabled(not self.autoMountAll.isChecked())
            for row in range(self.driveTable.rowCount()):
                for col in (3, 4):
                    item = self.driveTable.item(row, col)
                    if not enabled:
                        item.setCheckState(Qt.Unchecked)
                    self.setItemState(enabled=enabled, item=item)

    def setItemState(self, enabled: bool, item: QTableWidgetItem) -> None:
        if enabled:
            item.setFlags(
                item.flags()
                | Qt.ItemIsEnabled
                | Qt.ItemIsEditable
                | Qt.ItemIsSelectable
            )
        else:
            item.setFlags(
                item.flags()
                & ~Qt.ItemIsEditable
                & ~Qt.ItemIsEnabled
                & ~Qt.ItemIsSelectable
            )

    def addDriveAtRow(self, row: int, drive: WindowsDriveMount):
        auto_mount = self.autoMount.isChecked()
        if drive.mount_point:
            mount_point = drive.mount_point
            is_mounted = True
        else:
            is_mounted = False
            mount_point = wsl_standard_mount_point(drive.drive_letter)
            suffix = ""
            if os.path.ismount(mount_point):
                i = 1
                while os.path.ismount(f"{mount_point}{i}"):
                    i += 1
                suffix = str(i)
            mount_point = f"{mount_point}{suffix}"
        mountedItem = QTableWidgetItem()
        mountedItem.setCheckState(Qt.Checked if is_mounted else Qt.Unchecked)
        mountPointItem = QTableWidgetItem(mount_point)
        windowsDriveItem = QTableWidgetItem(
            f"{drive.label} ({drive.drive_letter.upper()}:)"
        )
        windowsDriveItem.setFlags(
            windowsDriveItem.flags() & ~Qt.ItemIsEditable & ~Qt.ItemIsSelectable
        )
        windowsDriveItem.setData(Qt.UserRole, drive.drive_letter)
        automountItem = QTableWidgetItem()
        autounmountItem = QTableWidgetItem()
        if auto_mount:
            automountItem.setCheckState(Qt.Checked)
            autounmountItem.setCheckState(Qt.Checked)
        else:
            automountItem.setCheckState(Qt.Unchecked)
            autounmountItem.setCheckState(Qt.Unchecked)
            self.setItemState(enabled=False, item=automountItem)
            self.setItemState(enabled=False, item=autounmountItem)

        self.driveTable.setItem(row, 0, mountedItem)
        self.driveTable.setItem(row, 1, mountPointItem)
        self.driveTable.setItem(row, 2, windowsDriveItem)
        self.driveTable.setItem(row, 3, automountItem)
        self.driveTable.setItem(row, 4, autounmountItem)

    def addMount(self, drive: WindowsDriveMount):
        row = self.driveTable.rowCount()
        self.driveTable.insertRow(row)
        logging.debug(
            "Adding drive %s: to Mount Windows Drive table", drive.drive_letter
        )
        self.addDriveAtRow(row, drive)

    def drives(self) -> List[WindowsDriveMount]:
        d = []
        for row in range(self.driveTable.rowCount()):
            item = self.driveTable.item(row, 0)
            if item.checkState() == Qt.Checked:
                d.append(
                    WindowsDriveMount(
                        drive_letter=self.driveTable.item(row, 1).data(Qt.UserRole),
                        label="",
                        mount_point=item.data(Qt.DisplayRole),
                    )
                )
        return d


class WslDrives:
    def __init__(self, rapidApp: "RapidWindow"):
        self.drives = []  # type: List[WindowsDriveMount]
        self.have_unmounted_drive = False
        self.rapidApp = rapidApp
        self.mountDrivesDialog = None  # type: Optional[WslMountDriveDialog]

    def add_drive(self, drive: WindowsDriveMount) -> None:
        self.drives.append(drive)
        if not drive.mount_point:
            self.have_unmounted_drive = True
        if self.mountDrivesDialog:
            self.mountDrivesDialog.addMount(drive)

    def mount_drives(self):
        if self.have_unmounted_drive and self.mountDrivesDialog is None:
            self.mountDrivesDialog = WslMountDriveDialog(
                parent=self.rapidApp,
                drives=self.drives,
                prefs=self.rapidApp.prefs,
            )
            self.mountDrivesDialog.exec()


class WslWindowsRemovableDriveMonitor(QObject):
    """
    Use wmic.exe to periodically probe for removable drives on Windows
    """

    driveMounted = pyqtSignal("PyQt_PyObject")
    driveUnmounted = pyqtSignal(str, str, str)

    def __init__(self) -> None:
        super().__init__()
        self.known_removable_drives = set()

    @pyqtSlot()
    def startMonitor(self) -> None:
        logging.debug("Starting Wsl Removable Drive Monitor")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.probeWindowsDrives)
        self.timer.setTimerType(Qt.CoarseTimer)
        self.timer.setInterval(1500)
        self.probeWindowsDrives()
        self.timer.start()

    @pyqtSlot()
    def stopMonitor(self) -> None:
        logging.debug("Stopping Wsl Removable Drive Monitor")
        self.timer.stop()

    @pyqtSlot()
    def probeWindowsDrives(self) -> None:
        timer_active = self.timer.isActive()
        if timer_active:
            self.timer.stop()
        current_drives = wsl_windows_drives((WindowsDriveType.removable_disk,))
        new_drives = current_drives - self.known_removable_drives
        removed_drives = self.known_removable_drives - current_drives

        drives = []

        for drive in new_drives:
            if wsl_drive_valid(drive.drive_letter):
                mount_point = wsl_mount_point(drive.drive_letter)
                if mount_point:
                    assert os.path.ismount(mount_point)
                drives.append(
                    WindowsDriveMount(
                        drive_letter=drive.drive_letter,
                        label=drive.label or _("Removable Drive"),
                        mount_point=mount_point,
                    )
                )

        if drives:
            self.driveMounted.emit(drives)

        for drive in removed_drives:
            mount_point = wsl_standard_mount_point(drive.drive_letter)
            self.driveUnmounted.emit(
                drive.drive_letter,
                drive.label or _("Removable Drive"),
                mount_point,
            )

        self.known_removable_drives = current_drives
        if timer_active:
            self.timer.start()


def wsl_standard_mount_point(drive_letter: str) -> str:
    return f"/mnt/{drive_letter.lower()}"


def wsl_mount_point(drive_letter: str) -> str:
    """
    Determine the existing mount point of a Windows drive

    :param drive_letter: windows drive letter
    :return: Linux mount point, or "" if it is not mounted
    """

    with open("/proc/mounts") as m:
        mounts = m.read()

    regex = fr"^drvfs (.+?) 9p .+?path={drive_letter.upper()}:\\?;"
    mnt = re.search(regex, mounts, re.MULTILINE)
    if mnt is not None:
        return mnt.group(1)
    else:
        return ""


def wsl_drive_valid(drive_letter: str) -> bool:
    """
    Use the Windows command 'vol' to determine if the drive letter indicates a valid
    drive

    :param drive_letter: drive letter to check in Windows
    :return: True if valid, False otherwise
    """

    try:
        subprocess.check_call(
            shlex.split(f"cmd.exe /c vol {drive_letter}:"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def wsl_windows_drives(
    drive_type_filter: Optional[Tuple[WindowsDriveType]] = None,
) -> Set[WindowsDrive]:

    # wmic is deprecated, but is much, much faster than calling powershell
    output = subprocess.run(
        shlex.split("wmic.exe logicaldisk get deviceid, volumename, drivetype"),
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()
    # Discard first line of output, which is a table header
    drives = set()
    for line in output.split("\n")[1:]:
        if line:  # expect blank lines
            components = line.split(maxsplit=2)

            drive_type = int(components[1])
            # 0 - Unknown
            # 1 - No Root Directory
            # 2 - Removable Disk
            # 3 - Local Disk
            # 4 - Network Drive
            # 5 - Compact Disk
            # 6 - RAM Disk

            if 2 <= drive_type <= 4:
                drive_type = WindowsDriveType(drive_type)
                if drive_type_filter is None or drive_type in drive_type_filter:
                    drive_letter = components[0][0]
                    if len(components) == 3:
                        label = components[2].strip()
                    else:
                        label = ""
                    drives.add(
                        WindowsDrive(
                            drive_letter=drive_letter,
                            label=label,
                            drive_type=drive_type,
                        )
                    )
    return drives


if __name__ == "__main__":
    # Application development test code:

    from PyQt5.QtWidgets import QApplication

    from raphodo.preferences import Preferences

    app = QApplication([])

    app.setOrganizationName("Rapid Photo Downloader")
    app.setOrganizationDomain("damonlynch.net")
    app.setApplicationName("Rapid Photo Downloader")

    prefs = Preferences()

    windows_drives = wsl_windows_drives(
        drive_type_filter=(WindowsDriveType.removable_disk,)
    )

    ddrives = []

    for wdrive in windows_drives:
        if wsl_drive_valid(wdrive.drive_letter):
            mount_point = wsl_mount_point(wdrive.drive_letter)
            if mount_point:
                assert os.path.ismount(mount_point)
                print(f"{wdrive.drive_letter}: is mounted at {mount_point}")
            else:
                print(f"{wdrive.drive_letter}: is not mounted")
            ddrives.append(
                WindowsDriveMount(
                    drive_letter=wdrive.drive_letter,
                    label=wdrive.label or _("Removable Drive"),
                    mount_point=mount_point,
                )
            )

    w = WslMountDriveDialog(drives=ddrives, prefs=prefs)
    w.exec()
