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

from gettext import gettext as _







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
    
    def _get_filename_component(self):
        """
        Returns portion of new file / subfolder name based on the file name
        """
        
        name, extension = os.path.splitext(self.rpd_file.name)
        
        if self.L1 == NAME_EXTENSION:
            filename = self.rpd_file.name
        elif self.L1 == NAME:
                filename = name
        elif self.L1 == EXTENSION:
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
                self.problem.add_problem(self.component, pn.MISSING_FILE_EXTENSION)
                return ""
        elif self.L1 == IMAGE_NUMBER or self.L1 == VIDEO_NUMBER:
            n = re.search("(?P<image_number>[0-9]+$)", name)
            if not n:
                self.problem.add_problem(self.component, pn.MISSING_IMAGE_NUMBER)
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
            v = self.metadata.aperture()
        elif self.L1 == ISO:
            v = self.metadata.iso()
        elif self.L1 == EXPOSURE_TIME:
            v = self.metadata.exposure_time(alternativeFormat=True)
        elif self.L1 == FOCAL_LENGTH:
            v = self.metadata.focal_length()
        elif self.L1 == CAMERA_MAKE:
            v = self.metadata.camera_make()
        elif self.L1 == CAMERA_MODEL:
            v = self.metadata.camera_model()
        elif self.L1 == SHORT_CAMERA_MODEL:
            v = self.metadata.short_camera_model()
        elif self.L1 == SHORT_CAMERA_MODEL_HYPHEN:
            v = self.metadata.short_camera_model(includeCharacters = "\-")
        elif self.L1 == SERIAL_NUMBER:
            v = self.metadata.camera_serial()
        elif self.L1 == SHUTTER_COUNT:
            v = self.metadata.shutter_count()
            if v:
                v = int(v)
                padding = LIST_SHUTTER_COUNT_L2.index(self.L2) + 3
                formatter = '%0' + str(padding) + "i"
                v = formatter % v
            
        elif self.L1 == OWNER_NAME:
            v = self.metadata.owner_name()
        else:
            raise TypeError("Invalid metadata option specified")
        if self.L1 in [CAMERA_MAKE, CAMERA_MODEL, SHORT_CAMERA_MODEL,
                        SHORT_CAMERA_MODEL_HYPHEN,  OWNER_NAME]:
            if self.L2 == UPPERCASE:
                v = v.upper()
            elif self.L2 == LOWERCASE:
                v = v.lower()
        if not v:
            self.problem.add_problem(self.component, pn.MISSING_METADATA, _(self.L1))
        return v        
        
    def _get_component(self):
        #~ try:
        if True:
            if self.L0 == DATE_TIME:
                return self._get_date_component()
            elif self.L0 == TEXT:
                return self.L1
            elif self.L0 == FILENAME:
                return self._get_filename_component()
            elif self.L0 == METADATA:
                return self._get_metadata_component()
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
        v = video.metadata.codec()
    elif video.L1 == WIDTH:
        v = video.metadata.width()
    elif video.L1 == HEIGHT:
        v = video.metadata.height()
    elif video.L1 == FPS:
        v = video.metadata.framesPerSecond()
    elif video.L1 == LENGTH:
        v = video.metadata.length()
    else:
        raise TypeError("Invalid metadata option specified")
    if video.L1 in [CODEC]:
        if video.L2 == UPPERCASE:
            v = v.upper()
        elif video.L2 == LOWERCASE:
            v = v.lower()
    if not v:
        video.problem.add_problem(video.component, pn.MISSING_METADATA, _(video.L1))
    return v
