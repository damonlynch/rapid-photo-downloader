# Copyright (C) 2015-2021 Damon Lynch <damonlynch@gmail.com>
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

__author__ = "Damon Lynch"
__copyright__ = (
    "Copyright 2011-2021, Damon Lynch. Copyright 2008-2015 Canonical Ltd. Copyright"
    " 2013 Bernard Baeyens."
)

import functools
import logging
import os
import re
import sys
import time
import pwd
from pathlib import Path
from collections import namedtuple
import shutil
from typing import Optional, Tuple, List, Dict, Set
from urllib.request import pathname2url
from urllib.parse import quote
from tempfile import NamedTemporaryFile

from PyQt5.QtCore import (
    QStorageInfo,
    QObject,
    pyqtSignal,
    QFileSystemWatcher,
    pyqtSlot,
    QTimer,
    QStandardPaths,
)
from showinfm import linux_desktop, LinuxDesktop, valid_file_manager

import gi

from raphodo.wslutils import (
    wsl_home,
    wsl_pictures_folder,
    wsl_videos_folder,
    wsl_conf_mnt_location,
    wsl_filter_directories,
)

gi.require_version("GUdev", "1.0")
gi.require_version("UDisks", "2.0")
gi.require_version("GExiv2", "0.10")
gi.require_version("GLib", "2.0")
from gi.repository import GUdev, UDisks, GLib


from raphodo.constants import Distro, PostCameraUnmountAction
from raphodo.utilities import (
    log_os_release,
    remove_topmost_directory_from_path,
)

logging_level = logging.DEBUG

try:
    from gi.repository import Gio

    have_gio = True
except ImportError:
    have_gio = False

StorageSpace = namedtuple("StorageSpace", "bytes_free, bytes_total, path")
CameraDetails = namedtuple(
    "CameraDetails", "model, port, display_name, is_mtp, storage_desc"
)
UdevAttr = namedtuple(
    "UdevAttr", "is_mtp_device, vendor, model, is_apple_mobile, serial"
)

PROGRAM_DIRECTORY = "rapid-photo-downloader"

try:
    _linux_desktop = linux_desktop()
except Exception:
    _linux_desktop = LinuxDesktop.unknown


def guess_distro() -> Distro:
    """
    Guess distro support by checking package manager support
    :return:
    """

    if shutil.which("apt") or shutil.which("apt-get"):
        return Distro.debian_derivative
    if shutil.which("dnf"):
        return Distro.fedora_derivative
    return Distro.unknown


def parse_os_release() -> Dict[str, str]:
    """
    Sync with code in install.py
    """

    d = {}
    if os.path.isfile("/etc/os-release"):
        with open("/etc/os-release", "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    k, v = line.split("=", maxsplit=1)
                    v = v.strip("'\"")
                    d[k] = v
    return d


# Keep up to date with parse_distro_details() with code in install.py


def get_distro() -> Distro:
    """
    Determine the Linux distribution using /etc/os-release
    :param os_release: parsed /etc/os-release file
    """

    os_release = parse_os_release()
    name = os_release.get("NAME")

    distro = None

    if name:
        if "Ubuntu" in name:
            distro = Distro.ubuntu
        if "Fedora" in name:
            distro = Distro.fedora
        if "CentOS Linux" in name:
            version_id = os_release.get("VERSION_ID")
            if version_id == "7":
                distro = Distro.centos7
            else:
                distro = Distro.centos8
        if "CentOS Stream" in name:
            version_id = os_release.get("VERSION_ID")
            if version_id == "8":
                distro = Distro.centos_stream8
            else:
                distro = Distro.centos_stream9
        if "Linux Mint" in name:
            distro = Distro.linuxmint
        if "elementary" in name:
            distro = Distro.elementary
        if "openSUSE" in name:
            distro = Distro.opensuse
        if "Deepin" in name:
            distro = Distro.deepin
        if "KDE neon" in name:
            distro = Distro.neon
        if "Zorin" in name:
            distro = Distro.zorin
        if "Kylin" in name:
            distro = Distro.kylin
        if "Pop!_OS" in name:
            distro = Distro.popos
        if "Raspbian" in name:
            distro = Distro.raspbian
        if "Debian" in name:
            distro = Distro.debian
        if "Manjaro" in name:
            distro = Distro.manjaro
        if "Gentoo" in name:
            distro = Distro.gentoo

    if distro is None:
        idlike = os_release.get("ID_LIKE")
        if idlike:
            if "arch" in idlike:
                distro = Distro.arch
            if "ubuntu" in idlike:
                distro = Distro.ubuntu_derivative
            if "debian" in idlike:
                distro = Distro.debian_derivative
            if "fedora" in idlike:
                distro = Distro.fedora_derivative

    if distro is None:
        distro = guess_distro()

    return distro


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
        display_name = _("File system root")
    else:
        display_name = os.path.basename(path)
    return display_name, path


@functools.lru_cache(maxsize=None)
def get_media_dir() -> str:
    """
    Returns the media directory, i.e. where external mounts are mounted.

    Assumes mount point of /media/<USER>.

    """

    if sys.platform.startswith("linux"):
        if _linux_desktop == LinuxDesktop.wsl2:
            return wsl_conf_mnt_location()

        media_dir = "/media/{}".format(get_user_name())
        run_media_dir = "/run/media"
        distro = get_distro()
        if os.path.isdir(run_media_dir) and distro not in (
            Distro.ubuntu,
            Distro.debian,
            Distro.neon,
            Distro.galliumos,
            Distro.peppermint,
            Distro.elementary,
            Distro.zorin,
            Distro.popos,
        ):
            if distro not in (
                Distro.fedora,
                Distro.manjaro,
                Distro.arch,
                Distro.opensuse,
                Distro.gentoo,
                Distro.centos8,
                Distro.centos_stream8,
                Distro.centos_stream9,
                Distro.centos7,
            ):
                logging.debug(
                    "Detected /run/media directory, but distro does not appear "
                    "to be CentOS, Fedora, Arch, openSUSE, Gentoo, or Manjaro"
                )
                log_os_release()
            return run_media_dir
        return media_dir
    else:
        raise ("Mounts.setValidMountPoints() not implemented on %s", sys.platform)


_gvfs_gphoto2 = re.compile("gvfs.*gphoto2.*host")


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


class ValidMounts:
    r"""
    Operations to find 'valid' mount points, i.e. the places in which
    it's sensible for a user to mount a partition. Valid mount points:
    include /home/<USER> , /media/<USER>, and /run/media/<USER>
    include directories in /etc/fstab, except /, /home, and swap
    However if only considering external mounts, the the mount must be
    under /media/<USER> or /run/media/<user>
    """

    def __init__(self, only_external_mounts: bool):
        """
        :param only_external_mounts: if True, valid mounts must be under
        /media/<USER>, /run/media/<user>, or if WSL2 /mnt/
        """
        self.validMountFolders = None  # type: Optional[Tuple[str]]
        self.only_external_mounts = only_external_mounts
        self.is_wsl2 = _linux_desktop == LinuxDesktop.wsl2
        self._setValidMountFolders()
        assert "/" not in self.validMountFolders
        if logging_level == logging.DEBUG:
            self.logValidMountFolders()

    def isValidMountPoint(self, mount: QStorageInfo) -> bool:
        """
        Determine if the path of the mount point starts with a valid
        path
        :param mount: QStorageInfo to be tested
        :return:True if mount is a mount under a valid mount, else False
        """
        root_path = mount.rootPath()
        if self.is_wsl2:
            for path in wsl_filter_directories():
                if root_path.startswith(path):
                    return False
        for m in self.validMountFolders:
            if root_path.startswith(m):
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

        if not sys.platform.startswith("linux"):
            raise ("Mounts.setValidMountPoints() not implemented on %s", sys.platform)
        else:
            try:
                media_dir = get_media_dir()
            except:
                logging.critical("Unable to determine username of this process")
                media_dir = ""
            logging.debug("Media dir is %s", media_dir)
            if self.only_external_mounts:
                self.validMountFolders = (media_dir,)
            else:
                home_dir = os.path.expanduser("~")
                validPoints = [home_dir, media_dir]
                for point in self.mountPointInFstab():
                    validPoints.append(point)
                self.validMountFolders = tuple(validPoints)

    def mountPointInFstab(self):
        """
        Yields a list of mount points in /etc/fstab
        The mount points will exclude /, /home, and swap
        """

        with open("/etc/fstab") as f:
            l = []
            for line in f:
                # As per fstab specs: white space is either Tab or space
                # Ignore comments, blank lines
                # Also ignore swap file (mount point none), root, and /home
                m = re.match(
                    r"^(?![\t ]*#)\S+\s+(?!(none|/[\t ]|/home))(" r"?P<point>\S+)", line
                )
                if m is not None:
                    yield (m.group("point"))

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
                msg += "{} or {}".format(
                    self.validMountFolders[-2], self.validMountFolders[-1]
                )
            elif len(self.validMountFolders) == 2:
                msg += "{} or {}".format(
                    self.validMountFolders[0], self.validMountFolders[1]
                )
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
        logging.error(
            "Unknown error occurred while probing potential source folder %s", path
        )
        return False
    return False


def get_desktop_environment() -> Optional[str]:
    """
    Determine desktop environment using environment variable XDG_CURRENT_DESKTOP

    :return: str with XDG_CURRENT_DESKTOP value
    """

    return os.getenv("XDG_CURRENT_DESKTOP")


def _platform_special_dir(
    dir_type: QStandardPaths, home_on_failure: bool = True
) -> Optional[str]:
    """
    Use Qt to query the platforms standard paths

    :param dir_type: one of Qt's standard paths
    :param home_on_failure: return the home directory if the special path cannot
     be located
    :return: the directory, or None if it cannot be determined
    """

    path = QStandardPaths.writableLocation(dir_type)
    if path:
        return path
    elif home_on_failure:
        try:
            return str(Path.home())
        except RuntimeError:
            logging.error("Unable to determine home directory")
    return None


def platform_photos_directory(home_on_failure: bool = True) -> Optional[str]:
    """
    Get localized version of /home/<USER>/Pictures

    :param home_on_failure: if the directory does not exist, return
     the home directory instead
    :return: the directory if it is specified, else the user's
    home directory or None
    """

    if _linux_desktop == LinuxDesktop.wsl2:
        try:
            return wsl_pictures_folder()
        except Exception as e:
            logging.error("Error querying Windows registry: %s", str(e))
        path = wsl_home()
        if path.is_dir():
            return str(path / "Pictures")
    return _platform_special_dir(QStandardPaths.PicturesLocation, home_on_failure)


def platform_videos_directory(home_on_failure: bool = True) -> str:
    """
    Get localized version of /home/<USER>/Videos

    :param home_on_failure: if the directory does not exist, return
     the home directory instead
    :return: the directory if it is specified, else the user's
    home directory or None
    """

    if _linux_desktop == LinuxDesktop.wsl2:
        try:
            return wsl_videos_folder()
        except Exception as e:
            logging.error("Error querying Windows registry: %s", str(e))
        path = wsl_home()
        if path.is_dir():
            return str(path / "Videos")
    return _platform_special_dir(QStandardPaths.MoviesLocation, home_on_failure)


def platform_desktop_directory(home_on_failure: bool = True) -> str:
    """
    Get localized version of /home/<USER>/Desktop

    :param home_on_failure: if the directory does not exist, return
     the home directory instead
    :return: the directory if it is specified, else the user's
    home directory or None
    """
    return _platform_special_dir(QStandardPaths.DesktopLocation, home_on_failure)


def platform_photos_identifier() -> str:
    """
    Get special subfoler indicated by the localized version of /home/<USER>/Pictures
    :return: the subfolder name if it is specified, else the localized version of 'Pictures'
    """

    path = _platform_special_dir(QStandardPaths.PicturesLocation, home_on_failure=False)
    if path is None:
        # translators: the name of the Pictures folder
        return _("Pictures")
    return os.path.basename(path)


def platform_videos_identifier() -> str:
    """
    Get special subfoler indicated by the localized version of /home/<USER>/Pictures
    :return: the subfolder name if it is specified, else the localized version of 'Pictures'
    """

    path = _platform_special_dir(QStandardPaths.MoviesLocation, home_on_failure=False)
    if path is None:
        # translators: the name of the Videos folder
        return _("Videos")
    return os.path.basename(path)


def make_program_directory(path: str) -> str:
    """
    Creates a subfolder used by Rapid Photo Downloader.

    Does not catch errors.

    :param path: location where the subfolder should be
    :return: the full path of the new directory
    """

    program_dir = os.path.join(path, "rapid-photo-downloader")
    if not os.path.exists(program_dir):
        os.mkdir(program_dir)
    elif not os.path.isdir(program_dir):
        os.remove(program_dir)
        os.mkdir(program_dir)
    return program_dir


def get_program_cache_directory(create_if_not_exist: bool = False) -> Optional[str]:
    """
    Get Rapid Photo Downloader cache directory.

    :param create_if_not_exist: creates directory if it does not exist.
    :return: the full path of the cache directory, or None on error
    """

    # Must use GenericCacheLocation, never CacheLocation
    cache_directory = _platform_special_dir(
        QStandardPaths.GenericCacheLocation, home_on_failure=False
    )
    if cache_directory is None:
        logging.error("The platform's cache directory could not be determined")
        return None
    try:
        if not create_if_not_exist:
            return str(Path(cache_directory) / PROGRAM_DIRECTORY)
        else:
            return make_program_directory(cache_directory)
    except OSError:
        logging.error("An error occurred while creating the cache directory")
        return None


def get_program_logging_directory(create_if_not_exist: bool = False) -> Optional[str]:
    """
    Get directory in which to store program log files.

    Log files are kept in the cache directory.

    :param create_if_not_exist: create the directory if it does not exist
    :return: the full path of the logging directory, or None on error
    """

    cache_directory = get_program_cache_directory(
        create_if_not_exist=create_if_not_exist
    )
    if cache_directory is None:
        logging.error("Unable to create logging directory")
        return None
    log_dir = os.path.join(cache_directory, "log")
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

    data_directory = _platform_special_dir(
        QStandardPaths.GenericDataLocation, home_on_failure=False
    )
    if data_directory is None:
        logging.error("The program's data directory could not be determined")
        return None
    if not create_if_not_exist:
        return str(Path(data_directory) / PROGRAM_DIRECTORY)
    else:
        return make_program_directory(data_directory)


def get_fdo_cache_thumb_base_directory() -> str:
    """
    Get the Freedesktop.org thumbnail directory location
    :return: location
    """

    # LXDE is a special case: handle it
    if _linux_desktop == LinuxDesktop.lxde:
        return str(Path.home() / ".thumbnails")

    cache = _platform_special_dir(
        QStandardPaths.GenericCacheLocation, home_on_failure=False
    )
    try:
        return str(Path(cache) / "thumbnails")
    except TypeError:
        logging.error("Could not determine freedesktop.org thumbnail cache location")
        raise "Could not determine freedesktop.org thumbnail cache location"


# Module level variables important for determining among other things the generation of
# URIs
_quoted_comma = quote(",")
_valid_file_manager_probed = False
_valid_file_manager = None  # type: Optional[str]

gvfs_file_managers = (
    "nautilus",
    "caja",
    "thunar",
    "nemo",
    "pcmanfm",
    "peony",
    "pcmanfm-qt",
    "dde-file-manager",
    "io.elementary.files",
)

kframework_file_managers = ("dolphin", "index", "krusader")


def get_uri(
    full_file_name: Optional[str] = None,
    path: Optional[str] = None,
    camera_details: Optional[CameraDetails] = None,
) -> str:
    """
    Generate and return the URI for the file, which varies depending on
    which device the file is located

    :param full_file_name: full filename and path
    :param path: straight path when not passing a full_file_name
    :param camera_details: see named tuple CameraDetails for parameters
    :param desktop_environment: if True, will to generate a URI accepted
     by Gnome, KDE and other desktops, which means adjusting the URI if it appears to be an
     MTP mount. Includes the port too, for cameras. Takes into account
     file manager characteristics.
    :return: the URI
    """

    global _valid_file_manager
    global _valid_file_manager_probed
    if not _valid_file_manager_probed:
        _valid_file_manager = valid_file_manager()
        _valid_file_manager_probed = True

    if camera_details is None:
        prefix = "file://"
    else:
        prefix = ""
        # Attempt to generate a URI accepted by desktop environments
        if camera_details.is_mtp:
            if full_file_name:
                full_file_name = remove_topmost_directory_from_path(full_file_name)
            elif path:
                path = remove_topmost_directory_from_path(path)

            if _valid_file_manager in gvfs_file_managers:
                prefix = "mtp://" + pathname2url(
                    "[{}]/{}".format(camera_details.port, camera_details.storage_desc)
                )
            elif _valid_file_manager in kframework_file_managers:
                prefix = "mtp:/" + pathname2url(
                    "{}/{}".format(
                        camera_details.display_name, camera_details.storage_desc
                    )
                )
            else:
                logging.error(
                    "Don't know how to generate MTP prefix for %s", _valid_file_manager
                )
        else:
            if _valid_file_manager in kframework_file_managers:
                prefix = f"camera:/{pathname2url(camera_details.display_name.replace('-', ' '))}@{camera_details.port}"
            else:
                prefix = "gphoto2://" + pathname2url("[{}]".format(camera_details.port))

        if _valid_file_manager == "pcmanfm-qt":
            # pcmanfm-qt does not like the quoted form of the comma
            prefix = prefix.replace(_quoted_comma, ",")
            if full_file_name:
                # pcmanfm-qt does not like the the filename as part of the path
                full_file_name = os.path.dirname(full_file_name)

    if full_file_name or path:
        uri = "{}{}".format(prefix, pathname2url(full_file_name or path))
    else:
        uri = prefix
    return uri


ValidatedFolder = namedtuple("ValidatedFolder", "valid, absolute_path")


def validate_download_folder(
    path: Optional[str], write_on_waccesss_failure: bool = False
) -> ValidatedFolder:
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
        return ValidatedFolder(False, "")
    absolute_path = os.path.abspath(path)
    valid = os.path.isdir(path) and os.access(path, os.W_OK)
    if not valid and write_on_waccesss_failure and os.path.isdir(path):
        try:
            with NamedTemporaryFile(dir=path):
                # the path is in fact writeable -- can happen with NFS
                valid = True
        except Exception:
            logging.warning(
                "While validating download / backup folder, failed to write a temporary file to "
                "%s",
                path,
            )

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
        return ValidatedFolder(False, "")
    absolute_path = os.path.abspath(path)
    valid = os.path.isdir(path) and os.access(path, os.R_OK)
    return ValidatedFolder(valid, absolute_path)


def udev_attributes(devname: str) -> Optional[UdevAttr]:
    """
    Query udev to see if device is an MTP device.

    :param devname: udev DEVNAME e.g. '/dev/bus/usb/001/003'
    :return True if udev property ID_MTP_DEVICE == '1', else False
    """

    client = GUdev.Client(subsystems=["usb", "block"])
    enumerator = GUdev.Enumerator.new(client)
    enumerator.add_match_property("DEVNAME", devname)
    for device in enumerator.execute():
        model = device.get_property("ID_MODEL")  # type: str
        if model is not None:
            is_mtp = (
                device.get_property("ID_MTP_DEVICE") == "1"
                or device.get_property("ID_MEDIA_PLAYER") == "1"
            )
            vendor = device.get_property("ID_VENDOR")  # type: str
            model = model.replace("_", " ").strip()
            vendor = vendor.replace("_", " ").strip()

            is_apple_mobile = False
            if device.has_sysfs_attr("configuration"):
                config = device.get_sysfs_attr("configuration")
                if config is not None:
                    is_apple_mobile = config.lower().find("apple mobile") >= 0

            if not is_apple_mobile and vendor.lower().find("apple") >= 0:
                logging.warning(
                    "Setting Apple device detected to True even though Apple Mobile "
                    "UDEV configuration not set because vendor is %s",
                    vendor,
                )
                is_apple_mobile = True

            if device.has_sysfs_attr("serial"):
                serial = device.get_sysfs_attr("serial")
                logging.debug("Device serial: %s", serial)
            else:
                serial = None

            if is_apple_mobile:
                if serial:
                    logging.debug(
                        "Detected using udev Apple Mobile device at %s with serial %s",
                        devname,
                        serial,
                    )
                else:
                    logging.warning(
                        "Detected using udev Apple Mobile device at %s but could not "
                        "determine serial number",
                        devname,
                    )

            return UdevAttr(is_mtp, vendor, model, is_apple_mobile, serial)
    return None


def udev_is_camera(devname: str) -> bool:
    """
    Query udev to see if device is a gphoto2 device (a camera or phone)
    :param devname: udev DEVNAME e.g. '/dev/bus/usb/001/003'
    :return: True if so, else False
    """

    client = GUdev.Client(subsystems=["usb", "block"])
    enumerator = GUdev.Enumerator.new(client)
    enumerator.add_match_property("DEVNAME", devname)
    for device in enumerator.execute():
        if device.get_property("ID_GPHOTO2") == "1":
            return True
    return False


def fs_device_details(path: str) -> Tuple:
    """
    :return: device (volume) name, uri, root path and filesystem type
     of the mount the path is on
    """
    qsInfo = QStorageInfo(path)
    name = qsInfo.displayName()
    root_path = qsInfo.rootPath()
    uri = "file://{}".format(pathname2url(root_path))
    fstype = qsInfo.fileSystemType()
    if isinstance(fstype, bytes):
        fstype = fstype.decode()
    return name, uri, root_path, fstype


class WatchDownloadDirs(QFileSystemWatcher):
    """
    Create a file system watch to monitor if there are changes to the
    download directories.

    Monitors the parent directory because we need to monitor it to detect if the
    download directory has been removed.
    """

    def updateWatchPathsFromPrefs(self, prefs) -> None:
        """
        Update the watched directories using values from the program preferences
        :param prefs: program preferences
        :type prefs: raphodo.preferences.Preferences
        """

        logging.debug("Updating watched paths")

        paths = (
            os.path.dirname(path)
            for path in (prefs.photo_download_folder, prefs.video_download_folder)
        )
        watch = {path for path in paths if path}

        existing_watches = set(self.directories())

        if watch == existing_watches:
            return

        new = watch - existing_watches
        if new:
            new = list(new)
            logging.debug("Adding to watched paths: %s", ", ".join(new))
            failures = self.addPaths(new)
            if failures:
                logging.debug("Failed to add watched paths: %s", failures)

        old = existing_watches - watch
        if old:
            old = list(old)
            logging.debug("Removing from watched paths: %s", ", ".join(old))
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
        self.client = GUdev.Client(subsystems=["usb", "block"])
        self.client.connect("uevent", self.ueventCallback)
        logging.debug("... camera hotplug monitor started")
        self.enumerateCameras()
        if self.cameras:
            logging.info(
                "Camera Hotplug found %d camera(s): %s",
                len(self.cameras),
                ", ".join((model for port, model in self.cameras.items())),
            )
            for port, model in self.cameras.items():
                logging.debug("%s is at %s", model, port)

    def enumerateCameras(self):
        """
        Query udev to get the list of cameras store their path and
        model in our internal dict, which is useful when responding to
        camera removal.
        """
        enumerator = GUdev.Enumerator.new(self.client)
        enumerator.add_match_property("ID_GPHOTO2", "1")
        for device in enumerator.execute():
            model = device.get_property("ID_MODEL")
            if model is not None:
                path = device.get_sysfs_path()
                self.cameras[path] = model

    def ueventCallback(
        self, client: GUdev.Client, action: str, device: GUdev.Device
    ) -> None:

        # for key in device.get_property_keys():
        #     print(key, device.get_property(key))
        if device.get_property("ID_GPHOTO2") == "1":
            self.camera(action, device)

    def camera(self, action: str, device: GUdev.Device) -> None:
        # For some reason, the add and remove camera event is triggered twice.
        # The second time the device information is a variation on information
        # from the first time.
        path = device.get_sysfs_path()
        parent_device = device.get_parent()
        parent_path = parent_device.get_sysfs_path()
        logging.debug(
            "Device change: %s. Path: %s Parent path: %s", action, path, parent_path
        )
        if device.has_property("ID_VENDOR_FROM_DATABASE"):
            vendor = device.get_property("ID_VENDOR_FROM_DATABASE")
            logging.debug("Device vendor: %s", vendor)
        else:
            vendor = ""

        # 'bind' vs 'add' action: see https://lwn.net/Articles/837033/

        if action == "bind":
            if parent_path not in self.cameras:
                model = ""

                if device.has_property("ID_MODEL"):
                    model = device.get_property("ID_MODEL")
                    model = model.replace("_", " ")
                    camera_path = path
                else:
                    camera_path = parent_path

                name = model or vendor or "unknown camera"

                logging.info("Hotplug: new camera: %s", name)
                self.cameras[camera_path] = name
                self.cameraAdded.emit()
            else:
                logging.debug(
                    "Hotplug: already know about %s", self.cameras[parent_path]
                )

        elif action == "remove":
            emit_remove = False
            name = ""

            # A path might look like:
            # /sys/devices/pci0000:00/0000:00:1c.6/0000:0e:00.0/usb3/3-2/3-2:1.0
            # When what we want is:
            # /sys/devices/pci0000:00/0000:00:1c.6/0000:0e:00.0/usb3/3-2
            # This unchanged path used to work, so test both the unchanged and modified
            # path
            # Note enumerateCameras() above finds only the path as in the 2nd type, without the
            # 3-2:1.0
            split_path = os.path.split(path)[0]

            for p in (path, split_path):
                if p in self.cameras:
                    name = self.cameras[p]
                    logging.debug("Hotplug: removing '%s' on basis of path %s", name, p)
                    del self.cameras[p]
                    emit_remove = True
                    break

            if emit_remove:
                logging.info("Hotplug: '%s' has been removed", name)
                self.cameraRemoved.emit()
            else:
                logging.debug(
                    "Not responding to device removal: '%s'",
                    vendor or device.get_sysfs_path(),
                )


class UDisks2Monitor(QObject):
    # Most of this class is Copyright 2008-2015 Canonical

    partitionMounted = pyqtSignal(str, "PyQt_PyObject", bool)
    partitionUnmounted = pyqtSignal(str)

    loop_prefix = "/org/freedesktop/UDisks2/block_devices/loop"
    not_interesting = (
        "/org/freedesktop/UDisks2/block_devices/dm_",
        "/org/freedesktop/UDisks2/block_devices/ram",
        "/org/freedesktop/UDisks2/block_devices/zram",
    )

    def __init__(self, validMounts: ValidMounts, prefs) -> None:
        super().__init__()
        self.prefs = prefs
        self.validMounts = validMounts

    @pyqtSlot()
    def startMonitor(self) -> None:
        self.udisks = UDisks.Client.new_sync(None)
        self.manager = self.udisks.get_object_manager()
        self.manager.connect(
            "object-added", lambda man, obj: self._udisks_obj_added(obj)
        )
        self.manager.connect(
            "object-removed", lambda man, obj: self._device_removed(obj)
        )

        # Track the paths of the mount points, which is useful when unmounting
        # objects.
        self.known_mounts = {}  # type: Dict[str, str]
        for obj in self.manager.get_objects():
            path = obj.get_object_path()
            fs = obj.get_filesystem()
            if fs:
                mount_points = fs.get_cached_property(
                    "MountPoints"
                ).get_bytestring_array()
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
        is_system = block.get_cached_property("HintSystem").get_boolean()
        is_loop = (
            path.startswith(self.loop_prefix)
            and not block.get_cached_property("ReadOnly").get_boolean()
        )
        if not is_system or is_loop:
            if part:
                self._udisks_partition_added(obj, block, drive, path)

    def _get_drive(self, block) -> Optional[UDisks.Drive]:
        drive_name = block.get_cached_property("Drive").get_string()
        if drive_name != "/":
            return self.udisks.get_object(drive_name).get_drive()
        else:
            return None

    def _udisks_partition_added(self, obj, block, drive, path) -> None:
        logging.debug("UDisks: partition added: %s" % path)
        fstype = block.get_cached_property("IdType").get_string()
        logging.debug("Udisks: id-type: %s" % fstype)

        fs = obj.get_filesystem()

        if fs:
            icon_names = self.get_icon_names(obj)

            if drive is not None:
                ejectable = drive.get_property("ejectable")
            else:
                ejectable = False
            mount_point = ""
            if not self.prefs.auto_mount:
                logging.debug(
                    "Not mounting device because auto mount preference is off: %s",
                    path,
                )
                return

            mount_points = fs.get_cached_property("MountPoints").get_bytestring_array()
            if len(mount_points) == 0:
                try:
                    logging.debug("UDisks: attempting to mount %s", path)
                    mount_point = self.retry_mount(fs, fstype)
                    if not mount_point:
                        raise Exception
                    else:
                        logging.debug("UDisks: successfully mounted at %s", mount_point)
                except Exception:
                    logging.error("UDisks: could not mount the device: %s", path)
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
        list_options = ""
        if fstype == "vfat":
            list_options = "flush"
        elif fstype == "ext2":
            list_options = "sync"
        G_VARIANT_TYPE_VARDICT = GLib.VariantType.new("a{sv}")
        param_builder = GLib.VariantBuilder.new(G_VARIANT_TYPE_VARDICT)
        optname = GLib.Variant.new_string("fstype")  # s
        value = GLib.Variant.new_string(fstype)
        vvalue = GLib.Variant.new_variant(value)  # v
        newsv = GLib.Variant.new_dict_entry(optname, vvalue)  # {sv}
        param_builder.add_value(newsv)
        optname = GLib.Variant.new_string("options")
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
                if not "UDisks2.Error.DeviceBusy" in e.message:
                    raise
                logging.debug("Udisks: Device busy.")
                time.sleep(0.3)
                timeout -= 1
        return ""

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
        else:
            logging.debug(
                "Taking no action on device removal because of unrecognized path: %s",
                path,
            )

    def get_can_eject(self, obj: UDisks.Object) -> bool:
        block = obj.get_block()
        drive = self._get_drive(block)
        if drive is not None:
            return drive.get_property("ejectable")
        return False

    @staticmethod
    def _object_path(device_path: str) -> str:
        """
        Determine object path used by UDisks2 for device path

        :param device_path: system path of the device to check,
        e.g. /dev/sdc1
        """
        return f"/org/freedesktop/UDisks2/block_devices/{os.path.split(device_path)[1]}"

    def get_device_props(self, device_path: str) -> Tuple[List[str], bool]:
        """
        Given a device, get the icon names suggested by udev, and
        determine whether the mount is ejectable or not.
        :param device_path: system path of the device to check,
        e.g. /dev/sdc1
        :return: icon names and eject boolean
        """

        object_path = self._object_path(device_path)
        obj = self.udisks.get_object(object_path)
        if obj is None:
            icon_names = []
            can_eject = False
        else:
            icon_names = self.get_icon_names(obj)
            can_eject = self.get_can_eject(obj)
        return icon_names, can_eject

    def add_device(self, device_path: str, mount_point: str) -> None:
        object_path = self._object_path(device_path)
        self.known_mounts[object_path] = mount_point

    @pyqtSlot(str)
    def unmount_volume(self, mount_point: str) -> None:

        G_VARIANT_TYPE_VARDICT = GLib.VariantType.new("a{sv}")
        param_builder = GLib.VariantBuilder.new(G_VARIANT_TYPE_VARDICT)

        # Variant parameter construction Copyright Bernard Baeyens, and is
        # licensed under GNU General Public License Version 2 or higher.
        # https://github.com/berbae/udisksvm

        optname = GLib.Variant.new_string("force")
        value = GLib.Variant.new_boolean(False)
        vvalue = GLib.Variant.new_variant(value)
        newsv = GLib.Variant.new_dict_entry(optname, vvalue)
        param_builder.add_value(newsv)

        vparam = param_builder.end()  # a{sv}

        path = None
        # Get the path from the dict we keep of known mounts
        for key, value in self.known_mounts.items():
            if value == mount_point:
                path = key
                break
        if path is None:
            logging.error(
                "Could not find UDisks2 path used to be able to unmount %s", mount_point
            )

        fs = None
        for obj in self.manager.get_objects():
            opath = obj.get_object_path()
            if path == opath:
                fs = obj.get_filesystem()
        if fs is None:
            logging.error(
                "Could not find UDisks2 filesystem used to be able to unmount %s",
                mount_point,
            )

        logging.debug("Unmounting %s...", mount_point)
        try:
            fs.call_unmount(
                vparam, None, self.umount_volume_callback, (mount_point, fs)
            )
        except GLib.GError:
            value = sys.exc_info()[1]
            logging.error("Unmounting failed with error:")
            logging.error("%s", value)

    def umount_volume_callback(
        self,
        source_object: UDisks.FilesystemProxy,
        result: Gio.AsyncResult,
        user_data: Tuple[str, UDisks.Filesystem],
    ) -> None:
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
            logging.error("Exception occurred unmounting %s", mount_point)
            logging.exception("Traceback:")
        except:
            logging.error("Exception occurred unmounting %s", mount_point)
            logging.exception("Traceback:")

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

        # result (unmount succeeded or not), camera model, port, post unmount action
        cameraUnmounted = pyqtSignal(bool, str, str, PostCameraUnmountAction)

        cameraMounted = pyqtSignal()

        # path, icon names, volume can eject
        partitionMounted = pyqtSignal(str, "PyQt_PyObject", bool)

        # path
        partitionUnmounted = pyqtSignal(str)

        volumeAddedNoAutomount = pyqtSignal()
        cameraPossiblyRemoved = pyqtSignal()

        # device path
        cameraVolumeAdded = pyqtSignal(str)

        def __init__(self, validMounts: ValidMounts, prefs) -> None:
            super().__init__()
            self.prefs = prefs
            self.vm = Gio.VolumeMonitor.get()
            self.vm.connect("mount-added", self.mountAdded)
            self.vm.connect("volume-added", self.volumeAdded)
            self.vm.connect("mount-removed", self.mountRemoved)
            self.vm.connect("volume-removed", self.volumeRemoved)
            self.portSearch = re.compile(r"usb:([\d]+),([\d]+)")
            self.scsiPortSearch = re.compile(r"usbscsi:(.+)")
            self.possibleCamera = re.compile(r"/usb/([\d]+)/([\d]+)")
            self.validMounts = validMounts
            # device_path: volume_name
            self.camera_volumes_added = dict()  # type: Dict[str, str]
            self.camera_volumes_mounted = set()  # type: Set[str]

            self.manually_mounted_volumes = set()  # type: Set[Gio.Volume]

        @staticmethod
        def mountMightBeCamera(mount: Gio.Mount) -> bool:
            """
            :param mount: the mount to check
            :return: True if the mount needs to be checked if it is a camera
            """
            return not mount.is_shadowed() and mount.get_volume() is not None

        def unixDevicePathIsCamera(self, devname: str) -> bool:
            """
            Test if the device at unix device path devname is a camera
            :param devname: Gio.VOLUME_IDENTIFIER_KIND_UNIX_DEVICE device path
             e.g. '/dev/bus/usb/001/003'
            :return: True if camera else False
            """

            return self.possibleCamera.search(devname) is not None and udev_is_camera(
                devname
            )

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
                device_path = "/dev/bus/usb/{}/{}".format(p1, p2)
                return self.cameraMountPointByUnixDevice(device_path=device_path)
            else:
                p = self.scsiPortSearch.match(port)
                if p is None:
                    logging.error("Unknown camera mount method %s %s", model, port)
                return None

        def cameraMountPointByUnixDevice(self, device_path: str) -> Optional[Gio.Mount]:
            """
            :return: the mount point of the PTP / MTP camera, if it is mounted,
             else None. If camera is not mounted with PTP / MTP, None is
             returned.
            """

            to_unmount = None

            for mount in self.vm.get_mounts():
                if self.mountMightBeCamera(mount):
                    identifier = mount.get_volume().get_identifier(
                        Gio.VOLUME_IDENTIFIER_KIND_UNIX_DEVICE
                    )
                    if device_path == identifier:
                        to_unmount = mount
                        break
            return to_unmount

        @pyqtSlot(str, str, bool, bool, int)
        def reUnmountCamera(
            self,
            model: str,
            port: str,
            post_unmount_action: PostCameraUnmountAction,
            attempt_no: int,
        ) -> None:

            logging.info(
                "Attempt #%s to unmount camera %s on port %s",
                attempt_no + 1,
                model,
                port,
            )
            self.unmountCamera(
                model=model,
                port=port,
                post_unmount_action=post_unmount_action,
                attempt_no=attempt_no,
            )

        def unmountCamera(
            self,
            model: str,
            port: str,
            post_unmount_action: PostCameraUnmountAction,
            mount_point: Optional[Gio.Mount] = None,
            attempt_no: Optional[int] = 0,
        ) -> bool:
            """
            Unmount camera mounted on gvfs mount point, if it is
            mounted. If not mounted, ignore.

            :param model: model as returned by libgphoto2
            :param port: port as returned by libgphoto2, in format like
             usb:001,004
            :param download_starting: if True, the unmount is occurring
             because a download has been initiated.
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
                    0,
                    None,
                    None,
                    self.unmountCameraCallback,
                    (model, port, post_unmount_action, attempt_no),
                )
                return True

            return False

        def unmountCameraCallback(
            self,
            mount: Gio.Mount,
            result: Gio.AsyncResult,
            user_data: Tuple[str, str, PostCameraUnmountAction, bool],
        ) -> None:
            """
            Called by the asynchronous unmount operation.
            When complete, emits a signal indicating operation
            success, and the camera model and port
            :param mount: camera mount
            :param result: result of the unmount process
            :param user_data: model and port of the camera being
            unmounted, in the format of libgphoto2
            """

            model, port, post_unmount_action, attempt_no = user_data
            try:
                if mount.unmount_with_operation_finish(result):
                    logging.debug("...successfully unmounted {}".format(model))
                    self.cameraUnmounted.emit(True, model, port, post_unmount_action)
                else:
                    logging.debug("...failed to unmount {}".format(model))
                    self.cameraUnmounted.emit(False, model, port, post_unmount_action)
            except GLib.GError as e:
                if e.code == 26 and attempt_no < 10:
                    attempt_no += 1
                    QTimer.singleShot(
                        1000,
                        lambda: self.reUnmountCamera(
                            model, port, post_unmount_action, attempt_no
                        ),
                    )
                else:
                    logging.error("Exception occurred unmounting {}".format(model))
                    logging.exception("Traceback:")
                    self.cameraUnmounted.emit(False, model, port, post_unmount_action)

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
                        mount.unmount_with_operation(
                            0, None, None, self.unmountVolumeCallback, path
                        )
                        break

        @staticmethod
        def unmountVolumeCallback(
            mount: Gio.Mount, result: Gio.AsyncResult, user_data: str
        ) -> None:

            """
            Called by the asynchronous unmount operation.

            :param mount: volume mount
            :param result: result of the unmount process
            :param user_data: the path of the device unmounted
            """
            path = user_data

            try:
                if mount.unmount_with_operation_finish(result):
                    logging.info("...successfully unmounted volume %s", path)
                else:
                    logging.info("...failed to unmount volume %s", path)
            except GLib.GError as e:
                if e.code == 16:
                    logging.debug("...backend currently unmounting volume %s...", path)
                elif e.code == 26:
                    logging.debug(
                        "...did not yet unmount volume %s because it is busy..."
                    )
                    # TODO investigate if should try again to unmount the volume, similar to
                    # unmountCameraCallback()
                else:
                    logging.error("Exception occurred unmounting volume %s", path)
                    logging.exception("Traceback:")

        @staticmethod
        def mountIsAppleFileConduit(mount: Gio.Mount, path: str) -> bool:
            if path:
                logging.debug(
                    "GIO: Looking for Apple File Conduit (AFC) at mount {}".format(path)
                )
                path, folder_name = os.path.split(path)
                if folder_name:
                    if folder_name.startswith("afc:host="):
                        return True
            return False

        def mountVolume(self, volume: Gio.Volume) -> None:
            logging.debug("Attempting to mount %s", volume.get_name())
            self.manually_mounted_volumes.add(volume)
            volume.mount(0, None, None, self.mountVolumeCallback, volume)

        def mountVolumeCallback(
            self, source_object, result: Gio.AsyncResult, volume: Gio.Volume
        ) -> None:
            self.manually_mounted_volumes.remove(volume)
            if volume.mount_finish(result):
                logging.debug("%s was successfully manually mounted", volume.get_name())
                self.mountAdded(self.vm, volume.get_mount())
            else:
                logging.debug("%s failed to mount", volume.get_name())

        def mountIsCamera(self, mount: Gio.Mount, path: Optional[str] = None) -> bool:
            """
            Determine if the mount refers to a camera by checking the
            path to see if gphoto2 or mtp is in the last folder in the
            root path.

            Does not query udev, deliberately. This can be called when device
            is being unmounted. Unclear if the device is still on the system
            at this point, or how realible that is even if it is.

            :param mount: mount to check
            :param path: optional mount path if already determined
            :return: True if mount refers to a camera, else False
            """

            if self.mountMightBeCamera(mount):
                if path is None:
                    root = mount.get_root()
                    if root is None:
                        logging.warning(
                            "Unable to get mount root for %s", mount.get_name()
                        )
                    else:
                        path = root.get_path()
                if path:
                    logging.debug("GIO: Looking for camera at mount {}".format(path))
                    # check last two levels of the path name, as it might be in a format like
                    # /run/..../gvfs/gphoto2:host=Canon_Inc._Canon_Digital_Camera/store_00010001
                    for i in (1, 2):
                        path, folder_name = os.path.split(path)
                        if folder_name:
                            for s in ("gphoto2:host=", "mtp:host="):
                                if folder_name.startswith(s):
                                    return True
            return False

        def mountIsPartition(
            self, mount: Gio.Mount, path: Optional[str] = None
        ) -> bool:
            """
            Determine if the mount point is that of a valid partition,
            i.e. is mounted in a valid location, which is under one of
            self.validMountDirs
            :param mount: the mount to examine
            :param path: optional mount path if already determined
            :return: True if the mount is a valid partiion
            """

            if path is None:
                root = mount.get_root()
                if root is None:
                    logging.warning("Unable to get mount root for %s", mount.get_name())
                else:
                    path = root.get_path()
            if path:
                logging.debug(
                    "GIO: Looking for valid partition at mount {}".format(path)
                )
                if self.validMounts.pathIsValidMountPoint(path):
                    logging.debug("GIO: partition found at {}".format(path))
                    return True
            if path is not None:
                logging.debug("GIO: partition is not valid mount: {}".format(path))
            return False

        def mountAdded(self, volumeMonitor, mount: Gio.Mount) -> None:
            """
            Determine if mount is valid partition or is a camera, or something
            else.

            :param volumeMonitor: not used
            :param mount: the mount to examine
            """

            if mount.get_volume() in self.manually_mounted_volumes:
                logging.debug(
                    "Waiting for manual mount of %s to complete",
                    mount.get_volume().get_name(),
                )
                return

            logging.debug("Examining mount %s", mount.get_name())
            try:
                identifier = mount.get_volume().get_identifier(
                    Gio.VOLUME_IDENTIFIER_KIND_UNIX_DEVICE
                )
                if identifier in self.camera_volumes_added:
                    logging.debug(
                        "%s is now mounted", self.camera_volumes_added[identifier]
                    )
                    self.camera_volumes_mounted.add(identifier)
                    self.cameraMounted.emit()
                    return
            except Exception:
                pass

            try:
                path = mount.get_root().get_path()
            except Exception:
                logging.warning("Unable to get mount path for %s", mount.get_name())
            else:
                if self.mountIsAppleFileConduit(mount, path):
                    # An example of an AFC volume is the "Documents" mount for an iPhone, which
                    # in contrast to the gphoto2 mount for the same device
                    logging.debug("Apple File Conduit (AFC) mount detected at %s", path)
                    logging.info("Attempting to unmount %s...", path)
                    mount.unmount_with_operation(
                        0, None, None, self.unmountVolumeCallback, path
                    )
                elif self.mountIsCamera(mount, path):
                    # Can be called on startup if camera was already mounted in GIO before the program
                    # started. In that case, previous check would not have detected the camera.
                    self.cameraMounted.emit()
                elif self.mountIsPartition(mount, path):
                    icon_names = self.getIconNames(mount)
                    self.partitionMounted.emit(
                        mount.get_root().get_path(), icon_names, mount.can_eject()
                    )

        def mountRemoved(self, volumeMonitor, mount: Gio.Mount) -> None:
            if not self.mountIsCamera(mount):
                if self.mountIsPartition(mount):
                    logging.debug("GIO: %s has been unmounted", mount.get_name())
                    self.partitionUnmounted.emit(mount.get_root().get_path())

        def volumeAdded(self, volumeMonitor, volume: Gio.Volume) -> None:
            volume_name = volume.get_name()
            should_automount = volume.should_automount()
            logging.debug(
                "GIO: Volume added %s. Automount: %s",
                volume_name,
                should_automount,
            )

            if not should_automount:
                logging.debug(
                    "%s has probably been removed: do not automount", volume_name
                )
                return

            if not self.prefs.auto_mount:
                logging.debug(
                    "Not checking mount status for %s because auto mount preference "
                    "is off",
                    volume_name,
                )
                return

            # Even if volume.should_automount(), the volume in fact may not be mounted
            # automatically. It's a bug that has shown up at least twice!

            device_path = volume.get_identifier(Gio.VOLUME_IDENTIFIER_KIND_UNIX_DEVICE)
            if device_path is None:
                logging.debug("%s is not a Unix Device", volume_name)
            else:
                try:
                    is_camera = self.unixDevicePathIsCamera(device_path)
                except TypeError:
                    logging.debug(
                        "Unexpected device path for %s. Type %s",
                        volume_name,
                        type(device_path),
                    )
                else:
                    if is_camera:
                        self.camera_volumes_added[device_path] = volume_name
                        logging.debug("%s is a camera at %s", volume_name, device_path)
                        # Time is in milliseconds; 3000 is 3 seconds.
                        QTimer.singleShot(
                            3000, lambda: self.cameraVolumeAddedCheckMount(device_path)
                        )
                    else:
                        uuid = volume.get_uuid()
                        logging.debug(
                            "%s is a device at %s with UUID %s",
                            volume_name,
                            device_path,
                            uuid,
                        )
                        QTimer.singleShot(
                            3000, lambda: self.deviceVolumeAddedCheckMount(volume)
                        )

        def cameraVolumeAddedCheckMount(self, device_path) -> None:
            if device_path not in self.camera_volumes_mounted:
                logging.debug(
                    "%s had not been automatically mounted. Will initiate camera scan.",
                    self.camera_volumes_added[device_path],
                )
                self.cameraVolumeAdded.emit(device_path)
            else:
                logging.debug(
                    "%s had been automatically mounted",
                    self.camera_volumes_added[device_path],
                )

        def deviceVolumeAddedCheckMount(self, volume: Gio.Volume) -> None:
            mount = volume.get_mount()
            if mount is not None:
                # Double check that it's in the list of mounts
                mounted = mount in self.vm.get_mounts()
            else:
                mounted = False

            if not mounted:
                logging.debug(
                    "%s has not been automatically mounted. Will initiate mount.",
                    volume.get_name(),
                )
                self.mountVolume(volume)
            else:
                logging.debug("%s was automatically mounted", volume.get_name())

        def volumeRemoved(self, volumeMonitor, volume: Gio.Volume) -> None:
            logging.debug("GIO: %s volume removed", volume.get_name())
            if volume.get_activation_root() is not None:
                logging.debug("GIO: %s might be a camera", volume.get_name())
                self.cameraPossiblyRemoved.emit()

        @staticmethod
        def getIconNames(mount: Gio.Mount) -> List[str]:
            """
            Get icons for the mount from theme

            :param mount:
            :return:
            """
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
    if info.get_attribute_data(attr).type == Gio.FileAttributeType.UINT64:
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
    info = p.query_filesystem_info(
        ",".join(
            (Gio.FILE_ATTRIBUTE_FILESYSTEM_SIZE, Gio.FILE_ATTRIBUTE_FILESYSTEM_FREE)
        )
    )
    logging.debug("...query of file system attributes for %s completed", path)
    bytes_total = _get_info_size_value(info, Gio.FILE_ATTRIBUTE_FILESYSTEM_SIZE)
    bytes_free = _get_info_size_value(info, Gio.FILE_ATTRIBUTE_FILESYSTEM_FREE)
    return bytes_total, bytes_free
