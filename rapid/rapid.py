#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2007, 2008, 2009, 2010 Damon Lynch <damonlynch@gmail.com>

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
import types
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
import gobject

try:
    import gio
    import glib
    using_gio = True
except ImportError:
    import gnomevfs
    using_gio = False

import prefs
import paths
import gnomeglade

from optparse import OptionParser

import pynotify

import idletube as tube

import config

from config import  STATUS_CANNOT_DOWNLOAD, STATUS_DOWNLOADED, \
                    STATUS_DOWNLOADED_WITH_WARNING, \
                    STATUS_DOWNLOAD_FAILED, \
                    STATUS_DOWNLOAD_PENDING, \
                    STATUS_BACKUP_PROBLEM, \
                    STATUS_NOT_DOWNLOADED, \
                    STATUS_DOWNLOAD_AND_BACKUP_FAILED, \
                    STATUS_WARNING
                    
import common
import misc
import higdefaults as hd

from media import getDefaultPhotoLocation, getDefaultVideoLocation, \
                  getDefaultBackupPhotoIdentifier, \
                  getDefaultBackupVideoIdentifier
                  
import ValidatedEntry
                  
from media import CardMedia

import media

import metadata
import videometadata
from videometadata import DOWNLOAD_VIDEO

import renamesubfolderprefs as rn
import problemnotification as pn

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

try:
    from dropshadow import image_to_pixbuf, pixbuf_to_image, DropShadow
    DROP_SHADOW = True
except:
    DROP_SHADOW = False
    
from common import Configi18n
global _
_ = Configi18n._

#Translators: if neccessary, for guidance in how to translate this program, you may see http://damonlynch.net/translate.html 
PROGRAM_NAME = _('Rapid Photo Downloader')

TINY_SCREEN = gtk.gdk.screen_height() <= config.TINY_SCREEN_HEIGHT
#~ TINY_SCREEN = True

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
media_collection_treeview = selection_hbox = log_dialog = None

job_code = None
need_job_code_for_renaming = False

class ThreadManager:
    """
    Manages the threads that actually download photos and videos
    """
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
       
    def _isScanning(self, w):
        return w.isAlive() and w.hasStarted and not w.scanComplete and not w.manuallyDisabled
       
    def _isDownloading(self,  w):
        return w.downloadStarted and w.isAlive() and not w.downloadComplete
        
    def _isPaused(self, w):
        return w.downloadStarted and not w.running and not w.downloadComplete and not w.manuallyDisabled and w.isAlive()
        
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
            #for some reason, very occassionally a thread that has been started shows up in this list, so must filter them out
            if not w.isAlive():
                w.start()      
            
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
                
    def getNotDownloadingAndNotFinishedWorkers(self):
        for w in self._workers:
            if w.hasStarted and not w.downloadStarted and not self._isFinished(w):
                yield w
        

    def noReadyToStartWorkers(self):
        n = 0
        for w in self._workers:
            if self._isReadyToStart(w):
                n += 1
        return n
        
    def noScanningWorkers(self):
        n = 0
        for w in self._workers:
            if self._isScanning(w):
                n += 1
        return n
        
    def getScanningWorkers(self):
        for w in self._workers:
            if self._isScanning(w):
                yield w
        
    def scanComplete(self, threads):
        """
        Returns True only if the list of threads have completed their scan
        """
        for thread_id in threads:
            if not self[thread_id].scanComplete:
                return False
        return True
    
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

    def getPausedDownloadingWorkers(self):
        for w in self._workers:
            if self._isPaused(w):
                yield w            

    def getWaitingForJobCodeWorkers(self):
        for w in self._workers:
            if w.waitingForJobCode:
                yield w
                
    def getAutoStartWorkers(self):
        for w in self._workers:
            if w.autoStart:
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
        
    def noPausedWorkers(self):
        i = 0
        for w in self._workers:
            if self._isPaused(w):
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
            
class ImageRenameTable(tpm.TablePlusMinus):

    def __init__(self, parentApp, adjustScrollWindow):
  
        tpm.TablePlusMinus.__init__(self, 1, 3)
        self.parentApp = parentApp
        self.adjustScrollWindow = adjustScrollWindow
        if not hasattr(self, "errorTitle"):
            self.errorTitle = _("Error in Photo Rename preferences")
                    
        self.table_type = self.errorTitle[len("Error in "):]
        self.i = 0

        if adjustScrollWindow:
            self.scrollBar = self.adjustScrollWindow.get_vscrollbar()
            #this next line does not work on early versions of pygtk :(
            self.scrollBar.connect('visibility-notify-event', self.scrollbar_visibility_change)
            self.connect("size-request", self.size_adjustment)
            self.connect("add",  self.size_adjustment)
            self.connect("remove",  self.size_adjustment)

            # get scrollbar thickness from parent app scrollbar - very hackish, but what to do??
            self.bump = 16# self.parentApp.parentApp.image_scrolledwindow.get_hscrollbar().allocation.height
            self.haveVerticalScrollbar = False

            # vbar is '1' if there is not vertical scroll bar
            # if there is  a vertical scroll bar, then it will have a the width of the bar
            #self.vbar = self.adjustScrollWindow.get_vscrollbar().allocation.width

        self.getParentAppPrefs()
        self.getPrefsFactory()
        self.prefsFactory.setDownloadStartTime(datetime.datetime.now())
        
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
            msg += _("Resetting to default values." + "\n")
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
            
    
    def scrollbar_visibility_change(self, widget, event):
        if event.state == gdk.VISIBILITY_UNOBSCURED:
            self.haveVerticalScrollbar = True
            self.adjustScrollWindow.set_size_request(self.adjustScrollWindow.allocation.width + self.bump, -1)

            
    def size_adjustment(self, widget, arg2):
        """
        Adjust scrolledwindow width in preferences dialog to reflect width of image rename table
        
        The algorithm is complicated by the need to take into account the presence of a vertical scrollbar,
        which might be added as the user adds more rows
        
        The pygtk code behaves inconsistently depending on the pygtk version
        """
        
        if self.adjustScrollWindow:
            self.haveVerticalScrollbar = self.scrollBar.allocation.width > 1 or self.haveVerticalScrollbar
            if not self.haveVerticalScrollbar:
                if self.allocation.width > self.adjustScrollWindow.allocation.width:
                    self.adjustScrollWindow.set_size_request(self.allocation.width, -1)
            else:
                if self.allocation.width > self.adjustScrollWindow.allocation.width - self.bump:
                    self.adjustScrollWindow.set_size_request(self.allocation.width + self.bump, -1)
                    self.bump = 0
       
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

class VideoRenameTable(ImageRenameTable):
    def __init__(self, parentApp, adjustScollWindow):    
        self.errorTitle = _("Error in Video Rename preferences")
        ImageRenameTable.__init__(self,  parentApp,  adjustScollWindow)

    def getParentAppPrefs(self):
        self.prefList = self.parentApp.prefs.video_rename
    
    def getPrefsFactory(self):
        self.prefsFactory = rn.VideoRenamePreferences(self.prefList, self,
                                                    sequences = sequences)
        
    def updateParentAppPrefs(self):
        self.parentApp.prefs.video_rename = self.prefList

    def updateExample(self):
        self.parentApp.updateVideoRenameExample()

class SubfolderTable(ImageRenameTable):
    def __init__(self, parentApp, adjustScollWindow):    
        self.errorTitle = _("Error in Photo Download Subfolders preferences")
        ImageRenameTable.__init__(self, parentApp, adjustScollWindow)

    def getParentAppPrefs(self):
        self.prefList = self.parentApp.prefs.subfolder
    
    def getPrefsFactory(self):
        self.prefsFactory = rn.SubfolderPreferences(self.prefList, self)
        
    def updateParentAppPrefs(self):
        self.parentApp.prefs.subfolder = self.prefList

    def updateExample(self):
        self.parentApp.updatePhotoDownloadFolderExample()
        
class VideoSubfolderTable(ImageRenameTable):
    def __init__(self, parentApp, adjustScollWindow): 
        self.errorTitle = _("Error in Video Download Subfolders preferences")
        ImageRenameTable.__init__(self, parentApp, adjustScollWindow)

    def getParentAppPrefs(self):
        self.prefList = self.parentApp.prefs.video_subfolder
    
    def getPrefsFactory(self):
        self.prefsFactory = rn.VideoSubfolderPreferences(self.prefList, self)
        
    def updateParentAppPrefs(self):
        self.parentApp.prefs.video_subfolder = self.prefList

    def updateExample(self):
        self.parentApp.updateVideoDownloadFolderExample()        

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
        
        if DOWNLOAD_VIDEO:
            self.file_types = _("photos and videos")
        else:
            self.file_types = _("photos")

        # get example photo and video data
        try:
            w = workers.firstWorkerReadyToDownload()
            mediaFile = w.firstImage() 
            self.sampleImageName = mediaFile.name
            # assume the metadata is already read
            self.sampleImage = mediaFile.metadata
        except:
            self.sampleImage = metadata.DummyMetaData()
            self.sampleImageName = 'IMG_0524.CR2'
            
        try:
            mediaFile = w.firstVideo()
            self.sampleVideoName = mediaFile.name
            self.sampleVideo = mediaFile.metadata
            self.videoFallBackDate = mediaFile.modificationTime
        except:
            self.sampleVideo = videometadata.DummyMetaData()
            self.sampleVideoName = 'MVI_1379.MOV'
            self.videoFallBackDate = datetime.datetime.now()
            
        
        # setup tabs
        self._setupPhotoDownloadFolderTab()
        self._setupImageRenameTab()
        self._setupVideoDownloadFolderTab()
        self._setupVideoRenameTab()                
        self._setupRenameOptionsTab()
        self._setupJobCodeTab()
        self._setupDeviceTab()
        self._setupBackupTab()
        self._setupAutomationTab()
        self._setupErrorTab()
        
        if not DOWNLOAD_VIDEO:
            self.disableVideoControls()

        self.widget.realize()
        
        #set the width of the left column for selecting values
        #note: this must be called after self.widget.realize(), or else the width calculation will fail
        width_of_widest_sel_row = self.treeview.get_background_area(1, self.treeview_column)[2]
        self.scrolled_window.set_size_request(width_of_widest_sel_row + 2, -1)

        #set the minimum width of the scolled window holding the photo rename table
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
        self.updatePhotoDownloadFolderExample()
        
    def on_video_download_folder_filechooser_button_selection_changed(self, widget):
        self.prefs.video_download_folder = widget.get_current_folder()
        self.updateVideoDownloadFolderExample()
    
    def on_backup_folder_filechooser_button_selection_changed(self, widget):
        self.prefs.backup_location = widget.get_current_folder()
        self.updateBackupExample()
        
    def on_device_location_filechooser_button_selection_changed(self, widget):
        self.prefs.device_location = widget.get_current_folder()
        
    def _setupControlSpacing(self):
        """
        set spacing of some but not all controls
        """
        
        self._setupTableSpacing(self.download_folder_table) 
        self._setupTableSpacing(self.video_download_folder_table) 
        self.download_folder_table.set_row_spacing(2, 
                                hd.VERTICAL_CONTROL_SPACE)
        self.video_download_folder_table.set_row_spacing(2, 
                                hd.VERTICAL_CONTROL_SPACE)
        self._setupTableSpacing(self.rename_example_table)
        self._setupTableSpacing(self.video_rename_example_table)
        self.devices_table.set_col_spacing(0, hd.NESTED_CONTROLS_SPACE)        
      
        self._setupTableSpacing(self.backup_table)
        self.backup_table.set_col_spacing(1, hd.NESTED_CONTROLS_SPACE)
        self.backup_table.set_col_spacing(2, hd.CONTROL_LABEL_SPACE)
        self._setupTableSpacing(self.compatibility_table)
        self.compatibility_table.set_row_spacing(0, 
                                            hd.VERTICAL_CONTROL_LABEL_SPACE)                                                    
        self._setupTableSpacing(self.error_table)
    
    
    def _setupTableSpacing(self, table):
        table.set_col_spacing(0, hd.NESTED_CONTROLS_SPACE)
        table.set_col_spacing(1, hd.CONTROL_LABEL_SPACE)

    def _setupSubfolderTable(self):
        self.subfolder_table = SubfolderTable(self, None)
        self.subfolder_vbox.pack_start(self.subfolder_table)
        self.subfolder_table.show_all()
        
    def _setupVideoSubfolderTable(self):
        self.video_subfolder_table = VideoSubfolderTable(self, None)
        self.video_subfolder_vbox.pack_start(self.video_subfolder_table)
        self.video_subfolder_table.show_all()

    def _setupPhotoDownloadFolderTab(self):
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
        self.updatePhotoDownloadFolderExample()
        
    def _setupVideoDownloadFolderTab(self):
        self.video_download_folder_filechooser_button = gtk.FileChooserButton(
                            _("Select a folder to download videos to"))
        self.video_download_folder_filechooser_button.set_current_folder(
                            self.prefs.video_download_folder)
        self.video_download_folder_filechooser_button.set_action(
                            gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER)
        self.video_download_folder_filechooser_button.connect("selection-changed", 
                    self.on_video_download_folder_filechooser_button_selection_changed)
                            
        self.video_download_folder_table.attach(
                            self.video_download_folder_filechooser_button, 
                            2, 3, 2, 3, yoptions = gtk.SHRINK)
        self.video_download_folder_filechooser_button.show()        
        self._setupVideoSubfolderTable()
        self.updateVideoDownloadFolderExample()        
    
    def _setupImageRenameTab(self):

        self.rename_table = ImageRenameTable(self, self.rename_scrolledwindow)
        self.rename_table_vbox.pack_start(self.rename_table)
        self.rename_table.show_all()
        self.original_name_label.set_markup("<i>%s</i>" % self.sampleImageName)
        self.updateImageRenameExample()
        
    def _setupVideoRenameTab(self):

        self.video_rename_table = VideoRenameTable(self, self.video_rename_scrolledwindow)
        self.video_rename_table_vbox.pack_start(self.video_rename_table)
        self.video_rename_table.show_all()
        self.video_original_name_label.set_markup("<i>%s</i>" % self.sampleVideoName)
        self.updateVideoRenameExample()
                
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

        self.synchronize_raw_jpg_checkbutton.set_active(
                            self.prefs.synchronize_raw_jpg)
        
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
        
        self.remove_all_job_code_button.set_image(gtk.image_new_from_stock(
                                                gtk.STOCK_CLEAR,
                                                gtk.ICON_SIZE_BUTTON))  
    def _setupDeviceTab(self):

        self.device_location_filechooser_button = gtk.FileChooserButton(
                            _("Select a folder containing %(file_types)s") % {'file_types':self.file_types})
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
                            _("Select a folder in which to backup %(file_types)s") % {'file_types':self.file_types})
        self.backup_folder_filechooser_button.set_current_folder(
                            self.prefs.backup_location)
        self.backup_folder_filechooser_button.set_action(
                            gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER)
        self.backup_folder_filechooser_button.connect("selection-changed", 
                    self.on_backup_folder_filechooser_button_selection_changed)
        self.backup_table.attach(self.backup_folder_filechooser_button,
                            3, 4, 8, 9, yoptions = gtk.SHRINK)
        self.backup_folder_filechooser_button.show()
        self.backup_identifier_entry.set_text(self.prefs.backup_identifier)
        self.video_backup_identifier_entry.set_text(self.prefs.video_backup_identifier)
        
        #setup controls for manipulating sensitivity
        self._backupControls0 = [self.auto_detect_backup_checkbutton]
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
                                
        self._backupVideoControls = [self.video_backup_identifier_label,
                                self.video_backup_identifier_entry]
        
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
        if self.prefs.download_conflict_resolution == config.SKIP_DOWNLOAD:
            self.skip_download_radiobutton.set_active(True)
        else:
            self.add_identifier_radiobutton.set_active(True)
            
        if self.prefs.backup_duplicate_overwrite:
            self.backup_duplicate_overwrite_radiobutton.set_active(True)
        else:
            self.backup_duplicate_skip_radiobutton.set_active(True)

    
    def updateExampleFileName(self, display_table, rename_table, sample, sampleName, example_label, fallback_date = None):
        problem = pn.Problem()
        if hasattr(self, display_table):
            rename_table.updateExampleJobCode()
            rename_table.prefsFactory.initializeProblem(problem)
            name = rename_table.prefsFactory.generateNameUsingPreferences(
                    sample, sampleName,
                    self.prefs.strip_characters, sequencesPreliminary=False, fallback_date=fallback_date)
        else:
            name = ''
            
        # since this is markup, escape it
        text = "<i>%s</i>" % common.escape(name)
        
        if problem.has_problem():
            text += "\n"
            # Translators: please do not modify or leave out html formatting tags like <i> and <b>. These are used to format the text the users sees
            text += _("<i><b>Warning:</b> There is insufficient metadata to fully generate the name. Please use other renaming options.</i>")

        example_label.set_markup(text)        
    
    def updateImageRenameExample(self):
        """ 
        Displays example image name to the user 
        """
        self.updateExampleFileName('rename_table', self.rename_table, self.sampleImage,  self.sampleImageName, self.new_name_label)

        
    def updateVideoRenameExample(self):
        """
        Displays example video name to the user
        """
        self.updateExampleFileName('video_rename_table', self.video_rename_table, self.sampleVideo,  self.sampleVideoName, self.video_new_name_label, self.videoFallBackDate)
            
    def updateDownloadFolderExample(self, display_table, subfolder_table, download_folder, sample, sampleName, example_download_path_label, subfolder_warning_label, fallback_date = None):
        """ 
        Displays example subfolder name(s) to the user 
        """
        
        problem = pn.Problem()
        if hasattr(self, display_table):
            subfolder_table.updateExampleJobCode()
            subfolder_table.prefsFactory.initializeProblem(problem)
            path = subfolder_table.prefsFactory.generateNameUsingPreferences(
                            sample, sampleName,
                            self.prefs.strip_characters, fallback_date = fallback_date)
        else:
            path = ''
        
        text = os.path.join(download_folder, path)
        # since this is markup, escape it
        path = common.escape(text)
        if problem.has_problem():
            warning = _("<i><b>Warning:</b> There is insufficient metadata to fully generate subfolders. Please use other subfolder naming options.</i>" )
        else:
            warning = ""
        # Translators: you should not modify or leave out the %s. This is a code used by the programming language python to insert a value that thes user will see
        example_download_path_label.set_markup(_("<i>Example: %s</i>") % text)
        subfolder_warning_label.set_markup(warning)
        
    def updatePhotoDownloadFolderExample(self):
        if hasattr(self, 'subfolder_table'):
            self.updateDownloadFolderExample('subfolder_table', self.subfolder_table, self.prefs.download_folder, self.sampleImage, self.sampleImageName, self.example_photo_download_path_label, self.photo_subfolder_warning_label)
        
    def updateVideoDownloadFolderExample(self):
        if hasattr(self, 'video_subfolder_table'):
            self.updateDownloadFolderExample('video_subfolder_table', self.video_subfolder_table, self.prefs.video_download_folder, self.sampleVideo, self.sampleVideoName, self.example_video_download_path_label, self.video_subfolder_warning_label, self.videoFallBackDate)
        
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
        # do not update value if a download is occurring - it will mess it up!
        if workers.noDownloadingWorkers() <> 0:
            cmd_line(_("Downloads today value not updated, as a download is currently occurring"))
        else:            
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
        # do not update value if a download is occurring - it will mess it up!        
        if workers.noDownloadingWorkers() <> 0:
            cmd_line(_("Stored number value not updated, as a download is currently occurring"))
        else:
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

    def _updateSubfolderPrefOnError(self, newPrefList):
        self.prefs.subfolder = newPrefList

    def _updateVideoSubfolderPrefOnError(self, newPrefList):
        self.prefs.video_subfolder = newPrefList
        
    
    def checkSubfolderValuesValidOnExit(self, usersPrefList, updatePrefFunction, filetype, defaultPrefList):
        """
        Checks that the user has not entered in any inappropriate values
        
        If they have, filters out bad values and warns the user 
        """
        filtered,  prefList = rn.filterSubfolderPreferences(usersPrefList)
        if filtered:
            cmd_line(_("The %(filetype)s subfolder preferences had some unnecessary values removed.") % {'filetype': filetype})
            if prefList:
                updatePrefFunction(prefList)
            else:
                #Preferences list is now empty
                msg = _("The %(filetype)s subfolder preferences entered are invalid and cannot be used.\nThey will be reset to their default values.") % {'filetype': filetype}
                sys.stderr.write(msg + "\n")
                misc.run_dialog(PROGRAM_NAME, msg)
                updatePrefFunction(self.prefs.get_default(defaultPrefList))
    
    def on_response(self, dialog, arg):
        if arg == gtk.RESPONSE_HELP:
            webbrowser.open("http://www.damonlynch.net/rapid/documentation")
        else:
            # arg==gtk.RESPONSE_CLOSE, or the user hit the 'x' to close the window
            self.prefs.backup_identifier = self.backup_identifier_entry.get_property("text")
            self.prefs.video_backup_identifier = self.video_backup_identifier_entry.get_property("text")
            
            #check subfolder preferences for bad values
            self.checkSubfolderValuesValidOnExit(self.prefs.subfolder, self._updateSubfolderPrefOnError, _("photo"), "subfolder")
            self.checkSubfolderValuesValidOnExit(self.prefs.video_subfolder, self._updateVideoSubfolderPrefOnError, _("video"), "video_subfolder")
                    
            self.widget.destroy()
            self.parentApp.preferencesDialogDisplayed = False
            self.parentApp.postPreferenceChange()
            



    def on_add_job_code_button_clicked(self,  button):
        j = JobCodeDialog(self.widget,  self.prefs.job_codes,  None, self.add_job_code,  False, True, True)


    def add_job_code(self,  dialog,  userChoseCode,  job_code,  autoStart, downloadSelected):
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
        self.updateVideoRenameExample()
        self.updatePhotoDownloadFolderExample()
        self.updateVideoDownloadFolderExample()
        
    def on_remove_all_job_code_button_clicked(self,  button):
        j = RemoveAllJobCodeDialog(self.widget,  self.remove_all_job_code)
        
    def remove_all_job_code(self, dialog, userSelected):
        dialog.destroy()
        if userSelected:
            self.job_code_liststore.clear()
            self.update_job_codes()
            self.updateImageRenameExample()
            self.updateVideoRenameExample()
            self.updatePhotoDownloadFolderExample()
            self.updateVideoDownloadFolderExample()
        
    def on_job_code_edited(self,  widget,  path,  new_text):
        iter = self.job_code_liststore.get_iter(path)
        self.job_code_liststore.set_value(iter,  0,  new_text)
        self.update_job_codes()
        self.updateImageRenameExample()
        self.updateVideoRenameExample()
        self.updatePhotoDownloadFolderExample()
        self.updateVideoDownloadFolderExample()

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
    
    def on_treeview_cursor_changed(self, tree):
        path, column = tree.get_cursor()
        self.notebook.set_current_page(path[0])

    def on_synchronize_raw_jpg_checkbutton_toggled(self, check_button):
        self.prefs.synchronize_raw_jpg = check_button.get_active()
        
    def on_strip_characters_checkbutton_toggled(self, check_button):
        self.prefs.strip_characters = check_button.get_active()
        self.updateImageRenameExample()
        self.updatePhotoDownloadFolderExample()
        self.updateVideoDownloadFolderExample()
        
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
            for c in self._backupControls + self._backupVideoControls:
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
            for c in self._backupVideoControls:
                c.set_sensitive(False)
            if DOWNLOAD_VIDEO:
                for c in self._backupVideoControls:
                    c.set_sensitive(True)
        else:
            for c in self._backupControls1:
                c.set_sensitive(False)
            for c in self._backupControls2:
                c.set_sensitive(True)
            if DOWNLOAD_VIDEO:
                for c in self._backupVideoControls:
                    c.set_sensitive(False)                
            
    def disableVideoControls(self):
        """
        Disables video preferences if video downloading is disabled
        (probably because the appropriate libraries to enable
        video metadata extraction are not installed)
        """        
        controls = [self.example_video_filename_label, 
                    self.original_video_filename_label,
                    self.new_video_filename_label,
                    self.video_new_name_label,
                    self.video_original_name_label,
                    self.video_rename_scrolledwindow,
                    self.video_folders_hbox,
                    self.video_backup_identifier_label,
                    self.video_backup_identifier_entry
                    ]
        for c in controls:
            c.set_sensitive(False)
            
        self.videos_cannot_be_downloaded_label.show()
        self.folder_videos_cannot_be_downloaded_label.show()
        self.folder_videos_cannot_be_downloaded_hbox.show()
    
    def on_auto_detect_backup_checkbutton_toggled(self, widget):
        self.prefs.backup_device_autodetection = widget.get_active()
        self.updateBackupControlsAuto()
        
    def on_backup_checkbutton_toggled(self, widget):
        self.prefs.backup_images = self.backup_checkbutton.get_active()
        self.updateBackupControls()

    def on_backup_identifier_entry_changed(self, widget):
        self.updateBackupExample()
    
    def on_video_backup_identifier_entry_changed(self, widget):
        self.updateBackupExample()

    def on_backup_scan_folder_on_entry_changed(self, widget):
        self.updateBackupExample()        

    def updateBackupExample(self):
        # Translators: this value is used as an example device when automatic backup device detection is enabled. You should translate this.
        drive1 = os.path.join(config.MEDIA_LOCATION, _("externaldrive1"))
        # Translators: this value is used as an example device when automatic backup device detection is enabled. You should translate this.
        drive2 = os.path.join(config.MEDIA_LOCATION, _("externaldrive2"))

        path = os.path.join(drive1, self.backup_identifier_entry.get_text())
        path2 = os.path.join(drive2, self.backup_identifier_entry.get_text())
        path3 = os.path.join(drive2, self.video_backup_identifier_entry.get_text())
        path = common.escape(path)
        path2 = common.escape(path2)
        path3 = common.escape(path3)
        if DOWNLOAD_VIDEO:
            example = "<i>%s</i>\n<i>%s</i>\n<i>%s</i>" % (path, path2, path3)
        else:
            example = "<i>%s</i>\n<i>%s</i>" % (path, path2)
        self.example_backup_path_label.set_markup(example)

        
def file_types_by_number(noImages, noVideos):
    """ 
    returns a string to be displayed to the user that can be used
    to show if a value refers to photos or videos or both, or just one
    of each
    """
    if (noVideos > 0) and (noImages > 0):
        v = _('photos and videos')
    elif (noVideos == 0) and (noImages == 0):
        v = _('photos or videos')
    elif noVideos > 0:
        if noVideos > 1:
            v = _('videos')
        else:
            v = _('video')
    else:
        if noImages > 1:
            v = _('photos')
        else:
            v = _('photo')
    return v
    
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

def generateSubfolderAndName(mediaFile, problem, subfolderPrefsFactory, 
                            renamePrefsFactory, 
                            nameUsesJobCode, subfolderUsesJobCode, 
                            strip_characters, fallback_date):
                                
    subfolderPrefsFactory.initializeProblem(problem)
    mediaFile.sampleSubfolder = subfolderPrefsFactory.generateNameUsingPreferences(
                                mediaFile.metadata, mediaFile.name, 
                                strip_characters, 
                                fallback_date = fallback_date)

    mediaFile.samplePath = os.path.join(mediaFile.downloadFolder, mediaFile.sampleSubfolder)
    
    renamePrefsFactory.initializeProblem(problem)
    mediaFile.sampleName = renamePrefsFactory.generateNameUsingPreferences(
                            mediaFile.metadata, mediaFile.name, strip_characters, 
                            sequencesPreliminary=False,
                            fallback_date = fallback_date)
        
    if not (mediaFile.sampleName or nameUsesJobCode) or not (mediaFile.sampleSubfolder or subfolderUsesJobCode):
        if not (mediaFile.sampleName or nameUsesJobCode) and not (mediaFile.sampleSubfolder or subfolderUsesJobCode):
            area = _("subfolder and filename")
        elif not (mediaFile.sampleName or nameUsesJobCode):
            area = _("filename")
        else:
            area = _("subfolder")
        problem.add_problem(None, pn.ERROR_IN_NAME_GENERATION, {'filetype': mediaFile.displayNameCap, 'area': area})
        problem.add_extra_detail(pn.NO_DATA_TO_NAME, {'filetype': area})
        mediaFile.problem = problem
        mediaFile.status = STATUS_CANNOT_DOWNLOAD
    elif problem.has_problem():
        mediaFile.problem = problem
        mediaFile.status = STATUS_WARNING
    else:
        mediaFile.status = STATUS_NOT_DOWNLOADED


class NeedAJobCode():
    """
    Convenience class to check whether a job code is missing for a given
    file type (photo or video)
    """
    def __init__(self, prefs):
        self.imageRenameUsesJobCode = rn.usesJobCode(prefs.image_rename)
        self.imageSubfolderUsesJobCode = rn.usesJobCode(prefs.subfolder)
        self.videoRenameUsesJobCode = rn.usesJobCode(prefs.video_rename)
        self.videoSubfolderUsesJobCode = rn.usesJobCode(prefs.video_subfolder)
                
    def needAJobCode(self, job_code, is_image):
        if is_image:
            return not job_code and (self.imageRenameUsesJobCode or self.imageSubfolderUsesJobCode)
        else:
            return not job_code and (self.videoRenameUsesJobCode or self.videoSubfolderUsesJobCode)
        

class CopyPhotos(Thread):
    """Copies photos from source to destination, backing up if needed"""
    def __init__(self, thread_id, parentApp, fileRenameLock,  fileSequenceLock, 
                statsLock,  downloadedFilesLock,
                downloadStats, autoStart = False, cardMedia = None):
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
        self.downloadedFilesLock = downloadedFilesLock
        
        self.downloadStats = downloadStats
        
        self.hasStarted = False
        self.doNotStart = False
        self.waitingForJobCode = False
        
        self.autoStart = autoStart
        self.cardMedia = cardMedia
        
        self.initializeDisplay(thread_id, self.cardMedia)
               
        self.scanComplete = self.downloadStarted = self.downloadComplete = False
        
        # Need to account for situations where the user adjusts their preferences when the program is scanning
        # Here the sample filenames and paths will be out of date, and they will need to be updated
        # This flag indicates whether that is the case or not
        self.scanResultsStale = False # name and subfolder
        self.scanResultsStaleDownloadFolder = False #download folder only
        
        self.noErrors = self.noWarnings = 0
        self.videoTempWorkingDir = self.photoTempWorkingDir = ''
        
        if DOWNLOAD_VIDEO:
            self.types_searched_for = _('photos or videos')
        else:
            self.types_searched_for = _('photos')            
        
        Thread.__init__(self)
        

    def initializeDisplay(self, thread_id, cardMedia = None):

        if self.cardMedia:
            media_collection_treeview.addCard(thread_id, self.cardMedia.prettyName(), 
                                                                '', progress=0.0,  
                                                                # This refers to when a device like a hard drive is having its contents scanned,
                                                                # looking for photos or videos. It is visible initially in the progress bar for each device 
                                                                # (which normally holds "x photos and videos").
                                                                # It maybe displayed only briefly if the contents of the device being scanned is small.
                                                                progressBarText=_('scanning...'))

    def firstImage(self):
        """
        returns class mediaFile of the first photo
        """
        mediaFile = self.cardMedia.firstImage()
        return mediaFile

    def firstVideo(self):
        """
        returns class mediaFile of the first video
        """
        mediaFile = self.cardMedia.firstVideo()
        return mediaFile
                        
    def handlePreferencesError(self,  e,  prefsFactory):
            sys.stderr.write(_("Sorry,these preferences contain an error:\n"))
            sys.stderr.write(prefsFactory.formatPreferencesForPrettyPrint() + "\n")
            msg = str(e)
            sys.stderr.write(msg + "\n")
        
    def initializeFromPrefs(self, notifyOnError):
        """
        Setup thread so that user preferences are handled
        """
        
        def checkPrefs(prefsFactory):
            try:
                prefsFactory.checkPrefsForValidity()
            except (rn.PrefValueInvalidError, rn.PrefLengthError, 
                    rn.PrefValueKeyComboError, rn.PrefKeyError), e:
                if notifyOnError:
                    self.handlePreferencesError(e, prefsFactory)
                raise rn.PrefError
                
        self.prefs = self.parentApp.prefs
        
        #Image and Video filename preferences
        sample_download_start_time = datetime.datetime.now()

        self.imageRenamePrefsFactory = rn.ImageRenamePreferences(self.prefs.image_rename, self, 
                                                                 self.fileSequenceLock, sequences)
        self.imageRenamePrefsFactory.setDownloadStartTime(sample_download_start_time)
        checkPrefs(self.imageRenamePrefsFactory)
           
        self.videoRenamePrefsFactory = rn.VideoRenamePreferences(self.prefs.video_rename, self, 
                                                                 self.fileSequenceLock, sequences)
        self.videoRenamePrefsFactory.setDownloadStartTime(sample_download_start_time)
        checkPrefs(self.videoRenamePrefsFactory)
        
        #Image and Video subfolder preferences

        self.subfolderPrefsFactory = rn.SubfolderPreferences(self.prefs.subfolder, self)
        self.subfolderPrefsFactory.setDownloadStartTime(sample_download_start_time)
        checkPrefs(self.subfolderPrefsFactory)

        self.videoSubfolderPrefsFactory = rn.VideoSubfolderPreferences(self.prefs.video_subfolder, self)
        self.videoSubfolderPrefsFactory.setDownloadStartTime(sample_download_start_time)
        checkPrefs(self.videoSubfolderPrefsFactory)
        
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

        def checkDownloadPath(path):
            """
            Checks to see if download folder exists.
            
            Creates it if it does not exist.
            
            Returns False if the path could not be created.
            """
            
            try:
                if not os.path.isdir(path):
                    os.makedirs(path)
                return True
                    
            except:
                display_queue.put((media_collection_treeview.removeCard,  (self.thread_id, )))
                msg = _("The following download path could not be created:\n")
                msg += _("%(path)s: ") % {'path': path}
                logError(config.CRITICAL_ERROR, _("Download cannot proceed"), msg)
                cmd_line(_("Download cannot proceed"))
                cmd_line(msg)
                display_queue.put((self.parentApp.downloadFailed,  (self.thread_id, )))
                display_queue.close("rw")                     
                return False                
                
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
                    display_queue.put((self.parentApp.downloadFailed,  (self.thread_id, )))
                    display_queue.close("rw")                     
                return False
        

                    
        def scanMedia():
            """
            Scans media for photos and videos
            """
                       
            # load images to display for when a thumbnail cannot be extracted or created
            
            self.photoThumbnail = gtk.gdk.pixbuf_new_from_file(paths.share_dir('glade3/photo.png'))
            self.videoThumbnail = gtk.gdk.pixbuf_new_from_file(paths.share_dir('glade3/video.png'))
                
            imageRenameUsesJobCode = rn.usesJobCode(self.prefs.image_rename)
            imageSubfolderUsesJobCode = rn.usesJobCode(self.prefs.subfolder)
            videoRenameUsesJobCode = rn.usesJobCode(self.prefs.video_rename)
            videoSubfolderUsesJobCode = rn.usesJobCode(self.prefs.video_subfolder)
            
            def loadFileMetadata(mediaFile):
                """
                loads the metadate for the file, and additional information if required
                """
                
                problem = pn.Problem()
                try:
                    mediaFile.loadMetadata()
                except:
                    mediaFile.status = STATUS_CANNOT_DOWNLOAD
                    mediaFile.metadata = None
                    problem.add_problem(None, pn.CANNOT_DOWNLOAD_BAD_METADATA, {'filetype': mediaFile.displayNameCap})
                    mediaFile.problem = problem
                else:
                    # generate sample filename and subfolder
                    if mediaFile.isImage:
                        fallback_date = None
                        subfolderPrefsFactory = self.subfolderPrefsFactory
                        renamePrefsFactory = self.imageRenamePrefsFactory
                        nameUsesJobCode = imageRenameUsesJobCode
                        subfolderUsesJobCode = imageSubfolderUsesJobCode                        
                    else:
                        fallback_date = mediaFile.modificationTime
                        subfolderPrefsFactory = self.videoSubfolderPrefsFactory
                        renamePrefsFactory = self.videoRenamePrefsFactory
                        nameUsesJobCode = videoRenameUsesJobCode
                        subfolderUsesJobCode = videoSubfolderUsesJobCode
                        
                    generateSubfolderAndName(mediaFile, problem, subfolderPrefsFactory, renamePrefsFactory, 
                                            nameUsesJobCode, subfolderUsesJobCode, 
                                            self.prefs.strip_characters, fallback_date)
                    # generate thumbnail
                    mediaFile.generateThumbnail(self.videoTempWorkingDir)
                    
                if mediaFile.thumbnail is None:
                    mediaFile.genericThumbnail = True
                    if mediaFile.isImage:
                        mediaFile.thumbnail = self.photoThumbnail
                    else:
                        mediaFile.thumbnail = self.videoThumbnail
            
            def downloadable(name):
                isImage = media.isImage(name)
                isVideo = media.isVideo(name)
                download = (DOWNLOAD_VIDEO and (isImage or isVideo) or 
                        ((not DOWNLOAD_VIDEO) and isImage))
                return (download, isImage, isVideo)
                
            def addFile(name, path, size, modificationTime, device, volume, isImage):
                #~ if debug_info:
                    #~ cmd_line("Scanning %s" % name)
                    
                if isImage:
                    downloadFolder = self.prefs.download_folder
                else:
                    downloadFolder = self.prefs.video_download_folder
                    
                mediaFile = media.MediaFile(self.thread_id, name, path, size, modificationTime, device, downloadFolder, volume, isImage)
                loadFileMetadata(mediaFile)
                # modificationTime is very useful for quick sorting
                imagesAndVideos.append((mediaFile, modificationTime))
                display_queue.put((self.parentApp.addFile, (mediaFile,)))
                
                if isImage:
                    self.noImages += 1
                else:
                    self.noVideos += 1

            
            def gio_scan(path, fileSizeSum):
                """recursive function to scan a directory and its subdirectories
                for photos and possibly videos"""
                
                children = path.enumerate_children('standard::name,standard::type,standard::size,time::modified')

                for child in children:
                    if not self.running:
                        self.lock.acquire()
                        self.running = True
                    
                    if not self.ctrl:
                        return None
                        
                    if child.get_file_type() == gio.FILE_TYPE_DIRECTORY:
                        fileSizeSum = gio_scan(path.get_child(child.get_name()), fileSizeSum)
                        if fileSizeSum == None:
                            # this value will be None only if the thread is exiting
                            return None
                    elif child.get_file_type() == gio.FILE_TYPE_REGULAR:
                        name = child.get_name()
                        download, isImage, isVideo = downloadable(name)
                        if download:
                            size = child.get_size()
                            modificationTime = child.get_modification_time()
                            addFile(name, path.get_path(), size, modificationTime, self.cardMedia.prettyName(limit=0), self.cardMedia.volume, isImage)
                            fileSizeSum += size

                return fileSizeSum
            
                        
            imagesAndVideos = []
            fileSizeSum = 0
            self.noVideos = 0
            self.noImages = 0
                        
            if not using_gio or not self.cardMedia.volume:
                for root, dirs, files in os.walk(self.cardMedia.getPath()):
                    for name in files:
                        if not self.running:
                            self.lock.acquire()
                            self.running = True
                        
                        if not self.ctrl:
                            return None
                        

                        download, isImage, isVideo = downloadable(name)
                        if download:
                            fullFileName = os.path.join(root, name)
                            size = os.path.getsize(fullFileName)
                            modificationTime = os.path.getmtime(fullFileName)
                            addFile(name, root, size, modificationTime, self.cardMedia.prettyName(limit=0), self.cardMedia.volume, isImage)
                            fileSizeSum += size

                            
            else:
                # using gio and have a volume
                # make call to recursive function to scan volume
                fileSizeSum = gio_scan(self.cardMedia.volume.volume.get_root(), fileSizeSum)
                if fileSizeSum == None:
                    # thread exiting
                    return None
                
            # sort in place based on modification time
            imagesAndVideos.sort(key=operator.itemgetter(1))
            noFiles = len(imagesAndVideos)
            
            self.scanComplete = True
            
            self.display_file_types = file_types_by_number(self.noImages, self.noVideos)

            
            if noFiles:
                self.cardMedia.setMedia(imagesAndVideos, fileSizeSum, noFiles)
                # Translators: as already, mentioned the %s value should not be modified or left out. It may be moved if necessary.
                # It refers to the actual number of photos that can be copied. For example, the user might see the following:
                # '0 of 512 photos' or '0 of 10 videos' or '0 of 202 photos and videos'.
                # This particular text is displayed to the user before the download has started.
                display = _("%(number)s %(filetypes)s") % {'number':noFiles, 'filetypes':self.display_file_types}
                display_queue.put((media_collection_treeview.updateCard, (self.thread_id,  self.cardMedia.sizeOfImagesAndVideos())))
                display_queue.put((media_collection_treeview.updateProgress, (self.thread_id, 0.0, display, 0)))
                display_queue.put((self.parentApp.setDownloadButtonSensitivity, ()))
                
                # Translators: as you have already seen, the text can contain values that should not be modified or left out by you, for example %s.
                # This text is another example of that, but it is is a little more complex. Here there are two values which will be displayed
                # to the user when they run the program, signifying the number of photos found, and the device they were found on.
                # %(number)s should be left exactly as is: 'number' should not be translated. The same applies to %(device)s: 'device' should
                # not be translated. Generally speaking, if translating the sentence requires it, you can move items like '%(xyz)s' around 
                # in a sentence, but you should never modify them or leave them out.
                cmd_line(_("Device scan complete: found %(number)s %(filetypes)s on %(device)s") % 
                           {'number': noFiles, 'filetypes':self.display_file_types,
                            'device': self.cardMedia.prettyName(limit=0)})
                return True
            else:
                # it might be better to display "0 of 0" here
                display_queue.put((media_collection_treeview.removeCard,  (self.thread_id, )))
                cmd_line(_("Device scan complete: no %(filetypes)s found on %(device)s") % {'device':self.cardMedia.prettyName(limit=0), 'filetypes':self.types_searched_for})
                return False
            
            
        def logError(severity, problem, details, resolution=None):
            display_queue.put((log_dialog.addMessage, (self.thread_id, severity, problem, details, 
                            resolution)))
            if severity == config.WARNING:
                self.noWarnings += 1
            else:
                self.noErrors += 1

        def notifyAndUnmount(umountAttemptOK):
            if not self.cardMedia.volume:
                unmountMessage = ""
                notificationName = PROGRAM_NAME
            else:
                notificationName  = self.cardMedia.volume.get_name()
                if self.prefs.auto_unmount and umountAttemptOK:
                    self.cardMedia.volume.unmount(self.on_volume_unmount)
                    # This message informs the user that the device (e.g. camera, hard drive or memory card) was automatically unmounted and they can now remove it
                    unmountMessage = _("The device can now be safely removed")
                else:
                    unmountMessage = ""
            
            file_types = file_types_by_number(noImagesDownloaded, noVideosDownloaded)
            file_types_skipped = file_types_by_number(noImagesSkipped, noVideosSkipped)
            message = _("%(noFiles)s %(filetypes)s downloaded") % {'noFiles':noFilesDownloaded, 'filetypes': file_types}
            noFilesSkipped = noImagesSkipped + noVideosSkipped
            if noFilesSkipped:
                message += "\n" + _("%(noFiles)s %(filetypes)s failed to download") % {'noFiles':noFilesSkipped, 'filetypes':file_types_skipped}
            
            if self.noWarnings:
                message = "%s\n%s " % (message,  self.noWarnings) + _("warnings") 
            if self.noErrors:
                message = "%s\n%s " % (message,  self.noErrors) + _("errors")
                
            if unmountMessage:
                message = "%s\n%s" % (message,  unmountMessage)                
                
            n = pynotify.Notification(notificationName,  message)
            
            if self.cardMedia.volume:
                icon = self.cardMedia.volume.get_icon_pixbuf(self.parentApp.notification_icon_size)
            else:
                icon = self.parentApp.application_icon
            
            n.set_icon_from_pixbuf(icon)
            n.show()            

        def createTempDir(baseDir):
            """
            Create a temporary directory in which to download the photos to.
            
            Returns the directory if it was created, else returns None.
            
            Don't want to put it in system temp folder, as that is likely
            to be on another partition and hence copying files from it
            to the actual download folder will be slow!"""
            try:
                t = tempfile.mkdtemp(prefix='rapid-tmp-', 
                                                dir=baseDir)
                return t
            except OSError, (errno, strerror):
                if not self.cardMedia.volume:
                    image_device = _("Source: %s\n") % self.cardMedia.getPath()
                else:
                    _("Device: %s\n") % self.cardMedia.volume.get_name()
                destination = _("Destination: %s") % baseDir
                logError(config.CRITICAL_ERROR, _('Could not create temporary download directory'), 
                             image_device + destination,
                            _("Download cannot proceed"))
                cmd_line(_("Error:") + " " + _('Could not create temporary download directory'))
                cmd_line(image_device + destination)
                cmd_line(_("Download cannot proceed"))
                display_queue.put((media_collection_treeview.removeCard,  (self.thread_id, )))
                display_queue.put((self.parentApp.downloadFailed,  (self.thread_id, )))
                display_queue.close("rw")
                self.running = False
                self.lock.release()
                return None      
            
        def setupBackup():
            """
            Check for presence of backup path or volumes, and return the number of devices being used (1 in case of a path)
            """
            no_devices = 0
            if self.prefs.backup_images:
                no_devices = len(self.parentApp.backupVolumes)          
                if not self.prefs.backup_device_autodetection:
                    if not os.path.isdir(self.prefs.backup_location):
                        # the user has manually specified a path, but it
                        # does not exist. This is a problem.
                        try:
                            os.makedirs(self.prefs.backup_location)
                        except:
                            logError(config.SERIOUS_ERROR, _("Backup path does not exist"),
                                        _("The path %s could not be created") % path, 
                                        _("No backups can occur")
                                    )
                            no_devices = 0
            return no_devices
        
        def checkIfNeedAJobCode():
            needAJobCode = NeedAJobCode(self.prefs)
            
            for f in self.cardMedia.imagesAndVideos:
                mediaFile = f[0]
                if mediaFile.status in [STATUS_WARNING, STATUS_NOT_DOWNLOADED]:
                    if needAJobCode.needAJobCode(mediaFile.jobcode, mediaFile.isImage):
                        return True
            return False
            
        def createBothTempDirs():
            self.photoTempWorkingDir = createTempDir(photoBaseDownloadDir)
            created = self.photoTempWorkingDir is not None
            if created and DOWNLOAD_VIDEO:
                self.videoTempWorkingDir = createTempDir(videoBaseDownloadDir)
                created = self.videoTempWorkingDir is not None
                
            return created


        def checkProblemWithNameGeneration(mediaFile):
            if mediaFile.problem.has_problem():
                logError(config.WARNING, 
                    mediaFile.problem.get_title(),
                    _("Source: %(source)s\nDestination: %(destination)s\n%(problem)s") % 
                    {'source': mediaFile.fullFileName, 'destination': mediaFile.downloadFullFileName, 'problem': mediaFile.problem.get_problems()})
                mediaFile.status = STATUS_DOWNLOADED_WITH_WARNING
                    
        def fileAlreadyExists(mediaFile, identifier=None):
            """ Notify the user that the photo or video could not be downloaded because it already exists"""
            
            # get information on when the existing file was last modified
            try:
                modificationTime = os.path.getmtime(mediaFile.downloadFullFileName)
                dt = datetime.datetime.fromtimestamp(modificationTime)
                date = dt.strftime("%x")
                time = dt.strftime("%X")
            except:
                sys.stderr.write("WARNING: could not determine the file modification time of an existing file\n")
                date = time = ''
                
            if not identifier:
                mediaFile.problem.add_problem(None, pn.FILE_ALREADY_EXISTS_NO_DOWNLOAD, {'filetype':mediaFile.displayNameCap})
                mediaFile.problem.add_extra_detail(pn.EXISTING_FILE, {'filetype': mediaFile.displayName, 'date': date, 'time': time})
                mediaFile.status = STATUS_DOWNLOAD_FAILED
                log_status = config.SERIOUS_ERROR
                problem_text = pn.extra_detail_definitions[pn.EXISTING_FILE] % {'date':date, 'time':time, 'filetype': mediaFile.displayName}
            else:
                mediaFile.problem.add_problem(None, pn.UNIQUE_IDENTIFIER_ADDED, {'filetype':mediaFile.displayNameCap})
                mediaFile.problem.add_extra_detail(pn.UNIQUE_IDENTIFIER, {'identifier': identifier, 'filetype': mediaFile.displayName, 'date': date, 'time': time})
                mediaFile.status = STATUS_DOWNLOADED_WITH_WARNING
                log_status = config.WARNING
                problem_text = pn.extra_detail_definitions[pn.UNIQUE_IDENTIFIER] % {'identifier': identifier, 'filetype': mediaFile.displayName, 'date': date, 'time': time}
                
            logError(log_status, mediaFile.problem.get_title(),
                _("Source: %(source)s\nDestination: %(destination)s")
                % {'source': mediaFile.fullFileName, 'destination': mediaFile.downloadFullFileName},
                problem_text)

        def downloadCopyingError(mediaFile, inst=None, errno=None, strerror=None):
            """Notify the user that an error occurred (most likely at the OS / filesystem level) when coyping a photo or video"""
            
            if errno != None and strerror != None:
                mediaFile.problem.add_problem(None, pn.DOWNLOAD_COPYING_ERROR_W_NO, {'filetype': mediaFile.displayName})
                mediaFile.problem.add_extra_detail(pn.DOWNLOAD_COPYING_ERROR_W_NO_DETAIL, {'errorno': errno, 'strerror': strerror})

            else:
                mediaFile.problem.add_problem(None, pn.DOWNLOAD_COPYING_ERROR, {'filetype': mediaFile.displayName})
                if not inst:
                    # hopefully inst will never be None, but just to be safe...
                    inst = _("Please check your system and try again.") 
                mediaFile.problem.add_extra_detail(pn.DOWNLOAD_COPYING_ERROR_DETAIL, inst)

            logError(config.SERIOUS_ERROR, mediaFile.problem.get_title(), mediaFile.problem.get_problems())
            mediaFile.status = STATUS_DOWNLOAD_FAILED
                
        def sameNameDifferentExif(image_name, mediaFile):
            """Notify the user that a file was already downloaded with the same name, but the exif information was different"""
            i1_ext, i1_date_time, i1_subseconds = downloaded_files.extExifDateTime(image_name)
            detail = {'image1': "%s%s" % (image_name, i1_ext), 
                'image1_date': i1_date_time.strftime("%x"),
                'image1_time': time_subseconds_human_readable(i1_date_time, i1_subseconds), 
                'image2':      mediaFile.name, 
                'image2_date': mediaFile.metadata.dateTime().strftime("%x"),
                'image2_time': time_subseconds_human_readable(
                                    mediaFile.metadata.dateTime(), 
                                    mediaFile.metadata.subSeconds())}
            mediaFile.problem.add_problem(None, pn.SAME_FILE_DIFFERENT_EXIF, detail)

            msg = pn.problem_definitions[pn.SAME_FILE_DIFFERENT_EXIF][1] % detail
            logError(config.WARNING,_('Photos detected with the same filenames, but taken at different times'), msg)
            mediaFile.status = STATUS_DOWNLOADED_WITH_WARNING

        def generateSubfolderAndFileName(mediaFile):
            """
            Generates subfolder and file names for photos and videos
            """
            
            skipFile = alreadyDownloaded = False
            sequence_to_use = None
            
            if mediaFile.isVideo:
                fileRenameFactory = self.videoRenamePrefsFactory
                subfolderFactory = self.videoSubfolderPrefsFactory
            else:
                # file is an photo
                fileRenameFactory = self.imageRenamePrefsFactory                
                subfolderFactory = self.subfolderPrefsFactory
            
            fileRenameFactory.setJobCode(mediaFile.jobcode)
            subfolderFactory.setJobCode(mediaFile.jobcode)

            mediaFile.problem = pn.Problem()
            subfolderFactory.initializeProblem(mediaFile.problem)
            fileRenameFactory.initializeProblem(mediaFile.problem)
            
            # Here we cannot assume that the subfolder value will contain something -- the user may have changed the preferences after the scan
            mediaFile.downloadSubfolder = subfolderFactory.generateNameUsingPreferences(
                                                    mediaFile.metadata, mediaFile.name, 
                                                    self.stripCharacters, fallback_date = mediaFile.modificationTime)


            if self.prefs.synchronize_raw_jpg and usesImageSequenceElements and mediaFile.isImage:
                #synchronizing RAW and JPEG only applies to photos, not videos
                image_name, image_ext = os.path.splitext(mediaFile.name)
                with self.downloadedFilesLock:
                    i, sequence_to_use = downloaded_files.matching_pair(image_name, image_ext, mediaFile.metadata.dateTime(), mediaFile.metadata.subSeconds())
                    if i == -1:
                        # this exact file has already been downloaded (same extension, same filename, and same exif date time subsecond info)
                        if not addUniqueIdentifier:
                            logError(config.SERIOUS_ERROR,_('Photo has already been downloaded'), 
                                        _("Source: %(source)s") % {'source': mediaFile.fullFileName})
                            mediaFile.problem.add_problem(None, pn.FILE_ALREADY_DOWNLOADED, {'filetype': mediaFile.displayNameCap})
                            skipFile = True
                            
                
            # pass the subfolder the image will go into, as this is needed to determine subfolder sequence numbers 
            # indicate that sequences chosen should be queued
            
            if not skipFile:
                mediaFile.downloadName = fileRenameFactory.generateNameUsingPreferences(
                                                            mediaFile.metadata, mediaFile.name, self.stripCharacters,  mediaFile.downloadSubfolder,  
                                                            sequencesPreliminary = True,
                                                            sequence_to_use = sequence_to_use,
                                                            fallback_date = mediaFile.modificationTime)

                mediaFile.downloadPath = os.path.join(mediaFile.downloadFolder, mediaFile.downloadSubfolder)
                mediaFile.downloadFullFileName = os.path.join(mediaFile.downloadPath, mediaFile.downloadName)
                    
                if not mediaFile.downloadName or not mediaFile.downloadSubfolder:
                    if not mediaFile.downloadName and not mediaFile.downloadSubfolder:
                        area = _("subfolder and filename")
                    elif not mediaFile.downloadName:
                        area = _("filename")
                    else:
                        area = _("subfolder")
                    problem.add_problem(None, pn.ERROR_IN_NAME_GENERATION, {'filetype': mediaFile.displayNameCap, 'area': area})
                    problem.add_extra_detail(pn.NO_DATA_TO_NAME, {'filetype': area})
                    skipFile = True
                    logError(config.SERIOUS_ERROR, pn.problem_definitions[ERROR_IN_NAME_GENERATION][1] % {'filetype': mediaFile.displayNameCap, 'area': area})
            
            if not skipFile:
                checkProblemWithNameGeneration(mediaFile)
            else:
                self.sizeDownloaded += mediaFile.size * (no_backup_devices + 1)
                mediaFile.status = STATUS_DOWNLOAD_FAILED
                
            return (skipFile, sequence_to_use)
        
        def progress_callback(amount_downloaded, total):
            if (amount_downloaded - self.bytes_downloaded > 2097152) or (amount_downloaded == total):
                chunk_downloaded = amount_downloaded - self.bytes_downloaded
                self.bytes_downloaded = amount_downloaded
                percentComplete = (float(self.sizeDownloaded + amount_downloaded) / sizeFiles) * 100

                display_queue.put((media_collection_treeview.updateProgress, (self.thread_id, percentComplete, None, chunk_downloaded)))        
        
        def downloadFile(mediaFile, sequence_to_use):
            """
            Downloads the photo or video file to the specified subfolder 
            """
            
            if not mediaFile.isImage:
                renameFactory = self.videoRenamePrefsFactory
            else:
                renameFactory = self.imageRenamePrefsFactory
            
            def progress_callback_no_update(amount_downloaded, total):
                pass
                
            try:
                fileDownloaded = False
                if not os.path.isdir(mediaFile.downloadPath):
                    os.makedirs(mediaFile.downloadPath)
                
                nameUniqueBeforeCopy = True
                downloadNonUniqueFile = True
                
                # do a preliminary check to see if a file with the same name already exists
                if os.path.exists(mediaFile.downloadFullFileName):
                    nameUniqueBeforeCopy = False
                    if not addUniqueIdentifier:
                        downloadNonUniqueFile = False
                        if (usesVideoSequenceElements and not mediaFile.isImage) or (usesImageSequenceElements and mediaFile.isImage and not self.prefs.synchronize_raw_jpg):
                            # potentially, a unique file name could still be generated
                            # investigate this possibility
                            with self.fileSequenceLock:
                                for possibleName in renameFactory.generateNameSequencePossibilities(
                                                        mediaFile.metadata, 
                                                        mediaFile.name, self.stripCharacters, mediaFile.downloadSubfolder):
                                    if possibleName:
                                        # no need to check for any problems here, it's just a temporary name
                                        possibleFile = os.path.join(mediaFile.downloadPath, possibleName)
                                        possibleTempFile = os.path.join(tempWorkingDir, possibleName)
                                        if not os.path.exists(possibleFile) and not os.path.exists(possibleTempFile):
                                            downloadNonUniqueFile = True
                                            break

                                        
                    if not downloadNonUniqueFile:
                        fileAlreadyExists(mediaFile)

                copy_succeeded = False
                if nameUniqueBeforeCopy or downloadNonUniqueFile:
                    tempWorkingfile = os.path.join(tempWorkingDir, mediaFile.downloadName)
                    if using_gio:
                        g_dest = gio.File(path=tempWorkingfile)
                        g_src = gio.File(path=mediaFile.fullFileName)
                        try:
                            if not g_src.copy(g_dest, progress_callback, cancellable=gio.Cancellable()):
                                downloadCopyingError(mediaFile)
                            else:
                                copy_succeeded = True
                        except glib.GError, inst:
                            downloadCopyingError(mediaFile, inst=inst)
                    else:
                        shutil.copy2(mediaFile.fullFileName, tempWorkingfile)
                        copy_succeeded = True
                    
                    if copy_succeeded:
                        with self.fileRenameLock:
                            doRename = True
                            if usesSequenceElements:
                                with self.fileSequenceLock:
                                    # get a filename and use this as the "real" filename
                                    if sequence_to_use is None and self.prefs.synchronize_raw_jpg and mediaFile.isImage:
                                        # must check again, just in case the matching pair has been downloaded in the meantime
                                        image_name, image_ext = os.path.splitext(mediaFile.name)
                                        with self.downloadedFilesLock:
                                            i, sequence_to_use = downloaded_files.matching_pair(image_name, image_ext, mediaFile.metadata.dateTime(), mediaFile.metadata.subSeconds())
                                            if i == -99:
                                                sameNameDifferentExif(image_name, mediaFile)

                                    mediaFile.downloadName = renameFactory.generateNameUsingPreferences(
                                                                    mediaFile.metadata, mediaFile.name, self.stripCharacters, mediaFile.downloadSubfolder,  
                                                                    sequencesPreliminary = False,
                                                                    sequence_to_use = sequence_to_use,
                                                                    fallback_date = mediaFile.modificationTime)
                                                                    
                                if not mediaFile.downloadName:
                                    # there was a serious error generating the filename
                                    doRename = False                            
                                else:
                                    mediaFile.downloadFullFileName = os.path.join(mediaFile.downloadPath, mediaFile.downloadName)
                            # check if the file exists again
                            if os.path.exists(mediaFile.downloadFullFileName):
                                if not addUniqueIdentifier:
                                    doRename = False
                                    fileAlreadyExists(mediaFile)
                                else:
                                    # add  basic suffix to make the filename unique
                                    name = os.path.splitext(mediaFile.downloadName)
                                    suffixAlreadyUsed = True
                                    while suffixAlreadyUsed:
                                        if mediaFile.downloadFullFileName in duplicate_files:
                                            duplicate_files[mediaFile.downloadFullFileName] +=  1
                                        else:
                                            duplicate_files[mediaFile.downloadFullFileName] = 1
                                        identifier = '_%s' % duplicate_files[mediaFile.downloadFullFileName]
                                        mediaFile.downloadName = name[0] + identifier + name[1]
                                        possibleNewFile = os.path.join(mediaFile.downloadPath, mediaFile.downloadName)
                                        suffixAlreadyUsed = os.path.exists(possibleNewFile)

                                    fileAlreadyExists(mediaFile, identifier)
                                    mediaFile.downloadFullFileName = possibleNewFile
                                    

                            if doRename:
                                rename_succeeded = False
                                if using_gio:
                                    g_dest = gio.File(path=mediaFile.downloadFullFileName)
                                    g_src = gio.File(path=tempWorkingfile)
                                    try:
                                        if not g_src.move(g_dest, progress_callback_no_update, cancellable=gio.Cancellable()):
                                            downloadCopyingError(mediaFile)
                                        else:
                                            rename_succeeded = True
                                    except glib.GError, inst:
                                        downloadCopyingError(mediaFile, inst=inst)
                                else:
                                    os.rename(tempWorkingfile, mediaFile.downloadFullFileName)
                                    rename_succeeded = True
                                        
                                if rename_succeeded:
                                    fileDownloaded = True
                                    if mediaFile.status != STATUS_DOWNLOADED_WITH_WARNING:
                                        mediaFile.status = STATUS_DOWNLOADED
                                    if usesImageSequenceElements:
                                        if self.prefs.synchronize_raw_jpg and mediaFile.isImage:
                                            name, ext = os.path.splitext(mediaFile.name)
                                            if sequence_to_use is None:
                                                with self.fileSequenceLock:
                                                    seq = renameFactory.sequences.getFinalSequence()
                                            else:
                                                seq = sequence_to_use
                                            with self.downloadedFilesLock:
                                                downloaded_files.add_download(name, ext, mediaFile.metadata.dateTime(), mediaFile.metadata.subSeconds(), seq) 

                                        
                                        with self.fileSequenceLock:
                                            if sequence_to_use is None:
                                                renameFactory.sequences.imageCopySucceeded()
                                                if usesStoredSequenceNo:
                                                    self.prefs.stored_sequence_no += 1
                                                
                                    with self.fileSequenceLock:
                                        if sequence_to_use is None:
                                            if self.prefs.incrementDownloadsToday():
                                                # A new day, according the user's preferences of what time a day begins, has started
                                                cmd_line(_("New day has started - resetting 'Downloads Today' sequence number"))
                                                
                                                sequences.setDownloadsToday(0)
                    
            except (IOError, OSError), (errno, strerror):
                downloadCopyingError(mediaFile, errno=errno, strerror=strerror)              
            
            if usesSequenceElements:
                if not fileDownloaded and sequence_to_use is None:
                    renameFactory.sequences.imageCopyFailed()
            
            #update record keeping using in tracking progress
            self.sizeDownloaded += mediaFile.size
            self.bytes_downloaded_in_download = self.bytes_downloaded
            
            return fileDownloaded
            

        def backupFile(mediaFile, fileDownloaded, no_backup_devices):
            """ 
            Backup photo or video to path(s) chosen by the user
            
            there are three scenarios: 
            (1) file has just been downloaded and should now be backed up
            (2) file was already downloaded on some previous occassion and should still be backed up, because it hasn't been yet
            (3) file has been backed up already (or at least, a file with the same name already exists)
            
            A backup medium can be used to backup photos or videos, or both. 
            """

            backed_up = False
            fileNotBackedUpMessageDisplayed = False
            error_encountered = False
            expected_bytes_downloaded = self.sizeDownloaded + no_backup_devices * mediaFile.size
            
            if no_backup_devices:
                for rootBackupDir in self.parentApp.backupVolumes:
                    self.bytes_downloaded = 0
                    if self.prefs.backup_device_autodetection:
                        volume = self.parentApp.backupVolumes[rootBackupDir].get_name()
                        if mediaFile.isImage:
                            backupDir = os.path.join(rootBackupDir, self.prefs.backup_identifier)
                        else:
                            backupDir = os.path.join(rootBackupDir, self.prefs.video_backup_identifier)
                    else:
                        # photos and videos will be backed up into the same root folder, which the user has manually specified
                        backupDir = rootBackupDir
                        volume = backupDir # os.path.split(backupDir)[1]
                                                
                    # if user has chosen auto detection, then:
                    # photos should only be backed up to photo backup locations
                    # videos should only be backed up to video backup locations
                    # if user did not choose autodetection, and the backup path doesn't exist, then
                    # will try to create it
                    if os.path.isdir(backupDir) or not self.prefs.backup_device_autodetection:

                        backupPath = os.path.join(backupDir, mediaFile.downloadSubfolder)
                        newBackupFile = os.path.join(backupPath, mediaFile.downloadName)
                        copyBackup = True
                        if os.path.exists(newBackupFile):
                            # this check is of course not thread safe -- it doesn't need to be, because at this stage the file names are going to be unique
                            # (the folder structure is the same as the actual download folders, and the file names are unique in them)
                            copyBackup = self.prefs.backup_duplicate_overwrite  
                            
                            if copyBackup:
                                mediaFile.problem.add_problem(None, pn.BACKUP_EXISTS_OVERWRITTEN, volume)
                            else:
                                mediaFile.problem.add_problem(None, pn.BACKUP_EXISTS, volume)
                            severity = config.SERIOUS_ERROR
                            fileNotBackedUpMessageDisplayed = True

                            title = _("Backup of %(file_type)s already exists") % {'file_type': mediaFile.displayName}
                            details = _("Source: %(source)s\nDestination: %(destination)s") \
                                    % {'source': mediaFile.fullFileName, 'destination': newBackupFile}
                            if copyBackup:
                                resolution = _("Backup %(file_type)s overwritten") % {'file_type': mediaFile.displayName}
                            else:
                                if self.prefs.backup_device_autodetection:
                                    volume = self.parentApp.backupVolumes[rootBackupDir].get_name()
                                    resolution = _("%(file_type)s not backed up to %(volume)s") % {'file_type': mediaFile.displayNameCap, 'volume': volume}
                                else:
                                    resolution = _("%(file_type)s not backed up") % {'file_type': mediaFile.displayNameCap}                                
                            logError(severity, title, details, resolution)

                        if copyBackup:
                            if fileDownloaded:
                                fileToCopy = mediaFile.downloadFullFileName
                            else:
                                fileToCopy = mediaFile.fullFileName
                            if os.path.isdir(backupPath):
                                pathExists = True
                            else:
                                pathExists = False
                                # create the backup subfolders
                                if using_gio:
                                    dirs = gio.File(backupPath)
                                    try:
                                        if dirs.make_directory_with_parents(cancellable=gio.Cancellable()):
                                            pathExists = True
                                    except glib.GError, inst:
                                        fileNotBackedUpMessageDisplayed = True
                                        mediaFile.problem.add_problem(None, pn.BACKUP_DIRECTORY_CREATION, volume)
                                        mediaFile.problem.add_extra_detail('%s%s' % (pn.BACKUP_DIRECTORY_CREATION, volume), inst)
                                        error_encountered = True
                                        logError(config.SERIOUS_ERROR, _('Backing up error'), 
                                                 _("Destination directory could not be created: %(directory)s\n") %
                                                 {'directory': backupPath,  } +
                                                 _("Source: %(source)s\nDestination: %(destination)s") % 
                                                 {'source': mediaFile.fullFileName, 'destination': newBackupFile} + "\n" +
                                                 _("Error: %(inst)s") % {'inst': inst}, 
                                                 _('The %(file_type)s was not backed up.') % {'file_type': mediaFile.displayName}
                                                 )                                        
                                else:
                                    # recreate folder structure in backup location
                                    # cannot do os.makedirs(backupPath) - it can give bad results when using external drives
                                    # we know backupDir exists 
                                    # all the components of subfolder may not
                                    folders = mediaFile.downloadSubfolder.split(os.path.sep)
                                    folderToMake = backupDir 
                                    for f in folders:
                                        if f:
                                            folderToMake = os.path.join(folderToMake,  f)
                                            if not os.path.isdir(folderToMake):
                                                try:
                                                    os.mkdir(folderToMake)
                                                    pathExists = True
                                                except (IOError, OSError), (errno, strerror):
                                                    fileNotBackedUpMessageDisplayed = True
                                                    inst = "%s: %s" % (errno, strerror)
                                                    mediaFile.problem.add_problem(None, pn.BACKUP_DIRECTORY_CREATION, volume)
                                                    mediaFile.problem.add_extra_detail('%s%s' % (pn.BACKUP_DIRECTORY_CREATION, volume), inst)
                                                    error_encountered = True
                                                    logError(config.SERIOUS_ERROR, _('Backing up error'), 
                                                             _("Destination directory could not be created: %(directory)s\n") %
                                                             {'directory': backupPath,  } +
                                                             _("Source: %(source)s\nDestination: %(destination)s") % 
                                                             {'source': mediaFile.fullFileName, 'destination': newBackupFile} + "\n" +
                                                             _("Error: %(errno)s %(strerror)s") % {'errno': errno,  'strerror': strerror}, 
                                                             _('The %(file_type)s was not backed up.') % {'file_type': mediaFile.displayName}
                                                             )

                                                    break
                                        
                            if pathExists:
                                if using_gio:
                                    g_dest = gio.File(path=newBackupFile)
                                    g_src = gio.File(path=fileToCopy)
                                    if self.prefs.backup_duplicate_overwrite:
                                        flags = gio.FILE_COPY_OVERWRITE
                                    else:
                                        flags = gio.FILE_COPY_NONE
                                    try:
                                        if not g_src.copy(g_dest, progress_callback, flags, cancellable=gio.Cancellable()):
                                            fileNotBackedUpMessageDisplayed = True
                                            mediaFile.problem.add_problem(None, pn.BACKUP_ERROR, volume)
                                            error_encountered = True
                                        else:
                                            backed_up = True
                                            if mediaFile.status == STATUS_DOWNLOAD_FAILED:
                                                mediaFile.problem.add_problem(None, pn.NO_DOWNLOAD_WAS_BACKED_UP, volume)
                                    except glib.GError, inst:
                                        fileNotBackedUpMessageDisplayed = True
                                        mediaFile.problem.add_problem(None, pn.BACKUP_ERROR, volume)
                                        mediaFile.problem.add_extra_detail('%s%s' % (pn.BACKUP_ERROR, volume), inst)
                                        error_encountered = True
                                        logError(config.SERIOUS_ERROR, _('Backing up error'), 
                                                _("Source: %(source)s\nDestination: %(destination)s") %
                                                 {'source': fileToCopy, 'destination': newBackupFile} + "\n" +
                                                _("Error: %(inst)s") % {'inst': inst},
                                                _('The %(file_type)s was not backed up.')  % {'file_type': mediaFile.displayName}
                                            )
                                else:
                                    try:
                                        shutil.copy2(fileToCopy, newBackupFile)
                                        backed_up = True
                                        if mediaFile.status == STATUS_DOWNLOAD_FAILED:
                                            mediaFile.problem.add_problem(None, pn.NO_DOWNLOAD_WAS_BACKED_UP, volume)
                                        
                                    except (IOError, OSError), (errno, strerror):
                                        fileNotBackedUpMessageDisplayed = True
                                        mediaFile.problem.add_problem(None, pn.BACKUP_ERROR, volume)
                                        inst = "%s: %s" % (errno, strerror)
                                        mediaFile.problem.add_extra_detail('%s%s' % (pn.BACKUP_ERROR, volume), inst)
                                        error_encountered = True
                                        logError(config.SERIOUS_ERROR, _('Backing up error'), 
                                                _("Source: %(source)s\nDestination: %(destination)s") % 
                                                 {'source': fileToCopy, 'destination': newBackupFile} + "\n" +
                                                _("Error: %(errno)s %(strerror)s") % {'errno': errno,  'strerror': strerror},
                                                _('The %(file_type)s was not backed up.')  % {'file_type': mediaFile.displayName}
                                            )
                    
                    #update record keeping using in tracking progress
                    self.sizeDownloaded += mediaFile.size
                    self.bytes_downloaded_in_backup += self.bytes_downloaded

            if not backed_up and not fileNotBackedUpMessageDisplayed:
                # The file has not been backed up to any medium
                mediaFile.problem.add_problem(None, pn.NO_BACKUP_PERFORMED, {'filetype': mediaFile.displayNameCap})

                severity = config.SERIOUS_ERROR
                problem = _("%(file_type)s could not be backed up") % {'file_type': mediaFile.displayName}
                details = _("Source: %(source)s") % {'source': mediaFile.fullFileName}
                if self.prefs.backup_device_autodetection:
                    resolution = _("No suitable backup volume was found")
                else:
                    resolution = _("A backup location was not found")
                logError(severity, problem, details, resolution)    

            if backed_up and mediaFile.status == STATUS_DOWNLOAD_FAILED:
                mediaFile.problem.add_extra_detail(pn.BACKUP_OK_TYPE, mediaFile.displayNameCap)
            
            if not backed_up:
                if mediaFile.status == STATUS_DOWNLOAD_FAILED:
                    mediaFile.status = STATUS_DOWNLOAD_AND_BACKUP_FAILED
                else:
                    mediaFile.status = STATUS_BACKUP_PROBLEM
            elif error_encountered:
                # it was backed up to at least one volume, but there was an error on another backup volume
                if mediaFile.status != STATUS_DOWNLOAD_FAILED:
                    mediaFile.status = STATUS_BACKUP_PROBLEM
            
            # Take into account instances where a backup device has been removed part way through a download
            # (thereby making self.parentApp.backupVolumes have less items than expected)
            if self.sizeDownloaded < expected_bytes_downloaded:
                self.sizeDownloaded = expected_bytes_downloaded
            return backed_up

        
        self.hasStarted = True
        display_queue.open('w')

        #Do not try to handle any preference errors here
        getPrefs(False)
        
        #Check photo and video download path, create if necessary
        photoBaseDownloadDir = self.prefs.download_folder
        if not checkDownloadPath(photoBaseDownloadDir):
            return # cleanup already done

        if DOWNLOAD_VIDEO:
            videoBaseDownloadDir = self.prefs.video_download_folder
            if not checkDownloadPath(videoBaseDownloadDir):
                return
        else:
            videoBaseDownloadDir = self.videoTempWorkingDir = None
            
        if not createBothTempDirs():
            return 
        
        s = scanMedia()
        if s is None:
            if not self.ctrl:
                self.running = False
                display_queue.put((media_collection_treeview.removeCard, (self.thread_id, )))
                display_queue.close("rw")
                return
            else:
                sys.stderr.write("FIXME: scan returned None, but the thread is not meant to be exiting\n")
        if not s:
            cmd_line(_("This device has no %(types_searched_for)s to download from.") % {'types_searched_for': self.types_searched_for})
            display_queue.put((self.parentApp.downloadFailed, (self.thread_id, )))
            display_queue.close("rw")
            self.running = False
            return
        
        if self.scanResultsStale or self.scanResultsStaleDownloadFolder:
            display_queue.put((self.parentApp.regenerateScannedDevices, (self.thread_id, )))
        all_files_downloaded = False
        
        totalNonErrorFiles = self.cardMedia.numberOfFilesNotCannotDownload()
        
        if not self.autoStart:
            # halt thread, waiting to be restarted so download proceeds
            self.cleanUp()
            self.running = False
            self.lock.acquire()

            if not self.ctrl:
                # thread will restart at this point, when the program is exiting
                # so must exit if self.ctrl indicates this

                self.running = False
                display_queue.close("rw")
                return

            self.running = True
            if not createBothTempDirs():
                return
                
        else:
            if need_job_code_for_renaming:
                if checkIfNeedAJobCode():
                    if job_code == None:
                        self.cleanUp()
                        self.waitingForJobCode = True
                        display_queue.put((self.parentApp.getJobCode, ()))
                        self.running = False
                        self.lock.acquire()

                        if not self.ctrl:
                            # thread is exiting
                            display_queue.close("rw")
                            return

                        self.running = True                        
                        self.waitingForJobCode = False
                        if not createBothTempDirs():
                            return
                    else:
                        # User has entered a job code, and it's in the global variable
                        # Assign it to all those files that do not have one
                        display_queue.put((self.parentApp.selection_vbox.selection_treeview.apply_job_code, (job_code, False, True, self.thread_id)))

            # auto start could be false if the user hit cancel when prompted for a job code
            if self.autoStart:
                # set all in this thread to download pending
                display_queue.put((self.parentApp.selection_vbox.selection_treeview.set_status_to_download_pending, (False, self.thread_id)))
                # wait until all the files have had their status set to download pending, and once that is done, restart
                self.running = False
                self.lock.acquire()
                self.running = True
                
                # set download started time
                display_queue.put((self.parentApp.setDownloadStartTime, ()))

        while not all_files_downloaded:

            # set the download start time to be the time that the user clicked the download button, or if on auto start, the value just set
            i = 0
            while self.parentApp.download_start_time is None or i > 2:
                time.sleep(0.5)
                i += 1
            
            if self.parentApp.download_start_time:
                start_time = self.parentApp.download_start_time
            else:
                # in a bizarre corner case situation, with mulitple cards of greatly varying size, 
                # it's possible the start time was set above and then in the meantime unset (very unlikely, but conceivably it could happen)
                # fall back to the current time in this less than satisfactory situation
                start_time = datetime.datetime.now()
                
            self.imageRenamePrefsFactory.setDownloadStartTime(start_time)
            self.subfolderPrefsFactory.setDownloadStartTime(start_time)
            if DOWNLOAD_VIDEO:
                self.videoRenamePrefsFactory.setDownloadStartTime(start_time)
                self.videoSubfolderPrefsFactory.setDownloadStartTime(start_time)
            
            self.noErrors = self.noWarnings = 0
            
            if not getPrefs(True):
                    self.running = False
                    display_queue.close("rw")           
                    return
             
            self.downloadStarted = True
            cmd_line(_("Download has started from %s") % self.cardMedia.prettyName(limit=0))
            
            
            noFiles, sizeFiles, fileIndex = self.cardMedia.sizeAndNumberDownloadPending()
            cmd_line(_("Attempting to download %s files") % noFiles)
                        
            no_backup_devices = setupBackup()

            # include the time it takes to copy to the backup volumes
            sizeFiles = sizeFiles * (no_backup_devices + 1)
            
            display_queue.put((self.parentApp.timeRemaining.set, (self.thread_id, sizeFiles)))
            
            i = 0
            self.sizeDownloaded = noFilesDownloaded = noImagesDownloaded = noVideosDownloaded = noImagesSkipped = noVideosSkipped = 0
            filesDownloadedSuccessfully = []
            self.bytes_downloaded_in_backup = 0
            
            display_queue.put((self.parentApp.addToTotalDownloadSize, (sizeFiles, )))
            display_queue.put((self.parentApp.setOverallDownloadMark, ()))
            display_queue.put((self.parentApp.postStartDownloadTasks,  ()))
            
            sizeFiles = float(sizeFiles)

            addUniqueIdentifier = self.prefs.download_conflict_resolution == config.ADD_UNIQUE_IDENTIFIER
            usesImageSequenceElements = self.imageRenamePrefsFactory.usesSequenceElements()
            usesVideoSequenceElements = self.videoRenamePrefsFactory.usesSequenceElements()
            usesSequenceElements = usesVideoSequenceElements or usesImageSequenceElements
            
            usesStoredSequenceNo = (self.imageRenamePrefsFactory.usesTheSequenceElement(rn.STORED_SEQ_NUMBER) or
                                    self.videoRenamePrefsFactory.usesTheSequenceElement(rn.STORED_SEQ_NUMBER))
            sequences.setUseOfSequenceElements(
                self.imageRenamePrefsFactory.usesTheSequenceElement(rn.SESSION_SEQ_NUMBER), 
                self.imageRenamePrefsFactory.usesTheSequenceElement(rn.SEQUENCE_LETTER))
            
            # reset the progress bar to update the status of this download attempt
            progressBarText = _("%(number)s of %(total)s %(filetypes)s") % {'number':  0, 'total': noFiles, 'filetypes':self.display_file_types}
            display_queue.put((media_collection_treeview.updateProgress, (self.thread_id, 0.0, progressBarText, 0)))
            
            
            while i < noFiles:
                # if the user pauses the download, then this will be triggered
                if not self.running:
                    self.lock.acquire()
                    self.running = True
                
                if not self.ctrl:
                    self.running = False
                    self.cleanUp()
                    display_queue.close("rw")
                    return
                
                # get information about the image to deduce image name and path
                mediaFile = self.cardMedia.imagesAndVideos[fileIndex[i]][0]
                if not mediaFile.status == STATUS_DOWNLOAD_PENDING:
                    sys.stderr.write("FIXME: Thread %s is trying to download a file that it should not be!!" % self.thread_id)
                else:
                    self.bytes_downloaded_in_download = self.bytes_downloaded_in_backup = self.bytes_downloaded = 0
                    if mediaFile.isImage:
                        tempWorkingDir = self.photoTempWorkingDir
                        baseDownloadDir = photoBaseDownloadDir
                    else:
                        tempWorkingDir = self.videoTempWorkingDir
                        baseDownloadDir = videoBaseDownloadDir
                        
                    skipFile, sequence_to_use = generateSubfolderAndFileName(mediaFile)

                    if skipFile:
                        if mediaFile.isImage:
                            noImagesSkipped += 1
                        else:
                            noVideosSkipped += 1
                    else:
                        fileDownloaded = downloadFile(mediaFile, sequence_to_use)

                        if self.prefs.backup_images:
                            backed_up = backupFile(mediaFile, fileDownloaded, no_backup_devices)

                        if fileDownloaded:
                            noFilesDownloaded += 1
                            if mediaFile.isImage:
                                noImagesDownloaded += 1
                            else:
                                noVideosDownloaded += 1
                            if self.prefs.backup_images and backed_up:
                                filesDownloadedSuccessfully.append(mediaFile.fullFileName)
                            elif not self.prefs.backup_images:
                                filesDownloadedSuccessfully.append(mediaFile.fullFileName)
                        else:
                            if mediaFile.isImage:
                                noImagesSkipped += 1
                            else:
                                noVideosSkipped += 1
                                
                    #update the selction treeview in the main window with the new status of the file
                    display_queue.put((self.parentApp.update_status_post_download, (mediaFile.treerowref, )))

                percentComplete = (float(self.sizeDownloaded) / sizeFiles) * 100
                    
                if self.sizeDownloaded == sizeFiles and (totalNonErrorFiles - noFiles):
                    progressBarText = _("%(number)s of %(total)s %(filetypes)s (%(remaining)s remaining)") % {
                                        'number':  i + 1, 'total': noFiles, 'filetypes':self.display_file_types,
                                        'remaining': totalNonErrorFiles - noFiles}
                else:
                    progressBarText = _("%(number)s of %(total)s %(filetypes)s") % {'number':  i + 1, 'total': noFiles, 'filetypes':self.display_file_types}
                
                if using_gio:
                    # do not want to update the progress bar any more than it has already been updated
                    size = mediaFile.size * (no_backup_devices + 1) - self.bytes_downloaded_in_download - self.bytes_downloaded_in_backup
                else:
                    size = mediaFile.size * (no_backup_devices + 1)
                display_queue.put((media_collection_treeview.updateProgress, (self.thread_id, percentComplete, progressBarText, size)))
                
                i += 1
            
            with self.statsLock:
                self.downloadStats.adjust(self.sizeDownloaded, noImagesDownloaded, noVideosDownloaded, noImagesSkipped, noVideosSkipped, self.noWarnings, self.noErrors)
                
            if self.prefs.auto_delete:
                j = 0
                for imageOrVideo in filesDownloadedSuccessfully:
                    try:
                        os.unlink(imageOrVideo)
                        j += 1
                    except OSError, (errno, strerror):
                        logError(config.SERIOUS_ERROR,  _("Could not delete photo or video from device"),  
                                _("Photo: %(source)s\nError: %(errno)s %(strerror)s")
                                % {'source': image, 'errno': errno,  'strerror': strerror})
                    except:
                        logError(config.SERIOUS_ERROR,  _("Could not delete photo or video from device"),  
                                _("Photo: %(source)s"))
                        
                cmd_line(_("Deleted %(number)i %(filetypes)s from device") % {'number':j, 'filetypes':self.display_file_types})
                
            totalNonErrorFiles = totalNonErrorFiles - noFiles
            if totalNonErrorFiles == 0:
                all_files_downloaded = True
                
                # must manually delete these variables, or else the media cannot be unmounted (bug in some versions of pyexiv2 / exiv2)
                # for some reason directories on the device remain open with read only access, even after these steps - I don't know why
                del self.subfolderPrefsFactory, self.imageRenamePrefsFactory, self.videoSubfolderPrefsFactory, self.videoRenamePrefsFactory
                for i in self.cardMedia.imagesAndVideos:
                    i[0].metadata = None
                
            notifyAndUnmount(umountAttemptOK = all_files_downloaded)
            cmd_line(_("Download complete from %s") % self.cardMedia.prettyName(limit=0))
            display_queue.put((self.parentApp.notifyUserAllDownloadsComplete,()))
            display_queue.put((self.parentApp.resetSequences,()))
            
            if all_files_downloaded:
                self.downloadComplete = True
            else:
                self.cleanUp()
                self.downloadStarted = False
                self.running = False
                self.lock.acquire()
                if not self.ctrl:
                    # thread will restart at this point, when the program is exiting
                    # so must exit if self.ctrl indicates this

                    self.running = False
                    display_queue.close("rw")
                    return
                self.running = True
                if not createBothTempDirs():
                    return


        display_queue.put((self.parentApp.exitOnDownloadComplete, ()))
        display_queue.close("rw")

        self.cleanUp()
                
        self.running = False
        if noFiles:
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
    
    def cleanUp(self):
        """
        Deletes temporary files and folders
        """

        for tempWorkingDir in (self.videoTempWorkingDir, self.photoTempWorkingDir):
            if tempWorkingDir:
                # possibly delete any lingering files
                if os.path.isdir(tempWorkingDir):
                    tf = os.listdir(tempWorkingDir)
                    if tf:
                        for f in tf:
                            os.remove(os.path.join(tempWorkingDir, f))
                    os.rmdir(tempWorkingDir)
                    
    def quit(self):
        """ 
        Quits the thread 
        
        A thread can be in one of four states:
        
        Not started (not alive, nothing to do)
        Started and actively running (alive)
        Started and paused (alive)
        Completed (not alive, nothing to do)
        """
        
        # cleanup any temporary directories and files
        self.cleanUp()
        
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
    TreeView display of devices and associated copying progress.
    
    Assumes a threaded environment.
    """
    def __init__(self, parentApp):

        self.parentApp = parentApp
        # device name, size of images on the device (human readable), copy progress (%), copy text
        self.liststore = gtk.ListStore(str, str, float, str)
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
                                    gtk.CellRendererProgress(), value=2, text=3)
        self.append_column(column2)
        self.show_all()
        
    def addCard(self, thread_id, cardName, sizeFiles, progress = 0.0, progressBarText = ''):
        
        # add the row, and get a temporary pointer to the row
        iter = self.liststore.append((cardName, sizeFiles, progress, progressBarText))
        
        self._setThreadMap(thread_id, iter)
        
        # adjust scrolled window height, based on row height and number of ready to start downloads
        if workers.noReadyToStartWorkers() >= 1 or workers.noRunningWorkers() > 0:
            # please note, at program startup, self.rowHeight() will be less than it will be when already running
            # e.g. when starting with 3 cards, it could be 18, but when adding 2 cards to the already running program
            # (with one card at startup), it could be 21
            height = (workers.noReadyToStartWorkers() + workers.noRunningWorkers() + 2) * (self.rowHeight())
            self.parentApp.media_collection_scrolledwindow.set_size_request(-1,  height)

        
    def updateCard(self, thread_id, totalSizeFiles):
        """
        Updates the size of the photos and videos on the device, displayed to the user
        """
        if thread_id in self.mapThreadToRow:
            iter = self._getThreadMap(thread_id)
            self.liststore.set_value(iter, 1, totalSizeFiles)
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
        
        if thread_id in self.mapThreadToRow:
            treerowRef = self.mapThreadToRow[thread_id]
            path = treerowRef.get_path()
            iter = self.liststore.get_iter(path)
            return iter
        else:
            return None
    
    def updateProgress(self, thread_id, percentComplete, progressBarText, bytesDownloaded):
        
        iter = self._getThreadMap(thread_id)
        if iter:
            self.liststore.set_value(iter, 2, percentComplete)
            if progressBarText:
                self.liststore.set_value(iter, 3, progressBarText)
            if percentComplete or bytesDownloaded:
                self.parentApp.updateOverallProgress(thread_id, bytesDownloaded, percentComplete)
        

    def rowHeight(self):
        if not self.mapThreadToRow:
            return 0
        else:
            index = self.mapThreadToRow.keys()[0]
            path = self.mapThreadToRow[index].get_path()
            col = self.get_column(0)
            return self.get_background_area(path, col)[3] + 1


class ShowWarningDialog(gtk.Dialog):
    """
    Displays a warning to the user that downloading directly from a 
    camera does not always work well
    """ 
    def __init__(self, parent_window, postChoiceCB):
        gtk.Dialog.__init__(self, _("Downloading From Cameras"), None,
                   gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                   (gtk.STOCK_OK, gtk.RESPONSE_OK))
                        
        self.postChoiceCB = postChoiceCB
        
        primary_msg = _("Downloading directly from a camera may work poorly or not at all")
        secondary_msg = _("Downloading from a card reader always works and is generally much faster. It is strongly recommended to use a card reader.")
        
        self.set_icon_from_file(paths.share_dir('glade3/rapid-photo-downloader.svg'))

        primary_label = gtk.Label()
        primary_label.set_markup("<b>%s</b>" % primary_msg)
        primary_label.set_line_wrap(True)
        primary_label.set_alignment(0, 0.5)

        secondary_label = gtk.Label()
        secondary_label.set_text(secondary_msg)
        secondary_label.set_line_wrap(True)
        secondary_label.set_alignment(0, 0.5)

        self.show_again_checkbutton = gtk.CheckButton(_('_Show this message again'), True)
        self.show_again_checkbutton.set_active(True)
        
        msg_vbox = gtk.VBox()
        msg_vbox.pack_start(primary_label, False, False, padding=6)
        msg_vbox.pack_start(secondary_label, False, False, padding=6)        
        msg_vbox.pack_start(self.show_again_checkbutton)

        icon = parent_window.render_icon(gtk.STOCK_DIALOG_WARNING, gtk.ICON_SIZE_DIALOG)
        image = gtk.Image()
        image.set_from_pixbuf(icon)
        image.set_alignment(0, 0)
            
        warning_hbox = gtk.HBox()
        warning_hbox.pack_start(image, False, False, padding = 12)
        warning_hbox.pack_start(msg_vbox, False, False, padding = 12)
            
        self.vbox.pack_start(warning_hbox, padding=6)

        self.set_border_width(6)
        self.set_has_separator(False)   
        
        self.set_default_response(gtk.RESPONSE_OK)
      
        self.set_transient_for(parent_window)
        self.show_all()
        
        self.connect('response', self.on_response)
        
    def on_response(self,  device_dialog, response):
        show_again = self.show_again_checkbutton.get_active()
        self.postChoiceCB(self,  show_again)

class UseDeviceDialog(gtk.Dialog):
    def __init__(self,  parent_window,  path,  volume,  autostart, postChoiceCB):
        gtk.Dialog.__init__(self, _('Device Detected'), None,
                   gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                   (gtk.STOCK_NO, gtk.RESPONSE_CANCEL, 
                   gtk.STOCK_YES, gtk.RESPONSE_OK))
                        
        self.postChoiceCB = postChoiceCB
        
        self.set_icon_from_file(paths.share_dir('glade3/rapid-photo-downloader.svg'))
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#usedeviceprompt
        prompt_label = gtk.Label(_('Should this device or partition be used to download photos or videos from?'))
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
                          
class RemoveAllJobCodeDialog(gtk.Dialog):
    def __init__(self, parent_window, postChoiceCB):
        gtk.Dialog.__init__(self, _('Remove all Job Codes?'), None,
                   gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                   (gtk.STOCK_NO, gtk.RESPONSE_CANCEL, 
                   gtk.STOCK_YES, gtk.RESPONSE_OK))
                        
        self.postChoiceCB = postChoiceCB        
        self.set_icon_from_file(paths.share_dir('glade3/rapid-photo-downloader.svg'))
        
        prompt_hbox = gtk.HBox()
        
        icontheme = gtk.icon_theme_get_default()
        icon = icontheme.load_icon('gtk-dialog-question', 36, gtk.ICON_LOOKUP_USE_BUILTIN)        
        if icon:
            image = gtk.Image()
            image.set_from_pixbuf(icon)
            prompt_hbox.pack_start(image, False, False, padding = 6)
            
        prompt_label = gtk.Label(_('Should all Job Codes be removed?'))
        prompt_label.set_line_wrap(True)
        prompt_hbox.pack_start(prompt_label, False, False, padding=6)
                    
        self.vbox.pack_start(prompt_hbox, padding=6)

        self.set_border_width(6)
        self.set_has_separator(False)   
        
        self.set_default_response(gtk.RESPONSE_OK)
      
       
        self.set_transient_for(parent_window)
        self.show_all()

        
        self.connect('response', self.on_response)
        
    def on_response(self,  device_dialog, response):
        userSelected = response == gtk.RESPONSE_OK
        self.postChoiceCB(self, userSelected)   
        
        
class JobCodeDialog(gtk.Dialog):
    """ Dialog prompting for a job code"""
    
    def __init__(self, parent_window, job_codes,  default_job_code, postJobCodeEntryCB, autoStart, downloadSelected, entryOnly):
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#jobcode
        gtk.Dialog.__init__(self,  _('Enter a Job Code'), None,
                   gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                   (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, 
                   gtk.STOCK_OK, gtk.RESPONSE_OK))
                        
        
        self.set_icon_from_file(paths.share_dir('glade3/rapid-photo-downloader.svg'))
        self.postJobCodeEntryCB = postJobCodeEntryCB
        self.autoStart = autoStart
        self.downloadSelected = downloadSelected
        
        self.combobox = gtk.combo_box_entry_new_text()
        for text in job_codes:
            self.combobox.append_text(text)
            
        self.job_code_hbox = gtk.HBox(homogeneous = False)
        
        if len(job_codes) and not entryOnly:
            # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#jobcode
            task_label = gtk.Label(_('Enter a new Job Code, or select a previous one'))
        else:
            # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#jobcode
            task_label = gtk.Label(_('Enter a new Job Code'))            
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
         return model[iter][0].lower().startswith(self.entry.get_text().lower())
         
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
        self.postJobCodeEntryCB(self, userChoseCode, self.get_job_code(), self.autoStart, self.downloadSelected)



class SelectionTreeView(gtk.TreeView):
    """
    TreeView display of photos and videos available for download
    
    Assumes a threaded environment.
    """
    def __init__(self, parentApp):

        self.parentApp = parentApp
        self.rapidApp = parentApp.parentApp
        
        self.liststore = gtk.ListStore(
                         gtk.gdk.Pixbuf,        # 0 thumbnail icon
                         str,                   # 1 name (for sorting)
                         int,                   # 2 timestamp (for sorting), float converted into an int
                         str,                   # 3 date (human readable)
                         int,                   # 4 size (for sorting)
                         str,                   # 5 size (human readable)
                         int,                   # 6 isImage (for sorting)
                         gtk.gdk.Pixbuf,        # 7 type (photo or video)
                         str,                   # 8 job code
                         gobject.TYPE_PYOBJECT, # 9 mediaFile (for data)
                         gtk.gdk.Pixbuf,        # 10 status icon
                         int,                   # 11 status (downloaded, cannot download, etc, for sorting)
                         str,                   # 12 path (on the device)
                         str,                   # 13 device
                         int)                   # 14 thread id (worker the file is associated with)
                         
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
        
        
        
    def get_thread(self, iter):
        """
        Returns the thread associated with the liststore's iter
        """
        return self.liststore.get_value(iter, 14)
        
    def get_status(self, iter):
        """
        Returns the status associated with the liststore's iter
        """
        return self.liststore.get_value(iter, 11)
        
    def get_mediaFile(self, iter):
        """
        Returns the mediaFile associated with the liststore's iter
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
            tree_row_refs.append(self.get_mediaFile(iter).treerowref)
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
            tree_row_refs.append(self.get_mediaFile(iter).treerowref)
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
    
    def add_file(self, mediaFile):
        if debug_info:
            cmd_line('Adding file %s' % mediaFile.fullFileName)
        if mediaFile.metadata:
            date = mediaFile.dateTime()
            timestamp = mediaFile.metadata.timeStamp(missing=None)
            if timestamp is None:
                timestamp = mediaFile.modificationTime
        else:
            timestamp = mediaFile.modificationTime
            date = datetime.datetime.fromtimestamp(timestamp)

        timestamp = int(timestamp)
            
        date_human_readable = date_time_human_readable(date)
        name = mediaFile.name
        size = mediaFile.size
        thumbnail = mediaFile.thumbnail
        thumbnail_icon = common.scale2pixbuf(60, 36, thumbnail)
        #thumbnail_icon = common.scale2pixbuf(80, 48, mediaFile.thumbnail)
        if DROP_SHADOW:
            if not mediaFile.genericThumbnail:
                pil_image = pixbuf_to_image(thumbnail_icon)
                pil_image = self.iconDropShadow.dropShadow(pil_image)
                thumbnail_icon = image_to_pixbuf(pil_image)
            else:
                if mediaFile.isImage:
                    thumbnail_icon = self.generic_photo_with_shadow
                else:
                    thumbnail_icon = self.generic_video_with_shadow
        
        if mediaFile.isImage:
            type_icon = self.icon_photo
        else:
            type_icon = self.icon_video

        status_icon = self.get_status_icon(mediaFile.status)
        
        if debug_info:
            cmd_line('Thumbnail icon: %s' % thumbnail_icon)
            cmd_line('Name: %s' % name)
            cmd_line('Timestamp: %s' % timestamp)
            cmd_line('Date: %s' % date_human_readable)
            cmd_line('Size: %s %s' % (size, common.formatSizeForUser(size)))
            cmd_line('Is an image: %s' % mediaFile.isImage)
            cmd_line('Status: %s' % self.status_human_readable(mediaFile))
            cmd_line('Path: %s' % mediaFile.path)
            cmd_line('Device name: %s' % mediaFile.deviceName)
            cmd_line('Thread: %s' % mediaFile.thread_id)
            cmd_line(' ')

        iter = self.liststore.append((thumbnail_icon, name, timestamp, date_human_readable, size, common.formatSizeForUser(size), mediaFile.isImage, type_icon, '', mediaFile, status_icon, mediaFile.status, mediaFile.path, mediaFile.deviceName, mediaFile.thread_id))
        
        #create a reference to this row and store it in the mediaFile
        path = self.liststore.get_path(iter)
        mediaFile.treerowref = gtk.TreeRowReference(self.liststore, path)
        
        if mediaFile.status in [STATUS_CANNOT_DOWNLOAD, STATUS_WARNING]:
            if not self.user_has_clicked_header:
                self.liststore.set_sort_column_id(11, gtk.SORT_DESCENDING)
        
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
        self.update_download_selected_button()
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
                ref = self.get_mediaFile(iter).treerowref
                
                if ref not in self.selected_rows:
                    self.show_preview(iter)
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
                        mediaFile = self.get_mediaFile(iter)
                        if mediaFile.treerowref == self.previewed_file_treerowref:
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
                    mediaFile = self.get_mediaFile(iter)
                    if mediaFile.isImage:
                        mediaFile.downloadFolder = self.rapidApp.prefs.download_folder
                    else:
                        mediaFile.downloadFolder = self.rapidApp.prefs.video_download_folder
                    mediaFile.samplePath = os.path.join(mediaFile.downloadFolder, mediaFile.sampleSubfolder)
                    if mediaFile.treerowref == self.previewed_file_treerowref:
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
                    mediaFile = self.get_mediaFile(iter)
                    self.generateSampleSubfolderAndName(mediaFile, iter)
                    if mediaFile.treerowref == self.previewed_file_treerowref:
                        self.show_preview(iter)
    
    def generateSampleSubfolderAndName(self, mediaFile, iter):
        problem = pn.Problem()
        if mediaFile.isImage:
            fallback_date = None
            subfolderPrefsFactory = self.subfolderPrefsFactory
            renamePrefsFactory = self.imageRenamePrefsFactory
            nameUsesJobCode = self.imageRenameUsesJobCode
            subfolderUsesJobCode = self.imageSubfolderUsesJobCode
        else:
            fallback_date = mediaFile.modificationTime
            subfolderPrefsFactory = self.videoSubfolderPrefsFactory
            renamePrefsFactory = self.videoRenamePrefsFactory
            nameUsesJobCode = self.videoRenameUsesJobCode
            subfolderUsesJobCode = self.videoSubfolderUsesJobCode
            
        renamePrefsFactory.setJobCode(self.get_job_code(iter))
        subfolderPrefsFactory.setJobCode(self.get_job_code(iter))
        
        generateSubfolderAndName(mediaFile, problem, subfolderPrefsFactory, renamePrefsFactory, 
                                nameUsesJobCode, subfolderUsesJobCode,
                                self.strip_characters, fallback_date)
        if self.get_status(iter) != mediaFile.status:
            self.liststore.set(iter, 11, mediaFile.status)
            self.liststore.set(iter, 10, self.get_status_icon(mediaFile.status))
        mediaFile.sampleStale = False
        
    def _setUsesJobCode(self):
        self.imageRenameUsesJobCode = rn.usesJobCode(self.rapidApp.prefs.image_rename)
        self.imageSubfolderUsesJobCode = rn.usesJobCode(self.rapidApp.prefs.subfolder)
        self.videoRenameUsesJobCode = rn.usesJobCode(self.rapidApp.prefs.video_rename)
        self.videoSubfolderUsesJobCode = rn.usesJobCode(self.rapidApp.prefs.video_subfolder)        
    
    
    def status_human_readable(self, mediaFile):
        if mediaFile.status == STATUS_DOWNLOADED:
            v = _('%(filetype)s was downloaded successfully') % {'filetype': mediaFile.displayNameCap}
        elif mediaFile.status == STATUS_DOWNLOAD_FAILED:
            v = _('%(filetype)s was not downloaded') % {'filetype': mediaFile.displayNameCap}
        elif mediaFile.status == STATUS_DOWNLOADED_WITH_WARNING:
            v = _('%(filetype)s was downloaded with warnings') % {'filetype': mediaFile.displayNameCap}
        elif mediaFile.status == STATUS_BACKUP_PROBLEM:
            v = _('%(filetype)s was downloaded but there were problems backing up') % {'filetype': mediaFile.displayNameCap}
        elif mediaFile.status == STATUS_DOWNLOAD_AND_BACKUP_FAILED:
            v = _('%(filetype)s was neither downloaded nor backed up') % {'filetype': mediaFile.displayNameCap}                
        elif mediaFile.status == STATUS_NOT_DOWNLOADED:
            v = _('%(filetype)s is ready to be downloaded') % {'filetype': mediaFile.displayNameCap}
        elif mediaFile.status == STATUS_DOWNLOAD_PENDING:
            v = _('%(filetype)s is about to be downloaded') % {'filetype': mediaFile.displayNameCap}
        elif mediaFile.status == STATUS_WARNING:
            v = _('%(filetype)s will be downloaded with warnings')% {'filetype': mediaFile.displayNameCap}
        elif mediaFile.status == STATUS_CANNOT_DOWNLOAD:
            v = _('%(filetype)s cannot be downloaded') % {'filetype': mediaFile.displayNameCap}
        return v    
        
    def show_preview(self, iter):
            
        if not iter:
            # clear everything except the label Preview at the top
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
            mediaFile = self.get_mediaFile(iter)
            
            self.previewed_file_treerowref = mediaFile.treerowref
            
            self.parentApp.set_base_preview_image(mediaFile.thumbnail)
            thumbnail = self.parentApp.scaledPreviewImage()
                
            self.parentApp.preview_image.set_from_pixbuf(thumbnail)
            
            image_tool_tip = "%s\n%s" % (date_time_human_readable(mediaFile.dateTime(), False), common.formatSizeForUser(mediaFile.size))
            self.parentApp.preview_image.set_tooltip_text(image_tool_tip)

            if mediaFile.sampleStale and mediaFile.status in [STATUS_NOT_DOWNLOADED, STATUS_WARNING]:
                self._refreshNameFactories()
                self._setUsesJobCode()
                self.generateSampleSubfolderAndName(mediaFile, iter)

            self.parentApp.preview_original_name_label.set_text(mediaFile.name)
            self.parentApp.preview_original_name_label.set_tooltip_text(mediaFile.name)
            if mediaFile.volume:
                pixbuf = mediaFile.volume.get_icon_pixbuf(16)
            else:
                pixbuf = self.icontheme.load_icon('gtk-harddisk', 16, gtk.ICON_LOOKUP_USE_BUILTIN)
            self.parentApp.preview_device_image.set_from_pixbuf(pixbuf)
            self.parentApp.preview_device_label.set_text(mediaFile.deviceName)
            self.parentApp.preview_device_path_label.set_text(mediaFile.path)
            self.parentApp.preview_device_path_label.set_tooltip_text(mediaFile.path)
            
            if using_gio:
                folder = gio.File(mediaFile.downloadFolder)
                fileInfo = folder.query_info(gio.FILE_ATTRIBUTE_STANDARD_ICON)
                icon = fileInfo.get_icon()
                pixbuf = common.get_icon_pixbuf(using_gio, icon, 16, fallback='folder')
            else:
                pixbuf = self.icontheme.load_icon('folder', 16, gtk.ICON_LOOKUP_USE_BUILTIN)
                
            self.parentApp.preview_destination_image.set_from_pixbuf(pixbuf)
            downloadFolderName = os.path.split(mediaFile.downloadFolder)[1]            
            self.parentApp.preview_destination_label.set_text(downloadFolderName)

            if mediaFile.status in [STATUS_WARNING, STATUS_CANNOT_DOWNLOAD, STATUS_NOT_DOWNLOADED, STATUS_DOWNLOAD_PENDING]:
                
                self.parentApp.preview_name_label.set_text(mediaFile.sampleName)
                self.parentApp.preview_name_label.set_tooltip_text(mediaFile.sampleName)
                self.parentApp.preview_destination_path_label.set_text(mediaFile.samplePath)
                self.parentApp.preview_destination_path_label.set_tooltip_text(mediaFile.samplePath)
            else:
                self.parentApp.preview_name_label.set_text(mediaFile.downloadName)
                self.parentApp.preview_name_label.set_tooltip_text(mediaFile.downloadName)
                self.parentApp.preview_destination_path_label.set_text(mediaFile.downloadPath)
                self.parentApp.preview_destination_path_label.set_tooltip_text(mediaFile.downloadPath)
            
            status_text = self.status_human_readable(mediaFile)
            self.parentApp.preview_status_icon.set_from_pixbuf(self.get_status_icon(mediaFile.status, preview=True))
            self.parentApp.preview_status_label.set_markup('<b>' + status_text + '</b>')
            self.parentApp.preview_status_label.set_tooltip_text(status_text)


            if mediaFile.status in [STATUS_WARNING, STATUS_DOWNLOAD_FAILED,
                                    STATUS_DOWNLOADED_WITH_WARNING, 
                                    STATUS_CANNOT_DOWNLOAD, 
                                    STATUS_BACKUP_PROBLEM, 
                                    STATUS_DOWNLOAD_AND_BACKUP_FAILED]:
                problem_title = mediaFile.problem.get_title()
                self.parentApp.preview_problem_title_label.set_markup('<i>' + problem_title + '</i>')
                self.parentApp.preview_problem_title_label.set_tooltip_text(problem_title)
                
                problem_text = mediaFile.problem.get_problems()
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
                
                if mediaFile.isImage:
                    apply = rn.usesJobCode(self.rapidApp.prefs.image_rename) or rn.usesJobCode(self.rapidApp.prefs.subfolder)
                else:
                    apply = rn.usesJobCode(self.rapidApp.prefs.video_rename) or rn.usesJobCode(self.rapidApp.prefs.video_subfolder)
                if apply:
                    if overwrite:
                        self.liststore.set(iter, 8, job_code)
                        mediaFile.jobcode = job_code
                        mediaFile.sampleStale = True
                    else:
                        if not self.get_job_code(iter):
                            self.liststore.set(iter, 8, job_code)
                            mediaFile.jobcode = job_code
                            mediaFile.sampleStale = True
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
                    mediaFile = self.get_mediaFile(iter)
                    _apply_job_code()
                    if mediaFile.treerowref == self.previewed_file_treerowref:
                        self.show_preview(iter)
        else:
            for iter in self.get_tree_row_iters(selected_only = True):
                mediaFile = self.get_mediaFile(iter)
                _apply_job_code()
                if mediaFile.treerowref == self.previewed_file_treerowref:
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
            mediaFile = self.get_mediaFile(iter)
            # each thread will see this change in status
            mediaFile.status = STATUS_DOWNLOAD_PENDING
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
            mediaFile = self.get_mediaFile(iter)
            status = mediaFile.status
            self.liststore.set(iter, 11, status)
            self.liststore.set(iter, 10, self.get_status_icon(status))
            
            # If this row is currently previewed, then should update the preview
            if mediaFile.treerowref == self.previewed_file_treerowref:
                self.show_preview(iter)


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
            
    def add_file(self, mediaFile):
        self.selection_treeview.add_file(mediaFile)
            
        
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
        
        self.errorTag = self.textbuffer.create_tag(weight=pango.WEIGHT_BOLD, foreground="red")
        self.warningTag = self.textbuffer.create_tag(weight=pango.WEIGHT_BOLD)
        self.resolutionTag = self.textbuffer.create_tag(style=pango.STYLE_ITALIC)
        
    def addMessage(self, thread_id, severity, problem, details, resolution):
        if severity in [config.CRITICAL_ERROR, config.SERIOUS_ERROR]:
            self.parentApp.error_image.show()
        elif severity == config.WARNING:
            self.parentApp.warning_image.show()
        self.parentApp.warning_vseparator.show()
        
        iter = self.textbuffer.get_end_iter()
        if severity in [config.CRITICAL_ERROR, config.SERIOUS_ERROR]:
            self.textbuffer.insert_with_tags(iter, problem +"\n", self.errorTag)
        else:
            self.textbuffer.insert_with_tags(iter, problem +"\n", self.warningTag)
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
            
        self.widget.show()
        
        self._setupIcons()
        
        # this must come after the window is shown
        if self.prefs.vpaned_pos > 0:
            self.main_vpaned.set_position(self.prefs.vpaned_pos)
        else:
            self.main_vpaned.set_position(66)
        
        self.checkIfFirstTimeProgramEverRun()

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
        global media_collection_treeview, log_dialog
        global workers

        #track files that should have a suffix added to them
        global duplicate_files
        
        #track files that have been downloaded in this session
        global downloaded_files
        
        # control sequence numbers and letters
        global sequences
        
        # whether we need to prompt for a job code
        global need_job_code_for_renaming

        duplicate_files = {}
        downloaded_files = DownloadedFiles()
        
        self.download_start_time = None
        
        downloadsToday = self.prefs.getAndMaybeResetDownloadsToday()
        sequences = rn.Sequences(downloadsToday, self.prefs.stored_sequence_no)
        
        self.downloadStats = DownloadStats()
        
        # set the number of seconds gap with which to measure download time remaing 
        self.downloadTimeGap = 3

        #locks for threadsafe file downloading and stats gathering
        self.fileRenameLock = Lock()
        self.fileSequenceLock = Lock()
        self.statsLock = Lock()
        self.downloadedFilesLock = Lock()

        # log window, in dialog format
        # used for displaying download information to the user
        
        log_dialog = LogDialog(self)


        self.volumeMonitor = None
        if self.usingVolumeMonitor():
            self.startVolumeMonitor()
        
        # flag to indicate whether the user changed some preferences that 
        # indicate the image and backup devices should be setup again
        self.rerunSetupAvailableImageAndVideoMedia = False
        self.rerunSetupAvailableBackupMedia = False
        
        # flag to indicate the user changes some preferences and the display
        # of sample names and subfolders needs to be refreshed
        self.refreshGeneratedSampleSubfolderAndName = False
        
        # counter to indicate how many threads need their sample names and subfolders regenerated because the user
        # changes their prefs at the same time as devices were being scanned
        self.noAfterScanRefreshGeneratedSampleSubfolderAndName = 0
        
        # flag to indicate the user changes some preferences and the display
        # of sample download folders needs to be refreshed
        self.refreshSampleDownloadFolder = False
        self.noAfterScanRefreshSampleDownloadFolders = 0
        
        # flag to indicate that the preferences dialog window is being 
        # displayed to the user
        self.preferencesDialogDisplayed = False
        
        # set up tree view display to display image devices and download status
        media_collection_treeview = MediaTreeView(self)        

        self.media_collection_vbox.pack_start(media_collection_treeview)
        
        #Selection display
        self.selection_vbox = SelectionVBox(self)
        self.selection_hbox.pack_start(self.selection_vbox, padding=12)
        self.set_display_selection(self.prefs.display_selection)
        self.set_display_preview_folders(self.prefs.display_preview_folders)
        
        self.backupVolumes = {}

        #Help button and download buttons
        self._setupDownloadbuttons()
        
        #status bar progress bar
        self.download_progressbar = gtk.ProgressBar()
        self.download_progressbar.set_size_request(150, -1)
        self.download_progressbar.show()
        self.download_progressbar_hbox.pack_start(self.download_progressbar, expand=False, 
                                        fill=0)
        

        # menus

        #preview panes
        self.menu_display_selection.set_active(self.prefs.display_selection)
        self.menu_preview_folders.set_active(self.prefs.display_preview_folders)
        
        #preview columns in pane
        if not DOWNLOAD_VIDEO:
            self.menu_type_column.set_active(False)
            self.menu_type_column.set_sensitive(False)
        else:
            self.menu_type_column.set_active(self.prefs.display_type_column)
        self.menu_size_column.set_active(self.prefs.display_size_column)
        self.menu_filename_column.set_active(self.prefs.display_filename_column)
        self.menu_device_column.set_active(self.prefs.display_device_column)
        self.menu_path_column.set_active(self.prefs.display_path_column)
        
        self.menu_clear.set_sensitive(False)

        need_job_code_for_renaming = self.needJobCodeForRenaming()
        self.menu_select_all_without_job_code.set_sensitive(need_job_code_for_renaming)
        self.menu_select_all_with_job_code.set_sensitive(need_job_code_for_renaming)
        
        #job code initialization
        self.last_chosen_job_code = None
        self.prompting_for_job_code = False
        
        #check to see if the download folder exists and is writable
        displayPreferences_2 = not self.checkDownloadPathOnStartup()
        displayPreferences = displayPreferences or displayPreferences_2
            
        if self.prefs.device_autodetection == False:
            displayPreferences_2 = not self.checkImageDevicePathOnStartup()
            displayPreferences = displayPreferences or displayPreferences_2
        
        #setup download and backup mediums, initiating scans
        self.setupAvailableImageAndBackupMedia(onStartup=True, onPreferenceChange=False, doNotAllowAutoStart = displayPreferences)

        #adjust viewport size for displaying media
        #this is important because the code in MediaTreeView.addCard() is inaccurate at program startup
        
        if media_collection_treeview.mapThreadToRow:
            height = self.media_collection_viewport.size_request()[1]
            self.media_collection_scrolledwindow.set_size_request(-1,  height)
        else:
            # don't allow the media collection to be absolutely empty
            self.media_collection_scrolledwindow.set_size_request(-1, 47)
        
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
#            if not using_gio:
            self.main()
#            else:
#                mainloop = gobject.MainLoop()
#                mainloop.run()
            self.running = False
            
    def setTestingEnv(self):
        #self.prefs.program_version = '0.0.8~b7'
        p = ['Date time', 'Image date', 'YYYYMMDD', 'Text', '-', '', 'Date time', 'Image date', 'HHMM', 'Text', '-', '', rn.SEQUENCES, rn.DOWNLOAD_SEQ_NUMBER, rn.SEQUENCE_NUMBER_3, 'Text', '-iso', '', 'Metadata', 'ISO', '', 'Text', '-f', '', 'Metadata', 'Aperture', '', 'Text', '-', '', 'Metadata', 'Focal length', '', 'Text', 'mm-', '', 'Metadata', 'Exposure time', '', 'Filename', 'Extension', 'lowercase']
        v = ['Date time', 'Video date', 'YYYYMMDD', 'Text', '-', '', 'Date time', 'Video date', 'HHMM', 'Text', '-', '', 'Sequences', 'Downloads today', 'One digit', 'Text', '-', '', 'Metadata', 'Width', '', 'Text', 'x', '', 'Metadata', 'Height', '', 'Filename', 'Extension', 'lowercase']
        f = '/home/damon/store/rapid-dump'
        self.prefs.image_rename = p
        self.prefs.video_rename = v
        self.prefs.download_folder = f
        self.prefs.video_download_folder = f
        
        
    def _setupIcons(self):
        icons = ['rapid-photo-downloader-downloaded', 
             'rapid-photo-downloader-downloaded-with-error',
             'rapid-photo-downloader-downloaded-with-warning',
             'rapid-photo-downloader-download-pending',
             'rapid-photo-downloader-jobcode']
        
        icon_list = [(icon, paths.share_dir('glade3/%s.svg' % icon)) for icon in icons]
        common.register_iconsets(icon_list)
    
    def displayFreeSpace(self):
        """
        Displays the amount of space free on the filesystem the files will be downloaded to.
        Also displays backup volumes / path being used.
        """
        msg = ''
        if using_gio and os.path.isdir(self.prefs.download_folder):
            folder = gio.File(self.prefs.download_folder)
            fileInfo = folder.query_filesystem_info(gio.FILE_ATTRIBUTE_FILESYSTEM_FREE)
            free = common.formatSizeForUser(fileInfo.get_attribute_uint64(gio.FILE_ATTRIBUTE_FILESYSTEM_FREE))
            msg = " " + _("%(free)s available") % {'free': free}
        
            
        if self.prefs.backup_images:
            if not self.prefs.backup_device_autodetection:
                # user manually specified backup location
                msg2 = _('Backing up to %(path)s') % {'path':self.prefs.backup_location}
            else:
                msg2 = self.displayBackupVolumes()
                
            if msg:
                msg = _("%(freespace)s. %(backuppaths)s.") % {'freespace': msg, 'backuppaths': msg2}
            else:
                msg = msg2
            
        self.rapid_statusbar.push(self.statusbar_context_id, msg)
    
    def checkImageDevicePathOnStartup(self):
        msg = None
        if not os.path.isdir(self.prefs.device_location):
            msg = _("Sorry, this device location does not exist:\n%(path)s\n\nPlease resolve the problem, or modify your preferences." % {"path": self.prefs.device_location})
            
        if msg:
            sys.stderr.write(msg +'\n')
            misc.run_dialog(_("Problem with Device Location Folder"), msg, 
                self,
                gtk.MESSAGE_ERROR)
            return False
        else:
            return True
        
    def checkDownloadPathOnStartup(self):
        if DOWNLOAD_VIDEO:
            paths = ((self.prefs.download_folder, _('Photo')), (self.prefs.video_download_folder, _('Video')))
        else:
            paths = ((self.prefs.download_folder, _('Photo')),)
        msg = ''
        noProblems = 0
        for path, file_type in paths:
            if not os.path.isdir(path):
                msg += _("The %(file_type)s Download Folder does not exist.\n") % {'file_type': file_type}
                noProblems += 1
            else:
                #unfortunately 'os.access(self.prefs.download_folder, os.W_OK)' is not reliable
                try:
                    tempWorkingDir = tempfile.mkdtemp(prefix='rapid-tmp-', 
                                                dir=path)
                except:
                    noProblems += 1
                    msg += _("The %(file_type)s Download Folder exists but cannot be written to.\n") % {'file_type': file_type}
                else:
                    os.rmdir(tempWorkingDir)
            
        if msg:
            msg = _("Sorry, problems were encountered with your download folders. Please fix the problems or modify the preferences.\n\n") + msg
            sys.stderr.write(msg)
            if noProblems == 1:
                title = _("Problem with Download Folder")
            else:
                title = _("Problem with Download Folders")
            
            misc.run_dialog(title, msg, 
                self,
                gtk.MESSAGE_ERROR)
            return False
        else:
            return True
    
    def checkPreferencesOnStartup(self):
        prefsOk = rn.checkPreferencesForValidity(self.prefs.image_rename,  self.prefs.subfolder, self.prefs.video_rename, self.prefs.video_subfolder)
        if not prefsOk:
            msg = _("There is an error in the program preferences.")
            msg += " " + _("Some preferences will be reset.") 
            # do not use cmd_line here, as this is a genuine error
            sys.stderr.write(msg +'\n')
        return prefsOk
        
    def needJobCodeForRenaming(self):
        return rn.usesJobCode(self.prefs.image_rename) or rn.usesJobCode(self.prefs.subfolder) or rn.usesJobCode(self.prefs.video_rename) or rn.usesJobCode(self.prefs.video_subfolder)
        
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
            
    
    def getShowWarningDownloadingFromCamera(self):
        if self.prefs.show_warning_downloading_from_camera:
            cmd_line(_("Displaying warning about downloading directly from camera"))
            d = ShowWarningDialog(self.widget, self.gotShowWarningDownloadingFromCamera)
            
    def gotShowWarningDownloadingFromCamera(self, dialog, showWarningAgain):
        dialog.destroy()
        self.prefs.show_warning_downloading_from_camera = showWarningAgain
    
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
                
    def _getJobCode(self,  postJobCodeEntryCB,  autoStart, downloadSelected):
        """ prompt for a job code """
        
        if not self.prompting_for_job_code:
            cmd_line(_("Prompting for Job Code"))
            self.prompting_for_job_code = True
            j = JobCodeDialog(self.widget, self.prefs.job_codes,  self.last_chosen_job_code, postJobCodeEntryCB,  autoStart, downloadSelected, False)
        else:
            cmd_line(_("Already prompting for Job Code, do not prompt again"))
        
    def getJobCode(self, autoStart=True, downloadSelected=False):
        """ called from the copyphotos thread, or when the user clicks one of the two download buttons"""
        
        self._getJobCode(self.gotJobCode, autoStart, downloadSelected)
        
    def gotJobCode(self, dialog, userChoseCode, code, autoStart, downloadSelected):
        dialog.destroy()
        self.prompting_for_job_code = False
        
        if userChoseCode:
            self.assignJobCode(code)
            self.last_chosen_job_code = code
            self.selection_vbox.selection_treeview.apply_job_code(code, overwrite=False, to_all_rows = not downloadSelected)
            threads = self.selection_vbox.selection_treeview.set_status_to_download_pending(selected_only = downloadSelected)
            if downloadSelected or not autoStart:
                cmd_line(_("Starting downloads"))
                self.startDownload(threads)
            else:
                # autostart is true
                cmd_line(_("Starting downloads that have been waiting for a Job Code"))
                for w in workers.getWaitingForJobCodeWorkers():
                    w.startStop()    
                
        else:
            # user cancelled
            for w in workers.getWaitingForJobCodeWorkers():
                w.waitingForJobCode = False
                
            if autoStart:
                for w in workers.getAutoStartWorkers():
                    w.autoStart = False
            
    def addFile(self, mediaFile):
        self.selection_vbox.add_file(mediaFile)
        
    def update_status_post_download(self, treerowref):
        self.selection_vbox.selection_treeview.update_status_post_download(treerowref)
            
    def on_menu_size_column_toggled(self, widget):
        self.prefs.display_size_column = widget.get_active()
        self.selection_vbox.selection_treeview.display_size_column(self.prefs.display_size_column)
        
    def on_menu_type_column_toggled(self, widget):
        self.prefs.display_type_column = widget.get_active()
        self.selection_vbox.selection_treeview.display_type_column(self.prefs.display_type_column)
        
    def on_menu_filename_column_toggled(self, widget):
        self.prefs.display_filename_column = widget.get_active()
        self.selection_vbox.selection_treeview.display_filename_column(self.prefs.display_filename_column)
        
    def on_menu_path_column_toggled(self, widget):
        self.prefs.display_path_column = widget.get_active()
        self.selection_vbox.selection_treeview.display_path_column(self.prefs.display_path_column)        
        
    def on_menu_device_column_toggled(self, widget):        
        self.prefs.display_device_column = widget.get_active()
        self.selection_vbox.selection_treeview.display_device_column(self.prefs.display_device_column)
                
    def checkIfFirstTimeProgramEverRun(self):
        """
        if this is the first time the program has been run, then
        might need to create default directories
        """
        if len(self.prefs.program_version) == 0:
            path = getDefaultPhotoLocation(ignore_missing_dir=True)
            if not os.path.isdir(path):
                cmd_line(_("Creating photo download folder %(folder)s") % {'folder':path})
                try:
                    os.makedirs(path)
                    self.prefs.download_folder = path
                except:
                    cmd_line(_("Failed to create default photo download folder %(folder)s") % {'folder':path})
            if DOWNLOAD_VIDEO:
                path = getDefaultVideoLocation(ignore_missing_dir=True)
                if not os.path.isdir(path):
                    cmd_line(_("Creating video download folder %(folder)s") % {'folder':path})
                    try:
                        os.makedirs(path)
                        self.prefs.video_download_folder = path
                    except:
                        cmd_line(_("Failed to create default video download folder %(folder)s") % {'folder':path})
    
    def checkForUpgrade(self, runningVersion):
        """ Checks if the running version of the program is different from the version recorded in the preferences.
        
        If the version is different, then the preferences are checked to see whether they should be upgraded or not.
        
        returns True if program preferences window should be opened """
        
        displayPrefs = upgraded = False
        
        previousVersion = self.prefs.program_version
        if len(previousVersion) > 0:
            # the program has been run previously for this user
        
            pv = common.pythonifyVersion(previousVersion)
            rv = common.pythonifyVersion(runningVersion)
            
            title = PROGRAM_NAME
            imageRename = subfolder = None
            
            if pv != rv:
                if pv > rv:
                    prefsOk = rn.checkPreferencesForValidity(self.prefs.image_rename, self.prefs.subfolder, self.prefs.video_rename, self.prefs.video_subfolder)
                        
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

                    if rn.checkPreferencesForValidity(self.prefs.image_rename, self.prefs.subfolder, self.prefs.video_rename, self.prefs.video_subfolder, previousVersion):
                        upgraded,  imageRename,  subfolder = rn.upgradePreferencesToCurrent(self.prefs.image_rename, self.prefs.subfolder, previousVersion)
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

        do_not_size_icon = False
        self.notification_icon_size = 48        
        try:
            info = pynotify.get_server_info()
        except:
            cmd_line(_("Warning: desktop environment notification server is incorrectly configured."))
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
        

    def isGProxyShadowMount(self, gMount):

        """ gvfs GProxyShadowMount is used for the camera itself, not the data in the memory card """
        if using_gio:
            if hasattr(gMount, 'is_shadowed'):
                return gMount.is_shadowed()
            else:
                return str(type(gMount)).find('GProxyShadowMount') >= 0
        else:
            return False
            
    def isCamera(self, volume):
        if using_gio:
            try:
                return volume.get_root().query_filesystem_info(gio.FILE_ATTRIBUTE_GVFS_BACKEND).get_attribute_as_string(gio.FILE_ATTRIBUTE_GVFS_BACKEND) == 'gphoto2'
            except:
                return False
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
                        if path not in self.backupVolumes:
                            self.backupVolumes[path] = volume
                            self.displayFreeSpace()

                    elif self.prefs.device_autodetection and (media.is_DCIM_Media(path) or self.searchForPsd()):
                        if self.isCamera(volume.volume):
                            self.getShowWarningDownloadingFromCamera()
                        if self.searchForPsd() and path not in self.prefs.device_whitelist:
                            # prompt user if device should be used or not
                            self.getUseDevice(path, volume, self.prefs.auto_download_upon_device_insertion)
                        else:   
                            self._printAutoStart(self.prefs.auto_download_upon_device_insertion)                   
                            self.initiateScan(path, volume, self.prefs.auto_download_upon_device_insertion)
                             
    def initiateScan(self, path, volume, autostart):
        """ initiates scan of image device"""
        cardMedia = CardMedia(path, volume)
        i = workers.getNextThread_id()
        
        workers.append(CopyPhotos(i, self, self.fileRenameLock, 
                                    self.fileSequenceLock, self.statsLock,
                                    self.downloadedFilesLock, self.downloadStats,
                                    autostart, cardMedia))


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
                        self.selection_vbox.selection_treeview.clear_all(w.thread_id)
                        workers.disableWorker(w.thread_id)
            # second scenario
            for w in workers.getReadyToDownloadWorkers():
                if w.cardMedia.volume:                
                    if w.cardMedia.volume.volume == volume:
                        media_collection_treeview.removeCard(w.thread_id)
                        self.selection_vbox.selection_treeview.clear_all(w.thread_id)
                        workers.disableWorker(w.thread_id)
                    
            # fourth scenario - nothing to do
                    
            # remove backup volumes
            if path in self.backupVolumes:
                del self.backupVolumes[path]
                self.displayFreeSpace()
                
            # may need to disable download button
            self.setDownloadButtonSensitivity()
        
    
    def clearCompletedDownloads(self):
        """
        clears the display of completed downloads
        """

        for w in workers.getFinishedWorkers():
            media_collection_treeview.removeCard(w.thread_id)
            self.selection_vbox.selection_treeview.clear_all(w.thread_id)

            

        
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
        identifiers = [self.prefs.backup_identifier]
        if DOWNLOAD_VIDEO:
            identifiers.append(self.prefs.video_backup_identifier)
        if self.prefs.backup_images:
            if self.prefs.backup_device_autodetection:
                if media.isBackupMedia(path, identifiers):
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
        
    def setupAvailableImageAndBackupMedia(self, onStartup, onPreferenceChange, doNotAllowAutoStart):
        """
        Sets up volumes for downloading from and backing up to
        
        onStartup should be True if the program is still starting, i.e. this is being called from the 
        program's initialization.
        
        onPreferenceChange should be True if this is being called as the result of a preference
        being changed
        
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
            # or download devices
            
            for v in self.volumeMonitor.get_mounts():
                volume = Volume(v) #'volumes' are actually mounts (legacy variable name at work here)
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
                                #backupPath = os.path.join(path,  self.prefs.backup_identifier)
                                self.backupVolumes[path] = volume
                            elif self.prefs.device_autodetection and (media.is_DCIM_Media(path) or self.searchForPsd()):
                                volumeList.append((path, volume))
                        
        
        if not self.prefs.device_autodetection:
            # user manually specified the path from which to download 
            path = self.prefs.device_location
            if path:
                cmd_line(_("Using manually specified path") + " %s" %  path)
                volumeList.append((path,  None))
                    
        if self.prefs.backup_images:
            if not self.prefs.backup_device_autodetection:
                # user manually specified backup location
                # will backup to this path, but don't need any volume info associated with it
                self.backupVolumes[self.prefs.backup_location] = None
        
        self.displayFreeSpace()
        # add each memory card / other device to the list of threads
        
        if doNotAllowAutoStart:
            autoStart = False
        else:
            autoStart = (not onPreferenceChange) and ((self.prefs.auto_download_at_startup and onStartup) or (self.prefs.auto_download_upon_device_insertion and not onStartup))
        
        self._printAutoStart(autoStart)
        
        shownWarning = False

        for i in range(len(volumeList)):
            path, volume = volumeList[i]
            if volume:
                if self.isCamera(volume.volume) and not shownWarning:
                    self.getShowWarningDownloadingFromCamera()
                    shownWarning = True
            if self.searchForPsd() and path not in self.prefs.device_whitelist:
                # prompt user to see if device should be used or not
                self.getUseDevice(path, volume, autoStart)
            else:
                self.initiateScan(path, volume, autoStart)
                
    def refreshBackupMedia(self):
        """
        Setup the backup media
        
        Assumptions: this is being called after the user has changed their preferences AND download media has already been setup
        """
        self.backupVolumes = {}
        if self.prefs.backup_images:
            if not self.prefs.backup_device_autodetection:
                # user manually specified backup location
                # will backup to this path, but don't need any volume info associated with it
                self.backupVolumes[self.prefs.backup_location] = None
            else:
                for v in self.volumeMonitor.get_mounts():
                    volume = Volume(v)
                    path = volume.get_path(avoid_gnomeVFS_bug = True)
                    if path:
                        if self.checkIfBackupVolume(path):
                            # is a backup volume
                            if path not in self.backupVolumes:
                                # ensure it is not in a list of workers which have not started downloading
                                # if it is, remove it
                                for w in workers.getNotDownloadingAndNotFinishedWorkers():
                                    if w.cardMedia.path == path:
                                        media_collection_treeview.removeCard(w.thread_id)
                                        self.selection_vbox.selection_treeview.clear_all(w.thread_id)
                                        workers.disableWorker(w.thread_id)
                                
                                downloading_workers = []
                                for w in workers.getDownloadingWorkers():
                                    downloading_workers.append(w)
                                
                                for w in downloading_workers:
                                    if w.cardMedia.path == path:
                                        # the user is trying to backup to a device that is currently being downloaded from..... we don't normally allow that, but what to do?
                                        cmd_line(_("Warning: backup device %(device)s is currently being downloaded from") % {'device': volume.get_name(limit=0)})
                                        
                                self.backupVolumes[path] = volume
                        
        self.displayFreeSpace()
        
    def _setupDownloadbuttons(self):
        self.download_hbutton_box = gtk.HButtonBox()
        self.download_hbutton_box.set_spacing(12)
        self.download_hbutton_box.set_homogeneous(False)

        help_button = gtk.Button(stock=gtk.STOCK_HELP)
        help_button.connect("clicked", self.on_help_button_clicked)
        self.download_hbutton_box.pack_start(help_button)
        self.download_hbutton_box.set_child_secondary(help_button, True)
    
        self.DOWNLOAD_SELECTED_LABEL = _("D_ownload Selected")
        self.download_button_is_download = True
        self.download_button = gtk.Button() 
        self.download_button.set_use_underline(True)
        self.download_button.set_flags(gtk.CAN_DEFAULT)
        self.download_selected_button = gtk.Button() 
        self.download_selected_button.set_use_underline(True)        
        self._set_download_button()
        self.download_button.connect('clicked', self.on_download_button_clicked)
        self.download_selected_button.connect('clicked', self.on_download_selected_button_clicked)
        self.download_hbutton_box.set_layout(gtk.BUTTONBOX_END)
        self.download_hbutton_box.pack_start(self.download_selected_button)        
        self.download_hbutton_box.pack_start(self.download_button)
        self.download_hbutton_box.show_all()
        self.buttons_hbox.pack_start(self.download_hbutton_box, 
                                    padding=hd.WINDOW_BORDER_SPACE)
                                    
        self.setDownloadButtonSensitivity()

    def set_display_selection(self, value):
        if value:
            self.selection_vbox.preview_table.show_all()
        else:
            self.selection_vbox.preview_table.hide()
        self.selection_vbox.set_display_preview_folders(self.prefs.display_preview_folders)
            
    def set_display_preview_folders(self, value):
        self.selection_vbox.set_display_preview_folders(value)
       
    def _resetDownloadInfo(self):
        self.markSet = False
        self.startTime = None
        self.totalDownloadSize = self.totalDownloadedSoFar = 0
        self.totalDownloadSizeThisRun = self.totalDownloadedSoFarThisRun = 0 
        # there is no need to clear self.timeRemaining, as when each thread is completed, it removes itself
        
        # this next value is used by the date time option "Download Time"
        self.download_start_time = None 
        
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
        
    def startOrResumeWorkers(self, threads):
                    
        # resume any paused workers
        for w in workers.getPausedDownloadingWorkers():
            w.startStop()
            self.timeRemaining.setTimeMark(w)
        
        # set the time that the download started - this is used
        # in the "Download Time" date time renaming option.
        self.setDownloadStartTime()

            
        #start any new workers that have downloads pending
        for i in threads:
            workers[i].startStop()
        
        if is_beta and verbose and False:
            workers.printWorkerStatus()
    
    def setDownloadStartTime(self):
        if not self.download_start_time:
            self.download_start_time = datetime.datetime.now()
        
    def updateOverallProgress(self, thread_id, bytesDownloaded, percentComplete):
        """
        Updates progress bar and status bar text with time remaining
        to download images
        """
                
        self.totalDownloadedSoFar += bytesDownloaded
        self.totalDownloadedSoFarThisRun += bytesDownloaded
        
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
            job_code = None
            if is_beta and verbose and False:
                workers.printWorkerStatus()
    
        else:
            now = time.time()
            self.timeRemaining.update(thread_id, bytesDownloaded)
            
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
                    
                    self.rapid_statusbar.pop(self.statusbar_context_id)
                    self.rapid_statusbar.push(self.statusbar_context_id, message)
                    
    
    def resetSequences(self):
        if self.downloadComplete():
            sequences.reset(self.prefs.getDownloadsToday(),  self.prefs.stored_sequence_no)
    
    def notifyUserAllDownloadsComplete(self):
        """ If all downloads are complete, if needed notify the user using libnotify 
        
        Reset progress bar info"""
        
        if self.downloadComplete():
            if self.displayDownloadSummaryNotification:
                message = _("All downloads complete")
                if self.downloadStats.noImagesDownloaded:
                    filetype = file_types_by_number(self.downloadStats.noImagesDownloaded, 0)
                    message += "\n" + _("%(number)s %(numberdownloaded)s") % \
                                {'number': self.downloadStats.noImagesDownloaded, 
                                'numberdownloaded': _("%(filetype)s downloaded") % \
                                {'filetype': filetype}}
                if self.downloadStats.noImagesSkipped:
                    filetype = file_types_by_number(self.downloadStats.noImagesSkipped, 0)
                    message += "\n" + _("%(number)s %(numberdownloaded)s") % \
                                {'number': self.downloadStats.noImagesSkipped,
                                'numberdownloaded': _("%(filetype)s failed to download") % \
                                {'filetype': filetype}}
                if self.downloadStats.noVideosDownloaded:
                    filetype = file_types_by_number(0, self.downloadStats.noVideosDownloaded)
                    message += "\n" + _("%(number)s %(numberdownloaded)s") % \
                                {'number': self.downloadStats.noVideosDownloaded, 
                                'numberdownloaded': _("%(filetype)s downloaded") % \
                                {'filetype': filetype}}                    
                if self.downloadStats.noVideosSkipped:
                    filetype = file_types_by_number(0, self.downloadStats.noVideosSkipped)
                    message += "\n" + _("%(number)s %(numberdownloaded)s") % \
                                {'number': self.downloadStats.noVideosSkipped,
                                'numberdownloaded': _("%(filetype)s failed to download") % \
                                {'filetype': filetype}}                    
                if self.downloadStats.noWarnings:
                    message += "\n" + _("%(number)s %(numberdownloaded)s") % \
                                {'number': self.downloadStats.noWarnings, 
                                'numberdownloaded': _("warnings")}
                if self.downloadStats.noErrors:
                    message += "\n" + _("%(number)s %(numberdownloaded)s") % \
                                {'number': self.downloadStats.noErrors, 
                                'numberdownloaded': _("errors")}
                    
                n = pynotify.Notification(PROGRAM_NAME,  message)
                n.set_icon_from_pixbuf(self.application_icon)
                n.show()
                self.displayDownloadSummaryNotification = False # don't show it again unless needed
                # download statistics are cleared in exitOnDownloadComplete()
            self._resetDownloadInfo()
            self.speed_label.set_text('         ')
            self.displayFreeSpace()
            
                
    def exitOnDownloadComplete(self):
        if self.downloadComplete():
            if self.prefs.auto_exit:
                if not (self.downloadStats.noErrors or self.downloadStats.noWarnings):                
                    self.quit()
            # since for whatever reason am not exiting, clear the download statistics
            self.downloadStats.clear()
        
    
    def downloadFailed(self, thread_id):
        if workers.noDownloadingWorkers() == 0:
            self.download_button_is_download = True
            self._set_download_button()
            self.setDownloadButtonSensitivity()
    
    def downloadComplete(self):
        return self.totalDownloadedSoFar == self.totalDownloadSize

    def setDownloadButtonSensitivity(self):

        isSensitive = (workers.noReadyToDownloadWorkers() > 0 and 
                        workers.noScanningWorkers() == 0 and
                        self.selection_vbox.selection_treeview.rows_available_for_download()) or \
                        workers.noDownloadingWorkers() > 0
        
        if isSensitive:
            self.download_button.props.sensitive = True
            # download selected button sensitity is enabled only when the user selects something
            self.selection_vbox.selection_treeview.update_download_selected_button()
            self.menu_download_pause.props.sensitive = True
        else:
            self.download_button.props.sensitive = False
            self.download_selected_button.props.sensitive = False
            self.menu_download_pause.props.sensitive = False
            
        return isSensitive
        
        
    def on_rapidapp_destroy(self, widget):
        """Called when the application is going to quit"""
        
        # save window and component sizes
        self.prefs.hpaned_pos = self.selection_vbox.file_hpaned.get_position()
        self.prefs.vpaned_pos = self.main_vpaned.get_position()

        x, y = self.rapidapp.get_size()
        self.prefs.main_window_size_x = x
        self.prefs.main_window_size_y = y

        workers.quitAllWorkers()

        self.flushevents() 
        
        display_queue.close("w")


    def on_rapidapp_window_state_event(self, widget, event):
        """ Checkto see if the user maximized the main application window or not. """
        if event.changed_mask & gdk.WINDOW_STATE_MAXIMIZED:
            self.prefs.main_window_maximized = event.new_window_state & gdk.WINDOW_STATE_MAXIMIZED
                

    def on_menu_clear_activate(self, widget):
        self.clearCompletedDownloads()
        widget.set_sensitive(False)
        
    def on_menu_refresh_activate(self, widget):
        self.selection_vbox.selection_treeview.clear_all()
        self.setupAvailableImageAndBackupMedia(onStartup = False,  onPreferenceChange = True,  doNotAllowAutoStart = True)
        
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

    def on_menu_display_selection_toggled(self, check_button):
        self.prefs.display_selection = check_button.get_active()
        
    def on_menu_preview_folders_toggled(self, check_button):
        self.prefs.display_preview_folders = check_button.get_active()
        
    def on_menu_zoom_out_activate(self, widget):
        self.selection_vbox.zoom_out()
        
    def on_menu_zoom_in_activate(self, widget):
        self.selection_vbox.zoom_in()
        
    def on_menu_select_all_activate(self, widget):
        self.selection_vbox.selection_treeview.select_rows('all')

    def on_menu_select_all_photos_activate(self, widget):
        self.selection_vbox.selection_treeview.select_rows('photos')
    
    def on_menu_select_all_videos_activate(self, widget):
        self.selection_vbox.selection_treeview.select_rows('videos')
        
    def on_menu_select_none_activate(self, widget):
        self.selection_vbox.selection_treeview.select_rows('none')
        
    def on_menu_select_all_with_job_code_activate(self, widget):
        self.selection_vbox.selection_treeview.select_rows('withjobcode')

    def on_menu_select_all_without_job_code_activate(self, widget):
        self.selection_vbox.selection_treeview.select_rows('withoutjobcode')


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
            self.download_selected_button.set_label(self.DOWNLOAD_SELECTED_LABEL)
            self.download_selected_button.set_image(gtk.image_new_from_stock(
                                                gtk.STOCK_CONVERT,
                                                gtk.ICON_SIZE_BUTTON))
            self.selection_vbox.selection_treeview.update_download_selected_button()
            
            self.download_button.set_image(gtk.image_new_from_stock(
                                                gtk.STOCK_CONVERT,
                                                gtk.ICON_SIZE_BUTTON))
            
            if workers.noPausedWorkers():
                self.download_button.set_label(_("_Resume"))
                self.download_selected_button.hide()
            else:
                self.download_button.set_label(_("_Download All"))
                self.download_selected_button.show_all()
                                                
        else:
            # button should indicate paused state
            self.download_button.set_image(gtk.image_new_from_stock(
                                                gtk.STOCK_MEDIA_PAUSE,
                                                gtk.ICON_SIZE_BUTTON))
            # This text will be displayed to the user on the Download / Pause button.
            self.download_button.set_label(_("_Pause"))
            self.download_selected_button.set_sensitive(False)
            self.download_selected_button.hide()
            
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
        
    def startDownload(self, threads):
        self.startOrResumeWorkers(threads)
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
        
        Button is in one of three states: download all, resume, or pause.
        
        If download, a click indicates to start or resume a download run.
        If pause, a click indicates to pause all running downloads.
        """
        if self.download_button_is_download:
            if need_job_code_for_renaming and self.selection_vbox.selection_treeview.job_code_missing(False) and not self.prompting_for_job_code:
                self.getJobCode(autoStart=False, downloadSelected=False)
            else:
                threads = self.selection_vbox.selection_treeview.set_status_to_download_pending(selected_only = False)
                self.startDownload(threads)
            self._set_download_button()
        else:
            self.pauseDownload()

    def on_download_selected_button_clicked(self, widget):
        # set the status of the selected workers to be downloading pending
        if need_job_code_for_renaming and self.selection_vbox.selection_treeview.job_code_missing(True) and not self.prompting_for_job_code:
            self.getJobCode(autoStart=False, downloadSelected=True)
        else:
            threads = self.selection_vbox.selection_treeview.set_status_to_download_pending(selected_only = True)
            self.startDownload(threads)
                

        
    def on_help_button_clicked(self, widget):
        webbrowser.open("http://www.damonlynch.net/rapid/help.html")
            
    def on_preference_changed(self, key, value):
        """
        Called when user changes the program's preferences
        """
        
        if key == 'display_selection':
            self.set_display_selection(value)
        elif key == 'display_preview_folders':
            self.set_display_preview_folders(value)
        elif key == 'show_log_dialog':
            self.menu_log_window.set_active(value)
        elif key in ['device_autodetection', 'device_autodetection_psd', 'device_location']:
            self.rerunSetupAvailableImageAndVideoMedia = True
            if not self.preferencesDialogDisplayed:
                self.postPreferenceChange()
                
        elif key in ['backup_images', 'backup_device_autodetection', 'backup_location', 'backup_identifier', 'video_backup_identifier']:
            self.rerunSetupAvailableBackupMedia = True
            if not self.preferencesDialogDisplayed:
                self.postPreferenceChange()

        elif key in ['subfolder', 'image_rename', 'video_subfolder', 'video_rename']:
            global need_job_code_for_renaming
            need_job_code_for_renaming = self.needJobCodeForRenaming()
            self.selection_vbox.set_job_code_display()
            self.menu_select_all_without_job_code.set_sensitive(need_job_code_for_renaming)
            self.menu_select_all_with_job_code.set_sensitive(need_job_code_for_renaming)
            self.refreshGeneratedSampleSubfolderAndName = True
                
            if not self.preferencesDialogDisplayed:
                self.postPreferenceChange()
                
        elif key in ['download_folder', 'video_download_folder']:
            self.refreshSampleDownloadFolder = True
            if not self.preferencesDialogDisplayed:
                self.postPreferenceChange()            
            
        elif key == 'job_codes':
            # update job code list in left pane
            self.selection_vbox.update_job_code_combo()
        
            
    def postPreferenceChange(self):
        """
        Handle changes in program preferences after the preferences dialog window has been closed
        """
        if self.rerunSetupAvailableImageAndVideoMedia:
            if self.usingVolumeMonitor():
                self.startVolumeMonitor()
            cmd_line("\n" + _("Download device settings preferences were changed."))
            
            self.selection_vbox.selection_treeview.clear_all()
            self.setupAvailableImageAndBackupMedia(onStartup = False, onPreferenceChange = True, doNotAllowAutoStart = True)
            if is_beta and verbose and False:
                workers.printWorkerStatus()
                
            self.rerunSetupAvailableImageAndVideoMedia = False
            
        if self.rerunSetupAvailableBackupMedia:
            if self.usingVolumeMonitor():
                self.startVolumeMonitor()            
            cmd_line("\n" + _("Backup preferences were changed."))
            
            self.refreshBackupMedia()
            self.rerunSetupAvailableBackupMedia = False
            
        if self.refreshGeneratedSampleSubfolderAndName:
            cmd_line("\n" + _("Subfolder and filename preferences were changed."))
            for w in workers.getScanningWorkers():
                if not w.scanResultsStale:
                    w.scanResultsStale = True
                    self.noAfterScanRefreshGeneratedSampleSubfolderAndName += 1
                
            self.selection_vbox.selection_treeview.refreshGeneratedSampleSubfolderAndName()
            self.refreshGeneratedSampleSubfolderAndName = False
            self.setDownloadButtonSensitivity()
            
        if self.refreshSampleDownloadFolder:
            cmd_line("\n" + _("Download folder preferences were changed."))
            for w in workers.getScanningWorkers():
                if not w.scanResultsStaleDownloadFolder:
                    w.scanResultsStaleDownloadFolder = True
                    self.noAfterScanRefreshSampleDownloadFolders += 1
            
            self.selection_vbox.selection_treeview.refreshSampleDownloadFolders()
            self.refreshSampleDownloadFolder = False

    def regenerateScannedDevices(self, thread_id):
        """
        Regenerate the filenames / subfolders / download folders for this thread
        
        The user must have adjusted their preferences as the device was being scanned
        """
        
        if self.noAfterScanRefreshSampleDownloadFolders:
            # no point updating it if we're going to update it in the
            # refresh of sample names and subfolders anway!
            if not self.noAfterScanRefreshGeneratedSampleSubfolderAndName:
                self.selection_vbox.selection_treeview.refreshSampleDownloadFolders(thread_id)
            self.noAfterScanRefreshSampleDownloadFolders -= 1
                
        if self.noAfterScanRefreshGeneratedSampleSubfolderAndName:
            self.selection_vbox.selection_treeview.refreshGeneratedSampleSubfolderAndName(thread_id)
            self.noAfterScanRefreshGeneratedSampleSubfolderAndName -= 1
            

        
 
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
        
        return common.get_icon_pixbuf(using_gio, self.volume.get_icon(), size)
            
    def unmount(self,  callback):
        self.volume.unmount(callback)

class DownloadStats:
    def __init__(self):
        self.clear()
        
    def adjust(self, size, noImagesDownloaded, noVideosDownloaded, noImagesSkipped, noVideosSkipped, noWarnings,  noErrors):
        self.downloadSize += size
        self.noImagesDownloaded += noImagesDownloaded
        self.noVideosDownloaded += noVideosDownloaded
        self.noImagesSkipped += noImagesSkipped
        self.noVideosSkipped += noVideosSkipped
        self.noWarnings += noWarnings
        self.noErrors += noErrors
        
    def clear(self):
        self.noImagesDownloaded = self.noVideosDownloaded = self.noImagesSkipped = self.noVideosSkipped = 0
        self.downloadSize = 0
        self.noWarnings = self.noErrors = 0
        
class DownloadedFiles:
    def __init__(self):
        self.images = {}
        
    def add_download(self, name, extension, date_time, sub_seconds, sequence_number_used):
        if name not in self.images:
            self.images[name] = ([extension], date_time, sub_seconds, sequence_number_used)
        else:
            if extension not in self.images[name][0]:
                self.images[name][0].append(extension)

        
    def matching_pair(self, name, extension, date_time, sub_seconds):
        """Checks to see if the image matches an image that has already been downloaded.
        Image name (minus extension), exif date time, and exif subseconds are checked.
        
        Returns -1 and a sequence number if the name, extension, and exif values match (i.e. it has already been downloaded)
        Returns 0 and a sequence number if name and exif values match, but the extension is different (i.e. a matching RAW + JPG image)
        Returns -99 and a sequence number of None if images detected with the same filenames, but taken at different times
        Returns 1 and a sequence number of None if no match"""
        
        if name in self.images:
            if self.images[name][1] == date_time and self.images[name][2] == sub_seconds:
                if extension in self.images[name][0]:
                    return (-1, self.images[name][3])
                else:
                    return (0, self.images[name][3])
            else:
                return (-99, None)
        return (1, None)
        
    def extExifDateTime(self, name):
        """Returns first extension, exif date time and subseconds data for the already downloaded  image"""
        return (self.images[name][0][0], self.images[name][1], self.images[name][2])
        
class TimeForDownload:
    # used to store variables, see below
    pass

class TimeRemaining:
    gap = 2
    def __init__(self):
        self.clear()
        
    def set(self,  w,  size):
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
                timefraction = amtDownloaded / float(amtTime)
                amtToDownload = float(self.times[w].size) - self.times[w].downloaded
                if timefraction:
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
    parser.add_option("-d", "--debug", action="store_true", dest="debug", help=_('display debugging information when run from the command line'))
    parser.add_option("-q", "--quiet",  action="store_false", dest="verbose",  help=_("only output errors to the command line"))
    # image file extensions are recognized RAW files plus TIFF and JPG
    parser.add_option("-e",  "--extensions", action="store_true", dest="extensions", help=_("list photo and video file extensions the program recognizes and exit"))
    parser.add_option("--reset-settings", action="store_true", dest="reset", help=_("reset all program settings and preferences and exit"))
    (options, args) = parser.parse_args()
    global verbose
    verbose = options.verbose
    
    global debug_info
    debug_info = options.debug
    if debug_info:
        verbose = True
    
    if verbose:
        atexit.register(programStatus)
        
    if options.extensions:
        extensions = ((metadata.RAW_FILE_EXTENSIONS + metadata.NON_RAW_IMAGE_FILE_EXTENSIONS, _("Photos:")), (videometadata.VIDEO_FILE_EXTENSIONS, _("Videos:")))
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

    cmd_line(_("Rapid Photo Downloader") + " %s" % config.version)
    cmd_line(_("Using") + " pyexiv2 " + metadata.version_info())
    cmd_line(_("Using") + " exiv2 " + metadata.exiv2_version_info())
    if DOWNLOAD_VIDEO:
        cmd_line(_("Using") + " hachoir " + videometadata.version_info())
    else:
        cmd_line(_("\n" + "Video downloading functionality disabled.\nTo download videos, please install the hachoir metadata and kaa metadata packages for python.") + "\n")
        
    if using_gio:
        cmd_line(_("Using") + " GIO")
        gobject.threads_init()
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
