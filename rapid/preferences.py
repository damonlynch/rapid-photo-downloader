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


class ScanPreferences:
    r"""
    Handle user preferences while scanning devices like memory cards, cameras
    or the filesystem

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
                logging.error("Ignoring malformed regular expression: {}".format(path))
                error_encountered = True

        if pattern:
            pattern = pattern[:-1]

            try:
                self.re_pattern = re.compile(pattern)
            except re.error:
                logging.error('This regular expression is invalid: {}'.format(pattern))
                self.re_pattern = None
                error_encountered = True

        logging.debug("Ignored paths regular expression pattern: {}".format(pattern))

        return not error_encountered