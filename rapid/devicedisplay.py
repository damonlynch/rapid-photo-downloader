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

from collections import namedtuple, defaultdict

from gettext import gettext as _

from PyQt5.QtCore import (QAbstractTableModel, QModelIndex, QSize, Qt)
from PyQt5.QtWidgets import (QTableView, QStyledItemDelegate,
                             QStyleOptionViewItem, QStyleOptionProgressBar,
                             QApplication, QStyle, QAbstractItemView, QWidget)
from PyQt5.QtGui import (QPixmap, QPainter, QIcon)

from viewutils import RowTracker
from constants import DeviceState

DeviceRow = namedtuple('DeviceRow', ['icon', 'name', 'ejection'])
DEVICE, SIZE, TEXT = range(3)


class DeviceWidget(QWidget):

    def __init__(self):
        super().__init__()

    def paintEvent(self, e):
      
        painter = QPainter()
        painter.begin(self)
        painter.end()
          

class DeviceTableModel(QAbstractTableModel):
    def __init__(self, parent):
        super(DeviceTableModel, self).__init__(parent)
        self.devices = {}
        self.sizes = {}
        self.texts = {}
        self.state = {}
        self.progress = defaultdict(float)
        self.rows = RowTracker()

    def columnCount(self, parent=QModelIndex()):
        return 3

    def rowCount(self, parent=QModelIndex()):
        return len(self.rows)

    def insertRows(self, position, rows=1, index=QModelIndex()):
        self.beginInsertRows(QModelIndex(), position, position + rows - 1)
        self.endInsertRows()
        return True

    def removeRows(self, position, rows=1, index=QModelIndex()):
        self.beginRemoveRows(QModelIndex(), position, position + rows - 1)
        scan_ids = self.rows.removeRows(position, rows)
        for scan_id in scan_ids:
            del self.texts[scan_id]
            del self.devices[scan_id]
            del self.sizes[scan_id]
            del self.state[scan_id]
            if scan_id in self.progress:
                del self.progress[scan_id]
        self.endRemoveRows()
        return True

    def addDevice(self, scan_id: int, deviceIcon: QIcon, deviceName: str,
                  ejectIcon: QPixmap) -> None:
        row = self.rowCount()
        self.insertRow(row)

        self.devices[scan_id] = DeviceRow(deviceIcon, deviceName, ejectIcon)
        self.sizes[scan_id] = _('0GB')
        self.texts[scan_id] = _('scanning...')
        self.state[scan_id] = DeviceState.scanning
        self.rows[row] = scan_id

    def removeDevice(self, scan_id: int):
        row = self.rows.row(scan_id)
        self.removeRows(row)

    def updateDeviceScan(self, scan_id: int, textToDisplay: str, size=None,
                         scan_completed=False):
        self.texts[scan_id] = textToDisplay
        if size is not None:
            self.sizes[scan_id] = size
            column = 1
        else:
            column = 2
        if scan_completed:
            self.state[scan_id] = DeviceState.scanned
        row = self.rows.row(scan_id)
        self.dataChanged.emit(self.index(row, column), self.index(row, 2))

    def updateDownloadProgress(self, scan_id: int, percent_complete: float,
                               progress_bar_text: str):
        self.state[scan_id] = DeviceState.downloading
        if percent_complete:
            self.progress[scan_id] = percent_complete
        if progress_bar_text:
            self.texts[scan_id] = progress_bar_text
        row = self.rows.row(scan_id)
        column = 2
        self.dataChanged.emit(self.index(row, column), self.index(row, 2))

    def data(self, index: QModelIndex, role=Qt.DisplayRole):

        if not index.isValid():
            return None

        row = index.row()
        if row >= len(self.rows) or row < 0:
            return None
        if row not in self.rows:
            return None
        elif role == Qt.DisplayRole:
            scan_id = self.rows[row]
            column = index.column()
            if column == DEVICE:
                device = self.devices[scan_id] # type: DeviceRow
                return (device.icon, device.name, device.ejection)
            elif column == SIZE:
                return self.sizes[scan_id]
            else:
                assert column == TEXT
                state = self.state[scan_id]
                if state == DeviceState.downloading:
                    progress = self.progress[scan_id]
                    maximum = 100
                elif state == DeviceState.scanning:
                    progress = 0
                    maximum = 0
                elif state == DeviceState.scanned:
                    maximum = 100
                    progress = 100

                return (self.texts[scan_id], progress, maximum)
        # else:
        #     pass
        #     # print("Unknown role:", role)

class DeviceView(QTableView):
    def __init__(self):
        super(DeviceView, self).__init__()
        # Set the last column (with the progressbar) to fill the remaining
        # width
        self.horizontalHeader().setStretchLastSection(True)
        # Hide the headers
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setVisible(False)
        # Disallow the user from being able to select the table cells
        self.setSelectionMode(QAbstractItemView.NoSelection)

    def resizeColumns(self):
        for column in (DEVICE, SIZE):
            self.resizeColumnToContents(column)

class DeviceDelegate(QStyledItemDelegate):
    iconSize = 16
    padding = 2
    def __init__(self, parent=None):
        super(DeviceDelegate, self).__init__(parent)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem,
              index: QModelIndex):
        if index.column() == DEVICE:
            painter.save()

            icon, name, ejection = index.model().data(index, Qt.DisplayRole)
            assert isinstance(icon, QIcon)

            y = option.rect.y()

            height = option.rect.height()
            icon_y = round((height-self.iconSize) / 2) + y
            icon.paint(painter, self.padding, icon_y,
                       self.iconSize, self.iconSize)

            assert isinstance(name, str)
            metrics = option.fontMetrics
            width = metrics.width(name)
            painter.drawText(self.padding * 3 + self.iconSize, y,
                             width,height, Qt.AlignCenter, name)
            if ejection is not None:
                x = option.rect.width() - self.padding - self.iconSize
                ejection.paint(painter, x, icon_y, self.iconSize,
                               self.iconSize)
            painter.restore()
        elif index.column() == SIZE:
            painter.save()
            size = index.model().data(index, Qt.DisplayRole)
            painter.drawText(option.rect.x(), option.rect.y(),
                             option.rect.width()-self.padding,
                             option.rect.height(),
                             Qt.AlignRight | Qt.AlignVCenter, size)
            painter.restore()
        else:
            assert index.column() == TEXT
            painter.save()
            text, progress, maximum = index.model().data(index, Qt.DisplayRole)
            progressStyle = QStyleOptionProgressBar()
            progressStyle.state = QStyle.State_Enabled
            progressStyle.direction = QApplication.layoutDirection()
            progressStyle.rect = option.rect
            progressStyle.fontmetrics = QApplication.fontMetrics()
            progressStyle.minimum = 0
            progressStyle.maximum = maximum
            progressStyle.progress = progress
            progressStyle.text = text
            progressStyle.textAlignment = Qt.AlignCenter
            progressStyle.textVisible = True
            QApplication.style().drawControl(QStyle.CE_ProgressBar,
                                             progressStyle, painter)
            painter.restore()

    def sizeHint(self, option, index):
        metrics = option.fontMetrics
        if index.column() == DEVICE:
            icon, name, ejection = index.model().data(index, Qt.DisplayRole)
            if ejection is not None or True:
                ejectionWidth = self.padding * 2 + self.iconSize + 10
            else:
                ejectionWidth = 0
            return QSize(metrics.width(name) + self.iconSize + self.padding*4 +
                         ejectionWidth,
                         max(self.iconSize, metrics.height()) + self.padding*2)
        elif index.column() == SIZE:
            # size = index.model().data(index, Qt.DisplayRole)
            width = metrics.width('9999.9GB')
            return QSize(width, metrics.height())
        else:
            assert index.column() == TEXT
            text, progress, maximum = index.model().data(index, Qt.DisplayRole)
            return QSize(metrics.width(text), metrics.height())