#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2011-2012 Damon Lynch <damonlynch@gmail.com>

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
### Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301
### USA

"""
Generates names for files and folders.

Runs as a daemon process.
"""

import os, datetime, collections

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

class SyncRawJpeg:
    def __init__(self):
        self.photos = {}
        
    def add_download(self, name, extension, date_time, sub_seconds, sequence_number_used):
        if name not in self.photos:
            self.photos[name] = ([extension], date_time, sub_seconds, sequence_number_used)
        else:
            if extension not in self.photos[name][0]:
                self.photos[name][0].append(extension)

        
    def matching_pair(self, name, extension, date_time, sub_seconds):
        """Checks to see if the image matches an image that has already been downloaded.
        Image name (minus extension), exif date time, and exif subseconds are checked.
        
        Returns -1 and a sequence number if the name, extension, and exif values match (i.e. it has already been downloaded)
        Returns 0 and a sequence number if name and exif values match, but the extension is different (i.e. a matching RAW + JPG image)
        Returns -99 and a sequence number of None if photos detected with the same filenames, but taken at different times
        Returns 1 and a sequence number of None if no match"""
        
        if name in self.photos:
            if self.photos[name][1] == date_time and self.photos[name][2] == sub_seconds:
                if extension in self.photos[name][0]:
                    return (-1, self.photos[name][3])
                else:
                    return (0, self.photos[name][3])
            else:
                return (-99, None)
        return (1, None)
        
    def ext_exif_date_time(self, name):
        """Returns first extension, exif date time and subseconds data for the already downloaded photo"""
        return (self.photos[name][0][0], self.photos[name][1], self.photos[name][2])
        
def time_subseconds_human_readable(date, subseconds):
    return _("%(hour)s:%(minute)s:%(second)s:%(subsecond)s") % \
            {'hour':date.strftime("%H"),
             'minute':date.strftime("%M"), 
             'second':date.strftime("%S"),
             'subsecond': subseconds}        

def load_metadata(rpd_file, temp_file=True):
    """
    Loads the metadata for the file. Returns True if operation succeeded, false
    otherwise
    
    If temp_file is true, the the metadata from the temporary file rather than
    the original source file is used. This is important, because the metadata
    can be modified by the filemodify process.
    """
    if rpd_file.metadata is None:        
        if not rpd_file.load_metadata(temp_file):
            # Error in reading metadata
            rpd_file.add_problem(None, pn.CANNOT_DOWNLOAD_BAD_METADATA, {'filetype': rpd_file.title_capitalized})
            return False
    return True
        

def _generate_name(generator, rpd_file):
    
    do_generation = True
    if rpd_file.file_type == rpdfile.FILE_TYPE_PHOTO:
        do_generation = load_metadata(rpd_file)
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
        
    def file_exists(self, rpd_file, identifier=None):
        """
        Notify user that the download file already exists
        """
        # get information on when the existing file was last modified
        try:
            modification_time = os.path.getmtime(rpd_file.download_full_file_name)
            dt = datetime.datetime.fromtimestamp(modification_time)
            date = dt.strftime("%x")
            time = dt.strftime("%X")
        except:
            logger.warning("Could not determine the file modification time of %s", 
                                rpd_file.download_full_file_name)
            date = time = ''
            
        if not identifier:
            rpd_file.add_problem(None, pn.FILE_ALREADY_EXISTS_NO_DOWNLOAD, 
                                {'filetype':rpd_file.title_capitalized})
            rpd_file.add_extra_detail(pn.EXISTING_FILE, 
                                {'filetype': rpd_file.title, 
                                'date': date, 'time': time})
            rpd_file.status = config.STATUS_DOWNLOAD_FAILED
            rpd_file.error_extra_detail = pn.extra_detail_definitions[pn.EXISTING_FILE] % \
                  {'date':date, 'time':time, 'filetype': rpd_file.title}
        else:
            rpd_file.add_problem(None, pn.UNIQUE_IDENTIFIER_ADDED, 
                                {'filetype':rpd_file.title_capitalized})
            rpd_file.add_extra_detail(pn.UNIQUE_IDENTIFIER, 
                                {'identifier': identifier, 
                                'filetype': rpd_file.title,
                                'date': date, 'time': time})
            rpd_file.status = config.STATUS_DOWNLOADED_WITH_WARNING
            rpd_file.error_extra_detail = pn.extra_detail_definitions[pn.UNIQUE_IDENTIFIER] % \
                   {'identifier': identifier, 'filetype': rpd_file.title,
                    'date': date, 'time': time}
        rpd_file.error_title = rpd_file.problem.get_title()
        rpd_file.error_msg = _("Source: %(source)s\nDestination: %(destination)s") \
                % {'source': rpd_file.full_file_name, 
                   'destination': rpd_file.download_full_file_name}
        return rpd_file
        
    def download_failure_file_error(self, rpd_file, inst):
        """
        Handle cases where file failed to download
        """
        rpd_file.add_problem(None, pn.DOWNLOAD_COPYING_ERROR, {'filetype': rpd_file.title})
        rpd_file.add_extra_detail(pn.DOWNLOAD_COPYING_ERROR_DETAIL, inst)
        rpd_file.status = config.STATUS_DOWNLOAD_FAILED
        logger.error("Failed to create file %s: %s", rpd_file.download_full_file_name, inst)
        
        rpd_file.error_title = rpd_file.problem.get_title()
        rpd_file.error_msg = _("%(problem)s\nFile: %(file)s") % \
                              {'problem': rpd_file.problem.get_problems(),
                               'file': rpd_file.full_file_name}
        
        return rpd_file
        
    def same_name_different_exif(self, sync_photo_name, rpd_file):
        """Notify the user that a file was already downloaded with the same name, but the exif information was different"""
        i1_ext, i1_date_time, i1_subseconds = self.sync_raw_jpeg.ext_exif_date_time(sync_photo_name)
        detail = {'image1': "%s%s" % (sync_photo_name, i1_ext), 
            'image1_date': i1_date_time.strftime("%x"),
            'image1_time': time_subseconds_human_readable(i1_date_time, i1_subseconds), 
            'image2':      rpd_file.name, 
            'image2_date': rpd_file.metadata.date_time().strftime("%x"),
            'image2_time': time_subseconds_human_readable(
                                rpd_file.metadata.date_time(), 
                                rpd_file.metadata.sub_seconds())}
        rpd_file.add_problem(None, pn.SAME_FILE_DIFFERENT_EXIF, detail)

        rpd_file.error_title = _('Photos detected with the same filenames, but taken at different times')
        rpd_file.error_msg = pn.problem_definitions[pn.SAME_FILE_DIFFERENT_EXIF][1] % detail
        rpd_file.status = config.STATUS_DOWNLOADED_WITH_WARNING
        return rpd_file
        
        
    def run(self):
        """
        Get subfolder and name.
        Attempt to move the file from it's temporary directory.
        Move video THM file if there is one.
        If successful, increment sequence values.
        Report any success or failure.
        """
        i = 0
        download_count = 0
        
        duplicate_files = {}


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
                                      
        self.sync_raw_jpeg = SyncRawJpeg()
                                      

        while True:
            logger.debug("Finished %s. Getting next task.", download_count)

            # rename file and move to generated subfolder                    
            download_succeeded, download_count, rpd_file = self.results_pipe.recv()
            
            move_succeeded = False
            

            if download_succeeded:
                temp_file = gio.File(rpd_file.temp_full_file_name)

                synchronize_raw_jpg_failed = False
                if not (rpd_file.synchronize_raw_jpg and
                    rpd_file.file_type == rpdfile.FILE_TYPE_PHOTO):
                    synchronize_raw_jpg = False
                    sequence_to_use = None
                else:
                    synchronize_raw_jpg = True
                    sync_photo_name, sync_photo_ext = os.path.splitext(rpd_file.name)
                    if not load_metadata(rpd_file):
                        synchronize_raw_jpg_failed = True
                    else:
                        j, sequence_to_use = self.sync_raw_jpeg.matching_pair(
                                name=sync_photo_name, extension=sync_photo_ext, 
                                date_time=rpd_file.metadata.date_time(), 
                                sub_seconds=rpd_file.metadata.sub_seconds())
                        if j == -1:
                            # this exact file has already been downloaded (same extension, same filename, and same exif date time subsecond info)
                            if (rpd_file.download_conflict_resolution <>
                                    config.ADD_UNIQUE_IDENTIFIER):
                                rpd_file.add_problem(None, pn.FILE_ALREADY_DOWNLOADED, {'filetype': rpd_file.title_capitalized})
                                rpd_file.error_title = _('Photo has already been downloaded')
                                rpd_file.error_msg = _("Source: %(source)s") % {'source': rpd_file.full_file_name}
                                rpd_file.status = config.STATUS_DOWNLOAD_FAILED
                                synchronize_raw_jpg_failed = True
                        else:
                            self.sequences.set_matched_sequence_value(sequence_to_use)
                            if j == -99:
                                rpd_file = self.same_name_different_exif(sync_photo_name, rpd_file)
                    
                if synchronize_raw_jpg_failed:
                    generation_succeeded = False
                else:
                    # Generate subfolder name and new file name
                    generation_succeeded = True
                    
                    if rpd_file.file_type == rpdfile.FILE_TYPE_PHOTO:
                        if hasattr(rpd_file, 'new_focal_length'):
                            # A RAW file has had its focal length and aperture adjusted.
                            # These have been written out to an XMP sidecar, but they won't
                            # be picked up by pyexiv2. So temporarily change the values inplace here, 
                            # without saving them.
                            if load_metadata(rpd_file):
                                rpd_file.metadata["Exif.Photo.FocalLength"] = rpd_file.new_focal_length
                                rpd_file.metadata["Exif.Photo.FNumber"] = rpd_file.new_aperture
                    
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
                            rpd_file.error_title = rpd_file.problem.get_title()
                            rpd_file.error_msg = _("%(problem)s\nFile: %(file)s") % \
                                     {'problem': rpd_file.problem.get_problems(),
                                      'file': rpd_file.full_file_name}
                                      
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
                        
                        rpd_file.error_title = rpd_file.problem.get_title()
                        rpd_file.error_msg = _("%(problem)s\nFile: %(file)s") % \
                                     {'problem': rpd_file.problem.get_problems(),
                                      'file': rpd_file.full_file_name}
                    
                    
                if generation_succeeded:
                    rpd_file.download_path = os.path.join(rpd_file.download_folder, rpd_file.download_subfolder)
                    rpd_file.download_full_file_name = os.path.join(rpd_file.download_path, rpd_file.download_name)
                    rpd_file.download_full_base_name = os.path.splitext(rpd_file.download_full_file_name)[0]
                    
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
                                logger.error("Failed to create download subfolder: %s", rpd_file.download_path)
                                logger.error(inst)
                                rpd_file.error_title = _("Failed to create download subfolder")
                                rpd_file.error_msg = _("Path: %s") % rpd_file.download_path
                    
                    # Move temp file to subfolder

                    download_file = gio.File(rpd_file.download_full_file_name)
                    
                    add_unique_identifier = False
                    try:
                        temp_file.move(download_file, self.progress_callback_no_update, cancellable=None)
                        move_succeeded = True
                        if rpd_file.status <> config.STATUS_DOWNLOADED_WITH_WARNING:
                            rpd_file.status = config.STATUS_DOWNLOADED
                    except gio.Error, inst:
                        if inst.code == gio.ERROR_EXISTS:
                            if (rpd_file.download_conflict_resolution == 
                                config.ADD_UNIQUE_IDENTIFIER):
                                add_unique_identifier = True
                            else:
                                rpd_file = self.file_exists(rpd_file)
                        else:
                            rpd_file = self.download_failure_file_error(rpd_file, inst)
                    
                    if add_unique_identifier:
                        name = os.path.splitext(rpd_file.download_name)
                        full_name = rpd_file.download_full_file_name
                        suffix_already_used = True
                        while suffix_already_used:
                            duplicate_files[full_name] = duplicate_files.get(
                                                              full_name, 0) + 1
                            identifier = '_%s' % duplicate_files[full_name]
                            rpd_file.download_name = name[0] + identifier + name[1]
                            rpd_file.download_full_file_name = os.path.join(
                                                    rpd_file.download_path,
                                                    rpd_file.download_name)
                            download_file = gio.File(
                                            rpd_file.download_full_file_name)
                            
                            try:
                                temp_file.move(download_file, self.progress_callback_no_update, cancellable=None)
                                move_succeeded = True
                                suffix_already_used = False
                                rpd_file = self.file_exists(rpd_file, identifier)
                                logger.error("%s: %s - %s", rpd_file.full_file_name, 
                                    rpd_file.problem.get_title(), 
                                    rpd_file.problem.get_problems())
                            except gio.Error, inst:
                                if inst.code <> gio.ERROR_EXISTS:
                                    rpd_file = self.download_failure_file_error(rpd_file, inst)
                            
                        
                        
                    logger.debug("Finish processing file: %s", download_count)                    
                
                if move_succeeded:
                    if synchronize_raw_jpg:
                        if sequence_to_use is None:
                            sequence = self.sequences.create_matched_sequences()
                        else:
                            sequence = sequence_to_use
                        self.sync_raw_jpeg.add_download(name=sync_photo_name,
                                extension=sync_photo_ext,
                                date_time=rpd_file.metadata.date_time(),
                                sub_seconds=rpd_file.metadata.sub_seconds(),
                                sequence_number_used=sequence)
                    if sequence_to_use is None:
                        if self.uses_session_sequece_no.value or self.uses_sequence_letter.value:
                            self.sequences.increment(
                                            self.uses_session_sequece_no.value, 
                                            self.uses_sequence_letter.value)
                        if self.uses_stored_sequence_no.value:
                            self.stored_sequence_no.value += 1
                        self.downloads_today_tracker.increment_downloads_today()
                        self.downloads_today.value = self.downloads_today_tracker.get_raw_downloads_today()
                        self.downloads_today_date.value = self.downloads_today_tracker.get_raw_downloads_today_date()
                        
                    if rpd_file.temp_thm_full_name:
                        # copy and rename THM video file
                        source = gio.File(path=rpd_file.temp_thm_full_name)
                        ext = None
                        if hasattr(rpd_file, 'thm_extension'):
                            if rpd_file.thm_extension:
                                ext = rpd_file.thm_extension
                        if ext is None:
                            ext = '.THM'
                        download_thm_full_name = rpd_file.download_full_base_name + ext
                        dest = gio.File(path=download_thm_full_name)
                        try:
                            source.move(dest, self.progress_callback_no_update, cancellable=None)
                            rpd_file.download_thm_full_name = download_thm_full_name
                        except gio.Error, inst:
                            logger.error("Failed to move video THM file %s", download_thm_full_name)
                            
                    if rpd_file.temp_xmp_full_name:
                        # copy and rename XMP sidecar file
                        source = gio.File(path=rpd_file.temp_xmp_full_name)
                        # generate_name() has generated xmp extension with correct capitalization
                        download_xmp_full_name = rpd_file.download_full_base_name + rpd_file.xmp_extension
                        dest = gio.File(path=download_xmp_full_name)
                        try:
                            source.move(dest, self.progress_callback_no_update, cancellable=None)
                            rpd_file.download_xmp_full_name = download_xmp_full_name
                        except gio.Error, inst:
                            logger.error("Failed to move XMP sidecar file %s", download_xmp_full_name)
                            
                
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
            rpd_file.sequences = None
            self.results_pipe.send((move_succeeded, rpd_file,))
            
            i += 1
            


