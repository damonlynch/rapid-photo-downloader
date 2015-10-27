__author__ = 'Damon Lynch'

from enum import IntEnum

from PyQt5.QtWidgets import (QPushButton, QStylePainter, QStyle,
                             QStyleOptionButton)

class VerticalRotation(IntEnum):
    left_side = 270
    right_side = 90


class RotatedButton(QPushButton):
    def __init__(self, text, parent, rotation: VerticalRotation):
        super().__init__(text, parent)
        self.buttonRotation = rotation

    def paintEvent(self, event):
        painter = QStylePainter(self)
        painter.rotate(self.buttonRotation)
        if self.buttonRotation == VerticalRotation.left_side:
            painter.translate(-1 * self.height(), 0)
        elif self.buttonRotation == VerticalRotation.right_side:
            painter.translate(0, -1 * self.width())
        painter.drawControl(QStyle.CE_PushButton, self.getSyleOptions())

    def minimumSizeHint(self):
        size = super().minimumSizeHint()
        # size.transpose()
        return size

    def sizeHint(self):
        size = super().sizeHint()
        size.transpose()
        return size

    def getSyleOptions(self):
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
