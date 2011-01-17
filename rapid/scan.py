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
import gio
import multiprocessing

import media
import paths
import gtk

def getGenericPhotoImage():
    return gtk.gdk.pixbuf_new_from_file(paths.share_dir('glade3/photo.png'))
    
def getGenericVideoImage():
    return gtk.gdk.pixbuf_new_from_file(paths.share_dir('glade3/video.png'))

photoThumbnail = getGenericPhotoImage()
videoThumbnail = getGenericVideoImage()

def addGenericThumbnail(mediaFile):
    """
    Adds a generic thumbnail to the mediafile, which
    can be very useful when previews are disabled
    """
    mediaFile.genericThumbnail = True
    if mediaFile.isImage:
        mediaFile.thumbnail = photoThumbnail
    else:
        mediaFile.thumbnail = videoThumbnail 

# python whitespace is significant - don't remove the leading whitespace on
# the second line

file_attributes = "standard::name,standard::display-name,\
standard::type,standard::size,time::modified,access::can-read"

CONN_PARTIAL = 0
CONN_COMPLETE = 1

class Scan(multiprocessing.Process):
    """
    Scans the given path for files of the specified type
    """
    
    def __init__(self, path, is_downloadable, batch_size, results_pipe, terminate_queue, run_event):
        multiprocessing.Process.__init__(self)
        self.path = path
        self.results_pipe = results_pipe
        self.terminate_queue = terminate_queue
        self.run_event = run_event
        self.is_downloadable = is_downloadable
        self.batch_size = batch_size
        self.counter = 0
        self.files = []


    def _gio_scan(self, path, file_size_sum):
        """recursive function to scan a directory and its subdirectories
        for photos and possibly videos"""
        
        children = path.enumerate_children(file_attributes)
        
        for child in children:
            
            # pause if instructed by the caller
            self.run_event.wait()
            
            if not self.terminate_queue.empty():
                x = self.terminate_queue.get()
                # terminate immediately
                print "terminating..."
                self.files = []
                return None

            # only collect files and scan in directories we can actually read
            # cannot assume that users will download only from memory cards
            
            if child.get_attribute_boolean(gio.FILE_ATTRIBUTE_ACCESS_CAN_READ):
                file_type = child.get_file_type()
                name = child.get_name()
                if file_type == gio.FILE_TYPE_DIRECTORY:
                    file_size_sum = self._gio_scan(path.get_child(name), file_size_sum)
                    if file_size_sum is None:
                        return None

                elif file_type == gio.FILE_TYPE_REGULAR:
                    ext = os.path.splitext(name)[1].lower()[1:]
                    
                    if self.is_downloadable(ext):
                        
                        self.counter += 1
                        display_name = child.get_display_name()
                        size = child.get_size()
                        modification_time = child.get_modification_time()
                        
                        media_file = self.create_media_file(name, path.get_path(), display_name, size, modification_time)
                        self.files.append(media_file)
                        
                        if self.counter == self.batch_size:
                            # send batch of results
                            self.results_pipe.send((CONN_PARTIAL, self.files))
                            #~ logger.info('sent')
                            self.files = []
                            self.counter = 0
                        
                        file_size_sum += size

        return file_size_sum
        

    def run(self):
        
        source = gio.File(self.path)
        size = self._gio_scan(source, 0)
        if size is not None:
            if self.counter > 0:
                # send any remaining results
                self.results_pipe.send((CONN_PARTIAL, self.files))
            self.results_pipe.send((CONN_COMPLETE, size))
            
    def create_media_file(self, name, path, display_name, size, modification_time):
        device = 'foo'
        download_folder = 'foo'
        volume = 'foo'
        is_image = True  
        media_file = media.MediaFile(0, name, path, size, modification_time, device, download_folder, volume, is_image)
        addGenericThumbnail(media_file)
        return media_file

      
        

