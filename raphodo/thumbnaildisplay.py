# SPDX-FileCopyrightText: Copyright 2015-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

import datetime
import logging
import os
from collections import defaultdict, deque
from collections.abc import Sequence
from typing import NamedTuple

import arrow.arrow
from colour import Color
from dateutil.tz import tzlocal
from PyQt5.QtCore import (
    QAbstractItemModel,
    QAbstractListModel,
    QEvent,
    QItemSelection,
    QItemSelectionModel,
    QModelIndex,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    QSizeF,
    Qt,
    QTimeLine,
    pyqtSignal,
    pyqtSlot,
)
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QGuiApplication,
    QMouseEvent,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
    QResizeEvent,
)
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QListView,
    QMenu,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionButton,
    QStyleOptionViewItem,
    QWidget,
)
from showinfm import show_in_file_manager

from raphodo.constants import (
    CustomColors,
    DarkGray,
    DarkModeThumbnailBackgroundName,
    DeviceState,
    DeviceType,
    DoubleDarkGray,
    Downloaded,
    DownloadStatus,
    FadeMilliseconds,
    FadeSteps,
    FileType,
    FileTypeFlag,
    PaleGray,
    Plural,
    Roles,
    Show,
    Sort,
    ThumbnailBackgroundName,
    ThumbnailCacheStatus,
    ThumbnailSize,
    extensionColor,
    manually_marked_previously_downloaded,
    thumbnail_margin,
)
from raphodo.internationalisation.install import install_gettext
from raphodo.internationalisation.utilities import make_internationalized_list
from raphodo.interprocess import (
    Device,
)
from raphodo.metadata.fileextensions import ALL_USER_VISIBLE_EXTENSIONS
from raphodo.prefs.preferences import Preferences  # noqa: F401
from raphodo.proximity import TemporalProximityState
from raphodo.rpdfile import FileTypeCounter, RPDFile
from raphodo.rpdsql import DownloadedSQL, ThumbnailRow, ThumbnailRowsSQL
from raphodo.storage.storage import (
    get_program_cache_directory,
    kframework_file_managers,
    validate_download_folder,
)
from raphodo.thumbnailer import Thumbnailer
from raphodo.tools.utilities import (
    CacheDirs,
    arrow_locale,
    data_file_path,
    format_size_for_user,
    runs,
)
from raphodo.ui.viewutils import (
    ScrollBarEmitsVisible,
    ThumbnailDataForProximity,
    is_dark_mode,
    scaledIcon,
)

install_gettext()


class DownloadStats:
    def __init__(self):
        self.no_photos = 0
        self.no_videos = 0
        self.photos_size_in_bytes = 0
        self.videos_size_in_bytes = 0
        self.post_download_thumb_generation = 0


class DownloadFiles(NamedTuple):
    files: defaultdict[int, list[RPDFile]]
    download_types: FileTypeFlag
    download_stats: defaultdict[int, DownloadStats]
    camera_access_needed: defaultdict[int, bool]


class MarkedSummary(NamedTuple):
    marked: FileTypeCounter
    size_photos_marked: int
    size_videos_marked: int


class AddBuffer:
    """
    Buffers thumbnail rows for display.

    Add thumbnail rows to the listview is a relatively expensive operation, as the
    model must be reset. Buffer the rows here, and then when big enough, flush it.
    """

    min_buffer_length = 10

    def __init__(self):
        self.initialize()
        self.buffer_length = self.min_buffer_length

    def initialize(self) -> None:
        self.buffer: dict[int, deque] = defaultdict(deque)

    def __len__(self):
        return sum(len(buffer) for buffer in self.buffer.values())

    def __getitem__(self, scan_id: int) -> deque:
        return self.buffer[scan_id]

    def should_flush(self) -> bool:
        return len(self) > self.buffer_length

    def reset(self, buffer_length: int) -> None:
        self.initialize()
        self.buffer_length = buffer_length

    def set_buffer_length(self, length: int) -> None:
        self.buffer_length = max(self.min_buffer_length, length)

    def extend(self, scan_id: int, thumbnail_rows: Sequence[ThumbnailRow]) -> None:
        self.buffer[scan_id].extend(thumbnail_rows)

    def purge(self, scan_id: int) -> None:
        if scan_id in self.buffer:
            logging.debug(
                "Purging %s thumbnails from buffer", len(self.buffer[scan_id])
            )
        del self.buffer[scan_id]


class ThumbnailListModel(QAbstractListModel):
    selectionReset = pyqtSignal()

    def __init__(self, parent, logging_port: int, log_gphoto2: bool) -> None:
        super().__init__(parent)
        self.rapidApp = parent
        self.prefs: Preferences = self.rapidApp.prefs

        self.thumbnailer_ready = False
        self.thumbnailer_generation_queue = []

        # track what devices are having thumbnails generated, by scan_id
        # see also DeviceCollection.thumbnailing

        # FIXME maybe this duplicated set is stupid
        self.generating_thumbnails: set[int] = set()

        # Sorting and filtering GUI defaults
        self.sort_by = Sort.modification_time
        self.sort_order = Qt.AscendingOrder
        self.show = Show.all

        self.initialize()

        no_workers = parent.prefs.max_cpu_cores
        self.thumbnailer = Thumbnailer(
            parent=parent,
            no_workers=no_workers,
            logging_port=logging_port,
            log_gphoto2=log_gphoto2,
        )
        self.thumbnailer.frontend_port.connect(self.rapidApp.initStage4)
        self.thumbnailer.thumbnailReceived.connect(self.thumbnailReceived)
        self.thumbnailer.cacheDirs.connect(self.cacheDirsReceived)
        self.thumbnailer.workerFinished.connect(self.thumbnailWorkerFinished)
        self.thumbnailer.cameraRemoved.connect(
            self.rapidApp.cameraRemovedWhileThumbnailing
        )
        # Connect to the signal that is emitted when a thumbnailing operation is
        # terminated by us, not merely finished
        self.thumbnailer.workerStopped.connect(self.thumbnailWorkerStopped)
        self.arrow_locale_for_humanize = arrow_locale(self.prefs.language)
        logging.debug("Setting arrow locale to %s", self.arrow_locale_for_humanize)

    def initialize(self) -> None:
        # uid: QPixmap
        self.thumbnails: dict[bytes, QPixmap] = {}

        self.add_buffer = AddBuffer()

        # Proximity filtering
        self.proximity_col1: list[int] = []
        self.proximity_col2: list[int] = []

        # scan_id
        self.removed_devices: set[int] = set()

        # Files are hidden when the combo box "Show" in the main window is set to
        # "New" instead of the default "All".

        # uid: RPDFile
        self.rpd_files: dict[bytes, RPDFile] = {}

        # In memory database to hold all thumbnail rows
        self.tsql = ThumbnailRowsSQL()

        # Rows used to render the thumbnail view - contains query result of the DB
        # Each list element corresponds to a row in the thumbnail view such that
        # index 0 in the list is row 0 in the view
        # [(uid, marked)]
        self.rows: list[tuple[bytes, bool]] = []
        # {uid: row}
        self.uid_to_row: dict[bytes, int] = {}

        size = QSize(106, 106)
        self.photo_icon = scaledIcon(data_file_path("thumbnail/photo.svg")).pixmap(size)
        self.video_icon = scaledIcon(data_file_path("thumbnail/video.svg")).pixmap(size)

        self.total_thumbs_to_generate = 0
        self.thumbnails_generated = 0
        self.no_thumbnails_by_scan = defaultdict(int)

        # scan_id
        self.ctimes_differ: list[int] = []

        # Highlight thumbnails when from a particular device when there is more than one
        # device.
        # Thumbnails to highlight by uid
        self.currently_highlighting_scan_id: int | None = None
        self.currently_highlighting_tp_row: int | None = None
        self._resetHighlightingValues()
        self.highlightingTimeline = QTimeLine(FadeMilliseconds // 2)
        self.highlightingTimeline.setCurveShape(QTimeLine.SineCurve)
        self.highlightingTimeline.frameChanged.connect(self.doHighlightThumbs)
        self.highlightingTimeline.finished.connect(self.highlightPhaseFinished)
        self.highlighting_timeline_max = FadeSteps
        self.highlighting_timeline_mint = 0
        self.highlightingTimeline.setFrameRange(
            self.highlighting_timeline_mint, self.highlighting_timeline_max
        )
        self.highlight_value = 0

        self._resetRememberSelection()

    def stopThumbnailer(self) -> None:
        self.thumbnailer.stop()

    @pyqtSlot(int)
    def thumbnailWorkerFinished(self, scan_id: int) -> None:
        self.generating_thumbnails.remove(scan_id)

    @pyqtSlot(int)
    def thumbnailWorkerStopped(self, scan_id: int) -> None:
        self.generating_thumbnails.remove(scan_id)
        self.rapidApp.thumbnailGenerationStopped(scan_id=scan_id)

    def logState(self) -> None:
        logging.debug("-- Thumbnail Model --")

        db_length = self.tsql.get_count()
        db_length_and_buffer_length = db_length + len(self.add_buffer)
        if len(
            self.thumbnails
        ) != db_length_and_buffer_length or db_length_and_buffer_length != len(
            self.rpd_files
        ):
            logging.error(
                "Conflicting values: %s thumbnails; %s database rows; %s rpd_files",
                len(self.thumbnails),
                db_length,
                len(self.rpd_files),
            )
        else:
            logging.debug(
                "%s thumbnails (%s marked)", db_length, self.tsql.get_count(marked=True)
            )

        logging.debug(
            "%s not downloaded; %s downloaded; %s previously downloaded",
            self.tsql.get_count(downloaded=False),
            self.tsql.get_count(downloaded=True),
            self.tsql.get_count(previously_downloaded=True),
        )

        if self.total_thumbs_to_generate:
            logging.debug(
                "%s to be generated; %s generated",
                self.total_thumbs_to_generate,
                self.thumbnails_generated,
            )

        scan_ids = self.tsql.get_all_devices()
        active_devices = ", ".join(
            self.rapidApp.devices[scan_id].display_name
            for scan_id in scan_ids
            if scan_id not in self.removed_devices
        )
        if len(self.removed_devices):
            logging.debug(
                "Active devices: %s (%s removed)",
                active_devices,
                len(self.removed_devices),
            )
        else:
            logging.debug("Active devices: %s", active_devices)

    def validateModelConsistency(self):
        logging.debug("Validating thumbnail model consistency...")

        for idx, row in enumerate(self.rows):
            uid = row[0]
            if self.rpd_files.get(uid) is None:
                raise KeyError(f"Missing key in rpd files at row {idx}")
            if self.thumbnails.get(uid) is None:
                raise KeyError(f"Missing key in thumbnails at row {idx}")

        [self.tsql.validate_uid(uid=row[0]) for row in self.rows]
        for uid, row in self.uid_to_row.items():
            assert self.rows[row][0] == uid
        for uid in self.tsql.get_uids():
            assert uid in self.rpd_files
            assert uid in self.thumbnails
        logging.debug("...thumbnail model looks okay")

    def refresh(self, suppress_signal=False, rememberSelection=False) -> None:
        """
        Refresh thumbnail view after files have been added, the proximity filters
        are used, or the sort criteria is changed.

        :param suppress_signal: if True don't emit signals that layout is changing
        :param rememberSelection: remember which uids were selected before change,
         and reselect them
        """

        if rememberSelection:
            self.rememberSelection()

        if not suppress_signal:
            self.layoutAboutToBeChanged.emit()

        self.rows = self.tsql.get_view(
            sort_by=self.sort_by,
            sort_order=self.sort_order,
            show=self.show,
            proximity_col1=self.proximity_col1,
            proximity_col2=self.proximity_col2,
        )
        self.uid_to_row = {row[0]: idx for idx, row in enumerate(self.rows)}

        if not suppress_signal:
            self.layoutChanged.emit()

        if rememberSelection:
            self.reselect()

    def _selectionModel(self) -> QItemSelectionModel:
        return self.rapidApp.thumbnailView.selectionModel()

    def rememberSelection(self):
        selection = self._selectionModel()
        selected: QItemSelection = selection.selection()
        self.remember_selection_all_selected = len(selected) == len(self.rows)
        if not self.remember_selection_all_selected:
            self.remember_selection_selected_uids = [
                self.rows[index.row()][0] for index in selected.indexes()
            ]
            selection.reset()

    def reselect(self):
        if not self.remember_selection_all_selected:
            selection: QItemSelectionModel = (
                self.rapidApp.thumbnailView.selectionModel()
            )
            new_selection: QItemSelection = QItemSelection()
            rows = [
                self.uid_to_row[uid]
                for uid in self.remember_selection_selected_uids
                if uid in self.uid_to_row
            ]
            rows.sort()
            for first, last in runs(rows):
                new_selection.select(self.index(first, 0), self.index(last, 0))

            selection.select(new_selection, QItemSelectionModel.Select)

            for first, last in runs(rows):
                self.dataChanged.emit(self.index(first, 0), self.index(last, 0))

    def _resetRememberSelection(self):
        self.remember_selection_all_selected: bool | None = None
        self.remember_selection_selected_uids: list[bytes] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.rows)

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags

        row = index.row()
        if row >= len(self.rows) or row < 0:
            return Qt.NoItemFlags

        uid = self.rows[row][0]
        rpd_file: RPDFile = self.rpd_files[uid]

        if rpd_file.status == DownloadStatus.not_downloaded:
            return super().flags(index) | Qt.ItemIsEnabled | Qt.ItemIsSelectable
        else:
            return Qt.NoItemFlags

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        if row >= len(self.rows) or row < 0:
            return None

        uid = self.rows[row][0]
        rpd_file: RPDFile = self.rpd_files[uid]

        if role == Qt.DisplayRole:
            # This is never displayed, but is (was?) used for filtering!
            return rpd_file.modification_time
        elif role == Roles.highlight:
            if self.currently_highlighting_scan_id is not None:
                if rpd_file.scan_id == self.currently_highlighting_scan_id:
                    return self.highlight_value
                else:
                    return 0
            elif self.currently_highlighting_tp_row is not None:
                if uid in self.current_highlight_uids:
                    return self.highlight_value
                else:
                    return 0
            return 0
        elif role == Qt.DecorationRole:
            return self.thumbnails[uid]
        elif role == Qt.CheckStateRole:
            if self.rows[row][1]:
                return Qt.Checked
            else:
                return Qt.Unchecked
        elif role == Roles.sort_extension:
            return rpd_file.extension
        elif role == Roles.filename:
            return rpd_file.name
        elif role == Roles.previously_downloaded:
            return rpd_file.previously_downloaded
        elif role == Roles.extension:
            return rpd_file.extension, rpd_file.extension_type
        elif role == Roles.download_status:
            return rpd_file.status
        elif role == Roles.job_code:
            return rpd_file.job_code
        elif role == Roles.has_audio:
            return rpd_file.has_audio()
        elif role == Roles.secondary_attribute:
            if rpd_file.xmp_file_full_name:
                return "XMP"
            elif rpd_file.log_file_full_name:
                return "LOG"
            else:
                return None
        elif role == Roles.path:
            if rpd_file.status in Downloaded:
                return rpd_file.download_full_file_name
            else:
                return rpd_file.full_file_name
        elif role == Roles.uri:
            return rpd_file.get_uri()
        elif role == Roles.camera_memory_card:
            return rpd_file.camera_memory_card_identifiers
        elif role == Roles.mtp:
            return rpd_file.is_mtp_device
        elif role == Roles.scan_id:
            return rpd_file.scan_id
        elif role == Roles.is_camera:
            return rpd_file.from_camera
        elif role == Qt.ToolTipRole:
            devices = self.rapidApp.devices
            if len(devices) > 1:
                # To account for situations where the device has been removed, use
                # the display name from the device archive
                device_name = devices.device_archive[rpd_file.scan_id].name
            else:
                device_name = ""
            size = format_size_for_user(rpd_file.size)
            mtime = arrow.get(rpd_file.modification_time)

            try:
                mtime_h = mtime.humanize(locale=self.arrow_locale_for_humanize)
            except Exception:
                mtime_h = mtime.humanize()
                logging.debug(
                    "Failed to humanize modification time %s with locale %s, reverting "
                    "to English",
                    mtime_h,
                    self.arrow_locale_for_humanize,
                )

            if rpd_file.ctime_mtime_differ():
                ctime = arrow.get(rpd_file.ctime)

                # Sadly, arrow raises an exception if it's locale is not translated
                # when using humanize. So attempt conversion using user's locale, and if
                # that fails, use English.

                try:
                    ctime_h = ctime.humanize(locale=self.arrow_locale_for_humanize)
                except Exception:
                    ctime_h = ctime.humanize()
                    logging.debug(
                        "Failed to humanize taken on time %s with locale %s, reverting "
                        "to English",
                        ctime_h,
                        self.arrow_locale_for_humanize,
                    )

                # Translators: %(variable)s represents Python code, not a plural of the
                # term variable. You must keep the %(variable)s untranslated, or the
                # program will crash.
                humanized_ctime = _(
                    "Taken on %(date_time)s (%(human_readable)s)"
                ) % dict(
                    date_time=ctime.to("local").naive.strftime("%c"),
                    human_readable=ctime_h,
                )

                # Translators: %(variable)s represents Python code, not a plural of the
                # term variable. You must keep the %(variable)s untranslated, or the
                # program will crash.
                humanized_mtime = _(
                    "Modified on %(date_time)s (%(human_readable)s)"
                ) % dict(
                    date_time=mtime.to("local").naive.strftime("%c"),
                    human_readable=mtime_h,
                )
                humanized_file_time = f"{humanized_ctime}<br>{humanized_mtime}"
            else:
                # Translators: %(variable)s represents Python code, not a plural of the
                # term variable. You must keep the %(variable)s untranslated, or the
                # program will crash.
                humanized_file_time = _("%(date_time)s (%(human_readable)s)") % dict(
                    date_time=mtime.to("local").naive.strftime("%c"),
                    human_readable=mtime_h,
                )

            humanized_file_time = humanized_file_time.replace(" ", "&nbsp;")

            if not device_name:
                msg = f"<b>{rpd_file.name}</b><br>{humanized_file_time}<br>{size}"
            else:
                msg = (
                    f"<b>{rpd_file.name}</b><br>{device_name}"
                    f"<br>{humanized_file_time}<br>{size}"
                )

            if rpd_file.camera_memory_card_identifiers:
                if len(rpd_file.camera_memory_card_identifiers) > 1:
                    cards = _("Memory cards: %s") % make_internationalized_list(
                        [str(i) for i in rpd_file.camera_memory_card_identifiers]
                    )
                else:
                    cards = (
                        _("Memory card: %s")
                        % rpd_file.camera_memory_card_identifiers[0]
                    )
                msg += "<br>" + cards

            if rpd_file.status in Downloaded:
                path = rpd_file.download_path + os.sep
                downloaded_as = _("Downloaded as:")
                msg += (
                    f"<br><br><i>{downloaded_as}</i>"
                    f"<br>{rpd_file.download_name}<br>{path}"
                )

            if rpd_file.previously_downloaded:
                prev_datetime = arrow.get(rpd_file.prev_datetime, tzlocal())
                try:
                    prev_dt_h = prev_datetime.humanize(
                        locale=self.arrow_locale_for_humanize
                    )
                except Exception:
                    prev_dt_h = prev_datetime.humanize()
                    logging.debug(
                        "Failed to humanize taken on time %s with locale %s, reverting "
                        "to English",
                        prev_dt_h,
                        self.arrow_locale_for_humanize,
                    )
                # Translators: %(variable)s represents Python code, not a plural of the
                # term variable. You must keep the %(variable)s untranslated, or the
                # program will crash.
                prev_date = _("%(date_time)s (%(human_readable)s)") % dict(
                    date_time=prev_datetime.naive.strftime("%c"),
                    human_readable=prev_dt_h,
                )

                if rpd_file.prev_full_name != manually_marked_previously_downloaded:
                    path, prev_file_name = os.path.split(rpd_file.prev_full_name)
                    path += os.sep
                    # Translators: %(variable)s represents Python code, not a plural of
                    # the term variable. You must keep the %(variable)s untranslated, or
                    # the program will crash.
                    # Translators: please do not change HTML codes like <br>, <i>, </i>,
                    # or <b>, </b> etc.
                    msg += _(
                        "<br><br>Previous download:<br>%(filename)s<br>%(path)s<br>"
                        "%(date)s"
                    ) % dict(date=prev_date, filename=prev_file_name, path=path)
                else:
                    # Translators: %(variable)s represents Python code, not a plural of
                    # the term variable. You must keep the %(variable)s untranslated, or
                    # the program will crash.
                    # Translators: please do not change HTML codes like <br>, <i>, </i>,
                    # or <b>, </b> etc.
                    msg += _(
                        "<br><br>"
                        "<i>Manually set as previously downloaded on %(date)s</i>"
                    ) % dict(date=prev_date)
            return msg

    def setData(self, index: QModelIndex, value, role: int) -> bool:
        if not index.isValid():
            return False

        row = index.row()
        if row >= len(self.rows) or row < 0:
            return False
        uid = self.rows[row][0]
        if role == Qt.CheckStateRole:
            self.tsql.set_marked(uid=uid, marked=value)
            self.rows[row] = (uid, value is True)
            self.dataChanged.emit(index, index)
            return True
        elif role == Roles.job_code:
            self.rpd_files[uid].job_code = value
            self.tsql.set_job_code_assigned(uids=[uid], job_code=True)
            self.dataChanged.emit(index, index)
            return True
        return False

    def setDataRange(self, indexes: tuple[QModelIndex], value, role: int) -> bool:
        """
        Modify a range of indexes simultaneously
        :param indexes: the indexes
        :param value: new value to assign
        :param role: the role the value is associated with
        :return: True
        """
        valid_rows = (index.row() for index in indexes if index.isValid())
        rows = [row for row in valid_rows if 0 <= row < len(self.rows)]
        rows.sort()
        uids = [self.rows[row][0] for row in rows]

        if role == Roles.previously_downloaded:
            logging.debug(
                "Manually setting %s files as previously downloaded", len(uids)
            )
            # Set the files as unmarked
            self.tsql.set_list_marked(uids=uids, marked=False)
            for row, uid in zip(rows, uids):
                self.rows[row] = (uid, False)
            # Set the files as previously downloaded
            self.tsql.set_list_previously_downloaded(
                uids=uids, previously_downloaded=value
            )
            d = DownloadedSQL()
            now = datetime.datetime.now()
            for uid in uids:
                rpd_file = self.rpd_files[uid]
                rpd_file.previously_downloaded = value
                rpd_file.prev_full_name = manually_marked_previously_downloaded
                rpd_file.prev_datetime = now
                d.add_downloaded_file(
                    name=rpd_file.name,
                    size=rpd_file.size,
                    modification_time=rpd_file.modification_time,
                    download_full_file_name=manually_marked_previously_downloaded,
                )
            # Update Timeline formatting, if needed
            self.rapidApp.temporalProximity.previouslyDownloadedManuallySet(uids=uids)

        # Indicate to the list view that the rows have changed
        for first, last in runs(rows):
            self.dataChanged.emit(self.index(first, 0), self.index(last, 0))
        return True

    def assignJobCodesToMarkedFilesWithNoJobCode(self, job_code: str) -> None:
        """
        Called when assigning job codes when a download is initiated and not all
        files have had a job code assigned to them.

        :param job_code: job code to assign
        """

        uids = self.tsql.get_uids(marked=True, job_code=False)
        logging.debug(
            "Assigning job code to %s files because a download was initiated", len(uids)
        )
        for uid in uids:
            self.rpd_files[uid].job_code = job_code
            rows = [self.uid_to_row[uid] for uid in uids if uid in self.uid_to_row]
            rows.sort()
            for first, last in runs(rows):
                self.dataChanged.emit(self.index(first, 0), self.index(last, 0))
        self.tsql.set_job_code_assigned(uids=uids, job_code=True)

    def updateDisplayPostDataChange(self, scan_id: int | None = None):
        if scan_id is not None:
            scan_ids = [scan_id]
        else:
            scan_ids = (scan_id for scan_id in self.rapidApp.devices)
        for scan_id in scan_ids:
            self.updateDeviceDisplayCheckMark(scan_id=scan_id)
        self.rapidApp.displayMessageInStatusBar()
        self.rapidApp.setDownloadCapabilities()

    def removeRows(self, position, rows=1, index=QModelIndex()) -> bool:
        """
        Removes Python list rows only, i.e. self.rows.

        Does not touch database or other variables.
        """

        self.beginRemoveRows(QModelIndex(), position, position + rows - 1)
        del self.rows[position : position + rows]
        self.endRemoveRows()
        return True

    def addOrUpdateDevice(self, scan_id: int) -> None:
        device_name = self.rapidApp.devices[scan_id].display_name
        self.tsql.add_or_update_device(scan_id=scan_id, device_name=device_name)

    def addFiles(
        self, scan_id: int, rpd_files: list[RPDFile], generate_thumbnail: bool
    ) -> None:
        if not rpd_files:
            return

        thumbnail_rows = deque(maxlen=len(rpd_files))

        for rpd_file in rpd_files:
            uid = rpd_file.uid
            self.rpd_files[uid] = rpd_file

            if rpd_file.file_type == FileType.photo:
                self.thumbnails[uid] = self.photo_icon
            else:
                self.thumbnails[uid] = self.video_icon

            if generate_thumbnail:
                self.total_thumbs_to_generate += 1
                self.no_thumbnails_by_scan[rpd_file.scan_id] += 1

            tr = ThumbnailRow(
                uid=uid,
                scan_id=rpd_file.scan_id,
                mtime=rpd_file.modification_time,
                marked=not rpd_file.previously_downloaded,
                file_name=rpd_file.name,
                extension=rpd_file.extension,
                file_type=rpd_file.file_type,
                downloaded=False,
                previously_downloaded=rpd_file.previously_downloaded,
                job_code=False,
                proximity_col1=-1,
                proximity_col2=-1,
            )

            thumbnail_rows.append(tr)

        self.add_buffer.extend(scan_id=scan_id, thumbnail_rows=thumbnail_rows)

        if self.add_buffer.should_flush():
            self.flushAddBuffer()
            marked_summary = self.getMarkedSummary()
            destinations_good = self.rapidApp.updateDestinationViews(
                marked_summary=marked_summary
            )
            self.rapidApp.destinationButton.setHighlighted(not destinations_good)
            if self.prefs.backup_files:
                backups_good = self.rapidApp.updateBackupView(
                    marked_summary=marked_summary
                )
            else:
                backups_good = True
            self.rapidApp.destinationButton.setHighlighted(not destinations_good)
            self.rapidApp.backupButton.setHighlighted(not backups_good)

    def flushAddBuffer(self):
        if len(self.add_buffer):
            self.beginResetModel()

            for buffer in self.add_buffer.buffer.values():
                self.tsql.add_thumbnail_rows(thumbnail_rows=buffer)
            self.refresh(suppress_signal=True)

            self.add_buffer.reset(buffer_length=len(self.rows))

            self.endResetModel()

            self._resetHighlightingValues()
            self._resetRememberSelection()

    def getMarkedSummary(self) -> MarkedSummary:
        """
        :return: summary of files marked for download including sizes in bytes
        """

        size_photos_marked = self.getSizeOfFilesMarkedForDownload(FileType.photo)
        size_videos_marked = self.getSizeOfFilesMarkedForDownload(FileType.video)
        marked = self.getNoFilesAndTypesMarkedForDownload()
        return MarkedSummary(
            marked=marked,
            size_photos_marked=size_photos_marked,
            size_videos_marked=size_videos_marked,
        )

    def setFileSort(self, sort: Sort, order: Qt.SortOrder, show: Show) -> None:
        if self.sort_by != sort or self.sort_order != order or self.show != show:
            logging.debug(
                "Changing layout due to sort change: %s, %s, %s", sort, order, show
            )
            self.sort_by = sort
            self.sort_order = order
            self.show = show
            self.refresh(rememberSelection=True)

    @pyqtSlot(int, CacheDirs)
    def cacheDirsReceived(self, scan_id: int, cache_dirs: CacheDirs) -> None:
        self.rapidApp.fileSystemFilter.setTempDirs(
            [cache_dirs.photo_cache_dir, cache_dirs.video_cache_dir]
        )
        if scan_id in self.rapidApp.devices:
            self.rapidApp.devices[scan_id].photo_cache_dir = cache_dirs.photo_cache_dir
            self.rapidApp.devices[scan_id].video_cache_dir = cache_dirs.video_cache_dir

    @pyqtSlot(RPDFile, QPixmap)
    def thumbnailReceived(self, rpd_file: RPDFile, thumbnail: QPixmap) -> None:
        """
        A thumbnail has been generated by either the dedicated thumbnailing phase, or
        during the download by a daemon process.

        :param rpd_file: details of the file the thumbnail was geneerated for
        :param thumbnail: If isNull(), the thumbnail either could not be generated or
         did not need to be (because it already had been). Otherwise, this is
         the thumbnail to display.
        """

        uid = rpd_file.uid
        scan_id = rpd_file.scan_id

        if uid not in self.rpd_files or scan_id not in self.rapidApp.devices:
            # A thumbnail has been generated for a no longer displayed file
            return

        download_is_running = self.rapidApp.downloadIsRunning()

        if (
            rpd_file.mdatatime_caused_ctime_change
            and not rpd_file.modified_via_daemon_process
        ):
            rpd_file.mdatatime_caused_ctime_change = False
            if scan_id not in self.ctimes_differ:
                self.addCtimeDisparity(rpd_file=rpd_file)

        if not rpd_file.modified_via_daemon_process and self.rpd_files[uid].status in (
            DownloadStatus.not_downloaded,
            DownloadStatus.download_pending,
        ):
            # Only update the rpd_file if the file has not already been downloaded
            # TODO consider merging this no matter what the status
            if self.rpd_files[uid].job_code is not None:
                rpd_file.job_code = self.rpd_files[uid].job_code
            self.rpd_files[uid] = rpd_file

        if not thumbnail.isNull():
            self.thumbnails[uid] = thumbnail
            # The thumbnail may or may not be displayed at this moment
            row = self.uid_to_row.get(uid)
            if row is not None:
                # logging.debug("Updating thumbnail row %s with new thumbnail", row)
                self.dataChanged.emit(self.index(row, 0), self.index(row, 0))
        else:
            logging.debug("Thumbnail was null: %s", rpd_file.name)

        if not rpd_file.modified_via_daemon_process:
            self.thumbnails_generated += 1
            self.no_thumbnails_by_scan[scan_id] -= 1
            log_state = False
            if self.no_thumbnails_by_scan[scan_id] == 0:
                if self.rapidApp.deviceState(scan_id) == DeviceState.thumbnailing:
                    self.rapidApp.devices.set_device_state(scan_id, DeviceState.idle)
                device = self.rapidApp.devices[scan_id]
                logging.info("Finished thumbnail generation for %s", device.name())

                if scan_id in self.ctimes_differ:
                    uids = self.tsql.get_uids_for_device(scan_id=scan_id)
                    rpd_files = [self.rpd_files[uid] for uid in uids]
                    self.rapidApp.folder_preview_manager.add_rpd_files(
                        rpd_files=rpd_files
                    )
                    self.processCtimeDisparity(scan_id=scan_id)
                log_state = True

            if self.thumbnails_generated == self.total_thumbs_to_generate:
                self.thumbnails_generated = 0
                self.total_thumbs_to_generate = 0
                if not download_is_running:
                    self.rapidApp.updateProgressBarState()
            elif self.total_thumbs_to_generate and not download_is_running:
                self.rapidApp.updateProgressBarState(thumbnail_generated=True)

            if not download_is_running:
                self.rapidApp.displayMessageInStatusBar()

            if log_state:
                self.logState()

        else:
            self.rapidApp.thumbnailGeneratedPostDownload(rpd_file=rpd_file)

    def addCtimeDisparity(self, rpd_file: RPDFile) -> None:
        """
        Track the fact that there was a disparity between the creation time and
        modification time for a file, that was identified either during a download
        or during a scan
        :param rpd_file: sample rpd_file (scan id of the device will be taken from it)
        """

        logging.info(
            "Metadata time differs from file modification time for "
            "%s (with possibly more to come, but these will not be logged)",
            rpd_file.full_file_name,
        )

        scan_id = rpd_file.scan_id
        self.ctimes_differ.append(scan_id)
        self.rapidApp.temporalProximity.setState(TemporalProximityState.ctime_rebuild)
        if not self.rapidApp.downloadIsRunning():
            self.rapidApp.folder_preview_manager.remove_folders_for_device(
                scan_id=scan_id
            )

    def processCtimeDisparity(self, scan_id: int) -> None:
        """
        A device that had a disparity between the creation time and
        modification time for a file has been fully downloaded from.

        :param scan_id:
        :return:
        """
        self.ctimes_differ.remove(scan_id)
        if not self.ctimes_differ:
            self.rapidApp.temporalProximity.setState(
                TemporalProximityState.ctime_rebuild_proceed
            )
            self.rapidApp.generateTemporalProximityTableData(
                reason="a photo or video's creation time differed from its file system "
                "modification time"
            )

    def _get_cache_location(self, download_folder: str) -> str:
        if validate_download_folder(download_folder).valid:
            return download_folder
        else:
            folder = get_program_cache_directory(create_if_not_exist=True)
            if folder is not None:
                return folder
            else:
                return os.path.expanduser("~")

    def getCacheLocations(self) -> CacheDirs:
        photo_cache_folder = self._get_cache_location(
            self.rapidApp.prefs.photo_download_folder
        )
        video_cache_folder = self._get_cache_location(
            self.rapidApp.prefs.video_download_folder
        )
        return CacheDirs(photo_cache_folder, video_cache_folder)

    def generateThumbnails(self, scan_id: int, device: Device) -> None:
        """Initiates generation of thumbnails for the device."""

        if scan_id not in self.removed_devices:
            self.generating_thumbnails.add(scan_id)
            self.rapidApp.updateProgressBarState()
            cache_dirs = self.getCacheLocations()
            uids = self.tsql.get_uids_for_device(scan_id=scan_id)
            rpd_files = list(self.rpd_files[uid] for uid in uids)

            need_video_cache_dir = need_photo_cache_dir = False
            if device.device_type == DeviceType.camera:
                need_video_cache_dir = (
                    device.entire_video_required
                    or self.tsql.any_files_of_type(scan_id, FileType.video)
                )
                # defer check to see if ExifTool is needed until later
                need_photo_cache_dir = device.entire_photo_required
                camera_model = device.camera_model
                camera_port = device.camera_port
                is_mtp_device = device.is_mtp_device
            else:
                camera_model = None
                camera_port = None
                is_mtp_device = None

            gen_args = (
                scan_id,
                rpd_files,
                device.name(),
                self.rapidApp.prefs.proximity_seconds,
                cache_dirs,
                need_photo_cache_dir,
                need_video_cache_dir,
                camera_model,
                camera_port,
                is_mtp_device,
                device.entire_video_required,
                device.entire_photo_required,
            )
            self.thumbnailer.generateThumbnails(*gen_args)

    def resetThumbnailTracking(self):
        self.thumbnails_generated = 0
        self.total_thumbs_to_generate = 0

    def _deleteRows(self, uids: list[bytes]) -> None:
        """
        Delete a list of thumbnails from the thumbnail display

        :param uids: files to remove
        """

        rows = [self.uid_to_row[uid] for uid in uids]

        if rows:
            # Generate groups of rows, and remove that group
            # Must do it in reverse!
            rows.sort()
            rrows = reversed(list(runs(rows)))
            for first, last in rrows:
                no_rows = last - first + 1
                self.removeRows(first, no_rows)

            self.uid_to_row = {row[0]: idx for idx, row in enumerate(self.rows)}

    def purgeRpdFiles(self, uids: list[bytes]) -> None:
        for uid in uids:
            del self.thumbnails[uid]
            del self.rpd_files[uid]

    def clearAll(
        self, scan_id: int | None = None, keep_downloaded_files: bool = False
    ) -> bool:
        """
        Removes files from display and internal tracking.

        If scan_id is not None, then only files matching that scan_id
        will be removed. Otherwise, everything will be removed, regardless of
        the keep_downloaded_files parameter.

        If keep_downloaded_files is True, files will not be removed if
        they have been downloaded.

        Two aspects to this task:
         1. remove files list of rows which drive the list view display
         2. remove files from backend DB and from thumbnails and rpd_files lists.

        :param scan_id: if None, keep_downloaded_files must be False
        :param keep_downloaded_files: don't remove thumbnails if they represent
         files that have now been downloaded. Ignored if no device is passed.
        :return: True if any thumbnail was removed (irrespective of whether
        it was displayed at this moment), else False
        """

        if scan_id is None and not keep_downloaded_files:
            files_removed = self.tsql.any_files()
            logging.debug("Clearing all thumbnails for all devices")
            self.initialize()
            return files_removed
        else:
            assert scan_id is not None

            if not keep_downloaded_files:
                files_removed = self.tsql.any_files(scan_id=scan_id)
            else:
                files_removed = self.tsql.any_files_to_download(scan_id=scan_id)

            if keep_downloaded_files:
                logging.debug(
                    "Clearing all non-downloaded thumbnails for scan id %s", scan_id
                )
            else:
                logging.debug("Clearing all thumbnails for scan id %s", scan_id)
            # Generate list of displayed thumbnails to remove
            if keep_downloaded_files:
                uids = self.getDisplayedUids(scan_id=scan_id)
            else:
                uids = self.getDisplayedUids(scan_id=scan_id, downloaded=None)

            self._deleteRows(uids)

            # Delete from DB and thumbnails and rpd_files lists
            if keep_downloaded_files:
                uids = self.tsql.get_uids(scan_id=scan_id, downloaded=False)
            else:
                uids = self.tsql.get_uids(scan_id=scan_id)

            logging.debug("Removing %s thumbnail and rpd_files rows", len(uids))
            self.purgeRpdFiles(uids)

            uids = [row.uid for row in self.add_buffer[scan_id]]
            if uids:
                logging.debug(
                    "Removing additional %s thumbnail and rpd_files rows", len(uids)
                )
                self.purgeRpdFiles(uids)

            self.add_buffer.purge(scan_id=scan_id)
            self.add_buffer.set_buffer_length(len(self.rows))

            if keep_downloaded_files:
                self.tsql.delete_files_by_scan_id(scan_id=scan_id, downloaded=False)
            else:
                self.tsql.delete_files_by_scan_id(scan_id=scan_id)

            self.removed_devices.add(scan_id)

            if scan_id in self.no_thumbnails_by_scan:
                self.recalculateThumbnailsPercentage(scan_id=scan_id)
            self.rapidApp.displayMessageInStatusBar()

            if self.tsql.get_count(scan_id=scan_id) == 0:
                self.tsql.delete_device(scan_id=scan_id)

            if scan_id in self.ctimes_differ:
                self.ctimes_differ.remove(scan_id)

            # self.validateModelConsistency()

            return files_removed

    def clearCompletedDownloads(self) -> None:
        logging.debug("Clearing all completed download thumbnails")

        # Get uids for complete downloads that are currently displayed
        uids = self.getDisplayedUids(downloaded=True)
        self._deleteRows(uids)

        # Now get uids of all downloaded files, regardless of whether they're
        # displayed at the moment
        uids = self.tsql.get_uids(downloaded=True)
        logging.debug("Removing %s thumbnail and rpd_files rows", len(uids))
        self.purgeRpdFiles(uids)

        # Delete the files from the internal database that drives the display
        self.tsql.delete_uids(uids)

    def filesAreMarkedForDownload(self, scan_id: int | None = None) -> bool:
        """
        Checks for the presence of checkmark besides any file that has
        not yet been downloaded.

        :param: scan_id: if specified, only for that device
        :return: True if there is any file that the user has indicated
        they intend to download, else False.
        """

        return self.tsql.any_files_marked(scan_id=scan_id)

    def getNoFilesMarkedForDownload(self) -> int:
        return self.tsql.get_count(marked=True)

    def getNoHiddenFiles(self) -> int:
        if self.rapidApp.showOnlyNewFiles():
            return self.tsql.get_count(previously_downloaded=True, downloaded=False)
        else:
            return 0

    def getNoFilesAndTypesMarkedForDownload(self) -> FileTypeCounter:
        no_photos = self.tsql.get_count(marked=True, file_type=FileType.photo)
        no_videos = self.tsql.get_count(marked=True, file_type=FileType.video)
        f = FileTypeCounter()
        f[FileType.photo] = no_photos
        f[FileType.video] = no_videos
        return f

    def getSizeOfFilesMarkedForDownload(self, file_type: FileType) -> int:
        uids = self.tsql.get_uids(marked=True, file_type=file_type)
        return sum(self.rpd_files[uid].size for uid in uids)

    def getNoFilesAvailableForDownload(self) -> FileTypeCounter:
        no_photos = self.tsql.get_count(downloaded=False, file_type=FileType.photo)
        no_videos = self.tsql.get_count(downloaded=False, file_type=FileType.video)
        f = FileTypeCounter()
        f[FileType.photo] = no_photos
        f[FileType.video] = no_videos
        return f

    def getNoFilesSelected(self) -> FileTypeCounter:
        selection = self._selectionModel()
        selected: QItemSelection = selection.selection()

        if len(selected) != len(self.rows):
            # not all files are selected
            selected_uids = [self.rows[index.row()][0] for index in selected.indexes()]
            return FileTypeCounter(
                self.rpd_files[uid].file_type for uid in selected_uids
            )
        else:
            return self.getDisplayedCounter()

    def getCountNotPreviouslyDownloadedAvailableForDownload(self) -> int:
        return self.tsql.get_count(previously_downloaded=False, downloaded=False)

    def getAllDownloadableRPDFiles(self) -> list[RPDFile]:
        uids = self.tsql.get_uids(downloaded=False)
        return [self.rpd_files[uid] for uid in uids]

    def getFilesMarkedForDownload(self, scan_id: int | None) -> DownloadFiles:
        """
        Returns a dict of scan ids and associated files the user has
        indicated they want to download, and whether there are photos
        or videos included in the download.

        Exclude files from which a device is still scanning.

        :param scan_id: if not None, then returns those files only from
        the device associated with that scan_id
        :return: namedtuple DownloadFiles with defaultdict() indexed by
        scan_id with value List(rpd_file), and defaultdict() indexed by
        scan_id with value DownloadStats
        """

        if scan_id is None:
            exclude_scan_ids = list(self.rapidApp.devices.scanning)
        else:
            exclude_scan_ids = None

        files: defaultdict[int, list[RPDFile]] = defaultdict(list)
        download_stats = defaultdict(DownloadStats)
        camera_access_needed = defaultdict(bool)
        download_photos = download_videos = False

        uids = self.tsql.get_uids(
            scan_id=scan_id,
            marked=True,
            downloaded=False,
            exclude_scan_ids=exclude_scan_ids,
        )

        for uid in uids:
            rpd_file: RPDFile = self.rpd_files[uid]

            scan_id = rpd_file.scan_id
            files[scan_id].append(rpd_file)

            # TODO contemplate using a counter here
            if rpd_file.file_type == FileType.photo:
                download_photos = True
                download_stats[scan_id].no_photos += 1
                download_stats[scan_id].photos_size_in_bytes += rpd_file.size
            else:
                download_videos = True
                download_stats[scan_id].no_videos += 1
                download_stats[scan_id].videos_size_in_bytes += rpd_file.size
            if rpd_file.from_camera and not rpd_file.cache_full_file_name:
                camera_access_needed[scan_id] = True

            # Need to generate a thumbnail after a file has been downloaded
            # if generating FDO thumbnails or if the orientation of the
            # thumbnail we may have is unknown

            if self.sendToDaemonThumbnailer(rpd_file=rpd_file):
                download_stats[scan_id].post_download_thumb_generation += 1

        # self.validateModelConsistency()
        download_types = FileTypeFlag(0)
        if download_photos:
            download_types = FileTypeFlag.PHOTOS
        if download_videos:
            download_types = FileTypeFlag.VIDEOS

        return DownloadFiles(
            files=files,
            download_types=download_types,
            download_stats=download_stats,
            camera_access_needed=camera_access_needed,
        )

    def sendToDaemonThumbnailer(self, rpd_file: RPDFile) -> bool:
        """
        Determine if the file needs to be sent for thumbnail generation
        by the post download daemon.

        :param rpd_file: file to analyze
        :return: True if need to send, False otherwise
        """

        return self.prefs.generate_thumbnails and (
            (self.prefs.save_fdo_thumbnails and rpd_file.should_write_fdo())
            or rpd_file.thumbnail_status
            not in (ThumbnailCacheStatus.ready, ThumbnailCacheStatus.fdo_256_ready)
        )

    def markDownloadPending(self, files: dict[int, list[RPDFile]]) -> None:
        """
        Sets status to download pending and updates thumbnails display.

        Assumes all marked files are being downloaded.

        :param files: rpd_files by scan
        """

        uids = [rpd_file.uid for scan_id in files for rpd_file in files[scan_id]]
        rows = [self.uid_to_row[uid] for uid in uids if uid in self.uid_to_row]
        for row in rows:
            uid = self.rows[row][0]
            self.rows[row] = (uid, False)
        self.tsql.set_list_marked(uids=uids, marked=False)

        for uid in uids:
            self.rpd_files[uid].status = DownloadStatus.download_pending

        rows.sort()
        for first, last in runs(rows):
            self.dataChanged.emit(self.index(first, 0), self.index(last, 0))

    def markThumbnailsNeeded(self, rpd_files: list[RPDFile]) -> bool:
        """
        Analyzes the files that will be downloaded, and sees if any of
        them still need to have their thumbnails generated.

        Marks generate_thumbnail in each rpd_file those for that need
        thumbnails.

        :param rpd_files: list of files to examine
        :return: True if at least one thumbnail needs to be generated
        """

        generation_needed = False
        for rpd_file in rpd_files:
            if rpd_file.uid not in self.thumbnails:
                rpd_file.generate_thumbnail = True
                generation_needed = True
        return generation_needed

    def getNoFilesRemaining(self, scan_id: int | None = None) -> int:
        """
        :param scan_id: if None, returns files remaining to be
         downloaded for all scan_ids, else only for that scan_id.
        :return the number of files that have not yet been downloaded
        """

        return self.tsql.get_count(scan_id=scan_id, downloaded=False)

    def updateSelectionAfterProximityChange(self) -> None:
        if self._selectionModel().hasSelection():
            # completely reset the existing selection
            self._selectionModel().reset()
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.rows) - 1, 0))

        select_all_photos = self.rapidApp.selectAllPhotosCheckbox.isChecked()
        select_all_videos = self.rapidApp.selectAllVideosCheckbox.isChecked()
        if select_all_photos:
            self.selectAll(select_all=select_all_photos, file_type=FileType.photo)
        if select_all_videos:
            self.selectAll(select_all=select_all_videos, file_type=FileType.video)

    def selectAll(self, select_all: bool, file_type: FileType) -> None:
        """
        Check or deselect all visible files that are not downloaded.

        :param select_all:  if True, select, else deselect
        :param file_type: the type of files to select/deselect
        """

        uids = self.getDisplayedUids(file_type=file_type)

        if not uids:
            return

        action = "Selecting all %s" if select_all else "Deslecting all %ss"

        logging.debug(action, file_type.name)

        selection = self._selectionModel()
        selected: QItemSelection = selection.selection()

        if select_all:
            # print("gathering unique ids")
            rows = [self.uid_to_row[uid] for uid in uids]
            # print(len(rows))
            # print('doing sort')
            rows.sort()
            new_selection: QItemSelection = QItemSelection()
            # print("creating new selection")
            for first, last in runs(rows):
                new_selection.select(self.index(first, 0), self.index(last, 0))
            # print('merging select')
            new_selection.merge(selected, QItemSelectionModel.Select)
            # print('resetting')
            selection.reset()
            # print('doing select')
            selection.select(new_selection, QItemSelectionModel.Select)
        else:
            # print("gathering unique ids from existing selection")
            if file_type == FileType.photo:
                keep_type = FileType.video
            else:
                keep_type = FileType.photo
            # print("filtering", keep_type)
            keep_rows = [
                index.row()
                for index in selected.indexes()
                if self.rpd_files[self.rows[index.row()][0]].file_type == keep_type
            ]
            rows = [index.row() for index in selected.indexes()]
            # print(len(keep_rows), len(rows))
            # print("sorting rows to keep")
            keep_rows.sort()
            new_selection: QItemSelection = QItemSelection()
            # print("creating new selection")
            for first, last in runs(keep_rows):
                new_selection.select(self.index(first, 0), self.index(last, 0))
            # print('resetting')
            selection.reset()
            self.selectionReset.emit()
            # print('doing select')
            selection.select(new_selection, QItemSelectionModel.Select)

        # print('doing data changed')
        for first, last in runs(rows):
            self.dataChanged.emit(self.index(first, 0), self.index(last, 0))
        # print("finished")

    def checkAll(
        self,
        check_all: bool,
        file_type: FileType | None = None,
        scan_id: int | None = None,
    ) -> None:
        """
        Check or uncheck all visible files that are not downloaded.

        A file is "visible" if it is in the current thumbnail display.
        That means if files are not showing because they are previously
        downloaded, they will not be affected. Likewise, if temporal
        proximity rows are selected, only those files are affected.

        Runs in the main thread and is thus time sensitive.

        :param check_all: if True, mark as checked, else unmark
        :param file_type: if specified, files must be of specified type
        :param scan_id: if specified, affects only files for that scan
        """

        uids = self.getDisplayedUids(
            marked=not check_all, file_type=file_type, scan_id=scan_id
        )
        self.tsql.set_list_marked(uids=uids, marked=check_all)
        rows = [self.uid_to_row[uid] for uid in uids]
        for row in rows:
            self.rows[row] = (self.rows[row][0], check_all)
        rows.sort()
        for first, last in runs(rows):
            self.dataChanged.emit(self.index(first, 0), self.index(last, 0))

        self.updateDeviceDisplayCheckMark(scan_id=scan_id)
        self.rapidApp.displayMessageInStatusBar()
        self.rapidApp.setDownloadCapabilities()

    def getTypeCountForProximityCell(
        self, col1id: int | None = None, col2id: int | None = None
    ) -> str:
        """
        Generates a string displaying how many photos and videos are
        in the proximity table cell
        """
        uids = self.getTemporalProximityUids(col1id=col1id, col2id=col2id)
        file_types = (self.rpd_files[uid].file_type for uid in uids)
        return FileTypeCounter(file_types).summarize_file_count()[0]

    def getTemporalProximityUids(
        self, col1id: int | None = None, col2id: int | None = None
    ) -> list[bytes]:
        assert not (col1id is None and col2id is None)
        if col2id is not None:
            col2id = [col2id]
        else:
            col1id = [col1id]
        return self.tsql.get_uids(proximity_col1=col1id, proximity_col2=col2id)

    def getDisplayedUids(
        self,
        scan_id: int | None = None,
        marked: bool | None = None,
        file_type: FileType | None = None,
        downloaded: bool | None = False,
    ) -> list[bytes]:
        return self.tsql.get_uids(
            scan_id=scan_id,
            downloaded=downloaded,
            show=self.show,
            proximity_col1=self.proximity_col1,
            proximity_col2=self.proximity_col2,
            marked=marked,
            file_type=file_type,
        )

    def getFirstUidFromUidList(self, uids: list[bytes]) -> bytes | None:
        return self.tsql.get_first_uid_from_uid_list(
            sort_by=self.sort_by,
            sort_order=self.sort_order,
            show=self.show,
            proximity_col1=self.proximity_col1,
            proximity_col2=self.proximity_col2,
            uids=uids,
        )

    def getDisplayedCount(
        self, scan_id: int | None = None, marked: bool | None = None
    ) -> int:
        return self.tsql.get_count(
            scan_id=scan_id,
            downloaded=False,
            show=self.show,
            proximity_col1=self.proximity_col1,
            proximity_col2=self.proximity_col2,
            marked=marked,
        )

    def getDisplayedCounter(self) -> FileTypeCounter:
        no_photos = self.tsql.get_count(
            downloaded=False,
            file_type=FileType.photo,
            show=self.show,
            proximity_col1=self.proximity_col1,
            proximity_col2=self.proximity_col2,
        )
        no_videos = self.tsql.get_count(
            downloaded=False,
            file_type=FileType.video,
            show=self.show,
            proximity_col1=self.proximity_col1,
            proximity_col2=self.proximity_col2,
        )
        f = FileTypeCounter()
        f[FileType.photo] = no_photos
        f[FileType.video] = no_videos
        return f

    def _getSampleFileNonCamera(self, file_type: FileType) -> RPDFile | None:
        """
        Attempt to return a sample file used to illustrate file renaming and subfolder
        generation, but only if it's not from a camera.
        :return:
        """

        devices = self.rapidApp.devices
        exclude_scan_ids = [
            s_id
            for s_id, device in devices.devices.items()
            if device.device_type == DeviceType.camera
        ]
        if not exclude_scan_ids:
            exclude_scan_ids = None

        uid = self.tsql.get_single_file_of_type(
            file_type=file_type, exclude_scan_ids=exclude_scan_ids
        )
        if uid is not None:
            return self.rpd_files[uid]
        else:
            return None

    def getSampleFile(
        self, scan_id: int, device_type: DeviceType, file_type: FileType
    ) -> RPDFile | None:
        """
        Attempt to return a sample file used to illustrate file renaming and subfolder
        generation.

        If the device_type is a camera, then search only for
        a downloaded instance of the file.

        If the device is not a camera, prefer a non-downloaded file
        over a downloaded file for that scan_id.

        If no file is available for that scan_id, try again with another scan_id.

        :param scan_id:
        :param device_type:
        :param file_type:
        :return:
        """

        if device_type == DeviceType.camera:
            uid = self.tsql.get_single_file_of_type(
                scan_id=scan_id, file_type=file_type, downloaded=True
            )
            if uid is not None:
                return self.rpd_files[uid]
            else:
                # try find a *downloaded* file from another camera

                # could determine which devices to exclude in SQL but it's a little
                # simpler here
                devices = self.rapidApp.devices
                exclude_scan_ids = [
                    s_id
                    for s_id, device in devices.items()
                    if device.device_type != DeviceType.camera
                ]

                if not exclude_scan_ids:
                    exclude_scan_ids = None

                uid = self.tsql.get_single_file_of_type(
                    file_type=file_type,
                    downloaded=True,
                    exclude_scan_ids=exclude_scan_ids,
                )
                if uid is not None:
                    return self.rpd_files[uid]
                else:
                    return self._getSampleFileNonCamera(file_type=file_type)

        else:
            uid = self.tsql.get_single_file_of_type(
                scan_id=scan_id, file_type=file_type
            )
            if uid is not None:
                return self.rpd_files[uid]
            else:
                return self._getSampleFileNonCamera(file_type=file_type)

    def updateDeviceDisplayCheckMark(self, scan_id: int) -> None:
        if scan_id not in self.removed_devices:
            uid_count = self.getDisplayedCount(scan_id=scan_id)
            checked_uid_count = self.getDisplayedCount(scan_id=scan_id, marked=True)
            if uid_count == 0 or checked_uid_count == 0:
                checked = Qt.Unchecked
            elif uid_count != checked_uid_count:
                checked = Qt.PartiallyChecked
            else:
                checked = Qt.Checked
            self.rapidApp.mapModel(scan_id).setCheckedValue(checked, scan_id)

    def updateAllDeviceDisplayCheckMarks(self) -> None:
        for scan_id in self.rapidApp.devices:
            self.updateDeviceDisplayCheckMark(scan_id=scan_id)

    def highlightDeviceThumbs(self, scan_id) -> None:
        """
        Animate fade to and from highlight color for thumbnails associated
        with device.
        :param scan_id: device's id
        """

        if scan_id == self.currently_highlighting_scan_id:
            return

        self.resetHighlighting()

        self.currently_highlighting_scan_id = scan_id
        if scan_id != self.most_recent_highlighted_device:
            highlighting = [
                self.uid_to_row[uid] for uid in self.getDisplayedUids(scan_id=scan_id)
            ]
            self._generateHighlightingRows(rows=highlighting)
            self.most_recent_highlighted_device = scan_id
        self.highlightingTimeline.setDirection(QTimeLine.Forward)
        self.highlightingTimeline.start()

    def highlightTemporalProximityThumbs(self, row: int, uids: list[bytes]) -> None:
        """
        Currently unused. Highlights thumbnails from the selected column 2
        timeline row.
        """

        if row == self.currently_highlighting_tp_row:
            return

        self.resetHighlighting()

        self.currently_highlighting_tp_row = row
        if row != self.most_recent_highlighted_row:
            highlighting = [self.uid_to_row[uid] for uid in uids]
            self._generateHighlightingRows(rows=highlighting)
            self.most_recent_highlighted_row = row
            self.current_highlight_uids = uids
        self.highlightingTimeline.setDirection(QTimeLine.Forward)
        self.highlightingTimeline.start()

    def _generateHighlightingRows(self, rows: list[int]) -> None:
        rows.sort()
        self.highlighting_rows = list(runs(rows))

    def resetHighlighting(self) -> None:
        if (
            self.currently_highlighting_scan_id is not None
            or self.currently_highlighting_tp_row is not None
        ):
            self.highlightingTimeline.stop()
            self.doHighlightThumbs(value=0)
            self.current_highlight_uids = []

    @pyqtSlot(int)
    def doHighlightThumbs(self, value: int) -> None:
        self.highlight_value = value
        # print(self.highlighting_rows)
        for first, last in self.highlighting_rows:
            self.dataChanged.emit(self.index(first, 0), self.index(last, 0))

    @pyqtSlot()
    def highlightPhaseFinished(self):
        self.currently_highlighting_scan_id = None
        self.currently_highlighting_tp_row = None

    def _resetHighlightingValues(self):
        self.most_recent_highlighted_device: int | None = None
        self.most_recent_highlighted_row: int | None = None
        self.current_highlight_uids: list[bytes] = []
        self.highlighting_rows: list[int] = []

    def terminateThumbnailGeneration(self, scan_id: int) -> bool:
        """
        Terminates thumbnail generation if thumbnails are currently
        being generated for this scan_id
        :return True if thumbnail generation had to be terminated, else
        False
        """

        # the slot for when a thumbnailing operation is terminated is in the
        # main window - thumbnailGenerationStopped()
        terminate = scan_id in self.generating_thumbnails
        if terminate:
            self.thumbnailer.stop_worker(scan_id)
            # TODO update this check once checking for thumnbnailing code is more robust
            # note that check == 1 because it is assumed the scan id has not been
            # deleted from the device collection
            if len(self.rapidApp.devices.thumbnailing) == 1:
                self.resetThumbnailTracking()
            else:
                self.recalculateThumbnailsPercentage(scan_id=scan_id)
        return terminate

    def recalculateThumbnailsPercentage(self, scan_id: int) -> None:
        """
        Adjust % of thumbnails generated calculations after device removal.

        :param scan_id: id of removed device
        """

        self.total_thumbs_to_generate -= self.no_thumbnails_by_scan[scan_id]
        self.rapidApp.updateProgressBarState()
        del self.no_thumbnails_by_scan[scan_id]

    def updateStatusPostDownload(self, rpd_file: RPDFile):
        # self.validateModelConsistency()

        uid = rpd_file.uid
        self.rpd_files[uid] = rpd_file
        self.tsql.set_downloaded(uid=uid, downloaded=True)
        row = self.uid_to_row.get(uid)

        if row is not None:
            self.dataChanged.emit(self.index(row, 0), self.index(row, 0))

    def filesRemainToDownload(self, scan_id: int | None = None) -> bool:
        """
        :return True if any files remain that are not downloaded, else
         returns False
        """
        return self.tsql.any_files_to_download(scan_id)

    def dataForProximityGeneration(self) -> list[ThumbnailDataForProximity]:
        return [
            ThumbnailDataForProximity(
                uid=rpd_file.uid,
                ctime=rpd_file.ctime,
                file_type=rpd_file.file_type,
                previously_downloaded=rpd_file.previously_downloaded,
            )
            for rpd_file in self.rpd_files.values()
        ]

    def assignProximityGroups(
        self, col1_col2_uid: list[tuple[int, int, bytes]]
    ) -> None:
        """
        For every uid, associates it with a cell in the temporal proximity view.

        Relevant columns are col 1 and col 2.
        """

        self.tsql.assign_proximity_groups(col1_col2_uid)

    def setProximityGroupFilter(
        self, col1: Sequence[int] | None, col2: Sequence[int] | None
    ) -> None:
        """
        Filter display of thumbnails based on what cells the user has clicked in the
        Temporal Proximity view.

        Relevant columns are col 1 and col 2.
        """

        if col1 != self.proximity_col1 or col2 != self.proximity_col2:
            self.proximity_col1 = col1
            self.proximity_col2 = col2
            self.refresh()

    def anyCheckedFilesFiltered(self) -> bool:
        """
        :return: True if any files marked for download are currently
         not displayed because they are filtered
        """

        return self.tsql.get_count(marked=True) != self.getDisplayedCount(marked=True)

    def anyFileNotPreviouslyDownloaded(self, uids: list[bytes]) -> bool:
        return self.tsql.any_not_previously_downloaded(uids=uids)

    def getFileDownloadsCompleted(self) -> FileTypeCounter:
        """
        :return: counter for how many photos and videos have their downloads completed
         whether successfully or not
        """

        return FileTypeCounter(
            {
                FileType.photo: self.tsql.get_count(
                    downloaded=True, file_type=FileType.photo
                ),
                FileType.video: self.tsql.get_count(
                    downloaded=True, file_type=FileType.video
                ),
            }
        )

    def anyCompletedDownloads(self) -> bool:
        """
        :return: True if any files have been downloaded (including failures)
        """

        return self.tsql.any_files_download_completed()

    def jobCodeNeeded(self) -> bool:
        """
        :return: True if any files marked for download do not have job codes
         assigned to them
        """

        return self.tsql.any_marked_file_no_job_code()

    def getNoFilesJobCodeNeeded(self) -> FileTypeCounter:
        """
        :return: the number of marked files that need a job code assigned to them, and
         the file types they will be applied to.
        """

        no_photos = no_videos = 0
        if self.prefs.file_type_uses_job_code(FileType.photo):
            no_photos = self.tsql.get_count(
                marked=True, file_type=FileType.photo, job_code=False
            )
        if self.prefs.file_type_uses_job_code(FileType.video):
            no_videos = self.tsql.get_count(
                marked=True, file_type=FileType.video, job_code=False
            )

        f = FileTypeCounter()
        f[FileType.photo] = no_photos
        f[FileType.video] = no_videos

        return f


class ThumbnailView(QListView):
    """
    Thumbnail view. QListView in icon mode.
    """

    verticalScrollBarVisible = pyqtSignal(bool)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.rapidApp = parent
        self.setObjectName("thumbnailView")
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setUniformItemSizes(True)
        self.setSpacing(8)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setFrameShadow(QFrame.Plain)
        palette = self.palette()
        color = QColor()
        if is_dark_mode():
            color.setNamedColor(DarkModeThumbnailBackgroundName)
        else:
            color.setNamedColor(ThumbnailBackgroundName)
        palette.setColor(QPalette.Base, color)
        self.setPalette(palette)
        self.possiblyPreserveSelectionPostClick = False

        sbv = ScrollBarEmitsVisible(orientation=Qt.Vertical)
        self.setVerticalScrollBar(sbv)
        sbv.scrollBarVisible.connect(self.verticalScrollBarVisible)

        # Track how many columns the user sees
        # QListView IconMode indexes are always set to column 0
        self.user_visible_columns = 0

    def setScrollTogether(self, on: bool) -> None:
        """
        Turn on or off the linking of scrolling the Timeline with the Thumbnail display.

        Called from the Proximity (Timeline) widget

        :param on: whether to turn on or off
        """

        if on:
            self.verticalScrollBar().valueChanged.connect(self.scrollTimeline)
        else:
            self.verticalScrollBar().valueChanged.disconnect(self.scrollTimeline)

    def _scrollTemporalProximity(
        self, row: int | None = None, index: QModelIndex | None = None
    ) -> None:
        temporalProximity = self.rapidApp.temporalProximity
        temporalProximity.setScrollTogether(False)
        if row is None:
            row = index.row()
        model = self.model()
        rows = model.rows
        uid = rows[row][0]
        temporalProximity.scrollToUid(uid=uid)
        temporalProximity.setScrollTogether(True)

    def selectionChanged(
        self, selected: QItemSelection, deselected: QItemSelection
    ) -> None:
        """
        Reselect items if the user clicked a checkmark within an existing selection
        :param selected: new selection
        :param deselected: previous selection
        """

        super().selectionChanged(deselected, selected)

        if self.possiblyPreserveSelectionPostClick:
            # Must set this to False before adjusting the selection!
            self.possiblyPreserveSelectionPostClick = False

            current = self.currentIndex()
            if not (len(selected.indexes()) == 1 and selected.indexes()[0] == current):
                deselected.merge(
                    self.selectionModel().selection(), QItemSelectionModel.Select
                )
                self.selectionModel().select(deselected, QItemSelectionModel.Select)

    @pyqtSlot(QMouseEvent)
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        Filter selection changes when click is on a thumbnail checkbox.

        When the user has selected multiple items (thumbnails), and
        then clicks one of the checkboxes, Qt's default behaviour is to
        treat that click as selecting the single item, because it doesn't
        know about our checkboxes. Therefore if the user is in fact
        clicking on a checkbox, we need to filter that event.

        On some versions of Qt 5 (to be determined), no matter what we do here,
        the delegate's editorEvent will still be triggered.

        :param event: the mouse click event
        """

        right_button_pressed = event.button() == Qt.RightButton
        if right_button_pressed:
            super().mousePressEvent(event)

        else:
            index = self.indexAt(event.pos())
            clicked_row = index.row()

            if clicked_row >= 0:
                rect: QRect = self.visualRect(index)
                delegate: ThumbnailDelegate = self.itemDelegate(index)
                checkboxRect = delegate.getCheckBoxRect(rect)
                checkbox_clicked = checkboxRect.contains(event.pos())
                if checkbox_clicked:
                    status: DownloadStatus = index.data(Roles.download_status)
                    checkbox_clicked = status not in Downloaded

                if not checkbox_clicked:
                    if self.rapidApp.prefs.auto_scroll and clicked_row >= 0:
                        self._scrollTemporalProximity(row=clicked_row)
                else:
                    self.possiblyPreserveSelectionPostClick = True
            super().mousePressEvent(event)

    def topRowIndex(self) -> QModelIndex | None:
        # index of top left item
        index: QModelIndex = self.indexAt(QPoint(self.spacing(), self.spacing()))

        if index.isValid():
            # Determine index of item in user visible row with the earliest time
            row = index.row()
            indicies = [
                index.sibling(row + i, 0) for i in range(self.user_visible_columns)
            ]

            # Filter out invalid indicies
            indicies = [idx for idx in indicies if idx.isValid()]

            # Get the index with the earliest time
            # Inspiration: https://stackoverflow.com/a/11825864
            data = [idx.data() for idx in indicies]
            index_min = min(range(len(data)), key=data.__getitem__)
            return indicies[index_min]
        return None

    def topRowUid(self) -> bytes | None:
        index = self.topRowIndex()
        if index:
            row = index.row()
            uid = self.model().rows[row][0]
            return uid
        return None

    @pyqtSlot(int)
    def scrollTimeline(self, value) -> None:
        index = self.topRowIndex()
        if index:
            self._scrollTemporalProximity(index=index)

    def topLeft(self) -> QPoint:
        return QPoint(thumbnail_margin, thumbnail_margin)

    def thumbnail_width(self) -> int:
        return self.itemDelegate().fixedSizeHint.width()

    def width_required(self, no_thumbails: int) -> int:
        return (
            no_thumbails * (self.thumbnail_width() + self.spacing())
            + self.spacing()
            + self.frameWidth() * 2
        )

    def resizeEvent(self, event: QResizeEvent) -> None:
        """
        Resize, then calculate and store how many columns the user sees
        """

        super().resizeEvent(event)
        item_width = self.itemDelegate().fixedSizeHint.width() + self.spacing()
        view_width = self.viewport().contentsRect().width() - self.spacing() - 1
        self.user_visible_columns = view_width // item_width

    def scrollToUids(self, uids: list[bytes]) -> None:
        """
        Scroll the Thumbnail Display to the first visible uid from the list of uids.

        Remember not all uids are necessarily visible in the Thumbnail Display,
        because of filtering.

        :param uids: list of uids to scroll to
        """
        model: ThumbnailListModel = self.model()
        if self.rapidApp.showOnlyNewFiles():
            uid = model.getFirstUidFromUidList(uids=uids)
            if uid is None:
                return
        else:
            uid = uids[0]
        try:
            row = model.uid_to_row[uid]
        except KeyError:
            logging.debug("Ignoring scroll request to unknown thumbnail")
        else:
            index = model.index(row, 0)
            self.scrollTo(index, QAbstractItemView.PositionAtTop)


class ThumbnailDelegate(QStyledItemDelegate):
    """
    Render thumbnail cells
    """

    # markedWithMouse = pyqtSignal()

    def __init__(self, rapidApp, parent=None) -> None:
        super().__init__(parent)
        self.rapidApp = rapidApp
        try:
            # Works on Qt 5.6 and above
            self.device_pixel_ratio = rapidApp.devicePixelRatioF()
            self.devicePixelF = True
        except AttributeError:
            self.device_pixel_ratio = rapidApp.devicePixelRatio()
            self.devicePixelF = False

        self.checkboxStyleOption = QStyleOptionButton()
        self.checkboxRect = QRectF(
            QApplication.style().subElementRect(
                QStyle.SE_CheckBoxIndicator, self.checkboxStyleOption, None
            )
        )
        self.checkbox_size = self.checkboxRect.height()

        size16 = QSize(16, 16)
        size24 = QSize(24, 24)
        self.downloadPendingPixmap = scaledIcon(
            data_file_path("thumbnail/download-pending.svg")
        ).pixmap(size16)
        self.downloadedPixmap = scaledIcon(
            data_file_path("thumbnail/downloaded.svg")
        ).pixmap(size16)
        self.downloadedWarningPixmap = scaledIcon(
            data_file_path("thumbnail/downloaded-with-warning.svg")
        ).pixmap(size16)
        self.downloadedErrorPixmap = scaledIcon(
            data_file_path("thumbnail/downloaded-with-error.svg")
        ).pixmap(size16)
        self.audioIcon = scaledIcon(
            data_file_path("thumbnail/audio.svg"), size24
        ).pixmap(size24)

        # Determine pixel scaling for SVG files
        # Applies to all SVG files delegate will load
        if self.devicePixelF:
            self.pixmap_ratio = self.downloadPendingPixmap.devicePixelRatioF()
        else:
            self.pixmap_ratio = self.downloadedErrorPixmap.devicePixelRatio()

        self.dimmed_opacity = 0.5

        self.image_width = float(max(ThumbnailSize.width, ThumbnailSize.height))
        self.image_height = self.image_width
        self.horizontal_margin = float(thumbnail_margin)
        self.vertical_margin = float(thumbnail_margin)
        self.image_footer = float(self.checkbox_size)
        self.footer_padding = 5.0

        # Position of first memory card indicator
        self.card_x = float(
            max(
                self.checkboxRect.width(),
                self.downloadPendingPixmap.width() / self.pixmap_ratio,
                self.downloadedPixmap.width() / self.pixmap_ratio,
            )
            + self.horizontal_margin
            + self.footer_padding
        )

        self.shadow_size = 2.0
        self.width = self.image_width + self.horizontal_margin * 2
        self.height = (
            self.image_height
            + self.footer_padding
            + self.image_footer
            + self.vertical_margin * 2
        )

        # Thumbnail is located in a 160px square...
        self.image_area_size = float(max(ThumbnailSize.width, ThumbnailSize.height))
        self.image_frame_bottom = self.vertical_margin + self.image_area_size

        self.contextMenu = QMenu()
        self.openInFileBrowserAct = self.contextMenu.addAction(
            _("Open in File Browser...")
        )
        self.openInFileBrowserAct.triggered.connect(self.doOpenInFileManagerAct)
        self.copyPathAct = self.contextMenu.addAction(_("Copy Path"))
        self.copyPathAct.triggered.connect(self.doCopyPathAction)
        # Translators: 'File' here applies to a single file. The command allows users to
        # instruct Rapid Photo Downloader that photos and videos have been previously
        # downloaded by another application.
        self.markFileDownloadedAct = self.contextMenu.addAction(
            _("Mark File as Downloaded")
        )
        self.markFileDownloadedAct.triggered.connect(self.doMarkFileDownloadedAct)
        # Translators: 'Files' here applies to two or more files
        self.markFilesDownloadedAct = self.contextMenu.addAction(
            _("Mark Files as Downloaded")
        )
        self.markFilesDownloadedAct.triggered.connect(self.doMarkFileDownloadedAct)
        # store the index in which the user right clicked
        self.clickedIndex: QModelIndex | None = None

        self.color3 = QColor(CustomColors.color3.value)

        self.paleGray = QColor(PaleGray)
        self.darkGray = QColor(DarkGray)

        palette = QGuiApplication.palette()
        self.highlight: QColor = palette.highlight().color()
        self.highlight_size = 3
        self.highlight_offset = self.highlight_size / 2
        self.highlightPen = QPen()
        self.highlightPen.setColor(self.highlight)
        self.highlightPen.setWidth(self.highlight_size)
        self.highlightPen.setStyle(Qt.SolidLine)
        self.highlightPen.setJoinStyle(Qt.MiterJoin)

        self.emblemFont = QFont()
        self.emblemFont.setPointSize(self.emblemFont.pointSize() - 3)
        metrics = QFontMetricsF(self.emblemFont)

        # Determine the actual height of the largest extension, and the actual
        # width of all extensions.
        # For our purposes, this is more accurate than the generic metrics.height()
        self.emblem_width: dict[str, int] = {}
        height = 0
        # Include the emblems for which memory card on a camera the file came from
        for ext in ALL_USER_VISIBLE_EXTENSIONS + ["1", "2"]:
            ext = ext.upper()
            tbr: QRectF = metrics.tightBoundingRect(ext)
            self.emblem_width[ext] = tbr.width()
            height = max(height, tbr.height())

        # Set and calculate the padding to go around each emblem
        self.emblem_pad = height / 3
        self.emblem_height = height + self.emblem_pad * 2
        self.emblem_width = {
            emblem: width + self.emblem_pad * 2
            for emblem, width in self.emblem_width.items()
        }

        self.jobCodeFont = QFont()
        self.jobCodeFont.setPointSize(self.jobCodeFont.pointSize() - 2)
        self.jobCodeMetrics = QFontMetricsF(self.jobCodeFont)
        height = self.jobCodeMetrics.height()
        self.job_code_pad = height / 4
        self.job_code_height = height + self.job_code_pad * 2
        self.job_code_width = self.image_width
        self.job_code_text_width = self.job_code_width - self.job_code_pad * 2
        self.jobCodeBackground = QColor(DoubleDarkGray)
        # alternative would be functools.lru_cache() decorator, but it
        # is required to be a function. It's easier to keep everything
        # in this class, especially regarding the default font
        self.job_code_lru: dict[str, str] = dict()

        # Generate the range of colors to be displayed when highlighting
        # files from a particular device
        ch = Color(self.highlight.name())
        cg = Color(self.paleGray.name())
        self.colorGradient = [QColor(c.hex) for c in cg.range_to(ch, FadeSteps)]

        # Size is always fixed, so calculate it here
        self.fixedSizeHint = QSizeF(
            self.width + self.shadow_size, self.height + self.shadow_size
        ).toSize()

    @pyqtSlot()
    def doCopyPathAction(self) -> None:
        index = self.clickedIndex
        if index:
            path = index.model().data(index, Roles.path)
            QApplication.clipboard().setText(path)

    @pyqtSlot()
    def doOpenInFileManagerAct(self) -> None:
        selectedIndexes = self.selectedIndexes()
        if selectedIndexes is not None:
            if self.clickedIndex not in selectedIndexes:
                selectedIndexes.append(self.clickedIndex)
            uris = [index.model().data(index, Roles.uri) for index in selectedIndexes]
        else:
            index = self.clickedIndex
            uris = [index.model().data(index, Roles.uri)]
        if uris:
            logging.debug(
                "Calling show_in_file_manager() with %s and %s",
                self.rapidApp.file_manager,
                ", ".join(uris),
            )
            show_in_file_manager(path_or_uri=uris, allow_conversion=False)

    @pyqtSlot()
    def doMarkFileDownloadedAct(self) -> None:
        selectedIndexes = self.selectedIndexes()
        if selectedIndexes is None:
            return
        not_downloaded: tuple[QModelIndex, ...] = tuple(
            index
            for index in selectedIndexes
            if not index.data(Roles.previously_downloaded)
        )
        thumbnailModel: ThumbnailListModel = self.rapidApp.thumbnailModel
        thumbnailModel.setDataRange(not_downloaded, True, Roles.previously_downloaded)
        self.rapidApp.setDownloadCapabilities()

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        if index is None:
            return

        if not index.isValid():
            return

        # Save state of painter, restore on function exit
        painter.save()

        checked = index.data(Qt.CheckStateRole) == Qt.Checked
        previously_downloaded = index.data(Roles.previously_downloaded)
        extension, ext_type = index.data(Roles.extension)
        download_status: DownloadStatus = index.data(Roles.download_status)
        has_audio = index.data(Roles.has_audio)
        secondary_attribute = index.data(Roles.secondary_attribute)
        memory_cards: list[int] = index.data(Roles.camera_memory_card)
        highlight = index.data(Roles.highlight)
        job_code: str | None = index.data(Roles.job_code)

        # job_code = 'An extremely long and complicated Job Code'
        # job_code = 'Job Code'

        is_selected = option.state & QStyle.State_Selected

        x = option.rect.x()
        y = option.rect.y()

        # Draw rectangle in which the individual items will be placed
        boxRect = QRectF(x, y, self.width, self.height)
        shadowRect = QRectF(
            x + self.shadow_size, y + self.shadow_size, self.width, self.height
        )

        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(self.darkGray)
        painter.fillRect(shadowRect, self.darkGray)
        painter.drawRect(shadowRect)
        painter.setRenderHint(QPainter.Antialiasing, False)
        if highlight != 0:
            painter.fillRect(boxRect, self.colorGradient[highlight - 1])
        else:
            painter.fillRect(boxRect, self.paleGray)

        if is_selected:
            hightlightRect = QRectF(
                boxRect.left() + self.highlight_offset,
                boxRect.top() + self.highlight_offset,
                boxRect.width() - self.highlight_size,
                boxRect.height() - self.highlight_size,
            )
            painter.setPen(self.highlightPen)
            painter.drawRect(hightlightRect)

        thumbnail: QPixmap = index.model().data(index, Qt.DecorationRole)

        # If on high DPI screen, scale the thumbnail using a smooth transform
        if self.device_pixel_ratio > 1.0:
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        if (
            previously_downloaded
            and not checked
            and download_status == DownloadStatus.not_downloaded
        ):
            disabled = QPixmap(thumbnail.size())
            if self.devicePixelF:
                disabled.setDevicePixelRatio(thumbnail.devicePixelRatioF())
            else:
                disabled.setDevicePixelRatio(thumbnail.devicePixelRatio())
            disabled.fill(Qt.transparent)
            p = QPainter(disabled)
            p.setBackgroundMode(Qt.TransparentMode)
            p.setBackground(QBrush(Qt.transparent))
            p.eraseRect(thumbnail.rect())
            p.setOpacity(self.dimmed_opacity)
            p.drawPixmap(0, 0, thumbnail)
            p.end()
            thumbnail = disabled

        thumbnail_width = thumbnail.size().width()
        thumbnail_height = thumbnail.size().height()
        if self.devicePixelF:
            ratio = thumbnail.devicePixelRatioF()
        else:
            ratio = thumbnail.devicePixelRatio()

        thumbnailX = (
            self.horizontal_margin
            + (self.image_area_size - thumbnail_width / ratio) / 2
            + x
        )
        thumbnailY = (
            self.vertical_margin
            + (self.image_area_size - thumbnail_height / ratio) / 2
            + y
        )

        target = QRectF(
            thumbnailX, thumbnailY, thumbnail_width / ratio, thumbnail_height / ratio
        )
        source = QRectF(0, 0, thumbnail_width, thumbnail_height)
        painter.drawPixmap(target, thumbnail, source)

        dimmed = previously_downloaded and not checked

        # Render the job code near the top of the square, if there is one
        if job_code:
            if is_selected:
                color = self.highlight
                painter.setOpacity(1.0)
            else:
                color = self.jobCodeBackground
                if not dimmed:
                    painter.setOpacity(0.75)
                else:
                    painter.setOpacity(self.dimmed_opacity)

            jobCodeRect = QRectF(
                x + self.horizontal_margin,
                y + self.vertical_margin,
                self.job_code_width,
                self.job_code_height,
            )
            painter.fillRect(jobCodeRect, color)
            painter.setFont(self.jobCodeFont)
            painter.setPen(QColor(Qt.white))
            if job_code in self.job_code_lru:
                text = self.job_code_lru[job_code]
            else:
                text = self.jobCodeMetrics.elidedText(
                    job_code, Qt.ElideRight, self.job_code_text_width
                )
                self.job_code_lru[job_code] = text
            if not dimmed:
                painter.setOpacity(1.0)
            else:
                painter.setOpacity(self.dimmed_opacity)
            painter.drawText(jobCodeRect, Qt.AlignCenter, text)

        if dimmed:
            painter.setOpacity(self.dimmed_opacity)

        # painter.setPen(QColor(Qt.blue))
        # painter.drawText(x + 2, y + 15, str(index.row()))

        if has_audio:
            audio_x = (
                self.width / 2 - self.audioIcon.width() / self.pixmap_ratio / 2 + x
            )
            audio_y = self.image_frame_bottom + self.footer_padding + y - 1
            painter.drawPixmap(QPointF(audio_x, audio_y), self.audioIcon)

        # Draw a small coloured box containing the file extension in the
        #  bottom right corner
        extension = extension.upper()
        # Calculate size of extension text
        painter.setFont(self.emblemFont)
        # em_width = self.emblemFontMetrics.width(extension)
        emblem_width = self.emblem_width[extension]
        emblem_rect_x = self.width - self.horizontal_margin - emblem_width + x
        emblem_rect_y = self.image_frame_bottom + self.footer_padding + y - 1

        emblemRect: QRectF = QRectF(
            emblem_rect_x, emblem_rect_y, emblem_width, self.emblem_height
        )

        color = extensionColor(ext_type=ext_type)

        # Use an angular rect, because a rounded rect with anti-aliasing doesn't look
        # too good
        painter.fillRect(emblemRect, color)
        painter.setPen(QColor(Qt.white))
        painter.drawText(emblemRect, Qt.AlignCenter, extension)

        # Draw another small colored box to the left of the
        # file extension box containing a secondary
        # attribute, if it exists. Currently the secondary attribute is
        # only an XMP file, but in future it could be used to display a
        # matching jpeg in a RAW+jpeg set
        if secondary_attribute:
            # Assume the attribute is already upper case
            sec_width = self.emblem_width[secondary_attribute]
            sec_rect_x = emblem_rect_x - self.footer_padding - sec_width
            color = QColor(self.color3)
            secRect = QRectF(sec_rect_x, emblem_rect_y, sec_width, self.emblem_height)
            painter.fillRect(secRect, color)
            painter.drawText(secRect, Qt.AlignCenter, secondary_attribute)

        if memory_cards:
            # if downloaded from a camera, and the camera has more than
            # one memory card, a list of numeric identifiers (i.e. 1 or
            # 2) identifying which memory card the file came from
            text_x = self.card_x + x
            for card in memory_cards:
                card = str(card)
                card_width = self.emblem_width[card]
                color = QColor(70, 70, 70)
                cardRect = QRectF(text_x, emblem_rect_y, card_width, self.emblem_height)
                painter.fillRect(cardRect, color)
                painter.drawText(cardRect, Qt.AlignCenter, card)
                text_x = text_x + card_width + self.footer_padding

        if dimmed:
            painter.setOpacity(1.0)

        if download_status == DownloadStatus.not_downloaded:
            checkboxStyleOption = QStyleOptionButton()
            if checked:
                checkboxStyleOption.state |= QStyle.State_On
            else:
                checkboxStyleOption.state |= QStyle.State_Off
            checkboxStyleOption.state |= QStyle.State_Enabled
            checkboxStyleOption.rect = self.getCheckBoxRect(option.rect).toRect()
            QApplication.style().drawControl(
                QStyle.CE_CheckBox, checkboxStyleOption, painter
            )
        else:
            if download_status == DownloadStatus.download_pending:
                pixmap = self.downloadPendingPixmap
            elif download_status == DownloadStatus.downloaded:
                pixmap = self.downloadedPixmap
            elif (
                download_status == DownloadStatus.downloaded_with_warning
                or download_status == DownloadStatus.backup_problem
            ):
                pixmap = self.downloadedWarningPixmap
            elif (
                download_status == DownloadStatus.download_failed
                or download_status == DownloadStatus.download_and_backup_failed
            ):
                pixmap = self.downloadedErrorPixmap
            else:
                pixmap = None
            if pixmap is not None:
                painter.drawPixmap(
                    QPointF(option.rect.x() + self.horizontal_margin, emblem_rect_y),
                    pixmap,
                )

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return self.fixedSizeHint

    def oneOrMoreNotDownloaded(self) -> tuple[int, Plural]:
        i = 0
        selectedIndexes = self.selectedIndexes()
        if selectedIndexes is None:
            no_selected = 0
        else:
            no_selected = len(selectedIndexes)
            for index in selectedIndexes:
                if not index.data(Roles.previously_downloaded):
                    i += 1
                    if i == 2:
                        break

        if i == 0:
            return no_selected, Plural.zero
        elif i == 1:
            return no_selected, Plural.two_form_single
        else:
            return no_selected, Plural.two_form_plural

    def editorEvent(
        self,
        event: QEvent,
        model: QAbstractItemModel,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> bool:
        """
        Change the data in the model and the state of the checkbox
        if the user presses the left mouse button or presses
        Key_Space or Key_Select and this cell is editable. Otherwise do nothing.

        Handle right click too.
        """

        download_status = index.data(Roles.download_status)

        if (
            event.type() == QEvent.MouseButtonRelease
            or event.type() == QEvent.MouseButtonDblClick
        ):
            if event.button() == Qt.RightButton:
                self.clickedIndex = index

                # Determine if user can manually mark file or files as previously
                # downloaded
                noSelected, noDownloaded = self.oneOrMoreNotDownloaded()
                if noDownloaded == Plural.two_form_single:
                    self.markFilesDownloadedAct.setVisible(False)
                    self.markFileDownloadedAct.setVisible(True)
                    self.markFileDownloadedAct.setEnabled(True)
                elif noDownloaded == Plural.two_form_plural:
                    self.markFilesDownloadedAct.setVisible(True)
                    self.markFilesDownloadedAct.setEnabled(True)
                    self.markFileDownloadedAct.setVisible(False)
                else:
                    assert noDownloaded == Plural.zero
                    if noSelected == 1:
                        self.markFilesDownloadedAct.setVisible(False)
                        self.markFileDownloadedAct.setVisible(True)
                        self.markFileDownloadedAct.setEnabled(False)
                    else:
                        self.markFilesDownloadedAct.setVisible(True)
                        self.markFilesDownloadedAct.setEnabled(False)
                        self.markFileDownloadedAct.setVisible(False)

                globalPos = self.rapidApp.thumbnailView.viewport().mapToGlobal(
                    event.pos()
                )
                # libgphoto2 needs exclusive access to the camera, so there are times
                # when "open in file browswer" should be disabled:
                # First, for all desktops, when a camera, disable when thumbnailing or
                # downloading.
                # Second, disable opening MTP devices in KDE environment,
                # as KDE won't release them until them the file browser is closed!
                # However if the file is already downloaded, we don't care, as can
                # get it from local source.
                # Finally, disable when we don't know what the default file manager is

                active_camera = disable_kde = False
                have_file_manager = (
                    self.rapidApp.file_manager is not None
                    and self.rapidApp.file_manager != ""
                )
                if download_status not in Downloaded:
                    if index.data(Roles.is_camera):
                        scan_id = index.data(Roles.scan_id)
                        active_camera = (
                            self.rapidApp.deviceState(scan_id) != DeviceState.idle
                        )
                    if not active_camera:
                        disable_kde = (
                            index.data(Roles.is_camera)
                            and self.rapidApp.file_manager in kframework_file_managers
                        )

                self.openInFileBrowserAct.setEnabled(
                    not (disable_kde or active_camera) and have_file_manager
                )
                self.contextMenu.popup(globalPos)
                return False
            if event.button() != Qt.LeftButton or not self.getCheckBoxRect(
                option.rect
            ).contains(event.pos()):
                return False
            if event.type() == QEvent.MouseButtonDblClick:
                return True
        elif event.type() == QEvent.KeyPress:
            if event.key() != Qt.Key_Space and event.key() != Qt.Key_Select:
                return False
        else:
            return False

        if download_status != DownloadStatus.not_downloaded:
            return False

        # Change the checkbox-state
        self.setModelData(None, model, index)
        return True

    def setModelData(
        self, editor: QWidget, model: QAbstractItemModel, index: QModelIndex
    ) -> None:
        newValue = index.data(Qt.CheckStateRole) != Qt.Checked
        thumbnailModel: ThumbnailListModel = self.rapidApp.thumbnailModel
        selection: QItemSelectionModel = self.rapidApp.thumbnailView.selectionModel()
        if selection.hasSelection():
            selected: QItemSelection = selection.selection()
            if index in selected.indexes():
                for i in selected.indexes():
                    thumbnailModel.setData(i, newValue, Qt.CheckStateRole)
            else:
                # The user has clicked on a checkbox that for a
                # thumbnail that is outside their previous selection
                selection.clear()
                selection.select(index, QItemSelectionModel.Select)
                model.setData(index, newValue, Qt.CheckStateRole)
        else:
            # The user has previously selected nothing, so mark this
            # thumbnail as selected
            selection.select(index, QItemSelectionModel.Select)
            model.setData(index, newValue, Qt.CheckStateRole)
        thumbnailModel.updateDisplayPostDataChange()

    def getLeftPoint(self, rect: QRect) -> QPointF:
        return QPointF(
            rect.x() + self.horizontal_margin,
            rect.y() + self.image_frame_bottom + self.footer_padding - 1,
        )

    def getCheckBoxRect(self, rect: QRect) -> QRectF:
        return QRectF(
            self.getLeftPoint(rect), QSizeF(self.checkboxRect.toRect().size())
        )

    def applyJobCode(self, job_code: str) -> None:
        thumbnailModel: ThumbnailListModel = self.rapidApp.thumbnailModel
        selectedIndexes = self.selectedIndexes()
        if selectedIndexes is not None:
            logging.debug("Applying job code to %s files", len(selectedIndexes))
            for i in selectedIndexes:
                thumbnailModel.setData(i, job_code, Roles.job_code)
        else:
            logging.debug("Not applying job code because no files selected")

    def selectedIndexes(self) -> list[QModelIndex] | None:
        selection: QItemSelectionModel = self.rapidApp.thumbnailView.selectionModel()
        if selection.hasSelection():
            selected: QItemSelection = selection.selection()
            return selected.indexes()
        return None
