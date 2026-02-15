#  SPDX-FileCopyrightText: 2020-2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: GPL-3.0-or-later

import logging

from PyQt5.QtGui import QImage

try:
    import pillow_heif
    from PIL import Image, ImageQt

    # pillow support for PyQt5 is not guaranteed
    assert ["5", "PyQt5"] in ImageQt.qt_versions

    pillow_heif.register_heif_opener(thumbnails=False)

    have_heif_module = True
except (ImportError, AssertionError):
    have_heif_module = False

import importlib.metadata

_error_logged = False
_attribute_error_logged = False


def pillow_heif_version() -> str:
    """
    :return: Version of pillow heif package
    """
    try:
        return pillow_heif.__version__
    except AttributeError:
        return importlib.metadata.version("pillow_heif")


def libheif_version() -> str:
    """
    :return: Version of libheif package
    """

    try:
        return pillow_heif.libheif_version()
    except Exception:
        logging.debug("Error determining libheif version")
        return ""


def load_heif(
    full_file_name: str,
    catch_pillow_heif_exceptions: bool = True,
    process_name: str = "",
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
        with Image.open(full_file_name) as pillow_image:
            if pillow_image.mode not in ("RGB", "RGBA", "1", "L", "P"):
                pillow_image = pillow_image.convert("RGBA")
            try:
                imageqt = ImageQt.ImageQt(pillow_image)
            except AttributeError:
                if not _attribute_error_logged:
                    process_id = f"the {process_name if process_name else 'this'}"
                    logging.error(
                        "Error using pillow-heif to load HEIF file %s. "
                        "The Python package Pillow was unable to convert the image to "
                        "be in Qt format. "
                        "If encountered on another file, this error message will only "
                        "be repeated once for %s process.",
                        full_file_name,
                        process_id,
                    )
                    _attribute_error_logged = True
                if not catch_pillow_heif_exceptions:
                    raise
                imageqt = None

            if imageqt is not None and not imageqt.isNull():
                return imageqt
            return None
    except FileNotFoundError:
        if not _error_logged:
            process_id = "the %s" % process_name if process_name else "this"
            logging.error(
                "FileNotFoundError using pillow-heif to load HEIF file %s ."
                "If encountered on another file, this error message will only be "
                "repeated once for %s process.",
                full_file_name,
                process_id,
            )
            _error_logged = True
        if not catch_pillow_heif_exceptions:
            raise
        return None
    except Exception:
        if not _error_logged:
            process_id = f"the {process_name if process_name else 'this'}"
            logging.error(
                "Error using pillow-heif to load HEIF file %s. "
                "If encountered on another file, this error message will only be "
                "repeated once for %s process.",
                full_file_name,
                process_id,
            )
            _error_logged = True
        if not catch_pillow_heif_exceptions:
            raise
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
            imageqt = load_heif(file, catch_pillow_heif_exceptions=False)
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
