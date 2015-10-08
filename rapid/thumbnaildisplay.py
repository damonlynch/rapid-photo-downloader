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
import datetime
from gettext import gettext as _

from sortedcontainers import SortedListWithKey

from PyQt5.QtCore import  (QAbstractTableModel, QModelIndex, Qt, pyqtSignal,
    QThread, QTimer, QSize, QRect, QEvent, QPoint)
from PyQt5.QtWidgets import (QListView, QStyledItemDelegate,
                             QStyleOptionViewItem, QApplication, QStyle,
                             QStyleOptionButton)
from PyQt5.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QBrush

import zmq

from viewutils import RowTracker, SortedListItem
from rpdfile import RPDFile
from interprocess import (PublishPullPipelineManager,
    GenerateThumbnailsArguments, Device, GenerateThumbnailsResults)
from constants import (DownloadStatus, Downloaded, FileType, ThumbnailSize,
                       ThumbnailCacheStatus)
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
        self.no_photos = 0
        self.no_videos = 0
        self.photos_size_in_bytes = 0
        self.videos_size_in_bytes = 0
        self.post_download_thumb_generation = 0

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

        # Sort thumbnails based on the time the files were modified
        self.rows = SortedListWithKey(key=attrgetter('modification_time'))
        self.scan_index = defaultdict(list)
        self.rpd_files = {}

        self.photo_icon = QPixmap('images/photo106.png')
        self.video_icon = QPixmap('images/video106.png')

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
        rpd_file = self.rpd_files[unique_id]
        """:type : RPDFile"""

        # if role == Qt.DisplayRole:
        #     return self.file_names[unique_id]
        if role == Qt.DecorationRole:
            return self.thumbnails[unique_id]
        elif role == Qt.CheckStateRole:
            if unique_id in self.marked:
                return Qt.Checked
            else:
                return Qt.Unchecked
        elif role == Qt.ToolTipRole:
            file_name = self.file_names[unique_id]
            size = self.rapidApp.formatSizeForUser(rpd_file.size)
            modification_time = datetime.datetime.fromtimestamp(
                rpd_file.modification_time)
            modification_time = modification_time.strftime('%c')
            msg = '{}\n{}\n{}'.format(file_name, modification_time, size)
            if rpd_file.previously_downloaded():
                if isinstance(rpd_file.prev_datetime, datetime.datetime):
                    prev_date = rpd_file.prev_datetime.strftime('%c')
                else:
                    prev_date = rpd_file.prev_datetime
                path, prev_file_name = os.path.split(rpd_file.prev_full_name)
                msg += _('\n\nPrevious download:\n%(date)s\n%('
                         'filename)s''\n%(path)s') % {'date': prev_date,
                                           'filename': prev_file_name,
                                           'path': path}
            return msg
        elif role == Qt.UserRole:
            return rpd_file.previously_downloaded()

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

    def thumbnailReceived(self, rpd_file: RPDFile, thumbnail: QPixmap):
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
            self.thumbnailmq.start_worker(scan_id, generate_arguments)


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
            """ :type : RPDFile"""
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
        generating_fdo_thumbs = self.rapidApp.prefs.save_fdo_thumbnails
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

    def getNoFilesRemaining(self, scan_id: int) -> int:
        """
        :return: the number of files that have not yet been downloaded
        for the scan_id
        """
        i = 0
        for unique_id in self.scan_index[scan_id]:
            if self.rpd_files[unique_id].status == \
                    DownloadStatus.not_downloaded:
                i += 1
        return i

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
        #TODO implement download status update
        pass
        # iter = self.get_iter_from_unique_id(rpd_file.unique_id)
        # self.liststore.set_value(iter, self.DOWNLOAD_STATUS_COL, rpd_file.status)
        # icon = self.get_status_icon(rpd_file.status)
        # self.liststore.set_value(iter, self.STATUS_ICON_COL, icon)
        # self.liststore.set_value(iter, self.CHECKBUTTON_VISIBLE_COL, False)
        # self.rpd_files[rpd_file.unique_id] = rpd_file

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
        super(ThumbnailView, self).__init__()
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setStyleSheet("QListView {background-color:#444444;}")
        # self.setGridSize(QSize(250, 200))
        self.setUniformItemSizes(True)
        # self.setSpacing(16)
        # palette = self.palette()
        # palette.setColor(self.backgroundRole(), QColor(68,68,68))
        # self.setPalette(palette)


class ThumbnailDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super(ThumbnailDelegate, self).__init__(parent)

        self.checkboxStyleOption = QStyleOptionButton()
        self.checkboxRect = QApplication.style().subElementRect(
            QStyle.SE_CheckBoxIndicator, self.checkboxStyleOption, None)
        self.checkboxSize = self.checkboxRect.size().height()

        self.imageWidth = max(ThumbnailSize.width, ThumbnailSize.height)
        self.imageHeight = max(ThumbnailSize.width, ThumbnailSize.height)
        self.horizontalSpacing = 10
        self.verticalSpacing = 10
        self.imageFooter = self.checkboxSize
        self.footerPadding = 5

        self.width = self.imageWidth + self.horizontalSpacing * 2
        self.height = self.imageHeight + self.footerPadding \
                      + self.imageFooter + \
            self.verticalSpacing * 2

        # Thumbnail is located in a 160px square...
        self.imageAreaSize = max(ThumbnailSize.width, ThumbnailSize.height)
        # ...surrounded by a 1px frame...
        self.imageFrameBorderSize = 1
        #...which is bottom aligned
        self.imageFrameBottom = self.imageAreaSize + 2 + self.verticalSpacing


    def paint(self, painter: QPainter, option: QStyleOptionViewItem ,
              index:  QModelIndex):
        if index.column() == 0:

            # Save state of painter, restore on function exit
            painter.save()

            x = option.rect.x()
            y = option.rect.y()

            checked = index.model().data(index, Qt.CheckStateRole) == \
                      Qt.Checked
            previously_downloaded = index.model().data(index, Qt.UserRole)

            thumbnail = index.model().data(index, Qt.DecorationRole)
            if previously_downloaded and not checked:
                disabled = QPixmap(thumbnail.size())
                disabled.fill(Qt.transparent)
                p = QPainter(disabled)
                p.setBackgroundMode(Qt.TransparentMode)
                p.setBackground(QBrush(Qt.transparent))
                p.eraseRect(thumbnail.rect())
                p.setOpacity(0.3)
                p.drawPixmap(0, 0, thumbnail)
                p.end()
                thumbnail = disabled

            thumbnailWidth = thumbnail.size().width()
            thumbnailHeight = thumbnail.size().height()

            frameWidth = thumbnailWidth + 1
            frameHeight = thumbnailHeight + 1
            frameX = (self.width - frameWidth) // 2 + x
            frameY = self.imageFrameBottom - frameHeight + y

            thumbnailX = frameX + 1
            thumbnailY = frameY + 1

            frame = QRect(frameX, frameY, frameWidth, frameHeight)
            target = QRect(thumbnailX, thumbnailY, thumbnailWidth,
                           thumbnailHeight)
            source = QRect(0, 0, thumbnailWidth, thumbnailHeight)

            # set light grey pen for border around thumbnail
            # color #a9a9a9
            painter.setPen(QColor(169,169,169))

            painter.drawRect(frame)
            painter.drawPixmap(target, thumbnail, source)

            checkboxStyleOption = QStyleOptionButton()
            if checked:
                checkboxStyleOption.state |= QStyle.State_On
            else:
                checkboxStyleOption.state |= QStyle.State_Off
            checkboxStyleOption.state |= QStyle.State_Enabled
            checkboxStyleOption.rect = self.getCheckBoxRect(option)
            QApplication.style().drawControl(QStyle.CE_CheckBox,
                                             checkboxStyleOption, painter)

            painter.restore()


    def sizeHint(self, option, index):
        return QSize(self.width, self.height)

    def editorEvent(self, event, model, option, index):
        '''
        Change the data in the model and the state of the checkbox
        if the user presses the left mousebutton or presses
        Key_Space or Key_Select and this cell is editable. Otherwise do nothing.
        '''
        # if not (index.flags() & Qt.ItemIsEditable) > 0:
        #     return False

        # Do not change the checkbox-state
        if event.type() == QEvent.MouseButtonRelease or event.type() == QEvent.MouseButtonDblClick:
            print("Click at", event.pos())
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

        # Change the checkbox-state
        print("Got click on checkbox")
        self.setModelData(None, model, index)
        return True

    def setModelData (self, editor, model, index):
        '''
        The user wanted to change the old state in the opposite.
        '''
        newValue = not (index.model().data(index, Qt.CheckStateRole) ==
                        Qt.Checked)
        print(newValue)
        # model.setData(index, newValue, Qt.EditRole)

    def getCheckBoxRect(self, option):
        checkboxPoint = QPoint(option.rect.x() + self.horizontalSpacing,
                               option.rect.y() + self.imageFrameBottom +
                               self.footerPadding )
        return QRect(checkboxPoint, self.checkboxRect.size())