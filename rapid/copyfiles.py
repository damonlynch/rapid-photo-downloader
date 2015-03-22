#!/usr/bin/python3
__author__ = 'Damon Lynch'

# Copyright (C) 2011-2015 Damon Lynch <damonlynch@gmail.com>

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

import tempfile
import os
import random
import string
import errno
import io
import shutil
import stat
import hashlib
import logging
import pickle

from . import rpdfile
from . import problemnotification as pn

from interprocess import CopyFilesArguments
from interprocess import WorkerInPublishPullPipeline
from constants import FileType
from . import thumbnail as tn

from gettext import gettext as _

logging.basicConfig(format='%(levelname)s:%(asctime)s:%(message)s',
                    datefmt='%H:%M:%S',
                    level=logging.DEBUG)


def copy_file_metadata(src, dst):
    """
    Copy all stat info (mode bits, atime, mtime, flags) from src to
    dst.

    Adapted from python's shutil.copystat().

    Necessary because with some NTFS file systems, there can be
    problems with setting filesystem metadata like permissions and
    modification time
    """

    st = os.stat(src)
    mode = stat.S_IMODE(st.st_mode)
    try:
        os.utime(dst, (st.st_atime, st.st_mtime))
    except OSError as inst:
        logging.warning(
            "Couldn't adjust file modification time when copying %s. %s: %s",
            src, inst.errno, inst.strerror)
    try:
        os.chmod(dst, mode)
    except OSError as inst:
        if logging:
            logging.warning(
                "Couldn't adjust file permissions when copying %s. %s: %s",
                src, inst.errno, inst.strerror)

    if hasattr(os, 'chflags') and hasattr(st, 'st_flags'):
        try:
            os.chflags(dst, st.st_flags)
        except OSError as why:
            for err in 'EOPNOTSUPP', 'ENOTSUP':
                if hasattr(errno, err) and why.errno == getattr(errno, err):
                    break
            else:
                raise

class CopyFilesWorker(WorkerInPublishPullPipeline):

    def __init__(self):
        super(CopyFilesWorker, self).__init__('CopyFiles')
        self.io_buffer = 1048576

    def do_work(self):
        copyfiles_args = pickle.loads(self.content)
        """:type : CopyFilesArguments"""

        for idx, rpd_file in enumerate(copyfiles_args.files):
            self.check_for_command()


class CopyFiles(multiprocessing.Process):
    """
    Copies files from source to temporary directory, giving them a random name
    """

    def __init__(self, photo_download_folder, video_download_folder, files,
                 verify_file,
                 modify_files_during_download, modify_pipe,
                 scan_pid,
                 batch_size_MB, results_pipe, terminate_queue,
                 run_event):
        multiprocessing.Process.__init__(self)
        self.results_pipe = results_pipe
        self.terminate_queue = terminate_queue
        self.batch_size_bytes = batch_size_MB * 1048576  # * 1024 * 1024
        self.io_buffer = 1048576
        self.photo_download_folder = photo_download_folder
        self.video_download_folder = video_download_folder
        self.files = files
        self.verify_file = verify_file
        self.modify_files_during_download = modify_files_during_download
        self.modify_pipe = modify_pipe
        self.scan_pid = scan_pid
        self.no_files = len(self.files)
        self.run_event = run_event


    def check_termination_request(self):
        """
        Check to see this process has not been requested to immediately
        terminate
        """
        if not self.terminate_queue.empty():
            x = self.terminate_queue.get()
            # terminate immediately
            logging.info("Terminating file copying")
            return True
        return False


    def update_progress(self, amount_downloaded, total):

        chunk_downloaded = amount_downloaded - self.bytes_downloaded
        if (chunk_downloaded > self.batch_size_bytes) or (
            amount_downloaded == total):
            self.bytes_downloaded = amount_downloaded
            self.results_pipe.send((rpdmp.CONN_PARTIAL, (rpdmp.MSG_BYTES, (
            self.scan_pid, self.total_downloaded + amount_downloaded,
            chunk_downloaded))))
            if amount_downloaded == total:
                self.bytes_downloaded = 0


    def run(self):
        """start the actual copying of files"""

        # characters used to generate temporary filenames
        filename_characters = string.letters + string.digits

        self.bytes_downloaded = 0
        self.total_downloaded = 0

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

                # pause if instructed by the caller
                self.run_event.wait()

                if self.check_termination_request():
                    return None

                #generate temporary name 5 digits long, no extension
                temp_name = ''.join(
                    random.choice(filename_characters) for i in range(5))

                temp_full_file_name = os.path.join(
                    self._get_dest_dir(rpd_file.file_type),
                    temp_name)
                rpd_file.temp_full_file_name = temp_full_file_name

                copy_succeeded = False

                src_bytes = ''

                try:
                    dest = io.open(temp_full_file_name, 'wb', self.io_buffer)
                    src = io.open(rpd_file.full_file_name, 'rb',
                                  self.io_buffer)
                    total = rpd_file.size
                    amount_downloaded = 0
                    while True:
                        # first check if process is being terminated
                        if self.check_termination_request():
                            logging.debug(
                                "Closing partially written temporary file")
                            dest.close()
                            src.close()
                            return None
                        else:
                            chunk = src.read(self.io_buffer)
                            if chunk:
                                dest.write(chunk)
                                src_bytes += chunk
                                amount_downloaded += len(chunk)
                                self.update_progress(amount_downloaded, total)
                            else:
                                break
                    dest.close()
                    src.close()
                    copy_succeeded = True
                except (IOError, OSError) as inst:
                    rpd_file.add_problem(None,
                                         pn.DOWNLOAD_COPYING_ERROR_W_NO,
                                         {'filetype': rpd_file.title})
                    rpd_file.add_extra_detail(
                        pn.DOWNLOAD_COPYING_ERROR_W_NO_DETAIL,
                        {'errorno': inst.errno, 'strerror': inst.strerror})

                    rpd_file.status = constants.STATUS_DOWNLOAD_FAILED

                    rpd_file.error_title = rpd_file.problem.get_title()
                    rpd_file.error_msg = _("%(problem)s\nFile: %(file)s") % \
                                         {
                                         'problem':
                                             rpd_file.problem.get_problems(),
                                         'file': rpd_file.full_file_name}

                    logging.error("Failed to download file: %s",
                                  rpd_file.full_file_name)
                    logging.error(inst)
                    self.update_progress(rpd_file.size, rpd_file.size)
                except:
                    rpd_file.add_problem(None,
                                         pn.DOWNLOAD_COPYING_ERROR,
                                         {'filetype': rpd_file.title})
                    rpd_file.add_extra_detail(
                        pn.DOWNLOAD_COPYING_ERROR_DETAIL,
                        _("An unknown error occurred"))

                    rpd_file.status = constants.STATUS_DOWNLOAD_FAILED

                    rpd_file.error_title = rpd_file.problem.get_title()
                    rpd_file.error_msg = _("%(problem)s\nFile: %(file)s") % \
                                         {
                                         'problem':
                                             rpd_file.problem.get_problems(),
                                         'file': rpd_file.full_file_name}

                    logging.error("Failed to download file: %s",
                                  rpd_file.full_file_name)
                    self.update_progress(rpd_file.size, rpd_file.size)

                # increment this amount regardless of whether the copy actually
                # succeeded or not. It's neccessary to keep the user informed.
                self.total_downloaded += rpd_file.size

                try:
                    copy_file_metadata(rpd_file.full_file_name,
                                       temp_full_file_name, logging)
                except:
                    logging.error(
                        "Unknown error updating filesystem metadata when "
                        "copying %s",
                        rpd_file.full_file_name)

                # copy THM (video thumbnail file) if there is one
                if copy_succeeded and rpd_file.thm_full_name:
                    # reuse video's file name
                    temp_thm_full_name = temp_full_file_name + '__rpd__thm'
                    try:
                        shutil.copyfile(rpd_file.thm_full_name,
                                        temp_thm_full_name)
                        rpd_file.temp_thm_full_name = temp_thm_full_name
                        logging.debug("Copied video THM file %s",
                                      rpd_file.temp_thm_full_name)
                    except (IOError, OSError) as inst:
                        logging.error("Failed to download video THM file: %s",
                                      rpd_file.thm_full_name)
                        logging.error("%s: %s", inst.errno, inst.strerror)
                    try:
                        copy_file_metadata(rpd_file.thm_full_name,
                                           temp_thm_full_name.logging)
                    except:
                        logging.error(
                            "Unknown error updating filesystem metadata when "
                            "copying %s",
                            rpd_file.thm_full_name)

                else:
                    temp_thm_full_name = None

                #copy audio file if there is one
                if copy_succeeded and rpd_file.audio_file_full_name:
                    # reuse photo's file name
                    temp_audio_full_name = temp_full_file_name + '__rpd__audio'
                    try:
                        shutil.copyfile(rpd_file.audio_file_full_name,
                                        temp_audio_full_name)
                        rpd_file.temp_audio_full_name = temp_audio_full_name
                        logging.debug("Copied audio file %s",
                                      rpd_file.temp_audio_full_name)
                    except (IOError, OSError) as inst:
                        logging.error("Failed to download audio file: %s",
                                      rpd_file.audio_file_full_name)
                        logging.error("%s: %s", inst.errno, inst.strerror)
                    try:
                        copy_file_metadata(rpd_file.audio_file_full_name,
                                           temp_audio_full_name, logging)
                    except:
                        logging.error(
                            "Unknown error updating filesystem metadata when "
                            "copying %s",
                            rpd_file.audio_file_full_name)

                if copy_succeeded and rpd_file.generate_thumbnail:
                    thumbnail, thumbnail_icon = \
                        self.thumbnail_maker.get_thumbnail(
                        temp_full_file_name,
                        temp_thm_full_name,
                        rpd_file.file_type,
                        (160, 120), (100, 100))
                else:
                    thumbnail = None
                    thumbnail_icon = None

                if copy_succeeded and self.verify_file:
                    rpd_file.md5 = hashlib.md5(src_bytes).hexdigest()

                if rpd_file.metadata is not None:
                    rpd_file.metadata = None

                download_count = i + 1
                if self.modify_files_during_download and copy_succeeded:
                    copy_finished = download_count == self.no_files

                    self.modify_pipe.send(
                        (rpd_file, download_count, temp_full_file_name,
                         thumbnail_icon, thumbnail, copy_finished))
                else:
                    self.results_pipe.send(
                        (rpdmp.CONN_PARTIAL, (rpdmp.MSG_FILE,
                                              (copy_succeeded, rpd_file,
                                               download_count,
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
        except OSError as inst:
            # FIXME: error reporting
            logging.error("Failed to create temporary directory in %s: %s %s",
                          folder,
                          inst.errono,
                          inst.strerror,
                          )
            temp_dir = None

        return temp_dir

    def create_temp_dirs(self):
        self.photo_temp_dir = self.video_temp_dir = None
        if self.photo_download_folder is not None:
            self.photo_temp_dir = self._create_temp_dir(
                self.photo_download_folder)
            logging.debug("Photo temporary directory: %s", self.photo_temp_dir)
        if self.video_download_folder is not None:
            self.video_temp_dir = self._create_temp_dir(
                self.video_download_folder)
            logging.debug("Video temporary directory: %s", self.video_temp_dir)



