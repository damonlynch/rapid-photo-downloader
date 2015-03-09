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

from enum import Enum

version = '0.5.0~a1'

DBUS_NAME = "net.damonlynch.RapidPhotoDownloader"

#i18n
APP_NAME = "rapid-photo-downloader"

SKIP_DOWNLOAD = "skip"
ADD_UNIQUE_IDENTIFIER = "unique identifier"

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

class BackupLocationForFileType(Enum):
    photos = 1
    videos = 2
    photos_and_videos = 3

class DeviceType(Enum):
    camera = 1
    volume = 2
    path = 3

class FileType(Enum):
    photo = 1
    video = 2



