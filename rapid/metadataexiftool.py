#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2011 Damon Lynch <damonlynch@gmail.com>

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

import subprocess
import json
import datetime, time
import string

import multiprocessing
import logging
logger = multiprocessing.get_logger()

def version_info():
    """returns the version of exiftool being used"""
    try:
        # unfortunately subprocess.check_output does not exist on python 2.6
        proc = subprocess.Popen(['exiftool', '-ver'], stdout=subprocess.PIPE)
        v = proc.communicate()[0].strip()
    except OSError:
        v = None
    return v
    
EXIFTOOL_VERSION = version_info()

class ExifToolMetaData:
    """
    Class to use when a python based metadata parser fails to correctly load
    necessary metadata. Calls exiftool as a subprocess. It is therefore slow,
    but in contrast to exiv2 or kaa metadata, exiftool somtimes gives better
    output.
    """
    def __init__(self, filename):
        self.filename = filename
        self.metadata = None
        self.metadata_string_format = None
        self.exiftool_error = "Error encountered using exiftool with file %s"
        self.exiftool_output = "Unexpected output from exiftool with file %s"
        
    def _get(self, key, missing):
        
        if key == "VideoStreamType" or "FileNumber":
            # special case: want exiftool's string formatting
            if self.metadata_string_format is None:
                try:
                    proc = subprocess.Popen(['exiftool', '-j', self.filename], stdout=subprocess.PIPE)
                    s = proc.communicate()[0]
                except:
                    logger.error(self.exiftool_error, self.filename)
                    return missing
                try:
                    self.metadata_string_format = json.loads(s)
                except:
                    logger.error(self.exiftool_output, self.filename)
                    return missing
                
            try:
                v = self.metadata_string_format[0][key]
            except:
                return missing
            return v
                
        elif self.metadata is None:
            # note: exiftool's string formatting is OFF (-n switch)
            try:
                proc = subprocess.Popen(['exiftool', '-j', '-n', self.filename], stdout=subprocess.PIPE)
                s = proc.communicate()[0]
            except:
                logger.error(self.exiftool_error, self.filename)
                return missing
            try:
                self.metadata = json.loads(s)
            except:
                logger.error(self.exiftool_output, self.filename)
                return missing
            
        try:
            v = self.metadata[0][key]
        except:
            return missing
        return v
        
        
    def date_time(self, missing=''):
        """ 
        Returns in python datetime format the date and time the image was 
        recorded.
        
        Trys to get value from key "DateTimeOriginal"
        If that fails, tries "CreateDate"
        
        Returns missing either metadata value is not present.
        """
        d = self._get('DateTimeOriginal', None)
        if d is None:
            d = self._get('CreateDate', None)
        if d is None:
            d = self._get('FileModifyDate', None)
        if d is not None:
            try:
                # returned value may or may not have a time offset
                # strip it if need be
                dt = d[:19]
                dt = datetime.datetime.strptime(dt, "%Y:%m:%d %H:%M:%S")
            except:
                logger.error("Error reading date metadata with file %s", self.filename)
                return missing
        
            return dt
        else:
            return missing
            
    def time_stamp(self, missing=''):
        """
        Returns a float value representing the time stamp, if it exists
        """
        dt = self.date_time(missing=None)
        if dt:
            # convert it to a time stamp (not optimal, but better than nothing!)
            v = time.mktime(dt.timetuple())
        else:
            v = missing
        return v
        
    def file_number(self, missing=''):
        v = self._get("FileNumber", None)
        if v is not None:
            return str(v)
        else:
            return missing
            
    def width(self, missing=''):
        v = self._get('ImageWidth', None)
        if v is not None:
            return str(v)
        else:
            return missing
        
    def height(self, missing=''):
        v = self._get('ImageHeight', None)
        if v is not None:
            return str(v)
        else:
            return missing
            
    def length(self, missing=''):
        """
        return the duration (length) of the video, rounded to the nearest second, in string format
        """ 
        v = self._get("Duration", None)
        if v is not None:
            try:
                v = float(v)
                v = "%0.f" % v
            except:
                return missing
            return v
        else:
            return missing

    def frames_per_second(self, stream=0, missing=''):
        """
        value stream is ignored (kept for compatibilty with code calling kaa)
        """
        v = self._get("FrameRate", None)
        if v is None:
            v = self._get("VideoFrameRate", None)
            
        if v is None:
            return missing
        try:
            v = '%.0f' % v
        except:
            return missing
        return v
            
    def codec(self, stream=0, missing=''):
        """
        value stream is ignored (kept for compatibilty with code calling kaa)
        """
        v = self._get("VideoStreamType", None)
        if v is None:
            v = self._get("VideoCodec", None)
        if v is not None:
            return v
        else:
            return missing
        
    def fourcc(self, stream=0, missing=''):
        """
        value stream is ignored (kept for compatibilty with code calling kaa)
        """
        return self._get("CompressorID", missing)
        
if __name__ == '__main__':
    import sys
    
    
    if (len(sys.argv) != 2):
        print 'Usage: ' + sys.argv[0] + ' path/to/video/containing/metadata'
        sys.exit(0)

    else:
        m = ExifToolMetaData(sys.argv[1])
        dt = m.date_time()
        print dt
        print "%sx%s" % (m.width(), m.height())
        print m.length()
        print m.frames_per_second()
        print m.codec()
