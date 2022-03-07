#!/usr/bin/env python3

# Copyright (C) 2015-2022 Damon Lynch <damonlynch@gmail.com>

# This file is part of Rapid Photo Downloader.
#
# Rapid Photo Downloader is free software: you can redistribute it and/or
# modify
# it under the terms of the GNU General Public License as published by
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

"""
Detect versions of external programs.
Some version checks are also in the module thumbnailextractor
"""

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2015-2022, Damon Lynch"

import re
import subprocess
from typing import Optional

import gi

gi.require_version("GExiv2", "0.10")
from gi.repository import GExiv2


def gexiv2_version() -> str:
    """
    :return: version number of GExiv2
    """
    # GExiv2.get_version() returns an integer XXYYZZ, where XX is the
    # major version, YY is the minor version, and ZZ is the micro version
    v = "{0:06d}".format(GExiv2.get_version())
    return "{}.{}.{}".format(v[0:2], v[2:4], v[4:6]).replace("00", "0")


def exiv2_version() -> Optional[str]:
    """
    :return: version number of exiv2, if available, else None
    """

    # exiv2 outputs a verbose version string, e.g. the first line can be
    # 'exiv2 0.24 001800 (64 bit build)'
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
