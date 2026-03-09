#  SPDX-FileCopyrightText: 2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: GPL-3.0-or-later

"""
Compatibility layer for Qt.

Use new signals with old versions of Qt6.
"""

from PyQt6.QtCore import QMetaMethod, Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication, QPalette
from PyQt6.QtWidgets import QCheckBox

from raphodo.constants import QtColorScheme


def build_qt_compat_metaclass(qt_base_class):
    qt_meta = type(qt_base_class)

    class QtCompatMeta(qt_meta):
        def __new__(mcls, name, bases, namespace, **kwargs):
            signal_backports = namespace.get("__qt_signal_backports__", {})
            method_backports = namespace.get("__qt_method_backports__", {})

            cls = super().__new__(mcls, name, bases, namespace, **kwargs)

            if not signal_backports and not method_backports:
                return cls

            # Find the first real Qt base class
            qt_base = next((b for b in bases if hasattr(b, "staticMetaObject")), None)

            if qt_base is None:
                return cls

            missing = {}
            if signal_backports:
                meta = qt_base.staticMetaObject

                existing_signatures = {
                    bytes(meta.method(i).methodSignature()).decode()
                    for i in range(meta.methodCount())
                    if meta.method(i).methodType() == QMetaMethod.MethodType.Signal
                }

                missing = {
                    signal_name: spec
                    for signal_name, spec in signal_backports.items()
                    if spec["signature"] not in existing_signatures
                }

            missing_methods = {
                method_name: spec
                for method_name, spec in method_backports.items()
                if not hasattr(qt_base, method_name)
            }

            if not missing and not missing_methods:
                return cls

            # Install missing signals at class level
            for signal_name, spec in missing.items():
                setattr(cls, signal_name, spec["signal"])

            # Install missing methods at class level
            for method_name, spec in missing_methods.items():
                setattr(cls, method_name, spec["method"])

            if not missing:
                return cls

            original_init = cls.__init__

            def __init__(self, *args, **kwargs):
                original_init(self, *args, **kwargs)

                for signal_name, spec in missing.items():
                    existing_signal = getattr(self, spec["connect_to"])
                    new_signal = getattr(self, signal_name)
                    converter = spec.get("converter")

                    if converter:
                        existing_signal.connect(
                            lambda value, s=new_signal, c=converter: s.emit(c(value))
                        )
                    else:
                        existing_signal.connect(
                            lambda value, s=new_signal: s.emit(value)
                        )

            cls.__init__ = __init__

            return cls

    return QtCompatMeta


QtCheckBoxCompatMeta = build_qt_compat_metaclass(QCheckBox)


class CompatCheckBox(QCheckBox, metaclass=QtCheckBoxCompatMeta):
    """
    Compatibility Layer for QCheckBox.

    Use signal checkStateChanged, introduced with Qt 6.7.
    """

    __qt_signal_backports__ = {
        "checkStateChanged": {
            "signature": "checkStateChanged(Qt::CheckState)",
            "signal": pyqtSignal(Qt.CheckState),
            "connect_to": "stateChanged",
            "converter": lambda v: Qt.CheckState(v),
        }
    }


# This remaining code is unused, but provides a template for
# adding compatibility layer methods.


def _detect_color_scheme() -> QtColorScheme:
    app = QGuiApplication.instance()
    if app is None:
        return QtColorScheme.Unknown

    palette = app.palette()
    window = palette.color(QPalette.ColorRole.Window)
    window_text = palette.color(QPalette.ColorRole.WindowText)
    return (
        QtColorScheme.Dark
        if window.lightnessF() < window_text.lightnessF()
        else QtColorScheme.Light
    )


class _CompatStyleHintsProxy:
    def __init__(self, style_hints):
        self._style_hints = style_hints

    def colorScheme(self) -> QtColorScheme:
        return _detect_color_scheme()

    def __getattr__(self, item):
        return getattr(self._style_hints, item)


_original_style_hints = QGuiApplication.styleHints


def _compat_style_hints(*args, **kwargs):
    style_hints = _original_style_hints(*args, **kwargs)
    if hasattr(style_hints, "colorScheme"):
        return style_hints
    return _CompatStyleHintsProxy(style_hints)


QGuiApplication.styleHints = staticmethod(_compat_style_hints)
