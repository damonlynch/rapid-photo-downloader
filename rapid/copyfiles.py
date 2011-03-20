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

import gio

import logging
logger = multiprocessing.get_logger()

import rpdmultiprocessing as rpdmp
import rpdfile
import problemnotification as pn
import config


from gettext import gettext as _


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
        
    def check_termination_request(self):
        """
        Check to see this process has not been requested to immediately terminate
        """
        if not self.terminate_queue.empty():
            x = self.terminate_queue.get()
            # terminate immediately
            logger.info("Terminating file copying")
            return True
        return False
        
        
    def update_progress(self, amount_downloaded, total):
        if (amount_downloaded - self.bytes_downloaded > self.batch_size_bytes) or (amount_downloaded == total):
            chunk_downloaded = amount_downloaded - self.bytes_downloaded
            self.bytes_downloaded = amount_downloaded
            self.results_pipe.send((rpdmp.CONN_PARTIAL, (rpdmp.MSG_BYTES, (self.scan_pid, self.total_downloaded + amount_downloaded))))        
    
    def progress_callback(self, amount_downloaded, total):
        
        if self.check_termination_request():
            # FIXME: cancel copy
            pass
         
        self.update_progress(amount_downloaded, total)
        

    def run(self):
        """start the actual copying of files"""
        
        self.bytes_downloaded = 0
        self.total_downloaded = 0
        
        self.create_temp_dirs()
        
        # Send the location of both temporary directories, so they can be
        # removed once another process attempts to rename all the files in them
        # and move them to generated subfolders
        self.results_pipe.send((rpdmp.CONN_PARTIAL, (rpdmp.MSG_TEMP_DIRS, 
                                                     (self.scan_pid,
                                                     self.photo_temp_dir,
                                                     self.video_temp_dir))))
        
        if self.photo_temp_dir or self.video_temp_dir:
            for i in range(len(self.files)):
                rpd_file = self.files[i]
                
                # pause if instructed by the caller
                self.run_event.wait()
                
                if self.check_termination_request():
                    return None
                
                source = gio.File(path=rpd_file.full_file_name)
                temp_full_file_name = os.path.join(
                                    self._get_dest_dir(rpd_file.file_type), 
                                    rpd_file.name)
                rpd_file.temp_full_file_name = temp_full_file_name
                dest = gio.File(path=temp_full_file_name)
                
                copy_succeeded = False
                try:
                    source.copy(dest, self.progress_callback, cancellable=None)
                    copy_succeeded = True
                except gio.Error, inst:
                    rpd_file.add_problem(None,
                        pn.DOWNLOAD_COPYING_ERROR_W_NO,
                        {'filetype': rpd_file.title})
                    rpd_file.add_extra_detail(
                        pn.DOWNLOAD_COPYING_ERROR_W_NO_DETAIL, 
                        {'errorno': inst.code, 'strerror': inst.message})
                        
                    rpd_file.status = config.STATUS_DOWNLOAD_FAILED
                    logger.error("Failed to download file: %s", rpd_file.full_file_name)
                    logger.error(inst)
                    self.update_progress(rpd_file.size, rpd_file.size)
                
                # increment this amount regardless of whether the copy actually
                # succeeded or not. It's neccessary to keep the user informed.
                self.total_downloaded += rpd_file.size
                
                
                self.results_pipe.send((rpdmp.CONN_PARTIAL, (rpdmp.MSG_FILE, 
                    (copy_succeeded, rpd_file, i + 1, temp_full_file_name))))
                    
            
        self.results_pipe.send((rpdmp.CONN_COMPLETE, None))
            

    def _get_dest_dir(self, file_type):
        if file_type == rpdfile.FILE_TYPE_PHOTO:
            return self.photo_temp_dir
        else:
            return self.video_temp_dir
    
    def _create_temp_dir(self, folder):
        try:
            temp_dir = tempfile.mkdtemp(prefix="rpd-tmp-", dir=folder)
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
            


