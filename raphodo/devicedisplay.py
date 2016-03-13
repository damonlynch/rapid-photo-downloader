# Copyright (C) 2015-2016 Damon Lynch <damonlynch@gmail.com>
# Copyright (c) 2012-2014 Alexander Turkin

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

See devices.py for an explanation of what "Device" means in the context of
Rapid Photo Downloader.

Spinner code is derived from QtWaitingSpinner source, which is under the
MIT License:
https://github.com/snowwlex/QtWaitingSpinner

Copyright notice from QtWaitingSpinner source:
    Original Work Copyright (c) 2012-2014 Alexander Turkin
        Modified 2014 by William Hallatt
        Modified 2015 by Jacob Dawid
        Ported to Python3 2015 by Luca Weiss
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2015-2016, Damon Lynch"

import math
from collections import namedtuple, defaultdict
from typing import Optional, Dict, List, Set
import logging

from gettext import gettext as _

from PyQt5.QtCore import (QModelIndex, QSize, Qt, QPoint, QRect, QRectF,
                          QEvent, QAbstractItemModel, QAbstractListModel, pyqtSlot, QTimer)
from PyQt5.QtWidgets import (QStyledItemDelegate,QStyleOptionViewItem, QApplication, QStyle,
                             QListView, QStyleOptionButton, QAbstractItemView, QMenu, QWidget)
from PyQt5.QtGui import (QPainter, QFontMetrics, QFont, QColor, QLinearGradient, QBrush, QPalette,
                         QPixmap)

from raphodo.viewutils import RowTracker
from raphodo.constants import (DeviceState, FileType, CustomColors, DeviceType, Roles,
                               emptyViewHeight, ViewRowType, minPanelWidth)
from raphodo.devices import Device, display_devices
from raphodo.utilities import thousands, format_size_for_user
from raphodo.storage import StorageSpace
from raphodo.rpdfile import make_key


def icon_size() -> int:
    height = QFontMetrics(QFont()).height()
    if height % 2 == 1:
        height = height + 1
    return height

number_spinner_lines = 10
revolutions_per_second = 1

class DeviceModel(QAbstractListModel):
    """
    Stores Device / This Computer data.

    One Device is displayed has multiple rows:
    1. Header row
    2. One or two rows displaying storage info, depending on how many
       storage devices the device has (i.e. memory cards or perhaps a
       combo of onboard flash memory and additional storage)

    Therefore must map rows to device and back, which is handled by
    a row having a row id, and row ids being linked to a scan id.
    """

    def __init__(self, parent, device_display_type: str):
        super().__init__(parent)
        self.rapidApp = parent
        self.device_display_type = device_display_type
        self.devices = {}  # type: Dict[int, Device]
        self.spinner_state = {}  # type: Dict[int, DeviceState]
        self.checked = defaultdict(lambda: True) # type: Dict[int, bool]
        self.icons = {}  # type: Dict[int, QPixmap]
        self.rows = RowTracker()  # type: RowTracker
        self.row_id_counter = 0  # type: int
        self.row_id_to_scan_id = dict()  # type: Dict[int, int]
        self.scan_id_to_row_ids = defaultdict(list)  # type: Dict[int, List[int]]
        self.storage= dict()  # type: Dict[int, StorageSpace]
        self.headers = set()  # type: Set[int]

        self.icon_size = icon_size()
        
        self.row_ids_active = []  # type: List[int]

        self._rotation_position = 0
        self._timer = QTimer(self)
        self._timer.setInterval(1000 / (number_spinner_lines * revolutions_per_second))
        self._timer.timeout.connect(self.rotateSpinner)
        self._isSpinning = False

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
        self.endRemoveRows()
        return True

    def addDevice(self, scan_id: int, device: Device) -> None:
        no_storage = max(len(device.storage_space), 1)
        no_rows = no_storage + 1

        if len(device.storage_space):
            i = 0
            start_row_id = self.row_id_counter + 1
            for row_id in range(start_row_id, start_row_id + len(device.storage_space)):
                self.storage[row_id] = device.storage_space[i]
                i += 1
        else:
            self.storage[self.row_id_counter + 1] = None

        self.headers.add(self.row_id_counter)
        self.row_ids_active.append(self.row_id_counter)

        row = self.rowCount()
        self.insertRows(row, no_rows)
        logging.debug("Adding %s to %s display with scan id %s at row %s",
                      device.name(), self.device_display_type, scan_id, row)
        for row_id in range(self.row_id_counter, self.row_id_counter + no_rows):
            self.row_id_to_scan_id[row_id] = scan_id
            self.rows[row] = row_id
            self.scan_id_to_row_ids[scan_id].append(row_id)
            row += 1
        self.row_id_counter += no_rows

        self.devices[scan_id] = device
        self.spinner_state[scan_id] = DeviceState.scanning
        self.icons[scan_id] = device.get_pixmap(QSize(self.icon_size, self.icon_size))

        if self._isSpinning is False:
            self.startSpinners()

    def updateDeviceNameAndStorage(self, scan_id: int, device: Device) -> None:
        """
        Update Cameras with updated storage information and display
        name as reported by libgphoto2.

        If number of storage devies is > 1, inserts additional rows
        for the camera.

        :param scan_id: id of the camera
        :param device: camera device
        """

        row_ids = self.scan_id_to_row_ids[scan_id]
        if len(device.storage_space) > 1:
            # Add a new row after the current empty storage row
            row_id = row_ids[1]
            row = self.rows.row(row_id)
            logging.debug("Adding row %s for additional storage device for %s",
                          row, device.display_name)

            for i in range(len(device.storage_space) - 1):
                row += 1
                new_row_id = self.row_id_counter + i
                self.rows.insert_row(row, new_row_id)
                self.scan_id_to_row_ids[scan_id].append(new_row_id)
                self.row_id_to_scan_id[new_row_id] = scan_id
            self.row_id_counter += len(device.storage_space) - 1

        for idx, storage_space in enumerate(device.storage_space):
            row_id = row_ids[idx + 1]
            self.storage[row_id] = storage_space

        row = self.rows.row(row_ids[0])
        self.dataChanged.emit(self.index(row, 0),
                              self.index(row + len(self.devices[scan_id].storage_space), 0))

    def getHeaderRowId(self, scan_id: int) -> int:
        row_ids = self.scan_id_to_row_ids[scan_id]
        return row_ids[0]

    def removeDevice(self, scan_id: int) -> None:
        row_ids = self.scan_id_to_row_ids[scan_id]
        header_row_id = row_ids[0]
        row = self.rows.row(header_row_id)
        logging.debug("Removing %s rows from %s display, starting at row %s",
                      len(row_ids), self.device_display_type, row)
        self.rows.remove_rows(row, len(row_ids))
        del self.devices[scan_id]
        del self.spinner_state[scan_id]
        if scan_id in self.checked:
            del self.checked[scan_id]
        if header_row_id in self.row_ids_active:
            self.row_ids_active.remove(header_row_id)
            if len(self.row_ids_active) == 0:
                self.stopSpinners()
        self.headers.remove(header_row_id)
        del self.scan_id_to_row_ids[scan_id]
        for row_id in row_ids:
            del self.row_id_to_scan_id[row_id]

        self.removeRows(row, len(row_ids))

    def updateDeviceScan(self, scan_id: int) -> None:
        row_id = self.scan_id_to_row_ids[scan_id][0]
        row = self.rows.row(row_id)
        # TODO optimize which storage space is updated
        self.dataChanged.emit(self.index(row + 1, 0),
                              self.index(row + len(self.devices[scan_id].storage_space), 0))

    def setSpinnerState(self, scan_id: int, state: DeviceState) -> None:
        row_id = self.getHeaderRowId(scan_id)
        row = self.rows.row(row_id)

        current_state = self.spinner_state[scan_id]
        current_state_active = current_state in (DeviceState.scanning, DeviceState.downloading)

        if current_state_active and state == DeviceState.idle:
            self.row_ids_active.remove(row_id)
            if len(self.row_ids_active) == 0:
                self.stopSpinners()
        # Next line assumes spinners were started when a device was added
        elif not current_state_active and state == DeviceState.downloading:
            self.row_ids_active.append(row_id)
            if not self._isSpinning:
                self.startSpinners()

        self.spinner_state[scan_id] = state
        self.dataChanged.emit(self.index(row, 0), self.index(row, 0))

    def data(self, index: QModelIndex, role=Qt.DisplayRole):

        if not index.isValid():
            return None

        row = index.row()
        if row >= len(self.rows) or row < 0:
            return None
        if row not in self.rows:
            return None

        row_id = self.rows[row]
        scan_id = self.row_id_to_scan_id[row_id]

        if role == Qt.DisplayRole:
            if row_id in self.headers:
                return ViewRowType.header
            else:
                return ViewRowType.content
        elif role == Qt.CheckStateRole:
            return self.checked[scan_id]
        elif role == Roles.scan_id:
            return scan_id
        else:
            device = self.devices[scan_id] # type: Device
            if role == Qt.ToolTipRole:
                if device.device_type in (DeviceType.path, DeviceType.volume):
                    return device.path
            elif role == Roles.device_details:
                return (device.display_name, self.icons[scan_id], self.spinner_state[scan_id],
                        self._rotation_position)
            elif role == Roles.storage:
                return device, self.storage[row_id]
        return None

    def setData(self, index: QModelIndex, value, role: int) -> bool:
        if not index.isValid():
            return False

        row = index.row()
        if row >= len(self.rows) or row < 0:
            return False
        row_id = self.rows[row]
        scan_id = self.row_id_to_scan_id[row_id]

        if role == Qt.CheckStateRole:
            self.setCheckedValue(value, scan_id, row)
            self.rapidApp.thumbnailModel.checkAll(value, scan_id=scan_id)
            return True
        return False

    def setCheckedValue(self, checked: bool, scan_id: int, row: Optional[int]=None):
        if row is None:
            row_id = self.scan_id_to_row_ids[scan_id][0]
            row = self.rows.row(row_id)
        self.checked[scan_id] = checked
        self.dataChanged.emit(self.index(row, 0),self.index(row, 0))
        
    
    def startSpinners(self):
        self._isSpinning = True

        if not self._timer.isActive():
            self._timer.start()
            self._rotation_position = 0

    def stopSpinners(self):
        self._isSpinning = False

        if self._timer.isActive():
            self._timer.stop()
            self._rotation_position = 0    
    
    @pyqtSlot()
    def rotateSpinner(self):
        self._rotation_position += 1
        if self._rotation_position >= number_spinner_lines:
            self._rotation_position = 0
        for row_id in self.row_ids_active:
            row = self.rows.row(row_id)
            self.dataChanged.emit(self.index(row, 0),self.index(row, 0))


class DeviceView(QListView):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Disallow the user from being able to select the table cells
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.view_width = minPanelWidth()
        # Assume view is always going to be placed into a QScrollArea
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def sizeHint(self):
        height = self.minimumHeight()
        return QSize(self.view_width, height)

    def minimumHeight(self) -> int:
        model = self.model()  # type: DeviceModel
        if model.rowCount() > 0:
            height = 0
            for row in range(self.model().rowCount()):
                row_height = self.sizeHintForRow(row)
                height += row_height
            height += len(model.headers) + 5
            return height
        return emptyViewHeight

    def minimumSizeHint(self):
        return self.sizeHint()


class DeviceDelegate(QStyledItemDelegate):

    padding = 6
    
    photos = _('Photos')
    videos = _('Videos')
    other = _('Other')
    probing_text = _('Probing device...')

    shading_intensity = 104

    def __init__(self, rapidApp, parent=None) -> None:
        super(DeviceDelegate, self).__init__(parent)
        self.rapidApp = rapidApp

        self.checkboxStyleOption = QStyleOptionButton()
        self.checkboxRect = QApplication.style().subElementRect(
            QStyle.SE_CheckBoxIndicator, self.checkboxStyleOption, None)  # type: QRect
        self.checkbox_right = self.checkboxRect.right()

        self.standard_font = QFont()  # type: QFont
        self.standard_font_bold = QFont(self.standard_font)
        self.standard_font_bold.setWeight(63)
        self.standard_metrics = QFontMetrics(self.standard_font)
        self.standard_height = self.standard_metrics.height()

        self.icon_size = icon_size()

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
        self.view_width = minPanelWidth()
        
        self.grey_border = QColor('#cdcdcd')

        alternate_color = QPalette().alternateBase().color()
        self.device_name_highlight_color = QColor(alternate_color).darker(105)

        # Height of the colored box that includes the device's
        # spinner/checkbox, icon & name
        self.device_name_strip_height = self.standard_height + self.padding * 3
        self.device_name_height = self.device_name_strip_height + self.padding

        self.icon_y_offset = (self.device_name_strip_height - self.icon_size) / 2
        self.checkbox_y_offset = (self.device_name_strip_height - self.checkboxRect.height()) // 2

        self.header_horizontal_padding = 8
        self.icon_x_offset = self.icon_size + self.header_horizontal_padding
        self.vertical_padding = 10

        # Calculate height of storage details:
        # text above gradient, gradient, and text below

        self.base_height = (self.padding * 2 + self.standard_height)
        self.storage_height = (self.standard_height + self.padding +
                               self.g_height + self.vertical_padding + self.details_height +
                               self.padding * 2)

        self.contextMenu = QMenu()
        removeDeviceAct = self.contextMenu.addAction(_('Remove'))
        removeDeviceAct.triggered.connect(self.removeDevice)
        rescanDeviceAct = self.contextMenu.addAction(_('Rescan'))
        rescanDeviceAct.triggered.connect(self.rescanDevice)
        # store the index in which the user right clicked
        self.clickedIndex = None  # type: QModelIndex

        # Spinner values
        self.spinner_color = QColor(Qt.black)
        self.spinner_roundness = 100.0
        self.spinner_min_trail_opacity = 0.0
        self.spinner_trail_fade_percent = 60.0
        self.spinner_line_length = max(self.icon_size // 4, 4)
        self.spinner_line_width = self.spinner_line_length // 2
        self.spinner_inner_radius = self.icon_size // 2 - self.spinner_line_length

    @pyqtSlot()
    def removeDevice(self) -> None:
        index = self.clickedIndex
        if index:
            scan_id = index.model().data(index, Roles.scan_id)  # type: Device
            self.rapidApp.removeDevice(scan_id)

    @pyqtSlot()
    def rescanDevice(self) -> None:
        index = self.clickedIndex
        if index:
            pass

    def lineCountDistanceFromPrimary(self, current, primary):
        distance = primary - current
        if distance < 0:
            distance += number_spinner_lines
        return distance

    def currentLineColor(self, countDistance: int) -> QColor:
        color = QColor(self.spinner_color)
        if countDistance == 0:
            return color
        minAlphaF = self.spinner_min_trail_opacity / 100.0
        distanceThreshold = int(math.ceil((number_spinner_lines - 1) *
                                          self.spinner_trail_fade_percent / 100.0))
        if countDistance > distanceThreshold:
            color.setAlphaF(minAlphaF)
        else:
            alphaDiff = color.alphaF() - minAlphaF
            gradient = alphaDiff / float(distanceThreshold + 1)
            resultAlpha = color.alphaF() - gradient * countDistance
            # If alpha is out of bounds, clip it.
            resultAlpha = min(1.0, max(0.0, resultAlpha))
            color.setAlphaF(resultAlpha)
        return color

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        painter.save()

        x = option.rect.x() + self.padding
        y = option.rect.y() + self.padding
        width = option.rect.width() - self.padding * 2

        standard_pen_color = painter.pen().color()

        view_type = index.data(Qt.DisplayRole)  # type: ViewRowType
        if view_type == ViewRowType.header:
            painter.setRenderHint(QPainter.Antialiasing, True)

            display_name, icon, device_state, rotation = index.data(Roles.device_details)

            deviceNameRect = QRect(option.rect.x(), option.rect.y(), option.rect.width(),
                                   self.device_name_strip_height)
            painter.fillRect(deviceNameRect, self.device_name_highlight_color)

            if device_state not in (DeviceState.scanning, DeviceState.downloading):
                checked = index.model().data(index, Qt.CheckStateRole)

                checkboxStyleOption = QStyleOptionButton()
                if checked:
                    checkboxStyleOption.state |= QStyle.State_On
                else:
                    checkboxStyleOption.state |= QStyle.State_Off
                checkboxStyleOption.state |= QStyle.State_Enabled

                checkboxStyleOption.rect = self.getCheckBoxRect(option)

                QApplication.style().drawControl(QStyle.CE_CheckBox, checkboxStyleOption, painter)

            else:
                # Draw spinning widget
                painter.setPen(Qt.NoPen)
                for i in range(0, number_spinner_lines):
                    painter.save()
                    painter.translate(x + self.spinner_inner_radius + self.spinner_line_length,
                                      y + 1 + self.spinner_inner_radius + self.spinner_line_length)
                    rotateAngle = float(360 * i) / float(number_spinner_lines)
                    painter.rotate(rotateAngle)
                    painter.translate(self.spinner_inner_radius, 0)
                    distance = self.lineCountDistanceFromPrimary(i, rotation)
                    color = self.currentLineColor(distance)
                    painter.setBrush(color)
                    rect = QRect(0, -self.spinner_line_width / 2, self.spinner_line_length,
                                 self.spinner_line_width)
                    painter.drawRoundedRect(rect, self.spinner_roundness, self.spinner_roundness,
                                            Qt.RelativeSize)
                    painter.restore()

                painter.setPen(Qt.SolidLine)
                painter.setPen(standard_pen_color)

            icon_x = float(x + self.icon_x_offset)
            icon_y = float(option.rect.y() + self.icon_y_offset)

            target = QRectF(icon_x, icon_y, self.icon_size, self.icon_size)
            source = QRectF(0, 0, self.icon_size, self.icon_size)
            painter.drawPixmap(target, icon, source)

            text_x = target.right() + self.header_horizontal_padding
            deviceNameRect.setLeft(text_x)
            painter.drawText(deviceNameRect, Qt.AlignLeft | Qt.AlignVCenter, display_name)

        else:
            assert view_type == ViewRowType.content

            device, storage_space = index.data(Roles.storage)  # type: Device, StorageSpace

            if storage_space is not None:

                painter.setFont(self.standard_font)

                if device.device_type == DeviceType.camera:
                    photo_key = make_key(FileType.photo, storage_space.path)
                    video_key = make_key(FileType.video, storage_space.path)
                    sum_key = storage_space.path
                else:
                    photo_key = FileType.photo
                    video_key = FileType.video
                    sum_key = None

                photos = _('%(no_photos)s Photos') % {
                    'no_photos': thousands(device.file_type_counter[photo_key])}
                videos = _('%(no_videos)s Videos') % {
                    'no_videos': thousands(device.file_type_counter[video_key])}
                photos_size = format_size_for_user(device.file_size_sum[photo_key])
                videos_size = format_size_for_user(device.file_size_sum[video_key])
                other_bytes = storage_space.bytes_total - device.file_size_sum.sum(sum_key) - \
                              storage_space.bytes_free
                other_size = format_size_for_user(other_bytes)
                bytes_total = format_size_for_user(storage_space.bytes_total, no_decimals=0)
                bytes_used = storage_space.bytes_total-storage_space.bytes_free

                percent_used = '{0:.0%}'.format(bytes_used / storage_space.bytes_total)
                # Translators: percentage full e.g. 75% full
                percent_used = '%s full' % percent_used

                # Device size
                device_size_x = x
                device_size_y = y + self.standard_height - self.padding
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

                if other_bytes:
                    color3 = QColor(CustomColors.color3.value)
                    other_g_width = other_bytes / storage_space.bytes_total * width
                    other_g_x = videos_g_x + videos_g_width
                    other_g_rect = QRectF(other_g_x, g_y, other_g_width, self.g_height)
                    linearGradient.setColorAt(0.2, color3.lighter(self.shading_intensity))
                    linearGradient.setColorAt(0.8, color3.darker(self.shading_intensity))
                    painter.fillRect(other_g_rect, QBrush(linearGradient))

                # Rectangle around spatial representation of sizes
                rect = QRectF(photos_g_x, g_y, width, self.g_height)
                painter.setPen(QColor('#cdcdcd'))
                painter.drawRect(rect)
                bottom = rect.bottom()

                # Details text indicating number and size of photos & videos
                gradient_width = 10

                # Photo details
                # =============

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
                # =============

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
                    # =============

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

            else:
                assert len(device.storage_space) == 0
                # Storage space not available, which for cameras means libgphoto2 is currently
                # still trying to access the device
                if device.device_type == DeviceType.camera:
                    painter.setPen(standard_pen_color)
                    painter.setFont(self.small_font)
                    probing_y = y + self.small_font_metrics.height()
                    probing_x = x
                    painter.drawText(probing_x, probing_y, self.probing_text)

        painter.restore()

    def getLeftPoint(self, option: QStyleOptionViewItem ) -> QPoint:
        return QPoint(option.rect.x() + self.padding, option.rect.y() + self.checkbox_y_offset)

    def getCheckBoxRect(self, option: QStyleOptionViewItem) -> QRect:
        return QRect(self.getLeftPoint(option), self.checkboxRect.size())

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        view_type = index.data(Qt.DisplayRole)  # type: ViewRowType
        if view_type == ViewRowType.header:
            height = self.device_name_height
        else:
            device, storage_space = index.data(Roles.storage)

            if storage_space is None:
                height = self.base_height
            else:
                height = self.storage_height
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
