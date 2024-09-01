# SPDX-FileCopyrightText: Copyright 2016-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from PyQt5.QtCore import QSize
from PyQt5.QtGui import QColor, QIcon
from PyQt5.QtWidgets import QMenu, QToolButton

from raphodo.ui.primarybutton import DownloadButtonHeight
from raphodo.ui.viewutils import darkModePixmap, menuHoverColor


class MenuButton(QToolButton):
    """
    Button that provides access to a drop-down menu
    """

    def __init__(self, path: str, menu: QMenu) -> None:
        super().__init__()

        self.setPopupMode(QToolButton.InstantPopup)

        hover_color = menuHoverColor().name(QColor.HexRgb)

        try:
            scaling = self.devicePixelRatioF()
        except AttributeError:
            scaling = self.devicePixelRatio()

        # Derive icon size from download button size
        height = round(DownloadButtonHeight()[0] * (2 / 3) * scaling)
        size = QSize(height, height)

        self.setIcon(QIcon(darkModePixmap(path=path, size=size)))
        self.setStyleSheet(
            """
            QToolButton {border: none;}
            QToolButton::menu-indicator { image: none; }
            QToolButton::hover {
                background-color: %s;
                outline: none;
            }
            """
            % hover_color
        )
        self.setMenu(menu)
