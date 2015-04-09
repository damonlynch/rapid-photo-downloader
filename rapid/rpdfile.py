__author__ = 'Damon Lynch'

# Copyright (C) 2011-2015 Damon Lynch <damonlynch@gmail.com>

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

import os
import time
import datetime
import uuid
import logging
import mimetypes
from collections import Counter

from gettext import gettext as _

from constants import (DownloadStatus, FileType)
import metadataphoto
import metadatavideo

import problemnotification as pn


RAW_EXTENSIONS = ['arw', 'dcr', 'cr2', 'crw',  'dng', 'mos', 'mef', 'mrw',
                  'nef', 'nrw', 'orf', 'pef', 'raf', 'raw', 'rw2', 'sr2',
                  'srw']

JPEG_EXTENSIONS = ['jpg', 'jpe', 'jpeg']

# FIXME does QT5 QImage even support TIFF? On Ubuntu, yes.
#
NON_RAW_IMAGE_EXTENSIONS = JPEG_EXTENSIONS + ['tif', 'tiff', 'mpo']

PHOTO_EXTENSIONS = RAW_EXTENSIONS + NON_RAW_IMAGE_EXTENSIONS

AUDIO_EXTENSIONS = ['wav', 'mp3']


VIDEO_EXTENSIONS = ['3gp', 'avi', 'm2t', 'mov', 'mp4', 'mpeg','mpg', 'mod',
                    'tod', 'mts']

VIDEO_THUMBNAIL_EXTENSIONS = ['thm']


def file_type(file_extension: str) -> FileType:
    """
    Returns file type (photo/video), or None if it's neither.
    Checks only the file's extension
    """

    if file_extension in PHOTO_EXTENSIONS:
        return FileType.photo
    elif file_extension in VIDEO_EXTENSIONS:
        return FileType.video
    return None

def get_rpdfile(name, path, size,
                file_system_modification_time,
                thm_full_name, audio_file_full_name,
                scan_id, file_type, from_camera):

    if file_type == FileType.video:
        return Video(name, path, size,
                     file_system_modification_time, thm_full_name,
                     audio_file_full_name,
                     scan_id, from_camera)
    else:
        return Photo(name, path, size,
                     file_system_modification_time, thm_full_name,
                     audio_file_full_name,
                     scan_id, from_camera)

class FileTypeCounter(Counter):
    r"""
    Track the number of photos and videos in a scan, and display the
    results to the user

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

        no_videos = self[FileType.video]
        no_photos = self[FileType.photo]

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

    def summarize_file_count(self) -> str:
        """
        Summarizes the total number of photos and/or videos that can be
        downloaded. Displayed in the progress bar at the top of the
        main application window after a scan is finished.

        :return number of files, e.g. "433 photos and videos" or
        "23 videos".
        """
        file_types_present = self.file_types_present()
        file_count_summary = _("%(number)s %(filetypes)s") % \
                              {'number': sum(self.values()),
                               'filetypes': file_types_present}
        return (file_count_summary, file_types_present)

    def running_file_count(self) -> str:
        """
        Displays raw numbers of photos and videos. Displayed as a scan
        is occurring.
        :return some variaton of 'scanning (found 6 photos and 3 videos)...'
        """
        return _("scanning (found %(photos)s photos and %(videos)s videos)...") \
               % ({'photos': self[FileType.photo], 'videos': self[
            FileType.video]})

class RPDFile:
    """
    Base class for photo or video file, with metadata
    """

    def __init__(self, name: str, path: str, size: int,
                 modification_time: float, thm_full_name: str,
                 audio_file_full_name: str,
                 scan_id: bytes,
                 from_camera: bool):
        """

        :param name: filename
        :param path: path of the file
        :param size: file size
        :param modification_time: file modification time
        :param thm_full_name: name and path of and associated thumbnail
               file
        :param audio_file_full_name: name and path of any associated
               audio file
        :param scan_id: id of the scan
        :param from_camera: whether the file is being downloaded from a
               camera
        """

        self.from_camera = from_camera

        self.path = path

        self.name = name

        self.full_file_name = os.path.join(path, name)
        self.extension = os.path.splitext(name)[1][1:].lower()

        self.mime_type = mimetypes.guess_type(name)[0]

        self.size = size

        self.modification_time = modification_time

        #full path and name of thumbnail file that is associated with some videos
        self.thm_full_name = thm_full_name

        #full path and name of audio file that is associated with some photos
        # and maybe one day videos, e.g. found with the Canon 1D series of
        # cameras
        self.audio_file_full_name = audio_file_full_name

        self.status = DownloadStatus.not_downloaded
        self.problem = None # class Problem in problemnotifcation.py

        self._assign_file_type() # Indicate whether file is a photo or video

        self.scan_id = int(scan_id)
        self.unique_id = '{}:{}'.format(self.scan_id, uuid.uuid4())

        self.job_code = None

        # indicates whether to generate a thumbnail during the copy
        # files process
        self.generate_thumbnail = False

        # generated values

        self.cache_full_file_name = ''
        self.temp_full_file_name = ''
        self.temp_thm_full_name = ''
        self.temp_audio_full_name = ''
        self.temp_xmp_full_name = ''

        self.download_start_time = None

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
        #self.subfolder_pref_list = []
        #self.name_pref_list = []
        #strip_characters = False
        #self.thm_extension = ''
        #self.wav_extension = ''
        #self.xmp_extension = ''

        #these values are set only if they were written to an xmp sidecar
        #in the filemodify process
        #self.new_aperture = ''
        #self.new_focal_length = ''

    def is_jpeg(self) -> bool:
        """
        Uses guess from mimetypes module
        :return:True if the image is a jpeg image
        """
        return self.mime_type == 'image/jpeg'

    def is_raw(self) -> bool:
        """
        Inspects file extenstion to determine if a RAW file
        :return: True if the image is a RAW file
        """
        return self.extension in RAW_EXTENSIONS

    def _assign_file_type(self):
        self.file_type = None

    def _load_file_for_metadata(self, temp_file):
        if temp_file:
            return self.temp_full_file_name
        else:
            return self.full_file_name

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
        return "{}\t{}".format(self.name, datetime.datetime.fromtimestamp(
            self.modification_time).strftime('%Y-%m-%d %H:%M:%S'))

class Photo(RPDFile):

    title = _("photo")
    title_capitalized = _("Photo")

    def _assign_file_type(self):
        self.file_type = FileType.photo


    # def load_metadata(self, temp_file=False):
    #     self.metadata = metadataphoto.MetaData(self._load_file_for_metadata(temp_file))
    #     try:
    #         self.metadata.read()
    #     except:
    #         logger.warning("Could not read metadata from {}".format(
    #                        self.full_file_name))
    #         return False
    #     else:
    #         return True


class Video(RPDFile):

    title = _("video")
    title_capitalized = _("Video")

    def _assign_file_type(self):
        self.file_type = FileType.video

    def load_metadata(self, temp_file=False):
        self.metadata = metadatavideo.ExifToolMetaData(
            self._load_file_for_metadata(temp_file))
        return True



class SamplePhoto(Photo):
    def __init__(self, sample_name='IMG_0524.CR2', sequences=None):
        Photo.__init__(self, name=sample_name,
                       display_name=sample_name,
                       path='/media/EOS_DIGITAL/DCIM/100EOS5D',
                       size=23516764,
                       file_system_modification_time=time.time(),
                       scan_pid=2033,
                       file_id='9873afe',
                       thm_full_name=None,
                       audio_file_full_name=None)
        self.sequences = sequences
        self.metadata = metadataphoto.DummyMetaData()
        self.download_start_time = datetime.datetime.now()

class SampleVideo(Video):
    def __init__(self, sample_name='MVI_1379.MOV', sequences=None):
        Video.__init__(self, name=sample_name,
                       display_name=sample_name,
                       path='/media/EOS_DIGITAL/DCIM/100EOS5D',
                       size=823513764,
                       file_system_modification_time=time.time(),
                       scan_pid=2033,
                       file_id='9873qrsfe',
                       thm_full_name=None,
                       audio_file_full_name=None)
        self.sequences = sequences
        self.metadata = metadatavideo.DummyMetaData(sample_name, None)
        self.download_start_time = datetime.datetime.now()
