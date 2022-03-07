# Copyright (C) 2017-2022 Damon Lynch <damonlynch@gmail.com>

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

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2017-2022, Damon Lynch"

import webbrowser
from typing import List
import logging


from PyQt5.QtCore import Qt, pyqtSlot, pyqtSignal, QObject, QThread, QTimer, QSize
from PyQt5.QtWidgets import (
    QWidget,
    QSizePolicy,
    QComboBox,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QGridLayout,
    QAbstractItemView,
    QListWidgetItem,
    QHBoxLayout,
    QDialog,
    QDialogButtonBox,
    QCheckBox,
    QStyle,
    QStackedWidget,
    QApplication,
    QPushButton,
    QGroupBox,
    QFormLayout,
    QMessageBox,
    QButtonGroup,
    QRadioButton,
    QAbstractButton,
)
from PyQt5.QtGui import (
    QShowEvent,
    QCloseEvent,
    QMouseEvent,
    QIcon,
    QFont,
    QFontMetrics,
    QPixmap,
    QPalette,
)

from raphodo.prefs.preferences import Preferences
from raphodo.constants import (
    KnownDeviceType,
    CompletedDownloads,
    TreatRawJpeg,
    MarkRawJpeg,
)
from raphodo.ui.viewutils import (
    QNarrowListWidget,
    translateDialogBoxButtons,
    standardMessageBox,
    StyledLinkLabel,
)
from raphodo.cache import ThumbnailCacheSql
from raphodo.constants import ConflictResolution
from raphodo.utilities import (
    current_version_is_dev_version,
    make_internationalized_list,
    version_check_disabled,
    available_languages,
    available_cpu_count,
    format_size_for_user,
    thousands,
)
from raphodo.ui.viewutils import darkModePixmap
from raphodo.metadata.fileformats import (
    PHOTO_EXTENSIONS,
    AUDIO_EXTENSIONS,
    VIDEO_EXTENSIONS,
    VIDEO_THUMBNAIL_EXTENSIONS,
    ALL_KNOWN_EXTENSIONS,
)


class ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.clicked.emit()


consolidation_implemented = False
# consolidation_implemented = True

system_language = "SYSTEM"


class PreferencesDialog(QDialog):
    """
    Preferences dialog for those preferences that are not adjusted via the main window

    Note:

    When pref value generate_thumbnails is made False, pref values use_thumbnail_cache
    and generate_thumbnails are not changed, even though the preference value shown to
    the user shows False (to indicate that the activity will not occur).
    """

    getCacheSize = pyqtSignal()

    def __init__(self, prefs: Preferences, parent=None) -> None:
        super().__init__(parent=parent)

        self.rapidApp = parent

        self.setWindowTitle(_("Preferences"))

        self.prefs = prefs

        self.is_prerelease = current_version_is_dev_version()

        self.panels = QStackedWidget()

        self.chooser = QNarrowListWidget(no_focus_recentangle=True)

        font = QFont()
        fontMetrics = QFontMetrics(font)
        icon_padding = 6
        icon_height = max(fontMetrics.height(), 16)
        icon_width = icon_height + icon_padding
        self.chooser.setIconSize(QSize(icon_width, icon_height))

        palette = QPalette()
        selectedColour = palette.color(palette.HighlightedText)

        if consolidation_implemented:
            self.chooser_items = (
                _("Devices"),
                _("Language"),
                _("Automation"),
                _("Thumbnails"),
                _("Time Zones"),
                _("Error Handling"),
                _("Warnings"),
                _("Consolidation"),
                _("Miscellaneous"),
            )
            icons = (
                ":/prefs/devices.svg",
                ":/prefs/language.svg",
                ":/prefs/automation.svg",
                ":/prefs/thumbnails.svg",
                ":/prefs/timezone.svg",
                ":/prefs/error-handling.svg",
                ":/prefs/warnings.svg",
                ":/prefs/consolidation.svg",
                ":/prefs/miscellaneous.svg",
            )
        else:
            self.chooser_items = (
                _("Devices"),
                _("Language"),
                _("Automation"),
                _("Thumbnails"),
                _("Time Zones"),
                _("Error Handling"),
                _("Warnings"),
                _("Miscellaneous"),
            )
            icons = (
                ":/prefs/devices.svg",
                ":/prefs/language.svg",
                ":/prefs/automation.svg",
                ":/prefs/thumbnails.svg",
                ":/prefs/timezone.svg",
                ":/prefs/error-handling.svg",
                ":/prefs/warnings.svg",
                ":/prefs/miscellaneous.svg",
            )

        for prefIcon, label in zip(icons, self.chooser_items):
            # make the selected icons be the same colour as the selected text
            icon = QIcon()
            pixmap = QPixmap(prefIcon)
            selected = QPixmap(pixmap.size())
            selected.fill(selectedColour)
            selected.setMask(pixmap.createMaskFromColor(Qt.transparent))
            pixmap = darkModePixmap(pixmap=pixmap)
            icon.addPixmap(pixmap, QIcon.Normal)
            icon.addPixmap(selected, QIcon.Selected)

            item = QListWidgetItem(icon, label, self.chooser)
            item.setFont(QFont())
            width = fontMetrics.width(label) + icon_width + icon_padding * 2
            item.setSizeHint(QSize(width, icon_height * 2))

        self.chooser.currentRowChanged.connect(self.rowChanged)
        self.chooser.setSelectionMode(QAbstractItemView.SingleSelection)
        self.chooser.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.MinimumExpanding)

        self.devices = QWidget()

        self.scanBox = QGroupBox(_("Device Scanning"))
        self.onlyExternal = QCheckBox(_("Scan only external devices"))
        self.onlyExternal.setToolTip(
            _(
                "Scan for photos and videos only on devices that are external to the "
                "computer,\n"
                "including cameras, memory cards, external hard drives, and USB flash "
                "drives."
            )
        )
        self.scanSpecificFolders = QCheckBox(_("Scan only specific folders on devices"))
        tip = _(
            "Scan for photos and videos only in the folders specified below "
            "(except paths\n"
            "specified in Ignored Paths).\n\n"
            "Changing this setting causes all devices to be scanned again."
        )
        self.scanSpecificFolders.setToolTip(tip)

        self.foldersToScanLabel = QLabel(_("Folders to scan:"))
        self.foldersToScan = QNarrowListWidget(minimum_rows=5)
        self.foldersToScan.setToolTip(
            _(
                "Folders at the base level of device file systems that will be "
                "scanned\n"
                "for photos and videos."
            )
        )
        self.addFolderToScan = QPushButton(_("Add..."))
        self.addFolderToScan.setToolTip(
            _(
                "Add a folder to the list of folders to scan for photos and videos.\n\n"
                "Changing this setting causes all devices to be scanned again."
            )
        )
        self.removeFolderToScan = QPushButton(_("Remove"))
        self.removeFolderToScan.setToolTip(
            _(
                "Remove a folder from the list of folders to scan for photos and "
                "videos.\n\n"
                "Changing this setting causes all devices to be scanned again."
            )
        )

        self.addFolderToScan.clicked.connect(self.addFolderToScanClicked)
        self.removeFolderToScan.clicked.connect(self.removeFolderToScanClicked)

        scanLayout = QGridLayout()
        scanLayout.setHorizontalSpacing(18)
        scanLayout.addWidget(self.onlyExternal, 0, 0, 1, 3)
        scanLayout.addWidget(self.scanSpecificFolders, 1, 0, 1, 3)
        scanLayout.addWidget(self.foldersToScanLabel, 2, 1, 1, 2)
        scanLayout.addWidget(self.foldersToScan, 3, 1, 3, 1)
        scanLayout.addWidget(self.addFolderToScan, 3, 2, 1, 1)
        scanLayout.addWidget(self.removeFolderToScan, 4, 2, 1, 1)
        self.scanBox.setLayout(scanLayout)

        tip = _("Devices that have been set to automatically ignore or download from.")
        self.knownDevicesBox = QGroupBox(_("Remembered Devices"))
        self.knownDevices = QNarrowListWidget(minimum_rows=5)
        self.knownDevices.setToolTip(tip)
        tip = _(
            "Remove a device from the list of devices to automatically ignore or "
            "download from."
        )
        self.removeDevice = QPushButton(_("Remove"))
        self.removeDevice.setToolTip(tip)
        self.removeAllDevice = QPushButton(_("Remove All"))
        tip = _(
            "Clear the list of devices from which to automatically ignore or download "
            "from.\n\n"
            "Note: Changes take effect when the computer is next scanned for devices."
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

        self.ignoredPathsBox = QGroupBox(_("Ignored Paths"))
        tip = _(
            "The end part of a path that should never be scanned for photos or videos."
        )
        self.ignoredPaths = QNarrowListWidget(minimum_rows=4)
        self.ignoredPaths.setToolTip(tip)
        self.addPath = QPushButton(_("Add..."))
        self.addPath.setToolTip(
            _(
                "Add a path to the list of paths to ignore.\n\n"
                "Changing this setting causes all devices to be scanned again."
            )
        )
        self.removePath = QPushButton(_("Remove"))
        self.removePath.setToolTip(
            _(
                "Remove a path from the list of paths to ignore.\n\n"
                "Changing this setting causes all devices to be scanned again."
            )
        )
        self.removeAllPath = QPushButton(_("Remove All"))
        self.removeAllPath.setToolTip(
            _(
                "Clear the list of paths to ignore.\n\n"
                "Changing this setting causes all devices to be scanned again."
            )
        )
        self.addPath.clicked.connect(self.addPathClicked)
        self.removePath.clicked.connect(self.removePathClicked)
        self.removeAllPath.clicked.connect(self.removeAllPathClicked)
        self.ignoredPathsRe = QCheckBox()
        self.ignorePathsReLabel = ClickableLabel(
            # Translators: you must include {link} exactly as it is below.
            # Do not translate the term link. Be sure to include the <a> and </a> as well.
            _("Use python-style <a {link}>regular expressions</a>").format(
                link='style="text-decoration:none; color: palette(highlight);"'
                'href="http://damonlynch.net/rapid/documentation/#regularexpressions"'
            )
        )
        self.ignorePathsReLabel.setToolTip(
            _(
                "Use regular expressions in the list of ignored paths.\n\n"
                "Changing this setting causes all devices to be scanned again."
            )
        )
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

        # connect these next 3 only after having set their values, so rescan / search
        # again in rapidApp is not triggered
        self.onlyExternal.stateChanged.connect(self.onlyExternalChanged)
        self.scanSpecificFolders.stateChanged.connect(self.noDcimChanged)
        self.ignoredPathsRe.stateChanged.connect(self.ignoredPathsReChanged)

        devicesLayout = QVBoxLayout()
        devicesLayout.addWidget(self.scanBox)
        devicesLayout.addWidget(self.ignoredPathsBox)
        devicesLayout.addWidget(self.knownDevicesBox)
        devicesLayout.addStretch()
        devicesLayout.setSpacing(18)

        self.devices.setLayout(devicesLayout)
        devicesLayout.setContentsMargins(0, 0, 0, 0)

        self.language = QWidget()
        self.languages = QComboBox()
        self.languages.setEditable(False)
        self.languagesLabel = QLabel(_("Language: "))
        self.languages.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        # self.languages.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)

        self.setLanguageWidgetValues()

        self.languages.currentIndexChanged.connect(self.languagesChanged)

        languageWidgetsLayout = QHBoxLayout()
        languageWidgetsLayout.addWidget(self.languagesLabel)
        languageWidgetsLayout.addWidget(self.languages)
        # Translators: the * acts as an asterisk to denote a reference to an annotation
        # such as '* Takes effect upon program restart'
        languageWidgetsLayout.addWidget(QLabel(_("*")))
        languageWidgetsLayout.addStretch()
        languageWidgetsLayout.setSpacing(5)

        languageLayout = QVBoxLayout()
        languageLayout.addLayout(languageWidgetsLayout)
        # Translators: the * acts as an asterisk to denote a reference to this
        # annotation
        languageLayout.addWidget(QLabel(_("* Takes effect upon program restart")))
        languageLayout.addStretch()
        languageLayout.setContentsMargins(0, 0, 0, 0)
        languageLayout.setSpacing(18)
        self.language.setLayout(languageLayout)

        self.automation = QWidget()

        self.automationBox = QGroupBox(_("Program Automation"))
        self.autoMount = QCheckBox(_("Mount devices not already automatically mounted"))
        tooltip = _(
            # Translators: This next sentence is used in a tool tip. Feel free to place the
            # carriage return where you think it makes sense so that the tool tip does not
            # stretch too far horizontally across the screen.
            "Mount devices like memory cards or external drives when\n"
            "the operating system does not automatically mount them"
        )
        self.autoMount.setToolTip(tooltip)
        self.autoDownloadStartup = QCheckBox(_("Start downloading at program startup"))
        self.autoDownloadInsertion = QCheckBox(
            _("Start downloading upon device insertion")
        )
        self.autoEject = QCheckBox(_("Unmount (eject) device upon download completion"))
        self.autoExit = QCheckBox(_("Exit program when download completes"))
        self.autoExitError = QCheckBox(
            _("Exit program even if download had warnings or errors")
        )
        self.setAutomationWidgetValues()
        self.autoMount.stateChanged.connect(self.autoMountChanged)
        self.autoDownloadStartup.stateChanged.connect(self.autoDownloadStartupChanged)
        self.autoDownloadInsertion.stateChanged.connect(
            self.autoDownloadInsertionChanged
        )
        self.autoEject.stateChanged.connect(self.autoEjectChanged)
        self.autoExit.stateChanged.connect(self.autoExitChanged)
        self.autoExitError.stateChanged.connect(self.autoExitErrorChanged)

        automationBoxLayout = QGridLayout()
        automationBoxLayout.addWidget(self.autoMount, 0, 0, 1, 2)
        automationBoxLayout.addWidget(self.autoDownloadStartup, 1, 0, 1, 2)
        automationBoxLayout.addWidget(self.autoDownloadInsertion, 2, 0, 1, 2)
        automationBoxLayout.addWidget(self.autoEject, 3, 0, 1, 2)
        automationBoxLayout.addWidget(self.autoExit, 4, 0, 1, 2)
        automationBoxLayout.addWidget(self.autoExitError, 5, 1, 1, 1)
        checkbox_width = self.autoExit.style().pixelMetric(QStyle.PM_IndicatorWidth)
        automationBoxLayout.setColumnMinimumWidth(0, checkbox_width)
        self.automationBox.setLayout(automationBoxLayout)

        automationLayout = QVBoxLayout()
        automationLayout.addWidget(self.automationBox)
        automationLayout.addStretch()
        automationLayout.setContentsMargins(0, 0, 0, 0)

        self.automation.setLayout(automationLayout)

        self.performance = QWidget()

        self.performanceBox = QGroupBox(_("Thumbnail Generation"))
        self.generateThumbnails = QCheckBox(_("Generate thumbnails"))
        self.generateThumbnails.setToolTip(
            _("Generate thumbnails to show in the main program window")
        )
        self.useThumbnailCache = QCheckBox(_("Cache thumbnails"))
        self.useThumbnailCache.setToolTip(
            _(
                "Save thumbnails shown in the main program window in a thumbnail cache "
                "unique to Rapid Photo Downloader"
            )
        )
        self.fdoThumbnails = QCheckBox(_("Generate system thumbnails"))
        self.fdoThumbnails.setToolTip(
            _(
                "While downloading, save thumbnails that can be used by desktop file "
                "managers and other programs"
            )
        )
        self.generateThumbnails.stateChanged.connect(self.generateThumbnailsChanged)
        self.useThumbnailCache.stateChanged.connect(self.useThumbnailCacheChanged)
        self.fdoThumbnails.stateChanged.connect(self.fdoThumbnailsChanged)
        self.maxCores = QComboBox()
        self.maxCores.setEditable(False)
        tip = _("Number of CPU cores used to generate thumbnails.")
        self.coresLabel = QLabel(_("CPU cores:"))
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
        coresLayout.addWidget(QLabel(_("*")))
        coresLayout.addStretch()

        performanceBoxLayout = QVBoxLayout()
        performanceBoxLayout.addWidget(self.generateThumbnails)
        performanceBoxLayout.addWidget(self.useThumbnailCache)
        performanceBoxLayout.addWidget(self.fdoThumbnails)
        performanceBoxLayout.addLayout(coresLayout)
        self.performanceBox.setLayout(performanceBoxLayout)

        self.thumbnail_cache = ThumbnailCacheSql(create_table_if_not_exists=False)

        self.cacheSize = CacheSize()
        self.cacheSizeThread = QThread()
        self.cacheSizeThread.started.connect(self.cacheSize.start)
        self.getCacheSize.connect(self.cacheSize.getCacheSize)
        self.cacheSize.size.connect(self.setCacheSize)
        self.cacheSize.moveToThread(self.cacheSizeThread)

        QTimer.singleShot(0, self.cacheSizeThread.start)

        self.getCacheSize.emit()

        self.cacheBox = QGroupBox(_("Thumbnail Cache"))
        self.thumbnailCacheSize = QLabel()
        self.thumbnailCacheSize.setText(_("Calculating..."))
        self.thumbnailNumber = QLabel()
        self.thumbnailSqlSize = QLabel()
        self.thumbnailCacheDaysKeep = QSpinBox()
        self.thumbnailCacheDaysKeep.setMinimum(0)
        self.thumbnailCacheDaysKeep.setMaximum(360 * 3)
        self.thumbnailCacheDaysKeep.setSuffix(" " + _("days"))
        self.thumbnailCacheDaysKeep.setSpecialValueText(_("forever"))
        self.thumbnailCacheDaysKeep.valueChanged.connect(
            self.thumbnailCacheDaysKeepChanged
        )

        cacheBoxLayout = QVBoxLayout()
        cacheLayout = QGridLayout()
        cacheLayout.addWidget(QLabel(_("Cache size:")), 0, 0, 1, 1)
        cacheLayout.addWidget(self.thumbnailCacheSize, 0, 1, 1, 1)
        cacheLayout.addWidget(QLabel(_("Number of thumbnails:")), 1, 0, 1, 1)
        cacheLayout.addWidget(self.thumbnailNumber, 1, 1, 1, 1)
        cacheLayout.addWidget(QLabel(_("Database size:")), 2, 0, 1, 1)
        cacheLayout.addWidget(self.thumbnailSqlSize, 2, 1, 1, 1)
        cacheLayout.addWidget(QLabel(_("Cache unaccessed thumbnails for:")), 3, 0, 1, 1)
        cacheDays = QHBoxLayout()
        cacheDays.addWidget(self.thumbnailCacheDaysKeep)
        cacheDays.addWidget(QLabel(_("*")))
        cacheLayout.addLayout(cacheDays, 3, 1, 1, 1)
        cacheBoxLayout.addLayout(cacheLayout)

        cacheButtons = QDialogButtonBox()
        self.purgeCache = cacheButtons.addButton(
            _("Purge Cache..."), QDialogButtonBox.ResetRole
        )
        self.optimizeCache = cacheButtons.addButton(
            _("Optimize Cache..."), QDialogButtonBox.ResetRole
        )
        self.purgeCache.clicked.connect(self.purgeCacheClicked)
        self.optimizeCache.clicked.connect(self.optimizeCacheClicked)

        cacheBoxLayout.addWidget(cacheButtons)

        self.cacheBox.setLayout(cacheBoxLayout)
        self.setCacheValues()

        performanceLayout = QVBoxLayout()
        performanceLayout.addWidget(self.performanceBox)
        performanceLayout.addWidget(self.cacheBox)
        performanceLayout.addWidget(QLabel(_("* Takes effect upon program restart")))
        performanceLayout.addStretch()
        performanceLayout.setContentsMargins(0, 0, 0, 0)
        performanceLayout.setSpacing(18)

        self.performance.setLayout(performanceLayout)

        self.timeZone = QWidget()

        # Translators: see explanation at https://damonlynch.net/rapid/documentation/#timezonehandling
        self.timeZoneBox = QGroupBox(_("Time Zones"))
        # Translators: see explanation at https://damonlynch.net/rapid/documentation/#timezonehandling
        self.ignoreTimeZone = QCheckBox(
            _("Ignore time zone and daylight savings changes")
        )
        self.timeZoneOffsetResolution = QComboBox()
        self.timeZoneOffsetResolution.setEditable(False)
        self.timeZoneOffsetResolution.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.timeZoneOffsetResolution.setSizePolicy(
            QSizePolicy.Minimum, QSizePolicy.Minimum
        )
        self.timeZoneOffsetResolution.addItems(("60", "30", "15"))
        # Translators: for an explanation of what an offset resolution is, see https://damonlynch.net/rapid/documentation/#timezoneoffsetresolution
        self.timeZoneOffsetLabel = QLabel(_("Offset resolution (minutes):"))
        # Translators: for an explanation of what an offset resolution is, see https://damonlynch.net/rapid/documentation/#timezoneoffsetresolution
        tooltip = _(
            "The multiple used when calculating the offset from the time the photo or "
            "video was originally taken"
        )
        self.timeZoneOffsetLabel.setToolTip(tooltip)
        self.timeZoneOffsetResolution.setToolTip(tooltip)
        self.timeZoneOffset = QWidget()
        timeZoneOffsetLayout = QHBoxLayout()
        timeZoneOffsetLayout.addWidget(self.timeZoneOffsetResolution)
        timeZoneOffsetLayout.addStretch()
        timeZoneOffsetLayout.setContentsMargins(0, 0, 0, 0)
        self.timeZoneOffset.setLayout(timeZoneOffsetLayout)

        # Translators: see explanation at https://damonlynch.net/rapid/documentation/#timezonehandling
        timeZoneExplanation = QLabel(
            _("When detecting if a file has been previously downloaded:")
        )

        timeZoneBoxLayout = QGridLayout()
        timeZoneBoxLayout.addWidget(timeZoneExplanation, 0, 0, 1, 3)
        timeZoneBoxLayout.addWidget(self.ignoreTimeZone, 1, 0, 1, 3)
        timeZoneBoxLayout.addWidget(self.timeZoneOffsetLabel, 2, 1, 1, 1)
        timeZoneBoxLayout.addWidget(self.timeZoneOffset, 2, 2, 1, 1)
        timeZoneBoxLayout.setColumnMinimumWidth(0, checkbox_width)
        self.timeZoneBox.setLayout(timeZoneBoxLayout)

        timeZoneHelpLink = StyledLinkLabel()
        timeZoneHelpLink.setLink(
            url="https://damonlynch.net/rapid/documentation#timezonehandling",
            text=_("Learn more about time zone handling"),
        )
        timeZoneHelpLink.setWordWrap(True)
        timeZoneHelpLink.setOpenExternalLinks(True)

        timeZoneLayout = QVBoxLayout()
        timeZoneLayout.addWidget(self.timeZoneBox)
        timeZoneLayout.addWidget(timeZoneHelpLink)
        timeZoneLayout.addStretch()
        timeZoneLayout.setContentsMargins(0, 0, 0, 0)
        timeZoneLayout.setSpacing(18)

        self.timeZone.setLayout(timeZoneLayout)

        self.setTimeZoneValues()
        self.ignoreTimeZone.stateChanged.connect(self.ignoreTimeZoneChanged)
        self.timeZoneOffsetResolution.currentIndexChanged.connect(
            self.timeZoneOffsetResolutionChanged
        )

        self.errorBox = QGroupBox(_("Error Handling"))

        self.downloadErrorGroup = QButtonGroup()
        self.skipDownload = QRadioButton(_("Skip download"))
        self.skipDownload.setToolTip(
            _("Don't download the file, and issue an error message")
        )
        self.addIdentifier = QRadioButton(_("Add unique identifier"))
        self.addIdentifier.setToolTip(
            _(
                "Add an identifier like _1 or _2 to the end of the filename, "
                "immediately before the file's extension"
            )
        )
        self.downloadErrorGroup.addButton(self.skipDownload)
        self.downloadErrorGroup.addButton(self.addIdentifier)

        self.backupErrorGroup = QButtonGroup()
        self.overwriteBackup = QRadioButton(_("Overwrite"))
        self.overwriteBackup.setToolTip(_("Overwrite the previously backed up file"))
        self.skipBackup = QRadioButton(_("Skip"))
        self.skipBackup.setToolTip(
            _("Don't overwrite the backup file, and issue an error message")
        )
        self.backupErrorGroup.addButton(self.overwriteBackup)
        self.backupErrorGroup.addButton(self.skipBackup)

        errorBoxLayout = QVBoxLayout()
        lbl = _(
            "When a photo or video of the same name has already been downloaded, "
            "choose whether to skip downloading the file, or to add a unique "
            "identifier:"
        )
        self.downloadError = QLabel(lbl)
        self.downloadError.setWordWrap(True)
        errorBoxLayout.addWidget(self.downloadError)
        errorBoxLayout.addWidget(self.skipDownload)
        errorBoxLayout.addWidget(self.addIdentifier)
        lbl = (
            "<i>"
            + _(
                "Using sequence numbers to automatically generate unique filenames is "
                "strongly recommended. Configure file renaming in the Rename panel in "
                "the main window."
            )
            + "</i>"
        )
        self.recommended = QLabel(lbl)
        self.recommended.setWordWrap(True)
        errorBoxLayout.addWidget(self.recommended)
        errorBoxLayout.addSpacing(18)
        lbl = _(
            "When backing up, choose whether to overwrite a file on the backup device "
            "that has the same name, or skip backing it up:"
        )
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

        self.warningBox = QGroupBox(_("Program Warnings"))
        lbl = _("Show a warning when:")
        self.warningLabel = QLabel(lbl)
        self.warningLabel.setWordWrap(True)
        self.warnDownloadingAll = QCheckBox(
            _("Downloading files currently not displayed")
        )
        tip = _(
            "Warn when about to download files that are not displayed in the main "
            "window."
        )
        self.warnDownloadingAll.setToolTip(tip)
        self.warnBackupProblem = QCheckBox(_("Backup destinations are missing"))
        tip = _(
            "Warn before starting a download if it is not possible to back up files."
        )
        self.warnBackupProblem.setToolTip(tip)
        self.warnMissingLibraries = QCheckBox(
            _("Program libraries are missing or broken")
        )
        tip = _(
            "Warn if a software library used by Rapid Photo Downloader is missing or "
            "not functioning."
        )
        self.warnMissingLibraries.setToolTip(tip)
        self.warnMetadata = QCheckBox(_("Filesystem metadata cannot be set"))
        tip = _(
            "Warn if there is an error setting a file's filesystem metadata, "
            "such as its modification time."
        )
        self.warnMetadata.setToolTip(tip)
        self.warnUnhandledFiles = QCheckBox(_("Encountering unhandled files"))
        tip = _(
            "Warn after scanning a device or this computer if there are unrecognized "
            "files that will not be included in the download."
        )
        self.warnUnhandledFiles.setToolTip(tip)
        self.exceptTheseFilesLabel = QLabel(
            _("Do not warn about unhandled files with extensions:")
        )
        self.exceptTheseFilesLabel.setWordWrap(True)
        self.exceptTheseFiles = QNarrowListWidget(minimum_rows=4)
        tip = _(
            "File extensions are case insensitive and do not need to include the "
            "leading dot."
        )
        self.exceptTheseFiles.setToolTip(tip)
        self.addExceptFiles = QPushButton(_("Add"))
        tip = _(
            "Add a file extension to the list of unhandled file types to not warn "
            "about."
        )
        self.addExceptFiles.setToolTip(tip)
        tip = _(
            "Remove a file extension from the list of unhandled file types to not warn "
            "about."
        )
        self.removeExceptFiles = QPushButton(_("Remove"))
        self.removeExceptFiles.setToolTip(tip)
        self.removeAllExceptFiles = QPushButton(_("Remove All"))
        tip = _(
            "Clear the list of file extensions of unhandled file types to not warn "
            "about."
        )
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
        warningBoxLayout.addWidget(self.exceptTheseFilesLabel, 6, 1, 1, 2)
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

        if consolidation_implemented:
            self.consolidationBox = QGroupBox(_("Photo and Video Consolidation"))

            self.consolidateIdentical = QCheckBox(
                _("Consolidate files across devices and downloads")
            )
            tip = _(
                "Analyze the results of device scans looking for duplicate files and "
                "matching RAW and JPEG pairs,\n"
                "comparing them across multiple devices and download sessions."
            )
            self.consolidateIdentical.setToolTip(tip)

            self.treatRawJpegLabel = QLabel(_("Treat matching RAW and JPEG files as:"))
            self.oneRawJpeg = QRadioButton(_("One photo"))
            self.twoRawJpeg = QRadioButton(_("Two photos"))
            tip = _(
                "Display matching pairs of RAW and JPEG photos as one photo, and if "
                "marked, download both."
            )
            self.oneRawJpeg.setToolTip(tip)
            tip = _(
                "Display matching pairs of RAW and JPEG photos as two different "
                "photos. You can still synchronize their sequence numbers."
            )
            self.twoRawJpeg.setToolTip(tip)

            self.treatRawJpegGroup = QButtonGroup()
            self.treatRawJpegGroup.addButton(self.oneRawJpeg)
            self.treatRawJpegGroup.addButton(self.twoRawJpeg)

            self.markRawJpegLabel = QLabel(_("With matching RAW and JPEG photos:"))

            self.noJpegWhenRaw = QRadioButton(_("Do not mark JPEG for download"))
            self.noRawWhenJpeg = QRadioButton(_("Do not mark RAW for download"))
            self.markRawJpeg = QRadioButton(_("Mark both for download"))

            self.markRawJpegGroup = QButtonGroup()
            for widget in (self.noJpegWhenRaw, self.noRawWhenJpeg, self.markRawJpeg):
                self.markRawJpegGroup.addButton(widget)

            tip = _(
                "When matching RAW and JPEG photos are found, do not automatically "
                "mark the JPEG for\n"
                "download. You can still mark it for download yourself."
            )
            self.noJpegWhenRaw.setToolTip(tip)
            tip = _(
                "When matching RAW and JPEG photos are found, do not automatically "
                "mark the RAW for\n"
                "download. You can still mark it for download yourself."
            )
            self.noRawWhenJpeg.setToolTip(tip)
            tip = _(
                "When matching RAW and JPEG photos are found, automatically mark both "
                "for download."
            )
            self.markRawJpeg.setToolTip(tip)

            explanation = _(
                "If you disable file consolidation, choose what to do when a download "
                "device is inserted while completed downloads are displayed:"
            )

        else:
            explanation = _(
                "When a download device is inserted while completed downloads are "
                "displayed:"
            )
        self.noconsolidationLabel = QLabel(explanation)
        self.noconsolidationLabel.setWordWrap(True)
        self.noconsolidationLabel.setSizePolicy(
            QSizePolicy.Ignored, QSizePolicy.Minimum
        )
        # Unless this next call is made, for some reason the widget is far too high! :-(
        self.noconsolidationLabel.setContentsMargins(0, 0, 1, 0)

        self.noConsolidationGroup = QButtonGroup()
        self.noConsolidationGroup.buttonClicked.connect(
            self.noConsolidationGroupClicked
        )

        self.clearCompletedDownloads = QRadioButton(_("Clear completed downloads"))
        self.keepCompletedDownloads = QRadioButton(
            _("Keep displaying completed downloads")
        )
        self.promptCompletedDownloads = QRadioButton(_("Prompt for what to do"))
        self.noConsolidationGroup.addButton(self.clearCompletedDownloads)
        self.noConsolidationGroup.addButton(self.keepCompletedDownloads)
        self.noConsolidationGroup.addButton(self.promptCompletedDownloads)
        tip = _(
            "Automatically clear the display of completed downloads whenever a new "
            "download device is inserted."
        )
        self.clearCompletedDownloads.setToolTip(tip)
        tip = _(
            "Keep displaying completed downloads whenever a new download device is "
            "inserted."
        )
        self.keepCompletedDownloads.setToolTip(tip)
        tip = _(
            "Prompt whether to keep displaying completed downloads or clear them "
            "whenever a new download device is inserted."
        )
        self.promptCompletedDownloads.setToolTip(tip)

        if consolidation_implemented:
            consolidationBoxLayout = QGridLayout()
            consolidationBoxLayout.addWidget(self.consolidateIdentical, 0, 0, 1, 3)

            consolidationBoxLayout.addWidget(self.treatRawJpegLabel, 1, 1, 1, 2)
            consolidationBoxLayout.addWidget(self.oneRawJpeg, 2, 1, 1, 2)
            consolidationBoxLayout.addWidget(self.twoRawJpeg, 3, 1, 1, 2)

            consolidationBoxLayout.addWidget(self.markRawJpegLabel, 4, 2, 1, 1)
            consolidationBoxLayout.addWidget(self.noJpegWhenRaw, 5, 2, 1, 1)
            consolidationBoxLayout.addWidget(self.noRawWhenJpeg, 6, 2, 1, 1)
            consolidationBoxLayout.addWidget(self.markRawJpeg, 7, 2, 1, 1, Qt.AlignTop)

            consolidationBoxLayout.addWidget(self.noconsolidationLabel, 8, 0, 1, 3)
            consolidationBoxLayout.addWidget(self.keepCompletedDownloads, 9, 0, 1, 3)
            consolidationBoxLayout.addWidget(self.clearCompletedDownloads, 10, 0, 1, 3)
            consolidationBoxLayout.addWidget(self.promptCompletedDownloads, 11, 0, 1, 3)

            consolidationBoxLayout.setColumnMinimumWidth(0, checkbox_width)
            consolidationBoxLayout.setColumnMinimumWidth(1, checkbox_width)

            consolidationBoxLayout.setRowMinimumHeight(7, checkbox_width * 2)

            self.consolidationBox.setLayout(consolidationBoxLayout)

            self.consolidation = QWidget()
            consolidationLayout = QVBoxLayout()
            consolidationLayout.addWidget(self.consolidationBox)
            consolidationLayout.addStretch()
            consolidationLayout.setContentsMargins(0, 0, 0, 0)
            consolidationLayout.setSpacing(18)
            self.consolidation.setLayout(consolidationLayout)

            self.setCompletedDownloadsValues()
            self.setConsolidatedValues()
            self.consolidateIdentical.stateChanged.connect(
                self.consolidateIdenticalChanged
            )
            self.treatRawJpegGroup.buttonClicked.connect(self.treatRawJpegGroupClicked)
            self.markRawJpegGroup.buttonClicked.connect(self.markRawJpegGroupClicked)

        if not version_check_disabled():
            self.newVersionBox = QGroupBox(_("Version Check"))
            self.checkNewVersion = QCheckBox(_("Check for new version at startup"))
            self.checkNewVersion.setToolTip(
                _(
                    "Check for a new version of the program each time the program "
                    "starts."
                )
            )
            self.includeDevRelease = QCheckBox(_("Include development releases"))
            tip = _(
                "Include alpha, beta and other development releases when checking for "
                "a new version of the program.\n\n"
                "If you are currently running a development version, the check will "
                "always occur."
            )
            self.includeDevRelease.setToolTip(tip)
            self.setVersionCheckValues()
            self.checkNewVersion.stateChanged.connect(self.checkNewVersionChanged)
            self.includeDevRelease.stateChanged.connect(self.includeDevReleaseChanged)

            newVersionLayout = QGridLayout()
            newVersionLayout.addWidget(self.checkNewVersion, 0, 0, 1, 2)
            newVersionLayout.addWidget(self.includeDevRelease, 1, 1, 1, 1)
            newVersionLayout.setColumnMinimumWidth(0, checkbox_width)
            self.newVersionBox.setLayout(newVersionLayout)

        self.metadataBox = QGroupBox(_("Metadata"))
        self.ignoreMdatatimeMtpDng = QCheckBox(
            _("Ignore DNG date/time metadata on MTP devices")
        )
        tip = _(
            "Ignore date/time metadata in DNG files located on MTP devices, and use "
            "the file's modification time instead.\n\n"
            "Useful for devices like some phones and tablets that create incorrect "
            "DNG metadata."
        )
        self.ignoreMdatatimeMtpDng.setToolTip(tip)

        self.forceExiftool = QCheckBox(_("Read photo metadata using only ExifTool"))
        tip = _(
            "Use ExifTool instead of Exiv2 to read photo metadata and extract "
            "thumbnails.\n\n"
            "The default is to use Exiv2, relying on ExifTool only when Exiv2 does not "
            "support\n"
            "the file format being read.\n\n"
            "Exiv2 is fast, accurate, and almost always reliable, but it crashes when "
            "extracting\n"
            "metadata from a small number of files, such as DNG files produced by "
            "Leica M8\n"
            "cameras."
        )

        self.forceExiftool.setToolTip(tip)

        self.setMetdataValues()
        self.ignoreMdatatimeMtpDng.stateChanged.connect(
            self.ignoreMdatatimeMtpDngChanged
        )
        self.forceExiftool.stateChanged.connect(self.forceExiftoolChanged)

        metadataLayout = QVBoxLayout()
        metadataLayout.addWidget(self.ignoreMdatatimeMtpDng)
        metadataLayout.addWidget(self.forceExiftool)
        self.metadataBox.setLayout(metadataLayout)

        if not consolidation_implemented:
            self.completedDownloadsBox = QGroupBox(_("Completed Downloads"))
            completedDownloadsLayout = QVBoxLayout()
            completedDownloadsLayout.addWidget(self.noconsolidationLabel)
            completedDownloadsLayout.addWidget(self.keepCompletedDownloads)
            completedDownloadsLayout.addWidget(self.clearCompletedDownloads)
            completedDownloadsLayout.addWidget(self.promptCompletedDownloads)
            self.completedDownloadsBox.setLayout(completedDownloadsLayout)
            self.setCompletedDownloadsValues()

        self.miscWidget = QWidget()
        miscLayout = QVBoxLayout()
        if not version_check_disabled():
            miscLayout.addWidget(self.newVersionBox)
        miscLayout.addWidget(self.metadataBox)
        if not consolidation_implemented:
            miscLayout.addWidget(self.completedDownloadsBox)
        miscLayout.addStretch()
        miscLayout.setContentsMargins(0, 0, 0, 0)
        miscLayout.setSpacing(18)
        self.miscWidget.setLayout(miscLayout)

        self.panels.addWidget(self.devices)
        self.panels.addWidget(self.language)
        self.panels.addWidget(self.automation)
        self.panels.addWidget(self.performance)
        self.panels.addWidget(self.timeZone)
        self.panels.addWidget(self.errorWidget)
        self.panels.addWidget(self.warnings)
        if consolidation_implemented:
            self.panels.addWidget(self.consolidation)
        self.panels.addWidget(self.miscWidget)

        layout = QVBoxLayout()
        self.setLayout(layout)
        layout.setSpacing(layout.contentsMargins().left() * 2)
        layout.setContentsMargins(18, 18, 18, 18)

        buttons = QDialogButtonBox(
            QDialogButtonBox.RestoreDefaults
            | QDialogButtonBox.Close
            | QDialogButtonBox.Help
        )
        translateDialogBoxButtons(buttons)
        self.restoreButton = buttons.button(
            QDialogButtonBox.RestoreDefaults
        )  # type: QPushButton
        self.restoreButton.clicked.connect(self.restoreDefaultsClicked)
        self.helpButton = buttons.button(QDialogButtonBox.Help)  # type: QPushButton
        self.helpButton.clicked.connect(self.helpButtonClicked)
        self.helpButton.setToolTip(_("Get help online..."))
        self.closeButton = buttons.button(QDialogButtonBox.Close)  # type: QPushButton
        self.closeButton.clicked.connect(self.close)

        controlsLayout = QHBoxLayout()
        controlsLayout.addWidget(self.chooser)
        controlsLayout.addWidget(self.panels)

        controlsLayout.setStretch(0, 0)
        controlsLayout.setStretch(1, 1)
        controlsLayout.setSpacing(layout.contentsMargins().left())

        layout.addLayout(controlsLayout)
        layout.addWidget(buttons)

        self.device_right_side_buttons = (
            self.removeDevice,
            self.removeAllDevice,
            self.addPath,
            self.removePath,
            self.removeAllPath,
        )

        self.device_list_widgets = (self.knownDevices, self.ignoredPaths)
        self.chooser.setCurrentRow(0)

    def reject(self) -> None:
        # If not called, rejecting this dialog will cause Rapid Photo Downloader to
        # crash
        self.close()

    def _addItems(self, pref_list: str, pref_type: int) -> None:
        if self.prefs.list_not_empty(key=pref_list):
            for value in self.prefs[pref_list]:
                QListWidgetItem(value, self.knownDevices, pref_type)

    def setDeviceWidgetValues(self) -> None:
        self.onlyExternal.setChecked(self.prefs.only_external_mounts)
        self.scanSpecificFolders.setChecked(self.prefs.scan_specific_folders)
        self.setFoldersToScanWidgetValues()
        self.knownDevices.clear()
        self._addItems("volume_whitelist", KnownDeviceType.volume_whitelist)
        self._addItems("volume_blacklist", KnownDeviceType.volume_blacklist)
        self._addItems("camera_blacklist", KnownDeviceType.camera_blacklist)
        if self.knownDevices.count():
            self.knownDevices.setCurrentRow(0)
        self.removeDevice.setEnabled(self.knownDevices.count())
        self.removeAllDevice.setEnabled(self.knownDevices.count())
        self.setIgnorePathWidgetValues()

    def setLanguageWidgetValues(self) -> None:
        # Translators: this is an option when the user chooses the language to use for
        # Rapid Photo Downloader and it allows them to reset it back to whatever their
        # system language settings are. The < and > are not HTML codes. They are there
        # simply to set this choice apart from all the other choices in the drop down
        # list. You can keep the < > if you like, or replace them with whatever you
        # typically use in your language.
        self.languages.addItem(_("<System Language>"), system_language)
        for code, language in available_languages(
            display_locale_code=self.prefs.language
        ):
            self.languages.addItem(language, code)
        value = self.prefs.language
        if value:
            index = self.languages.findData(value)
            self.languages.setCurrentIndex(index)

    def setFoldersToScanWidgetValues(self) -> None:
        self.foldersToScan.clear()
        if self.prefs.list_not_empty("folders_to_scan"):
            self.foldersToScan.addItems(self.prefs.folders_to_scan)
            self.foldersToScan.setCurrentRow(0)
        self.setFoldersToScanState()

    def setFoldersToScanState(self) -> None:
        scan_specific = self.prefs.scan_specific_folders
        self.foldersToScanLabel.setEnabled(scan_specific)
        self.foldersToScan.setEnabled(scan_specific)
        self.addFolderToScan.setEnabled(scan_specific)
        self.removeFolderToScan.setEnabled(
            scan_specific and self.foldersToScan.count() > 1
        )

    def setIgnorePathWidgetValues(self) -> None:
        self.ignoredPaths.clear()
        if self.prefs.list_not_empty("ignored_paths"):
            self.ignoredPaths.addItems(self.prefs.ignored_paths)
            self.ignoredPaths.setCurrentRow(0)
        self.removePath.setEnabled(self.ignoredPaths.count())
        self.removeAllPath.setEnabled(self.ignoredPaths.count())
        self.ignoredPathsRe.setChecked(self.prefs.use_re_ignored_paths)

    def setAutomationWidgetValues(self) -> None:
        self.autoMount.setChecked(self.prefs.auto_mount)
        self.autoDownloadStartup.setChecked(self.prefs.auto_download_at_startup)
        self.autoDownloadInsertion.setChecked(
            self.prefs.auto_download_upon_device_insertion
        )
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

    def setPerformanceValues(self, check_boxes_only: bool = False) -> None:
        self.generateThumbnails.setChecked(self.prefs.generate_thumbnails)
        self.useThumbnailCache.setChecked(
            self.prefs.use_thumbnail_cache and self.prefs.generate_thumbnails
        )
        self.fdoThumbnails.setChecked(
            self.prefs.save_fdo_thumbnails and self.prefs.generate_thumbnails
        )

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
        self.thumbnailSqlSize.setText(
            format_size_for_user(self.thumbnail_cache.db_size())
        )
        self.thumbnailCacheDaysKeep.setValue(self.prefs.keep_thumbnails_days)

    @pyqtSlot("PyQt_PyObject")
    def setCacheSize(self, size: int) -> None:
        self.thumbnailCacheSize.setText(format_size_for_user(size))

    def setTimeZoneValues(self) -> None:
        ignore = self.prefs.ignore_time_zone_changes
        self.ignoreTimeZone.setChecked(ignore)
        self.timeZoneOffsetResolution.setCurrentText(
            str(self.prefs.time_zone_offset_resolution)
        )
        self.timeZoneOffset.setEnabled(ignore)
        self.timeZoneOffsetLabel.setEnabled(ignore)

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
        self.warnMissingLibraries.setChecked(
            self.prefs.warn_broken_or_missing_libraries
        )
        self.warnMetadata.setChecked(self.prefs.warn_fs_metadata_error)
        self.warnUnhandledFiles.setChecked(self.prefs.warn_unhandled_files)
        self.setAddExceptFilesValues()

        self.setBackupWarningEnabled()
        self.setUnhandledWarningEnabled()

    def setAddExceptFilesValues(self) -> None:
        self.exceptTheseFiles.clear()
        if self.prefs.list_not_empty("ignore_unhandled_file_exts"):
            self.exceptTheseFiles.addItems(self.prefs.ignore_unhandled_file_exts)
            self.exceptTheseFiles.setCurrentRow(0)

    def setBackupWarningEnabled(self) -> None:
        self.warnBackupProblem.setEnabled(self.prefs.backup_files)

    def setUnhandledWarningEnabled(self) -> None:
        enabled = self.prefs.warn_unhandled_files
        for widget in (
            self.exceptTheseFilesLabel,
            self.exceptTheseFiles,
            self.addExceptFiles,
        ):
            widget.setEnabled(enabled)
        count = bool(self.exceptTheseFiles.count())
        for widget in (self.removeExceptFiles, self.removeAllExceptFiles):
            widget.setEnabled(enabled and count)

    def setConsolidatedValues(self) -> None:
        enabled = self.prefs.consolidate_identical
        self.consolidateIdentical.setChecked(enabled)

        self.setTreatRawJpeg()
        self.setMarkRawJpeg()

        if enabled:
            # Must turn off the exclusive button group feature, or else
            # it's impossible to set all the radio buttons to False
            self.noConsolidationGroup.setExclusive(False)
            for widget in (
                self.clearCompletedDownloads,
                self.keepCompletedDownloads,
                self.promptCompletedDownloads,
            ):
                widget.setChecked(False)
            # Now turn it back on again
            self.noConsolidationGroup.setExclusive(True)
        else:
            self.setCompletedDownloadsValues()

        self.setConsolidatedEnabled()

    def setTreatRawJpeg(self) -> None:
        if self.prefs.consolidate_identical:
            if self.prefs.treat_raw_jpeg == int(TreatRawJpeg.one_photo):
                self.oneRawJpeg.setChecked(True)
            else:
                self.twoRawJpeg.setChecked(True)
        else:
            # Must turn off the exclusive button group feature, or else
            # it's impossible to set all the radio buttons to False
            self.treatRawJpegGroup.setExclusive(False)
            self.oneRawJpeg.setChecked(False)
            self.twoRawJpeg.setChecked(False)
            # Now turn it back on again
            self.treatRawJpegGroup.setExclusive(True)

    def setMarkRawJpeg(self) -> None:
        if self.prefs.consolidate_identical and self.twoRawJpeg.isChecked():
            v = self.prefs.mark_raw_jpeg
            if v == int(MarkRawJpeg.no_jpeg):
                self.noJpegWhenRaw.setChecked(True)
            elif v == int(MarkRawJpeg.no_raw):
                self.noRawWhenJpeg.setChecked(True)
            else:
                self.markRawJpeg.setChecked(True)
        else:
            # Must turn off the exclusive button group feature, or else
            # it's impossible to set all the radio buttons to False
            self.markRawJpegGroup.setExclusive(False)
            for widget in (self.noJpegWhenRaw, self.noRawWhenJpeg, self.markRawJpeg):
                widget.setChecked(False)
            # Now turn it back on again
            self.markRawJpegGroup.setExclusive(True)

    def setConsolidatedEnabled(self) -> None:
        enabled = self.prefs.consolidate_identical

        for widget in self.treatRawJpegGroup.buttons():
            widget.setEnabled(enabled)
        self.treatRawJpegLabel.setEnabled(enabled)

        self.setMarkRawJpegEnabled()

        for widget in (
            self.noconsolidationLabel,
            self.clearCompletedDownloads,
            self.keepCompletedDownloads,
            self.promptCompletedDownloads,
        ):
            widget.setEnabled(not enabled)

    def setMarkRawJpegEnabled(self) -> None:
        mark_enabled = self.prefs.consolidate_identical and self.twoRawJpeg.isChecked()
        for widget in self.markRawJpegGroup.buttons():
            widget.setEnabled(mark_enabled)
        self.markRawJpegLabel.setEnabled(mark_enabled)

    def setVersionCheckValues(self) -> None:
        self.checkNewVersion.setChecked(self.prefs.check_for_new_versions)
        self.includeDevRelease.setChecked(
            self.prefs.include_development_release or self.is_prerelease
        )
        self.setVersionCheckEnabled()

    def setVersionCheckEnabled(self) -> None:
        self.includeDevRelease.setEnabled(
            not (self.is_prerelease or not self.prefs.check_for_new_versions)
        )

    def setMetdataValues(self) -> None:
        self.ignoreMdatatimeMtpDng.setChecked(self.prefs.ignore_mdatatime_for_mtp_dng)
        self.forceExiftool.setChecked(self.prefs.force_exiftool)

    def setCompletedDownloadsValues(self) -> None:
        s = self.prefs.completed_downloads
        if s == int(CompletedDownloads.keep):
            self.keepCompletedDownloads.setChecked(True)
        elif s == int(CompletedDownloads.clear):
            self.clearCompletedDownloads.setChecked(True)
        else:
            self.promptCompletedDownloads.setChecked(True)

    @pyqtSlot(int)
    def onlyExternalChanged(self, state: int) -> None:
        self.prefs.only_external_mounts = state == Qt.Checked
        if self.rapidApp is not None:
            self.rapidApp.search_for_devices_again = True

    @pyqtSlot(int)
    def noDcimChanged(self, state: int) -> None:
        self.prefs.scan_specific_folders = state == Qt.Checked
        self.setFoldersToScanState()
        if self.rapidApp is not None:
            self.rapidApp.scan_non_cameras_again = True

    @pyqtSlot(int)
    def ignoredPathsReChanged(self, state: int) -> None:
        self.prefs.use_re_ignored_paths = state == Qt.Checked
        if self.rapidApp is not None:
            self.rapidApp.scan_all_again = True

    def _equalizeWidgetWidth(self, widget_list) -> None:
        max_width = round(max(widget.width() for widget in widget_list))
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
        self.restoreButton.setToolTip(
            _("Restores default %s preference values") % self.chooser_items[row]
        )

    @pyqtSlot()
    def removeDeviceClicked(self) -> None:
        row = self.knownDevices.currentRow()
        item = self.knownDevices.takeItem(row)  # type: QListWidgetItem
        known_device_type = item.type()
        if known_device_type == KnownDeviceType.volume_whitelist:
            self.prefs.del_list_value("volume_whitelist", item.text())
        elif known_device_type == KnownDeviceType.volume_blacklist:
            self.prefs.del_list_value("volume_blacklist", item.text())
        else:
            assert known_device_type == KnownDeviceType.camera_blacklist
            self.prefs.del_list_value("camera_blacklist", item.text())

        self.removeDevice.setEnabled(self.knownDevices.count())
        self.removeAllDevice.setEnabled(self.knownDevices.count())

        if self.rapidApp is not None:
            self.rapidApp.search_for_devices_again = True

    @pyqtSlot()
    def removeAllDeviceClicked(self) -> None:
        self.knownDevices.clear()
        self.prefs.volume_whitelist = [""]
        self.prefs.volume_blacklist = [""]
        self.prefs.camera_blacklist = [""]
        self.removeDevice.setEnabled(False)
        self.removeAllDevice.setEnabled(False)

        if self.rapidApp is not None:
            self.rapidApp.search_for_devices_again = True

    @pyqtSlot()
    def removeFolderToScanClicked(self) -> None:
        row = self.foldersToScan.currentRow()
        if row >= 0 and self.foldersToScan.count() > 1:
            item = self.foldersToScan.takeItem(row)
            self.prefs.del_list_value("folders_to_scan", item.text())
            self.removeFolderToScan.setEnabled(self.foldersToScan.count() > 1)

            if self.rapidApp is not None:
                self.rapidApp.scan_all_again = True

    @pyqtSlot()
    def addFolderToScanClicked(self) -> None:
        dlg = FoldersToScanDialog(prefs=self.prefs, parent=self)
        if dlg.exec():
            self.setFoldersToScanWidgetValues()

            if self.rapidApp is not None:
                self.rapidApp.scan_all_again = True

    @pyqtSlot()
    def removePathClicked(self) -> None:
        row = self.ignoredPaths.currentRow()
        if row >= 0:
            item = self.ignoredPaths.takeItem(row)
            self.prefs.del_list_value("ignored_paths", item.text())
            self.removePath.setEnabled(self.ignoredPaths.count())
            self.removeAllPath.setEnabled(self.ignoredPaths.count())

            if self.rapidApp is not None:
                self.rapidApp.scan_all_again = True

    @pyqtSlot()
    def removeAllPathClicked(self) -> None:
        self.ignoredPaths.clear()
        self.prefs.ignored_paths = [""]
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
    def languagesChanged(self, index: int) -> None:
        if index == 0:
            self.prefs.language = ""
            logging.info("Resetting user interface language to system default")
        elif index > 0:
            self.prefs.language = self.languages.currentData()
            logging.info("Setting user interface language to %s", self.prefs.language)

    @pyqtSlot(int)
    def autoMountChanged(self, state: int) -> None:
        on = state == Qt.Checked
        self.prefs.auto_mount = on
        if self.rapidApp.use_udsisks:
            if not on:
                self.rapidApp.start_monitoring_mount_count = True
                self.rapidApp.stop_monitoring_mount_count = False
            else:
                self.rapidApp.stop_monitoring_mount_count = True
                self.rapidApp.start_monitoring_mount_count = False

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
        message = _(
            "Do you want to purge the thumbnail cache? The cache will be purged when "
            "the program is next started."
        )
        msgBox = standardMessageBox(
            parent=self,
            title=_("Purge Thumbnail Cache"),
            message=message,
            standardButtons=QMessageBox.Yes | QMessageBox.No,
            rich_text=False,
        )

        if msgBox.exec_() == QMessageBox.Yes:
            self.prefs.purge_thumbnails = True
            self.prefs.optimize_thumbnail_db = False
        else:
            self.prefs.purge_thumbnails = False

    @pyqtSlot()
    def optimizeCacheClicked(self) -> None:
        message = _(
            "Do you want to optimize the thumbnail cache? The cache will be optimized "
            "when the program is next started."
        )
        msgBox = standardMessageBox(
            parent=self,
            title=_("Optimize Thumbnail Cache"),
            message=message,
            standardButtons=QMessageBox.Yes | QMessageBox.No,
            rich_text=False,
        )
        if msgBox.exec_() == QMessageBox.Yes:
            self.prefs.purge_thumbnails = False
            self.prefs.optimize_thumbnail_db = True
        else:
            self.prefs.optimize_thumbnail_db = False

    @pyqtSlot(int)
    def ignoreTimeZoneChanged(self, state: int) -> None:
        ignore = state == Qt.Checked
        self.prefs.ignore_time_zone_changes = ignore
        self.timeZoneOffset.setEnabled(ignore)
        self.timeZoneOffsetLabel.setEnabled(ignore)

    @pyqtSlot(int)
    def timeZoneOffsetResolutionChanged(self, index: int) -> None:
        self.prefs.time_zone_offset_resolution = int(
            self.timeZoneOffsetResolution.currentText()
        )

    @pyqtSlot(QAbstractButton)
    def downloadErrorGroupClicked(self, button: QRadioButton) -> None:
        if self.downloadErrorGroup.checkedButton() == self.skipDownload:
            self.prefs.conflict_resolution = int(ConflictResolution.skip)
        else:
            self.prefs.conflict_resolution = int(ConflictResolution.add_identifier)

    @pyqtSlot(QAbstractButton)
    def backupErrorGroupClicked(self, button: QRadioButton) -> None:
        self.prefs.backup_duplicate_overwrite = (
            self.backupErrorGroup.checkedButton() == self.overwriteBackup
        )

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
            self.prefs.del_list_value("ignore_unhandled_file_exts", item.text())
            self.removeExceptFiles.setEnabled(self.exceptTheseFiles.count())
            self.removeAllExceptFiles.setEnabled(self.exceptTheseFiles.count())

    @pyqtSlot()
    def removeAllExceptFilesClicked(self) -> None:
        self.exceptTheseFiles.clear()
        self.prefs.ignore_unhandled_file_exts = [""]
        self.removeExceptFiles.setEnabled(False)
        self.removeAllExceptFiles.setEnabled(False)

    @pyqtSlot(int)
    def consolidateIdenticalChanged(self, state: int) -> None:
        self.prefs.consolidate_identical = state == Qt.Checked
        self.setConsolidatedValues()
        self.setConsolidatedEnabled()

    @pyqtSlot(QAbstractButton)
    def treatRawJpegGroupClicked(self, button: QRadioButton) -> None:
        if button == self.oneRawJpeg:
            self.prefs.treat_raw_jpeg = int(TreatRawJpeg.one_photo)
        else:
            self.prefs.treat_raw_jpeg = int(TreatRawJpeg.two_photos)
        self.setMarkRawJpeg()
        self.setMarkRawJpegEnabled()

    @pyqtSlot(QAbstractButton)
    def markRawJpegGroupClicked(self, button: QRadioButton) -> None:
        if button == self.noJpegWhenRaw:
            self.prefs.mark_raw_jpeg = int(MarkRawJpeg.no_jpeg)
        elif button == self.noRawWhenJpeg:
            self.prefs.mark_raw_jpeg = int(MarkRawJpeg.no_raw)
        else:
            self.prefs.mark_raw_jpeg = int(MarkRawJpeg.both)

    @pyqtSlot(int)
    def noJpegWhenRawChanged(self, state: int) -> None:
        self.prefs.do_not_mark_jpeg = state == Qt.Checked

    @pyqtSlot(int)
    def noRawWhenJpegChanged(self, state: int) -> None:
        self.prefs.do_not_mark_raw = state == Qt.Checked

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

    @pyqtSlot(int)
    def forceExiftoolChanged(self, state: int) -> None:
        self.prefs.force_exiftool = state == Qt.Checked

    @pyqtSlot(QAbstractButton)
    def noConsolidationGroupClicked(self, button: QRadioButton) -> None:
        if button == self.keepCompletedDownloads:
            self.prefs.completed_downloads = int(CompletedDownloads.keep)
        elif button == self.clearCompletedDownloads:
            self.prefs.completed_downloads = int(CompletedDownloads.clear)
        else:
            self.prefs.completed_downloads = int(CompletedDownloads.prompt)

    @pyqtSlot()
    def restoreDefaultsClicked(self) -> None:
        row = self.chooser.currentRow()
        if row == 0:
            for value in (
                "only_external_mounts",
                "scan_specific_folders",
                "folders_to_scan",
                "ignored_paths",
                "use_re_ignored_paths",
            ):
                self.prefs.restore(value)
            self.removeAllDeviceClicked()
            self.setDeviceWidgetValues()
        elif row == 1:
            self.prefs.restore("language")
            self.languages.setCurrentIndex(0)
        elif row == 2:
            for value in (
                "auto_mount",
                "auto_download_at_startup",
                "auto_download_upon_device_insertion",
                "auto_unmount",
                "auto_exit",
                "auto_exit_force",
            ):
                self.prefs.restore(value)
            self.setAutomationWidgetValues()
        elif row == 3:
            for value in (
                "generate_thumbnails",
                "use_thumbnail_cache",
                "save_fdo_thumbnails",
                "max_cpu_cores",
                "keep_thumbnails_days",
            ):
                self.prefs.restore(value)
            self.setPerformanceValues(check_boxes_only=True)
            self.maxCores.setCurrentText(str(self.prefs.max_cpu_cores))
            self.setPerfomanceEnabled()
            self.thumbnailCacheDaysKeep.setValue(self.prefs.keep_thumbnails_days)
        elif row == 4:
            for value in ("ignore_time_zone_changes", "time_zone_offset_resolution"):
                self.prefs.restore(value)
                self.setTimeZoneValues()
        elif row == 5:
            for value in ("conflict_resolution", "backup_duplicate_overwrite"):
                self.prefs.restore(value)
            self.setErrorHandingValues()
        elif row == 6:
            for value in (
                "warn_downloading_all",
                "warn_backup_problem",
                "warn_broken_or_missing_libraries",
                "warn_fs_metadata_error",
                "warn_unhandled_files",
                "ignore_unhandled_file_exts",
            ):
                self.prefs.restore(value)
            self.setWarningValues()
        elif row == 7 and consolidation_implemented:
            for value in (
                "completed_downloads",
                "consolidate_identical",
                "one_raw_jpeg",
                "do_not_mark_jpeg",
                "do_not_mark_raw",
            ):
                self.prefs.restore(value)
            self.setConsolidatedValues()
        elif (row == 8 and consolidation_implemented) or (
            row == 7 and not consolidation_implemented
        ):
            if not version_check_disabled():
                self.prefs.restore("check_for_new_versions")
            for value in (
                "include_development_release",
                "ignore_mdatatime_for_mtp_dng",
                "force_exiftool",
            ):
                self.prefs.restore(value)
            if not consolidation_implemented:
                self.prefs.restore("completed_downloads")
            if not version_check_disabled():
                self.setVersionCheckValues()
            self.setMetdataValues()
            if not consolidation_implemented:
                self.setCompletedDownloadsValues()

    @pyqtSlot()
    def helpButtonClicked(self) -> None:
        row = self.chooser.currentRow()
        if row == 0:
            location = "#devicepreferences"
        elif row == 1:
            location = "#languagepreferences"
        elif row == 2:
            location = "#automationpreferences"
        elif row == 3:
            location = "#thumbnailpreferences"
        elif row == 4:
            location = "#timezonehandling"
        elif row == 5:
            location = "#errorhandlingpreferences"
        elif row == 6:
            location = "#warningpreferences"
        elif row == 7:
            if consolidation_implemented:
                location = "#consolidationpreferences"
            else:
                location = "#miscellaneousnpreferences"
        elif row == 8:
            location = "#miscellaneousnpreferences"
        else:
            location = ""

        webbrowser.open_new_tab(
            "https://www.damonlynch.net/rapid/documentation/{}".format(location)
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        self.cacheSizeThread.quit()
        self.cacheSizeThread.wait(1000)
        event.accept()


class PreferenceAddDialog(QDialog):
    """
    Base class for adding value to pref list
    """

    def __init__(
        self,
        prefs: Preferences,
        title: str,
        instruction: str,
        label: str,
        pref_value: str,
        parent=None,
    ) -> None:
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
        translateDialogBoxButtons(buttons)
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


class FoldersToScanDialog(PreferenceAddDialog):
    """
    Dialog prompting for a folder on devices to scan for photos and videos
    """

    def __init__(self, prefs: Preferences, parent=None) -> None:
        super().__init__(
            prefs=prefs,
            title=_("Enter a Folder to Scan"),
            instruction=_(
                "Specify a folder that will be scanned for photos and videos"
            ),
            label=_("Folder:"),
            pref_value="folders_to_scan",
            parent=parent,
        )


class IgnorePathDialog(PreferenceAddDialog):
    """
    Dialog prompting for a path to ignore when scanning devices
    """

    def __init__(self, prefs: Preferences, parent=None) -> None:
        super().__init__(
            prefs=prefs,
            title=_("Enter a Path to Ignore"),
            instruction=_(
                "Specify a path that will never be scanned for photos or videos"
            ),
            label=_("Path:"),
            pref_value="ignored_paths",
            parent=parent,
        )


class ExceptFileExtDialog(PreferenceAddDialog):
    """
    Dialog prompting for file extensions never to warn about
    """

    def __init__(self, prefs: Preferences, parent=None) -> None:
        super().__init__(
            prefs=prefs,
            title=_("Enter a File Extension"),
            instruction=_("Specify a file extension (without the leading dot)"),
            label=_("Extension:"),
            pref_value="ignore_unhandled_file_exts",
            parent=parent,
        )

    def exts(self, exts: List[str]) -> str:
        return make_internationalized_list([ext.upper() for ext in exts])

    def accept(self):
        value = self.valueEdit.text()
        if value:
            while value.startswith("."):
                value = value[1:]
            value = value.upper()
            if value.lower() in ALL_KNOWN_EXTENSIONS:
                title = _("Invalid File Extension")
                # Translators: please do not change HTML codes like <br>, <i>, </i>,
                # or <b>, </b> etc.
                message = (
                    _(
                        "The file extension <b>%s</b> is recognized by Rapid Photo "
                        "Downloader, so it makes no sense to warn about its presence."
                    )
                    % value
                )
                # Translators: %(variable)s represents Python code, not a plural of
                # the term variable. You must keep the %(variable)s untranslated, or the
                # program will crash.
                details = _(
                    "Recognized file types:\n\n"
                    "Photos:\n%(photos)s\n\nVideos:\n%(videos)s\n\n"
                    "Audio:\n%(audio)s\n\nOther:\n%(other)s"
                ) % dict(
                    photos=self.exts(PHOTO_EXTENSIONS),
                    videos=self.exts(VIDEO_EXTENSIONS + VIDEO_THUMBNAIL_EXTENSIONS),
                    audio=self.exts(AUDIO_EXTENSIONS),
                    other=self.exts(["xmp"]),
                )
                msgBox = standardMessageBox(
                    parent=self,
                    title=title,
                    message=message,
                    rich_text=True,
                    standardButtons=QMessageBox.Ok,
                    iconType=QMessageBox.Information,
                )
                msgBox.setDetailedText(details)
                msgBox.exec()
                self.valueEdit.setText(value)
                self.valueEdit.selectAll()
                return
            else:
                self.prefs.add_list_value(self.pref_value, value)
        QDialog.accept(self)


class CacheSize(QObject):
    size = pyqtSignal("PyQt_PyObject")  # don't convert python int to C++ int

    @pyqtSlot()
    def start(self) -> None:
        self.thumbnail_cache = ThumbnailCacheSql(create_table_if_not_exists=False)

    @pyqtSlot()
    def getCacheSize(self) -> None:
        self.size.emit(self.thumbnail_cache.cache_size())


if __name__ == "__main__":

    # Application development test code:

    app = QApplication([])

    app.setOrganizationName("Rapid Photo Downloader")
    app.setOrganizationDomain("damonlynch.net")
    app.setApplicationName("Rapid Photo Downloader")

    prefs = Preferences()

    prefDialog = PreferencesDialog(prefs)
    prefDialog.show()
    app.exec_()
