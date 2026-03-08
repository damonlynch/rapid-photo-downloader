#  SPDX-FileCopyrightText: 2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: GPL-3.0-or-later

from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from PyQt6.QtDBus import QDBusConnection, QDBusInterface, QDBusVariant
from PyQt6.QtGui import QColor

from raphodo.constants import StockAccent


class DesktopColorSchemeMonitor(QObject):
    colorSchemeChanged = pyqtSignal(str)
    accentColorChanged = pyqtSignal(QColor)

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._color_scheme: int | None = None
        self._accent_colour: tuple[float, float, float] | None = None

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
            self.onSettingChanged,
        )

        self.setInitialState()

    def accentColor(self) -> QColor | None:
        if self._accent_colour is not None:
            return QColor.fromRgbF(*self._accent_colour)
        return QColor(StockAccent)

    def colorScheme(self) -> str:
        if self._color_scheme is not None:
            return "dark" if self._color_scheme == 1 else "light"
        return "light"

    @pyqtSlot(str, str, QDBusVariant)
    def onSettingChanged(self, namespace, key, dbus_variant):
        if namespace == "org.freedesktop.appearance":
            match key:
                case "color-scheme":
                    color_scheme = dbus_variant.variant()
                    if color_scheme == self._color_scheme:
                        return
                    self._color_scheme = color_scheme
                    if color_scheme is not None:
                        self.colorSchemeChanged.emit(self.colorScheme())
                case "accent-color":
                    raw_color = dbus_variant.variant()
                    if self._accent_colour == raw_color:
                        return
                    self._accent_colour = raw_color
                    if raw_color is not None:
                        self.accentColorChanged.emit(self.accentColor())

    def _callDBus(self, iface, key) -> Any:
        msg = iface.call("Read", "org.freedesktop.appearance", key)

        if not msg.errorName():
            args = msg.arguments()
            if args:
                raw_val = args[0]
                if isinstance(raw_val, QDBusVariant):
                    return raw_val.variant()
                else:
                    return raw_val
        return None

    def setInitialState(self):
        iface = QDBusInterface(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Settings",
            QDBusConnection.sessionBus(),
        )

        self._color_scheme = self._callDBus(iface=iface, key="color-scheme")
        self._accent_colour = self._callDBus(iface=iface, key="accent-color")
