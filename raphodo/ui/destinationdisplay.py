# SPDX-FileCopyrightText: Copyright 2016-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Display download destination details
"""

import logging
import math
import os
from collections import defaultdict

from PyQt5.QtCore import QPoint, QRect, QRectF, QSize, QStorageInfo, Qt, pyqtSlot
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QMouseEvent,
    QPainterPath,
    QPaintEvent,
    QPalette,
    QPen,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QAction,
    QActionGroup,
    QApplication,
    QMenu,
    QSizePolicy,
    QSplitter,
    QStyle,
    QStylePainter,
    QWidget,
)

from raphodo.constants import (
    COLOR_RED_WARNING_HTML,
    CustomColors,
    DestinationDisplayMousePos,
    DestinationDisplayStatus,
    DestinationDisplayTooltipState,
    DestinationDisplayType,
    DeviceDisplayPadding,
    DisplayingFilesOfType,
    FileType,
    NameGenerationType,
    PresetPrefType,
)
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
from raphodo.storage.storage import StorageSpace, get_mount_size, get_path_display_name
from raphodo.tools.utilities import data_file_path, format_size_for_user
from raphodo.ui.devicedisplay import BodyDetails, DeviceDisplay, icon_size
from raphodo.ui.nameeditor import PrefDialog, make_subfolder_menu_entry
from raphodo.ui.viewutils import darkModePixmap, paletteMidPen


def make_body_details(
    bytes_total: int,
    bytes_free: int,
    files_to_display: DisplayingFilesOfType,
    marked: FileTypeCounter,
    photos_size_to_download: int,
    videos_size_to_download: int,
) -> BodyDetails:
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

    photos = videos = photos_size = videos_size = ""

    if files_to_display != DisplayingFilesOfType.videos:
        # Translators: no_photos refers to the number of photos
        # Translators: %(variable)s represents Python code, not a plural of the term
        # variable. You must keep the %(variable)s untranslated, or the program will
        # crash.
        photos = _("%(no_photos)s Photos") % {
            "no_photos": thousands(marked[FileType.photo])
        }
        photos_size = format_size_for_user(photos_size_to_download)
    if files_to_display != DisplayingFilesOfType.photos:
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
        displaying_files_of_type=files_to_display,
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
        menu: bool = False,
        file_type: FileType = None,
        parent: QWidget = None,
        rapidApp=None,
    ) -> None:
        """
        :param menu: whether to render a drop-down menu
        :param file_type: whether for photos or videos. Relevant only for menu display.
        """

        super().__init__(parent)
        self.rapidApp = rapidApp
        if rapidApp is not None:
            self.prefs = self.rapidApp.prefs
        else:
            self.prefs = None

        self.storage_space: StorageSpace | None = None

        self.menu_actions: list[QAction] = []
        if menu:
            pixmap = darkModePixmap(
                path="icons/settings.svg",
                size=QSize(100, 100),
                soften_regular_mode_color=True,
            )
            menuIcon = QIcon(pixmap)
            self.file_type = file_type
            self.createActionsAndMenu()
            self.mouse_pos = DestinationDisplayMousePos.normal
            self.tooltip_display_state = DestinationDisplayTooltipState.path
        else:
            menuIcon = None
            self.menu = None
            self.mouse_pos = None
            self.tooltip_display_state = None

        self.deviceDisplay = DeviceDisplay(parent=self, menuButtonIcon=menuIcon)
        self.deviceDisplay.widthChanged.connect(self.widthChanged)
        size = icon_size()
        self.pixmap: QPixmap = QIcon(data_file_path("icons/folder.svg")).pixmap(
            QSize(size, size)
        )
        self.pixmap = darkModePixmap(pixmap=self.pixmap)
        self.display_name = ""
        self.photos_size_to_download = self.videos_size_to_download = 0
        self.files_to_display: DisplayingFilesOfType | None = None
        self.marked = FileTypeCounter()
        self.display_type: DestinationDisplayType | None = None
        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)

        self.sample_rpd_file: Photo | Video | None = None

        self.os_stat_device: int = 0
        self._downloading_to: DownloadingTo = defaultdict(set)

        self.midPen = paletteMidPen()
        self.frame_width = QApplication.style().pixelMetric(QStyle.PM_DefaultFrameWidth)
        self.container_vertical_scrollbar_visible = None

        self.status = DestinationDisplayStatus.valid
        self.invalidColor = QColor(COLOR_RED_WARNING_HTML)

    @property
    def downloading_to(self) -> DownloadingTo:
        return self._downloading_to

    @downloading_to.setter
    def downloading_to(self, downloading_to: DownloadingTo) -> None:
        if downloading_to is not None:
            self._downloading_to = downloading_to
            # TODO determine if this is always needed here
            self.update()

    def createActionsAndMenu(self) -> None:
        self.setMouseTracking(True)
        self.menu = QMenu()

        if self.file_type == FileType.photo:
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

        if self.file_type == FileType.photo:
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

    @pyqtSlot(int)
    def menuItemChosen(self, index: int) -> None:
        self.mouse_pos = DestinationDisplayMousePos.normal
        self.update()

        user_pref_list = None

        if index == CUSTOM_SUBFOLDER_MENU_ENTRY_POSITION:
            if self.file_type == FileType.photo:
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
            if self.file_type == FileType.photo:
                user_pref_list = PHOTO_SUBFOLDER_MENU_DEFAULTS_CONV[index]
            else:
                user_pref_list = VIDEO_SUBFOLDER_MENU_DEFAULTS_CONV[index]

        if user_pref_list is not None:
            logging.debug(
                "Updating %s subfolder generation preference value", self.file_type.name
            )
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
            logging.error(
                "Cannot set download destination display: %s does not exist", path
            )
            self.os_stat_device = 0

        mount = QStorageInfo(path)
        bytes_total, bytes_free = get_mount_size(mount=mount)

        self.storage_space = StorageSpace(
            bytes_free=bytes_free, bytes_total=bytes_total, path=path
        )

    def setDownloadAttributes(
        self,
        marked: FileTypeCounter,
        photos_size: int,
        videos_size: int,
        files_to_display: DisplayingFilesOfType,
        display_type: DestinationDisplayType,
        merge: bool,
    ) -> None:
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
            downloading_to=self._downloading_to,
        )
        return (
            photos_size_to_download + videos_size_to_download
            < self.storage_space.bytes_free
        )

    @pyqtSlot(bool)
    def containerVerticalScrollBar(self, visible: bool) -> None:
        self.container_vertical_scrollbar_visible = visible

    @staticmethod
    def invalidStatusHeight() -> int:
        return QFontMetrics(QFont()).height() + DeviceDisplayPadding * 2

    def setStatus(self, status: DestinationDisplayStatus)-> None:
        self.status = status
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        """
        Render the custom widget
        """

        painter = QStylePainter()
        painter.begin(self)

        x: int = 0
        y: int = 0
        width = self.width()

        rect: QRect = self.rect()
        palette = QPalette()
        backgroundColor = palette.base().color()

        if (
            self.display_type == DestinationDisplayType.usage_only
            and QSplitter().lineWidth()
        ):
            pen = painter.pen()
            painter.setPen(backgroundColor)
            painter.drawLine(rect.topLeft(), rect.topRight())
            painter.setPen(self.midPen)
            painter.drawLine(rect.bottomLeft(), rect.bottomRight())
            painter.drawLine(rect.topLeft(), rect.bottomLeft())
            if (
                self.container_vertical_scrollbar_visible is None
                or not self.container_vertical_scrollbar_visible
            ):
                painter.drawLine(rect.topRight(), rect.bottomRight())
            painter.setPen(pen)

            w = QSplitter().lineWidth()
            rect.adjust(w, w, -w, -w)

        painter.fillRect(rect, backgroundColor)

        if self.storage_space is None:
            painter.end()
            return

        highlight_menu = self.mouse_pos == DestinationDisplayMousePos.menu

        if self.display_type != DestinationDisplayType.usage_only:
            # Render the folder icon, folder name, and the menu icon
            self.deviceDisplay.paint_header(
                painter=painter,
                x=x,
                y=y,
                width=width,
                display_name=self.display_name,
                icon=self.pixmap,
                highlight_menu=highlight_menu,
            )
            y = y + self.deviceDisplay.dc.device_name_height

            if self.status != DestinationDisplayStatus.valid:
                displayPen = painter.pen()
                match self.status:
                    case DestinationDisplayStatus.unwritable:
                        # Translators: the lack of a period at the end is deliberate
                        text = _("Unwritable destination")
                    case DestinationDisplayStatus.does_not_exist:
                        # Translators: the lack of a period at the end is deliberate
                        text = _("Folder does not exist")
                    case DestinationDisplayStatus.no_storage_space:
                        # Translators: the lack of a period at the end is deliberate
                        text = _("Insufficient storage space")
                    case _:
                        raise NotImplementedError(
                            "Unhandled destination display status"
                        )

                y = y - DeviceDisplayPadding  # remove the bottom padding

                status_height = self.invalidStatusHeight()
                statusRect = QRect(x, y, width, status_height)
                painter.fillRect(statusRect, self.invalidColor)

                text_height = QFontMetrics(QFont()).height()
                white = QColor(Qt.GlobalColor.white)

                iconRect = QRectF(
                    float(DeviceDisplayPadding),
                    float(y + DeviceDisplayPadding),
                    float(text_height),
                    float(text_height),
                )
                exclamationRect = iconRect.adjusted(0.25, 1.0, 0.25, 1.0)
                textRect = QRectF(
                    iconRect.right() + DeviceDisplayPadding,
                    iconRect.top(),
                    width - iconRect.right() - DeviceDisplayPadding,
                    float(text_height),
                )

                painter.setPen(QPen(white))

                # Draw a triangle
                path = QPainterPath()
                path.moveTo(iconRect.left() + (iconRect.width() / 2), iconRect.top())
                path.lineTo(iconRect.bottomLeft())
                path.lineTo(iconRect.bottomRight())
                path.lineTo(iconRect.left() + (iconRect.width() / 2), iconRect.top())

                painter.fillPath(path, QBrush(white))

                # Draw an exclamation point
                displayFont = painter.font()
                warningFont = QFont()
                warningFont.setBold(True)
                exclamationFont = QFont(warningFont)
                exclamationFont.setPointSize(warningFont.pointSize() - 2)

                painter.setFont(exclamationFont)
                painter.setPen(QPen(self.invalidColor))
                painter.drawText(exclamationRect, Qt.AlignmentFlag.AlignCenter, "!")

                # Draw the warning
                painter.setFont(warningFont)
                painter.setPen(QPen(white))
                painter.drawText(
                    textRect,
                    Qt.TextFlag.TextSingleLine | Qt.AlignmentFlag.AlignVCenter,
                    text,
                )
                painter.setPen(displayPen)
                painter.setFont(displayFont)
                y = y + status_height

        if self.display_type != DestinationDisplayType.folder_only:
            # Render the projected storage space
            if self.display_type == DestinationDisplayType.usage_only:
                y += self.deviceDisplay.dc.padding

            photos_size_to_download, videos_size_to_download = adjusted_download_size(
                photos_size_to_download=self.photos_size_to_download,
                videos_size_to_download=self.videos_size_to_download,
                os_stat_device=self.os_stat_device,
                downloading_to=self._downloading_to,
            )

            details = make_body_details(
                bytes_total=self.storage_space.bytes_total,
                bytes_free=self.storage_space.bytes_free,
                files_to_display=self.files_to_display,
                marked=self.marked,
                photos_size_to_download=photos_size_to_download,
                videos_size_to_download=videos_size_to_download,
            )

            self.deviceDisplay.paint_body(
                painter=painter, x=x, y=y, width=width, details=details
            )

        painter.end()

    @pyqtSlot(int)
    def widthChanged(self, width: int) -> None:
        self.updateGeometry()

    def sizeHint(self) -> QSize:
        if self.display_type == DestinationDisplayType.usage_only:
            height = self.deviceDisplay.dc.padding
        else:
            height = 0

        if self.display_type != DestinationDisplayType.usage_only:
            height += self.deviceDisplay.dc.device_name_height
            if self.status != DestinationDisplayStatus.valid:
                height += self.invalidStatusHeight()
        if self.display_type != DestinationDisplayType.folder_only:
            height += self.deviceDisplay.dc.storage_height

        return QSize(self.deviceDisplay.width(), height)

    def minimumSize(self) -> QSize:
        return self.sizeHint()

    @pyqtSlot(QMouseEvent)
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.menu is None:
            return

        iconRect = self.deviceDisplay.menu_button_rect(0, 0, self.width())

        if iconRect.contains(event.pos()) and event.button() == Qt.LeftButton:
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

            headerRect = QRect(
                0, 0, self.width(), self.deviceDisplay.dc.device_name_height
            )
            if not headerRect.contains(event.pos()):
                if (
                    self.tooltip_display_state
                    != DestinationDisplayTooltipState.storage_space
                ):
                    # Display tooltip for storage space
                    self.setToolTip(self.projected_space_msg)
                    self.tooltip_display_state = (
                        DestinationDisplayTooltipState.storage_space
                    )
                    self.update()
                return

        iconRect = self.deviceDisplay.menu_button_rect(0, 0, self.width())
        if iconRect.contains(event.pos()):
            if self.mouse_pos == DestinationDisplayMousePos.normal:
                self.mouse_pos = DestinationDisplayMousePos.menu

                if self.file_type == FileType.photo:
                    self.setToolTip(_("Configure photo subfolder creation"))
                else:
                    self.setToolTip(_("Configure video subfolder creation"))
                self.tooltip_display_state = DestinationDisplayTooltipState.menu
                self.update()

        else:
            if (
                self.mouse_pos == DestinationDisplayMousePos.menu
                or self.tooltip_display_state != DestinationDisplayTooltipState.path
            ):
                self.mouse_pos = DestinationDisplayMousePos.normal
                self.setToolTip(self.tool_tip)
                self.tooltip_display_state = DestinationDisplayTooltipState.path
                self.update()
