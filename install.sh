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


try:
    import pip
except ImportError:
    sys.stderr.write("To run this program, you must first install pip for Python 3\n")
    sys.stderr.write("Install it using your Linux distribution's standard package manager -\n\n")
    fedora_pip = 'Fedora:\nsudo dnf install python3 python3-wheel\n'
    suse_pip = 'openSUSE:\nsudo zypper install python3-pip python3-setuptools python3-wheel\n'
    debian_pip = 'Ubuntu/Debian:\nsudo apt-get install python3-pip\n'
    arch_pip = 'Arch Linux:\nsudo pacman -S python-pip\n'
    for distro in (fedora_pip, suse_pip, debian_pip, arch_pip):
        sys.stderr.write('{}\n'.format(distro))
    sys.exit(1)

try:
    import apt
    have_apt = True
except ImportError:
    have_apt = False


def check_non_debian_packages() -> None:
    """
    Check to see if some (but not all) application dependencies are
    installed on non-Debian-like systems.
    """

    import_msgs = []

    try:
        import PyQt5
    except ImportError:
        import_msgs.append('python3 PyQt5')
    try:
        import gi
        have_gi = True
    except ImportError:
        import_msgs.append('python3 gobject introspection')
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

def distro_is_debian_like() -> bool:
    is_debian = None
    if os.path.isfile('/etc/os-release'):
        with open('/etc/os-release', 'r') as f:
            for line in f:
                if line.startswith('ID_LIKE='):
                    is_debian = line.find('debian' , 7) >= 0
                    break
    return is_debian

def check_package_import_requirements() -> None:
    if distro_is_debian_like():
        if not have_apt:
            sys.stderr.write('To continue, the package python3-apt must be installed.')
            sys.exit(1)
        cache = apt.Cache()
        missing_packages = []
        packages = 'libimage-exiftool-perl python3-pyqt5 python3-setuptools python3-dev ' \
             'python3-distutils-extra gir1.2-gexiv2-0.10 python3-gi gir1.2-gudev-1.0 ' \
             'gir1.2-udisks-2.0 gir1.2-notify-0.7 gir1.2-glib-2.0 gir1.2-gstreamer-1.0 '\
             'libgphoto2-dev python3-sortedcontainers python3-arrow python3-psutil '\
             'qt5-image-formats-plugins python3-zmq exiv2 python3-colorlog libraw-bin ' \
             'python3-easygui'.split()

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
    else:
        check_non_debian_packages()

def main(installer: str) -> None:

    check_package_import_requirements()

    name = os.path.basename(installer)
    name = name[:len('.tar.gz') * -1]

    rpath = os.path.join(name, 'requirements.txt')
    with tarfile.open(installer) as tar:
        with tar.extractfile(rpath) as requirements:
            bytes = requirements.read()
            with tempfile.NamedTemporaryFile(delete=False) as temp_requirements:
                temp_requirements.write(bytes)
                temp_requirements_name = temp_requirements.name

    print("\nInstalling application requirements")
    pip.main(['install', '--user', '-r' ,temp_requirements.name])
    os.remove(temp_requirements_name)

    print("\nInstalling application")
    pip.main(['install', '--user', '--no-deps', installer])

    path = os.getenv('PATH')
    install_path = os.path.join(os.path.expanduser('~'), '.local', 'bin')

    if install_path not in path.split(':'):
        if distro_is_debian_like():
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
                    os.symlink(os.path.join(install_path, executable), symlink)

            if created_bin_dir:
                print("\nLogout and login again to be able to run the program from the commmand "
                      "line or application launcher")
        else:
            sys.stderr.write("\nThe application was installed in {}\n".format(install_path))
            sys.stderr.write("Add {} to your PATH to be able to launch it.\n".format(install_path))

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

    if StrictVersion(pip.__version__) < StrictVersion('8.1'):
        sys.stderr.write("Python 3's pip and setuptools must be upgraded for your user\n\n")

        sys.stderr.write('Run both of these commands as your regular user (i.e. without '
                         'sudo)\n\n')
           
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
    main(installer)


