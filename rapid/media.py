#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2007, 2008, 2009, 2010 Damon Lynch <damonlynch@gmail.com>

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
import sys
import types
import datetime 
import subprocess

import config
from config import max_thumbnail_size
from config import STATUS_NOT_DOWNLOADED, \
                    STATUS_DOWNLOAD_PENDING, \
                    STATUS_CANNOT_DOWNLOAD


import common
import metadata
import videometadata

from common import Configi18n
global _
_ = Configi18n._

import operator
import gtk

def _getDefaultLocationLegacy(options, ignore_missing_dir=False):
    if ignore_missing_dir:
        return common.getFullPath(options[0])
    for default in options:
        path = common.getFullPath(default)
        if os.path.isdir(path):
            return path
    return common.getFullPath('')
    
def _getDefaultLocationXDG(dir_type):
    proc = subprocess.Popen(['xdg-user-dir', dir_type], stdout=subprocess.PIPE)
    output = proc.communicate()[0].strip()
    return output

def getDefaultPhotoLocation(ignore_missing_dir=False):
    try:
        return _getDefaultLocationXDG('PICTURES')
    except:
        return _getDefaultLocationLegacy(config.DEFAULT_PHOTO_LOCATIONS, ignore_missing_dir)
    
def getDefaultVideoLocation(ignore_missing_dir=False):
    try:
        return _getDefaultLocationXDG('VIDEOS')
    except:    
        return _getDefaultLocationLegacy(config.DEFAULT_VIDEO_LOCATIONS, ignore_missing_dir)
        
def getDefaultBackupPhotoIdentifier():
    return os.path.split(getDefaultPhotoLocation(ignore_missing_dir = True))[1]

def getDefaultBackupVideoIdentifier():
    return os.path.split(getDefaultVideoLocation(ignore_missing_dir = True))[1]
    
def is_DCIM_Media(path):
    """ Returns true if directory specifies some media with photos on it   """
    
    if os.path.isdir(os.path.join(path, "DCIM")):
        # is very likely a memory card, or something like that!
       return True
    else:
        return False

    
def isBackupMedia(path, identifiers, writeable=True):
    """  Test to see if path is used as a backup medium for storing photos or videos
    
    Identifiers is expected to be a list of folder names to check to see
    if the path is a backup path. Only one of them needs to be present
    for the path to be considered a backup medium.
    
    If writeable is True, the directory must be writeable by the user """
    suitable = False
    
    for identifier in identifiers:
        if os.path.isdir(os.path.join(path, identifier)):
            if writeable:
                suitable = os.access(os.path.join(path, identifier), os.W_OK)
            else:
                suitable = True
        if suitable:
            return True
    return False
    
def isImage(fileName):
    ext = os.path.splitext(fileName)[1].lower()[1:]
    return (ext in metadata.RAW_FILE_EXTENSIONS) or (ext in metadata.NON_RAW_IMAGE_FILE_EXTENSIONS)
    
def isVideo(fileName):
    ext = os.path.splitext(fileName)[1].lower()[1:]
    return (ext in videometadata.VIDEO_FILE_EXTENSIONS)
    

class MediaFile:
    """
    A photo or video file, with metadata
    """
    
    def __init__(self, thread_id, name, path, size, fileSystemModificationTime, deviceName, downloadFolder, volume, isPhoto = True):
        self.thread_id = thread_id
        self.path = path
        self.name = name
        self.fullFileName = os.path.join(path, name)
        self.size = size # type int
        self.modificationTime = fileSystemModificationTime
        self.deviceName = deviceName
        self.downloadFolder = downloadFolder
        self.volume = volume
        
        self.jobcode = ''
        
        # a reference into the SelectionTreeView's liststore
        self.treerowref = None
        
        # generated values
        self.downloadSubfolder = ''
        self.downloadPath = ''
        self.downloadName = ''
        self.downloadFullFileName = ''

        self.isImage = isPhoto
        self.isVideo = not self.isImage
        if isPhoto:
            self.displayName = _("photo")
            self.displayNameCap = _("Photo")
        else:
            self.displayName = _("video")
            self.displayNameCap = _("Video")
        
        
        self.metadata = None
        self.thumbnail = None
        self.genericThumbnail = False
        self.sampleName = ''
        self.sampleSubfolder = ''
        self.samplePath = ''
        
        # whether the sample genereated name, subfolder and path need to be refreshed in a preview
        self.sampleStale = False

        self.status = STATUS_NOT_DOWNLOADED
        self.problem = None # class Problem in problemnotifcation.py
        
    def loadMetadata(self):
        """
        Attempt to load the metadata for the photo or video
        
        Raises errors if unable to be loaded
        """
        if not self.metadata:
            if self.isImage:
                self.metadata = metadata.MetaData(self.fullFileName)
                self.metadata.read()
            else:
                self.metadata = videometadata.VideoMetaData(self.fullFileName)

                
    def dateTime(self, alternative_if_date_missing=None):
        date = None
        if self.metadata:
            date = self.metadata.dateTime()
        if not date:
            if alternative_if_date_missing:
                date = alternative_if_date_missing
            else:
                date = datetime.datetime.fromtimestamp(self.modificationTime)
        return date
            
        
    def generateThumbnail(self, tempWorkingDir):
        """
        Attempts to generate or extract a thumnail and its orientation for the photo or video
        """
        if self.metadata is None:
            sys.stderr.write("metadata should not be empty!")
        else:
            if self.isImage:
                try:
                    thumbnail = self.metadata.getThumbnailData(max_thumbnail_size)
                    if not isinstance(thumbnail, types.StringType):
                        self.thumbnail = None
                    else:
                        orientation = self.metadata.orientation(missing=None)
                        pbloader = gtk.gdk.PixbufLoader()
                        pbloader.write(thumbnail)
                        pbloader.close()
                        # Get the resulting pixbuf and build an image to be displayed
                        pixbuf = pbloader.get_pixbuf()
                        if orientation == 8:
                            pixbuf = pixbuf.rotate_simple(gtk.gdk.PIXBUF_ROTATE_COUNTERCLOCKWISE)
                        elif orientation == 6:
                            pixbuf = pixbuf.rotate_simple(gtk.gdk.PIXBUF_ROTATE_CLOCKWISE)
                        elif orientation == 3:
                            pixbuf = pixbuf.rotate_simple(gtk.gdk.PIXBUF_ROTATE_UPSIDEDOWN)
                        
                        self.thumbnail = pixbuf
                except:
                    pass
            else:
                # get thumbnail of video
                # it may need to be generated
                self.thumbnail = self.metadata.getThumbnailData(max_thumbnail_size, tempWorkingDir)
        if self.thumbnail:
            # scale to size
            self.thumbnail = common.scale2pixbuf(max_thumbnail_size, max_thumbnail_size, self.thumbnail)

    

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
    def __init__(self, path, volume = None):
        """
        volume is a gnomevfs or gio volume, see class Volume in rapid.py
        """
        Media.__init__(self, path, volume)

        
    def setMedia(self, imagesAndVideos, fileSizeSum, noFiles):
        self.imagesAndVideos = imagesAndVideos # class MediaFile
        self.fileSizeSum = fileSizeSum
        self.noFiles = noFiles
        
    def numberOfImagesAndVideos(self):
        return self.noFiles
        
    def sizeOfImagesAndVideos(self, humanReadable = True):
        if humanReadable:
            return common.formatSizeForUser(self.fileSizeSum)
        else:
            return self.fileSizeSum
            
    def sizeAndNumberDownloadPending(self):
        """
        Returns how many files have their status set to download pending, and their size
        """
        v = s = 0
        fileIndex = []
        for i in range(len(self.imagesAndVideos)):
            mediaFile = self.imagesAndVideos[i][0]
            if mediaFile.status == STATUS_DOWNLOAD_PENDING:
                v += 1
                s += mediaFile.size
                fileIndex.append(i)
        return (v, s, fileIndex)
        
    def numberOfFilesNotCannotDownload(self):
        """
        Returns how many files whose status is not cannot download
        """
        v = 0
        for i in range(len(self.imagesAndVideos)):
            mediaFile = self.imagesAndVideos[i][0]
            if mediaFile.status <> STATUS_CANNOT_DOWNLOAD:
                v += 1
                
        return v
        
    def downloadPending(self):
        """
        Returns true if there a mediaFile with status download pending on the device.
        Inefficient. Not currently used.
        """
        for i in range(len(self.imagesAndVideos)):
            mediaFile = self.imagesAndVideos[i][0]
            if mediaFile.status == config.STATUS_DOWNLOAD_PENDING:
                return True
        return False
    
    def _firstFile(self, isImage):
        if self.imagesAndVideos:
            for i in range(len(self.imagesAndVideos)):
                if self.imagesAndVideos[i][0].isImage == isImage:
                    return self.imagesAndVideos[i][0]
        else:
            return None
        
    def firstImage(self):
        return self._firstFile(True)
    
    def firstVideo(self):
        return self._firstFile(False)
        
