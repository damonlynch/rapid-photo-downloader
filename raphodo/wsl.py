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

from collections import OrderedDict, defaultdict
import enum
from pathlib import Path, PurePosixPath
import logging
import os
import re
import shlex
import subprocess
from typing import NamedTuple, Optional, Tuple, Set, List, Dict, DefaultDict
import webbrowser

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer, Qt, QSize
from PyQt5.QtGui import QTextDocument, QShowEvent
from PyQt5.QtWidgets import (
    QSizePolicy,
    QDialog,
    QVBoxLayout,
    QWidget,
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
    QTextBrowser,
    QLabel,
    QMessageBox,
)

from raphodo.constants import WindowsDriveType
from raphodo.prefs.preferences import Preferences, WSLWindowsDrivePrefs
from raphodo.ui.viewutils import (
    translateDialogBoxButtons,
    CheckBoxDelegate,
    standardMessageBox,
)
from raphodo.sudocommand import run_commands_as_sudo, SudoException, SudoExceptionCode
from raphodo.utilities import make_internationalized_list
from raphodo.wslutils import wsl_conf_mnt_location


class WindowsDrive(NamedTuple):
    drive_letter: str
    label: str
    drive_type: WindowsDriveType


class WindowsDriveMount(NamedTuple):
    drive_letter: str
    label: str
    mount_point: str
    drive_type: WindowsDriveType
    system_mounted: bool


class MountTask(enum.Enum):
    create_directory = enum.auto()
    mount_drive = enum.auto()
    unmount_drive = enum.auto()


class MountOp(NamedTuple):
    task: MountTask
    path: Path
    drive: str
    cmd: str


class MountPref(NamedTuple):
    auto_mount: bool
    auto_unmount: bool


class MountOpHumanReadable:
    human_hr = {
        # Translators: see https://damonlynch.net/rapid/documentation/fullsize/wsl/windows-drive-dialog-do-mount.png
        # Please keep the html tags <tt> and </tt>
        MountTask.create_directory: _("Create directory <tt>%(path)s</tt>"),
        # Translators: see https://damonlynch.net/rapid/documentation/fullsize/wsl/windows-drive-dialog-do-mount.png
        # Please keep the html tags <tt> and </tt>
        MountTask.mount_drive: _(
            "Mount drive <tt>%(drive)s:</tt> at <tt>%(path)s</tt>"
        ),
        # Translators: see https://damonlynch.net/rapid/documentation/fullsize/wsl/windows-drive-dialog-do-mount.png
        # This string is not shown in the screenshot, but you get the idea.
        # Please keep the html tags <tt> and </tt>
        MountTask.unmount_drive: _(
            "Unmount drive <tt>%(drive)s:</tt> from <tt>%(path)s</tt>"
        ),
    }

    def mount_task_human_readable(self, op: MountOp) -> str:
        """
        Create human readable versions of mount operations
        :param op: operation to perform and its parameters
        :return: operation in human readable form
        """

        task_hr = self.human_hr[op.task]
        if op.task in (MountTask.unmount_drive, MountTask.mount_drive):
            task_hr = task_hr % {"drive": op.drive, "path": op.path}
        else:
            task_hr = task_hr % {"path": op.path}
        return task_hr


def make_mount_op_cmd(
    task: MountTask,
    drive_letter: str,
    path: Path,
    uid: Optional[int] = None,
    gid: Optional[int] = None,
) -> str:
    """
    Create command to be via subprocess.Popen() call.

    :param task: task to perform
    :param drive_letter: windows drive letter
    :param path: path of mount point, directory or file
    :param uid: user's user id
    :param gid: user's group id
    :return:  the command to run
    """

    if task == MountTask.mount_drive:
        if has_fstab_entry(drive_letter=drive_letter, mount_point=str(path)):
            return f"mount {path}"
        else:
            return rf"mount -t drvfs -o uid={uid},gid={gid},noatime {drive_letter.upper()}:\\ {path}"
    elif task == MountTask.unmount_drive:
        return f"umount {path}"
    elif task == MountTask.create_directory:
        return f"mkdir {path}"
    raise NotImplementedError


def has_fstab_entry(drive_letter: str, mount_point: str) -> bool:
    """
    Determine if the drive letter and mount point are in /etc/fstab

    :param drive_letter: Windows drive letter
    :param mount_point: mount point the drive should be mounted at
    :return: True if located, else False
    """

    with open("/etc/fstab") as f:
        fstab = f.read()
    # strip any extraneous trailing slash
    mount_point = str(PurePosixPath(mount_point))
    regex = rf"^{drive_letter}:\\?\s+{mount_point}/?\s+drvfs"
    m = re.search(regex, fstab, re.IGNORECASE | re.MULTILINE)
    return m is not None


def determine_mount_ops(
    do_mount: bool,
    drive_letter: str,
    mount_point: str,
    uid: int,
    gid: int,
) -> List[MountOp]:
    """
    Generator sequence of operations to mount or unmount a Windows drive

    :param do_mount: Whether to mount or unmount
    :param drive_letter: Windows drive letter
    :param mount_point: Existing or desired mount point. Must not be empty.
    :param uid: User's user ID
    :param gid: User's group ID
    :return: List of operations required to mount or unmount the windows drive
    """

    tasks = []  # type: List[MountOp]
    assert mount_point
    if do_mount:
        mp = Path(mount_point)
        if mp.is_mount():
            return tasks
        if not mp.is_dir():
            tasks.append(
                MountOp(
                    task=MountTask.create_directory,
                    path=mp,
                    drive=drive_letter,
                    cmd=make_mount_op_cmd(
                        task=MountTask.create_directory,
                        drive_letter=drive_letter,
                        path=mp,
                    ),
                )
            )
        tasks.append(
            MountOp(
                task=MountTask.mount_drive,
                path=mp,
                drive=drive_letter,
                cmd=make_mount_op_cmd(
                    task=MountTask.mount_drive,
                    drive_letter=drive_letter,
                    path=mp,
                    uid=uid,
                    gid=gid,
                ),
            )
        )
    else:
        mp = Path(mount_point)
        if mp.is_mount():
            tasks.append(
                MountOp(
                    task=MountTask.unmount_drive,
                    path=mp,
                    drive=drive_letter,
                    cmd=make_mount_op_cmd(
                        task=MountTask.unmount_drive,
                        drive_letter=drive_letter,
                        path=mp,
                    ),
                )
            )

    return tasks


def make_hr_drive_list(drives: List[WindowsDriveMount]) -> str:
    """
    Make a human readable list of drives for use in dialog windows, etc.
    :param drives: the list of drives
    :return: internationalized string
    """

    drive_names = [f"{drive.label} ({drive.drive_letter}:)" for drive in drives]
    drive_names.sort()
    return make_internationalized_list(drive_names)


def make_hr_drive_letter_list(drives: List[WindowsDriveMount]) -> str:
    """
    Return a comma seperated human readable list of drive letters for use in logging,
    etc.
    :param drives: the list of drives
    :return: simple comma seperated string
    """
    return ", ".join(sorted([drive.drive_letter for drive in drives]))


class DoMountOpResult(NamedTuple):
    cancelled: bool
    successes: List[WindowsDriveMount]
    failures: List[WindowsDriveMount]
    no_op: List[WindowsDriveMount]


def do_mount_drives_op(
    drives: List[WindowsDriveMount], pending_ops: OrderedDict, parent, is_do_mount: bool
) -> DoMountOpResult:
    """
    Mount or unmount the Windows drives, prompting the user for the sudo password if
    necessary.

    :param drives: List of drives to mount or unmount
    :param pending_ops: The operations required to mount unmount the drives
    :param parent: Parent window to attach the password entry message box to
    :param is_do_mount: True if mounting the drives, else False
    :return: DoMountOpResult containing results of the operations
    """

    if is_do_mount:
        op_lower = "mount"
        op_cap = "Mount"
    else:
        op_lower = "unmount"
        op_cap = "Unmount"

    info_list = make_hr_drive_list(drives)
    if is_do_mount:
        if len(drives) > 1:
            # Translators: This is part of a title for a dialog box, and is in plural
            # form, where two or more drives will be mounted. This screenshot shows only
            # one drive, but you get the idea:
            # https://damonlynch.net/rapid/documentation/fullsize/wsl/password-prompt-hidden.png
            title = _("Mount drives %s") % info_list
        else:
            # Translators: This is part of a title for a dialog box, and is in singular
            # form, where only one drive will be mounted. This screenshot illustrates:
            # https://damonlynch.net/rapid/documentation/fullsize/wsl/password-prompt-hidden.png
            title = _("Mount drive %s") % info_list
    else:
        if len(drives) > 1:
            # Translators: This is part of a title for a dialog box, and is in plural
            # form, where two or more drives will be unmounted. This screenshot shows
            # only one drive being mounted, but you get the idea:
            # https://damonlynch.net/rapid/documentation/fullsize/wsl/password-prompt-hidden.png
            title = _("Unmount drives %s") % info_list
        else:
            # Translators: This is part of a title for a dialog box, and is in singular
            # form, where only one drive will be unmounted. This screenshot shows a
            # drive being mounted, but you get the idea:
            # https://damonlynch.net/rapid/documentation/fullsize/wsl/password-prompt-hidden.png
            title = _("Unmount drive %s") % info_list
    logging.info("%sing drives %s", op_cap, info_list)

    icon = ":/icons/drive-removable-media.svg"

    no_op = drives.copy()
    failed_drives = []
    failure_stderr = []
    successes = []
    cancelled = False

    for drive, mount_ops in pending_ops.items():
        cmds = [op.cmd for op in mount_ops]
        try:
            results = run_commands_as_sudo(
                cmds=cmds,
                parent=parent,
                title=title,
                icon=icon,
                help_url="https://damonlynch.net/rapid/documentation/#wslsudopassword",
            )
        except SudoException as e:
            assert e.code == SudoExceptionCode.command_cancelled
            logging.debug(
                "%s %s (%s): cancelled by user. Not %sing any remaining drives.",
                op_cap,
                drive.drive_letter,
                drive.label,
                op_lower,
            )
            cancelled = True
            break
        else:
            no_op.remove(drive)
            return_code = results[-1].return_code
            if return_code != 0:
                # a command failed
                logging.error(
                    "Failed to %s %s: (%s) : %s",
                    op_lower,
                    drive.drive_letter.upper(),
                    drive.label,
                    results[-1].stderr,
                )
                failed_drives.append(drive)
                failure_stderr.append(results[-1].stderr)
            else:
                logging.debug(
                    "Successfully %sed %s: (%s)",
                    op_lower,
                    drive.drive_letter.upper(),
                    drive.label,
                )
                successes.append(drive)

    if failed_drives:
        fail_list = make_hr_drive_list(failed_drives)
        failure_messages = "; ".join(failure_stderr)
        if len(failed_drives) > 1:
            if is_do_mount:
                # Translators: this error message is displayed when more than one
                # Windows drive fails to mount within Windows Subsystem for Linux
                message = (
                    _("Sorry, an error occurred when mounting drives %s") % fail_list
                )
            else:
                # Translators: this error message is displayed when more than one
                # Windows drive fails to unmount within Windows Subsystem for Linux
                message = (
                    _("Sorry, an error occurred when unmounting drives %s") % fail_list
                )
        else:
            if is_do_mount:
                # Translators: this error message is displayed when one Windows drive
                # fails to mount within Windows Subsystem for Linux
                message = (
                    _("Sorry, an error occurred when mounting drive %s") % fail_list
                )
            else:
                # Translators: this error message is displayed when one Windows drive
                # fails to unmount within Windows Subsystem for Linux.
                message = (
                    _("Sorry, an error occurred when unmounting drive %s") % fail_list
                )

        msgBox = standardMessageBox(
            message=message,
            standardButtons=QMessageBox.Ok,
            parent=parent,
            rich_text=True,
            iconType=QMessageBox.Warning,
        )
        msgBox.setDetailedText(failure_messages)
        msgBox.exec()

    return DoMountOpResult(
        cancelled=cancelled, successes=successes, failures=failed_drives, no_op=no_op
    )


class WSLWindowsDrivePrefsInterface:
    """
    An interface to the QSettings based method to store whether to auto mount or
    unmount Windows drives.

    Abstraction layer so program preferences do not need to know about implementation
    details in the UI.
    """

    def __init__(self, prefs: Preferences) -> None:
        self.prefs = prefs
        # Keep a copy of the live preferences.
        # If something else changes the prefs, then this will be stale.
        # Currently do not check to verify this is not stale.
        self.drives = prefs.get_wsl_drives()

    def drive_prefs(self, drive: WindowsDriveMount) -> MountPref:
        """
        Get auto mount and auto unmount prefs for this Windows drive.

        :param drive: drive to get prefs for
        :return: Tuple of auto mount and auto unmount
        """

        for d in self.drives:
            if d.drive_letter == drive.drive_letter and d.label == drive.label:
                return MountPref(auto_mount=d.auto_mount, auto_unmount=d.auto_unmount)
        return MountPref(auto_mount=False, auto_unmount=False)

    def set_prefs(
        self, drive: WindowsDriveMount, auto_mount: bool, auto_unmount: bool
    ) -> None:
        """
        Set auto mount and auto unmount prefs for this Windows drive.

        :param drive: drive to get prefs for
        :param auto_mount: auto mount pref
        :param auto_unmount: auto unmount pref
        """

        if auto_mount or auto_unmount:
            updated_pref = WSLWindowsDrivePrefs(
                drive_letter=drive.drive_letter,
                label=drive.label,
                auto_mount=auto_mount,
                auto_unmount=auto_unmount,
            )
        else:
            # Filter out default value of False, False
            updated_pref = None

        updated_drives_prefs = [
            d
            for d in self.drives
            if d.drive_letter != drive.drive_letter or d.label != drive.label
        ]
        if updated_pref is not None:
            updated_drives_prefs.append(updated_pref)
        self.drives = updated_drives_prefs
        self.prefs.set_wsl_drives(drives=self.drives)


class PendingOpsBox(QTextBrowser):
    def __init__(self, parent) -> None:
        super().__init__(parent=parent)
        self.setReadOnly(True)
        self.setMinimumHeight(self.fontMetrics().height() * 4)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)
        sheet = """
        tt {
            font-weight: bold;
            color: gray;
        }
        """
        document = self.document()  # type: QTextDocument
        document.setDefaultStyleSheet(sheet)

    def sizeHint(self) -> QSize:
        return QSize(self.minimumWidth(), self.minimumHeight())


class WslMountDriveDialog(QDialog):
    """
    Dialog window containing Windows drives and mounting options.

    Deals with "System" drives (drives mounted by WSL before this program was run),
    and "User" drives (drives mounted by the user in this program).
    """

    def __init__(
        self,
        drives: List[WindowsDriveMount],
        prefs: Preferences,
        windrive_prefs: WSLWindowsDrivePrefsInterface,
        wsl_mount_root: Path,
        parent: "RapidWindow" = None,
    ) -> None:
        """
        Open the dialog window to show Windows drive mounts

        :param drives: List of Windows drives detected on the system
        :param prefs: main program preferences
        :param windrive_prefs: Interface to the windows drives preferences
        :param wsl_mount_root: where WSL mounts Windows drives
        :param parent: RapidApp main window
        """

        super().__init__(parent=parent)
        if parent:
            self.wsldrives = parent.wslDrives

        self.prefs = prefs
        self.windrive_prefs = windrive_prefs
        self.wsl_mount_root = wsl_mount_root

        # drives where the user should be prompted whether to mount these drives
        # after the dialog is closed
        self.prompt_to_mount_drives = []  # type: List[WindowsDriveMount]

        self.driveTable = None  # type: Optional[QTableWidget]

        #  OrderedDict[drive: List[MountOp]]
        self.pending_mount_ops = OrderedDict()
        self.pending_unmount_ops = OrderedDict()

        self.uid = os.getuid()
        self.gid = os.getgid()

        self.make_mount_op_hr = MountOpHumanReadable()

        # Translators: see https://damonlynch.net/rapid/documentation/fullsize/wsl/windows-drive-dialog.png
        self.setWindowTitle(_("Windows Drives"))

        # Translators: see https://damonlynch.net/rapid/documentation/fullsize/wsl/windows-drive-dialog.png
        self.autoMountCheckBox = QCheckBox(
            _("Enable automatic mounting of Windows drives")
        )
        # Translators: see https://damonlynch.net/rapid/documentation/fullsize/wsl/windows-drive-dialog.png
        self.autoMountAllButton = QRadioButton(
            _("Automatically mount all Windows drives")
        )
        # Translators: see https://damonlynch.net/rapid/documentation/fullsize/wsl/windows-drive-dialog.png
        self.autoMountManualButton = QRadioButton(
            _("Only automatically mount Windows drives that are configured below")
        )
        self.autoMountGroup = QButtonGroup()
        self.autoMountGroup.addButton(self.autoMountAllButton)
        self.autoMountGroup.addButton(self.autoMountManualButton)
        self.setAutoMountWidgetValues()
        self.autoMountCheckBox.stateChanged.connect(self.autoMountChanged)
        self.autoMountGroup.buttonToggled.connect(self.autoMountGroupToggled)

        autoMountLayout = QGridLayout()
        autoMountLayout.addWidget(self.autoMountCheckBox, 0, 0, 1, 2)
        autoMountLayout.addWidget(self.autoMountAllButton, 1, 1, 1, 1)
        autoMountLayout.addWidget(self.autoMountManualButton, 2, 1, 1, 1)
        checkbox_width = self.autoMountCheckBox.style().pixelMetric(
            QStyle.PM_IndicatorWidth
        )
        autoMountLayout.setColumnMinimumWidth(0, checkbox_width)
        autoMountLayout.setVerticalSpacing(8)
        autoMountLayout.setContentsMargins(0, 0, 0, 8)

        self.driveTable = QTableWidget(len(drives), 6, self)
        self.driveTable.setHorizontalHeaderLabels(
            [
                # Translators: see https://damonlynch.net/rapid/documentation/fullsize/wsl/windows-drive-dialog.png
                _("User Mounted"),
                # Translators: see https://damonlynch.net/rapid/documentation/fullsize/wsl/windows-drive-dialog.png
                _("System Mounted"),
                # Translators: see https://damonlynch.net/rapid/documentation/fullsize/wsl/windows-drive-dialog.png
                _("Drive"),
                # Translators: see https://damonlynch.net/rapid/documentation/fullsize/wsl/windows-drive-dialog.png
                _("Mount Point"),
                # Translators: see https://damonlynch.net/rapid/documentation/fullsize/wsl/windows-drive-dialog.png
                _("Automatic Mount"),
                # Translators: see https://damonlynch.net/rapid/documentation/fullsize/wsl/windows-drive-dialog.png
                _("Automatic Unmount at Exit"),
            ]
        )
        self.userMountCol = 0
        self.systemMountCol = 1
        self.mountPointCol = 3
        self.windowsDriveCol = 2
        self.autoMountCol = 4
        self.autoUnmountCol = 5

        self.driveTable.verticalHeader().setVisible(False)
        delegate = CheckBoxDelegate(None)
        for col in (
            self.userMountCol,
            self.systemMountCol,
            self.autoMountCol,
            self.autoUnmountCol,
        ):
            self.driveTable.setItemDelegateForColumn(col, delegate)

        self.driveTable.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
        row = 0
        for drive in drives:
            self.addDriveAtRow(row, drive)
            row += 1

        self.setAllDriveAutoMountColStates()
        self.driveTable.resizeColumnsToContents()
        self.driveTable.sortItems(self.mountPointCol)
        self.driveTable.itemChanged.connect(self.driveTableItemChanged)
        self.driveTable.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.driveTable.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Translators: see https://damonlynch.net/rapid/documentation/fullsize/wsl/windows-drive-dialog.png
        self.pendingOpsLabel = QLabel(_("Pending Operations:"))
        self.pendingOpsBox = PendingOpsBox(self)

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
        # Translators: see https://damonlynch.net/rapid/documentation/fullsize/wsl/windows-drive-dialog.png
        self.applyButton.setText(_("&Apply Pending Operations"))

        layout = QVBoxLayout()
        layout.setSpacing(18)
        layout.setContentsMargins(18, 18, 18, 18)
        # For autoMount column 0 size to be correctly set, first add it to a widget:
        autoMount = QWidget()
        autoMount.setLayout(autoMountLayout)
        layout.addWidget(autoMount)
        layout.addWidget(self.driveTable)
        layout.addWidget(self.pendingOpsLabel)
        layout.addWidget(self.pendingOpsBox)
        layout.addWidget(buttonBox)
        self.setLayout(layout)
        self.setApplyButtonState()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.calculateScrollBarAppearance()

    def calculateScrollBarAppearance(self):
        """
        If table has grown so big it needs scroll bars, add them
        """

        screen_size = self.screen().size()
        height = screen_size.height()
        width = screen_size.width()
        if self.driveTable.height() > height * 0.66:
            self.driveTable.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        if self.driveTable.width() > width * 0.85:
            self.driveTable.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.adjustSize()

    @pyqtSlot()
    def helpButtonClicked(self) -> None:
        webbrowser.open_new_tab("https://damonlynch.net/rapid/documentation/#wslmount")

    def updateUserMountedCheckState(
        self, drive_letter: str, check_state: Qt.CheckState
    ) -> None:
        """
        Set the user mounted check state for a drive
        :param drive_letter: drive letter of the drive to set
        :param check_state: new check state
        """

        for row in range(self.driveTable.rowCount()):
            item = self.driveTable.item(row, self.userMountCol)
            drive = item.data(Qt.UserRole)  # type: WindowsDriveMount
            if drive.drive_letter == drive_letter:
                item.setCheckState(check_state)
                break

    def updateDriveDataInTable(self, new_drive: WindowsDriveMount) -> None:
        """
        Update the user data for the table row
        :param new_drive: new data to set
        """

        for row in range(self.driveTable.rowCount()):
            item = self.driveTable.item(row, self.userMountCol)
            drive = item.data(Qt.UserRole)  # type: WindowsDriveMount
            if drive.drive_letter == new_drive.drive_letter:
                item.setData(Qt.UserRole, new_drive)
                break

    @pyqtSlot()
    def applyButtonClicked(self) -> None:
        """ "
        Initiate mount or unmount operations after the user clicked the apply button
        """

        logging.debug("Applying WSL mount ops")
        cancelled = False
        check = []
        uncheck = []
        mount_successes = []
        unmount_successes = []

        if self.pending_mount_ops:
            drives = list(self.pending_mount_ops.keys())
            result = do_mount_drives_op(
                drives=drives,
                pending_ops=self.pending_mount_ops,
                parent=self,
                is_do_mount=True,
            )
            mount_successes = result.successes
            if result.no_op or result.failures:
                if result.failures:
                    logging.debug("Not all drives mounted successfully")
                uncheck = result.no_op + result.failures
            if result.cancelled:
                cancelled = True

        if self.pending_unmount_ops and not cancelled:
            drives = list(self.pending_unmount_ops.keys())
            result = do_mount_drives_op(
                drives=drives,
                pending_ops=self.pending_unmount_ops,
                parent=self,
                is_do_mount=False,
            )
            unmount_successes = result.successes
            if result.no_op or result.failures:
                if result.failures:
                    logging.debug("Not all drives unmounted successfully")
                check = result.no_op + result.failures

        # block signal being emitted when programmatically changing checkbox states
        blocked = self.driveTable.blockSignals(True)

        mount_points = {}

        for drive in mount_successes:
            mount_point = wsl_standard_mount_point(
                self.wsl_mount_root, drive.drive_letter
            )
            mount_points[drive.drive_letter] = mount_point
            new_drive = drive._replace(mount_point=mount_point)
            self.updateDriveDataInTable(new_drive=new_drive)
        for drive in unmount_successes:
            new_drive = drive._replace(mount_point="")
            self.updateDriveDataInTable(new_drive=new_drive)

        for drive in uncheck:
            self.updateUserMountedCheckState(drive.drive_letter, Qt.Unchecked)
        for drive in check:
            self.updateUserMountedCheckState(drive.drive_letter, Qt.Checked)

        # restore signal state
        self.driveTable.blockSignals(blocked)

        if mount_successes:
            self.wsldrives.updateDriveStatePostMount(
                mounted=mount_successes, mount_points=mount_points
            )
        if unmount_successes:
            self.wsldrives.updateDriveStatePostUnmount(unmounted=unmount_successes)

        self.pending_mount_ops.clear()
        self.pending_unmount_ops.clear()
        self.updatePendingOps()
        self.setApplyButtonState()

    @pyqtSlot(QTableWidgetItem)
    def driveTableItemChanged(self, item: QTableWidgetItem) -> None:
        """
        Respond to the user checking or unchecking a checkbox in the table of drives

        :param item: the table item checked or unchecked
        """

        column = item.column()
        if column == self.userMountCol:
            drive = item.data(Qt.UserRole)  # type: WindowsDriveMount
            do_mount = item.checkState() == Qt.Checked
            if do_mount:
                assert drive.mount_point == ""
                mount_point = wsl_standard_mount_point(
                    root=self.wsl_mount_root, drive_letter=drive.drive_letter
                )
            else:
                mount_point = drive.mount_point
            if mount_point:
                tasks = determine_mount_ops(
                    do_mount=do_mount,
                    drive_letter=drive.drive_letter,
                    mount_point=mount_point,
                    uid=self.uid,
                    gid=self.gid,
                )
            else:
                # User has likely changed their mind about mounting a drive
                tasks = []
            if tasks:
                if do_mount:
                    self.pending_mount_ops[drive] = tasks
                else:
                    self.pending_unmount_ops[drive] = tasks
            else:
                del self.pending_mount_ops[drive]
            self.updatePendingOps()
            self.setApplyButtonState()
        elif not self.prefs.wsl_automount_all_removable_drives and column in (
            self.autoMountCol,
            self.autoUnmountCol,
        ):
            row = item.row()
            drive = self.driveTable.item(row, self.userMountCol).data(
                Qt.UserRole
            )  # type: WindowsDriveMount
            if column == self.autoUnmountCol:
                auto_mount = (
                    self.driveTable.item(row, self.autoMountCol).checkState()
                    == Qt.Checked
                )
                auto_unmount = item.checkState() == Qt.Checked
            else:
                auto_mount = item.checkState() == Qt.Checked
                auto_unmount = (
                    self.driveTable.item(row, self.autoUnmountCol).checkState()
                    == Qt.Checked
                )
                if auto_mount:
                    self.prompt_to_mount_drives.append(drive)
                elif drive in self.prompt_to_mount_drives:
                    self.prompt_to_mount_drives.remove(drive)
            self.windrive_prefs.set_prefs(drive, auto_mount, auto_unmount)

    def updatePendingOps(self) -> None:
        """
        Update the list of pending operations displayed to the user at the bottom of the
        Windows Drive Mount window
        """
        self.pendingOpsBox.clear()
        lines = []
        for mount_ops in self.pending_mount_ops.values():
            for op in mount_ops:
                lines.append(self.make_mount_op_hr.mount_task_human_readable(op))
        for mount_ops in self.pending_unmount_ops.values():
            for op in mount_ops:
                lines.append(self.make_mount_op_hr.mount_task_human_readable(op))

        text = "<br>".join(lines)
        self.pendingOpsBox.setHtml(text)

    def setApplyButtonState(self) -> None:
        """
        Change the apply button state depending on whether there are any pending
        mount or unmount operations
        """

        enabled = len(self.pending_mount_ops) > 0 or len(self.pending_unmount_ops) > 0
        self.applyButton.setEnabled(enabled)

    @pyqtSlot(int)
    def autoMountChanged(self, state: int) -> None:
        """
        Respond to the user checking or unchecking the automatically mount Windows
        drives option, adjusting the preferences and setting other control states

        :param state: Whether the new state is checked or unchecked
        """

        auto_mount = state == Qt.Checked
        self.prefs.wsl_automount_removable_drives = auto_mount
        self.setAutoMountGroupState()

    @pyqtSlot(QAbstractButton, bool)
    def autoMountGroupToggled(self, button: QAbstractButton, checked: bool) -> None:
        """
        Respond to the user checking or unchecking one of the order auto mount radio
        buttons

        :param button: Radio button modified
        :param checked: Whether the button was checked or unchecked
        """

        automount_all = self.autoMountAllButton.isChecked()
        self.prefs.wsl_automount_all_removable_drives = automount_all
        self.driveTable.setEnabled(not self.prefs.wsl_automount_all_removable_drives)
        self.setAutoMountGroupState()
        if automount_all:
            self.driveTable.selectionModel().clearSelection()

    def setAutoMountWidgetValues(self) -> None:
        """
        Set values for Auto mount and other controls based on program preferences
        """
        self.autoMountCheckBox.setChecked(self.prefs.wsl_automount_removable_drives)
        self.setAutoMountGroupState()

    def setAutoMountGroupState(self):
        """
        Set control states of controls depending on program preferences, including
        whether they are enabled or not
        """

        if self.prefs.wsl_automount_removable_drives:
            self.autoMountAllButton.setEnabled(True)
            self.autoMountManualButton.setEnabled(True)
            self.autoMountGroup.setExclusive(True)
            self.autoMountAllButton.setChecked(
                self.prefs.wsl_automount_all_removable_drives
            )
            self.autoMountManualButton.setChecked(
                not self.prefs.wsl_automount_all_removable_drives
            )
            self.setAllDriveAutoMountColStates()
        else:
            self.autoMountAllButton.setEnabled(False)
            self.autoMountManualButton.setEnabled(False)
            self.autoMountGroup.setExclusive(False)
            self.autoMountAllButton.setChecked(False)
            self.autoMountManualButton.setChecked(False)
            self.setAllDriveAutoMountColStates()

    def setAllDriveAutoMountColStates(self) -> None:
        """
        For each Windows drive in the drive table, enable or disable checkboxes and set
        their values
        """

        if self.driveTable is not None:
            # Set table state here rather than in setAutoMountGroupState() because
            # it does not exist early in window init
            self.driveTable.setEnabled(
                not self.prefs.wsl_automount_all_removable_drives
            )

            for row in range(self.driveTable.rowCount()):
                self.setDriveAutoMountColStates(row=row)

    def setDriveAutoMountColStates(self, row: int) -> bool:
        """
        For a single row in the drive table, enable or disable checkboxes and set
        their values
        :param row: the row to act on
        :return True if drive is not system mounted and it should be automatically
         mounted, else False
        """

        drive = self.driveTable.item(row, self.userMountCol).data(
            Qt.UserRole
        )  # type: WindowsDriveMount

        auto_mount = False

        if not drive.system_mounted:
            if not self.prefs.wsl_automount_removable_drives:
                auto_mount = auto_unmount = False
            elif self.prefs.wsl_automount_all_removable_drives:
                auto_mount = auto_unmount = True
            else:
                auto_mount, auto_unmount = self.windrive_prefs.drive_prefs(drive=drive)
            autoMountItem = self.driveTable.item(row, self.autoMountCol)
            autoUnmountItem = self.driveTable.item(row, self.autoUnmountCol)

            # block signal being emitted when programmatically changing checkbox
            # states
            blocked = self.driveTable.blockSignals(True)
            for item, value in (
                (autoMountItem, auto_mount),
                (autoUnmountItem, auto_unmount),
            ):
                item.setCheckState(Qt.Checked if value else Qt.Unchecked)
                self.setItemState(
                    enabled=self.prefs.wsl_automount_removable_drives,
                    item=item,
                )
            # restore signal state
            self.driveTable.blockSignals(blocked)

        return auto_mount

    @staticmethod
    def setItemState(enabled: bool, item: QTableWidgetItem) -> None:
        """
        Enable or disable an individual check box in the Windows drive mount table
        :param enabled: Whether the control should be enabled or disabled
        :param item: The item to apply the state to
        """

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
        """
        Add new windows mount drive to the drive table at the row indicated

        :param row: row to add the drive to
        :param drive: the drive to add
        """

        auto_mount = self.autoMountCheckBox.isChecked()
        auto_mount_all = self.autoMountAllButton.isChecked()

        if drive.mount_point:
            mount_point = drive.mount_point
            is_mounted = True
        else:
            is_mounted = False

        system_mounted = drive.system_mounted
        user_mounted = not system_mounted

        if not is_mounted:
            mount_point = wsl_standard_mount_point(
                self.wsl_mount_root, drive.drive_letter
            )

        # User Mounted Column
        userMountedItem = QTableWidgetItem()
        checked = user_mounted and is_mounted
        userMountedItem.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        if system_mounted:
            self.setItemState(enabled=False, item=userMountedItem)
        # Store the drive data in the first column
        userMountedItem.setData(Qt.UserRole, drive)

        # System Mounted Columns
        systemMountItem = QTableWidgetItem()
        systemMountItem.setCheckState(Qt.Checked if system_mounted else Qt.Unchecked)
        systemMountItem.setFlags(
            systemMountItem.flags() & ~Qt.ItemIsEditable & ~Qt.ItemIsSelectable
        )

        # Mount Point Column
        mountPointItem = QTableWidgetItem(mount_point)
        mountPointItem.setFlags(
            mountPointItem.flags() & ~Qt.ItemIsEditable & ~Qt.ItemIsSelectable
        )

        # Windows Drive Column
        windowsDriveItem = QTableWidgetItem(
            f"{drive.label} ({drive.drive_letter.upper()}:)"
        )
        windowsDriveItem.setFlags(
            windowsDriveItem.flags() & ~Qt.ItemIsEditable & ~Qt.ItemIsSelectable
        )

        # Automount and Auto Unmount at Exit Columns
        automountItem = QTableWidgetItem()
        autounmountItem = QTableWidgetItem()
        if system_mounted:
            automountItem.setCheckState(Qt.Checked)
            autounmountItem.setCheckState(Qt.Unchecked)
            self.setItemState(enabled=False, item=automountItem)
            self.setItemState(enabled=False, item=autounmountItem)
        elif auto_mount:
            if auto_mount_all:
                automountItem.setCheckState(Qt.Checked)
                autounmountItem.setCheckState(Qt.Checked)
        else:
            automountItem.setCheckState(Qt.Unchecked)
            autounmountItem.setCheckState(Qt.Unchecked)
            self.setItemState(enabled=False, item=automountItem)
            self.setItemState(enabled=False, item=autounmountItem)

        self.driveTable.setItem(row, self.userMountCol, userMountedItem)
        self.driveTable.setItem(row, self.systemMountCol, systemMountItem)
        self.driveTable.setItem(row, self.mountPointCol, mountPointItem)
        self.driveTable.setItem(row, self.windowsDriveCol, windowsDriveItem)
        self.driveTable.setItem(row, self.autoMountCol, automountItem)
        self.driveTable.setItem(row, self.autoUnmountCol, autounmountItem)

    def addMount(self, drive: WindowsDriveMount) -> None:
        """
        Add a new Windows drive mount to the table
        This drive has been added when the dialog is already showing
        :param drive: drive to add
        """

        row = self.driveTable.rowCount()
        self.driveTable.insertRow(row)
        logging.debug(
            "Adding drive %s: to Mount Windows Drive table", drive.drive_letter
        )
        # block signal being emitted when programmatically changing checkbox
        # states
        blocked = self.driveTable.blockSignals(True)
        self.addDriveAtRow(row, drive)
        auto_mount = self.setDriveAutoMountColStates(row=row)
        if auto_mount:
            self.prompt_to_mount_drives.append(drive)
        self.driveTable.sortItems(self.mountPointCol)
        # restore signal state
        self.driveTable.blockSignals(blocked)
        self.calculateScrollBarAppearance()

    def removeMount(self, drive: WindowsDriveMount) -> None:
        """
        Remove a Windows drive from the table
        :param drive: Drive to remove
        """

        for row in range(self.driveTable.rowCount()):
            d = self.driveTable.item(row, 0).data(Qt.UserRole)
            if d == drive:
                logging.debug(
                    "Removing drive %s: from Mount Windows Drive table",
                    drive.drive_letter,
                )
                self.driveTable.removeRow(row)
                if drive in self.prompt_to_mount_drives:
                    self.prompt_to_mount_drives.remove(drive)
                break


class WslDrives(QObject):
    """
    Manages Windows drive mounts under the Window Subsystem for Linux
    """

    driveMounted = pyqtSignal("PyQt_PyObject")
    driveUnmounted = pyqtSignal("PyQt_PyObject")

    def __init__(self, rapidApp: "RapidWindow") -> None:
        super().__init__(parent=rapidApp)

        self.drives = []  # type: List[WindowsDriveMount]
        self.mount_points = defaultdict(
            list
        )  # type: DefaultDict[str, List[WindowsDriveMount]]
        self.make_mount_drive_attempt = False
        self.rapidApp = rapidApp
        self.prefs = self.rapidApp.prefs
        self.windrive_prefs = WSLWindowsDrivePrefsInterface(prefs=self.prefs)
        self.mountDrivesDialog = None  # type: Optional[WslMountDriveDialog]
        self.uid = os.getuid()
        self.gid = os.getgid()
        self.wsl_mount_root = Path(wsl_conf_mnt_location())

    def addDrive(self, drive: WindowsDriveMount) -> None:
        """
        Add a new windows drive, which may be already mounted or not

        :param drive: the drive to add
        """

        self.drives.append(drive)
        self.mount_points[drive.mount_point].append(drive)
        if not drive.mount_point:
            self.make_mount_drive_attempt = True
        if self.mountDrivesDialog:
            self.mountDrivesDialog.addMount(drive)

    def removeDrive(self, drive: WindowsDriveMount) -> None:
        """
        Remove a windows drive

        :param drive: the drive to remove
        """

        logging.debug("Removing drive %s from WSL drives", drive)
        self.drives.remove(drive)
        self.mount_points[drive.mount_point].remove(drive)
        self.logDrives()

        if self.mountDrivesDialog:
            self.mountDrivesDialog.removeMount(drive)

    def knownMountPoint(self, mount_point: str) -> bool:
        if mount_point:
            return mount_point in self.mount_points
        return False

    def driveType(self, mount_point: str) -> WindowsDriveType:
        """
        Drive type as reported by Windows

        :param mount_point: mount point of the volume
        :return: Drive type as reported by Windows
        """

        try:
            return self.mount_points[mount_point][0].drive_type
        except Exception:
            logging.error("Mount point %s is an unknown WSL drive", mount_point)
            return WindowsDriveType.local_disk

    def displayName(self, mount_point: str) -> str:
        """
        Volume name and drive letter for the mount point

        If the volume name is currently unknown, return simply the drive letter
        and a colon, e.g. C: or D:

        :param mount_point: mount point of the volume
        :return: volume name and drive letter as reported by Windows
        """

        if mount_point in self.mount_points:
            drive = self.mount_points[mount_point][0]
            return f"{drive.label} ({drive.drive_letter.upper()}:)"
        else:
            return f"{Path(mount_point).name.upper()}:"

    def driveProperties(self, mount_point: str) -> Tuple[List[str], bool]:
        assert mount_point != ""
        drive = self.mount_points[mount_point][0]
        return (
            self.iconNames(drive.drive_type),
            drive.drive_type == WindowsDriveType.removable_disk,
        )

    @staticmethod
    def iconNames(drive_type: WindowsDriveType) -> List[str]:
        """
        Return a list of icons that match the drive type
        :param drive_type:
        :return:
        """

        if drive_type == WindowsDriveType.removable_disk:
            return [
                "drive-removable-media-usb",
                "drive-removable-media",
                "drive-removable",
                "drive",
                "drive-removable-media-usb-symbolic",
                "drive-removable-media-symbolic",
                "drive-removable-symbolic",
                "drive-symbolic",
            ]
        elif drive_type == WindowsDriveType.local_disk:
            return ["folder", "folder-symbolic"]
        else:
            return [
                "folder-remote",
                "folder",
                "folder-remote-symbolic",
                "folder-symbolic",
            ]

    def mountDrives(self) -> None:
        """
        Mount all drives that should be automatically mounted, and prompt the user for
        drives that are not automatically mounted
        """

        if self.mountDrivesDialog is not None:
            # given the dialog is active, prompt to mount any unmounted auto
            # mount drives when the user has closed the dialog
            return

        if self.make_mount_drive_attempt:
            unmounted_drives = self.mount_points[""]

            drives_to_mount = []
            show_dialog = False
            for drive in unmounted_drives:
                if self.prefs.wsl_automount_removable_drives:
                    if self.prefs.wsl_automount_all_removable_drives:
                        drives_to_mount.append(drive)
                    else:
                        if self.windrive_prefs.drive_prefs(drive).auto_mount:
                            drives_to_mount.append(drive)
                        else:
                            show_dialog = True

            if drives_to_mount:
                self.doMountDrives(drives=drives_to_mount)

            if show_dialog and self.mountDrivesDialog is None:
                self.showMountDrivesDialog(validate_drive_state=False)

        self.make_mount_drive_attempt = False

    def unmountDrives(
        self, at_exit: Optional[bool] = False, mount_point: Optional[str] = ""
    ) -> bool:
        """
        Unmount drives that should be automatically unmounted at program exit, or when
        a device has been downloaded from.

        :param at_exit: True if this is being called as the program is exiting, else
        False
        :param mount_point: if at exit is false, a mount point must be specified. If so,
         only its mount will be unmounted.
        :return: True if the user did not cancel the unmount operation when prompted to
        enter a password
        """

        auto_unmount_drives = []  # type: List[WindowsDriveMount]
        if at_exit:
            if self.prefs.wsl_automount_removable_drives:
                for drive in self.drives:
                    if drive.mount_point and not drive.system_mounted:
                        if (
                            self.prefs.wsl_automount_all_removable_drives
                            or self.windrive_prefs.drive_prefs(drive=drive).auto_unmount
                        ):
                            auto_unmount_drives.append(drive)
        else:
            assert mount_point
            auto_unmount_drives.append(self.mount_points[mount_point][0])

        if auto_unmount_drives:
            pending_ops = OrderedDict()
            for drive in auto_unmount_drives:
                tasks = determine_mount_ops(
                    do_mount=False,
                    drive_letter=drive.drive_letter,
                    mount_point=drive.mount_point,
                    uid=self.uid,
                    gid=self.gid,
                )
                if tasks:
                    pending_ops[drive] = tasks
            result = do_mount_drives_op(
                drives=auto_unmount_drives,
                pending_ops=pending_ops,
                parent=self.rapidApp,
                is_do_mount=False,
            )
            if result.cancelled or not at_exit:
                # Update internal drive state tracking, because we're not exiting
                self.updateDriveStatePostUnmount(unmounted=result.successes)
                self.logDrives()
                return False
        return True

    def validateDriveState(self) -> None:
        """
        Validate the internally maintained list of drives and their mount status by
        examining /proc/mounts
        """

        valdiated_drives = []  # type: List[WindowsDriveMount]
        valdiated_mount_points = defaultdict(
            list
        )  # type: DefaultDict[str, List[WindowsDriveMount]]
        difference_found = False
        for drive in self.drives:
            mount_point = wsl_mount_point(drive_letter=drive.drive_letter)
            if mount_point != drive.mount_point:
                difference_found = True
                new_drive = drive._replace(mount_point=mount_point)
                valdiated_drives.append(new_drive)
                valdiated_mount_points[mount_point].append(new_drive)
                if drive.mount_point == "":
                    logging.warning(
                        "Drive %s: (%s) was previously unmounted but is now "
                        "unexpectedly mounted at %s",
                        drive.drive_letter,
                        drive.label,
                        mount_point,
                    )
                else:
                    logging.warning(
                        "Drive %s: (%s) was previously mounted at %s but is now "
                        "unexpectedly unmounted",
                        drive.drive_letter,
                        drive.label,
                        drive.mount_point,
                    )
            else:
                valdiated_drives.append(drive)
                valdiated_mount_points[mount_point].append(drive)
        if difference_found:
            self.drives = valdiated_drives
            self.mount_points = valdiated_mount_points
            self.logDrives()

    def logDrives(self) -> None:
        if self.mount_points[""]:
            logging.debug(
                "%s mounted Windows drives (%s); %s unmounted (%s)",
                len(self.drives),
                make_hr_drive_letter_list(self.drives),
                len(self.mount_points[""]),
                make_hr_drive_letter_list(self.mount_points[""]),
            )
        else:
            logging.debug(
                "%s mounted Windows drives (%s)",
                len(self.drives),
                make_hr_drive_letter_list(self.drives),
            )

    def showMountDrivesDialog(self, validate_drive_state: bool = True) -> None:
        """
        Show the Dialogue window with a list of Windows drive mounts and associated
        options

        :param validate_drive_state: if True, fefresh the internally maintained list of
         Windows drives and their states
        :return:
        """
        if validate_drive_state:
            self.validateDriveState()

        if self.mountDrivesDialog is None:
            self.mountDrivesDialog = WslMountDriveDialog(
                parent=self.rapidApp,
                drives=self.drives,
                prefs=self.rapidApp.prefs,
                windrive_prefs=self.windrive_prefs,
                wsl_mount_root=self.wsl_mount_root,
            )
            self.mountDrivesDialog.exec()
            unmounted_drives = [
                drive
                for drive in self.mountDrivesDialog.prompt_to_mount_drives
                if drive in self.drives and not wsl_mount_point(drive.drive_letter)
            ]
            if unmounted_drives:
                drives_list_hr = make_hr_drive_list(unmounted_drives)
                logging.debug("Prompting to ask whether to mount %s", drives_list_hr)
                if len(unmounted_drives) == 1:
                    # Translators: this will appear in a small dialog asking the user
                    # if they want to mount a single drive
                    message = _("Do you want to mount drive %s?") % drives_list_hr
                else:
                    # translators: this will appear in a small dialog asking the user
                    # if they want to mount two or more drives
                    message = _("Do you want to mount drives %s?") % drives_list_hr
                msgBox = standardMessageBox(
                    message=message,
                    rich_text=False,
                    standardButtons=QMessageBox.Yes | QMessageBox.No,
                    parent=self.rapidApp,
                )
                if msgBox.exec() == QMessageBox.Yes:
                    logging.debug("Will mount drives %s", drives_list_hr)
                    self.doMountDrives(drives=unmounted_drives)
                else:
                    logging.debug("User chose not mount %s", drives_list_hr)
            self.mountDrivesDialog = None

    def doMountDrives(self, drives: List[WindowsDriveMount]) -> None:
        """
        Mount the list of drives that should be automatically mounted

        :param drives: the drives to mount
        """

        logging.debug("Auto mounting %s drives", len(drives))
        pending_ops = OrderedDict()
        mount_points = {}

        for drive in drives:
            mount_point = wsl_standard_mount_point(
                self.wsl_mount_root, drive.drive_letter
            )
            mount_points[drive.drive_letter] = mount_point
            tasks = determine_mount_ops(
                do_mount=True,
                drive_letter=drive.drive_letter,
                mount_point=mount_point,
                uid=self.uid,
                gid=self.gid,
            )
            if tasks:
                pending_ops[drive] = tasks

        result = do_mount_drives_op(
            drives=drives,
            pending_ops=pending_ops,
            parent=self.rapidApp,
            is_do_mount=True,
        )
        self.updateDriveStatePostMount(
            mounted=result.successes, mount_points=mount_points
        )
        self.logDrives()

    def updateDriveStatePostMount(
        self, mounted: List[WindowsDriveMount], mount_points: Dict[str, str]
    ):
        notify_via_signal = []
        for drive in mounted:
            new_drive = drive._replace(mount_point=mount_points[drive.drive_letter])
            self.mount_points[""].remove(drive)
            self.mount_points[new_drive.mount_point].append(new_drive)
            self.drives.remove(drive)
            self.drives.append(new_drive)
            notify_via_signal.append(new_drive)
        self.driveMounted.emit(notify_via_signal)

    def updateDriveStatePostUnmount(self, unmounted: List[WindowsDriveMount]) -> None:
        notify_via_signal = []
        for drive in unmounted:
            new_drive = drive._replace(mount_point="")
            self.drives.remove(drive)
            self.drives.append(new_drive)
            self.mount_points[drive.mount_point].remove(drive)
            self.mount_points[""].append(new_drive)
            notify_via_signal.append(drive)
        self.driveUnmounted.emit(notify_via_signal)


class WslWindowsRemovableDriveMonitor(QObject):
    """
    Use wmic.exe to periodically probe for removable drives on Windows

    On Windows an actual removable drive, e.g. a USB drive, can be classified
    as a "local drive". Strange but true. Thus need to probe for both local and
    removable drives.
    """

    driveMounted = pyqtSignal("PyQt_PyObject")
    driveUnmounted = pyqtSignal("PyQt_PyObject")

    def __init__(self) -> None:
        super().__init__()
        self.known_drives = set()  # type: Set[WindowsDrive]
        self.invalid_drives = set()  # type: Set[WindowsDrive]
        # dict key is drive letter
        self.detected_drives = dict()  # type: Dict[str, WindowsDriveMount]

    @pyqtSlot()
    def startMonitor(self) -> None:
        logging.debug("Starting Wsl Removable Drive Monitor")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.probeWindowsDrives)
        self.timer.setTimerType(Qt.CoarseTimer)
        self.timer.setInterval(1500)
        if self.probeWindowsDrives():
            self.timer.start()

    @pyqtSlot()
    def stopMonitor(self) -> None:
        logging.debug("Stopping Wsl Removable Drive Monitor")
        self.timer.stop()

    @pyqtSlot()
    def probeWindowsDrives(self) -> bool:
        timer_active = self.timer.isActive()
        if timer_active:
            self.timer.stop()
        try:
            current_drives = wsl_windows_drives(
                (WindowsDriveType.removable_disk, WindowsDriveType.local_disk)
            )
        except Exception:
            if timer_active:
                self.stopMonitor()
            return False

        new_drives = current_drives - self.known_drives
        removed_drives = self.known_drives - current_drives

        drives = []

        for drive in new_drives:
            if not wsl_drive_valid(drive.drive_letter):
                logging.debug(
                    "WslWindowsRemovableDriveMonitor adding invalid drive %s:",
                    drive.drive_letter,
                )
                self.invalid_drives.add(drive)
            else:
                mount_point = wsl_mount_point(drive.drive_letter)
                if mount_point:
                    assert os.path.ismount(mount_point)
                label = drive.label or (
                    # Translators: this is the name Windows uses for a removable drive,
                    # like a USB drive
                    _("Removable Drive")
                    if drive.drive_type == WindowsDriveType.removable_disk
                    # Translators: this is the name Windows uses for a drive that is
                    # normally part of the computer, like an internal hard drive
                    # (although for some reason some USB drives are classified by
                    # Windows as local drives)
                    else _("Local Drive")
                )
                windows_drive_mount = WindowsDriveMount(
                    drive_letter=drive.drive_letter,
                    label=label,
                    mount_point=mount_point,
                    drive_type=drive.drive_type,
                    system_mounted=drive.drive_type == WindowsDriveType.local_disk
                    and mount_point != "",
                )
                drives.append(windows_drive_mount)
                self.detected_drives[drive.drive_letter] = windows_drive_mount

        if drives:
            self.driveMounted.emit(drives)

        for drive in removed_drives:
            if drive in self.invalid_drives:
                logging.debug(
                    "WslWindowsRemovableDriveMonitor removing invalid drive %s:",
                    drive.drive_letter,
                )
                self.invalid_drives.remove(drive)
            else:
                windows_drive_mount = self.detected_drives[drive.drive_letter]
                self.driveUnmounted.emit(windows_drive_mount)
                del self.detected_drives[drive.drive_letter]

        self.known_drives = current_drives
        if timer_active:
            self.timer.start()
        return True


def wsl_standard_mount_point(root: Path, drive_letter: str) -> str:
    """
    Return mount point for the driver letter
    :param root: WSL mount point root
    :param drive_letter: drive's driver letter
    :return: the standard mount point
    """

    return str(root / drive_letter.lower())


def wsl_mount_point(drive_letter: str) -> str:
    """
    Determine the existing mount point of a Windows drive

    :param drive_letter: windows drive letter
    :return: Linux mount point, or "" if it is not mounted
    """

    with open("/proc/mounts") as m:
        mounts = m.read()

    regex = fr"^drvfs (.+?) 9p .+?path={drive_letter}:\\?;"
    mnt = re.search(regex, mounts, re.MULTILINE | re.IGNORECASE)
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
    # Testing only:
    # return drive_letter.lower() in ('c', 'd', 'f', 'g', 'j')
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
    drive_type_filter: Optional[Tuple[WindowsDriveType, ...]] = None,
) -> Set[WindowsDrive]:
    """
    Get Windows to report its drives and their types
    :param drive_type_filter: the type of drives to search for
    """

    # wmic is deprecated, but is much, much faster than calling powershell
    try:
        output = subprocess.run(
            shlex.split("wmic.exe logicaldisk get deviceid, volumename, drivetype"),
            universal_newlines=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout.strip()
    except Exception as e:
        logging.error("Call to wmic.exe failed: %s", str(e))
        raise "Call to wmic.exe failed"
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

    from raphodo.prefs.preferences import Preferences

    app = QApplication([])

    app.setOrganizationName("Rapid Photo Downloader")
    app.setOrganizationDomain("damonlynch.net")
    app.setApplicationName("Rapid Photo Downloader")

    prefs = Preferences()
    wdrive_prefs = WSLWindowsDrivePrefsInterface(prefs)

    all_drives = True
    if not all_drives:
        windows_drives = wsl_windows_drives(
            drive_type_filter=(
                WindowsDriveType.removable_disk,
                WindowsDriveType.local_disk,
            )
        )
    else:
        windows_drives = wsl_windows_drives()
    ddrives = []

    for wdrive in windows_drives:
        if wsl_drive_valid(wdrive.drive_letter):
            main_mount_point = wsl_mount_point(wdrive.drive_letter)
            if main_mount_point:
                assert os.path.ismount(main_mount_point)
                print(f"{wdrive.drive_letter}: is mounted at {main_mount_point}")
            else:
                print(f"{wdrive.drive_letter}: is not mounted")
            ddrives.append(
                WindowsDriveMount(
                    drive_letter=wdrive.drive_letter,
                    label=wdrive.label or "Removable Drive",
                    mount_point=main_mount_point,
                    drive_type=wdrive.drive_type,
                    system_mounted=wdrive.drive_type == WindowsDriveType.local_disk
                    and main_mount_point != "",
                )
            )

    w = WslMountDriveDialog(
        drives=ddrives,
        prefs=prefs,
        windrive_prefs=wdrive_prefs,
        wsl_mount_root=Path("/mnt"),
    )
    w.exec()
