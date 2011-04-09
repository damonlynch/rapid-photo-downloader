#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2007, 2008, 2009, 2010, 2011 Damon Lynch <damonlynch@gmail.com>

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

import subprocess, os, datetime

import prefs

import preferencesdialog as pd
from generatenameconfig import *
import rpdfile

import utilities
import config
__version__ = config.version

import multiprocessing
import logging
logger = multiprocessing.get_logger()

from gettext import gettext as _

def _get_default_location_legacy(options, ignore_missing_dir=False):
    if ignore_missing_dir:
        return utilities.get_full_path(options[0])
    for default in options:
        path = utilities.get_full_path(default)
        if os.path.isdir(path):
            return path
    return utilities.get_full_path('')
    
def _get_default_location_XDG(dir_type):
    proc = subprocess.Popen(['xdg-user-dir', dir_type], stdout=subprocess.PIPE)
    output = proc.communicate()[0].strip()
    return output

def get_default_photo_location(ignore_missing_dir=False):
    try:
        return _get_default_location_XDG('PICTURES')
    except:
        return _get_default_location_legacy(config.DEFAULT_PHOTO_LOCATIONS, ignore_missing_dir)
    
def get_default_video_location(ignore_missing_dir=False):
    try:
        return _get_default_location_XDG('VIDEOS')
    except:    
        return _get_default_location_legacy(config.DEFAULT_VIDEO_LOCATIONS, ignore_missing_dir)
        
def get_default_backup_photo_identifier():
    return os.path.split(get_default_photo_location(ignore_missing_dir = True))[1]

def get_default_backup_video_identifier():
    return os.path.split(get_default_video_location(ignore_missing_dir = True))[1]
    
def today():
    return datetime.date.today().strftime('%Y-%m-%d')    
    
class RapidPreferences(prefs.Preferences):
        
    defaults = {
        "program_version": prefs.Value(prefs.STRING, ""),
        "download_folder": prefs.Value(prefs.STRING, 
                                        get_default_photo_location()),
        "video_download_folder": prefs.Value(prefs.STRING, 
                                        get_default_video_location()),
        "subfolder": prefs.ListValue(prefs.STRING_LIST, DEFAULT_SUBFOLDER_PREFS),
        "video_subfolder": prefs.ListValue(prefs.STRING_LIST, DEFAULT_VIDEO_SUBFOLDER_PREFS),
        "image_rename": prefs.ListValue(prefs.STRING_LIST, [FILENAME, 
                                        NAME_EXTENSION,
                                        ORIGINAL_CASE]),
        "video_rename": prefs.ListValue(prefs.STRING_LIST, [FILENAME, 
                                        NAME_EXTENSION,
                                        ORIGINAL_CASE]),
        "device_autodetection": prefs.Value(prefs.BOOL, True),
        "device_location": prefs.Value(prefs.STRING, os.path.expanduser('~')), 
        "device_autodetection_psd": prefs.Value(prefs.BOOL,  False),
        "device_whitelist": prefs.ListValue(prefs.STRING_LIST,  ['']), 
        "device_blacklist": prefs.ListValue(prefs.STRING_LIST,  ['']), 
        "backup_images": prefs.Value(prefs.BOOL, False),
        "backup_device_autodetection": prefs.Value(prefs.BOOL, True),
        "backup_identifier": prefs.Value(prefs.STRING, 
                                        get_default_backup_photo_identifier()),
        "video_backup_identifier": prefs.Value(prefs.STRING, 
                                        get_default_backup_video_identifier()),
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
        #~ "hpaned_pos": prefs.Value(prefs.INT, 0),
        "vpaned_pos": prefs.Value(prefs.INT, 0),
        "main_window_size_x": prefs.Value(prefs.INT, 0),
        "main_window_size_y": prefs.Value(prefs.INT, 0),
        "main_window_maximized": prefs.Value(prefs.INT, 0),
        "show_warning_downloading_from_camera": prefs.Value(prefs.BOOL, True),
        #~ "preview_zoom": prefs.Value(prefs.INT, zoom),
        "enable_previews": prefs.Value(prefs.BOOL, True),
        }

    def __init__(self):
        prefs.Preferences.__init__(self, config.GCONF_KEY, self.defaults)

                
    def get_downloads_today_tracker(self):
        return DownloadsTodayTracker(downloads_today_date = self.downloads_today[0],
                                     downloads_today = self.downloads_today[1],
                                     day_start = self.day_start
                                    )
        
    def set_downloads_today_from_tracker(self, downloads_today_tracker):
        self.downloads_today = downloads_today_tracker.downloads_today
        self.day_start = downloads_today_tracker.day_start

    def get_sample_job_code(self):
        if self.job_codes:
            return self.job_codes[0]
        else:
            return ''
            
    def _get_pref_lists(self):
        return (self.image_rename, self.subfolder, self.video_rename, 
                     self.video_subfolder)
    
    def _pref_list_uses_component(self, pref_list, pref_component, offset):
        for i in range(0, len(pref_list), 3):
            if pref_list[i+offset] == pref_component:
                return True
        return False        
    
    def must_synchronize_raw_jpg(self):
        """Returns True if synchronize_raw_jpg is True and photo renaming
        uses sequence values"""
        if self.synchronize_raw_jpg:
            for s in LIST_SEQUENCE_L1:
                if self._pref_list_uses_component(self.image_rename, s, 1):
                    return True
        return False
    
    def any_pref_uses_stored_sequence_no(self):
        """Returns True if any of the pref lists contain a stored sequence no"""
        for pref_list in self._get_pref_lists():
            if self._pref_list_uses_component(pref_list, STORED_SEQ_NUMBER, 1):
                return True
        return False        
        
    def any_pref_uses_session_sequece_no(self):
        """Returns True if any of the pref lists contain a session sequence no"""
        for pref_list in self._get_pref_lists():
            if self._pref_list_uses_component(pref_list, SESSION_SEQ_NUMBER, 1):
                return True
        return False 
        
    def any_pref_uses_sequence_letter_value(self):
        """Returns True if any of the pref lists contain a sequence letter"""
        for pref_list in self._get_pref_lists():
            if self._pref_list_uses_component(pref_list, SEQUENCE_LETTER, 1):
                return True
        return False         
            
    def reset(self):
        """
        resets all preferences to default values
        """
        
        prefs.Preferences.reset(self)
        self.program_version = __version__
        
        
    def pref_uses_job_code(self, pref_list):
        """ Returns True if the particular preferences contains a job code"""
        for i in range(0, len(pref_list), 3):
            if pref_list[i] == JOB_CODE:
                return True
        return False
        
    def any_pref_uses_job_code(self):
        """ Returns True if any of the preferences contain a job code"""
        for pref_list in self._get_pref_lists():
            if self.pref_uses_job_code(pref_list):
                return True
        return False
        
    def most_recent_job_code(self):
        if len(self.job_codes) > 0:
            return self.job_codes[0]
        else:
            return None
        
    def get_pref_lists_by_file_type(self, file_type):
        """
        Returns tuple of subfolder and file rename pref lists for the given 
        file type
        """
        if file_type == rpdfile.FILE_TYPE_PHOTO:
            return (self.subfolder, self.image_rename)
        else:
            return (self.video_subfolder, self.video_rename)

    def get_download_folder_for_file_type(self, file_type):
        """
        Returns the download folder for the given file type
        """
        if file_type == rpdfile.FILE_TYPE_PHOTO:
            return self.download_folder
        else:
            return self.video_download_folder            
        

class DownloadsTodayTracker:
    """
    Handles tracking the number of downloads undertaken on any one day.
    
    When a day starts is flexible. See http://damonlynch.net/rapid/documentation/#renameoptions
    """
    def __init__(self, downloads_today_date, downloads_today, day_start):
        self.day_start = day_start # string
        self.downloads_today = [downloads_today_date, str(downloads_today)] # two strings
        
    def get_and_maybe_reset_downloads_today(self):
        v = self.get_downloads_today()
        if v <= 0:
            self.reset_downloads_today()
        return v

    def get_downloads_today(self):
        """Returns the preference value for the number of downloads performed today 
        
        If value is less than zero, that means the date has changed"""
        
        hour, minute = self.get_day_start()
        try:
            adjusted_today = datetime.datetime.strptime("%s %s:%s" % (self.downloads_today[0], hour,  minute), "%Y-%m-%d %H:%M") 
        except:
            logger.critical("Failed to calculate date adjustment. Download today values appear to be corrupted: %s %s:%s", 
                            self.downloads_today[0], hour, minute)
            adjusted_today = None
        
        now = datetime.datetime.today()
        
        if adjusted_today is None:
            return -1
            
        if  now < adjusted_today :
            try:
                return int(self.downloads_today[1])
            except ValueError:
                logger.error("Invalid Downloads Today value. Resetting value to zero.")
                self.get_downloads_today(self.downloads_today[0] ,  0)
                return 0
        else:
            return -1
            
    def get_raw_downloads_today(self):
        """
        Gets value without changing it in any way, except to check for type convesion error.
        If there is an error, then the value is reset
        """
        try:
            return int(self.downloads_today[1])
        except ValueError:
            logger.critical("Downloads today value is corrupted: %s", self.downloads_today[1])
            self.downloads_today[1] = '0'
            return 0
            
    def set_raw_downloads_today_from_int(self, downloads_today):
        self.downloads_today[1] = str(downloads_today)
        
    def set_raw_downloads_today_date(self, downloads_today_date):
        self.downloads_today[0] = downloads_today_date
            
    def get_raw_downloads_today_date(self):
        return self.downloads_today[0]

    def get_raw_day_start(self):
        """
        Gets value without changing it in any way
        """
        return self.day_start
        
    def get_day_start(self):
        try:
            t1,  t2 = self.day_start.split(":")
            return (int(t1),  int(t2))
        except ValueError:
            logger.error("'Start of day' preference value %s is corrupted. Resetting to midnight", self.day_start)
            self.day_start = "0:0"
            return 0, 0        
            
    def increment_downloads_today(self):
        """ returns true if day changed """
        v = self.get_downloads_today()
        if v >= 0:
            self.set_downloads_today(self.downloads_today[0], v + 1)
            return False
        else:
            self.reset_downloads_today(1)
            return True

    def reset_downloads_today(self, value=0):
        now = datetime.datetime.today()
        hour, minute = self.get_day_start()
        t = datetime.time(hour, minute)
        if now.time() < t:
            date = today()
        else:
            d = datetime.datetime.today() + datetime.timedelta(days=1)
            date = d.strftime(('%Y-%m-%d'))
            
        self.set_downloads_today(date, value)            
        
    def set_downloads_today(self, date, value=0):
        self.downloads_today = [date, str(value)]
        
    def set_day_start(self, hour, minute):
        self.day_start = "%s:%s" % (hour, minute)
        
    def log_vals(self):
        logger.info("Date %s Value %s Day start %s", self.downloads_today[0], self.downloads_today[1], self.day_start)
        
        

def check_prefs_for_validity(prefs):
    """
    Checks preferences for validity (called at program startup)
    
    Returns tuple with two values:
    1. true if the passed in preferences are valid, else returns False
    2. message if prefs are invalid
    """
    

    msg = ''
    valid = True
    tests = ((prefs.image_rename, pd.PhotoNamePrefs), 
             (prefs.subfolder, pd.PhotoSubfolderPrefs),
             (prefs.video_rename, pd.VideoNamePrefs),
             (prefs.video_subfolder, pd.VideoSubfolderPrefs))
    for pref, pref_widgets in tests:
        p = pref_widgets(pref)
        try:
            p.check_prefs_for_validity()
        except pd.PrefError as e:
            valid = False
            msg += e.msg + "\n"
            
    return (valid, msg)

def insert_pref_lists(prefs, rpd_file):
    """
    Convenience function to insert subfolder and file rename pref_lists for
    the given file type.
    
    Returns the modified rpd_file
    """
    subfolder_pref_list, name_pref_list = prefs.get_pref_lists_by_file_type(rpd_file.file_type)
    rpd_file.subfolder_pref_list = subfolder_pref_list
    rpd_file.name_pref_list = name_pref_list
    return rpd_file

def format_pref_list_for_pretty_print(pref_list):
    """ returns a string useful for printing the preferences"""
    
    v = ''
    
    for i in range(0, len(pref_list), 3):
        if (pref_list[i+1] or pref_list[i+2]):
            c = ':'
        else: 
            c = ''
        s = "%s%s " % (pref_list[i], c) 
        
        if pref_list[i+1]:
            s = "%s%s" % (s, pref_list[i+1])
        if pref_list[i+2]:
            s = "%s (%s)" % (s, pref_list[i+2])
        v += s + "\n"
    return v


