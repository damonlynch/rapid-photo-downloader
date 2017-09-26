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

import os
import errno
import io
import shutil
import stat
import hashlib
import logging
import pickle
from operator import attrgetter
from itertools import chain
from collections import defaultdict
from typing import Dict, Optional, Tuple
import locale
# Use the default locale as defined by the LANG variable
locale.setlocale(locale.LC_ALL, '')

import gphoto2 as gp

from gettext import gettext as _

import problemnotification as pn
from raphodo.camera import Camera, CameraProblemEx
from raphodo.interprocess import (
    WorkerInPublishPullPipeline, CopyFilesArguments, CopyFilesResults
)
from raphodo.constants import (FileType, DownloadStatus, CameraErrorCode)
from raphodo.utilities import (GenerateRandomFileName, create_temp_dirs, same_device)
from raphodo.rpdfile import RPDFile
from raphodo.problemnotification import (
    CopyingProblems, CameraFileReadProblem, FileWriteProblem, FileMoveProblem, FileDeleteProblem,
    FileCopyProblem, CameraInitializationProblem
)
from raphodo.storage import get_uri
from raphodo.preferences import Preferences
from raphodo.rescan import RescanCamera


def copy_file_metadata(src: str, dst: str) -> Optional[Tuple]:
    """
    Copy all stat info (mode bits, atime, mtime, flags) from src to
    dst.

    Adapted from python's shutil.copystat().

    Necessary because with some NTFS file systems, there can be
    problems with setting filesystem metadata like permissions and
    modification time

    :return Tuple of errors, if there were any, else None
    """

    st = os.stat(src)
    mode = stat.S_IMODE(st.st_mode)
    errors = []

    try:
        os.utime(dst, (st.st_atime, st.st_mtime))
    except (OSError, PermissionError, FileNotFoundError) as inst:
        errors.append(inst)

    try:
        os.chmod(dst, mode)
    except (OSError, PermissionError, FileNotFoundError) as inst:
        errors.append(inst)

    if hasattr(os, 'chflags') and hasattr(st, 'st_flags'):
        try:
            os.chflags(dst, st.st_flags)
        except OSError as why:
            for err in 'EOPNOTSUPP', 'ENOTSUP':
                if hasattr(errno, err) and why.errno == getattr(errno, err):
                    break
            else:
                pass

    if errors:
        return tuple(errors)

    # Test code:
    # try:
    #     os.chown('/', 1000, 1000)
    # except OSError as inst:
    #     return inst,


def copy_camera_file_metadata(mtime: float, dst: str) -> Optional[Tuple]:
    # test code:
    # try:
    #     os.chown('/', 1000, 1000)
    # except OSError as inst:
    #     return inst,

    try:
        os.utime(dst, (mtime, mtime))
    except (OSError, PermissionError, FileNotFoundError) as inst:
        return inst,  # note the comma: return a Tuple


class FileCopy:
    """
    Used by classes CopyFilesWorker and BackupFilesWorker
    """
    def __init__(self):
        self.io_buffer = 1024 * 1024
        self.batch_size_bytes = 5 * 1024 * 1024
        self.dest = self.src = None

        self.bytes_downloaded = 0
        self.total_downloaded = 0

    def cleanup_pre_stop(self):
        if self.dest is not None:
            self.dest.close()
        if self.src is not None:
            self.src.close()

    def init_copy_progress(self) -> None:
        self.bytes_downloaded = 0

    def copy_from_filesystem(self, source: str, destination: str, rpd_file: RPDFile) -> bool:
        src_chunks = []
        try:
            self.dest = io.open(destination, 'wb', self.io_buffer)
            self.src = io.open(source, 'rb', self.io_buffer)
            total = rpd_file.size
            amount_downloaded = 0

            while True:
                # first check if process is being stopped or paused
                self.check_for_controller_directive()

                chunk = self.src.read(self.io_buffer)
                if chunk:
                    self.dest.write(chunk)
                    if self.verify_file:
                        src_chunks.append(chunk)
                    amount_downloaded += len(chunk)
                    self.update_progress(amount_downloaded, total)
                else:
                    break
            self.dest.close()
            self.src.close()

            if self.verify_file:
                src_bytes = b''.join(src_chunks)
                rpd_file.md5 = hashlib.md5(src_bytes).hexdigest()

            return True
        except (OSError, FileNotFoundError, PermissionError) as e:
            self.problems.append(
                FileCopyProblem(
                    name=os.path.basename(source), uri=get_uri(full_file_name=source), exception=e
                )
            )
            try:
                msg = '%s: %s' % (e.errno, e.strerror)
            except AttributeError:
                msg = str(e)
            logging.error("%s. Failed to copy %s to %s", msg, source, destination)
            return False
        except Exception as e:
            self.problems.append(
                FileCopyProblem(
                    name=os.path.basename(source), uri=get_uri(full_file_name=source), exception=e
                )
            )
            try:
                msg = '%s: %s' % (e.errno, e.strerror)
            except AttributeError:
                msg = str(e)
            logging.error("Unexpected error: %s. Failed to copy %s to %s", msg, source, destination)
            return False


class CopyFilesWorker(WorkerInPublishPullPipeline, FileCopy):

    def __init__(self):
        super().__init__('CopyFiles')

    def cleanup_pre_stop(self) -> None:
        super().cleanup_pre_stop()
        if self.camera is not None:
            if self.camera.camera_initialized:
                self.camera.free_camera()
        self.send_problems()

    def send_problems(self) -> None:
        """
        Send problems encountered copying to the main process.

        Always sends problems, even if empty, because of the
        possibility that there were filesystem metadata errors
        encountered.
        """

        self.content = pickle.dumps(
            CopyFilesResults(
                scan_id=self.scan_id, problems=self.problems
            ),
            pickle.HIGHEST_PROTOCOL
        )
        self.send_message_to_sink()

    def update_progress(self, amount_downloaded: int, total: int) -> None:
        """
        Update the main process about how many bytes have been copied

        :param amount_downloaded: the size in bytes of the file that
         has been copied
        :param total: the size of the file in bytes
        """

        chunk_downloaded = amount_downloaded - self.bytes_downloaded
        if (chunk_downloaded > self.batch_size_bytes) or (amount_downloaded == total):
            self.bytes_downloaded = amount_downloaded
            self.content = pickle.dumps(
                CopyFilesResults(
                    scan_id=self.scan_id,
                    total_downloaded=self.total_downloaded + amount_downloaded,
                    chunk_downloaded=chunk_downloaded),
               pickle.HIGHEST_PROTOCOL)
            self.send_message_to_sink()

            # if amount_downloaded == total:
            #     self.bytes_downloaded = 0

    def copy_from_camera(self, rpd_file: RPDFile) -> bool:

        try:
            src_bytes = self.camera.save_file_by_chunks(
                dir_name=rpd_file.path,
                file_name=rpd_file.name,
                size=rpd_file.size,
                dest_full_filename=rpd_file.temp_full_file_name,
                progress_callback=self.update_progress,
                check_for_command=self.check_for_controller_directive,
                return_file_bytes=self.verify_file
            )
        except CameraProblemEx as e:
            name = rpd_file.name
            uri = rpd_file.get_uri()
            if e.code == CameraErrorCode.read:
                self.problems.append(CameraFileReadProblem(name=name, uri=uri, gp_code=e.gp_code))
            else:
                assert e.code == CameraErrorCode.write
                self.problems.append(FileWriteProblem(name=name, uri=uri, exception=e.py_exception))
            return False

        if self.verify_file:
            rpd_file.md5 = hashlib.md5(src_bytes).hexdigest()

        return True

    def copy_associate_file(self, rpd_file: RPDFile, temp_name: str,
                            dest_dir: str, associate_file_fullname: str,
                            file_type: str) -> Optional[str]:

        ext = os.path.splitext(associate_file_fullname)[1]
        temp_ext = '{}{}'.format(temp_name, ext)
        temp_full_name = os.path.join(dest_dir, temp_ext)
        if rpd_file.from_camera:
            dir_name, file_name = os.path.split(associate_file_fullname)
            try:
                self.camera.save_file(dir_name, file_name, temp_full_name)
            except CameraProblemEx as e:
                uri = get_uri(
                    full_file_name=associate_file_fullname, camera_details=rpd_file.camera_details
                )
                if e.code == CameraErrorCode.read:
                    self.problems.append(
                        CameraFileReadProblem(name=file_name, uri=uri, gp_code=e.gp_code)
                    )
                else:
                    assert e.code == CameraErrorCode.write
                    self.problems.append(FileWriteProblem(
                        name=file_name, uri=uri, exception=e.py_exception
                    ))
                logging.error("Failed to download %s file: %s", file_type, associate_file_fullname)
                return None
        else:
            try:
                shutil.copyfile(associate_file_fullname, temp_full_name)
            except (OSError, FileNotFoundError, PermissionError) as e:
                logging.error("Failed to download %s file: %s", file_type, associate_file_fullname)
                logging.error("%s: %s", e.errno, e.strerror)
                name = os.path.basename(associate_file_fullname)
                uri = get_uri(full_file_name=associate_file_fullname)
                self.problems.append(FileWriteProblem(name=name, uri=uri, exception=e))
                return None
            logging.debug("Copied %s file %s", file_type, temp_full_name)

        # Adjust file modification times and other file system metadata
        # Ignore any errors copying file system metadata -- assume they would
        # have been raised when copying the primary file's filesystem metadata
        if rpd_file.from_camera:
            copy_camera_file_metadata(mtime=rpd_file.modification_time, dst=temp_full_name)
        else:
            copy_file_metadata(associate_file_fullname, temp_full_name)
        return temp_full_name

    def do_work(self):
        self.problems = CopyingProblems()
        args = pickle.loads(self.content)  # type: CopyFilesArguments

        if args.log_gphoto2:
            gp.use_python_logging()

        self.scan_id = args.scan_id
        self.verify_file = args.verify_file

        self.camera = None

        # To workaround a bug in iOS and possibly other devices, check if need to rescan the files
        # on the device
        rescan_check = [
            rpd_file for rpd_file in args.files
            if rpd_file.from_camera and not rpd_file.cache_full_file_name
         ]
        no_rescan = [
            rpd_file for rpd_file in args.files
            if not rpd_file.from_camera or rpd_file.cache_full_file_name
        ]

        if rescan_check:
            prefs = Preferences()
            # Initialize camera
            try:
                self.camera = Camera(
                    args.device.camera_model, args.device.camera_port,
                    raise_errors=True, specific_folders=prefs.folders_to_scan
                )
            except CameraProblemEx as e:
                self.problems.append(
                    CameraInitializationProblem(gp_code=e.gp_code)
                )
                logging.error("Could not initialize camera %s", self.display_name)
            else:
                rescan = RescanCamera(camera=self.camera, prefs=prefs)
                rescan.rescan_camera(rpd_files=rescan_check)
                rescan_check = rescan.rpd_files
                if rescan.missing_rpd_files:
                    logging.error(
                        "%s files could not be relocated on %s",
                        len(rescan.missing_rpd_files), self.camera.display_name
                    )
                    rescan_check = list(chain(rescan_check, rescan.missing_rpd_files))

        rpd_files = list(chain(rescan_check, no_rescan))

        random_filename = GenerateRandomFileName()

        rpd_cache_same_device = defaultdict(lambda: None)  # type: Dict[FileType, Optional[bool]]

        photo_temp_dir, video_temp_dir = create_temp_dirs(
            args.photo_download_folder, args.video_download_folder)

        # Notify main process of temp directory names
        self.content = pickle.dumps(CopyFilesResults(
                    scan_id=args.scan_id,
                    photo_temp_dir=photo_temp_dir or '',
                    video_temp_dir=video_temp_dir or ''),
                    pickle.HIGHEST_PROTOCOL)
        self.send_message_to_sink()

        # Sort the files to be copied by modification time
        # Important to do this with respect to sequence numbers, or else
        # they'll be downloaded in what looks like a random order
        rpd_files = sorted(rpd_files, key=attrgetter('modification_time'))

        self.display_name = args.device.display_name

        for idx, rpd_file in enumerate(rpd_files):

            self.dest = self.src = None

            if rpd_file.file_type == FileType.photo:
                dest_dir = photo_temp_dir
            else:
                dest_dir = video_temp_dir

            # Three scenarios:
            # 1. Downloading from device with file system we can directly
            #    access
            # 2. Downloading from camera using libgphoto2
            # 3. Downloading from camera where we've already cached at
            #    least some of the files in the Download Cache

            self.init_copy_progress()

            if rpd_file.cache_full_file_name and os.path.isfile(rpd_file.cache_full_file_name):
                # Scenario 3
                temp_file_name = os.path.basename(rpd_file.cache_full_file_name)
                temp_name = os.path.splitext(temp_file_name)[0]
                temp_full_file_name = os.path.join(dest_dir,temp_file_name)

                if rpd_cache_same_device[rpd_file.file_type] is None:
                    rpd_cache_same_device[rpd_file.file_type] = same_device(
                        rpd_file.cache_full_file_name, dest_dir)

                if rpd_cache_same_device[rpd_file.file_type]:
                    try:
                        shutil.move(rpd_file.cache_full_file_name, temp_full_file_name)
                        copy_succeeded = True
                    except (OSError, PermissionError, FileNotFoundError) as inst:
                        copy_succeeded = False
                        logging.error("Could not move cached file %s to temporary file %s. Error "
                                      "code: %s", rpd_file.cache_full_file_name,
                                      temp_full_file_name, inst.errno)
                        self.problems.append(
                            FileMoveProblem(
                                name=rpd_file.name, uri=rpd_file.get_uri(), exception=inst
                            )
                        )
                    if self.verify_file:
                        rpd_file.md5 = hashlib.md5(open(
                            temp_full_file_name).read()).hexdigest()
                    self.update_progress(rpd_file.size, rpd_file.size)
                else:
                    # The download folder changed since the scan occurred, and is now
                    # on a different file system compared to that where the devices
                    # files were cached. Or the file was downloaded in full by the scan
                    # stage and saved, e.g. a sample video.
                    source = rpd_file.cache_full_file_name
                    destination = temp_full_file_name
                    copy_succeeded = self.copy_from_filesystem(source, destination, rpd_file)
                    try:
                        os.remove(source)
                    except (OSError, PermissionError, FileNotFoundError) as e:
                        logging.error("Error removing RPD Cache file %s while copying %s. Error "
                                      "code: %s", source, rpd_file.full_file_name, e.errno)
                        self.problems.append(
                            FileDeleteProblem(
                                name=os.path.basename(source), uri=get_uri(source), exception=e
                            )
                        )

            else:
                # Scenario 1 or 2
                # Generate temporary name 5 digits long, because we cannot
                # guarantee the source does not have duplicate file names in
                # different directories, and here we are copying the files into
                # a single directory
                temp_name = random_filename.name()
                temp_name_ext = '{}.{}'.format(temp_name, rpd_file.extension)
                temp_full_file_name = os.path.join(dest_dir, temp_name_ext)

            rpd_file.temp_full_file_name = temp_full_file_name

            if not rpd_file.cache_full_file_name:
                if rpd_file.from_camera:
                    # Scenario 2
                    if not self.camera:
                        copy_succeeded = False
                        logging.error(
                            "Could not copy %s from the %s",
                            rpd_file.full_file_name, self.display_name
                        )
                        # self.problems.append(CameraFileReadProblem(name=rpd_file.name,
                        #                                            uri=rpd_file.get_uri()))
                        self.update_progress(rpd_file.size, rpd_file.size)
                    else:
                        copy_succeeded = self.copy_from_camera(rpd_file)
                else:
                    # Scenario 1
                    source = rpd_file.full_file_name
                    destination = rpd_file.temp_full_file_name
                    copy_succeeded = self.copy_from_filesystem(source, destination, rpd_file)

            # increment this amount regardless of whether the copy actually
            # succeeded or not. It's necessary to keep the user informed.
            self.total_downloaded += rpd_file.size

            mdata_exceptions = None

            if not copy_succeeded:
                rpd_file.status = DownloadStatus.download_failed
                logging.debug("Download failed for %s", rpd_file.full_file_name)
            else:
                if rpd_file.from_camera:
                    mdata_exceptions = copy_camera_file_metadata(
                        float(rpd_file.modification_time), temp_full_file_name
                    )
                else:
                    mdata_exceptions = copy_file_metadata(
                        rpd_file.full_file_name, temp_full_file_name
                    )

                # copy THM (video thumbnail file) if there is one
                if rpd_file.thm_full_name:
                    rpd_file.temp_thm_full_name = self.copy_associate_file(
                        # translators: refers to the video thumbnail file that some
                        # cameras generate -- it has a .THM file extension
                        rpd_file, temp_name, dest_dir, rpd_file.thm_full_name, _('video THM')
                    )

                # copy audio file if there is one
                if rpd_file.audio_file_full_name:
                    rpd_file.temp_audio_full_name = self.copy_associate_file(
                        rpd_file, temp_name, dest_dir, rpd_file.audio_file_full_name, _('audio')
                    )

                # copy XMP file if there is one
                if rpd_file.xmp_file_full_name:
                    rpd_file.temp_xmp_full_name = self.copy_associate_file(
                        rpd_file, temp_name, dest_dir, rpd_file.xmp_file_full_name, 'XMP'
                    )

                # copy Magic Lantern LOG file if there is one
                if rpd_file.log_file_full_name:
                    rpd_file.temp_log_full_name = self.copy_associate_file(
                        rpd_file, temp_name, dest_dir, rpd_file.log_file_full_name, 'LOG'
                    )

            download_count = idx + 1

            self.content = pickle.dumps(
                CopyFilesResults(
                    copy_succeeded=copy_succeeded,
                    rpd_file=rpd_file,
                    download_count=download_count,
                    mdata_exceptions=mdata_exceptions
                ),
                pickle.HIGHEST_PROTOCOL
            )
            self.send_message_to_sink()

        if len(self.problems):
            logging.debug('Encountered %s problems while copying from %s', len(self.problems),
                          self.display_name)
        self.send_problems()

        if self.camera is not None:
            self.camera.free_camera()

        self.disconnect_logging()
        self.send_finished_command()


if __name__ == "__main__":
    copy = CopyFilesWorker()

