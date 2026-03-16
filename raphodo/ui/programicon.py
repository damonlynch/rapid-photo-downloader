#  SPDX-FileCopyrightText: 2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: GPL-3.0-or-later

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import QApplication

from raphodo.constants import HeaderBackgroundName
from raphodo.tools.utilities import data_file_path
from raphodo.ui.viewutils import coloredPixmap


class ProgramIcon(QIcon):
    def __init__(
        self,
        path: str,
        path_dark: str | None = None,
        size: QSize | None = None,
        soften_regular_mode_color: bool = False,
    ):
        self._size = size
        if soften_regular_mode_color:
            color = QColor(HeaderBackgroundName)
            pixmap = coloredPixmap(path=path, size=size, color=color)
            super().__init__(pixmap)
        else:
            if size:
                super().__init__(QIcon(data_file_path(path)).pixmap(size))
            else:
                super().__init__(data_file_path(path))
        self.darkIcon = QIcon(data_file_path(path_dark)) if path_dark else None

    @property
    def size(self) -> QSize | None:
        return self._size

    @size.setter
    def size(self, size: QSize) -> None:
        self._size = size

    def darkModeAware(self, dark_mode: bool) -> QIcon:
        assert self._size is not None
        if dark_mode:
            if self.darkIcon is not None:
                return self.darkIcon
            else:
                color = QApplication.palette().windowText().color()
                pixmap = coloredPixmap(pixmap=self.pixmap(self._size), color=color)
                return QIcon(pixmap)
        else:
            return QIcon(self)
