#!/usr/bin/env python3

# Copyright (C) 2016-2017 Damon Lynch <damonlynch@gmail.com>

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
# along with Rapid Photo Downloader. If not,
# see <http://www.gnu.org/licenses/>.

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2016-2017, Damon Lynch"

import sys
import os
from enum import Enum
from distutils.version import StrictVersion
import pkg_resources
import hashlib
import tempfile
import argparse
import shlex
import subprocess
import platform
import math
import threading
import time
from subprocess import Popen, PIPE
import shutil
import tarfile

__version__ = '0.1'
__title__ = 'Rapid Photo Downloader installer'
__description__ = "Download and install latest version of Rapid Photo Downloader"


try:
    import requests
    have_requests = True
except ImportError:
    have_requests = False

try:
    import apt
    have_apt = True
except ImportError:
    have_apt = False

try:
    import dnf
    have_dnf = True
except ImportError:
    have_dnf = False

try:
    import pip
    have_pip = True
    pip_version = StrictVersion(pip.__version__)
except ImportError:
    have_pip = False
    pip_version = None


try:
    import pyprind
    have_pyprind_progressbar = True
except ImportError:
    have_pyprind_progressbar = False


os_release = '/etc/os-release'


class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class Distro(Enum):
    debian = 1
    ubuntu = 2
    fedora = 3
    neon = 4
    linuxmint = 5
    korora = 6
    arch = 7
    opensuse = 8
    manjaro = 9
    galliumos = 10
    unknown = 20


debian_like = (Distro.debian, Distro.ubuntu, Distro.neon, Distro.linuxmint, Distro.galliumos)
fedora_like = (Distro.fedora, Distro.korora)
arch_like = (Distro.arch, Distro.manjaro)


installer_cmds = {
    Distro.fedora: 'dnf',
    Distro.debian: 'apt-get',
    Distro.opensuse: 'zypper',
}


def get_distro() -> Distro:
    if os.path.isfile(os_release):
        with open(os_release, 'r') as f:
            for line in f:
                if line.startswith('NAME=') and line.find('Korora') > 0:
                    return Distro.korora
                if line.startswith('ID='):
                    return get_distro_id(line[3:])
                if line.startswith('ID_LIKE='):
                    return get_distro_id(line[8:])
    return Distro.unknown


def get_distro_id(id_or_id_like: str) -> Distro:
    try:
        return Distro[id_or_id_like.strip()]
    except KeyError:
        return Distro.unknown


def get_distro_version(distro: Distro) -> float:
    remove_quotemark = False
    if distro == Distro.fedora:
        version_string = 'REDHAT_BUGZILLA_PRODUCT_VERSION='
    elif distro in debian_like or distro == Distro.opensuse:
        version_string = 'VERSION_ID="'
        remove_quotemark = True
    elif distro == Distro.korora:
        version_string = 'VERSION_ID='
    else:
        return 0.0

    with open(os_release, 'r') as f:
        for line in f:
            if line.startswith(version_string):
                try:
                    if remove_quotemark:
                        v = line[len(version_string):-2]
                    else:
                        v = line[len(version_string):]
                    return float(v)
                except ValueError:
                    sys.stderr.write("Unexpected format while parsing {} version\n".format(
                        distro.name.capitalize()))
                    return 0.0
    return 0.0


def is_debian_testing_or_unstable() -> bool:
    with open(os_release, 'r') as f:
        for line in f:
            if line.startswith('PRETTY_NAME'):
                return 'buster' in line or 'sid' in line
    return False


def pypi_pyqt5_capable() -> bool:
    return platform.machine() == 'x86_64' and platform.python_version_tuple()[1] in ('5', '6')


def make_pip_command(args: str, split: bool=True):
    cmd_line = '{} -m pip --disable-pip-version-check {}'.format(sys.executable, args)
    if split:
        return shlex.split(cmd_line)
    else:
        return cmd_line


def make_distro_packager_commmand(distro_family: Distro,
                                  packages: str,
                                  interactive: bool,
                                  command: str='install',
                                  sudo: bool=True) -> str:

    installer = installer_cmds[distro_family]
    cmd = shutil.which(installer)

    if interactive:
        automatic = ''
    else:
        automatic = '-y'

    if sudo:
        super = 'sudo '
    else:
        super = ''


    return '{}{} {} {} {}'.format(super, cmd, automatic, command, packages)


def custom_python() -> bool:
    return not sys.executable.startswith('/usr/bin/python')


def user_pip() -> bool:
    args = make_pip_command('--version')
    try:
        v = subprocess.check_output(args, universal_newlines=True)
        return os.path.expanduser('~/.local/lib/python3') in v
    except Exception:
        return False


def pip_package(package: str, local_pip: bool) -> str:
    return package if local_pip else 'python3-{}'.format(package)


def get_yes_no(response: str) -> bool:
    return response.lower() in ('y', 'yes', '')


def run_cmd(command_line: str,
            restart=False,
            exit_on_failure=True,
            shell=False,
            interactive=False) -> None:

    print("The following command will be run:\n")
    print(command_line)
    if command_line.startswith('sudo'):
        print("\nsudo may prompt you for the sudo password.")
    print()

    if interactive:
        answer = input('Would you like to run the command now? [Y/n]: ')
        if not get_yes_no(answer):
            print('Answer is not yes, exiting.')
            sys.exit(0)

    args = shlex.split(command_line)

    print()

    try:
        subprocess.check_call(args, shell=shell)
    except subprocess.CalledProcessError:
        sys.stderr.write("Command failed\n")
        if exit_on_failure:
            sys.stderr.write("Exiting\n")
            sys.exit(1)
    else:
        if restart:
            sys.stdout.flush()
            sys.stderr.flush()
            # restart the script
            os.execl(sys.executable, sys.executable, *sys.argv)


def enable_universe(interacive: bool):
    try:
        repos = subprocess.check_output(['apt-cache', 'policy'], universal_newlines=True)
        version = subprocess.check_output(['lsb_release', '-sc'], universal_newlines=True).strip()
        if not '{}/universe'.format(version) in repos and version not in (
                'sarah', 'serena', 'sonya'):
            print("The Universe repository must be enabled.\n")
            run_cmd(
                command_line='sudo add-apt-repository universe', restart=False,
                interactive=interacive
            )
            run_cmd(command_line='sudo apt update', restart=True, interactive=interacive)

    except Exception:
        pass


def query_uninstall(interactive: bool) -> bool:
    if not interactive:
        return True

    answer = input(
        '\nDo you want to to uninstall the previous version of Rapid Photo Downloader: [Y/n]'
    )
    return get_yes_no(answer)


def opensuse_missing_packages(packages: str):
    command_line = make_distro_packager_commmand(Distro.opensuse, packages, True, 'se', False)
    args = shlex.split(command_line)
    output = subprocess.check_output(args, universal_newlines=True)
    return [package for package in packages.split() if '\ni | {}'.format(package) not in output]


def opensuse_package_installed(package) -> bool:
    return not opensuse_missing_packages(package)


def uninstall_old_version(distro_family: Distro, interactive: bool) -> None:
    pkg_name = 'rapid-photo-downloader'

    if distro_family == Distro.debian:
        try:
            cache = apt.Cache()
            pkg = cache[pkg_name]
            if pkg.is_installed and query_uninstall(interactive):
                run_cmd(make_distro_packager_commmand(distro, pkg_name, interactive, 'remove'))
        except Exception:
            pass

    elif distro_family == Distro.fedora:
        print("Querying package system to see if an older version of Rapid Photo Downloader is "
              "installed (this may take a while)...")
        with dnf.Base() as base:
            base.read_all_repos()
            try:
                base.fill_sack()
            except dnf.exceptions.RepoError as e:
                print("Unable to query package system. Please check your internet connection and "
                      "try again")
                sys.exit(1)

            q = base.sack.query()
            q_inst = q.installed()
            i = q_inst.filter(name=pkg_name)
            if len(list(i)) and query_uninstall(interactive):
                run_cmd(make_distro_packager_commmand(distro, pkg_name, interactive, 'remove'))

    elif distro_family == Distro.opensuse:
        print("Querying package system to see if an older version of Rapid Photo Downloader is "
              "installed (this may take a while)...")

        if opensuse_package_installed('rapid-photo-downloader') and query_uninstall(interactive):
            run_cmd(make_distro_packager_commmand(distro, pkg_name, interactive, 'rm'))

    # explicitly uninstall any previous version installed with pip
    print("Checking if previous version installed with pip...")
    l_command_line = 'list --user --disable-pip-version-check'
    if pip_version >= StrictVersion('9.0.0'):
        l_command_line = '{} --format=columns'.format(l_command_line)
    l_args = make_pip_command(l_command_line)

    u_command_line = 'uninstall --disable-pip-version-check -y rapid-photo-downloader'
    u_args = make_pip_command(u_command_line)
    while True:
        try:
            output = subprocess.check_output(l_args, universal_newlines=True)
            if 'rapid-photo-downloader' in output:
                try:
                    subprocess.check_call(u_args)
                except subprocess.CalledProcessError:
                    print("Encountered an error uninstalling previous version installed with pip")
                    break
            else:
                break
        except Exception:
            break


def check_packages_on_other_systems() -> None:
    """
    Check to see if some (but not all) application dependencies are
    installed on systems that we are not explicitly analyzing.
    """

    import_msgs = []

    if not pypi_pyqt5_capable():
        try:
            import PyQt5
        except ImportError:
            import_msgs.append('python3 variant of PyQt5')
    try:
        import gi
        have_gi = True
    except ImportError:
        import_msgs.append('python3 variant of gobject introspection')
        have_gi = False
    if have_gi:
        try:
            gi.require_version('GUdev', '1.0')
        except ValueError:
            import_msgs.append('GUdev 1.0 from gi.repository')
        try:
            gi.require_version('UDisks', '2.0')
        except ValueError:
            import_msgs.append('UDisks 2.0 from gi.repository')
        try:
             gi.require_version('GLib', '2.0')
        except ValueError:
            import_msgs.append('GLib 2.0 from gi.repository')
        try:
            gi.require_version('GExiv2', '0.10')
        except ValueError:
            import_msgs.append('GExiv2 0.10 from gi.repository')
        try:
            gi.require_version('Gst', '1.0')
        except ValueError:
            import_msgs.append('Gst 1.0 from gi.repository')
        try:
            gi.require_version('Notify', '0.7')
        except ValueError:
            import_msgs.append('Notify 0.7 from gi.repository')
    if shutil.which('exiftool') is None:
        import_msgs.append('ExifTool')
    if len(import_msgs):
        install_error_message = "This program requires:\n{}\nPlease install them " \
                                "using your distribution's standard installation tools.\n"
        sys.stderr.write(install_error_message.format('\n'.join(s for s in import_msgs)))
        sys.exit(1)


def check_package_import_requirements(distro_family: Distro,
                                      version: float,
                                      interactive: bool) -> None:

    if distro_family == Distro.debian:

        cache = apt.Cache()
        missing_packages = []
        packages = 'gstreamer1.0-libav gstreamer1.0-plugins-good ' \
             'libimage-exiftool-perl python3-dev ' \
             'intltool gir1.2-gexiv2-0.10 python3-gi gir1.2-gudev-1.0 ' \
             'gir1.2-udisks-2.0 gir1.2-notify-0.7 gir1.2-glib-2.0 gir1.2-gstreamer-1.0 '\
             'libgphoto2-dev python3-arrow python3-psutil g++ libmediainfo0v5 '\
             'python3-zmq exiv2 python3-colorlog libraw-bin ' \
             'python3-easygui python3-sortedcontainers'

        if not pypi_pyqt5_capable():
            packages = 'qt5-image-formats-plugins python3-pyqt5 {}'.format(packages)

        if not have_requests:
            packages = 'python3-requests {}'.format(packages)

        for package in packages.split():
            try:
                if not cache[package].is_installed:
                    missing_packages.append(package)
            except KeyError:
                    print(
                        'The following package is unknown on your system: {}\n'.format(package)
                    )
                    sys.exit(1)

        if missing_packages:
            print("To continue, some packages required to run the application will be "
                  "installed.\n")
            run_cmd(
                make_distro_packager_commmand(
                    distro_family, ' '.join(missing_packages), interactive
                ), interactive=interactive
            )

    elif distro_family == Distro.fedora:

        missing_packages = []
        packages = 'gstreamer1-libav gstreamer1-plugins-good ' \
                   'gobject-introspection python3-gobject ' \
                   'libgphoto2-devel zeromq-devel exiv2 perl-Image-ExifTool LibRaw-devel gcc-c++ ' \
                   'rpm-build python3-devel intltool ' \
                   'python3-easygui python3-psutil libmediainfo '

        if not pypi_pyqt5_capable():
            packages = 'qt5-qtimageformats python3-qt5 {}'.format(packages)

        if not have_requests:
            packages = 'python3-requests {}'.format(packages)

        if 0.0 < version <= 24.0:
            packages = 'libgexiv2-python3 {}'.format(packages)
        else:
            packages = 'python3-gexiv2 {}'.format(packages)

        print("Querying installed and available packages (this may take a while)")

        with dnf.Base() as base:
            # Code from http://dnf.readthedocs.org/en/latest/use_cases.html

            # Repositories serve as sources of information about packages.
            base.read_all_repos()
            # A sack is needed for querying.
            base.fill_sack()

            # A query matches all packages in sack
            q = base.sack.query()

            # Derived query matches only available packages
            q_avail = q.available()
            # Derived query matches only installed packages
            q_inst = q.installed()

            installed = [pkg.name for pkg in q_inst.run()]
            available = [pkg.name for pkg in q_avail.run()]

            for package in packages.split():
                if package not in installed:
                    if package in available:
                        missing_packages.append(package)
                    elif package == 'gstreamer1-libav':
                        print(
                            bcolors.BOLD + "\nTo be able to generate thumbnails for a wider range "
                            "of video formats, install gstreamer1-libav after having first added "
                            "an appropriate software repository such as rpmfusion.org." +
                            bcolors.ENDC
                        )
                    else:
                        sys.stderr.write(
                            'The following package is unavailable on your system: {}\n'.format(
                                package
                            )
                        )
                        sys.exit(1)

        if missing_packages:
            print("To continue, some packages required to run the application will be "
                  "installed.\n")
            run_cmd(
                make_distro_packager_commmand(
                    distro_family, ' '.join(missing_packages), interactive
                ), interactive=interactive
            )

    elif distro_family == Distro.opensuse:

        packages = 'girepository-1_0 python3-gobject ' \
                   'zeromq-devel exiv2 exiftool python3-devel ' \
                   'libgphoto2-devel libraw-devel gcc-c++ rpm-build intltool ' \
                   'python3-psutil ' \
                   'typelib-1_0-GExiv2-0_10 typelib-1_0-UDisks-2_0 typelib-1_0-Notify-0_7 ' \
                   'typelib-1_0-Gst-1_0 typelib-1_0-GUdev-1_0'

        #TODO libmediainfo - not a default openSUSE package, sadly

        if not pypi_pyqt5_capable():
            packages = 'python3-qt5 libqt5-qtimageformats {}'.format(packages)

        if not have_requests:
            packages = 'python3-requests {}'.format(packages)

        print("Querying zypper to see if any required packages are already installed (this may "
              "take a while)... ")
        missing_packages = opensuse_missing_packages(packages)

        if missing_packages:
            print("To continue, some packages required to run the application will be installed.\n")
            run_cmd(
                make_distro_packager_commmand(
                    distro_family, ' '.join(missing_packages), interactive
                ), interactive=interactive
            )
    else:
        check_packages_on_other_systems()



def parser_options(formatter_class=argparse.HelpFormatter) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=__title__, formatter_class=formatter_class, description=__description__
    )
    parser.add_argument(
        '--version', action='version', version='%(prog)s {}'.format(__version__)
    )
    parser.add_argument(
        "-i", "--interactive",  action="store_true", dest="interactive", default=False,
        help="Query to confirm action at each step."
    )
    parser.add_argument(
        '--devel', action="store_true", dest="devel", default=False,
        help="Install latest development version if it is newer than latest stable version"
    )

    parser.add_argument(
        'tarfile',  action='store', nargs='?',
        help="Optional tar.gz Rapid Photo Downloader installer archive"
    )

    return parser


def verify_download(downloaded_tar: str, md5_url: str) -> bool:
    """
    Verifies downloaded tarball against the launchpad generated md5sum file.

    Exceptions not caught.

    :param downloaded_tar: local file
    :param md5_url: remote md5sum file for the download
    :return: True if md5sum matches, False otherwise,
    """

    if not md5_url:
        return True

    r = requests.get(md5_url)
    assert r.status_code == 200
    remote_md5 = r.text.split()[0]
    with open(downloaded_tar, 'rb') as tar:
        m = hashlib.md5()
        m.update(tar.read())
    return m.hexdigest() == remote_md5


def get_installer_url_md5(devel: bool):
    remote_versions_file = 'https://www.damonlynch.net/rapid/version.json'

    try:
        r = requests.get(remote_versions_file)
    except:
        print("Failed to download versions file", remote_versions_file)
    else:
        status_code = r.status_code
        if status_code != 200:
            print("Got error code {} while accessing versions file".format(status_code))
        else:
            try:
                version = r.json()
            except:
                print("Error %d accessing versions JSON file")
            else:
                stable = version['stable']
                dev = version['dev']

                if devel and \
                        pkg_resources.parse_version(dev['version']) > \
                        pkg_resources.parse_version(stable['version']).version:
                    tarball_url = dev['url']
                    md5 = dev['md5']
                else:
                    tarball_url = stable['url']
                    md5 = stable['md5']

                return tarball_url, md5
    return '', ''


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

    suffixes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']

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


def delete_installer_and_its_temp_dir(full_file_name):
    temp_dir = os.path.dirname(full_file_name)
    if temp_dir:
        shutil.rmtree(temp_dir, ignore_errors=True)


class progress_bar_scanning(threading.Thread):
    # Adapted from http://thelivingpearl.com/2012/12/31/
    # creating-progress-bars-with-python/
    def run(self):
            print('Downloading....  ', end='', flush=True)
            i = 0
            while stop_pbs != True:
                    if (i%4) == 0:
                        sys.stdout.write('\b/')
                    elif (i%4) == 1:
                        sys.stdout.write('\b-')
                    elif (i%4) == 2:
                        sys.stdout.write('\b\\')
                    elif (i%4) == 3:
                        sys.stdout.write('\b|')

                    sys.stdout.flush()
                    time.sleep(0.2)
                    i+=1

            if kill_pbs == True:
                print('\b\b\b\b ABORT!', flush=True)
            else:
                print('\b\b done!', flush=True)


def download_installer(devel):
    tarball_url, md5_url = get_installer_url_md5(devel)
    if not tarball_url:
        sys.stderr.write("Sorry, could not locate installer. Exiting.")
        sys.exit(1)

    temp_dir = tempfile.mkdtemp()

    try:
        r = requests.get(tarball_url, stream=True)
        local_file = os.path.join(temp_dir, tarball_url.split('/')[-1])
        chunk_size = 1024
        total_size = int(r.headers['content-length'])
        size_human = format_size_for_user(total_size)
        print("Downloading {} ({})".format(tarball_url, size_human))
        no_iterations = int(math.ceil(total_size / chunk_size))

        global stop_pbs
        global kill_pbs

        stop_pbs = kill_pbs = False
        if have_pyprind_progressbar:
            bar = pyprind.ProgBar(
                iterations=no_iterations, stream=1, track_time=False, width=80
            )
        else:
            pbs = progress_bar_scanning()
            pbs.start()

        with open(local_file, 'wb') as f:
            for chunk in r.iter_content(chunk_size=chunk_size):
                if chunk:  # filter out keep-alive new chunks
                    f.write(chunk)
                    if have_pyprind_progressbar:
                        bar.update()

        if not have_pyprind_progressbar:
            stop_pbs = True
            pbs.join()

    except Exception:
        sys.stderr.write("Failed to download {}\n".format(tarball_url))
        sys.exit(1)

    try:
        if verify_download(local_file, md5_url):
            return local_file
        else:
            sys.stderr.write("Tar file MD5 mismatch\n")
            delete_installer_and_its_temp_dir(local_file)
            sys.exit(1)
    except Exception:
        sys.stderr.write("There was a problem verifying the download\n")
        delete_installer_and_its_temp_dir(local_file)
        sys.exit(1)

def main(installer: str,
         distro: Distro,
         distro_family: Distro,
         distro_version: float,
         interactive: bool,
         devel: bool) -> None:

    uninstall_old_version(distro_family, interactive)

    check_package_import_requirements(distro_family, distro_version, interactive)

    if installer is None:
        delete_installer = True
        installer = download_installer(devel)
    else:
        delete_installer = False

    name = os.path.basename(installer)
    name = name[:len('.tar.gz') * -1]

    rpath = os.path.join(name, 'requirements.txt')
    with tarfile.open(installer) as tar:
        with tar.extractfile(rpath) as requirements:
            reqbytes = requirements.read()
            if pypi_pyqt5_capable():
                reqbytes = reqbytes.rstrip() + b'\nPyQt5'

            with tempfile.NamedTemporaryFile(delete=False) as temp_requirements:
                temp_requirements.write(reqbytes)
                temp_requirements_name = temp_requirements.name

    print("\nInstalling application requirements...\n")

    # Don't call pip directly - there is no API, and its developers say not to
    cmd = make_pip_command(
        'install --user --disable-pip-version-check -r {}'.format(temp_requirements.name)
    )
    with Popen(cmd, stdout=PIPE, stderr=PIPE, bufsize=1, universal_newlines=True) as p:
        for line in p.stdout:
            print(line, end='')
        p.wait()
        i = p.returncode
    os.remove(temp_requirements_name)
    if i != 0:
        if delete_installer:
            delete_installer_and_its_temp_dir(installer)
        sys.stderr.write("Failed to install application requirements: exiting\n")
        sys.exit(1)

    print("\nInstalling application...\n")
    cmd = make_pip_command(
        'install --user --disable-pip-version-check --no-deps {}'.format(installer)
    )
    with Popen(cmd, stdout=PIPE, stderr=PIPE, bufsize=1, universal_newlines=True) as p:
        for line in p.stdout:
            print(line, end='')
        p.wait()
        i = p.returncode
    if i != 0:
        if delete_installer:
            delete_installer_and_its_temp_dir(installer)
        sys.stderr.write("Failed to install application: exiting\n")
        sys.exit(1)

    path = os.getenv('PATH')
    install_path = os.path.join(os.path.expanduser('~'), '.local', 'bin')

    if install_path not in path.split(':'):
        if distro in debian_like or distro == Distro.opensuse:
            bin_dir = os.path.join(os.path.expanduser('~'), 'bin')
            if not os.path.isdir(bin_dir):
                created_bin_dir = True
                os.mkdir(bin_dir)
            else:
                created_bin_dir = False
            for executable in ('rapid-photo-downloader', 'analyze-pv-structure'):
                symlink =  os.path.join(bin_dir, executable)
                if not os.path.exists(symlink):
                    print('Creating symlink', symlink)
                    print("If you uninstall the application, remove this symlink yourself.")
                    os.symlink(os.path.join(install_path, executable), symlink)

            if created_bin_dir:
                print(bcolors.BOLD + "\nYou may have to restart the computer to be able to run the "
                         "program from the commmand line or application launcher" + bcolors.ENDC)
        else:
            sys.stderr.write("\nThe application was installed in {}\n".format(install_path))
            sys.stderr.write("Add {} to your PATH to be able to launch it.\n".format(install_path))

    man_dir = '/usr/local/share/man/man1'

    if interactive:
        print("\nDo you want to install the application's man pages?")
        print("They will be installed into {}".format(man_dir))
        print("If you uninstall the application, remove these manpages yourself.")
        print("sudo may prompt you for the sudo password.")
        answer = input('Do want to install the man pages? [Y/n] ')
    else:
        print("\nInstalling man pages into {}".format(man_dir))
        print("If you uninstall the application, remove these manpages yourself.")
        print("sudo may prompt you for the sudo password.\n")
        answer = 'y'

    if get_yes_no(answer):
        if not os.path.isdir(man_dir):
            cmd = shutil.which('mkdir')
            command_line = 'sudo {} -p {}'.format(cmd, man_dir)
            print(command_line)
            args = shlex.split(command_line)
            try:
                subprocess.check_call(args)
            except subprocess.CalledProcessError:
                if delete_installer:
                    delete_installer_and_its_temp_dir(installer)
                sys.stderr.write("Failed to create man page directory: exiting\n")
                sys.exit(1)
        cmd = shutil.which('cp')
        for manpage in ('rapid-photo-downloader.1', 'analyze-pv-structure.1'):
            source = os.path.join(os.path.expanduser('~'), '.local/share/man/man1', manpage)
            dest = os.path.join(man_dir, manpage)
            command_line = 'sudo {} {} {}'.format(cmd, source, dest)
            print(command_line)
            args = shlex.split(command_line)
            try:
                subprocess.check_call(args)
            except subprocess.CalledProcessError:
                sys.stderr.write("Failed to copy man page.")

    if delete_installer:
        delete_installer_and_its_temp_dir(installer)


if __name__ == '__main__':

    if os.getuid() == 0:
        sys.stderr.write("Do not run this installer script as sudo / root user.\nRun it using the "
                         "user who will run the program.\n")
        sys.exit(1)

    parser = parser_options()

    args = parser.parse_args()

    distro = get_distro()
    if distro != Distro.unknown:
        distro_version = get_distro_version(distro)
    else:
        distro_version = 0.0

    if distro == Distro.debian:
        if distro_version == 0.0:
            if not is_debian_testing_or_unstable():
                print('Warning: this version of Debian may not work with Rapid Photo Downloader.')
        elif distro_version <= 8.0:
            sys.stderr.write("Sorry, Debian Jessie is too old to be able to run this version of "
                             "Rapid Photo Downloader.\n")
            sys.exit(1)

    elif distro in fedora_like and 0.0 > distro_version <= 23.0:
        sys.stderr.write("Sorry, Fedora 23 is no longer supported by Rapid Photo Downloader.\n")
        sys.exit(1)
    elif distro in arch_like:
        print('Users of Arch Linux or its derivatives should try the AUR package: '
              'https://aur.archlinux.org/packages/rapid-photo-downloader-bzr/')
        print("Exiting...")
        sys.exit(0)


    if distro == Distro.ubuntu:
        enable_universe(args.interactive)

    if distro in debian_like:
        distro_family = Distro.debian
        if not have_apt:
            if not custom_python():
                print('To continue, the package python3-apt must be installed.\n')
                command_line = make_distro_packager_commmand(
                    distro_family, 'python3-apt', args.interactive
                )
                run_cmd(command_line, restart=True, interactive=args.interactive)
            else:
                sys.stderr.write("Sorry, this installer does not support a custom python "
                                 "installation.\nExiting\n")
                sys.exit(1)

    elif distro in fedora_like:
        distro_family = Distro.fedora
        if custom_python():
            sys.stderr.write("Sorry, this installer does not support a custom python "
                             "installation.\nExiting\n")
            sys.exit(1)
    else:
        distro_family = distro

    packages = []

    if have_pip:
        local_pip = custom_python() or user_pip()
    else:
        packages.append('python3-pip')
        local_pip = False


    try:
        import setuptools
    except ImportError:
        packages.append(pip_package('setuptools', local_pip))

    try:
        import wheel
    except:
        packages.append(pip_package('wheel', local_pip))

    if packages:
        packages = ' '.join(packages)

        if distro_family not in (Distro.fedora, Distro.debian, Distro.opensuse):
            sys.stderr.write(
                "Install the following packacges using your Linux distribution's standard package "
                "manager, and then rerun this installer\n")
            sys.stderr.write(packages + '\n')
            sys.exit(1)

        print("To run this program, programs to assist Python 3 and its package management must "
              "be installed.\n")

        if not local_pip:
            command_line = make_distro_packager_commmand(distro_family, packages, args.interactive)
        else:
            command_line = make_pip_command('install --user ' + packages, split=False)

        run_cmd(command_line, restart=True, interactive=args.interactive)

    # Can now assume that both pip and wheel have been installed
    if pip_version < StrictVersion('8.1'):
        print("\nPython 3's pip and setuptools must be upgraded for your user.\n")

        command_line = make_pip_command(
            'install --user --upgrade pip setuptools wheel', split=False
        )

        run_cmd(command_line, restart=True, interactive=args.interactive)

    installer = args.tarfile

    if installer is None:
        if have_requests is False:
            print("Installing python requests")
            command_line = make_pip_command(
                'install --user requests', split=False
            )
            run_cmd(command_line, restart=True, interactive=args.interactive)
    elif not os.path.exists(installer):
        print("Installer not found:", installer)
        sys.exit(1)
    elif not installer.endswith('.tar.gz'):
        print("Installer not in tar.gz format:", installer)
        sys.exit(1)

    main(installer, distro, distro_family, distro_version, args.interactive, args.devel)
