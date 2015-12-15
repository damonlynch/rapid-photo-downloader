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

from PyQt5.QtCore import (QAbstractTableModel, QModelIndex, QSize, Qt, QPoint, QRect, QMargins,
                          QRectF)
from PyQt5.QtWidgets import (QStyledItemDelegate,
                             QStyleOptionViewItem, QStyleOptionProgressBar,
                             QApplication, QStyle, QListView, QWidget, QLabel,
                             QCheckBox, QGridLayout, QPushButton, QStyleOptionButton,
                             QAbstractItemView)
from PyQt5.QtGui import (QPixmap, QPainter, QIcon, QRegion, QFontMetrics, QFont, QGuiApplication,
                         QColor, QLinearGradient, QBrush)

from viewutils import RowTracker
from constants import DeviceState, FileType, CustomColors, DeviceType
from devices import Device
from utilities import thousands, format_size_for_user
from storage import StorageSpace
from rpdfile import make_key


class DeviceTableModel(QAbstractTableModel):
    def __init__(self, parent):
        super(DeviceTableModel, self).__init__(parent)
        self.devices = {} # type: Dict[int, Device]
        self.state = {} # type: Dict[int, DeviceState]
        self.progress = defaultdict(float) # type: Dict[int, float]
        self.checked = defaultdict(lambda: True) # type: Dict[int, bool]
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

        row = self.rows.row(scan_id)
        column = 0
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
        return QSize(200, 270)

class DeviceDelegate(QStyledItemDelegate):

    icon_size = 20
    padding = 6
    
    photos = _('Photos')
    videos = _('Videos')
    other = _('Other')
    empty = _('Empty Space')
    
    shading_intensity = 104

    def __init__(self, parent):
        super(DeviceDelegate, self).__init__(parent)
        
        self.parent_font = parent.font()
        
        self.checkboxStyleOption = QStyleOptionButton()
        self.checkboxRect = QApplication.style().subElementRect(
            QStyle.SE_CheckBoxIndicator, self.checkboxStyleOption, None)
        
        self.no_files_header_font = QFont(self.parent_font) # type: QFont
        self.no_files_header_font.setPointSize(self.no_files_header_font.pointSize() - 3)
        self.no_files_header_metrics = QFontMetrics(self.no_files_header_font)
        self.no_files_header_height = self.no_files_header_metrics.height()
        self.no_photos_header_width = self.no_files_header_metrics.boundingRect(self.photos).width()
        self.no_videos_header_width = self.no_files_header_metrics.boundingRect(self.videos).width()

        sample_number = thousands(9999)
        sample_number_width = QFontMetrics(self.parent_font).boundingRect(sample_number).width()
        self.no_photos_width = max(sample_number_width, self.no_photos_header_width)
        self.no_videos_width = max(sample_number_width, self.no_videos_header_width)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        painter.save()

        x = option.rect.x() + self.padding
        y = option.rect.y() + self.padding

        standard_pen_color = painter.pen().color()

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
        icon = device.get_pixmap(QSize(self.icon_size, self.icon_size))
        target = QRect(icon_x, icon_y, self.icon_size, self.icon_size)
        source = QRect(0, 0, self.icon_size, self.icon_size)
        painter.drawPixmap(target, icon, source)

        standard_font = painter.font() # type: QFont
        metrics = QFontMetrics(standard_font)
        text_y = y + metrics.height()
        text_x = target.right() + 10
        painter.drawText(text_x, text_y, device.display_name)

        width = option.rect.width() - self.padding * 2

        top = text_y
        small_font = QFont(standard_font)
        small_font.setPointSize(standard_font.pointSize() - 2)
        small_font_metrics = QFontMetrics(small_font)

        for storage_space in device.storage_space:
            painter.setFont(standard_font)

            if device.device_type == DeviceType.camera:
                photo_key = make_key(FileType.photo, storage_space.path)
                video_key = make_key(FileType.video, storage_space.path)
                sum_key = storage_space.path
            else:
                photo_key = FileType.photo
                video_key = FileType.video
                sum_key = None

            photos = _('%(no_photos)s Photos') % {'no_photos': device.file_type_counter[
                photo_key]}
            videos = _('%(no_videos)s Videos') % {'no_videos': device.file_type_counter[
                video_key]}
            photos_size = format_size_for_user(device.file_size_sum[photo_key])
            videos_size = format_size_for_user(device.file_size_sum[video_key])
            other_bytes = storage_space.bytes_total - device.file_size_sum.sum(sum_key) - \
                          storage_space.bytes_free
            other_size = format_size_for_user(other_bytes)

            # If something went wrong getting the storage details
            # for this device, the total space will be zero
            if storage_space.bytes_total:
                bytes_total = format_size_for_user(storage_space.bytes_total, no_decimals=0)
                bytes_used = storage_space.bytes_total-storage_space.bytes_free

                percent_used = '{0:.0%}'.format(bytes_used / storage_space.bytes_total)
                # Translators: percentage full e.g. 75% full
                percent_used = '%s full' % percent_used
                empty_size = format_size_for_user(storage_space.bytes_free)


                # Device size
                metrics = QFontMetrics(self.parent_font)
                device_size_x = x
                device_size_y = top + 10 + metrics.height()
                painter.drawText(device_size_x, device_size_y, bytes_total)

                # Percent used
                device_used_width = metrics.boundingRect(percent_used).width()
                device_used_x = width - device_used_width
                device_used_y = device_size_y
                painter.drawText(device_used_x, device_used_y, percent_used)

                photos_g_width = (device.file_size_sum[photo_key] /
                                  storage_space.bytes_total * width)
                photos_g_x = device_size_x
                g_height = 25.0
                g_y = device_size_y + self.padding
                linearGradient = QLinearGradient(photos_g_x, g_y, photos_g_x, g_y + g_height)
                color1 = QColor(CustomColors.color1.value)

                if device.file_size_sum[photo_key]:
                    photos_g_rect = QRectF(photos_g_x, g_y, photos_g_width, g_height)
                    linearGradient.setColorAt(0.2, color1.lighter(self.shading_intensity))
                    linearGradient.setColorAt(0.8, color1.darker(self.shading_intensity))
                    painter.fillRect(photos_g_rect, QBrush(linearGradient))
                else:
                    photos_g_width = 0

                videos_g_x = photos_g_x + photos_g_width
                color2 = QColor(CustomColors.color2.value)
                if device.file_size_sum[video_key]:
                    videos_g_width = (device.file_size_sum[video_key] /
                                      storage_space.bytes_total * width)
                    videos_g_rect = QRectF(videos_g_x, g_y, videos_g_width, g_height)
                    linearGradient.setColorAt(0.2, color2.lighter(self.shading_intensity))
                    linearGradient.setColorAt(0.8, color2.darker(self.shading_intensity))
                    painter.fillRect(videos_g_rect, QBrush(linearGradient))
                else:
                    videos_g_width = 0

                color3 = QColor(CustomColors.color3.value)
                if other_bytes:
                    other_g_width = other_bytes / storage_space.bytes_total * width
                    other_g_x = videos_g_x + videos_g_width
                    other_g_rect = QRectF(other_g_x, g_y, other_g_width, g_height)
                    linearGradient.setColorAt(0.2, color3.lighter(self.shading_intensity))
                    linearGradient.setColorAt(0.8, color3.darker(self.shading_intensity))
                    painter.fillRect(other_g_rect, QBrush(linearGradient))
                else:
                    other_g_width = 0

                # Rectangle around spatial representation of sizes
                rect = QRectF(photos_g_x, g_y, width, g_height)
                painter.setPen(QColor('#cdcdcd'))
                painter.drawRect(rect)
                bottom = rect.bottom()
            else:
                bottom = top
                other_bytes = 0

            # Details text indicating number and size of photos & videos
            gradient_width = 10

            # Photo details
            spacer = 3
            details_y = bottom + 10
            details_height = small_font_metrics.height() * 2 + 2

            # Gradient
            photos_g2_x =  x
            photos_g2_rect = QRect(photos_g2_x, details_y, gradient_width, details_height)
            linearGradient = QLinearGradient(photos_g2_x, details_y,
                                            photos_g2_x, details_y + details_height)
            linearGradient.setColorAt(0.2, color1.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, color1.darker(self.shading_intensity))
            painter.fillRect(photos_g2_rect, QBrush(linearGradient))
            painter.setPen(QColor('#cdcdcd'))
            painter.drawRect(photos_g2_rect)

            # Text
            photos_x = photos_g2_x + gradient_width + spacer
            photos_no_width = small_font_metrics.boundingRect(photos).width()
            photos_size_width = small_font_metrics.boundingRect(photos_size).width()
            photos_width = max(photos_no_width, photos_size_width)
            photos_rect = QRect(photos_x, details_y, photos_width, details_height)

            painter.setPen(standard_pen_color)
            painter.setFont(small_font)
            painter.drawText(photos_rect, Qt.AlignLeft|Qt.AlignTop, photos)
            painter.drawText(photos_rect, Qt.AlignLeft|Qt.AlignBottom, photos_size)

            # Video details

            # Gradient
            videos_g2_x = photos_rect.right() + 10
            videos_g2_rect = QRect(videos_g2_x, details_y, gradient_width, details_height)
            linearGradient.setColorAt(0.2, color2.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, color2.darker(self.shading_intensity))
            painter.fillRect(videos_g2_rect, QBrush(linearGradient))
            painter.setPen(QColor('#cdcdcd'))
            painter.drawRect(videos_g2_rect)
            
            #Text
            videos_x = videos_g2_x + gradient_width + spacer
            videos_no_width = small_font_metrics.boundingRect(videos).width()
            videos_size_width = small_font_metrics.boundingRect(videos_size).width()
            videos_width = max(videos_no_width, videos_size_width)
            videos_rect = QRect(videos_x, details_y, videos_width, details_height)

            painter.setPen(standard_pen_color)
            painter.drawText(videos_rect, Qt.AlignLeft|Qt.AlignTop, videos)
            painter.drawText(videos_rect, Qt.AlignLeft|Qt.AlignBottom, videos_size)
            
            if other_bytes:
                # Other details

                # Gradient
                other_g2_x = videos_rect.right() + 10
                other_g2_rect = QRect(other_g2_x, details_y, gradient_width, details_height)
                linearGradient.setColorAt(0.2, color3.lighter(self.shading_intensity))
                linearGradient.setColorAt(0.8, color3.darker(self.shading_intensity))
                painter.fillRect(other_g2_rect, QBrush(linearGradient))
                painter.setPen(QColor('#cdcdcd'))
                painter.drawRect(other_g2_rect)

                #Text
                other_x = other_g2_x + gradient_width + spacer
                other_no_width = small_font_metrics.boundingRect(self.other).width()
                other_size_width = small_font_metrics.boundingRect(other_size).width()
                other_width = max(other_no_width, other_size_width)
                other_rect = QRect(other_x, details_y, other_width, details_height)

                painter.setPen(standard_pen_color)
                painter.drawText(other_rect, Qt.AlignLeft|Qt.AlignTop, self.other)
                painter.drawText(other_rect, Qt.AlignLeft|Qt.AlignBottom, other_size)
            
            top = photos_g2_rect.bottom()

        painter.restore()

    def getLeftPoint(self, option: QStyleOptionViewItem ) -> QPoint:
        return QPoint(option.rect.x() + self.padding, option.rect.y() + self.padding)

    def getCheckBoxRect(self, option: QStyleOptionViewItem) -> QRect:
        return QRect(self.getLeftPoint(option), self.checkboxRect.size())

    def sizeHint(self, option, index):

        return QSize(200, 130)

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