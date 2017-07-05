#!/usr/bin/env python3

# Copyright (C) 2011-2017 Damon Lynch <damonlynch@gmail.com>

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
__copyright__ = "Copyright 2011-2017, Damon Lynch"

import pickle
import os
import errno
import hashlib
from datetime import datetime
import shutil
import logging
from typing import Optional, Tuple
from gettext import gettext as _

from raphodo.interprocess import (BackupFileData, BackupResults, BackupArguments,
                          WorkerInPublishPullPipeline)
from raphodo.copyfiles import FileCopy
from raphodo.constants import (FileType, DownloadStatus, BackupStatus)
from raphodo.rpdfile import RPDFile
from raphodo.cache import FdoCacheNormal, FdoCacheLarge

from raphodo.copyfiles import copy_file_metadata
from raphodo.problemnotification import (
    BackingUpProblems, BackupSubfolderCreationProblem, make_href, BackupOverwrittenProblem,
    BackupAlreadyExistsProblem, FileWriteProblem
)
from raphodo.storage import get_uri


class BackupFilesWorker(WorkerInPublishPullPipeline, FileCopy):
    def __init__(self):
        self.problems = BackingUpProblems()
        super().__init__('BackupFiles')

    def update_progress(self, amount_downloaded, total):
        self.amount_downloaded = amount_downloaded
        chunk_downloaded = amount_downloaded - self.bytes_downloaded
        if (chunk_downloaded > self.batch_size_bytes) or (amount_downloaded == total):
            self.bytes_downloaded = amount_downloaded
            self.content= pickle.dumps(BackupResults(
                scan_id=self.scan_id,
                device_id=self.device_id,
                total_downloaded=self.total_downloaded + amount_downloaded,
                chunk_downloaded=chunk_downloaded),
               pickle.HIGHEST_PROTOCOL)
            self.send_message_to_sink()

            # if amount_downloaded == total:
            #     self.bytes_downloaded = 0

    def backup_associate_file(self, dest_dir: str, full_file_name: str) -> None:
        """
        Backs up small files like XMP or THM files
        """

        base_name = os.path.basename(full_file_name)
        full_dest_name = os.path.join(dest_dir, base_name)

        try:
            logging.debug("Backing up additional file %s...", full_dest_name)
            shutil.copyfile(full_file_name, full_dest_name)
            logging.debug("...backing up additional file %s succeeded", full_dest_name)
        except Exception as e:
            logging.error("Backup of %s failed", full_file_name)
            logging.error(str(e))
            uri = get_uri(full_file_name=full_dest_name)
            self.problems.append(FileWriteProblem(name=base_name, uri=uri, exception=e))
        else:
            # ignore any metadata copying errors
            copy_file_metadata(full_file_name, full_dest_name)

    def do_backup(self, data: BackupFileData) -> None:
        rpd_file = data.rpd_file
        backup_succeeded = False
        self.scan_id = rpd_file.scan_id
        self.verify_file = data.verify_file

        mdata_exceptions = None

        if not (data.move_succeeded and data.do_backup):
            backup_full_file_name = ''
        else:
            self.total_reached = False

            if data.path_suffix is None:
                dest_base_dir = self.path
            else:
                dest_base_dir = os.path.join(self.path, data.path_suffix)

            dest_dir = os.path.join(dest_base_dir, rpd_file.download_subfolder)
            backup_full_file_name = os.path.join(dest_dir, rpd_file.download_name)

            if not os.path.isdir(dest_dir):
                # create the subfolders on the backup path
                try:
                    logging.debug("Creating subfolder %s on backup device %s...",
                                  dest_dir, self.device_name)
                    os.makedirs(dest_dir)
                    logging.debug("...backup subfolder created")
                except OSError as inst:
                    # There is a minuscule chance directory may have been
                    # created by another process between the time it
                    # takes to query and the time it takes to create a
                    # new directory. Ignore that error.
                    if inst.errno != errno.EEXIST:
                        logging.error("Failed to create backup subfolder: %s",
                                      rpd_file.download_path)
                        logging.error(inst)

                        self.problems.append(
                            BackupSubfolderCreationProblem(
                                folder=make_href(
                                    name=rpd_file.download_subfolder, uri=get_uri(path=dest_dir)
                                ),
                                exception=inst
                            )
                        )

            backup_already_exists = os.path.exists(backup_full_file_name)

            if backup_already_exists:
                try:
                    modification_time = os.path.getmtime(backup_full_file_name)
                    dt = datetime.fromtimestamp(modification_time)
                    date = dt.strftime("%x")
                    time = dt.strftime("%X")
                except Exception:
                    logging.error("Could not determine the file modification time of %s",
                                  backup_full_file_name)
                    date = time = ''

                source = rpd_file.get_souce_href()
                device = make_href(name=rpd_file.device_display_name, uri=rpd_file.device_uri)

                if data.backup_duplicate_overwrite:
                    self.problems.append(BackupOverwrittenProblem(
                        file_type_capitalized=rpd_file.title_capitalized,
                        file_type=rpd_file.title,
                        name=rpd_file.download_name,
                        uri=get_uri(full_file_name=backup_full_file_name),
                        source=source,
                        device=device,
                        date=date,
                        time=time
                    ))
                    msg = "Overwriting backup file %s" % backup_full_file_name
                else:
                    self.problems.append(BackupAlreadyExistsProblem(
                        file_type_capitalized=rpd_file.title_capitalized,
                        file_type=rpd_file.title,
                        name=rpd_file.download_name,
                        uri=get_uri(full_file_name=backup_full_file_name),
                        source=source,
                        device=device,
                        date=date,
                        time=time
                    ))
                    msg = "Skipping backup of file %s because it already exists" % \
                          backup_full_file_name
                logging.warning(msg)

            if not backup_already_exists or data.backup_duplicate_overwrite:
                logging.debug("Backing up file %s on device %s...",
                              data.download_count, self.device_name)
                source = rpd_file.download_full_file_name
                destination = backup_full_file_name
                backup_succeeded = self.copy_from_filesystem(source, destination, rpd_file)
                if backup_succeeded and self.verify_file:
                    md5 = hashlib.md5(open(backup_full_file_name).read()).hexdigest()
                    if md5 != rpd_file.md5:
                        pass
                if backup_succeeded:
                    logging.debug("...backing up file %s on device %s succeeded",
                                  data.download_count, self.device_name)

                if backup_succeeded:
                    mdata_exceptions = copy_file_metadata(
                        rpd_file.download_full_file_name, backup_full_file_name
                    )
            if not backup_succeeded:
                if rpd_file.status == DownloadStatus.download_failed:
                    rpd_file.status = DownloadStatus.download_and_backup_failed
                else:
                    rpd_file.status = DownloadStatus.backup_problem
            else:
                # backup any THM, audio or XMP files
                if rpd_file.download_thm_full_name:
                    self.backup_associate_file(dest_dir, rpd_file.download_thm_full_name)
                if rpd_file.download_audio_full_name:
                    self.backup_associate_file(dest_dir, rpd_file.download_audio_full_name)
                if rpd_file.download_xmp_full_name:
                    self.backup_associate_file(dest_dir, rpd_file.download_xmp_full_name)
                if rpd_file.download_log_full_name:
                    self.backup_associate_file(dest_dir, rpd_file.download_log_full_name)

        self.total_downloaded += rpd_file.size
        bytes_not_downloaded = rpd_file.size - self.amount_downloaded
        if bytes_not_downloaded and data.do_backup:
            self.content = pickle.dumps(
                BackupResults(
                    scan_id=self.scan_id, device_id=self.device_id,
                    total_downloaded=self.total_downloaded, chunk_downloaded=bytes_not_downloaded
                ),
                pickle.HIGHEST_PROTOCOL
            )
            self.send_message_to_sink()

        self.content = pickle.dumps(
            BackupResults(
                scan_id=self.scan_id, device_id=self.device_id, backup_succeeded=backup_succeeded,
                do_backup=data.do_backup, rpd_file=rpd_file,
                backup_full_file_name=backup_full_file_name, mdata_exceptions=mdata_exceptions
            ),
            pickle.HIGHEST_PROTOCOL
        )
        self.send_message_to_sink()

    def reset_problems(self) -> None:
        self.problems = BackingUpProblems(
            name=self.device_name, uri=self.uri
        )

    def send_problems(self) -> None:
        if self.problems:
            self.content = pickle.dumps(
                BackupResults(
                    scan_id=self.scan_id, device_id=self.device_id, problems=self.problems
                ),
                pickle.HIGHEST_PROTOCOL
            )
            self.send_message_to_sink()
            self.reset_problems()

    def cleanup_pre_stop(self):
        self.send_problems()

    def do_work(self):

        backup_arguments = pickle.loads(self.content)
        self.path = backup_arguments.path
        self.device_name = backup_arguments.device_name
        self.uri = get_uri(path=self.path)
        self.fdo_cache_normal = FdoCacheNormal()
        self.fdo_cache_large = FdoCacheLarge()

        while True:
            worker_id, directive, content = self.receiver.recv_multipart()
            self.device_id = int(worker_id)

            self.check_for_command(directive, content)

            data = pickle.loads(content) # type: BackupFileData
            if data.message == BackupStatus.backup_started:
                self.reset_problems()
            elif data.message == BackupStatus.backup_completed:
                self.send_problems()
            else:
                self.amount_downloaded = 0
                self.init_copy_progress()

                self.do_backup(data=data)


if __name__ == "__main__":
    backup = BackupFilesWorker()