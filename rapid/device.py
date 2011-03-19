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

import os
import gtk, gio

import multiprocessing
import logging
logger = multiprocessing.get_logger()

import paths
import utilities

from gettext import gettext as _

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


class UseDeviceDialog(gtk.Dialog):
    """
    Simple dialog window that prompt's the user whether to use a certain 
    device or not
    """
    def __init__(self,  parent_window, device, post_choice_callback):
        gtk.Dialog.__init__(self, _('Device Detected'), None,
                   gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                   (gtk.STOCK_NO, gtk.RESPONSE_CANCEL, 
                   gtk.STOCK_YES, gtk.RESPONSE_OK))
                        
        self.post_choice_callback = post_choice_callback
        
        self.set_icon_from_file(paths.share_dir('glade3/rapid-photo-downloader.svg'))
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#usedeviceprompt
        prompt_label = gtk.Label(_('Should this device or partition be used to download photos or videos from?'))
        prompt_label.set_line_wrap(True)
        prompt_hbox = gtk.HBox()
        prompt_hbox.pack_start(prompt_label, False, False, padding=6)
        device_label = gtk.Label()
        device_label.set_markup("<b>%s</b>" % device.get_name())
        device_hbox = gtk.HBox()
        device_hbox.pack_start(device_label, False, False)
        path_label = gtk.Label()
        path_label.set_markup("<i>%s</i>" % device.get_path())
        path_hbox = gtk.HBox()
        path_hbox.pack_start(path_label, False, False)
        
        icon = device.get_icon(size=36)
        if icon:
            image = gtk.Image()
            image.set_from_pixbuf(icon)
            
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#usedeviceprompt
        self.always_checkbutton = gtk.CheckButton(_('_Remember this choice'), True)

        if icon:
            device_hbox_icon = gtk.HBox(homogeneous=False, spacing=6)
            device_hbox_icon.pack_start(image, False, False, padding = 6)
            device_vbox = gtk.VBox(homogeneous=True, spacing=6)
            device_vbox.pack_start(device_hbox, False, False)
            device_vbox.pack_start(path_hbox, False, False)
            device_hbox_icon.pack_start(device_vbox, False, False)
            self.vbox.pack_start(device_hbox_icon, padding = 6)
        else:
            self.vbox.pack_start(device_hbox, padding=6)
            self.vbox.pack_start(path_hbox, padding = 6)
            
        self.vbox.pack_start(prompt_hbox, padding=6)
        self.vbox.pack_start(self.always_checkbutton, padding=6)

        self.set_border_width(6)
        self.set_has_separator(False)   
        
        self.set_default_response(gtk.RESPONSE_OK)
      
       
        self.set_transient_for(parent_window)
        self.show_all()
        self.device = device
        
        self.connect('response', self.on_response)
        
    def on_response(self, device_dialog, response):
        user_selected = False
        permanent_choice = self.always_checkbutton.get_active()
        if response == gtk.RESPONSE_OK:
            user_selected = True
            logger.info("%s selected for downloading from", self.device.get_name())
            if permanent_choice:
                logger.info("This device or partition will always be used to download from")
        else:
            logger.info("%s rejected as a download device", self.device.get_name())
            if permanent_choice:
                logger.info("This device or partition will never be used to download from")
            
        self.post_choice_callback(self,  user_selected,  permanent_choice,  
                          self.device)
                          
                          
def is_DCIM_device(path):
    """ Returns true if directory specifies media with photos on it"""
    
    test_path = os.path.join(path, "DCIM")
    return utilities.is_directory(test_path)
    
def is_backup_media(path, identifiers, writeable=True):
    """  Test to see if path is used as a backup medium for storing photos or videos
    
    Identifiers is expected to be a list of folder names to check to see
    if the path is a backup path. Only one of them needs to be present
    for the path to be considered a backup medium.
    
    If writeable is True, the directory must be writeable by the user """
    suitable = False
    
    for identifier in identifiers:
        if os.path.isdir(os.path.join(path, identifier)):
            if writeable:
                suitable = os.access(os.path.join(path, identifier), os.W_OK)
            else:
                suitable = True
    return suitable

