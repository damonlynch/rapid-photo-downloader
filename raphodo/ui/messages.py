# SPDX-FileCopyrightText: Copyright 2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from raphodo.constants import DestDisplayStatus
from raphodo.internationalisation.strings import (
    DIR_NO_READ,
    DIR_NOT_EXIST,
    DIR_READ_ONLY,
    NO_SPACE,
)

DIR_PROBLEM_TEXT = {
    DestDisplayStatus.cannot_read: DIR_NO_READ,
    DestDisplayStatus.read_only: DIR_READ_ONLY,
    DestDisplayStatus.does_not_exist: DIR_NOT_EXIST,
    DestDisplayStatus.no_storage_space: NO_SPACE,
}
