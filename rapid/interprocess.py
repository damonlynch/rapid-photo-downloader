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

from psutil import (Process, wait_procs, pid_exists)
from PyQt5.QtCore import (pyqtSignal, QObject)

import zmq

from rpdfile import RPDFile
from devices import Device
from preferences import ScanPreferences

logging_level = logging.DEBUG
logging.basicConfig(format='%(levelname)s:%(asctime)s:%(message)s',
                    datefmt='%H:%M:%S',
                    level=logging_level)


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

class PullPipelineManager(QObject):
    """
    Base class from which more specialized 0MQ classes are derived.

    Receives data into ts sink via a ZMQ PULL socket, but does not
    specify how workers should be sent data.

    Sends Signals using Qt.
    """

    message = pyqtSignal(str) # Derived class will change this
    workerFinished = pyqtSignal(int)
    def __init__(self, context: zmq.Context):
        super(PullPipelineManager, self).__init__()

        # Sink socket to receive results of the workers
        self.receiver_socket = context.socket(zmq.PULL)
        self.receiver_port = self.receiver_socket.bind_to_random_port(
            "tcp://*")

        # Socket to communicate directly with the sink, bypassing the workers
        self.terminate_socket = context.socket(zmq.PUSH)
        self.terminate_socket.connect("tcp://localhost:{}".format(
            self.receiver_port))

        # Monitor which workers we have running
        self.workers = [] # type list[int]

        self.processes = {}

        self.terminating = False

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
                del self.processes[worker_id]
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

    def terminate_sink(self):
        self.terminate_socket.send_multipart([b'0', b'cmd', b'KILL'])

    def worker_finished(worker_id):
        pass

    def forcefully_terminate(self):
        """
        Forcefully terminate any running child processes, and then
        shut down the sink.
        """

        def on_terminate(proc: Process):
            logging.debug("Process %s (%s) terminated", proc.name(), proc.pid)

        terminated = []
        for proc in self.processes.values():
            if pid_exists(proc.pid):
                try:
                    p = Process(proc.pid)
                except:
                    p = None
                if p is not None and p == proc:
                    logging.debug("Process %s (%s) has %s status",
                                  p.name(), p.pid, p.status())
                    try:
                        p.terminate()
                        terminated.append(p)
                    except:
                        logging.error("Terminating process %s with "
                                  "pid %s failed", p.name(), p.pid)
        if terminated:
            gone, alive = wait_procs(terminated, timeout=2,
                                     callback=on_terminate)
            for p in alive:
                logging.debug("Killing process %s", p)
                try:
                    p.kill()
                except:
                    logging.debug("Failed to kill process %s with pid %s",
                                  p.name(), p.pid)

        self.terminate_sink()

    def process_alive(self, worker_id: int) -> bool:
        """
        Process IDs are reused by the system. Check to make sure
        a new process has not been created with the same process id.

        :param worker_id: the process to check
        :return True if the process is the same, False otherwise
        """
        if pid_exists(self.processes[worker_id].pid):
            return Process(self.processes[worker_id].pid) \
                              == self.processes[worker_id]
        return False


DAEMON_WORKER_ID = 0

class PushPullDaemonManager(PullPipelineManager):

    def __init__(self, context: zmq.Context):
        super(PushPullDaemonManager, self).__init__(context)

        # Ventilator socket to send message to worker
        self.ventilator_socket = context.socket(zmq.PUSH)
        self.ventilator_port = self.ventilator_socket.bind_to_random_port(
            'tcp://*')

    def stop(self):
        """
        Permanently stop the daemon process and terminate
        """
        logging.debug("{} halting".format(self._process_name))
        self.terminating = True

        # Only send stop command if the process is still running
        if self.process_alive(DAEMON_WORKER_ID):
            try:
                self.ventilator_socket.send_multipart([b'cmd', b'STOP'],
                                                  zmq.DONTWAIT)
            except zmq.Again:
                logging.debug(
                    "Terminating %s sink because child process did not "
                    "receive message",
                    self._process_name)
                self.terminate_sink()
        else:
            # The process may have crashed. Stop the sink.
            self.terminate_sink()

    def start(self):
        cmd = os.path.join(os.path.dirname(__file__), self._process_to_run)
        command_line = '{} --receive {} --send {} --logginglevel {}'.format(
                        cmd,
                        self.ventilator_port,
                        self.receiver_port,
                        logging_level)

        args = shlex.split(command_line)

        # run command immediately, without waiting a reply
        pid = subprocess.Popen(args).pid
        # logging.debug("Started '%s' with pid %s", command_line, pid)

        # Add to list of running workers
        self.workers.append(DAEMON_WORKER_ID)
        self.processes[DAEMON_WORKER_ID] = Process(pid)

class PublishPullPipelineManager(PullPipelineManager):
    """
    Set of standard operations when managing a 0MQ Pipeline that
    distributes work with a publisher to one or more workers, and pulls
    results from the workers into a sink.

    Worker counterpart is interprocess.WorkerInPublishPullPipeline
    """

    def __init__(self, context: zmq.Context):
        super(PublishPullPipelineManager, self).__init__(context)

        # Ventilator socket to send messages to workers on
        self.publisher_socket = context.socket(zmq.PUB)
        self.publisher_port= self.publisher_socket.bind_to_random_port(
            'tcp://*')

        # Socket to synchronize the start of each worker
        self.sync_service_socket = context.socket(zmq.REP)
        self.sync_service_port = \
            self.sync_service_socket.bind_to_random_port("tcp://*")

        # Socket for worker control: pause, resume, stop
        self.controller_socket = context.socket(zmq.PUB)
        self.controller_port = self.controller_socket.bind_to_random_port(
            "tcp://*")

    def stop(self):
        """
        Permanently stop all the workers and terminate
        """
        # TODO: exit when a worker has crashed
        logging.debug("{} halting".format(self._process_name))
        self.terminating = True
        if self.workers:
            # Signal workers they must immediately stop
            termination_signal_sent = False
            alive_workers = [worker_id for worker_id in self.workers if
                             self.process_alive(worker_id)]
            for worker_id in alive_workers:
                message = [make_filter_from_worker_id(worker_id),b'STOP']
                try:
                    self.controller_socket.send_multipart(message,
                                                          zmq.DONTWAIT)
                    termination_signal_sent = True
                except zmq.Again:
                    pass

            if not termination_signal_sent:
                self.terminate_sink()
        else:
            self.terminate_sink()

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
        self.processes[worker_id] = Process(pid)

        # Send START commands until scan worker indicates it is ready to
        # receive data
        # Worker ID must be in bytes format
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


class WorkerProcess():
    def __init__(self, worker_type):
        logging.debug("{} worker started".format(worker_type))
        self.parser = argparse.ArgumentParser()
        self.parser.add_argument("--receive", required=True)
        self.parser.add_argument("--send", required=True)
        self.parser.add_argument("--logginglevel", required=True)

    def cleanup_pre_stop(self):
        """
        Implement in child class if needed. Operations to run if
        process is stopped.
        """
        pass


    def send_message_to_sink(self):

        self.sender.send_multipart([self.worker_id, b'data',
                                    self.content])


class DaemonProcess(WorkerProcess):
    """
    Single instance
    """
    def __init__(self, worker_type):
        super(DaemonProcess, self).__init__(worker_type)

        args = self.parser.parse_args()

        context = zmq.Context()
        # Socket to send messages along the pipe to
        self.sender = context.socket(zmq.PUSH)
        self.sender.set_hwm(10)
        self.sender.connect("tcp://localhost:{}".format(args.send))

        self.receiver = context.socket(zmq.PULL)
        self.receiver.connect("tcp://localhost:{}".format(args.receive))

        self.run()

    def run(self):
        pass

    def check_for_command(self, directive, content):
        if directive == b'cmd':
            assert content == b'STOP'
            self.cleanup_pre_stop()
            # signal to sink that we've terminated
            self.sender.send_multipart([DAEMON_WORKER_ID, b'cmd',
                                        b'STOPPED'])
            sys.exit(0)


    def send_message_to_sink(self):
        # Must use a dummy value for the worker id, as there is only ever one
        # instance.
        self.sender.send_multipart([DAEMON_WORKER_ID, b'data',
                                    self.content])


class WorkerInPublishPullPipeline(WorkerProcess):

    def __init__(self, worker_type):
        super(WorkerInPublishPullPipeline, self).__init__(worker_type)
        self.parser.add_argument("--controller", required=True)
        self.parser.add_argument("--syncclient", required=True)
        self.parser.add_argument("--filter", required=True)
        args = self.parser.parse_args()

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
        assert directive == b'cmd'
        assert content == b'START'

        # send a synchronization request
        sync_client.send(b'')

        # wait for synchronization reply
        sync_client.recv()

        # Receive next "START" message and discard, looking for data message
        while True:
            worker_id, directive, content = receiver.recv_multipart()
            if directive == b'data':
                break
            else:
                assert directive == b'cmd'
                assert content == b'START'

        self.content = content
        self.do_work()


    def check_for_command(self):
        try:
            # Don't block if process is running regularly
            # If there is no command,exception will occur
            worker_id, command = self.controller.recv_multipart(zmq.DONTWAIT)
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
            pass # Continue working

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
    def  __init__(self, scan_id: int,
                  device: Device,
                  photo_download_folder: str,
                  video_download_folder: str,
                  files,
                  verify_file: bool,
                  generate_thumbnails: bool,
                  thumbnail_quality_lower: bool):
        """
        :param files: List(rpd_file)
        """
        self.scan_id = scan_id
        self.device = device
        self.photo_download_folder = photo_download_folder
        self.video_download_folder = video_download_folder
        self.files = files
        self.generate_thumbnails = generate_thumbnails
        self.thumbnail_quality_lower = thumbnail_quality_lower
        self.verify_file = verify_file

class CopyFilesResults:
    """
    Receive results from the copyfiles process
    """
    def __init__(self, scan_id=None, photo_temp_dir=None, video_temp_dir=None,
                 total_downloaded=None, chunk_downloaded=None,
                 copy_succeeded=None, rpd_file=None,
                 download_count=None, png_data=None):
        self.scan_id = scan_id

        self.photo_temp_dir = photo_temp_dir
        self.video_temp_dir = video_temp_dir

        self.total_downloaded = total_downloaded
        self.chunk_downloaded = chunk_downloaded

        self.copy_succeeded = copy_succeeded
        self.rpd_file = rpd_file
        self.download_count = download_count
        self.png_data = png_data

class RenameAndMoveFileData:
    """
    Pass arguments to the renameandmovefile process
    """
    def __init__(self, rpd_file: RPDFile, download_count: int,
                 download_succeeded: bool):
        self.rpd_file = rpd_file
        self.download_count = download_count
        self.download_succeeded = download_succeeded


class RenameAndMoveFileResults:
    def __init__(self, move_succeeded: bool, rpd_file: RPDFile,
                 download_count: int):
        self.move_succeeded = move_succeeded
        self.rpd_file = rpd_file
        self.download_count = download_count


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
