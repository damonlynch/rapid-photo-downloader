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

import operator

def getDefaultPhotoLocation():
    for default in config.DEFAULT_PHOTO_LOCATIONS:
        path = common.getFullPath(default)
        if os.path.isdir(path):
            return path
    return common.getFullPath('')
    
def isImageMedia(path):
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
    return (ext in config.RAW_FILE_EXTENSIONS) or (ext in config.NON_RAW_IMAGE_FILE_EXTENSIONS)

class Media:
    """ Generic class for media holding images """
    def __init__(self, path, volume = None):
        """
        volume is a gnomevfs volume
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
    """Compact Flash cards, etc."""
    def __init__(self, path, volume = None,  doNotScan=True):
        """
        volume is a gnomevfs volume
        """
        Media.__init__(self, path, volume)
        if not doNotScan:
            self.scanMedia()

    def scanMedia(self):
        """ creates a list of images on a path, recursively scanning
        
        images are sorted by modification time"""
        
        self.images = []
        self.imageSizeSum = 0
        for root, dirs, files in os.walk(self.path):
            for name in files:
                if isImage(name):
                    image = os.path.join(root, name)
                    size = os.path.getsize(image)
                    modificationTime = os.path.getmtime(image)
                    self.images.append((name, root, size,  modificationTime),)
                    self.imageSizeSum += size
        self.images.sort(key=operator.itemgetter(3))
        self.noImages = len(self.images)
        
    def setMedia(self,  images,  imageSizeSum,  noImages):
        self.images = images
        self.imageSizeSum = imageSizeSum
        self.noImages = noImages
        
    def numberOfImages(self):
        return self.noImages
        
    def sizeOfImages(self, humanReadable = True):
        if humanReadable:
            return common.formatSizeForUser(self.imageSizeSum)
        else:
            return self.imageSizeSum
    
    def firstImage(self):
        if self.images:
            return self.images[0]
        else:
            return None
    
        
def scanForImageMedia(path):
    """ returns a list of paths that contain images on media produced by a digital camera """
    
    media = []
    for i in os.listdir(path):
        p = os.path.join(path, i)
        if os.path.isdir(p):
            if isImageMedia(p):
                media.append(p)
    return media
    
def scanForBackupMedia(path, identifier):
    """ returns a list of paths that contains backed up images  """
    
    media = []
    for i in os.listdir(path):
        p = os.path.join(path, i)
        if os.path.isdir(p):
            if isBackupMedia(p, identifier):
                media.append(os.path.join(p, identifier))
    return media

    
if __name__ == '__main__':
    print "Card media:"
    for m in scanForImageMedia('/media'):
        media = CardMedia(m)
        print media.prettyName()
        print media.numberOfImages()
        print media.sizeOfImages()
        
    print "\nBackup media:"
    for m in scanForBackupMedia('/media',  'photos'):
        print m

    print "\nDefault download folder: ",  getDefaultPhotoLocation()
