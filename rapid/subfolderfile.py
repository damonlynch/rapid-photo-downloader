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

"""
Generates names for files and folders.

Runs a daemon process.
"""

import os

import gio
import multiprocessing
import logging
logger = multiprocessing.get_logger()

import prefsrapid
import rpdfile
import rpdmultiprocessing as rpdmp
import generatename as gn
import problemnotification as pn

def generate_subfolder(prefs, rpd_file, download_start_time):
    
    problem = pn.Problem()
    generate_subfolder = True    
    
    if rpd_file.file_type == rpdfile.FILE_TYPE_PHOTO:
        if not rpd_file.load_metadata():
            # Error in reading metadata
            problem.add_problem(None, pn.CANNOT_DOWNLOAD_BAD_METADATA, {'filetype': rpd_file.title_capitalized})
            generate_subfolder = False
        else:
            generator = gn.PhotoSubfolder(prefs, download_start_time)
    else:
        subfolder_prefs = prefs.video_subfolder
        rpd_file.load_metadata()
        generator = gn.VideoSubfolder(prefs, download_start_time)
    
 
    if generate_subfolder:
        generator.initialize_problem(problem)
        subfolder = generator.generate_name(rpd_file)
        logger.debug("Generated subfolder: %s", subfolder)
    else:
        subfolder = None
    
    return subfolder
    
def get_download_folder_from_prefs(prefs, file_type):
    if file_type == rpdfile.FILE_TYPE_PHOTO:
        return prefs.download_folder
    else:
        return prefs.video_download_folder
        

class SubfolderFile(multiprocessing.Process):
    def __init__(self, results_pipe):
        multiprocessing.Process.__init__(self)
        self.daemon = True
        self.results_pipe = results_pipe
        
    def progress_callback_no_update(self, amount_downloaded, total):
        pass
        
    def run(self):
        """
        Get subfolder and name.
        Attempt to move the file from it's temporary directory.
        If successful, increment sequence values.
        Report any success or failure.
        """
        i = 0
        download_count = 0
        
        # Preferences are 'live', i.e. they can change at any time
        # Before they are applied to generate file and subfolder names, they
        # must be accessed each and every time.
        self.prefs = prefsrapid.RapidPreferences()
        
        while True:
            logger.info("Finished %s. Getting next task.", download_count)

            task = self.results_pipe.recv()
                
            download_succeeded, download_count, rpd_file, temp_full_file_name, download_start_time = task
            
            move_succeeded = False
            
            if download_succeeded:
            
                # Generate subfolder name and new file name
                download_folder = get_download_folder_from_prefs(self.prefs, rpd_file.file_type)
                generated_subfolder = generate_subfolder(self.prefs, rpd_file, download_start_time)
                #~ generated_name = 'sample%s.cr2' % i
                generated_name = rpd_file.name
                if generated_subfolder is not None:
                    rpd_file.download_subfolder = generated_subfolder
                    rpd_file.download_path = os.path.join('/home/damon/store/rapid-dump', generated_subfolder)
                    rpd_file.download_name = generated_name
                    rpd_file.download_full_file_name = os.path.join(rpd_file.download_path, rpd_file.download_name)
                    
                    subfolder = gio.File(path=rpd_file.download_path)
                    
                    # Create subfolder if it does not exist.
                    # It is possible to skip the query step, and just try to create
                    # the directories and ignore the error of it already existing -
                    # but it takes twice as long to fail with an error than just
                    # run the straight query
                    
                    if not subfolder.query_exists(cancellable=None):
                        try:
                            subfolder.make_directory_with_parents(cancellable=None)
                        except gio.Error, inst:
                            # The directory may have been created by another process
                            # between the time it takes to query and the time it takes
                            # to create a new directory. Ignore such errors.
                            if inst.code <> gio.ERROR_EXISTS:
                                logger.error("Failed to create directory: %s", rpd_file.download_path)
                                logger.error(inst)
                    
                    # Move temp file to subfolder
                    temp_file = gio.File(temp_full_file_name)
                    download_file = gio.File(rpd_file.download_full_file_name)
                    
                    try:
                        temp_file.move(download_file, self.progress_callback_no_update, cancellable=None)
                        move_succeeded = True
                    except gio.Error, inst:
                        logger.error("Failed to create file %s: %s", rpd_file.download_full_file_name, inst)
                        
                    logger.info("Moved file: %s", download_count)                    
                        
                if not move_succeeded:
                    try:
                        temp_file.delete(cancellable=None)
                    except gio.Error, inst:
                        logger.error("Failed to delete temporary file %s", temp_full_file_name)
                        logger.error(inst)
                    

                    
            
            
            rpd_file.metadata = None #purge metadata, as it cannot be pickled
            self.results_pipe.send((move_succeeded, rpd_file,))
            
            i += 1
            
