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

class DownloadTracker:
    def __init__(self):
        self.size_of_download_in_bytes_by_scan_pid = dict()
        self.total_bytes_copied_in_bytes_by_scan_pid = dict()
        self.no_files_in_download_by_scan_pid = dict()
        self.file_types_present_by_scan_pid = dict()
        self.download_count_for_file_by_unique_id = dict()
        self.download_count_by_scan_pid = dict()
        self.rename_chunk = dict()
        self.files_downloaded = dict()
        
    def init_stats(self, scan_pid, bytes, no_files):
        self.no_files_in_download_by_scan_pid[scan_pid] = no_files
        self.rename_chunk[scan_pid] = bytes / 10 / no_files
        self.size_of_download_in_bytes_by_scan_pid[scan_pid] = bytes + self.rename_chunk[scan_pid] * no_files
        self.files_downloaded[scan_pid] = 0
        
    def get_no_files_in_download(self, scan_pid):
        return self.no_files_in_download_by_scan_pid[scan_pid]
        
    def file_downloaded_increment(self, scan_pid):
        self.files_downloaded[scan_pid] += 1
        
        
    def get_percent_complete(self, scan_pid):
        """
        Returns a float representing how much of the download
        has been completed 
        """
        
        # three components: copy (download), rename, and backup
        percent_complete = ((float(
                  self.total_bytes_copied_in_bytes_by_scan_pid[scan_pid]) 
                + self.rename_chunk[scan_pid] * self.files_downloaded[scan_pid])
                / self.size_of_download_in_bytes_by_scan_pid[scan_pid]) * 100
        return percent_complete
        
    def set_total_bytes_copied(self, scan_pid, total_bytes):
        self.total_bytes_copied_in_bytes_by_scan_pid[scan_pid] = total_bytes
        
    def set_download_count_for_file(self, unique_id, download_count):
        self.download_count_for_file_by_unique_id[unique_id] = download_count
        
    def get_download_count_for_file(self, unique_id):
        return self.download_count_for_file_by_unique_id[unique_id]
        
    def set_download_count(self, scan_pid, download_count):
        self.download_count_by_scan_pid[scan_pid] = download_count
        
    def get_file_types_present(self, scan_pid):
        return self.file_types_present_by_scan_pid[scan_pid]
    
    def set_file_types_present(self, scan_pid, file_types_present):
        self.file_types_present_by_scan_pid[scan_pid] = file_types_present
        
    def purge(self, scan_pid):
        del self.no_files_in_download_by_scan_pid[scan_pid]
        del self.size_of_download_in_bytes_by_scan_pid[scan_pid]
        
