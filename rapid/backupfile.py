#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2011 - 2012 Damon Lynch <damonlynch@gmail.com>

### This program is free software; you can redistribute it and/or modify
### it under the terms of the GNU General Public License as published by
### the Free Software Foundation; either version 2 of the License, or
### (at your option) any later version.

### This program is distributed in the hope that it will be useful,
### but WITHOUT ANY WARRANTY; without even the implied warranty of
### MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
### GNU General Public License for more details.

### You should have received a copy of the GNU General Public License
### along with this program; if not, write to the Free Software
### Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301
### USA

import multiprocessing
import tempfile
import os

import gio
import shutil

import logging
logger = multiprocessing.get_logger()

import rpdmultiprocessing as rpdmp
import rpdfile
import problemnotification as pn
import config

PHOTO_BACKUP = 1
VIDEO_BACKUP = 2
PHOTO_VIDEO_BACKUP = 3

from gettext import gettext as _


class BackupFiles(multiprocessing.Process):
    def __init__(self, path, name,
                 batch_size_MB, results_pipe, terminate_queue,
                 run_event):
        multiprocessing.Process.__init__(self)
        self.results_pipe = results_pipe
        self.terminate_queue = terminate_queue
        self.batch_size_bytes = batch_size_MB * 1048576 # * 1024 * 1024
        self.path = path
        self.mount_name = name
        self.run_event = run_event

        # As of Ubuntu 12.10 / Fedora 18, the file move/rename command is running agonisingly slowly
        # A hackish workaround is to replace it with the standard python function
        self.use_gnome_file_operations = False

    def check_termination_request(self):
        """
        Check to see this process has not been requested to immediately terminate
        """
        if not self.terminate_queue.empty():
            x = self.terminate_queue.get()
            # terminate immediately
            logger.info("Terminating file backup")
            return True
        return False


    def update_progress(self, amount_downloaded, total):
        # first check if process is being terminated
        self.amount_downloaded = amount_downloaded
        if not self.terminate_queue.empty():
            # it is - cancel the current copy
            self.cancel_copy.cancel()
        else:
            if not self.total_reached:
                chunk_downloaded = amount_downloaded - self.bytes_downloaded
                if (chunk_downloaded > self.batch_size_bytes) or (amount_downloaded == total):
                    self.bytes_downloaded = amount_downloaded

                    if amount_downloaded == total:
                        # this function is called a couple of times when total is reached
                        self.total_reached = True

                    self.results_pipe.send((rpdmp.CONN_PARTIAL, (rpdmp.MSG_BYTES, (self.scan_pid, self.pid, self.total_downloaded + amount_downloaded, chunk_downloaded))))
                    if amount_downloaded == total:
                        self.bytes_downloaded = 0

    def progress_callback(self, amount_downloaded, total):
        self.update_progress(amount_downloaded, total)

    def progress_callback_no_update(self, amount_downloaded, total):
        """called when copying very small files"""
        pass

    def backup_additional_file(self, dest_dir, full_file_name):
        """Backs up small files like XMP or THM files"""
        source = gio.File(full_file_name)
        dest_name = os.path.join(dest_dir, os.path.split(full_file_name)[1])

        if self.use_gnome_file_operations:
            logger.debug("Backing up additional file %s...", dest_name)
            dest=gio.File(dest_name)
            try:
                source.copy(dest, self.progress_callback_no_update, cancellable=None)
                logger.debug("...backing up additional file %s succeeded", dest_name)
            except gio.Error, inst:
                    logger.error("Failed to backup file %s: %s", full_file_name, inst)
        else:
            try:
                logger.debug("Using python to back up additional file %s...", dest_name)
                shutil.copy(full_file_name, dest_name)
                logger.debug("...backing up additional file %s succeeded", dest_name)
            except:
                logger.error("Backup of %s failed", full_file_name)

    def run(self):

        self.cancel_copy = gio.Cancellable()
        self.bytes_downloaded = 0
        self.total_downloaded = 0

        while True:

            self.amount_downloaded = 0
            move_succeeded, rpd_file, path_suffix, backup_duplicate_overwrite, download_count = self.results_pipe.recv()
            if rpd_file is None:
                # this is a termination signal
                return None
            # pause if instructed by the caller
            self.run_event.wait()

            if self.check_termination_request():
                return None

            backup_succeeded = False
            self.scan_pid = rpd_file.scan_pid

            if move_succeeded:
                self.total_reached = False

                source = gio.File(path=rpd_file.download_full_file_name)

                if path_suffix is None:
                    dest_base_dir = self.path
                else:
                    dest_base_dir = os.path.join(self.path, path_suffix)


                dest_dir = os.path.join(dest_base_dir, rpd_file.download_subfolder)
                backup_full_file_name = os.path.join(
                                    dest_dir,
                                    rpd_file.download_name)

                subfolder = gio.File(path=dest_dir)
                if not subfolder.query_exists(cancellable=None):
                    # create the subfolders on the backup path
                    try:
                        logger.debug("Creating subfolder %s on backup device %s...", dest_dir, self.mount_name)
                        subfolder.make_directory_with_parents(cancellable=gio.Cancellable())
                        logger.debug("...backup subfolder created")
                    except gio.Error, inst:
                        # There is a tiny chance directory may have been created by
                        # another process between the time it takes to query and
                        # the time it takes to create a new directory.
                        # Ignore such errors.
                        if inst.code <> gio.ERROR_EXISTS:
                            logger.error("Failed to create backup subfolder: %s", dest_dir)
                            logger.error(inst)
                            rpd_file.add_problem(None, pn.BACKUP_DIRECTORY_CREATION, self.mount_name)
                            rpd_file.add_extra_detail('%s%s' % (pn.BACKUP_DIRECTORY_CREATION, self.mount_name), inst)
                            rpd_file.error_title = _('Backing up error')
                            rpd_file.error_msg = \
                                 _("Destination directory could not be created: %(directory)s\n") % \
                                  {'directory': subfolder,  } + \
                                 _("Source: %(source)s\nDestination: %(destination)s") % \
                                  {'source': rpd_file.download_full_file_name,
                                   'destination': backup_full_file_name} + "\n" + \
                                 _("Error: %(inst)s") % {'inst': inst}

                dest = gio.File(path=backup_full_file_name)
                if backup_duplicate_overwrite:
                    flags = gio.FILE_COPY_OVERWRITE
                else:
                    flags = gio.FILE_COPY_NONE

                if self.use_gnome_file_operations:
                    try:
                        logger.debug("Backing up file %s on device %s...", download_count, self.mount_name)
                        source.copy(dest, self.progress_callback, flags,
                                            cancellable=self.cancel_copy)
                        backup_succeeded = True
                        logger.debug("...backing up file %s on device %s succeeded", download_count, self.mount_name)
                    except gio.Error, inst:
                        fileNotBackedUpMessageDisplayed = True
                        rpd_file.add_problem(None, pn.BACKUP_ERROR, self.mount_name)
                        rpd_file.add_extra_detail('%s%s' % (pn.BACKUP_ERROR, self.mount_name), inst)
                        rpd_file.error_title = _('Backing up error')
                        rpd_file.error_msg = \
                                _("Source: %(source)s\nDestination: %(destination)s") % \
                                 {'source': rpd_file.download_full_file_name, 'destination': backup_full_file_name} + "\n" + \
                                _("Error: %(inst)s") % {'inst': inst}
                        logger.error("%s:\n%s", rpd_file.error_title, rpd_file.error_msg)
                else:
                    try:
                        logger.debug("Using python to back up file %s on device %s...", download_count, self.mount_name)
                        shutil.copy(rpd_file.download_full_file_name, backup_full_file_name)
                        backup_succeeded = True
                        logger.debug("...backing up file %s on device %s succeeded", download_count, self.mount_name)
                    except:
                        logger.error("Backup of %s failed", backup_full_file_name)


                if not backup_succeeded:
                    if rpd_file.status ==  config.STATUS_DOWNLOAD_FAILED:
                        rpd_file.status = config.STATUS_DOWNLOAD_AND_BACKUP_FAILED
                    else:
                        rpd_file.status = config.STATUS_BACKUP_PROBLEM
                else:
                    # backup any THM, audio or XMP files
                    if rpd_file.download_thm_full_name:
                        self.backup_additional_file(dest_dir,
                                        rpd_file.download_thm_full_name)
                    if rpd_file.download_audio_full_name:
                        self.backup_additional_file(dest_dir,
                                        rpd_file.download_audio_full_name)
                    if rpd_file.download_xmp_full_name:
                        self.backup_additional_file(dest_dir,
                                        rpd_file.download_xmp_full_name)

            self.total_downloaded += rpd_file.size
            bytes_not_downloaded = rpd_file.size - self.amount_downloaded
            if bytes_not_downloaded:
                self.results_pipe.send((rpdmp.CONN_PARTIAL, (rpdmp.MSG_BYTES, (self.scan_pid, self.pid, self.total_downloaded, bytes_not_downloaded))))

            self.results_pipe.send((rpdmp.CONN_PARTIAL, (rpdmp.MSG_FILE,
                                   (backup_succeeded, rpd_file))))






