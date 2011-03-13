#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2007, 2008, 2009, 2010, 2011 Damon Lynch <damonlynch@gmail.com>

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

import os, re, datetime

import multiprocessing
import logging
logger = multiprocessing.get_logger()

import problemnotification as pn

from generatenameconfig import *

from common import Configi18n
global _
_ = Configi18n._



class PrefError(Exception):
    """ base class """
    def unpackList(self, l):
        """
        Make the preferences presentable to the user
        """
        
        s = ''
        for i in l:
            if i <> ORDER_KEY:
                s += "'" + i + "', "
        return s[:-2]

    def __str__(self): 
        return self.msg
        
class PrefKeyError(PrefError):
    def __init__(self, error):
        value = error[0]
        expectedValues = self.unpackList(error[1])
        self.msg = "Preference key '%(key)s' is invalid.\nExpected one of %(value)s" % {
                            'key': value, 'value': expectedValues}


class PrefValueInvalidError(PrefKeyError):
    def __init__(self, error):
        value = error[0]
        self.msg = "Preference value '%(value)s' is invalid" % {'value': value}
        
class PrefLengthError(PrefError):
    def __init__(self, error):
        self.msg = "These preferences are not well formed:" + "\n %s" % self.unpackList(error)
        
class PrefValueKeyComboError(PrefError):
    def __init__(self, error):    
        self.msg = error


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
    
    def __init__(self, prefs, download_start_time):
        self.prefs = prefs
        self.download_start_time = download_start_time
        
        # Some of the next values are overwritten in derived classes
        self.pref_list = prefs.image_rename
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
                d = self.rpd_file.metadata.sub_seconds()
                if d == '00':
                    self.problem.add_problem(self.component, pn.MISSING_METADATA, _(self.L2))
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
            d = self.download_start_time
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
                self.problem.add_problem(self.component, pn.INVALID_DATE_TIME, '')
                logger.error("Both file modification time and metadata date & time are invalid for file %s", self.rpd_file.full_file_name)
                return ''
        else:
            self.problem.add_problem(self.component, pn.MISSING_METADATA, _(self.L1))
            return ''
        
        try:
            return d.strftime(convert_date_for_strftime(self.L2))
        except:
            self.problem.add_problem(self.component, pn.INVALID_DATE_TIME, d)
            logger.error("Both file modification time and metadata date & time are invalid for file %s", self.rpd_file.full_file_name)
            return ''
            
    def _get_component(self):
        #~ try:
        if True:
            if self.L0 == DATE_TIME:
                return self._get_date_component()
            #~ elif self.L0 == TEXT:
                #~ return self.L1
            #~ elif self.L0 == FILENAME:
                #~ return self._getFilenameComponent()
            #~ elif self.L0 == METADATA:
                #~ return self._getMetadataComponent()
            #~ elif self.L0 == SEQUENCES:
                #~ return self._getSequencesComponent()
            #~ elif self.L0 == JOB_CODE:
                #~ return self.job_code
            elif self.L0 == SEPARATOR:
                return os.sep
            else:
                # for development phase only
                return ''
        #~ except:
            #~ self.problem.add_problem(self.component, pn.ERROR_IN_GENERATION, _(self.L0))
            #~ return ''
            
    
    def generate_name(self, rpd_file):
        self.rpd_file = rpd_file

        name = ''

        for self.L0, self.L1, self.L2 in self._get_values_from_pref_list():
            v = self._get_component()
            if v:
                name += v

        if self.prefs.strip_characters:
            for c in r'\:*?"<>|':
                name = name.replace(c, '')
                
        if self.strip_forward_slash:
            name = name.replace('/', '')
            
        name = name.strip()
                    
        return name

    def initialize_problem(self, problem):
        """
        Set the problem tracker used in name generation
        """
        self.problem = problem    
        

class VideoName:
    def __init__(self, prefs, download_start_time):
        PhotoName.__init__(self, prefs, download_start_time)
        self.pref_list = prefs.video_rename
        self.L1_date_check = VIDEO_DATE  #used in _get_date_component()

class PhotoSubfolder(PhotoName):
    """
    Generate subfolder names for photo files
    """
    
    def __init__(self, prefs, download_start_time):
        self.prefs = prefs
        self.download_start_time = download_start_time
        self.pref_list = prefs.subfolder #overwritten in class VideoSubfolder
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
        if subfolders and self.prefs.strip_characters:
            subfolders = self.strip_extraneous_white_space.sub(os.sep, subfolders)
            
        return subfolders
                

        
class VideoSubfolder(PhotoSubfolder):
    """
    Generate subfolder names for video files
    """
    
    def __init__(self, prefs, download_start_time):
        PhotoSubfolder.__init__(self, prefs, download_start_time)
        self.pref_list = prefs.video_subfolder
        self.L1_date_check = VIDEO_DATE  #used in _get_date_component()
    
