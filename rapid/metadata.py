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
import subprocess
import config
import types
import time

try:
    import pyexiv2
except ImportError:
    sys.stderr.write("You need to install pyexiv2, the python binding for exiv2, to run this program.\n" )
    sys.exit(1)
    
#only pyexiv2 <= 0.1.1 does not use the "Rational" class 
if 'Rational' in dir(pyexiv2):
    usesRational = True
else:
    usesRational = False

#get versions of pyexiv2 and exiv2 libraries
if 'version_info' in dir(pyexiv2):
    pyexiv2_version = pyexiv2.version_info
    exiv2_version = pyexiv2.exiv2_version_info
    baseclass = eval('pyexiv2.metadata.ImageMetadata')
else:
    pyexiv2_version = (0,1,'x')
    # try to determine the version of exiv2 from it's standard output
    try:
        proc = subprocess.Popen(['exiv2', '-V'], stdout=subprocess.PIPE)
        output = proc.communicate()[0]
    except:
        output = None
        exiv2_version = None
    if output:
        # assume output contains the line 'exiv2 0.x' or possibly
        # 'exiv2 0.x.x'
        start = output.find('exiv2 ')
        if start < 0:
            exiv2_version = None            
        else:
            end = output.find('\n', start)
            if end:
                exiv2_v = output[6:end]
            else:
                exiv2_v = output[6:]
            
            exiv2_version = []
            dot = exiv2_v.find('.')
            while dot > 0:
                exiv2_version += [int(exiv2_v[:dot])]
                exiv2_v = exiv2_v[dot+1:]
                dot = exiv2_v.find('.')
            exiv2_version += [int(exiv2_v)]
            exiv2_version = tuple(exiv2_version) 
            
        
    baseclass = eval('pyexiv2.Image')

def __version_info(version):
    if not version:
        return ''
    else:
        v = ''
        for i in version:
            v += '.%s' % i
        return v[1:]    
    
def version_info():
    return __version_info(pyexiv2_version)
    
def exiv2_version_info():
    return __version_info(exiv2_version)    

RAW_FILE_EXTENSIONS = ['arw', 'dcr', 'cr2', 'crw',  'dng', 'mos', 'mrw', 
                        'nef', 'orf', 'pef', 'raf', 'raw', 'sr2', 'srw']

#exiv2 0.18.1 introduces support for Panasonic .RW2 files
#pyexiv2 in combination with exiv2 0.18 segfaults when trying to read an
#RW2 files, so we should not read those! exiv2 0.17 & pyexiv2 segfaults
#with MEF files.

if exiv2_version is not None:
    if exiv2_version[0] > 0:
        RAW_FILE_EXTENSIONS += ['rw2', 'mef']
    else:
        if exiv2_version[1] > 17:
            RAW_FILE_EXTENSIONS += ['mef']
        if exiv2_version[1] > 18:
            RAW_FILE_EXTENSIONS += ['rw2']
        else:
            if len(exiv2_version) > 2:
                if exiv2_version[2] >= 1:
                    RAW_FILE_EXTENSIONS += ['rw2']
                
RAW_FILE_EXTENSIONS.sort()

NON_RAW_IMAGE_FILE_EXTENSIONS = ['jpg', 'jpe', 'jpeg', 'tif', 'tiff']


class MetaData(baseclass):
    """
    Class providing human readable access to image metadata

    """
    
    __version01__ = pyexiv2_version[0] == 0 and pyexiv2_version[1] == 1

    def aperture(self, missing=''):
        """ 
        Returns in string format the floating point value of the image's aperture.
        
        Returns missing if the metadata value is not present.
        """
        
        try:
            if  usesRational:
                a = self["Exif.Photo.FNumber"]
                a0,  a1 = str(a).split('/')
            else:
                a0, a1 = self["Exif.Photo.FNumber"]
            a = float(a0) / float(a1)
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
        For exposures less than one second but more than or equal to 
        one tenth of a second, the result is formatted as an integer 
        e.g. 3 representing 3/10 of a second
        For exposures greater than or equal to one second, the value is 
        formatted as an integer with a trailing s e.g. 30s
        """

        try:
            if usesRational:

                e = str(self["Exif.Photo.ExposureTime"])

                e0,  e1 = e.split('/')
                e0 = int(e0)
                e1 = int(e1)
                # some values, e.g. Nikon, are in the format "10/1600"
                if (e0 > 1) and (e0 < e1):
                    e1 = e1 / e0
                    e0 = 1
            else:
                e0, e1 = self["Exif.Photo.ExposureTime"]
            
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
        
    def focalLength(self, missing=''):
        """ 
        Returns in string format the focal length of the lens used to record the image.
        
        Returns missing if the metadata value is not present.
        """
        try:
            if usesRational:
                f = str(self["Exif.Photo.FocalLength"])
                f0,  f1 = f.split('/')
            else:
                f0, f1 = self["Exif.Photo.FocalLength"]
                
            f0 = float(f0)
            if not f1:
                f1 = 1.0
            else:
                f1 = float(f1)

            return "%.0f" % (f0 / f1)
        except:
            return missing
            
            
    def cameraMake(self, missing=''):
        """ 
        Returns in string format the camera make (manufacturer) used to record the image.
        
        Returns missing if the metadata value is not present.
        """
        try:
            return self["Exif.Image.Make"].strip()
        except:
            return missing
    
    def cameraModel(self, missing=''):
        """ 
        Returns in string format the camera model used to record the image.
        
        Returns missing if the metadata value is not present.
        """
        try:
            return self["Exif.Image.Model"].strip()
        except:
            return missing
            
    def cameraSerial(self,  missing=''):
        try:
            keys = self.rpd_keys()
            if 'Exif.Canon.SerialNumber' in keys:
                v = self['Exif.Canon.SerialNumber']
            elif 'Exif.Nikon3.SerialNumber' in keys:
                v = self['Exif.Nikon3.SerialNumber']
            elif 'Exif.OlympusEq.SerialNumber' in keys:
                v = self['Exif.OlympusEq.SerialNumber']
            elif 'Exif.Olympus.SerialNumber' in keys:
                v = self['Exif.Olympus.SerialNumber']
            elif 'Exif.Olympus.SerialNumber2' in keys:
                v = self['Exif.Olympus.SerialNumber2']
            elif 'Exif.Panasonic.SerialNumber' in keys:
                v = self['Exif.Panasonic.SerialNumber']
            elif 'Exif.Fujifilm.SerialNumber' in keys:
                v = self['Exif.Fujifilm.SerialNumber']
            elif 'Exif.Image.CameraSerialNumber' in keys:
                v = self['Exif.Image.CameraSerialNumber']
            else:
                return missing
            return str(v)
        except:
            return missing
            
    def shutterCount(self,  missing=''):
        try:
            keys = self.rpd_keys()
            if 'Exif.Nikon3.ShutterCount' in keys:
                v = self['Exif.Nikon3.ShutterCount']
            elif 'Exif.Canon.FileNumber' in keys:
                v = self['Exif.Canon.FileNumber']
            elif 'Exif.Canon.ImageNumber' in keys:
                v = self['Exif.Canon.ImageNumber']
            else:
                return missing
            return str(v)
        except:
            return missing
            
    def ownerName(self,  missing=''):
        """ returns camera name recorded by select Canon cameras"""
        try:
            return self['Exif.Canon.OwnerName'].strip()
        except:
            return missing
            
    def shortCameraModel(self, includeCharacters = '', missing=''):
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
        m = self.cameraModel()
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
    
    def filterMangledDates(self, d):
        """
        Some EXIF dates are badly formed. Try to fix them
        """
        
        _datetime = d.strip()
        # remove any weird characters at the end of the string
        while _datetime and not _datetime[-1].isdigit():
            _datetime = _datetime[:-1]
        _date,  _time = _datetime.split(' ')
        _datetime = "%s %s" % (_date.replace(":",  "-") ,  _time.replace("-",  ":"))
        try:
            d = datetime.datetime.strptime(_datetime, '%Y-%m-%d %H:%M:%S')
        except:
            d = None
        return d
                
    def dateTime(self, missing=''):
        """ 
        Returns in python datetime format the date and time the image was 
        recorded.
        
        Trys to get value from exif key "Exif.Photo.DateTimeOriginal".
        If that does not exist, trys key "Exif.Image.DateTime"
        
        Returns missing either metadata value is not present.
        """
        keys = self.rpd_keys()
        try:
            if "Exif.Photo.DateTimeOriginal" in keys:
                v = self["Exif.Photo.DateTimeOriginal"]
            else:
                v = self["Exif.Image.DateTime"]
            if isinstance(v, types.StringType):
                v = self.filterMangledDates(v)
                if v is None:
                    v = missing
            return v
        except:
            return missing
            
    def timeStamp(self, missing=''):
        dt = self.dateTime(missing=None)
        if not dt is None:
            try:
                t = dt.timetuple()
                ts = time.mktime(t)
            except:
                ts = missing
        else:
            ts = missing
        return ts
            
    def subSeconds(self,  missing='00'):
        """ returns the subsecond the image was taken, as recorded by the camera"""
        try:
            return str(self["Exif.Photo.SubSecTimeOriginal"])
        except:
            return missing
            
    def orientation(self, missing=''):
        """
        Returns the orientation of the image, as recorded by the camera
        Return type int
        """
        try:
            v = self['Exif.Image.Orientation']
            if isinstance(v, types.StringType):
                # pyexiv2 >= 0.2 returns a string, not an int
                v = int(v)
            return v
        except:
            return missing
            
    # following class methods are designed to cope with using both
    # pyexiv2 0.1.x and pyexiv2 0.2.x
            
    def getThumbnailData(self, max_size_needed=0):
        """
        Returns a thumbnail of the image.
        
        If the image supports multiple thumbnails, and max_size_needed
        is not 0, then it will search for the smallest thumbnail that 
        matches the size required 
        
        The image will be in whatever format the thumbnail itself is, 
        typically a jpeg or tiff.
        """
        if self.__version01__:
            return pyexiv2.Image.getThumbnailData(self)[1]

        else:
            if not self.previews:
                return None, None
            else:
                if max_size_needed:
                    for thumbnail in self.previews:
                        if thumbnail.dimensions[0] >= max_size_needed or thumbnail.dimensions[1] >= max_size_needed:
                            break
                else:
                    thumbnail = self.previews[-1]
                        
                return thumbnail.data
                
    def read(self):
        if self.__version01__:
            self.readMetadata()
        else:
            pyexiv2.metadata.ImageMetadata.read(self)
            
    def rpd_keys(self):
        if self.__version01__:
            return pyexiv2.Image.exifKeys(self)
        else:
            return self.exif_keys
            
    def __getitem__(self, key):
        if self.__version01__:
            v = pyexiv2.Image.__getitem__(self, key)
        else:
            v = pyexiv2.metadata.ImageMetadata.__getitem__(self, key).raw_value
        # strip out null bytes from strings
        if isinstance(v, types.StringType):
            v = v.replace('\x00', '')
        return v
        

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
        
    def cameraSerial(self,  missing=''):
        return '730402168'
        
    def shutterCount(self,  missing=''):
        return '387'
        
    def ownerName(self,  missing=''):
        return 'Photographer Name'
        
    def dateTime(self, missing=''):
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
    print m.exposureTime(missing='missing ') + " sec"
    print m.exposureTime(alternativeFormat=True,  missing='missing ')
    print m.focalLength('missing ') + "mm"
    print m.cameraMake()
    print m.cameraModel()
    print m.shortCameraModel()
    print m.shortCameraModel(includeCharacters = "\-")
    print m.dateTime()
    print m.orientation()
    print 'Serial number:',  m.cameraSerial()
    print 'Shutter count:', m.shutterCount()
    print 'Subseconds:',  m.subSeconds()
    
