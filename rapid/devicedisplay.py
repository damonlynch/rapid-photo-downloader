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

"""
Display details of devices like cameras, external drives and folders on the
computer.
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2015-2016, Damon Lynch"

from collections import namedtuple, defaultdict
from typing import Optional, Dict
import logging

from gettext import gettext as _

from PyQt5.QtCore import (QModelIndex, QSize, Qt, QPoint, QRect, QRectF,
                          QEvent, QAbstractItemModel, QAbstractListModel)
from PyQt5.QtWidgets import (QStyledItemDelegate,QStyleOptionViewItem, QApplication, QStyle,
                             QListView, QStyleOptionButton, QAbstractItemView, QMenu, QWidget)
from PyQt5.QtGui import (QPainter, QFontMetrics, QFont, QColor, QLinearGradient, QBrush, QPalette)

from viewutils import RowTracker
from constants import DeviceState, FileType, CustomColors, DeviceType, Roles
from devices import Device, display_devices
from utilities import thousands, format_size_for_user
from storage import StorageSpace
from rpdfile import make_key

def device_view_width(standard_font_size: int) -> int:
    return standard_font_size * 12

class DeviceModel(QAbstractListModel):
    def __init__(self, parent):
        super().__init__(parent)
        self.rapidApp = parent
        self.devices = {} # type: Dict[int, Device]
        self.state = {} # type: Dict[int, DeviceState]
        self.progress = defaultdict(float) # type: Dict[int, float]
        self.checked = defaultdict(lambda: True) # type: Dict[int, bool]
        self.rows = RowTracker()

    def columnCount(self, parent=QModelIndex()):
        return 1

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

    def updateDeviceScan(self, scan_id: int):
        row = self.rows.row(scan_id)
        column = 0
        self.dataChanged.emit(self.index(row, column), self.index(row, column))

    def updateDownloadProgress(self, scan_id: int, percent_complete: float,
                               progress_bar_text: str):
        pass

    def data(self, index: QModelIndex, role=Qt.DisplayRole):

        if not index.isValid():
            return None

        row = index.row()
        if row >= len(self.rows) or row < 0:
            return None
        if row not in self.rows:
            return None
        scan_id = self.rows[row]
        if role == Qt.DisplayRole:
            device = self.devices[scan_id] # type: Device
            return device
        elif role == Qt.CheckStateRole:
            return self.checked[scan_id]
        elif role == Roles.scan_id:
            return scan_id
        elif role == Qt.ToolTipRole:
            device = self.devices[scan_id] # type: Device
            if device.device_type in (DeviceType.path, DeviceType.volume):
                return device.path
        return None

    def setData(self, index: QModelIndex, value, role: int) -> bool:
        if not index.isValid():
            return False

        row = index.row()
        if row >= len(self.rows) or row < 0:
            return False
        scan_id = self.rows[row]
        if role == Qt.CheckStateRole:
            self.setCheckedValue(value, scan_id, row)
            self.rapidApp.thumbnailModel.checkAll(value, scan_id=scan_id)
            return True
        return False

    def setCheckedValue(self, checked: bool, scan_id: int, row: Optional[int]=None):
        if row is None:
            row = self.rows.row(scan_id)
        self.checked[scan_id] = checked
        self.dataChanged.emit(self.index(row, 0),self.index(row, 0))


class DeviceView(QListView):
    def __init__(self, parent):
        super().__init__(parent)
        # Disallow the user from being able to select the table cells
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.view_width = device_view_width(QFontMetrics(parent.font()).height())
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def sizeHint(self):
        height = 0
        for row in range(self.model().rowCount()):
            height += self.sizeHintForRow(row)
        scrollbar_height = round(self.horizontalScrollBar().height() / 3)
        delegate = self.itemDelegate()  # type: DeviceDelegate
        height = height - delegate.footer  # + scrollbar_height
        return QSize(self.view_width, height)


class DeviceDelegate(QStyledItemDelegate):

    padding = 6
    
    photos = _('Photos')
    videos = _('Videos')
    other = _('Other')
    empty = _('Empty Space')
    
    shading_intensity = 104

    def __init__(self, parent):
        super(DeviceDelegate, self).__init__(parent)
        self.rapidApp = parent

        self.checkboxStyleOption = QStyleOptionButton()
        self.checkboxRect = QApplication.style().subElementRect(
            QStyle.SE_CheckBoxIndicator, self.checkboxStyleOption, None)
        
        self.standard_font = QFont()  # type: QFont
        self.standard_font_bold = QFont(self.standard_font)
        self.standard_font_bold.setWeight(63)
        self.standard_metrics = QFontMetrics(self.standard_font)
        self.standard_height = self.standard_metrics.height()

        self.icon_size = self.standard_height

        self.small_font = QFont(self.standard_font)
        self.small_font.setPointSize(self.standard_font.pointSize() - 2)
        self.small_font_metrics = QFontMetrics(self.small_font)
        sample_number = thousands(999)
        sample_no_photos = '{} {}'.format(self.photos, sample_number)
        sample_no_videos = '{} {}'.format(self.videos, sample_number)
        self.sample_photos_width = self.small_font_metrics.boundingRect(sample_no_photos).width()
        self.sample_videos_width = self.small_font_metrics.boundingRect(sample_no_videos).width()
        
        # Height of the graqient bar that visually shows storage use
        self.g_height = self.standard_height * 1.5
        # Height of the details about the storage e.g. number of photos
        # videos, etc.
        self.details_height = self.small_font_metrics.height() * 2 + 2
        self.footer = 10
        self.view_width = device_view_width(self.standard_height)
        
        self.grey_border = QColor('#cdcdcd')

        alternate_color = QPalette().alternateBase().color()
        self.device_name_highlight_color = QColor(alternate_color).darker(105)
        self.device_name_height = self.standard_height + self.padding * 3

        self.vertical_padding = 10

        # Calculate height of device view, including device name/icon/checkbox,
        # text above gradient, gradient, and text below

        self.base_height = (self.padding * 2 + self.standard_height + self.footer)
        self.storage_height = (self.vertical_padding * 2 + self.standard_height + self.padding +
                               self.g_height + self.vertical_padding + self.details_height)
        self.contextMenu = QMenu()
        removeDeviceAct = self.contextMenu.addAction(_('Remove'))
        removeDeviceAct.triggered.connect(self.removeDevice)
        rescanDeviceAct = self.contextMenu.addAction(_('Rescan'))
        rescanDeviceAct.triggered.connect(self.rescanDevice)
        # store the index in which the user right clicked
        self.clickedIndex = None  # type: QModelIndex

    def removeDevice(self) -> None:
        index = self.clickedIndex
        if index:
            scan_id = index.model().data(index, Roles.scan_id)  # type: Device
            self.rapidApp.removeDevice(scan_id)

    def rescanDevice(self) -> None:
        index = self.clickedIndex
        if index:
            pass

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        painter.save()

        x = option.rect.x() + self.padding
        y = option.rect.y() + self.padding
        width = option.rect.width() - self.padding * 2

        standard_pen_color = painter.pen().color()

        device = index.model().data(index, Qt.DisplayRole)  # type: Device
        checked = index.model().data(index, Qt.CheckStateRole)

        deviceNameRect = QRect(option.rect.x(), option.rect.y(), option.rect.width(),
                               self.device_name_height)
        painter.fillRect(deviceNameRect, self.device_name_highlight_color)

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
        icon_y = y + self.standard_height / 6
        icon = device.get_pixmap(QSize(self.icon_size, self.icon_size))
        target = QRect(icon_x, icon_y, self.icon_size, self.icon_size)
        source = QRect(0, 0, self.icon_size, self.icon_size)
        painter.drawPixmap(target, icon, source)

        # painter.setFont(self.standard_font_bold)
        text_y = y + self.standard_height
        text_x = target.right() + 10
        painter.drawText(text_x, text_y, device.display_name)

        top = text_y

        for storage_space in device.storage_space:  # type: StorageSpace
            painter.setFont(self.standard_font)

            if device.device_type == DeviceType.camera:
                photo_key = make_key(FileType.photo, storage_space.path)
                video_key = make_key(FileType.video, storage_space.path)
                sum_key = storage_space.path
            else:
                photo_key = FileType.photo
                video_key = FileType.video
                sum_key = None

            photos = _('%(no_photos)s Photos') % {'no_photos': thousands(device.file_type_counter[
                photo_key])}
            videos = _('%(no_videos)s Videos') % {'no_videos': thousands(device.file_type_counter[
                video_key])}
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
                # empty_size = format_size_for_user(storage_space.bytes_free)

                # Device size
                device_size_x = x
                device_size_y = top + self.vertical_padding + self.standard_height
                painter.drawText(device_size_x, device_size_y, bytes_total)

                # Percent used
                device_used_width = self.standard_metrics.boundingRect(percent_used).width()
                device_used_x = width - device_used_width
                device_used_y = device_size_y
                painter.drawText(device_used_x, device_used_y, percent_used)

                photos_g_width = (device.file_size_sum[photo_key] /
                                  storage_space.bytes_total * width)
                photos_g_x = device_size_x
                g_y = device_size_y + self.padding
                linearGradient = QLinearGradient(photos_g_x, g_y, photos_g_x, g_y + self.g_height)
                color1 = QColor(CustomColors.color1.value)

                if device.file_size_sum[photo_key]:
                    photos_g_rect = QRectF(photos_g_x, g_y, photos_g_width, self.g_height)
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
                    videos_g_rect = QRectF(videos_g_x, g_y, videos_g_width, self.g_height)
                    linearGradient.setColorAt(0.2, color2.lighter(self.shading_intensity))
                    linearGradient.setColorAt(0.8, color2.darker(self.shading_intensity))
                    painter.fillRect(videos_g_rect, QBrush(linearGradient))
                else:
                    videos_g_width = 0

                color3 = QColor(CustomColors.color3.value)
                if other_bytes:
                    other_g_width = other_bytes / storage_space.bytes_total * width
                    other_g_x = videos_g_x + videos_g_width
                    other_g_rect = QRectF(other_g_x, g_y, other_g_width, self.g_height)
                    linearGradient.setColorAt(0.2, color3.lighter(self.shading_intensity))
                    linearGradient.setColorAt(0.8, color3.darker(self.shading_intensity))
                    painter.fillRect(other_g_rect, QBrush(linearGradient))
                else:
                    other_g_width = 0

                # Rectangle around spatial representation of sizes
                rect = QRectF(photos_g_x, g_y, width, self.g_height)
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
            details_y = bottom + self.vertical_padding

            # Gradient
            photos_g2_x =  x
            photos_g2_rect = QRect(photos_g2_x, details_y, gradient_width, self.details_height)
            linearGradient = QLinearGradient(photos_g2_x, details_y,
                                            photos_g2_x, details_y + self.details_height)
            linearGradient.setColorAt(0.2, color1.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, color1.darker(self.shading_intensity))
            painter.fillRect(photos_g2_rect, QBrush(linearGradient))
            painter.setPen(self.grey_border)
            painter.drawRect(photos_g2_rect)

            # Text
            photos_x = photos_g2_x + gradient_width + spacer
            photos_no_width = self.small_font_metrics.boundingRect(photos).width()
            photos_size_width = self.small_font_metrics.boundingRect(photos_size).width()
            photos_width = max(photos_no_width, photos_size_width, self.sample_photos_width)
            photos_rect = QRect(photos_x, details_y, photos_width, self.details_height)

            painter.setPen(standard_pen_color)
            painter.setFont(self.small_font)
            painter.drawText(photos_rect, Qt.AlignLeft|Qt.AlignTop, photos)
            painter.drawText(photos_rect, Qt.AlignLeft|Qt.AlignBottom, photos_size)

            # Video details

            # Gradient
            videos_g2_x = photos_rect.right() + 10
            videos_g2_rect = QRect(videos_g2_x, details_y, gradient_width, self.details_height)
            linearGradient.setColorAt(0.2, color2.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, color2.darker(self.shading_intensity))
            painter.fillRect(videos_g2_rect, QBrush(linearGradient))
            painter.setPen(self.grey_border)
            painter.drawRect(videos_g2_rect)
            
            #Text
            videos_x = videos_g2_x + gradient_width + spacer
            videos_no_width = self.small_font_metrics.boundingRect(videos).width()
            videos_size_width = self.small_font_metrics.boundingRect(videos_size).width()
            videos_width = max(videos_no_width, videos_size_width, self.sample_videos_width)
            videos_rect = QRect(videos_x, details_y, videos_width, self.details_height)

            painter.setPen(standard_pen_color)
            painter.drawText(videos_rect, Qt.AlignLeft|Qt.AlignTop, videos)
            painter.drawText(videos_rect, Qt.AlignLeft|Qt.AlignBottom, videos_size)
            
            if other_bytes:
                # Other details

                # Gradient
                other_g2_x = videos_rect.right() + 10
                other_g2_rect = QRect(other_g2_x, details_y, gradient_width, self.details_height)
                linearGradient.setColorAt(0.2, color3.lighter(self.shading_intensity))
                linearGradient.setColorAt(0.8, color3.darker(self.shading_intensity))
                painter.fillRect(other_g2_rect, QBrush(linearGradient))
                painter.setPen(QColor('#cdcdcd'))
                painter.drawRect(other_g2_rect)

                #Text
                other_x = other_g2_x + gradient_width + spacer
                other_no_width = self.small_font_metrics.boundingRect(self.other).width()
                other_size_width = self.small_font_metrics.boundingRect(other_size).width()
                other_width = max(other_no_width, other_size_width)
                other_rect = QRect(other_x, details_y, other_width, self.details_height)

                painter.setPen(standard_pen_color)
                painter.drawText(other_rect, Qt.AlignLeft|Qt.AlignTop, self.other)
                painter.drawText(other_rect, Qt.AlignLeft|Qt.AlignBottom, other_size)
            
            top = photos_g2_rect.bottom()

        painter.restore()

    def getLeftPoint(self, option: QStyleOptionViewItem ) -> QPoint:
        return QPoint(option.rect.x() + self.padding, option.rect.y() + self.padding)

    def getCheckBoxRect(self, option: QStyleOptionViewItem) -> QRect:
        return QRect(self.getLeftPoint(option), self.checkboxRect.size())

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        device = index.model().data(index, Qt.DisplayRole)  # type: Device
        height = self.base_height + self.storage_height * len(device.storage_space)
        return QSize(self.view_width, height)

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

        if (event.type() == QEvent.MouseButtonRelease or event.type() ==
            QEvent.MouseButtonDblClick):
            if event.button() == Qt.RightButton:
                self.clickedIndex = index
                scan_id = index.data(Roles.scan_id)
                device = index.model().data(index, Qt.DisplayRole)  # type: Device

                view = self.rapidApp.mapView(scan_id)
                globalPos = view.viewport().mapToGlobal(event.pos())
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

        # Change the checkbox-state
        self.setModelData(None, model, index)
        return True

    def setModelData (self, editor: QWidget,
                      model: QAbstractItemModel,
                      index: QModelIndex) -> None:
        newValue = not (index.model().data(index, Qt.CheckStateRole))
        model.setData(index, newValue, Qt.CheckStateRole)
