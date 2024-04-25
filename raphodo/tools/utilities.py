# SPDX-FileCopyrightText: Copyright 2007-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

import contextlib
import ctypes
import locale
import logging
import os
import random
import re
import signal
import string
import struct
import sys
import tarfile
import tempfile
from collections import defaultdict, namedtuple
from datetime import datetime
from glob import glob
from importlib.resources import files
from itertools import groupby
from pathlib import Path

import arrow
import babel
import psutil
from packaging.version import parse
from PyQt5.QtCore import QLibraryInfo, QSize, QStandardPaths, QTranslator

import raphodo.__about__ as __about__
from raphodo.internationalisation.install import i18n_domain, install_gettext, localedir

install_gettext()

# Linux specific code to ensure child processes exit when parent dies
# See http://stackoverflow.com/questions/19447603/
# how-to-kill-a-python-child-process-created-with-subprocess-check-output-when-t/
libc = ctypes.CDLL("libc.so.6")


def set_pdeathsig(sig=signal.SIGTERM):
    def callable():
        return libc.prctl(1, sig)

    return callable


def data_file_path(data_file: str) -> str:
    """
    Returns the location on the file system of a data file
    :param data_file: relative path to a file found within the data directory
    :return: the absolute path to the data file
    """

    return str((files("raphodo") / "data").joinpath(data_file))


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
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/self/status") as status_file:
                status = status_file.read()
        except OSError:
            pass
        else:
            m = re.search(r"(?m)^Cpus_allowed:\s*(.*)$", status)
            if m:
                available = bin(int(m.group(1).replace(",", ""), 16)).count("1")
                if available > 0 and not physical_only:
                    return available

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


def default_thumbnail_process_count() -> int:
    num_system_cores = max(available_cpu_count(physical_only=True), 2)
    return min(num_system_cores, 8)


def confirm(prompt: str | None = None, resp: bool | None = False) -> bool:
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
        prompt = "Confirm"

    prompt = f"{prompt} [y]|n: " if resp else f"{prompt} [n]|y: "

    while True:
        ans = input(prompt)
        if not ans:
            return resp
        if ans not in ["y", "Y", "n", "N"]:
            print("please enter y or n.")
            continue
        return ans in ["y", "Y"]


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
        dest_file = open(dest_filename, "w")  # noqa: SIM115
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


# Translators: these values are file size suffixes like B representing bytes, KB
# representing kilobytes, etc.
suffixes = [
    _("B"),
    _("KB"),
    _("MB"),
    _("GB"),
    _("TB"),
    _("PB"),
    _("EB"),
    _("ZB"),
    _("YB"),
]


def format_size_for_user(
    size_in_bytes: int, zero_string: str = "", no_decimals: int = 2
) -> str:
    r"""
    Humanize display of bytes.

    Uses Microsoft style i.e. 1000 Bytes = 1 KB

    :param size: size in bytes
    :param zero_string: string to use if size == 0

    >>> locale.setlocale(locale.LC_ALL, ('en_US', 'utf-8'))
    'en_US.UTF-8'
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

    if size_in_bytes == 0:
        return zero_string
    i = 0
    while size_in_bytes >= 1000 and i < len(suffixes) - 1:
        size_in_bytes /= 1000
        i += 1

    if no_decimals:
        s = (
            "{:.{prec}f}".format(size_in_bytes, prec=no_decimals)
            .rstrip("0")
            .rstrip(".")
        )
    else:
        s = f"{size_in_bytes:.0f}"
    return s + " " + suffixes[i]


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
        source_slice = source[start : start + slice_size]
        if remainder:
            source_slice += [source[start + slice_size]]
            remainder -= 1
            extra += 1
        result.append(source_slice)
    return result


def divide_list_on_length(source: list[int], length: int) -> list[list[int]]:
    r"""
    Break a list into lists no longer than length.

    >>> li=list(range(11))
    >>> divide_list_on_length(li, 3)
    [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9, 10]]
    >>> li=list(range(12))
    >>> divide_list_on_length(li, 3)
    [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9, 10, 11]]
    """

    return [source[i : i + length] for i in range(0, len(source), length)]


def addPushButtonLabelSpacer(s: str) -> str:
    return " " + s


class GenerateRandomFileName:
    def __init__(self):
        # the characters used to generate temporary file names
        self.file_name_characters = list(string.ascii_letters + string.digits)

    def name(self, extension: str = None) -> str:
        """
        :param extension: if included, random file name will include the
         file extension
        :return: file name 5 characters long with or without extension
        """
        if extension is not None:
            return "{}.{}".format(
                "".join(random.sample(self.file_name_characters, 5)), extension
            )
        else:
            return "".join(random.sample(self.file_name_characters, 5))


TempDirs = namedtuple("TempDirs", "photo_temp_dir, video_temp_dir")
CacheDirs = namedtuple("CacheDirs", "photo_cache_dir, video_cache_dir")


def create_temp_dir(
    folder: str | None = None,
    prefix: str | None = None,
    force_no_prefix: bool = False,
    temp_dir_name: str | None = None,
) -> str:
    """
    Creates a temporary director and logs errors
    :param folder: the folder in which the temporary directory should
     be created. If not specified, uses the tempfile.mkstemp default.
    :param prefix: any name the directory should start with. If None,
     default rpd-tmp will be used as prefix, unless force_no_prefix
     is True
    :param force_no_prefix: if True, a directory prefix will never
     be used
    :param temp_dir_name: if specified, create the temporary directory
     using this actual name. If it already exists, add a suffix.
    :return: full path of the temporary directory
    """

    if temp_dir_name:
        if folder is None:
            folder = tempfile.gettempdir()
        for i in range(10):
            if i == 0:
                path = os.path.join(folder, temp_dir_name)
            else:
                path = os.path.join(folder, f"{temp_dir_name}_{i}")
            try:
                os.mkdir(path=path, mode=0o700)
            except FileExistsError:
                logging.warning("Failed to create temporary directory %s", path)
            else:
                break
        return path
    else:
        if prefix is None and not force_no_prefix:
            prefix = "rpd-tmp-"
        try:
            temp_dir = tempfile.mkdtemp(prefix=prefix, dir=folder)
        except OSError as inst:
            msg = (
                f"Failed to create temporary directory in {folder}: "
                f"{inst.errno} {inst.strerror}"
            )
            logging.critical(msg)
            temp_dir = None
    return temp_dir


def create_temp_dirs(
    photo_download_folder: str, video_download_folder: str
) -> TempDirs:
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


def same_device(file1: str, file2: str) -> bool:
    """
    Returns True if the files / directories are on the same device (partition).

    No error checking.

    :param file1: first file / directory to check
    :param file2: second file / directory to check
    :return: True if the same file system, else false
    """

    dev1 = os.stat(file1).st_dev
    dev2 = os.stat(file2).st_dev
    return dev1 == dev2


def find_mount_point(path: str) -> str:
    """
    Find the mount point of a path
    See:
    http://stackoverflow.com/questions/4453602/how-to-find-the-mountpoint-a-file-resides-on

    >>> print(find_mount_point('/crazy/path'))
    /

    :param path:
    :return:
    """
    path = os.path.realpath(path)
    while not os.path.ismount(path):
        path = os.path.dirname(path)
    return path


# Source of class AdjacentKey, first_and_last and runs:
# http://stupidpythonideas.blogspot.com/2014/01/grouping-into-runs-of-adjacent-values.html
class AdjacentKey:
    r"""
    >>> example = [0, 1, 2, 3, 5, 6, 7, 10, 11, 13, 16]
    >>> [list(g) for k, g in groupby(example, AdjacentKey)]
    [[0, 1, 2, 3], [5, 6, 7], [10, 11], [13], [16]]
    """

    __slots__ = ["obj"]

    def __init__(self, obj) -> None:
        self.obj = obj

    def __eq__(self, other) -> bool:
        ret = self.obj - 1 <= other.obj <= self.obj + 1
        if ret:
            self.obj = other.obj
        return ret


def first_and_last(iterable):
    start = end = next(iterable)
    for end in iterable:
        pass
    return start, end


def runs(iterable):
    r"""
    identify adjacent elements in pre-sorted data

    :param iterable: sorted data

    >>> list(runs([0, 1, 2, 3, 5, 6, 7, 10, 11, 13, 16]))
    [(0, 3), (5, 7), (10, 11), (13, 13), (16, 16)]
    >>> list(runs([0]))
    [(0, 0)]
    >>> list(runs([0, 1, 10, 100, 101]))
    [(0, 1), (10, 10), (100, 101)]
    """

    for k, g in groupby(iterable, AdjacentKey):
        yield first_and_last(g)


numbers = namedtuple("numbers", "number, plural")

long_numbers = {
    1: _("one"),
    2: _("two"),
    3: _("three"),
    4: _("four"),
    5: _("five"),
    6: _("six"),
    7: _("seven"),
    8: _("eight"),
    9: _("nine"),
    10: _("ten"),
    11: _("eleven"),
    12: _("twelve"),
    13: _("thirteen"),
    14: _("fourteen"),
    15: _("fifteen"),
    16: _("sixteen"),
    17: _("seventeen"),
    18: _("eighteen"),
    19: _("ninenteen"),
    20: _("twenty"),
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


def datetime_roughly_equal(
    dt1: datetime | float, dt2: datetime | float, seconds: int = 120
) -> bool:
    r"""
    Check to see if date times are equal, give or take n seconds
    :param dt1: python datetime, or timestamp, to check
    :param dt2:python datetime, or timestamp to check
    :param seconds: number of seconds leeway
    :return: True if "equal", False otherwise

    >>> dt1 = datetime.now()
    >>> time.sleep(.1)
    >>> dt2 = datetime.now()
    >>> datetime_roughly_equal(dt1, dt2, 1)
    True
    >>> dt1 = 1458561776.0
    >>> dt2 = 1458561776.0
    >>> datetime_roughly_equal(dt1, dt2, 120)
    True
    >>> dt2 += 450
    >>> datetime_roughly_equal(dt1, dt2, 120)
    False
    >>> datetime_roughly_equal(dt1, dt2, 500)
    True
    """

    # arrow.get from time stamp gives UTC time
    at1 = arrow.get(dt1)
    at2 = arrow.get(dt2)
    return at1.shift(seconds=-seconds) < at2 < at1.shift(seconds=+seconds)


def process_running(process_name: str, partial_name: bool = True) -> bool:
    """
    Search the list of the system's running processes to see if a process with this
    name is running

    :param process_name: the name of the process to search for
    :param partial_name: if True, the process_name argument can be a
     partial match
    :return: True if found, else False
    """

    for proc in psutil.process_iter():
        try:
            name = proc.name()
        except psutil.NoSuchProcess:
            pass
        else:
            if partial_name:
                if name.find(process_name) >= 0:
                    return True
            else:
                if name == process_name:
                    return True
    return False


def make_html_path_non_breaking(path: str) -> str:
    """
    When /some/path is displayed in rich text, it will be word-wrapped on the
    slashes. Inhibit that using a special unicode character.

    :param path: the path
    :return: the path containing the special characters
    """

    return path.replace(os.sep, f"{os.sep}&#8288;")


def remove_last_char_from_list_str(items: list[str]) -> list[str]:
    r"""
    Remove the last character from a list of strings, modifying the list in place,
    such that the last item is never empty

    :param items: the list to modify
    :return: in place copy

    >>> remove_last_char_from_list_str([' abc', 'def', 'ghi'])
    [' abc', 'def', 'gh']
    >>> remove_last_char_from_list_str([' abc', 'def', 'gh'] )
    [' abc', 'def', 'g']
    >>> remove_last_char_from_list_str([' abc', 'def', 'g'] )
    [' abc', 'def']
    >>> remove_last_char_from_list_str([' a'])
    [' ']
    >>> remove_last_char_from_list_str([' '])
    []
    >>> remove_last_char_from_list_str([])
    []
    """
    if items:
        if not items[-1]:
            items = items[:-1]
        else:
            items[-1] = items[-1][:-1]
            if items and not items[-1]:
                items = items[:-1]
    return items


def platform_c_maxint() -> int:
    """
    See http://stackoverflow.com/questions/13795758/what-is-sys-maxint-in-python-3

    :return: the maximum size of an int in C when compiled the same way Python was
    """
    return 2 ** (struct.Struct("i").size * 8 - 1) - 1


def _recursive_identify_depth(*paths, depth) -> int:
    basenames = [os.path.basename(path) for path in paths]
    if len(basenames) != len(set(basenames)):
        duplicates = _collect_duplicates(basenames, paths)

        for basename in duplicates:
            chop = len(basename) + 1
            chopped = (path[:-chop] for path in duplicates[basename])
            depth = max(depth, _recursive_identify_depth(*chopped, depth=depth + 1))
    return depth


def _collect_duplicates(basenames, paths):
    duplicates = defaultdict(list)
    for basename, path in zip(basenames, paths):
        duplicates[basename].append(path)
    return {basename: paths for basename, paths in duplicates.items() if len(paths) > 1}


def make_path_end_snippets_unique(*paths) -> list[str]:
    r"""
    Make list of path ends unique given possible common path endings.

    A snippet starts from the end of the path, in extreme cases possibly up the path
    start.

    :param paths: sequence of paths to generate unique end snippets for
    :return: list of unique snippets

    >>> p0 = '/home/damon/photos'
    >>> p1 = '/media/damon/backup1/photos'
    >>> p2 = '/media/damon/backup2/photos'
    >>> p3 = '/home/damon/videos'
    >>> p4 = '/media/damon/backup1/videos'
    >>> p5 = '/media/damon/backup2/videos'
    >>> p6 = '/media/damon/drive1/home/damon/photos'
    >>> s0 = make_path_end_snippets_unique(p0, p3)
    >>> print(s0)
    ['photos', 'videos']
    >>> s1 = make_path_end_snippets_unique(p0, p1, p2)
    >>> print(s1)
    ['damon/photos', 'backup1/photos', 'backup2/photos']
    >>> s2 = make_path_end_snippets_unique(p0, p1, p2, p3)
    >>> print(s2)
    ['damon/photos', 'backup1/photos', 'backup2/photos', 'videos']
    >>> s3 = make_path_end_snippets_unique(p3, p4, p5)
    >>> print(s3)
    ['damon/videos', 'backup1/videos', 'backup2/videos']
    >>> s4 = make_path_end_snippets_unique(p0, p1, p2, p3, p6)
    >>> print(s4) #doctest: +NORMALIZE_WHITESPACE
    ['/home/damon/photos', '/media/damon/backup1/photos', '/media/damon/backup2/photos',
     'videos', 'drive1/home/damon/photos']
    >>> s5 = make_path_end_snippets_unique(p1, p2, p3, p6)
    >>> print(s5)
    ['backup1/photos', 'backup2/photos', 'videos', 'damon/photos']
    """

    basenames = [os.path.basename(path) for path in paths]

    if len(basenames) != len(set(basenames)):
        names = []
        depths = defaultdict(int)
        duplicates = _collect_duplicates(basenames, paths)

        for basename, path in zip(basenames, paths):
            if basename in duplicates:
                depths[basename] = _recursive_identify_depth(
                    *duplicates[basename], depth=0
                )

        for basename, path in zip(basenames, paths):
            depth = depths[basename]
            if depth:
                dirs = path.split(os.sep)
                index = len(dirs) - depth - 1
                name = os.sep.join(dirs[max(index, 0) :])
                if index > 1:
                    pass
                    # name = '...' + name
                elif index == 1:
                    name = os.sep + name
            else:
                name = basename
            names.append(name)
        return names
    else:
        return basenames


have_logged_os_release = False


def log_os_release() -> None:
    """
    Log the entired contents of /etc/os-release, but only if
    we didn't do so already.
    """

    global have_logged_os_release

    if not have_logged_os_release:
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    logging.debug(line.rstrip("\n"))
        except Exception:
            pass
        have_logged_os_release = True


def bug_report_full_tar_path() -> str:
    """
    Generate a full path for a compressed bug report tar file.
    The filename will not already exist.

    :return: File name including path
    """

    filename = "rpd-bug-report-{}".format(datetime.now().strftime("%Y%m%d"))
    component = os.path.join(os.path.expanduser("~"), filename)

    i = 0
    while os.path.isfile(f"{component}{'' if not i else f'-{i}'}.tar.gz"):
        i += 1

    return f"{component}{'' if not i else f'-{i}'}.tar.gz"


def create_bugreport_tar(
    full_tar_name: str,
    log_path: str | None = "",
    full_config_file: str | None = "",
) -> bool:
    """
    Create a tar file containing log and configuration files.

    If the file already exists, do nothing.

    :param full_tar_name: the full path in which to create the tar file
    :param log_path: path to the log files
    :param full_config_file: the full path and file of the configuration file
    :return: True if tar file created, else False
    """

    if os.path.isfile(full_tar_name):
        logging.error("Cannot create bug report tarfile, because it already exists")
        return False

    if not log_path:
        log_path = os.path.join(
            QStandardPaths.writableLocation(QStandardPaths.GenericCacheLocation),
            "rapid-photo-downloader",
            "log",
        )

    if not full_config_file:
        config_dir = os.path.join(
            QStandardPaths.writableLocation(QStandardPaths.GenericConfigLocation),
            "Rapid Photo Downloader",
        )
        config_file = "Rapid Photo Downloader.conf"
    else:
        config_dir, config_file = os.path.split(full_config_file)

    curr_dir = os.getcwd()
    created = False

    try:
        with tarfile.open(full_tar_name, "x:gz") as t:
            os.chdir(log_path)
            for li in glob("*"):
                t.add(
                    li,
                    "rapid-photo-downloader.0.log"
                    if li == "rapid-photo-downloader.log"
                    else li,
                )
            os.chdir(config_dir)
            t.add(config_file)
    except FileNotFoundError as e:
        logging.error(
            "When creating a bug report tar file, the directory or file %s does "
            "not exist",
            e.filename,
        )
    except Exception:
        logging.exception("Unexpected error when creating bug report tar file")
    else:
        created = True

    with contextlib.suppress(FileNotFoundError):
        os.chdir(curr_dir)

    return created


def current_version_is_dev_version(current_version=None) -> bool:
    if current_version is None:
        current_version = parse(__about__.__version__)
    return current_version.is_prerelease


def remove_topmost_directory_from_path(path: str) -> str:
    if os.sep not in path:
        return path
    return path[path[1:].find(os.sep) + 1 :]


def arrow_locale(lang: str) -> str:
    """
    Test if locale is suitable for use with Arrow.
    :return: Return user locale if it works with Arrow, else Arrow default ('en_us')
    """

    default = "en_us"
    if not lang:
        try:
            lang = locale.getdefaultlocale()[0]
        except Exception:
            return default

    try:
        arrow.locales.get_locale(lang)
        return lang
    except (ValueError, AttributeError):
        return default


def letters(x: int) -> str:
    """
    Return a letter representation of a positive number.

    Adapted from algorithm at
    http://en.wikipedia.org/wiki/Hexavigesimal

    >>> letters(0)
    'a'
    >>> letters(1)
    'b'
    >>> letters(2)
    'c'
    >>> letters(25)
    'z'
    >>> letters(26)
    'aa'
    >>> letters(27)
    'ab'
    >>> letters(28)
    'ac'
    """

    v = ""
    while x > 25:
        r = x % 26
        x = x // 26 - 1
        v = string.ascii_lowercase[r] + v
    v = string.ascii_lowercase[x] + v

    return v


# Use to extract time zone information from date / times:
_flexible_dt_re = re.compile(
    r"""(?P<year>\d{4})[:-](?P<month>\d{2})[:-](?P<day>\d{2})
        [\sT]  # separator between date and time
        (?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})
        (?P<subsecond>\.\d{2})?
        (?P<timezone>([+-])\d{2}:\d{2})?
        (?P<dst>\s(DST))?""",
    re.VERBOSE,
)


def flexible_date_time_parser(dt_string: str) -> tuple[datetime, str]:
    r"""
    Use regular expresion to parse exif date time value, and attempt
    to convert it to a python date time.
    No error checking.

    :param dt_string: date time from exif in string format
    :return: datetime, may or may not have a time zone, and format string

    >>> flexible_date_time_parser('2018:09:03 14:00:13+01:00 DST')
    ... # doctest: +NORMALIZE_WHITESPACE
    datetime.datetime(2018, 9, 3, 14, 0, 13, tzinfo=datetime.timezone(
    datetime.timedelta(0, 3600)))
    >>> flexible_date_time_parser('2010:07:18 01:53:35')
    datetime.datetime(2010, 7, 18, 1, 53, 35)
    >>> flexible_date_time_parser('2016:02:27 22:18:03.00')
    datetime.datetime(2016, 2, 27, 22, 18, 3)
    >>> flexible_date_time_parser('2010:05:25 17:43:16+02:00')
    ... # doctest: +NORMALIZE_WHITESPACE
    datetime.datetime(2010, 5, 25, 17, 43, 16, tzinfo=datetime.timezone(
    datetime.timedelta(0, 7200)))
    >>> flexible_date_time_parser('2010:06:07 14:14:02+00:00')
    datetime.datetime(2010, 6, 7, 14, 14, 2, tzinfo=datetime.timezone.utc)
    >>> flexible_date_time_parser('2016-11-25T14:31:24')
    datetime.datetime(2016, 11, 25, 14, 31, 24)
    >>> flexible_date_time_parser('2016-11-25T14:20:09')
    datetime.datetime(2016, 11, 25, 14, 20, 9)
    """

    match = _flexible_dt_re.match(dt_string)
    assert match
    m = match.groupdict()

    dte = "{}:{}:{} {}:{}:{}".format(
        m["year"], m["month"], m["day"], m["hour"], m["minute"], m["second"]
    )

    fs = "%Y:%m:%d %H:%M:%S"  # format string

    ss = m["subsecond"]
    if ss:
        dte = f"{dte}{ss}"
        fs = f"{fs}.%f"

    tze = m["timezone"]
    if tze:
        dte = f"{dte}{tze.replace(':', '')}"
        fs = f"{fs}%z"

    # dst: daylight savings
    # no idea how to handle this properly -- so ignore for now!

    return datetime.strptime(dte, fs), fs


def image_large_enough_fdo(size: QSize) -> bool:
    """
    :param size: image size
    :return: True if image is large enough to meet the FreeDesktop.org
     specs for a large thumbnail
    """

    return size.width() >= 256 or size.height() >= 256


def is_venv():
    """
    :return: True if the python interpreter is running in venv or virtualenv
    """

    return hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    )


def available_lang_codes() -> list[str]:
    """
    Detect translations that exist for Rapid Photo Downloader
    :return: list of language codes
    """

    if localedir is not None:
        files = glob(os.path.join(localedir, "*", "LC_MESSAGES", "%s.mo" % i18n_domain))
        langs = [file.split(os.path.sep)[-3] for file in files]
        langs.append("en")
        return langs
    else:
        return []


# Auto-generated from extract_language_names.py do not delete
substitute_languages = {
    "fa": "Persian",
    "sk": "Slovak",
    "it": "Italian",
    "oc": "Occitan (post 1500)",
    "fi": "Finnish",
    "sv": "Swedish",
    "cs": "Czech",
    "pl": "Polish",
    "kab": "Kabyle",
    "tr": "Turkish",
    "hr": "Croatian",
    "nn": "Norwegian Nynorsk",
    "da": "Danish",
    "de": "German",
    "sr": "српски",
    "pt_BR": "Brazilian Portuguese",
    "ja": "Japanese",
    "bg": "Bulgarian",
    "uk": "Ukrainian",
    "ar": "Arabic",
    "ca": "Catalan",
    "nb": "Norwegian Bokmal",
    "ru": "Russian",
    "hu": "magyar",
    "be": "Belarusian",
    "es": "Spanish",
    "pt": "Portuguese",
    "zh_CN": "Chinese (Simplified)",
    "fr": "Français",
    "et": "Estonian",
    "nl": "Dutch",
    "ro": "Romanian",
    "id": "Indonesian",
    "el": "Greek",
}  # Auto-generated from extract_language_names.py do not delete


def get_language_display_name(
    lang_code: str, make_missing_lower: bool, locale_code: str
) -> str:
    """
    Use babel to the human friendly name for a locale, or failing that our
    auto-generated version
    :param lang_code: locale code for language to get the display name for
    :param make_missing_lower: whether to make the default name when
     babel does not suppply it lower case
    :param locale_code: current system locale code
    :return: human friendly version
    """

    try:
        return babel.Locale.parse(lang_code).get_display_name(locale_code)
    except babel.core.UnknownLocaleError:
        display = substitute_languages[lang_code]
        return display if not make_missing_lower else display.lower()


def available_languages(display_locale_code: str = "") -> list[tuple[str, str]]:
    """
    Detect translations that exist for Rapid Photo Downloader
    :return: iterator of Tuple of language code and localized name
    """

    lang_codes = available_lang_codes()

    if not lang_codes:  # Testing code when translations are not installed
        lang_codes = ["en", "de", "es"]

    if not display_locale_code:
        try:
            locale_code = locale.getdefaultlocale()[0]
        except Exception:
            locale_code = "en_US"
    else:
        locale_code = display_locale_code

    # Determine if this locale makes its language names lower case
    babel_sample = babel.Locale.parse("en").get_display_name(locale_code)
    make_missing_lower = babel_sample.islower()

    langs = zip(
        lang_codes,
        [
            get_language_display_name(code, make_missing_lower, locale_code)
            for code in lang_codes
        ],
    )

    # Sort languages by display name
    langs = list(langs)
    try:
        langs.sort(key=lambda i: locale.strxfrm(i[1]))
    except Exception:
        logging.error("Error sorting language names for display in program preferences")
    return langs


def getQtSystemTranslation(locale_name: str) -> QTranslator | None:
    """
    Attempt to install Qt base system translations (for QMessageBox and QDialogBox
    buttons)
    :return: translator if loaded, else None
    """

    # These locales are found in the path QLibraryInfo.TranslationsPath
    convert_locale = dict(
        cs_CZ="cs",
        da_DK="da",
        de_DE="de",
        es_ES="es",
        fi_FI="fi",
        fr_FR="fr",
        it_IT="it",
        ja_JP="ja",
        hu_HU="hu",
        pl_PL="pl",
        ru_RU="ru",
        sk_SK="sk",
        uk_UA="uk",
    )

    qtTranslator = QTranslator()
    location = QLibraryInfo.location(QLibraryInfo.TranslationsPath)
    qm_file = f"qtbase_{convert_locale.get(locale_name, locale_name)}.qm"
    qm_file = os.path.join(location, qm_file)
    if os.path.isfile(qm_file):
        if qtTranslator.load(qm_file):
            logging.debug("Installing Qt support for locale %s", locale_name)
            return qtTranslator
        else:
            logging.debug("Could not load Qt locale file %s", qm_file)


def existing_parent_for_new_dir(path: Path) -> Path:
    """
    Locate the first parent folder that exists for a given path
    :param path: path to look for first existing parent
    :return: the first parent folder that exists for the  path
    """
    for parent in path.parents:
        if parent.is_dir():
            return parent
