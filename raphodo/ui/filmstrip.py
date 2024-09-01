# SPDX-FileCopyrightText: Copyright 2011-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Overlays a filmstrip onto QImage, keeping the image's dimensions the
same
"""

from PyQt5.QtGui import QImage, QPainter

xpm_data = [
    "12 10 27 1",
    "   c #000000",
    ".  c #232323",
    "+  c #7A7A7A",
    "@  c #838383",
    "#  c #8C8C8C",
    "$  c #909090",
    "%  c #8E8E8E",
    "&  c #525252",
    "*  c #6E6E6E",
    "=  c #939393",
    "-  c #A3A3A3",
    ";  c #ABABAB",
    ">  c #A8A8A8",
    ",  c #9B9B9B",
    "'  c #727272",
    ")  c #A4A4A4",
    "!  c #BBBBBB",
    "~  c #C4C4C4",
    "{  c #C1C1C1",
    "]  c #AFAFAF",
    "^  c #3E3E3E",
    "/  c #A6A6A6",
    "(  c #BEBEBE",
    "_  c #C8C8C8",
    ":  c #070707",
    "<  c #090909",
    "[  c #0A0A0A",
    "            ",
    "            ",
    "            ",
    "    .+@#$%& ",
    "    *@=-;>, ",
    "    '%)!~{] ",
    "    ^$/(_~% ",
    "     :<[[[  ",
    "            ",
    "            ",
]


def add_filmstrip(thumbnail: QImage) -> QImage:
    """
    Overlays a filmstrip onto the thumbnail.

    Keeps the thumbnail's dimensions the same.

    :param thumbnail: thumbnail on which to put the filmstrip
    :return a copy of the thumbnail

    """

    filmstrip = QImage(xpm_data)
    filmstrip_width = filmstrip.width()
    filmstrip_height = filmstrip.height()
    filmstrip_right = filmstrip.mirrored(horizontal=True, vertical=False)

    thumbnail_right_col = thumbnail.width() - filmstrip_width

    painter = QPainter(thumbnail)

    # add filmstrips to left and right
    for i in range(thumbnail.height() // filmstrip_height):
        painter.drawImage(0, i * filmstrip_height, filmstrip)
        painter.drawImage(thumbnail_right_col, i * filmstrip_height, filmstrip_right)

    # now do the remainder, at the bottom
    remaining_height = thumbnail.height() % filmstrip_height
    if remaining_height:
        painter.drawImage(
            0,
            thumbnail.height() - remaining_height,
            filmstrip.copy(0, 0, filmstrip_width, remaining_height),
        )
        painter.drawImage(
            thumbnail_right_col,
            thumbnail.height() - remaining_height,
            filmstrip_right.copy(0, 0, filmstrip_width, remaining_height),
        )

    return thumbnail
