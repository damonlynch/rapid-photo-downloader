# Copyright (C) 2016-2024 Damon Lynch <damonlynch@gmail.com>

# This file is part of Rapid Photo Downloader.
#
# Rapid Photo Downloader is free software: you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published by
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

# Directly modelled on Donald Stufft's readme_renderer code:
# https://github.com/pypa/readme_renderer/blob/master/readme_renderer/__about__.py

__all__ = [
    "__title__",
    "__summary__",
    "__uri__",
    "__version__",
    "__author__",
    "__email__",
    "__license__",
    "__copyright__",
]

__title__ = "rapid-photo-downloader"
__summary__ = (
    "Downloads, renames and backs up photos and videos from cameras, phones, "
    "memory cards and other devices."
)
__uri__ = "https://damonlynch.net/rapid"

__version__ = "0.9.37a1"

__author__ = "Damon Lynch"
__email__ = "damonlynch@gmail.com"

__license__ = "GPL 3+"
__licence_full__ = (
    "License GPLv3+: GNU GPL version 3 or later https://gnu.org/licenses/gpl.html.\n"
    "This is free software: you are free to change and redistribute it. "
    "There is NO WARRANTY, to the extent permitted by law."
)
__copyright__ = f"Copyright 2007-2024 {__author__}"

__help_epilog__ = (
    "If the environment variable RPD_SCAN_DEBUG is set to any value, the program's "
    "scan operation will output voluminous debug information to stdout.\n\n"

    "If the environment variable RPD_DEVEL_DEFAULTS is set to any value, the "
    "program's default preferences will be set to those of a development "
    "environment.\n\n"
    
    "Report bugs to https://bugs.rapidphotodownloader.com/\n\n"
    
    f"Written by {__author__} {__email__}.\n\n"
    
    f"{__copyright__}. {__licence_full__}\n\n"
    ""
)
