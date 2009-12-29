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

#needed for python 2.5, unneeded for python 2.6
from __future__ import with_statement 

import sys
import os
import shutil
import time
import datetime
import atexit
import tempfile
import webbrowser
import operator

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

try:
    import gio
    using_gio = True
except ImportError:
    import gnomevfs
    using_gio = False


import prefs
import paths
import gnomeglade

from optparse import OptionParser

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

from common import Configi18n
global _
_ = Configi18n._

#Translators: if neccessary, for guidance in how to translate this program, you may see http://damonlynch.net/translate.html 
PROGRAM_NAME = _('Rapid Photo Downloader')

def today():
    return datetime.date.today().strftime('%Y-%m-%d')



def cmd_line(msg):    
    if verbose:
        print msg

exiting = False

def updateDisplay(display_queue):

    try:
        if display_queue.size() != 0:
            call, args = display_queue.get()
            if not exiting:
                call(*args)
#            else do not update display
        else:
            sys.stderr.write("Empty display queue!\n")
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

job_code = None
need_job_code = False

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
        set so a worker will not run, or if it is running, make it quit and therefore complete
        """
        
        self._workers[thread_id].manuallyDisabled = True
        if self._workers[thread_id].hasStarted:
            self._workers[thread_id].quit()
            
        else:
            self._workers[thread_id].doNotStart = True
        
    def _isReadyToStart(self, w):
        """
        Returns True if the worker is ready to start
        and has not been disabled
        """
        return not w.hasStarted and not w.doNotStart and not w.manuallyDisabled
        
    def _isReadyToDownload(self, w):
       return w.scanComplete and not w.downloadStarted and not w.doNotStart and w.isAlive() and not w.manuallyDisabled
       
    def _isDownloading(self,  w):
        return w.downloadStarted and w.isAlive() and not w.downloadComplete
        
    def _isFinished(self, w):
        """
        Returns True if the worker has finished running
        
        It does not signify it finished a download
        """
        
        return (w.hasStarted and not w.isAlive()) or w.manuallyDisabled
                
    def completedDownload(self,  w):
        return w.completedDownload
    
    def firstWorkerReadyToStart(self):
        for w in self._workers:
            if self._isReadyToStart(w):
                return w
        return None

    def firstWorkerReadyToDownload(self):
        for w in self._workers:
            if self._isReadyToDownload(w):
                return w
        return None

    def startWorkers(self):
        for w in self.getReadyToStartWorkers():
            w.start()

    def startDownloadingWorkers(self):
        for w in self.getReadyToDownloadWorkers():
            w.startStop()        
            
    def quitAllWorkers(self):
        global exiting 
        exiting = True
        for w in self._workers:
            w.quit()

    def getWorkers(self):
        for w in self._workers:
            yield w
            
    def getNonFinishedWorkers(self):
        for w in self._workers:
            if not self._isFinished(w):
                yield w
                
    def getStartedWorkers(self):
        for w in self._workers:
            if w.hasStarted:
                yield w
    
    def getReadyToStartWorkers(self):
        for w in self._workers:
            if self._isReadyToStart(w):
                yield w

    def getReadyToDownloadWorkers(self):
        for w in self._workers:
            if self._isReadyToDownload(w):
                yield w
                
    def getNotDownloadingWorkers(self):
        for w in self._workers:
            if w.hasStarted and not w.downloadStarted:
                yield w

    def noReadyToStartWorkers(self):
        n = 0
        for w in self._workers:
            if self._isReadyToStart(w):
                n += 1
        return n
        
    def noReadyToDownloadWorkers(self):
        n = 0
        for w in self._workers:
            if self._isReadyToDownload(w):
                n += 1
        return n
        
    def getRunningWorkers(self):
        for w in self._workers:
            if w.hasStarted and w.isAlive():
                yield w
                
    def getDownloadingWorkers(self):
        for w in self._workers:
            if self._isDownloading(w):
                yield w
        
                
    def getPausedWorkers(self):
        for w in self._workers:
            if w.hasStarted and not w.running:
                yield w            

    def getPausedDownloadingWorkers(self):
        for w in self._workers:
            if w.downloadStarted and not w.running:
                yield w            

    def getWaitingForJobCodeWorkers(self):
        for w in self._workers:
            if w.waitingForJobCode:
                yield w
    
    def getFinishedWorkers(self):
        for w in self._workers:
            if self._isFinished(w):
                yield w
    
    def noDownloadingWorkers(self):
        i = 0
        for w in self._workers:
            if self._isDownloading(w):
                i += 1
        return i

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
            print "Volume / source:",  w.cardMedia.prettyName(limit=0)
            print "Do not start:", w.doNotStart
            print "Started:", w.hasStarted
            print "Running:", w.running
            print "Scan completed:",  w.scanComplete
            print "Download started:",  w.downloadStarted
            print "Download completed:",  w.downloadComplete
            print "Finished:", self._isFinished(w)
            print "Alive:",  w.isAlive()
            print "Manually disabled:",  w.manuallyDisabled,  "\n"

                
        
workers = ThreadManager()

class RapidPreferences(prefs.Preferences):
    defaults = {
        "program_version": prefs.Value(prefs.STRING, ""),
        "download_folder":  prefs.Value(prefs.STRING, 
                                        getDefaultPhotoLocation()),
        "subfolder": prefs.ListValue(prefs.STRING_LIST, rn.DEFAULT_SUBFOLDER_PREFS),
        "image_rename": prefs.ListValue(prefs.STRING_LIST, [rn.FILENAME, 
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
                                        config.DEFAULT_BACKUP_LOCATION),
        "backup_location": prefs.Value(prefs.STRING, os.path.expanduser('~')),
        "strip_characters": prefs.Value(prefs.BOOL, True),
        "auto_download_at_startup": prefs.Value(prefs.BOOL, False),
        "auto_download_upon_device_insertion": prefs.Value(prefs.BOOL, False),
        "auto_unmount": prefs.Value(prefs.BOOL, False),
        "auto_exit": prefs.Value(prefs.BOOL, False),
        "auto_delete": prefs.Value(prefs.BOOL, False),
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
         "job_codes": prefs.ListValue(prefs.STRING_LIST,  [_('New York'),  
               _('Manila'),  _('Prague'),  _('Helsinki'),   _('Wellington'), 
               _('Tehran'), _('Kampala'),  _('Paris'), _('Berlin'),  _('Sydney'), 
               _('Budapest'), _('Rome'),  _('Moscow'),  _('Delhi'), _('Warsaw'), 
               _('Jakarta'),  _('Madrid'),  _('Stockholm')])
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
            
class ImageRenameTable(tpm.TablePlusMinus):

    def __init__(self, parentApp,  adjustScrollWindow):
  
        tpm.TablePlusMinus.__init__(self, 1, 3)
        self.parentApp = parentApp
        self.adjustScrollWindow = adjustScrollWindow
        if adjustScrollWindow:
            self.connect("size-request", self.size_adjustment)
            self.connect("add",  self.size_adjustment)
            self.tableWidth = self.allocation.width
            # vbar is '1' if there is not vertical scroll bar
            # if there is  a vertical scroll bar, then it will have a the width of the bar
            self.vbar = self.adjustScrollWindow.get_vscrollbar().allocation.width

        self.getParentAppPrefs()
        self.getPrefsFactory()
        
        if not hasattr(self, "errorTitle"):
            self.errorTitle = _("Error in Image Rename preferences")
        
        try:
            self.prefsFactory.checkPrefsForValidity()
            
        except (rn.PrefValueInvalidError, rn.PrefLengthError, 
                rn.PrefValueKeyComboError,  rn.PrefKeyError),  e:

            sys.stderr.write(self.errorTitle + "\n")
            sys.stderr.write(_("Sorry,these preferences contain an error:\n"))
            sys.stderr.write(self.prefsFactory.formatPreferencesForPrettyPrint() + "\n")
            
            # the preferences were invalid
            # reset them to their default

            self.prefList = self.prefsFactory.defaultPrefs
            self.getPrefsFactory()
            self.updateParentAppPrefs()

            msg = "%s.\n" % e
            msg += _("Resetting to default values.")
            sys.stderr.write(msg)
            
            
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
                        sys.stderr.write("Program error: Unknown preference widget!")
                        value = ''
                else:
                    value = ''
                prefList.append(value)

        self.prefList = prefList
        self.updateParentAppPrefs()
        self.prefsFactory.prefList = prefList
        self.updateExample()
            
    
    def size_adjustment(self,  arg1,  arg2):
        """ Adjust scrolledwindow width in preferences dialog to reflect width of image rename table
        
        The algorithm is complicated by the need to tak into account the presence of a vertical scrollbar"""
        
        if self.adjustScrollWindow:
            if self.adjustScrollWindow.get_vscrollbar().allocation.width > 1:
                extra = self.adjustScrollWindow.get_vscrollbar().allocation.width + 10
            else:
                extra = 0
            if self.vbar <= 1:
                if self.allocation.width > self.tableWidth:
                    self.adjustScrollWindow.set_size_request(self.allocation.width + extra,  -1) 
                    self.tableWidth = self.allocation.width + extra
            elif self.allocation.width - extra > self.tableWidth:
                self.adjustScrollWindow.set_size_request(self.allocation.width + extra,  -1) 
                self.tableWidth = self.allocation.width + extra
            self.vbar = self.adjustScrollWindow.get_vscrollbar().allocation.width
            
    def getParentAppPrefs(self):
        self.prefList = self.parentApp.prefs.image_rename
        
    
    def getPrefsFactory(self):
        self.prefsFactory = rn.ImageRenamePreferences(self.prefList, self,  
              sequences = sequences)
        
    def updateParentAppPrefs(self):
        self.parentApp.prefs.image_rename = self.prefList
        
    def updateExampleJobCode(self):
        job_code = self.parentApp.prefs.getSampleJobCode()
        if not job_code:
            job_code = _('Job code')
        self.prefsFactory.setJobCode(job_code)
        
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
            w = self.pm_rows[rowPosition][i]
            name = w.get_name()
            if name == 'GtkComboBox':
                selection.append(w.get_active_text())
            else:
                selection.append(w.get_text())
                
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
        self.updatePreferences()

    def on_rowAdded(self, rowPosition):
        """
        Update preferences, as a row has been added
        """
        self.updatePreferences()
        
        # if this was the last row or 2nd to last row, and another has just been added, move vertical scrollbar down
        if rowPosition in range(self.pm_noRows - 3,  self.pm_noRows - 2):
            adjustment = self.parentApp.rename_scrolledwindow.get_vadjustment()
            adjustment.set_value(adjustment.upper)
        

    def on_rowDeleted(self, rowPosition):
        """
        Update preferences, as a row has been deleted
        """
        self.updatePreferences()        

class SubfolderTable(ImageRenameTable):
    def __init__(self, parentApp,  adjustScollWindow):    
        self.errorTitle = _("Error in Download Subfolder preferences")
        ImageRenameTable.__init__(self,  parentApp,  adjustScollWindow)

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
        
        parentApp.preferencesDialogDisplayed = True
        
        self.parentApp = parentApp

        self._setupTabSelector()
        
        self._setupControlSpacing()

        # get example image data
        
        try:
            w = workers.firstWorkerReadyToDownload()
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
        self._setupJobCodeTab()
        self._setupDeviceTab()
        self._setupBackupTab()
        self._setupAutomationTab()
        self._setupErrorTab()

        self.widget.realize()
        
        #set the width of the left column for selecting values
        #note: this must be called after self.widget.realize(), or else the width calculation will fail
        width_of_widest_sel_row = self.treeview.get_background_area(1, self.treeview_column)[2]
        self.scrolled_window.set_size_request(width_of_widest_sel_row + 2, -1)

        #set the minimum width of the scolled window holding the image rename table
        if self.rename_scrolledwindow.get_vscrollbar():
            extra = self.rename_scrolledwindow.get_vscrollbar().allocation.width + 10
        else:
            extra = 10
        self.rename_scrolledwindow.set_size_request(self.rename_table.allocation.width + extra,   -1)

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
        self.treeview_column = column
        self.treeview.append_column(column)
        self.treeview.props.model = self.model
        for c in self.notebook.get_children():
            label = self.notebook.get_tab_label(c).get_text()
            if not label.startswith("_"):
                self.model.append( (label,) )
        

        # select the first value in the list store
        self.treeview.set_cursor(0,column)
    
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
        self.subfolder_table = SubfolderTable(self,  None)
        self.subfolder_vbox.pack_start(self.subfolder_table)
        self.subfolder_table.show_all()
        
    def _setupDownloadFolderTab(self):
        self.download_folder_filechooser_button = gtk.FileChooserButton(
                            _("Select a folder to download photos to"))
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

        self.rename_table = ImageRenameTable(self,  self.rename_scrolledwindow)
        self.rename_table_vbox.pack_start(self.rename_table)
        self.rename_table.show_all()
        self.original_name_label.set_markup("<i>%s</i>" % self.sampleImageName)
        self.updateImageRenameExample()
        
    def _setupRenameOptionsTab(self):
        
        # sequence numbers
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

        #compatibility
        self.strip_characters_checkbutton.set_active(
                            self.prefs.strip_characters)
        
    def _setupJobCodeTab(self):
        self.job_code_liststore = gtk.ListStore(str)
        column = gtk.TreeViewColumn()
        rentext = gtk.CellRendererText()
        rentext.connect('edited', self.on_job_code_edited)
        rentext .set_property('editable', True)

        column.pack_start(rentext, expand=0)
        column.set_attributes(rentext, text=0)
        self.job_code_treeview_column = column
        self.job_code_treeview.append_column(column)
        self.job_code_treeview.props.model = self.job_code_liststore
        for code in self.prefs.job_codes:
            self.job_code_liststore.append((code, ))
            
        # set multiple selections
        self.job_code_treeview.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
        
        self.clear_job_code_button.set_image(gtk.image_new_from_stock(
                                                gtk.STOCK_CLEAR,
                                                gtk.ICON_SIZE_BUTTON))  
    def _setupDeviceTab(self):
        self.device_location_filechooser_button = gtk.FileChooserButton(
                            _("Select an image folder"))
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
                            _("Select a folder in which to backup images"))
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
        self.auto_delete_checkbutton.set_active(
                        self.prefs.auto_delete)

        
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
            self.rename_table.updateExampleJobCode()
            name, problem = self.rename_table.prefsFactory.generateNameUsingPreferences(
                    self.sampleImage, self.sampleImageName, 
                    self.prefs.strip_characters,  sequencesPreliminary=False)
        else:
            name = problem = ''
            
        # since this is markup, escape it
        text = "<i>%s</i>" % common.escape(name)
        
        if problem:
            text += "\n"
            # Translators: please do not modify or leave out html formatting tags like <i> and <b>. These are used to format the text the users sees
            text += _("<i><b>Warning:</b> There is insufficient image metadata to fully generate the name. Please use other renaming options.</i>")

        self.new_name_label.set_markup(text)
            
    def updateDownloadFolderExample(self):
        """ 
        Displays example subfolder name(s) to the user 
        """
        
        if hasattr(self,  'subfolder_table'):
            self.subfolder_table.updateExampleJobCode()
            path, problem = self.subfolder_table.prefsFactory.generateNameUsingPreferences(
                            self.sampleImage, self.sampleImageName,
                            self.prefs.strip_characters)
        else:
            path = problem = ''
        
        text = os.path.join(self.prefs.download_folder, path)
        # since this is markup, escape it
        path = common.escape(text)
        if problem:
            warning = _("<i><b>Warning:</b> There is insufficient image metadata to fully generate subfolders. Please use other subfolder naming options.</i>" )
        else:
            warning = ""
        # Translators: you should not modify or leave out the %s. This is a code used by the programming language python to insert a value that thes user will see
        self.example_download_path_label.set_markup(_("<i>Example: %s</i>") % text)
        self.subfolder_warning_label.set_markup(warning)
        
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
        if arg == gtk.RESPONSE_HELP:
            webbrowser.open("http://www.damonlynch.net/rapid/documentation")
        else:
            # arg==gtk.RESPONSE_CLOSE, or the user hit the 'x' to close the window
            self.prefs.backup_identifier = self.backup_identifier_entry.get_property("text")
            
            #check subfolder preferences for bad values
            filtered,  prefList = rn.filterSubfolderPreferences(self.prefs.subfolder)
            if filtered:
                cmd_line(_("The subfolder preferences had some unnecessary values removed."))
                if prefList:
                    self.prefs.subfolder = prefList
                else:
                    #Preferences list is now empty
                    msg = _("The subfolder preferences entered are invalid and cannot be used.\nThey will be reset to their default values.")
                    sys.stderr.write(msg + "\n")
                    misc.run_dialog(PROGRAM_NAME, msg)
                    self.prefs.subfolder = self.prefs.get_default("subfolder")
                    
            self.widget.destroy()
            self.parentApp.preferencesDialogDisplayed = False
            self.parentApp.postPreferenceChange()
            



    def on_add_job_code_button_clicked(self,  button):
        j = JobCodeDialog(self.widget,  self.prefs.job_codes,  None, self.add_job_code,  False, True)       


    def add_job_code(self,  dialog,  userChoseCode,  job_code,  autoStart):
        dialog.destroy()
        if userChoseCode:
            if job_code and job_code not in self.prefs.job_codes:
                self.job_code_liststore.prepend((job_code,  ))
                self.update_job_codes()
                selection = self.job_code_treeview.get_selection()
                selection.unselect_all()
                selection.select_path((0, ))
                #scroll to the top
                adjustment = self.job_code_scrolledwindow.get_vadjustment()
                adjustment.set_value(adjustment.lower)

    def on_remove_job_code_button_clicked(self,  button):
        """ remove selected job codes (can be multiple selection)"""
        selection = self.job_code_treeview.get_selection()
        model, selected = selection.get_selected_rows()
        iters = [model.get_iter(path) for path in selected]
        # only delete if a jobe code is selected
        if iters:
            no = len(iters)
            path = None
            for i in range(0, no):
                iter = iters[i]
                if i == no - 1:
                    path = model.get_path(iter) 
                model.remove(iter)
            
            # now that we removed the selection, play nice with 
            # the user and select the next item
            selection.select_path(path)
            
            #  if there was no selection that meant the user
            # removed the last entry, so we try to select the 
            # last item
            if not selection.path_is_selected(path):
                 row = path[0]-1
                 # test case for empty lists
                 if row >= 0:
                    selection.select_path((row,))

        self.update_job_codes()
        self.updateImageRenameExample()
        self.updateDownloadFolderExample()
        
    def on_clear_job_code_button_clicked(self,  button):
        self.job_code_liststore.clear()
        self.update_job_codes()
        self.updateImageRenameExample()
        self.updateDownloadFolderExample()
        
    def on_job_code_edited(self,  widget,  path,  new_text):
        iter = self.job_code_liststore.get_iter(path)
        self.job_code_liststore.set_value(iter,  0,  new_text)
        self.update_job_codes()
        self.updateImageRenameExample()
        self.updateDownloadFolderExample()

    def update_job_codes(self):
        """ update preferences with list of job codes"""
        job_codes = []
        for row in self.job_code_liststore:
            job_codes.append(row[0])
        self.prefs.job_codes = job_codes
        
    def on_auto_startup_checkbutton_toggled(self, checkbutton):
        self.prefs.auto_download_at_startup = checkbutton.get_active()
        
    def on_auto_insertion_checkbutton_toggled(self, checkbutton):
        self.prefs.auto_download_upon_device_insertion = checkbutton.get_active()
        
    def on_auto_unmount_checkbutton_toggled(self, checkbutton):
        self.prefs.auto_unmount = checkbutton.get_active()
        

    def on_auto_delete_checkbutton_toggled(self, checkbutton):
        self.prefs.auto_delete = checkbutton.get_active()

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
            self.autodetect_image_devices_label.set_sensitive(True)
        else:
            for c in controls:
                c.set_sensitive(True)
            self.autodetect_psd_checkbutton.set_sensitive(False)
            self.autodetect_image_devices_label.set_sensitive(False)
    
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
        # Translators: this value is used as an example device when automatic backup device detection is enabled. You should translate this.
        path = os.path.join(config.MEDIA_LOCATION, _("externaldrive1"))
        # Translators: this value is used as an example device when automatic backup device detection is enabled. You should translate this.
        path2 = os.path.join(config.MEDIA_LOCATION, _("externaldrive2"))

        path = os.path.join(path, self.backup_identifier_entry.get_text())
        path2 = os.path.join(path2, self.backup_identifier_entry.get_text())
        path = common.escape(path)
        path2 = common.escape(path2)
        self.example_backup_path_label.set_markup("<i>%s</i>\n<i>%s</i>" % (path,
                            path2))

        


class CopyPhotos(Thread):
    """Copies photos from source to destination, backing up if needed"""
    def __init__(self, thread_id, parentApp, fileRenameLock,  fileSequenceLock, statsLock,  downloadStats,  autoStart = False,  cardMedia = None):
        self.parentApp = parentApp
        self.thread_id = thread_id
        self.ctrl = True
        self.running = False
        self.manuallyDisabled = False
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
        self.waitingForJobCode = False
        
        self.autoStart = autoStart
        self.cardMedia = cardMedia
        
        self.initializeDisplay(thread_id,  self.cardMedia)
        
        self.noErrors = self.noWarnings = 0
        
        self.scanComplete = self.downloadStarted = self.downloadComplete = False
        
        Thread.__init__(self)
        

    def initializeDisplay(self, thread_id, cardMedia = None):

        if self.cardMedia:
            media_collection_treeview.addCard(thread_id, self.cardMedia.prettyName(), 
                                                                '',  0,  progress=0.0,  
                                                                # This refers to when a device like a hard drive is having its contents scanned,
                                                                # looking for images. It is visible initially in the progress bar for each device 
                                                                # (which normally holds "x of y images copied").
                                                                # It maybe displayed only briefly if the contents of the device being scanned is small.
                                                                progressBarText=_('scanning...'))

                
    def firstImage(self):
        """
        returns name, path and size of the first image
        """
        name, root, size,  modificationTime = self.cardMedia.firstImage()
        return root, name
        
    def handlePreferencesError(self,  e,  prefsFactory):
            sys.stderr.write(_("Sorry,these preferences contain an error:\n"))
            sys.stderr.write(prefsFactory.formatPreferencesForPrettyPrint() + "\n")
            msg = str(e)
            sys.stderr.write(msg + "\n")
        
    def initializeFromPrefs(self,  notifyOnError):
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
            if notifyOnError:
                self.handlePreferencesError(e, self.imageRenamePrefsFactory)
            raise rn.PrefError
            

        self.subfolderPrefsFactory = rn.SubfolderPreferences(
                                                self.prefs.subfolder, self)
        try:            
            self.subfolderPrefsFactory.checkPrefsForValidity()
        except (rn.PrefValueInvalidError, rn.PrefLengthError, 
                rn.PrefValueKeyComboError,  rn.PrefKeyError), e:
            if notifyOnError:
                self.handlePreferencesError(e, self.subfolderPrefsFactory)
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
                2.b.4  rename it to the "real" name, effectively performing a mv
                2.b.5  allow other threads to rename files
        
        3.  Backup the image, using the same filename as was used when it was downloaded
            3.a  does a file with the same name already exist on the backup medium?
            3.b  if so, user preferences determine whether it should be overwritten or not
        """

        def getPrefs(notifyOnError):
            try:
                self.initializeFromPrefs(notifyOnError)
                return True
            except rn.PrefError:
                if notifyOnError:
                    display_queue.put((media_collection_treeview.removeCard,  (self.thread_id, )))
                    msg = _("There is an error in the program preferences.")
                    msg += _("\nPlease check preferences, restart the program, and try again.")
                    logError(config.CRITICAL_ERROR, _("Download cannot proceed"), msg)
                    cmd_line(_("Download cannot proceed"))
                    cmd_line(msg) 
                return False
        def scanMedia():
            
            images = []
            imageSizeSum = 0
            for root, dirs, files in os.walk(self.cardMedia.getPath()):
                for name in files:
                    if not self.running:
                        self.lock.acquire()
                        self.running = True
                    
                    if not self.ctrl:
                        self.running = False
                        display_queue.put((media_collection_treeview.removeCard,  (self.thread_id, )))
                        display_queue.close("rw")
                        return
                    
                    if media.isImage(name):
                        image = os.path.join(root, name)
                        size = os.path.getsize(image)
                        modificationTime = os.path.getmtime(image)
                        images.append((name, root, size,  modificationTime),)
                        imageSizeSum += size
            images.sort(key=operator.itemgetter(3))
            noImages = len(images)
            
            self.scanComplete = True
            
            if noImages:
                self.cardMedia.setMedia(images,  imageSizeSum,  noImages)
                # Translators: as already, mentioned the %s value should not be modified or left out. It may be moved if necessary.
                # It refers to the actual number of images that can be copied. For example, the user might see the following:
                # '0 of 512 images copied'.
                # This particular text is displayed to the user before the download has started.
                display = _("0 of %s images copied") % noImages
                display_queue.put((media_collection_treeview.updateCard,  (self.thread_id,  self.cardMedia.sizeOfImages(), noImages)))
                display_queue.put((media_collection_treeview.updateProgress, (self.thread_id, 0.0, display, 0)))
                display_queue.put((self.parentApp.timeRemaining.add,  (self.thread_id,  imageSizeSum)))
                display_queue.put((self.parentApp.setDownloadButtonSensitivity, ()))
                
                # Translators: as you have already seen, the text can contain values that should not be modified or left out by you, for example %s.
                # This text is another example of that, but it is is a little more complex. Here there are two values which will be displayed
                # to the user when they run the program, signifying the number of images found, and the device they were found on.
                # %(number)s should be left exactly as is: 'number' should not be translated. The same applies to %(device)s: 'device' should
                # not be translated. Generally speaking, if translating the sentence requires it, you can move items like '%(xyz)s' around 
                # in a sentence, but you should never modify them or leave them out.
                cmd_line(_("Device scan complete: found %(number)s images on %(device)s") % 
                           {'number': noImages,  'device': self.cardMedia.prettyName(limit=0)})
                return True
            else:
                # it might be better to display "0 of 0" here
                display_queue.put((media_collection_treeview.removeCard,  (self.thread_id, )))
                cmd_line(_("Device scan complete: no images found on %s") % self.cardMedia.prettyName(limit=0))
                return False

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
                    _("Image filename could not be generated"),
                    # '%(source)s' and '%(problem)s' are two more examples of text that should not be modified or left out
                    _("Source: %(source)s\nProblem: %(problem)s") % {'source': image, 'problem': problem},
                    IMAGE_SKIPPED)
            elif problem:
                logError(config.WARNING, 
                    _("Image filename could not be properly generated. Check to ensure there is sufficient image metadata."),
                    _("Source: %(source)s\nDestination: %(destination)s\nProblem: %(problem)s") % 
                    {'source': image, 'destination': newName, 'problem': problem})
             
        def generateSubfolderAndFileName(image,  name,  needMetaDataToCreateUniqueImageName,  
                       needMetaDataToCreateUniqueSubfolderName):
            skipImage = False
            try:
                imageMetadata = metadata.MetaData(image)
            except IOError:
                logError(config.CRITICAL_ERROR, _("Could not open image"), 
                                _("Source: %s") % image, 
                                IMAGE_SKIPPED)
                skipImage = True
                imageMetadata =  newName = newFile = path = subfolder = None
            else:
                try:
                    # this step can fail if the source image is corrupt
                    imageMetadata.readMetadata()
                except:
                    skipImage = True

                if not skipImage:
                    if not imageMetadata.exifKeys() and (needMetaDataToCreateUniqueSubfolderName or 
                                                         (needMetaDataToCreateUniqueImageName and 
                                                         not addUniqueIdentifier)):
                        skipImage = True
                        
                if skipImage:
                    logError(config.SERIOUS_ERROR, _("Image has no metadata"), 
                                        _("Metadata is essential for generating subfolders / image names.\nSource: %s") % image, 
                                        IMAGE_SKIPPED)
                    newName = newFile = path = subfolder = None
                else:
                    subfolder, problem = self.subfolderPrefsFactory.generateNameUsingPreferences(
                                                            imageMetadata, name, 
                                                            self.stripCharacters)
        
                    if problem:
                        logError(config.WARNING, 
                            _("Subfolder name could not be properly generated. Check to ensure there is sufficient image metadata."),
                            _("Subfolder: %(subfolder)s\nImage: %(image)s\nProblem: %(problem)s") % 
                            {'subfolder': subfolder, 'image': image, 'problem': problem})
                    
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
                                    if possibleName:
                                        # no need to check for any problems here, it's just a temporary name
                                        possibleFile = os.path.join(path, possibleName)
                                        possibleTempFile = os.path.join(tempWorkingDir,  possibleName)
                                        if not os.path.exists(possibleFile) and not os.path.exists(possibleTempFile):
                                            downloadNonUniqueFile = True
                                            break

                                        
                    if self.prefs.indicate_download_error and not downloadNonUniqueFile:
                        logError(config.SERIOUS_ERROR, IMAGE_ALREADY_EXISTS,
                                _("Source: %(source)s\nDestination: %(destination)s") % 
                                {'source': image, 'destination': newFile},
                                IMAGE_SKIPPED)

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
                                        _("Source: %(source)s\nDestination: %(destination)s")
                                        % {'source': image, 'destination': newFile},
                                        IMAGE_SKIPPED) 
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
                                        _("Source: %(source)s\nDestination: %(destination)s")
                                        % {'source': image, 'destination': newFile},
                                        _("Unique identifier '%s' added") % identifier)
                                        
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
                                    # A new day, according the user's preferences of what time a day begins, has started
                                    cmd_line(_("New day has started - resetting 'Downloads Today' sequence number"))
                                    
                                    sequences.setDownloadsToday(0)
                    
            except IOError, (errno, strerror):
                logError(config.SERIOUS_ERROR, _('Download copying error'), 
                            _("Source: %(source)s\nDestination: %(destination)s\nError: %(errorno)s %(strerror)s") 
                            % {'source': image, 'destination': newFile, 'errorno': errno, 'strerror': strerror},
                            _('The image was not copied.'))

            except OSError, (errno, strerror):
                logError(config.CRITICAL_ERROR, _('Download copying error'), 
                            "Source: %(source)s\nDestination: %(destination)s\nError: %(errorno)s %(strerror)s" 
                            % {'source': image, 'destination': newFile, 'errorno': errno, 'strerror': strerror},
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
                            problem = _("Backup image already exists")
                            details = _("Source: %(source)s\nDestination: %(destination)s") \
                                % {'source': image, 'destination': newBackupFile}
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
                                            logError(config.SERIOUS_ERROR, _('Backing up error'), 
                                                     _("Destination directory could not be created\n%(directory)s\nError: %(errno)s %(strerror)s")
                                                     % {'directory': folderToMake,  'errno': errno,  'strerror': strerror}, 
                                                     )
                                    
                        shutil.copy2(fileToCopy,  newBackupFile)
                        
            except IOError, (errno, strerror):
                logError(config.SERIOUS_ERROR, _('Backing up error'), 
                            _("Source: %(source)s\nDestination: %(destination)s\nError: %(errno)s %(strerror)s")
                            % {'source': image, 'destination': newBackupFile,  'errno': errno,  'strerror': strerror},
                            _('The image was not copied.'))

            except OSError, (errno, strerror):
                logError(config.CRITICAL_ERROR, _('Backing up error'), 
                            _("Source: %(source)s\nDestination: %(destination)s\nError: %(errno)s %(strerror)s")
                            % {'source': image, 'destination': newBackupFile,  'errno': errno,  'strerror': strerror}
                        )            

        def notifyAndUnmount():
            if not self.cardMedia.volume:
                unmountMessage = ""
                notificationName = PROGRAM_NAME
            else:
                notificationName  = self.cardMedia.volume.get_name()
                if self.prefs.auto_unmount:
                    self.cardMedia.volume.unmount(self.on_volume_unmount)
                    # This message informs the user that the device (e.g. camera, hard drive or memory card) was automatically unmounted and they can now remove it
                    unmountMessage = _("The device can now be safely removed")
                else:
                    unmountMessage = ""
            
            message = _("%s images downloaded") % noImagesDownloaded
            if noImagesSkipped:
                message += "\n" + _("%s images skipped") % noImagesSkipped
            
            if unmountMessage:
                message = "%s\n%s" % (message,  unmountMessage)
                
            if self.noWarnings:
                message = "%s\n%s " % (message,  self.noWarnings) + _("warnings") 
            if self.noErrors:
                message = "%s\n%s " % (message,  self.noErrors) + _("errors")
                
            n = pynotify.Notification(notificationName,  message)
            
            if self.cardMedia.volume:
                icon = self.cardMedia.volume.get_icon_pixbuf(self.parentApp.notification_icon_size)
            else:
                icon = self.parentApp.application_icon
            
            n.set_icon_from_pixbuf(icon)
            n.show()            
        

        

        self.hasStarted = True
        display_queue.open('w')

        #Do not try to handle any preference errors here
        getPrefs(False)
        
        #check for presence of backup meditum
        if self.prefs.backup_images:
            if self.prefs.backup_missing <> config.IGNORE:
                if not len(self.parentApp.backupVolumes):
                    if self.prefs.backup_missing == config.REPORT_ERROR:
                        e = config.SERIOUS_ERROR
                    else:
                        e = config.WARNING
                    logError(e,  _("Backup device missing"),  _("No backup device was detected."))
                
        
        if not scanMedia():
            cmd_line(_("This device has no images to download from."))
            display_queue.close("rw")
            self.running = False
            self.lock.release()
            return 
        elif self.autoStart and need_job_code:
            if job_code == None:
                self.waitingForJobCode = True
                display_queue.put((self.parentApp.getJobCode, ()))
                self.running = False
                self.lock.acquire()
                self.running = True
                self.waitingForJobCode = False
        elif not self.autoStart:
            # halt thread, waiting to be restarted so download proceeds
            self.running = False
            self.lock.acquire()

            if not self.ctrl:
                # thread will restart at this point, when the program is exiting
                # so must exit if self.ctrl indicates this

                self.running = False
                display_queue.close("rw")
                return

            self.running = True
        
        if not getPrefs(True):
                self.running = False
                display_queue.close("rw")           
                return
         
            
        self.downloadStarted = True
        cmd_line(_("Download has started from %s") % self.cardMedia.prettyName(limit=0))
        
        if need_job_code and job_code == None:
            sys.stderr.write(str(self.thread_id ) + ": job code should never be None\n")
            self.imageRenamePrefsFactory.setJobCode('unknown-job-code')
            self.subfolderPrefsFactory.setJobCode('unknown-job-code')
        else:
            self.imageRenamePrefsFactory.setJobCode(job_code)
            self.subfolderPrefsFactory.setJobCode(job_code)
            
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
        imagesDownloadedSuccessfully = []
        
        sizeImages = self.cardMedia.sizeOfImages(humanReadable = False)
        display_queue.put((self.parentApp.addToTotalDownloadSize,  (sizeImages, )))
        display_queue.put((self.parentApp.setOverallDownloadMark, ()))
        display_queue.put((self.parentApp.postStartDownloadTasks,  ()))
        
        sizeImages = float(sizeImages)
        noImages = self.cardMedia.numberOfImages()
        
        baseDownloadDir = self.prefs.download_folder
        #create a temporary directory in which to download the photos to
        #don't want to put it in system temp folder, as that is likely
        #to be on another partition and hence copying files from it
        #to the download folder will be slow!
        tempWorkingDir = tempfile.mkdtemp(prefix='rapid-tmp-', 
                                            dir=baseDownloadDir)
                                            
        IMAGE_SKIPPED = _("Image skipped")
        IMAGE_OVERWRITTEN = _("Image overwritten")
        IMAGE_ALREADY_EXISTS = _("Image already exists")
        
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
                    imagesDownloadedSuccessfully.append(image)
                else:
                    noImagesSkipped += 1
                try:
                    thumbnailType, thumbnail = imageMetadata.getThumbnailData()
                except:
                    logError(config.WARNING, _("Image has no thumbnail"), image)
                    thumbnail = orientation = None
                else:
                    orientation = imageMetadata.orientation(missing=None)
                display_queue.put((image_hbox.addImage, (self.thread_id, thumbnail, orientation, image,  imageDownloaded)))
            
            sizeDownloaded += size
            percentComplete = (sizeDownloaded / sizeImages) * 100
            if sizeDownloaded == sizeImages:
                self.downloadComplete = True
            progressBarText = _("%(number)s of %(total)s images copied") % {'number':  i + 1, 'total': noImages}
            display_queue.put((media_collection_treeview.updateProgress, (self.thread_id, percentComplete, progressBarText, size)))
            
            i += 1

        with self.statsLock:
            self.downloadStats.adjust(sizeDownloaded,  noImagesDownloaded,  noImagesSkipped,  self.noWarnings,  self.noErrors)
            
        if self.prefs.auto_delete:
            j = 0
            for image in imagesDownloadedSuccessfully:
                try:
                    os.unlink(image)
                    j += 1
                except OSError, (errno, strerror):
                    logError(config.SERIOUS_ERROR,  _("Could not delete image from image device"),  
                            _("Image: %(source)s\nError: %(errno)s %(strerror)s")
                            % {'source': image, 'errno': errno,  'strerror': strerror})
                except:
                    logError(config.SERIOUS_ERROR,  _("Could not delete image from image device"),  
                            _("Image: %(source)s"))
                    
            cmd_line(_("Deleted %i images from image device") % j)

        # must manually delete these variables, or else the media cannot be unmounted (bug in pyexiv or exiv2)
        del self.subfolderPrefsFactory,  self.imageRenamePrefsFactory
        try:
            del imageMetadata
        except:
            pass
                
        notifyAndUnmount()
        cmd_line(_("Download complete from %s") % self.cardMedia.prettyName(limit=0))
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
                    sys.stderr.write(str(self.thread_id) + " thread error\n")
    
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
                            sys.stderr.write("Could not release lock for thread %s\n" % self.thread_id)
                            
                            

    def on_volume_unmount(self,  data1,  data2):
        """ needed for call to unmount volume"""
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
        
        # Device refers to a thing like a camera, memory card in its reader, external hard drive, Portable Storage Device, etc.
        column0 = gtk.TreeViewColumn(_("Device"), gtk.CellRendererText(), 
                                    text=0)
        self.append_column(column0)
        
        # Size refers to the total size of images on the device, typically in MB or GB
        column1 = gtk.TreeViewColumn(_("Size"), gtk.CellRendererText(), text=1)
        self.append_column(column1)
        
        column2 = gtk.TreeViewColumn(_("Download Progress"), 
                                    gtk.CellRendererProgress(), value=3, text=4)
        self.append_column(column2)
        self.show_all()
        
    def addCard(self, thread_id, cardName, sizeImages, noImages, progress = 0.0,
                progressBarText = ''):
        if not progressBarText:
            progressBarText = _("0 of %s images copied") % (noImages)
        
        # add the row, and get a temporary pointer to the row
        iter = self.liststore.append((cardName, sizeImages, noImages, 
                                                progress, progressBarText))
        
        self._setThreadMap(thread_id, iter)
        
        # adjust scrolled window height, based on row height and number of ready to start downloads
        if workers.noReadyToStartWorkers() >= 1 or workers.noRunningWorkers() > 0:
            # please note, at program startup, self.rowHeight() will be less than it will be when already running
            # e.g. when starting with 3 cards, it could be 18, but when adding 2 cards to the already running program
            # (with one card at startup), it could be 21
            height = (workers.noReadyToStartWorkers() + workers.noRunningWorkers() + 2) * (self.rowHeight())
            self.parentApp.media_collection_scrolledwindow.set_size_request(-1,  height)

        
    def updateCard(self,  thread_id,  sizeImages, noImages):
        if thread_id in self.mapThreadToRow:
            iter = self._getThreadMap(thread_id)
            self.liststore.set_value(iter, 1, sizeImages)
            self.liststore.set_value(iter, 2, noImages)
        else:
            sys.stderr.write("FIXME: this card is unknown")
    
    def removeCard(self, thread_id):
        if thread_id in self.mapThreadToRow:
            iter = self._getThreadMap(thread_id)
            self.liststore.remove(iter)
            del self.mapThreadToRow[thread_id]


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
        if percentComplete or imageSize:
            self.parentApp.updateOverallProgress(thread_id, imageSize,  percentComplete)
        

    def rowHeight(self):
        if not self.mapThreadToRow:
            return 0
        else:
            index = self.mapThreadToRow.keys()[0]
            path = self.mapThreadToRow[index].get_path()
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
                                _('Thumbnail cannot be displayed'), filename, 
                                _('It may be corrupted'))
                pixbuf = self.missingThumbnail

        if not pixbuf:
            log_dialog.addMessage(thread_id, config.WARNING, 
                            _('Thumbnail cannot be displayed'), filename, 
                            _('It may be corrupted'))
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

        
class UseDeviceDialog(gtk.Dialog):
    def __init__(self,  parent_window,  path,  volume,  autostart, postChoiceCB):
        gtk.Dialog.__init__(self, _('Device Detected'), None,
                   gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                   (gtk.STOCK_NO, gtk.RESPONSE_CANCEL, 
                   gtk.STOCK_YES, gtk.RESPONSE_OK))
                        
        self.postChoiceCB = postChoiceCB
        
        self.set_icon_from_file(paths.share_dir('glade3/rapid-photo-downloader-about.png'))
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#usedeviceprompt
        prompt_label = gtk.Label(_('Should this device or partition be used to download images from?'))
        prompt_label.set_line_wrap(True)
        prompt_hbox = gtk.HBox()
        prompt_hbox.pack_start(prompt_label, False, False, padding=6)
        device_label = gtk.Label()
        device_label.set_markup("<b>%s</b>" % volume.get_name(limit=0))
        device_hbox = gtk.HBox()
        device_hbox.pack_start(device_label, False, False)
        path_label = gtk.Label()
        path_label.set_markup("<i>%s</i>" % path)
        path_hbox = gtk.HBox()
        path_hbox.pack_start(path_label, False, False)
        
        icon = volume.get_icon_pixbuf(36)
        if icon:
            image = gtk.Image()
            image.set_from_pixbuf(icon)
            
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#usedeviceprompt
        self.always_checkbutton = gtk.CheckButton(_('_Remember this choice'),  True)

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
        self.vbox.pack_start(self.always_checkbutton,  padding=6)

        self.set_border_width(6)
        self.set_has_separator(False)   
        
        self.set_default_response(gtk.RESPONSE_OK)
      
       
        self.set_transient_for(parent_window)
        self.show_all()
        self.path = path
        self.volume = volume
        self.autostart = autostart
        
        self.connect('response', self.on_response)
        
    def on_response(self,  device_dialog, response):
        userSelected = False
        permanent_choice = self.always_checkbutton.get_active()
        if response == gtk.RESPONSE_OK:
            userSelected = True
            # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#usedeviceprompt
            cmd_line(_("%s selected for downloading from" % self.volume.get_name(limit=0)))
            if permanent_choice:
                # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#usedeviceprompt
                cmd_line(_("This device or partition will always be used to download from"))
        else:
            # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#usedeviceprompt
            cmd_line(_("%s rejected as a download device" % self.volume.get_name(limit=0)))
            if permanent_choice:
                # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#usedeviceprompt
                cmd_line(_("This device or partition will never be used to download from"))
            
        self.postChoiceCB(self,  userSelected,  permanent_choice,  self.path,  
                          self.volume, self.autostart)        

class JobCodeDialog(gtk.Dialog):
    """ Dialog prompting for a job code"""
    
    def __init__(self,  parent_window,  job_codes,  default_job_code,  postJobCodeEntryCB,  autoStart, entryOnly):
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#jobcode
        gtk.Dialog.__init__(self,  _('Enter a Job Code'), None,
                   gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                   (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, 
                   gtk.STOCK_OK, gtk.RESPONSE_OK))
                        
        
        self.set_icon_from_file(paths.share_dir('glade3/rapid-photo-downloader-about.png'))
        self.postJobCodeEntryCB = postJobCodeEntryCB
        self.autoStart = autoStart
        
        self.combobox = gtk.combo_box_entry_new_text()
        for text in job_codes:
            self.combobox.append_text(text)
            
        self.job_code_hbox = gtk.HBox(homogeneous = False)
        
        if len(job_codes) and not entryOnly:
            # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#jobcode
            task_label = gtk.Label(_('Enter a new job code, or select a previous one.'))
        else:
            # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#jobcode
            task_label = gtk.Label(_('Enter a new job code.'))            
        task_label.set_line_wrap(True)
        task_hbox = gtk.HBox()
        task_hbox.pack_start(task_label, False, False, padding=6)

        label = gtk.Label(_('Job Code:'))
        self.job_code_hbox.pack_start(label, False, False, padding=6)
        self.job_code_hbox.pack_start(self.combobox, True, True, padding=6)
        
        self.set_border_width(6)
        self.set_has_separator(False)

        # make entry box have entry completion
        self.entry = self.combobox.child
        
        completion = gtk.EntryCompletion()
        completion.set_match_func(self.match_func)
        completion.connect("match-selected",
                             self.on_completion_match)
        completion.set_model(self.combobox.get_model())
        completion.set_text_column(0)
        self.entry.set_completion(completion)
        
        # when user hits enter, close the dialog window
        self.set_default_response(gtk.RESPONSE_OK)
        self.entry.set_activates_default(True)

        if default_job_code:
            self.entry.set_text(default_job_code)
        
        self.vbox.pack_start(task_hbox, False, False, padding = 6)
        self.vbox.pack_start(self.job_code_hbox, False, False, padding=12)
        
        self.set_transient_for(parent_window)
        self.show_all()
        self.connect('response', self.on_job_code_resp)
            
    def match_func(self, completion, key, iter):
         model = completion.get_model()
         return model[iter][0].startswith(self.entry.get_text())
         
    def on_completion_match(self, completion, model, iter):
         self.entry.set_text(model[iter][0])
         self.entry.set_position(-1)

    def get_job_code(self):
        return self.combobox.child.get_text()
        
    def on_job_code_resp(self,  jc_dialog, response):
        userChoseCode = False
        if response == gtk.RESPONSE_OK:
            userChoseCode = True
            cmd_line(_("Job Code entered"))  
        else:
            cmd_line(_("Job Code not entered"))
        self.postJobCodeEntryCB(self,  userChoseCode,  self.get_job_code(),  self.autoStart)

        
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
                                    
        
        self.widget.connect("delete-event", self.hide_window)
        
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
        self.parentApp.warning_vseparator.show()
        
        iter = self.textbuffer.get_end_iter()
        self.textbuffer.insert_with_tags(iter, problem +"\n", self.problemTag)
        if details:
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
        self.parentApp.warning_vseparator.hide()
        self.parentApp.prefs.show_log_dialog = False
        self.widget.hide()
        return True

    def hide_window(self,  window, event):
        window.hide()
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
        
        self.timeRemaining = TimeRemaining()
        self._resetDownloadInfo()
        self.statusbar_context_id = self.rapid_statusbar.get_context_id("progress")
        
        # hide display of warning and error symbols in the taskbar until they are needed
        self.error_image.hide()
        self.warning_image.hide()
        self.warning_vseparator.hide()
        
        if not displayPreferences:
            displayPreferences = not self.checkPreferencesOnStartup()
        
        # display download information using threads
        global media_collection_treeview, image_hbox, log_dialog
        global download_queue, image_queue, log_queue
        global workers

        #track files that should have a suffix added to them
        global duplicate_files
        
        # control sequence numbers and letters
        global sequences
        
        # whether we need to prompt for a job code
        global need_job_code

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
        
        # flag to indicate whether the user changed some preferences that 
        # indicate the image and backup devices should be setup again
        self.rerunSetupAvailableImageAndBackupMedia = False
        
        # flag to indicate that the preferences dialog window is being 
        # displayed to the user
        self.preferencesDialogDisplayed = False
        
        # set up tree view display to display image devices and download status
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

        self.menu_display_thumbnails.set_active(self.prefs.display_thumbnails)
        self.menu_clear.set_sensitive(False)
        
        #job code initialization
        need_job_code = self.needJobCode()
        self.last_chosen_job_code = None
        self.prompting_for_job_code = False
        
        #setup download and backup mediums, initiating scans
        self.setupAvailableImageAndBackupMedia(onStartup=True,  onPreferenceChange=False,  doNotAllowAutoStart = displayPreferences)

        #adjust viewport size for displaying media
        #this is important because the code in MediaTreeView.addCard() is inaccurate at program startup
        
        height = self.media_collection_viewport.size_request()[1]
        self.media_collection_scrolledwindow.set_size_request(-1,  height)
        
        self.download_button.grab_default()
        # for some reason, the grab focus command is not working... unsure why
        self.download_button.grab_focus()
        
        if displayPreferences:
            PreferencesDialog(self)



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
        
    
    
    def checkPreferencesOnStartup(self):
        prefsOk = rn.checkPreferencesForValidity(self.prefs.image_rename,  self.prefs.subfolder)
        if not prefsOk:
            title = PROGRAM_NAME
            msg = _("There is an error in the program preferences.")
            msg += " " + _("Some preferences will be reset.") 
            sys.stderr.write(msg +'\n')
#            misc.run_dialog(title, msg)
        return prefsOk
        
    def needJobCode(self):
        return rn.usesJobCode(self.prefs.image_rename) or rn.usesJobCode(self.prefs.subfolder)
        
    def assignJobCode(self,  code):
        """ assign job code (which may be empty) to global variable and update user preferences
        
        Update preferences only if code is not empty. Do not duplicate job code.
        """
        global job_code
        if code == None:
            code = ''
        job_code = code
        
        if job_code:
            #add this value to job codes preferences
            #delete any existing value which is the same
            #(this way it comes to the front, which is where it should be)
            #never modify self.prefs.job_codes in place! (or prefs become screwed up)
            
            jcs = self.prefs.job_codes
            while code in jcs:
                jcs.remove(code)
                
            self.prefs.job_codes = [code] + jcs
            
    
    def getUseDevice(self,  path,  volume, autostart):  
        """ Prompt user whether or not to download from this device """
        
        cmd_line(_("Prompting whether to use %s" % volume.get_name(limit=0)))
        d = UseDeviceDialog(self.widget, path, volume, autostart, self.gotUseDevice)
        
    def gotUseDevice(self,  dialog,  userSelected,  permanent_choice,  path, volume, autostart):
        """ User has chosen whether or not to use a device to download from """
        dialog.destroy()
        
        if userSelected:
            if permanent_choice and path not in self.prefs.device_whitelist:
                # do not do a list append operation here without the assignment, or the preferences will not be updated!
                if len(self.prefs.device_whitelist):
                    self.prefs.device_whitelist = self.prefs.device_whitelist + [path]
                else:
                    self.prefs.device_whitelist = [path]
            self.initiateScan(path, volume, autostart)
            
        elif permanent_choice and path not in self.prefs.device_blacklist:
            # do not do a list append operation here without the assignment, or the preferences will not be updated!
            if len(self.prefs.device_blacklist):
                self.prefs.device_blacklist = self.prefs.device_blacklist + [path]
            else:
                self.prefs.device_blacklist = [path]
                
    def _getJobCode(self,  postJobCodeEntryCB,  autoStart):
        """ prompt for a job code """
        

        if not self.prompting_for_job_code:
            cmd_line(_("Prompting for Job Code"))
            self.prompting_for_job_code = True
            j = JobCodeDialog(self.widget,  self.prefs.job_codes,  self.last_chosen_job_code, postJobCodeEntryCB,  autoStart, False)
        else:
            cmd_line(_("Already prompting for Job Code, do not prompt again"))
        
    def getJobCode(self,  autoStart=True):
        """ called from the copyphotos thread"""
        
        self._getJobCode(self.gotJobCode,  autoStart)
        
    def gotJobCode(self,  dialog,  userChoseCode,  code, autoStart):
        dialog.destroy()
        self.prompting_for_job_code = False
        
        if userChoseCode:
            self.assignJobCode(code)
            self.last_chosen_job_code = code
            if autoStart:
                cmd_line(_("Starting downloads that have been waiting for a Job Code"))
                for w in workers.getWaitingForJobCodeWorkers():
                    w.startStop()    
            else:
                cmd_line(_("Starting downloads"))
                self.startDownload()
                

        # FIXME: what happens to these workers that are waiting? How will the user start their download?
        # check if need to add code to start button
                
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
            
            title = PROGRAM_NAME
            imageRename = subfolder = None
            
            if pv != rv:
                if pv > rv:
                    prefsOk = rn.checkPreferencesForValidity(self.prefs.image_rename,  self.prefs.subfolder)
                        
                    msg = _("A newer version of this program was previously run on this computer.\n\n")
                    if prefsOk:
                        msg += _("Program preferences appear to be valid, but please check them to ensure correct operation.")
                    else:
                        msg += _("Sorry, some preferences are invalid and will be reset.")
                    sys.stderr.write(_("Warning:") + " %s\n" % msg)
                    misc.run_dialog(title, msg)
                    displayPrefs = True
                
                else:
                    cmd_line(_("This version of the program is newer than the previously run version. Checking preferences."))
#                    if True:
                    if rn.checkPreferencesForValidity(self.prefs.image_rename,  self.prefs.subfolder,  previousVersion):
                        upgraded,  imageRename,  subfolder = rn.upgradePreferencesToCurrent(self.prefs.image_rename,  self.prefs.subfolder,  previousVersion)
                        if upgraded:
                            self.prefs.image_rename = imageRename
                            self.prefs.subfolder = subfolder
                            cmd_line(_("Preferences were modified."))
                            msg = _('This version of the program uses different preferences than the old version. Your preferences have been updated.\n\nPlease check them to ensure correct operation.')
                            misc.run_dialog(title,  msg)
                            displayPrefs = True
                        else:
                            cmd_line(_("No preferences needed to be changed."))
                    else:
                        msg = _('This version of the program uses different preferences than the old version. Some of your previous preferences were invalid, and could not be updated. They will be reset.')
                        sys.stderr.write(msg + "\n")
                        misc.run_dialog(title,  msg)
                        displayPrefs = True

        return displayPrefs

    def initPyNotify(self):
        if not pynotify.init("TestCaps"):
            sys.stderr.write(_("Problem using pynotify.") + "\n")
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
            sys.stderr.write(_("Failed to receive pynotify server capabilities.") + "\n")
            sys.exit (1)

        for cap in caps:
            capabilities[cap] = True

        info = pynotify.get_server_info()
        
        if info['name'] == 'Notification Daemon':
            self.notification_icon_size = 48
        else:
            self.notification_icon_size = 128
            
        self.application_icon = gtk.gdk.pixbuf_new_from_file_at_size(
                paths.share_dir('glade3/rapid-photo-downloader-about.png'),
                self.notification_icon_size,  self.notification_icon_size)
        
    
    def usingVolumeMonitor(self):
        """
        Returns True if programs needs to use gio or gnomevfs volume monitor
        """
        
        return (self.prefs.device_autodetection or 
                (self.prefs.backup_images and 
                self.prefs.backup_device_autodetection
                ))
        
    
    def startVolumeMonitor(self):
        if not self.volumeMonitor:
            self.volumeMonitor = VMonitor(self)
    
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
                    prefix = " " + _("and")  + " "
            i += 1
            message = "%s%s'%s'" % (message,  prefix, self.backupVolumes[b].get_name())
        
        if v > 1:
            message = _("Using backup devices") + " %s" % message
        elif v == 1:
            message = _("Using backup device") + " %s"  % message
        else:
            message = _("No backup devices detected")
            
        return message
        
    def searchForPsd(self):
        """
        Check to see if user preferences are to automatically search for Portable Storage Devices or not
        """
        return self.prefs.device_autodetection_psd and self.prefs.device_autodetection
        

    def isGProxyShadowMount(self,  gvfsVolume):

        """ gvfs GProxyShadowMount are used for camera specific things, not the data in the memory card """
        if using_gio:
            #FIXME: this is a hack, but what is the correct function?
            return str(type(gvfsVolume)).find('GProxyShadowMount') >= 0
        else:
            return False

    def workerHasThisPath(self,  path):
        havePath= False
        for w in workers.getNonFinishedWorkers():
            if w.cardMedia.path == path:
                havePath = True
                break
        return havePath
        
    def on_volume_mounted(self, monitor, mount):
        """
        callback run when gnomevfs indicates a new volume
        has been mounted
        """
        
        if self.usingVolumeMonitor():
            volume = Volume(mount)
            path = volume.get_path()
             
            if path in self.prefs.device_blacklist and self.searchForPsd():
                cmd_line(_("Device %(device)s (%(path)s) ignored") % {
                            'device': volume.get_name(limit=0), 'path': path})
            else:
                if not self.isGProxyShadowMount(mount):
                    self._printDetectedDevice(volume.get_name(limit=0),  path)
                    
                    isBackupVolume = self.checkIfBackupVolume(path)
                                
                    if isBackupVolume:
                        backupPath = os.path.join(path,  self.prefs.backup_identifier)
                        if path not in self.backupVolumes:
                            self.backupVolumes[backupPath] = volume
                            self.rapid_statusbar.push(self.statusbar_context_id, self.displayBackupVolumes())

                    elif media.isImageMedia(path) or self.searchForPsd():
                        if self.searchForPsd() and path not in self.prefs.device_whitelist:
                            # prompt user if device should be used or not
                            self.getUseDevice(path,  volume, self.prefs.auto_download_upon_device_insertion)
                        else:   
                            self._printAutoStart(self.prefs.auto_download_upon_device_insertion)                   
                            self.initiateScan(path, volume, self.prefs.auto_download_upon_device_insertion)
                             
    def initiateScan(self, path, volume, autostart):
        """ initiates scan of image device"""
        cardMedia = CardMedia(path, volume,  True)
        i = workers.getNextThread_id()
        
        workers.append(CopyPhotos(i, self, self.fileRenameLock, self.fileSequenceLock, self.statsLock, 
                                                    self.downloadStats, autostart, 
                                                    cardMedia))


        self.setDownloadButtonSensitivity()
        self.startScan()

        
    def on_volume_unmounted(self, monitor, volume):
        """
        callback run when gnomevfs indicates a volume
        has been unmounted
        """
        
        v = Volume(volume)
        path = v.get_path()

        # four scenarios -
        # volume is waiting to be scanned
        # the volume has been scanned but downloading has not yet started
        # images are being downloaded from volume (it must be a messy unmount)
        # images finished downloading from volume
        
        if path:
            # first scenario

            for w in workers.getReadyToStartWorkers():
                if w.cardMedia.volume:
                    if w.cardMedia.volume.volume == volume:
                        media_collection_treeview.removeCard(w.thread_id)
                        workers.disableWorker(w.thread_id)
            # second scenario
            for w in workers.getReadyToDownloadWorkers():
                if w.cardMedia.volume:                
                    if w.cardMedia.volume.volume == volume:
                        media_collection_treeview.removeCard(w.thread_id)
                        workers.disableWorker(w.thread_id)
                    
            # fourth scenario - nothing to do
                    
            # remove backup volumes
            backupPath = os.path.join(path,  self.prefs.backup_identifier)
            if backupPath in self.backupVolumes:
                del self.backupVolumes[backupPath]
                self.rapid_statusbar.push(self.statusbar_context_id, self.displayBackupVolumes())
                
            # may need to disable download button
            self.setDownloadButtonSensitivity()
        
    
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
        
        for w in workers.getNotDownloadingWorkers():
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
        
    def _printDetectedDevice(self,  volume_name, path):
        cmd_line (_("Detected %(device)s with path %(path)s") % {'device': volume_name,   'path': path})
        
    def _printAutoStart(self,  autoStart):
        if autoStart:
            cmd_line(_("Automatically start download is true") )
        else:
            cmd_line(_("Automatically start download is false") )
        
    def setupAvailableImageAndBackupMedia(self,  onStartup,  onPreferenceChange,  doNotAllowAutoStart):
        """
        Sets up volumes for downloading from and backing up to
        
        onStartup should be True if the program is still starting, i.e. this is being called from the 
        program's initialization.
        
        onPreferenceChange should be True if this is being called as the result of a preference
        bring changed
        
        Removes any image media that are currently not downloaded, 
        or finished downloading
        """
        
        self.clearNotStartedDownloads()
        
        volumeList = []
        self.backupVolumes = {}
        
        if not workers.noDownloadingWorkers():
            self.downloadStats.clear() 
            self._resetDownloadInfo()
        
        if self.usingVolumeMonitor():
            # either using automatically detected backup devices
            # or image devices
            
            for v in self.volumeMonitor.get_mounts():
                volume = Volume(v)
                path = volume.get_path(avoid_gnomeVFS_bug = True)

                if path:
                    if path in self.prefs.device_blacklist and self.searchForPsd():
                        cmd_line(_("Device %(device)s (%(path)s) ignored") % {
                                    'device': volume.get_name(limit=0), 
                                    'path': path})
                    else:
                        if not self.isGProxyShadowMount(v):
                            self._printDetectedDevice(volume.get_name(limit=0), path)
                            isBackupVolume = self.checkIfBackupVolume(path)
                            if isBackupVolume:
                                backupPath = os.path.join(path,  self.prefs.backup_identifier)
                                self.backupVolumes[backupPath] = volume
                            elif self.prefs.device_autodetection and (media.isImageMedia(path) or self.searchForPsd()):
                                volumeList.append((path, volume))
                        
        
        if not self.prefs.device_autodetection:
            # user manually specified the path from which to download images
            path = self.prefs.device_location
            if path:
                cmd_line(_("Using manually specified path") + " %s" %  path)
                volumeList.append((path,  None))
                    
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
        
        if doNotAllowAutoStart:
            autoStart = False
        else:
            autoStart = (not onPreferenceChange) and ((self.prefs.auto_download_at_startup and onStartup) or (self.prefs.auto_download_upon_device_insertion and not onStartup))
        
        self._printAutoStart(autoStart)

        for i in range(len(volumeList)):
            path, volume = volumeList[i]
            if self.searchForPsd() and path not in self.prefs.device_whitelist:
                # prompt user to see if device should be used or not
                self.getUseDevice(path, volume, autoStart)
            else:
                self.initiateScan(path, volume, autoStart)
        
    def _setupDownloadbutton(self):
    
        self.download_hbutton_box = gtk.HButtonBox()
        self.download_button_is_download = True
        self.download_button = gtk.Button() 
        self.download_button.set_use_underline(True)
        self.download_button.set_flags(gtk.CAN_DEFAULT)
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
        self.markSet = False
        self.startTime = None
        self.totalDownloadSize = self.totalDownloadedSoFar = 0
        self.totalDownloadSizeThisRun = self.totalDownloadedSoFarThisRun = 0 
        # there is no need to clear self.timeRemaining, as when each thread is completed, it removes itself
        
        global job_code
        job_code = None
    
    def addToTotalDownloadSize(self,  size):
        self.totalDownloadSize += size
        
    def setOverallDownloadMark(self):
        if not self.markSet:
            self.markSet = True
            self.totalDownloadSizeThisRun = self.totalDownloadSize - self.totalDownloadedSoFar
            self.totalDownloadedSoFarThisRun = 0
                
            self.startTime = time.time()
            self.timeStatusBarUpdated = self.startTime

            self.timeMark = self.startTime
            self.sizeMark = 0            
        
    def startOrResumeWorkers(self):
                    
        # resume any paused workers
        for w in workers.getPausedDownloadingWorkers():
            w.startStop()
            self.timeRemaining.setTimeMark(w)
            
        #start any new workers
        workers.startDownloadingWorkers()
        
        if is_beta and verbose:
            workers.printWorkerStatus()
    
        
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
            self.timeRemaining.remove(thread_id)

        if self.downloadComplete():
            # finished all downloads
            self.rapid_statusbar.push(self.statusbar_context_id, "")
            self.download_button_is_download = True
            self._set_download_button()
            self.setDownloadButtonSensitivity()
            cmd_line(_("All downloads complete"))
            if is_beta and verbose:
                workers.printWorkerStatus()
    
        else:
            now = time.time()
            self.timeRemaining.update(thread_id,  imageSize)
            
            if now > (self.downloadTimeGap + self.timeMark):
                amtTime = now - self.timeMark
                self.timeMark = now
                amtDownloaded = self.totalDownloadedSoFarThisRun - self.sizeMark
                self.sizeMark = self.totalDownloadedSoFarThisRun
                amtToDownload = float(self.totalDownloadSizeThisRun) - self.totalDownloadedSoFarThisRun
                downloadSpeed = "%1.1f" % (amtDownloaded / 1048576 / amtTime) +_("MB/s")
                self.speed_label.set_text(downloadSpeed)
                
                timeRemaining = self.timeRemaining.timeRemaining()
                if timeRemaining:
                    secs =  int(timeRemaining)
                
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
                    
                    self.rapid_statusbar.push(self.statusbar_context_id, message)
                    
    
    def resetSequences(self):
        if self.downloadComplete():
            sequences.reset(self.prefs.getDownloadsToday(),  self.prefs.stored_sequence_no)
    
    def notifyUserAllDownloadsComplete(self):
        """ Possibly notify the user all downloads are complete using libnotify
        
        Reset progress bar info"""
        
        if self.downloadComplete():
            if self.displayDownloadSummaryNotification:
                message = _("All downloads complete")
                message += "\n%s " % self.downloadStats.noImagesDownloaded + _("images downloaded")
                if self.downloadStats.noImagesSkipped:
                    message = "%s\n%s " % (message,  self.downloadStats.noImagesSkipped) + _("images skipped")
                if self.downloadStats.noWarnings:
                    message = "%s\n%s " % (message,  self.downloadStats.noWarnings) + _("warnings")
                if self.downloadStats.noErrors:
                    message = "%s\n%s " % (message,  self.downloadStats.noErrors) +_("errors")
                n = pynotify.Notification(PROGRAM_NAME,  message)
                n.set_icon_from_pixbuf(self.application_icon)
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

        isSensitive = workers.noReadyToDownloadWorkers() > 0 or workers.noDownloadingWorkers() > 0
        
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

        self.flushevents() 
        
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

    def on_menu_translate_activate(self,  widget):
        webbrowser.open("http://www.damonlynch.net/rapid/translate.html") 

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
        about.set_property("name", PROGRAM_NAME)
        about.set_property("version", __version__)
        about.run()
        about.destroy()       

    def _set_download_button(self):
        """
        Sets download button to appropriate state
        """
        if self.download_button_is_download:
            # This text will be displayed to the user on the Download / Pause button.
            # Please note the space at the end of the label - it is needed to meet the Gnome Human Interface Guidelines
            self.download_button.set_label(_("_Download "))
            self.download_button.set_image(gtk.image_new_from_stock(
                                                gtk.STOCK_CONVERT,
                                                gtk.ICON_SIZE_BUTTON))        
        else:
            # button should indicate paused state
            self.download_button.set_image(gtk.image_new_from_stock(
                                                gtk.STOCK_MEDIA_PAUSE,
                                                gtk.ICON_SIZE_BUTTON))
            # This text will be displayed to the user on the Download / Pause button.
            self.download_button.set_label(_("_Pause") + " ")
            
    def on_menu_download_pause_activate(self, widget):
        self.on_download_button_clicked(widget)
        
    def startScan(self):
        if workers.noReadyToStartWorkers() > 0:
            workers.startWorkers()



    def postStartDownloadTasks(self):
        if workers.noDownloadingWorkers() > 1:
            self.displayDownloadSummaryNotification = True
            
        # set button to display Pause
        self.download_button_is_download = False
        self._set_download_button()
        
    def startDownload(self):
        self.startOrResumeWorkers()
        self.postStartDownloadTasks()
        
    def pauseDownload(self):
        for w in workers.getDownloadingWorkers():
            w.startStop()
        # set button to display Download
        if not self.download_button_is_download:
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
            if need_job_code and job_code == None and not self.prompting_for_job_code:
                self.getJobCode(autoStart=False)
            else:
                self.startDownload()
        else:
            self.pauseDownload()
            
    def on_preference_changed(self, key, value):
        """
        Called when user changes the program's preferences
        """
        
        if key == 'display_thumbnails':
            self.set_display_thumbnails(value)
        elif key == 'show_log_dialog':
            self.menu_log_window.set_active(value)
        elif key in ['device_autodetection', 'device_autodetection_psd', 'backup_images',  'device_location',
                      'backup_device_autodetection', 'backup_location' ]:              
            self.rerunSetupAvailableImageAndBackupMedia = True
            if not self.preferencesDialogDisplayed:
                self.postPreferenceChange()

        elif key in ['subfolder',  'image_rename']:
            global need_job_code
            need_job_code = self.needJobCode()
            
    def postPreferenceChange(self):
        """
        Handle changes in program preferences after the preferences dialog window has been closed
        """
        if self.rerunSetupAvailableImageAndBackupMedia:
            if self.usingVolumeMonitor():
                self.startVolumeMonitor()
            cmd_line("\n" + _("Preferences were changed."))
                        
            self.setupAvailableImageAndBackupMedia(onStartup = False,  onPreferenceChange = True,  doNotAllowAutoStart = False)
            if is_beta and verbose:
                print "Current worker status:"
                workers.printWorkerStatus()
                
            self.rerunSetupAvailableImageAndBackupMedia = False


 
    def on_error_eventbox_button_press_event(self,  widget,  event):
        self.prefs.show_log_dialog = True
        log_dialog.widget.show()

class VMonitor:
    """ Transistion to gvfs from gnomevfs"""
    def __init__(self,  app):
        self.app = app
        if using_gio:
            self.vmonitor = gio.volume_monitor_get()
            self.vmonitor.connect("mount-added", self.app.on_volume_mounted)
            self.vmonitor.connect("mount-removed", self.app.on_volume_unmounted)
        else:
            self.vmonitor = gnomevfs.VolumeMonitor()
            self.vmonitor.connect("volume-mounted", self.app.on_volume_mounted)
            self.vmonitor.connect("volume-unmounted", self.app.on_volume_unmounted)
            

    def get_mounts(self):        
        if using_gio:
            return self.vmonitor.get_mounts()
        else:
            return self.vmonitor.get_mounted_volumes()
            
class Volume:
    """ Transistion to gvfs from gnomevfs"""
    def __init__(self,  volume):
        self.volume = volume
        
    def get_name(self, limit=config.MAX_LENGTH_DEVICE_NAME):
        if using_gio:
            v = self.volume.get_name()
        else:
            v = self.volume.get_display_name()

        if limit:
            if len(v) > limit:
                v = v[:limit] + '...'
        return v
        
    def get_path(self,  avoid_gnomeVFS_bug = False):
        if using_gio:
            path = self.volume.get_root().get_path()
        else:
            uri = self.volume.get_activation_uri()
            path = None
            if avoid_gnomeVFS_bug:
                # ugly hack to work around bug where gnomevfs.get_local_path_from_uri(uri) causes a crash
                mediaLocation = "file://" + config.MEDIA_LOCATION
                if uri.find(mediaLocation) == 0:
                    path = gnomevfs.get_local_path_from_uri(uri)
            else:
                path = gnomevfs.get_local_path_from_uri(uri)
        return path
        
        
    def get_icon_pixbuf(self, size):
        """ returns icon for the volume, or None if not available"""
        
        icontheme = gtk.icon_theme_get_default()        

        if using_gio:
            gicon = self.volume.get_icon()
            f = None
            if isinstance(gicon, gio.ThemedIcon):
                iconinfo = icontheme.choose_icon(gicon.get_names(), size, gtk.ICON_LOOKUP_USE_BUILTIN)
                f = iconinfo.get_filename()
                try:
                    v = gtk.gdk.pixbuf_new_from_file_at_size(f, size, size)
                except:
                    f = None                
            if not f:
                v = icontheme.load_icon('gtk-harddisk', size, gtk.ICON_LOOKUP_USE_BUILTIN)
        else:
            gicon = self.volume.get_icon()
            v = icontheme.load_icon(gicon, size, gtk.ICON_LOOKUP_USE_BUILTIN)
        return v
            
    def unmount(self,  callback):
        self.volume.unmount(callback)

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
        
class TimeForDownload:
    pass

class TimeRemaining:
    gap = 2
    def __init__(self):
        self.clear()
        
    def add(self,  w,  size):
        if w not in self.times:
            t = TimeForDownload()
            t.timeRemaining = None
            t.size = size
            t.downloaded = 0
            t.sizeMark = 0
            t.timeMark = time.time()
            self.times[w] = t
        
    def update(self,  w,  size):
        if w in self.times:
            self.times[w].downloaded += size
            now = time.time()
            tm = self.times[w].timeMark
            amtTime = now - tm
            if amtTime > self.gap:
                self.times[w].timeMark = now
                amtDownloaded = self.times[w].downloaded - self.times[w].sizeMark
                self.times[w].sizeMark = self.times[w].downloaded
                timefraction = amtDownloaded / amtTime
                amtToDownload = float(self.times[w].size) - self.times[w].downloaded
                self.times[w].timeRemaining = amtToDownload / timefraction
        
    def _timeEstimates(self):
        for t in self.times:
            yield self.times[t].timeRemaining
            
    def timeRemaining(self):
        return max(self._timeEstimates())

    def setTimeMark(self,  w):
        if w in self.times:
            self.times[w].timeMark = time.time()
        
    def clear(self):
        self.times = {}         
        
    def remove(self,  w):
        if w in self.times:
            del self.times[w]
        
def programStatus():
    print _("Goodbye")

        
def start ():
    global is_beta
    is_beta = config.version.find('~b') > 0
    
    parser = OptionParser(version= "%%prog %s" % config.version)
    parser.set_defaults(verbose=is_beta,  extensions=False)
    # Translators: this text is displayed to the user when they request information on the command line options. 
    # The text %default should not be modified or left out.
    parser.add_option("-v",  "--verbose",  action="store_true", dest="verbose",  help=_("display program information on the command line as the program runs (default: %default)"))
    parser.add_option("-q", "--quiet",  action="store_false", dest="verbose",  help=_("only output errors to the command line"))
    # image file extensions are recognized RAW files plus TIFF and JPG
    parser.add_option("-e",  "--extensions",  action="store_true", dest="extensions", help=_("list image file extensions the program recognizes and exit"))
    (options, args) = parser.parse_args()
    global verbose
    verbose = options.verbose
    
    if verbose:
        atexit.register(programStatus)
        
    if options.extensions:
        exts = config.RAW_FILE_EXTENSIONS + config.NON_RAW_IMAGE_FILE_EXTENSIONS
        v = ''
        for e in exts[:-1]:
            v += '%s, ' % e.upper()
        v = v[:-1] + ' '+ (_('and %s') % exts[-1].upper())
        print v
        sys.exit(0)

    if using_gio:
        cmd_line(_("Using") + " GIO")
    else:
        # Which volume management code is being used (GIO or GnomeVFS)
        cmd_line(_("Using") + " GnomeVFS")
        
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
        # this application is already running
        print _("%s is already running") % PROGRAM_NAME
        object = bus.get_object (config.DBUS_NAME, "/")
        app = dbus.Interface (object, config.DBUS_NAME)
    
    app.start()
    gdk.threads_leave()    

if __name__ == "__main__":
    start()
