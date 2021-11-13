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
import shlex
import subprocess
from enum import IntEnum
from typing import List, NamedTuple, Optional

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox, QLabel

from raphodo.password import PasswordEdit
from raphodo.viewutils import translateDialogBoxButtons


class SudoCommand(QDialog):
    def __init__(
        self,
        msg: Optional[str] = None,
        hint: Optional[str] = None,
        password_incorrect: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent=parent)

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
    cmd: str, password: str, user: Optional[str]=None, timeout=10
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
            errors = errors[len(sudo_output):]
    except subprocess.TimeoutExpired:
        proc.kill()
        output, errors = proc.communicate()

    if errors.find(b"Sorry, try again.") >= 0:
        raise SudoException(code=SudoExceptionCode.password_wrong)
    return SudoCommandResult(
        return_code=proc.returncode, stdout=output.decode(), stderr=errors.decode()
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
            return_code=proc.returncode, stdout=output.decode(), stderr=errors.decode()
        )


def run_commands_as_sudo(cmds: List[str], timeout=10) -> List[SudoCommandResult]:
    """
    Run a list of commands. If necessary, prompt for the sudo password using a dialog.

    If return code of any of the commands is not zero, exit without doing the next
    commands.

    :param cmds: list of commands to run
    :param timeout: timeout for subprocess.Popen call
    :return: list of return codes, stdout and stderr
    """

    results = []  # type: List[SudoCommandResult, ...]
    for cmd in cmds:
        result = None  # type: Optional[SudoCommandResult]
        try:
            result = run_command_as_sudo_without_password(cmd)
        except SudoException as e:
            assert e.code == SudoExceptionCode.password_required
            password_incorrect = False
            user = getuser()
            while True:
                passwordPrompt = SudoCommand(password_incorrect=password_incorrect)
                if passwordPrompt.exec():
                    try:
                        result = run_command_as_sudo_with_password(
                            cmd=cmd, password=passwordPrompt.password(), user=user
                        )
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
    results = run_commands_as_sudo(cmds)
    for result in results:
        print(result)
