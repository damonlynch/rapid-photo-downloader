# Copyright (C) 2016-2017 Damon Lynch <damonlynch@gmail.com>

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
Display download destination details
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2016-2017, Damon Lynch"

import os
import math
from typing import Optional, Dict, Tuple, Union, DefaultDict, Set
import logging
from collections import defaultdict
from gettext import gettext as _


from PyQt5.QtCore import (QSize, Qt, QStorageInfo, QRect, pyqtSlot, QPoint)
from PyQt5.QtWidgets import (QStyleOptionFrame, QStyle, QStylePainter, QWidget, QSplitter,
                             QSizePolicy, QAction, QMenu, QActionGroup)
from PyQt5.QtGui import (QColor, QPixmap, QIcon, QPaintEvent, QPalette, QMouseEvent)


from raphodo.devicedisplay import DeviceDisplay, BodyDetails, icon_size
from raphodo.storage import (StorageSpace, get_path_display_name, get_mount_size)
from raphodo.constants import (CustomColors, DestinationDisplayType, DisplayingFilesOfType,
                               DestinationDisplayMousePos, PresetPrefType, NameGenerationType,
                               DestinationDisplayTooltipState, FileType)
from raphodo.utilities import thousands, format_size_for_user
from raphodo.rpdfile import FileTypeCounter, Photo, Video
from raphodo.nameeditor import PrefDialog, make_subfolder_menu_entry
import raphodo.generatenameconfig as gnc
from raphodo.generatenameconfig import *


def make_body_details(bytes_total: int,
                      bytes_free: int,
                      files_to_display: DisplayingFilesOfType,
                      marked: FileTypeCounter,
                      photos_size_to_download: int,
                      videos_size_to_download: int) -> BodyDetails:
    """
    Gather the details to render for destination storage usage
    for photo and video downloads, and their backups.

    :param bytes_total:
    :param bytes_free:
    :param files_to_display:
    :param marked:
    :param photos_size_to_download:
    :param videos_size_to_download:
    :return:
    """

    bytes_total_text = format_size_for_user(bytes_total, no_decimals=0)
    existing_bytes = bytes_total - bytes_free
    existing_size = format_size_for_user(existing_bytes)

    photos = videos = photos_size = videos_size = ''

    if files_to_display != DisplayingFilesOfType.videos:
        photos = _('%(no_photos)s Photos') % {'no_photos':
                                                  thousands(marked[FileType.photo])}
        photos_size = format_size_for_user(photos_size_to_download)
    if files_to_display != DisplayingFilesOfType.photos:
        videos = _('%(no_videos)s Videos') % {'no_videos':
                                                  thousands(marked[FileType.video])}
        videos_size = format_size_for_user(videos_size_to_download)

    size_to_download = photos_size_to_download + videos_size_to_download
    comp1_file_size_sum = photos_size_to_download
    comp2_file_size_sum = videos_size_to_download
    comp3_file_size_sum = existing_bytes
    comp1_text = photos
    comp2_text = videos
    comp3_text = _('Used')
    comp4_text = _('Excess')
    comp1_size_text = photos_size
    comp2_size_text = videos_size
    comp3_size_text = existing_size

    bytes_to_use = size_to_download + existing_bytes
    percent_used = ''

    if bytes_total == 0:
        bytes_free_of_total = _('Device size unknown')
        comp4_file_size_sum = 0
        comp4_size_text = 0
        comp3_size_text = 0
    elif bytes_to_use > bytes_total:
        bytes_total_ = bytes_total
        bytes_total = bytes_to_use
        excess_bytes = bytes_to_use - bytes_total_
        comp4_file_size_sum = excess_bytes
        comp4_size_text = format_size_for_user(excess_bytes)
        bytes_free_of_total = _('No space free on %(size_total)s device') % dict(
            size_total=bytes_total_text
        )
    else:
        comp4_file_size_sum = 0
        comp4_size_text = 0
        bytes_free = bytes_total - bytes_to_use
        bytes_free_of_total = _('%(size_free)s free of %(size_total)s') % dict(
            size_free=format_size_for_user(bytes_free, no_decimals=1),
            size_total=bytes_total_text
        )

    return BodyDetails(
        bytes_total_text=bytes_total_text,
        bytes_total=bytes_total,
        percent_used_text=percent_used,
        bytes_free_of_total=bytes_free_of_total,
        comp1_file_size_sum=comp1_file_size_sum,
        comp2_file_size_sum=comp2_file_size_sum,
        comp3_file_size_sum=comp3_file_size_sum,
        comp4_file_size_sum=comp4_file_size_sum,
        comp1_text=comp1_text,
        comp2_text=comp2_text,
        comp3_text=comp3_text,
        comp4_text=comp4_text,
        comp1_size_text=comp1_size_text,
        comp2_size_text=comp2_size_text,
        comp3_size_text=comp3_size_text,
        comp4_size_text=comp4_size_text,
        color1=QColor(CustomColors.color1.value),
        color2=QColor(CustomColors.color2.value),
        color3=QColor(CustomColors.color3.value),
        displaying_files_of_type=files_to_display
    )

def adjusted_download_size(photos_size_to_download: int,
                           videos_size_to_download: int,
                           os_stat_device: int,
                           downloading_to) -> Tuple[int, int]:
    """
    Adjust download size to account for situations where
    photos and videos are being backed up to the same
    partition (device) they're downloaded to.

    :return: photos_size_to_download, videos_size_to_download
    """
    if os_stat_device in downloading_to:
        file_types = downloading_to[os_stat_device]
        if FileType.photo in file_types:
            photos_size_to_download = photos_size_to_download * 2
        if FileType.video in file_types:
            videos_size_to_download = videos_size_to_download * 2
    return photos_size_to_download, videos_size_to_download


class DestinationDisplay(QWidget):
    """
    Custom widget handling the display of download destinations, not including the file system
    browsing component.

    Serves a dual purpose, depending on whether photos and videos are being downloaded
    to the same file system or not:

    1. Display how much storage space the checked files will use in addition
       to the space used by existing files.

    2. Display the download destination (path), and a local menu to control subfolder
       generation.

    Where photos and videos are being downloaded to the same file system, the storage space display
    is combined into one widget, which appears in its own panel above the photo and video
    destination panels.

    Where photos and videos are being downloaded to different file systems, the combined
    display (above) is invisible, and photo and video panels have the own section in which
    to display their storage space display
    """

    photos = _('Photos')
    videos = _('Videos')
    projected_space_msg = _('Projected storage use after download')

    def __init__(self, menu: bool=False,
                 file_type: FileType=None,
                 parent=None) -> None:
        """
        :param menu: whether to render a drop down menu
        :param file_type: whether for photos or videos. Relevant only for menu display.
        """

        super().__init__(parent)
        self.rapidApp = parent
        if parent is not None:
            self.prefs = self.rapidApp.prefs
        else:
            self.prefs = None

        self.storage_space = None  # type: StorageSpace

        self.map_action = dict()  # type: Dict[int, QAction]

        if menu:
            menuIcon = QIcon(':/icons/settings.svg')
            self.file_type = file_type
            self.createActionsAndMenu()
            self.mouse_pos = DestinationDisplayMousePos.normal
            self.tooltip_display_state = DestinationDisplayTooltipState.path
        else:
            menuIcon = None
            self.menu = None
            self.mouse_pos = None
            self.tooltip_display_state = None

        self.deviceDisplay = DeviceDisplay(menuButtonIcon=menuIcon)
        size = icon_size()
        self.icon = QIcon(':/icons/folder.svg').pixmap(QSize(size, size))  # type: QPixmap
        self.display_name = ''
        self.photos_size_to_download = self.videos_size_to_download = 0
        self.files_to_display = None   # type: DisplayingFilesOfType
        self.marked = FileTypeCounter()
        self.display_type = None  # type: DestinationDisplayType
        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)

        # default number of built-in subfolder generation defaults
        self.no_builtin_defaults = 5
        self.max_presets = 5

        self.sample_rpd_file = None  # type: Union[Photo, Video]

        self.os_stat_device = 0  # type: int
        self._downloading_to = defaultdict(list)  # type: DefaultDict[int, Set[FileType]]

    @property
    def downloading_to(self) -> DefaultDict[int, Set[FileType]]:
        return self._downloading_to

    @downloading_to.setter
    def downloading_to(self, downloading_to) -> None:
        if downloading_to is not None:
            self._downloading_to = downloading_to
            # TODO determine if this is always needed here
            self.update()

    def createActionsAndMenu(self) -> None:
        self.setMouseTracking(True)
        self.menu = QMenu()

        if self.file_type == FileType.photo:
            defaults = gnc.PHOTO_SUBFOLDER_MENU_DEFAULTS
        else:
            defaults = gnc.VIDEO_SUBFOLDER_MENU_DEFAULTS

        self.subfolder0Act = QAction(
            make_subfolder_menu_entry(defaults[0]),
            self,
            checkable=True,
            triggered=self.doSubfolder0
        )
        self.subfolder1Act = QAction(
            make_subfolder_menu_entry(defaults[1]),
            self,
            checkable=True,
            triggered=self.doSubfolder1
        )
        self.subfolder2Act = QAction(
            make_subfolder_menu_entry(defaults[2]),
            self,
            checkable=True,
            triggered=self.doSubfolder2
        )
        self.subfolder3Act = QAction(
            make_subfolder_menu_entry(defaults[3]),
            self,
            checkable=True,
            triggered=self.doSubfolder3
        )
        self.subfolder4Act = QAction(
            make_subfolder_menu_entry(defaults[4]),
            self,
            checkable=True,
            triggered=self.doSubfolder4
        )
        self.subfolder5Act = QAction(
            'Preset 0',
            self,
            checkable=True,
            triggered=self.doSubfolder5
        )
        self.subfolder6Act = QAction(
            'Preset 1',
            self,
            checkable=True,
            triggered=self.doSubfolder6
        )
        self.subfolder7Act = QAction(
            'Preset 2',
            self,
            checkable=True,
            triggered=self.doSubfolder7
        )
        self.subfolder8Act = QAction(
            'Preset 3',
            self,
            checkable=True,
            triggered=self.doSubfolder8
        )
        self.subfolder9Act = QAction(
            'Preset 4',
            self,
            checkable=True,
            triggered=self.doSubfolder9
        )
        # Translators: Custom refers to the user choosing a non-default value that
        # they customize themselves
        self.subfolderCustomAct = QAction(
            _('Custom...'),
            self,
            checkable=True,
            triggered=self.doSubfolderCustom
        )

        self.subfolderGroup = QActionGroup(self)

        self.subfolderGroup.addAction(self.subfolder0Act)
        self.subfolderGroup.addAction(self.subfolder1Act)
        self.subfolderGroup.addAction(self.subfolder2Act)
        self.subfolderGroup.addAction(self.subfolder3Act)
        self.subfolderGroup.addAction(self.subfolder4Act)
        self.subfolderGroup.addAction(self.subfolder5Act)
        self.subfolderGroup.addAction(self.subfolder6Act)
        self.subfolderGroup.addAction(self.subfolder7Act)
        self.subfolderGroup.addAction(self.subfolder8Act)
        self.subfolderGroup.addAction(self.subfolder9Act)
        self.subfolderGroup.addAction(self.subfolderCustomAct)
        
        self.menu.addAction(self.subfolder0Act)
        self.menu.addAction(self.subfolder1Act)
        self.menu.addAction(self.subfolder2Act)
        self.menu.addAction(self.subfolder3Act)
        self.menu.addAction(self.subfolder4Act)
        self.menu.addSeparator()
        self.menu.addAction(self.subfolder5Act)
        self.menu.addAction(self.subfolder6Act)
        self.menu.addAction(self.subfolder7Act)
        self.menu.addAction(self.subfolder8Act)
        self.menu.addAction(self.subfolder9Act)
        self.menu.addAction(self.subfolderCustomAct)

        self.map_action[0] = self.subfolder0Act
        self.map_action[1] = self.subfolder1Act
        self.map_action[2] = self.subfolder2Act
        self.map_action[3] = self.subfolder3Act
        self.map_action[4] = self.subfolder4Act
        self.map_action[5] = self.subfolder5Act
        self.map_action[6] = self.subfolder6Act
        self.map_action[7] = self.subfolder7Act
        self.map_action[8] = self.subfolder8Act
        self.map_action[9] = self.subfolder9Act
        self.map_action[-1] = self.subfolderCustomAct

    def setupMenuActions(self) -> None:
        if self.file_type == FileType.photo:
            preset_type = PresetPrefType.preset_photo_subfolder
        else:
            preset_type = PresetPrefType.preset_video_subfolder
        self.preset_names, self.preset_pref_lists = self.prefs.get_preset(preset_type=preset_type)

        if self.file_type == FileType.photo:
            index = self.prefs.photo_subfolder_index(self.preset_pref_lists)
        else:
            index = self.prefs.video_subfolder_index(self.preset_pref_lists)

        action = self.map_action[index]  # type: QAction
        action.setChecked(True)

        # Set visibility of custom presets menu items to match how many we are displaying
        for idx, text in enumerate(self.preset_names[:self.max_presets]):
            action = self.map_action[self.no_builtin_defaults + idx]
            action.setText(text)
            action.setVisible(True)

        for i in range(self.max_presets - min(len(self.preset_names), self.max_presets)):
            idx = len(self.preset_names) + self.no_builtin_defaults + i
            action = self.map_action[idx]
            action.setVisible(False)

    def doSubfolder0(self) -> None:
        self.menuItemChosen(0)

    def doSubfolder1(self) -> None:
        self.menuItemChosen(1)

    def doSubfolder2(self) -> None:
        self.menuItemChosen(2)

    def doSubfolder3(self) -> None:
        self.menuItemChosen(3)

    def doSubfolder4(self) -> None:
        self.menuItemChosen(4)

    def doSubfolder5(self) -> None:
        self.menuItemChosen(5)

    def doSubfolder6(self) -> None:
        self.menuItemChosen(6)

    def doSubfolder7(self) -> None:
        self.menuItemChosen(7)

    def doSubfolder8(self) -> None:
        self.menuItemChosen(8)

    def doSubfolder9(self) -> None:
        self.menuItemChosen(9)

    def doSubfolderCustom(self):
        self.menuItemChosen(-1)

    def menuItemChosen(self, index: int) -> None:
        self.mouse_pos = DestinationDisplayMousePos.normal
        self.update()

        user_pref_list = None

        if index == -1:
            if self.file_type == FileType.photo:
                pref_defn = DICT_SUBFOLDER_L0
                pref_list = self.prefs.photo_subfolder
                generation_type = NameGenerationType.photo_subfolder
            else:
                pref_defn = DICT_VIDEO_SUBFOLDER_L0
                pref_list = self.prefs.video_subfolder
                generation_type = NameGenerationType.video_subfolder

            prefDialog = PrefDialog(pref_defn, pref_list, generation_type, self.prefs,
                                    self.sample_rpd_file)
            if prefDialog.exec():
                user_pref_list = prefDialog.getPrefList()
                if not user_pref_list:
                    user_pref_list = None

        elif index >= self.no_builtin_defaults:
            assert index < self.no_builtin_defaults + self.max_presets
            user_pref_list = self.preset_pref_lists[index - self.no_builtin_defaults]

        else:
            if self.file_type == FileType.photo:
                user_pref_list = gnc.PHOTO_SUBFOLDER_MENU_DEFAULTS_CONV[index]
            else:
                user_pref_list = gnc.VIDEO_SUBFOLDER_MENU_DEFAULTS_CONV[index]

        if user_pref_list is not None:
            logging.debug("Updating %s subfolder generation preference value", self.file_type.name)
            if self.file_type == FileType.photo:
                self.prefs.photo_subfolder = user_pref_list
            else:
                self.prefs.video_subfolder = user_pref_list
            self.rapidApp.folder_preview_manager.change_subfolder_structure()

    def setDestination(self, path: str) -> None:
        """
        Set the downloaded destination path
        :param path: valid path
        """

        self.display_name, self.path = get_path_display_name(path)
        try:
            self.os_stat_device = os.stat(path).st_dev
        except FileNotFoundError:
            logging.error('Cannot set download destination display: %s does not exist', path)
            self.os_stat_device = 0

        mount = QStorageInfo(path)
        bytes_total, bytes_free = get_mount_size(mount=mount)

        self.storage_space = StorageSpace(bytes_free=bytes_free, bytes_total=bytes_total, path=path)

    def setDownloadAttributes(self, marked: FileTypeCounter,
                              photos_size: int,
                              videos_size: int,
                              files_to_display: DisplayingFilesOfType,
                              display_type: DestinationDisplayType,
                              merge: bool) -> None:
        """
        Set the attributes used to generate the visual display of the
        files marked to be downloaded

        :param marked: number and type of files marked for download
        :param photos_size: size in bytes of photos marked for download
        :param videos_size: size in bytes of videos marked for download
        :param files_to_display: whether displaying photos or videos or both
        :param display_type: whether showing only the header (folder only),
         usage only, or both
        :param merge: whether to replace or add to the current values
        """

        if not merge:
            self.marked = marked
            self.photos_size_to_download = photos_size
            self.videos_size_to_download = videos_size
        else:
            self.marked.update(marked)
            self.photos_size_to_download += photos_size
            self.videos_size_to_download += videos_size

        self.files_to_display = files_to_display

        self.display_type = display_type

        if self.display_type != DestinationDisplayType.usage_only:
            self.tool_tip = self.path
        else:
            self.tool_tip = self.projected_space_msg
        self.setToolTip(self.tool_tip)

        self.update()
        self.updateGeometry()

    def sufficientSpaceAvailable(self) -> bool:
        """
        Check to see that there is sufficient space with which to perform a download.

        :return: True or False value if sufficient space. Will always return False if
         the download destination is not yet set.
        """

        if self.storage_space is None:
            return False

        # allow for destinations that don't properly report their size
        if self.storage_space.bytes_total == 0:
            return True

        photos_size_to_download, videos_size_to_download = adjusted_download_size(
            photos_size_to_download=self.photos_size_to_download,
            videos_size_to_download=self.videos_size_to_download,
            os_stat_device=self.os_stat_device,
            downloading_to=self._downloading_to)
        return photos_size_to_download + videos_size_to_download < self.storage_space.bytes_free

    def paintEvent(self, event: QPaintEvent) -> None:
        """
        Render the custom widget
        """

        painter = QStylePainter()
        painter.begin(self)

        x = 0
        y = 0
        width = self.width()

        rect = self.rect()  # type: QRect

        if self.display_type == DestinationDisplayType.usage_only and QSplitter().lineWidth():
            # Draw a frame if that's what the style requires
            option = QStyleOptionFrame()
            option.initFrom(self)
            painter.drawPrimitive(QStyle.PE_Frame, option)

            w = QSplitter().lineWidth()
            rect.adjust(w, w, -w, -w)

        palette = QPalette()
        backgroundColor = palette.base().color()
        painter.fillRect(rect, backgroundColor)

        if self.storage_space is None:
            painter.end()
            return

        highlight_menu = self.mouse_pos == DestinationDisplayMousePos.menu

        if self.display_type != DestinationDisplayType.usage_only:
            # Render the folder icon, folder name, and the menu icon
            self.deviceDisplay.paint_header(painter=painter, x=x, y=y, width=width,
                                            display_name=self.display_name, icon=self.icon,
                                            highlight_menu=highlight_menu)
            y = y + self.deviceDisplay.device_name_height

        if self.display_type != DestinationDisplayType.folder_only:
            # Render the projected storage space
            if self.display_type == DestinationDisplayType.usage_only:
                y += self.deviceDisplay.padding

            photos_size_to_download, videos_size_to_download = adjusted_download_size(
                photos_size_to_download=self.photos_size_to_download,
                videos_size_to_download=self.videos_size_to_download,
                os_stat_device=self.os_stat_device,
                downloading_to=self._downloading_to)

            details = make_body_details(bytes_total=self.storage_space.bytes_total,
                                        bytes_free=self.storage_space.bytes_free,
                                        files_to_display=self.files_to_display,
                                        marked=self.marked,
                                        photos_size_to_download=photos_size_to_download,
                                        videos_size_to_download=videos_size_to_download)

            self.deviceDisplay.paint_body(painter=painter, x=x,
                                          y=y,
                                          width=width,
                                          details=details)

        painter.end()

    def sizeHint(self) -> QSize:
        if self.display_type == DestinationDisplayType.usage_only:
            height = self.deviceDisplay.padding
        else:
            height = 0

        if self.display_type != DestinationDisplayType.usage_only:
            height += self.deviceDisplay.device_name_height
        if self.display_type != DestinationDisplayType.folder_only:
            height += self.deviceDisplay.storage_height
        return QSize(self.deviceDisplay.view_width, height)

    def minimumSize(self) -> QSize:
        return self.sizeHint()

    @pyqtSlot(QMouseEvent)
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.menu is None:
            return

        iconRect = self.deviceDisplay.menu_button_rect(0, 0, self.width())

        if iconRect.contains(event.pos()):
            if event.button() == Qt.LeftButton:
                menuTopReal = iconRect.bottomLeft()
                x = math.ceil(menuTopReal.x())
                y = math.ceil(menuTopReal.y())
                self.setupMenuActions()
                self.menu.popup(self.mapToGlobal(QPoint(x, y)))

    @pyqtSlot(QMouseEvent)
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """
        Sets the tooltip depending on the position of the mouse.
        """

        if self.menu is None:
            # Relevant only for photo and video destination panels, not the combined
            # storage space display.
            return

        if self.display_type == DestinationDisplayType.folders_and_usage:
            # make tooltip different when hovering above storage space compared
            # to when hovering above the destination folder

            headerRect = QRect(0, 0, self.width(), self.deviceDisplay.device_name_height)
            if not headerRect.contains(event.pos()):
                if self.tooltip_display_state != DestinationDisplayTooltipState.storage_space:
                    # Display tooltip for storage space
                    self.setToolTip(self.projected_space_msg)
                    self.tooltip_display_state = DestinationDisplayTooltipState.storage_space
                    self.update()
                return

        iconRect = self.deviceDisplay.menu_button_rect(0, 0, self.width())
        if iconRect.contains(event.pos()):
            if self.mouse_pos == DestinationDisplayMousePos.normal:
                self.mouse_pos = DestinationDisplayMousePos.menu

                if self.file_type == FileType.photo:
                    self.setToolTip(_('Configure photo subfolder creation'))
                else:
                    self.setToolTip(_('Configure video subfolder creation'))
                self.tooltip_display_state = DestinationDisplayTooltipState.menu
                self.update()

        else:
            if (self.mouse_pos == DestinationDisplayMousePos.menu or
                    self.tooltip_display_state != DestinationDisplayTooltipState.path):
                self.mouse_pos = DestinationDisplayMousePos.normal
                self.setToolTip(self.tool_tip)
                self.tooltip_display_state = DestinationDisplayTooltipState.path
                self.update()



