# Copyright (C) 2015-2016 Damon Lynch <damonlynch@gmail.com>

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

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2015-2016, Damon Lynch"

import pickle
import os
import sys
import datetime
from collections import (namedtuple, defaultdict, Counter)
from operator import attrgetter
import subprocess
import shlex
from itertools import chain
import logging
from timeit import timeit
from typing import Optional, Dict, List, Set, Tuple

from gettext import gettext as _

from sortedcontainers import (SortedListWithKey, SortedList)
import arrow.arrow
from dateutil.tz import tzlocal

from PyQt5.QtCore import (QAbstractListModel, QModelIndex, Qt, pyqtSignal, QSize, QRect, QEvent,
                          QPoint, QMargins, QSortFilterProxyModel, QItemSelectionModel,
                          QAbstractItemModel, pyqtSlot, QItemSelection)
from PyQt5.QtWidgets import (QListView, QStyledItemDelegate, QStyleOptionViewItem, QApplication,
                             QStyle, QStyleOptionButton, QMenu, QWidget, QAbstractItemView)
from PyQt5.QtGui import (QPixmap, QImage, QPainter, QColor, QBrush, QFontMetrics,
                         QGuiApplication, QPen, QMouseEvent, QFont)

import zmq

from raphodo.viewutils import RowTracker, SortedListItem
from raphodo.rpdfile import RPDFile, FileTypeCounter
from raphodo.interprocess import (PublishPullPipelineManager, GenerateThumbnailsArguments, Device,
                          GenerateThumbnailsResults)
from raphodo.constants import (DownloadStatus, Downloaded, FileType, FileExtension, ThumbnailSize,
                               ThumbnailCacheStatus, Roles, DeviceType, CustomColors, Show, Sort,
                               ThumbnailBackgroundName, Desktop, DeviceState, extensionColor)
from raphodo.storage import get_program_cache_directory, get_desktop
from raphodo.utilities import (CacheDirs, make_internationalized_list, format_size_for_user, runs)
from raphodo.thumbnailer import Thumbnailer


class DownloadTypes:
    def __init__(self):
        self.photos = False
        self.videos = False


DownloadFiles = namedtuple('DownloadFiles', ['files', 'download_types',
                                             'download_stats',
                                             'camera_access_needed'])


class DownloadStats:
    def __init__(self):
        self.no_photos = 0
        self.no_videos = 0
        self.photos_size_in_bytes = 0
        self.videos_size_in_bytes = 0
        self.post_download_thumb_generation = 0


class ThumbnailManager(PublishPullPipelineManager):
    message = pyqtSignal(RPDFile, QPixmap)
    cacheDirs = pyqtSignal(int, CacheDirs)

    def __init__(self, logging_port: int) -> None:
        super().__init__(logging_port=logging_port)
        self._process_name = 'Thumbnail Manager'
        self._process_to_run = 'thumbnail.py'
        self._worker_id = 0

    def process_sink_data(self) -> None:
        data = pickle.loads(self.content) # type: GenerateThumbnailsResults
        if data.rpd_file is not None:
            thumbnail = QImage.fromData(data.thumbnail_bytes)
            thumbnail = QPixmap.fromImage(thumbnail)
            self.message.emit(data.rpd_file, thumbnail)
        else:
            assert data.cache_dirs is not None
            self.cacheDirs.emit(data.scan_id, data.cache_dirs)

    def get_worker_id(self) -> int:
        self._worker_id += 1
        return self._worker_id


class ThumbnailListModel(QAbstractListModel):
    def __init__(self, parent, logging_port: int, log_gphoto2: bool) -> None:
        super().__init__(parent)
        self.rapidApp = parent
        self.proxyModel = None  # type: ThumbnailSortFilterProxyModel

        self.initialize()

        no_workers = parent.prefs.max_cpu_cores
        self.thumbnailmq = Thumbnailer(parent=parent, no_workers=no_workers,
               logging_port=logging_port, log_gphoto2=log_gphoto2)
        self.thumbnailmq.ready.connect(self.thumbnailerReady)
        self.thumbnailmq.thumbnailReceived.connect(self.thumbnailReceived)

        self.thumbnailmq.cacheDirs.connect(self.cacheDirsReceived)

        # dict of scan_pids that are having thumbnails generated
        # value is the thumbnail process id
        # this is needed when terminating thumbnailing early such as when
        # user clicks download before the thumbnailing is finished
        self.generating_thumbnails = {}

    def initialize(self) -> None:
        # unique_id: QPixmap
        self.thumbnails = {}  # type: Dict[str, QPixmap]

        # unique_id
        self.marked = set()  # type: Set[str]
        self.photos = set()  # type: Set[str]
        self.videos = set()  # type: Set[str]
        self.downloaded = set()  # type: Set[str]
        self.not_downloaded = set()  # type: Set[str]
        self.previously_downloaded = set()  # type: Set[str]

        # scan_id
        self.removed_devices = set()  # type: Set[int]

        # Files are hidden when the combo box "Show" in the main window is set to
        # "New" instead of the default "All".

        # Sort thumbnails based on the time the files were modified
        self.rows = SortedListWithKey(key=attrgetter('modification_time'))
        # unique_id: RPDFile
        self.rpd_files = {}  # type: Dict[str, RPDFile]
        # scan_id: unique_id  -- includes scan ids of removed devices
        self.scan_index = defaultdict(set)  # type: defaultdict[int, Set[str]]

        self.photo_icon = QPixmap(':/photo.png')
        self.video_icon = QPixmap(':/video.png')

        self.total_thumbs_to_generate = 0
        self.thumbnails_generated = 0
        self.no_thumbnails_by_scan = defaultdict(int)

        self.thumbnailer_ready = False
        self.thumbnailer_generation_queue = []

    def logState(self) -> None:
        logging.debug("-- Thumbnail Model --")
        if not self.thumbnailer_ready:
            logging.debug("Thumbnailer not yet ready")
        else:
            if len(self.thumbnails) != len(self.rows) or len(self.rows) != len(self.rpd_files):
                logging.error("Conflicting values: %s thumbnails; %s rows; %s rpd_files",
                              len(self.thumbnails), len(self.rows), len(self.rpd_files))
            else:
                logging.debug("%s thumbnails", len(self.thumbnails))
            logging.debug("%s thumnails marked", len(self.marked))
            logging.debug("%s not downloaded; %s downloaded; %s previously downloaded",
                          len(self.not_downloaded), len(self.downloaded),
                          len(self.previously_downloaded))
            logging.debug("%s photos; %s videos", len(self.photos), len(self.videos))
            if self.total_thumbs_to_generate:
                logging.debug("%s to be generated; %s generated", self.total_thumbs_to_generate,
                              self.thumbnails_generated)
            logging.debug("Known devices: %s",
                          ', '.join(self.rapidApp.devices[scan_id].display_name
                                    for scan_id in self.scan_index
                                    if scan_id not in self.removed_devices))
            logging.debug("%s total devices seen; %s devices removed",
                          len(self.scan_index),  len(self.removed_devices))
    def rowFromUniqueId(self, unique_id: str) -> int:
        list_item = SortedListItem(unique_id, self.rpd_files[unique_id].modification_time)
        return self.rows.index(list_item)

    def columnCount(self, parent: QModelIndex) -> int:
        return 1

    def rowCount(self, parent: QModelIndex=QModelIndex()) -> int:
        return len(self.rows)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        if row >= len(self.rows) or row < 0:
            return None
        unique_id = self.rows[row].id_value
        rpd_file = self.rpd_files[unique_id] # type: RPDFile

        if role == Qt.DisplayRole:
            # This is never displayed, but is used for filtering!
            return self.rows[row].modification_time
        elif role == Qt.DecorationRole:
            return self.thumbnails[unique_id]
        elif role == Qt.CheckStateRole:
            if unique_id in self.marked:
                return Qt.Checked
            else:
                return Qt.Unchecked
        elif role == Roles.sort_extension:
            return rpd_file.extension
        elif role == Roles.file_type_sort:
            # For sorting to work, must explicitly return the enum's value
            return rpd_file.file_type.value
        elif role == Roles.filename:
            return rpd_file.name
        elif role == Roles.previously_downloaded:
            return rpd_file.previously_downloaded()
        elif role == Roles.extension:
            return rpd_file.extension, rpd_file.extension_type
        elif role == Roles.download_status:
            return rpd_file.status
        elif role == Roles.has_audio:
            return rpd_file.has_audio()
        elif role == Roles.secondary_attribute:
            if rpd_file.xmp_file_full_name:
                return 'XMP'
            else:
                return None
        elif role== Roles.path:
            if rpd_file.status in Downloaded:
                return rpd_file.download_full_file_name
            else:
                return rpd_file.full_file_name
        elif role == Roles.uri:
            return rpd_file.get_uri(desktop_environment=True)
        elif role == Roles.camera_memory_card:
            return rpd_file.camera_memory_card_identifiers
        elif role == Roles.mtp:
            return rpd_file.is_mtp_device
        elif role == Roles.scan_id:
            return rpd_file.scan_id
        elif role == Roles.is_camera:
            return rpd_file.from_camera
        elif role == Qt.ToolTipRole:
            size = format_size_for_user(rpd_file.size)

            mtime = arrow.get(rpd_file.modification_time)
            humanized_modification_time = _(
                '%(date_time)s (%(human_readable)s)' %
                {'date_time': mtime.to('local').naive.strftime(
                    '%c'),
                 'human_readable': mtime.humanize()})

            msg = '{}\n{}\n{}'.format(rpd_file.name,
                                      humanized_modification_time, size)

            if rpd_file.camera_memory_card_identifiers:
                cards = _('Memory cards: %s') % make_internationalized_list(
                    rpd_file.camera_memory_card_identifiers)
                msg += '\n' + cards

            if rpd_file.status in Downloaded:
                path = rpd_file.download_path + os.sep
                msg += '\n\nDownloaded as:\n%(filename)s\n%(path)s' % {
                    'filename': rpd_file.download_name,
                    'path': path}

            if rpd_file.previously_downloaded():

                prev_datetime = arrow.get(rpd_file.prev_datetime,
                                          tzlocal())
                prev_date = _('%(date_time)s (%(human_readable)s)' %
                {'date_time': prev_datetime.naive.strftime(
                    '%c'),
                 'human_readable': prev_datetime.humanize()})

                path, prev_file_name = os.path.split(rpd_file.prev_full_name)
                path += os.sep
                msg += _('\n\nPrevious download:\n%(filename)s\n%(path)s\n%('
                         'date)s') % {'date': prev_date,
                                       'filename': prev_file_name,
                                       'path': path}
            return msg

    def setData(self, index: QModelIndex, value, role: int) -> bool:
        if not index.isValid():
            return False

        row = index.row()
        if row >= len(self.rows) or row < 0:
            return False
        unique_id = self.rows[row].id_value
        if role == Qt.CheckStateRole:
            self.setCheckedValue(value, unique_id)
            self.dataChanged.emit(self.index(row, 0), self.index(row, 0))
            return True
        return False

    def updateDisplayPostDataChange(self, scan_id: Optional[int]=None):
        if scan_id is not None:
            scan_ids = [scan_id]
        else:
            scan_ids = (scan_id for scan_id in self.scan_index
                        if scan_id not in self.removed_devices)
        for scan_id in scan_ids:
            self.updateDeviceDisplayCheckMark(scan_id=scan_id)
        self.rapidApp.displayMessageInStatusBar()
        self.rapidApp.setDownloadActionState()

    def setCheckedValue(self, checked: bool, unique_id: str) -> None:
        if checked:
            self.marked.add(unique_id)
        else:
            if unique_id in self.marked:
                self.marked.remove(unique_id)

    def insertRows(self, position, rows=1, index=QModelIndex()):
        self.beginInsertRows(QModelIndex(), position, position + rows - 1)
        self.endInsertRows()
        return True

    def removeRows(self, position, rows=1, index=QModelIndex()):
        self.beginRemoveRows(QModelIndex(), position, position + rows - 1)
        unique_ids = [item.id_value for item in self.rows[position:position+rows]]
        del self.rows[position:position+rows]
        for unique_id in unique_ids:
            scan_id = self.rpd_files[unique_id].scan_id
            del self.thumbnails[unique_id]
            if unique_id in self.marked:
                self.marked.remove(unique_id)
            rpd_file = self.rpd_files[unique_id]
            if rpd_file.previously_downloaded():
                self.previously_downloaded.remove(unique_id)
            if rpd_file.file_type == FileType.photo:
                self.photos.remove(unique_id)
            else:
                self.videos.remove(unique_id)
            if rpd_file.status in Downloaded:
                self.downloaded.remove(unique_id)
            else:
                self.not_downloaded.remove(unique_id)
            self.scan_index[scan_id].remove(unique_id)
            del self.rpd_files[unique_id]
        self.endRemoveRows()
        return True

    def addFile(self, rpd_file: RPDFile, generate_thumbnail: bool):
        unique_id = rpd_file.unique_id
        self.rpd_files[unique_id] = rpd_file

        if rpd_file.file_type == FileType.photo:
            self.thumbnails[unique_id] = self.photo_icon
            self.photos.add(unique_id)
        else:
            self.thumbnails[unique_id] = self.video_icon
            self.videos.add(unique_id)

        self.not_downloaded.add(unique_id)

        if not rpd_file.previously_downloaded():
            self.marked.add(unique_id)
        else:
            self.previously_downloaded.add(unique_id)

        self.scan_index[rpd_file.scan_id].add(unique_id)

        if generate_thumbnail:
            self.total_thumbs_to_generate += 1
            self.no_thumbnails_by_scan[rpd_file.scan_id] += 1

        list_item = SortedListItem(unique_id, rpd_file.modification_time)
        self.rows.add(list_item)
        row = self.rows.index(list_item)

        self.insertRow(row)

    @pyqtSlot(int, CacheDirs)
    def cacheDirsReceived(self, scan_id: int, cache_dirs: CacheDirs):
        if scan_id in self.rapidApp.devices:
            self.rapidApp.devices[scan_id].photo_cache_dir = cache_dirs.photo_cache_dir
            self.rapidApp.devices[scan_id].video_cache_dir = cache_dirs.video_cache_dir

    @pyqtSlot(RPDFile, QPixmap)
    def thumbnailReceived(self, rpd_file: RPDFile, thumbnail: Optional[QPixmap]) -> None:
        unique_id = rpd_file.unique_id
        if unique_id not in self.rpd_files:
            # A thumbnail has been generated for a no longer displayed file
            return
        scan_id = rpd_file.scan_id
        self.rpd_files[unique_id] = rpd_file
        if not thumbnail.isNull():
            try:
                row = self.rowFromUniqueId(unique_id)
            except ValueError:
                return
            self.thumbnails[unique_id] = thumbnail
            self.dataChanged.emit(self.index(row,0),self.index(row,0))
        self.thumbnails_generated += 1
        self.no_thumbnails_by_scan[scan_id] -= 1
        log_state = False
        if self.no_thumbnails_by_scan[scan_id] == 0:
            if self.rapidApp.deviceState(scan_id) == DeviceState.thumbnailing:
                self.rapidApp.devices.set_device_state(scan_id, DeviceState.idle)
            device = self.rapidApp.devices[scan_id]
            logging.info('Finished thumbnail generation for %s', device.name())
            self.rapidApp.updateProgressBarState()
            log_state = True

        if self.thumbnails_generated == self.total_thumbs_to_generate:
            self.resetThumbnailTrackingAndDisplay()
        elif self.total_thumbs_to_generate:
            self.rapidApp.downloadProgressBar.setValue(self.thumbnails_generated)

        if log_state:
            self.logState()

    def _get_cache_location(self, download_folder: str, is_photo_dir: bool) -> str:
        if self.rapidApp.isValidDownloadDir(download_folder, is_photo_dir=is_photo_dir):
            return download_folder
        else:
            folder = get_program_cache_directory(create_if_not_exist=True)
            if folder is not None:
                return folder
            else:
                return os.path.expanduser('~')

    def getCacheLocations(self) -> CacheDirs:
        photo_cache_folder = self._get_cache_location(
            self.rapidApp.prefs.photo_download_folder, is_photo_dir=True)
        video_cache_folder = self._get_cache_location(
            self.rapidApp.prefs.video_download_folder, is_photo_dir=False)
        return CacheDirs(photo_cache_folder, video_cache_folder)

    @pyqtSlot()
    def thumbnailerReady(self) -> None:
        self.thumbnailer_ready = True
        if self.thumbnailer_generation_queue:
            for gen_args in self.thumbnailer_generation_queue:
                self.thumbnailmq.generateThumbnails(*gen_args)
            self.thumbnailer_generation_queue = []

    def generateThumbnails(self, scan_id: int, device: Device) -> None:
        """Initiates generation of thumbnails for the device."""

        if scan_id in self.scan_index:
            self.rapidApp.downloadProgressBar.setMaximum(self.total_thumbs_to_generate)
            cache_dirs = self.getCacheLocations()
            rpd_files = list((self.rpd_files[unique_id] for unique_id in self.scan_index[scan_id]))

            gen_args = (scan_id, rpd_files, device.name(), cache_dirs, device.camera_model,
                        device.camera_port)
            if not self.thumbnailer_ready:
                self.thumbnailer_generation_queue.append(gen_args)
            else:
                self.thumbnailmq.generateThumbnails(*gen_args)

    def resetThumbnailTrackingAndDisplay(self):
        self.rapidApp.downloadProgressBar.reset()
        self.thumbnails_generated = 0
        self.total_thumbs_to_generate = 0

    def clearAll(self, scan_id: Optional[int]=None, keep_downloaded_files: bool=False) -> bool:
        """
        Removes files from display and internal tracking.

        If scan_id is not None, then only files matching that scan_id
        will be removed. Otherwise, everything will be removed.

        If keep_downloaded_files is True, files will not be removed if
        they have been downloaded.

        :param scan_id: if None, keep_downloaded_files must be False
        :param keep_downloaded_files: don't remove thumbnails if they represent
         files that have now been downloaded
        :return: True if any row was removed, else False
        """
        if scan_id is None and not keep_downloaded_files:
            self.initialize()
            return True
        else:
            assert scan_id is not None
            # Generate list of thumbnails to remove
            if keep_downloaded_files:
                not_downloaded = self.scan_index[scan_id] - self.downloaded
                rows = [self.rowFromUniqueId(unique_id) for unique_id in not_downloaded]
            else:
                rows = [self.rowFromUniqueId(unique_id) for unique_id in self.scan_index[scan_id]]

            # Generate groups of rows, and remove that group
            rows.sort()
            start = 0
            for index, row in enumerate(rows[:-1]):
                if row+1 != rows[index+1]:
                    group = rows[start:index+1]
                    self.removeRows(group[0], len(group))
                    start = index+1
            if rows:
                self.removeRows(rows[start], len(rows[start:]))
            if not keep_downloaded_files or not len(self.scan_index[scan_id]):
                del self.scan_index[scan_id]
            self.removed_devices.add(scan_id)

            if scan_id in self.no_thumbnails_by_scan:
                self.recalculateThumbnailsPercentage(scan_id=scan_id)
            self.rapidApp.displayMessageInStatusBar()

            return len(rows) > 0

    def filesAreMarkedForDownload(self, scan_id: Optional[int]=None) -> bool:
        """
        Checks for the presence of checkmark besides any file that has
        not yet been downloaded.

        :param scan_id: if specified, checks for files only associated
         with that scan
        :return: True if there is any file that the user has indicated
        they intend to download, else False.
        """
        if scan_id is not None:
            return len(self.marked & self.scan_index[scan_id]) > 0
        else:
            return len(self.marked) > 0

    def displayedNotDownloadedThumbs(self, scan_id: Optional[int]=None) -> Set[str]:
        if scan_id is not None:
            unique_ids = self.scan_index[scan_id] - self.downloaded
        else:
            unique_ids = self.not_downloaded.copy()

        if self.proxyModel.proximity_rows:
            unique_ids = unique_ids & self.rapidApp.temporalProximity.selected_unique_ids

        if self.rapidApp.showOnlyNewFiles():
            unique_ids -= self.previously_downloaded

        return unique_ids

    def getNoFilesMarkedForDownload(self) -> int:
        return len(self.marked)

    def getNoHiddenFiles(self) -> int:
        if self.rapidApp.showOnlyNewFiles():
            return len(self.previously_downloaded)
        else:
            return 0

    def getNoFilesAndTypesMarkedForDownload(self) -> FileTypeCounter:
        return FileTypeCounter(self.rpd_files[unique_id].file_type for unique_id in self.marked)

    def getSizeOfFilesMarkedForDownload(self) -> int:
        return sum(self.rpd_files[unique_id].size for unique_id in self.marked)

    def getNoFilesAvailableForDownload(self) -> FileTypeCounter:
        return FileTypeCounter(rpd_file.file_type for rpd_file in self.rpd_files.values() if
                                rpd_file.status == DownloadStatus.not_downloaded)

    def getFilesMarkedForDownload(self, scan_id: int) -> DownloadFiles:
        """
        Returns a dict of scan ids and associated files the user has
        indicated they want to download, and whether there are photos
        or videos included in the download.

        :param scan_id: if not None, then returns those files only from
        the device associated with that scan_id
        :return: namedtuple DownloadFiles with defaultdict() indexed by
        scan_id with value List(rpd_file), namedtuple DownloadTypes,
        and defaultdict() indexed by scan_id with value DownloadStats
        """

        files = defaultdict(list)
        download_types = DownloadTypes()
        download_stats = defaultdict(DownloadStats)
        camera_access_needed = defaultdict(bool)
        generating_fdo_thumbs = self.rapidApp.prefs.save_fdo_thumbnails


        if scan_id is not None:
            unique_ids = self.scan_index[scan_id] & self.marked
        else:
            unique_ids = self.marked

        for unique_id in unique_ids:
            rpd_file = self.rpd_files[unique_id] # type: RPDFile
            if rpd_file.status not in Downloaded:
                scan_id = rpd_file.scan_id
                files[scan_id].append(rpd_file)
                if rpd_file.file_type == FileType.photo:
                    download_types.photos = True
                    download_stats[scan_id].no_photos += 1
                    download_stats[scan_id].photos_size_in_bytes += rpd_file.size
                else:
                    download_types.videos = True
                    download_stats[scan_id].no_videos += 1
                    download_stats[scan_id].videos_size_in_bytes += rpd_file.size
                if rpd_file.from_camera and not rpd_file.cache_full_file_name:
                    camera_access_needed[scan_id] = True

                # Need to generate a thumbnail after a file has been renamed
                # if large FDO Cache thumbnail does not exist or if the
                # existing thumbnail has been marked as not suitable for the
                # FDO Cache (e.g. if we don't know the correct orientation).
                # TODO check to see if this code should be updated given can now
                # read orientation from most cameras
                if ((rpd_file.thumbnail_status !=
                        ThumbnailCacheStatus.suitable_for_fdo_cache_write) or
                        (generating_fdo_thumbs and not
                             rpd_file.fdo_thumbnail_256_name)):
                    download_stats[scan_id].post_download_thumb_generation += 1

        return DownloadFiles(files=files, download_types=download_types,
                             download_stats=download_stats,
                             camera_access_needed=camera_access_needed)

    def markDownloadPending(self, files: Dict[int, List[RPDFile]]) -> None:
        """
        Sets status to download pending and updates thumbnails display

        :param files: rpd_files by scan
        """
        for scan_id in files:
            for rpd_file in files[scan_id]:
                unique_id = rpd_file.unique_id
                self.rpd_files[unique_id].status = DownloadStatus.download_pending
                self.marked.remove(unique_id)
                row = self.rowFromUniqueId(unique_id)
                self.dataChanged.emit(self.index(row,0),self.index(row,0))

    def markThumbnailsNeeded(self, rpd_files: List[RPDFile]) -> bool:
        """
        Analyzes the files that will be downloaded, and sees if any of
        them still need to have their thumbnails generated.

        Marks generate_thumbnail in each rpd_file those for that need
        thumbnails.

        :param rpd_files: list of files to examine
        :return: True if at least one thumbnail needs to be generated
        """

        generation_needed = False
        for rpd_file in rpd_files:
            if rpd_file.unique_id not in self.thumbnails:
                rpd_file.generate_thumbnail = True
                generation_needed = True
        return generation_needed

    def getNoFilesRemaining(self, scan_id: int) -> int:
        """
        :param scan_id: if None, returns files remaining to be
         downloaded for all scan_ids, else only for that scan_id.
        :return the number of files that have not yet been downloaded
        """

        return len(self.scan_index[scan_id] - self.downloaded)

    def updateSelection(self) -> None:
        select_all_photos = self.rapidApp.selectAllPhotosCheckbox.isChecked()
        select_all_videos = self.rapidApp.selectAllVideosCheckbox.isChecked()
        unique_ids = self.displayedNotDownloadedThumbs()
        self.selectAll(select_all=select_all_photos, file_type=FileType.photo,
                       unique_ids=unique_ids)
        self.selectAll(select_all=select_all_videos, file_type=FileType.video,
                       unique_ids=unique_ids)

    def selectAll(self, select_all: bool,
                  file_type: FileType,
                  unique_ids: Optional[Set[str]]=None)-> None:
        """
        Check or deselect all visible files that are not downloaded.

        :param select_all:  if True, select, else deselect
        :param file_type: the type of files to select/deselect
        :param unique_ids: list of unique ids with which to select / deselect all
        """

        if unique_ids:
            # Don't alter the original set - create a copy
            if file_type == FileType.photo:
                unique_ids = unique_ids & self.photos
            else:
                unique_ids = unique_ids & self.videos
        else:
            unique_ids = self.displayedNotDownloadedThumbs()

            if file_type == FileType.photo:
                unique_ids -= self.videos
            else:
                unique_ids = unique_ids & self.videos

        if not unique_ids:
            return

        rows = SortedList()
        proxy = self.rapidApp.thumbnailProxyModel  # type: ThumbnailSortFilterProxyModel
        selection = self.rapidApp.thumbnailView.selectionModel()  # type: QItemSelectionModel
        selected = selection.selection()  # type: QItemSelection
        selected_indexes =  selected.indexes()

        if select_all:
            for unique_id in unique_ids:
                row = self.rowFromUniqueId(unique_id)
                model_index = self.index(row, 0)
                proxy_index = proxy.mapFromSource(model_index)
                if proxy_index not in selected_indexes:
                    rows.add(row)
            new_selection = QItemSelection()  # type: QItemSelection
            for first, last in runs(rows):
                new_selection.select(self.index(first, 0), self.index(last, 0))
            new_selection = proxy.mapSelectionFromSource(new_selection)
            new_selection.merge(selected, QItemSelectionModel.Select)
            selection.select(new_selection, QItemSelectionModel.Select)

        else:
            for unique_id in unique_ids:
                row = self.rowFromUniqueId(unique_id)
                model_index = self.index(row, 0)
                proxy_index = proxy.mapFromSource(model_index)
                if proxy_index in selected_indexes:
                    rows.add(row)
            new_selection = QItemSelection()
            for first, last in runs(rows):
                new_selection.select(self.index(first, 0), self.index(last, 0))
            new_selection = proxy.mapSelectionFromSource(new_selection)
            selection.select(new_selection, QItemSelectionModel.Deselect)

        for first, last in runs(rows):
            self.dataChanged.emit(self.index(first, 0), self.index(last, 0))

    def checkAll(self, check_all: bool,
                 file_type: Optional[FileType]=None,
                 scan_id: Optional[int]=None) -> None:
        """
        Check or uncheck all visible files that are not downloaded.

        A file is "visible" if it is in the current thumbnail display.
        That means if files are not showing because they are previously
        downloaded, they will not be affected. Likewise, if temporal
        proximity rows are selected, only those files are affected.

        Runs in the main thread and is thus time sensitive.

        :param check_all: if True, mark as checked, else unmark
        :param file_type: if specified, files must be of specified type
        :param scan_id: if specified, affects only files for that scan
        """

        rows = SortedList()

        if check_all:
            if scan_id is not None:
                unique_ids = self.scan_index[scan_id] - self.marked - self.downloaded
            else:
                unique_ids = self.not_downloaded - self.marked
        else:
            if scan_id is not None:
                unique_ids = self.marked & self.scan_index[scan_id]
            else:
                unique_ids = self.marked.copy()

        if self.proxyModel.proximity_rows:
            unique_ids = unique_ids & self.rapidApp.temporalProximity.selected_unique_ids

        if file_type == FileType.photo:
            unique_ids -= self.videos
        elif file_type == FileType.video:
            unique_ids -= self.photos

        if self.rapidApp.showOnlyNewFiles():
            unique_ids -= self.previously_downloaded

        for unique_id in unique_ids:
            row = self.rowFromUniqueId(unique_id)
            rows.add(row)

        if check_all:
            for unique_id in unique_ids:
                self.marked.add(unique_id)
        else:
            for unique_id in unique_ids:
                self.marked.remove(unique_id)

        for first, last in runs(rows):
            self.dataChanged.emit(self.index(first, 0), self.index(last, 0))

        self.updateDeviceDisplayCheckMark(scan_id=scan_id)
        self.rapidApp.displayMessageInStatusBar()
        self.rapidApp.setDownloadActionState()

    def visibleRows(self):
        """
        Yield rows visible in viewport. Currently not used.
        """

        view = self.rapidApp.thumbnailView
        rect = view.viewport().contentsRect()
        width = view.itemDelegate().width
        last_row = rect.bottomRight().x() // width * width
        top = view.indexAt(rect.topLeft())
        if top.isValid():
            bottom = view.indexAt(QPoint(last_row, rect.bottomRight().y()))
            if not bottom.isValid():
                # take a guess with an arbitrary figure
                bottom = self.index(top.row() + 15)
            for row in range(top.row(), bottom.row() + 1):
                yield row
    
    def updateDeviceDisplayCheckMark(self, scan_id: int,
                                     unique_ids: Optional[Set[str]]=None) -> None:
        if scan_id not in self.removed_devices:
            if unique_ids is None:
                unique_ids = self.displayedNotDownloadedThumbs(scan_id)
            checked_ids = unique_ids & self.marked
            if len(unique_ids) == 0 or len(checked_ids) == 0:
                checked = Qt.Unchecked
            elif len(unique_ids) != len(checked_ids):
                checked = Qt.PartiallyChecked
            else:
                checked = Qt.Checked
            self.rapidApp.mapModel(scan_id).setCheckedValue(checked, scan_id)

    def updateAllDeviceDisplayCheckMarks(self) -> None:
        scan_ids = (scan_id for scan_id in self.scan_index if scan_id not in self.removed_devices)
        for scan_id in scan_ids:
            self.updateDeviceDisplayCheckMark(scan_id=scan_id)


    def terminateThumbnailGeneration(self, scan_id: int) -> bool:
        """
        Terminates thumbnail generation if thumbnails are currently
        being generated for this scan_id
        :return True if thumbnail generation had to be terminated, else
        False
        """

        manager = self.thumbnailmq.thumbnail_manager

        terminate = scan_id in manager
        if terminate:
            manager.stop_worker(scan_id)
            # TODO update this check once checking for thumnbnailing code is more robust
            # note that check == 1 because it is assume the scan id has not been deleted
            # from the device collection
            if len(self.rapidApp.devices.thumbnailing) == 1:
                self.resetThumbnailTrackingAndDisplay()
            else:
                self.recalculateThumbnailsPercentage(scan_id=scan_id)
        return terminate

    def recalculateThumbnailsPercentage(self, scan_id: int) -> None:
        """
        Adjust % of thumbnails generated calculations after device removal.

        :param scan_id: id of removed device
        """

        self.total_thumbs_to_generate -= self.no_thumbnails_by_scan[scan_id]
        self.rapidApp.downloadProgressBar.setMaximum(self.total_thumbs_to_generate)
        del self.no_thumbnails_by_scan[scan_id]

    def updateStatusPostDownload(self, rpd_file: RPDFile):
        unique_id = rpd_file.unique_id
        self.rpd_files[unique_id] = rpd_file
        self.downloaded.add(unique_id)
        self.not_downloaded.remove(unique_id)
        row = self.rowFromUniqueId(rpd_file.unique_id)
        self.dataChanged.emit(self.index(row,0),self.index(row,0))

    def filesRemainToDownload(self) -> bool:
        """
        :return True if any files remain that are not downloaded, else
         returns False
        """
        return len(self.not_downloaded) > 0


class ThumbnailView(QListView):
    def __init__(self, parent: QWidget) -> None:
        style = """QAbstractScrollArea { background-color: %s;}""" % ThumbnailBackgroundName
        super().__init__(parent)
        self.rapidApp = parent
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setStyleSheet(style)
        self.setUniformItemSizes(True)
        self.setSpacing(8)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    @pyqtSlot(QMouseEvent)
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        Filter selection changes when click is on a thumbnail checkbox.

        When the user has selected multiple items (thumbnails), and
        then clicks one of the checkboxes, Qt's default behaviour is to
        treat that click as selecting the single item, because it doesn't
        know about our checkboxes. Therefore if the user is in fact
        clicking on a checkbox, we need to filter that event.

        Note that no matter what we do here, the delegate's editorEvent
        will still be triggered.

        :param event: the mouse click event
        """

        checkbox_clicked = False
        index = self.indexAt(event.pos())
        if index.row() >= 0:
            rect = self.visualRect(index)  # type: QRect
            delegate = self.itemDelegate(index)  # type: ThumbnailDelegate
            checkboxRect = delegate.getCheckBoxRect(rect)
            checkbox_clicked = checkboxRect.contains(event.pos())
            if checkbox_clicked:
                model = self.rapidApp.thumbnailProxyModel
                download_status = model.data(index, Roles.download_status) # type: DownloadStatus
                checkbox_clicked = download_status not in Downloaded

        if not checkbox_clicked:
            super().mousePressEvent(event)

class ThumbnailDelegate(QStyledItemDelegate):
    """
    Render thumbnail cells
    """

    def __init__(self, rapidApp, parent=None) -> None:
        super().__init__(parent)
        self.rapidApp = rapidApp

        self.checkboxStyleOption = QStyleOptionButton()
        self.checkboxRect = QApplication.style().subElementRect(
            QStyle.SE_CheckBoxIndicator, self.checkboxStyleOption, None)
        self.checkbox_size = self.checkboxRect.size().height()

        self.downloadPendingIcon = QPixmap(':/download-pending.png')
        self.downloadedIcon = QPixmap(':/downloaded.png')
        self.downloadedWarningIcon = QPixmap(':/downloaded-with-warning.png')
        self.downloadedErrorIcon = QPixmap(':/downloaded-with-error.png')
        self.audioIcon = QPixmap(':/audio.png')

        self.dimmed_opacity = 0.5

        self.image_width = max(ThumbnailSize.width, ThumbnailSize.height)
        self.image_height = self.image_width
        self.horizontal_margin = 10
        self.vertical_margin = 10
        self.image_footer = self.checkbox_size
        self.footer_padding = 5

        # Position of first memory card indicator
        self.card_x = max(self.checkboxRect.size().width(),
                          self.downloadPendingIcon.width(),
                          self.downloadedIcon.width()) + \
                      self.horizontal_margin + self.footer_padding

        self.shadow_size = 2
        self.width = self.image_width + self.horizontal_margin * 2
        self.height = self.image_height + self.footer_padding \
                      + self.image_footer + self.vertical_margin * 2

        # Thumbnail is located in a 160px square...
        self.image_area_size = max(ThumbnailSize.width, ThumbnailSize.height)
        self.image_frame_bottom = self.vertical_margin + self.image_area_size

        self.contextMenu = QMenu()
        self.openInFileBrowserAct = self.contextMenu.addAction(_('Open in File Browser...'))
        self.openInFileBrowserAct.triggered.connect(self.doOpenInFileBrowserAct)
        self.copyPathAct = self.contextMenu.addAction(_('Copy Path'))
        self.copyPathAct.triggered.connect(self.doCopyPathAction)
        # store the index in which the user right clicked
        self.clickedIndex = None  # type: QModelIndex

        self.color3 = QColor(CustomColors.color3.value)

        self.lightGray = QColor(221,221,221)
        self.darkGray = QColor(51, 51, 51)

        palette = QGuiApplication.palette()
        self.highlight = palette.highlight().color()
        self.highlight_size = 3
        self.highlight_offset = 1
        self.highlightPen = QPen()
        self.highlightPen.setColor(self.highlight)
        self.highlightPen.setWidth(self.highlight_size)
        self.highlightPen.setStyle(Qt.SolidLine)
        self.highlightPen.setJoinStyle(Qt.MiterJoin)

        self.emblemFont = QFont()
        self.emblemFont.setPointSize(self.emblemFont.pointSize() - 3)
        self.emblemFontMetrics = QFontMetrics(self.emblemFont)
        self.emblem_pad = self.emblemFontMetrics.height() // 3
        self.emblem_descent = self.emblemFontMetrics.descent()
        self.emblemMargins = QMargins(self.emblem_pad, self.emblem_pad, self.emblem_pad,
                                      self.emblem_pad)

        self.emblem_bottom = (self.image_frame_bottom + self.footer_padding +
                              self.emblemFontMetrics.height() + self.emblem_pad * 2)

    @pyqtSlot()
    def doCopyPathAction(self) -> None:
        index = self.clickedIndex
        if index:
            path = index.model().data(index, Roles.path)
            QApplication.clipboard().setText(path)

    @pyqtSlot()
    def doOpenInFileBrowserAct(self) -> None:
        index = self.clickedIndex
        if index:
            uri = index.model().data(index, Roles.uri)
            cmd = '{} {}'.format(self.rapidApp.file_manager, uri)
            logging.debug("Launching: %s", cmd)
            args = shlex.split(cmd)
            subprocess.Popen(args)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        if index is None:
            return

        # Save state of painter, restore on function exit
        painter.save()

        checked = index.data(Qt.CheckStateRole) == Qt.Checked
        previously_downloaded = index.data(Roles.previously_downloaded)
        extension, ext_type = index.data( Roles.extension)
        download_status = index.data( Roles.download_status) # type: DownloadStatus
        has_audio = index.data( Roles.has_audio)
        secondary_attribute = index.data(Roles.secondary_attribute)
        memory_cards = index.data(Roles.camera_memory_card) # type: List[int]

        x = option.rect.x()
        y = option.rect.y()

        # Draw recentangle in which the individual items will be placed
        boxRect = QRect(x, y, self.width, self.height)
        shadowRect = QRect(x + self.shadow_size, y + self.shadow_size,
                           self.width, self.height)

        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(self.darkGray)
        painter.fillRect(shadowRect, self.darkGray)
        painter.drawRect(shadowRect)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.fillRect(boxRect, self.lightGray)

        if option.state & QStyle.State_Selected:
            hightlightRect = QRect(boxRect.left() + self.highlight_offset,
                              boxRect.top() + self.highlight_offset,
                              boxRect.width() - self.highlight_size,
                              boxRect.height() - self.highlight_size)
            painter.setPen(self.highlightPen)
            painter.drawRect(hightlightRect)

        thumbnail = index.model().data(index, Qt.DecorationRole)
        if previously_downloaded and not checked:
            disabled = QPixmap(thumbnail.size())
            disabled.fill(Qt.transparent)
            p = QPainter(disabled)
            p.setBackgroundMode(Qt.TransparentMode)
            p.setBackground(QBrush(Qt.transparent))
            p.eraseRect(thumbnail.rect())
            p.setOpacity(self.dimmed_opacity)
            p.drawPixmap(0, 0, thumbnail)
            p.end()
            thumbnail = disabled

        thumbnail_width = thumbnail.size().width()
        thumbnail_height = thumbnail.size().height()

        thumbnailX = self.horizontal_margin + (self.image_area_size -
                                               thumbnail_width) // 2 + x
        thumbnailY = self.vertical_margin + (self.image_area_size -
                                               thumbnail_height) // 2 + y

        target = QRect(thumbnailX, thumbnailY, thumbnail_width,
                       thumbnail_height)
        source = QRect(0, 0, thumbnail_width, thumbnail_height)
        painter.drawPixmap(target, thumbnail, source)

        if previously_downloaded and not checked:
            painter.setOpacity(self.dimmed_opacity)

        if has_audio:
            audio_x = self.width // 2 - self.audioIcon.width() // 2 + x
            audio_y = self.image_frame_bottom + self.footer_padding
            painter.drawPixmap(audio_x, audio_y, self.audioIcon)

        # Draw a small coloured box containing the file extension in the
        #  bottom right corner
        extension = extension.upper()
        # Calculate size of extension text
        painter.setFont(self.emblemFont)
        rect = self.emblemFontMetrics.boundingRect(extension)  # type: QRect
        extBoundingRect = rect.marginsAdded(self.emblemMargins) # type: QRect
        text_width = self.emblemFontMetrics.width(extension)
        text_height = self.emblemFontMetrics.height()
        text_x = self.width - self.horizontal_margin - text_width - self.emblem_pad * 2 + x
        text_y = self.image_frame_bottom + self.footer_padding + text_height + y

        color = extensionColor(ext_type=ext_type)

        # Use an angular rect, because a rounded rect with anti-aliasing doesn't look too good
        rect = QRect(text_x, text_y - text_height,
                     extBoundingRect.width(), extBoundingRect.height())
        painter.fillRect(rect, color)
        painter.setPen(QColor(Qt.white))
        painter.drawText(rect, Qt.AlignCenter, extension)

        # Draw another small colored box to the left of the
        # file extension box containing a secondary
        # attribute, if it exists. Currently the secondary attribute is
        # only an XMP file, but in future it could be used to display a
        # matching jpeg in a RAW+jpeg set
        if secondary_attribute:
            extBoundingRect = self.emblemFontMetrics.boundingRect(
                secondary_attribute).marginsAdded(self.emblemMargins) # type: QRect
            text_width = self.emblemFontMetrics.width(secondary_attribute)
            text_x = text_x - text_width - self.emblem_pad * 2 - self.footer_padding
            color = QColor(self.color3)
            rect = QRect(text_x, text_y - text_height,
                         extBoundingRect.width(), extBoundingRect.height())
            painter.fillRect(rect, color)
            painter.drawText(rect, Qt.AlignCenter, secondary_attribute)

        if memory_cards:
            # if downloaded from a camera, and the camera has more than
            # one memory card, a list of numeric identifiers (i.e. 1 or
            # 2) identifying which memory card the file came from
            text_x = self.card_x + x
            for card in memory_cards:
                card = str(card)
                extBoundingRect = self.emblemFontMetrics.boundingRect(
                    card).marginsAdded(self.emblemMargins) # type: QRect
                color = QColor(70, 70, 70)
                rect = QRect(text_x, text_y - text_height,
                             extBoundingRect.width(), extBoundingRect.height())
                painter.fillRect(rect, color)
                painter.drawText(rect, Qt.AlignCenter, card)
                text_x = text_x + extBoundingRect.width() + self.footer_padding

        if previously_downloaded and not checked:
            painter.setOpacity(1.0)

        if download_status == DownloadStatus.not_downloaded:
            checkboxStyleOption = QStyleOptionButton()
            if checked:
                checkboxStyleOption.state |= QStyle.State_On
            else:
                checkboxStyleOption.state |= QStyle.State_Off
            checkboxStyleOption.state |= QStyle.State_Enabled
            checkboxStyleOption.rect = self.getCheckBoxRect(option.rect)
            QApplication.style().drawControl(QStyle.CE_CheckBox, checkboxStyleOption, painter)
        else:
            if download_status == DownloadStatus.download_pending:
                pixmap = self.downloadPendingIcon
            elif download_status == DownloadStatus.downloaded:
                pixmap = self.downloadedIcon
            elif (download_status == DownloadStatus.downloaded_with_warning or
                  download_status == DownloadStatus.backup_problem):
                pixmap = self.downloadedWarningIcon
            elif (download_status == DownloadStatus.download_failed or
                  download_status == DownloadStatus.download_and_backup_failed):
                pixmap = self.downloadedErrorIcon
            else:
                pixmap = None
            if pixmap is not None:
                painter.drawPixmap(option.rect.x() + self.horizontal_margin, text_y - text_height,
                                   pixmap)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index:  QModelIndex) -> QSize:
        return QSize(self.width + self.shadow_size, self.height
                     + self.shadow_size)

    def editorEvent(self, event: QEvent,
                    model: QAbstractItemModel,
                    option: QStyleOptionViewItem,
                    index: QModelIndex) -> bool:
        """
        Change the data in the model and the state of the checkbox
        if the user presses the left mousebutton or presses
        Key_Space or Key_Select and this cell is editable. Otherwise do nothing.
        """

        download_status = index.data(Roles.download_status)

        if (event.type() == QEvent.MouseButtonRelease or event.type() ==
            QEvent.MouseButtonDblClick):
            if event.button() == Qt.RightButton:
                self.clickedIndex = index
                globalPos = self.rapidApp.thumbnailView.viewport().mapToGlobal(event.pos())
                # libgphoto2 needs exclusive access to the camera, so there are times when "open
                # in file browswer" should be disabled:
                # First, for all desktops, when a camera, disable when thumbnailing or
                # downloading.
                # Second, disable opening MTP devices in KDE environment,
                # as KDE won't release them until them the file browser is closed!
                # However if the file is already downloaded, we don't care, as can get it from
                # local source.

                active_camera = disable_kde = False
                if download_status not in Downloaded:
                    if index.data(Roles.is_camera):
                        scan_id = index.data(Roles.scan_id)
                        active_camera = self.rapidApp.deviceState(scan_id) != DeviceState.idle
                    if not active_camera:
                        disable_kde = index.data(Roles.mtp) and get_desktop() == Desktop.kde

                self.openInFileBrowserAct.setEnabled(not (disable_kde or active_camera))
                self.contextMenu.popup(globalPos)
                return False
            if event.button() != Qt.LeftButton or not self.getCheckBoxRect(
                    option.rect).contains(event.pos()):
                return False
            if event.type() == QEvent.MouseButtonDblClick:
                return True
        elif event.type() == QEvent.KeyPress:
            if event.key() != Qt.Key_Space and event.key() != Qt.Key_Select:
                return False
        else:
            return False

        if download_status != DownloadStatus.not_downloaded:
            return False

        # Change the checkbox-state
        self.setModelData(None, model, index)
        return True

    def setModelData (self, editor: QWidget,
                      model: QAbstractItemModel,
                      index: QModelIndex) -> None:
        newValue = not (index.data(Qt.CheckStateRole) == Qt.Checked)
        proxy = self.rapidApp.thumbnailProxyModel  # type: ThumbnailSortFilterProxyModel
        thumbnailModel = self.rapidApp.thumbnailModel  # type: ThumbnailListModel
        selection = self.rapidApp.thumbnailView.selectionModel()  # type: QItemSelectionModel
        if selection.hasSelection():
            selected = selection.selection()  # type: QItemSelection
            if index in selected.indexes():
                selected = proxy.mapSelectionToSource(selected)  # type: QItemSelection
                for i in selected.indexes():
                    thumbnailModel.setData(i, newValue, Qt.CheckStateRole)
            else:
                # The user has clicked on a checkbox that for a
                # thumbnail that is outside their previous selection
                selection.clear()
                selection.select(index, QItemSelectionModel.Select)
                model.setData(index, newValue, Qt.CheckStateRole)
        else:
            # The user has previously selected nothing, so mark this
            # thumbnail as selected
            selection.select(index, QItemSelectionModel.Select)
            model.setData(index, newValue, Qt.CheckStateRole)
        thumbnailModel.updateDisplayPostDataChange()

    def getLeftPoint(self, rect: QRect) -> QPoint:
        return QPoint(rect.x() + self.horizontal_margin,
                      #rect.y() + self.emblem_bottom - self.checkbox_size)
                      rect.y() + self.image_frame_bottom + self.footer_padding - 1)

    def getCheckBoxRect(self, rect: QRect) -> QRect:
        return QRect(self.getLeftPoint(rect), self.checkboxRect.size())


class ThumbnailSortFilterProxyModel(QSortFilterProxyModel):
    def __init__(self,  parent=None) -> None:
        super().__init__(parent)
        self.proximity_rows = set()
        self.show_filter = Show.all

    def setFilterShow(self, show: Show) -> None:
        if show != self.show_filter:
            self.show_filter = show
            self.invalidateFilter()

    def filterAcceptsRow(self, sourceRow: int, sourceParent: QModelIndex) -> bool:
        if self.show_filter == Show.new_only:
            index = self.sourceModel().index(sourceRow, 0, sourceParent)  # type: QModelIndex
            previously_downloaded = index.data(Roles.previously_downloaded)
            if previously_downloaded:
                return False
        if len(self.proximity_rows) == 0:
            return True
        return sourceRow in self.proximity_rows
