# Copyright (C) 2015-2016 Damon Lynch <damonlynch@gmail.com>

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

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2015-2016, Damon Lynch"

import pickle
from typing import Optional
import zmq
from PyQt5.QtCore import (QThread, QTimer, pyqtSignal, pyqtSlot, QObject)
from PyQt5.QtGui import (QPixmap, QImage)

from raphodo.interprocess import (LoadBalancerManager, PublishPullPipelineManager,
                          GenerateThumbnailsArguments, GenerateThumbnailsResults)
from raphodo.rpdfile import RPDFile
from raphodo.utilities import CacheDirs


class ThumbnailManagerPara(PublishPullPipelineManager):
    message = pyqtSignal(RPDFile, QPixmap)
    cacheDirs = pyqtSignal(int, CacheDirs)
    def __init__(self, context: zmq.Context, logging_level: int) -> None:
        super().__init__(context, logging_level)
        self._process_name = 'Thumbnail Manager'
        self._process_to_run = 'thumbnailpara.py'
        self._worker_id = 0

    def process_sink_data(self) -> None:
        data = pickle.loads(self.content) # type: GenerateThumbnailsResults
        if data.rpd_file is not None:
            if data.thumbnail_bytes is None:
                thumbnail = QPixmap()
            else:
                thumbnail = QImage.fromData(data.thumbnail_bytes)
                if thumbnail.isNull():
                    thumbnail = QPixmap()
                else:
                    thumbnail = QPixmap.fromImage(thumbnail)
            self.message.emit(data.rpd_file, thumbnail)
        else:
            assert data.cache_dirs is not None
            self.cacheDirs.emit(data.scan_id, data.cache_dirs)

class ThumbnailLoadBalancerManager(LoadBalancerManager):
    def __init__(self, context: zmq.Context,
                 no_workers: int,
                 sink_port: int,
                 logging_level: int) -> None:
        super().__init__(context, no_workers, sink_port, logging_level)
        self._process_name = 'Thumbnail Load Balancer Manager'
        self._process_to_run = 'thumbloadbalancer.py'

class Thumbnailer(QObject):
    """
    Extracts, caches and retrieves thumbnails for a set of files.

    For each set of files, a process runs to extract the files from
    their source. Each file is then processed, if necessary using
    worker processes fronted by a load balancer.

    Emits two signals: one to indicate it's ready, and another to
    indicate a thumbnail has been generated.
    """

    ready = pyqtSignal()
    # See also the thumbnailReceived and cacheDirs signal below

    def __init__(self, parent, no_workers: int, logging_level: int) -> None:
        """
        :param parent: Qt parent window
        :param no_workers: how many thumbnail extractor processes to
         use
        """
        super().__init__(parent)
        self.logging_level = logging_level
        self.context = zmq.Context.instance()
        self.setupThumbnailManager()
        self.setupLoadBalancer(no_workers)

    def generateThumbnails(self, scan_id: int,
                           rpd_files: list,
                           name: str,
                           cache_dirs: CacheDirs,
                           camera_model: Optional[str]==None,
                           camera_port: Optional[str]=None) -> None:
        """
        Initiates thumbnail generation.

        :param scan_id: worker id of the scan
        :param rpd_files: list of rpd_files, all of which should be
         from the same source
        :param name: name of the device
        :param cache_dirs: the location where the cache directories
         should be created
        :param camera_model: If the thumbnails are being downloaded
         from a camera, this is the name of the camera, else None
        :param camera_port: If the thumbnails are being downloaded
         from a camera, this is the port of the camera, else None
        """
        self.thumbnail_manager.start_worker(scan_id,
                        GenerateThumbnailsArguments(
                            scan_id=scan_id, rpd_files=rpd_files,
                            name=name, cache_dirs=cache_dirs,
                            frontend_port=self.frontend_port,
                            camera=camera_model,
                            port=camera_port))

    @property
    def thumbnailReceived(self) -> pyqtSignal:
        return self.thumbnail_manager.message

    @property
    def cacheDirs(self) -> pyqtSignal:
        return self.thumbnail_manager.cacheDirs

    def setupThumbnailManager(self) -> None:
        self.thumbnail_manager_thread = QThread()
        self.thumbnail_manager = ThumbnailManagerPara(self.context, self.logging_level)
        self.thumbnail_manager_sink_port = self.thumbnail_manager.receiver_port
        self.thumbnail_manager.moveToThread(self.thumbnail_manager_thread)
        self.thumbnail_manager_thread.started.connect(self.thumbnail_manager.run_sink)

        QTimer.singleShot(0, self.thumbnail_manager_thread.start)

    def setupLoadBalancer(self, no_workers: int) -> None:
        self.load_balancer_thread =  QThread()
        self.load_balancer = ThumbnailLoadBalancerManager(self.context, no_workers,
                          self.thumbnail_manager_sink_port, self.logging_level)
        self.load_balancer.moveToThread(self.load_balancer_thread)
        self.load_balancer_thread.started.connect(self.load_balancer.start_load_balancer)

        self.load_balancer.load_balancer_started.connect(self.loadBalancerFrontendPort)
        QTimer.singleShot(0, self.load_balancer_thread.start)

    @pyqtSlot(int)
    def loadBalancerFrontendPort(self, frontend_port: int) -> None:
        self.frontend_port = frontend_port
        self.ready.emit()

    def stop(self) -> None:
        self.thumbnail_manager.stop()
        self.load_balancer.stop()
        self.thumbnail_manager_thread.quit()
        if not self.thumbnail_manager_thread.wait(1000):
            self.thumbnail_manager.forcefully_terminate()
        self.load_balancer_thread.quit()
        if not self.load_balancer_thread.wait(1000):
            self.load_balancer.forcefully_terminate()

