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


import rpdfile
import rpdmultiprocessing as rpdmp
import generatename as gn
import problemnotification as pn
import prefsrapid
import config

from gettext import gettext as _



def _generate_name(generator, rpd_file):
    
    do_generation = True
    if rpd_file.file_type == rpdfile.FILE_TYPE_PHOTO:
        if rpd_file.metadata is None:        
            if not rpd_file.load_metadata():
                # Error in reading metadata
                rpd_file.add_problem(None, pn.CANNOT_DOWNLOAD_BAD_METADATA, {'filetype': rpd_file.title_capitalized})
                do_generation = False
    else:
        if rpd_file.metadata is None:
            rpd_file.load_metadata()

    if do_generation:
        value = generator.generate_name(rpd_file)
        if value is None:
            value = ''
    else:
        value = ''
    
    return value

def generate_subfolder(rpd_file):
    
    if rpd_file.file_type == rpdfile.FILE_TYPE_PHOTO:
        generator = gn.PhotoSubfolder(rpd_file.subfolder_pref_list)
    else:
        generator = gn.VideoSubfolder(rpd_file.subfolder_pref_list)
        
    rpd_file.download_subfolder = _generate_name(generator, rpd_file)
    return rpd_file
    
def generate_name(rpd_file):
    do_generation = True
    
    if rpd_file.file_type == rpdfile.FILE_TYPE_PHOTO:
        generator = gn.PhotoName(rpd_file.name_pref_list)
    else:
        generator = gn.VideoName(rpd_file.name_pref_list)
        
    rpd_file.download_name = _generate_name(generator, rpd_file)
    return rpd_file
        

class SubfolderFile(multiprocessing.Process):
    def __init__(self, results_pipe, sequence_values):
        multiprocessing.Process.__init__(self)
        self.daemon = True
        self.results_pipe = results_pipe
        
        self.downloads_today = sequence_values[0]
        self.downloads_today_date = sequence_values[1]
        self.day_start = sequence_values[2]
        self.refresh_downloads_today = sequence_values[3]
        self.stored_sequence_no = sequence_values[4]
        self.uses_stored_sequence_no = sequence_values[5]
        self.uses_session_sequece_no = sequence_values[6]
        self.uses_sequence_letter = sequence_values[7]
        
        logger.debug("Start of day is set to %s", self.day_start.value)
        


        
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


        # Track downloads today, using a class whose purpose is to 
        # take the value in the user prefs, increment, and then be used
        # to update the prefs (which can only happen via the main process)
        self.downloads_today_tracker = prefsrapid.DownloadsTodayTracker(
                                        day_start = self.day_start.value,
                                        downloads_today = self.downloads_today.value,
                                        downloads_today_date = self.downloads_today_date.value)
                                                
        # Track sequences using shared downloads today and stored sequence number
        # (shared with main process)
        self.sequences = gn.Sequences(self.downloads_today_tracker, 
                                      self.stored_sequence_no.value)
                                      

        while True:
            logger.debug("Finished %s. Getting next task.", download_count)

            task = self.results_pipe.recv()
            
            # rename file and move to generated subfolder                    
            download_succeeded, download_count, rpd_file = task
            
            move_succeeded = False
            

            if download_succeeded:
                temp_file = gio.File(rpd_file.temp_full_file_name)

                # Generate subfolder name and new file name                
                generation_succeeded = True
                rpd_file = generate_subfolder(rpd_file)
                if rpd_file.download_subfolder:
                    
                    if self.refresh_downloads_today.value:
                        # overwrite downloads today value tracked here,
                        # as user has modified their preferences
                        self.downloads_today_tracker.set_raw_downloads_today_from_int(self.downloads_today.value)
                        self.downloads_today_tracker.set_raw_downloads_today_date(self.downloads_today_date.value)
                        self.downloads_today_tracker.day_start = self.day_start.value
                        self.refresh_downloads_today.value = False
                        
                    # update whatever the stored value is
                    self.sequences.stored_sequence_no = self.stored_sequence_no.value
                    rpd_file.sequences = self.sequences
                    
                    # generate the file name
                    rpd_file = generate_name(rpd_file)
                    
                    if rpd_file.has_problem():
                        rpd_file.status = config.STATUS_DOWNLOADED_WITH_WARNING

                # Check for any errors
                if not rpd_file.download_subfolder or not rpd_file.download_name:
                    if not rpd_file.download_subfolder and not rpd_file.download_name:
                        area = _("subfolder and filename")
                    elif not rpd_file.download_name:
                        area = _("filename")
                    else:
                        area = _("subfolder")
                    rpd_file.add_problem(None, pn.ERROR_IN_NAME_GENERATION, {'filetype': rpd_file.title_capitalized, 'area': area})
                    rpd_file.add_extra_detail(pn.NO_DATA_TO_NAME, {'filetype': area})
                    generation_succeeded = False
                    rpd_file.status = config.STATUS_DOWNLOAD_FAILED
                    # FIXME: log error
                    
                if generation_succeeded:
                    rpd_file.download_path = os.path.join(rpd_file.download_folder, rpd_file.download_subfolder)
                    rpd_file.download_full_file_name = os.path.join(rpd_file.download_path, rpd_file.download_name)
                    
                    subfolder = gio.File(path=rpd_file.download_path)
                    
                    # Create subfolder if it does not exist.
                    # It is possible to skip the query step, and just try to create
                    # the directories and ignore the error of it already existing -
                    # but it takes twice as long to fail with an error than just
                    # run the straight query
                    
                    if not subfolder.query_exists(cancellable=None):
                        try:
                            subfolder.make_directory_with_parents(cancellable=gio.Cancellable())
                        except gio.Error, inst:
                            # The directory may have been created by another process
                            # between the time it takes to query and the time it takes
                            # to create a new directory. Ignore such errors.
                            if inst.code <> gio.ERROR_EXISTS:
                                logger.error("Failed to create directory: %s", rpd_file.download_path)
                                logger.error(inst)
                    
                    # Move temp file to subfolder

                    download_file = gio.File(rpd_file.download_full_file_name)
                    
                    try:
                        temp_file.move(download_file, self.progress_callback_no_update, cancellable=None)
                        move_succeeded = True
                        if rpd_file.status <> config.STATUS_DOWNLOADED_WITH_WARNING:
                            rpd_file.status = config.STATUS_DOWNLOADED
                    except gio.Error, inst:
                        rpd_file.add_problem(None, pn.DOWNLOAD_COPYING_ERROR, {'filetype': rpd_file.title})
                        rpd_file.add_extra_detail(pn.DOWNLOAD_COPYING_ERROR_DETAIL, inst)
                        rpd_file.status = config.STATUS_DOWNLOAD_FAILED
                        logger.error("Failed to create file %s: %s", rpd_file.download_full_file_name, inst)
                        
                    logger.debug("Finish processing file: %s", download_count)                    
                
                if move_succeeded:
                    if self.uses_session_sequece_no.value or self.uses_sequence_letter.value:
                        self.sequences.increment(
                                        self.uses_session_sequece_no.value, 
                                        self.uses_sequence_letter.value)
                    if self.uses_stored_sequence_no.value:
                        self.stored_sequence_no.value += 1
                    self.downloads_today_tracker.increment_downloads_today()
                    self.downloads_today.value = self.downloads_today_tracker.get_raw_downloads_today()
                    self.downloads_today_date.value = self.downloads_today_tracker.get_raw_downloads_today_date()
                
                if not move_succeeded:
                    logger.error("%s: %s - %s", rpd_file.full_file_name, 
                                 rpd_file.problem.get_title(), 
                                 rpd_file.problem.get_problems())
                    try:
                        temp_file.delete(cancellable=None)
                    except gio.Error, inst:
                        logger.error("Failed to delete temporary file %s", rpd_file.temp_full_file_name)
                        logger.error(inst)
                    

                    
            
            
            rpd_file.metadata = None #purge metadata, as it cannot be pickled
            self.results_pipe.send((move_succeeded, rpd_file,))
            
            i += 1
            


