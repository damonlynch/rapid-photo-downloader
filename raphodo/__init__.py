# Copyright (C) 2016 Damon Lynch <damonlynch@gmail.com>

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

"""
Initialize gettext translations.
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2016, Damon Lynch"

from typing import Optional
import os
import gettext
from xdg import BaseDirectory


def locale_directory() -> Optional[str]:
    """
    Locate locale directory. Prioritizes whatever is newer, comparing the locale
    directory at xdg_data_home and the one in /usr/share/

    :return: the locale directory with the most recent messages for Rapid Photo
    Downloader, if found, else None.
    """

    mo_file = '{}.mo'.format(i18n_domain)
    # Test the Spanish file
    sample_lang_path = os.path.join('es', 'LC_MESSAGES', mo_file)
    locale_mtime = 0.0
    locale_dir = None

    for path in (BaseDirectory.xdg_data_home, '/usr/share'):
        locale_path = os.path.join(path, 'locale')
        sample_path = os.path.join(locale_path, sample_lang_path)
        if os.path.isfile(sample_path) and os.access(sample_path, os.R_OK):
            if os.path.getmtime(sample_path) > locale_mtime:
                locale_dir = locale_path
    return locale_dir

i18n_domain = 'rapid-photo-downloader'
localedir = locale_directory()

gettext.bindtextdomain(i18n_domain, localedir=localedir)
gettext.textdomain(i18n_domain)
