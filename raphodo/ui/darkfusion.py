#  SPDX-FileCopyrightText: 2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: GPL-3.0-or-later


from PyQt6.QtGui import QPainter, QPalette
from PyQt6.QtWidgets import (
    QProxyStyle,
    QStyle,
    QStyleOption,
    QStyleOptionButton,
    QWidget,
)

highlight_darken = 262


class DarkModeQuirkCheckBoxStyle(QProxyStyle):
    """
    Make a fusion themed checkbox visible when running in dark mode without
    using stylesheets
    """

    def __init__(self, style: QStyle | None = None):
        super().__init__(style)
        self._proxy_enabled = True
        self._proxy_state = self._proxy_enabled

    def setOverride(self, override: bool) -> None:
        if override:
            self._proxy_state = self._proxy_enabled
            self._proxy_enabled = False
        else:
            self._proxy_enabled = self._proxy_state

    @property
    def proxyEnabled(self) -> bool:
        return self._proxy_enabled

    @proxyEnabled.setter
    def proxyEnabled(self, enabled: bool) -> None:
        self._proxy_enabled = self._proxy_state = enabled

    def applicationPaletteChanged(self, dark_mode: bool) -> None:
        self.proxyEnabled = dark_mode

    def drawPrimitive(
        self,
        element: QStyle.PrimitiveElement,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ):
        if (
            element == QStyle.PrimitiveElement.PE_IndicatorCheckBox
            and self._proxy_enabled
        ):
            new_option = QStyleOptionButton(option)
            highlight = option.palette.color(QPalette.ColorRole.Highlight)

            is_checked = new_option.state & QStyle.StateFlag.State_On

            if is_checked:
                new_option.palette.setColor(
                    QPalette.ColorRole.Base, highlight.darker(highlight_darken)
                )
                new_option.palette.setColor(QPalette.ColorRole.Window, highlight)
            else:
                # unchecked
                new_option.palette.setColor(
                    QPalette.ColorRole.Base,
                    option.palette.color(QPalette.ColorRole.Button),
                )
                new_option.palette.setColor(
                    QPalette.ColorRole.Window,
                    option.palette.color(QPalette.ColorRole.Light),
                )
            option = new_option
        super().drawPrimitive(element, option, painter, widget)
