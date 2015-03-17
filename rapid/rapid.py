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
import time
import os

from gettext import gettext as _

import zmq
import gphoto2 as gp

from PyQt5 import QtCore, QtWidgets, QtGui

from PyQt5.QtCore import (QThread, Qt, QStorageInfo, QSettings, QPoint,
                          QSize, QFileInfo)
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (QAction, QApplication, QFileDialog, QLabel,
        QMainWindow, QMenu, QMessageBox, QScrollArea, QSizePolicy,
        QPushButton, QFrame, QWidget, QDialogButtonBox,
        QProgressBar, QSplitter, QFileIconProvider, QHBoxLayout, QVBoxLayout)

# import dbus
# from dbus.mainloop.pyqt5 import DBusQtMainLoop


from storage import (ValidMounts, CameraHotplug, UDisks2Monitor,
                     GVolumeMonitor, have_gio, has_non_empty_dcim_folder,
                     mountPaths, get_desktop_environment, gvfs_controls_mounts)
from interprocess import (PublishPullPipelineManager, ScanArguments)
from devices import (Device, DeviceCollection)
from preferences import (Preferences, ScanPreferences)
from constants import BackupLocationForFileType, DeviceType
from thumbnaildisplay import (ThumbnailView, ThumbnailTableModel,
    ThumbnailDelegate)
from devicedisplay import (DeviceTableModel, DeviceView, DeviceDelegate)
import rpdfile

logging_level = logging.DEBUG
logging.basicConfig(format='%(asctime)s %(message)s', level=logging_level)


class ScanManager(PublishPullPipelineManager):
    message = QtCore.pyqtSignal(rpdfile.RPDFile)
    def __init__(self, context):
        super(ScanManager, self).__init__(context)
        self._process_name = 'Scan Manager'
        self._process_to_run = 'scan.py'


class RapidWindow(QMainWindow):
    def __init__(self, parent=None):
        self.do_init = QtCore.QEvent.registerEventType()
        super(RapidWindow, self).__init__(parent)

        self.context = zmq.Context()

        self.setWindowTitle(_("Rapid Photo Downloader"))
        self.readWindowSettings()
        self.prefs = Preferences()
        self.setupWindow()

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
        # self.statusLabel.setFrameStyle()
        status.addPermanentWidget(self.downloadProgressBar)

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

        self.validMounts = ValidMounts(onlyExternalMounts=self.prefs[
            'only_external_mounts'])

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

        #Track which downloads are running
        self.activeDownloadsByScanId = set()

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

        # Setup the Scan processes
        self.scanThread = QThread()
        self.scanmq = ScanManager(self.context)
        self.scanmq.moveToThread(self.scanThread)

        self.scanThread.started.connect(self.scanmq.run_sink)
        self.scanmq.message.connect(self.scanMessageReceived)
        self.scanmq.workerFinished.connect(self.scanFinished)

        # call the slot with no delay
        QtCore.QTimer.singleShot(0, self.scanThread.start)

        self.setDownloadActionSensitivity()
        self.searchForCameras()
        self.setupNonCameraDevices(onStartup=True, onPreferenceChange=False,
                                   blockAutoStart=False)

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

    def set_download_action_label(self, is_download):
        """
        Toggles label betwen pause and download
        """

        if is_download:
            self.download_action.set_label(_("Download"))
            self.download_action_is_download = True
        else:
            self.download_action.set_label(_("Pause"))
            self.download_action_is_download = False


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

    def handlePauseButton(self):
        if self.paused:
            self.scanmq.resume()
            self.paused = False
            self.pauseButton.setText("Pause")
        else:
            self.scanmq.pause()
            self.pauseButton.setText("Resume")
            self.paused = True

    def downloadIsRunning(self) -> bool:
        """
        :return True if a file is currently being downloaded, renamed
        or backed up, else False
        """
        return len(self.activeDownloadsByScanId) > 0

    def scanMessageReceived(self, rpd_file: rpdfile.RPDFile):
        # Update scan running totals
        scan_id = rpd_file.scan_id
        device = self.devices[scan_id]
        device.file_type_counter[rpd_file.file_type] += 1
        device.file_size_sum += rpd_file.size
        size = self.formatSizeForUser(device.file_size_sum)
        text = device.file_type_counter.running_file_count()
        self.deviceModel.updateDeviceScan(scan_id, text, size)

        self.thumbnailModel.addFile(rpd_file, True)

    def scanFinished(self, scan_id: int):
        device = self.devices[scan_id]
        text = device.file_type_counter.summarize_file_count()[0]
        self.deviceModel.updateDeviceScan(scan_id, text, scanCompleted=True)
        # Generate thumbnails for finished scan
        self.thumbnailModel.generateThumbnails(scan_id, self.devices[
            scan_id], self.prefs['thumbnail_quality_lower'])
        self.setDownloadActionSensitivity()

    def closeEvent(self, event):
        self.writeWindowSettings()
        self.scanmq.stop()
        self.thumbnailModel.thumbnailmq.stop()
        self.scanThread.quit()
        self.scanThread.wait()
        self.thumbnailModel.thumbnailThread.quit()
        self.thumbnailModel.thumbnailThread.wait()
        if not self.gvfsControlsMounts:
            self.udisks2MonitorThread.quit()
            self.udisks2MonitorThread.wait()
            self.cameraHotplugThread.quit()
            self.cameraHotplugThread.wait()

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
        if not self.prefs['device_autodetection']:
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
        if self.prefs['device_autodetection']:
            cameras = self.gp_context.camera_autodetect()
            for model, port in cameras:
                if port in self.camerasToUnmount:
                    assert self.camerasToUnmount[port] == model
                    logging.debug("Already unmounting %s", model)
                elif self.devices.known_camera(model, port):
                    logging.debug("Camera %s is known", model)
                elif model in self.prefs['camera_blacklist']:
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
        scan_preferences = ScanPreferences(self.prefs['ignored_paths'])
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
            if (path in self.prefs['path_blacklist'] and
                    self.scanEvenIfNoDCIM()):
                logging.info("blacklisted device %s ignored",
                             mount.displayName())
                return False
            else:
                return True
        return False

    def shouldScanMountPath(self, path: str) -> bool:
        if self.prefs['device_autodetection']:
            if (self.prefs['device_without_dcim_autodetection'] or
                    has_non_empty_dcim_folder(path)):
                return True
        return False

    def prepareNonCameraDeviceScan(self, device: Device):
        if not self.devices.known_device(device):
            if (self.scanEvenIfNoDCIM() and
                    not device.path in self.prefs['path_whitelist']):
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
                backupFileType = self.isBackupPath(path)

                if backupFileType is not None:
                    #TODO implement backup handling
                    pass
                    # if path not in self.backup_devices:
                    #     self.backup_devices[path] = mount
                    #     name = self._backup_device_name(path)
                    #     self.backup_manager.add_device(path, name, backup_file_type)
                    #     self.update_no_backup_devices()
                    #     self.display_free_space()

                elif self.shouldScanMountPath(path):
                    #TODO implement autostart
                    #self.auto_start_is_on =
                    # self.prefs.auto_download_upon_device_insertion
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

        elif False: #path in self.backup_devices:
            pass
            # del self.backup_devices[path]
            # self.display_free_space()
            # self.backup_manager.remove_device(path)
            # self.update_no_backup_devices()

        self.setDownloadActionSensitivity()


    def removeDevice(self, scan_id):
        assert scan_id is not None
        self.thumbnailModel.clearAll(scan_id=scan_id,
                                     keep_downloaded_files=True)
        self.deviceModel.removeDevice(scan_id)
        del self.devices[scan_id]
        self.resizeDeviceView()

    def setupNonCameraDevices(self, onStartup: bool, onPreferenceChange: bool,
                              blockAutoStart: bool):
        """
        Setup devices from which to download from and backup to, and
        if relevant start scanning them

        Removes any image media that are currently not downloaded,
        or finished downloading

        :param onStartup: should be True if the program is still
        starting i.e. this is being called from the program's
        initialization.
        :param onPreferenceChange: should be True if this is being
        called as the result of a program preference being changed
        :param blockAutoStart: should be True if automation options to
        automatically start a download should be ignored
        """

        self.clearNonRunningDownloads()
        if not self.prefs['device_autodetection']:
             if not self.confirmManualDownloadLocation():
                return

        mounts = []
        self.backupDevices = {}

        if self.monitorPartitionChanges():
            # either using automatically detected backup devices
            # or download devices
            for mount in self.validMounts.mountedValidMountPoints():
                if self.partitionValid(mount):
                    path = mount.rootPath()
                    logging.debug("Detected %s", mount.displayName())
                    backupFileType = self.isBackupPath(path)
                    if backupFileType is not None:
                        #TODO use namedtuple or better
                        self.backup_devices[path] = (mount, backupFileType)
                    elif self.shouldScanMountPath(path):
                        logging.debug("Appending %s", mount.displayName())
                        mounts.append(mount)
                    else:
                        logging.debug("Ignoring %s", mount.displayName())

        # if self.prefs.backup_images:
        #     if not self.prefs.backup_device_autodetection:
        #         self._setup_manual_backup()
        #     self._add_backup_devices()
        #
        # self.update_no_backup_devices()

        # Display amount of free space in a status bar message
        # self.display_free_space()

        if blockAutoStart:
            self.autoStartIsOn = False
        else:
            self.autoStartIsOn = ((not onPreferenceChange) and
                    ((self.prefs['auto_download_at_startup'] and
                      onStartup) or
                      (self.prefs['auto_download_upon_device_insertion'] and
                       not onStartup)))

        if not self.prefs['device_autodetection']:
            # user manually specified the path from which to download
            path = self.prefs['device_location']
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
                iconNames, canEject = self.getIconsAndEjectableForMount(mount)
                device = Device()
                device.set_download_from_volume(mount.rootPath(),
                                              mount.displayName(),
                                              iconNames,
                                              canEject)
                self.prepareNonCameraDeviceScan(device)
        # if not mounts:
        #     self.set_download_action_sensitivity()

    def isBackupPath(self, path: str) -> BackupLocationForFileType:
        """
        Checks to see if backups are enabled and path represents a
        valid backup location. It must be writeable.

        Checks against user preferences.

        :return The type of file that should be backed up to the path,
        else if nothing should be, return None
        """
        if self.prefs['backup_images']:
            if self.prefs['backup_device_autodetection']:
                # Determine if the auto-detected backup device is
                # to be used to backup only photos, or videos, or both.
                # Use the presence of a corresponding directory to
                # determine this.
                # The directory must be writable.
                photo_path = os.path.join(path, self.prefs[
                    'photo_backup_identifier'])
                p_backup = os.path.isdir(photo_path) and os.access(
                    photo_path, os.W_OK)
                video_path = os.path.join(path, self.prefs[
                    'video_backup_identifier'])
                v_backup = os.path.isdir(video_path) and os.access(
                    video_path, os.W_OK)
                if p_backup and v_backup:
                    logging.info("Photos and videos will be backed up to "
                                 "%s", path)
                    return BackupLocationForFileType.photos_and_videos
                elif p_backup:
                    logging.info("Photos will be backed up to %s", path)
                    return BackupLocationForFileType.photos
                elif v_backup:
                    logging.info("Videos will be backed up to %s", path)
                    return BackupLocationForFileType.videos
            elif path == self.prefs['backup_photo_location']:
                # user manually specified the path
                if os.access(path, os.W_OK):
                    return BackupLocationForFileType.photos
            elif path == self.prefs['backup_video_location']:
                # user manually specified the path
                if os.access(path, os.W_OK):
                    return BackupLocationForFileType.videos
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
        return (self.prefs['device_autodetection'] or self.prefs[
            'backup_device_autodetection'])

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
        return (self.prefs['device_autodetection'] and self.prefs[
            'device_without_dcim_autodetection'])

    def formatSizeForUser(self, size: int, zero_string='',
                             with_decimals=True,
                             kb_only=False):
        """
        Format an int containing the number of bytes into a string
        suitable for displaying to the user.

        :param size: size in bytes
        :param zero_string: string to use if size == 0
        :param kb_only: display in KB or B
        source: https://develop.participatoryculture.org/trac/democracy/browser/trunk/tv/portable/util.py?rev=3993
        """
        if size > (1 << 30) and not kb_only:
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
