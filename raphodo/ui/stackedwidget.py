# SPDX-FileCopyrightText: Copyright 2015-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from PyQt5.QtCore import QSize, pyqtSlot
from PyQt5.QtWidgets import QSizePolicy, QStackedWidget, QWidget


class ResizableStackedWidget(QStackedWidget):
    """
    The default of QStackedWidget is not to resize itself to the currently displayed
    widget. This widget adjusts its size to the currently displayed widget.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent=parent)
        self.currentChanged.connect(self.onCurrentChanged)

    @pyqtSlot(int)
    def onCurrentChanged(self, index: int) -> None:
        for i in range(self.count()):
            if i == index:
                verticalPolicy = QSizePolicy.MinimumExpanding
            else:
                verticalPolicy = QSizePolicy.Ignored
            widget = self.widget(i)
            widget.setSizePolicy(widget.sizePolicy().horizontalPolicy(), verticalPolicy)
            widget.adjustSize()
        self.adjustSize()

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def sizeHint(self) -> QSize:
        return self.currentWidget().sizeHint()
