# Copyright (C) 2016-2022 Damon Lynch <damonlynch@gmail.com>

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
__copyright__ = "Copyright 2016-2022, Damon Lynch"

import math
from typing import Tuple

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import (
    QFont,
    QIcon,
    QFontMetrics,
    QGuiApplication,
    QPainter,
    QPaintEvent,
)
from PyQt5.QtWidgets import QPushButton, QSizePolicy, QApplication

from raphodo.ui.rotatedpushbutton import FlatButton
from raphodo.ui.viewutils import is_dark_mode, darkModeIcon


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

        font = self.font()  # type: QFont
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
            "padding-left: {padding_side}px; padding-right: {padding_side}px; "
            "padding-top: {padding_top}px; padding-bottom: {padding_bottom}px;".format(
                padding_top=padding_top,
                padding_side=self.padding_side,
                padding_bottom=padding_bottom,
            )
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


def DownloadButtonHeight() -> Tuple[int, int]:
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
            """
            QPushButton {
            background-color: %(color)s;
            outline: none;
            padding-left: %(padding)dpx;
            padding-right: %(padding)dpx;
            border-radius: %(radius)dpx;
            border: 1px solid %(borderColor)s;
            height: %(height)dpx;
            color: %(textcolor)s;
            }
            QPushButton:hover {
            background-color: %(hoverColor)s;
            border: 1px solid %(hoverBorderColor)s;
            }
            QPushButton:disabled {
            background-color: %(disabledColor)s;
            color: %(disabledTextColor)s;
            border: 1px solid %(disabledBorderColor)s;
            }
            """
            % dict(
                color=primaryColor.name(),
                padding=padding,
                borderColor=borderColor.name(),
                hoverColor=hoverColor.name(),
                hoverBorderColor=hoverBorderColor.name(),
                height=height,
                radius=radius,
                textcolor=primaryTextColor.name(),
                disabledColor=disabledColor.name(),
                disabledTextColor=disabledTextColor.name(),
                disabledBorderColor=disabledBorderColor.name(),
            )
        )

    def setText(self, text: str) -> None:
        super().setText(text)
        self.rapidApp.sourceButton.updateGeometry()
