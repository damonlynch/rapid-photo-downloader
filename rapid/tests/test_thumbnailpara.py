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

from PyQt5.QtCore import (QThread, Qt, QTimer, pyqtSignal, QSize)
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


class TestThumbnail(QTextEdit ):
    def __init__(self, testdata: str, profile: bool, no_workers: int, parent=None) -> None:
        super().__init__(parent)

        self.context = zmq.Context()
        self.scan_id = 0
        self.received = 0

        with open(testdata, 'rb') as td:
            self.rpd_files = pickle.load(td)

        with tempfile.TemporaryDirectory() as tempdir:
            self.tempdir = tempdir
            self.setupThumbnailManager()
            self.setupLoadBalancer(no_workers)

    def setupThumbnailManager(self):

        self.ttm_thread = QThread()
        self.ttm = ThumbnailManagerPara(self.context)
        self.ttm_receiver_port = self.ttm.receiver_port
        self.ttm.moveToThread(self.ttm_thread)
        self.ttm_thread.started.connect(self.ttm.run_sink)

        self.ttm.message.connect(self.thumbnailReceived)
        self.ttm.workerFinished.connect(self.finished)
        QTimer.singleShot(0, self.ttm_thread.start)


    def setupLoadBalancer(self, no_workers: int):
        self.lb_thread =  QThread()
        self.lb = ThumbnailLoadBalancerManager(self.context, no_workers, self.ttm_receiver_port)
        self.lb.moveToThread(self.lb_thread)
        self.lb_thread.started.connect(self.lb.start_load_balancer)

        self.lb.load_balancer_started.connect(self.loadBalancerFrontendPort)
        QTimer.singleShot(0, self.lb_thread.start)

    def loadBalancerFrontendPort(self, frontend_port: int):
        print("Received frontend port {}, now starting worker...".format(frontend_port))
        gta = GenerateThumbnailsArguments(self.scan_id, self.rpd_files, False, 'test',
                                          CacheDirs(self.tempdir, self.tempdir), frontend_port)
        self.ttm.start_worker(self.scan_id, gta)

    def thumbnailReceived(self, rpd_file: RPDFile) -> None:
        self.received += 1
        self.insertPlainText('{}\n'.format(rpd_file.full_file_name))

    def finished(self):
        pass
        # QTimer.singleShot(0, self.close)

    def sizeHint(self):
        return QSize(800, 900)


    def closeEvent(self, QCloseEvent):
        assert self.received == len(self.rpd_files)
        self.ttm.stop()
        self.lb.stop()
        self.ttm_thread.quit()
        if not self.ttm_thread.wait(1000):
            self.ttm.forcefully_terminate()
        self.lb_thread.quit()
        if not self.lb_thread.wait(1000):
            self.lb.forcefully_terminate()


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



