#!/usr/bin/python3
__author__ = 'Damon Lynch'
# Copyright (C) 2015 Damon Lynch <damonlynch@gmail.com>

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

import argparse
import sys
import logging
import pickle
import os

import zmq


from interprocess import (LoadBalancerWorker, ThumbnailExtractorArgument,
                          GenerateThumbnailsParaResults)

class ThumbnailExtractor(LoadBalancerWorker):
    def __init__(self):
        super().__init__('Thumbnail Extractor')

    def do_work(self):
        while True:
            directive, content = self.requester.recv_multipart()
            self.check_for_command(directive, content)
            #
            data = pickle.loads(content) # type: ThumbnailExtractorArgument

            print("{}: {}".format(self.requester.identity.decode(), data.rpd_file.name))


            self.sender.send_multipart([b'0', b'data',
                                        pickle.dumps(GenerateThumbnailsParaResults(data.rpd_file),
                                          pickle.HIGHEST_PROTOCOL)])
            self.requester.send_multipart([b'', b'', b'OK'])



if __name__ == "__main__":
    thumbnail_extractor = ThumbnailExtractor()