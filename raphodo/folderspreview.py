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
from typing import Tuple, Set, Sequence, Dict, Optional

from PyQt5.QtWidgets import QFileSystemModel

from raphodo.rpdfile import RPDFile
from raphodo.constants import FileType
import raphodo.generatename as gn
from raphodo.storage import validate_download_folder


DownloadDestination = namedtuple('DownloadDestination',
                                 'photo_download_folder, video_download_folder, photo_subfolder, '
                                 'video_subfolder')

class FoldersPreview:
    """
    Core tasks of this class are to be able to handle these scenarios:
     * the user changing the download destination
     * download destination being invalid or not yet specified
     * knowing which download subfolders already existed
     * files from more than one device be downloaded to the same subfolders
     * photos and videos being downloaded to overlapping subfolders folders
     * the download not proceeding, and the generated subfolders needing to
       be removed
     * the device being removed, and the generated subfolders needing to
       be removed
    """

    def __init__(self):
        # Subfolders to generate, in simple string format
        self.generated_photo_subfolders = set()  # type: Set[str]
        self.generated_video_subfolders = set()  # type: Set[str]

        # Scan ids associated with generated subfolders
        self.generated_photo_subfolders_scan_ids = defaultdict(set)  # type: Dict[str, Set[int]]
        self.generated_video_subfolders_scan_ids = defaultdict(set)  # type: Dict[str, Set[int]]

        # Subfolders actually created by this class, differentiated by level.
        # Need to differentiate levels because of need for fine grained control
        # due to scenarios outlined above.
        self.created_photo_subfolders = defaultdict(set)  # type: Dict[int, Set[str]]
        self.created_video_subfolders = defaultdict(set)  # type: Dict[int, Set[str]]

        self.scan_ids_for_created_subfolders = defaultdict(set)  # type: Dict[Tuple[int, str], Set[int]]

        # Subfolders that were not created by this class, in simple string format
        self.existing_subfolders = set()  # type: Set[str]

        # Download config paramaters
        self.photo_download_folder = ''
        self.video_download_folder = ''
        self.photo_download_folder_valid = False
        self.video_download_folder_valid = False
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
            self.photo_download_folder_valid = validate_download_folder(
                self.photo_download_folder).valid
            if self.photo_download_folder_valid:
                # Handle situation where the user clicks on one of the
                # generated subfolders to use as the new new download
                # folder. A strange thing to do in all likelihood, but
                # need to handle it in any case.
                self.existing_subfolders.add(self.photo_download_folder)
            if self.generated_photo_subfolders:
                self.move_subfolders(photos=True)

        if destination.video_download_folder != self.video_download_folder:
            self.video_download_folder = destination.video_download_folder
            self.dirty = True
            self.video_download_folder_valid = validate_download_folder(
                self.video_download_folder).valid
            if self.video_download_folder_valid:
                # See explanation above.
                self.existing_subfolders.add(self.video_download_folder)
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
        used for the download (assuming the subfolder generation config doesn't
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
                generated_subfolder_scan_ids = self.generated_photo_subfolders_scan_ids
            else:
                generator = gn.VideoSubfolder(self.video_subfolder, no_metadata=True)
                generated_subfolders = self.generated_video_subfolders
                generated_subfolder_scan_ids = self.generated_video_subfolders_scan_ids
            value = generator.generate_name(rpd_file)
            if value:
                if value not in generated_subfolders:
                    generated_subfolders.add(value)
                    generated_subfolder_scan_ids[value].add(rpd_file.scan_id)
                    self.create_path(path=value, photos=photo, scan_ids={rpd_file.scan_id})
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
                scan_ids = self.generated_photo_subfolders_scan_ids[path]
                self.create_path(path=path, photos=True, scan_ids=scan_ids)
        else:
            self.clean_generated_folders(remove=self.created_video_subfolders,
                                         keep=self.created_photo_subfolders)
            self.created_video_subfolders = defaultdict(set)  # type: Dict[int, Set[str]]
            for path in self.generated_video_subfolders:
                scan_ids = self.generated_video_subfolders_scan_ids[path]
                self.create_path(path=path, photos=False, scan_ids=scan_ids)

    def clean_generated_folders(self, remove: Dict[int, Set[str]],
                                keep: Optional[Dict[int, Set[str]]]=None,
                                scan_id: Optional[int]=None,
                                fsmodel: Optional[QFileSystemModel]=None) -> None:
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

        removed_folders = []

        for level in levels:
            for subfolder in remove[level]:
                if (subfolder not in keep and subfolder not in self.existing_subfolders and
                        os.path.isdir(subfolder)):
                    if scan_id is not None:
                        do_rmdir = False
                        key = (level, subfolder)
                        scan_ids = self.scan_ids_for_created_subfolders[key]
                        if scan_id in scan_ids:
                            if len(scan_ids) == 1:
                                do_rmdir = True
                                removed_folders.append((level, subfolder))
                            scan_ids.remove(scan_id)
                            if len(scan_ids) == 0:
                                del self.scan_ids_for_created_subfolders[key]
                    else:
                        do_rmdir = True
                    if do_rmdir:
                        if not os.listdir(subfolder):
                            if fsmodel is not None:
                                index = fsmodel.index(subfolder)
                                if not fsmodel.rmdir(index):
                                    logging.debug("While cleaning generated folders, did not "
                                                  "remove %s. The cause for the error is unknown.",
                                                  subfolder)
                            else:
                                try:
                                    os.rmdir(subfolder)
                                except OSError as e:
                                    logging.debug("While cleaning generated folders, did not "
                                                  "remove %s. Code: %s. Error: %s.",
                                                  subfolder, e.errno, e.strerror)

        if scan_id is not None:
            for level, subfolder in removed_folders:
                remove[level].remove(subfolder)

    def clean_all_generated_folders(self, fsmodel: QFileSystemModel) -> None:
        """
        Remove all unused (i.e. empty) generated preview folders from the file system.

        Called at program exit.
        """
        self.clean_generated_folders(remove=self.created_photo_subfolders, fsmodel=fsmodel)
        self.clean_generated_folders(remove=self.created_video_subfolders, fsmodel=fsmodel)
        self.generated_photo_subfolders = set()  # type: Set[str]
        self.generated_video_subfolders = set()  # type: Set[str]
        self.generated_photo_subfolders_scan_ids = defaultdict(set)  # type: Dict[str, Set[int]]
        self.generated_video_subfolders_scan_ids = defaultdict(set)  # type: Dict[str, Set[int]]

    def clean_generated_folders_for_scan_id(self, scan_id: int) -> None:

        logging.debug("Cleaning subfolders created for scan id %s", scan_id)

        self.clean_generated_folders(remove=self.created_photo_subfolders, scan_id=scan_id)
        self.clean_generated_folders(remove=self.created_video_subfolders, scan_id=scan_id)
        for subfolder, scan_ids in self.generated_photo_subfolders_scan_ids.items():
            if scan_id in scan_ids:
                self.generated_photo_subfolders_scan_ids[subfolder].remove(scan_id)
                if not len(self.generated_photo_subfolders_scan_ids[subfolder]):
                    self.generated_photo_subfolders.remove(subfolder)
        for subfolder, scan_ids in self.generated_video_subfolders_scan_ids.items():
            if scan_id in scan_ids:
                self.generated_video_subfolders_scan_ids[subfolder].remove(scan_id)
                if not len(self.generated_video_subfolders_scan_ids[subfolder]):
                    self.generated_video_subfolders.remove(subfolder)

        # Delete subfolders that are no longer associated with a scan id
        # Can't do that above, as there are iterating over the sets
        for subfolder in list(self.generated_photo_subfolders_scan_ids.keys()):
            if not self.generated_photo_subfolders_scan_ids[subfolder]:
                del self.generated_photo_subfolders_scan_ids[subfolder]
                
        for subfolder in list(self.generated_video_subfolders_scan_ids.keys()):
            if not self.generated_video_subfolders_scan_ids[subfolder]:
                del self.generated_video_subfolders_scan_ids[subfolder]

    def create_path(self, path: str, photos: bool, scan_ids: Set[int]) -> None:
        """
        Create folders on the actual file system if they don't already exist

        Only creates a path if the download folder is valid

        :param path: folder structure to create
        :param photos: whether working on photos (True) or videos (False)
        :param scan_ids: scan ids of devices associated with this subfolder
        """

        components = ''
        level = -1
        if photos:
            dest = self.photo_download_folder
            dest_valid = self.photo_download_folder_valid
            creating = self.created_photo_subfolders
        else:
            dest = self.video_download_folder
            dest_valid = self.video_download_folder_valid
            creating = self.created_video_subfolders

        if not dest_valid:
            logging.debug("Not creating preview folders because download folder is invalid")
            return

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
                # Even though the directory is already created, it may have been created
                # for the other file type, so record the fact that we're creating it for
                # this file type.
                creating[level].add(p)
            elif not os.path.isdir(p):
                creating[level].add(p)
                try:
                    os.mkdir(p)
                    self.scan_ids_for_created_subfolders[(level, p)].update(scan_ids)
                except OSError:
                    logging.error("Failed to create download directory %s", p)
                    return
                logging.debug("Created provisional download folder: %s", p)
            else:
                self.existing_subfolders.add(p)
                logging.debug("Provisional download folder already exists: %s", p)







