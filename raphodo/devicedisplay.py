# Copyright (C) 2015-2017 Damon Lynch <damonlynch@gmail.com>
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
__copyright__ = "Copyright 2015-2017, Damon Lynch"

import math
from collections import namedtuple, defaultdict
from typing import Optional, Dict, List, Set
import logging
from pprint import pprint

from gettext import gettext as _

from PyQt5.QtCore import (QModelIndex, QSize, Qt, QPoint, QRect, QRectF,
                          QEvent, QAbstractItemModel, QAbstractListModel, pyqtSlot, QTimer)
from PyQt5.QtWidgets import (QStyledItemDelegate, QStyleOptionViewItem, QApplication, QStyle,
                             QListView, QStyleOptionButton, QAbstractItemView, QMenu, QWidget,
                             QStyleOptionToolButton)
from PyQt5.QtGui import (QPainter, QFontMetrics, QFont, QColor, QLinearGradient, QBrush, QPalette,
                         QPixmap, QPaintEvent, QGuiApplication, QPen, QIcon)

from raphodo.viewutils import RowTracker
from raphodo.constants import (DeviceState, FileType, CustomColors, DeviceType, Roles,
                               EmptyViewHeight, ViewRowType, minPanelWidth, Checked_Status,
                               DeviceDisplayPadding, DeviceShadingIntensity, DisplayingFilesOfType,
                               DownloadStatus, DownloadWarning, DownloadFailure)
from raphodo.devices import Device, display_devices
from raphodo.utilities import thousands, format_size_for_user
from raphodo.storage import StorageSpace
from raphodo.rpdfile import make_key
from raphodo.menubutton import MenuButton


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

    def __init__(self, parent, device_display_type: str) -> None:
        super().__init__(parent)
        self.rapidApp = parent
        self.device_display_type = device_display_type
        # scan_id: Device
        self.devices = {}  # type: Dict[int, Device]
        # scan_id: DeviceState
        self.spinner_state = {}  # type: Dict[int, DeviceState]
        # scan_id: bool
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

        # scan_id: 0.0-1.0
        self.percent_complete = defaultdict(float)  # type: Dict[int, float]

        self._rotation_position = 0  # type: int
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
        # TODO perhaps optimize which storage space is updated
        self.dataChanged.emit(self.index(row + 1, 0),
                              self.index(row + len(self.devices[scan_id].storage_space), 0))

    def setSpinnerState(self, scan_id: int, state: DeviceState) -> None:
        row_id = self.getHeaderRowId(scan_id)
        row = self.rows.row(row_id)

        current_state = self.spinner_state[scan_id]
        current_state_active = current_state in (DeviceState.scanning, DeviceState.downloading)

        if current_state_active and state in (DeviceState.idle, DeviceState.finished):
            self.row_ids_active.remove(row_id)
            self.percent_complete[scan_id] = 0.0
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
                        self._rotation_position, self.percent_complete[scan_id])
            elif role == Roles.storage:
                return device, self.storage[row_id]
            elif role == Roles.device_type:
                return device.device_type
            elif role == Roles.download_statuses:
                return device.download_statuses
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
            # In theory, update checkbox immediately, as selecting a very large number of thumbnails
            # can take time. However the code is probably wrong, as it doesn't work:
            # self.setCheckedValue(checked=value, scan_id=scan_id, row=row, log_state_change=False)
            # QApplication.instance().processEvents()
            self.rapidApp.thumbnailModel.checkAll(value, scan_id=scan_id)
            return True
        return False

    def logState(self) -> None:
        if len(self.devices):
            logging.debug("-- Device Model for %s --", self.device_display_type)
            logging.debug("Known devices: %s", ', '.join(self.devices[device].display_name
                 for device in self.devices))
            for row in self.rows.row_to_id:
                row_id = self.rows.row_to_id[row]
                scan_id = self.row_id_to_scan_id[row_id]
                device = self.devices[scan_id]
                logging.debug('Row %s: %s', row, device.display_name)
            logging.debug("Spinner states: %s", ', '.join("%s: %s" %
                              (self.devices[scan_id].display_name, self.spinner_state[scan_id].name)
                              for scan_id in self.spinner_state))
            logging.debug(', '.join('%s: %s' % (self.devices[scan_id].display_name,
                                Checked_Status[self.checked[scan_id]]) for scan_id in self.checked))

    def setCheckedValue(self, checked: Qt.CheckState,
                        scan_id: int,
                        row: Optional[int]=None,
                        log_state_change: Optional[bool]=True) -> None:
        logging.debug("Setting %s checkbox to %s", self.devices[scan_id].display_name,
                      Checked_Status[checked])
        if row is None:
            row_id = self.scan_id_to_row_ids[scan_id][0]
            row = self.rows.row(row_id)
        self.checked[scan_id] = checked
        self.dataChanged.emit(self.index(row, 0),self.index(row, 0))

        if log_state_change:
            self.logState()

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
    def __init__(self, rapidApp, parent=None) -> None:
        super().__init__(parent)
        self.rapidApp = rapidApp
        # Disallow the user from being able to select the table cells
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.view_width = minPanelWidth()
        # Assume view is always going to be placed into a splitter
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)

        self.setMouseTracking(True)
        self.entered.connect(self.rowEntered)

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
        return EmptyViewHeight

    def minimumSizeHint(self):
        return self.sizeHint()

    @pyqtSlot(QModelIndex)
    def rowEntered(self, index: QModelIndex) -> None:
        if index.data() == ViewRowType.header and len(self.rapidApp.devices) > 1:
            scan_id = index.data(Roles.scan_id)
            self.rapidApp.thumbnailModel.highlightDeviceThumbs(scan_id=scan_id)


BodyDetails = namedtuple('BodyDetails', 'bytes_total_text, bytes_total, '
                                        'percent_used_text, '
                                        'bytes_free_of_total, '
                                        'comp1_file_size_sum, comp2_file_size_sum, '
                                        'comp3_file_size_sum, comp4_file_size_sum, '
                                        'comp1_text, comp2_text, comp3_text, '
                                        'comp4_text, '
                                        'comp1_size_text, comp2_size_text, '
                                        'comp3_size_text, comp4_size_text, '
                                        'color1, color2, color3,'
                                        'displaying_files_of_type')


def standard_height():
    return QFontMetrics(QFont()).height()

def device_name_height():
    return  standard_height() + DeviceDisplayPadding * 3

def device_header_row_height():
    return device_name_height() +  DeviceDisplayPadding

def device_name_highlight_color():
    palette = QPalette()

    alternate_color = palette.alternateBase().color()
    return QColor(alternate_color).darker(105)


class EmulatedHeaderRow(QWidget):
    """
    When displaying a view of a destination or source folder, display an
    empty colored strip with no icon when the folder is not yet valid.
    """

    def __init__(self, select_text: str) -> None:
        """

        :param select_text: text to be displayed e.g. 'Select a destination folder'
        :return:
        """
        super().__init__()
        self.setMinimumSize(1, device_header_row_height())
        self.select_text = select_text
        palette = QPalette()
        palette.setColor(QPalette.Window, palette.color(palette.Base))
        self.setAutoFillBackground(True)
        self.setPalette(palette)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter()
        painter.begin(self)
        rect = self.rect()  # type: QRect
        rect.setHeight(device_name_height())
        painter.fillRect(rect, device_name_highlight_color())
        rect.adjust(DeviceDisplayPadding, 0, 0, 0)
        font = QFont()
        font.setItalic(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, self.select_text)
        painter.end()


class DeviceDisplay:
    """
    Graphically render the storage space, and photos and videos that
    are currently in it or will be downloaded into it.

    Used in list view by devices / this computer, and in destination
    custom widget.
    """

    padding = DeviceDisplayPadding
    shading_intensity = DeviceShadingIntensity

    def __init__(self, menuButtonIcon: Optional[QIcon]=None) -> None:
        self.menuButtonIcon = menuButtonIcon

        self.sample1_width = self.sample2_width = 40
        self.rendering_destination = True

        self.standard_font = QFont()  # type: QFont
        self.standard_metrics = QFontMetrics(self.standard_font)
        self.standard_height = standard_height()

        self.icon_size = icon_size()

        self.small_font = QFont(self.standard_font)
        self.small_font.setPointSize(self.standard_font.pointSize() - 2)
        self.small_font_metrics = QFontMetrics(self.small_font)
        self.small_height = self.small_font_metrics.height()

        # Height of the graqient bar that visually shows storage use
        self.g_height = self.standard_height

        # Height of the details about the storage e.g. number of photos
        # videos, etc.
        self.details_height = self.small_font_metrics.height() * 2 + 2
        self.view_width = minPanelWidth()

        self.device_name_highlight_color = device_name_highlight_color()

        self.storage_border = QColor('#bcbcbc')

        # Height of the colored box that includes the device's
        # spinner/checkbox, icon & name
        self.device_name_strip_height = device_name_height()
        self.device_name_height = device_header_row_height()

        self.icon_y_offset = (self.device_name_strip_height - self.icon_size) / 2

        self.header_horizontal_padding = 8
        self.icon_x_offset = 0
        self.vertical_padding = 10

        # Calculate height of storage details:
        # text above gradient, gradient, and text below

        # Base height is when there is no storage space to display
        self.base_height = (self.padding * 2 + self.standard_height)

        # Storage height is when there is storage space to display
        self.storage_height = (self.standard_height + self.padding +
                               self.g_height + self.vertical_padding + self.details_height +
                               self.padding * 2)
        
        self.emptySpaceColor = QColor('#f2f2f2')
        self.subtlePenColor = QColor('#6d6d6d')

        self.menu_button_padding = 3
        self.menuHighlightPen =  QPen(QBrush(self.subtlePenColor), 0.5)

    def v_align_header_pixmap(self, y: int, pixmap_height: int) -> float:
        return y + (self.device_name_strip_height / 2 - pixmap_height / 2)

    def paint_header(self, painter: QPainter, x: int, y: int, width: int,
                     display_name: str, icon: QPixmap, highlight_menu: bool=False) -> None:
        """
        Render the header portion, which contains the device / folder name, icon, and
        for download sources, a spinner or checkbox.

        If needed, draw a pixmap for for a drop-down menu.
        """

        painter.setRenderHint(QPainter.Antialiasing, True)

        deviceNameRect = QRect(x, y, width, self.device_name_strip_height)
        painter.fillRect(deviceNameRect, self.device_name_highlight_color)

        icon_x = float(x + self.padding + self.icon_x_offset)
        icon_y = self.v_align_header_pixmap(y, self.icon_size)

        target = QRectF(icon_x, icon_y, self.icon_size, self.icon_size)
        source = QRectF(0, 0, self.icon_size, self.icon_size)
        painter.drawPixmap(target, icon, source)

        text_x = target.right() + self.header_horizontal_padding
        deviceNameRect.setLeft(text_x)
        painter.drawText(deviceNameRect, Qt.AlignLeft | Qt.AlignVCenter, display_name)

        if self.menuButtonIcon:
            size = icon_size()
            rect = self.menu_button_rect(x, y, width)
            if highlight_menu:
                pen = painter.pen()
                painter.setPen(self.menuHighlightPen)
                painter.drawRoundedRect(rect, 2.0, 2.0)
                painter.setPen(pen)
            button_x = rect.x() + self.menu_button_padding
            button_y = rect.y() + self.menu_button_padding
            pixmap = self.menuButtonIcon.pixmap(QSize(size, size))
            painter.drawPixmap(button_x, button_y, pixmap)

    def menu_button_rect(self, x: int, y: int, width: int) -> QRectF:
        size = icon_size() + self.menu_button_padding * 2
        button_x = x + width - size - self.padding
        button_y = y + self.device_name_strip_height / 2 - size / 2
        return QRectF(button_x, button_y, size, size)

    def paint_body(self, painter: QPainter,
                   x: int, y: int,
                   width: int,
                   details: BodyDetails) -> None:
        """
        Render the usage portion, which contains basic storage space information,
        a colored bar with a gradient that visually represents allocation of the
        storage space, and details about the size and number of photos / videos.

        For download destinations, also displays excess usage.
        """

        x = x + self.padding
        y = y + self.padding
        width = width - self.padding * 2
        d = details

        painter.setRenderHint(QPainter.Antialiasing, False)

        painter.setFont(self.small_font)

        standard_pen_color = painter.pen().color()

        device_size_x = x
        device_size_y = y + self.standard_height - self.padding

        text_rect = QRect(device_size_x, y - self.padding, width, self.standard_height)


        if self.rendering_destination:
            # bytes free of total size e..g 123 MB free of 2 TB
            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignBottom, d.bytes_free_of_total)

            # Render the used space in the gradient bar before rendering the space
            # that will be taken by photos and videos
            comp1_file_size_sum = d.comp3_file_size_sum
            comp2_file_size_sum = d.comp1_file_size_sum
            comp3_file_size_sum = d.comp2_file_size_sum
            color1 = d.color3
            color2 = d.color1
            color3 = d.color2
        else:
            # Device size e.g. 32 GB
            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignBottom, d.bytes_total_text)
            # Percent used e.g. 79%
            painter.drawText(text_rect, Qt.AlignRight | Qt.AlignBottom, d.percent_used_text)

            # Don't change the order
            comp1_file_size_sum = d.comp1_file_size_sum
            comp2_file_size_sum = d.comp2_file_size_sum
            comp3_file_size_sum = d.comp3_file_size_sum
            color1 = d.color1
            color2 = d.color2
            color3 = d.color3

        skip_comp1 = d.displaying_files_of_type == DisplayingFilesOfType.videos
        skip_comp2 = d.displaying_files_of_type == DisplayingFilesOfType.photos
        skip_comp3 = d.comp3_size_text == 0

        photos_g_x = device_size_x
        g_y = device_size_y + self.padding
        if d.bytes_total:
            photos_g_width = (comp1_file_size_sum / d.bytes_total * width)
            linearGradient = QLinearGradient(photos_g_x, g_y, photos_g_x, g_y + self.g_height)

        rect = QRectF(photos_g_x, g_y, width, self.g_height)
        # Apply subtle shade to empty space
        painter.fillRect(rect, self.emptySpaceColor)

        if comp1_file_size_sum and d.bytes_total:
            photos_g_rect = QRectF(photos_g_x, g_y, photos_g_width, self.g_height)
            linearGradient.setColorAt(0.2, color1.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, color1.darker(self.shading_intensity))
            painter.fillRect(photos_g_rect, QBrush(linearGradient))
        else:
            photos_g_width = 0

        videos_g_x = photos_g_x + photos_g_width
        if comp2_file_size_sum and d.bytes_total:
            videos_g_width = (comp2_file_size_sum / d.bytes_total * width)
            videos_g_rect = QRectF(videos_g_x, g_y, videos_g_width, self.g_height)
            linearGradient.setColorAt(0.2, color2.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, color2.darker(self.shading_intensity))
            painter.fillRect(videos_g_rect, QBrush(linearGradient))
        else:
            videos_g_width = 0

        if comp3_file_size_sum and d.bytes_total:
            other_g_width = comp3_file_size_sum / d.bytes_total * width
            other_g_x = videos_g_x + videos_g_width
            other_g_rect = QRectF(other_g_x, g_y, other_g_width, self.g_height)
            linearGradient.setColorAt(0.2, color3.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, color3.darker(self.shading_intensity))
            painter.fillRect(other_g_rect, QBrush(linearGradient))
        else:
            other_g_width = 0
        

        if d.comp4_file_size_sum and d.bytes_total:
            # Excess usage, only for download destinations
            color4 = QColor(CustomColors.color6.value)
            comp4_g_width = d.comp4_file_size_sum / d.bytes_total * width
            comp4_g_x = x + width - comp4_g_width
            comp4_g_rect = QRectF(comp4_g_x, g_y, comp4_g_width, self.g_height)
            linearGradient.setColorAt(0.2, color4.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, color4.darker(self.shading_intensity))
            painter.fillRect(comp4_g_rect, QBrush(linearGradient))

        # Rectangle around spatial representation of sizes
        painter.setPen(self.storage_border)
        painter.drawRect(rect)
        bottom = rect.bottom()

        # Details text indicating number and size of components 1 & 2
        gradient_width = 10

        spacer = 3
        details_y = bottom + self.vertical_padding

        painter.setFont(self.small_font)
        
        # Component 4 details
        # (excess usage, only displayed if the storage space is not sufficient)
        # =====================================================================
        
        if d.comp4_file_size_sum:
            # Gradient
            comp4_g2_x =  x
            comp4_g2_rect = QRect(comp4_g2_x, details_y, gradient_width, self.details_height)
            linearGradient = QLinearGradient(comp4_g2_x, details_y,
                                            comp4_g2_x, details_y + self.details_height)
            linearGradient.setColorAt(0.2, color4.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, color4.darker(self.shading_intensity))
            painter.fillRect(comp4_g2_rect, QBrush(linearGradient))
            painter.setPen(self.storage_border)
            painter.drawRect(comp4_g2_rect)

            # Text
            comp4_x = comp4_g2_x + gradient_width + spacer
            comp4_no_width = self.small_font_metrics.boundingRect(d.comp4_text).width()
            comp4_size_width = self.small_font_metrics.boundingRect(d.comp4_size_text).width()
            comp4_width = max(comp4_no_width, comp4_size_width, self.sample1_width)
            comp4_rect = QRect(comp4_x, details_y, comp4_width, self.details_height)

            painter.setPen(standard_pen_color)
            painter.drawText(comp4_rect, Qt.AlignLeft|Qt.AlignTop, d.comp4_text)
            painter.drawText(comp4_rect, Qt.AlignLeft|Qt.AlignBottom, d.comp4_size_text)
            photos_g2_x = comp4_rect.right() + 10
        else:
            photos_g2_x =  x

        # Component 1 details
        # ===================
        
        if not skip_comp1:

            # Gradient
            photos_g2_rect = QRect(photos_g2_x, details_y, gradient_width, self.details_height)
            linearGradient = QLinearGradient(photos_g2_x, details_y,
                                            photos_g2_x, details_y + self.details_height)
            linearGradient.setColorAt(0.2, d.color1.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, d.color1.darker(self.shading_intensity))
            painter.fillRect(photos_g2_rect, QBrush(linearGradient))
            painter.setPen(self.storage_border)
            painter.drawRect(photos_g2_rect)

            # Text
            photos_x = photos_g2_x + gradient_width + spacer
            photos_no_width = self.small_font_metrics.boundingRect(d.comp1_text).width()
            photos_size_width = self.small_font_metrics.boundingRect(d.comp1_size_text).width()
            photos_width = max(photos_no_width, photos_size_width, self.sample1_width)
            photos_rect = QRect(photos_x, details_y, photos_width, self.details_height)

            painter.setPen(standard_pen_color)
            painter.drawText(photos_rect, Qt.AlignLeft|Qt.AlignTop, d.comp1_text)
            painter.drawText(photos_rect, Qt.AlignLeft|Qt.AlignBottom, d.comp1_size_text)
            videos_g2_x = photos_rect.right() + 10

        else:
            videos_g2_x = photos_g2_x

        # Component 2 details
        # ===================

        if not skip_comp2:
            # Gradient
            videos_g2_rect = QRect(videos_g2_x, details_y, gradient_width, self.details_height)
            linearGradient.setColorAt(0.2, d.color2.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, d.color2.darker(self.shading_intensity))
            painter.fillRect(videos_g2_rect, QBrush(linearGradient))
            painter.setPen(self.storage_border)
            painter.drawRect(videos_g2_rect)

            #Text
            videos_x = videos_g2_x + gradient_width + spacer
            videos_no_width = self.small_font_metrics.boundingRect(d.comp2_text).width()
            videos_size_width = self.small_font_metrics.boundingRect(d.comp2_size_text).width()
            videos_width = max(videos_no_width, videos_size_width, self.sample2_width)
            videos_rect = QRect(videos_x, details_y, videos_width, self.details_height)

            painter.setPen(standard_pen_color)
            painter.drawText(videos_rect, Qt.AlignLeft|Qt.AlignTop, d.comp2_text)
            painter.drawText(videos_rect, Qt.AlignLeft|Qt.AlignBottom, d.comp2_size_text)

            other_g2_x = videos_rect.right() + 10
        else:
            other_g2_x = videos_g2_x

        if not skip_comp3 and (d.comp3_file_size_sum or self.rendering_destination):
            # Other details
            # =============

            # Gradient

            other_g2_rect = QRect(other_g2_x, details_y, gradient_width, self.details_height)
            linearGradient.setColorAt(0.2, d.color3.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, d.color3.darker(self.shading_intensity))
            painter.fillRect(other_g2_rect, QBrush(linearGradient))
            painter.setPen(self.storage_border)
            painter.drawRect(other_g2_rect)

            #Text
            other_x = other_g2_x + gradient_width + spacer
            other_no_width = self.small_font_metrics.boundingRect(d.comp3_text).width()
            other_size_width = self.small_font_metrics.boundingRect(d.comp3_size_text).width()
            other_width = max(other_no_width, other_size_width)
            other_rect = QRect(other_x, details_y, other_width, self.details_height)

            painter.setPen(standard_pen_color)
            painter.drawText(other_rect, Qt.AlignLeft|Qt.AlignTop, d.comp3_text)
            painter.drawText(other_rect, Qt.AlignLeft|Qt.AlignBottom, d.comp3_size_text)


class AdvancedDeviceDisplay(DeviceDisplay):
    """
    Subclass to handle header for download devices/ This Computer
    """

    def __init__(self, comp1_sample: str, comp2_sample: str):
        super().__init__()

        self.sample1_width = self.small_font_metrics.boundingRect(comp1_sample).width()
        self.sample2_width = self.small_font_metrics.boundingRect(comp2_sample).width()

        self.rendering_destination = False

        self.checkboxStyleOption = QStyleOptionButton()
        self.checkboxRect = QApplication.style().subElementRect(
            QStyle.SE_CheckBoxIndicator, self.checkboxStyleOption, None)  # type: QRect
        self.checkbox_right = self.checkboxRect.right()
        self.checkbox_y_offset = (self.device_name_strip_height - self.checkboxRect.height()) // 2

        # Spinner values
        self.spinner_color = QColor(Qt.black)
        self.spinner_roundness = 100.0
        self.spinner_min_trail_opacity = 0.0
        self.spinner_trail_fade_percent = 60.0
        self.spinner_line_length = max(self.icon_size // 4, 4)
        self.spinner_line_width = self.spinner_line_length // 2
        self.spinner_inner_radius = self.icon_size // 2 - self.spinner_line_length

        self.icon_x_offset = self.icon_size + self.header_horizontal_padding

        self.downloadedPixmap = QPixmap(':/downloaded.png')
        self.downloadedWarningPixmap = QPixmap(':/downloaded-with-warning.png')
        self.downloadedErrorPixmap = QPixmap(':/downloaded-with-error.png')
        self.downloaded_icon_y = self.v_align_header_pixmap(0, self.downloadedPixmap.height())

        palette = QGuiApplication.instance().palette()
        color = palette.highlight().color()
        self.progressBarPen = QPen(QBrush(color), 2.0)

    def paint_header(self, painter: QPainter,
                     x: int, y: int, width: int,
                     display_name: str,
                     icon: QPixmap,
                     device_state: DeviceState,
                     rotation: int,
                     checked: bool,
                     download_statuses: Set[DownloadStatus],
                     percent_complete: float) -> None:

        standard_pen_color = painter.pen().color()

        super().paint_header(painter=painter, x=x, y=y, width=width, display_name=display_name,
                             icon=icon)

        if device_state == DeviceState.finished:
            # indicate that no more files can be downloaded from the device, and if there
            # were any errors or warnings
            if download_statuses & DownloadFailure:
                pixmap = self.downloadedErrorPixmap
            elif download_statuses & DownloadWarning:
                pixmap = self.downloadedWarningPixmap
            else:
                pixmap = self.downloadedPixmap
            painter.drawPixmap(x + self.padding, y + self.downloaded_icon_y, pixmap)

        elif device_state not in (DeviceState.scanning, DeviceState.downloading):

            checkboxStyleOption = QStyleOptionButton()
            if checked == Qt.Checked:
                checkboxStyleOption.state |= QStyle.State_On
            elif checked == Qt.PartiallyChecked:
                checkboxStyleOption.state |= QStyle.State_NoChange
            else:
                checkboxStyleOption.state |= QStyle.State_Off
            checkboxStyleOption.state |= QStyle.State_Enabled

            checkboxStyleOption.rect = self.getCheckBoxRect(x, y)

            QApplication.style().drawControl(QStyle.CE_CheckBox, checkboxStyleOption, painter)

        else:
            x = x + self.padding
            y = y + self.padding
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

            if percent_complete:
                painter.setPen(self.progressBarPen)
                x1 = x - self.padding
                y = y - self.padding + self.device_name_strip_height - 1
                x2 = x1 + percent_complete * width
                painter.drawLine(x1, y, x2, y)

            painter.setPen(Qt.SolidLine)
            painter.setPen(standard_pen_color)

    def paint_alternate(self, painter: QPainter,  x: int, y: int, text: str) -> None:

        standard_pen_color = painter.pen().color()

        painter.setPen(standard_pen_color)
        painter.setFont(self.small_font)
        probing_y = y + self.small_font_metrics.height()
        probing_x = x + self.padding
        painter.drawText(probing_x, probing_y, text)

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

    def getLeftPoint(self, x: int, y: int) -> QPoint:
        return QPoint(x + self.padding, y + self.checkbox_y_offset)

    def getCheckBoxRect(self, x: int, y: int) -> QRect:
        return QRect(self.getLeftPoint(x, y), self.checkboxRect.size())


class DeviceDelegate(QStyledItemDelegate):

    padding = DeviceDisplayPadding
    
    other = _('Other')
    probing_text = _('Probing device...')

    shading_intensity = DeviceShadingIntensity

    def __init__(self, rapidApp, parent=None) -> None:
        super().__init__(parent)
        self.rapidApp = rapidApp

        sample_number = thousands(999)
        sample_no_photos = '{} {}'.format(sample_number, _('Photos'))
        sample_no_videos = '{} {}'.format(sample_number, _('Videos'))

        self.deviceDisplay = AdvancedDeviceDisplay(comp1_sample=sample_no_photos,
                                                   comp2_sample=sample_no_videos)

        self.contextMenu = QMenu()
        self.ignoreDeviceAct = self.contextMenu.addAction(_('Temporarily ignore this device'))
        self.ignoreDeviceAct.triggered.connect(self.ignoreDevice)
        self.blacklistDeviceAct = self.contextMenu.addAction(_('Permanently ignore this device'))
        self.blacklistDeviceAct.triggered.connect(self.blacklistDevice)
        self.rescanDeviceAct = self.contextMenu.addAction(_('Rescan'))
        self.rescanDeviceAct.triggered.connect(self.rescanDevice)
        # store the index in which the user right clicked
        self.clickedIndex = None  # type: QModelIndex

    @pyqtSlot()
    def ignoreDevice(self) -> None:
        index = self.clickedIndex
        if index:
            scan_id = index.data(Roles.scan_id)  # type: int
            self.rapidApp.removeDevice(scan_id=scan_id, ignore_in_this_program_instantiation=True)
            self.clickedIndex = None  # type: QModelIndex

    @pyqtSlot()
    def blacklistDevice(self) -> None:
        index = self.clickedIndex
        if index:
            scan_id = index.data(Roles.scan_id)  # type: int
            self.rapidApp.blacklistDevice(scan_id=scan_id)
            self.clickedIndex = None  # type: QModelIndex

    @pyqtSlot()
    def rescanDevice(self) -> None:
        index = self.clickedIndex
        if index:
            scan_id = index.data(Roles.scan_id)  # type: int
            self.rapidApp.rescanDevice(scan_id=scan_id)
            self.clickedIndex = None  # type: QModelIndex

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        painter.save()

        x = option.rect.x()
        y = option.rect.y()
        width = option.rect.width()

        view_type = index.data(Qt.DisplayRole)  # type: ViewRowType
        if view_type == ViewRowType.header:
            display_name, icon, device_state, rotation, percent_complete = index.data(
                Roles.device_details)
            if device_state == DeviceState.finished:
                download_statuses = index.data(Roles.download_statuses)  # type: Set[DownloadStatus]
            else:
                download_statuses = set()

            if device_state not in (DeviceState.scanning, DeviceState.downloading):
                checked = index.model().data(index, Qt.CheckStateRole)
            else:
                checked = None

            self.deviceDisplay.paint_header(painter=painter, x=x, y=y, width=width,
                                            rotation=rotation,
                                            icon=icon,
                                            device_state=device_state,
                                            display_name=display_name,
                                            checked=checked,
                                            download_statuses=download_statuses,
                                            percent_complete=percent_complete)

        else:
            assert view_type == ViewRowType.content

            device, storage_space = index.data(Roles.storage)  # type: Device, StorageSpace

            if storage_space is not None:

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
                bytes_total_text = format_size_for_user(storage_space.bytes_total, no_decimals=0)
                bytes_used = storage_space.bytes_total-storage_space.bytes_free

                percent_used = '{0:.0%}'.format(bytes_used / storage_space.bytes_total)
                # Translators: percentage full e.g. 75% full
                percent_used = _('%s full') % percent_used

                details = BodyDetails(bytes_total_text=bytes_total_text,
                                  bytes_total=storage_space.bytes_total,
                                  percent_used_text=percent_used,
                                  bytes_free_of_total='',
                                  comp1_file_size_sum=device.file_size_sum[photo_key],
                                  comp2_file_size_sum=device.file_size_sum[video_key],
                                  comp3_file_size_sum=other_bytes,
                                  comp4_file_size_sum=0,
                                  comp1_text = photos,
                                  comp2_text = videos,
                                  comp3_text = self.other,
                                  comp4_text = '',
                                  comp1_size_text=photos_size,
                                  comp2_size_text=videos_size,
                                  comp3_size_text=other_size,
                                  comp4_size_text='',
                                  color1=QColor(CustomColors.color1.value),
                                  color2=QColor(CustomColors.color2.value),
                                  color3=QColor(CustomColors.color3.value),
                                  displaying_files_of_type=DisplayingFilesOfType.photos_and_videos
                                  )
                self.deviceDisplay.paint_body(painter=painter, x=x, y=y, width=width,
                                              details=details)

            else:
                assert len(device.storage_space) == 0
                # Storage space not available, which for cameras means libgphoto2 is currently
                # still trying to access the device
                if device.device_type == DeviceType.camera:
                    self.deviceDisplay.paint_alternate(painter=painter, x=x, y=y,
                                                       text=self.probing_text)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        view_type = index.data(Qt.DisplayRole)  # type: ViewRowType
        if view_type == ViewRowType.header:
            height = self.deviceDisplay.device_name_height
        else:
            device, storage_space = index.data(Roles.storage)

            if storage_space is None:
                height = self.deviceDisplay.base_height
            else:
                height = self.deviceDisplay.storage_height
        return QSize(self.deviceDisplay.view_width, height)

    def editorEvent(self, event: QEvent,
                    model: QAbstractItemModel,
                    option: QStyleOptionViewItem,
                    index: QModelIndex) -> bool:
        """
        Change the data in the model and the state of the checkbox
        if the user presses the left mousebutton or presses
        Key_Space or Key_Select and this cell is editable. Otherwise do nothing.
        """

        if (event.type() == QEvent.MouseButtonRelease or event.type() ==
            QEvent.MouseButtonDblClick):
            if event.button() == Qt.RightButton:
                # Disable ignore and blacklist menus if the device is a This Computer path

                self.clickedIndex = index

                scan_id = index.data(Roles.scan_id)
                device_type = index.data(Roles.device_type)
                downloading = self.rapidApp.devices.downloading

                self.ignoreDeviceAct.setEnabled(device_type != DeviceType.path and
                                                scan_id not in downloading)
                self.blacklistDeviceAct.setEnabled(device_type != DeviceType.path and
                                                   scan_id not in downloading)
                self.rescanDeviceAct.setEnabled(scan_id not in downloading)

                view = self.rapidApp.mapView(scan_id)
                globalPos = view.viewport().mapToGlobal(event.pos())
                self.contextMenu.popup(globalPos)
                return False
            if event.button() != Qt.LeftButton or not self.deviceDisplay.getCheckBoxRect(
                    option.rect.x(), option.rect.y()).contains(event.pos()):
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
