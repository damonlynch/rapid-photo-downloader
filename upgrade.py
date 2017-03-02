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
Helper program to upgrade Rapid Photo Downloader using pip
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
from gettext import gettext as _

from PyQt5.QtCore import (pyqtSignal, pyqtSlot,  Qt, QThread, QObject, QTimer)
from PyQt5.QtGui import QIcon, QFontMetrics, QFont, QFontDatabase
from PyQt5.QtWidgets import (QApplication, QDialog, QPushButton, QVBoxLayout, QTextEdit,
                             QDialogButtonBox, QStackedWidget, QLabel)
from PyQt5.QtNetwork import QLocalSocket

import raphodo.qrc_resources as qrc_resources


q = Queue()


class RPDUpgrade(QObject):
    """
    Upgrade Rapid Photo Downloader using python's pip
    """

    message = pyqtSignal(str)
    upgradeFinished = pyqtSignal(bool)


    def make_pip_command(self, args: str) -> List[str]:
        return shlex.split('{} -m pip {}'.format(sys.executable, args))

    @pyqtSlot(str)
    def start(self, installer: str) -> None:

        name = os.path.basename(installer)
        name = name[:len('.tar.gz') * -1]

        rpath = os.path.join(name, 'requirements.txt')
        try:
            with tarfile.open(installer) as tar:
                with tar.extractfile(rpath) as requirements:
                    reqbytes = requirements.read()
                    with tempfile.NamedTemporaryFile(delete=False) as temp_requirements:
                        temp_requirements.write(reqbytes)
                        temp_requirements_name = temp_requirements.name
        except Exception:
            self.failure("Failed to extract application requirements")
            return

        self.sendMessage("Installing application requirements...\n")
        try:
            cmd = self.make_pip_command('install --user -r {}'.format(temp_requirements.name))
            with Popen(cmd, stdout=PIPE, stderr=PIPE, bufsize=1, universal_newlines=True) as p:
                for line in p.stdout:
                    self.sendMessage(line, truncate=True)
                    cmd = self.checkForCmd()
                    if cmd is not None:
                        assert cmd == 'STOP'
                        self.failure('\nTermination requested')
                        return
                p.wait()
                i = p.returncode
            os.remove(temp_requirements_name)
            if i != 0:
                self.failure("Failed to install application requirements: %i" % i)
                return
        except Exception:
            self.sendMessage(sys.exc_info())
            self.failure("Failed to install application requirements")
            return

        self.sendMessage("\nInstalling application...\n")
        try:
            cmd = self.make_pip_command('install --user --no-deps {}'.format(installer))
            with Popen(cmd, stdout=PIPE, stderr=PIPE, bufsize=1, universal_newlines=True) as p:
                for line in p.stdout:
                    self.sendMessage(line, truncate=True)
                    cmd = self.checkForCmd()
                    if cmd is not None:
                        assert cmd == 'STOP'
                        self.failure('\nTermination requested')
                        return
                p.wait()
                i = p.returncode
            if i != 0:
                self.failure("Failed to install application")
                return
        except Exception:
            self.failure("Failed to install application")
            return

        self.upgradeFinished.emit(True)

    def failure(self, message: str) -> None:
        self.sendMessage(message)
        self.upgradeFinished.emit(False)


    def sendMessage(self, message: str, truncate=False) -> None:
        if truncate:
            self.message.emit(message[:-1])
        else:
            self.message.emit(message)

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
        self.setWindowTitle(_('Upgrade Rapid Photo Downloader'))

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

        upgradeButtonBox = QDialogButtonBox(QDialogButtonBox.Cancel)
        upgradeButtonBox.rejected.connect(self.reject)
        upgradeButtonBox.accepted.connect(self.doUpgrade)
        self.startButton = upgradeButtonBox.addButton(_('&Upgrade'),
                                                 QDialogButtonBox.AcceptRole)  # QPushButton
        # self.startButton.setDefault(True)

        if self.version_no:
            self.explanation = QLabel(_('Click the Upgrade button to upgrade to '
                                        'version %s.') % self.version_no)
        else:
            self.explanation = QLabel(_('Click the Upgrade button to start the upgrade.'))

        finishButtonBox = QDialogButtonBox(QDialogButtonBox.Close)
        finishButtonBox.addButton(_('&Run'), QDialogButtonBox.AcceptRole)
        finishButtonBox.rejected.connect(self.reject)
        finishButtonBox.accepted.connect(self.runNewVersion)

        failedButtonBox = QDialogButtonBox(QDialogButtonBox.Close)
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
                message = _('Successfully upgraded to %s. Click Close to exit, or Run to '
                            'start the program.' % self.version_no)
            else:
                message = _('Upgrade finished successfully. Click Close to exit, or Run to '
                            'start the program.')
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
            # strangely, using zmq in this program causes a segfault :-/
            q.put('STOP')
        super().reject()

    @pyqtSlot()
    def runNewVersion(self) -> None:
        cmd = shutil.which('rapid-photo-downloader')
        subprocess.Popen(cmd)
        super().accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(':/rapid-photo-downloader.svg'))
    widget = UpgradeDialog(sys.argv[1])
    widget.show()
    sys.exit(app.exec_())