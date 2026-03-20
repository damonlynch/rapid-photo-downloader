#  SPDX-FileCopyrightText: 2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: GPL-3.0-or-later

import sys

from PyQt6.QtCore import QRect, QSize, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import (
    QPaintEvent,
    QPalette,
    QPen,
    QShowEvent,
)
from PyQt6.QtWidgets import (
    QFrame,
    QScrollArea,
    QWidget,
)

from raphodo.ui.uipalette import listViewBorderColor


def paletteMidPen() -> QPen:
    return QPen(listViewBorderColor())


class ScrollAreaNoFrame(QScrollArea):
    """
    Scroll Area with no frame
    """

    horizontalScrollBarVisible = pyqtSignal(bool)
    verticalScrollBarVisible = pyqtSignal(bool)

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent=parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        return
