# Copyright (C) 2015-2022 Damon Lynch <damonlynch@gmail.com>

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

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2015-2022, Damon Lynch"

from enum import IntEnum

from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import (
    QPushButton,
    QStylePainter,
    QStyle,
    QStyleOptionButton,
    QSizePolicy,
)


from raphodo.ui.viewutils import is_dark_mode, menuHoverColor


class VerticalRotation(IntEnum):
    left_side = 270
    right_side = 90


class FlatButton:
    _padding = (
        "padding-left: {padding_side}px; padding-right: {padding_side}px; padding-top: "
        "{padding_top}px; padding-bottom: {padding_bottom}px;".format(
            padding_top=6, padding_side=7, padding_bottom=6
        )
    )

    def setFlatStyle(
        self,
        button: QPushButton,
        darker_if_checked: bool = True,
        padding: str = "",
        color: QColor = None,
        text_color: QColor = None,
    ) -> None:
        if color is None:
            color = QPalette().color(QPalette.Window)
        default_color = color.name(QColor.HexRgb)

        if darker_if_checked:
            if is_dark_mode():
                checked_color = QPalette().color(QPalette.Light).name(QColor.HexRgb)
            else:
                checked_color = color.darker(125).name(QColor.HexRgb)
        else:
            checked_color = default_color

        hover_color = menuHoverColor().name(QColor.HexRgb)

        if not padding:
            padding = self._padding

        if text_color is not None:
            text = "color: {};".format(text_color.name(QColor.HexRgb))
        else:
            text = ""

        # outline:none is used to remove the rectangle that appears on a
        # button when the button has focus
        # http://stackoverflow.com/questions/17280056/qt-css-decoration-on-focus
        stylesheet = """
        QPushButton { background-color: %s;
                      border: 0px;
                      outline: none;
                      %s
                      %s}
        QPushButton:checked { background-color: %s; border: none; }
        QPushButton:hover{ background-color: %s; border-style: inset; }
        """ % (
            default_color,
            padding,
            text,
            checked_color,
            hover_color,
        )  #

        button.setStyleSheet(stylesheet)

    def setHighlightedFlatStyle(self, button: QPushButton) -> None:
        palette = QPalette()
        color = palette.color(palette.Highlight)
        text_color = palette.color(palette.HighlightedText)
        self.setFlatStyle(
            button, color=color, text_color=text_color, darker_if_checked=False
        )


class RotatedButton(QPushButton, FlatButton):
    leftSide = 270.0
    rightSide = 90.0

    def __init__(
        self,
        text: str,
        rotation: float,
        flat: bool = True,
        use_highlight_color=False,
        checkable: bool = True,
        parent=None,
    ) -> None:
        """
        A push button to show in the left or right side of a window
        :param text: text to display
        :param rotation: whether on the left or right side of the window
        :param flat: if True, set style to flat style
        :param use_highlight_color: if True, the button's color should be the palette's
         color for highlighting selected items. Takes effect only when using a flat is
         also True.
        :param checkable: if the button is checkable or not
        :param parent: optional parent widget
        """

        super().__init__(text, parent)
        self.buttonRotation = rotation
        if flat:
            # Use only the stylesheet to give the appearance of being flat.
            # Don't mix and match stylesheet and non-stylesheet options for widgets.
            # http://stackoverflow.com/questions/34654545/qt-flat-qpushbutton-background-color-doesnt-work
            if use_highlight_color:
                self.setHighlightedFlatStyle(self)
            else:
                self.setFlatStyle(self)
        self.setCheckable(checkable)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.MinimumExpanding)

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
            options.features = getattr(QStyleOptionButton, "None")
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

    def setHighlighted(self, highlighted: bool) -> None:
        if highlighted:
            self.setHighlightedFlatStyle(self)
        else:
            self.setFlatStyle(self)
        self.update()
