# SPDX-FileCopyrightText: Copyright 2016-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

import math

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import (
    QFont,
    QFontMetrics,
    QGuiApplication,
    QIcon,
    QPainter,
    QPaintEvent,
)
from PyQt5.QtWidgets import QApplication, QPushButton, QSizePolicy

from raphodo.internationalisation.install import install_gettext
from raphodo.ui.rotatedpushbutton import FlatButton
from raphodo.ui.viewutils import darkModeIcon, is_dark_mode

install_gettext()


class TopPushButton(QPushButton, FlatButton):
    def __init__(self, text, parent, extra_top: int = 0) -> None:
        """

        :param text: text to display in the button
        :param extra_top: extra spacing at the top of the widget
        :param parent: parent widget
        """

        super().__init__(text, parent)
        self.rapidApp = parent
        self.setCheckable(True)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)

        font: QFont = self.font()
        top_row_font_size = font.pointSize() + 8
        self.top_row_icon_size = top_row_font_size + 10
        font.setPointSize(top_row_font_size)
        self.setFont(font)

        font_height = QFontMetrics(font).height()
        self.padding_side = math.ceil(font_height / 3.5)
        padding_bottom = math.ceil(font_height / 5.6)
        padding_top = padding_bottom + extra_top

        self.non_elided_text = ""

        padding = (
            f"padding-left: {self.padding_side}px; "
            f"padding-right: {self.padding_side}px; "
            f"padding-top: {padding_top}px; "
            f"padding-bottom: {padding_bottom}px; "
        )
        self.setFlatStyle(self, darker_if_checked=False, padding=padding)

    def text(self) -> str:
        return self.non_elided_text

    def setText(self, text: str) -> None:
        self.non_elided_text = text
        self.update()

    def setIcon(self, icon: QIcon) -> None:
        size = QSize(self.top_row_icon_size, self.top_row_icon_size)
        icon = darkModeIcon(icon=icon, size=size)
        super().setIcon(icon)
        self.setIconSize(size)

    def paintEvent(self, event: QPaintEvent):
        """
        Override default rendering to elide button text if it is bigger than half the
        window size
        """

        painter = QPainter(self)
        metrics = painter.fontMetrics()
        right_element_widths = (
            self.rapidApp.downloadButton.width() + self.rapidApp.menuButton.width()
        )
        window_width = self.rapidApp.width()
        window_half = window_width / 2
        if right_element_widths > window_half:
            maximum_width = window_width - right_element_widths
        else:
            maximum_width = window_half
        maximum_width -= self.padding_side - self.top_row_icon_size

        # account for situations where we might have negative values, i.e., display some
        # text at least
        maximum_width = max(30, maximum_width)

        usable_width = round(0.9 * maximum_width)
        elided_text = metrics.elidedText(
            self.non_elided_text, Qt.ElideMiddle, usable_width
        )
        super().setText(elided_text)
        super().paintEvent(event)


def DownloadButtonHeight() -> tuple[int, int]:
    font_height = (
        QFontMetrics(QApplication.font())
        .tightBoundingRect(_("Download 8 Photos and 10 Videos"))
        .height()
    )
    padding = math.ceil(font_height * 1.7)
    height = font_height // 2 * 6
    return height, padding


class DownloadButton(QPushButton):
    """
    Button used to initiate downloads
    """

    def __init__(self, text: str, parent) -> None:
        super().__init__(text, parent)

        self.rapidApp = parent
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)

        height, padding = DownloadButtonHeight()
        radius = height // 2

        palette = QGuiApplication.palette()
        primaryColor = palette.highlight().color()
        borderColor = primaryColor.darker(105)
        hoverColor = palette.highlight().color().darker(106)
        hoverBorderColor = hoverColor.darker(105)
        primaryTextColor = palette.highlightedText().color()

        if is_dark_mode():
            disabledColor = palette.window().color().lighter(130)
            disabledBorderColor = disabledColor.lighter(115)
            disabledTextColor = palette.highlightedText().color()
        else:
            disabledColor = palette.window().color().darker(120)
            disabledBorderColor = disabledColor.darker(105)
            disabledTextColor = palette.highlightedText().color()

        # outline:none is used to remove the rectangle that appears on a
        # button when the button has focus
        # http://stackoverflow.com/questions/17280056/qt-css-decoration-on-focus

        self.setStyleSheet(
            f"""
            QPushButton {{
            background-color: {primaryColor.name()};
            outline: none;
            padding-left: {padding}px;
            padding-right: {padding}px;
            border-radius: {radius}px;
            border: 1px solid {borderColor.name()};
            height: {height}px;
            color: {primaryTextColor.name()};
            }}
            QPushButton:hover {{
            background-color: {hoverColor.name()};
            border: 1px solid {hoverBorderColor.name()};
            }}
            QPushButton:disabled {{
            background-color: {disabledColor.name()};
            color: {disabledTextColor.name()};
            border: 1px solid {disabledBorderColor.name()};
            }}
            """
        )

    def setText(self, text: str) -> None:
        super().setText(text)
        self.rapidApp.sourceButton.updateGeometry()
