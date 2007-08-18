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

import re
import pyexiv2
import datetime

class MetaData(pyexiv2.Image):
    """
    Class providing human readable access to image metadata
    """

    def aperture(self, missing=''):
        """ 
        Returns in string format the floating point value of the image's aperture.
        
        Returns missing if the metadata value is not present.
        """
        try:
            a0, a1 = self["Exif.Photo.FNumber"]
            a = float(a0) / a1
            return "%.1f" % a
        except:
            return missing
            
    def iso(self, missing=''):
        """ 
        Returns in string format the integer value of the image's ISO.
        
        Returns missing if the metadata value is not present.
        """
        try:
            return "%s" % (self["Exif.Photo.ISOSpeedRatings"])
        except:
            return missing
            
    def exposureTime(self, alternativeFormat=False, missing=''):
        """ 
        Returns in string format the exposure time of the image.
        
        Returns missing if the metadata value is not present.
        
        alternativeFormat is useful if the value is going to be  used in a 
        purpose where / is an invalid character, e.g. file system names.  
        
        alternativeFormat is False:
        For exposures less than one second, the result is formatted as a 
        fraction e.g. 1/125
        For exposures greater than or equal to one second, the value is 
        formatted as an integer e.g. 30
        
        alternativeFormat is True:
        For exposures less than one second, the result is formatted as an 
        integer e.g. 125
        For exposures greater than or equal to one second, the value is 
        formatted as an integer with a trailing s e.g. 30s
        """

        try:
            e0, e1 = self["Exif.Photo.ExposureTime"]
            
            if e1 > e0:
                e = float(e1) / e0
                if alternativeFormat:
                    return  "%.0f" % e 
                else:
                    return  "1/%.0f" % e            
            elif e0 > e1:
                e = float(e0) / e1
                if alternativeFormat:
                    return "%.0fs" % e
                else:
                    return "%.0f" % e
            else:
                if alternativeFormat:
                    return "1s"
                else:
                    return "1"
        except:
            return missing
        
    def focalLength(self, missing=''):
        """ 
        Returns in string format the focal length of the lens used to record the image.
        
        Returns missing if the metadata value is not present.
        """
        try:
            f0, f1 = self["Exif.Photo.FocalLength"]
            if not f1:
                f1 = 1
            return "%.0f" % (float(f0) / f1)
        except:
            return missing
            
    def cameraMake(self, missing=''):
        """ 
        Returns in string format the camera make (manufacturer) used to record the image.
        
        Returns missing if the metadata value is not present.
        """
        try:
            return self["Exif.Image.Make"]
        except:
            return missing
    
    def cameraModel(self, missing=''):
        """ 
        Returns in string format the camera model used to record the image.
        
        Returns missing if the metadata value is not present.
        """
        try:
            return self["Exif.Image.Model"]
        except:
            return missing
            
    def shortCameraModel(self, includeCharacters = '', missing=''):
        """ 
        Returns in shorterned string format the camera model used to record the image.
        
        Returns missing if the metadata value is not present.
        
        The short format is determined by the first occurence of a digit in the 
        camera model, including all alphaNumeric characters before and after 
        that digit up till a non-alphanumeric character.
        
        Examples:
        Canon EOS 300D DIGITAL -> 300D
        Canon EOS 5D -> 5D
        NIKON D2X -> D2X
        NIKON D70 -> D70
        X100,D540Z,C310Z -> X100
        
        The optional includeCharacters allows additional characters to appear 
        before and after the digits. 
        Note: special includeCharacters MUST be escaped as per syntax of a 
        regular expressions (see documentation for module re)
       
        Examples:
        
        includeCharacters = '':
        DSC-P92 -> P92 
        includeCharacters = '\-':
        DSC-P92 -> DSC-P92 
        
        If a digit is not found in the camera model, the full length camera 
        model is returned.
        
        Note: assume exif values are in ENGLISH, regardless of current platform
        """
        m = self.cameraModel()
        if m:
            s = r"(?:[^a-zA-Z0-9%s]?)(?P<model>[a-zA-Z0-9%s]*\d+[a-zA-Z0-9%s]*)"\
                % (includeCharacters, includeCharacters, includeCharacters)
            r = re.search(s, m)
            if r:
                return r.group("model")
            else:
                return m
        else:
            return missing
        
    def dateTime(self, missing=''):
        """ 
        Returns in python date time format the date and time the image was recorded.
        
        Returns missing if the metadata value is not present.
        """
        try:
            return self["Exif.Image.DateTime"]
        except:
            return missing
            
    def orientation(self, missing=''):
        """
        Returns the orientation of the image, as recorded by the camera
        """
        try:
            return self['Exif.Image.Orientation']
        except:
            return missing

class DummyMetaData(MetaData):
    """
    Class which gives metadata values for an imaginary image.
    
    Useful for displaying in preference examples etc. when no image is ready to
    be downloaded.
    
    See MetaData class for documentation of class methods.
    """

    def __init__(self):
        pass
        
    def readMetadata(self):
        pass
        
    def aperture(self, missing=''):
        return "2.0"
            
    def iso(self, missing=''):
        return "100"
            
    def exposureTime(self, alternativeFormat=False, missing=''):
        if alternativeFormat:
            return  "4000"
        else:
            return  "1/4000"
        
    def focalLength(self, missing=''):
        return "135"
            
    def cameraMake(self, missing=''):
        return "Canon"
    
    def cameraModel(self, missing=''):
        return "Canon EOS 5D"
            
    def shortCameraModel(self, includeCharacters = '', missing=''):
        return "5D"
        
    def dateTime(self, missing=''):
        return datetime.datetime.now()
        
    def orientation(self, missing=''):
        return 1
            
if __name__ == '__main__':
    import sys
    
    if (len(sys.argv) != 2):
        print 'Usage: ' + sys.argv[0] + ' path/to/photo/containing/metadata'
        m = DummyMetaData()
##        sys.exit(1)
    else:
        m = MetaData(sys.argv[1])
        m.readMetadata()
    print "f"+ m.aperture()
    print "ISO " + m.iso()
    print m.exposureTime() + " sec"
    print m.exposureTime(alternativeFormat=True)
    print m.focalLength() + "mm"
    print m.cameraMake()
    print m.cameraModel()
    print m.shortCameraModel()
    print m.shortCameraModel(includeCharacters = "\-")
    print m.dateTime()
    print m.orientation()

