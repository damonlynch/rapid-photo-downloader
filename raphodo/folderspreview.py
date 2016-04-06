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
# along with Rapid Photo Downloader.  If not,
# see <http://www.gnu.org/licenses/>.

"""
Two tasks:

Create a preview of destination folder structure by actually creating the directories
on the file system, and removing them at program exit if they were not used.


Highlight to the user where files will be downloaded to, regardless of whether the
subfolder already exists or not.
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2016, Damon Lynch"

import os
from collections import namedtuple, defaultdict
import logging
from typing import List, Set, Sequence, Dict, Optional

from raphodo.rpdfile import RPDFile
from raphodo.constants import FileType
import raphodo.generatename as gn


DownloadDestination = namedtuple('DownloadDestination',
                                 'photo_download_folder, video_download_folder, photo_subfolder, '
                                 'video_subfolder')

class FoldersPreview:
    def __init__(self):
        # Subfolders to generate, in simple string format
        self.generated_photo_subfolders = set()  # type: Set[str]
        self.generated_video_subfolders = set()  # type: Set[str]

        # Subfolders actually created by this class, differentiated by level
        self.created_photo_subfolders = defaultdict(set)  # type: Dict[int, Set[str]]
        self.created_video_subfolders = defaultdict(set)  # type: Dict[int, Set[str]]

        # Subfolders that were not created by this class
        self.existing_subfolders = set()  # type: Set[str]

        # Download config paramaters
        self.photo_download_folder = ''
        self.video_download_folder = ''
        self.photo_subfolder = ''
        self.video_subfolder = ''

        # Track whether some change was made to the file system
        self.dirty = False

    def __repr__(self):
        return 'FoldersPreview(%s photo dirs, %s video dirs)' % (len(self._flatten_set(
            self.created_photo_subfolders)), len(self._flatten_set(self.created_video_subfolders)))

    def _flatten_set(self, s: Dict[int, Set[str]]) -> Set[str]:
        return {path for level in s for path in s[level]}

    def _generate_dests(self, dest: str, subfolders: Set[str]) -> Set[str]:
        d = set()
        for subfolder in subfolders:
            components = ''
            for component in subfolder.split(os.sep):
                components = os.path.join(components, component)
                d.add(os.path.join(dest, components))
        return d

    def process_rpd_files(self, rpd_files: Optional[Sequence[RPDFile]],
                          destination: DownloadDestination,
                          strip_characters: bool) -> Set[str]:
        """
        Determine if subfolder generation config or download destination
        has changed.

        If given a list of rpd_files, generate subfolder names for each.

        :param rpd_files: rpd_files to generate names for
        :param destination: Tuple with download destation and
         subfolder gneeration config
        :param strip_characters: value from user prefs.
        """

        self.process_destination(destination=destination)
        if rpd_files:
            self.generate_subfolders(rpd_files=rpd_files, strip_characters=strip_characters)

    def preview_subfolders(self) -> Set[str]:
        """
        Subfolders that have been generated to preview to the user where their
        files will be downloaded
        :return: set of actual subfolders in simple string format
        """

        p = self._flatten_set(self.created_photo_subfolders)
        v = self._flatten_set(self.created_video_subfolders)
        return p|v

    def download_subfolders(self) -> Set[str]:
        """
        Subfolders where files will be downloaded to, regardless of
        whether the subfolder already existed or not.
        :return: set of actual subfolders in simple string format
        """

        p = self._generate_dests(self.photo_download_folder, self.generated_photo_subfolders)
        v = self._generate_dests(self.video_download_folder, self.generated_video_subfolders)
        return p|v

    def process_destination(self, destination: DownloadDestination) -> None:
        """
        Handle any changes in destination directories or subfolder generation config
        :param destination: Tuple with download destation and
         subfolder gneeration config
        """

        if destination.photo_download_folder != self.photo_download_folder:
            self.dirty = True
            self.photo_download_folder = destination.photo_download_folder
            if self.generated_photo_subfolders:
                self.move_subfolders(photos=True)

        if destination.video_download_folder != self.video_download_folder:
            self.video_download_folder = destination.video_download_folder
            self.dirty = True
            if self.generated_video_subfolders:
                self.move_subfolders(photos=False)

        if destination.photo_subfolder != self.photo_subfolder:
            self.dirty = True
            self.photo_subfolder = destination.photo_subfolder
            self.clean_generated_folders(remove=self.created_photo_subfolders,
                                         keep=self.created_video_subfolders)

        if destination.video_subfolder != self.video_subfolder:
            self.dirty = True
            self.video_subfolder = destination.video_subfolder
            self.clean_generated_folders(remove=self.created_video_subfolders,
                                         keep=self.created_photo_subfolders)

    def generate_subfolders(self, rpd_files: Sequence[RPDFile], strip_characters: bool) -> None:
        """
        Generate on the file system if necessary the subfolders that will be
        used for the download (assuming the subfolder geneation config doesn't
        change, of course).
        :param rpd_files: rpd_files to generate names for
        :param strip_characters: value from user prefs.
        """

        for rpd_file in rpd_files:  # type: RPDFile
            photo = rpd_file.file_type == FileType.photo
            rpd_file.strip_characters = strip_characters
            if photo:
                generator = gn.PhotoSubfolder(self.photo_subfolder, no_metadata=True)
                generated_subfolders = self.generated_photo_subfolders
            else:
                generator = gn.VideoSubfolder(self.video_subfolder, no_metadata=True)
                generated_subfolders = self.generated_video_subfolders
            value = generator.generate_name(rpd_file)
            if value:
                if value not in generated_subfolders:
                    generated_subfolders.add(value)
                    self.create_path(path=value, photos=photo)
                    self.dirty = True

    def move_subfolders(self, photos: bool) -> None:
        """
        Handle case where the user has chosen a different download directory
        :param photos: whether working on photos (True) or videos (False)
        """

        if photos:
            self.clean_generated_folders(remove=self.created_photo_subfolders,
                                         keep=self.created_video_subfolders)
            self.created_photo_subfolders = defaultdict(set)  # type: Dict[int, Set[str]]
            for path in self.generated_photo_subfolders:
                self.create_path(path=path, photos=True)
        else:
            self.clean_generated_folders(remove=self.created_video_subfolders,
                                         keep=self.created_photo_subfolders)
            self.created_video_subfolders = defaultdict(set)  # type: Dict[int, Set[str]]
            for path in self.generated_video_subfolders:
                self.create_path(path=path, photos=False)

    def clean_generated_folders(self, remove: Dict[int, Set[str]],
                                keep: Optional[Dict[int, Set[str]]]=None) -> None:
        """
        Remove preview folders from the file system, if necessary keeping those
        used for the other type of file (e.g. if moving only photos, keep video download
        dirs)

        :param remove: folders to remove
        :param keep: folders to keep
        """

        levels = [level for level in remove]
        levels.sort(reverse=True)

        if keep is not None:
            keep = self._flatten_set(keep)
        else:
            keep = set()

        for level in levels:
            for subfolder in remove[level]:
                if (subfolder not in keep and subfolder not in self.existing_subfolders and
                        os.path.isdir(subfolder)):
                    try:
                        os.rmdir(subfolder)
                        logging.debug("While cleaning generated folders, removed %s", subfolder)
                    except OSError:
                        logging.debug("While cleaning generated folders, did not remove %s. It "
                                      "may not be empty.", subfolder)
                else:
                    logging.debug("While cleaning generated folders, not removing %s ", subfolder)

    def clean_all_generated_folders(self) -> None:
        """
        Remove all unused (i.e. empty) generated preview folders from the file system.

        Called at program exit.
        """

        self.clean_generated_folders(remove=self.created_photo_subfolders)
        self.clean_generated_folders(remove=self.created_video_subfolders)
        self.generated_photo_subfolders = set()  # type: Set[str]
        self.generated_video_subfolders = set()  # type: Set[str]

    def create_path(self, path: str, photos: bool) -> None:
        """
        Create folders on the actual file system if they don't already exist

        :param path: folder structure to create
        :param photos: whether working on photos (True) or videos (False)
        """

        components = ''
        level = -1
        if photos:
            dest = self.photo_download_folder
            creating = self.created_photo_subfolders
        else:
            dest = self.video_download_folder
            creating = self.created_video_subfolders

        created_photo_subfolders = self._flatten_set(self.created_photo_subfolders)

        created_video_subfolders = self._flatten_set(self.created_video_subfolders)

        already_created = created_photo_subfolders | created_video_subfolders

        for component in path.split(os.sep):
            level += 1
            components = os.path.join(components, component)
            p = os.path.join(dest, components)
            if os.path.isfile(p):
                logging.error("While generating provisional download folders, "
                              "found conflicting file %s. Therefore cannot create path %s", p, path)
                return
            if p in already_created:
                creating[level].add(p)
            elif not os.path.isdir(p):
                creating[level].add(p)
                if p not in already_created:
                    try:
                        os.mkdir(p)
                    except OSError:
                        logging.error("Failed to create download directory %s", p)
                        return
                    logging.debug("Created provisional download folder: %s", p)
            else:
                self.existing_subfolders.add(p)
                logging.debug("Provisional download folder already exists: %s", p)







