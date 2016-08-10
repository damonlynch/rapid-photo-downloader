#!/usr/bin/env python3

# Copyright (C) 2011-2016 Damon Lynch <damonlynch@gmail.com>

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
__copyright__ = "Copyright 2011-2016, Damon Lynch"

import pickle
import tempfile
import os
import errno
import hashlib
import sys

import shutil
import io

import logging
from gettext import gettext as _

from raphodo.interprocess import (BackupFileData, BackupResults, BackupArguments,
                          WorkerInPublishPullPipeline)
from raphodo.copyfiles import FileCopy
from raphodo.constants import (FileType, DownloadStatus)
from raphodo.rpdfile import RPDFile
from raphodo.cache import FdoCacheNormal, FdoCacheLarge

import raphodo.problemnotification as pn
from raphodo.copyfiles import copy_file_metadata


class BackupFilesWorker(WorkerInPublishPullPipeline, FileCopy):
    def __init__(self):
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

            if amount_downloaded == total:
                self.bytes_downloaded = 0

    def copying_file_error(self, rpd_file: RPDFile, destination:str, inst) -> None:
        logging.error("Backup of %s failed", destination)
        msg = "%s %s" % (inst.errno, inst.strerror)
        rpd_file.add_problem(None, pn.BACKUP_ERROR, self.device_name)
        rpd_file.add_extra_detail('%s%s' % (pn.BACKUP_ERROR,
                                            self.device_name), msg)
        rpd_file.error_title = _('Backing up error')
        rpd_file.error_msg = \
                _("Source: %(source)s\nDestination: %(destination)s") % dict(
                 source=rpd_file.download_full_file_name,
                 destination=destination) + "\n" + _("Error: %(inst)s") % dict(inst=msg)
        logging.error("%s:\n%s", rpd_file.error_title, rpd_file.error_msg)

    def create_subdir_error(self, dest_dir: str,
                            inst,
                            rpd_file: RPDFile,
                            backup_full_file_name: str) -> None:
        logging.error("Failed to create backup subfolder: %s", dest_dir)
        msg = "%s %s" % (inst.errno, inst.strerror)
        logging.error(msg)
        rpd_file.add_problem(None,
             pn.BACKUP_DIRECTORY_CREATION,
             self.device_name)
        rpd_file.add_extra_detail('%s%s' % (pn.BACKUP_DIRECTORY_CREATION, self.device_name), msg)
        rpd_file.error_title = _('Backing up error')
        rpd_file.error_msg = \
             _("Destination directory could not be "
               "created: %(directory)s\n")  % dict(directory=dest_dir) + \
             _("Source: %(source)s\nDestination: %(destination)s")  % dict(
               source=rpd_file.download_full_file_name,
               destination=backup_full_file_name) + \
             "\n" + _("Error: %(inst)s") % dict(inst=msg)

    def backup_associate_file(self, dest_dir: str, full_file_name: str) -> None:
        """Backs up small files like XMP or THM files"""
        dest_name = os.path.join(dest_dir, os.path.split(full_file_name)[1])

        try:
            logging.debug("Backing up additional file %s...", dest_name)
            shutil.copyfile(full_file_name, dest_name)
            logging.debug("...backing up additional file %s succeeded", dest_name)
        except:
            logging.error("Backup of %s failed", full_file_name)

        copy_file_metadata(full_file_name, dest_name)

    def do_work(self):

        backup_arguments = pickle.loads(self.content)
        self.path = backup_arguments.path
        self.device_name = backup_arguments.device_name
        self.fdo_cache_normal = FdoCacheNormal()
        self.fdo_cache_large = FdoCacheLarge()

        while True:
            self.amount_downloaded = 0
            worker_id, directive, content = self.receiver.recv_multipart()
            self.device_id = int(worker_id)

            self.check_for_command(directive, content)

            data = pickle.loads(content) # type: BackupFileData
            rpd_file = data.rpd_file
            backup_succeeded = False
            self.scan_id = rpd_file.scan_id
            self.verify_file = data.verify_file

            if data.move_succeeded and data.do_backup:
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
                    except IOError as inst:
                        # There is a miniscule chance directory may have been
                        # created by another process between the time it
                        # takes to query and the time it takes to create a
                        # new directory. Ignore that error.
                        if inst.errno != errno.EEXIST:
                            self.create_subdir_error(dest_dir, inst,rpd_file, backup_full_file_name)

                backup_already_exists = os.path.exists(backup_full_file_name)
                if backup_already_exists:
                    if data.backup_duplicate_overwrite:
                        rpd_file.add_problem(None,
                                             pn.BACKUP_EXISTS_OVERWRITTEN,
                                             self.device_name)
                        msg = _("Backup %(file_type)s overwritten") % {
                            'file_type': rpd_file.title}
                    else:
                        rpd_file.add_problem(None, pn.BACKUP_EXISTS, self.device_name)
                        msg = _("%(file_type)s not backed up") % {
                            'file_type': rpd_file.title_capitalized}

                    rpd_file.error_title = _(
                        "Backup of %(file_type)s already exists") % {
                                               'file_type': rpd_file.title}
                    rpd_file.error_msg = \
                        _("Source: %(source)s\nDestination: %(destination)s") % \
                        {'source': rpd_file.download_full_file_name,
                         'destination': backup_full_file_name} + "\n" + msg

                if backup_already_exists and not data.backup_duplicate_overwrite:
                    logging.warning(msg)
                else:
                    logging.debug("Backing up file %s on device %s...",
                                    data.download_count, self.device_name)
                    source = rpd_file.download_full_file_name
                    destination = backup_full_file_name
                    backup_succeeded = self.copy_from_filesystem(source, destination, rpd_file)
                    if backup_succeeded and self.verify_file:
                        md5 = hashlib.md5(open(backup_full_file_name).read()).hexdigest()
                        if md5 != rpd_file.md5:
                            backup_succeeded = False
                            logging.critical("%s file verification FAILED", rpd_file.name)
                            logging.critical("The %s did not back up correctly!", rpd_file.title)
                            rpd_file.add_problem(None,
                                                 pn.BACKUP_VERIFICATION_FAILED,
                                                 self.device_name)
                            rpd_file.error_title = rpd_file.problem.get_title()
                            rpd_file.error_msg = _("%(problem)s\nFile: %("
                                                   "file)s")  % {
                                'problem': rpd_file.problem.get_problems(),
                                'file': rpd_file.download_full_file_name}
                    if backup_succeeded:
                        logging.debug("...backing up file %s on device %s succeeded",
                                      data.download_count, self.device_name)
                    if backup_already_exists:
                        logging.warning(msg)

                    if backup_succeeded:
                        copy_file_metadata(rpd_file.download_full_file_name, backup_full_file_name)
                if not backup_succeeded:
                    if rpd_file.status ==  DownloadStatus.download_failed:
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

            self.total_downloaded += rpd_file.size
            bytes_not_downloaded = rpd_file.size - self.amount_downloaded
            if bytes_not_downloaded and data.do_backup:
                self.content= pickle.dumps(BackupResults(
                    scan_id=self.scan_id, device_id=self.device_id,
                    total_downloaded=self.total_downloaded,
                    chunk_downloaded=bytes_not_downloaded),
                    pickle.HIGHEST_PROTOCOL)
                self.send_message_to_sink()

            self.content = pickle.dumps(BackupResults(
                scan_id=self.scan_id, device_id=self.device_id,
                backup_succeeded=backup_succeeded, do_backup=data.do_backup,
                rpd_file=rpd_file, backup_full_file_name=backup_full_file_name))
            self.send_message_to_sink()


if __name__ == "__main__":
    backup = BackupFilesWorker()