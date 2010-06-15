#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2010 Damon Lynch <damonlynch@gmail.com>

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
### Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import sys
import types
from common import Configi18n
global _
_ = Configi18n._


# components
SUBFOLDER_COMPONENT = _('subfolder')
FILENAME_COMPONENT = _('filename')

# problem categories
METADATA_PROBLEM = 'metadata'
FILE_PROBLEM = 'file'
GENERATION_PROBLEM = 'generation'
DOWNLOAD_PROBLEM = 'download'
DOWNLOAD_PROBLEM_W_NO = 'download with error number'
DIFFERENT_EXIF = 'different exif'
FILE_ALREADY_EXISTS = 'file already exists'
UNIQUE_IDENTIFIER_CAT = 'unique identifier added'

# problem text - inefficient representation, but easier to debug!
MISSING_METADATA = 'missing metadata'
INVALID_DATE_TIME = 'invalid date time'
MISSING_FILE_EXTENSION = 'missing file extension'
MISSING_IMAGE_NUMBER = 'missing image number'
ERROR_IN_GENERATION = 'error in genereration'

CANNOT_DOWNLOAD_BAD_METADATA = 'cannot download bad metadata'

ERROR_IN_NAME_GENERATION = 'error in name generation'

DOWNLOAD_COPYING_ERROR = 'download copying error'
DOWNLOAD_COPYING_ERROR_W_NO = 'download copying error with error number'

FILE_ALREADY_EXISTS_NO_DOWNLOAD = 'file already exists no download'
UNIQUE_IDENTIFIER_ADDED = 'unique identifier added'

SAME_FILE_DIFFERENT_EXIF = 'same file different exif'

#extra details
UNIQUE_IDENTIFIER = 'unique identifier'
FILE_WAS_NOT_DOWNLOADED = 'file was not downloaded'
FILE_CANNOT_BE_DOWNLOADED = 'file cannot be downloaded'

DOWNLOAD_COPYING_ERROR_DETAIL = 'download copying error detail'
DOWNLOAD_COPYING_ERROR_W_NO_DETAIL = 'download copying error with error number detail'

#                                   category,               text, duplicates allowed
problem_definitions = {
                                    
    MISSING_METADATA:               (METADATA_PROBLEM,      _("%s"), True),
    INVALID_DATE_TIME:              (METADATA_PROBLEM,      _('Date time value %s appears invalid.'), False),
    MISSING_FILE_EXTENSION:         (METADATA_PROBLEM,      _("Filename does not have an extension."), False),
    # a number component is something like the 8346 in IMG_8346.JPG
    MISSING_IMAGE_NUMBER:           (METADATA_PROBLEM,      _("Filename does not have a number component."), False),
    ERROR_IN_GENERATION:            (METADATA_PROBLEM,      _("Error generating component %s."), False), # a generic problem
    
    CANNOT_DOWNLOAD_BAD_METADATA:   (FILE_PROBLEM,          _("%(filetype)s metadata cannot be read"), False),
    
    ERROR_IN_NAME_GENERATION:       (GENERATION_PROBLEM,    _("%(filetype)s %(area)s could not be generated"), False),
    
    DOWNLOAD_COPYING_ERROR:         (DOWNLOAD_PROBLEM,      _("An error occurred when copying the %(filetype)s"), False),
    DOWNLOAD_COPYING_ERROR_W_NO:    (DOWNLOAD_PROBLEM_W_NO, _("An error occurred when copying the %(filetype)s"), False),
    
    FILE_ALREADY_EXISTS_NO_DOWNLOAD:(FILE_ALREADY_EXISTS,   _("%(filetype)s already exists"), False),
    UNIQUE_IDENTIFIER_ADDED:        (UNIQUE_IDENTIFIER_CAT, _("%(filetype)s already exists"), False),
    
    SAME_FILE_DIFFERENT_EXIF:       (DIFFERENT_EXIF,        _("First photo: %(image1)s %(image1_date_time)s\nSecond photo: %(image2)s %(image2_date_time)s"), False),
    
}

extra_detail_definitions = {
    UNIQUE_IDENTIFIER:                  _("Unique identifier '%(identifier)s' added."),
    FILE_WAS_NOT_DOWNLOADED:            _("The %(filetype)s was not downloaded."),
    FILE_CANNOT_BE_DOWNLOADED:          _("The %(filetype)s cannot be not downloaded."),
    DOWNLOAD_COPYING_ERROR_DETAIL:      "%s",
    DOWNLOAD_COPYING_ERROR_W_NO_DETAIL: _("Error: %(errorno)s %(strerror)s"),
}

class Problem:
    """
    Collect problems with subfolder and filename generation, download errors, and so forth
    
    Problems are human readable
    """
    
    def __init__(self):
        self.problems = {}
        self.categories = []
        self.components = []
        self.extra_detail = {}
    
    def add_problem(self, component, problem_definition, *args):
        if problem_definition not in problem_definitions:
            sys.stderr.write("FIXME: unknown problem definition!\n")
        else:
            category, problem, duplicates_ok = problem_definitions[problem_definition]
            
            if args:
                # check for special case of named arguments in a dictionary
                if isinstance(args[0], types.DictType):
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
                    self.problems[problem_definition] = [problem_details]
                    
            if category not in self.categories:
                self.categories.append(category)
            
            if (component is not None) and (component not in self.components):
                self.components.append(component)

    def add_extra_detail(self, extra_detail, *args):
        if extra_detail not in extra_detail_definitions:
            sys.stderr.write("FIXME: unknown extra detail definition!\n")
        else:
            detail = extra_detail_definitions[extra_detail]
            
            if args:
                if isinstance(args[0], types.DictType):
                    extra_details = detail % args[0]
                else:
                    extra_details = detail % args
            else:
                extra_details = detail
                
            self.extra_detail[extra_detail] = extra_details
        
        
    def has_problem(self):
        return len(self.problems) > 0
        
    def get_problems(self):
        v = ''
        
        # special cases
        if FILE_PROBLEM in self.categories:
            return _("The metadata might be corrupt.")

        if FILE_ALREADY_EXISTS in self.categories:
            return self.extra_detail[FILE_WAS_NOT_DOWNLOADED]
            
        if UNIQUE_IDENTIFIER_CAT in self.categories:
            return self.extra_detail[UNIQUE_IDENTIFIER]
        
        if DOWNLOAD_PROBLEM in self.categories:
            return self.extra_detail[DOWNLOAD_COPYING_ERROR_DETAIL]
            
        if DOWNLOAD_PROBLEM_W_NO in self.categories:
            return self.extra_detail[DOWNLOAD_COPYING_ERROR_W_NO_DETAIL]

        #if GENERATION_PROBLEM in self.categories:
        #    v = self.extra_detail[FILE_CANNOT_BE_DOWNLOADED]
            
        if DIFFERENT_EXIF in self.categories:
            v = self.problems[SAME_FILE_DIFFERENT_EXIF][0] 
        
        for p in self.problems:
            vv = ''
            details = self.problems[p]
            if p == MISSING_METADATA:
                if len(details) == 1:
                    vv = _("The %(type)s metadata is missing.") % {'type': details[0]}
                else:
                    vv = _("The following metadata is missing: ")
                    for d in details[:-1]:
                        vv += "%s, " % d
                    vv = "%(missing_metadata_elements)s and %(final_missing_metadata_element)s." % \
                        {'missing_metadata_elements': vv[:-2], 
                        'final_missing_metadata_element': details[-1]}
                
                
            elif p in [MISSING_IMAGE_NUMBER, ERROR_IN_GENERATION, INVALID_DATE_TIME]:
                vv = details[0]
                                
            v += ' ' + vv
            
        v = v.strip()
        return v

    def get_title(self):
        
        if FILE_ALREADY_EXISTS in self.categories:
            return self.problems[FILE_ALREADY_EXISTS_NO_DOWNLOAD][0]
        elif UNIQUE_IDENTIFIER_CAT in self.categories:
            return self.problems[UNIQUE_IDENTIFIER_ADDED][0]
        elif FILE_PROBLEM in self.categories:
            return self.problems[CANNOT_DOWNLOAD_BAD_METADATA][0]
        elif GENERATION_PROBLEM in self.categories:
            return self.problems[ERROR_IN_NAME_GENERATION][0]
        elif DOWNLOAD_PROBLEM in self.categories:
            return self.problems[DOWNLOAD_COPYING_ERROR][0]
        elif DOWNLOAD_PROBLEM_W_NO in self.categories:
            return self.problems[DOWNLOAD_COPYING_ERROR_W_NO][0]
        elif DIFFERENT_EXIF in self.categories:
            return _('Photos detected with the same filenames, but taken at different times')
        
        if self.components:
            if len(self.components) > 1:
                if len(self.problems) > 1:
                    return _('Problems in subfolder and filename generation')
                else:
                    return _('Problem in subfolder and filename generation')
            else:
                if len(self.problems) > 1:
                    return _('Problems in %s generation') % self.components[0]
                else:
                    return _('Problem in %s generation') % self.components[0]
        return ''

if __name__ == '__main__':
     pass
