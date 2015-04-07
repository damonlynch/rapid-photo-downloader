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
from collections import (namedtuple, defaultdict)
from operator import attrgetter

from sortedcontainers import SortedListWithKey

from PyQt5.QtCore import  (QAbstractTableModel, QModelIndex, Qt, pyqtSignal,
    QThread, QTimer, QSize, QRect)
from PyQt5.QtWidgets import QListView, QStyledItemDelegate
from PyQt5.QtGui import QPixmap, QImage, QPainter, QColor, QFontMetrics

import zmq

from viewutils import RowTracker, SortedListItem
from rpdfile import RPDFile
from interprocess import (PublishPullPipelineManager,
    GenerateThumbnailsArguments, Device, GenerateThumbnailsResults)
from constants import (DownloadStatus, Downloaded, FileType, ThumbnailSize)
from storage import get_program_cache_directory
from utilities import (CacheDirs)

class DownloadTypes:
    def __init__(self):
        self.photos = False
        self.videos = False

DownloadFiles = namedtuple('DownloadFiles', ['files', 'download_types',
                                             'download_stats'])

class DownloadStats:
    def __init__(self):
        self.photos = 0
        self.videos = 0
        self.photos_size = 0
        self.videos_size = 0

class ThumbnailManager(PublishPullPipelineManager):
    message = pyqtSignal(RPDFile, QPixmap)
    cacheDirs = pyqtSignal(int, CacheDirs)
    def __init__(self, context: zmq.Context):
        super(ThumbnailManager, self).__init__(context)
        self._process_name = 'Thumbnail Manager'
        self._process_to_run = 'thumbnail.py'

    def process_sink_data(self):
        data = pickle.loads(self.content)
        """ :type : GenerateThumbnailsResults"""
        if data.rpd_file is not None:
            thumbnail = QImage.fromData(data.png_data)
            thumbnail = QPixmap.fromImage(thumbnail)
            self.message.emit(data.rpd_file, thumbnail)
        else:
            assert data.cache_dirs is not None
            self.cacheDirs.emit(data.scan_id, data.cache_dirs)


class ThumbnailTableModel(QAbstractTableModel):
    def __init__(self, parent):
        super(ThumbnailTableModel, self).__init__(parent)
        self.rapidApp = parent
        """ :type : rapid.RapidWindow"""
        self.initialize()

        self.thumbnailThread = QThread()
        self.thumbnailmq = ThumbnailManager(self.rapidApp.context)
        self.thumbnailmq.moveToThread(self.thumbnailThread)

        self.thumbnailThread.started.connect(self.thumbnailmq.run_sink)
        self.thumbnailmq.message.connect(self.thumbnailReceived)
        self.thumbnailmq.cacheDirs.connect(self.cacheDirsReceived)

        QTimer.singleShot(0, self.thumbnailThread.start)

        # self.liststore = gtk.ListStore(
        #      gobject.TYPE_PYOBJECT, # 0 PIL thumbnail
        #      gobject.TYPE_BOOLEAN,  # 1 selected or not
        #      str,                   # 2 unique id
        #      str,                   # 3 file name
        #      int,                   # 4 timestamp for sorting, converted float
        #      int,                   # 5 file type i.e. photo or video
        #      gobject.TYPE_BOOLEAN,  # 6 visibility of checkbutton
        #      int,                   # 7 status of download
        #      gtk.gdk.Pixbuf,        # 8 status icon
        #  )


        # dict of scan_pids that are having thumbnails generated
        # value is the thumbnail process id
        # this is needed when terminating thumbnailing early such as when
        # user clicks download before the thumbnailing is finished
        self.generating_thumbnails = {}

    def initialize(self):
        self.file_names = {} # type: Dict[int, str]
        self.thumbnails = {} # type: Dict[int, QPixmap]
        self.marked = set()

        self.rows = SortedListWithKey(key=attrgetter('modification_time'))
        self.scan_index = defaultdict(list)
        self.rpd_files = {}

        #FIXME change this placeholer image
        self.photo_icon = QPixmap('images/photo66.png')

        self.total_thumbs_to_generate = 0
        self.thumbnails_generated = 0
        self.no_thumbnails_by_scan = defaultdict(int)

    def rowFromUniqueId(self, unique_id: str) -> int:
        list_item = SortedListItem(unique_id,
                        self.rpd_files[unique_id].modification_time)
        return self.rows.index(list_item)

    def columnCount(self, parent=QModelIndex()):
        return 1

    def rowCount(self, parent=QModelIndex()):
        return len(self.rows)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        if row >= len(self.rows) or row < 0:
            return None
        unique_id = self.rows[row].id_value

        if role == Qt.DisplayRole:
            return self.file_names[unique_id]
        elif role == Qt.DecorationRole:
            return self.thumbnails[unique_id]


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
        assert row == self.rowFromUniqueId(unique_id)

        self.file_names[unique_id] = rpd_file.name
        self.thumbnails[unique_id] = self.photo_icon
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


    def thumbnailReceived(self, rpd_file, thumbnail):
        unique_id = rpd_file.unique_id
        self.rpd_files[unique_id] = rpd_file
        row = self.rowFromUniqueId(unique_id)
        self.thumbnails[unique_id] = thumbnail
        self.dataChanged.emit(self.index(row,0),self.index(row,0))
        self.thumbnails_generated += 1
        self.no_thumbnails_by_scan[self.rpd_files[unique_id].scan_id] -= 1
        if self.thumbnails_generated == self.total_thumbs_to_generate:
            self.resetThumbnailTrackingAndDisplay()
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

    def get_cache_locations(self) -> CacheDirs:
        photo_cache_folder = self._get_cache_location(
            self.rapidApp.prefs.photo_download_folder, is_photo_dir=True)
        video_cache_folder = self._get_cache_location(
            self.rapidApp.prefs.video_download_folder, is_photo_dir=False)
        return CacheDirs(photo_cache_folder, video_cache_folder)

    def generateThumbnails(self, scan_id: int, device: Device,
                           thumbnail_quality_lower: bool):
        """
        Initiates generation of thumbnails for the device. We already
        know which files to generate the thumbnails for.
        :param thumbnail_quality_lower: whether to generate the
        thumbnail high or low quality as it is scaled by Qt
        """
        if scan_id in self.scan_index:
            self.rapidApp.downloadProgressBar.setMaximum(
                self.total_thumbs_to_generate)
            rpd_files = list((self.rpd_files[unique_id] for unique_id in
                         self.scan_index[scan_id]))
            cache_dirs = self.get_cache_locations()

            generate_arguments = GenerateThumbnailsArguments(scan_id,
                                 rpd_files,
                                 thumbnail_quality_lower,
                                 device.name(),
                                 cache_dirs,
                                 device.camera_model,
                                 device.camera_port)
            self.thumbnailmq.add_worker(scan_id, generate_arguments)


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

    def filesAreMarkedForDownload(self) -> bool:
        """
        Checks for the presence of checkmark besides any file that has
        not yet been downloaded.
        :return: True if there is any file that the user has indicated
        they intend to download, else False.
        """
        for unique_id in self.marked:
            if self.rpd_files[unique_id].status not in Downloaded:
                return True
        return False

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
            rpd_file = self.rpd_files[unique_id]
            """ :type : rpdfile"""
            if rpd_file.status not in Downloaded:
                scan_id = rpd_file.scan_id
                files[scan_id].append(rpd_file)
                if rpd_file.file_type == FileType.photo:
                    download_types.photos = True
                    download_stats[scan_id].photos += 1
                    download_stats[scan_id].photos_size += rpd_file.size
                else:
                    download_types.videos = True
                    download_stats[scan_id].videos += 1
                    download_stats[scan_id].videos_size += rpd_file.size

        files = defaultdict(list)
        download_types = DownloadTypes()
        download_stats = defaultdict(DownloadStats)
        if scan_id is None:
            for unique_id in self.marked:
                addFile(unique_id)
        else:
            for unique_id in self.scan_index[scan_id]:
                if unique_id in self.marked:
                    addFile(unique_id)

        return DownloadFiles(files=files, download_types=download_types,
                             download_stats=download_stats)

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
                #TODO finish implementing logic to display download status

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


class ThumbnailView(QListView):
    def __init__(self):
        super(ThumbnailView, self).__init__(uniformItemSizes=True, spacing=16)
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setStyleSheet("background-color:#444444")
        # palette = self.palette()
        # palette.setColor(self.backgroundRole(), QColor(68,68,68))
        # self.setPalette(palette)


class ThumbnailDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super(ThumbnailDelegate, self).__init__(parent)
        # Thumbnail is located in a 100px square...
        self.imageAreaSize = max(ThumbnailSize.width, ThumbnailSize.height)
        # ...surrounded by a 1px frame...
        self.imageFrameBorderSize = 1
        #...which is bottom aligned
        self.imageFrameBottom = self.imageAreaSize + 2
        self.width = self.imageAreaSize + self.imageFrameBorderSize * 2
        # Allow space for text beneath the image
        self.height = self.imageAreaSize  + self.imageFrameBorderSize * 2 + 17

    def paint(self, painter: QPainter, option, index):
        if index.column() == 0:

            # Save state of painter, restore on function exit
            painter.save()

            thumbnail = index.model().data(index, Qt.DecorationRole)
            thumbnailWidth = thumbnail.size().width()
            thumbnailHeight = thumbnail.size().height()

            frameWidth = thumbnailWidth + 1
            frameHeight = thumbnailHeight + 1
            frameX = (self.width - frameWidth) // 2
            frameY = self.imageFrameBottom - frameHeight

            thumbnailX = frameX + 1
            thumbnailY = frameY + 1

            frame = QRect(frameX, frameY, frameWidth, frameHeight)
            target = QRect(thumbnailX, thumbnailY, thumbnailWidth,
                           thumbnailHeight)
            source = QRect(0, 0, thumbnailWidth, thumbnailHeight)

            # set light grey pen for border around thumbnail
            # color #a9a9a9
            painter.setPen(QColor(169,169,169))

            painter.translate(option.rect.x(), option.rect.y())
            painter.drawRect(frame)
            painter.drawPixmap(target, thumbnail, source)

            # Draw file name
            file_name = index.model().data(index, Qt.DisplayRole)

            font = painter.font()
            font.setPixelSize(11)
            painter.setFont(font)
            metrics = QFontMetrics(font)
            elided_text = metrics.elidedText(file_name, Qt.ElideRight,
                                             self.width)
            painter.setPen(QColor(Qt.white))
            painter.drawText(0, self.height, elided_text)

            painter.restore()


    def sizeHint(self, option, index):
        return QSize(self.width, self.height)