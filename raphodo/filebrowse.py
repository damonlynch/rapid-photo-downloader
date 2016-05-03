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

"""
Display file system folders and allow the user to select one
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2016, Damon Lynch"

import os
from typing import List, Set

from PyQt5.QtCore import (QDir, Qt, QModelIndex, QItemSelectionModel, QSortFilterProxyModel)
from PyQt5.QtWidgets import (QTreeView, QAbstractItemView, QFileSystemModel, QSizePolicy,
                             QStyledItemDelegate, QStyleOptionViewItem)
from PyQt5.QtGui import QIcon
from PyQt5.QtGui import (QPainter, QFont)

import raphodo.qrc_resources as qrc_resources
from raphodo.constants import (minPanelWidth, minFileSystemViewHeight, Roles)
from raphodo.folderspreview import FoldersPreview


class FileSystemModel(QFileSystemModel):
    """
    Use Qt's built-in functionality to model the file system.

    Augment it by displaying provisional subfolders in the photo and video
    download destinations.
    """

    def __init__(self, parent) -> None:
        super().__init__(parent)
        # More filtering done in the FileSystemFilter
        self.setFilter(QDir.AllDirs | QDir.NoDotAndDotDot )
        self.folder_icon = QIcon(':/icons/folder.svg')
        self.download_folder_icon = QIcon(':/icons/folder-filled.svg')
        self.setRootPath('/')
        self.folders_preview = FoldersPreview()
        self.preview_subfolders = set()  # type: Set[str]
        self.download_subfolders = set()  # type: Set[str]

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if role == Qt.DecorationRole:
            path = index.data(QFileSystemModel.FilePathRole)  # type: str
            if path in self.download_subfolders:
                return self.download_folder_icon
            else:
                return self.folder_icon
        if role == Roles.folder_preview:
            path = index.data(QFileSystemModel.FilePathRole)
            return path in self.preview_subfolders

        return super().data(index, role)

    def update_preview_folders(self, folders_preview: FoldersPreview) -> None:
        self.folders_preview = folders_preview
        self.preview_subfolders = self.folders_preview.preview_subfolders()
        self.download_subfolders = self.folders_preview.download_subfolders()

    def remove_preview_folders(self) -> None:
        self.folders_preview.clean_all_generated_folders()


class FileSystemView(QTreeView):
    def __init__(self, model: FileSystemModel, parent=None) -> None:
        super().__init__(parent)
        self.fileSystemModel = model
        self.setHeaderHidden(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        self.setMinimumWidth(minPanelWidth())
        self.setMinimumHeight(minFileSystemViewHeight())

    def hideColumns(self) -> None:
        """
        Call only after the model has been initialized
        """
        for i in (1,2,3):
            self.hideColumn(i)

    def goToPath(self, path: str) -> None:
        index = self.model().mapFromSource(self.fileSystemModel.index(path))
        self.setExpanded(index, True)
        selection = self.selectionModel()
        selection.select(index, QItemSelectionModel.ClearAndSelect|QItemSelectionModel.Rows)
        self.scrollTo(index, QAbstractItemView.PositionAtTop)


class FileSystemFilter(QSortFilterProxyModel):
    """
    Filter out the display of RPD's cache and temporary directories
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.filtered_dir_names = set()

    def setTempDirs(self, dirs: List[str]) -> None:
        filters = [os.path.basename(path) for path in dirs]
        self.filtered_dir_names = self.filtered_dir_names | set(filters)
        self.invalidateFilter()

    def filterAcceptsRow(self, sourceRow: int, sourceParent: QModelIndex=None) -> bool:
        if not self.filtered_dir_names:
            return True

        index = self.sourceModel().index(sourceRow, 0, sourceParent)  # type: QModelIndex
        file_name = index.data(QFileSystemModel.FileNameRole)
        return file_name not in self.filtered_dir_names


class FileSystemDelegate(QStyledItemDelegate):
    """
    Italicize provisional download folders that were not already created
    """
    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        if index is None:
            return

        folder_preview = index.data(Roles.folder_preview)
        if folder_preview:
            font = QFont()
            font.setItalic(True)
            option.font = font

        super().paint(painter, option, index)
