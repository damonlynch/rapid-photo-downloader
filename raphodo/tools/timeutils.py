# SPDX-FileCopyrightText: Copyright 2015-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""A few utility functions relating to time conversion and internationalization"""

import locale
import re
from datetime import datetime

from arrow.arrow import Arrow


def twelve_hour_clock() -> bool:
    """
    Determine if a twelve-hour clock is being used in the current locale

    :return: True if so, else False
    """

    return bool(locale.nl_langinfo(locale.T_FMT_AMPM))


replacement_fmts = [
    (".%S", ""),
    (":%S", ""),
    (",%S", ""),
    (":%OS", ""),
    ("ཀསར་ཆ%S", ""),
    (" %S초", ""),
    ("%S秒", ""),
    ("%r", "%I:%M"),
    ("%t", "%H:%M"),
    ("%T", "%H:%M"),
]

dt_am = datetime(2015, 11, 3, 1)
dt_pm = datetime(2015, 11, 3, 13)


def locale_time(t: datetime) -> str:
    """
    Attempt to localize the time without displaying seconds

    locale.nl_langinfo(locale.T_FMT) for this locale is %r, %T or %t,
    then just return the time, dropping the ':dd' in 'dd:dd:dd' if
    that's the format the time is in.

    Otherwise, then use the approach here:
    Adapted from http://stackoverflow.com/questions/2507726/how-to-display
    -locale-sensitive-time-format-without-seconds-in-python
    :param t: time in datetime format
    :return: time in format like "12:08 AM", or locale equivalent
    """

    t_fmt = locale.nl_langinfo(locale.T_FMT_AMPM) or locale.nl_langinfo(locale.T_FMT)

    if t_fmt in ("%r", "%t", "%T"):
        s = t.strftime("%X").strip()
        return re.sub(r"(\d\d):(\d\d):\d\d", r"\1:\2", s)

    for fmt in replacement_fmts:
        new_t_fmt = t_fmt.replace(*fmt)
        if new_t_fmt != t_fmt:
            return t.strftime(new_t_fmt)

    return t.strftime(t_fmt)


def strip_zero(t: str, strip_zero) -> str:
    if not strip_zero:
        return t.strip()
    return t.lstrip("0").strip()


def strip_am(t: str) -> str:
    if not locale.nl_langinfo(locale.T_FMT_AMPM):
        return t.strip()
    return t.replace(dt_am.strftime("%p"), "").strip()


def strip_pm(t: str) -> str:
    if not locale.nl_langinfo(locale.T_FMT_AMPM):
        return t.strip()
    return t.replace(dt_pm.strftime("%p"), "").strip()


def make_long_date_format(arrowtime: Arrow) -> str:
    # Translators: for example, Nov 3 or Dec 31
    # Translators: %(variable)s represents Python code, not a plural of the term
    # variable. You must keep the %(variable)s untranslated, or the program will
    # crash.
    long_format = _("%(month)s %(numeric_day)s") % {
        "month": arrowtime.datetime.strftime("%b"),
        "numeric_day": arrowtime.format("D"),
    }
    # Translators: for example, Nov 15 2015
    # Translators: %(variable)s represents Python code, not a plural of the term
    # variable. You must keep the %(variable)s untranslated, or the program will
    # crash.
    return _("%(date)s %(year)s") % dict(date=long_format, year=arrowtime.year)
