__author__ = 'Damon Lynch'

from enum import IntEnum

from PyQt5.QtGui import (QColor, QPalette)
from PyQt5.QtWidgets import (QPushButton, QStylePainter, QStyle,
                             QStyleOptionButton)

class VerticalRotation(IntEnum):
    left_side = 270
    right_side = 90


class RotatedButton(QPushButton):
    leftSide = 270.0
    rightSide = 90.0

    def __init__(self, text, parent, rotation: float, flat:bool = True,
                 checkable: bool=True):
        super().__init__(text, parent)
        self.buttonRotation = rotation
        if flat:
            self.setFlat(flat)
            self.setFlatStyle()
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

    def minimumSizeHint(self):
        size = super().minimumSizeHint()
        # size.transpose()
        return size

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

    def setFlatStyle(self):
        color = self.palette().color(self.backgroundRole())
        default_color = color.name(QColor.HexRgb)
        checked_color = color.darker(125).name(QColor.HexRgb)
        hover_color = color.darker(110).name(QColor.HexRgb)

        # outline:none is used to remove the rectangle that apperas on a
        # button when the button has focus
        # http://stackoverflow.com/questions/17280056/qt-css-decoration-on-focus
        self.setStyleSheet("""
        QPushButton { background-color: %s; outline: none}
        QPushButton:checked { background-color: %s; border: none; }
        QPushButton:hover{ background-color: %s; border-style: inset; }
        """ % (default_color, checked_color, hover_color))



