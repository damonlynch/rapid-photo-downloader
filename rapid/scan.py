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
import multiprocessing

import gio
import gtk

import pyexiv2

import rpdmultiprocessing as rpdmp
import rpdfile


import logging
logger = multiprocessing.get_logger()

# python whitespace is significant - don't remove the leading whitespace on
# the second line

file_attributes = "standard::name,standard::display-name,\
standard::type,standard::size,time::modified,access::can-read,id::file"



class Scan(multiprocessing.Process):

    """Scans the given path for files of a specified type.
    
    Returns results in batches, finishing with a total of the size of all the
    files in bytes.
    """
    
    def __init__(self, path, batch_size, generate_folder, results_pipe, 
                 terminate_queue, run_event):
                     
        """Setup values needed to conduct the scan.
        
        'path' is a string of the path to be scanned, which is passed to gio.
        
        'batch_size' is the number of files that should be sent back to the 
        calling function at one time.
        
        'results_pipe' is a connection on which to send the results.
        
        'terminate_queue' is a queue whose sole purpose is to notify the 
        process that it should terminate and not return any results.
        
        'run_event' is an Event that is used to temporarily halt execution.
        
        """
        
        multiprocessing.Process.__init__(self)
        self.path = path
        self.results_pipe = results_pipe
        self.terminate_queue = terminate_queue
        self.run_event = run_event
        self.batch_size = batch_size
        self.generate_folder = generate_folder
        self.counter = 0
        self.files = []
        self.file_type_counter = rpdfile.FileTypeCounter()


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
                logger.info("terminating scan...")
                self.files = []
                return None

            # only collect files and scan in directories we can actually read
            # cannot assume that users will download only from memory cards
            
            if child.get_attribute_boolean(gio.FILE_ATTRIBUTE_ACCESS_CAN_READ):
                file_type = child.get_file_type()
                name = child.get_name()
                if file_type == gio.FILE_TYPE_DIRECTORY:
                    file_size_sum = self._gio_scan(path.get_child(name), 
                                                   file_size_sum)
                    if file_size_sum is None:
                        return None

                elif file_type == gio.FILE_TYPE_REGULAR:
                    ext = os.path.splitext(name)[1].lower()[1:]
                    
                    file_type = rpdfile.file_type(ext)
                    if file_type is not None:
                        file_id = child.get_attribute_string(
                                                gio.FILE_ATTRIBUTE_ID_FILE)
                        if file_id is not None:
                            # count how many files of each type are included
                            # e.g. photo, video
                            self.file_type_counter.add(file_type)
                            self.counter += 1
                            display_name = child.get_display_name()
                            size = child.get_size()
                            modification_time = child.get_modification_time()

                            scanned_file = rpdfile.get_rpdfile(ext, 
                                             name, 
                                             display_name, 
                                             path.get_path(),
                                             size,
                                             modification_time, 
                                             self.pid,
                                             file_id)
                                         
                            self.files.append(scanned_file)
                        
                            if self.counter == self.batch_size:
                                # send batch of results
                                self.results_pipe.send((rpdmp.CONN_PARTIAL, 
                                                        self.files))
                                self.files = []
                                self.counter = 0
                            
                            file_size_sum += size

        return file_size_sum
        

    def run(self):
        """start the actual scan."""
        source = gio.File(self.path)
        try:
            size = self._gio_scan(source, 0)
        except gio.Error, inst:
            logger.error("Error while scanning %s: %s", self.path, inst)
            size = None
            
        if size is not None:
            if self.counter > 0:
                # send any remaining results
                self.results_pipe.send((rpdmp.CONN_PARTIAL, self.files))
            self.results_pipe.send((rpdmp.CONN_COMPLETE, (size, 
                                    self.file_type_counter, self.pid)))
            self.results_pipe.close()                
