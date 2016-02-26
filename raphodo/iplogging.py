# Copyright (C) 2016 Damon Lynch <damonlynch@gmail.com>

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

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2016, Damon Lynch"

import logging
from logging.handlers import QueueHandler
import pickle
import os
from typing import Optional

logging_format = '%(levelname)s: %(message)s'
logging_date_format = '%Y-%m-%d %H:%M:%S'
file_logging_format = '%(asctime)s %(levelname)s %(filename)s %(lineno)d: %(message)s'

class ZeroMQSocketHandler(QueueHandler):
    def enqueue(self, record):
        data = pickle.dumps(record.__dict__)
        self.queue.send(data)


def setup_main_process_logging(log_file_path: Optional[str], logging_level: int) -> logging.Logger:
    """
    Setup logging at the module level
    :param log_file_path: path where log file should be stored
    :param logging_level: logging module's logging level for console output
    :return: default logging object
    """
    if log_file_path is not None:
        log_file = os.path.join(log_file_path, 'rapid-photo-downloader.log')
    else:
        # Problem: for some reason cannot create log file in standard location,
        # so create it in the home directory
        log_file = os.path.join(os.path.expanduser('~'), 'rapid-photo-downloader.log')
    logger = logging.getLogger()
    filehandler = logging.FileHandler(log_file)
    filehandler.setLevel(logging.DEBUG)
    filehandler.setFormatter(logging.Formatter(file_logging_format, logging_date_format))
    logger.addHandler(filehandler)
    logger.setLevel(logging.DEBUG)
    consolehandler = logging.StreamHandler()
    consolehandler.setLevel(logging_level)
    consolehandler.setFormatter(logging.Formatter(logging_format))
    logger.addHandler(consolehandler)
    return logger



