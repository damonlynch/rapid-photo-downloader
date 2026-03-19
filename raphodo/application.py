#  SPDX-FileCopyrightText: 2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: GPL-3.0-or-later

import logging
from typing import Any

from PyQt6.QtCore import QEvent, pyqtSignal, pyqtSlot
from PyQt6.QtDBus import QDBusConnection, QDBusInterface, QDBusVariant
from PyQt6.QtGui import QColor, QPalette

from raphodo.constants import StockAccent
from raphodo.qtsingleapplication import QtSingleApplication
from raphodo.ui.applicationpalette import darkPalette, standardPalette
from raphodo.ui.gnomepalette import GnomeAccentColor
from raphodo.ui.uipalette import listViewBorderColor


class Application(QtSingleApplication):
    """
    Handle Linux desktop color scheme (dark mode) and accent color changes
    """

    # bool: is dark mode True or False
    applicationPaletteChanged = pyqtSignal(bool)

    def __init__(self, programId: str, *argv) -> None:
        super().__init__(programId, *argv)
        self._log_accent = False
        self._dark_mode = False
        self._accentColor = QColor(StockAccent)

        self._raw_color_scheme: int = 2
        # tuple[float, float, float]
        self._raw_accent_colour: tuple | None = None
        self._raw_gtk_theme: str | None

        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return

        # Connect using the explicit signature 'ssv'
        # 'v' maps specifically to QDBusVariant in the receiver
        bus.connect(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Settings",
            "SettingChanged",
            "ssv",
            self.DBusSettingChanged,
        )

        self.setStartupPalette()

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ApplicationPaletteChange:
            listViewBorderColor.cache_clear()
            self.applicationPaletteChanged.emit(self.darkMode)
        return super().event(event)

    @property
    def darkMode(self) -> bool:
        return self._dark_mode

    @darkMode.setter
    def darkMode(self, dark_mode: bool) -> None:
        self._dark_mode = dark_mode
        if dark_mode:
            self.setPalette(darkPalette(accent=self.accentColor))
        else:
            self.setPalette(standardPalette(accent=self.accentColor))

    @property
    def accentColor(self) -> QColor:
        return self._accentColor

    @accentColor.setter
    def accentColor(self, accentColor: QColor) -> None:
        # Don't log the accent color during start-up
        if self._log_accent:
            logging.debug("Setting accent color to %s", accentColor.name())
        else:
            self._log_accent = True

        self._accentColor = accentColor
        palette = self.palette()
        palette.setColor(
            QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight, accentColor
        )
        palette.setColor(
            QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight, accentColor
        )
        self.setPalette(palette)

    @pyqtSlot(str, str, QDBusVariant)
    def DBusSettingChanged(self, namespace, key, dbus_variant):
        match namespace:
            case "org.freedesktop.appearance":
                match key:
                    case "color-scheme":
                        color_scheme = dbus_variant.variant()
                        if color_scheme == self._raw_color_scheme:
                            return
                        self._raw_color_scheme = color_scheme
                        self._setDarkMode()
                    case "accent-color":
                        raw_color = dbus_variant.variant()
                        if self._raw_accent_colour == raw_color:
                            return
                        self._raw_accent_colour = raw_color[:3]
                        self._setAccentColor()
            case "org.gnome.desktop.interface":
                match key:
                    case "gtk-theme":
                        color_identifier = dbus_variant.variant()
                        if color_identifier == self._raw_gtk_theme:
                            return
                        self._raw_gtk_theme = color_identifier
                        self._setThemeColor()

    @staticmethod
    def _callDBus(iface, namespace, key) -> Any:
        msg = iface.call("Read", namespace, key)

        if not msg.errorName():
            args = msg.arguments()
            if args:
                raw_val = args[0]
                if isinstance(raw_val, QDBusVariant):
                    return raw_val.variant()
                else:
                    return raw_val
        return None

    def setStartupPalette(self):
        iface = QDBusInterface(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Settings",
            QDBusConnection.sessionBus(),
        )

        self._raw_color_scheme = self._callDBus(
            iface=iface, namespace="org.freedesktop.appearance", key="color-scheme"
        )
        self._raw_accent_colour = self._callDBus(
            iface=iface, namespace="org.freedesktop.appearance", key="accent-color"
        )
        self._raw_gtk_theme = self._callDBus(
            iface=iface, namespace="org.gnome.desktop.interface", key="gtk-theme"
        )

        self._setDarkMode()
        if self._raw_accent_colour is not None or self._raw_gtk_theme is None:
            self._setAccentColor()
        elif self._raw_gtk_theme:
            self._setThemeColor()

    def _setDarkMode(self) -> None:
        self.darkMode = self._raw_color_scheme == 1

    def _setAccentColor(self) -> None:
        if self._raw_accent_colour is not None:
            self.accentColor = QColor.fromRgbF(*self._raw_accent_colour)
        else:
            logging.debug("Setting stock accent color", self._raw_accent_colour)
            self.accentColor = QColor(StockAccent)

    def _setThemeColor(self) -> None:
        if self._raw_accent_colour is not None:
            return
        color = QColor(GnomeAccentColor[self._raw_gtk_theme.lower().strip()])
        if color != self.accentColor:
            logging.debug("Setting accent color using GTK theme")
            self.accentColor = color
