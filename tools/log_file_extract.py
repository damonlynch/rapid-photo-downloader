#!/usr/bin/env python3

# Copyright (C) 2020 Damon Lynch <damonlynch@gmail.com>

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
# along with Rapid Photo Downloader. If not,
# see <http://www.gnu.org/licenses/>.


"""
Extract Rapid Photo Downloader log files
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2020, Damon Lynch"
__title__ = __file__
__description__ = 'Extract and give nice names to Rapid Photo Downloader log files'

import gzip
import sys
import re
import glob
import os
import argparse


def parser_options(formatter_class=argparse.HelpFormatter):
    parser = argparse.ArgumentParser(
        prog=__title__,
        description=__description__,
        formatter_class=formatter_class
    )

    parser.add_argument(
        'path', help="path to log file directory"
    )

    return parser


if __name__ == '__main__':
    parser = parser_options()
    args = parser.parse_args()

    home = os.path.expanduser('~')

    path = os.path.abspath(args.path)

    standard_name = 'rapid-photo-downloader.log'
    standard_file = os.path.join(path, standard_name)
    zero_name = 'rapid-photo-downloader.0.log'
    zero_file = os.path.join(path, zero_name)
    if os.path.isfile(standard_file):
        if os.path.isfile(zero_file):
            print("rapid-photo-downloader.0.log already exists. Do not know what to do.")
            sys.exit(1)
        print("{} -> {}".format(standard_name, zero_name))
        os.rename(standard_file, zero_file)

    log_files = glob.glob(os.path.join(path, '*.log'))
    log_gzips = glob.glob(os.path.join(path, '*.log.*.gz'))

    max_identifier = None
    for log_file in log_files:
        identifier_re = re.search(r'\.([\d]+)\.log$', log_file)
        if identifier_re is not None:
            identifier = int(identifier_re.group(1))
            if max_identifier is None or identifier > max_identifier:
                max_identifier = identifier
    assert max_identifier >= 0

    counter = max_identifier

    for log_gzip in log_gzips:
        identifier_re = re.search(r'\.([\d]+)\.gz$', log_gzip)
        if identifier_re is not None:
            identifier = int(identifier_re.group(1)) + counter
            new_name = 'rapid-photo-downloader.{}.log'.format(identifier)
            new_log = os.path.join(path, new_name)
            if os.path.isfile(new_log):
                print("Error: {} already exists".format(new_name))
            else:
                print("{} -> {}".format(os.path.split(log_gzip)[1], new_name))
                with gzip.GzipFile(log_gzip, 'rb') as f:
                    file_content = f.read()
                    with open(new_log, 'wb') as w:
                        w.write(file_content)
                os.remove(log_gzip)




