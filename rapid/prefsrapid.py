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

import utilities
import config
__version__ = config.version

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

    def get_and_maybe_reset_downloads_today(self):
        v = self.get_downloads_today()
        if v <= 0:
            self.reset_downloads_today()
        return v

    def get_downloads_today(self):
        """Returns the preference value for the number of downloads performed today 
        
        If value is less than zero, that means the date has changed"""
        
        hour,  minute = self.get_day_start()
        adjustedToday = datetime.datetime.strptime("%s %s:%s" % (self.downloads_today[0], hour,  minute), "%Y-%m-%d %H:%M") 
        
        now = datetime.datetime.today()

        if  now < adjustedToday :
            try:
                return int(self.downloads_today[1])
            except ValueError:
                sys.stderr.write(_("Invalid Downloads Today value.\n"))
                sys.stderr.write(_("Resetting value to zero.\n"))
                self.get_downloads_today(self.downloads_today[0] ,  0)
                return 0
        else:
            return -1
                
    def set_downloads_today(self, date,  value=0):
            self.downloads_today = [date,  str(value)]
            
    def increment_downloads_today(self):
        """ returns true if day changed """
        v = self.get_downloads_today()
        if v >= 0:
            self.set_downloads_today(self.downloads_today[0], v + 1)
            return False
        else:
            self.reset_downloads_today(1)
            return True

    def reset_downloads_today(self,  value=0):
        now = datetime.datetime.today()
        hour,  minute = self.get_day_start()
        t = datetime.time(hour,  minute)
        if now.time() < t:
            date = today()
        else:
            d = datetime.datetime.today() + datetime.timedelta(days=1)
            date = d.strftime(('%Y-%m-%d'))
            
        self.set_downloads_today(date, value)
        
    def set_day_start(self,  hour,  minute):
        self.day_start = "%s:%s" % (hour,  minute)

    def get_day_start(self):
        try:
            t1,  t2 = self.day_start.split(":")
            return (int(t1),  int(t2))
        except ValueError:
            sys.stderr.write(_("'Start of day' preference value is corrupted.\n"))
            sys.stderr.write(_("Resetting to midnight.\n"))
            self.day_start = "0:0"
            return 0, 0

    def get_sample_job_code(self):
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
        
        
            
def check_prefs_for_validity(prefs):
    """
    Checks preferences for validity (called at program startup)
    
    Returns true if the passed in preferences are valid, else returns False
    """
    
    try:
        tests = ((prefs.image_rename, pd.PhotoNamePrefs), 
                 (prefs.subfolder, pd.PhotoSubfolderPrefs),
                 (prefs.video_rename, pd.VideoNamePrefs),
                 (prefs.video_subfolder, pd.VideoSubfolderPrefs))
        for pref, pref_widgets in tests:
            p = pref_widgets(pref)
            p.check_prefs_for_validity()
    except:
        return False
    return True





