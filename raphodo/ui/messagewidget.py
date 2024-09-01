# SPDX-FileCopyrightText: Copyright 2017-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Display messages to the user in stacked widget
"""

from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QFocusEvent, QMouseEvent
from PyQt5.QtWidgets import QLabel, QPushButton, QSizePolicy, QStackedWidget

from raphodo.internationalisation.install import install_gettext

install_gettext()


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

    def __init__(self, messages: tuple[str, ...], parent=None) -> None:
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
