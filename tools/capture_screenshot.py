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

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2020-24, Damon Lynch"
__title__ = __file__
__description__ = "Capture screenshots of Rapid Photo Downloader."

import argparse
import glob
import os
import re
import shlex
import shutil
import subprocess
import sys
import time

import icecream
from PyQt5.QtCore import QRect, Qt
from PyQt5.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen

# Position of window
main_window_x = 920
main_window_y = 100
# Height of titlebar in default Ubuntu 19.10 theme
titlebar_height = 37

# Window width and height
main_window_width = 1600
main_window_height = 900

home_page_ratio = 463 / 439

features_main_window_width = 1164
features_main_window_height = 880

# Color of top and left window borders in default Ubuntu 19.10 theme
top_border_color = QColor(163, 160, 158, 255)
left_border_color = QColor(159, 156, 154, 255)

wmctrl = shutil.which("wmctrl")
gm = shutil.which("gm")
gnome_screenshot = shutil.which("gnome-screenshot")


pictures_directory = os.path.join(os.path.expanduser("~"), "Pictures")


def parser_options(formatter_class=argparse.HelpFormatter) -> argparse.ArgumentParser:
    """
    Construct the command line arguments for the script

    :return: the parser
    """

    parser = argparse.ArgumentParser(
        prog=__title__, formatter_class=formatter_class, description=__description__
    )

    parser.add_argument("file", help="Name of screenshot")
    parser.add_argument(
        "--screenshot",
        action="store_true",
        default=False,
        help="Screenshot from another tool that needs to be cropped. If does not "
        "exist in Pictures folder, will open the tool to create a new screenshot.",
    )

    parser.add_argument("--name", help="Window name if not main window")

    parser.add_argument(
        "--home",
        action="store_true",
        default=False,
        help="Size width / height ratio for home screen slideshow",
    )

    parser.add_argument(
        "--features",
        action="store_true",
        default=False,
        help="Size for display on features page",
    )

    parser.add_argument(
        "--sixteen-by-nine",
        action="store_true",
        default=False,
        help="Create 16:9 screenshot of main window",
    )

    return parser


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


def get_program_name() -> str:
    """
    Get Rapid Photo Downloader program title, if it's not English

    Getting translated names automatically does not work. Not sure why.

    :return: name in title bar of Rapid Photo Downloader
    """

    cmd = f"{wmctrl} -l"
    args = shlex.split(cmd)
    result = subprocess.run(args, stdout=subprocess.PIPE, text=True)
    if result.returncode == 0:
        window_list = result.stdout
    else:
        print("Could not get window list")
        sys.exit(1)

    if "Rapid Photo Downloader" in window_list:
        return "Rapid Photo Downloader"

    names = (
        "Rapid foto allalaadija",
        "Gyors Fotó Letöltő",
        "高速写真ダウンローダ",
        "Rapid-Fotoübertragung",
    )

    for title in names:
        if title in window_list:
            return title

    print(
        "Could not determine localized program title.\n"
        "Add it to the script using output from wmctrl -l.\n"
    )
    sys.exit(1)


def get_window_details(window_title: str) -> tuple[int, int, int, int]:
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
    match = re.search(
        pattern.format(window_title),
        window_list,
        re.MULTILINE,
    )
    if match is None:
        print("Could not get window details")
        sys.exit(1)

    return (
        int(match.group("x")),
        int(match.group("y")),
        int(match.group("width")),
        int(match.group("height")),
    )


def extract_image(image: str, width: int, height: int) -> QImage:
    """ "
    Get the program window from the screenshot by detecting its borders
    and knowing its size ahead of time
    """

    qimage = QImage(image)
    assert not qimage.isNull()

    # print("{}: {}x{}".format(image, qimage.width(), qimage.height()))

    y = qimage.height() // 2
    left = -1
    lightness = left_border_color.lightness()
    for x in range(0, qimage.width()):
        if qimage.pixelColor(x, y).lightness() <= lightness:
            left = x
            break

    if left < 0:
        sys.stderr.write("Could not locate left window border\n")
        sys.exit(1)

    x = qimage.width() // 2
    top = -1
    lightness = top_border_color.lightness()
    for y in range(0, qimage.height()):
        if qimage.pixelColor(x, y).lightness() <= lightness:
            top = y
            break

    if top < 0:
        sys.stderr.write("Could not locate top window border\n")
        sys.exit(1)

    return qimage.copy(QRect(left, top, width, height))


def add_border(image: str) -> QImage:
    """
    Add border to screenshot that was taken away by screenshot utility
    :param image: image without borders
    :return: image with borders
    """

    qimage = QImage(image)
    painter = QPainter()
    painter.begin(qimage)
    pen = QPen()
    pen.setColor(left_border_color)
    pen.setWidth(1)
    pen.setStyle(Qt.SolidLine)
    pen.setJoinStyle(Qt.MiterJoin)
    rect = QRect(0, 0, qimage.width() - 1, qimage.height() - 1)
    painter.setPen(pen)
    painter.drawRect(rect)
    painter.end()
    return qimage


def add_transparency(qimage: QImage) -> QImage:
    """
    Add transparent window borders according to Ubuntu 19.10 titlebar style
    :param qimage: image with non transparent top left and right corners
    :return: image with transparent top left and right corners
    """

    if not qimage.hasAlphaChannel():
        assert qimage.format() == QImage.Format_RGB32
        transparent = QImage(qimage.size(), QImage.Format_ARGB32_Premultiplied)
        transparent.fill(Qt.black)
        painter = QPainter()
        painter.begin(transparent)
        painter.drawImage(0, 0, qimage)
        painter.end()
        qimage = transparent

    image_width = qimage.width()
    y = -1
    for width in (5, 3, 2, 1):
        y += 1
        for x in range(width):
            color = qimage.pixelColor(x, y)
            color.setAlpha(0)
            qimage.setPixelColor(x, y, color)
            qimage.setPixelColor(image_width - x - 1, y, color)

    return qimage


if __name__ == "__main__":
    icecream.install()

    check_requirements()

    parser = parser_options()
    parserargs = parser.parse_args()

    app = QGuiApplication(sys.argv + ["-platform", "offscreen"])

    filename = f"{parserargs.file}.png"

    image = os.path.join(pictures_directory, filename)
    window_title = parserargs.name

    program_name = window_title or get_program_name()

    if parserargs.home is not None or parserargs.features is not None:
        window_x, window_y, width, height = get_window_details(program_name)
        ic(window_x, window_y, width, height)

        restore_x, restore_y, restore_width, restore_height = (
            window_x,
            window_y,
            width,
            height,
        )

        if parserargs.home:
            height = int(width / home_page_ratio)

        if parserargs.features:
            width = features_main_window_width
            height = features_main_window_height + titlebar_height
            # window_x, window_y = 100, 100

        # parserargs.screenshot = False

    elif parserargs.sixteen_by_nine:
        # 16:9 screenshot of main window
        width = main_window_width
        height = main_window_height
        window_x = main_window_x
        window_y = main_window_y
        restore_x, restore_y, restore_width, restore_height = 0, 0, 0, 0

    else:
        print("Don't know what task to do. Exiting")
        sys.exit(1)

    if not parserargs.screenshot:
        resize_command = "{program} -r '{program_name}' -e 0,{x},{y},{width},{height}"

        # Adjust width and height allowing for 1px border round outside of window
        resize = resize_command.format(
            x=window_x + 1,
            y=window_y + 1,
            width=width - 2,
            height=height - titlebar_height - 1,
            program=wmctrl,
            program_name=program_name,
        )

        ic(resize)

        restore = resize_command.format(
            x=restore_x - 15,
            y=restore_y - titlebar_height * 2 - 1,
            width=restore_width,
            height=restore_height,
            program=wmctrl,
            program_name=program_name,
        )

        capture = (
            "{program} import -window root -crop {width}x{height}+{x}+{y} -quality 90 "
            "{file}".format(
                x=window_x,
                y=window_y,
                width=width,
                height=height,
                file=image,
                program=gm,
            )
        )

        remove_offset = f"{gm} convert +page {image} {image}"

        if restore_height:
            cmds = (resize, capture, remove_offset, restore)
        else:
            cmds = (resize, capture, remove_offset)
        for cmd in cmds:
            if cmd == capture:
                time.sleep(2)
            args = shlex.split(cmd)
            if subprocess.run(args).returncode != 0:
                print("Failed to complete tasks")
                sys.exit(1)

        qimage = add_border(image)

    else:
        screenshot = glob.glob(os.path.join(pictures_directory, "Screenshot*.png"))
        if len(screenshot) == 1:
            os.rename(screenshot[0], image)
        else:
            cmd = f"{gnome_screenshot} -a -f {image}"
            args = shlex.split(cmd)
            if subprocess.run(args).returncode != 0:
                print("Failed to capture screenshot")
                sys.exit(1)

        qimage = extract_image(image, width, height)

    qimage = add_transparency(qimage)
    qimage.save(image)

    cmd = f"/usr/bin/eog {image}"
    args = shlex.split(cmd)
    subprocess.run(args)
