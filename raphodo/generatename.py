# SPDX-FileCopyrightText: Copyright 2007-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

import contextlib
import locale
import logging
import os
import re
from collections import namedtuple
from datetime import datetime, timedelta

with contextlib.suppress(locale.Error):
    # Use the default locale as defined by the LANG variable
    locale.setlocale(locale.LC_ALL, "")

from raphodo.generatenameconfig import (
    APERTURE,
    ARTIST,
    CAMERA_MAKE,
    CAMERA_MODEL,
    CODEC,
    COPYRIGHT,
    DATE_TIME,
    DATE_TIME_CONVERT,
    DOWNLOAD_SEQ_NUMBER,
    DOWNLOAD_TIME,
    EXPOSURE_TIME,
    EXTENSION,
    FILE_NUMBER,
    FILE_NUMBER_FOLDER,
    FILENAME,
    FOCAL_LENGTH,
    FPS,
    HEIGHT,
    IMAGE_DATE,
    IMAGE_NUMBER,
    IMAGE_NUMBER_1,
    IMAGE_NUMBER_2,
    IMAGE_NUMBER_3,
    IMAGE_NUMBER_4,
    IMAGE_NUMBER_ALL,
    ISO,
    JOB_CODE,
    LENGTH,
    LIST_DATE_TIME_L2,
    LIST_SEQUENCE_NUMBERS_L2,
    LIST_SHUTTER_COUNT_L2,
    LOWERCASE,
    METADATA,
    NAME,
    OWNER_NAME,
    SEPARATOR,
    SEQUENCE_LETTER,
    SEQUENCES,
    SERIAL_NUMBER,
    SESSION_SEQ_NUMBER,
    SHORT_CAMERA_MODEL,
    SHORT_CAMERA_MODEL_HYPHEN,
    SHUTTER_COUNT,
    STORED_SEQ_NUMBER,
    SUBSECONDS,
    TEXT,
    TODAY,
    UPPERCASE,
    VIDEO_DATE,
    VIDEO_NUMBER,
    WIDTH,
    YESTERDAY,
    PrefValueInvalidError,
)
from raphodo.internationalisation.install import install_gettext
from raphodo.prefs.preferences import DownloadsTodayTracker
from raphodo.problemnotification import (
    FilenameNotFullyGeneratedProblem,
    FolderNotFullyGeneratedProblemProblem,
    RenamingProblems,
    make_href,
)
from raphodo.rpdfile import RPDFile
from raphodo.storage.storage import get_uri
from raphodo.tools.utilities import letters

install_gettext()

MatchedSequences = namedtuple(
    "MatchedSequences",
    "session_sequence_no, sequence_letter, downloads_today, stored_sequence_no",
)


def convert_date_for_strftime(datetime_user_choice):
    try:
        return DATE_TIME_CONVERT[LIST_DATE_TIME_L2.index(datetime_user_choice)]
    except KeyError:
        raise PrefValueInvalidError(datetime_user_choice)


class abstract_attribute:
    """
    http://stackoverflow.com/questions/32536176/how-to-define-lazy-variable-in-python-which-will-raise-notimplementederror-for-a/32536493
    """

    def __get__(self, obj, type):
        # Now we will iterate over the names on the class,
        # and all its superclasses, and try to find the attribute
        # name for this descriptor
        # traverse the parents in the method resolution order
        for cls in type.__mro__:
            # for each cls thus, see what attributes they set
            for name, value in cls.__dict__.items():
                # we found ourselves here
                if value is self:
                    # if the property gets accessed as Child.variable,
                    # obj will be done. For this case
                    # If accessed as a_child.variable, the class Child is
                    # in the type, and a_child in the obj.
                    this_obj = obj if obj else type

                    raise NotImplementedError(
                        f"{this_obj!r} does not have the attribute {name!r} "
                        f"(abstract from class {cls.__name__!r})"
                    )

        # we did not find a match, should be rare, but prepare for it
        raise NotImplementedError(
            f"{type.__name__} does not set the abstract attribute <unknown>"
        )


GenerationErrors = (
    FilenameNotFullyGeneratedProblem | FolderNotFullyGeneratedProblemProblem
)


class NameGeneration:
    """
    Generate the name of a photo. Used as a base class for generating names
    of videos, as well as subfolder names for both file types
    """

    def __init__(
        self, pref_list: list[str], problems: RenamingProblems | None = None
    ) -> None:
        self.pref_list = pref_list
        self.no_metadata = False

        self.problems = problems
        self.problem: GenerationErrors = abstract_attribute()

        self.strip_forward_slash = abstract_attribute()
        self.add_extension = abstract_attribute()
        self.L1_date_check = abstract_attribute()

        self.L0 = ""
        self.L1 = ""
        self.L2 = ""

    def _get_values_from_pref_list(self):
        for i in range(0, len(self.pref_list), 3):
            yield (self.pref_list[i], self.pref_list[i + 1], self.pref_list[i + 2])

    def _get_date_component(self) -> str:
        """
        Returns portion of new file / subfolder name based on date time.
        If the date is missing, will attempt to use the fallback date.
        """

        # step 1: get the correct value from metadata
        if self.L1 == self.L1_date_check:  # noqa: SIM300
            if self.no_metadata:
                if self.L2 == SUBSECONDS:
                    d = datetime.fromtimestamp(self.rpd_file.modification_time)
                    if not d.microsecond:
                        d = "00"
                    try:
                        d = str(round(int(str(d.microsecond)[:3]) / 10))
                    except Exception:
                        d = "00"
                    return d
                d = datetime.fromtimestamp(self.rpd_file.ctime)
            else:
                if self.L2 == SUBSECONDS:
                    d = self.rpd_file.metadata.sub_seconds(missing=None)
                    if d is None:
                        self.problem.missing_metadata.append(_(self.L2))
                        return ""
                    else:
                        return d
                else:
                    d = self.rpd_file.date_time(missing=None)

        elif self.L1 == TODAY:
            d = datetime.now()
        elif self.L1 == YESTERDAY:
            delta = timedelta(days=1)
            d = datetime.now() - delta
        elif self.L1 == DOWNLOAD_TIME:
            d = self.rpd_file.download_start_time
        else:
            raise TypeError("Date options invalid")

        # step 2: if have a value, try to convert it to string format
        if d:
            try:
                return d.strftime(convert_date_for_strftime(self.L2))
            except Exception as e:
                logging.warning(
                    "Problem converting date/time value for file %s",
                    self.rpd_file.full_file_name,
                )
                self.problem.bad_converstion_date_time = True
                self.problem.bad_conversion_exception = e

        # step 3: handle a missing value using file modification time
        if self.rpd_file.modification_time:
            try:
                d = datetime.fromtimestamp(self.rpd_file.modification_time)
            except Exception:
                logging.error(
                    "Both file modification time and metadata date & time are invalid "
                    "for file %s",
                    self.rpd_file.full_file_name,
                )
                self.problem.invalid_date_time = True
                return ""
        else:
            self.problem.missing_metadata.append(_(self.L1))
            return ""

        try:
            return d.strftime(convert_date_for_strftime(self.L2))
        except Exception:
            logging.error(
                "Both file modification time and metadata date & time are invalid for "
                "file %s",
                self.rpd_file.full_file_name,
            )
            self.problem.invalid_date_time = True
            return ""

    def _get_associated_file_extension(self, associate_file):
        """
        Generates extensions with correct capitalization for files like
        thumbnail or audio files.
        """

        if not associate_file:
            return None

        extension = os.path.splitext(associate_file)[1]
        if self.rpd_file.generate_extension_case == UPPERCASE:
            extension = extension.upper()
        elif self.rpd_file.generate_extension_case == LOWERCASE:
            extension = extension.lower()
        # else keep extension case the same as what it originally was
        return extension

    def _get_thm_extension(self) -> None:
        """
        Generates THM extension with correct capitalization, if needed
        """
        self.rpd_file.thm_extension = self._get_associated_file_extension(
            self.rpd_file.thm_full_name
        )

    def _get_audio_extension(self) -> None:
        """
        Generates audio extension with correct capitalization, if needed
        e.g. WAV or wav
        """
        self.rpd_file.audio_extension = self._get_associated_file_extension(
            self.rpd_file.audio_file_full_name
        )

    def _get_xmp_extension(self) -> None:
        """
        Generates XMP extension with correct capitalization, if needed.
        """

        self.rpd_file.xmp_extension = self._get_associated_file_extension(
            self.rpd_file.xmp_file_full_name
        )

    def _get_log_extension(self) -> None:
        """
        Generates LOG extension with correct capitalization, if needed.
        """

        self.rpd_file.log_extension = self._get_associated_file_extension(
            self.rpd_file.log_file_full_name
        )

    def _get_filename_component(self):
        """
        Returns portion of new file / subfolder name based on the file name
        """

        name, extension = os.path.splitext(self.rpd_file.name)

        if self.L1 == NAME:
            filename = name
        elif self.L1 == EXTENSION:
            # Used in subfolder name generation
            if extension:
                # having the period when this is used as a part of a
                # subfolder name
                # is a bad idea when it is at the start!
                filename = extension[1:]
            else:
                self.problem.missing_extension = True
                return ""
        elif self.L1 == IMAGE_NUMBER or self.L1 == VIDEO_NUMBER:
            n = re.search("(?P<image_number>[0-9]+$)", name)
            if not n:
                self.problem.missing_image_no = True
                return ""
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
                else:
                    assert self.L2 == IMAGE_NUMBER_4
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
            v = self.rpd_file.metadata.exposure_time(alternative_format=True)
        elif self.L1 == FOCAL_LENGTH:
            v = self.rpd_file.metadata.focal_length()
        elif self.L1 == CAMERA_MAKE:
            v = self.rpd_file.metadata.camera_make()
        elif self.L1 == CAMERA_MODEL:
            v = self.rpd_file.metadata.camera_model()
        elif self.L1 == SHORT_CAMERA_MODEL:
            v = self.rpd_file.metadata.short_camera_model()
        elif self.L1 == SHORT_CAMERA_MODEL_HYPHEN:
            v = self.rpd_file.metadata.short_camera_model(include_characters="-")
        elif self.L1 == SERIAL_NUMBER:
            v = self.rpd_file.metadata.camera_serial()
        elif self.L1 == SHUTTER_COUNT:
            v = self.rpd_file.metadata.shutter_count()
            if v:
                v = int(v)
                padding = LIST_SHUTTER_COUNT_L2.index(self.L2) + 3
                formatter = "%0" + str(padding) + "i"
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
        if self.L1 in (
            CAMERA_MAKE,
            CAMERA_MODEL,
            SHORT_CAMERA_MODEL,
            SHORT_CAMERA_MODEL_HYPHEN,
            OWNER_NAME,
            ARTIST,
            COPYRIGHT,
        ):
            if self.L2 == UPPERCASE:
                v = v.upper()
            elif self.L2 == LOWERCASE:
                v = v.lower()
        if not v:
            self.problem.missing_metadata.append(_(self.L1))
        return v

    def _calculate_letter_sequence(self, sequence):
        v = letters(sequence)
        if self.L2 == UPPERCASE:
            v = v.upper()

        return v

    def _format_sequence_no(self, value, amountToPad):
        padding = LIST_SEQUENCE_NUMBERS_L2.index(amountToPad) + 1
        formatter = "%0" + str(padding) + "i"
        return formatter % value

    def _get_downloads_today(self):
        return self._format_sequence_no(
            self.rpd_file.sequences.downloads_today, self.L2
        )

    def _get_session_sequence_no(self):
        return self._format_sequence_no(
            self.rpd_file.sequences.session_sequence_no, self.L2
        )

    def _get_stored_sequence_no(self):
        return self._format_sequence_no(
            self.rpd_file.sequences.stored_sequence_no, self.L2
        )

    def _get_sequence_letter(self):
        return self._calculate_letter_sequence(self.rpd_file.sequences.sequence_letter)

    def _get_sequences_component(self):
        if self.L1 == DOWNLOAD_SEQ_NUMBER:
            return self._get_downloads_today()
        elif self.L1 == SESSION_SEQ_NUMBER:
            return self._get_session_sequence_no()
        elif self.L1 == STORED_SEQ_NUMBER:
            return self._get_stored_sequence_no()
        elif self.L1 == SEQUENCE_LETTER:
            return self._get_sequence_letter()

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
        except Exception as e:
            self.problem.component_problem = _(self.L0)
            self.problem.component_exception = e
            return ""

    def filter_strip_characters(self, name: str) -> str:
        """
        Filter out unwanted chacters from file and subfolder names
        :param name: full name or name component
        :return: filtered name
        """

        # remove any null characters - they are bad news in file names
        name = name.replace("\x00", "")

        # the user could potentially copy and paste a block of text with a carriage /
        # line return
        name = name.replace("\n", "")

        if self.rpd_file.strip_characters:
            for c in r'\:*?"<>|':
                name = name.replace(c, "")

        if self.strip_forward_slash:
            name = name.replace("/", "")
        return name

    def _destination(self, rpd_file: RPDFile, name: str) -> str:
        # implement in subclass
        return ""

    def _filter_name(self, name: str, parts: bool) -> str:
        # implement in subclass if need be
        return name

    def generate_name(
        self, rpd_file: RPDFile, parts: bool | None = False
    ) -> str | list[str]:
        """
        Generate subfolder name(s), and photo/video filenames

        :param rpd_file: rpd file for the name to generate
        :param parts: if True, return string components in a list
        :return: complete string or list of name components
        """

        self.rpd_file = rpd_file

        name = [] if parts else ""

        for self.L0, self.L1, self.L2 in self._get_values_from_pref_list():
            v = self._get_component()
            if parts:
                name.append(self.filter_strip_characters(v))
            elif v:
                name += v

        if not parts:
            name = self.filter_strip_characters(name)
            # strip any white space from the beginning and end of the name
            name = name.strip()
        elif name:
            # likewise, strip any white space from the beginning and end of the name
            name[0] = name[0].lstrip()
            name[-1] = name[-1].rstrip()

        if self.add_extension:
            case = rpd_file.generate_extension_case
            extension = os.path.splitext(rpd_file.name)[1]
            if case == UPPERCASE:
                extension = extension.upper()
            elif case == LOWERCASE:
                extension = extension.lower()
            if parts:
                name.append(extension)
            else:
                name += extension

            self._get_thm_extension()
            self._get_audio_extension()
            self._get_xmp_extension()
            self._get_log_extension()

        name = self._filter_name(name, parts)

        if self.problem.has_error():
            rpd_file.name_generation_problem = True

            if self.problems is not None:
                self.problem.destination = self._destination(
                    rpd_file=rpd_file, name=name
                )
                self.problem.file_type = rpd_file.title
                self.problem.source = rpd_file.get_souce_href()
                self.problems.append(self.problem)

        return name


class PhotoName(NameGeneration):
    """
    Generate filenames for photos
    """

    def __init__(
        self, pref_list: list[str], problems: RenamingProblems | None = None
    ) -> None:
        super().__init__(pref_list, problems)

        self.problem = FilenameNotFullyGeneratedProblem()

        self.strip_forward_slash = True
        self.add_extension = True
        self.L1_date_check = IMAGE_DATE  # used in _get_date_component()

    def _destination(self, rpd_file: RPDFile, name: str) -> str:
        if rpd_file.download_subfolder:
            return make_href(
                name=name,
                uri=get_uri(
                    full_file_name=os.path.join(
                        rpd_file.download_folder, rpd_file.download_subfolder, name
                    )
                ),
            )
        else:
            return name


class VideoName(PhotoName):
    """
    Generate filenames for videos
    """

    def __init__(
        self, pref_list: list[str], problems: RenamingProblems | None = None
    ) -> None:
        super().__init__(pref_list, problems)

        self.L1_date_check = VIDEO_DATE  # used in _get_date_component()

    def _get_metadata_component(self):
        """
        Returns portion of video / subfolder name based on the metadata

        Note: date time metadata found in _getDateComponent()
        """
        return get_video_metadata_component(self)


class PhotoSubfolder(NameGeneration):
    """
    Generate subfolder names for photo files
    """

    def __init__(
        self,
        pref_list: list[str],
        problems: RenamingProblems | None = None,
        no_metadata: bool | None = False,
    ) -> None:
        """
        :param pref_list: subfolder generation preferences list
        :param no_metadata: if True, halt as soon as the need for metadata
        or a job code or sequence number becomes necessary
        """

        super().__init__(pref_list, problems)

        if no_metadata:
            self.pref_list = truncate_before_unwanted_subfolder_component(pref_list)
        else:
            self.pref_list = pref_list

        self.no_metadata = no_metadata

        self.problem = FolderNotFullyGeneratedProblemProblem()

        self.strip_extraneous_white_space = re.compile(r"\s*%s\s*" % os.sep)
        self.strip_forward_slash = False
        self.add_extension = False
        self.L1_date_check = IMAGE_DATE  # used in _get_date_component()

    def _filter_name(self, name: str, parts: bool) -> str:
        if not parts:
            return self.filter_subfolder_characters(name)
        return name

    def _destination(self, rpd_file: RPDFile, name: str) -> str:
        return make_href(
            name=name, uri=get_uri(path=os.path.join(rpd_file.download_folder, name))
        )

    def filter_subfolder_characters(self, subfolders: str) -> str:
        """
        Remove unwanted characters specific to the generation of subfolders
        :param subfolders: the complete string containing the subfolders
         (not component parts)
        :return: filtered string
        """

        # subfolder value must never start with a separator, or else any
        # os.path.join function call will fail to join a subfolder to its
        # parent folder
        if subfolders and subfolders[0] == os.sep:
            subfolders = subfolders[1:]

        # remove any spaces before and after a directory name
        if subfolders and self.rpd_file.strip_characters:
            subfolders = self.strip_extraneous_white_space.sub(os.sep, subfolders)

        # remove any repeated directory separators
        double_sep = os.sep * 2
        subfolders = subfolders.replace(double_sep, os.sep)

        # remove any trailing directory separators
        while subfolders.endswith(os.sep):
            subfolders = subfolders[:-1]

        return subfolders


class VideoSubfolder(PhotoSubfolder):
    """
    Generate subfolder names for video files
    """

    def __init__(
        self,
        pref_list: list[str],
        problems: RenamingProblems | None = None,
        no_metadata: bool = False,
    ) -> None:
        """
        :param pref_list: subfolder generation preferences list
        :param no_metadata: if True, halt as soon as the need for metadata
        or a job code or sequence number becomes necessary
        """
        super().__init__(pref_list, problems, no_metadata)
        self.L1_date_check = VIDEO_DATE  # used in _get_date_component()

    def _get_metadata_component(self):
        """
        Returns portion of video / subfolder name based on the metadata

        Note: date time metadata found in _getDateComponent()
        """
        return get_video_metadata_component(self)


def truncate_before_unwanted_subfolder_component(pref_list: list[str]) -> list[str]:
    r"""
    truncate the preferences list to remove any subfolder element that
    contains a metadata or a job code or sequence number

    :param pref_list: subfolder prefs list
    :return: truncated list

    >>> pref_list = PHOTO_SUBFOLDER_MENU_DEFAULTS_CONV[0]
    >>> print(truncate_before_unwanted_subfolder_component(pref_list))
    ... # doctest: +NORMALIZE_WHITESPACE
    ['Date time', 'Image date', 'YYYY', '/', '', '', 'Date time', 'Image date',
    'YYYYMMDD']
    >>> pref_list = PHOTO_SUBFOLDER_MENU_DEFAULTS_CONV[1]
    >>> print(truncate_before_unwanted_subfolder_component(pref_list))
    ... # doctest: +NORMALIZE_WHITESPACE
    ['Date time', 'Image date', 'YYYY', '/', '', '', 'Date time', 'Image date',
    'YYYY-MM-DD']
    >>> pref_list = PHOTO_SUBFOLDER_MENU_DEFAULTS_CONV[2]
    >>> print(truncate_before_unwanted_subfolder_component(pref_list))
    ... # doctest: +NORMALIZE_WHITESPACE
    ['Date time', 'Image date', 'YYYY', '/', '', '', 'Date time', 'Image date',
    'YYYY_MM_DD']
    >>> pref_list = PHOTO_SUBFOLDER_MENU_DEFAULTS_CONV[3]
    >>> print(truncate_before_unwanted_subfolder_component(pref_list))
    ['Date time', 'Image date', 'YYYY']
    >>> pref_list = PHOTO_SUBFOLDER_MENU_DEFAULTS_CONV[4])
    >>> print(truncate_before_unwanted_subfolder_component(pref_list)
    ... # doctest: +NORMALIZE_WHITESPACE
    ['Date time', 'Image date', 'YYYY', '/', '', '', 'Date time', 'Image date', 'YYYY',
    'Date time', 'Image date', 'MM']
    >>> print(truncate_before_unwanted_subfolder_component([JOB_CODE, '', '',]))
    []
    >>> pl = [DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[11]]
    >>> print(truncate_before_unwanted_subfolder_component(pl))
    ['Date time', 'Image date', 'YYYY']
    """

    rl = [pref_list[i] for i in range(0, len(pref_list), 3)]
    truncate = -1
    for idx, value in enumerate(rl):
        if value in (METADATA, SEQUENCES, JOB_CODE):
            break
        if idx == len(rl) - 1:
            truncate = idx + 1
        elif value == SEPARATOR:
            truncate = idx

    if truncate >= 0:
        return pref_list[: truncate * 3]
    return []


def get_video_metadata_component(video: VideoSubfolder | VideoName):
    """
    Returns portion of video / subfolder name based on the metadata

    This is outside of a class definition because of the inheritance
    hierarchy.
    """

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
        video.problem.missing_metadata.append(_(video.L1))
    return v


class Sequences:
    """
    Stores sequence numbers and letters used in generating file names.
    """

    def __init__(
        self, downloads_today_tracker: DownloadsTodayTracker, stored_sequence_no: int
    ) -> None:
        self._session_sequence_no = 0
        self._sequence_letter = -1
        self.downloads_today_tracker = downloads_today_tracker
        self._stored_sequence_no = stored_sequence_no
        self.matched_sequences = None
        self.use_matched_sequences = False

    @property
    def session_sequence_no(self) -> int:
        if self.use_matched_sequences:
            return self.matched_sequences.session_sequence_no
        else:
            return self._session_sequence_no + 1

    @property
    def sequence_letter(self) -> int:
        if self.use_matched_sequences:
            return self.matched_sequences.sequence_letter
        else:
            return self._sequence_letter + 1

    def increment(self, uses_session_sequence_no, uses_sequence_letter) -> None:
        if uses_session_sequence_no:
            self._session_sequence_no += 1
        if uses_sequence_letter:
            self._sequence_letter += 1

    @property
    def downloads_today(self) -> int:
        if self.use_matched_sequences:
            return self.matched_sequences.downloads_today
        else:
            return self._get_downloads_today()

    def _get_downloads_today(self) -> int:
        v = self.downloads_today_tracker.get_downloads_today()
        if v == -1:
            return 1
        else:
            return v + 1

    @property
    def stored_sequence_no(self) -> int:
        if self.use_matched_sequences:
            return self.matched_sequences.stored_sequence_no
        else:
            return self._stored_sequence_no + 1

    @stored_sequence_no.setter
    def stored_sequence_no(self, value: int) -> None:
        self._stored_sequence_no = value

    def create_matched_sequences(self) -> MatchedSequences:
        return MatchedSequences(
            session_sequence_no=self._session_sequence_no + 1,
            sequence_letter=self._sequence_letter + 1,
            downloads_today=self._get_downloads_today(),
            stored_sequence_no=self._stored_sequence_no + 1,
        )
