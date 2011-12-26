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

import os.path
import subprocess
import multiprocessing
import logging
logger = multiprocessing.get_logger()

import rpdmultiprocessing as rpdmp
import rpdfile

def lossless_rotate(jpeg):
    """using exiftran, performs a lossless, inplace translation of a jpeg, preserving time stamps"""
    try:
        logger.debug("Auto rotating %s", jpeg)
        v = proc = subprocess.Popen(['exiftran', '-a', '-i', '-p', jpeg], stdout=subprocess.PIPE)
        v = proc.communicate()[0].strip()
    except OSError:
        v = None
    return v
    
class FileModify(multiprocessing.Process):
    def __init__(self, auto_rotate_jpeg, results_pipe, terminate_queue, 
                 run_event):
        multiprocessing.Process.__init__(self)
        self.results_pipe = results_pipe
        self.terminate_queue = terminate_queue
        self.run_event = run_event
        
        self.auto_rotate_jpeg = auto_rotate_jpeg

    def check_termination_request(self):
        """
        Check to see this process has not been requested to immediately terminate
        """
        if not self.terminate_queue.empty():
            x = self.terminate_queue.get()
            # terminate immediately
            return True
        return False
        
    def run(self):
        
        download_count = 0
        copy_finished = False
        while not copy_finished:        
            logger.debug("Finished %s. Getting next task.", download_count)
            
            #~ download_count, rpd_file = self.results_pipe.recv()
            rpd_file, download_count, temp_full_file_name, thumbnail_icon, thumbnail, copy_finished = self.results_pipe.recv()
            if rpd_file is None:
                # this is a termination signal
                logger.info("Terminating file modify via pipe")
                return None
            # pause if instructed by the caller
            self.run_event.wait()
                
            if self.check_termination_request():
                return None
            
            file_modified = False

            if self.auto_rotate_jpeg and rpd_file.file_type == rpdfile.FILE_TYPE_PHOTO:
                if rpd_file.extension in rpdfile.JPEG_EXTENSIONS:
                    lossless_rotate(rpd_file.temp_full_file_name)
                    file_modified = True
                
            copy_succeeded = True
            self.results_pipe.send((rpdmp.CONN_PARTIAL, 
                        (copy_succeeded, rpd_file, download_count,
                         temp_full_file_name, 
                         thumbnail_icon, thumbnail)))
                         
        self.results_pipe.send((rpdmp.CONN_COMPLETE, None))        
                         
        
