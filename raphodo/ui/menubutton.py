#  SPDX-FileCopyrightText: 2016-2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: GPL-3.0-or-later

from typing import cast

from PyQt6.QtCore import QSize, pyqtSlot
from PyQt6.QtGui import QColor, QGuiApplication
from PyQt6.QtWidgets import QMenu, QToolButton

from raphodo.application import Application
from raphodo.ui.primarybutton import DownloadButtonHeight
from raphodo.ui.programicon import ProgramIcon
from raphodo.ui.viewutils import menuHoverColor


class MenuButton(QToolButton):
    """
    Button that provides access to a drop-down menu
    """

    def __init__(self, path: str, menu: QMenu) -> None:
        super().__init__()
        self.app = cast(Application, QGuiApplication.instance())
        self.app.applicationPaletteChanged.connect(self.applicationPaletteChanged)

        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        scaling = self.devicePixelRatioF()

        # Derive icon size from download button size
        height = round(DownloadButtonHeight()[0] * (2 / 3) * scaling)
        size = QSize(height, height)
        self._icon = ProgramIcon(path=path, size=size)
        self.applicationPaletteChanged(self.app.darkMode)
        self.setMenu(menu)

    @pyqtSlot(bool)
    def applicationPaletteChanged(self, dark_mode: bool) -> None:
        self.setIcon(self._icon.darkModeAware(dark_mode=dark_mode))
        hover_color = menuHoverColor(dark_mode=dark_mode).name(QColor.NameFormat.HexRgb)
        self.setStyleSheet(
            f"""
            QToolButton {{border: none;}}
            QToolButton::menu-indicator {{ image: none; }}
            QToolButton::hover {{
                background-color: {hover_color};
                outline: none;
            }}
            """
        )
