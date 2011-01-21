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

import multiprocessing
import types

import gtk
import numpy

import paths

import config
import common
import rpdmultiprocessing as rpdmp
import metadata as photometadata

import logging
logger = multiprocessing.log_to_stderr()
logger.setLevel(logging.INFO)

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
    

    
class PhotoIcons():
    generic_thumbnail_image = get_generic_photo_image()
    generic_thumbnail_image_icon = get_generic_photo_image_icon()
    type_icon = get_photo_type_icon()



    #~ type_icon = thumbnail.get_video_type_icon()
    #~ 
    #~ _generic_thumbnail_image = thumbnail.get_generic_video_image()
    #~ _generic_thumbnail_image_icon = thumbnail.get_generic_video_image_icon()
    
class PicklablePixBuf:
    """
    A convenience class to allow Pixbufs to be passed between processes.
    
    Pixbufs cannot be pickled, which means they cannot be exchanged between
    processes. This class converts them into a numeric array that can be
    pickled.
    
    Source for background information:
    http://lisas.de/~alex/?p=46
    https://bugzilla.gnome.org/show_bug.cgi?id=309469
    """
    def __init__(self, pixbuf):
        """Pixbuf to be pickled"""
        self.array = pixbuf.get_pixels_array()
        self.colorspace = pixbuf.get_colorspace()
        self.bits_per_sample = pixbuf.get_bits_per_sample()
        
    def get_pixbuf(self):
        """Return the pixbuf"""
        return gtk.gdk.pixbuf_new_from_array(self.array, 
                                             self.colorspace,
                                             self.bits_per_sample)


class PhotoThumbnail:
    def __init__(self):
        pass
    def get_thumbnail(self, full_file_name, size):
        thumbnail = None
        thumbnail_icon = None        
        metadata = photometadata.MetaData(full_file_name)
        try:
            metadata.read()
        except:
            logger.warning("Could not read metadata from %s" % full_file_name)
        else:
            thumbnail = metadata.getThumbnailData(size)
            if isinstance(thumbnail, types.StringType):
                orientation = metadata.orientation(missing=None)
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
                
                thumbnail = PicklablePixBuf(pixbuf)
                thumbnail_icon = PicklablePixBuf(
                                        common.scale2pixbuf(60, 36, pixbuf))
                
        del(metadata)
        return (thumbnail, thumbnail_icon)

                
class GenerateThumbnails(multiprocessing.Process):
    def __init__(self, files, batch_size, results_pipe, terminate_queue, 
                 run_event):
        multiprocessing.Process.__init__(self)
        self.results_pipe = results_pipe
        self.terminate_queue = terminate_queue
        self.batch_size = batch_size
        self.files = files
        self.run_event = run_event
        self.counter = 0
        self.results = []
        
        self.thumbnail_maker = PhotoThumbnail()
        
    def run(self):
        for f in self.files:
            
            # pause if instructed by the caller
            self.run_event.wait()
            
            if not self.terminate_queue.empty():
                x = self.terminate_queue.get()
                # terminate immediately
                logger.info("Terminating thumbnailing")
                return None
            
            thumbnail, thumbnail_icon = self.thumbnail_maker.get_thumbnail(f.full_file_name, config.max_thumbnail_size)
            
            self.results.append((f.unique_id, thumbnail, thumbnail_icon))
            self.counter += 1
            if self.counter == self.batch_size:
                self.results_pipe.send((rpdmp.CONN_PARTIAL, self.results))
                self.results = []
                self.counter = 0                
            
        if self.counter > 0:
            # send any remaining results
            self.results_pipe.send((rpdmp.CONN_PARTIAL, self.results))
        self.results_pipe.send((rpdmp.CONN_COMPLETE, None))            
        
