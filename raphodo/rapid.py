#!/usr/bin/env python3

# Copyright (C) 2011-2020 Damon Lynch <damonlynch@gmail.com>

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
# along with Rapid Photo Downloader. If not,
# see <http://www.gnu.org/licenses/>.

"""
Primary logic for Rapid Photo Downloader.

Qt related class method and variable names use CamelCase.
Everything else should follow PEP 8.
Project line length: 100 characters (i.e. word wrap at 99)

"Hamburger" Menu Icon by Daniel Bruce -- www.entypo.com
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2011-2020, Damon Lynch"

import sys
import logging

import shutil
import datetime
import locale

try:
    # Use the default locale as defined by the LANG variable
    locale.setlocale(locale.LC_ALL, '')
except locale.Error:
    pass

from collections import namedtuple, defaultdict
import platform
import argparse
from typing import Optional, Tuple, List, Sequence, Dict, Set, Any, DefaultDict
import faulthandler
import pkg_resources as pkgr
import webbrowser
import time
import shlex
import subprocess
from urllib.request import pathname2url
import inspect

import dateutil

import gi
gi.require_version('Notify', '0.7')
from gi.repository import Notify

try:
    gi.require_version('Unity', '7.0')
    from gi.repository import Unity
    launcher = 'net.damonlynch.rapid_photo_downloader.desktop'
    Unity.LauncherEntry.get_for_desktop_id(launcher)
    have_unity = True
except (ImportError, ValueError, gi.repository.GLib.GError):
    have_unity = False

import zmq
import psutil
import arrow
import gphoto2 as gp
from PyQt5 import QtCore
from PyQt5.QtCore import (
    QThread, Qt, QStorageInfo, QSettings, QPoint, QSize, QTimer, QTextStream, QModelIndex,
    pyqtSlot, QRect, pyqtSignal, QObject, QEvent, QLocale, 
)
from PyQt5.QtGui import (
    QIcon, QPixmap, QImage, QColor, QPalette, QFontMetrics, QFont, QPainter, QMoveEvent, QBrush,
    QPen, QColor, QScreen, QDesktopServices
)
from PyQt5.QtWidgets import (
    QAction, QApplication, QMainWindow, QMenu, QWidget, QDialogButtonBox,
    QProgressBar, QSplitter, QHBoxLayout, QVBoxLayout, QDialog, QLabel, QComboBox, QGridLayout,
    QCheckBox, QSizePolicy, QMessageBox, QSplashScreen, QStackedWidget, QScrollArea,
    QStyledItemDelegate, QPushButton, QDesktopWidget
)
from PyQt5.QtNetwork import QLocalSocket, QLocalServer

# PyQt 5.11 introduces from PyQt5 import sip i.e. from a 'private' sip, unique
# to PyQt5. However we cannot assume that distros will follow this mechanism.
# So as a defensive measure, merely import sip, doing this only after Qt has
# already been imported. See:
# http://pyqt.sourceforge.net/Docs/PyQt5/incompatibilities.html#importing-the-sip-module
import sip

from raphodo.storage import (
    ValidMounts, CameraHotplug, UDisks2Monitor, GVolumeMonitor, have_gio,
    has_one_or_more_folders, mountPaths, get_desktop_environment, get_desktop,
    gvfs_controls_mounts, get_default_file_manager, validate_download_folder,
    validate_source_folder, get_fdo_cache_thumb_base_directory, WatchDownloadDirs, get_media_dir,
    StorageSpace, gvfs_gphoto2_path, get_uri
)
from raphodo.interprocess import (
    ScanArguments, CopyFilesArguments, RenameAndMoveFileData, BackupArguments,
    BackupFileData, OffloadData, ProcessLoggingManager, ThumbnailDaemonData, ThreadNames,
    OffloadManager, CopyFilesManager, ThumbnailDaemonManager,
    ScanManager, BackupManager, stop_process_logging_manager, RenameMoveFileManager,
    create_inproc_msg)
from raphodo.devices import (
    Device, DeviceCollection, BackupDevice, BackupDeviceCollection, FSMetadataErrors
)
from raphodo.preferences import Preferences
from raphodo.constants import (
    BackupLocationType, DeviceType, ErrorType, FileType, DownloadStatus, RenameAndMoveStatus,
    ApplicationState, CameraErrorCode, TemporalProximityState, ThumbnailBackgroundName,
    Desktop, BackupFailureType, DeviceState, Sort, Show, DestinationDisplayType,
    DisplayingFilesOfType, DownloadingFileTypes, RememberThisMessage, RightSideButton,
    CheckNewVersionDialogState, CheckNewVersionDialogResult, RememberThisButtons,
    BackupStatus, CompletedDownloads, disable_version_check, FileManagerType, ScalingAction,
    ScalingDetected
)
from raphodo.thumbnaildisplay import (
    ThumbnailView, ThumbnailListModel, ThumbnailDelegate, DownloadStats, MarkedSummary
)
from raphodo.devicedisplay import (DeviceModel, DeviceView, DeviceDelegate)
from raphodo.proximity import (TemporalProximityGroups, TemporalProximity)
from raphodo.utilities import (
    same_device, make_internationalized_list, thousands, addPushButtonLabelSpacer,
    make_html_path_non_breaking, prefs_list_from_gconftool2_string,
    pref_bool_from_gconftool2_string, extract_file_from_tar, format_size_for_user,
    is_snap, version_check_disabled, installed_using_pip, getQtSystemTranslation
)
from raphodo.rememberthisdialog import RememberThisDialog
import raphodo.utilities
from raphodo.rpdfile import (
    RPDFile, file_types_by_number, FileTypeCounter, Video, Photo, FileSizeSum
)
import raphodo.fileformats as fileformats
import raphodo.downloadtracker as downloadtracker
from raphodo.cache import ThumbnailCacheSql
from raphodo.programversions import gexiv2_version, exiv2_version, EXIFTOOL_VERSION
from raphodo.metadatavideo import pymedia_version_info, libmediainfo_missing
from raphodo.camera import (
    gphoto2_version, python_gphoto2_version, dump_camera_details, gphoto2_python_logging,
    autodetect_cameras
)
from raphodo.rpdsql import DownloadedSQL
from raphodo.generatenameconfig import *
from raphodo.rotatedpushbutton import RotatedButton, FlatButton
from raphodo.primarybutton import TopPushButton, DownloadButton
from raphodo.filebrowse import (
    FileSystemView, FileSystemModel, FileSystemFilter, FileSystemDelegate
)
from raphodo.toggleview import QToggleView
import raphodo.__about__ as __about__
import raphodo.iplogging as iplogging
import raphodo.excepthook as excepthook
from raphodo.panelview import QPanelView
from raphodo.computerview import ComputerWidget
from raphodo.folderspreview import DownloadDestination, FoldersPreview
from raphodo.destinationdisplay import DestinationDisplay
from raphodo.aboutdialog import AboutDialog
import raphodo.constants as constants
from raphodo.menubutton import MenuButton
from raphodo.renamepanel import RenamePanel
from raphodo.jobcodepanel import JobCodePanel
from raphodo.backuppanel import BackupPanel
import raphodo
import raphodo.exiftool as exiftool
from raphodo.newversion import (
    NewVersion, NewVersionCheckDialog, version_details, DownloadNewVersionDialog
)
from raphodo.chevroncombo import ChevronCombo
from raphodo.preferencedialog import PreferencesDialog
from raphodo.errorlog import ErrorReport, SpeechBubble
from raphodo.problemnotification import (
    FsMetadataWriteProblem, Problem, Problems, CopyingProblems, RenamingProblems, BackingUpProblems
)
from raphodo.viewutils import (
    standardIconSize, qt5_screen_scale_environment_variable, QT5_VERSION, validateWindowSizeLimit,
    validateWindowPosition, scaledIcon, any_screen_scaled, standardMessageBox
)
from raphodo import viewutils
import raphodo.didyouknow as didyouknow
from raphodo.thumbnailextractor import gst_version, libraw_version, rawkit_version
from raphodo.heif import have_heif_module, pyheif_version, libheif_version
from raphodo.filesystemurl import FileSystemUrlHandler


# Avoid segfaults at exit:
# http://pyqt.sourceforge.net/Docs/PyQt5/gotchas.html#crashes-on-exit
app = None  # type: 'QtSingleApplication'

faulthandler.enable()
logger = None
sys.excepthook = excepthook.excepthook


class FolderPreviewManager(QObject):
    """
    Manages sending FoldersPreview() off to the offload process to
    generate new provisional download subfolders, and removing provisional download subfolders
    in the main process, using QFileSystemModel.

    Queues operations if they need to be, or runs them immediately when it can.

    Sadly we must delete provisional download folders only in the main process, using
    QFileSystemModel. Otherwise the QFileSystemModel is liable to issue a large number of
    messages like this:

    QInotifyFileSystemWatcherEngine::addPaths: inotify_add_watch failed: No such file or directory

    Yet we must generate and create folders in the offload process, because that
    can be expensive for a large number of rpd_files.

    New for PyQt 5.7: Inherits from QObject to allow for Qt signals and slots using PyQt slot
    decorator.
    """

    def __init__(self, fsmodel: FileSystemModel,
                 prefs: Preferences,
                 photoDestinationFSView: FileSystemView,
                 videoDestinationFSView: FileSystemView,
                 devices: DeviceCollection,
                 rapidApp: 'RapidWindow') -> None:
        """

        :param fsmodel: FileSystemModel powering the destination and this computer views
        :param prefs: program preferences
        :param photoDestinationFSView: photo destination view
        :param videoDestinationFSView: video destination view
        :param devices: the device collection
        :param rapidApp: main application window
        """

        super().__init__()

        self.rpd_files_queue = []  # type: List[RPDFile]
        self.clean_for_scan_id_queue = []  # type: List[int]
        self.change_destination_queued = False  # type: bool
        self.subfolder_rebuild_queued = False  # type: bool

        self.offloaded = False
        self.process_destination = False
        self.fsmodel = fsmodel
        self.prefs = prefs
        self.devices = devices
        self.rapidApp = rapidApp

        self.photoDestinationFSView = photoDestinationFSView
        self.videoDestinationFSView = videoDestinationFSView

        self.folders_preview = FoldersPreview()
        # Set the initial download destination values, using the values
        # in the program prefs:
        self._change_destination()

    def add_rpd_files(self, rpd_files: List[RPDFile]) -> None:
        """
        Generate new provisional download folders for the rpd_files, either
        by sending them off for generation to the offload process, or if some
        are already being generated, queueing the operation

        :param rpd_files: the list of rpd files
        """

        if self.offloaded:
            self.rpd_files_queue.extend(rpd_files)
        else:
            if self.rpd_files_queue:
                rpd_files = rpd_files + self.rpd_files_queue
                self.rpd_files_queue = []  # type: List[RPDFile]
            self._generate_folders(rpd_files=rpd_files)

    def _generate_folders(self, rpd_files: List[RPDFile]) -> None:
        if not self.devices.scanning or self.rapidApp.downloadIsRunning():
            logging.info("Generating provisional download folders for %s files", len(rpd_files))
        data = OffloadData(
            rpd_files=rpd_files, strip_characters=self.prefs.strip_characters,
            folders_preview=self.folders_preview
        )
        self.offloaded = True
        self.rapidApp.sendToOffload(data=data)

    def change_destination(self) -> None:
        if self.offloaded:
            self.change_destination_queued = True
        else:
            self._change_destination()
            self._update_model_and_views()

    def change_subfolder_structure(self) -> None:
        self.change_destination()
        if self.offloaded:
            assert self.change_destination_queued == True
            self.subfolder_rebuild_queued = True
        else:
            self._change_subfolder_structure()

    def _change_destination(self) -> None:
            destination = DownloadDestination(
                photo_download_folder=self.prefs.photo_download_folder,
                video_download_folder=self.prefs.video_download_folder,
                photo_subfolder=self.prefs.photo_subfolder,
                video_subfolder=self.prefs.video_subfolder
            )
            self.folders_preview.process_destination(
                destination=destination, fsmodel=self.fsmodel
            )

    def _change_subfolder_structure(self) -> None:
        rpd_files = self.rapidApp.thumbnailModel.getAllDownloadableRPDFiles()
        if rpd_files:
            self.add_rpd_files(rpd_files=rpd_files)

    @pyqtSlot(FoldersPreview)
    def folders_generated(self, folders_preview: FoldersPreview) -> None:
        """
        Receive the folders_preview from the offload process, and
        handle any tasks that may have been queued in the time it was
        being processed in the offload process

        :param folders_preview: the folders_preview as worked on by the
         offload process
        """

        logging.debug("Provisional download folders received")
        self.offloaded = False
        self.folders_preview = folders_preview

        dirty = self.folders_preview.dirty
        self.folders_preview.dirty = False
        if dirty:
            logging.debug("Provisional download folders change detected")

        if not self.rapidApp.downloadIsRunning():
            for scan_id in self.clean_for_scan_id_queue:
                dirty = True
                self._remove_provisional_folders_for_device(scan_id=scan_id)

            self.clean_for_scan_id_queue = []  # type: List[int]

            if self.change_destination_queued:
                self.change_destination_queued = False
                dirty = True
                logging.debug("Changing destination of provisional download folders")
                self._change_destination()

            if self.subfolder_rebuild_queued:
                self.subfolder_rebuild_queued = False
                logging.debug("Rebuilding provisional download folders")
                self._change_subfolder_structure()
        else:
            logging.debug(
                "Not removing or moving provisional download folders because a download is running"
            )

        if dirty:
            self._update_model_and_views()

        if self.rpd_files_queue:
            logging.debug("Assigning queued provisional download folders to be generated")
            self._generate_folders(rpd_files=self.rpd_files_queue)
            self.rpd_files_queue = []  # type: List[RPDFile]

        # self.folders_preview.dump()

    def _update_model_and_views(self):
        logging.debug("Updating file system model and views")
        self.fsmodel.preview_subfolders = self.folders_preview.preview_subfolders()
        self.fsmodel.download_subfolders = self.folders_preview.download_subfolders()
        # Update the view
        self.photoDestinationFSView.reset()
        self.videoDestinationFSView.reset()
        # Ensure the file system model caches are refreshed:
        self.fsmodel.setRootPath(self.folders_preview.photo_download_folder)
        self.fsmodel.setRootPath(self.folders_preview.video_download_folder)
        self.fsmodel.setRootPath('/')
        self.photoDestinationFSView.expandPreviewFolders(self.prefs.photo_download_folder)
        self.videoDestinationFSView.expandPreviewFolders(self.prefs.video_download_folder)

        # self.photoDestinationFSView.update()
        # self.videoDestinationFSView.update()

    def remove_folders_for_device(self, scan_id: int) -> None:
        """
        Remove provisional download folders unique to this scan_id
        using the offload process.

        :param scan_id: scan id of the device
        """

        if self.offloaded:
            self.clean_for_scan_id_queue.append(scan_id)
        else:
            self._remove_provisional_folders_for_device(scan_id=scan_id)
            self._update_model_and_views()

    def queue_folder_removal_for_device(self, scan_id: int) -> None:
        """
        Queues provisional download files for removal after
        all files have been downloaded for a device.

        :param scan_id: scan id of the device
        """

        self.clean_for_scan_id_queue.append(scan_id)

    def remove_folders_for_queued_devices(self) -> None:
        """
        Once all files have been downloaded (i.e. no more remain
        to be downloaded) and there was a disparity between
        modification times and creation times that was discovered during
        the download, clean any provisional download folders now that the
        download has finished.
        """

        for scan_id in self.clean_for_scan_id_queue:
            self._remove_provisional_folders_for_device(scan_id=scan_id)
        self.clean_for_scan_id_queue = []  # type: List[int]
        self._update_model_and_views()

    def _remove_provisional_folders_for_device(self, scan_id: int) -> None:
        if scan_id in self.devices:
            logging.info(
                "Cleaning provisional download folders for %s", self.devices[scan_id].display_name
            )
        else:
            logging.info("Cleaning provisional download folders for device %d", scan_id)
        self.folders_preview.clean_generated_folders_for_scan_id(
            scan_id=scan_id, fsmodel=self.fsmodel
        )

    def remove_preview_folders(self) -> None:
        """
        Called when application is exiting.
        """

        self.folders_preview.clean_all_generated_folders(fsmodel=self.fsmodel)


class RapidWindow(QMainWindow):
    """
    Main application window, and primary controller of program logic

    Such attributes unfortunately make it very complex.

    For better or worse, Qt's state machine technology is not used.
    State indicating whether a download or scan is occurring is
    thus kept in the device collection, self.devices
    """

    checkForNewVersionRequest = pyqtSignal()
    downloadNewVersionRequest = pyqtSignal(str, str)
    reverifyDownloadedTar = pyqtSignal(str)
    udisks2Unmount = pyqtSignal(str)

    def __init__(self, splash: 'SplashScreen',
                 fractional_scaling: str,
                 scaling_set: str,
                 scaling_action: ScalingAction,
                 scaling_detected: ScalingDetected,
                 xsetting_running: bool,
                 photo_rename: Optional[bool]=None,
                 video_rename: Optional[bool]=None,
                 auto_detect: Optional[bool]=None,
                 this_computer_source: Optional[str]=None,
                 this_computer_location: Optional[str]=None,
                 photo_download_folder: Optional[str]=None,
                 video_download_folder: Optional[str]=None,
                 backup: Optional[bool]=None,
                 backup_auto_detect: Optional[bool]=None,
                 photo_backup_identifier: Optional[str]=None,
                 video_backup_identifier: Optional[str]=None,
                 photo_backup_location: Optional[str]=None,
                 video_backup_location: Optional[str]=None,
                 ignore_other_photo_types: Optional[bool]=None,
                 thumb_cache: Optional[bool]=None,
                 auto_download_startup: Optional[bool]=None,
                 auto_download_insertion: Optional[bool]=None,
                 log_gphoto2: Optional[bool]=None) -> None:

        super().__init__()
        self.splash = splash
        if splash.isVisible():
            self.screen = splash.windowHandle().screen()  # type: QScreen
        else:
            self.screen = None

        self.fractional_scaling_message = fractional_scaling
        self.scaling_set_message = scaling_set

        # Process Qt events - in this case, possible closing of splash screen
        app.processEvents()

        # Three values to handle window position quirks under X11:
        self.window_show_requested_time = None  # type: Optional[datetime.datetime]
        self.window_move_triggered_count = 0
        self.windowPositionDelta = QPoint(0, 0)

        self.setFocusPolicy(Qt.StrongFocus)

        self.ignore_other_photo_types = ignore_other_photo_types
        self.application_state = ApplicationState.normal
        self.prompting_for_user_action = {}  # type: Dict[Device, QMessageBox]

        self.close_event_run = False

        self.file_manager, self.file_manager_type = get_default_file_manager()

        self.fileSystemUrlHandler = FileSystemUrlHandler(self.file_manager, self.file_manager_type)
        QDesktopServices.setUrlHandler("file", self.fileSystemUrlHandler, "openFileBrowser")

        for version in get_versions(
                self.file_manager, self.file_manager_type, scaling_action,
                scaling_detected, xsetting_running):
            logging.info('%s', version)

        if disable_version_check:
            logging.debug("Version checking disabled via code")

        if is_snap():
            logging.debug("Version checking disabled because running in a snap")

        if EXIFTOOL_VERSION is None:
            logging.error("ExifTool is either missing or has a problem")

        if pymedia_version_info() is None:
            if libmediainfo_missing:
                logging.error(
                    "pymediainfo is installed, but the library libmediainfo appears to be missing"
                )

        self.log_gphoto2 = log_gphoto2 == True

        self.setWindowTitle(_("Rapid Photo Downloader"))
        # app is a module level global
        self.readWindowSettings(app)
        self.prefs = Preferences()
        self.checkPrefsUpgrade()
        self.prefs.program_version = __about__.__version__

        if self.prefs.force_exiftool:
            logging.debug("ExifTool and not Exiv2 will be used to read photo metadata")

        # track devices on which there was an error setting a file's filesystem metadata
        self.copy_metadata_errors = FSMetadataErrors()
        self.backup_metadata_errors = FSMetadataErrors()

        if thumb_cache is not None:
            logging.debug("Use thumbnail cache: %s", thumb_cache)
            self.prefs.use_thumbnail_cache = thumb_cache

        self.setupWindow()

        splash.setProgress(10)

        if photo_rename is not None:
            if photo_rename:
                self.prefs.photo_rename = PHOTO_RENAME_SIMPLE
            else:
                self.prefs.photo_rename = self.prefs.rename_defaults['photo_rename']

        if video_rename is not None:
            if video_rename:
                self.prefs.video_rename = VIDEO_RENAME_SIMPLE
            else:
                self.prefs.video_rename = self.prefs.rename_defaults['video_rename']

        if auto_detect is not None:
            self.prefs.device_autodetection = auto_detect
        else:
            logging.info("Device autodetection: %s", self.prefs.device_autodetection)

        if self.prefs.device_autodetection:
            if not self.prefs.scan_specific_folders:
                logging.info("Devices do not need specific folders to be scanned")
            else:
                logging.info(
                    "For automatically detected devices, only the contents the following "
                    "folders will be scanned: %s", ', '.join(self.prefs.folders_to_scan)
                )

        if this_computer_source is not None:
            self.prefs.this_computer_source = this_computer_source

        if this_computer_location is not None:
            self.prefs.this_computer_path = this_computer_location

        if self.prefs.this_computer_source:
            if self.prefs.this_computer_path:
                logging.info(
                    "This Computer is set to be used as a download source, using: %s",
                    self.prefs.this_computer_path
                )
            else:
                logging.info(
                    "This Computer is set to be used as a download source, but the location is "
                    "not yet set"
                )
        else:
            logging.info("This Computer is not used as a download source")

        if photo_download_folder is not None:
            self.prefs.photo_download_folder = photo_download_folder
        logging.info("Photo download location: %s", self.prefs.photo_download_folder)
        if video_download_folder is not None:
            self.prefs.video_download_folder = video_download_folder
        logging.info("Video download location: %s", self.prefs.video_download_folder)

        if backup is not None:
            self.prefs.backup_files = backup
        else:
            logging.info("Backing up files: %s", self.prefs.backup_files)
            
        if backup_auto_detect is not None:
            self.prefs.backup_device_autodetection = backup_auto_detect
        elif self.prefs.backup_files:
            logging.info("Backup device auto detection: %s", self.prefs.backup_device_autodetection)
            
        if photo_backup_identifier is not None:
            self.prefs.photo_backup_identifier = photo_backup_identifier
        elif self.prefs.backup_files and self.prefs.backup_device_autodetection:
            logging.info("Photo backup identifier: %s", self.prefs.photo_backup_identifier)

        if video_backup_identifier is not None:
            self.prefs.video_backup_identifier = video_backup_identifier
        elif self.prefs.backup_files and self.prefs.backup_device_autodetection:
            logging.info("video backup identifier: %s", self.prefs.video_backup_identifier)
            
        if photo_backup_location is not None:
            self.prefs.backup_photo_location = photo_backup_location
        elif self.prefs.backup_files and not self.prefs.backup_device_autodetection:
            logging.info("Photo backup location: %s", self.prefs.backup_photo_location)

        if video_backup_location is not None:
            self.prefs.backup_video_location = video_backup_location
        elif self.prefs.backup_files and not self.prefs.backup_device_autodetection:
            logging.info("video backup location: %s", self.prefs.backup_video_location)

        if auto_download_startup is not None:
            self.prefs.auto_download_at_startup = auto_download_startup
        elif self.prefs.auto_download_at_startup:
            logging.info("Auto download at startup is on")

        if auto_download_insertion is not None:
            self.prefs.auto_download_upon_device_insertion = auto_download_insertion
        elif self.prefs.auto_download_upon_device_insertion:
            logging.info("Auto download upon device insertion is on")

        if self.prefs.list_not_empty('volume_whitelist'):
            logging.info("Whitelisted devices: %s", " ; ".join(self.prefs.volume_whitelist))

        if self.prefs.list_not_empty('volume_blacklist'):
            logging.info("Blacklisted devices: %s", " ; ".join(self.prefs.volume_blacklist))

        if self.prefs.list_not_empty('camera_blacklist'):
            logging.info("Blacklisted cameras: %s", " ; ".join(self.prefs.camera_blacklist))

        self.prefs.verify_file = False

        logging.debug("Starting main ExifTool process")
        self.exiftool_process = exiftool.ExifTool()
        self.exiftool_process.start()

        self.prefs.validate_max_CPU_cores()
        self.prefs.validate_ignore_unhandled_file_exts()

        # Don't call processEvents() after initiating 0MQ, as it can
        # cause "Interrupted system call" errors
        app.processEvents()

        self.download_paused = False

        self.startThreadControlSockets()
        self.startProcessLogger()

    def checkPrefsUpgrade(self) -> None:
        if self.prefs.program_version != __about__.__version__:
            previous_version = self.prefs.program_version
            if not len(previous_version):
                logging.debug("Initial program run detected")
            else:
                pv = pkgr.parse_version(previous_version)
                rv = pkgr.parse_version(__about__.__version__)
                if pv < rv:
                    logging.info(
                        "Version upgrade detected, from %s to %s",
                        previous_version, __about__.__version__
                    )
                    self.prefs.upgrade_prefs(pv)
                elif pv > rv:
                    logging.info(
                        "Version downgrade detected, from %s to %s",
                        previous_version, __about__.__version__
                    )
                if pv < pkgr.parse_version('0.9.7b1'):
                    # Remove any duplicate subfolder generation or file renaming custom presets
                    self.prefs.filter_duplicate_generation_prefs()

    def startThreadControlSockets(self) -> None:
        """
        Create and bind inproc sockets to communicate with threads that
        handle inter process communication via zmq.

        See 'Signaling Between Threads (PAIR Sockets)' in 'ØMQ - The Guide'
        http://zguide.zeromq.org/page:all#toc46
        """

        context = zmq.Context.instance()
        inproc = "inproc://{}"

        self.logger_controller =  context.socket(zmq.PAIR)
        self.logger_controller.bind(inproc.format(ThreadNames.logger))

        self.rename_controller = context.socket(zmq.PAIR)
        self.rename_controller.bind(inproc.format(ThreadNames.rename))

        self.scan_controller = context.socket(zmq.PAIR)
        self.scan_controller.bind(inproc.format(ThreadNames.scan))

        self.copy_controller = context.socket(zmq.PAIR)
        self.copy_controller.bind(inproc.format(ThreadNames.copy))

        self.backup_controller = context.socket(zmq.PAIR)
        self.backup_controller.bind(inproc.format(ThreadNames.backup))

        self.thumbnail_deamon_controller = context.socket(zmq.PAIR)
        self.thumbnail_deamon_controller.bind(inproc.format(ThreadNames.thumbnail_daemon))

        self.offload_controller = context.socket(zmq.PAIR)
        self.offload_controller.bind(inproc.format(ThreadNames.offload))

        self.new_version_controller = context.socket(zmq.PAIR)
        self.new_version_controller.bind(inproc.format(ThreadNames.new_version))

    def sendStopToThread(self, socket: zmq.Socket) -> None:
        socket.send_multipart(create_inproc_msg(b'STOP'))

    def sendTerminateToThread(self, socket: zmq.Socket) -> None:
        socket.send_multipart(create_inproc_msg(b'TERMINATE'))

    def sendStopWorkerToThread(self, socket: zmq.Socket, worker_id: int) -> None:
        socket.send_multipart(create_inproc_msg(b'STOP_WORKER', worker_id=worker_id))

    def sendStartToThread(self, socket: zmq.Socket) -> None:
        socket.send_multipart(create_inproc_msg(b'START'))

    def sendStartWorkerToThread(self, socket: zmq.Socket, worker_id: int, data: Any) -> None:
        socket.send_multipart(create_inproc_msg(b'START_WORKER', worker_id=worker_id, data=data))

    def sendResumeToThread(self, socket: zmq.Socket, worker_id: Optional[int]=None) -> None:
        socket.send_multipart(create_inproc_msg(b'RESUME', worker_id=worker_id))

    def sendPauseToThread(self, socket: zmq.Socket) -> None:
        socket.send_multipart(create_inproc_msg(b'PAUSE'))

    def sendDataMessageToThread(self, socket: zmq.Socket,
                                data: Any,
                                worker_id: Optional[int]=None) -> None:
        socket.send_multipart(create_inproc_msg(b'SEND_TO_WORKER', worker_id=worker_id, data=data))

    def sendToOffload(self, data: Any) -> None:
        self.offload_controller.send_multipart(
            create_inproc_msg(b'SEND_TO_WORKER', worker_id=None, data=data)
        )

    def startProcessLogger(self) -> None:
        self.loggermq = ProcessLoggingManager()
        self.loggermqThread = QThread()
        self.loggermq.moveToThread(self.loggermqThread)

        self.loggermqThread.started.connect(self.loggermq.startReceiver)
        self.loggermq.ready.connect(self.initStage2)
        logging.debug("Starting logging subscription manager...")
        QTimer.singleShot(0, self.loggermqThread.start)

    @pyqtSlot(int)
    def initStage2(self, logging_port: int) -> None:
        logging.debug("...logging subscription manager started")
        self.logging_port = logging_port

        self.splash.setProgress(20)

        logging.debug("Stage 2 initialization")

        if self.prefs.purge_thumbnails:
            cache = ThumbnailCacheSql(create_table_if_not_exists=False)
            logging.info("Purging thumbnail cache...")
            cache.purge_cache()
            logging.info("...thumbnail Cache has been purged")
            self.prefs.purge_thumbnails = False
            # Recreate the cache on the file system
            ThumbnailCacheSql(create_table_if_not_exists=True)
        elif self.prefs.optimize_thumbnail_db:
            cache = ThumbnailCacheSql(create_table_if_not_exists=True)
            logging.info("Optimizing thumbnail cache...")
            db, fs, size = cache.optimize()
            logging.info("...thumbnail cache has been optimized.")

            if db:
                logging.info("Removed %s files from thumbnail database", db)
            if fs:
                logging.info("Removed %s thumbnails from file system", fs)
            if size:
                logging.info("Thumbnail database size reduction: %s", format_size_for_user(size))

            self.prefs.optimize_thumbnail_db = False
        else:
            # Recreate the cache on the file system
            t = ThumbnailCacheSql(create_table_if_not_exists=True)

        # For meaning of 'Devices', see devices.py
        self.devices = DeviceCollection(self.exiftool_process, self)
        self.backup_devices = BackupDeviceCollection(rapidApp=self)

        logging.debug("Starting thumbnail daemon model")

        self.thumbnaildaemonmqThread = QThread()
        self.thumbnaildaemonmq = ThumbnailDaemonManager(logging_port=logging_port)
        self.thumbnaildaemonmq.moveToThread(self.thumbnaildaemonmqThread)
        self.thumbnaildaemonmqThread.started.connect(self.thumbnaildaemonmq.run_sink)
        self.thumbnaildaemonmq.message.connect(self.thumbnailReceivedFromDaemon)
        self.thumbnaildaemonmq.sinkStarted.connect(self.initStage3)

        QTimer.singleShot(0, self.thumbnaildaemonmqThread.start)

    @pyqtSlot()
    def initStage3(self) -> None:
        logging.debug("Stage 3 initialization")

        self.splash.setProgress(30)

        self.sendStartToThread(self.thumbnail_deamon_controller)
        logging.debug("...thumbnail daemon model started")

        self.thumbnailView = ThumbnailView(self)
        self.thumbnailModel = ThumbnailListModel(
            parent=self, logging_port=self.logging_port, log_gphoto2=self.log_gphoto2
        )

        self.thumbnailView.setModel(self.thumbnailModel)
        self.thumbnailView.setItemDelegate(ThumbnailDelegate(rapidApp=self))

    @pyqtSlot(int)
    def initStage4(self, frontend_port: int) -> None:
        logging.debug("Stage 4 initialization")

        self.splash.setProgress(40)

        self.sendDataMessageToThread(
            self.thumbnail_deamon_controller, worker_id=None,
            data=ThumbnailDaemonData(frontend_port=frontend_port)
        )

        centralWidget = QWidget()
        self.setCentralWidget(centralWidget)

        self.temporalProximity = TemporalProximity(rapidApp=self, prefs=self.prefs)

        # Respond to the user selecting / deslecting temporal proximity (timeline) cells:
        self.temporalProximity.proximitySelectionHasChanged.connect(
            self.updateThumbnailModelAfterProximityChange
        )
        self.temporalProximity.temporalProximityView.proximitySelectionHasChanged.connect(
            self.updateThumbnailModelAfterProximityChange
        )

        # Setup notification system
        try:
            self.have_libnotify = Notify.init(_('Rapid Photo Downloader'))
        except:
            logging.error("Notification intialization problem")
            self.have_libnotify = False

        logging.debug("Locale directory: %s", raphodo.localedir)

        # Initialise use of libgphoto2
        logging.debug("Getting gphoto2 context")
        try:
            self.gp_context = gp.Context()
        except:
            logging.critical("Error getting gphoto2 context")
            self.gp_context = None

        logging.debug("Probing for valid mounts")
        self.validMounts = ValidMounts(onlyExternalMounts=self.prefs.only_external_mounts)

        logging.debug(
            "Freedesktop.org thumbnails location: %s", get_fdo_cache_thumb_base_directory()
        )

        logging.debug("Probing desktop environment")
        desktop_env = get_desktop_environment()

        self.unity_progress = False
        self.desktop_launchers = []

        if have_unity:
            logging.info("Unity LauncherEntry API installed")
            launchers = (
                'net.damonlynch.rapid_photo_downloader.desktop',
            )
            for launcher in launchers:
                desktop_launcher = Unity.LauncherEntry.get_for_desktop_id(launcher)
                if desktop_launcher is not None:
                    self.desktop_launchers.append(desktop_launcher)
                    self.unity_progress = True

            if not self.desktop_launchers:
                logging.warning(
                    "Desktop environment is Unity Launcher API compatible, but could not "
                    "find program's .desktop file"
                )
            else:
                logging.debug(
                    "Unity progress indicator found, using %s launcher(s)",
                    len(self.desktop_launchers)
                )

        self.createPathViews()

        self.createActions()
        logging.debug("Laying out main window")
        self.createMenus()
        self.createLayoutAndButtons(centralWidget)

        logging.debug("Have GIO module: %s", have_gio)
        self.gvfsControlsMounts = gvfs_controls_mounts() and have_gio
        if have_gio:
            logging.debug("GVFS (GIO) controls mounts: %s", self.gvfsControlsMounts)

        if not self.gvfsControlsMounts:
            # Monitor when the user adds or removes a camera
            self.cameraHotplug = CameraHotplug()
            self.cameraHotplugThread = QThread()
            self.cameraHotplugThread.started.connect(self.cameraHotplug.startMonitor)
            self.cameraHotplug.moveToThread(self.cameraHotplugThread)
            self.cameraHotplug.cameraAdded.connect(self.cameraAdded)
            self.cameraHotplug.cameraRemoved.connect(self.cameraRemoved)
            # Start the monitor only on the thread it will be running on
            logging.debug("Starting camera hotplug monitor...")
            QTimer.singleShot(0, self.cameraHotplugThread.start)

            # Monitor when the user adds or removes a partition
            self.udisks2Monitor = UDisks2Monitor(self.validMounts)
            self.udisks2MonitorThread = QThread()
            self.udisks2MonitorThread.started.connect(self.udisks2Monitor.startMonitor)
            self.udisks2Unmount.connect(self.udisks2Monitor.unmount_volume)
            self.udisks2Monitor.moveToThread(self.udisks2MonitorThread)
            self.udisks2Monitor.partitionMounted.connect(self.partitionMounted)
            self.udisks2Monitor.partitionUnmounted.connect(self.partitionUmounted)
            # Start the monitor only on the thread it will be running on
            logging.debug("Starting UDisks2 monitor...")
            QTimer.singleShot(0, self.udisks2MonitorThread.start)

        if self.gvfsControlsMounts:
            # Gio.VolumeMonitor must be in the main thread, according to
            # Gnome documentation

            logging.debug("Starting GVolumeMonitor...")
            self.gvolumeMonitor = GVolumeMonitor(self.validMounts)
            logging.debug("...GVolumeMonitor started")
            self.gvolumeMonitor.cameraUnmounted.connect(self.cameraUnmounted)
            self.gvolumeMonitor.cameraMounted.connect(self.cameraMounted)
            self.gvolumeMonitor.partitionMounted.connect(self.partitionMounted)
            self.gvolumeMonitor.partitionUnmounted.connect(self.partitionUmounted)
            self.gvolumeMonitor.volumeAddedNoAutomount.connect(self.noGVFSAutoMount)
            self.gvolumeMonitor.cameraPossiblyRemoved.connect(self.cameraRemoved)
            self.gvolumeMonitor.cameraVolumeAdded.connect(self.cameraVolumeAdded)

        if version_check_disabled():
            logging.debug("Version check disabled")
        else:
            logging.debug("Starting version check")
            self.newVersion = NewVersion(self)
            self.newVersionThread = QThread()
            self.newVersionThread.started.connect(self.newVersion.start)
            self.newVersion.checkMade.connect(self.newVersionCheckMade)
            self.newVersion.bytesDownloaded.connect(self.newVersionBytesDownloaded)
            self.newVersion.fileDownloaded.connect(self.newVersionDownloaded)
            self.reverifyDownloadedTar.connect(self.newVersion.reVerifyDownload)
            self.newVersion.downloadSize.connect(self.newVersionDownloadSize)
            self.newVersion.reverified.connect(self.installNewVersion)
            self.newVersion.moveToThread(self.newVersionThread)

            QTimer.singleShot(0, self.newVersionThread.start)

            self.newVersionCheckDialog = NewVersionCheckDialog(self)
            self.newVersionCheckDialog.finished.connect(self.newVersionCheckDialogFinished)

            # if values set, indicates the latest version of the program, and the main
            # download page on the Rapid Photo Downloader website
            self.latest_version = None  # type: version_details
            self.latest_version_download_page = None  # type: str

        # Track the creation of temporary directories
        self.temp_dirs_by_scan_id = {}

        # Track the time a download commences - used in file renaming
        self.download_start_datetime = None  # type: Optional[datetime.datetime]
        # The timestamp for when a download started / resumed after a pause
        self.download_start_time = None  # type: Optional[float]

        logging.debug("Starting download tracker")
        self.download_tracker = downloadtracker.DownloadTracker()

        # Values used to display how much longer a download will take
        self.time_remaining = downloadtracker.TimeRemaining()
        self.time_check = downloadtracker.TimeCheck()

        logging.debug("Setting up download update timer")
        self.dl_update_timer = QTimer(self)
        self.dl_update_timer.setInterval(constants.DownloadUpdateMilliseconds)
        self.dl_update_timer.timeout.connect(self.displayDownloadRunningInStatusBar)

        # Offload process is used to offload work that could otherwise
        # cause this process and thus the GUI to become unresponsive
        logging.debug("Starting offload manager...")

        self.offloadThread = QThread()
        self.offloadmq = OffloadManager(logging_port=self.logging_port)
        self.offloadThread.started.connect(self.offloadmq.run_sink)
        self.offloadmq.sinkStarted.connect(self.initStage5)
        self.offloadmq.message.connect(self.proximityGroupsGenerated)
        self.offloadmq.moveToThread(self.offloadThread)

        QTimer.singleShot(0, self.offloadThread.start)


    @pyqtSlot()
    def initStage5(self) -> None:
        logging.debug("...offload manager started")
        self.sendStartToThread(self.offload_controller)

        self.splash.setProgress(50)

        self.folder_preview_manager = FolderPreviewManager(
            fsmodel=self.fileSystemModel,
            prefs=self.prefs,
            photoDestinationFSView=self.photoDestinationFSView,
            videoDestinationFSView=self.videoDestinationFSView,
            devices=self.devices,
            rapidApp=self
        )

        self.offloadmq.downloadFolders.connect(self.folder_preview_manager.folders_generated)

        self.renameThread = QThread()
        self.renamemq = RenameMoveFileManager(logging_port=self.logging_port)
        self.renameThread.started.connect(self.renamemq.run_sink)
        self.renamemq.sinkStarted.connect(self.initStage6)
        self.renamemq.message.connect(self.fileRenamedAndMoved)
        self.renamemq.sequencesUpdate.connect(self.updateSequences)
        self.renamemq.renameProblems.connect(self.addErrorLogMessage)
        self.renamemq.moveToThread(self.renameThread)

        logging.debug("Starting rename manager...")
        QTimer.singleShot(0, self.renameThread.start)

    @pyqtSlot()
    def initStage6(self) -> None:
        logging.debug("...rename manager started")

        self.splash.setProgress(60)

        self.sendStartToThread(self.rename_controller)

        # Setup the scan processes
        self.scanThread = QThread()
        self.scanmq = ScanManager(logging_port=self.logging_port)

        self.scanThread.started.connect(self.scanmq.run_sink)
        self.scanmq.sinkStarted.connect(self.initStage7)
        self.scanmq.scannedFiles.connect(self.scanFilesReceived)
        self.scanmq.deviceError.connect(self.scanErrorReceived)
        self.scanmq.deviceDetails.connect(self.scanDeviceDetailsReceived)
        self.scanmq.scanProblems.connect(self.scanProblemsReceived)
        self.scanmq.workerFinished.connect(self.scanFinished)
        self.scanmq.fatalError.connect(self.scanFatalError)
        self.scanmq.cameraRemovedDuringScan.connect(self.cameraRemovedDuringScan)

        self.scanmq.moveToThread(self.scanThread)

        logging.debug("Starting scan manager...")
        QTimer.singleShot(0, self.scanThread.start)

    @pyqtSlot()
    def initStage7(self) -> None:
        logging.debug("...scan manager started")

        self.splash.setProgress(70)

        # Setup the copyfiles process
        self.copyfilesThread = QThread()
        self.copyfilesmq = CopyFilesManager(logging_port=self.logging_port)

        self.copyfilesThread.started.connect(self.copyfilesmq.run_sink)
        self.copyfilesmq.sinkStarted.connect(self.initStage8)
        self.copyfilesmq.message.connect(self.copyfilesDownloaded)
        self.copyfilesmq.bytesDownloaded.connect(self.copyfilesBytesDownloaded)
        self.copyfilesmq.tempDirs.connect(self.tempDirsReceivedFromCopyFiles)
        self.copyfilesmq.copyProblems.connect(self.copyfilesProblems)
        self.copyfilesmq.workerFinished.connect(self.copyfilesFinished)
        self.copyfilesmq.cameraRemoved.connect(self.cameraRemovedWhileCopyingFiles)

        self.copyfilesmq.moveToThread(self.copyfilesThread)

        logging.debug("Starting copy files manager...")
        QTimer.singleShot(0, self.copyfilesThread.start)

    @pyqtSlot()
    def initStage8(self) -> None:
        logging.debug("...copy files manager started")

        self.splash.setProgress(80)

        self.backupThread = QThread()
        self.backupmq = BackupManager(logging_port=self.logging_port)

        self.backupThread.started.connect(self.backupmq.run_sink)
        self.backupmq.sinkStarted.connect(self.initStage9)
        self.backupmq.message.connect(self.fileBackedUp)
        self.backupmq.bytesBackedUp.connect(self.backupFileBytesBackedUp)
        self.backupmq.backupProblems.connect(self.backupFileProblems)

        self.backupmq.moveToThread(self.backupThread)

        logging.debug("Starting backup manager ...")
        QTimer.singleShot(0, self.backupThread.start)

    @pyqtSlot()
    def initStage9(self) -> None:
        logging.debug("...backup manager started")

        self.splash.setProgress(90)

        if self.prefs.backup_files:
            self.setupBackupDevices()
        else:
            self.download_tracker.set_no_backup_devices(0, 0)

        settings = QSettings()
        settings.beginGroup("MainWindow")

        self.proximityButton.setChecked(settings.value("proximityButtonPressed", True, bool))
        self.proximityButtonClicked()

        self.sourceButton.setChecked(settings.value("sourceButtonPressed", True, bool))
        self.sourceButtonClicked()

        # Default to displaying the destination panels if the value has never been
        # set
        index = settings.value("rightButtonPressed", 0, int)
        if index >= 0:
            try:
                button = self.rightSideButtonMapper[index]
            except ValueError:
                logging.error("Unexpected preference value for right side button")
                index = RightSideButton.destination
                button = self.rightSideButtonMapper[index]
            button.setChecked(True)
            self.setRightPanelsAndButtons(RightSideButton(index))
        else:
            # For some unknown reason, under some sessions need to explicitly set this to False,
            # or else it shows and no button is pressed.
            self.rightPanels.setVisible(False)

        settings.endGroup()

        prefs_valid, msg = self.prefs.check_prefs_for_validity()

        self.setupErrorLogWindow(settings=settings)

        self.setDownloadCapabilities()
        self.searchForCameras(on_startup=True)
        self.setupNonCameraDevices(on_startup=True)
        self.splash.setProgress(100)
        self.setupManualPath(on_startup=True)
        self.updateSourceButton()
        self.displayMessageInStatusBar()

        self.showMainWindow()

        if not EXIFTOOL_VERSION and self.prefs.warn_broken_or_missing_libraries:
            message = _(
                '<b>ExifTool has a problem</b><br><br> '
                'Rapid Photo Downloader uses ExifTool to get metadata from videos and photos. '
                'The program will run without it, but installing it is <b>highly</b> recommended.'
            )
            warning = RememberThisDialog(
                message=message,
                icon=':/rapid-photo-downloader.svg',
                remember=RememberThisMessage.do_not_warn_again_about_missing_libraries,
                parent=self,
                buttons=RememberThisButtons.ok,
                title=_('Problem with ExifTool')
            )

            warning.exec_()
            if warning.remember:
                self.prefs.warn_broken_or_missing_libraries = False

        if libmediainfo_missing and self.prefs.warn_broken_or_missing_libraries:
            message = _(
                '<b>The library libmediainfo appears to be missing</b><br><br> '
                'Rapid Photo Downloader uses libmediainfo to get the date and time a video was '
                'shot. The program will run  without it, but installing it is recommended.'
            )

            warning = RememberThisDialog(
                message=message,
                icon=':/rapid-photo-downloader.svg',
                remember=RememberThisMessage.do_not_warn_again_about_missing_libraries,
                parent=self,
                buttons=RememberThisButtons.ok,
                title=_('Problem with libmediainfo')
            )

            warning.exec_()
            if warning.remember:
                self.prefs.warn_broken_or_missing_libraries = False

        self.tip = didyouknow.DidYouKnowDialog(self.prefs, self)
        if self.prefs.did_you_know_on_startup:
            self.tip.activate()

        if not prefs_valid:
            self.notifyPrefsAreInvalid(details=msg)
        else:
            self.checkForNewVersionRequest.emit()

        logging.debug("Completed stage 9 initializing main window")

    def showMainWindow(self) -> None:
        if not self.isVisible():
            self.splash.finish(self)

            self.window_show_requested_time = datetime.datetime.now()
            self.show()
            if self.deferred_resize_and_move_until_after_show:
                self.resizeAndMoveMainWindow()

            self.errorLog.setVisible(self.errorLogAct.isChecked())

    def mapModel(self, scan_id: int) -> DeviceModel:
        """
        Map a scan_id onto Devices' or This Computer's device model.
        :param scan_id: scan id of the device
        :return: relevant device model
        """

        return self._mapModel[self.devices[scan_id].device_type]

    def mapView(self, scan_id: int) -> DeviceView:
        """
        Map a scan_id onto Devices' or This Computer's device view.
        :param scan_id: scan id of the device
        :return: relevant device view
        """

        return self._mapView[self.devices[scan_id].device_type]

    def setupErrorLogWindow(self, settings: QSettings) -> None:
        """
        Creates, moves and resizes error log window, but does not show it.
        """

        default_x = self.pos().x()
        default_y = self.pos().y()
        default_width = int(self.size().width() * 0.5)
        default_height = int(self.size().height() * 0.5)

        settings.beginGroup("ErrorLog")
        pos = settings.value("windowPosition", QPoint(default_x, default_y))
        size = settings.value("windowSize", QSize(default_width, default_height))
        visible = settings.value('visible', False, type=bool)
        settings.endGroup()

        self.errorLog = ErrorReport(rapidApp=self)
        self.errorLogAct.setChecked(visible)
        self.errorLog.move(pos)
        self.errorLog.resize(size)
        self.errorLog.finished.connect(self.setErrorLogAct)
        self.errorLog.dialogShown.connect(self.setErrorLogAct)
        self.errorLog.dialogActivated.connect(self.errorsPending.reset)
        self.errorsPending.clicked.connect(self.errorLog.activate)

    def resizeAndMoveMainWindow(self) -> None:
        """
        Load window settings from last application run, after validating they
        will fit on the screen
        """

        if self.deferred_resize_and_move_until_after_show:
            logging.debug("Resizing and moving main window after it was deferred")

            assert self.isVisible()

            self.screen = self.windowHandle().screen()  # type: QScreen

        assert self.screen is not None

        available = self.screen.availableGeometry()  # type: QRect
        display = self.screen.size()  # type: QSize

        default_width = max(960, available.width() // 2)
        default_width = min(default_width, available.width())
        default_x = display.width() - default_width
        default_height = int(available.height() * .85)
        default_y = display.height() - default_height

        logging.debug(
            "Available screen geometry: %sx%s on %sx%s display. Default window size: %sx%s.",
            available.width(), available.height(), display.width(), display.height(),
            default_width, default_height
        )

        settings = QSettings()
        settings.beginGroup("MainWindow")

        try:
            scaling = self.devicePixelRatioF()
        except AttributeError:
            scaling = self.devicePixelRatio()

        logging.info("%s", self.scaling_set_message)
        logging.info('Desktop scaling set to %s', scaling)
        logging.debug("%s", self.fractional_scaling_message)

        maximized = settings.value("maximized", False, type=bool)
        logging.debug("Window maximized when last run: %s", maximized)

        # Even if window is maximized, must restore saved window size and position for when the user
        # unmaximizes the window

        pos = settings.value("windowPosition", QPoint(default_x, default_y))
        size = settings.value("windowSize", QSize(default_width, default_height))
        settings.endGroup()

        was_valid, validatedSize = validateWindowSizeLimit(available.size(), size)
        if not was_valid:
            logging.debug(
                "Windows size %sx%s was invalid. Value was reset to %sx%s.",
                size.width(), size.height(), validatedSize.width(), validatedSize.height()
            )
        logging.debug(
            "Window size: %sx%s", validatedSize.width(), validatedSize.height()
        )
        was_valid, validatedPos = validateWindowPosition(pos, available.size(), validatedSize)
        if not was_valid:
            logging.debug("Window position %s,%s was invalid", pos.x(), pos.y())

        self.resize(validatedSize)
        self.move(validatedPos)

        if maximized:
            logging.debug("Setting window to maximized state")
            self.setWindowState(Qt.WindowMaximized)

    def readWindowSettings(self, app: 'QtSingleApplication'):
        self.deferred_resize_and_move_until_after_show = False

        # Calculate window sizes
        if self.screen is None:
            self.deferred_resize_and_move_until_after_show = True
        else:
            self.resizeAndMoveMainWindow()

    def writeWindowSettings(self):
        logging.debug("Writing window settings")
        settings = QSettings()
        settings.beginGroup("MainWindow")
        windowPos = self.pos() + self.windowPositionDelta
        if windowPos.x() < 0:
            windowPos.setX(0)
        if windowPos.y() < 0:
            windowPos.setY(0)
        settings.setValue("windowPosition", windowPos)
        settings.setValue("windowSize", self.size())
        # Alternative to position and size:
        # settings.setValue("geometry", self.saveGeometry())
        state = self.windowState()
        maximized = bool(state & Qt.WindowMaximized)
        settings.setValue("maximized", maximized)
        settings.setValue("centerSplitterSizes", self.centerSplitter.saveState())
        settings.setValue("sourceButtonPressed", self.sourceButton.isChecked())
        settings.setValue("rightButtonPressed", self.rightSideButtonPressed())
        settings.setValue("proximityButtonPressed", self.proximityButton.isChecked())
        settings.setValue("leftPanelSplitterSizes", self.leftPanelSplitter.saveState())
        settings.setValue("rightPanelSplitterSizes", self.rightPanelSplitter.saveState())
        settings.endGroup()

        settings.beginGroup("ErrorLog")
        settings.setValue("windowPosition", self.errorLog.pos())
        settings.setValue("windowSize", self.errorLog.size())
        settings.setValue('visible', self.errorLog.isVisible())
        settings.endGroup()

    def moveEvent(self, event: QMoveEvent) -> None:
        """
        Handle quirks in window positioning.

        X11 has a feature where the window managager can decorate the
        windows. A side effect of this is that the position returned by
        window.pos() can be different between restoring the position
        from the settings, and saving the position at application exit, even if
        the user never moved the window.
        """

        super().moveEvent(event)
        self.window_move_triggered_count += 1

        if self.window_show_requested_time is None:
            pass
            # self.windowPositionDelta = QPoint(0, 0)
        elif self.window_move_triggered_count == 2:
            if (datetime.datetime.now() - self.window_show_requested_time).total_seconds() < 1.0:
                self.windowPositionDelta = event.oldPos() - self.pos()
                logging.debug("Window position quirk delta: %s", self.windowPositionDelta)
            self.window_show_requested_time = None

    def setupWindow(self) -> None:
        status = self.statusBar()
        status.setStyleSheet("QStatusBar::item { border: 0px solid black }; ")
        self.downloadProgressBar = QProgressBar()
        self.downloadProgressBar.setMaximumWidth(QFontMetrics(QFont()).height() * 9)
        self.errorsPending = SpeechBubble(self)
        self.errorsPending.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        status.addPermanentWidget(self.errorsPending)
        status.addPermanentWidget(self.downloadProgressBar, 1)

    def anyFilesSelected(self) -> bool:
        """
        :return: True if any files are selected
        """

        return self.thumbnailView.selectionModel().hasSelection()

    def applyJobCode(self, job_code: str) -> None:
        """
        Apply job code to all selected photos/videos.

        :param job_code: job code to apply
        """

        delegate = self.thumbnailView.itemDelegate()  # type: ThumbnailDelegate
        delegate.applyJobCode(job_code=job_code)

    @pyqtSlot(bool, version_details, version_details, str, bool, bool, bool)
    def newVersionCheckMade(self, success: bool,
                            stable_version: version_details,
                            dev_version: version_details,
                            download_page: str,
                            no_upgrade: bool,
                            pip_install: bool,
                            is_venv: bool) -> None:
        """
        Respond to a version check, either initiated at program startup, or from the
        application's main menu.

        If the check was initiated at program startup, then the new version dialog box
        will not be showing.

        :param success: whether the version check was successful or not
        :param stable_version: latest stable version
        :param dev_version: latest development version
        :param download_page: url of the download page on the Rapid
         Photo Downloader website
        :param no_upgrade: if True, don't offer to do an inplace upgrade
        :param pip_install: whether pip was used to install this
         program version
        :param is_venv: whether the program is running in a python virtual
         environment
        """

        if success:
            self.latest_version = None
            current_version = pkgr.parse_version(__about__.__version__)

            check_dev_version = (current_version.is_prerelease or
                                 self.prefs.include_development_release)

            if current_version < stable_version.version:
                self.latest_version = stable_version

            if check_dev_version and (
                current_version < dev_version.version or
                current_version < stable_version.version
                ):
                if dev_version.version > stable_version.version:
                    self.latest_version = dev_version
                else:
                    self.latest_version = stable_version

            if (
                    self.latest_version is not None and str(self.latest_version.version) not in
                    self.prefs.ignore_versions):

                version = str(self.latest_version.version)
                changelog_url = self.latest_version.changelog_url

                if pip_install:
                    logging.debug("Installation performed via pip")
                    if is_venv:
                        logging.info(
                            "Cannot use in-program update to upgrade program from within virtual "
                            "environment"
                        )
                        state = CheckNewVersionDialogState.open_website
                    elif no_upgrade:
                        logging.info("Cannot perform in-place upgrade to this version")
                        state = CheckNewVersionDialogState.open_website
                    else:
                        download_page = None
                        state = CheckNewVersionDialogState.prompt_for_download
                else:
                    logging.debug("Installation not performed via pip")
                    state = CheckNewVersionDialogState.open_website

                self.latest_version_download_page = download_page

                self.newVersionCheckDialog.displayUserMessage(
                    new_state=state,
                    version=version,
                    download_page=download_page,
                    changelog_url=changelog_url
                )
                if not self.newVersionCheckDialog.isVisible():
                    self.newVersionCheckDialog.show()

            elif self.newVersionCheckDialog.isVisible():
                self.newVersionCheckDialog.displayUserMessage(
                    CheckNewVersionDialogState.have_latest_version)

        elif self.newVersionCheckDialog.isVisible():
            # Failed to reach update server
            self.newVersionCheckDialog.displayUserMessage(
                CheckNewVersionDialogState.failed_to_contact)

    @pyqtSlot(int)
    def newVersionCheckDialogFinished(self, result: int) -> None:
        current_state = self.newVersionCheckDialog.current_state
        if current_state in (
                CheckNewVersionDialogState.prompt_for_download,
                CheckNewVersionDialogState.open_website):
            if self.newVersionCheckDialog.dialog_detailed_result == \
                    CheckNewVersionDialogResult.skip:
                version = str(self.latest_version.version)
                logging.info(
                    "Adding version %s to the list of program versions to ignore", version
                )
                self.prefs.add_list_value(key='ignore_versions', value=version)
            elif self.newVersionCheckDialog.dialog_detailed_result == \
                    CheckNewVersionDialogResult.open_website:
                webbrowser.open_new_tab(self.latest_version_download_page)
            elif self.newVersionCheckDialog.dialog_detailed_result == \
                    CheckNewVersionDialogResult.download:
                url = self.latest_version.url
                md5 = self.latest_version.md5
                self.downloadNewVersionRequest.emit(url, md5)
                self.downloadNewVersionDialog = DownloadNewVersionDialog(parent=self)
                self.downloadNewVersionDialog.rejected.connect(self.newVersionDownloadCancelled)
                self.downloadNewVersionDialog.show()

    @pyqtSlot('PyQt_PyObject')
    def newVersionBytesDownloaded(self, bytes_downloaded: int) -> None:
        if self.downloadNewVersionDialog.isVisible():
            self.downloadNewVersionDialog.updateProgress(bytes_downloaded)

    @pyqtSlot('PyQt_PyObject')
    def newVersionDownloadSize(self, download_size: int) -> None:
        if self.downloadNewVersionDialog.isVisible():
            self.downloadNewVersionDialog.setDownloadSize(download_size)

    @pyqtSlot(str, bool)
    def newVersionDownloaded(self, path: str, download_cancelled: bool) -> None:
        self.downloadNewVersionDialog.accept()
        if not path and not download_cancelled:
            msgBox = QMessageBox(parent=self)
            msgBox.setIcon(QMessageBox.Warning)
            msgBox.setWindowTitle(_("Download failed"))
            msgBox.setText(
                _('Sorry, the download of the new version of Rapid Photo Downloader failed.')
            )
            msgBox.exec_()
        elif path:
            logging.info("New program version downloaded to %s", path)

            message = _(
                'The new version was successfully downloaded. Do you want to '
                'close Rapid Photo Downloader and install it now?'
            )
            msgBox = QMessageBox(parent=self)
            msgBox.setWindowTitle(_('Update Rapid Photo Downloader'))
            msgBox.setText(message)
            msgBox.setIcon(QMessageBox.Question)
            msgBox.setStandardButtons(QMessageBox.Cancel)
            installButton = msgBox.addButton(_('Install'), QMessageBox.AcceptRole)
            msgBox.setDefaultButton(installButton)
            if msgBox.exec_() == QMessageBox.AcceptRole:
                self.reverifyDownloadedTar.emit(path)
            else:
                # extract the install.py script and move it to the correct location
                # for testing:
                # path = '/home/damon/rapid090a7/dist/rapid-photo-downloader-0.9.0a7.tar.gz'
                extract_file_from_tar(full_tar_path=path, member_filename='install.py')
                installer_dir = os.path.dirname(path)
                if self.file_manager:
                    uri = pathname2url(path)
                    cmd = '{} {}'.format(self.file_manager, uri)
                    logging.debug("Launching: %s", cmd)
                    args = shlex.split(cmd)
                    subprocess.Popen(args)
                else:
                    msgBox = QMessageBox(parent=self)
                    msgBox.setWindowTitle(_('New version saved'))
                    message = _(
                        'The tar file and installer script are saved at:\n\n %s'
                    ) % installer_dir
                    msgBox.setText(message)
                    msgBox.setIcon(QMessageBox.Information)
                    msgBox.exec_()

    @pyqtSlot(bool, str)
    def installNewVersion(self, reverified: bool, full_tar_path: str) -> None:
        """
        Launch script to install new version of Rapid Photo Downloader
        via upgrade.py.
        :param reverified: whether file has been reverified or not
        :param full_tar_path: path to the tarball
        """
        if not reverified:
            msgBox = QMessageBox(parent=self)
            msgBox.setIcon(QMessageBox.Warning)
            msgBox.setWindowTitle(_("Upgrade failed"))
            msgBox.setText(
                _(
                    'Sorry, upgrading Rapid Photo Downloader failed because there was '
                    'an error opening the installer.'
                )
            )
            msgBox.exec_()
        else:
            # for testing:
            # full_tar_path = '/home/damon/rapid090a7/dist/rapid-photo-downloader-0.9.0a7.tar.gz'
            upgrade_py = 'upgrade.py'
            installer_dir = os.path.dirname(full_tar_path)
            if extract_file_from_tar(full_tar_path, upgrade_py):
                upgrade_script = os.path.join(installer_dir, upgrade_py)
                cmd = shlex.split('{} {} {}'.format(sys.executable, upgrade_script, full_tar_path))
                subprocess.Popen(cmd)
                self.quit()

    @pyqtSlot()
    def newVersionDownloadCancelled(self) -> None:
        logging.info("Download of new program version cancelled")
        self.new_version_controller.send(b'STOP')

    def updateProgressBarState(self, thumbnail_generated: bool=None) -> None:
        """
        Updates the state of the ProgessBar in the main window's lower right corner.

        If any device is downloading, the progress bar displays
        download progress.

        Else, if any device is thumbnailing, the progress bar
        displays thumbnailing progress.

        Else, if any device is scanning, the progress bar shows a busy status.

        Else, the progress bar is set to an idle status.
        """

        if self.downloadIsRunning():
            logging.debug("Setting progress bar to show download progress")
            self.downloadProgressBar.setMaximum(100)
            return

        if self.unity_progress:
            for launcher in self.desktop_launchers:
                launcher.set_property('progress_visible', False)

        if len(self.devices.thumbnailing):
            if self.downloadProgressBar.maximum() != self.thumbnailModel.total_thumbs_to_generate:
                logging.debug(
                    "Setting progress bar maximum to %s",
                    self.thumbnailModel.total_thumbs_to_generate
                )
                self.downloadProgressBar.setMaximum(self.thumbnailModel.total_thumbs_to_generate)
            if thumbnail_generated:
                self.downloadProgressBar.setValue(self.thumbnailModel.thumbnails_generated)
        elif len(self.devices.scanning):
            logging.debug("Setting progress bar to show scanning activity")
            self.downloadProgressBar.setMaximum(0)
        else:
            logging.debug("Resetting progress bar")
            self.downloadProgressBar.reset()
            self.downloadProgressBar.setMaximum(100)

    def updateSourceButton(self) -> None:
        text, icon = self.devices.get_main_window_display_name_and_icon()
        self.sourceButton.setText(addPushButtonLabelSpacer(text))
        self.sourceButton.setIcon(icon)

    def setLeftPanelVisibility(self) -> None:
        self.leftPanelSplitter.setVisible(
            self.sourceButton.isChecked() or self.proximityButton.isChecked()
        )

    def setRightPanelsAndButtons(self, buttonPressed: RightSideButton) -> None:
        """
        Set visibility of right panel based on which right bar buttons
        is pressed, and ensure only one button is pressed at any one time.

        Cannot use exclusive QButtonGroup because with that, one button needs to be
        pressed. We allow no button to be pressed.
        """

        widget = self.rightSideButtonMapper[buttonPressed]  # type: RotatedButton

        if widget.isChecked():
            self.rightPanels.setVisible(True)
            for button in RightSideButton:
                if button == buttonPressed:
                    self.rightPanels.setCurrentIndex(buttonPressed.value)
                else:
                    self.rightSideButtonMapper[button].setChecked(False)
        else:
            self.rightPanels.setVisible(False)

    def rightSideButtonPressed(self) -> int:
        """
        Determine which right side button is currently pressed, if any.
        :return: -1 if no button is pressed, else the index into
         RightSideButton
        """

        for button in RightSideButton:
            widget = self.rightSideButtonMapper[button]
            if widget.isChecked():
                return int(button.value)
        return -1

    @pyqtSlot()
    def sourceButtonClicked(self) -> None:
        self.deviceToggleView.setVisible(self.sourceButton.isChecked())
        self.thisComputerToggleView.setVisible(self.sourceButton.isChecked())
        self.setLeftPanelVisibility()

    @pyqtSlot()
    def destinationButtonClicked(self) -> None:
        self.setRightPanelsAndButtons(RightSideButton.destination)

    @pyqtSlot()
    def renameButtonClicked(self) -> None:
        self.setRightPanelsAndButtons(RightSideButton.rename)

    @pyqtSlot()
    def backupButtonClicked(self) -> None:
        self.setRightPanelsAndButtons(RightSideButton.backup)

    @pyqtSlot()
    def jobcodButtonClicked(self) -> None:
        self.jobCodePanel.updateDefaultMessage()
        self.setRightPanelsAndButtons(RightSideButton.jobcode)

    @pyqtSlot()
    def proximityButtonClicked(self) -> None:
        self.temporalProximity.setVisible(self.proximityButton.isChecked())
        self.setLeftPanelVisibility()
        self.adjustLeftPanelSliderHandles()

    def adjustLeftPanelSliderHandles(self):
        """
        Move left panel splitter handles in response to devices / this computer
        changes.
        """

        preferred_devices_height = self.deviceToggleView.minimumHeight()
        min_this_computer_height = self.thisComputerToggleView.minimumHeight()

        if self.thisComputerToggleView.on():
            this_computer_height = max(
                min_this_computer_height, self.centerSplitter.height() - preferred_devices_height
            )
        else:
            this_computer_height = min_this_computer_height

        if self.proximityButton.isChecked():
            if not self.thisComputerToggleView.on():
                proximity_height = (
                    self.centerSplitter.height() - this_computer_height - preferred_devices_height
                )
            else:
                proximity_height = this_computer_height // 2
                this_computer_height = this_computer_height // 2
        else:
            proximity_height = 0
        self.leftPanelSplitter.setSizes(
            [preferred_devices_height, this_computer_height, proximity_height]
        )

    @pyqtSlot(int)
    def showComboChanged(self, index: int) -> None:
        self.sortComboChanged(index=-1)
        self.thumbnailModel.updateAllDeviceDisplayCheckMarks()

    def showOnlyNewFiles(self) -> bool:
        """
        User can use combo switch to show only so-called "hew" files, i.e. files that
        have not been previously downloaded.

        :return: True if only new files are shown
        """
        return self.showCombo.currentData() == Show.new_only

    @pyqtSlot(int)
    def sortComboChanged(self, index: int) -> None:
        sort = self.sortCombo.currentData()
        order = self.sortOrder.currentData()
        show = self.showCombo.currentData()
        self.thumbnailModel.setFileSort(sort=sort, order=order, show=show)

    @pyqtSlot(int)
    def sortOrderChanged(self, index: int) -> None:
        self.sortComboChanged(index=-1)

    @pyqtSlot(int)
    def selectAllPhotosCheckboxChanged(self, state: int) -> None:
        select_all = state == Qt.Checked
        self.thumbnailModel.selectAll(select_all=select_all, file_type=FileType.photo)

    @pyqtSlot(int)
    def selectAllVideosCheckboxChanged(self, state: int) -> None:
        select_all = state == Qt.Checked
        self.thumbnailModel.selectAll(select_all=select_all, file_type=FileType.video)

    @pyqtSlot()
    def setErrorLogAct(self) -> None:
        self.errorLogAct.setChecked(self.errorLog.isVisible())

    def createActions(self) -> None:
        self.downloadAct = QAction(
            _("Download"), self, shortcut="Ctrl+Return", triggered=self.doDownloadAction
        )

        self.refreshAct = QAction(
            _("&Refresh..."), self, shortcut="Ctrl+R", triggered=self.doRefreshAction
        )

        self.preferencesAct = QAction(
            _("&Preferences"), self, shortcut="Ctrl+P", triggered=self.doPreferencesAction
        )

        self.quitAct = QAction(
            _("&Quit"), self, shortcut="Ctrl+Q", triggered=self.close
        )

        self.errorLogAct = QAction(
            _("Error &Reports"), self, enabled=True, checkable=True, triggered=self.doErrorLogAction
        )

        self.clearDownloadsAct = QAction(
            _("Clear Completed Downloads"), self, triggered=self.doClearDownloadsAction
        )

        self.helpAct = QAction(
            _("Get Help Online..."), self, shortcut="F1", triggered=self.doHelpAction
        )

        self.didYouKnowAct = QAction(
            _("&Tip of the Day..."), self, triggered=self.doDidYouKnowAction
        )

        self.reportProblemAct = QAction(
            _("Report a Problem..."), self, triggered=self.doReportProblemAction
        )

        self.makeDonationAct = QAction(
            _("Make a Donation..."), self, triggered=self.doMakeDonationAction
        )

        self.translateApplicationAct = QAction(
            _("Translate this Application..."), self, triggered=self.doTranslateApplicationAction
        )

        self.aboutAct = QAction(
            _("&About..."), self, triggered=self.doAboutAction
        )

        self.newVersionAct = QAction(
            _("Check for Updates..."), self, triggered=self.doCheckForNewVersion
        )

    def createLayoutAndButtons(self, centralWidget) -> None:
        """
        Create widgets used to display the GUI.
        :param centralWidget: the widget in which to layout the new widgets
        """

        settings = QSettings()
        settings.beginGroup("MainWindow")

        verticalLayout = QVBoxLayout()
        verticalLayout.setContentsMargins(0, 0, 0, 0)
        centralWidget.setLayout(verticalLayout)
        self.standard_spacing = verticalLayout.spacing()

        self.topBar = self.createTopBar()
        verticalLayout.addLayout(self.topBar)

        centralLayout = QHBoxLayout()
        centralLayout.setContentsMargins(0, 0, 0, 0)

        self.leftBar = self.createLeftBar()
        self.rightBar = self.createRightBar()

        self.createCenterPanels()
        self.createDeviceThisComputerViews()
        self.createDestinationViews()
        self.createRenamePanels()
        self.createJobCodePanel()
        self.createBackupPanel()
        self.configureCenterPanels(settings)
        self.createBottomControls()

        centralLayout.addLayout(self.leftBar)
        centralLayout.addWidget(self.centerSplitter)
        centralLayout.addLayout(self.rightBar)

        verticalLayout.addLayout(centralLayout)
        verticalLayout.addWidget(self.thumbnailControl)

    def createTopBar(self) -> QHBoxLayout:
        topBar = QHBoxLayout()
        menu_margin = int(QFontMetrics(QFont()).height() / 3)
        topBar.setContentsMargins(0, 0, menu_margin, 0)

        topBar.setSpacing(int(QFontMetrics(QFont()).height() / 2))

        self.sourceButton = TopPushButton(
            addPushButtonLabelSpacer(_('Select Source')),
            parent=self, extra_top=self.standard_spacing
        )
        self.sourceButton.clicked.connect(self.sourceButtonClicked)

        vlayout = QVBoxLayout()
        vlayout.setContentsMargins(0, 0, 0, 0)
        vlayout.setSpacing(0)
        vlayout.addSpacing(self.standard_spacing)
        hlayout = QHBoxLayout()
        hlayout.setContentsMargins(0, 0, 0, 0)
        hlayout.setSpacing(menu_margin)
        vlayout.addLayout(hlayout)

        self.downloadButton = DownloadButton(self.downloadAct.text(), parent=self)
        self.downloadButton.addAction(self.downloadAct)
        self.downloadButton.setDefault(True)
        self.downloadButton.clicked.connect(self.downloadButtonClicked)

        self.menuButton.setIconSize(
            QSize(self.sourceButton.top_row_icon_size, self.sourceButton.top_row_icon_size)
        )

        topBar.addWidget(self.sourceButton)
        topBar.addStretch()
        topBar.addLayout(vlayout)
        hlayout.addWidget(self.downloadButton)
        hlayout.addWidget(self.menuButton)
        return topBar

    def createLeftBar(self) -> QVBoxLayout:
        leftBar = QVBoxLayout()
        leftBar.setContentsMargins(0, 0, 0, 0)

        self.proximityButton = RotatedButton(_('Timeline'), RotatedButton.leftSide)
        self.proximityButton.clicked.connect(self.proximityButtonClicked)
        leftBar.addWidget(self.proximityButton)
        leftBar.addStretch()
        return leftBar

    def createRightBar(self) -> QVBoxLayout:
        rightBar = QVBoxLayout()
        rightBar.setContentsMargins(0, 0, 0, 0)

        self.destinationButton = RotatedButton(_('Destination'), RotatedButton.rightSide)
        self.renameButton = RotatedButton(_('Rename'), RotatedButton.rightSide)
        self.jobcodeButton = RotatedButton(_('Job Code'), RotatedButton.rightSide)
        self.backupButton = RotatedButton(_('Back Up'), RotatedButton.rightSide)

        self.destinationButton.clicked.connect(self.destinationButtonClicked)
        self.renameButton.clicked.connect(self.renameButtonClicked)
        self.jobcodeButton.clicked.connect(self.jobcodButtonClicked)
        self.backupButton.clicked.connect(self.backupButtonClicked)

        self.rightSideButtonMapper = {
            RightSideButton.destination: self.destinationButton,
            RightSideButton.rename: self.renameButton,
            RightSideButton.jobcode: self.jobcodeButton,
            RightSideButton.backup: self.backupButton
        }

        rightBar.addWidget(self.destinationButton)
        rightBar.addWidget(self.renameButton)
        rightBar.addWidget(self.jobcodeButton)
        rightBar.addWidget(self.backupButton)
        rightBar.addStretch()
        return rightBar

    def createPathViews(self) -> None:
        self.deviceView = DeviceView(rapidApp=self)
        self.deviceModel = DeviceModel(self, "Devices")
        self.deviceView.setModel(self.deviceModel)
        self.deviceView.setItemDelegate(DeviceDelegate(rapidApp=self))

        # This computer is any local path
        self.thisComputerView = DeviceView(rapidApp=self)
        self.thisComputerModel = DeviceModel(self, "This Computer")
        self.thisComputerView.setModel(self.thisComputerModel)
        self.thisComputerView.setItemDelegate(DeviceDelegate(self))

        # Map different device types onto their appropriate view and model
        self._mapModel = {
            DeviceType.path: self.thisComputerModel,
            DeviceType.camera: self.deviceModel,
            DeviceType.volume: self.deviceModel
        }
        self._mapView = {
            DeviceType.path: self.thisComputerView,
            DeviceType.camera: self.deviceView,
            DeviceType.volume: self.deviceView
        }

        # Be cautious: validate paths. The settings file can alwasy be edited by hand, and
        # the user can set it to whatever value they want using the command line options.
        logging.debug("Checking path validity")
        this_computer_sf = validate_source_folder(self.prefs.this_computer_path)
        if this_computer_sf.valid:
            if this_computer_sf.absolute_path != self.prefs.this_computer_path:
                self.prefs.this_computer_path = this_computer_sf.absolute_path
        elif self.prefs.this_computer_source and self.prefs.this_computer_path != '':
            logging.warning(
                "Ignoring invalid 'This Computer' path: %s", self.prefs.this_computer_path
            )
            self.prefs.this_computer_path = ''

        photo_df = validate_download_folder(self.prefs.photo_download_folder)
        if photo_df.valid:
            if photo_df.absolute_path != self.prefs.photo_download_folder:
                self.prefs.photo_download_folder = photo_df.absolute_path
        else:
            if self.prefs.photo_download_folder:
                logging.error(
                    "Ignoring invalid Photo Destination path: %s", self.prefs.photo_download_folder
                )
            self.prefs.photo_download_folder = ''

        video_df = validate_download_folder(self.prefs.video_download_folder)
        if video_df.valid:
            if video_df.absolute_path != self.prefs.video_download_folder:
                self.prefs.video_download_folder = video_df.absolute_path
        else:
            if self.prefs.video_download_folder:
                logging.error(
                    "Ignoring invalid Video Destination path: %s", self.prefs.video_download_folder
                )
            self.prefs.video_download_folder = ''

        self.watchedDownloadDirs = WatchDownloadDirs()
        self.watchedDownloadDirs.updateWatchPathsFromPrefs(self.prefs)
        self.watchedDownloadDirs.directoryChanged.connect(self.watchedFolderChange)

        self.fileSystemModel = FileSystemModel(parent=self)
        self.fileSystemFilter = FileSystemFilter(self)
        self.fileSystemFilter.setSourceModel(self.fileSystemModel)
        self.fileSystemDelegate = FileSystemDelegate()

        index = self.fileSystemFilter.mapFromSource(self.fileSystemModel.index('/'))

        self.thisComputerFSView = FileSystemView(model=self.fileSystemModel, rapidApp=self)
        self.thisComputerFSView.setModel(self.fileSystemFilter)
        self.thisComputerFSView.setItemDelegate(self.fileSystemDelegate)
        self.thisComputerFSView.hideColumns()
        self.thisComputerFSView.setRootIndex(index)
        if this_computer_sf.valid:
            self.thisComputerFSView.goToPath(self.prefs.this_computer_path)
        self.thisComputerFSView.activated.connect(self.thisComputerPathChosen)
        self.thisComputerFSView.clicked.connect(self.thisComputerPathChosen)

        self.photoDestinationFSView = FileSystemView(model=self.fileSystemModel, rapidApp=self)
        self.photoDestinationFSView.setModel(self.fileSystemFilter)
        self.photoDestinationFSView.setItemDelegate(self.fileSystemDelegate)
        self.photoDestinationFSView.hideColumns()
        self.photoDestinationFSView.setRootIndex(index)
        if photo_df.valid:
            self.photoDestinationFSView.goToPath(self.prefs.photo_download_folder)
        self.photoDestinationFSView.activated.connect(self.photoDestinationPathChosen)
        self.photoDestinationFSView.clicked.connect(self.photoDestinationPathChosen)

        self.videoDestinationFSView = FileSystemView(model=self.fileSystemModel, rapidApp=self)
        self.videoDestinationFSView.setModel(self.fileSystemFilter)
        self.videoDestinationFSView.setItemDelegate(self.fileSystemDelegate)
        self.videoDestinationFSView.hideColumns()
        self.videoDestinationFSView.setRootIndex(index)
        if video_df.valid:
            self.videoDestinationFSView.goToPath(self.prefs.video_download_folder)
        self.videoDestinationFSView.activated.connect(self.videoDestinationPathChosen)
        self.videoDestinationFSView.clicked.connect(self.videoDestinationPathChosen)

    def createDeviceThisComputerViews(self) -> None:

        # Devices Header and View
        tip = _('Turn on or off the use of devices attached to this computer as download sources')
        self.deviceToggleView = QToggleView(
            label=_('Devices'),
            display_alternate=True,
            toggleToolTip=tip,
            headerColor=QColor(ThumbnailBackgroundName),
            headerFontColor=QColor(Qt.white),
            on=self.prefs.device_autodetection
        )
        self.deviceToggleView.addWidget(self.deviceView)
        self.deviceToggleView.valueChanged.connect(self.deviceToggleViewValueChange)
        self.deviceToggleView.setSizePolicy(
            QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding
        )

        # This Computer Header and View

        tip = _('Turn on or off the use of a folder on this computer as a download source')
        self.thisComputerToggleView = QToggleView(
            label=_('This Computer'),
            display_alternate=True,
            toggleToolTip=tip,
            headerColor=QColor(ThumbnailBackgroundName),
            headerFontColor=QColor(Qt.white),
            on=bool(self.prefs.this_computer_source)
        )
        self.thisComputerToggleView.valueChanged.connect(self.thisComputerToggleValueChanged)

        self.thisComputer = ComputerWidget(
            objectName='thisComputer',
            view=self.thisComputerView,
            fileSystemView=self.thisComputerFSView,
            select_text=_('Select a source folder')
        )
        if self.prefs.this_computer_source:
            self.thisComputer.setViewVisible(self.prefs.this_computer_source)

        self.thisComputerToggleView.addWidget(self.thisComputer)

    def createDestinationViews(self) -> None:
        """
        Create the widgets that let the user choose where to download photos and videos to,
        and that show them how much storage space there is available for their files.
        """

        self.photoDestination = QPanelView(
            label=_('Photos'),
            headerColor=QColor(ThumbnailBackgroundName),
            headerFontColor=QColor(Qt.white)
        )
        self.videoDestination = QPanelView(
            label=_('Videos'),
            headerColor=QColor(ThumbnailBackgroundName),
            headerFontColor=QColor(Qt.white)
        )

        # Display storage space when photos and videos are being downloaded to the same
        # partition

        self.combinedDestinationDisplay = DestinationDisplay(parent=self)
        self.combinedDestinationDisplayContainer = QPanelView(
            _('Projected Storage Use'),
            headerColor=QColor(ThumbnailBackgroundName),
            headerFontColor=QColor(Qt.white)
        )
        self.combinedDestinationDisplayContainer.addWidget(self.combinedDestinationDisplay)

        # Display storage space when photos and videos are being downloaded to different
        # partitions.
        # Also display the file system folder chooser for both destinations.

        self.photoDestinationDisplay = DestinationDisplay(
            menu=True, file_type=FileType.photo, parent=self
        )
        self.photoDestinationDisplay.setDestination(self.prefs.photo_download_folder)
        self.photoDestinationWidget = ComputerWidget(
            objectName='photoDestination',
            view=self.photoDestinationDisplay,
            fileSystemView=self.photoDestinationFSView,
            select_text=_('Select a destination folder')
        )
        self.photoDestination.addWidget(self.photoDestinationWidget)
        
        self.videoDestinationDisplay = DestinationDisplay(
            menu=True, file_type=FileType.video, parent=self
        )
        self.videoDestinationDisplay.setDestination(self.prefs.video_download_folder)
        self.videoDestinationWidget = ComputerWidget(
            objectName='videoDestination',
            view=self.videoDestinationDisplay,
            fileSystemView=self.videoDestinationFSView,
            select_text=_('Select a destination folder')
        )
        self.videoDestination.addWidget(self.videoDestinationWidget)

        self.photoDestinationContainer = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.photoDestinationContainer.setLayout(layout)
        layout.addWidget(self.combinedDestinationDisplayContainer)
        layout.addWidget(self.photoDestination)

    def createRenamePanels(self) -> None:
        """
        Create the file renaming panel
        """

        self.renamePanel = RenamePanel(parent=self)

    def createJobCodePanel(self) -> None:
        """
        Create the job code panel
        """

        self.jobCodePanel = JobCodePanel(parent=self)

    def createBackupPanel(self) -> None:
        """
        Create the backup options panel
        """

        self.backupPanel = BackupPanel(parent=self)

    def createBottomControls(self) -> None:
        self.thumbnailControl = QWidget()
        layout = QHBoxLayout()

        # left and right align at edge of left & right bar
        hmargin = self.proximityButton.sizeHint().width()
        hmargin += self.standard_spacing
        vmargin = int(QFontMetrics(QFont()).height() / 2 )

        layout.setContentsMargins(hmargin, vmargin, hmargin, vmargin)
        layout.setSpacing(self.standard_spacing)
        self.thumbnailControl.setLayout(layout)

        font = self.font()  # type: QFont
        font.setPointSize(font.pointSize() - 2)

        self.showCombo = ChevronCombo()
        self.showCombo.addItem(_('All'), Show.all)
        self.showCombo.addItem(_('New'), Show.new_only)
        self.showCombo.currentIndexChanged.connect(self.showComboChanged)
        self.showLabel = self.showCombo.makeLabel(_("Show:"))

        self.sortCombo = ChevronCombo()
        self.sortCombo.addItem(_("Modification Time"), Sort.modification_time)
        self.sortCombo.addItem(_("Checked State"), Sort.checked_state)
        self.sortCombo.addItem(_("Filename"), Sort.filename)
        self.sortCombo.addItem(_("Extension"), Sort.extension)
        self.sortCombo.addItem(_("File Type"), Sort.file_type)
        self.sortCombo.addItem(_("Device"), Sort.device)
        self.sortCombo.currentIndexChanged.connect(self.sortComboChanged)
        self.sortLabel= self.sortCombo.makeLabel(_("Sort:"))

        self.sortOrder = ChevronCombo()
        self.sortOrder.addItem(_("Ascending"), Qt.AscendingOrder)
        self.sortOrder.addItem(_("Descending"), Qt.DescendingOrder)
        self.sortOrder.currentIndexChanged.connect(self.sortOrderChanged)

        for widget in (
                self.showLabel, self.sortLabel, self.sortCombo, self.showCombo, self.sortOrder):
            widget.setFont(font)

        self.checkAllLabel = QLabel(_('Select All:'))

        # Remove the border when the widget is highlighted
        style = """
        QCheckBox {
            border: none;
            outline: none;
            spacing: %(spacing)d;
        }
        """ % dict(spacing=self.standard_spacing // 2)
        self.selectAllPhotosCheckbox = QCheckBox(_("Photos") + " ")
        self.selectAllVideosCheckbox = QCheckBox(_("Videos"))
        self.selectAllPhotosCheckbox.setStyleSheet(style)
        self.selectAllVideosCheckbox.setStyleSheet(style)

        for widget in (self.checkAllLabel, self.selectAllPhotosCheckbox,
                       self.selectAllVideosCheckbox):
            widget.setFont(font)

        self.selectAllPhotosCheckbox.stateChanged.connect(self.selectAllPhotosCheckboxChanged)
        self.selectAllVideosCheckbox.stateChanged.connect(self.selectAllVideosCheckboxChanged)

        layout.addWidget(self.showLabel)
        layout.addWidget(self.showCombo)
        layout.addSpacing(QFontMetrics(QFont()).height() * 2)
        layout.addWidget(self.sortLabel)
        layout.addWidget(self.sortCombo)
        layout.addWidget(self.sortOrder)
        layout.addStretch()
        layout.addWidget(self.checkAllLabel)
        layout.addWidget(self.selectAllPhotosCheckbox)
        layout.addWidget(self.selectAllVideosCheckbox)

    def createCenterPanels(self) -> None:
        self.centerSplitter = QSplitter()
        self.centerSplitter.setOrientation(Qt.Horizontal)
        self.leftPanelSplitter = QSplitter()
        self.leftPanelSplitter.setOrientation(Qt.Vertical)
        self.rightPanelSplitter = QSplitter()
        self.rightPanelSplitter.setOrientation(Qt.Vertical)
        self.rightPanels = QStackedWidget()

    def configureCenterPanels(self, settings: QSettings) -> None:
        self.leftPanelSplitter.addWidget(self.deviceToggleView)
        self.leftPanelSplitter.addWidget(self.thisComputerToggleView)
        self.leftPanelSplitter.addWidget(self.temporalProximity)

        self.rightPanelSplitter.addWidget(self.photoDestinationContainer)
        self.rightPanelSplitter.addWidget(self.videoDestination)

        self.leftPanelSplitter.setCollapsible(0, False)
        self.leftPanelSplitter.setCollapsible(1, False)
        self.leftPanelSplitter.setCollapsible(2, False)
        self.leftPanelSplitter.setStretchFactor(0, 0)
        self.leftPanelSplitter.setStretchFactor(1, 1)
        self.leftPanelSplitter.setStretchFactor(2, 1)

        self.rightPanels.addWidget(self.rightPanelSplitter)
        self.rightPanels.addWidget(self.renamePanel)
        self.rightPanels.addWidget(self.jobCodePanel)
        self.rightPanels.addWidget(self.backupPanel)

        self.centerSplitter.addWidget(self.leftPanelSplitter)
        self.centerSplitter.addWidget(self.thumbnailView)
        self.centerSplitter.addWidget(self.rightPanels)
        self.centerSplitter.setStretchFactor(0, 0)
        self.centerSplitter.setStretchFactor(1, 2)
        self.centerSplitter.setStretchFactor(2, 0)
        self.centerSplitter.setCollapsible(0, False)
        self.centerSplitter.setCollapsible(1, False)
        self.centerSplitter.setCollapsible(2, False)

        self.rightPanelSplitter.setCollapsible(0, False)
        self.rightPanelSplitter.setCollapsible(1, False)

        splitterSetting = settings.value("centerSplitterSizes")
        if splitterSetting is not None:
            self.centerSplitter.restoreState(splitterSetting)
        else:
            self.centerSplitter.setSizes([200, 400, 200])

        splitterSetting = settings.value("leftPanelSplitterSizes")
        if splitterSetting is not None:
            self.leftPanelSplitter.restoreState(splitterSetting)
        else:
            self.leftPanelSplitter.setSizes([200, 200, 400])

        splitterSetting = settings.value("rightPanelSplitterSizes")
        if splitterSetting is not None:
            self.rightPanelSplitter.restoreState(splitterSetting)
        else:
            self.rightPanelSplitter.setSizes([200,200])

    def setDownloadCapabilities(self) -> bool:
        """
        Update the destination displays and download button

        :return: True if download destinations are capable of having
        all marked files downloaded to them
        """
        marked_summary = self.thumbnailModel.getMarkedSummary()
        if self.prefs.backup_files:
            downloading_to = self.backup_devices.get_download_backup_device_overlap(
                photo_download_folder=self.prefs.photo_download_folder,
                video_download_folder=self.prefs.video_download_folder
            )
            self.backupPanel.setDownloadingTo(downloading_to=downloading_to)
            backups_good = self.updateBackupView(marked_summary=marked_summary)
        else:
            backups_good = True
            downloading_to = defaultdict(set)

        destinations_good = self.updateDestinationViews(
            marked_summary=marked_summary, downloading_to=downloading_to
        )

        download_good = destinations_good and backups_good
        self.setDownloadActionState(download_good)
        self.destinationButton.setHighlighted(not destinations_good)
        self.backupButton.setHighlighted(not backups_good)
        return download_good

    def updateDestinationViews(self,
            marked_summary: MarkedSummary,
            downloading_to: Optional[DefaultDict[int, Set[FileType]]]=None) -> bool:
        """
        Updates the the header bar and storage space view for the
        photo and video download destinations.

        :return True if destinations required for the download exist,
         and there is sufficient space on them, else False.
        """

        size_photos_marked = marked_summary.size_photos_marked
        size_videos_marked = marked_summary.size_videos_marked
        marked = marked_summary.marked

        if self.unity_progress:
            available = self.thumbnailModel.getNoFilesMarkedForDownload()
            for launcher in self.desktop_launchers:
                if available:
                    launcher.set_property("count", available)
                    launcher.set_property("count_visible", True)
                else:
                    launcher.set_property("count_visible", False)

        destinations_good = True

        # Assume that invalid destination folders have already been reset to ''
        if self.prefs.photo_download_folder and self.prefs.video_download_folder:
            same_dev = same_device(self.prefs.photo_download_folder,
                                   self.prefs.video_download_folder)
        else:
            same_dev = False

        merge = self.downloadIsRunning()

        if same_dev:
            files_to_display = DisplayingFilesOfType.photos_and_videos
            self.combinedDestinationDisplay.downloading_to = downloading_to
            self.combinedDestinationDisplay.setDestination(self.prefs.photo_download_folder)
            self.combinedDestinationDisplay.setDownloadAttributes(
                marked=marked,
                photos_size=size_photos_marked,
                videos_size=size_videos_marked,
                files_to_display=files_to_display,
                display_type=DestinationDisplayType.usage_only,
                merge=merge
            )
            display_type = DestinationDisplayType.folder_only
            self.combinedDestinationDisplayContainer.setVisible(True)
            destinations_good = self.combinedDestinationDisplay.sufficientSpaceAvailable()
        else:
            files_to_display = DisplayingFilesOfType.photos
            display_type = DestinationDisplayType.folders_and_usage
            self.combinedDestinationDisplayContainer.setVisible(False)

        if self.prefs.photo_download_folder:
            self.photoDestinationDisplay.downloading_to = downloading_to
            self.photoDestinationDisplay.setDownloadAttributes(
                marked=marked,
                photos_size=size_photos_marked,
                videos_size=0,
                files_to_display=files_to_display,
                display_type=display_type,
                merge=merge
            )
            self.photoDestinationWidget.setViewVisible(True)
            if display_type == DestinationDisplayType.folders_and_usage:
                destinations_good = self.photoDestinationDisplay.sufficientSpaceAvailable()
        else:
            # Photo download folder was invalid or simply not yet set
            self.photoDestinationWidget.setViewVisible(False)
            if size_photos_marked:
                destinations_good = False

        if not same_dev:
            files_to_display = DisplayingFilesOfType.videos
        if self.prefs.video_download_folder:
            self.videoDestinationDisplay.downloading_to = downloading_to
            self.videoDestinationDisplay.setDownloadAttributes(
                marked=marked,
                photos_size=0,
                videos_size=size_videos_marked,
                files_to_display=files_to_display,
                display_type=display_type,
                merge=merge
            )
            self.videoDestinationWidget.setViewVisible(True)
            if display_type == DestinationDisplayType.folders_and_usage:
                destinations_good = (
                    self.videoDestinationDisplay.sufficientSpaceAvailable() and destinations_good
                )
        else:
            # Video download folder was invalid or simply not yet set
            self.videoDestinationWidget.setViewVisible(False)
            if size_videos_marked:
                destinations_good = False

        return destinations_good

    @pyqtSlot()
    def updateThumbnailModelAfterProximityChange(self) -> None:
        """
        Respond to the user selecting / deslecting temporal proximity
        cells
        """

        self.thumbnailModel.updateAllDeviceDisplayCheckMarks()
        self.thumbnailModel.updateSelectionAfterProximityChange()
        self.thumbnailModel.resetHighlighting()

    def updateBackupView(self, marked_summary: MarkedSummary) -> bool:
        merge = self.downloadIsRunning()
        self.backupPanel.setDownloadAttributes(
            marked=marked_summary.marked,
            photos_size=marked_summary.size_photos_marked,
            videos_size=marked_summary.size_videos_marked,
            merge=merge
        )
        return self.backupPanel.sufficientSpaceAvailable()

    def setDownloadActionState(self, download_destinations_good: bool) -> None:
        """
        Sets sensitivity of Download action to enable or disable it.
        Affects download button and menu item.

        :param download_destinations_good: whether the download destinations
        are valid and contain sufficient space for the download to proceed
        """

        if not self.downloadIsRunning():
            files_marked = False
            # Don't enable starting a download while devices are being scanned
            if len(self.devices.scanning) == 0:
                files_marked = self.thumbnailModel.filesAreMarkedForDownload()

            enabled = files_marked and download_destinations_good

            self.downloadAct.setEnabled(enabled)
            self.downloadButton.setEnabled(enabled)
            if files_marked:
                marked = self.thumbnailModel.getNoFilesAndTypesMarkedForDownload()
                files = marked.file_types_present_details()
                # Translators: %(variable)s represents Python code, not a plural of the term
                # variable. You must keep the %(variable)s untranslated, or the program will
                # crash.
                text = _("Download %(files)s") % dict(files=files)  # type: str
                self.downloadButton.setText(text)
            else:
                self.downloadButton.setText(self.downloadAct.text())
        else:
            self.downloadAct.setEnabled(True)
            self.downloadButton.setEnabled(True)

    def setDownloadActionLabel(self) -> None:
        """
        Sets download action and download button text to correct value, depending on
        whether a download is occurring or not, including whether it is paused
        """

        if self.devices.downloading:
            if self.download_paused:
                text = _("Resume Download")
            else:
                text = _("Pause")
        else:
            text = _("Download")

        self.downloadAct.setText(text)
        self.downloadButton.setText(text)

    def createMenus(self) -> None:
        self.menu = QMenu()
        self.menu.addAction(self.downloadAct)
        self.menu.addAction(self.preferencesAct)
        self.menu.addSeparator()
        self.menu.addAction(self.errorLogAct)
        self.menu.addAction(self.clearDownloadsAct)
        self.menu.addSeparator()
        self.menu.addAction(self.helpAct)
        self.menu.addAction(self.didYouKnowAct)
        if not version_check_disabled():
            self.menu.addAction(self.newVersionAct)
        self.menu.addAction(self.reportProblemAct)
        self.menu.addAction(self.makeDonationAct)
        self.menu.addAction(self.translateApplicationAct)
        self.menu.addAction(self.aboutAct)
        self.menu.addAction(self.quitAct)

        self.menuButton = MenuButton(icon=':/icons/menu.svg', menu=self.menu)

    def doCheckForNewVersion(self) -> None:
        """Check online for a new program version"""
        if not version_check_disabled():
            self.newVersionCheckDialog.reset()
            self.newVersionCheckDialog.show()
            self.checkForNewVersionRequest.emit()

    def doSourceAction(self) -> None:
        self.sourceButton.animateClick()

    def doDownloadAction(self) -> None:
        self.downloadButton.animateClick()

    def doRefreshAction(self) -> None:
        pass

    def doPreferencesAction(self) -> None:
        self.scan_all_again = self.scan_non_camera_devices_again = False
        self.search_for_devices_again = False

        dialog = PreferencesDialog(prefs=self.prefs, parent=self)
        dialog.exec()
        self.prefs.sync()

        if self.scan_all_again or self.scan_non_camera_devices_again:
            self.rescanDevicesAndComputer(
                ignore_cameras=not self.scan_all_again,
                rescan_path=self.scan_all_again
            )

        if self.search_for_devices_again:
            # Update the list of valid mounts
            logging.debug(
                "Updating the list of valid mounts after preference change to only_external_mounts"
            )
            self.validMounts = ValidMounts(onlyExternalMounts=self.prefs.only_external_mounts)
            self.searchForDevicesAgain()

        # Just to be extra safe, reset these values to their 'off' state:
        self.scan_all_again = self.scan_non_camera_devices_again = False
        self.search_for_devices_again = False

    def doErrorLogAction(self) -> None:
        self.errorLog.setVisible(self.errorLogAct.isChecked())

    def doClearDownloadsAction(self):
        self.thumbnailModel.clearCompletedDownloads()

    def doHelpAction(self) -> None:
        webbrowser.open_new_tab("http://www.damonlynch.net/rapid/help.html")

    def doDidYouKnowAction(self) -> None:
        try:
            self.tip.activate()
        except AttributeError:
            self.tip = didyouknow.DidYouKnowDialog(self.prefs, self)
            self.tip.activate()

    def makeProblemReportDialog(self, header: str, title: Optional[str]=None) -> None:
        """
        Create the dialog window to guide the user in reporting a bug
        :param header: text at the top of the dialog window
        :param title: optional title
        """

        body = excepthook.please_report_problem_body.format(
            website='https://bugs.launchpad.net/rapid'
        )

        message = '{header}<br><br>{body}'.format(header=header, body=body)

        errorbox = standardMessageBox(
            message=message, rich_text=True, title=title,
            standardButtons=QMessageBox.Save | QMessageBox.Cancel,
            defaultButton=QMessageBox.Save
        )
        if errorbox.exec_() == QMessageBox.Save:
            excepthook.save_bug_report_tar(
                config_file=self.prefs.settings_path(),
                full_log_file_path=iplogging.full_log_file_path()
            )

    def doReportProblemAction(self) -> None:
        header = _('Thank you for reporting a problem in Rapid Photo Downloader')
        header = '<b>{}</b>'.format(header)
        self.makeProblemReportDialog(header)

    def doMakeDonationAction(self) -> None:
        webbrowser.open_new_tab("http://www.damonlynch.net/rapid/donate.html")

    def doTranslateApplicationAction(self) -> None:
        webbrowser.open_new_tab("http://www.damonlynch.net/rapid/translate.html")

    def doAboutAction(self) -> None:
        about = AboutDialog(self)
        about.exec()

    @pyqtSlot(bool)
    def thisComputerToggleValueChanged(self, on: bool) -> None:
        """
        Respond to This Computer Toggle Switch

        :param on: whether switch is on or off
        """

        if on:
            self.thisComputer.setViewVisible(bool(self.prefs.this_computer_path))
        self.prefs.this_computer_source = on
        if not on:
            if len(self.devices.this_computer) > 0:
                scan_id = list(self.devices.this_computer)[0]
                self.removeDevice(scan_id=scan_id)
            self.prefs.this_computer_path = ''
            self.thisComputerFSView.clearSelection()

        self.adjustLeftPanelSliderHandles()

    @pyqtSlot(bool)
    def deviceToggleViewValueChange(self, on: bool) -> None:
        """
        Respond to Devices Toggle Switch

        :param on: whether switch is on or off
        """

        self.prefs.device_autodetection = on
        if not on:
            for scan_id in list(self.devices.volumes_and_cameras):
                self.removeDevice(scan_id=scan_id, adjust_temporal_proximity=False)
            state = self.proximityStatePostDeviceRemoval()
            if state == TemporalProximityState.empty:
                self.temporalProximity.setState(TemporalProximityState.empty)
            else:
                self.generateTemporalProximityTableData("devices were removed as a download source")
        else:
            # This is a real hack -- but I don't know a better way to let the
            # slider redraw itself
            QTimer.singleShot(100, self.devicesViewToggledOn)
        self.adjustLeftPanelSliderHandles()

    def proximityStatePostDeviceRemoval(self) -> TemporalProximityState:
        """
        :return: set correct proximity state after a device is removed
        """

        # ignore devices that are scanning - we don't care about them, because the scan
        # could take a long time, especially with phones
        if len(self.devices) - len(self.devices.scanning) > 0:
            # Other already scanned devices are present
            return TemporalProximityState.regenerate
        else:
            return TemporalProximityState.empty

    @pyqtSlot()
    def devicesViewToggledOn(self) -> None:
        self.searchForCameras()
        self.setupNonCameraDevices()

    @pyqtSlot(QModelIndex)
    def thisComputerPathChosen(self, index: QModelIndex) -> None:
        """
        Handle user selecting new device location path.

        Called after single click or folder being activated.

        :param index: cell clicked
        """

        path = self.fileSystemModel.filePath(index.model().mapToSource(index))

        if self.downloadIsRunning() and self.prefs.this_computer_path:
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            # Translators: please do not change HTML codes like <br>, <i>, </i>, or <b>, </b> etc.
            message = _(
                "<b>Changing This Computer source path</b><br><br>Do you really want to "
                "change the source path to %(new_path)s?<br><br>You are currently "
                "downloading from %(source_path)s.<br><br>"
                "If you do change the path, the current download from This Computer "
                "will be cancelled."
            ) % dict(
                new_path=make_html_path_non_breaking(path),
                source_path=make_html_path_non_breaking(self.prefs.this_computer_path)
            )

            msgbox = standardMessageBox(
                message=message, rich_text=True, standardButtons=QMessageBox.Yes | QMessageBox.No,
            )
            if msgbox.exec() == QMessageBox.No:
                self.thisComputerFSView.goToPath(self.prefs.this_computer_path)
                return

        if path != self.prefs.this_computer_path:
            if self.prefs.this_computer_path:
                scan_id = self.devices.scan_id_from_path(
                    self.prefs.this_computer_path, DeviceType.path
                )
                if scan_id is not None:
                    logging.debug(
                        "Removing path from device view %s", self.prefs.this_computer_path
                    )
                    self.removeDevice(scan_id=scan_id)
            self.prefs.this_computer_path = path
            self.thisComputer.setViewVisible(True)
            self.setupManualPath()

    @pyqtSlot(QModelIndex)
    def photoDestinationPathChosen(self, index: QModelIndex) -> None:
        """
        Handle user setting new photo download location

        Called after single click or folder being activated.

        :param index: cell clicked
        """

        path = self.fileSystemModel.filePath(index.model().mapToSource(index))

        if not self.checkChosenDownloadDestination(path, FileType.photo):
            return

        if validate_download_folder(path).valid:
            if path != self.prefs.photo_download_folder:
                self.prefs.photo_download_folder = path
                self.watchedDownloadDirs.updateWatchPathsFromPrefs(self.prefs)
                self.folder_preview_manager.change_destination()
                self.photoDestinationDisplay.setDestination(path=path)
                self.setDownloadCapabilities()
        else:
            logging.error("Invalid photo download destination chosen: %s", path)
            self.handleInvalidDownloadDestination(file_type=FileType.photo)

    def checkChosenDownloadDestination(self, path: str, file_type: FileType) -> bool:
        """
        Check the path the user has chosen to ensure it's not a provisional
        download subfolder. If it is a download subfolder that already existed,
        confirm with the user that they did in fact want to use that destination.

        :param path: path chosen
        :param file_type: whether for photos or videos
        :return: False if the path is problematic and should be ignored, else True
        """

        problematic = self.downloadIsRunning()
        if problematic:
            message = _("You cannot change the download destination while downloading.")
            msgbox = standardMessageBox(
                message=message, rich_text=False, standardButtons=QMessageBox.Ok,
                iconType=QMessageBox.Warning
            )
            msgbox.exec()

        else:
            problematic = path in self.fileSystemModel.preview_subfolders

        if not problematic and path in self.fileSystemModel.download_subfolders:
            message = _(
                "<b>Confirm Download Destination</b><br><br>Are you sure you want to set "
                "the %(file_type)s download destination to %(path)s?"
            ) % dict(
                file_type=file_type.name, path=make_html_path_non_breaking(path)
            )
            msgbox = standardMessageBox(
                message=message, rich_text=True,
                standardButtons=QMessageBox.Yes | QMessageBox.No,
            )
            problematic = msgbox.exec() == QMessageBox.No

        if problematic:
            if file_type == FileType.photo and self.prefs.photo_download_folder:
                self.photoDestinationFSView.goToPath(self.prefs.photo_download_folder)
            elif file_type == FileType.video and self.prefs.video_download_folder:
                self.videoDestinationFSView.goToPath(self.prefs.video_download_folder)
            return False

        return True

    def handleInvalidDownloadDestination(self, file_type: FileType, do_update: bool=True) -> None:
        """
        Handle cases where user clicked on an invalid download directory,
        or the directory simply having disappeared

        :param file_type: type of destination to work on
        :param do_update: if True, update watched folders, provisional
         download folders and update the UI to reflect new download
         capabilities
        """

        if file_type == FileType.photo:
            self.prefs.photo_download_folder = ''
            self.photoDestinationWidget.setViewVisible(False)
        else:
            self.prefs.video_download_folder = ''
            self.videoDestinationWidget.setViewVisible(False)

        if do_update:
            self.watchedDownloadDirs.updateWatchPathsFromPrefs(self.prefs)
            self.folder_preview_manager.change_destination()
            self.setDownloadCapabilities()

    @pyqtSlot(QModelIndex)
    def videoDestinationPathChosen(self, index: QModelIndex) -> None:
        """
        Handle user setting new video download location

        Called after single click or folder being activated.

        :param index: cell clicked
        """

        path = self.fileSystemModel.filePath(index.model().mapToSource(index))

        if not self.checkChosenDownloadDestination(path, FileType.video):
            return

        if validate_download_folder(path).valid:
            if path != self.prefs.video_download_folder:
                self.prefs.video_download_folder = path
                self.watchedDownloadDirs.updateWatchPathsFromPrefs(self.prefs)
                self.folder_preview_manager.change_destination()
                self.videoDestinationDisplay.setDestination(path=path)
                self.setDownloadCapabilities()
        else:
            logging.error("Invalid video download destination chosen: %s", path)
            self.handleInvalidDownloadDestination(file_type=FileType.video)

    @pyqtSlot()
    def downloadButtonClicked(self) -> None:
        if self.download_paused:
            logging.debug("Download resumed")
            self.resumeDownload()
        else:
            if self.downloadIsRunning():
                self.pauseDownload()
            else:
                start_download = True
                if self.prefs.warn_downloading_all and \
                        self.thumbnailModel.anyCheckedFilesFiltered():
                    message = _(
                        """
<b>Downloading all files</b><br><br>
A download always includes all files that are checked for download,
including those that are not currently displayed because the Timeline
is being used or because only new files are being shown.<br><br>
Do you want to proceed with the download?
                        """
                    )

                    warning = RememberThisDialog(
                        message=message,
                        icon=':/rapid-photo-downloader.svg',
                        remember=RememberThisMessage.do_not_ask_again,
                        parent=self
                    )

                    start_download = warning.exec_()
                    if warning.remember:
                        self.prefs.warn_downloading_all = False

                if start_download:
                    logging.debug("Download activated")

                    if self.jobCodePanel.needToPromptForJobCode():
                        if self.jobCodePanel.getJobCodeBeforeDownload():
                            self.startDownload()
                    else:
                        self.startDownload()

    def pauseDownload(self) -> None:
        """
        Pause the copy files processes
        """

        self.dl_update_timer.stop()
        self.download_paused = True
        self.sendPauseToThread(self.copy_controller)
        self.setDownloadActionLabel()
        self.time_check.pause()
        self.displayMessageInStatusBar()

    def resumeDownload(self) -> None:
        """
        Resume a download after it has been paused, and start
        downloading from any queued auto-start downloads
        """

        for scan_id in self.devices.downloading:
            self.time_remaining.set_time_mark(scan_id)

        self.time_check.set_download_mark()
        self.sendResumeToThread(self.copy_controller)
        self.download_paused = False
        self.dl_update_timer.start()
        self.download_start_time = time.time()
        self.setDownloadActionLabel()
        self.immediatelyDisplayDownloadRunningInStatusBar()
        for scan_id in self.devices.queued_to_download:
            self.startDownload(scan_id=scan_id)
        self.devices.queued_to_download = set()  # type: Set[int]

    def downloadIsRunning(self) -> bool:
        """
        :return True if a file is currently being downloaded, renamed
        or backed up, else False
        """
        if not self.devices.downloading:
            if self.prefs.backup_files:
                return not self.download_tracker.all_files_backed_up()
            else:
                return False
        else:
            return True

    def startDownload(self, scan_id: int=None) -> None:
        """
        Start download, renaming and backup of files.

        :param scan_id: if specified, only files matching it will be
        downloaded
        """
        logging.debug("Start Download phase 1 has started")

        if self.prefs.backup_files:
            self.initializeBackupThumbCache()

        self.download_files = self.thumbnailModel.getFilesMarkedForDownload(scan_id)

        # model, port
        camera_unmounts_called = set()  # type: Set[Tuple[str, str]]
        stop_thumbnailing_cmd_issued = False

        stop_thumbnailing = [scan_id for scan_id in self.download_files.camera_access_needed
                             if scan_id in self.devices.thumbnailing]
        for scan_id in stop_thumbnailing:
            device = self.devices[scan_id]
            if scan_id not in self.thumbnailModel.generating_thumbnails:
                logging.debug(
                    "Not terminating thumbnailing of %s because it's not in the thumbnail manager",
                    device.display_name
                )
            else:
                logging.debug(
                    "Terminating thumbnailing for %s because a download is starting",
                    device.display_name
                )
                self.thumbnailModel.terminateThumbnailGeneration(scan_id)
                self.devices.cameras_to_stop_thumbnailing.add(scan_id)
                stop_thumbnailing_cmd_issued = True

        if self.gvfsControlsMounts:
            mount_points = {}
            # If a device was being thumbnailed, then it wasn't mounted by GVFS
            # Therefore filter out the cameras we've already requested their
            # thumbnailing be stopped
            still_to_check = [
                scan_id for scan_id in self.download_files.camera_access_needed
                if scan_id not in stop_thumbnailing
            ]
            for scan_id in still_to_check:
                # This next value is likely *always* True, but check nonetheless
                if self.download_files.camera_access_needed[scan_id]:
                    device = self.devices[scan_id]
                    model = device.camera_model
                    port = device.camera_port
                    mount_point = self.gvolumeMonitor.ptpCameraMountPoint(model, port)
                    if mount_point is not None:
                        self.devices.cameras_to_gvfs_unmount_for_download.add(scan_id)
                        camera_unmounts_called.add((model, port))
                        mount_points[(model, port)] = mount_point
            if len(camera_unmounts_called):
                logging.info(
                    "%s camera(s) need to be unmounted by GVFS before the download begins",
                    len(camera_unmounts_called)
                )
                for model, port in camera_unmounts_called:
                    self.gvolumeMonitor.unmountCamera(
                        model, port, download_starting=True, mount_point=mount_points[(model, port)]
                    )

        if not camera_unmounts_called and not stop_thumbnailing_cmd_issued:
            self.startDownloadPhase2()

    def startDownloadPhase2(self) -> None:
        logging.debug("Start Download phase 2 has started")
        download_files = self.download_files

        invalid_dirs = self.invalidDownloadFolders(download_files.download_types)

        if invalid_dirs:
            if len(invalid_dirs) > 1:
                # Translators: %(variable)s represents Python code, not a plural of the term
                # variable. You must keep the %(variable)s untranslated, or the program will
                # crash.
                msg = _(
                    "These download folders are invalid:\n%(folder1)s\n%(folder2)s"
                ) % {'folder1': invalid_dirs[0], 'folder2': invalid_dirs[1]}
            else:
                msg = _("This download folder is invalid:\n%s") % invalid_dirs[0]
            msgBox = QMessageBox(self)
            msgBox.setIcon(QMessageBox.Critical)
            msgBox.setWindowTitle(_("Download Failure"))
            msgBox.setText(_("The download cannot proceed."))
            msgBox.setInformativeText(msg)
            msgBox.exec()
        else:
            missing_destinations = self.backup_devices.backup_destinations_missing(
                download_files.download_types
            )
            if missing_destinations is not None:
                # Warn user that they have specified that they want to
                # backup a file type, but no such folder exists on backup
                # devices
                if self.prefs.backup_device_autodetection:
                    if missing_destinations == BackupFailureType.photos_and_videos:
                        logging.warning(
                            "Photos and videos will not be backed up because there "
                            "is nowhere to back them up"
                        )
                        msg = _(
                            "Photos and videos will not be backed up because there is nowhere "
                            "to back them up. Do you still want to start the download?"
                        )
                    elif missing_destinations == BackupFailureType.photos:
                        logging.warning("No backup device exists for backing up photos")
                        # Translators: filetype will be replaced with 'photos' or 'videos'
                        # Translators: %(variable)s represents Python code, not a plural of the term
                        # variable. You must keep the %(variable)s untranslated, or the program will
                        # crash.
                        msg = _(
                            "No backup device exists for backing up %(filetype)s. Do you "
                            "still want to start the download?"
                        ) % {'filetype': _('photos')}

                    else:
                        logging.warning(
                            "No backup device contains a valid folder for backing up videos"
                        )
                        # Translators: filetype will be replaced with 'photos' or 'videos'
                        # Translators: %(variable)s represents Python code, not a plural of the term
                        # variable. You must keep the %(variable)s untranslated, or the program will
                        # crash.
                        msg = _(
                            "No backup device exists for backing up %(filetype)s. Do you "
                            "still want to start the download?"
                        ) % {'filetype': _('videos')}
                else:
                    if missing_destinations == BackupFailureType.photos_and_videos:
                        logging.warning(
                            "The manually specified photo and videos backup paths do "
                            "not exist or are not writable"
                        )
                        # Translators: please do not change HTML codes like <br>, <i>, </i>, or
                        # <b>, </b> etc.
                        msg = _(
                            "<b>The photo and video backup destinations do not exist or cannot "
                            "be written to.</b><br><br>Do you still want to start the download?"
                        )
                    elif missing_destinations == BackupFailureType.photos:
                        logging.warning(
                            "The manually specified photo backup path does not exist "
                            "or is not writable"
                        )
                        # Translators: filetype will be replaced by either 'photo' or 'video'
                        # Translators: %(variable)s represents Python code, not a plural of the term
                        # variable. You must keep the %(variable)s untranslated, or the program will
                        # crash.
                        # Translators: please do not change HTML codes like <br>, <i>, </i>, or
                        # <b>, </b> etc.
                        msg = _(
                            "<b>The %(filetype)s backup destination does not exist or cannot be "
                                "written to.</b><br><br>Do you still want to start the download?"
                        ) % {'filetype': _('photo')}
                    else:
                        logging.warning(
                            "The manually specified video backup path does not exist "
                            "or is not writable"
                        )
                        # Translators: filetype will be replaced by either 'photo' or 'video'
                        # Translators: %(variable)s represents Python code, not a plural of the term
                        # variable. You must keep the %(variable)s untranslated, or the program will
                        # crash.
                        # Translators: please do not change HTML codes like <br>, <i>, </i>, or
                        # <b>, </b> etc.
                        msg = _(
                            "<b>The %(filetype)s backup destination does not exist or cannot be "
                                "written to.</b><br><br>Do you still want to start the download?"
                        )  % {'filetype': _('video')}

                if self.prefs.warn_backup_problem:
                    warning = RememberThisDialog(
                        message=msg,
                        icon=':/rapid-photo-downloader.svg',
                        remember=RememberThisMessage.do_not_ask_again,
                        parent=self,
                        title=_("Backup problem")
                    )
                    do_download = warning.exec()
                    if warning.remember:
                        self.prefs.warn_backup_problem = False
                    if not do_download:
                        return

            # Set time download is starting if it is not already set
            # it is unset when all downloads are completed
            # It is used in file renaming
            if self.download_start_datetime is None:
                self.download_start_datetime = datetime.datetime.now()
            # The download start time (not datetime) is used to determine
            # when to show the time remaining and download speed in the status bar
            if self.download_start_time is None:
                self.download_start_time = time.time()

            # Set status to download pending
            self.thumbnailModel.markDownloadPending(download_files.files)

            # disable refresh and the changing of various preferences while
            # the download is occurring
            self.enablePrefsAndRefresh(enabled=False)

            # notify renameandmovefile process to read any necessary values
            # from the program preferences
            data = RenameAndMoveFileData(message=RenameAndMoveStatus.download_started)
            self.sendDataMessageToThread(self.rename_controller, data=data)

            # notify backup processes to reset their problem reports
            self.sendBackupStartFinishMessageToWorkers(BackupStatus.backup_started)

            # Maximum value of progress bar may have been set to the number
            # of thumbnails being generated. Reset it to use a percentage.
            self.downloadProgressBar.setMaximum(100)

            for scan_id in download_files.files:
                files = download_files.files[scan_id]
                # if generating thumbnails for this scan_id, stop it
                if self.thumbnailModel.terminateThumbnailGeneration(scan_id):
                    generate_thumbnails = self.thumbnailModel.markThumbnailsNeeded(files)
                else:
                    generate_thumbnails = False

                self.downloadFiles(
                    files=files,
                    scan_id=scan_id,
                    download_stats=download_files.download_stats[scan_id],
                    generate_thumbnails=generate_thumbnails
                )

            self.setDownloadActionLabel()

    def downloadFiles(self, files: List[RPDFile],
                      scan_id: int,
                      download_stats: DownloadStats,
                      generate_thumbnails: bool) -> None:
        """

        :param files: list of the files to download
        :param scan_id: the device from which to download the files
        :param download_stats: count of files and their size
        :param generate_thumbnails: whether thumbnails must be
        generated in the copy files process.
        """

        model = self.mapModel(scan_id)
        model.setSpinnerState(scan_id, DeviceState.downloading)

        if download_stats.no_photos > 0:
            photo_download_folder = self.prefs.photo_download_folder
        else:
            photo_download_folder = None

        if download_stats.no_videos > 0:
            video_download_folder = self.prefs.video_download_folder
        else:
            video_download_folder = None

        self.download_tracker.init_stats(scan_id=scan_id, stats=download_stats)
        download_size = download_stats.photos_size_in_bytes + \
                        download_stats.videos_size_in_bytes

        if self.prefs.backup_files:
            download_size += (
                (
                    len(self.backup_devices.photo_backup_devices) *
                    download_stats.photos_size_in_bytes
                ) + (
                    len(self.backup_devices.video_backup_devices) *
                    download_stats.videos_size_in_bytes
                )
            )

        self.time_remaining[scan_id] = download_size
        self.time_check.set_download_mark()

        self.devices.set_device_state(scan_id, DeviceState.downloading)
        self.updateProgressBarState()
        self.immediatelyDisplayDownloadRunningInStatusBar()
        self.setDownloadActionState(True)

        if not self.dl_update_timer.isActive():
            self.dl_update_timer.start()

        if self.autoStart(scan_id) and self.prefs.generate_thumbnails:
            for rpd_file in files:
                rpd_file.generate_thumbnail = True
            generate_thumbnails = True

        verify_file = self.prefs.verify_file

        # Initiate copy files process

        device = self.devices[scan_id]
        copyfiles_args = CopyFilesArguments(
            scan_id=scan_id,
            device=device,
            photo_download_folder=photo_download_folder,
            video_download_folder=video_download_folder,
            files=files,
            verify_file=verify_file,
            generate_thumbnails=generate_thumbnails,
            log_gphoto2=self.log_gphoto2
        )

        self.sendStartWorkerToThread(self.copy_controller, worker_id=scan_id, data=copyfiles_args)

    @pyqtSlot(int, str, str)
    def tempDirsReceivedFromCopyFiles(self, scan_id: int,
                                      photo_temp_dir: str,
                                      video_temp_dir: str) -> None:
        self.fileSystemFilter.setTempDirs([photo_temp_dir, video_temp_dir])
        self.temp_dirs_by_scan_id[scan_id] = list(
            filter(None,[photo_temp_dir, video_temp_dir])
        )

    def cleanAllTempDirs(self):
        """
        Deletes temporary files and folders used in all downloads.
        """
        if self.temp_dirs_by_scan_id:
            logging.debug("Cleaning temporary directories")
            for scan_id in self.temp_dirs_by_scan_id:
                self.cleanTempDirsForScanId(scan_id, remove_entry=False)
            self.temp_dirs_by_scan_id = {}

    def cleanTempDirsForScanId(self, scan_id: int, remove_entry: bool=True):
        """
        Deletes temporary files and folders used in download.

        :param scan_id: the scan id associated with the temporary
         directory
        :param remove_entry: if True, remove the scan_id from the
         dictionary tracking temporary directories
        """

        home_dir = os.path.expanduser("~")
        for d in self.temp_dirs_by_scan_id[scan_id]:
            assert d != home_dir
            if os.path.isdir(d):
                try:
                    shutil.rmtree(d, ignore_errors=True)
                except:
                    logging.error("Unknown error deleting temporary directory %s", d)
        if remove_entry:
            del self.temp_dirs_by_scan_id[scan_id]

    @pyqtSlot(bool, RPDFile, int, 'PyQt_PyObject')
    def copyfilesDownloaded(self, download_succeeded: bool,
                            rpd_file: RPDFile,
                            download_count: int,
                            mdata_exceptions: Optional[Tuple[Exception]]) -> None:

        scan_id = rpd_file.scan_id

        if scan_id not in self.devices:
            logging.debug(
                "Ignoring file %s because its device has been removed", rpd_file.full_file_name
            )
            return

        self.download_tracker.set_download_count_for_file(rpd_file.uid, download_count)
        self.download_tracker.set_download_count(scan_id, download_count)
        rpd_file.download_start_time = self.download_start_datetime
        if rpd_file.file_type == FileType.photo:
            rpd_file.generate_extension_case = self.prefs.photo_extension
        else:
            rpd_file.generate_extension_case = self.prefs.video_extension

        if mdata_exceptions is not None and self.prefs.warn_fs_metadata_error:
            self.copy_metadata_errors.add_problem(
                worker_id=scan_id, path=rpd_file.temp_full_file_name,
                mdata_exceptions=mdata_exceptions
            )

        self.sendDataMessageToThread(
            self.rename_controller,
            data=RenameAndMoveFileData(rpd_file=rpd_file,
            download_count=download_count,
            download_succeeded=download_succeeded)
        )

    @pyqtSlot(int, 'PyQt_PyObject', 'PyQt_PyObject')
    def copyfilesBytesDownloaded(self, scan_id: int,
                                 total_downloaded: int,
                                 chunk_downloaded: int) -> None:
        """
        Update the tracking and display of how many bytes have been
        downloaded / copied.
        """

        if scan_id not in self.devices:
            return

        try:
            assert total_downloaded >= 0
            assert chunk_downloaded >= 0
        except AssertionError:
            logging.critical(
                "Unexpected negative values for total / chunk downloaded: %s %s ",
                total_downloaded, chunk_downloaded
            )

        self.download_tracker.set_total_bytes_copied(scan_id, total_downloaded)
        if len(self.devices.have_downloaded_from) > 1:
            model = self.mapModel(scan_id)
            model.percent_complete[scan_id] = self.download_tracker.get_percent_complete(scan_id)
        self.time_check.increment(bytes_downloaded=chunk_downloaded)
        self.time_remaining.update(scan_id, bytes_downloaded=chunk_downloaded)
        self.updateFileDownloadDeviceProgress()

    @pyqtSlot(int, 'PyQt_PyObject')
    def copyfilesProblems(self, scan_id: int, problems: CopyingProblems) -> None:
        for problem in self.copy_metadata_errors.problems(worker_id=scan_id):
            problems.append(problem)

        if problems:
            try:
                device = self.devices[scan_id]
                problems.name = device.display_name
                problems.uri=device.uri
            except KeyError:
                # Device has already been removed
                logging.error("Device with scan id %s unexpectedly removed", scan_id)
                device_archive = self.devices.device_archive[scan_id]
                problems.name = device_archive.name
                problems.uri = device_archive.uri
            finally:
                self.addErrorLogMessage(problems=problems)

    @pyqtSlot(int)
    def copyfilesFinished(self, scan_id: int) -> None:
        if scan_id in self.devices:
            logging.debug("All files finished copying for %s", self.devices[scan_id].display_name)

    @pyqtSlot(bool, RPDFile, int)
    def fileRenamedAndMoved(self, move_succeeded: bool,
                            rpd_file: RPDFile,
                            download_count: int) -> None:
        """
        Called after a file has been renamed  -- that is, moved from the
        temp dir it was downloaded into, and renamed using the file
        renaming rules
        """

        scan_id = rpd_file.scan_id

        if scan_id not in self.devices:
            logging.debug(
                "Ignoring file %s because its device has been removed",
                rpd_file.download_full_file_name or rpd_file.full_file_name
            )
            return

        if rpd_file.mdatatime_caused_ctime_change and scan_id not in \
                self.thumbnailModel.ctimes_differ:
            self.thumbnailModel.addCtimeDisparity(rpd_file=rpd_file)

        if self.thumbnailModel.sendToDaemonThumbnailer(rpd_file=rpd_file):
            if rpd_file.status in constants.Downloaded:
                logging.debug(
                    "Assigning daemon thumbnailer to work on %s", rpd_file.download_full_file_name
                )
                self.sendDataMessageToThread(
                    self.thumbnail_deamon_controller,
                    data=ThumbnailDaemonData(
                        rpd_file=rpd_file,
                        write_fdo_thumbnail=self.prefs.save_fdo_thumbnails,
                        use_thumbnail_cache=self.prefs.use_thumbnail_cache,
                        force_exiftool=self.prefs.force_exiftool,
                    )
                )
            else:
                logging.debug(
                    '%s was not downloaded, so adjusting download tracking', rpd_file.full_file_name
                )
                self.download_tracker.thumbnail_generated_post_download(scan_id)

        if rpd_file.status in constants.Downloaded and \
                self.fileSystemModel.add_subfolder_downloaded_into(
                    path=rpd_file.download_path, download_folder=rpd_file.download_folder):
            if rpd_file.file_type == FileType.photo:
                self.photoDestinationFSView.expandPath(rpd_file.download_path)
                self.photoDestinationFSView.update()
            else:
                self.videoDestinationFSView.expandPath(rpd_file.download_path)
                self.videoDestinationFSView.update()

        if self.prefs.backup_files:
            if self.backup_devices.backup_possible(rpd_file.file_type):
                self.backupFile(rpd_file, move_succeeded, download_count)
            else:
                self.fileDownloadFinished(move_succeeded, rpd_file)
        else:
            self.fileDownloadFinished(move_succeeded, rpd_file)

    @pyqtSlot(RPDFile, QPixmap)
    def thumbnailReceivedFromDaemon(self, rpd_file: RPDFile, thumbnail: QPixmap) -> None:
        """
        A thumbnail will be received directly from the daemon process when
        it was able to get a thumbnail from the FreeDesktop.org 256x256
        cache, and there was thus no need write another

        :param rpd_file: rpd_file details of the file the thumbnail was
         generated for
        :param thumbnail: a thumbnail for display in the thumbnail view,
        """

        self.thumbnailModel.thumbnailReceived(rpd_file=rpd_file, thumbnail=thumbnail)

    def thumbnailGeneratedPostDownload(self, rpd_file: RPDFile) -> None:
        """
        Adjust download tracking to note that a thumbnail was generated
        after a file was downloaded. Possibly handle situation where
        all files have been downloaded.

        A thumbnail will be generated post download if
        the sole task of the thumbnail extractors was to write out the
        FreeDesktop.org thumbnails, and/or if we didn't generate it before
        the download started.

        :param rpd_file: details of the file
        """

        uid = rpd_file.uid
        scan_id = rpd_file.scan_id
        if self.prefs.backup_files and rpd_file.fdo_thumbnail_128_name:
            self.generated_fdo_thumbnails[uid] = rpd_file.fdo_thumbnail_128_name
            if uid in self.backup_fdo_thumbnail_cache:
                self.sendDataMessageToThread(
                    self.thumbnail_deamon_controller,
                    data=ThumbnailDaemonData(
                        rpd_file=rpd_file,
                        write_fdo_thumbnail=True,
                        backup_full_file_names=self.backup_fdo_thumbnail_cache[uid],
                        fdo_name=rpd_file.fdo_thumbnail_128_name,
                        force_exiftool=self.prefs.force_exiftool
                    )
                )
                del self.backup_fdo_thumbnail_cache[uid]
        self.download_tracker.thumbnail_generated_post_download(scan_id=scan_id)
        completed, files_remaining = self.isDownloadCompleteForScan(scan_id)
        if completed:
            self.fileDownloadCompleteFromDevice(scan_id=scan_id, files_remaining=files_remaining)

    def thumbnailGenerationStopped(self, scan_id: int) -> None:
        """
        Slot for when a the thumbnail worker has been forcefully stopped,
        rather than merely finished in its work

        :param scan_id: scan_id of the device that was being thumbnailed
        """
        if scan_id not in self.devices:
            logging.debug(
                "Ignoring scan_id %s from terminated thumbailing, as its device does "
                "not exist anymore", scan_id
            )
        else:
            device = self.devices[scan_id]
            if scan_id in self.devices.cameras_to_stop_thumbnailing:
                self.devices.cameras_to_stop_thumbnailing.remove(scan_id)
                logging.debug("Thumbnailing successfully terminated for %s", device.display_name)
                if not self.devices.download_start_blocked():
                    self.startDownloadPhase2()
            else:
                logging.debug(
                    "Ignoring the termination of thumbnailing from %s, as it's "
                    "not for a camera from which a download was waiting to be started",
                    device.display_name
                )

    @pyqtSlot(int, 'PyQt_PyObject')
    def backupFileProblems(self, device_id: int, problems: BackingUpProblems) -> None:
        for problem in self.backup_metadata_errors.problems(worker_id=device_id):
            problems.append(problem)

        if problems:
            self.addErrorLogMessage(problems=problems)

    def sendBackupStartFinishMessageToWorkers(self, message: BackupStatus) -> None:
        if self.prefs.backup_files:
            download_types = self.download_files.download_types
            for path in self.backup_devices:
                backup_type = self.backup_devices[path].backup_type
                if (
                        (
                            backup_type == BackupLocationType.photos_and_videos or
                            download_types == DownloadingFileTypes.photos_and_videos
                        ) or backup_type == download_types):
                    device_id = self.backup_devices.device_id(path)
                    data = BackupFileData(message=message)
                    self.sendDataMessageToThread(
                        self.backup_controller, worker_id=device_id, data=data
                    )

    def backupFile(self, rpd_file: RPDFile, move_succeeded: bool, download_count: int) -> None:
        if self.prefs.backup_device_autodetection:
            if rpd_file.file_type == FileType.photo:
                path_suffix = self.prefs.photo_backup_identifier
            else:
                path_suffix = self.prefs.video_backup_identifier
        else:
            path_suffix = None

        if rpd_file.file_type == FileType.photo:
            logging.debug("Backing up photo %s", rpd_file.download_name)
        else:
            logging.debug("Backing up video %s", rpd_file.download_name)

        for path in self.backup_devices:
            backup_type = self.backup_devices[path].backup_type
            do_backup = (
                (backup_type == BackupLocationType.photos_and_videos) or
                (
                    rpd_file.file_type == FileType.photo and backup_type ==
                    BackupLocationType.photos
                ) or (
                    rpd_file.file_type == FileType.video and backup_type ==
                    BackupLocationType.videos
                )
            )
            if do_backup:
                logging.debug("Backing up to %s", path)
            else:
                logging.debug("Not backing up to %s", path)
            # Even if not going to backup to this device, need to send it
            # anyway so progress bar can be updated. Not this most efficient
            # but the code is more simpler
            # TODO: investigate a more optimal approach!

            device_id = self.backup_devices.device_id(path)
            data = BackupFileData(
                rpd_file=rpd_file,
                move_succeeded=move_succeeded,
                do_backup=do_backup,
                path_suffix=path_suffix,
                backup_duplicate_overwrite=self.prefs.backup_duplicate_overwrite,
                verify_file=self.prefs.verify_file,
                download_count=download_count,
                save_fdo_thumbnail=self.prefs.save_fdo_thumbnails
            )
            self.sendDataMessageToThread(self.backup_controller, worker_id=device_id, data=data)

    @pyqtSlot(int, bool, bool, RPDFile, str, 'PyQt_PyObject')
    def fileBackedUp(self, device_id: int,
                     backup_succeeded: bool,
                     do_backup: bool,
                     rpd_file: RPDFile,
                     backup_full_file_name: str,
                     mdata_exceptions: Optional[Tuple[Exception]]) -> None:

        if do_backup:
            if self.prefs.generate_thumbnails and self.prefs.save_fdo_thumbnails and \
                    rpd_file.should_write_fdo() and backup_succeeded:
                self.backupGenerateFdoThumbnail(
                    rpd_file=rpd_file, backup_full_file_name=backup_full_file_name
                )

            self.download_tracker.file_backed_up(rpd_file.scan_id, rpd_file.uid)

            if mdata_exceptions is not None and self.prefs.warn_fs_metadata_error:
                self.backup_metadata_errors.add_problem(
                    worker_id=device_id, path=backup_full_file_name,
                    mdata_exceptions=mdata_exceptions
                )

            if self.download_tracker.file_backed_up_to_all_locations(
                    rpd_file.uid, rpd_file.file_type):
                logging.debug(
                    "File %s will not be backed up to any more locations", rpd_file.download_name
                )
                self.fileDownloadFinished(backup_succeeded, rpd_file)

    @pyqtSlot('PyQt_PyObject', 'PyQt_PyObject')
    def backupFileBytesBackedUp(self, scan_id: int, chunk_downloaded: int) -> None:
        self.download_tracker.increment_bytes_backed_up(scan_id, chunk_downloaded)
        self.time_check.increment(bytes_downloaded=chunk_downloaded)
        self.time_remaining.update(scan_id, bytes_downloaded=chunk_downloaded)
        self.updateFileDownloadDeviceProgress()

    def initializeBackupThumbCache(self) -> None:
        """
        Prepare tracking of thumbnail generation for backed up files
        """

        # indexed by uid, deque of full backup paths
        self.generated_fdo_thumbnails = dict()  # type: Dict[str]
        self.backup_fdo_thumbnail_cache = defaultdict(list)  # type: Dict[List[str]]

    def backupGenerateFdoThumbnail(self, rpd_file: RPDFile, backup_full_file_name: str) -> None:
        uid = rpd_file.uid
        if uid not in self.generated_fdo_thumbnails:
            logging.debug(
                "Caching FDO thumbnail creation for backup %s", backup_full_file_name
            )
            self.backup_fdo_thumbnail_cache[uid].append(backup_full_file_name)
        else:
            # An FDO thumbnail has already been generated for the downloaded file
            assert uid not in self.backup_fdo_thumbnail_cache
            logging.debug(
                "Assigning daemon thumbnailer to create FDO thumbnail for %s", backup_full_file_name
            )
            self.sendDataMessageToThread(
                self.thumbnail_deamon_controller,
                data=ThumbnailDaemonData(
                    rpd_file=rpd_file,
                    write_fdo_thumbnail=True,
                    backup_full_file_names=[backup_full_file_name],
                    fdo_name=self.generated_fdo_thumbnails[uid],
                    force_exiftool=self.prefs.force_exiftool,
                )
            )

    @pyqtSlot(int, list)
    def updateSequences(self, stored_sequence_no: int, downloads_today: List[str]) -> None:
        """
        Called at conclusion of a download, with values coming from
        renameandmovefile process
        """

        self.prefs.stored_sequence_no = stored_sequence_no
        self.prefs.downloads_today = downloads_today
        self.prefs.sync()
        logging.debug("Saved sequence values to preferences")
        if self.application_state == ApplicationState.exiting:
            self.close()
        else:
            self.renamePanel.updateSequences(
                downloads_today=downloads_today, stored_sequence_no=stored_sequence_no
            )

    @pyqtSlot()
    def fileRenamedAndMovedFinished(self) -> None:
        """Currently not called"""
        pass

    def isDownloadCompleteForScan(self, scan_id: int) -> Tuple[bool, int]:
        """
        Determine if all files have been downloaded and backed up for a device

        :param scan_id: device's scan id
        :return: True if the download is completed for that scan_id,
        and the number of files remaining for the scan_id, BUT
        the files remaining value is valid ONLY if the download is
         completed
        """

        completed = self.download_tracker.all_files_downloaded_by_scan_id(scan_id)
        if completed:
            logging.debug("All files downloaded for %s", self.devices[scan_id].display_name)
            if self.download_tracker.no_post_download_thumb_generation_by_scan_id[scan_id]:
                logging.debug(
                    "Thumbnails generated for %s thus far during download: %s of %s",
                    self.devices[scan_id].display_name,
                    self.download_tracker.post_download_thumb_generation[scan_id],
                    self.download_tracker.no_post_download_thumb_generation_by_scan_id[scan_id]
                )
        completed = completed and \
                    self.download_tracker.all_post_download_thumbs_generated_for_scan(scan_id)

        if completed and self.prefs.backup_files:
            completed = self.download_tracker.all_files_backed_up(scan_id)

        if completed:
            files_remaining = self.thumbnailModel.getNoFilesRemaining(scan_id)
        else:
            files_remaining = 0

        return completed, files_remaining

    def updateFileDownloadDeviceProgress(self):
        """
        Updates progress bar and optionally the Unity progress bar
        """

        percent_complete = self.download_tracker.get_overall_percent_complete()
        self.downloadProgressBar.setValue(round(percent_complete * 100))
        if self.unity_progress:
            for launcher in self.desktop_launchers:
                launcher.set_property('progress', percent_complete)
                launcher.set_property('progress_visible', True)

    def fileDownloadFinished(self, succeeded: bool, rpd_file: RPDFile) -> None:
        """
        Called when a file has been downloaded i.e. copied, renamed,
        and backed up
        """
        scan_id = rpd_file.scan_id

        if self.prefs.move:
            # record which files to automatically delete when download
            # completes
            self.download_tracker.add_to_auto_delete(rpd_file)

        self.thumbnailModel.updateStatusPostDownload(rpd_file)
        self.download_tracker.file_downloaded_increment(
            scan_id, rpd_file.file_type, rpd_file.status
        )

        device = self.devices[scan_id]
        device.download_statuses.add(rpd_file.status)

        completed, files_remaining = self.isDownloadCompleteForScan(scan_id)
        if completed:
            self.fileDownloadCompleteFromDevice(scan_id=scan_id, files_remaining=files_remaining)

    def fileDownloadCompleteFromDevice(self, scan_id: int, files_remaining: int) -> None:

        device = self.devices[scan_id]

        device_finished = files_remaining == 0
        if device_finished:
            logging.debug("All files from %s are downloaded; none remain", device.display_name)
            state = DeviceState.finished
        else:
            logging.debug(
                "Download finished from %s; %s remain be be potentially downloaded",
                device.display_name, files_remaining
            )
            state = DeviceState.idle

        self.devices.set_device_state(scan_id=scan_id, state=state)
        self.mapModel(scan_id).setSpinnerState(scan_id, state)

        # Rebuild temporal proximity if it needs it
        if scan_id in self.thumbnailModel.ctimes_differ and not \
                self.thumbnailModel.filesRemainToDownload(scan_id=scan_id):
            self.thumbnailModel.processCtimeDisparity(scan_id=scan_id)
            self.folder_preview_manager.queue_folder_removal_for_device(scan_id=scan_id)

        # Last file for this scan id has been downloaded, so clean temp
        # directory
        logging.debug("Purging temp directories")
        self.cleanTempDirsForScanId(scan_id)
        if self.prefs.move:
            logging.debug("Deleting downloaded source files")
            self.deleteSourceFiles(scan_id)
            self.download_tracker.clear_auto_delete(scan_id)
        self.updateProgressBarState()
        self.thumbnailModel.updateDeviceDisplayCheckMark(scan_id=scan_id)

        del self.time_remaining[scan_id]
        self.notifyDownloadedFromDevice(scan_id)
        if files_remaining == 0 and self.prefs.auto_unmount:
            self.unmountVolume(scan_id)

        if not self.downloadIsRunning():
            logging.debug("Download completed")
            self.dl_update_timer.stop()
            self.enablePrefsAndRefresh(enabled=True)
            self.notifyDownloadComplete()
            self.downloadProgressBar.reset()
            if self.prefs.backup_files:
                self.initializeBackupThumbCache()
                self.backupPanel.updateLocationCombos()

            if self.unity_progress:
                for launcher in self.desktop_launchers:
                    launcher.set_property('progress_visible', False)

            self.folder_preview_manager.remove_folders_for_queued_devices()

            # Update prefs with stored sequence number and downloads today
            # values
            data = RenameAndMoveFileData(message=RenameAndMoveStatus.download_completed)
            self.sendDataMessageToThread(self.rename_controller, data=data)

            # Ask backup processes to send problem reports
            self.sendBackupStartFinishMessageToWorkers(message=BackupStatus.backup_completed)

            if ((self.prefs.auto_exit and self.download_tracker.no_errors_or_warnings())
                    or self.prefs.auto_exit_force):

                if not self.thumbnailModel.filesRemainToDownload():
                    logging.debug("Auto exit is initiated")
                    self.close()

            self.download_tracker.purge_all()

            self.setDownloadActionLabel()
            self.setDownloadCapabilities()

            self.download_start_datetime = None
            self.download_start_time = None

    @pyqtSlot('PyQt_PyObject')
    def addErrorLogMessage(self, problems: Problems) -> None:

        self.errorLog.addProblems(problems)
        increment = len(problems)
        if not self.errorLog.isActiveWindow():
            self.errorsPending.incrementCounter(increment=increment)

    def immediatelyDisplayDownloadRunningInStatusBar(self):
        """
        Without any delay, immediately change the status bar message so the
        user knows the download has started.
        """

        self.statusBar().showMessage(self.devices.downloading_from())

    @pyqtSlot()
    def displayDownloadRunningInStatusBar(self):
        """
        Display a message in the status bar about the current download
        """
        if not self.downloadIsRunning():
            self.dl_update_timer.stop()
            self.displayMessageInStatusBar()
            return

        updated, download_speed = self.time_check.update_download_speed()
        if updated:

            downloading = self.devices.downloading_from()

            time_remaining = self.time_remaining.time_remaining(self.prefs.detailed_time_remaining)
            if (time_remaining is None or
                    time.time() < self.download_start_time + constants.ShowTimeAndSpeedDelay):
                message = downloading
            else:
                # Translators - in the middle is a unicode em dash - please retain it
                # This string is displayed in the status bar when the download is running
                # Translators: %(variable)s represents Python code, not a plural of the term
                # variable. You must keep the %(variable)s untranslated, or the program will
                # crash.
                message = _(
                    '%(downloading_from)s — %(time_left)s left (%(speed)s)'
                ) % dict(
                    downloading_from=downloading,
                    time_left=time_remaining,
                    speed=download_speed
                )
            self.statusBar().showMessage(message)

    def enablePrefsAndRefresh(self, enabled: bool) -> None:
        """
        Disable the user being to access the refresh command or change various
        program preferences while a download is occurring.

        :param enabled: if True, then the user is able to activate the
        preferences and refresh commands.
        """

        self.refreshAct.setEnabled(enabled)
        self.preferencesAct.setEnabled(enabled)
        self.renamePanel.setEnabled(enabled)
        self.backupPanel.setEnabled(enabled)
        self.jobCodePanel.setEnabled(enabled)

    def unmountVolume(self, scan_id: int) -> None:
        """
        Cameras are already unmounted, so no need to unmount them!
        :param scan_id: the scan id of the device to be umounted
        """

        device = self.devices[scan_id]  # type: Device

        if device.device_type == DeviceType.volume:
            if self.gvfsControlsMounts:
                self.gvolumeMonitor.unmountVolume(path=device.path)
            else:
                self.udisks2Unmount.emit(device.path)

    def deleteSourceFiles(self, scan_id: int)  -> None:
        """
        Delete files from download device at completion of download
        """
        # TODO delete from cameras and from other devices
        # TODO should assign this to a process or a thread, and delete then
        to_delete = self.download_tracker.get_files_to_auto_delete(scan_id)

    def notifyDownloadedFromDevice(self, scan_id: int) -> None:
        """
        Display a system notification to the user using libnotify
        that the files have been downloaded from the device
        :param scan_id: identifies which device
        """

        device = self.devices[scan_id]

        notification_name  = device.display_name

        no_photos_downloaded = self.download_tracker.get_no_files_downloaded(
            scan_id, FileType.photo
        )
        no_videos_downloaded = self.download_tracker.get_no_files_downloaded(
            scan_id, FileType.video
        )
        no_photos_failed = self.download_tracker.get_no_files_failed(scan_id, FileType.photo)
        no_videos_failed = self.download_tracker.get_no_files_failed(scan_id, FileType.video)
        no_files_downloaded = no_photos_downloaded + no_videos_downloaded
        no_files_failed = no_photos_failed + no_videos_failed
        no_warnings = self.download_tracker.get_no_warnings(scan_id)

        file_types = file_types_by_number(no_photos_downloaded, no_videos_downloaded)
        file_types_failed = file_types_by_number(no_photos_failed, no_videos_failed)
        # Translators: e.g. 23 photos downloaded
        # Translators: %(variable)s represents Python code, not a plural of the term
        # variable. You must keep the %(variable)s untranslated, or the program will
        # crash.
        message = _(
            "%(noFiles)s %(filetypes)s downloaded"
        ) % {
            'noFiles': thousands(no_files_downloaded), 'filetypes': file_types
        }

        if no_files_failed:
            # Translators: e.g. 2 videos failed to download
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            message += "\n" + _(
                "%(noFiles)s %(filetypes)s failed to download"
            ) % {
                'noFiles': thousands(no_files_failed), 'filetypes': file_types_failed
            }

        if no_warnings:
            message = "%s\n%s " % (message, no_warnings) + _("warnings")

        message_shown = False
        if self.have_libnotify:
            n = Notify.Notification.new(notification_name, message, 'rapid-photo-downloader')
            try:
                message_shown =  n.show()
            except:
                logging.error(
                    "Unable to display downloaded from device message using notification system"
                )
            if not message_shown:
                logging.error(
                    "Unable to display downloaded from device message using notification system"
                )
                logging.info("{}: {}".format(notification_name, message))

    def notifyDownloadComplete(self) -> None:
        """
        Notify all downloads are complete

        If having downloaded from more than one device, display a
        system notification to the user using libnotify that all files
        have been downloaded.

        Regardless of how many downloads have been downloaded
        from, display message in status bar.
        """

        show_notification = len(self.devices.have_downloaded_from) > 1

        n_message = _("All downloads complete")

        # photo downloads
        photo_downloads = self.download_tracker.total_photos_downloaded
        if photo_downloads and show_notification:
            filetype = file_types_by_number(photo_downloads, 0)
            # Translators: e.g. 23 photos downloaded
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            n_message += "\n" + _(
                "%(number)s %(numberdownloaded)s"
            ) % dict(
                number=thousands(photo_downloads),
                # Translators: %(variable)s represents Python code, not a plural of the term
                # variable. You must keep the %(variable)s untranslated, or the program will
                # crash.
                numberdownloaded=_("%(filetype)s downloaded") % dict(filetype=filetype)
            )

        # photo failures
        photo_failures = self.download_tracker.total_photo_failures
        if photo_failures and show_notification:
            filetype = file_types_by_number(photo_failures, 0)
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            n_message += "\n" + _(
                "%(number)s %(numberdownloaded)s"
            ) % dict(
                number=thousands(photo_failures),
                # Translators: %(variable)s represents Python code, not a plural of the term
                # variable. You must keep the %(variable)s untranslated, or the program will
                # crash.
                numberdownloaded=_("%(filetype)s failed to download") % dict(filetype=filetype)
            )

        # video downloads
        video_downloads = self.download_tracker.total_videos_downloaded
        if video_downloads and show_notification:
            filetype = file_types_by_number(0, video_downloads)
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            n_message += "\n" + _(
                "%(number)s %(numberdownloaded)s"
            ) % dict(
                number=thousands(video_downloads),
                # Translators: %(variable)s represents Python code, not a plural of the term
                # variable. You must keep the %(variable)s untranslated, or the program will
                # crash.
                numberdownloaded=_("%(filetype)s downloaded") % dict(filetype=filetype)
            )

        # video failures
        video_failures = self.download_tracker.total_video_failures
        if video_failures and show_notification:
            filetype = file_types_by_number(0, video_failures)
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            n_message += "\n" + _(
                "%(number)s %(numberdownloaded)s"
            ) % dict(
                number=thousands(video_failures),
                # Translators: %(variable)s represents Python code, not a plural of the term
                # variable. You must keep the %(variable)s untranslated, or the program will
                # crash.
                numberdownloaded=_("%(filetype)s failed to download") % dict(filetype=filetype)
            )

        # warnings
        warnings = self.download_tracker.total_warnings
        if warnings and show_notification:
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            n_message += "\n" + _(
                "%(number)s %(numberdownloaded)s"
            ) % dict(
                number=thousands(warnings),
                numberdownloaded=_("warnings")
            )

        if show_notification:
            message_shown = False
            if self.have_libnotify:
                n = Notify.Notification.new(
                    _('Rapid Photo Downloader'), n_message, 'rapid-photo-downloader'
                )
                try:
                    message_shown = n.show()
                except Exception:
                    logging.error(
                        "Unable to display download complete message using notification system"
                    )
            if not message_shown:
                logging.error(
                    "Unable to display download complete message using notification system"
                )

        failures = photo_failures + video_failures

        if failures == 1:
            f = _('1 failure')
        elif failures > 1:
            f = _('%d failures') % failures
        else:
            f = ''

        if warnings == 1:
            w = _('1 warning')
        elif warnings > 1:
            w = _('%d warnings') % warnings
        else:
            w = ''

        if f and w:
            fw = make_internationalized_list((f, w))
        elif f:
            fw = f
        elif w:
            fw = w
        else:
            fw = ''

        devices = self.devices.reset_and_return_have_downloaded_from()
        if photo_downloads + video_downloads:
            ftc = FileTypeCounter(
                    {FileType.photo: photo_downloads, FileType.video: video_downloads}
            )
            no_files_and_types = ftc.file_types_present_details().lower()

            if not fw:
                # Translators: %(variable)s represents Python code, not a plural of the term
                # variable. You must keep the %(variable)s untranslated, or the program will
                # crash.
                downloaded = _(
                    'Downloaded %(no_files_and_types)s from %(devices)s'
                ) % dict(no_files_and_types=no_files_and_types, devices=devices)
            else:
                # Translators: %(variable)s represents Python code, not a plural of the term
                # variable. You must keep the %(variable)s untranslated, or the program will
                # crash.
                downloaded = _(
                    'Downloaded %(no_files_and_types)s from %(devices)s — %(failures)s'
                ) % dict(no_files_and_types=no_files_and_types, devices=devices, failures=fw)
        else:
            if fw:
                # Translators: %(variable)s represents Python code, not a plural of the term
                # variable. You must keep the %(variable)s untranslated, or the program will
                # crash.
                downloaded = _('No files downloaded — %(failures)s') % dict(failures=fw)
            else:
                downloaded = _('No files downloaded')
        logging.info('%s', downloaded)
        self.statusBar().showMessage(downloaded)

    def invalidDownloadFolders(self, downloading: DownloadingFileTypes) -> List[str]:
        """
        Checks validity of download folders based on the file types the
        user is attempting to download.

        :return list of the invalid directories, if any, or empty list.
        """

        invalid_dirs = []

        # sadly this causes an exception on python 3.4:
        # downloading.photos or downloading.photos_and_videos

        if downloading in (DownloadingFileTypes.photos,  DownloadingFileTypes.photos_and_videos):
            if not validate_download_folder(self.prefs.photo_download_folder).valid:
                invalid_dirs.append(self.prefs.photo_download_folder)
        if downloading in (DownloadingFileTypes.videos,  DownloadingFileTypes.photos_and_videos):
            if not validate_download_folder(self.prefs.video_download_folder).valid:
                invalid_dirs.append(self.prefs.video_download_folder)
        return invalid_dirs

    def notifyPrefsAreInvalid(self, details: str) -> None:
        """
        Notifies the user that the preferences are invalid.

        Assumes that the main window is already showing
        :param details: preference error details
        """

        logging.error("Program preferences are invalid: %s", details)
        title = _("Program preferences are invalid")
        # Translators: %(variable)s represents Python code, not a plural of the term
        # variable. You must keep the %(variable)s untranslated, or the program will
        # crash.
        # Translators: please do not change HTML codes like <br>, <i>, </i>, or <b>, </b> etc.
        message = "<b>%(title)s</b><br><br>%(details)s" % dict(title=title, details=details)
        msgBox = standardMessageBox(
            message=message, rich_text=True, standardButtons=QMessageBox.Ok,
            iconType=QMessageBox.Warning
        )
        msgBox.exec()

    def deviceState(self, scan_id: int) -> DeviceState:
        """
        What the device is being used for at the present moment.

        :param scan_id: device to check
        :return: DeviceState
        """

        return self.devices.device_state[scan_id]

    @pyqtSlot('PyQt_PyObject', 'PyQt_PyObject', FileTypeCounter, 'PyQt_PyObject', bool, bool)
    def scanFilesReceived(self, rpd_files: List[RPDFile],
                          sample_files: List[RPDFile],
                          file_type_counter: FileTypeCounter,
                          file_size_sum: FileSizeSum,
                          entire_video_required: Optional[bool],
                          entire_photo_required: Optional[bool]) -> None:
        """
        Process scanned file information received from the scan process
        """

        # Update scan running totals
        scan_id = rpd_files[0].scan_id
        if scan_id not in self.devices:
            return
        device = self.devices[scan_id]

        sample_photo, sample_video = sample_files
        if sample_photo is not None:
            logging.info(
                "Updating example file name using sample photo from %s", device.display_name
            )
            self.devices.sample_photo = sample_photo  # type: Photo
            self.renamePanel.setSamplePhoto(self.devices.sample_photo)
            # sample required for editing download subfolder generation
            self.photoDestinationDisplay.sample_rpd_file = self.devices.sample_photo

        if sample_video is not None:
            logging.info(
                "Updating example file name using sample video from %s", device.display_name
            )
            self.devices.sample_video = sample_video  # type: Video
            self.renamePanel.setSampleVideo(self.devices.sample_video)
            # sample required for editing download subfolder generation
            self.videoDestinationDisplay.sample_rpd_file = self.devices.sample_video

        if device.device_type == DeviceType.camera:
            if entire_video_required is not None:
                device.entire_video_required = entire_video_required
            if entire_photo_required is not None:
                device.entire_photo_required = entire_photo_required

        device.file_type_counter = file_type_counter
        device.file_size_sum = file_size_sum

        self.mapModel(scan_id).updateDeviceScan(scan_id)

        self.thumbnailModel.addFiles(
            scan_id=scan_id, rpd_files=rpd_files, generate_thumbnail=not self.autoStart(scan_id)
        )
        self.folder_preview_manager.add_rpd_files(rpd_files=rpd_files)

    @pyqtSlot(int, CameraErrorCode)
    def scanErrorReceived(self, scan_id: int, error_code: CameraErrorCode) -> None:
        """
        Notify the user their camera/phone is inaccessible.

        :param scan_id: scan id of the device
        :param error_code: the specific libgphoto2 error, mapped onto our own
         enum
        """

        if scan_id not in self.devices:
            return

        # During program startup, the main window may not yet be showing
        self.showMainWindow()

        # An error occurred
        device = self.devices[scan_id]
        camera_model = device.display_name
        if error_code == CameraErrorCode.locked:
            title =_('Rapid Photo Downloader')
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            # Translators: please do not change HTML codes like <br>, <i>, </i>, or <b>, </b> etc.
            message = _(
                '<b>All files on the %(camera)s are inaccessible</b>.<br><br>It '
                'may be locked or not configured for file transfers using USB. '
                'You can unlock it and try again.<br><br>On some models you also '
                'need to change the setting to allow the use of USB for '
                '<i>File Transfer</i>.<br><br>'
                'Learn more about '
                '<a href="https://damonlynch.net/rapid/documentation/#downloadingfromcameras">'
                'downloading from cameras</a> and '
                '<a href="https://damonlynch.net/rapid/documentation/#downloadingfromphones">'
                'enabling downloading from phones</a>. <br><br>'
                'Alternatively, you can ignore the %(camera)s.'
            ) % {'camera': camera_model}
        else:
            assert error_code == CameraErrorCode.inaccessible
            title = _('Rapid Photo Downloader')
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            # Translators: please do not change HTML codes like <br>, <i>, </i>, or <b>, </b> etc.
            message = _(
                '<b>The %(camera)s appears to be in use by another '
                'application.</b><br><br>Rapid Photo Downloader cannnot access a phone or camera '
                'that is being used by another program like a file manager.<br><br>'
                'If the device is mounted in your file manager, you must first &quot;eject&quot; '
                'it from the other program while keeping the %(camera)s plugged in.<br><br>'
                'If that does not work, unplug the '
                '%(camera)s from the computer and plug it in again.<br><br>'
                'Learn more about '
                '<a href="https://damonlynch.net/rapid/documentation/#downloadingfromcameras">'
                'downloading from cameras</a> and '
                '<a href="https://damonlynch.net/rapid/documentation/#downloadingfromphones">'
                'enabling downloading from phones</a>. <br><br>'
                'Alternatively, you can ignore the %(camera)s.'
            ) % {'camera':camera_model}

        msgBox = QMessageBox(
            QMessageBox.Warning, title, message, QMessageBox.NoButton, self
        )
        msgBox.setIconPixmap(self.devices[scan_id].get_pixmap())
        msgBox.addButton(_("&Try Again"), QMessageBox.AcceptRole)
        msgBox.addButton(_("&Ignore This Device"), QMessageBox.RejectRole)
        self.prompting_for_user_action[device] = msgBox
        role = msgBox.exec_()
        if role == QMessageBox.AcceptRole:
            self.sendResumeToThread(self.scan_controller, worker_id=scan_id)
        else:
            self.removeDevice(scan_id=scan_id, show_warning=False)
        del self.prompting_for_user_action[device]

    @pyqtSlot(int, 'PyQt_PyObject', 'PyQt_PyObject', str)
    def scanDeviceDetailsReceived(self, scan_id: int,
                                  storage_space: List[StorageSpace],
                                  storage_descriptions: List[str],
                                  optimal_display_name: str) -> None:
        """
        Update GUI display and rows DB with definitive camera display name

        :param scan_id: scan id of the device
        :param storage_space: storage information on the device e.g.
         memory card(s) capacity and use
        :param  storage_desctriptions: names of storage on a camera
        :param optimal_display_name: canonical name of the device, as
         reported by libgphoto2
        """

        if scan_id in self.devices:
            device = self.devices[scan_id]
            logging.debug(
                '%s with scan id %s is now known as %s',
                device.display_name, scan_id, optimal_display_name
            )

            if len(storage_space) > 1:
                logging.debug(
                    '%s has %s storage devices', optimal_display_name, len(storage_space)
                )

            if not storage_descriptions:
                logging.warning("No storage descriptors available for %s", optimal_display_name)
            else:
                if len(storage_descriptions) == 1:
                    msg = 'description'
                else:
                    msg = 'descriptions'
                logging.debug("Storage %s: %s", msg, ', '.join(storage_descriptions))

            device.update_camera_attributes(
                display_name=optimal_display_name, storage_space=storage_space,
                storage_descriptions=storage_descriptions
            )
            self.updateSourceButton()
            self.deviceModel.updateDeviceNameAndStorage(scan_id, device)
            self.thumbnailModel.addOrUpdateDevice(scan_id=scan_id)
            self.adjustLeftPanelSliderHandles()
        else:
            logging.debug(
                "Ignoring optimal display name %s and other details because that device was "
                "removed", optimal_display_name
            )

    @pyqtSlot(int, 'PyQt_PyObject')
    def scanProblemsReceived(self, scan_id: int, problems: Problems) -> None:
        self.addErrorLogMessage(problems=problems)

    @pyqtSlot(int)
    def scanFatalError(self, scan_id: int) -> None:
        try:
            device = self.devices[scan_id]
        except KeyError:
            logging.debug("Got scan error from device that no longer exists (scan_id %s)", scan_id)
            return

        h1 = _('Sorry, an unexpected problem occurred while scanning %s.') % device.display_name
        h2 = _('Unfortunately you cannot download from this device.')
        header = '<b>{}</b><br><br>{}'.format(h1, h2)
        if device.device_type == DeviceType.camera and not device.is_mtp_device:
            h3 = _(
                "A possible workaround for the problem might be downloading from the camera's "
                "memory card using a card reader."
            )
            header = '{}<br><br><i>{}</i>'.format(header, h3)

        title = _('Device scan failed')
        self.makeProblemReportDialog(header=header, title=title)

        self.removeDevice(scan_id=scan_id, show_warning=False)

    @pyqtSlot(int)
    def cameraRemovedDuringScan(self, scan_id: int) -> None:
        """
        Scenarios: a camera was physically removed, or file transfer was disabled on an MTP device.

        If disabled, a problem is that the device has not yet been removed from the system.

        But in any case, sometimes camera removal is not picked up by the system while it's being
        accessed. So let's remove it ourselves.

        :param scan_id: device that was removed / disabled
        """

        try:
            device = self.devices[scan_id]
        except KeyError:
            logging.debug("Got scan error from device that no longer exists (scan id %s)", scan_id)
            return

        logging.debug("Camera %s was removed during a scan", device.display_name)
        self.removeDevice(scan_id=scan_id)

    @pyqtSlot(int)
    def cameraRemovedWhileThumbnailing(self, scan_id: int) -> None:
        """
        Scenarios: a camera was physically removed, or file transfer was disabled on an MTP device.

        If disabled, a problem is that the device has not yet been removed from the system.

        But in any case, sometimes camera removal is not picked up by the system while it's being
        accessed. So let's remove it ourselves.

        :param scan_id: device that was removed / disabled
        """

        try:
            device = self.devices[scan_id]
        except KeyError:
            logging.debug(
                "Got thumbnailing error from a camera that no longer exists (scan id %s)", scan_id
            )
            return

        logging.debug(
            "Camera %s was removed while thumbnails were being generated", device.display_name
        )
        self.removeDevice(scan_id=scan_id)

    @pyqtSlot(int)
    def cameraRemovedWhileCopyingFiles(self, scan_id: int) -> None:
        """
        Scenarios: a camera was physically removed, or file transfer was disabled on an MTP device.

        If disabled, a problem is that the device has not yet been removed from the system.

        But in any case, sometimes camera removal is not picked up by the system while it's being
        accessed. So let's remove it ourselves.

        :param scan_id: device that was removed / disabled
        """

        try:
            device = self.devices[scan_id]
        except KeyError:
            logging.debug(
                "Got copy files error from a camera that no longer exists (scan id %s)", scan_id
            )
            return

        logging.debug(
            "Camera %s was removed while filed were being copied from it", device.display_name
        )
        self.removeDevice(scan_id=scan_id)

    @pyqtSlot(int)
    def scanFinished(self, scan_id: int) -> None:
        """
        A single device has finished its scan. Other devices can be in any
        one of a number of states.

        :param scan_id: scan id of the device that finished scanning
        """

        if scan_id not in self.devices:
            return
        device = self.devices[scan_id]
        self.devices.set_device_state(scan_id, DeviceState.idle)
        self.thumbnailModel.flushAddBuffer()

        self.updateProgressBarState()
        self.thumbnailModel.updateAllDeviceDisplayCheckMarks()
        results_summary, file_types_present  = device.file_type_counter.summarize_file_count()
        self.download_tracker.set_file_types_present(scan_id, file_types_present)
        model = self.mapModel(scan_id)
        model.updateDeviceScan(scan_id)
        destinations_good = self.setDownloadCapabilities()

        self.logState()

        if len(self.devices.scanning) == 0:
            self.generateTemporalProximityTableData("a download source has finished being scanned")
        else:
            self.temporalProximity.setState(TemporalProximityState.pending)

        if not destinations_good:
            auto_start = False
        else:
            auto_start = self.autoStart(scan_id)

        if not auto_start and self.prefs.generate_thumbnails:
            # Generate thumbnails for finished scan
            model.setSpinnerState(scan_id, DeviceState.idle)
            if scan_id in self.thumbnailModel.no_thumbnails_by_scan:
                self.devices.set_device_state(scan_id, DeviceState.thumbnailing)
                self.updateProgressBarState()
                self.thumbnailModel.generateThumbnails(scan_id, self.devices[scan_id])
            self.displayMessageInStatusBar()
        elif auto_start:
            self.displayMessageInStatusBar()
            if self.jobCodePanel.needToPromptForJobCode():
                self.showMainWindow()
                model.setSpinnerState(scan_id, DeviceState.idle)
                start_download = self.jobCodePanel.getJobCodeBeforeDownload()
                if not start_download:
                    logging.debug(
                        "Not auto-starting download, because a job code is already being "
                        "prompted for."
                    )
            else:
                start_download = True
            if start_download:
                if self.download_paused:
                    self.devices.queued_to_download.add(scan_id)
                else:
                    self.startDownload(scan_id=scan_id)
        else:
            # not generating thumbnails, and auto start is not on
            model.setSpinnerState(scan_id, DeviceState.idle)
            self.displayMessageInStatusBar()

    def autoStart(self, scan_id: int) -> bool:
        """
        Determine if the download for this device should start automatically
        :param scan_id: scan id of the device
        :return: True if the should start automatically, else False,
        """

        prefs_valid, msg = self.prefs.check_prefs_for_validity()
        if not prefs_valid:
            return False

        if not self.thumbnailModel.filesAreMarkedForDownload(scan_id):
            logging.debug(
                "No files are marked for download for %s", self.devices[scan_id].display_name
            )
            return False

        if scan_id in self.devices.startup_devices:
            return self.prefs.auto_download_at_startup
        else:
            return self.prefs.auto_download_upon_device_insertion

    def quit(self) -> None:
        """
        Convenience function to quit the application.

        Issues a signal to initiate the quit. The signal will be acted
        on when Qt gets the chance.
        """

        QTimer.singleShot(0, self.close)

    def generateTemporalProximityTableData(self, reason: str) -> None:
        """
        Initiate Timeline generation if it's right to do so
        """

        if self.temporalProximity.state == TemporalProximityState.ctime_rebuild:
            logging.info(
                "Was tasked to generate Timeline because %s, but ignoring request "
                "because a rebuild is required ", reason
            )
            return

        rows = self.thumbnailModel.dataForProximityGeneration()
        if rows:
            logging.info("Generating Timeline because %s", reason)

            self.temporalProximity.setState(TemporalProximityState.generating)
            data = OffloadData(thumbnail_rows=rows, proximity_seconds=self.prefs.proximity_seconds)
            self.sendToOffload(data=data)
        else:
            logging.info(
                "Was tasked to generate Timeline because %s, but there is nothing to generate",
                reason
            )


    @pyqtSlot(TemporalProximityGroups)
    def proximityGroupsGenerated(self, proximity_groups: TemporalProximityGroups) -> None:
        if self.temporalProximity.setGroups(proximity_groups=proximity_groups):
            self.thumbnailModel.assignProximityGroups(proximity_groups.col1_col2_uid)

    def closeEvent(self, event) -> None:
        logging.debug("Close event activated")

        if self.close_event_run:
            logging.debug("Close event already run: accepting close event")
            event.accept()
            return

        if self.application_state == ApplicationState.normal:
            self.application_state = ApplicationState.exiting
            self.sendStopToThread(self.scan_controller)
            self.thumbnailModel.stopThumbnailer()
            self.sendStopToThread(self.copy_controller)

            if self.downloadIsRunning():
                logging.debug("Exiting while download is running. Cleaning up...")
                # Update prefs with stored sequence number and downloads today
                # values
                data = RenameAndMoveFileData(message=RenameAndMoveStatus.download_completed)
                self.sendDataMessageToThread(self.rename_controller, data=data)
                # renameandmovefile process will send a message with the
                # updated sequence values. When that occurs,
                # this application will save the sequence values to the
                # program preferences, resume closing and this close event
                # will again be called, but this time the application state
                # flag will indicate the need to resume below.
                logging.debug("Ignoring close event")
                event.ignore()
                return
                # Incidentally, it's the renameandmovefile process that
                # updates the SQL database with the file downloads,
                # so no need to update or close it in this main process

        if self.unity_progress:
            for launcher in self.desktop_launchers:
                launcher.set_property("count", 0)
                launcher.set_property("count_visible", False)
                launcher.set_property('progress_visible', False)

        self.writeWindowSettings()
        logging.debug("Cleaning up provisional download folders")
        self.folder_preview_manager.remove_preview_folders()

        # write settings before closing error log window
        self.errorLog.done(0)

        logging.debug("Terminating main ExifTool process")
        self.exiftool_process.terminate()

        self.sendStopToThread(self.offload_controller)
        self.offloadThread.quit()
        if not self.offloadThread.wait(500):
            self.sendTerminateToThread(self.offload_controller)

        self.sendStopToThread(self.rename_controller)
        self.renameThread.quit()
        if not self.renameThread.wait(500):
            self.sendTerminateToThread(self.rename_controller)

        self.scanThread.quit()
        if not self.scanThread.wait(2000):
            self.sendTerminateToThread(self.scan_controller)

        self.copyfilesThread.quit()
        if not self.copyfilesThread.wait(1000):
            self.sendTerminateToThread(self.copy_controller)

        self.sendStopToThread(self.backup_controller)
        self.backupThread.quit()
        if not self.backupThread.wait(1000):
            self.sendTerminateToThread(self.backup_controller)

        if not self.gvfsControlsMounts:
            self.udisks2MonitorThread.quit()
            self.udisks2MonitorThread.wait()
            self.cameraHotplugThread.quit()
            self.cameraHotplugThread.wait()
        else:
            del self.gvolumeMonitor

        if not version_check_disabled():
            self.newVersionThread.quit()
            self.newVersionThread.wait(100)

        self.sendStopToThread(self.thumbnail_deamon_controller)
        self.thumbnaildaemonmqThread.quit()
        if not self.thumbnaildaemonmqThread.wait(2000):
            self.sendTerminateToThread(self.thumbnail_deamon_controller)

        # Tell logging thread to stop: uses slightly different approach
        # than other threads
        stop_process_logging_manager(info_port=self.logging_port)
        self.loggermqThread.quit()
        self.loggermqThread.wait()

        self.watchedDownloadDirs.closeWatch()

        self.cleanAllTempDirs()
        logging.debug("Cleaning any device cache dirs and sample video")
        self.devices.delete_cache_dirs_and_sample_video()
        tc = ThumbnailCacheSql(create_table_if_not_exists=False)
        logging.debug("Cleaning up Thumbnail cache")
        tc.cleanup_cache(days=self.prefs.keep_thumbnails_days)

        Notify.uninit()

        self.close_event_run = True

        logging.debug("Accepting close event")
        event.accept()

    def getIconsAndEjectableForMount(self, mount: QStorageInfo) -> Tuple[List[str], bool]:
        """
        Given a mount, get the icon names suggested by udev or
        GVFS, and  determine whether the mount is ejectable or not.
        :param mount:  the mount to check
        :return: icon names and eject boolean
        :rtype Tuple[str, bool]
        """
        if self.gvfsControlsMounts:
            iconNames, canEject = self.gvolumeMonitor.getProps(mount.rootPath())
        else:
            # get the system device e.g. /dev/sdc1
            systemDevice = bytes(mount.device()).decode()
            iconNames, canEject = self.udisks2Monitor.get_device_props(systemDevice)
        return iconNames, canEject

    def addToDeviceDisplay(self, device: Device, scan_id: int) -> None:
        self.mapModel(scan_id).addDevice(scan_id, device)
        self.adjustLeftPanelSliderHandles()
        # Resize the "This Computer" view after a device has been added
        # If not done, the widget geometry will not be updated to reflect
        # the new view.
        if device.device_type == DeviceType.path:
            self.thisComputerView.updateGeometry()

    @pyqtSlot()
    def cameraAdded(self) -> None:
        if not self.prefs.device_autodetection:
            logging.debug("Ignoring camera as device auto detection is off")
        else:
            logging.debug("Assuming camera will not be mounted: immediately proceeding with scan")
        self.searchForCameras()

    @pyqtSlot()
    def cameraRemoved(self) -> None:
        """
        Handle the possible removal of a camera by comparing the
        cameras the OS knows about compared to the cameras we are
        tracking. Remove tracked cameras if they are not on the OS.

        We need this brute force method because I don't know if it's
        possible to query GIO or udev to return the info needed by
        libgphoto2
        """

        logging.debug("Examining system for removed camera")
        sc = autodetect_cameras(self.gp_context)
        system_cameras = ((model, port) for model, port in sc if not port.startswith('disk:'))
        kc = self.devices.cameras.items()
        known_cameras = ((model, port) for port, model in kc)
        removed_cameras = set(known_cameras) - set(system_cameras)
        for model, port in removed_cameras:
            scan_id = self.devices.scan_id_from_camera_model_port(model, port)
            if scan_id is None:
                logging.debug("The camera with scan id %s was already removed", scan_id)
            else:
                device = self.devices[scan_id]
                # Don't log a warning when the camera was removed while the user was being
                # informed it was locked or inaccessible
                show_warning = not device in self.prompting_for_user_action
                self.removeDevice(scan_id=scan_id, show_warning=show_warning)

        if removed_cameras:
            self.setDownloadCapabilities()

    @pyqtSlot()
    def noGVFSAutoMount(self) -> None:
        """
        In Gnome like environment we rely on Gnome automatically
        mounting cameras and devices with file systems. But sometimes
        it will not automatically mount them, for whatever reason.
        Try to handle those cases.
        """
        #TODO Implement noGVFSAutoMount()
        # however, I have no idea under what circumstances it is called
        logging.error("Implement noGVFSAutoMount()")

    @pyqtSlot()
    def cameraMounted(self) -> None:
        if have_gio:
            self.searchForCameras()

    @pyqtSlot(str)
    def cameraVolumeAdded(self, path):
        assert self.gvfsControlsMounts
        self.searchForCameras()

    def unmountCameraToEnableScan(self, model: str,
                                  port: str,
                                  on_startup: bool) -> bool:
        """
        Possibly "unmount" a camera or phone controlled by GVFS so it can be scanned

        :param model: camera model
        :param port: port used by camera
        :param on_startup: if True, the unmount is occurring during
         the program's startup phase
        :return: True if unmount operation initiated, else False
        """

        if self.gvfsControlsMounts:
            self.devices.cameras_to_gvfs_unmount_for_scan[port] = model
            unmounted = self.gvolumeMonitor.unmountCamera(
                model=model, port=port, on_startup=on_startup
            )
            if unmounted:
                logging.debug("Successfully unmounted %s", model)
                return True
            else:
                logging.debug("%s was not already mounted", model)
                del self.devices.cameras_to_gvfs_unmount_for_scan[port]
        return False

    @pyqtSlot(bool, str, str, bool, bool)
    def cameraUnmounted(self, result: bool,
                        model: str,
                        port: str,
                        download_started: bool,
                        on_startup: bool) -> None:
        """
        Handle the attempt to unmount a GVFS mounted camera.

        Note: cameras that have not yet been scanned do not yet have a scan_id assigned!
        An obvious point, but easy to forget.

        :param result: result from the GVFS operation
        :param model: camera model
        :param port: camera port
        :param download_started: whether the unmount happened because a download
         was initiated
        :param on_startup: if the unmount happened on a device during program startup
        """

        if not download_started:
            assert self.devices.cameras_to_gvfs_unmount_for_scan[port] == model
            del self.devices.cameras_to_gvfs_unmount_for_scan[port]
            if result:
                self.startCameraScan(model=model, port=port, on_startup=on_startup)
            else:
                # Get the camera's short model name, instead of using the exceptionally
                # long name that gphoto2 can sometimes use. Get the icon too.
                camera = Device()
                camera.set_download_from_camera(model, port)

                logging.debug(
                    "Not scanning %s because it could not be unmounted", camera.display_name
                )

                # Translators: %(variable)s represents Python code, not a plural of the term
                # variable. You must keep the %(variable)s untranslated, or the program will
                # crash.
                # Translators: please do not change HTML codes like <br>, <i>, </i>, or <b>, </b>
                # etc.
                message = _(
                    '<b>The %(camera)s cannot be scanned because it cannot be '
                    'unmounted.</b><br><br>You can close any other application (such as a '
                    'file browser) that is using it and try again. If that does not work, '
                    'unplug the %(camera)s from the computer and plug it in again.'
                ) % dict(camera=camera.display_name)

                # Show the main window if it's not yet visible
                self.showMainWindow()
                msgBox = standardMessageBox(
                    message=message, rich_text=True, standardButtons=QMessageBox.Ok,
                    iconPixmap=camera.get_pixmap()
                )
                msgBox.exec()
        else:
            # A download was initiated

            scan_id = self.devices.scan_id_from_camera_model_port(model, port)
            self.devices.cameras_to_gvfs_unmount_for_download.remove(scan_id)
            if result:
                if not self.devices.download_start_blocked():
                    self.startDownloadPhase2()
            else:
                camera = self.devices[scan_id]
                display_name = camera.display_name

                title = _('Rapid Photo Downloader')
                # Translators: %(variable)s represents Python code, not a plural of the term
                # variable. You must keep the %(variable)s untranslated, or the program will
                # crash.
                # Translators: please do not change HTML codes like <br>, <i>, </i>, or <b>, </b>
                # etc.
                message = _(
                    '<b>The download cannot start because the %(camera)s cannot be '
                    'unmounted.</b><br><br>You '
                    'can close any other application (such as a file browser) that is '
                    'using it and try again. If that '
                    'does not work, unplug the %(camera)s from the computer and plug '
                    'it in again, and choose which files you want to download from it.'
                ) % dict(camera=display_name)
                msgBox = QMessageBox(QMessageBox.Warning, title, message, QMessageBox.Ok)
                msgBox.setIconPixmap(camera.get_pixmap())
                msgBox.exec_()

    def searchForCameras(self, on_startup: bool=False) -> None:
        """
        Detect using gphoto2 any cameras attached to the computer.

        Initiates unmount of cameras that are mounted by GIO/GVFS.

        :param on_startup: if True, the search is occurring during
         the program's startup phase
        """

        if self.prefs.device_autodetection:
            cameras = autodetect_cameras(self.gp_context)
            for model, port in cameras:
                if port in self.devices.cameras_to_gvfs_unmount_for_scan:
                    assert self.devices.cameras_to_gvfs_unmount_for_scan[port] == model
                    logging.debug("Already unmounting %s", model)
                elif self.devices.known_camera(model, port):
                    logging.debug("Camera %s is known", model)
                elif self.devices.user_marked_camera_as_ignored(model, port):
                    logging.debug("Ignoring camera marked as removed by user %s", model)
                elif not port.startswith('disk:'):
                    device = Device()
                    device.set_download_from_camera(model, port)
                    if device.udev_name in self.prefs.camera_blacklist:
                        logging.debug("Ignoring blacklisted camera %s", model)
                    else:
                        logging.debug("Detected %s on port %s", model, port)
                        # almost always, libgphoto2 cannot access a camera when
                        # it is mounted by another process, like Gnome's GVFS
                        # or any other system. Before attempting to scan the
                        # camera, check to see if it's mounted and if so,
                        # unmount it. Unmounting is asynchronous.
                        if not self.unmountCameraToEnableScan(
                                model=model, port=port, on_startup=on_startup):
                            self.startCameraScan(model=model, port=port, on_startup=on_startup)

    def startCameraScan(self, model: str,
                        port: str,
                        on_startup: bool=False) -> None:
        """
        Initiate the scan of an unmounted camera

        :param model: camera model
        :param port:  camera port
        :param on_startup: if True, the scan is occurring during
         the program's startup phase
        """

        device = Device()
        device.set_download_from_camera(model, port)
        self.startDeviceScan(device=device, on_startup=on_startup)

    def startDeviceScan(self, device: Device,  on_startup: bool=False) -> None:
        """
        Initiate the scan of a device (camera, this computer path, or external device)

        :param device: device to scan
        :param on_startup: if True, the scan is occurring during
         the program's startup phase
        """

        scan_id = self.devices.add_device(device=device, on_startup=on_startup)
        logging.debug("Assigning scan id %s to %s", scan_id, device.name())
        self.thumbnailModel.addOrUpdateDevice(scan_id)
        self.addToDeviceDisplay(device, scan_id)
        self.updateSourceButton()
        scan_arguments = ScanArguments(
            device=device,
            ignore_other_types=self.ignore_other_photo_types,
            log_gphoto2=self.log_gphoto2,
        )
        self.sendStartWorkerToThread(self.scan_controller, worker_id=scan_id, data=scan_arguments)
        self.devices.set_device_state(scan_id, DeviceState.scanning)
        self.setDownloadCapabilities()
        self.updateProgressBarState()
        self.displayMessageInStatusBar()

        if not on_startup and self.thumbnailModel.anyCompletedDownloads():

            if self.prefs.completed_downloads == int(CompletedDownloads.prompt):
                logging.info("Querying whether to clear completed downloads")
                counter = self.thumbnailModel.getFileDownloadsCompleted()

                numbers = counter.file_types_present_details(singular_natural=True).capitalize()
                plural = sum(counter.values()) > 1
                if plural:
                    title = _('Completed Downloads Present')
                    body = _(
                        '%s whose download have completed are displayed.'
                    ) % numbers
                    question = _('Do you want to clear the completed downloads?')
                else:
                    title = _('Completed Download Present')
                    body = _(
                        '%s whose download has completed is displayed.'
                    ) % numbers
                    question = _('Do you want to clear the completed download?')
                message = "<b>{}</b><br><br>{}<br><br>{}".format(title, body, question)

                questionDialog = RememberThisDialog(
                    message=message,
                    icon=':/rapid-photo-downloader.svg',
                    remember=RememberThisMessage.do_not_ask_again,
                    parent=self
                )

                clear = questionDialog.exec_()
                if clear:
                    self.thumbnailModel.clearCompletedDownloads()

                if questionDialog.remember:
                    if clear:
                        self.prefs.completed_downloads = int(CompletedDownloads.clear)
                    else:
                        self.prefs.completed_downloads = int(CompletedDownloads.keep)

            elif self.prefs.completed_downloads == int(CompletedDownloads.clear):
                logging.info("Clearing completed downloads")
                self.thumbnailModel.clearCompletedDownloads()
            else:
                logging.info("Keeping completed downloads")

    def partitionValid(self, mount: QStorageInfo) -> bool:
        """
        A valid partition is one that is:
        1) available
        2) the mount name should not be blacklisted
        :param mount: the mount point to check
        :return: True if valid, False otherwise
        """
        if mount.isValid() and mount.isReady():
            if mount.displayName() in self.prefs.volume_blacklist:
                logging.info("blacklisted device %s ignored", mount.displayName())
                return False
            else:
                return True
        return False

    def shouldScanMount(self, mount: QStorageInfo) -> bool:
        if self.prefs.device_autodetection:
            path = mount.rootPath()
            if (not self.prefs.scan_specific_folders or has_one_or_more_folders(
                                                path=path, folders=self.prefs.folders_to_scan)):
                if not self.devices.user_marked_volume_as_ignored(path):
                    return True
                else:
                    logging.debug(
                        'Not scanning volume with path %s because it was set to be temporarily '
                        'ignored', path
                    )
            else:
                logging.debug(
                    'Not scanning volume with path %s because it lacks a folder at the base '
                    'level that indicates it should be scanned', path
                )
        return False

    def prepareNonCameraDeviceScan(self, device: Device, on_startup: bool=False) -> None:
        """
        Initiates a device scan for volume.

        If non-DCIM device scans are enabled, and the device is not whitelisted
        (determined by the display name), then the user is prompted whether to download
        from the device.

        :param device: device to scan
        :param on_startup: if True, the search is occurring during
         the program's startup phase
        """

        if not self.devices.known_device(device):
            if (self.scanEvenIfNoFoldersLikeDCIM() and
                    not device.display_name in self.prefs.volume_whitelist):
                logging.debug("Prompting whether to use device %s", device.display_name)
                # prompt user to see if device should be used or not
                self.showMainWindow()
                message = _(
                    'Do you want to download photos and videos from the device <i>%('
                    'device)s</i>?'
                ) % dict(device=device.display_name)
                use = RememberThisDialog(
                    message=message, icon=device.get_pixmap(),
                    remember=RememberThisMessage.remember_choice,
                    parent=self, title=device.display_name
                )
                if use.exec():
                    if use.remember:
                        logging.debug("Whitelisting device %s", device.display_name)
                        self.prefs.add_list_value(key='volume_whitelist', value=device.display_name)
                    self.startDeviceScan(device=device, on_startup=on_startup)
                else:
                    logging.debug("Device %s rejected as a download device", device.display_name)
                    if use.remember and device.display_name not in self.prefs.volume_blacklist:
                        logging.debug("Blacklisting device %s", device.display_name)
                        self.prefs.add_list_value(key='volume_blacklist', value=device.display_name)
            else:
                self.startDeviceScan(device=device, on_startup=on_startup)

    @pyqtSlot(str, list, bool)
    def partitionMounted(self, path: str, iconNames: List[str], canEject: bool) -> None:
        """
        Setup devices from which to download from and backup to, and
        if relevant start scanning them

        :param path: the path of the mounted partition
        :param iconNames: a list of names of icons used in themed icons
        associated with this partition
        :param canEject: whether the partition can be ejected or not
        """

        assert path in mountPaths()

        if self.monitorPartitionChanges():
            mount = QStorageInfo(path)
            if self.partitionValid(mount):
                backup_file_type = self.isBackupPath(path)

                if backup_file_type is not None:
                    if path not in self.backup_devices:
                        device = BackupDevice(mount=mount, backup_type=backup_file_type)
                        self.backup_devices[path] = device
                        self.addDeviceToBackupManager(path)
                        self.download_tracker.set_no_backup_devices(
                            len(self.backup_devices.photo_backup_devices),
                            len(self.backup_devices.video_backup_devices)
                        )
                        self.displayMessageInStatusBar()
                        self.backupPanel.addBackupVolume(
                            mount_details=self.backup_devices.get_backup_volume_details(path)
                        )
                        if self.prefs.backup_device_autodetection:
                            self.backupPanel.updateExample()

                elif self.shouldScanMount(mount):
                    device = Device()
                    device.set_download_from_volume(
                        path, mount.displayName(), iconNames, canEject, mount
                    )
                    self.prepareNonCameraDeviceScan(device)

    @pyqtSlot(str)
    def partitionUmounted(self, path: str) -> None:
        """
        Handle the unmounting of partitions by the system / user.

        :param path: the path of the partition just unmounted
        """
        if not path:
            return

        if self.devices.known_path(path, DeviceType.volume):
            # four scenarios -
            # the mount is being scanned
            # the mount has been scanned but downloading has not yet started
            # files are being downloaded from mount
            # files have finished downloading from mount
            scan_id = self.devices.scan_id_from_path(path, DeviceType.volume)
            self.removeDevice(scan_id=scan_id)

        elif path in self.backup_devices:
            self.removeBackupDevice(path)
            self.backupPanel.removeBackupVolume(path=path)
            self.displayMessageInStatusBar()
            self.download_tracker.set_no_backup_devices(
                len(self.backup_devices.photo_backup_devices),
                len(self.backup_devices.video_backup_devices)
            )
            if self.prefs.backup_device_autodetection:
                self.backupPanel.updateExample()

        self.setDownloadCapabilities()

    def removeDevice(self, scan_id: int,
                     show_warning: bool=True,
                     adjust_temporal_proximity: bool=True,
                     ignore_in_this_program_instantiation: bool=False) -> None:
        """
        Remove a device from internal tracking and display.

        :param scan_id: scan id of device to remove
        :param show_warning: log warning if the device was having
         something done to it e.g. scan
        :param adjust_temporal_proximity: if True, update the temporal
         proximity table to reflect device removal
        :param ignore_in_this_program_instantiation: don't scan this
         device again during this instance of the program being run
        """

        assert scan_id is not None

        if scan_id in self.devices:
            device = self.devices[scan_id]
            device_state = self.deviceState(scan_id)

            if show_warning:
                if device_state == DeviceState.scanning:
                    logging.warning("Removed device %s was being scanned", device.name())
                elif device_state == DeviceState.downloading:
                    logging.error("Removed device %s was being downloaded from", device.name())
                elif device_state == DeviceState.thumbnailing:
                    logging.warning(
                        "Removed device %s was having thumbnails generated", device.name()
                    )
                else:
                    logging.info("Device removed: %s", device.name())
            else:
                logging.debug("Device removed: %s", device.name())

            if device in self.prompting_for_user_action:
                self.prompting_for_user_action[device].reject()

            files_removed = self.thumbnailModel.clearAll(
                scan_id=scan_id, keep_downloaded_files=True
            )
            self.mapModel(scan_id).removeDevice(scan_id)

            was_downloading = self.downloadIsRunning()

            if device_state == DeviceState.scanning:
                self.sendStopWorkerToThread(self.scan_controller, scan_id)
            elif device_state == DeviceState.downloading:
                self.sendStopWorkerToThread(self.copy_controller, scan_id)
                self.download_tracker.device_removed_mid_download(scan_id, device.display_name)
                del self.time_remaining[scan_id]
                self.notifyDownloadedFromDevice(scan_id=scan_id)
            # TODO need correct check for "is thumbnailing", given is now asynchronous
            elif device_state == DeviceState.thumbnailing:
                self.thumbnailModel.terminateThumbnailGeneration(scan_id)

            if ignore_in_this_program_instantiation:
                self.devices.ignore_device(scan_id=scan_id)

            self.folder_preview_manager.remove_folders_for_device(scan_id=scan_id)

            del self.devices[scan_id]
            self.adjustLeftPanelSliderHandles()

            if device.device_type == DeviceType.path:
                self.thisComputer.setViewVisible(False)

            self.updateSourceButton()
            self.setDownloadCapabilities()

            if adjust_temporal_proximity:
                state = self.proximityStatePostDeviceRemoval()
                if state == TemporalProximityState.empty:
                    self.temporalProximity.setState(TemporalProximityState.empty)
                elif files_removed:
                    self.generateTemporalProximityTableData("a download source was removed")
                elif self.temporalProximity.state == TemporalProximityState.pending:
                    self.generateTemporalProximityTableData(
                        "a download source was removed and a build is pending"
                    )

            self.logState()
            self.updateProgressBarState()
            self.displayMessageInStatusBar()

            # Reset Download button from "Pause" to "Download"
            if was_downloading and not self.downloadIsRunning():
                self.setDownloadActionLabel()

    def rescanDevice(self, scan_id: int) -> None:
        """
        Remove a device and scan it again.

        :param scan_id: scan id of the device
        """

        device = self.devices[scan_id]
        logging.debug("Rescanning %s", device.display_name)
        self.removeDevice(scan_id=scan_id)
        if device.device_type == DeviceType.camera:
            self.startCameraScan(device.camera_model, device.camera_port)
        else:
            if device.device_type == DeviceType.path:
                self.thisComputer.setViewVisible(True)
            self.startDeviceScan(device=device)

    def rescanDevicesAndComputer(self, ignore_cameras: bool, rescan_path: bool) -> None:
        """
        After a preference change, rescan already scanned devices
        :param ignore_cameras: if True, don't rescan cameras
        :param rescan_path: if True, include manually specified paths
         (i.e. This Computer)  
        """

        if rescan_path:
            logging.info("Rescanning all paths and devices")
        if ignore_cameras:
            logging.info("Rescanning non camera devices")

        # Collect the scan ids to work on - don't modify the
        # collection of devices in place!
        scan_ids = []
        for scan_id in self.devices:
            device = self.devices[scan_id]
            if not ignore_cameras or device.device_type == DeviceType.volume:
                scan_ids.append(scan_id)
            elif rescan_path and device.device_type == DeviceType.path:
                scan_ids.append(scan_id)

        for scan_id in scan_ids:
            self.rescanDevice(scan_id=scan_id)

    def searchForDevicesAgain(self) -> None:
        """
        Called after a preference change to only_external_mounts
        """

        # only scan again if the new pref value is more permissive than the former
        # (don't remove existing devices)
        if not self.prefs.only_external_mounts:
            logging.debug("Searching for new volumes to scan...")
            self.setupNonCameraDevices(scanning_again=True)
            logging.debug("... finished searching for volumes to scan")


    def blacklistDevice(self, scan_id: int) -> None:
        """
        Query user if they really want to to permanently ignore a camera or
        volume. If they do, the device is removed and blacklisted.

        :param scan_id: scan id of the device
        """

        device = self.devices[scan_id]
        if device.device_type == DeviceType.camera:
            text = _("<b>Do you want to ignore the %s whenever this program is run?</b>")
            text = text % device.display_name
            info_text = _(
                "All cameras, phones and tablets with the same model name will be ignored."
            )
        else:
            assert device.device_type == DeviceType.volume
            text = _("<b>Do you want to ignore the device %s whenever this program is run?</b>")
            text = text % device.display_name
            info_text = _("Any device with the same name will be ignored.")

        msgbox = QMessageBox()
        msgbox.setWindowTitle(_("Rapid Photo Downloader"))
        msgbox.setIcon(QMessageBox.Question)
        msgbox.setText(text)
        msgbox.setTextFormat(Qt.RichText)
        msgbox.setInformativeText(info_text)
        msgbox.setStandardButtons(QMessageBox.Yes|QMessageBox.No)
        if msgbox.exec() == QMessageBox.Yes:
            if device.device_type == DeviceType.camera:
                self.prefs.add_list_value(key='camera_blacklist', value=device.udev_name)
                logging.debug('Added %s to camera blacklist',device.udev_name)
            else:
                self.prefs.add_list_value(key='volume_blacklist', value=device.display_name)
                logging.debug('Added %s to volume blacklist', device.display_name)
            self.removeDevice(scan_id=scan_id)

    def logState(self) -> None:
        self.devices.logState()
        self.thumbnailModel.logState()
        self.deviceModel.logState()
        self.thisComputerModel.logState()

    def setupBackupDevices(self) -> None:
        """
        Setup devices to back up to.

        Includes both auto detected back up devices, and manually
        specified paths.
        """
        if self.prefs.backup_device_autodetection:
            for mount in self.validMounts.mountedValidMountPoints():
                if self.partitionValid(mount):
                    path = mount.rootPath()
                    backup_type = self.isBackupPath(path)
                    if backup_type is not None:
                        self.backup_devices[path] = BackupDevice(
                            mount=mount, backup_type=backup_type
                        )
                        self.addDeviceToBackupManager(path)
            self.backupPanel.updateExample()
        else:
            self.setupManualBackup()
            for path in self.backup_devices:
                self.addDeviceToBackupManager(path)

        self.download_tracker.set_no_backup_devices(
            len(self.backup_devices.photo_backup_devices),
            len(self.backup_devices.video_backup_devices))

        self.backupPanel.setupBackupDisplay()

    def removeBackupDevice(self, path: str) -> None:
        device_id = self.backup_devices.device_id(path)
        self.sendStopWorkerToThread(self.backup_controller, worker_id=device_id)
        del self.backup_devices[path]

    def resetupBackupDevices(self) -> None:
        """
        Change backup preferences in response to preference change.

        Assumes backups may have already been setup.
        """

        try:
            assert not self.downloadIsRunning()
        except AssertionError:
            logging.critical("Backup devices should never be reset when a download is occurring")
            return

        logging.info("Resetting backup devices configuration...")
        # Clear all existing backup devices
        for path in self.backup_devices.all_paths():
            self.removeBackupDevice(path)
        self.download_tracker.set_no_backup_devices(0, 0)
        self.backupPanel.resetBackupDisplay()

        self.setupBackupDevices()
        self.setDownloadCapabilities()
        logging.info("...backup devices configuration is reset")

    def setupNonCameraDevices(self, on_startup: bool=False, scanning_again: bool=False) -> None:
        """
        Setup devices from which to download and initiates their scan.

        :param on_startup: if True, the search is occurring during
         the program's startup phase
        :param scanning_again: if True, the search is occurring after a preference
         value change, where devices may have already been scanned.
        """

        if not self.prefs.device_autodetection:
            return

        mounts = [] # type: List[QStorageInfo]
        for mount in self.validMounts.mountedValidMountPoints():
            if self.partitionValid(mount):
                path = mount.rootPath()

                if scanning_again and \
                        self.devices.known_path(path=path, device_type=DeviceType.volume):
                    logging.debug(
                        "Will not scan %s, because it's associated with an existing device",
                        mount.displayName()
                    )
                    continue

                if path not in self.backup_devices and self.shouldScanMount(mount):
                    logging.debug("Will scan %s", mount.displayName())
                    mounts.append(mount)
                else:
                    logging.debug("Will not scan %s", mount.displayName())

        for mount in mounts:
            icon_names, can_eject = self.getIconsAndEjectableForMount(mount)
            device = Device()
            device.set_download_from_volume(
                mount.rootPath(), mount.displayName(), icon_names, can_eject, mount
            )
            self.prepareNonCameraDeviceScan(device=device, on_startup=on_startup)

    def setupManualPath(self, on_startup: bool=False) -> None:
        """
        Setup This Computer path from which to download and initiates scan.

        :param on_startup: if True, the setup is occurring during
         the program's startup phase
        """

        if not self.prefs.this_computer_source:
            return

        if self.prefs.this_computer_path:
            if not self.confirmManualDownloadLocation():
                logging.debug(
                    "This Computer path %s rejected as download source",
                    self.prefs.this_computer_path
                )
                self.prefs.this_computer_path = ''
                self.thisComputer.setViewVisible(False)
                return

            # user manually specified the path from which to download
            path = self.prefs.this_computer_path

            if path:
                if os.path.isdir(path) and os.access(path, os.R_OK):
                    logging.debug("Using This Computer path %s", path)
                    device = Device()
                    device.set_download_from_path(path)
                    self.startDeviceScan(device=device, on_startup=on_startup)
                else:
                    logging.error("This Computer download path is invalid: %s", path)
            else:
                logging.warning("This Computer download path is not specified")

    def addDeviceToBackupManager(self, path: str) -> None:
        device_id = self.backup_devices.device_id(path)
        self.backup_controller.send_multipart(create_inproc_msg(b'START_WORKER',
                                worker_id=device_id,
                                data=BackupArguments(path, self.backup_devices.name(path))))

    def setupManualBackup(self) -> None:
        """
        Setup backup devices that the user has manually specified.

        Depending on the folder the user has chosen, the paths for
        photo and video backup will either be the same or they will
        differ.

        Because the paths are manually specified, there is no mount
        associated with them.
        """

        backup_photo_location = self.prefs.backup_photo_location
        backup_video_location = self.prefs.backup_video_location

        if not self.manualBackupPathAvailable(backup_photo_location):
            logging.warning("Photo backup path unavailable: %s", backup_photo_location)
        if not self.manualBackupPathAvailable(backup_video_location):
            logging.warning("Video backup path unavailable: %s", backup_video_location)

        if backup_photo_location != backup_video_location:
            backup_photo_device =  BackupDevice(mount=None, backup_type=BackupLocationType.photos)
            backup_video_device = BackupDevice(mount=None, backup_type=BackupLocationType.videos)
            self.backup_devices[backup_photo_location] = backup_photo_device
            self.backup_devices[backup_video_location] = backup_video_device

            logging.info("Backing up photos to %s", backup_photo_location)
            logging.info("Backing up videos to %s", backup_video_location)
        else:
            # videos and photos are being backed up to the same location
            backup_device = BackupDevice(mount=None,
                     backup_type=BackupLocationType.photos_and_videos)
            self.backup_devices[backup_photo_location] = backup_device

            logging.info("Backing up photos and videos to %s", backup_photo_location)

    def isBackupPath(self, path: str) -> Optional[BackupLocationType]:
        """
        Checks to see if backups are enabled and path represents a
        valid backup location. It must be writeable.

        Checks against user preferences.

        :return The type of file that should be backed up to the path,
        else if nothing should be, None
        """

        if self.prefs.backup_files:
            if self.prefs.backup_device_autodetection:
                # Determine if the auto-detected backup device is
                # to be used to backup only photos, or videos, or both.
                # Use the presence of a corresponding directory to
                # determine this.
                # The directory must be writable.
                photo_path = os.path.join(path, self.prefs.photo_backup_identifier)
                p_backup = os.path.isdir(photo_path) and os.access(photo_path, os.W_OK)
                video_path = os.path.join(path, self.prefs.video_backup_identifier)
                v_backup = os.path.isdir(video_path) and os.access(video_path, os.W_OK)
                if p_backup and v_backup:
                    logging.info("Photos and videos will be backed up to %s", path)
                    return BackupLocationType.photos_and_videos
                elif p_backup:
                    logging.info("Photos will be backed up to %s", path)
                    return BackupLocationType.photos
                elif v_backup:
                    logging.info("Videos will be backed up to %s", path)
                    return BackupLocationType.videos
            elif path == self.prefs.backup_photo_location:
                # user manually specified the path
                if self.manualBackupPathAvailable(path):
                    return BackupLocationType.photos
            elif path == self.prefs.backup_video_location:
                # user manually specified the path
                if self.manualBackupPathAvailable(path):
                    return BackupLocationType.videos
            return None

    def manualBackupPathAvailable(self, path: str) -> bool:
        return os.access(path, os.W_OK)

    def monitorPartitionChanges(self) -> bool:
        """
        If the user is downloading from a manually specified location,
        and is not using any automatically detected backup devices,
        then there is no need to monitor for devices with filesystems
        being added or removed
        :return: True if should monitor, False otherwise
        """
        return (self.prefs.device_autodetection or
                self.prefs.backup_device_autodetection)

    @pyqtSlot(str)
    def watchedFolderChange(self, path: str) -> None:
        """
        Handle case where a download folder has been removed or altered

        :param path: watched path
        """

        logging.debug("Change in watched folder %s; validating download destinations", path)
        valid = True
        if self.prefs.photo_download_folder and not validate_download_folder(
                self.prefs.photo_download_folder).valid:
            valid = False
            logging.debug(
                "Photo download destination %s is now invalid", self.prefs.photo_download_folder
            )
            self.handleInvalidDownloadDestination(file_type=FileType.photo, do_update=False)

        if self.prefs.video_download_folder and not validate_download_folder(
                self.prefs.video_download_folder).valid:
            valid = False
            logging.debug(
                "Video download destination %s is now invalid", self.prefs.video_download_folder
            )
            self.handleInvalidDownloadDestination(file_type=FileType.video, do_update=False)

        if not valid:
            self.watchedDownloadDirs.updateWatchPathsFromPrefs(self.prefs)
            self.folder_preview_manager.change_destination()
            self.setDownloadCapabilities()

    def confirmManualDownloadLocation(self) -> bool:
        """
        Queries the user to ask if they really want to download from locations
        that could take a very long time to scan. They can choose yes or no.

        Returns True if yes or there was no need to ask the user, False if the
        user said no.
        """

        self.showMainWindow()
        path = self.prefs.this_computer_path
        if path in (
                '/media', '/run', os.path.expanduser('~'), '/', '/bin', '/boot', '/dev',
                '/lib', '/lib32', '/lib64', '/mnt', '/opt', '/sbin', '/snap', '/sys', '/tmp',
                '/usr', '/var', '/proc'):

            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            message = "<b>" + _(
                "Downloading from %(location)s on This Computer."
            ) % dict(location=make_html_path_non_breaking(path)
            ) + "</b><br><br>" + _(
                "Do you really want to download from here?<br><br>On some systems, scanning this "
                "location can take a very long time."
            )
            msgbox = standardMessageBox(
                message=message, rich_text=True,
                standardButtons=QMessageBox.Yes | QMessageBox.No,
            )
            return msgbox.exec() == QMessageBox.Yes
        return True

    def scanEvenIfNoFoldersLikeDCIM(self) -> bool:
        """
        Determines if partitions should be scanned even if there is
        no specific folder like a DCIM folder present in the base folder of the file system.

        :return: True if scans of such partitions should occur, else
        False
        """

        return self.prefs.device_autodetection and not self.prefs.scan_specific_folders

    def displayMessageInStatusBar(self) -> None:
        """
        Displays message on status bar.

        Notifies user if scanning or thumbnailing.

        If neither scanning or thumbnailing, displays:
        1. files checked for download
        2. total number files available
        3. how many not shown (user chose to show only new files)
        """

        if self.downloadIsRunning():
            if self.download_paused:
                downloading = self.devices.downloading_from()
                # Translators - in the middle is a unicode em dash - please retain it
                # This string is displayed in the status bar when the download is paused
                # Translators: %(variable)s represents Python code, not a plural of the term
                # variable. You must keep the %(variable)s untranslated, or the program will
                # crash.
                msg = '%(downloading_from)s — download paused' % dict(downloading_from=downloading)
            else:
                # status message updates while downloading are handled in another function
                return
        elif self.devices.thumbnailing:
            devices = [self.devices[scan_id].display_name for scan_id in self.devices.thumbnailing]
            msg = _("Generating thumbnails for %s") % make_internationalized_list(devices)
        elif self.devices.scanning:
            devices = [self.devices[scan_id].display_name for scan_id in self.devices.scanning]
            msg = _("Scanning %s") % make_internationalized_list(devices)
        else:
            files_avilable = self.thumbnailModel.getNoFilesAvailableForDownload()

            if sum(files_avilable.values()) != 0:
                files_to_download = self.thumbnailModel.getNoFilesMarkedForDownload()
                files_avilable_sum = files_avilable.summarize_file_count()[0]
                files_hidden = self.thumbnailModel.getNoHiddenFiles()

                if files_hidden:
                    # Translators: %(variable)s represents Python code, not a plural of the term
                    # variable. You must keep the %(variable)s untranslated, or the program will
                    # crash.
                    files_checked = _(
                        '%(number)s of %(available files)s checked for download (%(hidden)s hidden)'
                    ) % {
                        'number': thousands(files_to_download),
                        'available files': files_avilable_sum,
                        'hidden': files_hidden
                    }
                else:
                    # Translators: %(variable)s represents Python code, not a plural of the term
                    # variable. You must keep the %(variable)s untranslated, or the program will
                    # crash.
                    files_checked = _(
                        '%(number)s of %(available files)s checked for download'
                    ) % {
                        'number': thousands(files_to_download),
                        'available files': files_avilable_sum
                    }
                msg = files_checked
            else:
                msg = ''
        self.statusBar().showMessage(msg)


class QtSingleApplication(QApplication):
    """
    Taken from
    http://stackoverflow.com/questions/12712360/qtsingleapplication
    -for-pyside-or-pyqt
    """

    messageReceived = pyqtSignal(str)

    def __init__(self, programId: str, *argv) -> None:
        super().__init__(*argv)
        self._id = programId
        self._activationWindow = None # type: RapidWindow
        self._activateOnMessage = False # type: bool

        # Is there another instance running?
        self._outSocket = QLocalSocket()  # type: QLocalSocket
        self._outSocket.connectToServer(self._id)
        self._isRunning = self._outSocket.waitForConnected() # type: bool

        self._outStream = None  # type: QTextStream
        self._inSocket  = None
        self._inStream  = None  # type: QTextStream
        self._server    = None

        if self._isRunning:
            # Yes, there is.
            self._outStream = QTextStream(self._outSocket)
            self._outStream.setCodec('UTF-8')
        else:
            # No, there isn't, at least not properly.
            # Cleanup any past, crashed server.
            error = self._outSocket.error()
            if error == QLocalSocket.ConnectionRefusedError:
                self.close()
                QLocalServer.removeServer(self._id)
            self._outSocket = None
            self._server = QLocalServer()
            self._server.listen(self._id)
            self._server.newConnection.connect(self._onNewConnection)

    def close(self) -> None:
        if self._inSocket:
            self._inSocket.disconnectFromServer()
        if self._outSocket:
            self._outSocket.disconnectFromServer()
        if self._server:
            self._server.close()

    def isRunning(self) -> bool:
        return self._isRunning

    def id(self) -> str:
        return self._id

    def activationWindow(self) -> RapidWindow:
        return self._activationWindow

    def setActivationWindow(self, activationWindow: RapidWindow,
                            activateOnMessage: bool = True) -> None:
        self._activationWindow = activationWindow
        self._activateOnMessage = activateOnMessage

    def activateWindow(self) -> None:
        if not self._activationWindow:
            return
        self._activationWindow.setWindowState(
            self._activationWindow.windowState() & ~Qt.WindowMinimized)
        self._activationWindow.raise_()
        self._activationWindow.activateWindow()

    def sendMessage(self, msg) -> bool:
        if not self._outStream:
            return False
        self._outStream << msg << '\n'
        self._outStream.flush()
        return self._outSocket.waitForBytesWritten()

    def _onNewConnection(self) -> None:
        if self._inSocket:
            self._inSocket.readyRead.disconnect(self._onReadyRead)
        self._inSocket = self._server.nextPendingConnection()
        if not self._inSocket:
            return
        self._inStream = QTextStream(self._inSocket)
        self._inStream.setCodec('UTF-8')
        self._inSocket.readyRead.connect(self._onReadyRead)
        if self._activateOnMessage:
            self.activateWindow()

    def _onReadyRead(self) -> None:
        while True:
            msg = self._inStream.readLine()
            if not msg: break
            self.messageReceived.emit(msg)


def python_package_source(package: str) -> str:
    """
    Return package installation source for Python package
    :param package: package name
    :return:
    """

    pip_install = '(installed using pip)'
    system_package = '(system package)'
    return pip_install if installed_using_pip(package) else system_package

def get_versions(file_manager: Optional[str],
                 file_manager_type: Optional[FileManagerType],
                 scaling_action: ScalingAction,
                 scaling_detected: ScalingDetected,
                 xsetting_running: bool) -> List[str]:
    if 'cython' in zmq.zmq_version_info.__module__:
        pyzmq_backend = 'cython'
    else:
        pyzmq_backend = 'cffi'
    try:
        ram = psutil.virtual_memory()
        total = format_size_for_user(ram.total)
        used = format_size_for_user(ram.used)
    except Exception:
        total = used = 'unknown'

    rpd_pip_install = installed_using_pip('rapid-photo-downloader')

    versions = [
        'Rapid Photo Downloader: {}'.format(__about__.__version__),
        'Platform: {}'.format(platform.platform()),
        'Memory: {} used of {}'.format(used, total),
        'Confinement: {}'.format('snap' if is_snap() else 'none'),
        'Installed using pip: {}'.format('yes' if rpd_pip_install else 'no'),
        'Python: {}'.format(platform.python_version()),
        'Python executable: {}'.format(sys.executable),
        'Qt: {}'.format(QtCore.QT_VERSION_STR),
        'PyQt: {} {}'.format(QtCore.PYQT_VERSION_STR, python_package_source('PyQt5')),
        'SIP: {}'.format(sip.SIP_VERSION_STR),
        'ZeroMQ: {}'.format(zmq.zmq_version()),
        'Python ZeroMQ: {} ({} backend)'.format(zmq.pyzmq_version(), pyzmq_backend),
        'gPhoto2: {}'.format(gphoto2_version()),
        'Python gPhoto2: {} {}'.format(
            python_gphoto2_version(), python_package_source('gphoto2')
        ),
        'ExifTool: {}'.format(EXIFTOOL_VERSION),
        'pymediainfo: {}'.format(pymedia_version_info()),
        'GExiv2: {}'.format(gexiv2_version()),
        'Gstreamer: {}'.format(gst_version()),
        'PyGObject: {}'.format('.'.join(map(str, gi.version_info))),
        'libraw: {}'.format(libraw_version() or 'not installed'),
        'rawkit: {}'.format(rawkit_version() or 'not installed'),
        'psutil: {}'.format('.'.join(map(str, psutil.version_info)))
    ]
    v = exiv2_version()
    if v:
        versions.append('Exiv2: {}'.format(v))
    try:
        versions.append('{}: {}'.format(*platform.libc_ver()))
    except:
        pass
    try:
        versions.append('Arrow: {} {}'.format(arrow.__version__, python_package_source('arrow')))
        versions.append('dateutil: {}'.format(dateutil.__version__))
    except AttributeError:
        pass
    try:
        import tornado
        versions.append('Tornado: {}'.format(tornado.version))
    except ImportError:
        pass
    versions.append(
        "Can read HEIF/HEIC metadata: {}".format('yes' if fileformats.heif_capable() else 'no')
    )
    if have_heif_module:
        versions.append('Pyheif: {}'.format(pyheif_version()))
        v = libheif_version()
        if v:
            versions.append('libheif: {}'.format(v))
    for display in ('XDG_SESSION_TYPE', 'WAYLAND_DISPLAY'):
        session = os.getenv(display, '')
        if session.find('wayland') >= 0:
            wayland_platform = os.getenv('QT_QPA_PLATFORM', '')
            if wayland_platform != 'wayland':
                session = 'wayland desktop (but this application might be running in XWayland)'
                break
            else:
                session = 'wayland desktop (with wayland enabled for this application)'
        elif session:
            break
    if session:
        versions.append('Session: {}'.format(session))

    versions.append('Desktop scaling: {}'.format(scaling_action.name.replace('_', ' ')))
    versions.append(
        'Desktop scaling detection: {}{}'.format(
            scaling_detected.name.replace('_', ' '),
            '' if xsetting_running else ' (xsetting not running)'
        )
    )

    try:
        versions.append("Desktop: {} ({})".format(get_desktop_environment(), get_desktop().name))
    except Exception:
        pass

    if file_manager:
        file_manager_details = "{} ({})".format(file_manager, file_manager_type.name)
    else:
        file_manager_details = "Unknown"

    versions.append("Default file manager: {}".format(file_manager_details))

    return versions

# def darkFusion(app: QApplication):
#     app.setStyle("Fusion")
#
#     dark_palette = QPalette()
#
#     dark_palette.setColor(QPalette.Window, QColor(53, 53, 53))
#     dark_palette.setColor(QPalette.WindowText, Qt.white)
#     dark_palette.setColor(QPalette.Base, QColor(25, 25, 25))
#     dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
#     dark_palette.setColor(QPalette.ToolTipBase, Qt.white)
#     dark_palette.setColor(QPalette.ToolTipText, Qt.white)
#     dark_palette.setColor(QPalette.Text, Qt.white)
#     dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
#     dark_palette.setColor(QPalette.ButtonText, Qt.white)
#     dark_palette.setColor(QPalette.BrightText, Qt.red)
#     dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
#     dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
#     dark_palette.setColor(QPalette.HighlightedText, Qt.black)
#
#     app.setPalette(dark_palette)
#     style = """
#     QToolTip { color: #ffffff; background-color: #2a82da; border: 1px solid white; }
#     """
#     app.setStyleSheet(style)


class SplashScreen(QSplashScreen):
    def __init__(self, pixmap: QPixmap, flags) -> None:
        super().__init__(pixmap, flags)
        self.progress = 0
        try:
            self.image_width = pixmap.width() / pixmap.devicePixelRatioF()
        except AttributeError:
            self.image_width = pixmap.width() / pixmap.devicePixelRatio()

        self.progressBarPen = QPen(QBrush(QColor(Qt.white)), 2.0)

    def drawContents(self, painter: QPainter):
        painter.save()
        painter.setPen(QColor(Qt.black))
        painter.drawText(18, 64, __about__.__version__)
        if self.progress:
            painter.setPen(self.progressBarPen)
            x = int(self.progress / 100 * self.image_width)
            painter.drawLine(0, 360, x, 360)
        painter.restore()

    def setProgress(self, value: int) -> None:
        """
        Update splash screen progress bar
        :param value: percent done, between 0 and 100
        """

        self.progress = value
        self.repaint()


def parser_options(formatter_class=argparse.HelpFormatter):
    parser = argparse.ArgumentParser(
        prog=__about__.__title__, description=__about__.__summary__, formatter_class=formatter_class
    )

    parser.add_argument(
        '--version', action='version', version='%(prog)s {}'.format(__about__.__version__)
    )
    parser.add_argument(
        '--detailed-version', action='store_true',
        help=_("Show version numbers of program and its libraries and exit.")
    )
    parser.add_argument(
        "-v", "--verbose",  action="store_true", dest="verbose",
         help=_("Display program information when run from the command line.")
    )
    parser.add_argument(
        "--debug", action="store_true", dest="debug",
        help=_("Display debugging information when run from the command line.")
    )
    parser.add_argument(
        "-e",  "--extensions", action="store_true", dest="extensions",
         help=_("List photo and video file extensions the program recognizes and exit.")
    )
    parser.add_argument(
        "--photo-renaming", choices=['on','off'], dest="photo_renaming",
        help=_("Turn on or off the the renaming of photos.")
    )
    parser.add_argument(
        "--video-renaming", choices=['on','off'], dest="video_renaming",
        help=_("Turn on or off the the renaming of videos.")
    )
    parser.add_argument(
        "-a", "--auto-detect", choices=['on','off'], dest="auto_detect",
        help=_("Turn on or off the automatic detection of devices from which to download.")
    )
    parser.add_argument(
        "-t", "--this-computer", choices=['on','off'], dest="this_computer_source",
        help=_("Turn on or off downloading from this computer.")
    )
    parser.add_argument(
        "--this-computer-location", type=str, metavar=_("PATH"), dest="this_computer_location",
        help=_("The PATH on this computer from which to download.")
    )
    parser.add_argument(
        "--photo-destination", type=str, metavar=_("PATH"), dest="photo_location",
        help=_("The PATH where photos will be downloaded to.")
    )
    parser.add_argument(
        "--video-destination", type=str, metavar=_("PATH"), dest="video_location",
        help=_("The PATH where videos will be downloaded to.")
    )
    parser.add_argument(
        "-b", "--backup", choices=['on','off'], dest="backup",
        help=_("Turn on or off the backing up of photos and videos while downloading.")
    )
    parser.add_argument(
        "--backup-auto-detect", choices=['on','off'], dest="backup_auto_detect",
        help=_("Turn on or off the automatic detection of backup devices.")
    )
    parser.add_argument(
        "--photo-backup-identifier", type=str, metavar=_("FOLDER"), dest="photo_backup_identifier",
        help=_(
            "The FOLDER in which backups are stored on the automatically detected photo backup "
            "device, with the folder's name being used to identify whether or not the device "
            "is used for backups. For each device you wish to use for backing photos up to, "
            "create a folder on it with this name."
        )
    )
    parser.add_argument(
        "--video-backup-identifier", type=str, metavar=_("FOLDER"), dest="video_backup_identifier",
        help=_(
            "The FOLDER in which backups are stored on the automatically detected video backup "
            "device, with the folder's name being used to identify whether or not the device "
            "is used for backups. For each device you wish to use for backing up videos to, "
            "create a folder on it with this name."
        )
    )
    parser.add_argument(
        "--photo-backup-location", type=str, metavar=_("PATH"), dest="photo_backup_location",
        help=_(
            "The PATH where photos will be backed up when automatic detection of backup devices is "
            "turned off."
        )
    )
    parser.add_argument(
        "--video-backup-location", type=str, metavar=_("PATH"), dest="video_backup_location",
        help=_(
            "The PATH where videos will be backed up when automatic detection of backup devices "
            "is turned off."
        )
    )
    parser.add_argument(
        "--ignore-other-photo-file-types", action="store_true", dest="ignore_other",
        help=_('Ignore photos with the following extensions: %s') %
        make_internationalized_list([s.upper() for s in fileformats.OTHER_PHOTO_EXTENSIONS])
    )
    parser.add_argument(
        "--auto-download-startup", dest="auto_download_startup",
        choices=['on', 'off'],
        help=_("Turn on or off starting downloads as soon as the program itself starts.")
    )
    parser.add_argument(
        "--auto-download-device-insertion", dest="auto_download_insertion",
        choices=['on', 'off'],
        help=_("Turn on or off starting downloads as soon as a device is inserted.")
    )
    parser.add_argument(
        "--thumbnail-cache", dest="thumb_cache",
        choices=['on','off'],
        help=_(
            "Turn on or off use of the Rapid Photo Downloader Thumbnail Cache. "
            "Turning it off does not delete existing cache contents."
        )
    )
    parser.add_argument(
        "--delete-thumbnail-cache", dest="delete_thumb_cache", action="store_true",
        help=_("Delete all thumbnails in the Rapid Photo Downloader Thumbnail Cache, and exit.")
    )
    parser.add_argument(
        "--forget-remembered-files", dest="forget_files", action="store_true",
        help=_("Forget which files have been previously downloaded, and exit.")
    )
    parser.add_argument(
        "--import-old-version-preferences", action="store_true", dest="import_prefs",
        help=_(
            "Import preferences from an old program version and exit. Requires the "
            "command line program gconftool-2."
        )
    )
    parser.add_argument(
        "--reset", action="store_true", dest="reset",
        help=_(
            "Reset all program settings to their default values, delete all thumbnails "
            "in the Thumbnail cache, forget which files have been previously downloaded, and exit."
        )
    )
    parser.add_argument(
        "--log-gphoto2", action="store_true",
        help=_("Include gphoto2 debugging information in log files.")
    )

    parser.add_argument(
        "--camera-info", action="store_true",
        help=_("Print information to the terminal about attached cameras and exit.")
    )

    parser.add_argument('path', nargs='?')

    return parser


def import_prefs() -> None:
    """
    Import program preferences from the Gtk+ 2 version of the program.

    Requires the command line program gconftool-2.
    """

    def run_cmd(k: str) -> str:
        command_line = '{} --get /apps/rapid-photo-downloader/{}'.format(cmd, k)
        args = shlex.split(command_line)
        try:
            return subprocess.check_output(args=args).decode().strip()
        except subprocess.SubprocessError:
            return ''


    cmd = shutil.which('gconftool-2')
    keys = (('image_rename', 'photo_rename', prefs_list_from_gconftool2_string),
            ('video_rename', 'video_rename', prefs_list_from_gconftool2_string),
            ('subfolder', 'photo_subfolder', prefs_list_from_gconftool2_string),
            ('video_subfolder', 'video_subfolder', prefs_list_from_gconftool2_string),
            ('download_folder', 'photo_download_folder', str),
            ('video_download_folder','video_download_folder', str),
            ('device_autodetection', 'device_autodetection', pref_bool_from_gconftool2_string),
            ('device_location', 'this_computer_path', str),
            ('device_autodetection_psd', 'scan_specific_folders',
             pref_bool_from_gconftool2_string),
            ('ignored_paths', 'ignored_paths', prefs_list_from_gconftool2_string),
            ('use_re_ignored_paths', 'use_re_ignored_paths', pref_bool_from_gconftool2_string),
            ('backup_images', 'backup_files', pref_bool_from_gconftool2_string),
            ('backup_device_autodetection', 'backup_device_autodetection',
             pref_bool_from_gconftool2_string),
            ('backup_identifier', 'photo_backup_identifier', str),
            ('video_backup_identifier', 'video_backup_identifier', str),
            ('backup_location', 'backup_photo_location', str),
            ('backup_video_location', 'backup_video_location', str),
            ('strip_characters', 'strip_characters', pref_bool_from_gconftool2_string),
            ('synchronize_raw_jpg', 'synchronize_raw_jpg', pref_bool_from_gconftool2_string),
            ('auto_download_at_startup', 'auto_download_at_startup',
             pref_bool_from_gconftool2_string),
            ('auto_download_upon_device_insertion', 'auto_download_upon_device_insertion',
             pref_bool_from_gconftool2_string),
            ('auto_unmount', 'auto_unmount', pref_bool_from_gconftool2_string),
            ('auto_exit', 'auto_exit', pref_bool_from_gconftool2_string),
            ('auto_exit_force', 'auto_exit_force', pref_bool_from_gconftool2_string),
            ('verify_file', 'verify_file', pref_bool_from_gconftool2_string),
            ('job_codes', 'job_codes', prefs_list_from_gconftool2_string),
            ('generate_thumbnails', 'generate_thumbnails', pref_bool_from_gconftool2_string),
            ('download_conflict_resolution', 'conflict_resolution', str),
            ('backup_duplicate_overwrite', 'backup_duplicate_overwrite',
             pref_bool_from_gconftool2_string))

    if cmd is None:
        print(_("To import preferences from the old version of Rapid Photo Downloader, you must "
                "install the program gconftool-2."))
        return

    prefs = Preferences()

    with raphodo.utilities.stdchannel_redirected(sys.stderr, os.devnull):
        value = run_cmd('program_version')
        if not value:
            print(_("No prior program preferences detected: exiting."))
            return
        else:
            print(
                # Translators: %(variable)s represents Python code, not a plural of the term
                # variable. You must keep the %(variable)s untranslated, or the program will
                # crash.
                _(
                    "Importing preferences from Rapid Photo Downloader %(version)s"
                ) % dict(version=value)
            )
            print()

        for key_triplet in keys:
            key = key_triplet[0]
            value = run_cmd(key)
            if value:
                try:
                    new_value = key_triplet[2](value)
                except:
                    print("Skipping malformed value for key {}".format(key))
                else:
                    if key == 'device_autodetection':
                        if new_value:
                            print("Setting device_autodetection to True")
                            print("Setting this_computer_source to False")
                            prefs.device_autodetection = True
                            prefs.this_computer_source = False
                        else:
                            print("Setting device_autodetection to False")
                            print("Setting this_computer_source to True")
                            prefs.device_autodetection = False
                            prefs.this_computer_source = True
                    elif key == 'device_autodetection_psd':
                        print("Setting scan_specific_folders to", not new_value)
                        prefs.scan_specific_folders = not new_value
                    elif key == 'device_location' and prefs.this_computer_source:
                        print("Setting this_computer_path to", new_value)
                        prefs.this_computer_path = new_value
                    elif key == 'download_conflict_resolution':
                        if new_value == "skip download":
                            prefs.conflict_resolution = int(constants.ConflictResolution.skip)
                        else:
                            prefs.conflict_resolution = \
                                int(constants.ConflictResolution.add_identifier)
                    else:
                        new_key = key_triplet[1]
                        if new_key in ('photo_rename', 'video_rename'):
                            pref_list, case = upgrade_pre090a4_rename_pref(new_value)
                            print("Setting", new_key, "to", pref_list)
                            setattr(prefs, new_key, pref_list)
                            if case is not None:
                                if new_key == 'photo_rename':
                                    ext_key = 'photo_extension'
                                else:
                                    ext_key = 'video_extension'
                                print("Setting", ext_key, "to", case)
                                setattr(prefs, ext_key, case)
                        else:
                            print("Setting", new_key, "to", new_value)
                            setattr(prefs, new_key, new_value)

    key = 'stored_sequence_no'
    with raphodo.utilities.stdchannel_redirected(sys.stderr, os.devnull):
        value = run_cmd(key)
    if value:
        try:
            new_value = int(value)
            # we need to add 1 to the number for historic reasons
            new_value += 1
        except ValueError:
            print("Skipping malformed value for key stored_sequence_no")
        else:
            if new_value and raphodo.utilities.confirm(
                '\n' + _(
                    'Do you want to copy the stored sequence number, which has the value %d?'
                    ) % new_value, resp=False):
                prefs.stored_sequence_no = new_value


def critical_startup_error(message: str) -> None:
    errorapp = QApplication(sys.argv)
    msg = QMessageBox()
    msg.setWindowTitle(_("Rapid Photo Downloader"))
    msg.setIcon(QMessageBox.Critical)
    msg.setText('<b>%s</b>' % message)
    msg.setInformativeText(_('Program aborting.'))
    msg.setStandardButtons(QMessageBox.Ok)
    msg.show()
    errorapp.exec_()


def main():
    scaling_action = ScalingAction.not_set

    scaling_detected, xsetting_running = any_screen_scaled()

    if scaling_detected == ScalingDetected.undetected:
        scaling_set = 'High DPI scaling disabled because no scaled screen was detected'
        fractional_scaling = 'Fractional scaling not set'
    else:
        # Set Qt 5 screen scaling if it is not already set in an environment variable
        qt5_variable = qt5_screen_scale_environment_variable()
        scaling_variables = {qt5_variable, 'QT_SCALE_FACTOR', 'QT_SCREEN_SCALE_FACTORS'}
        if not scaling_variables & set(os.environ):
            scaling_set = 'High DPI scaling automatically set to ON because one of the ' \
                          'following environment variables not already ' \
                          'set: {}'.format(', '.join(scaling_variables))
            scaling_action = ScalingAction.turned_on
            if pkgr.parse_version(QtCore.QT_VERSION_STR) >= pkgr.parse_version('5.6.0'):
                QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
            else:
                os.environ[qt5_variable] = '1'
        else:
            scaling_set = 'High DPI scaling not automatically set to ON because environment ' \
                          'variable(s) already ' \
                          'set: {}'.format(', '.join(scaling_variables & set(os.environ)))
            scaling_action = ScalingAction.already_set

        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

        try:
            # Enable fractional scaling support on Qt 5.14 or above
            # Doesn't seem to be working on Gnome X11, however :-/
            # Works on KDE Neon
            if pkgr.parse_version(QtCore.QT_VERSION_STR) >= pkgr.parse_version('5.14.0'):
                QApplication.setHighDpiScaleFactorRoundingPolicy(
                    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
                )
                fractional_scaling = 'Fractional scaling set to pass through'
            else:
                fractional_scaling = 'Fractional scaling unable to be set because Qt version is ' \
                                     'older than 5.14'
        except Exception:
            fractional_scaling = 'Error setting fractional scaling'
            logging.warning(fractional_scaling)

    if sys.platform.startswith('linux') and os.getuid() == 0:
        sys.stderr.write("Never run this program as the sudo / root user.\n")
        critical_startup_error(_("Never run this program as the sudo / root user."))
        sys.exit(1)

    if not shutil.which('exiftool'):
        critical_startup_error(_('You must install ExifTool to run Rapid Photo Downloader.'))
        sys.exit(1)

    rapid_path = os.path.realpath(os.path.dirname(inspect.getfile(inspect.currentframe())))
    import_path = os.path.realpath(os.path.dirname(inspect.getfile(downloadtracker)))
    if rapid_path != import_path:
        sys.stderr.write(
            "Rapid Photo Downloader is installed in multiple locations. Uninstall all copies "
            "except the version you want to run.\n"
        )
        critical_startup_error(
            _(
                "Rapid Photo Downloader is installed in multiple locations.\n\nUninstall all "
                "copies except the version you want to run."
            )
        )

        sys.exit(1)

    parser = parser_options()

    args = parser.parse_args()
    if args.detailed_version:
        file_manager, file_manager_type = get_default_file_manager()
        print(
            '\n'.join(
                get_versions(
                    file_manager, file_manager_type, scaling_action, scaling_detected,
                    xsetting_running
                )
            )
        )
        sys.exit(0)

    if args.extensions:
        photos = list((ext.upper() for ext in fileformats.PHOTO_EXTENSIONS))
        videos = list((ext.upper() for ext in fileformats.VIDEO_EXTENSIONS))
        extensions = ((photos, _("Photos")), (videos, _("Videos")))
        for exts, file_type in extensions:
            extensions = make_internationalized_list(exts)
            print('{}: {}'.format(file_type, extensions))
        sys.exit(0)

    if args.debug:
        logging_level = logging.DEBUG
    elif args.verbose:
        logging_level = logging.INFO
    else:
        logging_level = logging.ERROR

    global logger
    logger = iplogging.setup_main_process_logging(logging_level=logging_level)

    logging.info("Rapid Photo Downloader is starting")

    if args.photo_renaming:
        photo_rename = args.photo_renaming == 'on'
        if photo_rename:
            logging.info("Photo renaming turned on from command line")
        else:
            logging.info("Photo renaming turned off from command line")
    else:
        photo_rename = None
        
    if args.video_renaming:
        video_rename = args.video_renaming == 'on'
        if video_rename:
            logging.info("Video renaming turned on from command line")
        else:
            logging.info("Video renaming turned off from command line")
    else:
        video_rename = None

    if args.path:
        if args.auto_detect or args.this_computer_source:
            msg = _(
                'When specifying a path on the command line, do not also specify an\n'
                'option for device auto detection or a path on "This Computer".'
            )
            print(msg)
            critical_startup_error(msg.replace('\n', ' '))
            sys.exit(1)

        media_dir = get_media_dir()
        auto_detect = args.path.startswith(media_dir) or gvfs_gphoto2_path(args.path)
        if auto_detect:
            this_computer_source = False
            this_computer_location = None
            logging.info(
                "Device auto detection turned on from command line using positional PATH argument"
            )

        if not auto_detect:
            this_computer_source = True
            this_computer_location = os.path.abspath(args.path)
            logging.info(
                "Downloading from This Computer turned on from command line using positional "
                "PATH argument"
            )

    else:
        if args.auto_detect:
            auto_detect= args.auto_detect == 'on'
            if auto_detect:
                logging.info("Device auto detection turned on from command line")
            else:
                logging.info("Device auto detection turned off from command line")
        else:
            auto_detect=None

        if args.this_computer_source:
            this_computer_source = args.this_computer_source == 'on'
            if this_computer_source:
                logging.info("Downloading from This Computer turned on from command line")
            else:
                logging.info("Downloading from This Computer turned off from command line")
        else:
            this_computer_source=None

        if args.this_computer_location:
            this_computer_location = os.path.abspath(args.this_computer_location)
            logging.info("This Computer path set from command line: %s", this_computer_location)
        else:
            this_computer_location=None
        
    if args.photo_location:
        photo_location = os.path.abspath(args.photo_location)
        logging.info("Photo location set from command line: %s", photo_location)
    else:
        photo_location=None
        
    if args.video_location:
        video_location = os.path.abspath(args.video_location)
        logging.info("video location set from command line: %s", video_location)
    else:
        video_location=None

    if args.backup:
        backup = args.backup == 'on'
        if backup:
            logging.info("Backup turned on from command line")
        else:
            logging.info("Backup turned off from command line")
    else:
        backup=None

    if args.backup_auto_detect:
        backup_auto_detect = args.backup_auto_detect == 'on'
        if backup_auto_detect:
            logging.info("Automatic detection of backup devices turned on from command line")
        else:
            logging.info("Automatic detection of backup devices turned off from command line")
    else:
        backup_auto_detect=None

    if args.photo_backup_identifier:
        photo_backup_identifier = args.photo_backup_identifier
        logging.info("Photo backup identifier set from command line: %s", photo_backup_identifier)
    else:
        photo_backup_identifier=None

    if args.video_backup_identifier:
        video_backup_identifier = args.video_backup_identifier
        logging.info("Video backup identifier set from command line: %s", video_backup_identifier)
    else:
        video_backup_identifier=None

    if args.photo_backup_location:
        photo_backup_location = os.path.abspath(args.photo_backup_location)
        logging.info("Photo backup location set from command line: %s", photo_backup_location)
    else:
        photo_backup_location=None

    if args.video_backup_location:
        video_backup_location = os.path.abspath(args.video_backup_location)
        logging.info("Video backup location set from command line: %s", video_backup_location)
    else:
        video_backup_location=None

    if args.thumb_cache:
        thumb_cache = args.thumb_cache == 'on'
    else:
        thumb_cache = None

    if args.auto_download_startup:
        auto_download_startup = args.auto_download_startup == 'on'
        if auto_download_startup:
            logging.info("Automatic download at startup turned on from command line")
        else:
            logging.info("Automatic download at startup turned off from command line")
    else:
        auto_download_startup=None

    if args.auto_download_insertion:
        auto_download_insertion = args.auto_download_insertion == 'on'
        if auto_download_insertion:
            logging.info("Automatic download upon device insertion turned on from command line")
        else:
            logging.info("Automatic download upon device insertion turned off from command line")
    else:
        auto_download_insertion=None

    if args.log_gphoto2:
        gphoto_logging = gphoto2_python_logging()

    if args.camera_info:
        dump_camera_details()
        sys.exit(0)

    # keep appGuid value in sync with value in upgrade.py
    appGuid = '8dbfb490-b20f-49d3-9b7d-2016012d2aa8'

    # See note at top regarding avoiding crashes
    global app
    app = QtSingleApplication(appGuid, sys.argv)
    if app.isRunning():
        print('Rapid Photo Downloader is already running')
        sys.exit(0)

    app.setOrganizationName("Rapid Photo Downloader")
    app.setOrganizationDomain("damonlynch.net")
    app.setApplicationName("Rapid Photo Downloader")
    app.setWindowIcon(QIcon(':/rapid-photo-downloader.svg'))

    # Determine the system locale as reported by Qt. Use it to
    # see if Qt has a base translation available, which allows
    # automatic translation of QMessageBox buttons
    try:
        locale = QLocale.system()
        if locale:
            locale_name = locale.name()
            if not locale_name:
                logging.debug("Could not determine system locale using Qt")
            elif locale_name.startswith('en'):
                # Set module level variable indicating there is no need to translate
                # the buttons because language is English
                viewutils.Do_Message_And_Dialog_Box_Button_Translation = False
            else:
                qtTranslator = getQtSystemTranslation(locale_name)
                if qtTranslator:
                    app.installTranslator(qtTranslator)
                    # Set module level variable indicating there is no need to translate
                    # the buttons because Qt does the translation
                    viewutils.Do_Message_And_Dialog_Box_Button_Translation = False
    except Exception:
        logging.error('Error determining locale via Qt')

    # darkFusion(app)
    # app.setStyle('Fusion')

    # Resetting preferences must occur after QApplication is instantiated
    if args.reset:
        prefs = Preferences()
        prefs.reset()
        prefs.sync()
        d = DownloadedSQL()
        d.update_table(reset=True)
        cache = ThumbnailCacheSql(create_table_if_not_exists=False)
        cache.purge_cache()
        print(_("All settings and caches have been reset."))
        logging.debug("Exiting immediately after full reset")
        sys.exit(0)

    if args.delete_thumb_cache or args.forget_files or args.import_prefs:
        if args.delete_thumb_cache:
            cache = ThumbnailCacheSql(create_table_if_not_exists=False)
            cache.purge_cache()
            print(_("Thumbnail Cache has been reset."))
            logging.debug("Thumbnail Cache has been reset")

        if args.forget_files:
            d = DownloadedSQL()
            d.update_table(reset=True)
            print(_("Remembered files have been forgotten."))
            logging.debug("Remembered files have been forgotten")

        if args.import_prefs:
            import_prefs()
        logging.debug("Exiting immediately after thumbnail cache / remembered files reset")
        sys.exit(0)

    # Use QIcon to render so we get the high DPI version automatically
    size = QSize(600, 400)
    pixmap = scaledIcon(':/splashscreen.png', size).pixmap(size)

    splash = SplashScreen(pixmap, Qt.WindowStaysOnTopHint)
    splash.show()
    app.processEvents()

    rw = RapidWindow(
        photo_rename=photo_rename,
        video_rename=video_rename,
        auto_detect=auto_detect,
        this_computer_source=this_computer_source,
        this_computer_location=this_computer_location,
        photo_download_folder=photo_location,
        video_download_folder=video_location,
        backup=backup,
        backup_auto_detect=backup_auto_detect,
        photo_backup_identifier=photo_backup_identifier,
        video_backup_identifier=video_backup_identifier,
        photo_backup_location=photo_backup_location,
        video_backup_location=video_backup_location,
        ignore_other_photo_types=args.ignore_other,
        thumb_cache=thumb_cache,
        auto_download_startup=auto_download_startup,
        auto_download_insertion=auto_download_insertion,
        log_gphoto2=args.log_gphoto2,
        splash=splash,
        fractional_scaling=fractional_scaling,
        scaling_set=scaling_set,
        scaling_action=scaling_action,
        scaling_detected=scaling_detected,
        xsetting_running=xsetting_running,
    )

    app.setActivationWindow(rw)
    code = app.exec_()
    logging.debug("Exiting")
    sys.exit(code)


if __name__ == "__main__":
    main()
