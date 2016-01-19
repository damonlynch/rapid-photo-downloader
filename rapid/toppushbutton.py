__author__ = 'Damon Lynch'

# Copyright (C) 2016 Damon Lynch <damonlynch@gmail.com>

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

from PyQt5.QtCore import QSize
from PyQt5.QtGui import (QFont, QIcon)
from PyQt5.QtWidgets import (QPushButton, QSizePolicy)

from rotatedpushbutton import FlatButton

class TopPushButton(QPushButton, FlatButton):
    def __init__(self, text, parent) -> None:
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        self.setFlat(True)
        self.setFlatStyle(self, darker_if_checked=False)

        font = self.font() # type: QFont
        top_row_font_size = font.pointSize() + 8
        self.top_row_icon_size = top_row_font_size + 10
        font.setPointSize(top_row_font_size)
        self.setFont(font)

    def setIcon(self, icon: QIcon) -> None:
        super().setIcon(icon)
        self.setIconSize(QSize(self.top_row_icon_size, self.top_row_icon_size))
