# -*- coding: latin1 -*-
### Copyright (C) 2007 - 2012 Damon Lynch <damonlynch@gmail.com>

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

version = '0.4.6'

GCONF_KEY="/apps/rapid-photo-downloader"

DBUS_NAME = "net.damonlynch.RapidPhotoDownloader"

#i18n
APP_NAME = "rapid-photo-downloader"

MEDIA_LOCATION = "/media"

SKIP_DOWNLOAD = "skip download"
ADD_UNIQUE_IDENTIFIER = "add unique identifier"

# These next three values are fall back values that are used only
# if calls to xdg-user-dir fail
DEFAULT_PHOTO_LOCATIONS = ['Pictures',  'Photos']
DEFAULT_BACKUP_LOCATION = 'Pictures'
DEFAULT_VIDEO_BACKUP_LOCATION = 'Videos'

DEFAULT_VIDEO_LOCATIONS = ['Videos']

CRITICAL_ERROR = 1
SERIOUS_ERROR = 2
WARNING = 3

STATUS_DOWNLOAD_PENDING = 0                 # going to try to download it
STATUS_DOWNLOADED = 1                       # downloaded successfully
STATUS_DOWNLOADED_WITH_WARNING = 2          # downloaded ok but there was a warning
STATUS_BACKUP_PROBLEM = 3                   # downloaded ok, but the file was not backed up, or had a problem (overwrite or duplicate)
STATUS_NOT_DOWNLOADED = 4                   # has not yet been downloaded (but might be if the user chooses)
STATUS_DOWNLOAD_AND_BACKUP_FAILED = 5       # tried to download but failed, and the backup failed or had an error
STATUS_DOWNLOAD_FAILED = 6                  # tried to download but failed
STATUS_WARNING = 7                          # warning (shown in pre-download preview)
STATUS_CANNOT_DOWNLOAD = 8                  # cannot be downloaded

DEFAULT_WINDOW_WIDTH = 670
DEFAULT_WINDOW_HEIGHT = 650


