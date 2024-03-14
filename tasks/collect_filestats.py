# Copyright (C) 2017-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Gather the file stats for all the files in a directory"""


import argparse
import contextlib
import os
import pickle
import sys
from collections.abc import Iterator
from datetime import datetime


def parser_options(formatter_class=argparse.HelpFormatter) -> argparse.ArgumentParser:
    """
    Construct the command line arguments for the script

    :return: the parser
    """

    parser = argparse.ArgumentParser(
        formatter_class=formatter_class,
        description= (
            "Gather the file stats for all the files in a directory, and use them to "
            "apply their mtime and atime to the same tree of files on another "
            "computer"
        )
    )
    group = parser.add_mutually_exclusive_group()

    group.add_argument(
        "-c",
        "--collect",
        action="store_true",
        help="Collect the file stats and write them out to a new file",
    )
    group.add_argument(
        "-w",
        "--write",
        action="store",
        dest="stats",
        help="Write out the file stats to the directory of files using the stats file "
             "provided",
    )

    parser.add_argument(
        "directory", action="store", help="The directory to apply the operation to"
    )

    return parser


def walk_file_system(path_to_walk: str) -> Iterator[tuple[str, str]]:
    for dir_name, dir_list, file_list in os.walk(path_to_walk):
        for name in file_list:
            yield dir_name, name


def main():
    parser = parser_options()

    args = parser.parse_args()

    if not (args.collect or args.stats):
        print("Expected either the collect or write option. Exiting...")
        sys.exit(1)

    path_to_walk = os.path.realpath(args.directory)

    if args.collect:
        file_stats = dict()
        for dir_name, name in walk_file_system(path_to_walk):
            full_path = os.path.join(os.path.realpath(dir_name), name)
            path = full_path[len(path_to_walk) + 1 :]
            with contextlib.suppress(Exception):
                file_stats[path] = os.stat(full_path)

        suffix = path_to_walk.replace(os.sep, "-")
        filename = os.path.expanduser(
            "~/{}{}".format(datetime.now().strftime("%Y%m%d-%H%M%S"), suffix)
        )
        with open(filename, "wb") as stats:
            pickle.dump(file_stats, stats)

        print("Created file", filename)
    else:
        assert args.stats
        stat_file = os.path.realpath(args.stats)
        with open(stat_file, "rb") as stats:
            file_stats = pickle.load(stats)

        max_len = len(max(file_stats.keys(), key=len)) + 2
        format = "%Y-%m-%d %H:%M:%S"

        for dir_name, name in walk_file_system(path_to_walk):
            full_path = os.path.join(os.path.realpath(dir_name), name)
            path = full_path[len(path_to_walk) + 1 :]
            stats = file_stats.get(path)  # type: os.stat_result

            if stats:
                print(
                    "{:{}}{} {}".format(
                        path,
                        max_len + 2,
                        datetime.fromtimestamp(stats.st_mtime).strftime(format),
                        datetime.fromtimestamp(stats.st_atime).strftime(format),
                    )
                )
                os.utime(full_path, (stats.st_atime, stats.st_mtime))
            else:
                print("Ignoring file", path)


if __name__ == "__main__":
    main()
