#!/usr/bin/env python3

# Copyright (C) 2015-2021 Damon Lynch <damonlynch@gmail.com>

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


__author__ = "Damon Lynch"
__copyright__ = "Copyright 2015-2021, Damon Lynch"

import pickle
import sys
import logging
import locale

try:
    # Use the default locale as defined by the LANG variable
    locale.setlocale(locale.LC_ALL, "")
except locale.Error:
    pass

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

                data = pickle.loads(content)  # type: OffloadData
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
            sys.exit(e)


if __name__ == "__main__":
    # Must initialize QGuiApplication to use QFont() and QFontMetrics
    app = QGuiApplication(sys.argv)

    offload = OffloadWorker()
    offload.run()
