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
import os

import gtk
import numpy

import paths

import config
import common
import rpdmultiprocessing as rpdmp
import pyexiv2

import prototype
#~ from prototype import logger

def get_stock_photo_image():
    return gtk.gdk.pixbuf_new_from_file(paths.share_dir('glade3/photo.png'))
    
def get_stock_photo_image_icon():
    return gtk.gdk.pixbuf_new_from_file(paths.share_dir('glade3/photo_small_shadow.png'))
    
def get_photo_type_icon():
    return gtk.gdk.pixbuf_new_from_file(paths.share_dir('glade3/photo24.png'))
    
def get_stock_video_image():
    return gtk.gdk.pixbuf_new_from_file(paths.share_dir('glade3/video.png'))
    
def get_stock_video_image_icon():
    return gtk.gdk.pixbuf_new_from_file(paths.share_dir('glade3/video_small_shadow.png'))

def get_video_type_icon():
    return gtk.gdk.pixbuf_new_from_file(paths.share_dir('glade3/video24.png'))
    

    
class PhotoIcons():
    stock_thumbnail_image = get_stock_photo_image()
    stock_thumbnail_image_icon = get_stock_photo_image_icon()
    type_icon = get_photo_type_icon()
    
class VideoIcons():
    stock_thumbnail_image = get_stock_video_image()
    stock_thumbnail_image_icon = get_stock_video_image_icon()
    type_icon = get_video_type_icon()

    
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


class PhotoThumbnail_v2:
    def __init__(self):
        pass
        
    def get_thumbnail_data(self, metadata, high_quality, max_size_needed=0):
        
        if high_quality:

            previews = metadata.previews
            if not previews:
                return None, None
            else:
                if max_size_needed:
                    for thumbnail in previews:
                        if thumbnail.dimensions[0] >= max_size_needed or thumbnail.dimensions[1] >= max_size_needed:
                            break
                else:
                    thumbnail = self.previews[-1]
                
        else:
            thumbnail = metadata.exif_thumbnail
        
        return thumbnail.data
            
    def get_thumbnail(self, full_file_name, size):
        thumbnail = None
        thumbnail_icon = None        
        metadata = pyexiv2.metadata.ImageMetadata(full_file_name)
        try:
            metadata.read()
        except:
            prototype.logger.warning("Could not read metadata from %s" % full_file_name)
        else:
            thumbnail_data = self.get_thumbnail_data(metadata, high_quality=False, max_size_needed=size)
            if isinstance(thumbnail_data, types.StringType):
                try:
                    orientation = metadata['Exif.Image.Orientation'].value
                except:
                    orientation = None
                try:
                    pbloader = gtk.gdk.PixbufLoader()
                    pbloader.write(thumbnail_data)
                    pbloader.close()
                except:
                    prototype.logger.warning("bad thumbnail for %s" % full_file_name)
                else:
                    # Get the resulting pixbuf and build an image to be displayed
                    pixbuf = pbloader.get_pixbuf()
                    

                    
                
                    if orientation == 8:
                        pixbuf = pixbuf.rotate_simple(gtk.gdk.PIXBUF_ROTATE_COUNTERCLOCKWISE)
                    elif orientation == 6:
                        pixbuf = pixbuf.rotate_simple(gtk.gdk.PIXBUF_ROTATE_CLOCKWISE)
                    elif orientation == 3:
                        pixbuf = pixbuf.rotate_simple(gtk.gdk.PIXBUF_ROTATE_UPSIDEDOWN)
                    thumbnail_icon = PicklablePixBuf(
                                            common.scale2pixbuf(60, 36, pixbuf))
                    if pixbuf.get_height() > size or pixbuf.get_width() > size:
                        pixbuf = common.scale2pixbuf(size, size, pixbuf)
                    thumbnail = PicklablePixBuf(pixbuf)
                    
                    
                    p = thumbnail.get_pixbuf()
                    name = os.path.split(full_file_name)[1]
                    path = "%s.jpg" % os.path.join('/home/damon/tmp/rpd', name)
                    p.save(path, 'jpeg')

        return (thumbnail, thumbnail_icon)

class PhotoThumbnail_v1:
    def __init__(self):
        pass
        
    def get_thumbnail_data(self, metadata, max_size_needed=0):

        previews = metadata.previews
        if not previews:
            return None, None
        else:
            if max_size_needed:
                for thumbnail in previews:
                    if thumbnail.dimensions[0] >= max_size_needed or thumbnail.dimensions[1] >= max_size_needed:
                        break
            else:
                thumbnail = self.previews[-1]
                    
            return thumbnail.data
            
    def get_thumbnail(self, full_file_name, size):
        thumbnail = None
        thumbnail_icon = None        
        metadata = pyexiv2.Image(full_file_name)
        try:
            metadata.readMetadata()
        except:
            logger.warning("Could not read metadata from %s" % full_file_name)
        else:
            thumbnail_type, thumbnail_data = metadata.getThumbnailData()
            if isinstance(thumbnail_data, types.StringType):
                orientation = metadata['Exif.Image.Orientation']
                pbloader = gtk.gdk.PixbufLoader()
                pbloader.write(thumbnail_data)
                pbloader.close()
                # Get the resulting pixbuf and build an image to be displayed
                pixbuf = pbloader.get_pixbuf()
                if orientation == 8:
                    pixbuf = pixbuf.rotate_simple(gtk.gdk.PIXBUF_ROTATE_COUNTERCLOCKWISE)
                elif orientation == 6:
                    pixbuf = pixbuf.rotate_simple(gtk.gdk.PIXBUF_ROTATE_CLOCKWISE)
                elif orientation == 3:
                    pixbuf = pixbuf.rotate_simple(gtk.gdk.PIXBUF_ROTATE_UPSIDEDOWN)
                thumbnail_icon = PicklablePixBuf(
                                        common.scale2pixbuf(60, 36, pixbuf))                
                thumbnail = PicklablePixBuf(pixbuf)

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
        
        if 'version_info' in dir(pyexiv2):
            self.thumbnail_maker = PhotoThumbnail_v2()
        else:
            self.thumbnail_maker = PhotoThumbnail_v1()
        
        
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
            
            self.results.append((f.unique_id, thumbnail_icon, thumbnail))
            #~ self.results.append((f.unique_id, thumbnail_icon))
            self.counter += 1
            if self.counter == self.batch_size:
                self.results_pipe.send((rpdmp.CONN_PARTIAL, self.results))
                self.results = []
                self.counter = 0
            
        if self.counter > 0:
            # send any remaining results
            self.results_pipe.send((rpdmp.CONN_PARTIAL, self.results))
        self.results_pipe.send((rpdmp.CONN_COMPLETE, None))
        self.results_pipe.close()
        
#~ if __name__ == '__main__':
