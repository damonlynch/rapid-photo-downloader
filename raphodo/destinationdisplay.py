# Copyright (C) 2015-2016 Damon Lynch <damonlynch@gmail.com>

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
# along with Rapid Photo Downloader.  If not,
# see <http://www.gnu.org/licenses/>.

"""
Display download destination details
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2016, Damon Lynch"

import os
from typing import Optional
from gettext import gettext as _


from PyQt5.QtCore import (QSize, Qt, QStorageInfo, QRect)
from PyQt5.QtWidgets import (QStyleOptionFrame, QStyle, QStylePainter, QWidget, QSplitter,
                             QSizePolicy)
from PyQt5.QtGui import (QColor, QPixmap, QIcon, QPaintEvent, QPalette)


from raphodo.devicedisplay import DeviceDisplay, BodyDetails, icon_size
from raphodo.storage import StorageSpace
from raphodo.constants import (CustomColors, DestinationDisplayType, DisplayingFilesOfType)
from raphodo.utilities import thousands, format_size_for_user
from raphodo.rpdfile import FileTypeCounter, FileType


class DestinationDisplay(QWidget):
    """
    Display how much storage space the checked files will use in addition
    to the space used by existing files
    """

    existing = _('Used')
    photos = _('Photos')
    videos = _('Videos')
    excess = _('Excess')

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.storage_space = None  # type: StorageSpace
        self.deviceDisplay = DeviceDisplay()
        size = icon_size()
        self.icon = QIcon(':/icons/folder.svg').pixmap(QSize(size, size))  # type: QPixmap
        self.display_name = ''
        self.photos_size_to_download = self.videos_size_to_download = 0
        self.files_to_display = None   # type: DisplayingFilesOfType
        self.marked = FileTypeCounter()
        self.display_type = None  # type: DestinationDisplayType
        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)

    def setDestination(self, path: str) -> None:
        """
        Set the downloaded destination path
        :param path: valid path
        """

        if path.endswith(os.sep):
            path = path[:-1]
        self.path = path
        self.display_name = os.path.basename(path)

        mount = QStorageInfo(path)
        self.storage_space=StorageSpace(
                        bytes_free=mount.bytesAvailable(),
                        bytes_total=mount.bytesTotal(),
                        path=path)

    def setDownloadAttributes(self, marked: FileTypeCounter,
                              photos_size: int,
                              videos_size: int,
                              files_to_display: DisplayingFilesOfType,
                              display_type: DestinationDisplayType,
                              merge: bool) -> None:
        """
        Set the attributes used to generate the visual display of the
        files marked to be downloaded

        :param marked: number and type of files marked for download
        :param photos_size: size in bytes of photos marked for download
        :param videos_size: size in bytes of videos marked for download
        :param files_to_display: whether displaying photos or videos or both
        :param display_type: whether showing only the header (folder only),
         usage only, or both
        :param merge: whether to replace or add to the current values
        """

        if not merge:
            self.marked = marked
            self.photos_size_to_download = photos_size
            self.videos_size_to_download = videos_size
        else:
            self.marked.update(marked)
            self.photos_size_to_download += photos_size
            self.videos_size_to_download += videos_size

        self.files_to_display = files_to_display

        self.display_type = display_type

        if self.display_type == DestinationDisplayType.folder_only:
            self.setToolTip(self.path)
        else:
            self.setToolTip('')

        self.update()
        self.updateGeometry()

    def sufficientSpaceAvailable(self) -> bool:
        """
        Check to see that there is sufficient space with which to perform a download.

        :return: True or False value if sufficient space. Will always return False if
         the download destination is not yet set.
        """

        if self.storage_space is None:
            return False
        return (self.photos_size_to_download + self.videos_size_to_download <
                self.storage_space.bytes_free)

    def paintEvent(self, event: QPaintEvent) -> None:
        """
        Render the custom widget
        """

        painter = QStylePainter()
        painter.begin(self)

        x = 0
        y = 0
        width = self.width()

        rect = self.rect()  # type: QRect

        if self.display_type == DestinationDisplayType.usage_only and QSplitter().lineWidth():
            option = QStyleOptionFrame()
            option.initFrom(self)
            painter.drawPrimitive(QStyle.PE_Frame, option)

            w = QSplitter().lineWidth()
            rect.adjust(w, w, -w, -w)

        palette = QPalette()
        backgroundColor = palette.base().color()
        painter.fillRect(rect, backgroundColor)

        if self.storage_space is None:
            painter.end()
            return

        if self.display_type != DestinationDisplayType.usage_only:
            self.deviceDisplay.paint_header(painter=painter, x=x, y=y, width=width,
                                            display_name=self.display_name, icon=self.icon)
            y = y + self.deviceDisplay.device_name_height

        if self.display_type != DestinationDisplayType.folder_only:

            if self.display_type == DestinationDisplayType.usage_only:
                y += self.deviceDisplay.padding

            bytes_total_text = format_size_for_user(self.storage_space.bytes_total, no_decimals=0)
            existing_bytes = self.storage_space.bytes_total - self.storage_space.bytes_free
            existing_size = format_size_for_user(existing_bytes)

            photos = videos = photos_size = videos_size = ''

            if self.files_to_display != DisplayingFilesOfType.videos:
                photos = _('%(no_photos)s Photos') % {'no_photos':
                                                          thousands(self.marked[FileType.photo])}
                photos_size = format_size_for_user(self.photos_size_to_download)
            if self.files_to_display != DisplayingFilesOfType.photos:
                videos = _('%(no_videos)s Videos') % {'no_videos':
                                                          thousands(self.marked[FileType.video])}
                videos_size = format_size_for_user(self.videos_size_to_download)

            size_to_download = self.photos_size_to_download + self.videos_size_to_download
            comp1_file_size_sum = self.photos_size_to_download
            comp2_file_size_sum =  self.videos_size_to_download
            comp3_file_size_sum =  existing_bytes
            comp1_text = photos
            comp2_text = videos
            comp3_text = self.existing
            comp4_text = self.excess
            comp1_size_text = photos_size
            comp2_size_text = videos_size
            comp3_size_text = existing_size

            bytes_to_use = size_to_download + existing_bytes
            percent_used = '{0:.0%}'.format(bytes_to_use / self.storage_space.bytes_total)
            # Translators: percentage full e.g. 75% full
            percent_used = '%s full' % percent_used

            if bytes_to_use > self.storage_space.bytes_total:
                bytes_total = bytes_to_use
                excess_bytes = bytes_to_use - self.storage_space.bytes_total
                comp4_file_size_sum = excess_bytes
                comp4_size_text = format_size_for_user(excess_bytes)
                bytes_free_of_total = _('No space free of %(size_total)s') % dict(
                    size_total=bytes_total_text)
            else:
                bytes_total = self.storage_space.bytes_total
                comp4_file_size_sum = 0
                comp4_size_text = 0
                bytes_free = self.storage_space.bytes_total - bytes_to_use
                bytes_free_of_total = _('%(size_free)s free of %(size_total)s') % dict(
                    size_free=format_size_for_user(bytes_free, no_decimals=1),
                    size_total=bytes_total_text)

            details = BodyDetails(bytes_total_text=bytes_total_text,
                                  bytes_total=bytes_total,
                                  percent_used_text=percent_used,
                                  bytes_free_of_total=bytes_free_of_total,
                                  comp1_file_size_sum=comp1_file_size_sum,
                                  comp2_file_size_sum=comp2_file_size_sum,
                                  comp3_file_size_sum=comp3_file_size_sum,
                                  comp4_file_size_sum=comp4_file_size_sum,
                                  comp1_text = comp1_text,
                                  comp2_text = comp2_text,
                                  comp3_text = comp3_text,
                                  comp4_text = comp4_text,
                                  comp1_size_text=comp1_size_text,
                                  comp2_size_text=comp2_size_text,
                                  comp3_size_text=comp3_size_text,
                                  comp4_size_text=comp4_size_text,
                                  color1=QColor(CustomColors.color1.value),
                                  color2=QColor(CustomColors.color2.value),
                                  color3=QColor(CustomColors.color3.value),
                                  displaying_files_of_type=self.files_to_display
                                  )

            self.deviceDisplay.paint_body(painter=painter, x=x,
                                          y=y,
                                          width=width,
                                          details=details)

        painter.end()

    def sizeHint(self) -> QSize:
        if self.display_type == DestinationDisplayType.usage_only:
            height = self.deviceDisplay.padding
        else:
            height = 0

        if self.display_type != DestinationDisplayType.usage_only:
            height += self.deviceDisplay.device_name_height
        if self.display_type != DestinationDisplayType.folder_only:
            height += self.deviceDisplay.storage_height
        return QSize(self.deviceDisplay.view_width, height)

    def minimumSize(self) -> QSize:
        return self.sizeHint()

