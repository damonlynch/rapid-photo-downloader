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

"""
Generates thumbnails for files that have already been downloaded, and
writes out FDO thumbnails for files of the type where that makes sense
e.g. RAW files

See cache.py for definitions of various caches used by Rapid Photo Downloader.

Runs as a single instance daemon process, i.e. for the lifetime of the program.
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2015-2016, Damon Lynch"

import logging
import pickle
import sys
import os
from typing import Set, Dict
import locale
# Use the default locale as defined by the LANG variable
locale.setlocale(locale.LC_ALL, '')

import zmq

from raphodo.constants import (
    FileType, ThumbnailSize, ThumbnailCacheStatus, ThumbnailCacheDiskStatus, ExtractionTask,
    ExtractionProcessing, ThumbnailCacheOrigin
)
from raphodo.interprocess import (
    ThumbnailDaemonData, GenerateThumbnailsResults, DaemonProcess, ThumbnailExtractorArgument
)
from raphodo.rpdfile import RPDFile
from raphodo.thumbnailpara import GetThumbnailFromCache, preprocess_thumbnail_from_disk
from raphodo.cache import FdoCacheLarge, FdoCacheNormal


class DameonThumbnailWorker(DaemonProcess):
    """
    Generates thumbnails for files that have already been downloaded, and
    writes out FDO thumbnails for files of the type where that makes sense
    e.g. RAW files
    """

    def __init__(self):
        super().__init__('Thumbnail Daemon')

    def run(self):
        """
        Set up process and then process thumbnail requests one by one
        """

        # Always set use_thumbnail_cache to True, because this is a daemon
        # process that runs for the lifetime of the program. User can
        # change the program preferences.
        # Whether to actually use it will be determined at the time the
        # thumbnail is sought, using the user's preference at that moment.
        thumbnail_caches = GetThumbnailFromCache(use_thumbnail_cache=True)

        self.frontend = self.context.socket(zmq.PUSH)

        directive, content = self.receiver.recv_multipart()

        self.check_for_command(directive, content)

        data = pickle.loads(content) # type: ThumbnailDaemonData
        assert data.frontend_port is not None
        self.frontend.connect("tcp://localhost:{}".format(data.frontend_port))

        # handle freedesktop.org cache files directly
        fdo_cache_large = FdoCacheLarge()
        fdo_cache_normal = FdoCacheNormal()

        while True:
            directive, content = self.receiver.recv_multipart()

            self.check_for_command(directive, content)

            data = pickle.loads(content) # type: ThumbnailDaemonData
            rpd_file = data.rpd_file
            if data.backup_full_file_names is not None:
                # File has been backed up, and an extractor has already generated a FDO thumbnail
                # for it.
                # Copy and modify the existing FDO thumbnail

                # MD5 name of the existing FDO thumbnail
                md5_name = data.fdo_name
                assert md5_name

                for backup_full_file_name in data.backup_full_file_names:

                    # Check to see if existing thumbnail in FDO cache can be
                    # modified and renamed to reflect new URI
                    try:
                        mtime = os.path.getmtime(backup_full_file_name)
                    except OSError:
                        logging.debug("Backup file does not exist: %s", backup_full_file_name)
                    else:
                        logging.debug("Copying and modifying existing FDO 128 thumbnail for %s",
                                      backup_full_file_name)
                        fdo_cache_normal.modify_existing_thumbnail_and_save_copy(
                            existing_cache_thumbnail=md5_name,
                            full_file_name=backup_full_file_name,
                            size=rpd_file.size,
                            modification_time=mtime,
                            error_on_missing_thumbnail=True)

                        logging.debug("Copying and modifying existing FDO 256 thumbnail for %s",
                                      backup_full_file_name)
                        fdo_cache_large.modify_existing_thumbnail_and_save_copy(
                            existing_cache_thumbnail=md5_name,
                            full_file_name=backup_full_file_name,
                            size=rpd_file.size,
                            modification_time=mtime,
                            error_on_missing_thumbnail=False)
            else:
                # file has just been downloaded and renamed
                rpd_file.modified_via_daemon_process = True
                try:

                    # Check the download source to see if it's in the caches, not the file
                    # we've just downloaded

                    use_thumbnail_cache = (data.use_thumbnail_cache and not
                        (data.write_fdo_thumbnail and rpd_file.should_write_fdo()))
                    cache_search = thumbnail_caches.get_from_cache(
                        rpd_file=rpd_file,
                        use_thumbnail_cache=use_thumbnail_cache)
                    task, thumbnail_bytes, full_file_name_to_work_on, origin = cache_search
                    processing = set()  # type: Set[ExtractionProcessing]

                    if task == ExtractionTask.undetermined:
                        # Thumbnail was not found in any cache: extract it

                        task = preprocess_thumbnail_from_disk(rpd_file=rpd_file,
                                                              processing=processing)
                        if task != ExtractionTask.bypass:
                            if rpd_file.thm_full_name is not None:
                                full_file_name_to_work_on = rpd_file.download_thm_full_name
                            else:
                                full_file_name_to_work_on = rpd_file.download_full_file_name

                    if task == ExtractionTask.bypass:
                        self.content = pickle.dumps(GenerateThumbnailsResults(
                            rpd_file=rpd_file, thumbnail_bytes=thumbnail_bytes),
                            pickle.HIGHEST_PROTOCOL)
                        self.send_message_to_sink()

                    elif task != ExtractionTask.undetermined:
                        # Send data to load balancer, which will send to one of its
                        # workers

                        self.content = pickle.dumps(ThumbnailExtractorArgument(
                            rpd_file=rpd_file,
                            task=task,
                            processing=processing,
                            full_file_name_to_work_on=full_file_name_to_work_on,
                            secondary_full_file_name='',
                            exif_buffer=None,
                            thumbnail_bytes=thumbnail_bytes,
                            use_thumbnail_cache=data.use_thumbnail_cache,
                            file_to_work_on_is_temporary=False,
                            write_fdo_thumbnail=data.write_fdo_thumbnail,
                            send_thumb_to_main=True),
                            pickle.HIGHEST_PROTOCOL)
                        self.frontend.send_multipart([b'data', self.content])
                except SystemExit as e:
                    sys.exit(e)
                except:
                    logging.error("Exception working on file %s", rpd_file.full_file_name)
                    logging.exception("Traceback:")

if __name__ == '__main__':
    generate_thumbnails = DameonThumbnailWorker()
    generate_thumbnails.run()