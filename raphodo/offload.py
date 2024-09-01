# SPDX-FileCopyrightText: Copyright 2015-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

import contextlib
import locale
import logging
import pickle
import sys

with contextlib.suppress(locale.Error):
    # Use the default locale as defined by the LANG variable
    locale.setlocale(locale.LC_ALL, "")

from PyQt5.QtGui import QGuiApplication

from raphodo.interprocess import (
    DaemonProcess,
    OffloadData,
    OffloadResults,
)
from raphodo.proximity import TemporalProximityGroups


class OffloadWorker(DaemonProcess):
    def __init__(self) -> None:
        super().__init__("Offload")

    def run(self) -> None:
        try:
            while True:
                directive, content = self.receiver.recv_multipart()

                self.check_for_command(directive, content)

                data: OffloadData = pickle.loads(content)
                if data.thumbnail_rows:
                    groups = TemporalProximityGroups(
                        thumbnail_rows=data.thumbnail_rows,
                        temporal_span=data.proximity_seconds,
                    )
                    self.content = pickle.dumps(
                        OffloadResults(proximity_groups=groups), pickle.HIGHEST_PROTOCOL
                    )
                    self.send_message_to_sink()
                else:
                    assert data.folders_preview
                    assert data.rpd_files
                    data.folders_preview.generate_subfolders(
                        rpd_files=data.rpd_files, strip_characters=data.strip_characters
                    )
                    self.content = pickle.dumps(
                        OffloadResults(folders_preview=data.folders_preview),
                        pickle.HIGHEST_PROTOCOL,
                    )
                    self.send_message_to_sink()

        except Exception:
            logging.error(
                "An unhandled exception occurred while processing offloaded tasks"
            )
            logging.exception("Traceback:")
        except SystemExit as e:
            sys.exit(e.code)


if __name__ == "__main__":
    # Must initialize QGuiApplication to use QFont() and QFontMetrics
    app = QGuiApplication(sys.argv)

    offload = OffloadWorker()
    offload.run()
