# SPDX-FileCopyrightText: Copyright 2017-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Combobox widget to easily choose file locations
"""

import logging
import os

from PyQt5.QtCore import pyqtSignal, pyqtSlot
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QComboBox, QFileDialog

from raphodo.constants import (
    FileType,
    StandardFileLocations,
    max_remembered_destinations,
)
from raphodo.internationalisation.install import install_gettext
from raphodo.prefs.preferences import Preferences
from raphodo.storage.storage import (
    ValidMounts,
    platform_desktop_directory,
    platform_photos_directory,
    platform_videos_directory,
)
from raphodo.tools.utilities import data_file_path, make_path_end_snippets_unique

install_gettext()


class FolderCombo(QComboBox):
    """
    Combobox widget to easily choose file locations.
    """

    # Signal emitted whenever user chooses a path
    pathChosen = pyqtSignal(str)

    def __init__(
        self,
        parent,
        prefs: Preferences,
        file_type: FileType,
        file_chooser_title: str,
        special_dirs: tuple[StandardFileLocations] | None = None,
        valid_mounts: ValidMounts = None,
    ) -> None:
        super().__init__(parent)

        self.prefs = prefs
        self.rapidApp = parent.rapidApp
        self.is_wsl2 = self.rapidApp.is_wsl2
        if self.is_wsl2:
            self.wslDrives = self.rapidApp.wslDrives
        self.file_chooser_title = file_chooser_title
        self.file_type = file_type
        self.valid_mounts = valid_mounts
        self.special_dirs = special_dirs

        # Flag to indicate whether the combo box is displaying a path error
        self.invalid_path = False

        self.activated.connect(self.processPath)

        self._setup_entries()

    def _setup_entries(self) -> None:
        logging.debug("Rebuilding %s combobox entries...", self.file_type.name)

        # Track where the remembered destinations (paths) are in the pop up menu
        # -1 indicates there are none.
        self.destinations_start = -1

        # Home directory
        home_dir = os.path.expanduser("~")
        home_label = os.path.basename(home_dir)

        # Desktop directory, if it exists
        desktop_dir = platform_desktop_directory(home_on_failure=False)
        if desktop_dir is not None and os.path.isdir(desktop_dir):
            desktop_label = os.path.basename(desktop_dir)
        else:
            desktop_label = None

        # Any external mounts
        mounts = ()
        if not self.is_wsl2:
            if self.valid_mounts is not None:
                mounts = tuple(
                    (mount.name(), mount.rootPath())
                    for mount in self.valid_mounts.mountedValidMountPoints()
                )
        else:
            if self.valid_mounts is not None:
                mounts = tuple(
                    (self.wslDrives.displayName(mount.rootPath()), mount.rootPath())
                    for mount in self.valid_mounts.mountedValidMountPoints()
                )

        # Pictures and Videos directories, if required and if they exist
        pictures_dir = pictures_label = videos_dir = videos_label = None
        if self.special_dirs is not None:
            for dir in self.special_dirs:
                if dir == StandardFileLocations.pictures:
                    pictures_dir = platform_photos_directory(home_on_failure=False)
                    if pictures_dir is not None and os.path.isdir(pictures_dir):
                        pictures_label = os.path.basename(pictures_dir)
                elif dir == StandardFileLocations.videos:
                    videos_dir = platform_videos_directory(home_on_failure=False)
                    if videos_dir is not None and os.path.isdir(videos_dir):
                        videos_label = os.path.basename(videos_dir)

        self.addItem(QIcon(data_file_path("icons/home.svg")), home_label, home_dir)
        idx = 1
        if desktop_label:
            self.addItem(
                QIcon(data_file_path("icons/desktop.svg")), desktop_label, desktop_dir
            )
            idx += 1
        self.addItem(
            QIcon(data_file_path("icons/drive-harddisk.svg")), _("File System"), "/"
        )
        idx += 1

        if mounts:
            for name, path in mounts:
                self.addItem(
                    QIcon(data_file_path("icons/drive-removable-media.svg")), name, path
                )
                idx += 1

        if pictures_label is not None or videos_label is not None:
            self.insertSeparator(idx)
            idx += 1
            if pictures_label is not None:
                self.addItem(
                    QIcon(data_file_path("icons/pictures-folder.svg")),
                    pictures_label,
                    pictures_dir,
                )
                idx += 1
            if videos_label is not None:
                self.addItem(
                    QIcon(data_file_path("icons/videos-folder.svg")),
                    videos_label,
                    videos_dir,
                )
                idx += 1

        # Remembered paths / destinations
        dests = self._get_dests()
        valid_dests = [dest for dest in dests if dest and os.path.isdir(dest)]
        valid_names = make_path_end_snippets_unique(*valid_dests) if valid_dests else []

        if valid_names:
            folder_icon = QIcon(data_file_path("icons/folder.svg"))
            self.insertSeparator(idx)
            idx += 1
            self.destinations_start = idx
            for name, path in zip(valid_names, valid_dests):
                self.addItem(folder_icon, name, path)
                idx += 1

        self.insertSeparator(idx)
        idx += 1
        self.addItem(_("Other..."))
        logging.debug("...%s combobox entries added", self.count())

    def showPopup(self) -> None:
        """
        Refresh the combobox menu each time the menu is shown, to handle adding
        or removing of external volumes or default directories
        """

        self.refreshFolderList()
        super().showPopup()

    def refreshFolderList(self) -> None:
        """
        Refresh the combobox to reflect any file system changes
        """
        self.clear()
        self._setup_entries()
        self.setPath(self.chosen_path)

    def setPath(self, path: str) -> None:
        """
        Set the path displayed in the combo box.

        This must be called for the combobox to function properly.

        :param path: the path to display
        """

        self.chosen_path = path
        invalid = False

        dests = self._get_dests()

        standard_path = False

        if self.destinations_start == -1:
            # Deduct two from the count, to allow for the "Other..." at the end,
            # along with its separator
            default_end = self.count() - 2
        else:
            default_end = self.destinations_start

        default_start = 2 if self.invalid_path else 0

        for i in range(default_start, default_end):
            if self.itemData(i) == path:
                self.setCurrentIndex(i)
                standard_path = True
                logging.info(
                    "%s path %s is a default value or path to an external volume",
                    self.file_type.name,
                    path,
                )
                break

        if standard_path:
            if path in dests:
                logging.info(
                    "Removing %s from list of stored %s destinations because its now a "
                    "standard path",
                    path,
                    self.file_type.name,
                )
                self.prefs.del_list_value(self._get_dest_pref_key(), path)
        else:
            valid_dests = [dest for dest in dests if dest and os.path.isdir(dest)]
            if path in valid_dests:
                self._make_dest_active(path, len(valid_dests))
            elif os.path.isdir(path):
                # Add path to destinations in prefs, and regenerate the combobox entries
                self.prefs.add_list_value(
                    self._get_dest_pref_key(),
                    path,
                    max_list_size=max_remembered_destinations,
                )
                self.clear()
                self._setup_entries()
                # List may or may not have grown in size
                dests = self._get_dests()
                valid_dests = [dest for dest in dests if dest and os.path.isdir(dest)]
                self._make_dest_active(path, len(valid_dests))
            else:
                invalid = True
                # Translators: indicate in combobox that a path does not exist
                self.insertItem(
                    0,
                    QIcon(data_file_path("icons/error.svg")),
                    _("%s (location does not exist)") % os.path.basename(path),
                    path,
                )
                self.setCurrentIndex(0)
                if self.destinations_start != -1:
                    self.destinations_start += 1

                self.invalid_path = invalid

    def _make_dest_active(self, path: str, dest_len: int) -> None:
        """
        Make the path be the displayed value in the combobox
        **Key assumption**: the path is NOT one of the default paths
        or a path to an external volume

        :param path: the path to display
        :param dest_len: remembered paths (destinations) list length
        """

        for j in range(self.destinations_start, self.destinations_start + dest_len):
            if self.itemData(j) == path:
                self.setCurrentIndex(j)
                break

    def _get_dests(self) -> list[str]:
        if self.file_type == FileType.photo:
            return self.prefs.photo_backup_destinations
        else:
            return self.prefs.video_backup_destinations

    def _get_dest_pref_key(self) -> str:
        if self.file_type == FileType.photo:
            return "photo_backup_destinations"
        else:
            return "video_backup_destinations"

    @pyqtSlot(int)
    def processPath(self, index: int) -> None:
        """Handle the path that the user has chosen via the combo box"""

        if index == self.count() - 1:
            try:
                if os.path.isdir(self.chosen_path):
                    chosen_path = self.chosen_path
                else:
                    chosen_path = os.path.expanduser("~")
            except AttributeError:
                chosen_path = os.path.expanduser("~")
            path = QFileDialog.getExistingDirectory(
                self, self.file_chooser_title, chosen_path, QFileDialog.ShowDirsOnly
            )
            if path:
                self.setPath(path)
                self.pathChosen.emit(path)
            else:
                self.setPath(chosen_path)
        else:
            path = self.itemData(index)
            self.setPath(path)
            self.pathChosen.emit(path)
