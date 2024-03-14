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


import functools
import shutil
from pathlib import Path
from typing import Any

from hatch.utils.platform import Platform
from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class GettextBuildHook(BuildHookInterface):
    """
    Compile GNU gettext translation files from po-format into
    mo-format using the GNU gettext utility msgfmt, and optionally translate files
    using the GNU gettext utility intltool-merge.

    Cleans up any files that it creates, and any resulting directories, but
    only if the directories are empty.
    """

    GETTEXT_SWITCHES = {
        ".xml": "-x",
        ".desktop": "-d",
    }

    def _compile_po_to_mo(self, po_file: Path, mo_file: Path) -> None:
        """
        Compile po-file to mo-file using the GNU gettext utility msgfmt

        :param po_file: the full path to the po file
        :param mo_file: the full path to the mo file
        """

        cmd = f"msgfmt --output-file={mo_file} {po_file}"
        self.platform.check_command(cmd, text=True, capture_output=True)

    def _translate_file(
        self, po_dir: Path, in_file: Path, translated_file: Path
    ) -> None:
        """
        Translate a .desktop or .xml file using the GNU gettext utility intltool-merge

        :param po_dir: directory containing the po files
        :param in_file: the full path to the .desktop.in or .xml.in file
        :param translated_file: the full path to the output .desktop or .xml file
        """

        file_extension = in_file.suffixes[-2]
        switch = self.GETTEXT_SWITCHES[file_extension]
        cmd = f"intltool-merge {switch} {po_dir} {in_file} {translated_file}"
        self.platform.check_command(cmd, text=True, capture_output=True)

    def _clean_files(self, relative_file_paths: list[str]) -> None:
        project_root = Path(self.root)
        for p in relative_file_paths:
            full_path = project_root / p
            if full_path.exists():
                print(f"Removing {full_path}")
                full_path.unlink()

    def _has_only_subdirectories(self, path: Path) -> bool:
        """
        Checks if a directory has only subdirectories and no files.

        :param path: the full path to the directory to check
        :return: True if the directory has only subdirectories and no files
        """

        for entry in path.iterdir():
            if entry.is_file():
                return False
            # Recursively check subdirectories
            if entry.is_dir() and not self._has_only_subdirectories(entry):
                return False
        return True

    def _clean_directory_tree_only_if_has_empty_subdirectories(
        self, folder: Path
    ) -> None:
        """
        Removes a directory tree only if it contains no files and any of its
        subdirectories in its tree likewise contain no files

        :param folder:  full path of the directory
        """

        if folder.is_dir() and self._has_only_subdirectories(folder):
            print(f"Removing {folder}")
            shutil.rmtree(folder)

    def clean(self, versions: list[str]) -> None:
        """
        Remove all files created by this plug-in, if they exist.

        Remove all their directories only they contain no other files,
        with the same being true of their subdirectories.

        :param versions: see Hatch documentation for details
        """

        self.load_gettextbuild_config()

        if self._locale_dir.is_dir():
            self._clean_files(self.mo_files_to_build)

        if self._gtb_files:
            self._clean_files(self.translate_files_to_build)

        self._clean_directory_tree_only_if_has_empty_subdirectories(self._locale_dir)

        project_root = Path(self.root)
        for translated_file in self.translate_files_to_build:
            folders = (project_root / p for p in Path(translated_file).parents)
            translated_subfolders = filter(lambda p: p != project_root, folders)
            for folder in translated_subfolders:
                self._clean_directory_tree_only_if_has_empty_subdirectories(folder)

    def load_gettextbuild_config(self) -> None:
        """
        Load the gettextbuild config from pyproject.toml using hatch's interface
        and assign the values to private class variables.
        """

        try:
            self._gtb = self.metadata.config["tool"]["gettextbuild"]
        except KeyError:
            raise ValueError(
                '"[tool.gettextbuild]" not found in pyproject.toml.',
            )

        self._i18n_name = self._gtb.get("i18n_name") or self.metadata.name

        project_root = Path(self.root)

        self._po_dir = project_root / (self._gtb.get("po_directory") or "po")
        if not self._po_dir.is_dir():
            raise ValueError(
                'Configure "po_directory" in "[tool.gettextbuild]" in pyproject.toml '
                'to the project\'s po directory [default: "po"], and ensure the '
                "directory exists."
            )
        try:
            self._locale_dir = project_root / self._gtb["locale_directory"]
        except KeyError:
            raise ValueError(
                'Configure "locale_directory" in "[tool.gettextbuild]" in '
                "pyproject.toml to the directory in which compiled mo files will be "
                "written to."
            )
        try:
            assert self._locale_dir != project_root
        except AssertionError:
            raise ValueError(
                "The locale directory must be different from the project's root "
                "directory."
            )
        try:
            assert self._po_dir != self._locale_dir
        except AssertionError:
            raise ValueError(
                "The locale directory must be different from the po directory."
            )

        self._gtb_files = self._gtb.get("files")

    @functools.cache
    def po_mo_pairs(self) -> list[tuple[Path, str]]:
        """
        :return: a list of tuples containing po files, and their corresponding mo
         filenames that the build will create.

         Each po file will be a full Path, but the mo files' path will be a string
         whose path is relative to the project root.
        """

        return [
            (
                Path(po_file),
                str(
                    Path(self._gtb["locale_directory"])
                    / po_file.stem
                    / "LC_MESSAGES"
                    / f"{self._i18n_name}.mo"
                ),
            )
            for po_file in self._po_dir.glob("*.po")
        ]

    @functools.cache
    def translate_file_pairs(self) -> list[tuple[Path, str]]:
        """
        :return: a list of tuples containing .in files, and their corresponding
         files to be translated by intltool-merge that the build will create.

         Each .in file will be a full Path, but the translated files' path will be a
         string whose path is relative to the project root.
        """

        if self._gtb_files is None:
            return []

        project_root = Path(self.root)
        files_to_build = []
        for folder, files in self._gtb_files.items():
            for in_file in files:
                translated_file = Path(folder) / Path(in_file).stem
                files_to_build.append((project_root / in_file, str(translated_file)))
        return files_to_build

    @property
    def mo_files_to_build(self) -> list[str]:
        """
        :return: a list of mo filenames with relative paths that the build will create
        """

        return [pair[1] for pair in self.po_mo_pairs()]

    @property
    def translate_files_to_build(self) -> list[str]:
        """
        :return: a list of files translated by intltool-merge that the build will create

         Each file's path will be a string whose path is relative to the project root.
        """

        return [pair[1] for pair in self.translate_file_pairs()]

    def compile_mo_files(self) -> None:
        """
        Compile .po files into .mo files using msgfmt
        """

        project_root = Path(self.root)

        for po_file, m in self.po_mo_pairs():
            print(f'Compiling "{po_file.name}"')
            mo_file = project_root / m
            mo_file.parent.mkdir(parents=True, exist_ok=True)
            self._compile_po_to_mo(po_file, mo_file)

    def translate_files(self) -> None:
        """
        Translate .desktop and .xml files using intltool-merge
        """

        project_root = Path(self.root)
        for in_file, to_translate in self.translate_file_pairs():
            to_translate = project_root / to_translate
            to_translate.parent.mkdir(parents=True, exist_ok=True)
            print(f'Translating "{to_translate.stem}"')
            self._translate_file(self._po_dir, in_file, to_translate)

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if self.target_name not in ["wheel", "sdist"]:
            return

        self.platform = Platform()
        self.load_gettextbuild_config()

        build_data["artifacts"].extend(self.mo_files_to_build)
        self.compile_mo_files()

        if self._gtb_files:
            build_data["artifacts"].extend(self.translate_files_to_build)
            self.translate_files()
