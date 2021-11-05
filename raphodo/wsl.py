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
__copyright__ = (
    "Copyright 2021, Damon Lynch."
)

import functools
import logging
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import NamedTuple, Optional, Tuple, Set

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer, Qt, QFileSystemWatcher
from showinfm.system.linux import translate_wsl_path

from raphodo.constants import WindowsDriveType


class WslWindowsRemovableDriveMonitor(QObject):
    """
    Use wmic.exe to periodically probe for removable drives on Windows
    """

    driveMounted = pyqtSignal(str, str, str)
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

        for drive in new_drives:
            if wsl_drive_valid(drive.drive_letter):
                mount_point = wsl_mount_point(drive.drive_letter)

                self.driveMounted.emit(
                    drive.drive_letter,
                    drive.label,
                    mount_point if os.path.ismount(mount_point) else ''
                )

        for drive in removed_drives:
            mount_point = wsl_mount_point(drive.drive_letter)
            self.driveUnmounted.emit(
                drive.drive_letter,
                drive.label,
                mount_point if os.path.ismount(mount_point) else ''
            )

        self.known_removable_drives = current_drives
        if timer_active:
            self.timer.start()


def wsl_mount_point(drive_letter: str) -> str:
    return f'/mnt/{drive_letter}'


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


@functools.lru_cache(maxsize=None)
def wsl_env_variable(variable: str) -> str:
    """
    Return Windows environment variable within WSL
    """

    assert variable
    return subprocess.run(
        shlex.split(f"wslvar {variable}"),
        universal_newlines=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()


@functools.lru_cache(maxsize=None)
def wsl_home() -> Path:
    """
    Return user's Windows home directory within WSL
    """

    return Path(
        translate_wsl_path(wsl_env_variable("USERPROFILE"), from_windows_to_wsl=True)
    )


class WindowsDrive(NamedTuple):
    drive_letter: str
    label: str
    drive_type: WindowsDriveType


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


@functools.lru_cache(maxsize=None)
def _wsl_reg_query_standard_folder(folder: str) -> str:
    """
    Use reg query on Windows to query the user's Pictures and Videos folder.

    No error checking.

    :param folder: one of "My Pictures" or "My Video"
    :return: registry value for the folder
    """

    assert folder in ("My Pictures", "My Video")
    query = fr"reg.exe query 'HKEY_CURRENT_USER\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders\' /v '{folder}'"
    output = subprocess.run(
        shlex.split(query),
        stdout=subprocess.PIPE,
        universal_newlines=True,
    ).stdout
    regex = rf"{folder}\s+REG_EXPAND_SZ\s+(.+)\n\n$"
    return re.search(regex, output).group(1)


@functools.lru_cache(maxsize=None)
def wsl_pictures_folder() -> str:
    """
    Query the Windows registry for the location of the user's Pictures folder
    :return: location as a Linux path
    """

    return translate_wsl_path(
        _wsl_reg_query_standard_folder("My Pictures"), from_windows_to_wsl=True
    )


@functools.lru_cache(maxsize=None)
def wsl_videos_folder() -> str:
    """
    Query the Windows registry for the location of the user's Videos folder
    :return: location as a Linux path
    """

    return translate_wsl_path(
        _wsl_reg_query_standard_folder("My Video"), from_windows_to_wsl=True
    )
