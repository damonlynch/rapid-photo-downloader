#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2007-2012 Damon Lynch <damonlynch@gmail.com>

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

import os, re, datetime, string, collections

import multiprocessing
import logging
logger = multiprocessing.get_logger()

import problemnotification as pn

from generatenameconfig import *

from gettext import gettext as _


def convert_date_for_strftime(datetime_user_choice):
    try:
        return DATE_TIME_CONVERT[LIST_DATE_TIME_L2.index(datetime_user_choice)]
    except:
        raise PrefValueInvalidError(datetime_user_choice)


class PhotoName:
    """
    Generate the name of a photo. Used as a base class for generating names
    of videos, as well as subfolder names for both file types
    """

    def __init__(self, pref_list):
        self.pref_list = pref_list


        # Some of the next values are overwritten in derived classes
        self.strip_initial_period_from_extension = False
        self.strip_forward_slash = True
        self.L1_date_check = IMAGE_DATE #used in _get_date_component()
        self.component = pn.FILENAME_COMPONENT #used in error reporting


    def _get_values_from_pref_list(self):
        for i in range(0, len(self.pref_list), 3):
            yield (self.pref_list[i], self.pref_list[i+1], self.pref_list[i+2])

    def _get_date_component(self):
        """
        Returns portion of new file / subfolder name based on date time.
        If the date is missing, will attempt to use the fallback date.
        """

        # step 1: get the correct value from metadata
        if self.L1 == self.L1_date_check:
            if self.L2 == SUBSECONDS:
                d = self.rpd_file.metadata.sub_seconds(missing=None)
                if d is None:
                    self.rpd_file.problem.add_problem(self.component, pn.MISSING_METADATA, _(self.L2))
                    return ''
                else:
                    return d
            else:
                d = self.rpd_file.metadata.date_time(missing=None)

        elif self.L1 == TODAY:
            d = datetime.datetime.now()
        elif self.L1 == YESTERDAY:
            delta = datetime.timedelta(days = 1)
            d = datetime.datetime.now() - delta
        elif self.L1 == DOWNLOAD_TIME:
            d = self.rpd_file.download_start_time
        else:
            raise("Date options invalid")

        # step 2: if have a value, try to convert it to string format
        if d:
            try:
                return d.strftime(convert_date_for_strftime(self.L2))
            except:
                logger.warning("Exif date time value appears invalid for file %s", self.rpd_file.full_file_name)

        # step 3: handle a missing value using file modification time
        if self.rpd_file.modification_time:
            try:
                d = datetime.datetime.fromtimestamp(self.rpd_file.modification_time)
            except:
                self.rpd_file.add_problem(self.component, pn.INVALID_DATE_TIME, '')
                logger.error("Both file modification time and metadata date & time are invalid for file %s", self.rpd_file.full_file_name)
                return ''
        else:
            self.rpd_file.add_problem(self.component, pn.MISSING_METADATA, _(self.L1))
            return ''

        try:
            return d.strftime(convert_date_for_strftime(self.L2))
        except:
            self.rpd_file.add_problem(self.component, pn.INVALID_DATE_TIME, d)
            logger.error("Both file modification time and metadata date & time are invalid for file %s", self.rpd_file.full_file_name)
            return ''

    def _get_associated_file_extension(self, associate_file):
        """
        Generates extensions with correct capitalization for files like
        thumbnail or audio files.
        """
        if associate_file:
            extension = os.path.splitext(associate_file)[1]
            if self.L2 == UPPERCASE:
                extension = extension.upper()
            elif self.L2 == LOWERCASE:
                extension = extension.lower()
        else:
            extension = None
        return extension


    def _get_thm_extension(self):
        """
        Generates THM extension with correct capitalization, if needed
        """
        self.rpd_file.thm_extension = self._get_associated_file_extension(self.rpd_file.thm_full_name)

    def _get_audio_extension(self):
        """
        Generates audio extension with correct capitalization, if needed
        e.g. WAV or wav
        """
        self.rpd_file.audio_extension = self._get_associated_file_extension(self.rpd_file.audio_file_full_name)

    def _get_xmp_extension(self, extension):
        """
        Generates XMP extension with correct capitalization, if needed.
        """
        if self.rpd_file.temp_xmp_full_name:
            if self.L2 == UPPERCASE:
                self.rpd_file.xmp_extension = '.XMP'
            elif self.L2 == LOWERCASE:
                self.rpd_file.xmp_extension = '.xmp'
            else:
                # mimic capitalization of extension
                if extension.isupper():
                    self.rpd_file.xmp_extension = '.XMP'
                else:
                    self.rpd_file.xmp_extension = '.xmp'
        else:
            self.rpd_file.xmp_extension = None


    def _get_filename_component(self):
        """
        Returns portion of new file / subfolder name based on the file name
        """

        name, extension = os.path.splitext(self.rpd_file.name)

        if self.L1 == NAME_EXTENSION:
            filename = self.rpd_file.name
            self._get_thm_extension()
            self._get_audio_extension()
            self._get_xmp_extension(extension)
        elif self.L1 == NAME:
                filename = name
        elif self.L1 == EXTENSION:
            self._get_thm_extension()
            self._get_audio_extension()
            self._get_xmp_extension(extension)
            if extension:
                if not self.strip_initial_period_from_extension:
                    # keep the period / dot of the extension, so the user does not
                    # need to manually specify it
                    filename = extension
                else:
                    # having the period when this is used as a part of a subfolder name
                    # is a bad idea when it is at the start!
                    filename = extension[1:]
            else:
                self.rpd_file.add_problem(self.component, pn.MISSING_FILE_EXTENSION)
                return ""
        elif self.L1 == IMAGE_NUMBER or self.L1 == VIDEO_NUMBER:
            n = re.search("(?P<image_number>[0-9]+$)", name)
            if not n:
                self.rpd_file.add_problem(self.component, pn.MISSING_IMAGE_NUMBER)
                return ''
            else:
                image_number = n.group("image_number")

                if self.L2 == IMAGE_NUMBER_ALL:
                    filename = image_number
                elif self.L2 == IMAGE_NUMBER_1:
                    filename = image_number[-1]
                elif self.L2 == IMAGE_NUMBER_2:
                    filename = image_number[-2:]
                elif self.L2 == IMAGE_NUMBER_3:
                    filename = image_number[-3:]
                elif self.L2 == IMAGE_NUMBER_4:
                    filename = image_number[-4:]
        else:
            raise TypeError("Incorrect filename option")

        if self.L2 == UPPERCASE:
            filename = filename.upper()
        elif self.L2 == LOWERCASE:
            filename = filename.lower()

        return filename

    def _get_metadata_component(self):
        """
        Returns portion of new image / subfolder name based on the metadata

        Note: date time metadata found in _getDateComponent()
        """

        if self.L1 == APERTURE:
            v = self.rpd_file.metadata.aperture()
        elif self.L1 == ISO:
            v = self.rpd_file.metadata.iso()
        elif self.L1 == EXPOSURE_TIME:
            v = self.rpd_file.metadata.exposure_time(alternativeFormat=True)
        elif self.L1 == FOCAL_LENGTH:
            v = self.rpd_file.metadata.focal_length()
        elif self.L1 == CAMERA_MAKE:
            v = self.rpd_file.metadata.camera_make()
        elif self.L1 == CAMERA_MODEL:
            v = self.rpd_file.metadata.camera_model()
        elif self.L1 == SHORT_CAMERA_MODEL:
            v = self.rpd_file.metadata.short_camera_model()
        elif self.L1 == SHORT_CAMERA_MODEL_HYPHEN:
            v = self.rpd_file.metadata.short_camera_model(includeCharacters = "\-")
        elif self.L1 == SERIAL_NUMBER:
            v = self.rpd_file.metadata.camera_serial()
        elif self.L1 == SHUTTER_COUNT:
            v = self.rpd_file.metadata.shutter_count()
            if v:
                v = int(v)
                padding = LIST_SHUTTER_COUNT_L2.index(self.L2) + 3
                formatter = '%0' + str(padding) + "i"
                v = formatter % v
        elif self.L1 == FILE_NUMBER:
            v = self.rpd_file.metadata.file_number()
            if v and self.L2 == FILE_NUMBER_FOLDER:
                v = v[:3]
        elif self.L1 == OWNER_NAME:
            v = self.rpd_file.metadata.owner_name()
        elif self.L1 == ARTIST:
            v = self.rpd_file.metadata.artist()
        elif self.L1 == COPYRIGHT:
            v = self.rpd_file.metadata.copyright()
        else:
            raise TypeError("Invalid metadata option specified")
        if self.L1 in [CAMERA_MAKE, CAMERA_MODEL, SHORT_CAMERA_MODEL,
                       SHORT_CAMERA_MODEL_HYPHEN, OWNER_NAME, ARTIST,
                       COPYRIGHT]:
            if self.L2 == UPPERCASE:
                v = v.upper()
            elif self.L2 == LOWERCASE:
                v = v.lower()
        if not v:
            self.rpd_file.add_problem(self.component, pn.MISSING_METADATA, _(self.L1))
        return v

    def _calculate_letter_sequence(self, sequence):

        def _letters(x):
            """
            Adapted from algorithm at http://en.wikipedia.org/wiki/Hexavigesimal
            """
            v = ''
            while x > 25:
                r = x % 26
                x= x / 26 - 1
                v = string.lowercase[r] + v
            v = string.lowercase[x] + v

            return v


        v = _letters(sequence)
        if self.L2 == UPPERCASE:
            v = v.upper()

        return v

    def _format_sequence_no(self,  value,  amountToPad):
        padding = LIST_SEQUENCE_NUMBERS_L2.index(amountToPad) + 1
        formatter = '%0' + str(padding) + "i"
        return formatter % value

    def _get_downloads_today(self):
        return self._format_sequence_no(self.rpd_file.sequences.get_downloads_today(), self.L2)

    def _get_session_sequence_no(self):
        return self._format_sequence_no(self.rpd_file.sequences.get_session_sequence_no(), self.L2)

    def _get_stored_sequence_no(self):
        return self._format_sequence_no(self.rpd_file.sequences.get_stored_sequence_no(), self.L2)

    def _get_sequence_letter(self):
        return self._calculate_letter_sequence(self.rpd_file.sequences.get_sequence_letter())

    def _get_sequences_component(self):
        if self.L1 == DOWNLOAD_SEQ_NUMBER:
            return self._get_downloads_today()
        elif self.L1 == SESSION_SEQ_NUMBER:
            return self._get_session_sequence_no()
        elif self.L1 == STORED_SEQ_NUMBER:
            return self._get_stored_sequence_no()
        elif self.L1 == SEQUENCE_LETTER:
            return self._get_sequence_letter()


        #~ elif self.L1 == SUBFOLDER_SEQ_NUMBER:
            #~ return self._getSubfolderSequenceNo()



    def _get_component(self):
        try:
            if self.L0 == DATE_TIME:
                return self._get_date_component()
            elif self.L0 == TEXT:
                return self.L1
            elif self.L0 == FILENAME:
                return self._get_filename_component()
            elif self.L0 == METADATA:
                return self._get_metadata_component()
            elif self.L0 == SEQUENCES:
                return self._get_sequences_component()
            elif self.L0 == JOB_CODE:
                return self.rpd_file.job_code
            elif self.L0 == SEPARATOR:
                return os.sep
        except:
            self.rpd_file.add_problem(self.component, pn.ERROR_IN_GENERATION, _(self.L0))
            return ''


    def generate_name(self, rpd_file):
        self.rpd_file = rpd_file

        name = ''

        for self.L0, self.L1, self.L2 in self._get_values_from_pref_list():
            v = self._get_component()
            if v:
                name += v

        # remove any null characters - they are bad news in filenames
        name = name.replace('\x00', '')

        if self.rpd_file.strip_characters:
            for c in r'\:*?"<>|':
                name = name.replace(c, '')

        if self.strip_forward_slash:
            name = name.replace('/', '')

        name = name.strip()

        return name




class VideoName(PhotoName):
    def __init__(self, pref_list):
        PhotoName.__init__(self, pref_list)
        self.L1_date_check = VIDEO_DATE  #used in _get_date_component()

    def _get_metadata_component(self):
        """
        Returns portion of video / subfolder name based on the metadata

        Note: date time metadata found in _getDateComponent()
        """
        return get_video_metadata_component(self)

class PhotoSubfolder(PhotoName):
    """
    Generate subfolder names for photo files
    """

    def __init__(self, pref_list):
        self.pref_list = pref_list

        self.strip_extraneous_white_space = re.compile(r'\s*%s\s*' % os.sep)
        self.strip_initial_period_from_extension = True
        self.strip_forward_slash = False
        self.L1_date_check = IMAGE_DATE #used in _get_date_component()
        self.component = pn.SUBFOLDER_COMPONENT #used in error reporting

    def generate_name(self, rpd_file):

        subfolders = PhotoName.generate_name(self, rpd_file)

        # subfolder value must never start with a separator, or else any
        # os.path.join function call will fail to join a subfolder to its
        # parent folder
        if subfolders:
            if subfolders[0] == os.sep:
                subfolders = subfolders[1:]

        # remove any spaces before and after a directory name
        if subfolders and self.rpd_file.strip_characters:
            subfolders = self.strip_extraneous_white_space.sub(os.sep, subfolders)

        return subfolders




class VideoSubfolder(PhotoSubfolder):
    """
    Generate subfolder names for video files
    """

    def __init__(self, pref_list):
        PhotoSubfolder.__init__(self, pref_list)
        self.L1_date_check = VIDEO_DATE  #used in _get_date_component()


    def _get_metadata_component(self):
        """
        Returns portion of video / subfolder name based on the metadata

        Note: date time metadata found in _getDateComponent()
        """
        return get_video_metadata_component(self)

def get_video_metadata_component(video):
    """
    Returns portion of video / subfolder name based on the metadata

    This is outside of a class definition because of the inheritence
    hierarchy.
    """

    problem = None
    if video.L1 == CODEC:
        v = video.rpd_file.metadata.codec()
    elif video.L1 == WIDTH:
        v = video.rpd_file.metadata.width()
    elif video.L1 == HEIGHT:
        v = video.rpd_file.metadata.height()
    elif video.L1 == FPS:
        v = video.rpd_file.metadata.frames_per_second()
    elif video.L1 == LENGTH:
        v = video.rpd_file.metadata.length()
    else:
        raise TypeError("Invalid metadata option specified")
    if video.L1 in [CODEC]:
        if video.L2 == UPPERCASE:
            v = v.upper()
        elif video.L2 == LOWERCASE:
            v = v.lower()
    if not v:
        video.rpd_file.add_problem(video.component, pn.MISSING_METADATA, _(video.L1))
    return v

class Sequences:
    """
    Holds sequence numbers and letters used in generating filenames.
    """
    def __init__(self, downloads_today_tracker, stored_sequence_no):
        self.session_sequence_no = 0
        self.sequence_letter = -1
        self.downloads_today_tracker = downloads_today_tracker
        self.stored_sequence_no = stored_sequence_no
        self.matched_sequences = None

    def set_matched_sequence_value(self, matched_sequences):
        self.matched_sequences = matched_sequences

    def get_session_sequence_no(self):
        if self.matched_sequences is not None:
            return self.matched_sequences.session_sequence_no
        else:
            return self._get_session_sequence_no()

    def _get_session_sequence_no(self):
        return self.session_sequence_no + 1

    def get_sequence_letter(self):
        if self.matched_sequences is not None:
            return self.matched_sequences.sequence_letter
        else:
            return self._get_sequence_letter()

    def _get_sequence_letter(self):
        return self.sequence_letter + 1

    def increment(self, uses_session_sequece_no, uses_sequence_letter):
        if uses_session_sequece_no:
            self.session_sequence_no += 1
        if uses_sequence_letter:
            self.sequence_letter += 1

    def get_downloads_today(self):
        if self.matched_sequences is not None:
            return self.matched_sequences.downloads_today
        else:
            return self._get_downloads_today()

    def _get_downloads_today(self):
        v = self.downloads_today_tracker.get_downloads_today()
        if v == -1:
            return 1
        else:
            return v + 1

    def get_stored_sequence_no(self):
        if self.matched_sequences is not None:
            return self.matched_sequences.stored_sequence_no
        else:
            return self._get_stored_sequence_no()

    def _get_stored_sequence_no(self):
        # Must add 1 to the value, for historic reasons (that is how it used
        # to work)
        return self.stored_sequence_no + 1

    def create_matched_sequences(self):
        sequences = collections.namedtuple(
            'AssignedSequences',
            'session_sequence_no sequence_letter downloads_today stored_sequence_no'
            )
        sequences.session_sequence_no = self._get_session_sequence_no()
        sequences.sequence_letter = self._get_sequence_letter()
        sequences.downloads_today = self._get_downloads_today()
        sequences.stored_sequence_no = self._get_stored_sequence_no()
        return sequences
