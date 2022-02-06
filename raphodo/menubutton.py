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

from PyQt5.QtGui import QGuiApplication, QPalette, QColor
from PyQt5.QtWidgets import QMenu, QToolButton

from raphodo.viewutils import scaledIcon
from raphodo.constants import ButtonHoverIntensity


class MenuButton(QToolButton):
    """
    Button that provides access to a drop-down menu
    """

    def __init__(self, icon: str, menu: QMenu) -> None:
        super().__init__()

        self.setPopupMode(QToolButton.InstantPopup)

        color = QGuiApplication.palette().color(QPalette.Background)
        hover_color = color.darker(ButtonHoverIntensity).name(QColor.HexRgb)

        self.setIcon(scaledIcon(icon, self.iconSize()))
        self.setStyleSheet(
            """
            QToolButton {border: none;}
            QToolButton::menu-indicator { image: none; }
            QToolButton::hover {
                background-color: %s;
                outline: none;
            }
            """ % hover_color
        )
        self.setMenu(menu)
