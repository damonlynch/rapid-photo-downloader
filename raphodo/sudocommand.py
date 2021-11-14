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

from getpass import getuser
import logging
import shlex
import subprocess
from enum import IntEnum
from typing import List, NamedTuple, Optional

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox, QLabel, QHBoxLayout
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QIcon, QFontMetrics, QFont

from raphodo.password import PasswordEdit
from raphodo.viewutils import translateDialogBoxButtons, standardIconSize


class SudoCommand(QDialog):
    def __init__(
        self,
        msg: Optional[str] = None,
        hint: Optional[str] = None,
        title: Optional[str] = None,
        password_incorrect: bool = False,
        icon: Optional[str] = None,
        parent=None,
    ) -> None:
        super().__init__(parent=parent)

        if title:
            titleHLayout = QHBoxLayout()
            if icon:
                i = QIcon(icon)
            else:
                i = QIcon(":/rapid-photo-downloader.svg")
            size = QFontMetrics(QFont()).height()
            pixmap = i.pixmap(QSize(size, size))
            titleIcon = QLabel()
            titleIcon.setPixmap(pixmap)
            titleLabel = QLabel(f"<b>{title}</b>")
            if len(title) > 50:
                titleLabel.setWordWrap(True)
            titleLabel.setTextFormat(Qt.RichText)
            titleHLayout.addWidget(titleIcon)
            titleHLayout.addWidget(titleLabel)
            titleHLayout.addStretch()
            titleLayout = QVBoxLayout()
            titleLayout.addLayout(titleHLayout)
            titleLayout.addSpacing(8)

        if password_incorrect:
            wrongPasswordLabel = QLabel(_("Sorry, the password was incorrect."))

        msgLabel = QLabel(msg or _("Enter the administrator (root) password:"))
        if len(msgLabel.text()) > 50:
            msgLabel.setWordWrap(True)

        if hint:
            hintLabel = QLabel(hint)
            if len(hint) > 50:
                hintLabel.setWordWrap(True)

        self.passwordEdit = PasswordEdit()
        buttonBox = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        translateDialogBoxButtons(buttonBox)
        buttonBox.rejected.connect(self.reject)
        buttonBox.accepted.connect(self.accept)

        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)

        if title:
            layout.addLayout(titleLayout)
        if password_incorrect:
            layout.addWidget(wrongPasswordLabel)
        layout.addWidget(msgLabel)
        layout.addWidget(self.passwordEdit)
        if hint:
            layout.addWidget(hintLabel)
        layout.addWidget(buttonBox)
        self.setLayout(layout)

    def password(self) -> str:
        return self.passwordEdit.text()


class SudoExceptionCode(IntEnum):
    password_required = 1
    password_wrong = 2


class SudoException(Exception):
    def __init__(self, code: SudoExceptionCode) -> None:
        self.code = code

    def __repr__(self) -> str:
        if self.code == SudoExceptionCode.password_required:
            return "Password required"
        else:
            return "Password incorrect"


class SudoCommandResult(NamedTuple):
    return_code: int
    stdout: str
    stderr: str


def run_command_as_sudo_with_password(
    cmd: str, password: str, user: Optional[str] = None, timeout=10
) -> SudoCommandResult:
    """
    Run a single command via sudo, allowing for sudo to prompt for the password

    Generates exception if password is incorrect.

    :param cmd: command to run
    :param password: the password to pass to sudo
    :param user: username sudo will ask for. If not specified will get it via
     Python standard library.
    :param timeout: timeout for subprocess.Popen call
    :return: return codes, stdout and stderr
    """

    if user is None:
        user = getuser()
    password = f"{password}\n".encode()

    cmd = f"sudo -S {cmd}"
    cmd = shlex.split(cmd)

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"LANG": "C", "LANGUAGE": "C"},
    )
    try:
        output, errors = proc.communicate(input=password, timeout=timeout)
        sudo_output = f"[sudo] password for {user}: ".encode()
        if errors.startswith(sudo_output):
            errors = errors[len(sudo_output) :]
    except subprocess.TimeoutExpired:
        proc.kill()
        output, errors = proc.communicate()

    if errors.find(b"Sorry, try again.") >= 0:
        raise SudoException(code=SudoExceptionCode.password_wrong)
    return SudoCommandResult(
        return_code=proc.returncode,
        stdout=output.decode().strip(),
        stderr=errors.decode().strip(),
    )


def run_command_as_sudo_without_password(cmd: str, timeout=10) -> SudoCommandResult:
    """
    Run a single command via sudo instructing sudo to not prompt for the password

    Generates exception if password is required by sudo.

    :param cmd: command to run
    :param timeout: timeout for subprocess.Popen call
    :return: return codes, stdout and stderr
    """

    cmd = f"sudo -n {cmd}"
    cmd = shlex.split(cmd)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"LANG": "C", "LANGUAGE": "C"},
    )
    try:
        output, errors = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        output, errors = proc.communicate()

    if proc.returncode == 1 and errors == b"sudo: a password is required\n":
        raise SudoException(code=SudoExceptionCode.password_required)
    else:
        return SudoCommandResult(
            return_code=proc.returncode,
            stdout=output.decode().strip(),
            stderr=errors.decode().strip(),
        )


def _log_result(cmd: str, result: SudoCommandResult) -> None:
    if not (result.stdout or result.stderr) and result.return_code == 0:
        logging.debug("0: %s", cmd)
    else:
        logging.debug("%s: %s", result.return_code, cmd)
        if result.stdout and not result.stderr:
            logging.debug("stdout: %s", result.stdout)
        elif not result.stdout and result.stderr:
            logging.debug("stderr: %s", result.stderr)
        else:
            logging.debug("stdout: %s; stderr: %s", result.stdout, result.stderr)


def run_commands_as_sudo(
    cmds: List[str],
    parent,
    msg: Optional[str] = None,
    timeout=10,
    title: Optional[str] = None,
    icon: Optional[str] = None,
) -> List[SudoCommandResult]:
    """
    Run a list of commands. If necessary, prompt for the sudo password using a dialog.

    If return code of any of the commands is not zero, exit without doing the next
    commands.

    :param cmds: list of commands to run
    :param msg: message to display in password prompt dialog
    :param timeout: timeout for subprocess.Popen call
    :param title: title to display in password prompt
    :return: list of return codes, stdout and stderr
    """

    results = []  # type: List[SudoCommandResult, ...]
    for cmd in cmds:
        result = None  # type: Optional[SudoCommandResult]
        try:
            result = run_command_as_sudo_without_password(cmd=cmd, timeout=timeout)
            _log_result(cmd, result)
        except SudoException as e:
            assert e.code == SudoExceptionCode.password_required
            password_incorrect = False
            user = getuser()
            while True:
                passwordPrompt = SudoCommand(
                    msg=msg,
                    password_incorrect=password_incorrect,
                    parent=parent,
                    title=title,
                    icon=icon,
                )
                if passwordPrompt.exec():
                    try:
                        result = run_command_as_sudo_with_password(
                            cmd=cmd,
                            password=passwordPrompt.password(),
                            user=user,
                            timeout=timeout,
                        )
                        _log_result(cmd, result)
                        break
                    except SudoException as e:
                        assert e.code == SudoExceptionCode.password_wrong
                        password_incorrect = True
                else:
                    break

        results.append(result)
        if result is not None and result.return_code != 0:
            return results
    return results


if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication

    app = QApplication([])

    cmds = ["ls /root", "echo OK"]
    results = run_commands_as_sudo(cmds, parent=None)
    for result in results:
        print(result)
