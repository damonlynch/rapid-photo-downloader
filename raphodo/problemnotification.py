# Copyright (C) 2010-2017 Damon Lynch <damonlynch@gmail.com>

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
Notify user of problems when downloading: problems with subfolder and filename generation,
download errors, and so forth

Goals:
Group problems into tasks:
1. scanning
2. copying
3. renaming
4. backing up - per backup device

Present message in human readable manner
There can be duplicate problems
Distinguish error severity

"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2010-2017, Damon Lynch"

import sys
from enum import Enum
from collections import deque
from typing import Tuple, Optional, List, Union, Iterator
from html import escape
from gettext import gettext as _

import logging

from raphodo.utilities import make_internationalized_list
from raphodo.constants import ErrorType

# components
SUBFOLDER_COMPONENT = _('subfolder')
FILENAME_COMPONENT = _('filename')




# problem categories
METADATA_PROBLEM = 1
FILE_PROBLEM = 2
GENERATION_PROBLEM = 3
DOWNLOAD_PROBLEM = 4
DOWNLOAD_PROBLEM_W_NO = 5
DOWNLOAD_PROBLEM_CAM = 6
DIFFERENT_EXIF = 7
FILE_ALREADY_EXISTS = 8
UNIQUE_IDENTIFIER_CAT = 9
BACKUP_PROBLEM = 10
BACKUP_OK = 11
FILE_ALREADY_DOWN_CAT = 12
VERIFICATION_PROBLEM = 13

# problem text

CANNOT_DOWNLOAD_BAD_METADATA = 6

ERROR_IN_NAME_GENERATION = 7

DOWNLOAD_COPYING_ERROR = 8
DOWNLOAD_COPYING_ERROR_W_NO = 9
DOWNLOAD_FROM_CAMERA_ERROR = 10

FILE_ALREADY_EXISTS_NO_DOWNLOAD = 11
UNIQUE_IDENTIFIER_ADDED = 12
BACKUP_EXISTS = 13
BACKUP_EXISTS_OVERWRITTEN = 14
NO_BACKUP_PERFORMED = 15
BACKUP_ERROR = 16
BACKUP_DIRECTORY_CREATION = 17

SAME_FILE_DIFFERENT_EXIF = 18
NO_DOWNLOAD_WAS_BACKED_UP = 19
FILE_ALREADY_DOWNLOADED = 20

FILE_VERIFICATION_FAILED = 21
BACKUP_VERIFICATION_FAILED = 22

#extra details
UNIQUE_IDENTIFIER = '__1'
EXISTING_FILE = '__2'
NO_DATA_TO_NAME = '__3'
DOWNLOAD_COPYING_ERROR_DETAIL = '__4'
DOWNLOAD_COPYING_ERROR_W_NO_DETAIL = '__5'
DOWNLOAD_FROM_CAMERA_ERROR_DETAIL = '__6'
BACKUP_OK_TYPE = '__7'

#                                   category,               text, duplicates allowed
problem_definitions = {

    CANNOT_DOWNLOAD_BAD_METADATA:   (FILE_PROBLEM,          _("%(filetype)s metadata cannot be read"), False),

    ERROR_IN_NAME_GENERATION:       (GENERATION_PROBLEM,    _("%(filetype)s %(area)s could not be generated"), False),

    DOWNLOAD_COPYING_ERROR:         (DOWNLOAD_PROBLEM,      _("An error occurred when copying the %(filetype)s"), False),
    DOWNLOAD_COPYING_ERROR_W_NO:    (DOWNLOAD_PROBLEM_W_NO, _("An error occurred when copying the %(filetype)s"), False),
    DOWNLOAD_FROM_CAMERA_ERROR:     (DOWNLOAD_PROBLEM_CAM,  _("An error occurred copying the %("
                                                              "filetype)s from the %(camera)s")),

    FILE_VERIFICATION_FAILED:       (VERIFICATION_PROBLEM,  _("The %(filetype)s did not download correctly"), False),
    BACKUP_VERIFICATION_FAILED:     (BACKUP_PROBLEM,         "%s", True),

    FILE_ALREADY_EXISTS_NO_DOWNLOAD:(FILE_ALREADY_EXISTS,   _("%(filetype)s already exists"), False),
    UNIQUE_IDENTIFIER_ADDED:        (UNIQUE_IDENTIFIER_CAT, _("%(filetype)s already exists"), False),
    BACKUP_EXISTS:                  (BACKUP_PROBLEM,         "%s", True),
    BACKUP_EXISTS_OVERWRITTEN:      (BACKUP_PROBLEM,         "%s", True),
    NO_BACKUP_PERFORMED:            (BACKUP_PROBLEM,        _("%(filetype)s could not be backed up because no suitable backup locations were found."), False),
    BACKUP_ERROR:                   (BACKUP_PROBLEM,         "%s", True),
    BACKUP_DIRECTORY_CREATION:      (BACKUP_PROBLEM,         "%s", True),
    NO_DOWNLOAD_WAS_BACKED_UP:      (BACKUP_OK,              "%s", True),

    SAME_FILE_DIFFERENT_EXIF:       (DIFFERENT_EXIF,        _("%(image1)s was taken on %(image1_date)s at %(image1_time)s, and %(image2)s on %(image2_date)s at %(image2_time)s."), False),
    FILE_ALREADY_DOWNLOADED:        (FILE_ALREADY_DOWN_CAT, _('%(filetype)s was already downloaded'), False),
}

extra_detail_definitions = {
    UNIQUE_IDENTIFIER:                  _("The existing %(filetype)s was last modified on %(date)s at %(time)s. Unique identifier '%(identifier)s' added."),
    EXISTING_FILE:                      _("The existing %(filetype)s was last modified on %(date)s at %(time)s."),
    NO_DATA_TO_NAME:                    _("There is no data with which to name the %(filetype)s."),
    DOWNLOAD_COPYING_ERROR_DETAIL:      "%s",
    DOWNLOAD_COPYING_ERROR_W_NO_DETAIL: _("Error: %(errorno)s %(strerror)s"),
    DOWNLOAD_FROM_CAMERA_ERROR_DETAIL:  "%s",
    BACKUP_OK_TYPE:                     "%s",
}


def make_href(name: str, uri: str) -> str:
    """
    Construct a hyperlink.
    """

    # Note: keep consistent with ErrorReport._saveUrls()
    return '<a href="{}">{}</a>'.format(uri, escape(name))


class Problem:
    def __init__(self, name: Optional[str]=None,
                 uri: Optional[str]=None,
                 exception: Optional[Exception]=None,
                 **attrs) -> None:
        for attr, value in attrs.items():
            setattr(self, attr, value)
        self.name = name
        self.uri = uri
        self.exception = exception

    @property
    def title(self) -> str:
        logging.critical('title() not implemented in subclass %s', self.__class__.__name__)
        return 'undefined'

    @property
    def body(self) -> str:
        logging.critical('body() not implemented in subclass %s', self.__class__.__name__)
        return 'undefined'

    @property
    def details(self) -> List[str]:
        if self.exception is not None:
            try:
                return [escape(_("Error: %(errno)s %(strerror)s")) % dict(
                    errno=self.exception.errno, strerror=self.exception.strerror)]
            except AttributeError:
                return [escape(_("Error: %s")) % self.exception]
        else:
            return []

    @property
    def href(self) -> str:
        if self.name and self.uri:
            return make_href(name=self.name, uri=self.uri)
        else:
            logging.critical('href() is missing name or uri in subclass %s',
                             self.__class__.__name__)

    @property
    def severity(self) -> ErrorType:
        return ErrorType.warning


class SeriousProblem(Problem):
    @property
    def severity(self) -> ErrorType:
        return ErrorType.serious_error


class CameraGpProblem(SeriousProblem):
    @property
    def details(self) -> List[str]:
        try:
            return [escape(_("GPhoto2 Error: %s")) % self.gp_code]
        except AttributeError:
            return []


class CameraInitializationProblem(CameraGpProblem):
    @property
    def body(self) -> str:
        return escape(_("Unable to initialize the camera, probably because another program is "
                        "using it. No files were copied from it."))
    @property
    def severity(self) -> ErrorType:
        return ErrorType.critical_error


class CameraDirectoryReadProblem(CameraGpProblem):
    @property
    def body(self) -> str:
        return escape(_("Unable to read directory %s")) % self.href


class CameraFileInfoProblem(CameraGpProblem):
    @property
    def body(self) -> str:
        return escape(_('Unable to access modification time or size from %s')) % self.href


class CameraFileReadProblem(CameraGpProblem):
    @property
    def body(self) -> str:
        return escape(_('Unable to read file %s')) % self.href


class FileWriteProblem(SeriousProblem):
    @property
    def body(self) -> str:
        return escape(_('Unable to write file %s')) % self.href


class FileMoveProblem(SeriousProblem):
    @property
    def body(self) -> str:
        return escape(_('Unable to move file %s')) % self.href


class FileDeleteProblem(SeriousProblem):
    @property
    def body(self) -> str:
        return escape(_('Unable to remove file %s')) % self.href


class FileCopyProblem(SeriousProblem):
    @property
    def body(self) -> str:
        return escape(_('Unable to copy file %s')) % self.href


class FsMetadataReadProblem(Problem):
    @property
    def body(self) -> str:
        return escape(_("Could not determine filesystem modification time for %s")) % self.href


class FileMetadataLoadProblem(Problem):
    @property
    def body(self) -> str:
        return escape(_('Unable to load metadata from %s')) % self.href


class FileMetadataLoadProblemNoDownload(SeriousProblem):
    @property
    def body(self) -> str:
        return escape(_('Unable to load metadata from %(name)s. The %(filetype)s was not '
                        'downloaded.')) % dict(filetype=self.file_type, name=self.href)


class FsMetadataWriteProblem(Problem):
    @property
    def body(self) -> str:
        return escape(_(
            "An error occurred setting a file's filesystem metadata on the filesystem %s. "
            "If this error occurs again on the same filesystem, it will not be reported again."
        )) % self.href

    @property
    def details(self) -> List[str]:
        return [escape(_("Error: %(errno)s %(strerror)s")) % dict(errno=e.errno,
                                                                  strerror=e.strerror)
                for e in self.mdata_exceptions]


class UnhandledFileProblem(SeriousProblem):
    @property
    def body(self) -> str:
        return escape(_('Encountered unhandled file %s. It will not be downloaded.')) % self.href


class FileAlreadyExistsProblem(SeriousProblem):
    @property
    def body(self) -> str:
        return escape(
            _("%(filetype)s %(destination)s already exists.")
        ) % dict(
            filetype=escape(self.file_type_capitalized),
            destination=self.href
        )

    @property
    def details(self) -> List[str]:
        d = list()
        d.append(
            escape(
                _("The existing %(filetype)s %(destination)s was last modified on "
                  "%(date)s at %(time)s.")
            ) % dict(
                    filetype=escape(self.file_type),
                    date=escape(self.date),
                    time=escape(self.time),
                    destination=self.href
            )
        )
        d.append(
            escape(
                _("The %(filetype)s %(source)s was not downloaded from %(device)s.")
            ) % dict(
                filetype=escape(self.file_type),
                source=self.source,
                device=self.device
            )
        )
        return d


class IdentifierAddedProblem(FileAlreadyExistsProblem):

    @property
    def details(self) -> List[str]:
        d = list()
        d.append(
            escape(
                _("The existing %(filetype)s %(destination)s was last modified on "
                  "%(date)s at %(time)s.")
            ) % dict(
                    filetype=escape(self.file_type),
                    date=escape(self.date),
                    time=escape(self.time),
                    destination=self.href
            )
        )
        d.append(
            escape(
                _("The %(filetype)s %(source)s was downloaded from %(device)s.")
            ) % dict(
                filetype=escape(self.file_type),
                source=self.source,
                device=self.device
            )
        )
        d.append(
            escape(
                _("The unique identifier '%s' was added to the filename.")) % self.identifier
        )
        return d

    @property
    def severity(self) -> ErrorType:
        return ErrorType.warning


class DuplicateFileWhenSyncingProblem(SeriousProblem):
    @property
    def body(self) -> str:
        return escape(
            _("When synchronizing RAW + JPEG sequence values, a duplicate %(filetype)s "
              "%(file)s was encountered, and was not downloaded."
              )
        ) % dict(file=self.href, filetype=self.file_type)


class SameNameDifferentExif(Problem):
    @property
    def body(self) -> str:
        return escape(
            _("When synchronizing RAW + JPEG sequence values, photos were detected with the " 
              "same filenames, but taken at different times:")
        )

    @property
    def details(self) -> List[str]:
        return [escape(
            _("%(image1)s was taken on %(image1_date)s at %(image1_time)s, and %(image2)s "
              "on %(image2_date)s at %(image2_time)s.")
        ) % dict(
            image1=self.image1,
            image1_date=self.image1_date,
            image1_time=self.image1_time,
            image2=self.image2,
            image2_date=self.image2_date,
            image2_time=self.image2_time
        )]


class RenamingAssociateFileProblem(SeriousProblem):
    @property
    def body(self) -> str:
        return escape(
            _("Unable to finalize the filename for %s")
        ) % self.source


class FilenameNotFullyGeneratedProblem(Problem):
    def __init__(self, name: Optional[str]=None,
                 uri: Optional[str]=None,
                 exception: Optional[Exception]=None,
                 **attrs) -> None:
        super().__init__(name=name, uri=uri, exception=exception, **attrs)
        self.missing_metadata = []
        self.file_type = ''
        self.destination = ''
        self.source = ''
        self.bad_converstion_date_time = False
        self.bad_conversion_exception = None  # type: Optional[Exception]
        self.invalid_date_time = False
        self.missing_extension = False
        self.missing_image_no = False
        self.component_error = False
        self.component_problem = ''
        self.component_exception = None

    def has_error(self) -> bool:
        """
        :return: True if any of the errors occurred 
        """

        return bool(self.missing_metadata) or self.invalid_date_time or \
               self.bad_converstion_date_time or self.missing_extension or self.missing_image_no \
               or self.component_error

    @property
    def body(self) -> str:
        return escape(
            _("The filename %(destination)s was not fully generated for %(filetype)s %(source)s.")
        ) % dict(destination=self.destination, filetype=self.file_type, source=self.source)

    @property
    def details(self) -> List[str]:
        d = []
        if len(self.missing_metadata) == 1:
            d.append(
                escape(
                    _("The %(type)s metadata is missing.")
                ) % dict(type=self.missing_metadata[0])
            )
        elif len(self.missing_metadata) > 1:
            d.append(
                escape(
                    _("The following metadata is missing: %s.")
                ) % make_internationalized_list(self.missing_metadata)
            )

        if self.bad_converstion_date_time:
            d.append(
                escape(_('Date/time conversion failed: %s.')) % self.bad_conversion_exception
            )

        if self.invalid_date_time:
            d.append(
                escape(
                    _("Could not extract valid date/time metadata or determine the file "
                      "modification time.")
                )
            )

        if self.missing_extension:
            d.append(escape(_("Filename does not have an extension.")))

        if self.missing_image_no:
            d.append(escape(_("Filename does not have a number component.")))

        if self.component_error:
            d.append(
                escape(_("Error generating component %(component)s. Error: %(error)s")) % dict(
                    component=self.component_problem,
                    error=self.component_exception
                )
            )

        return d


class FolderNotFullyGeneratedProblemProblem(FilenameNotFullyGeneratedProblem):
    @property
    def body(self) -> str:
        return escape(
            _("The download subfolders %(folder)s were only partially generated for %(filetype)s "
              "%(source)s.")
        ) % dict(folder=self.destination, filetype=self.file_type, source=self.source)


class NoDataToNameProblem(SeriousProblem):
    @property
    def body(self) -> str:
        return escape(
            _("There is no data with which to generate the %(subfolder_file)s for %(filename)s. It "
              "was not downloaded.")
        ) % dict(
            subfolder_file = self.area,
            filename = self.href
        )


class RenamingFileProblem(SeriousProblem):
    @property
    def body(self) -> str:
        return escape(
            _('Unable to create the %(filetype)s %(destination)s in %(folder)s. The download file '
              'was %(source)s in %device)s. It was not downloaded.')
        ) % dict(
            filetype=escape(self.file_type),
            destination=escape(self.destination),
            folder=self.folder,
            source=self.href,
            device=self.device
        )

_("The following metadata is missing: ")
_("The %(type)s metadata is missing.")


class SubfolderCreationProblem(Problem):
    @property
    def body(self) -> str:
        return escape(
            _('Unable to create the download subfolder %s.')
        ) % self.folder

    @property
    def severity(self) -> ErrorType:
        return ErrorType.critical_error


class Problems:
    def __init__(self, name: Optional[str]='',
                 uri: Optional[str]='',
                 problem: Optional[Problem]=None) -> None:
        self.problems = deque()
        self.name = name
        self.uri = uri
        if problem:
            self.append(problem=problem)

    def __len__(self) -> int:
        return len(self.problems)

    def __iter__(self) -> Iterator[Problem]:
        return iter(self.problems)

    def __getitem__(self, index: int) -> Problem:
        return self.problems[index]

    def append(self, problem: Problem) -> None:
        self.problems.append(problem)

    @property
    def title(self) -> str:
        logging.critical('title() not implemented in subclass %s', self.__class__.__name__)
        return 'undefined'

    @property
    def body(self) -> str:
        return 'body'

    @property
    def details(self) -> List[str]:
        return []

    @property
    def href(self) -> str:
        if self.name and self.uri:
            return make_href(name=self.name, uri=self.uri)
        else:
            logging.critical('href() is missing name or uri in %s', self.__class__.__name__)


class ScanProblems(Problems):

    @property
    def title(self) -> str:
        return escape(_('Problems scanning %s')) % self.href


class CopyingProblems(Problems):

    @property
    def title(self) -> str:
        return escape(_('Problems copying from %s')) % self.href


class RenamingProblems(Problems):

    @property
    def title(self) -> str:
        return escape(_('Problems while finalizing filenames and generating subfolders'))


class BackingUpProblems(Problems):

    @property
    def title(self) -> str:
        return escape(_('Problems backing up to %s')) % self.href

class LegacyProblem:
    """
    Collect problems with subfolder and filename generation, download errors, and so forth

    Problems are human readable.

    This code is in severe need of an overhaul. It's a mess.
    """

    def __init__(self):
        self.problems = {}
        self.categories = {}
        self.components = []
        self.extra_detail = {}

    def add_problem(self, component, problem_definition, *args):
        added = True
        if problem_definition not in problem_definitions:
            sys.stderr.write("FIXME: unknown problem definition!\n")
        else:
            category, problem, duplicates_ok = problem_definitions[problem_definition]

            if args:
                # check for special case of named arguments in a dictionary
                if isinstance(args[0], dict):
                    problem_details = problem % args[0]
                else:
                    problem_details = problem % args
            else:
                problem_details = problem

            if not duplicates_ok:
                self.problems[problem_definition] = [problem_details]
            else:
                if problem_definition in self.problems:
                    if problem_details not in self.problems[problem_definition]:
                        self.problems[problem_definition].append(problem_details)
                    else:
                        added = False
                else:
                    self.problems[problem_definition] = [problem_details]

            if category not in self.categories or not added:
                self.categories[category] = 1
            else:
                self.categories[category] += 1

            if (component is not None) and (component not in self.components):
                self.components.append(component)

    def add_extra_detail(self, extra_detail, *args):
        if extra_detail not in extra_detail_definitions:
            self.extra_detail[extra_detail] = args[0]
        else:
            detail = extra_detail_definitions[extra_detail]

            if args:
                if isinstance(args[0], dict):
                    extra_details = detail % args[0]
                else:
                    extra_details = detail % args
            else:
                extra_details = detail

            self.extra_detail[extra_detail] = extra_details


    def has_problem(self):
        return len(self.problems) > 0

    def get_problems(self):
        """
        Returns a string with the problems encountered in downloading the file.
        """

        def get_backup_error_inst(volume):
            if ('%s%s' % (BACKUP_ERROR, volume)) in self.extra_detail:
                return  self.extra_detail['%s%s' % (BACKUP_ERROR, volume)]
            else:
                return ''

        def get_dir_creation_inst(volume):
            return  self.extra_detail['%s%s' % (BACKUP_DIRECTORY_CREATION, volume)]

        v = ''

        # special cases

        if VERIFICATION_PROBLEM in self.categories:
            return _("File verification failed. The downloaded version is different from the "
                     "original.")

        if FILE_PROBLEM in self.categories:
            return _("The metadata could not be parsed.")

        if FILE_ALREADY_DOWN_CAT in self.categories:
            return _("The filename, extension and Exif information indicate it has already been "
                     "downloaded.")

        if FILE_ALREADY_EXISTS in self.categories:
            if EXISTING_FILE in self.extra_detail:
                v = self.extra_detail[EXISTING_FILE]


        if UNIQUE_IDENTIFIER_CAT in self.categories:
            v = self.extra_detail[UNIQUE_IDENTIFIER]

        if DOWNLOAD_PROBLEM in self.categories:
            v = self.extra_detail[DOWNLOAD_COPYING_ERROR_DETAIL]

        if DOWNLOAD_PROBLEM_W_NO in self.categories:
            v = self.extra_detail[DOWNLOAD_COPYING_ERROR_W_NO_DETAIL]

        if DOWNLOAD_PROBLEM_CAM in self.categories:
            v = self.extra_detail[DOWNLOAD_FROM_CAMERA_ERROR_DETAIL]

        if BACKUP_OK in self.categories:
            details = self.problems[NO_DOWNLOAD_WAS_BACKED_UP]
            if len(self.problems[NO_DOWNLOAD_WAS_BACKED_UP]) == 1:
                vv = _(' It was backed up to %(volume)s') % {'volume': details[0]}
            else:
                vv = _(" It was backed up to these devices: ")
                for d in details[:-1]:
                    vv += _("%s, ") % d
                vv = _("%(volumes)s and %(final_volume)s.") % \
                    {'volumes': vv[:-2],
                    'final_volume': details[-1]} \
                     + ' '
            v += vv

        if GENERATION_PROBLEM in self.categories:
            v = self.extra_detail[NO_DATA_TO_NAME]

        if DIFFERENT_EXIF in self.categories:
            v = self.problems[SAME_FILE_DIFFERENT_EXIF][0]
            if METADATA_PROBLEM in self.categories:
                v = _('Photos detected with the same filenames, but taken at different times: '
                      '%(details)s' ) % {'details':v}

        # Problems backing up
        if BACKUP_PROBLEM in self.categories:
            vv = ''
            for p in self.problems:
                details = self.problems[p]

                if p == NO_BACKUP_PERFORMED:
                    vv = details[0]

                elif p == BACKUP_ERROR:

                    if len(details) == 1:
                        volume = details[0]
                        inst = get_backup_error_inst(volume)
                        if inst:
                            vv += _("An error occurred when backing up on %(volume)s: "
                                    "%(inst)s.") % {'volume': volume, 'inst': inst} + ' '
                        else:
                            vv += _("An error occurred when backing up on "
                                    "%(volume)s.") % {'volume': volume} + ' '
                    else:
                        vv += _("Errors occurred when backing up on the following backup devices: ")
                        for volume in details[:-1]:
                            inst = get_backup_error_inst(volume)
                            if inst:
                                vv += _("%(volume)s (%(inst)s), ") % {'volume': volume,
                                                                      'inst': inst}
                            else:
                                vv += _("%(volume)s, ") % {'volume': volume}
                        volume = details[-1]
                        inst = get_backup_error_inst(volume)
                        if inst:
                            vv = _("%(volumes)s and %(volume)s (%(inst)s).") % \
                                {'volumes': vv[:-2],
                                'volume': volume,
                                'inst': get_backup_error_inst(volume)}
                        else:
                            vv = _("%(volumes)s and %(volume)s.") % \
                                {'volumes': vv[:-2],
                                'volume': volume} \
                                 + ' '

                elif p == BACKUP_EXISTS:
                    if len(details) == 1:
                        vv += _("Backup already exists on %(volume)s.") % {
                                                                        'volume': details[0]} + ' '
                    else:
                        vv += _("Backups already exist in these locations: ")
                        for d in details[:-1]:
                            vv += _("%s, ") % d
                        vv = _("%(volumes)s and %(final_volume)s.") % \
                            {'volumes': vv[:-2],
                            'final_volume': details[-1]} \
                             + ' '

                elif p == BACKUP_EXISTS_OVERWRITTEN:
                    if len(details) == 1:
                        vv += _("Backup overwritten on %(volume)s.") % {'volume': details[0]} + ' '
                    else:
                        vv += _("Backups overwritten on these devices: ")
                        for d in details[:-1]:
                            vv += _("%s, ") % d
                        vv = _("%(volumes)s and %(final_volume)s.") % \
                            {'volumes': vv[:-2],
                            'final_volume': details[-1]} \
                             + ' '

                elif p == BACKUP_DIRECTORY_CREATION:
                    if len(details) == 1:
                        volume = details[0]
                        vv += _("An error occurred when creating directories on %(volume)s: "
                                "%(inst)s.") % {'volume': volume,
                                                'inst': get_dir_creation_inst(volume)} + ' '
                    else:
                        vv += _("Errors occurred when creating directories on the following "
                                "backup devices: ")
                        for volume in details[:-1]:
                            vv += _("%(volume)s (%(inst)s), ") % {'volume': volume,
                                                          'inst': get_dir_creation_inst(volume)}
                        volume = details[-1]
                        vv = _("%(volumes)s and %(volume)s (%(inst)s).") % \
                            {'volumes': vv[:-2],
                            'volume': volume,
                            'inst': get_dir_creation_inst(volume)} \
                             + ' '

                elif p == BACKUP_VERIFICATION_FAILED:
                    if len(details) == 1:
                        vv += _("File verification failed on %(volume)s. The backed up "
                                "version is different from the "
                                "downloaded version.") % {'volume': details[0]} + ' '
                    else:
                        vv += _("File verification failed on these devices: ")
                        for d in details[:-1]:
                            vv += _("%s, ") % d
                        vv = _("%(volumes)s and %(final_volume)s.") % \
                            {'volumes': vv[:-2],
                            'final_volume': details[-1]} \
                             + ' '


            if v:
                v = _('%(previousproblem)s Additionally, %(newproblem)s') % {
                    'previousproblem': v, 'newproblem': vv[0].lower() + vv[1:]}
            else:
                v = vv


        if v and METADATA_PROBLEM in self.categories:
            vv = self._get_generation_title()
            if self.categories[METADATA_PROBLEM] > 1:
                v += _(' Furthermore, there were %(problems)s.') % {
                    'problems': vv[0].lower() + vv[1:]}
            else:
                v += _(' Furthermore, there was a %(problem)s.') % {
                    'problem': vv[0].lower() + vv[1:]}



        v = v.strip()
        return v

    def _get_generation_title(self):
        if self.components:
            if len(self.components) > 1:
                if self.categories[METADATA_PROBLEM] > 1:
                    return _('Problems in subfolder and filename generation')
                else:
                    return _('Problem in subfolder and filename generation')
            else:
                if self.categories[METADATA_PROBLEM] > 1:
                    return _('Problems in %s generation') % self.components[0]
                else:
                    return _('Problem in %s generation') % self.components[0]
        return ''


    def get_title(self):
        v = ''

        if BACKUP_OK in self.categories:
            if FILE_ALREADY_EXISTS in self.categories:
                v = _('%(filetype)s already exists, but it was backed up') % {
                    'filetype': self.extra_detail[BACKUP_OK_TYPE]}
            else:
                v = _('An error occurred when copying the %(filetype)s, but it was backed up') % {
                    'filetype': self.extra_detail[BACKUP_OK_TYPE]}

        # High priority problems
        elif VERIFICATION_PROBLEM in self.categories:
            v = self.problems[FILE_VERIFICATION_FAILED][0]
        elif FILE_ALREADY_DOWN_CAT in self.categories:
            v = self.problems[FILE_ALREADY_DOWNLOADED][0]
        elif DOWNLOAD_PROBLEM in self.categories:
            v = self.problems[DOWNLOAD_COPYING_ERROR][0]
        elif DOWNLOAD_PROBLEM_W_NO in self.categories:
            v = self.problems[DOWNLOAD_COPYING_ERROR_W_NO][0]
        elif GENERATION_PROBLEM in self.categories:
            v = self.problems[ERROR_IN_NAME_GENERATION][0]
        elif FILE_ALREADY_EXISTS in self.categories:
            v = self.problems[FILE_ALREADY_EXISTS_NO_DOWNLOAD][0]
        elif UNIQUE_IDENTIFIER_CAT in self.categories:
            v = self.problems[UNIQUE_IDENTIFIER_ADDED][0]
        elif FILE_PROBLEM in self.categories:
            v = self.problems[CANNOT_DOWNLOAD_BAD_METADATA][0]

        # Lesser priority
        elif len(self.categories) > 1:
            v = _('Multiple problems were encountered')
        elif DIFFERENT_EXIF in self.categories:
            v = _('Photos detected with the same filenames, but taken at different times')
        elif METADATA_PROBLEM in self.categories:
            v = self._get_generation_title()

        if BACKUP_PROBLEM in self.categories:
            if self.categories[BACKUP_PROBLEM] >1:
                vp = _("there were errors backing up")
                vv = _("There were errors backing up")
            else:
                vp = _("there was an error backing up")
                vv = _("There was an error backing up")
            if v:
                # e.g.
                v = _("%(previousproblem)s, and %(backinguperror)s") % {'previousproblem': v,
                                                                        'backinguperror':vp}
            else:
                v = vv

        return v



if __name__ == '__main__':
    p = Problems()
    print(p.title)