#  SPDX-FileCopyrightText: 2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: GPL-3.0-or-later

"""
Compatibility layer for Qt.

Use new signals with old versions of Qt6.
"""

from PyQt6.QtCore import QMetaMethod, Qt, pyqtSignal
from PyQt6.QtWidgets import QCheckBox


def build_qt_compat_metaclass(qt_base_class):
    qt_meta = type(qt_base_class)

    class QtCompatMeta(qt_meta):
        def __new__(mcls, name, bases, namespace, **kwargs):
            backports = namespace.get("__qt_signal_backports__", {})

            cls = super().__new__(mcls, name, bases, namespace, **kwargs)

            if not backports:
                return cls

            # Find the first real Qt base class
            qt_base = next((b for b in bases if hasattr(b, "staticMetaObject")), None)

            if qt_base is None:
                return cls

            meta = qt_base.staticMetaObject

            existing_signatures = {
                bytes(meta.method(i).methodSignature()).decode()
                for i in range(meta.methodCount())
                if meta.method(i).methodType() == QMetaMethod.MethodType.Signal
            }

            missing = {
                name: spec
                for name, spec in backports.items()
                if spec["signature"] not in existing_signatures
            }

            if not missing:
                return cls

            # Install missing signals at class level
            for signal_name, spec in missing.items():
                setattr(cls, signal_name, spec["signal"])

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
