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
import tempfile
import os

import gio, glib

import logging
logger = multiprocessing.get_logger()

import rpdmultiprocessing as rpdmp
import rpdfile


from common import Configi18n
global _
_ = Configi18n._


class CopyFiles(multiprocessing.Process):
    def __init__(self, photo_download_folder, video_download_folder, files,
                 scan_pid, 
                 batch_size_MB, results_pipe, terminate_queue, 
                 run_event):
        multiprocessing.Process.__init__(self)
        self.results_pipe = results_pipe
        self.terminate_queue = terminate_queue
        self.batch_size_bytes = batch_size_MB * 1048576 # * 1024 * 1024
        self.photo_download_folder = photo_download_folder
        self.video_download_folder = video_download_folder
        self.files = files
        self.scan_pid = scan_pid
        self.no_files= len(self.files)
        self.run_event = run_event
        
    def progress_callback(self, amount_downloaded, total):
        
        if (amount_downloaded - self.bytes_downloaded > self.batch_size_bytes) or (amount_downloaded == total):
            chunk_downloaded = amount_downloaded - self.bytes_downloaded
            self.bytes_downloaded = amount_downloaded
            self.results_pipe.send((rpdmp.CONN_PARTIAL, (rpdmp.MSG_BYTES, (self.scan_pid, self.total_downloaded + amount_downloaded))))

    def run(self):
        """start the actual copying of files"""
        
        self.bytes_downloaded = 0
        self.total_downloaded = 0
        
        self.create_temp_dirs()
        
        if self.photo_temp_dir or self.video_temp_dir:
            for i in range(len(self.files)):
                rpd_file = self.files[i]
                
                # pause if instructed by the caller
                self.run_event.wait()
                
                if not self.terminate_queue.empty():
                    x = self.terminate_queue.get()
                    # terminate immediately
                    logger.info("Terminating file copying")
                    self.clean_temp_dirs()
                    return None
                
                source = gio.File(path=rpd_file.full_file_name)
                temp_full_file_name = os.path.join(
                                    self._get_dest_dir(rpd_file.file_type), 
                                    rpd_file.name)
                dest = gio.File(path=temp_full_file_name)
                
                copy_succeeded = False            
                try:
                    if not source.copy(dest, self.progress_callback, cancellable=gio.Cancellable()):
                        logger.error("Failed to copy %s", rpd_file.full_file_name)
                    else:
                        copy_succeeded = True
                except glib.GError, inst:
                    logger.error("Copy failure: %s", inst)
                
                # increment this amount regardless of whether the copy actually
                # succeeded or not. It's neccessary to keep the user informed.
                self.total_downloaded += rpd_file.size
                
                
                self.results_pipe.send((rpdmp.CONN_PARTIAL, (rpdmp.MSG_FILE, 
                                    (rpd_file, i + 1, temp_full_file_name))))
                    
            
            
        #FIXME: move this
        self.clean_temp_dirs()
        # Send the location of both temporary directories, so they can be
        # removed once another process attempts to rename all the files in them
        # and move them to generated subfolders
        self.results_pipe.send((rpdmp.CONN_COMPLETE, (self.scan_pid,
                                                     self.photo_temp_dir,
                                                     self.video_temp_dir)))
            

    def _get_dest_dir(self, file_type):
        if file_type == rpdfile.FILE_TYPE_PHOTO:
            return self.photo_temp_dir
        else:
            return self.video_temp_dir
    
    def _create_temp_dir(self, folder):
        try:
            temp_dir = tempfile.mkdtemp(prefix="rpd-tmp-", dir=folder)
            logger.info("Created temp dir %s", temp_dir)
        except OSError, (errno, strerror):
            # FIXME: error reporting
            logger.error("Failed to create temporary directory in %s: %s %s",
                         errono,
                         strerror,
                         folder)
            temp_dir = None
        
        return temp_dir
    
    def create_temp_dirs(self):
        self.photo_temp_dir = self.video_temp_dir = None
        if self.photo_download_folder is not None:
            self.photo_temp_dir = self._create_temp_dir(self.photo_download_folder)
        if self.video_download_folder is not None:
            self.video_temp_dir = self._create_temp_dir(self.photo_download_folder)
            
    def clean_temp_dirs(self):
        """
        Deletes temporary files and folders using gio
        """
        for temp_dir in (self.photo_temp_dir, self.video_temp_dir):
            if temp_dir:
                path = gio.File(temp_dir)
                # first delete any files in the temp directory
                # assume there are no directories in the temp directory
                file_attributes = "standard::name,standard::type"
                children = path.enumerate_children(file_attributes)
                for child in children:
                    f = path.get_child(child.get_name())
                    logger.info("Deleting %s", child.get_name())
                    f.delete(cancellable=None)
                path.delete(cancellable=None)
                logger.info("Deleted temp dir %s", temp_dir)
                
                
            
            
                            
        #~ if size is not None:
            #~ if self.counter > 0:
                #~ # send any remaining results
                #~ self.results_pipe.send((rpdmp.CONN_PARTIAL, self.files))
            #~ self.results_pipe.send((rpdmp.CONN_COMPLETE, (size, 
                                    #~ self.file_type_counter, self.pid)))
            #~ self.results_pipe.close()   
