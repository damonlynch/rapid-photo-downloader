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
import textwrap
from typing import List, NamedTuple, Optional
import webbrowser

from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QDialogButtonBox,
    QLabel,
    QHBoxLayout,
    QSizePolicy,
)
from PyQt5.QtCore import Qt, QSize, pyqtSlot
from PyQt5.QtGui import QIcon, QFontMetrics, QFont

from raphodo.ui.password import PasswordEdit
from raphodo.ui.viewutils import translateDialogBoxButtons


class SudoCommand(QDialog):
    def __init__(
        self,
        msg: Optional[str] = None,
        hint: Optional[str] = None,
        title: Optional[str] = None,
        password_incorrect: bool = False,
        icon: Optional[str] = None,
        help_url: Optional[str] = None,
        parent=None,
    ) -> None:
        super().__init__(parent=parent)

        word_wrap_width = 50

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
            titleIcon.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            if len(title) > word_wrap_width:
                # DO NOT set wordwrap on the richtext QLabel, or else the Qt layout
                # management is truly screwed!!
                # from the Qt documentation:
                # "The use of rich text in a label widget can introduce some problems to
                # the layout of its parent widget. Problems occur due to the way rich
                # text is handled by Qt's layout managers when the label is word
                # wrapped"
                title = "<br>".join(textwrap.wrap(title, width=word_wrap_width))
            titleLabel = QLabel(f"<b>{title}</b>")
            titleLabel.setTextFormat(Qt.RichText)
            titleLabel.setAlignment(Qt.AlignTop)
            titleLabel.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
            titleHLayout.addWidget(titleIcon, alignment=Qt.AlignTop)
            titleHLayout.addWidget(titleLabel, alignment=Qt.AlignTop)
            titleLayout = QVBoxLayout()
            titleLayout.addLayout(titleHLayout)
            titleLayout.addSpacing(8)

        if password_incorrect:
            wrongPasswordLabel = QLabel(_("Sorry, the password was incorrect."))

        msgLabel = QLabel(
            msg
            # Translators: here %s refers to the username (you must keep %s or the
            # program will crash). This is what it looks like:
            # https://damonlynch.net/rapid/documentation/fullsize/wsl/password-prompt-hidden.png
            or _("To perform administrative tasks, enter the password for %s.")
            % getuser()
        )
        if len(msgLabel.text()) > 50:
            msgLabel.setWordWrap(True)
            msgLabel.setSizePolicy(
                QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding
            )

        if hint:
            hintLabel = QLabel(hint)
            if len(hint) > 50:
                hintLabel.setWordWrap(True)
                hintLabel.setSizePolicy(
                    QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding
                )

        self.passwordEdit = PasswordEdit()
        self.passwordEdit.setMinimumWidth(220)
        self.passwordEdit.setSizePolicy(
            QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding
        )
        buttonBox = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        if help_url:
            self.help_url = help_url
            self.helpButton = buttonBox.addButton(QDialogButtonBox.Help)
            self.helpButton.clicked.connect(self.helpButtonClicked)

        translateDialogBoxButtons(buttonBox)
        buttonBox.rejected.connect(self.reject)
        buttonBox.accepted.connect(self.accept)
        buttonBox.setSizePolicy(
            QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding
        )

        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)

        passwordLayout = QHBoxLayout()
        passwordLayout.addWidget(QLabel(_("Password:")))
        passwordLayout.addWidget(self.passwordEdit)

        if title:
            layout.addLayout(titleLayout)
        if password_incorrect:
            layout.addWidget(wrongPasswordLabel)
        layout.addWidget(msgLabel)
        layout.addLayout(passwordLayout)
        if hint:
            layout.addWidget(hintLabel)
        layout.addWidget(buttonBox)
        self.setLayout(layout)

    @pyqtSlot()
    def helpButtonClicked(self) -> None:
        webbrowser.open_new_tab(self.help_url)

    def password(self) -> str:
        return self.passwordEdit.text()


class SudoExceptionCode(IntEnum):
    password_required = 1
    password_wrong = 2
    command_cancelled = 3


class SudoException(Exception):
    def __init__(self, code: SudoExceptionCode) -> None:
        self.code = code

    def __repr__(self) -> str:
        if self.code == SudoExceptionCode.password_required:
            return "Password required"
        elif self.code == SudoExceptionCode.password_wrong:
            return "Password incorrect"
        else:
            assert self.code == SudoExceptionCode.command_cancelled
            return "Command cancelled"


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
    help_url: Optional[str] = None,
) -> List[SudoCommandResult]:
    """
    Run a list of commands. If necessary, prompt for the sudo password using a dialog.

    If return code of any of the commands is not zero, exit without doing the next
    commands.

    :param cmds: list of commands to run
    :param msg: message to display in password prompt dialog
    :param timeout: timeout for subprocess.Popen call
    :param title: title to display in password prompt
    :param icon: icon to display if a dialog window is
     needed to prompt for the password
    :param help_url: if specified, a help button will be added to the dialog window,
     and clicking it will open this URL
    :return: list of return codes, stdout and stderr
    """

    results = []  # type: List[SudoCommandResult, ...]
    for cmd in cmds:
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
                    help_url=help_url,
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
                    logging.debug("Mount ops cancelled by user request")
                    raise SudoException(code=SudoExceptionCode.command_cancelled)

        results.append(result)
        if result.return_code != 0:
            return results
    return results


if __name__ == "__main__":
    # Test code
    from PyQt5.QtWidgets import QApplication

    app = QApplication([])

    cmds = ["echo OK"]

    title = "Unmount drives EOS_DIGITAL (G:) and EOS_DIGITAL (J:)"
    title = "Unmount drives EOS_DIGITAL (G:)"
    icon = ":/icons/drive-removable-media.svg"

    results = run_commands_as_sudo(
        cmds=cmds,
        parent=None,
        title=title,
        icon=icon,
        help_url="https://damonlynch.net/rapid/documentation/#wslsudopassword",
    )

    for result in results:
        print(result)
