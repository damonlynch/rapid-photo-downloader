# Copyright (C) 2017-2021 Damon Lynch <damonlynch@gmail.com>

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

"""
Display messages to the user in stacked widget
"""

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2017-2021, Damon Lynch"

from typing import Tuple


from PyQt5.QtCore import Qt, pyqtSlot, pyqtSignal
from PyQt5.QtWidgets import QSizePolicy, QStackedWidget, QPushButton, QLabel
from PyQt5.QtGui import QMouseEvent, QFocusEvent


class MessageWidget(QStackedWidget):
    """
    Display messages to the user in stacked widget.

    Index 0 always represents a blank state.

    Other indexes represent the position in the
    tuple of messages.

    If the message does not start with an html tag <i> or <b>,
    the start of the message will be modified to display <i><b>Hint:</b>
    (with closing tags too, naturally).
    """

    def __init__(self, messages: Tuple[str, ...], parent=None) -> None:
        super().__init__(parent)

        # For some obscure reason, must set the label types for all labels in the
        # stacked widget to have the same properties, or else the stacked layout size
        # goes bonkers. Must make the empty label contain *something*, too, so make it
        # contain a space.
        blank = QLabel(" ")
        blank.setWordWrap(True)
        blank.setTextFormat(Qt.RichText)
        self.addWidget(blank)

        for message in messages:
            if message.startswith("<i>") or message.startswith("<b>"):
                label = QLabel(message)
            else:
                # Translators: please do not modify or leave out html formatting tags
                # like <i> and <b>. These are used to format the text the users sees
                label = QLabel(
                    _("<i><b>Hint:</b> %(message)s</i>") % dict(message=message)
                )
            label.setWordWrap(True)
            label.setTextFormat(Qt.RichText)
            label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            self.addWidget(label)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)


class MessageButton(QPushButton):
    """
    A simple QPushButton that emits a signal when it is entered / exited.
    """

    isActive = pyqtSignal()
    isInactive = pyqtSignal()

    def __init__(self, label: str, parent=None) -> None:
        super().__init__(label, parent)

    @pyqtSlot(QMouseEvent)
    def enterEvent(self, event: QMouseEvent) -> None:
        self.isActive.emit()
        super().enterEvent(event)

    @pyqtSlot(QMouseEvent)
    def leaveEvent(self, event: QMouseEvent) -> None:
        self.isInactive.emit()
        super().leaveEvent(event)

    @pyqtSlot(QFocusEvent)
    def focusInEvent(self, event: QFocusEvent) -> None:
        self.isActive.emit()
        super().focusInEvent(event)

    @pyqtSlot(QFocusEvent)
    def focusOutEvent(self, event: QFocusEvent) -> None:
        self.isInactive.emit()
        super().focusOutEvent(event)
