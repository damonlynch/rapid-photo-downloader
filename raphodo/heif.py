# Copyright (C) 2020 Damon Lynch <damonlynch@gmail.com>

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

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2020, Damon Lynch"

import logging
from typing import Optional

from PyQt5.QtGui import QImage
try:
    import pyheif
    from PIL import ImageQt, Image
    have_heif_module = True
except ImportError:
    have_heif_module = False


_error_logged = False


def load_heif(full_file_name: str,
              catch_pyheif_exceptions: bool=True,
              process_name: str='') -> Optional[QImage]:
    """
    Load HEIF file and convert it to a QImage using Pillow
    :param full_file_name: image to load
    :return: QImage
    """
    global _error_logged

    try:
        image = pyheif.read_heif(full_file_name)
    except pyheif.error.HeifError:
        if not _error_logged:
            if process_name:
                process_id = "the %s" % process_name
            else:
                process_id = 'this'
            logging.error(
                "Error using pyheif to load HEIF file %s. "
                "If encountered on another file, this error message will only be repeated once "
                "for %s process.", full_file_name, process_id
            )
            _error_logged = True
        if not catch_pyheif_exceptions:
            raise
        return None

    pillow_image = Image.frombytes(mode=image.mode, size=image.size, data=image.data)
    if pillow_image.mode not in ('RGB', 'RGBA', '1', 'L', 'P'):
        pillow_image = pillow_image.convert('RGBA')
    return ImageQt.ImageQt(pillow_image)
