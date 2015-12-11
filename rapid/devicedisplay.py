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
from typing import Optional, Dict
import logging

from gettext import gettext as _

from PyQt5.QtCore import (QAbstractTableModel, QModelIndex, QSize, Qt, QPoint, QRect, QMargins)
from PyQt5.QtWidgets import (QStyledItemDelegate,
                             QStyleOptionViewItem, QStyleOptionProgressBar,
                             QApplication, QStyle, QListView, QWidget, QLabel,
                             QCheckBox, QGridLayout, QPushButton, QStyleOptionButton,
                             QAbstractItemView)
from PyQt5.QtGui import (QPixmap, QPainter, QIcon, QRegion, QFontMetrics)

from viewutils import RowTracker
from constants import DeviceState
from devices import Device

# class DeviceDisplay(QWidget):
#     def __init__(self, parent=None) -> None:
#         super().__init__(parent)
#         self.__scan_id = None
#         self.__device = None # type: Device
#
#         self.noPhotos = QLabel('0')
#         self.noVideos = QLabel('0')
#         self.photosLabel = QLabel(_('Photos'))
#         self.videosLabel = QLabel(_('Videos'))
#         self.deviceCheckbox = QCheckBox()
#         self.ejectButton = QPushButton()
#         self.ejectButton.setIcon(QIcon(':/icons/media-eject.svg'))
#
#         layout = QGridLayout()
#         layout.addWidget(self.deviceCheckbox, 0, 0, 2, 1)
#         layout.addWidget(self.ejectButton, 0, 1, 2, 1)
#         layout.addWidget(self.photosLabel, 0, 2, 1, 1)
#         layout.addWidget(self.videosLabel, 0, 3, 1, 1)
#         layout.addWidget(self.noPhotos, 1, 2, 1, 1)
#         layout.addWidget(self.noVideos, 1, 3, 1, 1)
#         self.setLayout(layout)
#
#     @property
#     def scan_id(self):
#         return self.__scan_id
#
#     @scan_id.setter
#     def scan_id(self, scan_id):
#         self.__scan_id = scan_id
#
#     @property
#     def device(self) -> Device:
#         return self.__device
#
#     @device.setter
#     def device(self, device: Device):
#         self.__device = device

        # self.device.render(painter, QPoint(), QRegion(), QWidget.DrawChildren)


class DeviceTableModel(QAbstractTableModel):
    def __init__(self, parent):
        super(DeviceTableModel, self).__init__(parent)
        self.devices = {} # type: Dict[Device]
        self.state = {} # type: Dict[DeviceState]
        self.progress = defaultdict(float) # type: Dict[int]
        self.checked = defaultdict(lambda: True) # type: Dict[int]
        self.rows = RowTracker()

    def columnCount(self, parent=QModelIndex()):
        return 4

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
            del self.devices[scan_id]
            del self.state[scan_id]
            if scan_id in self.progress:
                del self.progress[scan_id]
            if scan_id in self.checked:
                del self.checked[scan_id]
        self.endRemoveRows()
        return True

    def addDevice(self, scan_id: int, device: Device) -> None:
        row = self.rowCount()
        self.insertRow(row)

        self.devices[scan_id] = device
        self.state[scan_id] = DeviceState.scanning
        self.rows[row] = scan_id

    def removeDevice(self, scan_id: int):
        row = self.rows.row(scan_id)
        self.removeRows(row)

    def updateDeviceScan(self, scan_id: int, textToDisplay: str, size=None,
                         scan_completed=False):
        pass
        # self.texts[scan_id] = textToDisplay
        # if size is not None:
        #     self.sizes[scan_id] = size
        #     column = 1
        # else:
        #     column = 2
        # if scan_completed:
        #     self.state[scan_id] = DeviceState.scanned
        # row = self.rows.row(scan_id)
        # self.dataChanged.emit(self.index(row, column), self.index(row, 2))

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
        scan_id = self.rows[row]
        column = index.column()
        if column == 0:
            device = self.devices[scan_id] # type: Device
            if role == Qt.DisplayRole:
                return device
            elif role == Qt.CheckStateRole:
                return self.checked[scan_id]
            # elif role == Qt.DecorationRole:
            #     return device.get_icon()
            logging.error("Unexpected role %s for %s", role, device)
            return None
        # elif column == 1:
        #     device = self.devices[scan_id] # type: Device
        #     return device.can_eject
        # elif column == 3:
        #     state = self.state[scan_id]
        #     if state == DeviceState.downloading:
        #         progress = self.progress[scan_id]
        #         maximum = 100
        #     elif state == DeviceState.scanning:
        #         progress = 0
        #         maximum = 0
        #     elif state == DeviceState.scanned:
        #         maximum = 100
        #         progress = 100
        #
        #     return (self.texts[scan_id], progress, maximum)
        # else:
        #     pass
        #     # print("Unknown role:", role)

class DeviceView(QListView):
    def __init__(self):
        super(DeviceView, self).__init__()
        # Set the last column (with the progressbar) to fill the remaining
        # width
        # self.horizontalHeader().setStretchLastSection(True)
        # # Hide the headers
        # self.verticalHeader().setVisible(False)
        # self.horizontalHeader().setVisible(False)
        # Disallow the user from being able to select the table cells
        self.setSelectionMode(QAbstractItemView.NoSelection)

    def resizeColumns(self):
        pass
        # for column in (DEVICE, SIZE):
        #     self.resizeColumnToContents(column)

    def sizeHint(self):
        return QSize(200, 60)

class DeviceDelegate(QStyledItemDelegate):
    iconSize = 16
    padding = 2
    def __init__(self, parent=None):
        super(DeviceDelegate, self).__init__(parent)
        self.checkboxStyleOption = QStyleOptionButton()
        self.checkboxRect = QApplication.style().subElementRect(
            QStyle.SE_CheckBoxIndicator, self.checkboxStyleOption, None)

        self.margin = 5


    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        painter.save()

        text_padding = 3
        x = option.rect.x() + self.padding
        y = option.rect.y() + self.padding

        device = index.model().data(index, Qt.DisplayRole) # type: Device
        checked = index.model().data(index, Qt.CheckStateRole)

        checkboxStyleOption = QStyleOptionButton()
        if checked:
            checkboxStyleOption.state |= QStyle.State_On
        else:
            checkboxStyleOption.state |= QStyle.State_Off
        checkboxStyleOption.state |= QStyle.State_Enabled

        checkboxStyleOption.rect = self.getCheckBoxRect(option)
        QApplication.style().drawControl(QStyle.CE_CheckBox,
                                         checkboxStyleOption, painter)

        icon_x = checkboxStyleOption.rect.right() + 10
        icon_y = y
        icon = device.get_pixmap(QSize(22, 22))
        target = QRect(icon_x, icon_y, 22, 22)
        source = QRect(0, 0, 22, 22)
        painter.drawPixmap(target, icon, source)


        font = painter.font()
        metrics = QFontMetrics(font)
        nameBoundingRect = metrics.boundingRect(device.display_name).marginsAdded(
            QMargins(text_padding, 0, text_padding, text_padding)) # type: QRect

        text_x = target.right() + 10
        text_y = y + metrics.height()
        painter.drawText(text_x + text_padding, text_y, device.display_name)

        painter.restore()

    def getLeftPoint(self, option: QStyleOptionViewItem ) -> QPoint:
        return QPoint(option.rect.x() + self.padding, option.rect.y() + self.padding)

    def getCheckBoxRect(self, option: QStyleOptionViewItem) -> QRect:
        return QRect(self.getLeftPoint(option), self.checkboxRect.size())

    def sizeHint(self, option, index):

        return QSize(200, 30)

        # metrics = option.fontMetrics
        # if index.column() == DEVICE:
        #     icon, name, ejection = index.model().data(index, Qt.DisplayRole)
        #     if ejection is not None or True:
        #         ejectionWidth = self.padding * 2 + self.iconSize + 10
        #     else:
        #         ejectionWidth = 0
        #     return QSize(metrics.width(name) + self.iconSize + self.padding*4 +
        #                  ejectionWidth,
        #                  max(self.iconSize, metrics.height()) + self.padding*2)
        # elif index.column() == SIZE:
        #     # size = index.model().data(index, Qt.DisplayRole)
        #     width = metrics.width('9999.9GB')
        #     return QSize(width, metrics.height())
        # else:
        #     assert index.column() == TEXT
        #     text, progress, maximum = index.model().data(index, Qt.DisplayRole)
        #     return QSize(metrics.width(text), metrics.height())