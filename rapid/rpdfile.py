#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2011 Damon Lynch <damonlynch@gmail.com>

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

import os
import gtk

import paths

from common import Configi18n
_ = Configi18n._

import config

import metadata as photometadata

PHOTO_EXTENSIONS = photometadata.RAW_FILE_EXTENSIONS + \
                   photometadata.NON_RAW_IMAGE_FILE_EXTENSIONS
                   
VIDEO_EXTENSIONS = []

EXTENSIONS = PHOTO_EXTENSIONS


def get_generic_photo_image():
    return gtk.gdk.pixbuf_new_from_file(paths.share_dir('glade3/photo.png'))
    
def get_generic_photo_image_icon():
    return gtk.gdk.pixbuf_new_from_file(paths.share_dir('glade3/photo_small_shadow.png'))
    
def get_photo_type_icon():
    return gtk.gdk.pixbuf_new_from_file(paths.share_dir('glade3/photo24.png'))
    
def get_generic_video_image():
    return gtk.gdk.pixbuf_new_from_file(paths.share_dir('glade3/video.png'))
    
def get_generic_video_image_icon():
    return gtk.gdk.pixbuf_new_from_file(paths.share_dir('glade3/video_small_shadow.png'))

def get_video_type_icon():
    return gtk.gdk.pixbuf_new_from_file(paths.share_dir('glade3/video24.png'))
    
_generic_photo_image = get_generic_photo_image()
_generic_photo_image_icon = get_generic_photo_image_icon()
    
def is_downloadable(file_extension):
    """
    Uses file extentsion to determines if the file could be downloaded or not.
    
    Returns True if yes, else False.
    """
    return file_extension in EXTENSIONS
    
def get_rpdfile(extension, name, display_name, path, size, 
                file_system_modification_time, 
                device_name, download_folder, volume):
                    
    if extension in VIDEO_EXTENSIONS:
        return Video(name, display_name, path, size,
                     file_system_modification_time, 
                     device_name, download_folder, volume)
    else:
        # assume it's a photo - no check for performance reasons (this will be
        # called many times)
        return Photo(name, display_name, path, size,
                     file_system_modification_time, 
                     device_name, download_folder, volume)


class RPDFile:
    """
    Base class for photo or video file, with metadata
    """

    def __init__(self, name, display_name, path, size, 
                 file_system_modification_time, device_name, download_folder,
                 volume):
                     
        self.thread_id = 99 # just a dummy value
        
        self.path = path

        self.name = name
        self.display_name = display_name

        self.full_file_name = os.path.join(path, name)
        
        self.size = size # type int
        
        self.modification_time = file_system_modification_time
        self.device_name = device_name
        
        self.download_folder = download_folder
        self.volume = volume
        
        self.metadata = None
        
        self.status = config.STATUS_NOT_DOWNLOADED
        self.problem = None # class Problem in problemnotifcation.py
                
        self.apply_generic_thumbnail()
        self._image_type()
        
    def _image_type(self):
        self.file_type = None
    
    def apply_generic_thumbnail(self):
        """Adds a generic thumbnail to the file.
        
        Expected to be implemented in derived classes.
        """
        self.generic_thumbnail = True
        self.thumbnail = None
        self.thumbnail_icon = None
    
    def date_time(self, alternative_if_date_missing=None):
        date = None
        if self.metadata:
            date = self.photometadata.date_time()
        if not date:
            if alternative_if_date_missing:
                date = alternative_if_date_missing
            else:
                date = datetime.datetime.fromtimestamp(self.modification_time)
        return date        


class Photo(RPDFile):
    
    title = _("photo")
    title_capitalized = _("Photo")
    
    type_icon = get_photo_type_icon()
    
    def _image_type(self):
        self.file_type = config.FILE_TYPE_PHOTO
    
    def apply_generic_thumbnail(self):
        """Adds a generic thumbnail to the file."""
        self.thumbnail = get_generic_photo_image_icon()
        self.thumbnail_icon = _generic_photo_image_icon
        self.generic_thumbnail = True
        
    def load_metadata(self):
        self.metadata = metadata.MetaData(self.full_file_name)
        self.metadata.read()

class Video(RPDFile):
    
    title = _("video")
    title_capitalized = _("Video")
    
    type_icon = get_video_type_icon()
    
    _generic_thumbnail_image = get_generic_video_image()
    _generic_thumbnail_image_icon = get_generic_video_image_icon()
    
    def _image_type(self):
        self.file_type = config.FILE_TYPE_VIDEO
    
    def apply_generic_thumbnail(self):
        """Adds a generic thumbnail to the file."""
        self.thumbnail = Video._generic_thumbnail_image
        self.thumbnail_icon = Video._generic_thumbnail_image_icon
        self.generic_thumbnail = True
    
    def load_metadata(self):    
        self.metadata = videometadata.VideoMetaData(self.full_file_name)
        
        

