#!/usr/bin/env python3

# Copyright (C) 2020-2024 Damon Lynch <damonlynch@gmail.com>

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

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2020-2024, Damon Lynch"
__title__ = __file__
__description__ = "Extract and give nice names to Rapid Photo Downloader log files"

import argparse
import datetime
import glob
import gzip
import os
import re
import sys
import tarfile

import icecream


def parser_options(formatter_class=argparse.HelpFormatter):
    parser = argparse.ArgumentParser(
        prog=__title__, description=__description__, formatter_class=formatter_class
    )

    parser.add_argument(
        "path", help="path to log file directory or tar file containg log files"
    )

    return parser


if __name__ == "__main__":
    icecream.install()

    parser = parser_options()
    args = parser.parse_args()

    # home = os.path.expanduser('~')

    path = os.path.abspath(args.path)

    if path.endswith(".tar") or path.endswith(".tar.gz"):
        tarfile_path = path
        tar = tarfile.open(path)
        dt_re = re.search(r"(\d[\d\-]+)", os.path.split(path)[1])
        if dt_re:
            tar_datetime = dt_re.group(1)
        else:
            tar_datetime = datetime.datetime.now().strftime("%Y%m%d")

        path = os.path.split(path)[0]
        i = 0
        while os.path.isdir(
            os.path.join(path, "{}{}".format(tar_datetime, "" if not i else f"-{i}"))
        ):
            i += 1

        tar_path = os.path.join(
            path, "{}{}".format(tar_datetime, "" if not i else f"-{i}")
        )
        os.mkdir(tar_path)
        tar.extractall(path=tar_path)
        path = tar_path
        try:
            os.remove(tarfile_path)
        except OSError as e:
            if e.errno == 26:
                print("Warning: could not remove tar file because it is being used")
            else:
                raise

    standard_name = "rapid-photo-downloader.log"
    standard_file = os.path.join(path, standard_name)
    zero_name = "rapid-photo-downloader.0.log"
    zero_file = os.path.join(path, zero_name)
    if os.path.isfile(standard_file):
        if os.path.isfile(zero_file):
            print(
                "rapid-photo-downloader.0.log already exists. Do not know what to do."
            )
            sys.exit(1)
        print(f"{standard_name} -> {zero_name}")
        os.rename(standard_file, zero_file)
    elif os.path.isfile(zero_file):
        print(f"{zero_name} -> {zero_name}")

    log_files = glob.glob(os.path.join(path, "*.log"))
    log_gzips = glob.glob(os.path.join(path, "*.log.*.gz"))

    max_identifier = None
    for log_file in log_files:
        identifier_re = re.search(r"\.([\d]+)\.log$", log_file)
        if identifier_re is not None:
            identifier = int(identifier_re.group(1))
            if max_identifier is None or identifier > max_identifier:
                max_identifier = identifier
    assert max_identifier >= 0

    counter = max_identifier

    for log_gzip in log_gzips:
        identifier_re = re.search(r"\.([\d]+)\.gz$", log_gzip)
        if identifier_re is not None:
            identifier = int(identifier_re.group(1)) + counter
            new_name = f"rapid-photo-downloader.{identifier}.log"
            new_log = os.path.join(path, new_name)
            if os.path.isfile(new_log):
                print(f"Error: {new_name} already exists")
            else:
                print(f"{os.path.split(log_gzip)[1]} -> {new_name}")
                with gzip.GzipFile(log_gzip, "rb") as f:
                    file_content = f.read()
                    with open(new_log, "wb") as w:
                        w.write(file_content)
                os.remove(log_gzip)
