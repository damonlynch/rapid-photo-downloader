#!/usr/bin/python

import config

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

import gobject, pango
 
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

try:
    from dropshadow import image_to_pixbuf, pixbuf_to_image, DropShadow
    DROP_SHADOW = True
except:
    DROP_SHADOW = False

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

TINY_SCREEN = gtk.gdk.screen_height() <= config.TINY_SCREEN_HEIGHT

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



class SelectionVBox(gtk.VBox):
    """
    Dialog from which the user can select photos and videos to download
    """

    
    def __init__(self, parentApp):
        """
        Initialize values for log dialog, but do not display.
        """
        
        gtk.VBox.__init__(self)
        self.parentApp = parentApp
        
        tiny_screen = TINY_SCREEN
        if tiny_screen:
            config.max_thumbnail_size = 160
        
        selection_scrolledwindow = gtk.ScrolledWindow()
        selection_scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        selection_viewport = gtk.Viewport()
        
        
        self.selection_treeview = SelectionTreeView(self)
        
        selection_scrolledwindow.add(self.selection_treeview)


        # Job code controls
        self.add_job_code_combo()
        left_pane_vbox = gtk.VBox(spacing = 12)
        left_pane_vbox.pack_start(selection_scrolledwindow, True, True)
        left_pane_vbox.pack_start(self.job_code_hbox, False, True)
                
        # Window sizes
        #selection_scrolledwindow.set_size_request(350, -1)
        
        
        # Preview pane
        
        # Zoom in and out slider (make the image bigger / smaller)
        
        # Zoom out (on the left of the slider)
        self.zoom_out_eventbox = gtk.EventBox()
        self.zoom_out_eventbox.set_events(gtk.gdk.BUTTON_PRESS_MASK)        
        self.zoom_out_image = gtk.Image()
        self.zoom_out_image.set_from_file(paths.share_dir('glade3/zoom-out.png'))
        self.zoom_out_eventbox.add(self.zoom_out_image)
        self.zoom_out_eventbox.connect("button_press_event", self.zoom_out_0_callback)
        
        # Zoom in (on the right of the slider)
        self.zoom_in_eventbox = gtk.EventBox()
        self.zoom_in_eventbox.set_events(gtk.gdk.BUTTON_PRESS_MASK)
        self.zoom_in_image = gtk.Image()
        self.zoom_in_image.set_from_file(paths.share_dir('glade3/zoom-in.png'))
        self.zoom_in_eventbox.add(self.zoom_in_image)
        self.zoom_in_eventbox.connect("button_press_event", self.zoom_in_100_callback)
        
        self.slider_adjustment = gtk.Adjustment(value=self.parentApp.prefs.preview_zoom, 
                lower=config.MIN_THUMBNAIL_SIZE, upper=config.max_thumbnail_size, 
                step_incr=1.0, page_incr=config.THUMBNAIL_INCREMENT, page_size=0)
        self.slider_adjustment.connect("value_changed", self.resize_image_callback)
        self.slider_hscale = gtk.HScale(self.slider_adjustment)
        self.slider_hscale.set_draw_value(False) # don't display numeric value
        self.slider_hscale.set_size_request(config.MIN_THUMBNAIL_SIZE * 2, -1)
        
        
        #Preview image
        self.base_preview_image = None # large size image used to scale down from
        self.preview_image = gtk.Image()

        self.preview_image.set_alignment(0, 0.5)
        #leave room for thumbnail shadow
        if DROP_SHADOW:
            self.cacheDropShadow()
        else:
            self.shadow_size = 0
        
        image_size, shadow_size, offset = self._imageAndShadowSize()
        
        self.preview_image.set_size_request(image_size, image_size)
        
        #labels to display file information
        
        #Original filename
        self.preview_original_name_label = gtk.Label()
        self.preview_original_name_label.set_alignment(0, 0.5)
        self.preview_original_name_label.set_ellipsize(pango.ELLIPSIZE_END)
        
        
        #Device (where it will be downloaded from)
        self.preview_device_expander = gtk.Expander()
        self.preview_device_label = gtk.Label()
        self.preview_device_label.set_alignment(0, 0.5)
        self.preview_device_image = gtk.Image()
        
        self.preview_device_path_label = gtk.Label()
        self.preview_device_path_label.set_alignment(0, 0.5)
        self.preview_device_path_label.set_ellipsize(pango.ELLIPSIZE_MIDDLE)
        self.preview_device_path_label.set_padding(30, 0)
        self.preview_device_expander.add(self.preview_device_path_label)
        
        device_hbox = gtk.HBox(False, spacing = 6)
        device_hbox.pack_start(self.preview_device_image)
        device_hbox.pack_start(self.preview_device_label, True, True)
        
        self.preview_device_expander.set_label_widget(device_hbox)
        
        #Filename that has been generated
        self.preview_name_label = gtk.Label()
        self.preview_name_label.set_alignment(0, 0.5)
        self.preview_name_label.set_ellipsize(pango.ELLIPSIZE_END)
        
        #Download destination
        self.preview_destination_expander = gtk.Expander()
        self.preview_destination_label = gtk.Label()
        self.preview_destination_label.set_alignment(0, 0.5)
        self.preview_destination_image = gtk.Image()
        
        self.preview_destination_path_label = gtk.Label()
        self.preview_destination_path_label.set_alignment(0, 0.5)
        self.preview_destination_path_label.set_ellipsize(pango.ELLIPSIZE_MIDDLE)        
        self.preview_destination_path_label.set_padding(30, 0)
        self.preview_destination_expander.add(self.preview_destination_path_label)

        destination_hbox = gtk.HBox(False, spacing = 6)
        destination_hbox.pack_start(self.preview_destination_image)
        destination_hbox.pack_start(self.preview_destination_label, True, True)
        
        self.preview_destination_expander.set_label_widget(destination_hbox)

        
        #Status of the file
        
        self.preview_status_icon = gtk.Image()
        self.preview_status_icon.set_size_request(16,16)

        self.preview_status_label = gtk.Label()
        self.preview_status_label.set_alignment(0, 0.5)
        self.preview_status_label.set_ellipsize(pango.ELLIPSIZE_END)
        self.preview_status_label.set_padding(12, 0)

        #Title of problems encountered in generating the name / subfolder
        self.preview_problem_title_label = gtk.Label()
        self.preview_problem_title_label.set_alignment(0, 0.5)
        self.preview_problem_title_label.set_ellipsize(pango.ELLIPSIZE_END)
        self.preview_problem_title_label.set_padding(12, 0)
        
        #Details of what the problem(s) are
        self.preview_problem_label = gtk.Label()
        self.preview_problem_label.set_alignment(0, 0)
        self.preview_problem_label.set_line_wrap(True)
        self.preview_problem_label.set_padding(12, 0)
        #Can't combine wrapping and ellipsize, sadly
        #self.preview_problem_label.set_ellipsize(pango.ELLIPSIZE_END)
                
        #Put content into table
        # Use a table so we can do the Gnome HIG layout more easily
        self.preview_table = gtk.Table(10, 4)
        self.preview_table.set_row_spacings(12)
        left_spacer = gtk.Label('')
        left_spacer.set_padding(12, 0)
        right_spacer = gtk.Label('')
        right_spacer.set_padding(6, 0)
        

        spacer2 = gtk.Label('')
        
        #left and right spacers
        self.preview_table.attach(left_spacer, 0, 1, 1, 2, xoptions=gtk.SHRINK, yoptions=gtk.SHRINK)
        self.preview_table.attach(right_spacer, 3, 4, 1, 2, xoptions=gtk.SHRINK, yoptions=gtk.SHRINK)
        
        row = 0
        zoom_hbox = gtk.HBox()
        zoom_hbox.pack_start(self.zoom_out_eventbox, False, False)
        zoom_hbox.pack_start(self.slider_hscale, False, False)
        zoom_hbox.pack_start(self.zoom_in_eventbox, False, False)
        
        self.preview_table.attach(zoom_hbox, 1, 3, row, row+1, yoptions=gtk.SHRINK)
        
        row += 1
        self.preview_table.attach(self.preview_image, 1, 3, row, row+1, yoptions=gtk.SHRINK)
        row += 1
        
        self.preview_table.attach(self.preview_original_name_label, 1, 3, row, row+1, xoptions=gtk.EXPAND|gtk.FILL, yoptions=gtk.SHRINK)
        row += 1
        if not tiny_screen:
            self.preview_table.attach(self.preview_device_expander, 1, 3, row, row+1, xoptions=gtk.EXPAND|gtk.FILL, yoptions=gtk.SHRINK)
            row += 1
        
        self.preview_table.attach(self.preview_name_label, 1, 3, row, row+1, xoptions=gtk.EXPAND|gtk.FILL, yoptions=gtk.SHRINK)
        row += 1
        if not tiny_screen:
            self.preview_table.attach(self.preview_destination_expander, 1, 3, row, row+1, xoptions=gtk.EXPAND|gtk.FILL, yoptions=gtk.SHRINK)
            row += 1

        if not tiny_screen:
            self.preview_table.attach(spacer2, 0, 7, row, row+1, yoptions=gtk.SHRINK)
            row += 1
        
        self.preview_table.attach(self.preview_status_icon, 1, 2, row, row+1, xoptions=gtk.SHRINK, yoptions=gtk.SHRINK)
        self.preview_table.attach(self.preview_status_label, 2, 3, row, row+1, yoptions=gtk.SHRINK)
        row += 1
        
        self.preview_table.attach(self.preview_problem_title_label, 2, 3, row, row+1, yoptions=gtk.SHRINK)
        row += 1
        self.preview_table.attach(self.preview_problem_label, 2, 4, row, row+1, xoptions=gtk.EXPAND|gtk.FILL, yoptions=gtk.EXPAND|gtk.FILL)
        row += 1
        
        self.file_hpaned = gtk.HPaned()
        self.file_hpaned.pack1(left_pane_vbox, shrink=False)
        self.file_hpaned.pack2(self.preview_table, resize=True, shrink=False)
        self.pack_start(self.file_hpaned, True, True)
        if self.parentApp.prefs.hpaned_pos > 0:
            self.file_hpaned.set_position(self.parentApp.prefs.hpaned_pos)
        else:
            # this is what the user will see the first time they run the app
            self.file_hpaned.set_position(300)

        self.show_all()
    
    
    def set_base_preview_image(self, pixbuf):
        """
        sets the unscaled pixbuf image to be displayed to the user
        the actual image the user will see will depend on the scale
        they've set to view it at
        """
        self.base_preview_image = pixbuf
        
    def zoom_in(self):
        self.slider_adjustment.set_value(min([config.max_thumbnail_size, int(self.slider_adjustment.get_value()) + config.THUMBNAIL_INCREMENT]))
        
    def zoom_out(self):
        self.slider_adjustment.set_value(max([config.MIN_THUMBNAIL_SIZE, int(self.slider_adjustment.get_value()) - config.THUMBNAIL_INCREMENT]))
    
    def zoom_in_100_callback(self, widget, value):
        self.slider_adjustment.set_value(config.max_thumbnail_size)
        
    def zoom_out_0_callback(self, widget, value):
        self.slider_adjustment.set_value(config.MIN_THUMBNAIL_SIZE)
    
    def set_display_preview_folders(self, value):
        if value and self.selection_treeview.previewed_file_treerowref:
            self.preview_destination_expander.show()
            self.preview_device_expander.show()

        else:
            self.preview_destination_expander.hide()
            self.preview_device_expander.hide()
            
    def cacheDropShadow(self):
        i, self.shadow_size, offset_v = self._imageAndShadowSize()
        self.drop_shadow = DropShadow(offset=(offset_v,offset_v), shadow = (0x44, 0x44, 0x44, 0xff), border=self.shadow_size, trim_border = True)
        
    def _imageAndShadowSize(self):
        image_size = int(self.slider_adjustment.get_value())
        offset_v = max([image_size / 25, 5]) # realistically size the shadow based on the size of the image
        shadow_size = offset_v + 3
        image_size = image_size + offset_v * 2 + 3
        return (image_size, shadow_size, offset_v)
    
    def resize_image_callback(self, adjustment):
        """
        Resize the preview image after the adjustment value has been
        changed
        """
        size = int(adjustment.value)
        self.parentApp.prefs.preview_zoom = size
        self.cacheDropShadow()
        
        pixbuf = self.scaledPreviewImage()
        if pixbuf:
            self.preview_image.set_from_pixbuf(pixbuf)
            size = max([pixbuf.get_width(), pixbuf.get_height()])
            self.preview_image.set_size_request(size, size)
        else:    
            self.preview_image.set_size_request(size + self.shadow_size, size + self.shadow_size)
        
    def scaledPreviewImage(self):
        """
        Generate a scaled version of the preview image
        """
        size = int(self.slider_adjustment.get_value())
        if not self.base_preview_image:
            return None
        else:
            pixbuf = common.scale2pixbuf(size, size, self.base_preview_image)
            
            if DROP_SHADOW: 
                pil_image = pixbuf_to_image(pixbuf)
                pil_image = self.drop_shadow.dropShadow(pil_image) 
                pixbuf = image_to_pixbuf(pil_image)
            
            return pixbuf
    
    def set_job_code_display(self):
        """
        Shows or hides the job code entry
        
        If user is not using job codes in their file or subfolder names
        then do not prompt for it
        """

        if self.parentApp.needJobCodeForRenaming():
            self.job_code_hbox.show()
            self.job_code_label.show()
            self.job_code_combo.show()
            self.selection_treeview.job_code_column.set_visible(True)
        else:
            self.job_code_hbox.hide()
            self.job_code_label.hide()
            self.job_code_combo.hide()
            self.selection_treeview.job_code_column.set_visible(False)
    
    def update_job_code_combo(self):
        # delete existing rows
        while len(self.job_code_combo.get_model()) > 0:
            self.job_code_combo.remove_text(0)
        # add new ones
        for text in self.parentApp.prefs.job_codes:
            self.job_code_combo.append_text(text)
        # clear existing entry displayed in entry box
        self.job_code_entry.set_text('')
        
    
    def add_job_code_combo(self):
        self.job_code_hbox = gtk.HBox(spacing = 12)
        self.job_code_hbox.set_no_show_all(True)
        self.job_code_label = gtk.Label(_("Job Code:"))
        
        self.job_code_combo = gtk.combo_box_entry_new_text()
        for text in self.parentApp.prefs.job_codes:
            self.job_code_combo.append_text(text)
        
        # make entry box have entry completion
        self.job_code_entry = self.job_code_combo.child
        
        self.completion = gtk.EntryCompletion()
        self.completion.set_match_func(self.job_code_match_func)
        self.completion.connect("match-selected",
                             self.on_job_code_combo_completion_match)
        self.completion.set_model(self.job_code_combo.get_model())
        self.completion.set_text_column(0)
        self.job_code_entry.set_completion(self.completion)
        
        
        self.job_code_combo.connect('changed', self.on_job_code_resp)
        
        self.job_code_entry.connect('activate', self.on_job_code_entry_resp)
        
        self.job_code_combo.set_tooltip_text(_("Enter a new Job Code and press Enter, or select an existing Job Code"))

        #add widgets
        self.job_code_hbox.pack_start(self.job_code_label, False, False)
        self.job_code_hbox.pack_start(self.job_code_combo, True, True)
        self.set_job_code_display()

    def job_code_match_func(self, completion, key, iter):
         model = completion.get_model()
         return model[iter][0].lower().startswith(self.job_code_entry.get_text().lower())
         
    def on_job_code_combo_completion_match(self, completion, model, iter):
         self.job_code_entry.set_text(model[iter][0])
         self.job_code_entry.set_position(-1)
         
    def on_job_code_resp(self, widget):
        """
        When the user has clicked on an existing job code
        """
        
        # ignore changes because the user is typing in a new value
        if widget.get_active() >= 0:
            self.job_code_chosen(widget.get_active_text())
            
    def on_job_code_entry_resp(self, widget):
        """
        When the user has hit enter after entering a new job code
        """
        self.job_code_chosen(widget.get_text())
        
    def job_code_chosen(self, job_code):
        """
        The user has selected a Job code, apply it to selected images. 
        """
        self.selection_treeview.apply_job_code(job_code, overwrite = True)
        self.completion.set_model(None)
        self.parentApp.assignJobCode(job_code)
        self.completion.set_model(self.job_code_combo.get_model())
            
    def add_file(self, rpd_file):
        self.selection_treeview.add_file(rpd_file)

    
class SelectionTreeView(gtk.TreeView):
    """
    TreeView display of photos and videos available for download
    
    Assumes a threaded environment.
    """
    def __init__(self, parentApp):

        self.parentApp = parentApp
        self.rapidApp = parentApp.parentApp
        
        self.batch_size = 10
        
        self.thumbnail_manager = ThumbnailManager(self.thumbnail_results, self.batch_size)
        self.treerow_index = {}
        self.process_index = {}
        
        self.thumbnails = {}
        
        self.stock_photo_thumbnails = tn.PhotoIcons()
        self.stock_video_thumbnails = tn.VideoIcons()
        
        self.liststore = gtk.ListStore(
             gtk.gdk.Pixbuf,        # 0 thumbnail icon
             str,                   # 1 name (for sorting)
             int,                   # 2 timestamp (for sorting), float converted into an int
             str,                   # 3 date (human readable)
             long,                  # 4 size (for sorting)
             str,                   # 5 size (human readable)
             int,                   # 6 isImage (for sorting)
             gtk.gdk.Pixbuf,        # 7 type (photo or video)
             str,                   # 8 job code
             gobject.TYPE_PYOBJECT, # 9 rpd_file (for data)
             gtk.gdk.Pixbuf,        # 10 status icon
             int,                   # 11 status (downloaded, cannot download, etc, for sorting)
             str,                   # 12 path (on the device)
             str)                   # 13 device (human readable)
                         
        self.selected_rows = set()

        # sort by date (unless there is a problem)
        self.liststore.set_sort_column_id(2, gtk.SORT_ASCENDING)
        
        gtk.TreeView.__init__(self, self.liststore)

        selection = self.get_selection()
        selection.set_mode(gtk.SELECTION_MULTIPLE)
        selection.connect('changed', self.on_selection_changed)
        
        self.set_rubber_banding(True)
        
        # Status Column
        # Indicates whether file was downloaded, or a warning or error of some kind
        cell = gtk.CellRendererPixbuf()
        cell.set_property("yalign", 0.5)
        status_column = gtk.TreeViewColumn(_("Status"), cell, pixbuf=10)
        status_column.set_sort_column_id(11)
        status_column.connect('clicked', self.header_clicked)
        self.append_column(status_column)
        
        # Type of file column i.e. photo or video (displays at user request)
        cell = gtk.CellRendererPixbuf()
        cell.set_property("yalign", 0.5)     
        self.type_column = gtk.TreeViewColumn(_("Type"), cell, pixbuf=7)
        self.type_column.set_sort_column_id(6)
        self.type_column.set_clickable(True)
        self.type_column.connect('clicked', self.header_clicked)
        self.append_column(self.type_column)
        
        self.display_type_column(self.rapidApp.prefs.display_type_column)
        
        #File thumbnail column
        if not DOWNLOAD_VIDEO:
            title = _("Photo")
        else:
            title = _("File")
        thumbnail_column = gtk.TreeViewColumn(title)
        cellpb = gtk.CellRendererPixbuf()
        if not DROP_SHADOW:
            cellpb.set_fixed_size(60,50)           
        thumbnail_column.pack_start(cellpb, False)
        thumbnail_column.set_attributes(cellpb, pixbuf=0)
        thumbnail_column.set_sort_column_id(1)
        thumbnail_column.set_clickable(True)        
        thumbnail_column.connect('clicked', self.header_clicked)
        self.append_column(thumbnail_column)

        # Job code column
        cell = gtk.CellRendererText()
        cell.set_property("yalign", 0)
        self.job_code_column = gtk.TreeViewColumn(_("Job Code"), cell, text=8)
        self.job_code_column.set_sort_column_id(8)
        self.job_code_column.set_resizable(True)
        self.job_code_column.set_clickable(True)        
        self.job_code_column.connect('clicked', self.header_clicked)
        self.append_column(self.job_code_column)

        # Date column
        cell = gtk.CellRendererText()
        cell.set_property("yalign", 0)
        date_column = gtk.TreeViewColumn(_("Date"), cell, text=3)
        date_column.set_sort_column_id(2)   
        date_column.set_resizable(True)
        date_column.set_clickable(True)
        date_column.connect('clicked', self.header_clicked)
        self.append_column(date_column)
        
        # Size column (displays at user request)
        cell = gtk.CellRendererText()
        cell.set_property("yalign", 0)
        self.size_column = gtk.TreeViewColumn(_("Size"), cell, text=5)
        self.size_column.set_sort_column_id(4)
        self.size_column.set_resizable(True)
        self.size_column.set_clickable(True)            
        self.size_column.connect('clicked', self.header_clicked)
        self.append_column(self.size_column)
        self.display_size_column(self.rapidApp.prefs.display_size_column)
        
        # Device column (displays at user request)
        cell = gtk.CellRendererText()
        cell.set_property("yalign", 0)
        self.device_column = gtk.TreeViewColumn(_("Device"), cell, text=13)
        self.device_column.set_sort_column_id(13)
        self.device_column.set_resizable(True)
        self.device_column.set_clickable(True)        
        self.device_column.connect('clicked', self.header_clicked)
        self.append_column(self.device_column)
        self.display_device_column(self.rapidApp.prefs.display_device_column)        
        
        # Filename column (displays at user request)
        cell = gtk.CellRendererText()
        cell.set_property("yalign", 0)
        self.filename_column = gtk.TreeViewColumn(_("Filename"), cell, text=1)
        self.filename_column.set_sort_column_id(1)   
        self.filename_column.set_resizable(True)
        self.filename_column.set_clickable(True)
        self.filename_column.connect('clicked', self.header_clicked)
        self.append_column(self.filename_column)
        self.display_filename_column(self.rapidApp.prefs.display_filename_column)
        
        # Path column (displays at user request)
        cell = gtk.CellRendererText()
        cell.set_property("yalign", 0)
        self.path_column = gtk.TreeViewColumn(_("Path"), cell, text=12)
        self.path_column.set_sort_column_id(12)   
        self.path_column.set_resizable(True)
        self.path_column.set_clickable(True)
        self.path_column.connect('clicked', self.header_clicked)
        self.append_column(self.path_column)
        self.display_path_column(self.rapidApp.prefs.display_path_column)        
                
        self.show_all()
        
        # flag used to determine if a preview should be generated or not
        # there is no point generating a preview for each photo when 
        # select all photos is called, for instance
        self.suspend_previews = False
        
        self.user_has_clicked_header = False
        
        # icons to be displayed in status column

        self.downloaded_icon = self.render_icon('rapid-photo-downloader-downloaded', gtk.ICON_SIZE_MENU) 
        self.download_failed_icon = self.render_icon(gtk.STOCK_DIALOG_ERROR, gtk.ICON_SIZE_MENU)
        self.error_icon = self.render_icon(gtk.STOCK_DIALOG_ERROR, gtk.ICON_SIZE_MENU)
        self.warning_icon = self.render_icon(gtk.STOCK_DIALOG_WARNING, gtk.ICON_SIZE_MENU)

        self.download_pending_icon = self.render_icon('rapid-photo-downloader-download-pending', gtk.ICON_SIZE_MENU) 
        self.downloaded_with_warning_icon = self.render_icon('rapid-photo-downloader-downloaded-with-warning', gtk.ICON_SIZE_MENU)
        self.downloaded_with_error_icon = self.render_icon('rapid-photo-downloader-downloaded-with-error', gtk.ICON_SIZE_MENU)
        
        # make the not yet downloaded icon a transparent square
        self.not_downloaded_icon = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False, 8, 16, 16)
        self.not_downloaded_icon.fill(0xffffffff)
        self.not_downloaded_icon = self.not_downloaded_icon.add_alpha(True, chr(255), chr(255), chr(255))
        # but make it be a tick in the preview pane
        self.not_downloaded_icon_tick = self.render_icon(gtk.STOCK_YES, gtk.ICON_SIZE_MENU)
        
        #preload generic icons
        self.icon_photo =  gtk.gdk.pixbuf_new_from_file(paths.share_dir('glade3/photo24.png'))
        self.icon_video =  gtk.gdk.pixbuf_new_from_file(paths.share_dir('glade3/video24.png'))
        #with shadows
        self.generic_photo_with_shadow = gtk.gdk.pixbuf_new_from_file(paths.share_dir('glade3/photo_small_shadow.png'))
        self.generic_video_with_shadow = gtk.gdk.pixbuf_new_from_file(paths.share_dir('glade3/video_small_shadow.png'))
        
        if DROP_SHADOW:
            self.iconDropShadow = DropShadow(offset=(3,3), shadow = (0x34, 0x34, 0x34, 0xff), border=6)
            
        self.previewed_file_treerowref = None
        self.icontheme = gtk.icon_theme_get_default()
        
    def thumbnail_results(self, source, condition):
        connection = self.thumbnail_manager.get_pipe(source)
        
        conn_type, data = connection.recv()
        
        if conn_type == rpdmp.CONN_COMPLETE:
            pass
        else:
            for i in range(len(data)):
                thumbnail_data = data[i]
                self.update_thumbnail(thumbnail_data)                
        
        return True          
        
    def get_thread(self, iter):
        """
        Returns the thread associated with the liststore's iter
        """
        return 1
        
    def get_status(self, iter):
        """
        Returns the status associated with the liststore's iter
        """
        return self.liststore.get_value(iter, 11)
        
    def get_rpd_file(self, iter):
        """
        Returns the rpd_file associated with the liststore's iter
        """
        return self.liststore.get_value(iter, 9)
        
    def get_is_image(self, iter):
        """
        Returns the file type (is image or video) associated with the liststore's iter
        """
        return self.liststore.get_value(iter, 6)
    
    def get_type_icon(self, iter):
        """
        Returns the file type's pixbuf associated with the liststore's iter
        """
        return self.liststore.get_value(iter, 7)
        
    def get_job_code(self, iter):
        """
        Returns the job code associated with the liststore's iter
        """
        return self.liststore.get_value(iter, 8)
        
    def get_status_icon(self, status, preview=False):
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
            if preview:
                status_icon = self.not_downloaded_icon_tick
            else:
                status_icon = self.not_downloaded_icon
        elif status in [STATUS_DOWNLOADED_WITH_WARNING, STATUS_BACKUP_PROBLEM]:
            status_icon = self.downloaded_with_warning_icon
        elif status in [STATUS_DOWNLOAD_FAILED, STATUS_DOWNLOAD_AND_BACKUP_FAILED]:
            status_icon = self.downloaded_with_error_icon
        elif status == STATUS_DOWNLOAD_PENDING:
            status_icon = self.download_pending_icon
        else:
            sys.stderr.write("FIXME: unknown status: %s\n" % status)
            status_icon = self.not_downloaded_icon
        return status_icon
        
    def get_tree_row_refs(self):
        """
        Returns a list of all tree row references
        """
        tree_row_refs = []
        iter = self.liststore.get_iter_first()
        while iter:
            tree_row_refs.append(self.get_rpd_file(iter).treerowref)
            iter = self.liststore.iter_next(iter)
        return tree_row_refs
        
    def get_selected_tree_row_refs(self):
        """
        Returns a list of tree row references for the selected rows
        """
        tree_row_refs = []
        selection = self.get_selection()
        model, pathlist = selection.get_selected_rows()
        for path in pathlist:
            iter = self.liststore.get_iter(path)
            tree_row_refs.append(self.get_rpd_file(iter).treerowref)
        return tree_row_refs            
            
    def get_tree_row_iters(self, selected_only=False):
        """
        Yields tree row iters
        
        If selected_only is True, then only those from the selected
        rows will be returned.
        
        This function is essential when modifying any content
        in the list store (because rows can easily be moved when their
        content changes)
        """
        if selected_only:
            tree_row_refs = self.get_selected_tree_row_refs()
        else:
            tree_row_refs = self.get_tree_row_refs()
        for reference in tree_row_refs:
            path = reference.get_path()
            yield self.liststore.get_iter(path)
    
    
    def get_stock_icon(self, file_type):
        if file_type == config.FILE_TYPE_PHOTO:
            return self.stock_photo_thumbnails.stock_thumbnail_image_icon
        else:
            return self.stock_video_thumbnails.stock_thumbnail_image_icon
            
    def get_stock_thumbnail(self, file_type):
        if file_type == config.FILE_TYPE_PHOTO:
            return self.stock_photo_thumbnails.stock_thumbnail_image
        else:
            return self.stock_video_thumbnails.stock_thumbnail_image
            
    def get_stock_type_icon(self, file_type):
        if file_type == config.FILE_TYPE_PHOTO:
            return self.stock_photo_thumbnails.type_icon
        else:
            return self.stock_video_thumbnails.type_icon        
    
    def add_file(self, rpd_file):
        if debug_info and False:
            cmd_line('Adding file %s' % rpd_file.full_file_name)
            
        # metadata is loaded when previews are generated before downloading
        #~ if rpd_file.metadata:
            #~ date = rpd_file.date_time()
            #~ timestamp = rpd_file.metadata.timeStamp(missing=None)
            #~ if timestamp is None:
                #~ timestamp = rpd_file.modification_time
        # if metadata has not been loaded, substitute other values
        #~ else:
        timestamp = rpd_file.modification_time
        date = datetime.datetime.fromtimestamp(timestamp)

        timestamp = int(timestamp)
            
        date_human_readable = date_time_human_readable(date)
        name = rpd_file.name
        size = rpd_file.size
        

        thumbnail_icon = self.get_stock_icon(rpd_file.file_type)
        type_icon = self.get_stock_type_icon(rpd_file.file_type)

        status_icon = self.get_status_icon(rpd_file.status)
        
        if debug_info and False:
            cmd_line('Thumbnail icon: %s' % thumbnail_icon)
            cmd_line('Name: %s' % name)
            cmd_line('Timestamp: %s' % timestamp)
            cmd_line('Date: %s' % date_human_readable)
            cmd_line('Size: %s %s' % (size, common.formatSizeForUser(size)))
            cmd_line('Status: %s' % self.status_human_readable(rpd_file))
            cmd_line('Path: %s' % rpd_file.path)
            cmd_line('Device name: %s' % rpd_file.device_name)
            cmd_line(' ')

        iter = self.liststore.append((thumbnail_icon,
                                      name, 
                                      timestamp,
                                      date_human_readable,
                                      size, 
                                      common.formatSizeForUser(size),
                                      rpd_file.file_type, 
                                      type_icon,
                                      '',
                                      rpd_file,
                                      status_icon,
                                      rpd_file.status,
                                      rpd_file.path,
                                      rpd_file.device_name))
        
        scan_pid = rpd_file.scan_pid
        unique_id = rpd_file.unique_id
        path = self.liststore.get_path(iter)
        treerowref = gtk.TreeRowReference(self.liststore, path)
        
        if scan_pid in self.process_index:
            self.process_index[scan_pid].append(rpd_file)
        else:
            self.process_index[scan_pid] = [rpd_file,]
            
        self.treerow_index[unique_id] = treerowref
        
        if rpd_file.status in [STATUS_CANNOT_DOWNLOAD, STATUS_WARNING]:
            if not self.user_has_clicked_header:
                self.liststore.set_sort_column_id(11, gtk.SORT_DESCENDING)

    def generate_thumbnails(self, scan_pid):
        """Initiate thumbnail generation for files scanned in one process
        """
        self.thumbnail_manager.add_task(self.process_index[scan_pid])
    
    def update_thumbnail(self, thumbnail_data):
        """
        Takes the generated thumbnail and 
        """
        unique_id = thumbnail_data[0]
        thumbnail = thumbnail_data[1]
        thumbnail_icon = thumbnail_data[2]
        
        if thumbnail_icon is not None:
            thumbnail_icon = thumbnail_icon.get_pixbuf()
            
            treerowref = self.treerow_index[unique_id]
            path = treerowref.get_path()
            iter = self.liststore.get_iter(path)
            
            if thumbnail_icon:
                self.liststore.set(iter, 0, thumbnail_icon)
                
            #~ print type(thumbnail), thumbnail
            self.thumbnails[unique_id] = thumbnail.get_pixbuf()
        
        
    def no_selected_rows_available_for_download(self):
        """
        Gets the number of rows the user has selected that can actually
        be downloaded, and the threads they are found in
        """
        v = 0
        threads = []
        model, paths = self.get_selection().get_selected_rows()
        for path in paths:
            iter = self.liststore.get_iter(path)
            status = self.get_status(iter)
            if status in [STATUS_NOT_DOWNLOADED, STATUS_WARNING]:
                v += 1
                thread = self.get_thread(iter)
                if thread not in threads:
                    threads.append(thread)
        return v, threads
        
    def rows_available_for_download(self):
        """
        Returns true if one or more rows has their status as STATUS_NOT_DOWNLOADED or STATUS_WARNING
        """
        iter = self.liststore.get_iter_first()
        while iter:
            status = self.get_status(iter)
            if status in [STATUS_NOT_DOWNLOADED, STATUS_WARNING]:
                return True
            iter = self.liststore.iter_next(iter)
        return False
    
    def update_download_selected_button(self):
        """
        Updates the text on the Download Selection button, and set its sensitivity
        """
        no_available_for_download = 0
        selection = self.get_selection()
        model, paths = selection.get_selected_rows()
        if paths:            
            path = paths[0]
            iter = self.liststore.get_iter(path)
            
            #update button text
            no_available_for_download, threads = self.no_selected_rows_available_for_download()
            
        if no_available_for_download and workers.scanComplete(threads):
            self.rapidApp.download_selected_button.set_label(self.rapidApp.DOWNLOAD_SELECTED_LABEL + " (%s)" % no_available_for_download)
            self.rapidApp.download_selected_button.set_sensitive(True)
        else:
            #nothing was selected, or nothing is available from what the user selected, or should not download right now
            self.rapidApp.download_selected_button.set_label(self.rapidApp.DOWNLOAD_SELECTED_LABEL)
            self.rapidApp.download_selected_button.set_sensitive(False)
    
    def on_selection_changed(self, selection):
        """
        Update download selected button and preview the most recently
        selected row in the treeview
        """
        #~ self.update_download_selected_button()
        size = selection.count_selected_rows()
        if size == 0:
            self.selected_rows = set()
            self.show_preview(None)
        else:
            if size <= len(self.selected_rows):
                # discard everything, start over
                self.selected_rows = set()
                self.selection_size = size
            model, paths = selection.get_selected_rows()
            for path in paths:
                iter = self.liststore.get_iter(path)
                
                ref = self.treerow_index[self.get_rpd_file(iter).unique_id]
                
                if ref not in self.selected_rows:
                    self.show_preview(treerowref=ref, iter=iter)
                    self.selected_rows.add(ref)
            
    def clear_all(self, thread_id = None):
        if thread_id is None:
            self.liststore.clear()
            self.show_preview(None)
        else:
            iter = self.liststore.get_iter_first()
            while iter:
                t = self.get_thread(iter) 
                if t == thread_id:
                    if self.previewed_file_treerowref:
                        rpd_file = self.get_rpd_file(iter)
                        if rpd_file.treerowref == self.previewed_file_treerowref:
                            self.show_preview(None)
                    self.liststore.remove(iter)
                    # need to start over, or else bad things happen
                    iter = self.liststore.get_iter_first()
                else:
                    iter = self.liststore.iter_next(iter)
    
    def refreshSampleDownloadFolders(self, thread_id = None):
        """
        Refreshes the download folder of every file that has not yet been downloaded
        
        This is useful when the user updates the preferences, and the scan has already occurred (or is occurring)
        
        If thread_id is specified, will only update rows with that thread
        """
        for iter in self.get_tree_row_iters():
            status = self.get_status(iter)
            if status in [STATUS_NOT_DOWNLOADED, STATUS_WARNING, STATUS_CANNOT_DOWNLOAD]:
                regenerate = True
                if thread_id is not None:
                    t = self.get_thread(iter)
                    regenerate = t == thread_id
                
                if regenerate:
                    rpd_file = self.get_rpd_file(iter)
                    if rpd_file.isImage:
                        rpd_file.downloadFolder = self.rapidApp.prefs.download_folder
                    else:
                        rpd_file.downloadFolder = self.rapidApp.prefs.video_download_folder
                    rpd_file.samplePath = os.path.join(rpd_file.downloadFolder, rpd_file.sampleSubfolder)
                    if rpd_file.treerowref == self.previewed_file_treerowref:
                        self.show_preview(iter)                

    def _refreshNameFactories(self):
        sample_download_start_time = datetime.datetime.now()
        self.imageRenamePrefsFactory = rn.ImageRenamePreferences(self.rapidApp.prefs.image_rename, self, 
                                                                 self.rapidApp.fileSequenceLock, sequences)
        self.imageRenamePrefsFactory.setDownloadStartTime(sample_download_start_time)
        self.videoRenamePrefsFactory = rn.VideoRenamePreferences(self.rapidApp.prefs.video_rename, self, 
                                                                 self.rapidApp.fileSequenceLock, sequences)
        self.videoRenamePrefsFactory.setDownloadStartTime(sample_download_start_time)
        self.subfolderPrefsFactory = rn.SubfolderPreferences(self.rapidApp.prefs.subfolder, self)
        self.subfolderPrefsFactory.setDownloadStartTime(sample_download_start_time)
        self.videoSubfolderPrefsFactory = rn.VideoSubfolderPreferences(self.rapidApp.prefs.video_subfolder, self)
        self.videoSubfolderPrefsFactory.setDownloadStartTime(sample_download_start_time)
        self.strip_characters = self.rapidApp.prefs.strip_characters
        
    
    def refreshGeneratedSampleSubfolderAndName(self, thread_id = None):
        """
        Refreshes the name, subfolder and status of every file that has not yet been downloaded
        
        This is useful when the user updates the preferences, and the scan has already occurred (or is occurring)
        
        If thread_id is specified, will only update rows with that thread
        """
        self._setUsesJobCode()
        self._refreshNameFactories()
        for iter in self.get_tree_row_iters():
            status = self.get_status(iter)
            if status in [STATUS_NOT_DOWNLOADED, STATUS_WARNING, STATUS_CANNOT_DOWNLOAD]:
                regenerate = True
                if thread_id is not None:
                    t = self.get_thread(iter)
                    regenerate = t == thread_id
                
                if regenerate:
                    rpd_file = self.get_rpd_file(iter)
                    self.generateSampleSubfolderAndName(rpd_file, iter)
                    if rpd_file.treerowref == self.previewed_file_treerowref:
                        self.show_preview(iter)
    
    def generateSampleSubfolderAndName(self, rpd_file, iter):
        problem = pn.Problem()
        if rpd_file.isImage:
            fallback_date = None
            subfolderPrefsFactory = self.subfolderPrefsFactory
            renamePrefsFactory = self.imageRenamePrefsFactory
            nameUsesJobCode = self.imageRenameUsesJobCode
            subfolderUsesJobCode = self.imageSubfolderUsesJobCode
        else:
            fallback_date = rpd_file.modification_time
            subfolderPrefsFactory = self.videoSubfolderPrefsFactory
            renamePrefsFactory = self.videoRenamePrefsFactory
            nameUsesJobCode = self.videoRenameUsesJobCode
            subfolderUsesJobCode = self.videoSubfolderUsesJobCode
            
        renamePrefsFactory.setJobCode(self.get_job_code(iter))
        subfolderPrefsFactory.setJobCode(self.get_job_code(iter))
        
        generateSubfolderAndName(rpd_file, problem, subfolderPrefsFactory, renamePrefsFactory, 
                                nameUsesJobCode, subfolderUsesJobCode,
                                self.strip_characters, fallback_date)
        if self.get_status(iter) != rpd_file.status:
            self.liststore.set(iter, 11, rpd_file.status)
            self.liststore.set(iter, 10, self.get_status_icon(rpd_file.status))
        rpd_file.sampleStale = False
        
    def _setUsesJobCode(self):
        self.imageRenameUsesJobCode = rn.usesJobCode(self.rapidApp.prefs.image_rename)
        self.imageSubfolderUsesJobCode = rn.usesJobCode(self.rapidApp.prefs.subfolder)
        self.videoRenameUsesJobCode = rn.usesJobCode(self.rapidApp.prefs.video_rename)
        self.videoSubfolderUsesJobCode = rn.usesJobCode(self.rapidApp.prefs.video_subfolder)        
    
    
    def status_human_readable(self, rpd_file):
        if rpd_file.status == STATUS_DOWNLOADED:
            v = _('%(filetype)s was downloaded successfully') % {'filetype': rpd_file.displayNameCap}
        elif rpd_file.status == STATUS_DOWNLOAD_FAILED:
            v = _('%(filetype)s was not downloaded') % {'filetype': rpd_file.displayNameCap}
        elif rpd_file.status == STATUS_DOWNLOADED_WITH_WARNING:
            v = _('%(filetype)s was downloaded with warnings') % {'filetype': rpd_file.displayNameCap}
        elif rpd_file.status == STATUS_BACKUP_PROBLEM:
            v = _('%(filetype)s was downloaded but there were problems backing up') % {'filetype': rpd_file.displayNameCap}
        elif rpd_file.status == STATUS_DOWNLOAD_AND_BACKUP_FAILED:
            v = _('%(filetype)s was neither downloaded nor backed up') % {'filetype': rpd_file.displayNameCap}                
        elif rpd_file.status == STATUS_NOT_DOWNLOADED:
            v = _('%(filetype)s is ready to be downloaded') % {'filetype': rpd_file.displayNameCap}
        elif rpd_file.status == STATUS_DOWNLOAD_PENDING:
            v = _('%(filetype)s is about to be downloaded') % {'filetype': rpd_file.displayNameCap}
        elif rpd_file.status == STATUS_WARNING:
            v = _('%(filetype)s will be downloaded with warnings')% {'filetype': rpd_file.displayNameCap}
        elif rpd_file.status == STATUS_CANNOT_DOWNLOAD:
            v = _('%(filetype)s cannot be downloaded') % {'filetype': rpd_file.displayNameCap}
        return v    

    def getThumbnail(self, rpd_file):
        rpd_file.generateThumbnail()
        if rpd_file.thumbnail is None:
            if rpd_file.isImage:
                rpd_file.thumbnail = getGenericPhotoImage()
            else:
                rpd_file.thumbnail = getGenericVideoImage()
            rpd_file.generic_thumbnail = True        
    
    def loadMetadata(self, rpd_file, fromDownloadedFile=False):
        try:
            rpd_file.loadMetadata(fromDownloadedFile)
        except:
            if debug_info:
                cmd_line("Preview of file occurred where metadata could not be loaded")
            if rpd_file.status == STATUS_NOT_DOWNLOADED:
                rpd_file.status = STATUS_CANNOT_DOWNLOAD
                rpd_file.problem = pn.Problem()
                rpd_file.problem.add_problem(None, pn.CANNOT_DOWNLOAD_BAD_METADATA, {'filetype': rpd_file.displayNameCap})
                
            rpd_file.metadata = None            
        else:
            self.getThumbnail(rpd_file)
        
    def show_preview(self, treerowref=None, iter=None):
        """
        Shows information about the image or video in the preview panel.
        """
        
        def _generateSampleSubfolderAndName():
            self._refreshNameFactories()
            self._setUsesJobCode()
            self.generateSampleSubfolderAndName(rpd_file, iter)
            
        def _loadMetadataAndThumbNailIfNeccesary():
            """
            the user may have selected a row in which know metadata has been loaded and/or no thumbnail generated
            """
            if rpd_file.metadata is None and rpd_file.status == STATUS_NOT_DOWNLOADED:
                if debug_info:
                    cmd_line("Loading metadata, and generating thumbnail, sample name, folders for a file that has not yet been downloaded")
                self.loadMetadata(rpd_file)
                if rpd_file.status <> STATUS_CANNOT_DOWNLOAD:
                    _generateSampleSubfolderAndName()
                
            elif rpd_file.status in [STATUS_DOWNLOADED, STATUS_DOWNLOADED_WITH_WARNING, STATUS_BACKUP_PROBLEM]:
                #~ if rpd_file.generic_thumbnail:
                    #~ cmd_line("must get thumbnail from downloaded file")
                    #~ self.loadMetadata(rpd_file, True)
                if debug_info:
                    cmd_line("File is downloaded, metadata should be loaded.... may need to generate a thumbnail")
                    print rpd_file.metadata
                    
            elif rpd_file.status in [STATUS_WARNING]:
                if debug_info:
                    cmd_line("Warning for file, but not downloaded")
                print "metadata", rpd_file.metadata
                if rpd_file.generic_thumbnail:
                    self.getThumbnail(rpd_file)
            
            elif rpd_file.status in [STATUS_DOWNLOAD_FAILED, STATUS_DOWNLOAD_AND_BACKUP_FAILED]:
                if debug_info:
                    cmd_line("Download failed on this file")
                self.loadMetadata(rpd_file)
                #~ if rpd_file.metadata is None:
                    #~ self.loadMetadata(rpd_file, True)
                print "metadata", rpd_file.metadata
            elif rpd_file.status == STATUS_DOWNLOAD_PENDING:
                # do nothing..... do not want to potentially overwrite data in thread
                pass
            elif rpd_file.status == STATUS_CANNOT_DOWNLOAD:
                # do nothing..... do not want to potentially overwrite data
                if debug_info:
                     cmd_line("File cannot be downloaded because of some kind of serious error")
            
        if not iter and not treerowref:
            # clear everything
            for widget in  [self.parentApp.preview_original_name_label,
                            self.parentApp.preview_name_label,
                            self.parentApp.preview_status_label, 
                            self.parentApp.preview_problem_title_label, 
                            self.parentApp.preview_problem_label]:
                widget.set_text('')
                
            for widget in  [self.parentApp.preview_image,
                            self.parentApp.preview_name_label,
                            self.parentApp.preview_original_name_label,
                            self.parentApp.preview_status_label,                             
                            self.parentApp.preview_problem_title_label,
                            self.parentApp.preview_problem_label                            
                            ]:
                widget.set_tooltip_text('')
                
            self.parentApp.preview_image.clear()
            self.parentApp.preview_status_icon.clear()
            self.parentApp.preview_destination_expander.hide()
            self.parentApp.preview_device_expander.hide()
            self.previewed_file_treerowref = None
            
        
        elif not self.suspend_previews:
            rpd_file = self.get_rpd_file(iter) #should fix this to something else!
            
            #~ _loadMetadataAndThumbNailIfNeccesary()
            
            self.previewed_file_treerowref = treerowref
            unique_id = rpd_file.unique_id
            
            if unique_id in self.thumbnails:
                base_thumbnail = self.thumbnails[unique_id]
            else:
                base_thumbnail = self.get_stock_thumbnail(rpd_file.file_type)
            
            self.parentApp.set_base_preview_image(base_thumbnail)
            thumbnail = self.parentApp.scaledPreviewImage()
                
            self.parentApp.preview_image.set_from_pixbuf(thumbnail)
            
            if False:
                image_tool_tip = "%s\n%s" % (date_time_human_readable(rpd_file.date_time(), False), common.formatSizeForUser(rpd_file.size))
                self.parentApp.preview_image.set_tooltip_text(image_tool_tip)

                if rpd_file.sampleStale and rpd_file.status in [STATUS_NOT_DOWNLOADED, STATUS_WARNING]:
                    _generateSampleSubfolderAndName()

                self.parentApp.preview_original_name_label.set_text(rpd_file.name)
                self.parentApp.preview_original_name_label.set_tooltip_text(rpd_file.name)
                if rpd_file.volume:
                    pixbuf = rpd_file.volume.get_icon_pixbuf(16)
                else:
                    pixbuf = self.icontheme.load_icon('gtk-harddisk', 16, gtk.ICON_LOOKUP_USE_BUILTIN)
                self.parentApp.preview_device_image.set_from_pixbuf(pixbuf)
                self.parentApp.preview_device_label.set_text(rpd_file.device_name)
                self.parentApp.preview_device_path_label.set_text(rpd_file.path)
                self.parentApp.preview_device_path_label.set_tooltip_text(rpd_file.path)
                
                if using_gio:
                    folder = gio.File(rpd_file.downloadFolder)
                    fileInfo = folder.query_info(gio.FILE_ATTRIBUTE_STANDARD_ICON)
                    icon = fileInfo.get_icon()
                    pixbuf = common.get_icon_pixbuf(using_gio, icon, 16, fallback='folder')
                else:
                    pixbuf = self.icontheme.load_icon('folder', 16, gtk.ICON_LOOKUP_USE_BUILTIN)
                    
                self.parentApp.preview_destination_image.set_from_pixbuf(pixbuf)
                downloadFolderName = os.path.split(rpd_file.downloadFolder)[1]            
                self.parentApp.preview_destination_label.set_text(downloadFolderName)

                if rpd_file.status in [STATUS_WARNING, STATUS_CANNOT_DOWNLOAD, STATUS_NOT_DOWNLOADED, STATUS_DOWNLOAD_PENDING]:
                    
                    self.parentApp.preview_name_label.set_text(rpd_file.sampleName)
                    self.parentApp.preview_name_label.set_tooltip_text(rpd_file.sampleName)
                    self.parentApp.preview_destination_path_label.set_text(rpd_file.samplePath)
                    self.parentApp.preview_destination_path_label.set_tooltip_text(rpd_file.samplePath)
                else:
                    self.parentApp.preview_name_label.set_text(rpd_file.downloadName)
                    self.parentApp.preview_name_label.set_tooltip_text(rpd_file.downloadName)
                    self.parentApp.preview_destination_path_label.set_text(rpd_file.downloadPath)
                    self.parentApp.preview_destination_path_label.set_tooltip_text(rpd_file.downloadPath)
                
                status_text = self.status_human_readable(rpd_file)
                self.parentApp.preview_status_icon.set_from_pixbuf(self.get_status_icon(rpd_file.status, preview=True))
                self.parentApp.preview_status_label.set_markup('<b>' + status_text + '</b>')
                self.parentApp.preview_status_label.set_tooltip_text(status_text)


                if rpd_file.status in [STATUS_WARNING, STATUS_DOWNLOAD_FAILED,
                                        STATUS_DOWNLOADED_WITH_WARNING, 
                                        STATUS_CANNOT_DOWNLOAD, 
                                        STATUS_BACKUP_PROBLEM, 
                                        STATUS_DOWNLOAD_AND_BACKUP_FAILED]:
                    problem_title = rpd_file.problem.get_title()
                    self.parentApp.preview_problem_title_label.set_markup('<i>' + problem_title + '</i>')
                    self.parentApp.preview_problem_title_label.set_tooltip_text(problem_title)
                    
                    problem_text = rpd_file.problem.get_problems()
                    self.parentApp.preview_problem_label.set_text(problem_text)
                    self.parentApp.preview_problem_label.set_tooltip_text(problem_text)
                else:
                    self.parentApp.preview_problem_label.set_markup('')
                    self.parentApp.preview_problem_title_label.set_markup('')
                    for widget in  [self.parentApp.preview_problem_title_label,
                                    self.parentApp.preview_problem_label
                                    ]:
                        widget.set_tooltip_text('')                
                    
                if self.rapidApp.prefs.display_preview_folders:
                    self.parentApp.preview_destination_expander.show()
                    self.parentApp.preview_device_expander.show()
            
    
    def select_rows(self, range):
        selection = self.get_selection()
        if range == 'all':
            selection.select_all()
        elif range == 'none':
            selection.unselect_all()
        else:
            # User chose to select all photos or all videos,
            # or select all files with or without job codes.

            # Temporarily suspend previews while a large number of rows
            # are being selected / unselected
            self.suspend_previews = True
            
            iter = self.liststore.get_iter_first()
            while iter is not None:
                if range in ['photos', 'videos']:
                    type = self.get_is_image(iter)
                    select_row = (type and range == 'photos') or (not type and range == 'videos')
                else:
                    job_code = self.get_job_code(iter)
                    select_row = (job_code and range == 'withjobcode') or (not job_code and range == 'withoutjobcode')

                if select_row:
                    selection.select_iter(iter)
                else:
                    selection.unselect_iter(iter)
                iter = self.liststore.iter_next(iter)
            
            self.suspend_previews = False
            # select the first photo / video
            iter = self.liststore.get_iter_first()
            while iter is not None:
                type = self.get_is_image(iter)
                if (type and range == 'photos') or (not type and range == 'videos'):
                    self.show_preview(iter)
                    break
                iter = self.liststore.iter_next(iter)


    def header_clicked(self, column):
        self.user_has_clicked_header = True
        
    def display_filename_column(self, display):
        """
        if display is true, the column will be shown
        otherwise, it will not be shown
        """
        self.filename_column.set_visible(display)
        
    def display_size_column(self, display):
        self.size_column.set_visible(display)

    def display_type_column(self, display):
        if not DOWNLOAD_VIDEO:
            self.type_column.set_visible(False)
        else:
            self.type_column.set_visible(display)
        
    def display_path_column(self, display):
        self.path_column.set_visible(display)
        
    def display_device_column(self, display):
        self.device_column.set_visible(display)
        
    def apply_job_code(self, job_code, overwrite=True, to_all_rows=False, thread_id=None):
        """
        Applies the Job code to the selected rows, or all rows if to_all_rows is True.
        
        If overwrite is True, then it will overwrite any existing job code.
        """

        def _apply_job_code():
            status = self.get_status(iter)
            if status in [STATUS_DOWNLOAD_PENDING, STATUS_WARNING, STATUS_NOT_DOWNLOADED]:
                
                if rpd_file.isImage:
                    apply = rn.usesJobCode(self.rapidApp.prefs.image_rename) or rn.usesJobCode(self.rapidApp.prefs.subfolder)
                else:
                    apply = rn.usesJobCode(self.rapidApp.prefs.video_rename) or rn.usesJobCode(self.rapidApp.prefs.video_subfolder)
                if apply:
                    if overwrite:
                        self.liststore.set(iter, 8, job_code)
                        rpd_file.jobcode = job_code
                        rpd_file.sampleStale = True
                    else:
                        if not self.get_job_code(iter):
                            self.liststore.set(iter, 8, job_code)
                            rpd_file.jobcode = job_code
                            rpd_file.sampleStale = True
                else:
                    pass
                    #if they got an existing job code, may as well keep it there in case the user 
                    #reactivates job codes again in their prefs
                    
        if to_all_rows or thread_id is not None:
            for iter in self.get_tree_row_iters():
                apply = True
                if thread_id is not None:
                    t = self.get_thread(iter)
                    apply = t == thread_id
                    
                if apply:
                    rpd_file = self.get_rpd_file(iter)
                    _apply_job_code()
                    if rpd_file.treerowref == self.previewed_file_treerowref:
                        self.show_preview(iter)
        else:
            for iter in self.get_tree_row_iters(selected_only = True):
                rpd_file = self.get_rpd_file(iter)
                _apply_job_code()
                if rpd_file.treerowref == self.previewed_file_treerowref:
                    self.show_preview(iter)
            
    def job_code_missing(self, selected_only):
        """
        Returns True if any of the pending downloads do not have a 
        job code assigned.
        
        If selected_only is True, will only check in rows that the 
        user has selected.
        """
        
        def _job_code_missing(iter):
            status = self.get_status(iter)
            if status in [STATUS_WARNING, STATUS_NOT_DOWNLOADED]:
                is_image = self.get_is_image(iter)
                job_code = self.get_job_code(iter)
                return needAJobCode.needAJobCode(job_code, is_image)
            return False
        
        self._setUsesJobCode()
        needAJobCode = NeedAJobCode(self.rapidApp.prefs)
        
        v = False
        if selected_only:
            selection = self.get_selection()
            model, pathlist = selection.get_selected_rows()
            for path in pathlist:
                iter = self.liststore.get_iter(path)
                v = _job_code_missing(iter)
                if v:
                    break
        else:
            iter = self.liststore.get_iter_first()
            while iter:
                v = _job_code_missing(iter)
                if v:
                    break
                iter = self.liststore.iter_next(iter)
        return v

    
    def _set_download_pending(self, iter, threads):
        existing_status = self.get_status(iter)
        if existing_status in [STATUS_WARNING, STATUS_NOT_DOWNLOADED]:
            self.liststore.set(iter, 11, STATUS_DOWNLOAD_PENDING)
            self.liststore.set(iter, 10, self.download_pending_icon)
            # this value is in a thread's list of files to download
            rpd_file = self.get_rpd_file(iter)
            # each thread will see this change in status
            rpd_file.status = STATUS_DOWNLOAD_PENDING
            thread = self.get_thread(iter)
            if thread not in threads:
                threads.append(thread)
        
    def set_status_to_download_pending(self, selected_only, thread_id=None):
        """
        Sets status of files to be download pending, if they are waiting to be downloaded
        if selected_only is true, only applies to selected rows
        
        If thread_id is not None, then after the statuses have been set, 
        the thread will be restarted (this is intended for the cases
        where this method is called from a thread and auto start is True)
        
        Returns a list of threads which can be downloaded
        """
        threads = []
        
        if selected_only:
            for iter in self.get_tree_row_iters(selected_only = True):
                self._set_download_pending(iter, threads)
        else:
            for iter in self.get_tree_row_iters():
                apply = True                
                if thread_id is not None:
                    t = self.get_thread(iter)
                    apply = t == thread_id
                if apply:                
                    self._set_download_pending(iter, threads)
                
            if thread_id is not None:
                # restart the thread
                workers[thread_id].startStop()
        return threads
                
    def update_status_post_download(self, treerowref):
        path = treerowref.get_path()
        if not path:
            sys.stderr.write("FIXME: SelectionTreeView treerowref no longer refers to valid row\n")
        else:
            iter = self.liststore.get_iter(path)
            rpd_file = self.get_rpd_file(iter)
            status = rpd_file.status
            self.liststore.set(iter, 11, status)
            self.liststore.set(iter, 10, self.get_status_icon(status))
            
            # If this row is currently previewed, then should update the preview
            if rpd_file.treerowref == self.previewed_file_treerowref:
                self.show_preview(iter)

class RapidPreferences(prefs.Preferences):
    if TINY_SCREEN:
        zoom = 120
    else:
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
        task_results_conn, task_process_conn = Pipe()
        
        source = task_results_conn.fileno()
        self._pipes[source] = task_results_conn
        gobject.io_add_watch(source, gobject.IO_IN, self.results_callback)
        
        terminate_queue = Queue()
        run_event = Event()
        run_event.set()
        
        self._initiate_task(task, task_process_conn, terminate_queue, run_event)
        
    def _initiate_task(self, task, task_process_conn, terminate_queue, run_event):
        print "implement child class method"
        
    
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
    def _initiate_task(self, path, task_process_conn, terminate_queue, run_event):
        scan = scan_process.Scan(path, self.batch_size, task_process_conn, terminate_queue, run_event)
        scan.start()
        self._processes.append((scan, terminate_queue, run_event))
        
class ThumbnailManager(TaskManager):
    def _initiate_task(self, files, task_process_conn, terminate_queue, run_event):
        generator = tn.GenerateThumbnails(files, self.batch_size, task_process_conn, terminate_queue, run_event)
        generator.start()
        self._processes.append((generator, terminate_queue, run_event))

class RapidApp(dbus.service.Object): 
    def __init__(self,  bus, path, name, taskserver=None): 
        
        dbus.service.Object.__init__ (self, bus, path, name)
        self.running = False
        
        self.taskserver = taskserver
        
        builder = gtk.Builder()
        builder.add_from_file("glade3/mp-prototype.glade") 
        
        self.rapidapp = builder.get_object("rapidapp")
        self.selection_hbox = builder.get_object("selection_hbox")
        self.textbuffer = builder.get_object("output_textview").get_buffer()
        #~ self.main_vpaned = builder.get_object(
        
        builder.connect_signals(self)
        
        
        self.prefs = RapidPreferences()
        
        # remember the window size from the last time the program was run
        if self.prefs.main_window_maximized:
            self.rapidapp.maximize()
        elif self.prefs.main_window_size_x > 0:
            self.rapidapp.set_default_size(self.prefs.main_window_size_x, self.prefs.main_window_size_y)
        else:
            # set a default size
            self.rapidapp.set_default_size(650, 650)
            
        if gtk.gdk.screen_height() <= config.TINY_SCREEN_HEIGHT:
            self.prefs.display_preview_folders = False
            self.menu_preview_folders.set_sensitive(False)
        
        self.rapidapp.show_all()
        
        #~ paths = ['/home/damon/rapid', '/home/damon/Pictures/processing']
        #~ paths = ['/media/EOS_DIGITAL/', '/media/EOS_DIGITAL_/']
        paths = ['/home/damon/rapid/cr2']
        self.batch_size = 10
        
        self.testing_auto_exit = False
        self.testing_auto_exit_trip = len(paths)
        self.testing_auto_exit_trip_counter = 0
        
        self.selection_vbox = SelectionVBox(self)
        self.selection_hbox.pack_start(self.selection_vbox, padding=12)
        
        self.scan_manager = ScanManager(self.scan_results, self.batch_size)
        
        for path in paths:
            self.scan_manager.add_task(path)
            
    
    def on_rapidapp_destroy(self, widget, data=None):

        self.scan_manager.terminate()        
        self.selection_vbox.selection_treeview.thumbnail_manager.terminate()

        # save window and component sizes
        self.prefs.hpaned_pos = self.selection_vbox.file_hpaned.get_position()
        #~ self.prefs.vpaned_pos = self.main_vpaned.get_position()

        x, y = self.rapidapp.get_size()
        self.prefs.main_window_size_x = x
        self.prefs.main_window_size_y = y
        
        gtk.main_quit()        
        
    def scan_results(self, source, condition):
        connection = self.scan_manager.get_pipe(source)
        
        conn_type, data = connection.recv()
        iter = self.textbuffer.get_end_iter()
        
        if conn_type == rpdmp.CONN_COMPLETE:
            size, scan_pid = data
            size = formatSizeForUser(size)
            self.textbuffer.insert(iter, 'Files total %s\n' % size)
            self.testing_auto_exit_trip_counter += 1
            if self.testing_auto_exit_trip_counter == self.testing_auto_exit_trip and self.testing_auto_exit:
                self.on_rapidapp_destroy(self.rapidapp)
            else:
                self.selection_vbox.selection_treeview.generate_thumbnails(
                                                            scan_pid)
            
        else:
            if len(data) > self.batch_size:
                logger.error("incoming pipe length is %s" % len(data))
            else:
                for i in range(len(data)):
                    rpd_file = data[i]
                    self.selection_vbox.selection_treeview.add_file(rpd_file)
        
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
