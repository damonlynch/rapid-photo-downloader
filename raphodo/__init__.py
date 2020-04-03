# Copyright (C) 2016-2020 Damon Lynch <damonlynch@gmail.com>

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
__copyright__ = "Copyright 2016-2020, Damon Lynch"

from typing import Optional
import os
import gettext
import locale
from xdg import BaseDirectory
import builtins

from PyQt5.QtCore import QSettings


def sample_translation() -> str:
    """
    :return: return the Spanish translation as a sample translation
    """

    mo_file = '{}.mo'.format(i18n_domain)
    return os.path.join('es', 'LC_MESSAGES', mo_file)


def locale_directory() -> Optional[str]:
    """
    Locate locale directory. Prioritizes whatever is newer, comparing the locale
    directory at xdg_data_home and the one in /usr/share/

    If running in a snap, use the snap locale directory.

    :return: the locale directory with the most recent messages for Rapid Photo
    Downloader, if found, else None.
    """

    snap_name = os.getenv('SNAP_NAME', '')
    if snap_name.find('rapid-photo-downloader') >= 0:
        snap_dir = os.getenv('SNAP', '')
        return os.path.join(snap_dir, '/usr/lib/locale')

    sample_lang_path = sample_translation()
    locale_mtime = 0.0
    locale_dir = None

    for path in (BaseDirectory.xdg_data_home, '/usr/share'):
        locale_path = os.path.join(path, 'locale')
        sample_path = os.path.join(locale_path, sample_lang_path)
        if os.path.isfile(sample_path) and os.access(sample_path, os.R_OK):
            if os.path.getmtime(sample_path) > locale_mtime:
                locale_dir = locale_path
    return locale_dir


def no_translation_performed(s: str) -> str:
    """
    We are missing translation mo files. Do nothing but return the string
    """

    return s

# Install translation support
# Users and specify the translation they want in the program preferences
# The default is to use the system default


i18n_domain = 'rapid-photo-downloader'
localedir = locale_directory()

lang = None
lang_installed = False

if localedir is not None and os.path.isfile(os.path.join(localedir, sample_translation())):
    settings = QSettings("Rapid Photo Downloader", "Rapid Photo Downloader")
    settings.beginGroup('Display')
    lang = settings.value('language', '', str)
    settings.endGroup()

    if not lang:
        lang, encoding = locale.getdefaultlocale()

    if lang:
        lang = [lang]

    try:
        lang = gettext.translation(i18n_domain, localedir=localedir, languages=lang)
        lang.install()
        lang_installed = True
    except FileNotFoundError:
        pass

if not lang_installed:
    # Building on what lang.install() does above - but in this case, pretend we are
    # translating files
    builtins.__dict__['_'] = no_translation_performed

