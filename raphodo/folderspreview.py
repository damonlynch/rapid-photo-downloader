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
Create preview of destination folder structure
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2016, Damon Lynch"

import os
from collections import namedtuple, defaultdict
import logging
from typing import List, Set, Sequence, Dict, Optional

from raphodo.rpdfile import RPDFile


DownloadDestination = namedtuple('DownloadDestination',
                                 'photo_download_folder, video_download_folder, photo_subfolder, '
                                 'video_subfolder')

class FoldersPreview:
    def __init__(self):
        self.generated_photo_subfolders = set()  # type: Set[str]
        self.generated_video_subfolders = set()  # type: Set[str]
        self.created_photo_subfolders = defaultdict(set)  # type: Dict[int, Set[str]]
        self.created_video_subfolders = defaultdict(set)  # type: Dict[int, Set[str]]
        self.existing_subfolders = set()  # type: Set[str]
        self.photo_download_folder = ''
        self.video_download_folder = ''
        self.photo_subfolder = ''
        self.video_subfolder = ''
        self.dirty = False
        
        self.generated_photo_subfolders.add('2016/20160606')
        self.generated_photo_subfolders.add('2016/20160707')

        self.generated_video_subfolders.add('2016/20160101')
        self.generated_video_subfolders.add('2016/20160102')
        self.generated_video_subfolders.add('2016/20160606')

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

    def process_rpd_files(self, rpd_files: Sequence[RPDFile],
                          destination: DownloadDestination) -> Set[str]:
        self.process_destination(destination=destination)
        self.dirty = True

    def preview_subfolders(self) -> Set[str]:
        p = self._flatten_set(self.created_photo_subfolders)
        v = self._flatten_set(self.created_video_subfolders)
        return p|v

    def download_subfolders(self) -> Set[str]:
        p = self._generate_dests(self.photo_download_folder, self.generated_photo_subfolders)
        v = self._generate_dests(self.video_download_folder, self.generated_video_subfolders)
        return p|v

    def process_destination(self, destination: DownloadDestination) -> None:
        if destination.photo_download_folder != self.photo_download_folder:
            self.photo_download_folder = destination.photo_download_folder
            if self.generated_photo_subfolders:
                self.move_subfolders(photos=True)
            
            
        if destination.video_download_folder != self.video_download_folder:
            self.video_download_folder = destination.video_download_folder
            if self.generated_video_subfolders:
                self.move_subfolders(photos=False)

    def move_subfolders(self, photos: bool) -> None:

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
        self.clean_generated_folders(remove=self.created_photo_subfolders)
        self.clean_generated_folders(remove=self.created_video_subfolders)

    def create_path(self, path: str, photos: bool) -> None:
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







