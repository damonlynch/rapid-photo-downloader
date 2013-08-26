#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2011-2012 Damon Lynch <damonlynch@gmail.com>

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
import random
import string

import gio

import logging
logger = multiprocessing.get_logger()

import rpdmultiprocessing as rpdmp
import rpdfile
import problemnotification as pn
import config
import thumbnail as tn


from gettext import gettext as _


class CopyFiles(multiprocessing.Process):
    """
    Copies files from source to temporary directory, giving them a random name
    """
    def __init__(self, photo_download_folder, video_download_folder, files,
                 modify_files_during_download, modify_pipe,
                 scan_pid,
                 batch_size_MB, results_pipe, terminate_queue,
                 run_event):
        multiprocessing.Process.__init__(self)
        self.results_pipe = results_pipe
        self.terminate_queue = terminate_queue
        self.batch_size_bytes = batch_size_MB * 1048576 # * 1024 * 1024
        self.photo_download_folder = photo_download_folder
        self.video_download_folder = video_download_folder
        self.files = files
        self.modify_files_during_download = modify_files_during_download
        self.modify_pipe = modify_pipe
        self.scan_pid = scan_pid
        self.no_files= len(self.files)
        self.run_event = run_event

    def check_termination_request(self):
        """
        Check to see this process has not been requested to immediately terminate
        """
        if not self.terminate_queue.empty():
            x = self.terminate_queue.get()
            # terminate immediately
            logger.info("Terminating file copying")
            return True
        return False


    def update_progress(self, amount_downloaded, total):
        # first check if process is being terminated
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

                    self.results_pipe.send((rpdmp.CONN_PARTIAL, (rpdmp.MSG_BYTES, (self.scan_pid, self.total_downloaded + amount_downloaded, chunk_downloaded))))
                    if amount_downloaded == total:
                        self.bytes_downloaded = 0

    def progress_callback(self, amount_downloaded, total):
        self.update_progress(amount_downloaded, total)

    def thm_progress_callback(self, amount_downloaded, total):
        # we don't care about tracking download progress for tiny THM files!
        pass


    def run(self):
        """start the actual copying of files"""

        #characters used to generate temporary filenames
        filename_characters = string.letters + string.digits

        self.bytes_downloaded = 0
        self.total_downloaded = 0

        self.cancel_copy = gio.Cancellable()

        self.create_temp_dirs()

        # Send the location of both temporary directories, so they can be
        # removed once another process attempts to rename all the files in them
        # and move them to generated subfolders
        self.results_pipe.send((rpdmp.CONN_PARTIAL, (rpdmp.MSG_TEMP_DIRS,
                                                     (self.scan_pid,
                                                     self.photo_temp_dir,
                                                     self.video_temp_dir))))

        if self.photo_temp_dir or self.video_temp_dir:

            self.thumbnail_maker = tn.Thumbnail()

            for i in range(self.no_files):
                rpd_file = self.files[i]
                self.total_reached = False

                # pause if instructed by the caller
                self.run_event.wait()

                if self.check_termination_request():
                    return None

                source = gio.File(path=rpd_file.full_file_name)

                #generate temporary name 5 digits long, no extension
                temp_name = ''.join(random.choice(filename_characters) for i in xrange(5))

                temp_full_file_name = os.path.join(
                                    self._get_dest_dir(rpd_file.file_type),
                                    temp_name)
                rpd_file.temp_full_file_name = temp_full_file_name
                dest = gio.File(path=temp_full_file_name)

                copy_succeeded = False
                try:
                    source.copy(dest, self.progress_callback, cancellable=self.cancel_copy)
                    copy_succeeded = True
                except gio.Error, inst:
                    rpd_file.add_problem(None,
                        pn.DOWNLOAD_COPYING_ERROR_W_NO,
                        {'filetype': rpd_file.title})
                    rpd_file.add_extra_detail(
                        pn.DOWNLOAD_COPYING_ERROR_W_NO_DETAIL,
                        {'errorno': inst.code, 'strerror': inst.message})

                    rpd_file.status = config.STATUS_DOWNLOAD_FAILED

                    rpd_file.error_title = rpd_file.problem.get_title()
                    rpd_file.error_msg = _("%(problem)s\nFile: %(file)s") % \
                                  {'problem': rpd_file.problem.get_problems(),
                                   'file': rpd_file.full_file_name}

                    logger.error("Failed to download file: %s", rpd_file.full_file_name)
                    logger.error(inst)
                    self.update_progress(rpd_file.size, rpd_file.size)

                # increment this amount regardless of whether the copy actually
                # succeeded or not. It's neccessary to keep the user informed.
                self.total_downloaded += rpd_file.size

                # copy THM (video thumbnail file) if there is one
                if copy_succeeded and rpd_file.thm_full_name:
                    source = gio.File(path=rpd_file.thm_full_name)
                    # reuse video's file name
                    temp_thm_full_name = temp_full_file_name + '__rpd__thm'
                    dest = gio.File(path=temp_thm_full_name)
                    try:
                        source.copy(dest, self.thm_progress_callback, cancellable=self.cancel_copy)
                        rpd_file.temp_thm_full_name = temp_thm_full_name
                        logger.debug("Copied video THM file %s", rpd_file.temp_thm_full_name)
                    except gio.Error, inst:
                        logger.error("Failed to download video THM file: %s", rpd_file.thm_full_name)
                else:
                    temp_thm_full_name = None

                #copy audio file if there is one
                if copy_succeeded and rpd_file.audio_file_full_name:
                    source = gio.File(path=rpd_file.audio_file_full_name)
                    # reuse photo's file name
                    temp_audio_full_name = temp_full_file_name + '__rpd__audio'
                    dest = gio.File(path=temp_audio_full_name)
                    try:
                        source.copy(dest, self.thm_progress_callback, cancellable=self.cancel_copy)
                        rpd_file.temp_audio_full_name = temp_audio_full_name
                        logger.debug("Copied audio file %s", rpd_file.temp_audio_full_name)
                    except gio.Error, inst:
                        logger.error("Failed to download audio file: %s", rpd_file.audio_file_full_name)


                if copy_succeeded and rpd_file.generate_thumbnail:
                    thumbnail, thumbnail_icon = self.thumbnail_maker.get_thumbnail(
                                    temp_full_file_name,
                                    temp_thm_full_name,
                                    rpd_file.file_type,
                                    (160, 120), (100,100))
                else:
                    thumbnail = None
                    thumbnail_icon = None

                if rpd_file.metadata is not None:
                    rpd_file.metadata = None


                download_count = i + 1
                if self.modify_files_during_download and copy_succeeded:
                    copy_finished = download_count == self.no_files

                    self.modify_pipe.send((rpd_file, download_count, temp_full_file_name,
                        thumbnail_icon, thumbnail, copy_finished))
                else:
                    self.results_pipe.send((rpdmp.CONN_PARTIAL, (rpdmp.MSG_FILE,
                        (copy_succeeded, rpd_file, download_count,
                         temp_full_file_name,
                         thumbnail_icon, thumbnail))))


        self.results_pipe.send((rpdmp.CONN_COMPLETE, None))


    def _get_dest_dir(self, file_type):
        if file_type == rpdfile.FILE_TYPE_PHOTO:
            return self.photo_temp_dir
        else:
            return self.video_temp_dir

    def _create_temp_dir(self, folder):
        try:
            temp_dir = tempfile.mkdtemp(prefix="rpd-tmp-", dir=folder)
        except OSError, (errno, strerror):
            # FIXME: error reporting
            logger.error("Failed to create temporary directory in %s: %s %s",
                         errono,
                         strerror,
                         folder)
            temp_dir = None

        return temp_dir

    def create_temp_dirs(self):
        self.photo_temp_dir = self.video_temp_dir = None
        if self.photo_download_folder is not None:
            self.photo_temp_dir = self._create_temp_dir(self.photo_download_folder)
        if self.video_download_folder is not None:
            self.video_temp_dir = self._create_temp_dir(self.photo_download_folder)



