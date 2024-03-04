#!/usr/bin/env python3

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
Prepare directory for running dch, debuild and dput for Rapid Photo Downloader PPA.

Directory locations are configured in buildconfig.py

Workflow:
1. Run this script. It will create a Debian directory in debian_folder_git with contents
from the latest rapid-photo-downloader package from Ubuntu
2. Check if anything needs to be merged from the Debian directory in debian_folder_git
3. Copy that Debian directory into the version being worked on in packaging_staging
4. Run dch (from within the version being worked on)
5. Run debuild -S -d (from within the version being worked on)
6. cd to packaging_staging
7. Run dput ppa:dlynch3/ppa rapid-photo-downloader_x.x.xx-0ubuntu1ppa1_source.changes

Not included in program tarball distributed to end users.
"""

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2024, Damon Lynch"

import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from argumentsparse import get_parser
from buildconfig import (
    code_build_folder,
    debian_folder_git,
    determine_current_version_in_code,
    full_distro_package_name,
    local_package_name,
    package_ext,
    packaging_staging,
    signature_ext,
)
from console import console
from git import Head, Repo
from rich.prompt import Confirm


def reset_packaging_staging() -> None:
    if Path(packaging_staging).is_dir() and Confirm.ask(
        f"Remove folder {packaging_staging}?", default=True
    ):
        shutil.rmtree(packaging_staging)
    packaging_staging.mkdir(parents=True, exist_ok=True)


def extract_version(package_name: str) -> str:
    """
    Extract the version number from a package string

    >>> extract_version("show-in-file-manager-1.1.5")
    '1.1.5'
    >>> extract_version("rapid-photo-downloader-0.9.35")
    '0.9.35'
    """
    r = re.search(r"(?P<version>\d{1,3}\.\d{1,3}(\.\d{1,3})?$)", package_name)
    try:
        return r.group("version")
    except AttributeError:
        console.print(f"Package {package_name} does not have a version number")
        raise f"Package {package_name} does not have a version number"


def get_dist_tarball_and_signature(
    distro_package: str, local_package: str
) -> tuple[Path, Path]:
    dist_folder = code_build_folder(package=distro_package)
    tarballs = list(dist_folder.glob(f"{local_package}*.tar.gz"))
    try:
        assert len(tarballs) == 1
    except AssertionError:
        console.print(
            "Unexpected number of tarballs in the dist directory", style="fail"
        )
        sys.exit(1)

    tarball = tarballs[0]
    signature = Path(f"{tarball}{signature_ext}")

    try:
        assert signature.is_file()
    except AssertionError:
        console.print(f"Signature missing: {signature}", style="fail")
        sys.exit(1)

    return tarball, signature


def validate_versions(expected_version: str, tarball: Path) -> str:
    full_base_name = Path(str(tarball)[: -len(package_ext)])
    name = full_base_name.name

    # Check if the version in code matches the built version
    if not str(full_base_name).endswith(expected_version):
        console.print(f"Unexpected version {expected_version}", style="warning")
        if not Confirm.ask("Continue?", default=False):
            sys.exit(0)
        version = extract_version(name)
    else:
        version = expected_version
    return version


def copy_sources(
    local_package: str, version: str, tarball: Path, signature: Path
) -> Path:
    ppa_package_tarball = f"{local_package}_{version}.orig.tar.gz"
    ppa_package_signature = f"{ppa_package_tarball}{signature_ext}"
    ppa_package_tarball = packaging_staging / ppa_package_tarball
    ppa_package_signature = packaging_staging / ppa_package_signature

    # Copy the dist tarball and rename it, as well as the signature
    do_source_copy = True
    if ppa_package_tarball.exists() or ppa_package_signature.exists():
        console.print("PPA tarball and/or signature already exists", style="warning")
        do_source_copy = Confirm.ask(
            "Overwrite existing tarball and signature?", default=True
        )

    if do_source_copy:
        console.print("Copying source tarball and signature...")
        shutil.copy(tarball, ppa_package_tarball)
        shutil.copy(signature, ppa_package_signature)
    return ppa_package_tarball


def extract_dist_tarball(
    local_package: str, version: str, ppa_package_tarball: Path
) -> None:
    ppa_folder = packaging_staging / f"{local_package}-{version}"
    do_tarball_extract = True
    if ppa_folder.is_dir():
        console.print(f"Folder already exists for release {version}", style="warning")
        do_tarball_extract = Confirm.ask(
            "Do you want to overwrite everything in the release folder and its "
            "subfolders?",
            default=True,
        )
        if do_tarball_extract:
            console.print("Removing old release folder...")
            shutil.rmtree(ppa_folder)

    if do_tarball_extract:
        console.print("Extracting source tarball...")
        with tarfile.open(ppa_package_tarball, "r:gz") as tar:
            tar.extractall(packaging_staging)


def pull_official_ubuntu_tarball(
    distro_package: str, local_package: str, version: str
) -> str:
    pull_version = ""

    # Pull the latest package from Ubuntu into a temporary directory
    # Determine the version, and see if it can be copied into the packaging_folder
    do_launchpad_pull = Confirm.ask(
        f"Pull package from launchpad into {packaging_staging}?", default=True
    )
    if do_launchpad_pull:
        cmd = f"pull-lp-source {distro_package}"
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            try:
                subprocess.run(shlex.split(cmd), capture_output=False)
            except subprocess.CalledProcessError as inst:
                console.print(f"Encountered error while running {cmd}", style="fail")
                console.print(inst)
                sys.exit(1)
            dirs = list(Path(tmpdir).glob(f"{local_package}-*{os.sep}"))
            try:
                assert len(dirs) == 1
            except AssertionError:
                console.print(
                    f"Unexpected number of directories created by {cmd}", style="fail"
                )
            else:
                pull_version = extract_version(dirs[0].name)
                if pull_version == version:
                    console.print("Same version already exists", style="warning")

                for source in Path(tmpdir).glob("*"):
                    s = source.relative_to(tmpdir)
                    destination = packaging_staging / s
                    if destination.exists():
                        console.print(f"Skipping {s}", style="warning")
                    else:
                        shutil.move(source, destination)
    return pull_version


class DebianRepo:
    def __init__(self, path: Path, local_package: Path) -> None:
        self.path = path
        self.local_package = local_package
        if not path.is_dir():
            self.initialise_repo()
        else:
            self.repo = Repo(str(path))

    def initialise_repo(self) -> None:
        console.print(f"Initialising repo {self.path}", style="info")
        self.path.mkdir()

        self.repo = Repo.init(str(self.path))
        console.print(
            f"Copy Debian directory to repo {self.path} and commit it", style="info"
        )
        sys.exit(0)

    def is_clean(self) -> bool:
        if self.repo.untracked_files:
            console.print(
                "The repo contains untracked "
                f"files: {', '.join(self.repo.untracked_files)}",
                style="warning",
            )
            return False
        if self.repo.is_dirty():
            console.print(
                f"The repo branch {self.repo.active_branch.name} is dirty",
                style="warning",
            )
            return False
        return True

    def get_head(self, name: str) -> Head:
        for head in self.repo.heads:
            if head.name == name:
                return head
        raise (Exception(f"{name} not found"))

    def checkout_head(self, name: str):
        head = self.get_head(name)
        head.checkout()

    def create_version_branch_with_debian_folder_contents(
        self, pull_version: str
    ) -> None:
        try:
            head = self.get_head(pull_version)
            console.print(f"Branch {pull_version} already exists", style="info")
        except Exception:
            console.print(f"Creating branch {pull_version}")
            head = self.repo.create_head(pull_version)

        console.print(f"Checking out branch {pull_version}")
        try:
            head.checkout()
        except Exception as inst:
            console.print(f"Could not switch branch: {inst}", style="fail")
        else:
            console.print(f"Copying Debian folder to branch {pull_version}")
            shutil.rmtree(self.path / "debian")
            shutil.copytree(
                packaging_staging / f"{self.local_package}-{pull_version}" / "debian",
                self.path / "debian",
            )
            if self.repo.untracked_files or self.repo.is_dirty():
                self.repo.git.add(A=True)
                console.print(f"Committing branch {pull_version}")
                self.repo.git.commit(m=f"Ubuntu upstream package for {pull_version}")
                console.print("Switching to main branch")
                self.checkout_head("main")
            else:
                console.print(f"No changes on branch {pull_version}")


def main() -> None:
    parser = get_parser()
    args = parser.parse_args()
    distro_package = full_distro_package_name(abbreviation=args.package)
    local_package = local_package_name(distro_package=distro_package)
    console.print(f"Packaging {distro_package} using {local_package}", style="info")
    debian_folder = debian_folder_git(package=distro_package)
    repo = DebianRepo(debian_folder, Path(local_package))
    if not repo.is_clean():
        sys.exit(1)
    expected_version = determine_current_version_in_code(distro_package)
    tarball, signature = get_dist_tarball_and_signature(distro_package, local_package)
    version = validate_versions(expected_version, tarball)
    console.print(f"Working with version {version} using {debian_folder}", style="info")
    reset_packaging_staging()
    ppa_package_tarball = copy_sources(local_package, version, tarball, signature)
    extract_dist_tarball(distro_package, version, ppa_package_tarball)
    pull_version = pull_official_ubuntu_tarball(distro_package, local_package, version)
    if pull_version:
        repo.create_version_branch_with_debian_folder_contents(pull_version)


if __name__ == "__main__":
    main()
