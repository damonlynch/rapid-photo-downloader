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
from typing import Optional, Dict, List, Set

from gettext import gettext as _

from sortedcontainers import (SortedListWithKey, SortedList)
import arrow.arrow
from dateutil.tz import tzlocal

from PyQt5.QtCore import  (QAbstractListModel, QModelIndex, Qt, pyqtSignal, QSize, QRect, QEvent,
                           QPoint, QMargins, QSortFilterProxyModel, QRegExp, QAbstractItemModel)
from PyQt5.QtWidgets import (QListView, QStyledItemDelegate, QStyleOptionViewItem, QApplication,
                             QStyle, QStyleOptionButton, QMenu, QWidget)
from PyQt5.QtGui import (QPixmap, QImage, QPainter, QColor, QBrush, QFontMetrics)

import zmq

from viewutils import RowTracker, SortedListItem
from rpdfile import RPDFile, FileTypeCounter
from interprocess import (PublishPullPipelineManager, GenerateThumbnailsArguments, Device,
                          GenerateThumbnailsResults)
from constants import (DownloadStatus, Downloaded, FileType, FileExtension, ThumbnailSize,
                       ThumbnailCacheStatus, Roles, DeviceType, CustomColors,
                       ThumbnailBackgroundName)
from storage import get_program_cache_directory
from utilities import (CacheDirs, make_internationalized_list, format_size_for_user, runs)
from thumbnailer import Thumbnailer


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
    def __init__(self, context: zmq.Context, logging_level: int) -> None:
        super().__init__(context, logging_level)
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
    def __init__(self, parent, logging_level: int, benchmark: Optional[int]=None) -> None:
        super().__init__(parent)
        self.rapidApp = parent

        self.benchmark = benchmark

        self.initialize()

        if benchmark is not None:
            no_workers = benchmark
        else:
            no_workers = parent.prefs.max_cpu_cores
        self.thumbnailmq = Thumbnailer(parent=parent, no_workers=no_workers,
                                       logging_level=logging_level)
        self.thumbnailmq.ready.connect(self.thumbnailerReady)
        self.thumbnailmq.thumbnailReceived.connect(self.thumbnailReceived)

        self.thumbnailmq.cacheDirs.connect(self.cacheDirsReceived)

        # dict of scan_pids that are having thumbnails generated
        # value is the thumbnail process id
        # this is needed when terminating thumbnailing early such as when
        # user clicks download before the thumbnailing is finished
        self.generating_thumbnails = {}

    def initialize(self) -> None:
        self.file_names = {} # type: Dict[int, str]
        self.thumbnails = {} # type: Dict[str, QPixmap]
        self.marked = defaultdict(set)  # type: Dict[int, Set[str]]

        # Sort thumbnails based on the time the files were modified
        self.rows = SortedListWithKey(key=attrgetter('modification_time'))
        self.scan_index = defaultdict(list)  # type: defaultdict[int, List[str]]
        self.rpd_files = {}  # type: Dict[str, RPDFile]

        self.photo_icon = QPixmap(':/photo.png')
        self.video_icon = QPixmap(':/video.png')

        self.total_thumbs_to_generate = 0
        self.thumbnails_generated = 0
        self.no_thumbnails_by_scan = defaultdict(int)

        self.thumbnailer_ready = False
        self.thumbnailer_generation_queue = []

    def rowFromUniqueId(self, unique_id: str) -> int:
        list_item = SortedListItem(unique_id,
                        self.rpd_files[unique_id].modification_time)
        return self.rows.index(list_item)

    def columnCount(self, parent: QModelIndex) -> int:
        return 1

    def rowCount(self, parent: QModelIndex) -> int:
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
            # This is never displayed, but could be used for filtering!
            return self.rows[row].modification_time
        elif role == Qt.DecorationRole:
            return self.thumbnails[unique_id]
        elif role == Qt.CheckStateRole:
            if unique_id in self.marked[rpd_file.scan_id]:
                return Qt.Checked
            else:
                return Qt.Unchecked
        elif role == Qt.ToolTipRole:
            file_name = self.file_names[unique_id]
            size = format_size_for_user(rpd_file.size)

            mtime = arrow.get(rpd_file.modification_time)
            humanized_modification_time = _(
                '%(date_time)s (%(human_readable)s)' %
                {'date_time': mtime.to('local').naive.strftime(
                    '%c'),
                 'human_readable': mtime.humanize()})

            msg = '{}\n{}\n{}'.format(file_name,
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

    def setData(self, index: QModelIndex, value, role: int) -> bool:
        if not index.isValid():
            return False

        row = index.row()
        if row >= len(self.rows) or row < 0:
            return False
        unique_id = self.rows[row].id_value
        rpd_file = self.rpd_files[unique_id]
        if role == Qt.CheckStateRole:
            self.setCheckedValue(value, unique_id, rpd_file.scan_id)
            self.dataChanged.emit(self.index(row, 0), self.index(row, 0))
            self.synchronizeDeviceDisplayCheckMark()
            self.rapidApp.displayMessageInStatusBar(update_only_marked=True)
            self.rapidApp.setDownloadActionSensitivity()
            return True
        return False

    def setCheckedValue(self, checked: bool, unique_id: str, scan_id: int) -> None:
        if checked:
            self.marked[scan_id].add(unique_id)
        else:
            self.marked[scan_id].remove(unique_id)

    def insertRows(self, position, rows=1, index=QModelIndex()):
        self.beginInsertRows(QModelIndex(), position, position + rows - 1)
        self.endInsertRows()
        return True

    def removeRows(self, position, rows=1, index=QModelIndex()):
        self.beginRemoveRows(QModelIndex(), position, position + rows - 1)
        unique_ids = [item.id_value for item in self.rows[
                                                position:position+rows]]
        del self.rows[position:position+rows]
        for unique_id in unique_ids:
            scan_id = self.rpd_files[unique_id].scan_id
            del self.file_names[unique_id]
            del self.thumbnails[unique_id]
            if unique_id in self.marked[scan_id]:
                self.marked[scan_id].remove(unique_id)
            self.scan_index[scan_id].remove(unique_id)
            del self.rpd_files[unique_id]
        self.endRemoveRows()
        return True

    def addFile(self, rpd_file: RPDFile, generate_thumbnail: bool):
        unique_id = rpd_file.unique_id
        list_item = SortedListItem(unique_id, rpd_file.modification_time)
        self.rows.add(list_item)
        row = self.rows.index(list_item)

        self.insertRow(row)

        self.rpd_files[unique_id] = rpd_file
        self.file_names[unique_id] = rpd_file.name
        if rpd_file.file_type == FileType.photo:
            self.thumbnails[unique_id] = self.photo_icon
        else:
            self.thumbnails[unique_id] = self.video_icon
        if not rpd_file.previously_downloaded():
            self.marked[rpd_file.scan_id].add(unique_id)

        self.scan_index[rpd_file.scan_id].append(unique_id)

        if generate_thumbnail:
            self.total_thumbs_to_generate += 1
            self.no_thumbnails_by_scan[rpd_file.scan_id] += 1

    def cacheDirsReceived(self, scan_id: int, cache_dirs: CacheDirs):
        if scan_id in self.rapidApp.devices:
            self.rapidApp.devices[scan_id].photo_cache_dir = \
                cache_dirs.photo_cache_dir
            self.rapidApp.devices[scan_id].video_cache_dir = \
                cache_dirs.video_cache_dir

    def thumbnailReceived(self, rpd_file: RPDFile,
                          thumbnail: Optional[QPixmap]) -> None:
        unique_id = rpd_file.unique_id
        scan_id = rpd_file.scan_id
        self.rpd_files[unique_id] = rpd_file
        if not thumbnail.isNull():
            row = self.rowFromUniqueId(unique_id)
            self.thumbnails[unique_id] = thumbnail
            self.dataChanged.emit(self.index(row,0),self.index(row,0))
        self.thumbnails_generated += 1
        self.no_thumbnails_by_scan[scan_id] -= 1
        if self.no_thumbnails_by_scan[scan_id] == 0:
            device = self.rapidApp.devices[scan_id]
            logging.debug('Finished phase 2 of thumbnail generation for %s', device.display_name)

        if self.thumbnails_generated == self.total_thumbs_to_generate:
            self.resetThumbnailTrackingAndDisplay()
            if self.benchmark is not None:
                self.rapidApp.quit()
        elif self.total_thumbs_to_generate:
            self.rapidApp.downloadProgressBar.setValue(
                self.thumbnails_generated)

    def _get_cache_location(self, download_folder: str, is_photo_dir: bool) \
                            -> str:
        if self.rapidApp.isValidDownloadDir(download_folder,
                                            is_photo_dir=is_photo_dir):
            return download_folder
        else:
            folder = get_program_cache_directory(
                create_if_not_exist=True)
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

    def thumbnailerReady(self) -> None:
        self.thumbnailer_ready = True
        if self.thumbnailer_generation_queue:
            for gen_args in self.thumbnailer_generation_queue:
                self.thumbnailmq.generateThumbnails(*gen_args)
            self.thumbnailer_generation_queue = []

    def generateThumbnails(self, scan_id: int, device: Device) -> None:
        """Initiates generation of thumbnails for the device."""

        if scan_id in self.scan_index:
            self.rapidApp.downloadProgressBar.setMaximum(
                self.total_thumbs_to_generate)
            cache_dirs = self.getCacheLocations()
            rpd_files = list((self.rpd_files[unique_id] for unique_id in
                         self.scan_index[scan_id]))

            gen_args = (scan_id, rpd_files, device.name(),
                        cache_dirs, device.camera_model, device.camera_port)
            if not self.thumbnailer_ready:
                self.thumbnailer_generation_queue.append(gen_args)
            else:
                self.thumbnailmq.generateThumbnails(*gen_args)

    def resetThumbnailTrackingAndDisplay(self):
        self.rapidApp.downloadProgressBar.reset()
        # self.rapid_app.download_progressbar.set_text('')
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
        :return: True if any row was removed, else False
        """
        if scan_id is None and not keep_downloaded_files:
            self.initialize()
            return True
        else:
            assert scan_id is not None
            # Generate list of thumbnails to remove
            if keep_downloaded_files:
                rows = [self.rowFromUniqueId(unique_id)
                        for unique_id in self.scan_index[scan_id]
                        if not self.rpd_files[unique_id].status in Downloaded]
            else:
                rows = [self.rowFromUniqueId(unique_id)
                        for unique_id in self.scan_index[scan_id]]

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
            self.rapidApp.displayMessageInStatusBar(update_only_marked=True)

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
            return len(self.marked[scan_id]) > 0
        else:
            for scan_id in self.marked:
                if len(self.marked[scan_id]) > 0:
                    return True
        return False

    def getNoFilesMarkedForDownload(self) -> int:
        return sum((len(self.marked[scan_id]) for scan_id in self.marked))

    def getSizeOfFilesMarkedForDownload(self) -> int:
        return sum(self.rpd_files[unique_id].size for scan_id in self.marked for unique_id in
             self.marked[scan_id])
        # size = 0
        # for unique_id in self.marked:
        #     size += self.rpd_files[unique_id].size
        # return size

    def getNoFilesAvailableForDownload(self) -> FileTypeCounter:
        return FileTypeCounter(rpd_file.file_type for rpd_file in self.rpd_files.values() if
                                rpd_file.status == DownloadStatus.not_downloaded)
        # file_type_counter = FileTypeCounter()
        # for unique_id, rpd_file in self.rpd_files.items():
        #     if rpd_file.status == DownloadStatus.not_downloaded:
        #         file_type_counter[rpd_file.file_type] += 1
        # return file_type_counter

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
            unique_ids = self.marked[scan_id]
        else:
            unique_ids = chain.from_iterable((self.marked.values()))

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
                # TODO check to see if this code should be update given can now
                # read orientation from most cameras
                if ((rpd_file.thumbnail_status !=
                        ThumbnailCacheStatus.suitable_for_fdo_cache_write) or
                        (generating_fdo_thumbs and not
                             rpd_file.fdo_thumbnail_256_name)):
                    download_stats[scan_id].post_download_thumb_generation += 1

        return DownloadFiles(files=files, download_types=download_types,
                             download_stats=download_stats,
                             camera_access_needed=camera_access_needed)

    def markDownloadPending(self, files):
        """
        Sets status to download pending and updates thumbnails display

        :param files: rpd_files by scan
        :type files: defaultdict(int, List[rpd_file])
        """
        for scan_id in files:
            for rpd_file in files[scan_id]:
                unique_id = rpd_file.unique_id
                self.rpd_files[unique_id].status = DownloadStatus.download_pending
                self.marked[scan_id].remove(unique_id)
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

    def getNoFilesRemaining(self, scan_id: int=None) -> int:
        """
        :param scan_id: if None, returns files remaining to be
         downloaded for all scan_ids, else only for that scan_id.
        :return the number of files that have not yet been downloaded
        """

        i = 0
        if scan_id is not None:
            for unique_id in self.scan_index[scan_id]:
                if self.rpd_files[unique_id].status == DownloadStatus.not_downloaded:
                    i += 1
        else:
            for rpd_file in self.rpd_files.values():
                if rpd_file.status == DownloadStatus.not_downloaded:
                    i += 1
        return i

    def uniqueIdsByStatus(self, download_status: DownloadStatus,
                          scan_id: Optional[int]=None):
        if scan_id is not None:
            return (unique_id for unique_id in self.scan_index[scan_id]
                    if self.rpd_files[unique_id].status == download_status)
        else:
            return (rpd_file.unique_id for rpd_file in self.rpd_files.values()
                    if rpd_file.status == download_status)

    def uniqueIdsByStatusAndType(self, download_status: DownloadStatus,
                                 file_type: FileType,
                                 scan_id: Optional[int]=None):
        if scan_id is not None:
            return (unique_id for unique_id in self.scan_index[scan_id]
                    if self.rpd_files[unique_id].status == download_status and
                    self.rpd_files[unique_id].file_type == file_type)
        else:
            return (rpd_file.unique_id for rpd_file in self.rpd_files.values()
                    if rpd_file.status == download_status and
                    rpd_file.file_type == file_type)

    def checkAll(self, check_all: bool,
                 file_type: Optional[FileType]=None,
                 scan_id: Optional[int]=None) -> None:
        """
        Check or uncheck all files that are not downloaded.

        :param check_all: if True, mark as checked, else unmark
        :param file_type: if specified, files must be of specified type
        :param scan_id: if specified, affects only files for that scan
        """

        rows = SortedList()

        # Optimize this code as much as possible, because it's time
        # sensitive. Sure looks ugly, though.
        if check_all:
            if scan_id is not None:
                if file_type is None:
                    unique_ids = (unique_id for unique_id in self.scan_index[scan_id]
                        if self.rpd_files[unique_id].status == DownloadStatus.not_downloaded and
                            unique_id not in self.marked[scan_id])
                else:
                    unique_ids = (unique_id for unique_id in self.scan_index[scan_id]
                        if self.rpd_files[unique_id].status == DownloadStatus.not_downloaded and
                            unique_id not in self.marked[scan_id] and
                            self.rpd_files[unique_id].file_type == file_type)
                for unique_id in unique_ids:
                    row = self.rowFromUniqueId(unique_id)
                    rows.add(row)
                    self.marked[scan_id].add(unique_id)
            else:
                if file_type is None:
                    unique_ids = self.uniqueIdsByStatus(DownloadStatus.not_downloaded, scan_id)
                else:
                    unique_ids = self.uniqueIdsByStatusAndType(DownloadStatus.not_downloaded,
                                                               file_type, scan_id)
                for unique_id in unique_ids:
                    rpd_file = self.rpd_files[unique_id]
                    scan_id2 = rpd_file.scan_id
                    if unique_id not in self.marked[scan_id2]:
                        row = self.rowFromUniqueId(unique_id)
                        rows.add(row)
                        self.marked[scan_id2].add(unique_id)
        else:
            # uncheck all
            if file_type is None:
                if scan_id is not None:
                    for unique_id in self.marked[scan_id]:
                        row = self.rowFromUniqueId(unique_id)
                        rows.add(row)
                    self.marked[scan_id] = set()
                else:
                    unique_ids = chain.from_iterable((self.marked.values()))
                    for unique_id in unique_ids:
                        row = self.rowFromUniqueId(unique_id)
                        rows.add(row)
                    self.marked = defaultdict(set)  # type: Dict[int, Set[str]]
            else:
                # file_type is specified
                if scan_id is not None:
                    for unique_id in self.marked[scan_id]:
                        if self.rpd_files[unique_id].file_type == file_type:
                            row = self.rowFromUniqueId(unique_id)
                            rows.add(row)
                            self.marked[scan_id].remove(unique_id)
                else:
                    unique_ids = chain.from_iterable((self.marked.values()))
                    for unique_id in unique_ids:
                        if self.rpd_files[unique_id].file_type == file_type:
                            row = self.rowFromUniqueId(unique_id)
                            rows.add(row)
                            self.marked[scan_id].remove(unique_id)

        for first, last in runs(rows):
            self.dataChanged.emit(self.index(first, 0), self.index(last, 0))

        self.synchronizeDeviceDisplayCheckMark()
        self.rapidApp.displayMessageInStatusBar(update_only_marked=True)
        self.rapidApp.setDownloadActionSensitivity()

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
    
    def synchronizeDeviceDisplayCheckMark(self):
        for scan_id in self.scan_index:
            can_download = self.filesAreMarkedForDownload(scan_id)
            self.rapidApp.mapModel(scan_id).setCheckedValue(can_download, scan_id)

    def terminateThumbnailGeneration(self, scan_id: int) -> bool:
        """
        Terminates thumbnail generation if thumbnails are currently
        being generated for this scan_id
        :return True if thumbnail generation had to be terminated, else
        False
        """

        manager = self.thumbnailmq.thumbnail_manager

        terminated = scan_id in manager
        if terminated:
            no_workers = len(manager)
            manager.stop_worker(scan_id)
            if no_workers == 1:
                # Don't be fooled: the number of workers will become zero
                # momentarily!
                self.resetThumbnailTrackingAndDisplay()
            else:
                # Recalculate the percentages for the toolbar
                self.total_thumbs_to_generate -= self.no_thumbnails_by_scan[
                    scan_id]
                self.rapidApp.downloadProgressBar.setMaximum(
                    self.total_thumbs_to_generate)
                del self.no_thumbnails_by_scan[scan_id]
        return terminated

    def updateStatusPostDownload(self, rpd_file: RPDFile):
        unique_id = rpd_file.unique_id
        self.rpd_files[unique_id] = rpd_file
        row = self.rowFromUniqueId(rpd_file.unique_id)
        self.dataChanged.emit(self.index(row,0),self.index(row,0))

    def filesRemainToDownload(self) -> bool:
        """
        :return True if any files remain that are not downloaded, else
         returns False
        """
        for rpd_file in self.rpd_files:
            if rpd_file.status == DownloadStatus.not_downloaded:
                return True
        return False


class ThumbnailView(QListView):
    def __init__(self) -> None:
        style = """QAbstractScrollArea { background-color: %s;}""" % ThumbnailBackgroundName
        super().__init__()
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setStyleSheet(style)
        self.setUniformItemSizes(True)
        self.setSpacing(8)


class ThumbnailDelegate(QStyledItemDelegate):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

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

        self.color1 = QColor(CustomColors.color1.value)
        self.color2 = QColor(CustomColors.color2.value)
        self.color3 = QColor(CustomColors.color3.value)
        self.color4 = QColor(CustomColors.color4.value)
        self.color5 = QColor(CustomColors.color5.value)

        self.lightGray = QColor(221,221,221)
        self.darkGray = QColor(51, 51, 51)


    def doCopyPathAction(self) -> None:
        index = self.clickedIndex
        if index:
            path = index.model().data(index, Roles.path)
            QApplication.clipboard().setText(path)

    def doOpenInFileBrowserAct(self) -> None:
        index = self.clickedIndex
        if index:
            uri = index.model().data(index, Roles.uri)
            cmd = '{} {}'.format(self.parent().file_manager, uri)
            logging.debug("Launching: %s", cmd)
            args = shlex.split(cmd)
            subprocess.Popen(args)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        if index.column() == 0:

            # Save state of painter, restore on function exit
            painter.save()

            # Get data about the file
            model = index.model()
            checked = model.data(index, Qt.CheckStateRole) == Qt.Checked
            previously_downloaded = model.data(
                index, Roles.previously_downloaded)
            extension, ext_type = model.data(index, Roles.extension)
            download_status = model.data(index, Roles.download_status) # type: DownloadStatus
            has_audio = model.data(index, Roles.has_audio)
            secondary_attribute = model.data(index, Roles.secondary_attribute)
            memory_cards = model.data(index, Roles.camera_memory_card) # type: List[int]

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
            text_padding = 3
            font = painter.font()
            font.setPixelSize(9)
            painter.setFont(font)
            metrics = QFontMetrics(font)
            extBoundingRect = metrics.boundingRect(extension).marginsAdded(
                QMargins(text_padding, 0, text_padding, text_padding)) # type: QRect
            text_width = metrics.width(extension)
            text_height = metrics.height()
            text_x = self.width - self.horizontal_margin - text_width - \
                     text_padding * 2 + x
            text_y = self.image_frame_bottom + self.footer_padding + \
                     text_height + y

            if ext_type == FileExtension.raw:
                color = self.color1
            elif ext_type == FileExtension.jpeg:
                color = self.color4
            elif ext_type == FileExtension.other_photo:
                color = self.color5
            elif ext_type == FileExtension.video:
                color = self.color2
            else:
                color = QColor(0, 0, 0)

            painter.fillRect(text_x, text_y - text_height,
                             extBoundingRect.width(),
                             extBoundingRect.height(),
                             color)

            painter.setPen(QColor(Qt.white))
            painter.drawText(text_x + text_padding, text_y - 1,
                             extension)

            # Draw another small colored box to the left of the
            # file extension box containing a secondary
            # attribute, if it exists. Currently the secondary attribute is
            # only an XMP file, but in future it could be used to display a
            # matching jpeg in a RAW+jpeg set
            if secondary_attribute:
                extBoundingRect = metrics.boundingRect(
                    secondary_attribute).marginsAdded(QMargins(text_padding, 0,
                    text_padding, text_padding)) # type: QRect
                text_width = metrics.width(secondary_attribute)
                text_x = text_x - text_width - text_padding * 2 - \
                         self.footer_padding
                color = QColor(self.color3)
                painter.fillRect(text_x, text_y - text_height,
                             extBoundingRect.width(),
                             extBoundingRect.height(),
                             color)
                painter.drawText(text_x + text_padding, text_y - 1,
                             secondary_attribute)

            if memory_cards:
                # if downloaded from a camera, and the camera has more than
                # one memory card, a list of numeric identifiers (i.e. 1 or
                # 2) identifying which memory card the file came from
                text_x = self.card_x + x
                for card in memory_cards:
                    card = str(card)
                    extBoundingRect = metrics.boundingRect(
                        card).marginsAdded(QMargins(
                        text_padding, 0, text_padding, text_padding)) # type: QRect
                    text_width = metrics.width(card)
                    color = QColor(70, 70, 70)
                    painter.fillRect(text_x, text_y - text_height,
                                 extBoundingRect.width(),
                                 extBoundingRect.height(),
                                 color)
                    painter.drawText(text_x + text_padding, text_y - 1,
                                 card)
                    text_x = text_x + extBoundingRect.width() + \
                             self.footer_padding


            if previously_downloaded and not checked:
                painter.setOpacity(1.0)

            if download_status == DownloadStatus.not_downloaded:
                checkboxStyleOption = QStyleOptionButton()
                if checked:
                    checkboxStyleOption.state |= QStyle.State_On
                else:
                    checkboxStyleOption.state |= QStyle.State_Off
                checkboxStyleOption.state |= QStyle.State_Enabled
                checkboxStyleOption.rect = self.getCheckBoxRect(option)
                QApplication.style().drawControl(QStyle.CE_CheckBox,
                                                 checkboxStyleOption, painter)
            else:
                if download_status == DownloadStatus.download_pending:
                    pixmap = self.downloadPendingIcon
                elif download_status == DownloadStatus.downloaded:
                    pixmap = self.downloadedIcon
                elif (download_status ==
                          DownloadStatus.downloaded_with_warning or
                      download_status == DownloadStatus.backup_problem):
                    pixmap = self.downloadedWarningIcon
                elif (download_status == DownloadStatus.download_failed or
                      download_status ==
                              DownloadStatus.download_and_backup_failed):
                    pixmap = self.downloadedErrorIcon
                else:
                    pixmap = None
                if pixmap is not None:
                    painter.drawPixmap(option.rect.x() +
                                       self.horizontal_margin, text_y -
                                       text_height, pixmap)

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
        # if not (index.flags() & Qt.ItemIsEditable) > 0:
        #     return False

        download_status = model.data(index, Roles.download_status)

        if (event.type() == QEvent.MouseButtonRelease or event.type() ==
            QEvent.MouseButtonDblClick):
            if event.button() == Qt.RightButton:
                self.clickedIndex = index
                globalPos = self.parent().thumbnailView.viewport().mapToGlobal(event.pos())
                self.contextMenu.popup(globalPos)
                return False
            if event.button() != Qt.LeftButton or not self.getCheckBoxRect(
                    option).contains(event.pos()):
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
        newValue = not (index.model().data(index, Qt.CheckStateRole) == Qt.Checked)
        model.setData(index, newValue, Qt.CheckStateRole)

    def getLeftPoint(self, option) -> QPoint:
        return QPoint(option.rect.x() + self.horizontal_margin,
                               option.rect.y() + self.image_frame_bottom +
                               self.footer_padding )

    def getCheckBoxRect(self, option) -> QRect:
        return QRect(self.getLeftPoint(option), self.checkboxRect.size())


class ThumbnailSortFilterProxyModel(QSortFilterProxyModel):
    def __init__(self,  parent=None) -> None:
        super().__init__(parent)
        self.selected_rows = set()

    def filterAcceptsRow(self, sourceRow: int, sourceParent: QModelIndex) -> bool:
        if len(self.selected_rows) == 0:
            return True
        return sourceRow in self.selected_rows