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

import gtk, gio

class Device:
    def __init__(self, mount=None, path=None):
        self.mount = mount
        self.path = path
        
    def get_path(self):
        if self.mount:
            return self.mount.get_root().get_path()
        else:
            return self.path
            
    def get_name(self):
        if self.mount:
            return self.mount.get_name()
        else:
            return self.path
            
    def get_icon(self, size=16):
        if self.mount:
            icon = self.mount.get_icon()
        else:
            folder = gio.File(self.path)
            file_info = folder.query_info(gio.FILE_ATTRIBUTE_STANDARD_ICON)
            icon = file_info.get_icon()
        
        icontheme = gtk.icon_theme_get_default()        
        
        icon_file = None
        if isinstance(icon, gio.ThemedIcon):
            try:
                # on some user's systems, themes do not have icons associated with them
                iconinfo = icontheme.choose_icon(icon.get_names(), size, gtk.ICON_LOOKUP_USE_BUILTIN)
                icon_file = iconinfo.get_filename()
                return gtk.gdk.pixbuf_new_from_file_at_size(icon_file, size, size)
            except:
                pass

        if not icon_file:
            return icontheme.load_icon('folder', size, gtk.ICON_LOOKUP_USE_BUILTIN)

