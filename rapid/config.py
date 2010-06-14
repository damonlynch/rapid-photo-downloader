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

version = '0.2.3'

GCONF_KEY="/apps/rapid-photo-downloader"
GLADE_FILE = "glade3/rapid.glade"

DBUS_NAME = "net.damonlynch.RapidPhotoDownloader"

#i18n
APP_NAME = "rapid-photo-downloader"

MEDIA_LOCATION = "/media"

SKIP_DOWNLOAD = "skip download"
ADD_UNIQUE_IDENTIFIER = "add unique identifier"

REPORT_WARNING = "warning"
REPORT_ERROR = "error"
IGNORE = "ignore"

DEFAULT_PHOTO_LOCATIONS = ['Pictures',  'Photos']
DEFAULT_BACKUP_LOCATION = 'Pictures'
DEFAULT_VIDEO_BACKUP_LOCATION = 'Videos'

DEFAULT_VIDEO_LOCATIONS = ['Videos']

MAX_NO_READERS = 20

CRITICAL_ERROR = 1
SERIOUS_ERROR = 2
WARNING = 3

MAX_LENGTH_DEVICE_NAME = 15
MAX_THUMBNAIL_SIZE = 160

STATUS_DOWNLOADED =         0       # downloaded successfully
STATUS_DOWNLOAD_FAILED = 1          # tried to download but failed
STATUS_DOWNLOADED_WITH_WARNING = 2  # downloaded ok but there was a warning
STATUS_NOT_DOWNLOADED = 3           # has not yet been downloaded (but might be if the user chooses)
STATUS_DOWNLOAD_PENDING = 4         # going to try to download it
STATUS_WARNING = 5                  # warning (shown in pre-download preview)
STATUS_CANNOT_DOWNLOAD = 6          # cannot be downloaded


