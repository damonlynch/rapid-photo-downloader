__author__ = 'Damon Lynch'

# Copyright (C) 2007-2015 Damon Lynch <damonlynch@gmail.com>

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

import os
import sys
import re
import distutils.version
from collections import namedtuple
import random
import string
import tempfile
import logging
import locale
from gettext import gettext as _

import psutil


logging.basicConfig(format='%(levelname)s:%(asctime)s:%(message)s',
                    datefmt='%H:%M:%S',
                    level=logging.DEBUG)

def available_cpu_count():
    """
    Number of available virtual or physical CPUs on this system, i.e.
    user/real as output by time(1) when called with an optimally scaling
    userspace-only program

    http://stackoverflow.com/questions/1006289/how-to-find-out-the-number-of-
    cpus-using-python
    """

    # cpuset may restrict the number of *available* processors
    if sys.platform.startswith('linux'):
        try:
            m = re.search(r'(?m)^Cpus_allowed:\s*(.*)$',
                          open('/proc/self/status').read())
            if m:
                res = bin(int(m.group(1).replace(',', ''), 16)).count('1')
                if res > 0:
                    return res
        except IOError:
            pass

    c = os.cpu_count()
    if c is not None:
        return c
    try:
        return psutil.cpu_count()
    except:
        return 1

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

def divide_list_on_length(source: list, length: int) -> list:
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
    Add a thousands seperator (or it's locale equivalent) to an
    integer. Assumes the module leve locale setting has already been
    set.
    :param i: the integer e.g. 1000
    :return: string with seperators e.g. '1,000'
    """
    try:
        return locale.format("%d", i, grouping=True)
    except TypeError:
        return i

def pythonify_version(v):
    """ makes version number a version number in distutils sense"""
    return distutils.version.StrictVersion(v.replace( '~',''))
    
def human_readable_version(v: str) -> str:
    """
    returns a version in human readable form"""
    v = v.replace('~a', ' alpha ')
    v = v.replace('~b', ' beta ')
    v = v.replace('~rc', ' RC ')
    return v
        
