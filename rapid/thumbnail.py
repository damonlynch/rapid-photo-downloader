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

from PIL import Image
import cStringIO

import config
import common
import rpdmultiprocessing as rpdmp
import dropshadow
import pyexiv2

import logging
logger = multiprocessing.get_logger()
logger.setLevel(logging.INFO)

def get_stock_photo_image():
    return Image.open(paths.share_dir('glade3/photo.png'))
    #~ return gtk.gdk.pixbuf_new_from_file(paths.share_dir('glade3/photo.png'))
    
def get_stock_photo_image_icon():
    return gtk.gdk.pixbuf_new_from_file(paths.share_dir('glade3/photo_small_shadow.png'))
    
def get_photo_type_icon():
    return gtk.gdk.pixbuf_new_from_file(paths.share_dir('glade3/photo24.png'))
    
def get_stock_video_image():
    return Image.open(paths.share_dir('glade3/video.png'))
    #~ return gtk.gdk.pixbuf_new_from_file(paths.share_dir('glade3/video.png'))
    
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


def upsize(image, size):
    width_max = size[0]
    height_max = size[1]
    width_orig = float(image.size[0])
    height_orig = float(image.size[1])
    if (width_orig / width_max) > (height_orig / height_max):
        height = int((height_orig / width_orig) * width_max)
        width = width_max
    else:
        width = int((width_orig / height_orig) * height_max)
        height=height_max
        
    return image.resize((width, height), Image.ANTIALIAS)

def downsize(image, box, fit):
    """Downsample the PIL image.
   image: Image -  an Image-object
   box: tuple(x, y) - the bounding box of the result image
   fix: boolean - crop the image to fill the box
   
   Code from Christian Harms
   Source: http://united-coders.com/christian-harms/image-resizing-tips-every-coder-should-know
   """
    #preresize image with factor 2, 4, 8 and fast algorithm
    factor = 1
    while image.size[0]/factor > 2*box[0] and image.size[1]*2/factor > 2*box[1]:
        factor *=2
    if factor > 1:
        image.thumbnail((image.size[0]/factor, image.size[1]/factor), Image.NEAREST)
 
    #calculate the cropping box and get the cropped part
    if fit:
        x1 = y1 = 0
        x2, y2 = image.size
        wRatio = 1.0 * x2/box[0]
        hRatio = 1.0 * y2/box[1]
        if hRatio > wRatio:
            y1 = y2/2-box[1]*wRatio/2
            y2 = y2/2+box[1]*wRatio/2
        else:
            x1 = x2/2-box[0]*hRatio/2
            x2 = x2/2+box[0]*hRatio/2
        image = image.crop((x1,y1,x2,y2))
 
    #Resize the image with best quality algorithm ANTI-ALIAS
    image.thumbnail(box, Image.ANTIALIAS)
 
    
class PicklablePIL:
    def __init__(self, image):
        self.size = image.size
        self.mode = image.mode
        self.image_data = image.tostring()
        
    def get_image(self):
        return Image.fromstring(self.mode, self.size, self.image_data)
        
    def get_pixbuf(self):
        return dropshadow.image_to_pixbuf(self.get_image())
    
class PicklablePixBuf:
    """
    A convenience class to allow Pixbufs to be passed between processes.
    
    THIS DOES NOT SEEM TO WORK! IMAGES BECOME CORRUPTED AND THERE ARE MEMORY LEAKS
    
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
        self.md5 = hashlib.md5(self.array).hexdigest()
        
    def get_pixbuf(self):
        """Return the pixbuf"""
        assert self.md5 == hashlib.md5(self.array).hexdigest()

        return gtk.gdk.pixbuf_new_from_array(self.array, 
                                             self.colorspace,
                                             self.bits_per_sample)


class PhotoThumbnail_v3:
    
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
        
    def get_thumbnail(self, full_file_name, size, quality):
        thumbnail = None
        thumbnail_icon = None        
        metadata = pyexiv2.metadata.ImageMetadata(full_file_name)
        try:
            metadata.read()
        except:
            logger.warning("Could not read metadata from %s" % full_file_name)
        else:
            thumbnail_data = self.get_thumbnail_data(metadata, high_quality=quality, max_size_needed=size)
            if isinstance(thumbnail_data, types.StringType):
                try:
                    orientation = metadata['Exif.Image.Orientation'].value
                except:
                    orientation = None
                   
                td = cStringIO.StringIO(thumbnail_data)
                try:
                    image = Image.open(td)
                except:
                    logger.warning("Unreadable thumbnail for %s" % full_file_name)
                else:
                    downsize(image, (size, size), False)
                    if orientation == 8:
                        # rotate counter clockwise
                        image = image.rotate(90)
                    elif orientation == 6:
                        # rotate clockwise
                        image = image.rotate(270)
                    elif orientation == 3:
                        # rotate upside down
                        image = image.rotate(180)                 
                    if image.mode == "RGB":
                        image = image.convert("RGBA")                
                    thumbnail = PicklablePIL(image)
                    thumbnail_icon = image.copy()
                    downsize(thumbnail_icon, (60, 36), False)                
                    thumbnail_icon = PicklablePIL(thumbnail_icon)
        return (thumbnail, thumbnail_icon)        
                
class PhotoThumbnail_v1:
    """
    needs to be converted to PIL
    """
    def __init__(self):
        pass
        
            
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
    def __init__(self, files, quality, batch_size, results_pipe, terminate_queue, 
                 run_event):
        multiprocessing.Process.__init__(self)
        self.results_pipe = results_pipe
        self.terminate_queue = terminate_queue
        self.batch_size = batch_size
        self.files = files
        self.quality = quality
        self.run_event = run_event
        self.counter = 0
        self.results = []
        
        if 'version_info' in dir(pyexiv2):
            self.thumbnail_maker = PhotoThumbnail_v3()
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
            
            
            thumbnail, thumbnail_icon = self.thumbnail_maker.get_thumbnail(f.full_file_name, config.max_thumbnail_size, self.quality)
            
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
