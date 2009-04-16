#!/usr/bin/python
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

import os
import sys
import gc
import distutils.version
import gtk.gdk as gdk

#from config import  LOGFILE_DIRECTORY, MAX_LOGFILE_SIZE, MAX_LOGFILES 
#
#from logging.handlers import RotatingFileHandler
#import logging

def pythonifyVersion(v):
    """ makes version number a version number in distutils sense"""
    return distutils.version.StrictVersion(v.replace( '~',''))

def getFullProgramName():
    """ return the full name of the process running """
    return os.path.basename(sys.argv[0])

def getProgramName():
    """ return the name of the process running, removing the .py extension if it exists """
    programName = getFullProgramName()
    if programName.find('.py') > 0:
        programName = programName[:programName.find('.py')]
    return programName

def splitDirectories(directories):
    """ split directories specified in string into a list """
    if directories.find(',') > 0:
        d  = directories.split(',')
    else:
        d = directories.split()
    directories = []
    for i in d:
        directories.append(i.strip())
    return directories



def getFullPath(path):
    """ make path relative to home directory if not an absolute path """
    if os.path.isabs(path):
        return path
    else:
        return os.path.join(os.path.expanduser('~'), path)    
        
    
def escape(s):
    """
    Replace special characters by SGML entities.
    """
    entities = ("&&amp;", "<&lt;", ">&gt;")
    for e in entities:
        s = s.replace(e[0], e[1:])
    return s

    



def formatSizeForUser(bytes, zeroString="", withDecimals=True, kbOnly=False):
    """Format an int containing the number of bytes into a string suitable for
    printing out to the user.  zeroString is the string to use if bytes == 0.
    source: https://develop.participatoryculture.org/trac/democracy/browser/trunk/tv/portable/util.py?rev=3993
    
    FIXME: replace with call to gnomevfs function
    """
    if bytes > (1 << 30) and not kbOnly:
        value = (bytes / (1024.0 * 1024.0 * 1024.0))
        if withDecimals:
            format = "%1.1fGB"
        else:
            format = "%dGB"
    elif bytes > (1 << 20) and not kbOnly:
        value = (bytes / (1024.0 * 1024.0))
        if withDecimals:
            format = "%1.1fMB"
        else:
            format = "%dMB"
    elif bytes > (1 << 10):
        value = (bytes / 1024.0)
        if withDecimals:
            format = "%1.1fKB"
        else:
            format = "%dKB"
    elif bytes > 1:
        value = bytes
        if withDecimals:
            format = "%1.1fB"
        else:
            format = "%dB"
    else:
        return zeroString
    return format % value
    
def scale2pixbuf(width_max, height_max, pixbuf, return_size=False):
    """
    Scale to width_max and height_max.
    Keep aspect ratio.
    Code adapted from gthumpy, by guettli
    """
    
    width_orig = float(pixbuf.get_width())
    height_orig = float(pixbuf.get_height())
    if (width_orig / width_max) > (height_orig / height_max):
        height = int((height_orig / width_orig) * width_max)
        width = width_max
    else:
        width = int((width_orig / height_orig) * height_max)
        height=height_max

    pixbuf = pixbuf.scale_simple(width, height, gdk.INTERP_BILINEAR)
    gc.collect() # Tell Python to clean up the memory
    if return_size:
        return pixbuf, width_orig, height_orig
    return pixbuf


    
if __name__ == '__main__':
    pass
