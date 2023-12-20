#!/usr/bin/python3
__author__ = 'Damon Lynch'

# Copyright (C) 2015-2020 Damon Lynch <damonlynch@gmail.com>

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

import sys
import os
import shutil
import pickle
import tempfile
import argparse

from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import (QApplication, QTextEdit)
from PyQt5.QtGui import (QPixmap, QImage)
from xdg import BaseDirectory
import gphoto2 as gp

from raphodo.utilities import CacheDirs

from raphodo.thumbnailer import Thumbnailer
from raphodo.rpdfile import RPDFile
from raphodo.cache import ThumbnailCacheSql
from raphodo.camera import autodetect_cameras


class TestThumbnail(QTextEdit):
    def __init__(self, testdata: str, profile: bool, no_workers: int, cache_dirs: CacheDirs,
                 camera_model: str, camera_port: str, parent=None) -> None:
        super().__init__(parent)

        self.received = 0
        self.cache_dirs = cache_dirs

        with open(testdata, 'rb') as td:
            self.rpd_files = pickle.load(td)

        self.thumbnailer = Thumbnailer(self, no_workers)
        self.thumbnailer.ready.connect(self.startGeneration)
        self.thumbnailer.thumbnailReceived.connect(self.thumbnailReceived)
        self.camera_model = camera_model
        self.camera_port = camera_port

    def startGeneration(self):
        print("Starting generation of {} thumbnails....".format(len(self.rpd_files)))

        self.thumbnailer.generateThumbnails(0, self.rpd_files, False, 'test', self.cache_dirs,
                                                self.camera_model, self.camera_port)

    def thumbnailReceived(self, rpd_file: RPDFile, thumbnail: QPixmap) -> None:
        self.received += 1
        if thumbnail is not None:
            self.insertPlainText('{}x{} - {}\n'.format(thumbnail.width(),
                                                   thumbnail.height(),
                                                   rpd_file.full_file_name))
        else:
            self.insertPlainText('No thumbnail for {}\n'.format(rpd_file.full_file_name))

    def sizeHint(self):
        return QSize(800, 900)

    def closeEvent(self, QCloseEvent):
        if self.received != len(self.rpd_files):
            print("WARNING: Didn't receive correct amount of thumbnails. Missing {}".format(
                len(self.rpd_files) - self.received))
        self.thumbnailer.stop()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--data', dest='data', type=str)
    parser.add_argument('-p', '--profile', dest='profile', action="store_true")
    parser.add_argument("--reset", action="store_true", dest="reset",
                 help="reset all thumbnail caches and exit")
    args = parser.parse_args()
    if args.reset:
        cache = ThumbnailCacheSql(create_table_if_not_exists=False)
        cache.purge_cache()
        print("Thumbnail cache reset")
        cache = os.path.join(BaseDirectory.xdg_cache_home, 'thumbnails')
        folders = [os.path.join(cache, subdir) for subdir in ('normal', 'large')]
        i = 0
        for folder in folders:
            for the_file in os.listdir(folder):
                file_path = os.path.join(folder, the_file)
                try:
                    if os.path.isfile(file_path):
                        i += 1
                        os.remove(file_path)
                except OSError as e:
                    print(e)
        print('Removed {} XDG thumbnails'.format(i))

    camera_model = camera_port = None
    if args.data is None:
        testdata = 'thumbnail_data_small'
    else:
        testdata = args.data
        if testdata == 'thumbnail_data_camera':
            cameras = autodetect_cameras()
            camera_model, camera_port = cameras[0]

    no_workers = 4

    app = QApplication(sys.argv)

    with tempfile.TemporaryDirectory() as tempdir:
        cache_dirs = CacheDirs(tempdir, tempdir)
        tt = TestThumbnail(testdata, args.profile, no_workers, cache_dirs, camera_model,
                           camera_port)
        tt.show()
        app.setActiveWindow(tt)
        code = app.exec_()
    sys.exit(code)
