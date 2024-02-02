# Copyright (C) 2016-2024 Damon Lynch <damonlynch@gmail.com>

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
__copyright__ = "Copyright 2016-2024, Damon Lynch"

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QSplashScreen

from raphodo import __about__


class SplashScreen(QSplashScreen):
    def __init__(self, pixmap: QPixmap, flags) -> None:
        super().__init__(pixmap, flags)
        self.progress = 0
        try:
            self.image_width = pixmap.width() / pixmap.devicePixelRatioF()
        except AttributeError:
            self.image_width = pixmap.width() / pixmap.devicePixelRatio()

        self.progressBarPen = QPen(QBrush(QColor(Qt.white)), 2.0)

    def drawContents(self, painter: QPainter):
        painter.save()
        painter.setPen(QColor(Qt.black))
        painter.drawText(18, 64, __about__.__version__)
        if self.progress:
            painter.setPen(self.progressBarPen)
            x = int(self.progress / 100 * self.image_width)
            painter.drawLine(0, 360, x, 360)
        painter.restore()

    def setProgress(self, value: int) -> None:
        """
        Update splash screen progress bar
        :param value: percent done, between 0 and 100
        """

        self.progress = value
        self.repaint()
