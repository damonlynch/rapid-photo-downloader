#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2007-2012 Damon Lynch <damonlynch@gmail.com>

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
### Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301
### USA

import os
import gio
import gtk
from PIL import Image
import distutils.version

def get_full_path(path):
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


    
def pythonify_version(v):
    """ makes version number a version number in distutils sense"""
    return distutils.version.StrictVersion(v.replace( '~',''))
    
def human_readable_version(v):
    """ returns a version in human readable form"""
    v = v.replace('~a', ' alpha ')
    v = v.replace('~b', ' beta ')
    v = v.replace('~rc', ' RC ')
    return v
        
