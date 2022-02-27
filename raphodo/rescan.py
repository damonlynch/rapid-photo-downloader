#!/usr/bin/env python3

# Copyright (C) 2011-2021 Damon Lynch <damonlynch@gmail.com>

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
Given a collection of RPDFiles, rescans a camera to locate their 'new' location.

Used in case of iOS and possibly other buggy devices that generate subfolders
for photos / videos seemingly at random each time the device is initialized for access,
which is what a gphoto2 process does.
"""

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2011-2021, Damon Lynch"

from typing import List, DefaultDict, Optional
import logging
from collections import defaultdict
import os
from itertools import chain

import gphoto2 as gp

from raphodo.rpdfile import RPDFile
from raphodo.camera import Camera, CameraProblemEx
from raphodo.prefs.preferences import ScanPreferences, Preferences


class RescanCamera:
    """
    Rescan a camera / smartphone looking for files that were already
    previously scanned.

    Newly updated files are stored in the member variable rpd_files, and
    files that could not be relocated are found in member missing_rpd_files.

    Assumes camera already initialized, with specific folders correctly set.
    """

    def __init__(self, camera: Camera, prefs: Preferences) -> None:
        self.camera = camera
        if not camera.specific_folder_located:
            logging.warning(
                "No folders located on %s: there might be a bug the camera firmware "
                "or libgphoto2. Continuing rescan regardless.",
                camera.display_name,
            )
        # Relocated RPD files
        self.rpd_files = []  # type: List[RPDFile]
        # Missing RPD files
        self.missing_rpd_files = []  # type: List[RPDFile]
        self.prefs = prefs
        self.scan_preferences = None  # type: Optional[ScanPreferences]

    def rescan_camera(self, rpd_files: List[RPDFile]) -> None:
        """
        Determine if the files are found in the same folders as when the camera was
        last initialized. Works around a crazy iOS bug.

        :param rpd_files: if individual rpd_files are indeed located in new folders,
         a side effect of calling this function is that the rpd_files will have their
         paths updated, even though a new list is returned
        """

        if not rpd_files:
            return
        # attempt to read extract of file
        rpd_file = rpd_files[0]
        try:
            self.camera.get_exif_extract(folder=rpd_file.path, file_name=rpd_file.name)
        except CameraProblemEx as e:
            logging.debug(
                "Failed to read extract of sample file %s: rescanning %s",
                rpd_file.name,
                self.camera.display_name,
            )
        else:
            # Apparently no problems accessing the first file, so let's assume the rest are
            # fine. Let's hope that's a valid assumption.
            logging.debug("%s did not need to be rescanned", self.camera.display_name)
            self.rpd_files = rpd_files
            return

        # filename: RPDFile
        self.prev_scanned_files = defaultdict(
            list
        )  # type: DefaultDict[str, List[RPDFile]]
        self.scan_preferences = ScanPreferences(self.prefs.ignored_paths)

        for rpd_file in rpd_files:
            self.prev_scanned_files[rpd_file.name].append(rpd_file)

        for folders in self.camera.specific_folders:
            for folder in folders:
                logging.info("Rescanning %s on %s", folder, self.camera.display_name)
                self.relocate_files_on_camera(folder)

        self.missing_rpd_files = list(chain(*self.prev_scanned_files.values()))

    def relocate_files_on_camera(self, path: str) -> None:
        """
        Recursively scan path looking for the folders in which previously located files
        are now stored.

        :param path: path to check in
        """

        files_in_folder = []

        try:
            files_in_folder = self.camera.camera.folder_list_files(
                path, self.camera.context
            )
        except gp.GPhoto2Error as e:
            logging.error("Unable to scan files on camera: error %s", e.code)

        for name, value in files_in_folder:
            if name in self.prev_scanned_files:
                prev_rpd_files = self.prev_scanned_files[name]
                if len(prev_rpd_files) > 1:
                    rpd_file = None  # type: Optional[RPDFile]
                    # more than one file with the same filename is found on the camera
                    # compare match by modification time and size check
                    for prev_rpd_file in prev_rpd_files:
                        modification_time, size = 0, 0
                        if prev_rpd_file.modification_time:
                            try:
                                modification_time, size = self.camera.get_file_info(
                                    path, name
                                )
                            except gp.GPhoto2Error as e:
                                logging.error(
                                    "Unable to access modification_time or size from "
                                    "%s on %s. Error code: %s",
                                    os.path.join(path, name),
                                    self.camera.display_name,
                                    e.code,
                                )
                        if (
                            modification_time == prev_rpd_file.modification_time
                            and size == prev_rpd_file.size
                        ):
                            rpd_file = prev_rpd_file
                            prev_rpd_files.remove(prev_rpd_file)
                            break
                else:
                    rpd_file = prev_rpd_files[0]
                    del self.prev_scanned_files[name]

                if rpd_file:
                    rpd_file.path = path
                    self.rpd_files.append(rpd_file)

        # Recurse over subfolders in which we should
        folders = []
        try:
            for name, value in self.camera.camera.folder_list_folders(
                path, self.camera.context
            ):
                if self.scan_preferences.scan_this_path(os.path.join(path, name)):
                    folders.append(name)
        except gp.GPhoto2Error as e:
            logging.error(
                "Unable to scan files on %s. Error code: %s",
                self.camera.display_name,
                e.code,
            )

        for name in folders:
            self.relocate_files_on_camera(os.path.join(path, name))
