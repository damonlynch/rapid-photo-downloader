# SPDX-FileCopyrightText: Copyright 2015-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from enum import IntEnum

from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import (
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyleOptionButton,
    QStylePainter,
)

from raphodo.internationalisation.install import install_gettext
from raphodo.ui.viewutils import is_dark_mode, menuHoverColor

install_gettext()


class VerticalRotation(IntEnum):
    left_side = 270
    right_side = 90


class FlatButton:
    _padding = (
        "padding-left: 7px; "
        "padding-right: 7px; "
        "padding-top: 6px; "
        "padding-bottom: 6px; "
    )

    def setFlatStyle(
        self,
        button: QPushButton,
        darker_if_checked: bool = True,
        padding: str = "",
        color: QColor | None = None,
        checkedHoverColor: QColor | None = None,
        text_color: QColor | None = None,
    ) -> None:
        """
        Apply styling to top left device(s) button, as well as left and
        right panel buttons.

        :param button: QPushButton to apply styling to
        :param darker_if_checked: True if appearance darkens when the button
         is checked
        :param padding: padding around the button
        :param color: button color
        :param checkedHoverColor: color to apply when the button is both checked
         and on hover
        :param text_color: button text color
        """

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

        if checkedHoverColor is None:
            hover_color = menuHoverColor().name(QColor.HexRgb)
        else:
            hover_color = checkedHoverColor.name(QColor.HexRgb)

        if not padding:
            padding = self._padding

        if text_color is not None:
            text = f"color: {text_color.name(QColor.HexRgb)};"
        else:
            text = ""

        # outline:none is used to remove the rectangle that appears on a
        # button when the button has focus
        # http://stackoverflow.com/questions/17280056/qt-css-decoration-on-focus
        stylesheet = f"""
        QPushButton {{
            background-color: {default_color};
            border: 0px;
            outline: none;
            {padding}
            {text}
        }}
        QPushButton:checked {{
            background-color: {checked_color};
            border: none;
        }}
        QPushButton:hover {{
            background-color: {hover_color};
            border-style: inset; 
        }}
        """

        button.setStyleSheet(stylesheet)

    def setHighlightedFlatStyle(self, button: QPushButton) -> None:
        palette = QPalette()
        color = palette.color(palette.Highlight)
        text_color = palette.color(palette.HighlightedText)
        self.setFlatStyle(
            button,
            color=color,
            text_color=text_color,
            darker_if_checked=False,
            checkedHoverColor=color.darker(106),
        )


class RotatedButton(QPushButton, FlatButton):
    left_side = 270.0
    right_side = 90.0

    def __init__(
        self,
        text: str,
        rotation: float,
        parent=None,
    ) -> None:
        """
        A push button to show in the left or right side of a window
        :param text: text to display
        :param rotation: whether on the left or right side of the window
        :param parent: optional parent widget
        """

        super().__init__(text, parent)
        self.buttonRotation = rotation
        # Use only the stylesheet to give the appearance of being flat.
        # Don't mix and match stylesheet and non-stylesheet options for widgets.
        # http://stackoverflow.com/questions/34654545/qt-flat-qpushbutton-background-color-doesnt-work
        self.setFlatStyle(self)
        self.setCheckable(True)
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
        """
        Change the button appearance to highlight the button using
        the theme's highlight color
        :param highlighted: if True the button will be highlighted
        """

        if highlighted:
            self.setHighlightedFlatStyle(self)
        else:
            self.setFlatStyle(self)
        self.update()
