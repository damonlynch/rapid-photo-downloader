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

"""
Generates names for files and folders, and renames (moves) files.

Runs as a daemon process.
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2011-2017, Damon Lynch"

import os
from datetime import datetime
from enum import Enum
from collections import namedtuple
import errno
import logging
import pickle
import sys
from typing import Union, Tuple, Dict, Optional
import locale
# Use the default locale as defined by the LANG variable
locale.setlocale(locale.LC_ALL, '')

from gettext import gettext as _

import raphodo.exiftool as exiftool
import raphodo.generatename as gn
from raphodo.preferences import DownloadsTodayTracker, Preferences
from raphodo.constants import (ConflictResolution, FileType, DownloadStatus, RenameAndMoveStatus)
from raphodo.interprocess import (RenameAndMoveFileData, RenameAndMoveFileResults, DaemonProcess)
from raphodo.rpdfile import RPDFile, Photo, Video
from raphodo.rpdsql import DownloadedSQL
from raphodo.utilities import stdchannel_redirected, datetime_roughly_equal, platform_c_maxint
from raphodo.problemnotification import (
    FileAlreadyExistsProblem, IdentifierAddedProblem, RenamingProblems, make_href,
    RenamingFileProblem, SubfolderCreationProblem, DuplicateFileWhenSyncingProblem,
    SameNameDifferentExif, RenamingAssociateFileProblem, FileMetadataLoadProblem,
    NoDataToNameProblem
)
from raphodo.storage import get_uri


class SyncRawJpegStatus(Enum):
    matching_pair = 1
    no_match = 2
    error_already_downloaded = 3
    error_datetime_mismatch = 4


SyncRawJpegMatch = namedtuple('SyncRawJpegMatch', 'status, sequence_number')
SyncRawJpegResult = namedtuple('SyncRawJpegResult', 'sequence_to_use, failed, photo_name, '
                                                    'photo_ext')
SyncRawJpegRecord = namedtuple('SyncRawJpegRecord', 'extension, date_time, sequence_number_used')


class SyncRawJpeg:
    """
    Match JPEG and RAW images so they have the same file names
    """

    def __init__(self):
        self.photos = {}  # type: Dict[str, SyncRawJpegRecord]

    def add_download(self, name: str,
                     extension: str,
                     date_time: datetime,
                     sequence_number_used: gn.MatchedSequences) -> None:

        if not isinstance(date_time, datetime):
            logging.debug("Rejecting %s for sync RAW jpeg matching because its"
                          "metadata date time does not exist", name)
            return

        if name not in self.photos:
            self.photos[name] = SyncRawJpegRecord(extension=[extension],
                                                  date_time=date_time,
                                                  sequence_number_used=sequence_number_used)
        else:
            if extension not in self.photos[name].extension:
                self.photos[name].extension.append(extension)

    def matching_pair(self, name: str,
                      extension: str,
                      date_time: datetime) -> SyncRawJpegMatch:
        """
        Checks to see if the image matches an image that has already been
        downloaded.
        
        Image name (minus extension), exif date time are checked. Exif
        date times should be within 30 seconds of each other, because
        need to allow for the fact that RAW and jpegs might not be
        written to the memory card(s) at the same time.

        :return: Returns SyncRawJpegStatus.error_already_downloaded
         and a sequence number if the name, extension, and exif values
         match (i.e. it has already been downloaded).

         Returns SyncRawJpegStatus.matching_pair and a sequence number
         if name and exif values match, but the extension is different
         (i.e. a matching RAW + JPG image).

         Returns SyncRawJpegStatus.error_datetime_mismatch and a
         sequence number of None if photos detected with the same
         filenames, but taken at different times.

         Returns SyncRawJpegStatus.no_match and a sequence number
         of None if no match
        """

        if name in self.photos:
            if datetime_roughly_equal(self.photos[name].date_time, date_time, 30):
                if extension in self.photos[name].extension:
                    return SyncRawJpegMatch(
                        SyncRawJpegStatus.error_already_downloaded,
                        self.photos[name].sequence_number_used
                    )
                else:
                    return SyncRawJpegMatch(
                        SyncRawJpegStatus.matching_pair,
                        self.photos[name].sequence_number_used
                    )
            else:
                return SyncRawJpegMatch(SyncRawJpegStatus.error_datetime_mismatch, None)
        return SyncRawJpegMatch(SyncRawJpegStatus.no_match, None)

    def ext_exif_date_time(self, name) -> Tuple[str, datetime]:
        """
        Returns first extension, and exif date time data for
        the already downloaded photo
        """

        return self.photos[name].extension[0], self.photos[name].date_time


def load_metadata(rpd_file: Union[Photo, Video],
                  et_process: exiftool.ExifTool,
                  problems: RenamingProblems) -> bool:
    """
    Loads the metadata for the file.

    :param rpd_file: photo or video
    :param et_process: the daemon ExifTool process
    :param problems: problems encountered renaming the file
    :return True if operation succeeded, false otherwise
    """
    if rpd_file.metadata is None:
        if not rpd_file.load_metadata(full_file_name=rpd_file.temp_full_file_name,
                                      et_process=et_process):
            # Error in reading metadata

            problems.append(FileMetadataLoadProblem(
                name=rpd_file.name, uri=rpd_file.get_uri(), file_type=rpd_file.title
            ))
            return False
    return True


def _generate_name(generator: Union[gn.PhotoName, gn.PhotoSubfolder, gn.VideoName,
                                    gn.VideoSubfolder],
                   rpd_file: Union[Photo, Video], 
                   et_process: exiftool.ExifTool,
                   problems: RenamingProblems) -> str:
    """
    Generate a subfolder or file name.
    
    :param generator: subfolder or file name generator, appropriate 
     for the file type (photo or video)
    :param rpd_file: file to work on 
    :param et_process:  the daemon ExifTool process
    :return: the name in string format, emptry string if error
    """
    do_generation = load_metadata(rpd_file, et_process, problems)

    if do_generation:
        value = generator.generate_name(rpd_file)
        if value is None:
            value = ''
    else:
        value = ''

    return value


def generate_subfolder(rpd_file: Union[Photo, Video],
                       et_process: exiftool.ExifTool,
                       problems: RenamingProblems) -> None:
    """
    Generate subfolder names e.g. 2015/201512
    
    :param rpd_file: file to work on
    :param et_process:  the daemon ExifTool process
    :param problems: problems encountered renaming the file
    """
    
    if rpd_file.file_type == FileType.photo:
        generator = gn.PhotoSubfolder(rpd_file.subfolder_pref_list, problems=problems)
    else:
        generator = gn.VideoSubfolder(rpd_file.subfolder_pref_list, problems=problems)

    rpd_file.download_subfolder = _generate_name(generator, rpd_file, et_process, problems)


def generate_name(rpd_file: Union[Photo, Video],
                  et_process: exiftool.ExifTool,
                  problems: RenamingProblems) -> None:
    """
    Generate file names e.g. 20150607-1.cr2

    :param rpd_file: file to work on
    :param et_process:  the daemon ExifTool process
    :param problems: problems encountered renaming the file
    """

    if rpd_file.file_type == FileType.photo:
        generator = gn.PhotoName(pref_list=rpd_file.name_pref_list, problems=problems)
    else:
        generator = gn.VideoName(pref_list=rpd_file.name_pref_list, problems=problems)

    rpd_file.download_name = _generate_name(generator, rpd_file, et_process, problems)


class RenameMoveFileWorker(DaemonProcess):
    """
    Generates names for files and folders, and renames (moves) files.

    Runs as a daemon process.
    """
    
    def __init__(self) -> None:
        super().__init__('Rename and Move')

        self.prefs = Preferences()

        self.sync_raw_jpeg = SyncRawJpeg()
        self.downloaded = DownloadedSQL()

        logging.debug("Start of day is set to %s", self.prefs.day_start)

        self.platform_c_maxint = platform_c_maxint()

        # This will be assigned again in run(), but initializing it here
        # clarifies any problems with type checking in an IDE
        self.problems = RenamingProblems()

    def notify_file_already_exists(self, rpd_file: Union[Photo, Video],
                                   identifier: Optional[str]=None) -> None:
        """
        Notify user that the download file already exists
        """

        # get information on when the existing file was last modified
        try:
            modification_time = os.path.getmtime(rpd_file.download_full_file_name)
            dt = datetime.fromtimestamp(modification_time)
            date = dt.strftime("%x")
            time = dt.strftime("%X")
        except Exception:
            logging.error(
                "Could not determine the file modification time of %s",
                rpd_file.download_full_file_name
            )
            date = time = ''

        source = rpd_file.get_souce_href()

        device = make_href(name=rpd_file.device_display_name, uri=rpd_file.device_uri)

        if not identifier:
            problem = FileAlreadyExistsProblem(
                file_type_capitalized=rpd_file.title_capitalized,
                file_type=rpd_file.title,
                name=rpd_file.download_name,
                uri=get_uri(full_file_name=rpd_file.download_full_file_name),
                source=source,
                device=device,
                date=date,
                time=time
            )

            rpd_file.status = DownloadStatus.download_failed
        else:
            problem = IdentifierAddedProblem(
                file_type_capitalized=rpd_file.title_capitalized,
                file_type=rpd_file.title,
                name=rpd_file.download_name,
                uri=get_uri(full_file_name=rpd_file.download_full_file_name),
                source=source,
                device=device,
                date=date,
                time=time,
                identifier=identifier
            )

            rpd_file.status = DownloadStatus.downloaded_with_warning

        self.problems.append(problem)

    def notify_download_failure_file_error(
            self, rpd_file: Union[Photo, Video], inst: Exception) -> None:
        """
        Handle cases where file failed to download
        """
        uri = get_uri(
                full_file_name=rpd_file.full_file_name, camera_details=rpd_file.camera_details
        )
        device = make_href(name=rpd_file.device_display_name, uri=rpd_file.device_uri)

        problem = RenamingFileProblem(
            file_type=rpd_file.title,
            destination=rpd_file.download_name,
            folder=rpd_file.download_path,
            name=rpd_file.name,
            uri=uri,
            device=device,
            exception=inst
        )
        self.problems.append(problem)

        rpd_file.status = DownloadStatus.download_failed

        try:
            msg = "Failed to create file {}: {} {}".format(
                rpd_file.download_full_file_name, inst.errno, inst.strerror
            )
            logging.error(msg)
        except AttributeError:
            logging.error(
                "Failed to create file %s: %s ", rpd_file.download_full_file_name, str(inst)
            )

    def download_file_exists(self, rpd_file: Union[Photo, Video]) -> bool:
        """
        Check how to handle a download file already existing
        """
        
        if self.prefs.conflict_resolution == ConflictResolution.add_identifier:
            logging.debug("Will add unique identifier to avoid duplicate filename for %s",
                          rpd_file.full_file_name)
            return True
        else:
            self.notify_file_already_exists(rpd_file)
            return False

    def same_name_different_exif(self, sync_photo_name: str,
                                 rpd_file: Union[Photo, Video]) -> None:
        """
        Notify the user that a file was already downloaded with the same
        name, but the exif information was different
        """
        
        i1_ext, i1_date_time = self.sync_raw_jpeg.ext_exif_date_time(sync_photo_name)
        image2_date_time = rpd_file.date_time()
        assert isinstance(i1_date_time, datetime)
        i1_date = i1_date_time.strftime("%x")
        i1_time = i1_date_time.strftime("%X")
        assert isinstance(image2_date_time, datetime)
        image2_date = image2_date_time.strftime("%x")
        image2_time = image2_date_time.strftime("%X")

        self.problems.append(
            SameNameDifferentExif(
                image1='%s%s' % (sync_photo_name, i1_ext),
                image1_date=i1_date,
                image1_time=i1_time,
                image2=rpd_file.name,
                image2_date=image2_date,
                image2_time=image2_time
            )
        )
        rpd_file.status = DownloadStatus.downloaded_with_warning

    def _move_associate_file(self, extension: str,
                             full_base_name: str,
                             temp_associate_file: str) -> str:
        """
        Move (rename) the associate file using the pre-generated name.
        
        Exceptions are not caught.

        :return: full path and filename
        """

        download_full_name = full_base_name + extension

        # move (rename) associate file
        # don't check to see if it already exists
        os.rename(temp_associate_file, download_full_name)

        return download_full_name

    def move_thm_file(self, rpd_file: Union[Photo, Video]) -> None:
        """
        Move (rename) the THM thumbnail file using the pre-generated name
        """

        try:
            if rpd_file.thm_extension:
                ext = rpd_file.thm_extension
            else:
                ext = '.THM'
        except AttributeError:
            ext = '.THM'

        try:
            rpd_file.download_thm_full_name = self._move_associate_file(
                extension=ext,
                full_base_name=rpd_file.download_full_base_name,
                temp_associate_file=rpd_file.temp_thm_full_name
            )
        except (OSError, FileNotFoundError) as e:
            self.problems.append(
                RenamingAssociateFileProblem(
                    source=make_href(
                        name=os.path.basename(rpd_file.download_thm_full_name),
                        uri=get_uri(
                            full_file_name=rpd_file.download_thm_full_name,
                            camera_details=rpd_file.camera_details
                        )
                    ),
                    exception=e
                )
            )

            logging.error("Failed to move video THM file %s", rpd_file.download_thm_full_name)

    def move_audio_file(self, rpd_file: Union[Photo, Video]) -> None:
        """
        Move (rename) the associate audio file using the pre-generated
        name
        """

        try:
            if rpd_file.audio_extension:
                ext = rpd_file.audio_extension
            else:
                ext = '.WAV'
        except AttributeError:
            ext = '.WAV'

        try:
            rpd_file.download_audio_full_name = self._move_associate_file(
                extension=ext,
                full_base_name=rpd_file.download_full_base_name,
                temp_associate_file=rpd_file.temp_audio_full_name
            )
        except (OSError, FileNotFoundError) as e:
            self.problems.append(
                RenamingAssociateFileProblem(
                    source=make_href(
                        name=os.path.basename(rpd_file.download_audio_full_name),
                        uri=get_uri(
                            full_file_name=rpd_file.download_audio_full_name,
                            camera_details=rpd_file.camera_details
                        )
                    ),
                    exception=e
                )
            )
            logging.error("Failed to move file's associated audio file %s",
                          rpd_file.download_audio_full_name)

    def move_xmp_file(self, rpd_file: Union[Photo, Video]) -> None:
        """
        Move (rename) the associate XMP file using the pre-generated
        name
        """

        try:
            if rpd_file.xmp_extension:
                ext = rpd_file.xmp_extension
            else:
                ext = '.XMP'
        except AttributeError:
            ext = '.XMP'

        try:
            rpd_file.download_xmp_full_name = self._move_associate_file(
                extension=ext,
                full_base_name=rpd_file.download_full_base_name,
                temp_associate_file=rpd_file.temp_xmp_full_name
            )
        except (OSError, FileNotFoundError) as e:
            self.problems.append(
                RenamingAssociateFileProblem(
                    source=make_href(
                        name=os.path.basename(rpd_file.download_xmp_full_name),
                        uri=get_uri(
                            full_file_name=rpd_file.download_xmp_full_name,
                            camera_details=rpd_file.camera_details
                        )
                    ),
                    exception=e
                )
            )
            logging.error("Failed to move file's associated XMP file %s",
                          rpd_file.download_xmp_full_name)

    def move_log_file(self, rpd_file: Union[Photo, Video]) -> None:
        """
        Move (rename) the associate XMP file using the pre-generated
        name
        """

        try:
            if rpd_file.log_extension:
                ext = rpd_file.log_extension
            else:
                ext = '.LOG'
        except AttributeError:
            ext = '.LOG'

        try:
            rpd_file.download_log_full_name = self._move_associate_file(
                extension=ext,
                full_base_name=rpd_file.download_full_base_name,
                temp_associate_file=rpd_file.temp_log_full_name
            )
        except (OSError, FileNotFoundError) as e:
            self.problems.append(
                RenamingAssociateFileProblem(
                    source=make_href(
                        name=os.path.basename(rpd_file.download_log_full_name),
                        uri=get_uri(
                            full_file_name=rpd_file.download_log_full_name,
                            camera_details=rpd_file.camera_details
                        )
                    ),
                    exception=e
                )
            )
            logging.error("Failed to move file's associated LOG file %s",
                          rpd_file.download_log_full_name)

    def check_for_fatal_name_generation_errors(self, rpd_file: Union[Photo, Video]) -> bool:
        """
        :return False if either the download subfolder or filename are
         blank, else returns True
         """

        if not rpd_file.download_subfolder or not rpd_file.download_name:
            if not rpd_file.download_subfolder and not rpd_file.download_name:
                area = _("subfolder and filename")
            elif not rpd_file.download_name:
                area = _("filename")
            else:
                area = _("subfolder")

            rpd_file.status = DownloadStatus.download_failed
            self.problems.append(
                NoDataToNameProblem(
                    name=rpd_file.name, uri=rpd_file.get_uri(), area=area, file_type=rpd_file.title
                )
            )
            return False
        else:
            return True

    def add_unique_identifier(self, rpd_file: Union[Photo, Video]) -> bool:
        """
        Adds a unique identifier like _1 to a filename, in ever
        incrementing values, until a unique filename is generated.

        :param rpd_file: the file being worked on
        :return: True if the operation was successful, else returns
         False
        """

        name = os.path.splitext(rpd_file.download_name)
        full_name = rpd_file.download_full_file_name
        while True:
            self.duplicate_files[full_name] = self.duplicate_files.get(full_name, 0) + 1
            identifier = '_%s' % self.duplicate_files[full_name]
            rpd_file.download_name = '{}{}{}'.format(name[0], identifier, name[1])
            rpd_file.download_full_file_name = os.path.join(
                rpd_file.download_path, rpd_file.download_name)

            try:
                if os.path.exists(rpd_file.download_full_file_name):
                    raise OSError(errno.EEXIST, "File exists: %s" %
                                  rpd_file.download_full_file_name)
                os.rename(rpd_file.temp_full_file_name, rpd_file.download_full_file_name)
                self.notify_file_already_exists(rpd_file, identifier)
                return True

            except OSError as inst:
                if inst.errno != errno.EEXIST:
                    self.notify_download_failure_file_error(rpd_file, inst)
                    return False

    def sync_raw_jpg(self, rpd_file: Union[Photo, Video]) -> SyncRawJpegResult:

        failed = False
        sequence_to_use = None
        photo_name, photo_ext = os.path.splitext(rpd_file.name)
        if not load_metadata(rpd_file, self.exiftool_process, self.problems):
            failed = True
            rpd_file.status = DownloadStatus.download_failed
            self.check_for_fatal_name_generation_errors(rpd_file)
        else:
            date_time = rpd_file.date_time()
            if not isinstance(date_time, datetime):
                failed = True
                rpd_file.status = DownloadStatus.download_failed
                self.check_for_fatal_name_generation_errors(rpd_file)
            else:
                matching_pair = self.sync_raw_jpeg.matching_pair(
                    name=photo_name, extension=photo_ext,
                    date_time=date_time
                )  # type: SyncRawJpegMatch
                sequence_to_use = matching_pair.sequence_number
                if matching_pair.status == SyncRawJpegStatus.error_already_downloaded:
                    # this exact file has already been
                    # downloaded (same extension, same filename,
                    # and roughly the same exif date time  info)
                    if self.prefs.conflict_resolution != ConflictResolution.add_identifier:
                        self.problems.append(
                            DuplicateFileWhenSyncingProblem(
                                name=rpd_file.name,
                                uri=rpd_file.get_uri(),
                                file_type=rpd_file.title,
                            )
                        )

                        rpd_file.status = DownloadStatus.download_failed
                        failed = True
                else:
                    self.sequences.matched_sequences = matching_pair.sequence_number
                    self.sequences.use_matched_sequences = self.sequences.matched_sequences is \
                                                           not None
                    if matching_pair.status == SyncRawJpegStatus.error_datetime_mismatch:
                        self.same_name_different_exif(photo_name, rpd_file)

        return SyncRawJpegResult(sequence_to_use, failed, photo_name, photo_ext)

    def prepare_rpd_file(self, rpd_file: Union[Photo, Video]) -> None:
        """
        Populate the RPDFile with download values used in subfolder
        and filename generation
        """

        if rpd_file.file_type == FileType.photo:
            rpd_file.download_folder = self.prefs.photo_download_folder
            rpd_file.subfolder_pref_list = self.prefs.photo_subfolder
            rpd_file.name_pref_list = self.prefs.photo_rename
        else:
            rpd_file.download_folder = self.prefs.video_download_folder
            rpd_file.subfolder_pref_list = self.prefs.video_subfolder
            rpd_file.name_pref_list = self.prefs.video_rename

    def process_rename_failure(self, rpd_file: RPDFile) -> None:
        try:
            os.remove(rpd_file.temp_full_file_name)
        except OSError:
            logging.error("Failed to delete temporary file %s", rpd_file.temp_full_file_name)

    def generate_names(self, rpd_file: Union[Photo, Video], synchronize_raw_jpg: bool) -> bool:

        rpd_file.strip_characters = self.prefs.strip_characters

        generate_subfolder(rpd_file, self.exiftool_process, self.problems)

        if rpd_file.download_subfolder:
            logging.debug("Generated subfolder name %s for file %s",
                          rpd_file.download_subfolder, rpd_file.name)

            self.sequences.stored_sequence_no = self.prefs.stored_sequence_no
            if self.must_synchronize_raw_jpg and rpd_file.file_type == FileType.video:
                self.sequences.use_matched_sequences = False

            rpd_file.sequences = self.sequences

            # generate the file name
            generate_name(rpd_file, self.exiftool_process, self.problems)

            if rpd_file.name_generation_problem:
                logging.warning(
                    "Encountered a problem generating file name for file %s",
                    rpd_file.name
                )
                rpd_file.status = DownloadStatus.downloaded_with_warning
            else:
                logging.debug(
                    "Generated file name %s for file %s", rpd_file.download_name, rpd_file.name
                )
        else:
            logging.error("Failed to generate subfolder name for file: %s", rpd_file.name)

        return self.check_for_fatal_name_generation_errors(rpd_file)

    def move_file(self, rpd_file: Union[Photo, Video]) -> bool:
        """
        Having generated the file name and subfolder names, move
        the file
        :param rpd_file: photo or video being worked on
        :return: True if move succeeded, False otherwise
        """

        move_succeeded = False

        rpd_file.download_path = os.path.join(rpd_file.download_folder, rpd_file.download_subfolder)
        rpd_file.download_full_file_name = os.path.join(
            rpd_file.download_path, rpd_file.download_name
        )
        rpd_file.download_full_base_name = os.path.splitext(rpd_file.download_full_file_name)[0]

        if not os.path.isdir(rpd_file.download_path):
            try:
                os.makedirs(rpd_file.download_path)
            except OSError as inst:
                if inst.errno != errno.EEXIST:
                    logging.error("Failed to create download subfolder: %s", rpd_file.download_path)
                    logging.error(inst)

                    problem = SubfolderCreationProblem(
                        folder=make_href(
                            name=rpd_file.download_subfolder,
                            uri=get_uri(path=rpd_file.download_path)
                        ),
                        exception=inst
                    )
                    self.problems.append(problem)

        # Move temp file to subfolder

        add_unique_identifier = False
        try:
            if os.path.exists(rpd_file.download_full_file_name):
                raise OSError(errno.EEXIST, "File exists: %s" % rpd_file.download_full_file_name)
            logging.debug(
                "Renaming %s to %s .....",
                rpd_file.temp_full_file_name, rpd_file.download_full_file_name
            )
            os.rename(rpd_file.temp_full_file_name, rpd_file.download_full_file_name)
            logging.debug("....successfully renamed file")
            move_succeeded = True
            if rpd_file.status != DownloadStatus.downloaded_with_warning:
                rpd_file.status = DownloadStatus.downloaded
        except OSError as inst:
            if inst.errno == errno.EEXIST:
                add_unique_identifier = self.download_file_exists(rpd_file)
            else:
                self.notify_download_failure_file_error(rpd_file, inst)
        except Exception as inst:
            # all other errors, including PermissionError
            self.notify_download_failure_file_error(rpd_file, inst)

        if add_unique_identifier:
            self.add_unique_identifier(rpd_file)

        return move_succeeded

    def process_file(self, rpd_file: Union[Photo, Video], download_count: int) -> bool:
        """
        Generate file & subfolder name, and move (rename) photo / video
        :param rpd_file: photo or video
        :param download_count: used to track the file being downloaded via a counter
        :return: success or otherwise of operation
        """

        move_succeeded = False

        self.prepare_rpd_file(rpd_file)

        synchronize_raw_jpg = self.must_synchronize_raw_jpg and rpd_file.file_type == FileType.photo

        if synchronize_raw_jpg:
            sync_result = self.sync_raw_jpg(rpd_file)

            if sync_result.failed:
                return False

        generation_succeeded = self.generate_names(rpd_file, synchronize_raw_jpg)

        if generation_succeeded:
            move_succeeded = self.move_file(rpd_file)

            logging.debug("Finished processing file: %s", download_count)

        if move_succeeded:
            if synchronize_raw_jpg:
                if sync_result.sequence_to_use is None:
                    sequence = self.sequences.create_matched_sequences()
                else:
                    sequence = sync_result.sequence_to_use
                self.sync_raw_jpeg.add_download(
                    name=sync_result.photo_name,
                    extension=sync_result.photo_ext,
                    date_time=rpd_file.date_time(),
                    sequence_number_used=sequence)

            if not synchronize_raw_jpg or (synchronize_raw_jpg and
                                           sync_result.sequence_to_use is None):

                if self.uses_sequence_session_no or self.uses_sequence_letter:
                    self.sequences.increment(
                        self.uses_sequence_session_no, self.uses_sequence_letter
                    )
                if self.uses_stored_sequence_no:
                    if self.prefs.stored_sequence_no == self.platform_c_maxint:
                        # wrap value if it exceeds the maximum size value that Qt can display
                        # in its spinbox
                        self.prefs.stored_sequence_no = 0
                    else:
                        self.prefs.stored_sequence_no += 1
                self.downloads_today_tracker.increment_downloads_today()

            if rpd_file.temp_thm_full_name:
                self.move_thm_file(rpd_file)

            if rpd_file.temp_audio_full_name:
                self.move_audio_file(rpd_file)

            if rpd_file.temp_xmp_full_name:
                self.move_xmp_file(rpd_file)

            if rpd_file.temp_log_full_name:
                self.move_log_file(rpd_file)

        return move_succeeded

    def initialise_downloads_today_stored_number(self) -> None:
        """
        Initialize (or reinitialize) Downloads Today and Stored No
        sequence values from the program preferences.
        """

        # Synchronize QSettings instance in preferences class
        self.prefs.sync()

        # Track downloads today, using a class whose purpose is to
        # take the value in the user prefs, increment, and then
        # finally used to update the prefs
        self.downloads_today_tracker = DownloadsTodayTracker(
            day_start=self.prefs.day_start,
            downloads_today=self.prefs.downloads_today
        )

    def initialise_sequence_number_usage(self) -> None:
        """
        Determine what type of sequence numbers are being used in file name generation
        """

        self.uses_sequence_session_no = self.prefs.any_pref_uses_session_sequence_no()
        self.uses_sequence_letter = self.prefs.any_pref_uses_sequence_letter_value()
        self.uses_stored_sequence_no = self.prefs.any_pref_uses_stored_sequence_no()

    def run(self) -> None:
        """
        Generate subfolder and filename, and attempt to move the file
        from its temporary directory.

        Move video THM and/or audio file if there is one.

        If successful, increment sequence values.

        Report any success or failure.
        """
        i = 0

        # Dict of filename keys and int values used to track ints to add as
        # suffixes to duplicate files
        self.duplicate_files = {}

        self.initialise_downloads_today_stored_number()

        self.sequences = gn.Sequences(
            self.downloads_today_tracker, self.prefs.stored_sequence_no
        )

        with stdchannel_redirected(sys.stderr, os.devnull):
            with exiftool.ExifTool() as self.exiftool_process:
                while True:
                    if i:
                        logging.debug("Finished %s. Getting next task.", i)

                    # rename file and move to generated subfolder
                    directive, content = self.receiver.recv_multipart()

                    self.check_for_command(directive, content)

                    data = pickle.loads(content) # type: RenameAndMoveFileData
                    if data.message == RenameAndMoveStatus.download_started:

                        # reinitialize downloads today and stored sequence number
                        # in case the user has updated them via the user interface
                        self.initialise_downloads_today_stored_number()
                        self.sequences.downloads_today_tracker = self.downloads_today_tracker
                        self.sequences.stored_sequence_no = self.prefs.stored_sequence_no

                        dl_today = self.downloads_today_tracker.get_or_reset_downloads_today()
                        logging.debug("Completed downloads today: %s", dl_today)

                        self.initialise_sequence_number_usage()

                        self.must_synchronize_raw_jpg = self.prefs.must_synchronize_raw_jpg()

                        self.problems = RenamingProblems()

                    elif data.message == RenameAndMoveStatus.download_completed:
                        if len(self.problems):
                            self.content = pickle.dumps(
                                RenameAndMoveFileResults(problems=self.problems),
                                pickle.HIGHEST_PROTOCOL
                            )
                            self.send_message_to_sink()

                        # Ask main application process to update prefs with stored
                        # sequence number and downloads today values. Cannot do it
                        # here because to save QSettings, QApplication should be
                        # used.
                        self.content = pickle.dumps(
                            RenameAndMoveFileResults(
                                stored_sequence_no=self.sequences.stored_sequence_no,
                                downloads_today=self.downloads_today_tracker.downloads_today
                            ),
                            pickle.HIGHEST_PROTOCOL
                        )
                        dl_today = self.downloads_today_tracker.get_or_reset_downloads_today()
                        logging.debug("Downloads today: %s", dl_today)
                        self.send_message_to_sink()
                    else:
                        rpd_file = data.rpd_file
                        download_count = data.download_count

                        if data.download_succeeded:
                            move_succeeded = self.process_file(rpd_file, download_count)
                            if not move_succeeded:
                                self.process_rename_failure(rpd_file)
                            else:
                                # Record file as downloaded in SQLite database
                                self.downloaded.add_downloaded_file(
                                    name=rpd_file.name, size=rpd_file.size,
                                    modification_time=rpd_file.modification_time,
                                    download_full_file_name=rpd_file.download_full_file_name
                                )
                        else:
                            move_succeeded = False

                        rpd_file.metadata = None
                        self.content = pickle.dumps(
                            RenameAndMoveFileResults(
                                move_succeeded=move_succeeded,
                                rpd_file=rpd_file,
                                download_count=download_count
                            ),
                            pickle.HIGHEST_PROTOCOL
                        )
                        self.send_message_to_sink()

                        i += 1


if __name__ == '__main__':
    rename = RenameMoveFileWorker()
    rename.run()