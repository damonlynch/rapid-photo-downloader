#  SPDX-FileCopyrightText: 2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: GPL-3.0-or-later

import logging
import re
import shutil
import subprocess
from pathlib import Path


def udisksd_path_systemd() -> str:
    """
    Return the udisksd executable path from systemd unit metadata.
    """

    try:
        result = subprocess.run(
            [
                "systemctl",
                "show",
                "-P",
                "ExecStart",
                "udisks2.service",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        value = result.stdout.strip()

        if not value:
            return ""

        # Example:
        # { path=/usr/libexec/udisks2/udisksd ; argv[]=/usr/libexec/udisks2/udisksd ... ; ... }

        marker = "path="
        start = value.find(marker)

        if start == -1:
            return ""

        start += len(marker)

        end = value.find(" ", start)
        if end == -1:
            end = value.find(";", start)

        return value[start:end]

    except Exception:
        return ""


def detect_run_media_dir() -> bool:
    """
    Heuristically detect whether UDisks2 defaults mounting external devices to:
      /run/media/$USER
    or
      /media/$USER
    """

    daemon = udisksd_path_systemd()
    if not daemon:
        # Linux distributions without systemd
        for path in (
            "/usr/libexec/udisks2/udisksd",
            "/usr/lib/udisks2/udisksd",
            "/lib/udisks2/udisksd",
        ):
            if Path(path).exists():
                daemon = path
                break

    if not daemon or not Path(daemon).exists():
        raise Exception("UDisks2 daemon not detected")

    logging.debug("UDisks2 daemon detected at %s", daemon)

    data = Path(daemon).read_bytes()
    # Extract printable ASCII path-like substrings
    paths = {
        m.group().decode("ascii", errors="ignore")
        for m in re.finditer(rb"/[A-Za-z0-9._/+:-]+", data)
    }

    has_media = {p for p in paths if p == "/media" or p.startswith("/media/")}

    has_run_media = {
        p for p in paths if p == "/run/media" or p.startswith("/run/media/")
    }

    if has_run_media and has_media:
        raise Exception(
            "UDisks2 media path is ambiguous; both /run/media and /media detected"
        )

    if not (has_media or has_run_media):
        raise Exception("no /media or /run/media path detected")

    return bool(has_run_media)
