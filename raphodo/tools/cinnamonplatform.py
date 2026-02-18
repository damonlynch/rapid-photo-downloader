#  SPDX-FileCopyrightText: 2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: GPL-3.0-or-later


from raphodo.tools.platformtools import get_gnome_setting, get_gnome_setting_subprocess


def cinnamon_prefer_dark() -> bool:
    """Return true if Gnome is set to run in dark mode"""
    try:
        return "dark" in get_gnome_setting(setting="gtk-theme").lower()
    except Exception:
        return False


def cinnamon_accent_color() -> str:
    """Return Cinnamon accent color from gtk-theme"""
    return get_gnome_setting_subprocess("gtk-theme")


if __name__ == "__main__":
    print(cinnamon_prefer_dark())
    print(cinnamon_accent_color())
