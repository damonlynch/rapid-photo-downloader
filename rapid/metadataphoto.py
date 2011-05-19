#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2007-10 Damon Lynch <damonlynch@gmail.com>

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
import datetime
import sys
import config
import types
import time

try:
    import pyexiv2
except ImportError:
    sys.stderr.write("You need to install pyexiv2, the python binding for exiv2, to run this program.\n" )
    sys.exit(1)
    


def __version_info(version):
    if not version:
        return ''
    else:
        v = ''
        for i in version:
            v += '.%s' % i
        return v[1:]    
    
def pyexiv2_version_info():
    return __version_info(pyexiv2.version_info)
    
def exiv2_version_info():
    return __version_info(pyexiv2.exiv2_version_info)    


class MetaData(pyexiv2.metadata.ImageMetadata):
    """
    Class providing human readable access to image metadata

    """
    
    def aperture(self, missing=''):
        """ 
        Returns in string format the floating point value of the image's aperture.
        
        Returns missing if the metadata value is not present.
        """
        
        try:

            a = self["Exif.Photo.FNumber"].value

            a = float(a.numerator) / float(a.denominator)
            return "%.1f" % a
        except:
            return missing
            
    def iso(self, missing=''):
        """ 
        Returns in string format the integer value of the image's ISO.
        
        Returns missing if the metadata value is not present.
        """
        try:
            return self["Exif.Photo.ISOSpeedRatings"].human_value
        except:
            return missing
            
    def exposure_time(self, alternativeFormat=False, missing=''):
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
        For exposures less than one second but more than or equal to 
        one tenth of a second, the result is formatted as an integer 
        e.g. 3 representing 3/10 of a second
        For exposures greater than or equal to one second, the value is 
        formatted as an integer with a trailing s e.g. 30s
        """

        try:

            e = self["Exif.Photo.ExposureTime"].value

            e0 = int(e.numerator)
            e1 = int(e.denominator)

            if e1 > e0:
                if alternativeFormat:
                    if e0 == 1:
                        return str(e1)
                    else:
                        return  str(e0)
                else:
                    return "%s/%s" % (e0,e1)
            elif e0 > e1:
                e = float(e0) / e1
                if alternativeFormat:
                    return "%.0fs" % e
                else:
                    return "%.0f" % e
            else:
                    return "1s"
        except:
            return missing
        
    def focal_length(self, missing=''):
        """ 
        Returns in string format the focal length of the lens used to record the image.
        
        Returns missing if the metadata value is not present.
        """
        try:
            f = self["Exif.Photo.FocalLength"].value
            f0 = float(f.numerator)
            f1 = float(f.denominator)
                
            return "%.0f" % (f0 / f1)
        except:
            return missing
            
            
    def camera_make(self, missing=''):
        """ 
        Returns in string format the camera make (manufacturer) used to record the image.
        
        Returns missing if the metadata value is not present.
        """
        try:
            return self["Exif.Image.Make"].value.strip()
        except:
            return missing
    
    def camera_model(self, missing=''):
        """ 
        Returns in string format the camera model used to record the image.
        
        Returns missing if the metadata value is not present.
        """
        try:
            return self["Exif.Image.Model"].value.strip()
        except:
            return missing
            
    def camera_serial(self,  missing=''):
        try:
            keys = self.exif_keys
            if 'Exif.Canon.SerialNumber' in keys:
                v = self['Exif.Canon.SerialNumber'].raw_value
            elif 'Exif.Nikon3.SerialNumber' in keys:
                v = self['Exif.Nikon3.SerialNumber'].raw_value
            elif 'Exif.OlympusEq.SerialNumber' in keys:
                v = self['Exif.OlympusEq.SerialNumber'].raw_value
            elif 'Exif.Olympus.SerialNumber' in keys:
                v = self['Exif.Olympus.SerialNumber'].raw_value
            elif 'Exif.Olympus.SerialNumber2' in keys:
                v = self['Exif.Olympus.SerialNumber2'].raw_value
            elif 'Exif.Panasonic.SerialNumber' in keys:
                v = self['Exif.Panasonic.SerialNumber'].raw_value
            elif 'Exif.Fujifilm.SerialNumber' in keys:
                v = self['Exif.Fujifilm.SerialNumber'].raw_value
            elif 'Exif.Image.CameraSerialNumber' in keys:
                v = self['Exif.Image.CameraSerialNumber'].raw_value
            else:
                return missing
            v = str(v) # probably not necessary, but just in case
            return v.strip()
        except:
            return missing
            
    def shutter_count(self,  missing=''):
        try:
            keys = self.exif_keys
            if 'Exif.Nikon3.ShutterCount' in keys:
                v = self['Exif.Nikon3.ShutterCount'].raw_value
            elif 'Exif.Canon.FileNumber' in keys:
                v = self['Exif.Canon.FileNumber'].raw_value
            elif 'Exif.Canon.ImageNumber' in keys:
                v = self['Exif.Canon.ImageNumber'].raw_value
            else:
                return missing
            return str(v)
        except:
            return missing
            
    def owner_name(self,  missing=''):
        """ returns camera name recorded by select Canon cameras"""
        try:
            return self['Exif.Canon.OwnerName'].value.strip()
        except:
            return missing
            
    def copyright(self, missing=''):
        """returns copyright exif information"""
        try:
            return self['Exif.Image.Copyright'].value.strip()
        except:
            return missing
            
    def artist(self, missing=''):
        """returns exif artis information"""
        try:
            return self['Exif.Image.Artist'].value.strip()
        except:
            return missing
            
    def short_camera_model(self, includeCharacters = '', missing=''):
        """ 
        Returns in shorterned string format the camera model used to record the image.
        
        Returns missing if the metadata value is not present.
        
        The short format is determined by the first occurrence of a digit in the 
        camera model, including all alphaNumeric characters before and after 
        that digit up till a non-alphanumeric character, but with these interventions:
        
        1. Canon "Mark" designations are shortened prior to conversion.
        2. Names like "Canon EOS DIGITAL REBEL XSi" do not have a number and must
            and treated differently (see below)
        
        Examples:
        Canon EOS 300D DIGITAL -> 300D
        Canon EOS 5D -> 5D
        Canon EOS 5D Mark II -> 5DMkII
        NIKON D2X -> D2X
        NIKON D70 -> D70
        X100,D540Z,C310Z -> X100
        Canon EOS DIGITAL REBEL XSi -> XSi
        Canon EOS Digital Rebel XS -> XS
        Canon EOS Digital Rebel XTi -> XTi
        Canon EOS Kiss Digital X -> Digital
        Canon EOS Digital Rebel XT -> XT
        EOS Kiss Digital -> Digital        
        Canon Digital IXUS Wireless -> Wireless
        Canon Digital IXUS i zoom -> zoom
        Canon EOS Kiss Digital N -> N
        Canon Digital IXUS IIs -> IIs
        IXY Digital L -> L
        Digital IXUS i -> i
        IXY Digital -> Digital
        Digital IXUS -> IXUS
        
        The optional includeCharacters allows additional characters to appear 
        before and after the digits. 
        Note: special includeCharacters MUST be escaped as per syntax of a 
        regular expressions (see documentation for module re)
       
        Examples:
        
        includeCharacters = '':
        DSC-P92 -> P92 
        includeCharacters = '\-':
        DSC-P92 -> DSC-P92 
        
        If a digit is not found in the camera model, the last word is returned.
        
        Note: assume exif values are in ENGLISH, regardless of current platform
        """
        m = self.camera_model()
        m = m.replace(' Mark ', 'Mk') 
        if m:
            s = r"(?:[^a-zA-Z0-9%s]?)(?P<model>[a-zA-Z0-9%s]*\d+[a-zA-Z0-9%s]*)"\
                % (includeCharacters, includeCharacters, includeCharacters)
            r = re.search(s, m)
            if r:
                return r.group("model")
            else:
                head,  space,  model = m.strip().rpartition(' ')
                return model
        else:
            return missing

    
    def date_time(self, missing=''):
        """ 
        Returns in python datetime format the date and time the image was 
        recorded.
        
        Trys to get value from exif key "Exif.Photo.DateTimeOriginal".
        If that does not exist, trys key "Exif.Image.DateTime"
        
        Returns missing either metadata value is not present.
        """
        try:
            if "Exif.Photo.DateTimeOriginal" in self.exif_keys:
                v = self["Exif.Photo.DateTimeOriginal"].value
            else:
                v = self["Exif.Image.DateTime"].value

            return v
        except:
            return missing
            
    def time_stamp(self, missing=''):
        dt = self.date_time(missing=None)
        if not dt is None:
            try:
                t = dt.timetuple()
                ts = time.mktime(t)
            except:
                ts = missing
        else:
            ts = missing
        return ts
            
    def sub_seconds(self,  missing='00'):
        """ returns the subsecond the image was taken, as recorded by the camera"""
        try:
            return str(self["Exif.Photo.SubSecTimeOriginal"].value)
        except:
            return missing
            
    def orientation(self, missing=''):
        """
        Returns the orientation of the image, as recorded by the camera
        Return type int
        """
        try:
            v = self['Exif.Image.Orientation'].value
            if isinstance(v, types.StringType):
                v = int(v)
            return v
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
            
    def exposure_time(self, alternativeFormat=False, missing=''):
        if alternativeFormat:
            return  "4000"
        else:
            return  "1/4000"
        
    def focal_length(self, missing=''):
        return "135"
            
    def camera_make(self, missing=''):
        return "Canon"
    
    def camera_model(self, missing=''):
        return "Canon EOS 5D"
            
    def short_camera_model(self, includeCharacters = '', missing=''):
        return "5D"
        
    def camera_serial(self,  missing=''):
        return '730402168'
        
    def shutter_count(self,  missing=''):
        return '387'
        
    def owner_name(self,  missing=''):
        return 'Photographer Name'
        
    def date_time(self, missing=''):
        return datetime.datetime.now()
        
    def subSeconds(self,  missing='00'):
        return '57'
        
    def orientation(self, missing=''):
        return 1
            
if __name__ == '__main__':
    import sys
    
    
    if (len(sys.argv) != 2):
        print 'Usage: ' + sys.argv[0] + ' path/to/photo/containing/metadata'
        m = DummyMetaData()

    else:
        m = MetaData(sys.argv[1])
        m.read()
        
    print "f"+ m.aperture('missing ')
    print "ISO " + m.iso('missing ')
    print m.exposure_time(missing='missing ') + " sec"
    print m.exposure_time(alternativeFormat=True,  missing='missing ')
    print m.focal_length('missing ') + "mm"
    print m.camera_make()
    print m.camera_model()
    print m.short_camera_model()
    print m.short_camera_model(includeCharacters = "\-")
    print m.date_time()
    print m.orientation()
    print 'Serial number:',  m.camera_serial()
    print 'Shutter count:', m.shutter_count()
    print 'Subseconds:',  m.sub_seconds()
    
