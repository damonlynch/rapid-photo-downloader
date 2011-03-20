#!/usr/bin/python
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

import paths

from PIL import Image
import cStringIO
import tempfile
import subprocess

import rpdfile

import rpdmultiprocessing as rpdmp
from utilities import image_to_pixbuf, pixbuf_to_image
import pyexiv2

from filmstrip import add_filmstrip

import logging
logger = multiprocessing.get_logger()


def get_stock_photo_image():
    length = min(gtk.gdk.screen_width(), gtk.gdk.screen_height())
    pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(paths.share_dir('glade3/photo.svg'), length, length)
    image = pixbuf_to_image(pixbuf)    
    return image
    
def get_stock_photo_image_icon():
    image = Image.open(paths.share_dir('glade3/photo66.png'))
    image = image.convert("RGBA")
    return image
    
def get_stock_video_image():
    length = min(gtk.gdk.screen_width(), gtk.gdk.screen_height())
    pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(paths.share_dir('glade3/video.svg'), length, length)
    image = pixbuf_to_image(pixbuf)    
    return image
        
def get_stock_video_image_icon():
    image = Image.open(paths.share_dir('glade3/video66.png'))
    image = image.convert("RGBA")
    return image
    
    
class PhotoIcons():
    stock_thumbnail_image_icon = get_stock_photo_image_icon()

class VideoIcons():
    stock_thumbnail_image_icon = get_stock_video_image_icon()

def upsize_pil(image, size):
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

def downsize_pil(image, box, fit=False):
    """Downsample the PIL image.
   image: Image -  an Image-object
   box: tuple(x, y) - the bounding box of the result image
   fix: boolean - crop the image to fill the box
   
   Code adpated from example by Christian Harms
   Source: http://united-coders.com/christian-harms/image-resizing-tips-every-coder-should-know
   """
    #preresize image with factor 2, 4, 8 and fast algorithm
    factor = 1
    logger.debug("Image size %sx%s", image.size[0], image.size[1])
    logger.debug("Box size %sx%s", box[0],box[1])
    while image.size[0]/factor > 2*box[0] and image.size[1]*2/factor > 2*box[1]:
        factor *=2
    if factor > 1:
        logger.debug("quick resize %sx%s", image.size[0]/factor, image.size[1]/factor)
        image.thumbnail((image.size[0]/factor, image.size[1]/factor), Image.NEAREST)
        logger.debug("did first thumbnail")
 
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
    logger.debug("about to actually downsize using image.thumbnail")
    image.thumbnail(box, Image.ANTIALIAS)
    logger.debug("it downsized")
    
class PicklablePIL:
    def __init__(self, image):
        self.size = image.size
        self.mode = image.mode
        self.image_data = image.tostring()
        
    def get_image(self):
        return Image.fromstring(self.mode, self.size, self.image_data)
        
    def get_pixbuf(self):
        return image_to_pixbuf(self.get_image())

def get_video_THM_file(fullFileName):
    """
    Checks to see if a thumbnail file (THM) is in the same directory as the 
    file. Expects a full path to be part of the file name.
    
    Returns the filename, including path, if found, else returns None.
    """
    
    f = None
    name, ext = os.path.splitext(fullFileName)
    for e in rpdfile.VIDEO_THUMBNAIL_EXTENSIONS:
        if os.path.exists(name + '.' + e):
            f = name + '.' + e
            break
        if os.path.exists(name + '.' + e.upper()):
            f = name + '.' + e.upper()
            break
        
    return f 

class Thumbnail:
    
    # file types from which to remove letterboxing (black bands in the thumbnail
    # previews)
    crop_thumbnails = ('CR2', 'DNG', 'RAF', 'ORF', 'PEF', 'ARW')
    
    def _ignore_embedded_160x120_thumbnail(self, max_size_needed, metadata):
        return max_size_needed is None or max_size_needed[0] > 160 or max_size_needed[1] > 120 or not metadata.exif_thumbnail.data
    
    def _get_thumbnail_data(self, metadata, max_size_needed):
        logger.debug("Getting thumbnail data %s", max_size_needed)
        if self._ignore_embedded_160x120_thumbnail(max_size_needed, metadata):
            logger.debug("Ignoring embedded preview")
            lowrez = False
            previews = metadata.previews
            if not previews:
                return (None, None)
            else:
                if max_size_needed:
                    for thumbnail in previews:
                        if thumbnail.dimensions[0] >= max_size_needed or thumbnail.dimensions[1] >= max_size_needed:
                            break
                else:
                    thumbnail = previews[-1]
        else:
            thumbnail = metadata.exif_thumbnail
            lowrez = True
        return (thumbnail.data, lowrez)
        
    def _process_thumbnail(self, image, size_reduced):
        if image.mode <> "RGBA":
            image = image.convert("RGBA")

        thumbnail = PicklablePIL(image)
        if size_reduced is not None:
            thumbnail_icon = image.copy()
            downsize_pil(thumbnail_icon, size_reduced, fit=False)                
            thumbnail_icon = PicklablePIL(thumbnail_icon)
        else:
            thumbnail_icon = None
            
        return (thumbnail, thumbnail_icon)
    
    def _get_photo_thumbnail(self, full_file_name, size_max, size_reduced):
        thumbnail = None
        thumbnail_icon = None
        name = os.path.basename(full_file_name)
        metadata = pyexiv2.metadata.ImageMetadata(full_file_name)
        try:
            logger.debug("Read photo metadata...")
            metadata.read()
        except:
            logger.warning("Could not read metadata from %s", full_file_name)
        else:
            logger.debug("...successfully read photo metadata")
            if metadata.mime_type == "image/jpeg" and self._ignore_embedded_160x120_thumbnail(size_max, metadata):
                try:
                    image = Image.open(full_file_name)
                    lowrez = False
                except:
                    logger.warning("Could not generate thumbnail for jpeg %s ", full_file_name)
                    image = None
            else:
                thumbnail_data, lowrez = self._get_thumbnail_data(metadata, max_size_needed=size_max)
                logger.debug("_get_thumbnail_data returned")
                if not isinstance(thumbnail_data, types.StringType):
                    image = None
                else:
                    td = cStringIO.StringIO(thumbnail_data)
                    logger.debug("got td")
                    try:
                        image = Image.open(td)
                    except:
                        logger.warning("Unreadable thumbnail for %s", full_file_name)
                        image = None
            logger.debug("opened image")
            if image:
                try:
                    orientation = metadata['Exif.Image.Orientation'].value
                except:
                    orientation = None                
                if lowrez:
                    # need to remove letterboxing / pillarboxing from some
                    # RAW thumbnails
                    if os.path.splitext(full_file_name)[1][1:].upper() in Thumbnail.crop_thumbnails:
                        image2 = image.crop((0, 8, 160, 112))
                        image2.load()
                        image = image2                    
                if size_max is not None and (image.size[0] > size_max[0] or image.size[1] > size_max[1]):
                    logger.debug("downsizing")
                    downsize_pil(image, size_max, fit=False)
                    logger.debug("downsized")
                if orientation == 8:
                    # rotate counter clockwise
                    image = image.rotate(90)
                elif orientation == 6:
                    # rotate clockwise
                    image = image.rotate(270)
                elif orientation == 3:
                    # rotate upside down
                    image = image.rotate(180)
                thumbnail, thumbnail_icon = self._process_thumbnail(image, size_reduced)

        logger.debug("...got thumbnail for %s", full_file_name)
        return (thumbnail, thumbnail_icon)
        
    def _get_video_thumbnail(self, full_file_name, size_max, size_reduced):
        thumbnail = None
        thumbnail_icon = None
        if size_max is None:
            size = 0
        else:
            size = max(size_max[0], size_max[1])
        image = None
        if size > 0 and size <= 160:
            thm = get_video_THM_file(full_file_name)
            if thm:
                try:
                    thumbnail = gtk.gdk.pixbuf_new_from_file(thm)
                except:
                    logger.warning("Could not open THM file for %s", full_file_name)
                thumbnail = add_filmstrip(thumbnail)
                image = pixbuf_to_image(thumbnail)
        
        if image is None:
            try:
                tmp_dir = tempfile.mkdtemp(prefix="rpd-tmp")
                thm = os.path.join(tmp_dir, 'thumbnail.jpg')
                subprocess.check_call(['ffmpegthumbnailer', '-i', full_file_name, '-t', '10', '-f', '-o', thm, '-s', str(size)])
                image = Image.open(thm)
                image.load()
                os.unlink(thm)
                os.rmdir(tmp_dir)
            except:
                image = None
                logger.error("Error generating thumbnail for %s", full_file_name)
        if image:
            thumbnail, thumbnail_icon = self._process_thumbnail(image, size_reduced)
        
        logger.debug("...got thumbnail for %s", full_file_name)    
        return (thumbnail, thumbnail_icon)
    
    def get_thumbnail(self, full_file_name, file_type, size_max=None, size_reduced=None):
        logger.debug("Getting thumbnail for %s...", full_file_name)
        if file_type == rpdfile.FILE_TYPE_PHOTO:
            logger.debug("file type is photo")
            return self._get_photo_thumbnail(full_file_name, size_max, size_reduced)
        else:
            return self._get_video_thumbnail(full_file_name, size_max, size_reduced)
                
                
class GetPreviewImage(multiprocessing.Process):
    def __init__(self, results_pipe):
        multiprocessing.Process.__init__(self)
        self.daemon = True
        self.results_pipe = results_pipe
        self.thumbnail_maker = Thumbnail()
        self.stock_photo_thumbnail_image = None
        self.stock_video_thumbnail_image = None        
        
    def get_stock_image(self, file_type):
        """
        Get stock image for file type scaled to the current size of the 
        """
        if file_type == rpdfile.FILE_TYPE_PHOTO:
            if self.stock_photo_thumbnail_image is None:
                self.stock_photo_thumbnail_image = PicklablePIL(get_stock_photo_image())
            return self.stock_photo_thumbnail_image
        else:
            if self.stock_video_thumbnail_image is None:
                self.stock_video_thumbnail_image = PicklablePIL(get_stock_video_image())
            return self.stock_video_thumbnail_image         
        
    def run(self):
        while True:
            unique_id, full_file_name, file_type, size_max = self.results_pipe.recv()
            full_size_preview, reduced_size_preview = self.thumbnail_maker.get_thumbnail(full_file_name, file_type, size_max=size_max, size_reduced=None)
            if full_size_preview is None:
                full_size_preview = self.get_stock_image(file_type)
            self.results_pipe.send((unique_id, full_size_preview, reduced_size_preview))
            


class GenerateThumbnails(multiprocessing.Process):
    def __init__(self, files, batch_size, results_pipe, terminate_queue, 
                 run_event):
        multiprocessing.Process.__init__(self)
        self.results_pipe = results_pipe
        self.terminate_queue = terminate_queue
        self.batch_size = batch_size
        self.files = files
        self.run_event = run_event
        self.results = []
        
        self.thumbnail_maker = Thumbnail()
        
        
    def run(self):
        counter = 0
        i = 0
        for f in self.files:
            
            # pause if instructed by the caller
            self.run_event.wait()
            
            if not self.terminate_queue.empty():
                x = self.terminate_queue.get()
                # terminate immediately
                logger.info("Terminating thumbnailing")
                return None
            
            
            thumbnail, thumbnail_icon = self.thumbnail_maker.get_thumbnail(
                                    f.full_file_name,
                                    f.file_type,
                                    (160, 120), (100,100))
            
            #~ logger.debug("Appending results for %s" %f.full_file_name)
            self.results.append((f.unique_id, thumbnail_icon, thumbnail))
            counter += 1
            if counter == self.batch_size:
                #~ logger.debug("Sending results....")
                self.results_pipe.send((rpdmp.CONN_PARTIAL, self.results))
                self.results = []
                counter = 0
            i += 1
            
        if counter > 0:
            # send any remaining results
            #~ logger.debug("Sending final results....")
            self.results_pipe.send((rpdmp.CONN_PARTIAL, self.results))
        self.results_pipe.send((rpdmp.CONN_COMPLETE, None))
        self.results_pipe.close()
        
