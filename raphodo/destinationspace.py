# SPDX-FileCopyrightText: Copyright 2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from PyQt5.QtCore import QStorageInfo

from raphodo.constants import DisplayFileType
from raphodo.storage.storage import StorageSpace, get_mount_size


class DestinationDeviceSpace:
    def __init__(self, display_type: DisplayFileType) -> None:
        super().__init__()
        self.mount: QStorageInfo | None = None
        self.bytes_total: int = 0
        self.bytes_free: int = 0
        self._path: str = ""
        self.display_type = display_type

    @property
    def path(self) -> str:
        return self._path

    def resolve_mount(self, path: str) -> bool:
        """
        Determine the mount associated with the path, and return a Boolean indicating
        if the mount changed compared to the previous path.

        :param path: the full path to check
        :return: True if the mount was changed, False otherwise
        """

        if not path:
            self.mount = None
            self.bytes_total = 0
            self.bytes_free = 0
            self._path = ""
            return True

        mount_changed = False
        if path != self._path:
            self._path = path
            mount = QStorageInfo(path)
            if self.mount != mount:
                mount_changed = True
                self.mount = mount

        if self.mount.isValid():
            self.bytes_total, self.bytes_free = get_mount_size(mount=self.mount)

        return mount_changed

    def valid(self) -> bool:
        if self.mount is not None:
            return self.mount.isValid()
        return False

    def not_reported(self) -> bool:
        return self.mount is not None and self.bytes_total == 0

    def update_free(self) -> None:
        if not self.valid():
            return
        self.bytes_total, self.bytes_free = get_mount_size(mount=self.mount)

    def storage_space(self) -> StorageSpace:
        return StorageSpace(
            bytes_free=self.bytes_free,
            bytes_total=self.bytes_total,
            path=self._path,
        )


class DestinationSpace:
    def __init__(self) -> None:
        super().__init__()
        self.dest = {
            DisplayFileType.photos: DestinationDeviceSpace(DisplayFileType.photos),
            DisplayFileType.videos: DestinationDeviceSpace(DisplayFileType.videos),
            DisplayFileType.photos_and_videos: DestinationDeviceSpace(
                DisplayFileType.photos_and_videos
            ),
        }

    def set_destination(self, path: str, display_type: DisplayFileType) -> bool:
        """

        :param path:
        :param display_type:
        :return: True if the mount was changed, False otherwise
        """

        return self.dest[display_type].resolve_mount(path)

    def space_is_available(
        self, download_size: int, display_type: DisplayFileType
    ) -> bool:
        dest = self.dest[display_type]
        return dest.not_reported() or download_size < dest.bytes_free
