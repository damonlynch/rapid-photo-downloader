# SPDX-FileCopyrightText: Copyright 2020-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

import ctypes
import ctypes.util
import logging

from PyQt5.QtGui import QImage

try:
    import pyheif
    from PIL import Image, ImageQt

    have_heif_module = True
except ImportError:
    have_heif_module = False

import importlib.metadata

_error_logged = False
_attribute_error_logged = False


def pyheif_version() -> str:
    """
    :return: Version of pyheif package
    """
    try:
        return pyheif.__version__
    except AttributeError:
        return importlib.metadata.version("pyheif")


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
            return (
                f"{h.heif_get_version_number_major()}."
                f"{h.heif_get_version_number_minor()}."
                f"{h.heif_get_version_number_maintenance()}"
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
    :return: ImageQt (subclass of QImage). Must keep this in memory for the duration of
     operations on it
    """
    global _error_logged
    global _attribute_error_logged

    try:
        image = pyheif.read_heif(full_file_name)
    except pyheif.error.HeifError:
        if not _error_logged:
            process_id = f"the {process_name if process_name else 'this'}"
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
            process_id = "the %s" % process_name if process_name else "this"
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

    try:
        imageqt = ImageQt.ImageQt(pillow_image)
    except AttributeError:
        if not _attribute_error_logged:
            process_id = f"the {process_name if process_name else 'this'}"
            logging.error(
                "Error using pyheif to load HEIF file %s. "
                "The Python package Pillow was unable to load Qt. "
                "If encountered on another file, this error message will only be "
                "repeated once for %s process.",
                full_file_name,
                process_id,
            )
            _attribute_error_logged = True
        if not catch_pyheif_exceptions:
            raise
        imageqt = None

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

        from PyQt5.QtGui import QPixmap
        from PyQt5.QtWidgets import QApplication, QLabel, QWidget

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
