# SPDX-FileCopyrightText: Copyright 2016-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Initialize gettext translations.
"""

import builtins
import gettext
import locale
import os
from pathlib import Path

from PyQt5.QtCore import QSettings


def sample_translation() -> str:
    """
    :return: return the Spanish translation as a sample translation
    """

    mo_file = f"{i18n_domain}.mo"
    return os.path.join("es", "LC_MESSAGES", mo_file)


def no_translation_performed(s: str) -> str:
    """
    We are missing translation mo files. Do nothing but return the string
    """

    return s


# Install translation support
# Users and specify the translation they want in the program preferences
# The default is to use the system default


i18n_domain = "rapid-photo-downloader"
localedir = Path(__file__).parent / "locale"

lang = None
lang_installed = False

if localedir is not None and os.path.isfile(
    os.path.join(localedir, sample_translation())
):
    settings = QSettings("Rapid Photo Downloader", "Rapid Photo Downloader")
    settings.beginGroup("Display")
    lang = settings.value("language", "", str)
    settings.endGroup()

    if not lang:
        lang, encoding = locale.getdefaultlocale()

    try:
        gnulang = gettext.translation(
            i18n_domain, localedir=localedir, languages=[lang]
        )
        gnulang.install()
        lang_installed = True
    except FileNotFoundError:
        pass
    except Exception:
        pass

if not lang_installed:
    # Building on what lang.install() does above - but in this case, pretend we are
    # translating files
    builtins.__dict__["_"] = no_translation_performed
