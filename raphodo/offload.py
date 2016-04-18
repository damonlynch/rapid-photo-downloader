#!/usr/bin/env python3

# Copyright (C) 2015-2016 Damon Lynch <damonlynch@gmail.com>

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


__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2015-2016, Damon Lynch"

import pickle
import sys
import logging

from PyQt5.QtGui import QGuiApplication
from raphodo.interprocess import (DaemonProcess, OffloadData, OffloadResults, DownloadDestination)
from raphodo.proximity import TemporalProximityGroups
from raphodo.viewutils import ThumbnailDataForProximity
from raphodo.folderspreview import FoldersPreview


class OffloadWorker(DaemonProcess):
    def __init__(self) -> None:
        super().__init__('Offload')

    def run(self) -> None:
        try:
            folders_preview = FoldersPreview()
            while True:
                directive, content = self.receiver.recv_multipart()

                self.check_for_command(directive, content)

                data = pickle.loads(content) # type: OffloadData
                if data.thumbnail_rows:
                    groups = TemporalProximityGroups(thumbnail_rows=data.thumbnail_rows,
                                                     temporal_span=data.proximity_seconds)
                    self.content = pickle.dumps(OffloadResults(
                        proximity_groups=groups),
                        pickle.HIGHEST_PROTOCOL)
                    self.send_message_to_sink()
                elif data.destination:
                    folders_preview.process_rpd_files(rpd_files=data.rpd_files,
                                                      destination=data.destination,
                                                      strip_characters=data.strip_characters)
                    if folders_preview.dirty:
                        folders_preview.dirty = False
                        self.content = pickle.dumps(OffloadResults(
                            folders_preview=folders_preview),
                            pickle.HIGHEST_PROTOCOL)
                        self.send_message_to_sink()
                else:
                    assert data.scan_id is not None
                    folders_preview.clean_generated_folders_for_scan_id(data.scan_id)
                    folders_preview.dirty = False
                    self.content = pickle.dumps(OffloadResults(
                        folders_preview=folders_preview),
                        pickle.HIGHEST_PROTOCOL)
                    self.send_message_to_sink()

        except Exception as e:
            logging.error("An unhandled exception occurred while processing offloaded tasks")
            logging.exception("Traceback:")

if __name__ == '__main__':
    # Must initialize QGuiApplication to use QFont() and QFontMetrics
    app = QGuiApplication(sys.argv)

    offload = OffloadWorker()
    offload.run()