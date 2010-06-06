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
METADATA_PROBLEM = _('metadata')
#METADATA_MISSING_PROBLEM = _('missing metadata')
FILE_PROBLEM = _('file')

# problem text
MISSING_METADATA = 'missing metadata'
INVALID_DATE_TIME = 'invalid date time'
MISSING_FILE_EXTENSION = 'missing file extension'
MISSING_IMAGE_NUMBER = 'missing image number'
ERROR_IN_GENERATION = 'error in genereration'

CANNOT_DOWNLOAD_BAD_METADATA = 'cannot download bad metadata'

#category, text, duplicates allowed
problem_definitions = {
                                    
    MISSING_METADATA:               (METADATA_PROBLEM, _("%s"), True),
    INVALID_DATE_TIME:              (METADATA_PROBLEM, _('Date time value %s appears invalid.'), False),
    MISSING_FILE_EXTENSION:         (METADATA_PROBLEM, _("Filename does not have an extension."), False),
    # a number component is something like the 8346 in IMG_8346.JPG
    MISSING_IMAGE_NUMBER:           (METADATA_PROBLEM, _("Filename has not have a number component."), False),
    ERROR_IN_GENERATION:            (METADATA_PROBLEM, _("Error generating component %s."), False),
    
    CANNOT_DOWNLOAD_BAD_METADATA:   (FILE_PROBLEM, _("%(filetype)s cannot be downloaded"), False)
    
}

class Problem:
    """
    Collect problems with subfolder and filename generation
    
    Problems are human readable
    """
    
    def __init__(self):
        self.problems = {}
        self.categories = []
        self.components = []
    
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
                
    def has_problem(self):
        return len(self.problems) > 0
        
    def get_problems(self):
        v = ''
        # special cases
        
        if len(self.problems) == 1:         
            if self.problems.keys()[0] == CANNOT_DOWNLOAD_BAD_METADATA:
                return _("The metadata might be corrupt.")
                
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
        
        if self.components:
            if self.components[0] == FILE_PROBLEM:
                return self.problems[CANNOT_DOWNLOAD_BAD_METADATA][0]
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
