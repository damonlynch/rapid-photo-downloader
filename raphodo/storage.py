# Copyright (C) 2015-2017 Damon Lynch <damonlynch@gmail.com>
# Copyright (C) 2008-2015 Canonical Ltd.
# Copyright (C) 2013 Bernard Baeyens

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

"""
The primary task of this module is to handle addition and removal of
(1) cameras and (2) devices with file systems.

There are two scenarios:

1) User is running under a Gnome-like environment in which GVFS will
automatically mount cameras and devices. We can monitor mounts and
send a signal when something is mounted. The camera must be
unmounted before libgphoto2 can access it, so we must handle that too.

2) User is running under a non Gnome-like environment (e.g. KDE) in
which GVFS may or may not be running. However we can assume GVFS will
not automatically mount cameras and devices. In this case, using GIO
to monitor mounts is useless, as the mounts may not occur. So we must
monitor when cameras and other devices are added or removed ourselves.
To do this, use udev for cameras, and udisks2 for devices with file
systems. When a device with a file system is inserted, if it is not
already mounted, attempt to mount it.

The secondary task of this module is to provide miscellaneous services
regarding mount points and XDG related functionality.
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2011-2017, Damon Lynch. Copyright 2008-2015 Canonical Ltd. Copyright" \
                " 2013 Bernard Baeyens."

import logging
import os
import re
import sys
import time
import subprocess
import shlex
import pwd
import shutil
from collections import namedtuple
from typing import Optional, Tuple, List, Dict, Any
from urllib.request import pathname2url, quote
from tempfile import NamedTemporaryFile

from PyQt5.QtCore import (QStorageInfo, QObject, pyqtSignal, QFileSystemWatcher, pyqtSlot, QTimer)
from xdg.DesktopEntry import DesktopEntry
from xdg import BaseDirectory
import xdg

import gi

gi.require_version('GUdev', '1.0')
gi.require_version('UDisks', '2.0')
gi.require_version('GExiv2', '0.10')
gi.require_version('GLib', '2.0')
from gi.repository import GUdev, UDisks, GLib

from gettext import gettext as _

from raphodo.constants import Desktop, Distro, FileManagerType
from raphodo.utilities import (
    process_running, log_os_release, remove_topmost_directory_from_path, find_mount_point
)

logging_level = logging.DEBUG

try:
    from gi.repository import Gio

    have_gio = True
except ImportError:
    have_gio = False

StorageSpace = namedtuple('StorageSpace', 'bytes_free, bytes_total, path')
CameraDetails = namedtuple('CameraDetails', 'model, port, display_name, is_mtp, storage_desc')
UdevAttr = namedtuple('UdevAttr', 'is_mtp_device, vendor, model')

PROGRAM_DIRECTORY = 'rapid-photo-downloader'


def get_distro_id(id_or_id_like: str) -> Distro:
    if id_or_id_like[0] in ('"', "'"):
        id_or_id_like = id_or_id_like[1:-1]
    try:
        return Distro[id_or_id_like.strip()]
    except KeyError:
        return Distro.unknown


def get_distro() -> Distro:
    if os.path.isfile('/etc/os-release'):
        with open('/etc/os-release', 'r') as f:
            for line in f:
                if line.startswith('ID='):
                    return get_distro_id(line[3:])
                if line.startswith('ID_LIKE='):
                    return get_distro_id(line[8:])
    return Distro.unknown


def get_user_name() -> str:
    """
    Gets the user name of the process owner, with no exception checking
    :return: user name of the process owner
    """

    return pwd.getpwuid(os.getuid())[0]


def get_path_display_name(path: str) -> Tuple[str, str]:
    """
    Return a name for the path (path basename),
    removing a final '/' when it's not the root of the
    file system.

    :param path: path to generate the display name for
    :return: display name and sanitized path
    """
    if path.endswith(os.sep) and path != os.sep:
        path = path[:-1]

    if path == os.sep:
        display_name = _('File system root')
    else:
        display_name = os.path.basename(path)
    return display_name, path


def get_media_dir() -> str:
    """
    Returns the media directory, i.e. where external mounts are mounted.

    Assumes mount point of /media/<USER>.

    """

    if sys.platform.startswith('linux'):
        media_dir = '/media/{}'.format(get_user_name())
        run_media_dir = '/run{}'.format(media_dir)
        distro = get_distro()
        if os.path.isdir(run_media_dir) and distro not in (
                Distro.ubuntu, Distro.debian, Distro.neon, Distro.galliumos, Distro.peppermint,
                Distro.elementary):
            if distro not in (Distro.fedora, Distro.manjaro, Distro.arch, Distro.opensuse,
                              Distro.gentoo, Distro.antergos):
                logging.debug("Detected /run/media directory, but distro does not appear to "
                              "be Fedora, Arch, openSUSE, Gentoo, Manjaro or Antergos")
                log_os_release()
            return run_media_dir
        return media_dir
    else:
        raise ("Mounts.setValidMountPoints() not implemented on %s", sys.platform())


_gvfs_gphoto2 = re.compile('gvfs.*gphoto2.*host')


def gvfs_gphoto2_path(path: str) -> bool:
    """
    :return: True if the path appears to be a GVFS gphoto2 path

    >>> p = "/run/user/1000/gvfs/gphoto2:host=%5Busb%3A002%2C013%5D"
    >>> gvfs_gphoto2_path(p)
    True
    >>> p = '/home/damon'
    >>> gvfs_gphoto2_path(p)
    False
    """

    return _gvfs_gphoto2.search(path) is not None


class ValidMounts():
    r"""
    Operations to find 'valid' mount points, i.e. the places in which
    it's sensible for a user to mount a partition. Valid mount points:
    include /home/<USER> , /media/<USER>, and /run/media/<USER>
    include directories in /etc/fstab, except /, /home, and swap
    However if only considering external mounts, the the mount must be
    under /media/<USER> or /run/media/<user>
    """

    def __init__(self, onlyExternalMounts: bool):
        """
        :param onlyExternalMounts: if True, valid mounts must be under
        /media/<USER> or /run/media/<user>
        """
        self.validMountFolders = None  # type: Tuple[str]
        self.onlyExternalMounts = onlyExternalMounts
        self._setValidMountFolders()
        assert '/' not in self.validMountFolders
        if logging_level == logging.DEBUG:
            self.logValidMountFolders()

    def isValidMountPoint(self, mount: QStorageInfo) -> bool:
        """
        Determine if the path of the mount point starts with a valid
        path
        :param mount: QStorageInfo to be tested
        :return:True if mount is a mount under a valid mount, else False
        """
        for m in self.validMountFolders:
            if mount.rootPath().startswith(m):
                return True
        return False

    def pathIsValidMountPoint(self, path: str) -> bool:
        """
        Determine if path indicates a mount point under a valid mount
        point
        :param path: path to be tested
        :return:True if path is a mount under a valid mount, else False
        """
        for m in self.validMountFolders:
            if path.startswith(m):
                return True
        return False

    def mountedValidMountPointPaths(self) -> Tuple[str]:
        """
        Return paths of all the currently mounted partitions that are
        valid
        :return: tuple of currently mounted valid partition paths
        """

        return tuple(filter(self.pathIsValidMountPoint, mountPaths()))

    def mountedValidMountPoints(self) -> Tuple[QStorageInfo]:
        """
        Return mount points of all the currently mounted partitions
        that are valid
        :return: tuple of currently mounted valid partition
        """

        return tuple(filter(self.isValidMountPoint, QStorageInfo.mountedVolumes()))

    def _setValidMountFolders(self) -> None:
        """
        Determine the valid mount point folders and set them in
        self.validMountFolders, e.g. /media/<USER>, etc.
        """

        if not sys.platform.startswith('linux'):
            raise ("Mounts.setValidMountPoints() not implemented on %s", sys.platform())
        else:
            try:
                media_dir = get_media_dir()
            except:
                logging.critical("Unable to determine username of this process")
                media_dir = ''
            logging.debug("Media dir is %s", media_dir)
            if self.onlyExternalMounts:
                self.validMountFolders = (media_dir, )
            else:
                home_dir = os.path.expanduser('~')
                validPoints = [home_dir, media_dir]
                for point in self.mountPointInFstab():
                    validPoints.append(point)
                self.validMountFolders = tuple(validPoints)

    def mountPointInFstab(self):
        """
        Yields a list of mount points in /etc/fstab
        The mount points will exclude /, /home, and swap
        """

        with open('/etc/fstab') as f:
            l = []
            for line in f:
                # As per fstab specs: white space is either Tab or space
                # Ignore comments, blank lines
                # Also ignore swap file (mount point none), root, and /home
                m = re.match(r'^(?![\t ]*#)\S+\s+(?!(none|/[\t ]|/home))('
                             r'?P<point>\S+)',
                             line)
                if m is not None:
                    yield (m.group('point'))

    def logValidMountFolders(self):
        """
        Output nicely formatted debug logging message
        """

        assert len(self.validMountFolders) > 0
        if logging_level == logging.DEBUG:
            msg = "To be recognized, partitions must be mounted under "
            if len(self.validMountFolders) > 2:
                msg += "one of "
                for p in self.validMountFolders[:-2]:
                    msg += "{}, ".format(p)
                msg += "{} or {}".format(self.validMountFolders[-2],
                                         self.validMountFolders[-1])
            elif len(self.validMountFolders) == 2:
                msg += "{} or {}".format(self.validMountFolders[0],
                                         self.validMountFolders[1])
            else:
                msg += self.validMountFolders[0]
            logging.debug(msg)


def mountPaths():
    """
    Yield all the mount paths returned by QStorageInfo
    """

    for m in QStorageInfo.mountedVolumes():
        yield m.rootPath()


def has_one_or_more_folders(path: str, folders: List[str]) -> bool:
    """
    Checks to see if directly below the path there is a folder
    from the list of specified folders, and if the folder is readable.
    :param path: path to check
    :return: True if has one or more valid folders, False otherwise
    """

    try:
        contents = os.listdir(path)
        for folder in folders:
            if folder in contents:
                full_path = os.path.join(path, folder)
                if os.path.isdir(full_path) and os.access(full_path, os.R_OK):
                    return True
    except (PermissionError, FileNotFoundError, OSError):
        return False
    except:
        logging.error("Unknown error occurred while probing potential source folder %s", path)
        return False
    return False


def get_desktop_environment() -> Optional[str]:
    """
    Determine desktop environment using environment variable XDG_CURRENT_DESKTOP

    :return: str with XDG_CURRENT_DESKTOP value
    """

    return os.getenv('XDG_CURRENT_DESKTOP')


def get_desktop() -> Desktop:
    """
    Determine desktop environment
    :return: enum representing desktop environment,
    Desktop.unknown if unknown.
    """

    try:
        env = get_desktop_environment().lower()
    except AttributeError:
        # Occurs when there is no value set
        return Desktop.unknown

    if env == 'unity:unity7':
        env = 'unity'
    elif env == 'x-cinnamon':
        env = 'cinnamon'
    elif env == 'ubuntu:gnome':
        env = 'ubuntugnome'
    elif env == 'pop:gnome':
        env = 'popgnome'
    try:
        return Desktop[env]
    except KeyError:
        return Desktop.unknown


def gvfs_controls_mounts() -> bool:
    """
    Determine if GVFS controls mounts on this system.

    By default, common desktop environments known to use it are assumed
    to be using it or not. If not found in this list, then the list of
    running processes is searched, looking for a match against 'gvfs-gphoto2',
    which will match what is at the time of this code being developed called
    'gvfs-gphoto2-volume-monitor', which is what we're most interested in.

    :return: True if so, False otherwise
    """

    desktop = get_desktop()
    if desktop in (Desktop.gnome, Desktop.unity, Desktop.cinnamon, Desktop.xfce,
                   Desktop.mate, Desktop.lxde):
        return True
    elif desktop == Desktop.kde:
        return False
    return process_running('gvfs-gphoto2')


def _get_xdg_special_dir(dir_type: gi.repository.GLib.UserDirectory,
                         home_on_failure: bool=True) -> Optional[str]:
    path = GLib.get_user_special_dir(dir_type)
    if path is None and home_on_failure:
        return os.path.expanduser('~')
    return path

def xdg_photos_directory(home_on_failure: bool=True) -> Optional[str]:
    """
    Get localized version of /home/<USER>/Pictures

    :param home_on_failure: if the directory does not exist, return
     the home directory instead
    :return: the directory if it is specified, else the user's
    home directory or None
    """
    return _get_xdg_special_dir(GLib.USER_DIRECTORY_PICTURES, home_on_failure)


def xdg_videos_directory(home_on_failure: bool=True) -> str:
    """
    Get localized version of /home/<USER>/Videos

    :param home_on_failure: if the directory does not exist, return
     the home directory instead
    :return: the directory if it is specified, else the user's
    home directory or None
    """
    return _get_xdg_special_dir(GLib.USER_DIRECTORY_VIDEOS, home_on_failure)

def xdg_desktop_directory(home_on_failure: bool=True) -> str:
    """
    Get localized version of /home/<USER>/Desktop

    :param home_on_failure: if the directory does not exist, return
     the home directory instead
    :return: the directory if it is specified, else the user's
    home directory or None
    """
    return _get_xdg_special_dir(GLib.UserDirectory.DIRECTORY_DESKTOP, home_on_failure)

def xdg_photos_identifier() -> str:
    """
    Get special subfoler indicated by the localized version of /home/<USER>/Pictures
    :return: the subfolder name if it is specified, else the localized version of 'Pictures'
    """

    path = _get_xdg_special_dir(GLib.USER_DIRECTORY_PICTURES, home_on_failure=False)
    if path is None:
        # translators: the name of the Pictures folder
        return _('Pictures')
    return os.path.basename(path)

def xdg_videos_identifier() -> str:
    """
    Get special subfoler indicated by the localized version of /home/<USER>/Pictures
    :return: the subfolder name if it is specified, else the localized version of 'Pictures'
    """

    path = _get_xdg_special_dir(GLib.USER_DIRECTORY_VIDEOS, home_on_failure=False)
    if path is None:
        # translators: the name of the Videos folder
        return _('Videos')
    return os.path.basename(path)


def make_program_directory(path: str) -> str:
    """
    Creates a subfolder used by Rapid Photo Downloader.

    Does not catch errors.

    :param path: location where the subfolder should be
    :return: the full path of the new directory
    """
    program_dir = os.path.join(path, 'rapid-photo-downloader')
    if not os.path.exists(program_dir):
        os.mkdir(program_dir)
    elif not os.path.isdir(program_dir):
        os.remove(program_dir)
        os.mkdir(program_dir)
    return program_dir


def get_program_cache_directory(create_if_not_exist: bool = False) -> Optional[str]:
    """
    Get Rapid Photo Downloader cache directory.

    Is assumed to be under $XDG_CACHE_HOME or if that doesn't exist,
     ~/.cache.
    :param create_if_not_exist: creates directory if it does not exist.
    :return: the full path of the cache directory, or None on error
    """
    try:
        cache_directory = BaseDirectory.xdg_cache_home
        if not create_if_not_exist:
            return os.path.join(cache_directory, PROGRAM_DIRECTORY)
        else:
            return make_program_directory(cache_directory)
    except OSError:
        logging.error("An error occurred while creating the cache directory")
        return None


def get_program_logging_directory(create_if_not_exist: bool = False) -> Optional[str]:
    """
    Get directory in which to store program log files.

    Log files are kept in the cache dirctory.

    :param create_if_not_exist:
    :return: the full path of the logging directory, or None on error
    """
    cache_directory = get_program_cache_directory(create_if_not_exist=create_if_not_exist)
    log_dir = os.path.join(cache_directory, 'log')
    if os.path.isdir(log_dir):
        return log_dir
    if create_if_not_exist:
        try:
            if os.path.isfile(log_dir):
                os.remove(log_dir)
            os.mkdir(log_dir, 0o700)
            return log_dir
        except OSError:
            logging.error("An error occurred while creating the log directory")
    return None


def get_program_data_directory(create_if_not_exist=False) -> Optional[str]:
    """
    Get Rapid Photo Downloader data directory, which is assumed to be
    under $XDG_DATA_HOME or if that doesn't exist,  ~/.local/share
    :param create_if_not_exist: creates directory if it does not exist.
    :return: the full path of the data directory, or None on error
    """
    try:
        data_directory = BaseDirectory.xdg_data_dirs[0]
        if not create_if_not_exist:
            return os.path.join(data_directory, PROGRAM_DIRECTORY)
        else:
            return make_program_directory(data_directory)
    except OSError:
        logging.error("An error occurred while creating the data directory")
        return None


def get_fdo_cache_thumb_base_directory() -> str:
    """
    Get the Freedesktop.org thumbnail directory location
    :return: location
    """

    # LXDE is a special case: handle it
    if get_desktop() == Desktop.lxde:
        return os.path.join(os.path.expanduser('~'), '.thumbnails')

    return os.path.join(BaseDirectory.xdg_cache_home, 'thumbnails')


def get_default_file_manager(remove_args: bool = True) -> Tuple[
                                                        Optional[str], Optional[FileManagerType]]:
    """
    Attempt to determine the default file manager for the system
    :param remove_args: if True, remove any arguments such as %U from
     the returned command
    :return: command (without path) if found, else None
    """
    assert sys.platform.startswith('linux')
    cmd = shlex.split('xdg-mime query default inode/directory')
    try:
        desktop_file = subprocess.check_output(cmd, universal_newlines=True)  # type: str
    except:
        return None, None
    # Remove new line character from output
    desktop_file = desktop_file[:-1]
    if desktop_file.endswith(';'):
        desktop_file = desktop_file[:-1]

    for desktop_path in (os.path.join(d, 'applications') for d in BaseDirectory.xdg_data_dirs):
        path = os.path.join(desktop_path, desktop_file)
        if os.path.exists(path):
            try:
                desktop_entry = DesktopEntry(path)
            except xdg.Exceptions.ParsingError:
                return None, None
            try:
                desktop_entry.parse(path)
            except:
                return None, None
            fm = desktop_entry.getExec()
            if fm.startswith('dolphin'):
                file_manager_type = FileManagerType.select
            else:
                file_manager_type = FileManagerType.regular
            if remove_args:
                return fm.split()[0], file_manager_type
            else:
                return fm, file_manager_type

    # Special case: LXQt
    if get_desktop() == Desktop.lxqt:
        if shutil.which('pcmanfm-qt'):
            return 'pcmanfm-qt', FileManagerType.regular

    return None, None

def open_in_file_manager(file_manager: str,
                         file_manager_type: FileManagerType,
                         uri: str) -> None:
    if file_manager_type == FileManagerType.regular:
        arg = ''
    else:
        arg = '--select '

    cmd = '{} {}"{}"'.format(file_manager, arg, uri)
    logging.debug("Launching: %s", cmd)
    args = shlex.split(cmd)
    subprocess.Popen(args)


_desktop = get_desktop()
_quoted_comma = quote(',')


def get_uri(full_file_name: Optional[str]=None,
            path: Optional[str]=None,
            camera_details: Optional[CameraDetails]=None,
            desktop_environment: Optional[bool]=True) -> str:
    """
    Generate and return the URI for the file, which varies depending on
    which device it is

    :param full_file_name: full filename and path
    :param path: straight path when not passing a full_file_name
    :param camera_details: see named tuple CameraDetails for parameters
    :param desktop_environment: if True, will to generate a URI accepted
     by Gnome and KDE desktops, which means adjusting the URI if it appears to be an
     MTP mount. Includes the port too.
    :return: the URI
    """

    if camera_details is None:
        prefix = 'file://'
        if desktop_environment:
            desktop = get_desktop()
            if full_file_name and desktop == Desktop.mate:
                full_file_name = os.path.dirname(full_file_name)
    else:
        if not desktop_environment:
            if full_file_name or path:
                prefix = 'gphoto2://'
            else:
                prefix = 'gphoto2://' + pathname2url('[{}]'.format(camera_details.port))
        else:
            prefix = ''
            # Attempt to generate a URI accepted by desktop environments
            if camera_details.is_mtp:
                if full_file_name:
                    full_file_name = remove_topmost_directory_from_path(full_file_name)
                elif path:
                    path = remove_topmost_directory_from_path(path)

                if gvfs_controls_mounts() or _desktop == Desktop.lxqt:
                    prefix = 'mtp://' + pathname2url(
                        '[{}]/{}'.format(camera_details.port, camera_details.storage_desc)
                    )
                elif _desktop == Desktop.kde:
                    prefix = 'mtp:/' + pathname2url(
                        '{}/{}'.format(camera_details.display_name, camera_details.storage_desc)
                    )
                else:
                    logging.error("Don't know how to generate MTP prefix for %s", _desktop.name)
            else:
                prefix = 'gphoto2://' + pathname2url('[{}]'.format(camera_details.port))

            if _desktop == Desktop.lxqt:
                # pcmanfm-qt does not like the quoted form of the comma
                prefix = prefix.replace(_quoted_comma, ',')
                if full_file_name:
                    # pcmanfm-qt does not like the the filename as part of the path
                    full_file_name = os.path.dirname(full_file_name)

    if full_file_name or path:
        uri = '{}{}'.format(prefix, pathname2url(full_file_name or path))
    else:
        uri = prefix
    return uri


ValidatedFolder = namedtuple('ValidatedFolder', 'valid, absolute_path')


def validate_download_folder(path: Optional[str],
                             write_on_waccesss_failure: bool=False) -> ValidatedFolder:
    r"""
    Check if folder exists and is writeable.

    Accepts None as a folder, which will always be invalid.

    :param path: path to analyze
    :param write_on_waccesss_failure: if os.access reports path is not writable, test
     nonetheless to see if it's writable by writing and deleting a test file 
    :return: Tuple indicating validity and path made absolute

    >>> validate_download_folder('/some/bogus/and/ridiculous/path')
    ValidatedFolder(valid=False, absolute_path='/some/bogus/and/ridiculous/path')
    >>> validate_download_folder(None)
    ValidatedFolder(valid=False, absolute_path='')
    >>> validate_download_folder('')
    ValidatedFolder(valid=False, absolute_path='')
    """

    if not path:
        return ValidatedFolder(False, '')
    absolute_path = os.path.abspath(path)
    valid = os.path.isdir(path) and os.access(path, os.W_OK)
    if not valid and write_on_waccesss_failure and os.path.isdir(path):
        try:
            with NamedTemporaryFile(dir=path):
                # the path is in fact writeable -- can happen with NFS
                valid = True
        except Exception:
            logging.warning('While validating download / backup folder, failed to write a '
                            'temporary file to %s', path)

    return ValidatedFolder(valid, absolute_path)


def validate_source_folder(path: Optional[str]) -> ValidatedFolder:
    r"""
    Check if folder exists and is readable.

    Accepts None as a folder, which will always be invalid.

    :param path: path to analyze
    :return: Tuple indicating validity and path made absolute

    >>> validate_source_folder('/some/bogus/and/ridiculous/path')
    ValidatedFolder(valid=False, absolute_path='/some/bogus/and/ridiculous/path')
    >>> validate_source_folder(None)
    ValidatedFolder(valid=False, absolute_path='')
    >>> validate_source_folder('')
    ValidatedFolder(valid=False, absolute_path='')
    """

    if not path:
        return ValidatedFolder(False, '')
    absolute_path = os.path.abspath(path)
    valid = os.path.isdir(path) and os.access(path, os.R_OK)
    return ValidatedFolder(valid, absolute_path)


def udev_attributes(devname: str) -> Optional[UdevAttr]:
    """
    Query udev to see if device is an MTP device.

    :param devname: udev DEVNAME e.g. '/dev/bus/usb/001/003'
    :return True if udev property ID_MTP_DEVICE == '1', else False
    """

    client = GUdev.Client(subsystems=['usb', 'block'])
    enumerator = GUdev.Enumerator.new(client)
    enumerator.add_match_property('DEVNAME', devname)
    for device in enumerator.execute():
        model = device.get_property('ID_MODEL')  # type: str
        if model is not None:
            is_mtp = device.get_property('ID_MTP_DEVICE') == '1'
            vendor = device.get_property('ID_VENDOR')  # type: str
            model = model.replace('_', ' ').strip()
            vendor = vendor.replace('_', ' ').strip()
            return UdevAttr(is_mtp, vendor, model)
    return None


def fs_device_details(path: str) -> Tuple:
    """
    :return: device (volume) name, uri, root path and filesystem type
     of the mount the path is on
    """
    qsInfo = QStorageInfo(path)
    name = qsInfo.displayName()
    root_path = qsInfo.rootPath()
    uri = 'file://{}'.format(pathname2url(root_path))
    fstype = qsInfo.fileSystemType()
    if isinstance(fstype, bytes):
        fstype = fstype.decode()
    return name, uri, root_path, fstype


class WatchDownloadDirs(QFileSystemWatcher):
    """
    Create a file system watch to monitor if there are changes to the
    download directories
    """

    def updateWatchPathsFromPrefs(self, prefs) -> None:
        """
        Update the watched directories using values from the program preferences
        :param prefs: program preferences
        :type prefs: raphodo.preferences.Preferences
        """

        logging.debug("Updating watched paths")

        paths = (os.path.dirname(path) for path in (prefs.photo_download_folder,
                                                    prefs.video_download_folder))
        watch = {path for path in paths if path}

        existing_watches = set(self.directories())

        if watch == existing_watches:
            return

        new = watch - existing_watches
        if new:
            new = list(new)
            logging.debug("Adding to watched paths: %s", ', '.join(new))
            failures = self.addPaths(new)
            if failures:
                logging.debug("Failed to add watched paths: %s", failures)

        old = existing_watches - watch
        if old:
            old = list(old)
            logging.debug("Removing from watched paths: %s", ', '.join(old))
            failures = self.removePaths(old)
            if failures:
                logging.debug("Failed to remove watched paths: %s", failures)

    def closeWatch(self) -> None:
        """
        End all watches.
        """
        dirs = self.directories()
        if dirs:
            self.removePaths(dirs)


class CameraHotplug(QObject):
    cameraAdded = pyqtSignal()
    cameraRemoved = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.cameras = {}

    @pyqtSlot()
    def startMonitor(self):
        self.client = GUdev.Client(subsystems=['usb', 'block'])
        self.client.connect('uevent', self.ueventCallback)
        logging.debug("... camera hotplug monitor started")
        self.enumerateCameras()
        if self.cameras:
            logging.debug("Camera Hotplug found %d cameras:", len(self.cameras))
            for port, model in self.cameras.items():
                logging.debug("%s at %s", model, port)

    def enumerateCameras(self):
        """
        Query udev to get the list of cameras store their path and
        model in our internal dict, which is useful when responding to
        camera removal.
        """
        enumerator = GUdev.Enumerator.new(self.client)
        enumerator.add_match_property('ID_GPHOTO2', '1')
        for device in enumerator.execute():
            model = device.get_property('ID_MODEL')
            if model is not None:
                path = device.get_sysfs_path()
                self.cameras[path] = model

    def ueventCallback(self, client: GUdev.Client, action: str, device: GUdev.Device) -> None:

        # for key in device.get_property_keys():
        #     print(key, device.get_property(key))
        if device.get_property('ID_GPHOTO2') == '1':
            self.camera(action, device)

    def camera(self, action: str, device: GUdev.Device) -> None:
        # For some reason, the add and remove camera event is triggered twice.
        # The second time the device information is a variation on information
        # from the first time.
        path = device.get_sysfs_path()
        parent_device = device.get_parent()
        parent_path = parent_device.get_sysfs_path()
        logging.debug("Device change: %s. Path: %s Parent Device: %s Parent path: %s",
                      action, path, parent_device, parent_path)

        if action == 'add':
            if parent_path not in self.cameras:
                model = device.get_property('ID_MODEL')
                logging.debug("Hotplug: new camera: %s", model)
                self.cameras[path] = model
                self.cameraAdded.emit()
            else:
                logging.debug("Hotplug: already know about %s", self.cameras[
                    parent_path])

        elif action == 'remove':
            emit_remove = False
            name = ''
            if path in self.cameras:
                name = self.cameras[path]
                del self.cameras[path]
                emit_remove = True
            elif device.get_property('ID_GPHOTO2') == '1':
                # This should not need to be called. However,
                # self.enumerateCameras may not have been called earlier
                name = device.get_property('ID_MODEL')
                if name is not None:
                    emit_remove = True
            if emit_remove:
                logging.debug("Hotplug: %s has been removed", name)
                self.cameraRemoved.emit()


class UDisks2Monitor(QObject):
    # Most of this class is Copyright 2008-2015 Canonical

    partitionMounted = pyqtSignal(str, list, bool)
    partitionUnmounted = pyqtSignal(str)

    loop_prefix = '/org/freedesktop/UDisks2/block_devices/loop'
    not_interesting = (
        '/org/freedesktop/UDisks2/block_devices/dm_',
        '/org/freedesktop/UDisks2/block_devices/ram',
        '/org/freedesktop/UDisks2/block_devices/zram',
    )

    def __init__(self, validMounts: ValidMounts) -> None:
        super().__init__()
        self.validMounts = validMounts

    @pyqtSlot()
    def startMonitor(self) -> None:
        self.udisks = UDisks.Client.new_sync(None)
        self.manager = self.udisks.get_object_manager()
        self.manager.connect('object-added',
                             lambda man, obj: self._udisks_obj_added(obj))
        self.manager.connect('object-removed',
                             lambda man, obj: self._device_removed(obj))

        # Track the paths of the mount points, which is useful when unmounting
        # objects.
        self.known_mounts = {}  # type: Dict[str, str]
        for obj in self.manager.get_objects():
            path = obj.get_object_path()
            fs = obj.get_filesystem()
            if fs:
                mount_points = fs.get_cached_property('MountPoints').get_bytestring_array()
                if mount_points:
                    self.known_mounts[path] = mount_points[0]
        logging.debug("... UDisks2 monitor started")

    def _udisks_obj_added(self, obj) -> None:
        path = obj.get_object_path()
        for boring in self.not_interesting:
            if path.startswith(boring):
                return
        block = obj.get_block()
        if not block:
            return

        drive = self._get_drive(block)

        part = obj.get_partition()
        is_system = block.get_cached_property('HintSystem').get_boolean()
        is_loop = path.startswith(self.loop_prefix) and not \
            block.get_cached_property('ReadOnly').get_boolean()
        if not is_system or is_loop:
            if part:
                self._udisks_partition_added(obj, block, drive, path)

    def _get_drive(self, block) -> Optional[UDisks.Drive]:
        drive_name = block.get_cached_property('Drive').get_string()
        if drive_name != '/':
            return self.udisks.get_object(drive_name).get_drive()
        else:
            return None

    def _udisks_partition_added(self, obj, block, drive, path) -> None:
        logging.debug('UDisks: partition added: %s' % path)
        fstype = block.get_cached_property('IdType').get_string()
        logging.debug('Udisks: id-type: %s' % fstype)

        fs = obj.get_filesystem()

        if fs:
            icon_names = self.get_icon_names(obj)

            if drive is not None:
                ejectable = drive.get_property('ejectable')
            else:
                ejectable = False
            mount_point = ''
            mount_points = fs.get_cached_property('MountPoints').get_bytestring_array()
            if len(mount_points) == 0:
                try:
                    logging.debug("UDisks: attempting to mount %s", path)
                    mount_point = self.retry_mount(fs, fstype)
                    if not mount_point:
                        raise Exception
                    else:
                        logging.debug("UDisks: successfully mounted at %s", mount_point)
                except Exception:
                    logging.error('UDisks: could not mount the device: %s', path)
                    return
            else:
                mount_point = mount_points[0]
                logging.debug("UDisks: already mounted at %s", mount_point)

            self.known_mounts[path] = mount_point
            if self.validMounts.pathIsValidMountPoint(mount_point):
                self.partitionMounted.emit(mount_point, icon_names, ejectable)

        else:
            logging.debug("Udisks: partition has no file system %s", path)

    def retry_mount(self, fs, fstype) -> str:
        # Variant parameter construction Copyright Bernard Baeyens, and is
        # licensed under GNU General Public License Version 2 or higher.
        # https://github.com/berbae/udisksvm
        list_options = ''
        if fstype == 'vfat':
            list_options = 'flush'
        elif fstype == 'ext2':
            list_options = 'sync'
        G_VARIANT_TYPE_VARDICT = GLib.VariantType.new('a{sv}')
        param_builder = GLib.VariantBuilder.new(G_VARIANT_TYPE_VARDICT)
        optname = GLib.Variant.new_string('fstype')  # s
        value = GLib.Variant.new_string(fstype)
        vvalue = GLib.Variant.new_variant(value)  # v
        newsv = GLib.Variant.new_dict_entry(optname, vvalue)  # {sv}
        param_builder.add_value(newsv)
        optname = GLib.Variant.new_string('options')
        value = GLib.Variant.new_string(list_options)
        vvalue = GLib.Variant.new_variant(value)
        newsv = GLib.Variant.new_dict_entry(optname, vvalue)
        param_builder.add_value(newsv)
        vparam = param_builder.end()  # a{sv}

        # Try to mount until it does not fail with "Busy"
        timeout = 10
        while timeout >= 0:
            try:
                return fs.call_mount_sync(vparam, None)
            except GLib.GError as e:
                if not 'UDisks2.Error.DeviceBusy' in e.message:
                    raise
                logging.debug('Udisks: Device busy.')
                time.sleep(0.3)
                timeout -= 1
        return ''

    def get_icon_names(self, obj: UDisks.Object) -> List[str]:
        # Get icon information, if possible
        icon_names = []
        if have_gio:
            info = self.udisks.get_object_info(obj)
            icon = info.get_icon()
            if isinstance(icon, Gio.ThemedIcon):
                icon_names = icon.get_names()
        return icon_names

    # Next four class member functions from Damon Lynch, not Canonical
    def _device_removed(self, obj: UDisks.Object) -> None:
        # path here refers to the udev / udisks path, not the mount point
        path = obj.get_object_path()
        if path in self.known_mounts:
            mount_point = self.known_mounts[path]
            del self.known_mounts[path]
            self.partitionUnmounted.emit(mount_point)

    def get_can_eject(self, obj: UDisks.Object) -> bool:
        block = obj.get_block()
        drive = self._get_drive(block)
        if drive is not None:
            return drive.get_property('ejectable')
        return False

    def get_device_props(self, device_path: str) -> Tuple[List[str], bool]:
        """
        Given a device, get the icon names suggested by udev, and
        determine whether the mount is ejectable or not.
        :param device_path: system path of the device to check,
        e.g. /dev/sdc1
        :return: icon names and eject boolean
        """

        object_path = '/org/freedesktop/UDisks2/block_devices/{}'.format(
            os.path.split(device_path)[1])
        obj = self.udisks.get_object(object_path)
        icon_names = self.get_icon_names(obj)
        can_eject = self.get_can_eject(obj)
        return (icon_names, can_eject)

    @pyqtSlot(str)
    def unmount_volume(self, mount_point: str) -> None:

        G_VARIANT_TYPE_VARDICT = GLib.VariantType.new('a{sv}')
        param_builder = GLib.VariantBuilder.new(G_VARIANT_TYPE_VARDICT)

        # Variant parameter construction Copyright Bernard Baeyens, and is
        # licensed under GNU General Public License Version 2 or higher.
        # https://github.com/berbae/udisksvm

        optname = GLib.Variant.new_string('force')
        value = GLib.Variant.new_boolean(False)
        vvalue = GLib.Variant.new_variant(value)
        newsv = GLib.Variant.new_dict_entry(optname, vvalue)
        param_builder.add_value(newsv)

        vparam = param_builder.end()                            # a{sv}

        path = None
        # Get the path from the dict we keep of known mounts
        for key, value in self.known_mounts.items():
            if value == mount_point:
                path = key
                break
        if path is None:
            logging.error("Could not find UDisks2 path used to be able to unmount %s", mount_point)

        fs = None
        for obj in self.manager.get_objects():
            opath = obj.get_object_path()
            if path == opath:
                fs = obj.get_filesystem()
        if fs is None:
            logging.error("Could not find UDisks2 filesystem used to be able to unmount %s",
                          mount_point)

        logging.debug("Unmounting %s...", mount_point)
        try:
            fs.call_unmount(vparam, None, self.umount_volume_callback, (mount_point, fs))
        except GLib.GError:
            value = sys.exc_info()[1]
            logging.error('Unmounting failed with error:')
            logging.error("%s", value)

    def umount_volume_callback(self, source_object:  UDisks.FilesystemProxy,
                               result: Gio.AsyncResult,
                               user_data: Tuple[str, UDisks.Filesystem]) -> None:
        """
        Callback for asynchronous unmount operation.

        :param source_object: the FilesystemProxy object
        :param result: result of the unmount
        :param user_data: mount_point and the file system
        """

        mount_point, fs = user_data

        try:
            if fs.call_unmount_finish(result):
                logging.debug("...successfully unmounted %s", mount_point)
            else:
                # this is the result even when the unmount was unsuccessful
                logging.debug("...possibly failed to unmount %s", mount_point)
        except GLib.GError as e:
            logging.error('Exception occurred unmounting %s', mount_point)
            logging.exception('Traceback:')
        except:
            logging.error('Exception occurred unmounting %s', mount_point)
            logging.exception('Traceback:')

        self.partitionUnmounted.emit(mount_point)


if have_gio:
    class GVolumeMonitor(QObject):
        r"""
        Monitor the mounting or unmounting of cameras or partitions
        using Gnome's GIO/GVFS. Unmount cameras automatically mounted
        by GVFS.

        Raises a signal if a volume has been inserted, but will not be
        automatically mounted. This is important because this class
        is monitoring mounts, and if the volume is not mounted, it will
        go unnoticed.
        """

        cameraUnmounted = pyqtSignal(bool, str, str, bool, bool)
        cameraMounted = pyqtSignal()
        partitionMounted = pyqtSignal(str, list, bool)
        partitionUnmounted = pyqtSignal(str)
        volumeAddedNoAutomount = pyqtSignal()
        cameraPossiblyRemoved = pyqtSignal()

        def __init__(self, validMounts: ValidMounts) -> None:
            super().__init__()
            self.vm = Gio.VolumeMonitor.get()
            self.vm.connect('mount-added', self.mountAdded)
            self.vm.connect('volume-added', self.volumeAdded)
            self.vm.connect('mount-removed', self.mountRemoved)
            self.vm.connect('volume-removed', self.volumeRemoved)
            self.portSearch = re.compile(r'usb:([\d]+),([\d]+)')
            self.scsiPortSearch = re.compile(r'usbscsi:(.+)')
            self.validMounts = validMounts

        def ptpCameraMountPoint(self, model: str, port: str) -> Optional[Gio.Mount]:
            """
            :return: the mount point of the PTP / MTP camera, if it is mounted,
             else None. If camera is not mounted with PTP / MTP, None is
             returned.
            """

            p = self.portSearch.match(port)
            if p is not None:
                p1 = p.group(1)
                p2 = p.group(2)
                pattern = re.compile(r'%\S\Susb%\S\S{}%\S\S{}%\S\S'.format(p1, p2))
            else:
                p = self.scsiPortSearch.match(port)
                if p is None:
                    logging.error("Unknown camera mount method %s %s", model, port)
                return None

            to_unmount = None

            for mount in self.vm.get_mounts():
                folder_extract = self.mountIsCamera(mount)
                if folder_extract is not None:
                    if pattern.match(folder_extract):
                        to_unmount = mount
                        break
            return to_unmount

        @pyqtSlot(str, str, bool, bool, int)
        def reUnmountCamera(self, model: str,
                          port: str,
                          download_starting: bool,
                          on_startup: bool,
                          attempt_no: int) -> None:

            logging.info(
                "Attempt #%s to unmount camera %s on port %s",
                attempt_no + 1, model, port
            )
            self.unmountCamera(
                model=model, port=port, download_starting=download_starting, on_startup=on_startup,
                attempt_no=attempt_no
            )

        def unmountCamera(self, model: str,
                          port: str,
                          download_starting: bool=False,
                          on_startup: bool=False,
                          mount_point: Optional[Gio.Mount]=None,
                          attempt_no: Optional[int]=0) -> bool:
            """
            Unmount camera mounted on gvfs mount point, if it is
            mounted. If not mounted, ignore.
            :param model: model as returned by libgphoto2
            :param port: port as returned by libgphoto2, in format like
             usb:001,004
            :param download_starting: if True, the unmount is occurring
             because a download has been initiated.
            :param on_startup: if True, the unmount is occurring during
             the program's startup phase
            :param mount_point: if not None, try umounting from this
             mount point without scanning for it first
            :return: True if an unmount operation has been initiated,
             else returns False.
            """

            if mount_point is None:
                to_unmount = self.ptpCameraMountPoint(model, port)
            else:
                to_unmount = mount_point

            if to_unmount is not None:
                logging.debug("GIO: Attempting to unmount %s...", model)
                to_unmount.unmount_with_operation(
                    0, None, None, self.unmountCameraCallback,
                    (model, port, download_starting, on_startup, attempt_no)
                )
                return True

            return False

        def unmountCameraCallback(self, mount: Gio.Mount,
                                  result: Gio.AsyncResult,
                                  user_data: Tuple[str, str, bool, bool]) -> None:
            """
            Called by the asynchronous unmount operation.
            When complete, emits a signal indicating operation
            success, and the camera model and port
            :param mount: camera mount
            :param result: result of the unmount process
            :param user_data: model and port of the camera being
            unmounted, in the format of libgphoto2
            """

            model, port, download_starting, on_startup, attempt_no = user_data
            try:
                if mount.unmount_with_operation_finish(result):
                    logging.debug("...successfully unmounted {}".format(model))
                    self.cameraUnmounted.emit(True, model, port, download_starting, on_startup)
                else:
                    logging.debug("...failed to unmount {}".format(model))
                    self.cameraUnmounted.emit(False, model, port, download_starting, on_startup)
            except GLib.GError as e:
                if e.code == 26 and attempt_no < 10:
                    attempt_no += 1
                    QTimer.singleShot(
                        750, lambda : self.reUnmountCamera(
                            model, port, download_starting,
                            on_startup, attempt_no
                        )
                    )
                else:
                    logging.error('Exception occurred unmounting {}'.format(model))
                    logging.exception('Traceback:')
                    self.cameraUnmounted.emit(False, model, port, download_starting, on_startup)

        def unmountVolume(self, path: str) -> None:
            """
            Unmounts the volume represented by the path. If no volume is found
            representing that path, nothing happens.

            :param path: path of the volume. It should not end with os.sep.
            """

            for mount in self.vm.get_mounts():
                root = mount.get_root()
                if root is not None:
                    mpath = root.get_path()
                    if path == mpath:
                        logging.info("Attempting to unmount %s...", path)
                        mount.unmount_with_operation(0, None, None, self.unmountVolumeCallback,
                                                     path)
                        break

        def unmountVolumeCallback(self, mount: Gio.Mount,
                                  result: Gio.AsyncResult,
                                  user_data: str) -> None:

            """
            Called by the asynchronous unmount operation.

            :param mount: volume mount
            :param result: result of the unmount process
            :param user_data: the path of the device unmounted
            """
            path = user_data

            try:
                if mount.unmount_with_operation_finish(result):
                    logging.info("...successfully unmounted %s", path)
                else:
                    logging.info("...failed to unmount %s", path)
            except GLib.GError as e:
                logging.error('Exception occurred unmounting %s', path)
                logging.exception('Traceback:')


        def mountIsCamera(self, mount: Gio.Mount) -> Optional[str]:
            """
            Determine if the mount point is that of a camera
            :param mount: the mount to examine
            :return: None if not a camera, or the component of the
            folder name that indicates on which port it is mounted
            """
            root = mount.get_root()
            if root is None:
                logging.warning('Unable to get mount root')
            else:
                path = root.get_path()
                if path:
                    logging.debug("GIO: Looking for camera at mount {}".format(path))
                    folder_name = os.path.split(path)[1]
                    for s in ('gphoto2:host=', 'mtp:host='):
                        if folder_name.startswith(s):
                            return folder_name[len(s):]
                if path is not None:
                    logging.debug("GIO: camera not found at {}".format(path))
            return None

        def mountIsPartition(self, mount: Gio.Mount) -> bool:
            """
            Determine if the mount point is that of a valid partition,
            i.e. is mounted in a valid location, which is under one of
            self.validMountDirs
            :param mount: the mount to examine
            :return: True if the mount is a valid partiion
            """
            root = mount.get_root()
            if root is None:
                logging.warning('Unable to get mount root')
            else:
                path = root.get_path()
                if path:
                    logging.debug("GIO: Looking for valid partition at mount {}".format(path))
                    if self.validMounts.pathIsValidMountPoint(path):
                        logging.debug("GIO: partition found at {}".format(path))
                        return True
                if path is not None:
                    logging.debug("GIO: partition is not valid mount: {}".format(path))
            return False

        def mountAdded(self, volumeMonitor, mount: Gio.Mount) -> None:
            if self.mountIsCamera(mount):
                self.cameraMounted.emit()
            elif self.mountIsPartition(mount):
                icon_names = self.getIconNames(mount)
                self.partitionMounted.emit(mount.get_root().get_path(),
                                           icon_names,
                                           mount.can_eject())

        def mountRemoved(self, volumeMonitor, mount: Gio.Mount) -> None:
            if not self.mountIsCamera(mount):
                if self.mountIsPartition(mount):
                    logging.debug("GIO: %s has been unmounted", mount.get_name())
                    self.partitionUnmounted.emit(mount.get_root().get_path())

        def volumeAdded(self, volumeMonitor, volume: Gio.Volume) -> None:
            logging.debug("GIO: Volume added %s. Automount: %s",
                          volume.get_name(),
                          volume.should_automount())
            if not volume.should_automount():
                # TODO is it possible to determine the device type?
                self.volumeAddedNoAutomount.emit()

        def volumeRemoved(self, volumeMonitor, volume: Gio.Volume) -> None:
            logging.debug("GIO: %s volume removed", volume.get_name())
            if volume.get_activation_root() is not None:
                logging.debug("GIO: %s might be a camera", volume.get_name())
                self.cameraPossiblyRemoved.emit()

        def getIconNames(self, mount: Gio.Mount) -> List[str]:
            icon_names = []
            icon = mount.get_icon()
            if isinstance(icon, Gio.ThemedIcon):
                icon_names = icon.get_names()

            return icon_names

        def getProps(self, path: str) -> Tuple[Optional[List[str]], Optional[bool]]:
            """
            Given a mount's path, get the icon names suggested by the
            volume monitor, and determine whether the mount is
            ejectable or not.
            :param path: the path of mount to check
            :return: icon names and eject boolean
            """

            for mount in self.vm.get_mounts():
                root = mount.get_root()
                if root is not None:
                    p = root.get_path()
                    if path == p:
                        icon_names = self.getIconNames(mount)
                        return (icon_names, mount.can_eject())
            return (None, None)


def _get_info_size_value(info: Gio.FileInfo, attr: str) -> int:
    if info.get_attribute_data(attr).type ==  Gio.FileAttributeType.UINT64:
        return info.get_attribute_uint64(attr)
    else:
        return info.get_attribute_uint32(attr)


def get_mount_size(mount: QStorageInfo) -> Tuple[int, int]:
    """
    Uses GIO to get bytes total and bytes free (available) for the mount that a
    path is in.
    
    :param path: path located anywhere in the mount
    :return: bytes_total, bytes_free
    """

    bytes_free = mount.bytesAvailable()
    bytes_total = mount.bytesTotal()

    if bytes_total or not have_gio:
        return bytes_total, bytes_free

    path = mount.rootPath()

    logging.debug("Using GIO to query file system attributes for %s...", path)
    p = Gio.File.new_for_path(os.path.abspath(path))
    info = p.query_filesystem_info(','.join((Gio.FILE_ATTRIBUTE_FILESYSTEM_SIZE,
                                             Gio.FILE_ATTRIBUTE_FILESYSTEM_FREE)))
    logging.debug("...query of file system attributes for %s completed", path)
    bytes_total = _get_info_size_value(info, Gio.FILE_ATTRIBUTE_FILESYSTEM_SIZE)
    bytes_free = _get_info_size_value(info, Gio.FILE_ATTRIBUTE_FILESYSTEM_FREE)
    return bytes_total, bytes_free
