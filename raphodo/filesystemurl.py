# Copyright (C) 2020-2021 Damon Lynch <damonlynch@gmail.com>

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
Handle when the user clicks on a URL in Qt and the URL scheme is file://

The point is to open a file manager which selects the file in the URI, rather than
opening the file directly.
"""


__author__ = "Damon Lynch"
__copyright__ = "Copyright 2020-2021, Damon Lynch"

from PyQt5.QtCore import QObject, QUrl, pyqtSlot
from showinfm import show_in_file_manager


class FileSystemUrlHandler(QObject):
    @pyqtSlot(QUrl)
    def openFileBrowser(self, url: QUrl):
        show_in_file_manager(url.url(options=QUrl.FullyEncoded))
