# SPDX-FileCopyrightText: Copyright 2015-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Detect versions of external programs.
Some version checks are also in the module thumbnailextractor
"""

import re
import subprocess

import gi

gi.require_version("GExiv2", "0.10")
from gi.repository import GExiv2  # noqa: E402


def gexiv2_version() -> str:
    """
    :return: version number of GExiv2
    """
    # GExiv2.get_version() returns an integer XXYYZZ, where XX is the
    # major version, YY is the minor version, and ZZ is the micro version
    v = f"{GExiv2.get_version():06d}"
    return f"{v[0:2]}.{v[2:4]}.{v[4:6]}".replace("00", "0")


def exiv2_version() -> str | None:
    """
    :return: version number of exiv2, if available, else None
    """

    # exiv2 outputs a verbose version string, e.g., the first line can be
    # 'exiv2 0.24 001800 (64-bit build)'
    # followed by the copyright & GPL
    try:
        v = subprocess.check_output(["exiv2", "-V", "-v"]).strip().decode()
        v = re.search("exiv2=([0-9.]+)\n", v)
        if v:
            return v.group(1)
        else:
            return None
    except (OSError, subprocess.CalledProcessError):
        return None


def exiftool_version_info() -> str:
    """
    returns the version of Exiftool being used

    :return version number, or None if Exiftool cannot be found
    """

    try:
        return subprocess.check_output(["exiftool", "-ver"]).strip().decode()
    except (OSError, subprocess.CalledProcessError):
        return ""


EXIFTOOL_VERSION = exiftool_version_info()
