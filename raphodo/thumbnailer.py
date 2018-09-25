# Copyright (C) 2015-2017 Damon Lynch <damonlynch@gmail.com>

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
__copyright__ = "Copyright 2015-2017, Damon Lynch"

import pickle
from typing import Optional
import logging

import zmq
from PyQt5.QtCore import (QThread, QTimer, pyqtSignal, pyqtBoundSignal, pyqtSlot, QObject)
from PyQt5.QtGui import (QPixmap, QImage)

from raphodo.interprocess import (LoadBalancerManager, PublishPullPipelineManager,
                                  GenerateThumbnailsArguments, GenerateThumbnailsResults,
                                  ThreadNames, create_inproc_msg)
from raphodo.rpdfile import RPDFile
from raphodo.utilities import CacheDirs


class ThumbnailManagerPara(PublishPullPipelineManager):
    """
    Manages thumbnailing using processes that run in parallel,
    one for each device. Not to be confused with
    ThumbnailDaemonManager, which manages the daemon process
    that extracts thumbnails after the file has already been
    downloaded and that writes FreeDesktop.org thumbnails.
    """

    message = pyqtSignal(RPDFile, QPixmap)
    cacheDirs = pyqtSignal(int, CacheDirs)

    def __init__(self, logging_port: int, thread_name: str) -> None:
        super().__init__(logging_port=logging_port, thread_name=thread_name)
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
                 logging_port: int) -> None:
        super().__init__(context, no_workers, sink_port, logging_port, ThreadNames.load_balancer)
        self._process_name = 'Thumbnail Load Balancer Manager'
        self._process_to_run = 'thumbloadbalancer.py'


class Thumbnailer(QObject):
    """
    Extracts, caches and retrieves thumbnails for a set of files.

    For each set of files, a process runs to extract the files from
    their source. Each file is then processed, if necessary using
    worker processes fronted by a load balancer.
    """

    frontend_port = pyqtSignal(int)
    # See also the four other signals below

    def __init__(self, parent,
                 no_workers: int,
                 logging_port: int,
                 log_gphoto2: bool) -> None:
        """
        :param parent: Qt parent window
        :param no_workers: how many thumbnail extractor processes to
         use
        :param logging_port: 0MQ port to use for logging control
        :param log_gphoto2: if True, log libgphoto2 logging message
        """
        super().__init__(parent)
        self.context = zmq.Context.instance()
        self.log_gphoto2 = log_gphoto2
        self._frontend_port = None  # type: int
        self.no_workers = no_workers
        self.logging_port = logging_port

        inproc = "inproc://{}"
        self.thumbnailer_controller = self.context.socket(zmq.PAIR)
        self.thumbnailer_controller.bind(inproc.format(ThreadNames.thumbnailer))
        self.load_balancer_controller = self.context.socket(zmq.PAIR)
        self.load_balancer_controller.bind(inproc.format(ThreadNames.load_balancer))

        self.setupThumbnailManager()

    def generateThumbnails(self, scan_id: int,
                           rpd_files: list,
                           name: str,
                           proximity_seconds: int,
                           cache_dirs: CacheDirs,
                           need_photo_cache_dir: bool,
                           need_video_cache_dir: bool,
                           camera_model: Optional[str]==None,
                           camera_port: Optional[str]=None,
                           entire_video_required: Optional[bool]=None,
                           entire_photo_required: Optional[bool] = None) -> None:
        """
        Initiates thumbnail generation.

        :param scan_id: worker id of the scan
        :param rpd_files: list of rpd_files, all of which should be
         from the same source
        :param name: name of the device
        :param proximity_seconds: the time elapsed between consecutive
         shots that is used to prioritize the order of thumbnail
         generation
        :param cache_dirs: the location where the cache directories
         should be created
        :param need_photo_cache_dir: if True, must use cache dir
         to extract photo thumbnail
        :param need_video_cache_dir: if True, must use cache dir
         to extract video thumbnail
        :param camera_model: If the thumbnails are being downloaded
         from a camera, this is the name of the camera, else None
        :param camera_port: If the thumbnails are being downloaded
         from a camera, this is the port of the camera, else None,
        :param entire_video_required: if the entire video is required
         to extract the thumbnail
        :param entire_photo_required: if the entire photo is required
         to extract the thumbnail
         """
        self.thumbnailer_controller.send_multipart(
            create_inproc_msg(
                b'START_WORKER',
                worker_id=scan_id,
                data=GenerateThumbnailsArguments(
                    scan_id=scan_id,
                    rpd_files=rpd_files,
                    name=name,
                    proximity_seconds=proximity_seconds,
                    cache_dirs=cache_dirs,
                    need_photo_cache_dir=need_photo_cache_dir,
                    need_video_cache_dir=need_video_cache_dir,
                    frontend_port=self._frontend_port,
                    log_gphoto2=self.log_gphoto2,
                    camera=camera_model,
                    port=camera_port,
                    entire_video_required=entire_video_required,
                    entire_photo_required=entire_photo_required
                )
            )
        )

    @property
    def thumbnailReceived(self) -> pyqtBoundSignal:
        return self.thumbnail_manager.message

    @property
    def cacheDirs(self) -> pyqtBoundSignal:
        return self.thumbnail_manager.cacheDirs

    # Signal emitted when the worker has been forcefully stopped, rather than
    # merely finished in its work
    @property
    def workerStopped(self) -> pyqtSignal:
        return self.thumbnail_manager.workerStopped

    @property
    def workerFinished(self) -> pyqtSignal:
        return self.thumbnail_manager.workerFinished

    def setupThumbnailManager(self) -> None:
        logging.debug("Starting thumbnail model...")

        self.thumbnail_manager_thread = QThread()
        self.thumbnail_manager = ThumbnailManagerPara(
            logging_port=self.logging_port, thread_name=ThreadNames.thumbnailer
        )
        self.thumbnail_manager.moveToThread(self.thumbnail_manager_thread)
        self.thumbnail_manager_thread.started.connect(self.thumbnail_manager.run_sink)
        self.thumbnail_manager.receiverPortSignal.connect(self.managerReceiverPort)
        self.thumbnail_manager.sinkStarted.connect(self.thumbnailManagerSinkStarted)

        QTimer.singleShot(0, self.thumbnail_manager_thread.start)

    @pyqtSlot(int)
    def managerReceiverPort(self, port: int) -> None:
        self.thumbnail_manager_sink_port = port

    @pyqtSlot()
    def thumbnailManagerSinkStarted(self) -> None:
        logging.debug("...thumbnail model started")

        self.setupLoadBalancer()

    def setupLoadBalancer(self) -> None:
        logging.debug("Starting thumbnail load balancer...")
        self.load_balancer_thread = QThread()
        self.load_balancer = ThumbnailLoadBalancerManager(
            self.context, self.no_workers, self.thumbnail_manager_sink_port, self.logging_port
        )
        self.load_balancer.moveToThread(self.load_balancer_thread)
        self.load_balancer_thread.started.connect(self.load_balancer.start_load_balancer)

        self.load_balancer.load_balancer_started.connect(self.loadBalancerFrontendPort)
        QTimer.singleShot(0, self.load_balancer_thread.start)

    @pyqtSlot(int)
    def loadBalancerFrontendPort(self, frontend_port: int) -> None:
        logging.debug("...thumbnail load balancer started")
        self._frontend_port = frontend_port
        self.frontend_port.emit(frontend_port)

    def stop(self) -> None:

        self.thumbnailer_controller.send_multipart(create_inproc_msg(b'STOP'))
        self.load_balancer_controller.send_multipart(create_inproc_msg(b'STOP'))
        self.thumbnail_manager_thread.quit()
        if not self.thumbnail_manager_thread.wait(1000):
            self.thumbnailer_controller.send_multipart(create_inproc_msg(b'TERMINATE'))
        self.load_balancer_thread.quit()
        if not self.load_balancer_thread.wait(1000):
            self.load_balancer_controller.send_multipart(create_inproc_msg(b'TERMINATE'))

    def stop_worker(self, scan_id: int) -> None:
        self.thumbnailer_controller.send_multipart(
            create_inproc_msg(b'STOP_WORKER', worker_id=scan_id)
        )



