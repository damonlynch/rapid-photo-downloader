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

from PyQt5.QtCore import  (QAbstractTableModel, QModelIndex, Qt, pyqtSignal,
    QThread, QTimer, QSize, QRect)
from PyQt5.QtWidgets import QListView, QStyledItemDelegate
from PyQt5.QtGui import QPixmap, QImage, QPainter, QColor, QFontMetrics

from interprocess import (PublishPullPipelineManager,
    GenerateThumbnailsArguments, Device)

class ThumbnailManager(PublishPullPipelineManager):
    message = pyqtSignal(str, QPixmap)
    def __init__(self, context):
        super(ThumbnailManager, self).__init__(context)
        self._process_name = 'Thumbnail Manager'
        self._process_to_run = 'thumbnail.py'

    def process_sink_data(self):
        unique_id, thumbnail = pickle.loads(self.content)
        thumbnail = QImage.fromData(thumbnail)
        thumbnail = QPixmap.fromImage(thumbnail)
        self.message.emit(unique_id, thumbnail)


class ThumbnailTableModel(QAbstractTableModel):
    def __init__(self, parent):
        super(ThumbnailTableModel, self).__init__(parent)
        self.rapidApp = parent
        self.file_names = {} # type: Dict[int, str]
        self.thumbnails = {} # type: Dict[int, QPixmap]
        self.no_thumbmnails = 0

        self.unique_id_to_row = {}
        self.row_to_unique_id = {}
        self.scan_index = {}
        self.rpd_files = {}

        #FIXME change this placeholer image
        self.photo_icon = QPixmap('images/photo66.png')

        self.total_thumbs_to_generate = 0
        self.thumbnails_generated = 0

        self.thumbnailThread = QThread()
        self.thumbnailmq = ThumbnailManager(self.rapidApp.context)
        self.thumbnailmq.moveToThread(self.thumbnailThread)

        self.thumbnailThread.started.connect(self.thumbnailmq.run_sink)
        self.thumbnailmq.message.connect(self.thumbnailReceived)

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

    def columnCount(self, parent=QModelIndex()):
        return 1

    def rowCount(self, parent=QModelIndex()):
        return self.no_thumbmnails

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        if row >= self.no_thumbmnails or row < 0:
            return None
        if row not in self.row_to_unique_id:
            return None
        else:
            unique_id = self.row_to_unique_id[row]

        if role == Qt.DisplayRole:
            return self.file_names[unique_id]
        elif role == Qt.DecorationRole:
            return self.thumbnails[unique_id]


    def insertRows(self, position, rows=1, index=QModelIndex()):
        self.beginInsertRows(QModelIndex(), position, position + rows - 1)
        self.no_thumbmnails += 1
        self.endInsertRows()

        return True


    def removeRows(self, position, rows=1, index=QModelIndex()):
        self.beginRemoveRows(QModelIndex(), position, position + rows - 1)
        self.file_names = (self.file_names[:position] +
                      self.file_names[position + rows:])
        self.endRemoveRows()
        return True


    def addFile(self, rpd_file, generate_thumbnail):
        row = self.rowCount()
        self.insertRow(row)

        unique_id = rpd_file.unique_id
        self.unique_id_to_row[unique_id] = row
        self.row_to_unique_id[row] = unique_id
        self.rpd_files[unique_id] = rpd_file
        self.file_names[unique_id] = rpd_file.name
        self.thumbnails[unique_id] = self.photo_icon

        if rpd_file.scan_id in self.scan_index:
            self.scan_index[rpd_file.scan_id].append(unique_id)
        else:
            self.scan_index[rpd_file.scan_id] = [unique_id, ]

        if generate_thumbnail:
            self.total_thumbs_to_generate += 1

    def thumbnailReceived(self, unique_id, thumbnail):
        row = self.unique_id_to_row[unique_id]
        self.thumbnails[unique_id] = thumbnail
        self.dataChanged.emit(self.index(row,0),self.index(row,0))
        self.thumbnails_generated += 1
        if self.thumbnails_generated == self.total_thumbs_to_generate:
            self.resetThumbnailTrackingAndDisplay()
        elif self.total_thumbs_to_generate:
            self.rapidApp.downloadProgressBar.setValue(
                self.thumbnails_generated)

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

            generate_arguments = GenerateThumbnailsArguments(scan_id,
                                                     rpd_files,
                                                     thumbnail_quality_lower,
                                                     device.camera_model,
                                                     device.camera_port)
            self.thumbnailmq.add_worker(scan_id, generate_arguments)


    def resetThumbnailTrackingAndDisplay(self):
        self.rapidApp.downloadProgressBar.reset()
        # self.rapid_app.download_progressbar.set_text('')
        self.thumbnails_generated = 0
        self.total_thumbs_to_generate = 0



class ThumbnailView(QListView):
    def __init__(self):
        super(ThumbnailView, self).__init__(uniformItemSizes=True, spacing=16)
        self.setViewMode(QListView.IconMode)
        self.setStyleSheet("background-color:#444444")
        # palette = self.palette()
        # palette.setColor(self.backgroundRole(), QColor(68,68,68))
        # self.setPalette(palette)


class ThumbnailDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super(ThumbnailDelegate, self).__init__(parent)
        # Thumbnail is located in a 100px square...
        self.imageAreaSize = 100
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