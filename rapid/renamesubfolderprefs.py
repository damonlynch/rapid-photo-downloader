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

#LIST_IMAGE_RENAME_L0 = [DATE_TIME, TEXT, FILENAME, METADATA, 
#                        SEQUENCE_NUMBER, SEQUENCE_LETTER]

LIST_IMAGE_RENAME_L0 = [DATE_TIME, TEXT, FILENAME, METADATA]

DICT_IMAGE_RENAME_L0 = {
                    DATE_TIME: DICT_DATE_TIME_L1,
                    TEXT: None,
                    FILENAME: DICT_FILENAME_L1,
                    METADATA: DICT_METADATA_L1,
#                    SEQUENCE_NUMBER: DICT_SEQUENCE_NUMBER_L1,
#                    SEQUENCE_LETTER: DICT_SEQUENCE_LETTER_L1,
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

# preference elements that require metadata
# note there is no need to specify lower level elements if a higher level 
# element is necessary for them to be present to begin with
METADATA_ELEMENTS = [METADATA, IMAGE_DATE]

# preference elements that do not require metadata and are not fixed
# as above, there is no need to specify lower level elements if a higher level 
# element is necessary for them to be present to begin with
DYNAMIC_NON_METADATA_ELEMENTS = [TODAY, YESTERDAY, FILENAME, SEQUENCE_NUMBER, SEQUENCE_LETTER]

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
            if i <> ORDER_KEY:
                s += "'" + i + "', "
        return s[:-2]

        
class PrefKeyError(PrefError):
    def __init__(self, error):
        value = error[0]
        expectedValues = self.unpackList(error[1])
        self.message = "Preference value %s is invalid.\nExpected one of %s" % (value, expectedValues)


class PrefValueInvalidError(PrefKeyError):
    def __init__(self, error):
        value = error[0]
        self.message = "Preference value %s is invalid." % (value)
        
class PrefLengthError(PrefError):
    def __init__(self, error):
        self.message = "These preferences are not well formed: %s " % self.unpackList(error)
        
class PrefValueKeyComboError(PrefError):
    def __init__(self, error):    
        self.message = error


def convertDateForStrftime(dateTimeUserChoice):
    try:
        return DATE_TIME_CONVERT[LIST_DATE_TIME_L2.index(dateTimeUserChoice)]
    except:
        raise PrefValueInvalidError(dateTimeUserChoice)



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
            


    def checkPrefsForValidity(self):
        """
        Checks image preferences validity
        """
        return checkPreferenceValid(self.prefsDefnL0, self.prefList)


    def _getDateComponent(self):
        """
        Returns portion of new image / subfolder name based on date time
        """
        
        problem = None
        if self.L1 == IMAGE_DATE:
            d = self.photo.dateTime(missing=None)
            problem = "%s metadata is not present in image" % self.L1.lower()
        elif self.L1 == TODAY:
            d = datetime.datetime.now()
        elif self.L1 == YESTERDAY:
            delta = datetime.timedelta(days = 1)
            d = datetime.datetime.now() - delta
        else:
            raise("Date options invalid")

        if d:
            return (d.strftime(convertDateForStrftime(self.L2)), None)
        else:
            return ('', problem)

    def _getFilenameComponent(self):
        """
        Returns portion of new image / subfolder name based on the file name
        """
        
        name, extenstion = os.path.splitext(self.existingFilename)
        problem = None
        
        if self.L1 == NAME_EXTENSION:
            filename = self.existingFilename
        elif self.L1 == NAME:
                filename = name
        elif self.L1 == EXTENSION:
            if extenstion:
                # keep the period / dot of the extension, so the user does not
                # need to manually specify it
                filename = extenstion
            else:
                filename = ""
                problem = "extension was specified but image name has no extension"
        elif self.L1 == IMAGE_NUMBER:
            n = re.search("(?P<image_number>[0-9]+)", self.existingFilename)
            if not n:
                problem = "image number was specified but image has no number"
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
        else:
            raise TypeError("Invalid metadata option specified")
        if self.L1 in [CAMERA_MAKE, CAMERA_MODEL, SHORT_CAMERA_MODEL,
                        SHORT_CAMERA_MODEL_HYPHEN]:
            if self.L2 == UPPERCASE:
                v = v.upper()
            elif self.L2 == LOWERCASE:
                v = v.lower()
        if not v:
            if self.L1 <> ISO:
                md = self.L1.lower()
            else:
                md = ISO
            problem = "%s metadata is not present in image" % md
        return (v, problem)

    def _getSequenceNumber(self):
        """ Not yet implemented """
        return (None, None)

    def _getSequenceLetter(self):
        """ Not yet implemented """
        return (None, None)
        
    def _getComponent(self):
            if self.L0 == DATE_TIME:
                return self._getDateComponent()
            elif self.L0 == TEXT:
                return (self.L1, None)
            elif self.L0 == FILENAME:
                return self._getFilenameComponent()
            elif self.L0 == METADATA:
                return self._getMetadataComponent()
            elif self.L0 == SEQUENCE_NUMBER:
                return _getSequenceNumber()
            elif self.L0 == SEQUENCE_LETTER:
                return _getSequenceLetter()
            elif self.L0 == SEPARATOR:
                return (os.sep, None)

    def _getValuesFromList(self):
        for i in range(0, len(self.prefList), 3):
            yield (self.prefList[i], self.prefList[i+1], self.prefList[i+2])



    def getStringFromPreferences(self, photo, existingFilename=None, 
                                    stripCharacters = False):
        """
        Generate a filename for the photo in string format based on user prefs.
        
        Returns a tuple of two strings: 
        - the name
        - any problems generating the name.  If blank, there were no problems
        """

        self.photo = photo
        self.existingFilename = existingFilename
            
        name = ''
        problem = ''
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

    def filterPreferences(self):
        """
        Filters out extraneous preference choices
        Expected to be implemented in derived classes when needed
        """
        pass
    
    def needMetaDataToCreateUniqueName(self):
        """
        Returns True if metadata is essential to properly generate an image name
        
        Image names should be unique.  Some images may not have metadata.  If
        only non-dynamic components make up the rest of an image name 
        (e.g. text specified by the user), then relying on metadata will likely 
        produce duplicate names. 
        """
        hasMD = hasDynamic = False
        
        for e in METADATA_ELEMENTS:
            if e in self.prefList:
                hasMD = True
                break
        if hasMD:
            for e in DYNAMIC_NON_METADATA_ELEMENTS:
                if e in self.prefList:
                    hasDynamic = True
                    break
        
        if hasMD and not hasDynamic:
            return True
        else:
            return False
    
    def _createCombo(self, choices):
        combobox = gtk.combo_box_new_text()
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
        
    def getStringFromPreferences(self, photo, existingFilename=None, 
                                    stripCharacters = False):
        """
        Generate a filename for the photo in string format based on user prefs.
        
        Returns a tuple of two strings: 
        - the name
        - any problems generating the name.  If blank, there were no problems
        """

        subfolders, problem = ImageRenamePreferences.getStringFromPreferences(
                                        self, photo, 
                                        existingFilename, stripCharacters)
        # subfolder value must never start with a separator, or else any 
        # os.path.join function call will fail to join a subfolder to its 
        # parent folder
        if subfolders[0] == os.sep:
            subfolders = subfolders[1:]
            
        return (subfolders, problem)

    def needMetaDataToCreateUniqueName(self):
        """
        Returns True if metadata is essential to properly generate subfolders
        
        This will be the case if the only components are metadata and separators
        """

        for e in self.prefList:
            if (not e) and ((e not in METADATA_ELEMENTS) or (e <> SEPARATOR)):
                return True
                    
        return False

    def filterPreferences(self):
        """
        Filters out extraneous preference choices
        """
        continueCheck = True
        while continueCheck:
            continueCheck = False
            if self.prefList[0] == SEPARATOR:
                # Subfolder preferences should not start with a /
                self.prefList = self.prefList[3:]
                continueCheck = True
            elif self.prefList[-3] == SEPARATOR:
                # Subfolder preferences should not end with a /
                self.prefList = self.prefList[:-3]
                continueCheck = True
            else:
                for i in range(0, len(self.prefList) - 3, 3):
                    if self.prefList[i] == SEPARATOR and self.prefList[i+3] == SEPARATOR:
                        # Subfolder preferences should not contain two /s side by side
                        continueCheck = True
                        # note we are messing with the contents of the pref list,
                        # must exit loop and try again
                        self.prefList = self.prefList[:i] + self.prefList[i+3:]
                        break
                        
                
                

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
            # separator is spcified
            L1s = []
            for i in range(0, len(self.prefList), 3):
                L1s.append(self.prefList[i])

            if L1s[0] == SEPARATOR:
                raise PrefValueKeyComboError("Subfolder preferences should not start with a %s" % os.sep)
            elif L1s[-1] == SEPARATOR:
                raise PrefValueKeyComboError("Subfolder preferences should not end with a %s" % os.sep)
            else:
                for i in range(len(L1s) - 1):
                    if L1s[i] == SEPARATOR and L1s[i+1] == SEPARATOR:
                        raise PrefValueKeyComboError("Subfolder preferences should not contain two %ss side by side" % os.sep)
        return v

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
