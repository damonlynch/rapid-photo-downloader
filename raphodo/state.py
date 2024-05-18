# SPDX-FileCopyrightText: Copyright 2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
from enum import Flag, auto

from raphodo.constants import (
    DisplayFileType,
    FileType,
)


class AppState(Flag):
    STARTUP = auto()
    INITIALIZE_UI = auto()
    NORMAL = auto()
    EXITING = auto()
    DOWNLOADING = auto()
    DOWNLOAD_PAUSED = auto()
    GENERATING_THUMBNAILS = auto()
    SCANNING = auto()
    UI_ELEMENT_CHANGE_PENDING_DEST_PHOTO_PATH = auto()
    UI_ELEMENT_CHANGE_PENDING_DEST_VIDEO_PATH = auto()
    UI_ELEMENT_CHANGE_PENDING_DEST_PHOTO_STATUS = auto()
    UI_ELEMENT_CHANGE_PENDING_DEST_VIDEO_STATUS = auto()
    UI_ELEMENT_CHANGE_PENDING_DEST_PHOTO_SPACE = auto()
    UI_ELEMENT_CHANGE_PENDING_DEST_VIDEO_SPACE = auto()
    UI_ELEMENT_CHANGE_PENDING_DEST_SAME_SPACE = auto()
    UI_GEOMETRY_CHANGE_PENDING_DEST_PHOTO = auto()
    UI_GEOMETRY_CHANGE_PENDING_DEST_VIDEO = auto()
    UI_GEOMETRY_CHANGE_PENDING_DEST_SAME = auto()
    UI_ELEMENT_CHANGE_PENDING_DEST_PHOTO_STATUS_NO_SPACE = auto()
    UI_ELEMENT_CHANGE_PENDING_DEST_VIDEO_STATUS_NO_SPACE = auto()
    UI_ELEMENT_CHANGE_PENDING_DEST_SAME_STATUS_NO_SPACE = auto()
    UI_STATE_CHANGE_PENDING_DEST_SAME = auto()
    UI_STATE_CHANGE_PENDING_DEST_WATCH = auto()
    UI_STATE_CHANGE_PENDING_DEST_PREVIEW_FOLDERS = auto()
    TIMELINE_GENERATING = auto()
    TIMELINE_GENERATED = auto()
    # Destination directory characteristics
    DEST_PHOTO_DIR_NOT_SPECIFIED = auto()
    DEST_PHOTO_DIR_NO_READ = auto()
    DEST_PHOTO_DIR_READ_ONLY = auto()
    DEST_PHOTO_DIR_NOT_EXIST = auto()
    DEST_VIDEO_DIR_NOT_SPECIFIED = auto()
    DEST_VIDEO_DIR_NO_READ = auto()
    DEST_VIDEO_DIR_READ_ONLY = auto()
    DEST_VIDEO_DIR_NOT_EXIST = auto()
    # Destination device characteristics
    DEST_SAME = auto()
    # Destination space characteristics
    DEST_PHOTO_NO_SPACE = auto()
    DEST_VIDEO_NO_SPACE = auto()
    DEST_SAME_NO_SPACE = auto()

    def state_str(self, mask: "AppState") -> str:
        return (self & mask)._name_ or self.not_set_str()

    @staticmethod
    def not_set_str() -> str:
        return "<not set>"


CORE_APPLICATION_STATE_MASK = (
    AppState.STARTUP | AppState.INITIALIZE_UI | AppState.NORMAL | AppState.EXITING
)
TIMELINE_APPLICATION_STATE_MASK = (
    AppState.TIMELINE_GENERATING | AppState.TIMELINE_GENERATED
)
DEST_PHOTO_DIR_MASK = (
    AppState.DEST_PHOTO_DIR_NOT_SPECIFIED
    |AppState.DEST_PHOTO_DIR_NO_READ
    | AppState.DEST_PHOTO_DIR_READ_ONLY
    | AppState.DEST_PHOTO_DIR_NOT_EXIST
)
DEST_VIDEO_DIR_MASK = (
    AppState.DEST_VIDEO_DIR_NOT_SPECIFIED
    |AppState.DEST_VIDEO_DIR_NO_READ
    | AppState.DEST_VIDEO_DIR_READ_ONLY
    | AppState.DEST_VIDEO_DIR_NOT_EXIST
)
DEST_NO_SPACE_MASK = (
    AppState.DEST_PHOTO_NO_SPACE
    | AppState.DEST_VIDEO_NO_SPACE
    | AppState.DEST_SAME_NO_SPACE
)
UI_GEOMETRY_CHANGE_NEEDED_DEST_PHOTO = (
    AppState.UI_ELEMENT_CHANGE_PENDING_DEST_PHOTO_STATUS
    | AppState.UI_ELEMENT_CHANGE_PENDING_DEST_PHOTO_STATUS_NO_SPACE
)
UI_GEOMETRY_CHANGE_NEEDED_DEST_VIDEO = (
    AppState.UI_ELEMENT_CHANGE_PENDING_DEST_VIDEO_STATUS
    | AppState.UI_ELEMENT_CHANGE_PENDING_DEST_VIDEO_STATUS_NO_SPACE
)
UI_ELEMENT_CHANGE_PENDING_DEST_STATUS_MASK = (
    AppState.UI_ELEMENT_CHANGE_PENDING_DEST_PHOTO_STATUS
    | AppState.UI_ELEMENT_CHANGE_PENDING_DEST_VIDEO_STATUS
)
MAP_DEST_NO_SPACE_MASK = {
    DisplayFileType.photos: AppState.DEST_PHOTO_NO_SPACE,
    DisplayFileType.videos: AppState.DEST_VIDEO_NO_SPACE,
    DisplayFileType.photos_and_videos: AppState.DEST_SAME_NO_SPACE,
}
MAP_DEST_DIR_MASK = {
    FileType.photo: DEST_PHOTO_DIR_MASK,
    FileType.video: DEST_VIDEO_DIR_MASK,
}
MAP_DEST_DIR_NOT_EXIST = {
    FileType.photo: AppState.DEST_PHOTO_DIR_NOT_EXIST,
    FileType.video: AppState.DEST_VIDEO_DIR_NOT_EXIST,
}
MAP_DEST_DIR_NOT_SPECIFIED = {
    FileType.photo: AppState.DEST_PHOTO_DIR_NOT_SPECIFIED,
    FileType.video: AppState.DEST_VIDEO_DIR_NOT_SPECIFIED,
}
MAP_DEST_DIR_NO_READ = {
    FileType.photo: AppState.DEST_PHOTO_DIR_NO_READ,
    FileType.video: AppState.DEST_VIDEO_DIR_NO_READ,
}
MAP_DEST_DIR_READ_ONLY = {
    FileType.photo: AppState.DEST_PHOTO_DIR_READ_ONLY,
    FileType.video: AppState.DEST_VIDEO_DIR_READ_ONLY,
}
MAP_UI_ELEMENT_CHANGE_PENDING_DEST_PATH = {
    FileType.photo: AppState.UI_ELEMENT_CHANGE_PENDING_DEST_PHOTO_PATH,
    FileType.video: AppState.UI_ELEMENT_CHANGE_PENDING_DEST_VIDEO_PATH,
}
MAP_UI_ELEMENT_CHANGE_PENDING_DEST_STATUS = {
    FileType.photo: AppState.UI_ELEMENT_CHANGE_PENDING_DEST_PHOTO_STATUS,
    FileType.video: AppState.UI_ELEMENT_CHANGE_PENDING_DEST_VIDEO_STATUS,
}
MAP_UI_ELEMENT_CHANGE_PENDING_DEST_SPACE = {
    DisplayFileType.photos: AppState.UI_ELEMENT_CHANGE_PENDING_DEST_PHOTO_SPACE,
    DisplayFileType.videos: AppState.UI_ELEMENT_CHANGE_PENDING_DEST_VIDEO_SPACE,
    DisplayFileType.photos_and_videos: AppState.UI_ELEMENT_CHANGE_PENDING_DEST_SAME_SPACE,  # noqa: E501
}
MAP_UI_GEOMETRY_CHANGE_PENDING_DEST = {
    DisplayFileType.photos: AppState.UI_GEOMETRY_CHANGE_PENDING_DEST_PHOTO,
    DisplayFileType.videos: AppState.UI_GEOMETRY_CHANGE_PENDING_DEST_VIDEO,
    DisplayFileType.photos_and_videos: AppState.UI_GEOMETRY_CHANGE_PENDING_DEST_SAME,
}
MAP_UI_GEOMETRY_CHANGE_NEEDED_DEST = {
    FileType.photo: UI_GEOMETRY_CHANGE_NEEDED_DEST_PHOTO,
    FileType.video: UI_GEOMETRY_CHANGE_NEEDED_DEST_VIDEO,
}
MAP_UI_ELEMENT_CHANGE_PENDING_DEST_STATUS_NO_SPACE = {
    DisplayFileType.photos: AppState.UI_ELEMENT_CHANGE_PENDING_DEST_PHOTO_STATUS_NO_SPACE,  # noqa: E501
    DisplayFileType.videos: AppState.UI_ELEMENT_CHANGE_PENDING_DEST_VIDEO_STATUS_NO_SPACE,  # noqa: E501
    DisplayFileType.photos_and_videos: AppState.UI_ELEMENT_CHANGE_PENDING_DEST_SAME_STATUS_NO_SPACE,  # noqa: E501
}


def file_type_from_dest_dir_state(state: AppState) -> FileType:
    if state & DEST_PHOTO_DIR_MASK:
        return FileType.photo
    return FileType.video


class State:
    def __init__(self) -> None:
        self.state = AppState.STARTUP

    def set_app_state(self, state: AppState, log_only_if_changed: bool = True) -> bool:
        changed = not (self.state & state)
        if (log_only_if_changed and changed) or not log_only_if_changed:
            logging.debug(
                "Setting state %s → %s",
                self.state.state_str(state),
                state._name_,
            )
        self.state |= state
        return changed

    def unset_app_state(
        self, state: AppState, log_only_if_changed: bool = True
    ) -> bool:
        changed = bool(self.state & state)
        if (log_only_if_changed and changed) or not log_only_if_changed:
            logging.debug(
                "Removing state %s → %s",
                self.state.state_str(state),
                AppState.not_set_str(),
            )
        self.state &= ~state
        return changed

    def set_core_state(self, state: AppState) -> None:
        assert state & CORE_APPLICATION_STATE_MASK
        if not self.state & CORE_APPLICATION_STATE_MASK:
            logging.critical("Core application flag not set")
        else:
            logging.debug(
                "Core state change: %s → %s",
                self.state.state_str(CORE_APPLICATION_STATE_MASK),
                state._name_,
            )
        # Clear existing state
        self.state &= ~CORE_APPLICATION_STATE_MASK
        # Add new state
        self.state |= state

    def _set_exclusive_state(
        self, state: AppState, mask: AppState, log_message: str
    ) -> None:
        logging.debug(
            "%s state change: %s → %s",
            log_message,
            self.state.state_str(mask),
            state._name_,
        )
        self.state &= ~mask
        self.state |= state

    def _unset_exclusive_state(self, mask: AppState, log_message: str) -> None:
        logging.debug(
            "%s state change: %s → %s",
            log_message,
            self.state.state_str(mask),
            AppState.not_set_str(),
        )
        self.state &= ~mask

    def set_dest_dir_state(self, state: AppState) -> None:
        file_type = file_type_from_dest_dir_state(state)
        self._set_exclusive_state(
            state=state,
            mask=MAP_DEST_DIR_MASK[file_type],
            log_message="Destination directory",
        )

    def reset_dest_dir_state(self, file_type: FileType) -> None:
        self._unset_exclusive_state(
            mask=MAP_DEST_DIR_MASK[file_type],
            log_message=f"{file_type.name.capitalize()} destination directory",
        )

    @property
    def on_startup(self) -> bool:
        return bool(AppState.STARTUP & self.state)

    @property
    def on_initialize_ui(self) -> bool:
        return bool(AppState.INITIALIZE_UI & self.state)

    @property
    def on_normal(self) -> bool:
        return bool(AppState.NORMAL & self.state)

    @property
    def on_exit(self) -> bool:
        return bool(AppState.EXITING & self.state)

    @property
    def photo_destination_valid(self) -> bool:
        return bool(DEST_PHOTO_DIR_MASK & self.state)

    @property
    def video_destination_valid(self) -> bool:
        return bool(DEST_VIDEO_DIR_MASK & self.state)

    def destination_dir_valid(self, file_type: FileType) -> bool:
        return not bool(MAP_DEST_DIR_MASK[file_type] & self.state)

    def dest_dir_not_specified(self, file_type: FileType) -> bool:
        return bool(MAP_DEST_DIR_NOT_SPECIFIED[file_type] & self.state)

    @property
    def ui_state_change_pending_to_dest_same(self) -> bool:
        return bool(AppState.UI_STATE_CHANGE_PENDING_DEST_SAME & self.state)

    def ui_change_pending_destination_panel(
        self, file_type: FileType, display_type: DisplayFileType
    ) -> bool:
        return bool(
            self.on_initialize_ui
            or self.ui_state_change_pending_to_dest_same
            or self.ui_element_change_pending_dest_path(file_type)
            or self.ui_element_change_pending_dest_status(file_type)
            or self.ui_element_change_pending_dest_space(display_type)
            or self.ui_element_change_pending_dest_status_no_space(display_type)
        )

    def reset_ui_change_pending_destination_panel(
        self, file_type: FileType, display_type: DisplayFileType
    ) -> None:
        mask = (
            MAP_UI_ELEMENT_CHANGE_PENDING_DEST_PATH[file_type]
            | MAP_UI_ELEMENT_CHANGE_PENDING_DEST_STATUS[file_type]
            | MAP_UI_ELEMENT_CHANGE_PENDING_DEST_STATUS_NO_SPACE[display_type]
            | MAP_UI_ELEMENT_CHANGE_PENDING_DEST_SPACE[display_type]
        )
        self.state &= ~mask

    @property
    def dest_same(self) -> bool:
        return bool(self.state & AppState.DEST_SAME)

    def dest_dir_exists(self, file_type: FileType) -> bool:
        if MAP_DEST_DIR_NOT_SPECIFIED[file_type] & self.state:
            return False
        if MAP_DEST_DIR_NOT_EXIST[file_type] & self.state:
            return False
        return True

    def _unset_ui_change_pending(
        self,
        state: AppState,
        flag_str: str,
        file_type: FileType | None = None,
        display_type: DisplayFileType | None = None,
    ) -> bool:
        name = file_type.name if file_type is not None else display_type.name
        if not (self.state & state):
            logging.error("UI change pending %s %s flag not set", name, flag_str)
        return self.unset_app_state(state)

    def set_ui_element_change_pending_dest_path(self, file_type: FileType) -> bool:
        return self.set_app_state(
            state=MAP_UI_ELEMENT_CHANGE_PENDING_DEST_PATH[file_type]
        )

    def ui_element_change_pending_dest_path(self, file_type: FileType) -> bool:
        return bool(MAP_UI_ELEMENT_CHANGE_PENDING_DEST_PATH[file_type] & self.state)

    def unset_ui_element_change_pending_dest_path(self, file_type: FileType) -> bool:
        return self.unset_app_state(
            state=MAP_UI_ELEMENT_CHANGE_PENDING_DEST_PATH[file_type]
        )

    def set_ui_element_change_pending_dest_status(self, file_type: FileType) -> bool:
        return self.set_app_state(
            state=MAP_UI_ELEMENT_CHANGE_PENDING_DEST_STATUS[file_type]
        )

    def ui_element_change_pending_dest_status(
        self, file_type: FileType | None = None
    ) -> bool:
        if file_type:
            return bool(
                MAP_UI_ELEMENT_CHANGE_PENDING_DEST_STATUS[file_type] & self.state
            )
        return bool(UI_ELEMENT_CHANGE_PENDING_DEST_STATUS_MASK & self.state)

    def unset_ui_element_change_pending_dest_status(self, file_type: FileType) -> bool:
        return self.unset_app_state(
            state=MAP_UI_ELEMENT_CHANGE_PENDING_DEST_STATUS[file_type]
        )

    def set_ui_element_change_pending_dest_space(
        self, display_type: DisplayFileType
    ) -> bool:
        return self.set_app_state(
            state=MAP_UI_ELEMENT_CHANGE_PENDING_DEST_SPACE[display_type]
        )

    def ui_element_change_pending_dest_space(
        self, display_type: DisplayFileType
    ) -> bool:
        return bool(MAP_UI_ELEMENT_CHANGE_PENDING_DEST_SPACE[display_type] & self.state)

    def unset_ui_element_change_pending_dest_space(
        self, display_type: DisplayFileType
    ) -> bool:
        return self.unset_app_state(
            state=MAP_UI_ELEMENT_CHANGE_PENDING_DEST_SPACE[display_type]
        )

    def set_ui_state_change_pending_dest_watch(self) -> bool:
        return self.set_app_state(state=AppState.UI_STATE_CHANGE_PENDING_DEST_WATCH)

    @property
    def ui_state_change_pending_dest_watch(self) -> bool:
        return bool(AppState.UI_STATE_CHANGE_PENDING_DEST_WATCH & self.state)

    def unset_ui_state_change_pending_dest_watch(self) -> bool:
        return self.unset_app_state(state=AppState.UI_STATE_CHANGE_PENDING_DEST_WATCH)

    def set_ui_state_change_pending_dest_preview_folders(self) -> bool:
        return self.set_app_state(
            state=AppState.UI_STATE_CHANGE_PENDING_DEST_PREVIEW_FOLDERS
        )

    @property
    def ui_state_change_pending_dest_preview_folders(self) -> bool:
        return bool(AppState.UI_STATE_CHANGE_PENDING_DEST_PREVIEW_FOLDERS & self.state)

    def unset_ui_state_change_pending_dest_preview_folders(self) -> bool:
        return self.unset_app_state(
            state=AppState.UI_STATE_CHANGE_PENDING_DEST_PREVIEW_FOLDERS
        )

    def set_ui_geometry_change_pending_dest(
        self, display_type: DisplayFileType
    ) -> bool:
        return self.set_app_state(
            state=MAP_UI_GEOMETRY_CHANGE_PENDING_DEST[display_type]
        )

    def ui_geometry_change_pending_dest(self, display_type: DisplayFileType) -> bool:
        return bool(MAP_UI_GEOMETRY_CHANGE_PENDING_DEST[display_type] & self.state)

    def unset_ui_geometry_change_pending_dest(
        self, display_type: DisplayFileType
    ) -> bool:
        return self.unset_app_state(
            state=MAP_UI_GEOMETRY_CHANGE_PENDING_DEST[display_type]
        )

    def ui_geometry_change_needed_dest(self, file_type: FileType) -> bool:
        return (
            bool(MAP_UI_GEOMETRY_CHANGE_NEEDED_DEST[file_type] & self.state)
            or self.ui_state_change_pending_to_dest_same
        )

    def set_ui_element_change_pending_dest_status_no_space(
        self, display_type: DisplayFileType
    ) -> bool:
        return self.set_app_state(
            state=MAP_UI_ELEMENT_CHANGE_PENDING_DEST_STATUS_NO_SPACE[display_type]
        )

    def ui_element_change_pending_dest_status_no_space(
        self, display_type: DisplayFileType
    ) -> bool:
        return bool(
            MAP_UI_ELEMENT_CHANGE_PENDING_DEST_STATUS_NO_SPACE[display_type]
            & self.state
        )

    def unset_ui_element_change_pending_dest_status_no_space(
        self, display_type: DisplayFileType
    ) -> bool:
        return self.unset_app_state(
            state=MAP_UI_ELEMENT_CHANGE_PENDING_DEST_STATUS_NO_SPACE[display_type]
        )

    def set_dest_no_space(self, display_type: DisplayFileType) -> bool:
        return self.set_app_state(state=MAP_DEST_NO_SPACE_MASK[display_type])

    def dest_no_space(self, display_type: DisplayFileType) -> bool:
        return bool(MAP_DEST_NO_SPACE_MASK[display_type] & self.state)

    def unset_dest_no_space(self, display_type: DisplayFileType) -> bool:
        return self.unset_app_state(state=MAP_DEST_NO_SPACE_MASK[display_type])
