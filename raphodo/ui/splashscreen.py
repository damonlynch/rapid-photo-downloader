# SPDX-FileCopyrightText: Copyright 2016-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

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
