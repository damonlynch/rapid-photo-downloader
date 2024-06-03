# SPDX-FileCopyrightText: Copyright 2016-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Display download destination details
"""

import logging
from collections import defaultdict

from PyQt5.QtCore import (
    QRect,
    pyqtSlot,
)
from PyQt5.QtGui import (
    QColor,
    QPaintEvent,
    QPalette, QPainter
)
from PyQt5.QtWidgets import (
    QAction,
    QActionGroup,
    QMenu,
    QSizePolicy,
    QSplitter,
    QStylePainter,
    QVBoxLayout,
    QWidget,
)

from raphodo.constants import (
    COLOR_RED_WARNING_HTML,
    CustomColors,
    DeviceDisplayPadding,
    DeviceDisplayStatus,
    DeviceRowItem,
    DisplayFileType,
    FileType,
    NameGenerationType,
    PresetPrefType,
)
from raphodo.customtypes import BodyDetails, DownloadFilesSizeAndNum
from raphodo.devices import DownloadingTo
from raphodo.generatenameconfig import (
    CUSTOM_SUBFOLDER_MENU_ENTRY_POSITION,
    DICT_SUBFOLDER_L0,
    DICT_VIDEO_SUBFOLDER_L0,
    MAX_DOWNLOAD_SUBFOLDER_MENU_ENTRIES,
    MAX_DOWNLOAD_SUBFOLDER_MENU_PRESETS,
    NUM_DOWNLOAD_SUBFOLDER_BUILT_IN_PRESETS,
    NUM_DOWNLOAD_SUBFOLDER_MENU_CUSTOM_PRESETS,
    PHOTO_SUBFOLDER_MENU_DEFAULTS,
    PHOTO_SUBFOLDER_MENU_DEFAULTS_CONV,
    VIDEO_SUBFOLDER_MENU_DEFAULTS,
    VIDEO_SUBFOLDER_MENU_DEFAULTS_CONV,
    CustomPresetSubfolderLists,
    CustomPresetSubfolderNames,
)
from raphodo.internationalisation.utilities import thousands
from raphodo.rpdfile import FileTypeCounter, Photo, Video
from raphodo.storage.storage import StorageSpace, get_path_display_name
from raphodo.tools.utilities import format_size_for_user
from raphodo.ui.devicedisplay import (
    DeviceRows,
    IndividualDestinationDeviceRows,
)
from raphodo.ui.nameeditor import PrefDialog, make_subfolder_menu_entry


def make_body_details(
    bytes_total: int,
    bytes_free: int,
    display_type: DisplayFileType,
    marked: FileTypeCounter,
    photos_size_to_download: int,
    videos_size_to_download: int,
) -> BodyDetails:
    """
    Gather the details to render for destination storage usage
    for photo and video downloads, and their backups.
    """

    bytes_total_text = format_size_for_user(bytes_total, no_decimals=0)
    existing_bytes = bytes_total - bytes_free
    existing_size = format_size_for_user(existing_bytes)

    photos = videos = photos_size = videos_size = ""

    if display_type != DisplayFileType.videos:
        # Translators: no_photos refers to the number of photos
        # Translators: %(variable)s represents Python code, not a plural of the term
        # variable. You must keep the %(variable)s untranslated, or the program will
        # crash.
        photos = _("%(no_photos)s Photos") % {
            "no_photos": thousands(marked[FileType.photo])
        }
        photos_size = format_size_for_user(photos_size_to_download)
    if display_type != DisplayFileType.photos:
        # Translators: no_videos refers to the number of videos
        # Translators: %(variable)s represents Python code, not a plural of the term
        # variable. You must keep the %(variable)s untranslated, or the program will
        # crash.
        videos = _("%(no_videos)s Videos") % {
            "no_videos": thousands(marked[FileType.video])
        }
        videos_size = format_size_for_user(videos_size_to_download)

    size_to_download = photos_size_to_download + videos_size_to_download
    comp1_file_size_sum = photos_size_to_download
    comp2_file_size_sum = videos_size_to_download
    comp3_file_size_sum = existing_bytes
    comp1_text = photos
    comp2_text = videos
    comp3_text = _("Used")
    comp4_text = _("Excess")
    comp1_size_text = photos_size
    comp2_size_text = videos_size
    comp3_size_text = existing_size

    bytes_to_use = size_to_download + existing_bytes
    percent_used = ""

    if bytes_total == 0:
        bytes_free_of_total = _("Device size unknown")
        comp4_file_size_sum = 0
        comp4_size_text = 0
        comp3_size_text = 0
    elif bytes_to_use > bytes_total:
        bytes_total_ = bytes_total
        bytes_total = bytes_to_use
        excess_bytes = bytes_to_use - bytes_total_
        comp4_file_size_sum = excess_bytes
        comp4_size_text = format_size_for_user(excess_bytes)
        # Translators: %(variable)s represents Python code, not a plural of the term
        # variable. You must keep the %(variable)s untranslated, or the program will
        # crash.
        bytes_free_of_total = _("No space free on %(size_total)s device") % dict(
            size_total=bytes_total_text
        )
    else:
        comp4_file_size_sum = 0
        comp4_size_text = 0
        bytes_free = bytes_total - bytes_to_use
        # Translators: %(variable)s represents Python code, not a plural of the term
        # variable. You must keep the %(variable)s untranslated, or the program will
        # crash.
        bytes_free_of_total = _("%(size_free)s free of %(size_total)s") % dict(
            size_free=format_size_for_user(bytes_free, no_decimals=1),
            size_total=bytes_total_text,
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
        display_type=display_type,
    )


def adjusted_download_size(
    photos_size_to_download: int,
    videos_size_to_download: int,
    os_stat_device: int,
    downloading_to,
) -> tuple[int, int]:
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


# TODO fix tool tip when displaying an error message


class DestinationDisplay(QWidget):
    """
    Custom widget handling the display of download destinations, not including the file
    system browsing component.

    Serves a dual purpose, depending on whether photos and videos are being downloaded
    to the same file system or not:

    1. Display how much storage space the checked files will use in addition
       to the space used by existing files.

    2. Display the download destination (path), and a local menu to control subfolder
       generation.

    Where photos and videos are being downloaded to the same file system, the storage
    space display is combined into one widget, which appears in its own panel above the
    photo and video destination panels.

    Where photos and videos are being downloaded to different file systems, the combined
    display (above) is invisible, and photo and video panels have the own section in
    which to display their storage space display
    """

    photos = _("Photos")
    videos = _("Videos")
    projected_space_msg = _("Projected storage use after download")


    def __init__(
        self,
        deviceRows: IndividualDestinationDeviceRows | DeviceRows,
        rapidApp,
    ) -> None:
        super().__init__()
        self.deviceRows = deviceRows
        self.rapidApp = rapidApp
        self.prefs = self.rapidApp.prefs

        self.storage_space: StorageSpace | None = None

        # TODO account for changing width in child item?:
        # self.deviceDisplay.widthChanged.connect(self.widthChanged)

        # @pyqtSlot(int)
        # def widthChanged(self, width: int) -> None:
        #     self.updateGeometry()

        self.display_name = ""
        self.photos_size_to_download = self.videos_size_to_download = 0
        self.display_type: DisplayFileType | None = None
        self.marked = FileTypeCounter()
        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)

        self.sample_rpd_file: Photo | Video | None = None

        self.os_stat_device: int = 0
        # TODO set this value
        self._downloading_to: DownloadingTo = defaultdict(set)

        self.container_vertical_scrollbar_visible = None

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        layout.addWidget(self.deviceRows)
        layout.addStretch(100)

    @property
    def downloading_to(self) -> DownloadingTo:
        return self._downloading_to

    @downloading_to.setter
    def downloading_to(self, downloading_to: DownloadingTo) -> None:
        if downloading_to is not None:
            self._downloading_to = downloading_to

    def setNoSpace(self, no_space: bool) -> None:
        self.deviceRows.setNoSpace(no_space)

    def setPath(self, path: str) -> None:
        display_name, path = get_path_display_name(path)
        self.deviceRows.setHeaderText(display_name)
        self.deviceRows.setHeaderToolTip(path)

    def setStorage(self, storage_space: StorageSpace) -> None:
        self.storage_space = storage_space

    def setFilesToDownload(
        self,
        sizeAndNum: DownloadFilesSizeAndNum,
        merge: bool,
        display_type: DisplayFileType,
    ) -> None:
        photos_size = (
            0
            if display_type == DisplayFileType.videos
            else sizeAndNum.size_photos_marked
        )
        videos_size = (
            0
            if display_type == DisplayFileType.photos
            else sizeAndNum.size_videos_marked
        )

        if not merge:
            self.marked = sizeAndNum.marked
            self.photos_size_to_download = photos_size
            self.videos_size_to_download = videos_size
        else:
            self.marked.update(sizeAndNum.marked)
            self.photos_size_to_download += photos_size
            self.videos_size_to_download += videos_size

    def updateUsage(self) -> None:
        if self.storage_space is None:
            # TODO optimise this. This should not be happening.
            return

        photos_size_to_download, videos_size_to_download = adjusted_download_size(
            photos_size_to_download=self.photos_size_to_download,
            videos_size_to_download=self.videos_size_to_download,
            os_stat_device=self.os_stat_device,
            downloading_to=self._downloading_to,
        )

        details = make_body_details(
            bytes_total=self.storage_space.bytes_total,
            bytes_free=self.storage_space.bytes_free,
            display_type=self.display_type,
            marked=self.marked,
            photos_size_to_download=photos_size_to_download,
            videos_size_to_download=videos_size_to_download,
        )
        self.deviceRows.setUsage(details)

    @pyqtSlot(bool)
    def containerVerticalScrollBar(self, visible: bool) -> None:
        pass

    def setStatus(self, status: DeviceDisplayStatus) -> None:
        self.deviceRows.setDeviceDisplayStatus(status)


class CombinedDestinationDisplay(DestinationDisplay):
    def __init__(self, rapidApp) -> None:
        super().__init__(
            deviceRows=DeviceRows(
                device_row_item=DeviceRowItem.no_storage_space | DeviceRowItem.usage0 | DeviceRowItem.frame,
            ),
            rapidApp=rapidApp,
        )
        self.setObjectName("combinedDestinationDisplay")
        self.display_type = DisplayFileType.photos_and_videos

    @pyqtSlot(bool)
    def containerVerticalScrollBar(self, visible: bool) -> None:
        self.deviceRows.usage0Widget.container_vertical_scrollbar_visible = visible

class IndividualDestinationDisplay(DestinationDisplay):
    def __init__(
        self,
        display_type: DisplayFileType,
        rapidApp,
    ) -> None:
        super().__init__(
            deviceRows=IndividualDestinationDeviceRows(),
            rapidApp=rapidApp,
        )
        if display_type == DisplayFileType.photos:
            self.setObjectName("photoDestinationDisplay")
        else:
            self.setObjectName("videoDestinationDisplay")

        self.menu_actions: list[QAction] = []
        self.display_type = display_type
        self.createActionsAndMenu()
        tooltip = (
            _("Configure photo subfolder creation")
            if display_type == DisplayFileType.photos
            else _("Configure video subfolder creation")
        )
        menuButton = self.deviceRows.menuButton()
        menuButton.setToolTip(tooltip)
        menuButton.setMenu(self.menu)
        menuButton.mousePressed.connect(self.setupMenuActions)

    def createActionsAndMenu(self) -> None:
        self.menu = QMenu()

        if self.display_type == DisplayFileType.photos:
            defaults = PHOTO_SUBFOLDER_MENU_DEFAULTS
        else:
            defaults = VIDEO_SUBFOLDER_MENU_DEFAULTS

        self.subfolderGroup = QActionGroup(self)

        # Generate a list of actions with matching text entries, and place them in a
        # menu
        for index in range(MAX_DOWNLOAD_SUBFOLDER_MENU_ENTRIES):
            if index < NUM_DOWNLOAD_SUBFOLDER_BUILT_IN_PRESETS:
                menu_text = make_subfolder_menu_entry(defaults[index])
            elif index == CUSTOM_SUBFOLDER_MENU_ENTRY_POSITION:
                # Translators: Custom refers to the user choosing a non-default value
                # that they customize themselves
                menu_text = _("Custom...")
            else:
                menu_text = "Placeholder text"

            action = QAction(menu_text, self)
            action.setCheckable(True)
            action.triggered.connect(
                lambda checked, index=index: self.menuItemChosen(index)
            )

            self.subfolderGroup.addAction(action)
            self.menu_actions.append(action)

            if index == NUM_DOWNLOAD_SUBFOLDER_BUILT_IN_PRESETS:
                self.menu.addSeparator()

            self.menu.addAction(action)

    @pyqtSlot()
    def setupMenuActions(self) -> None:
        index, preset_names, preset_pref_lists = self.getPresetIndex()
        assert index < MAX_DOWNLOAD_SUBFOLDER_MENU_ENTRIES

        action: QAction = self.menu_actions[index]
        action.setChecked(True)

        # Set visibility of custom presets menu items to match how many we are
        # displaying

        for index in range(NUM_DOWNLOAD_SUBFOLDER_MENU_CUSTOM_PRESETS):
            action = self.menu_actions[NUM_DOWNLOAD_SUBFOLDER_BUILT_IN_PRESETS + index]
            if index < len(preset_names):
                action.setText(preset_names[index])
                action.setVisible(True)
            else:
                action.setVisible(False)

        # Save the custom preset list for access in self.menuItemChosen()
        self.preset_pref_lists = preset_pref_lists

    def getPresetIndex(
        self,
    ) -> tuple[int, CustomPresetSubfolderNames, CustomPresetSubfolderLists]:
        """
        Returns the index of the user's download subfolder generation config in the
        list of subfolder generation preferences, which is a combination of the built-in
        defaults and the user's custom presets.

        :return: index into the combined list of subfolder generation preferences, or -1
         if it doesn't exist in the list, as well as the user's custom presets and their
         names.
        """

        if self.display_type == DisplayFileType.photos:
            default_prefs_list = PHOTO_SUBFOLDER_MENU_DEFAULTS_CONV
            prefs_subfolder_list = self.prefs.photo_subfolder
            preset_type = PresetPrefType.preset_photo_subfolder
        else:
            default_prefs_list = VIDEO_SUBFOLDER_MENU_DEFAULTS_CONV
            prefs_subfolder_list = self.prefs.video_subfolder
            preset_type = PresetPrefType.preset_video_subfolder

        custom_preset_names, custom_preset_pref_lists = self.prefs.get_custom_presets(
            preset_type=preset_type
        )

        try:
            index = default_prefs_list.index(prefs_subfolder_list)
        except ValueError:
            try:
                index = custom_preset_pref_lists.index(prefs_subfolder_list)
            except ValueError:
                index = -1
            else:
                if index >= NUM_DOWNLOAD_SUBFOLDER_MENU_CUSTOM_PRESETS:
                    # A custom preset is in use, but due to the position of that custom
                    # preset in the list of presets, it will not be shown in the menu
                    # without being moved up in position.
                    # Move it to the beginning.
                    preset_name = custom_preset_names.pop(index)
                    pref_list = custom_preset_pref_lists.pop(index)
                    custom_preset_names.insert(0, preset_name)
                    custom_preset_pref_lists.insert(0, pref_list)

                    self.prefs.set_custom_presets(
                        preset_type=preset_type,
                        preset_names=custom_preset_names,
                        preset_pref_lists=custom_preset_pref_lists,
                    )
                    index = NUM_DOWNLOAD_SUBFOLDER_BUILT_IN_PRESETS
                else:
                    # Return the index into taking into account
                    # the length of the default presets.
                    index += NUM_DOWNLOAD_SUBFOLDER_BUILT_IN_PRESETS

        return index, custom_preset_names, custom_preset_pref_lists

    @pyqtSlot(int)
    def menuItemChosen(self, index: int) -> None:
        user_pref_list = None

        if index == CUSTOM_SUBFOLDER_MENU_ENTRY_POSITION:
            if self.display_type == DisplayFileType.photos:
                pref_defn = DICT_SUBFOLDER_L0
                pref_list = self.prefs.photo_subfolder
                generation_type = NameGenerationType.photo_subfolder
            else:
                pref_defn = DICT_VIDEO_SUBFOLDER_L0
                pref_list = self.prefs.video_subfolder
                generation_type = NameGenerationType.video_subfolder

            prefDialog = PrefDialog(
                pref_defn=pref_defn,
                user_pref_list=pref_list,
                generation_type=generation_type,
                prefs=self.prefs,
                sample_rpd_file=self.sample_rpd_file,
                max_entries=MAX_DOWNLOAD_SUBFOLDER_MENU_PRESETS,
            )
            if prefDialog.exec():
                user_pref_list = prefDialog.getPrefList()
                if not user_pref_list:
                    user_pref_list = None

        elif index >= NUM_DOWNLOAD_SUBFOLDER_BUILT_IN_PRESETS:
            assert index < CUSTOM_SUBFOLDER_MENU_ENTRY_POSITION
            user_pref_list = self.preset_pref_lists[
                index - NUM_DOWNLOAD_SUBFOLDER_BUILT_IN_PRESETS
            ]

        else:
            if self.display_type == DisplayFileType.photos:
                user_pref_list = PHOTO_SUBFOLDER_MENU_DEFAULTS_CONV[index]
            else:
                user_pref_list = VIDEO_SUBFOLDER_MENU_DEFAULTS_CONV[index]

        if user_pref_list is not None:
            logging.debug(
                "Updating %s subfolder generation preference value",
                self.display_type.name,
            )
            if self.display_type == DisplayFileType.photos:
                self.prefs.photo_subfolder = user_pref_list
            else:
                self.prefs.video_subfolder = user_pref_list
            self.rapidApp.folder_preview_manager.change_subfolder_structure()
