# Copyright (C) 2016-2017 Damon Lynch <damonlynch@gmail.com>

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
Yes/No dialog that displays a statement along with a "Remember this choice"
or "Don't ask me about this again" checkbox.
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2016-2017, Damon Lynch"

from typing import Optional, Union
from PyQt5.QtCore import pyqtSlot
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QCheckBox, QLabel, QGridLayout

from gettext import gettext as _

from raphodo.constants import RememberThisMessage, RememberThisButtons
from raphodo.viewutils import standardIconSize,\
    translateButtons

class RememberThisDialog(QDialog):

    """
    A small dialog window that prompts the user if they want to
    do something or not.

    Includes a prompt whether to remember the choice.
    """

    def __init__(self, message: str,
                 icon: Union[QPixmap, str],
                 remember: RememberThisMessage,
                 parent,
                 buttons: RememberThisButtons=RememberThisButtons.yes_no,
                 title: Optional[str]=None) -> None:

        super().__init__(parent)

        self.remember = False

        messageLabel = QLabel(message)
        messageLabel.setWordWrap(True)

        iconLabel = QLabel()
        if isinstance(icon, str):
            iconLabel.setPixmap(QIcon(icon).pixmap(standardIconSize()))
        else:
            iconLabel.setPixmap(icon)

        if remember == RememberThisMessage.remember_choice:
            question =  _("&Remember this choice")
        elif remember == RememberThisMessage.do_not_ask_again:
            question = _("&Don't ask me about this again")
        elif remember == RememberThisMessage.do_not_warn_again:
            question = _("&Don't warn me about this again")
        else:
            assert remember == RememberThisMessage.do_not_warn_again_about_missing_libraries
            question = _("&Don't warn me again about missing or broken program libraries")

        self.rememberCheckBox = QCheckBox(question)

        self.rememberCheckBox.setChecked(False)
        buttonBox = QDialogButtonBox()

        if buttons == RememberThisButtons.yes_no:
            yesButton = buttonBox.addButton(QDialogButtonBox.Yes)
            noButton = buttonBox.addButton(QDialogButtonBox.No)
        else:
            okayButton = buttonBox.addButton(QDialogButtonBox.Ok)

        translateButtons(buttonBox)

        grid = QGridLayout()
        grid.setSpacing(11)
        grid.setContentsMargins(11, 11, 11, 11)
        grid.addWidget(iconLabel, 0, 0, 2, 1)
        grid.addWidget(messageLabel, 0, 1, 1, 1)
        grid.addWidget(self.rememberCheckBox, 1, 1, 1, 1)
        grid.addWidget(buttonBox, 2, 0, 1, 2)
        self.setLayout(grid)
        if title is None or not title:
            self.setWindowTitle(_('Rapid Photo Downloader'))
        else:
            self.setWindowTitle(title)

        if buttons == RememberThisButtons.yes_no:
            yesButton.clicked.connect(self.doAction)
            noButton.clicked.connect(self.doNotDoAction)
            noButton.setFocus()
        else:
            okayButton.clicked.connect(self.doAction)

    @pyqtSlot()
    def doAction(self) -> None:
        self.remember = self.rememberCheckBox.isChecked()
        super().accept()

    @pyqtSlot()
    def doNotDoAction(self) -> None:
        self.remember = self.rememberCheckBox.isChecked()
        super().reject()