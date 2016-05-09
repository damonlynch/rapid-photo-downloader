#!/usr/bin/env python3

# Copyright (C) 2011-2016 Damon Lynch <damonlynch@gmail.com>

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
__copyright__ = "Copyright 2011-2016, Damon Lynch"

import sys
import logging

import shutil
import datetime
import locale
locale.setlocale(locale.LC_ALL, '')
import pickle
from collections import namedtuple
import platform
import argparse
from typing import Optional, Tuple, List, Sequence, Dict, Set
import faulthandler
import pkg_resources
import webbrowser
import time
from urllib.request import pathname2url

from gettext import gettext as _

import gi
gi.require_version('Notify', '0.7')
from gi.repository import Notify

try:
    gi.require_version('Unity', '7.0')
    from gi.repository import Unity
    have_unity = True
except (ImportError, ValueError):
    have_unity = False

import zmq
import psutil
import gphoto2 as gp
from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import (QThread, Qt, QStorageInfo, QSettings, QPoint,
                          QSize, QTimer, QTextStream, QModelIndex,
                          pyqtSlot, QRect, pyqtSignal)
from PyQt5.QtGui import (QIcon, QPixmap, QImage, QColor, QPalette, QFontMetrics,
                         QFont, QPainter, QMoveEvent)
from PyQt5.QtWidgets import (QAction, QApplication, QMainWindow, QMenu,
                             QWidget, QDialogButtonBox,
                             QProgressBar, QSplitter,
                             QHBoxLayout, QVBoxLayout, QDialog, QLabel,
                             QComboBox, QGridLayout, QCheckBox, QSizePolicy,
                             QMessageBox, QSplashScreen,
                             QScrollArea, QDesktopWidget, QToolButton, QStyledItemDelegate)
from PyQt5.QtNetwork import QLocalSocket, QLocalServer

from raphodo.storage import (ValidMounts, CameraHotplug, UDisks2Monitor,
                     GVolumeMonitor, have_gio, has_non_empty_dcim_folder,
                     mountPaths, get_desktop_environment, get_desktop,
                     gvfs_controls_mounts, get_default_file_manager, validate_download_folder,
                     validate_source_folder, get_fdo_cache_thumb_base_directory,
                     WatchDownloadDirs)
from raphodo.interprocess import (PublishPullPipelineManager,
                                  PushPullDaemonManager,
                                  ScanArguments,
                                  CopyFilesArguments,
                                  RenameAndMoveFileData,
                                  BackupArguments,
                                  BackupFileData,
                                  OffloadData,
                                  ProcessLoggingManager,
                                  RenameAndMoveFileResults,
                                  OffloadResults,
                                  BackupResults,
                                  CopyFilesResults,
                                  GenerateThumbnailsResults,
                                  ThumbnailDaemonData,
                                  ScanResults)
from raphodo.devices import (Device, DeviceCollection, BackupDevice,
                     BackupDeviceCollection)
from raphodo.preferences import (Preferences, ScanPreferences)
from raphodo.constants import (BackupLocationType, DeviceType, ErrorType,
                               FileType, DownloadStatus, RenameAndMoveStatus,
                               photo_rename_test, ApplicationState, photo_rename_simple_test,
                               CameraErrorCode, TemporalProximityState,
                               ThumbnailBackgroundName, Desktop,
                               DeviceState, Sort, Show, Roles, DestinationDisplayType,
                               DisplayingFilesOfType, DownloadFailure, DownloadWarning)
from raphodo.thumbnaildisplay import (ThumbnailView, ThumbnailListModel, ThumbnailDelegate,
                                      DownloadTypes, DownloadStats)
from raphodo.devicedisplay import (DeviceModel, DeviceView, DeviceDelegate)
from raphodo.proximity import (TemporalProximityGroups, TemporalProximity)
from raphodo.utilities import (same_file_system, make_internationalized_list,
                               thousands, addPushButtonLabelSpacer, format_size_for_user,
                               make_html_path_non_breaking)
from raphodo.rpdfile import (RPDFile, file_types_by_number, PHOTO_EXTENSIONS,
                             VIDEO_EXTENSIONS, OTHER_PHOTO_EXTENSIONS, FileTypeCounter)
import raphodo.downloadtracker as downloadtracker
from raphodo.cache import ThumbnailCacheSql
from raphodo.metadataphoto import exiv2_version, gexiv2_version
from raphodo.metadatavideo import EXIFTOOL_VERSION, pymedia_version_info
from raphodo.camera import gphoto2_version, python_gphoto2_version
from raphodo.rpdsql import DownloadedSQL
from raphodo.generatenameconfig import *
from raphodo.rotatedpushbutton import RotatedButton, FlatButton
from raphodo.primarybutton import TopPushButton, DownloadButton
from raphodo.filebrowse import (FileSystemView, FileSystemModel, FileSystemFilter,
                                FileSystemDelegate)
from raphodo.toggleview import QToggleView
import raphodo.__about__ as __about__
import raphodo.iplogging as iplogging
import raphodo.excepthook
from raphodo.panelview import QPanelView, QComputerScrollArea
from raphodo.computerview import ComputerWidget
from raphodo.folderspreview import DownloadDestination, FoldersPreview
from raphodo.destinationdisplay import DestinationDisplay
from raphodo.aboutdialog import AboutDialog
from raphodo.jobcode import JobCode
import raphodo.constants as constants

BackupMissing = namedtuple('BackupMissing', 'photo, video')

# Avoid segfaults at exit. Recommended by Kovid Goyal:
# https://www.riverbankcomputing.com/pipermail/pyqt/2016-February/036932.html
app = None  # type: 'QtSingleApplication'

faulthandler.enable()
logger = None
sys.excepthook = raphodo.excepthook.excepthook


class RenameMoveFileManager(PushPullDaemonManager):
    """
    Manages the single instance daemon process that renames and moves
    files that have just been downloaded
    """

    message = QtCore.pyqtSignal(bool, RPDFile, int)
    sequencesUpdate = QtCore.pyqtSignal(int, list)

    def __init__(self, logging_port: int) -> None:
        super().__init__(logging_port)
        self._process_name = 'Rename and Move File Manager'
        self._process_to_run = 'renameandmovefile.py'

    def rename_file(self, data: RenameAndMoveFileData):
        self.send_message_to_worker(data)

    def process_sink_data(self):
        data = pickle.loads(self.content)  # type: RenameAndMoveFileResults
        if data.move_succeeded is not None:

            self.message.emit(data.move_succeeded, data.rpd_file, data.download_count)
        else:
            assert data.stored_sequence_no is not None
            assert data.downloads_today is not None
            assert isinstance(data.downloads_today, list)
            self.sequencesUpdate.emit(data.stored_sequence_no,
                                      data.downloads_today)


class OffloadManager(PushPullDaemonManager):
    """
    Handles tasks best run in a separate process
    """

    message = QtCore.pyqtSignal(TemporalProximityGroups)
    downloadFolders = QtCore.pyqtSignal(FoldersPreview)
    def __init__(self, logging_port: int):
        super().__init__(logging_port=logging_port)
        self._process_name = 'Offload Manager'
        self._process_to_run = 'offload.py'

    def assign_work(self, data: OffloadData):
        self.send_message_to_worker(data)

    def process_sink_data(self):
        data = pickle.loads(self.content)  # type: OffloadResults
        if data.proximity_groups is not None:
            self.message.emit(data.proximity_groups)
        elif data.folders_preview is not None:
            self.downloadFolders.emit(data.folders_preview)


class ThumbnailDaemonManager(PushPullDaemonManager):
    """
    Manages the process that extracts thumbnails after the file
    has already been downloaded and that writes FreeDesktop.org
    thumbnails. Not to be confused with ThumbnailManagerPara, which
    manages thumbnailing using processes that run in parallel,
    one for each device.
    """

    message = QtCore.pyqtSignal(RPDFile, QPixmap)

    def __init__(self, logging_port: int) -> None:
        super().__init__(logging_port)
        self._process_name = 'Thumbnail Daemon Manager'
        self._process_to_run = 'thumbnaildaemon.py'

    def process_sink_data(self):
        data = pickle.loads(self.content) # type: GenerateThumbnailsResults
        if data.thumbnail_bytes is None:
            thumbnail = QPixmap()
        else:
            thumbnail = QImage.fromData(data.thumbnail_bytes)
            if thumbnail.isNull():
                thumbnail = QPixmap()
            else:
                thumbnail = QPixmap.fromImage(thumbnail)
        self.message.emit(data.rpd_file, thumbnail)

class ScanManager(PublishPullPipelineManager):
    """
    Handles the processes that scan devices (cameras, external devices,
    this computer path)
    """
    message = QtCore.pyqtSignal(bytes)
    def __init__(self, logging_port: int):
        super().__init__(logging_port=logging_port)
        self._process_name = 'Scan Manager'
        self._process_to_run = 'scan.py'

    def process_sink_data(self):
        self.message.emit(self.content)


class BackupManager(PublishPullPipelineManager):
    """
    Each backup "device" (it could be an external drive, or a user-
    specified path on the local file system) has associated with it one
    worker process. For example if photos and videos are both being
    backed up to the same external hard drive, one worker process
    handles both the photos and the videos. However if photos are being
    backed up to one drive, and videos to another, there would be a
    worker process for each drive (2 in total).
    """
    message = QtCore.pyqtSignal(int, bool, bool, RPDFile)
    bytesBackedUp = QtCore.pyqtSignal(bytes)

    def __init__(self, logging_port: int) -> None:
        super().__init__(logging_port=logging_port)
        self._process_name = 'Backup Manager'
        self._process_to_run = 'backupfile.py'

    def add_device(self, device_id: int, backup_arguments: BackupArguments) -> None:
        self.start_worker(device_id, backup_arguments)

    def remove_device(self, device_id: int) -> None:
        self.stop_worker(device_id)

    def backup_file(self, data: BackupFileData, device_id: int) -> None:
        self.send_message_to_worker(data, device_id)

    def process_sink_data(self) -> None:
        data = pickle.loads(self.content) # type: BackupResults
        if data.total_downloaded is not None:
            assert data.scan_id is not None
            assert data.chunk_downloaded >= 0
            assert data.total_downloaded >= 0
            # Emit the unpickled data, as when PyQt converts an int to a
            # C++ int, python ints larger that the maximum C++ int are
            # corrupted
            self.bytesBackedUp.emit(self.content)
        else:
            assert data.backup_succeeded is not None
            assert data.do_backup is not None
            assert data.rpd_file is not None
            self.message.emit(data.device_id, data.backup_succeeded,
                              data.do_backup, data.rpd_file)


class CopyFilesManager(PublishPullPipelineManager):
    """
    Manage the processes that copy files from devices to the computer
    during the download process
    """

    message = QtCore.pyqtSignal(bool, RPDFile, int)
    tempDirs = QtCore.pyqtSignal(int, str,str)
    bytesDownloaded = QtCore.pyqtSignal(bytes)

    def __init__(self, logging_port: int) -> None:
        super().__init__(logging_port=logging_port)
        self._process_name = 'Copy Files Manager'
        self._process_to_run = 'copyfiles.py'

    def process_sink_data(self) -> None:
        data = pickle.loads(self.content) # type: CopyFilesResults
        if data.total_downloaded is not None:
            assert data.scan_id is not None
            #TODO handle cases where this legitimately is zero e.g. gphoto2 error -6
            assert data.chunk_downloaded >= 0
            assert data.total_downloaded >= 0
            # Emit the unpickled data, as when PyQt converts an int to a
            # C++ int, python ints larger that the maximum C++ int are
            # corrupted
            self.bytesDownloaded.emit(self.content)

        elif data.copy_succeeded is not None:
            assert data.rpd_file is not None
            assert data.download_count is not None
            self.message.emit(data.copy_succeeded, data.rpd_file,
                              data.download_count)

        else:
            assert (data.photo_temp_dir is not None or
                    data.video_temp_dir is not None)
            assert data.scan_id is not None
            self.tempDirs.emit(data.scan_id, data.photo_temp_dir,
                               data.video_temp_dir)


class UseDeviceDialog(QDialog):
    """
    A small dialog window that prompts the user if they want to
    use the external device as a download source or not.

    Includes a prompot whether to remember the choice, i.e.
    whitelist the device.
    """

    def __init__(self, device: Device, parent) -> None:
        super().__init__(parent)

        self.remember = False

        instruction = _('Should %(device)s be used to download photos and videos from?') % dict(
            device=device.display_name)
        instructionLabel = QLabel(instruction)

        icon = QLabel()
        icon.setPixmap(device.get_pixmap())

        self.rememberCheckBox = QCheckBox(_("&Remember this choice"))
        self.rememberCheckBox.setChecked(False)
        buttonBox = QDialogButtonBox()
        yesButton = buttonBox.addButton(QDialogButtonBox.Yes)
        noButton = buttonBox.addButton(QDialogButtonBox.No)
        grid = QGridLayout()
        grid.setSpacing(11)
        grid.setContentsMargins(11, 11, 11, 11)
        grid.addWidget(icon, 0, 0, 2, 1)
        grid.addWidget(instructionLabel, 0, 1, 1, 1)
        grid.addWidget(self.rememberCheckBox, 1, 1, 1, 1)
        grid.addWidget(buttonBox, 2, 0, 1, 2)
        self.setLayout(grid)
        self.setWindowTitle(_('Rapid Photo Downloader'))

        yesButton.clicked.connect(self.useDevice)
        noButton.clicked.connect(self.doNotUseDevice)

    @pyqtSlot()
    def useDevice(self) -> None:
        self.remember = self.rememberCheckBox.isChecked()
        super().accept()

    @pyqtSlot()
    def doNotUseDevice(self) -> None:
        self.remember = self.rememberCheckBox.isChecked()
        super().reject()


class RapidWindow(QMainWindow):
    """
    Main application window, and primary controller of program logic

    Such attributes unfortunately make it very complex.

    For better or worse, Qt's state machine technology is not used.
    State indicating whether a download or scan is occurring is
    thus kept in the device collection, self.devices
    """

    def __init__(self, splash: 'SplashScreen',
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
        # Process Qt events - in this case, possible closing of splash screen
        app.processEvents()

        # Three values to handle window position quirks under X11:
        self.window_show_requested_time = None  # type: datetime.datetime
        self.window_move_triggered_count = 0
        self.windowPositionDelta = QPoint(0, 0)

        self.setFocusPolicy(Qt.StrongFocus)

        self.ignore_other_photo_types = ignore_other_photo_types
        self.application_state = ApplicationState.normal
        self.prompting_for_user_action = {}  # type: Dict[Device, QMessageBox]

        for version in get_versions():
            logging.info('%s', version)

        self.log_gphoto2 = log_gphoto2 == True

        self.context = zmq.Context()

        self.setWindowTitle(_("Rapid Photo Downloader"))
        # app is a module level global
        self.readWindowSettings(app)
        self.prefs = Preferences()
        self.checkPrefsUpgrade()
        self.prefs.program_version = __about__.__version__

        if thumb_cache is not None:
            logging.debug("Use thumbnail cache: %s", thumb_cache)
            self.prefs.use_thumbnail_cache = thumb_cache

        self.setupWindow()

        if auto_detect is not None:
            self.prefs.device_autodetection = auto_detect
        else:
            logging.info("Device autodetection: %s", self.prefs.device_autodetection)

        if self.prefs.device_autodetection:
            if self.prefs.device_without_dcim_autodetection:
                logging.info("Devices do not need a DCIM folder to be scanned")
            else:
                logging.info("For automatically detected devices, only the contents of their "
                             "DCIM folder will be scanned")

        if this_computer_source is not None:
            self.prefs.this_computer_source = this_computer_source

        if this_computer_location is not None:
            self.prefs.this_computer_path = this_computer_location

        if self.prefs.this_computer_source:
            if self.prefs.this_computer_path:
                logging.info("This Computer is set to be used as a download source, "
                             "using: %s", self.prefs.this_computer_path)
            else:
                logging.info("This Computer is set to be used as a download source, "
                             "but the location is not yet set")
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

        self.prefs.verify_file = False
        # self.prefs.photo_rename = photo_rename_test

        self.prefs.photo_rename = photo_rename_simple_test
        # self.prefs.photo_rename = job_code_rename_test

        # Don't call processEvents() after initiating 0MQ, as it can
        # cause "Interrupted system call" errors
        app.processEvents()

        self.startProcessLogger()

    def checkPrefsUpgrade(self) -> None:
        if self.prefs.program_version != __about__.__version__:
            previous_version = self.prefs.program_version
            if not len(previous_version):
                logging.debug("Initial program run detected")
            else:
                pv = pkg_resources.parse_version(previous_version)
                rv = pkg_resources.parse_version(__about__.__version__)
                if pv < rv:
                    logging.debug("Version upgrade detected, from %s to %s",
                                  previous_version, __about__.__version__)
                elif pv > rv:
                    logging.debug("Version downgrade detected, from %s to %s",
                                  __about__.__version__, previous_version)

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
        logging.debug("... logging subscription manager started")
        self.logging_port = logging_port

        logging.debug("Stage 2 initialization")

        # For meaning of 'Devices', see devices.py
        self.devices = DeviceCollection()

        logging.debug("Starting thumbnail daemon model")

        self.thumbnaildaemonmqThread = QThread()
        self.thumbnaildaemonmq = ThumbnailDaemonManager(logging_port=logging_port)

        self.thumbnaildaemonmq.moveToThread(self.thumbnaildaemonmqThread)

        self.thumbnaildaemonmqThread.started.connect(self.thumbnaildaemonmq.run_sink)
        self.thumbnaildaemonmq.message.connect(self.thumbnailReceivedFromDaemon)

        QTimer.singleShot(0, self.thumbnaildaemonmqThread.start)
        # Immediately start the sole thumbnail daemon process worker
        self.thumbnaildaemonmq.start()

        self.thumbnailView = ThumbnailView(self)
        logging.debug("Starting thumbnail model and load balancer...")
        self.thumbnailModel = ThumbnailListModel(parent=self, logging_port=logging_port,
                                                 log_gphoto2=self.log_gphoto2)

        self.thumbnailView.setModel(self.thumbnailModel)
        self.thumbnailView.setItemDelegate(ThumbnailDelegate(rapidApp=self))

        # Connect to the signal that is emitted when a thumbnailing operation is
        # terminated by us, not merely finished
        self.thumbnailModel.thumbnailmq.workerStopped.connect(self.thumbnailGenerationStopped)


    @pyqtSlot()
    def initStage3(self) -> None:
        logging.debug("... thumbnail model and load balancer started")

        logging.debug("Stage 3 initialization")

        self.thumbnaildaemonmq.send_message_to_worker(ThumbnailDaemonData(
            frontend_port=self.thumbnailModel.thumbnailmq.frontend_port))

        centralWidget = QWidget()
        self.setCentralWidget(centralWidget)

        self.temporalProximity = TemporalProximity(rapidApp=self, prefs=self.prefs)

        self.createPathViews()

        self.createActions()
        logging.debug("Laying out main window")
        self.createMenus()
        self.createLayoutAndButtons(centralWidget)

        # Setup notification system
        try:
            self.have_libnotify = Notify.init('rapid-photo-downloader')
            self.ctime_update_notification = None  # type: Optional[Notify.Notification]
            self.ctime_notification_issued = False
        except:
            logging.error("Notification intialization problem")
            self.have_libnotify = False

        self.file_manager = get_default_file_manager()
        if self.file_manager:
            logging.debug("Default file manager: %s", self.file_manager)
        else:
            logging.debug("Default file manager could not be determined")

        self.program_svg = ':/rapid-photo-downloader.svg'
        # Initialise use of libgphoto2
        logging.debug("Getting gphoto2 context")
        try:
            self.gp_context = gp.Context()
        except:
            logging.critical("Error getting gphoto2 context")
            self.gp_context = None

        logging.debug("Probing for valid mounts")
        self.validMounts = ValidMounts(onlyExternalMounts=self.prefs.only_external_mounts)

        logging.debug("Freedesktop.org thumbnails location: %s",
                       get_fdo_cache_thumb_base_directory())

        logging.debug("Setting up Job Code window")
        self.job_code = JobCode(self)

        logging.debug("Probing desktop environment")
        desktop_env = get_desktop_environment()
        logging.debug("Desktop environment: %s", desktop_env)

        self.unity_progress = False
        if get_desktop() == Desktop.unity:
            if not have_unity:
                logging.debug("Desktop environment is Unity, but could not load Unity 7.0 module")
            else:
                # Unity auto-generated desktop files use underscores, it seems
                for launcher in ('rapid-photo-downloader.desktop',
                                 'rapid_photo_downloader.desktop'):
                    self.desktop_launcher = Unity.LauncherEntry.get_for_desktop_id(launcher)
                    if self.desktop_launcher is not None:
                        self.unity_progress = True
                        break

                if self.desktop_launcher is None:
                    logging.debug("Desktop environment is Unity 7.0, but could not find "
                                  "program's .desktop file")
                else:
                    logging.debug("Unity progress indicator will be used")

        logging.debug("Have GIO module: %s", have_gio)
        self.gvfsControlsMounts = gvfs_controls_mounts() and have_gio
        if have_gio:
            logging.debug("Using GIO: %s", self.gvfsControlsMounts)

        if not self.gvfsControlsMounts:
            # Monitor when the user adds or removes a camera
            self.cameraHotplug = CameraHotplug()
            self.cameraHotplugThread = QThread()
            self.cameraHotplug.moveToThread(self.cameraHotplugThread)
            self.cameraHotplug.cameraAdded.connect(self.cameraAdded)
            self.cameraHotplug.cameraRemoved.connect(self.cameraRemoved)
            # Start the monitor only on the thread it will be running on
            logging.debug("Starting camera hotplug monitor...")
            self.cameraHotplug.startMonitor()
            logging.debug("... camera hotplug monitor started")
            self.cameraHotplug.enumerateCameras()

            if self.cameraHotplug.cameras:
                logging.debug("Camera Hotplug found %d cameras:", len(self.cameraHotplug.cameras))
                for port, model in self.cameraHotplug.cameras.items():
                    logging.debug("%s at %s", model, port)

            # Monitor when the user adds or removes a partition
            self.udisks2Monitor = UDisks2Monitor(self.validMounts)
            self.udisks2MonitorThread = QThread()
            self.udisks2Monitor.moveToThread(self.udisks2MonitorThread)
            self.udisks2Monitor.partitionMounted.connect(self.partitionMounted)
            self.udisks2Monitor.partitionUnmounted.connect(
                self.partitionUmounted)
            # Start the monitor only on the thread it will be running on
            logging.debug("Starting UDisks2 monitor...")
            self.udisks2Monitor.startMonitor()
            logging.debug("... UDisks2 monitor started")

        if self.gvfsControlsMounts:
            logging.debug("Starting GVolumeMonitor...")
            self.gvolumeMonitor = GVolumeMonitor(self.validMounts)
            logging.debug("... GVolumeMonitor started")
            self.gvolumeMonitor.cameraUnmounted.connect(self.cameraUnmounted)
            self.gvolumeMonitor.cameraMounted.connect(self.cameraMounted)
            self.gvolumeMonitor.partitionMounted.connect(self.partitionMounted)
            self.gvolumeMonitor.partitionUnmounted.connect(self.partitionUmounted)
            self.gvolumeMonitor.volumeAddedNoAutomount.connect(self.noGVFSAutoMount)
            self.gvolumeMonitor.cameraPossiblyRemoved.connect(self.cameraRemoved)

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
        self.offloadThread = QThread()
        self.offloadmq = OffloadManager(logging_port=self.logging_port)
        self.offloadmq.moveToThread(self.offloadThread)

        self.offloadThread.started.connect(self.offloadmq.run_sink)
        self.offloadmq.message.connect(self.proximityGroupsGenerated)
        self.offloadmq.downloadFolders.connect(self.provisionalDownloadFoldersGenerated)

        QTimer.singleShot(0, self.offloadThread.start)
        # Immediately start the sole daemon offload process worker
        self.offloadmq.start()

        self.renameThread = QThread()
        self.renamemq = RenameMoveFileManager(logging_port=self.logging_port)
        self.renamemq.moveToThread(self.renameThread)

        self.renameThread.started.connect(self.renamemq.run_sink)
        self.renamemq.message.connect(self.fileRenamedAndMoved)
        self.renamemq.sequencesUpdate.connect(self.updateSequences)
        self.renamemq.workerFinished.connect(self.fileRenamedAndMovedFinished)

        QTimer.singleShot(0, self.renameThread.start)
        # Immediately start the sole daemon process rename and move files
        # worker
        self.renamemq.start()

        # Setup the scan processes
        self.scanThread = QThread()
        self.scanmq = ScanManager(logging_port=self.logging_port)
        self.scanmq.moveToThread(self.scanThread)

        self.scanThread.started.connect(self.scanmq.run_sink)
        self.scanmq.message.connect(self.scanMessageReceived)
        self.scanmq.workerFinished.connect(self.scanFinished)

        # call the slot with no delay
        QTimer.singleShot(0, self.scanThread.start)

        # Setup the copyfiles process
        self.copyfilesThread = QThread()
        self.copyfilesmq = CopyFilesManager(logging_port=self.logging_port)
        self.copyfilesmq.moveToThread(self.copyfilesThread)

        self.copyfilesThread.started.connect(self.copyfilesmq.run_sink)
        self.copyfilesmq.message.connect(self.copyfilesDownloaded)
        self.copyfilesmq.bytesDownloaded.connect(self.copyfilesBytesDownloaded)
        self.copyfilesmq.tempDirs.connect(self.tempDirsReceivedFromCopyFiles)
        self.copyfilesmq.workerFinished.connect(self.copyfilesFinished)

        QTimer.singleShot(0, self.copyfilesThread.start)

        self.backup_manager_started = False
        self.backup_devices = BackupDeviceCollection()
        if self.prefs.backup_files:
            self.startBackupManager()
            self.setupBackupDevices()
        else:
            self.download_tracker.set_no_backup_devices(0, 0)

        settings = QSettings()
        settings.beginGroup("MainWindow")

        self.proximityButton.setChecked(settings.value("proximityButtonPressed", False, bool))
        self.proximityButtonClicked()

        self.sourceButton.setChecked(settings.value("sourceButtonPressed", True, bool))
        self.sourceButtonClicked()

        self.destinationButton.setChecked(settings.value("destinationButtonPressed", True, bool))
        self.destinationButtonClicked()

        prefs_valid, msg = self.prefs.check_prefs_for_validity()

        self.setDownloadCapabilities()
        self.searchForCameras(on_startup=True)
        self.setupNonCameraDevices(on_startup=True)
        self.setupManualPath(on_startup=True)
        self.updateSourceButton()
        self.displayMessageInStatusBar()

        self.showMainWindow()

        if not prefs_valid:
            self.notifyPrefsAreInvalid(details=msg)

        logging.debug("Completed stage 3 initializing main window")

    def showMainWindow(self) -> None:
        if not self.isVisible():
            self.splash.finish(self)

            self.window_show_requested_time = datetime.datetime.now()
            self.show()

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

    def readWindowSettings(self, app: 'QtSingleApplication'):
        settings = QSettings()
        settings.beginGroup("MainWindow")
        desktop = app.desktop() # type: QDesktopWidget

        # Calculate window sizes
        available = desktop.availableGeometry(desktop.primaryScreen())  # type: QRect
        screen = desktop.screenGeometry(desktop.primaryScreen())  # type: QRect
        default_width = max(960, available.width() // 2)
        default_width = min(default_width, available.width())
        default_x = screen.width() - default_width
        default_height = available.height()
        default_y = screen.height() - default_height
        pos = settings.value("windowPosition", QPoint(default_x, default_y))
        size = settings.value("windowSize", QSize(default_width, default_height))
        settings.endGroup()
        self.resize(size)
        self.move(pos)

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
        settings.setValue("centerSplitterSizes", self.centerSplitter.saveState())
        settings.setValue("sourceButtonPressed", self.sourceButton.isChecked())
        settings.setValue("destinationButtonPressed", self.destinationButton.isChecked())
        settings.setValue("proximityButtonPressed", self.proximityButton.isChecked())
        settings.setValue("leftPanelSplitterSizes", self.leftPanelSplitter.saveState())
        settings.setValue("rightPanelSplitterSizes", self.rightPanelSplitter.saveState())
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

    def setupWindow(self):
        status = self.statusBar()
        self.downloadProgressBar = QProgressBar()
        self.downloadProgressBar.setMaximumWidth(QFontMetrics(QFont()).height() * 9)
        status.addPermanentWidget(self.downloadProgressBar, 1)

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
            self.desktop_launcher.set_property('progress_visible', False)

        if len(self.devices.thumbnailing):
            if self.downloadProgressBar.maximum() != self.thumbnailModel.total_thumbs_to_generate:
                logging.debug("Setting progress bar maximum to %s",
                              self.thumbnailModel.total_thumbs_to_generate)
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

    def startBackupManager(self) -> None:
        if not self.backup_manager_started:
            self.backupThread = QThread()
            self.backupmq = BackupManager(logging_port=self.logging_port)
            self.backupmq.moveToThread(self.backupThread)

            self.backupThread.started.connect(self.backupmq.run_sink)
            self.backupmq.message.connect(self.fileBackedUp)
            self.backupmq.bytesBackedUp.connect(self.backupFileBytesBackedUp)

            QTimer.singleShot(0, self.backupThread.start)

            self.backup_manager_started = True

    def updateSourceButton(self) -> None:
        text, icon = self.devices.get_main_window_display_name_and_icon()
        self.sourceButton.setText(addPushButtonLabelSpacer(text))
        self.sourceButton.setIcon(icon)

    def setLeftPanelVisibility(self) -> None:
        self.leftPanelSplitter.setVisible(self.sourceButton.isChecked() or
                                          self.proximityButton.isChecked())

    def setRightPanelVisibility(self) -> None:
        self.rightPanelSplitter.setVisible(self.destinationButton.isChecked())

    @pyqtSlot()
    def sourceButtonClicked(self) -> None:
        self.deviceToggleView.setVisible(self.sourceButton.isChecked())
        self.thisComputerToggleView.setVisible(self.sourceButton.isChecked())
        self.setLeftPanelVisibility()

    @pyqtSlot()
    def destinationButtonClicked(self) -> None:
        self.photoDestination.setVisible(self.destinationButton.isChecked())
        self.videoDestination.setVisible(self.destinationButton.isChecked())
        self.setRightPanelVisibility()

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
            this_computer_height = max(min_this_computer_height, self.centerSplitter.height() -
                                       preferred_devices_height)
        else:
            this_computer_height = min_this_computer_height

        if self.proximityButton.isChecked():
            if not self.thisComputerToggleView.on():
                proximity_height = (self.centerSplitter.height() - this_computer_height -
                                    preferred_devices_height)
            else:
                proximity_height = this_computer_height // 2
                this_computer_height = this_computer_height // 2
        else:
            proximity_height = 0
        self.leftPanelSplitter.setSizes([preferred_devices_height, this_computer_height,
                                         proximity_height])

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

    def createActions(self):
        self.sourceAct = QAction(_('&Source'), self, shortcut="Ctrl+s",
                                 triggered=self.doSourceAction)

        self.downloadAct = QAction(_("Download"), self,
                                   shortcut="Ctrl+Return",
                                   triggered=self.doDownloadAction)

        self.refreshAct = QAction(_("&Refresh..."), self, shortcut="Ctrl+R",
                                  triggered=self.doRefreshAction)

        self.preferencesAct = QAction(_("&Preferences"), self,
                                      shortcut="Ctrl+P",
                                      triggered=self.doPreferencesAction)

        self.quitAct = QAction(_("&Quit"), self, shortcut="Ctrl+Q",
                               triggered=self.close)

        self.checkAllAct = QAction(_("&Check All"), self, shortcut="Ctrl+A",
                                   triggered=self.doCheckAllAction)

        self.checkAllPhotosAct = QAction(_("Check All Photos"), self,
                                         shortcut="Ctrl+T",
                                         triggered=self.doCheckAllPhotosAction)

        self.checkAllVideosAct = QAction(_("Check All Videos"), self,
                                         shortcut="Ctrl+D",
                                         triggered=self.doCheckAllVideosAction)

        self.uncheckAllAct = QAction(_("&Uncheck All"), self,
                                     shortcut="Ctrl+L",
                                     triggered=self.doUncheckAllAction)

        self.errorLogAct = QAction(_("Error Log"), self, enabled=False,
                                   checkable=True,
                                   triggered=self.doErrorLogAction)

        self.clearDownloadsAct = QAction(_("Clear Completed Downloads"), self,
                                         triggered=self.doClearDownloadsAction)

        self.previousFileAct = QAction(_("Previous File"), self, shortcut="[",
                                       triggered=self.doPreviousFileAction)

        self.nextFileAct = QAction(_("Next File"), self, shortcut="]",
                                   triggered=self.doNextFileAction)

        self.helpAct = QAction(_("Get Help Online..."), self, shortcut="F1",
                               triggered=self.doHelpAction)

        self.reportProblemAct = QAction(_("Report a Problem..."), self,
                                        triggered=self.doReportProblemAction)

        self.makeDonationAct = QAction(_("Make a Donation..."), self,
                                       triggered=self.doMakeDonationAction)

        self.translateApplicationAct = QAction(_("Translate this Application..."),
                           self, triggered=self.doTranslateApplicationAction)

        self.aboutAct = QAction(_("&About..."), self, triggered=self.doAboutAction)

    def createLayoutAndButtons(self, centralWidget) -> None:

        settings = QSettings()
        settings.beginGroup("MainWindow")

        verticalLayout = QVBoxLayout()
        verticalLayout.setContentsMargins(0, 0, 0, 0)
        centralWidget.setLayout(verticalLayout)
        self.standard_spacing = verticalLayout.spacing()

        topBar = self.createTopBar()
        verticalLayout.addLayout(topBar)

        centralLayout = QHBoxLayout()
        centralLayout.setContentsMargins(0, 0, 0, 0)

        self.leftBar = self.createLeftBar()
        self.rightBar = self.createRightBar()

        self.createCenterPanels()
        self.createDeviceThisComputerViews()
        self.createDestinationViews()
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

        self.sourceButton = TopPushButton(addPushButtonLabelSpacer(_('Select Source')),
                                          extra_top=self.standard_spacing)
        self.sourceButton.clicked.connect(self.sourceButtonClicked)

        vlayout = QVBoxLayout()
        vlayout.setContentsMargins(0, 0, 0, 0)
        vlayout.setSpacing(0)
        vlayout.addSpacing(self.standard_spacing)
        hlayout = QHBoxLayout()
        hlayout.setContentsMargins(0, 0, 0, 0)
        hlayout.setSpacing(menu_margin)
        vlayout.addLayout(hlayout)

        self.downloadButton = DownloadButton(self.downloadAct.text())
        self.downloadButton.addAction(self.downloadAct)
        self.downloadButton.setDefault(True)
        self.downloadButton.clicked.connect(self.downloadButtonClicked)
        # self.download_action_is_download = True

        self.menuButton.setIconSize(QSize(self.sourceButton.top_row_icon_size,
                               self.sourceButton.top_row_icon_size))

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
        self._mapModel = {DeviceType.path: self.thisComputerModel,
                         DeviceType.camera: self.deviceModel,
                         DeviceType.volume: self.deviceModel}
        self._mapView = {DeviceType.path: self.thisComputerView,
                         DeviceType.camera: self.deviceView,
                         DeviceType.volume: self.deviceView}

        # Be cautious: validate paths. The settings file can alwasy be edited by hand, and
        # the user can set it to whatever value they want using the command line options.
        logging.debug("Checking path validity")
        this_computer_sf = validate_source_folder(self.prefs.this_computer_path)
        if this_computer_sf.valid:
            if this_computer_sf.absolute_path != self.prefs.this_computer_path:
                self.prefs.this_computer_path = this_computer_sf.absolute_path
        elif self.prefs.this_computer_source and self.prefs.this_computer_path != '':
            logging.warning("Ignoring invalid 'This Computer' path: %s",
                            self.prefs.this_computer_path)
            self.prefs.this_computer_path = ''

        photo_df = validate_download_folder(self.prefs.photo_download_folder)
        if photo_df.valid:
            if photo_df.absolute_path != self.prefs.photo_download_folder:
                self.prefs.photo_download_folder = photo_df.absolute_path
        else:
            if self.prefs.photo_download_folder:
                logging.error("Ignoring invalid Photo Destination path: %s",
                              self.prefs.photo_download_folder)
            self.prefs.photo_download_folder = ''

        video_df = validate_download_folder(self.prefs.video_download_folder)
        if video_df.valid:
            if video_df.absolute_path != self.prefs.video_download_folder:
                self.prefs.video_download_folder = video_df.absolute_path
        else:
            if self.prefs.video_download_folder:
                logging.error("Ignoring invalid Video Destination path: %s",
                              self.prefs.video_download_folder)
            self.prefs.video_download_folder = ''

        self.watchedDownloadDirs = WatchDownloadDirs()
        self.watchedDownloadDirs.updateWatchPathsFromPrefs(self.prefs)
        self.watchedDownloadDirs.directoryChanged.connect(self.watchedFolderChange)

        self.fileSystemModel = FileSystemModel(parent=self)
        self.fileSystemFilter = FileSystemFilter(self)
        self.fileSystemFilter.setSourceModel(self.fileSystemModel)
        self.fileSystemDelegate = FileSystemDelegate()

        index = self.fileSystemFilter.mapFromSource(self.fileSystemModel.index('/'))

        self.thisComputerFSView = FileSystemView(self.fileSystemModel)
        self.thisComputerFSView.setModel(self.fileSystemFilter)
        self.thisComputerFSView.setItemDelegate(self.fileSystemDelegate)
        self.thisComputerFSView.hideColumns()
        self.thisComputerFSView.setRootIndex(index)
        if this_computer_sf.valid:
            self.thisComputerFSView.goToPath(self.prefs.this_computer_path)
        self.thisComputerFSView.activated.connect(self.thisComputerPathChosen)
        self.thisComputerFSView.clicked.connect(self.thisComputerPathChosen)

        self.photoDestinationFSView = FileSystemView(self.fileSystemModel)
        self.photoDestinationFSView.setModel(self.fileSystemFilter)
        self.photoDestinationFSView.setItemDelegate(self.fileSystemDelegate)
        self.photoDestinationFSView.hideColumns()
        self.photoDestinationFSView.setRootIndex(index)
        if photo_df.valid:
            self.photoDestinationFSView.goToPath(self.prefs.photo_download_folder)
        self.photoDestinationFSView.activated.connect(self.photoDestinationPathChosen)
        self.photoDestinationFSView.clicked.connect(self.photoDestinationPathChosen)

        self.videoDestinationFSView = FileSystemView(self.fileSystemModel)
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
        self.deviceToggleView = QToggleView(label=_('Devices'),
                                            display_alternate=True,
                                            toggleToolTip=tip,
                                            headerColor=QColor(ThumbnailBackgroundName),
                                            headerFontColor=QColor(Qt.white),
                                            on=self.prefs.device_autodetection)
        self.deviceToggleView.addWidget(self.deviceView)
        self.deviceToggleView.valueChanged.connect(self.deviceToggleViewValueChange)
        self.deviceToggleView.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)

        # This Computer Header and View

        tip = _('Turn on or off the use of a folder on this computer as a download source')
        self.thisComputerToggleView = QToggleView(label=_('This Computer'),
                                                  display_alternate=True,
                                                  toggleToolTip=tip,
                                                  headerColor=QColor(ThumbnailBackgroundName),
                                                  headerFontColor=QColor(Qt.white),
                                                  on=bool(self.prefs.this_computer_source))
        self.thisComputerToggleView.valueChanged.connect(self.thisComputerToggleValueChanged)

        self.thisComputer = ComputerWidget(objectName='thisComputer',
                                           view=self.thisComputerView,
                                           fileSystemView=self.thisComputerFSView,
                                           select_text=_('Select a source folder'))
        if self.prefs.this_computer_source:
            self.thisComputer.setViewVisible(self.prefs.this_computer_source)

        self.thisComputerToggleView.addWidget(self.thisComputer)

    def createDestinationViews(self) -> None:
        """
        Create the widgets that let the user choose where to download photos and videos to,
        and that show them how much storage space there is available for their files.
        """

        self.photoDestination = QPanelView(label=_('Photos'),
                                      headerColor=QColor(ThumbnailBackgroundName),
                                      headerFontColor=QColor(Qt.white))
        self.videoDestination = QPanelView(label=_('Videos'),
                                      headerColor=QColor(ThumbnailBackgroundName),
                                      headerFontColor=QColor(Qt.white))

        # Display storage space when photos and videos are being downloaded to the same
        # partition

        self.combinedDestinationDisplay = DestinationDisplay()
        self.combinedDestinationDisplayContainer = QPanelView(_('Storage Space'),
                                      headerColor=QColor(ThumbnailBackgroundName),
                                      headerFontColor=QColor(Qt.white))
        self.combinedDestinationDisplayContainer.addWidget(self.combinedDestinationDisplay)

        # Display storage space when photos and videos are being downloaded to different
        # partitions.
        # Also display the file system folder chooser for both destinations.

        self.photoDestinationDisplay = DestinationDisplay()
        self.photoDestinationDisplay.setDestination(self.prefs.photo_download_folder)
        self.photoDestinationWidget = ComputerWidget(objectName='photoDestination',
             view=self.photoDestinationDisplay, fileSystemView=self.photoDestinationFSView,
             select_text=_('Select a destination folder'))
        self.photoDestination.addWidget(self.photoDestinationWidget)
        
        self.videoDestinationDisplay = DestinationDisplay()
        self.videoDestinationDisplay.setDestination(self.prefs.video_download_folder)
        self.videoDestinationWidget = ComputerWidget(objectName='videoDestination',
             view=self.videoDestinationDisplay, fileSystemView=self.videoDestinationFSView,
             select_text=_('Select a destination folder'))
        self.videoDestination.addWidget(self.videoDestinationWidget)

        self.photoDestinationContainer = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.photoDestinationContainer.setLayout(layout)
        layout.addWidget(self.combinedDestinationDisplayContainer)
        layout.addWidget(self.photoDestination)

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

        style = """
        QComboBox {
            border: 0px;
            padding: 1px 3px 1px 3px;
            background-color: palette(window);
            selection-background-color: palette(highlight);
            color: palette(window-text);
        }

        QComboBox:on { /* shift the text when the popup opens */
            padding-top: 3px;
            padding-left: 4px;
        }

        QComboBox::drop-down {
             subcontrol-origin: padding;
             subcontrol-position: top right;
             width: %(width)dpx;
             border: 0px;
         }

        QComboBox::down-arrow {
            image: url(:/chevron-down.svg);
            width: %(width)dpx;
        }

        QComboBox QAbstractItemView {
            outline: none;
            border: 1px solid palette(shadow);
            background-color: palette(window);
            selection-background-color: palette(highlight);
            selection-color: palette(highlighted-text);
            color: palette(window-text)
        }

        QComboBox QAbstractItemView::item {
            padding: 3px;
        }
        """ % dict(width=int(QFontMetrics(QFont()).height() * (2/3)))

        label_style = """
        QLabel {border-color: palette(window); border-width: 1px; border-style: solid;}
        """

        # Delegate overrides default delegate for the Combobox, which is
        # pretty ugly whenever a style sheet color is applied.
        # See http://stackoverflow.com/questions/13308341/qcombobox-abstractitemviewitem?rq=1
        self.comboboxDelegate = QStyledItemDelegate()

        font = self.font()  # type: QFont
        font.setPointSize(font.pointSize() - 2)

        self.showLabel = QLabel(_("Show:"))
        self.showLabel.setAlignment(Qt.AlignBottom)
        self.showCombo = QComboBox()
        self.showCombo.addItem(_('All'), Show.all)
        self.showCombo.addItem(_('New'), Show.new_only)
        self.showCombo.currentIndexChanged.connect(self.showComboChanged)

        self.sortLabel= QLabel(_("Sort:"))
        self.sortLabel.setAlignment(Qt.AlignBottom)
        self.sortCombo = QComboBox()
        self.sortCombo.addItem(_("Modification Time"), Sort.modification_time)
        self.sortCombo.addItem(_("Checked State"), Sort.checked_state)
        self.sortCombo.addItem(_("Filename"), Sort.filename)
        self.sortCombo.addItem(_("Extension"), Sort.extension)
        self.sortCombo.addItem(_("File Type"), Sort.file_type)
        self.sortCombo.addItem(_("Device"), Sort.device)
        self.sortCombo.currentIndexChanged.connect(self.sortComboChanged)

        self.sortOrder = QComboBox()
        self.sortOrder.addItem(_("Ascending"), Qt.AscendingOrder)
        self.sortOrder.addItem(_("Descending"), Qt.DescendingOrder)
        self.sortOrder.currentIndexChanged.connect(self.sortOrderChanged)

        for combobox in (self.showCombo, self.sortCombo, self.sortOrder):
            combobox.setItemDelegate(self.comboboxDelegate)
            combobox.setStyleSheet(style)

        # Add an invisible border to make the lable vertically align with the comboboxes
        # Otherwise it's off by 1px
        # TODO come up with a better way to solve this alignment problem, because this sucks
        for label in (self.sortLabel,self.showLabel):
            label.setStyleSheet(label_style)

        for widget in (self.showLabel, self.sortLabel, self.sortCombo, self.showCombo,
                       self.sortOrder):
            widget.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Maximum)
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

        self.centerSplitter.addWidget(self.leftPanelSplitter)
        self.centerSplitter.addWidget(self.thumbnailView)
        self.centerSplitter.addWidget(self.rightPanelSplitter)
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

        destinations_good = self.updateDestinationViews()
        self.setDownloadActionState(destinations_good)
        self.destinationButton.setHighlighted(not destinations_good)
        return destinations_good

    def updateDestinationViews(self) -> bool:
        """
        Updates the the header bar and storage space view for the
        photo and video download destinations.

        :return True if destinations required for the download exist,
         and there is sufficient space on them, else False.
        """

        size_photos_marked = self.thumbnailModel.getSizeOfFilesMarkedForDownload(FileType.photo)
        size_videos_marked = self.thumbnailModel.getSizeOfFilesMarkedForDownload(FileType.video)
        marked = self.thumbnailModel.getNoFilesAndTypesMarkedForDownload()

        if self.unity_progress:
            available = self.thumbnailModel.getCountNotPreviouslyDownloadedAvailableForDownload()
            if available:
                self.desktop_launcher.set_property("count", available)
                self.desktop_launcher.set_property("count_visible", True)
            else:
                self.desktop_launcher.set_property("count_visible", False)

        destinations_good = True

        # Assume that invalid destination folders have already been reset to ''
        if self.prefs.photo_download_folder and self.prefs.video_download_folder:
            same_fs = same_file_system(self.prefs.photo_download_folder,
                                       self.prefs.video_download_folder)
        else:
            same_fs = False

        merge = self.downloadIsRunning()

        if same_fs:
            files_to_display = DisplayingFilesOfType.photos_and_videos
            self.combinedDestinationDisplay.setDestination(self.prefs.photo_download_folder)
            self.combinedDestinationDisplay.setDownloadAttributes(marked, size_photos_marked,
                          size_videos_marked, files_to_display, DestinationDisplayType.usage_only,
                                                                  merge)
            display_type = DestinationDisplayType.folder_only
            self.combinedDestinationDisplayContainer.setVisible(True)
            destinations_good = self.combinedDestinationDisplay.sufficientSpaceAvailable()
        else:
            files_to_display = DisplayingFilesOfType.photos
            display_type = DestinationDisplayType.folders_and_usage
            self.combinedDestinationDisplayContainer.setVisible(False)

        if self.prefs.photo_download_folder:
            self.photoDestinationDisplay.setDownloadAttributes(marked, size_photos_marked,
                            0, files_to_display, display_type, merge)
            self.photoDestinationWidget.setViewVisible(True)
            if display_type == DestinationDisplayType.folders_and_usage:
                destinations_good = self.photoDestinationDisplay.sufficientSpaceAvailable()
        else:
            # Photo download folder was invalid or simply not yet set
            self.photoDestinationWidget.setViewVisible(False)
            if size_photos_marked:
                destinations_good = False

        if not same_fs:
            files_to_display = DisplayingFilesOfType.videos
        if self.prefs.video_download_folder:
            self.videoDestinationDisplay.setDownloadAttributes(marked, 0,
                           size_videos_marked, files_to_display, display_type, merge)
            self.videoDestinationWidget.setViewVisible(True)
            if display_type == DestinationDisplayType.folders_and_usage:
                destinations_good = (self.videoDestinationDisplay.sufficientSpaceAvailable() and
                                     destinations_good)
        else:
            # Video download folder was invalid or simply not yet set
            self.videoDestinationWidget.setViewVisible(False)
            if size_videos_marked:
                destinations_good = False

        return destinations_good

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
            if self.downloadPaused():
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
        self.menu.addAction(self.reportProblemAct)
        self.menu.addAction(self.makeDonationAct)
        self.menu.addAction(self.translateApplicationAct)
        self.menu.addAction(self.aboutAct)
        self.menu.addAction(self.quitAct)


        self.menuButton = QToolButton()
        self.menuButton.setPopupMode(QToolButton.InstantPopup)
        self.menuButton.setIcon(QIcon(':/menu.svg'))
        self.menuButton.setStyleSheet("""
        QToolButton {border: none;}
        QToolButton::menu-indicator { image: none; }
        QToolButton::hover {
            border: 1px solid palette(shadow);
            border-radius: 3px;
        }
        QToolButton::pressed {
            border: 1px solid palette(shadow);
            border-radius: 3px;
        }
        """)
        self.menuButton.setMenu(self.menu)

    def doSourceAction(self):
        self.sourceButton.animateClick()

    def doDownloadAction(self):
        self.downloadButton.animateClick()

    def doRefreshAction(self):
        pass

    def doPreferencesAction(self):
        pass

    def doCheckAllAction(self):
        self.thumbnailModel.checkAll(check_all=True)

    def doCheckAllPhotosAction(self):
        self.thumbnailModel.checkAll(check_all=True, file_type=FileType.photo)

    def doCheckAllVideosAction(self):
        self.thumbnailModel.checkAll(check_all=True, file_type=FileType.video)

    def doUncheckAllAction(self):
        self.thumbnailModel.checkAll(check_all=False)

    def doErrorLogAction(self):
        pass

    def doClearDownloadsAction(self):
        self.thumbnailModel.clearCompletedDownloads()

    def doPreviousFileAction(self):
        pass

    def doNextFileAction(self):
        pass

    def doHelpAction(self):
        webbrowser.open_new_tab("http://www.damonlynch.net/rapid/help.html")

    def doReportProblemAction(self):

        log_path, log_file = os.path.split(iplogging.full_log_file_path())
        log_uri = pathname2url(log_path)

        message = _(r"""<b>Thank you for reporting a problem in Rapid Photo
            Downloader</b><br><br>
            Please report the problem at <a href="{website}">{website}</a>.<br><br>
            If relevant, attach the log file <i>{log_file}</i> to your report (click
            <a href="{log_path}">here</a> to open the log directory).
            """).format(website='https://bugs.launchpad.net/rapid', log_path=log_uri,
                        log_file=log_file)

        errorbox = self.standardMessageBox(message=message, rich_text=True)
        errorbox.exec_()

    def doMakeDonationAction(self):
        webbrowser.open_new_tab("http://www.damonlynch.net/rapid/donate.html")

    def doTranslateApplicationAction(self):
        webbrowser.open_new_tab("http://www.damonlynch.net/rapid/translate.html")

    def doAboutAction(self):
        about = AboutDialog(self)
        about.exec()

    def standardMessageBox(self, message: str, rich_text: bool) -> QMessageBox:
        """
        Create a standard messagebox to be displayed to the user

        :param message: the text to display
        :param rich_text: whether it text to display is in HTML format
        :return: the message box
        """

        msgBox = QMessageBox()
        icon = QPixmap(':/rapid-photo-downloader.svg')
        title = _("Rapid Photo Downloader")
        if rich_text:
            msgBox.setTextFormat(Qt.RichText)
        msgBox.setIconPixmap(icon)
        msgBox.setWindowTitle(title)
        msgBox.setText(message)
        return msgBox

    @pyqtSlot(bool)
    def thisComputerToggleValueChanged(self, on: bool) -> None:
        """
        Respond to This Computer Toggle Switch

        :param on: whether swich is on or off
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

        :param on: whether swich is on or off
        """

        self.prefs.device_autodetection = on
        if not on:
            for scan_id in list(self.devices.volumes_and_cameras):
                self.removeDevice(scan_id=scan_id, adjust_temporal_proximity=False)
            if len(self.devices) == 0:
                self.temporalProximity.setState(TemporalProximityState.empty)
            else:
                self.generateTemporalProximityTableData("devices were removed as a download source")
        else:
            # This is a real hack -- but I don't know a better way to let the
            # slider redraw itself
            QTimer.singleShot(100, self.devicesViewToggledOn)
        self.adjustLeftPanelSliderHandles()

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
            message = _("<b>Changing This Computer source path</b><br><br>Do you really want to "
                        "change the source path to %(new_path)s?<br><br>You are currently "
                        "downloading from %(source_path)s.<br><br>"
                        "If you do change the path, the current download from This Computer "
                        "will be cancelled.") % dict(new_path=make_html_path_non_breaking(path),
                                                source_path=make_html_path_non_breaking(
                                                    self.prefs.this_computer_path))

            msgbox = self.standardMessageBox(message=message, rich_text=True)
            msgbox.setIcon(QMessageBox.Question)
            msgbox.setStandardButtons(QMessageBox.Yes|QMessageBox.No)
            if msgbox.exec() == QMessageBox.No:
                self.thisComputerFSView.goToPath(self.prefs.this_computer_path)
                return

        if path != self.prefs.this_computer_path:
            if self.prefs.this_computer_path:
                scan_id = self.devices.scan_id_from_path(self.prefs.this_computer_path,
                                                         DeviceType.path)
                if scan_id is not None:
                    logging.debug("Removing path from device view %s",
                                  self.prefs.this_computer_path)
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
                self.generateProvisionalDownloadFolders()
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
            msgbox = self.standardMessageBox(message=message, rich_text=False)
            msgbox.setIcon(QMessageBox.Warning)
            msgbox.exec()

        else:
            problematic = path in self.fileSystemModel.preview_subfolders

        if not problematic and path in self.fileSystemModel.download_subfolders:
            message = _("<b>Confirm Download Destination</b><br><br>Are you sure you want to set "
                        "the %(file_type)s download destination to %(path)s?") % dict(
                        file_type=file_type.name, path=make_html_path_non_breaking(path))
            msgbox = self.standardMessageBox(message=message, rich_text=True)
            msgbox.setStandardButtons(QMessageBox.Yes|QMessageBox.No)
            msgbox.setIcon(QMessageBox.Question)
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
            self.generateProvisionalDownloadFolders()
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
                self.generateProvisionalDownloadFolders()
                self.videoDestinationDisplay.setDestination(path=path)
                self.setDownloadCapabilities()
        else:
            logging.error("Invalid video download destination chosen: %s", path)
            self.handleInvalidDownloadDestination(file_type=FileType.video)

    @pyqtSlot()
    def downloadButtonClicked(self) -> None:
        if self.copyfilesmq.paused:
            logging.debug("Download resumed")
            self.resumeDownload()
        else:
            logging.debug("Download activated")

            if self.downloadIsRunning():
                self.pauseDownload()
            else:
                if self.job_code.need_to_prompt():
                    self.job_code.get_job_code()
                else:
                    self.startDownload()

    def pauseDownload(self) -> None:
        """
        Pause the copy files processes
        """

        self.dl_update_timer.stop()
        self.copyfilesmq.pause()
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
        self.copyfilesmq.resume()
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
                if self.download_tracker.all_files_backed_up():
                    return False
                else:
                    return True
            else:
                return False
        else:
            return True

    def downloadPaused(self) -> bool:
        return self.copyfilesmq.paused

    def startDownload(self, scan_id: int=None) -> None:
        """
        Start download, renaming and backup of files.

        :param scan_id: if specified, only files matching it will be
        downloaded
        """
        logging.debug("Start Download phase 1 has started")

        self.download_files = self.thumbnailModel.getFilesMarkedForDownload(scan_id)

        # model, port
        camera_unmounts_called = set()  # type: Set[Tuple(str, str)]
        stop_thumbnailing_cmd_issued = False

        stop_thumbnailing = [scan_id for scan_id in self.download_files.camera_access_needed
                             if scan_id in self.devices.thumbnailing]
        for scan_id in stop_thumbnailing:
            device = self.devices[scan_id]
            if not scan_id in self.thumbnailModel.thumbnailmq.thumbnail_manager:
                logging.debug("Not terminating thumbnailing of %s because it's not in the "
                              "thumbnail manager", device.display_name)
            else:
                logging.debug("Terminating thumbnailing for %s because a download is starting",
                              device.display_name)
                self.thumbnailModel.terminateThumbnailGeneration(scan_id)
                self.devices.cameras_to_stop_thumbnailing.add(scan_id)
                stop_thumbnailing_cmd_issued = True

        if self.gvfsControlsMounts:
            mount_points = {}
            # If a device was being thumbnailed, then it wasn't mounted by GVFS
            # Therefore filter out the cameras we've already requested their
            # thumbnailing be stopped
            still_to_check = [scan_id for scan_id in self.download_files.camera_access_needed
                              if scan_id not in stop_thumbnailing]
            for scan_id in still_to_check:
                # This next value is likely *always* True, but check nonetheless
                if self.download_files.camera_access_needed[scan_id]:
                    device = self.devices[scan_id]
                    model = device.camera_model
                    port = device.camera_port
                    mount_point = self.gvolumeMonitor.cameraMountPoint(model, port)
                    if mount_point is not None:
                        self.devices.cameras_to_gvfs_unmount_for_download.add(scan_id)
                        camera_unmounts_called.add((model, port))
                        mount_points[(model, port)] = mount_point
            if len(camera_unmounts_called):
                logging.info("%s camera(s) need to be unmounted by GVFS before the download begins",
                              len(camera_unmounts_called))
                for model, port in camera_unmounts_called:
                    self.gvolumeMonitor.unmountCamera(model, port,
                          download_starting=True,
                          mount_point=mount_points[(model, port)])

        if not camera_unmounts_called and not stop_thumbnailing_cmd_issued:
            self.startDownloadPhase2()

    def startDownloadPhase2(self) -> None:
        logging.debug("Start Download phase 2 has started")
        download_files = self.download_files

        invalid_dirs = self.invalidDownloadFolders(download_files.download_types)

        if invalid_dirs:
            if len(invalid_dirs) > 1:
                msg = _("These download folders are invalid:\n%("
                        "folder1)s\n%(folder2)s")  % {
                        'folder1': invalid_dirs[0], 'folder2': invalid_dirs[1]}
            else:
                msg = _("This download folder is invalid:\n%s") % invalid_dirs[0]
            self.log_error(ErrorType.critical_error, _("Download cannot proceed"), msg)
        else:
            missing_destinations = self.backupDestinationsMissing(download_files.download_types)
            if missing_destinations is not None:
                # Warn user that they have specified that they want to
                # backup a file type, but no such folder exists on backup
                # devices
                if not missing_destinations[0]:
                    logging.warning("No backup device contains a valid "
                                    "folder for backing up photos")
                    msg = _("No backup device contains a valid folder for "
                            "backing up %(filetype)s") % {'filetype': _(
                            'photos')}
                else:
                    logging.warning("No backup device contains a valid "
                                    "folder for backing up videos")
                    msg = _("No backup device contains a valid folder for "
                            "backing up %(filetype)s") % {'filetype': _(
                            'videos')}

                self.logError(ErrorType.warning, _("Backup problem"), msg)

            # Suppress showing a notification message about any timeline
            # and provisional folders rebuild - download takes priority
            self.ctime_notification_issued = False

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

            # disable refresh and preferences change while download is
            # occurring
            #TODO include destinations and source!
            self.enablePrefsAndRefresh(enabled=False)

            # notify renameandmovefile process to read any necessary values
            # from the program preferences
            data = RenameAndMoveFileData(message=RenameAndMoveStatus.download_started)
            self.renamemq.send_message_to_worker(data)

            # Maximum value of progress bar may have been set to the number
            # of thumbnails being generated. Reset it to use a percentage.
            #TODO confirm it's best to set this here
            self.downloadProgressBar.setMaximum(100)

            for scan_id in download_files.files:
                files = download_files.files[scan_id]
                # if generating thumbnails for this scan_id, stop it
                if self.thumbnailModel.terminateThumbnailGeneration(scan_id):
                    generate_thumbnails = self.thumbnailModel.markThumbnailsNeeded(files)
                else:
                    generate_thumbnails = False

                self.downloadFiles(files, scan_id,
                                   download_files.download_stats[scan_id],
                                   generate_thumbnails)

            self.setDownloadActionLabel()

    def downloadFiles(self, files: list,
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
            download_size += ((self.backup_devices.no_photo_backup_devices *
                               download_stats.photos_size_in_bytes) + (
                               self.backup_devices.no_video_backup_devices *
                               download_stats.videos_size_in_bytes))

        self.time_remaining[scan_id] = download_size
        self.time_check.set_download_mark()

        self.devices.set_device_state(scan_id, DeviceState.downloading)
        self.updateProgressBarState()
        self.immediatelyDisplayDownloadRunningInStatusBar()
        self.setDownloadActionState(True)

        #TODO implement check for not paused
        if not self.dl_update_timer.isActive():
            self.dl_update_timer.start()


        if self.autoStart(scan_id) and self.prefs.generate_thumbnails:
            for rpd_file in files:
                rpd_file.generate_thumbnail = True
            generate_thumbnails = True

        verify_file = self.prefs.verify_file
        if verify_file:
            # since a file might be modified in the file modify process,
            # if it will be backed up, need to refresh the md5 once it has
            # been modified
            refresh_md5_on_file_change = self.prefs.backup_files
        else:
            refresh_md5_on_file_change = False

        # Initiate copy files process

        device = self.devices[scan_id]
        copyfiles_args = CopyFilesArguments(scan_id=scan_id,
                                device=device,
                                photo_download_folder=photo_download_folder,
                                video_download_folder=video_download_folder,
                                files=files,
                                verify_file=verify_file,
                                generate_thumbnails=generate_thumbnails,
                                log_gphoto2=self.log_gphoto2)

        self.copyfilesmq.start_worker(scan_id, copyfiles_args)

    @pyqtSlot(int, str, str)
    def tempDirsReceivedFromCopyFiles(self, scan_id: int,
                                      photo_temp_dir: str,
                                      video_temp_dir: str) -> None:
        self.fileSystemFilter.setTempDirs([photo_temp_dir, video_temp_dir])
        self.temp_dirs_by_scan_id[scan_id] = list(filter(None,[photo_temp_dir,
                                                  video_temp_dir]))

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

    @pyqtSlot(bool, RPDFile, int)
    def copyfilesDownloaded(self, download_succeeded: bool,
                            rpd_file: RPDFile,
                            download_count: int) -> None:

        self.download_tracker.set_download_count_for_file(rpd_file.uid, download_count)
        self.download_tracker.set_download_count(rpd_file.scan_id, download_count)
        rpd_file.download_start_time = self.download_start_datetime
        rpd_file.job_code = self.job_code.job_code
        data = RenameAndMoveFileData(rpd_file=rpd_file,
                                     download_count=download_count,
                                     download_succeeded=download_succeeded)
        self.renamemq.rename_file(data)

    @pyqtSlot(bytes)
    def copyfilesBytesDownloaded(self, pickled_data: bytes) -> None:
        data = pickle.loads(pickled_data) # type: CopyFilesResults
        scan_id = data.scan_id
        total_downloaded = data.total_downloaded
        chunk_downloaded = data.chunk_downloaded
        assert total_downloaded >= 0
        assert chunk_downloaded >= 0
        self.download_tracker.set_total_bytes_copied(scan_id, total_downloaded)
        self.time_check.increment(bytes_downloaded=chunk_downloaded)
        self.time_remaining.update(scan_id, bytes_downloaded=chunk_downloaded)
        self.updateFileDownloadDeviceProgress()

    @pyqtSlot(int)
    def copyfilesFinished(self, scan_id: int) -> None:
        if scan_id in self.devices:
            logging.debug("All files finished copying for %s", self.devices[scan_id].display_name)

    @pyqtSlot(bool, RPDFile, int)
    def fileRenamedAndMoved(self, move_succeeded: bool, rpd_file: RPDFile,
                            download_count: int) -> None:
        scan_id = rpd_file.scan_id

        if scan_id not in self.devices:
            logging.debug("Ignoring file %s because the device has been removed",
                          rpd_file.download_full_file_name)
            return

        if rpd_file.mdatatime_caused_ctime_change and scan_id not in \
                self.thumbnailModel.ctimes_differ:
            self.thumbnailModel.addCtimeDisparity(rpd_file=rpd_file)

        if self.thumbnailModel.send_to_daemon_thumbnailer(rpd_file=rpd_file):
            logging.debug("Assigning daemon thumbnailer to work on %s",
                          rpd_file.download_full_file_name)
            self.thumbnaildaemonmq.send_message_to_worker(ThumbnailDaemonData(
                rpd_file=rpd_file,
                write_fdo_thumbnail=self.prefs.save_fdo_thumbnails,
                use_thumbnail_cache=self.prefs.use_thumbnail_cache
            ))

        if rpd_file.status == DownloadStatus.downloaded_with_warning:
            self.logError(ErrorType.warning, rpd_file.error_title,
                           rpd_file.error_msg, rpd_file.error_extra_detail)

        if self.prefs.backup_files:
            if self.backup_devices.backup_possible(rpd_file.file_type):
                self.backupFile(rpd_file, move_succeeded, download_count)
            else:
                self.fileDownloadFinished(move_succeeded, rpd_file)
        else:
            self.fileDownloadFinished(move_succeeded, rpd_file)

    @pyqtSlot(RPDFile, QPixmap)
    def thumbnailReceivedFromDaemon(self, rpd_file: RPDFile, thumbnail: Optional[QPixmap]) -> None:
        self.thumbnailModel.thumbnailReceived(rpd_file=rpd_file, thumbnail=thumbnail)

    @pyqtSlot(int)
    def thumbnailGenerationStopped(self, scan_id: int) -> None:
        """
        Slot for when a the thumbnail worker has been forcefully stopped,
        rather than merely finished in its work

        :param scan_id: scan_id of the device that was being thumbnailed
        """
        if scan_id not in self.devices:
            logging.debug("Ignoring scan_id %s from terminated thumbailing, as its device does "
                          "not exist anymore", scan_id)
        else:
            device = self.devices[scan_id]
            if scan_id in self.devices.cameras_to_stop_thumbnailing:
                self.devices.cameras_to_stop_thumbnailing.remove(scan_id)
                logging.debug("Thumbnailing sucessfully terminated for %s", device.display_name)
                if not self.devices.download_start_blocked():
                    self.startDownloadPhase2()
            else:
                logging.debug("Ignoring the termination of thumbnailing from %s, as it's "
                              "not for a camera from which a download was waiting to be started",
                              device.display_name)

    def backupFile(self, rpd_file: RPDFile, move_succeeded: bool,
                   download_count: int) -> None:
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
                (rpd_file.file_type == FileType.photo and backup_type ==
                 BackupLocationType.photos) or
                (rpd_file.file_type == FileType.video and backup_type ==
                 BackupLocationType.videos))
            if do_backup:
                logging.debug("Backing up to %s", path)
            else:
                logging.debug("Not backing up to %s", path)
            # Even if not going to backup to this device, need to send it
            # anyway so progress bar can be updated. Not this most efficient
            # but the code is much more simple
            # TODO: check if this is still correct with new code!

            device_id = self.backup_devices.device_id(path)
            data = BackupFileData(rpd_file, move_succeeded, do_backup,
                                  path_suffix,
                                  self.prefs.backup_duplicate_overwrite,
                                  self.prefs.verify_file, download_count,
                                  self.prefs.save_fdo_thumbnails)
            self.backupmq.backup_file(data, device_id)

    @pyqtSlot(int, bool, bool, RPDFile)
    def fileBackedUp(self, device_id: int, backup_succeeded: bool, do_backup: bool,
                     rpd_file: RPDFile) -> None:

        # Only show an error message if there is more than one device
        # backing up files of this type - if that is the case,
        # do not want to rely on showing an error message in the
        # function file_download_finished, as it is only called once,
        # when all files have been backed up
        if not backup_succeeded and self.backup_devices.multiple_backup_devices(
                rpd_file.file_type) and do_backup:
            # TODO implement error notification on backups
            pass
            # self.log_error(config.SERIOUS_ERROR,
            #     rpd_file.error_title,
            #     rpd_file.error_msg, rpd_file.error_extra_detail)

        if do_backup:
            self.download_tracker.file_backed_up(rpd_file.scan_id, rpd_file.uid)
            if self.download_tracker.file_backed_up_to_all_locations(
                    rpd_file.uid, rpd_file.file_type):
                logging.debug("File %s will not be backed up to any more locations",
                              rpd_file.download_name)
                self.fileDownloadFinished(backup_succeeded, rpd_file)

    @pyqtSlot(bytes)
    def backupFileBytesBackedUp(self, pickled_data: bytes) -> None:
        data = pickle.loads(pickled_data) # type: BackupResults
        scan_id = data.scan_id
        chunk_downloaded = data.chunk_downloaded
        self.download_tracker.increment_bytes_backed_up(scan_id, chunk_downloaded)
        self.time_check.increment(bytes_downloaded=chunk_downloaded)
        self.time_remaining.update(scan_id, bytes_downloaded=chunk_downloaded)
        self.updateFileDownloadDeviceProgress()

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

    @pyqtSlot()
    def fileRenamedAndMovedFinished(self) -> None:
        pass

    def isDownloadCompleteForScan(self, scan_id: int, uid: bytes) -> Tuple[bool, int]:
        """
        Determine if all files have been downloaded and backed up for a device

        :param scan_id: device's scan id
        :param uid: uid of an rpd_file, used to determine the download count
        :return: True if the download is completed for that scan_id,
        and the number of files remaining for the scan_id, BUT
        the files remaining value is valid ONLY if the download is
         completed
        """

        files_downloaded = self.download_tracker.get_download_count_for_file(uid)
        files_to_download = self.download_tracker.get_no_files_in_download(scan_id)
        completed = files_downloaded == files_to_download
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
            self.desktop_launcher.set_property('progress', percent_complete)
            self.desktop_launcher.set_property('progress_visible', True)

    def fileDownloadFinished(self, succeeded: bool, rpd_file: RPDFile) -> None:
        """
        Called when a file has been downloaded i.e. copied, renamed,
        and backed up
        """
        scan_id = rpd_file.scan_id
        uid = rpd_file.uid
        # Update error log window if neccessary
        if not succeeded and not self.backup_devices.multiple_backup_devices(
                rpd_file.file_type):
            self.logError(ErrorType.serious_error, rpd_file.error_title,
                           rpd_file.error_msg, rpd_file.error_extra_detail)
        elif self.prefs.move:
            # record which files to automatically delete when download
            # completes
            self.download_tracker.add_to_auto_delete(rpd_file)

        self.thumbnailModel.updateStatusPostDownload(rpd_file)
        self.download_tracker.file_downloaded_increment(scan_id,
                                                        rpd_file.file_type,
                                                        rpd_file.status)

        device = self.devices[scan_id]
        device.download_statuses.add(rpd_file.status)

        completed, files_remaining = self.isDownloadCompleteForScan(scan_id, uid)

        # if self.downloadIsRunning():
        #     self.updateTimeRemaining()

        if completed:
            device_finished = files_remaining == 0
            if device_finished:
                logging.debug("All files from %s are downloaded; none remain", device.display_name)
                state = DeviceState.finished
            else:
                logging.debug("Download finished from %s; %s remain be be potentially downloaded",
                              device.display_name, files_remaining)
                state = DeviceState.idle

            self.devices.set_device_state(scan_id=scan_id, state=state)
            # Setting the spinner state also sets the
            self.mapModel(scan_id).setSpinnerState(scan_id, state)

            # Rebuild temporal proximity if it needs it
            if scan_id in self.thumbnailModel.ctimes_differ and not \
                    self.thumbnailModel.filesRemainToDownload(scan_id=scan_id):
                self.thumbnailModel.processCtimeDisparity(scan_id=scan_id)

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
                if self.unity_progress:
                    self.desktop_launcher.set_property('progress_visible', False)

                # Update prefs with stored sequence number and downloads today
                # values
                data = RenameAndMoveFileData(message=RenameAndMoveStatus.download_completed)
                self.renamemq.send_message_to_worker(data)

                if ((self.prefs.auto_exit and self.download_tracker.no_errors_or_warnings())
                                                or self.prefs.auto_exit_force):
                    if not self.thumbnailModel.filesRemainToDownload():
                        self.quit()

                self.download_tracker.purge_all()

                self.setDownloadActionLabel()
                self.setDownloadCapabilities()

                self.job_code.job_code = ''
                self.download_start_datetime = None
                self.download_start_time = None

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
                message = '%(downloading_from)s — %(time_left)s left (%(speed)s)' % dict(
                    downloading_from = downloading, time_left=time_remaining, speed=download_speed)
            self.statusBar().showMessage(message)

    def enablePrefsAndRefresh(self, enabled: bool) -> None:
        """
        Disable the user being to access the refresh command or change
        program preferences while a download is occurring.

        :param enabled: if True, then the user is able to activate the
        preferences and refresh commands.
        """

        self.refreshAct.setEnabled(enabled)
        self.preferencesAct.setEnabled(enabled)

    def unmountVolume(self, scan_id: int) -> None:
        """
        Cameras are already unmounted, so no need to unmount them!
        :param scan_id: the scan id of the device to be umounted
        """

        device = self.devices[scan_id]  # type: Device

        if device.device_type == DeviceType.volume:
            #TODO implement device unmounting
            if self.gvfsControlsMounts:
                #self.gvolumeMonitor.
                pass
            else:
                #self.udisks2Monitor.
                pass

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

        notification_name  = device.name()

        no_photos_downloaded = self.download_tracker.get_no_files_downloaded(
                                            scan_id, FileType.photo)
        no_videos_downloaded = self.download_tracker.get_no_files_downloaded(
                                            scan_id, FileType.video)
        no_photos_failed = self.download_tracker.get_no_files_failed(
                                            scan_id, FileType.photo)
        no_videos_failed = self.download_tracker.get_no_files_failed(
                                            scan_id, FileType.video)
        no_files_downloaded = no_photos_downloaded + no_videos_downloaded
        no_files_failed = no_photos_failed + no_videos_failed
        no_warnings = self.download_tracker.get_no_warnings(scan_id)

        file_types = file_types_by_number(no_photos_downloaded,
                                               no_videos_downloaded)
        file_types_failed = file_types_by_number(no_photos_failed,
                                                      no_videos_failed)
        # Translators: e.g. 23 photos downloaded
        message = _("%(noFiles)s %(filetypes)s downloaded") % {
            'noFiles': thousands(no_files_downloaded), 'filetypes': file_types}

        if no_files_failed:
            # Translators: e.g. 2 videos failed to download
            message += "\n" + _("%(noFiles)s %(filetypes)s failed to download") % {
                              'noFiles': thousands(no_files_failed),
                              'filetypes': file_types_failed}

        if no_warnings:
            message = "%s\n%s " % (message, no_warnings) + _("warnings")

        message_shown = False
        if self.have_libnotify:
            n = Notify.Notification.new(notification_name, message, 'rapid-photo-downloader')
            try:
                message_shown =  n.show()
            except:
                logging.error("Unable to display downloaded from device message using notification "
                              "system")
            if not message_shown:
                logging.error("Unable to display downloaded from device message using notification "
                              "system")
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
            n_message += "\n" + _("%(number)s %(numberdownloaded)s") % dict(
                              number=thousands(photo_downloads),
                              numberdownloaded=_("%(filetype)s downloaded") % dict(
                                                 filetype=filetype))

        # photo failures
        photo_failures = self.download_tracker.total_photo_failures
        if photo_failures and show_notification:
            filetype = file_types_by_number(photo_failures, 0)
            n_message += "\n" + _("%(number)s %(numberdownloaded)s") % dict(
                              number=thousands(photo_failures),
                              numberdownloaded=_("%(filetype)s failed to download") % dict(
                                                   filetype=filetype))

        # video downloads
        video_downloads = self.download_tracker.total_videos_downloaded
        if video_downloads and show_notification:
            filetype = file_types_by_number(0, video_downloads)
            n_message += "\n" + _("%(number)s %(numberdownloaded)s") % dict(
                               number=thousands(video_downloads),
                               numberdownloaded=_("%(filetype)s downloaded") % dict(
                                                  filetype=filetype))

        # video failures
        video_failures = self.download_tracker.total_video_failures
        if video_failures and show_notification:
            filetype = file_types_by_number(0, video_failures)
            n_message += "\n" + _("%(number)s %(numberdownloaded)s") % dict(
                               number=thousands(video_failures),
                               numberdownloaded=_("%(filetype)s failed to download") % dict(
                                                  filetype=filetype))

        # warnings
        warnings = self.download_tracker.total_warnings
        if warnings and show_notification:
            n_message += "\n" + _("%(number)s %(numberdownloaded)s") % dict(
                                  number=thousands(warnings),
                                  numberdownloaded=_("warnings"))

        if show_notification:
            message_shown = False
            if self.have_libnotify:
                n = Notify.Notification.new(_('Rapid Photo Downloader'), n_message,
                                            'rapid-photo-downloader')
                try:
                    message_shown = n.show()
                except:
                    logging.error("Unable to display download complete message using notification "
                                  "system")
            if not message_shown:
                logging.error("Unable to display download complete message using notification "
                              "system")

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
                    {FileType.photo: photo_downloads, FileType.video: video_downloads})
            no_files_and_types = ftc.file_types_present_details().lower()

            if not fw:
                downloaded = _('Downloaded %(no_files_and_types)s from %(devices)s') % dict(
                                no_files_and_types=no_files_and_types, devices=devices)
            else:
                downloaded = _('Downloaded %(no_files_and_types)s from %(devices)s — %(failures)s')\
                             % dict(no_files_and_types=no_files_and_types,
                                    devices=devices, failures=fw)
        else:
            if fw:
                downloaded = _('No files downloaded — %failures)s') % dict(failures=fw)
            else:
                downloaded = _('No files downloaded')
        logging.info('%s', downloaded)
        self.statusBar().showMessage(downloaded)

    def notifyFoldersProximityRebuild(self, scan_id) -> None:
        """
        Inform the user that a timeline rebuild and folder preview update is pending,
        taking into account they may have already been notified.
        """

        if self.have_libnotify:
            device = self.devices[scan_id]
            notification_devices = self.thumbnailModel.ctimes_differ

            logging.info("Need to rebuild timeline and subfolder previews for %s",
                          device.display_name)

            simple_message = len(notification_devices) == 1

            this_computer = len([scan_id for scan_id in notification_devices
                                 if self.devices[scan_id].device_type == DeviceType.path]) > 0

            if simple_message:
                if device.device_type == DeviceType.camera:
                    message = _("The Destination subfolders and Timeline will be rebuilt after "
                                "all thumbnails have been generated for the %(camera)s"
                                ) % dict(camera=device.display_name)
                elif this_computer:
                    message = _("The Destination subfolders and Timeline will be rebuilt after "
                                "all thumbnails have been generated for this computer")
                else:
                    message = _("The Destination subfolders and Timeline will be rebuilt after "
                                "all thumbnails have been generated for %(device)s"
                                ) % dict(device=device.display_name)
            else:
                no_devices = len(notification_devices)
                if this_computer:
                    no_devices -= 1
                    if no_devices > 1:
                        message = _("The Destination subfolders and Timeline will be rebuilt "
                                    "after all thumbnails have been generated for "
                                    "%(number_devices)s devices and this computer"
                                    ) % dict(number_devices=no_devices)
                    else:
                        assert no_devices == 1
                        if device.device_type != DeviceType.path:
                            other_device = device
                        else:
                            # the other device must be the first one
                            other_device = self.devices[notification_devices[0]]
                        name = other_device.display_name
                        if other_device.device_type == DeviceType.camera:
                            message = _("The Destination subfolders and Timeline will be rebuilt "
                                        "after all thumbnails have been generated for the "
                                        "%(camera)s and this computer") % dict(camera=name)
                        else:
                            message = _("The Destination subfolders and Timeline will be rebuilt "
                                        "after all thumbnails have been generated for "
                                        "%(device)s and this computer") % dict(device=name)
                else:
                        message = _("The Destination subfolders and Timeline will be rebuilt "
                                    "after all thumbnails have been generated for "
                                    "%(number_devices)s devices") % dict(number_devices=no_devices)

            if self.ctime_update_notification is None:
                notify = Notify.Notification.new(_('Rapid Photo Downloader'), message,
                                                 'rapid-photo-downloader')
            else:
                notify = self.ctime_update_notification
                notify.update(_('Rapid Photo Downloader'), message, 'rapid-photo-downloader')
            try:
                message_shown = notify.show()
                if message_shown:
                    self.ctime_notification_issued = True
                notify.connect('closed', self.notificationFoldersProximityRefreshClosed)
            except:
                logging.error("Unable to display message using notification system")
            self.ctime_update_notification = notify

    def notifyFoldersProximityRebuilt(self) -> None:
        """
        Inform the user that the the refresh has occurred, updating the existing
        message if need be.
        """

        if self.have_libnotify:
            message = _("The Destination subfolders and Timeline have been rebuilt")

            if self.ctime_update_notification is None:
                notify = Notify.Notification.new(_('Rapid Photo Downloader'), message,
                                                 'rapid-photo-downloader')
            else:
                notify = self.ctime_update_notification
                notify.update(_('Rapid Photo Downloader'), message, 'rapid-photo-downloader')
            try:
                message_shown = notify.show()
            except:
                logging.error("Unable to display message using notification system")

            self.ctime_update_notification = None

    def notificationFoldersProximityRefreshClosed(self, notify: Notify.Notification) -> None:
        """
        Delete our reference to the notification that was used to inform the user
        that the timeline and preview folders will be. If it's not deleted, there will
        be glib problems at program exit, when the reference is deleted.
        :param notify: the notification itself
        """

        self.ctime_update_notification = None

    def invalidDownloadFolders(self, downloading: DownloadTypes) -> List[str]:
        """
        Checks validity of download folders based on the file types the
        user is attempting to download.

        :return list of the invalid directories, if any, or empty list.
        """

        invalid_dirs = []
        if downloading.photos:
            if not validate_download_folder(self.prefs.photo_download_folder).valid:
                invalid_dirs.append(self.prefs.photo_download_folder)
        if downloading.videos:
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
        message = "<b>%(title)s</b><br><br>%(details)s" % dict(title=title, details=details)
        msgBox = self.standardMessageBox(message=message, rich_text=True)
        msgBox.exec()

    def logError(self, severity, problem, details, extra_detail=None) -> None:
        """
        Display error and warning messages to user in log window
        """
        #TODO implement error log window
        pass
        # self.error_log.add_message(severity, problem, details, extra_detail)

    def backupDestinationsMissing(self, downloading: DownloadTypes) -> BackupMissing:
        """
        Checks if there are backup destinations matching the files
        going to be downloaded
        :param downloading: the types of file that will be downloaded
        :return: None if no problems, or BackupMissing
        """
        photo_missing = video_missing = False
        if self.prefs.backup_files and self.prefs.backup_device_autodetection:
            if downloading.photos and not self.backup_devices.backup_possible(FileType.photo):
                photo_missing = True
            if downloading.videos and not self.backup_devices.backup_possible(FileType.video):
                video_missing = True
            if not(photo_missing or video_missing):
                return None
            else:
                return BackupMissing(photo=photo_missing, video=video_missing)
        return None

    def deviceState(self, scan_id: int) -> DeviceState:
        """
        What the device is being used for at the present moment.

        :param scan_id: device to check
        :return: DeviceState
        """

        return self.devices.device_state[scan_id]

    @pyqtSlot(bytes)
    def scanMessageReceived(self, pickled_data: bytes) -> None:
        """
        Process data received from the scan process.

        The data is pickled because PyQt converts the Python int into
        a C++ int, which unlike Pyhon has an upper limit. Unpickle it
        too early, and the int wraps around to become a negative
        number.
        """

        data = pickle.loads(pickled_data)  # type: ScanResults
        if data.rpd_files is not None:
            # Update scan running totals
            scan_id = data.rpd_files[0].scan_id
            if scan_id not in self.devices:
                return
            device = self.devices[scan_id]
            device.file_type_counter = data.file_type_counter
            device.file_size_sum = data.file_size_sum
            self.mapModel(scan_id).updateDeviceScan(scan_id)

            self.thumbnailModel.addFiles(scan_id=scan_id,
                                         rpd_files=data.rpd_files,
                                         generate_thumbnail=not self.autoStart(scan_id))
            self.generateProvisionalDownloadFolders(rpd_files=data.rpd_files)
        else:
            scan_id = data.scan_id
            if scan_id not in self.devices:
                return
            if data.error_code is not None:

                self.showMainWindow()

                # An error occurred
                error_code = data.error_code
                device = self.devices[scan_id]
                camera_model = device.display_name
                if error_code == CameraErrorCode.locked:
                    title =_('Rapid Photo Downloader')
                    message = _('<b>All files on the %(camera)s are inaccessible</b>.<br><br>It '
                                'may be locked or not configured for file transfers using MTP. '
                                'You can unlock it and try again.<br><br>On some models you also '
                                'need to change the setting <i>USB for charging</i> to <i>USB for '
                                'file transfers</i>.<br><br>Alternatively, you can ignore this '
                                'device.') % {'camera': camera_model}
                else:
                    assert error_code == CameraErrorCode.inaccessible
                    title = _('Rapid Photo Downloader')
                    message = _('<b>The %(camera)s appears to be in use by another '
                                'application.</b><br><br>You '
                                'can close any other application (such as a file browser) that is '
                                'using it and try again. If that '
                                'does not work, unplug the %(camera)s from the computer and plug '
                                'it in again.<br><br>Alternatively, you can ignore '
                                'this device.') % {'camera':camera_model}

                msgBox = QMessageBox(QMessageBox.Warning, title, message,
                                QMessageBox.NoButton, self)
                msgBox.setIconPixmap(self.devices[scan_id].get_pixmap())
                msgBox.addButton(_("&Try Again"), QMessageBox.AcceptRole)
                msgBox.addButton(_("&Ignore This Device"), QMessageBox.RejectRole)
                self.prompting_for_user_action[device] = msgBox
                role = msgBox.exec_()
                if role == QMessageBox.AcceptRole:
                    self.scanmq.resume(worker_id=scan_id)
                else:
                    self.removeDevice(scan_id=scan_id, show_warning=False)
                del self.prompting_for_user_action[device]
            else:
                # Update GUI display and rows DB with definitive camera display name
                device = self.devices[scan_id]
                logging.debug('%s with scan id %s is now known as %s',
                              device.display_name, scan_id, data.optimal_display_name)
                if len(data.storage_space) > 1:
                    logging.debug('%s has %s storage devices',
                              data.optimal_display_name, len(data.storage_space))
                device.update_camera_attributes(display_name=data.optimal_display_name,
                                                storage_space=data.storage_space)
                self.updateSourceButton()
                self.deviceModel.updateDeviceNameAndStorage(scan_id, device)
                self.thumbnailModel.addOrUpdateDevice(scan_id=scan_id)
                self.adjustLeftPanelSliderHandles()

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
            if self.job_code.need_to_prompt_on_auto_start():
                model.setSpinnerState(scan_id, DeviceState.idle)
                self.job_code.get_job_code()
            else:
                if self.downloadPaused():
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

        if not self.prefs.valid:
            return False

        if not self.thumbnailModel.filesAreMarkedForDownload(scan_id):
            logging.debug("No files are marked for download for %s",
                          self.devices[scan_id].display_name)
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

        if len(self.devices.scanning):
            logging.info("Was tasked to generate Timeline because %s, but ignoring request "
                         "because a scan is occurring", reason)            
            return
        
        if self.temporalProximity.state == TemporalProximityState.ctime_rebuild:
            logging.info("Was tasked to generate Timeline because %s, but ignoring request "
                         "because a rebuild is required ", reason)               
            return

        rows = self.thumbnailModel.dataForProximityGeneration()
        if rows:
            logging.info("Generating Timeline because %s", reason)

            self.temporalProximity.setState(TemporalProximityState.generating)
            data = OffloadData(thumbnail_rows=rows, proximity_seconds=self.prefs.proximity_seconds)
            self.offloadmq.assign_work(data)
        else:
            logging.info("Was tasked to generate Timeline because %s, but there is nothing to "
                         "generate", reason)

    def generateProvisionalDownloadFolders(self,
                                           rpd_files: Optional[Sequence[RPDFile]]=None) -> None:
        """
        Generate download subfolders for the rpd files
        """

        logging.debug("Generating provisional download folders")

        destination = DownloadDestination(photo_download_folder=self.prefs.photo_download_folder,
                                          video_download_folder=self.prefs.video_download_folder,
                                          photo_subfolder=self.prefs.photo_subfolder,
                                          video_subfolder=self.prefs.video_subfolder)
        data = OffloadData(rpd_files=rpd_files, destination=destination,
                           strip_characters=self.prefs.strip_characters)
        self.offloadmq.assign_work(data)

    def removeProvisionalDownloadFolders(self, scan_id: int) -> None:
        """
        Remove provisional download folders unique to this scan_id
        using the offload process.

        :param scan_id: scan id of the device
        """

        data = OffloadData(scan_id=scan_id)
        self.offloadmq.assign_work(data)

    @pyqtSlot(TemporalProximityGroups)
    def proximityGroupsGenerated(self, proximity_groups: TemporalProximityGroups) -> None:
        if self.temporalProximity.setGroups(proximity_groups=proximity_groups):
            self.thumbnailModel.assignProximityGroups(proximity_groups.col1_col2_uid)
            if self.ctime_notification_issued:
                self.notifyFoldersProximityRebuilt()
                self.ctime_notification_issued = False

    @pyqtSlot(FoldersPreview)
    def provisionalDownloadFoldersGenerated(self, folders_preview: FoldersPreview) -> None:
        self.fileSystemModel.update_preview_folders(folders_preview=folders_preview)
        self.photoDestinationFSView.expandPreviewFolders(self.prefs.photo_download_folder)
        self.videoDestinationFSView.expandPreviewFolders(self.prefs.video_download_folder)
        # Update the views in case nothing was expanded
        self.photoDestinationFSView.update()
        self.videoDestinationFSView.update()

    def closeEvent(self, event) -> None:
        if self.application_state == ApplicationState.normal:
            self.application_state = ApplicationState.exiting
            self.scanmq.stop()
            self.thumbnailModel.thumbnailmq.stop()
            self.copyfilesmq.stop()

            if self.downloadIsRunning():
                logging.debug("Exiting while download is running. Cleaning up...")
                # Update prefs with stored sequence number and downloads today
                # values
                data = RenameAndMoveFileData(message=RenameAndMoveStatus.download_completed)
                self.renamemq.send_message_to_worker(data)
                # renameandmovefile process will send a message with the
                # updated sequence values. When that occurs,
                # this application will save the sequence values to the
                # program preferences, resume closing and this close event
                # will again be called, but this time the application state
                # flag will indicate the need to resume below.
                event.ignore()
                return
                # Incidentally, it's the renameandmovefile process that
                # updates the SQL database with the file downloads,
                # so no need to update or close it in this main process

        self.writeWindowSettings()
        logging.debug("Cleaning up provisional download folders")
        self.fileSystemModel.remove_preview_folders()

        if self.ctime_update_notification is not None:
            self.ctime_update_notification = None

        self.offloadmq.stop()
        self.offloadThread.quit()
        if not self.offloadThread.wait(500):
            self.offloadmq.forcefully_terminate()

        self.renamemq.stop()
        self.renameThread.quit()
        if not self.renameThread.wait(500):
            self.renamemq.forcefully_terminate()

        self.thumbnaildaemonmq.stop()
        self.thumbnaildaemonmqThread.quit()
        if not self.thumbnaildaemonmqThread.wait(2000):
            self.thumbnaildaemonmq.forcefully_terminate()

        self.scanThread.quit()
        if not self.scanThread.wait(2000):
            self.scanmq.forcefully_terminate()

        self.copyfilesThread.quit()
        if not self.copyfilesThread.wait(1000):
            self.copyfilesmq.forcefully_terminate()

        if self.backup_manager_started:
            self.backupmq.stop()
            self.backupThread.quit()
            if not self.backupThread.wait(1000):
                self.backupmq.forcefully_terminate()

        if not self.gvfsControlsMounts:
            self.udisks2MonitorThread.quit()
            self.udisks2MonitorThread.wait()
            self.cameraHotplugThread.quit()
            self.cameraHotplugThread.wait()

        self.loggermq.stop()
        self.loggermqThread.quit()
        self.loggermqThread.wait()

        self.watchedDownloadDirs.closeWatch()

        self.cleanAllTempDirs()
        logging.debug("Cleaning any device cache dirs")
        self.devices.delete_cache_dirs()
        tc = ThumbnailCacheSql()
        logging.debug("Cleaning up Thumbnail cache")
        tc.cleanup_cache()
        Notify.uninit()

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
            iconNames, canEject = self.gvolumeMonitor.getProps(
                mount.rootPath())
        else:
            # get the system device e.g. /dev/sdc1
            systemDevice = bytes(mount.device()).decode()
            iconNames, canEject = self.udisks2Monitor.get_device_props(
                systemDevice)
        return (iconNames, canEject)

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

        sc = self.gp_context.camera_autodetect()
        system_cameras = ((model, port) for model, port in sc if not
                          port.startswith('disk:'))
        kc = self.devices.cameras.items()
        known_cameras = ((model, port) for port, model in kc)
        removed_cameras = set(known_cameras) - set(system_cameras)
        for model, port in removed_cameras:
            scan_id = self.devices.scan_id_from_camera_model_port(model, port)
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
        print("Implement noGVFSAutoMount()")

    @pyqtSlot()
    def cameraMounted(self):
        if have_gio:
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
            if self.gvolumeMonitor.unmountCamera(model=model, port=port, on_startup=on_startup):
                return True
            else:
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

                logging.debug("Not scanning %s because it could not be unmounted",
                              camera.display_name)

                message = _('<b>The %(camera)s cannot be scanned because it cannot be '
                            'unmounted.</b><br><br>You can close any other application (such as a '
                            'file browser) that is using it and try again. If that does not work, '
                            'unplug the %(camera)s from the computer and plug it in again.') \
                          % dict(camera=camera.display_name)

                # Show the main window if it's not yet visible
                self.showMainWindow()
                msgBox = self.standardMessageBox(message=message, rich_text=True)
                msgBox.setIconPixmap(camera.get_pixmap())
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
                message = _('<b>The download cannot start because the %(camera)s cannot be '
                            'unmounted.</b><br><br>You '
                            'can close any other application (such as a file browser) that is '
                            'using it and try again. If that '
                            'does not work, unplug the %(camera)s from the computer and plug '
                            'it in again, and choose which files you want to download from it.') \
                          % dict(camera=display_name)
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
            cameras = self.gp_context.camera_autodetect()
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
                        # libgphoto2 cannot access a camera when it is mounted
                        # by another process, like Gnome's GVFS or any other
                        # system. Before attempting to scan the camera, check
                        # to see if it's mounted and if so, unmount it.
                        # Unmounting is asynchronous.
                        if not self.unmountCameraToEnableScan(model=model, port=port,
                                                              on_startup=on_startup):
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
        scan_preferences = ScanPreferences(self.prefs.ignored_paths)
        scan_arguments = ScanArguments(scan_preferences=scan_preferences,
                           device=device,
                           ignore_other_types=self.ignore_other_photo_types,
                           log_gphoto2=self.log_gphoto2,
                           use_thumbnail_cache=self.prefs.use_thumbnail_cache,
                           scan_only_DCIM=not self.prefs.device_without_dcim_autodetection)
        self.scanmq.start_worker(scan_id, scan_arguments)
        self.devices.set_device_state(scan_id, DeviceState.scanning)
        self.setDownloadCapabilities()
        self.updateProgressBarState()
        self.displayMessageInStatusBar()

    def partitionValid(self, mount: QStorageInfo) -> bool:
        """
        A valid partition is one that is:
        1) available
        2) if devices without DCIM folders are to be scanned (e.g.
        Portable Storage Devices), then the path should not be
        blacklisted
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
            if (self.prefs.device_without_dcim_autodetection or has_non_empty_dcim_folder(path)):
                if not self.devices.user_marked_volume_as_ignored(path):
                    return True
                else:
                    logging.debug('Not scanning volume with path %s because it was set '
                                  'to be temporarily ignored', path)
            else:
                logging.debug('Not scanning volume with path %s because it lacks a DCIM folder '
                              'with at least one file or folder in it', path)
        return False

    def prepareNonCameraDeviceScan(self, device: Device, on_startup: bool=False) -> None:
        """

        :param device:
        :param on_startup: if True, the search is occurring during
         the program's startup phase
        """

        if not self.devices.known_device(device):
            if (self.scanEvenIfNoDCIM() and not device.path in self.prefs.volume_whitelist):
                logging.debug("Prompting whether to use device %s, which has no DCIM folder",
                              device.display_name)
                # prompt user to see if device should be used or not
                self.showMainWindow()
                use = UseDeviceDialog(device, self)
                if use.exec():
                    if use.remember:
                        logging.debug("Whitelisting device %s", device.display_name)
                        self.prefs.volume_whitelist = self.prefs.volume_whitelist + [
                                                                            device.display_name]
                    self.startDeviceScan(device=device, on_startup=on_startup)
                else:
                    logging.debug("Device %s rejected as a download device", device.display_name)
                    if use.remember and device.display_name not in self.prefs.volume_blacklist:
                        logging.debug("Blacklisting device %s", device.display_name)
                        self.prefs.volume_blacklist = self.prefs.volume_blacklist + [
                                                                            device.display_name]
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
                            self.backup_devices.no_photo_backup_devices,
                            self.backup_devices.no_video_backup_devices)
                        self.displayMessageInStatusBar()

                elif self.shouldScanMount(mount):
                    device = Device()
                    device.set_download_from_volume(path, mount.displayName(),
                                                    iconNames, canEject, mount)
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
            device_id = self.backup_devices.device_id(path)
            self.backupmq.remove_device(device_id)
            del self.backup_devices[path]
            self.displayMessageInStatusBar()
            self.download_tracker.set_no_backup_devices(
                self.backup_devices.no_photo_backup_devices,
                self.backup_devices.no_video_backup_devices)

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
                    logging.warning("Removed device %s was having thumbnails generated", device.name())
                else:
                    logging.info("Device removed: %s", device.name())
            else:
                logging.debug("Device removed: %s", device.name())

            if device in self.prompting_for_user_action:
                self.prompting_for_user_action[device].reject()

            files_removed = self.thumbnailModel.clearAll(scan_id=scan_id,
                                                         keep_downloaded_files=True)
            self.mapModel(scan_id).removeDevice(scan_id)

            was_downloading = self.downloadIsRunning()

            if scan_id in self.scanmq.workers:
                if device_state != DeviceState.scanning:
                    logging.error("Expected device state to be 'scanning'")
                self.scanmq.stop_worker(scan_id)
            elif scan_id in self.copyfilesmq.workers:
                if device_state != DeviceState.downloading:
                    logging.error("Expected device state to be 'downloading'")
                self.copyfilesmq.stop_worker(scan_id)
            # TODO need correct check for "is thumbnailing", given is now asynchronous
            elif scan_id in self.thumbnailModel.thumbnailmq.thumbnail_manager:
                if device_state != DeviceState.thumbnailing:
                    logging.error("Expected device state to be 'thumbnailing'")
                self.thumbnailModel.terminateThumbnailGeneration(scan_id)

            if ignore_in_this_program_instantiation:
                self.devices.ignore_device(scan_id=scan_id)

            self.removeProvisionalDownloadFolders(scan_id=scan_id)

            del self.devices[scan_id]
            self.adjustLeftPanelSliderHandles()

            self.updateSourceButton()
            self.setDownloadCapabilities()

            if adjust_temporal_proximity:
                if len(self.devices) == 0:
                    self.temporalProximity.setState(TemporalProximityState.empty)
                elif files_removed:
                    self.generateTemporalProximityTableData("a download source was removed")

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
        self.removeDevice(scan_id=scan_id)
        if device.device_type == DeviceType.camera:
            self.startCameraScan(device.camera_model, device.camera_port)
        else:
            self.startDeviceScan(device=device)

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
            info_text = _("All cameras, phones and tablets with the same model "
                          "name will be ignored.")
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
                self.prefs.camera_blacklist = self.prefs.camera_blacklist + [device.udev_name]
                logging.debug('Added %s to camera blacklist',device.udev_name)
            else:
                self.prefs.volume_blacklist = self.prefs.volume_blacklist + [device.display_name]
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
                        self.backup_devices[path] = BackupDevice(mount=mount,
                                                     backup_type=backup_type)
                        self.addDeviceToBackupManager(path)
        else:
            self.setupManualBackup()
            for path in self.backup_devices:
                self.addDeviceToBackupManager(path)

        self.download_tracker.set_no_backup_devices(
            self.backup_devices.no_photo_backup_devices,
            self.backup_devices.no_video_backup_devices)

    def setupNonCameraDevices(self, on_startup: bool=False) -> None:
        """
        Setup devices from which to download and initiates their scan.

        :param on_startup: if True, the search is occurring during
         the program's startup phase
        """

        if not self.prefs.device_autodetection:
            return

        mounts = [] # type: List[QStorageInfo]
        for mount in self.validMounts.mountedValidMountPoints():
            if self.partitionValid(mount):
                path = mount.rootPath()
                if path not in self.backup_devices and self.shouldScanMount(mount):
                    logging.debug("Will scan %s", mount.displayName())
                    mounts.append(mount)
                else:
                    logging.debug("Will not scan %s", mount.displayName())

        for mount in mounts:
            icon_names, can_eject = self.getIconsAndEjectableForMount(mount)
            device = Device()
            device.set_download_from_volume(mount.rootPath(),
                                          mount.displayName(),
                                          icon_names,
                                          can_eject,
                                          mount)
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
                logging.debug("This Computer path %s rejected as download source",
                              self.prefs.this_computer_path)
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
        backup_args = BackupArguments(path, self.backup_devices.name(path))
        self.backupmq.add_device(device_id, backup_args)

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

    def isBackupPath(self, path: str) -> BackupLocationType:
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

    def clearNonRunningDownloads(self):
        """
        Clears the display of downloads that are currently not running
        """

        #TODO implement once UI is more complete
        # Stop any processes currently scanning or creating thumbnails
        pass

        # Remove them from the user interface
        # for scan_pid in self.device_collection.get_all_displayed_processes():
        #     if scan_pid not in self.download_active_by_scan_pid:
        #         self.device_collection.remove_device(scan_pid)
        #         self.thumbnails.clear_all(scan_pid=scan_pid)

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
            logging.debug("Photo download destination %s is now invalid",
                          self.prefs.photo_download_folder)
            self.handleInvalidDownloadDestination(file_type=FileType.photo, do_update=False)

        if self.prefs.video_download_folder and not validate_download_folder(
                self.prefs.video_download_folder).valid:
            valid = False
            logging.debug("Video download destination %s is now invalid",
                          self.prefs.video_download_folder)
            self.handleInvalidDownloadDestination(file_type=FileType.video, do_update=False)

        if not valid:
            self.watchedDownloadDirs.updateWatchPathsFromPrefs(self.prefs)
            self.generateProvisionalDownloadFolders()
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
        if path in ('/media', '/run', os.path.expanduser('~'), '/', '/bin', '/boot', '/dev',
                    '/lib', '/lib32', '/lib64', '/mnt', '/opt', '/sbin', '/snap', '/sys', '/tmp',
                    '/usr', '/var', '/proc'):
            message = "<b>" + _("Downloading from %(location)s on This Computer.") % dict(
                location=make_html_path_non_breaking(path)) + "</b><br><br>" + _(
                "Do you really want to download from here?<br><br>On some systems, scanning this "
                "location can take a very long time.")
            msgbox = self.standardMessageBox(message=message, rich_text=True)
            msgbox.setStandardButtons(QMessageBox.Yes|QMessageBox.No)
            return msgbox.exec() == QMessageBox.Yes
        return True

    def scanEvenIfNoDCIM(self) -> bool:
        """
        Determines if partitions should be scanned even if there is
        no DCIM folder present in the base folder of the file system.

        This is necessary when both portable storage device automatic
        detection is on, and downloading from automatically detected
        partitions is on.
        :return: True if scans of such partitions should occur, else
        False
        """
        return (self.prefs.device_autodetection and
                self.prefs.device_without_dcim_autodetection)

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
            if self.downloadPaused():
                downloading = self.devices.downloading_from()
                # Translators - in the middle is a unicode em dash - please retain it
                # This string is displayed in the status bar when the download is paused
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
                    files_checked = _('%(number)s of %(available files)s checked for download (%('
                                       'hidden)s hidden)') % {
                                       'number': thousands(files_to_download),
                                       'available files': files_avilable_sum,
                                       'hidden': files_hidden}
                else:
                    files_checked = _('%(number)s of %(available files)s checked for download') % {
                                       'number': thousands(files_to_download),
                                       'available files': files_avilable_sum}
                msg = files_checked
            else:
                msg = ''
        self.statusBar().showMessage(msg)

    def generateBasicStatusMessage(self) -> str:

        # No longer used - candidate for deletion
        msg = ''
        if self.prefs.backup_files:
            if not self.prefs.backup_device_autodetection:
                if self.prefs.backup_photo_location ==  self.prefs.backup_video_location:
                    # user manually specified the same location for photos
                    # and video backups
                    pass
                    # msg = _('Backing up photos and videos to %(path)s') % {
                    #     'path':self.prefs.backup_photo_location}
                else:
                    # user manually specified different locations for photo
                    # and video backups
                    pass
                    # msg = _('Backing up photos to %(path)s and videos to %(path2)s')  % {
                    #          'path': self.prefs.backup_photo_location,
                    #          'path2': self.prefs.backup_video_location}
            else:
                msg = self.displayBackupMounts()
            # msg = "%(backuppaths)s." % dict(backuppaths=msg)
        return msg.rstrip()

    def displayBackupMounts(self) -> str:
        """
        Create a message to be displayed to the user showing which
        backup mounts will be used
        :return the string to be displayed
        """

        # No longer used - candidate for deletion

        message =  ''

        # backup_device_names = [self.backup_devices.name(path) for path in
        #                   self.backup_devices]
        # message = make_internationalized_list(backup_device_names)
        #
        # if len(backup_device_names) > 1:
        #     message = _("Using backup devices %(devices)s") % dict(
        #         devices=message)
        # elif len(backup_device_names) == 1:
        #     message = _("Using backup device %(device)s")  % dict(
        #         device=message)
        # else:
        #     message = _("No backup devices detected")
        # return message


class QtSingleApplication(QApplication):
    """
    Taken from
    http://stackoverflow.com/questions/12712360/qtsingleapplication
    -for-pyside-or-pyqt
    """

    messageReceived = QtCore.pyqtSignal(str)

    def __init__(self, programId: str, *argv) -> None:
        super().__init__(*argv)
        self._id = programId
        self._activationWindow = None # type: RapidWindow
        self._activateOnMessage = False # type: bool

        # Is there another instance running?
        self._outSocket = QLocalSocket() # type: QLocalSocket
        self._outSocket.connectToServer(self._id)
        self._isRunning = self._outSocket.waitForConnected() # type: bool

        self._outStream = None # type: QTextStream
        self._inSocket  = None
        self._inStream  = None # type: QTextStream
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


def get_versions() -> List[str]:
    versions = [
        'Rapid Photo Downloader: {}'.format(__about__.__version__),
        'Platform: {}'.format(platform.platform()),
        'Python: {}'.format(platform.python_version()),
        'Qt: {}'.format(QtCore.QT_VERSION_STR),
        'PyQt: {}'.format(QtCore.PYQT_VERSION_STR),
        'ZeroMQ: {}'.format(zmq.zmq_version()),
        'Python ZeroMQ: {}'.format(zmq.pyzmq_version()),
        'gPhoto2: {}'.format(gphoto2_version()),
        'Python gPhoto2: {}'.format(python_gphoto2_version()),
        'ExifTool: {}'.format(EXIFTOOL_VERSION),
        'pymediainfo: {}'.format(pymedia_version_info()),
        'GExiv2: {}'.format(gexiv2_version()),
        'psutil: {}'.format('.'.join((str(v) for v in psutil.version_info)))]
    v = exiv2_version()
    if v:
        versions.append('Exiv2: {}'.format(v))
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
    def drawContents(self, painter: QPainter):
        painter.save()
        painter.setPen(QColor(Qt.black))
        painter.drawText(18, 64, __about__.__version__)
        painter.restore()


def parser_options(formatter_class=argparse.HelpFormatter):
    parser = argparse.ArgumentParser(prog=__about__.__title__,
                                     description=__about__.__summary__,
                                     formatter_class=formatter_class)

    parser.add_argument('--version', action='version', version=
        '%(prog)s {}'.format(__about__.__version__))
    parser.add_argument('--detailed-version', action='store_true',
        help="show version numbers of program and its libraries and exit")
    parser.add_argument("-v", "--verbose",  action="store_true", dest="verbose",
         help=_("display program information when run from the command line"))
    parser.add_argument("--debug", action="store_true", dest="debug",
         help=_("display debugging information when run from the command line"))
    parser.add_argument("-e",  "--extensions", action="store_true",
         dest="extensions",
         help=_("list photo and video file extensions the program recognizes "
                "and exit"))
    parser.add_argument("-a", "--auto-detect", choices=['on','off'],
        dest="auto_detect", help=_("turn on or off the automatic detection of devices from which "
       "to download"))
    parser.add_argument("-t", "--this-computer", choices=['on','off'],
        dest="this_computer_source",
        help=_("turn on or off downloading from this computer"))
    parser.add_argument("--this-computer-location", type=str,
        metavar=_("PATH"), dest="this_computer_location",
        help=_("the PATH on this computer from which to download"))
    parser.add_argument("--photo-destination", type=str,
        metavar=_("PATH"), dest="photo_location",
        help=_("the PATH where photos will be downloaded to"))
    parser.add_argument("--video-destination", type=str,
        metavar=_("PATH"), dest="video_location",
        help=_("the PATH where videos will be downloaded to"))
    parser.add_argument("-b", "--backup", choices=['on','off'],
        dest="backup", help=_("turn on or off the backing up of photos and videos while "
                              "downloading"))
    parser.add_argument("--backup-auto-detect", choices=['on','off'],
        dest="backup_auto_detect",
        help=_("turn on or off the automatic detection of backup devices"))
    parser.add_argument("--photo-backup-identifier", type=str,
        metavar=_("FOLDER"), dest="photo_backup_identifier",
        help=_("the FOLDER in which backups are stored on the automatically detected photo backup "
               "device, with the folder's name being used to identify whether or not the device "
               "is used for backups. For each device you wish to use for backing photos up to, "
               "create a folder on it with this name."))
    parser.add_argument("--video-backup-identifier", type=str,
        metavar=_("FOLDER"), dest="video_backup_identifier",
        help=_("the FOLDER in which backups are stored on the automatically detected video backup "
               "device, with the folder's name being used to identify whether or not the device "
               "is used for backups. For each device you wish to use for backing up videos to, "
               "create a folder on it with this name."))
    parser.add_argument("--photo-backup-location", type=str,
        metavar=_("PATH"), dest="photo_backup_location",
        help=_("the PATH where photos will be backed up when automatic "
        "detection of backup devices is turned off"))
    parser.add_argument("--video-backup-location", type=str,
        metavar=_("PATH"), dest="video_backup_location",
        help=_("the PATH where videos will be backed up when automatic "
        "detection of backup devices is turned off"))
    parser.add_argument("--ignore-other-photo-file-types", action="store_true", dest="ignore_other",
                        help=_('ignore photos with the following extensions: %s') %
                        make_internationalized_list([s.upper() for s in OTHER_PHOTO_EXTENSIONS]))
    parser.add_argument("--auto-download-startup", dest="auto_download_startup",
        choices=['on', 'off'],
        help=_("Turn on or off starting downloads as soon as the program itself starts"))
    parser.add_argument("--auto-download-device-insertion", dest="auto_download_insertion",
        choices=['on', 'off'],
        help=_("Turn on or off starting downloads as soon as a device is inserted"))
    parser.add_argument("--thumbnail-cache", dest="thumb_cache",
                        choices=['on','off'],
                        help=_("turn on or off use of the Rapid Photo Downloader Thumbnail Cache. "
                               "Turning it off does not delete existing cache contents."))
    parser.add_argument("--delete-thumbnail-cache", dest="delete_thumb_cache",
                        action="store_true",
                        help=_("delete all thumbnails in the Rapid Photo Downloader Thumbnail "
                               "Cache, and exit"))
    parser.add_argument("--forget-remembered-files", dest="forget_files",
                        action="store_true",
                        help=_("Forget which files have been previously downloaded, and exit"))
    parser.add_argument("--reset", action="store_true", dest="reset",
                 help=_("reset all program settings to their default values, delete all thumbnails "
                        "in the Thumbnail cache, forget which files have been previously "
                        "downloaded, and exit."))
    parser.add_argument("--log-gphoto2", action="store_true",
        help=_("include gphoto2 debugging information in log files"))
    return parser

def main():

    parser = parser_options()

    args = parser.parse_args()
    if args.detailed_version:
        print('\n'.join(get_versions()))
        sys.exit(0)

    if args.extensions:
        photos = list((ext.upper() for ext in PHOTO_EXTENSIONS))
        videos = list((ext.upper() for ext in VIDEO_EXTENSIONS))
        extensions = ((photos, _("Photos")),
                      (videos, _("Videos")))
        for exts, file_type in extensions:
            extensions = make_internationalized_list(exts)
            print('{}: {}'.format(file_type, extensions))
        sys.exit(0)

    global logging_level

    if args.debug:
        logging_level = logging.DEBUG
    elif args.verbose:
        logging_level = logging.INFO
    else:
        logging_level = logging.ERROR

    global logger
    logger = iplogging.setup_main_process_logging(logging_level=logging_level)

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
            logging.info("Downloading from this computer turned on from command line")
        else:
            logging.info("Downloading from this computer turned off from command line")
    else:
        this_computer_source=None

    if args.this_computer_location:
        this_computer_location = os.path.abspath(args.this_computer_location)
        logging.info("This computer path set from command line: %s", this_computer_location)
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
        gp.use_python_logging()

    appGuid = '8dbfb490-b20f-49d3-9b7d-2016012d2aa8'

    # See note above regarding avoiding crashes
    global app
    app = QtSingleApplication(appGuid, sys.argv)
    if app.isRunning():
        print('Rapid Photo Downloader is already running')
        sys.exit(0)

    app.setOrganizationName("Rapid Photo Downloader")
    app.setOrganizationDomain("damonlynch.net")
    app.setApplicationName("Rapid Photo Downloader")
    app.setWindowIcon(QtGui.QIcon(':/rapid-photo-downloader.svg'))


    # darkFusion(app)
    # app.setStyle('Fusion')

    # Resetting preferences must occur after QApplication is instantiated
    if args.reset:
        prefs = Preferences()
        prefs.reset()
        prefs.sync()
        d = DownloadedSQL()
        d.update_table(reset=True)
        cache = ThumbnailCacheSql()
        cache.purge_cache()
        print(_("All settings and caches have been reset"))
        sys.exit(0)

    if args.delete_thumb_cache or args.forget_files:
        if args.delete_thumb_cache:
            cache = ThumbnailCacheSql()
            cache.purge_cache()
            print(_("Thumbnail Cache has been reset"))
        if args.forget_files:
            d = DownloadedSQL()
            d.update_table(reset=True)
            print(_("Remembered files have been forgotten"))
        sys.exit(0)

    splash = SplashScreen(QPixmap(':/splashscreen.png'), Qt.WindowStaysOnTopHint)
    splash.show()
    app.processEvents()

    rw = RapidWindow(auto_detect=auto_detect,
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
                     splash=splash)

    app.setActivationWindow(rw)
    code = app.exec_()
    logging.debug("Exiting")
    sys.exit(code)

if __name__ == "__main__":
    main()
