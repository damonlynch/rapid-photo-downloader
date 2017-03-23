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

# components
SUBFOLDER_COMPONENT = _('subfolder')
FILENAME_COMPONENT = _('filename')

# Problem categories
class ProblemCat(Enum):
    metadata = 1
    file = 2
    generation = 3
    download = 4
    different_exif = 5
    file_already_exists = 6
    unique_identifier_added = 7
    backup = 8
    download_failed_backup_ok = 9
    file_already_downloaded = 10
    verification = 11
    fs_metadata = 12


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
MISSING_METADATA = 1
INVALID_DATE_TIME = 2
MISSING_FILE_EXTENSION = 3
MISSING_IMAGE_NUMBER = 4
ERROR_IN_GENERATION = 5

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

    MISSING_METADATA:               (METADATA_PROBLEM,        "%s", True),
    INVALID_DATE_TIME:              (METADATA_PROBLEM,      _('Date time value %s appears invalid.'), False),
    MISSING_FILE_EXTENSION:         (METADATA_PROBLEM,      _("Filename does not have an extension."), False),
    # a number component is something like the 8346 in IMG_8346.JPG
    MISSING_IMAGE_NUMBER:           (METADATA_PROBLEM,      _("Filename does not have a number component."), False),
    ERROR_IN_GENERATION:            (METADATA_PROBLEM,      _("Error generating component %s."), False), # a generic problem

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
            return [escape(_("Error: %(errno)s %(strerror)s")) % dict(
                errno=self.exception.errno, strerror=self.exception.strerror)]
        else:
            return []

    @property
    def href(self) -> str:
        if self.name and self.uri:
            return '<a href="{}">{}</a>'.format(self.uri, escape(self.name))
        else:
            logging.critical('href() is missing name or uri in subclass %s',
                             self.__class__.__name__)


class CameraGpProblem(Problem):
    @property
    def details(self) -> List[str]:
            return [escape(_("GPhoto2 Error: %s")) % self.gp_code]


class CameraDirectoryReadProblem(CameraGpProblem):
    @property
    def body(self) -> str:
        return escape(_("Unable to read directory %s")) % self.href


class CameraFileInfoProblem(CameraGpProblem):
    @property
    def body(self) -> str:
        return escape(_('Unable to access modification time or size from %s')) % self.href


class CameraFileReadProblem(Problem):
    @property
    def body(self) -> str:
        return escape(_('Unable to read file %s')) % self.href


class FileWriteProblem(Problem):
    @property
    def body(self) -> str:
        return escape(_('Unable to write file %s')) % self.href


class FsMetadataReadProblem(Problem):
    @property
    def body(self) -> str:
        return escape(_("Could not determine filesystem modification time for %s")) % self.href


class FileMetadataLoadProblem(Problem):
    @property
    def body(self) -> str:
        return escape(_('Unable to load metadata from %s')) % self.href


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


class UnhandledFileProblem(Problem):
    @property
    def body(self) -> str:
        return escape(_('Encountered unhandled file %s. It will not be downloaded.')) % self.href


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
            return '<a href="{}">{}</a>'.format(self.uri, self.name)
        else:
            logging.critical('href() is missing name or uri in %s', self.__class__.__name__)


class ScanProblems(Problems):

    @property
    def title(self) -> str:
        return escape(_('Errors scanning %s')) % self.href


class CopyingProblems(Problems):

    @property
    def title(self) -> str:
        return escape(_('Errors copying from %s')) % self.href


class RenamingProblems(Problems):

    @property
    def title(self) -> str:
        return escape(_('Errors while renaming and generating subfolders'))



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

        # Problems generating file / subfolder names
        if METADATA_PROBLEM in self.categories:
            for p in self.problems:
                vv = ''
                details = self.problems[p]
                if p == MISSING_METADATA:
                    if len(details) == 1:
                        vv = _("The %(type)s metadata is missing.") % {'type': details[0]}
                    else:
                        vv = _("The following metadata is missing: ")
                        for d in details[:-1]:
                            vv += ("%s, ") % d
                        vv = _("%(missing_metadata_elements)s and "
                               "%(final_missing_metadata_element)s.") % {
                            'missing_metadata_elements': vv[:-2],
                            'final_missing_metadata_element': details[-1]}


                elif p in [MISSING_IMAGE_NUMBER, ERROR_IN_GENERATION, INVALID_DATE_TIME]:
                    vv = details[0]

                v += ' ' + vv

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