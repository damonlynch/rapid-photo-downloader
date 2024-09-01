# SPDX-FileCopyrightText: Copyright 2020 Martin Fitzpatrick
# SPDX-License-Identifier: MIT OR BSD-2-Clause

# Source:
# https://github.com/pythonguis/python-qtwidgets/blob/master/qtwidgets/passwordedit/password.py

# Edited Damon Lynch 2024 to remove resource import
# Edited Damon Lynch 2024 to optimize imports

from PyQt5 import QtGui, QtWidgets

from raphodo.tools.utilities import data_file_path


class PasswordEdit(QtWidgets.QLineEdit):
    """
    Password LineEdit with icons to show/hide password entries.
    Based on this example by Kushal Das:
    https://kushaldas.in/posts/creating-password-input-widget-in-pyqt.html
    """

    def __init__(self, show_visibility=True, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.visibleIcon = QtGui.QIcon(data_file_path("icons/eye.svg"))
        self.hiddenIcon = QtGui.QIcon(data_file_path("icons/hidden.svg"))

        self.setEchoMode(QtWidgets.QLineEdit.Password)

        if show_visibility:
            # Add the password hide/shown toggle at the end of the edit box.
            self.togglepasswordAction = self.addAction(
                self.visibleIcon, QtWidgets.QLineEdit.TrailingPosition
            )
            self.togglepasswordAction.triggered.connect(self.on_toggle_password_Action)

        self.password_shown = False

    def on_toggle_password_Action(self):
        if not self.password_shown:
            self.setEchoMode(QtWidgets.QLineEdit.Normal)
            self.password_shown = True
            self.togglepasswordAction.setIcon(self.hiddenIcon)
        else:
            self.setEchoMode(QtWidgets.QLineEdit.Password)
            self.password_shown = False
            self.togglepasswordAction.setIcon(self.visibleIcon)
