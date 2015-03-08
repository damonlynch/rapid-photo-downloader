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

from collections import namedtuple

from PyQt5.QtCore import (QAbstractTableModel, QModelIndex, QSize, Qt)
from PyQt5.QtWidgets import (QTableView, QStyledItemDelegate,
                             QStyleOptionViewItem, QStyleOptionProgressBar,
                             QApplication, QStyle)
from PyQt5.QtGui import (QPixmap, QPainter, QIcon)

DeviceRow = namedtuple('DeviceRow', ['icon', 'name', 'ejection', 'size',
                                     'text'])
DEVICE, SIZE, TEXT = range(3)

class DeviceTableModel(QAbstractTableModel):
    def __init__(self, parent):
        super(DeviceTableModel, self).__init__(parent)
        # device icon & name, size of images on the device (human readable),
        # copy progress (%), copy text, eject button (None if irrelevant),
        # process id, pulse
        self.devices = {}
        self.row_to_scan_id = {}
        self.no_devices = 0

    def columnCount(self, parent=QModelIndex()):
        return 3

    def rowCount(self, parent=QModelIndex()):
        return self.no_devices

    def insertRows(self, position, rows=1, index=QModelIndex()):
        self.beginInsertRows(QModelIndex(), position, position + rows - 1)
        self.no_devices += 1
        self.endInsertRows()

        return True

    def removeRows(self, position, rows=1, index=QModelIndex()):
        if not index.isValid():
            return

        final_pos = position + rows - 1
        self.beginRemoveRows(QModelIndex(), position, final_pos)
        # remap the dict to match rows the correct scan ids
        scan_ids = [scan_id for row, scan_id in self.row_to_scan_id.items() if
                    row < position or row > final_pos]
        self.row_to_scan_id = dict(enumerate(scan_ids))
        self.endRemoveRows()
        return True


    def addDevice(self, scan_id: int, deviceIcon: QPixmap, deviceName: str,
                  ejectIcon: QPixmap, textDisplay: str):
        row = self.rowCount()
        self.insertRow(row)

        self.devices[scan_id] = DeviceRow(deviceIcon, deviceName, ejectIcon,
                                          '1GB', textDisplay)
        self.row_to_scan_id[row] = scan_id

    def data(self, index: QModelIndex, role=Qt.DisplayRole):

        if not index.isValid():
            return None

        row = index.row()
        if row >= self.no_devices or row < 0:
            return None
        if row not in self.row_to_scan_id:
            return None
        elif role == Qt.DisplayRole:
            scan_id = self.row_to_scan_id[row]
            column = index.column()
            device = self.devices[scan_id] # type: DeviceRow
            if column == DEVICE:
                return (device.icon, device.name, device.ejection)
            elif column == SIZE:
                return device.size
            else:
                assert column == TEXT
                return device.text
        else:
            pass
            # print("Unknown role:", role)

class DeviceView(QTableView):
    def __init__(self):
        super(DeviceView, self).__init__()
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setVisible(False)

    def resizeColumns(self):
        for column in (DEVICE, SIZE):
            self.resizeColumnToContents(column)

class DeviceDelegate(QStyledItemDelegate):
    iconSize = 16
    padding = 2
    def __init__(self, parent=None):
        super(DeviceDelegate, self).__init__(parent)

    def deviceColumnHeight(self, option):
        metrics = option.fontMetrics
        return


    def paint(self, painter: QPainter, option: QStyleOptionViewItem,
              index: QModelIndex):
        if index.column() == DEVICE:
            painter.save()

            icon, name, ejection = index.model().data(index, Qt.DisplayRole)
            assert isinstance(icon, QIcon)

            height = option.rect.height()
            icon_y = round((height-self.iconSize) / 2)
            icon.paint(painter, self.padding, icon_y,
                       self.iconSize, self.iconSize)

            assert isinstance(name, str)
            metrics = option.fontMetrics
            width = metrics.width(name)
            painter.drawText(self.padding * 3 + self.iconSize, 0,
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
                             option.rect.width(), option.rect.height(),
                             Qt.AlignCenter, size)
            painter.restore()
        else:
            assert index.column() == TEXT
            text = index.model().data(index, Qt.DisplayRole)
            progressStyle = QStyleOptionProgressBar()
            progressStyle.state = QStyle.State_Enabled
            progressStyle.direction = QApplication.layoutDirection()
            progressStyle.rect = option.rect
            progressStyle.fontmetrics = QApplication.fontMetrics()
            progressStyle.minimum = 0
            progressStyle.maximum = 0
            progressStyle.progress = 1
            progressStyle.text = text
            progressStyle.textAlignment = Qt.AlignCenter
            progressStyle.textVisible = True
            QApplication.style().drawControl(QStyle.CE_ProgressBar,
                                             progressStyle, painter)

    def sizeHint(self, option, index):
        metrics = option.fontMetrics
        if index.column() == DEVICE:
            icon, name, ejection = index.model().data(index, Qt.DisplayRole)
            if ejection is not None:
                ejectionWidth = self.padding * 2 + self.iconSize + 10
            else:
                ejectionWidth = 0
            return QSize(metrics.width(name) + self.iconSize + self.padding*4 +
                         ejectionWidth,
                         max(self.iconSize, metrics.height()) + self.padding*2)
        elif index.column() == SIZE:
            size = index.model().data(index, Qt.DisplayRole)
            return QSize(metrics.width(size), metrics.height())
        else:
            assert index.column() == TEXT
            text = index.model().data(index, Qt.DisplayRole)
            return QSize(metrics.width(text), metrics.height())