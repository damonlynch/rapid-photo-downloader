# Copyright (C) 2017-2021 Damon Lynch <damonlynch@gmail.com>

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
Widgets and program logic to check for new program versions and
to download them.
"""

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2017-2021, Damon Lynch"

import logging
from collections import namedtuple
import pkg_resources
import hashlib
import os
import shutil
from typing import Optional

import requests

import arrow
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, Qt
from PyQt5.QtWidgets import (
    QDialog,
    QLabel,
    QStackedWidget,
    QDialogButtonBox,
    QGridLayout,
    QPushButton,
    QProgressBar,
)
import zmq

from raphodo.constants import (
    remote_versions_file,
    CheckNewVersionDialogState,
    CheckNewVersionDialogResult,
    standardProgressBarWidth,
)
from raphodo.utilities import (
    create_temp_dir,
    format_size_for_user,
    is_venv,
    installed_using_pip,
)
from raphodo.interprocess import ThreadNames
from raphodo.ui.viewutils import translateDialogBoxButtons

version_details = namedtuple(
    "version_details", "version release_date url md5 changelog_url"
)


class NewVersion(QObject):
    """
    Check for and download a new version of the program.

    Runs in its own thread.
    """

    checkMade = pyqtSignal(
        bool, version_details, version_details, str, bool, bool, bool
    )
    # See http://pyqt.sourceforge.net/Docs/PyQt5/signals_slots.html#the-pyqt-pyobject-signal-argument-type
    bytesDownloaded = pyqtSignal("PyQt_PyObject")  # don't convert python int to C++ int
    downloadSize = pyqtSignal("PyQt_PyObject")  # don't convert python int to C++ int
    # if not empty, file downloaded okay and saved to this temp directory
    # if empty, file failed to download and verify
    fileDownloaded = pyqtSignal(str, bool)
    # signal True if downloaded tar passed md5sum check, else signal False
    # also include path to tar
    reverified = pyqtSignal(bool, str)

    def __init__(self, rapidApp):
        super().__init__()
        self.rapidApp = rapidApp
        self.rapidApp.checkForNewVersionRequest.connect(self.check)
        self.rapidApp.downloadNewVersionRequest.connect(self.download)
        self.installed_via_pip_check_made = False
        self.is_venv_check_made = False
        self.installed_via_pip = None  # type: Optional[bool]
        self.is_venv = None  # type: Optional[bool]

    @pyqtSlot()
    def start(self) -> None:
        context = zmq.Context.instance()
        self.thread_controller = context.socket(zmq.PAIR)
        self.thread_controller.connect("inproc://{}".format(ThreadNames.new_version))

    @pyqtSlot()
    def check(self) -> None:
        success = False
        dev_version = version_details("", "", "", "", "")
        stable_version = version_details("", "", "", "", "")
        download_page = ""
        no_upgrade = True
        try:
            r = requests.get(remote_versions_file)
        except:
            logging.debug("Failed to download versions file %s", remote_versions_file)
        else:
            status_code = r.status_code
            success = status_code == 200
            if not success:
                logging.debug(
                    "Got error code %d while accessing versions file", status_code
                )
                self.status_code = r.status_code
            else:
                try:
                    self.version = r.json()
                except:
                    logging.error("Error %d accessing versions JSON file", status_code)
                    success = False
                    self.status_code = r.status_code
                else:
                    stable = self.version["stable"]
                    dev = self.version["dev"]
                    # Dates in format 2019-08-10T08:01:00+00:00
                    dev_version = version_details(
                        version=pkg_resources.parse_version(dev["version"]),
                        release_date=arrow.get(dev["date"]).to("local"),
                        url=dev["url"],
                        md5=dev["md5"],
                        changelog_url=dev["changelog"],
                    )
                    stable_version = version_details(
                        version=pkg_resources.parse_version(stable["version"]),
                        release_date=arrow.get(stable["date"]).to("local"),
                        url=stable["url"],
                        md5=stable["md5"],
                        changelog_url=stable["changelog"],
                    )
                    download_page = self.version["download_page"]
                    no_upgrade = self.version["no_upgrade"]

        if not self.installed_via_pip_check_made:
            try:
                self.installed_via_pip = installed_using_pip(
                    "rapid-photo-downloader", suppress_errors=False
                )
            except Exception:
                logging.debug(
                    "Exception encountered when checking if pip was used to install "
                    "(probably the program has not been installed)"
                )
                self.installed_via_pip = False

        if not self.is_venv_check_made:
            self.is_venv = is_venv()
            self.is_venv_check_made = True

        self.checkMade.emit(
            success,
            stable_version,
            dev_version,
            download_page,
            no_upgrade,
            self.installed_via_pip,
            self.is_venv,
        )

    def verifyDownload(self, downloaded_tar: str, md5_url: str) -> bool:
        """
        Verifies downloaded tarball against the launchpad generated md5sum file.

        Exceptions not caught.

        :param downloaded_tar: local file
        :param md5_url: remote md5sum file for the download
        :return: True if md5sum matches, False otherwise,
        """

        if not md5_url:
            return True

        r = requests.get(md5_url)
        assert r.status_code == 200
        self.remote_md5 = r.text.split()[0]
        with open(downloaded_tar, "rb") as tar:
            m = hashlib.md5()
            m.update(tar.read())
        return m.hexdigest() == self.remote_md5

    @pyqtSlot(str)
    def reVerifyDownload(self, downloaded_tar: str) -> None:
        """
        Reverify a tar that has been downloaded.

        Emits signal reverified.

        All exceptions caught and logged.

        :param downloaded_tar: file to verify
        """
        try:
            with open(downloaded_tar, "rb") as tar:
                m = hashlib.md5()
                m.update(tar.read())
            self.reverified.emit(m.hexdigest() == self.remote_md5, downloaded_tar)
        except (FileNotFoundError, OSError):
            logging.exception(
                "Could not open tarfile %s for hash reverification", downloaded_tar
            )
            self.reverified.emit(False, "")
        except Exception:
            logging.exception(
                "Unknown exception when doing hash reverification of tarfile %s",
                downloaded_tar,
            )
            self.reverified.emit(False, "")

    def checkForCmd(self) -> Optional[bytes]:
        try:
            return self.thread_controller.recv(zmq.DONTWAIT)
        except zmq.Again:
            return None

    def handleDownloadNotCompleted(
        self, temp_dir: str, cancelled: bool = False
    ) -> None:
        """
        Cleanup download file and signal we're done
        :param temp_dir: the directory into which the file was downloaded
        :param cancelled: if True, the user cancelled the download
        """

        # Delete the temporary directory and any file in it
        shutil.rmtree(temp_dir, ignore_errors=True)
        self.fileDownloaded.emit("", cancelled)

    @pyqtSlot(str, str)
    def download(self, tarball_url: str, md5_url: str):
        """
        Downloads tarball from website e.g. Launchpad

        Deletes temp dir if download failed.

        Emits:
         - download size
         - bytes downloaded
         - filename if successful, blank filename if not

        :param tarball_url: tarball to download
        :param md5_url: md5sum of the download. If empty or None,
         will not do md5sum check for the download.
        """

        temp_dir = create_temp_dir()
        if temp_dir is not None:
            try:
                r = requests.get(tarball_url, stream=True)
                assert r.status_code == 200
                local_file = os.path.join(temp_dir, tarball_url.split("/")[-1])
                chunk_size = 1024
                bytes_downloaded = 0
                total_size = int(r.headers["content-length"])
                self.downloadSize.emit(total_size)
                terminated = False
                with open(local_file, "wb") as f:
                    for chunk in r.iter_content(chunk_size=chunk_size):
                        cmd = self.checkForCmd()
                        if cmd is None:
                            if chunk:  # filter out keep-alive new chunks
                                f.write(chunk)
                                bytes_downloaded += chunk_size
                                self.bytesDownloaded.emit(
                                    min(total_size, bytes_downloaded)
                                )
                        else:
                            assert cmd == b"STOP"
                            terminated = True
                            break
                if terminated:
                    self.handleDownloadNotCompleted(temp_dir=temp_dir, cancelled=True)
                else:
                    try:
                        if self.verifyDownload(local_file, md5_url):
                            self.fileDownloaded.emit(local_file, False)
                        else:
                            self.handleDownloadNotCompleted(temp_dir=temp_dir)
                    except Exception:
                        self.handleDownloadNotCompleted(temp_dir=temp_dir)

            except Exception as e:
                logging.exception("Failed to download %s", tarball_url)
                self.handleDownloadNotCompleted(temp_dir=temp_dir)


class NewVersionCheckDialog(QDialog):
    """
    Dialog that shows to the user that the program is either checking for a new version
    or the results of such a check. The idea is to not create a temporary dialog to show
    it is checking and then another to show the results.

    As such, it has different states.  Each state is associated with different buttons
    and a different message.
    """

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.rapidApp = parent  # type: 'RapidWindow'

        self.setModal(True)
        self.setSizeGripEnabled(False)

        self.dialog_detailed_result = None
        self.current_state = CheckNewVersionDialogState.check

        self.checkingLabel = QLabel(_("Checking for new version..."))
        self.noNewVersion = QLabel(_("You are running the latest version."))
        self.failedToCheck = QLabel(_("Failed to contact the update server."))
        self.url = "http://www.damonlynch.net/rapid/download.html"
        self.new_version_message = _(
            "A new version of Rapid Photo Downloader (%s) is available."
        )
        self.new_version_message = "<b>{}</b>".format(self.new_version_message)
        self.download_it = _("Do you want to download the new version?") + "<br>"
        self.changelog_msg = _(
            'Changes in the new release can be viewed <a href="%s">here</a>.'
        )

        for label in (self.checkingLabel, self.noNewVersion, self.failedToCheck):
            label.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        self.newVersion = QLabel(
            self._makeDownloadMsg("1.2.3a10", offer_download=True, changelog_url="")
        )
        self.newVersion.setOpenExternalLinks(True)

        self.changelog = QLabel(self.changelog_msg)
        self.changelog.setOpenExternalLinks(True)

        self.messages = QStackedWidget()
        self.messages.addWidget(self.checkingLabel)
        self.messages.addWidget(self.noNewVersion)
        self.messages.addWidget(self.newVersion)
        self.messages.addWidget(self.failedToCheck)

        cancelBox = QDialogButtonBox(QDialogButtonBox.Cancel)
        translateDialogBoxButtons(cancelBox)
        cancelBox.rejected.connect(self.reject)

        self.downloadItBox = QDialogButtonBox(
            QDialogButtonBox.Yes | QDialogButtonBox.No
        )
        translateDialogBoxButtons(self.downloadItBox)
        # Translators: this text appears in a button - the & sets the s key in
        # combination with the alt key to act as the keyboard shortcut
        self.dlItSkipButton = QPushButton(_("&Skip this release"))
        self.dlItSkipButton.setDefault(False)
        self.downloadItBox.addButton(self.dlItSkipButton, QDialogButtonBox.RejectRole)
        self.dlItYesButton = self.downloadItBox.button(
            QDialogButtonBox.Yes
        )  # type: QPushButton
        self.dlItNoButton = self.downloadItBox.button(
            QDialogButtonBox.No
        )  # type: QPushButton
        self.downloadItBox.clicked.connect(self.downloadItClicked)

        closeBox = QDialogButtonBox(QDialogButtonBox.Close)
        translateDialogBoxButtons(closeBox)
        closeBox.rejected.connect(self.reject)

        openDownloadPageBox = QDialogButtonBox(QDialogButtonBox.Close)
        translateDialogBoxButtons(openDownloadPageBox)
        # Translators: this text appears in a button - the & sets the s key in
        # combination with the alt key to act as the keyboard shortcut
        self.openDlPageSkipButton = QPushButton(_("&Skip this release"))
        # Translators: this text appears in a button - the & sets the o key in
        # combination with the alt key to act as the keyboard shortcut
        self.openDlPageButton = QPushButton(_("&Open Download Page"))
        self.openDlPageButton.setDefault(True)
        openDownloadPageBox.addButton(
            self.openDlPageSkipButton, QDialogButtonBox.RejectRole
        )
        openDownloadPageBox.addButton(
            self.openDlPageButton, QDialogButtonBox.ActionRole
        )
        self.openDlCloseButton = openDownloadPageBox.button(QDialogButtonBox.Close)
        openDownloadPageBox.clicked.connect(self.openWebsiteClicked)

        self.buttons = QStackedWidget()
        self.buttons.addWidget(cancelBox)
        self.buttons.addWidget(closeBox)
        self.buttons.addWidget(self.downloadItBox)
        self.buttons.addWidget(openDownloadPageBox)

        self.messages.setCurrentIndex(0)
        self.buttons.setCurrentIndex(0)

        grid = QGridLayout()
        grid.addWidget(self.messages, 0, 0, 1, 2, Qt.AlignTop)
        grid.addWidget(self.buttons, 1, 0, 1, 2)
        self.setLayout(grid)
        self.setWindowTitle(_("Rapid Photo Downloader updates"))

    def _makeDownloadMsg(
        self, new_version_number: str, offer_download: bool, changelog_url: str
    ) -> str:
        s1 = self.new_version_message % new_version_number
        s2 = self.changelog_msg % changelog_url
        s = "{}<br><br>{}".format(s1, s2)
        if offer_download:
            return "<br><br>".join((s, self.download_it))
        else:
            return s

    def displayUserMessage(
        self,
        new_state: CheckNewVersionDialogState,
        version: Optional[str] = None,
        download_page: Optional[str] = None,
        changelog_url: Optional[str] = None,
    ) -> None:

        self.current_state = new_state

        if new_state == CheckNewVersionDialogState.check:
            self.messages.setCurrentIndex(0)
            self.buttons.setCurrentIndex(0)
        elif new_state == CheckNewVersionDialogState.failed_to_contact:
            self.messages.setCurrentIndex(3)
            self.buttons.setCurrentIndex(1)
        elif new_state == CheckNewVersionDialogState.have_latest_version:
            self.messages.setCurrentIndex(1)
            self.buttons.setCurrentIndex(1)
        else:
            assert new_state in (
                CheckNewVersionDialogState.open_website,
                CheckNewVersionDialogState.prompt_for_download,
            )
            assert version is not None
            assert changelog_url is not None
            self.new_version_number = version
            self.url = download_page
            offer_download = new_state == CheckNewVersionDialogState.prompt_for_download
            self.newVersion.setText(
                self._makeDownloadMsg(
                    version, offer_download=offer_download, changelog_url=changelog_url
                )
            )
            self.messages.setCurrentIndex(2)
            if offer_download:
                self.buttons.setCurrentIndex(2)
                yesButton = self.downloadItBox.button(
                    QDialogButtonBox.Yes
                )  # type: QPushButton
                yesButton.setDefault(True)

            else:
                self.buttons.setCurrentIndex(3)

    def reset(self) -> None:
        """
        Reset appearance to default checking...
        """
        self.current_state = CheckNewVersionDialogState.check
        self.messages.setCurrentIndex(0)
        self.buttons.setCurrentIndex(0)

    def downloadItClicked(self, button) -> None:
        if button == self.dlItYesButton:
            self.setResult(QDialog.Accepted)
            self.dialog_detailed_result = CheckNewVersionDialogResult.download
            super().accept()
        elif button == self.dlItNoButton:
            self.setResult(QDialog.Rejected)
            self.dialog_detailed_result = CheckNewVersionDialogResult.do_not_download
            super().reject()
        else:
            assert button == self.dlItSkipButton
            self.setResult(QDialog.Rejected)
            self.dialog_detailed_result = CheckNewVersionDialogResult.skip
            super().reject()

    def openWebsiteClicked(self, button) -> None:
        if button == self.openDlPageButton:
            self.setResult(QDialog.Accepted)
            self.dialog_detailed_result = CheckNewVersionDialogResult.open_website
            super().accept()
        elif button == self.openDlCloseButton:
            self.setResult(QDialog.Rejected)
            self.dialog_detailed_result = CheckNewVersionDialogResult.do_not_download
            super().reject()
        else:
            assert button == self.openDlPageSkipButton
            self.setResult(QDialog.Rejected)
            self.dialog_detailed_result = CheckNewVersionDialogResult.skip
            super().reject()


class DownloadNewVersionDialog(QDialog):
    def __init__(
        self, parent=None, bytes_downloaded: int = 0, download_size: int = 0
    ) -> None:
        super().__init__(parent)
        self.rapidApp = parent  # type: 'RapidWindow'

        self.setModal(True)
        self.setSizeGripEnabled(False)

        self.download_size_display = format_size_for_user(
            download_size, zero_string="0 KB"
        )
        bytes_downloaded_display = format_size_for_user(
            bytes_downloaded, zero_string="0 KB"
        )

        # Translators: shows how much of a file has been downloaded e.g  123 KB of
        # 1.3 MB
        # Translators: %(variable)s represents Python code, not a plural of the term
        # variable. You must keep the %(variable)s untranslated, or the program will
        # crash.
        self.text = _("%(downloaded)s of %(total)s")
        self.message = QLabel(
            self.text
            % dict(
                downloaded=bytes_downloaded_display, total=self.download_size_display
            )
        )

        self.progressBar = QProgressBar()
        self.progressBar.setMinimumWidth(standardProgressBarWidth())
        self.progressBar.setMaximum(download_size)
        self.progressBar.setValue(bytes_downloaded)

        buttonBox = QDialogButtonBox(QDialogButtonBox.Cancel)
        translateDialogBoxButtons(buttonBox)
        buttonBox.rejected.connect(self.reject)

        grid = QGridLayout()
        grid.addWidget(self.message, 0, 0, 1, 2)
        grid.addWidget(self.progressBar, 1, 0, 1, 2)
        grid.addWidget(buttonBox, 2, 0, 1, 2)
        self.setLayout(grid)
        self.setWindowTitle(_("Downloading..."))

    def updateProgress(self, bytes_downloaded: int) -> None:
        bytes_downloaded_display = format_size_for_user(
            bytes_downloaded, zero_string="0 KB"
        )
        self.message.setText(
            self.text
            % dict(
                downloaded=bytes_downloaded_display, total=self.download_size_display
            )
        )
        self.progressBar.setValue(bytes_downloaded)

    def setDownloadSize(self, download_size: int) -> None:
        self.download_size_display = format_size_for_user(
            download_size, zero_string="0 KB"
        )
        self.progressBar.setMaximum(download_size)
