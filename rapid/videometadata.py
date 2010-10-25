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

DOWNLOAD_VIDEO = True

import os
import datetime
import time
import subprocess
import tempfile

import gtk
import media
import paths
from filmstrip import add_filmstrip

try:
    import kaa.metadata
    from hachoir_core.cmd_line import unicodeFilename
    from hachoir_parser import createParser
    from hachoir_metadata import extractMetadata
except ImportError:
    DOWNLOAD_VIDEO = False

VIDEO_THUMBNAIL_FILE_EXTENSIONS = ['thm']
VIDEO_FILE_EXTENSIONS = ['3gp', 'avi', 'm2t', 'mov', 'mp4', 'mpeg','mpg', 'mod', 'tod']

   

if DOWNLOAD_VIDEO:
    
    
    try:
        subprocess.check_call(["ffmpegthumbnailer", "-h"], stdout=subprocess.PIPE)
        ffmpeg = True
    except:
        ffmpeg = False

    
    def version_info():
        from hachoir_metadata.version import VERSION
        return VERSION
        
    def get_video_THM_file(fullFileName):
        """
        Checks to see if a thumbnail file (THM) is in the same directory as the 
        file. Expects a full path to be part of the file name.
        
        Returns the filename, including path, if found, else returns None.
        """
        
        f = None
        name, ext = os.path.splitext(fullFileName)
        for e in VIDEO_THUMBNAIL_FILE_EXTENSIONS:
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
                self.info = kaa.metadata.parse(self.filename)
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
            
        def dateTime(self, missing=''):
            return self._get('creation_date', missing)
                
        def timeStamp(self, missing=''):
            """
            Returns a float value representing the time stamp, if it exists
            """
            dt = self.dateTime(missing=None)
            if dt:
                # convert it to a timestamp (not optimal, but better than nothing!)
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
            
        def framesPerSecond(self, stream=0, missing=''):
            fps = self._kaa_get('fps', missing, stream)
            try:
                fps = '%.0f' % float(fps)
            except:
                pass
            return fps
        
        def fourcc(self, stream=0, missing=''):
            return self._kaa_get('fourcc', missing, stream)
            
        def getThumbnailData(self, size, tempWorkingDir):
            """
            Returns a pixbuf of the video's thumbnail
            
            If it cannot be created, returns None
            """
            thm = get_video_THM_file(self.filename)
            if thm:
                thumbnail = gtk.gdk.pixbuf_new_from_file(thm)
                aspect = float(thumbnail.get_height()) / thumbnail.get_width()
                thumbnail = thumbnail.scale_simple(size, int(aspect*size), gtk.gdk.INTERP_BILINEAR)
                thumbnail = add_filmstrip(thumbnail)
            else:
                if ffmpeg:
                    try:
                        tmp = tempfile.NamedTemporaryFile(dir=tempWorkingDir, prefix="rpd-tmp")
                        tmp.close()
                    except:
                        return None
                    
                    thm = os.path.join(tempWorkingDir, tmp.name)
                    
                    try:
                        subprocess.check_call(['ffmpegthumbnailer', '-i', self.filename, '-t', '10', '-f', '-o', thm, '-s', str(size)])
                        thumbnail = gtk.gdk.pixbuf_new_from_file_at_size(thm,  size,  size)
                        os.unlink(thm)
                    except:
                        thumbnail = None                    
                else:
                    thumbnail = None
            return thumbnail
        
class DummyMetaData():
    """
    Class which gives metadata values for an imaginary video.
    
    Useful for displaying in preference examples etc. when no video is ready to
    be downloaded.
    
    See VideoMetaData class for documentation of class methods.        
    """
    def __init__(self):
        pass        
    
    def dateTime(self, missing=''):
        return datetime.datetime.now()
        
    def codec(self, stream=0, missing=''):
        return 'H.264 AVC'
        
    def length(self, missing=''):
        return '57'
        
    def width(self, stream=0, missing=''):
        return '1920'
        
    def height(self, stream=0, missing=''):
        return '1080'
        
    def framesPerSecond(self, stream=0, missing=''):
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
        dt = m.dateTime()
        if dt:
            print dt.strftime('%Y%m%d-%H:%M:%S')
        print "codec: %s" % m.codec()
        print "%s seconds" % m.length()
        print "%sx%s" % (m.width(), m.height())
        print "%s fps" % m.framesPerSecond()
        print "Fourcc: %s" % (m.fourcc())
            
