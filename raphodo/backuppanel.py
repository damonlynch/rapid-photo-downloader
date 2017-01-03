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
Display backup preferences
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2017, Damon Lynch"

from typing import Optional, Dict, Tuple, Union
import logging
from gettext import gettext as _


from PyQt5.QtCore import (Qt, pyqtSlot)
from PyQt5.QtWidgets import (QWidget, QSizePolicy, QComboBox, QFormLayout,
                             QVBoxLayout, QLabel, QLineEdit, QFileDialog, QCheckBox, QPushButton,
                             QScrollArea, QFrame, QGridLayout)
from PyQt5.QtGui import (QColor, QPalette, QIcon)


from raphodo.constants import (StandardFileLocations, ThumbnailBackgroundName, FileType,
                               minGridColumnWidth)
from raphodo.viewutils import QFramedWidget
from raphodo.panelview import QPanelView
from raphodo.preferences import Preferences
from raphodo.foldercombo import FolderCombo
import raphodo.qrc_resources as qrc_resources
from raphodo.storage import (ValidMounts, )



class BackupOptionsWidget(QFramedWidget):
    """
    Display and allow editing of preference values for Downloads today
    and Stored Sequence Number and associated options, as well as
    the strip incompatible characters option.
    """

    def __init__(self, prefs: Preferences, parent, rapidApp) -> None:
        super().__init__(parent)

        self.rapidApp = rapidApp
        self.prefs = prefs

        self.setBackgroundRole(QPalette.Base)
        self.setAutoFillBackground(True)

        backupLayout = QGridLayout()
        layout = QVBoxLayout()
        layout.addLayout(backupLayout)
        self.setLayout(layout)

        self.backupExplanation = QLabel(_('You can have your photos and videos backed up to '
                                          'multiple locations as they are downloaded, e.g. '
                                          'external hard drives.'))
        self.backupExplanation.setWordWrap(True)

        self.backup = QCheckBox(_('Back up photos and videos when downloading'))
        self.backup.setChecked(self.prefs.backup_files)
        self.backup.stateChanged.connect(self.backupChanged)

        self.autoBackup = QCheckBox(_('Automatically detect backup devices'))
        self.autoBackup.setChecked(self.prefs.backup_device_autodetection)
        self.autoBackup.stateChanged.connect(self.autoBackupChanged)

        self.folderExplanation = QLabel(_('Specify the folder in which backups are stored on the '
                                          'device.<br><br>'
                                          '<i>Note: this will also be used to determine whether or '
                                          'not the device is used for backups. For each device you '
                                          'wish to use for backing up to, create a folder in it '
                                          'with one of these names.</i>'))
        self.folderExplanation.setWordWrap(True)

        self.photoFolderNameLabel = QLabel(_('Photo backup folder name:'))
        self.photoFolderName = QLineEdit()
        self.videoFolderNameLabel = QLabel(_('Video backup folder name:'))
        self.videoFolderName = QLineEdit()

        valid_mounts = ValidMounts(onlyExternalMounts=True)

        self.manualLocationExplanation = QLabel(_('If you disable automatic detection, choose the '
                                                  'exact backup locations.'))
        self.photoLocationLabel = QLabel(_('Photo backup location:'))
        self.photoLocation = FolderCombo(self, prefs=self.prefs, file_type=FileType.photo,
                                         file_chooser_title=_('Select Photo Backup Location'),
                                         special_dirs=(StandardFileLocations.pictures,),
                                         valid_mounts=valid_mounts)
        self.photoLocation.setPath(self.prefs.backup_photo_location)
        self.photoLocation.pathChosen.connect(self.photoPathChosen)

        self.videoLocationLabel = QLabel(_('Video backup location:'))
        self.videoLocation = FolderCombo(self, prefs=self.prefs, file_type=FileType.video,
                                         file_chooser_title=_('Select Video Backup Location'),
                                         special_dirs=(StandardFileLocations.videos, ),
                                         valid_mounts=valid_mounts)
        self.videoLocation.setPath(self.prefs.backup_video_location)
        self.videoLocation.pathChosen.connect(self.videoPathChosen)

        backupLayout.addWidget(self.backupExplanation, 0, 0, 1, 4)
        backupLayout.addWidget(self.backup, 1, 0, 1, 4)
        backupLayout.addWidget(self.autoBackup, 2, 1, 1, 3)
        backupLayout.addWidget(self.folderExplanation, 3, 2, 1, 2)
        backupLayout.addWidget(self.photoFolderNameLabel, 4, 2, 1, 1)
        backupLayout.addWidget(self.photoFolderName, 4, 3, 1, 1)
        backupLayout.addWidget(self.videoFolderNameLabel, 5, 2, 1, 1)
        backupLayout.addWidget(self.videoFolderName, 5, 3, 1, 1)
        backupLayout.addWidget(self.manualLocationExplanation, 6, 1, 1, 3)
        backupLayout.addWidget(self.photoLocationLabel, 7, 1, 1, 2)
        backupLayout.addWidget(self.photoLocation, 7, 3, 1, 1)
        backupLayout.addWidget(self.videoLocationLabel, 8, 1, 1, 2)
        backupLayout.addWidget(self.videoLocation, 8, 3, 1, 1)

        min_width = minGridColumnWidth()
        backupLayout.setColumnMinimumWidth(0, min_width)
        backupLayout.setColumnMinimumWidth(1, min_width)

        layout.addStretch()

        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.setBackupButtonHighlight()

        # Group controls to enable / disable sets of them
        self._backup_controls_type = (self.autoBackup, )
        self._backup_controls_auto = (self.folderExplanation, self.photoFolderNameLabel,
                                      self.photoFolderName, self.videoFolderNameLabel,
                                      self.videoFolderName, )
        self._backup_controls_manual = (self.manualLocationExplanation, self.photoLocationLabel,
                                        self.photoLocation, self.videoLocationLabel,
                                        self.videoLocation, )
        self.enableControlsByBackupType()


    @pyqtSlot(int)
    def backupChanged(self, state: int) -> None:
        backup = state == Qt.Checked
        logging.info("Setting backup while downloading to %s", backup)
        self.prefs.backup_files = backup
        self.setBackupButtonHighlight()
        self.enableControlsByBackupType()

    @pyqtSlot(int)
    def autoBackupChanged(self, state: int) -> None:
        autoBackup = state == Qt.Checked
        logging.info("Setting automatically detect backup devices to %s", autoBackup)
        self.prefs.backup_device_autodetection = autoBackup
        self.setBackupButtonHighlight()
        self.enableControlsByBackupType()

    @pyqtSlot(str)
    def photoPathChosen(self, path: str) -> None:
        logging.info("Setting backup photo location to %s", path)
        self.prefs.backup_photo_location = path
        self.setBackupButtonHighlight()

    @pyqtSlot(str)
    def videoPathChosen(self, path: str) -> None:
        logging.info("Setting backup video location to %s", path)
        self.prefs.backup_video_location = path
        self.setBackupButtonHighlight()

    def setBackupButtonHighlight(self) -> None:
        """
        Indicate error status in GUI by highlighting Backup button.

        Do so only if doing manual backups and there is a problem with one of the paths
        """

        self.rapidApp.backupButton.setHighlighted(
            self.prefs.backup_files and not self.prefs.backup_device_autodetection and (
                self.photoLocation.invalid_path or self.videoLocation.invalid_path))

    def enableControlsByBackupType(self) -> None:
        """
        Enable or disable backup controls depending on what the user
        has enabled.
        """

        backupsEnabled = self.backup.isChecked()
        autoEnabled = backupsEnabled and self.autoBackup.isChecked()
        manualEnabled = not autoEnabled and backupsEnabled

        for widget in self._backup_controls_type:
            widget.setEnabled(backupsEnabled)
        for widget in self._backup_controls_manual:
            widget.setEnabled(manualEnabled)
        for widget in self._backup_controls_auto:
            widget.setEnabled(autoEnabled)


class BackupPanel(QScrollArea):
    """
    Backup preferences widget, for photos and video backups while
    downloading.
    """

    def __init__(self,  parent) -> None:
        super().__init__(parent)
        if parent is not None:
            self.rapidApp = parent
            self.prefs = self.rapidApp.prefs
        else:
            self.prefs = None

        self.setFrameShape(QFrame.NoFrame)

        self.backupOptionsPanel = QPanelView(label=_('Backup Options'),
                                       headerColor=QColor(ThumbnailBackgroundName),
                                       headerFontColor=QColor(Qt.white))

        self.backupOptions = BackupOptionsWidget(prefs=self.prefs, parent=self,
                                                 rapidApp=self.rapidApp)
        self.backupOptionsPanel.addWidget(self.backupOptions)

        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        widget.setLayout(layout)
        layout.addWidget(self.backupOptionsPanel)
        self.setWidget(widget)
        self.setWidgetResizable(True)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)





