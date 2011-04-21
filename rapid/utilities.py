#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2007 - 2011 Damon Lynch <damonlynch@gmail.com>

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
        
def is_directory(path):
    
    # for some very strange reason, doing it the GIO way fails with
    # unknown type, even for directories!
    return os.path.isdir(path)
    
    if False:
        d = gio.File(path)
        if d.query_exists():
            file_info = d.query_filesystem_info(attributes="standard::type")
            file_type = file_info.get_file_type()
            if file_type == gio.FILE_TYPE_DIRECTORY:
                return True
            
        return False

def format_size_for_user(bytes, zero_string="", with_decimals=True, kb_only=False):
    """Format an int containing the number of bytes into a string suitable for
    printing out to the user.  zero_string is the string to use if bytes == 0.
    source: https://develop.participatoryculture.org/trac/democracy/browser/trunk/tv/portable/util.py?rev=3993
    
    """
    if bytes > (1 << 30) and not kb_only:
        value = (bytes / (1024.0 * 1024.0 * 1024.0))
        if with_decimals:
            format = "%1.1fGB"
        else:
            format = "%dGB"
    elif bytes > (1 << 20) and not kb_only:
        value = (bytes / (1024.0 * 1024.0))
        if with_decimals:
            format = "%1.1fMB"
        else:
            format = "%dMB"
    elif bytes > (1 << 10):
        value = (bytes / 1024.0)
        if with_decimals:
            format = "%1.1fKB"
        else:
            format = "%dKB"
    elif bytes > 1:
        value = bytes
        if with_decimals:
            format = "%1.1fB"
        else:
            format = "%dB"
    else:
        return zero_string
    return format % value

def register_iconsets(icon_info):
    """
    Register icons in the icon set if they're not already used
    
    From http://faq.pygtk.org/index.py?req=show&file=faq08.012.htp
    """
    
    icon_factory = gtk.IconFactory()
    stock_ids = gtk.stock_list_ids()
    for stock_id, file in icon_info:
        # only load image files when our stock_id is not present
        if stock_id not in stock_ids:
            pixbuf = gtk.gdk.pixbuf_new_from_file(file)
            iconset = gtk.IconSet(pixbuf)
            icon_factory.add(stock_id, iconset)
    icon_factory.add_default()

def escape(s):
    """
    Replace special characters by SGML entities.
    """
    entities = ("&&amp;", "<&lt;", ">&gt;")
    for e in entities:
        s = s.replace(e[0], e[1:])
    return s

def image_to_pixbuf(image):
    # convert PIL image to pixbuf
    # this one handles transparency, unlike the default example in the pygtk FAQ
    # this is also from the pygtk FAQ
    IS_RGBA = image.mode=='RGBA'
    return gtk.gdk.pixbuf_new_from_data(
            image.tostring(), # data
            gtk.gdk.COLORSPACE_RGB, # color mode
            IS_RGBA, # has alpha
            8, # bits
            image.size[0], # width
            image.size[1], # height
            (IS_RGBA and 4 or 3) * image.size[0] # rowstride
            ) 

def pixbuf_to_image(pb):
    assert(pb.get_colorspace() == gtk.gdk.COLORSPACE_RGB)
    dimensions = pb.get_width(), pb.get_height()
    stride = pb.get_rowstride()
    pixels = pb.get_pixels()

    mode = pb.get_has_alpha() and "RGBA" or "RGB"
    image = Image.frombuffer(mode, dimensions, pixels,
                            "raw", mode, stride, 1)
                            
    if mode == "RGB":
        # convert to having an alpha value, so that the image can
        # act as a mask in the drop shadow paste 
        image = image.convert("RGBA")

    return image
    
def pythonify_version(v):
    """ makes version number a version number in distutils sense"""
    return distutils.version.StrictVersion(v.replace( '~',''))
    
def human_readable_version(v):
    """ returns a version in human readable form"""
    v = v.replace('~a', ' alpha ')
    v = v.replace('~b', ' beta ')
    v = v.replace('~rc', ' RC ')
    return v
        
