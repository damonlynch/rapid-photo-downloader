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

import argparse
import sys
import logging
import pickle
import os
import subprocess
import shlex
import time
from collections import deque
from typing import Optional, Set, List, Dict

from psutil import (Process, wait_procs, pid_exists)
from sortedcontainers import SortedListWithKey

from PyQt5.QtCore import (pyqtSignal, QObject)
from PyQt5.QtGui import QPixmap

import zmq
from zmq.eventloop.ioloop import IOLoop
from zmq.eventloop.zmqstream import ZMQStream

from rpdfile import (RPDFile, FileTypeCounter, FileSizeSum)
from devices import Device
from preferences import ScanPreferences
from utilities import CacheDirs
from constants import (RenameAndMoveStatus, ExtractionTask, ExtractionProcessing,
                       CameraErrorCode, FileType)
from proximity import TemporalProximityGroups
from storage import StorageSpace
from viewutils import SortedListItem


def get_logging_level(level: str) -> int:
    """
    Convert command line version of logging level to int.

    Primary purpose is to catch exceptions, as conceivably the
    command line could contain anything.

    :param level: logging level directly from command line arg
    :return: int of level, else on failure logging.DEBUG
    """

    try:
        return int(level)
    except ValueError:
        return logging.DEBUG

def make_filter_from_worker_id(worker_id) -> bytes:
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

class ProcessManager:
    def __init__(self, logging_level: int) -> None:
        super().__init__()

        self.processes = {}
        self._process_to_run = '' # Implement in subclass
        self.logging_level = logging_level

        # Monitor which workers we have running
        self.workers = []  # type: List[int]

    def _get_cmd(self) -> str:
        return os.path.join(os.path.dirname(__file__), self._process_to_run)

    def _get_command_line(self, worker_id: int) -> str:
        """
        Implement in sublcass
        """
        return ''

    def add_worker(self, worker_id: int) -> None:

        command_line = self._get_command_line(worker_id)
        args = shlex.split(command_line)

        # run command immediately, without waiting a reply
        try:
            pid = subprocess.Popen(args).pid
        except OSError as e:
            logging.critical("Failed to start process: %s", command_line)
            logging.critical('OSError [Errno %s]: %s', e.errno, e.strerror)
            if e.errno == 8:
                logging.critical("Script shebang line might be malformed or missing: %s",
                                 self._get_cmd())
            sys.exit(1)
        # logging.debug("Started '%s' with pid %s", command_line, pid)

        # Add to list of running workers
        self.workers.append(worker_id)
        self.processes[worker_id] = Process(pid)

    def forcefully_terminate(self) -> None:
        """Forcefully terminate any running child processes."""

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
                    logging.debug("Process %s (%s) has %s status", p.name(), p.pid, p.status())
                    try:
                        p.terminate()
                        terminated.append(p)
                    except:
                        logging.error("Terminating process %s with pid %s failed", p.name(), p.pid)
        if terminated:
            gone, alive = wait_procs(terminated, timeout=2, callback=on_terminate)
            for p in alive:
                logging.debug("Killing process %s", p)
                try:
                    p.kill()
                except:
                    logging.debug("Failed to kill process %s with pid %s", p.name(), p.pid)

    def process_alive(self, worker_id: int) -> bool:
        """
        Process IDs are reused by the system. Check to make sure
        a new process has not been created with the same process id.

        :param worker_id: the process to check
        :return True if the process is the same, False otherwise
        """
        if pid_exists(self.processes[worker_id].pid):
            return Process(self.processes[worker_id].pid) == self.processes[worker_id]
        return False

class PullPipelineManager(ProcessManager, QObject):
    """
    Base class from which more specialized 0MQ classes are derived.

    Receives data into its sink via a ZMQ PULL socket, but does not
    specify how workers should be sent data.

    Outputs signals using Qt.
    """

    message = pyqtSignal(str) # Derived class will change this
    workerFinished = pyqtSignal(int)

    def __init__(self, context: zmq.Context, logging_level: int):
        super().__init__(logging_level)

        # Subclasses must define the type of port they need to send messages
        self.ventilator_socket = None
        self.ventilator_port = None

        # Sink socket to receive results of the workers
        self.receiver_socket = context.socket(zmq.PULL)
        self.receiver_port = self.receiver_socket.bind_to_random_port('tcp://*')

        # Socket to communicate directly with the sink, bypassing the workers
        self.terminate_socket = context.socket(zmq.PUSH)
        self.terminate_socket.connect("tcp://localhost:{}".format(self.receiver_port))

        self.terminating = False

    def run_sink(self) -> None:
        logging.debug("Running sink for %s", self._process_name)
        while True:
            try:
                # Receive messages from the workers
                # (or the terminate socket)
                worker_id, directive, content = self.receiver_socket.recv_multipart()
            except KeyboardInterrupt:
                break
            if directive == b'cmd':
                command = content
                assert command in [b"STOPPED", b"FINISHED", b"KILL"]
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

    def process_sink_data(self) -> None:
        data = pickle.loads(self.content)
        self.message.emit(data)

    def terminate_sink(self) -> None:
        self.terminate_socket.send_multipart([b'0', b'cmd', b'KILL'])

    def _get_ventilator_start_message(self, worker_id: int) -> list:
        return [make_filter_from_worker_id(worker_id), b'cmd', b'START']

    def send_message_to_worker(self, data, worker_id:int = None):
        data = pickle.dumps(data, pickle.HIGHEST_PROTOCOL)
        if worker_id is not None:
            message = [make_filter_from_worker_id(worker_id), b'data', data]
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
    def __init__(self, no_workers: int, backend_port: int, sink_port: int,
                 logging_level: int) -> None:
        super().__init__(logging_level)
        self.no_workers = no_workers
        self.backend_port = backend_port
        self.sink_port = sink_port

    def _get_command_line(self, worker_id: int) -> str:
        cmd = self._get_cmd()

        return '{} --request {} --send {} --identity {} --logginglevel {}'.format(
                        cmd,
                        self.backend_port,
                        self.sink_port,
                        worker_id,
                        self.logging_level)

    def start_workers(self) -> None:
        for worker_id in range(self.no_workers):
            self.add_worker(worker_id)

class LRUQueue:
    """LRUQueue class using ZMQStream/IOLoop for event dispatching"""

    def __init__(self, backend_socket: zmq.Socket,
                 frontend_socket: zmq.Socket,
                 controller_socket: zmq.Socket,
                 worker_type: str) -> None:

        self.worker_type = worker_type
        self.workers = deque()
        self.terminating = False
        self.terminating_workers = set()

        self.backend = ZMQStream(backend_socket)
        self.frontend = ZMQStream(frontend_socket)
        self.controller = ZMQStream(controller_socket)
        self.backend.on_recv(self.handle_backend)
        self.controller.on_recv(self.handle_controller)

        self.loop = IOLoop.instance()

    def handle_controller(self, msg):
        self.terminating = True
        logging.debug("%s load balancer requesting %s workers to stop", self.worker_type,
                      len(self.workers))

        while len(self.workers):
            worker_identity = self.workers.popleft()
            self.backend.send_multipart([worker_identity, b'', b'cmd', b'STOP'])
            self.terminating_workers.add(worker_identity)

        self.loop.add_timeout(time.time()+3, self.loop.stop)

    def handle_backend(self, msg):
        # Queue worker address for LRU routing
        worker_identity, empty, client_addr = msg[:3]

        # add worker back to the list of workers
        self.workers.append(worker_identity)

        # Second frame is empty
        assert empty == b''

        if msg[-1] == b'STOPPED' and self.terminating:
            self.terminating_workers.remove(worker_identity)
            if len(self.terminating_workers) == 0:
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
        self.parser.add_argument("--logginglevel", required=True)

        args = self.parser.parse_args()
        self.controller_port = args.controller

        logging_level = get_logging_level(args.logginglevel)

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

        logging.debug("{} worker waiting to be notified how many workers to initialize...".format(
            worker_type))
        no_workers = int(reply.recv())
        logging.debug("...{} worker will use {} workers".format(worker_type, no_workers))
        reply.send(str(frontend_port).encode())

        self.process_manager = process_manager(no_workers, backend_port, sink_port, logging_level)
        self.process_manager.start_workers()

        # create queue with the sockets
        queue = LRUQueue(backend, frontend, controller, worker_type)

        # start reactor, which is an infinite loop
        IOLoop.instance().start()

        # Finished infinite loop: do some housekeeping
        self.process_manager.forcefully_terminate()

        frontend.close()
        backend.close()


class LoadBalancerManager(ProcessManager, QObject):
    load_balancer_started = pyqtSignal(int)
    def __init__(self, context: zmq.Context,
                 no_workers: int,
                 sink_port: int,
                 logging_level: int):
        super().__init__(logging_level)

        self.controller_socket = context.socket(zmq.PUSH)
        self.controller_port = self.controller_socket.bind_to_random_port('tcp://*')

        self.requester = context.socket(zmq.REQ)
        self.requester_port = self.requester.bind_to_random_port('tcp://*')
        self.no_workers = no_workers
        self.sink_port = sink_port

    def start_load_balancer(self) -> None:
        worker_id = 0
        self.add_worker(worker_id)
        self.requester.send(str(self.no_workers).encode())
        self.frontend_port = int(self.requester.recv())
        # logging.debug("{} front end port: {}".format(self._process_name, self.frontend_port))
        self.load_balancer_started.emit(self.frontend_port)

    def stop(self):
        self.controller_socket.send(b'STOP')

    def _get_command_line(self, worker_id: int) -> str:
        cmd = self._get_cmd()

        return '{} --receive {} --send {} --controller {} --logginglevel {}'.format(
                        cmd,
                        self.requester_port,
                        self.sink_port,
                        self.controller_port,
                        self.logging_level)

DAEMON_WORKER_ID = 0


class PushPullDaemonManager(PullPipelineManager):
    """
    Manage a single isntance daemon worker process that waits to work on data
    issued by this manager. The data to be worked on is issued in sequence,
    one after the other.

    Because there is on a single daemon process, a Push-Pull model is most
    suitable for sending the data.
    """

    def __init__(self, context: zmq.Context, logging_level: int) -> None:
        super().__init__(context, logging_level)

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
                    self._process_name)
                self.terminate_sink()
        else:
            # The process may have crashed. Stop the sink.
            self.terminate_sink()

    def _get_command_line(self, worker_id: int) -> str:
        cmd = self._get_cmd()
        return '{} --receive {} --send {} --logginglevel {' \
               '}'.format(
                        cmd,
                        self.ventilator_port,
                        self.receiver_port,
                        self.logging_level)

    def _get_ventilator_start_message(self, worker_id: int) -> str:
        return [b'cmd', b'START']

    def start(self) -> None:
        self.add_worker(worker_id=DAEMON_WORKER_ID)

class PublishPullPipelineManager(PullPipelineManager):
    """
    Manage a collection of worker processes that wait to work on data
    issued by this manager. The data to be worked on is issued in sequence,
    one after the other, either once, or many times.

    Because there are multiple worker process, a Publish-Subscribe model is
    most suitable for sending data to workers.
    """
    def __init__(self, context: zmq.Context, logging_level: int) -> None:
        super().__init__(context, logging_level)

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

    def stop_worker(self, worker_id: int) -> None:
        """
        Permanently stop one worker
        """
        assert worker_id in self.workers
        message = [make_filter_from_worker_id(worker_id),b'STOP']
        self.controller_socket.send_multipart(message)
        message = [make_filter_from_worker_id(worker_id),b'cmd', b'STOP']
        self.ventilator_socket.send_multipart(message)

    def start_worker(self, worker_id: int, process_arguments) -> None:

        self.add_worker(worker_id)

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
        self.send_message_to_worker(process_arguments, worker_id)

    def _get_command_line(self, worker_id: int) -> str:
        cmd = self._get_cmd()

        return '{} --receive {} --send {} --controller {} --syncclient {} ' \
               '--filter {} --logginglevel {}'.format(
                        cmd,
                        self.ventilator_port,
                        self.receiver_port,
                        self.controller_port,
                        self.sync_service_port,
                        worker_id,
                        self.logging_level)

    def __len__(self) -> int:
        return len(self.workers)

    def __contains__(self, item) -> bool:
        return item in self.workers

    def pause(self) -> None:
        for worker_id in self.workers:
            message = [make_filter_from_worker_id(worker_id), b'PAUSE']
            self.controller_socket.send_multipart(message)

    def resume(self, worker_id: Optional[int]=None) -> None:
        if worker_id is not None:
            workers = [worker_id]
        else:
            workers = self.workers
        for worker_id in workers:
            message = [make_filter_from_worker_id(worker_id), b'RESUME']
            self.controller_socket.send_multipart(message)


class WorkerProcess():
    def __init__(self, worker_type: str) -> None:
        super().__init__()
        self.parser = argparse.ArgumentParser()
        self.parser.add_argument("--receive", required=True)
        self.parser.add_argument("--send", required=True)
        self.parser.add_argument("--logginglevel", required=True)

    def cleanup_pre_stop(self) -> None:
        """
        Operations to run if process is stopped.

        Implement in child class if needed.
        """

        pass

    def send_message_to_sink(self) -> None:

        self.sender.send_multipart([self.worker_id, b'data',
                                    self.content])

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

        self.logging_level = get_logging_level(args.logginglevel)

        context = zmq.Context()
        # Socket to send messages along the pipe to
        self.sender = context.socket(zmq.PUSH)
        self.sender.set_hwm(10)
        self.sender.connect("tcp://localhost:{}".format(args.send))

        self.receiver = context.socket(zmq.PULL)
        self.receiver.connect("tcp://localhost:{}".format(args.receive))

    def run(self) -> None:
        pass

    def check_for_command(self, directive: bytes, content: bytes) -> None:
        if directive == b'cmd':
            assert content == b'STOP'
            self.cleanup_pre_stop()
            # signal to sink that we've terminated before finishing
            self.sender.send_multipart([make_filter_from_worker_id(
                DAEMON_WORKER_ID), b'cmd', b'STOPPED'])
            sys.exit(0)

    def send_message_to_sink(self) -> None:
        # Must use a dummy value for the worker id, as there is only ever one
        # instance.
        self.sender.send_multipart([make_filter_from_worker_id(
            DAEMON_WORKER_ID), b'data', self.content])


class WorkerInPublishPullPipeline(WorkerProcess):
    """
    Worker counterpart to PublishPullPipelineManager; multiple instance.
    """
    def __init__(self, worker_type: str) -> None:
        super().__init__(worker_type)
        self.add_args()

        args = self.parser.parse_args()
        self.logging_level = get_logging_level(args.logginglevel)

        subscription_filter = self.worker_id = args.filter.encode()
        self.context = zmq.Context()

        self.setup_sockets(args, subscription_filter)

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
            assert content == b'STOP'
            self.cleanup_pre_stop()
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
            # before finishing, signal to sink that we've terminated
            self.sender.send_multipart([self.worker_id, b'cmd', b'STOPPED'])
            sys.exit(0)

    def send_finished_command(self) -> None:
        self.sender.send_multipart([self.worker_id, b'cmd', b'FINISHED'])


class LoadBalancerWorker:
    def __init__(self, worker_type: str) -> None:
        super().__init__()
        self.parser = argparse.ArgumentParser()
        self.parser.add_argument("--request", required=True)
        self.parser.add_argument("--send", required=True)
        self.parser.add_argument("--identity", required=True)
        self.parser.add_argument("--logginglevel", required=True)

        args = self.parser.parse_args()

        self.logging_level = get_logging_level(args.logginglevel)

        self.context = zmq.Context()

        self.requester = self.context.socket(zmq.REQ)
        self.requester.identity = create_identity(worker_type, args.identity)
        self.requester.connect("tcp://localhost:{}".format(args.request))

        self.sender = self.context.socket(zmq.PUSH)
        self.sender.connect("tcp://localhost:{}".format(args.send))

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

    def check_for_command(self, directive: bytes, content: bytes):
        if directive == b'cmd':
            assert content == b'STOP'
            self.cleanup_pre_stop()
            identity = self.requester.identity.decode()
            # signal to load balancer that we've terminated before finishing
            self.requester.send_multipart([b'', b'', b'STOPPED'])
            self.requester.close()
            self.sender.close()
            self.context.term()
            logging.debug("%s stopped", identity)
            sys.exit(0)


class ScanArguments:
    """
    Pass arguments to the scan process
    """
    def __init__(self, scan_preferences: ScanPreferences,
                 device: Device, ignore_other_types: bool) -> None:
        self.scan_preferences = scan_preferences
        self.device = device
        self.ignore_other_types = ignore_other_types


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
                 storage_space: Optional[List[StorageSpace]]=None) -> None:
        self.rpd_files = rpd_files
        self.file_type_counter = file_type_counter
        self.file_size_sum = file_size_sum
        self.error_code = error_code
        self.scan_id = scan_id
        self.optimal_display_name = optimal_display_name
        self.storage_space = storage_space


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
                  generate_thumbnails: bool) -> None:
        """
        :type files: List(rpd_file)
        """
        self.scan_id = scan_id
        self.device = device
        self.photo_download_folder = photo_download_folder
        self.video_download_folder = video_download_folder
        self.files = files
        self.generate_thumbnails = generate_thumbnails
        self.verify_file = verify_file

class CopyFilesResults:
    """
    Receive results from the copyfiles process
    """
    def __init__(self, scan_id: int=None,
                 photo_temp_dir: str=None,
                 video_temp_dir: str=None,
                 total_downloaded: int=None,
                 chunk_downloaded: int=None,
                 copy_succeeded: bool=None,
                 rpd_file: RPDFile=None,
                 download_count: int=None) -> None:
        self.scan_id = scan_id

        self.photo_temp_dir = photo_temp_dir
        self.video_temp_dir = video_temp_dir

        # if total_downloaded is not None:
        #     assert total_downloaded >= 0
        self.total_downloaded = total_downloaded
        self.chunk_downloaded = chunk_downloaded

        self.copy_succeeded = copy_succeeded
        self.rpd_file = rpd_file
        self.download_count = download_count


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
                 png_data: bytes=None,
                 stored_sequence_no: int=None,
                 downloads_today: List[str]=None) -> None:
        self.move_succeeded = move_succeeded
        self.rpd_file = rpd_file
        self.download_count = download_count
        self.png_data = png_data
        self.stored_sequence_no = stored_sequence_no
        self.downloads_today = downloads_today


class OffloadData:
    def __init__(self, thumbnail_rows: Optional[List[SortedListItem]]=None,
                 thumbnail_types: Optional[List[FileType]]=None,
                 proximity_seconds: int=None) -> None:
        self.thumbnail_rows = thumbnail_rows
        self.thumbnail_types = thumbnail_types
        self.proximity_seconds = proximity_seconds


class OffloadResults:
    def __init__(self, proximity_groups: Optional[TemporalProximityGroups]=None) -> None:
        self.proximity_groups = proximity_groups


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
    def __init__(self, rpd_file: RPDFile, move_succeeded: bool,
                 do_backup: bool, path_suffix: str,
                 backup_duplicate_overwrite: bool, verify_file: bool,
                 download_count: int, save_fdo_thumbnail: int) -> None:
        self.rpd_file = rpd_file
        self.move_succeeded = move_succeeded
        self.do_backup = do_backup
        self.path_suffix = path_suffix
        self.backup_duplicate_overwrite = backup_duplicate_overwrite
        self.verify_file = verify_file
        self.download_count = download_count
        self.save_fdo_thumbnail = save_fdo_thumbnail

class BackupResults:
    def __init__(self, scan_id: int, device_id: int,
                 total_downloaded=None, chunk_downloaded=None,
                 backup_succeeded: bool=None, do_backup: bool=None, rpd_file:
                 RPDFile=None) -> None:
        self.scan_id = scan_id
        self.device_id = device_id
        self.total_downloaded = total_downloaded
        self.chunk_downloaded = chunk_downloaded
        self.backup_succeeded = backup_succeeded
        self.do_backup = do_backup
        self.rpd_file = rpd_file


class GenerateThumbnailsArguments:
    def __init__(self, scan_id: int,
                 rpd_files: List[RPDFile],
                 name: str,
                 cache_dirs: CacheDirs,
                 frontend_port: int,
                 camera: Optional[str]=None,
                 port: Optional[str]=None) -> None:
        """
        List of files for which thumbnails are to be generated.
        All files  are assumed to have the same scan id.
        :param scan_id: id of the scan
        :param rpd_files: files from which to extract thumbnails
        :param name: name of the device
        :param cache_dirs: the location where the cache directories
         should be created
        :param frontend_port: port to use to send to load balancer's
         front end
        :param camera: If the thumbnails are being downloaded from a
         camera, this is the name of the camera, else None
        :param port: If the thumbnails are being downloaded from a
         camera, this is the port of the camera, else None
        """
        self.rpd_files = rpd_files
        self.scan_id = scan_id
        self.name = name
        self.cache_dirs = cache_dirs
        self.frontend_port = frontend_port
        if camera is not None:
            assert port is not None
        self.camera = camera
        self.port = port


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
                 exif_buffer: bytearray,
                 thumbnail_bytes: bytes,
                 use_thumbnail_cache: bool) -> None:
        self.rpd_file = rpd_file
        self.task = task
        self.processing = processing
        self.full_file_name_to_work_on = full_file_name_to_work_on
        self.exif_buffer = exif_buffer
        self.thumbnail_bytes = thumbnail_bytes
        self.use_thumbnail_cache = use_thumbnail_cache
