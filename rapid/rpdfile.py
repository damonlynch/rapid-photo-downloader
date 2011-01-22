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
import common

_ = common.Configi18n._

import config

import metadata as photometadata
import thumbnail as tn

PHOTO_EXTENSIONS = photometadata.RAW_FILE_EXTENSIONS + \
                   photometadata.NON_RAW_IMAGE_FILE_EXTENSIONS
                   
VIDEO_EXTENSIONS = []

EXTENSIONS = PHOTO_EXTENSIONS


def is_downloadable(file_extension):
    """
    Uses file extentsion to determines if the file could be downloaded or not.
    
    Returns True if yes, else False.
    """
    return file_extension in EXTENSIONS
    
def get_rpdfile(extension, name, display_name, path, size, 
                file_system_modification_time, 
                device_name, download_folder, volume, scan_pid, file_id):
                    
    if extension in VIDEO_EXTENSIONS:
        return Video(name, display_name, path, size,
                     file_system_modification_time, 
                     device_name, download_folder, volume, scan_pid, file_id)
    else:
        # assume it's a photo - no check for performance reasons (this will be
        # called many times)
        return Photo(name, display_name, path, size,
                     file_system_modification_time, 
                     device_name, download_folder, volume, scan_pid, file_id)


class RPDFile:
    """
    Base class for photo or video file, with metadata
    """

    def __init__(self, name, display_name, path, size, 
                 file_system_modification_time, device_name, download_folder,
                 volume, scan_pid, file_id):
                     
        self.path = path

        self.name = name
        self.display_name = display_name

        self.full_file_name = os.path.join(path, name)
        
        self.size = size # type int
        
        self.modification_time = file_system_modification_time
        self.device_name = device_name
        
        self.download_folder = download_folder
        self.volume = volume
        
        self.status = config.STATUS_NOT_DOWNLOADED
        self.problem = None # class Problem in problemnotifcation.py
                
        self._assign_file_type()
        
        self.scan_pid = scan_pid
        self.file_id = file_id
        self.unique_id = str(scan_pid) + ":" + file_id
        
        
    def _assign_file_type(self):
        self.file_type = None
    
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
    
    def _assign_file_type(self):
        self.file_type = config.FILE_TYPE_PHOTO
    
            
class Video(RPDFile):
    
    title = _("video")
    title_capitalized = _("Video")
    
    def _assign_file_type(self):
        self.file_type = config.FILE_TYPE_VIDEO


