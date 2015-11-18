__author__ = 'Damon Lynch'

# Copyright (C) 2007-2015 Damon Lynch <damonlynch@gmail.com>

# This file is part of Rapid Photo Downloader.
#
# Rapid Photo Downloader is free software: you can redistribute it and/or
# modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Rapid Photo Downloader is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Rapid Photo Downloader.  If not,
# see <http://www.gnu.org/licenses/>.

from enum import (Enum, IntEnum)
from PyQt5.QtCore import Qt

version = '0.9.0~a1'

DBUS_NAME = "net.damonlynch.RapidPhotoDownloader"

APP_NAME = "rapid-photo-downloader"

PROGRAM_NAME = "Rapid Photo Downloader"

class ConflictResolution(IntEnum):
    skip = 1
    add_identifier = 2

class ErrorType(Enum):
    critical_error = 1
    serious_error = 2
    warning= 3

class DownloadStatus(Enum):
    # going to try to download it
    download_pending = 1
    # downloaded successfully
    downloaded = 2
    # downloaded ok but there was a warning
    downloaded_with_warning = 3
    # downloaded ok, but the file was not backed up, or had a problem
    # (overwrite or duplicate)
    backup_problem = 4
    # has not yet been downloaded (but might be if the user chooses)
    not_downloaded = 5
    # tried to download but failed, and the backup failed or had an error
    download_and_backup_failed = 6
    # tried to download but failed
    download_failed = 7

Downloaded = (DownloadStatus.downloaded,
              DownloadStatus.downloaded_with_warning,
              DownloadStatus.backup_problem)

class ThumbnailCacheStatus(Enum):
    not_ready = 1
    from_rpd_cache_fdo_write_invalid = 2
    suitable_for_thumb_cache_write = 3
    suitable_for_fdo_cache_write = 4
    generation_failed=5

class ThumbnailCacheDiskStatus(Enum):
    found = 1
    not_foud = 2
    failure = 3

class BackupLocationType(Enum):
    photos = 1
    videos = 2
    photos_and_videos = 3

class DeviceType(Enum):
    camera = 1
    volume = 2
    path = 3

class FileType(IntEnum):
    photo = 1
    video = 2

class FileExtension(Enum):
    raw = 1
    jpeg = 2
    other_photo = 3
    video = 4
    audio = 5
    unknown = 6

class FileSortPriority(IntEnum):
    high = 1
    low = 2

class DeviceState(Enum):
    scanning = 1
    scanned = 2
    downloading = 3

class RenameAndMoveStatus(Enum):
    download_started = 1
    download_completed = 2

class ThumbnailSize(IntEnum):
    width = 160
    height = 120

class ApplicationState(Enum):
    normal = 1
    exiting = 2

class Roles(IntEnum):
    previously_downloaded = Qt.UserRole
    extension = Qt.UserRole + 1
    download_status = Qt.UserRole + 2
    has_audio = Qt.UserRole + 3
    secondary_attribute = Qt.UserRole + 4
    path = Qt.UserRole + 5
    uri = Qt.UserRole + 6
    camera_memory_card = Qt.UserRole + 7

photo_rename_test = ['Date time','Image date','YYYYMMDD','Text','-','',
                    'Date time','Image date','HHMM','Text','-','','Sequences',
                    'Downloads today','One digit','Text','-iso','',
                    'Metadata','ISO','','Text','-f','','Metadata',
                     'Aperture','','Text','-','','Metadata','Focal length','',
                     'Text','mm-','','Metadata','Exposure time','',
                     'Filename','Extension','lowercase']

job_code_rename_test = ['Job code','', '', 'Sequences',
                    'Downloads today','One digit', 'Filename','Extension',
                        'lowercase']
