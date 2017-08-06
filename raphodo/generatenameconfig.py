#!/usr/bin/env python3

# Copyright (C) 2007-2017 Damon Lynch <damonlynch@gmail.com>

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

# Special key in each dictionary which specifies the order of elements.
# It is very important to have a consistent and rational order when displaying 
# these prefs to the user, and dictionaries are unsorted.

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2007-2017, Damon Lynch"

import os
from collections import OrderedDict
from typing import List, Optional, Tuple

from gettext import gettext as _

# PLEASE NOTE: these values are duplicated in a dummy class whose function
# is to have them put into the translation template. If you change the values below
# then you MUST change the value in class i18TranslateMeThanks as well!! 

# *** Level 0, i.e. first column of values presented to user
DATE_TIME = 'Date time'
TEXT = 'Text'
FILENAME = 'Filename'
METADATA = 'Metadata'
SEQUENCES = 'Sequences'
JOB_CODE = 'Job code'

SEPARATOR = os.sep

# *** Level 1, i.e. second column of values presented to user

# Date time
IMAGE_DATE = 'Image date'
TODAY = 'Today'
YESTERDAY = 'Yesterday'
VIDEO_DATE = 'Video date'
DOWNLOAD_TIME = 'Download time'

# File name 
NAME = 'Name'
IMAGE_NUMBER = 'Image number'
VIDEO_NUMBER = 'Video number'

# pre 0.9.0a4 File name values: NAME_EXTENSION, EXTENSION
NAME_EXTENSION = 'Name + extension'

# however extension is used for subfolder generation in all versions
EXTENSION = 'Extension'


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
# Currently the only file number is Exif.CanonFi.FileNumber,
# which is in the format xxx-yyyy, where xxx is the folder and yyyy the image
FILE_NUMBER = 'File number'
OWNER_NAME = 'Owner name'
COPYRIGHT = 'Copyright'
ARTIST = 'Artist'

# Video metadata
CODEC = 'Codec'
WIDTH = 'Width'
HEIGHT = 'Height'
FPS = 'Frames Per Second'
LENGTH = 'Length'

# Image sequences
DOWNLOAD_SEQ_NUMBER = 'Downloads today'
SESSION_SEQ_NUMBER = 'Session number'
SUBFOLDER_SEQ_NUMBER = 'Subfolder number'
STORED_SEQ_NUMBER = 'Stored number'
SEQUENCE_LETTER = 'Sequence letter'

# *** Level 2, i.e. third and final column of values presented to user

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

# File number
FILE_NUMBER_FOLDER = "Folder only"
FILE_NUMBER_ALL = "Folder and file"

# Now, define dictionaries and lists of valid combinations of preferences.

# Level 2

# Date 

SUBSECONDS = 'Subseconds'

# NOTE 1: if changing LIST_DATE_TIME_L2, you MUST update the default
# subfolder preference immediately below
# NOTE 2: if changing LIST_DATE_TIME_L2, you MUST also update
# DATE_TIME_CONVERT below
# NOTE 3: if changing LIST_DATE_TIME_L2, you MUST also update
# PHOTO_SUBFOLDER_MENU_DEFAULTS_CONV 
LIST_DATE_TIME_L2 = [
    'YYYYMMDD',  # 0
    'YYYY-MM-DD',
    'YYYY_MM_DD',  # 2
    'YYMMDD',
    'YY-MM-DD',  # 4
    'YY_MM_DD',
    'MMDDYYYY',  # 6
    'MMDDYY',
    'MMDD',  # 8
    'DDMMYYYY',
    'DDMMYY',  # 10
    'YYYY',
    'YY',  # 12
    'MM',
    'DD',  # 14
    'Month (full)',
    'Month (abbreviated)',  # 16
    'HHMMSS',
    'HHMM',  # 18
    'HH-MM-SS',
    'HH-MM',  # 20
    'HH',
    'MM (minutes)',  # 22
    'SS'
]

LIST_IMAGE_DATE_TIME_L2 = LIST_DATE_TIME_L2 + [SUBSECONDS]

DEFAULT_SUBFOLDER_PREFS = [
    DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[11], '/', '', '', DATE_TIME, IMAGE_DATE,
    LIST_DATE_TIME_L2[0]
]
DEFAULT_VIDEO_SUBFOLDER_PREFS = [
    DATE_TIME, VIDEO_DATE, LIST_DATE_TIME_L2[11], '/', '', '', DATE_TIME,
    VIDEO_DATE, LIST_DATE_TIME_L2[0]
]

DEFAULT_PHOTO_RENAME_PREFS = [FILENAME, NAME, ORIGINAL_CASE]
DEFAULT_VIDEO_RENAME_PREFS = [FILENAME, NAME, ORIGINAL_CASE]

class i18TranslateMeThanks:
    """ this class is never used in actual running code
    Its purpose is to have these values inserted into the program's i18n template file
    
    """

    def __init__(self):
        _('Date time')
        _('Text')
        _('Filename')
        _('Metadata')
        _('Sequences')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#jobcode
        _('Job code')
        _('Image date')
        _('Video date')
        _('Today')
        _('Yesterday')
        # Translators: Download time is the time and date that the download started (when the
        # user clicked the Download button)
        _('Download time')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamefilename
        _('Name')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamefilename
        _('Extension')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamefilename
        _('Image number')
        _('Video number')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamemetadata
        _('Aperture')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamemetadata
        _('ISO')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamemetadata
        _('Exposure time')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamemetadata
        _('Focal length')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamemetadata
        _('Camera make')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamemetadata
        _('Camera model')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamemetadata
        _('Short camera model')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamemetadata
        _('Hyphenated short camera model')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamemetadata
        _('Serial number')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamemetadata
        _('Shutter count')
        # File number currently refers to the Exif value Exif.Canon.FileNumber
        _('File number')
        # Only the folder component of the Exif.Canon.FileNumber value
        _('Folder only')
        # The folder and file component of the Exif.Canon.FileNumber value
        _('Folder and file')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamemetadata
        _('Owner name')
        _('Codec')
        _('Width')
        _('Height')
        _('Length')
        _('Frames Per Second')
        _('Artist')
        _('Copyright')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#sequencenumbers
        _('Downloads today')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#sequencenumbers
        _('Session number')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#sequencenumbers
        _('Subfolder number')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#sequencenumbers
        _('Stored number')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#sequenceletters
        _('Sequence letter')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamefilename
        _('All digits')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamefilename
        _('Last digit')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamefilename
        _('Last 2 digits')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamefilename
        _('Last 3 digits')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamefilename
        _('Last 4 digits')
        # Translators: please not the capitalization of this text, and keep it the same if your
        # language features capitalization
        _("Original Case")
        # Translators: please not the capitalization of this text, and keep it the same if your
        # language features capitalization
        _("UPPERCASE")
        # Translators: please not the capitalization of this text, and keep it the same if your
        # language features capitalization
        _("lowercase")
        _("One digit")
        _("Two digits")
        _("Three digits")
        _("Four digits")
        _("Five digits")
        _("Six digits")
        _("Seven digits")
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('Subseconds')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('YYYYMMDD')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('YYYY-MM-DD')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('YYYY_MM_DD')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('YYMMDD')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('YY-MM-DD')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('YY_MM_DD')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('MMDDYYYY')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('MMDDYY')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('MMDD')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('DDMMYYYY')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('DDMMYY')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('YYYY')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('YY')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('MM')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('DD')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('Month (full)'),
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('Month (abbreviated)'),
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('HHMMSS')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('HHMM')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('HH-MM-SS')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('HH-MM')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('HH')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('MM (minutes)')
        # Translators: for an explanation of what this means,
        # see http://damonlynch.net/rapid/documentation/index.html#renamedateandtime
        _('SS')

    # Convenience values for python datetime conversion using values in


# Default subfolder options that appear in drop-down menu in Destination views
# Any change to PHOTO_SUBFOLDER_MENU_DEFAULTS must also be reflected in 
# PHOTO_SUBFOLDER_MENU_DEFAULTS_CONV

# The following values will be displayed in the menu after an os.sep.join() operation

PHOTO_SUBFOLDER_MENU_DEFAULTS = (
    (_('Date'), _('YYYY'), _('YYYYMMDD')),
    (_('Date (hyphens)'), _('YYYY'), _('YYYY-MM-DD')),
    (_('Date (underscores)'), _('YYYY'), _('YYYY_MM_DD')),
    (_('Date and Job Code'), _('YYYY'), _('YYYYMM_Job Code')),
    (_('Date and Job Code Subfolder'), _('YYYY'), _('YYYYMM'), _('Job Code'))
)

# Any change to PHOTO_SUBFOLDER_MENU_DEFAULTS_CONV must also be reflected in 
# PHOTO_SUBFOLDER_MENU_DEFAULTS

PHOTO_SUBFOLDER_MENU_DEFAULTS_CONV = (
    # 0
    [DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[11],
     '/', '', '', 
     DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[0]
    ],
    # 1
    [DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[11],
     '/', '', '',
     DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[1]
    ],
    # 2
    [DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[11],
     '/', '', '',
     DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[2]
    ],
    # 3
    [DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[11],
     '/', '', '',
     DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[11],
     DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[13],
     TEXT, '_', '',
     JOB_CODE, '', ''],
    # 4
    [DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[11],
     '/', '', '',
     DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[11],
     DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[13],
     '/', '', '',
     JOB_CODE, '', '',
     ],
)

PHOTO_RENAME_MENU_DEFAULTS = (
    (_('Original Filename'), 'IMG_1234'),
    (_('Date-Time and Downloads today'), _('YYYYMMDD-HHMM-1')),
    (_('Date and Downloads today'), _('YYYYMMDD-1')),
    (_('Date-Time and Image number'), _('YYYYMMDD-1234')),
    (_('Date-Time and Job Code'), _('YYYYMMDD-HHMM-Job Code-1')),
    (_('Date and Job Code'), _('YYYYMMDD-Job Code-1'))
)

PHOTO_RENAME_MENU_DEFAULTS_CONV = (
    # 0 Original Filename
    [FILENAME, NAME, ORIGINAL_CASE],
    # 1 Date-Time and Downloads today
    [
        DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[0],
        TEXT, '-', '',
        DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[18],
        TEXT, '-', '',
        SEQUENCES, DOWNLOAD_SEQ_NUMBER, SEQUENCE_NUMBER_1
    ],
    # 2 Date and Downloads today
    [
        DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[0],
        TEXT, '-', '',
        SEQUENCES, DOWNLOAD_SEQ_NUMBER, SEQUENCE_NUMBER_1
    ],
    # 3 Date-Time and Image number
    [
        DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[0],
        TEXT, '-', '',
        DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[18],
        TEXT, '-', '',
        FILENAME, IMAGE_NUMBER, IMAGE_NUMBER_ALL
    ],
    # 4 Date-Time and Job Code
    [
        DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[0],
        TEXT, '-', '',
        DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[18],
        TEXT, '-', '',
        JOB_CODE, '', '',
        TEXT, '-', '',
        SEQUENCES, DOWNLOAD_SEQ_NUMBER, SEQUENCE_NUMBER_1
    ],
    # 5 Date and Job Code
    [
        DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[0],
        TEXT, '-', '',
        JOB_CODE, '', '',
        TEXT, '-', '',
        SEQUENCES, DOWNLOAD_SEQ_NUMBER, SEQUENCE_NUMBER_1
    ]
)

# See notes above regarding keeping values in sync
VIDEO_SUBFOLDER_MENU_DEFAULTS = PHOTO_SUBFOLDER_MENU_DEFAULTS
VIDEO_SUBFOLDER_MENU_DEFAULTS_CONV = (
    # 0
    [
        DATE_TIME, VIDEO_DATE, LIST_DATE_TIME_L2[11],
        SEPARATOR, '', '',
        DATE_TIME, VIDEO_DATE, LIST_DATE_TIME_L2[0]
     ],
    # 1
    [
        DATE_TIME, VIDEO_DATE, LIST_DATE_TIME_L2[11],
        SEPARATOR, '', '',
        DATE_TIME, VIDEO_DATE, LIST_DATE_TIME_L2[1]
     ],
    # 2
    [
        DATE_TIME, VIDEO_DATE, LIST_DATE_TIME_L2[11],
        SEPARATOR, '', '',
        DATE_TIME, VIDEO_DATE, LIST_DATE_TIME_L2[2]
     ],
    # 3
    [
        DATE_TIME, VIDEO_DATE, LIST_DATE_TIME_L2[11],
        SEPARATOR, '', '',
        DATE_TIME, VIDEO_DATE, LIST_DATE_TIME_L2[11],
        DATE_TIME, VIDEO_DATE, LIST_DATE_TIME_L2[13],
        TEXT, '_', '',
        JOB_CODE, '', ''
    ],
    # 4
    [
        DATE_TIME, VIDEO_DATE, LIST_DATE_TIME_L2[11],
        SEPARATOR, '', '',
        DATE_TIME, VIDEO_DATE, LIST_DATE_TIME_L2[11],
        DATE_TIME, VIDEO_DATE, LIST_DATE_TIME_L2[13],
        SEPARATOR, '', '',
        JOB_CODE, '', '',
     ],
)

VIDEO_RENAME_MENU_DEFAULTS = (
    (_('Original Filename'), 'MVI_1234'),
    (_('Date-Time and Downloads today'), _('YYYYMMDD-HHMM-1')),
    (_('Date and Downloads today'), _('YYYYMMDD-1')),
    (_('Date-Time and Video number'), _('YYYYMMDD_1234')),
    (_('Date-Time and Job Code'), _('YYYYMMDD-HHMM-Job Code-1')),
    (_('Date and Job Code'), _('YYYYMMDD-Job Code-1')),
    (_('Resolution'), _('YYYYMMDD-HHMM-1-1920x1080'))
)

VIDEO_RENAME_MENU_DEFAULTS_CONV = (
    # 0 Original Filename
    [FILENAME, NAME, ORIGINAL_CASE],
    # 1 Date-Time and Downloads today
    [
        DATE_TIME, VIDEO_DATE, LIST_DATE_TIME_L2[0],
        TEXT, '-', '',
        DATE_TIME, VIDEO_DATE, LIST_DATE_TIME_L2[18],
        TEXT, '-', '',
        SEQUENCES, DOWNLOAD_SEQ_NUMBER, SEQUENCE_NUMBER_1
    ],
    # 2 Date and Downloads today
    [
        DATE_TIME, VIDEO_DATE, LIST_DATE_TIME_L2[0],
        TEXT, '-', '',
        SEQUENCES, DOWNLOAD_SEQ_NUMBER, SEQUENCE_NUMBER_1
    ],
    # 3 Date-Time and Image number
    [
        DATE_TIME, VIDEO_DATE, LIST_DATE_TIME_L2[0],
        TEXT, '-', '',
        DATE_TIME, VIDEO_DATE, LIST_DATE_TIME_L2[18],
        TEXT, '-', '',
        FILENAME, VIDEO_NUMBER, IMAGE_NUMBER_ALL
    ],
    # 4 Date-Time and Job Code
    [
        DATE_TIME, VIDEO_DATE, LIST_DATE_TIME_L2[0],
        TEXT, '-', '',
        DATE_TIME, VIDEO_DATE, LIST_DATE_TIME_L2[18],
        TEXT, '-', '',
        JOB_CODE, '', '',
        TEXT, '-', '',
        SEQUENCES, DOWNLOAD_SEQ_NUMBER, SEQUENCE_NUMBER_1
    ],
    # 5 Date and Job Code
    [
        DATE_TIME, VIDEO_DATE, LIST_DATE_TIME_L2[0],
        TEXT, '-', '',
        JOB_CODE, '', '',
        TEXT, '-', '',
        SEQUENCES, DOWNLOAD_SEQ_NUMBER, SEQUENCE_NUMBER_1
    ],
    # 6 Resolution
    [
        DATE_TIME, VIDEO_DATE, LIST_DATE_TIME_L2[0],
        TEXT, '-', '',
        DATE_TIME, VIDEO_DATE, LIST_DATE_TIME_L2[18],
        TEXT, '-', '',
        SEQUENCES, DOWNLOAD_SEQ_NUMBER, SEQUENCE_NUMBER_1,
        TEXT, '-', '',
        METADATA, WIDTH, '',
        TEXT, 'x', '',
        METADATA, HEIGHT, ''
    ]
)

# See notes above regarding keeping values in sync
DATE_TIME_CONVERT = [
    '%Y%m%d',  # 0
    '%Y-%m-%d',
    '%Y_%m_%d',  # 2
    '%y%m%d',
    '%y-%m-%d',   # 4
    '%y_%m_%d',
    '%m%d%Y',  # 6
    '%m%d%y',
    '%m%d',  # 8
    '%d%m%Y',
    '%d%m%y', # 10
    '%Y',
    '%y',  # 12
    '%m',
    '%d',  # 14
    '%B',
    '%b',  # 16
    '%H%M%S',
    '%H%M',  # 18
    '%H-%M-%S',
    '%H-%M',  # 20
    '%H',
    '%M',  # 22
    '%S'
]

LIST_IMAGE_NUMBER_L2 = [
    IMAGE_NUMBER_ALL, IMAGE_NUMBER_1, IMAGE_NUMBER_2, IMAGE_NUMBER_3, IMAGE_NUMBER_4
]

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
FILE_NUMBER_L2 = [
    FILE_NUMBER_FOLDER,
    FILE_NUMBER_ALL
]

# Level 1

DICT_DATE_TIME_L1 = OrderedDict(
    [
        (IMAGE_DATE, LIST_IMAGE_DATE_TIME_L2),
        (TODAY, LIST_DATE_TIME_L2),
        (YESTERDAY, LIST_DATE_TIME_L2),
        (DOWNLOAD_TIME, LIST_DATE_TIME_L2),
    ]
)

VIDEO_DICT_DATE_TIME_L1 = OrderedDict(
    [
        (VIDEO_DATE, LIST_IMAGE_DATE_TIME_L2),
        (TODAY, LIST_DATE_TIME_L2),
        (YESTERDAY, LIST_DATE_TIME_L2),
        (DOWNLOAD_TIME, LIST_DATE_TIME_L2),
    ]
)

DICT_FILENAME_L1 = OrderedDict(
    [
        (NAME, LIST_CASE_L2),
        (IMAGE_NUMBER, LIST_IMAGE_NUMBER_L2),
    ]
)

# pre 0.9.0a4 values for DICT_FILENAME_L1:
#(NAME_EXTENSION, LIST_CASE_L2),
# (EXTENSION, LIST_CASE_L2),

DICT_VIDEO_FILENAME_L1 = OrderedDict(
    [
        (NAME, LIST_CASE_L2),
        (VIDEO_NUMBER, LIST_IMAGE_NUMBER_L2),
    ]
)

# pre 0.9.0a4 values for DICT_VIDEO_FILENAME_L1:
# (NAME_EXTENSION, LIST_CASE_L2),
# (EXTENSION, LIST_CASE_L2),

DICT_SUBFOLDER_FILENAME_L1 = {
    EXTENSION: LIST_CASE_L2,
}

DICT_METADATA_L1 = OrderedDict(
    [
        (APERTURE, None),
        (ISO, None),
        (EXPOSURE_TIME, None),
        (FOCAL_LENGTH, None),
        (CAMERA_MAKE, LIST_CASE_L2),
        (CAMERA_MODEL, LIST_CASE_L2),
        (SHORT_CAMERA_MODEL, LIST_CASE_L2),
        (SHORT_CAMERA_MODEL_HYPHEN, LIST_CASE_L2),
        (SERIAL_NUMBER, None),
        (SHUTTER_COUNT, LIST_SHUTTER_COUNT_L2),
        (FILE_NUMBER, FILE_NUMBER_L2),
        (OWNER_NAME, LIST_CASE_L2),
        (ARTIST, LIST_CASE_L2),
        (COPYRIGHT, LIST_CASE_L2),
    ]
)

DICT_VIDEO_METADATA_L1 = OrderedDict(
    [
        (CODEC, LIST_CASE_L2),
        (WIDTH, None),
        (HEIGHT, None),
        (LENGTH, None),
        (FPS, None),
    ]
)

DICT_SEQUENCE_L1 = OrderedDict(
    [
        (DOWNLOAD_SEQ_NUMBER, LIST_SEQUENCE_NUMBERS_L2),
        (STORED_SEQ_NUMBER, LIST_SEQUENCE_NUMBERS_L2),
        (SESSION_SEQ_NUMBER, LIST_SEQUENCE_NUMBERS_L2),
        (SEQUENCE_LETTER, LIST_SEQUENCE_LETTER_L2),
    ]
)

LIST_SEQUENCE_L1 = list(DICT_SEQUENCE_L1.keys())

# Level 0

DICT_IMAGE_RENAME_L0 = OrderedDict(
    [
        (DATE_TIME, DICT_DATE_TIME_L1),
        (TEXT, None),
        (FILENAME, DICT_FILENAME_L1),
        (METADATA, DICT_METADATA_L1),
        (SEQUENCES, DICT_SEQUENCE_L1),
        (JOB_CODE, None),
    ]
)

DICT_VIDEO_RENAME_L0 = OrderedDict(
    [
        (DATE_TIME, VIDEO_DICT_DATE_TIME_L1),
        (TEXT, None),
        (FILENAME, DICT_VIDEO_FILENAME_L1),
        (METADATA, DICT_VIDEO_METADATA_L1),
        (SEQUENCES, DICT_SEQUENCE_L1),
        (JOB_CODE, None),
    ]
)

DICT_SUBFOLDER_L0 = OrderedDict(
    [
        (DATE_TIME, DICT_DATE_TIME_L1),
        (TEXT, None),
        (FILENAME, DICT_SUBFOLDER_FILENAME_L1),
        (METADATA, DICT_METADATA_L1),
        (SEPARATOR, None),
        (JOB_CODE, None),
    ]
)

DICT_VIDEO_SUBFOLDER_L0 = OrderedDict(
    [
        (DATE_TIME, VIDEO_DICT_DATE_TIME_L1),
        (TEXT, None),
        (FILENAME, DICT_SUBFOLDER_FILENAME_L1),
        (METADATA, DICT_VIDEO_METADATA_L1),
        (SEPARATOR, None),
        (JOB_CODE, None),
    ]
)

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
    SEQUENCE_LETTER
]

# preference elements that do not require metadata and are not fixed
# as above, there is no need to specify lower level elements if a higher level 
# element is necessary for them to be present to begin with
DYNAMIC_NON_METADATA_ELEMENTS = [TODAY, YESTERDAY, FILENAME] + SEQUENCE_ELEMENTS

PHOTO_RENAME_COMPLEX = [
    'Date time', 'Image date', 'YYYYMMDD', 'Text', '-', '', 'Date time', 'Image date', 'HHMM',
    'Text', '-', '', 'Sequences', 'Downloads today', 'One digit', 'Text', '-iso', '', 'Metadata',
    'ISO', '', 'Text', '-f', '', 'Metadata', 'Aperture', '', 'Text', '-', '', 'Metadata',
    'Focal length', '', 'Text', 'mm-', '', 'Metadata', 'Exposure time', ''
]
PHOTO_RENAME_SIMPLE = [
    'Date time', 'Image date', 'YYYYMMDD', 'Text', '-', '', 'Date time', 'Image date', 'HHMM',
    'Text', '-', '', 'Sequences', 'Downloads today', 'One digit'
]

VIDEO_RENAME_SIMPLE = [x if x != 'Image date' else 'Video date' for x in PHOTO_RENAME_SIMPLE]

JOB_CODE_RENAME_TEST = ['Job code', '', '', 'Sequences', 'Downloads today', 'One digit']


def upgrade_pre090a4_rename_pref(pref_list: List[str]) -> Tuple[List[str], str]:
    r"""
    Upgrade photo and video rename preference list

    :param pref_list: pref list to upgrade
    :return: tuple of new pref list, and if found, the case to be used for the
     extension

    >>> upgrade_pre090a4_rename_pref([FILENAME, NAME_EXTENSION, ORIGINAL_CASE])
    (['Filename', 'Name', 'Original Case'], 'Original Case')
    >>> upgrade_pre090a4_rename_pref(PHOTO_RENAME_SIMPLE + [FILENAME, EXTENSION, LOWERCASE])
    ... # doctest: +NORMALIZE_WHITESPACE
    (['Date time', 'Image date', 'YYYYMMDD',
      'Text', '-', '',
      'Date time', 'Image date', 'HHMM',
      'Text', '-', '',
      'Sequences', 'Downloads today', 'One digit'], 'lowercase')
    >>> upgrade_pre090a4_rename_pref(PHOTO_RENAME_COMPLEX + [FILENAME, EXTENSION, UPPERCASE])
    ... # doctest: +NORMALIZE_WHITESPACE
    (['Date time', 'Image date', 'YYYYMMDD', 'Text', '-', '',
      'Date time', 'Image date', 'HHMM', 'Text', '-', '', 'Sequences',
      'Downloads today', 'One digit', 'Text', '-iso', '',
      'Metadata', 'ISO', '', 'Text', '-f', '', 'Metadata',
      'Aperture', '', 'Text', '-', '', 'Metadata', 'Focal length', '',
      'Text', 'mm-', '', 'Metadata', 'Exposure time', ''], 'UPPERCASE')
     >>> upgrade_pre090a4_rename_pref([FILENAME, NAME, LOWERCASE])
     (['Filename', 'Name', 'lowercase'], None)

    """
    if not pref_list:
        return (pref_list, None)

    # get extension case from last value
    if pref_list[-2] in (NAME_EXTENSION, EXTENSION):
        case = pref_list[-1]
    else:
        case = None

    new_pref_list = []
    for idx in range(0, len(pref_list), 3):
        l1 = pref_list[idx + 1]
        if  l1 != EXTENSION:
            if l1 == NAME_EXTENSION:
                l1 = NAME
            new_pref_list.extend([pref_list[idx], l1, pref_list[idx + 2]])
    return new_pref_list, case


class PrefError(Exception):
    """ base class """

    def __init__(self):
        super().__init__()
        self.msg = ''

    def unpackList(self, l: List[str]):
        """
        Make the preferences presentable to the user
        """
        return ', '.join("'{}'".format(i) for i in l)

    def __str__(self):
        return self.msg


class PrefKeyError(PrefError):
    def __init__(self, error):
        super().__init__()
        value = error[0]
        expectedValues = self.unpackList(error[1])
        self.msg = "Preference key '%(key)s' is invalid.\nExpected one of %(value)s" % {
            'key': value, 'value': expectedValues}


class PrefValueInvalidError(PrefKeyError):
    def __init__(self, error):
        super().__init__(error)
        value = error[0]
        self.msg = "Preference value '%(value)s' is invalid" % {'value': value}


class PrefLengthError(PrefError):
    def __init__(self, error):
        super().__init__()
        self.msg = "These preferences are not well formed:" + "\n %s" % self.unpackList(error)


class PrefValueKeyComboError(PrefError):
    def __init__(self, error):
        super().__init__()
        self.msg = error


def check_pref_valid(pref_defn, prefs, modulo=3) -> bool:
    """
    Checks to see if user preferences are valid according to their
    definition. Raises appropriate exception if an error is found.

    :param prefs: list of preferences
    :param pref_defn: is a Dict specifying what is valid
    :param modulo: how many list elements are equivalent to one line
    of preferences.
    :return: True if prefs match with pref_defn
    """

    if (len(prefs) % modulo != 0) or not prefs:
        raise PrefLengthError(prefs)
    else:
        for i in range(0, len(prefs), modulo):
            _check_pref_valid(pref_defn, prefs[i:i + modulo])

    return True


def _check_pref_valid(pref_defn, prefs):
    key = prefs[0]
    value = prefs[1]

    if key in pref_defn:

        next_pref_defn = pref_defn[key]

        if value is None:
            # value should never be None, at any time
            raise PrefValueInvalidError((None, next_pref_defn))

        if next_pref_defn and not value:
            raise PrefValueInvalidError((value, next_pref_defn))

        if isinstance(next_pref_defn, dict):
            return _check_pref_valid(next_pref_defn, prefs[1:])
        else:
            if isinstance(next_pref_defn, list):
                result = value in next_pref_defn
                if not result:
                    raise PrefValueInvalidError((value, next_pref_defn))
                return True
            elif not next_pref_defn:
                return True
            else:
                result = next_pref_defn == value
                if not result:
                    raise PrefValueInvalidError((value, next_pref_defn))
                return True
    else:
        raise PrefKeyError((key, list(pref_defn.keys())))


def filter_subfolder_prefs(pref_list: List[str],
                           pref_colors: Optional[List[str]]=None) \
        -> Tuple[bool, List[str], Optional[List[str]]]:
    """
    Filters out extraneous preference choices.

    :param pref_list: the list of user specified preferences
    :param pref_colors: optional list of colors associated with displaying the
     generated sample name while editing the preferences
    :return: bool indicating whether list changed, the pref list, and optionally the
     list of colors
    """

    prefs_changed = False
    continue_check = True
    while continue_check and pref_list:
        continue_check = False
        if pref_list[0] == SEPARATOR:
            # subfolder preferences should not start with a /
            pref_list = pref_list[3:]
            if pref_colors is not None:
                pref_colors = pref_colors[1:]
            prefs_changed = True
            continue_check = True
        elif pref_list[-3] == SEPARATOR:
            # subfolder preferences should not end with a /
            pref_list = pref_list[:-3]
            if pref_colors is not None:
                pref_colors = pref_colors[:-1]
            continue_check = True
            prefs_changed = True
        else:
            for i in range(0, len(pref_list) - 3, 3):
                if pref_list[i] == SEPARATOR and pref_list[i + 3] == SEPARATOR:
                    # subfolder preferences should not contain two /s side by side
                    continue_check = True
                    prefs_changed = True
                    # note we are messing with the contents of the pref list,
                    # must exit loop and try again
                    pref_list = pref_list[:i] + pref_list[i + 3:]
                    if pref_colors is not None:
                        pref_colors = pref_colors[:i//3] + pref_colors[i//3 + 1:]
                    break

    return (prefs_changed, pref_list, pref_colors)
