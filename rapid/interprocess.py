__author__ = 'Damon Lynch'

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

import argparse
import sys
import logging
import pickle
import os
import subprocess
import shlex
import time

from PyQt5.QtCore import (pyqtSignal, QObject)

import zmq

from rpdfile import RPDFile
from devices import Device
from preferences import ScanPreferences

logging_level = logging.DEBUG
logging.basicConfig(format='%(levelname)s:%(asctime)s:%(message)s',
                    datefmt='%H:%M:%S',
                    level=logging_level)

def is_data_message(directive):
    r"""
    Tests to see if the message is a data message

    >>> is_data_message(b"data")
    True

    >>> is_data_message("data")
    False

    >>> is_data_message(b"cmd")
    False
    """
    return directive == b'data'

def is_cmd_message(directive):
    r"""
    Tests to see if the message is a command message

    >>> is_cmd_message(b"cmd")
    True

    >>> is_cmd_message("cmd")
    False
    """
    return directive == b'cmd'

def make_filter_from_worker_id(worker_id):
    r"""
    Returns a python byte string from an integer or string

    >>> make_filter_from_worker_id(54)
    b'54'

    >>> make_filter_from_worker_id('54')
    b'54'
    """
    if isinstance(worker_id, int):
        return str(worker_id).encode()
    if isinstance(worker_id, str):
        return worker_id.encode()
    raise(TypeError)

class PublishPullPipelineManager(QObject):
    """
    Set of standard operations when managing a 0MQ Pipeline that
    distributes work with a publisher to one or more workers, and pulls
    results from the workers into a sink.

    Sends Signals using Qt.

    Worker counterpart is interprocess.WorkerInPublishPullPipeline
    """

    message = pyqtSignal(str) # Derived class will change this
    workerFinished = pyqtSignal(int)
    def __init__(self, context):
        super(PublishPullPipelineManager, self).__init__()

        # Ventilator socket to send messages to workers on
        self.publisher_socket = context.socket(zmq.PUB)
        self.publisher_port= self.publisher_socket.bind_to_random_port(
            'tcp://*')

        # Sink socket to receive results of the workers
        self.receiver_socket = context.socket(zmq.PULL)
        self.receiver_port = self.receiver_socket.bind_to_random_port(
            "tcp://*")

        # Socket to synchronize the start of each worker
        self.sync_service_socket = context.socket(zmq.REP)
        self.sync_service_port = \
            self.sync_service_socket.bind_to_random_port("tcp://*")

        # Socket to communicate directly with the sink, bypassing the workers
        self.terminate_socket = context.socket(zmq.PUSH)
        self.terminate_socket.connect("tcp://localhost:{}".format(
            self.receiver_port))

        # Socket for worker control: pause, resume, stop
        self.controller_socket = context.socket(zmq.PUB)
        self.controller_port = self.controller_socket.bind_to_random_port(
            "tcp://*")

        self.terminating = False

        # Monitor which workers we have running
        self.workers = [] # type list[int]

    def run_sink(self):
        logging.debug("Running sink for %s", self._process_name)
        while True:
            try:
                # Receive messages from the workers
                # (or the terminate socket)
                worker_id, directive, content = \
                    self.receiver_socket.recv_multipart()
            except KeyboardInterrupt:
                break
            if directive == b'cmd':
                command = content
                assert command in [b"STOPPED", b"FINISHED", b"KILL"]
                if command == b"KILL":
                    # Terminate immediately, without regard for any incoming
                    # messages. This message is only sent from this manager
                    # to itself, using the self.terminate_socket
                    logging.debug("{} is terminating".format(
                        self._process_name))
                    break
                # This worker is done; remove from monitored workers and
                # continue
                worker_id = int(worker_id)
                if command == b"STOPPED":
                    logging.debug("%s worker %s has stopped",
                                  self._process_name, worker_id)
                else:
                    # Worker has finished its work
                    self.workerFinished.emit(worker_id)
                self.workers.remove(worker_id)
                if not self.workers:
                    logging.debug("{} currently has no workers".format(
                        self._process_name))
                if not self.workers and self.terminating:
                    logging.debug("{} is exiting".format(self._process_name))
                    break
            else:
                assert directive == b'data'
                self.content = content
                self.process_sink_data()

    def process_sink_data(self):
        data = pickle.loads(self.content)
        self.message.emit(data)

    def stop(self):
        """
        Permanently stop all the workers and terminate
        """
        # TODO: exit when a worker has crashed
        logging.debug("{} halting".format(self._process_name))
        self.terminating = True
        if self.workers:
            # Signal workers they must immediately stop
            for worker_id in self.workers:
                message = [make_filter_from_worker_id(worker_id),b'STOP']
                self.controller_socket.send_multipart(message)
        else:
            self.terminate_socket.send_multipart([b'0', b'cmd', b'KILL'])

    def stop_worker(self, worker_id: int):
        """
        Permanently stop one worker
        """
        assert worker_id in self.workers
        message = [make_filter_from_worker_id(worker_id),b'STOP']
        self.controller_socket.send_multipart(message)

    def add_worker(self, worker_id: int, process_arguments):
        cmd = os.path.join(os.path.dirname(__file__), self._process_to_run)
        command_line = '{} --receive {} --send {} --controller {} ' \
                       '--syncclient {} --filter {} --logginglevel {}'.format(
                        cmd,
                        self.publisher_port,
                        self.receiver_port,
                        self.controller_port,
                        self.sync_service_port,
                        worker_id,
                        logging_level)

        args = shlex.split(command_line)

        # run command immediately, without waiting a reply
        pid = subprocess.Popen(args).pid
        # logging.debug("Started '%s' with pid %s", command_line, pid)

        # Add to list of running workers
        self.workers.append(worker_id)

        # Send START commands until scan worker indicates it is ready to
        # receive data
        while True:
            self.publisher_socket.send_multipart([str(worker_id).encode(),
                                                  b'cmd', b'START'])
            try:
                # look for synchronization request
                self.sync_service_socket.recv(zmq.DONTWAIT)
                # send synchronization reply
                self.sync_service_socket.send(b'')
                break
            except zmq.Again:
                # Briefly pause sending out START messages
                # There is no point flooding the network
                time.sleep(.01)

        # Send data to process to tell it what to work on
        data = pickle.dumps(process_arguments, pickle.HIGHEST_PROTOCOL)
        message = [make_filter_from_worker_id(worker_id), b'data', data]
        self.publisher_socket.send_multipart(message)

    def worker_finished(worker_id):
        pass

    def pause(self):
        for worker_id in self.workers:
            message = [make_filter_from_worker_id(worker_id),b'PAUSE']
            self.controller_socket.send_multipart(message)

    def resume(self):
        for worker_id in self.workers:
            message = [make_filter_from_worker_id(worker_id),b'RESUME']
            self.controller_socket.send_multipart(message)

    def __len__(self):
        return len(self.workers)

    def __contains__(self, item):
        return item in self.workers


class WorkerInPublishPullPipeline():

    def __init__(self, worker_type):
        logging.debug("{} worker started".format(worker_type))
        parser = argparse.ArgumentParser()
        parser.add_argument("--receive", required=True)
        parser.add_argument("--send", required=True)
        parser.add_argument("--controller", required=True)
        parser.add_argument("--syncclient", required=True)
        parser.add_argument("--filter", required=True)
        parser.add_argument("--logginglevel", required=True)
        args = parser.parse_args()

        subscription_filter = self.worker_id = args.filter.encode()

        context = zmq.Context()
        # Socket to send messages along the pipe to
        self.sender = context.socket(zmq.PUSH)
        self.sender.set_hwm(10)
        self.sender.connect("tcp://localhost:{}".format(args.send))

        # Socket to receive messages from the pipe
        receiver = context.socket(zmq.SUB)
        receiver.connect("tcp://localhost:{}".format(args.receive))
        receiver.setsockopt(zmq.SUBSCRIBE, subscription_filter)

        # Socket for control input: pause, resume, stop
        self.controller = context.socket(zmq.SUB)
        self.controller.connect("tcp://localhost:{}".format(args.controller))
        self.controller.setsockopt(zmq.SUBSCRIBE, subscription_filter)

        # Socket to synchronize the start of receiving data from upstream
        sync_client = context.socket(zmq.REQ)
        sync_client.connect("tcp://localhost:{}".format(args.syncclient))

        # Wait to receive "START" message
        worker_id, directive, content = receiver.recv_multipart()
        assert is_cmd_message(directive)
        assert content == b'START'

        # send a synchronization request
        sync_client.send(b'')

        # wait for synchronization reply
        sync_client.recv()

        # Receive next "START" message and discard, looking for data message
        while True:
            worker_id, directive, content = receiver.recv_multipart()
            if is_data_message(directive):
                break
            else:
                assert is_cmd_message(directive)
                assert content == b'START'

        self.content = content
        self.do_work()


    def check_for_command(self):
        try:
            # Don't block if process is running regularly
            # If there is no command,exception will occur
            data = self.controller.recv_multipart(zmq.DONTWAIT)
            worker_id, command = data
            assert command in [b'PAUSE', b'STOP']
            assert  worker_id == self.worker_id

            if command == b'PAUSE':
                # Because the process is paused, do a blocking read to wait for
                # the next command
                command = self.controller.recv()
                assert (command in [b'RESUME', b'STOP'])
            if command == b'STOP':
                self.cleanup_pre_stop()
                # signal to sink that we've terminated before finishing
                self.sender.send_multipart([self.worker_id, b'cmd',
                                            b'STOPPED'])
                sys.exit(0)
        except zmq.Again:
            pass # Continue scanning

    def cleanup_pre_stop(self):
        """
        Implement in child class if needed. Operations to run if
        process is stopped.
        """
        pass

    def send_message_to_sink(self):

        self.sender.send_multipart([self.worker_id, b'data',
                                    self.content])

    def send_finished_command(self):
        self.sender.send_multipart([self.worker_id, b'cmd', b'FINISHED'])


class ScanArguments:
    """
    Pass arguments to the scan process
    """
    def __init__(self, scan_preferences: ScanPreferences, device: Device):
        self.scan_preferences = scan_preferences
        self.device = device


class CopyFilesArguments:
    """
    Pass arugments to the copyfiles process
    """
    def  __init__(self, device: Device,
                  photo_download_folder: str,
                  video_download_folder: str,
                  files,
                  verify_file: bool,
                  generate_thumbnails: bool,
                  thumbnail_quality_lower: bool):
        """
        :param files: List(rpd_file)
        """
        self.device = device
        self.photo_download_folder = photo_download_folder
        self.video_download_folder = video_download_folder
        self.files = files
        self.generate_thumbnails = generate_thumbnails
        self.thumbnail_quality_lower = thumbnail_quality_lower
        self.verify_file = verify_file

class CopyFilesResult:
    """
    Receive results from the copyfiles process
    """
    def __init__(self):
        pass
        # copy_succeeded
        # rpd_file
        # download_count
        # temp_full_file_name
        # thumbnail_icon, thumbnail


class BackupArguments:
    """
    Pass arguments to the backup process
    """
    pass


class GenerateThumbnailsArguments:
    def __init__(self, scan_id: int, rpd_files, thumbnail_quality_lower: bool,
                 name: str, photo_cache_folder: str,
                 camera=None, port=None):
        """
        List of files for which thumbnails are to be generated.
        All files  are assumed to have the same scan id.
        :param scan_id: id of the scan
        :param rpd_files: list of files from which to extract thumbnails
        :param thumbnail_quality_lower: whether to generate the
         thumbnail high or low quality as it is scaled by Qt
        :param name: name of the device
        :param photo_cache_folder: full path of where the photos will
         downloaded to
        :param camera: If the thumbnails are being downloaded from a
         camera, this is the name of the camera, else None
        :param port: If the thumbnails are being downloaded from a
         camera, this is the port of the camera, else None
        :type rpd_files: List[RPDFile]
        :type camera: str
        :type port: str
        """
        self.rpd_files = rpd_files
        self.scan_id = scan_id
        self.thumbnail_quality_lower = thumbnail_quality_lower
        self.name = name
        self.photo_cache_folder = photo_cache_folder
        if camera is not None:
            assert port is not None
        self.camera = camera
        self.port = port


class GenerateThumbnailsResults:
    def __init__(self, rpd_file=None, png_data=None,
                 scan_id=None, photo_cache_dir=None):
        self.rpd_file = rpd_file
        self.png_data = png_data
        self.scan_id = scan_id
        self.photo_cache_dir = photo_cache_dir
