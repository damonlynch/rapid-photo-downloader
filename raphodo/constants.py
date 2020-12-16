# Copyright (C) 2007-2020 Damon Lynch <damonlynch@gmail.com>

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

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2007-2020, Damon Lynch"

from enum import (Enum, IntEnum)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QFontMetrics, QColor

PROGRAM_NAME = "Rapid Photo Downloader"
logfile_name = 'rapid-photo-downloader.log'

remote_versions_file = 'https://www.damonlynch.net/rapid/version.json'

# If set to True, the ability to check for a new version will be removed
# from the user interface and disabled in program logic.
disable_version_check = False


class CheckNewVersionDialogResult(IntEnum):
    download = 1
    do_not_download = 2
    skip = 3
    open_website = 4


class CheckNewVersionDialogState(IntEnum):
    check = 1
    prompt_for_download = 2
    open_website = 3
    failed_to_contact = 4
    have_latest_version = 5


class ConflictResolution(IntEnum):
    skip = 1
    add_identifier = 2


class ErrorType(Enum):
    critical_error = 1
    serious_error = 2
    warning = 3


class PresetPrefType(Enum):
    preset_photo_subfolder = 1
    preset_video_subfolder = 2
    preset_photo_rename = 3
    preset_video_rename = 4


class PresetClass(Enum):
    builtin = 1
    custom = 2
    new_preset = 3
    remove_all = 4
    update_preset = 5
    edited = 6
    start_editor = 7


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


DownloadWarning = {DownloadStatus.downloaded_with_warning, DownloadStatus.backup_problem}
DownloadFailure = {DownloadStatus.download_and_backup_failed, DownloadStatus.download_failed}


download_status_error_severity = {
    DownloadStatus.downloaded_with_warning: ErrorType.warning,
    DownloadStatus.backup_problem: ErrorType.serious_error,
    DownloadStatus.download_and_backup_failed: ErrorType.serious_error,
    DownloadStatus.download_failed: ErrorType.serious_error
}


DownloadUpdateMilliseconds = 1000
DownloadUpdateSeconds = DownloadUpdateMilliseconds / 1000
# How many seconds to delay showing the time remaining and download speed
ShowTimeAndSpeedDelay = 8.0


class RightSideButton(IntEnum):
    destination = 0
    rename = 1
    jobcode = 2
    backup = 3


class ThumbnailCacheStatus(Enum):
    not_ready = 1
    orientation_unknown = 2
    ready = 3
    fdo_256_ready = 4
    generation_failed = 5


class ThumbnailCacheDiskStatus(Enum):
    found = 1
    not_found = 2
    failure = 3
    unknown = 4


class ThumbnailCacheOrigin(Enum):
    thumbnail_cache = 1
    fdo_cache = 2


class DisplayingFilesOfType(Enum):
    photos = 1
    videos = 2
    photos_and_videos = 3


BackupLocationType = DisplayingFilesOfType
BackupFailureType = DisplayingFilesOfType
DownloadingFileTypes = DisplayingFilesOfType


class DestinationDisplayType(Enum):
    folder_only = 1
    usage_only = 2
    folders_and_usage = 3


class ExifSource(Enum):
    raw_bytes = 1
    app1_segment = 2
    actual_file = 3


class DestinationDisplayMousePos(Enum):
    normal = 1
    menu = 2


class DestinationDisplayTooltipState(Enum):
    menu = 1
    path = 2
    storage_space = 3


class DeviceType(Enum):
    camera = 1
    volume = 2
    path = 3


class BackupDeviceType:
    volume = 1
    path = 2


class DeviceState(Enum):
    pre_scan = 1
    scanning = 2
    idle = 3
    thumbnailing = 4
    downloading = 5
    finished = 6


class FileType(IntEnum):
    photo = 1
    video = 2


class FileExtension(Enum):
    raw = 1
    jpeg = 2
    heif = 3
    other_photo = 4
    video = 5
    audio = 6
    unknown = 7


class FileSortPriority(IntEnum):
    high = 1
    low = 2


class KnownDeviceType(IntEnum):
    volume_whitelist = 1
    volume_blacklist = 2
    camera_blacklist = 3


class RenameAndMoveStatus(Enum):
    download_started = 1
    download_completed = 2


class BackupStatus(Enum):
    backup_started = 1
    backup_completed = 2


class ThumbnailSize(IntEnum):
    width = 160
    height = 120


class ApplicationState(Enum):
    normal = 1
    exiting = 2


class Show(IntEnum):
    all = 1
    new_only = 2


class Sort(IntEnum):
    modification_time = 1
    checked_state = 2
    filename = 3
    extension = 4
    file_type = 5
    device = 6


class JobCodeSort(IntEnum):
    last_used = 1
    code = 2


Checked_Status = {
    Qt.Checked: 'checked',
    Qt.Unchecked: 'unchecked',
    Qt.PartiallyChecked: 'partially checked'
}


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
    device_details = Qt.UserRole + 9
    storage = Qt.UserRole + 10
    mtp = Qt.UserRole + 11
    is_camera = Qt.UserRole + 12
    sort_extension = Qt.UserRole + 13
    filename = Qt.UserRole + 14
    highlight = Qt.UserRole + 16
    folder_preview = Qt.UserRole + 17
    download_subfolder = Qt.UserRole + 18
    device_type = Qt.UserRole + 19
    download_statuses = Qt.UserRole + 20
    job_code = Qt.UserRole + 21
    uids = Qt.UserRole + 22


class ExtractionTask(Enum):
    undetermined = 1
    bypass = 2
    load_file_directly = 3
    load_file_and_exif_directly = 4
    load_file_directly_metadata_from_secondary = 5
    load_from_bytes = 6
    load_from_bytes_metadata_from_temp_extract = 7
    load_from_exif = 8
    extract_from_file = 9
    extract_from_file_and_load_metadata = 10
    load_from_exif_buffer = 11
    load_heif_directly = 12
    load_heif_and_exif_directly = 13


class ExtractionProcessing(Enum):
    resize = 1
    orient = 2
    strip_bars_photo = 3
    strip_bars_video = 4
    add_film_strip = 5


# Approach device uses to store timestamps
# i.e. whether assumes are located in utc timezone or local
class DeviceTimestampTZ(Enum):
    undetermined = 1
    unknown = 2
    is_utc = 3
    is_local = 4


class CameraErrorCode(Enum):
    inaccessible = 1
    locked = 2
    read = 3
    write = 4


class ViewRowType(Enum):
    header = 1
    content = 2


class Align(Enum):
    top = 1
    bottom = 2


class NameGenerationType(Enum):
    photo_name = 1
    video_name = 2
    photo_subfolder = 3
    video_subfolder = 4


class CustomColors(Enum):
    color1 = '#7a9c38'  # green
    color2 = '#cb493f'  # red
    color3 = '#d17109'  # orange
    color4 = '#4D8CDC'  # blue
    color5 = '#5f6bfe'  # purple
    color6 = '#6d7e90'  # greyish
    color7 = '#ffff00'  # bright yellow


PaleGray = '#d7d6d5'
DarkGray = '#35322f'
MediumGray = '#5d5b59'
DoubleDarkGray = '#1e1b18'


ExtensionColorDict = {
    FileExtension.raw: CustomColors.color1,
    FileExtension.video: CustomColors.color2,
    FileExtension.jpeg: CustomColors.color4,
    FileExtension.heif: CustomColors.color5,
    FileExtension.other_photo: CustomColors.color5
}


def extensionColor(ext_type: FileExtension) -> QColor:
    try:
        return QColor(ExtensionColorDict[ext_type].value)
    except KeyError:
        return QColor(0, 0, 0)


FileTypeColorDict = {
    FileType.photo: CustomColors.color1,
    FileType.video: CustomColors.color2
}


def fileTypeColor(file_type: FileType) -> QColor:
    try:
        return QColor(FileTypeColorDict[file_type].value)
    except KeyError:
        return QColor(CustomColors.color3.value)


# Position of preference values in file renaming and subfolder generation editor:
class PrefPosition(Enum):
    on_left = 1
    at = 2
    on_left_and_at = 3
    positioned_in = 4
    not_here = 5


# Values in minutes:
proximity_time_steps = [5, 10, 15, 30, 45, 60, 90, 120, 180, 240, 480, 960, 1440]


class TemporalProximityState(Enum):
    empty = 1
    pending = 2  # e.g. 2 devices scanning, only 1 scan finished
    generating = 3
    regenerate = 4
    generated = 5
    ctime_rebuild = 6
    ctime_rebuild_proceed = 7


class StandardFileLocations(Enum):
    home = 1
    desktop = 2
    file_system = 3
    documents = 4
    music = 5
    pictures = 6
    videos = 7
    downloads = 8



max_remembered_destinations = 10

ThumbnailBackgroundName = MediumGray
EmptyViewHeight = 20

DeviceDisplayPadding = 6
DeviceShadingIntensity = 104

# How many steps with which to highlight thumbnail cells
FadeSteps = 20
FadeMilliseconds = 700


# horizontal and vertical margin for thumbnail rectangles
thumbnail_margin = 10


def minPanelWidth() -> int:
    """
    Minimum width of panels on left and right side of main window.

    Derived from standard font size.

    :return: size in pixels
    """

    return int(QFontMetrics(QFont()).height() * 13.5)


def minFileSystemViewHeight() -> int:
    """
    Minimum height of file system views on left and right side of main window.

    Derived from standard font size.

    :return: size in pixels
    """

    return QFontMetrics(QFont()).height() * 7


def minGridColumnWidth() -> int:
    return int(QFontMetrics(QFont()).height() * 1.3333333333333333)


def standardProgressBarWidth() -> int:
    return int(QFontMetrics(QFont()).height() * 20)


# Be sure to update gvfs_controls_mounts() if updating this
class Desktop(Enum):
    gnome = 1
    unity = 2
    cinnamon = 3
    kde = 4
    xfce = 5
    mate = 6
    lxde = 7
    lxqt = 8
    ubuntugnome = 9
    popgnome = 10
    deepin = 11
    zorin = 12
    ukui = 13
    pantheon = 14
    unknown = 15


class FileManagerType(Enum):
    regular = 1
    select = 2
    dir_only_uri = 3
    show_item = 4
    show_items = 5


FileManagerBehavior = dict(
    nautilus=FileManagerType.select,
    dolphin=FileManagerType.select,
    caja=FileManagerType.dir_only_uri,
    thunar=FileManagerType.dir_only_uri,
    nemo=FileManagerType.regular,
    pcmanfm=FileManagerType.dir_only_uri,
    peony=FileManagerType.show_items,
)
FileManagerBehavior['pcmanfm-qt'] = FileManagerType.dir_only_uri
FileManagerBehavior['dde-file-manager'] = FileManagerType.show_item
FileManagerBehavior['io.elementary.files'] = FileManagerType.regular


DefaultFileBrowserFallback = dict(
    gnome='nautilus',
    ubuntugnome='nautilus',
    popgnome='nautilus',
    unity='nautilus',
    kde='dolphin',
    cinnamon='nemo',
    mate='caja',
    xfce='thunar',
    lxde='pcmanfm',
    lxqt='pcmanfm-qt',
    deepin='dde-file-manager',
    kylin='peony',
    pantheon='io.elementary.files',
)


# Sync with value in install.py
class Distro(Enum):
    debian = 1
    ubuntu = 2
    fedora = 3
    neon = 4
    linuxmint = 5
    zorin = 6
    arch = 7
    opensuse = 8
    manjaro = 9
    galliumos = 10
    peppermint = 11
    elementary = 13
    centos = 14
    centos7 = 15
    gentoo = 16
    deepin = 17
    kylin = 18
    popos = 19
    unknown = 20


orientation_offset = dict(
    arw=106,
    cr2=126,
    cr3=60000,  # assuming ExifTool (exiv2 >= 0.28 required for CR3)
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
orientation_offset['3fr'] = 132

orientation_offset_exiftool = dict(
    arw=350,
    cr2=320,
    cr3=60000,
    crw=20,
    dcr=8196,
    dng=644,
    iiq=20,
    mef=376,
    mrw=152580,
    nef=392,
    nrw=94,
    orf=6148,
    pef=332,
    raf=70660,
    raw=548,
    rw2=709636,
    sr2=276,
    srw=126
)
orientation_offset_exiftool['3fr'] = 376

datetime_offset = dict(
    arw=1540,
    cr2=1028,
    cr3=60000,  # assuming ExifTool
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
    srw=508,
    mts=5000,
    m2t=5000,
    m2ts=5000,
    mp4=50000,
    avi=50000,
    mov=250000,
)
datetime_offset['3fr'] = 1540
datetime_offset['3gp'] = 5000

datetime_offset_exiftool = dict(
    arw=1540,
    cr2=1000,  # varies widely :-/
    cr3=60000,
    crw=20,
    dng=3000,  # varies widely :-/
    mef=772,
    mrw=152580,
    nef=13316,
    nrw=488,
    orf=7172,
    pef=836,
    raf=70660,
    raw=932,
    rw2=709636,
    sr2=836,
    srw=496,
    x3f=69220070,
    mts=5000,
    m2t=5000,
    m2ts=5000,
    mp4=50000,
    avi=50000,
    mov=250000,
)
datetime_offset_exiftool['3fr'] = 1042
datetime_offset_exiftool['3gp'] = 5000

all_tags_offset = dict(
    arw=1848,
    cr2=94622,
    cr3=60000,  # assuming ExifTool
    dng=143774,
    mef=965,
    mrw=183096,
    nef=1126814,
    nrw=1848,
    orf=812242,
    pef=1042,
    raf=13522,
    raw=890885,
    rw2=1205458,
    sr2=1080,
    srw=614,
)
all_tags_offset['3fr'] = 1848

all_tags_offset_exiftool = dict(
    arw=1540,
    cr2=104453,
    cr3=60000,
    dng=143774,
    dcr=10450,
    mef=965,
    mrw=183096,
    nef=77213623,
    nrw=1848,
    orf=29113613,
    pef=183096,
    raf=84792,
    raw=890885,
    rw2=1205458,
    sr2=1080,
    srw=222418,
    x3f=7380128,
    mp4=130000,
    mts=1300000,
    mt2=1300000,
    m2ts=1300000,
    avi=50000,
    mov=250000
)
all_tags_offset_exiftool['3fr'] = 1042

thumbnail_offset = dict(
    jpg=100000,
    jpeg=100000,
    dng=100000,
    avi=500000,
    mod=500000,
    mov=2000000,
    mp4=2000000,
    mts=600000,
    m2t=600000,
    mpg=500000,
    mpeg=500000,
    tod=500000,
)

# Repeat video information here
thumbnail_offset_exiftool = dict(
    cr2=694277,
    cr3=45470,
    mrw=84792,
    nef=77213623,
    nrw=45470,
    raf=84792,
    raw=890885,
    rw2=1205458,
    sr2=222418,
    srw=812242,
    avi=500000,
    mod=500000,
    mov=2000000,
    mp4=2000000,
    mts=600000,
    m2t=600000,
    mpg=500000,
    mpeg=500000,
    tod=500000,
)



class RememberThisMessage(Enum):
    remember_choice = 1
    do_not_ask_again = 2
    do_not_warn_again = 3
    do_not_warn_again_about_missing_libraries = 4


class RememberThisButtons(Enum):
    yes_no = 1
    ok = 2


class CompletedDownloads(IntEnum):
    keep = 1
    clear = 2
    prompt = 3


class TreatRawJpeg(IntEnum):
    one_photo = 1
    two_photos = 2


class MarkRawJpeg(IntEnum):
    no_jpeg = 1
    no_raw = 2
    both = 3


# see https://developer.mozilla.org/en-US/docs/Mozilla/Localization/Localization_and_Plurals
class Plural(Enum):
    zero = 1
    two_form_single = 2
    two_form_plural = 3


class ScalingAction(Enum):
    turned_on = 1
    not_set = 2
    already_set = 3


class ScalingDetected(Enum):
    Qt = 1
    Xsetting = 2
    Qt_and_Xsetting = 3
    undetected = 4


# Use the character . to for download_name and path to indicate the user manually marked a
# file as previously downloaded
manually_marked_previously_downloaded = '.'

