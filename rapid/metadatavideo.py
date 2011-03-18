#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2007-11 Damon Lynch <damonlynch@gmail.com>

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

DOWNLOAD_VIDEO = True

import os
import datetime
import time
import subprocess
import tempfile

import multiprocessing
import logging
logger = multiprocessing.get_logger()

import gtk
import paths

import rpdfile

try:
    from hachoir_core.cmd_line import unicodeFilename
    from hachoir_parser import createParser
    from hachoir_metadata import extractMetadata
except ImportError:
    DOWNLOAD_VIDEO = False


if DOWNLOAD_VIDEO:

    def version_info():
        from hachoir_metadata.version import VERSION
        return VERSION
        
    def get_video_THM_file(full_filename):
        """
        Checks to see if a thumbnail file (THM) is in the same directory as the 
        file. Expects a full path to be part of the file name.
        
        Returns the filename, including path, if found, else returns None.
        """
        
        f = None
        name, ext = os.path.splitext(full_filename)
        for e in rpdfile.VIDEO_THUMBNAIL_FILE_EXTENSIONS:
            if os.path.exists(name + '.' + e):
                f = name + '.' + e
                break
            if os.path.exists(name + '.' + e.upper()):
                f = name + '.' + e.upper()
                break
            
        return f        

    class VideoMetaData():
        def __init__(self, filename):
            """
            Initialize by loading metadata using hachoir
            """
            
            self.filename = filename
            self.u_filename = unicodeFilename(filename)
            self.parser = createParser(self.u_filename, self.filename)
            self.metadata = extractMetadata(self.parser)
            
            
        def _kaa_get(self, key, missing, stream=None): 
            
            if not hasattr(self, 'info'):
                try:
                    from kaa.metadata import parse
                except ImportError:
                    msg = """The package Kaa metadata does not exist.
It is needed to access FPS and codec video file metadata."""
                    logger.error(msg)
                    self.info = None
                else:
                    self.info = parse(self.filename)
            if self.info:
                if stream != None:
                    v = self.info['video'][stream][key]
                else:
                    v = self.info[key]
            else:
                v = None
            if v:
                return str(v)
            else:
                return missing                
        
        def _get(self, key, missing):
            try:
                v = self.metadata.get(key)
            except:
                v = missing
            return v
            
        def date_time(self, missing=''):
            return self._get('creation_date', missing)
                
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
            
        def codec(self, stream=0, missing=''):
            return self._kaa_get('codec', missing, stream)
            
        def length(self, missing=''):
            """
            return the duration (length) of the video, rounded to the nearest second, in string format
            """
            delta = self.metadata.get('duration')
            l = '%.0f' % (86400 * delta.days + delta.seconds + float('.%s' % delta.microseconds))
            return l
            
            
        def width(self, missing=''):
            v = self._get('width', missing)
            if v != None:
                return str(v)
            else:
                return None
            
        def height(self, missing=''):
            v = self._get('height', missing)
            if v != None:
                return str(v)
            else:
                return None
            
        def frames_per_second(self, stream=0, missing=''):
            fps = self._kaa_get('fps', missing, stream)
            try:
                fps = '%.0f' % float(fps)
            except:
                pass
            return fps
        
        def fourcc(self, stream=0, missing=''):
            return self._kaa_get('fourcc', missing, stream)
            

            
class DummyMetaData():
    """
    Class which gives metadata values for an imaginary video.
    
    Useful for displaying in preference examples etc. when no video is ready to
    be downloaded.
    
    See VideoMetaData class for documentation of class methods.        
    """
    def __init__(self):
        pass        
    
    def date_time(self, missing=''):
        return date_time.date_time.now()
        
    def codec(self, stream=0, missing=''):
        return 'H.264 AVC'
        
    def length(self, missing=''):
        return '57'
        
    def width(self, stream=0, missing=''):
        return '1920'
        
    def height(self, stream=0, missing=''):
        return '1080'
        
    def frames_per_second(self, stream=0, missing=''):
        return '24'
    
    def fourcc(self, stream=0, missing=''):
        return 'AVC1'
                    
            
if __name__ == '__main__':
    import sys
    
    
    if (len(sys.argv) != 2):
        print 'Usage: ' + sys.argv[0] + ' path/to/video/containing/metadata'
        sys.exit(0)

    else:
        m = VideoMetaData(sys.argv[1])
        dt = m.date_time()
        if dt:
            print dt.strftime('%Y%m%d-%H:%M:%S')
        print "codec: %s" % m.codec()
        print "%s seconds" % m.length()
        print "%sx%s" % (m.width(), m.height())
        print "%s fps" % m.frames_per_second()
        print "Fourcc: %s" % (m.fourcc())
            
