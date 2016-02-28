# Copyright (C) 2007-2016 Damon Lynch <damonlynch@gmail.com>

# This file is part of Rapid Photo Downloader.
#
# Rapid Photo Downloader is free software: you can redistribute it and/or
# modify
# it under the terms of the GNU General Public License as published by
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
__copyright__ = "Copyright 2007-2016, Damon Lynch"

import os
import sys
import re
from collections import namedtuple
import random
import string
import tempfile
import logging
import locale
import contextlib
from itertools import groupby
from typing import Optional, List
from datetime import datetime
import time

from gettext import gettext as _

import psutil
import arrow

def available_cpu_count(physical_only=False) -> int:
    """
    Determine the number of CPUs available.

    A CPU is "available" if cpuset has not restricted the number of
    cpus. Portions of this code from
    http://stackoverflow.com/questions/1006289/how-to-find-out-the-number-of-
    cpus-using-python

    :return available CPU count, or 1 if cannot be determined.
     Value guaranteed to be >= 1.
    """

    # cpuset may restrict the number of *available* processors
    available = None
    if sys.platform.startswith('linux'):
        try:
            m = re.search(r'(?m)^Cpus_allowed:\s*(.*)$',
                          open('/proc/self/status').read())
            if m:
                available = bin(int(m.group(1).replace(',', ''), 16)).count('1')
                if available > 0 and not physical_only:
                    return available
        except IOError:
            pass

    if physical_only:
        physical = psutil.cpu_count(logical=False)
        if physical is not None:
            if available is not None:
                return min(available, physical)
            return physical

    c = os.cpu_count()
    if c is not None:
        return max(c, 1)
    c = psutil.cpu_count()
    if c is not None:
        return max(c, 1)
    else:
        return 1

def confirm(prompt: str=None, resp: bool=False) -> bool:
    r"""
    Prompts for yes or no response from the user.

    :param prompt: prompt displayed to user
    :param resp: the default value assumed by the caller when user
     simply types ENTER.
    :return: True for yes and False for no.
    """

    # >>> confirm(prompt='Create Directory?', resp=True)
    # Create Directory? [y]|n:
    # True
    # >>> confirm(prompt='Create Directory?', resp=False)
    # Create Directory? [n]|y:
    # False
    # >>> confirm(prompt='Create Directory?', resp=False)
    # Create Directory? [n]|y: y
    # True

    if prompt is None:
        prompt = 'Confirm'

    if resp:
        prompt = '%s [%s]|%s: ' % (prompt, 'y', 'n')
    else:
        prompt = '%s [%s]|%s: ' % (prompt, 'n', 'y')

    while True:
        ans = input(prompt)
        if not ans:
            return resp
        if ans not in ['y', 'Y', 'n', 'N']:
            print('please enter y or n.')
            continue
        return ans in ['y', 'Y']


@contextlib.contextmanager
def stdchannel_redirected(stdchannel, dest_filename):
    """
    A context manager to temporarily redirect stdout or stderr

    Usage:
    with stdchannel_redirected(sys.stderr, os.devnull):
       do_work()

    Source:
    http://marc-abramowitz.com/archives/2013/07/19/python-context-manager-for-redirected-stdout-and-stderr/
    """
    oldstdchannel = dest_file = None
    try:
        oldstdchannel = os.dup(stdchannel.fileno())
        dest_file = open(dest_filename, 'w')
        os.dup2(dest_file.fileno(), stdchannel.fileno())
        yield
    finally:
        if oldstdchannel is not None:
            os.dup2(oldstdchannel, stdchannel.fileno())
        if dest_file is not None:
            dest_file.close()

@contextlib.contextmanager
def show_errors():
    yield

suffixes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']

def format_size_for_user(size_in_bytes: int, 
                         zero_string: str='', 
                         no_decimals: int=2) -> str:
    r"""
    Humanize display of bytes.

    Uses Microsoft style i.e. 1000 Bytes = 1 KB

    :param size: size in bytes
    :param zero_string: string to use if size == 0

    >>> format_size_for_user(0)
    ''
    >>> format_size_for_user(1)
    '1 B'
    >>> format_size_for_user(123)
    '123 B'
    >>> format_size_for_user(1000)
    '1 KB'
    >>> format_size_for_user(1024)
    '1.02 KB'
    >>> format_size_for_user(1024, no_decimals=0)
    '1 KB'
    >>> format_size_for_user(1100, no_decimals=2)
    '1.1 KB'
    >>> format_size_for_user(1000000, no_decimals=2)
    '1 MB'
    >>> format_size_for_user(1000001, no_decimals=2)
    '1 MB'
    >>> format_size_for_user(1020001, no_decimals=2)
    '1.02 MB'
    """

    if size_in_bytes == 0: return zero_string
    i = 0
    while size_in_bytes >= 1000 and i < len(suffixes)-1:
        size_in_bytes /= 1000
        i += 1

    if no_decimals:
        s = '{:.{prec}f}'.format(size_in_bytes, prec=no_decimals).rstrip('0').rstrip('.')
    else:
        s = '{:.0f}'.format(size_in_bytes)
    return s + ' ' + suffixes[i]

def divide_list(source: list, no_pieces: int) -> list:
    r"""
    Returns a list containing no_pieces lists, with the items
    of the original list evenly distributed
    :param source: the list to divide
    :param no_pieces: the nubmer of pieces the lists
    :return: the new list

    >>> divide_list(list(range(12)), 4)
    [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9, 10, 11]]
    >>> divide_list(list(range(11)), 4)
    [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9, 10]]
    """
    source_size = len(source)
    slice_size = source_size // no_pieces
    remainder = source_size % no_pieces
    result = []

    extra = 0
    for i in range(no_pieces):
        start = i * slice_size + extra
        source_slice = source[start:start + slice_size]
        if remainder:
            source_slice += [source[start + slice_size]]
            remainder -= 1
            extra += 1
        result.append(source_slice)
    return result

def divide_list_on_length(source: List, length: int) -> List:

    r"""
    Break a list into lists no longer than length.

    >>> l=list(range(11))
    >>> divide_list_on_length(l, 3)
    [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9, 10]]
    >>> l=list(range(12))
    >>> divide_list_on_length(l, 3)
    [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9, 10, 11]]
    """

    return [source[i:i+length] for i in range(0, len(source), length)]

def addPushButtonLabelSpacer(s: str) -> str:
    return ' ' + s


class GenerateRandomFileName:
    def __init__(self):
        # the characters used to generate temporary filenames
        self.filename_characters = list(string.ascii_letters + string.digits)

    def name(self, extension: str=None) -> str:
        """

        :return: filename 5 characters long without any extension
        """
        if extension is not None:
            return '{}.{}'.format(''.join(
                random.sample(self.filename_characters, 5)),
                extension)
        else:
            return ''.join(random.sample(self.filename_characters, 5))


TempDirs = namedtuple('TempDirs', 'photo_temp_dir, video_temp_dir')
CacheDirs = namedtuple('CacheDirs', 'photo_cache_dir, video_cache_dir')

def create_temp_dir(folder: str, prefix=None) -> str:
    """
    Creates a temporary director and logs errors
    :param folder: the folder in which the temporary directory should
     be created
    :param prefix: any name the directory should start with
    :type prefix: str
    :return: full path of the temporary directory
    """
    if prefix is None:
        prefix = "rpd-tmp-"
    try:
        temp_dir = tempfile.mkdtemp(prefix=prefix, dir=folder)
    except OSError as inst:
        msg = "Failed to create temporary directory in %s: %s %s" % (
                      folder,
                      inst.errno,
                      inst.strerror)
        logging.critical(msg)
        temp_dir = None
    return temp_dir

def create_temp_dirs(photo_download_folder: str,
                     video_download_folder: str) -> TempDirs:
    """
    Create pair of temporary directories for photo and video download
    :param photo_download_folder: where photos will be downloaded to
    :param video_download_folder: where videos will be downloaded to
    :return: the directories
    """
    photo_temp_dir = video_temp_dir = None
    if photo_download_folder is not None:
        photo_temp_dir = create_temp_dir(photo_download_folder)
        logging.debug("Photo temporary directory: %s", photo_temp_dir)
    if video_download_folder is not None:
        video_temp_dir = create_temp_dir(video_download_folder)
        logging.debug("Video temporary directory: %s", video_temp_dir)
    return TempDirs(photo_temp_dir, video_temp_dir)

def same_file_system(file1: str, file2: str) -> bool:
    """
    Returns True if the files / directories are on the same filesystem
    :param file1: first file / directory to check
    :param file2: second file / directory to check
    :return: True if the same file system, else false
    """
    dev1 = os.stat(file1).st_dev
    dev2 = os.stat(file2).st_dev
    return dev1 == dev2

def make_internationalized_list(items) -> str:
    r"""
    Makes a string of items conforming to i18n

    >>> print(make_internationalized_list([]))
    <BLANKLINE>
    >>> print(make_internationalized_list(['one']))
    one
    >>> print(make_internationalized_list(['one', 'two']))
    one and two
    >>> print(make_internationalized_list(['one', 'two', 'three']))
    one, two and three
    >>> print(make_internationalized_list(['one', 'two', 'three', 'four']))
    one, two, three and four

    Loosely follows the guideline here:
    http://cldr.unicode.org/translation/lists

    :param items: the list of items to make a string out of
    :return: internationalized string
    """
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        # two things in a list e.g. "device1 and device2"
        return _('%(first_item)s and %(last_item)s') % dict(
            first_item=items[0], last_item=items[1])
    if len(items) > 2:
        s = items[0]
        for item in items[1:-1]:
            # the middle of a list of things
            s =  '%(first_items)s, %(last_items)s'% dict(first_items=s,
                                                         last_items=item)
        # the end of a list of things
        s = '%(start_items)s and %(last_item)s' % dict(start_items=s,
                                                       last_item=items[-1])
        return s
    return ''

def thousands(i: int) -> str:
    """
    Add a thousands seperator (or its locale equivalent) to an
    integer. Assumes the module level locale setting has already been
    set.
    :param i: the integer e.g. 1000
    :return: string with seperators e.g. '1,000'
    """
    try:
        return locale.format("%d", i, grouping=True)
    except TypeError:
        return i


# Source of class AdjacentKey, first_and_last and runs:
# http://stupidpythonideas.blogspot.com/2014/01/grouping-into-runs-of-adjacent-values.html
class AdjacentKey:
    r"""
    >>> [list(g) for k, g in groupby([0, 1, 2, 3, 5, 6, 7, 10, 11, 13, 16], AdjacentKey)]
    [[0, 1, 2, 3], [5, 6, 7], [10, 11], [13], [16]]
    """
    __slots__ = ['obj']

    def __init__(self, obj) -> None:
        self.obj = obj

    def __eq__(self, other) -> bool:
        ret = self.obj - 1 <= other.obj <= self.obj + 1
        if ret:
            self.obj = other.obj
        return ret


def first_and_last(iterable):
    start = end = next(iterable)
    for end in iterable: pass
    return start, end

def runs(iterable):
    r"""
    >>> list(runs([0, 1, 2, 3, 5, 6, 7, 10, 11, 13, 16]))
    [(0, 3), (5, 7), (10, 11), (13, 13), (16, 16)]
    >>> list(runs([0]))
    [(0, 0)]
    >>> list(runs([0, 1, 10, 100, 101]))
    [(0, 1), (10, 10), (100, 101)]
    """

    for k, g in groupby(iterable, AdjacentKey):
        yield first_and_last(g)

numbers = namedtuple('numbers', 'number, plural')

long_numbers = {
    1: _('one'),
    2: _('two'),
    3: _('three'),
    4: _('four'),
    5: _('five'),
    6: _('six'),
    7: _('seven'),
    8: _('eight'),
    9: _('nine'),
    10: _('ten'),
    11: _('eleven'),
    12: _('twelve'),
    13: _('thirteen'),
    14: _('fourteen'),
    15: _('fifteen'),
    16: _('sixteen'),
    17: _('seventeen'),
    18: _('eighteen'),
    19: _('ninenteen'),
    20: _('twenty')
}

def number(value: int) -> numbers:
    r"""
    Convert integer to written form, e.g. one, two, etc.

    Will propagate TypeError or KeyError on
    failure.

    >>> number(1)
    numbers(number='one', plural=False)
    >>> number(2)
    numbers(number='two', plural=True)
    >>> number(10)
    numbers(number='ten', plural=True)
    >>> number(20)
    numbers(number='twenty', plural=True)
    >>>

    :param value: int between 1 and 20
    :return: tuple of str and whether it is plural
    """

    plural = value > 1
    text = long_numbers[value]
    return numbers(text, plural)

def datetime_roughly_equal(dt1: datetime, dt2: datetime, seconds: int=60) -> bool:
    r"""
    Check to see if date times are equal, give or take n seconds
    :param dt1: python datetime to check
    :param dt2:python datetime to check
    :param seconds: number of seconds leeway
    :return: True if "equal", False otherwise

    >>> dt1 = datetime.now()
    >>> time.sleep(.1)
    >>> dt2 = datetime.now()
    >>> datetime_roughly_equal(dt1, dt2, 1)
    True
    """

    at1 = arrow.get(dt1)
    at2 = arrow.get(dt2)
    return at1.replace(seconds=-seconds) < at2 < at1.replace(seconds=+seconds)