#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2007-2014 Damon Lynch <damonlynch@gmail.com>

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
### Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301
### USA


import preferencesdialog as pd
from generatenameconfig import *
import rpdfile

import utilities
import constants
__version__ = constants.version

import logging

from gettext import gettext as _

def _get_default_location_legacy(options, ignore_missing_dir=False):
    if ignore_missing_dir:
        return utilities.get_full_path(options[0])
    for default in options:
        path = utilities.get_full_path(default)
        if os.path.isdir(path):
            return path
    return utilities.get_full_path('')


def get_default_backup_photo_identifier():
    return os.path.split(get_default_photo_location(ignore_missing_dir = True))[1]

def get_default_backup_video_identifier():
    return os.path.split(get_default_video_location(ignore_missing_dir = True))[1]

def today():
    return datetime.date.today().strftime('%Y-%m-%d')

class RapidPreferences(prefs.Preferences):


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



