#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2007, 2008, 2009 Damon Lynch <damonlynch@gmail.com>

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

from __future__ import with_statement #needed for python 2.5, unneeded for python 2.6

import sys
import os
import shutil
import time
import datetime
import atexit
import tempfile
import webbrowser

import dbus
import dbus.bus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
DBusGMainLoop(set_as_default=True)

from threading import Thread, Lock
from thread import error as thread_error
from thread import get_ident

import gtk.gdk as gdk
import pango

import gnomevfs

import prefs
import paths
import gnomeglade

import pynotify

import ValidatedEntry

import idletube as tube

import config
import common
import misc
import higdefaults as hd

from media import getDefaultPhotoLocation
from media import CardMedia

import media

import metadata

import renamesubfolderprefs as rn 

import tableplusminus as tpm

__version__ = config.version

try: 
    import pygtk 
    pygtk.require("2.0") 
except: 
    pass 
try: 
    import gtk 
    import gtk.glade 
except: 
    sys.exit(1)


def today():
    return datetime.date.today().strftime('%Y-%m-%d')
    

exiting = False

def updateDisplay(display_queue):

    try:
        if display_queue.size() != 0:
            call, args = display_queue.get()
            if not exiting:
                call(*args)
#            else do not update display
        else:
            print "Empty display queue!"
        return True
    
    except tube.EOInformation:
        for w in workers.getStartedWorkers():
            w.join()
        gtk.main_quit()
        
        return False


class Queue(tube.Tube):
    def __init__(self, maxSize = config.MAX_NO_READERS):
        tube.Tube.__init__(self, maxSize)

    def setMaxSize(self, maxSize):
        self.maxsize = maxSize


# Module wide values -
#   set up thesse variable in global name space, and initialize with proper 
#   values later
#   this is ugly but I don't know a better way :(

display_queue = Queue()
media_collection_treeview = image_hbox = log_dialog = None


class ThreadManager:
    _workers = []
    
    
    def append(self, w):
        self._workers.append(w)
    
    def __getitem__(self, i):
        return self._workers[i]
        
    def __len__(self):
        return len(self._workers)
        
    def disableWorker(self, thread_id):
        """
        it only makes sense to disable a worker
        when it has not yet started
        """
        
        self._workers[thread_id].doNotStart = True
        
    def _isReadyToStart(self, w):
        """
        Returns True if the worker is ready to start
        and has not been disabled
        """
        return not w.hasStarted and not w.doNotStart
        
    def _isFinished(self, w):
        """
        Returns True if the worker has finished running
        """
        
        return w.hasStarted and not w.isAlive()
    
    def firstWorkerReadyToStart(self):
        for w in self._workers:
            if self._isReadyToStart(w):
                return w
        return None
        
    def startWorkers(self):
        for w in self.getReadyToStartWorkers():
            w.start()
                
    def quitAllWorkers(self):
        global exiting 
        exiting = True
        for w in self._workers:
            w.quit()

    def getWorkers(self):
        for w in self._workers:
            yield w
            
    def getStartedWorkers(self):
        for w in self._workers:
            if w.hasStarted:
                yield w
    
    def getReadyToStartWorkers(self):
        for w in self._workers:
            if self._isReadyToStart(w):
                yield w
                
    def noReadyToStartWorkers(self):
        n = 0
        for w in self._workers:
            if self._isReadyToStart(w):
                n += 1
        return n
        
    def getRunningWorkers(self):
        for w in self._workers:
            if w.hasStarted and w.isAlive():
                yield w
                
    def getPausedWorkers(self):
        for w in self._workers:
            if w.hasStarted and not w.running:
                yield w            
                
    def getFinishedWorkers(self):
        for w in self._workers:
            if self._isFinished(w):
                yield w
    
    def noRunningWorkers(self):
        i = 0
        for w in self._workers:
            if w.hasStarted and w.isAlive():
                i += 1
        return i
        
    def getNextThread_id(self):
        return len(self._workers)
        
    def printWorkerStatus(self, worker=None):
        if worker:
            l = [worker]
        else:
            l = range(len(self._workers))
        for i in l: 
            print "\nThread %i\n=======\n" % i
            w = self._workers[i]
            print "Disabled:", w.doNotStart
            print "Started:", w.hasStarted
            print "Running:", w.running
            print "Completed:", self._isFinished(w)

                
        
workers = ThreadManager()

class RapidPreferences(prefs.Preferences):
    defaults = {
        "program_version": prefs.Value(prefs.STRING, ""),
        "download_folder":  prefs.Value(prefs.STRING, 
                                        getDefaultPhotoLocation()),
        "subfolder": prefs.ListValue(prefs.STRING_LIST, [rn.DATE_TIME,  
                                                rn.IMAGE_DATE,
                                                rn.LIST_DATE_TIME_L2[9], 
                                                rn.SEPARATOR,
                                                '', '', 
                                                rn.DATE_TIME,
                                                rn.IMAGE_DATE, 
                                                rn.LIST_DATE_TIME_L2[0]],
                                                ),
        "image_rename": prefs.ListValue(prefs.STRING_LIST, [rn.FILENAME, 
                                        rn.NAME_EXTENSION,
                                        rn.ORIGINAL_CASE]),
        "device_autodetection": prefs.Value(prefs.BOOL, True),
        "device_location": prefs.Value(prefs.STRING, os.path.expanduser('~')), 
        "device_autodetection_psd": prefs.Value(prefs.BOOL,  False),
        "backup_images": prefs.Value(prefs.BOOL, False),
        "backup_device_autodetection": prefs.Value(prefs.BOOL, True),
        "backup_identifier": prefs.Value(prefs.STRING, 
                                        config.DEFAULT_BACKUP_LOCATION),
        "backup_location": prefs.Value(prefs.STRING, os.path.expanduser('~')),
        "strip_characters": prefs.Value(prefs.BOOL, True),
        "auto_download_at_startup": prefs.Value(prefs.BOOL, False),
        "auto_download_upon_device_insertion": prefs.Value(prefs.BOOL, False),
        "auto_unmount": prefs.Value(prefs.BOOL, False),
        "auto_exit": prefs.Value(prefs.BOOL, False),
        "indicate_download_error": prefs.Value(prefs.BOOL, True),
        "download_conflict_resolution": prefs.Value(prefs.STRING, 
                                        config.SKIP_DOWNLOAD),
        "backup_duplicate_overwrite": prefs.Value(prefs.BOOL, False),
        "backup_missing": prefs.Value(prefs.STRING, config.IGNORE),
        "display_thumbnails": prefs.Value(prefs.BOOL, True),
        "show_log_dialog": prefs.Value(prefs.BOOL, False),
        "day_start": prefs.Value(prefs.STRING,  "03:00"), 
        "downloads_today": prefs.ListValue(prefs.STRING_LIST,  [today(),  '0']), 
         "stored_sequence_no": prefs.Value(prefs.INT,  0), 
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
#        print "now: %s  ## adjustedToday: %s" % (now,  adjustedToday)
        if  now < adjustedToday :
            try:
                return int(self.downloads_today[1])
            except ValueError:
                print "Invalid Downloads Today value.\nResetting value to zero."
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
            print "Start of day preference is corrupted.\nResetting to midnight."
            self.day_start = "0:0"
            return 0, 0


class ImageRenameTable(tpm.TablePlusMinus):

    def __init__(self, parentApp):
  
        tpm.TablePlusMinus.__init__(self, 1, 3)
        self.parentApp = parentApp

        self.getParentAppPrefs()
        self.getPrefsFactory()
        
        if not hasattr(self, "errorTitle"):
            self.errorTitle = "Error in Image Rename preferences"
        
        try:
            self.prefsFactory.checkPrefsForValidity()
            
        except (rn.PrefValueInvalidError, rn.PrefLengthError, 
                rn.PrefValueKeyComboError,  rn.PrefKeyError),  e:

            print self.errorTitle 
            print "Sorry,these preferences contain an error:"
            print self.prefsFactory.formatPreferencesForPrettyPrint()
            
            # the preferences were invalid
            # reset them to their default

            self.prefList = self.prefsFactory.defaultPrefs
            self.getPrefsFactory()
            self.updateParentAppPrefs()

            msg = "%s.\nResetting to default values." % e
            print msg
            
            
            misc.run_dialog(self.errorTitle, msg, 
                parentApp,
                gtk.MESSAGE_ERROR)
        
        for row in self.prefsFactory.getWidgetsBasedOnPreferences():
            self.append(row)
            


            
    def updatePreferences(self):
        prefList = []
        for row in self.pm_rows:                
            for col in range(self.pm_noColumns):
                widget = row[col]
                if widget:
                    name = widget.get_name()
                    if name == 'GtkComboBox':
                        value = widget.get_active_text()
                    elif name == 'GtkEntry':
                        value = widget.get_text()
                    else:
                        print "Unknown preference widget!"
                        value = ''
                else:
                    value = ''
                prefList.append(value)

        self.prefList = prefList
        self.updateParentAppPrefs()
        self.prefsFactory.prefList = prefList
        self.updateExample()
            
    def getParentAppPrefs(self):
        self.prefList = self.parentApp.prefs.image_rename
    
    def getPrefsFactory(self):
        self.prefsFactory = rn.ImageRenamePreferences(self.prefList, self,  
              sequences = sequences)
        
    def updateParentAppPrefs(self):
        self.parentApp.prefs.image_rename = self.prefList
        
    def updateExample(self):
        self.parentApp.updateImageRenameExample()
    
    def getDefaultRow(self):
        return self.prefsFactory.getDefaultRow()
        
    def on_combobox_changed(self, widget, rowPosition):
        
        for col in range(self.pm_noColumns):
            if self.pm_rows[rowPosition][col] == widget:
                break
        selection = []
        for i in range(col + 1):
            # ensure it is a combo box we are getting the value from
            if hasattr(self.pm_rows[rowPosition][i], 'get_active_text'):
                selection.append(self.pm_rows[rowPosition][i].get_active_text())
            else:
                selection.append(self.pm_rows[rowPosition][i].get_text())
                
        for i in range(col + 1, self.pm_noColumns):
            selection.append('')
            
        if col <> (self.pm_noColumns - 1):
            widgets = self.prefsFactory.getWidgetsBasedOnUserSelection(selection)
            
            for i in range(col + 1, self.pm_noColumns):
                oldWidget = self.pm_rows[rowPosition][i]
                if oldWidget:
                    self.remove(oldWidget)
                    if oldWidget in self.pm_callbacks:
                        del self.pm_callbacks[oldWidget]
                newWidget = widgets[i]
                self.pm_rows[rowPosition][i] = newWidget
                if newWidget:
                    self._createCallback(newWidget, rowPosition)
                    self.attach(newWidget, i, i+1, rowPosition, rowPosition + 1)
                    newWidget.show()
        self.updatePreferences()
        
    def on_entry_changed(self, widget, rowPosition):
        
#        print  "on entry changed",  widget.get_text()
        self.updatePreferences()

    def on_rowAdded(self, rowPosition):
        """
        Update preferences, as a row has been added
        """
        self.updatePreferences()
        
        # if this was the last row, and another has just been added, move vertical scrollbar down
        if rowPosition == (self.pm_noRows - 2):
            adjustment = self.parentApp.rename_scrolledwindow.get_vadjustment()
            adjustment.set_value(adjustment.upper)
        

    def on_rowDeleted(self, rowPosition):
        """
        Update preferences, as a row has been deleted
        """
        self.updatePreferences()        

class SubfolderTable(ImageRenameTable):
    def __init__(self, parentApp):    
        self.errorTitle = "Error in Download Subfolder preferences"
        ImageRenameTable.__init__(self,  parentApp)

    def getParentAppPrefs(self):
        self.prefList = self.parentApp.prefs.subfolder
    
    def getPrefsFactory(self):
        self.prefsFactory = rn.SubfolderPreferences(self.prefList, self)
        
    def updateParentAppPrefs(self):
        self.parentApp.prefs.subfolder = self.prefList

    def updateExample(self):
        self.parentApp.updateDownloadFolderExample()
        

class PreferencesDialog(gnomeglade.Component):
    def __init__(self, parentApp):
        gnomeglade.Component.__init__(self, 
                                    paths.share_dir(config.GLADE_FILE), 
                                    "preferencesdialog")
        
        self.widget.set_transient_for(parentApp.widget)
        self.prefs = parentApp.prefs

#        self._setupTabSelector()
        
        self._setupControlSpacing()

        # get example image data
        
        try:
            w = workers.firstWorkerReadyToStart()
            root, self.sampleImageName = w.firstImage()
            image = os.path.join(root, self.sampleImageName)
            self.sampleImage = metadata.MetaData(image)
            self.sampleImage.readMetadata() 
        except:
            self.sampleImage = metadata.DummyMetaData()
            self.sampleImageName = 'IMG_0524.CR2'
        
        # setup tabs
        self._setupDownloadFolderTab()
        self._setupImageRenameTab()
        self._setupRenameOptionsTab()
        self._setupDeviceTab()
        self._setupBackupTab()
        self._setupAutomationTab()
        self._setupErrorTab()

        self.widget.show()


    def on_preferencesdialog_destroy(self,  widget):
        """ Delete variables from memory that cause a file descriptor to be created on a mounted media"""
        del self.sampleImage,  self.rename_table.prefsFactory,  self.subfolder_table.prefsFactory
        
    def _setupTabSelector(self):
        self.notebook.set_show_tabs(0)
        self.model = gtk.ListStore(type(""))
        column = gtk.TreeViewColumn()
        rentext = gtk.CellRendererText()
        column.pack_start(rentext, expand=0)
        column.set_attributes(rentext, text=0)
        self.treeview.append_column(column)
        self.treeview.props.model = self.model
        for c in self.notebook.get_children():
            label = self.notebook.get_tab_label(c).get_text()
            if not label.startswith("_"):
                self.model.append( (label,) )
        self.treeview.columns_autosize()                
    
    def on_download_folder_filechooser_button_selection_changed(self, widget):
        self.prefs.download_folder = widget.get_current_folder()
        self.updateDownloadFolderExample()
    
    def on_backup_folder_filechooser_button_selection_changed(self, widget):
        self.prefs.backup_location = widget.get_current_folder()
        self.updateBackupExample()
        
    def on_device_location_filechooser_button_selection_changed(self, widget):
        self.prefs.device_location = widget.get_current_folder()
        
    def _setupControlSpacing(self):
        """
        set spacing of some but not all controls
        
        not currently used
        """
        
        self._setupTableSpacing(self.download_folder_table) 
        self.download_folder_table.set_row_spacing(2, 
                                hd.VERTICAL_CONTROL_SPACE)
        self._setupTableSpacing(self.rename_example_table)
        self.devices_table.set_col_spacing(0,   hd.NESTED_CONTROLS_SPACE)        
      
        self._setupTableSpacing(self.backup_table)
        self.backup_table.set_col_spacing(1, hd.NESTED_CONTROLS_SPACE)
        self.backup_table.set_col_spacing(2, hd.CONTROL_LABEL_SPACE)
        self._setupTableSpacing(self.compatibility_table)
        self.compatibility_table.set_row_spacing(0, 
                                            hd.VERTICAL_CONTROL_LABEL_SPACE)                                                    
        self._setupTableSpacing(self.error_table)
        self.error_table.set_row_spacing(5, hd.VERTICAL_CONTROL_SPACE / 2)
    
    
    def _setupTableSpacing(self, table):
        table.set_col_spacing(0, hd.NESTED_CONTROLS_SPACE)
        table.set_col_spacing(1, hd.CONTROL_LABEL_SPACE)

    def _setupSubfolderTable(self):
        self.subfolder_table = SubfolderTable(self)
        self.subfolder_vbox.pack_start(self.subfolder_table)
        self.subfolder_table.show_all()
        
    def _setupDownloadFolderTab(self):
        self.download_folder_filechooser_button = gtk.FileChooserButton(
                            "Select a folder to download photos to")
        self.download_folder_filechooser_button.set_current_folder(
                            self.prefs.download_folder)
        self.download_folder_filechooser_button.set_action(
                            gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER)
        self.download_folder_filechooser_button.connect("selection-changed", 
                    self.on_download_folder_filechooser_button_selection_changed)
                            
        self.download_folder_table.attach(
                            self.download_folder_filechooser_button, 
                            2, 3, 2, 3, yoptions = gtk.SHRINK)
        self.download_folder_filechooser_button.show()        

        self._setupSubfolderTable()
        self.updateDownloadFolderExample()
    
    def _setupImageRenameTab(self):

        self.rename_table = ImageRenameTable(self)
        self.rename_table_vbox.pack_start(self.rename_table)
        self.rename_table.show_all()
        self.original_name_label.set_markup("<i>%s</i>" % self.sampleImageName)
        self.updateImageRenameExample()
        
    def _setupRenameOptionsTab(self):
        self.downloads_today_entry = ValidatedEntry.ValidatedEntry(ValidatedEntry.bounded(ValidatedEntry.v_int, int, 0))
        self.stored_number_entry = ValidatedEntry.ValidatedEntry(ValidatedEntry.bounded(ValidatedEntry.v_int, int, 1))
        self.downloads_today_entry.connect('changed', self.on_downloads_today_entry_changed)
        self.stored_number_entry.connect('changed', self.on_stored_number_entry_changed)
        v = self.prefs.getAndMaybeResetDownloadsToday()
        self.downloads_today_entry.set_text(str(v))
        # make the displayed value of stored sequence no 1 more than actual value
        # so as not to confuse the user
        self.stored_number_entry.set_text(str(self.prefs.stored_sequence_no+1))
        self.sequence_vbox.pack_start(self.downloads_today_entry, expand=True, fill=True)
        self.sequence_vbox.pack_start(self.stored_number_entry, expand=False)
        self.downloads_today_entry.show()
        self.stored_number_entry.show()
        hour, minute = self.prefs.getDayStart()
        self.hour_spinbutton.set_value(float(hour))
        self.minute_spinbutton.set_value(float(minute))

        self.strip_characters_checkbutton.set_active(
                            self.prefs.strip_characters)
        
    def _setupDeviceTab(self):
        self.device_location_filechooser_button = gtk.FileChooserButton(
                            "Select an image folder")
        self.device_location_filechooser_button.set_current_folder(
                            self.prefs.device_location)
        self.device_location_filechooser_button.set_action(
                            gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER)
                            
        self.device_location_filechooser_button.connect("selection-changed", 
                    self.on_device_location_filechooser_button_selection_changed)

        self.devices2_table.attach(self.device_location_filechooser_button,
                            1, 2, 1, 2, xoptions = gtk.EXPAND|gtk.FILL,  yoptions = gtk.SHRINK)
        self.device_location_filechooser_button.show()
        self.autodetect_device_checkbutton.set_active(
                            self.prefs.device_autodetection)
        self.autodetect_psd_checkbutton.set_active(
                            self.prefs.device_autodetection_psd)
                            
        self.updateDeviceControls()
        

    def _setupBackupTab(self):
        self.backup_folder_filechooser_button = gtk.FileChooserButton(
                            "Select a folder in which to backup images")
        self.backup_folder_filechooser_button.set_current_folder(
                            self.prefs.backup_location)
        self.backup_folder_filechooser_button.set_action(
                            gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER)
        self.backup_folder_filechooser_button.connect("selection-changed", 
                    self.on_backup_folder_filechooser_button_selection_changed)
        self.backup_table.attach(self.backup_folder_filechooser_button,
                            3, 4, 7, 8, yoptions = gtk.SHRINK)
        self.backup_folder_filechooser_button.show()
        self.backup_identifier_entry.set_text(self.prefs.backup_identifier)
        
        #setup controls for manipulating sensitivity
        self._backupControls0 = [self.auto_detect_backup_checkbutton,
                                self.missing_backup_label,
                                self.backup_error_radiobutton,
                                self.backup_warning_radiobutton,
                                self.backup_ignore_radiobutton]
        self._backupControls1 = [self.backup_identifier_explanation_label,
                                self.backup_identifier_label,
                                self.backup_identifier_entry,
                                self.example_backup_path_label,
                                self.backup_example_label,]
        self._backupControls2 = [self.backup_location_label,
                                self.backup_folder_filechooser_button,
                                self.backup_location_explanation_label]
        self._backupControls = self._backupControls0 + self._backupControls1 + \
                                self._backupControls2
        
        #assign values to checkbuttons only when other controls
        #have been setup, because their toggle signal is activated
        #when a value is assigned
        
        self.backup_checkbutton.set_active(self.prefs.backup_images)
        self.auto_detect_backup_checkbutton.set_active(
                            self.prefs.backup_device_autodetection)
        self.updateBackupControls()
        self.updateBackupExample()
    
    def _setupAutomationTab(self):
        self.auto_startup_checkbutton.set_active(
                        self.prefs.auto_download_at_startup)
        self.auto_insertion_checkbutton.set_active(
                        self.prefs.auto_download_upon_device_insertion)
        self.auto_unmount_checkbutton.set_active(
                        self.prefs.auto_unmount)
        self.auto_exit_checkbutton.set_active(
                        self.prefs.auto_exit)

        
    def _setupErrorTab(self):
        self.indicate_download_error_checkbutton.set_active(
                            self.prefs.indicate_download_error)
                            
        if self.prefs.download_conflict_resolution == config.SKIP_DOWNLOAD:
            self.skip_download_radiobutton.set_active(True)
        else:
            self.add_identifier_radiobutton.set_active(True)
            
        if self.prefs.backup_missing == config.REPORT_ERROR:
            self.backup_error_radiobutton.set_active(True)
        elif self.prefs.backup_missing == config.REPORT_WARNING:
            self.backup_warning_radiobutton.set_active(True)
        else:
            self.backup_ignore_radiobutton.set_active(True)
            
        if self.prefs.backup_duplicate_overwrite:
            self.backup_duplicate_overwrite_radiobutton.set_active(True)
        else:
            self.backup_duplicate_skip_radiobutton.set_active(True)

    def updateImageRenameExample(self):
        """ 
        Displays example image name to the user 
        """
        
        if hasattr(self, 'rename_table'):
            name, problem = self.rename_table.prefsFactory.generateNameUsingPreferences(
                    self.sampleImage, self.sampleImageName, 
                    self.prefs.strip_characters,  sequencesPreliminary=False)
        else:
            name = problem = ''
            
        # since this is markup, escape it
        text = "<i>%s</i>" % common.escape(name)
        
        if problem:
            text += "\n<i><b>Warning:</b> There is insufficient image metatdata to fully generate the name. Please use other renaming options.</i>" 

        self.new_name_label.set_markup(text)
            
    def updateDownloadFolderExample(self):
        """ 
        Displays example subfolder name(s) to the user 
        """
        
        if hasattr(self,  'subfolder_table'):
            path, problem = self.subfolder_table.prefsFactory.generateNameUsingPreferences(
                            self.sampleImage, self.sampleImageName,
                            self.prefs.strip_characters)
        else:
            path = problem = ''
        
        text = os.path.join(self.prefs.download_folder, path)
        # since this is markup, escape it
        path = common.escape(text)
        if problem:
            text += "\n<i><b>Warning:</b> There is insufficient image metatdata to fully generate subfolders. Please use other subfolder naming options.</i>" 
            
        self.example_download_path_label.set_markup("<i>Example: %s</i>" % text)
        
    def on_hour_spinbutton_value_changed(self, spinbutton):
        hour = spinbutton.get_value_as_int()
        minute = self.minute_spinbutton.get_value_as_int()
        self.prefs.setDayStart(hour, minute)
        self.on_downloads_today_entry_changed(self.downloads_today_entry)
        
    def on_minute_spinbutton_value_changed(self, spinbutton):
        hour = self.hour_spinbutton.get_value_as_int()
        minute = spinbutton.get_value_as_int()
        self.prefs.setDayStart(hour, minute)
        self.on_downloads_today_entry_changed(self.downloads_today_entry)

    def on_downloads_today_entry_changed(self, entry):
        if workers.noRunningWorkers() == 0:
            # do not update value if a download is occurring - it will mess it up!
            v = entry.get_text()
            try:
                v = int(v)
            except:
                v = 0
            if v < 0:
                v = 0
            self.prefs.resetDownloadsToday(v)
            sequences.setDownloadsToday(v)
            self.updateImageRenameExample()
        
    def on_stored_number_entry_changed(self, entry):
        if workers.noRunningWorkers() == 0:
            # do not update value if a download is occurring - it will mess it up!
            v = entry.get_text()
            try:
                # the displayed value of stored sequence no 1 more than actual value
                # so as not to confuse the user
                v = int(v) - 1
            except:
                v = 0
            if v < 0:
                v = 0
            self.prefs.stored_sequence_no = v
            sequences.setStoredSequenceNo(v)
            self.updateImageRenameExample()

    def on_response(self, dialog, arg):
        if arg==gtk.RESPONSE_CLOSE:
            self.prefs.backup_identifier = self.backup_identifier_entry.get_property("text")
        self.widget.destroy()

    def on_auto_startup_checkbutton_toggled(self, checkbutton):
        self.prefs.auto_download_at_startup = checkbutton.get_active()
        
    def on_auto_insertion_checkbutton_toggled(self, checkbutton):
        self.prefs.auto_download_upon_device_insertion = checkbutton.get_active()
        
    def on_auto_unmount_checkbutton_toggled(self, checkbutton):
        self.prefs.auto_unmount = checkbutton.get_active()
        
    def on_auto_exit_checkbutton_toggled(self, checkbutton):
        self.prefs.auto_exit = checkbutton.get_active()
        
    def on_autodetect_device_checkbutton_toggled(self, checkbutton):
        self.prefs.device_autodetection = checkbutton.get_active()
        self.updateDeviceControls()

    def on_autodetect_psd_checkbutton_toggled(self,  checkbutton):
        self.prefs.device_autodetection_psd = checkbutton.get_active()
        
    def on_backup_duplicate_overwrite_radiobutton_toggled(self,  widget):
        self.prefs.backup_duplicate_overwrite = widget.get_active()
            
    def on_backup_duplicate_skip_radiobutton_toggled(self,  widget):
        self.prefs.backup_duplicate_overwrite = not widget.get_active()
        
    def on_backup_error_radiobutton_toggled(self,  widget):
        self.prefs.backup_missing = config.REPORT_ERROR
        
    def on_backup_warning_radiobutton_toggled(self,  widget):
        self.prefs.backup_missing = config.REPORT_WARNING
    
    def on_backup_ignore_radiobutton_toggled(self,  widget):
        self.prefs.backup_missing = config.IGNORE
    
    def on_treeview_cursor_changed(self, tree):
        path, column = tree.get_cursor()
        self.notebook.set_current_page(path[0])

        
    def on_strip_characters_checkbutton_toggled(self, check_button):
        self.prefs.strip_characters = check_button.get_active()
        self.updateImageRenameExample()
        self.updateDownloadFolderExample()
        
    def on_indicate_download_error_checkbutton_toggled(self, check_button):
        self.prefs.indicate_download_error = check_button.get_active()
        
    def on_add_identifier_radiobutton_toggled(self, widget):
        if widget.get_active():
            self.prefs.download_conflict_resolution = config.ADD_UNIQUE_IDENTIFIER
        else:
            self.prefs.download_conflict_resolution = config.SKIP_DOWNLOAD

    def on_memory_card_radiobutton_toggled(self, widget):
        if widget.get_active():
            self.prefs.media_type = config.MEMORY_CARD
        else:
            self.prefs.media_type = config.PORTABLE_STORAGE_DEVICE
            

    def updateDeviceControls(self):
        """
        Sets sensitivity of image device controls
        """
        controls = [self.device_location_explanation_label,
                    self.device_location_label,
                    self.device_location_filechooser_button]

        if self.prefs.device_autodetection:
            for c in controls:
                c.set_sensitive(False)
            self.autodetect_psd_checkbutton.set_sensitive(True)
        else:
            for c in controls:
                c.set_sensitive(True)
            self.autodetect_psd_checkbutton.set_sensitive(False)
    
    def updateBackupControls(self):
        """
        Sets sensitivity of backup related widgets
        """
        
        if not self.backup_checkbutton.get_active():
            for c in self._backupControls:
                c.set_sensitive(False)

        else:
            for c in self._backupControls0:
                c.set_sensitive(True)
                
            self.updateBackupControlsAuto()

    def updateBackupControlsAuto(self):
        """
        Sets sensitivity of subset of backup related widgets
        """

        if self.auto_detect_backup_checkbutton.get_active():
            for c in self._backupControls1:
                c.set_sensitive(True)
            for c in self._backupControls2:
                c.set_sensitive(False)
        else:
            for c in self._backupControls1:
                c.set_sensitive(False)
            for c in self._backupControls2:
                c.set_sensitive(True)
            
    def on_auto_detect_backup_checkbutton_toggled(self, widget):
        self.prefs.backup_device_autodetection = widget.get_active()
        self.updateBackupControlsAuto()
        
    def on_backup_checkbutton_toggled(self, widget):
        self.prefs.backup_images = self.backup_checkbutton.get_active()
        self.updateBackupControls()

    def on_backup_identifier_entry_changed(self, widget):
        self.updateBackupExample()

    def on_backup_scan_folder_on_entry_changed(self, widget):
        self.updateBackupExample()        

    def updateBackupExample(self):
        path = os.path.join(config.MEDIA_LOCATION, "externaldrive1")
        path2 = os.path.join(config.MEDIA_LOCATION, "externaldrive2")

        path = os.path.join(path, self.backup_identifier_entry.get_text())
        path2 = os.path.join(path2, self.backup_identifier_entry.get_text())
        path = common.escape(path)
        path2 = common.escape(path2)
        self.example_backup_path_label.set_markup("<i>%s</i>\n<i>%s</i>" % (path,
                            path2))

        


class CopyPhotos(Thread):
    def __init__(self, thread_id, parentApp, fileRenameLock,  fileSequenceLock, statsLock,  downloadStats,  cardMedia = None):
        self.parentApp = parentApp
        self.thread_id = thread_id
        self.ctrl = True
        self.running = False
        # enable the capacity to block oneself with a lock
        # the lock will be first set when the thread begins
        # it will then be locked when the thread needs to be paused
        # releasing it will cause the code to restart from where it 
        # left off
        self.lock = Lock()
        
        self.fileRenameLock = fileRenameLock
        self.fileSequenceLock = fileSequenceLock
        self.statsLock = statsLock
        
        self.downloadStats = downloadStats
        
        self.hasStarted = False
        self.doNotStart = False
        
        self.cardMedia = cardMedia
        
        self.initializeDisplay(thread_id,  cardMedia)
        
        self.noErrors = self.noWarnings = 0
        
        Thread.__init__(self)

    def initializeDisplay(self, thread_id, cardMedia = None):

        if self.cardMedia:
            media_collection_treeview.addCard(thread_id, self.cardMedia.prettyName(), 
                self.cardMedia.sizeOfImages(), self.cardMedia.numberOfImages())

                
    def firstImage(self):
        """
        returns name, path and size of the first image
        """
        name, root, size,  modificationTime = self.cardMedia.firstImage()
        return root, name
        
    def handlePreferencesError(self,  e,  prefsFactory):
            print "Sorry,these preferences contain an error:"
            print prefsFactory.formatPreferencesForPrettyPrint()
            msg = str(e)
            print msg
        
    def initializeFromPrefs(self):
        """
        Setup thread so that user preferences are handled
        """
        self.prefs = self.parentApp.prefs

        self.imageRenamePrefsFactory = rn.ImageRenamePreferences(self.prefs.image_rename, self, 
                                                                 self.fileSequenceLock, sequences)
        try:
            self.imageRenamePrefsFactory.checkPrefsForValidity()
        except (rn.PrefValueInvalidError, rn.PrefLengthError, 
                rn.PrefValueKeyComboError,  rn.PrefKeyError), e:
            self.handlePreferencesError(e, self.imageRenamePrefsFactory)
            raise rn.PrefError
            
        try:
            self.subfolderPrefsFactory = rn.SubfolderPreferences(
                                                self.prefs.subfolder, self)    
        except (rn.PrefValueInvalidError, rn.PrefLengthError, 
                rn.PrefValueKeyComboError,  rn.PrefKeyError), e:
            self.handlePreferencesError(e, self.imageRenamePrefsFactory)
            raise rn.PrefError
                                                
        # copy this variable, as it is used heavily in the loop
        # and it is perhaps relatively expensive to read
        self.stripCharacters = self.prefs.strip_characters
        
        
    def run(self):
        """
        Copy photos from device to local drive, and if requested, backup
        
        1.  Should the image be downloaded?
            1.a  generate file name 
                1.a.1  generate sequence numbers if needed
                1.a.2  FIFO queue sequence numbers to indicate that they could 
                          potentially be used in a filename
            1.b  check to see if a file exists with the same name in the place it will 
                   be downloaded to
            1.c if it exisits, and unique identifiers are not being used:
                1.b.1  if using sequence numbers or letters, then potentially any of the 
                          sequence numbers in the queue could be used to make the filename
                    1.b.1.a  generate and check each filename using sequence numbers in the queue
                    1.b.1.b  if one of these filenames is unique, then image needs to be downloaded
                1.b.2  do not do not download

        
        2.  Download the image
            2.a  copy it to temporary folder (this takes time)
            2.b  is the file name still unique? Perhaps a new file was created with this name in the meantime
                   (either by another thread or another program)
                2.b.1  don't allow any other thread to rename a file
                2.b.2  check file name
                2.b.3  adding suffix if it is not unique, being careful not to overwrite any existing file with a suffix
                2.b.4  rename it to the "real"" name, effectively performing a mv
                2.b.5  allow other threads to rename files
        
        3.  Backup the image, using the same filename as was used when it was downloaded
            3.a  does a file with the same name already exist on the backup medium?
            3.b  if so, user preferences determine whether it should be overwritten or not
        """

        def cleanUp():
            """
            Cleanup functions that must be performed whether the thread exits 
            early or when it has completed its run.
            """

            # possibly delete any lingering files
            tf = os.listdir(tempWorkingDir)
            if tf:
                for f in tf:
                    os.remove(os.path.join(tempWorkingDir,  f))
                
            os.rmdir(tempWorkingDir)
            
            
        def logError(severity, problem, details, resolution=None):
            display_queue.put((log_dialog.addMessage, (self.thread_id, severity, problem, details, 
                            resolution)))
            if severity == config.WARNING:
                self.noWarnings += 1
            else:
                self.noErrors += 1


        def checkProblemWithImageNameGeneration(newName,  image,  problem):
            if not newName:
                # a serious problem - a filename should never be blank!
                logError(config.SERIOUS_ERROR,
                    "Image filename could not be generated",
                    "Source: %s\nProblem: %s" % (image, problem),
                    IMAGE_SKIPPED)                            
            elif problem:
                logError(config.WARNING, 
                    "Image filename could not be properly generated. Check to ensure there is sufficient image metadata.",
                    "Source: %s\nDestination: %s\nProblem: %s" % 
                    (image, newName, problem))
             
        def generateSubfolderAndFileName(image,  name,  needMetaDataToCreateUniqueImageName,  
                       needMetaDataToCreateUniqueSubfolderName):
            skipImage = False
            try:
                imageMetadata = metadata.MetaData(image)
            except IOError:
                logError(config.CRITICAL_ERROR, "Could not open image", 
                                "Source: %s" % image, 
                                IMAGE_SKIPPED)
                skipImage = True
            else:
                imageMetadata.readMetadata()
                if not imageMetadata.exifKeys() and (needMetaDataToCreateUniqueSubfolderName or 
                                                     (needMetaDataToCreateUniqueImageName and 
                                                     not addUniqueIdentifier)):
                    logError(config.SERIOUS_ERROR, "Image has no metadata", 
                                    "Metadata is essential for generating subfolders / image names.\nSource: %s" % image, 
                                    IMAGE_SKIPPED)
                    skipImage = True
                    newName = newFile = path = subfolder = None
                    
                else:
                    subfolder, problem = self.subfolderPrefsFactory.generateNameUsingPreferences(
                                                            imageMetadata, name, 
                                                            self.stripCharacters)
        
                    if problem:
                        logError(config.WARNING, 
                            "Subfolder name could not be properly generated. Check to ensure there is sufficient image metadata.",
                            "Subfolder: %s\nImage: %s\nProblem: %s" % 
                            (subfolder, image, problem))
                    
                    # pass the subfolder the image will go into, as this is needed to determine subfolder sequence numbers 
                    # indicate that sequences chosen should be queued
                    
                    newName, problem = self.imageRenamePrefsFactory.generateNameUsingPreferences(
                                                            imageMetadata, name, self.stripCharacters,  subfolder,  
                                                            sequencesPreliminary = True)
                                                            
                    path = os.path.join(baseDownloadDir, subfolder)
                    newFile = os.path.join(path, newName)
                    
                    if not newName:
                        skipImage = True
                    checkProblemWithImageNameGeneration(newName,  image,  problem)
                    
            return (skipImage,  imageMetadata,  newName,  newFile,  path,  subfolder)
        
        def downloadImage(path,  newFile,  newName,  originalName,  image,  imageMetadata,  subfolder):
            try:
                imageDownloaded = False
                if not os.path.isdir(path):
                    os.makedirs(path)
                
                nameUniqueBeforeCopy = True
                downloadNonUniqueFile = True
                
                
                # do a preliminary check to see if a file with the same name already exists
                if os.path.exists(newFile):
                    nameUniqueBeforeCopy = False
                    if not addUniqueIdentifier:
                        downloadNonUniqueFile = False
                        if usesSequenceElements:
                            # potentially, a unique image name could still be generated
                            # investigate this possibility
                            with self.fileSequenceLock:
                                for possibleName,  problem in self.imageRenamePrefsFactory.generateNameSequencePossibilities(imageMetadata, 
                                                                                                               originalName, self.stripCharacters,  subfolder):
#                                    print "checking",  possibleName,  "using",  originalName
                                    if possibleName:
                                        # no need to check for any problems here, it's just a temporary name
                                        possibleFile = os.path.join(path, possibleName)
                                        possibleTempFile = os.path.join(tempWorkingDir,  possibleName)
                                        if not os.path.exists(possibleFile) and not os.path.exists(possibleTempFile):
                                            downloadNonUniqueFile = True
                                            break

                                        
                    if self.prefs.indicate_download_error and not downloadNonUniqueFile:
                        logError(config.SERIOUS_ERROR, IMAGE_ALREADY_EXISTS,
                                "Source: %s\nDestination: %s" % (image, newFile),  IMAGE_SKIPPED)

                if nameUniqueBeforeCopy or downloadNonUniqueFile:
                    tempWorkingfile = os.path.join(tempWorkingDir, newName)
                    shutil.copy2(image, tempWorkingfile)
                    
                    with self.fileRenameLock:
                        doRename = True
                        if usesSequenceElements:
                            with self.fileSequenceLock:
                                # get a filename and use this as the "real" filename
                                newName, problem = self.imageRenamePrefsFactory.generateNameUsingPreferences(
                                                                imageMetadata, originalName, self.stripCharacters,  subfolder,  
                                                                sequencesPreliminary = False)
                            checkProblemWithImageNameGeneration(newName,  image,  problem)
                            if not newName:
                                # there was a serious error generating the filename
                                doRename = False                            
                            else:
                                newFile = os.path.join(path, newName)
                        # check if the file exists again
                        if os.path.exists(newFile):
                            if not addUniqueIdentifier:
                                doRename = False
                                if self.prefs.indicate_download_error:
                                    logError(config.SERIOUS_ERROR, IMAGE_ALREADY_EXISTS,
                                        "Source: %s\nDestination: %s" % (image, newFile),  IMAGE_SKIPPED) 
                            else:
                                # add  basic suffix to make the filename unique
                                name = os.path.splitext(newName)
                                suffixAlreadyUsed = True
                                while suffixAlreadyUsed:
                                    if newFile in duplicate_files:
                                        duplicate_files[newFile] +=  1
                                    else:
                                        duplicate_files[newFile] = 1
                                    identifier = '_%s' % duplicate_files[newFile]
                                    newName = name[0] + identifier + name[1]
                                    possibleNewFile = os.path.join(path,  newName)
                                    suffixAlreadyUsed = os.path.exists(possibleNewFile)

                                if self.prefs.indicate_download_error:
                                    logError(config.SERIOUS_ERROR, IMAGE_ALREADY_EXISTS,
                                        "Source: %s\nDestination: %s" % (image, newFile),
                                        "Unique identifier '%s' added" % identifier)
                                        
                                newFile = possibleNewFile
                                

                        if doRename:
                            os.rename(tempWorkingfile, newFile)
                            imageDownloaded = True
                            if usesSequenceElements:
                                with self.fileSequenceLock:
                                    self.imageRenamePrefsFactory.sequences.imageCopySucceeded()
                                    if usesStoredSequenceNo:
                                        self.prefs.stored_sequence_no += 1
                                        
                            with self.fileSequenceLock:
                                if self.prefs.incrementDownloadsToday():
                                    print "new day started"
                                    # a new day has started
                                    sequences.setDownloadsToday(0)
                    
            except IOError, (errno, strerror):
                # FIXME: is the lock released on an error here?!
                logError(config.SERIOUS_ERROR, 'Download copying error', 
                            "Source: %s\nDestination: %s\nError: %s %s" % (image, newFile, errno, strerror),
                            'The image was not copied.')

            except OSError, (errno, strerror):
                logError(config.CRITICAL_ERROR, 'Download copying error', 
                            "Source: %s\nDestination: %s\nError: %s %s" % (image, newFile, errno, strerror),
                        )
            
            if usesSequenceElements:
                if not imageDownloaded:
                    self.imageRenamePrefsFactory.sequences.imageCopyFailed()

                    
                
            return (imageDownloaded,  newName,  newFile)
            

        def backupImage(subfolder,  newName,  imageDownloaded,  newFile,  image):
            """ backup image to path(s) chosen by the user
            
            there are two scenarios: 
            (1) image has just been downloaded and should now be backed up
            (2) image was already downloaded on some previous occassion and should still be backed up, because it hasn't been yet
            (3) image has been backed up already (or at least, a file with the same name already exists)
            """
            
            try:
                for backupDir in self.parentApp.backupVolumes:
                    backupPath = os.path.join(backupDir, subfolder)
                    newBackupFile = os.path.join(backupPath,  newName)
                    copyBackup = True
                    if os.path.exists(newBackupFile):
                        # again, not thread safe
                        copyBackup = self.prefs.backup_duplicate_overwrite                                     
                        if self.prefs.indicate_download_error:
                            severity = config.SERIOUS_ERROR
                            problem = "Backup image already exists"
                            details = "Source: %s\nDestination: %s" % (image, newBackupFile) 
                            if copyBackup :
                                resolution = IMAGE_OVERWRITTEN
                            else:
                                resolution = IMAGE_SKIPPED
                            logError(severity, problem, details, resolution)

                    if copyBackup:
                        if imageDownloaded:
                            fileToCopy = newFile
                        else:
                            fileToCopy = image
                        if not os.path.isdir(backupPath):
                            # recreate folder structure in backup location
                            # cannot do os.makedirs(backupPath) - it gives bad results when using external drives
                            # we know backupDir exists 
                            # all the components of subfolder may not
                            folders = subfolder.split(os.path.sep)
                            folderToMake = backupDir 
                            for f in folders:
                                if f:
                                    folderToMake = os.path.join(folderToMake,  f)
                                    if not os.path.isdir(folderToMake):
                                        try:
                                            os.mkdir(folderToMake)
                                        except (errno, strerror):
                                            logError(config.SERIOUS_ERROR, 'Backing up error', 
                                                     "Destination directory could not be created\n%s\nError: %s %s" % (folderToMake,  errno,  strerror), 
                                                     )
                                    
                        shutil.copy2(fileToCopy,  newBackupFile)
                        
            except IOError, (errno, strerror):
                logError(config.SERIOUS_ERROR, 'Backing up error', 
                            "Source: %s\nDestination: %s\nError: %s %s" % (image, newBackupFile, errno, strerror),
                            'The image was not copied.')

            except OSError, (errno, strerror):
                logError(config.CRITICAL_ERROR, 'Backing up error', 
                            "Source: %s\nDestination: %s\nError: %s %s" % (image, newBackupFile, errno, strerror),
                        )            

        def notifyAndUnmount():
            if not self.cardMedia.volume:
                unmountMessage = ""
                notificationName = config.PROGRAM_NAME
            else:
                notificationName = self.cardMedia.volume.get_display_name()
                if self.prefs.auto_unmount:
                    self.cardMedia.volume.unmount(self.on_volume_unmount)
                    unmountMessage = "The device can now be safely removed"
                else:
                    unmountMessage = ""
            
            message = "%s images downloaded" % noImagesDownloaded
            if noImagesSkipped:
                message += "\n%s images skipped" % noImagesSkipped
            
            if unmountMessage:
                message = "%s\n%s"  % (message,  unmountMessage)
                
            if self.noWarnings:
                message = "%s\n%s warnings" % (message,  self.noWarnings)
            if self.noErrors:
                message = "%s\n%s errors" % (message,  self.noErrors)
                
            n = pynotify.Notification(notificationName,  message)
            n.show()            
        
        self.hasStarted = True

        display_queue.open('w')
        
        try:
            self.initializeFromPrefs()
        except rn.PrefError:
            logError(config.CRITICAL_ERROR, "Download cannot proceed", "There is an error in the program preferences.\nPlease check preferences, restart the program, and try again.")
            display_queue.close("rw")
            return
            
        
        #check for presence of backup meditum
        if self.prefs.backup_images:
            if self.prefs.backup_missing <> config.IGNORE:
                if not len(self.parentApp.backupVolumes):
                    if self.prefs.backup_missing == config.REPORT_ERROR:
                        e = config.SERIOUS_ERROR
                    else:
                        e = config.WARNING
                    logError(e,  "Backup device missing",  "No backup device was detected.")
                
        # Some images may not have metadata (this
        # is unlikely for images straight out of a 
        # camera, but it is possible for images that have been edited).  If
        # only non-dynamic components make up the rest of an image name 
        # (e.g. text specified by the user), then relying on metadata will 
        # likely produce duplicate names. 
        
        needMetaDataToCreateUniqueImageName = self.imageRenamePrefsFactory.needImageMetaDataToCreateUniqueName()
        
        # subfolder generation also need to be examined, but here the need is
        # not so exacting, since subfolders contain images, and naturally the
        # requirement to be unique is far more relaxed.  However if subfolder 
        # generation relies entirely on metadata, that is a problem worth
        # looking for
        needMetaDataToCreateUniqueSubfolderName = self.subfolderPrefsFactory.needMetaDataToCreateUniqueName()
        
        i = 0
        sizeDownloaded = noImagesDownloaded =  noImagesSkipped = 0
        
        sizeImages = float(self.cardMedia.sizeOfImages(humanReadable = False))
        noImages = self.cardMedia.numberOfImages()
        
        baseDownloadDir = self.prefs.download_folder
        #create a temporary directory in which to download the photos to
        #don't want to put it in system temp folder, as that is likely
        #to be on another partition and hence copying files from it
        #to the download folder will be slow!
        tempWorkingDir = tempfile.mkdtemp(prefix='rapid-tmp-', 
                                            dir=baseDownloadDir)
                                            
        IMAGE_SKIPPED = "Image skipped"
        IMAGE_OVERWRITTEN = "Image overwritten" # users can specify that duplicate backup files can be overwritten
        IMAGE_ALREADY_EXISTS = "Image already exists"
        
        addUniqueIdentifier = self.prefs.download_conflict_resolution == config.ADD_UNIQUE_IDENTIFIER
        usesSequenceElements = self.imageRenamePrefsFactory.usesSequenceElements()
        usesStoredSequenceNo = self.imageRenamePrefsFactory.usesTheSequenceElement(rn.STORED_SEQ_NUMBER)
        sequences. setUseOfSequenceElements(
            self.imageRenamePrefsFactory.usesTheSequenceElement(rn.SESSION_SEQ_NUMBER), 
            self.imageRenamePrefsFactory.usesTheSequenceElement(rn.SEQUENCE_LETTER))
        
        while i < noImages:
            if not self.running:
                self.lock.acquire()
                self.running = True
            
            if not self.ctrl:
                self.running = False
                cleanUp()
                display_queue.close("rw")
                return
            
            # get information about the image to deduce image name and path
            name, root, size,  modificationTime = self.cardMedia.images[i]
            image = os.path.join(root, name)
            
            skipImage,  imageMetadata,  newName,  newFile,  path,  subfolder = generateSubfolderAndFileName(
                       image,  name,  needMetaDataToCreateUniqueImageName,  
                       needMetaDataToCreateUniqueSubfolderName)

            if skipImage:
                noImagesSkipped += 1
            else:
                imageDownloaded, newName, newFile  = downloadImage(path,  newFile,  newName,  name,  image,  
                                                                   imageMetadata,  subfolder)

                if self.prefs.backup_images:
                    backupImage(subfolder,  newName,  imageDownloaded,  newFile,  image)

                if imageDownloaded:
                    noImagesDownloaded += 1
                else:
                    noImagesSkipped += 1
                try:
                    thumbnailType, thumbnail = imageMetadata.getThumbnailData()
                except:
                    logError(config.WARNING, "Image has no thumbnail", image)
                    thumbnail = Orientation = None
                else:
                    orientation = imageMetadata.orientation(missing=None)
                display_queue.put((image_hbox.addImage, (self.thread_id, thumbnail, orientation, image,  imageDownloaded)))
            
            sizeDownloaded += size
            percentComplete = (sizeDownloaded / sizeImages) * 100
            progressBarText = "%s of %s images copied" % (i + 1, noImages)
            display_queue.put((media_collection_treeview.updateProgress, (self.thread_id, percentComplete, progressBarText, size)))
            
            i += 1

        with self.statsLock:
            self.downloadStats.adjust(sizeDownloaded,  noImagesDownloaded,  noImagesSkipped,  self.noWarnings,  self.noErrors)

        # must manually delete these variables, or else the media cannot be unmounted (bug in pyexiv or exiv2)
        del self.subfolderPrefsFactory,  self.imageRenamePrefsFactory
        if 'imageMetadata' in dir(self):
            del imageMetadata
                
        notifyAndUnmount()
        display_queue.put((self.parentApp.notifyUserAllDownloadsComplete,()))
        display_queue.put((self.parentApp.resetSequences,()))

        cleanUp()
        display_queue.put((self.parentApp.exitOnDownloadComplete, ()))
        display_queue.close("rw")
        
        self.running = False
        if noImages:
            self.lock.release()
        
    def startStop(self):
        if self.isAlive():
            if self.running:
                self.running = False
            else:
                try:
                    self.lock.release()
    
                except thread_error:
                    print self.thread_id, "thread error"    
    
    def quit(self):
        """ 
        Quits the thread 
        
        A thread can be in one of four states:
        
        Not started (not alive, nothing to do)
        Started and actively running (alive)
        Started and paused (alive)
        Completed (not alive, nothing to do)
        """
        if self.hasStarted:
            if self.isAlive():            
                self.ctrl = False
                
                if not self.running:
                    released = False
                    while not released:
                        try:
                            self.lock.release()
                            released = True
                        except thread_error:
                            print "Could not release lock for thread", self.thread_id

    def on_volume_unmount(self,  data1,  data2):
        pass
            

class MediaTreeView(gtk.TreeView):
    """
    TreeView display of memory cards and associated copying progress.
    
    Assumes a threaded environment.
    """
    def __init__(self, parentApp):

        self.parentApp = parentApp
        # card name, size of images, number of images, copy progress, copy text
        self.liststore = gtk.ListStore(str, str, int, float, str)
        self.mapThreadToRow = {}

        gtk.TreeView.__init__(self, self.liststore)
        
        self.props.enable_search = False
        # make it impossible to select a row
        selection = self.get_selection()
        selection.set_mode(gtk.SELECTION_NONE)
        
        column0 = gtk.TreeViewColumn("Device", gtk.CellRendererText(), 
                                    text=0)
        self.append_column(column0)
        column1 = gtk.TreeViewColumn("Size", gtk.CellRendererText(), text=1)
        self.append_column(column1)
        
        column2 = gtk.TreeViewColumn("Download Progress", 
                                    gtk.CellRendererProgress(), value=3, text=4)
        self.append_column(column2)
        self.show_all()
        
    def addCard(self, thread_id, cardName, sizeImages, noImages, progress = 0.0,
                progressBarText = ''):
        if not progressBarText:
            progressBarText = "0 of %s images copied" % (noImages)
        
        # add the row, and get a temporary pointer to the row
        iter = self.liststore.append((cardName, sizeImages, noImages, 
                                                progress, progressBarText))
        
        self._setThreadMap(thread_id, iter)
        
        # adjust scrolled window height, based on row height and number of ready to start downloads
        if workers.noReadyToStartWorkers() >= 1:
            # please note, at program startup, self.rowHeight() will be less than it will be when already running
            # e.g. when starting with 3 cards, it could be 18, but when adding 2 cards to the already running program
            # (with one card at startup), it could be 21
            height = (workers.noReadyToStartWorkers() + 2) * (self.rowHeight())
            self.parentApp.media_collection_scrolledwindow.set_size_request(-1,  height)

        
    def removeCard(self, thread_id):
        iter = self._getThreadMap(thread_id)
        self.liststore.remove(iter)


    def _setThreadMap(self, thread_id, iter):
        """
        convert the temporary iter into a tree reference, which is 
        permanent
        """

        path = self.liststore.get_path(iter)
        treerowRef = gtk.TreeRowReference(self.liststore, path)
        self.mapThreadToRow[thread_id] = treerowRef
    
    def _getThreadMap(self, thread_id):
        """
        return the tree iter for this thread
        """
        
        treerowRef = self.mapThreadToRow[thread_id]
        path = treerowRef.get_path()
        iter = self.liststore.get_iter(path)
        return iter
    
    def updateProgress(self, thread_id, percentComplete, progressBarText, imageSize):
        
        iter = self._getThreadMap(thread_id)
        
        self.liststore.set_value(iter, 3, percentComplete)
        self.liststore.set_value(iter, 4, progressBarText)
        self.parentApp.updateOverallProgress(thread_id, imageSize,  percentComplete)
        

    def rowHeight(self):
        if not self.mapThreadToRow:
            return 0
        else:
            path = self.mapThreadToRow[0].get_path()
            col = self.get_column(0)
            return self.get_background_area(path, col)[3]

class ImageHBox(gtk.HBox):
    """
    Displays thumbnails of the images being downloaded
    """
    
    def __init__(self, parentApp):
        gtk.HBox.__init__(self)
        self.parentApp = parentApp
        self.padding = hd.CONTROL_IN_TABLE_SPACE / 2

        #create image used to lighten thumbnails
        self.white = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB,  False,  8,  width=100, height=100)
        #fill with white
        self.white.fill(0xffffffff)
        
        #load missing image 
        self.missingThumbnail = gtk.gdk.pixbuf_new_from_file_at_size(paths.share_dir('glade3/image-missing.svg'),  100,  100)
        
    def addImage(self, thread_id, thumbnail, orientation, filename,  imageDownloaded):
        """ 
        Add thumbnail
        
        Orientation indicates if the thumbnail needs to be rotated or not.
        """
        
        if not thumbnail:
            pixbuf = self.missingThumbnail
        else:
            try:
                pbloader = gdk.PixbufLoader()
                pbloader.write(thumbnail)
                # Get the resulting pixbuf and build an image to be displayed
                pixbuf = pbloader.get_pixbuf()
                pbloader.close()
                
            except:
                log_dialog.addMessage(thread_id, config.WARNING, 
                                'Thumbnail cannot be displayed', filename, 
                                'It may be corrupted')
                pixbuf = self.missingThumbnail

        if not pixbuf:
            log_dialog.addMessage(thread_id, config.WARNING, 
                            'Thumbnail cannot be displayed', filename, 
                            'It may be corrupted')
            pixbuf = self.missingThumbnail
        else:
            # rotate if necessary
            if orientation == 8:
                pixbuf = pixbuf.rotate_simple(gdk.PIXBUF_ROTATE_COUNTERCLOCKWISE)
    
        # scale to size
        pixbuf = common.scale2pixbuf(100, 100, pixbuf)
        if not imageDownloaded:
            # lighten it
            self.white.composite(pixbuf, 0, 0, pixbuf.props.width, pixbuf.props.height, 0, 0, 1.0, 1.0, gtk.gdk.INTERP_HYPER, 180)

        image = gtk.Image()
        image.set_from_pixbuf(pixbuf)
        
        self.pack_start(image, expand=False, padding=self.padding)
        image.show()
        
        # move viewport to display the latest image
        adjustment = self.parentApp.image_scrolledwindow.get_hadjustment()
        adjustment.set_value(adjustment.upper)

        
class LogDialog(gnomeglade.Component):
    """
    Displays a log of errors, warnings or other information to the user
    """
    
    def __init__(self, parentApp):
        """
        Initialize values for log dialog, but do not display.
        """
        
        gnomeglade.Component.__init__(self, 
                                    paths.share_dir(config.GLADE_FILE), 
                                    "logdialog")
                                    
        
        self.widget.connect("destroy", self.on_logdialog_destroy)
        
        self.parentApp = parentApp
        self.log_textview.set_cursor_visible(False)
        self.textbuffer = self.log_textview.get_buffer()
        
        self.problemTag = self.textbuffer.create_tag(weight=pango.WEIGHT_BOLD)
        self.resolutionTag = self.textbuffer.create_tag(style=pango.STYLE_ITALIC)
        
    def addMessage(self, thread_id, severity, problem, details, resolution):
        if severity in [config.CRITICAL_ERROR, config.SERIOUS_ERROR]:
            self.parentApp.error_image.show()
        elif severity == config.WARNING:
            self.parentApp.warning_image.show()
        
        iter = self.textbuffer.get_end_iter()
        self.textbuffer.insert_with_tags(iter, problem +"\n", self.problemTag)
        iter = self.textbuffer.get_end_iter()
        self.textbuffer.insert(iter, details + "\n")
        if resolution:
            iter = self.textbuffer.get_end_iter()
            self.textbuffer.insert_with_tags(iter, resolution +"\n", self.resolutionTag)
            
        iter = self.textbuffer.get_end_iter()
        self.textbuffer.insert(iter, "\n")
        
        # move viewport to display the latest message
        adjustment = self.log_scrolledwindow.get_vadjustment()
        adjustment.set_value(adjustment.upper)
        
        
    def on_logdialog_response(self, dialog, arg):
        if arg == gtk.RESPONSE_CLOSE:
            pass
        self.parentApp.error_image.hide()
        self.parentApp.warning_image.hide()
        self.parentApp.prefs.show_log_dialog = False
        self.widget.hide()

        
    def on_logdialog_destroy(self, dialog):
        self.on_logdialog_response(dialog, gtk.RESPONSE_CLOSE)
        dialog.emit_stop_by_name("destroy")
        return True


class RapidApp(gnomeglade.GnomeApp,  dbus.service.Object): 
    def __init__(self,  bus, path, name): 
        
        dbus.service.Object.__init__ (self, bus, path, name)
        self.running = False
        
        gladefile = paths.share_dir(config.GLADE_FILE)
        gnomeglade.GnomeApp.__init__(self, "rapid", __version__, gladefile, "rapidapp")


        # notifications
        self.displayDownloadSummaryNotification = False
        self.initPyNotify()
        
        self.prefs = RapidPreferences()
        self.prefs.notify_add(self.on_preference_changed)
        
        self.testing = False
        if self.testing:
            self.setTestingEnv()
            
#        sys.exit(0)

        self.widget.show()

        displayPreferences = self.checkForUpgrade(__version__)
        self.prefs.program_version = __version__
        

        self._resetDownloadInfo()
        self.statusbar_context_id = self.rapid_statusbar.get_context_id("progress")
        
        self.error_image.hide()
        self.warning_image.hide()
        
        
        # display download information using threads
        global media_collection_treeview, image_hbox, log_dialog
        global download_queue, image_queue, log_queue
        global workers

        #track files that should have a suffix added to them
        global duplicate_files
        
        # control sequence numbers and letters
        global sequences

        duplicate_files = {}
        
        downloadsToday = self.prefs.getAndMaybeResetDownloadsToday()
        sequences = rn.Sequences(downloadsToday,  self.prefs.stored_sequence_no)
        
        self.downloadStats = DownloadStats()
        
        # set the number of seconds gap with which to measure download time remaing 
        self.downloadTimeGap = 3

        #locks for threadsafe file downloading and stats gathering
        self.fileRenameLock = Lock()
        self.fileSequenceLock = Lock()
        self.statsLock = Lock()

        # log window, in dialog format
        # used for displaying download information to the user
        
        log_dialog = LogDialog(self)


        self.volumeMonitor = None
        if self.usingVolumeMonitor():
            self.startVolumeMonitor()
        
       
        # set up tree view display 
        media_collection_treeview = MediaTreeView(self)        

        self.media_collection_vbox.pack_start(media_collection_treeview)
        
        #thumbnail display
        image_hbox = ImageHBox(self)
        self.image_viewport.add(image_hbox)
        self.image_viewport.modify_bg(gtk.STATE_NORMAL, gdk.color_parse("white"))
        self.set_display_thumbnails(self.prefs.display_thumbnails)
        
        self.backupVolumes = {}

        self._setupDownloadbutton()
        
        #status bar progress bar
        self.download_progressbar = gtk.ProgressBar()
        self.download_progressbar.set_size_request(150, -1)
        self.download_progressbar.show()
        self.download_progressbar_hbox.pack_start(self.download_progressbar, expand=False, 
                                        fill=0)
        

        # menus
        self.menu_resequence.set_sensitive(False)
        self.menu_display_thumbnails.set_active(self.prefs.display_thumbnails)
        self.menu_clear.set_sensitive(False)
        
        self.download_folders_display_label.hide()

        
        self.setupAvailableImageAndBackupMedia()

        #adjust viewport size for displaying media
        #this is important because the code in MediaTreeView.addCard() is inaccurate at program startup
        
        height = self.media_collection_viewport.size_request()[1]
        self.media_collection_scrolledwindow.set_size_request(-1,  height)
        
        self.download_button.grab_focus()
        
        if displayPreferences:
            PreferencesDialog(self)
        elif self.prefs.auto_download_at_startup and workers.noReadyToStartWorkers() > 0:
            self.startDownload()

    

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
            self.main()
            self.running = False
            
    def setTestingEnv(self):
        self.prefs.program_version = '0.0.8~b7'
        r = ['Date time', 'Image date', 'YYYYMMDD', 'Text', '-', '', 'Date time', 'Image date', 'HHMM', 'Text', '-', '', 'Session number', '1', 'Three digits', 'Text', '-iso', '', 'Metadata', 'ISO', '', 'Text', '-f', '', 'Metadata', 'Aperture', '', 'Text', '-', '', 'Metadata', 'Focal length', '', 'Text', 'mm-', '', 'Metadata', 'Exposure time', '', 'Filename', 'Extension', 'lowercase']
        self.prefs.image_rename = r
        
    
    def checkForUpgrade(self,  runningVersion):
        """ Checks if the running version of the program is different from the version recorded in the preferences.
        
        If the version is different, then the preferences are checked to see whether they should be upgraded or not.
        
        returns True if program preferences window should be opened """
        
        displayPrefs = upgraded = False
        
        previousVersion = self.prefs.program_version
        if previousVersion:
            # the program has been run previously for this user
        
            pv = common.pythonifyVersion(previousVersion)
            rv = common.pythonifyVersion(runningVersion)
            
            title = config.PROGRAM_NAME
            imageRename = subfolder = None
            
            if pv != rv:
                if pv > rv:
                    prefsOk = rn.checkPreferencesForValidity(self.prefs.image_rename,  self.prefs.subfolder)
                        
                    msg = "A newer version of this program was previously run on this computer.\n\n"
                    if prefsOk:
                        msg += "Program preferences appear to be valid, but please check them to ensure correct operation."
                    else:
                        msg += "Sorry, some preferences are invalid and will be reset."
                    print "Warning: %s" % msg
                    misc.run_dialog(title, msg)
                    displayPrefs = True
                
                else:
                    print "This version of the program is newer than the previously run version. Checking preferences."
                    if True:
    #                if rn.checkPreferencesForValidity(self.prefs.image_rename,  self.prefs.subfolder,  previousVersion):
                        upgraded,  imageRename,  subfolder = rn.upgradePreferencesToCurrent(self.prefs.image_rename,  self.prefs.subfolder,  previousVersion)
                        if upgraded:
                            self.prefs.image_rename = imageRename
                            self.prefs.subfolder = subfolder
                            print "Preferences were modified."
                            msg = 'This version of the program uses different preferences than the old version. Your preferences have been updated.\n\nPlease check them to ensure correct operation.'
                            misc.run_dialog(title,  msg)
                            displayPrefs = True
                        else:
                            print "No preferences needed to be changed."
                    else:
                        msg = 'This version of the program uses different preferences than the old version. Some of your previous preferences were invalid, and could not be updated. They will be reset.'
                        misc.run_dialog(title,  msg)
                        displayPrefs = True

        return displayPrefs

    def initPyNotify(self):
        if not pynotify.init("TestCaps"):
            print "Problem using pynotify."
            sys.exit(1)

        capabilities = {'actions':  False,
            'body':  False,
            'body-hyperlinks': False,
            'body-images': False,
            'body-markup': False,
            'icon-multi': False,
            'icon-static': False,
            'sound': False,
            'image/svg+xml': False,
            'append':  False}

        caps = pynotify.get_server_caps ()
        if caps is None:
            print "Failed to receive pynotify server capabilities."
            sys.exit (1)

        for cap in caps:
            capabilities[cap] = True

        info = pynotify.get_server_info()
    
    def usingVolumeMonitor(self):
        """
        Returns True if programs needs to use gnomevfs volume monitor
        """
        
        return (self.prefs.device_autodetection or 
                (self.prefs.backup_images and 
                self.prefs.backup_device_autodetection
                ))
        
    
    def startVolumeMonitor(self):
        if not self.volumeMonitor:
            self.volumeMonitor = gnomevfs.VolumeMonitor()
            self.volumeMonitor.connect("volume-mounted", self.on_volume_mounted)
            self.volumeMonitor.connect("volume-unmounted", self.on_volume_unmounted)
    
    def displayBackupVolumes(self):
        """
        Create a message to be displayed to the user showing which backup volumes will be used
        """
        message =  ''
        
        paths = self.backupVolumes.keys()
        i = 0
        v = len(paths)
        prefix = ''
        for b in paths:
            if v > 1:
                if i < (v -1)  and i > 0:
                    prefix = ', '
                elif i == (v - 1) :
                    prefix = ' and '
            i += 1
            message = "%s%s'%s'" % (message,  prefix, self.backupVolumes[b].get_display_name())
        
        if v > 1:
            message = "Using backup devices %s" % message
        elif v == 1:
            message = "Using backup device %s"  % message
        else:
            message = "No backup devices detected"
            
        return message
        
    def searchForPsd(self):
        """
        Check to see if user preferences are to automatically search for Portable Storage Devices or not
        """
        return self.prefs.device_autodetection_psd and self.prefs.device_autodetection
        
    def on_volume_mounted(self, monitor, volume):
        """
        callback run when gnomevfs indicates a new volume
        has been mounted
        """
        
        uri = volume.get_activation_uri()
#        print "%s has been mounted" % uri
        path = gnomevfs.get_local_path_from_uri(uri)

        isBackupVolume = self.checkIfBackupVolume(path)
                    
        if isBackupVolume:
            backupPath = os.path.join(path,  self.prefs.backup_identifier)
            if path not in self.backupVolumes:
                self.backupVolumes[backupPath] = volume
                self.rapid_statusbar.push(self.statusbar_context_id, self.displayBackupVolumes())

        elif media.isImageMedia(path,  self.searchForPsd()):
            cardMedia = CardMedia(path, volume)
            i = workers.getNextThread_id()
            workers.append(CopyPhotos(i, self, self.fileRenameLock, self.fileSequenceLock, self.statsLock,  self.downloadStats,  cardMedia))
            self.setDownloadButtonSensitivity()
            
            if self.prefs.auto_download_upon_device_insertion:
                self.startDownload()
            
    def on_volume_unmounted(self, monitor, volume):
        """
        callback run when gnomevfs indicates a volume
        has been unmounted
        """
        
        uri = volume.get_activation_uri()
        path = gnomevfs.get_local_path_from_uri(uri)

        # three scenarios -
        # volume is waiting to have images downloaded
        # images are being downloaded from volume
        # images finished downloading from volume
        
        # first scenario
        for w in workers.getReadyToStartWorkers():
            if w.cardMedia.volume == volume:
                media_collection_treeview.removeCard(w.thread_id)
                workers.disableWorker(w.thread_id)
                
        # remove backup volumes
        backupPath = os.path.join(path,  self.prefs.backup_identifier)
        if backupPath in self.backupVolumes:
            del self.backupVolumes[backupPath]
            self.rapid_statusbar.push(self.statusbar_context_id, self.displayBackupVolumes())

        
    
    def clearCompletedDownloads(self):
        """
        clears the display of completed downloads
        """
        for w in workers.getFinishedWorkers():
            media_collection_treeview.removeCard(w.thread_id)
        
    def clearNotStartedDownloads(self):
        """
        Clears the display of the download and instructs the thread not to run
        """
        for w in workers.getReadyToStartWorkers():
            media_collection_treeview.removeCard(w.thread_id)
            workers.disableWorker(w.thread_id)
    
    def checkIfBackupVolume(self,  path):
        """
        Checks to see if backups are enabled and path represents a valid backup location
        
        Checks against user preferences.
        """
        if self.prefs.backup_images:
            if self.prefs.backup_device_autodetection:
                if media.isBackupMedia(path, self.prefs.backup_identifier):
                    return True
            elif path == self.prefs.backup_location:
                # user manually specified the path
                return True
        return False
    
    def setupAvailableImageAndBackupMedia(self):
        """
        Creates a list of CardMedia
        
        Removes any image media that are currently not downloaded, 
        or finished downloading
        """
        
        self.clearNotStartedDownloads()
        
        cardMediaList = []
        self.backupVolumes = {}
        
        if self.usingVolumeMonitor():
            # either using automatically detected backup devices
            # or image devices
            
            # ugly hack to work around bug where gnomevfs.get_local_path_from_uri(uri) causes a crash
            mediaLocation = "file://" + config.MEDIA_LOCATION
            
            for volume in self.volumeMonitor.get_mounted_volumes():
                uri = volume.get_activation_uri()
                if uri.find(mediaLocation) == 0:
                    path = gnomevfs.get_local_path_from_uri(uri)
                    if path.startswith(config.MEDIA_LOCATION):
                        isBackupVolume = self.checkIfBackupVolume(path)
                        
                        if isBackupVolume:
                            backupPath = os.path.join(path,  self.prefs.backup_identifier)
                            self.backupVolumes[backupPath] = volume
                        elif self.prefs.device_autodetection and media.isImageMedia(path, self.searchForPsd()):
                            cardMediaList.append(CardMedia(path, volume))
                        
        
        if not self.prefs.device_autodetection:
            # user manually specified the path from which to download images
            path = self.prefs.device_location
            if path:
                cardMedia = CardMedia(path)
                if cardMedia.numberOfImages() > 0:
                    cardMediaList.append(cardMedia)
                    
        if self.prefs.backup_images:
            if not self.prefs.backup_device_autodetection:
                # user manually specified backup location
                self.backupVolumes[self.prefs.backup_location] = None
                self.rapid_statusbar.push(self.statusbar_context_id, '')
            else:
                self.rapid_statusbar.push(self.statusbar_context_id, self.displayBackupVolumes())
                
        else:
            self.rapid_statusbar.push(self.statusbar_context_id, '')
        
        # add each memory card / other device to the list of threads
        j = workers.getNextThread_id()

        for i in range(j, j + len(cardMediaList)):
            cardMedia = cardMediaList[i - j]
            workers.append(CopyPhotos(i, self, self.fileRenameLock, self.fileSequenceLock, self.statsLock,self.downloadStats, cardMedia))
        
        self.setDownloadButtonSensitivity()
        
    def _setupDownloadbutton(self):
    
        self.download_hbutton_box = gtk.HButtonBox()
        self.download_button_is_download = True
        self.download_button = gtk.Button() 
        self.download_button.set_use_underline(True)
        self._set_download_button()
        self.download_button.connect('clicked', self.on_download_button_clicked)
        self.download_hbutton_box.set_layout(gtk.BUTTONBOX_START)
        self.download_hbutton_box.pack_start(self.download_button)
        self.download_hbutton_box.show_all()
        self.buttons_hbox.pack_start(self.download_hbutton_box, 
                                    padding=hd.WINDOW_BORDER_SPACE)
                                    
        self.setDownloadButtonSensitivity()

    
    def set_display_thumbnails(self, value):
        if value:
            self.image_scrolledwindow.show_all()
        else:
            self.image_scrolledwindow.hide()

    
    def _resetDownloadInfo(self):
        self.startTime = None
        self.totalDownloadSize = self.totalDownloadedSoFar = 0
        self.totalDownloadSizeThisRun = self.totalDownloadedSoFarThisRun = 0 
    
    def startOrResumeWorkers(self):
            
        # take into account any newly added cards
        for w in workers.getReadyToStartWorkers():
            size = w.cardMedia.sizeOfImages(humanReadable = False)
            self.totalDownloadSize += size

##        if self.totalDownloadedSoFar > 0:
##            # the download must have been paused, so must recalculate download 
##            # times
        self.totalDownloadSizeThisRun = self.totalDownloadSize - self.totalDownloadedSoFar
        self.totalDownloadedSoFarThisRun = 0
            
        self.startTime = time.time()
        self.timeStatusBarUpdated = self.startTime

        self.timeMark = self.startTime
        self.sizeMark = 0
        self.timeRemaining = None
        
        # resume any paused workers
        for w in workers.getPausedWorkers():
            w.startStop()
            
        #start any new workers
        workers.startWorkers()
    

    def on_unmount(self, *args):
        pass
        
    def updateOverallProgress(self, thread_id, imageSize,  percentComplete):
        """
        Updates progress bar and status bar text with time remaining
        to download images
        """
                
        self.totalDownloadedSoFar += imageSize
        self.totalDownloadedSoFarThisRun += imageSize
        
        fraction = self.totalDownloadedSoFar / float(self.totalDownloadSize)
        
        self.download_progressbar.set_fraction(fraction)        
        
        if percentComplete == 100.0:
            self.menu_clear.set_sensitive(True)

        if self.downloadComplete():
            # finished all downloads
            self.rapid_statusbar.push(self.statusbar_context_id, "")
            self.download_button_is_download = True
            self._set_download_button()
            self.setDownloadButtonSensitivity()
    
        else:
            now = time.time()
            
            if now > (self.downloadTimeGap + self.timeMark):
                amtTime = now - self.timeMark
                self.timeMark = now
                amtDownloaded = self.totalDownloadedSoFarThisRun - self.sizeMark
                self.sizeMark = self.totalDownloadedSoFarThisRun
            
                timefraction = amtDownloaded / amtTime
                amtToDownload = float(self.totalDownloadSizeThisRun) - self.totalDownloadedSoFarThisRun
                
                self.timeRemaining = amtToDownload / timefraction
                self.downloadSpeed = "%1.1fMB/s" % (amtDownloaded / 1048576 / amtTime)
                
            
                secs =  int(self.timeRemaining)
                
                if secs == 0:
                    message = ""
                elif secs == 1:
                    message = "About 1 second remaining"
                elif secs < 60:
                    message = "About %i seconds remaining" % secs 
                elif secs == 60:
                    message = "About 1 minute remaining" 
                else:
                    message = "About %i:%02i minutes remaining" % (secs / 60, secs % 60)
                
                self.rapid_statusbar.push(self.statusbar_context_id, message)
                self.speed_label.set_text(self.downloadSpeed)
    
    def resetSequences(self):
        if self.downloadComplete():
            sequences.reset(self.prefs.getDownloadsToday(),  self.prefs.stored_sequence_no)
    
    def notifyUserAllDownloadsComplete(self):
        """ Possibly notify the user all downloads are complete using libnotify
        
        Reset progress bar info"""
        
        if self.downloadComplete():
            if self.displayDownloadSummaryNotification:
                message = "All downloads complete\n%s images downloaded" % self.downloadStats.noImagesDownloaded
                if self.downloadStats.noImagesSkipped:
                    message = "%s\n%s images skipped" % (message,  self.downloadStats.noImagesSkipped)
                if self.downloadStats.noWarnings:
                    message = "%s\n%s warnings" % (message,  self.downloadStats.noWarnings)
                if self.downloadStats.noErrors:
                    message = "%s\n%s errors" % (message,  self.downloadStats.noErrors)
                n = pynotify.Notification(config.PROGRAM_NAME,  message)
                n.show()
                self.displayDownloadSummaryNotification = False # don't show it again unless needed
                self.downloadStats.clear()
            self._resetDownloadInfo()
            self.speed_label.set_text('         ')
                
    def exitOnDownloadComplete(self):
        if self.downloadComplete():
            if self.prefs.auto_exit:
                if not (self.downloadStats.noErrors or self.downloadStats.noWarnings):                
                    self.quit()
    
    def downloadComplete(self):
        return self.totalDownloadedSoFar == self.totalDownloadSize

    def setDownloadButtonSensitivity(self):
        isSensitive = workers.firstWorkerReadyToStart()
        
        if isSensitive:
            self.download_button.props.sensitive = True
            self.menu_download_pause.props.sensitive = True
        else:
            self.download_button.props.sensitive = False
            self.menu_download_pause.props.sensitive = False
            
        return isSensitive
        

        
    def on_rapidapp_destroy(self, widget):
        """Called when the application is going to quit"""
        workers.quitAllWorkers()

        self.flushevents() # perhaps this will eliminate thread-related shutdown lockups?
        
        display_queue.close("w")


    def on_menu_clear_activate(self, widget):
        self.clearCompletedDownloads()
        widget.set_sensitive(False)
        
    def on_menu_report_problem_activate(self,  widget):
        webbrowser.open("https://bugs.launchpad.net/rapid") 
        
    def on_menu_get_help_online_activate(self,  widget):
        webbrowser.open("http://www.damonlynch.net/rapid/help.html") 

    def on_menu_donate_activate(self,  widget):
        webbrowser.open("http://www.damonlynch.net/rapid/donate.html") 

    def on_menu_preferences_activate(self, widget):
        """ Sets preferences for the application using dialog window """

        PreferencesDialog(self)
        
    def on_menu_log_window_toggled(self, widget):
        active = widget.get_active()
        self.prefs.show_log_dialog = active
        if active:
            log_dialog.widget.show()
        else:
            log_dialog.widget.hide()

    def on_menu_display_thumbnails_toggled(self, check_button):
        self.prefs.display_thumbnails = check_button.get_active()        

    def on_menu_about_activate(self, widget):
        """ Display about dialog box """

        about = gtk.glade.XML(paths.share_dir(config.GLADE_FILE), "about").get_widget("about")
        about.set_property("name", config.PROGRAM_NAME)
        about.set_property("version", __version__)
        about.run()
        about.destroy()       

    def _set_download_button(self):
        """
        Sets download button to appropriate state
        """
        if self.download_button_is_download:
            #note the space at the end of the label, need it to meet HIG! :(
            self.download_button.set_label("_Download ")
            self.download_button.set_image(gtk.image_new_from_stock(
                                                gtk.STOCK_CONVERT,
                                                gtk.ICON_SIZE_BUTTON))        
        else:
            # button should indicate paused state
            self.download_button.set_image(gtk.image_new_from_stock(
                                                gtk.STOCK_MEDIA_PAUSE,
                                                gtk.ICON_SIZE_BUTTON))
            #note the space at the end of the label, need it to meet HIG! :(
            self.download_button.set_label("_Pause ")
            
    def on_menu_download_pause_activate(self, widget):
        self.on_download_button_clicked(widget)
        

    def startDownload(self):
        self.startOrResumeWorkers()
        if workers.noRunningWorkers() > 1:
            self.displayDownloadSummaryNotification = True
        # set button to display Pause
        self.download_button_is_download = False
        self._set_download_button()
        
    def pauseDownload(self):
        for w in workers.getWorkers():
            w.startStop()
        # set button to display Download
        self.download_button_is_download = True
        self._set_download_button()
        
    def on_download_button_clicked(self, widget):
        """
        Handle download button click.
        
        Button is in one of two states: download, or pause.
        
        If download, a click indicates to start or resume a download run.
        If pause, a click indicates to pause all running downloads.
        """
        if self.download_button_is_download:
            self.startDownload()
        else:
            self.pauseDownload()
            
    def on_preference_changed(self, key, value):
#        if self.testing:
#            print "on_preference_changed",  key,  value

        if key == 'display_thumbnails':
            self.set_display_thumbnails(value)
        elif key == 'media_type':
            self.set_media_device_display(value)
        elif key == 'show_log_dialog':
            self.menu_log_window.set_active(value)
        elif key in ['device_autodetection', 'device_autodetection_psd', 'backup_images',  'device_location',
                      'backup_device_autodetection', 'backup_location' ]:
            if self.usingVolumeMonitor():
                self.startVolumeMonitor()
            self.setupAvailableImageAndBackupMedia()

    def on_error_eventbox_button_press_event(self,  widget,  event):
        self.prefs.show_log_dialog = True
        log_dialog.widget.show()

class DownloadStats:
    def __init__(self):
        self.clear()
        
    def adjust(self, size,  noImagesDownloaded,  noImagesSkipped,  noWarnings,  noErrors):
        self.downloadSize += size
        self.noImagesDownloaded += noImagesDownloaded
        self.noImagesSkipped += noImagesSkipped
        self.noWarnings += noWarnings
        self.noErrors += noErrors
        
    def clear(self):
        self.noImagesDownloaded = self.noImagesSkipped = 0
        self.downloadSize = 0
        self.noWarnings = self.noErrors = 0
        
def programStatus():
    print "Goodbye"

        
def start ():
    atexit.register(programStatus)
    
    gdk.threads_init()
    display_queue.open("rw")
    tube.tube_add_watch(display_queue, updateDisplay)
    gdk.threads_enter()

    # run only a single instance of the application 
    bus = dbus.SessionBus ()
    request = bus.request_name (config.DBUS_NAME, dbus.bus.NAME_FLAG_DO_NOT_QUEUE)
    if request != dbus.bus.REQUEST_NAME_REPLY_EXISTS:
        app = RapidApp (bus, '/', config.DBUS_NAME)
    else:
        print "%s is already running" % config.PROGRAM_NAME
        object = bus.get_object (config.DBUS_NAME, "/")
        app = dbus.Interface (object, config.DBUS_NAME)
    
    app.start()
    gdk.threads_leave()    

if __name__ == "__main__":
    start()
