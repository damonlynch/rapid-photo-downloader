#!/usr/bin/env python3

# Copyright (C) 2016-2024 Damon Lynch <damonlynch@gmail.com>

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

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2016-2024, Damon Lynch"

import argparse
import importlib.metadata
import importlib.util
import os
import re
import shlex
import site
import subprocess
import sys
from typing import Union

__version__ = "0.0.1"
__title__ = "pip-uninstall.py"
__description__ = (
    "Uninstall any version of Rapid Photo Downloader installed using the old "
    "install.py script."
)

if sys.version_info < (3, 10):  # noqa: UP036
    print("Sorry, Python 3.10 or greater is required.")
    sys.exit(1)


def python_package_can_import(package: str) -> bool:
    """
    Determine if a package can be imported, without importing it
    :param package: package name
    :return: True if can import, else False
    """

    return importlib.util.find_spec(package) is not None


def make_pip_command(
    args: str,
    split: bool = True,
) -> Union[list[str], str]:  # noqa: UP007
    """
    Construct a call to python's pip
    :param args: arguments to pass to the command
    :param split: whether to split the result into a list or not using shlex
    :return: command line in string or list format
    """

    cmd_line = f"{sys.executable} -m pip {args}"
    if split:
        return shlex.split(cmd_line)
    else:
        return cmd_line


def installed_using_pip(package: str, suppress_errors: bool = True) -> bool:
    """
    Determine if a python package was installed in the local directory using pip.

    Determination is not 100% robust in all circumstances.

    :param package: package name to search for
    :param suppress_errors: if True, silently catch all exceptions and return False
    :return: True if installed via pip, else False
    """

    try:
        d = importlib.metadata.distribution(package)
        return d.read_text("INSTALLER").strip().lower() == "pip"
    except Exception:
        if not suppress_errors:
            raise
        return False


def package_in_pip_output(package: str, output: str) -> bool:
    """
    Determine if a package is found in the output of packages installed by pip
    :param package:
    :param output:
    :return: True if found, False otherwise
    """
    return re.search(f"^{package}\s", output, re.IGNORECASE | re.MULTILINE) is not None


def dir_accessible(path: str) -> bool:
    return os.path.isdir(path) and os.access(path, os.W_OK)


def uninstall_pip_package(package: str, no_deps_only: bool) -> bool:
    """
    Uninstall a package from the local user using pip.

    Uninstall all local instances, including those installed multiple times,
    as can happen with the Debian patch to pip

    :param package: package to remove
    :param no_deps_only: if True, remove a package only if no other package
     depends on it
    :return: True if the package was uninstalled, False otherwise
    """

    uninstalled = False

    l_command_line = "list"

    l_command_line = f"{l_command_line} --format=columns"
    if no_deps_only:
        l_command_line = f"{l_command_line} --not-required"

    l_args = make_pip_command(l_command_line)

    u_command_line = f"uninstall -y {package}"
    u_args = make_pip_command(u_command_line)
    while True:
        try:
            output = subprocess.check_output(l_args, text=True)
            if package_in_pip_output(package, output) and installed_using_pip(package):
                try:
                    subprocess.check_call(u_args)
                    uninstalled = True
                except subprocess.CalledProcessError as e:
                    print(f"Encountered an error uninstalling {package}:")
                    print(str(e))
                    break
            else:
                break
        except Exception:
            break

    if package == "rapid-photo-downloader":
        home_bin = os.path.join(os.path.expanduser("~"), "bin")
        install_path = os.path.join(site.getuserbase(), "bin")

        if dir_accessible(home_bin):
            for executable in ("rapid-photo-downloader", "analyze-pv-structure"):
                symlink = os.path.join(home_bin, executable)
                if os.path.islink(symlink) and os.readlink(symlink) == os.path.join(
                    install_path, executable
                ):
                    print(f"Removing symlink {symlink}")
                    os.remove(symlink)
    return uninstalled


def uninstall_with_deps() -> bool:
    uninstall_pip_package("rapid-photo-downloader", no_deps_only=False)

    packages = (
        "psutil gphoto2 pyzmq pyxdg arrow python-dateutil rawkit PyPrind colorlog "
        "easygui colour pymediainfo sortedcontainers requests tornado pyheif "
        "show-in-file-manager PyQt5 PyQt5_sip"
    )

    something_done = False
    for package in packages.split():
        if uninstall_pip_package(package, no_deps_only=True):
            something_done = True
    return something_done


def parser_options(formatter_class=argparse.HelpFormatter) -> argparse.ArgumentParser:
    """
    Construct the command line arguments for the script

    :return: the parser
    """

    parser = argparse.ArgumentParser(
        prog=__title__, formatter_class=formatter_class, description=__description__
    )

    msg = (
        "Uninstall Rapid Photo Downloader that was installed with pip, keeping its "
        "dependencies."
    )

    msg2 = (
        "Uninstall the dependencies installed by pip during Rapid Photo Downloader's "
        "installation, and Rapid Photo Downloader itself, then exit."
    )

    pip_only = (
        "Note: this will not uninstall any version of Rapid Photo Downloader installed "
        "by your Linux distribution's package manager."
    )

    msg = f"{msg} {pip_only}"

    note = (
        "Dependencies will only be removed if they are not required by other "
        "programs."
    )
    note = f"{note} {pip_only}"

    msg2 = f"{msg2} {note}"

    parser.add_argument("--uninstall", action="store_true", help=msg)

    parser.add_argument(
        "--uninstall-including-pip-dependencies",
        action="store_true",
        dest="uninstall_with_deps",
        help=msg2,
    )

    return parser


def pip_needed_to_uninstall():
    sys.stderr.write(
        "The python3 tool pip is required to uninstall a version of Rapid Photo "
        "Downloader that was installed with pip.\n\n"
        "Please install it using your Linux system's standard installation method.\n\n"
        "A common package name is python3-pip.\n\n"
        "Cannot continue. Exiting.\n"
    )
    sys.exit(1)


def main():
    print(
        "\nThis program uninstalls a copy of Rapid Photo Downloader that was \n"
        "installed using the old install.py script.\n\n"
        "If you installed Rapid Photo Downloader using the old install.py script,\n"
        "you need to uninstall that copy before reinstalling it using your Linux\n"
        "system's standard package management tools.\n"
    )

    if not python_package_can_import("pip"):
        pip_needed_to_uninstall()

    if os.getuid() == 0:
        sys.stderr.write(
            "Do not run this installer script as sudo / root user.\nRun it using the "
            "user who will run the program.\n"
        )
        sys.exit(1)

    parser = parser_options()

    args = parser.parse_args()
    with_deps = False
    rpd_only = False

    if args.uninstall_with_deps:
        with_deps = True

    elif args.uninstall:
        rpd_only = True
    else:
        if input("Do you want to continue? [Y/n] ").lower() in ("y", ""):
            print("\nYou have the option of uninstalling only Rapid Photo Downloader, ")
            print("or Rapid Photo Downloader and all its dependencies that were ")
            print("installed for your user (not system-wide).\n")
            print("Which do you prefer:")
            print("1. Uninstall only Rapid Photo Downloader")
            print("2. Uninstall Rapid Photo Downloader and its dependencies")
            resp = input("Enter choice [1/2] (default: 2): ")
            if resp == "1":
                rpd_only = True
            elif resp in ("2", ""):
                with_deps = True
            else:
                print("Invalid choice. Please try again with either 1 or 2.")

    if with_deps:
        if not uninstall_with_deps():
            print("\nNothing needed to be uninstalled.")
    elif rpd_only and not uninstall_pip_package(
        "rapid-photo-downloader", no_deps_only=False
    ):
        print("\nThe program was not installed.")


if __name__ == "__main__":
    main()
