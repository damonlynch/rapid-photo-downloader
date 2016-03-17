# Copyright (C) 2015-2016 Damon Lynch <damonlynch@gmail.com>

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

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2015-2016, Damon Lynch"

from enum import IntEnum

from PyQt5.QtGui import (QColor, QPalette)
from PyQt5.QtWidgets import (QPushButton, QStylePainter, QStyle, QStyleOptionButton, QHBoxLayout)

class VerticalRotation(IntEnum):
    left_side = 270
    right_side = 90

class FlatButton:
    def setFlatStyle(self, button: QPushButton,
                     darker_if_checked: bool=True,
                     additional_style: str='') -> None:
        color = button.palette().color(button.backgroundRole())
        default_color = color.name(QColor.HexRgb)
        if darker_if_checked:
            checked_color = color.darker(125).name(QColor.HexRgb)
        else:
            checked_color = default_color
        hover_color = color.darker(110).name(QColor.HexRgb)

        # outline:none is used to remove the rectangle that appears on a
        # button when the button has focus
        # http://stackoverflow.com/questions/17280056/qt-css-decoration-on-focus
        button.setStyleSheet("""
        QPushButton { background-color: %s; outline: none; %s}
        QPushButton:checked { background-color: %s; border: none; }
        QPushButton:hover{ background-color: %s; border-style: inset; }
        """ % (default_color, additional_style, checked_color, hover_color))


class RotatedButton(QPushButton, FlatButton):
    leftSide = 270.0
    rightSide = 90.0

    def __init__(self, text: str, rotation: float,
                 flat: bool=True, checkable: bool=True, parent=None) -> None:
        super().__init__(text, parent)
        self.buttonRotation = rotation
        if flat:
            self.setFlat(flat)
            self.setFlatStyle(self)
        self.setCheckable(checkable)

    def paintEvent(self, event):
        painter = QStylePainter(self)
        painter.rotate(self.buttonRotation)
        if self.buttonRotation == VerticalRotation.left_side:
            painter.translate(-1 * self.height(), 0)
        elif self.buttonRotation == VerticalRotation.right_side:
            painter.translate(0, -1 * self.width())
        painter.drawControl(QStyle.CE_PushButton, self.getSyleOptions())

    def setRotation(self, rotation: float):
        self.buttonRotation = rotation

    # def minimumSizeHint(self):
    #     size = super().minimumSizeHint()
    #     size.transpose()
    #     return size

    def sizeHint(self):
        size = super().sizeHint()
        size.transpose()
        return size

    def getSyleOptions(self) -> QStyleOptionButton:
        options = QStyleOptionButton()
        options.initFrom(self)
        size = options.rect.size()
        size.transpose()
        options.rect.setSize(size)

        try:
            options.features = QStyleOptionButton.None_
        except AttributeError:
            # Allow for bug in PyQt 5.4
            options.features = getattr(QStyleOptionButton, 'None')
        if self.isFlat():
            options.features |= QStyleOptionButton.Flat
        if self.menu():
            options.features |= QStyleOptionButton.HasMenu
        if self.autoDefault() or self.isDefault():
            options.features |= QStyleOptionButton.AutoDefaultButton
        if self.isDefault():
            options.features |= QStyleOptionButton.DefaultButton
        if self.isDown() or (self.menu() and self.menu().isVisible()):
            options.state |= QStyle.State_Sunken
        if self.isChecked():
            options.state |= QStyle.State_On
        if not self.isFlat() and not self.isDown():
            options.state |= QStyle.State_Raised

        options.text = self.text()
        options.icon = self.icon()
        options.iconSize = self.iconSize()
        return options





