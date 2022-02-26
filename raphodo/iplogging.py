# Copyright (C) 2016-2021 Damon Lynch <damonlynch@gmail.com>

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

"""
Specify logging setup.

Log all messages to file log
Log messages at user specified level to console
"""

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2016-2021, Damon Lynch"

import logging
from logging.handlers import QueueHandler, RotatingFileHandler
import pickle
import gzip
import os
from typing import Optional

try:
    import colorlog

    use_colorlog = True
except ImportError:
    use_colorlog = False

from raphodo.constants import logfile_name
from raphodo.storage.storage import get_program_logging_directory

logging_format = "%(levelname)s: %(message)s"
colored_logging_format = "%(log_color)s%(levelname)-8s%(reset)s %(message)s"
log_colors = {
    "DEBUG": "cyan",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "red,bg_white",
}

logging_date_format = "%Y-%m-%d %H:%M:%S"
file_logging_format = "%(asctime)s %(levelname)s %(filename)s %(lineno)d: %(message)s"


class ZeroMQSocketHandler(QueueHandler):
    def enqueue(self, record):
        data = pickle.dumps(record.__dict__)
        self.queue.send(data)


class RotatingGzipFileHandler(RotatingFileHandler):
    def rotation_filename(self, name):
        return name + ".gz"

    def rotate(self, source, dest):
        with open(source, "rb") as sf:
            with gzip.open(dest, "wb") as df:
                df.writelines(sf)
                os.remove(source)


def full_log_file_path():
    log_file_path = get_program_logging_directory(create_if_not_exist=True)
    if log_file_path is not None:
        log_file = os.path.join(log_file_path, logfile_name)
    else:
        # Problem: for some reason cannot create log file in standard location,
        # so create it in the home directory
        log_file = os.path.join(os.path.expanduser("~"), logfile_name)
    return log_file


def setup_main_process_logging(logging_level: int) -> logging.Logger:
    """
    Setup logging at the module level

    :param log_file_path: path where log file should be stored
    :param logging_level: logging module's logging level for console output
    :return: default logging object
    """

    log_file = full_log_file_path()
    logger = logging.getLogger()
    max_bytes = 1024 * 1024  # 1 MB
    filehandler = RotatingGzipFileHandler(log_file, maxBytes=max_bytes, backupCount=10)
    filehandler.setLevel(logging.DEBUG)
    filehandler.setFormatter(
        logging.Formatter(file_logging_format, logging_date_format)
    )
    logger.addHandler(filehandler)
    logger.setLevel(logging.DEBUG)

    consolehandler = logging.StreamHandler()
    consolehandler.set_name("console")
    if not use_colorlog:
        consolehandler.setFormatter(logging.Formatter(logging_format))
    else:
        consolehandler.setFormatter(
            colorlog.ColoredFormatter(fmt=colored_logging_format, log_colors=log_colors)
        )
    consolehandler.setLevel(logging_level)
    logger.addHandler(consolehandler)
    return logger
