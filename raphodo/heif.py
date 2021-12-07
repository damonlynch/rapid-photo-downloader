# Copyright (C) 2020-2021 Damon Lynch <damonlynch@gmail.com>

# This file is part of Rapid Photo Downloader.
#
# Rapid Photo Downloader is free software: you can redistribute it and/or
# modify
# it under the terms of the GNU General Public License as published by
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

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2020-2021, Damon Lynch"

import logging
from typing import Optional
import ctypes, ctypes.util

from PyQt5.QtGui import QImage

try:
    import pyheif
    from PIL import ImageQt, Image

    have_heif_module = True
except ImportError:
    have_heif_module = False

from raphodo.utilities import python_package_version

_error_logged = False


def pyheif_version() -> str:
    """
    :return: Version of pyheif package
    """
    try:
        return pyheif.__version__
    except AttributeError:
        return python_package_version("pyheif")


def libheif_version() -> str:
    """
    :return: Version of libheif package
    """

    try:
        return pyheif.libheif_version()
    except AttributeError:
        try:
            library_name = ctypes.util.find_library("heif")
            h = ctypes.cdll.LoadLibrary(library_name)
            return "{}.{}.{}".format(
                h.heif_get_version_number_major(),
                h.heif_get_version_number_minor(),
                h.heif_get_version_number_maintenance(),
            )
        except Exception:
            logging.debug("Error determining libheif version")
            return ""


def load_heif(
    full_file_name: str, catch_pyheif_exceptions: bool = True, process_name: str = ""
):
    """
    Load HEIF file and convert it to a QImage using Pillow
    :param full_file_name: image to load
    :return: ImageQt (subclass of QImage). Must keep this in memory for duration of
     operations on it
    """
    global _error_logged

    try:
        image = pyheif.read_heif(full_file_name)
    except pyheif.error.HeifError:
        if not _error_logged:
            if process_name:
                process_id = "the %s" % process_name
            else:
                process_id = "this"
            logging.error(
                "Error using pyheif to load HEIF file %s. "
                "If encountered on another file, this error message will only be "
                "repeated once for %s process.",
                full_file_name,
                process_id,
            )
            _error_logged = True
        if not catch_pyheif_exceptions:
            raise
        return None
    except FileNotFoundError:
        if not _error_logged:
            if process_name:
                process_id = "the %s" % process_name
            else:
                process_id = "this"
            logging.error(
                "FileNotFoundError using pyheif to load HEIF file %s ."
                "If encountered on another file, this error message will only be "
                "repeated once for %s process.",
                full_file_name,
                process_id,
            )
            _error_logged = True
        if not catch_pyheif_exceptions:
            raise
        return None

    pillow_image = Image.frombytes(mode=image.mode, size=image.size, data=image.data)
    if pillow_image.mode not in ("RGB", "RGBA", "1", "L", "P"):
        pillow_image = pillow_image.convert("RGBA")

    imageqt = ImageQt.ImageQt(pillow_image)
    if imageqt is not None and not imageqt.isNull():
        return imageqt
    return None


if __name__ == "__main__":
    # test stub
    import sys

    if len(sys.argv) != 2:
        print("Usage: " + sys.argv[0] + " path/to/heif")
    else:
        file = sys.argv[1]

        import os
        from PyQt5.QtWidgets import QLabel, QWidget, QApplication
        from PyQt5.QtGui import QPixmap

        app = QApplication(sys.argv)
        image = None
        if os.path.splitext(file)[1][1:] in ("jpg", "png"):
            image = QPixmap(file)
        elif have_heif_module:
            imageqt = load_heif(file, catch_pyheif_exceptions=False)
            if imageqt is not None:
                image = QImage(imageqt)
                image = QPixmap(image)
            else:
                print("Error loading HEIF / HEIC image")
        else:
            print("image format not supported")

        if image is not None:
            widget = QWidget()
            widget.setFixedSize(image.size())
            label = QLabel(widget)
            label.setPixmap(image)
            widget.show()
            sys.exit(app.exec())
