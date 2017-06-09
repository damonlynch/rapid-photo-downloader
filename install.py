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

"""
Install script for Rapid Photo Downloader.

Do not run as root - it will refuse to run if you try.

The primary purpose of this installation script is to install packages that are required
for Rapid Photo Downloader to run. Specifically, these packages are:

1. Non-python programs, e.g. exiv2, ExifTool.
2. Python packages that are unavailable on Python's PyPi service, namely
   python3 gobject introspection modules.
3. Although PyQt 5.6 and above is available on PyPi, bundled with Qt 5.6, it's easier
   to use the Linux distro's PyQt packages, particularly in the case of Ubuntu, whose
   custom scrollbar implementation does not work with stock Qt without a special environment
   variable being set that disables the custom scrollbars.

Once these dependencies are satisfied, Python's pip is used to install Rapid Photo Downloader
itself, along with several Python packages from PyPi, found in requirements.txt.

The secondary purpose of this install script is to give the option to the user of installing man
pages in the system's standard  man page location, and for Debian/Ubuntu/openSUSE distros,
to create a link in ~/bin to the rapid-photo-downloader executable.
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2016-2017, Damon Lynch"

import tarfile
import os
import sys
import tempfile
import argparse
import shlex
import subprocess
from subprocess import Popen, PIPE
import shutil
from distutils.version import StrictVersion
from enum import Enum


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


def run_cmd(command_line: str, restart=False, exit_on_failure=True, shell=False) -> None:
    print("The following command will be run:\n")
    print(command_line)
    if command_line.startswith('sudo'):
        print("\nsudo may prompt you for the sudo password.")
    print()

    args = shlex.split(command_line)
    answer = input('Would you like to run the command now? (If you do, type yes and hit enter): ')

    if answer != 'yes':
        print('Answer is not yes, exiting.')
        sys.exit(0)

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
            if len(sys.argv) == 2:
                sys.stdout.flush()
                sys.stderr.flush()
                # restart the script
                os.execl(sys.executable, sys.executable, *sys.argv)
            else:
                print("Rerun this script, passing the path to the tarfile\n")
                sys.exit(0)


def enable_universe():
    try:
        repos = subprocess.check_output(['apt-cache', 'policy'], universal_newlines=True)
        version = subprocess.check_output(['lsb_release', '-sc'], universal_newlines=True).strip()
        if not '{}/universe'.format(version) in repos and version not in (
                'sarah', 'serena', 'sonya'):
            print("The Universe repository must be enabled. Do you want do that now?\n")
            run_cmd(command_line='sudo add-apt-repository universe', restart=False)
            run_cmd(command_line='sudo apt update', restart=True)

    except Exception:
        pass

def check_package_import_requirements(distro: Distro, version: float) -> None:
    if distro in debian_like:
        if not have_apt:
            print('To continue, the package python3-apt must be installed.\n')
            cmd = shutil.which('apt-get')
            command_line = 'sudo {} install python3-apt'.format(cmd)
            run_cmd(command_line, restart=True)

        cache = apt.Cache()
        missing_packages = []
        packages = 'libimage-exiftool-perl python3-pyqt5 python3-dev ' \
             'intltool gir1.2-gexiv2-0.10 python3-gi gir1.2-gudev-1.0 ' \
             'gir1.2-udisks-2.0 gir1.2-notify-0.7 gir1.2-glib-2.0 gir1.2-gstreamer-1.0 '\
             'libgphoto2-dev python3-arrow python3-psutil g++ libmediainfo0v5 '\
             'qt5-image-formats-plugins python3-zmq exiv2 python3-colorlog libraw-bin ' \
             'python3-easygui python3-sortedcontainers python3-wheel python3-requests'.split()

        for package in packages:
            try:
                if not cache[package].is_installed:
                    missing_packages.append(package)
            except KeyError:
                print('The following package is unknown on your system: {}\n'.format(
                    package))
                sys.exit(1)

        if missing_packages:
            cmd = shutil.which('apt-get')
            command_line = 'sudo {} install {}'.format(cmd, ' '.join(missing_packages))
            print("To continue, some packages required to run the application will be "
                  "installed.\n")
            run_cmd(command_line)

    elif distro in fedora_like:
        if not have_dnf:
            print('To continue, the package python3-dnf must be installed.\n')
            cmd = shutil.which('dnf')
            command_line = 'sudo {} install python3-dnf'.format(cmd)
            run_cmd(command_line, restart=True)

        missing_packages = []
        packages = 'python3-qt5 gobject-introspection python3-gobject ' \
                   'libgphoto2-devel zeromq-devel exiv2 perl-Image-ExifTool LibRaw-devel gcc-c++ ' \
                   'rpm-build python3-devel intltool ' \
                   'python3-easygui qt5-qtimageformats python3-psutil libmediainfo ' \
                   'python3-requests'.split()

        if 0.0 < version <= 24.0:
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
            print("To continue, some packages required to run the application will be "
                  "installed.\n")
            run_cmd(command_line)

    elif distro == Distro.opensuse:
        cmd = shutil.which('zypper')
        packages = 'python3-qt5 girepository-1_0 python3-gobject ' \
                   'zeromq-devel exiv2 exiftool python3-devel ' \
                   'libgphoto2-devel libraw-devel gcc-c++ rpm-build intltool ' \
                   'libqt5-qtimageformats python3-requests python3-psutil ' \
                   'typelib-1_0-GExiv2-0_10 typelib-1_0-UDisks-2_0 typelib-1_0-Notify-0_7 ' \
                   'typelib-1_0-Gst-1_0 typelib-1_0-GUdev-1_0'
        command_line = 'sudo {} in {}'.format(cmd, packages)
        print("To continue, some packages required to run the application will be checked or "
              "installed.\n")

        run_cmd(command_line)

        #TODO libmediainfo - not a default openSUSE package, sadly
    else:
        check_packages_on_other_systems()


def query_uninstall() -> bool:
    return input('\nType yes and hit enter if you want to to uninstall the previous version of '
                 'Rapid Photo Downloader: ') == 'yes'


def uninstall_old_version(distro: Distro) -> None:
    pkg_name = 'rapid-photo-downloader'

    if distro in debian_like:
        try:
            cache = apt.Cache()
            pkg = cache[pkg_name]
            if pkg.is_installed and query_uninstall():
                cmd = shutil.which('apt-get')
                command_line = 'sudo {} remove {}'.format(cmd, pkg_name)
                run_cmd(command_line)
        except Exception:
            pass

    elif distro in fedora_like:
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
            if len(list(i)) and query_uninstall():
                cmd = shutil.which('dnf')
                command_line = 'sudo {} remove {}'.format(cmd, pkg_name)
                run_cmd(command_line)

    elif distro == Distro.opensuse:
        print("Querying package system to see if an older version of Rapid Photo Downloader is "
              "installed (this may take a while)...")
        zypper = shutil.which('zypper')
        command_line = '{} se rapid-photo-downloader'.format(zypper)
        args = shlex.split(command_line)
        output = subprocess.check_output(args, universal_newlines=True)
        if '\ni | rapid-photo-downloader' in output and query_uninstall():
            command_line = 'sudo {} rm rapid-photo-downloader'.format(zypper)
            run_cmd(command_line)


def make_pip_command(args: str):
    return shlex.split('{} -m pip {}'.format(sys.executable, args))


def main(installer: str, distro: Distro, distro_version: float) -> None:

    uninstall_old_version(distro)

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

    print("\nInstalling application requirements...\n")

    # Don't call pip directly - there is no API, and its developers say not to
    cmd = make_pip_command('install --user -r {}'.format(temp_requirements.name))
    with Popen(cmd, stdout=PIPE, stderr=PIPE, bufsize=1, universal_newlines=True) as p:
        for line in p.stdout:
            print(line, end='')
        p.wait()
        i = p.returncode
    os.remove(temp_requirements_name)
    if i != 0:
        sys.stderr.write("Failed to install application requirements: exiting\n")
        sys.exit(1)

    print("\nInstalling application...\n")
    cmd = make_pip_command('install --user --upgrade --no-deps {}'.format(installer))
    with Popen(cmd, stdout=PIPE, stderr=PIPE, bufsize=1, universal_newlines=True) as p:
        for line in p.stdout:
            print(line, end='')
        p.wait()
        i = p.returncode
    if i != 0:
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

    if distro == Distro.debian and distro_version <= 8.0:
        sys.stderr.write("Sorry, Debian Jessie is too old to be able to run this version of Rapid "
                         "Photo Downloader.\n")
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
        enable_universe()

    if distro in debian_like:
        distro_family = Distro.debian
    elif distro in fedora_like:
        distro_family = Distro.fedora
    else:
        distro_family = distro

    packages = []
    try:
        import pip
    except ImportError:
        packages.append('python3-pip')

    try:
        import setuptools
    except ImportError:
        packages.append('python3-setuptools')

    try:
        import wheel
    except:
        packages.append('python3-wheel')

    if packages:
        packages = ' '.join(packages)

        if distro_family not in (Distro.fedora, Distro.debian, Distro.opensuse):
            sys.stderr.write(
                "Install the following packacges using your Linux distribution's standard package "
                "manager, and then rerun this installer\n")
            sys.stderr.write(packages + '\n')
            sys.exit(1)

        print("To run this program, you must first install some programs to assist "
              "Python 3 and its package management.\n")

        installer = installer_cmds[distro_family]
        command_line = 'sudo {} install '.format(installer) + packages
        run_cmd(command_line, restart=True)

    # Can now assume that both pip and wheel have been installed

    if StrictVersion(pip.__version__) < StrictVersion('8.1'):
        print("\nPython 3's pip and setuptools must be upgraded for your user.\n")

        print("Caution: upgrading pip and setuptools for your user could potentially "
             "negatively affect the installation of other, older Python packages by your user.\n")
        print("However the risk is very small and is normally nothing to worry about.\n")

        command_line = '{} -m pip install --user --upgrade pip setuptools'.format(sys.executable)

        run_cmd(command_line, restart=True)

    parser = argparse.ArgumentParser(description='Install Rapid Photo Downloader')
    parser.add_argument('tarfile', action='store', help="tar.gz Rapid Photo Downloader "
                                                        "installer archive")
    args = parser.parse_args()
    installer = args.tarfile  # type: str
    if not os.path.exists(installer):
        print("Installer not found:", installer)
        print("Include the name of the tar.gz Rapid Photo Downloader installer archive")
        sys.exit(1)
    elif not installer.endswith('.tar.gz'):
        print("Installer not in tar.gz format:", installer)
        sys.exit(1)
    main(installer, distro, distro_version)


