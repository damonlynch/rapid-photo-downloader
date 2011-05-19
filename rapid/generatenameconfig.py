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

# Special key in each dictionary which specifies the order of elements.
# It is very important to have a consistent and rational order when displaying 
# these prefs to the user, and dictionaries are unsorted.

import os

from gettext import gettext as _

ORDER_KEY = "__order__"

# PLEASE NOTE: these values are duplicated in a dummy class whose function
# is to have them put into the translation template. If you change the values below
# then you MUST change the value in class i18TranslateMeThanks as well!! 

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
VIDEO_DATE = 'Video date'
DOWNLOAD_TIME = 'Download time'

# File name 
NAME_EXTENSION = 'Name + extension'
NAME =   'Name'
EXTENSION = 'Extension'
IMAGE_NUMBER = 'Image number'
VIDEO_NUMBER = 'Video number'

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
COPYRIGHT = 'Copyright'
ARTIST = 'Artist'

# Video metadata
CODEC = 'Codec'
WIDTH = 'Width'
HEIGHT = 'Height'
FPS = 'Frames Per Second'
LENGTH = 'Length'

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
SEQUENCE_NUMBER_7 = "Seven digits"


# Now, define dictionaries and lists of valid combinations of preferences.

# Level 2

# Date 

SUBSECONDS = 'Subseconds'

# ****** NOTE 1: if changing LIST_DATE_TIME_L2, you MUST update the default subfolder preference below *****
# ****** NOTE 2: if changing LIST_DATE_TIME_L2, you MUST update DATE_TIME_CONVERT below *****
LIST_DATE_TIME_L2 = ['YYYYMMDD', 'YYYY-MM-DD','YYMMDD', 'YY-MM-DD', 
                    'MMDDYYYY', 'MMDDYY', 'MMDD', 
                    'DDMMYYYY', 'DDMMYY', 'YYYY', 'YY', 
                    'MM', 'DD', 
                    'HHMMSS', 'HHMM', 'HH-MM-SS',  'HH-MM',  'HH',  'MM (minutes)',  'SS']
                    

LIST_IMAGE_DATE_TIME_L2 = LIST_DATE_TIME_L2 + [SUBSECONDS]

DEFAULT_SUBFOLDER_PREFS = [DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[9], '/',  '', '', DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[0]]
DEFAULT_VIDEO_SUBFOLDER_PREFS = [DATE_TIME, VIDEO_DATE, LIST_DATE_TIME_L2[9], '/',  '', '', DATE_TIME, VIDEO_DATE, LIST_DATE_TIME_L2[0]]

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
        _('Video date')
        _('Today')
        _('Yesterday')
        # Translators: Download time is the time and date that the download started (when the user clicked the Download button)
        _('Download time')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamefilename
        _('Name + extension')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamefilename
        _('Name')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamefilename
        _('Extension')
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#renamefilename
        _('Image number')
        _('Video number')
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
        _('Codec')
        _('Width')
        _('Height')
        _('Length')
        _('Frames Per Second')
        _('Artist')
        _('Copyright')
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
        _("Seven digits")
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
        _('MM (minutes)') 
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
                    SEQUENCE_NUMBER_7,
                    ]
                


LIST_SHUTTER_COUNT_L2 = [
                     SEQUENCE_NUMBER_3, 
                     SEQUENCE_NUMBER_4, 
                     SEQUENCE_NUMBER_5, 
                     SEQUENCE_NUMBER_6,                      
                     ]

# Level 1
LIST_DATE_TIME_L1 = [IMAGE_DATE, TODAY, YESTERDAY, DOWNLOAD_TIME]
LIST_VIDEO_DATE_TIME_L1 = [VIDEO_DATE, TODAY, YESTERDAY, DOWNLOAD_TIME]

DICT_DATE_TIME_L1 = {
                    IMAGE_DATE: LIST_IMAGE_DATE_TIME_L2,
                    TODAY: LIST_DATE_TIME_L2,
                    YESTERDAY: LIST_DATE_TIME_L2,
                    DOWNLOAD_TIME: LIST_DATE_TIME_L2,
                    ORDER_KEY: LIST_DATE_TIME_L1
                  }
                  
VIDEO_DICT_DATE_TIME_L1 = {
                    VIDEO_DATE: LIST_IMAGE_DATE_TIME_L2,
                    TODAY: LIST_DATE_TIME_L2,
                    YESTERDAY: LIST_DATE_TIME_L2,
                    DOWNLOAD_TIME: LIST_DATE_TIME_L2,
                    ORDER_KEY: LIST_VIDEO_DATE_TIME_L1
                  }


LIST_FILENAME_L1 = [NAME_EXTENSION, NAME, EXTENSION, IMAGE_NUMBER]

DICT_FILENAME_L1 = {
                    NAME_EXTENSION: LIST_CASE_L2,
                    NAME: LIST_CASE_L2,
                    EXTENSION: LIST_CASE_L2,
                    IMAGE_NUMBER: LIST_IMAGE_NUMBER_L2,
                    ORDER_KEY: LIST_FILENAME_L1
                  }

LIST_VIDEO_FILENAME_L1 = [NAME_EXTENSION, NAME, EXTENSION, VIDEO_NUMBER]

DICT_VIDEO_FILENAME_L1 = {
                    NAME_EXTENSION: LIST_CASE_L2,
                    NAME: LIST_CASE_L2,
                    EXTENSION: LIST_CASE_L2,
                    VIDEO_NUMBER: LIST_IMAGE_NUMBER_L2,
                    ORDER_KEY: LIST_VIDEO_FILENAME_L1
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
                    OWNER_NAME,
                    ARTIST,
                    COPYRIGHT]
                    
LIST_VIDEO_METADATA_L1 = [CODEC, WIDTH, HEIGHT, LENGTH, FPS]

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
                    ARTIST: LIST_CASE_L2,
                    COPYRIGHT: LIST_CASE_L2,
                    ORDER_KEY: LIST_METADATA_L1
                }

DICT_VIDEO_METADATA_L1 = {
                    CODEC: LIST_CASE_L2,
                    WIDTH: None,
                    HEIGHT: None,
                    LENGTH: None,
                    FPS: None,
                    ORDER_KEY: LIST_VIDEO_METADATA_L1
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
                        
LIST_VIDEO_RENAME_L0 = LIST_IMAGE_RENAME_L0
                        

DICT_IMAGE_RENAME_L0 = {
                    DATE_TIME: DICT_DATE_TIME_L1,
                    TEXT: None,
                    FILENAME: DICT_FILENAME_L1,
                    METADATA: DICT_METADATA_L1,
                    SEQUENCES: DICT_SEQUENCE_L1, 
                    JOB_CODE: None, 
                    ORDER_KEY: LIST_IMAGE_RENAME_L0
                    }
                    
DICT_VIDEO_RENAME_L0 = {
                    DATE_TIME: VIDEO_DICT_DATE_TIME_L1,
                    TEXT: None,
                    FILENAME: DICT_VIDEO_FILENAME_L1,
                    METADATA: DICT_VIDEO_METADATA_L1,
                    SEQUENCES: DICT_SEQUENCE_L1,
                    JOB_CODE: None,
                    ORDER_KEY: LIST_VIDEO_RENAME_L0
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
                                      
LIST_VIDEO_SUBFOLDER_L0 = [DATE_TIME, TEXT, FILENAME, METADATA, JOB_CODE,  SEPARATOR]
                   
DICT_VIDEO_SUBFOLDER_L0 = {
                    DATE_TIME: VIDEO_DICT_DATE_TIME_L1,
                    TEXT: None,
                    FILENAME: DICT_SUBFOLDER_FILENAME_L1,
                    METADATA: DICT_VIDEO_METADATA_L1,
                    JOB_CODE: None, 
                    SEPARATOR: None,
                    ORDER_KEY: LIST_VIDEO_SUBFOLDER_L0
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
