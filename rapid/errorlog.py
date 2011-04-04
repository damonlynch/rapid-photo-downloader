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

import gtk

import pango
import config
import paths

class ErrorLog():
    """
    Displays a log of errors, warnings or other information to the user
    """
    
    def __init__(self, rapidapp):
        """
        Initialize values for log dialog, but do not display.
        """
        
        self.builder = gtk.Builder()
        self.builder.add_from_file(paths.share_dir("glade3/errorlog.ui"))
        self.builder.connect_signals(self)
        self.widget = self.builder.get_object("errorlog")
        self.log_textview = self.builder.get_object("log_textview")
        self.log_scrolledwindow = self.builder.get_object("log_scrolledwindow")
        
        self.widget.connect("delete-event", self.hide_window)
        
        self.rapidapp = rapidapp
        #~ self.log_textview.set_cursor_visible(False)
        self.textbuffer = self.log_textview.get_buffer()
        
        self.error_tag = self.textbuffer.create_tag(weight=pango.WEIGHT_BOLD, foreground="red")
        self.warning_tag = self.textbuffer.create_tag(weight=pango.WEIGHT_BOLD)
        self.extra_detail_tag = self.textbuffer.create_tag(style=pango.STYLE_ITALIC)
        
    def add_message(self, severity, problem, details, extra_detail):
        if severity in [config.CRITICAL_ERROR, config.SERIOUS_ERROR]:
            self.rapidapp.error_image.show()
        elif severity == config.WARNING:
            self.rapidapp.warning_image.show()
        self.rapidapp.warning_vseparator.show()
        
        iter = self.textbuffer.get_end_iter()
        if severity in [config.CRITICAL_ERROR, config.SERIOUS_ERROR]:
            self.textbuffer.insert_with_tags(iter, problem +"\n", self.error_tag)
        else:
            self.textbuffer.insert_with_tags(iter, problem +"\n", self.warning_tag)
        if details:
            iter = self.textbuffer.get_end_iter()
            self.textbuffer.insert(iter, details + "\n")
        if extra_detail:
            iter = self.textbuffer.get_end_iter()
            self.textbuffer.insert_with_tags(iter, extra_detail +"\n", self.extra_detail_tag)
            
        iter = self.textbuffer.get_end_iter()
        self.textbuffer.insert(iter, "\n")
        
        # move viewport to display the latest message
        adjustment = self.log_scrolledwindow.get_vadjustment()
        adjustment.set_value(adjustment.upper)
        
        
    def on_errorlog_response(self, dialog, arg):
        if arg == gtk.RESPONSE_CLOSE:
            pass
        self.rapidapp.error_image.hide()
        self.rapidapp.warning_image.hide()
        self.rapidapp.warning_vseparator.hide()
        self.rapidapp.prefs.show_log_dialog = False
        self.widget.hide()
        return True

    def hide_window(self,  window, event):
        window.hide()
        return True
