# Copyright (C) 2011-2016 Damon Lynch <damonlynch@gmail.com>

# This file is part of Rapid Photo Downloader.
#
# Rapid Photo Downloader is free software: you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Rapid Photo Downloader is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Rapid Photo Downloader.  If not,
# see <http://www.gnu.org/licenses/>.

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2011-2016, Damon Lynch"

from collections import defaultdict
import time
import logging
from typing import Optional, Dict, List

from gettext import gettext as _

from raphodo.constants import DownloadStatus, FileType
from raphodo.thumbnaildisplay import DownloadStats


class DownloadTracker:
    """
    Track file downloads - their size, number, and any problems
    """
    def __init__(self):
        self.file_types_present_by_scan_id = dict()  # type: Dict[int, str]
        self._refresh_values()

    def _refresh_values(self):
        """ these values are reset when a download is completed"""
        self.size_of_download_in_bytes_by_scan_id = dict()  # type: Dict[int, int]
        self.total_bytes_backed_up_by_scan_id = dict()  # type: Dict[int, int]
        self.size_of_photo_backup_in_bytes_by_scan_id = dict()  # type: Dict[int, int]
        self.size_of_video_backup_in_bytes_by_scan_id = dict()  # type: Dict[int, int]
        self.raw_size_of_download_in_bytes_by_scan_id = dict()  # type: Dict[int, int]
        self.total_bytes_copied_by_scan_id = dict()  # type: Dict[int, int]
        self.total_bytes_video_backed_up_by_scan_id = dict()  # type: Dict[int, int]
        self.no_files_in_download_by_scan_id = dict()  # type: Dict[int, int]
        self.no_photos_in_download_by_scan_id = dict()  # type: Dict[int, int]
        self.no_videos_in_download_by_scan_id = dict()  # type: Dict[int, int]

        # 'Download count' tracks the index of the file being downloaded
        # into the list of files that need to be downloaded -- much like
        # a counter in a for loop, e.g. 'for i in list', where i is the counter
        self.download_count_for_file_by_uid = dict()  # type: Dict[bytes, int]
        self.download_count_by_scan_id = dict()  # type: Dict[int, int]
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
        self.backups_performed_by_uid = defaultdict(int)  # type: Dict[bytes, List[int,...]]
        self.backups_performed_by_scan_id = defaultdict(int)  # type: Dict[int, List[int,...]]
        self.no_backups_to_perform_by_scan_id = dict()  # type: Dict[int, int]
        self.auto_delete = defaultdict(list)

    def set_no_backup_devices(self, no_photo_backup_devices: int,
                              no_video_backup_devices: int) -> None:
        self.no_photo_backup_devices = no_photo_backup_devices
        self.no_video_backup_devices = no_video_backup_devices

    def init_stats(self, scan_id: int, stats: DownloadStats) -> None:
        no_files = stats.no_photos + stats.no_videos
        self.no_files_in_download_by_scan_id[scan_id] = no_files
        self.no_photos_in_download_by_scan_id[scan_id] = stats.no_photos
        self.no_videos_in_download_by_scan_id[scan_id] = stats.no_videos
        self.size_of_photo_backup_in_bytes_by_scan_id[
            scan_id] = stats.photos_size_in_bytes * \
                       self.no_photo_backup_devices
        self.size_of_video_backup_in_bytes_by_scan_id[
            scan_id] = stats.videos_size_in_bytes * \
                       self.no_video_backup_devices
        self.no_backups_to_perform_by_scan_id[scan_id] = \
            (stats.no_photos * self.no_photo_backup_devices) + \
            (stats.no_videos * self.no_video_backup_devices)
        total_bytes = stats.photos_size_in_bytes + stats.videos_size_in_bytes
        # rename_chunk is used to account for the time it takes to rename a
        # file, and potentially to generate thumbnails after it has renamed.
        # rename_chunk makes a notable difference to the user when they're
        # downloading from a a high speed source.
        # Determine the value by calculating how many files need a thumbnail
        # generated after they've been downloaded and renamed.
        chunk_weight = (stats.post_download_thumb_generation * 60 + (
            no_files - stats.post_download_thumb_generation) * 5) / no_files
        self.rename_chunk[scan_id] = int((total_bytes / no_files) * (chunk_weight / 100))
        self.size_of_download_in_bytes_by_scan_id[scan_id] = total_bytes + \
                    self.rename_chunk[scan_id] * no_files
        self.raw_size_of_download_in_bytes_by_scan_id[scan_id] = total_bytes
        self.total_bytes_to_download += \
                    self.size_of_download_in_bytes_by_scan_id[scan_id]
        self.files_downloaded[scan_id] = 0
        self.photos_downloaded[scan_id] = 0
        self.videos_downloaded[scan_id] = 0
        self.photo_failures[scan_id] = 0
        self.video_failures[scan_id] = 0
        self.warnings[scan_id] = 0
        self.total_bytes_backed_up_by_scan_id[scan_id] = 0

    def get_no_files_in_download(self, scan_id) -> int:
        return self.no_files_in_download_by_scan_id[scan_id]

    def get_no_files_downloaded(self, scan_id, file_type) -> int:
        if file_type == FileType.photo:
            return self.photos_downloaded.get(scan_id, 0)
        else:
            return self.videos_downloaded.get(scan_id, 0)

    def get_no_files_failed(self, scan_id, file_type) -> int:
        if file_type == FileType.photo:
            return self.photo_failures.get(scan_id, 0)
        else:
            return self.video_failures.get(scan_id, 0)

    def get_no_warnings(self, scan_id) -> int:
        return self.warnings.get(scan_id, 0)

    def add_to_auto_delete(self, rpd_file) -> None:
        self.auto_delete[rpd_file.scan_id].append(rpd_file.full_file_name)

    def get_files_to_auto_delete(self, scan_id) -> int:
        return self.auto_delete[scan_id]

    def clear_auto_delete(self, scan_id) -> None:
        if scan_id in self.auto_delete:
            del self.auto_delete[scan_id]

    def file_backed_up(self, scan_id: int, uid: bytes) -> None:
        self.backups_performed_by_uid[uid] += 1
        self.backups_performed_by_scan_id[scan_id] += 1

    def file_backed_up_to_all_locations(self, uid: bytes, file_type: FileType) -> bool:
        """
        Determine if this particular file has been backed up to all
        locations it should be
        :param uid: unique id of the file
        :param file_type: photo or video
        :return: True if backups for this particular file have completed, else
        False
        """
        if uid in self.backups_performed_by_uid:
            if file_type == FileType.photo:
                return self.backups_performed_by_uid[uid] == self.no_photo_backup_devices
            else:
                return self.backups_performed_by_uid[uid] == self.no_video_backup_devices
        else:
            logging.critical(
                "Unexpected uid in self.backups_performed_by_uid")
            return True

    def all_files_backed_up(self, scan_id: Optional[int]=None) -> bool:
        """
        Determine if all backups have finished in the download
        :param scan_id: scan id of the download. If None, then all
         scans will be checked
        :return: True if all backups finished, else False
        """
        if scan_id is None:
            for scan_id in self.no_backups_to_perform_by_scan_id:
                if self.no_backups_to_perform_by_scan_id[scan_id] != \
                        self.backups_performed_by_scan_id[scan_id]:
                    return False
            return True
        else:
            return self.no_backups_to_perform_by_scan_id[scan_id] == \
               self.backups_performed_by_scan_id[scan_id]

    def file_downloaded_increment(self, scan_id: int, file_type: FileType,
                                  status: DownloadStatus) -> None:
        self.files_downloaded[scan_id] += 1

        if status not in (DownloadStatus.download_failed,
                          DownloadStatus.download_and_backup_failed):
            if file_type == FileType.photo:
                self.photos_downloaded[scan_id] += 1
                self.total_photos_downloaded += 1
            else:
                self.videos_downloaded[scan_id] += 1
                self.total_videos_downloaded += 1

            if status in (DownloadStatus.downloaded_with_warning,
                          DownloadStatus.backup_problem):
                self.warnings[scan_id] += 1
                self.total_warnings += 1
        else:
            if file_type == FileType.photo:
                self.photo_failures[scan_id] += 1
                self.total_photo_failures += 1
            else:
                self.video_failures[scan_id] += 1
                self.total_video_failures += 1

    def get_percent_complete(self, scan_id: int) -> float:
        """
        Returns a float representing how much of the download
        has been completed for one particular device
        :return a value between 0.0 and 100.0
        """

        # when calculating the percentage, there are three components:
        # copy (download), rename ('rename_chunk'), and backup
        percent_complete = (((float(
                  self.total_bytes_copied_by_scan_id[scan_id])
                + self.rename_chunk[scan_id] * self.files_downloaded[scan_id])
                + self.total_bytes_backed_up_by_scan_id[scan_id])
                / (self.size_of_download_in_bytes_by_scan_id[scan_id] +
                   self.size_of_photo_backup_in_bytes_by_scan_id[scan_id] +
                   self.size_of_video_backup_in_bytes_by_scan_id[scan_id]
                   )) * 100

        return percent_complete

    def get_overall_percent_complete(self) -> float:
        """
        Returns a float representing how much of the download from one
        or more devices
        :return: a value between 0.0 and 1.0
        """
        total = 0
        for scan_id in self.total_bytes_copied_by_scan_id:
            device_total = (self.total_bytes_copied_by_scan_id[scan_id] +
                     (self.rename_chunk[scan_id] *
                      self.files_downloaded[scan_id]))
            total += device_total

        percent_complete = float(total) / self.total_bytes_to_download
        return percent_complete

    def set_total_bytes_copied(self, scan_id, total_bytes) -> None:
        assert total_bytes >= 0
        self.total_bytes_copied_by_scan_id[scan_id] = total_bytes

    def increment_bytes_backed_up(self, scan_id, chunk_downloaded) -> None:
        self.total_bytes_backed_up_by_scan_id[scan_id] += chunk_downloaded

    def set_download_count_for_file(self, uid, download_count) -> None:
        self.download_count_for_file_by_uid[uid] = download_count

    def get_download_count_for_file(self, uid: bytes) -> None:
        return self.download_count_for_file_by_uid[uid]

    def set_download_count(self, scan_id, download_count) -> None:
        self.download_count_by_scan_id[scan_id] = download_count

    def get_file_types_present(self, scan_id) -> str:
        return self.file_types_present_by_scan_id[scan_id]

    def set_file_types_present(self, scan_id: int, file_types_present: str) -> None:
        self.file_types_present_by_scan_id[scan_id] = file_types_present

    def no_errors_or_warnings(self):
        """
        Return True if there were no errors or warnings in the download
        else return False
        """
        return (self.total_warnings == 0 and
                self.total_photo_failures == 0 and
                self.total_video_failures == 0)

    def purge(self, scan_id):
        del self.no_files_in_download_by_scan_id[scan_id]
        del self.size_of_download_in_bytes_by_scan_id[scan_id]
        del self.raw_size_of_download_in_bytes_by_scan_id[scan_id]
        del self.photos_downloaded[scan_id]
        del self.videos_downloaded[scan_id]
        del self.files_downloaded[scan_id]
        del self.photo_failures[scan_id]
        del self.video_failures[scan_id]
        del self.warnings[scan_id]
        del self.no_backups_to_perform_by_scan_id[scan_id]

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
            download_speed = "%1.1f" % (
                            amt_downloaded / 1048576 / amt_time) + _("MB/s")
        else:
            download_speed = None

        return (update, download_speed)

class TimeForDownload:
    # used to store variables, see below
    pass

class TimeRemaining:
    r"""
    Calculate how much time is remaining to finish a download

    >>> t = TimeRemaining()
    >>> t[0] = 1024*1024*1024
    >>> del t[0]
    """
    gap = 3
    def __init__(self):
        self.clear()

    def __setitem__(self, scan_id, size: int):
        t = TimeForDownload()
        t.time_remaining = None
        t.size = size
        t.downloaded = 0
        t.size_mark = 0
        t.time_mark = time.time()
        self.times[scan_id] = t

    def update(self, scan_id, bytes_downloaded):
        if scan_id in self.times:
            self.times[scan_id].downloaded += bytes_downloaded
            now = time.time()
            tm = self.times[scan_id].time_mark
            amt_time = now - tm
            if amt_time > self.gap:
                self.times[scan_id].time_mark = now
                amt_downloaded = self.times[scan_id].downloaded - self.times[
                    scan_id].size_mark
                self.times[scan_id].size_mark = self.times[scan_id].downloaded
                timefraction = amt_downloaded / float(amt_time)
                amt_to_download = float(self.times[scan_id].size) - self.times[
                    scan_id].downloaded
                if timefraction:
                    self.times[
                        scan_id].time_remaining = amt_to_download / \
                                                  timefraction

    def _time_estimates(self):
        for t in self.times:
            yield self.times[t].time_remaining

    def time_remaining(self):
        return max(self._time_estimates())

    def set_time_mark(self, scan_id):
        if scan_id in self.times:
            self.times[scan_id].time_mark = time.time()

    def clear(self):
        self.times = {}

    def __delitem__(self, scan_id):
        del self.times[scan_id]
