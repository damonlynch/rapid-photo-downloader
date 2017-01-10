#!/usr/bin/env python3

# Copyright (C) 2016 Damon Lynch <damonlynch@gmail.com>

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

"""
Install script for Rapid Photo Downloader.

Do not run as root - it will refuse to run if you try.

The primary purpose of this installation script is to install packages that are required
for Rapid Photo Downloader to run. Specifically, these packages are:

1. Non-python programs, e.g. exiv2, ExifTool.
2. Python packages that are unavailable on Python's PyPi service, namely
   python3 gobject introspection modules.
3. Although PyQt 5.6 is available on PyPi, bundled with Qt 5.6, it's easier
   to use the Linux distro's PyQt packages, particularly in the case of Ubuntu, whose
   custom scrollbar implementation does not work with stock Qt without a special environment
   variable being set that disables the custom scrollbars.

Once these dependencies are satisifed, Python's pip is used to install Rapid Photo Downloader
itself, along with several Python packages from PyPi, found in requirements.txt.

The secondary purpose of this install script is to give the option to the user of installing man
pages in the system's standard  man page location, and for Debian/Ubuntu distros, to create a
link in ~/bin to the rapid-photo-downloader executable.
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2016, Damon Lynch"

import tarfile
import os
import sys
import tempfile
import argparse
import shlex
import subprocess
import shutil
from distutils.version import StrictVersion
from enum import Enum


try:
    import pip
except ImportError:
    sys.stderr.write("To run this program, you must first install pip for Python 3\n")
    sys.stderr.write("Install it using your Linux distribution's standard package manager -\n\n")
    fedora_pip = 'Fedora:\nsudo dnf install python3 python3-wheel\n'
    suse_pip = 'openSUSE:\nsudo zypper install python3-pip python3-setuptools python3-wheel\n'
    debian_pip = 'Ubuntu/Debian/Mint:\nsudo apt-get install python3-pip python3-wheel\n'
    arch_pip = 'Arch Linux:\nsudo pacman -S python-pip\n'
    for distro in (fedora_pip, suse_pip, debian_pip, arch_pip):
        sys.stderr.write('{}\n'.format(distro))
    sys.exit(1)

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
    unknown = 4


def check_packages_on_other_systems() -> None:
    """
    Check to see if some (but not all) application dependencies are
    installed on systems that we are not explicitly analyzing.
    """

    import_msgs = []

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

def get_distro_id(id_or_id_like: str) -> Distro:
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

def get_distro_version(distro: Distro) -> float:
    if distro == Distro.fedora:
        version_string = 'REDHAT_BUGZILLA_PRODUCT_VERSION='
    elif distro in (Distro.debian, Distro.ubuntu):
        version_string = 'VERSION_ID="'
    else:
        return 0.0

    with open('/etc/os-release', 'r') as f:
        for line in f:
            if line.startswith(version_string):
                try:
                    if distro == Distro.fedora:
                        v = line[len(version_string):]
                    else:
                        v = line[len(version_string):-2]
                    return float(v)
                except ValueError:
                    sys.stderr.write("Unexpected format while parsing {} version".format(
                        distro.name.capitalize()))
                    return 0.0

def install_packages(command_line: str) -> None:
    print("To continue, some packages required to run the application will be "
          "installed.\n")
    print("The following command will be run:\n")
    print(command_line)
    print("\nsudo may prompt you for the sudo password.\n")
    answer = input('Do you agree to run this command? (if you do, type yes and hit '
                   'enter): ')
    if answer == 'yes':
        args = shlex.split(command_line)
        try:
            subprocess.check_call(args)
        except subprocess.CalledProcessError:
            sys.stderr.write("Command failed: exiting\n")
            sys.exit(1)
    else:
        print("Answer is not yes, exiting")
        sys.exit(0)

def uninstall_packages(command_line: str) -> None:
    print("\nThe following command will be run:\n")
    print(command_line)
    print("\nsudo may prompt you for the sudo password.\n")
    answer = input('Do you agree to run this command? (if you do, type yes and hit enter): ')
    if answer == 'yes':
        args = shlex.split(command_line)
        try:
            subprocess.check_call(args)
        except subprocess.CalledProcessError:
            sys.stderr.write("Command failed\n")

def check_package_import_requirements(distro: Distro, version: float) -> None:
    if distro in (Distro.debian, Distro.ubuntu):
        if not have_apt:
            sys.stderr.write('To continue, the package python3-apt must be installed.')
            sys.exit(1)
        cache = apt.Cache()
        missing_packages = []
        packages = 'libimage-exiftool-perl python3-pyqt5 python3-setuptools python3-dev ' \
             'python3-distutils-extra gir1.2-gexiv2-0.10 python3-gi gir1.2-gudev-1.0 ' \
             'gir1.2-udisks-2.0 gir1.2-notify-0.7 gir1.2-glib-2.0 gir1.2-gstreamer-1.0 '\
             'libgphoto2-dev python3-arrow python3-psutil g++ libmediainfo0v5 '\
             'qt5-image-formats-plugins python3-zmq exiv2 python3-colorlog libraw-bin ' \
             'python3-easygui python3-sortedcontainers python3-wheel python3-requests'.split()

        for package in packages:
            try:
                if not cache[package].is_installed:
                    missing_packages.append(package)
            except KeyError:
                sys.stderr.write('The following package is unknown on your system: {}\n'.format(
                    package))
                sys.exit(1)

        if missing_packages:
            cmd = shutil.which('apt-get')
            command_line = 'sudo {} install {}'.format(cmd, ' '.join(missing_packages))
            install_packages(command_line)

    elif distro in (Distro.fedora,):
        if not have_dnf:
            sys.stderr.write('To continue, the package python3-dnf must be installed.')
            sys.exit(1)

        missing_packages = []
        packages = 'python3-qt5 gobject-introspection python3-gobject ' \
                   'libgphoto2-devel zeromq-devel exiv2 perl-Image-ExifTool LibRaw-devel gcc-c++ ' \
                   'rpm-build python3-devel python3-distutils-extra intltool ' \
                   'python3-easygui qt5-qtimageformats python3-psutil libmediainfo' \
                   'python3-requests'.split()

        if version <= 24.0 and version > 0.0:
            packages.append('libgexiv2-python3')
        else:
            packages.append('python3-gexiv2')

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

            for package in packages:
                if package not in installed:
                    if package in available:
                        missing_packages.append(package)
                    else:
                        sys.stderr.write(
                            'The following package is unavailable on your system: {}\n'.format(
                            package))
                        sys.exit(1)

        if missing_packages:
            cmd = shutil.which('dnf')
            command_line = 'sudo {} install {}'.format(cmd, ' '.join(missing_packages))
            install_packages(command_line)
    else:
        check_packages_on_other_systems()

def query_uninstall() -> bool:
    return input('Type yes and hit enter if you want to to uninstall the previous version of '
                 'Rapid Photo Downloader: ') == 'yes'

def uninstall_old_version(distro: Distro) -> None:
    pkg_name = 'rapid-photo-downloader'

    if distro in (Distro.debian, Distro.ubuntu):
        cache = apt.Cache()
        pkg = cache[pkg_name]
        if pkg.is_installed and query_uninstall():
            cmd = shutil.which('apt-get')
            command_line = 'sudo {} remove {}'.format(cmd, pkg_name)
            uninstall_packages(command_line)

    elif distro == Distro.fedora:
        with dnf.Base() as base:
            base.read_all_repos()
            base.fill_sack()
            q = base.sack.query()
            q_inst = q.installed()
            i = q_inst.filter(name=pkg_name)
            if len(list(i)) and query_uninstall():
                cmd = shutil.which('dnf')
                command_line = 'sudo {} remove {}'.format(cmd, pkg_name)
                uninstall_packages(command_line)


def main(installer: str, distro: Distro, distro_version: float) -> None:

    check_package_import_requirements(distro, distro_version)

    name = os.path.basename(installer)
    name = name[:len('.tar.gz') * -1]

    rpath = os.path.join(name, 'requirements.txt')
    with tarfile.open(installer) as tar:
        with tar.extractfile(rpath) as requirements:
            reqbytes = requirements.read()
            with tempfile.NamedTemporaryFile(delete=False) as temp_requirements:
                temp_requirements.write(reqbytes)
                temp_requirements_name = temp_requirements.name

    print("\nInstalling application requirements")
    i = pip.main(['install', '--user', '-r',temp_requirements.name])
    os.remove(temp_requirements_name)
    if i != 0:
        sys.stderr.write("Failed to install application requirements: exiting\n")
        sys.exit(1)

    print("\nInstalling application")
    i = pip.main(['install', '--user', '--no-deps', installer])
    if i != 0:
        sys.stderr.write("Failed to install application: exiting\n")
        sys.exit(1)

    path = os.getenv('PATH')
    install_path = os.path.join(os.path.expanduser('~'), '.local', 'bin')

    if install_path not in path.split(':'):
        if distro == Distro.debian or distro == Distro.ubuntu:
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
                print(bcolors.BOLD + "\nLogout and login again to be able to run the program "\
                                 "from the commmand line or application launcher" + bcolors.ENDC)
        else:
            sys.stderr.write("\nThe application was installed in {}\n".format(install_path))
            sys.stderr.write("Add {} to your PATH to be able to launch it.\n".format(install_path))

    uninstall_old_version(distro)

    man_dir = '/usr/local/share/man/man1'
    print("\nDo you want to install the application's man pages?")
    print("They will be installed into {}".format(man_dir))
    print("If you uninstall the application, remove these manpages yourself.")
    print("sudo may prompt you for the sudo password.")
    answer = input('Type yes and hit enter if you do want to install the man pages: ')
    if answer == 'yes':
        if not os.path.isdir(man_dir):
            cmd = shutil.which('mkdir')
            command_line = 'sudo {} -p {}'.format(cmd, man_dir)
            print(command_line)
            args = shlex.split(command_line)
            try:
                subprocess.check_call(args)
            except subprocess.CalledProcessError:
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
                sys.stderr.write("Failed to copy man page: exiting\n")
                sys.exit(1)


if __name__ == '__main__':

    if os.getuid() == 0:
        sys.stderr.write("Do not run this installer script as sudo / root user.\nRun it using the "
                         "user who will run the program.\n")
        sys.exit(1)

    distro = get_distro()
    if distro != Distro.unknown:
        distro_version = get_distro_version(distro)
    else:
        distro_version = 0.0

    if distro == Distro.debian and distro_version == 8.0:
        sys.stderr.write("Sorry, Debian Jessie is too old to be able to run this version of Rapid "
                         "Photo Downloader.\n")
        sys.exit(1)
    elif distro == Distro.fedora and distro_version <= 23.0:
        sys.stderr.write("Sorry, Fedora 23 is no longer supported by Rapid Photo Downloader.\n")
        sys.exit(1)

    if StrictVersion(pip.__version__) < StrictVersion('8.1'):
        sys.stderr.write("Python 3's pip and setuptools must be upgraded for your user.\n\n")

        if get_distro() == Distro.fedora:
            sys.stderr.write("\nNOTE: ensure the package python3-wheel is installed before you "
                             "upgrade pip and setuptools. Install it by running this command:\n"
                             "sudo dnf install python3-wheel\n\n")

        sys.stderr.write('To upgrade pip and setuptools, run both of these commands as your '
                         'regular user (i.e. without sudo):\n\n')
           
        for cmd in ('python3 -m pip install --user --upgrade pip',
                    'python3 -m pip install --user --upgrade setuptools'):
            sys.stderr.write('{}\n'.format(cmd))
        sys.stderr.write('\nThen run this installer again.\n\n')

        sys.stderr.write("Caution: upgrading pip and setuptools for your user could potentially "
                         "negatively affect the installation of other, older Python packages by your user.\n")
        sys.stderr.write("However the risk is small and is normally nothing to worry about.\n")


        sys.exit(1)

    parser = argparse.ArgumentParser(description='Install Rapid Photo Downloader')
    parser.add_argument('tarfile', action='store', help="tar.gz Rapid Photo Downloader "
                                                        "installer archive")
    args = parser.parse_args()
    installer = args.tarfile  # type: str
    if not os.path.exists(installer):
        print("Installer not found:", installer)
        sys.exit(1)
    elif not installer.endswith('.tar.gz'):
        print("Installer not in tar.gz format:", installer)
        sys.exit(1)
    main(installer, distro, distro_version)


