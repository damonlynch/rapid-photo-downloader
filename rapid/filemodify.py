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

import os.path, fractions
import subprocess
import multiprocessing
import logging
logger = multiprocessing.get_logger()

import rpdmultiprocessing as rpdmp
import rpdfile
import metadataxmp as mxmp
import subfolderfile

WRITE_XMP_INPLACE = rpdfile.NON_RAW_IMAGE_EXTENSIONS + ['dng']

def lossless_rotate(jpeg):
    """using exiftran, performs a lossless, inplace translation of a jpeg, preserving time stamps"""
    try:
        logger.debug("Auto rotating %s", jpeg)
        proc = subprocess.Popen(['exiftran', '-a', '-i', '-p', jpeg], stdout=subprocess.PIPE)
        v = proc.communicate()[0].strip()
    except OSError:
        v = None
    return v
    
class FileModify(multiprocessing.Process):
    def __init__(self, auto_rotate_jpeg, focal_length, results_pipe, terminate_queue, 
                 run_event):
        multiprocessing.Process.__init__(self)
        self.results_pipe = results_pipe
        self.terminate_queue = terminate_queue
        self.run_event = run_event
        
        self.auto_rotate_jpeg = auto_rotate_jpeg
        self.focal_length = focal_length

    def check_termination_request(self):
        """
        Check to see this process has not been requested to immediately terminate
        """
        if not self.terminate_queue.empty():
            x = self.terminate_queue.get()
            # terminate immediately
            return True
        return False
        
    def create_rational(self, value):
        return '%s/%s' % (value.numerator, value.denominator)
        
    def run(self):
        
        download_count = 0
        copy_finished = False
        while not copy_finished:        
            logger.debug("Finished %s. Getting next task.", download_count)
            
            rpd_file, download_count, temp_full_file_name, thumbnail_icon, thumbnail, copy_finished = self.results_pipe.recv()
            if rpd_file is None:
                # this is a termination signal
                logger.info("Terminating file modify via pipe")
                return None
            # pause if instructed by the caller
            self.run_event.wait()
                
            if self.check_termination_request():
                return None
            
            if self.auto_rotate_jpeg and rpd_file.file_type == rpdfile.FILE_TYPE_PHOTO:
                if rpd_file.extension in rpdfile.JPEG_EXTENSIONS:
                    lossless_rotate(rpd_file.temp_full_file_name)

            xmp_sidecar = None
            # check to see if focal length and aperture data should be manipulated
            if self.focal_length is not None and rpd_file.file_type == rpdfile.FILE_TYPE_PHOTO:
                if subfolderfile.load_metadata(rpd_file, temp_file=True):
                    a = rpd_file.metadata.aperture()
                    if a == '0.0':
                        logger.info("Adjusting focal length and aperture for %s (%s)", rpd_file.temp_full_file_name, rpd_file.name)
                        
                        new_focal_length = fractions.Fraction(self.focal_length,1)
                        new_aperture = fractions.Fraction(8,1)
                        if rpd_file.extension in WRITE_XMP_INPLACE:
                            try:
                                rpd_file.metadata["Exif.Photo.FocalLength"] = new_focal_length
                                rpd_file.metadata["Exif.Photo.FNumber"] = new_aperture
                                rpd_file.metadata.write(preserve_timestamps=True)
                                logger.debug("Wrote new focal length and aperture to %s (%s)", rpd_file.temp_full_file_name, rpd_file.name)
                            except:
                                logger.error("failed to write new focal length and aperture to %s (%s)!", rpd_file.temp_full_file_name, rpd_file.name)
                        else:
                            # write to xmp sidecar
                            xmp_sidecar = mxmp.XmpMetadataSidecar(rpd_file.temp_full_file_name)
                            xmp_sidecar.set_exif_value('FocalLength', self.create_rational(new_focal_length))
                            xmp_sidecar.set_exif_value('FNumber', self.create_rational(new_aperture))
                            # store values in rpd_file, so they can be used in the subfolderfile process
                            rpd_file.new_focal_length = new_focal_length
                            rpd_file.new_aperture = new_aperture

            if False:
                xmp_sidecar.set_contact_url('http://www.website.net')
                xmp_sidecar.set_contact_email('user@email.com')
                
            if xmp_sidecar is not None:
                # need to write out xmp sidecar
                o = xmp_sidecar.write_xmp_sidecar()
                logger.debug("Wrote XMP sidecar file")
                logger.debug("exiv2 output: %s", o)
                rpd_file.temp_xmp_full_name = rpd_file.temp_full_file_name + '.xmp'
                
                
            copy_succeeded = True
            rpd_file.metadata = None #purge metadata, as it cannot be pickled
            
            self.results_pipe.send((rpdmp.CONN_PARTIAL, 
                        (copy_succeeded, rpd_file, download_count,
                         temp_full_file_name, 
                         thumbnail_icon, thumbnail)))
                         
        self.results_pipe.send((rpdmp.CONN_COMPLETE, None))        
                         
        
