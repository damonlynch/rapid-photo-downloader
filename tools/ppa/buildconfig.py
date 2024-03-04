# Copyright (C) 2024 Damon Lynch <damonlynch@gmail.com>

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
Used by preparation script

Not included in program tarball distributed to end users.
"""

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2024, Damon Lynch"

from pathlib import Path

import tomli
from showinfm.system.linux import wsl_transform_path_uri

package_ext = ".tar.gz"
signature_ext = ".asc"

packaging_staging = Path().home() / "ppa-launchpad-staging"


with open("config.toml", "rb") as f:
    toml_dict = tomli.load(f)


def package_abbreviations()->list[str]:
    return [v["abbreviation"] for v in toml_dict.values()]

def full_distro_package_name(abbreviation:str)->str:
    for key, value in toml_dict.items():
        if value["abbreviation"] == abbreviation:
            return key

def local_package_name(distro_package:str)->str:
    return toml_dict[distro_package]["local_package_name"]

def convert_path(path:str) -> Path:
    """
    Converts a path into an absolute path, where the input path is a Windows
    path or a path relative to the home directory.

    Assumes running under Linux or WSL.
    """
    p = wsl_transform_path_uri(path, generate_win_path=False)
    return Path(p.linux_path if p.is_win_location else Path().home() / path).absolute()


def code_build_folder(package: str) -> Path:
    return convert_path(toml_dict[package]["code_dist_folder"])


def debian_folder_git(package: str) -> Path:
    return Path.home() / toml_dict[package]["debian_folder_git"]


def determine_current_version_in_code(package: str) -> str:
    version_path = convert_path(toml_dict[package]["version_path"])
    if version_path.name == "pyproject.toml":
        with open(version_path, "rb") as f:
            toml_pyproject=tomli.load(f)
            return toml_pyproject["project"]["version"]
    else:
        # Assume Rapid Photo Downloader
        with open(version_path) as f:
            about = {}
            exec(f.read(), about)
            return about["__version__"]
