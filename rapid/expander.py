# -*- coding: utf-8 -*-
#
# Copyright 2012 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranties of
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# In addition, as a special exception, the copyright holders give
# permission to link the code of portions of this program with the
# OpenSSL library under certain conditions as described in each
# individual source file, and distribute linked combinations
# including the two.
# You must obey the GNU General Public License in all respects
# for all of the code used other than OpenSSL.  If you modify
# file(s) with this exception, you may extend this exception to your
# version of the file(s), but you are not obligated to do so.  If you
# do not wish to do so, delete this exception statement from your
# version.  If you delete this exception statement from all source
# files in the program, then also delete it here.

# 2015: Lightly modified by Damon Lynch to use Qt 5 and Python 3.4

"""A Expander widget similar to the GtkExpander."""

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout,
                             QWidget)

from qarrow import QArrow

# we are following the Qt style, lets tell pylint to ignore it
# pylint: disable=C0103


class QExpanderLabel(QWidget):
    """Widget used to show the label of a QExpander."""

    clicked = pyqtSignal()

    def __init__(self, label, parent=None):
        """Create a new instance."""
        super().__init__(parent)
        self.arrow = QArrow(QArrow.RIGHT)
        self.label = QLabel(label)
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        layout.addWidget(self.arrow)
        layout.addWidget(self.label)

    def mousePressEvent(self, event):
        """Mouse clicked."""
        if self.arrow.direction == QArrow.DOWN:
            self.arrow.direction = QArrow.RIGHT
        else:
            self.arrow.direction = QArrow.DOWN
        self.clicked.emit()

    def text(self):
        """Return the text of the label."""
        return self.label.text()

    def setText(self, text):
        """Set the text of the label."""
        self.label.setText(text)


class QExpander(QWidget):
    """A Qt implementation similar to GtkExpander."""

    def __init__(self, label, expanded=False, parent=None):
        """Create a new instance."""
        super(QExpander, self).__init__(parent)
        self.label = QExpanderLabel(label)
        self.label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.content = None
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)
        self.layout.addWidget(self.label)
        self.layout.addStretch()
        self.label.clicked.connect(self._on_label_clicked)
        self.setExpanded(expanded)

    def _on_label_clicked(self):
        """The expander widget was clicked."""
        self._expanded = not self._expanded
        self.setExpanded(self._expanded)

    def addWidget(self, widget):
        """Add a widget to the expander.

        The previous widget will be removed.
        """
        if self.content is not None:
            self.layout.removeWidget(self.content)
        self.content = widget
        self.content.setVisible(self._expanded)
        self.layout.insertWidget(1, self.content)

    def text(self):
        """Return the text of the label."""
        return self.label.text()

    def setText(self, text):
        """Set the text of the label."""
        self.label.setText(text)

    def expanded(self):
        """Return if widget is expanded."""
        return self._expanded

    # pylint: disable=W0201
    def setExpanded(self, is_expanded):
        """Expand the widget or not."""
        self._expanded = is_expanded
        if self._expanded:
            self.label.arrow.direction = QArrow.DOWN
        else:
            self.label.arrow.direction = QArrow.RIGHT
        if self.content is not None:
            self.content.setVisible(self._expanded)
    # pylint: enable=W0201
