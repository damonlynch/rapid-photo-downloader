#!/usr/bin/python3

__author__ = 'Damon Lynch'

# Copyright (C) 2011-2015 Damon Lynch <damonlynch@gmail.com>

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

import logging
import re
import os
import datetime

from PyQt5.QtCore import QSettings

from gettext import gettext as _

from storage import xdg_photos_directory, xdg_videos_directory
from generatenameconfig import *
import constants


class ScanPreferences:
    r"""
    Handle user preferences while scanning devices like memory cards,
    cameras or the filesystem. Pickled and passed between processes.

    Sets data attribute valid to True if ignored paths are valid. An ignored
    path is always assumed to be valid unless regular expressions are used.
    If regular expressions are used, then it is valid only if a valid
    regular expression can be compiled from each line.

    >>> no_ignored_paths = ScanPreferences([])
    >>> no_ignored_paths.valid
    True

    >>> some_paths = ScanPreferences(['.Trash', '.thumbnails'])
    >>> some_paths.valid
    True

    >>> some_re_paths = ScanPreferences(['.Trash', '\.[tT]humbnails'], True)
    >>> some_re_paths.valid
    True

    >>> some_more_re_paths = ScanPreferences(['.Trash', '\.[tThumbnails'], True)
    >>> some_more_re_paths.valid
    False
    """

    def __init__(self, ignored_paths, use_regular_expressions=False):
        """
        :type ignored_paths: List[str]
        :type use_regular_expressions: bool
        """

        self.ignored_paths = ignored_paths
        self.use_regular_expressions = use_regular_expressions

        if ignored_paths and use_regular_expressions:
            self.valid = self._check_and_compile_re()
        else:
            self.re_pattern = None
            self.valid = True

    def scan_this_path(self, path: str) -> bool:
        """
        Returns true if the path should be included in the scan.
        Assumes path is a full path

        :return: True|False

        """
        if not self.ignored_paths:
            return True
        if not self.use_regular_expressions:
            return not path.endswith(tuple(self.ignored_paths))
        return not self.re_pattern.match(path)

    def _check_and_compile_re(self) -> bool:
        """
        Take the ignored paths and attempt to compile a regular expression
        out of them. Checks line by line.

        :return: True if there were no problems creating the regular
        expression pattern
        """

        assert self.use_regular_expressions

        error_encountered = False
        pattern = ''
        for path in self.ignored_paths:
            # check path for validity
            try:
                re.match(path, '')
                pattern += '.*{}s$|'.format(path)
            except re.error:
                logging.error("Ignoring malformed regular expression: {"
                              "}".format(path))
                error_encountered = True

        if pattern:
            pattern = pattern[:-1]

            try:
                self.re_pattern = re.compile(pattern)
            except re.error:
                logging.error('This regular expression is invalid: {'
                              '}'.format(pattern))
                self.re_pattern = None
                error_encountered = True

        logging.debug("Ignored paths regular expression pattern: {}".format(
            pattern))

        return not error_encountered


def today():
    return datetime.date.today().strftime('%Y-%m-%d')

class Preferences:
    rename_defaults = dict(photo_download_folder=xdg_photos_directory(),
                           video_download_folder=xdg_videos_directory(),
                           photo_subfolder=DEFAULT_SUBFOLDER_PREFS,
                           video_subfolder=DEFAULT_VIDEO_SUBFOLDER_PREFS,
                           photo_rename=[FILENAME, NAME_EXTENSION,
                                         ORIGINAL_CASE],
                           video_rename=[FILENAME, NAME_EXTENSION,
                                         ORIGINAL_CASE],
                           day_start="03:00",
                           downloads_today=[today(), '0'],
                           stored_sequence_no=0,
                           strip_characters=True,
                           synchronize_raw_jpg=False,
                           job_codes=[_('New York'), _('Manila'),
                                      _('Prague'),  _('Helsinki'),
                                      _('Wellington'), _('Tehran'),
                                      _('Kampala'),   _('Paris'),
                                      _('Berlin'),  _('Sydney'),
                                      _('Budapest'), _('Rome'),
                                      _('Moscow'),  _('Delhi'), _('Warsaw'),
                                      _('Jakarta'),  _('Madrid'),
                                      _('Stockholm')],
                          )
    device_defaults = dict(only_external_mounts=True,
                           device_autodetection=True,
                           device_location=os.path.expanduser('~'),
                           device_without_dcim_autodetection=False,
                           path_whitelist=[''],
                           path_blacklist=[''],
                           camera_blacklist=[''],
                           ignored_paths=['.Trash', '.thumbnails'],
                           use_re_ignored_paths=False
                          )
    backup_defaults = dict(backup_images=False,
                           backup_device_autodetection=True,
                           photo_backup_identifier=os.path.split(
                               xdg_photos_directory())[1],
                           video_backup_identifier=os.path.split(
                               xdg_videos_directory())[1],
                           backup_photo_location=os.path.expanduser('~'),
                           backup_video_location=os.path.expanduser('~'),
                          )
    automation_defaults = dict(auto_download_at_startup=False,
                               auto_download_upon_device_insertion=False,
                               auto_unmount=False,
                               auto_exit=False,
                               auto_exit_force=False,
                               move=False,
                               verify_file=False
                              )
    performance_defaults = dict(generate_thumbnails=True,
                                thumbnail_quality_lower=False)
    error_defaults = dict(conflict_resolution=constants.SKIP_DOWNLOAD,
                          backup_duplicate_overwrite=False)


    def __init__(self):
        self.settings = QSettings()
        # These next two values must be kept in sync
        dicts = (self.rename_defaults, self.device_defaults,
                 self.backup_defaults, self.automation_defaults,
                 self.performance_defaults, self.error_defaults)
        group_names = ('Rename', 'Device', 'Backup', 'Automation',
                       'Performance', 'ErrorHandling')
        assert len(dicts) == len(group_names)

        # Create quick lookup table for types of each value, including the
        # special case of lists, which use the type of what they contain.
        # While we're at it also merge the dictionaries into one dictionary
        # of default values.
        self.types = {}
        self.defaults = {}
        for d in dicts:
            for key, value in d.items():
                if isinstance(value, list):
                    t = type(value[0])
                else:
                    t = type(value)
                self.types[key] = t
                self.defaults[key] = value
        # Create quick lookup table of the group each key is in
        self.groups = {}
        for idx, d in enumerate(dicts):
            for key in d:
                self.groups[key] = group_names[idx]

    def __getitem__(self, key):
        group = self.groups.get(key, 'General')
        self.settings.beginGroup(group)
        v = self.settings.value(key, self.defaults[key], self.types[key])
        self.settings.endGroup()
        return v

    def __setitem__(self, key, value):
        group = self.groups.get(key, 'General')
        self.settings.beginGroup(group)
        self.settings.setValue(key, value)
        self.settings.endGroup()
