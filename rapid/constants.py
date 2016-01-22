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

PROGRAM_NAME = "Rapid Photo Downloader"

logging_format = '%(asctime)s %(levelname)s: %(message)s'
logging_date_format = '%H:%M:%S'


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
    scan_id = Qt.UserRole + 8


class ExtractionTask(Enum):
    undetermined = 1
    bypass = 2
    load_file_directly = 3
    load_from_bytes = 4
    load_from_exif = 5
    extract_from_file = 6


class ExtractionProcessing(Enum):
    resize = 1
    orient = 2
    strip_bars_photo = 3
    strip_bars_video = 4
    add_film_strip = 5


class GphotoMTime(Enum):
    undetermined = 1
    unknown = 2
    is_utc = 3
    is_local = 4


class CameraErrorCode(Enum):
    inaccessible = 1
    locked = 2


class CustomColors(Enum):
    color1 = '#7a9c38'
    color2 = '#cb493f'
    color3 = '#d17109'
    color4 = '#5b97e4'
    color5 = '#5f6bfe'
    color6 = '#6d7e90'


class Desktop(Enum):
    gnome = 1
    unity = 2
    cinnamon = 3
    kde = 4
    xfce = 5
    unknown = 10


orientation_offset = dict(
    arw=106,
    cr2=126,
    dcr=7684,
    dng=144,
    mef=144,
    mrw=152580,
    nef=144,
    nrw=94,
    orf=132,
    pef=118,
    raf=208,
    raw=742404,
    rw2=1004548,
    sr2=82,
    srw=46
)

datetime_offset = dict(
    arw=1540,
    cr2=1028,
    dng=119812,
    mef=772,
    mrw=152580,
    nef=14340,
    nrw=1540,
    orf=6660,
    pef=836,
    raf=1796,
    raw=964,
    rw2=3844,
    sr2=836,
    srw=508
)

photo_rename_test = ['Date time','Image date','YYYYMMDD','Text','-','',
                    'Date time','Image date','HHMM','Text','-','','Sequences',
                    'Downloads today','One digit','Text','-iso','',
                    'Metadata','ISO','','Text','-f','','Metadata',
                     'Aperture','','Text','-','','Metadata','Focal length','',
                     'Text','mm-','','Metadata','Exposure time','',
                     'Filename','Extension','lowercase']

photo_rename_simple_test = ['Date time','Image date','YYYYMMDD','Text','-','',
                    'Date time','Image date','HHMM','Text','-','','Sequences',
                    'Downloads today','One digit', 'Filename','Extension','lowercase']

job_code_rename_test = ['Job code','', '', 'Sequences',
                    'Downloads today','One digit', 'Filename','Extension',
                        'lowercase']
