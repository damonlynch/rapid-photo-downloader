#  SPDX-FileCopyrightText: 2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: GPL-3.0-or-later

import shlex
from subprocess import DEVNULL, CalledProcessError, check_output

import gi

try:
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio

    have_gio = True
except Exception:
    have_gio = False


def get_gnome_setting_subprocess(setting: str) -> str:
    cmd = f"gsettings get org.gnome.desktop.interface {setting}"
    shlex.split(cmd)
    try:
        return (
            check_output(shlex.split(cmd), text=True, stderr=DEVNULL)
            .strip()
            .strip("'")
            .lower()
        )
    except CalledProcessError:
        return ""


def get_gnome_setting(setting: str) -> str:
    """Return the Gnome setting from gsettings as a string"""
    if not have_gio:
        raise Exception("Gnome scheme not available")

    schema_id = "org.gnome.desktop.interface"

    # Note: This will crash (segfault) if the schema is not installed on the system
    settings = Gio.Settings.new(schema_id)

    return settings.get_string(setting)
