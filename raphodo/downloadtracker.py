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
import math
import locale
import logging
from typing import Optional, Dict, List, Tuple, Set

from gettext import gettext as _

from raphodo.constants import DownloadStatus, FileType, DownloadUpdateSeconds
from raphodo.thumbnaildisplay import DownloadStats
from raphodo.rpdfile import RPDFile

try:
    Infinity = math.inf
except AttributeError:
    Infinity = float("inf")

class DownloadTracker:
    """
    Track file downloads - their size, number, and any problems
    """
    # TODO: refactor this class to make it more pythonic
    # contemplate using settrs

    def __init__(self):
        self.file_types_present_by_scan_id = dict()  # type: Dict[int, str]
        self._refresh_values()

    def _refresh_values(self):
        """
        Reset values when a download is completed
        """

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
        self.no_post_download_thumb_generation_by_scan_id = dict()  # type: Dict[int, int]

        # 'Download count' tracks the index of the file being downloaded
        # into the list of files that need to be downloaded -- much like
        # a counter in a for loop, e.g. 'for i in list', where i is the counter
        self.download_count_for_file_by_uid = dict()  # type: Dict[bytes, int]
        self.download_count_by_scan_id = dict()  # type: Dict[int, int]
        self.rename_chunk = dict()  # type: Dict[int, int]
        self.files_downloaded = dict()  # type: Dict[int, int]
        self.photos_downloaded = dict()  # type: Dict[int, int]
        self.videos_downloaded = dict()  # type: Dict[int, int]
        self.photo_failures = dict()  # type: Dict[int, int]
        self.video_failures = dict()  # type: Dict[int, int]
        self.warnings = dict()  # type: Dict[int, int]
        self.post_download_thumb_generation = dict()  # type: Dict[int, int]
        self.total_photos_downloaded = 0  # type: int
        self.total_photo_failures = 0  # type: int
        self.total_videos_downloaded = 0  # type: int
        self.total_video_failures = 0  # type: int
        self.total_warnings = 0  # type: int
        self.total_bytes_to_download = 0  # type: int
        self.total_bytes_to_backup = 0  # type: int
        self.backups_performed_by_uid = defaultdict(int)  # type: Dict[bytes, List[int,...]]
        self.backups_performed_by_scan_id = defaultdict(int)  # type: Dict[int, List[int,...]]
        self.no_backups_to_perform_by_scan_id = dict()  # type: Dict[int, int]
        self.auto_delete = defaultdict(list)
        self._devices_removed_mid_download = set()  # type: Set[int]

    def set_no_backup_devices(self, no_photo_backup_devices: int,
                              no_video_backup_devices: int) -> None:
        self.no_photo_backup_devices = no_photo_backup_devices
        self.no_video_backup_devices = no_video_backup_devices

    def init_stats(self, scan_id: int, stats: DownloadStats) -> None:
        no_files = stats.no_photos + stats.no_videos
        self.no_files_in_download_by_scan_id[scan_id] = no_files
        self.no_photos_in_download_by_scan_id[scan_id] = stats.no_photos
        self.no_videos_in_download_by_scan_id[scan_id] = stats.no_videos
        self.size_of_photo_backup_in_bytes_by_scan_id[scan_id] = \
            stats.photos_size_in_bytes * self.no_photo_backup_devices
        self.size_of_video_backup_in_bytes_by_scan_id[scan_id] = \
            stats.videos_size_in_bytes * self.no_video_backup_devices
        self.no_backups_to_perform_by_scan_id[scan_id] = \
            stats.no_photos * self.no_photo_backup_devices + \
            stats.no_videos * self.no_video_backup_devices
        total_bytes = stats.photos_size_in_bytes + stats.videos_size_in_bytes
        self.no_post_download_thumb_generation_by_scan_id[scan_id] =  \
            stats.post_download_thumb_generation

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
        self.total_bytes_to_download += self.size_of_download_in_bytes_by_scan_id[scan_id]
        self.total_bytes_to_backup += self.size_of_photo_backup_in_bytes_by_scan_id[scan_id] + \
                                      self.size_of_video_backup_in_bytes_by_scan_id[scan_id]
        self.files_downloaded[scan_id] = 0
        self.photos_downloaded[scan_id] = 0
        self.videos_downloaded[scan_id] = 0
        self.photo_failures[scan_id] = 0
        self.video_failures[scan_id] = 0
        self.warnings[scan_id] = 0
        self.post_download_thumb_generation[scan_id] = 0
        self.total_bytes_backed_up_by_scan_id[scan_id] = 0

    def get_no_files_in_download(self, scan_id: int) -> int:
        return self.no_files_in_download_by_scan_id[scan_id]

    def get_no_files_downloaded(self, scan_id: int, file_type: FileType) -> int:
        if file_type == FileType.photo:
            return self.photos_downloaded.get(scan_id, 0)
        else:
            return self.videos_downloaded.get(scan_id, 0)

    def get_no_files_failed(self, scan_id: int, file_type: FileType) -> int:
        if file_type == FileType.photo:
            return self.photo_failures.get(scan_id, 0)
        else:
            return self.video_failures.get(scan_id, 0)

    def get_no_warnings(self, scan_id: int) -> int:
        return self.warnings.get(scan_id, 0)

    def add_to_auto_delete(self, rpd_file: RPDFile) -> None:
        self.auto_delete[rpd_file.scan_id].append(rpd_file.full_file_name)

    def get_files_to_auto_delete(self, scan_id: int) -> int:
        return self.auto_delete[scan_id]

    def clear_auto_delete(self, scan_id: int) -> None:
        if scan_id in self.auto_delete:
            del self.auto_delete[scan_id]

    def thumbnail_generated_post_download(self, scan_id: int) -> None:
        """
        Increment the number of files that have had their thumbnail
        generated after they were downloaded
        :param scan_id: the device from which the file came
        """

        if scan_id in self._devices_removed_mid_download:
            return

        self.post_download_thumb_generation[scan_id] += 1

    def file_backed_up(self, scan_id: int, uid: bytes) -> None:

        if scan_id in self._devices_removed_mid_download:
            return

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
            logging.critical("Unexpected uid in self.backups_performed_by_uid")
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
                if (self.no_backups_to_perform_by_scan_id[scan_id] !=
                        self.backups_performed_by_scan_id[scan_id] and
                        scan_id not in self._devices_removed_mid_download):
                    return False
            return True
        else:
            return (self.no_backups_to_perform_by_scan_id[scan_id] ==
                    self.backups_performed_by_scan_id[scan_id] or
                    scan_id in self._devices_removed_mid_download)

    def file_downloaded_increment(self, scan_id: int,
                                  file_type: FileType,
                                  status: DownloadStatus) -> None:

        if scan_id in self._devices_removed_mid_download:
            return

        self.files_downloaded[scan_id] += 1

        if status in (DownloadStatus.download_failed, DownloadStatus.download_and_backup_failed):
            if file_type == FileType.photo:
                self.photo_failures[scan_id] += 1
                self.total_photo_failures += 1
            else:
                self.video_failures[scan_id] += 1
                self.total_video_failures += 1
        else:
            if file_type == FileType.photo:
                self.photos_downloaded[scan_id] += 1
                self.total_photos_downloaded += 1
            else:
                self.videos_downloaded[scan_id] += 1
                self.total_videos_downloaded += 1

            if status in (DownloadStatus.downloaded_with_warning, DownloadStatus.backup_problem):
                self.warnings[scan_id] += 1
                self.total_warnings += 1

    def device_removed_mid_download(self, scan_id: int, display_name: str) -> None:
        """
        Adjust the the tracking to account for a device being removed as a download
        was occurring.

        :param scan_id: scan id of the device that has been removed
        """

        logging.debug("Adjusting download tracking to account for removed device %s",
                      display_name)

        self._devices_removed_mid_download.add(scan_id)

        photos_downloaded = self.photo_failures[scan_id] + self.photos_downloaded[scan_id]
        failures = self.no_photos_in_download_by_scan_id[scan_id] - photos_downloaded
        self.photo_failures[scan_id] += failures
        self.total_photo_failures += failures

        videos_downloaded = self.video_failures[scan_id] + self.videos_downloaded[scan_id]
        failures = self.no_videos_in_download_by_scan_id[scan_id] - videos_downloaded
        self.video_failures[scan_id] += failures
        self.total_video_failures += failures

        self.download_count_by_scan_id[scan_id] = self.no_files_in_download_by_scan_id[scan_id]
        self.files_downloaded[scan_id] = self.no_files_in_download_by_scan_id[scan_id]

        self.total_bytes_copied_by_scan_id[scan_id] = \
            self.size_of_download_in_bytes_by_scan_id[scan_id]

        self.total_bytes_backed_up_by_scan_id[scan_id] = \
            self.size_of_photo_backup_in_bytes_by_scan_id[scan_id] + \
            self.size_of_video_backup_in_bytes_by_scan_id[scan_id]

    def get_percent_complete(self, scan_id: int) -> float:
        """
        Returns a float representing how much of the download
        has been completed for one particular device

        :return a value between 0.0 and 1.0
        """

        # when calculating the percentage, there are three components:
        # copy (download), rename ('rename_chunk'), and backup
        percent_complete = (((
                  self.total_bytes_copied_by_scan_id[scan_id]
                + self.rename_chunk[scan_id] * self.files_downloaded[scan_id])
                + self.total_bytes_backed_up_by_scan_id[scan_id])
                / (self.size_of_download_in_bytes_by_scan_id[scan_id] +
                   self.size_of_photo_backup_in_bytes_by_scan_id[scan_id] +
                   self.size_of_video_backup_in_bytes_by_scan_id[scan_id]
                   ))

        return  percent_complete

    def get_overall_percent_complete(self) -> float:
        """
        Returns a float representing how much of the download from one
        or more devices
        :return: a value between 0.0 and 1.0
        """

        total = sum(self.total_bytes_copied_by_scan_id[scan_id] +
                    self.rename_chunk[scan_id] * self.files_downloaded[scan_id] +
                    self.total_bytes_backed_up_by_scan_id[scan_id]
                    for scan_id in self.total_bytes_copied_by_scan_id)

        p = total / (self.total_bytes_to_download + self.total_bytes_to_backup)
        # round the number down, e.g. 0.997 becomes 0.99
        return math.floor(p * 100) / 100

    def all_post_download_thumbs_generated_for_scan(self, scan_id: int) -> bool:
        return self.no_post_download_thumb_generation_by_scan_id[scan_id] == \
               self.post_download_thumb_generation[scan_id]

    def all_files_downloaded_by_scan_id(self, scan_id: int) -> bool:
        return self.files_downloaded[scan_id] == self.no_files_in_download_by_scan_id[scan_id]

    def set_total_bytes_copied(self, scan_id: int, total_bytes: int) -> None:
        if scan_id in self._devices_removed_mid_download:
            return
        assert total_bytes >= 0
        self.total_bytes_copied_by_scan_id[scan_id] = total_bytes

    def increment_bytes_backed_up(self, scan_id: int, chunk_downloaded: int) -> None:

        if scan_id in self._devices_removed_mid_download:
            return

        self.total_bytes_backed_up_by_scan_id[scan_id] += chunk_downloaded

    def set_download_count_for_file(self, uid: bytes, download_count: int) -> None:
        self.download_count_for_file_by_uid[uid] = download_count

    def get_download_count_for_file(self, uid: bytes) -> None:
        return self.download_count_for_file_by_uid[uid]

    def set_download_count(self, scan_id: int, download_count: int) -> None:
        if scan_id in self._devices_removed_mid_download:
            return
        self.download_count_by_scan_id[scan_id] = download_count

    def get_file_types_present(self, scan_id: int) -> str:
        return self.file_types_present_by_scan_id[scan_id]

    def set_file_types_present(self, scan_id: int, file_types_present: str) -> None:
        self.file_types_present_by_scan_id[scan_id] = file_types_present

    def no_errors_or_warnings(self) -> bool:
        """
        :return: True if there were no errors or warnings in the download
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
    Record times downloads commence and pause - used in calculating time
    remaining.

    Also tracks and reports download speed for the entire download, in sum, i.e.
    for all the devices and all backups as one.

    Note: Times here are completely independent of the file / subfolder naming
    preference "download start time"
    """

    def __init__(self):
        # set the number of seconds gap with which to measure download time remaing
        self.reset()
        self.mpbs = _("MB/sec")
        self.time_gap = DownloadUpdateSeconds / 2

    def reset(self):
        self.mark_set = False
        self.total_downloaded_so_far = 0
        self.total_download_size = 0
        self.size_mark = 0
        self.smoothed_speed = None  # type: Optional[float]

    def increment(self, bytes_downloaded):
        self.total_downloaded_so_far += bytes_downloaded

    def set_download_mark(self):
        if not self.mark_set:
            self.mark_set = True
            self.time_mark = time.time()

    def pause(self):
        self.mark_set = False

    def update_download_speed(self) -> Tuple[bool, str]:
        now = time.time()
        updated = now > (self.time_gap + self.time_mark)

        if updated:
            amt_time = now - self.time_mark
            self.time_mark = now
            amt_downloaded = self.total_downloaded_so_far - self.size_mark
            self.size_mark = self.total_downloaded_so_far
            speed = amt_downloaded / 1048576 / amt_time
            if self.smoothed_speed is None:
                self.smoothed_speed = speed
            else:
                # smooth speed across fifteen readings
                self.smoothed_speed = (self.smoothed_speed * 14 + speed) / 15
            download_speed = "%1.1f %s" % (self.smoothed_speed, self.mpbs)
        else:
            download_speed = None

        return (updated, download_speed)


class TimeForDownload:
    def __init__(self, size: int) -> None:
        self.time_remaining = Infinity  # type: float

        self.total_downloaded_so_far = 0   # type: int
        self.total_download_size = size  # type: int
        self.size_mark = 0  # type: int
        self.smoothed_speed = None  # type: Optional[float]

        self.time_mark = time.time()  # type: float
        self.smoothed_speed = None  # type: Optional[float]


class TimeRemaining:
    """
    Calculate how much time is remaining to finish a download
    
    Runs in tandem with TimeCheck, above.
    
    The smoothed speed for each device is independent of the smoothed
    speed for the download as a whole.
    """

    def __init__(self) -> None:
        self.clear()

    def __setitem__(self, scan_id: int, size: int) -> None:
        t = TimeForDownload(size)
        self.times[scan_id] = t

    def update(self, scan_id, bytes_downloaded) -> None:

        if not scan_id in self.times:
            return

        t = self.times[scan_id]  # type: TimeForDownload

        t.total_downloaded_so_far += bytes_downloaded
        now = time.time()
        tm = t.time_mark
        amt_time = now - tm

        if amt_time > DownloadUpdateSeconds:

            amt_downloaded = t.total_downloaded_so_far - t.size_mark
            t.size_mark = t.total_downloaded_so_far
            t.time_mark = now

            speed = amt_downloaded / amt_time

            if t.smoothed_speed is None:
                t.smoothed_speed = speed
            else:
                # smooth speed across ten readings
                t.smoothed_speed = t.smoothed_speed * .9 + speed * .1

            amt_to_download = t.total_download_size - t.total_downloaded_so_far

            if not t.smoothed_speed:
                t.time_remaining = Infinity
            else:
                time_remaining = amt_to_download / t.smoothed_speed
                # Use the previous value to help determine the current value,
                # which avoids values that jump around
                if math.isinf(t.time_remaining):
                    t.time_remaining = time_remaining
                else:
                    t.time_remaining = get_time_left(time_remaining, t.time_remaining)

    def time_remaining(self, detailed_time_remaining: bool) -> Optional[str]:
        """
        Return the time remaining to download by taking the largest
        value of all the devices being downloaded from.

        :param detailed_time_remaining: if True, don't limit the precision
         of the result return
        :return: Time remaining in string format. Returns None if the
        time remaining is unknown.
        """

        time_remaining = max(t.time_remaining for t in self.times.values())
        if math.isinf(time_remaining):
            return None

        time_remaining =  round(time_remaining)  # type: int
        if time_remaining < 4:
            # Be friendly in the last few seconds
            return _('A few seconds')
        else:
            # Format the string using the one or two largest units
            return formatTime(time_remaining, limit_precision=not detailed_time_remaining)

    def set_time_mark(self, scan_id):
        if scan_id in self.times:
            self.times[scan_id].time_mark = time.time()

    def clear(self):
        self.times = {}

    def __delitem__(self, scan_id):
        del self.times[scan_id]


def get_time_left(aSeconds: float, aLastSec: Optional[float]=None) -> float:
    """
    Generate a "time left" string given an estimate on the time left and the
    last time. The extra time is used to give a better estimate on the time to
    show. Both the time values are floats instead of integers to help get
    sub-second accuracy for current and future estimates.

    Closely adapted from Mozilla's getTimeLeft function:
    https://dxr.mozilla.org/mozilla-central/source/toolkit/mozapps/downloads/DownloadUtils.jsm

    :param aSeconds: Current estimate on number of seconds left for the download
    :param aLastSec: Last time remaining in seconds or None or infinity for unknown
    :return: time left text, new value of "last seconds"
    """

    if aLastSec is None:
        aLastSec = Infinity

    if aSeconds < 0:
      return aLastSec

    # Apply smoothing only if the new time isn't a huge change -- e.g., if the
    # new time is more than half the previous time; this is useful for
    # downloads that start/resume slowly
    if aSeconds > aLastSec / 2:
        # Apply hysteresis to favor downward over upward swings
        # 30% of down and 10% of up (exponential smoothing)
        diff = aSeconds - aLastSec
        aSeconds = aLastSec + (0.3 if diff < 0 else 0.1) * diff

        # If the new time is similar, reuse something close to the last seconds,
        # but subtract a little to provide forward progress
        diffPct = diff / aLastSec * 100
        if abs(diff) < 5 or abs(diffPct) < 5:
            aSeconds = aLastSec - (0.4 if diff < 0 else 0.2)

    return aSeconds

def _seconds(seconds: int) -> str:
    if seconds == 1:
        return _('1 second')
    else:
        return _('%d seconds') % seconds


def _minutes(minutes: int) -> str:
    if minutes == 1:
        return _('1 minute')
    else:
        return _('%d minutes') % minutes


def _hours(hours: int) -> str:
    if hours == 1:
        return _('1 hour')
    else:
        return _('%d hours') % hours


def _days(days: int) -> str:
    if days == 1:
        return _('1 day')
    else:
        return _('%d days') % days


def formatTime(seconds: int, limit_precision=False) -> str:
    r"""
    >>> locale.setlocale(locale.LC_ALL, ('en_US', 'utf-8'))
    'en_US.UTF-8'
    >>> formatTime(0)
    '0 seconds'
    >>> formatTime(1)
    '1 second'
    >>> formatTime(2)
    '2 seconds'
    >>> formatTime(59)
    '59 seconds'
    >>> formatTime(60)
    '1 minute'
    >>> formatTime(61)
    '1 minute, 1 second'
    >>> formatTime(62)
    '1 minute, 2 seconds'
    >>> formatTime(60 + 59)
    '1 minute, 59 seconds'
    >>> formatTime(60 * 2)
    '2 minutes'
    >>> formatTime(60 * 2 + 1)
    '2 minutes, 1 second'
    >>> formatTime(60 * 2 + 2)
    '2 minutes, 2 seconds'
    >>> formatTime(60 * 3 + 25)
    '3 minutes, 25 seconds'
    >>> formatTime(60 * 3 + 25, limit_precision=True)
    '3 minutes'
    >>> formatTime(60 * 3 + 30)
    '3 minutes, 30 seconds'
    >>> formatTime(60 * 3 + 30, limit_precision=True)
    '4 minutes'
    >>> formatTime(60 * 45)
    '45 minutes'
    >>> formatTime(60 * 60 - 30)
    '59 minutes, 30 seconds'
    >>> formatTime(60 * 60 - 30, limit_precision=True)
    '1 hour'
    >>> formatTime(60 * 60 - 1)
    '59 minutes, 59 seconds'
    >>> formatTime(60 * 60)
    '1 hour'
    >>> formatTime(60 * 60 + 1)
    '1 hour'
    >>> formatTime(60 * 60 + 29)
    '1 hour'
    >>> formatTime(60 * 60 + 30)
    '1 hour, 1 minute'
    >>> formatTime(60 * 60 + 59)
    '1 hour, 1 minute'
    >>> formatTime(60 * 61)
    '1 hour, 1 minute'
    >>> formatTime(60 * 61 + 29)
    '1 hour, 1 minute'
    >>> formatTime(60 * 61 + 30)
    '1 hour, 2 minutes'
    >>> formatTime(60 * 60 * 2)
    '2 hours'
    >>> formatTime(60 * 60 * 2 + 45)
    '2 hours, 1 minute'
    >>> formatTime(60 * 60 * 2 + 60 * 29)
    '2 hours, 29 minutes'
    >>> formatTime(60 * 60 * 2 + 60 * 29 + 29)
    '2 hours, 29 minutes'
    >>> formatTime(60 * 60 * 2 + 60 * 29 + 29, limit_precision=True)
    '2 hours'
    >>> formatTime(60 * 60 * 2 + 60 * 29 + 30)
    '2 hours, 30 minutes'
    >>> formatTime(60 * 60 * 2 + 60 * 29 + 30, limit_precision=True)
    '2 hours'
    >>> formatTime(60 * 60 * 2 + 60 * 30)
    '2 hours, 30 minutes'
    >>> formatTime(60 * 60 * 2 + 60 * 30, limit_precision=True)
    '3 hours'
    >>> formatTime(60 * 60 * 2 + 60 * 59)
    '2 hours, 59 minutes'
    >>> formatTime(60 * 60 * 2 + 60 * 59 + 30)
    '3 hours'
    >>> formatTime(60 * 60 * 3 + 29)
    '3 hours'
    >>> formatTime(60 * 60 * 3 + 30)
    '3 hours, 1 minute'
    >>> formatTime(60 * 60 * 23 + 60 * 29)
    '23 hours, 29 minutes'
    >>> formatTime(60 * 60 * 23 + 60 * 29 + 29)
    '23 hours, 29 minutes'
    >>> formatTime(60 * 60 * 23 + 60 * 29 + 30)
    '23 hours, 30 minutes'
    >>> formatTime(60 * 60 * 23 + 60 * 29 + 30)
    '23 hours, 30 minutes'
    >>> formatTime(60 * 60 * 23 + 60 * 59)
    '23 hours, 59 minutes'
    >>> formatTime(60 * 60 * 23 + 60 * 59 + 20)
    '23 hours, 59 minutes'
    >>> formatTime(60 * 60 * 23 + 60 * 59 + 40)
    '1 day'
    >>> formatTime(60 * 60 * 24)
    '1 day'
    >>> formatTime(60 * 60 * 24 + 60 * 29)
    '1 day'
    >>> formatTime(60 * 60 * 24 + 60 * 29 + 59)
    '1 day'
    >>> formatTime(60 * 60 * 24 + 60 * 30)
    '1 day, 1 hour'
    >>> formatTime(60 * 60 * 24 * 2 + 60 * 30)
    '2 days, 1 hour'
    >>> formatTime(60 * 60 * 24 * 2 + 60 * 60 * 3)
    '2 days, 3 hours'
    >>> formatTime(60 * 60 * 24 * 24 + 60 * 60 * 3)
    '24 days, 3 hours'
    >>> formatTime(60 * 60 * 24 * 24 + 60 * 60 * 3 + 59)
    '24 days, 3 hours'
    >>> formatTime(60 * 60 * 24 * 24 + 60 * 60 * 3 + 59, limit_precision=True)
    '24 days'
    >>> formatTime(60 * 60 * 24 * 24 + 60 * 60 * 18, limit_precision=True)
    '25 days'

    When passed n number of seconds, return a translated string
    that indicates using up to two units of time how much time is left.

    Times are rounded up or down.

    The highest unit of time used is days.
    :param seconds: the number of seconds
    :param limit_precision: if True, for any time >= three minutes, the
     time string will be limited to only 1 unit, e.g. 3 minutes, 4 minutes etc
    :return: the translated string
    """

    parts = []
    for idx, mul in enumerate((86400, 3600, 60, 1)):
        if seconds / mul >= 1 or mul == 1:
            if mul > 1:
                n = int(math.floor(seconds / mul))
                seconds -= n * mul
            else:
                n = seconds
            parts.append((idx, n))

    # take the parts, and if necessary add new parts that indicate zero hours or minutes

    parts2 = []
    i = 0
    for idx in range(parts[0][0], 4):
        part_idx = parts[i][0]
        if part_idx == idx:
            parts2.append(parts[i])
            i += 1
        else:
            parts2.append((idx, 0))

    # what remains is a consistent and predictable set of time components to work with:

    if len(parts2) == 1:
        assert parts2[0][0] == 3
        seconds = parts2[0][1]
        return _seconds(seconds)

    elif len(parts2) == 2:
        assert parts2[0][0] == 2
        assert parts2[0][1] > 0
        minutes = parts2[0][1]
        seconds = parts2[1][1]

        if limit_precision and minutes > 2:
            if seconds >= 30:
                minutes += 1
                if minutes == 60:
                    return _('1 hour')
            seconds = 0

        if seconds:
            if minutes == 1:
                if seconds == 1:
                    return _('1 minute, 1 second')
                else:
                    return _('1 minute, %d seconds') % seconds
            else:
                if seconds == 1:
                    return _('%d minutes, 1 second') % minutes
                else:
                    return _('%(minutes)d minutes, %(seconds)d seconds') % dict(
                        minutes=minutes, seconds=seconds)
        else:
            return _minutes(minutes)

    elif len(parts2) == 3:
        assert parts2[0][0] == 1
        assert parts2[0][1] > 0
        hours = parts2[0][1]
        minutes = parts2[1][1]
        seconds = parts2[2][1]

        if limit_precision:
            if minutes >= 30:
                hours += 1
                if hours == 24:
                    return _('1 day')
            minutes = 0
        # round up the minutes if needed
        elif seconds >= 30:
            if minutes == 59:
                minutes = 0
                hours += 1
                if hours == 24:
                    return _('1 day')
            else:
                minutes += 1

        if minutes:
            if hours == 1:
                if minutes == 1:
                    return _('1 hour, 1 minute')
                else:
                    return _('1 hour, %d minutes') % minutes
            else:
                if minutes == 1:
                    return _('%d hours, 1 minute') % hours
                else:
                    return _('%(hours)d hours, %(minutes)d minutes') % dict(hours=hours,
                                                                               minutes=minutes)
        else:
            return _hours(hours)
    else:
        assert len(parts2) == 4
        assert parts2[0][0] == 0
        assert parts2[0][1] > 0
        days = parts2[0][1]
        hours = parts2[1][1]
        minutes = parts2[2][1]

        if limit_precision:
            if hours >= 12:
                days += 1
            hours = 0
        elif minutes >= 30:
            if hours == 23:
                hours = 0
                days += 1
            else:
                hours += 1

        if hours:
            if days == 1:
                if hours == 1:
                    return _('1 day, 1 hour')
                else:
                    return _('1 day, %d hours') % hours
            else:
                if hours == 1:
                    return _('%d days, 1 hour') % days
                else:
                    return _('%(days)d days, %(hours)d hours') % dict(days=days, hours=hours)
        else:
            return _days(days)