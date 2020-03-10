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
Capture screenshots of Rapid Photo Downloader.
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2020, Damon Lynch"
__title__ = __file__
__description__ = 'Capture screenshots of Rapid Photo Downloader.'

import subprocess
import argparse
import os
import shutil
import sys
import shlex

wmctrl = shutil.which('wmctrl')
gm = shutil.which('gm')


pictures_directory = os.path.join(os.path.expanduser('~'), 'Pictures')
mask = os.path.join(pictures_directory, 'mask.png')


def parser_options(formatter_class=argparse.HelpFormatter) -> argparse.ArgumentParser:
    """
    Construct the command line arguments for the script

    :return: the parser
    """
    parser = argparse.ArgumentParser(
        prog=__title__, formatter_class=formatter_class, description=__description__
    )

    parser.add_argument('file', help='Name of screenshot')
    parser.add_argument('--gimp', help="Screenshot from Gimp zealous crop", default=False)
    return parser



def check_requirements() -> None:
    """
    Ensure program requirements are installed
    """

    global wmctrl
    global gm

    for program, package in ((wmctrl, 'wmctrl'), (gm, 'graphicsmagick')):
        if program is None:
            print("Installing {}".format(package))
            cmd = 'sudo apt -y install {}'.format(package)
            args = shlex.split(cmd)
            subprocess.run(args)

    wmctrl = shutil.which('wmctrl')
    gm = shutil.which('gm')

    if not os.path.isfile(mask):
        sys.stderr.write("Add {}".format(mask))
        sys.exit(1)


if __name__ == '__main__':
    check_requirements()

    parser = parser_options()
    args = parser.parse_args()

    x = 900
    y = 200
    titlebar_height = 37
    width = 1600
    height = 900

    image = os.path.join(pictures_directory, args.file)

    resize = "{program} -r 'Rapid Photo Downloader' -e 0,{x},{y},{width},{height}".format(
        x=x, y=y, width=width, height=height-titlebar_height, program=wmctrl
    )
    capture = "{program} import -window root -crop {width}x{height}+{x}+{y} -quality 90 " \
              "{file}.png".format(
        x=x, y=y - titlebar_height, width=width, height=height, file=image, program=gm
    )
    remove_offset = "{program} convert +page {file}.png {file}.png".format(
        file=image, program=gm

    )
    add_transparency = "{program} composite -compose CopyOpacity {mask} {file}.png " \
                       "{file}.png".format(mask=mask, file=image, program=gm)

    crop = "{program} convert -crop {width}x{height}+17+15 -quality 90 {file}.png {file}.png".format(
        width=width, height=height, file=image, program=gm
    )

    if args.gimp:
        cmds = (crop, remove_offset, add_transparency)
    else:
        cmds = (resize, capture, remove_offset, add_transparency)

    for cmd in cmds:
        args=shlex.split(cmd)
        subprocess.run(args)

