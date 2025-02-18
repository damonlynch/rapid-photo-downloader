# SPDX-FileCopyrightText: Copyright 2007-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

import locale

try:
    from PyQt5.QtCore import QSettings

    have_pyqt = True
except ImportError:
    have_pyqt = False


def make_internationalized_list(items: list[str]) -> str:
    r"""
    Makes a string of items conforming to i18n

    >>> print(make_internationalized_list([]))
    <BLANKLINE>
    >>> print(make_internationalized_list(['one']))
    one
    >>> print(make_internationalized_list(['one', 'two']))
    one and two
    >>> print(make_internationalized_list(['one', 'two', 'three']))
    one, two and three
    >>> print(make_internationalized_list(['one', 'two', 'three', 'four']))
    one, two, three and four

    Loosely follows the guideline here:
    http://cldr.unicode.org/translation/lists

    :param items: the list of items to make a string out of
    :return: internationalized string
    """

    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        # Translators: two things in a list e.g. "device1 and device2"
        # Translators: %(variable)s represents Python code, not a plural of the term
        # variable. You must keep the %(variable)s untranslated, or the program will
        # crash.
        return _("%(first_item)s and %(last_item)s") % dict(
            first_item=items[0], last_item=items[1]
        )
    if len(items) > 2:
        s = items[0]
        for item in items[1:-1]:
            # Translators: the middle of a list of things,
            # e.g, 'camera, memory card'
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            s = _("%(first_items)s, %(last_items)s") % dict(
                first_items=s, last_items=item
            )
        # Translators: the end of a list of things,
        # e.g, 'camera, memory card and external drive'
        # where 'camera, memory card' are represented by start_items in the code
        # and 'external drive' is represented by last_item in the code
        # Translators: %(variable)s represents Python code, not a plural of the term
        # variable. You must keep the %(variable)s untranslated, or the program will
        # crash.
        s = _("%(start_items)s and %(last_item)s") % dict(
            start_items=s, last_item=items[-1]
        )
        return s
    return ""


def thousands(i: int) -> str:
    """
    Add a thousands separator (or its locale equivalent) to an
    integer. Assumes the module level locale setting has already been
    set.
    :param i: the integer e.g., 1000
    :return: string with seperators e.g. '1,000'
    """
    try:
        return locale.format_string("%d", i, grouping=True)
    except TypeError:
        return str(i)

def current_locale() -> str:
    assert have_pyqt
    settings = QSettings("Rapid Photo Downloader", "Rapid Photo Downloader")
    settings.beginGroup("Display")
    lang = settings.value("language", "", str)
    settings.endGroup()
    if lang:
        return lang
    lang, encoding = locale.getdefaultlocale()
    return lang
