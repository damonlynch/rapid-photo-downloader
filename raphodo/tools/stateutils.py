# SPDX-FileCopyrightText: Copyright 2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from enum import Flag
from typing import Type


def chain_flags(flag: Type[Flag], start: int = 0, stop: int = 0):
    assert len(flag) > 1
    flag_list = list(flag)
    d = {}
    if stop == 0:
        stop = len(flag_list)
    return {flag_list[i]: flag_list[i + 1] for i in range(start, stop - 1)}
