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
Capture screenshots of Rapid Photo Downloader when running Wayland, assuming
XWayland is displaying the program.
"""

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2020-24, Damon Lynch"
__title__ = __file__
__description__ = "Capture screenshots of Rapid Photo Downloader when running Wayland."

import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import icecream
from PyQt6.QtCore import QStandardPaths
from PyQt6.QtGui import QGuiApplication, QImage

apply_offset = True

# From where are these offsets derived? I have no idea.
y_offset = 50
x_offset = 14

titlebar_height = 37
border_width = 1


wmctrl = shutil.which("wmctrl")
gm = shutil.which("gm")
gnome_screenshot = shutil.which("gnome-screenshot")
eog = shutil.which("eog")

screenshot_folder = Path(
    QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
)
output_folder = screenshot_folder / "output"


# TODO add more window titles
window_titles = ("Photo Subfolder Generation Editor",)


def check_requirements() -> None:
    """
    Ensure program requirements are installed
    """

    global wmctrl
    global gm
    global gnome_screenshot

    for program, package in (
        (wmctrl, "wmctrl"),
        (gm, "graphicsmagick"),
        (gnome_screenshot, "gnome-screenshot"),
    ):
        if program is None:
            print(f"Installing {package}")
            cmd = f"sudo apt -y install {package}"
            args = shlex.split(cmd)
            subprocess.run(args)

    wmctrl = shutil.which("wmctrl")
    gm = shutil.which("gm")
    gnome_screenshot = shutil.which("gnome-screenshot")


def extract_image(path: Path, window_x, window_y, width, height):
    image = QImage(str(path))
    assert not image.isNull()

    if apply_offset:
        x = window_x - x_offset - border_width
        y = window_y - y_offset - titlebar_height
        height = height + titlebar_height + border_width * 2
        width = width + border_width * 2
    else:
        x = window_x
        y = window_y

    cropped = image.copy(x, y, width, height)
    output_file = str(output_folder / path.name)
    cropped.save(output_file)
    if eog:
        subprocess.run([eog, str(output_file)])


def get_window_details() -> tuple[int, int, int, int]:
    """
    Get details of window using wmctrl

    :param window_title: title of window
    :return: x, y, width, height
    """

    cmd = f"{wmctrl} -l -G"
    args = shlex.split(cmd)
    result = subprocess.run(args, stdout=subprocess.PIPE, text=True)
    if result.returncode == 0:
        window_list = result.stdout
    else:
        print("Could not get window list")
        sys.exit(1)

    pattern = (
        r"^0x[\da-f]+\s+\d\s+(?P<x>\d+)\s+(?P<y>\d+)\s+"
        r"(?P<width>\d+)\s+(?P<height>\d+)\s+[\w]+\s+{}$"
    )

    for window_title in window_titles:
        match = re.search(
            pattern.format(window_title),
            window_list,
            re.MULTILINE,
        )
        if match is not None:
            return (
                int(match.group("x")),
                int(match.group("y")),
                int(match.group("width")),
                int(match.group("height")),
            )

    print("Could not get window details")
    sys.exit(1)


if __name__ == "__main__":
    icecream.install()

    check_requirements()

    output_folder.mkdir(exist_ok=True)

    app = QGuiApplication(sys.argv + ["-platform", "offscreen"])

    window_x, window_y, width, height = get_window_details()

    for path in screenshot_folder.glob("*.png"):
        extract_image(path, window_x, window_y, width, height)
