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
from collections import namedtuple

from gettext import gettext as _

import zmq
import gphoto2 as gp

from PyQt5 import QtCore, QtWidgets, QtGui

from PyQt5.QtCore import (QThread, Qt, QStorageInfo, QSettings, QPoint,
                          QSize, QFileInfo, QTimer)
from PyQt5.QtGui import (QIcon, QPixmap, QImage)
from PyQt5.QtWidgets import (QAction, QApplication, QFileDialog, QLabel,
        QMainWindow, QMenu, QMessageBox, QScrollArea, QSizePolicy,
        QPushButton, QFrame, QWidget, QDialogButtonBox,
        QProgressBar, QSplitter, QFileIconProvider, QHBoxLayout, QVBoxLayout)

# import dbus
# from dbus.mainloop.pyqt5 import DBusQtMainLoop


from storage import (ValidMounts, CameraHotplug, UDisks2Monitor,
                     GVolumeMonitor, have_gio, has_non_empty_dcim_folder,
                     mountPaths, get_desktop_environment,
                     gvfs_controls_mounts, get_program_cache_directory)
from interprocess import (PublishPullPipelineManager, ScanArguments,
                          CopyFilesArguments, CopyFilesResults,
                          PushPullDaemonManager)
from devices import (Device, DeviceCollection, BackupDevice,
                     BackupDeviceCollection)
from preferences import (Preferences, ScanPreferences)
from constants import (BackupLocationType, DeviceType, ErrorType,
                       FileType)
from thumbnaildisplay import (ThumbnailView, ThumbnailTableModel,
    ThumbnailDelegate, DownloadTypes, DownloadStats)
from devicedisplay import (DeviceTableModel, DeviceView, DeviceDelegate)
from utilities import (same_file_system, makeInternationalizedList, CacheDirs)
from rpdfile import RPDFile
import downloadtracker

logging_level = logging.DEBUG
logging.basicConfig(format='%(asctime)s %(message)s', level=logging_level)


BackupMissing = namedtuple('BackupMissing', ['photo', 'video'])

class RenameMoveFileManager(PushPullDaemonManager):
    def __init__(self, context: zmq.Context):
        super(RenameMoveFileManager, self).__init__(context)
        self._process_name = 'Rename and Move File Manager'
        self._process_to_run = 'renameandmovefile.py'

class ScanManager(PublishPullPipelineManager):
    message = QtCore.pyqtSignal(RPDFile)
    def __init__(self, context: zmq.Context):
        super(ScanManager, self).__init__(context)
        self._process_name = 'Scan Manager'
        self._process_to_run = 'scan.py'

class CopyFilesManager(PublishPullPipelineManager):
    message = QtCore.pyqtSignal(bool, RPDFile, int)
    thumbnail = QtCore.pyqtSignal(RPDFile, QPixmap)
    tempDirs = QtCore.pyqtSignal(int, str,str)
    bytesDownloaded = QtCore.pyqtSignal(int, int, int)
    def __init__(self, context: zmq.Context):
        super(CopyFilesManager, self).__init__(context)
        self._process_name = 'Copy Files Manager'
        self._process_to_run = 'copyfiles.py'

    def process_sink_data(self):
        data = pickle.loads(self.content)
        """ :type : CopyFilesResults"""
        if data.total_downloaded is not None:
            assert data.scan_id is not None
            assert data.chunk_downloaded is not None
            self.bytesDownloaded.emit(data.scan_id, data.total_downloaded,
                                      data.chunk_downloaded)

        elif data.copy_succeeded is not None:
            assert data.rpd_file is not None
            assert data.download_count is not None
            self.message.emit(data.copy_succeeded, data.rpd_file,
                              data.download_count)
            if data.png_data is not None:
                thumbnail = QImage.fromData(data.png_data)
                thumbnail = QPixmap.fromImage(thumbnail)
                self.thumbnail.emit(data.rpd_file, thumbnail)

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

        self.context = zmq.Context()

        self.setWindowTitle(_("Rapid Photo Downloader"))
        self.readWindowSettings()
        self.prefs = Preferences()
        self.setupWindow()

        self.prefs.photo_download_folder = '/data/Photos/Test'
        self.prefs.video_download_folder = '/data/Photos/Test'
        self.prefs.auto_download_at_startup = False
        self.prefs.verify_file = True

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
        # Initalize use of libgphoto2
        self.gp_context = gp.Context()

        self.validMounts = ValidMounts(
            onlyExternalMounts=self.prefs.only_external_mounts)

        logging.debug("Desktop environment: %s",
                      get_desktop_environment())
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
        self.camerasToUnmount = {}

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
        self.copyfilesmq.thumbnail.connect(
            self.thumbnailModel.thumbnailReceived)
        self.copyfilesmq.bytesDownloaded.connect(self.copyfilesBytesDownloaded)
        self.copyfilesmq.tempDirs.connect(self.tempDirsReceivedFromCopyFiles)
        self.copyfilesmq.workerFinished.connect(self.copyfilesFinished)

        QTimer.singleShot(0, self.copyfilesThread.start)

        self.setDownloadActionSensitivity()
        self.searchForCameras()
        self.setupNonCameraDevices(on_startup=True, on_preference_change=False,
                                   block_auto_start=False)
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

            # disable refresh and preferences change while download is occurring
            # self.enable_prefs_and_refresh(enabled=False)

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

            self.setDownloadActionLabel(is_download = False)


    def downloadFiles(self, files, scan_id: int, download_stats: \
                      DownloadStats, generate_thumbnails: bool):
        """

        :param files: list of the files to download
        :param scan_id: the device from which to download the files
        :param download_stats: count of files and their size
        :param generate_thumbnails: whether thumbnails must be
        generated in the copy files process.
        """

        if download_stats.photos > 0:
            photo_download_folder = self.prefs.photo_download_folder
        else:
            photo_download_folder = None

        if download_stats.videos > 0:
            video_download_folder = self.prefs.video_download_folder
        else:
            video_download_folder = None

        self.download_tracker.init_stats(scan_id=scan_id,
                                photo_size_in_bytes=download_stats.photos_size,
                                video_size_in_bytes=download_stats.videos_size,
                                no_photos_to_download=download_stats.photos,
                                no_videos_to_download=download_stats.videos)


        download_size = download_stats.photos_size + download_stats.videos_size

        if self.prefs.backup_images:
            download_size += ((self.backup_devices.no_photo_backup_devices *
                               download_stats.photos_size) + (
                               self.backup_devices.no_video_backup_devices *
                               download_stats.videos_size))

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

        self.copyfilesmq.add_worker(scan_id, copyfiles_args)

    def tempDirsReceivedFromCopyFiles(self, scan_id: int, photo_temp_dir: str,
                                      video_temp_dir: str):
        self.temp_dirs_by_scan_id[scan_id] = list(filter(None,[photo_temp_dir,
                                                  video_temp_dir]))

    def cleanAllTempDirs(self):
        """
        Deletes temporary files and folders used in all downloads
        """
        for scan_id in self.temp_dirs_by_scan_id:
            self.cleanTempDirsForScanId(scan_id)
        self.temp_dirs_by_scan_id = {}

    def cleanTempDirsForScanId(self, scan_id: int):
        """
        Deletes temporary files and folders used in download
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
        del self.temp_dirs_by_scan_id[scan_id]

    def copyfilesDownloaded(self, download_succeeded: bool,
                                      rpd_file: RPDFile, download_count: int):
        print(download_count)

    # def copyfilesThumbnail(self, rpd_file: RPDFile, thumbnail: QPixmap):
    #     self.thumbnailModel.

    def copyfilesBytesDownloaded(self, scan_id: int, total_downloaded: int,
                                 chunk_downloaded: int):
        self.download_tracker.set_total_bytes_copied(scan_id,
                                                     total_downloaded)
        self.time_check.increment(bytes_downloaded=chunk_downloaded)
        percent_complete = self.download_tracker.get_percent_complete(scan_id)
        self.deviceModel.updateDownloadProgress(scan_id, percent_complete,
                                    None, None)
        self.time_remaining.update(scan_id, bytes_downloaded=chunk_downloaded)

    def copyfilesFinished(self):
        pass

    def fileRenamedAndMoved(self):
        pass

    def fileRenamedAndMovedFinished(self):
        pass


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

    def log_error(self, severity, problem, details, extra_detail=None):
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
        text = device.file_type_counter.summarize_file_count()[0]
        self.deviceModel.updateDeviceScan(scan_id, text, scan_completed=True)
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
        self.writeWindowSettings()
        self.renamemq.stop()
        self.scanmq.stop()
        self.thumbnailModel.thumbnailmq.stop()
        self.copyfilesmq.stop()
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

        cache_dir = get_program_cache_directory()
        # Out of an abundance of caution, under no circumstance try the
        # dangerous rmtree command unless certain that the folder is safely
        # located
        assert cache_dir.startswith(os.path.join(os.path.expanduser('~'),
                                                 '.cache'))
        if os.path.isdir(cache_dir):
            try:
                shutil.rmtree(cache_dir, ignore_errors=True)
            except:
                logging.error("Unknown error deleting cache directory %s",
                              cache_dir)

        self.devices.delete_cache_dirs()


    def getDeviceIcon(self, device: Device) -> QIcon:
        if device.device_type == DeviceType.volume:
            icon = None
            if device.icon_names is not None:
                for i in device.icon_names:
                    if QIcon.hasThemeIcon(i):
                        icon = QIcon.fromTheme(i)
                        break
            if icon is not None:
                return icon
            else:
                return QFileIconProvider().icon(QFileIconProvider.Drive)
        elif device.device_type == DeviceType.path:
            return QFileIconProvider().icon(QFileIconProvider.Folder)
        else:
            assert device.device_type == DeviceType.camera
            for i in ('camera-photo', 'camera'):
                if QIcon.hasThemeIcon(i):
                    return QIcon.fromTheme(i)
            return None

    def getIconsAndEjectableForMount(self, mount: QStorageInfo):
        """
        Given a mount, get the icon names suggested by udev, and
        determine whether the mount is ejectable or not.
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
            self.camerasToUnmount[port] = model
            if self.gvolumeMonitor.unmountCamera(model, port):
                return True
            else:
                del self.camerasToUnmount[port]
        return False

    def cameraUnmounted(self, result, model, port):
        assert self.camerasToUnmount[port] == model
        del self.camerasToUnmount[port]
        if result:
            self.startCameraScan(model, port)
        else:
            logging.debug("Not scanning %s because it could not be "
                          "unmounted", model)

    def searchForCameras(self):
        if self.prefs.device_autodetection:
            cameras = self.gp_context.camera_autodetect()
            for model, port in cameras:
                if port in self.camerasToUnmount:
                    assert self.camerasToUnmount[port] == model
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
        self.scanmq.add_worker(scan_id, scan_arguments)
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
        # self.display_free_space()

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
    #FIXME move this to qrc file, so it doesn't fail when cwd is different
    app.setWindowIcon(QtGui.QIcon(os.path.join('images',
                                               'rapid-photo-downloader.svg')))

    rw = RapidWindow()
    rw.show()

    sys.exit(app.exec_())
