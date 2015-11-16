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
import shutil
import pickle
import tempfile
import argparse

from PyQt5.QtCore import (QThread, Qt, QTimer, pyqtSignal, QSize, QObject)
from PyQt5.QtWidgets import (QApplication, QTextEdit)
from PyQt5.QtGui import (QPixmap, QImage)
import zmq
from xdg import BaseDirectory

from utilities import CacheDirs

from interprocess import (LoadBalancerManager, PublishPullPipelineManager,
                          GenerateThumbnailsArguments, GenerateThumbnailsParaResults)

from rpdfile import RPDFile
from cache import ThumbnailCache

class ThumbnailManagerPara(PublishPullPipelineManager):
    message = pyqtSignal(RPDFile)
    cacheDirs = pyqtSignal(int, CacheDirs)
    def __init__(self, context: zmq.Context) -> None:
        super().__init__(context)
        self._process_name = 'Thumbnail Manager'
        self._process_to_run = 'thumbnailpara.py'
        self._worker_id = 0

    def process_sink_data(self) -> None:
        data = pickle.loads(self.content) # type: GenerateThumbnailsParaResults
        if data.rpd_file is not None:
            # thumbnail = QImage.fromData(data.png_data)
            # thumbnail = QPixmap.fromImage(thumbnail)
            self.message.emit(data.rpd_file)
        # else:
        #     assert data.cache_dirs is not None
        #     self.cacheDirs.emit(data.scan_id, data.cache_dirs)

class ThumbnailLoadBalancerManager(LoadBalancerManager):
    def __init__(self, context: zmq.Context, no_workers: int, sink_port: int) -> None:
        super().__init__(context, no_workers, sink_port)
        self._process_name = 'Thumbnail Load Balancer Manager'
        self._process_to_run = 'thumbloadbalancer.py'

class Thumbnailer(QObject):
    """
    Extracts, caches and retrieves thumbnails for a set of files.

    For each set of files, a process runs to extract the files from
    their source. Each file is then processed, if necessary using
    worker processes fronted by a load balancer.
    """
    ready = pyqtSignal()
    def __init__(self, parent, no_workers: int) -> None:
        """
        :param parent: Qt parent window
        :param no_workers: how many thumbnail extractor processes to
         use
        """
        super().__init__(parent)
        self.context = zmq.Context.instance()
        self.setupThumbnailManager()
        self.setupLoadBalancer(no_workers)

    def generateThumbnails(self, scan_id: int, rpd_files: list, cache_dirs: CacheDirs) -> None:
        """
        Initiates thumbnail generation.

        :param scan_id: worker id of the scan
        :param rpd_files: list of rpd_files, all of which should be
         from the same source
        :param cache_dirs: the location where the cache directories
         should be created
        """
        self.thumbnail_manager.start_worker(scan_id,
                        GenerateThumbnailsArguments(scan_id, rpd_files, False, 'test', cache_dirs,
                                        self.frontend_port))

    @property
    def thumbnailReceived(self) -> pyqtSignal:
        return self.thumbnail_manager.message

    def setupThumbnailManager(self) -> None:
        self.thumbnail_manager_thread = QThread()
        self.thumbnail_manager = ThumbnailManagerPara(self.context)
        self.thumbnail_manager_sink_port = self.thumbnail_manager.receiver_port
        self.thumbnail_manager.moveToThread(self.thumbnail_manager_thread)
        self.thumbnail_manager_thread.started.connect(self.thumbnail_manager.run_sink)

        QTimer.singleShot(0, self.thumbnail_manager_thread.start)

    def setupLoadBalancer(self, no_workers: int) -> None:
        self.load_balancer_thread =  QThread()
        self.load_balancer = ThumbnailLoadBalancerManager(self.context, no_workers,
                                                          self.thumbnail_manager_sink_port)
        self.load_balancer.moveToThread(self.load_balancer_thread)
        self.load_balancer_thread.started.connect(self.load_balancer.start_load_balancer)

        self.load_balancer.load_balancer_started.connect(self.loadBalancerFrontendPort)
        QTimer.singleShot(0, self.load_balancer_thread.start)

    def loadBalancerFrontendPort(self, frontend_port: int):
        self.frontend_port = frontend_port
        self.ready.emit()

    def stop(self):
        self.thumbnail_manager.stop()
        self.load_balancer.stop()
        self.thumbnail_manager_thread.quit()
        if not self.thumbnail_manager_thread.wait(1000):
            self.thumbnail_manager.forcefully_terminate()
        self.load_balancer_thread.quit()
        if not self.load_balancer_thread.wait(1000):
            self.load_balancer.forcefully_terminate()


class TestThumbnail(QTextEdit):
    def __init__(self, testdata: str, profile: bool, no_workers: int, parent=None) -> None:
        super().__init__(parent)

        self.received = 0

        with open(testdata, 'rb') as td:
            self.rpd_files = pickle.load(td)

        self.thumbnailer = Thumbnailer(self, no_workers)
        self.thumbnailer.ready.connect(self.startGeneration)
        self.thumbnailer.thumbnailReceived.connect(self.thumbnailReceived)

    def startGeneration(self):
        print("Starting generation of {} thumbnails....".format(len(self.rpd_files)))
        with tempfile.TemporaryDirectory() as tempdir:
            cache_dirs = CacheDirs(tempdir, tempdir)
            self.thumbnailer.generateThumbnails(0, self.rpd_files, cache_dirs)

    def thumbnailReceived(self, rpd_file: RPDFile) -> None:
        self.received += 1
        # self.insertPlainText('{}\n'.format(rpd_file.full_file_name))

    def sizeHint(self):
        return QSize(800, 900)


    def closeEvent(self, QCloseEvent):
        assert self.received == len(self.rpd_files)
        self.thumbnailer.stop()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--data', dest='data', type=str)
    parser.add_argument('-p', '--profile', dest='profile', action="store_true")
    parser.add_argument("--reset", action="store_true", dest="reset",
                 help="reset all thumbnail caches and exit")
    args = parser.parse_args()
    if args.reset:
        cache = ThumbnailCache()
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

    if args.data is None:
        testdata = 'thumbnail_data_small'
    else:
        testdata = args.data

    no_workers = 4
    app = QApplication(sys.argv)
    tt = TestThumbnail(testdata, args.profile, no_workers)
    tt.show()

    app.setActiveWindow(tt)
    sys.exit(app.exec_())



