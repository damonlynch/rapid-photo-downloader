#  SPDX-FileCopyrightText: 2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: GPL-3.0-or-later

from contextlib import suppress
from pathlib import Path


def cosmic_prefer_dark() -> bool:
    """Return true if Cosmic is set to run in dark mode"""

    config = Path().home() / ".config/cosmic/com.system76.CosmicTheme.Mode/v1/is_dark"
    with suppress(FileNotFoundError), open(config) as f:
        return f.read().strip() == "true"
    return False
