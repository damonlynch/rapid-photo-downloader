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

from PyQt5.QtCore import QThread, Qt, QStorageInfo
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QPixmap
from PyQt5.QtWidgets import (QAction, QApplication, QFileDialog, QLabel,
        QMainWindow, QMenu, QMessageBox, QScrollArea, QSizePolicy,
        QProgressBar, QSplitter)

# import dbus
# from dbus.mainloop.pyqt5 import DBusQtMainLoop


from storage import mounted_volumes, DeviceHotplug, using_gio
import storage

from interprocess import PublishPullPipelineManager, ScanArguments, Device
from preferences import ScanPreferences
from thumbnaildisplay import (ThumbnailView, ThumbnailTableModel, \
    ThumbnailDelegate)
import rpdfile

logging_level = logging.DEBUG
logging.basicConfig(format='%(asctime)s %(message)s', level=logging_level)



class ScanManager(PublishPullPipelineManager):
    message = QtCore.pyqtSignal(rpdfile.RPDFile)
    def __init__(self, context):
        super(ScanManager, self).__init__(context)
        self._process_name = 'Scan Manager'
        self._process_to_run = 'scan.py'


class DeviceCollection:
    def __init__(self):
        self.devices = {}
        self.cameras = {}

    def add_device(self, device: Device):
        scan_id = len(self.devices)
        self.devices[scan_id] = device
        if device.camera_port:
            port = device.camera_port
            assert port not in self.cameras
            self.cameras[port] = device.camera_model
        return scan_id

    def known_camera(self, model: str, port: str) -> bool:
        """
        Check if the camera is already in the list of devices
        :param model: camera model as specified by libgohoto2
        :param port: camera port as specified by libgohoto2
        :return: True if this camera is already being processed, else False
        """
        if port in self.cameras:
            assert self.cameras[port] == model
            return True
        return False

    def __getitem__(self, item):
        return self.devices[item]

    def __len__(self):
        return len(self.devices)

class RapidWindow(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        self.do_init = QtCore.QEvent.registerEventType()
        super(RapidWindow, self).__init__(parent)

        self.context = zmq.Context()

        self.setWindowTitle(_("Rapid Photo Downloader"))
        self.setWindowSize()
        self.setupWindow()

        # frame = QtWidgets.QFrame()
        # self.stopButton = QtWidgets.QPushButton("Cancel")
        # self.pauseButton = QtWidgets.QPushButton("Pause")
        # self.paused = False

        self.thumbnailView = ThumbnailView()
        self.thumbnailModel = ThumbnailTableModel(self)
        self.thumbnailView.setModel(self.thumbnailModel)
        self.thumbnailView.setItemDelegate(ThumbnailDelegate(self))

        # self.stopButton.released.connect(self.handleStopButton)
        # self.pauseButton.released.connect(self.handlePauseButton)

        splitter = QSplitter()
        splitter.setOrientation(Qt.Vertical)
        splitter.addWidget(self.thumbnailView)
        layout = QtWidgets.QVBoxLayout()
        # layout.addWidget(self.stopButton)
        # layout.addWidget(self.pauseButton)

        layout.addWidget(splitter)

        self.createActions()
        self.createMenus()

        # a main-window-style application has only one central widget
        self.setCentralWidget(splitter)

        # defer full initialisation (slow operation) until gui is visible
        QtWidgets.QApplication.postEvent(
            self, QtCore.QEvent(self.do_init), QtCore.Qt.LowEventPriority - 1)


    def setWindowSize(self):
        #FIXME figure out what minimum window size was in previous version
        self.setMinimumSize(650, 670)

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
        #FIXME get scan preferences from actual user prefs
        self.scan_preferences = ScanPreferences(['.Trash', '.thumbnails'])

        # Initalize use of libgphoto2
        self.gp_context = gp.Context()

        if not using_gio:
            # Monitor when the user adds or removes a camera or partition (drive)
            self.deviceHotplug = DeviceHotplug()
            self.deviceHotplugThread = QThread()
            self.deviceHotplug.moveToThread(self.deviceHotplugThread)
            self.deviceHotplug.cameraAdded.connect(self.cameraAdded)
            # Start the monitor only on the thread it will be running on
            self.deviceHotplug.startMonitor()

        #Track the unmounting of cameras by port and model
        self.camerasToUnmount = {}
        if using_gio:
            self.gvolumeMonitor = storage.GVolumeMonitor()
            self.gvolumeMonitor.cameraUnmounted.connect(self.cameraUnmounted)
            self.gvolumeMonitor.cameraMounted.connect(self.cameraMounted)
            self.gvolumeMonitor.partitionMounted.connect(self.partitionMounted)

        self.devices = DeviceCollection()
        # Setup the Scan processes
        self.scanThread = QThread()
        self.scanmq = ScanManager(self.context)
        self.scanmq.moveToThread(self.scanThread)

        self.scanThread.started.connect(self.scanmq.run_sink)
        self.scanmq.message.connect(self.scanMessageReceived)
        self.scanmq.workerFinished.connect(self.scanFinished)

        # Setup the Thumbnail processes

        # call the slot with no delay
        QtCore.QTimer.singleShot(0, self.scanThread.start)

        if False:
            scan_preferences = ScanPreferences(['.Trash', '.thumbnails'])
            device = Device()
            device.set_path('/home/damon/Desktop/DCIM')
            # device.set_path('/home/damon/Pictures/final')
            # device.set_path('/data/Photos/processing/2014')
            scan_id = self.devices.add_device(device)
            scan_arguments = ScanArguments(scan_preferences, device)
            self.scanmq.add_worker(scan_id, scan_arguments)

        self.searchForCameras()




    def createActions(self):
        self.downloadAct = QAction("&Download", self, shortcut="Ctrl+Return",
                                   triggered=self.download)

        self.refreshAct = QAction("&Refresh...", self, shortcut="Ctrl+R",
                                  triggered=self.refresh)

        self.preferencesAct = QAction("&Preferences", self,
                                      shortcut="Ctrl+P",
                                      triggered=self.preferences)

        self.quitAct = QAction("&Quit", self, shortcut="Ctrl+Q",
                               triggered=self.close)

        self.checkAllAct = QAction("&Check All", self, shortcut="Ctrl+A",
                                   triggered=self.checkAll)

        self.checkAllPhotosAct = QAction("Check All Photos", self,
                                         shortcut="Ctrl+T",
                                         triggered=self.checkAllPhotos)

        self.checkAllVideosAct = QAction("Check All Videos", self,
                                         shortcut="Ctrl+D",
                                         triggered=self.checkAllVideos)

        self.uncheckAllAct = QAction("&Uncheck All", self, shortcut="Ctrl+L",
                                     triggered=self.uncheckAll)

        self.errorLogAct = QAction("Error Log", self, enabled=False,
                                   checkable=True,
                                   triggered=self.errorLog)

        self.clearDownloadsAct = QAction("Clear Completed Downloads", self,
                                         triggered=self.clearDownloads)

        self.previousFileAct = QAction("Previous File", self, shortcut="[",
                                       triggered=self.previousFile)

        self.nextFileAct = QAction("Next File", self, shortcut="]",
                                   triggered=self.nextFile)

        self.helpAct = QAction("Get Help Online...", self, shortcut="F1",
                               triggered=help)

        self.reportProblemAct = QAction("Report a Problem...", self,
                                        triggered=self.reportProblem)

        self.makeDonationAct = QAction("Make a Donation...", self,
                                       triggered=self.makeDonation)

        self.translateApplicationAct = QAction("Translate this Application...",
                                               self,
                                               triggered=self.translateApplication)

        self.aboutAct = QAction("&About...", self, triggered=self.about)

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

    def download(self):
        pass

    def refresh(self):
        pass

    def preferences(self):
        pass

    def checkAll(self):
        pass

    def checkAllPhotos(self):
        pass

    def checkAllVideos(self):
        pass

    def uncheckAll(self):
        pass

    def errorLog(self):
        pass

    def clearDownloads(self):
        pass

    def previousFile(self):
        pass

    def nextFile(self):
        pass

    def help(self):
        pass

    def reportProblem(self):
        pass

    def makeDonation(self):
        pass

    def translateApplication(self):
        pass

    def about(self):
        pass

    def handleStopButton(self):
        self.scanmq.stop()

    def handlePauseButton(self):
        if self.paused:
            self.scanmq.resume()
            self.paused = False
            self.pauseButton.setText("Pause")
        else:
            self.scanmq.pause()
            self.pauseButton.setText("Resume")
            self.paused = True

    def scanMessageReceived(self, rpd_file: rpdfile.RPDFile):
        self.thumbnailModel.addFile(rpd_file, True)

    def scanFinished(self, worker_id):
        # Generate thumbnails for finished scan
        self.thumbnailModel.generateThumbnails(worker_id, self.devices[
            worker_id])

    def closeEvent(self, event):
        self.scanmq.stop()
        self.thumbnailModel.thumbnailmq.stop()
        self.scanThread.quit()
        self.scanThread.wait()

    def cameraAdded(self):
        return
        if not using_gio:
            self.searchForCameras()


    def partitionMounted(self, path):
        #FIXME add code from old setup_devices()
        if storage.contains_dcim_folder(path):
            device = Device()
            name = QStorageInfo(path).displayName()
            device.set_path(path, name)
            scan_id = self.devices.add_device(device)
            scan_arguments = ScanArguments(self.scan_preferences, device)
            self.scanmq.add_worker(scan_id, scan_arguments)




    def cameraMounted(self):
        if using_gio:
            self.searchForCameras()

    def unmountCamera(self, model, port):
        if using_gio:
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
        cameras = self.gp_context.camera_autodetect()
        for model, port in cameras:
            if port in self.camerasToUnmount:
                assert self.camerasToUnmount[port] == model
                logging.debug("Already unmounting %s", model)
            elif self.devices.known_camera(model, port):
                logging.debug("Camera %s is known", model)
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
        scan_id = self.devices.add_device(device)
        scan_arguments = ScanArguments(self.scan_preferences, device)
        self.scanmq.add_worker(scan_id, scan_arguments)



if __name__ == "__main__":

    app = QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(QtGui.QIcon(os.path.join('images', 'rapid-photo-downloader.svg')))

    rw = RapidWindow()
    rw.show()

    sys.exit(app.exec_())
