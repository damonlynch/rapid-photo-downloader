#!/usr/bin/python3
__author__ = 'Damon Lynch'

# Copyright (C) 2015 Damon Lynch <damonlynch@gmail.com>

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
import logging
import pickle
import tempfile
import argparse

from PyQt5.QtCore import (QThread, Qt, QTimer, pyqtSignal, QSize)
from PyQt5.QtWidgets import (QApplication, QTextEdit)
from PyQt5.QtGui import (QPixmap, QImage)
import zmq
from xdg import BaseDirectory

from utilities import CacheDirs
from interprocess import (GenerateThumbnailsArguments,
                          GenerateThumbnailsResults)

# from thumbnaildisplay import ThumbnailManager
from rpdfile import RPDFile
from cache import ThumbnailCacheSql


# class TestThumbnailManager(ThumbnailManager):
#     message = pyqtSignal(RPDFile, QPixmap)
#     def __init__(self, profile: bool):
#         super().__init__(logging_port=2000)
#         self._profile = profile
#
#     def _get_cmd(self) -> str:
#         folder = os.path.abspath(os.path.join(os.path.dirname(__file__),
#                                                   os.pardir))
#         cmd = os.path.join(folder, self._process_to_run)
#         if not self._profile:
#             return cmd
#         else:
#             cmd = 'kernprof -v -l {}'.format(cmd)
#             print("Running", cmd)
#             return cmd


# class TestThumbnail(QTextEdit ):
#     def __init__(self, testdata: str, profile: bool, parent=None) -> None:
#         super().__init__(parent)
#
#         scan_id = 0
#         self.received = 0
#
#         with open(testdata, 'rb') as td:
#             self.rpd_files = pickle.load(td)
#
#         with tempfile.TemporaryDirectory() as tempdir:
#             gta = GenerateThumbnailsArguments(
#                 scan_id=scan_id,
#                 rpd_files=self.rpd_files,
#                 name='test',
#                 cache_dirs=CacheDirs(tempdir, tempdir))
#             self.thread = QThread()
#             self.ttm = TestThumbnailManager(profile)
#             self.ttm.moveToThread(self.thread)
#             self.thread.started.connect(self.ttm.run_sink)
#
#             self.ttm.message.connect(self.thumbnailReceived)
#             self.ttm.workerFinished.connect(self.finished)
#             QTimer.singleShot(0, self.thread.start)
#             worker_id = self.ttm.get_worker_id()
#             self.ttm.start_worker(worker_id, gta)
#
#     def thumbnailReceived(self, rpd_file: RPDFile, thumbnail: QPixmap) -> None:
#         self.insertPlainText('{}\n'.format(rpd_file.full_file_name))
#         self.received += 1
#
#     def finished(self):
#         assert self.received == len(self.rpd_files)
#         print("Test finsihed successfully")
#         QTimer.singleShot(0, self.close)
#
#     def sizeHint(self):
#         return QSize(800, 900)
#
#
#     def closeEvent(self, QCloseEvent):
#         self.thread.quit()
#         if not self.thread.wait(1000):
#             self.ttm.forcefully_terminate()
#
#
# if __name__ == '__main__':
#     parser = argparse.ArgumentParser()
#     parser.add_argument('-d', '--data', dest='data', type=str)
#     parser.add_argument('-p', '--profile', dest='profile', action="store_true")
#     parser.add_argument("--reset", action="store_true", dest="reset",
#                  help="reset all thumbnail caches and exit")
#     args = parser.parse_args()
#     if args.reset:
#         cache = ThumbnailCacheSql()
#         cache.purge_cache()
#         print("Thumbnail cache reset")
#         cache = os.path.join(BaseDirectory.xdg_cache_home, 'thumbnails')
#         folders = [os.path.join(cache, subdir) for subdir in ('normal', 'large')]
#         i = 0
#         for folder in folders:
#             for the_file in os.listdir(folder):
#                 file_path = os.path.join(folder, the_file)
#                 try:
#                     if os.path.isfile(file_path):
#                         i += 1
#                         os.remove(file_path)
#                 except OSError as e:
#                     print(e)
#         print('Removed {} XDG thumbnails'.format(i))
#
#     if args.data is None:
#         testdata = 'thumbnail_data_small'
#     else:
#         testdata = args.data
#
#     app = QApplication(sys.argv)
#     tt = TestThumbnail(testdata, args.profile)
#     tt.show()
#
#     app.setActiveWindow(tt)
#     sys.exit(app.exec_())