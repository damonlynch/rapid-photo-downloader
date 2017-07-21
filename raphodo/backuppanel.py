# Copyright (C) 2017 Damon Lynch <damonlynch@gmail.com>

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
Display backup preferences
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2017, Damon Lynch"

from typing import Optional, Dict, Tuple, Union, Set, List, DefaultDict
import logging
import os
from collections import namedtuple, defaultdict

from gettext import gettext as _


from PyQt5.QtCore import (Qt, pyqtSlot, QAbstractListModel, QModelIndex, QSize)
from PyQt5.QtWidgets import (
    QWidget, QSizePolicy, QVBoxLayout, QLabel, QLineEdit, QCheckBox, QScrollArea, QFrame,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle, QGroupBox, QHBoxLayout, QGridLayout
)
from PyQt5.QtGui import (QPainter, QFontMetrics, QFont, QColor, QPalette, QIcon)

from raphodo.constants import (
    StandardFileLocations, ThumbnailBackgroundName, FileType,  Roles, ViewRowType,
    BackupLocationType
)
from raphodo.viewutils import (QFramedWidget, RowTracker)
from raphodo.rpdfile import FileTypeCounter, Photo, Video
from raphodo.panelview import QPanelView
from raphodo.preferences import Preferences
from raphodo.foldercombo import FolderCombo
import raphodo.qrc_resources as qrc_resources
from raphodo.storage import (ValidMounts, get_media_dir, StorageSpace, get_path_display_name)
from raphodo.devices import (BackupDeviceCollection, BackupVolumeDetails)
from raphodo.devicedisplay import (DeviceDisplay, BodyDetails, icon_size, DeviceView)
from raphodo.destinationdisplay import make_body_details, adjusted_download_size
from raphodo.storage import get_mount_size


BackupVolumeUse = namedtuple('BackupVolumeUse', 'bytes_total bytes_free backup_type marked '
                                                'photos_size_to_download videos_size_to_download')
BackupViewRow = namedtuple('BackupViewRow', 'mount display_name backup_type os_stat_device')


class BackupDeviceModel(QAbstractListModel):
    """
    Stores 'devices' used for backing up photos and videos.

    Want to display:
    (1) destination on local files systems
    (2) external devices, e.g. external hard drives

    Need to account for when download destination is same file system
    as backup destination.
    """

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.raidApp = parent.rapidApp
        self.prefs = parent.prefs
        size = icon_size()
        self.removableIcon = QIcon(':icons/drive-removable-media.svg').pixmap(size)
        self.folderIcon = QIcon(':/icons/folder.svg').pixmap(size)
        self._initValues()

    def _initValues(self):
        self.rows = RowTracker()  # type: RowTracker
        self.row_id_counter = 0  # type: int
        # {row_id}
        self.headers = set()  # type: Set[int]
        # path: BackupViewRow
        self.backup_devices = dict()  # type: Dict[str, BackupViewRow]
        self.path_to_row_ids = defaultdict(list)  # type: Dict[str, List[int]]
        self.row_id_to_path = dict()  # type: Dict[int, str]

        self.marked = FileTypeCounter()
        self.photos_size_to_download = self.videos_size_to_download = 0

        # os_stat_device: Set[FileType]
        self._downloading_to = defaultdict(list)  # type: DefaultDict[int, Set[FileType]]

    @property
    def downloading_to(self):
        return self._downloading_to

    @downloading_to.setter
    def downloading_to(self, downloading_to: DefaultDict[int, Set[FileType]]):
        self._downloading_to = downloading_to
        self.downloadSizeChanged()

    def reset(self) -> None:
        self.beginResetModel()
        self._initValues()
        self.endResetModel()

    def columnCount(self, parent=QModelIndex()):
        return 1

    def rowCount(self, parent=QModelIndex()):
        return max(len(self.rows), 1)

    def insertRows(self, position, rows=2, index=QModelIndex()):
        self.beginInsertRows(QModelIndex(), position, position + rows - 1)
        self.endInsertRows()
        return True

    def removeRows(self, position, rows=2, index=QModelIndex()):
        self.beginRemoveRows(QModelIndex(), position, position + rows - 1)
        self.endRemoveRows()
        return True

    def addBackupVolume(self, mount_details: BackupVolumeDetails) -> None:

        mount = mount_details.mount
        display_name = mount_details.name
        path = mount_details.path
        backup_type = mount_details.backup_type
        os_stat_device = mount_details.os_stat_device

        assert mount is not None
        assert display_name
        assert path
        assert backup_type

        # two rows per device: header row, and detail row
        row = len(self.rows)
        self.insertRows(position=row)
        logging.debug("Adding %s to backup device display with root path %s at rows %s - %s",
                      display_name, mount.rootPath(), row, row+1)

        for row_id in range(self.row_id_counter, self.row_id_counter + 2):
            self.row_id_to_path[row_id] = path
            self.rows[row] = row_id
            row += 1
            self.path_to_row_ids[path].append(row_id)

        header_row_id = self.row_id_counter
        self.headers.add(header_row_id)

        self.row_id_counter += 2

        self.backup_devices[path] = BackupViewRow(mount=mount, display_name=display_name,
                                                  backup_type=backup_type,
                                                  os_stat_device=os_stat_device)

    def removeBackupVolume(self, path: str) -> None:
        """
        :param path: the value of the volume (mount's path), NOT a
        manually specified path!
        """

        row_ids = self.path_to_row_ids[path]
        header_row_id = row_ids[0]
        row = self.rows.row(header_row_id)
        logging.debug("Removing 2 rows from backup view, starting at row %s", row)
        self.rows.remove_rows(row, 2)
        self.headers.remove(header_row_id)
        del self.path_to_row_ids[path]
        del self.backup_devices[path]
        for row_id in row_ids:
            del self.row_id_to_path[row_id]
        self.removeRows(row, 2)

    def setDownloadAttributes(self, marked: FileTypeCounter,
                              photos_size: int,
                              videos_size: int,
                              merge: bool) -> None:
        """
        Set the attributes used to generate the visual display of the
        files marked to be downloaded

        :param marked: number and type of files marked for download
        :param photos_size: size in bytes of photos marked for download
        :param videos_size: size in bytes of videos marked for download
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
        self.downloadSizeChanged()

    def downloadSizeChanged(self) -> None:
        # TODO possibly optimize for photo vs video rows
        for row in range(1, len(self.rows), 2):
            self.dataChanged.emit(self.index(row, 0), self.index(row, 0))

    def _download_size_by_backup_type(self, backup_type: BackupLocationType) -> Tuple[int, int]:
        """
        Include photos or videos in download size only if those file types
        are being backed up to this backup device
        :param backup_type: which file types are being backed up to this device
        :return: photos_size_to_download, videos_size_to_download
        """

        photos_size_to_download = videos_size_to_download = 0
        if backup_type != BackupLocationType.videos:
            photos_size_to_download = self.photos_size_to_download
        if backup_type != BackupLocationType.photos:
            videos_size_to_download = self.videos_size_to_download
        return photos_size_to_download, videos_size_to_download

    def data(self, index: QModelIndex, role=Qt.DisplayRole):

        if not index.isValid():
            return None

        row = index.row()

        # check for special case where no backup devices are active
        if len(self.rows) == 0:
            if role == Qt.DisplayRole:
                return ViewRowType.header
            else:
                assert role == Roles.device_details
                if not self.prefs.backup_files:
                    return (_('Backups are not configured'), self.removableIcon)
                elif self.prefs.backup_device_autodetection:
                    return (_('No backup devices detected'), self.removableIcon)
                else:
                    return (_('Valid backup locations not yet specified'), self.folderIcon)

        # at least one device  / location is being used
        if row >= len(self.rows) or row < 0:
            return None
        if row not in self.rows:
            return None

        row_id = self.rows[row]
        path = self.row_id_to_path[row_id]

        if role == Qt.DisplayRole:
            if row_id in self.headers:
                return ViewRowType.header
            else:
                return ViewRowType.content
        else:
            device = self.backup_devices[path]
            mount = device.mount

            if role == Qt.ToolTipRole:
                return path
            elif role == Roles.device_details:
                if self.prefs.backup_device_autodetection:
                    icon = self.removableIcon
                else:
                    icon = self.folderIcon
                return (device.display_name, icon)
            elif role == Roles.storage:
                photos_size_to_download, videos_size_to_download = \
                    self._download_size_by_backup_type(backup_type=device.backup_type)

                photos_size_to_download, videos_size_to_download = adjusted_download_size(
                    photos_size_to_download=photos_size_to_download,
                    videos_size_to_download=videos_size_to_download,
                    os_stat_device=device.os_stat_device,
                    downloading_to=self._downloading_to)

                bytes_total, bytes_free = get_mount_size(mount=mount)

                return BackupVolumeUse(
                    bytes_total=bytes_total,
                    bytes_free=bytes_free,
                    backup_type=device.backup_type,
                    marked = self.marked,
                    photos_size_to_download=photos_size_to_download,
                    videos_size_to_download=videos_size_to_download
                )

        return None

    def sufficientSpaceAvailable(self) -> bool:
        """
        Detect if each backup device has sufficient space for backing up, taking
        into accoutn situations where downloads and backups are going to the same
        partition.

        :return: False if any backup device has insufficient space, else True.
         True if there are no backup devices.
        """

        for device in self.backup_devices.values():
            photos_size_to_download, videos_size_to_download = \
                self._download_size_by_backup_type(backup_type=device.backup_type)
            photos_size_to_download, videos_size_to_download = adjusted_download_size(
                photos_size_to_download=photos_size_to_download,
                videos_size_to_download=videos_size_to_download,
                os_stat_device=device.os_stat_device,
                downloading_to=self._downloading_to
            )

            bytes_total, bytes_free = get_mount_size(mount=device.mount)
            if photos_size_to_download + videos_size_to_download >= bytes_free:
                return False
        return True


class BackupDeviceView(DeviceView):
    def __init__(self, rapidApp, parent=None) -> None:
        super().__init__(rapidApp, parent)
        self.setMouseTracking(False)
        self.entered.disconnect()


class BackupDeviceDelegate(QStyledItemDelegate):
    def __init__(self, rapidApp, parent=None) -> None:
        super().__init__(parent)
        self.rapidApp = rapidApp
        self.deviceDisplay = DeviceDisplay()

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        painter.save()

        x = option.rect.x()
        y = option.rect.y()
        width = option.rect.width()

        view_type = index.data(Qt.DisplayRole)  # type: ViewRowType
        if view_type == ViewRowType.header:
            display_name, icon = index.data(Roles.device_details)

            self.deviceDisplay.paint_header(painter=painter, x=x, y=y, width=width,
                                            icon=icon,
                                            display_name=display_name,
                                            )
        else:
            assert view_type == ViewRowType.content

            data = index.data(Roles.storage)  # type: BackupVolumeUse
            details = make_body_details(bytes_total=data.bytes_total,
                                        bytes_free=data.bytes_free,
                                        files_to_display=data.backup_type,
                                        marked=data.marked,
                                        photos_size_to_download=data.photos_size_to_download,
                                        videos_size_to_download=data.videos_size_to_download)

            self.deviceDisplay.paint_body(painter=painter, x=x,
                                          y=y,
                                          width=width,
                                          details=details)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        view_type = index.data(Qt.DisplayRole)  # type: ViewRowType
        if view_type == ViewRowType.header:
            height = self.deviceDisplay.device_name_height
        else:
            storage_space = index.data(Roles.storage)

            if storage_space is None:
                height = self.deviceDisplay.base_height
            else:
                height = self.deviceDisplay.storage_height
        return QSize(self.deviceDisplay.view_width, height)

class BackupOptionsWidget(QFramedWidget):
    """
    Display and allow editing of preference values for Downloads today
    and Stored Sequence Number and associated options, as well as
    the strip incompatible characters option.
    """

    def __init__(self, prefs: Preferences, parent, rapidApp) -> None:
        super().__init__(parent)

        self.rapidApp = rapidApp
        self.prefs = prefs
        self.media_dir = get_media_dir()

        self.setBackgroundRole(QPalette.Base)
        self.setAutoFillBackground(True)

        backupLayout = QGridLayout()
        layout = QVBoxLayout()
        layout.addLayout(backupLayout)
        self.setLayout(layout)

        self.backupExplanation = QLabel(
            _(
                'You can have your photos and videos backed up to '
                'multiple locations as they are downloaded, e.g. '
                'external hard drives.'
            )
        )
        self.backupExplanation.setWordWrap(True)
        self.backupExplanation.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)

        self.backup = QCheckBox(_('Back up photos and videos when downloading'))
        self.backup.setChecked(self.prefs.backup_files)
        self.backup.stateChanged.connect(self.backupChanged)

        checkbox_width = self.backup.style().pixelMetric(QStyle.PM_IndicatorWidth)

        self.autoBackup = QCheckBox(_('Automatically detect backup devices'))
        self.autoBackup.setChecked(self.prefs.backup_device_autodetection)
        self.autoBackup.stateChanged.connect(self.autoBackupChanged)

        self.folderExplanation = QLabel(
            _(
                'Specify the folder in which backups are stored on the '
                'device.<br><br>'
                '<i>Note: the presence of a folder with this name '
                'is used to determine if the device is used for backups. '
                'For each device you wish to use for backing up to, '
                'create a folder in it with one of these folder names. '
                'By adding both folders, the same device can be used '
                'to back up both photos and videos.</i>'
            )
        )
        self.folderExplanation.setWordWrap(True)
        self.folderExplanation.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
        # Unless this next call is made, for some reason the widget is too high! :-(
        self.folderExplanation.setContentsMargins(0, 0, 1, 0)

        self.photoFolderNameLabel = QLabel(_('Photo folder name:'))
        self.photoFolderName = QLineEdit()
        self.photoFolderName.setText(self.prefs.photo_backup_identifier)
        self.photoFolderName.editingFinished.connect(self.photoFolderIdentifierChanged)

        self.videoFolderNameLabel = QLabel(_('Video folder name:'))
        self.videoFolderName = QLineEdit()
        self.videoFolderName.setText(self.prefs.video_backup_identifier)
        self.videoFolderName.editingFinished.connect(self.videoFolderIdentifierChanged)

        self.autoBackupExampleBox = QGroupBox(_('Example:'))
        self.autoBackupExample = QLabel()

        autoBackupExampleBoxLayout = QHBoxLayout()
        autoBackupExampleBoxLayout.addWidget(self.autoBackupExample)

        self.autoBackupExampleBox.setLayout(autoBackupExampleBoxLayout)

        valid_mounts = ValidMounts(onlyExternalMounts=True)

        self.manualLocationExplanation = QLabel(
            _('If you disable automatic detection, choose the exact backup locations.')
        )
        self.manualLocationExplanation.setWordWrap(True)
        self.manualLocationExplanation.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
        # Translators: the word 'location' is optional in your translation. The left
        # side of the folder chooser combo box will always line up with the left side of the
        # the text entry boxes where the user can enter the photo folder name and the video
        # folder name. See http://damonlynch.net/rapid/documentation/thumbnails/backup.png
        self.photoLocationLabel = QLabel(_('Photo backup location:'))
        self.photoLocationLabel.setWordWrap(True)
        self.photoLocation = FolderCombo(
            self,
            prefs=self.prefs,
            file_type=FileType.photo,
            file_chooser_title=_('Select Photo Backup Location'),
            special_dirs=(StandardFileLocations.pictures,),
            valid_mounts=valid_mounts
        )
        self.photoLocation.setPath(self.prefs.backup_photo_location)
        self.photoLocation.pathChosen.connect(self.photoPathChosen)

        # Translators: the word 'location' is optional in your translation. The left
        # side of the folder chooser combo box will always line up with the left side of the
        # the text entry boxes where the user can enter the photo folder name and the video
        # folder name. See http://damonlynch.net/rapid/documentation/thumbnails/backup.png
        self.videoLocationLabel = QLabel(_('Video backup location:'))
        self.videoLocationLabel.setWordWrap(True)
        self.videoLocation = FolderCombo(
            self,
            prefs=self.prefs,
            file_type=FileType.video,
            file_chooser_title=_('Select Video Backup Location'),
            special_dirs=(StandardFileLocations.videos, ),
            valid_mounts=valid_mounts
        )
        self.videoLocation.setPath(self.prefs.backup_video_location)
        self.videoLocation.pathChosen.connect(self.videoPathChosen)

        backupLayout.addWidget(self.backupExplanation, 0, 0, 1, 4)
        backupLayout.addWidget(self.backup, 1, 0, 1, 4)
        backupLayout.addWidget(self.autoBackup, 2, 1, 1, 3)
        backupLayout.addWidget(self.folderExplanation, 3, 2, 1, 2)
        backupLayout.addWidget(self.photoFolderNameLabel, 4, 2, 1, 1)
        backupLayout.addWidget(self.photoFolderName, 4, 3, 1, 1)
        backupLayout.addWidget(self.videoFolderNameLabel, 5, 2, 1, 1)
        backupLayout.addWidget(self.videoFolderName, 5, 3, 1, 1)
        backupLayout.addWidget(self.autoBackupExampleBox, 6, 2, 1, 2)
        backupLayout.addWidget(self.manualLocationExplanation, 7, 1, 1, 3, Qt.AlignBottom)
        backupLayout.addWidget(self.photoLocationLabel, 8, 1, 1, 2)
        backupLayout.addWidget(self.photoLocation, 8, 3, 1, 1)
        backupLayout.addWidget(self.videoLocationLabel, 9, 1, 1, 2)
        backupLayout.addWidget(self.videoLocation, 9, 3, 1, 1)

        backupLayout.setColumnMinimumWidth(0, checkbox_width)
        backupLayout.setColumnMinimumWidth(1, checkbox_width)

        backupLayout.setRowMinimumHeight(7, checkbox_width * 2)

        layout.addStretch()

        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.setBackupButtonHighlight()

        # Group controls to enable / disable sets of them
        self._backup_controls_type = (self.autoBackup, )
        self._backup_controls_auto = (
            self.folderExplanation, self.photoFolderNameLabel, self.photoFolderName,
            self.videoFolderNameLabel, self.videoFolderName, self.autoBackupExampleBox
        )
        self._backup_controls_manual = (
            self.manualLocationExplanation, self.photoLocationLabel, self.photoLocation,
            self.videoLocationLabel, self.videoLocation,
        )
        self.updateExample()
        self.enableControlsByBackupType()

    @pyqtSlot(int)
    def backupChanged(self, state: int) -> None:
        backup = state == Qt.Checked
        logging.info("Setting backup while downloading to %s", backup)
        self.prefs.backup_files = backup
        self.setBackupButtonHighlight()
        self.enableControlsByBackupType()
        self.rapidApp.resetupBackupDevices()

    @pyqtSlot(int)
    def autoBackupChanged(self, state: int) -> None:
        autoBackup = state == Qt.Checked
        logging.info("Setting automatically detect backup devices to %s", autoBackup)
        self.prefs.backup_device_autodetection = autoBackup
        self.setBackupButtonHighlight()
        self.enableControlsByBackupType()
        self.rapidApp.resetupBackupDevices()

    @pyqtSlot(str)
    def photoPathChosen(self, path: str) -> None:
        logging.info("Setting backup photo location to %s", path)
        self.prefs.backup_photo_location = path
        self.setBackupButtonHighlight()
        self.rapidApp.resetupBackupDevices()

    @pyqtSlot(str)
    def videoPathChosen(self, path: str) -> None:
        logging.info("Setting backup video location to %s", path)
        self.prefs.backup_video_location = path
        self.setBackupButtonHighlight()
        self.rapidApp.resetupBackupDevices()

    @pyqtSlot()
    def photoFolderIdentifierChanged(self) -> None:
        name = self.photoFolderName.text()
        logging.info("Setting backup photo folder name to %s", name)
        self.prefs.photo_backup_identifier = name
        self.setBackupButtonHighlight()
        self.rapidApp.resetupBackupDevices()

    @pyqtSlot()
    def videoFolderIdentifierChanged(self) -> None:
        name = self.videoFolderName.text()
        logging.info("Setting backup video folder name to %s", name)
        self.prefs.video_backup_identifier = name
        self.setBackupButtonHighlight()
        self.rapidApp.resetupBackupDevices()

    def updateExample(self) -> None:
        """
        Update the example paths in the backup panel
        """

        if self.autoBackup.isChecked() and hasattr(self.rapidApp, 'backup_devices') and len(
                self.rapidApp.backup_devices):
            drives = self.rapidApp.backup_devices.sample_device_paths()
        else:
            # Translators: this value is used as an example device when automatic backup device
            # detection is enabled. You should translate this.
            drive1 = os.path.join(self.media_dir, _("drive1"))
            # Translators: this value is used as an example device when automatic backup device
            # detection is enabled. You should translate this.
            drive2 = os.path.join(self.media_dir, _("drive2"))
            drives = (
                os.path.join(path, identifier) for path, identifier in (
                    (drive1, self.prefs.photo_backup_identifier),
                    (drive2, self.prefs.photo_backup_identifier),
                    (drive2, self.prefs.video_backup_identifier)
                )
            )
        paths = '\n'.join(drives)
        self.autoBackupExample.setText(paths)

    def setBackupButtonHighlight(self) -> None:
        """
        Indicate error status in GUI by highlighting Backup button.

        Do so only if doing manual backups and there is a problem with one of the paths
        """

        self.rapidApp.backupButton.setHighlighted(
            self.prefs.backup_files and not self.prefs.backup_device_autodetection and (
                self.photoLocation.invalid_path or self.videoLocation.invalid_path))

    def enableControlsByBackupType(self) -> None:
        """
        Enable or disable backup controls depending on what the user
        has enabled.
        """

        backupsEnabled = self.backup.isChecked()
        autoEnabled = backupsEnabled and self.autoBackup.isChecked()
        manualEnabled = not autoEnabled and backupsEnabled

        for widget in self._backup_controls_type:
            widget.setEnabled(backupsEnabled)
        for widget in self._backup_controls_manual:
            widget.setEnabled(manualEnabled)
        for widget in self._backup_controls_auto:
            widget.setEnabled(autoEnabled)

    def updateLocationCombos(self) -> None:
        """
        Update backup locatation comboboxes in case directory status has changed.
        """
        for combo in self.photoLocation, self.videoLocation:
            combo.refreshFolderList()


class BackupPanel(QScrollArea):
    """
    Backup preferences widget, for photos and video backups while
    downloading.
    """

    def __init__(self,  parent) -> None:
        super().__init__(parent)

        assert parent is not None
        self.rapidApp = parent
        self.prefs = self.rapidApp.prefs  # type: Preferences

        self.backupDevices = BackupDeviceModel(parent=self)

        self.setFrameShape(QFrame.NoFrame)

        self.backupStoragePanel = QPanelView(
            label=_('Projected Backup Storage Use'),
            headerColor=QColor(ThumbnailBackgroundName),
            headerFontColor=QColor(Qt.white)
        )

        self.backupOptionsPanel = QPanelView(
            label=_('Backup Options'),
            headerColor=QColor(ThumbnailBackgroundName),
            headerFontColor=QColor(Qt.white)
        )

        self.backupDevicesView = BackupDeviceView(rapidApp=self.rapidApp, parent=self)
        self.backupStoragePanel.addWidget(self.backupDevicesView)
        self.backupDevicesView.setModel(self.backupDevices)
        self.backupDevicesView.setItemDelegate(BackupDeviceDelegate(rapidApp=self.rapidApp))
        self.backupDevicesView.setSizePolicy(
            QSizePolicy.MinimumExpanding, QSizePolicy.Fixed
        )
        self.backupOptionsPanel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)

        self.backupOptions = BackupOptionsWidget(
            prefs=self.prefs, parent=self, rapidApp=self.rapidApp
        )
        self.backupOptionsPanel.addWidget(self.backupOptions)

        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        widget.setLayout(layout)
        layout.addWidget(self.backupStoragePanel)
        layout.addWidget(self.backupOptionsPanel)
        # layout.addStretch()
        self.setWidget(widget)
        self.setWidgetResizable(True)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

    def updateExample(self) -> None:
        """
        Update the example paths in the backup panel
        """

        self.backupOptions.updateExample()

    def updateLocationCombos(self) -> None:
        """
        Update backup locatation comboboxes in case directory status has changed.
        """

        self.backupOptions.updateLocationCombos()

    def addBackupVolume(self, mount_details: BackupVolumeDetails) -> None:
        self.backupDevices.addBackupVolume(mount_details=mount_details)
        self.backupDevicesView.updateGeometry()

    def removeBackupVolume(self, path: str) -> None:
        self.backupDevices.removeBackupVolume(path=path)
        self.backupDevicesView.updateGeometry()

    def resetBackupDisplay(self) -> None:
        self.backupDevices.reset()
        self.backupDevicesView.updateGeometry()

    def setupBackupDisplay(self) -> None:
        """
        Sets up the backup view list regardless of whether backups
        are manual specified by the user, or auto-detection is on
        """

        if not self.prefs.backup_files:
            logging.debug("No backups configured: no backup destinations to display")
            return

        backup_devices = self.rapidApp.backup_devices  # type: BackupDeviceCollection
        if self.prefs.backup_device_autodetection:
            for path in backup_devices:
                self.backupDevices.addBackupVolume(
                    mount_details=backup_devices.get_backup_volume_details(path=path))
        else:
            # manually specified backup paths
            try:
                mounts = backup_devices.get_manual_mounts()
                if mounts is None:
                    return

                self.backupDevices.addBackupVolume(mount_details=mounts[0])
                if len(mounts) > 1:
                    self.backupDevices.addBackupVolume(mount_details=mounts[1])
            except Exception:
                logging.exception(
                    'An unexpected error occurred when adding backup destinations. Exception:'
                )
        self.backupDevicesView.updateGeometry()

    def setDownloadAttributes(self, marked: FileTypeCounter,
                              photos_size: int,
                              videos_size: int,
                              merge: bool) -> None:
        """
        Set the attributes used to generate the visual display of the
        files marked to be downloaded

        :param marked: number and type of files marked for download
        :param photos_size: size in bytes of photos marked for download
        :param videos_size: size in bytes of videos marked for download
        :param merge: whether to replace or add to the current values
        """

        self.backupDevices.setDownloadAttributes(
            marked=marked, photos_size=photos_size, videos_size=videos_size, merge=merge
        )

    def sufficientSpaceAvailable(self) -> bool:
        """
        Check to see that there is sufficient space with which to perform a download.

        :return: True or False value if sufficient space. Will always return True if
         backups are disabled or there are no backup devices.
        """
        if self.prefs.backup_files:
            return self.backupDevices.sufficientSpaceAvailable()
        else:
            return True

    def setDownloadingTo(self, downloading_to: DefaultDict[int, Set[FileType]]) -> None:
        self.backupDevices.downloading_to = downloading_to

