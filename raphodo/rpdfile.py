# Copyright (C) 2011-2016 Damon Lynch <damonlynch@gmail.com>

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
__copyright__ = "Copyright 2011-2016, Damon Lynch"

import os
import time
from datetime import datetime
import uuid
import logging
import mimetypes
from collections import Counter, UserDict
from urllib.request import pathname2url
import locale
from typing import Optional, List, Tuple

from gettext import gettext as _

import raphodo.exiftool as exiftool
from raphodo.constants import (DownloadStatus, FileType, FileExtension, FileSortPriority,
                       ThumbnailCacheStatus, Downloaded, Desktop)

from raphodo.storage import get_desktop, gvfs_controls_mounts
import raphodo.metadataphoto as metadataphoto
import raphodo.metadatavideo as metadatavideo
from raphodo.utilities import thousands

import raphodo.problemnotification as pn


RAW_EXTENSIONS = ['arw', 'dcr', 'cr2', 'crw',  'dng', 'mos', 'mef', 'mrw',
                  'nef', 'nrw', 'orf', 'pef', 'raf', 'raw', 'rw2', 'sr2',
                  'srw']

JPEG_EXTENSIONS = ['jpg', 'jpe', 'jpeg']

JPEG_TYPE_EXTENSIONS = ['jpg', 'jpe', 'jpeg', 'mpo']

OTHER_PHOTO_EXTENSIONS = ['tif', 'tiff', 'mpo']

NON_RAW_IMAGE_EXTENSIONS = JPEG_EXTENSIONS + OTHER_PHOTO_EXTENSIONS

PHOTO_EXTENSIONS = RAW_EXTENSIONS + NON_RAW_IMAGE_EXTENSIONS

PHOTO_EXTENSIONS_WITHOUT_OTHER = RAW_EXTENSIONS + JPEG_EXTENSIONS

PHOTO_EXTENSIONS_SCAN = PHOTO_EXTENSIONS

AUDIO_EXTENSIONS = ['wav', 'mp3']


VIDEO_EXTENSIONS = ['3gp', 'avi', 'm2t', 'mov', 'mp4', 'mpeg','mpg', 'mod',
                    'tod', 'mts']

VIDEO_THUMBNAIL_EXTENSIONS = ['thm']


def file_type(file_extension: str) -> FileType:
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

def get_rpdfile(name: str, path: str, size: int, prev_full_name: str,
                prev_datetime: datetime,
                file_system_modification_time: float,
                thm_full_name: str, audio_file_full_name: str,
                xmp_file_full_name: str,
                scan_id: bytes, file_type: FileType,
                from_camera: bool,
                camera_model: Optional[str],
                camera_port: Optional[str],
                camera_display_name: Optional[str],
                is_mtp_device: Optional[bool],
                camera_memory_card_identifiers: Optional[List[int]]):

    if file_type == FileType.video:
        return Video(name, path, size,
                     prev_full_name, prev_datetime,
                     file_system_modification_time,
                     thm_full_name,
                     audio_file_full_name,
                     xmp_file_full_name,
                     scan_id,
                     from_camera,
                     camera_model,
                     camera_port,
                     camera_display_name,
                     is_mtp_device,
                     camera_memory_card_identifiers)
    else:
        return Photo(name, path, size,
                     prev_full_name, prev_datetime,
                     file_system_modification_time,
                     thm_full_name,
                     audio_file_full_name,
                     xmp_file_full_name,
                     scan_id,
                     from_camera,
                     camera_model,
                     camera_port,
                     camera_display_name,
                     is_mtp_device,
                     camera_memory_card_identifiers)

def file_types_by_number(no_photos: int, no_videos:int) -> str:
        """
        generate a string to be displayed to the user that can be used
        to show if a value refers to photos or videos or both, or just
        one of each
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
    function, and display the results to the user. Only the function
    running_file_count is scan specific.

    >>> f = FileTypeCounter()
    >>> f.summarize_file_count()
    ('0 photos or videos', 'photos or videos')
    >>> f.running_file_count()
    'scanning (found 0 photos and 0 videos)...'
    >>> f[FileType.photo] += 1
    >>> f.summarize_file_count()
    ('1 photo', 'photo')
    >>> f.running_file_count()
    'scanning (found 1 photos and 0 videos)...'
    >>> f[FileType.video] += 3
    >>> f
    FileTypeCounter({<FileType.video: 2>: 3, <FileType.photo: 1>: 1})
    >>> f[FileType.photo] += 5
    >>> f
    FileTypeCounter({<FileType.photo: 1>: 6, <FileType.video: 2>: 3})
    >>> f.summarize_file_count()
    ('9 photos and videos', 'photos and videos')
    >>> f.running_file_count()
    'scanning (found 6 photos and 3 videos)...'
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
        file_count_summary = _("%(number)s %(filetypes)s") % \
                              {'number': thousands(self[FileType.photo] + self[FileType.video]),
                               'filetypes': file_types_present}
        return (file_count_summary, file_types_present)

    def running_file_count(self) -> str:
        """
        Displays raw numbers of photos and videos. Displayed as a scan
        is occurring.
        :return some variaton of 'scanning (found 6 photos and 3 videos)...'
        """
        return _("scanning (found %(photos)s photos and %(videos)s videos)...") \
               % ({'photos': thousands(self[FileType.photo]),
                   'videos': thousands(self[FileType.video])})

class RPDFile:
    """
    Base class for photo or video file, with metadata
    """

    title = ''
    title_capitalized = ''

    def __init__(self, name: str, path: str, size: int,
                 prev_full_name: str, prev_datetime: datetime,
                 modification_time: float, thm_full_name: str,
                 audio_file_full_name: str,
                 xmp_file_full_name: str,
                 scan_id: bytes,
                 from_camera: bool,
                 camera_model: Optional[str]=None,
                 camera_port: Optional[str]=None,
                 camera_display_name: Optional[str]=None,
                 is_mtp_device: Optional[bool]=None,
                 camera_memory_card_identifiers: Optional[List[int]]=None) -> None:
        """

        :param name: filename (without path)
        :param path: path of the file
        :param size: file size
        :param modification_time: file modification time
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
        :param scan_id: id of the scan
        :param from_camera: whether the file is being downloaded from a
         camera
        :param camera_model: if downloaded from a camera, the camera
         model name (not including the port)
        :param camera_port: if downloaded from a camera, the port
         as reported by gphoto2
        :param is_mtp_device: if downloaded from a camera, whether the camera is an
         MTP device
        :param camera_memory_card_identifiers: if downloaded from a
         camera, and the camera has more than one memory card, a list
         of numeric identifiers (i.e. 1 or 2) identifying which memory
         card the file came from
        """

        self.from_camera = from_camera
        self.camera_model = camera_model
        self.camera_port = camera_port
        self.camera_display_name = camera_display_name
        self.is_mtp_device = is_mtp_device == True

        self.path = path

        self.name = name

        self.prev_full_name = prev_full_name
        self.prev_datetime = prev_datetime

        self.full_file_name = os.path.join(path, name)

        # Indicate whether file is a photo or video
        self._assign_file_type()

        # Remove the period from the extension and make it lower case
        self.extension = os.path.splitext(name)[1][1:].lower()
        # Classify file based on its type e.g. jpeg, raw or tiff etc.
        self.extension_type = extension_type(self.extension)
        self.sort_priority = get_sort_priority(self.extension_type, self.file_type)

        self.mime_type = mimetypes.guess_type(name)[0]

        assert size > 0
        self.size = size

        self.modification_time = float(modification_time)

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

        self.status = DownloadStatus.not_downloaded
        self.problem = None # class Problem in problemnotifcation.py

        self.scan_id = int(scan_id)
        self.unique_id = '{}:{}'.format(self.scan_id, uuid.uuid4())

        self.job_code = None

        # freedesktop.org cache thumbnails
        # http://specifications.freedesktop.org/thumbnail-spec/thumbnail-spec-latest.html
        self.thumbnail_status = ThumbnailCacheStatus.not_ready
        self.fdo_thumbnail_128_name = ''
        self.fdo_thumbnail_256_name = ''

        # generated values

        self.cache_full_file_name = ''
        self.temp_full_file_name = ''
        self.temp_thm_full_name = ''
        self.temp_audio_full_name = ''
        self.temp_xmp_full_name = ''
        self.temp_cache_full_file_chunk = ''

        self.download_start_time = None

        self.download_folder = ''
        self.download_subfolder = ''
        self.download_path = ''
        self.download_name = ''
        self.download_full_file_name = '' #file name with path
        self.download_full_base_name = '' #file name with path but no extension
        self.download_thm_full_name = ''  #name of THM (thumbnail) file with path
        self.download_xmp_full_name = ''  #name of XMP sidecar with path
        self.download_audio_full_name = ''  #name of the WAV or MP3 audio file with path

        self.metadata = None

        # Values that will be inserted in download process --
        # (commented out because they're not needed until then)

        #self.sequences = None
        #self.download_folder
        self.subfolder_pref_list = []
        self.name_pref_list = []
        #self.thm_extension = ''
        #self.wav_extension = ''
        #self.xmp_extension = ''

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

    def previously_downloaded(self) -> bool:
        """
        :return: True if the file has been downloaded before,according
         to our SQL database
        """
        return self.prev_full_name is not None

    def has_audio(self) -> bool:
        """
        :return:True if the file has an associated audio file, else False
        """
        return self.audio_file_full_name is not None

    def get_uri(self, desktop_environment: Optional[bool]=False) -> str:
        """
        Generate and return the URI for the file
        :param desktop_environment: if True, will to generate a URI accepted
         by Gnome and KDE desktops, which means adjusting the URI if it appears to be an
         MTP mount. Horribly hackish. Includes the port too.
        :return: the URI
        """
        if self.status in Downloaded:
            uri = 'file://{}'.format(pathname2url(
                self.download_full_file_name))
        else:
            full_file_name = self.full_file_name
            if self.camera_model is None:
                prefix = 'file://'
                if desktop_environment:
                    desktop = get_desktop()
                    if desktop in (Desktop.mate, Desktop.kde):
                        full_file_name = os.path.dirname(full_file_name)
            else:
                if not desktop_environment:
                    prefix = 'gphoto2://'
                else:
                    # Attempt to generate a URI accepted by desktop environments
                    if self.is_mtp_device:
                        f = full_file_name
                        # Remove the top level directory
                        full_file_name = f[f[1:].find('/')+1:]

                        desktop = get_desktop()
                        if gvfs_controls_mounts():
                            prefix = 'mtp://'+ pathname2url('[{}]/Internal storage'.format(
                                self.camera_port))
                        elif desktop == Desktop.kde:
                            prefix = 'mtp:/' + pathname2url('{}/Internal storage'.format(
                                self.camera_display_name))
                            # Dolphin doesn't highlight the file if it's passed.
                            # Instead it tries to open it, but fails.
                            # So don't pass the file, just the directory it's in.
                            full_file_name = os.path.dirname(full_file_name)
                    else:
                        prefix = 'gphoto2://' + pathname2url('[{}]'.format(self.camera_port))
            uri = '{}{}'.format(prefix, pathname2url(full_file_name))
        return uri

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

    def initialize_problem(self):
        self.problem = pn.Problem()
        # these next values are used to display in the error log window
        # the information in them can vary from other forms of display of errors
        self.error_title = self.error_msg = self.error_extra_detail = ''

    def has_problem(self):
        if self.problem is None:
            return False
        else:
            return self.problem.has_problem()

    def add_problem(self, component, problem_definition, *args):
        if self.problem is None:
            self.initialize_problem()
        self.problem.add_problem(component, problem_definition, *args)

    def add_extra_detail(self, extra_detail, *args):
        self.problem.add_extra_detail(extra_detail, *args)

    def __repr__(self):
        return "{}\t{}".format(self.name, datetime.fromtimestamp(
            self.modification_time).strftime('%Y-%m-%d %H:%M:%S'))

class Photo(RPDFile):

    title = _("photo")
    title_capitalized = _("Photo")

    def _assign_file_type(self):
        self.file_type = FileType.photo

    def load_metadata(self, exiftool_process: exiftool.ExifTool,
                      file_source: Optional[str]=None) -> bool:
        """
        Use GExiv2 to read the photograph's metadata
        :param exiftool_process: the deamon exiftool process
        :param file_source: full path of file from which file to read
         the metadata. If not specified, defaults to
         self.full_file_name.
        :return: True if successful, False otherwise
        """
        try:
            self.metadata = metadataphoto.MetaData(file_source, exiftool_process)
        except:
            logging.warning("Could not read metadata from {}".format(self.full_file_name))
            return False
        else:
            return True


class Video(RPDFile):

    title = _("video")
    title_capitalized = _("Video")

    def _assign_file_type(self):
        self.file_type = FileType.video

    def load_metadata(self, exiftool_process: exiftool.ExifTool,
                      file_source: Optional[str]=None) -> bool:
        """
        Use ExifTool to read the video's metadata
        :param exiftool_process: the deamon exiftool process
        :param file_source: full path of file from which file to read
         the metadata. If not specified, defaults to
         self.full_file_name.
        :return: True if successful, False otherwise
        """

        self.metadata = metadatavideo.MetaData(file_source, exiftool_process)
        return True


# class SamplePhoto(Photo):
#     def __init__(self, sample_name='IMG_0524.CR2', sequences=None):
#         Photo.__init__(self, name=sample_name,
#                        display_name=sample_name,
#                        path='/media/EOS_DIGITAL/DCIM/100EOS5D',
#                        size=23516764,
#                        file_system_modification_time=time.time(),
#                        scan_pid=2033,
#                        file_id='9873afe',
#                        thm_full_name=None,
#                        audio_file_full_name=None)
#         self.sequences = sequences
#         self.metadata = metadataphoto.DummyMetaData()
#         self.download_start_time = datetime.now()
#
# class SampleVideo(Video):
#     def __init__(self, sample_name='MVI_1379.MOV', sequences=None):
#         Video.__init__(self, name=sample_name,
#                        display_name=sample_name,
#                        path='/media/EOS_DIGITAL/DCIM/100EOS5D',
#                        size=823513764,
#                        file_system_modification_time=time.time(),
#                        scan_pid=2033,
#                        file_id='9873qrsfe',
#                        thm_full_name=None,
#                        audio_file_full_name=None)
#         self.sequences = sequences
#         self.metadata = metadatavideo.DummyMetaData(sample_name, None)
#         self.download_start_time = datetime.now()
