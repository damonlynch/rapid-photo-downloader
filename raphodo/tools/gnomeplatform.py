#  SPDX-FileCopyrightText: 2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: GPL-3.0-or-later

import gi

try:
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio

    have_gio = True
except Exception:
    have_gio = False


def get_gnome_color_scheme() -> str:
    """Return the Gnome color scheme from gsettings as a string"""
    if not have_gio:
        raise Exception("Gnome color scheme not available")

    schema_id = "org.gnome.desktop.interface"

    # Note: This will crash (segfault) if the schema is not installed on the system
    settings = Gio.Settings.new(schema_id)

    color_scheme = settings.get_string("color-scheme")
    return color_scheme


def gnome_prefer_dark() -> bool:
    """Return true if Gnome is set to run in dark mode"""
    try:
        return get_gnome_color_scheme() == "prefer-dark"
    except Exception:
        return False
