# Copyright (C) Christian Buhtz <email@unknown.com>
# Copyright (C) 2024  Damon Lynch <damonlynch@gmail.com>

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

# Derived from Christian Buhtz's tech demo:
# https://codeberg.org/buhtz/tech-demo-python-packaging/src/branch/main/03b_i18n_hatch/hatch_build.py

import shutil
import subprocess
from pathlib import Path

import tomli
from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class GettextBuildHook(BuildHookInterface):
    """
    Compile the GNU gettext translation files from their po-format into
    their binary representating mo-format using 'msgfmt'.
    """

    # Command used to compile po into mo files.
    COMPILE_COMMAND = "msgfmt"

    GETTEXT_ARTIFACT = "/*/LC_MESSAGES/*.mo"

    GETTEXT_SWITCHES = {
        ".xml": "-x",
        ".desktop": "-d",
    }

    def _check_compile_command(self) -> None:
        """Check if "msgfmt" is available."""

        if not shutil.which(self.COMPILE_COMMAND):
            raise OSError(
                f'Executable "{self.COMPILE_COMMAND}" (from GNU gettext tools) is not '
                "available. Please install it via a package manager of "
                f'your trust. In most cases "{self.COMPILE_COMMAND}" is part of '
                f'"gettext".'
            )

    def _compile_po_to_mo(self, po_file: Path, mo_file: Path) -> None:
        """
        Compile po-file to mo-file using "msgfmt".

        As an alternative, the "polib" package is also able to do this in
        pure Python.
        """

        cmd = [self.COMPILE_COMMAND, f"--output-file={mo_file}", po_file]
        rc = subprocess.run(cmd, check=False, text=True, capture_output=True)

        # Validate output
        if rc.stderr:
            raise RuntimeError(rc.stderr)

    def _translate_file(
        self, po_dir: Path, in_file: Path, translated_file: Path
    ) -> None:
        """
        Translate a .desktop or .xml file using intltool-merge
        :param po_dir: directory containing the po files
        :param in_file: the full path to the .desktop.in or .xml.in file
        :param translated_file: the full path to the output .desktop or .xml file
        """

        file_extension = in_file.suffixes[-2]
        switch = self.GETTEXT_SWITCHES[file_extension]
        cmd = ["intltool-merge", switch, po_dir, in_file, translated_file]
        rc = subprocess.run(cmd, check=False, text=True, capture_output=True)

        # Validate output
        if rc.stderr:
            raise RuntimeError(rc.stderr)

    def initialize(self, version, build_data):
        if self.target_name not in ["wheel", "sdist"]:
            return

        self._check_compile_command()

        with open("pyproject.toml", "rb") as f:
            config_dict = tomli.load(f)

        # Location of the package
        pkg_path = Path.cwd()

        po_dir = pkg_path / config_dict["tool"]["gettextbuild"]["po_directory"]
        mo_dest = None

        artifacts = config_dict["tool"]["hatch"]["build"]["artifacts"]
        for artifact in artifacts:
            if artifact.endswith(self.GETTEXT_ARTIFACT):
                mo_dest = pkg_path / artifact[: -len(self.GETTEXT_ARTIFACT)]

        if mo_dest is None:
            raise FileNotFoundError(
                "Could not determine gettext mo file destination using pyproject.toml"
            )

        project_name = config_dict["project"]["name"]

        # Compile the mo files
        for in_file in po_dir.glob("*.po"):
            print(f'- Compiling "{in_file.name}"')

            mo_file = mo_dest / in_file.stem / "LC_MESSAGES" / f"{project_name}.mo"
            mo_file.parent.mkdir(parents=True, exist_ok=True)
            self._compile_po_to_mo(in_file, mo_file)

        # Translate .desktop and .xml files
        gettext_files = config_dict["tool"]["gettextbuild"]["files"]
        for folder, files in gettext_files.items():
            dest_folder = pkg_path / folder
            dest_folder.mkdir(parents=True, exist_ok=True)
            for f in files:
                print(f'- Translating "{Path(f).stem}"')
                in_file = pkg_path / f
                translated_file = dest_folder / in_file.stem
                self._translate_file(po_dir, in_file, translated_file)
