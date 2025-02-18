# SPDX-FileCopyrightText: Copyright 2011-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Primary logic for Rapid Photo Downloader.

Qt related class method and variable names use CamelCase.
Everything else should follow PEP 8.
Project line length: 88 characters (i.e., word wrap at 88)

"Hamburger" Menu Icon by Daniel Bruce -- www.entypo.com
"""

# ruff: noqa: E402

import contextlib
import datetime
import locale

with contextlib.suppress(locale.Error):
    # Use the default locale as defined by the LANG variable
    locale.setlocale(locale.LC_ALL, "")
import faulthandler
import functools
import inspect
import logging
import os
import platform
import shutil
import sys
import time
import webbrowser
from collections import defaultdict
from typing import Any

import gi
from packaging.version import parse

gi.require_version("Notify", "0.7")
from gi.repository import Notify

try:
    gi.require_version("Unity", "7.0")
    from gi.repository import Unity

    launcher = "net.damonlynch.rapid_photo_downloader.desktop"
    Unity.LauncherEntry.get_for_desktop_id(launcher)
    have_unity = True
except (ImportError, ValueError, gi.repository.GLib.GError):
    have_unity = False

import zmq
from PyQt5 import QtCore
from PyQt5.QtCore import (
    QByteArray,
    QLocale,
    QModelIndex,
    QPoint,
    QRect,
    QSettings,
    QSize,
    QStorageInfo,
    Qt,
    QThread,
    QTimer,
    pyqtSignal,
    pyqtSlot,
)
from PyQt5.QtGui import (
    QCloseEvent,
    QDesktopServices,
    QFont,
    QFontMetrics,
    QIcon,
    QMoveEvent,
    QPixmap,
    QScreen,
    QShowEvent,
)
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QVBoxLayout,
    QWidget,
)
from showinfm import (
    LinuxDesktop,
    linux_desktop,
    valid_file_manager,
)

import raphodo.__about__ as __about__
import raphodo.constants as constants
import raphodo.downloadtracker as downloadtracker
import raphodo.excepthook as excepthook
import raphodo.iplogging as iplogging
import raphodo.metadata.exiftool as exiftool
import raphodo.storage.storageidevice as storageidevice
import raphodo.ui.didyouknow as didyouknow
from raphodo.argumentsparse import get_parser
from raphodo.cache import ThumbnailCacheSql
from raphodo.camera import (
    autodetect_cameras,
    dump_camera_details,
    gphoto2_python_logging,
)
from raphodo.constants import (
    CORE_APPLICATION_STATE_MASK,
    TIMELINE_APPLICATION_STATE_MASK,
    ApplicationState,
    BackupFailureType,
    BackupLocationType,
    BackupStatus,
    CameraErrorCode,
    CompletedDownloads,
    DeviceState,
    DeviceType,
    FileType,
    FileTypeFlag,
    PostCameraUnmountAction,
    RememberThisButtons,
    RememberThisMessage,
    RenameAndMoveStatus,
    RightSideButton,
    ScalingAction,
    ScalingDetected,
    Show,
    Sort,
    TemporalProximityState,
)
from raphodo.devices import (
    BackupDevice,
    BackupDeviceCollection,
    Device,
    DeviceCollection,
    DownloadingTo,
    FSMetadataErrors,
)
from raphodo.errorlog import ErrorReport, SpeechBubble
from raphodo.filesystemurl import FileSystemUrlHandler
from raphodo.folderpreviewmanager import FolderPreviewManager
from raphodo.generatenameconfig import (
    PHOTO_RENAME_SIMPLE,
    VIDEO_RENAME_SIMPLE,
)
from raphodo.internationalisation.install import install_gettext, localedir
from raphodo.internationalisation.utilities import (
    current_locale,
    make_internationalized_list,
    thousands,
)
from raphodo.interprocess import (
    BackupArguments,
    BackupFileData,
    BackupManager,
    CopyFilesArguments,
    CopyFilesManager,
    OffloadData,
    OffloadManager,
    ProcessLoggingManager,
    RenameAndMoveFileData,
    RenameMoveFileManager,
    ScanArguments,
    ScanManager,
    ThreadNames,
    ThumbnailDaemonData,
    ThumbnailDaemonManager,
    create_inproc_msg,
    stop_process_logging_manager,
)
from raphodo.metadata.fileextensions import PHOTO_EXTENSIONS, VIDEO_EXTENSIONS
from raphodo.metadata.metadatavideo import libmediainfo_missing, pymedia_version_info
from raphodo.prefs.preferencedialog import PreferencesDialog
from raphodo.prefs.preferences import Preferences
from raphodo.problemnotification import BackingUpProblems, CopyingProblems, Problems
from raphodo.programversions import EXIFTOOL_VERSION
from raphodo.proximity import (
    TemporalProximity,
    TemporalProximityControls,
    TemporalProximityGroups,
)
from raphodo.qtsingleapplication import QtSingleApplication
from raphodo.rpdfile import (
    FileSizeSum,
    FileTypeCounter,
    Photo,
    RPDFile,
    Video,
    file_types_by_number,
)
from raphodo.rpdsql import DownloadedSQL
from raphodo.storage.storage import (
    CameraHotplug,
    GVolumeMonitor,
    StorageSpace,
    UDisks2Monitor,
    ValidatedFolder,
    ValidMounts,
    WatchDownloadDirs,
    get_fdo_cache_thumb_base_directory,
    get_media_dir,
    gvfs_gphoto2_path,
    has_one_or_more_folders,
    have_gio,
    mountPaths,
    platform_photos_directory,
    platform_videos_directory,
    validate_download_folder,
    validate_source_folder,
)
from raphodo.thumbnaildisplay import (
    DownloadStats,
    MarkedSummary,
    ThumbnailDelegate,
    ThumbnailListModel,
    ThumbnailView,
)
from raphodo.tools.libraryversions import get_versions
from raphodo.tools.utilities import (
    addPushButtonLabelSpacer,
    data_file_path,
    format_size_for_user,
    getQtSystemTranslation,
    log_os_release,
    make_html_path_non_breaking,
    process_running,
    same_device,
)
from raphodo.ui import viewutils
from raphodo.ui.aboutdialog import AboutDialog
from raphodo.ui.backuppanel import BackupPanel
from raphodo.ui.chevroncombo import ChevronCombo
from raphodo.ui.computerview import ComputerWidget
from raphodo.ui.destinationpanel import DestinationPanel
from raphodo.ui.devicedisplay import (
    DeviceComponent,
    DeviceDelegate,
    DeviceModel,
    DeviceView,
)
from raphodo.ui.filebrowse import (
    FileSystemDelegate,
    FileSystemFilter,
    FileSystemModel,
    FileSystemView,
)
from raphodo.ui.jobcodepanel import JobCodePanel
from raphodo.ui.menubutton import MenuButton
from raphodo.ui.primarybutton import DownloadButton, TopPushButton
from raphodo.ui.rememberthisdialog import RememberThisDialog
from raphodo.ui.renamepanel import RenamePanel
from raphodo.ui.rotatedpushbutton import RotatedButton
from raphodo.ui.sourcepanel import LeftPanelContainer, SourcePanel
from raphodo.ui.splashscreen import SplashScreen
from raphodo.ui.toggleview import QToggleView
from raphodo.ui.viewutils import (
    MainWindowSplitter,
    any_screen_scaled,
    qt5_screen_scale_environment_variable,
    scaledIcon,
    standardMessageBox,
    validateWindowPosition,
    validateWindowSizeLimit,
)
from raphodo.wsl.wsl import (
    WindowsDriveMount,
    WslDrives,
    WslWindowsRemovableDriveMonitor,
)

install_gettext()

# Avoid segfaults at exit:
# http://pyqt.sourceforge.net/Docs/PyQt5/gotchas.html#crashes-on-exit
app: QtSingleApplication | None = None

faulthandler.enable()
sys.excepthook = excepthook.excepthook

is_devel_env = os.getenv("RPD_DEVEL_DEFAULTS") is not None

try:
    from icecream import install

    install()

except ImportError:  # Graceful fallback if IceCream isn't installed.
    ic = lambda *a: None if not a else (a[0] if len(a) == 1 else a)  # noqa
    builtins = __import__("builtins")
    setattr(builtins, "ic", ic)


class RapidWindow(QMainWindow):
    """
    Main application window, and primary controller of program logic

    Such attributes unfortunately make it very complex.

    For better or worse, Qt's state machine technology is not used.
    State indicating whether a download or scan is occurring is
    thus kept in the device collection, self.devices
    """

    udisks2Unmount = pyqtSignal(str)

    def __init__(
        self,
        splash: "SplashScreen",
        fractional_scaling: str,
        scaling_set: str,
        scaling_action: ScalingAction,
        scaling_detected: ScalingDetected,
        xsetting_running: bool,
        force_wayland: bool,
        display_height: int,
        platform_selected: str | None,
        photo_rename: bool | None = None,
        video_rename: bool | None = None,
        auto_detect: bool | None = None,
        this_computer_source: bool | None = None,
        this_computer_location: str | None = None,
        photo_download_folder: str | None = None,
        video_download_folder: str | None = None,
        backup: bool | None = None,
        backup_auto_detect: bool | None = None,
        photo_backup_identifier: str | None = None,
        video_backup_identifier: str | None = None,
        photo_backup_location: str | None = None,
        video_backup_location: str | None = None,
        ignore_other_photo_types: bool | None = None,
        thumb_cache: bool | None = None,
        auto_download_startup: bool | None = None,
        auto_download_insertion: bool | None = None,
        log_gphoto2: bool | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("rapidMainWindow")

        self.application_state = ApplicationState.startup

        self.splash = splash
        if splash.isVisible():
            self.screen: QScreen = splash.windowHandle().screen()
        else:
            self.screen = None

        self.fractional_scaling_message = fractional_scaling
        self.scaling_set_message = scaling_set

        # Process Qt events - in this case, possible closing of splash screen
        app.processEvents()

        # Three values to handle window position quirks under X11:
        self.window_show_requested_time: datetime.datetime | None = None
        self.window_move_triggered_count = 0
        self.windowPositionDelta = QPoint(0, 0)

        self.setFocusPolicy(Qt.StrongFocus)

        self.ignore_other_photo_types = ignore_other_photo_types
        self.prompting_for_user_action: dict[Device, QMessageBox] = {}
        self.prefs_dialog_active = False

        self.close_event_run = False

        self.file_manager = valid_file_manager()
        if platform.system() == "Linux":
            try:
                self.linux_desktop = linux_desktop()
            except Exception as e:
                logging.debug("Error detecting Linux Desktop environment: %s", str(e))
                self.linux_desktop = LinuxDesktop.unknown
                log_os_release()
        else:
            self.linux_desktop = None

        self.fileSystemUrlHandler = FileSystemUrlHandler()
        QDesktopServices.setUrlHandler(
            "file", self.fileSystemUrlHandler, "openFileBrowser"
        )

        for version in get_versions(
            file_manager=self.file_manager,
            scaling_action=scaling_action,
            scaling_detected=scaling_detected,
            xsetting_running=xsetting_running,
            force_wayland=force_wayland,
            platform_selected=platform_selected,
        ):
            logging.info("%s", version)

        if EXIFTOOL_VERSION is None:
            logging.error("ExifTool is either missing or has a problem")

        if pymedia_version_info() is None and libmediainfo_missing:
            logging.error(
                "pymediainfo is installed, but the library libmediainfo appears to "
                "be missing"
            )

        self.log_gphoto2 = log_gphoto2 is True

        self.setWindowTitle(_("Rapid Photo Downloader"))
        # app is a module level global
        self.readWindowSettings(app)
        self.prefs = Preferences()
        self.checkPrefsUpgrade()
        self.prefs.program_version = __about__.__version__

        if self.linux_desktop and self.linux_desktop == LinuxDesktop.wsl2:
            self.wslDrives = WslDrives(rapidApp=self)
            self.wslDrives.driveMounted.connect(self.wslWindowsDriveMounted)
            self.wslDrives.driveUnmounted.connect(self.wslWindowsDriveUnmounted)
            self.is_wsl2 = True
            # Track whether a list of Windows drives has been returned yet
            self.wsl_drives_probed = False
            self.wsl_backup_drives_refresh_needed = False
        else:
            self.is_wsl2 = False

        self.iOSInitErrorMessaging()

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
                self.prefs.photo_rename = self.prefs.rename_defaults["photo_rename"]

        if video_rename is not None:
            if video_rename:
                self.prefs.video_rename = VIDEO_RENAME_SIMPLE
            else:
                self.prefs.video_rename = self.prefs.rename_defaults["video_rename"]

        if auto_detect is not None:
            self.prefs.device_autodetection = auto_detect
        else:
            logging.info("Device autodetection: %s", self.prefs.device_autodetection)

        if self.prefs.device_autodetection:
            if not self.prefs.scan_specific_folders:
                logging.info("Devices do not need specific folders to be scanned")
            else:
                logging.info(
                    "For automatically detected devices, only the contents the "
                    "following folders will be scanned: %s",
                    ", ".join(self.prefs.folders_to_scan),
                )

        if this_computer_source is not None:
            self.prefs.this_computer_source = this_computer_source

        if this_computer_location is not None:
            self.prefs.this_computer_path = this_computer_location

        if self.prefs.this_computer_source:
            if self.prefs.this_computer_path:
                logging.info(
                    "This Computer is set to be used as a download source, using: %s",
                    self.prefs.this_computer_path,
                )
            else:
                logging.info(
                    "This Computer is set to be used as a download source, but the "
                    "location is not yet set"
                )
        else:
            logging.info("This Computer is not used as a download source")

        if photo_download_folder is not None:
            self.prefs.photo_download_folder = photo_download_folder
        logging.info("Photo download location: %s", self.prefs.photo_download_folder)
        if video_download_folder is not None:
            self.prefs.video_download_folder = video_download_folder
        logging.info("Video download location: %s", self.prefs.video_download_folder)

        self.prefs.check_show_system_folders()

        if backup is not None:
            self.prefs.backup_files = backup
        else:
            logging.info("Backing up files: %s", self.prefs.backup_files)

        if backup_auto_detect is not None:
            self.prefs.backup_device_autodetection = backup_auto_detect
        elif self.prefs.backup_files:
            logging.info(
                "Backup device auto detection: %s",
                self.prefs.backup_device_autodetection,
            )

        if photo_backup_identifier is not None:
            self.prefs.photo_backup_identifier = photo_backup_identifier
        elif self.prefs.backup_files and self.prefs.backup_device_autodetection:
            logging.info(
                "Photo backup identifier: %s", self.prefs.photo_backup_identifier
            )

        if video_backup_identifier is not None:
            self.prefs.video_backup_identifier = video_backup_identifier
        elif self.prefs.backup_files and self.prefs.backup_device_autodetection:
            logging.info(
                "video backup identifier: %s", self.prefs.video_backup_identifier
            )

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

        if self.prefs.list_not_empty("volume_whitelist"):
            logging.info(
                "Whitelisted devices: %s", " ; ".join(self.prefs.volume_whitelist)
            )

        if self.prefs.list_not_empty("volume_blacklist"):
            logging.info(
                "Blacklisted devices: %s", " ; ".join(self.prefs.volume_blacklist)
            )

        if self.prefs.list_not_empty("camera_blacklist"):
            logging.info(
                "Blacklisted cameras: %s", " ; ".join(self.prefs.camera_blacklist)
            )

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
                pv = parse(previous_version)
                rv = parse(__about__.__version__)
                if pv < rv:
                    logging.info(
                        "Version upgrade detected, from %s to %s",
                        previous_version,
                        __about__.__version__,
                    )
                    self.prefs.upgrade_prefs(pv)
                elif pv > rv:
                    logging.info(
                        "Version downgrade detected, from %s to %s",
                        previous_version,
                        __about__.__version__,
                    )
                if pv < parse("0.9.7b1"):
                    # Remove any duplicate subfolder generation or file renaming custom
                    # presets
                    self.prefs.filter_duplicate_generation_prefs()
                if pv < parse("0.9.29a1"):
                    # clear window and panel size, so they can be regenerated
                    logging.debug(
                        "Resetting window size, and left and central splitter sizes"
                    )
                    settings = QSettings()
                    settings.beginGroup("MainWindow")
                    if settings.contains("centerSplitterSizes"):
                        settings.remove("centerSplitterSizes")
                    if settings.contains("windowSize"):
                        settings.remove("windowSize")
                    if settings.contains("leftPanelSplitterSizes"):
                        settings.remove("leftPanelSplitterSizes")

    def startThreadControlSockets(self) -> None:
        """
        Create and bind inproc sockets to communicate with threads that
        handle inter process communication via zmq.

        See 'Signaling Between Threads (PAIR Sockets)' in 'ØMQ - The Guide'
        http://zguide.zeromq.org/page:all#toc46
        """

        context = zmq.Context.instance()
        inproc = "inproc://{}"

        self.logger_controller = context.socket(zmq.PAIR)
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
        self.thumbnail_deamon_controller.bind(
            inproc.format(ThreadNames.thumbnail_daemon)
        )

        self.offload_controller = context.socket(zmq.PAIR)
        self.offload_controller.bind(inproc.format(ThreadNames.offload))

        self.new_version_controller = context.socket(zmq.PAIR)
        self.new_version_controller.bind(inproc.format(ThreadNames.new_version))

    def sendStopToThread(self, socket: zmq.Socket) -> None:
        socket.send_multipart(create_inproc_msg(b"STOP"))

    def sendTerminateToThread(self, socket: zmq.Socket) -> None:
        socket.send_multipart(create_inproc_msg(b"TERMINATE"))

    def sendStopWorkerToThread(self, socket: zmq.Socket, worker_id: int) -> None:
        socket.send_multipart(create_inproc_msg(b"STOP_WORKER", worker_id=worker_id))

    def sendStartToThread(self, socket: zmq.Socket) -> None:
        socket.send_multipart(create_inproc_msg(b"START"))

    def sendStartWorkerToThread(
        self, socket: zmq.Socket, worker_id: int, data: Any
    ) -> None:
        socket.send_multipart(
            create_inproc_msg(b"START_WORKER", worker_id=worker_id, data=data)
        )

    def sendResumeToThread(
        self, socket: zmq.Socket, worker_id: int | None = None
    ) -> None:
        socket.send_multipart(create_inproc_msg(b"RESUME", worker_id=worker_id))

    def sendPauseToThread(self, socket: zmq.Socket) -> None:
        socket.send_multipart(create_inproc_msg(b"PAUSE"))

    def sendDataMessageToThread(
        self, socket: zmq.Socket, data: Any, worker_id: int | None = None
    ) -> None:
        socket.send_multipart(
            create_inproc_msg(b"SEND_TO_WORKER", worker_id=worker_id, data=data)
        )

    def sendToOffload(self, data: Any) -> None:
        self.offload_controller.send_multipart(
            create_inproc_msg(b"SEND_TO_WORKER", worker_id=None, data=data)
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
                logging.info(
                    "Thumbnail database size reduction: %s", format_size_for_user(size)
                )

            self.prefs.optimize_thumbnail_db = False
        else:
            # Recreate the cache on the file system
            ThumbnailCacheSql(create_table_if_not_exists=True)

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
            self.thumbnail_deamon_controller,
            worker_id=None,
            data=ThumbnailDaemonData(frontend_port=frontend_port),
        )

        centralWidget = QWidget()
        centralWidget.setObjectName("mainWindowCentralWidget")
        self.setCentralWidget(centralWidget)

        self.temporalProximity = TemporalProximity(rapidApp=self, prefs=self.prefs)

        # Respond to the user selecting / deslecting temporal proximity (timeline)
        # cells:
        self.temporalProximity.proximitySelectionHasChanged.connect(
            self.updateThumbnailModelAfterProximityChange
        )
        self.temporalProximity.temporalProximityView.proximitySelectionHasChanged.connect(
            self.updateThumbnailModelAfterProximityChange
        )

        # Setup notification system
        if self.is_wsl2:
            self.have_libnotify = False
        else:
            try:
                self.have_libnotify = Notify.init(_("Rapid Photo Downloader"))
            except Exception:
                logging.error("Notification intialization problem")
                self.have_libnotify = False

        logging.debug("Locale directory: %s", localedir)

        logging.debug("Probing for valid mounts")
        self.validMounts = ValidMounts(
            only_external_mounts=self.prefs.only_external_mounts
        )

        logging.debug(
            "Freedesktop.org thumbnails location: %s",
            get_fdo_cache_thumb_base_directory(),
        )

        self.unity_progress = False
        self.desktop_launchers = []

        if have_unity:
            logging.info("Unity LauncherEntry API installed")
            launchers = ("net.damonlynch.rapid_photo_downloader.desktop",)
            for launcher in launchers:
                desktop_launcher = Unity.LauncherEntry.get_for_desktop_id(launcher)
                if desktop_launcher is not None:
                    self.desktop_launchers.append(desktop_launcher)
                    self.unity_progress = True

            if not self.desktop_launchers:
                logging.warning(
                    "Desktop environment is Unity Launcher API compatible, but could "
                    "not find program's .desktop file"
                )
            else:
                logging.debug(
                    "Unity progress indicator found, using %s launcher(s)",
                    len(self.desktop_launchers),
                )

        self.createPathViews()
        self.temporalProximity.setupExplanations(
            width=self.deviceView.sizeHint().width()
        )

        self.createActions()
        logging.debug("Laying out main window")
        self.createMenus()
        self.createLayoutAndButtons(centralWidget)

        self.startMountMonitor()

        # Track the creation of temporary directories
        self.temp_dirs_by_scan_id = {}

        # Track the time a download commences - used in file renaming
        self.download_start_datetime: datetime.datetime | None = None
        # The timestamp for when a download started / resumed after a pause
        self.download_start_time: float | None = None

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
            fileSystemFilter=self.fileSystemFilter,
            devices=self.devices,
            rapidApp=self,
        )

        self.offloadmq.downloadFolders.connect(
            self.folder_preview_manager.folders_generated
        )

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

        self.download_tracker.set_no_backup_devices(0, 0)
        if self.prefs.backup_files and (not self.is_wsl2 or self.wsl_drives_probed):
            self.setupBackupDevices()

        settings = QSettings()
        settings.beginGroup("MainWindow")

        self.proximityButton.setChecked(
            settings.value("proximityButtonPressed", True, bool)
        )
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
            # For some unknown reason, under some sessions need to explicitly set this
            # to False, or else it shows and no button is pressed.
            self.rightPanels.setVisible(False)

        settings.endGroup()

        prefs_valid, msg = self.prefs.check_prefs_for_validity()

        self.setupErrorLogWindow(settings=settings)

        self.setDownloadCapabilities()
        if not self.is_wsl2:
            self.searchForCameras()
            self.setupNonCameraDevices()
        self.splash.setProgress(100)
        self.setupManualPath()
        self.updateSourceButton()
        self.displayMessageInStatusBar()

        self.showMainWindow()

        if self.mountMonitorTimer is not None:
            self.mountMonitorTimer.start()

        if not EXIFTOOL_VERSION and self.prefs.warn_broken_or_missing_libraries:
            message = _(
                "<b>ExifTool has a problem</b><br><br> "
                "Rapid Photo Downloader uses ExifTool to get metadata from videos and "
                "photos. The program will run without it, but installing it is "
                "<b>highly</b> recommended."
            )
            warning = RememberThisDialog(
                message=message,
                icon="rapid-photo-downloader.svg",
                remember=RememberThisMessage.do_not_warn_again_about_missing_libraries,
                parent=self,
                buttons=RememberThisButtons.ok,
                title=_("Problem with ExifTool"),
            )

            warning.exec_()
            if warning.remember:
                self.prefs.warn_broken_or_missing_libraries = False

        if libmediainfo_missing and self.prefs.warn_broken_or_missing_libraries:
            message = _(
                "<b>The library libmediainfo appears to be missing</b><br><br> "
                "Rapid Photo Downloader uses libmediainfo to get the date and time a "
                "video was shot. The program will run without it, but installing it "
                "is recommended."
            )

            warning = RememberThisDialog(
                message=message,
                icon="rapid-photo-downloader.svg",
                remember=RememberThisMessage.do_not_warn_again_about_missing_libraries,
                parent=self,
                buttons=RememberThisButtons.ok,
                title=_("Problem with libmediainfo"),
            )

            warning.exec_()
            if warning.remember:
                self.prefs.warn_broken_or_missing_libraries = False

        self.setCoreState(ApplicationState.normal)

        self.iOSIssueErrorMessage()
        if self.is_wsl2:
            self.wslDrives.mountDrives()

        if not prefs_valid:
            self.notifyPrefsAreInvalid(details=msg)
        else:
            self.tip = didyouknow.DidYouKnowDialog(self.prefs, self)
            if self.prefs.did_you_know_on_startup:
                self.tip.activate()

        # Setup survey prompt context
        self.prompt_for_survey_post_download = False
        force_survey = os.getenv("RPDSURVEY")

        if force_survey or not (
            self.prefs.never_prompt_for_survey or self.prefs.survey_taken
        ):
            if self.prefs.survey_countdown > 0:
                self.prefs.survey_countdown -= 1

            if self.prefs.survey_countdown == 0 or force_survey:
                delay = 500 if force_survey else 10000
                QTimer.singleShot(delay, self.promptForSurvey)

        logging.debug("Completed stage 9 initializing main window")

    def addState(self, state: ApplicationState) -> None:
        logging.debug("Adding state %s", state._name_)
        self.application_state |= state

    def delState(self, state: ApplicationState) -> None:
        logging.debug("Deleting state %s", state._name_)
        self.application_state &= ~state

    def setCoreState(self, state: ApplicationState) -> None:
        assert state & CORE_APPLICATION_STATE_MASK
        if not self.application_state & CORE_APPLICATION_STATE_MASK:
            logging.critical("Core application flag not set")
        else:
            logging.debug(
                "Core state: %s ➡ %s",
                self._appState("core"),
                self._appState("core", state),
            )
        # Clear existing state
        self.application_state &= ~CORE_APPLICATION_STATE_MASK
        # Add new state
        self.application_state |= state

    def _appState(self, category: str, state: ApplicationState | None = None) -> str:
        if state is None:
            state = self.application_state
        match category.lower():
            case "core":
                s = state & CORE_APPLICATION_STATE_MASK
            case "timeline":
                s = state & TIMELINE_APPLICATION_STATE_MASK
            case _:
                raise ValueError("Unrecognised application state")

        return s._name_

    @property
    def on_startup(self) -> bool:
        return bool(ApplicationState.startup & self.application_state)

    @property
    def on_exit(self) -> bool:
        return bool(ApplicationState.exiting & self.application_state)

    def logApplicationState(self) -> None:
        logging.debug("Core state: %s", self._appState("core"))

    def showMainWindow(self) -> None:
        if not self.isVisible():
            self.splash.finish(self)

            self.window_show_requested_time = datetime.datetime.now()
            self.show()
            if self.deferred_resize_and_move_until_after_show:
                self.resizeAndMoveMainWindow()

            self.errorLog.setVisible(self.errorLogAct.isChecked())

    def startMountMonitor(self) -> None:
        """
        Initialize monitors to watch for volume / camera additions to system
        :return:
        """

        self.mountMonitorTimer: QTimer | None = None
        self.valid_mount_count = 0

        if self.is_wsl2:
            self.wslDriveMonitor = WslWindowsRemovableDriveMonitor()
            self.wslDriveMonitorThread = QThread()
            self.wslDriveMonitorThread.started.connect(
                self.wslDriveMonitor.startMonitor
            )
            self.wslDriveMonitor.moveToThread(self.wslDriveMonitorThread)
            self.wslDriveMonitor.driveMounted.connect(self.wslWindowsDriveAdded)
            self.wslDriveMonitor.driveUnmounted.connect(self.wslWindowsDriveRemoved)
            logging.debug("Starting WSL Windows Drive Monitor")
            QTimer.singleShot(0, self.wslDriveMonitorThread.start)
            self.use_udsisks = self.gvfs_controls_mounts = False
        else:
            self.wslDriveMonitor = None

            logging.debug("Have GIO module: %s", have_gio)
            self.gvfs_controls_mounts = process_running("gvfs-gphoto2") and have_gio
            if have_gio:
                logging.debug(
                    "GVFS (GIO) controls mounts: %s", self.gvfs_controls_mounts
                )

            self.use_udsisks = not self.gvfs_controls_mounts

            if self.use_udsisks:
                # Monitor when the user adds or removes a camera
                self.cameraHotplug = CameraHotplug()
                self.cameraHotplugThread = QThread()
                self.cameraHotplugThread.started.connect(
                    self.cameraHotplug.startMonitor
                )
                self.cameraHotplug.moveToThread(self.cameraHotplugThread)
                self.cameraHotplug.cameraAdded.connect(self.cameraAdded)
                self.cameraHotplug.cameraRemoved.connect(self.cameraRemoved)
                # Start the monitor only on the thread it will be running on
                logging.debug("Starting camera hotplug monitor...")
                QTimer.singleShot(0, self.cameraHotplugThread.start)

                # Monitor when the user adds or removes a partition
                self.udisks2Monitor = UDisks2Monitor(self.validMounts, self.prefs)
                self.udisks2MonitorThread = QThread()
                self.udisks2MonitorThread.started.connect(
                    self.udisks2Monitor.startMonitor
                )
                self.udisks2Unmount.connect(self.udisks2Monitor.unmount_volume)
                self.udisks2Monitor.moveToThread(self.udisks2MonitorThread)
                self.udisks2Monitor.partitionMounted.connect(self.partitionMounted)
                self.udisks2Monitor.partitionUnmounted.connect(self.partitionUmounted)
                # Start the monitor only on the thread it will be running on
                logging.debug("Starting UDisks2 monitor...")
                QTimer.singleShot(0, self.udisks2MonitorThread.start)

                if not self.prefs.auto_mount:
                    self.startMountMonitorTimer()

            if self.gvfs_controls_mounts:
                # Gio.VolumeMonitor must be in the main thread, according to
                # Gnome documentation

                logging.debug("Starting GVolumeMonitor...")
                self.gvolumeMonitor = GVolumeMonitor(self.validMounts, self.prefs)
                logging.debug("...GVolumeMonitor started")
                self.gvolumeMonitor.cameraUnmounted.connect(self.cameraUnmounted)
                self.gvolumeMonitor.cameraMounted.connect(self.cameraMounted)
                self.gvolumeMonitor.partitionMounted.connect(self.partitionMounted)
                self.gvolumeMonitor.partitionUnmounted.connect(self.partitionUmounted)
                self.gvolumeMonitor.volumeAddedNoAutomount.connect(self.noGVFSAutoMount)
                self.gvolumeMonitor.cameraPossiblyRemoved.connect(self.cameraRemoved)
                self.gvolumeMonitor.cameraVolumeAdded.connect(self.cameraVolumeAdded)

    def startMountMonitorTimer(self) -> None:
        logging.debug("Starting monitor of valid mount count")
        self.mountMonitorTimer = QTimer(self)
        self.mountMonitorTimer.timeout.connect(self.manuallyMonitorNewMounts)
        self.mountMonitorTimer.setTimerType(Qt.CoarseTimer)
        self.mountMonitorTimer.setInterval(2000)

    def mountMonitorActive(self) -> bool:
        return self.mountMonitorTimer is not None and self.mountMonitorTimer.isActive()

    def iOSInitErrorMessaging(self) -> None:
        """
        Initialize display of error message to the user about missing iOS support
        applications
        """

        # Track device names
        self.ios_issue_message_queue: set[str] = set()

    def iOSIssueErrorMessage(self, display_name: str | None = None) -> None:
        """
        If needed, warn the user about missing help applications to download from iOS
        devices.

        Does not display error message while program is starting up. Instead will queue
        the device name to display it when the program has finished starting (call this
        function again with a device name to display queued items).

        :param display_name: device name
        """

        if self.on_startup and display_name:
            logging.debug(
                "Queueing display of missing iOS helper application error message for "
                "display after program startup"
            )
            display_name = f"'{display_name}'"
            self.ios_issue_message_queue.add(display_name)
        elif not self.on_startup and (
            self.ios_issue_message_queue or display_name is not None
        ):
            if display_name is not None:
                devices = f"'{display_name}'"
            else:
                devices = make_internationalized_list(
                    list(self.ios_issue_message_queue)
                )

            missing_applications = make_internationalized_list(
                storageidevice.ios_missing_programs()
            )

            message = _(
                "<b>Cannot download from Apple devices</b><br><br>"
                "To download from %(device)s, this program requires additional "
                "software be installed that interacts with Apple devices.<br><br>"
                "Missing applications: %(applications)s<br><br>"
                "<a "
                'href="https://damonlynch.net/rapid/documentation/#iosdevicesupport"'
                ">Learn more</a> about which software to install."
            ) % dict(device=devices, applications=missing_applications)

            msgbox = standardMessageBox(
                message=message,
                rich_text=True,
                standardButtons=QMessageBox.Ok,
                iconType=QMessageBox.Warning,
                parent=self,
            )
            msgbox.exec()
            self.ios_issue_message_queue = set()

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
        visible = settings.value("visible", False, type=bool)
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

            self.screen: QScreen = self.windowHandle().screen()

        assert self.screen is not None

        available: QRect = self.screen.availableGeometry()
        display: QSize = self.screen.size()

        logging.debug(
            "Available screen geometry: %sx%s on %sx%s display.",
            available.width(),
            available.height(),
            display.width(),
            display.height(),
        )

        settings = QSettings()
        settings.beginGroup("MainWindow")

        try:
            scaling = self.devicePixelRatioF()
        except AttributeError:
            scaling = self.devicePixelRatio()

        logging.info("%s", self.scaling_set_message)
        logging.info("Desktop scaling set to %s", scaling)
        logging.debug("%s", self.fractional_scaling_message)

        maximized = settings.value("maximized", False, type=bool)
        logging.debug("Window maximized when last run: %s", maximized)

        # Even if window is maximized, must restore saved window size and position for
        # when the user unmaximizes the window

        pos = settings.value("windowPosition")  # , QPoint(default_x, default_y)
        size = settings.value("windowSize")  # , QSize(default_width, default_height)
        settings.endGroup()
        if not (pos and size) or is_devel_env:
            logging.info("Window position or size not found in program settings")
            self.do_generate_default_window_size = True
        else:
            self.do_generate_default_window_size = False
            was_valid, validatedSize = validateWindowSizeLimit(available.size(), size)
            if not was_valid:
                logging.debug(
                    "Windows size %sx%s was invalid. Value was reset to %sx%s.",
                    size.width(),
                    size.height(),
                    validatedSize.width(),
                    validatedSize.height(),
                )
            logging.debug(
                "Window size: %sx%s", validatedSize.width(), validatedSize.height()
            )
            was_valid, validatedPos = validateWindowPosition(
                pos, available.size(), validatedSize
            )
            if not was_valid:
                logging.debug("Window position %s,%s was invalid", pos.x(), pos.y())

            self.resize(validatedSize)
            self.move(validatedPos)

        if maximized:
            logging.debug("Setting window to maximized state")
            self.setWindowState(Qt.WindowMaximized)

    def readWindowSettings(self, app: "QtSingleApplication"):
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
        # left panel splitter sizes are saved / read on use
        settings.setValue(
            "rightPanelSplitterSizes", self.destinationPanel.splitter.saveState()
        )
        settings.endGroup()

        settings.beginGroup("ErrorLog")
        settings.setValue("windowPosition", self.errorLog.pos())
        settings.setValue("windowSize", self.errorLog.size())
        settings.setValue("visible", self.errorLog.isVisible())
        settings.endGroup()

    @staticmethod
    def sourceButtonSetting() -> bool:
        settings = QSettings()
        settings.beginGroup("MainWindow")
        on = settings.value("sourceButtonPressed", True, bool)
        settings.endGroup()
        return on

    @staticmethod
    def proximityButtonSetting() -> bool:
        settings = QSettings()
        settings.beginGroup("MainWindow")
        on = settings.value("proximityButtonPressed", True, bool)
        settings.endGroup()
        return on

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
            if (
                datetime.datetime.now() - self.window_show_requested_time
            ).total_seconds() < 1.0:
                self.windowPositionDelta = event.oldPos() - self.pos()
                logging.debug(
                    "Window position quirk delta: %s", self.windowPositionDelta
                )
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

        delegate: ThumbnailDelegate = self.thumbnailView.itemDelegate()
        delegate.applyJobCode(job_code=job_code)

    def anyMainWindowDialogVisible(self) -> bool:
        """
        :return: True if any dialog window is currently being displayed from the main
        window
        """
        return (
            self.prefs_dialog_active
            or self.prompting_for_user_action
            or self.tip.isVisible()
        )

    @pyqtSlot()
    def promptForSurvey(self) -> None:
        if not self.anyMainWindowDialogVisible():
            if self.downloadIsRunning():
                self.prompt_for_survey_post_download = True
                return
            # Translators: please keep the <p> and </p> tags
            message = _(
                """
<p>Rapid Photo Downloader is made for you. You can help improve it by participating in a
web survey.</p>
<p>Because this program does not collect analytics, the survey makes a real 
difference to the program's future.</p>"""
            )
            lang = current_locale()
            if lang and not lang.startswith("en"):
                english = _("The survey is in English.")
                message = f"{message}<p>{english}</p>"

            logging.debug("Prompting about survey")
            messagebox = standardMessageBox(
                message=message,
                rich_text=True,
                standardButtons=QMessageBox.Ok,
                parent=self,
            )
            messagebox.removeButton(messagebox.button(QMessageBox.Ok))
            messagebox.setInformativeText(_("Do you want to take the survey?"))

            # Use custom buttons, thereby avoiding button icons
            later = messagebox.addButton(_("Ask me later"), QMessageBox.RejectRole)
            yes = messagebox.addButton(_("Yes"), QMessageBox.AcceptRole)
            alreadyDid = messagebox.addButton(
                # Translators: "I already took it" means "I already took the survey"
                _("I already took it"),
                QMessageBox.NoRole,
            )
            never = messagebox.addButton(
                # Translators: "Never ask me about any survey" refers to now and in
                # the future
                _("Never ask me about any survey"),
                QMessageBox.DestructiveRole,
            )
            messagebox.setDefaultButton(yes)
            messagebox.exec()
            response = messagebox.clickedButton()
            if response == yes:
                logging.debug("Opening web browser to take survey")
                webbrowser.open_new_tab("https://survey.rapidphotodownloader.com/")
                if not os.getenv("RPDSURVEY"):
                    self.prefs.survey_taken = datetime.datetime.now().year
            elif response == alreadyDid:
                logging.debug("Survey was already taken")
                if not os.getenv("RPDSURVEY"):
                    self.prefs.survey_taken = datetime.datetime.now().year
            elif response == later:
                logging.debug("Will ask about the survey later")
                self.prefs.survey_countdown = 10
            elif response == never:
                logging.info("Will never ask again about any survey")
                if not os.getenv("RPDSURVEY"):
                    self.prefs.never_prompt_for_survey = True

        else:
            # A dialog window was open.
            delay = 10000 if os.getenv("RPDSURVEY") else 3 * 60 * 1000
            logging.debug("Delaying survey prompt by %s seconds", delay / 1000)
            QTimer.singleShot(delay, self.promptForSurvey)

    def updateProgressBarState(self, thumbnail_generated: bool = None) -> None:
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
                launcher.set_property("progress_visible", False)

        if len(self.devices.thumbnailing):
            if (
                self.downloadProgressBar.maximum()
                != self.thumbnailModel.total_thumbs_to_generate
            ):
                logging.debug(
                    "Setting progress bar maximum to %s",
                    self.thumbnailModel.total_thumbs_to_generate,
                )
                self.downloadProgressBar.setMaximum(
                    self.thumbnailModel.total_thumbs_to_generate
                )
            if thumbnail_generated:
                self.downloadProgressBar.setValue(
                    self.thumbnailModel.thumbnails_generated
                )
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
        self.leftPanelContainer.setVisible(
            self.sourceButton.isChecked() or self.proximityButton.isChecked()
        )

    def setRightPanelsAndButtons(self, buttonPressed: RightSideButton) -> None:
        """
        Set visibility of right panel based on which right bar buttons
        is pressed, and ensure only one button is pressed at any one time.

        Cannot use exclusive QButtonGroup because with that, one button needs to be
        pressed. We allow no button to be pressed.
        """

        widget: RotatedButton = self.rightSideButtonMapper[buttonPressed]

        if widget.isChecked():
            self.rightPanels.setVisible(True)
            for button in RightSideButton:
                if button == buttonPressed:
                    self.rightPanels.setCurrentIndex(buttonPressed.value)
                else:
                    self.rightSideButtonMapper[button].setChecked(False)
        else:
            self.rightPanels.setVisible(False)

    def rightSidePanelWidgetHeights(self) -> None:
        heights = ", ".join(
            str(self.rightPanels.widget(i).height())
            for i in range(self.rightPanels.count())
        )
        logging.debug("Right side panel widget heights: %s", heights)

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
        if not self.on_startup:
            self.sourcePanel.placeWidgets()
        self.sourcePanel.setSourcesVisible(self.sourceButton.isChecked())
        self.setLeftPanelVisibility()
        self.temporalProximityControls.setAutoScrollState()

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
        checked = self.proximityButton.isChecked()
        self.sourcePanel.setTemporalProximityVisible(checked)
        self.temporalProximityControls.setVisible(checked)
        self.setLeftPanelVisibility()

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
        self.downloadAct = QAction(_("Download"), self)
        self.downloadAct.setShortcut("Ctrl+Return")
        self.downloadAct.triggered.connect(self.doDownloadAction)

        self.refreshAct = QAction(_("&Refresh..."), self)
        self.refreshAct.setShortcut("Ctrl+R")
        self.refreshAct.triggered.connect(self.doRefreshAction)

        self.preferencesAct = QAction(_("&Preferences"), self)
        self.preferencesAct.setShortcut("Ctrl+P")
        self.preferencesAct.triggered.connect(self.doPreferencesAction)

        self.quitAct = QAction(_("&Quit"), self)
        self.quitAct.setShortcut("Ctrl+Q")
        self.quitAct.triggered.connect(self.close)

        if self.is_wsl2:
            self.wslMountsAct = QAction(_("Windows &Drives"), self)
            self.wslMountsAct.setShortcut("Ctrl+D")
            self.wslMountsAct.triggered.connect(self.doShowWslMountsAction)

        self.errorLogAct = QAction(_("Error &Reports"), self)
        self.errorLogAct.setEnabled(True)
        self.errorLogAct.setCheckable(True)
        self.errorLogAct.triggered.connect(self.doErrorLogAction)

        self.clearDownloadsAct = QAction(_("Clear Completed Downloads"), self)
        self.clearDownloadsAct.triggered.connect(self.doClearDownloadsAction)

        self.helpAct = QAction(_("Get Help Online..."), self)
        self.helpAct.setShortcut("F1")
        self.helpAct.triggered.connect(self.doHelpAction)

        self.didYouKnowAct = QAction(_("&Tip of the Day..."), self)
        self.didYouKnowAct.triggered.connect(self.doDidYouKnowAction)

        self.reportProblemAct = QAction(_("Report a Problem..."), self)
        self.reportProblemAct.triggered.connect(self.doReportProblemAction)

        self.makeDonationAct = QAction(_("Make a Donation..."), self)
        self.makeDonationAct.triggered.connect(self.doMakeDonationAction)

        self.translateApplicationAct = QAction(_("Translate this Application..."), self)
        self.translateApplicationAct.triggered.connect(
            self.doTranslateApplicationAction
        )

        self.aboutAct = QAction(_("&About..."), self)
        self.aboutAct.triggered.connect(self.doAboutAction)

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

        self.createLeftBar()
        self.createRightBar()

        self.createLeftCenterRightPanels()
        self.createSourcePanel()
        self.createDeviceThisComputerViews()
        self.sourcePanel.addSourceViews()
        self.createDestinationPanel()
        self.createRenamePanels()
        self.createJobCodePanel()
        self.createBackupPanel()
        self.configureLeftCenterRightPanels(settings)
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
            addPushButtonLabelSpacer(_("Select Source")),
            parent=self,
            extra_top=self.standard_spacing,
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
            QSize(
                self.sourceButton.top_row_icon_size, self.sourceButton.top_row_icon_size
            )
        )

        topBar.addWidget(self.sourceButton)
        topBar.addStretch()
        topBar.addLayout(vlayout)
        hlayout.addWidget(self.downloadButton)
        hlayout.addWidget(self.menuButton)
        return topBar

    def createLeftBar(self) -> None:
        leftBar = QVBoxLayout()
        leftBar.setContentsMargins(0, 0, 0, 0)

        self.proximityButton = RotatedButton(_("Timeline"), RotatedButton.left_side)
        self.proximityButton.clicked.connect(self.proximityButtonClicked)
        leftBar.addWidget(self.proximityButton, 1)
        leftBar.addStretch(100)
        self.leftBar = leftBar

    def createRightButtons(self) -> None:
        self.destinationButton = RotatedButton(
            _("Destination"), RotatedButton.right_side
        )
        self.renameButton = RotatedButton(_("Rename"), RotatedButton.right_side)
        self.jobcodeButton = RotatedButton(_("Job Code"), RotatedButton.right_side)
        self.backupButton = RotatedButton(_("Back Up"), RotatedButton.right_side)

        self.destinationButton.clicked.connect(self.destinationButtonClicked)
        self.renameButton.clicked.connect(self.renameButtonClicked)
        self.jobcodeButton.clicked.connect(self.jobcodButtonClicked)
        self.backupButton.clicked.connect(self.backupButtonClicked)

        self.rightSideButtonMapper = {
            RightSideButton.destination: self.destinationButton,
            RightSideButton.rename: self.renameButton,
            RightSideButton.jobcode: self.jobcodeButton,
            RightSideButton.backup: self.backupButton,
        }

    def createRightBar(self) -> None:
        self.rightBar = QVBoxLayout()
        self.rightBar.setContentsMargins(0, 0, 0, 0)
        self.compressedRightBar = QGridLayout()
        self.compressedRightBar.setContentsMargins(0, 0, 0, 0)
        self.rightBar.addLayout(self.compressedRightBar)
        self.rightBar.addStretch(100)
        self.createRightButtons()
        self.placeRightButtons(0)

    @functools.cache
    def rightBarRequiredHeight(self) -> list[int]:
        spacing = self.rightBar.spacing()
        buttons = (
            self.destinationButton,
            self.renameButton,
            self.jobcodeButton,
            self.backupButton,
        )
        button_heights = [b.height() + spacing for b in buttons]
        heights = [sum(button_heights)]
        heights.append(sum(button_heights[:3]))
        heights.append(max(sum(button_heights[:2]), sum(button_heights[2:4])))
        heights.append(max(button_heights))
        return heights

    @pyqtSlot(int)
    def rightBarResized(self, height: int) -> None:
        heights = self.rightBarRequiredHeight()
        index = 0
        while height < heights[index] and index < len(heights) - 1:
            index += 1

        if index != self.right_bar_index:
            self.placeRightButtons(index)

    def placeRightButtons(self, index: int) -> None:
        """
        Place right side buttons into layout depending on the height
        of the layout they're going into
        """

        self.right_bar_index = index
        if index == 0:
            self.rightBar.insertWidget(0, self.backupButton)
            self.rightBar.insertWidget(0, self.jobcodeButton)
            self.rightBar.insertWidget(0, self.renameButton)
            self.rightBar.insertWidget(0, self.destinationButton)
        elif index == 1:
            self.compressedRightBar.addWidget(self.destinationButton, 0, 0)
            self.compressedRightBar.addWidget(self.renameButton, 1, 0)
            self.compressedRightBar.addWidget(self.jobcodeButton, 2, 0)
            self.compressedRightBar.addWidget(self.backupButton, 0, 1)
        elif index == 2:
            self.compressedRightBar.addWidget(self.destinationButton, 0, 0)
            self.compressedRightBar.addWidget(self.renameButton, 1, 0)
            self.compressedRightBar.addWidget(self.jobcodeButton, 0, 1)
            self.compressedRightBar.addWidget(self.backupButton, 1, 1)
        else:
            assert index == 3
            self.compressedRightBar.addWidget(self.destinationButton, 0, 0)
            self.compressedRightBar.addWidget(self.renameButton, 0, 1)
            self.compressedRightBar.addWidget(self.jobcodeButton, 0, 2)
            self.compressedRightBar.addWidget(self.backupButton, 0, 3)

    def createPathViews(self) -> None:
        self.deviceView = DeviceView(rapidApp=self)
        self.deviceView.setObjectName("deviceView")
        self.deviceModel = DeviceModel(self, "Devices")
        self.deviceView.setModel(self.deviceModel)
        self.deviceView.setItemDelegate(DeviceDelegate(rapidApp=self))
        self.deviceView.itemDelegate().widthChanged.connect(
            self.deviceView.widthChanged
        )

        # This computer is any local path
        self.thisComputerView = DeviceView(rapidApp=self, frame_enabled=False)
        self.thisComputerView.setObjectName("thisComputerView")
        self.thisComputerModel = DeviceModel(self, "This Computer")
        self.thisComputerView.setModel(self.thisComputerModel)
        self.thisComputerView.setItemDelegate(DeviceDelegate(self))
        self.thisComputerView.itemDelegate().widthChanged.connect(
            self.thisComputerView.widthChanged
        )

        # Map different device types onto their appropriate view and model
        self._mapModel = {
            DeviceType.path: self.thisComputerModel,
            DeviceType.camera: self.deviceModel,
            DeviceType.volume: self.deviceModel,
            DeviceType.camera_fuse: self.deviceModel,
        }
        self._mapView = {
            DeviceType.path: self.thisComputerView,
            DeviceType.camera: self.deviceView,
            DeviceType.volume: self.deviceView,
            DeviceType.camera_fuse: self.deviceView,
        }

        # Be cautious: validate paths. The settings file can always be edited by hand,
        # and the user can set it to whatever value they want using the command line
        # options.
        logging.debug("Checking path validity")
        this_computer_sf = validate_source_folder(self.prefs.this_computer_path)
        if this_computer_sf.valid:
            if this_computer_sf.absolute_path != self.prefs.this_computer_path:
                self.prefs.this_computer_path = this_computer_sf.absolute_path
        elif self.prefs.this_computer_source and self.prefs.this_computer_path != "":
            logging.warning(
                "Ignoring invalid 'This Computer' path: %s",
                self.prefs.this_computer_path,
            )
            self.prefs.this_computer_path = ""

        photo_df = validate_download_folder(self.prefs.photo_download_folder)
        if photo_df.valid:
            if photo_df.absolute_path != self.prefs.photo_download_folder:
                self.prefs.photo_download_folder = photo_df.absolute_path
        else:
            # TODO change behaviour
            if self.prefs.photo_download_folder:
                logging.error(
                    "Ignoring invalid Photo Destination path: %s",
                    self.prefs.photo_download_folder,
                )
            self.prefs.photo_download_folder = ""

        video_df = validate_download_folder(self.prefs.video_download_folder)
        if video_df.valid:
            if video_df.absolute_path != self.prefs.video_download_folder:
                self.prefs.video_download_folder = video_df.absolute_path
        else:
            # TODO change behaviour
            if self.prefs.video_download_folder:
                logging.error(
                    "Ignoring invalid Video Destination path: %s",
                    self.prefs.video_download_folder,
                )
            self.prefs.video_download_folder = ""

        self.watchedDownloadDirs = WatchDownloadDirs()
        self.watchedDownloadDirs.updateWatchPathsFromPrefs(self.prefs)
        self.watchedDownloadDirs.directoryChanged.connect(self.watchedFolderChange)

        self.fileSystemModel = FileSystemModel(parent=self)
        self.fileSystemFilter = FileSystemFilter(self)
        self.fileSystemFilter.setSourceModel(self.fileSystemModel)
        self.fileSystemDelegate = FileSystemDelegate()
        self.fileSystemFilter.filterInvalidated.connect(
            self.fileSystemFilterInvalidated
        )

        index = self.fileSystemFilter.mapFromSource(self.fileSystemModel.index("/"))

        # This Computer (source)
        self.thisComputerFSView = FileSystemView(
            model=self.fileSystemModel, rapidApp=self
        )
        self.thisComputerFSView.setObjectName("thisComputerFSView")
        self.thisComputerFSView.setModel(self.fileSystemFilter)
        self.thisComputerFSView.setItemDelegate(self.fileSystemDelegate)
        self.thisComputerFSView.hideColumns()
        self.thisComputerFSView.setRootIndex(index)
        if this_computer_sf.valid:
            self.thisComputerFSView.goToPath(self.prefs.this_computer_path)
        self.thisComputerFSView.activated.connect(self.thisComputerPathChosen)
        self.thisComputerFSView.clicked.connect(self.thisComputerPathChosen)
        self.thisComputerFSView.showSystemFolders.connect(
            self.fileSystemFilter.setShowSystemFolders
        )
        self.thisComputerFSView.filePathReset.connect(self.thisComputerFileBrowserReset)

        # Photos (destination)
        self.photoDestinationFSView = FileSystemView(
            model=self.fileSystemModel, rapidApp=self
        )
        self.photoDestinationFSView.setObjectName("photoDestinationFSView")
        self.photoDestinationFSView.setModel(self.fileSystemFilter)
        self.photoDestinationFSView.setItemDelegate(self.fileSystemDelegate)
        self.photoDestinationFSView.hideColumns()
        self.photoDestinationFSView.setRootIndex(index)
        if photo_df.valid:
            self.photoDestinationFSView.goToPath(self.prefs.photo_download_folder)
        self.photoDestinationFSView.activated.connect(self.photoDestinationPathChosen)
        self.photoDestinationFSView.clicked.connect(self.photoDestinationPathChosen)
        self.photoDestinationFSView.showSystemFolders.connect(
            self.fileSystemFilter.setShowSystemFolders
        )
        self.photoDestinationFSView.filePathReset.connect(self.photoDestinationReset)

        # Videos (destination)
        self.videoDestinationFSView = FileSystemView(
            model=self.fileSystemModel, rapidApp=self
        )
        self.videoDestinationFSView.setObjectName("videoDestinationFSView")
        self.videoDestinationFSView.setModel(self.fileSystemFilter)
        self.videoDestinationFSView.setItemDelegate(self.fileSystemDelegate)
        self.videoDestinationFSView.hideColumns()
        self.videoDestinationFSView.setRootIndex(index)
        if video_df.valid:
            self.videoDestinationFSView.goToPath(self.prefs.video_download_folder)
        self.videoDestinationFSView.activated.connect(self.videoDestinationPathChosen)
        self.videoDestinationFSView.clicked.connect(self.videoDestinationPathChosen)
        self.videoDestinationFSView.showSystemFolders.connect(
            self.fileSystemFilter.setShowSystemFolders
        )
        self.videoDestinationFSView.filePathReset.connect(self.videoDestinationReset)

    def createDeviceThisComputerViews(self) -> None:
        # Devices Header and View
        tip = _(
            "Turn on or off the use of devices attached to this computer as download "
            "sources"
        )
        self.deviceToggleView = QToggleView(
            label=_("Devices"),
            display_alternate=False,
            toggleToolTip=tip,
            on=self.prefs.device_autodetection,
            object_name="deviceToggleView",
        )
        self.deviceToggleView.addWidget(self.deviceView)
        self.deviceToggleView.valueChanged.connect(self.deviceToggleViewValueChange)
        self.deviceToggleView.setSizePolicy(
            QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding
        )

        # This Computer Header and View

        tip = _(
            "Turn on or off the use of a folder on this computer as a download source"
        )
        self.thisComputerToggleView = QToggleView(
            label=_("This Computer"),
            display_alternate=True,
            toggleToolTip=tip,
            on=bool(self.prefs.this_computer_source),
            object_name="thisComputerToggleView",
        )
        self.thisComputerToggleView.valueChanged.connect(
            self.thisComputerToggleValueChanged
        )

        self.thisComputer = ComputerWidget(
            objectName="thisComputerWidget",
            view=self.thisComputerView,
            fileSystemView=self.thisComputerFSView,
            select_text=_("Select a source folder"),
        )
        if self.prefs.this_computer_source:
            self.thisComputer.setViewVisible(self.prefs.this_computer_source)

        self.thisComputerToggleView.addWidget(self.thisComputer)

    def createDestinationPanel(self) -> None:
        """
        Create the photo and video destination panel
        """

        self.destinationPanel = DestinationPanel(parent=self)

    def createSourcePanel(self) -> None:
        """
        Create the source (Devices and This Computer) panel, as well as the Timeline
        controls
        """

        self.sourcePanel = SourcePanel(rapidApp=self)
        self.temporalProximityControls = TemporalProximityControls(rapidApp=self)
        # Adjust Timeline auto scroll sync button state:
        self.sourcePanel.verticalScrollBarVisible.connect(
            self.temporalProximityControls.sourceScrollBarVisible
        )
        # After a Timeline is regenerated after a value change, scrolling to the
        # same part of the Timeline can be important:
        self.sourcePanel.verticalScrollBarVisible.connect(
            self.temporalProximity.postValueChangeScroll
        )
        self.thumbnailView.verticalScrollBarVisible.connect(
            self.temporalProximityControls.thumbnailScrollBarVisible
        )
        self.leftPanelContainer = LeftPanelContainer(
            sourcePanel=self.sourcePanel,
            temporalProximityControls=self.temporalProximityControls,
        )
        self.leftPanelContainer.setObjectName("leftPanelContainer")

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
        vmargin = int(QFontMetrics(QFont()).height() / 2)

        layout.setContentsMargins(hmargin, vmargin, hmargin, vmargin)
        layout.setSpacing(self.standard_spacing)
        self.thumbnailControl.setLayout(layout)

        font: QFont = self.font()
        font.setPointSize(font.pointSize() - 2)

        self.showCombo = ChevronCombo()
        self.showCombo.addItem(_("All"), Show.all)
        self.showCombo.addItem(_("New"), Show.new_only)
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
        self.sortLabel = self.sortCombo.makeLabel(_("Sort:"))

        self.sortOrder = ChevronCombo()
        self.sortOrder.addItem(_("Ascending"), Qt.AscendingOrder)
        self.sortOrder.addItem(_("Descending"), Qt.DescendingOrder)
        self.sortOrder.currentIndexChanged.connect(self.sortOrderChanged)

        for widget in (
            self.showLabel,
            self.sortLabel,
            self.sortCombo,
            self.showCombo,
            self.sortOrder,
        ):
            widget.setFont(font)

        self.checkAllLabel = QLabel(_("Select All:"))

        # Remove the border when the widget is highlighted
        style = f"""
        QCheckBox {{
            border: none;
            outline: none;
            spacing: {self.standard_spacing // 2};
        }}"""
        self.selectAllPhotosCheckbox = QCheckBox(_("Photos") + " ")
        self.selectAllVideosCheckbox = QCheckBox(_("Videos"))
        self.selectAllPhotosCheckbox.setStyleSheet(style)
        self.selectAllVideosCheckbox.setStyleSheet(style)

        for widget in (
            self.checkAllLabel,
            self.selectAllPhotosCheckbox,
            self.selectAllVideosCheckbox,
        ):
            widget.setFont(font)

        self.selectAllPhotosCheckbox.stateChanged.connect(
            self.selectAllPhotosCheckboxChanged
        )
        self.selectAllVideosCheckbox.stateChanged.connect(
            self.selectAllVideosCheckboxChanged
        )

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

    def createLeftCenterRightPanels(self) -> None:
        self.centerSplitter = MainWindowSplitter()
        self.centerSplitter.heightChanged.connect(self.rightBarResized)
        self.rightPanels = QStackedWidget()
        self.rightPanels.setObjectName("rightPanels")

    def configureLeftCenterRightPanels(self, settings: QSettings) -> None:
        self.rightPanels.addWidget(self.destinationPanel)
        self.rightPanels.addWidget(self.renamePanel)
        self.rightPanels.addWidget(self.jobCodePanel)
        self.rightPanels.addWidget(self.backupPanel)

        self.centerSplitter.addWidget(self.leftPanelContainer)
        self.centerSplitter.addWidget(self.thumbnailView)
        self.centerSplitter.addWidget(self.rightPanels)
        self.centerSplitter.setStretchFactor(0, 0)
        self.centerSplitter.setStretchFactor(1, 1)
        self.centerSplitter.setStretchFactor(2, 0)
        for i in range(3):
            self.centerSplitter.setCollapsible(i, False)

        splitterSetting = settings.value("centerSplitterSizes")
        if splitterSetting is not None and not is_devel_env:
            self.do_generate_center_splitter_size = False
            self.centerSplitter.restoreState(splitterSetting)
        else:
            self.do_generate_center_splitter_size = True

        # left panel splitter sizes are saved / read on use

        splitterSetting = settings.value("rightPanelSplitterSizes")
        if splitterSetting is not None:
            self.destinationPanel.splitter.restoreState(splitterSetting)
        else:
            self.destinationPanel.splitter.setSizes([200, 200])

    def setDefaultWindowSize(self) -> None:
        """
        Set window size so that the left and right panels show without a horizontal
        scroll bar, and show up to 3 columns of thumbnails
        """

        available: QRect = self.screen.availableGeometry()
        available_width = available.width()

        frame_width = self.style().pixelMetric(QStyle.PM_DefaultFrameWidth)
        scroll_bar_width = (
            self.style().pixelMetric(QStyle.PM_ScrollBarExtent) + frame_width
        )
        spacing = self.layout().spacing()
        deviceComponent: DeviceComponent = (
            self.deviceView.itemDelegate().deviceDisplay.dc
        )
        # Minimum width will be updated as a scan occurs
        panel_width = max(
            deviceComponent.sample_width(), deviceComponent.minimum_width()
        )
        panel_width += scroll_bar_width + frame_width * 3
        left_panel = right_panel = panel_width

        wiggle_room = scroll_bar_width

        # Could do the calculation in this for loop without the loop, but this
        # code has the advantage of being a lot easier to understand / maintain
        for no_thumbnails in range(3, 0, -1):
            thumbnails_width = self.thumbnailView.width_required(
                no_thumbails=no_thumbnails
            )
            preferred_width = (
                self.leftBar.geometry().width()
                + spacing
                + left_panel
                + spacing
                + thumbnails_width
                + scroll_bar_width
                + spacing
                + right_panel
                + spacing
                + self.rightBar.geometry().width()
                + wiggle_room
            )
            # Allow for a possible X11 window frame... which could be anything really
            if preferred_width < available_width - 4:
                break

        self.centerSplitter.setSizes(
            [left_panel, thumbnails_width + wiggle_room, right_panel]
        )

        preferred_height = min(int(preferred_width / 1.5), available.height() - 4)
        logging.info(
            "Setting new window size of %sx%s with splitter sizes of %s, %s, and %s",
            preferred_width,
            preferred_height,
            left_panel,
            thumbnails_width,
            right_panel,
        )
        self.resize(QSize(preferred_width, preferred_height))

    def showEvent(self, event: QShowEvent) -> None:
        if self.on_startup and (
            self.do_generate_default_window_size
            or self.do_generate_center_splitter_size
        ):
            self.setDefaultWindowSize()
        super().showEvent(event)

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
                video_download_folder=self.prefs.video_download_folder,
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

    def updateDestinationViews(
        self,
        marked_summary: MarkedSummary,
        downloading_to: DownloadingTo | None = None,
    ) -> bool:
        """
        Updates the header bar and storage space view for the
        photo and video download destinations.

        :return True if destinations required for the download exist,
         and there is sufficient space on them, else False.
        """

        if self.unity_progress:
            available = self.thumbnailModel.getNoFilesMarkedForDownload()
            for launcher in self.desktop_launchers:
                if available:
                    launcher.set_property("count", available)
                    launcher.set_property("count_visible", True)
                else:
                    launcher.set_property("count_visible", False)

        # Assume that invalid destination folders have already been reset to ''
        if self.prefs.photo_download_folder and self.prefs.video_download_folder:
            same_dev = same_device(
                self.prefs.photo_download_folder, self.prefs.video_download_folder
            )
        else:
            same_dev = False

        merge = self.downloadIsRunning()

        return self.destinationPanel.updateDestinationPanelViews(
            same_dev=same_dev,
            merge=merge,
            marked_summary=marked_summary,
            downloading_to=downloading_to,
        )

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
            merge=merge,
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
                # Translators: %(variable)s represents Python code, not a plural of the
                # term variable. You must keep the %(variable)s untranslated, or the
                # program will crash.
                text: str = _("Download %(files)s") % dict(files=files)
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
            text = _("Resume Download") if self.download_paused else _("Pause")
        else:
            text = _("Download")

        self.downloadAct.setText(text)
        self.downloadButton.setText(text)

    def createMenus(self) -> None:
        self.menu = QMenu()
        self.menu.addAction(self.downloadAct)
        self.menu.addAction(self.preferencesAct)
        if self.is_wsl2:
            self.menu.addAction(self.wslMountsAct)
        self.menu.addSeparator()
        self.menu.addAction(self.errorLogAct)
        self.menu.addAction(self.clearDownloadsAct)
        self.menu.addSeparator()
        self.menu.addAction(self.helpAct)
        self.menu.addAction(self.didYouKnowAct)
        self.menu.addAction(self.reportProblemAct)
        self.menu.addAction(self.makeDonationAct)
        self.menu.addAction(self.translateApplicationAct)
        self.menu.addAction(self.aboutAct)
        self.menu.addAction(self.quitAct)

        self.menuButton = MenuButton(path="icons/menu.svg", menu=self.menu)

    def doSourceAction(self) -> None:
        self.sourceButton.animateClick()

    def doDownloadAction(self) -> None:
        self.downloadButton.animateClick()

    def doRefreshAction(self) -> None:
        pass

    def doShowWslMountsAction(self) -> None:
        self.wslDrives.showMountDrivesDialog()

    def doPreferencesAction(self) -> None:
        self.scan_all_again = self.scan_non_camera_devices_again = False
        self.search_for_devices_again = False

        self.start_monitoring_mount_count = False
        self.stop_monitoring_mount_count = False

        dialog = PreferencesDialog(prefs=self.prefs, parent=self)
        self.prefs_dialog_active = True
        dialog.exec()
        self.prefs_dialog_active = False
        self.prefs.sync()

        if self.scan_all_again or self.scan_non_camera_devices_again:
            self.rescanDevicesAndComputer(
                ignore_cameras=not self.scan_all_again, rescan_path=self.scan_all_again
            )

        if self.search_for_devices_again:
            # Update the list of valid mounts
            logging.debug(
                "Updating the list of valid mounts after preference change to "
                "only_external_mounts"
            )
            self.validMounts = ValidMounts(
                only_external_mounts=self.prefs.only_external_mounts
            )
            self.searchForDevicesAgain()

        # Just to be extra safe, reset these values to their 'off' state:
        self.scan_all_again = self.scan_non_camera_devices_again = False
        self.search_for_devices_again = False

        if self.start_monitoring_mount_count:
            if self.mountMonitorTimer is None:
                self.startMountMonitorTimer()
            else:
                self.mountMonitorTimer.start()
            self.valid_mount_count = 0

        if self.stop_monitoring_mount_count and self.mountMonitorActive():
            self.mountMonitorTimer.stop()

        self.start_monitoring_mount_count = False
        self.stop_monitoring_mount_count = False

    def doErrorLogAction(self) -> None:
        self.errorLog.setVisible(self.errorLogAct.isChecked())

    def doClearDownloadsAction(self):
        self.thumbnailModel.clearCompletedDownloads()

    def doHelpAction(self) -> None:
        webbrowser.open_new_tab("https://damonlynch.net/rapid/help.html")

    def doDidYouKnowAction(self) -> None:
        try:
            self.tip.activate()
        except AttributeError:
            self.tip = didyouknow.DidYouKnowDialog(self.prefs, self)
            self.tip.activate()

    def makeProblemReportDialog(self, header: str, title: str | None = None) -> None:
        """
        Create the dialog window to guide the user in reporting a bug
        :param header: text at the top of the dialog window
        :param title: optional title
        """

        body = excepthook.please_report_problem_body.format(
            website="https://bugs.rapidphotodownloader.com"
        )

        message = f"{header}<br><br>{body}"

        errorbox = standardMessageBox(
            message=message,
            rich_text=True,
            title=title,
            standardButtons=QMessageBox.Save | QMessageBox.Cancel,
            defaultButton=QMessageBox.Save,
        )
        if errorbox.exec_() == QMessageBox.Save:
            excepthook.save_bug_report_tar(
                config_file=self.prefs.settings_path(),
                full_log_file_path=iplogging.full_log_file_path(),
            )

    def doReportProblemAction(self) -> None:
        header = _("Thank you for reporting a problem in Rapid Photo Downloader")
        header = f"<b>{header}</b>"
        self.makeProblemReportDialog(header)

    def doMakeDonationAction(self) -> None:
        webbrowser.open_new_tab("https://damonlynch.net/rapid/donate.html")

    def doTranslateApplicationAction(self) -> None:
        webbrowser.open_new_tab("https://damonlynch.net/rapid/translate.html")

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
            self.prefs.this_computer_path = ""
            self.thisComputerFSView.clearSelection()

        if not self.on_startup:
            self.sourcePanel.setThisComputerState()

    @pyqtSlot()
    def thisComputerFileBrowserReset(self) -> None:
        if len(self.devices.this_computer) > 0:
            scan_id = list(self.devices.this_computer)[0]
            self.removeDevice(scan_id=scan_id)
        self.prefs.this_computer_path = ""

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
                self.generateTemporalProximityTableData(
                    "devices were removed as a download source"
                )
        else:
            self.devicesViewToggledOn()

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
            # Translators: please do not change HTML codes like <br>, <i>, </i>, or <b>,
            # </b> etc.
            message = _(
                "<b>Changing This Computer source path</b><br><br>Do you really want "
                "to change the source path to %(new_path)s?<br><br>You are currently "
                "downloading from %(source_path)s.<br><br>"
                "If you do change the path, the current download from This Computer "
                "will be cancelled."
            ) % dict(
                new_path=make_html_path_non_breaking(path),
                source_path=make_html_path_non_breaking(self.prefs.this_computer_path),
            )

            msgbox = standardMessageBox(
                message=message,
                rich_text=True,
                standardButtons=QMessageBox.Yes | QMessageBox.No,
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
                        "Removing path from device view %s",
                        self.prefs.this_computer_path,
                    )
                    self.removeDevice(scan_id=scan_id)
            self.prefs.this_computer_path = path
            self.thisComputer.setViewVisible(True)
            self.setupManualPath()

    def displayInvalidDestinationMsgBox(
        self, validation: ValidatedFolder, file_type: FileType
    ) -> None:
        """
        Display a message box to the user indicating an error
        :param validation:  destination directory validation results
        :param file_type: whether photo or video
        """

        file_type_hr = _("photo") if file_type == FileType.photo else _("video")
        # Translators: %(variable)s represents Python code, not a plural of the term
        # variable. You must keep the %(variable)s untranslated, or the program will
        # crash.
        title = _("Invalid %(filetype)s download destination") % {
            "filetype": file_type_hr
        }
        if validation.absolute_path:
            details = _(
                "The download directory is not writable. "
                "Ensure permissions are correctly set. "
                "If the destination is on the network, ensure the network share is "
                "correctly configured."
            )
        else:
            details = _("The download directory does not exist.")
        message = f"<b>{title}</b><br><br>{details}"
        msgBox = standardMessageBox(
            message=message,
            rich_text=True,
            standardButtons=QMessageBox.Ok,
            iconType=QMessageBox.Warning,
            parent=self,
        )
        msgBox.exec()

    @pyqtSlot(QModelIndex)
    def photoDestinationPathChosen(self, index: QModelIndex) -> None:
        """
        Handle user setting new photo download location

        Called after single click or folder being activated.

        :param index: cell clicked
        """

        path = self.fileSystemModel.filePath(index.model().mapToSource(index))
        self.photoDestinationSetPath(path=path)

    def photoDestinationSetPath(self, path: str) -> None:
        if not self.checkChosenDownloadDestination(path, FileType.photo):
            return

        validation = validate_download_folder(path, write_on_waccesss_failure=True)
        if validation.valid:
            if path != self.prefs.photo_download_folder:
                self.prefs.photo_download_folder = path
                self.watchedDownloadDirs.updateWatchPathsFromPrefs(self.prefs)
                self.folder_preview_manager.change_destination()
                self.destinationPanel.photoDestinationDisplay.setDestination(path=path)
                self.setDownloadCapabilities()
        else:
            logging.error("Invalid photo download destination chosen: %s", path)
            self.displayInvalidDestinationMsgBox(
                validation=validation, file_type=FileType.photo
            )
            self.resetDownloadDestination(file_type=FileType.photo)

    def photoDestinationReset(self) -> None:
        self.photoDestinationSetPath(path=platform_photos_directory())
        self.photoDestinationFSView.goToPath(self.prefs.photo_download_folder)

    def videoDestinationReset(self) -> None:
        self.videoDestinationSetPath(path=platform_videos_directory())
        self.videoDestinationFSView.goToPath(self.prefs.video_download_folder)

    @pyqtSlot()
    def fileSystemFilterInvalidated(self) -> None:
        self.photoDestinationFSView.selectionModel().clear()
        self.photoDestinationFSView.goToPath(self.prefs.photo_download_folder)
        self.videoDestinationFSView.selectionModel().clear()
        self.videoDestinationFSView.goToPath(self.prefs.video_download_folder)
        if self.prefs.this_computer_source:
            self.thisComputerFSView.selectionModel().clear()
            self.thisComputerFSView.goToPath(self.prefs.this_computer_path)

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
                message=message,
                rich_text=False,
                standardButtons=QMessageBox.Ok,
                iconType=QMessageBox.Warning,
            )
            msgbox.exec()

        else:
            problematic = path in self.fileSystemModel.preview_subfolders

        if not problematic and path in self.fileSystemModel.download_subfolders:
            message = _(
                "<b>Confirm Download Destination</b><br><br>Are you sure you want to "
                "set the %(file_type)s download destination to %(path)s?"
            ) % dict(file_type=file_type.name, path=make_html_path_non_breaking(path))
            msgbox = standardMessageBox(
                message=message,
                rich_text=True,
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

    def resetDownloadDestination(
        self, file_type: FileType, do_update: bool = True
    ) -> None:
        """
        Handle cases where user clicked on an invalid download directory,
        or the directory simply having disappeared, or the user resets the destination

        :param file_type: type of destination to work on
        :param do_update: if True, update watched folders, provisional
         download folders and update the UI to reflect new download
         capabilities
        """

        if file_type == FileType.photo:
            self.prefs.photo_download_folder = ""
            self.destinationPanel.photoDestinationWidget.setViewVisible(False)
        else:
            self.prefs.video_download_folder = ""
            self.destinationPanel.videoDestinationWidget.setViewVisible(False)

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
        self.videoDestinationSetPath(path=path)

    def videoDestinationSetPath(self, path: str) -> None:
        if not self.checkChosenDownloadDestination(path, FileType.video):
            return

        validation = validate_download_folder(path, write_on_waccesss_failure=True)
        if validation.valid:
            if path != self.prefs.video_download_folder:
                self.prefs.video_download_folder = path
                self.watchedDownloadDirs.updateWatchPathsFromPrefs(self.prefs)
                self.folder_preview_manager.change_destination()
                self.destinationPanel.videoDestinationDisplay.setDestination(path=path)
                self.setDownloadCapabilities()
        else:
            logging.error("Invalid video download destination chosen: %s", path)
            self.displayInvalidDestinationMsgBox(
                validation=validation, file_type=FileType.video
            )
            self.resetDownloadDestination(file_type=FileType.video)

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
                if (
                    self.prefs.warn_downloading_all
                    and self.thumbnailModel.anyCheckedFilesFiltered()
                ):
                    message = _(
                        """
<b>Downloading all files</b><br><br>
A download always includes all files that are marked for download,
including those that are not currently displayed because the Timeline
is being used or because only new files are being shown.<br><br>
Do you want to proceed with the download?"""
                    )

                    warning = RememberThisDialog(
                        message=message,
                        icon="rapid-photo-downloader.svg",
                        remember=RememberThisMessage.do_not_ask_again,
                        parent=self,
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
        self.devices.queued_to_download = set()

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

    def startDownload(self, scan_id: int = None) -> None:
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
        camera_unmounts_called: set[tuple[str, str]] = set()
        stop_thumbnailing_cmd_issued = False

        stop_thumbnailing = [
            scan_id
            for scan_id in self.download_files.camera_access_needed
            if scan_id in self.devices.thumbnailing
        ]
        for scan_id in stop_thumbnailing:
            device = self.devices[scan_id]
            if scan_id not in self.thumbnailModel.generating_thumbnails:
                logging.debug(
                    "Not terminating thumbnailing of %s because it's not in the "
                    "thumbnail manager",
                    device.display_name,
                )
            else:
                logging.debug(
                    "Terminating thumbnailing for %s because a download is starting",
                    device.display_name,
                )
                self.thumbnailModel.terminateThumbnailGeneration(scan_id)
                self.devices.cameras_to_stop_thumbnailing.add(scan_id)
                stop_thumbnailing_cmd_issued = True

        if self.gvfs_controls_mounts:
            mount_points = {}
            # If a device was being thumbnailed, then it wasn't mounted by GVFS
            # Therefore filter out the cameras we've already requested their
            # thumbnailing be stopped
            still_to_check = [
                scan_id
                for scan_id in self.download_files.camera_access_needed
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
                    "%s camera(s) need to be unmounted by GVFS before the download "
                    "begins",
                    len(camera_unmounts_called),
                )
                for model, port in camera_unmounts_called:
                    self.gvolumeMonitor.unmountCamera(
                        model,
                        port,
                        post_unmount_action=PostCameraUnmountAction.download,
                        mount_point=mount_points[(model, port)],
                    )

        if not camera_unmounts_called and not stop_thumbnailing_cmd_issued:
            self.startDownloadPhase2()

    def startDownloadPhase2(self) -> None:
        logging.debug("Start Download phase 2 has started")
        download_files = self.download_files

        invalid_dirs = self.invalidDownloadFolders(download_files.download_types)

        if invalid_dirs:
            if len(invalid_dirs) > 1:
                # Translators: %(variable)s represents Python code, not a plural of the
                # term variable. You must keep the %(variable)s untranslated, or the
                # program will crash.
                msg = _(
                    "These download folders are invalid:\n%(folder1)s\n%(folder2)s"
                ) % {"folder1": invalid_dirs[0], "folder2": invalid_dirs[1]}
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
                            "Photos and videos will not be backed up because there is "
                            "nowhere to back them up. Do you still want to start the "
                            "download?"
                        )
                    elif missing_destinations == BackupFailureType.photos:
                        logging.warning("No backup device exists for backing up photos")
                        # Translators: filetype will be replaced with 'photos' or
                        # 'videos'
                        # Translators: %(variable)s represents Python code, not a plural
                        # of the term variable. You must keep the %(variable)s
                        # untranslated, or the program will crash.
                        msg = _(
                            "No backup device exists for backing up %(filetype)s. Do "
                            "you still want to start the download?"
                        ) % {"filetype": _("photos")}

                    else:
                        logging.warning(
                            "No backup device contains a valid folder for backing up "
                            "videos"
                        )
                        # Translators: filetype will be replaced with 'photos' or
                        # 'videos'
                        # Translators: %(variable)s represents Python code, not a plural
                        # of the term variable. You must keep the %(variable)s
                        # untranslated, or the program will crash.
                        msg = _(
                            "No backup device exists for backing up %(filetype)s. Do "
                            "you still want to start the download?"
                        ) % {"filetype": _("videos")}
                else:
                    if missing_destinations == BackupFailureType.photos_and_videos:
                        logging.warning(
                            "The manually specified photo and videos backup paths do "
                            "not exist or are not writable"
                        )
                        # Translators: please do not change HTML codes like <br>, <i>,
                        # </i>, or <b>, </b> etc.
                        msg = _(
                            "<b>The photo and video backup destinations do not exist "
                            "or cannot be written to.</b><br><br>Do you still want "
                            "to start the download?"
                        )
                    elif missing_destinations == BackupFailureType.photos:
                        logging.warning(
                            "The manually specified photo backup path does not exist "
                            "or is not writable"
                        )
                        # Translators: filetype will be replaced by either 'photo' or
                        # 'video'
                        # Translators: %(variable)s represents Python code, not a plural
                        # of the term variable. You must keep the %(variable)s
                        # untranslated, or the program will crash.
                        # Translators: please do not change HTML codes like <br>, <i>,
                        # </i>, or <b>, </b> etc.
                        msg = _(
                            "<b>The %(filetype)s backup destination does not exist or "
                            "cannot be written to.</b><br><br>Do you still want to "
                            "start the download?"
                        ) % {"filetype": _("photo")}
                    else:
                        logging.warning(
                            "The manually specified video backup path does not exist "
                            "or is not writable"
                        )
                        # Translators: filetype will be replaced by either 'photo' or
                        # 'video'
                        # Translators: %(variable)s represents Python code, not a plural
                        # of the term variable. You must keep the %(variable)s
                        # untranslated, or the program will crash.
                        # Translators: please do not change HTML codes like <br>, <i>,
                        # </i>, or <b>, </b> etc.
                        msg = _(
                            "<b>The %(filetype)s backup destination does not exist or "
                            "cannot be written to.</b><br><br>Do you still want to "
                            "start the download?"
                        ) % {"filetype": _("video")}

                if self.prefs.warn_backup_problem:
                    warning = RememberThisDialog(
                        message=msg,
                        icon="rapid-photo-downloader.svg",
                        remember=RememberThisMessage.do_not_ask_again,
                        parent=self,
                        title=_("Backup problem"),
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
                    generate_thumbnails = self.thumbnailModel.markThumbnailsNeeded(
                        files
                    )
                else:
                    generate_thumbnails = False

                self.downloadFiles(
                    files=files,
                    scan_id=scan_id,
                    download_stats=download_files.download_stats[scan_id],
                    generate_thumbnails=generate_thumbnails,
                )

            self.setDownloadActionLabel()

    def downloadFiles(
        self,
        files: list[RPDFile],
        scan_id: int,
        download_stats: DownloadStats,
        generate_thumbnails: bool,
    ) -> None:
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
        download_size = (
            download_stats.photos_size_in_bytes + download_stats.videos_size_in_bytes
        )

        if self.prefs.backup_files:
            download_size += (
                len(self.backup_devices.photo_backup_devices)
                * download_stats.photos_size_in_bytes
            ) + (
                len(self.backup_devices.video_backup_devices)
                * download_stats.videos_size_in_bytes
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
            log_gphoto2=self.log_gphoto2,
        )

        self.sendStartWorkerToThread(
            self.copy_controller, worker_id=scan_id, data=copyfiles_args
        )

    @pyqtSlot(int, str, str)
    def tempDirsReceivedFromCopyFiles(
        self, scan_id: int, photo_temp_dir: str, video_temp_dir: str
    ) -> None:
        self.fileSystemFilter.setTempDirs([photo_temp_dir, video_temp_dir])
        self.temp_dirs_by_scan_id[scan_id] = list(
            filter(None, [photo_temp_dir, video_temp_dir])
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

    def cleanTempDirsForScanId(self, scan_id: int, remove_entry: bool = True):
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
                except Exception:
                    logging.error("Unknown error deleting temporary directory %s", d)
        if remove_entry:
            del self.temp_dirs_by_scan_id[scan_id]

    @pyqtSlot(bool, RPDFile, int, "PyQt_PyObject")
    def copyfilesDownloaded(
        self,
        download_succeeded: bool,
        rpd_file: RPDFile,
        download_count: int,
        mdata_exceptions: tuple[Exception] | None,
    ) -> None:
        scan_id = rpd_file.scan_id

        if scan_id not in self.devices:
            logging.debug(
                "Ignoring file %s because its device has been removed",
                rpd_file.full_file_name,
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
                worker_id=scan_id,
                path=rpd_file.temp_full_file_name,
                mdata_exceptions=mdata_exceptions,
            )

        self.sendDataMessageToThread(
            self.rename_controller,
            data=RenameAndMoveFileData(
                rpd_file=rpd_file,
                download_count=download_count,
                download_succeeded=download_succeeded,
            ),
        )

    @pyqtSlot(int, "PyQt_PyObject", "PyQt_PyObject")
    def copyfilesBytesDownloaded(
        self, scan_id: int, total_downloaded: int, chunk_downloaded: int
    ) -> None:
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
                total_downloaded,
                chunk_downloaded,
            )

        self.download_tracker.set_total_bytes_copied(scan_id, total_downloaded)
        if len(self.devices.have_downloaded_from) > 1:
            model = self.mapModel(scan_id)
            model.percent_complete[scan_id] = (
                self.download_tracker.get_percent_complete(scan_id)
            )
        self.time_check.increment(bytes_downloaded=chunk_downloaded)
        self.time_remaining.update(scan_id, bytes_downloaded=chunk_downloaded)
        self.updateFileDownloadDeviceProgress()

    @pyqtSlot(int, "PyQt_PyObject")
    def copyfilesProblems(self, scan_id: int, problems: CopyingProblems) -> None:
        for problem in self.copy_metadata_errors.problems(worker_id=scan_id):
            problems.append(problem)

        if problems:
            try:
                device = self.devices[scan_id]
                problems.name = device.display_name
                problems.uri = device.uri
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
            logging.debug(
                "All files finished copying for %s", self.devices[scan_id].display_name
            )

    @pyqtSlot(bool, RPDFile, int)
    def fileRenamedAndMoved(
        self, move_succeeded: bool, rpd_file: RPDFile, download_count: int
    ) -> None:
        """
        Called after a file has been renamed  -- that is, moved from the
        temp dir it was downloaded into, and renamed using the file
        renaming rules
        """

        scan_id = rpd_file.scan_id

        if scan_id not in self.devices:
            logging.debug(
                "Ignoring file %s because its device has been removed",
                rpd_file.download_full_file_name or rpd_file.full_file_name,
            )
            return

        if (
            rpd_file.mdatatime_caused_ctime_change
            and scan_id not in self.thumbnailModel.ctimes_differ
        ):
            self.thumbnailModel.addCtimeDisparity(rpd_file=rpd_file)

        if self.thumbnailModel.sendToDaemonThumbnailer(rpd_file=rpd_file):
            if rpd_file.status in constants.Downloaded:
                logging.debug(
                    "Assigning daemon thumbnailer to work on %s",
                    rpd_file.download_full_file_name,
                )
                self.sendDataMessageToThread(
                    self.thumbnail_deamon_controller,
                    data=ThumbnailDaemonData(
                        rpd_file=rpd_file,
                        write_fdo_thumbnail=self.prefs.save_fdo_thumbnails,
                        use_thumbnail_cache=self.prefs.use_thumbnail_cache,
                        force_exiftool=self.prefs.force_exiftool,
                    ),
                )
            else:
                logging.debug(
                    "%s was not downloaded, so adjusting download tracking",
                    rpd_file.full_file_name,
                )
                self.download_tracker.thumbnail_generated_post_download(scan_id)

        if (
            rpd_file.status in constants.Downloaded
            and self.fileSystemModel.add_subfolder_downloaded_into(
                path=rpd_file.download_path, download_folder=rpd_file.download_folder
            )
        ):
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
    def thumbnailReceivedFromDaemon(
        self, rpd_file: RPDFile, thumbnail: QPixmap
    ) -> None:
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
                        force_exiftool=self.prefs.force_exiftool,
                    ),
                )
                del self.backup_fdo_thumbnail_cache[uid]
        self.download_tracker.thumbnail_generated_post_download(scan_id=scan_id)
        completed, files_remaining = self.isDownloadCompleteForScan(scan_id)
        if completed:
            self.fileDownloadCompleteFromDevice(
                scan_id=scan_id, files_remaining=files_remaining
            )

    def thumbnailGenerationStopped(self, scan_id: int) -> None:
        """
        Slot for when a the thumbnail worker has been forcefully stopped,
        rather than merely finished in its work

        :param scan_id: scan_id of the device that was being thumbnailed
        """
        if scan_id not in self.devices:
            logging.debug(
                "Ignoring scan_id %s from terminated thumbailing, as its device does "
                "not exist anymore",
                scan_id,
            )
        else:
            device = self.devices[scan_id]
            if scan_id in self.devices.cameras_to_stop_thumbnailing:
                self.devices.cameras_to_stop_thumbnailing.remove(scan_id)
                logging.debug(
                    "Thumbnailing successfully terminated for %s", device.display_name
                )
                if not self.devices.download_start_blocked():
                    self.startDownloadPhase2()
            else:
                logging.debug(
                    "Ignoring the termination of thumbnailing from %s, as it's "
                    "not for a camera from which a download was waiting to be started",
                    device.display_name,
                )

    @pyqtSlot(int, "PyQt_PyObject")
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
                    backup_type == BackupLocationType.photos_and_videos
                    or download_types == FileTypeFlag.PHOTOS | FileTypeFlag.VIDEOS
                ) or backup_type == download_types:
                    device_id = self.backup_devices.device_id(path)
                    data = BackupFileData(message=message)
                    self.sendDataMessageToThread(
                        self.backup_controller, worker_id=device_id, data=data
                    )

    def backupFile(
        self, rpd_file: RPDFile, move_succeeded: bool, download_count: int
    ) -> None:
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
                (backup_type == BackupLocationType.photos_and_videos)
                or (
                    rpd_file.file_type == FileType.photo
                    and backup_type == BackupLocationType.photos
                )
                or (
                    rpd_file.file_type == FileType.video
                    and backup_type == BackupLocationType.videos
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
                save_fdo_thumbnail=self.prefs.save_fdo_thumbnails,
            )
            self.sendDataMessageToThread(
                self.backup_controller, worker_id=device_id, data=data
            )

    @pyqtSlot(int, bool, bool, RPDFile, str, "PyQt_PyObject")
    def fileBackedUp(
        self,
        device_id: int,
        backup_succeeded: bool,
        do_backup: bool,
        rpd_file: RPDFile,
        backup_full_file_name: str,
        mdata_exceptions: tuple[Exception] | None,
    ) -> None:
        if do_backup:
            if (
                self.prefs.generate_thumbnails
                and self.prefs.save_fdo_thumbnails
                and rpd_file.should_write_fdo()
                and backup_succeeded
            ):
                self.backupGenerateFdoThumbnail(
                    rpd_file=rpd_file, backup_full_file_name=backup_full_file_name
                )

            self.download_tracker.file_backed_up(rpd_file.scan_id, rpd_file.uid)

            if mdata_exceptions is not None and self.prefs.warn_fs_metadata_error:
                self.backup_metadata_errors.add_problem(
                    worker_id=device_id,
                    path=backup_full_file_name,
                    mdata_exceptions=mdata_exceptions,
                )

            if self.download_tracker.file_backed_up_to_all_locations(
                rpd_file.uid, rpd_file.file_type
            ):
                logging.debug(
                    "File %s will not be backed up to any more locations",
                    rpd_file.download_name,
                )
                self.fileDownloadFinished(backup_succeeded, rpd_file)

    @pyqtSlot("PyQt_PyObject", "PyQt_PyObject")
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
        self.generated_fdo_thumbnails: dict[str] = dict()
        self.backup_fdo_thumbnail_cache: defaultdict[list[str]] = defaultdict(list)

    def backupGenerateFdoThumbnail(
        self, rpd_file: RPDFile, backup_full_file_name: str
    ) -> None:
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
                "Assigning daemon thumbnailer to create FDO thumbnail for %s",
                backup_full_file_name,
            )
            self.sendDataMessageToThread(
                self.thumbnail_deamon_controller,
                data=ThumbnailDaemonData(
                    rpd_file=rpd_file,
                    write_fdo_thumbnail=True,
                    backup_full_file_names=[backup_full_file_name],
                    fdo_name=self.generated_fdo_thumbnails[uid],
                    force_exiftool=self.prefs.force_exiftool,
                ),
            )

    @pyqtSlot(int, list)
    def updateSequences(
        self, stored_sequence_no: int, downloads_today: list[str]
    ) -> None:
        """
        Called at conclusion of a download, with values coming from the
        renameandmovefile process
        """

        self.prefs.stored_sequence_no = stored_sequence_no
        self.prefs.downloads_today = downloads_today
        self.prefs.sync()
        logging.debug("Saved sequence values to preferences")
        if ApplicationState.exiting in self.application_state:
            self.close()
        else:
            self.renamePanel.updateSequences(
                downloads_today=downloads_today, stored_sequence_no=stored_sequence_no
            )

    @pyqtSlot()
    def fileRenamedAndMovedFinished(self) -> None:
        """Currently not called"""
        pass

    def isDownloadCompleteForScan(self, scan_id: int) -> tuple[bool, int]:
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
            logging.debug(
                "All files downloaded for %s", self.devices[scan_id].display_name
            )
            if self.download_tracker.no_post_download_thumb_generation_by_scan_id[
                scan_id
            ]:
                logging.debug(
                    "Thumbnails generated for %s thus far during download: %s of %s",
                    self.devices[scan_id].display_name,
                    self.download_tracker.post_download_thumb_generation[scan_id],
                    self.download_tracker.no_post_download_thumb_generation_by_scan_id[
                        scan_id
                    ],
                )
        completed = (
            completed
            and self.download_tracker.all_post_download_thumbs_generated_for_scan(
                scan_id
            )
        )

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
                launcher.set_property("progress", percent_complete)
                launcher.set_property("progress_visible", True)

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
            self.fileDownloadCompleteFromDevice(
                scan_id=scan_id, files_remaining=files_remaining
            )

    def fileDownloadCompleteFromDevice(
        self, scan_id: int, files_remaining: int
    ) -> None:
        device = self.devices[scan_id]

        device_finished = files_remaining == 0
        if device_finished:
            logging.debug(
                "All files from %s are downloaded; none remain", device.display_name
            )
            state = DeviceState.finished
        else:
            logging.debug(
                "Download finished from %s; %s remain be be potentially downloaded",
                device.display_name,
                files_remaining,
            )
            state = DeviceState.idle

        self.devices.set_device_state(scan_id=scan_id, state=state)
        self.mapModel(scan_id).setSpinnerState(scan_id, state)

        # Rebuild temporal proximity if it needs it
        if (
            scan_id in self.thumbnailModel.ctimes_differ
            and not self.thumbnailModel.filesRemainToDownload(scan_id=scan_id)
        ):
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
                    launcher.set_property("progress_visible", False)

            self.folder_preview_manager.remove_folders_for_queued_devices()

            # Update prefs with stored sequence number and downloads today
            # values
            data = RenameAndMoveFileData(message=RenameAndMoveStatus.download_completed)
            self.sendDataMessageToThread(self.rename_controller, data=data)

            # Ask backup processes to send problem reports
            self.sendBackupStartFinishMessageToWorkers(
                message=BackupStatus.backup_completed
            )

            if (
                (self.prefs.auto_exit and self.download_tracker.no_errors_or_warnings())
                or self.prefs.auto_exit_force
            ) and not self.thumbnailModel.filesRemainToDownload():
                logging.debug("Auto exit is initiated")
                self.close()

            self.download_tracker.purge_all()

            self.setDownloadActionLabel()
            self.setDownloadCapabilities()

            self.download_start_datetime = None
            self.download_start_time = None

            if self.prompt_for_survey_post_download:
                self.prompt_for_survey_post_download = False
                self.promptForSurvey()

    @pyqtSlot("PyQt_PyObject")
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

            time_remaining = self.time_remaining.time_remaining(
                self.prefs.detailed_time_remaining
            )
            if (
                time_remaining is None
                or time.time()
                < self.download_start_time + constants.ShowTimeAndSpeedDelay
            ):
                message = downloading
            else:
                # Translators - in the middle is a unicode em dash - please retain it
                # This string is displayed in the status bar when the download is
                # running.
                # Translators: %(variable)s represents Python code, not a plural of the
                # term variable. You must keep the %(variable)s untranslated, or the
                # program will crash.
                message = _(
                    "%(downloading_from)s — %(time_left)s left (%(speed)s)"
                ) % dict(
                    downloading_from=downloading,
                    time_left=time_remaining,
                    speed=download_speed,
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

        device: Device = self.devices[scan_id]

        if device.device_type == DeviceType.volume:
            if self.is_wsl2:
                self.wslDrives.unmountDrives(at_exit=False, mount_point=device.path)
            elif self.gvfs_controls_mounts:
                self.gvolumeMonitor.unmountVolume(path=device.path)
            else:
                self.udisks2Unmount.emit(device.path)

    def deleteSourceFiles(self, scan_id: int) -> None:
        """
        Delete files from download device at completion of download
        """
        # TODO delete from cameras and from other devices
        # TODO should assign this to a process or a thread, and delete then
        # to_delete = self.download_tracker.get_files_to_auto_delete(scan_id)
        pass

    def notifyDownloadedFromDevice(self, scan_id: int) -> None:
        """
        Display a system notification to the user using libnotify
        that the files have been downloaded from the device
        :param scan_id: identifies which device
        """

        device = self.devices[scan_id]

        notification_name = device.display_name

        no_photos_downloaded = self.download_tracker.get_no_files_downloaded(
            scan_id, FileType.photo
        )
        no_videos_downloaded = self.download_tracker.get_no_files_downloaded(
            scan_id, FileType.video
        )
        no_photos_failed = self.download_tracker.get_no_files_failed(
            scan_id, FileType.photo
        )
        no_videos_failed = self.download_tracker.get_no_files_failed(
            scan_id, FileType.video
        )
        no_files_downloaded = no_photos_downloaded + no_videos_downloaded
        no_files_failed = no_photos_failed + no_videos_failed
        no_warnings = self.download_tracker.get_no_warnings(scan_id)

        file_types = file_types_by_number(no_photos_downloaded, no_videos_downloaded)
        file_types_failed = file_types_by_number(no_photos_failed, no_videos_failed)
        # Translators: e.g. 23 photos downloaded
        # Translators: %(variable)s represents Python code, not a plural of the term
        # variable. You must keep the %(variable)s untranslated, or the program will
        # crash.
        message = _("%(noFiles)s %(filetypes)s downloaded") % {
            "noFiles": thousands(no_files_downloaded),
            "filetypes": file_types,
        }

        if no_files_failed:
            # Translators: e.g. 2 videos failed to download
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            message += "\n" + _("%(noFiles)s %(filetypes)s failed to download") % {
                "noFiles": thousands(no_files_failed),
                "filetypes": file_types_failed,
            }

        if no_warnings:
            message = f"{message}\n{no_warnings} " + _("warnings")

        message_shown = False
        if self.have_libnotify:
            n = Notify.Notification.new(
                notification_name, message, "rapid-photo-downloader"
            )
            try:
                message_shown = n.show()
            except Exception:
                logging.error(
                    "Unable to display downloaded from device message using "
                    "notification system"
                )
            if not message_shown:
                logging.error(
                    "Unable to display downloaded from device message using "
                    "notification system"
                )
                logging.info(f"{notification_name}: {message}")

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
            n_message += "\n" + _("%(number)s %(numberdownloaded)s") % dict(
                number=thousands(photo_downloads),
                # Translators: %(variable)s represents Python code, not a plural of the
                # term variable. You must keep the %(variable)s untranslated, or the
                # program will crash.
                numberdownloaded=_("%(filetype)s downloaded") % dict(filetype=filetype),
            )

        # photo failures
        photo_failures = self.download_tracker.total_photo_failures
        if photo_failures and show_notification:
            filetype = file_types_by_number(photo_failures, 0)
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            n_message += "\n" + _("%(number)s %(numberdownloaded)s") % dict(
                number=thousands(photo_failures),
                # Translators: %(variable)s represents Python code, not a plural of the
                # term variable. You must keep the %(variable)s untranslated, or the
                # program will crash.
                numberdownloaded=_("%(filetype)s failed to download")
                % dict(filetype=filetype),
            )

        # video downloads
        video_downloads = self.download_tracker.total_videos_downloaded
        if video_downloads and show_notification:
            filetype = file_types_by_number(0, video_downloads)
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            n_message += "\n" + _("%(number)s %(numberdownloaded)s") % dict(
                number=thousands(video_downloads),
                # Translators: %(variable)s represents Python code, not a plural of the
                # term variable. You must keep the %(variable)s untranslated, or the
                # program will crash.
                numberdownloaded=_("%(filetype)s downloaded") % dict(filetype=filetype),
            )

        # video failures
        video_failures = self.download_tracker.total_video_failures
        if video_failures and show_notification:
            filetype = file_types_by_number(0, video_failures)
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            n_message += "\n" + _("%(number)s %(numberdownloaded)s") % dict(
                number=thousands(video_failures),
                # Translators: %(variable)s represents Python code, not a plural of the
                # term variable. You must keep the %(variable)s untranslated, or the
                # program will crash.
                numberdownloaded=_("%(filetype)s failed to download")
                % dict(filetype=filetype),
            )

        # warnings
        warnings = self.download_tracker.total_warnings
        if warnings and show_notification:
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            n_message += "\n" + _("%(number)s %(numberdownloaded)s") % dict(
                number=thousands(warnings), numberdownloaded=_("warnings")
            )

        if show_notification:
            message_shown = False
            if self.have_libnotify:
                n = Notify.Notification.new(
                    _("Rapid Photo Downloader"), n_message, "rapid-photo-downloader"
                )
                try:
                    message_shown = n.show()
                except Exception:
                    logging.error(
                        "Unable to display download complete message using "
                        "notification system"
                    )
            if not message_shown:
                logging.error(
                    "Unable to display download complete message using notification "
                    "system"
                )

        failures = photo_failures + video_failures

        if failures == 1:
            f = _("1 failure")
        elif failures > 1:
            f = _("%d failures") % failures
        else:
            f = ""

        if warnings == 1:
            w = _("1 warning")
        elif warnings > 1:
            w = _("%d warnings") % warnings
        else:
            w = ""

        if f and w:
            fw = make_internationalized_list([f, w])
        elif f:
            fw = f
        elif w:
            fw = w
        else:
            fw = ""

        devices = self.devices.reset_and_return_have_downloaded_from()
        if photo_downloads + video_downloads:
            ftc = FileTypeCounter(
                {FileType.photo: photo_downloads, FileType.video: video_downloads}
            )
            no_files_and_types = ftc.file_types_present_details().lower()

            if not fw:
                # Translators: %(variable)s represents Python code, not a plural of the
                # term variable. You must keep the %(variable)s untranslated, or the
                # program will crash.
                downloaded = _(
                    "Downloaded %(no_files_and_types)s from %(devices)s"
                ) % dict(no_files_and_types=no_files_and_types, devices=devices)
            else:
                # Translators: %(variable)s represents Python code, not a plural of the
                # term variable. You must keep the %(variable)s untranslated, or the
                # program will crash.
                downloaded = _(
                    "Downloaded %(no_files_and_types)s from %(devices)s — %(failures)s"
                ) % dict(
                    no_files_and_types=no_files_and_types, devices=devices, failures=fw
                )
        else:
            if fw:
                # Translators: %(variable)s represents Python code, not a plural of the
                # term variable. You must keep the %(variable)s untranslated, or the
                # program will crash.
                downloaded = _("No files downloaded — %(failures)s") % dict(failures=fw)
            else:
                downloaded = _("No files downloaded")
        logging.info("%s", downloaded)
        self.statusBar().showMessage(downloaded)

    def invalidDownloadFolders(self, downloading: FileTypeFlag) -> list[str]:
        """
        Checks validity of download folders based on the file types the
        user is attempting to download.

        :return list of the invalid directories, if any, or empty list.
        """

        invalid_dirs = []

        for destination, file_type_flag in (
            (self.prefs.photo_download_folder, FileTypeFlag.PHOTOS),
            (self.prefs.video_download_folder, FileTypeFlag.VIDEOS),
        ):
            if (
                downloading in file_type_flag
                and not validate_download_folder(
                    destination, write_on_waccesss_failure=True
                ).valid
            ):
                invalid_dirs.append(destination)
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
        # Translators: please do not change HTML codes like <br>, <i>, </i>, or <b>,
        # </b> etc.
        message = f"<b>{title}</b><br><br>{details}"
        msgBox = standardMessageBox(
            message=message,
            rich_text=True,
            standardButtons=QMessageBox.Ok,
            iconType=QMessageBox.Warning,
        )
        msgBox.exec()

    def deviceState(self, scan_id: int) -> DeviceState:
        """
        What the device is being used for at the present moment.

        :param scan_id: device to check
        :return: DeviceState
        """

        return self.devices.device_state[scan_id]

    @pyqtSlot(
        "PyQt_PyObject", "PyQt_PyObject", FileTypeCounter, "PyQt_PyObject", bool, bool
    )
    def scanFilesReceived(
        self,
        rpd_files: list[RPDFile],
        sample_files: list[RPDFile],
        file_type_counter: FileTypeCounter,
        file_size_sum: FileSizeSum,
        entire_video_required: bool | None,
        entire_photo_required: bool | None,
    ) -> None:
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
                "Updating example file name using sample photo from %s",
                device.display_name,
            )
            self.devices.sample_photo: Photo = sample_photo
            self.renamePanel.setSamplePhoto(self.devices.sample_photo)
            # sample required for editing download subfolder generation
            self.destinationPanel.photoDestinationDisplay.sample_rpd_file = (
                self.devices.sample_photo
            )

        if sample_video is not None:
            logging.info(
                "Updating example file name using sample video from %s",
                device.display_name,
            )
            self.devices.sample_video: Video = sample_video
            self.renamePanel.setSampleVideo(self.devices.sample_video)
            # sample required for editing download subfolder generation
            self.destinationPanel.videoDestinationDisplay.sample_rpd_file = (
                self.devices.sample_video
            )

        if device.device_type == DeviceType.camera:  # irrelevant when using FUSE
            if entire_video_required is not None:
                device.entire_video_required = entire_video_required
            if entire_photo_required is not None:
                device.entire_photo_required = entire_photo_required

        device.file_type_counter = file_type_counter
        device.file_size_sum = file_size_sum

        self.mapModel(scan_id).updateDeviceScan(scan_id)

        self.thumbnailModel.addFiles(
            scan_id=scan_id,
            rpd_files=rpd_files,
            generate_thumbnail=not self.autoStart(scan_id),
        )
        self.folder_preview_manager.add_rpd_files(rpd_files=rpd_files)

    @pyqtSlot(int, CameraErrorCode, str)
    def scanErrorReceived(
        self, scan_id: int, error_code: CameraErrorCode, error_message: str
    ) -> None:
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
            title = _("Rapid Photo Downloader")
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            # Translators: please do not change HTML codes like <br>, <i>, </i>, or
            # <b>, </b> etc.
            message = _(
                "<b>All files on the %(camera)s are inaccessible</b>.<br><br>It "
                "may be locked or not configured for file transfers using USB. "
                "You can unlock it and try again.<br><br>On some models you also "
                "need to change the setting to allow the use of USB for "
                "<i>File Transfer</i>.<br><br>"
                "Learn more about <a "
                'href="https://damonlynch.net/rapid/documentation/#downloadingfromcameras"'
                ">downloading from cameras</a> and <a "
                'href="https://damonlynch.net/rapid/documentation/#downloadingfromphones"'
                ">enabling downloading from phones</a>. <br><br>"
                "Alternatively, you can ignore the %(camera)s."
            ) % {"camera": camera_model}
        elif error_code == CameraErrorCode.inaccessible:
            title = _("Rapid Photo Downloader")
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            # Translators: please do not change HTML codes like <br>, <i>, </i>, or <b>,
            # </b> etc.
            message = _(
                "<b>The %(camera)s appears to be in use by another "
                "application.</b><br><br>Rapid Photo Downloader cannnot access a phone "
                "or camera that is being used by another program like a file "
                "manager.<br><br>"
                "If the device is mounted in your file manager, you must first "
                "&quot;eject&quot; it from the other program while keeping the "
                "%(camera)s plugged in.<br><br>"
                "If that does not work, unplug the %(camera)s from the computer and "
                "plug it in again.<br><br>"
                "Learn more about <a "
                'href="https://damonlynch.net/rapid/documentation/#downloadingfromcameras"'
                ">downloading from cameras</a> and <a "
                'href="https://damonlynch.net/rapid/documentation/#downloadingfromphones"'
                ">enabling downloading from phones</a>. <br><br>"
                "Alternatively, you can ignore the %(camera)s."
            ) % {"camera": camera_model}
        elif error_code == CameraErrorCode.pair:
            title = _("Rapid Photo Downloader")
            message = (
                "<b>"
                + _("Enable access to the iOS Device")
                + f"</b><br><br>{error_message}"
            )
        else:
            title = _("Rapid Photo Downloader")
            message = "Unknown error"

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

    @pyqtSlot(int, "PyQt_PyObject", "PyQt_PyObject", str, str, bool)
    def scanDeviceDetailsReceived(
        self,
        scan_id: int,
        storage_space: list[StorageSpace],
        storage_descriptions: list[str],
        optimal_display_name: str,
        mount_point: str,
        is_apple_mobile: bool,
    ) -> None:
        """
        Update GUI display and rows DB with definitive camera display name

        :param scan_id: scan id of the device
        :param storage_space: storage information on the device e.g.
         memory card(s) capacity and use
        :param  storage_desctriptions: names of storage on a camera
        :param optimal_display_name: canonical name of the device, as
         reported by libgphoto2
        :param mount_point: FUSE mount point, e.g. for iOS devices
        :param is_apple_mobile: True if device is iOS device
        """

        if scan_id in self.devices:
            device = self.devices[scan_id]
            logging.debug(
                "%s with scan id %s is now known as %s",
                device.display_name,
                scan_id,
                optimal_display_name,
            )

            if len(storage_space) > 1:
                logging.debug(
                    "%s has %s storage devices",
                    optimal_display_name,
                    len(storage_space),
                )

            if not storage_descriptions and not is_apple_mobile:
                logging.warning(
                    "No storage descriptors available for %s", optimal_display_name
                )
            else:
                if len(storage_descriptions) == 1:
                    msg = "description"
                else:
                    msg = "descriptions"
                logging.debug("Storage %s: %s", msg, ", ".join(storage_descriptions))

            device.update_camera_attributes(
                display_name=optimal_display_name,
                storage_space=storage_space,
                storage_descriptions=storage_descriptions,
                mount_point=mount_point,
                is_apple_mobile=is_apple_mobile,
            )
            self.updateSourceButton()
            self.deviceModel.updateDeviceNameAndStorage(scan_id, device)
            self.thumbnailModel.addOrUpdateDevice(scan_id=scan_id)
            self.updateDeviceWidgetGeometry(device_type=device.device_type)
        else:
            logging.debug(
                "Ignoring optimal display name %s and other details because that "
                "device was removed",
                optimal_display_name,
            )

    @pyqtSlot(int, "PyQt_PyObject")
    def scanProblemsReceived(self, scan_id: int, problems: Problems) -> None:
        self.addErrorLogMessage(problems=problems)

    @pyqtSlot(int)
    def scanFatalError(self, scan_id: int) -> None:
        try:
            device = self.devices[scan_id]
        except KeyError:
            logging.debug(
                "Got scan error from device that no longer exists (scan_id %s)", scan_id
            )
            return

        h1 = (
            _("Sorry, an unexpected problem occurred while scanning %s.")
            % device.display_name
        )
        h2 = _("Unfortunately you cannot download from this device.")
        header = f"<b>{h1}</b><br><br>{h2}"
        if device.device_type == DeviceType.camera and not device.is_mtp_device:
            h3 = _(
                "A possible workaround for the problem might be downloading from the "
                "camera's memory card using a card reader."
            )
            header = f"{header}<br><br><i>{h3}</i>"

        title = _("Device scan failed")
        self.makeProblemReportDialog(header=header, title=title)

        self.removeDevice(scan_id=scan_id, show_warning=False)

    @pyqtSlot(int)
    def cameraRemovedDuringScan(self, scan_id: int) -> None:
        """
        Scenarios: a camera was physically removed, or file transfer was disabled on
        an MTP device.

        If disabled, a problem is that the device has not yet been removed from the
        system.

        But in any case, sometimes camera removal is not picked up by the system while
        it's being accessed. So let's remove it ourselves.

        :param scan_id: device that was removed / disabled
        """

        try:
            device = self.devices[scan_id]
        except KeyError:
            logging.debug(
                "Got scan error from device that no longer exists (scan id %s)", scan_id
            )
            return

        logging.debug("Camera %s was removed during a scan", device.display_name)
        self.removeDevice(scan_id=scan_id)

    @pyqtSlot(int)
    def cameraRemovedWhileThumbnailing(self, scan_id: int) -> None:
        """
        Scenarios: a camera was physically removed, or file transfer was disabled on an
        MTP device.

        If disabled, a problem is that the device has not yet been removed from the
        system.

        But in any case, sometimes camera removal is not picked up by the system while
        it's being accessed. So let's remove it ourselves.

        :param scan_id: device that was removed / disabled
        """

        try:
            device = self.devices[scan_id]
        except KeyError:
            logging.debug(
                "Got thumbnailing error from a camera that no longer exists "
                "(scan id %s)",
                scan_id,
            )
            return

        logging.debug(
            "Camera %s was removed while thumbnails were being generated",
            device.display_name,
        )
        self.removeDevice(scan_id=scan_id)

    @pyqtSlot(int)
    def cameraRemovedWhileCopyingFiles(self, scan_id: int) -> None:
        """
        Scenarios: a camera was physically removed, or file transfer was disabled on an
        MTP device.

        If disabled, a problem is that the device has not yet been removed from the
        system.

        But in any case, sometimes camera removal is not picked up by the system while
        it's being accessed. So let's remove it ourselves.

        :param scan_id: device that was removed / disabled
        """

        try:
            device = self.devices[scan_id]
        except KeyError:
            logging.debug(
                "Got copy files error from a camera that no longer exists (scan id %s)",
                scan_id,
            )
            return

        logging.debug(
            "Camera %s was removed while filed were being copied from it",
            device.display_name,
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
        (
            results_summary,
            file_types_present,
        ) = device.file_type_counter.summarize_file_count()
        self.download_tracker.set_file_types_present(scan_id, file_types_present)
        model = self.mapModel(scan_id)
        model.updateDeviceScan(scan_id)
        destinations_good = self.setDownloadCapabilities()

        self.logState()

        if len(self.devices.scanning) == 0:
            self.generateTemporalProximityTableData(
                "a download source has finished being scanned"
            )
        else:
            self.temporalProximity.setState(TemporalProximityState.pending)

        auto_start = False if not destinations_good else self.autoStart(scan_id)

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
                        "Not auto-starting download, because a job code is already "
                        "being prompted for."
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
        :return: True if the download should start automatically, else False
        """

        prefs_valid, msg = self.prefs.check_prefs_for_validity()
        if not prefs_valid:
            return False

        if not self.thumbnailModel.filesAreMarkedForDownload(scan_id):
            logging.debug(
                "No files are marked for download for %s",
                self.devices[scan_id].display_name,
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
                "because a rebuild is required ",
                reason,
            )
            return

        rows = self.thumbnailModel.dataForProximityGeneration()
        if rows:
            logging.info("Generating Timeline because %s", reason)

            self.temporalProximity.setState(TemporalProximityState.generating)
            data = OffloadData(
                thumbnail_rows=rows, proximity_seconds=self.prefs.proximity_seconds
            )
            self.sendToOffload(data=data)
        else:
            logging.info(
                "Was tasked to generate Timeline because %s, but there is nothing to "
                "generate",
                reason,
            )

    @pyqtSlot(TemporalProximityGroups)
    def proximityGroupsGenerated(
        self, proximity_groups: TemporalProximityGroups
    ) -> None:
        if self.temporalProximity.setGroups(proximity_groups=proximity_groups):
            self.thumbnailModel.assignProximityGroups(proximity_groups.col1_col2_uid)
        self.temporalProximity.setProximityHeight()
        self.sourcePanel.setSplitterSize()

    def closeEvent(self, event: QCloseEvent) -> None:
        logging.debug("Close event activated")

        if self.is_wsl2 and not self.wslDrives.unmountDrives(at_exit=True):
            logging.debug("Ignoring close event because user cancelled unmount drives")
            event.ignore()
            return

        # TODO test what happens when a download is running and is wsl2 with auto
        #  unmount

        if self.close_event_run:
            logging.debug("Close event already run: accepting close event")
            event.accept()
            return

        if ApplicationState.normal & self.application_state:
            self.setCoreState(ApplicationState.exiting)
            self.sendStopToThread(self.scan_controller)
            self.thumbnailModel.stopThumbnailer()
            self.sendStopToThread(self.copy_controller)

            if self.downloadIsRunning():
                logging.debug("Exiting while download is running. Cleaning up...")
                # Update prefs with stored sequence number and downloads today
                # values
                data = RenameAndMoveFileData(
                    message=RenameAndMoveStatus.download_completed
                )
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

        if self.is_wsl2:
            QTimer.singleShot(0, self.wslDriveMonitor.stopMonitor)

        if self.mountMonitorActive():
            self.mountMonitorTimer.stop()

        if self.unity_progress:
            for launcher in self.desktop_launchers:
                launcher.set_property("count", 0)
                launcher.set_property("count_visible", False)
                launcher.set_property("progress_visible", False)

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

        if self.use_udsisks:
            self.udisks2MonitorThread.quit()
            self.udisks2MonitorThread.wait()
            self.cameraHotplugThread.quit()
            self.cameraHotplugThread.wait()
        elif self.gvfs_controls_mounts:
            del self.gvolumeMonitor
        elif self.wslDriveMonitor:
            self.wslDriveMonitorThread.quit()
            if not self.wslDriveMonitorThread.wait(1000):
                logging.debug(
                    "Terminating WSL Drive Monitor thread "
                    "(probably due to unfinished wmic.exe call)"
                )
                self.wslDriveMonitorThread.terminate()
                self.wslDriveMonitorThread.wait(1000)

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
        logging.debug("Unmounting any devices mounted with FUSE")
        self.devices.unmount_fuse_devices()
        tc = ThumbnailCacheSql(create_table_if_not_exists=False)
        logging.debug("Cleaning up Thumbnail cache")
        tc.cleanup_cache(days=self.prefs.keep_thumbnails_days)

        QDesktopServices.unsetUrlHandler("file")

        Notify.uninit()

        self.close_event_run = True

        logging.debug("Accepting close event")
        event.accept()

    def getIconsAndEjectableForMount(
        self, mount: QStorageInfo
    ) -> tuple[list[str], bool]:
        """
        Given a mount, get the icon names suggested by udev or
        GVFS, and  determine whether the mount is ejectable or not.
        :param mount:  the mount to check
        :return: icon names and eject boolean
        """

        if self.is_wsl2:
            mount_point = mount.rootPath()
            assert self.wslDrives.knownMountPoint(mount_point)
            icon_names, can_eject = self.wslDrives.driveProperties(
                mount_point=mount_point
            )
        elif self.gvfs_controls_mounts:
            icon_names, can_eject = self.gvolumeMonitor.getProps(mount.rootPath())
        else:
            # get the system device e.g. /dev/sdc1
            system_device = mount.device().data().decode()
            icon_names, can_eject = self.udisks2Monitor.get_device_props(system_device)
        return icon_names, can_eject

    def addToDeviceDisplay(self, device: Device, scan_id: int) -> None:
        self.mapModel(scan_id).addDevice(scan_id, device)
        self.updateDeviceWidgetGeometry(device_type=device.device_type)

    def updateDeviceWidgetGeometry(self, device_type: DeviceType):
        if device_type != DeviceType.path:
            self.deviceView.updateGeometry()
        if device_type == DeviceType.path:
            self.thisComputerView.updateGeometry()

    @pyqtSlot()
    def cameraAdded(self) -> None:
        if not self.prefs.device_autodetection:
            logging.debug("Ignoring camera as device auto detection is off")
        else:
            logging.debug(
                "Assuming camera will not be mounted: immediately proceeding with scan"
            )
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
        sc = autodetect_cameras()
        system_cameras = (
            (model, port) for model, port in sc if not port.startswith("disk:")
        )
        kc = self.devices.cameras.items()
        known_cameras = ((model, port) for port, model in kc)
        removed_cameras = set(known_cameras) - set(system_cameras)
        for model, port in removed_cameras:
            scan_id = self.devices.scan_id_from_camera_model_port(model, port)
            if scan_id is None:
                logging.debug(
                    "The camera with scan id %s was already removed, or was never "
                    "added",
                    scan_id,
                )
            else:
                device = self.devices[scan_id]
                # Don't log a warning when the camera was removed while the user was
                # being informed it was locked or inaccessible
                show_warning = device not in self.prompting_for_user_action
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
        # TODO Implement noGVFSAutoMount()
        # however, I have no idea under what circumstances it is called
        logging.error("Implement noGVFSAutoMount()")

    @pyqtSlot()
    def cameraMounted(self) -> None:
        if have_gio:
            self.searchForCameras()

    @pyqtSlot(str)
    def cameraVolumeAdded(self, path):
        assert self.gvfs_controls_mounts
        self.searchForCameras()

    def unmountCameraToEnableScan(self, model: str, port: str) -> bool:
        """
        Possibly "unmount" a camera or phone controlled by GVFS so it can be scanned

        :param model: camera model
        :param port: port used by camera
        :param on_startup: if True, the unmount is occurring during
         the program's startup phase
        :return: True if unmount operation initiated, else False
        """

        if self.gvfs_controls_mounts:
            self.devices.cameras_to_gvfs_unmount_for_scan[port] = model
            unmounted = self.gvolumeMonitor.unmountCamera(
                model=model,
                port=port,
                post_unmount_action=PostCameraUnmountAction.scan,
            )
            if unmounted:
                logging.debug("Successfully unmounted %s", model)
                return True
            else:
                logging.debug("%s was not already mounted", model)
                del self.devices.cameras_to_gvfs_unmount_for_scan[port]
        return False

    @pyqtSlot(bool, str, str, PostCameraUnmountAction)
    def cameraUnmounted(
        self,
        result: bool,
        model: str,
        port: str,
        post_camera_unmount_action: PostCameraUnmountAction,
    ) -> None:
        """
        Handle the attempt to unmount a GVFS mounted camera.

        Note: cameras that have not yet been scanned do not yet have a scan_id assigned!
        An obvious point, but easy to forget.

        :param result: result from the GVFS operation
        :param model: camera model
        :param port: camera port
        :param download_started: whether the unmount happened because a download
         was initiated
        """

        if post_camera_unmount_action == PostCameraUnmountAction.scan:
            assert self.devices.cameras_to_gvfs_unmount_for_scan[port] == model
            del self.devices.cameras_to_gvfs_unmount_for_scan[port]
            if result:
                self.startCameraScan(model=model, port=port)
            else:
                # Get the camera's short model name, instead of using the exceptionally
                # long name that gphoto2 can sometimes use. Get the icon too.
                camera = Device()
                camera.set_download_from_camera(model, port)

                logging.debug(
                    "Not scanning %s because it could not be unmounted",
                    camera.display_name,
                )

                # Translators: %(variable)s represents Python code, not a plural of the
                # term variable. You must keep the %(variable)s untranslated, or the
                # program will crash.
                # Translators: please do not change HTML codes like <br>, <i>, </i>,
                # or <b>, </b> etc.
                message = _(
                    "<b>The %(camera)s cannot be scanned because it cannot be "
                    "unmounted.</b><br><br>You can close any other application (such "
                    "as a file browser) that is using it and try again. If that does "
                    "not work, unplug the %(camera)s from the computer and plug it "
                    "in again."
                ) % dict(camera=camera.display_name)

                # Show the main window if it's not yet visible
                self.showMainWindow()
                msgBox = standardMessageBox(
                    message=message,
                    rich_text=True,
                    standardButtons=QMessageBox.Ok,
                    iconPixmap=camera.get_pixmap(),
                )
                msgBox.exec()
        elif post_camera_unmount_action == PostCameraUnmountAction.download:
            # A download was initiated

            scan_id = self.devices.scan_id_from_camera_model_port(model, port)
            self.devices.cameras_to_gvfs_unmount_for_download.remove(scan_id)
            if result:
                if not self.devices.download_start_blocked():
                    self.startDownloadPhase2()
            else:
                camera = self.devices[scan_id]
                display_name = camera.display_name

                title = _("Rapid Photo Downloader")
                # Translators: %(variable)s represents Python code, not a plural of the
                # term variable. You must keep the %(variable)s untranslated, or the
                # program will crash.
                # Translators: please do not change HTML codes like <br>, <i>, </i>,
                # or <b>, </b> etc.
                message = _(
                    "<b>The download cannot start because the %(camera)s cannot be "
                    "unmounted.</b><br><br>You can close any other application (such "
                    "as a file browser) that is using it and try again. If that does "
                    "not work, unplug the %(camera)s from the computer and plug it "
                    "in again, and choose which files you want to download from it."
                ) % dict(camera=display_name)
                msgBox = QMessageBox(
                    QMessageBox.Warning, title, message, QMessageBox.Ok
                )
                msgBox.setIconPixmap(camera.get_pixmap())
                msgBox.exec_()
        else:
            scan_id = self.devices.scan_id_from_camera_model_port(model, port)
            if scan_id:
                device = self.devices[scan_id]
                name = device.display_name
            else:
                name = ""
            logging.debug("Taking no additional action after unmounting %s", name)

    def searchForCameras(self) -> None:
        """
        Detect using gphoto2 any cameras attached to the computer.

        Initiates unmount of cameras that are mounted by GIO/GVFS.
        """

        logging.debug("Searching for cameras")
        if self.prefs.device_autodetection:
            cameras = autodetect_cameras()
            for model, port in cameras:
                if port in self.devices.cameras_to_gvfs_unmount_for_scan:
                    assert self.devices.cameras_to_gvfs_unmount_for_scan[port] == model
                    logging.debug("Already unmounting %s", model)
                elif self.devices.known_camera(model, port):
                    if self.gvfs_controls_mounts:
                        mount_point = self.gvolumeMonitor.ptpCameraMountPoint(
                            model, port
                        )
                        if mount_point is not None:
                            scan_id = self.devices.scan_id_from_camera_model_port(
                                model, port
                            )
                            if scan_id is None:
                                logging.critical(
                                    "Camera is recognized by model and port, but no "
                                    "scan_id exists for it: %s %s",
                                    model,
                                    port,
                                )
                                return
                            device = self.devices[scan_id]
                            if device.is_apple_mobile:
                                logging.info(
                                    "GIO has automatically mounted an iOS device '%s' "
                                    "that is currently %s",
                                    device.display_name,
                                    self.devices.device_state[scan_id].name,
                                )
                            else:
                                logging.info(
                                    "GIO has automatically mounted a camera '%s' that "
                                    "is currently %s",
                                    device.display_name,
                                    self.devices.device_state[scan_id].name,
                                )
                            logging.info(
                                "Will subsequently unmount '%s'", device.display_name
                            )
                            self.gvolumeMonitor.unmountCamera(
                                model,
                                port,
                                post_unmount_action=PostCameraUnmountAction.nothing,
                                mount_point=mount_point,
                            )
                elif self.devices.user_marked_camera_as_ignored(model, port):
                    logging.debug("Ignoring camera marked as removed by user %s", model)
                elif not port.startswith("disk:"):
                    device = Device()
                    device.set_download_from_camera(model, port)
                    if device.udev_name in self.prefs.camera_blacklist:
                        logging.debug("Ignoring blacklisted camera %s", model)
                    elif (
                        device.is_apple_mobile
                        and not storageidevice.utilities_present()
                    ):
                        logging.warning(
                            "Ignoring iOS device '%s' because required helper "
                            "applications are not installed.",
                            device.display_name,
                        )
                        logging.warning(
                            "Missing applications: %s",
                            make_internationalized_list(
                                storageidevice.ios_missing_programs()
                            ),
                        )
                        self.iOSIssueErrorMessage(display_name=device.display_name)
                    else:
                        logging.debug("Detected %s on port %s", model, port)
                        self.devices.cache_camera(device)
                        # almost always, libgphoto2 cannot access a camera when
                        # it is mounted by another process, like Gnome's GVFS
                        # or any other system. Before attempting to scan the
                        # camera, check to see if it's mounted and if so,
                        # unmount it. Unmounting is asynchronous.
                        if not self.unmountCameraToEnableScan(model=model, port=port):
                            self.startCameraScan(model=model, port=port)

    def startCameraScan(
        self,
        model: str,
        port: str,
    ) -> None:
        """
        Initiate the scan of an unmounted camera

        :param model: camera model
        :param port:  camera port
        """
        device = self.devices.remove_camera_from_cache(model, port)
        if device is None:
            device = Device()
            device.set_download_from_camera(model, port)
        self.startDeviceScan(device=device)

    def startDeviceScan(self, device: Device) -> None:
        """
        Initiate the scan of a device (camera, this computer path, or external device)

        :param device: device to scan
        """

        scan_id = self.devices.add_device(device=device, on_startup=self.on_startup)
        logging.debug("Assigning scan id %s to %s", scan_id, device.name())
        self.thumbnailModel.addOrUpdateDevice(scan_id)
        self.addToDeviceDisplay(device, scan_id)
        self.updateSourceButton()
        scan_arguments = ScanArguments(
            device=device,
            ignore_other_types=self.ignore_other_photo_types,
            log_gphoto2=self.log_gphoto2,
        )
        self.sendStartWorkerToThread(
            self.scan_controller, worker_id=scan_id, data=scan_arguments
        )
        self.devices.set_device_state(scan_id, DeviceState.scanning)
        self.setDownloadCapabilities()
        self.updateProgressBarState()
        self.displayMessageInStatusBar()

        if not self.on_startup and self.thumbnailModel.anyCompletedDownloads():
            if self.prefs.completed_downloads == int(CompletedDownloads.prompt):
                logging.info("Querying whether to clear completed downloads")
                counter = self.thumbnailModel.getFileDownloadsCompleted()

                numbers = counter.file_types_present_details(
                    singular_natural=True
                ).capitalize()
                plural = sum(counter.values()) > 1
                if plural:
                    title = _("Completed Downloads Present")
                    body = (
                        _("%s whose download have completed are displayed.") % numbers
                    )
                    question = _("Do you want to clear the completed downloads?")
                else:
                    title = _("Completed Download Present")
                    body = _("%s whose download has completed is displayed.") % numbers
                    question = _("Do you want to clear the completed download?")
                message = f"<b>{title}</b><br><br>{body}<br><br>{question}"

                questionDialog = RememberThisDialog(
                    message=message,
                    icon="rapid-photo-downloader.svg",
                    remember=RememberThisMessage.do_not_ask_again,
                    parent=self,
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
            if not self.prefs.scan_specific_folders or has_one_or_more_folders(
                path=path, folders=self.prefs.folders_to_scan
            ):
                if not self.devices.user_marked_volume_as_ignored(path):
                    return True
                else:
                    logging.debug(
                        "Not scanning volume with path %s because it was set to be "
                        "temporarily ignored",
                        path,
                    )
            else:
                logging.debug(
                    "Not scanning volume with path %s because it lacks a folder at the "
                    "base level that indicates it should be scanned",
                    path,
                )
        return False

    def prepareNonCameraDeviceScan(self, device: Device) -> None:
        """
        Initiates a device scan for volume.

        If non-DCIM device scans are enabled, and the device is not whitelisted
        (determined by the display name), then the user is prompted whether to download
        from the device.

        :param device: device to scan
        """

        if not self.devices.known_device(device):
            if (
                self.scanEvenIfNoFoldersLikeDCIM()
                and device.display_name not in self.prefs.volume_whitelist
            ):
                logging.debug("Prompting whether to use device %s", device.display_name)
                # prompt user to see if device should be used or not
                self.showMainWindow()
                message = _(
                    "Do you want to download photos and videos from the device <i>%("
                    "device)s</i>?"
                ) % dict(device=device.display_name)
                use = RememberThisDialog(
                    message=message,
                    icon=device.get_pixmap(),
                    remember=RememberThisMessage.remember_choice,
                    parent=self,
                    title=device.display_name,
                )
                if use.exec():
                    if use.remember:
                        logging.debug("Whitelisting device %s", device.display_name)
                        self.prefs.add_list_value(
                            key="volume_whitelist", value=device.display_name
                        )
                    self.startDeviceScan(device=device)
                else:
                    logging.debug(
                        "Device %s rejected as a download device", device.display_name
                    )
                    if (
                        use.remember
                        and device.display_name not in self.prefs.volume_blacklist
                    ):
                        logging.debug("Blacklisting device %s", device.display_name)
                        self.prefs.add_list_value(
                            key="volume_blacklist", value=device.display_name
                        )
            else:
                self.startDeviceScan(device=device)

    @pyqtSlot("PyQt_PyObject")
    def wslWindowsDriveAdded(self, drives: list[WindowsDriveMount]) -> None:
        if self.on_exit:
            logging.debug("Ignoring added WSL drives during exit")
            return

        wsl_drive_previously_probed = self.wsl_drives_probed
        self.wsl_drives_probed = True
        for drive in drives:
            logging.info(
                "Detected Windows drive %s: %s %s",
                drive.drive_letter,
                drive.label,
                drive.mount_point or "(not mounted)",
            )
            self.wslDrives.addDrive(drive)
        self.wslDrives.logDrives()

        if not wsl_drive_previously_probed:
            if self.wsl_backup_drives_refresh_needed:
                self.backupPanel.updateLocationCombos()
            if self.prefs.backup_files:
                self.setupBackupDevices()
        if not self.on_startup:
            self.wslDrives.mountDrives()
        self.setupNonCameraDevices()

    @pyqtSlot("PyQt_PyObject")
    def wslWindowsDriveRemoved(self, drive: WindowsDriveMount) -> None:
        if self.on_exit:
            logging.debug("Ignoring removed WSL drives during exit")
            return

        logging.info(
            "Detected removal of Windows drive %s: %s %s",
            drive.drive_letter,
            drive.label,
            drive.mount_point,
        )
        self.wslDrives.removeDrive(drive)

    @pyqtSlot("PyQt_PyObject")
    def wslWindowsDriveMounted(self, drives: list[WindowsDriveMount]) -> None:
        if self.on_exit:
            logging.debug("Ignoring mounted WSL drives during exit")
            return

        for drive in drives:
            icon_names, can_eject = self.wslDrives.driveProperties(
                mount_point=drive.mount_point
            )
            self.partitionMounted(
                path=drive.mount_point, iconNames=icon_names, canEject=can_eject
            )

    @pyqtSlot("PyQt_PyObject")
    def wslWindowsDriveUnmounted(self, drives: list[WindowsDriveMount]) -> None:
        for drive in drives:
            self.partitionUmounted(path=drive.mount_point)

    @pyqtSlot(str, "PyQt_PyObject", bool)
    def partitionMounted(self, path: str, iconNames: list[str], canEject: bool) -> None:
        """
        Setup devices from which to download from and backup to, and
        if relevant start scanning them

        :param path: the path of the mounted partition
        :param iconNames: a list of names of icons used in themed icons
        associated with this partition
        :param canEject: whether the partition can be ejected or not
        """

        if path not in mountPaths():
            logging.info("Ignoring path %s because it is not a mount", path)
            return

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
                            len(self.backup_devices.video_backup_devices),
                        )
                        self.displayMessageInStatusBar()
                        self.backupPanel.addBackupVolume(
                            mount_details=self.backup_devices.get_backup_volume_details(
                                path
                            )
                        )
                        if self.prefs.backup_device_autodetection:
                            self.backupPanel.updateExample()

                elif self.shouldScanMount(mount):
                    device = Device()
                    if self.is_wsl2:
                        display_name = self.wslDrives.displayName(mount.rootPath())
                    else:
                        display_name = mount.displayName()
                    device.set_download_from_volume(
                        path, display_name, iconNames, canEject, mount
                    )
                    self.prepareNonCameraDeviceScan(device=device)
            else:
                if not mount.isValid():
                    logging.warning("Mount %s is invalid", mount.name())
                elif not mount.isReady():
                    logging.warning("Mount %s is not ready", mount.name())

    @pyqtSlot(str)
    def partitionUmounted(self, path: str) -> None:
        """
        Handle the unmounting of partitions by the system / user.

        :param path: the path of the partition just unmounted
        """

        if not path:
            return

        device_removed = False
        if self.devices.known_path(path, DeviceType.volume):
            # four scenarios -
            # the mount is being scanned
            # the mount has been scanned but downloading has not yet started
            # files are being downloaded from mount
            # files have finished downloading from mount
            scan_id = self.devices.scan_id_from_path(path, DeviceType.volume)
            self.removeDevice(scan_id=scan_id)
            device_removed = True

        elif path in self.backup_devices:
            self.removeBackupDevice(path)
            self.backupPanel.removeBackupVolume(path=path)
            self.displayMessageInStatusBar()
            self.download_tracker.set_no_backup_devices(
                len(self.backup_devices.photo_backup_devices),
                len(self.backup_devices.video_backup_devices),
            )
            if self.prefs.backup_device_autodetection:
                self.backupPanel.updateExample()
            device_removed = True

        if device_removed:
            if self.mountMonitorActive():
                if self.valid_mount_count <= 0:
                    logging.warning("Unexpected valid mount count")
                else:
                    self.valid_mount_count -= 1
            self.setDownloadCapabilities()

    def removeDevice(
        self,
        scan_id: int,
        show_warning: bool = True,
        adjust_temporal_proximity: bool = True,
        ignore_in_this_program_instantiation: bool = False,
    ) -> None:
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
                    logging.warning(
                        "Removed device %s was being scanned", device.name()
                    )
                elif device_state == DeviceState.downloading:
                    logging.error(
                        "Removed device %s was being downloaded from", device.name()
                    )
                elif device_state == DeviceState.thumbnailing:
                    logging.warning(
                        "Removed device %s was having thumbnails generated",
                        device.name(),
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
                self.download_tracker.device_removed_mid_download(
                    scan_id, device.display_name
                )
                del self.time_remaining[scan_id]
                self.notifyDownloadedFromDevice(scan_id=scan_id)
            # TODO need correct check for "is thumbnailing", given is now asynchronous
            elif device_state == DeviceState.thumbnailing:
                self.thumbnailModel.terminateThumbnailGeneration(scan_id)

            if ignore_in_this_program_instantiation:
                self.devices.ignore_device(scan_id=scan_id)

            self.folder_preview_manager.remove_folders_for_device(scan_id=scan_id)

            del self.devices[scan_id]
            self.updateDeviceWidgetGeometry(device_type=device.device_type)

            if device.device_type == DeviceType.path:
                self.thisComputer.setViewVisible(False)

            self.updateSourceButton()
            self.setDownloadCapabilities()

            if adjust_temporal_proximity:
                state = self.proximityStatePostDeviceRemoval()
                if state == TemporalProximityState.empty:
                    self.temporalProximity.setState(TemporalProximityState.empty)
                elif files_removed:
                    self.generateTemporalProximityTableData(
                        "a download source was removed"
                    )
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
        if device.device_type in (DeviceType.camera, DeviceType.camera_fuse):
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
            if (not ignore_cameras or device.device_type == DeviceType.volume) or (
                rescan_path and device.device_type == DeviceType.path
            ):
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
        if device.device_type in (DeviceType.camera, DeviceType.camera_fuse):
            text = _(
                "<b>Do you want to ignore the %s whenever this program is run?</b>"
            )
            text = text % device.display_name
            info_text = _(
                "All cameras, phones and tablets with the same model name will be "
                "ignored."
            )
        else:
            assert device.device_type == DeviceType.volume
            text = _(
                "<b>Do you want to ignore the device %s whenever this program is "
                "run?</b>"
            )
            text = text % device.display_name
            info_text = _("Any device with the same name will be ignored.")

        msgbox = QMessageBox()
        msgbox.setWindowTitle(_("Rapid Photo Downloader"))
        msgbox.setIcon(QMessageBox.Question)
        msgbox.setText(text)
        msgbox.setTextFormat(Qt.RichText)
        msgbox.setInformativeText(info_text)
        msgbox.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        if msgbox.exec() == QMessageBox.Yes:
            if device.device_type in (DeviceType.camera, DeviceType.camera_fuse):
                self.prefs.add_list_value(
                    key="camera_blacklist", value=device.udev_name
                )
                logging.debug("Added %s to camera blacklist", device.udev_name)
            else:
                self.prefs.add_list_value(
                    key="volume_blacklist", value=device.display_name
                )
                logging.debug("Added %s to volume blacklist", device.display_name)
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
            len(self.backup_devices.video_backup_devices),
        )

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
            logging.critical(
                "Backup devices should never be reset when a download is occurring"
            )
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

    @pyqtSlot()
    def manuallyMonitorNewMounts(self) -> None:
        """
        Determine if the number of valid mounts differs from our stored count.

        Initiate scans for devices if they do differ.
        """

        if not self.monitorPartitionChanges():
            return

        valid_mount_count = len(self.validMounts.mountedValidMountPoints())
        if valid_mount_count > self.valid_mount_count:
            logging.debug(
                "Mount count differs: conducting probe for new cameras and non camera "
                "devices"
            )
            self.manuallyProbeForNewMount()
        elif valid_mount_count < self.valid_mount_count:
            logging.warning("Mount count differs: device has been removed")
            self.valid_mount_count -= 1

    def manuallyProbeForNewMount(self):
        validMounts = self.validMounts.mountedValidMountPoints()
        self.valid_mount_count = len(validMounts)

        for mount in validMounts:
            if self.partitionValid(mount):
                path = mount.rootPath()
                if self.isBackupPath(path):
                    known_path = path in self.backup_devices
                    mount_type = "backup"
                else:
                    known_path = self.devices.known_path(
                        path=path, device_type=DeviceType.volume
                    )
                    mount_type = "download"
                if known_path:
                    logging.debug(
                        "Manual probe indicates %s is already in use as a %s device",
                        mount.displayName(),
                        mount_type,
                    )
                    continue
                logging.info(
                    "Manual probe indicates %s is not yet used as a device",
                    mount.displayName(),
                )
                device: QByteArray = mount.device()
                device_path = device.data().decode()
                self.udisks2Monitor.add_device(
                    device_path=device_path, mount_point=path
                )
                icon_names, can_eject = self.udisks2Monitor.get_device_props(
                    device_path
                )
                self.partitionMounted(
                    path=path, iconNames=icon_names, canEject=can_eject
                )

    def setupNonCameraDevices(self, scanning_again: bool = False) -> None:
        """
        Setup devices from which to download and initiates their scan.

        :param scanning_again: if True, the search is occurring after a preference
         value change, where devices may have already been scanned.
        """

        if not self.prefs.device_autodetection:
            return

        logging.debug("Setting up non-camera devices")

        mounts: list[QStorageInfo] = []
        validMounts = self.validMounts.mountedValidMountPoints()
        self.valid_mount_count = len(validMounts)

        for mount in validMounts:
            if self.partitionValid(mount):
                path = mount.rootPath()

                if scanning_again and self.devices.known_path(
                    path=path, device_type=DeviceType.volume
                ):
                    logging.debug(
                        "Will not scan %s, because it's associated with an existing "
                        "device",
                        mount.displayName(),
                    )
                    continue

                if path not in self.backup_devices and self.shouldScanMount(mount):
                    logging.debug("Will scan %s", mount.displayName())
                    mounts.append(mount)
                else:
                    logging.debug("Will not scan %s", mount.displayName())

        for mount in mounts:
            device = Device()
            if self.is_wsl2 and not self.wsl_drives_probed:
                # Get place holder values for now
                icon_names = []
                can_eject = False
                display_name = self.wslDrives.displayName(mount.rootPath())
            else:
                icon_names, can_eject = self.getIconsAndEjectableForMount(mount)
                if self.is_wsl2:
                    display_name = self.wslDrives.displayName(mount.rootPath())
                else:
                    display_name = mount.displayName()
            device.set_download_from_volume(
                mount.rootPath(), display_name, icon_names, can_eject, mount
            )
            self.prepareNonCameraDeviceScan(device=device)

    def setupManualPath(self) -> None:
        """
        Setup This Computer path from which to download and initiates scan.

        """

        if not self.prefs.this_computer_source:
            return

        if self.prefs.this_computer_path:
            if not self.confirmManualDownloadLocation():
                logging.debug(
                    "This Computer path %s rejected as download source",
                    self.prefs.this_computer_path,
                )
                self.prefs.this_computer_path = ""
                self.thisComputer.setViewVisible(False)
                return

            # user manually specified the path from which to download
            path = self.prefs.this_computer_path

            if path:
                if os.path.isdir(path) and os.access(path, os.R_OK):
                    logging.debug("Using This Computer path %s", path)
                    device = Device()
                    device.set_download_from_path(path)
                    self.startDeviceScan(device=device)
                else:
                    logging.error("This Computer download path is invalid: %s", path)
            else:
                logging.warning("This Computer download path is not specified")

    def addDeviceToBackupManager(self, path: str) -> None:
        device_id = self.backup_devices.device_id(path)
        self.backup_controller.send_multipart(
            create_inproc_msg(
                b"START_WORKER",
                worker_id=device_id,
                data=BackupArguments(path, self.backup_devices.name(path)),
            )
        )

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
            backup_photo_device = BackupDevice(
                mount=None, backup_type=BackupLocationType.photos
            )
            backup_video_device = BackupDevice(
                mount=None, backup_type=BackupLocationType.videos
            )
            self.backup_devices[backup_photo_location] = backup_photo_device
            self.backup_devices[backup_video_location] = backup_video_device

            logging.info("Backing up photos to %s", backup_photo_location)
            logging.info("Backing up videos to %s", backup_video_location)
        else:
            # videos and photos are being backed up to the same location
            backup_device = BackupDevice(
                mount=None, backup_type=BackupLocationType.photos_and_videos
            )
            self.backup_devices[backup_photo_location] = backup_device

            logging.info("Backing up photos and videos to %s", backup_photo_location)

    def isBackupPath(self, path: str) -> BackupLocationType | bool | None:
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
                # to be used to back up only photos, or videos, or both.
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
        return self.prefs.device_autodetection or self.prefs.backup_device_autodetection

    @pyqtSlot(str)
    def watchedFolderChange(self, path: str) -> None:
        """
        Handle case where a download folder has been removed or altered

        :param path: watched path
        """

        logging.debug(
            "Change in watched folder %s; validating download destinations", path
        )
        valid = True
        if (
            self.prefs.photo_download_folder
            and not validate_download_folder(self.prefs.photo_download_folder).valid
        ):
            valid = False
            logging.debug(
                "Photo download destination %s is now invalid",
                self.prefs.photo_download_folder,
            )
            self.resetDownloadDestination(file_type=FileType.photo, do_update=False)

        if (
            self.prefs.video_download_folder
            and not validate_download_folder(self.prefs.video_download_folder).valid
        ):
            valid = False
            logging.debug(
                "Video download destination %s is now invalid",
                self.prefs.video_download_folder,
            )
            self.resetDownloadDestination(file_type=FileType.video, do_update=False)

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
            "/media",
            "/run",
            os.path.expanduser("~"),
            "/",
            "/bin",
            "/boot",
            "/dev",
            "/lib",
            "/lib32",
            "/lib64",
            "/mnt",
            "/opt",
            "/sbin",
            "/snap",
            "/sys",
            "/tmp",
            "/usr",
            "/var",
            "/proc",
        ):
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            message = (
                "<b>"
                + _("Downloading from %(location)s on This Computer.")
                % dict(location=make_html_path_non_breaking(path))
                + "</b><br><br>"
                + _(
                    "Do you really want to download from here?<br><br>On some systems, "
                    "scanning this location can take a very long time."
                )
            )
            msgbox = standardMessageBox(
                message=message,
                rich_text=True,
                standardButtons=QMessageBox.Yes | QMessageBox.No,
                parent=self,
            )
            return msgbox.exec() == QMessageBox.Yes
        return True

    def scanEvenIfNoFoldersLikeDCIM(self) -> bool:
        """
        Determines if partitions should be scanned even if there is no specific folder
        like a DCIM folder present in the base folder of the file system.

        :return: True if scans of such partitions should occur, else
        False
        """

        return self.prefs.device_autodetection and not self.prefs.scan_specific_folders

    def displayMessageInStatusBar(self) -> None:
        """
        Displays message on status bar.

        Notifies user if scanning or thumbnailing.

        If neither scanning or thumbnailing, displays:
        1. files marked for download
        2. total number files available
        3. how many not shown (user chose to show only new files)
        """

        if self.downloadIsRunning():
            if self.download_paused:
                downloading = self.devices.downloading_from()
                # Translators - in the middle is a unicode em dash - please retain it
                # This string is displayed in the status bar when the download is paused
                # Translators: %(variable)s represents Python code, not a plural of the
                # term variable. You must keep the %(variable)s untranslated, or the
                # program will crash.
                msg = _("%(downloading_from)s — download paused") % dict(
                    downloading_from=downloading
                )
            else:
                # status message updates while downloading are handled in another
                # function
                return
        elif self.devices.thumbnailing:
            devices = [
                self.devices[scan_id].display_name
                for scan_id in self.devices.thumbnailing
            ]
            msg = _("Generating thumbnails for %s") % make_internationalized_list(
                devices
            )
        elif self.devices.scanning:
            devices = [
                self.devices[scan_id].display_name for scan_id in self.devices.scanning
            ]
            msg = _("Scanning %s") % make_internationalized_list(devices)
        else:
            files_avilable = self.thumbnailModel.getNoFilesAvailableForDownload()

            if sum(files_avilable.values()) != 0:
                files_to_download = self.thumbnailModel.getNoFilesMarkedForDownload()
                files_avilable_sum = files_avilable.summarize_file_count()[0]
                files_hidden = self.thumbnailModel.getNoHiddenFiles()

                if files_hidden:
                    # Translators: %(variable)s represents Python code, not a plural of
                    # the term variable. You must keep the %(variable)s untranslated, or
                    # the program will crash.
                    files_checked = _(
                        "%(number)s of %(available files)s marked for download "
                        "(%(hidden)s hidden)"
                    ) % {
                        "number": thousands(files_to_download),
                        "available files": files_avilable_sum,
                        "hidden": files_hidden,
                    }
                else:
                    # Translators: %(variable)s represents Python code, not a plural of
                    # the term variable. You must keep the %(variable)s untranslated, or
                    # the program will crash.
                    files_checked = _(
                        "%(number)s of %(available files)s marked for download"
                    ) % {
                        "number": thousands(files_to_download),
                        "available files": files_avilable_sum,
                    }
                msg = files_checked
            else:
                msg = ""
        self.statusBar().showMessage(msg)


def critical_startup_error(message: str) -> None:
    errorapp = QApplication(sys.argv)
    msg = QMessageBox()
    msg.setWindowTitle(_("Rapid Photo Downloader"))
    msg.setIcon(QMessageBox.Critical)
    msg.setText(f"<b>{message}</b>")
    msg.setInformativeText(_("Program aborting."))
    msg.setStandardButtons(QMessageBox.Ok)
    msg.show()
    errorapp.exec_()


def main():
    # Must parse args before calling QApplication:
    # Calling QApplication.setAttribute below causes QApplication to parse sys.argv

    parser = get_parser()
    args = parser.parse_args()

    this_computer_source: bool | None = None
    this_computer_location: str | None = None

    try:
        force_wayland = linux_desktop() == LinuxDesktop.wsl2
    except Exception:
        force_wayland = False
    platform_cmd_line_overruled = False
    if force_wayland:
        qt_app_args = []
        # strip out any existing "-platform" argument, and its value
        pl = False
        for arg in sys.argv:
            if arg == "-platform":
                pl = True
            elif pl:
                pl = False
                if arg == "xcb":
                    platform_cmd_line_overruled = True
            else:
                qt_app_args.append(arg)

        qt_app_args.extend(["-platform", "wayland"])
        # Modify sys.argv in place
        sys.argv[:] = qt_app_args

    scaling_action = ScalingAction.not_set

    scaling_detected, xsetting_running = any_screen_scaled()

    if scaling_detected == ScalingDetected.undetected:
        scaling_set = "High DPI scaling disabled because no scaled screen was detected"
        fractional_scaling = "Fractional scaling not set"
    else:
        # Set Qt 5 screen scaling if it is not already set in an environment variable
        qt5_variable = qt5_screen_scale_environment_variable()
        scaling_variables = {qt5_variable, "QT_SCALE_FACTOR", "QT_SCREEN_SCALE_FACTORS"}
        if not scaling_variables & set(os.environ):
            scaling_set = (
                "High DPI scaling automatically set to ON because one of the "
                "following environment variables not already "
                "set: {}".format(", ".join(scaling_variables))
            )
            scaling_action = ScalingAction.turned_on
            if parse(QtCore.QT_VERSION_STR) >= parse("5.6.0"):
                QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
            else:
                os.environ[qt5_variable] = "1"
        else:
            scaling_set = (
                "High DPI scaling not automatically set to ON because environment "
                "variable(s) already "
                "set: {}".format(", ".join(scaling_variables & set(os.environ)))
            )
            scaling_action = ScalingAction.already_set

        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

        try:
            # Enable fractional scaling support on Qt 5.14 or above
            # Doesn't seem to be working on Gnome X11, however :-/
            # Works on KDE Neon
            if parse(QtCore.QT_VERSION_STR) >= parse("5.14.0"):
                QApplication.setHighDpiScaleFactorRoundingPolicy(
                    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
                )
                fractional_scaling = "Fractional scaling set to pass through"
            else:
                fractional_scaling = (
                    "Fractional scaling unable to be set because Qt version is "
                    "older than 5.14"
                )
        except Exception:
            fractional_scaling = "Error setting fractional scaling"
            logging.warning(fractional_scaling)

    if sys.platform.startswith("linux") and os.getuid() == 0:
        sys.stderr.write("Never run this program as the sudo / root user.\n")
        critical_startup_error(_("Never run this program as the sudo / root user."))
        sys.exit(1)

    if not shutil.which("exiftool"):
        critical_startup_error(
            _("You must install ExifTool to run Rapid Photo Downloader.")
        )
        sys.exit(1)

    rapid_path = os.path.realpath(
        os.path.dirname(inspect.getfile(inspect.currentframe()))
    )
    import_path = os.path.realpath(os.path.dirname(inspect.getfile(downloadtracker)))
    if rapid_path != import_path:
        sys.stderr.write(
            "Rapid Photo Downloader is installed in multiple locations. Uninstall all "
            "copies except the version you want to run.\n"
        )
        critical_startup_error(
            _(
                "Rapid Photo Downloader is installed in multiple locations.\n\n"
                "Uninstall all copies except the version you want to run."
            )
        )

        sys.exit(1)

    if args.detailed_version:
        file_manager = valid_file_manager()
        print(
            "\n".join(
                get_versions(
                    file_manager=file_manager,
                    scaling_action=scaling_action,
                    scaling_detected=scaling_detected,
                    xsetting_running=xsetting_running,
                    force_wayland=force_wayland,
                    platform_selected=args.platform,
                )
            )
        )
        sys.exit(0)

    if args.extensions:
        photos = list(ext.upper() for ext in PHOTO_EXTENSIONS)
        videos = list(ext.upper() for ext in VIDEO_EXTENSIONS)
        extensions = ((photos, _("Photos")), (videos, _("Videos")))
        for exts, file_type in extensions:
            extensions = make_internationalized_list(exts)
            print(f"{file_type}: {extensions}")
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
    if is_devel_env:
        logging.info(
            "Development environment settings activated because RPD_DEVEL_DEFAULTS "
            "is set"
        )
    if force_wayland:
        if platform_cmd_line_overruled:
            logging.warning("Forcing use of wayland")
        else:
            logging.info("Forcing use of wayland")

    if args.photo_renaming:
        photo_rename = args.photo_renaming == "on"
        if photo_rename:
            logging.info("Photo renaming turned on from command line")
        else:
            logging.info("Photo renaming turned off from command line")
    else:
        photo_rename = None

    if args.video_renaming:
        video_rename = args.video_renaming == "on"
        if video_rename:
            logging.info("Video renaming turned on from command line")
        else:
            logging.info("Video renaming turned off from command line")
    else:
        video_rename = None

    if args.path:
        if args.auto_detect or args.this_computer_source:
            msg = _(
                "When specifying a path on the command line, do not also specify an\n"
                'option for device auto detection or a path on "This Computer".'
            )
            print(msg)
            critical_startup_error(msg.replace("\n", " "))
            sys.exit(1)

        media_dir = get_media_dir()
        auto_detect = args.path.startswith(media_dir) or gvfs_gphoto2_path(args.path)
        if auto_detect:
            this_computer_source = False
            this_computer_location = None
            logging.info(
                "Device auto detection turned on from command line using positional "
                "PATH argument"
            )

        if not auto_detect:
            this_computer_source = True
            this_computer_location = os.path.abspath(args.path)
            logging.info(
                "Downloading from This Computer turned on from command line using "
                "positional PATH argument"
            )

    else:
        if args.auto_detect:
            auto_detect = args.auto_detect == "on"
            if auto_detect:
                logging.info("Device auto detection turned on from command line")
            else:
                logging.info("Device auto detection turned off from command line")
        else:
            auto_detect = None

        if args.this_computer_source:
            this_computer_source = args.this_computer_source == "on"
            if this_computer_source:
                logging.info(
                    "Downloading from This Computer turned on from command line"
                )
            else:
                logging.info(
                    "Downloading from This Computer turned off from command line"
                )
        else:
            this_computer_source = None

        if args.this_computer_location:
            this_computer_location = os.path.abspath(args.this_computer_location)
            logging.info(
                "This Computer path set from command line: %s", this_computer_location
            )
        else:
            this_computer_location = None

    if args.photo_location:
        photo_location = os.path.abspath(args.photo_location)
        logging.info("Photo location set from command line: %s", photo_location)
    else:
        photo_location = None

    if args.video_location:
        video_location = os.path.abspath(args.video_location)
        logging.info("video location set from command line: %s", video_location)
    else:
        video_location = None

    if args.backup:
        backup = args.backup == "on"
        if backup:
            logging.info("Backup turned on from command line")
        else:
            logging.info("Backup turned off from command line")
    else:
        backup = None

    if args.backup_auto_detect:
        backup_auto_detect = args.backup_auto_detect == "on"
        if backup_auto_detect:
            logging.info(
                "Automatic detection of backup devices turned on from command line"
            )
        else:
            logging.info(
                "Automatic detection of backup devices turned off from command line"
            )
    else:
        backup_auto_detect = None

    if args.photo_backup_identifier:
        photo_backup_identifier = args.photo_backup_identifier
        logging.info(
            "Photo backup identifier set from command line: %s", photo_backup_identifier
        )
    else:
        photo_backup_identifier = None

    if args.video_backup_identifier:
        video_backup_identifier = args.video_backup_identifier
        logging.info(
            "Video backup identifier set from command line: %s", video_backup_identifier
        )
    else:
        video_backup_identifier = None

    if args.photo_backup_location:
        photo_backup_location = os.path.abspath(args.photo_backup_location)
        logging.info(
            "Photo backup location set from command line: %s", photo_backup_location
        )
    else:
        photo_backup_location = None

    if args.video_backup_location:
        video_backup_location = os.path.abspath(args.video_backup_location)
        logging.info(
            "Video backup location set from command line: %s", video_backup_location
        )
    else:
        video_backup_location = None

    thumb_cache = args.thumb_cache == "on" if args.thumb_cache else None

    if args.auto_download_startup:
        auto_download_startup = args.auto_download_startup == "on"
        if auto_download_startup:
            logging.info("Automatic download at startup turned on from command line")
        else:
            logging.info("Automatic download at startup turned off from command line")
    else:
        auto_download_startup = None

    if args.auto_download_insertion:
        auto_download_insertion = args.auto_download_insertion == "on"
        if auto_download_insertion:
            logging.info(
                "Automatic download upon device insertion turned on from command line"
            )
        else:
            logging.info(
                "Automatic download upon device insertion turned off from command line"
            )
    else:
        auto_download_insertion = None

    if args.log_gphoto2:
        gphoto_logging = gphoto2_python_logging()  # noqa: F841

    if args.camera_info:
        dump_camera_details()
        sys.exit(0)

    # keep appGuid value in sync with value in upgrade.py
    appGuid = "8dbfb490-b20f-49d3-9b7d-2016012d2aa8"

    # See note at top regarding avoiding crashes
    global app
    app = QtSingleApplication(appGuid, sys.argv)
    if app.isRunning():
        print("Rapid Photo Downloader is already running")
        sys.exit(0)

    app.setOrganizationName("Rapid Photo Downloader")
    app.setOrganizationDomain("damonlynch.net")
    app.setApplicationName("Rapid Photo Downloader")
    app.setWindowIcon(QIcon(data_file_path("rapid-photo-downloader.svg")))
    if not args.force_system_theme:
        app.setStyle("Fusion")

    # Determine the system locale as reported by Qt. Use it to
    # see if Qt has a base translation available, which allows
    # automatic translation of QMessageBox buttons
    try:
        locale = QLocale.system()
        if locale:
            locale_name = locale.name()
            if not locale_name:
                logging.debug("Could not determine system locale using Qt")
            elif locale_name.startswith("en"):
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
        logging.error("Error determining locale via Qt")

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

    if args.delete_thumb_cache or args.forget_files:
        if args.delete_thumb_cache:
            cache = ThumbnailCacheSql(create_table_if_not_exists=False)
            cache.purge_cache()
            print(_("Thumbnail Cache has been reset."))
            logging.debug("Thumbnail Cache has been reset")

        if args.forget_files:
            d = DownloadedSQL()
            count = d.no_downloaded()
            if count:
                d.update_table(reset=True)
            print(
                _("%(count)s remembered files have been forgotten.") % dict(count=count)
            )
            logging.debug("%s remembered files have been forgotten", count)

        logging.debug(
            "Exiting immediately after thumbnail cache / remembered files reset"
        )
        sys.exit(0)

    # Use QIcon to render to get the high DPI version automatically
    size = QSize(600, 400)
    pixmap = scaledIcon(data_file_path("splashscreen.png"), size).pixmap(size)

    splash = SplashScreen(pixmap, Qt.WindowStaysOnTopHint)
    splash.show()
    try:
        display_height = splash.screen().availableGeometry().height()
    except Exception:
        display_height = 0
        logging.warning("Unable to determine display height")

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
        force_wayland=force_wayland,
        platform_selected=args.platform,
        display_height=display_height,
    )

    app.setActivationWindow(rw)
    code = app.exec_()
    logging.debug("Exiting")
    sys.exit(code)


if __name__ == "__main__":
    main()
