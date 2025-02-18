# SPDX-FileCopyrightText: Copyright 2015-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from PyQt5.QtCore import QSize, Qt, pyqtSlot
from PyQt5.QtWidgets import QSizePolicy, QStackedWidget, QWidget


class ResizableStackedWidget(QStackedWidget):
    """
    The default of QStackedWidget is not to resize itself to the currently displayed
    widget. This widget adjusts its size to the currently displayed widget.
    """

    def __init__(
        self,
        growDirection: Qt.Orientation = Qt.Orientation.Vertical,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self.growDirection = growDirection
        self.currentChanged.connect(self.onCurrentChanged)

    @pyqtSlot(int)
    def onCurrentChanged(self, index: int) -> None:
        for i in range(self.count()):
            if i == index:
                policy = QSizePolicy.MinimumExpanding
            else:
                policy = QSizePolicy.Ignored
            widget = self.widget(i)
            if self.growDirection == Qt.Orientation.Vertical:
                widget.setSizePolicy(widget.sizePolicy().horizontalPolicy(), policy)
            else:
                widget.setSizePolicy(policy, widget.sizePolicy().verticalPolicy())
            widget.adjustSize()
        self.adjustSize()

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def sizeHint(self) -> QSize:
        return self.currentWidget().sizeHint()
