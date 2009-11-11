#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2007, 2008, 2009 Damon Lynch <damonlynch@gmail.com>

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

""" Define and test preferences for use in PlusMinus tables.

These are displayed to the user as a series of rows in the user
preferences dialog window.

Preferences for subfolders and image renaming are defined below
in dictionaries and lists. This makes it easier for checking validity and 
creating combo boxes.

There are 3 levels: 0, 1 and 2, which specify the depth of the pref value. 
Level 0 is the topmost level, and corresponds to the first entry in the
row of preferences the user sees in the preferences dialog window.

Custom exceptions are defined to handle invalid preferences.

The user's actual preferences, on the other hand, are stored in flat lists.
Each list has members which are a multiple of 3 in length.  
Each group of 3 members is equal to one line of preferences in the plus minus 
table.
"""
#needed for python 2.5, unneeded for python 2.6
from __future__ import with_statement 

import string 

import os
import re
import sys

import gtk.gdk as gdk

try: 
    import pygtk 
    pygtk.require("2.0") 
except: 
    pass 
try: 
    import gtk 
except: 
    sys.exit(1)

from common import Configi18n
global _
_ = Configi18n._

import datetime

import ValidatedEntry
import config

from common import pythonifyVersion

# Special key in each dictionary which specifies the order of elements.
# It is very important to have a consistent and rational order when displaying 
# these prefs to the user, and dictionaries are unsorted.

ORDER_KEY = "__order__"

# PLEASE NOTE: these values are duplicated in a dummy class whose function
# is to have them put into the translation template. If you change the values below
# then change the value in class i18TranslateMeThanks as well!! Thanks!! 

# *** Level 0
DATE_TIME = 'Date time'
TEXT = 'Text'
FILENAME = 'Filename'
METADATA = 'Metadata'
SEQUENCES = 'Sequences'
JOB_CODE = 'Job code'

SEPARATOR = os.sep

# *** Level 1

# Date time
IMAGE_DATE = 'Image date'
TODAY = 'Today'
YESTERDAY = 'Yesterday'

# File name 
NAME_EXTENSION = 'Name + extension'
NAME =   'Name'
EXTENSION = 'Extension'
IMAGE_NUMBER = 'Image number'

# Metadata
APERTURE = 'Aperture'
ISO = 'ISO'
EXPOSURE_TIME = 'Exposure time'
FOCAL_LENGTH = 'Focal length'
CAMERA_MAKE = 'Camera make'
CAMERA_MODEL = 'Camera model'
SHORT_CAMERA_MODEL = 'Short camera model'
SHORT_CAMERA_MODEL_HYPHEN = 'Hyphenated short camera model'
SERIAL_NUMBER = 'Serial number'
SHUTTER_COUNT = 'Shutter count'
OWNER_NAME = 'Owner name'

#Image sequences
DOWNLOAD_SEQ_NUMBER = 'Downloads today'
SESSION_SEQ_NUMBER = 'Session number'
SUBFOLDER_SEQ_NUMBER = 'Subfolder number'
STORED_SEQ_NUMBER = 'Stored number'

SEQUENCE_LETTER = 'Sequence letter'



# *** Level 2

# Image number
IMAGE_NUMBER_ALL = 'All digits'
IMAGE_NUMBER_1 = 'Last digit'
IMAGE_NUMBER_2 = 'Last 2 digits'
IMAGE_NUMBER_3 = 'Last 3 digits'
IMAGE_NUMBER_4 = 'Last 4 digits'


# Case 
ORIGINAL_CASE = "Original Case"
UPPERCASE = "UPPERCASE"
LOWERCASE = "lowercase"

# Sequence number
SEQUENCE_NUMBER_1 = "One digit"
SEQUENCE_NUMBER_2 = "Two digits"
SEQUENCE_NUMBER_3 = "Three digits"
SEQUENCE_NUMBER_4 = "Four digits"
SEQUENCE_NUMBER_5 = "Five digits"
SEQUENCE_NUMBER_6 = "Six digits"


# Now, define dictionaries and lists of valid combinations of preferences.

# Level 2

# Date 

SUBSECONDS = 'Subseconds'

# ****** note if changing LIST_DATE_TIME_L2, update the default subfolder preference below :D *****
LIST_DATE_TIME_L2 = ['YYYYMMDD', 'YYYY-MM-DD','YYMMDD', 'YY-MM-DD', 
                    'MMDDYYYY', 'MMDDYY', 'MMDD', 
                    'DDMMYYYY', 'DDMMYY', 'YYYY', 'YY', 
                    'MM', 'DD', 
                    'HHMMSS', 'HHMM', 'HH-MM-SS',  'HH-MM',  'HH',  'MM',  'SS']
                    

LIST_IMAGE_DATE_TIME_L2 = LIST_DATE_TIME_L2 + [SUBSECONDS]

DEFAULT_SUBFOLDER_PREFS = [DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[9],  '/',  '', '', DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[0]]

class i18TranslateMeThanks:
    """ this class is never used in actual running code
    It's purpose is to have these values inserted into the program's i18n template file
    
    """
    def __init__(self):
        _('Date time')
        _('Text')
        _('Filename')
        _('Metadata')
        _('Sequences')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#jobcode
        _('Job code')
        _('Image date')
        _('Today')
        _('Yesterday')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamefilename
        _('Name + extension')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamefilename
        _('Name')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamefilename
        _('Extension')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamefilename
        _('Image number')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamemetadata        
        _('Aperture')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamemetadata        
        _('ISO')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamemetadata        
        _('Exposure time')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamemetadata        
        _('Focal length')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamemetadata        
        _('Camera make')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamemetadata        
        _('Camera model')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamemetadata        
        _('Short camera model')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamemetadata
        _('Hyphenated short camera model')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamemetadata
        _('Serial number')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamemetadata
        _('Shutter count')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamemetadata
        _('Owner name')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#sequencenumbers
        _('Downloads today')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#sequencenumbers
        _('Session number')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#sequencenumbers
        _('Subfolder number')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#sequencenumbers
        _('Stored number')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#sequenceletters
        _('Sequence letter')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamefilename
        _('All digits')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamefilename
        _('Last digit')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamefilename
        _('Last 2 digits')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamefilename
        _('Last 3 digits')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamefilename
        _('Last 4 digits')
        # Translators: please not the capitalization of this text, and keep it the same if your language features capitalization
        _("Original Case")
        # Translators: please not the capitalization of this text, and keep it the same if your language features capitalization
        _("UPPERCASE")
        # Translators: please not the capitalization of this text, and keep it the same if your language features capitalization
        _("lowercase")
        _("One digit")
        _("Two digits")
        _("Three digits")
        _("Four digits")
        _("Five digits")
        _("Six digits")
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('Subseconds')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('YYYYMMDD') 
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('YYYY-MM-DD')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('YYMMDD') 
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('YY-MM-DD') 
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('MMDDYYYY') 
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('MMDDYY') 
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('MMDD') 
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('DDMMYYYY') 
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('DDMMYY') 
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('YYYY') 
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('YY') 
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('MM') 
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('DD')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('HHMMSS')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('HHMM')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('HH-MM-SS')        
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('HH-MM') 
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('HH')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('MM') 
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('SS') 
        

# Convenience values for python datetime conversion using values in 
# LIST_DATE_TIME_L2.  Obviously the two must remain synchronized.

DATE_TIME_CONVERT = ['%Y%m%d', '%Y-%m-%d','%y%m%d', '%y-%m-%d', 
                    '%m%d%Y', '%m%d%y', '%m%d',
                    '%d%m%Y', '%d%m%y', '%Y', '%y', 
                    '%m', '%d',
                    '%H%M%S', '%H%M', '%H-%M-%S',  '%H-%M',  
                    '%H',  '%M',  '%S']
                    

LIST_IMAGE_NUMBER_L2 = [IMAGE_NUMBER_ALL, IMAGE_NUMBER_1, IMAGE_NUMBER_2, 
                        IMAGE_NUMBER_3, IMAGE_NUMBER_4]


LIST_CASE_L2 = [ORIGINAL_CASE, UPPERCASE, LOWERCASE]

LIST_SEQUENCE_LETTER_L2 = [
                    UPPERCASE,
                    LOWERCASE
                    ]
                


LIST_SEQUENCE_NUMBERS_L2 = [
                    SEQUENCE_NUMBER_1,
                    SEQUENCE_NUMBER_2,
                    SEQUENCE_NUMBER_3,
                    SEQUENCE_NUMBER_4,
                    SEQUENCE_NUMBER_5,
                    SEQUENCE_NUMBER_6,
                    ]
                


LIST_SHUTTER_COUNT_L2 = [
                     SEQUENCE_NUMBER_3, 
                     SEQUENCE_NUMBER_4, 
                     SEQUENCE_NUMBER_5, 
                     SEQUENCE_NUMBER_6,                      
                     ]

# Level 1
LIST_DATE_TIME_L1 = [IMAGE_DATE, TODAY, YESTERDAY]

DICT_DATE_TIME_L1 = {
                    IMAGE_DATE: LIST_IMAGE_DATE_TIME_L2,
                    TODAY: LIST_DATE_TIME_L2,
                    YESTERDAY: LIST_DATE_TIME_L2,
                    ORDER_KEY: LIST_DATE_TIME_L1
                  }


LIST_FILENAME_L1 = [NAME_EXTENSION, NAME, EXTENSION, IMAGE_NUMBER]

DICT_FILENAME_L1 = {
                    NAME_EXTENSION: LIST_CASE_L2,
                    NAME: LIST_CASE_L2,
                    EXTENSION: LIST_CASE_L2,
                    IMAGE_NUMBER: LIST_IMAGE_NUMBER_L2,
                    ORDER_KEY: LIST_FILENAME_L1
                  }



LIST_SUBFOLDER_FILENAME_L1 = [EXTENSION]

DICT_SUBFOLDER_FILENAME_L1 = {
                    EXTENSION: LIST_CASE_L2,
                    ORDER_KEY: LIST_SUBFOLDER_FILENAME_L1
}

LIST_METADATA_L1 = [APERTURE, ISO, EXPOSURE_TIME, FOCAL_LENGTH, 
                    CAMERA_MAKE, CAMERA_MODEL, 
                    SHORT_CAMERA_MODEL, 
                    SHORT_CAMERA_MODEL_HYPHEN, 
                    SERIAL_NUMBER, 
                    SHUTTER_COUNT, 
                    OWNER_NAME]                  

DICT_METADATA_L1 = {
                    APERTURE: None,
                    ISO: None,
                    EXPOSURE_TIME: None,
                    FOCAL_LENGTH: None,
                    CAMERA_MAKE: LIST_CASE_L2,
                    CAMERA_MODEL: LIST_CASE_L2, 
                    SHORT_CAMERA_MODEL: LIST_CASE_L2, 
                    SHORT_CAMERA_MODEL_HYPHEN: LIST_CASE_L2,
                    SERIAL_NUMBER: None, 
                    SHUTTER_COUNT: LIST_SHUTTER_COUNT_L2, 
                    OWNER_NAME: LIST_CASE_L2, 
                    ORDER_KEY: LIST_METADATA_L1
                }
                     

LIST_SEQUENCE_L1 = [
                    DOWNLOAD_SEQ_NUMBER,  
                    STORED_SEQ_NUMBER, 
                    SESSION_SEQ_NUMBER, 
                    SEQUENCE_LETTER
                    ]
                    
DICT_SEQUENCE_L1 = {
                    DOWNLOAD_SEQ_NUMBER: LIST_SEQUENCE_NUMBERS_L2, 
                    STORED_SEQ_NUMBER: LIST_SEQUENCE_NUMBERS_L2, 
                    SESSION_SEQ_NUMBER: LIST_SEQUENCE_NUMBERS_L2, 
                    SEQUENCE_LETTER: LIST_SEQUENCE_LETTER_L2, 
                    ORDER_KEY: LIST_SEQUENCE_L1
                    }
 

# Level 0


LIST_IMAGE_RENAME_L0 = [DATE_TIME, TEXT, FILENAME, METADATA, 
                        SEQUENCES,  JOB_CODE]
                        

DICT_IMAGE_RENAME_L0 = {
                    DATE_TIME: DICT_DATE_TIME_L1,
                    TEXT: None,
                    FILENAME: DICT_FILENAME_L1,
                    METADATA: DICT_METADATA_L1,
                    SEQUENCES: DICT_SEQUENCE_L1, 
                    JOB_CODE: None, 
                    ORDER_KEY: LIST_IMAGE_RENAME_L0
                    }

LIST_SUBFOLDER_L0 = [DATE_TIME, TEXT, FILENAME, METADATA, JOB_CODE,  SEPARATOR]

DICT_SUBFOLDER_L0 = {
                    DATE_TIME: DICT_DATE_TIME_L1,
                    TEXT: None,
                    FILENAME: DICT_SUBFOLDER_FILENAME_L1,
                    METADATA: DICT_METADATA_L1,
                    JOB_CODE: None, 
                    SEPARATOR: None,
                    ORDER_KEY: LIST_SUBFOLDER_L0
                   }

# preference elements that require metadata
# note there is no need to specify lower level elements if a higher level 
# element is necessary for them to be present to begin with
METADATA_ELEMENTS = [METADATA, IMAGE_DATE]

# preference elements that are sequence numbers or letters             
SEQUENCE_ELEMENTS = [
             DOWNLOAD_SEQ_NUMBER, 
             SESSION_SEQ_NUMBER, 
             SUBFOLDER_SEQ_NUMBER, 
             STORED_SEQ_NUMBER, 
             SEQUENCE_LETTER]

# preference elements that do not require metadata and are not fixed
# as above, there is no need to specify lower level elements if a higher level 
# element is necessary for them to be present to begin with
DYNAMIC_NON_METADATA_ELEMENTS = [
             TODAY, YESTERDAY, 
             FILENAME]  + SEQUENCE_ELEMENTS
             


#the following is what the preferences looked in older versions of the program
#they are here for reference, and for checking the validity of preferences

USER_INPUT = 'User'

DOWNLOAD_SEQ_NUMBER_V_0_0_8_B7 = 'Downloads today'
SESSION_SEQ_NUMBER_V_0_0_8_B7 = 'Session sequence number'
SUBFOLDER_SEQ_NUMBER_V_0_0_8_B7 = 'Subfolder sequence number'
STORED_SEQ_NUMBER_V_0_0_8_B7 = 'Stored sequence number'
SEQUENCE_LETTER_V_0_0_8_B7 = 'Sequence letter'

LIST_SEQUENCE_NUMBERS_L1_L2_V_0_0_8_B7 = [
                    SEQUENCE_NUMBER_1,
                    SEQUENCE_NUMBER_2,
                    SEQUENCE_NUMBER_3,
                    SEQUENCE_NUMBER_4,
                    SEQUENCE_NUMBER_5,
                    SEQUENCE_NUMBER_6,
                    ]
                
DICT_SEQUENCE_NUMBERS_L1_L2_V_0_0_8_B7 = { 
                    SEQUENCE_NUMBER_1: None,
                    SEQUENCE_NUMBER_2: None,
                    SEQUENCE_NUMBER_3: None,
                    SEQUENCE_NUMBER_4: None,
                    SEQUENCE_NUMBER_5: None,
                    SEQUENCE_NUMBER_6: None,
                    ORDER_KEY: LIST_SEQUENCE_NUMBERS_L1_L2_V_0_0_8_B7
                    }

LIST_SEQUENCE_L1_V_0_0_8_B7 = [USER_INPUT]

DICT_SEQUENCE_L1_V_0_0_8_B7 = {
                    USER_INPUT: DICT_SEQUENCE_NUMBERS_L1_L2_V_0_0_8_B7, 
                    ORDER_KEY: LIST_SEQUENCE_L1_V_0_0_8_B7
                    }

LIST_SEQUENCE_LETTER_L1_L1_V_0_0_8_B7 = [
                    UPPERCASE,
                    LOWERCASE
                    ]

DICT_SEQUENCE_LETTER_L1_V_0_0_8_B7 = { 
                    UPPERCASE: None,
                    LOWERCASE: None,
                    ORDER_KEY: LIST_SEQUENCE_LETTER_L1_L1_V_0_0_8_B7
                    }

LIST_IMAGE_RENAME_L0_V_0_0_8_B7 = [DATE_TIME, TEXT, FILENAME, METADATA, 
                        DOWNLOAD_SEQ_NUMBER_V_0_0_8_B7, 
                        SESSION_SEQ_NUMBER_V_0_0_8_B7,  
                        SEQUENCE_LETTER_V_0_0_8_B7]

DICT_IMAGE_RENAME_L0_V_0_0_8_B7 = {
                    DATE_TIME: DICT_DATE_TIME_L1,
                    TEXT: None,
                    FILENAME: DICT_FILENAME_L1,
                    METADATA: DICT_METADATA_L1,
                    DOWNLOAD_SEQ_NUMBER_V_0_0_8_B7: None,
                    SESSION_SEQ_NUMBER_V_0_0_8_B7: None, 
                    SEQUENCE_LETTER_V_0_0_8_B7: DICT_SEQUENCE_LETTER_L1_V_0_0_8_B7,
                    ORDER_KEY: LIST_IMAGE_RENAME_L0_V_0_0_8_B7
                    }

PREVIOUS_IMAGE_RENAME= {
                    '0.0.8~b7': DICT_IMAGE_RENAME_L0_V_0_0_8_B7, 
                    }


# Functions to work with above data

def _getPrevPrefs(oldDefs,  currentDefs,  previousVersion):
    k = oldDefs.keys()
    # if there were other defns, we'd need to figure out which one
    # but currently, there are no others
    # there will be in future, and this code wil be updated then
    version_change = pythonifyVersion(k[0])
    if pythonifyVersion(previousVersion) <= version_change:
        return oldDefs[k[0]]
    else:
        return currentDefs

def _upgradePreferencesToCurrent(prefs,  previousVersion):
    """ checks to see if preferences should be upgraded
    
    returns True if they were upgraded, and the new prefs
    
    VERY IMPORTANT: the new prefs will be a new list, not an inplace 
    modification of the existing preferences! Otherwise, the check on 
    assignment in the prefs.py __setattr__ will not work as expected!!
    """
    upgraded = False
    # code to upgrade from <= 0.0.8~b7 to >= 0.0.8~b8
    p = []
    for i in range(0,  len(prefs),  3):
        if prefs[i] in [SEQUENCE_LETTER_V_0_0_8_B7,  SESSION_SEQ_NUMBER_V_0_0_8_B7]:
            upgraded  = True
            p.append(SEQUENCES)
            if prefs[i] == SEQUENCE_LETTER_V_0_0_8_B7:
                p.append(SEQUENCE_LETTER)
                p.append(prefs[i+1])
            else:
                p.append(SESSION_SEQ_NUMBER)
                p.append(prefs[i+2])
        else:
            p += prefs[i:i+3]
    
    assert(len(prefs)==len(p))
    return (upgraded,  p)
    
    
def upgradePreferencesToCurrent(imageRenamePrefs,  subfolderPrefs,  previousVersion):
    """Upgrades user preferences to current version
    
    returns True if the preferences were upgraded"""
    
    # only check image rename, for now....
    upgraded,  imageRenamePrefs = _upgradePreferencesToCurrent(imageRenamePrefs,  previousVersion)
    return (upgraded,  imageRenamePrefs , subfolderPrefs)
 

def usesJobCode(prefs):
    """ Returns True if the preferences contain a job code, else returns False"""
    for i in range(0,  len(prefs),  3):
        if prefs[i] == JOB_CODE:
            return True
    return False
    
def checkPreferencesForValidity(imageRenamePrefs,  subfolderPrefs,  version=config.version):
    """Returns true if the passed in preferences are valid"""
    
    if version == config.version:
        try:
           checkPreferenceValid(DICT_SUBFOLDER_L0, subfolderPrefs)
           checkPreferenceValid(DICT_IMAGE_RENAME_L0,  imageRenamePrefs)
        except:
            return False
        return True
    else:
        defn = _getPrevPrefs(PREVIOUS_IMAGE_RENAME,  DICT_IMAGE_RENAME_L0,  version)
        try:
            checkPreferenceValid(defn, imageRenamePrefs)
            checkPreferenceValid(DICT_SUBFOLDER_L0, subfolderPrefs)
        except:
            return False
        return True

def checkPreferenceValid(prefDefinition, prefs, modulo=3):
    """
    Checks to see if prefs are valid according to definition.

    prefs is a list of preferences.
    prefDefinition is a Dict specifying what is valid.
    modulo is how many list elements are equivalent to one line of preferences.

    Returns True if prefs match with prefDefinition,
    else raises appropriate error.
    """

    if (len(prefs) % modulo <> 0) or not prefs:
        raise PrefLengthError(prefs)
    else:
        for i in range(0,  len(prefs),  modulo):
            _checkPreferenceValid(prefDefinition, prefs[i:i+modulo])
               
    return True

def _checkPreferenceValid(prefDefinition, prefs):

    key = prefs[0]
    value = prefs[1]


    if prefDefinition.has_key(key):
        
        nextPrefDefinition = prefDefinition[key]
        
        if value == None:
            # value should never be None, at any time
            raise PrefValueInvalidError((None, nextPrefDefinition))

        if nextPrefDefinition and not value:
            raise PrefValueInvalidError((value, nextPrefDefinition))
                    
        if type(nextPrefDefinition) == type({}):
            return _checkPreferenceValid(nextPrefDefinition, prefs[1:])
        else:
            if type(nextPrefDefinition) == type([]):
                result = value in nextPrefDefinition
                if not result:
                    raise PrefValueInvalidError((value, nextPrefDefinition))
                return True
            elif not nextPrefDefinition:
                return True
            else:
                result = nextPrefDefinition == value
                if not result:
                    raise PrefKeyValue((value, nextPrefDefinition))
                return True
    else:
        raise PrefKeyError((key, prefDefinition[ORDER_KEY]))

def filterSubfolderPreferences(prefList):
    """
    Filters out extraneous preference choices
    """
    prefs_changed = False
    continueCheck = True
    while continueCheck and prefList:
        continueCheck = False
        if prefList[0] == SEPARATOR:
            # Subfolder preferences should not start with a /
            prefList = prefList[3:]
            prefs_changed = True
            continueCheck = True
        elif prefList[-3] == SEPARATOR:
            # Subfolder preferences should not end with a /
            prefList = prefList[:-3]
            continueCheck = True
            prefs_changed = True
        else:
            for i in range(0, len(prefList) - 3, 3):
                if prefList[i] == SEPARATOR and prefList[i+3] == SEPARATOR:
                    # Subfolder preferences should not contain two /s side by side
                    continueCheck = True
                    prefs_changed = True
                    # note we are messing with the contents of the pref list,
                    # must exit loop and try again
                    prefList = prefList[:i] + prefList[i+3:]
                    break
                    
    return (prefs_changed,  prefList)


class PrefError(Exception):
    """ base class """
    def unpackList(self, l):
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
        self.msg = _("Preference key '%(key)s' is invalid.\nExpected one of %(value)s") % {
                            'key': value, 'value': expectedValues}


class PrefValueInvalidError(PrefKeyError):
    def __init__(self, error):
        value = error[0]
        self.msg = _("Preference value '%(value)s' is invalid") % {'value': value}
        
class PrefLengthError(PrefError):
    def __init__(self, error):
        self.msg = _("These preferences are not well formed:") % self.unpackList(error) + "\n %s"
        
class PrefValueKeyComboError(PrefError):
    def __init__(self, error):    
        self.msg = error


def convertDateForStrftime(dateTimeUserChoice):
    try:
        return DATE_TIME_CONVERT[LIST_DATE_TIME_L2.index(dateTimeUserChoice)]
    except:
        raise PrefValueInvalidError(dateTimeUserChoice)


class Comboi18n(gtk.ComboBox):
    """ very simple i18n version of the venerable combo box 
    with one column displayed to the user.
    
    This combo box has two columns:
    1. the first contains the actual value and is invisible
    2. the second contains the translation of the first column, and this is what
        the users sees
    """
    def __init__(self):
        liststore = gtk.ListStore(str, str)
        gtk.ComboBox.__init__(self,  liststore)
        cell = gtk.CellRendererText()
        self.pack_start(cell,  True)
        self.add_attribute(cell, 'text', 1)
        
    def append_text(self,  text):
        model = self.get_model()
        model.append((text,  _(text)))
        
    def get_active_text(self):
        model = self.get_model()
        active = self.get_active()
        if active < 0:
            return None
        return model[active][0]        

class ImageRenamePreferences:
    def __init__(self, prefList, parent,  fileSequenceLock=None,  sequences=None):
        """
        Exception raised if preferences are invalid.
        
        This should be caught by calling class."""
        
        self.parent = parent
        self.prefList = prefList

        # use variables for determining sequence numbers
        # there are two possibilities:
        # 1. this code is being called while being run from within a copy photos process
        # 2. it's being called from within the preferences dialog window

        self.fileSequenceLock = fileSequenceLock
        self.sequences = sequences
        
        self.job_code = ''
    
        # derived classes will have their own definitions, do not overwrite
        if not hasattr(self, "prefsDefnL0"):
            self.prefsDefnL0 = DICT_IMAGE_RENAME_L0
            self.defaultPrefs = [FILENAME, NAME_EXTENSION, ORIGINAL_CASE]
            self.defaultRow = self.defaultPrefs
            self.stripForwardSlash = True
            


    def checkPrefsForValidity(self):
        """
        Checks image preferences validity
        """
        
        return checkPreferenceValid(self.prefsDefnL0, self.prefList)
        
    def formatPreferencesForPrettyPrint(self):
        """ returns a string useful for printing the preferences"""
        
        v = ''
        
        for i in range(0,  len(self.prefList),  3):
            if (self.prefList[i+1] or self.prefList[i+2]):
                c = ':'
            else: 
                c = ''
            s = "%s%s " % (self.prefList[i],  c) 
            
            if self.prefList[i+1]:
                s = "%s%s" % (s,  self.prefList[i+1])
            if self.prefList[i+2]:
                s = "%s (%s)" % (s,  self.prefList[i+2])
                                
            v += s + "\n"
        return v
            

    def setJobCode(self,  job_code):
        self.job_code = job_code
        
    def _getDateComponent(self):
        """
        Returns portion of new image / subfolder name based on date time
        """
        
        problem = None
        if self.L1 == IMAGE_DATE:
            if self.L2 == SUBSECONDS:
                d = self.photo.subSeconds()
                problem = _("Subsecond metadata not present in image")
            else:
                d = self.photo.dateTime(missing=None)
                problem = _("%s metadata is not present in image") % self.L1.lower()
        elif self.L1 == TODAY:
            d = datetime.datetime.now()
        elif self.L1 == YESTERDAY:
            delta = datetime.timedelta(days = 1)
            d = datetime.datetime.now() - delta
        else:
            raise("Date options invalid")

        if d:
            if self.L2 <> SUBSECONDS:
                
                if type(d) == type('string'):
                    # will be a string only if the date time could not be converted in the datetime type
                    # try to massage badly formed date / times into a valid value
                    _datetime = d.strip()
                    # remove any weird characters at the end of the string
                    while _datetime and not _datetime[-1].isdigit():
                        _datetime = _datetime[:-1]
                    _date,  _time = _datetime.split(' ')
                    _datetime = "%s %s" % (_date.replace(":",  "-") ,  _time.replace("-",  ":"))
                    try:
                        d = datetime.datetime.strptime(_datetime, '%Y-%m-%d %H:%M:%S')
                    except:
                        v = ''
                        problem = _('Error in date time component. Value %s appears invalid') % ''
                        return (v,  problem)

                try:
                    return (d.strftime(convertDateForStrftime(self.L2)), None)
                except:
                    v = ''
                    problem = _('Error in date time component. Value %s appears invalid') % d
                    return (v,  problem)
            else:
                return (d,  None)
        else:
            return ('', problem)

    def _getFilenameComponent(self):
        """
        Returns portion of new image / subfolder name based on the file name
        """
        
        name, extension = os.path.splitext(self.existingFilename)
        problem = None
        
        if self.L1 == NAME_EXTENSION:
            filename = self.existingFilename
        elif self.L1 == NAME:
                filename = name
        elif self.L1 == EXTENSION:
            if extension:
                if not self.stripInitialPeriodFromExtension:
                    # keep the period / dot of the extension, so the user does not
                    # need to manually specify it
                    filename = extension
                else:
                    # having the period when this is used as a part of a subfolder name
                    # is a bad idea!
                    filename = extension[1:]
            else:
                filename = ""
                problem = _("extension was specified but image name has no extension")
        elif self.L1 == IMAGE_NUMBER:
            n = re.search("(?P<image_number>[0-9]+$)", name)
            if not n:
                problem = _("image number was specified but image filename has no number")
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

        return (filename, problem)
        
    def _getMetadataComponent(self):
        """
        Returns portion of new image / subfolder name based on the metadata
        
        Note: date time metadata found in _getDateComponent()
        """
        
        problem = None
        if self.L1 == APERTURE:
            v = self.photo.aperture()
        elif self.L1 == ISO:
            v = self.photo.iso()
        elif self.L1 == EXPOSURE_TIME:
            v = self.photo.exposureTime(alternativeFormat=True)
        elif self.L1 == FOCAL_LENGTH:
            v = self.photo.focalLength()
        elif self.L1 == CAMERA_MAKE:
            v = self.photo.cameraMake()
        elif self.L1 == CAMERA_MODEL:
            v = self.photo.cameraModel()
        elif self.L1 == SHORT_CAMERA_MODEL:
            v = self.photo.shortCameraModel()
        elif self.L1 == SHORT_CAMERA_MODEL_HYPHEN:
            v = self.photo.shortCameraModel(includeCharacters = "\-")
        elif self.L1 == SERIAL_NUMBER:
            v = self.photo.cameraSerial()
        elif self.L1 == SHUTTER_COUNT:
            v = self.photo.shutterCount()
            if v:
                v = int(v)
                padding = LIST_SHUTTER_COUNT_L2.index(self.L2) + 3
                formatter = '%0' + str(padding) + "i"
                v = formatter % v
            
        elif self.L1 == OWNER_NAME:
            v = self.photo.ownerName()
        else:
            raise TypeError("Invalid metadata option specified")
        if self.L1 in [CAMERA_MAKE, CAMERA_MODEL, SHORT_CAMERA_MODEL,
                        SHORT_CAMERA_MODEL_HYPHEN,  OWNER_NAME]:
            if self.L2 == UPPERCASE:
                v = v.upper()
            elif self.L2 == LOWERCASE:
                v = v.lower()
        if not v:
            if self.L1 <> ISO:
                md = self.L1.lower()
            else:
                md = ISO
            problem = _("%s metadata is not present in image") % md
        return (v, problem)


    def _formatSequenceNo(self,  value,  amountToPad):
        padding = LIST_SEQUENCE_NUMBERS_L2.index(amountToPad) + 1
        formatter = '%0' + str(padding) + "i"
        return formatter % value


    def _calculateLetterSequence(self,  sequence):

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

    def _getSubfolderSequenceNo(self):
        """ 
        Add a sequence number to the filename
       
       * Sequence numbering is per subfolder
       * Assume the user might actually have a (perhaps odd) reason to have more 
          than one subfolder sequence number in the same file name
        """
        
        problem = None
        self.subfolderSeqNoInstanceInFilename += 1

        if self.downloadSubfolder:
            subfolder = self.downloadSubfolder + str(self.subfolderSeqNoInstanceInFilename)
        else:
            subfolder = "__subfolder__" + str(self.subfolderSeqNoInstanceInFilename)
        
        if self.fileSequenceLock:
            with self.fileSequenceLock:
                v = self.sequenceNos.calculate(subfolder)
                v = self.formatSequenceNo(v,  self.L1)
        else:
            v = self.sequenceNos.calculate(subfolder)
            v = self.formatSequenceNo(v,  self.L1)
            
        return (v, problem)

    def _getSessionSequenceNo(self):
        problem = None
        v = self._formatSequenceNo(self.sequences.getSessionSequenceNoUsingCounter(self.sequenceCounter),  self.L2)            
        return (v, problem)

    def _getDownloadsTodaySequenceNo(self):
        problem = None
            
        v = self._formatSequenceNo(self.sequences.getDownloadsTodayUsingCounter(self.sequenceCounter),  self.L2)
        
        return (v, problem)
        
    def _getStoredSequenceNo(self):
        problem = None
        v = self._formatSequenceNo(self.sequences.getStoredSequenceNoUsingCounter(self.sequenceCounter),  self.L2)
        
        return (v,  problem)
        
    def _getSequenceLetter(self):

        problem = None
        v = self._calculateLetterSequence(self.sequences.getSequenceLetterUsingCounter(self.sequenceCounter))
        return (v, problem)

    def _getSequencesComponent(self):
        problem = None
        if self.L1 == DOWNLOAD_SEQ_NUMBER:
            return self._getDownloadsTodaySequenceNo()
        elif self.L1 == SESSION_SEQ_NUMBER:
            return self._getSessionSequenceNo()
        elif self.L1 == SUBFOLDER_SEQ_NUMBER:
            return self._getSubfolderSequenceNo()
        elif self.L1 == STORED_SEQ_NUMBER:
            return self._getStoredSequenceNo()                   
        elif self.L1 == SEQUENCE_LETTER:
            return self._getSequenceLetter()
            
    def _getComponent(self):
        try:
            if self.L0 == DATE_TIME:
                return self._getDateComponent()
            elif self.L0 == TEXT:
                return (self.L1, None)
            elif self.L0 == FILENAME:
                return self._getFilenameComponent()
            elif self.L0 == METADATA:
                return self._getMetadataComponent()
            elif self.L0 == SEQUENCES:
                return self._getSequencesComponent()
            elif self.L0 == JOB_CODE:
                return (self.job_code,  None)
            elif self.L0 == SEPARATOR:
                return (os.sep, None)
        except:
            v = ""
            problem = _("error generating name with component %s") % self.L2
            return (v,  problem)

    def _getValuesFromList(self):
        for i in range(0, len(self.prefList), 3):
            yield (self.prefList[i], self.prefList[i+1], self.prefList[i+2])


    def _generateName(self,  photo,  existingFilename,  stripCharacters,  subfolder,  stripInitialPeriodFromExtension,  sequence):
        self.photo = photo
        self.existingFilename = existingFilename
        self.stripInitialPeriodFromExtension = stripInitialPeriodFromExtension
            
        name = ''
        problem = ''

        #the subfolder in which the image will be downloaded to
        self.downloadSubfolder = subfolder 
        
        self.sequenceCounter = sequence
        
        for self.L0, self.L1, self.L2 in self._getValuesFromList():
            v, p = self._getComponent()
            if v:
                name += v
            if p:
                problem += p + "; "

        if problem:
            # remove final semicolon and space
            problem = problem[:-2] + '.'
            
        if stripCharacters:
            for c in r'\:*?"<>|':
                name = name.replace(c, '')
                
        if self.stripForwardSlash:
            name = name.replace('/', '')
                    
        return (name, problem)

    def generateNameUsingPreferences(self, photo, existingFilename=None, 
                                    stripCharacters = False,  subfolder=None,  
                                    stripInitialPeriodFromExtension=False, 
                                    sequencesPreliminary = True):
        """
        Generate a filename for the photo in string format based on user prefs.
        
        Returns a tuple of two strings: 
        - the name
        - any problems generating the name.  If blank, there were no problems
        """

        if self.sequences:
            if sequencesPreliminary:
                sequence = self.sequences.getPrelimSequence()
            else:
                sequence = self.sequences.getFinalSequence()
        else:
            sequence = 0

        return self._generateName(photo,  existingFilename,  stripCharacters,  subfolder,  
                                    stripInitialPeriodFromExtension,  sequence)

    def generateNameSequencePossibilities(self, photo, existingFilename, 
                                    stripCharacters=False,  subfolder=None,  
                                    stripInitialPeriodFromExtension=False):
                                   
        """ Generates the possible image names using the sequence numbers / letter possibilities"""
                                    
        for sequence in self.sequences.getSequencePossibilities():
            yield self._generateName(photo,  existingFilename, stripCharacters , subfolder, 
                                    stripInitialPeriodFromExtension,  sequence)

    def filterPreferences(self):
        """
        Filters out extraneous preference choices
        Expected to be implemented in derived classes when needed
        """
        pass
    
    def needImageMetaDataToCreateUniqueName(self):
        """
        Returns True if an image's metadata is essential to properly generate a unique image name
        
        Image names should be unique.  Some images may not have metadata.  If
        only non-dynamic components make up the rest of an image name 
        (e.g. text specified by the user), then relying on metadata will likely 
        produce duplicate names. 
        
        File extensions are not considered dynamic.
        
        This is NOT a general test to see if unique filenames can be generated. It is a test
        to see if an image's metadata is needed.
        """
        hasMD = hasDynamic = False
        
        for e in METADATA_ELEMENTS:
            if e in self.prefList:
                hasMD = True
                break
    
        if hasMD:
            for e in DYNAMIC_NON_METADATA_ELEMENTS:
                if e in self.prefList:
                    if e == FILENAME and (NAME_EXTENSION in self.prefList or 
                                                                NAME in self.prefList or
                                                                IMAGE_NUMBER in self.prefList):
                        hasDynamic = True
                        break
        
        if hasMD and not hasDynamic:
            return True
        else:
            return False
            
    def usesSequenceElements(self):
        """ Returns true if any sequence numbers or letters are used to generate the filename """
        
        for e in SEQUENCE_ELEMENTS:
            if e in self.prefList:
                return True
                
        return False
        
    def usesTheSequenceElement(self,  e):
        """ Returns true if a stored sequence number is used to generate the filename """
        return e in self.prefList
            
    
    def _createCombo(self, choices):
        combobox = Comboi18n()
        for text in choices:
            combobox.append_text(text)
        return combobox
        
    def getDefaultRow(self):
        """ 
        returns a list of default widgets
        """
        return self.getWidgetsBasedOnUserSelection(self.defaultRow)

    def _getPreferenceWidgets(self, prefDefinition, prefs, widgets):
        key = prefs[0]
        value = prefs[1]
        
        # supply a default value if the user has not yet chosen a value!
        if not key:
            key = prefDefinition[ORDER_KEY][0]
            
        if not key in prefDefinition:
            raise PrefKeyError((key, prefDefinition.keys()))


        list0 = prefDefinition[ORDER_KEY]

        # the first widget will always be a combo box
        widget0 = self._createCombo(list0)
        widget0.set_active(list0.index(key))
        
        widgets.append(widget0)
        
        if key == TEXT:
            widget1 = gtk.Entry()
            widget1.set_text(value)
            
            widgets.append(widget1)
            widgets.append(None)
            return
        elif key in [SEPARATOR,  JOB_CODE]:
            widgets.append(None)
            widgets.append(None)
            return
        else:
            nextPrefDefinition = prefDefinition[key]
            if type(nextPrefDefinition) == type({}):
                return self._getPreferenceWidgets(nextPrefDefinition, 
                                            prefs[1:], 
                                            widgets)
            else:
                if type(nextPrefDefinition) == type([]):
                    widget1 = self._createCombo(nextPrefDefinition)
                    if not value:
                        value = nextPrefDefinition[0]
                    try:
                        widget1.set_active(nextPrefDefinition.index(value))
                    except:
                        raise PrefValueInvalidError((value, nextPrefDefinition))
                    
                    widgets.append(widget1)
                else:
                    widgets.append(None)
    
    def getWidgetsBasedOnPreferences(self):
        """ 
        Yields a list of widgets and their callbacks based on the users preferences.
       
        This list is equivalent to one row of preferences when presented to the 
        user in the Plus Minus Table.
        """
        
        for L0, L1, L2 in self._getValuesFromList():
            prefs = [L0, L1, L2]
            widgets = []
            self._getPreferenceWidgets(self.prefsDefnL0, prefs, widgets)
            yield widgets
        

    def getWidgetsBasedOnUserSelection(self, selection):
        """
        Returns a list of widgets and their callbacks based on what the user has selected.
        
        Selection is the values the user has chosen thus far in comboboxes.
        It determines the contents of the widgets returned.
        It should be a list of three values, with None for values not chosen.
        For values which are None, the first value in the preferences
        definition is chosen.
        
        """
        widgets = []
            
        self._getPreferenceWidgets(self.prefsDefnL0, selection, widgets)
        return widgets

class SubfolderPreferences(ImageRenamePreferences):
    def __init__(self, prefList, parent):
        self.prefsDefnL0 = DICT_SUBFOLDER_L0
        self.defaultPrefs = DEFAULT_SUBFOLDER_PREFS
        self.defaultRow = [DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[0]]
        self.stripForwardSlash = False
        ImageRenamePreferences.__init__(self, prefList, parent)
        
    def generateNameUsingPreferences(self, photo, existingFilename=None, 
                                    stripCharacters = False):
        """
        Generate a filename for the photo in string format based on user prefs.
        
        Returns a tuple of two strings: 
        - the name
        - any problems generating the name.  If blank, there were no problems
        """

        subfolders, problem = ImageRenamePreferences.generateNameUsingPreferences(
                                        self, photo, 
                                        existingFilename, stripCharacters,  stripInitialPeriodFromExtension=True)
        # subfolder value must never start with a separator, or else any 
        # os.path.join function call will fail to join a subfolder to its 
        # parent folder
        if subfolders:
            if subfolders[0] == os.sep:
                subfolders = subfolders[1:]
            
        return (subfolders, problem)

    def filterPreferences(self):
        filtered,  prefList = filterSubfolderPreferences(self.prefList)
        if filtered:
            self.prefList = prefList
            
    def needMetaDataToCreateUniqueName(self):
        """
        Returns True if metadata is essential to properly generate subfolders
        
        This will be the case if the only components are metadata and separators
        """

        for e in self.prefList:
            if (not e) and ((e not in METADATA_ELEMENTS) or (e <> SEPARATOR)):
                return True
                    
        return False

                        


    def checkPrefsForValidity(self):
        """
        Checks subfolder preferences validity above and beyond image name checks.
        
        See parent method for full description.
        
        Subfolders have additional requirments to that of image names.
        """
        v = ImageRenamePreferences.checkPrefsForValidity(self)
        if v:
            # peform additional checks:
            # 1. do not start with a separator
            # 2. do not end with a separator
            # 3. do not have two separators in a row
            # these three rules will ensure something else other than a 
            # separator is specified
            L1s = []
            for i in range(0, len(self.prefList), 3):
                L1s.append(self.prefList[i])

            if L1s[0] == SEPARATOR:
                raise PrefValueKeyComboError(_("Subfolder preferences should not start with a %s") % os.sep)
            elif L1s[-1] == SEPARATOR:
                raise PrefValueKeyComboError(_("Subfolder preferences should not end with a %s") % os.sep)
            else:
                for i in range(len(L1s) - 1):
                    if L1s[i] == SEPARATOR and L1s[i+1] == SEPARATOR:
                        raise PrefValueKeyComboError(_("Subfolder preferences should not contain two %s one after the other") % os.sep)
        return v


class Sequences:
    """ Holds sequence numbers and letters used in generating filenames"""
    def __init__(self,  downloadsToday,  storedSequenceNo):

        
        self.subfolderSequenceNo = {}
        self.sessionSequenceNo = 1
        self.sequenceLetter = 0
    
        self.setUseOfSequenceElements(False,  False)
        
        self.assignedSequenceCounter = 1
        self.reset(downloadsToday,  storedSequenceNo)

    def setUseOfSequenceElements(self,  usesSessionSequenceNo,  usesSequenceLetter):
        self.usesSessionSequenceNo = usesSessionSequenceNo
        self.usesSequenceLetter = usesSequenceLetter
        
    def reset(self,  downloadsToday,  storedSequenceNo):
        self.downloadsToday = downloadsToday
        self.downloadsTodayOffset = 0
        self.storedSequenceNo = storedSequenceNo
        if self.usesSessionSequenceNo:
            self.sessionSequenceNo = self.sessionSequenceNo + self.assignedSequenceCounter - 1
        if self.usesSequenceLetter:
            self.sequenceLetter = self.sequenceLetter + self.assignedSequenceCounter - 1
        self.doNotAddToPool = False
        self.pool = []        
        self.poolSequenceCounter = 0
        self.assignedSequenceCounter = 1

    def getPrelimSequence(self):
        if self.doNotAddToPool:
            self.doNotAddToPool = False
        else:
            # increment pool sequence number
            self.poolSequenceCounter += 1
            self.pool.append(self.poolSequenceCounter)
            
        return self.poolSequenceCounter

    def getFinalSequence(self):
        # get oldest queue value
        # remove from queue or flag it should be removed
        
        return self.assignedSequenceCounter
        
    def getSequencePossibilities(self):
        for i in self.pool:
            yield i
            
    def getSessionSequenceNo(self):
        return self.sessionSequenceNo + self.assignedSequenceCounter - 1

    def getSessionSequenceNoUsingCounter(self,  counter):
        return self.sessionSequenceNo + counter - 1
        
    def setSessionSequenceNo(self,  value):
        self.sessionSequenceNo = value
        
    def setStoredSequenceNo(self,  value):
        self.storedSequenceNo = value
                
    def getDownloadsTodayUsingCounter(self,  counter):
        return self.downloadsToday + counter - self.downloadsTodayOffset
        
    def setDownloadsToday(self,  value):
        self.downloadsToday = value
        self.downloadsTodayOffset = self.assignedSequenceCounter - 1
        
    def getStoredSequenceNoUsingCounter(self,  counter):
        return self.storedSequenceNo + counter

    def getSequenceLetterUsingCounter(self,  counter):
        return self.sequenceLetter + counter - 1
        
    def imageCopyFailed(self):
        self.doNotAddToPool = True

    def imageCopySucceeded(self):
        self.increment()
    
    def increment(self,  subfolder=None):
        assert(self.assignedSequenceCounter == self.pool[0])
        self.assignedSequenceCounter += 1
        self.pool = self.pool[1:]
        
        

        
if __name__ == '__main__':
    import sys
    import os.path
    from metadata import MetaData

    if False:
        if (len(sys.argv) != 2):
            print 'Usage: ' + sys.argv[0] + ' path/to/photo/containing/metadata'
            sys.exit(1)
        else:
            p0 = [FILENAME, NAME_EXTENSION, ORIGINAL_CASE]
            p1 = [FILENAME, NAME_EXTENSION, LOWERCASE]
            p2 = [METADATA, APERTURE, None]
            p3 = [FILENAME, IMAGE_NUMBER, IMAGE_NUMBER_ALL]
            p4 = [METADATA, CAMERA_MODEL, ORIGINAL_CASE]
            p5 = [TEXT, '-', None]
            p6 = [TEXT, 'Job', None]
            
            p = [p0, p1, p2, p3, p4]
            p = [p6 + p5 + p2 + p5 + p3]
            
            d0 = [DATE_TIME,  IMAGE_DATE,  'YYYYMMDD']
            d1 = [DATE_TIME,  IMAGE_DATE,  'HHMMSS']
            d2 = [DATE_TIME,  IMAGE_DATE,  SUBSECONDS]
            
            d = [d0 + d1 + d2]
            
            fullpath = sys.argv[1]
            path, filename = os.path.split(fullpath)
            
            m = MetaData(fullpath)
            m.readMetadata()
                
            for pref in p:
                i = ImageRenamePreferences(pref,  None)
                print i.generateNameUsingPreferences(m, filename)

            for pref in d:
                i = ImageRenamePreferences(pref,  None)
                print i.generateNameUsingPreferences(m, filename)
    else:
        prefs = [SEQUENCES,  SESSION_SEQ_NUMBER,  SEQUENCE_NUMBER_3]
#        prefs = ['Filename2',  NAME_EXTENSION, UPPERCASE]
        print checkPreferenceValid(DICT_IMAGE_RENAME_L0,  prefs)
