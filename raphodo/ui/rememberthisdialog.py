# SPDX-FileCopyrightText: Copyright 2016-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Yes/No dialog that displays a statement along with a "Remember this choice"
or "Don't ask me about this again" checkbox.
"""

from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QGridLayout, QLabel

from raphodo.constants import RememberThisButtons, RememberThisMessage
from raphodo.internationalisation.install import install_gettext
from raphodo.tools.utilities import data_file_path
from raphodo.ui.viewutils import standardIconSize, translateDialogBoxButtons

install_gettext()


class RememberThisDialog(QDialog):
    """
    A small dialog window that prompts the user if they want to
    do something or not.

    Includes a prompt whether to remember the choice.

    See also standardMessageBox in viewutils.py
    """

    def __init__(
        self,
        message: str,
        icon: QPixmap | str,
        remember: RememberThisMessage,
        parent,
        buttons: RememberThisButtons = RememberThisButtons.yes_no,
        title: str | None = None,
        message_contains_link: bool | None = False,
    ) -> None:
        super().__init__(parent)

        self.remember = False

        messageLabel = QLabel(message)
        messageLabel.setWordWrap(True)

        if message_contains_link:
            messageLabel.setOpenExternalLinks(True)
            messageLabel.setTextFormat(Qt.RichText)

        iconLabel = QLabel()
        if isinstance(icon, str):
            iconLabel.setPixmap(QIcon(data_file_path(icon)).pixmap(standardIconSize()))
        else:
            iconLabel.setPixmap(icon)

        if remember == RememberThisMessage.remember_choice:
            question = _("&Remember this choice")
        elif remember == RememberThisMessage.do_not_ask_again:
            question = _("&Don't ask me about this again")
        elif remember == RememberThisMessage.do_not_warn_again:
            question = _("&Don't warn me about this again")
        else:
            assert (
                remember
                == RememberThisMessage.do_not_warn_again_about_missing_libraries
            )
            question = _(
                "&Don't warn me again about missing or broken program libraries"
            )

        self.rememberCheckBox = QCheckBox(question)

        self.rememberCheckBox.setChecked(False)
        buttonBox = QDialogButtonBox()

        if buttons == RememberThisButtons.yes_no:
            yesButton = buttonBox.addButton(QDialogButtonBox.Yes)
            noButton = buttonBox.addButton(QDialogButtonBox.No)
        else:
            okayButton = buttonBox.addButton(QDialogButtonBox.Ok)

        translateDialogBoxButtons(buttonBox)

        grid = QGridLayout()
        grid.setSpacing(11)
        grid.setContentsMargins(11, 11, 11, 11)
        grid.addWidget(iconLabel, 0, 0, 2, 1)
        grid.addWidget(messageLabel, 0, 1, 1, 1)
        grid.addWidget(self.rememberCheckBox, 1, 1, 1, 1)
        grid.addWidget(buttonBox, 2, 0, 1, 2)
        self.setLayout(grid)
        if title is None or not title:
            self.setWindowTitle(_("Rapid Photo Downloader"))
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
