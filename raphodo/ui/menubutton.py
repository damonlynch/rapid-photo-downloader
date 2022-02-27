# Copyright (C) 2016-2022 Damon Lynch <damonlynch@gmail.com>

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
# along with Rapid Photo Downloader. If not,
# see <http://www.gnu.org/licenses/>.

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2016-2022, Damon Lynch"

from PyQt5.QtCore import QSize
from PyQt5.QtGui import QColor, QIcon
from PyQt5.QtWidgets import QMenu, QToolButton

from raphodo.ui.viewutils import darkModePixmap, menuHoverColor
from raphodo.ui.primarybutton import DownloadButtonHeight


class MenuButton(QToolButton):
    """
    Button that provides access to a drop-down menu
    """

    def __init__(self, icon: str, menu: QMenu) -> None:
        super().__init__()

        self.setPopupMode(QToolButton.InstantPopup)

        hover_color = menuHoverColor().name(QColor.HexRgb)

        try:
            scaling = self.devicePixelRatioF()
        except AttributeError:
            scaling = self.devicePixelRatio()

        # Derive icon size from download button size
        height = round(DownloadButtonHeight()[0] * (2/3) * scaling)
        size = QSize(height, height)

        self.setIcon(QIcon(darkModePixmap(path=icon, size=size)))
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
