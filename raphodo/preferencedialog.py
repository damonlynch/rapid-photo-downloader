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
Dialog window to show and manipulate selected user preferences
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2017, Damon Lynch"

import webbrowser
from typing import List
from gettext import gettext as _


from PyQt5.QtCore import (Qt, pyqtSlot, pyqtSignal, QObject, QThread, QTimer)
from PyQt5.QtWidgets import (
    QWidget, QSizePolicy, QComboBox, QVBoxLayout, QLabel, QLineEdit, QSpinBox, QGridLayout,
    QAbstractItemView, QListWidgetItem, QHBoxLayout, QDialog, QDialogButtonBox, QCheckBox,
    QStyle, QStackedWidget, QApplication, QPushButton, QGroupBox,  QFormLayout, QMessageBox,
    QButtonGroup, QRadioButton, QAbstractButton
)
from PyQt5.QtGui import (QShowEvent, QCloseEvent, QMouseEvent)

from raphodo.preferences import Preferences
from raphodo.constants import KnownDeviceType
from raphodo.viewutils import QNarrowListWidget
from raphodo.utilities import available_cpu_count, format_size_for_user, thousands
from raphodo.cache import ThumbnailCacheSql
from raphodo.constants import ConflictResolution
from raphodo.utilities import current_version_is_dev_version, make_internationalized_list
from raphodo.rpdfile import (ALL_KNOWN_EXTENSIONS, PHOTO_EXTENSIONS, VIDEO_EXTENSIONS,
    VIDEO_THUMBNAIL_EXTENSIONS, AUDIO_EXTENSIONS)


class ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.clicked.emit()


class PreferencesDialog(QDialog):
    """
    Preferences dialog for those preferences that are not adjusted via the main window

    Note:

    When pref value generate_thumbnails is made False, pref values use_thumbnail_cache and
    generate_thumbnails are not changed, even though the preference value shown to the user
    shows False (to indicate that the activity will not occur).
    """

    getCacheSize = pyqtSignal()

    def __init__(self, prefs: Preferences, parent=None) -> None:
        super().__init__(parent=parent)

        self.rapidApp = parent

        self.setWindowTitle(_('Preferences'))

        self.prefs = prefs

        self.is_prerelease = current_version_is_dev_version()

        self.panels = QStackedWidget()

        self.chooser = QNarrowListWidget()
        self.chooser_items = (_('Devices'), _('Automation'), _('Thumbnails'), _('Error Handling'),
                              _('Warnings'), _('Miscellaneous'))
        self.chooser.addItems(self.chooser_items )
        self.chooser.currentRowChanged.connect(self.rowChanged)
        self.chooser.setSelectionMode(QAbstractItemView.SingleSelection)
        self.chooser.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.MinimumExpanding)

        self.devices = QWidget()

        self.scanBox = QGroupBox(_('Device Scanning'))
        scanLayout = QVBoxLayout()
        self.onlyExternal = QCheckBox(_('Scan only external devices'))
        self.onlyExternal.setToolTip(_(
            'Scan for photos and videos only on devices that are external to the computer,\n'
            'including cameras, memory cards, external hard drives, and USB flash drives.'
        ))

        self.noDcim = QCheckBox(_('Scan non-camera devices lacking a DCIM folder'))
        tip = _(
            'Scan the entirety of a device for photos and videos, irrespective of whether it '
            'contains a DCIM folder,\n'
            'as opposed to only scanning within a DCIM folder.\n\n'
            'Changing this setting causes all devices to be scanned again.\n\n'
            'Note: With cameras, only the DCIM folder is scanned.'
        )
        self.noDcim.setToolTip(tip)

        scanLayout.addWidget(self.onlyExternal)
        scanLayout.addWidget(self.noDcim)
        self.scanBox.setLayout(scanLayout)

        tip = _('Devices that have been set to automatically ignore or download from.')
        self.knownDevicesBox = QGroupBox(_('Remembered Devices'))
        self.knownDevices = QNarrowListWidget(minimum_rows=5)
        self.knownDevices.setToolTip(tip)
        tip = _(
            'Remove a device from the list of devices to automatically ignore or download from.'
        )
        self.removeDevice = QPushButton(_('Remove'))
        self.removeDevice.setToolTip(tip)
        self.removeAllDevice = QPushButton(_('Remove All'))
        tip = _(
            'Clear the list of devices from which to automatically ignore or download from.\n\n'
            'Note: Changes take effect when the computer is next scanned for devices.'
        )
        self.removeAllDevice.setToolTip(tip)
        self.removeDevice.clicked.connect(self.removeDeviceClicked)
        self.removeAllDevice.clicked.connect(self.removeAllDeviceClicked)
        knownDevicesLayout = QGridLayout()
        knownDevicesLayout.setHorizontalSpacing(18)
        knownDevicesLayout.addWidget(self.knownDevices, 0, 0, 3, 1)
        knownDevicesLayout.addWidget(self.removeDevice, 0, 1, 1, 1)
        knownDevicesLayout.addWidget(self.removeAllDevice, 1, 1, 1, 1)
        self.knownDevicesBox.setLayout(knownDevicesLayout)

        self.ignoredPathsBox = QGroupBox(_('Ignored Paths'))
        tip = _('The end part of a path that should never be scanned for photos or videos.')
        self.ignoredPaths = QNarrowListWidget(minimum_rows=4)
        self.ignoredPaths.setToolTip(tip)
        self.addPath = QPushButton(_('Add...'))
        self.addPath.setToolTip(_(
            'Add a path to the list of paths to ignore.\n\n'
            'Changing this setting causes all devices to be scanned again.'
        ))
        self.removePath = QPushButton(_('Remove'))
        self.removePath.setToolTip(_(
            'Remove a path from the list of paths to ignore.\n\n'
            'Changing this setting causes all devices to be scanned again.'
        ))
        self.removeAllPath = QPushButton(_('Remove All'))
        self.removeAllPath.setToolTip(_(
            'Clear the list of paths to ignore.\n\n'
            'Changing this setting causes all devices to be scanned again.'
        ))
        self.addPath.clicked.connect(self.addPathClicked)
        self.removePath.clicked.connect(self.removePathClicked)
        self.removeAllPath.clicked.connect(self.removeAllPathClicked)
        self.ignoredPathsRe = QCheckBox()
        self.ignorePathsReLabel = ClickableLabel(
            _('Use python-style '
              '<a href="http://damonlynch.net/rapid/documentation/#regularexpressions">regular '
              'expressions</a>'))
        self.ignorePathsReLabel.setToolTip(_(
            'Use regular expressions in the list of ignored paths.\n\n'
            'Changing this setting causes all devices to be scanned again.'
        ))
        self.ignorePathsReLabel.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.ignorePathsReLabel.setOpenExternalLinks(True)
        self.ignorePathsReLabel.clicked.connect(self.ignorePathsReLabelClicked)
        reLayout = QHBoxLayout()
        reLayout.setSpacing(5)
        reLayout.addWidget(self.ignoredPathsRe)
        reLayout.addWidget(self.ignorePathsReLabel)
        reLayout.addStretch()
        ignoredPathsLayout = QGridLayout()
        ignoredPathsLayout.setHorizontalSpacing(18)
        ignoredPathsLayout.addWidget(self.ignoredPaths, 0, 0, 4, 1)
        ignoredPathsLayout.addWidget(self.addPath, 0, 1, 1, 1)
        ignoredPathsLayout.addWidget(self.removePath, 1, 1, 1, 1)
        ignoredPathsLayout.addWidget(self.removeAllPath, 2, 1, 1, 1)
        ignoredPathsLayout.addLayout(reLayout, 4, 0, 1, 2)
        self.ignoredPathsBox.setLayout(ignoredPathsLayout)

        self.setDeviceWidgetValues()

        # connect these next 3 only after having set their values, so rescan / search again
        # in rapidApp is not triggered
        self.onlyExternal.stateChanged.connect(self.onlyExternalChanged)
        self.noDcim.stateChanged.connect(self.noDcimChanged)
        self.ignoredPathsRe.stateChanged.connect(self.ignoredPathsReChanged)

        devicesLayout = QVBoxLayout()
        devicesLayout.addWidget(self.scanBox)
        devicesLayout.addWidget(self.knownDevicesBox)
        devicesLayout.addWidget(self.ignoredPathsBox)
        devicesLayout.addStretch()
        devicesLayout.setSpacing(18)

        self.devices.setLayout(devicesLayout)
        devicesLayout.setContentsMargins(0, 0, 0, 0)

        self.automation = QWidget()

        self.automationBox = QGroupBox(_('Program Automation'))
        self.autoDownloadStartup = QCheckBox(_('Start downloading at program startup'))
        self.autoDownloadInsertion = QCheckBox(_('Start downloading upon device insertion'))
        self.autoEject = QCheckBox(_('Unmount (eject) device upon download completion'))
        self.autoExit = QCheckBox(_('Exit program when download completes'))
        self.autoExitError = QCheckBox(_('Exit program even if download had warnings or errors'))
        self.setAutomationWidgetValues()
        self.autoDownloadStartup.stateChanged.connect(self.autoDownloadStartupChanged)
        self.autoDownloadInsertion.stateChanged.connect(self.autoDownloadInsertionChanged)
        self.autoEject.stateChanged.connect(self.autoEjectChanged)
        self.autoExit.stateChanged.connect(self.autoExitChanged)
        self.autoExitError.stateChanged.connect(self.autoExitErrorChanged)

        automationBoxLayout = QGridLayout()
        automationBoxLayout.addWidget(self.autoDownloadStartup, 0, 0, 1, 2)
        automationBoxLayout.addWidget(self.autoDownloadInsertion, 1, 0, 1, 2)
        automationBoxLayout.addWidget(self.autoEject, 2, 0, 1, 2)
        automationBoxLayout.addWidget(self.autoExit, 3, 0, 1, 2)
        automationBoxLayout.addWidget(self.autoExitError, 4, 1, 1, 1)
        checkbox_width = self.autoExit.style().pixelMetric(QStyle.PM_IndicatorWidth)
        automationBoxLayout.setColumnMinimumWidth(0, checkbox_width)
        self.automationBox.setLayout(automationBoxLayout)

        automationLayout = QVBoxLayout()
        automationLayout.addWidget(self.automationBox)
        automationLayout.addStretch()
        automationLayout.setContentsMargins(0, 0, 0, 0)

        self.automation.setLayout(automationLayout)

        self.performance = QWidget()

        self.performanceBox = QGroupBox(_('Thumbnail Generation'))
        self.generateThumbnails = QCheckBox(_('Generate thumbnails'))
        self.generateThumbnails.setToolTip(_('Generate thumbnails to show in the main program '
                                             'window'))
        self.useThumbnailCache = QCheckBox(_('Cache thumbnails'))
        self.useThumbnailCache.setToolTip(_("Save thumbnails shown in the main program window in "
                                            "a thumbnail cache unique to Rapid Photo Downloader"))
        self.fdoThumbnails = QCheckBox(_('Generate system thumbnails'))
        self.fdoThumbnails.setToolTip(_('While downloading, save thumbnails that can be used by '
                                        'desktop file managers and other programs'))
        self.generateThumbnails.stateChanged.connect(self.generateThumbnailsChanged)
        self.useThumbnailCache.stateChanged.connect(self.useThumbnailCacheChanged)
        self.fdoThumbnails.stateChanged.connect(self.fdoThumbnailsChanged)
        self.maxCores = QComboBox()
        self.maxCores.setEditable(False)
        tip = _('Number of CPU cores used to generate thumbnails.')
        self.coresLabel = QLabel(_('CPU cores:'))
        self.coresLabel.setToolTip(tip)
        self.maxCores.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.maxCores.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.maxCores.setToolTip(tip)

        self.setPerformanceValues()

        self.maxCores.currentIndexChanged.connect(self.maxCoresChanged)

        coresLayout = QHBoxLayout()
        coresLayout.addWidget(self.coresLabel)
        coresLayout.addWidget(self.maxCores)
        # Translators: the * acts as an asterisk to denote a reference to an annotation
        # such as '* Takes effect upon program restart'
        coresLayout.addWidget(QLabel(_('*')))
        coresLayout.addStretch()

        performanceBoxLayout = QVBoxLayout()
        performanceBoxLayout.addWidget(self.generateThumbnails)
        performanceBoxLayout.addWidget(self.useThumbnailCache)
        performanceBoxLayout.addWidget(self.fdoThumbnails)
        performanceBoxLayout.addLayout(coresLayout)
        self.performanceBox.setLayout(performanceBoxLayout)

        self.thumbnail_cache = ThumbnailCacheSql()

        self.cacheSize = CacheSize()
        self.cacheSizeThread = QThread()
        self.cacheSizeThread.started.connect(self.cacheSize.start)
        self.getCacheSize.connect(self.cacheSize.getCacheSize)
        self.cacheSize.size.connect(self.setCacheSize)
        self.cacheSize.moveToThread(self.cacheSizeThread)

        QTimer.singleShot(0, self.cacheSizeThread.start)

        self.getCacheSize.emit()

        self.cacheBox = QGroupBox(_('Thumbnail Cache'))
        self.thumbnailCacheSize = QLabel()
        self.thumbnailCacheSize.setText(_('Calculating...'))
        self.thumbnailNumber = QLabel()
        self.thumbnailSqlSize = QLabel()
        self.thumbnailCacheDaysKeep = QSpinBox()
        self.thumbnailCacheDaysKeep.setMinimum(0)
        self.thumbnailCacheDaysKeep.setMaximum(360*3)
        self.thumbnailCacheDaysKeep.setSuffix(' ' + _('days'))
        self.thumbnailCacheDaysKeep.setSpecialValueText(_('forever'))
        self.thumbnailCacheDaysKeep.valueChanged.connect(self.thumbnailCacheDaysKeepChanged)

        cacheBoxLayout = QVBoxLayout()
        cacheLayout = QGridLayout()
        cacheLayout.addWidget(QLabel(_('Cache size:')), 0, 0, 1, 1)
        cacheLayout.addWidget(self.thumbnailCacheSize, 0, 1, 1, 1)
        cacheLayout.addWidget(QLabel(_('Number of thumbnails:')), 1, 0, 1, 1)
        cacheLayout.addWidget(self.thumbnailNumber, 1, 1, 1, 1)
        cacheLayout.addWidget(QLabel(_('Database size:')), 2, 0, 1, 1)
        cacheLayout.addWidget(self.thumbnailSqlSize, 2, 1, 1, 1)
        cacheLayout.addWidget(QLabel(_('Cache unaccessed thumbnails for:')), 3, 0, 1, 1)
        cacheDays = QHBoxLayout()
        cacheDays.addWidget(self.thumbnailCacheDaysKeep)
        cacheDays.addWidget(QLabel(_('*')))
        cacheLayout.addLayout(cacheDays, 3, 1, 1, 1)
        cacheBoxLayout.addLayout(cacheLayout)

        cacheButtons = QDialogButtonBox()
        self.purgeCache = cacheButtons.addButton(_('Purge Cache...'), QDialogButtonBox.ResetRole)
        self.optimizeCache = cacheButtons.addButton(_('Optimize Cache...'),
                                                    QDialogButtonBox.ResetRole)
        self.purgeCache.clicked.connect(self.purgeCacheClicked)
        self.optimizeCache.clicked.connect(self.optimizeCacheClicked)

        cacheBoxLayout.addWidget(cacheButtons)

        self.cacheBox.setLayout(cacheBoxLayout)
        self.setCacheValues()

        performanceLayout = QVBoxLayout()
        performanceLayout.addWidget(self.performanceBox)
        performanceLayout.addWidget(self.cacheBox)
        performanceLayout.addWidget(QLabel(_('* Takes effect upon program restart')))
        performanceLayout.addStretch()
        performanceLayout.setContentsMargins(0, 0, 0, 0)
        performanceLayout.setSpacing(18)

        self.performance.setLayout(performanceLayout)

        self.errorBox = QGroupBox(_('Error Handling'))

        self.downloadErrorGroup = QButtonGroup()
        self.skipDownload = QRadioButton(_('Skip download'))
        self.skipDownload.setToolTip(_("Don't download the file, and issue an error message"))
        self.addIdentifier = QRadioButton(_('Add unique identifier'))
        self.addIdentifier.setToolTip(_("Add an identifier like _1 or _2 to the end of the "
                                        "filename, immediately before the file's extension"))
        self.downloadErrorGroup.addButton(self.skipDownload)
        self.downloadErrorGroup.addButton(self.addIdentifier)

        self.backupErrorGroup = QButtonGroup()
        self.overwriteBackup = QRadioButton(_('Overwrite'))
        self.overwriteBackup.setToolTip(_("Overwrite the previously backed up file"))
        self.skipBackup = QRadioButton(_('Skip'))
        self.skipBackup.setToolTip(_("Don't overwrite the backup file, and issue an error "
                                       "message"))
        self.backupErrorGroup.addButton(self.overwriteBackup)
        self.backupErrorGroup.addButton(self.skipBackup)

        errorBoxLayout = QVBoxLayout()
        lbl = _('When a photo or video of the same name has already been downloaded, choose '
                'whether to skip downloading the file, or to add a unique identifier:')
        self.downloadError = QLabel(lbl)
        self.downloadError.setWordWrap(True)
        errorBoxLayout.addWidget(self.downloadError)
        errorBoxLayout.addWidget(self.skipDownload)
        errorBoxLayout.addWidget(self.addIdentifier)
        lbl = '<i>' + ('Using sequence numbers to automatically generate unique filenames is '
                       'strongly recommended. Configure file renaming in the Rename panel in the '
                       'main window.') + '</i>'
        self.recommended = QLabel(lbl)
        self.recommended.setWordWrap(True)
        errorBoxLayout.addWidget(self.recommended)
        errorBoxLayout.addSpacing(18)
        lbl = _('When backing up, choose whether to overwrite a file on the backup device that '
              'has the same name, or skip backing it up:')
        self.backupError = QLabel(lbl)
        self.backupError.setWordWrap(True)
        errorBoxLayout.addWidget(self.backupError)
        errorBoxLayout.addWidget(self.overwriteBackup)
        errorBoxLayout.addWidget(self.skipBackup)
        self.errorBox.setLayout(errorBoxLayout)

        self.setErrorHandingValues()
        self.downloadErrorGroup.buttonClicked.connect(self.downloadErrorGroupClicked)
        self.backupErrorGroup.buttonClicked.connect(self.backupErrorGroupClicked)

        self.errorWidget = QWidget()
        errorLayout = QVBoxLayout()
        self.errorWidget.setLayout(errorLayout)
        errorLayout.addWidget(self.errorBox)
        errorLayout.addStretch()
        errorLayout.setContentsMargins(0, 0, 0, 0)

        self.warningBox = QGroupBox(_('Program Warnings'))
        lbl = _('Show a warning when:')
        self.warningLabel = QLabel(lbl)
        self.warningLabel.setWordWrap(True)
        self.warnDownloadingAll = QCheckBox(_('Downloading files currently not displayed'))
        tip = _('Warn when about to download files that are not displayed in the main window.')
        self.warnDownloadingAll.setToolTip(tip)
        self.warnBackupProblem = QCheckBox(_('Backup destinations are missing'))
        tip = _("Warn before starting a download if it is not possible to back up files.")
        self.warnBackupProblem.setToolTip(tip)
        self.warnMissingLibraries = QCheckBox(_('Program libraries are missing or broken'))
        tip = _('Warn if a software library used by Rapid Photo Downloader is missing or not '
                'functioning.')
        self.warnMissingLibraries.setToolTip(tip)
        self.warnMetadata = QCheckBox(_('Filesystem metadata cannot be set'))
        tip = _("Warn if there is an error setting a file's filesystem metadata, "
                "such as its modification time.")
        self.warnMetadata.setToolTip(tip)
        self.warnUnhandledFiles = QCheckBox(_('Encountering unhandled files'))
        tip = _('Warn after scanning a device or this computer if there are unrecognized files '
                'that will not be included in the download.')
        self.warnUnhandledFiles.setToolTip(tip)
        self.exceptTheseFilesLabel = QLabel(_('Do not warn about unhandled files with '
                                              'extensions:'))
        self.exceptTheseFilesLabel.setWordWrap(True)
        self.exceptTheseFiles = QNarrowListWidget(minimum_rows=4)
        tip = _('File extensions are case insensitive and do not need to include the leading '
                'dot.')
        self.exceptTheseFiles.setToolTip(tip)
        self.addExceptFiles = QPushButton(_('Add'))
        tip = _('Add a file extension to the list of unhandled file types to not warn about.')
        self.addExceptFiles.setToolTip(tip)
        tip = _('Remove a file extension from the list of unhandled file types to not warn about.')
        self.removeExceptFiles = QPushButton(_('Remove'))
        self.removeExceptFiles.setToolTip(tip)
        self.removeAllExceptFiles = QPushButton(_('Remove All'))
        tip = _('Clear the list of file extensions of unhandled file types to not warn about.')
        self.removeAllExceptFiles.setToolTip(tip)
        self.addExceptFiles.clicked.connect(self.addExceptFilesClicked)
        self.removeExceptFiles.clicked.connect(self.removeExceptFilesClicked)
        self.removeAllExceptFiles.clicked.connect(self.removeAllExceptFilesClicked)

        self.setWarningValues()
        self.warnDownloadingAll.stateChanged.connect(self.warnDownloadingAllChanged)
        self.warnBackupProblem.stateChanged.connect(self.warnBackupProblemChanged)
        self.warnMissingLibraries.stateChanged.connect(self.warnMissingLibrariesChanged)
        self.warnMetadata.stateChanged.connect(self.warnMetadataChanged)
        self.warnUnhandledFiles.stateChanged.connect(self.warnUnhandledFilesChanged)

        warningBoxLayout = QGridLayout()
        warningBoxLayout.addWidget(self.warningLabel, 0, 0, 1, 3)
        warningBoxLayout.addWidget(self.warnDownloadingAll, 1, 0, 1, 3)
        warningBoxLayout.addWidget(self.warnBackupProblem, 2, 0, 1, 3)
        warningBoxLayout.addWidget(self.warnMissingLibraries, 3, 0, 1, 3)
        warningBoxLayout.addWidget(self.warnMetadata, 4, 0, 1, 3)
        warningBoxLayout.addWidget(self.warnUnhandledFiles, 5, 0, 1, 3)
        warningBoxLayout.addWidget(self.exceptTheseFilesLabel,  6, 1, 1, 2)
        warningBoxLayout.addWidget(self.exceptTheseFiles, 7, 1, 4, 1)
        warningBoxLayout.addWidget(self.addExceptFiles, 7, 2, 1, 1)
        warningBoxLayout.addWidget(self.removeExceptFiles, 8, 2, 1, 1)
        warningBoxLayout.addWidget(self.removeAllExceptFiles, 9, 2, 1, 1)
        warningBoxLayout.setColumnMinimumWidth(0, checkbox_width)
        self.warningBox.setLayout(warningBoxLayout)

        self.warnings = QWidget()
        warningLayout = QVBoxLayout()
        self.warnings.setLayout(warningLayout)
        warningLayout.addWidget(self.warningBox)
        warningLayout.addStretch()
        warningLayout.setContentsMargins(0, 0, 0, 0)

        self.newVersionBox = QGroupBox(_('Version Check'))
        self.checkNewVersion = QCheckBox(_('Check for new version at startup'))
        self.checkNewVersion.setToolTip(_('Check for a new version of the program each time the '
                                          'program starts.'))
        self.includeDevRelease = QCheckBox(_('Include development releases'))
        tip = _('Include alpha, beta and other development releases when checking for a new '
                'version of the program.\n\nIf you are currently running a development version, '
                'the check will always occur.')
        self.includeDevRelease.setToolTip(tip)
        self.setVersionCheckValues()
        self.checkNewVersion.stateChanged.connect(self.checkNewVersionChanged)
        self.includeDevRelease.stateChanged.connect(self.includeDevReleaseChanged)

        newVersionLayout = QGridLayout()
        newVersionLayout.addWidget(self.checkNewVersion, 0, 0, 1, 2)
        newVersionLayout.addWidget(self.includeDevRelease, 1, 1, 1, 1)
        newVersionLayout.setColumnMinimumWidth(0, checkbox_width)
        self.newVersionBox.setLayout(newVersionLayout)

        self.metadataBox = QGroupBox(_('Metadata'))
        self.ignoreMdatatimeMtpDng = QCheckBox(_('Ignore DNG date/time metadata on MTP devices'))
        tip = _("Ignore date/time metadata in DNG files located on MTP devices, and use the "
                "file's modification time instead.\n\nUseful for devices like some phones and "
                "tablets that create incorrect DNG metadata.")
        self.ignoreMdatatimeMtpDng.setToolTip(tip)

        self.setMetdataValues()
        self.ignoreMdatatimeMtpDng.stateChanged.connect(self.ignoreMdatatimeMtpDngChanged)

        metadataLayout = QVBoxLayout()
        metadataLayout.addWidget(self.ignoreMdatatimeMtpDng)
        self.metadataBox.setLayout(metadataLayout)

        self.miscWidget = QWidget()
        miscLayout = QVBoxLayout()
        miscLayout.addWidget(self.newVersionBox)
        miscLayout.addWidget(self.metadataBox)
        miscLayout.addStretch()
        miscLayout.setContentsMargins(0, 0, 0, 0)
        miscLayout.setSpacing(18)
        self.miscWidget.setLayout(miscLayout)

        self.panels.addWidget(self.devices)
        self.panels.addWidget(self.automation)
        self.panels.addWidget(self.performance)
        self.panels.addWidget(self.errorWidget)
        self.panels.addWidget(self.warnings)
        self.panels.addWidget(self.miscWidget)

        layout = QVBoxLayout()
        self.setLayout(layout)
        layout.setSpacing(layout.contentsMargins().left() * 2)
        layout.setContentsMargins(18, 18, 18, 18)

        buttons = QDialogButtonBox(
            QDialogButtonBox.RestoreDefaults | QDialogButtonBox.Close | QDialogButtonBox.Help
        )
        self.restoreButton = buttons.button(QDialogButtonBox.RestoreDefaults)  # type: QPushButton
        self.restoreButton.clicked.connect(self.restoreDefaultsClicked)
        self.helpButton = buttons.button(QDialogButtonBox.Help)  # type: QPushButton
        self.helpButton.clicked.connect(self.helpButtonClicked)
        self.helpButton.setToolTip(_('Get help online...'))
        self.closeButton = buttons.button(QDialogButtonBox.Close)   # type: QPushButton
        self.closeButton.clicked.connect(self.close)

        controlsLayout = QHBoxLayout()
        controlsLayout.addWidget(self.chooser)
        controlsLayout.addWidget(self.panels)

        controlsLayout.setStretch(0, 0)
        controlsLayout.setStretch(1, 1)
        controlsLayout.setSpacing(layout.contentsMargins().left())

        layout.addLayout(controlsLayout)
        layout.addWidget(buttons)

        self.device_right_side_buttons = (self.removeDevice, self.removeAllDevice, self.addPath,
                                          self.removePath, self.removeAllPath)

        self.device_list_widgets = (self.knownDevices, self.ignoredPaths)
        self.chooser.setCurrentRow(0)

    def _addItems(self, pref_list: str, pref_type: int) -> None:
        if self.prefs.list_not_empty(key=pref_list):
            for value in self.prefs[pref_list]:
                QListWidgetItem(value, self.knownDevices, pref_type)

    def setDeviceWidgetValues(self) -> None:
        self.onlyExternal.setChecked(self.prefs.only_external_mounts)
        self.noDcim.setChecked(self.prefs.device_without_dcim_autodetection)
        self.knownDevices.clear()
        self._addItems('volume_whitelist', KnownDeviceType.volume_whitelist)
        self._addItems('volume_blacklist', KnownDeviceType.volume_blacklist)
        self._addItems('camera_blacklist', KnownDeviceType.camera_blacklist)
        if self.knownDevices.count():
            self.knownDevices.setCurrentRow(0)
        self.removeDevice.setEnabled(self.knownDevices.count())
        self.removeAllDevice.setEnabled(self.knownDevices.count())
        self.setIgnorePathWidgetValues()

    def setIgnorePathWidgetValues(self) -> None:
        self.ignoredPaths.clear()
        if self.prefs.list_not_empty('ignored_paths'):
            self.ignoredPaths.addItems(self.prefs.ignored_paths)
            self.ignoredPaths.setCurrentRow(0)
        self.removePath.setEnabled(self.ignoredPaths.count())
        self.removeAllPath.setEnabled(self.ignoredPaths.count())
        self.ignoredPathsRe.setChecked(self.prefs.use_re_ignored_paths)

    def setAutomationWidgetValues(self) -> None:
        self.autoDownloadStartup.setChecked(self.prefs.auto_download_at_startup)
        self.autoDownloadInsertion.setChecked(self.prefs.auto_download_upon_device_insertion)
        self.autoEject.setChecked(self.prefs.auto_unmount)
        self.autoExit.setChecked(self.prefs.auto_exit)
        self.setAutoExitErrorState()

    def setAutoExitErrorState(self) -> None:
        if self.prefs.auto_exit:
            self.autoExitError.setChecked(self.prefs.auto_exit_force)
            self.autoExitError.setEnabled(True)
        else:
            self.autoExitError.setChecked(False)
            self.autoExitError.setEnabled(False)

    def setPerformanceValues(self, check_boxes_only: bool=False) -> None:
        self.generateThumbnails.setChecked(self.prefs.generate_thumbnails)
        self.useThumbnailCache.setChecked(self.prefs.use_thumbnail_cache and
                                          self.prefs.generate_thumbnails)
        self.fdoThumbnails.setChecked(self.prefs.save_fdo_thumbnails and
                                      self.prefs.generate_thumbnails)

        if not check_boxes_only:
            available = available_cpu_count(physical_only=True)
            self.maxCores.addItems(str(i + 1) for i in range(0, available))
            self.maxCores.setCurrentText(str(self.prefs.max_cpu_cores))

    def setPerfomanceEnabled(self) -> None:
        enable = self.prefs.generate_thumbnails
        self.useThumbnailCache.setEnabled(enable)
        self.fdoThumbnails.setEnabled(enable)
        self.maxCores.setEnabled(enable)
        self.coresLabel.setEnabled(enable)

    def setCacheValues(self) -> None:
        self.thumbnailNumber.setText(thousands(self.thumbnail_cache.no_thumbnails()))
        self.thumbnailSqlSize.setText(format_size_for_user(self.thumbnail_cache.db_size()))
        self.thumbnailCacheDaysKeep.setValue(self.prefs.keep_thumbnails_days)

    @pyqtSlot('PyQt_PyObject')
    def setCacheSize(self, size: int) -> None:
        self.thumbnailCacheSize.setText(format_size_for_user(size))

    def setErrorHandingValues(self) -> None:
        if self.prefs.conflict_resolution == int(ConflictResolution.skip):
            self.skipDownload.setChecked(True)
        else:
            self.addIdentifier.setChecked(True)
        if self.prefs.backup_duplicate_overwrite:
            self.overwriteBackup.setChecked(True)
        else:
            self.skipBackup.setChecked(True)

    def setWarningValues(self) -> None:
        self.warnDownloadingAll.setChecked(self.prefs.warn_downloading_all)
        if self.prefs.backup_files:
            self.warnBackupProblem.setChecked(self.prefs.warn_backup_problem)
        else:
            self.warnBackupProblem.setChecked(False)
        self.warnMissingLibraries.setChecked(self.prefs.warn_broken_or_missing_libraries)
        self.warnMetadata.setChecked(self.prefs.warn_fs_metadata_error)
        self.warnUnhandledFiles.setChecked(self.prefs.warn_unhandled_files)
        self.setAddExceptFilesValues()

        self.setBackupWarningEnabled()
        self.setUnhandledWarningEnabled()

    def setAddExceptFilesValues(self) -> None:
        self.exceptTheseFiles.clear()
        if self.prefs.list_not_empty('ignore_unhandled_file_exts'):
            self.exceptTheseFiles.addItems(self.prefs.ignore_unhandled_file_exts)
            self.exceptTheseFiles.setCurrentRow(0)

    def setBackupWarningEnabled(self) -> None:
        self.warnBackupProblem.setEnabled(self.prefs.backup_files)

    def setUnhandledWarningEnabled(self) -> None:
        enabled = self.prefs.warn_unhandled_files
        for widget in (self.exceptTheseFilesLabel, self.exceptTheseFiles, self.addExceptFiles):
            widget.setEnabled(enabled)
        count = bool(self.exceptTheseFiles.count())
        for widget in (self.removeExceptFiles, self.removeAllExceptFiles):
            widget.setEnabled(enabled and count)

    def setVersionCheckValues(self) -> None:
        self.checkNewVersion.setChecked(self.prefs.check_for_new_versions)
        self.includeDevRelease.setChecked(self.prefs.include_development_release or
                                          self.is_prerelease)
        self.setVersionCheckEnabled()

    def setVersionCheckEnabled(self) -> None:
        self.includeDevRelease.setEnabled(not(self.is_prerelease or
                                              not self.prefs.check_for_new_versions))

    def setMetdataValues(self) -> None:
        self.ignoreMdatatimeMtpDng.setChecked(self.prefs.ignore_mdatatime_for_mtp_dng)

    @pyqtSlot(int)
    def onlyExternalChanged(self, state: int) -> None:
        self.prefs.only_external_mounts = state == Qt.Checked
        if self.rapidApp is not None:
            self.rapidApp.search_for_devices_again = True

    @pyqtSlot(int)
    def noDcimChanged(self, state: int) -> None:
        self.prefs.device_without_dcim_autodetection = state == Qt.Checked
        if self.rapidApp is not None:
            self.rapidApp.scan_non_cameras_again = True

    @pyqtSlot(int)
    def ignoredPathsReChanged(self, state: int) -> None:
        self.prefs.use_re_ignored_paths = state == Qt.Checked
        if self.rapidApp is not None:
            self.rapidApp.scan_all_again = True

    def _equalizeWidgetWidth(self, widget_list) -> None:
        max_width = max(widget.width() for widget in widget_list)
        for widget in widget_list:
            widget.setFixedWidth(max_width)

    def showEvent(self, e: QShowEvent):
        self.chooser.minimum_width = self.restoreButton.width()
        self._equalizeWidgetWidth(self.device_right_side_buttons)
        self._equalizeWidgetWidth(self.device_list_widgets)
        super().showEvent(e)

    @pyqtSlot(int)
    def rowChanged(self, row: int) -> None:
        self.panels.setCurrentIndex(row)
        # Translators: substituted value is a description for the set of preferences
        # shown in the preference dialog window, e.g. Devices, Automation, etc.
        # This string is shown in a tooltip for the "Restore Defaults" button
        self.restoreButton.setToolTip(_('Restores default %s preference values') %
                                      self.chooser_items[row])

    @pyqtSlot()
    def removeDeviceClicked(self) -> None:
        row = self.knownDevices.currentRow()
        item = self.knownDevices.takeItem(row)  # type: QListWidgetItem
        known_device_type = item.type()
        if known_device_type == KnownDeviceType.volume_whitelist:
            self.prefs.del_list_value('volume_whitelist', item.text())
        elif known_device_type == KnownDeviceType.volume_blacklist:
            self.prefs.del_list_value('volume_blacklist', item.text())
        else:
            assert known_device_type == KnownDeviceType.camera_blacklist
            self.prefs.del_list_value('camera_blacklist', item.text())

        self.removeDevice.setEnabled(self.knownDevices.count())
        self.removeAllDevice.setEnabled(self.knownDevices.count())

        if self.rapidApp is not None:
            self.rapidApp.search_for_devices_again = True

    @pyqtSlot()
    def removeAllDeviceClicked(self) -> None:
        self.knownDevices.clear()
        self.prefs.volume_whitelist = ['']
        self.prefs.volume_blacklist = ['']
        self.prefs.camera_blacklist = ['']
        self.removeDevice.setEnabled(False)
        self.removeAllDevice.setEnabled(False)

        if self.rapidApp is not None:
            self.rapidApp.search_for_devices_again = True

    @pyqtSlot()
    def removePathClicked(self) -> None:
        row = self.ignoredPaths.currentRow()
        if row >= 0:
            item = self.ignoredPaths.takeItem(row)
            self.prefs.del_list_value('ignored_paths', item.text())
            self.removePath.setEnabled(self.ignoredPaths.count())
            self.removeAllPath.setEnabled(self.ignoredPaths.count())

            if self.rapidApp is not None:
                self.rapidApp.scan_all_again = True


    @pyqtSlot()
    def removeAllPathClicked(self) -> None:
        self.ignoredPaths.clear()
        self.prefs.ignored_paths = ['']
        self.removePath.setEnabled(False)
        self.removeAllPath.setEnabled(False)

        if self.rapidApp is not None:
            self.rapidApp.scan_all_again = True

    @pyqtSlot()
    def addPathClicked(self) -> None:
        dlg = IgnorePathDialog(prefs=self.prefs, parent=self)
        if dlg.exec():
            self.setIgnorePathWidgetValues()

            if self.rapidApp is not None:
                self.rapidApp.scan_all_again = True

    @pyqtSlot()
    def ignorePathsReLabelClicked(self) -> None:
        self.ignoredPathsRe.click()


    @pyqtSlot(int)
    def autoDownloadStartupChanged(self, state: int) -> None:
        self.prefs.auto_download_at_startup = state == Qt.Checked

    @pyqtSlot(int)
    def autoDownloadInsertionChanged(self, state: int) -> None:
        self.prefs.auto_download_upon_device_insertion = state == Qt.Checked

    @pyqtSlot(int)
    def autoEjectChanged(self, state: int) -> None:
        self.prefs.auto_unmount = state == Qt.Checked

    @pyqtSlot(int)
    def autoExitChanged(self, state: int) -> None:
        auto_exit = state == Qt.Checked
        self.prefs.auto_exit = auto_exit
        self.setAutoExitErrorState()
        if not auto_exit:
            self.prefs.auto_exit_force = False

    @pyqtSlot(int)
    def autoExitErrorChanged(self, state: int) -> None:
        self.prefs.auto_exit_force = state == Qt.Checked

    @pyqtSlot(int)
    def generateThumbnailsChanged(self, state: int) -> None:
        self.prefs.generate_thumbnails = state == Qt.Checked
        self.setPerformanceValues(check_boxes_only=True)
        self.setPerfomanceEnabled()

    @pyqtSlot(int)
    def useThumbnailCacheChanged(self, state: int) -> None:
        if self.prefs.generate_thumbnails:
            self.prefs.use_thumbnail_cache = state == Qt.Checked

    @pyqtSlot(int)
    def fdoThumbnailsChanged(self, state: int) -> None:
        if self.prefs.generate_thumbnails:
            self.prefs.save_fdo_thumbnails = state == Qt.Checked

    @pyqtSlot(int)
    def thumbnailCacheDaysKeepChanged(self, value: int) -> None:
        self.prefs.keep_thumbnails_days = value

    @pyqtSlot(int)
    def maxCoresChanged(self, index: int) -> None:
        if index >= 0:
            self.prefs.max_cpu_cores = int(self.maxCores.currentText())

    @pyqtSlot()
    def purgeCacheClicked(self) -> None:
        message = _('Do you want to purge the thumbnail cache? The cache will be purged when the '
                    'program is next started.')
        msgBox = QMessageBox(parent=self)
        msgBox.setWindowTitle(_('Purge Thumbnail Cache'))
        msgBox.setText(message)
        msgBox.setIcon(QMessageBox.Question)
        msgBox.setStandardButtons(QMessageBox.Yes|QMessageBox.No)
        if msgBox.exec_() == QMessageBox.Yes:
            self.prefs.purge_thumbnails = True
            self.prefs.optimize_thumbnail_db = False
        else:
            self.prefs.purge_thumbnails = False

    @pyqtSlot()
    def optimizeCacheClicked(self) -> None:
        message = _('Do you want to optimize the thumbnail cache? The cache will be optimized when '
                    'the program is next started.')
        msgBox = QMessageBox(parent=self)
        msgBox.setWindowTitle(_('Optimize Thumbnail Cache'))
        msgBox.setText(message)
        msgBox.setIcon(QMessageBox.Question)
        msgBox.setStandardButtons(QMessageBox.Yes|QMessageBox.No)
        if msgBox.exec_() == QMessageBox.Yes:
            self.prefs.purge_thumbnails = False
            self.prefs.optimize_thumbnail_db = True
        else:
            self.prefs.optimize_thumbnail_db = False

    @pyqtSlot(QAbstractButton)
    def downloadErrorGroupClicked(self, button: QRadioButton) -> None:
        if self.downloadErrorGroup.checkedButton() == self.skipDownload:
            self.prefs.conflict_resolution = int(ConflictResolution.skip)
        else:
            self.prefs.conflict_resolution = int(ConflictResolution.add_identifier)

    @pyqtSlot(QAbstractButton)
    def backupErrorGroupClicked(self, button: QRadioButton) -> None:
        self.prefs.backup_duplicate_overwrite = self.backupErrorGroup.checkedButton() == \
                                                self.overwriteBackup

    @pyqtSlot(int)
    def warnDownloadingAllChanged(self, state: int) -> None:
        self.prefs.warn_downloading_all = state == Qt.Checked

    @pyqtSlot(int)
    def warnBackupProblemChanged(self, state: int) -> None:
        self.prefs.warn_backup_problem = state == Qt.Checked

    @pyqtSlot(int)
    def warnMissingLibrariesChanged(self, state: int) -> None:
        self.prefs.warn_broken_or_missing_libraries = state == Qt.Checked

    @pyqtSlot(int)
    def warnMetadataChanged(self, state: int) -> None:
        self.prefs.warn_fs_metadata_error = state == Qt.Checked

    @pyqtSlot(int)
    def warnUnhandledFilesChanged(self, state: int) -> None:
        self.prefs.warn_unhandled_files = state == Qt.Checked
        self.setUnhandledWarningEnabled()

    @pyqtSlot()
    def addExceptFilesClicked(self) -> None:
        dlg = ExceptFileExtDialog(prefs=self.prefs, parent=self)
        if dlg.exec():
            self.setAddExceptFilesValues()

    @pyqtSlot()
    def removeExceptFilesClicked(self) -> None:
        row = self.exceptTheseFiles.currentRow()
        if row >= 0:
            item = self.exceptTheseFiles.takeItem(row)
            self.prefs.del_list_value('ignore_unhandled_file_exts', item.text())
            self.removeExceptFiles.setEnabled(self.exceptTheseFiles.count())
            self.removeAllExceptFiles.setEnabled(self.exceptTheseFiles.count())

    @pyqtSlot()
    def removeAllExceptFilesClicked(self) -> None:
        self.exceptTheseFiles.clear()
        self.prefs.ignore_unhandled_file_exts = ['']
        self.removeExceptFiles.setEnabled(False)
        self.removeAllExceptFiles.setEnabled(False)

    @pyqtSlot(int)
    def checkNewVersionChanged(self, state: int) -> None:
        do_check = state == Qt.Checked
        self.prefs.check_for_new_versions = do_check
        self.setVersionCheckEnabled()

    @pyqtSlot(int)
    def includeDevReleaseChanged(self, state: int) -> None:
        self.prefs.include_development_release = state == Qt.Checked

    @pyqtSlot(int)
    def ignoreMdatatimeMtpDngChanged(self, state: int) -> None:
        self.prefs.ignore_mdatatime_for_mtp_dng = state == Qt.Checked

    @pyqtSlot()
    def restoreDefaultsClicked(self) -> None:
        row = self.chooser.currentRow()
        if row == 0:
            for value in ('only_external_mounts', 'device_without_dcim_autodetection',
                           'ignored_paths', 'use_re_ignored_paths'):
                self.prefs.restore(value)
            self.removeAllDeviceClicked()
            self.setDeviceWidgetValues()
        elif row == 1:
            for value in ('auto_download_at_startup', 'auto_download_upon_device_insertion',
                          'auto_unmount', 'auto_exit', 'auto_exit_force'):
                self.prefs.restore(value)
            self.setAutomationWidgetValues()
        elif row == 2:
            for value in ('generate_thumbnails', 'use_thumbnail_cache', 'save_fdo_thumbnails',
                          'max_cpu_cores', 'keep_thumbnails_days'):
                self.prefs.restore(value)
            self.setPerformanceValues(check_boxes_only=True)
            self.maxCores.setCurrentText(str(self.prefs.max_cpu_cores))
            self.setPerfomanceEnabled()
            self.thumbnailCacheDaysKeep.setValue(self.prefs.keep_thumbnails_days)
        elif row == 3:
            for value in ('conflict_resolution', 'backup_duplicate_overwrite'):
                self.prefs.restore(value)
            self.setErrorHandingValues()
        elif row == 4:
            for value in (
                    'warn_downloading_all', 'warn_backup_problem',
                    'warn_broken_or_missing_libraries', 'warn_fs_metadata_error',
                    'warn_unhandled_files', 'ignore_unhandled_file_exts'):
                self.prefs.restore(value)
            self.setWarningValues()
            self.setVersionCheckValues()
        elif row == 5:
            for value in ('check_for_new_versions', 'include_development_release',
                          'ignore_mdatatime_for_mtp_dng'):
                self.prefs.restore(value)
            self.setVersionCheckValues()
            self.setMetdataValues()

    @pyqtSlot()
    def helpButtonClicked(self) -> None:
        row = self.chooser.currentRow()
        if row == 0:
            location = '#devicepreferences'
        elif row == 1:
            location = '#automationpreferences'
        elif row == 2:
            location = '#thumbnailpreferences'
        elif row == 3:
            location = '#errorhandlingpreferences'
        elif row == 4:
            location = '#warningpreferences'
        elif row == 5:
            location = '#miscellaneousnpreferences'
        else:
            location = ''

        webbrowser.open_new_tab("http://www.damonlynch.net/rapid/documentation/{}".format(location))

    def closeEvent(self, event: QCloseEvent) -> None:
        self.cacheSizeThread.quit()
        self.cacheSizeThread.wait(1000)
        event.accept()


class PreferenceAddDialog(QDialog):
    """
    Base class for adding value to pref list
    """
    def __init__(self, prefs: Preferences,
                 title: str,
                 instruction: str,
                 label: str,
                 pref_value: str,
                 parent=None) -> None:
        super().__init__(parent=parent)

        self.prefs = prefs
        self.pref_value = pref_value

        self.setWindowTitle(title)

        self.instructionLabel = QLabel(instruction)
        self.instructionLabel.setWordWrap(False)
        layout = QVBoxLayout()
        self.setLayout(layout)

        self.valueEdit = QLineEdit()
        formLayout = QFormLayout()
        formLayout.addRow(label, self.valueEdit)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout.addWidget(self.instructionLabel)
        layout.addLayout(formLayout)
        layout.addWidget(buttons)

    def accept(self):
        value = self.valueEdit.text()
        if value:
            self.prefs.add_list_value(self.pref_value, value)
        super().accept()


class IgnorePathDialog(PreferenceAddDialog):
    """
    Dialog prompting for a path to ignore when scanning devices
    """

    def __init__(self, prefs: Preferences, parent=None) -> None:
        super().__init__(
            prefs=prefs,
            title=_('Enter a Path to Ignore'),
            instruction=_('Specify a path that will never be scanned for photos or videos'),
            label=_('Path:'),
            pref_value='ignored_paths',
            parent=parent
        )


class ExceptFileExtDialog(PreferenceAddDialog):
    """
    Dialog prompting for file extensions never to warn about
    """

    def __init__(self, prefs: Preferences, parent=None) -> None:
        super().__init__(
            prefs=prefs,
            title=_('Enter a File Extension'),
            instruction=_('Specify a file extension (without the leading dot)'),
            label=_('Extension:'),
            pref_value='ignore_unhandled_file_exts',
            parent=parent
        )

    def exts(self, exts: List[str]) -> str:
        return make_internationalized_list([ext.upper() for ext in exts])

    def accept(self):
        value = self.valueEdit.text()
        if value:
            while value.startswith('.'):
                value = value[1:]
            value = value.upper()
            if value.lower() in ALL_KNOWN_EXTENSIONS:
                title = _('Invalid File Extension')
                message = _("The file extension <b>%s</b> is recognized by Rapid Photo Downloader, "
                            "so it makes no sense to warn about its presence.") % value
                details = _('Recognized file types:\n\n'
                            'Photos:\n%(photos)s\n\nVideos:\n%(videos)s\n\n'
                            'Audio:\n%(audio)s\n\nOther:\n%(other)s') % dict(
                    photos=self.exts(PHOTO_EXTENSIONS),
                    videos=self.exts(VIDEO_EXTENSIONS + VIDEO_THUMBNAIL_EXTENSIONS),
                    audio=self.exts(AUDIO_EXTENSIONS),
                    other=self.exts(['xmp'])
                )
                msgbox = QMessageBox(parent=self)
                msgbox.setWindowTitle(title)
                msgbox.setText(message)
                msgbox.setDetailedText(details)
                msgbox.setIcon(QMessageBox.Information)
                msgbox.exec()
                self.valueEdit.setText(value)
                self.valueEdit.selectAll()
                return
            else:
                self.prefs.add_list_value(self.pref_value, value)
        QDialog.accept(self)

class CacheSize(QObject):
    size = pyqtSignal('PyQt_PyObject')  # don't convert python int to C++ int

    @pyqtSlot()
    def start(self) -> None:
        self.thumbnail_cache = ThumbnailCacheSql()

    @pyqtSlot()
    def getCacheSize(self) -> None:
        self.size.emit(self.thumbnail_cache.cache_size())


if __name__ == '__main__':

    # Application development test code:

    app = QApplication([])

    app.setOrganizationName("Rapid Photo Downloader")
    app.setOrganizationDomain("damonlynch.net")
    app.setApplicationName("Rapid Photo Downloader")

    prefs = Preferences()

    prefDialog = PreferencesDialog(prefs)
    prefDialog.show()
    app.exec_()
