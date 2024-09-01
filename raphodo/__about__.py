# SPDX-FileCopyrightText: Copyright 2016-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

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

__version__ = "0.9.37a6"

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
    f"{__copyright__}. {__licence_full__}\n\n"
    ""
)
