# SPDX-FileCopyrightText: Copyright 2016-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Display file system folders and allow the user to select one
"""

import logging
import os
import pathlib
import re

from PyQt5.QtCore import (
    QDir,
    QItemSelectionModel,
    QModelIndex,
    QPoint,
    QSize,
    QSortFilterProxyModel,
    Qt,
    pyqtSignal,
    pyqtSlot,
)
from PyQt5.QtGui import QFont, QPainter
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QAction,
    QFileSystemModel,
    QMenu,
    QSizePolicy,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeView,
)
from showinfm import show_in_file_manager

from raphodo.constants import (
    Roles,
    filtered_file_browser_directories,
    minFileSystemViewHeight,
    minPanelWidth,
    non_system_root_folders,
)
from raphodo.internationalisation.install import install_gettext
from raphodo.storage.storage import get_media_dir, gvfs_gphoto2_path
from raphodo.ui.viewutils import (
    TopFramedVerticalScrollBar,
    darkModeIcon,
    standard_font_size,
)
from raphodo.wsl.wslutils import wsl_filter_directories

install_gettext()


class FileSystemModel(QFileSystemModel):
    """
    Use Qt's built-in functionality to model the file system.

    Augment it by displaying provisional subfolders in the photo and video
    download destinations.
    """

    def __init__(self, parent) -> None:
        super().__init__(parent)

        # More filtering done in the FileSystemFilter
        self.setFilter(QDir.AllDirs | QDir.NoDotAndDotDot)

        s = standard_font_size()
        size = QSize(s, s)

        self.folder_icon = darkModeIcon(
            path="icons/folder.svg", size=size, soften_regular_mode_color=True
        )
        self.download_folder_icon = darkModeIcon(
            path="icons/folder-filled.svg", size=size, soften_regular_mode_color=True
        )

        self.setRootPath("/")

        # The next two values are set via FolderPreviewManager.update()
        # They concern provisional folders that will be used if the
        # download proceeds, and all files are downloaded.

        # First value: subfolders we've created to demonstrate to the user
        # where their files will be downloaded to
        self.preview_subfolders: set[str] = set()
        # Second value: subfolders that already existed, but that we still
        # want to indicate to the user where their files will be downloaded to
        self.download_subfolders: set[str] = set()

        # Folders that were actually used to download files into
        self.subfolders_downloaded_into: set[str] = set()

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if role == Qt.DecorationRole:
            path: str = index.data(QFileSystemModel.FilePathRole)
            if (
                path in self.download_subfolders
                or path in self.subfolders_downloaded_into
            ):
                return self.download_folder_icon
            else:
                return self.folder_icon
        if role == Roles.folder_preview:
            path = index.data(QFileSystemModel.FilePathRole)
            return (
                path in self.preview_subfolders
                and path not in self.subfolders_downloaded_into
            )

        return super().data(index, role)

    def add_subfolder_downloaded_into(self, path: str, download_folder: str) -> bool:
        """
        Add a path to the set of subfolders that indicate where files where
        downloaded.
        :param path: the full path to the folder
        :return: True if the path was not added before, else False
        """

        if path not in self.subfolders_downloaded_into:
            self.subfolders_downloaded_into.add(path)

            pl_subfolders = pathlib.Path(path)
            pl_download_folder = pathlib.Path(download_folder)

            for subfolder in pl_subfolders.parents:
                if pl_download_folder not in subfolder.parents:
                    break
                self.subfolders_downloaded_into.add(str(subfolder))
            return True
        return False


class FileSystemView(QTreeView):
    showSystemFolders = pyqtSignal(bool)
    filePathReset = pyqtSignal()

    def __init__(self, model: FileSystemModel, rapidApp, parent=None) -> None:
        super().__init__(parent)
        self.rapidApp = rapidApp
        self.fileSystemModel = model
        self.setHeaderHidden(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        self.setMinimumWidth(minPanelWidth())
        self.setMinimumHeight(minFileSystemViewHeight())
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.onCustomContextMenu)
        self.contextMenu = QMenu()
        self.openInFileBrowserAct = self.contextMenu.addAction(
            _("Open in File Browser...")
        )
        self.openInFileBrowserAct.triggered.connect(self.doOpenInFileBrowserAct)
        self.openInFileBrowserAct.setEnabled(self.rapidApp.file_manager is not None)
        self.clickedIndex: QModelIndex | None = None

        self.resetSelectionAct = self.contextMenu.addAction(_("Reset"))
        self.resetSelectionAct.triggered.connect(self.doResetSelectionAct)

        self.showSystemFoldersAct = QAction(
            _("Show System Folders"),
            self,
            enabled=True,
            checkable=True,
            triggered=self.doShowSystemFoldersAct,
        )
        self.contextMenu.addAction(self.showSystemFoldersAct)

        self.setVerticalScrollBar(TopFramedVerticalScrollBar(name="fileSystemView"))

    def hideColumns(self) -> None:
        """
        Call only after the model has been initialized
        """
        for i in (1, 2, 3):
            self.hideColumn(i)

    def goToPath(self, path: str, scrollTo: bool = True) -> None:
        """
        Select the path, expand its subfolders, and scroll to it
        :param path:
        :return:
        """
        if not path:
            return
        index = self.model().mapFromSource(self.fileSystemModel.index(path))
        self.setExpanded(index, True)
        selection = self.selectionModel()
        selection.select(
            index, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows
        )
        if scrollTo:
            self.scrollTo(index, QAbstractItemView.PositionAtTop)

    def expandPreviewFolders(self, path: str) -> bool:
        """
        Expand any unexpanded preview folders

        :param path: path under which to expand folders
        :return: True if path was expanded, else False
        """

        self.goToPath(path, scrollTo=True)
        if not path:
            return False

        expanded = False
        for path in self.fileSystemModel.download_subfolders:
            # print('path', path)
            index = self.model().mapFromSource(self.fileSystemModel.index(path))
            if not self.isExpanded(index):
                self.expand(index)
                expanded = True
        return expanded

    def expandPath(self, path) -> None:
        index = self.model().mapFromSource(self.fileSystemModel.index(path))
        if not self.isExpanded(index):
            self.expand(index)

    def onCustomContextMenu(self, point: QPoint) -> None:
        index = self.indexAt(point)
        self.showSystemFoldersAct.setChecked(self.rapidApp.prefs.show_system_folders)
        if index.isValid():
            self.clickedIndex = index
            self.openInFileBrowserAct.setEnabled(True)
        else:
            self.openInFileBrowserAct.setEnabled(False)
        self.showSystemFoldersAct.setEnabled(
            not self.rapidApp.prefs.source_or_destination_is_system_folder()
        )
        self.contextMenu.exec(self.mapToGlobal(point))

    @pyqtSlot()
    def doOpenInFileBrowserAct(self) -> None:
        index = self.clickedIndex
        if index:
            uri = self.fileSystemModel.filePath(index.model().mapToSource(index))
            logging.debug(
                "Calling show_in_file_manager() with %s and %s",
                self.rapidApp.file_manager,
                uri,
            )
            show_in_file_manager(path_or_uri=uri, open_not_select_directory=True)

    @pyqtSlot()
    def doShowSystemFoldersAct(self) -> None:
        self.showSystemFolders.emit(self.showSystemFoldersAct.isChecked())

    @pyqtSlot()
    def doResetSelectionAct(self) -> None:
        self.selectionModel().clear()
        self.filePathReset.emit()


class FileSystemFilter(QSortFilterProxyModel):
    """
    Filter out the display of RPD's cache and temporary directories, in addition to
    a set of standard directories that should not be displayed.
    """

    filterInvalidated = pyqtSignal()

    def __init__(self, parent: "RapidWindow" = None):  # noqa: F821
        super().__init__(parent)
        self.is_wsl2 = parent.is_wsl2
        self.prefs = parent.prefs
        if self.is_wsl2:
            self.filter_paths = wsl_filter_directories()
            # Filter out system created WSL working directories
            self.regex = re.compile(r"/wsl[\w]")
        else:
            self.filter_paths = set()
        self.filtered_dir_names = filtered_file_browser_directories
        self.non_system_root_folders = non_system_root_folders
        if get_media_dir().startswith("/run"):
            self.non_system_root_folders.append("/run")

    def setTempDirs(self, dirs: list[str]) -> None:
        filters = [os.path.basename(path) for path in dirs]
        self.filtered_dir_names = self.filtered_dir_names | set(filters)
        self.invalidateFilter()

    def filterAcceptsRow(
        self, sourceRow: int, sourceParent: QModelIndex = None
    ) -> bool:
        index: QModelIndex = self.sourceModel().index(sourceRow, 0, sourceParent)
        path: str = index.data(QFileSystemModel.FilePathRole)

        if not self.prefs.show_system_folders and path != "/":
            path_ok = False
            for folder in self.non_system_root_folders:
                if path.startswith(folder):
                    path_ok = True
                    break
            if not path_ok:
                return False

        if gvfs_gphoto2_path(path):
            logging.debug("Rejecting browsing path %s", path)
            return False

        if not self.filtered_dir_names and not self.is_wsl2:
            return True

        file_name = index.data(QFileSystemModel.FileNameRole)
        do_filter = (
            file_name not in self.filtered_dir_names and path not in self.filter_paths
        )

        if self.is_wsl2:
            do_filter = do_filter and self.regex.match(path) is None
        return do_filter

    @pyqtSlot(bool)
    def setShowSystemFolders(self, enabled: bool) -> None:
        self.prefs.show_system_folders = enabled
        self.invalidateFilter()
        self.filterInvalidated.emit()


class FileSystemDelegate(QStyledItemDelegate):
    """
    Italicize provisional download folders that were not already created
    """

    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        if index is None:
            return

        folder_preview = index.data(Roles.folder_preview)
        if folder_preview:
            font = QFont()
            font.setItalic(True)
            option.font = font

        super().paint(painter, option, index)
