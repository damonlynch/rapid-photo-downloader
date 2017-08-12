# Copyright (C) 2017 Damon Lynch <damonlynch@gmail.com>

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
Helper program to upgrade Rapid Photo Downloader using pip.

Structure, all run from this script:

GUI: main thread in main process
Installer code: secondary process, no Qt, fully isolated
Communication: secondary thread in main process, using zeromq

Determining which code block in the structure is determined
at the script level i.e. in __name__ == '__main__'
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2017, Damon Lynch"

import sys
import os
import tarfile
import tempfile
import shutil
import re
from typing import List, Optional
import shlex
from subprocess import Popen, PIPE
from queue import Queue, Empty
import subprocess
import platform
from distutils.version import StrictVersion
import argparse


from gettext import gettext as _

from PyQt5.QtCore import (pyqtSignal, pyqtSlot,  Qt, QThread, QObject, QTimer)
from PyQt5.QtGui import QIcon, QFontMetrics, QFont, QFontDatabase
from PyQt5.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox, QStackedWidget, QLabel
)
from PyQt5.QtNetwork import QLocalSocket
from xdg import BaseDirectory
import gettext
import zmq
import psutil


__title__ = _('Upgrade Rapid Photo Downloader')
__description__ = "Upgrade to the latest version of Rapid Photo Downloader.\n" \
                  "Do not run this program yourself."

import raphodo.qrc_resources as qrc_resources
from raphodo.utilities import set_pdeathsig

i18n_domain = 'rapid-photo-downloader'

def locale_directory():
    """
    Locate locale directory. Prioritizes whatever is newer, comparing the locale
    directory at xdg_data_home and the one in /usr/share/

    :return: the locale directory with the most recent messages for Rapid Photo
    Downloader, if found, else None.
    """

    mo_file = '{}.mo'.format(i18n_domain)
    # Test the Spanish file
    sample_lang_path = os.path.join('es', 'LC_MESSAGES', mo_file)
    locale_mtime = 0.0
    locale_dir = None

    for path in (BaseDirectory.xdg_data_home, '/usr/share'):
        locale_path = os.path.join(path, 'locale')
        sample_path = os.path.join(locale_path, sample_lang_path)
        if os.path.isfile(sample_path) and os.access(sample_path, os.R_OK):
            if os.path.getmtime(sample_path) > locale_mtime:
                locale_dir = locale_path
    return locale_dir

q = Queue()


class RunInstallProcesses:
    """
    Run subprocess pip commmands in an isolated process, connected via zeromq
    request reply sockets.
    """

    def __init__(self, socket: str) -> None:

        context = zmq.Context()
        self.responder = context.socket(zmq.REP)
        self.responder.connect("tcp://localhost:{}".format(socket))

        installer = self.responder.recv_string()

        # explicitly uninstall any previous version installed with pip
        self.send_message("Uninstalling previous version installed with pip...\n")
        l_command_line = 'list --user --disable-pip-version-check'
        if self.pip_version() >= StrictVersion('9.0.0'):
            l_command_line = '{} --format=columns'.format(l_command_line)
        l_args = self.make_pip_command(l_command_line)

        u_command_line = 'uninstall --disable-pip-version-check -y rapid-photo-downloader'
        u_args = self.make_pip_command(u_command_line)
        pip_list = ''
        while True:
            try:
                pip_list = subprocess.check_output(l_args, universal_newlines=True)
                if 'rapid-photo-downloader' in pip_list:
                    with Popen(
                            u_args, stdout=PIPE, stderr=PIPE, bufsize=1, universal_newlines=True
                    ) as p:
                        for line in p.stdout:
                            self.send_message(line, truncate=True)
                        p.wait()
                        i = p.returncode
                    if i != 0:
                        self.send_message(
                            "Encountered an error uninstalling previous version installed with "
                            "pip\n"
                        )
                else:
                    break
            except Exception:
                break
        self.send_message('...done uninstalling previous version.\n')

        name = os.path.basename(installer)
        name = name[:len('.tar.gz') * -1]

        # Check the requirements file for any packages we should install using pip
        # Can't include packages that are already installed, or else a segfault can
        # occur. Which is a bummer, as that means automatic upgrades cannot occur.
        rpath = os.path.join(name, 'requirements.txt')
        package_match = re.compile(r'^([a-zA-Z]+[a-zA-Z0-9-]+)')
        try:
            with tarfile.open(installer) as tar:
                with tar.extractfile(rpath) as requirements_f:
                    requirements = ''
                    for line in requirements_f.readlines():
                        line = line.decode()
                        results = package_match.search(line)
                        if results is not None:
                            package = results.group(0)
                            # Don't include packages that are already installed
                            if package not in pip_list and package not in ('typing', 'scandir'):
                                requirements = '{}\n{}'.format(requirements, line)
                    if self.need_pyqt5(pip_list):
                        requirements = '{}\nPyQt5\n'.format(requirements)
                    if requirements:
                        with tempfile.NamedTemporaryFile(delete=False) as temp_requirements:
                            temp_requirements.write(requirements.encode())
                            temp_requirements_name = temp_requirements.name
                    else:
                        temp_requirements_name = ''
        except Exception:
            self.failure("Failed to extract application requirements")
            return

        if requirements:
            self.send_message("Installing application requirements...\n")
            cmd = self.make_pip_command(
                'install --user --upgrade --disable-pip-version-check -r {}'.format(
                    temp_requirements_name
                )
            )
            try:
                with Popen(cmd, stdout=PIPE, stderr=PIPE, bufsize=1, universal_newlines=True) as p:
                    for line in p.stdout:
                        self.send_message(line, truncate=True)
                    p.wait()
                    i = p.returncode
                os.remove(temp_requirements_name)
                if i != 0:
                    self.failure("Failed to install application requirements: %i" % i)
                    return
            except Exception as e:
                self.send_message(str(e))
                self.failure("Failed to install application requirements")
                return

        self.send_message("\nInstalling application...\n")
        cmd = self.make_pip_command(
            'install --user --disable-pip-version-check --no-deps {}'.format(installer)
        )
        try:
            with Popen(cmd, stdout=PIPE, stderr=PIPE, bufsize=1, universal_newlines=True) as p:
                for line in p.stdout:
                    self.send_message(line, truncate=True)
                p.wait()
                i = p.returncode
            if i != 0:
                self.failure("Failed to install application")
                return
        except Exception:
            self.failure("Failed to install application")
            return

        self.responder.send_multipart([b'cmd', b'FINISHED'])

    def check_cmd(self) -> None:
        cmd = self.responder.recv()
        if cmd == b'STOP':
            self.stop()

    def send_message(self, message: str, truncate: bool=False) -> None:
        if truncate:
            self.responder.send_multipart([b'data', message[:-1].encode()])
        else:
            self.responder.send_multipart([b'data', message.encode()])
        self.check_cmd()

    def failure(self, message: str) -> None:
        self.send_message(message)
        self.stop()

    def stop(self) -> None:
        self.responder.send_multipart([b'cmd', 'STOPPED'])
        sys.exit(0)

    def make_pip_command(self, args: str) -> List[str]:
        cmd = '{} -m pip {}'.format(sys.executable, args)
        return shlex.split(cmd)

    def pip_version(self) -> StrictVersion:
        import pip

        return StrictVersion(pip.__version__)

    def need_pyqt5(self, pip_list) -> bool:
        if platform.machine() == 'x86_64' and platform.python_version_tuple()[1] in ('5', '6'):
            return not 'PyQt5' in pip_list
        return False


class RPDUpgrade(QObject):
    """
    Upgrade Rapid Photo Downloader using python's pip
    """

    message = pyqtSignal(str)
    upgradeFinished = pyqtSignal(bool)


    def run_process(self, port: int) -> bool:
        command_line = '{} {} --socket={}'.format(sys.executable, __file__, port)
        args = shlex.split(command_line)

        try:
            proc = psutil.Popen(args, preexec_fn=set_pdeathsig())
            return True
        except OSError as e:
            return False

    @pyqtSlot(str)
    def start(self, installer: str) -> None:

        context = zmq.Context()
        requester = context.socket(zmq.REQ)
        port = requester.bind_to_random_port('tcp://*')

        if not self.run_process(port=port):
            self.upgradeFinished.emit(False)
            return

        requester.send_string(installer)

        while True:
            directive, content = requester.recv_multipart()
            if directive == b'data':
                self.message.emit(content.decode())
            else:
                assert directive == b'cmd'
                if content == b'STOPPED':
                    self.upgradeFinished.emit(False)
                elif content == b'FINISHED':
                    self.upgradeFinished.emit(True)
                return

            cmd = self.checkForCmd()
            if cmd is None:
                requester.send(b'CONT')
            else:
                requester.send(b'STOP')

    def checkForCmd(self) -> Optional[str]:
        try:
            return q.get(block=False)
        except Empty:
            return None


def extract_version_number(installer: str) -> str:
    targz = os.path.basename(installer)
    parsed_version = targz[:targz.find('tar') - 1]

    first_digit = re.search("\d", parsed_version)
    return parsed_version[first_digit.start():]


class UpgradeDialog(QDialog):
    """
    Very simple dialog window that allows user to initiate
    Rapid Photo Downloader upgrade and shows output of that
    upgrade.
    """

    startUpgrade = pyqtSignal(str)
    def __init__(self, installer):
        super().__init__()

        self.installer = installer
        self.setWindowTitle(__title__)

        try:
            self.version_no = extract_version_number(installer=installer)
        except Exception:
            self.version_no = ''

        self.running = False

        self.textEdit = QTextEdit()
        self.textEdit.setReadOnly(True)

        fixed = QFontDatabase.systemFont(QFontDatabase.FixedFont)  # type: QFont
        fixed.setPointSize(fixed.pointSize() - 1)
        self.textEdit.setFont(fixed)

        font_height = QFontMetrics(fixed).height()

        height = font_height * 20

        width = QFontMetrics(fixed).boundingRect('a' * 90).width()

        self.textEdit.setMinimumSize(width, height)

        upgradeButtonBox = QDialogButtonBox()
        upgradeButtonBox.addButton(_('&Cancel'), QDialogButtonBox.RejectRole)
        upgradeButtonBox.rejected.connect(self.reject)
        upgradeButtonBox.accepted.connect(self.doUpgrade)
        self.startButton = upgradeButtonBox.addButton(
            _('&Upgrade'), QDialogButtonBox.AcceptRole
        )  # QPushButton

        if self.version_no:
            self.explanation = QLabel(
                _('Click the Upgrade button to upgrade to version %s.') % self.version_no
            )
        else:
            self.explanation = QLabel(_('Click the Upgrade button to start the upgrade.'))

        finishButtonBox = QDialogButtonBox(QDialogButtonBox.Close)
        finishButtonBox.button(QDialogButtonBox.Close).setText(_('&Close'))
        finishButtonBox.addButton(_('&Run'), QDialogButtonBox.AcceptRole)
        finishButtonBox.rejected.connect(self.reject)
        finishButtonBox.accepted.connect(self.runNewVersion)

        failedButtonBox = QDialogButtonBox(QDialogButtonBox.Close)
        failedButtonBox.button(QDialogButtonBox.Close).setText(_('&Close'))
        failedButtonBox.rejected.connect(self.reject)

        self.stackedButtons = QStackedWidget()
        self.stackedButtons.addWidget(upgradeButtonBox)
        self.stackedButtons.addWidget(finishButtonBox)
        self.stackedButtons.addWidget(failedButtonBox)

        layout = QVBoxLayout()
        self.setLayout(layout)
        layout.addWidget(self.textEdit)
        layout.addWidget(self.explanation)
        layout.addWidget(self.stackedButtons)

        self.upgrade = RPDUpgrade()
        self.upgradeThread = QThread()
        self.startUpgrade.connect(self.upgrade.start)
        self.upgrade.message.connect(self.appendText)
        self.upgrade.upgradeFinished.connect(self.upgradeFinished)
        self.upgrade.moveToThread(self.upgradeThread)
        QTimer.singleShot(0, self.upgradeThread.start)

    @pyqtSlot()
    def doUpgrade(self) -> None:
        if self.rpdRunning():
            self.explanation.setText(_('Close Rapid Photo Downloader before running this upgrade'))
        else:
            self.running = True
            self.explanation.setText(_('Upgrade running...'))
            self.startButton.setEnabled(False)
            self.startUpgrade.emit(self.installer)

    def rpdRunning(self) -> bool:
        """
        Check to see if Rapid Photo Downloader is running
        :return: True if it is
        """

        # keep next value in sync with value in raphodo/rapid.py
        # can't import it
        appGuid = '8dbfb490-b20f-49d3-9b7d-2016012d2aa8'
        outSocket = QLocalSocket() # type: QLocalSocket
        outSocket.connectToServer(appGuid)
        isRunning = outSocket.waitForConnected()  # type: bool
        if outSocket:
            outSocket.disconnectFromServer()
        return isRunning

    @pyqtSlot(str)
    def appendText(self,text: str) -> None:
        self.textEdit.append(text)

    @pyqtSlot(bool)
    def upgradeFinished(self, success: bool) -> None:
        self.running = False

        if success:
            self.stackedButtons.setCurrentIndex(1)
        else:
            self.stackedButtons.setCurrentIndex(2)

        if success:
            if self.version_no:
                message = _(
                    'Successfully upgraded to %s. Click Close to exit, or Run to '
                    'start the program.'
                ) % self.version_no
            else:
                message = _(
                    'Upgrade finished successfully. Click Close to exit, or Run to '
                    'start the program.'
                )
        else:
            message = _('Upgrade failed. Click Close to exit.')

        self.explanation.setText(message)
        self.deleteTar()

    def deleteTar(self) -> None:
        temp_dir = os.path.dirname(self.installer)
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def closeEvent(self, event) -> None:
        self.upgradeThread.quit()
        self.upgradeThread.wait()
        event.accept()

    @pyqtSlot()
    def reject(self) -> None:
        if self.running:
            # strangely, using zmq in this script causes a segfault :-/
            q.put('STOP')
        super().reject()

    @pyqtSlot()
    def runNewVersion(self) -> None:
        cmd = shutil.which('rapid-photo-downloader')
        subprocess.Popen(cmd)
        super().accept()

def parser_options(formatter_class=argparse.HelpFormatter) -> argparse.ArgumentParser:
    """
    Construct the command line arguments for the script

    :return: the parser
    """

    parser = argparse.ArgumentParser(
        prog=__title__, formatter_class=formatter_class, description=__description__
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument('tarfile',  action='store', nargs='?', help=argparse.SUPPRESS)
    group.add_argument('--socket', action='store', nargs='?', help=argparse.SUPPRESS)

    return parser


if __name__ == '__main__':

    parser = parser_options()

    args = parser.parse_args()

    if args.tarfile:
        gettext.bindtextdomain(i18n_domain, localedir=locale_directory())
        gettext.textdomain(i18n_domain)

        app = QApplication(sys.argv)
        app.setWindowIcon(QIcon(':/rapid-photo-downloader.svg'))
        widget = UpgradeDialog(args.tarfile)
        widget.show()
        sys.exit(app.exec_())

    else:
        RunInstallProcesses(args.socket)