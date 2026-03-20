#  SPDX-FileCopyrightText: 2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: GPL-3.0-or-later
from functools import cache

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QListView


@cache
def listViewBorderColor() -> QColor:
    frame = QListView()
    image = QImage(20, 20, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(Qt.GlobalColor.white))
    frame.render(image)
    color = QColor(image.pixel(0, 0))
    return color
