# Copyright (C) 2016 Damon Lynch <damonlynch@gmail.com>

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

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2016, Damon Lynch"

from PyQt5.QtCore import (QDir, Qt, QModelIndex)
from PyQt5.QtWidgets import (QTreeView, QAbstractItemView, QFileSystemModel)
from PyQt5.QtGui import (QIcon)

import qrc_resources

class FileSystemModel(QFileSystemModel):
    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.setRootPath('/')
        self.setFilter(QDir.Dirs|QDir.AllDirs|QDir.NoDotAndDotDot|QDir.Drives)
        self.folder = QIcon(':/icons/folder.svg')

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if role == Qt.DecorationRole:
            return self.folder
        return super().data(index, role)

class FileSystemView(QTreeView):
    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)

    def hideColumns(self) -> None:
        """
        Call only after the model has been initialized
        """
        for i in (1,2,3):
            self.hideColumn(i)

