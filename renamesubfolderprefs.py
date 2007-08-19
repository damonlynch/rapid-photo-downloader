#!/usr/bin/env python
# -*- coding: latin1 -*-

### Copyright (C) 2007 Damon Lynch <damonlynch@gmail.com>

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

Preferences for subfolders and image renaming are defined 
in dictionaries and lists.

This makes it easier for checking validity and creating combo boxes.

There are 3 levels, 0, 1 and 2, which specify the depth of the pref value.

Custom exceptions are defined to handle invalid preferences.

The user's actual preferences, on the other hand, are stored in flat lists.
Each list has members which are a multiple of 3 in length.  
Each group of 3 members is equal to one line of preferences in the plus minus 
table.
"""

import os
import re

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

# Special key in each dictionary which specifies the order of elements.
# It is very important to have a consistent and rational order when displaying 
# these prefs to the user, and dictionaries are unsorted.

ORDER_KEY = "__order__"

# *** Level 0
DATE_TIME = 'Date time'
TEXT = 'Text'
FILENAME = 'Filename'
METADATA = 'Metadata'
SEQUENCE_NUMBER = 'Sequence number'
SEQUENCE_LETTER = 'Sequence letter'
SEPARATOR = os.sep

# *** Level 1

# Date time
IMAGE_DATE = 'Image date'
TODAY = 'Today'
YESTERDAY = 'Yesterday'

# No need for text Level 1

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

# Sequence letter
SEQUENCE_LETTER_1 = "One characters"
SEQUENCE_LETTER_2 = "Two characters"
SEQUENCE_LETTER_3 = "Three characters"
SEQUENCE_LETTER_4 = "Four characters"
SEQUENCE_LETTER_5 = "Five characters"
SEQUENCE_LETTER_6 = "Six characters"


# Now, define dictionaries and lists of valid combinations of preferences.

# Level 2

# Date 

LIST_DATE_TIME_L2 = ['YYYYMMDD', 'YYMMDD', 'MMDDYYYY', 'MMDDYY', 'MMDD', 
                    'DDMMYYYY', 'DDMMYY', 'YYYY', 'YY', 
                    'MM', 'DD', 
                    'HHMMSS', 'HHMM']

# Convenience values for python datetime conversion using values in 
# LIST_DATE_TIME_L2.  Obviously the two must remain synchronized.

DATE_TIME_CONVERT = ['%Y%m%d', '%y%m%d', '%m%d%Y', '%m%d%y', '%m%d',
                    '%d%m%Y', '%d%m%y', '%Y', '%y', 
                    '%m', '%d',
                    '%H%M%S', '%H%M']

LIST_IMAGE_NUMBER_L2 = [IMAGE_NUMBER_ALL, IMAGE_NUMBER_1, IMAGE_NUMBER_2, 
                        IMAGE_NUMBER_3, IMAGE_NUMBER_4]



LIST_CASE_L2 = [ORIGINAL_CASE, UPPERCASE, LOWERCASE]

# Level 1
LIST_DATE_TIME_L1 = [IMAGE_DATE, TODAY, YESTERDAY]

DICT_DATE_TIME_L1 = {
                    IMAGE_DATE: LIST_DATE_TIME_L2,
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
                    SHORT_CAMERA_MODEL_HYPHEN]                  

DICT_METADATA_L1 = {
                    APERTURE: None,
                    ISO: None,
                    EXPOSURE_TIME: None,
                    FOCAL_LENGTH: None,
                    CAMERA_MAKE: LIST_CASE_L2,
                    CAMERA_MODEL: LIST_CASE_L2, 
                    SHORT_CAMERA_MODEL: LIST_CASE_L2, 
                    SHORT_CAMERA_MODEL_HYPHEN: LIST_CASE_L2,
                    ORDER_KEY: LIST_METADATA_L1
                }

LIST_SEQUENCE_NUMBER_L1 = [
                    SEQUENCE_NUMBER_1,
                    SEQUENCE_NUMBER_2,
                    SEQUENCE_NUMBER_3,
                    SEQUENCE_NUMBER_4,
                    SEQUENCE_NUMBER_5,
                    SEQUENCE_NUMBER_6,
                    ]
                
                
DICT_SEQUENCE_NUMBER_L1 = { 
                    SEQUENCE_NUMBER_1: None,
                    SEQUENCE_NUMBER_2: None,
                    SEQUENCE_NUMBER_3: None,
                    SEQUENCE_NUMBER_4: None,
                    SEQUENCE_NUMBER_5: None,
                    SEQUENCE_NUMBER_6: None,
                    ORDER_KEY: LIST_SEQUENCE_NUMBER_L1
                    }

LIST_SEQUENCE_LETTER_L1 = [
                    SEQUENCE_LETTER_1,
                    SEQUENCE_LETTER_2,
                    SEQUENCE_LETTER_3,
                    SEQUENCE_LETTER_4,
                    SEQUENCE_LETTER_5,
                    SEQUENCE_LETTER_6,
                    ]
                
                
DICT_SEQUENCE_LETTER_L1 = { 
                    SEQUENCE_LETTER_1: None,
                    SEQUENCE_LETTER_2: None,
                    SEQUENCE_LETTER_3: None,
                    SEQUENCE_LETTER_4: None,
                    SEQUENCE_LETTER_5: None,
                    SEQUENCE_LETTER_6: None,
                    ORDER_KEY: LIST_SEQUENCE_LETTER_L1
                    }

# Level 0

LIST_IMAGE_RENAME_L0 = [DATE_TIME, TEXT, FILENAME, METADATA, 
                        SEQUENCE_NUMBER, SEQUENCE_LETTER]

DICT_IMAGE_RENAME_L0 = {
                    DATE_TIME: DICT_DATE_TIME_L1,
                    TEXT: None,
                    FILENAME: DICT_FILENAME_L1,
                    METADATA: DICT_METADATA_L1,
                    SEQUENCE_NUMBER: DICT_SEQUENCE_NUMBER_L1,
                    SEQUENCE_LETTER: DICT_SEQUENCE_LETTER_L1,
                    ORDER_KEY: LIST_IMAGE_RENAME_L0
                    }


LIST_SUBFOLDER_L0 = [DATE_TIME, TEXT, FILENAME, METADATA, SEPARATOR]

DICT_SUBFOLDER_L0 = {
                    DATE_TIME: DICT_DATE_TIME_L1,
                    TEXT: None,
                    FILENAME: DICT_SUBFOLDER_FILENAME_L1,
                    METADATA: DICT_METADATA_L1,
                    SEPARATOR: None,
                    ORDER_KEY: LIST_SUBFOLDER_L0
                   }



# Functions to work with above data
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
        return _checkPreferenceValid(prefDefinition, prefs)

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

class PrefError(Exception):
    """ base class """
    def unpackList(self, l):
        s = ''
        for i in l:
            s += "'" + i + "', "
        return s[:-2]

        
class PrefKeyError(PrefError):
    def __init__(self, error):
        value = error[0]
        expectedValues = self.unpackList(error[1])
        self.message = "Preference value %s is invalid.\nExpected one of %s" % (value, expectedValues)


class PrefValueInvalidError(PrefKeyError):
    pass
        
class PrefLengthError(PrefError):
    def __init__(self, error):
        self.message = "These preferences are not well formed: %s " % self.unpackList(error)
    

def convertDateForStrftime(dateTimeUserChoice):
    try:
        return DATE_TIME_CONVERT[LIST_DATE_TIME_L2.index(dateTimeUserChoice)]
    except:
        raise PrefValueInvalidError(dateTimeUserChoice, LIST_DATE_TIME_L2)



class ImageRenamePreferences:
    def __init__(self, prefList, parent):
        """
        Exception raised if preferences are invalid.
        
        This should be caught by calling class."""
        
        self.parent = parent
        self.prefList = prefList
    
        # derived classes will have their own definitions, do not overwrite
        if not hasattr(self, "prefsDefnL0"):
            self.prefsDefnL0 = DICT_IMAGE_RENAME_L0
            self.defaultPrefs = [FILENAME, NAME_EXTENSION, ORIGINAL_CASE]
            self.defaultRow = self.defaultPrefs
            self.stripForwardSlash = True
            
        try:
            self.checkPrefsForValidity()
        except (PrefKeyError, PrefValueInvalidError), inst:
            print inst.message
            print "Resetting to default values."
            self.prefList = self.defaultPrefs
        except PrefLengthError, inst:
            print inst.message
            print "Resetting to default values."
            self.prefList = self.defaultPrefs

    def checkPrefsForValidity(self):
        """
        Checks preferences validity
        """
        checkPreferenceValid(self.prefsDefnL0, self.prefList)


    def _getDateComponent(self):
        if self.L1 == IMAGE_DATE:
            d = self.photo.dateTime(missing=None)
        elif self.L1 == TODAY:
            d = datetime.datetime.now()
        elif self.L1 == YESTERDAY:
            delta = datetime.timedelta(days = 1)
            d = datetime.datetime.now() - delta
        else:
            raise("Date options invalid")

        if d:
            return d.strftime(convertDateForStrftime(self.L2))
        else:
            return ''

    def _getFilenameComponent(self):
        name, extenstion = os.path.splitext(self.existingFilename)
        if self.L1 == NAME_EXTENSION:
            filename = self.existingFilename
        elif self.L1 == NAME:
                filename = name
        elif self.L1 == EXTENSION:
            if extenstion:
                # remove the period / dot
                filename = extenstion[1:]
            else:
                filename = ""
        elif self.L1 == IMAGE_NUMBER:
            n = re.search("(?P<image_number>[0-9]+)", self.existingFilename)
            if n:
                image_number = n.group("image_number")
            else:
                return None
            if self.L2 == IMAGE_NUMBER_ALL:
                return image_number
            elif self.L2 == IMAGE_NUMBER_1:
                return image_number[-1]
            elif self.L2 == IMAGE_NUMBER_2:
                return image_number[-2:]
            elif self.L2 == IMAGE_NUMBER_3:
                return image_number[-3:]
            elif self.L2 == IMAGE_NUMBER_4:
                return image_number[-4:]
        else:
            raise TypeError("Incorrect filename option")

        if self.L2 == ORIGINAL_CASE:
            return filename
        elif self.L2 == UPPERCASE:
            return filename.upper()
        elif self.L2 == LOWERCASE:
            return filename.lower()


    def _getMetadataComponent(self):
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
        else:
            raise TypeError("Invalid metadata option specified")
        if self.L1 in [CAMERA_MAKE, CAMERA_MODEL, SHORT_CAMERA_MODEL,
                        SHORT_CAMERA_MODEL_HYPHEN]:
            if self.L2 == UPPERCASE:
                v = v.upper()
            elif self.L2 == LOWERCASE:
                v = v.lower()
        return v

    def _getTextComponent(self):
        return self.L1

    def _getSequenceNumber(self):
        pass

    def _getComponent(self):
            if self.L0 == DATE_TIME:
                return self._getDateComponent()
            elif self.L0 == TEXT:
                return self._getTextComponent()
            elif self.L0 == FILENAME:
                return self._getFilenameComponent()
            elif self.L0 == METADATA:
                return self._getMetadataComponent()
            elif self.L0 == SEPARATOR:
                return os.sep

    def _getValuesFromList(self):
        for i in range(0, len(self.prefList), 3):
            yield (self.prefList[i], self.prefList[i+1], self.prefList[i+2])



    def getStringFromPreferences(self, photo, existingFilename=None, 
                                    stripCharacters = False):
        """
        Returns a filename for the photo in string format based on user prefs.
        """

        self.photo = photo
        self.existingFilename = existingFilename
            
        name = ''
        for self.L0, self.L1, self.L2 in self._getValuesFromList():
            v = self._getComponent()
            if v:
                name += v

        if stripCharacters:
            for c in r'\:*?"<>|':
                name = name.replace(c, '')
                
        if self.stripForwardSlash:
            name = name.replace('/', '')
            
        return name

    def _createCombo(self, choices):
        combobox = gtk.combo_box_new_text()
        for text in choices:
            combobox.append_text(text)
        return combobox
        
    def getDefaultRow(self):
        return self.getWidgetsBasedOnUserSelection(self.defaultRow)

        
    def _getPreferenceWidgets(self, prefDefinition, prefs, widgets):
        key = prefs[0]
        value = prefs[1]

        # supply a default value if the user has not yet chosen a value!
        if not key:
            key = prefDefinition[ORDER_KEY][0]
            
        if not prefDefinition.has_key(key):
            raise PrefKeyError(key, prefDefinition.keys())


        list0 = prefDefinition[ORDER_KEY]
        
        widget0 = self._createCombo(list0)
        widget0.set_active(list0.index(key))
        
        widgets.append(widget0)
        
        
        if key == TEXT:
            widget1 = gtk.Entry()
            widget1.set_text(value)
            
            widgets.append(widget1)
            widgets.append(None)
            return
        elif key == SEPARATOR:
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
                        raise PrefValueInvalidError(value, nextPrefDefinition)
                    
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
        
        List elements a tuple in form (widget, callback_id)        
        """
        widgets = []
            
        self._getPreferenceWidgets(self.prefsDefnL0, selection, widgets)
        return widgets

class SubfolderPreferences(ImageRenamePreferences):
    def __init__(self, prefList, parent):
        self.prefsDefnL0 = DICT_SUBFOLDER_L0
        self.defaultPrefs = [DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[0]]
        self.defaultRow = self.defaultPrefs
        self.stripForwardSlash = False
        ImageRenamePreferences.__init__(self, prefList, parent)
        


if __name__ == '__main__':
    import sys, os.path
    from metadata import MetaData
    
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
        
        fullpath = sys.argv[1]
        path, filename = os.path.split(fullpath)
        
        m = MetaData(fullpath)
        m.readMetadata()
            
        for pref in p:
            i = ImageRenamePreferences(pref)
            print i.getStringFromPreferences(m, filename)
