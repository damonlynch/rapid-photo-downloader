#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2007 Damon Lynch <damonlynch@gmail.com>

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

import config
import common
import metadata
import videometadata

import operator

def getDefaultPhotoLocation():
    for default in config.DEFAULT_PHOTO_LOCATIONS:
        path = common.getFullPath(default)
        if os.path.isdir(path):
            return path
    return common.getFullPath('')
    
def is_DCIM_Media(path):
    """ Returns true if directory specifies some media with photos on it   """
    
    if os.path.isdir(os.path.join(path, "DCIM")):
        # is very likely a memory card, or something like that!
       return True
    else:
        return False

    
def isBackupMedia(path, identifier, writeable=True):
    """  Test to see if path is used as a backup medium for storing images
    
    If writeable is True, the directory must be writeable by the user """
    suitable = False
    if os.path.isdir(os.path.join(path, identifier)):
        if writeable:
            suitable = os.access(os.path.join(path, identifier), os.W_OK)
        else:
            suitable = True
    return suitable
    
def isImage(fileName):
    ext = os.path.splitext(fileName)[1].lower()[1:]
    return (ext in metadata.RAW_FILE_EXTENSIONS) or (ext in metadata.NON_RAW_IMAGE_FILE_EXTENSIONS)
    
def isVideo(fileName):
    ext = os.path.splitext(fileName)[1].lower()[1:]
    return (ext in videometadata.VIDEO_FILE_EXTENSIONS)
    
def getVideoThumbnailFile(fullFileName):
    """
    Checks to see if a thumbnail file is in the same directory as the 
    file. Expects a full path to be part of the file name.
    
    Returns the filename, including path, if found, else returns None.
    """
    
    f = None
    name, ext = os.path.splitext(fullFileName)
    for e in videometadata.VIDEO_THUMBNAIL_FILE_EXTENSIONS:
        if os.path.exists(name + '.' + e):
            f = name + '.' + e
            break
        if os.path.exists(name + '.' + e.upper()):
            f = name + '.' + e.upper()
            break
        
    return f
    

class Media:
    """ Generic class for media holding images and videos """
    def __init__(self, path, volume = None):
        """
        volume is a gnomevfs or gio volume: see class Volume in rapid.py
        """
        
        self.path = path
        self.volume = volume
            

    def prettyName(self,  limit=config.MAX_LENGTH_DEVICE_NAME):
        """ 
        Returns a name for the media, useful for display.
        
        If the media is from a gnomevfs volume, returns the gnome name.
        
        Else. returns the last part of the mount point after stripping out 
        underscores.
        """

        if self.volume:
            return self.volume.get_name(limit)
        else:
            name = os.path.split(self.path)[1]
            name = name.replace('_', ' ')
            v = name
            if limit:
                if len(v) > limit:
                    v = v[:limit] + '...'
            return v
            
    def getPath(self):
        return self.path
        
    
class CardMedia(Media):
    """Compact Flash cards, hard drives, etc."""
    def __init__(self, path, volume = None,  doNotScan=True):
        """
        volume is a gnomevfs or gio volume, see class Volume in rapid.py
        """
        Media.__init__(self, path, volume)

        
    def setMedia(self, imagesAndVideos, fileSizeSum, noFiles):
        self.imagesAndVideos = imagesAndVideos
        self.fileSizeSum = fileSizeSum
        self.noFiles = noFiles
        
    def numberOfImagesAndVideos(self):
        return self.noFiles
        
    def sizeOfImagesAndVideos(self, humanReadable = True):
        if humanReadable:
            return common.formatSizeForUser(self.fileSizeSum)
        else:
            return self.fileSizeSum
    
    def _firstFile(self, isCorrectFile):
        if self.imagesAndVideos:
            for i in range(len(self.imagesAndVideos)):
                if isImage(self.imagesAndVideos[i]):
                    return self.imagesAndVideos[i]
        else:
            return None
        
    def firstImage(self):
        return self._firstFile(isImage)
    
    def firstVideo(self):
        return self._firstFile(isVideo)
        
