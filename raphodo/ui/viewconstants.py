# SPDX-FileCopyrightText: Copyright 2016-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from PyQt5.QtCore import QSize
from PyQt5.QtGui import QFont, QFontMetrics


def icon_size() -> int:
    return standard_font_size(shrink_on_odd=False)


def iconQSize() -> QSize:
    s = icon_size()
    return QSize(s, s)


def standard_font_size(shrink_on_odd: bool = True) -> int:
    h = QFontMetrics(QFont()).height()
    if h % 2 == 1:
        if shrink_on_odd:
            h -= 1
        else:
            h += 1
    return h
