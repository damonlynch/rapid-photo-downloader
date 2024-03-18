# SPDX-FileCopyrightText: Copyright 2020-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Handle when the user clicks on a URL in Qt and the URL scheme is file://

The point is to open a file manager which selects the file in the URI, rather than
opening the file directly.
"""

from PyQt5.QtCore import QObject, QUrl, pyqtSlot
from showinfm import show_in_file_manager


class FileSystemUrlHandler(QObject):
    @pyqtSlot(QUrl)
    def openFileBrowser(self, url: QUrl):
        show_in_file_manager(url.url(options=QUrl.FullyEncoded))
