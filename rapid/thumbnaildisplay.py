__author__ = 'Damon Lynch'

# Copyright (C) 2015 Damon Lynch <damonlynch@gmail.com>

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

import pickle
import os
import sys
import datetime
from collections import (namedtuple, defaultdict, Counter)
from operator import attrgetter
import subprocess
import shlex
import logging

from gettext import gettext as _

from sortedcontainers import SortedListWithKey
import arrow.arrow
from dateutil.tz import tzlocal

from PyQt5.QtCore import  (QAbstractTableModel, QModelIndex, Qt, pyqtSignal,
    QThread, QTimer, QSize, QRect, QEvent, QPoint, QMargins)
from PyQt5.QtWidgets import (QListView, QStyledItemDelegate,
                             QStyleOptionViewItem, QApplication, QStyle,
                             QStyleOptionButton, QMenu, QAction)
from PyQt5.QtGui import (QPixmap, QImage, QPainter, QColor, QPen, QBrush,
                         QFontMetrics)

import zmq

from viewutils import RowTracker, SortedListItem
from rpdfile import RPDFile, extension_type, FileTypeCounter
from interprocess import (PublishPullPipelineManager,
    GenerateThumbnailsArguments, Device, GenerateThumbnailsResults)
from constants import (DownloadStatus, Downloaded, FileType, FileExtension,
                       ThumbnailSize, ThumbnailCacheStatus, Roles, DeviceType)
from storage import get_program_cache_directory, gvfs_controls_mounts
from utilities import (CacheDirs, make_internationalized_list,
                       divide_list)
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
    def __init__(self, context: zmq.Context) -> None:
        super().__init__(context)
        self._process_name = 'Thumbnail Manager'
        self._process_to_run = 'thumbnail.py'
        self._worker_id = 0

    def process_sink_data(self) -> None:
        data = pickle.loads(self.content) # type: GenerateThumbnailsResults
        if data.rpd_file is not None:
            thumbnail = QImage.fromData(data.png_data)
            thumbnail = QPixmap.fromImage(thumbnail)
            self.message.emit(data.rpd_file, thumbnail)
        else:
            assert data.cache_dirs is not None
            self.cacheDirs.emit(data.scan_id, data.cache_dirs)

    def get_worker_id(self) -> int:
        self._worker_id += 1
        return self._worker_id


class ThumbnailTableModel(QAbstractTableModel):
    def __init__(self, parent, benchmark: int=None) -> None:
        super().__init__(parent)
        self.rapidApp = parent # type: rapid.RapidWindow

        self.benchmark = benchmark

        self.initialize()

        self.gnome_env = gvfs_controls_mounts()

        self.thumbnailThread = QThread()
        self.thumbnailmq = ThumbnailManager(self.rapidApp.context)
        self.thumbnailmq.moveToThread(self.thumbnailThread)

        self.thumbnailThread.started.connect(self.thumbnailmq.run_sink)
        self.thumbnailmq.message.connect(self.thumbnailReceived)
        self.thumbnailmq.cacheDirs.connect(self.cacheDirsReceived)

        QTimer.singleShot(0, self.thumbnailThread.start)

        # dict of scan_pids that are having thumbnails generated
        # value is the thumbnail process id
        # this is needed when terminating thumbnailing early such as when
        # user clicks download before the thumbnailing is finished
        self.generating_thumbnails = {}

    def initialize(self) -> None:
        self.file_names = {} # type: Dict[int, str]
        self.thumbnails = {} # type: Dict[int, QPixmap]
        self.marked = set()

        # Sort thumbnails based on the time the files were modified
        self.rows = SortedListWithKey(key=attrgetter('modification_time'))
        self.scan_index = defaultdict(list)
        self.rpd_files = {} # type: Dict[int, RPDFile]

        self.photo_icon = QPixmap(':/photo.png')
        self.video_icon = QPixmap(':/video.png')

        self.total_thumbs_to_generate = 0
        self.thumbnails_generated = 0
        self.no_thumbnails_by_scan = defaultdict(int)

    def rowFromUniqueId(self, unique_id: str) -> int:
        list_item = SortedListItem(unique_id,
                        self.rpd_files[unique_id].modification_time)
        return self.rows.index(list_item)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 1

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self.rows)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        if row >= len(self.rows) or row < 0:
            return None
        unique_id = self.rows[row].id_value
        rpd_file = self.rpd_files[unique_id]
        """:type : RPDFile"""

        if role == Qt.DisplayRole:
            # This is never displayed, but it is used for filtering!
            return unique_id
        elif role == Qt.DecorationRole:
            return self.thumbnails[unique_id]
        elif role == Qt.CheckStateRole:
            if unique_id in self.marked:
                return Qt.Checked
            else:
                return Qt.Unchecked
        elif role == Qt.ToolTipRole:
            file_name = self.file_names[unique_id]
            size = self.rapidApp.formatSizeForUser(rpd_file.size)

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
            return rpd_file.extension
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
            return rpd_file.get_uri(gnomify_output=self.gnome_env)
        elif role == Roles.camera_memory_card:
            return rpd_file.camera_memory_card_identifiers

    def setData(self, index: QModelIndex, value, role: int):
        if not index.isValid():
            return False

        row = index.row()
        if row >= len(self.rows) or row < 0:
            return False
        unique_id = self.rows[row].id_value
        rpd_file = self.rpd_files[unique_id]
        if role == Qt.CheckStateRole:
            self.setCheckedValue(value, unique_id, row)
            self.rapidApp.displayMessageInStatusBar(update_only_marked=True)
            self.rapidApp.setDownloadActionSensitivity()
            return True
        return False

    def setCheckedValue(self, checked: bool, unique_id: str, row: int):
        if checked:
            self.marked.add(unique_id)
        else:
            self.marked.remove(unique_id)
        self.dataChanged.emit(self.index(row,0),self.index(row,0))

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
            del self.file_names[unique_id]
            del self.thumbnails[unique_id]
            if unique_id in self.marked:
                self.marked.remove(unique_id)
            scan_id = self.rpd_files[unique_id].scan_id
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
            self.marked.add(unique_id)

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

    def thumbnailReceived(self, rpd_file: RPDFile, thumbnail: QPixmap) -> None:
        unique_id = rpd_file.unique_id
        self.rpd_files[unique_id] = rpd_file
        row = self.rowFromUniqueId(unique_id)
        self.thumbnails[unique_id] = thumbnail
        self.dataChanged.emit(self.index(row,0),self.index(row,0))
        self.thumbnails_generated += 1
        self.no_thumbnails_by_scan[self.rpd_files[unique_id].scan_id] -= 1

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

    def getNoCPUsToGenerateThumbnails(self, scan_id: int) -> int:
        """
        Determine the number of CPUs that should be used to generate
        thumbnails for the device associated with this scan_id. To make
        life easier, assume that the number of devices being scanned
        will take the same amount of time to generate their thumbnails.
        We don't know that of course, and we can't know it, because some
        devices will not have finished being scanned.
        Note: if too many processes are generating thumbnails, the main
        process can become overwhelmed, and the GUI unresponsive.
        :param scan_id: the scan id of the device in question
        :return: the number of processes to assign
        """
        return 1
        device = self.rapidApp.devices[scan_id]

        # Cameras can use only one CPU, as only one process can access
        # camera contents
        if device.device_type == DeviceType.camera:
            return 1

        if self.benchmark is not None:
            return self.benchmark

        no_cameras = len(self.rapidApp.devices.cameras)
        no_non_camera_devices = len(self.rapidApp.devices) - no_cameras

        return max(1, self.rapidApp.prefs.max_cpu_cores //
                   no_non_camera_devices)

    def generateThumbnails(self, scan_id: int, device: Device,
                           thumbnail_quality_lower: bool):
        """
        Initiates generation of thumbnails for the device. We already
        know which files to generate the thumbnails for.
        :param thumbnail_quality_lower: whether to generate the
        thumbnail high or low quality as it is scaled by Qt
        """


        if scan_id in self.scan_index:
            cpus = self.getNoCPUsToGenerateThumbnails(scan_id)
            logging.debug("Will use %s logical CPUs to generate thumbnails "
                          "for %s",
                          cpus, self.rapidApp.devices[scan_id].name())

            self.rapidApp.downloadProgressBar.setMaximum(
                self.total_thumbs_to_generate)
            cache_dirs = self.getCacheLocations()
            rpd_files = list((self.rpd_files[unique_id] for unique_id in
                         self.scan_index[scan_id]))
            if cpus > 1 and len(rpd_files) > 500:
                rpd_file_slices = divide_list(rpd_files, cpus)
            else:
                rpd_file_slices = [rpd_files]

            for chunk in rpd_file_slices:
                worker_id = self.thumbnailmq.get_worker_id()

                generate_arguments = GenerateThumbnailsArguments(
                                     scan_id=scan_id,
                                     rpd_files=chunk,
                                     thumbnail_quality_lower=thumbnail_quality_lower,
                                     name=device.name(),
                                     cache_dirs=cache_dirs,
                                     camera=device.camera_model,
                                     port=device.camera_port,
                                     frontend_port=0)
                self.thumbnailmq.start_worker(worker_id, generate_arguments)

    def resetThumbnailTrackingAndDisplay(self):
        self.rapidApp.downloadProgressBar.reset()
        # self.rapid_app.download_progressbar.set_text('')
        self.thumbnails_generated = 0
        self.total_thumbs_to_generate = 0

    def clearAll(self, scan_id=None, keep_downloaded_files=False):
        """
        Removes files from display and internal tracking.

        If scan_id is not None, then only files matching that scan_id
        will be removed. Otherwise, everything will be removed.

        If keep_downloaded_files is True, files will not be removed if
        they have been downloaded.

        :param scan_id: if None, keep_downloaded_files must be False
        :type scan_id: int
        """
        if scan_id is None and not keep_downloaded_files:
            self.initialize()
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

    def filesAreMarkedForDownload(self) -> bool:
        """
        Checks for the presence of checkmark besides any file that has
        not yet been downloaded.
        :return: True if there is any file that the user has indicated
        they intend to download, else False.
        """
        return len(self.marked) > 0

    def getNoFilesMarkedForDownload(self) -> int:
        return len(self.marked)

    def getSizeOfFilesMarkedForDownload(self) -> int:
        size = 0
        for unique_id in self.marked:
            size += self.rpd_files[unique_id].size
        return size

    def getNoFilesAvailableForDownload(self) -> FileTypeCounter:
        file_type_counter = FileTypeCounter()
        for unique_id, rpd_file in self.rpd_files.items():
            if rpd_file.status == DownloadStatus.not_downloaded:
                file_type_counter[rpd_file.file_type] += 1
        return file_type_counter

    def getFilesMarkedForDownload(self, scan_id) -> DownloadFiles:
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

        def addFile(unique_id):
            rpd_file = self.rpd_files[unique_id] # type: RPDFile
            if rpd_file.status not in Downloaded:
                scan_id = rpd_file.scan_id
                files[scan_id].append(rpd_file)
                if rpd_file.file_type == FileType.photo:
                    download_types.photos = True
                    download_stats[scan_id].no_photos += 1
                    download_stats[scan_id].photos_size_in_bytes += \
                        rpd_file.size
                else:
                    download_types.videos = True
                    download_stats[scan_id].no_videos += 1
                    download_stats[scan_id].videos_size_in_bytes += \
                        rpd_file.size
                if rpd_file.from_camera and not rpd_file.cache_full_file_name:
                    camera_access_needed[scan_id] = True

                # Need to generate a thumbnail after a file has been renamed
                # if large FDO Cache thumbnail does not exist or if the
                # existing thumbnail has been marked as not suitable for the
                # FDO Cache (e.g. if we don't know the correct orientation).
                if ((rpd_file.thumbnail_status !=
                        ThumbnailCacheStatus.suitable_for_fdo_cache_write) or
                        (generating_fdo_thumbs and not
                             rpd_file.fdo_thumbnail_256_name)):
                    download_stats[scan_id].post_download_thumb_generation += 1

        files = defaultdict(list)
        download_types = DownloadTypes()
        download_stats = defaultdict(DownloadStats)
        camera_access_needed = defaultdict(bool)
        generating_fdo_thumbs = self.rapidApp.prefs.save_fdo_thumbnails
        if scan_id is None:
            for unique_id in self.marked:
                addFile(unique_id)
        else:
            for unique_id in self.scan_index[scan_id]:
                if unique_id in self.marked:
                    addFile(unique_id)

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
                self.rpd_files[unique_id].status = \
                    DownloadStatus.download_pending
                self.marked.remove(unique_id)
                row = self.rowFromUniqueId(unique_id)
                self.dataChanged.emit(self.index(row,0),self.index(row,0))


    def markThumbnailsNeeded(self, rpd_files) -> bool:
        """
        Analyzes the files that will be downloaded, and sees if any of
        them still need to have their thumbnails generated.
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
                if self.rpd_files[unique_id].status == \
                        DownloadStatus.not_downloaded:
                    i += 1
        else:
            for unique_id, rpd_file in self.rpd_files.items():
                if rpd_file.status == DownloadStatus.not_downloaded:
                    i += 1
        return i

    def checkAll(self, check_all: bool, file_type: FileType=None):
        for unique_id, rpd_file in self.rpd_files.items():
            if (rpd_file.status == DownloadStatus.not_downloaded and
                    ((check_all and unique_id not in self.marked) or
                     (not check_all and unique_id in self.marked)) and (
                      file_type is None or rpd_file.file_type==file_type)):
                row = self.rowFromUniqueId(unique_id)
                self.setCheckedValue(check_all, unique_id, row)

        self.rapidApp.displayMessageInStatusBar(update_only_marked=True)
        self.rapidApp.setDownloadActionSensitivity()

    def terminateThumbnailGeneration(self, scan_id: int) -> bool:
        """
        Terminates thumbnail generation if thumbnails are currently
        being generated for this scan_id
        :return True if thumbnail generation had to be terminated, else
        False
        """

        terminated = scan_id in self.thumbnailmq
        if terminated:
            no_workers = len(self.thumbnailmq)
            self.thumbnailmq.stop_worker(scan_id)
            if no_workers == 1:
                # Don't be fooled: the number of workers will become zero
                # momentarily!
                self.resetThumbnailTrackingAndDisplay()
            else:
                #Recalculate the percentages for the toolbar
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
    def __init__(self):
        style = """
        QListView {
        background-color:#555555; padding-left: 4px; padding-top: 4px;
        padding-bottom: 4px;
        }
        """
        super().__init__()
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setStyleSheet(style)
        self.setUniformItemSizes(True)


class ThumbnailDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
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

        self.padding = 4
        self.width = self.image_width + self.horizontal_margin * 2
        self.height = self.image_height + self.footer_padding \
                      + self.image_footer + self.vertical_margin * 2

        # Thumbnail is located in a 160px square...
        self.image_area_size = max(ThumbnailSize.width, ThumbnailSize.height)
        self.image_frame_bottom = self.vertical_margin + self.image_area_size

        self.contextMenu = QMenu()
        self.openInFileBrowserAct = self.contextMenu.addAction(
            _('Open in File Browser...'))
        self.openInFileBrowserAct.triggered.connect(
            self.doOpenInFileBrowserAct)
        self.copyPathAct = self.contextMenu.addAction(_('Copy Path'))
        self.copyPathAct.triggered.connect(self.doCopyPathAction)
        # store the index in which the user right clicked
        self.clickedIndex = None

    def doCopyPathAction(self):
        index = self.clickedIndex
        if index:
            path = index.model().data(index, Roles.path)
            QApplication.clipboard().setText(path)

    def doOpenInFileBrowserAct(self):
        index = self.clickedIndex
        if index:
            uri = index.model().data(index, Roles.uri)
            cmd = '{} {}'.format(self.parent().file_manager, uri)
            logging.debug("Launching: %s", cmd)
            args = shlex.split(cmd)
            subprocess.Popen(args)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem,
              index:  QModelIndex):
        if index.column() == 0:

            # Save state of painter, restore on function exit
            painter.save()


            # Get data about the file
            model = index.model()
            checked = model.data(index, Qt.CheckStateRole) == Qt.Checked
            previously_downloaded = model.data(
                index, Roles.previously_downloaded)
            extension = model.data(index, Roles.extension)
            """:type :str"""
            ext_type = extension_type(extension)
            download_status = model.data(index, Roles.download_status)
            """:type :DownloadStatus"""
            has_audio = model.data(index, Roles.has_audio)
            secondary_attribute = model.data(index, Roles.secondary_attribute)
            memory_cards = model.data(index, Roles.camera_memory_card)
            """:type : List[int] """

            x = option.rect.x() + self.padding
            y = option.rect.y() + self.padding

            # Draw recentangle in which the individual items will be placed
            boxRect = QRect(x, y, self.width, self.height)
            shadowRect = QRect(x + self.padding / 2, y + self.padding / 2,
                               self.width, self.height)

            lightGray = QColor(221,221,221)
            darkGray = QColor(51, 51, 51)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(darkGray)
            painter.fillRect(shadowRect, darkGray)
            painter.drawRect(shadowRect)
            painter.setRenderHint(QPainter.Antialiasing, False)
            painter.fillRect(boxRect, lightGray)

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
                QMargins(text_padding, 0, text_padding, text_padding))
            """:type : QRect"""
            text_width = metrics.width(extension)
            text_height = metrics.height()
            text_x = self.width - self.horizontal_margin - text_width - \
                     text_padding * 2 + x
            text_y = self.image_frame_bottom + self.footer_padding + \
                     text_height + y

            if ext_type == FileExtension.raw:
                color = QColor(Qt.darkBlue)
            elif ext_type == FileExtension.jpeg:
                color = QColor(Qt.darkRed)
            elif ext_type == FileExtension.other_photo:
                color = QColor(Qt.darkMagenta)
            elif ext_type == FileExtension.video:
                color = QColor(0, 77, 0)
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
                    text_padding, text_padding))
                """:type : QRect"""
                text_width = metrics.width(secondary_attribute)
                text_x = text_x - text_width - text_padding * 2 - \
                         self.footer_padding
                color = QColor(Qt.darkCyan)
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
                        text_padding, 0, text_padding, text_padding))
                    """:type : QRect"""
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

    def sizeHint(self, option, index):
        return QSize(self.width + self.padding * 2, self.height
                     + self.padding * 2)

    def editorEvent(self, event, model, option, index):
        '''
        Change the data in the model and the state of the checkbox
        if the user presses the left mousebutton or presses
        Key_Space or Key_Select and this cell is editable. Otherwise do nothing.
        '''
        # if not (index.flags() & Qt.ItemIsEditable) > 0:
        #     return False

        download_status = model.data(index, Roles.download_status)

        if (event.type() == QEvent.MouseButtonRelease or event.type() ==
            QEvent.MouseButtonDblClick):
            if event.button() == Qt.RightButton:
                self.clickedIndex = index
                globalPos = self.parent().thumbnailView.viewport().mapToGlobal(
                    event.pos())
                self.contextMenu.popup(globalPos)
                return False
            if event.button() != Qt.LeftButton or not self.getCheckBoxRect(
                    option).contains(
                    event.pos()):

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

    def setModelData (self, editor, model, index):
        '''
        The user wanted to change the old state in the opposite.
        '''
        newValue = not (index.model().data(index, Qt.CheckStateRole) ==
                        Qt.Checked)
        model.setData(index, newValue, Qt.CheckStateRole)


    def getLeftPoint(self, option):
        return QPoint(option.rect.x() + self.horizontal_margin,
                               option.rect.y() + self.image_frame_bottom +
                               self.footer_padding )

    def getCheckBoxRect(self, option):
        return QRect(self.getLeftPoint(option), self.checkboxRect.size())