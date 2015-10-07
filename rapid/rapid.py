#!/usr/bin/python3
__author__ = 'Damon Lynch'

# Copyright (C) 2011-2015 Damon Lynch <damonlynch@gmail.com>

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
Primary logic for Rapid Photo Downloader.

QT related function and variable names use CamelCase.
Everything else should follow PEP 8.
"""
import sys
import logging
import shutil
import datetime
import os
import pickle
import inspect
from collections import namedtuple
from gettext import gettext as _
from gi.repository import Notify

try:
    from gi.repository import Unity
    have_unity = True
except ImportError:
    have_unity = False

import zmq
import gphoto2 as gp
from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtCore import (QThread, Qt, QStorageInfo, QSettings, QPoint,
                          QSize, QTimer)
from PyQt5.QtGui import (QIcon, QPixmap, QImage)
from PyQt5.QtWidgets import (QAction, QApplication, QMainWindow, QMenu,
                             QPushButton, QWidget, QDialogButtonBox,
        QProgressBar, QSplitter, QFileIconProvider, QHBoxLayout, QVBoxLayout)
import qrc_resources

# import dbus
# from dbus.mainloop.pyqt5 import DBusQtMainLoop


from storage import (ValidMounts, CameraHotplug, UDisks2Monitor,
                     GVolumeMonitor, have_gio, has_non_empty_dcim_folder,
                     mountPaths, get_desktop_environment,
                     gvfs_controls_mounts)
from interprocess import (PublishPullPipelineManager, ScanArguments,
                          CopyFilesArguments, PushPullDaemonManager, RenameAndMoveFileData)
from devices import (Device, DeviceCollection, BackupDevice,
                     BackupDeviceCollection)
from preferences import (Preferences, ScanPreferences)
from constants import (BackupLocationType, DeviceType, ErrorType,
                       FileType, DownloadStatus, RenameAndMoveStatus,
                       photo_rename_test, ApplicationState)
from thumbnaildisplay import (ThumbnailView, ThumbnailTableModel,
    ThumbnailDelegate, DownloadTypes, DownloadStats)
from devicedisplay import (DeviceTableModel, DeviceView, DeviceDelegate)
from utilities import (same_file_system, makeInternationalizedList)
from rpdfile import RPDFile, file_types_by_number
import downloadtracker
from cache import ThumbnailCache
from generatenameconfig import *

logging_level = logging.DEBUG
logging.basicConfig(format='%(asctime)s %(message)s', level=logging_level)


BackupMissing = namedtuple('BackupMissing', ['photo', 'video'])


class RenameMoveFileManager(PushPullDaemonManager):
    message = QtCore.pyqtSignal(bool, RPDFile, int, QPixmap)
    sequencesUpdate = QtCore.pyqtSignal(int, list)
    def __init__(self, context: zmq.Context):
        super(RenameMoveFileManager, self).__init__(context)
        self._process_name = 'Rename and Move File Manager'
        self._process_to_run = 'renameandmovefile.py'

    def rename_file(self, data: RenameAndMoveFileData):
        self.send_message_to_worker(data)

    def process_sink_data(self):
        data = pickle.loads(self.content)
        """ :type : RenameAndMoveFileResults """
        if data.move_succeeded is not None:
            if data.png_data is not None:
                thumbnail = QImage.fromData(data.png_data)
                thumbnail = QPixmap.fromImage(thumbnail)
            else:
                thumbnail = QPixmap()
            self.message.emit(data.move_succeeded, data.rpd_file,
                              data.download_count, thumbnail)
        else:
            assert data.stored_sequence_no is not None
            assert data.downloads_today is not None
            assert isinstance(data.downloads_today, list)
            self.sequencesUpdate.emit(data.stored_sequence_no,
                                      data.downloads_today)


class ScanManager(PublishPullPipelineManager):
    message = QtCore.pyqtSignal(RPDFile)
    def __init__(self, context: zmq.Context):
        super(ScanManager, self).__init__(context)
        self._process_name = 'Scan Manager'
        self._process_to_run = 'scan.py'


class CopyFilesManager(PublishPullPipelineManager):
    message = QtCore.pyqtSignal(bool, RPDFile, int)
    tempDirs = QtCore.pyqtSignal(int, str,str)
    bytesDownloaded = QtCore.pyqtSignal(bytes)
    def __init__(self, context: zmq.Context):
        super(CopyFilesManager, self).__init__(context)
        self._process_name = 'Copy Files Manager'
        self._process_to_run = 'copyfiles.py'

    def process_sink_data(self):
        data = pickle.loads(self.content)
        """ :type : CopyFilesResults"""
        if data.total_downloaded is not None:
            assert data.scan_id is not None
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


class RapidWindow(QMainWindow):
    def __init__(self, parent=None):
        self.do_init = QtCore.QEvent.registerEventType()
        super(RapidWindow, self).__init__(parent)

        self.application_state = ApplicationState.normal

        self.context = zmq.Context()

        self.setWindowTitle(_("Rapid Photo Downloader"))
        self.readWindowSettings()
        self.prefs = Preferences()
        self.setupWindow()

        self.prefs.photo_download_folder = '/data/Photos/Test'
        self.prefs.video_download_folder = '/data/Photos/Test'
        self.prefs.auto_download_at_startup = False
        self.prefs.verify_file = False
        self.prefs.device_autodetection = True
        self.prefs.device_location = \
            '/home/damon/digitalPhotos/rapid/sample-cr2'
        self.prefs.photo_rename = photo_rename_test

        centralWidget = QWidget()

        self.thumbnailView = ThumbnailView()
        self.thumbnailModel = ThumbnailTableModel(self)
        self.thumbnailView.setModel(self.thumbnailModel)
        self.thumbnailView.setItemDelegate(ThumbnailDelegate(self))

        # Devices are cameras and partitions
        self.devices = DeviceCollection()
        self.deviceView = DeviceView()
        self.deviceModel = DeviceTableModel(self)
        self.deviceView.setModel(self.deviceModel)
        self.deviceView.setItemDelegate(DeviceDelegate(self))

        self.createActions()
        self.createLayoutAndButtons(centralWidget)
        self.createMenus()

        # a main-window application must have one and only one central widget
        self.setCentralWidget(centralWidget)

        # defer full initialisation (slow operation) until gui is visible
        QtWidgets.QApplication.postEvent(
            self, QtCore.QEvent(self.do_init), QtCore.Qt.LowEventPriority - 1)


    def readWindowSettings(self):
        settings = QSettings()
        settings.beginGroup("MainWindow")
        pos = settings.value("pos", QPoint(200, 200))
        size = settings.value("size", QSize(650, 670))
        settings.endGroup()
        self.resize(size)
        self.move(pos)

    def writeWindowSettings(self):
        settings = QSettings()
        settings.beginGroup("MainWindow")
        settings.setValue("pos", self.pos())
        settings.setValue("size", self.size())
        settings.endGroup()

    def setupWindow(self):
        status = self.statusBar()
        self.downloadProgressBar = QProgressBar()
        self.downloadProgressBar.setMaximumWidth(150)
        # self.statusLabel.setFrameStyle()
        status.addPermanentWidget(self.downloadProgressBar, .1)

    def event(self, event):
        # Code borrowed from Jim Easterbrook
        if event.type() != self.do_init:
            return QtWidgets.QMainWindow.event(self, event)
        event.accept()
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            self.initialise()
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        return True

    def initialise(self):
        # Setup notification system
        self.have_libnotify = Notify.init('rapid-photo-downloader')

        module_path = os.path.dirname(os.path.abspath(inspect.getfile(
            inspect.currentframe())))
        self.program_svg = os.path.join(module_path,
                         os.path.join('images', 'rapid-photo-downloader.svg'))
        # Initialise use of libgphoto2
        self.gp_context = gp.Context()

        self.validMounts = ValidMounts(
            onlyExternalMounts=self.prefs.only_external_mounts)

        desktop_env = get_desktop_environment()
        self.unity_progress = desktop_env.lower() == 'unity' and have_unity
        if self.unity_progress:
            self.deskop_launcher = Unity.LauncherEntry.get_for_desktop_id(
                "rapid-photo-downloader.desktop")
            if self.deskop_launcher is None:
                self.unity_progress = False

        logging.debug("Desktop environment: %s", desktop_env)
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
            self.cameraHotplug.startMonitor()

            # Monitor when the user adds or removes a partition
            self.udisks2Monitor = UDisks2Monitor(self.validMounts)
            self.udisks2MonitorThread = QThread()
            self.udisks2Monitor.moveToThread(self.udisks2MonitorThread)
            self.udisks2Monitor.partitionMounted.connect(self.partitionMounted)
            self.udisks2Monitor.partitionUnmounted.connect(
                self.partitionUmounted)
            # Start the monitor only on the thread it will be running on
            self.udisks2Monitor.startMonitor()

        #Track the unmounting of cameras by port and model
        self.cameras_to_unmount = {}

        if self.gvfsControlsMounts:
            self.gvolumeMonitor = GVolumeMonitor(self.validMounts)
            self.gvolumeMonitor.cameraUnmounted.connect(self.cameraUnmounted)
            self.gvolumeMonitor.cameraMounted.connect(self.cameraMounted)
            self.gvolumeMonitor.partitionMounted.connect(self.partitionMounted)
            self.gvolumeMonitor.partitionUnmounted.connect(
                self.partitionUmounted)
            self.gvolumeMonitor.volumeAddedNoAutomount.connect(
                self.noGVFSAutoMount)
            self.gvolumeMonitor.cameraPossiblyRemoved.connect(
                self.cameraRemoved)

        # Track the creation of temporary directories
        self.temp_dirs_by_scan_id = {}

        # Track which downloads are running
        self.active_downloads_by_scan_id = set()

        # Track the time a download commences
        self.download_start_time = None

        # Whether a system wide notification message should be shown
        # after a download has occurred in parallel
        self.display_summary_notification = False

        self.download_tracker = downloadtracker.DownloadTracker()

        # Values used to display how much longer a download will take
        self.time_remaining = downloadtracker.TimeRemaining()
        self.time_check = downloadtracker.TimeCheck()

        self.renameThread = QThread()
        self.renamemq = RenameMoveFileManager(self.context)
        self.renamemq.moveToThread(self.renameThread)

        self.renameThread.started.connect(self.renamemq.run_sink)
        self.renamemq.message.connect(self.fileRenamedAndMoved)
        self.renamemq.sequencesUpdate.connect(self.updateSequences)
        self.renamemq.workerFinished.connect(self.fileRenamedAndMovedFinished)

        QTimer.singleShot(0, self.renameThread.start)
        self.renamemq.start()

        # Setup the scan processes
        self.scanThread = QThread()
        self.scanmq = ScanManager(self.context)
        self.scanmq.moveToThread(self.scanThread)

        self.scanThread.started.connect(self.scanmq.run_sink)
        self.scanmq.message.connect(self.scanMessageReceived)
        self.scanmq.workerFinished.connect(self.scanFinished)

        # call the slot with no delay
        QTimer.singleShot(0, self.scanThread.start)

        # Setup the copyfiles process
        self.copyfilesThread = QThread()
        self.copyfilesmq = CopyFilesManager(self.context)
        self.copyfilesmq.moveToThread(self.copyfilesThread)

        self.copyfilesThread.started.connect(self.copyfilesmq.run_sink)
        self.copyfilesmq.message.connect(self.copyfilesDownloaded)
        self.copyfilesmq.bytesDownloaded.connect(self.copyfilesBytesDownloaded)
        self.copyfilesmq.tempDirs.connect(self.tempDirsReceivedFromCopyFiles)
        self.copyfilesmq.workerFinished.connect(self.copyfilesFinished)

        QTimer.singleShot(0, self.copyfilesThread.start)

        prefs_valid, msg = self.prefs.check_prefs_for_validity()
        if not prefs_valid:
            self.notifyPrefsAreInvalid(details=msg)

        self.setDownloadActionSensitivity()
        self.searchForCameras()
        self.setupNonCameraDevices(on_startup=True, on_preference_change=False,
                                   block_auto_start=not prefs_valid)
        self.displayFreeSpaceAndBackups()

    def createActions(self):
        self.downloadAct = QAction("&Download", self, shortcut="Ctrl+Return",
                                   triggered=self.doDownloadAction)

        self.refreshAct = QAction("&Refresh...", self, shortcut="Ctrl+R",
                                  triggered=self.doRefreshAction)

        self.preferencesAct = QAction("&Preferences", self,
                                      shortcut="Ctrl+P",
                                      triggered=self.doPreferencesAction)

        self.quitAct = QAction("&Quit", self, shortcut="Ctrl+Q",
                               triggered=self.close)

        self.checkAllAct = QAction("&Check All", self, shortcut="Ctrl+A",
                                   triggered=self.doCheckAllAction)

        self.checkAllPhotosAct = QAction("Check All Photos", self,
                                         shortcut="Ctrl+T",
                                         triggered=self.doCheckAllPhotosAction)

        self.checkAllVideosAct = QAction("Check All Videos", self,
                                         shortcut="Ctrl+D",
                                         triggered=self.doCheckAllVideosAction)

        self.uncheckAllAct = QAction("&Uncheck All", self, shortcut="Ctrl+L",
                                     triggered=self.doUncheckAllAction)

        self.errorLogAct = QAction("Error Log", self, enabled=False,
                                   checkable=True,
                                   triggered=self.doErrorLogAction)

        self.clearDownloadsAct = QAction("Clear Completed Downloads", self,
                                         triggered=self.doClearDownloadsAction)

        self.previousFileAct = QAction("Previous File", self, shortcut="[",
                                       triggered=self.doPreviousFileAction)

        self.nextFileAct = QAction("Next File", self, shortcut="]",
                                   triggered=self.doNextFileAction)

        self.helpAct = QAction("Get Help Online...", self, shortcut="F1",
                               triggered=help)

        self.reportProblemAct = QAction("Report a Problem...", self,
                                        triggered=self.doReportProblemAction)

        self.makeDonationAct = QAction("Make a Donation...", self,
                                       triggered=self.doMakeDonationAction)

        self.translateApplicationAct = QAction("Translate this Application...",
                                               self,
                                               triggered=self.doTranslateApplicationAction)

        self.aboutAct = QAction("&About...", self, triggered=self.doAboutAction)

    def createLayoutAndButtons(self, centralWidget):
        #TODO change splitter to something else since user can't manipulate it
        splitter = QSplitter()
        splitter.setOrientation(Qt.Vertical)
        splitter.addWidget(self.deviceView)
        splitter.addWidget(self.thumbnailView)
        verticalLayout = QVBoxLayout()
        centralWidget.setLayout(verticalLayout)
        verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.resizeDeviceView()

        verticalLayout.addWidget(splitter)

        # Help and Download buttons
        horizontalLayout = QHBoxLayout()
        horizontalLayout.setContentsMargins(7, 7, 7, 7)
        verticalLayout.addLayout(horizontalLayout, 0)
        self.downloadButton = QPushButton(self.downloadAct.text())
        self.downloadButton.addAction(self.downloadAct)
        self.downloadButton.setDefault(True)
        self.downloadButton.clicked.connect(self.downloadButtonClicked)
        self.download_action_is_download = True
        buttons = QDialogButtonBox(QDialogButtonBox.Help)
        buttons.addButton(self.downloadButton, QDialogButtonBox.ApplyRole)
        horizontalLayout.addWidget(buttons)

    def setDownloadActionSensitivity(self):
        """
        Sets sensitivity of Download action to enable or disable it.
        Affects download button and menu item.
        """
        if not self.downloadIsRunning():
            enabled = False
            # Don't enable starting a download while devices are being scanned
            if len(self.scanmq) == 0:
                enabled = self.thumbnailModel.filesAreMarkedForDownload()

            self.downloadAct.setEnabled(enabled)
            self.downloadButton.setEnabled(enabled)

    def setDownloadActionLabel(self, is_download: bool):
        """
        Toggles action and download button text between pause and
        download
        """
        self.download_action_is_download = is_download
        if self.download_action_is_download:
            text = _("Download")
        else:
            text = _("Pause")
        self.downloadAct.setText(text)
        self.downloadButton.setText(text)

    def createMenus(self):
        self.fileMenu = QMenu("&File", self)
        self.fileMenu.addAction(self.downloadAct)
        self.fileMenu.addAction(self.refreshAct)
        self.fileMenu.addAction(self.preferencesAct)
        self.fileMenu.addAction(self.quitAct)

        self.selectMenu = QMenu("&Select", self)
        self.selectMenu.addAction(self.checkAllAct)
        self.selectMenu.addAction(self.checkAllPhotosAct)
        self.selectMenu.addAction(self.checkAllVideosAct)
        self.selectMenu.addAction(self.uncheckAllAct)



        self.viewMenu = QMenu("&View", self)
        self.viewMenu.addAction(self.errorLogAct)
        self.viewMenu.addAction(self.clearDownloadsAct)
        self.viewMenu.addSeparator()
        self.viewMenu.addAction(self.previousFileAct)
        self.viewMenu.addAction(self.nextFileAct)

        self.helpMenu = QMenu("&Help", self)
        self.helpMenu.addAction(self.helpAct)
        self.helpMenu.addAction(self.reportProblemAct)
        self.helpMenu.addAction(self.makeDonationAct)
        self.helpMenu.addAction(self.translateApplicationAct)
        self.helpMenu.addAction(self.aboutAct)

        self.menuBar().addMenu(self.fileMenu)
        self.menuBar().addMenu(self.selectMenu)
        self.menuBar().addMenu(self.viewMenu)
        self.menuBar().addMenu(self.helpMenu)

    def doDownloadAction(self):
        self.downloadButton.animateClick()

    def doRefreshAction(self):
        pass

    def doPreferencesAction(self):
        pass

    def doCheckAllAction(self):
        pass

    def doCheckAllPhotosAction(self):
        pass

    def doCheckAllVideosAction(self):
        pass

    def doUncheckAllAction(self):
        pass

    def doErrorLogAction(self):
        pass

    def doClearDownloadsAction(self):
        pass

    def doPreviousFileAction(self):
        pass

    def doNextFileAction(self):
        pass

    def doHelpAction(self):
        pass

    def doReportProblemAction(self):
        pass

    def doMakeDonationAction(self):
        pass

    def doTranslateApplicationAction(self):
        pass

    def doAboutAction(self):
        pass

    def downloadButtonClicked(self):
        if False: #self.copy_files_manager.paused:
            logging.debug("Download resumed")
            self.resumeDownload()
        else:
            logging.debug("Download activated")

            if self.download_action_is_download:
                if False:#self.need_job_code_for_naming and not \
                        #self.prompting_for_job_code:

                    #self.get_job_code()
                    pass
                else:
                    self.startDownload()
            else:
                self.pauseDownload()

    def pauseDownload(self):

        self.copyfilesmq.pause()

        # set action to display Download
        if not self.download_action_is_download:
            self.setDownloadActionLabel(is_download = True)

        self.time_check.pause()

    def resumeDownload(self):
        for scan_id in self.active_downloads_by_scan_id:
            self.time_remaining.set_time_mark(scan_id)

        self.time_check.set_download_mark()

        self.copyfilesmq.resume()

    def downloadIsRunning(self) -> bool:
        """
        :return True if a file is currently being downloaded, renamed
        or backed up, else False
        """
        return len(self.active_downloads_by_scan_id) > 0

    def startDownload(self, scan_id=None):
        """
        Start download, renaming and backup of files.

        :param scan_id: if specified, only files matching it will be
        downloaded
        :type scan_id: int
        """

        download_files = self.thumbnailModel.getFilesMarkedForDownload(scan_id)
        invalid_dirs = self.invalidDownloadFolders(
            download_files.download_types)

        if invalid_dirs:
            if len(invalid_dirs) > 1:
                msg = _("These download folders are invalid:\n%("
                        "folder1)s\n%(folder2)s")  % {
                        'folder1': invalid_dirs[0], 'folder2': invalid_dirs[1]}
            else:
                msg = _("This download folder is invalid:\n%s") % \
                      invalid_dirs[0]
            self.log_error(ErrorType.critical_error, _("Download cannot "
                                                       "proceed"), msg)
        else:
            missing_destinations = self.backupDestinationsMissing(
                download_files.download_types)
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

                self.log_error(ErrorType.warning, _("Backup problem"), msg)

            # set time download is starting if it is not already set
            # it is unset when all downloads are completed
            if self.download_start_time is None:
                self.download_start_time = datetime.datetime.now()

            # Set status to download pending
            self.thumbnailModel.markDownloadPending(download_files.files)

            # disable refresh and preferences change while download is
            # occurring
            self.enablePrefsAndRefresh(enabled=False)

            # notify renameandmovefile process to read any necessary values
            # from the program preferences
            data = RenameAndMoveFileData(
                message=RenameAndMoveStatus.download_started)
            self.renamemq.send_message_to_worker(data)

            # Maximum value of progress bar may have been set to the number
            # of thumbnails being generated. Reset it to use a percentage.
            self.downloadProgressBar.setMaximum(100)

            for scan_id in download_files.files:
                files = download_files.files[scan_id]
                # if generating thumbnails for this scan_id, stop it
                if self.thumbnailModel.terminateThumbnailGeneration(scan_id):
                    generate_thumbnails = self.thumbnailModel\
                        .markThumbnailsNeeded(files)
                else:
                    generate_thumbnails = False

                self.downloadFiles(files, scan_id,
                                   download_files.download_stats[scan_id],
                                   generate_thumbnails)

            self.setDownloadActionLabel(is_download=False)


    def downloadFiles(self, files, scan_id: int, download_stats: \
                      DownloadStats, generate_thumbnails: bool):
        """

        :param files: list of the files to download
        :param scan_id: the device from which to download the files
        :param download_stats: count of files and their size
        :param generate_thumbnails: whether thumbnails must be
        generated in the copy files process.
        """

        if download_stats.no_photos > 0:
            photo_download_folder = self.prefs.photo_download_folder
        else:
            photo_download_folder = None

        if download_stats.no_videos > 0:
            video_download_folder = self.prefs.video_download_folder
        else:
            video_download_folder = None

        self.download_tracker.init_stats(scan_id=scan_id, stats=download_stats)
        download_size = download_stats.photos_size_in_bytes + download_stats.videos_size_in_bytes

        if self.prefs.backup_images:
            download_size += ((self.backup_devices.no_photo_backup_devices *
                               download_stats.photos_size_in_bytes) + (
                               self.backup_devices.no_video_backup_devices *
                               download_stats.videos_size_in_bytes))

        self.time_remaining[scan_id] = download_size
        self.time_check.set_download_mark()

        self.active_downloads_by_scan_id.add(scan_id)


        if len(self.active_downloads_by_scan_id) > 1:
            # Display an additional notification once all devices have been
            # downloaded from that summarizes the downloads.
            self.display_summary_notification = True

        if self.auto_start_is_on and self.prefs.generate_thumbnails:
            for rpd_file in files:
                rpd_file.generate_thumbnail = True
            generate_thumbnails = True

        verify_file = self.prefs.verify_file
        if verify_file:
            # since a file might be modified in the file modify process,
            # if it will be backed up, need to refresh the md5 once it has
            # been modified
            refresh_md5_on_file_change = self.prefs.backup_images
        else:
            refresh_md5_on_file_change = False

        #modify_files_during_download = self.modify_files_during_download()
        # if modify_files_during_download:
        #     self.file_modify_manager.add_task((scan_pid, self.prefs.auto_rotate_jpeg, self.focal_length, verify_file, refresh_md5_on_file_change))
        #     modify_pipe = self.file_modify_manager.get_modify_pipe(scan_pid)
        # else:
        #     modify_pipe = None


        # Initiate copy files process

        if generate_thumbnails:
            thumbnail_quality_lower = self.prefs.thumbnail_quality_lower
        else:
            thumbnail_quality_lower = None

        device = self.devices[scan_id]
        copyfiles_args = CopyFilesArguments(scan_id,
                                device,
                                photo_download_folder,
                                video_download_folder,
                                files,
                                verify_file,
                                generate_thumbnails,
                                thumbnail_quality_lower
                                )

        self.copyfilesmq.start_worker(scan_id, copyfiles_args)

    def tempDirsReceivedFromCopyFiles(self, scan_id: int, photo_temp_dir: str,
                                      video_temp_dir: str):
        self.temp_dirs_by_scan_id[scan_id] = list(filter(None,[photo_temp_dir,
                                                  video_temp_dir]))

    def cleanAllTempDirs(self):
        """
        Deletes temporary files and folders used in all downloads
        """
        for scan_id in self.temp_dirs_by_scan_id:
            self.cleanTempDirsForScanId(scan_id, remove_entry=False)
        self.temp_dirs_by_scan_id = {}

    def cleanTempDirsForScanId(self, scan_id: int, remove_entry: bool=True):
        """
        Deletes temporary files and folders used in download
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
                    logging.error("Unknown error deleting temporary  "
                                      "directory %s", d)
        if remove_entry:
            del self.temp_dirs_by_scan_id[scan_id]

    def copyfilesDownloaded(self, download_succeeded: bool,
                                      rpd_file: RPDFile, download_count: int):

        self.download_tracker.set_download_count_for_file(rpd_file.unique_id,
                                                 download_count)
        self.download_tracker.set_download_count(rpd_file.scan_id,
                                                 download_count)
        rpd_file.download_start_time = self.download_start_time
        data = RenameAndMoveFileData(rpd_file=rpd_file,
                                     download_count=download_count,
                                     download_succeeded=download_succeeded)
        self.renamemq.rename_file(data)

    # def copyfilesThumbnail(self, rpd_file: RPDFile, thumbnail: QPixmap):
    #     self.thumbnailModel.

    def copyfilesBytesDownloaded(self, pickled_data: bytes):
        data = pickle.loads(pickled_data)
        """ :type : CopyFilesResults"""
        scan_id = data.scan_id
        total_downloaded = data.total_downloaded
        chunk_downloaded = data.chunk_downloaded
        assert total_downloaded >= 0
        assert chunk_downloaded >= 0
        self.download_tracker.set_total_bytes_copied(scan_id,
                                                     total_downloaded)
        self.time_check.increment(bytes_downloaded=chunk_downloaded)
        percent_complete = self.download_tracker.get_percent_complete(scan_id)
        self.deviceModel.updateDownloadProgress(scan_id, percent_complete,
                                    None)
        self.time_remaining.update(scan_id, bytes_downloaded=chunk_downloaded)

    def copyfilesFinished(self):
        pass

    def fileRenamedAndMoved(self, move_succeeded: bool, rpd_file: RPDFile,
                            download_count: int, thumbnail: QPixmap):

        if not thumbnail.isNull():
            logging.debug("Updating GUI thumbnail for {} with unique "
                          "id {}".format(
                rpd_file.download_full_file_name, rpd_file.unique_id))
            self.thumbnailModel.thumbnailReceived(rpd_file, thumbnail)

        if rpd_file.status == DownloadStatus.downloaded_with_warning:
            self.logError(ErrorType.warning, rpd_file.error_title,
                           rpd_file.error_msg, rpd_file.error_extra_detail)

        if self.prefs.backup_images:
            scan_pid = rpd_file.scan_id
            unique_id = rpd_file.unique_id

            #TODO: implement backupimages

        self.fileDownloadFinished(move_succeeded, rpd_file)

    def updateSequences(self, stored_sequence_no: int, downloads_today: list):
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

    def fileRenamedAndMovedFinished(self):
        pass

    def updateFileDownloadDeviceProgress(self, scan_id: int, unique_id,
                                              file_type):
        """
        Increments the progress bar for an individual device

        Returns if the download is completed for that scan_pid
        It also returns the number of files remaining for the scan_pid, BUT
        this value is valid ONLY if the download is completed
        """

        files_downloaded = \
            self.download_tracker.get_download_count_for_file(unique_id)
        files_to_download = self.download_tracker.get_no_files_in_download(
            scan_id)
        file_types = self.download_tracker.get_file_types_present(scan_id)
        completed = files_downloaded == files_to_download
        if completed and (self.prefs.backup_images and
                              self.backup_devices.backup_possible(file_type)):
            completed = self.download_tracker.all_files_backed_up(unique_id,
                                                                  file_type)

        if completed:
            files_remaining = self.thumbnailModel.getNoFilesRemaining(scan_id)
        else:
            files_remaining = 0

        if completed and files_remaining:
            # e.g.: 3 of 205 photos and videos (202 remaining)
            progress_bar_text = _("%(number)s of %(total)s %(filetypes)s (%("
                                  "remaining)s remaining)") % {
                                  'number':  files_downloaded,
                                  'total': files_to_download,
                                  'filetypes': file_types,
                                  'remaining': files_remaining}
        else:
            # e.g.: 205 of 205 photos and videos
            progress_bar_text = _("%(number)s of %(total)s %(filetypes)s") % \
                                 {'number':  files_downloaded,
                                  'total': files_to_download,
                                  'filetypes': file_types}
        percent_complete = self.download_tracker.get_percent_complete(scan_id)
        self.deviceModel.updateDownloadProgress(scan_id=scan_id,
                                        percent_complete=percent_complete,
                                        progress_bar_text=progress_bar_text)

        percent_complete = self.download_tracker.get_overall_percent_complete()
        self.downloadProgressBar.setValue(round(percent_complete*100))
        if self.unity_progress:
            self.deskop_launcher.set_property('progress', percent_complete)
            self.deskop_launcher.set_property('progress_visible', True)

        return (completed, files_remaining)

    def fileDownloadFinished(self, succeeded: bool, rpd_file: RPDFile):
        """
        Called when a file has been downloaded i.e. copied, renamed,
        and backed up
        """
        scan_id = rpd_file.scan_id
        unique_id = rpd_file.unique_id
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

        completed, files_remaining = \
            self.updateFileDownloadDeviceProgress(scan_id, unique_id,
                                                       rpd_file.file_type)

        if self.downloadIsRunning():
            self.updateTimeRemaining()

        if completed:
            # Last file for this scan id has been downloaded, so clean temp
            # directory
            logging.debug("Purging temp directories")
            self.cleanTempDirsForScanId(scan_id)
            if self.prefs.move:
                logging.debug("Deleting downloaded source files")
                self.deleteSourceFiles(scan_id)
                self.download_tracker.clear_auto_delete(scan_id)
            self.active_downloads_by_scan_id.remove(scan_id)
            del self.time_remaining[scan_id]
            self.notifyDownloadedFromDevice(scan_id)
            if files_remaining == 0 and self.prefs.auto_unmount:
                self.unmount_volume(scan_id)

            if not self.downloadIsRunning():
                logging.debug("Download completed")
                self.enablePrefsAndRefresh(enabled=True)
                self.notifyDownloadComplete()
                self.downloadProgressBar.reset()
                if self.unity_progress:
                    self.deskop_launcher.set_property('progress_visible',
                                                      False)

                # Update prefs with stored sequence number and downloads today
                # values
                data = RenameAndMoveFileData(
                    message=RenameAndMoveStatus.download_completed)
                self.renamemq.send_message_to_worker(data)

                if ((self.prefs.auto_exit and self.download_tracker.no_errors_or_warnings())
                                                or self.prefs.auto_exit_force):
                    if not self.thumbnailModel.filesRemainToDownload():
                        self.quit()

                self.download_tracker.purge_all()
                # self.speed_label.set_label(" ")

                self.displayFreeSpaceAndBackups()

                self.setDownloadActionLabel(is_download=True)
                self.setDownloadActionSensitivity()

                self.job_code = ''
                self.download_start_time = None

    def updateTimeRemaining(self):
        update, download_speed = self.time_check.check_for_update()
        if update:
            # TODO implement label showing download speed
            # self.speedLabel.set_text(download_speed)

            time_remaining = self.time_remaining.time_remaining()
            if time_remaining:
                secs =  int(time_remaining)

                if secs == 0:
                    message = ""
                elif secs == 1:
                    message = _("About 1 second remaining")
                elif secs < 60:
                    message = _("About %i seconds remaining") % secs
                elif secs == 60:
                    message = _("About 1 minute remaining")
                else:
                    # Translators: in the text '%(minutes)i:%(seconds)02i',
                    # only the : should be translated, if needed.
                    # '%(minutes)i' and '%(seconds)02i' should not be
                    # modified or left out. They are used to format and
                    # display the amount
                    # of time the download has remainging, e.g. 'About 5:36
                    # minutes remaining'
                    message = _(
                        "About %(minutes)i:%(seconds)02i minutes remaining")\
                              % {
                              'minutes': secs / 60, 'seconds': secs % 60}

                self.statusBar().showMessage(message)

    def enablePrefsAndRefresh(self, enabled: bool):
        """
        Disable the user being to access the refresh command or change
        program preferences while a download is occurring.

        :param enabled: if True, then the user is able to activate the
        preferences and refresh commands.

        """
        self.refreshAct.setEnabled(enabled)
        self.preferencesAct.setEnabled(enabled)

    def unmount_volume(self, scan_id: int):
        """
        Cameras are already unmounted, so no need to unmount them!
        :param scan_id: the scan id of the device to be umounted
        """
        device = self.devices[scan_id]
        """ :type : Device"""

        if device.device_type == DeviceType.volume:
            #TODO implement
            if self.gvfsControlsMounts:
                #self.gvolumeMonitor.
                pass
            else:
                #self.udisks2Monitor.
                pass


    def deleteSourceFiles(self, scan_id: int):
        """
        Delete files from download device at completion of download
        """
        #TODO delete from cameras and from other devics
        # should assign this to a process or a thread, and delete then
        to_delete = self.download_tracker.get_files_to_auto_delete(scan_id)

    def notifyDownloadedFromDevice(self, scan_id: int):
        """
        Display a system notification to the user using libnotify
        that the files have been downloaded from the device
        :param scan_id: identifies which device
        """
        device = self.devices[scan_id]

        if device.device_type == DeviceType.path:
            notification_name = _('Rapid Photo Downloader')
        else:
            notification_name  = device.name()

        if device.icon_name is not None:
            icon = device.icon_name
        else:
            icon = None

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
        message = _("%(noFiles)s %(filetypes)s downloaded") % \
                  {'noFiles': no_files_downloaded, 'filetypes': file_types}

        if no_files_failed:
            message += "\n" + _(
                "%(noFiles)s %(filetypes)s failed to download") % {
                              'noFiles': no_files_failed,
                              'filetypes': file_types_failed}

        if no_warnings:
            message = "%s\n%s " % (message, no_warnings) + _("warnings")

        message_shown = False
        if self.have_libnotify:
            if icon is not None:
                # summary, body, icon (icon theme icon name or filename)
                n = Notify.Notification.new(notification_name, message, icon)
            else:
                n = Notify.Notification.new(notification_name, message)
            try:
                message_shown =  n.show()
            except:
                logging.error("Unable to display message using notification "
                          "system")
            if not message_shown:
                logging.info("{}: {}".format(notification_name, message))


    def notifyDownloadComplete(self):
        if self.display_summary_notification:
            message = _("All downloads complete")

            # photo downloads
            photo_downloads = self.download_tracker.total_photos_downloaded
            if photo_downloads:
                filetype = file_types_by_number(photo_downloads, 0)
                message += "\n" + _("%(number)s %(numberdownloaded)s") % \
                                  {'number': photo_downloads,
                                   'numberdownloaded': _(
                                       "%(filetype)s downloaded") % \
                                                       {'filetype': filetype}}

            # photo failures
            photo_failures = self.download_tracker.total_photo_failures
            if photo_failures:
                filetype = file_types_by_number(photo_failures, 0)
                message += "\n" + _("%(number)s %(numberdownloaded)s") % \
                                  {'number': photo_failures,
                                   'numberdownloaded': _(
                                       "%(filetype)s failed to download") % \
                                                       {'filetype': filetype}}

            # video downloads
            video_downloads = self.download_tracker.total_videos_downloaded
            if video_downloads:
                filetype = file_types_by_number(0, video_downloads)
                message += "\n" + _("%(number)s %(numberdownloaded)s") % \
                                  {'number': video_downloads,
                                   'numberdownloaded': _(
                                       "%(filetype)s downloaded") % \
                                                       {'filetype': filetype}}

            # video failures
            video_failures = self.download_tracker.total_video_failures
            if video_failures:
                filetype = file_types_by_number(0, video_failures)
                message += "\n" + _("%(number)s %(numberdownloaded)s") % \
                                  {'number': video_failures,
                                   'numberdownloaded': _(
                                       "%(filetype)s failed to download") % \
                                                       {'filetype': filetype}}

            # warnings
            warnings = self.download_tracker.total_warnings
            if warnings:
                message += "\n" + _("%(number)s %(numberdownloaded)s") % \
                            {'number': warnings,
                            'numberdownloaded': _("warnings")}

            message_shown = False
            if self.have_libnotify:
                n = Notify.Notification.new(_('Rapid Photo Downloader'),
                                message,
                                self.program_svg)
                try:
                    message_shown = n.show()
                except:
                    logging.error("Unable to display message using "
                                "notification system")
            if not message_shown:
                logging.info(message)

            # don't show summary again unless needed
            self.display_summary_notification = False

    def invalidDownloadFolders(self, downloading: DownloadTypes):
        """
        Checks validity of download folders based on the file types the
        user is attempting to download.

        :rtype List(str)
        :return list of the invalid directories, if any, or empty list .
        """
        invalid_dirs = []
        if downloading.photos:
            if not self.isValidDownloadDir(self.prefs.photo_download_folder,
                                                        is_photo_dir=True):
                invalid_dirs.append(self.prefs.photo_download_folder)
        if downloading.videos:
            if not self.isValidDownloadDir(self.prefs.video_download_folder,
                                                        is_photo_dir=False):
                invalid_dirs.append(self.prefs.video_download_folder)
        return invalid_dirs

    def isValidDownloadDir(self, path, is_photo_dir: bool,
                           show_error_in_log=False) -> bool:
        """
        Checks directory following conditions:
        Does it exist? Is it writable?

        :param show_error_in_log: if  True, then display warning in log
        window
        :type show_error_in_log: bool
        :param is_photo_dir: if true the download directory is for
        photos, else for videos
        :return True if directory is valid, else False
        """
        valid = False
        if is_photo_dir:
            download_folder_type = _("Photo")
        else:
            download_folder_type = _("Video")

        if not os.path.isdir(path):
            logging.error("%s download folder does not exist: %s",
                         download_folder_type, path)
            if show_error_in_log:
                severity = ErrorType.warning
                problem = _("%(file_type)s download folder is invalid") % {
                            'file_type': download_folder_type}
                details = _("Folder: %s") % path
                self.log_error(severity, problem, details)
        elif not os.access(path, os.W_OK):
            logging.error("%s is not writable", path)
            if show_error_in_log:
                severity = ErrorType.warning
                problem = _("%(file_type)s download folder is not writable") \
                            % {'file_type': download_folder_type}
                details = _("Folder: %s") % path
                self.log_error(severity, problem, details)
        else:
            valid = True
        return valid

    def notifyPrefsAreInvalid(self, details):
        title = _("Program preferences are invalid")
        logging.critical(title)
        self.log_error(severity=ErrorType.critical_error, problem=title,
                       details=details)

    def logError(self, severity, problem, details, extra_detail=None):
        """
        Display error and warning messages to user in log window
        """
        #TODO implement error log window
        pass
        # self.error_log.add_message(severity, problem, details, extra_detail)

    def backupDestinationsMissing(self, downloading: DownloadTypes) -> \
                                  BackupMissing:
        """
        Checks if there are backup destinations matching the files
        going to be downloaded
        :param downloading: the types of file that will be downloaded
        :return: None if no problems, or BackupMissing
        """
        backup_missing = BackupMissing(False, False)
        if self.prefs.backup_images and \
                self.prefs.backup_device_autodetection:
            if downloading.photos and not self.backupPossible(
                    FileType.photo):
                backup_missing.photo = True
            if downloading.videos and not self.backupPossible(
                    FileType.video):
                backup_missing.video = True
            if not (backup_missing.photo and backup_missing.video):
                return None
            else:
                return backup_missing
        return None

    def backupPossible(self, file_type: FileType) -> bool:
        #TODO implement backup device monitoring
        if file_type == FileType.photo:
            return True
            # return self.no_photo_backup_devices > 0
        assert file_type == FileType.video
        return True
            # return self.no_video_backup_devices > 0

    def scanMessageReceived(self, rpd_file: RPDFile):
        # Update scan running totals
        scan_id = rpd_file.scan_id
        device = self.devices[scan_id]
        device.file_type_counter[rpd_file.file_type] += 1
        device.file_size_sum += rpd_file.size
        size = self.formatSizeForUser(device.file_size_sum)
        text = device.file_type_counter.running_file_count()
        self.deviceModel.updateDeviceScan(scan_id, text, size)

        self.thumbnailModel.addFile(rpd_file, generate_thumbnail=not
                                    self.auto_start_is_on)

    def scanFinished(self, scan_id: int):
        device = self.devices[scan_id]
        results_summary, file_types_present  = \
            device.file_type_counter.summarize_file_count()
        self.download_tracker.set_file_types_present(scan_id,
                                                     file_types_present)
        self.deviceModel.updateDeviceScan(scan_id, results_summary,
                                          scan_completed=True)
        self.setDownloadActionSensitivity()

        if (not self.auto_start_is_on and  self.prefs.generate_thumbnails):
            # Generate thumbnails for finished scan
            self.thumbnailModel.generateThumbnails(scan_id, self.devices[
                        scan_id], self.prefs.thumbnail_quality_lower)
        elif self.auto_start_is_on:
            #TODO implement get job code
            if False: #self.need_job_code_for_naming and not self.job_code:
                pass
                #self.get_job_code()
            else:
                self.startDownload(scan_id=scan_id)

    def closeEvent(self, event):
        if self.application_state == ApplicationState.normal:
            self.application_state = ApplicationState.exiting
            self.scanmq.stop()
            self.thumbnailModel.thumbnailmq.stop()
            self.copyfilesmq.stop()

            if self.downloadIsRunning():
                logging.debug("Exiting while download is running. Cleaning "
                              "up...")
                # Update prefs with stored sequence number and downloads today
                # values
                data = RenameAndMoveFileData(
                    message=RenameAndMoveStatus.download_completed)
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
        self.renamemq.stop()
        self.renameThread.quit()
        if not self.renameThread.wait(500):
            self.renamemq.forcefully_terminate()
        self.scanThread.quit()
        if not self.scanThread.wait(2000):
            self.scanmq.forcefully_terminate()
        self.thumbnailModel.thumbnailThread.quit()
        if not self.thumbnailModel.thumbnailThread.wait(1000):
            self.thumbnailModel.thumbnailmq.forcefully_terminate()
        self.copyfilesThread.quit()
        if not self.copyfilesThread.wait(1000):
            self.copyfilesmq.forcefully_terminate()
        if not self.gvfsControlsMounts:
            self.udisks2MonitorThread.quit()
            self.udisks2MonitorThread.wait()
            self.cameraHotplugThread.quit()
            self.cameraHotplugThread.wait()

        self.cleanAllTempDirs()
        self.devices.delete_cache_dirs()
        tc = ThumbnailCache()
        tc.cleanup_cache()
        Notify.uninit()

        event.accept()


    def getDeviceIcon(self, device: Device) -> QIcon:
        """
        Return Qt icon for the device
        :param device: the device from which to get the icon
        :return: QIcon for the device, or None if it's not possible to
         get the icon (which should be extremely rare!)
        """
        if device.device_type == DeviceType.volume:
            icon = None
            if device.icon_name is not None:
                icon = QIcon.fromTheme(device.icon_name)
            if icon is not None:
                return icon
            else:
                return QFileIconProvider().icon(QFileIconProvider.Drive)
        elif device.device_type == DeviceType.path:
            return QIcon.fromTheme(device.icon_name)
        else:
            assert device.device_type == DeviceType.camera
            if device.icon_name is not None:
                return QIcon.fromTheme(device.icon_name)
            else:
                return None

    def getIconsAndEjectableForMount(self, mount: QStorageInfo):
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


    def addToDeviceDisplay(self, device: Device, scan_id: int):
        deviceIcon = self.getDeviceIcon(device)
        if device.can_eject:
            ejectIcon = QIcon.fromTheme('media-eject')
        else:
            ejectIcon = None
        self.deviceModel.addDevice(scan_id, deviceIcon, device.name(),
                                   ejectIcon)
        self.deviceView.resizeColumns()
        self.deviceView.resizeRowsToContents()
        self.resizeDeviceView()

    def resizeDeviceView(self):
        """
        Sets the maximum height for the device view table to match the
        number of rows. which has the happy side effect of moving the
        splitter.
        """
        assert len(self.devices) == self.deviceModel.rowCount()
        if len(self.devices):
            self.deviceView.setMaximumHeight(len(self.devices) *
                                             (self.deviceView.rowHeight(0)+1))
        else:
            self.deviceView.setMaximumHeight(20)


    def cameraAdded(self):
        if not self.prefs.device_autodetection:
            logging.debug("Ignoring camera as device auto detection is off")
        else:
            logging.debug("Assuming camera will not be mounted: "
                          "immediately proceeding with scan")
        self.searchForCameras()

    def cameraRemoved(self):
        """
        Handle the possible removal of a camera by comparing the
        cameras the OS knows about compared to the cameras we are
        tracking. Remove tracked cameras if they are not on the OS.

        We need this brute force method because I don't know if it's
        possible to query GIO or udev to return the info needed by
        libgphoto2
        """
        sc = self.gp_context.camera_autodetect()
        system_cameras = [(model, port) for model, port in sc if not
                          port.startswith('disk:')]
        kc = self.devices.cameras.items()
        known_cameras = [(model, port) for port, model in kc]
        removed_cameras = set(known_cameras) - set(system_cameras)
        #TODO handle situation when this is called twice, with dual  memory
        # cards
        for model, port in removed_cameras:
            scan_id = self.devices.scan_id_from_camera_model_port(model, port)
            self.removeDevice(scan_id)

        if removed_cameras:
            self.setDownloadActionSensitivity()

    def noGVFSAutoMount(self):
        """
        In Gnome like environment we rely on Gnome automatically
        mounting cameras and devices with file systems. But sometimes
        it will not automatically mount them, for whatever reason.
        Try to handle those cases.
        """
        #TODO Implement noGVFSAutoMount()
        print("Implement noGVFSAutoMount()")

    def cameraMounted(self):
        if have_gio:
            self.searchForCameras()

    def unmountCamera(self, model, port):
        if self.gvfsControlsMounts:
            self.cameras_to_unmount[port] = model
            if self.gvolumeMonitor.unmountCamera(model, port):
                return True
            else:
                del self.cameras_to_unmount[port]
        return False

    def cameraUnmounted(self, result, model, port):
        assert self.cameras_to_unmount[port] == model
        del self.cameras_to_unmount[port]
        if result:
            self.startCameraScan(model, port)
        else:
            logging.debug("Not scanning %s because it could not be "
                          "unmounted", model)

    def searchForCameras(self):
        if self.prefs.device_autodetection:
            cameras = self.gp_context.camera_autodetect()
            for model, port in cameras:
                if port in self.cameras_to_unmount:
                    assert self.cameras_to_unmount[port] == model
                    logging.debug("Already unmounting %s", model)
                elif self.devices.known_camera(model, port):
                    logging.debug("Camera %s is known", model)
                elif model in self.prefs.camera_blacklist:
                    logging.debug("Ignoring blacklisted camera %s", model)
                elif not port.startswith('disk:'):
                    logging.debug("Detected %s on port %s", model, port)
                    # libgphoto2 cannot access a camera when it is mounted
                    # by another process, like Gnome's GVFS or any other
                    # system. Before attempting to scan the camera, check
                    # to see if it's mounted and if so, unmount it.
                    # Unmounting is asynchronous.
                    if not self.unmountCamera(model, port):
                        self.startCameraScan(model, port)

    def startCameraScan(self, model: str, port: str):
        device = Device()
        device.set_download_from_camera(model, port)
        self.startDeviceScan(device)

    def startDeviceScan(self, device: Device):
        scan_id = self.devices.add_device(device)
        self.addToDeviceDisplay(device, scan_id)
        scan_preferences = ScanPreferences(self.prefs.ignored_paths)
        scan_arguments = ScanArguments(scan_preferences, device)
        self.scanmq.start_worker(scan_id, scan_arguments)
        self.setDownloadActionSensitivity()


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
            path = mount.rootPath()
            if (path in self.prefs.path_blacklist and
                    self.scanEvenIfNoDCIM()):
                logging.info("blacklisted device %s ignored",
                             mount.displayName())
                return False
            else:
                return True
        return False

    def shouldScanMountPath(self, path: str) -> bool:
        if self.prefs.device_autodetection:
            if (self.prefs.device_without_dcim_autodetection or
                    has_non_empty_dcim_folder(path)):
                return True
        return False

    def prepareNonCameraDeviceScan(self, device: Device):
        if not self.devices.known_device(device):
            if (self.scanEvenIfNoDCIM() and
                    not device.path in self.prefs.path_whitelist):
                # prompt user to see if device should be used or not
                pass
                #self.get_use_device(device)
            else:
                self.startDeviceScan(device)
                # if mount is not None:
                #     self.mounts_by_path[path] = scan_pid

    def partitionMounted(self, path: str, iconNames, canEject: bool):
        """
        Setup devices from which to download from and backup to, and
        if relevant start scanning them

        :param path: the path of the mounted partition
        :param iconNames: a list of names of icons used in themed icons
        associated with this partition
        :param canEject: whether the partition can be ejected or not
        :type iconNames: List[str]
        """
        assert path in mountPaths()

        if self.monitorPartitionChanges():
            mount = QStorageInfo(path)
            if self.partitionValid(mount):
                backup_file_type = self.isBackupPath(path)

                if backup_file_type is not None:
                    if path not in self.backup_devices:
                        device = BackupDevice(mount=mount,
                                              backup_type=backup_file_type)
                        self.backup_devices[path] = device
                        #TODO add backup device to manager
                    #     name = self._backup_device_name(path)
                    #     self.backup_manager.add_device(path, name, backup_file_type)
                        self.download_tracker.set_no_backup_devices(
                            self.backup_devices.no_photo_backup_devices,
                            self.backup_devices.no_video_backup_devices)
                        self.displayFreeSpaceAndBackups()

                elif self.shouldScanMountPath(path):
                    self.auto_start_is_on = \
                        self.prefs.auto_download_upon_device_insertion
                    device = Device()
                    device.set_download_from_volume(path, mount.displayName(),
                                                    iconNames, canEject)
                    self.prepareNonCameraDeviceScan(device)

    def partitionUmounted(self, path: str):
        """
        Handle the unmounting of partitions by the system / user
        :param path: the path of the partition just unmounted
        """
        if not path:
            return

        if self.devices.known_path(path):
            # four scenarios -
            # the mount is being scanned
            # the mount has been scanned but downloading has not yet started
            # files are being downloaded from mount
            # files have finished downloading from mount
            scan_id = self.devices.scan_id_from_path(path)
            self.removeDevice(scan_id)

        elif path in self.backup_devices:
            del self.backup_devices[path]
            self.displayFreeSpaceAndBackups()
             #TODO remove backup device from manager
            # self.backup_manager.remove_device(path)
            self.download_tracker.set_no_backup_devices(
                self.backup_devices.no_photo_backup_devices,
                self.backup_devices.no_video_backup_devices)

        self.setDownloadActionSensitivity()


    def removeDevice(self, scan_id):
        assert scan_id is not None
        if scan_id in self.devices:
            self.thumbnailModel.clearAll(scan_id=scan_id,
                                         keep_downloaded_files=True)
            self.deviceModel.removeDevice(scan_id)
            del self.devices[scan_id]
            self.resizeDeviceView()

    def setupNonCameraDevices(self, on_startup: bool,
                              on_preference_change: bool,
                              block_auto_start: bool):
        """
        Setup devices from which to download from and backup to, and
        if relevant start scanning them

        Removes any image media that are currently not downloaded,
        or finished downloading

        :param on_startup: should be True if the program is still
        starting i.e. this is being called from the program's
        initialization.
        :param on_preference_change: should be True if this is being
        called as the result of a program preference being changed
        :param block_auto_start: should be True if automation options to
        automatically start a download should be ignored
        """

        self.clearNonRunningDownloads()
        if not self.prefs.device_autodetection:
             if not self.confirmManualDownloadLocation():
                return

        mounts = []
        self.backup_devices = BackupDeviceCollection()

        if self.monitorPartitionChanges():
            # either using automatically detected backup devices
            # or download devices
            for mount in self.validMounts.mountedValidMountPoints():
                if self.partitionValid(mount):
                    path = mount.rootPath()
                    logging.debug("Detected %s", mount.displayName())
                    backup_type = self.isBackupPath(path)
                    if backup_type is not None:
                        self.backup_devices[path] = BackupDevice(mount=mount,
                                                     backup_type=backup_type)
                    elif self.shouldScanMountPath(path):
                        logging.debug("Appending %s", mount.displayName())
                        mounts.append(mount)
                    else:
                        logging.debug("Ignoring %s", mount.displayName())

        if self.prefs.backup_images:
            if not self.prefs.backup_device_autodetection:
                self.setupManualBackup()
                # TODO add backup devices to backup manager MQ
        #     self._add_backup_devices()
        #

        self.download_tracker.set_no_backup_devices(
            self.backup_devices.no_photo_backup_devices,
            self.backup_devices.no_video_backup_devices)

        # Display amount of free space in a status bar message
        self.displayFreeSpaceAndBackups()

        #TODO hey need to think about this now that we have cameras too
        if block_auto_start:
            self.auto_start_is_on = False
        else:
            self.auto_start_is_on = ((not on_preference_change) and
                    ((self.prefs.auto_download_at_startup and
                      on_startup) or
                      (self.prefs.auto_download_upon_device_insertion and
                       not on_startup)))

        if not self.prefs.device_autodetection:
            # user manually specified the path from which to download
            path = self.prefs.device_location
            if path:
                logging.debug("Using manually specified path %s", path)
                if os.path.isdir(path) and os.access(path, os.R_OK):
                    device = Device()
                    device.set_download_from_path(path)
                    self.startDeviceScan(device)
                else:
                    logging.error("Download path is invalid: %s", path)
            else:
                logging.error("Download path is not specified")

        else:
            for mount in mounts:
                icon_names, can_eject = self.getIconsAndEjectableForMount(
                                             mount)
                device = Device()
                device.set_download_from_volume(mount.rootPath(),
                                              mount.displayName(),
                                              icon_names,
                                              can_eject)
                self.prepareNonCameraDeviceScan(device)
        # if not mounts:
        #     self.set_download_action_sensitivity()

    def setupManualBackup(self):
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

        if backup_photo_location != backup_video_location:
            backup_photo_device =  BackupDevice(mount=None,
                                backup_type=BackupLocationType.photos)
            backup_video_device = BackupDevice(mount=None,
                                backup_type=BackupLocationType.videos)
            self.backup_devices[backup_photo_location] = backup_photo_device
            self.backup_devices[backup_video_location] = backup_video_device

            logging.info("Backing up photos to %s", backup_photo_location)
            logging.info("Backing up videos to %s", backup_video_location)
        else:
            # videos and photos are being backed up to the same location
            backup_device = BackupDevice(mount=None,
                     backup_type=BackupLocationType.photos_and_videos)
            self.backup_devices[backup_photo_location] = backup_device

            logging.info("Backing up photos and videos to %s",
                         backup_photo_location)

    def isBackupPath(self, path: str) -> BackupLocationType:
        """
        Checks to see if backups are enabled and path represents a
        valid backup location. It must be writeable.

        Checks against user preferences.

        :return The type of file that should be backed up to the path,
        else if nothing should be, None
        """
        if self.prefs.backup_images:
            if self.prefs.backup_device_autodetection:
                # Determine if the auto-detected backup device is
                # to be used to backup only photos, or videos, or both.
                # Use the presence of a corresponding directory to
                # determine this.
                # The directory must be writable.
                photo_path = os.path.join(path,
                                          self.prefs.photo_backup_identifier)
                p_backup = os.path.isdir(photo_path) and os.access(
                    photo_path, os.W_OK)
                video_path = os.path.join(path,
                                          self.prefs.video_backup_identifier)
                v_backup = os.path.isdir(video_path) and os.access(
                    video_path, os.W_OK)
                if p_backup and v_backup:
                    logging.info("Photos and videos will be backed up to "
                                 "%s", path)
                    return BackupLocationType.photos_and_videos
                elif p_backup:
                    logging.info("Photos will be backed up to %s", path)
                    return BackupLocationType.photos
                elif v_backup:
                    logging.info("Videos will be backed up to %s", path)
                    return BackupLocationType.videos
            elif path == self.prefs.backup_photo_location:
                # user manually specified the path
                if os.access(path, os.W_OK):
                    return BackupLocationType.photos
            elif path == self.prefs.backup_video_location:
                # user manually specified the path
                if os.access(path, os.W_OK):
                    return BackupLocationType.videos
            return None

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

    def confirmManualDownloadLocation(self) -> bool:
        """
        Queries the user to ask if they really want to download from locations
        that could take a very long time to scan. They can choose yes or no.

        Returns True if yes or there was no need to ask the user, False if the
        user said no.
        """
        #TODO implement
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

    def formatSizeForUser(self, size: int, zero_string='',
                             with_decimals=True,
                             kb_only=False) -> str:
        """
        Format an int containing the number of bytes into a string
        suitable for displaying to the user.

        source: https://develop.participatoryculture.org/trac/democracy/browser/trunk/tv/portable/util.py?rev=3993

        :param size: size in bytes
        :param zero_string: string to use if size == 0
        :param kb_only: display in KB or B
        """
        if size > (1 << 40) and not kb_only:
            value = (size / (1024.0 * 1024.0 * 1024.0 * 1024.0))
            if with_decimals:
                format = "%1.1fTB"
            else:
                format = "%dTB"
        elif size > (1 << 30) and not kb_only:
            value = (size / (1024.0 * 1024.0 * 1024.0))
            if with_decimals:
                format = "%1.1fGB"
            else:
                format = "%dGB"
        elif size > (1 << 20) and not kb_only:
            value = (size / (1024.0 * 1024.0))
            if with_decimals:
                format = "%1.1fMB"
            else:
                format = "%dMB"
        elif size > (1 << 10):
            value = (size / 1024.0)
            if with_decimals:
                format = "%1.1fKB"
            else:
                format = "%dKB"
        elif size > 1:
            value = size
            if with_decimals:
                format = "%1.1fB"
            else:
                format = "%dB"
        else:
            return zero_string
        return format % value

    def displayFreeSpaceAndBackups(self):
        """
        Displays on status bar the amount of space free on the
        filesystem the files will be downloaded to.

        Also displays backup volumes / path being used.
        """
        photo_dir = self.isValidDownloadDir(
            path=self.prefs.photo_download_folder,
            is_photo_dir=True,
            show_error_in_log=True)
        video_dir = self.isValidDownloadDir(
            path=self.prefs.video_download_folder,
            is_photo_dir=False,
            show_error_in_log=True)
        if photo_dir and video_dir:
            same_fs = same_file_system(self.prefs.photo_download_folder,
                                       self.prefs.video_download_folder)
        else:
            same_fs = False

        dirs = []
        if photo_dir:
            dirs.append(self.prefs.photo_download_folder)
        if video_dir and not same_fs:
            dirs.append(self.prefs.video_download_folder)

        if len(dirs) == 1:
            free = self.formatSizeForUser(size=shutil.disk_usage(dirs[0]).free)
            # Free space available on the filesystem for downloading to
            # Displayed in status bar message on main window
            # e.g. 14.7GB free
            if self.prefs.backup_images:
                msg = _("%(free)s free.") % {'free': free}
            else:
                msg = _("%(free)s free") % {'free': free}
        elif len(dirs) == 2:
            free1, free2 = (self.formatSizeForUser(size=shutil.disk_usage(
                path).free) for path in dirs)
            # Free space available on the filesystem for downloading to
            # Displayed in status bar message on main window
            # e.g. Free space: 21.3GB (photos); 14.7GB (videos).
            msg = _('Free space: %(photos)s (photos); %(videos)s (videos).') \
                  % {'photos': free1, 'videos': free2}
        else:
            msg = ''

        if self.prefs.backup_images:
            if not self.prefs.backup_device_autodetection:
                if self.prefs.photo_backup_location ==  \
                        self.prefs.backup_video_location:
                    # user manually specified the same location for photos
                    # and video backups
                    msg2 = _('Backing up photos and videos to %(path)s') % {
                        'path':self.prefs.photo_backup_location}
                else:
                    # user manually specified different locations for photo
                    # and video backups
                    msg2 = _('Backing up photos to %(path)s and videos to %('
                             'path2)s')  % {
                             'path': self.prefs.photo_backup_location,
                             'path2': self.prefs.backup_video_location}
            else:
                msg2 = self.displayBackupMounts()

            if msg:
                msg = _("%(freespace)s %(backuppaths)s.") % {'freespace':
                                                  msg, 'backuppaths': msg2}
            else:
                msg = msg2

        msg = msg.rstrip()

        self.statusBar().showMessage(msg)

    def displayBackupMounts(self) -> str:
        """
        Create a message to be displayed to the user showing which
        backup mounts will be used
        :return the string to be displayed
        """
        message =  ''

        backup_device_names = [self.backup_devices.name(path) for path in
                          self.backup_devices]
        message = makeInternationalizedList(backup_device_names)

        if len(backup_device_names) > 1:
            message = _("Using backup devices %(devices)s") % dict(
                devices=message)
        elif len(backup_device_names) == 1:
            message = _("Using backup device %(device)s")  % dict(
                device=message)
        else:
            message = _("No backup devices detected")
        return message

if __name__ == "__main__":

    app = QApplication(sys.argv)
    app.setOrganizationName("Rapid Photo Downloader")
    app.setOrganizationDomain("damonlynch.net")
    app.setApplicationName("Rapid Photo Downloader")
    app.setWindowIcon(QtGui.QIcon(':/rapid-photo-downloader.svg'))

    rw = RapidWindow()
    rw.show()

    sys.exit(app.exec_())
