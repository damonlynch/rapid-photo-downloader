# Copyright (C) 2016-2021 Damon Lynch <damonlynch@gmail.com>

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


__author__ = "Damon Lynch"
__copyright__ = "Copyright 2016-2021, Damon Lynch"

import logging
from typing import List

from PyQt5.QtCore import QObject, pyqtSlot

from raphodo.devices import DeviceCollection
from raphodo.ui.filebrowse import FileSystemModel, FileSystemView, FileSystemFilter
from raphodo.folderspreview import FoldersPreview, DownloadDestination
from raphodo.interprocess import OffloadData
from raphodo.prefs.preferences import Preferences
from raphodo.rpdfile import RPDFile


class FolderPreviewManager(QObject):
    """
    Manages sending FoldersPreview() off to the offload process to
    generate new provisional download subfolders, and removing provisional download
    subfolders in the main process, using QFileSystemModel.

    Queues operations if they need to be, or runs them immediately when it can.

    Sadly we must delete provisional download folders only in the main process, using
    QFileSystemModel. Otherwise the QFileSystemModel is liable to issue a large number
    of messages like this:

    QInotifyFileSystemWatcherEngine::addPaths: inotify_add_watch failed: No such file or
    directory

    Yet we must generate and create folders in the offload process, because that
    can be expensive for a large number of rpd_files.

    New for PyQt 5.7: Inherits from QObject to allow for Qt signals and slots using PyQt
    slot decorator.
    """

    def __init__(
        self,
        fsmodel: FileSystemModel,
        prefs: Preferences,
        photoDestinationFSView: FileSystemView,
        videoDestinationFSView: FileSystemView,
        fileSystemFilter: FileSystemFilter,
        devices: DeviceCollection,
        rapidApp: "RapidWindow",
    ) -> None:
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
        self.fileSystemFilter = fileSystemFilter

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
            logging.info(
                "Generating provisional download folders for %s files", len(rpd_files)
            )
        data = OffloadData(
            rpd_files=rpd_files,
            strip_characters=self.prefs.strip_characters,
            folders_preview=self.folders_preview,
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
            video_subfolder=self.prefs.video_subfolder,
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
                "Not removing or moving provisional download folders because a "
                "download is running"
            )

        if dirty:
            self._update_model_and_views()

        if self.rpd_files_queue:
            logging.debug(
                "Assigning queued provisional download folders to be generated"
            )
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
        # Set the root index so the views do not show the / folder
        index = self.fileSystemFilter.mapFromSource(self.fsmodel.index("/"))
        self.photoDestinationFSView.setRootIndex(index)
        self.videoDestinationFSView.setRootIndex(index)
        # Ensure the file system model caches are refreshed:
        self.fsmodel.setRootPath(self.folders_preview.photo_download_folder)
        self.fsmodel.setRootPath(self.folders_preview.video_download_folder)
        self.fsmodel.setRootPath("/")
        self.photoDestinationFSView.expandPreviewFolders(
            self.prefs.photo_download_folder
        )
        self.videoDestinationFSView.expandPreviewFolders(
            self.prefs.video_download_folder
        )

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
                "Cleaning provisional download folders for %s",
                self.devices[scan_id].display_name,
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
