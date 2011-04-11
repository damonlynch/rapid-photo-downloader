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


import tempfile

import dbus
import dbus.bus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
DBusGMainLoop(set_as_default=True)

from optparse import OptionParser

import gtk
import gtk.gdk as gdk

import webbrowser

import sys, time, types, os, datetime

import gobject, pango, cairo, array, pangocairo, gio
import pynotify

from multiprocessing import Process, Pipe, Queue, Event, Value, Array, current_process, log_to_stderr
from ctypes import c_int, c_bool, c_char

import logging
logger = log_to_stderr()

# Rapid Photo Downloader modules

import rpdfile
                  
import problemnotification as pn
import thumbnail as tn
import rpdmultiprocessing as rpdmp

import preferencesdialog
import prefsrapid

import tableplusminus as tpm
import generatename as gn

import downloadtracker

from metadatavideo import DOWNLOAD_VIDEO
import metadataphoto
import metadatavideo

import scan as scan_process
import copyfiles
import subfolderfile

import errorlog

import device as dv
import utilities

import config
__version__ = config.version

import paths

import gettext
gettext.bindtextdomain(config.APP_NAME)
gettext.textdomain(config.APP_NAME)

from gettext import gettext as _


from utilities import format_size_for_user
from utilities import register_iconsets


from config import  STATUS_CANNOT_DOWNLOAD, STATUS_DOWNLOADED, \
                    STATUS_DOWNLOADED_WITH_WARNING, \
                    STATUS_DOWNLOAD_FAILED, \
                    STATUS_DOWNLOAD_PENDING, \
                    STATUS_BACKUP_PROBLEM, \
                    STATUS_NOT_DOWNLOADED, \
                    STATUS_DOWNLOAD_AND_BACKUP_FAILED, \
                    STATUS_WARNING
                    
DOWNLOADED = [STATUS_DOWNLOADED, STATUS_DOWNLOADED_WITH_WARNING, STATUS_BACKUP_PROBLEM]

#Translators: if neccessary, for guidance in how to translate this program, you may see http://damonlynch.net/translate.html 
PROGRAM_NAME = _('Rapid Photo Downloader')
__version__ = config.version

def date_time_human_readable(date, with_line_break=True):
    if with_line_break:
        return _("%(date)s\n%(time)s") % {'date':date.strftime("%x"), 'time':date.strftime("%X")}
    else:
        return _("%(date)s %(time)s") % {'date':date.strftime("%x"), 'time':date.strftime("%X")}
        
def date_time_subseconds_human_readable(date, subseconds):
    return _("%(date)s %(hour)s:%(minute)s:%(second)s:%(subsecond)s") % \
            {'date':date.strftime("%x"), 
             'hour':date.strftime("%H"),
             'minute':date.strftime("%M"), 
             'second':date.strftime("%S"),
             'subsecond': subseconds}


class DeviceCollection(gtk.TreeView):
    """
    TreeView display of devices and how many files have been copied, shown
    immediately under the menu in the main application window.
    """
    def __init__(self, parent_app):

        self.parent_app = parent_app
        # device icon & name, size of images on the device (human readable), 
        # copy progress (%), copy text, eject button (None if irrelevant),
        # process id
        self.liststore = gtk.ListStore(gtk.gdk.Pixbuf, str, str, float, str,
                                       gtk.gdk.Pixbuf, int)
        self.map_process_to_row = {}
        self.devices_by_scan_pid = {}

        gtk.TreeView.__init__(self, self.liststore)
        
        self.props.enable_search = False
        # make it impossible to select a row
        selection = self.get_selection()
        selection.set_mode(gtk.SELECTION_NONE)
        
        
        # Device refers to a thing like a camera, memory card in its reader, 
        # external hard drive, Portable Storage Device, etc.
        column0 = gtk.TreeViewColumn(_("Device"))
        pixbuf_renderer = gtk.CellRendererPixbuf()
        text_renderer = gtk.CellRendererText()
        text_renderer.props.ellipsize = pango.ELLIPSIZE_MIDDLE
        text_renderer.set_fixed_size(160, -1)
        eject_renderer = gtk.CellRendererPixbuf()
        column0.pack_start(pixbuf_renderer, expand=False)
        column0.pack_start(text_renderer, expand=True)
        column0.pack_end(eject_renderer, expand=False)
        column0.add_attribute(pixbuf_renderer, 'pixbuf', 0)
        column0.add_attribute(text_renderer, 'text', 1)
        column0.add_attribute(eject_renderer, 'pixbuf', 5)
        self.append_column(column0)
        
        
        # Size refers to the total size of images on the device, typically in
        # MB or GB
        column1 = gtk.TreeViewColumn(_("Size"), gtk.CellRendererText(), text=2)
        self.append_column(column1)
        
        column2 = gtk.TreeViewColumn(_("Download Progress"), 
                                    gtk.CellRendererProgress(),
                                    value=3,
                                    text=4)
        self.append_column(column2)
        self.show_all()
        
        icontheme = gtk.icon_theme_get_default()
        try:
            self.eject_pixbuf = icontheme.load_icon('media-eject', 16, 
                                                gtk.ICON_LOOKUP_USE_BUILTIN)
        except:
            self.eject_pixbuf = gtk.gdk.pixbuf_new_from_file(
                                    paths.share_dir('glade3/media-eject.png'))
                                    
        self.add_events(gtk.gdk.BUTTON_PRESS_MASK)
        self.connect('button-press-event', self.button_clicked)
        

    def add_device(self, process_id, device, progress_bar_text = ''):
        
        # add the row, and get a temporary pointer to the row
        size_files = ''
        progress = 0.0
        
        if device.mount is None:
            eject = None
        else:
            eject = self.eject_pixbuf
            
        self.devices_by_scan_pid[process_id] = device
            
        iter = self.liststore.append((device.get_icon(),
                                      device.get_name(),
                                      size_files,
                                      progress,
                                      progress_bar_text,
                                      eject,
                                      process_id))
        
        self._set_process_map(process_id, iter)
        
        # adjust scrolled window height, based on row height and number of ready to start downloads

        # please note, at program startup, self.row_height() will be less than it will be when already running
        # e.g. when starting with 3 cards, it could be 18, but when adding 2 cards to the already running program
        # (with one card at startup), it could be 21
        row_height = self.get_background_area(0, self.get_column(0))[3] + 1
        height = (len(self.map_process_to_row) + 1) * row_height
        self.parent_app.device_collection_scrolledwindow.set_size_request(-1, height)
        
    def update_device(self, process_id, total_size_files):
        """
        Updates the size of the photos and videos on the device, displayed to the user
        """
        if process_id in self.map_process_to_row:
            iter = self._get_process_map(process_id)
            self.liststore.set_value(iter, 2, total_size_files)
        else:
            logger.critical("This device is unknown")
            
    def get_device(self, process_id):
        return self.devices_by_scan_pid.get(process_id)
    
    def remove_device(self, process_id):
        if process_id in self.map_process_to_row:
            iter = self._get_process_map(process_id)
            self.liststore.remove(iter)
            del self.map_process_to_row[process_id]
            del self.devices_by_scan_pid[process_id]
            
    def get_all_displayed_processes(self):
        """
        returns a list of the processes currently being displayed to the user 
        """
        return self.map_process_to_row.keys()


    def _set_process_map(self, process_id, iter):
        """
        convert the temporary iter into a tree reference, which is 
        permanent
        """

        path = self.liststore.get_path(iter)
        treerowref = gtk.TreeRowReference(self.liststore, path)
        self.map_process_to_row[process_id] = treerowref
    
    def _get_process_map(self, process_id):
        """
        return the tree iter for this process
        """
        
        if process_id in self.map_process_to_row:
            treerowref = self.map_process_to_row[process_id]
            path = treerowref.get_path()
            iter = self.liststore.get_iter(path)
            return iter
        else:
            return None
    
    def update_progress(self, scan_pid, percent_complete, progress_bar_text, bytes_downloaded):
        
        iter = self._get_process_map(scan_pid)
        if iter:
            if percent_complete:
                self.liststore.set_value(iter, 3, percent_complete)
            if progress_bar_text:
                self.liststore.set_value(iter, 4, progress_bar_text)
            if percent_complete or bytes_downloaded:
                pass
                #~ logger.info("Implement update overall progress")

    def button_clicked(self, widget, event):
        """
        Look for left single click on eject button
        """
        if event.button == 1:
            x = int(event.x)
            y = int(event.y)
            path, column, cell_x, cell_y = self.get_path_at_pos(x, y)
            if path is not None:
                if column == self.get_column(0):
                    if cell_x >= column.get_width() - self.eject_pixbuf.get_width():
                        iter = self.liststore.get_iter(path)
                        if self.liststore.get_value(iter, 5) is not None:
                            self.unmount(process_id = self.liststore.get_value(iter, 6))
            
    def unmount(self, process_id):
        device = self.devices_by_scan_pid[process_id]
        if device.mount is not None:
            logger.debug("Unmounting device with scan pid %s", process_id)
            device.mount.unmount(self.unmount_callback)
        
    
    def unmount_callback(self, mount, result):
        name = mount.get_name()

        try:
            mount.unmount_finish(result)
            logger.debug("%s successfully unmounted" % name)
        except gio.Error, inst:
            logger.error("%s did not unmount: %s", name, inst)
            
            title = _("%(device)s did not unmount") % {'device': name}
            message = '%s' % inst
                       
            n = pynotify.Notification(title, message)
            n.set_icon_from_pixbuf(self.parent_app.application_icon)
            n.show()             


def create_cairo_image_surface(pil_image, image_width, image_height):
        imgd = pil_image.tostring("raw","BGRA", 0, 1)
        data = array.array('B',imgd)
        stride = image_width * 4
        image = cairo.ImageSurface.create_for_data(data, cairo.FORMAT_ARGB32,
                                            image_width, image_height, stride)
        return image

class ThumbnailCellRenderer(gtk.CellRenderer):
    __gproperties__ = {
        "image": (gobject.TYPE_PYOBJECT, "Image",
        "Image", gobject.PARAM_READWRITE),
        
        "filename": (gobject.TYPE_STRING, "Filename", 
        "Filename", '', gobject.PARAM_READWRITE),
        
        "status": (gtk.gdk.Pixbuf, "Status",
        "Status", gobject.PARAM_READWRITE),
    }
    
    def __init__(self, checkbutton_height):
        gtk.CellRenderer.__init__(self)
        self.image = None
        
        self.image_area_size = 100
        self.text_area_size = 30
        self.padding = 6
        self.checkbutton_height = checkbutton_height
        self.icon_width = 20
        
    def do_set_property(self, pspec, value):
        setattr(self, pspec.name, value)

    def do_get_property(self, pspec):
        return getattr(self, pspec.name)
        
    def do_render(self, window, widget, background_area, cell_area, expose_area, flags):
        
        cairo_context = window.cairo_create()
        
        x = cell_area.x
        y = cell_area.y + self.checkbutton_height - 8
        w = cell_area.width
        h = cell_area.height
        
        #constrain operations to cell area, allowing for a 1 pixel border 
        #either side
        #~ cairo_context.rectangle(x-1, y-1, w+2, h+2)
        #~ cairo_context.clip()
        
        #fill in the background with dark grey
        #this ensures that a selected cell's fill does not make
        #the text impossible to read
        #~ cairo_context.rectangle(x, y, w, h)
        #~ cairo_context.set_source_rgb(0.267, 0.267, 0.267)
        #~ cairo_context.fill()
        
        #image width and height
        image_w = self.image.size[0]
        image_h = self.image.size[1]
        
        #center the image horizontally
        #bottom align vertically
        #top left and right corners for the image:
        image_x = x + ((w - image_w) / 2)
        image_y = y + self.image_area_size - image_h

        #convert PIL image to format suitable for cairo
        image = create_cairo_image_surface(self.image, image_w, image_h)

        # draw a light grey border of 1px around the image
        cairo_context.set_source_rgb(0.66, 0.66, 0.66) #light grey, #a9a9a9
        cairo_context.set_line_width(1)
        cairo_context.rectangle(image_x-.5, image_y-.5, image_w+1, image_h+1)
        cairo_context.stroke()
        
        # draw a thin border around each cell
        #~ cairo_context.set_source_rgb(0.33,0.33,0.33)
        #~ cairo_context.rectangle(x, y, w, h)
        #~ cairo_context.stroke()
        
        #place the image
        cairo_context.set_source_surface(image, image_x, image_y)
        cairo_context.paint()
        
        #text
        context = pangocairo.CairoContext(cairo_context)
        
        text_y = y + self.image_area_size + 10
        text_w = w - self.icon_width
        text_x = x + self.icon_width
        #~ context.rectangle(text_x, text_y, text_w, 15)
        #~ context.clip()        
        
        layout = context.create_layout()

        width = text_w * pango.SCALE
        layout.set_width(width)
        
        layout.set_alignment(pango.ALIGN_CENTER)
        layout.set_ellipsize(pango.ELLIPSIZE_END)
        
        #font color and size
        fg_color = pango.AttrForeground(65535, 65535, 65535, 0, -1)
        font_size = pango.AttrSize(8192, 0, -1) # 8 * 1024 = 8192
        font_family = pango.AttrFamily('sans', 0, -1)
        attr = pango.AttrList()
        attr.insert(fg_color)
        attr.insert(font_size)
        attr.insert(font_family)
        layout.set_attributes(attr)

        layout.set_text(self.filename)        

        context.move_to(text_x, text_y)
        context.show_layout(layout)

        #status
        cairo_context.set_source_pixbuf(self.status, x, y + self.image_area_size + 10)
        cairo_context.paint()
        
    def do_get_size(self, widget, cell_area):
        return (0, 0, self.image_area_size, self.image_area_size + self.text_area_size - self.checkbutton_height + 4)
        

gobject.type_register(ThumbnailCellRenderer)
 

class ThumbnailDisplay(gtk.IconView):
    def __init__(self, parent_app):
        gtk.IconView.__init__(self)
        self.set_spacing(0)
        self.set_row_spacing(5)
        self.set_margin(25)
                
        self.rapid_app = parent_app
        
        self.batch_size = 10
        
        self.thumbnail_manager = ThumbnailManager(self.thumbnail_results, self.batch_size)
        self.preview_manager = PreviewManager(self.preview_results)
        
        self.treerow_index = {} 
        self.process_index = {} 
        
        self.rpd_files = {}
        
        self.total_thumbs_to_generate = 0
        self.thumbnails_generated = 0
        
        self.thumbnails = {}
        self.previews = {}
        self.previews_being_fetched = set()
        
        self.stock_photo_thumbnails = tn.PhotoIcons()
        self.stock_video_thumbnails = tn.VideoIcons()
        
        self.SELECTED_COL = 1
        self.UNIQUE_ID_COL = 2
        self.TIMESTAMP_COL = 4
        self.FILETYPE_COL = 5
        self.CHECKBUTTON_VISIBLE_COL = 6
        self.DOWNLOAD_STATUS_COL = 7
        self.STATUS_ICON_COL = 8
        
        self.liststore = gtk.ListStore(
             gobject.TYPE_PYOBJECT, # 0 PIL thumbnail
             gobject.TYPE_BOOLEAN,  # 1 selected or not
             str,                   # 2 unique id
             str,                   # 3 file name
             int,                   # 4 timestamp for sorting, converted float
             int,                   # 5 file type i.e. photo or video
             gobject.TYPE_BOOLEAN,  # 6 visibility of checkbutton
             int,                   # 7 status of download
             gtk.gdk.Pixbuf,        # 8 status icon
             )

        self.clear()
        self.set_model(self.liststore)
        
        
        checkbutton = gtk.CellRendererToggle()
        checkbutton.set_radio(False)
        checkbutton.props.activatable = True
        checkbutton.props.xalign = 0.0
        checkbutton.connect('toggled', self.on_checkbutton_toggled)
        self.pack_end(checkbutton, expand=False)

        self.add_attribute(checkbutton, "active", 1)
        self.add_attribute(checkbutton, "visible", 6)
        
        checkbutton_size = checkbutton.get_size(self, None)
        checkbutton_height = checkbutton_size[3]
        checkbutton_width = checkbutton_size[2]
        
        image = ThumbnailCellRenderer(checkbutton_height)
        self.pack_start(image, expand=True)
        self.add_attribute(image, "image", 0)
        self.add_attribute(image, "filename", 3)
        self.add_attribute(image, "status", 8)


        
        #set the background color to a darkish grey
        self.modify_base(gtk.STATE_NORMAL, gtk.gdk.Color('#444444'))
        
        self.show_all()
        
        self._setup_icons()
                

        
        self.connect('item-activated', self.on_item_activated)
        
    def _setup_icons(self):
        # icons to be displayed in status column

        size = 16
        # standard icons
        failed = self.render_icon(gtk.STOCK_DIALOG_ERROR, gtk.ICON_SIZE_MENU)
        self.download_failed_icon = failed.scale_simple(size, size, gtk.gdk.INTERP_HYPER)
        error = self.render_icon(gtk.STOCK_DIALOG_ERROR, gtk.ICON_SIZE_MENU)
        self.error_icon = error.scale_simple(size, size, gtk.gdk.INTERP_HYPER)
        warning = self.render_icon(gtk.STOCK_DIALOG_WARNING, gtk.ICON_SIZE_MENU)
        self.warning_icon = warning.scale_simple(size, size, gtk.gdk.INTERP_HYPER)

        # Rapid Photo Downloader specific icons
        self.downloaded_icon = gtk.gdk.pixbuf_new_from_file_at_size(
               paths.share_dir('glade3/rapid-photo-downloader-downloaded.svg'),
               size, size)
        self.download_pending_icon = gtk.gdk.pixbuf_new_from_file_at_size(
               paths.share_dir('glade3/rapid-photo-downloader-download-pending.png'),
               size, size) 
        self.downloaded_with_warning_icon = gtk.gdk.pixbuf_new_from_file_at_size(
               paths.share_dir('glade3/rapid-photo-downloader-downloaded-with-warning.svg'),
               size, size)
        self.downloaded_with_error_icon = gtk.gdk.pixbuf_new_from_file_at_size(
               paths.share_dir('glade3/rapid-photo-downloader-downloaded-with-error.svg'),
               size, size)
        
        # make the not yet downloaded icon a transparent square
        self.not_downloaded_icon = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False, 8, 16, 16)
        self.not_downloaded_icon.fill(0xffffffff)
        self.not_downloaded_icon = self.not_downloaded_icon.add_alpha(True, chr(255), chr(255), chr(255))
        
    def get_status_icon(self, status):
        """
        Returns the correct icon, based on the status
        """
        if status == STATUS_WARNING:
            status_icon = self.warning_icon
        elif status == STATUS_CANNOT_DOWNLOAD:
            status_icon = self.error_icon
        elif status == STATUS_DOWNLOADED:
            status_icon =  self.downloaded_icon
        elif status == STATUS_NOT_DOWNLOADED:
            status_icon = self.not_downloaded_icon
        elif status in [STATUS_DOWNLOADED_WITH_WARNING, STATUS_BACKUP_PROBLEM]:
            status_icon = self.downloaded_with_warning_icon
        elif status in [STATUS_DOWNLOAD_FAILED, STATUS_DOWNLOAD_AND_BACKUP_FAILED]:
            status_icon = self.downloaded_with_error_icon
        elif status == STATUS_DOWNLOAD_PENDING:
            status_icon = self.download_pending_icon
        else:
            logger.critical("FIXME: unknown status: %s", status)
            status_icon = self.not_downloaded_icon
        return status_icon        
    
    def sort_by_timestamp(self):
        self.liststore.set_sort_column_id(self.TIMESTAMP_COL, gtk.SORT_ASCENDING)
        
    def on_checkbutton_toggled(self, cellrenderertoggle, path):
        iter = self.liststore.get_iter(path)
        self.liststore.set_value(iter, self.SELECTED_COL, not cellrenderertoggle.get_active())
        self.rapid_app.set_download_action_sensitivity()
        
    def set_selected(self, unique_id, value):
        iter = self.get_iter_from_unique_id(unique_id)
        self.liststore.set_value(iter, self.SELECTED_COL, value)
    
    def add_file(self, rpd_file, generate_thumbnail):

        thumbnail_icon = self.get_stock_icon(rpd_file.file_type)
        unique_id = rpd_file.unique_id
        scan_pid = rpd_file.scan_pid

        timestamp = int(rpd_file.modification_time)
        
        iter = self.liststore.append((thumbnail_icon,
                                      True,
                                      unique_id,
                                      rpd_file.display_name,
                                      timestamp,
                                      rpd_file.file_type,
                                      True,
                                      STATUS_NOT_DOWNLOADED,
                                      self.not_downloaded_icon
                                      ))
        
        path = self.liststore.get_path(iter)
        treerowref = gtk.TreeRowReference(self.liststore, path)
        
        if scan_pid in self.process_index:
            self.process_index[scan_pid].append(unique_id)
        else:
            self.process_index[scan_pid] = [unique_id,]
            
        self.treerow_index[unique_id] = treerowref
        self.rpd_files[unique_id] = rpd_file
        
        if generate_thumbnail:
            self.total_thumbs_to_generate += 1

    def get_sample_file(self, file_type):
        """Returns an rpd_file for of a given file type, or None if it does 
        not exist"""
        for unique_id, rpd_file in self.rpd_files.iteritems():
            if rpd_file.file_type == file_type:
                if rpd_file.status <> STATUS_CANNOT_DOWNLOAD:
                    return rpd_file
                    
        return None
    
    def get_unique_id_from_iter(self, iter):
        return self.liststore.get_value(iter, 2)
        
    def get_iter_from_unique_id(self, unique_id):
        treerowref = self.treerow_index[unique_id]
        path = treerowref.get_path()
        return self.liststore.get_iter(path)
    
    def on_item_activated(self, iconview, path):        
        """
        """
        iter = self.liststore.get_iter(path)
        self.show_preview(iter=iter)
        self.advance_get_preview_image(iter)

    
    def _get_preview(self, unique_id, rpd_file):
        if unique_id not in self.previews_being_fetched:
            #check if preview should be from a downloaded file, or the source
            if rpd_file.status in DOWNLOADED:
                file_location = rpd_file.download_full_file_name
            else:
                file_location = rpd_file.full_file_name
            self.preview_manager.get_preview(unique_id, file_location,
                                            rpd_file.file_type, size_max=None,)
                                            
            self.previews_being_fetched.add(unique_id)
            
    def show_preview(self, unique_id=None, iter=None):
        if unique_id is not None:
            iter = self.get_iter_from_unique_id(unique_id)
        elif iter is not None:
            unique_id = self.get_unique_id_from_iter(iter)
        else:
            # neither an iter or a unique_id were passed
            # use iter from first selected file
            # if none is selected, choose the first file
            selected = self.get_selected_items()
            if selected:
                path = selected[0]
            else:
                path = 0
            iter = self.liststore.get_iter(path)
            unique_id = self.get_unique_id_from_iter(iter)
            
            
        rpd_file = self.rpd_files[unique_id]    
        
        if unique_id in self.previews:
            preview_image = self.previews[unique_id]
        else:
            # request daemon process to get a full size thumbnail
            self._get_preview(unique_id, rpd_file)
            if unique_id in self.thumbnails:    
                preview_image = self.thumbnails[unique_id]
            else:
                preview_image = self.get_stock_icon(rpd_file.file_type)
        
        checked = self.liststore.get_value(iter, self.SELECTED_COL)
        include_checkbutton_visible = rpd_file.status == STATUS_NOT_DOWNLOADED
        self.rapid_app.show_preview_image(unique_id, preview_image, 
                                            include_checkbutton_visible, checked)
            
    def _get_next_iter(self, iter):
        iter = self.liststore.iter_next(iter)
        if iter is None:
            iter = self.liststore.get_iter_first()
        return iter
        
    def _get_prev_iter(self, iter):
        row = self.liststore.get_path(iter)[0]
        if row == 0:
            row = len(self.liststore)-1
        else:
            row -= 1
        iter = self.liststore.get_iter(row)
        return iter        
    
    def show_next_image(self, unique_id):
        iter = self.get_iter_from_unique_id(unique_id)
        iter = self._get_next_iter(iter)

        if iter is not None:
            self.show_preview(iter=iter)
            
            # cache next image
            self.advance_get_preview_image(iter, prev=False, next=True)
            
    def show_prev_image(self, unique_id):
        iter = self.get_iter_from_unique_id(unique_id)
        iter = self._get_prev_iter(iter)

        if iter is not None:
            self.show_preview(iter=iter)
            
            # cache next image
            self.advance_get_preview_image(iter, prev=True, next=False)

            
    def advance_get_preview_image(self, iter, prev=True, next=True):
        unique_ids = []
        if next:
            next_iter = self._get_next_iter(iter)
            unique_ids.append(self.get_unique_id_from_iter(next_iter))
            
        if prev:
            prev_iter = self._get_prev_iter(iter)
            unique_ids.append(self.get_unique_id_from_iter(prev_iter))
            
        for unique_id in unique_ids:
            if not unique_id in self.previews:
                rpd_file = self.rpd_files[unique_id]
                self._get_preview(unique_id, rpd_file)
            
    def check_all(self, check_all, file_type=None):
        for row in self.liststore:
            if row[self.CHECKBUTTON_VISIBLE_COL]:
                if file_type is not None:
                    if row[self.FILETYPE_COL] == file_type:
                        row[self.SELECTED_COL] = check_all
                else:
                    row[self.SELECTED_COL] = check_all
        self.rapid_app.set_download_action_sensitivity()
            
    def files_are_checked_to_download(self):
        """
        Returns True if there is any file that the user has indicated they
        intend to download, else returns False.
        """
        for row in self.liststore:
            if row[self.SELECTED_COL]:
                rpd_file = self.rpd_files[row[self.UNIQUE_ID_COL]]
                if rpd_file.status not in DOWNLOADED:
                    return True
        return False
        
    def get_files_checked_for_download(self, scan_pid):
        """
        Returns a dict of scan ids and associated files the user has indicated
        they want to download
        
        If scan_pid is not None, then returns only those files from that scan_pid
        """
        files = dict()
        if scan_pid is None:
            for row in self.liststore:
                if row[self.SELECTED_COL]:
                    rpd_file = self.rpd_files[row[self.UNIQUE_ID_COL]]
                    if rpd_file.status not in DOWNLOADED:
                        scan_pid = rpd_file.scan_pid
                        if scan_pid in files:
                            files[scan_pid].append(rpd_file)
                        else:
                            files[scan_pid] = [rpd_file,]
        else:
            files[scan_pid] = []
            for unique_id in self.process_index[scan_pid]:
                rpd_file = self.rpd_files[unique_id]
                if rpd_file.status not in DOWNLOADED:
                    iter = self.get_iter_from_unique_id(unique_id)
                    if self.liststore.get_value(iter, self.SELECTED_COL):
                        files[scan_pid].append(rpd_file)
        return files
                
    def get_no_files_remaining(self, scan_pid):
        """
        Returns the number of files that have not yet been downloaded for the
        scan_pid
        """
        i = 0
        for unique_id in self.process_index[scan_pid]:
            rpd_file = self.rpd_files[unique_id]
            if rpd_file.status == STATUS_NOT_DOWNLOADED:
                i += 1
        return i
        
    def files_remain_to_download(self):
        """
        Returns True if any files remain that are not downloaded, else returns 
        False
        """
        for row in self.liststore:
            if row[self.DOWNLOAD_STATUS_COL] == STATUS_NOT_DOWNLOADED:
                return True
        return False
            

    def mark_download_pending(self, files_by_scan_pid):
        """
        Sets status to download pending and updates thumbnails display
        """
        for scan_pid in files_by_scan_pid:
            for rpd_file in files_by_scan_pid[scan_pid]:
                unique_id = rpd_file.unique_id
                self.rpd_files[unique_id].status = STATUS_DOWNLOAD_PENDING
                iter = self.get_iter_from_unique_id(unique_id)
                if not self.rapid_app.auto_start_is_on:
                    # don't make the checkbox invisible immediately when on auto start
                    # otherwise the box can be rendred at the wrong size, as it is
                    # realized after the checkbox has already been made invisible
                    self.liststore.set_value(iter, self.CHECKBUTTON_VISIBLE_COL, False)
                self.liststore.set_value(iter, self.SELECTED_COL, False)
                self.liststore.set_value(iter, self.DOWNLOAD_STATUS_COL, STATUS_DOWNLOAD_PENDING)
                icon = self.get_status_icon(STATUS_DOWNLOAD_PENDING)
                self.liststore.set_value(iter, self.STATUS_ICON_COL, icon)
                
    def select_image(self, unique_id):
        iter = self.get_iter_from_unique_id(unique_id)
        path = self.liststore.get_path(iter)
        self.select_path(path)
        self.scroll_to_path(path, use_align=False, row_align=0.5, col_align=0.5)
        
    def get_stock_icon(self, file_type):
        if file_type == rpdfile.FILE_TYPE_PHOTO:
            return self.stock_photo_thumbnails.stock_thumbnail_image_icon
        else:
            return self.stock_video_thumbnails.stock_thumbnail_image_icon
            
    def update_status_post_download(self, rpd_file):
        iter = self.get_iter_from_unique_id(rpd_file.unique_id)
        self.liststore.set_value(iter, self.DOWNLOAD_STATUS_COL, rpd_file.status)
        icon = self.get_status_icon(rpd_file.status)
        self.liststore.set_value(iter, self.STATUS_ICON_COL, icon)
        self.liststore.set_value(iter, self.CHECKBUTTON_VISIBLE_COL, False)
        self.rpd_files[rpd_file.unique_id] = rpd_file
            
    def generate_thumbnails(self, scan_pid):
        """Initiate thumbnail generation for files scanned in one process
        """
        rpd_files = [self.rpd_files[unique_id] for unique_id in self.process_index[scan_pid]]
        self.thumbnail_manager.add_task(rpd_files)
    
    def update_thumbnail(self, thumbnail_data):
        """
        Takes the generated thumbnail and updates the display
        
        If the thumbnail_data includes a second image, that is used to
        update the thumbnail list using the unique_id
        """
        unique_id = thumbnail_data[0]
        thumbnail_icon = thumbnail_data[1]
        
        if thumbnail_icon is not None:
            # get the thumbnail icon in PIL format
            thumbnail_icon = thumbnail_icon.get_image()
            
            treerowref = self.treerow_index[unique_id]
            path = treerowref.get_path()
            iter = self.liststore.get_iter(path)
            
            if thumbnail_icon:
                self.liststore.set(iter, 0, thumbnail_icon)
                
            if len(thumbnail_data) > 2:
                # get the 2nd image in PIL format
                self.thumbnails[unique_id] = thumbnail_data[2].get_image()

            
    def thumbnail_results(self, source, condition):
        connection = self.thumbnail_manager.get_pipe(source)
        
        conn_type, data = connection.recv()
        
        if conn_type == rpdmp.CONN_COMPLETE:
            connection.close()
            return False
        else:
            
            for thumbnail_data in data:
                self.update_thumbnail(thumbnail_data)
            
            self.thumbnails_generated += len(data)
            
            # clear progress bar information if all thumbnails have been
            # extracted
            if self.thumbnails_generated == self.total_thumbs_to_generate:
                self.rapid_app.download_progressbar.set_fraction(0.0)
                self.rapid_app.download_progressbar.set_text('')
                self.thumbnails_generated = 0
                self.total_thumbs_to_generate = 0

            else:
                self.rapid_app.download_progressbar.set_fraction(
                    float(self.thumbnails_generated) / self.total_thumbs_to_generate)
            
        
        return True
        
    def preview_results(self, unique_id, preview_full_size, preview_small):
        """
        Receive a full size preview image and update
        """
        self.previews_being_fetched.remove(unique_id)
        if preview_full_size:
            preview_image = preview_full_size.get_image()
            self.previews[unique_id] = preview_image
            self.rapid_app.update_preview_image(unique_id, preview_image)
                    
    
    def clear_all(self, scan_pid=None, keep_downloaded_files=False):
        """
        Removes files from display and internal tracking.
        
        If scan_pid is not None, then only files matching that scan_pid will
        be removed. Otherwise, everything will be removed.
        
        If keep_downloaded_files is True, files will not be removed if they
        have been downloaded.
        """
        if scan_pid is None and not keep_downloaded_files:
            self.liststore.clear()
            self.treerow_index = {}
            self.process_index = {}
            
            self.rpd_files = {}
        else:
            if scan_pid in self.process_index:
                for unique_id in self.process_index[scan_pid]:
                    rpd_file = self.rpd_files[unique_id]
                    if not keep_downloaded_files or not rpd_file.status in DOWNLOADED:
                        treerowref = self.treerow_index[rpd_file.unique_id]
                        path = treerowref.get_path()
                        iter = self.liststore.get_iter(path)
                        self.liststore.remove(iter)
                        del self.treerow_index[rpd_file.unique_id]
                        del self.rpd_files[rpd_file.unique_id]
                if not keep_downloaded_files or not len(self.process_index[scan_pid]):
                    del self.process_index[scan_pid]
    
class TaskManager:
    def __init__(self, results_callback, batch_size):
        self.results_callback = results_callback
        
        # List of actual process, it's terminate_queue, and it's run_event
        self._processes = []
        
        self._pipes = {}
        self.batch_size = batch_size
        
        self.paused = False
        self.no_tasks = 0
       
    
    def add_task(self, task):
        pid = self._setup_task(task)
        logger.debug("TaskManager PID: %s", pid)
        self.no_tasks += 1
        return pid

        
    def _setup_task(self, task):
        task_results_conn, task_process_conn = Pipe(duplex=False)
        
        source = task_results_conn.fileno()
        self._pipes[source] = task_results_conn
        gobject.io_add_watch(source, gobject.IO_IN, self.results_callback)
        
        terminate_queue = Queue()
        run_event = Event()
        run_event.set()
        
        return self._initiate_task(task, task_process_conn, terminate_queue, run_event)
        
    def _initiate_task(self, task, task_process_conn, terminate_queue, run_event):
        logger.error("Implement child class method!")
        
    
    def processes(self):
        for i in range(len(self._processes)):
            yield self._processes[i]        
    
    def start(self):
        self.paused = False
        for scan in self.processes():
            run_event = scan[2]
            if not run_event.is_set():
                run_event.set()
                
    def pause(self):
        self.paused = True
        for scan in self.processes():
            run_event = scan[2]
            if run_event.is_set():
                run_event.clear()
    
    def request_termination(self):
        """
        Send a signal to processes that they should immediately terminate
        """
        requested = False
        for p in self.processes():
            if p[0].is_alive():
                requested = True
                p[1].put(None)
                # The process might be paused: let it run
                run_event = p[2]
                if not run_event.is_set():
                    run_event.set()
                    
        return requested
    
    def terminate_forcefully(self):
        """
        Forcefully terminates any running processes. Use with great caution.
        No cleanup action is performed. 
        
        As python essential reference (4th edition) says, if the process
        'holds a lock or is involved with interprocess communication,
        terminating it might cause a deadlock or corrupted I/O.'
        """
        
        for p in self.processes():
            if p[0].is_alive():
                p[0].terminate()

            
    def get_pipe(self, source):
        return self._pipes[source]
        
    def get_no_active_processes(self):
        """
        Returns how many processes are currently active, i.e. running
        """
        i = 0
        for p in self.processes():
            if p[0].is_alive():
                i += 1
        return i


class ScanManager(TaskManager):
    
    def __init__(self, results_callback, batch_size, generate_folder,
                 add_device_function):
        TaskManager.__init__(self, results_callback, batch_size)
        self.add_device_function = add_device_function
        self.generate_folder = generate_folder
        
    def _initiate_task(self, device, task_process_conn, terminate_queue, run_event):
        scan = scan_process.Scan(device.get_path(), self.batch_size, self.generate_folder, 
                                task_process_conn, terminate_queue, run_event)
        scan.start()
        self._processes.append((scan, terminate_queue, run_event))
        self.add_device_function(scan.pid, device, 
            # This refers to when a device like a hard drive is having its contents scanned,
            # looking for photos or videos. It is visible initially in the progress bar for each device 
            # (which normally holds "x photos and videos").
            # It maybe displayed only briefly if the contents of the device being scanned is small.
            progress_bar_text=_('scanning...'))
            
        return scan.pid
            
class CopyFilesManager(TaskManager):
    
    def _initiate_task(self, task, task_process_conn, terminate_queue, run_event):
        photo_download_folder = task[0]
        video_download_folder = task[1]
        scan_pid = task[2]
        files = task[3]
        generate_thumbnails = task[4]
        
        copy_files = copyfiles.CopyFiles(photo_download_folder,
                                video_download_folder,
                                files, generate_thumbnails,
                                scan_pid, self.batch_size, 
                                task_process_conn, terminate_queue, run_event)
        copy_files.start()
        self._processes.append((copy_files, terminate_queue, run_event))
        return copy_files.pid
        
class ThumbnailManager(TaskManager):
        
    def _initiate_task(self, files, task_process_conn, terminate_queue, run_event):
        generator = tn.GenerateThumbnails(files, self.batch_size, task_process_conn, terminate_queue, run_event)
        generator.start()
        self._processes.append((generator, terminate_queue, run_event))
        return generator.pid


class SingleInstanceTaskManager:
    """
    Base class to manage single instance processes. Examples are daemon
    processes, but also a non-daemon process that has one simple task.
    
    Core (infrastructure) functionality is implemented in this class.
    Derived classes should implemented functionality to actually implement
    specific tasks.
    """
    def __init__(self, results_callback):    
        self.results_callback = results_callback
        
        self.task_results_conn, self.task_process_conn = Pipe(duplex=True)
        
        source = self.task_results_conn.fileno()
        gobject.io_add_watch(source, gobject.IO_IN, self.task_results)

        
class PreviewManager(SingleInstanceTaskManager):
    def __init__(self, results_callback):
        SingleInstanceTaskManager.__init__(self, results_callback)
        self._get_preview = tn.GetPreviewImage(self.task_process_conn)
        self._get_preview.start()
        
    def get_preview(self, unique_id, full_file_name, file_type, size_max):
        self.task_results_conn.send((unique_id, full_file_name, file_type, size_max))
        
    def task_results(self, source, condition):
        unique_id, preview_full_size, preview_small = self.task_results_conn.recv()
        self.results_callback(unique_id, preview_full_size, preview_small)
        return True 
        
class SubfolderFileManager(SingleInstanceTaskManager):
    """
    Manages the daemon process that renames files and creates subfolders
    """
    def __init__(self, results_callback, sequence_values):
        SingleInstanceTaskManager.__init__(self, results_callback)
        self._subfolder_file = subfolderfile.SubfolderFile(self.task_process_conn, sequence_values)
        self._subfolder_file.start()
        logger.debug("SubfolderFile PID: %s", self._subfolder_file.pid)
        
    def rename_file_and_move_to_subfolder(self, download_succeeded, 
            download_count, rpd_file):
                                              
        self.task_results_conn.send((download_succeeded, download_count, 
            rpd_file))
        logger.debug("Download count: %s.", download_count)
        

    def task_results(self, source, condition):
        move_succeeded, rpd_file = self.task_results_conn.recv()
        self.results_callback(move_succeeded, rpd_file)
        return True
        


class ResizblePilImage(gtk.DrawingArea):
    def __init__(self, bg_color=None):
        gtk.DrawingArea.__init__(self)
        self.base_image = None
        self.bg_color = bg_color
        self.connect('expose_event', self.expose)
        
    def set_image(self, image):
        self.base_image = image
        
        #set up sizes and ratio used for drawing the derived image
        self.base_image_w = self.base_image.size[0]
        self.base_image_h = self.base_image.size[1]
        self.base_image_aspect = float(self.base_image_w) / self.base_image_h
        
        self.queue_draw()
        
    def expose(self, widget, event):

        cairo_context = self.window.cairo_create()
        
        x = event.area.x 
        y = event.area.y 
        w = event.area.width
        h = event.area.height
        
        #constrain operations to event area 
        cairo_context.rectangle(x, y, w, h)
        cairo_context.clip_preserve()
        
        #set background color, if needed
        if self.bg_color:
            cairo_context.set_source_rgb(*self.bg_color)
            cairo_context.fill_preserve()        

        if not self.base_image:
            return False
            
        frame_aspect = float(w) / h
        
        if frame_aspect > self.base_image_aspect:
            # Frame is wider than image
            height = h
            width = int(height * self.base_image_aspect)
        else:
            # Frame is taller than image
            width = w
            height = int(width / self.base_image_aspect)
            
        #resize image
        pil_image = self.base_image.copy()
        if self.base_image_w < width or self.base_image_h < height:
            logger.debug("Upsizing image")
            pil_image = tn.upsize_pil(pil_image, (width, height))
        else:
            logger.debug("Downsizing image")
            tn.downsize_pil(pil_image, (width, height))

        #image width and height
        image_w = pil_image.size[0]
        image_h = pil_image.size[1]
        
        #center the image horizontally and vertically
        #top left and right corners for the image:
        image_x = x + ((w - image_w) / 2)
        image_y = y + ((h - image_h) / 2)
        
        image = create_cairo_image_surface(pil_image, image_w, image_h)
        cairo_context.set_source_surface(image, image_x, image_y)
        cairo_context.paint()        

        return False    
        
        

class PreviewImage:
    
    def __init__(self, parent_app, builder):
        #set background color to equivalent of '#444444
        self.preview_image = ResizblePilImage(bg_color=(0.267, 0.267, 0.267)) 
        self.preview_image_eventbox = builder.get_object("preview_eventbox")
        self.preview_image_eventbox.add(self.preview_image)
        self.preview_image.show()
        self.download_this_checkbutton = builder.get_object("download_this_checkbutton")
        self.rapid_app = parent_app
        
        self.base_preview_image = None # large size image used to scale down from
        self.current_preview_size = (0,0)
        self.preview_image_size_limit = (0,0)
        
        self.unique_id = None
        
    def set_preview_image(self, unique_id, pil_image, include_checkbutton_visible=None, 
                          checked=None):
        """
        """
        self.preview_image.set_image(pil_image)
        self.unique_id = unique_id
        if checked is not None:
            self.download_this_checkbutton.set_active(checked)
            self.download_this_checkbutton.grab_focus()

        if include_checkbutton_visible is not None:
            self.download_this_checkbutton.props.visible = include_checkbutton_visible
        
    def update_preview_image(self, unique_id, pil_image):
        if unique_id == self.unique_id:
            self.set_preview_image(unique_id, pil_image)
      

        
class RapidApp(dbus.service.Object):
    """
    The main Rapid Photo Downloader application class.
    
    Contains functionality for main program window, and directs all other
    processes.
    """
     
    def __init__(self,  bus, path, name, taskserver=None): 
        
        dbus.service.Object.__init__ (self, bus, path, name)
        self.running = False
        
        self.taskserver = taskserver
        
        # Setup program preferences, and set callback for when they change
        self._init_prefs()
        
        # Initialize widgets in the main window, and variables that point to them
        self._init_widgets()
        self._init_pynotify()
        
        # Initialize job code handling
        self._init_job_code()
        
        # Remember the window size from the last time the program was run, or
        # set a default size
        self._set_window_size()
        
        # Setup various widgets
        self._setup_buttons()
        self._setup_error_icons()
        self._setup_icons()
            
        # Show the main window
        self.rapidapp.show()
        
        # Check program preferences - don't allow auto start if there is a problem
        prefs_valid, msg = prefsrapid.check_prefs_for_validity(self.prefs)
        if not prefs_valid:
            self.notify_prefs_are_invalid(details=msg)
        
        # Initialize variables with which to track important downloads results
        self._init_download_tracking()
        
        # Set up process managers.
        # A task such as scanning a device or copying files is handled in its
        # own process.
        self._start_process_managers()
        
        # Setup devices from which to download from and backup to
        self.setup_devices(on_startup=True, on_preference_change=False, 
                           block_auto_start=not prefs_valid)
        
        # Ensure the device collection scrolled window is not too small
        self._set_device_collection_size()
    
    def on_rapidapp_destroy(self, widget, data=None):

        self._terminate_processes(terminate_file_copies = True)

        # save window and component sizes
        self.prefs.vpaned_pos = self.main_vpaned.get_position()

        x, y, width, height = self.rapidapp.get_allocation()
        self.prefs.main_window_size_x = width
        self.prefs.main_window_size_y = height
        
        self.prefs.set_downloads_today_from_tracker(self.downloads_today_tracker)
        
        gtk.main_quit()
        
    def _terminate_processes(self, terminate_file_copies=False):
        
        # FIXME: need more fine grained tuning here - must cancel large file
        # copies midstream
        if terminate_file_copies:
            logger.info("Terminating all processes...")

        scan_termination_requested = self.scan_manager.request_termination()        
        thumbnails_termination_requested = self.thumbnails.thumbnail_manager.request_termination()
        if terminate_file_copies:
            copy_files_termination_requested = self.copy_files_manager.request_termination()
        else:
            copy_files_termination_requested = False
        
        if scan_termination_requested or thumbnails_termination_requested:
            time.sleep(1)
            if (self.scan_manager.get_no_active_processes() > 0 or 
                self.thumbnails.thumbnail_manager.get_no_active_processes() > 0):
                time.sleep(1)
                # must try again, just in case a new scan has meanwhile started!
                self.scan_manager.request_termination()
                self.thumbnails.thumbnail_manager.terminate_forcefully()
                self.scan_manager.terminate_forcefully()
                
        if terminate_file_copies and copy_files_termination_requested:
            time.sleep(1)
            self.copy_files_manager.terminate_forcefully()
        
        if terminate_file_copies:
            self._clean_all_temp_dirs()
        
    # # #
    # Events and tasks related to displaying preview images and thumbnails
    # # #

    def on_download_this_checkbutton_toggled(self, checkbutton):
        value = checkbutton.get_active()
        self.thumbnails.set_selected(self.preview_image.unique_id, value)
        self.set_download_action_sensitivity()
    
    def on_preview_eventbox_button_press_event(self, widget, event):
        
        if event.type == gtk.gdk._2BUTTON_PRESS and event.button == 1:
            self.show_thumbnails()    
    
    def on_show_thumbnails_action_activate(self, action):
        logger.debug("on_show_thumbnails_action_activate")
        self.show_thumbnails()
        
    def on_show_image_action_activate(self, action):
        logger.debug("on_show_image_action_activate")
        self.thumbnails.show_preview()
        
    def on_check_all_action_activate(self, action):
        self.thumbnails.check_all(check_all=True)
        
    def on_uncheck_all_action_activate(self, action):
        self.thumbnails.check_all(check_all=False)

    def on_check_all_photos_action_activate(self, action):
        self.thumbnails.check_all(check_all=True, 
                                  file_type=rpdfile.FILE_TYPE_PHOTO)
        
    def on_check_all_videos_action_activate(self, action):
        self.thumbnails.check_all(check_all=True, 
                                  file_type=rpdfile.FILE_TYPE_VIDEO)
                                  
    def on_quit_action_activate(self, action):
        self.on_rapidapp_destroy(widget=self.rapidapp, data=None)
        
    def on_refresh_action_activate(self, action):
        self.setup_devices(on_startup=False, on_preference_change=False,
                           block_auto_start=True)
                           
    def on_get_help_action_activate(self, action):
        webbrowser.open("http://www.damonlynch.net/rapid/help.html")
        
    def on_about_action_activate(self, action):
        self.about.set_property("name", PROGRAM_NAME)
        self.about.set_property("version", utilities.human_readable_version(
                                                                __version__))
        self.about.run()
        self.about.destroy() 
        
    def on_report_problem_action_activate(self, action):
        webbrowser.open("https://bugs.launchpad.net/rapid")
        
    def on_translate_action_activate(self, action):
        webbrowser.open("http://www.damonlynch.net/rapid/translate.html")
     
    def on_donate_action_activate(self, action):
        webbrowser.open("http://www.damonlynch.net/rapid/donate.html")
             
    def show_preview_image(self, unique_id, image, include_checkbutton_visible, checked):
        if self.main_notebook.get_current_page() == 0: # thumbnails
            logger.debug("Switching to preview image display")
            self.main_notebook.set_current_page(1)
        self.preview_image.set_preview_image(unique_id, image, include_checkbutton_visible, checked)
        self.next_image_action.set_sensitive(True)
        self.prev_image_action.set_sensitive(True)
        
    def update_preview_image(self, unique_id, image):
        self.preview_image.update_preview_image(unique_id, image)
        
    def show_thumbnails(self):
        logger.debug("Switching to thumbnails display")
        self.main_notebook.set_current_page(0)
        self.thumbnails.select_image(self.preview_image.unique_id)
        self.next_image_action.set_sensitive(False)
        self.prev_image_action.set_sensitive(False)
        
        
    def on_next_image_action_activate(self, action):
        if self.preview_image.unique_id is not None:
            self.thumbnails.show_next_image(self.preview_image.unique_id)
    
    def on_prev_image_action_activate(self, action):
        if self.preview_image.unique_id is not None:        
            self.thumbnails.show_prev_image(self.preview_image.unique_id)
        
    def set_thumbnail_sort(self):
        """
        If all the scans are complete, sets the sort order
        """
        if self.scan_manager.get_no_active_processes() == 0:
            self.thumbnails.sort_by_timestamp()


    # # #
    # Volume management
    # # #
    
    def start_volume_monitor(self):
        if not self.vmonitor:
            self.vmonitor = gio.volume_monitor_get()
            self.vmonitor.connect("mount-added", self.on_mount_added)
            self.vmonitor.connect("mount-removed", self.on_mount_removed) 
    
            
    def setup_devices(self, on_startup, on_preference_change, block_auto_start):
        """
        
        Setup devices from which to download from and backup to
        
        Sets up volumes for downloading from and backing up to
        
        on_startup should be True if the program is still starting, 
        i.e. this is being called from the program's initialization.
        
        on_preference_change should be True if this is being called as the
        result of a preference being changed
        
        block_auto_start should be True if automation options to automatically
        start a download should be ignored
        
        Removes any image media that are currently not downloaded, 
        or finished downloading        
        """
        
        if self.using_volume_monitor():
            self.start_volume_monitor()
        

        self.clear_non_running_downloads()
        
        mounts = []
        self.backup_devices = {}
        
        # Clear download statistics and tracking
        # FIXME
        
        if self.using_volume_monitor():
            # either using automatically detected backup devices
            # or download devices
            for mount in self.vmonitor.get_mounts():
                if not mount.is_shadowed():
                    path = mount.get_root().get_path()
                    if path:
                        if (path in self.prefs.device_blacklist and 
                                    self.search_for_PSD()):
                            logger.info("%s ignored", mount.get_name())
                        else:
                            logger.info("Detected %s", mount.get_name())
                            is_backup_mount = self.check_if_backup_mount(path)
                            if is_backup_mount:
                                self.backup_devices[path] = mount
                            elif (self.prefs.device_autodetection and 
                                 (dv.is_DCIM_device(path) or 
                                  self.search_for_PSD())):
                                mounts.append((path, mount))
                    
        
        if not self.prefs.device_autodetection:
            # user manually specified the path from which to download 
            path = self.prefs.device_location
            if path:
                logger.info("Using manually specified path %s", path)
                if utilities.is_directory(path):
                    mounts.append((path, None))
                else:
                    logger.error("Download path does not exist: %s", path)

        if self.prefs.backup_images:
            if not self.prefs.backup_device_autodetection:
                # user manually specified backup location
                # will backup to this path, but don't need any volume info 
                # associated with it
                self.backup_devices[self.prefs.backup_location] = None
        
        # Display amount of free space in a status bar message
        self.display_free_space()
        
        if block_auto_start:
            self.auto_start_is_on = False
        else:
            self.auto_start_is_on = ((not on_preference_change) and
                                    ((self.prefs.auto_download_at_startup and 
                                      on_startup) or 
                                      (self.prefs.auto_download_upon_device_insertion and
                                       not on_startup)))
        

        self.testing_auto_exit = False
        self.testing_auto_exit_trip = len(mounts)
        self.testing_auto_exit_trip_counter = 0
        

        for m in mounts:
            path, mount = m
            device = dv.Device(path=path, mount=mount)
            if (self.search_for_PSD() and 
                    path not in self.prefs.device_whitelist):
                # prompt user to see if device should be used or not
                self.get_use_device(device)
            else:
                scan_pid = self.scan_manager.add_task(device)
                if mount is not None:
                    self.mounts_by_path[path] = scan_pid
        if not mounts:
            self.set_download_action_sensitivity()
        
    def get_use_device(self, device):  
        """ Prompt user whether or not to download from this device """
        
        logger.info("Prompting whether to use %s", device.get_name())
        d = dv.UseDeviceDialog(self.rapidapp, device, self.got_use_device)
        
    def got_use_device(self, dialog, user_selected, permanent_choice, device):
        """ User has chosen whether or not to use a device to download from """
        dialog.destroy()
        
        path = device.get_path()
        
        if user_selected:
            if permanent_choice and path not in self.prefs.device_whitelist:
                # do NOT do a list append operation here without the assignment,
                # or the actual preferences will not be updated!!
                if len(self.prefs.device_whitelist):
                    self.prefs.device_whitelist = self.prefs.device_whitelist + [path]
                else:
                    self.prefs.device_whitelist = [path]
            scan_pid = self.scan_manager.add_task(device)
            self.mounts_by_path[path] = scan_pid
            
        elif permanent_choice and path not in self.prefs.device_blacklist:
            # do not do a list append operation here without the assignment, or the preferences will not be updated!
            if len(self.prefs.device_blacklist):
                self.prefs.device_blacklist = self.prefs.device_blacklist + [path]
            else:
                self.prefs.device_blacklist = [path]    
     
    def search_for_PSD(self):
        """
        Check to see if user preferences are to automatically search for 
        Portable Storage Devices or not
        """
        return self.prefs.device_autodetection_psd and self.prefs.device_autodetection

    def check_if_backup_mount(self,  path):
        """
        Checks to see if backups are enabled and path represents a valid backup location
        
        Checks against user preferences.
        """
        identifiers = [self.prefs.backup_identifier]
        if DOWNLOAD_VIDEO:
            identifiers.append(self.prefs.video_backup_identifier)
        if self.prefs.backup_images:
            if self.prefs.backup_device_autodetection:
                if dv.is_backup_media(path, identifiers):
                    return True
            elif path == self.prefs.backup_location:
                # user manually specified the path
                return True
        return False        
            
    def using_volume_monitor(self):
        """
        Returns True if programs needs to use gio volume monitor
        """
        
        return (self.prefs.device_autodetection or 
                (self.prefs.backup_images and 
                self.prefs.backup_device_autodetection
                ))
                    
    def on_mount_added(self, vmonitor, mount):
        """
        callback run when gio indicates a new volume
        has been mounted
        """


        if mount.is_shadowed():
            # ignore this type of mount
            return
            
        path = mount.get_root().get_path()
        if path is not None:

            if path in self.prefs.device_blacklist and self.search_for_PSD():
                logger.info("Device %(device)s (%(path)s) ignored" % {
                            'device': mount.get_name(), 'path': path})
            else:
                is_backup_mount = self.check_if_backup_mount(path)
                            
                if is_backup_mount:
                    if path not in self.backup_devices:
                        self.backup_devices[path] = mount
                        self.display_free_space()

                elif self.prefs.device_autodetection and (dv.is_DCIM_device(path) or 
                                                            self.search_for_PSD()):
                    
                    self.auto_start_is_on = self.prefs.auto_download_upon_device_insertion
                    device = dv.Device(path=path, mount=mount)
                    if self.search_for_PSD() and path not in self.prefs.device_whitelist:
                        # prompt user if device should be used or not
                        self.get_use_device(device)
                    else:   
                        scan_pid = self.scan_manager.add_task(device)
                        self.mounts_by_path[path] = scan_pid
            
    def on_mount_removed(self, vmonitor, mount):
        """
        callback run when gio indicates a new volume
        has been mounted
        """
        
        path = mount.get_root().get_path()

        # three scenarios -
        # the mount has been scanned but downloading has not yet started
        # files are being downloaded from mount (it must be a messy unmount)
        # files have finished downloading from mount
        
        if path in self.mounts_by_path:
            scan_pid = self.mounts_by_path[path]
            del self.mounts_by_path[path]
            # temp directory should be cleaned by finishing of process
            
            #~ if scan_pid in self.download_active_by_scan_pid:
                #~ self._clean_temp_dirs_for_scan_pid(scan_pid)
            self.thumbnails.clear_all(scan_pid = scan_pid, 
                                      keep_downloaded_files = True)
            self.device_collection.remove_device(scan_pid)
            
                
                    
        # remove backup volumes
        elif path in self.backup_devices:
            del self.backup_devices[path]
            self.display_free_space()
                
        # may need to disable download button and menu
        self.set_download_action_sensitivity()
            
    def clear_non_running_downloads(self):
        """
        Clears the display of downloads that are currently not running
        """
        
        # Stop any processes currently scanning or creating thumbnails
        self._terminate_processes(terminate_file_copies=False)
        
        # Remove them from the user interface
        for scan_pid in self.device_collection.get_all_displayed_processes():
            if scan_pid not in self.download_active_by_scan_pid:
                self.device_collection.remove_device(scan_pid)
                self.thumbnails.clear_all(scan_pid=scan_pid)
            
        

    
    # # #
    # Download and help buttons, and menu items
    # # #
    
    def on_download_action_activate(self, action):
        """
        Called when a download is activated
        """
        
        if self.copy_files_manager.paused:
            logger.debug("Download resumed")
            self.resume_download()
        else:
            logger.debug("Download activated")
            
            if self.download_action_is_download:
                if self.need_job_code_for_naming and not self.prompting_for_job_code:
                    self.get_job_code()
                else:
                    self.start_download()
            else:
                self.pause_download()

    
    def on_help_action_activate(self, action):
        webbrowser.open("http://www.damonlynch.net/rapid/documentation")
        
    def on_preferences_action_activate(self, action):

        preferencesdialog.PreferencesDialog(self)
        
    def set_download_action_sensitivity(self):
        """
        Sets sensitivity of Download action to enable or disable it
        
        Affects download button and menu item
        """
        if not self.download_is_occurring():
            sensitivity = False
            if self.scan_manager.no_tasks == 0:
                if self.thumbnails.files_are_checked_to_download():
                    sensitivity = True
                    
            self.download_action.set_sensitive(sensitivity)
            
    def set_download_action_label(self, is_download):
        """
        Toggles label betwen pause and download 
        """
        
        if is_download:
            self.download_action.set_label(_("Download"))
            self.download_action_is_download = True
        else:
            self.download_action.set_label(_("Pause"))
            self.download_action_is_download = False
    
    # # #
    # Job codes
    # # #
    
    
    def _init_job_code(self):
        self.job_code = self.last_chosen_job_code = ''
        self.need_job_code_for_naming = self.prefs.any_pref_uses_job_code()
        self.prompting_for_job_code = False

    def assign_job_code(self, code):
        """ assign job code (which may be empty) to member variable and update user preferences
        
        Update preferences only if code is not empty. Do not duplicate job code.
        """

        self.job_code = code
        
        if code:
            #add this value to job codes preferences
            #delete any existing value which is the same
            #(this way it comes to the front, which is where it should be)
            #never modify self.prefs.job_codes in place! (or prefs become screwed up)
            
            jcs = self.prefs.job_codes
            while code in jcs:
                jcs.remove(code)
                
            self.prefs.job_codes = [code] + jcs

    def _get_job_code(self, post_job_code_entry_callback):
        """ prompt for a job code """
        
        if not self.prompting_for_job_code:
            logger.debug("Prompting for Job Code")
            self.prompting_for_job_code = True
            j = preferencesdialog.JobCodeDialog(parent_window = self.rapidapp,
                    job_codes = self.prefs.job_codes,
                    default_job_code = self.last_chosen_job_code, 
                    post_job_code_entry_callback=post_job_code_entry_callback,
                    entry_only = False)
        else:
            logger.debug("Already prompting for Job Code, do not prompt again")
        
    def get_job_code(self):
        self._get_job_code(self.got_job_code)
        
    def got_job_code(self, dialog, user_chose_code, code):
        dialog.destroy()
        self.prompting_for_job_code = False
        
        if user_chose_code:
            if code is None:
                code = ''
            self.assign_job_code(code)
            self.last_chosen_job_code = code
            logger.debug("Job Code %s entered", self.job_code)
            self.start_download() 
                
        else:
            # user cancelled
            logger.debug("No Job Code entered")
            self.job_code = ''
            self.auto_start_is_on = False
   
    
    # # #
    # Download
    # # #
    
    def _init_download_tracking(self):
        """
        Initialize variables to track downloads
        """
        # Track download sizes and other values for each device.
        # (Scan id acts as an index to each device. A device could be scanned
        #  more than once).
        self.download_tracker = downloadtracker.DownloadTracker()
        
        # Track which temporary directories are created when downloading files
        self.temp_dirs_by_scan_pid = dict()
        
        # Track which downloads are running
        self.download_active_by_scan_pid = []
        

    
    def start_download(self, scan_pid=None):
        """
        Start download, renaming and backup of files.
        
        If scan_pid is specified, only files matching it will be downloaded
        """
        
        files_by_scan_pid = self.thumbnails.get_files_checked_for_download(scan_pid)
        folders_valid, invalid_dirs = self.check_download_folder_validity(files_by_scan_pid)
        
        if not folders_valid:
            if len(invalid_dirs) > 1:
                msg = _("These download folders are invalid:\n%(folder1)s\n%(folder2)s") % {
                        'folder1': invalid_dirs[0], 'folder2': invalid_dirs[1]}
            else:
                msg = _("This download folder is invalid:\n%s") % invalid_dirs[0]
            self.log_error(config.CRITICAL_ERROR, _("Download cannot proceed"),
                msg)
        else:
            # set time download is starting if it is not already set
            # it is unset when all downloads are completed
            if self.download_start_time is None:
                self.download_start_time = datetime.datetime.now()  
            
            self.thumbnails.mark_download_pending(files_by_scan_pid)
            for scan_pid in files_by_scan_pid:
                files = files_by_scan_pid[scan_pid]
                self.download_files(files, scan_pid)
                
            self.set_download_action_label(is_download = False)
        
    def pause_download(self):
        
        self.copy_files_manager.pause()
        
        # set action to display Download
        if not self.download_action_is_download:
            self.set_download_action_label(is_download = True)
            
        self.time_check.pause()
            
    def resume_download(self):
        for scan_pid in self.download_active_by_scan_pid:
            self.time_remaining.set_time_mark(scan_pid)
        
        self.time_check.set_download_mark()
            
        self.copy_files_manager.start()

    def download_files(self, files, scan_pid):
        """
        Initiate downloading and renaming of files
        """
        
        # Check which file types will be downloaded for this particular process
        if self.files_of_type_present(files, rpdfile.FILE_TYPE_PHOTO):
            photo_download_folder = self.prefs.download_folder
        else:
            photo_download_folder = None
            
        if self.files_of_type_present(files, rpdfile.FILE_TYPE_VIDEO):
            video_download_folder = self.prefs.video_download_folder
        else:
            video_download_folder = None
        
        download_size = self.size_files_to_be_downloaded(files)
        self.download_tracker.init_stats(scan_pid=scan_pid, 
                                bytes=download_size,
                                no_files=len(files))
        
        self.time_remaining.set(scan_pid, download_size)
        self.time_check.set_download_mark()
            
        self.download_active_by_scan_pid.append(scan_pid)
        
        
        if len(self.download_active_by_scan_pid) > 1:
            self.display_summary_notification = True
            
        # Initiate copy files process
        self.copy_files_manager.add_task((photo_download_folder, 
                              video_download_folder, scan_pid,
                              files, self.auto_start_is_on))
                              
    def copy_files_results(self, source, condition):
        """
        Handle results from copy files process
        """
        #FIXME: must handle early termination / pause of copy files process
        connection = self.copy_files_manager.get_pipe(source)
        conn_type, msg_data = connection.recv()
        if conn_type == rpdmp.CONN_PARTIAL:
            msg_type, data = msg_data

            if msg_type == rpdmp.MSG_TEMP_DIRS:
                scan_pid, photo_temp_dir, video_temp_dir = data
                self.temp_dirs_by_scan_pid[scan_pid] = (photo_temp_dir, video_temp_dir)                
            elif msg_type == rpdmp.MSG_BYTES:
                scan_pid, total_downloaded, chunk_downloaded = data
                self.download_tracker.set_total_bytes_copied(scan_pid, 
                                                             total_downloaded)
                self.time_check.increment(bytes_downloaded=chunk_downloaded)
                percent_complete = self.download_tracker.get_percent_complete(scan_pid)
                self.device_collection.update_progress(scan_pid, percent_complete,
                                            None, None)
                self.time_remaining.update(scan_pid, total_downloaded)
            elif msg_type == rpdmp.MSG_FILE:
                download_succeeded, rpd_file, download_count, temp_full_file_name = data
                
                self.download_tracker.set_download_count_for_file(
                                            rpd_file.unique_id, download_count)
                self.download_tracker.set_download_count(
                                            rpd_file.scan_pid, download_count)
                rpd_file.download_start_time = self.download_start_time
                
                if download_succeeded:
                    # Insert preference values needed for name generation
                    rpd_file = prefsrapid.insert_pref_lists(self.prefs, rpd_file)
                    rpd_file.strip_characters = self.prefs.strip_characters
                    rpd_file.download_folder = self.prefs.get_download_folder_for_file_type(rpd_file.file_type)
                    rpd_file.download_conflict_resolution = self.prefs.download_conflict_resolution
                    rpd_file.synchronize_raw_jpg = self.prefs.must_synchronize_raw_jpg()
                    rpd_file.job_code = self.job_code 
                
                self.subfolder_file_manager.rename_file_and_move_to_subfolder(
                        download_succeeded, 
                        download_count, 
                        rpd_file
                        )
            elif msg_type == rpdmp.MSG_THUMB:
                #~ unique_id, thumbnail, thumbnail_icon = data
                #~ thumbnail_data = (unique_id
                self.thumbnails.update_thumbnail(data)    
                
            return True
        else:
            # Process is complete, i.e. conn_type == rpdmp.CONN_COMPLETE
            connection.close()
            return False
            

    
    def download_is_occurring(self):
        """Returns True if a file is currently being downloaded or renamed
        """
        v = not len(self.download_active_by_scan_pid) == 0
        #~ logger.info("Download is occurring: %s", v)
        return v
    
    # # #
    # Create folder and file names for downloaded files
    # # #
    
    def subfolder_file_results(self, move_succeeded, rpd_file):
        """
        Handle results of subfolder creation and file renaming
        """
            
        scan_pid = rpd_file.scan_pid
        unique_id = rpd_file.unique_id
        
        self.thumbnails.update_status_post_download(rpd_file)
        
        # Update error log window if neccessary
        if not move_succeeded:
            self.log_error(config.SERIOUS_ERROR, rpd_file.error_title, 
                           rpd_file.error_msg, rpd_file.error_extra_detail)
        elif rpd_file.status == config.STATUS_DOWNLOADED_WITH_WARNING:
            self.log_error(config.WARNING, rpd_file.error_title, 
                           rpd_file.error_msg, rpd_file.error_extra_detail)
        
        self.download_tracker.file_downloaded_increment(scan_pid, 
                                                        rpd_file.file_type,
                                                        rpd_file.status)
                                                        
        completed, files_remaining = self._update_file_download_device_progress(scan_pid, unique_id)
        
        if self.download_is_occurring():
            self.update_time_remaining()
                
        if completed:
            # Last file for this scan pid has been downloaded, so clean temp directory
            logger.debug("Purging temp directories")
            self._clean_temp_dirs_for_scan_pid(scan_pid)
            self.download_active_by_scan_pid.remove(scan_pid)
            self.time_remaining.remove(scan_pid)
            self.notify_downloaded_from_device(scan_pid)
            if files_remaining == 0 and self.prefs.auto_unmount:
                self.device_collection.unmount(scan_pid)
            
            
            if not self.download_is_occurring():
                logger.debug("Download completed")
                self.notify_download_complete()
                self.download_progressbar.set_fraction(0.0)
                
                self.prefs.stored_sequence_no = self.stored_sequence_value.value
                self.downloads_today_tracker.set_raw_downloads_today_from_int(self.downloads_today_value.value)
                self.downloads_today_tracker.set_raw_downloads_today_date(self.downloads_today_date_value.value)
                self.prefs.set_downloads_today_from_tracker(self.downloads_today_tracker)

                if ((self.prefs.auto_exit and self.download_tracker.no_errors_or_warnings()) 
                                                or self.prefs.auto_exit_force):
                    if not self.thumbnails.files_remain_to_download():
                        gtk.main_quit()
                        
                self.download_tracker.purge_all()
                self.speed_label.set_label(" ")
                                        
                self.display_free_space()
                
                self.set_download_action_label(is_download=True)
                self.set_download_action_sensitivity()
                
                self.job_code = ''
                self.download_start_time = None
                
                
    def update_time_remaining(self):
        update, download_speed = self.time_check.check_for_update()
        if update:
            self.speed_label.set_text(download_speed)
            
            time_remaining = self.time_remaining.time_remaining()
            if time_remaining:
                secs =  int(time_remaining)
            
                if secs == 0:
                    message = ""
                elif secs == 1:
                    message = _("About 1 second remaining")
                elif secs < 60:
                    message = _("About %i seconds remaining") % secs 
                elif secs == 60:
                    message = _("About 1 minute remaining")
                else:
                    # Translators: in the text '%(minutes)i:%(seconds)02i', only the : should be translated, if needed. 
                    # '%(minutes)i' and '%(seconds)02i' should not be modified or left out. They are used to format and display the amount
                    # of time the download has remainging, e.g. 'About 5:36 minutes remaining'
                    message = _("About %(minutes)i:%(seconds)02i minutes remaining") % {'minutes': secs / 60, 'seconds': secs % 60}
                
                self.rapid_statusbar.pop(self.statusbar_context_id)
                self.rapid_statusbar.push(self.statusbar_context_id, message)         
            
    def file_types_by_number(self, no_photos, no_videos):
        """ 
        returns a string to be displayed to the user that can be used
        to show if a value refers to photos or videos or both, or just one
        of each
        """
        if (no_videos > 0) and (no_photos > 0):
            v = _('photos and videos')
        elif (no_videos == 0) and (no_photos == 0):
            v = _('photos or videos')
        elif no_videos > 0:
            if no_videos > 1:
                v = _('videos')
            else:
                v = _('video')
        else:
            if no_photos > 1:
                v = _('photos')
            else:
                v = _('photo')
        return v

    def notify_downloaded_from_device(self, scan_pid):
        device = self.device_collection.get_device(scan_pid)
        
        if device.mount is None:
            notificationName = PROGRAM_NAME
        else:
            notificationName  = device.get_name()
        
        no_photos_downloaded = self.download_tracker.get_no_files_downloaded(
                                            scan_pid, rpdfile.FILE_TYPE_PHOTO)
        no_videos_downloaded = self.download_tracker.get_no_files_downloaded(
                                            scan_pid, rpdfile.FILE_TYPE_VIDEO)
        no_photos_failed = self.download_tracker.get_no_files_failed(
                                            scan_pid, rpdfile.FILE_TYPE_PHOTO)
        no_videos_failed = self.download_tracker.get_no_files_failed(
                                            scan_pid, rpdfile.FILE_TYPE_VIDEO)
        no_files_downloaded = no_photos_downloaded + no_videos_downloaded
        no_files_failed = no_photos_failed + no_videos_failed
        no_warnings = self.download_tracker.get_no_warnings(scan_pid)
                                            
        file_types = self.file_types_by_number(no_photos_downloaded, no_videos_downloaded)
        file_types_failed = self.file_types_by_number(no_photos_failed, no_videos_failed)
        message = _("%(noFiles)s %(filetypes)s downloaded") % \
                   {'noFiles':no_files_downloaded, 'filetypes': file_types}
        
        if no_files_failed:
            message += "\n" + _("%(noFiles)s %(filetypes)s failed to download") % {'noFiles':no_files_failed, 'filetypes':file_types_failed}
        
        if no_warnings:
            message = "%s\n%s " % (message,  no_warnings) + _("warnings") 
  
        n = pynotify.Notification(notificationName,  message)
        n.set_icon_from_pixbuf(device.get_icon(self.notification_icon_size))
        
        n.show()
    
    def notify_download_complete(self):
        if self.display_summary_notification:
            message = _("All downloads complete")
            
            # photo downloads
            photo_downloads = self.download_tracker.total_photos_downloaded
            if photo_downloads:
                filetype = self.file_types_by_number(photo_downloads, 0)
                message += "\n" + _("%(number)s %(numberdownloaded)s") % \
                            {'number': photo_downloads, 
                            'numberdownloaded': _("%(filetype)s downloaded") % \
                            {'filetype': filetype}}
            
            # photo failures
            photo_failures = self.download_tracker.total_photo_failures
            if photo_failures:
                filetype = self.file_types_by_number(photo_failures, 0)
                message += "\n" + _("%(number)s %(numberdownloaded)s") % \
                            {'number': photo_failures,
                            'numberdownloaded': _("%(filetype)s failed to download") % \
                            {'filetype': filetype}}
                            
            # video downloads
            video_downloads = self.download_tracker.total_videos_downloaded
            if video_downloads:
                filetype = self.file_types_by_number(0, video_downloads)
                message += "\n" + _("%(number)s %(numberdownloaded)s") % \
                            {'number': video_downloads, 
                            'numberdownloaded': _("%(filetype)s downloaded") % \
                            {'filetype': filetype}}
                            
            # video failures
            video_failures = self.download_tracker.total_video_failures
            if video_failures:
                filetype = self.file_types_by_number(0, video_failures)
                message += "\n" + _("%(number)s %(numberdownloaded)s") % \
                            {'number': video_failures,
                            'numberdownloaded': _("%(filetype)s failed to download") % \
                            {'filetype': filetype}}
            
            # warnings
            warnings = self.download_tracker.total_warnings 
            if warnings:
                message += "\n" + _("%(number)s %(numberdownloaded)s") % \
                            {'number': warnings, 
                            'numberdownloaded': _("warnings")}
                            
            n = pynotify.Notification(PROGRAM_NAME, message)
            n.set_icon_from_pixbuf(self.application_icon)
            n.show()
            self.display_summary_notification = False # don't show it again unless needed
      
        
    def _update_file_download_device_progress(self, scan_pid, unique_id):
        """
        Increments the progress bar for an individual device
        
        Returns if the download is completed for that scan_pid
        It also returns the number of files remaining for the scan_pid, BUT
        this value is valid ONLY if the download is completed
        """
        
        files_downloaded = self.download_tracker.get_download_count_for_file(unique_id)
        files_to_download = self.download_tracker.get_no_files_in_download(scan_pid)
        file_types = self.download_tracker.get_file_types_present(scan_pid)
        completed = files_downloaded == files_to_download
        
        if completed:
            files_remaining = self.thumbnails.get_no_files_remaining(scan_pid)
        else:
            files_remaining = 0
                    
        if completed and files_remaining:
            # e.g.: 3 of 205 photos and videos (202 remaining)
            progress_bar_text = _("%(number)s of %(total)s %(filetypes)s (%(remaining)s remaining)") % {
                                  'number':  files_downloaded, 
                                  'total': files_to_download,
                                  'filetypes': file_types,
                                  'remaining': files_remaining}
        else:
            # e.g.: 205 of 205 photos and videos
            progress_bar_text = _("%(number)s of %(total)s %(filetypes)s") % \
                                 {'number':  files_downloaded, 
                                  'total': files_to_download,
                                  'filetypes': file_types}
        percent_complete = self.download_tracker.get_percent_complete(scan_pid)
        self.device_collection.update_progress(scan_pid=scan_pid,
                                        percent_complete=percent_complete,
                                        progress_bar_text=progress_bar_text, 
                                        bytes_downloaded=None)
        
        percent_complete = self.download_tracker.get_overall_percent_complete()
        self.download_progressbar.set_fraction(percent_complete)
                                        
        return (completed, files_remaining)
        

    def _clean_all_temp_dirs(self):
        """
        Cleans all temp dirs if they exist
        """
        for scan_pid in self.temp_dirs_by_scan_pid:
            for temp_dir in self.temp_dirs_by_scan_pid[scan_pid]:
                self._purge_dir(temp_dir)
                
        self.temp_dirs_by_scan_pid = {}
            
    
    def _clean_temp_dirs_for_scan_pid(self, scan_pid):
        """
        Deletes temp files and folders used in download
        """
        for temp_dir in self.temp_dirs_by_scan_pid[scan_pid]:
            self._purge_dir(temp_dir)
        del self.temp_dirs_by_scan_pid[scan_pid]

    def _purge_dir(self, directory):
        """
        Deletes all files in the directory, and the directory itself.
        
        Does not recursively traverse any subfolders in the directory.
        """
        
        if directory:
            try:
                path = gio.File(directory)
                # first delete any files in the temp directory
                # assume there are no directories in the temp directory
                file_attributes = "standard::name,standard::type"
                children = path.enumerate_children(file_attributes)
                for child in children:
                    f = path.get_child(child.get_name())
                    f.delete(cancellable=None)
                path.delete(cancellable=None)
                logger.debug("Deleted directory %s", directory)
            except gio.Error, inst:
                logger.error("Failure deleting temporary folder %s", directory)
                logger.error(inst)
    
    
    # # # 
    # Preferences
    # # #
        
        
    def _init_prefs(self): 
        self.prefs = prefsrapid.RapidPreferences()
        self.prefs.notify_add(self.on_preference_changed)
        
        # flag to indicate whether the user changed some preferences that 
        # indicate the image and backup devices should be setup again
        self.rerun_setup_available_image_and_video_media = False
        self.rerun_setup_available_backup_media = False
        
        # flag to indicate that the preferences dialog window is being 
        # displayed to the user
        self.preferences_dialog_displayed = False

        # flag to indicate that the user has modified the download today
        # related values in the preferences dialog window
        self.refresh_downloads_today = False
        
        self.downloads_today_tracker = self.prefs.get_downloads_today_tracker()
        
        downloads_today = self.downloads_today_tracker.get_and_maybe_reset_downloads_today()
        if downloads_today > 0:
            logger.info("Downloads that have occurred so far today: %s", downloads_today)
        else:
            logger.info("No downloads have occurred so far today")        

        self.downloads_today_value = Value(c_int, 
                        self.downloads_today_tracker.get_raw_downloads_today())
        self.downloads_today_date_value = Array(c_char,
                        self.downloads_today_tracker.get_raw_downloads_today_date())
        self.day_start_value = Array(c_char, 
                        self.downloads_today_tracker.get_raw_day_start())
        self.refresh_downloads_today_value = Value(c_bool, False)
        self.stored_sequence_value = Value(c_int, self.prefs.stored_sequence_no)
        self.uses_stored_sequence_no_value = Value(c_bool, self.prefs.any_pref_uses_stored_sequence_no())
        self.uses_session_sequece_no_value = Value(c_bool, self.prefs.any_pref_uses_session_sequece_no())
        self.uses_sequence_letter_value = Value(c_bool, self.prefs.any_pref_uses_sequence_letter_value())
        
        self.prefs.program_version = __version__
        
    def _check_for_sequence_value_use(self):
        self.uses_stored_sequence_no_value.value = self.prefs.any_pref_uses_stored_sequence_no()
        self.uses_session_sequece_no_value.value = self.prefs.any_pref_uses_session_sequece_no()
        self.uses_sequence_letter_value.value = self.prefs.any_pref_uses_sequence_letter_value()    
    
    def on_preference_changed(self, key, value):
        """
        Called when user changes the program's preferences
        """
        logger.debug("Preference change detected: %s", key)
        

        if key == 'show_log_dialog':
            self.menu_log_window.set_active(value)
        elif key in ['device_autodetection', 'device_autodetection_psd', 'device_location']:
            self.rerun_setup_available_image_and_video_media = True
            if not self.preferences_dialog_displayed:
                self.post_preference_change()
                
        elif key in ['backup_images', 'backup_device_autodetection', 'backup_location', 'backup_identifier', 'video_backup_identifier']:
            self.rerun_setup_available_backup_media = True
            if not self.preferences_dialog_displayed:
                self.post_preference_change()
                
        # Downloads today and stored sequence numbers are kept in shared memory,
        # so that the subfolderfile daemon process can access and modify them
        
        # Note, totally ignore any changes in downloads today, as it
        # is modified in a special manner via a tracking class
                
        elif key == 'stored_sequence_no':
            if type(value) <> types.IntType:
                logger.critical("Stored sequence number value is malformed")
            else:
                self.stored_sequence_value.value = value
                
        elif key in ['image_rename', 'subfolder', 'video_rename', 'video_subfolder']:
            # Check if stored sequence no is being used
            self._check_for_sequence_value_use()
            
        #~ elif key == 'job_codes':
            #~ # update job code list in left pane
            #~ self.selection_vbox.update_job_code_combo()
            
        elif key in ['download_folder', 'video_download_folder']:
            self.display_free_space()
    
    def post_preference_change(self):
        if self.rerun_setup_available_image_and_video_media:

            logger.info("Download device settings preferences were changed.")
            
            self.thumbnails.clear_all()
            self.setup_devices(on_startup = False, on_preference_change = True, block_auto_start = True)
            self._set_device_collection_size()
            
            if self.main_notebook.get_current_page() == 1: # preview of file
                self.main_notebook.set_current_page(0)
                
            self.rerun_setup_available_image_and_video_media = False
            
        if self.rerun_setup_available_backup_media:
            if self.using_volume_monitor():
                self.start_volume_monitor()          
            logger.info("Backup preferences were changed.")
            
            logger.info("self.refreshBackupMedia()")
            
            self.rerun_setup_available_backup_media = False
            
        if self.refresh_downloads_today:
            self.downloads_today_value.value = self.downloads_today_tracker.get_raw_downloads_today()
            self.downloads_today_date_value.value = self.downloads_today_tracker.get_raw_downloads_today_date()
            self.day_start_value.value = self.downloads_today_tracker.get_raw_day_start()
            self.refresh_downloads_today_value.value = True
            self.prefs.set_downloads_today_from_tracker(self.downloads_today_tracker)
            

    
    # # #
    # Main app window management and setup
    # # #
    
    def _init_pynotify(self):
        """
        Initialize system notification messages
        """
        
        if not pynotify.init("TestCaps"):
            logger.critical("Problem using pynotify.")
            gtk.main_quit()

        do_not_size_icon = False
        self.notification_icon_size = 48 
        try:
            info = pynotify.get_server_info()
        except:
            logger.warning("Desktop environment notification server is incorrectly configured.")
        else:
            try:
                if info["name"] == 'notify-osd':
                    do_not_size_icon = True
            except:
                pass
        
        if do_not_size_icon:
            self.application_icon = gtk.gdk.pixbuf_new_from_file(
                        paths.share_dir('glade3/rapid-photo-downloader.svg'))
        else:
            self.application_icon = gtk.gdk.pixbuf_new_from_file_at_size(
                    paths.share_dir('glade3/rapid-photo-downloader.svg'),
                    self.notification_icon_size, self.notification_icon_size)

    def _init_widgets(self):
        """
        Initialize widgets in the main window, and variables that point to them
        """
        builder = gtk.Builder()
        self.builder = builder
        builder.add_from_file(paths.share_dir("glade3/rapid.ui"))
        self.rapidapp = builder.get_object("rapidapp")
        self.main_vpaned = builder.get_object("main_vpaned")
        self.main_notebook = builder.get_object("main_notebook")
        self.download_action = builder.get_object("download_action")
        
        self.download_progressbar = builder.get_object("download_progressbar")
        self.rapid_statusbar = builder.get_object("rapid_statusbar")
        self.statusbar_context_id = self.rapid_statusbar.get_context_id("progress")
        self.device_collection_scrolledwindow = builder.get_object("device_collection_scrolledwindow")
        self.next_image_action = builder.get_object("next_image_action")
        self.prev_image_action = builder.get_object("prev_image_action")
        self.menu_log_window = builder.get_object("menu_log_window")
        self.speed_label = builder.get_object("speed_label")
        
        # Only enable this action when actually displaying a preview
        self.next_image_action.set_sensitive(False)
        self.prev_image_action.set_sensitive(False)        
        
        # About dialog
        builder.add_from_file(paths.share_dir("glade3/about.ui"))
        self.about = builder.get_object("about")
        
        builder.connect_signals(self)
        
        self.preview_image = PreviewImage(self, builder)

        thumbnails_scrolledwindow = builder.get_object('thumbnails_scrolledwindow')
        self.thumbnails = ThumbnailDisplay(self)
        thumbnails_scrolledwindow.add(self.thumbnails)        
        
        #collection of devices from which to download
        self.device_collection_viewport = builder.get_object("device_collection_viewport")
        self.device_collection = DeviceCollection(self)
        self.device_collection_viewport.add(self.device_collection)
        
        #error log window
        self.error_log = errorlog.ErrorLog(self)
        
        # monitor to handle mounts and dismounts
        self.vmonitor = None
        # track scan ids for mount paths - very useful when a device is unmounted
        self.mounts_by_path = {}
        
        # Download action state
        self.download_action_is_download = True
        
        # Track the time a download commences
        self.download_start_time = None
        
        # Whether a system wide notifcation message should be shown
        # after a download has occurred in parallel
        self.display_summary_notification = False
        
        # Values used to display how much longer a download will take
        self.time_remaining = downloadtracker.TimeRemaining()
        self.time_check = downloadtracker.TimeCheck()
        

    def _set_window_size(self):
        """
        Remember the window size from the last time the program was run, or
        set a default size        
        """
        
        if self.prefs.main_window_maximized:
            self.rapidapp.maximize()
            self.rapidapp.set_default_size(config.DEFAULT_WINDOW_WIDTH, 
                                           config.DEFAULT_WINDOW_HEIGHT)
        elif self.prefs.main_window_size_x > 0:
            self.rapidapp.set_default_size(self.prefs.main_window_size_x, self.prefs.main_window_size_y)
        else:
            # set a default size
            self.rapidapp.set_default_size(config.DEFAULT_WINDOW_WIDTH, 
                                           config.DEFAULT_WINDOW_HEIGHT)
        

    def _set_device_collection_size(self):
        """
        Set the size of the device collection scrolled window widget
        """
        
        
        if self.device_collection.map_process_to_row:
            height = self.device_collection_viewport.size_request()[1]
            self.device_collection_scrolledwindow.set_size_request(-1,  height)
        else:
            # don't allow the media collection to be absolutely empty
            self.device_collection_scrolledwindow.set_size_request(-1, 47)
        
            
    def on_rapidapp_window_state_event(self, widget, event):
        """ Records the window maximization state in the preferences."""
        
        if event.changed_mask & gdk.WINDOW_STATE_MAXIMIZED:
            self.prefs.main_window_maximized = event.new_window_state & gdk.WINDOW_STATE_MAXIMIZED
        
    def _setup_buttons(self):
        thumbnails_button = self.builder.get_object("thumbnails_button")
        image = gtk.image_new_from_file(paths.share_dir('glade3/thumbnails_icon.png'))
        thumbnails_button.set_image(image)
        
        preview_button = self.builder.get_object("preview_button")
        image = gtk.image_new_from_file(paths.share_dir('glade3/photo_icon.png'))
        preview_button.set_image(image)
        
        next_image_button = self.builder.get_object("next_image_button")
        image = gtk.image_new_from_stock(gtk.STOCK_GO_FORWARD, gtk.ICON_SIZE_BUTTON)
        next_image_button.set_image(image)
        
        prev_image_button = self.builder.get_object("prev_image_button")
        image = gtk.image_new_from_stock(gtk.STOCK_GO_BACK, gtk.ICON_SIZE_BUTTON)
        prev_image_button.set_image(image)
    
    def _setup_icons(self):
        icons = ['rapid-photo-downloader-jobcode',]
        icon_list = [(icon, paths.share_dir('glade3/%s.svg' % icon)) for icon in icons]        
        register_iconsets(icon_list)
    
    def _setup_error_icons(self):
        """
        hide display of warning and error symbols in the taskbar until they
        are needed
        """
        self.error_image = self.builder.get_object("error_image")
        self.warning_image = self.builder.get_object("warning_image")
        self.warning_vseparator = self.builder.get_object("warning_vseparator")
        self.error_image.hide()
        self.warning_image.hide()
        self.warning_vseparator.hide()
        
    def statusbar_message(self, msg):
        self.rapid_statusbar.push(self.statusbar_context_id, msg)
        
    def statusbar_message_remove(self):
        self.rapid_statusbar.pop(self.statusbar_context_id)
        
    def display_free_space(self):
        """
        Displays the amount of space free on the filesystem the files will be 
        downloaded to.
        
        Also displays backup volumes / path being used. (NOT IMPLEMENTED YET)
        """
        photo_dir = self.is_valid_download_dir(path=self.prefs.download_folder, is_photo_dir=True, show_error_in_log=True)
        video_dir = self.is_valid_download_dir(path=self.prefs.video_download_folder, is_photo_dir=False, show_error_in_log=True)
        if photo_dir and video_dir:
            same_file_system = self.same_file_system(self.prefs.download_folder,
                                            self.prefs.video_download_folder)
        else:
            same_file_system = False
                
        dirs = []
        if photo_dir:
            dirs.append((self.prefs.download_folder, _("photos")))
        if video_dir and not same_file_system:
            dirs.append((self.prefs.video_download_folder, _("videos")))
        
        msg = ''
        if len(dirs) > 1:
            msg = ' ' + _('Free space:') + ' '
            
        for i in range(len(dirs)):
            dir_info = dirs[i]
            folder = gio.File(dir_info[0])
            file_info = folder.query_filesystem_info(gio.FILE_ATTRIBUTE_FILESYSTEM_FREE)
            size = file_info.get_attribute_uint64(gio.FILE_ATTRIBUTE_FILESYSTEM_FREE)
            free = format_size_for_user(bytes=size)
            if len(dirs) > 1:
                #(videos) or (photos) will be appended to the free space message displayed to the 
                #user in the status bar.
                #you should only translate this if your language does not use parantheses 
                file_type = _("(%(file_type)s)") % {'file_type': dir_info[1]}

                #Freespace available on the filesystem for downloading to
                #Displayed in status bar message on main window                
                msg += _("%(free)s %(file_type)s") % {'free': free, 'file_type': file_type}
                if i == 0:
                    #Inserted in the middle of the statusbar message concerning the amount of freespace
                    #Used to differentiate between two different file systems
                    #e.g. Free space: 21.3GB (photos); 14.7GB (videos).
                    msg += _("; ")
                else:
                    #Inserted at the end of the statusbar message concerning the amount of freespace
                    #Used to differentiate between two different file systems
                    #e.g. Free space: 21.3GB (photos); 14.7GB (videos).                    
                    msg += _(".")
                
            else:
                #Freespace available on the filesystem for downloading to
                #Displayed in status bar message on main window
                #e.g. 14.7GB available
                msg = " " + _("%(free)s free") % {'free': free}
        
            
        if self.prefs.backup_images and False: #FIXME: skip this for now!
            if not self.prefs.backup_device_autodetection:
                # user manually specified backup location
                msg2 = _('Backing up to %(path)s') % {'path':self.prefs.backup_location}
            else:
                msg2 = self.displayBackupVolumes() #FIXME
                
            if msg:
                msg = _("%(freespace)s. %(backuppaths)s.") % {'freespace': msg, 'backuppaths': msg2}
            else:
                msg = msg2
        
        msg = msg.rstrip()
            
        self.statusbar_message(msg)
        
    def log_error(self, severity, problem, details, extra_detail=None):
        """
        Display error and warning messages to user in log window
        """
        self.error_log.add_message(severity, problem, details, extra_detail)
        
    
    def on_error_eventbox_button_press_event(self, widget, event):
        self.prefs.show_log_dialog = True
        self.error_log.widget.show()     
        
        
    def on_menu_log_window_toggled(self, widget):
        active = widget.get_active()
        self.prefs.show_log_dialog = active
        if active:
            self.error_log.widget.show()
        else:
            self.error_log.widget.hide()
            
    def notify_prefs_are_invalid(self, details):
        title = _("Program preferences are invalid")
        logger.critical(title)
        self.log_error(severity=config.CRITICAL_ERROR, problem=title,
                       details=details)
    
    
    # # #
    # Utility functions
    # # #

    def files_of_type_present(self, files, file_type):
        """
        Returns true if there is at least one instance of the file_type
        in the list of files to be copied
        """
        for rpd_file in files:
            if rpd_file.file_type == file_type:
                return True
        return False
        
    def size_files_to_be_downloaded(self, files):
        """
        Returns the total size of the files to be downloaded in bytes
        """
        size = 0
        for i in range(len(files)):
            size += files[i].size

        return size
                                              
    def check_download_folder_validity(self, files_by_scan_pid):
        """
        Checks validity of download folders based on the file types the user
        is attempting to download.
        
        If valid, returns a tuple of True and an empty list.
        If invalid, returns a tuple of False and a list of the invalid directores.
        """
        valid = True
        invalid_dirs = []
        # first, check what needs to be downloaded - photos and / or videos
        need_photo_folder = False
        need_video_folder = False
        while not need_photo_folder and not need_video_folder:
            for scan_pid in files_by_scan_pid:
                files = files_by_scan_pid[scan_pid]
                if not need_photo_folder:
                    if self.files_of_type_present(files, rpdfile.FILE_TYPE_PHOTO):
                        need_photo_folder = True
                if not need_video_folder:
                    if self.files_of_type_present(files, rpdfile.FILE_TYPE_VIDEO):
                        need_video_folder = True
            
        # second, check validity
        if need_photo_folder:
            if not self.is_valid_download_dir(self.prefs.download_folder, 
                                                        is_photo_dir=True):
                valid = False
                invalid_dirs.append(self.prefs.download_folder)
                
        if need_video_folder:
            if not self.is_valid_download_dir(self.prefs.video_download_folder,
                                                        is_photo_dir=False):            
                valid = False
                invalid_dirs.append(self.prefs.video_download_folder)
                
        return (valid, invalid_dirs)

    def same_file_system(self, file1, file2):
        """Returns True if the files / diretories are on the same file system
        """
        f1 = gio.File(file1)
        f2 = gio.File(file2)
        f1_info = f1.query_info(gio.FILE_ATTRIBUTE_ID_FILESYSTEM)
        f1_id = f1_info.get_attribute_string(gio.FILE_ATTRIBUTE_ID_FILESYSTEM)
        f2_info = f2.query_info(gio.FILE_ATTRIBUTE_ID_FILESYSTEM)
        f2_id = f2_info.get_attribute_string(gio.FILE_ATTRIBUTE_ID_FILESYSTEM)
        return f1_id == f2_id
        
    
    def same_file(self, file1, file2):
        """Returns True if the files / directories are the same
        """
        f1 = gio.File(file1)
        f2 = gio.File(file2)
        
        file_attributes = "id::file"
        f1_info = f1.query_filesystem_info(file_attributes)
        f1_id = f1_info.get_attribute_string(gio.FILE_ATTRIBUTE_ID_FILE)
        f2_info = f2.query_filesystem_info(file_attributes)
        f2_id = f2_info.get_attribute_string(gio.FILE_ATTRIBUTE_ID_FILE)
        return f1_id == f2_id
        
    def is_valid_download_dir(self, path, is_photo_dir, show_error_in_log=False):
        """
        Checks the following conditions:
        Does the directory exist?
        Is it writable?
        
        if show_error_in_log is True, then display warning in log window, using
        is_photo_dir, which if true means the download directory is for photos,
        if false, for Videos
        """
        valid = False
        if is_photo_dir:
            download_folder_type = _("Photo")
        else:
            download_folder_type = _("Video")
            
        try:
            d = gio.File(path)
            if not d.query_exists(cancellable=None):
                logger.error("%s download folder does not exist: %s", 
                             download_folder_type, path)
                if show_error_in_log:
                    severity = config.WARNING
                    problem = _("%(file_type)s download folder does not exist") % {
                                'file_type': download_folder_type}
                    details = _("Folder: %s") % path
                    self.log_error(severity, problem, details)
            else:
                file_attributes = "standard::type,access::can-read,access::can-write"
                file_info = d.query_filesystem_info(file_attributes)
                file_type = file_info.get_file_type()
                
                if file_type != gio.FILE_TYPE_DIRECTORY and file_type != gio.FILE_TYPE_UNKNOWN:
                    logger.error("%s download folder is invalid: %s", 
                                 download_folder_type, path)
                    if show_error_in_log:
                        severity = config.WARNING
                        problem = _("%(file_type)s download folder is invalid") % {
                                    'file_type': download_folder_type}
                        details = _("Folder: %s") % path
                        self.log_error(severity, problem, details)                  
                else:
                    # is the directory writable?
                    try:
                        temp_dir = tempfile.mkdtemp(prefix="rpd-tmp", dir=path)
                        valid = True
                    except:
                        logger.error("%s is not writable", path)
                        if show_error_in_log:
                            severity = config.WARNING
                            problem = _("%(file_type)s download folder is not writable") % {
                                        'file_type': download_folder_type}
                            details = _("Folder: %s") % path
                            self.log_error(severity, problem, details)                          
                    else:
                        f = gio.File(temp_dir)
                        f.delete(cancellable=None)

        except gio.Error, inst:
            logger.error("Error checking download directory %s", path)
            logger.error(inst)
            
        return valid
                
    
    
    # # #
    #  Process results and management
    # # #
        
        
    def _start_process_managers(self):
        """
        Set up process managers.
        
        A task such as scanning a device or copying files is handled in its
        own process.        
        """
        
        self.batch_size = 10
        self.batch_size_MB = 2
        
        sequence_values = (self.downloads_today_value,
                           self.downloads_today_date_value,
                           self.day_start_value,
                           self.refresh_downloads_today_value,
                           self.stored_sequence_value, 
                           self.uses_stored_sequence_no_value,
                           self.uses_session_sequece_no_value,
                           self.uses_sequence_letter_value)
                           
        self.subfolder_file_manager = SubfolderFileManager(
                                        self.subfolder_file_results,
                                        sequence_values)
            
        
        self.generate_folder = False
        self.scan_manager = ScanManager(self.scan_results, self.batch_size, 
                    self.generate_folder, self.device_collection.add_device)
        self.copy_files_manager = CopyFilesManager(self.copy_files_results, 
                                                   self.batch_size_MB)        
        
    def scan_results(self, source, condition):
        """
        Receive results from scan processes
        """
        connection = self.scan_manager.get_pipe(source)
        
        conn_type, data = connection.recv()
        
        if conn_type == rpdmp.CONN_COMPLETE:
            connection.close()
            self.scan_manager.no_tasks -= 1
            size, file_type_counter, scan_pid = data
            size = format_size_for_user(bytes=size)
            results_summary, file_types_present = file_type_counter.summarize_file_count()
            self.download_tracker.set_file_types_present(scan_pid, file_types_present)
            logger.info('Found %s' % results_summary)
            logger.info('Files total %s' % size)
            self.device_collection.update_device(scan_pid, size)
            self.device_collection.update_progress(scan_pid, 0.0, results_summary, 0)
            self.testing_auto_exit_trip_counter += 1
            self.set_download_action_sensitivity()
                        
            if self.testing_auto_exit_trip_counter == self.testing_auto_exit_trip and self.testing_auto_exit:
                self.on_rapidapp_destroy(self.rapidapp)
            else:
                if not self.testing_auto_exit and not self.auto_start_is_on:
                    self.download_progressbar.set_text(_("Thumbnails"))
                    self.thumbnails.generate_thumbnails(scan_pid)
                elif self.auto_start_is_on:
                    if self.need_job_code_for_naming and not self.job_code:
                        self.get_job_code()
                    else:
                        self.start_download(scan_pid=scan_pid)

            self.set_thumbnail_sort()
            
            # signal that no more data is coming, finishing io watch for this pipe
            return False
        else:
            if len(data) > self.batch_size:
                logger.critical("incoming pipe length is unexpectedly long: %s" % len(data))
            else:
                for rpd_file in data:
                    self.thumbnails.add_file(rpd_file=rpd_file, 
                                        generate_thumbnail = not self.auto_start_is_on)
        
        # must return True for this method to be called again
        return True
        
        

    @dbus.service.method (config.DBUS_NAME,
                           in_signature='', out_signature='b')
    def is_running (self):
        return self.running
    
    @dbus.service.method (config.DBUS_NAME,
                            in_signature='', out_signature='')
    def start (self):
        if self.is_running():
            self.rapidapp.present()
        else:
            self.running = True
            gtk.main()
        
def start():

    is_beta = config.version.find('~') > 0
    
    parser = OptionParser(version= "%%prog %s" % utilities.human_readable_version(config.version))
    parser.set_defaults(verbose=is_beta,  extensions=False)
    # Translators: this text is displayed to the user when they request information on the command line options. 
    # The text %default should not be modified or left out.
    parser.add_option("-v",  "--verbose",  action="store_true", dest="verbose",  help=_("display program information on the command line as the program runs (default: %default)"))
    parser.add_option("-d", "--debug", action="store_true", dest="debug", help=_('display debugging information when run from the command line'))
    parser.add_option("-q", "--quiet",  action="store_false", dest="verbose",  help=_("only output errors to the command line"))
    # image file extensions are recognized RAW files plus TIFF and JPG
    parser.add_option("-e",  "--extensions", action="store_true", dest="extensions", help=_("list photo and video file extensions the program recognizes and exit"))
    parser.add_option("--reset-settings", action="store_true", dest="reset", help=_("reset all program settings and preferences and exit"))
    (options, args) = parser.parse_args()
    
    if options.debug:
        logging_level = logging.DEBUG
    elif options.verbose:
        logging_level = logging.INFO
    else:
        logging_level = logging.ERROR
    
    logger.setLevel(logging_level)

    if options.extensions:
        extensions = ((rpdfile.RAW_FILE_EXTENSIONS + rpdfile.NON_RAW_IMAGE_FILE_EXTENSIONS, _("Photos:")), (rpdfile.VIDEO_FILE_EXTENSIONS, _("Videos:")))
        for exts, file_type in extensions:
            v = ''
            for e in exts[:-1]:
                v += '%s, ' % e.upper()
            v = file_type + " " + v[:-1] + ' '+ (_('and %s') % exts[-1].upper())
            print v
            
        sys.exit(0)
        
    if options.reset:
        prefs = RapidPreferences()
        prefs.reset()
        print _("All settings and preferences have been reset")
        sys.exit(0)

    logger.info("Rapid Photo Downloader %s", utilities.human_readable_version(config.version))
    logger.info("Using pyexiv2 %s", metadataphoto.pyexiv2_version_info())
    logger.info("Using exiv2 %s", metadataphoto.exiv2_version_info())
    if DOWNLOAD_VIDEO:
        logger.info("Using hachoir %s", metadatavideo.version_info())
    else:
        logger.info(_("Video downloading functionality disabled.\nTo download videos, please install the hachoir metadata and kaa metadata packages for python."))

    bus = dbus.SessionBus ()
    request = bus.request_name (config.DBUS_NAME, dbus.bus.NAME_FLAG_DO_NOT_QUEUE)
    if request != dbus.bus.REQUEST_NAME_REPLY_EXISTS: 
        app = RapidApp(bus, '/', config.DBUS_NAME)
    else:
        # this application is already running
        print "Rapid Photo Downloader is already running"
        object = bus.get_object (config.DBUS_NAME, "/")
        app = dbus.Interface (object, config.DBUS_NAME)
    
    app.start()            

if __name__ == "__main__":
    start()
