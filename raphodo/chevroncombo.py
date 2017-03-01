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
Combo box with a chevron selector
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2011-2017, Damon Lynch"

from PyQt5.QtWidgets import QStyledItemDelegate, QComboBox, QLabel, QSizePolicy
from PyQt5.QtGui import QFontMetrics, QFont
from PyQt5.QtCore import Qt

import raphodo.qrc_resources as qrc_resources


class ChevronCombo(QComboBox):
    """
    Combo box with a chevron selector
    """

    def __init__(self, in_panel: bool=False, parent=None) -> None:
        """
        :param in_panel: if True, widget color set to background color,
         else set to window color
        """

        super().__init__(parent)

        if in_panel:
            color = 'background'
        else:
            color = 'window'

        style = """
        QComboBox {
            border: 0px;
            padding: 1px 3px 1px 3px;
            background-color: palette(%(color)s);
            selection-background-color: palette(highlight);
            color: palette(window-text);
        }

        QComboBox:on { /* shift the text when the popup opens */
            padding-top: 3px;
            padding-left: 4px;
        }

        QComboBox::drop-down {
             subcontrol-origin: padding;
             subcontrol-position: top right;
             width: %(width)dpx;
             border: 0px;
         }

        QComboBox::down-arrow {
            image: url(:/chevron-down.svg);
            width: %(width)dpx;
        }

        QComboBox QAbstractItemView {
            outline: none;
            border: 1px solid palette(shadow);
            background-color: palette(%(color)s);
            selection-background-color: palette(highlight);
            selection-color: palette(highlighted-text);
            color: palette(window-text)
        }

        QComboBox QAbstractItemView::item {
            padding: 3px;
        }
        """ % dict(width=int(QFontMetrics(QFont()).height() * (2 / 3)), color=color)

        self.label_style = """
        QLabel {border-color: palette(%(color)s); border-width: 1px; border-style: solid;}
        """ % dict(color=color)

        self.setStyleSheet(style)

        # Delegate overrides default delegate for the Combobox, which is
        # pretty ugly whenever a style sheet color is applied.
        # See http://stackoverflow.com/questions/13308341/qcombobox-abstractitemviewitem?rq=1
        self.setItemDelegate(QStyledItemDelegate())

        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Maximum)

    def makeLabel(self, text: str) -> QLabel:
        label = QLabel(text)
        # Add an invisible border to make the label vertically align with the comboboxes
        # Otherwise it's off by 1px
        # TODO perhaps come up with a better way to solve this alignment problem
        label.setStyleSheet(self.label_style)
        label.setAlignment(Qt.AlignBottom)
        label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Maximum)
        return label
