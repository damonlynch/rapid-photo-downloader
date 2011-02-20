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


import dbus
import dbus.bus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
DBusGMainLoop(set_as_default=True)

try: 
    import pygtk 
    pygtk.require("2.0") 
except: 
    pass 

import gtk
import gtk.gdk as gdk

import getopt, sys, time, types, os, datetime

import gobject, pango, cairo, array, pangocairo

from multiprocessing import Process, Pipe, Queue, Event, current_process, log_to_stderr

import logging
logger = log_to_stderr()
logger.setLevel(logging.INFO)

import media, common, rpdfile
from media import getDefaultPhotoLocation, getDefaultVideoLocation, \
                  getDefaultBackupPhotoIdentifier, \
                  getDefaultBackupVideoIdentifier
                  
import renamesubfolderprefs as rn
import problemnotification as pn
import thumbnail as tn
import rpdmultiprocessing as rpdmp

import tableplusminus as tpm

import scan as scan_process

import config
__version__ = config.version

import prefs
import paths

from common import Configi18n
global _
_ = Configi18n._


from common import formatSizeForUser


DOWNLOAD_VIDEO = False

from config import  STATUS_CANNOT_DOWNLOAD, STATUS_DOWNLOADED, \
                    STATUS_DOWNLOADED_WITH_WARNING, \
                    STATUS_DOWNLOAD_FAILED, \
                    STATUS_DOWNLOAD_PENDING, \
                    STATUS_BACKUP_PROBLEM, \
                    STATUS_NOT_DOWNLOADED, \
                    STATUS_DOWNLOAD_AND_BACKUP_FAILED, \
                    STATUS_WARNING


def today():
    return datetime.date.today().strftime('%Y-%m-%d')

def cmd_line(msg):    
    if verbose:
        print msg
        

def date_time_human_readable(date, with_line_break=True):
    if with_line_break:
        return _("%(date)s\n%(time)s") % {'date':date.strftime("%x"), 'time':date.strftime("%X")}
    else:
        return _("%(date)s %(time)s") % {'date':date.strftime("%x"), 'time':date.strftime("%X")}
        
def time_subseconds_human_readable(date, subseconds):
    return _("%(hour)s:%(minute)s:%(second)s:%(subsecond)s") % \
            {'hour':date.strftime("%H"),
             'minute':date.strftime("%M"), 
             'second':date.strftime("%S"),
             'subsecond': subseconds}

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
        # device name, size of images on the device (human readable), 
        # copy progress (%), copy text
        self.liststore = gtk.ListStore(str, str, float, str)
        self.map_process_to_row = {}

        gtk.TreeView.__init__(self, self.liststore)
        
        self.props.enable_search = False
        # make it impossible to select a row
        selection = self.get_selection()
        selection.set_mode(gtk.SELECTION_NONE)
        
        # Device refers to a thing like a camera, memory card in its reader, external hard drive, Portable Storage Device, etc.
        column0 = gtk.TreeViewColumn(_("Device"), gtk.CellRendererText(), 
                                    text=0)
        self.append_column(column0)
        
        # Size refers to the total size of images on the device, typically in MB or GB
        column1 = gtk.TreeViewColumn(_("Size"), gtk.CellRendererText(), text=1)
        self.append_column(column1)
        
        column2 = gtk.TreeViewColumn(_("Download Progress"), 
                                    gtk.CellRendererProgress(), value=2, text=3)
        self.append_column(column2)
        self.show_all()
        
    def add_device(self, process_id, device_name, progress_bar_text = ''):
        
        # add the row, and get a temporary pointer to the row
        size_files = ''
        progress = 0.0
        iter = self.liststore.append((device_name, size_files, progress, progress_bar_text))
        
        self._set_process_map(process_id, iter)

        
    def update_device(self, process_id, total_size_files):
        """
        Updates the size of the photos and videos on the device, displayed to the user
        """
        if process_id in self.map_process_to_row:
            iter = self._get_process_map(process_id)
            self.liststore.set_value(iter, 1, total_size_files)
        else:
            logger.error("This device is unknown")
    
    def remove_device(self, process_id):
        if process_id in self.map_process_to_row:
            iter = self._get_process_map(process_id)
            self.liststore.remove(iter)
            del self.map_process_to_row[process_id]


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
    
    def update_progress(self, process_id, percent_complete, progress_bar_text, bytes_downloaded):
        
        iter = self._get_process_map(process_id)
        if iter:
            self.liststore.set_value(iter, 2, percent_complete)
            if progress_bar_text:
                self.liststore.set_value(iter, 3, progress_bar_text)
            if percent_complete or bytes_downloaded:
                logger.info("Implement update overall progress")


def create_cairo_image_surface(pil_image, image_width, image_height):
        imgd = pil_image.tostring("raw","BGRA")
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
    }
    def __init__(self, checkbutton_height):
        gtk.CellRenderer.__init__(self)
        self.image = None
        
        self.image_area_size = 100
        self.text_area_size = 30
        self.padding = 6
        self.checkbutton_height = checkbutton_height
        
    def do_set_property(self, pspec, value):
        setattr(self, pspec.name, value)

    def do_get_property(self, pspec):
        return getattr(self, pspec.name)
        
    def do_render(self, window, widget, background_area, cell_area, expose_area, flags):
        
        cairo_context = window.cairo_create()
        
        x = cell_area.x
        y = cell_area.y - self.checkbutton_height + 4
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
        # ouch - nasty hardcoding :(
        cairo_context.set_source_rgb(0.33, 0.33, 0.33)
        cairo_context.rectangle(x-6.5, y-9.5, w+14, h+31)
        cairo_context.stroke()
        
        #place the image
        cairo_context.set_source_surface(image, image_x, image_y)
        cairo_context.paint()
        
        #text
        context = pangocairo.CairoContext(cairo_context)
        
        text_y = y + self.image_area_size + 10
        context.rectangle(x, text_y, w, 15)
        context.clip()        
        
        layout = context.create_layout()

        width = w * pango.SCALE
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

        context.move_to(x, text_y)
        context.show_layout(layout)
        
        
    def do_get_size(self, widget, cell_area):
        return (0, 0, self.image_area_size, self.image_area_size + self.text_area_size - self.checkbutton_height + 4)
        

gobject.type_register(ThumbnailCellRenderer)
 

class ThumbnailDisplay(gtk.IconView):
    def __init__(self, parent_app):
        gtk.IconView.__init__(self)
        self.rapid_app = parent_app
        
        self.batch_size = 10
        
        self.thumbnail_manager = ThumbnailManager(self.thumbnail_results, self.batch_size)
        self.preview_manager = PreviewManager(self.preview_results)
        
        self.treerow_index = {}
        self.process_index = {}
        
        self.rpd_files = {}
        
        self.thumbnails = {}
        self.previews = {}
        
        self.stock_photo_thumbnails = tn.PhotoIcons()
        self.stock_video_thumbnails = tn.VideoIcons()
        
        self.SELECTED_COL = 1
        self.TIMESTAMP_COL = 4
        
        self.liststore = gtk.ListStore(
             gobject.TYPE_PYOBJECT, # 0 PIL thumbnail
             gobject.TYPE_BOOLEAN,  # 1 selected or not
             str,                   # 2 unique id
             str,                   # 3 file name
             int,                   # 4 timestamp for sorting, converted float
             )


        self.clear()
        self.set_model(self.liststore)
        
        checkbutton = gtk.CellRendererToggle()
        checkbutton.set_radio(False)
        checkbutton.props.activatable = True
        checkbutton.props.xalign = 0.0
        checkbutton.connect('toggled', self.on_checkbutton_toggled)
        self.pack_start(checkbutton, expand=False)
        self.add_attribute(checkbutton, "active", 1)
        
        checkbutton_size = checkbutton.get_size(self, None)
        checkbutton_height = checkbutton_size[3]
        checkbutton_width = checkbutton_size[2]
        
        image = ThumbnailCellRenderer(checkbutton_height)
        self.pack_start(image, expand=True)
        self.add_attribute(image, "image", 0)
        self.add_attribute(image, "filename", 3)

        
        #set the background color to a darkish grey
        self.modify_base(gtk.STATE_NORMAL, gtk.gdk.Color('#444444'))
        
        self.set_spacing(0)
        self.set_column_spacing(0)
        self.set_row_spacing(0)
        self.set_margin(0)
        
        #sort by timestamp
        self.liststore.set_sort_column_id(self.TIMESTAMP_COL, gtk.SORT_ASCENDING)
        
        self.show_all()
        
        self.connect('item-activated', self.on_item_activated)        
        
    def on_checkbutton_toggled(self, cellrenderertoggle, path):
        iter = self.liststore.get_iter(path)
        self.liststore.set_value(iter, self.SELECTED_COL, not cellrenderertoggle.get_active())
        
    def set_selected(self, unique_id, value):
        iter = self.get_iter_from_unique_id(unique_id)
        self.liststore.set_value(iter, self.SELECTED_COL, value)
    
    def add_file(self, rpd_file):

        thumbnail_icon = self.get_stock_icon(rpd_file.file_type)
        unique_id = rpd_file.unique_id
        scan_pid = rpd_file.scan_pid

        timestamp = int(rpd_file.modification_time)
        
        iter = self.liststore.append((thumbnail_icon,
                                      True,
                                      unique_id,
                                      rpd_file.display_name,
                                      timestamp
                                      ))
        
        path = self.liststore.get_path(iter)
        treerowref = gtk.TreeRowReference(self.liststore, path)
        
        if scan_pid in self.process_index:
            self.process_index[scan_pid].append(rpd_file)
        else:
            self.process_index[scan_pid] = [rpd_file,]
            
        self.treerow_index[unique_id] = treerowref
        self.rpd_files[unique_id] = rpd_file

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

    def show_preview(self, unique_id=None, iter=None):
        if unique_id is not None:
            iter = self.get_iter_from_unique_id(unique_id)
        else:
            assert(iter is not None)
            unique_id = self.get_unique_id_from_iter(iter)
            
        rpd_file = self.rpd_files[unique_id]    
        
        if unique_id in self.previews:
            preview_image = self.previews[unique_id]
        elif unique_id in self.thumbnails:
            preview_image = self.thumbnails[unique_id]
            # request daemon process to get a full size thumbnail
            self.preview_manager.get_preview(unique_id, rpd_file.full_file_name,
                                            rpd_file.file_type, size_max=None,)
        else:
            preview_image = self.get_stock_icon(rpd_file.file_type)
        
        checked = self.liststore.get_value(iter, self.SELECTED_COL)
        self.rapid_app.show_preview_image(unique_id, preview_image, checked)
            
    def show_next_image(self, unique_id):
        iter = self.get_iter_from_unique_id(unique_id)
        iter = self.liststore.iter_next(iter)
        if iter is None:
            iter = self.liststore.get_iter_first()

        if iter is not None:
            self.show_preview(iter=iter)
            
    def show_prev_image(self, unique_id):
        iter = self.get_iter_from_unique_id(unique_id)
        row = self.liststore.get_path(iter)[0]
        logger.debug("Looking for preview image of image %s", row)
        if row == 0:
            row = len(self.liststore)-1
        else:
            row -= 1
        iter = self.liststore.get_iter(row)

        if iter is not None:
            self.show_preview(iter=iter)
            
    def select_image(self, unique_id):
        iter = self.get_iter_from_unique_id(unique_id)
        path = self.liststore.get_path(iter)
        self.select_path(path)
        
    def get_stock_icon(self, file_type):
        if file_type == rpdfile.FILE_TYPE_PHOTO:
            return self.stock_photo_thumbnails.stock_thumbnail_image_icon
        else:
            return self.stock_video_thumbnails.stock_thumbnail_image_icon        
            
    def generate_thumbnails(self, scan_pid):
        """Initiate thumbnail generation for files scanned in one process
        """
        self.thumbnail_manager.add_task(self.process_index[scan_pid])
    
    def update_thumbnail(self, thumbnail_data):
        """
        Takes the generated thumbnail and 
        """
        unique_id = thumbnail_data[0]
        thumbnail_icon = thumbnail_data[1]
        
        if thumbnail_icon is not None:
            # get the thumbnail icon in pixbuf format
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
            for i in range(len(data)):
                thumbnail_data = data[i]
                self.update_thumbnail(thumbnail_data)                
        
        return True
        
    def preview_results(self, unique_id, preview_full_size, preview_small):
        """
        Receive a full size preview image and update
        """
        preview_image = preview_full_size.get_image()
        self.previews[unique_id] = preview_image
        self.rapid_app.update_preview_image(unique_id, preview_image)
                    
    
class RapidPreferences(prefs.Preferences):
    zoom = config.MIN_THUMBNAIL_SIZE * 2
        
    defaults = {
        "program_version": prefs.Value(prefs.STRING, ""),
        "download_folder": prefs.Value(prefs.STRING, 
                                        getDefaultPhotoLocation()),
        "video_download_folder": prefs.Value(prefs.STRING, 
                                        getDefaultVideoLocation()),
        "subfolder": prefs.ListValue(prefs.STRING_LIST, rn.DEFAULT_SUBFOLDER_PREFS),
        "video_subfolder": prefs.ListValue(prefs.STRING_LIST, rn.DEFAULT_VIDEO_SUBFOLDER_PREFS),
        "image_rename": prefs.ListValue(prefs.STRING_LIST, [rn.FILENAME, 
                                        rn.NAME_EXTENSION,
                                        rn.ORIGINAL_CASE]),
        "video_rename": prefs.ListValue(prefs.STRING_LIST, [rn.FILENAME, 
                                        rn.NAME_EXTENSION,
                                        rn.ORIGINAL_CASE]),
        "device_autodetection": prefs.Value(prefs.BOOL, True),
        "device_location": prefs.Value(prefs.STRING, os.path.expanduser('~')), 
        "device_autodetection_psd": prefs.Value(prefs.BOOL,  False),
        "device_whitelist": prefs.ListValue(prefs.STRING_LIST,  ['']), 
        "device_blacklist": prefs.ListValue(prefs.STRING_LIST,  ['']), 
        "backup_images": prefs.Value(prefs.BOOL, False),
        "backup_device_autodetection": prefs.Value(prefs.BOOL, True),
        "backup_identifier": prefs.Value(prefs.STRING, 
                                        getDefaultBackupPhotoIdentifier()),
        "video_backup_identifier": prefs.Value(prefs.STRING, 
                                        getDefaultBackupVideoIdentifier()),
        "backup_location": prefs.Value(prefs.STRING, os.path.expanduser('~')),
        "strip_characters": prefs.Value(prefs.BOOL, True),
        "auto_download_at_startup": prefs.Value(prefs.BOOL, False),
        "auto_download_upon_device_insertion": prefs.Value(prefs.BOOL, False),
        "auto_unmount": prefs.Value(prefs.BOOL, False),
        "auto_exit": prefs.Value(prefs.BOOL, False),
        "auto_exit_force": prefs.Value(prefs.BOOL, False),
        "auto_delete": prefs.Value(prefs.BOOL, False),
        "download_conflict_resolution": prefs.Value(prefs.STRING, 
                                        config.SKIP_DOWNLOAD),
        "backup_duplicate_overwrite": prefs.Value(prefs.BOOL, False),
        "display_selection": prefs.Value(prefs.BOOL, True),
        "display_size_column": prefs.Value(prefs.BOOL, True),
        "display_filename_column": prefs.Value(prefs.BOOL, False),
        "display_type_column": prefs.Value(prefs.BOOL, True),
        "display_path_column": prefs.Value(prefs.BOOL, False),
        "display_device_column": prefs.Value(prefs.BOOL, False),
        "display_preview_folders": prefs.Value(prefs.BOOL, True),
        "show_log_dialog": prefs.Value(prefs.BOOL, False),
        "day_start": prefs.Value(prefs.STRING,  "03:00"), 
        "downloads_today": prefs.ListValue(prefs.STRING_LIST, [today(), '0']), 
        "stored_sequence_no": prefs.Value(prefs.INT,  0), 
        "job_codes": prefs.ListValue(prefs.STRING_LIST,  [_('New York'),  
               _('Manila'),  _('Prague'),  _('Helsinki'),   _('Wellington'), 
               _('Tehran'), _('Kampala'),  _('Paris'), _('Berlin'),  _('Sydney'), 
               _('Budapest'), _('Rome'),  _('Moscow'),  _('Delhi'), _('Warsaw'), 
               _('Jakarta'),  _('Madrid'),  _('Stockholm')]),
        "synchronize_raw_jpg": prefs.Value(prefs.BOOL, False),
        "hpaned_pos": prefs.Value(prefs.INT, 0),
        "vpaned_pos": prefs.Value(prefs.INT, 0),
        "preview_vpaned_pos": prefs.Value(prefs.INT, 0),
        "main_window_size_x": prefs.Value(prefs.INT, 0),
        "main_window_size_y": prefs.Value(prefs.INT, 0),
        "main_window_maximized": prefs.Value(prefs.INT, 0),
        "show_warning_downloading_from_camera": prefs.Value(prefs.BOOL, True),
        "preview_zoom": prefs.Value(prefs.INT, zoom),
        "enable_previews": prefs.Value(prefs.BOOL, True),
        }

    def __init__(self):
        prefs.Preferences.__init__(self, config.GCONF_KEY, self.defaults)

    def getAndMaybeResetDownloadsToday(self):
        v = self.getDownloadsToday()
        if v <= 0:
            self.resetDownloadsToday()
        return v

    def getDownloadsToday(self):
        """Returns the preference value for the number of downloads performed today 
        
        If value is less than zero, that means the date has changed"""
        
        hour,  minute = self.getDayStart()
        adjustedToday = datetime.datetime.strptime("%s %s:%s" % (self.downloads_today[0], hour,  minute), "%Y-%m-%d %H:%M") 
        
        now = datetime.datetime.today()

        if  now < adjustedToday :
            try:
                return int(self.downloads_today[1])
            except ValueError:
                sys.stderr.write(_("Invalid Downloads Today value.\n"))
                sys.stderr.write(_("Resetting value to zero.\n"))
                self.setDownloadsToday(self.downloads_today[0] ,  0)
                return 0
        else:
            return -1
                
    def setDownloadsToday(self, date,  value=0):
            self.downloads_today = [date,  str(value)]
            
    def incrementDownloadsToday(self):
        """ returns true if day changed """
        v = self.getDownloadsToday()
        if v >= 0:
            self.setDownloadsToday(self.downloads_today[0] ,  v + 1)
            return False
        else:
            self.resetDownloadsToday(1)
            return True

    def resetDownloadsToday(self,  value=0):
        now = datetime.datetime.today()
        hour,  minute = self.getDayStart()
        t = datetime.time(hour,  minute)
        if now.time() < t:
            date = today()
        else:
            d = datetime.datetime.today() + datetime.timedelta(days=1)
            date = d.strftime(('%Y-%m-%d'))
            
        self.setDownloadsToday(date,  value)
        
    def setDayStart(self,  hour,  minute):
        self.day_start = "%s:%s" % (hour,  minute)

    def getDayStart(self):
        try:
            t1,  t2 = self.day_start.split(":")
            return (int(t1),  int(t2))
        except ValueError:
            sys.stderr.write(_("'Start of day' preference value is corrupted.\n"))
            sys.stderr.write(_("Resetting to midnight.\n"))
            self.day_start = "0:0"
            return 0, 0

    def getSampleJobCode(self):
        if self.job_codes:
            return self.job_codes[0]
        else:
            return ''
            
    def reset(self):
        """
        resets all preferences to default values
        """
        
        prefs.Preferences.reset(self)
        self.program_version = __version__
    
    
class TaskManager:
    def __init__(self, results_callback, batch_size):
        self.results_callback = results_callback
        self._processes = []
        self._pipes = {}
        self.batch_size = batch_size
       
    
    def add_task(self, task):
        self._setup_task(task)

        
    def _setup_task(self, task):
        task_results_conn, task_process_conn = Pipe(duplex=False)
        
        source = task_results_conn.fileno()
        self._pipes[source] = task_results_conn
        gobject.io_add_watch(source, gobject.IO_IN, self.results_callback)
        
        terminate_queue = Queue()
        run_event = Event()
        run_event.set()
        
        self._initiate_task(task, task_process_conn, terminate_queue, run_event)
        
    def _initiate_task(self, task, task_process_conn, terminate_queue, run_event):
        logger.error("Implement child class method!")
        
    
    def processes(self):
        for i in range(len(self._processes)):
            yield self._processes[i]        
    
    def start(self):
        for scan in self.processes():
            run_event = scan[2]
            if not run_event.is_set():
                run_event.set()
    
    def terminate(self):
        pause = False

        for scan in self.processes():
            if scan[0].is_alive():
                scan[1].put(None)
                pause = True
                run_event = scan[2]
                if not run_event.is_set():
                    run_event.set()
        if pause:
            time.sleep(1)
            
            
    def get_pipe(self, source):
        return self._pipes[source]


class ScanManager(TaskManager):
    
    def __init__(self, results_callback, batch_size, generate_folder,
                 add_device_function):
        TaskManager.__init__(self, results_callback, batch_size)
        self.add_device_function = add_device_function
        self.generate_folder = generate_folder
        
    def _initiate_task(self, path, task_process_conn, terminate_queue, run_event):
        scan = scan_process.Scan(path, self.batch_size, self.generate_folder, 
                                task_process_conn, terminate_queue, run_event)
        scan.start()
        self._processes.append((scan, terminate_queue, run_event))
        self.add_device_function(scan.pid, path, 
            # This refers to when a device like a hard drive is having its contents scanned,
            # looking for photos or videos. It is visible initially in the progress bar for each device 
            # (which normally holds "x photos and videos").
            # It maybe displayed only briefly if the contents of the device being scanned is small.
            progress_bar_text=_('scanning...'))
        
class ThumbnailManager(TaskManager):
    def add_task(self, task):
        TaskManager.add_task(self, task)
        
    def _initiate_task(self, files, task_process_conn, terminate_queue, run_event):
        generator = tn.GenerateThumbnails(files, self.batch_size, task_process_conn, terminate_queue, run_event)
        generator.start()
        self._processes.append((generator, terminate_queue, run_event))

class PreviewManager:
    def __init__(self, results_callback):
        self.run_event = Event()
        self.task_queue = Queue()
        self.results_callback = results_callback
        
        self.task_results_conn, self.task_process_conn = Pipe(duplex=False)
        
        source = self.task_results_conn.fileno()
        gobject.io_add_watch(source, gobject.IO_IN, self.preview_results)
        self._get_preview = tn.GetPreviewImage(self.task_process_conn, self.task_queue, self.run_event)
        self.queued_items = 0
        self._get_preview.start()
        
    def get_preview(self, unique_id, full_file_name, file_type, size_max):
        self.task_queue.put((unique_id, full_file_name, file_type, size_max))
        if not self.run_event.is_set():
            self.run_event.set()
        self.queued_items += 1
        
    def preview_results(self, source, condition):
        self.queued_items -= 1
        if self.queued_items == 0:
            self.run_event.clear()
        unique_id, preview_full_size, preview_small = self.task_results_conn.recv()
        self.results_callback(unique_id, preview_full_size, preview_small)
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
        
    def set_preview_image(self, unique_id, pil_image, checked=None):
        """
        """
        self.preview_image.set_image(pil_image)
        self.unique_id = unique_id
        if checked is not None:
            self.download_this_checkbutton.set_active(checked)
            self.download_this_checkbutton.grab_focus()
        
    def update_preview_image(self, unique_id, pil_image):
        if unique_id == self.unique_id:
            self.set_preview_image(unique_id, pil_image)
    
    def resize_preview_image(self, max_width=None, max_height=None, overwrite=False):
        
        if max_width is not None and max_height is not None:
            logger.info("Max width and height set to %s, %s" % (max_width, max_height))
            self.preview_image_size_limit = (max_width, max_height)
        else:
            max_width, max_height = self.preview_image_size_limit
        
        if self.base_preview_image:
        
            base_image_width = self.base_preview_image.size[0]
            base_image_height = self.base_preview_image.size[1]
            
            logger.info("Base image: %s, %s" %(base_image_width, base_image_height))

            image_aspect = float(base_image_width) / base_image_height
            frame_aspect = float(max_width) / max_height
    

            # Frame is wider than image
            if frame_aspect > image_aspect:
                height = max_height
                width = int(height * image_aspect)
            # Frame is taller than image
            else:
                width = max_width
                height = int(width / image_aspect)
                
            logger.info("Will resize base image to width and height %s, %s" % (width, height))
    
            if width != self.current_preview_size[0] or height!= self.current_preview_size[1] or overwrite:
                
                pil_image = self.base_preview_image.copy()
                if base_image_width < width or base_image_height < height:
                    pil_image = tn.upsize_pil(pil_image, (width, height))
                else:
                    logger.info("Downsizing image")
                    tn.downsize_pil(pil_image, (width, height))
                    logger.info("Preview image size %s, %s" % (pil_image.size[0], pil_image.size[1]))
                    
                pixbuf = image_to_pixbuf(pil_image)
                self.preview_image.set_from_pixbuf(pixbuf)
                self.current_preview_size = (width, height)    

        
class RapidApp(dbus.service.Object): 
    def __init__(self,  bus, path, name, taskserver=None): 
        
        dbus.service.Object.__init__ (self, bus, path, name)
        self.running = False
        
        self.taskserver = taskserver
        
        builder = gtk.Builder()
        builder.add_from_file(paths.share_dir("glade3/prototype.glade"))
        self.rapidapp = builder.get_object("rapidapp")
        self.main_vpaned = builder.get_object("main_vpaned")
        self.main_notebook = builder.get_object("main_notebook")
        
        builder.connect_signals(self)
        
        
        
        self.prefs = RapidPreferences()
        
        # remember the window size from the last time the program was run
        if self.prefs.main_window_maximized:
            self.rapidapp.maximize()
        elif self.prefs.main_window_size_x > 0:
            logger.info("Setting window size %sx%s", self.prefs.main_window_size_x, self.prefs.main_window_size_y)
            self.rapidapp.set_default_size(self.prefs.main_window_size_x, self.prefs.main_window_size_y)
        else:
            # set a default size
            logger.info("Setting default window size")
            self.rapidapp.set_default_size(800, 650)
            
        #collection of devices from which to download
        self.device_collection_viewport = builder.get_object("device_collection_viewport")
        self.device_collection = DeviceCollection(self)
        self.device_collection_viewport.add(self.device_collection)


        self.preview_image = PreviewImage(self, builder)

        thumbnails_scrolledwindow = builder.get_object('thumbnails_scrolledwindow')
        self.thumbnails = ThumbnailDisplay(self)
        thumbnails_scrolledwindow.add(self.thumbnails)
        
        self._setup_buttons(builder)
            
        self.rapidapp.show_all()
        
        #~ image_paths = ['/home/damon/rapid/cr2', '/home/damon/Pictures/processing/2010']
        #~ image_paths = ['/media/EOS_DIGITAL/']        
        #~ image_paths = ['/media/EOS_DIGITAL/', '/media/EOS_DIGITAL_/']
        #~ image_paths = ['/media/EOS_DIGITAL/', '/media/EOS_DIGITAL_/', '/media/EOS_DIGITAL__/']
        image_paths = ['/home/damon/rapid/cr2']
        #~ image_paths = ['/home/damon/Pictures/']

        
        self.batch_size = 10
        
        self.testing_auto_exit = False
        self.testing_auto_exit_trip = len(image_paths)
        self.testing_auto_exit_trip_counter = 0
        
        self.generate_folder = False
        self.scan_manager = ScanManager(self.scan_results, self.batch_size, 
                    self.generate_folder, self.device_collection.add_device)
        
        for path in image_paths:
            self.scan_manager.add_task(path)
        
        self.device_collection_scrolledwindow = builder.get_object("device_collection_scrolledwindow")
        
        if self.device_collection.map_process_to_row:
            height = self.device_collection_viewport.size_request()[1]
            self.device_collection_scrolledwindow.set_size_request(-1,  height)
        else:
            # don't allow the media collection to be absolutely empty
            self.device_collection_scrolledwindow.set_size_request(-1, 47)
            
    
    def on_rapidapp_destroy(self, widget, data=None):

        self.scan_manager.terminate()        
        self.thumbnails.thumbnail_manager.terminate()

        # save window and component sizes
        self.prefs.vpaned_pos = self.main_vpaned.get_position()

        x, y, width, height = self.rapidapp.get_allocation()
        logger.info("Saving window size %sx%s", width, height)
        self.prefs.main_window_size_x = width
        self.prefs.main_window_size_y = height
        
        gtk.main_quit()        
        
        


    def on_download_this_checkbutton_toggled(self, checkbutton):
        value = checkbutton.get_active()
        logger.debug("on_download_this_checkbutton_toggled %s", value)
        self.thumbnails.set_selected(self.preview_image.unique_id, value)
        
    # # #
    # Events related to displaying preview images and thumbnails
    # # #
    
    def on_preview_eventbox_button_press_event(self, widget, event):
        
        if event.type == gtk.gdk._2BUTTON_PRESS and event.button == 1:
            self.show_thumbnails()    
    
    def on_show_thumbnails_action_activate(self, action):
        logger.debug("on_show_thumbnails_action_activate")
        self.show_thumbnails()
     
    def show_preview_image(self, unique_id, image, checked):
        if self.main_notebook.get_current_page() == 0: # thumbnails
            logger.debug("Switching to preview image display")
            self.main_notebook.set_current_page(1)
        self.preview_image.set_preview_image(unique_id, image, checked)
        
    def update_preview_image(self, unique_id, image):
        self.preview_image.update_preview_image(unique_id, image)
        
    def show_thumbnails(self):
        logger.debug("Switching to thumbnails display")
        self.main_notebook.set_current_page(0)
        self.thumbnails.select_image(self.preview_image.unique_id)
        
    def on_next_image_action_activate(self, action):
        self.thumbnails.show_next_image(self.preview_image.unique_id)
    
    def on_prev_image_action_activate(self, action):
        self.thumbnails.show_prev_image(self.preview_image.unique_id)

    # # #
    # Main app window management and setup
    # # #
    
    def on_rapidapp_window_state_event(self, widget, event):
        """ Records the window maximization state in the preferences."""
        
        if event.changed_mask & gdk.WINDOW_STATE_MAXIMIZED:
            self.prefs.main_window_maximized = event.new_window_state & gdk.WINDOW_STATE_MAXIMIZED
        
    def _setup_buttons(self, builder):
        thumbnails_button = builder.get_object("thumbnails_button")
        image = gtk.image_new_from_file(paths.share_dir('glade3/thumbnails_icon.png'))
        thumbnails_button.set_image(image)
        
        preview_button = builder.get_object("preview_button")
        image = gtk.image_new_from_file(paths.share_dir('glade3/photo_icon.png'))
        preview_button.set_image(image)
        
        next_image_button = builder.get_object("next_image_button")
        image = gtk.image_new_from_stock(gtk.STOCK_GO_FORWARD, gtk.ICON_SIZE_BUTTON)
        next_image_button.set_image(image)
        
        prev_image_button = builder.get_object("prev_image_button")
        image = gtk.image_new_from_stock(gtk.STOCK_GO_BACK, gtk.ICON_SIZE_BUTTON)
        prev_image_button.set_image(image)        
        
    def scan_results(self, source, condition):
        connection = self.scan_manager.get_pipe(source)
        
        conn_type, data = connection.recv()
        
        if conn_type == rpdmp.CONN_COMPLETE:
            connection.close()
            size, file_type_counter, scan_pid = data
            size = formatSizeForUser(size)
            results_summary = file_type_counter.summarize_file_count()
            logger.info('Found %s' % results_summary)
            logger.info('Files total %s' % size)
            self.device_collection.update_device(scan_pid, size)
            self.device_collection.update_progress(scan_pid, 0.0, results_summary, 0)
            self.testing_auto_exit_trip_counter += 1
            if self.testing_auto_exit_trip_counter == self.testing_auto_exit_trip and self.testing_auto_exit:
                self.on_rapidapp_destroy(self.rapidapp)
            else:
                if not self.testing_auto_exit:
                    self.thumbnails.generate_thumbnails(scan_pid)
            # signal that no more data is coming, finishing io watch for this pipe
            return False
        else:
            if len(data) > self.batch_size:
                logger.error("incoming pipe length is %s" % len(data))
            else:
                for i in range(len(data)):
                    rpd_file = data[i]
                    #~ logger.info('<-- %s from %s' % (rpd_file.full_file_name, source))
                    self.thumbnails.add_file(rpd_file)
        
        # must return True for this method to be called again
        return True
        
        


    def needJobCodeForRenaming(self):
        return rn.usesJobCode(self.prefs.image_rename) or rn.usesJobCode(self.prefs.subfolder) or rn.usesJobCode(self.prefs.video_rename) or rn.usesJobCode(self.prefs.video_subfolder)

    @dbus.service.method (config.DBUS_NAME,
                           in_signature='', out_signature='b')
    def is_running (self):
        return self.running
    
    @dbus.service.method (config.DBUS_NAME,
                            in_signature='', out_signature='')
    def start (self):
        if self.is_running():
            self.window.present()
        else:
            self.running = True
            gtk.main()
        
def start():

    global debug_info
    global verbose
    
    debug_info = verbose = True

    bus = dbus.SessionBus ()
    request = bus.request_name (config.DBUS_NAME, dbus.bus.NAME_FLAG_DO_NOT_QUEUE)
    if request != dbus.bus.REQUEST_NAME_REPLY_EXISTS or True: # FIXME CHANGE THIS
        app = RapidApp(bus, '/', config.DBUS_NAME)
    else:
        # this application is already running
        print "program is already running"
        object = bus.get_object (config.DBUS_NAME, "/")
        app = dbus.Interface (object, config.DBUS_NAME)
    
    app.start()            

if __name__ == "__main__":
    start()
