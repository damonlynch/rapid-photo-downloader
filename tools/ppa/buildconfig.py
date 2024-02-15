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

packaging_staging = Path().home() / "ppa-launchpad-staging"
code_build_folder = Path().home() / "build_rapid" / "dist"
ubuntu_package_name = "rapid-photo-downloader"
package_ext = ".tar.gz"
signature_ext = ".asc"
debian_folder_git = Path().home() / "ppa-debian-git"
