# Copyright (C) 2011-2017 Damon Lynch <damonlynch@gmail.com>

# This file is part of Rapid Photo Downloader.
#
# Rapid Photo Downloader is free software: you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published by
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
__copyright__ = "Copyright 2011-2017, Damon Lynch"

import os
import time
from datetime import datetime
import uuid
import logging
import mimetypes
from collections import Counter, UserDict
from urllib.request import pathname2url
import locale
from collections import defaultdict
from typing import Optional, List, Tuple, Union, Any, Dict

from gettext import gettext as _
import gi
gi.require_version('GLib', '2.0')
from gi.repository import GLib

import raphodo.exiftool as exiftool
from raphodo.constants import (DownloadStatus, FileType, FileExtension, FileSortPriority,
                               ThumbnailCacheStatus, Downloaded, Desktop, thumbnail_offset,
                               DeviceTimestampTZ, ThumbnailCacheDiskStatus, ExifSource)

from raphodo.storage import get_uri, CameraDetails
import raphodo.metadataphoto as metadataphoto
import raphodo.metadatavideo as metadatavideo
from raphodo.utilities import thousands, make_internationalized_list, datetime_roughly_equal
from raphodo.problemnotification import Problem, make_href


RAW_EXTENSIONS = [
    '3fr', 'arw', 'dcr', 'cr2', 'crw',  'dng', 'mos', 'mef', 'mrw', 'nef', 'nrw', 'orf', 'pef',
    'raf', 'raw', 'rw2', 'sr2', 'srw'
]

JPEG_EXTENSIONS = ['jpg', 'jpe', 'jpeg']

JPEG_TYPE_EXTENSIONS = ['jpg', 'jpe', 'jpeg', 'mpo']

OTHER_PHOTO_EXTENSIONS = ['tif', 'tiff', 'mpo']

NON_RAW_IMAGE_EXTENSIONS = JPEG_EXTENSIONS + OTHER_PHOTO_EXTENSIONS

PHOTO_EXTENSIONS = RAW_EXTENSIONS + NON_RAW_IMAGE_EXTENSIONS

PHOTO_EXTENSIONS_WITHOUT_OTHER = RAW_EXTENSIONS + JPEG_EXTENSIONS

PHOTO_EXTENSIONS_SCAN = PHOTO_EXTENSIONS

AUDIO_EXTENSIONS = ['wav', 'mp3']


VIDEO_EXTENSIONS = [
    '3gp', 'avi', 'm2t', 'm2ts', 'mov', 'mp4', 'mpeg','mpg', 'mod', 'tod', 'mts'
]

VIDEO_THUMBNAIL_EXTENSIONS = ['thm']

ALL_USER_VISIBLE_EXTENSIONS = PHOTO_EXTENSIONS + VIDEO_EXTENSIONS + ['xmp', 'log']

ALL_KNOWN_EXTENSIONS = ALL_USER_VISIBLE_EXTENSIONS + AUDIO_EXTENSIONS + VIDEO_THUMBNAIL_EXTENSIONS

MUST_CACHE_VIDEOS = [video for video in VIDEO_EXTENSIONS if thumbnail_offset.get(video) is None]


def file_type(file_extension: str) -> Optional[FileType]:
    """
    Returns file type (photo/video), or None if it's neither.
    Checks only the file's extension
    """

    if file_extension in PHOTO_EXTENSIONS_SCAN:
        return FileType.photo
    elif file_extension in VIDEO_EXTENSIONS:
        return FileType.video
    return None


def extension_type(file_extension: str) -> FileExtension:
    """
    Returns the type of file as indicated by the filename extension.

    :param file_extension: lowercase filename extension
    :return: Enum indicating file type
    """
    if file_extension in RAW_EXTENSIONS:
        return FileExtension.raw
    elif file_extension in JPEG_EXTENSIONS:
        return FileExtension.jpeg
    elif file_extension in OTHER_PHOTO_EXTENSIONS:
        return FileExtension.other_photo
    elif file_extension in VIDEO_EXTENSIONS:
        return FileExtension.video
    elif file_extension in AUDIO_EXTENSIONS:
        return FileExtension.audio
    else:
        return FileExtension.unknown


def get_sort_priority(extension: FileExtension, file_type: FileType) -> FileSortPriority:
    """
    Classifies the extension by sort priority.

    :param extension: the extension's category
    :param file_type: whether photo or video
    :return: priority
    """
    if file_type == FileType.photo:
        if extension in (FileExtension.raw, FileExtension.jpeg):
            return FileSortPriority.high
        else:
            return FileSortPriority.low
    else:
        return FileSortPriority.high


def get_rpdfile(name: str,
                path: str,
                size: int,
                prev_full_name: Optional[str],
                prev_datetime: Optional[datetime],
                device_timestamp_type: DeviceTimestampTZ,
                mtime: float,
                mdatatime: float,
                thumbnail_cache_status: ThumbnailCacheDiskStatus,
                thm_full_name: Optional[str],
                audio_file_full_name: Optional[str],
                xmp_file_full_name: Optional[str],
                log_file_full_name: Optional[str],
                scan_id: bytes,
                file_type: FileType,
                from_camera: bool,
                camera_details: Optional[CameraDetails],
                camera_memory_card_identifiers: Optional[List[int]],
                never_read_mdatatime: bool,
                device_display_name: str,
                device_uri: str,
                raw_exif_bytes: Optional[bytes],
                exif_source: Optional[ExifSource],
                problem: Optional[Problem]):

    if file_type == FileType.video:
        return Video(
            name=name,
            path=path,
            size=size,
            prev_full_name=prev_full_name,
            prev_datetime=prev_datetime,
            device_timestamp_type=device_timestamp_type,
            mtime=mtime,
            mdatatime=mdatatime,
            thumbnail_cache_status=thumbnail_cache_status,
            thm_full_name=thm_full_name,
            audio_file_full_name=audio_file_full_name,
            xmp_file_full_name=xmp_file_full_name,
            log_file_full_name=log_file_full_name,
            scan_id=scan_id,
            from_camera=from_camera,
            camera_details=camera_details,
            camera_memory_card_identifiers=camera_memory_card_identifiers,
            never_read_mdatatime=never_read_mdatatime,
            device_display_name=device_display_name,
            device_uri=device_uri,
            raw_exif_bytes=raw_exif_bytes,
            problem=problem
        )
    else:
        return Photo(
            name=name,
            path=path,
            size=size,
            prev_full_name=prev_full_name,
            prev_datetime=prev_datetime,
            device_timestamp_type=device_timestamp_type,
            mtime=mtime,
            mdatatime=mdatatime,
            thumbnail_cache_status=thumbnail_cache_status,
            thm_full_name=thm_full_name,
            audio_file_full_name=audio_file_full_name,
            xmp_file_full_name=xmp_file_full_name,
            log_file_full_name=log_file_full_name,
            scan_id=scan_id,
            from_camera=from_camera,
            camera_details=camera_details,
            camera_memory_card_identifiers=camera_memory_card_identifiers,
            never_read_mdatatime=never_read_mdatatime,
            device_display_name=device_display_name,
            device_uri=device_uri,
            raw_exif_bytes=raw_exif_bytes,
            exif_source=exif_source,
            problem=problem
        )


def file_types_by_number(no_photos: int, no_videos: int) -> str:
        """
        Generate a string show number of photos and videos

        :param no_photos: number of photos
        :param no_videos: number of videos
        """
        if (no_videos > 0) and (no_photos > 0):
            v = _('photos and videos')
        elif (no_videos == 0) and (no_photos == 0):
            v = _('photos or videos')
        elif no_videos > 0:
            if no_videos > 1:
                v = _('videos')
            else:
                v = _('video')
        else:
            if no_photos > 1:
                v = _('photos')
            else:
                v = _('photo')
        return v


def make_key(file_t: FileType, path: str) -> str:
    return '{}:{}'.format(path, file_t.value)


class FileSizeSum(UserDict):
    """ Sum size in bytes of photos and videos """
    def __missing__(self, key):
        self[key] = 0
        return self[key]

    def sum(self, basedir: Optional[str]=None) -> int:
        if basedir is not None:
            return self[make_key(FileType.photo, basedir)] + self[make_key(FileType.video, basedir)]
        else:
            return self[FileType.photo] + self[FileType.video]


class FileTypeCounter(Counter):
    r"""
    Track the number of photos and videos in a scan or for some other
    function, and display the results to the user.

    >>> locale.setlocale(locale.LC_ALL, ('en_US', 'utf-8'))
    'en_US.UTF-8'
    >>> f = FileTypeCounter()
    >>> f.summarize_file_count()
    ('0 photos or videos', 'photos or videos')
    >>> f.file_types_present_details()
    ''
    >>> f[FileType.photo] += 1
    >>> f.summarize_file_count()
    ('1 photo', 'photo')
    >>> f.file_types_present_details()
    '1 Photo'
    >>> f.file_types_present_details(singular_natural=True)
    'a photo'
    >>> f[FileType.photo] = 0
    >>> f[FileType.video] = 1
    >>> f.file_types_present_details(singular_natural=True)
    'a video'
    >>> f[FileType.photo] += 1
    >>> f.file_types_present_details(singular_natural=True)
    'a photo and a video'
    >>> f[FileType.video] += 2
    >>> f
    FileTypeCounter({<FileType.video: 2>: 3, <FileType.photo: 1>: 1})
    >>> f.file_types_present_details()
    '1 Photo and 3 Videos'
    >>> f[FileType.photo] += 5
    >>> f
    FileTypeCounter({<FileType.photo: 1>: 6, <FileType.video: 2>: 3})
    >>> f.summarize_file_count()
    ('9 photos and videos', 'photos and videos')
    >>> f.file_types_present_details()
    '6 Photos and 3 Videos'
    >>> f2 = FileTypeCounter({FileType.photo:11, FileType.video: 12})
    >>> f2.file_types_present_details()
    '11 Photos and 12 Videos'
    """

    def file_types_present(self) -> str:
        """
        Display the types of files present in the scan
        :return a string to be displayed to the user that can be used
        to show if a value refers to photos or videos or both, or just
        one of each
        """

        return file_types_by_number(self[FileType.photo], self[FileType.video])

    def summarize_file_count(self) -> Tuple[str, str]:
        """
        Summarizes the total number of photos and/or videos that can be
        downloaded. Displayed in the progress bar at the top of the
        main application window after a scan is finished.

        :return tuple with (1) number of files, e.g.
         "433 photos and videos" or "23 videos". and (2) file types
         present e.g. "photos and videos"
        """
        file_types_present = self.file_types_present()
        file_count_summary = _("%(number)s %(filetypes)s") % dict(
            number=thousands(self[FileType.photo] + self[FileType.video]),
            filetypes=file_types_present
        )
        return file_count_summary, file_types_present

    def file_types_present_details(self, title_case=True, singular_natural=False) -> str:
        """

        :param title_case:
        :param singular_natural: if True, instead of '1 photo', return 'A photo'. If True,
         title_case parameter is treated as always False.
        :return:
        """

        p = self[FileType.photo]
        v = self[FileType.video]

        if v > 1:
            videos =  _('%(no_videos)s Videos') % dict(no_videos=thousands(v))
        elif v == 1:
            if singular_natural:
                # translators: natural language expression signifying a single video
                videos = _('a video')
            else:
                videos =  _('1 Video')

        if p > 1:
            photos = _('%(no_photos)s Photos') % dict(no_photos=thousands(p))
        elif p == 1:
            if singular_natural:
                # translators: natural language expression signifying a single photo
                photos = _('a photo')
            else:
                photos = _('1 Photo')

        if (p > 0) and (v > 0):
            s = make_internationalized_list([photos, videos])
        elif (p == 0) and (v == 0):
            return ''
        elif v > 0:
            s = videos
        else:
            s = photos

        if title_case or singular_natural:
            return s
        else:
            return s.lower()


class RPDFile:
    """
    Base class for photo or video file, with metadata
    """

    title = ''
    title_capitalized = ''

    def __init__(self, name: str,
                 path: str,
                 size: int,
                 prev_full_name: Optional[str],
                 prev_datetime: Optional[datetime],
                 device_timestamp_type: DeviceTimestampTZ,
                 mtime: float,
                 mdatatime: float,
                 thumbnail_cache_status: ThumbnailCacheDiskStatus,
                 thm_full_name: Optional[str],
                 audio_file_full_name: Optional[str],
                 xmp_file_full_name: Optional[str],
                 log_file_full_name: Optional[str],
                 scan_id: bytes,
                 from_camera: bool,
                 never_read_mdatatime: bool,
                 device_display_name: str,
                 device_uri:str,
                 camera_details: Optional[CameraDetails]=None,
                 camera_memory_card_identifiers: Optional[List[int]]=None,
                 raw_exif_bytes: Optional[bytes]=None,
                 exif_source: Optional[ExifSource]=None,
                 problem: Optional[Problem]=None) -> None:
        """

        :param name: filename, including the extension, without its path
        :param path: path of the file
        :param size: file size
        :param device_timestamp_type: the method with which the device
         records timestamps.
        :param mtime: file modification time
        :param mdatatime: file time recorded in metadata
        :param thumbnail_cache_status: whether there is an entry in the thumbnail
         cache or not
        :param prev_full_name: the name and path the file was
         previously downloaded with, else None
        :param prev_datetime: when the file was previously downloaded,
         else None
        :param thm_full_name: name and path of and associated thumbnail
         file
        :param audio_file_full_name: name and path of any associated
         audio file
        :param xmp_file_full_name: name and path of any associated XMP
         file
        :param log_file_full_name: name and path of any associated LOG
          file
        :param scan_id: id of the scan
        :param from_camera: whether the file is being downloaded from a
         camera
        :param never_read_mdatatime: whether to ignore the metadata
         date time when determining a photo or video's creation time,
         and rely only on the file modification time
        :param device_display_name: display name of the device the file was found on 
        :param device_uri: the uri of the device the file was found on
        :param camera_details: details about the camera, such as model name,
         port, etc.
        :param camera_memory_card_identifiers: if downloaded from a
         camera, and the camera has more than one memory card, a list
         of numeric identifiers (i.e. 1 or 2) identifying which memory
         card the file came from
        :param raw_exif_bytes: excerpt of the file's metadata in bytes format
        :param exif_source: source of photo metadata
        :param problem: any problems encountered
        """

        self.from_camera = from_camera
        self.camera_details = camera_details

        self.device_display_name = device_display_name
        self.device_uri = device_uri

        if camera_details is not None:
            self.camera_model = camera_details.model
            self.camera_port = camera_details.port
            self.camera_display_name = camera_details.display_name
            self.is_mtp_device = camera_details.is_mtp == True
            self.camera_storage_descriptions = camera_details.storage_desc
        else:
            self.camera_model = self.camera_port = self.camera_display_name = None
            self.camera_storage_descriptions = None
            self.is_mtp_device = False

        self.path = path

        self.name = name

        self.prev_full_name = prev_full_name
        self.prev_datetime = prev_datetime
        self.previously_downloaded = prev_full_name is not None

        self.full_file_name = os.path.join(path, name)

        # Used in sample RPD files
        self.raw_exif_bytes = raw_exif_bytes
        self.exif_source = exif_source

        # Indicate whether file is a photo or video
        self._assign_file_type()

        # Remove the period from the extension and make it lower case
        self.extension = os.path.splitext(name)[1][1:].lower()
        # Classify file based on its type e.g. jpeg, raw or tiff etc.
        self.extension_type = extension_type(self.extension)

        self.mime_type = mimetypes.guess_type(name)[0]

        assert size > 0
        self.size = size

        # Cached version of call to metadata.date_time()
        self._datetime = None  # type: Optional[datetime]

        ############################
        # self._no_datetime_metadata
        ############################
        # If True, tried to read the date time metadata, and failed
        # If None, haven't tried yet
        # If False, no problems encountered, got it (or it was assigned from mtime
        # when never_read_mdatatime is True)
        self._no_datetime_metadata = None  #type: Optional[bool]

        self.never_read_mdatatime = never_read_mdatatime
        if never_read_mdatatime:
            assert self.extension == 'dng'

        self.device_timestamp_type = device_timestamp_type

        ###########
        #self.ctime
        ###########
        #
        # self.ctime is the photo or video's creation time. It's value depends
        # on the values in self.modification_time and self.mdatatime. It's value
        # is set by the setter functions below.
        #
        # Ideally the file's metadata contains the date/time that the file
        # was created. However the metadata may not have been read yet (it's a slow
        # operation), or it may not exist or be invalid. In that case, need to rely on
        # the file modification time as a proxy, as reported by the file system or device.
        #
        # However that can also be misleading. On my Canon DSLR, for instance, if I'm in the
        # timezone UTC + 5, and I take a photo at 5pm, then the time stamp on the memory card
        # shows the photo being taken at 10pm when I look at it on the computer. The timestamp
        # written to the memory card should with this camera be read as
        # datetime.utcfromtimestamp(mtime), which would return a time zone naive value of 5pm.
        # In other words, the timestamp on the memory card is written as if it were always in
        # UTC, regardless of which timezone the photo was taken in.
        #
        # Yet this is not the case with a cellphone, where the file modification time knows
        # nothing about UTC and just saves it as a naive local time.

        self.mdatatime_caused_ctime_change = False

        # file modification time
        self.modification_time = mtime
        # date time recorded in metadata
        if never_read_mdatatime:
            self.mdatatime = mtime
        else:
            self.mdatatime = mdatatime
        self.mdatatime_caused_ctime_change = False

        # If a camera has more than one memory card, store a simple numeric
        # identifier to indicate which memory card it came from
        self.camera_memory_card_identifiers = camera_memory_card_identifiers

        # full path and name of thumbnail file that is associated with some
        # videos
        self.thm_full_name = thm_full_name

        # full path and name of audio file that is associated with some photos
        # and maybe one day videos, e.g. found with the Canon 1D series of
        # cameras
        self.audio_file_full_name = audio_file_full_name

        self.xmp_file_full_name = xmp_file_full_name
        # log files: see https://wiki.magiclantern.fm/userguide#movie_logging
        self.log_file_full_name = log_file_full_name

        self.status = DownloadStatus.not_downloaded
        self.problem = problem

        self.scan_id = int(scan_id)
        self.uid = uuid.uuid4().bytes

        self.job_code = None

        # freedesktop.org cache thumbnails
        # http://specifications.freedesktop.org/thumbnail-spec/thumbnail-spec-latest.html
        self.thumbnail_status = ThumbnailCacheStatus.not_ready  # type: ThumbnailCacheStatus
        self.fdo_thumbnail_128_name = ''
        self.fdo_thumbnail_256_name = ''
        # PNG data > 128x128 <= 256x256
        self.fdo_thumbnail_256 = None  # type: Optional[bytes]

        # Thee status of the file in the Rapid Photo Downloader thumbnail cache
        self.thumbnail_cache_status = thumbnail_cache_status

        # generated values

        self.cache_full_file_name = ''
        # temporary file used only for video metadata extraction:
        self.temp_sample_full_file_name = None  # type: Optional[str]
        # if True, the file is a complete copy of the original
        self.temp_sample_is_complete_file = False
        self.temp_full_file_name = ''
        self.temp_thm_full_name = ''
        self.temp_audio_full_name = ''
        self.temp_xmp_full_name = ''
        self.temp_log_full_name = ''
        self.temp_cache_full_file_chunk = ''

        self.download_start_time = None

        self.download_folder = ''
        self.download_subfolder = ''
        self.download_path = ''  # os.path.join(download_folder, download_subfolder)
        self.download_name = ''
        self.download_full_file_name = '' # filename with path
        self.download_full_base_name = '' # filename with path but no extension
        self.download_thm_full_name = ''  # name of THM (thumbnail) file with path
        self.download_xmp_full_name = ''  # name of XMP sidecar with path
        self.download_log_full_name = ''  # name of LOG associate file with path
        self.download_audio_full_name = ''  # name of the WAV or MP3 audio file with path

        self.thm_extension = ''
        self.audio_extension = ''
        self.xmp_extension = ''
        self.log_extension = ''

        self.metadata = None # type: Optional[Union[metadataphoto.MetaData, metadatavideo.MetaData]]
        self.metadata_failure = False # type: bool

        # User preference values used for name generation
        self.subfolder_pref_list = []  # type: List[str]
        self.name_pref_list = []  # type: List[str]
        self.generate_extension_case = ''  # type: str

        self.modified_via_daemon_process = False

        # If true, there was a name generation problem
        self.name_generation_problem = False

    def should_write_fdo(self) -> bool:
        """
        :return: True if a FDO thumbnail should be written for this file
        """
        return (self.thumbnail_status != ThumbnailCacheStatus.generation_failed and
                (self.is_raw() or self.is_tiff()))

    @property
    def modification_time(self) -> float:
        return self._mtime

    @modification_time.setter
    def modification_time(self, value: Union[float, int])  -> None:
        """
        See notes on self.ctime above
        """

        if not isinstance(value, float):
            value = float(value)
        if self.device_timestamp_type == DeviceTimestampTZ.is_utc:
            self._mtime = datetime.utcfromtimestamp(value).timestamp()
        else:
            self._mtime = value
        self._raw_mtime = value

        if not hasattr(self, '_mdatatime'):
            self.ctime = self._mtime

    @property
    def mdatatime(self) -> float:
        return self._mdatatime

    @mdatatime.setter
    def mdatatime(self, value: float) -> None:

        # Do not allow the value to be set to anything other than the modification time
        # if we are instructed to never read the metadata date time
        if self.never_read_mdatatime:
            value = self._mtime

        self._mdatatime = value

        # Only set the creation time if there is a value to set
        if value:
            self.mdatatime_caused_ctime_change = not datetime_roughly_equal(self.ctime, value)
            self.ctime = value
            if not self._datetime:
                self._datetime = datetime.fromtimestamp(value)
                self._no_datetime_metadata = False

    def ctime_mtime_differ(self) -> bool:
        """
        :return: True if the creation time and file system date
         modified time are not roughly the same. If the creation
         date is unknown (zero), the result will be False.
        """

        if not self._mdatatime:
            return False

        return not datetime_roughly_equal(self._mdatatime, self._mtime)

    def date_time(self, missing: Optional[Any]=None) -> datetime:
        """
        Returns the date time as found in the file's metadata, and caches it
        for later use.

        Will return the file's modification time if self.never_read_mdatatime
        is True.

        Expects the metadata to have already been loaded.

        :return: the metadata's date time value, else missing if not found or error
        """

        if self.never_read_mdatatime:
            # the value must have been set during the scan stage
            assert self._mdatatime == self._mtime
            return self._datetime

        if self._no_datetime_metadata:
            return missing
        if self._no_datetime_metadata is not None:
            return self._datetime

        # Have not yet tried to access the datetime metadata
        self._datetime = self.metadata.date_time(missing=None)
        self._no_datetime_metadata = self._datetime is None

        if self._no_datetime_metadata:
            return missing

        self.mdatatime = self._datetime.timestamp()
        return self._datetime

    def timestamp(self, missing: Optional[Any]=None) -> float:
        """
        Returns the time stamp as found in the file's metadata, and
        caches it for later use.

        Will return the file's modification time if self.never_read_mdatatime
        is True.

        Expects the metadata to have already been loaded.

        :return: the metadata's date time value, else missing if not found or error
        """


        dt = self.date_time(missing=missing)
        if self._no_datetime_metadata:
            return missing

        return dt.timestamp()

    def is_jpeg(self) -> bool:
        """
        Uses guess from mimetypes module
        :return:True if the image is a jpeg image
        """
        return self.mime_type == 'image/jpeg'


    def is_jpeg_type(self) -> bool:
        """
        :return:True if the image is a jpeg or MPO image
        """
        return self.mime_type == 'image/jpeg' or self.extension == 'mpo'

    def is_loadable(self) -> bool:
        """
        :return: True if the image can be loaded directly using Qt
        """
        return self.mime_type in ['image/jpeg', 'image/tiff']

    def is_raw(self) -> bool:
        """
        Inspects file extenstion to determine if a RAW file.

        :return: True if the image is a RAW file
        """
        return self.extension in RAW_EXTENSIONS

    def is_tiff(self) -> bool:
        """
        :return: True if the file is a tiff file
        """
        return self.mime_type == 'image/tiff'

    def has_audio(self) -> bool:
        """
        :return:True if the file has an associated audio file, else False
        """
        return self.audio_file_full_name is not None

    def get_current_full_file_name(self) -> str:
        if self.status in Downloaded:
            return self.download_full_file_name
        else:
            return self.full_file_name

    def get_current_name(self) -> str:
        if self.status in Downloaded:
            return self.download_name
        else:
            return self.name

    def get_uri(self, desktop_environment: Optional[bool]=True) -> str:
        """
        Generate and return the URI for the file

        :param desktop_environment: if True, will to generate a URI accepted
         by Gnome and KDE desktops, which means adjusting the URI if it appears to be an
         MTP mount. Includes the port too.
        :return: the URI
        """

        if self.status in Downloaded:
            return 'file://{}'.format(pathname2url(self.download_full_file_name))
        else:
            return get_uri(
                full_file_name = self.full_file_name, camera_details=self.camera_details,
                desktop_environment=desktop_environment
            )

    def get_souce_href(self) -> str:
        return make_href(
            name=self.name,
            uri=get_uri(
                full_file_name=self.full_file_name, camera_details=self.camera_details
            )
        )

    def get_current_href(self) -> str:
        return make_href(name=self.get_current_name(), uri=self.get_uri())

    def get_display_full_name(self) -> str:
        """
        Generate a full name indicating the file source.

        If it's not a camera, it will merely be the full name.
        If it's a camera, it will include the camera name
        :return: full name
        """

        if self.from_camera:
            return _('%(path)s on %(camera)s') % dict(path=self.full_file_name,
                                                     camera=self.camera_display_name)
        else:
            return self.full_file_name

    def _assign_file_type(self):
        self.file_type = None

    def __repr__(self):
        return "{}\t{}".format(self.name, datetime.fromtimestamp(
            self.modification_time).strftime('%Y-%m-%d %H:%M:%S'))


class Photo(RPDFile):

    title = _("photo")
    title_capitalized = _("Photo")

    def _assign_file_type(self):
        self.file_type = FileType.photo

    def load_metadata(self, full_file_name: Optional[str]=None,
                 raw_bytes: Optional[bytearray]=None,
                 app1_segment: Optional[bytearray]=None,
                 et_process: exiftool.ExifTool=None) -> bool:
        """
        Use GExiv2 to read the photograph's metadata.

        :param full_file_name: full path of file from which file to read
         the metadata.
        :param raw_bytes: portion of a non-jpeg file from which the
         metadata can be extracted
        :param app1_segment: the app1 segment of a jpeg file, from which
         the metadata can be read
        :param et_process: optional daemon ExifTool process
        :return: True if successful, False otherwise
        """

        try:
            self.metadata = metadataphoto.MetaData(full_file_name=full_file_name,
               raw_bytes=raw_bytes, app1_segment=app1_segment, et_process=et_process)
        except GLib.GError as e:
            logging.warning("Could not read metadata from %s. %s", self.full_file_name, e)
            self.metadata_failure = True
            return False
        except:
            logging.warning("Could not read metadata from %s", self.full_file_name)
            self.metadata_failure = True
            return False
        else:
            return True


class Video(RPDFile):

    title = _("video")
    title_capitalized = _("Video")

    def _assign_file_type(self):
        self.file_type = FileType.video

    def load_metadata(self, full_file_name: Optional[str]=None,
                 et_process: exiftool.ExifTool=None) -> bool:
        """
        Use ExifTool to read the video's metadata
        :param full_file_name: full path of file from which file to read
         the metadata.
        :param et_process: optional deamon exiftool process
        :return: Always returns True. Return value is needed to keep
         consistency with class Photo, where the value actually makes sense.
        """
        if full_file_name is None:
            if self.download_full_file_name:
                full_file_name = self.download_full_file_name
            elif self.cache_full_file_name:
                full_file_name = self.cache_full_file_name
            else:
                full_file_name = self.full_file_name
        self.metadata = metadatavideo.MetaData(full_file_name, et_process)
        return True


class SamplePhoto(Photo):
    def __init__(self, sample_name='IMG_1234.CR2', sequences=None):
        mtime = time.time()
        super().__init__(
            name=sample_name,
            path='/media/EOS_DIGITAL/DCIM/100EOS5D',
            size=23516764,
            prev_full_name=None,
            prev_datetime=None,
            device_timestamp_type=DeviceTimestampTZ.is_local,
            mtime=mtime,
            mdatatime=mtime,
            thumbnail_cache_status=ThumbnailCacheDiskStatus.not_found,
            thm_full_name=None,
            audio_file_full_name=None,
            xmp_file_full_name=None,
            log_file_full_name=None,
            scan_id=b'0',
            from_camera=False,
            never_read_mdatatime=False,
            device_display_name=_('Photos'),
            device_uri='file:///media/EOS_DIGITAL/'
        )
        self.sequences = sequences
        self.metadata = metadataphoto.DummyMetaData()
        self.download_start_time = datetime.now()


class SampleVideo(Video):
    def __init__(self, sample_name='MVI_1234.MOV', sequences=None):
        mtime = time.time()
        super().__init__(
            name=sample_name,
            path='/media/EOS_DIGITAL/DCIM/100EOS5D',
            size=823513764,
            prev_full_name=None,
            prev_datetime=None,
            device_timestamp_type=DeviceTimestampTZ.is_local,
            mtime=mtime,
            mdatatime=mtime,
            thumbnail_cache_status=ThumbnailCacheDiskStatus.not_found,
            thm_full_name=None,
            audio_file_full_name=None,
            xmp_file_full_name=None,
            log_file_full_name=None,
            scan_id=b'0',
            from_camera=False,
            never_read_mdatatime=False,
            device_display_name=_('Videos'),
            device_uri='file:///media/EOS_DIGITAL/'
        )
        self.sequences = sequences
        self.metadata = metadatavideo.DummyMetaData(sample_name, None)
        self.download_start_time = datetime.now()
