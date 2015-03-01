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

from PyQt5.QtCore import (QAbstractTableModel, QModelIndex)
from PyQt5.QtWidgets import QTableView, QStyledItemDelegate
from PyQt5.QtGui import QPixmap

class DeviceTableModel(QAbstractTableModel):
    def __init__(self, parent):
        super(DeviceTableModel, self).__init__(parent)
        # device icon & name, size of images on the device (human readable),
        # copy progress (%), copy text, eject button (None if irrelevant),
        # process id, pulse

    def columnCount(self, parent=QModelIndex()):
        return 6

    def rowCount(self, parent=QModelIndex()):
        return 1

    def addDevice(self, scan_id: int, deviceIcon: QPixmap, deviceName: str,
                  ejectIcon: QPixmap, textDisplay: str):
        pass

class DeviceView(QTableView):
    pass

class DeviceDelegate(QStyledItemDelegate):
    pass