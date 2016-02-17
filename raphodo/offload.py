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
import logging

from raphodo.interprocess import DaemonProcess, OffloadData, OffloadResults
from raphodo.proximity import TemporalProximityGroups
from raphodo.viewutils import SortedListItem
from raphodo.constants import (logging_format, logging_date_format)


class OffloadWorker(DaemonProcess):
    def __init__(self) -> None:
        super().__init__('Offload')

    def run(self) -> None:
        logging.basicConfig(format=logging_format,
                    datefmt=logging_date_format,
                    level=self.logging_level)
        while True:
            directive, content = self.receiver.recv_multipart()

            self.check_for_command(directive, content)

            data = pickle.loads(content) # type: OffloadData
            if data.thumbnail_rows:
                groups = TemporalProximityGroups(data.thumbnail_rows, data.thumbnail_types,
                                                 data.proximity_seconds)
                self.content = pickle.dumps(OffloadResults(
                    proximity_groups=groups),
                    pickle.HIGHEST_PROTOCOL)
                self.send_message_to_sink()

if __name__ == '__main__':
    offload = OffloadWorker()
    offload.run()