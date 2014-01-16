#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2011-2014 Damon Lynch <damonlynch@gmail.com>

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

import time

import multiprocessing
import logging
logger = multiprocessing.get_logger()

from rpdfile import FILE_TYPE_PHOTO, FILE_TYPE_VIDEO
from config import STATUS_DOWNLOAD_FAILED, STATUS_DOWNLOADED_WITH_WARNING, \
                   STATUS_DOWNLOAD_AND_BACKUP_FAILED, STATUS_BACKUP_PROBLEM

from gettext import gettext as _

class DownloadTracker:
    """
    Track file downloads - their size, number, and any problems
    """
    def __init__(self):
        self.file_types_present_by_scan_pid = dict()
        self._refresh_values()

    def _refresh_values(self):
        """ these values are reset when a download is completed"""
        self.size_of_download_in_bytes_by_scan_pid = dict()
        self.total_bytes_backed_up_by_scan_pid = dict()
        self.size_of_photo_backup_in_bytes_by_scan_pid = dict()
        self.size_of_video_backup_in_bytes_by_scan_pid = dict()
        self.raw_size_of_download_in_bytes_by_scan_pid = dict()
        self.total_bytes_copied_by_scan_pid = dict()
        self.total_bytes_video_backed_up_by_scan_pid = dict()
        self.no_files_in_download_by_scan_pid = dict()
        self.no_photos_in_download_by_scan_pid = dict()
        self.no_videos_in_download_by_scan_pid = dict()


        # 'Download count' tracks the index of the file being downloaded
        # into the list of files that need to be downloaded -- much like
        # a counter in a for loop, e.g. 'for i in list', where i is the counter
        self.download_count_for_file_by_unique_id = dict()
        self.download_count_by_scan_pid = dict()
        self.rename_chunk = dict()
        self.files_downloaded = dict()
        self.photos_downloaded = dict()
        self.videos_downloaded = dict()
        self.photo_failures = dict()
        self.video_failures = dict()
        self.warnings = dict()
        self.total_photos_downloaded = 0
        self.total_photo_failures = 0
        self.total_videos_downloaded = 0
        self.total_video_failures = 0
        self.total_warnings = 0
        self.total_bytes_to_download = 0
        self.backups_performed_by_unique_id = dict()
        self.auto_delete = dict()

    def set_no_backup_devices(self, no_photo_backup_devices, no_video_backup_devices):
        self.no_photo_backup_devices = no_photo_backup_devices
        self.no_video_backup_devices = no_video_backup_devices
        #~ self.no_backup_devices = no_photo_backup_devices + no_video_backup_devices
#~
    #~ def get_no_backup_devices(self):
        #~ """
        #~ Returns how many devices are being used to backup files of each type
        #~ Return value is an integer tuple: photo and video
        #~ """
        #~ return (self.no_photo_backup_devices, self.no_video_backup_devices)

    def init_stats(self, scan_pid, photo_size_in_bytes, video_size_in_bytes, no_photos_to_download, no_videos_to_download):
        no_files = no_photos_to_download + no_videos_to_download
        self.no_files_in_download_by_scan_pid[scan_pid] = no_files
        self.no_photos_in_download_by_scan_pid[scan_pid] = no_photos_to_download
        self.no_videos_in_download_by_scan_pid[scan_pid] = no_videos_to_download
        self.size_of_photo_backup_in_bytes_by_scan_pid[scan_pid] = photo_size_in_bytes * self.no_photo_backup_devices
        self.size_of_video_backup_in_bytes_by_scan_pid[scan_pid] = video_size_in_bytes * self.no_video_backup_devices
        bytes = photo_size_in_bytes + video_size_in_bytes
        # rename_chunk is used to account for the time it takes to rename a file
        # it is arbitrarily set to 10% of the time it takes to copy it
        # this makes a difference to the user when they're downloading from a
        # a high speed source
        self.rename_chunk[scan_pid] = bytes / 10 / no_files
        self.size_of_download_in_bytes_by_scan_pid[scan_pid] = bytes + self.rename_chunk[scan_pid] * no_files
        self.raw_size_of_download_in_bytes_by_scan_pid[scan_pid] = bytes
        self.total_bytes_to_download += self.size_of_download_in_bytes_by_scan_pid[scan_pid]
        self.files_downloaded[scan_pid] = 0
        self.photos_downloaded[scan_pid] = 0
        self.videos_downloaded[scan_pid] = 0
        self.photo_failures[scan_pid] = 0
        self.video_failures[scan_pid] = 0
        self.warnings[scan_pid] = 0
        self.total_bytes_backed_up_by_scan_pid[scan_pid] = 0

    def get_no_files_in_download(self, scan_pid):
        return self.no_files_in_download_by_scan_pid[scan_pid]

    def get_no_files_downloaded(self, scan_pid, file_type):
        if file_type == FILE_TYPE_PHOTO:
            return self.photos_downloaded.get(scan_pid, 0)
        else:
            return self.videos_downloaded.get(scan_pid, 0)

    def get_no_files_failed(self, scan_pid, file_type):
        if file_type == FILE_TYPE_PHOTO:
            return self.photo_failures.get(scan_pid, 0)
        else:
            return self.video_failures.get(scan_pid, 0)

    def get_no_warnings(self, scan_pid):
        return self.warnings.get(scan_pid, 0)

    def add_to_auto_delete(self, rpd_file):
        if rpd_file.scan_pid in self.auto_delete:
            self.auto_delete[rpd_file.scan_pid].append(rpd_file.full_file_name)
        else:
            self.auto_delete[rpd_file.scan_pid] = [rpd_file.full_file_name,]

    def get_files_to_auto_delete(self, scan_pid):
        return self.auto_delete[scan_pid]

    def clear_auto_delete(self, scan_pid):
        if scan_pid in self.auto_delete:
            del self.auto_delete[scan_pid]

    def file_backed_up(self, unique_id):
        self.backups_performed_by_unique_id[unique_id] = \
                    self.backups_performed_by_unique_id.get(unique_id, 0) + 1

    def all_files_backed_up(self, unique_id, file_type):
        if unique_id in self.backups_performed_by_unique_id:
            if file_type == FILE_TYPE_PHOTO:
                return self.backups_performed_by_unique_id[unique_id] == self.no_photo_backup_devices
            else:
                return self.backups_performed_by_unique_id[unique_id] == self.no_video_backup_devices
        else:
            logger.critical("Unexpected unique_id in self.backups_performed_by_unique_id")
            return True


    def file_downloaded_increment(self, scan_pid, file_type, status):
        self.files_downloaded[scan_pid] += 1

        if status <> STATUS_DOWNLOAD_FAILED and status <> STATUS_DOWNLOAD_AND_BACKUP_FAILED:
            if file_type == FILE_TYPE_PHOTO:
                self.photos_downloaded[scan_pid] += 1
                self.total_photos_downloaded += 1
            else:
                self.videos_downloaded[scan_pid] += 1
                self.total_videos_downloaded += 1

            if status == STATUS_DOWNLOADED_WITH_WARNING or status == STATUS_BACKUP_PROBLEM:
                self.warnings[scan_pid] += 1
                self.total_warnings += 1
        else:
            if file_type == FILE_TYPE_PHOTO:
                self.photo_failures[scan_pid] += 1
                self.total_photo_failures += 1
            else:
                self.video_failures[scan_pid] += 1
                self.total_video_failures += 1

    def get_percent_complete(self, scan_pid):
        """
        Returns a float representing how much of the download
        has been completed
        """

        # when calculating the percentage, there are three components:
        # copy (download), rename ('rename_chunk'), and backup
        percent_complete = (((float(
                  self.total_bytes_copied_by_scan_pid[scan_pid])
                + self.rename_chunk[scan_pid] * self.files_downloaded[scan_pid])
                + self.total_bytes_backed_up_by_scan_pid[scan_pid])
                / (self.size_of_download_in_bytes_by_scan_pid[scan_pid] +
                   self.size_of_photo_backup_in_bytes_by_scan_pid[scan_pid] +
                   self.size_of_video_backup_in_bytes_by_scan_pid[scan_pid]
                   )) * 100

        return percent_complete

    def get_overall_percent_complete(self):
        total = 0
        for scan_pid in self.total_bytes_copied_by_scan_pid:
            total += (self.total_bytes_copied_by_scan_pid[scan_pid] +
                     (self.rename_chunk[scan_pid] *
                      self.files_downloaded[scan_pid]))

        percent_complete = float(total) / self.total_bytes_to_download
        return percent_complete

    def set_total_bytes_copied(self, scan_pid, total_bytes):
        self.total_bytes_copied_by_scan_pid[scan_pid] = total_bytes

    def increment_bytes_backed_up(self, scan_pid, chunk_downloaded):
        self.total_bytes_backed_up_by_scan_pid[scan_pid] += chunk_downloaded

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

    def no_errors_or_warnings(self):
        """
        Return True if there were no errors or warnings in the download
        else return False
        """
        return (self.total_warnings == 0 and
                self.total_photo_failures == 0 and
                self.total_video_failures == 0)

    def purge(self, scan_pid):
        del self.no_files_in_download_by_scan_pid[scan_pid]
        del self.size_of_download_in_bytes_by_scan_pid[scan_pid]
        del self.raw_size_of_download_in_bytes_by_scan_pid[scan_pid]
        del self.photos_downloaded[scan_pid]
        del self.videos_downloaded[scan_pid]
        del self.files_downloaded[scan_pid]
        del self.photo_failures[scan_pid]
        del self.video_failures[scan_pid]
        del self.warnings[scan_pid]

    def purge_all(self):
        self._refresh_values()



class TimeCheck:
    """
    Record times downloads commmence and pause - used in calculating time
    remaining.

    Also tracks and reports download speed.

    Note: This is completely independent of the file / subfolder naming
    preference "download start time"
    """

    def __init__(self):
        # set the number of seconds gap with which to measure download time remaing
        self.download_time_gap = 3

        self.reset()

    def reset(self):
        self.mark_set = False
        self.total_downloaded_so_far = 0
        self.total_download_size = 0
        self.size_mark = 0

    def increment(self, bytes_downloaded):
        self.total_downloaded_so_far += bytes_downloaded

    def set_download_mark(self):
        if not self.mark_set:
            self.mark_set = True

            self.time_mark = time.time()

    def pause(self):
        self.mark_set = False

    def check_for_update(self):
        now = time.time()
        update = now > (self.download_time_gap + self.time_mark)

        if update:
            amt_time = now - self.time_mark
            self.time_mark = now
            amt_downloaded = self.total_downloaded_so_far - self.size_mark
            self.size_mark = self.total_downloaded_so_far
            download_speed = "%1.1f" % (amt_downloaded / 1048576 / amt_time) +_("MB/s")
        else:
            download_speed = None

        return (update, download_speed)

class TimeForDownload:
    # used to store variables, see below
    pass

class TimeRemaining:
    """
    Calculate how much time is remaining to finish a download
    """
    gap = 3
    def __init__(self):
        self.clear()

    def set(self, scan_pid, size):
        t = TimeForDownload()
        t.time_remaining = None
        t.size = size
        t.downloaded = 0
        t.size_mark = 0
        t.time_mark = time.time()
        self.times[scan_pid] = t

    def update(self, scan_pid, bytes_downloaded):
        if scan_pid in self.times:
            self.times[scan_pid].downloaded += bytes_downloaded
            now = time.time()
            tm = self.times[scan_pid].time_mark
            amt_time = now - tm
            if amt_time > self.gap:
                self.times[scan_pid].time_mark = now
                amt_downloaded = self.times[scan_pid].downloaded - self.times[scan_pid].size_mark
                self.times[scan_pid].size_mark = self.times[scan_pid].downloaded
                timefraction = amt_downloaded / float(amt_time)
                amt_to_download = float(self.times[scan_pid].size) - self.times[scan_pid].downloaded
                if timefraction:
                    self.times[scan_pid].time_remaining = amt_to_download / timefraction

    def _time_estimates(self):
        for t in self.times:
            yield self.times[t].time_remaining

    def time_remaining(self):
        return max(self._time_estimates())

    def set_time_mark(self, scan_pid):
        if scan_pid in self.times:
            self.times[scan_pid].time_mark = time.time()

    def clear(self):
        self.times = {}

    def remove(self, scan_pid):
        if scan_pid in self.times:
            del self.times[scan_pid]
