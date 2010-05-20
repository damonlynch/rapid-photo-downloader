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
import subprocess
import tempfile

import gtk
import media

try:
    import kaa.metadata
except ImportError:
    DOWNLOAD_VIDEO = False

VIDEO_THUMBNAIL_FILE_EXTENSIONS = ['thm']
VIDEO_FILE_EXTENSIONS = ['mov', 'avi', 'mp4']

if DOWNLOAD_VIDEO:
    
    try:
        subprocess.check_call(["ffmpegthumbnailer", "-h"], stdout=subprocess.PIPE)
        ffmpeg = True
    except:
        ffmpeg = False

    
    def version_info():
        return str(kaa.metadata.VERSION)
    
    class VideoMetaData():
        def __init__(self, filename):
            self.info = kaa.metadata.parse(filename)
            self.filename = filename
            
        def rpd_keys(self):
            return self.info.keys()
            
        def _get(self, key, missing, stream=None):
            if stream != None:
                v = self.info['video'][stream][key]
            else:
                v = self.info[key]
            if v:
                return v
            else:
                return missing
            
        def dateTime(self, missing=''):
            dt = self._get('timestamp', missing=None)
            if dt:
                try:
                    return datetime.datetime.fromtimestamp(self.info['timestamp'])
                except:
                    return missing
            else:
                return missing
            
        def codec(self, stream=0, missing=''):
            return self._get('codec', missing, stream)
            
        def length(self, missing=''):
            return self._get('length', missing)
            
        def width(self, stream=0, missing=''):
            return self._get('width', missing, stream)
            
        def height(self, stream=0, missing=''):
            return self._get('height', missing, stream)
            
        def framesPerSecond(self, stream=0, missing=''):
            return self._get('fps', missing, stream)
        
        def fourcc(self, stream=0, missing=''):
            return self._get('fourcc', missing, stream)
            
        def getThumbnailData(self, size, tempWorkingDir):
            thm = media.getVideoThumbnailFile(self.filename)
            if thm:
                thumbnail = gtk.gdk.pixbuf_new_from_file_at_size(thm,  size,  size)
            else:
                if ffmpeg:
                    tmp = tempfile.NamedTemporaryFile(dir=tempWorkingDir, prefix="rpd-tmp")
                    tmp.close()
                    
                    thm = os.path.join(tempWorkingDir, tmp.name)
                    
                    try:
                        subprocess.check_call(['ffmpegthumbnailer', '-i', self.filename, '-t', '10', '-o', thm, '-s', str(size)])
                        thumbnail = gtk.gdk.pixbuf_new_from_file_at_size(thm,  size,  size)
                        os.unlink(thm)
                    except:
                        thumbnail = None                    
                else:
                    thumbnail = None
            return thumbnail
        
        
            
            
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
            
