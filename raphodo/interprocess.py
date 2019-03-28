# Copyright (C) 2015-2019 Damon Lynch <damonlynch@gmail.com>

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
__copyright__ = "Copyright 2015-2019, Damon Lynch"

import argparse
import sys
import logging
import pickle
import os
import shlex
import time
from collections import deque, namedtuple
from typing import Optional, Set, List, Dict, Sequence, Any, Tuple, Union


import psutil

from PyQt5.QtCore import (pyqtSignal, QObject, pyqtSlot)
from PyQt5.QtGui import (QPixmap, QImage)

import zmq
import zmq.log.handlers
if zmq.pyzmq_version_info()[0] < 17:
    from zmq.eventloop import ioloop
else:
    try:
        from tornado import ioloop
    except ImportError:
        from zmq.eventloop import ioloop  # note: deprecated in pyzmq 17.0.0

from zmq.eventloop.zmqstream import ZMQStream

from raphodo.rpdfile import RPDFile, FileTypeCounter, FileSizeSum, Photo, Video
from raphodo.devices import Device
from raphodo.utilities import CacheDirs, set_pdeathsig
from raphodo.constants import (
    RenameAndMoveStatus, ExtractionTask, ExtractionProcessing, CameraErrorCode, FileType,
    FileExtension, BackupStatus
)
from raphodo.proximity import TemporalProximityGroups
from raphodo.storage import StorageSpace
from raphodo.iplogging import ZeroMQSocketHandler
from raphodo.viewutils import ThumbnailDataForProximity
from raphodo.folderspreview import DownloadDestination, FoldersPreview
from raphodo.problemnotification import (
    ScanProblems, CopyingProblems, RenamingProblems, BackingUpProblems
)

logger = logging.getLogger()


def make_filter_from_worker_id(worker_id: Union[int, str]) -> bytes:
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


def create_identity(worker_type: str, identity: str) -> bytes:
    r"""Generate identity for a worker's 0mq socket.

    >>> create_identity('Worker', '1')
    b'Worker-1'
    >>> create_identity('Thumbnail Extractor', '2')
    b'Thumbnail-Extractor-2'
    >>> create_identity('Thumbnail Extractor Plus', '22 2')
    b'Thumbnail-Extractor-Plus-22-2'
    """

    # Replace any whitespace in the strings with a hyphen
    return '{}-{}'.format('-'.join(worker_type.split()), '-'.join(identity.split())).encode()


def get_worker_id_from_identity(identity: bytes) -> int:
    r"""Extract worker id from the identity used in a 0mq socket

    >>> get_worker_id_from_identity(b'Worker-1')
    1
    >>> get_worker_id_from_identity(b'Thumbnail-Extractor-2')
    2
    >>> get_worker_id_from_identity(b'Thumbnail-Extractor-Plus-22-2')
    2
    """
    return int(identity.decode().split('-')[-1])


def create_inproc_msg(cmd: bytes,
                      worker_id: Optional[int]=None,
                      data: Optional[Any]=None) -> List[bytes]:
    """
    Create a list of three values to be sent via a PAIR socket
    between main and child threads using 0MQ.
    """

    if worker_id is not None:
        worker_id = make_filter_from_worker_id(worker_id)
    else:
        worker_id = b''

    if data is None:
        data = b''
    else:
        data = pickle.dumps(data, pickle.HIGHEST_PROTOCOL)

    return [cmd, worker_id, data]


class ThreadNames:
    rename = 'rename'
    scan = 'scan'
    copy = 'copy'
    backup = 'backup'
    thumbnail_daemon = 'thumbnail_daemon'
    thumbnailer = 'thumbnailer'
    offload = 'offload'
    logger = 'logger'
    load_balancer = 'load_balancer'
    new_version = 'new_version'


class ProcessManager:
    def __init__(self, logging_port: int,
                 thread_name: str) -> None:

        super().__init__()

        self.logging_port = logging_port

        self.processes = {}  # type: Dict[int, psutil.Process]
        self._process_to_run = ''  # Implement in subclass

        self.thread_name = thread_name

        # Monitor which workers we have running
        self.workers = []  # type: List[int]

    def _get_cmd(self) -> str:
        return '{} {}'.format(
            sys.executable, os.path.join(
                os.path.abspath(os.path.dirname(__file__)), self._process_to_run
            )
        )

    def _get_command_line(self, worker_id: int) -> str:
        """
        Implement in subclass
        """
        return ''

    def add_worker(self, worker_id: int) -> None:

        command_line = self._get_command_line(worker_id)
        args = shlex.split(command_line)

        # run command immediately, without waiting a reply, and instruct the Linux
        # kernel to send a terminate signal should this process unexpectedly die
        try:
            proc = psutil.Popen(args, preexec_fn=set_pdeathsig())
        except OSError as e:
            logging.critical("Failed to start process: %s", command_line)
            logging.critical('OSError [Errno %s]: %s', e.errno, e.strerror)
            if e.errno == 8:
                logging.critical(
                    "Script shebang line might be malformed or missing: %s", self._get_cmd()
                )
            sys.exit(1)
        logging.debug("Started '%s' with pid %s", command_line, proc.pid)

        # Add to list of running workers
        self.workers.append(worker_id)
        self.processes[worker_id] = proc

    def forcefully_terminate(self) -> None:
        """
        Forcefully terminate any running child processes.
        """

        zombie_processes = [
            p for p in self.processes.values()
            if p.is_running() and p.status() == psutil.STATUS_ZOMBIE
        ]
        running_processes = [
            p for p in self.processes.values()
            if p.is_running() and p.status() != psutil.STATUS_ZOMBIE
        ]
        if hasattr(self, '_process_name'):
            logging.debug(
                "Forcefully terminating processes for %s: %s zombies, %s running.",
                self._process_name, len(zombie_processes), len(running_processes)
            )

        for p in zombie_processes:  # type: psutil.Process
            try:
                logging.debug("Killing zombie process %s with pid %s", p.name(), p.pid)
                p.kill()
            except:
                logging.error("Failed to kill process with pid %s", p.pid)
        for p in running_processes:  # type: psutil.Process
            try:
                logging.debug("Terminating process %s with pid %s", p.name(), p.pid)
                p.terminate()
            except:
                logging.error("Terminating process with pid %s failed", p.pid)
        gone, alive = psutil.wait_procs(running_processes, timeout=2)
        for p in alive:
            try:
                logging.debug("Killing zombie process %s with pid %s", p.name(), p.pid)
                p.kill()
            except:
                logging.error("Failed to kill process with pid %s", p.pid)

    def process_alive(self, worker_id: int) -> bool:
        """
        Process IDs are reused by the system. Check to make sure
        a new process has not been created with the same process id.

        :param worker_id: the process to check
        :return True if the process is the same, False otherwise
        """

        return self.processes[worker_id].is_running()


class PullPipelineManager(ProcessManager, QObject):
    """
    Base class from which more specialized 0MQ classes are derived.

    Receives data into its sink via a ZMQ PULL socket, but does not
    specify how workers should be sent data.

    Outputs signals using Qt.
    """

    message = pyqtSignal(str) # Derived class will change this
    sinkStarted = pyqtSignal()
    workerFinished = pyqtSignal(int)
    workerStopped = pyqtSignal(int)
    receiverPortSignal = pyqtSignal(int)

    def __init__(self, logging_port: int,
                 thread_name: str) -> None:
        super().__init__(logging_port=logging_port, thread_name=thread_name)

    def _start_sockets(self) -> None:

        context = zmq.Context.instance()

        # Subclasses must define the type of port they need to send messages
        self.ventilator_socket = None
        self.ventilator_port = None

        # Sink socket to receive results of the workers
        self.receiver_socket = context.socket(zmq.PULL)
        self.receiver_port = self.receiver_socket.bind_to_random_port('tcp://*')

        # Socket to communicate directly with the sink, bypassing the workers
        self.terminate_socket = context.socket(zmq.PUSH)
        self.terminate_socket.connect("tcp://localhost:{}".format(self.receiver_port))

        # Socket to receive commands from main thread
        self.thread_controller = context.socket(zmq.PAIR)
        self.thread_controller.connect('inproc://{}'.format(self.thread_name))

        self.terminating = False

    @pyqtSlot()
    def run_sink(self) -> None:
        logging.debug("Running sink for %s", self._process_name)

        self._start_sockets()

        poller = zmq.Poller()
        poller.register(self.receiver_socket, zmq.POLLIN)
        poller.register(self.thread_controller, zmq.POLLIN)

        self.receiverPortSignal.emit(self.receiver_port)
        self.sinkStarted.emit()

        while True:
            try:
                socks = dict(poller.poll())
            except KeyboardInterrupt:
                break
            if self.receiver_socket in socks:
                # Receive messages from the workers
                # (or the terminate socket)
                worker_id, directive, content = self.receiver_socket.recv_multipart()

                if directive == b'cmd':
                    command = content
                    assert command in (b"STOPPED", b"FINISHED", b"KILL")
                    if command == b"KILL":
                        # Terminate immediately, without regard for any
                        # incoming messages. This message is only sent
                        # from this manager to itself, using the
                        # self.terminate_socket
                        logging.debug("{} is terminating".format(self._process_name))
                        break
                    # This worker is done; remove from monitored workers and
                    # continue
                    worker_id = int(worker_id)
                    if command == b"STOPPED":
                        logging.debug("%s worker %s has stopped", self._process_name, worker_id)
                        self.workerStopped.emit(worker_id)
                    else:
                        # Worker has finished its work
                        self.workerFinished.emit(worker_id)
                    self.workers.remove(worker_id)
                    del self.processes[worker_id]
                    if not self.workers:
                        logging.debug("{} currently has no workers".format(self._process_name))
                    if not self.workers and self.terminating:
                        logging.debug("{} is exiting".format(self._process_name))
                        break
                else:
                    assert directive == b'data'
                    self.content = content
                    self.process_sink_data()

            if self.thread_controller in socks:
                # Receive messages from the main Rapid Photo Downloader thread
                self.process_thread_directive()

    def process_thread_directive(self) -> None:
        directive, worker_id, data = self.thread_controller.recv_multipart()

        # Directives: START, STOP, TERMINATE, SEND_TO_WORKER, STOP_WORKER, START_WORKER
        if directive == b'START':
            self.start()
        elif directive == b'START_WORKER':
            self.start_worker(worker_id=worker_id, data=data)
        elif directive == b'SEND_TO_WORKER':
            self.send_message_to_worker(worker_id=worker_id, data=data)
        elif directive == b'STOP':
            self.stop()
        elif directive == b'STOP_WORKER':
            self.stop_worker(worker_id=worker_id)
        elif directive == b'PAUSE':
            self.pause()
        elif directive == b'RESUME':
            self.resume(worker_id=worker_id)
        elif directive == b'TERMINATE':
            self.forcefully_terminate()
        else:
            logging.critical("%s received unknown directive %s", directive.decode())

    def process_sink_data(self) -> None:
        data = pickle.loads(self.content)
        self.message.emit(data)

    def terminate_sink(self) -> None:
        self.terminate_socket.send_multipart([b'0', b'cmd', b'KILL'])

    def _get_ventilator_start_message(self, worker_id: bytes) -> list:
        return [worker_id, b'cmd', b'START']

    def start(self) -> None:
        logging.critical(
            "Member function start() not implemented in child class of %s", self._process_name
        )

    def start_worker(self, worker_id: bytes, data: bytes) -> None:
        logging.critical(
            "Member function start_worker() not implemented in child class of %s",
            self._process_name
        )

    def stop(self) -> None:
        logging.critical(
            "Member function stop() not implemented in child class of %s", self._process_name
        )

    def stop_worker(self, worker_id: int) -> None:
        logging.critical(
            "Member function stop_worker() not implemented in child class of %s",
            self._process_name
        )

    def pause(self) -> None:
        logging.critical("Member function pause() not implemented in child class of %s",
                         self._process_name)

    def resume(self, worker_id: Optional[bytes]) -> None:
        logging.critical(
            "Member function stop_worker() not implemented in child class of %s", self._process_name
        )

    def send_message_to_worker(self, data: bytes, worker_id:Optional[bytes]=None) -> None:
        if self.terminating:
            logging.debug(
                "%s not sending message to worker because manager is terminated", self._process_name
            )
            return
        if not self.workers:
            logging.debug(
                "%s not sending message to worker because there are no workers", self._process_name
            )
            return

        assert isinstance(data, bytes)

        if worker_id:
            message = [worker_id, b'data', data]
        else:
            message = [b'data', data]
        self.ventilator_socket.send_multipart(message)

    def forcefully_terminate(self) -> None:
        """
        Forcefully terminate any child processes and clean up.

        Shuts down the sink too.
        """

        super().forcefully_terminate()
        self.terminate_sink()


class LoadBalancerWorkerManager(ProcessManager):
    def __init__(self, no_workers: int,
                 backend_port: int,
                 sink_port: int,
                 logging_port: int) -> None:
        super().__init__(logging_port=logging_port, thread_name='')
        self.no_workers = no_workers
        self.backend_port = backend_port
        self.sink_port = sink_port

    def _get_command_line(self, worker_id: int) -> str:
        cmd = self._get_cmd()

        return '{} --request {} --send {} --identity {} --logging {}'.format(
            cmd,
            self.backend_port,
            self.sink_port,
            worker_id,
            self.logging_port
        )

    def start_workers(self) -> None:
        for worker_id in range(self.no_workers):
            self.add_worker(worker_id)

    def zombie_workers(self) -> List[int]:
        return [
            worker_id for worker_id in self.workers
            if self.processes[worker_id].status() == psutil.STATUS_ZOMBIE
        ]


class LRUQueue:
    """LRUQueue class using ZMQStream/IOLoop for event dispatching"""

    def __init__(self, backend_socket: zmq.Socket,
                 frontend_socket: zmq.Socket,
                 controller_socket: zmq.Socket,
                 worker_type: str,
                 process_manager: LoadBalancerWorkerManager) -> None:

        self.worker_type = worker_type
        self.process_manager = process_manager
        self.workers = deque()
        self.terminating = False
        self.terminating_workers = set()  # type: Set[bytes]
        self.stopped_workers = set()  # type: Set[int]

        self.backend = ZMQStream(backend_socket)
        self.frontend = ZMQStream(frontend_socket)
        self.controller = ZMQStream(controller_socket)
        self.backend.on_recv(self.handle_backend)
        self.controller.on_recv(self.handle_controller)

        self.loop = ioloop.IOLoop.instance()

    def handle_controller(self, msg):
        self.terminating = True
        # logging.debug(
        #     "%s load balancer requesting %s workers to stop", self.worker_type, len(self.workers)
        # )

        while len(self.workers):
            worker_identity = self.workers.popleft()

            logging.debug(
                "%s load balancer sending stop cmd to worker %s",
                self.worker_type, worker_identity.decode()
            )
            self.backend.send_multipart([worker_identity, b'', b'cmd', b'STOP'])
            self.terminating_workers.add(worker_identity)

        self.loop.add_timeout(time.time()+3, self.loop.stop)

    def handle_backend(self, msg):
        # Queue worker address for LRU routing
        worker_identity, empty, client_addr = msg[:3]

        # add worker back to the list of workers
        self.workers.append(worker_identity)

        zw = self.process_manager.zombie_workers()
        if zw:
            logging.error("%s dead thumbnail extractors", len(zw))

        # Second frame is empty
        assert empty == b''

        if msg[-1] == b'STOPPED' and self.terminating:
            worker_id = get_worker_id_from_identity(worker_identity)
            self.stopped_workers.add(worker_id)
            self.terminating_workers.remove(worker_identity)
            if len(self.terminating_workers) == 0:
                for worker_id in self.stopped_workers:
                    p = self.process_manager.processes[worker_id]  # type: psutil.Process
                    if p.is_running():
                        pid = p.pid
                        if p.status() != psutil.STATUS_SLEEPING:
                            logging.debug(
                                "Waiting on %s process %s...", p.status(), pid
                            )
                            os.waitpid(pid, 0)
                            logging.debug("...process %s is finished", pid)
                        else:
                            logging.debug("Process %s is sleeping", pid)
                self.loop.add_timeout(time.time()+0.5, self.loop.stop)

        if len(self.workers) == 1:
            # on first recv, start accepting frontend messages
            self.frontend.on_recv(self.handle_frontend)

    def handle_frontend(self, request):
        #  Dequeue and drop the next worker address
        worker_identity = self.workers.popleft()

        message = [worker_identity, b''] + request
        self.backend.send_multipart(message)
        if len(self.workers) == 0:
            # stop receiving until workers become available again
            self.frontend.stop_on_recv()


class LoadBalancer:
    def __init__(self, worker_type: str, process_manager) -> None:

        self.parser = argparse.ArgumentParser()
        self.parser.add_argument("--receive", required=True)
        self.parser.add_argument("--send", required=True)
        self.parser.add_argument("--controller", required=True)
        self.parser.add_argument("--logging", required=True)

        args = self.parser.parse_args()
        self.controller_port = args.controller

        context = zmq.Context()
        frontend = context.socket(zmq.PULL)
        frontend_port = frontend.bind_to_random_port('tcp://*')

        backend = context.socket(zmq.ROUTER)
        backend_port = backend.bind_to_random_port('tcp://*')

        reply = context.socket(zmq.REP)
        reply.connect("tcp://localhost:{}".format(args.receive))

        controller = context.socket(zmq.PULL)
        controller.connect('tcp://localhost:{}'.format(self.controller_port))

        sink_port = args.send
        logging_port = args.logging

        self.logger_publisher = ProcessLoggerPublisher(
            context=context, name=worker_type, notification_port=args.logging
        )

        logging.debug(
            "{} load balancer waiting to be notified how many workers to initialize...".format(
                worker_type
            )
        )
        no_workers = int(reply.recv())
        logging.debug("...{} load balancer will use {} workers".format(worker_type, no_workers))
        reply.send(str(frontend_port).encode())

        process_manager = process_manager(no_workers, backend_port, sink_port, logging_port)
        process_manager.start_workers()

        # create queue with the sockets
        queue = LRUQueue(backend, frontend, controller, worker_type, process_manager)

        # start reactor, which is an infinite loop
        ioloop.IOLoop.instance().start()

        # Finished infinite loop: do some housekeeping
        logging.debug("Forcefully terminating load balancer child processes")
        process_manager.forcefully_terminate()

        frontend.close()
        backend.close()


class LoadBalancerManager(ProcessManager, QObject):
    """
    Launches and requests termination of the Load Balancer process
    """

    load_balancer_started = pyqtSignal(int)
    def __init__(self, context: zmq.Context,
                 no_workers: int,
                 sink_port: int,
                 logging_port: int,
                 thread_name: str) -> None:
        super().__init__(logging_port=logging_port, thread_name=thread_name)
        self.no_workers = no_workers
        self.sink_port = sink_port
        self.context = context

    @pyqtSlot()
    def start_load_balancer(self) -> None:

        self.controller_socket = self.context.socket(zmq.PUSH)
        self.controller_port = self.controller_socket.bind_to_random_port('tcp://*')

        self.requester = self.context.socket(zmq.REQ)
        self.requester_port = self.requester.bind_to_random_port('tcp://*')

        self.thread_controller = self. context.socket(zmq.PAIR)
        self.thread_controller.connect('inproc://{}'.format(self.thread_name))

        worker_id = 0
        self.add_worker(worker_id)
        self.requester.send(str(self.no_workers).encode())
        self.frontend_port = int(self.requester.recv())
        self.load_balancer_started.emit(self.frontend_port)

        # wait for stop signal
        directive, worker_id, data = self.thread_controller.recv_multipart()
        assert directive == b'STOP'
        self.stop()

    def stop(self):
        self.controller_socket.send(b'STOP')

    def _get_command_line(self, worker_id: int) -> str:
        cmd = self._get_cmd()

        return '{} --receive {} --send {} --controller {} --logging {}'.format(
            cmd,
            self.requester_port,
            self.sink_port,
            self.controller_port,
            self.logging_port
        )

DAEMON_WORKER_ID = 0


class PushPullDaemonManager(PullPipelineManager):
    """
    Manage a single instance daemon worker process that waits to work on data
    issued by this manager. The data to be worked on is issued in sequence,
    one after the other.

    Because this is a single daemon process, a Push-Pull model is most
    suitable for sending the data.
    """

    def _start_sockets(self) -> None:

        super()._start_sockets()

        context = zmq.Context.instance()

        # Ventilator socket to send message to worker
        self.ventilator_socket = context.socket(zmq.PUSH)
        self.ventilator_port = self.ventilator_socket.bind_to_random_port('tcp://*')

    def stop(self) -> None:
        """
        Permanently stop the daemon process and terminate
        """

        logging.debug("{} halting".format(self._process_name))
        self.terminating = True

        # Only send stop command if the process is still running
        if self.process_alive(DAEMON_WORKER_ID):
            try:
                self.ventilator_socket.send_multipart([b'cmd', b'STOP'], zmq.DONTWAIT)
            except zmq.Again:
                logging.debug(
                    "Terminating %s sink because child process did not receive message",
                    self._process_name
                )
                self.terminate_sink()
        else:
            # The process may have crashed. Stop the sink.
            self.terminate_sink()

    def _get_command_line(self, worker_id: int) -> str:
        cmd = self._get_cmd()

        return '{} --receive {} --send {} --logging {}'.format(
            cmd,
            self.ventilator_port,
            self.receiver_port,
            self.logging_port
        )

    def _get_ventilator_start_message(self, worker_id: int) -> List[bytes]:
        return [b'cmd', b'START']

    def start(self) -> None:
        logging.debug("Starting worker for %s", self._process_name)
        self.add_worker(worker_id=DAEMON_WORKER_ID)


class PublishPullPipelineManager(PullPipelineManager):
    """
    Manage a collection of worker processes that wait to work on data
    issued by this manager. The data to be worked on is issued in sequence,
    one after the other, either once, or many times.

    Because there are multiple worker process, a Publish-Subscribe model is
    most suitable for sending data to workers.
    """

    def _start_sockets(self) -> None:

        super()._start_sockets()

        context = zmq.Context.instance()

        # Ventilator socket to send messages to workers on
        self.ventilator_socket = context.socket(zmq.PUB)
        self.ventilator_port= self.ventilator_socket.bind_to_random_port('tcp://*')

        # Socket to synchronize the start of each worker
        self.sync_service_socket = context.socket(zmq.REP)
        self.sync_service_port = self.sync_service_socket.bind_to_random_port("tcp://*")

        # Socket for worker control: pause, resume, stop
        self.controller_socket = context.socket(zmq.PUB)
        self.controller_port = self.controller_socket.bind_to_random_port("tcp://*")

    def stop(self) -> None:
        """
        Permanently stop all the workers and terminate
        """

        logging.debug("{} halting".format(self._process_name))
        self.terminating = True
        if self.workers:
            # Signal workers they must immediately stop
            termination_signal_sent = False
            alive_workers = [worker_id for worker_id in self.workers if
                             self.process_alive(worker_id)]
            for worker_id in alive_workers:

                message = [make_filter_from_worker_id(worker_id),b'STOP']
                self.controller_socket.send_multipart(message)

                message = [make_filter_from_worker_id(worker_id), b'cmd', b'STOP']
                self.ventilator_socket.send_multipart(message)
                termination_signal_sent = True

            if not termination_signal_sent:
                self.terminate_sink()
        else:
            self.terminate_sink()

    def stop_worker(self, worker_id: bytes) -> None:
        """
        Permanently stop one worker
        """

        if int(worker_id) in self.workers:
            message = [worker_id, b'STOP']
            self.controller_socket.send_multipart(message)
            message = [worker_id, b'cmd', b'STOP']
            self.ventilator_socket.send_multipart(message)

    def start_worker(self, worker_id: bytes, data: bytes) -> None:

        self.add_worker(int(worker_id))

        # Send START commands until scan worker indicates it is ready to
        # receive data
        # Worker ID must be in bytes format
        while True:
            self.ventilator_socket.send_multipart(
                self._get_ventilator_start_message(worker_id))
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
        self.send_message_to_worker(data=data, worker_id=worker_id)

    def _get_command_line(self, worker_id: int) -> str:
        cmd = self._get_cmd()

        return '{} --receive {} --send {} --controller {} --syncclient {} --filter {} --logging '\
               '{}'.format(
            cmd,
            self.ventilator_port,
            self.receiver_port,
            self.controller_port,
            self.sync_service_port,
            worker_id,
            self.logging_port
        )

    def __len__(self) -> int:
        return len(self.workers)

    def __contains__(self, item) -> bool:
        return item in self.workers

    def pause(self) -> None:
        for worker_id in self.workers:
            message = [make_filter_from_worker_id(worker_id), b'PAUSE']
            self.controller_socket.send_multipart(message)

    def resume(self, worker_id: bytes) -> None:
        if worker_id:
            workers = [int(worker_id)]
        else:
            workers = self.workers
        for worker_id in workers:
            message = [make_filter_from_worker_id(worker_id), b'RESUME']
            self.controller_socket.send_multipart(message)


class ProcessLoggerPublisher:
    """
    Setup the sockets for worker processes to send log messages to the
    main process.

    Two tasks: set up the PUB socket, and then tell the main process
    what port we're using via a second socket, and when we're closing it.
    """

    def __init__(self, context: zmq.Context, name: str, notification_port: int) -> None:

        self.logger_pub = context.socket(zmq.PUB)
        self.logger_pub_port = self.logger_pub.bind_to_random_port("tcp://*")
        self.handler = ZeroMQSocketHandler(self.logger_pub)
        self.handler.setLevel(logging.DEBUG)

        self.logger = logging.getLogger()
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(self.handler)
    
        self.logger_socket = context.socket(zmq.PUSH)
        self.logger_socket.connect("tcp://localhost:{}".format(notification_port))
        self.logger_socket.send_multipart([b'CONNECT', str(self.logger_pub_port).encode()])

    def close(self):
        self.logger.removeHandler(self.handler)
        self.logger_socket.send_multipart([b'DISCONNECT', str(self.logger_pub_port).encode()])
        self.logger_pub.close()
        self.logger_socket.close()


class WorkerProcess():
    def __init__(self, worker_type: str) -> None:
        super().__init__()
        self.parser = argparse.ArgumentParser()
        self.parser.add_argument("--receive", required=True)
        self.parser.add_argument("--send", required=True)
        self.parser.add_argument("--logging", required=True)

    def cleanup_pre_stop(self) -> None:
        """
        Operations to run if process is stopped.

        Implement in child class if needed.
        """

        pass

    def setup_logging_pub(self, notification_port: int, name: str) -> None:
        """
        Sets up the 0MQ socket that sends out logging messages

        :param notification_port: port that should be notified about
         the new logging publisher
        :param name: descriptive name to place in the log messages
        """

        if self.worker_id is not None:
            name = '{}-{}'.format(name, self.worker_id.decode())
        self.logger_publisher = ProcessLoggerPublisher(
            context=self.context, name=name, notification_port=notification_port
        )

    def send_message_to_sink(self) -> None:

        self.sender.send_multipart([self.worker_id, b'data', self.content])

    def initialise_process(self) -> None:
        # Wait to receive "START" message
        worker_id, directive, content = self.receiver.recv_multipart()
        assert directive == b'cmd'
        assert content == b'START'

        # send a synchronization request
        self.sync_client.send(b'')

        # wait for synchronization reply
        self.sync_client.recv()

        # Receive next "START" message and discard, looking for data message
        while True:
            worker_id, directive, content = self.receiver.recv_multipart()
            if directive == b'data':
                break
            else:
                assert directive == b'cmd'
                assert content == b'START'

        self.content = content

    def do_work(self):
        pass


class DaemonProcess(WorkerProcess):
    """
    Single instance
    """
    def __init__(self, worker_type: str) -> None:
        super().__init__(worker_type)

        args = self.parser.parse_args()

        self.context = zmq.Context()
        # Socket to send messages along the pipe to
        self.sender = self.context.socket(zmq.PUSH)
        self.sender.set_hwm(10)
        self.sender.connect("tcp://localhost:{}".format(args.send))

        self.receiver = self.context.socket(zmq.PULL)
        self.receiver.connect("tcp://localhost:{}".format(args.receive))

        self.worker_id = None

        self.setup_logging_pub(notification_port=args.logging, name=worker_type)

    def run(self) -> None:
        pass

    def check_for_command(self, directive: bytes, content: bytes) -> None:
        if directive == b'cmd':
            assert content == b'STOP'
            self.cleanup_pre_stop()
            # signal to sink that we've terminated before finishing
            self.sender.send_multipart(
                [make_filter_from_worker_id(DAEMON_WORKER_ID), b'cmd', b'STOPPED']
            )
            sys.exit(0)

    def send_message_to_sink(self) -> None:
        # Must use a dummy value for the worker id, as there is only ever one
        # instance.
        self.sender.send_multipart(
            [make_filter_from_worker_id(DAEMON_WORKER_ID), b'data', self.content]
        )


class WorkerInPublishPullPipeline(WorkerProcess):
    """
    Worker counterpart to PublishPullPipelineManager; multiple instance.
    """
    def __init__(self, worker_type: str) -> None:
        super().__init__(worker_type)
        self.add_args()

        args = self.parser.parse_args()

        subscription_filter = self.worker_id = args.filter.encode()
        self.context = zmq.Context()

        self.setup_sockets(args, subscription_filter)
        self.setup_logging_pub(notification_port=args.logging, name=worker_type)

        self.initialise_process()
        self.do_work()

    def add_args(self) -> None:
        self.parser.add_argument("--filter", required=True)
        self.parser.add_argument("--syncclient", required=True)
        self.parser.add_argument("--controller", required=True)

    def setup_sockets(self, args, subscription_filter: bytes) -> None:

        # Socket to send messages along the pipe to
        self.sender = self.context.socket(zmq.PUSH)
        self.sender.set_hwm(10)
        self.sender.connect("tcp://localhost:{}".format(args.send))

        # Socket to receive messages from the pipe
        self.receiver = self.context.socket(zmq.SUB)
        self.receiver.connect("tcp://localhost:{}".format(args.receive))
        self.receiver.setsockopt(zmq.SUBSCRIBE, subscription_filter)

        # Socket to receive controller messages: stop, pause, resume
        self.controller = self.context.socket(zmq.SUB)
        self.controller.connect("tcp://localhost:{}".format(args.controller))
        self.controller.setsockopt(zmq.SUBSCRIBE, subscription_filter)

        # Socket to synchronize the start of receiving data from upstream
        self.sync_client = self.context.socket(zmq.REQ)
        self.sync_client.connect("tcp://localhost:{}".format(args.syncclient))

    def check_for_command(self, directive: bytes, content) -> None:
        if directive == b'cmd':
            try:
                assert content == b'STOP'
            except AssertionError:
                logging.critical("Expected STOP command but instead got %s", content.decode())
            else:
                self.cleanup_pre_stop()
                self.disconnect_logging()
                # signal to sink that we've terminated before finishing
                self.sender.send_multipart([self.worker_id, b'cmd', b'STOPPED'])
                sys.exit(0)

    def check_for_controller_directive(self) -> None:
        try:
            # Don't block if process is running regularly
            # If there is no command,exception will occur
            worker_id, command = self.controller.recv_multipart(zmq.DONTWAIT)
            assert command in [b'PAUSE', b'STOP']
            assert  worker_id == self.worker_id

            if command == b'PAUSE':
                # Because the process is paused, do a blocking read to
                # wait for the next command
                worker_id, command = self.controller.recv_multipart()
                assert (command in [b'RESUME', b'STOP'])
            if command == b'STOP':
                self.cleanup_pre_stop()
                # before finishing, signal to sink that we've terminated
                self.sender.send_multipart([self.worker_id, b'cmd', b'STOPPED'])
                sys.exit(0)
        except zmq.Again:
            pass # Continue working

    def resume_work(self) -> None:
        worker_id, command = self.controller.recv_multipart()
        assert (command in [b'RESUME', b'STOP'])
        if command == b'STOP':
            self.cleanup_pre_stop()
            self.disconnect_logging()
            # before finishing, signal to sink that we've terminated
            self.sender.send_multipart([self.worker_id, b'cmd', b'STOPPED'])
            sys.exit(0)

    def disconnect_logging(self) -> None:
        self.logger_publisher.close()

    def send_finished_command(self) -> None:
        self.sender.send_multipart([self.worker_id, b'cmd', b'FINISHED'])


class LoadBalancerWorker:
    def __init__(self, worker_type: str) -> None:
        super().__init__()
        self.parser = argparse.ArgumentParser()
        self.parser.add_argument("--request", required=True)
        self.parser.add_argument("--send", required=True)
        self.parser.add_argument("--identity", required=True)
        self.parser.add_argument("--logging", required=True)

        args = self.parser.parse_args()

        self.context = zmq.Context()

        self.requester = self.context.socket(zmq.REQ)
        self.identity = create_identity(worker_type, args.identity)
        self.requester.identity = self.identity
        self.requester.connect("tcp://localhost:{}".format(args.request))

        # Sender is located in the main process. It is where output (messages)
        # from this process are are sent to.
        self.sender = self.context.socket(zmq.PUSH)
        self.sender.connect("tcp://localhost:{}".format(args.send))
        
        self.logger_publisher = ProcessLoggerPublisher(
            context=self.context, name=worker_type, notification_port=args.logging
        )

        # Tell the load balancer we are ready for work
        self.requester.send(b"READY")
        self.do_work()

    def do_work(self) -> None:
        # Implement in subclass
        pass

    def cleanup_pre_stop(self) -> None:
        """
        Operations to run if process is stopped.

        Implement in child class if needed.
        """

        pass

    def exit(self):
        self.cleanup_pre_stop()
        identity = self.requester.identity.decode()
        # signal to load balancer that we've terminated before finishing
        self.requester.send_multipart([b'', b'', b'STOPPED'])
        self.requester.close()
        self.sender.close()
        self.logger_publisher.close()
        self.context.term()
        logging.debug("%s with pid %s stopped", identity, os.getpid())
        sys.exit(0)

    def check_for_command(self, directive: bytes, content: bytes):
        if directive == b'cmd':
            assert content == b'STOP'
            self.exit()


class ProcessLoggingManager(QObject):
    """
    Receive and log logging messages from workers.

    An alternative might be using python logging's QueueListener, which
    like this code, runs on its own thread.
    """

    ready = pyqtSignal(int)

    @pyqtSlot()
    def startReceiver(self) -> None:
        context = zmq.Context.instance()
        self.receiver = context.socket(zmq.SUB)
        # Subscribe to all variates of logging messages
        self.receiver.setsockopt(zmq.SUBSCRIBE, b'')

        # Socket to receive subscription information, and the stop command
        info_socket = context.socket(zmq.PULL)
        self.info_port = info_socket.bind_to_random_port('tcp://*')

        poller = zmq.Poller()
        poller.register(self.receiver, zmq.POLLIN)
        poller.register(info_socket, zmq.POLLIN)

        self.ready.emit(self.info_port)

        while True:
            try:
                socks = dict(poller.poll())
            except KeyboardInterrupt:
                break

            if self.receiver in socks:
                message = self.receiver.recv()
                record = logging.makeLogRecord(pickle.loads(message))
                logger.handle(record)

            if info_socket in socks:
                directive, content = info_socket.recv_multipart()
                if directive == b'STOP':
                    break
                elif directive == b'CONNECT':
                    self.addSubscription(content)
                else:
                    assert directive == b'DISCONNECT'
                    self.removeSubscription(content)

    def addSubscription(self, port: bytes) -> None:
        try:
            port = int(port)
        except ValueError:
            logging.critical('Incorrect port value in add logging subscription: %s', port)
        else:
            logging.debug("Subscribing to logging on port %s", port)
            self.receiver.connect("tcp://localhost:{}".format(port))

    def removeSubscription(self, port: bytes):
        try:
            port = int(port)
        except ValueError:
            logging.critical('Incorrect port value in remove logging subscription: %s', port)
        else:
            logging.debug("Unsubscribing to logging on port %s", port)
            self.receiver.disconnect("tcp://localhost:{}".format(port))


def stop_process_logging_manager(info_port: int) -> None:
    """
    Stop ProcessLoggingManager thread

    :param info_port: the port number the manager uses
    """

    context = zmq.Context.instance()
    command =  context.socket(zmq.PUSH)
    command.connect("tcp://localhost:{}".format(info_port))
    command.send_multipart([b'STOP', b''])


class ScanArguments:
    """
    Pass arguments to the scan process
    """
    def __init__(self, device: Device,
                 ignore_other_types: bool,
                 log_gphoto2: bool) -> None:
        """
        Pass arguments to the scan process

        :param device: the device to scan
        :param ignore_other_types: ignore file types like TIFF
        :param log_gphoto2: whether to generate detailed gphoto2 log
         messages
        :param scan_only_DCIM: if the device is an auto-detected volume,
         then if True, scan only in it's DCIM folder
        :param warn_unknown_file: whether to issue a warning when
         encountering an unknown (unrecognized) file
        """

        self.device = device
        self.ignore_other_types = ignore_other_types
        self.log_gphoto2 = log_gphoto2


class ScanResults:
    """
    Receive results from the scan process
    """

    def __init__(self, rpd_files: Optional[List[RPDFile]]=None,
                 file_type_counter: Optional[FileTypeCounter]=None,
                 file_size_sum: Optional[FileSizeSum]=None,
                 error_code: Optional[CameraErrorCode]=None,
                 scan_id: Optional[int]=None,
                 optimal_display_name: Optional[str]=None,
                 storage_space: Optional[List[StorageSpace]]=None,
                 storage_descriptions: Optional[List[str]]=None,
                 sample_photo: Optional[Photo]=None,
                 sample_video: Optional[Video]=None,
                 problems: Optional[ScanProblems]=None,
                 fatal_error: Optional[bool]=None,
                 entire_video_required: Optional[bool]=None,
                 entire_photo_required: Optional[bool]=None) -> None:
        self.rpd_files = rpd_files
        self.file_type_counter = file_type_counter
        self.file_size_sum = file_size_sum
        self.error_code = error_code
        self.scan_id = scan_id
        self.optimal_display_name = optimal_display_name
        self.storage_space = storage_space
        self.storage_descriptions = storage_descriptions
        self.sample_photo = sample_photo
        self.sample_video = sample_video
        self.problems = problems
        self.fatal_error = fatal_error
        self.entire_video_required = entire_video_required
        self.entire_photo_required = entire_photo_required


class CopyFilesArguments:
    """
    Pass arguments to the copyfiles process
    """

    def  __init__(self, scan_id: int,
                  device: Device,
                  photo_download_folder: str,
                  video_download_folder: str,
                  files: List[RPDFile],
                  verify_file: bool,
                  generate_thumbnails: bool,
                  log_gphoto2: bool) -> None:
        self.scan_id = scan_id
        self.device = device
        self.photo_download_folder = photo_download_folder
        self.video_download_folder = video_download_folder
        self.files = files
        self.generate_thumbnails = generate_thumbnails
        self.verify_file = verify_file
        self.log_gphoto2 = log_gphoto2


class CopyFilesResults:
    """
    Receive results from the copyfiles process
    """

    def __init__(self, scan_id: Optional[int]=None,
                 photo_temp_dir: Optional[str]=None,
                 video_temp_dir: Optional[str]=None,
                 total_downloaded: Optional[int]=None,
                 chunk_downloaded: Optional[int]=None,
                 copy_succeeded: Optional[bool]=None,
                 rpd_file: Optional[RPDFile]=None,
                 download_count: Optional[int]=None,
                 mdata_exceptions: Optional[Tuple]=None,
                 problems: Optional[CopyingProblems]=None) -> None:
        """

        :param scan_id: scan id of the device the files are being
         downloaded from
        :param photo_temp_dir: temp directory path, used to copy
         photos into until they're renamed
        :param video_temp_dir: temp directory path, used to copy
         videos into until they're renamed
        :param total_downloaded: how many bytes in total have been
         downloaded
        :param chunk_downloaded: how many bytes were downloaded since
         the last message
        :param copy_succeeded: whether the copy was successful or not
        :param rpd_file: details of the file that was copied
        :param download_count: a running count of how many files
         have been copied. Used in download tracking.
        :param mdata_exceptions: details of errors setting file metadata
        :param problems: details of any problems encountered copying files,
         not including metedata write problems.
        """

        self.scan_id = scan_id

        self.photo_temp_dir = photo_temp_dir
        self.video_temp_dir = video_temp_dir

        self.total_downloaded = total_downloaded
        self.chunk_downloaded = chunk_downloaded

        self.copy_succeeded = copy_succeeded
        self.rpd_file = rpd_file
        self.download_count = download_count
        self.mdata_exceptions = mdata_exceptions
        self.problems = problems


class ThumbnailDaemonData:
    """
    Pass arguments to the thumbnail daemon process.

    Occurs after a file is downloaded & renamed, and also
    after a file is backed up.
    """

    def __init__(self, frontend_port: Optional[int]=None,
                 rpd_file: Optional[RPDFile]=None,
                 write_fdo_thumbnail: Optional[bool]=None,
                 use_thumbnail_cache: Optional[bool]=None,
                 backup_full_file_names: Optional[List[str]]=None,
                 fdo_name: Optional[str]=None) -> None:
        self.frontend_port = frontend_port
        self.rpd_file = rpd_file
        self.write_fdo_thumbnail = write_fdo_thumbnail
        self.use_thumbnail_cache = use_thumbnail_cache
        self.backup_full_file_names = backup_full_file_names
        self.fdo_name = fdo_name


class RenameAndMoveFileData:
    """
    Pass arguments to the renameandmovefile process
    """

    def __init__(self, rpd_file: RPDFile=None,
                 download_count: int=None,
                 download_succeeded: bool=None,
                 message: RenameAndMoveStatus=None) -> None:
        self.rpd_file = rpd_file
        self.download_count = download_count
        self.download_succeeded = download_succeeded
        self.message = message


class RenameAndMoveFileResults:
    def __init__(self, move_succeeded: bool=None,
                 rpd_file: RPDFile=None,
                 download_count: int=None,
                 stored_sequence_no: int=None,
                 downloads_today: List[str]=None,
                 problems: Optional[RenamingProblems]=None) -> None:
        self.move_succeeded = move_succeeded
        self.rpd_file = rpd_file
        self.download_count = download_count
        self.stored_sequence_no = stored_sequence_no
        self.downloads_today = downloads_today
        self.problems = problems


class OffloadData:
    def __init__(self, thumbnail_rows: Optional[Sequence[ThumbnailDataForProximity]]=None,
                 proximity_seconds: int=None,
                 rpd_files: Optional[Sequence[RPDFile]]=None,
                 strip_characters: Optional[bool]=None,
                 folders_preview: Optional[FoldersPreview]=None) -> None:
        self.thumbnail_rows = thumbnail_rows
        self.proximity_seconds = proximity_seconds
        self.rpd_files = rpd_files
        self.strip_characters = strip_characters
        self.folders_preview = folders_preview


class OffloadResults:
    def __init__(self, proximity_groups: Optional[TemporalProximityGroups]=None,
                 folders_preview: Optional[FoldersPreview]=None) -> None:
        self.proximity_groups = proximity_groups
        self.folders_preview = folders_preview


class BackupArguments:
    """
    Pass start up data to the back up process
    """
    def __init__(self, path: str, device_name: str) -> None:
        self.path = path
        self.device_name = device_name


class BackupFileData:
    """
    Pass file data to the backup process
    """
    def __init__(self, rpd_file: Optional[RPDFile]=None,
                 move_succeeded: Optional[bool]=None,
                 do_backup: Optional[bool]=None,
                 path_suffix: Optional[str]=None,
                 backup_duplicate_overwrite: Optional[bool]=None,
                 verify_file: Optional[bool]=None,
                 download_count: Optional[int]=None,
                 save_fdo_thumbnail: Optional[int]=None,
                 message: Optional[BackupStatus]=None) -> None:
        self.rpd_file = rpd_file
        self.move_succeeded = move_succeeded
        self.do_backup = do_backup
        self.path_suffix = path_suffix
        self.backup_duplicate_overwrite = backup_duplicate_overwrite
        self.verify_file = verify_file
        self.download_count = download_count
        self.save_fdo_thumbnail = save_fdo_thumbnail
        self.message = message


class BackupResults:
    def __init__(self, scan_id: int,
                 device_id: int,
                 total_downloaded: Optional[int]=None,
                 chunk_downloaded: Optional[int]=None,
                 backup_succeeded: Optional[bool]=None,
                 do_backup: Optional[bool]=None,
                 rpd_file: Optional[RPDFile] = None,
                 backup_full_file_name: Optional[str]=None,
                 mdata_exceptions: Optional[Tuple] = None,
                 problems: Optional[BackingUpProblems]=None) -> None:
        self.scan_id = scan_id
        self.device_id = device_id
        self.total_downloaded = total_downloaded
        self.chunk_downloaded = chunk_downloaded
        self.backup_succeeded = backup_succeeded
        self.do_backup = do_backup
        self.rpd_file = rpd_file
        self.backup_full_file_name = backup_full_file_name
        self.mdata_exceptions = mdata_exceptions
        self.problems = problems


class GenerateThumbnailsArguments:
    def __init__(self, scan_id: int,
                 rpd_files: List[RPDFile],
                 name: str,
                 proximity_seconds: int,
                 cache_dirs: CacheDirs,
                 need_photo_cache_dir: bool,
                 need_video_cache_dir: bool,
                 frontend_port: int,
                 log_gphoto2: bool,
                 camera: Optional[str]=None,
                 port: Optional[str]=None,
                 entire_video_required: Optional[bool]=None,
                 entire_photo_required: Optional[bool]=None) -> None:
        """
        List of files for which thumbnails are to be generated.
        All files  are assumed to have the same scan id.
        :param scan_id: id of the scan
        :param rpd_files: files from which to extract thumbnails
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
        :param frontend_port: port to use to send to load balancer's
         front end
        :param log_gphoto2: if True, log libgphoto2 logging messages
        :param camera: If the thumbnails are being downloaded from a
         camera, this is the name of the camera, else None
        :param port: If the thumbnails are being downloaded from a
         camera, this is the port of the camera, else None
        :param entire_video_required: if the entire video is required
         to extract the thumbnail
        :param entire_photo_required: if the entire photo is required
         to extract the thumbnail
        """

        self.rpd_files = rpd_files
        self.scan_id = scan_id
        self.name = name
        self.proximity_seconds = proximity_seconds
        self.cache_dirs = cache_dirs
        self.need_photo_cache_dir = need_photo_cache_dir
        self.need_video_cache_dir = need_video_cache_dir
        self.frontend_port = frontend_port
        if camera is not None:
            assert port is not None
            assert entire_video_required is not None
        self.camera = camera
        self.port = port
        self.log_gphoto2 = log_gphoto2
        self.entire_video_required = entire_video_required
        self.entire_photo_required = entire_photo_required


class GenerateThumbnailsResults:
    def __init__(self, rpd_file: Optional[RPDFile]=None,
                 thumbnail_bytes: Optional[bytes]=None,
                 scan_id: Optional[int]=None,
                 cache_dirs: Optional[CacheDirs]=None) -> None:
        self.rpd_file = rpd_file
        # If thumbnail_bytes is None, there is no thumbnail
        self.thumbnail_bytes = thumbnail_bytes
        self.scan_id = scan_id
        self.cache_dirs = cache_dirs


class ThumbnailExtractorArgument:
    def __init__(self, rpd_file: RPDFile,
                 task: ExtractionTask,
                 processing: Set[ExtractionProcessing],
                 full_file_name_to_work_on: str,
                 secondary_full_file_name: str,
                 exif_buffer: Optional[bytearray],
                 thumbnail_bytes: bytes,
                 use_thumbnail_cache: bool,
                 file_to_work_on_is_temporary: bool,
                 write_fdo_thumbnail: bool,
                 send_thumb_to_main: bool) -> None:
        self.rpd_file = rpd_file
        self.task = task
        self.processing = processing
        self.full_file_name_to_work_on = full_file_name_to_work_on
        self.secondary_full_file_name = secondary_full_file_name
        self.file_to_work_on_is_temporary = file_to_work_on_is_temporary
        self.exif_buffer = exif_buffer
        self.thumbnail_bytes = thumbnail_bytes
        self.use_thumbnail_cache = use_thumbnail_cache
        self.write_fdo_thumbnail = write_fdo_thumbnail
        self.send_thumb_to_main = send_thumb_to_main


class RenameMoveFileManager(PushPullDaemonManager):
    """
    Manages the single instance daemon process that renames and moves
    files that have just been downloaded
    """

    message = pyqtSignal(bool, RPDFile, int)
    sequencesUpdate = pyqtSignal(int, list)
    renameProblems = pyqtSignal('PyQt_PyObject')

    def __init__(self, logging_port: int) -> None:
        super().__init__(logging_port=logging_port, thread_name=ThreadNames.rename)
        self._process_name = 'Rename and Move File Manager'
        self._process_to_run = 'renameandmovefile.py'

    def process_sink_data(self):
        data = pickle.loads(self.content)  # type: RenameAndMoveFileResults
        if data.move_succeeded is not None:

            self.message.emit(data.move_succeeded, data.rpd_file, data.download_count)

        elif data.problems is not None:
            self.renameProblems.emit(data.problems)
        else:
            assert data.stored_sequence_no is not None
            assert data.downloads_today is not None
            assert isinstance(data.downloads_today, list)
            self.sequencesUpdate.emit(data.stored_sequence_no, data.downloads_today)


class ThumbnailDaemonManager(PushPullDaemonManager):
    """
    Manages the process that extracts thumbnails after the file
    has already been downloaded and that writes FreeDesktop.org
    thumbnails. Not to be confused with ThumbnailManagerPara, which
    manages thumbnailing using processes that run in parallel,
    one for each device.
    """

    message = pyqtSignal(RPDFile, QPixmap)

    def __init__(self, logging_port: int) -> None:
        super().__init__(logging_port=logging_port, thread_name=ThreadNames.thumbnail_daemon)
        self._process_name = 'Thumbnail Daemon Manager'
        self._process_to_run = 'thumbnaildaemon.py'

    def process_sink_data(self) -> None:
        data = pickle.loads(self.content) # type: GenerateThumbnailsResults
        if data.thumbnail_bytes is None:
            thumbnail = QPixmap()
        else:
            thumbnail = QImage.fromData(data.thumbnail_bytes)
            if thumbnail.isNull():
                thumbnail = QPixmap()
            else:
                thumbnail = QPixmap.fromImage(thumbnail)
        self.message.emit(data.rpd_file, thumbnail)


class OffloadManager(PushPullDaemonManager):
    """
    Handles tasks best run in a separate process
    """

    message = pyqtSignal(TemporalProximityGroups)
    downloadFolders = pyqtSignal(FoldersPreview)

    def __init__(self, logging_port: int) -> None:
        super().__init__(logging_port=logging_port, thread_name=ThreadNames.offload)
        self._process_name = 'Offload Manager'
        self._process_to_run = 'offload.py'

    def process_sink_data(self) -> None:
        data = pickle.loads(self.content)  # type: OffloadResults
        if data.proximity_groups is not None:
            self.message.emit(data.proximity_groups)
        elif data.folders_preview is not None:
            self.downloadFolders.emit(data.folders_preview)


class ScanManager(PublishPullPipelineManager):
    """
    Handles the processes that scan devices (cameras, external devices,
    this computer path)
    """
    scannedFiles = pyqtSignal(
        'PyQt_PyObject', 'PyQt_PyObject', FileTypeCounter, 'PyQt_PyObject', bool, bool
    )
    deviceError = pyqtSignal(int, CameraErrorCode)
    deviceDetails = pyqtSignal(int, 'PyQt_PyObject', 'PyQt_PyObject', str)
    scanProblems = pyqtSignal(int, 'PyQt_PyObject')
    fatalError = pyqtSignal(int)

    def __init__(self, logging_port: int) -> None:
        super().__init__(logging_port=logging_port, thread_name=ThreadNames.scan)
        self._process_name = 'Scan Manager'
        self._process_to_run = 'scan.py'

    def process_sink_data(self) -> None:
        data = pickle.loads(self.content)  # type: ScanResults
        if data.rpd_files is not None:
            assert data.file_type_counter
            assert data.file_size_sum
            assert data.entire_video_required is not None
            assert  data.entire_photo_required is not None
            self.scannedFiles.emit(
                data.rpd_files,
                (data.sample_photo, data.sample_video),
                data.file_type_counter,
                data.file_size_sum,
                data.entire_video_required,
                data.entire_photo_required
            )
        else:
            assert data.scan_id is not None
            if data.error_code is not None:
                self.deviceError.emit(data.scan_id, data.error_code)
            elif data.optimal_display_name is not None:
                self.deviceDetails.emit(
                    data.scan_id, data.storage_space, data.storage_descriptions,
                    data.optimal_display_name
                )
            elif data.problems is not None:
                self.scanProblems.emit(data.scan_id, data.problems)
            else:
                assert data.fatal_error
                self.fatalError.emit(data.scan_id)


class BackupManager(PublishPullPipelineManager):
    """
    Each backup "device" (it could be an external drive, or a user-
    specified path on the local file system) has associated with it one
    worker process. For example if photos and videos are both being
    backed up to the same external hard drive, one worker process
    handles both the photos and the videos. However if photos are being
    backed up to one drive, and videos to another, there would be a
    worker process for each drive (2 in total).
    """
    message = pyqtSignal(int, bool, bool, RPDFile, str, 'PyQt_PyObject')
    bytesBackedUp = pyqtSignal('PyQt_PyObject', 'PyQt_PyObject')
    backupProblems = pyqtSignal(int, 'PyQt_PyObject')

    def __init__(self, logging_port: int) -> None:
        super().__init__(logging_port=logging_port, thread_name=ThreadNames.backup)
        self._process_name = 'Backup Manager'
        self._process_to_run = 'backupfile.py'

    def process_sink_data(self) -> None:
        data = pickle.loads(self.content) # type: BackupResults
        if data.total_downloaded is not None:
            assert data.scan_id is not None
            assert data.chunk_downloaded >= 0
            assert data.total_downloaded >= 0
            self.bytesBackedUp.emit(data.scan_id, data.chunk_downloaded)
        elif data.backup_succeeded is not None:
            assert data.do_backup is not None
            assert data.rpd_file is not None
            self.message.emit(
                data.device_id, data.backup_succeeded, data.do_backup, data.rpd_file,
                data.backup_full_file_name, data.mdata_exceptions
            )
        else:
            assert data.problems is not None
            self.backupProblems.emit(data.device_id, data.problems)


class CopyFilesManager(PublishPullPipelineManager):
    """
    Manage the processes that copy files from devices to the computer
    during the download process
    """

    message = pyqtSignal(bool, RPDFile, int, 'PyQt_PyObject')
    tempDirs = pyqtSignal(int, str,str)
    bytesDownloaded = pyqtSignal(int, 'PyQt_PyObject', 'PyQt_PyObject')
    copyProblems = pyqtSignal(int, 'PyQt_PyObject')

    def __init__(self, logging_port: int) -> None:
        super().__init__(logging_port=logging_port, thread_name=ThreadNames.copy)
        self._process_name = 'Copy Files Manager'
        self._process_to_run = 'copyfiles.py'

    def process_sink_data(self) -> None:
        data = pickle.loads(self.content) # type: CopyFilesResults
        if data.total_downloaded is not None:
            assert data.scan_id is not None
            if data.chunk_downloaded < 0:
                logging.critical("Chunk downloaded is less than zero: %s", data.chunk_downloaded)
            if data.total_downloaded < 0:
                logging.critical("Chunk downloaded is less than zero: %s", data.total_downloaded)

            self.bytesDownloaded.emit(data.scan_id, data.total_downloaded, data.chunk_downloaded)

        elif data.copy_succeeded is not None:
            assert data.rpd_file is not None
            assert data.download_count is not None
            self.message.emit(
                data.copy_succeeded, data.rpd_file, data.download_count, data.mdata_exceptions
            )

        elif data.problems is not None:
            self.copyProblems.emit(data.scan_id, data.problems)

        else:
            assert (data.photo_temp_dir is not None and
                    data.video_temp_dir is not None)
            assert data.scan_id is not None
            self.tempDirs.emit(data.scan_id, data.photo_temp_dir, data.video_temp_dir)