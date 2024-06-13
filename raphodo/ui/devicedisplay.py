# SPDX-FileCopyrightText: Copyright 2015-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Display details of devices like cameras, external drives and folders on the
computer.

See devices.py for an explanation of what "Device" means in the context of
Rapid Photo Downloader.
"""

import logging
import math
from collections import defaultdict

from PyQt5.QtCore import (
    QAbstractItemModel,
    QAbstractListModel,
    QEvent,
    QModelIndex,
    QObject,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    pyqtSignal,
    pyqtSlot,
)
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QIcon,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPalette,
    QPen,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionButton,
    QStyleOptionViewItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from raphodo.constants import (
    COLOR_RED_WARNING_HTML,
    Checked_Status,
    CustomColors,
    DeviceDisplayPadding,
    DeviceDisplayStatus,
    DeviceDisplayVPadding,
    DeviceRowItem,
    DeviceShadingIntensity,
    DeviceState,
    DeviceType,
    DisplayFileType,
    DownloadFailure,
    DownloadStatus,
    DownloadWarning,
    EmptyViewHeight,
    FileType,
    Roles,
    SourceState,
    ViewRowType,
)
from raphodo.customtypes import UsageDetails
from raphodo.devices import Device
from raphodo.internationalisation.install import install_gettext
from raphodo.internationalisation.utilities import thousands
from raphodo.storage.storage import StorageSpace, get_path_display_name
from raphodo.tools.utilities import data_file_path, format_size_for_user
from raphodo.ui.chevroncombo import ChevronComboSpaced
from raphodo.ui.messages import DIR_PROBLEM_TEXT
from raphodo.ui.source import usage_details
from raphodo.ui.spinnerwidget import (
    SpinnerWidget,
    number_spinner_lines,
    revolutions_per_second,
)
from raphodo.ui.stackedwidget import ResizableStackedWidget
from raphodo.ui.viewconstants import icon_size, iconQSize
from raphodo.ui.viewutils import (
    ListViewFlexiFrame,
    RowTracker,
    darkModePixmap,
    device_name_highlight_color,
    is_dark_mode,
    paletteMidPen,
    scaledIcon,
)

install_gettext()


class DeviceModel(QAbstractListModel):
    """
    Stores Device / This Computer data.

    One Device is displayed has multiple rows:
    1. Header row
    2. One or two rows displaying storage info, depending on how many
       storage devices the device has (i.e. memory cards or perhaps a
       combo of onboard flash memory and additional storage)

    Therefore must map rows to device and back, which is handled by
    a row having a row id, and row ids being linked to a scan id.
    """

    def __init__(self, parent, device_display_type: str) -> None:
        super().__init__(parent)
        self.rapidApp = parent
        self.device_display_type = device_display_type
        # scan_id: Device
        self.devices: dict[int, Device] = {}
        # scan_id: DeviceState
        self.spinner_state: dict[int, DeviceState] = {}
        # scan_id: bool
        self.checked: dict[int, Qt.CheckState] = defaultdict(lambda: Qt.Checked)
        self.icons: dict[int, QPixmap] = {}
        self.rows: RowTracker = RowTracker()
        self.row_id_counter: int = 0
        self.row_id_to_scan_id: dict[int, int] = dict()
        self.scan_id_to_row_ids: dict[int, list[int]] = defaultdict(list)
        self.storage: dict[int, StorageSpace | None] = dict()
        self.headers: set[int] = set()

        self.icon_size = icon_size()

        self.row_ids_active: list[int] = []

        # scan_id: 0.0-1.0
        self.percent_complete: dict[int, float] = defaultdict(float)

        self._rotation_position: int = 0
        self._timer = QTimer(self)
        self._timer.setInterval(
            round(1000 / (number_spinner_lines * revolutions_per_second))
        )
        self._timer.timeout.connect(self.rotateSpinner)
        self._isSpinning = False

    def columnCount(self, parent=QModelIndex()):
        return 1

    def rowCount(self, parent=QModelIndex()):
        return len(self.rows)

    def insertRows(self, position, rows=1, index=QModelIndex()):
        self.beginInsertRows(QModelIndex(), position, position + rows - 1)
        self.endInsertRows()
        return True

    def removeRows(self, position, rows=1, index=QModelIndex()):
        self.beginRemoveRows(QModelIndex(), position, position + rows - 1)
        self.endRemoveRows()
        return True

    def addDevice(self, scan_id: int, device: Device) -> None:
        no_storage = max(len(device.storage_space), 1)
        no_rows = no_storage + 1

        if len(device.storage_space):
            start_row_id = self.row_id_counter + 1
            for i, row_id in enumerate(
                range(start_row_id, start_row_id + len(device.storage_space))
            ):
                self.storage[row_id] = device.storage_space[i]
        else:
            self.storage[self.row_id_counter + 1] = None

        self.headers.add(self.row_id_counter)
        self.row_ids_active.append(self.row_id_counter)

        row = self.rowCount()
        self.insertRows(row, no_rows)
        logging.debug(
            "Adding %s to %s display with scan id %s at row %s",
            device.name(),
            self.device_display_type,
            scan_id,
            row,
        )
        for row_id in range(self.row_id_counter, self.row_id_counter + no_rows):
            self.row_id_to_scan_id[row_id] = scan_id
            self.rows[row] = row_id
            self.scan_id_to_row_ids[scan_id].append(row_id)
            row += 1
        self.row_id_counter += no_rows

        self.devices[scan_id] = device
        self.spinner_state[scan_id] = DeviceState.scanning
        self.icons[scan_id] = device.get_pixmap(QSize(self.icon_size, self.icon_size))

        if self._isSpinning is False:
            self.startSpinners()

    def updateDeviceNameAndStorage(self, scan_id: int, device: Device) -> None:
        """
        Update Cameras with updated storage information and display
        name as reported by libgphoto2.

        If number of storage devies is > 1, inserts additional rows
        for the camera.

        :param scan_id: id of the camera
        :param device: camera device
        """

        row_ids = self.scan_id_to_row_ids[scan_id]
        if len(device.storage_space) > 1:
            # Add a new row after the current empty storage row
            row_id = row_ids[1]
            row = self.rows.row(row_id)
            logging.debug(
                "Adding row %s for additional storage device for %s",
                row,
                device.display_name,
            )

            for i in range(len(device.storage_space) - 1):
                row += 1
                new_row_id = self.row_id_counter + i
                self.rows.insert_row(row, new_row_id)
                self.scan_id_to_row_ids[scan_id].append(new_row_id)
                self.row_id_to_scan_id[new_row_id] = scan_id
            self.row_id_counter += len(device.storage_space) - 1

        for idx, storage_space in enumerate(device.storage_space):
            row_id = row_ids[idx + 1]
            self.storage[row_id] = storage_space

        row = self.rows.row(row_ids[0])
        self.dataChanged.emit(
            self.index(row, 0),
            self.index(row + len(self.devices[scan_id].storage_space), 0),
        )

    def getHeaderRowId(self, scan_id: int) -> int:
        row_ids = self.scan_id_to_row_ids[scan_id]
        return row_ids[0]

    def removeDevice(self, scan_id: int) -> None:
        row_ids = self.scan_id_to_row_ids[scan_id]
        header_row_id = row_ids[0]
        row = self.rows.row(header_row_id)
        logging.debug(
            "Removing %s rows from %s display, starting at row %s",
            len(row_ids),
            self.device_display_type,
            row,
        )
        self.rows.remove_rows(row, len(row_ids))
        del self.devices[scan_id]
        del self.spinner_state[scan_id]
        if scan_id in self.checked:
            del self.checked[scan_id]
        if header_row_id in self.row_ids_active:
            self.row_ids_active.remove(header_row_id)
            if len(self.row_ids_active) == 0:
                self.stopSpinners()
        self.headers.remove(header_row_id)
        del self.scan_id_to_row_ids[scan_id]
        for row_id in row_ids:
            del self.row_id_to_scan_id[row_id]

        self.removeRows(row, len(row_ids))

    def updateDeviceScan(self, scan_id: int) -> None:
        row_id = self.scan_id_to_row_ids[scan_id][0]
        row = self.rows.row(row_id)
        # TODO perhaps optimize which storage space is updated
        self.dataChanged.emit(
            self.index(row + 1, 0),
            self.index(row + len(self.devices[scan_id].storage_space), 0),
        )

    def setSpinnerState(self, scan_id: int, state: DeviceState) -> None:
        row_id = self.getHeaderRowId(scan_id)
        row = self.rows.row(row_id)

        current_state = self.spinner_state[scan_id]
        current_state_active = current_state in (
            DeviceState.scanning,
            DeviceState.downloading,
        )

        if current_state_active and state in (DeviceState.idle, DeviceState.finished):
            self.row_ids_active.remove(row_id)
            self.percent_complete[scan_id] = 0.0
            if len(self.row_ids_active) == 0:
                self.stopSpinners()
        # Next line assumes spinners were started when a device was added
        elif not current_state_active and state == DeviceState.downloading:
            self.row_ids_active.append(row_id)
            if not self._isSpinning:
                self.startSpinners()

        self.spinner_state[scan_id] = state
        self.dataChanged.emit(self.index(row, 0), self.index(row, 0))

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        if row >= len(self.rows) or row < 0:
            return None
        if row not in self.rows:
            return None

        row_id = self.rows[row]
        scan_id = self.row_id_to_scan_id[row_id]

        match role:
            case Qt.DisplayRole:
                return (
                    ViewRowType.header
                    if row_id in self.headers
                    else ViewRowType.content
                )
            case Qt.CheckStateRole:
                return self.checked[scan_id]
            case Roles.scan_id:
                return scan_id
            case Roles.device_status:
                return self._dataDeviceStatus()
            case _:
                device: Device = self.devices[scan_id]
                match role:
                    case Qt.ToolTipRole:
                        if device.device_type in (DeviceType.path, DeviceType.volume):
                            return device.path
                    case Roles.device_details:
                        return (
                            device.display_name,
                            self.icons[scan_id],
                            self.spinner_state[scan_id],
                            self._rotation_position,
                            self.percent_complete[scan_id],
                        )
                    case Roles.storage:
                        return device, self.storage[row_id]
                    case Roles.device_type:
                        return device.device_type
                    case Roles.download_statuses:
                        return device.download_statuses
        return None

    def _dataDeviceStatus(self) -> DeviceState | None:
        return None

    def setData(self, index: QModelIndex, value, role: int) -> bool:
        if not index.isValid():
            return False

        row = index.row()
        if row >= len(self.rows) or row < 0:
            return False
        row_id = self.rows[row]
        scan_id = self.row_id_to_scan_id[row_id]

        if role == Qt.CheckStateRole:
            # In theory, update checkbox immediately, as selecting a very large number
            # of thumbnails can take time. However, the code is probably wrong, as it
            # doesn't work:
            # self.setCheckedValue(
            #   checked=value, scan_id=scan_id, row=row, log_state_change=False
            # )
            # QApplication.instance().processEvents()
            self.rapidApp.thumbnailModel.checkAll(value, scan_id=scan_id)
            return True
        return False

    def logState(self) -> None:
        if len(self.devices):
            logging.debug("-- Device Model for %s --", self.device_display_type)
            logging.debug(
                "Known devices: %s",
                ", ".join(self.devices[device].display_name for device in self.devices),
            )
            for row in self.rows.row_to_id:
                row_id = self.rows.row_to_id[row]
                scan_id = self.row_id_to_scan_id[row_id]
                device = self.devices[scan_id]
                logging.debug("Row %s: %s", row, device.display_name)
            logging.debug(
                "Spinner states: %s",
                ", ".join(
                    (
                        f"{self.devices[scan_id].display_name}: "
                        f"{self.spinner_state[scan_id].name}"
                    )
                    for scan_id in self.spinner_state
                ),
            )
            logging.debug(
                ", ".join(
                    (
                        f"{self.devices[scan_id].display_name}: "
                        f"{Checked_Status[self.checked[scan_id]]}"
                    )
                    for scan_id in self.checked
                )
            )

    def setCheckedValue(
        self,
        checked: Qt.CheckState,
        scan_id: int,
        row: int | None = None,
        log_state_change: bool | None = True,
    ) -> None:
        logging.debug(
            "Setting %s checkbox to %s",
            self.devices[scan_id].display_name,
            Checked_Status[checked],
        )
        if row is None:
            row_id = self.scan_id_to_row_ids[scan_id][0]
            row = self.rows.row(row_id)
        self.checked[scan_id] = checked
        self.dataChanged.emit(self.index(row, 0), self.index(row, 0))

        if log_state_change:
            self.logState()

    def startSpinners(self):
        self._isSpinning = True

        if not self._timer.isActive():
            self._timer.start()
            self._rotation_position = 0

    def stopSpinners(self):
        self._isSpinning = False

        if self._timer.isActive():
            self._timer.stop()
            self._rotation_position = 0

    @pyqtSlot()
    def rotateSpinner(self):
        self._rotation_position += 1
        if self._rotation_position >= number_spinner_lines:
            self._rotation_position = 0
        for row_id in self.row_ids_active:
            row = self.rows.row(row_id)
            self.dataChanged.emit(self.index(row, 0), self.index(row, 0))


class DeviceView(ListViewFlexiFrame):
    def __init__(
        self,
        rapidApp,
        frame_enabled: bool | None = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(frame_enabled=frame_enabled, parent=parent)
        self.rapidApp = rapidApp
        # Disallow the user from being able to select the table cells
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.view_width = DeviceComponent().sampleWidth()
        # Assume view is always going to be placed into a container that can be scrolled
        # or a splitter
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.setMouseTracking(True)
        self.entered.connect(self.rowEntered)

    @pyqtSlot(int)
    def widthChanged(self, width: int) -> None:
        self.updateGeometry()

    def sizeHint(self):
        height = self.minimumHeight()
        return QSize(self.view_width, height)

    def minimumHeight(self) -> int:
        model: DeviceModel = self.model()
        if model.rowCount() > 0:
            height = 0
            for row in range(self.model().rowCount()):
                row_height = self.sizeHintForRow(row)
                height += row_height
            height += len(model.headers) + 5
            return height
        return EmptyViewHeight

    def minimumSizeHint(self):
        return self.sizeHint()

    @pyqtSlot(QModelIndex)
    def rowEntered(self, index: QModelIndex) -> None:
        if index.data() == ViewRowType.header and len(self.rapidApp.devices) > 1:
            scan_id = index.data(Roles.scan_id)
            self.rapidApp.thumbnailModel.highlightDeviceThumbs(scan_id=scan_id)


def standard_height() -> int:
    return QFontMetrics(QFont()).height()


def device_name_height() -> int:
    return standard_height() + DeviceDisplayPadding * 3


def device_header_row_height() -> int:
    return device_name_height() + DeviceDisplayPadding


def folder_icon_width() -> int:
    return QIcon(data_file_path("icons/folder.svg")).pixmap(icon_size()).width()


def warningPixmap() -> QPixmap:
    width = folder_icon_width()
    white = QColor(Qt.GlobalColor.white)

    pixmap = QPixmap(width, width)
    painter = QPainter()
    painter.begin(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(white))

    rect = QRectF(0.0, 0.0, float(width), float(width))

    painter.fillRect(rect, QColor(COLOR_RED_WARNING_HTML))

    # Draw a triangle
    path = QPainterPath()
    triangle_center = rect.left() + rect.width() / 2
    path.moveTo(triangle_center, rect.top())
    path.lineTo(rect.bottomLeft())
    path.lineTo(rect.bottomRight())
    path.lineTo(triangle_center, rect.top())

    painter.fillPath(path, QBrush(white))

    # Draw an exclamation point
    pen = QPen(QColor(COLOR_RED_WARNING_HTML))
    pen.setWidthF(1.5)
    painter.setPen(pen)

    vertical_padding = rect.height() / 3
    line_top = rect.top() + vertical_padding
    line_bottom = rect.bottom() - vertical_padding

    # Draw the top part of the exclamation point
    painter.drawLine(
        QPointF(triangle_center, line_top),
        QPointF(triangle_center, line_bottom),
    )
    # Draw the dot
    dot_y = vertical_padding / 2 + line_bottom
    painter.drawLine(
        QPointF(triangle_center, dot_y),
        QPointF(triangle_center, dot_y),
    )
    painter.end()
    return pixmap


class DropDownMenuButton(QToolButton):
    mousePressed = pyqtSignal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.mousePressed.emit()
        super().mousePressEvent(event)


class IconLabelWidget(QWidget):
    pathChanged = pyqtSignal(str, "PyQt_PyObject")

    def __init__(
        self,
        initial_text: str = "",
        pixmap: QPixmap | None = None,
        source: bool = False,  # checkbox, spinner, download complete icon
        show_menu_button: bool = False,
        folder_combo: bool = False,
        warning: bool = False,
        file_type: FileType | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.is_folder_combo = folder_combo
        self.is_source = source
        self.file_type = file_type
        gear_padding = 0

        if warning:
            pixmap = warningPixmap()
            backgroundColor = QColor(COLOR_RED_WARNING_HTML)
            textColor = QColor(Qt.GlobalColor.white)
        else:
            backgroundColor = device_name_highlight_color()
            textColor = None

        if source:
            self.checkbox = QCheckBox()
            self.spinnerWidget = SpinnerWidget()
            self.downloadCompleteLabel = QLabel()
            self.stackedWidget = QStackedWidget(parent=self)
            self.stackedWidget.addWidget(self.checkbox)
            self.stackedWidget.addWidget(self.spinnerWidget)
            self.stackedWidget.addWidget(self.downloadCompleteLabel)
            size = iconQSize()
            self.downloadedPixmap = scaledIcon(
                data_file_path("thumbnail/downloaded.svg")
            ).pixmap(size)
            self.downloadedWarningPixmap = scaledIcon(
                data_file_path("thumbnail/downloaded-with-warning.svg")
            ).pixmap(size)
            self.downloadedErrorPixmap = scaledIcon(
                data_file_path("thumbnail/downloaded-with-error.svg")
            ).pixmap(size)
            self.MAP_DOWNLOADED_STATE = {
                SourceState.downloaded: self.downloadedPixmap,
                SourceState.downloaded_warning: self.downloadedWarningPixmap,
                SourceState.downloaded_error: self.downloadedErrorPixmap,
            }

        self.pixmap = pixmap
        if pixmap is not None:
            self.iconLabel = QLabel()
            self.iconLabel.setPixmap(self.pixmap)
            self.iconLabel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        palette = QPalette()
        palette.setColor(QPalette.Window, backgroundColor)
        if textColor is not None:
            palette.setColor(QPalette.WindowText, textColor)
        self.setAutoFillBackground(True)
        self.setPalette(palette)

        layout = QHBoxLayout()
        layout.setSpacing(0)

        if warning:
            # Warnings are kept in a container widget, such that if there is more than
            # one warning, the vertical gap between them will be DeviceDisplayPadding
            v = DeviceDisplayPadding // 2
        else:
            gear_padding = 2
            v = (
                DeviceDisplayVPadding - gear_padding * 2
                if show_menu_button
                else DeviceDisplayVPadding
            )
        layout.setContentsMargins(DeviceDisplayPadding, v, DeviceDisplayPadding, v)

        if source:
            self.sourceWidget = QWidget()
            sourceLayout = QHBoxLayout()
            sourceLayout.setSpacing(0)
            sourceLayout.setContentsMargins(0, 0, DeviceDisplayPadding, 0)
            sourceLayout.addWidget(
                self.stackedWidget, alignment=Qt.AlignmentFlag.AlignCenter
            )
            self.sourceWidget.setLayout(sourceLayout)
            layout.addWidget(self.sourceWidget)
            self.sourceWidget.setVisible(False)

        if pixmap is not None:
            layout.addWidget(self.iconLabel)
            if not folder_combo:
                layout.addSpacing(DeviceDisplayPadding)
        else:
            layout.addSpacing(folder_icon_width() + DeviceDisplayPadding)

        if folder_combo:
            self.folderCombo = ChevronComboSpaced(QFont(), initial_text)
            self.folderCombo.setPalette(palette)
            layout.addWidget(self.folderCombo, 100)
            self.folderCombo.setInsertPolicy(QComboBox.InsertPolicy.InsertAtTop)
            self.folderCombo.currentIndexChanged.connect(self._indexChanged)
            self.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        else:
            self.textLabel = QLabel()
            self.textLabel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self.textLabel.setPalette(palette)
            layout.addWidget(self.textLabel)

        layout.addStretch()

        if show_menu_button:
            if is_dark_mode():
                hoverColor = QPalette().color(QPalette.Highlight)
            else:
                hoverColor = device_name_highlight_color().darker(115)
            gearPixmap = darkModePixmap(
                path="icons/settings.svg",
                size=QSize(pixmap.width(), pixmap.height()),
                soften_regular_mode_color=True,
            )
            self.button = DropDownMenuButton(self)
            self.button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            self.button.setIcon(QIcon(gearPixmap))
            self.button.setStyleSheet(
                f"""
                QToolButton {{
                    border: 0px;
                    padding: {gear_padding}px; 
                }}
                QToolButton:hover {{
                    background-color: {hoverColor.name()};
                }}
                QToolButton::menu-indicator {{
                    image: none; 
                }}
                """
            )
            layout.addWidget(self.button, alignment=Qt.AlignRight)
        self.setLayout(layout)

    def setPath(self, text: str) -> None:
        if self.is_folder_combo:
            display_name, path = get_path_display_name(text)
            index = self.folderCombo.findData(path)
            match index:
                case 0:
                    return
                case -1:
                    state = self.blockSignals(True)
                case _:
                    state = self.blockSignals(True)
                    self.folderCombo.removeItem(index)
            self.folderCombo.insertItem(0, display_name, text)
            self.folderCombo.setCurrentIndex(0)
            self.blockSignals(state)
        else:
            self.textLabel.setText(text)

    @pyqtSlot(int)
    def _indexChanged(self, index: int) -> None:
        path = self.folderCombo.itemData(index)
        self.pathChanged.emit(path, self.file_type)

    def insertPaths(self, paths: list[str]) -> None:
        state = self.blockSignals(True)
        for p in paths:
            display_name, path = get_path_display_name(p)
            self.folderCombo.addItem(display_name, path)
        self.folderCombo.setCurrentIndex(0)
        self.blockSignals(state)

    def enterEvent(self, event: QEvent) -> None:
        super().enterEvent(event)
        if self.is_folder_combo:
            self.folderCombo.hovered = True
            self.folderCombo.update()

    def leaveEvent(self, event: QEvent) -> None:
        super().leaveEvent(event)
        if self.is_folder_combo:
            self.folderCombo.hovered = False
            self.folderCombo.update()

    def setSourceWidgetVisible(self, visible: bool) -> None:
        self.sourceWidget.setVisible(visible)

    def setSourceWidget(self, sourceState: SourceState) -> None:
        match sourceState:
            case SourceState.checkbox:
                self.stackedWidget.setCurrentIndex(0)
            case SourceState.spinner:
                self.stackedWidget.setCurrentIndex(1)
            case _:
                self.stackedWidget.setCurrentIndex(2)
                self.downloadCompleteLabel.setPixmap(
                    self.MAP_DOWNLOADED_STATE[sourceState]
                )


class WarningWidget(QWidget):
    """
    Contains either or both of the following:
    1.  general status row, e.g. "Folder is read-only"
    2.  no space row, e.g. "Not enough space"
    If neither are visible, this widget makes itself invisible
    """

    def __init__(self, device_row_item: DeviceRowItem, parent: QWidget) -> None:
        super().__init__(parent)
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(COLOR_RED_WARNING_HTML))
        self.setAutoFillBackground(True)
        self.setPalette(palette)
        layout = QVBoxLayout()
        padding = DeviceDisplayPadding
        layout.setContentsMargins(0, padding, 0, padding)
        layout.setSpacing(0)
        self.setLayout(layout)

        self.device_row_item = device_row_item

        if DeviceRowItem.dir_invalid & device_row_item:
            self.statusRow = IconLabelWidget(warning=True, parent=self)
            self.status = DeviceDisplayStatus.valid
            layout.addWidget(self.statusRow)

        if DeviceRowItem.no_storage_space & device_row_item:
            self.noStorageSpaceRow = IconLabelWidget(warning=True, parent=self)
            self.noStorageSpaceRow.textLabel.setText(
                DIR_PROBLEM_TEXT[DeviceDisplayStatus.no_storage_space]
            )
            self.no_space = False
            layout.addWidget(self.noStorageSpaceRow)

    def setStatus(self, status: DeviceDisplayStatus) -> None:
        assert bool(DeviceRowItem.dir_invalid & self.device_row_item)
        self.status = status
        if status != DeviceDisplayStatus.valid:
            self.statusRow.textLabel.setText(DIR_PROBLEM_TEXT[status])
        self._setVisibility()

    def setNoSpace(self, no_space: bool) -> None:
        assert bool(DeviceRowItem.no_storage_space & self.device_row_item)
        self.no_space = no_space
        self._setVisibility()

    def _setVisibility(self) -> None:
        status_visible = (
            bool(DeviceRowItem.dir_invalid & self.device_row_item)
            and self.status != DeviceDisplayStatus.valid
        )
        no_space_visible = (
            bool(DeviceRowItem.no_storage_space & self.device_row_item)
            and self.no_space
        )

        self.setVisible(status_visible or no_space_visible)
        if DeviceRowItem.dir_invalid & self.device_row_item:
            self.statusRow.setVisible(status_visible)
        if DeviceRowItem.no_storage_space & self.device_row_item:
            self.noStorageSpaceRow.setVisible(no_space_visible)


class UsageWidget(QWidget):
    """
    Render the usage portion of a Device Row, which contains basic storage space
    information, a colored bar with a gradient that visually represents allocation of
    the storage space, and details about the size and number of photos / videos.

    For download destinations, it also displays excess usage.
    """

    shading_intensity = DeviceShadingIntensity
    storageBorderColor = QColor("#bcbcbc")
    emptySpaceColor = QColor("#f2f2f2")
    leftBottom = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
    rightBottom = int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
    leftTop = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

    def __init__(self, parent, is_source: bool, frame: bool = False) -> None:
        super().__init__(parent)
        self.rendering_destination = not is_source
        # TODO move these out of the special class
        self.dc = DeviceComponent(parent=self)
        self.setAutoFillBackground(True)
        palette = QPalette()
        palette.setColor(QPalette.Window, palette.color(palette.Base))
        self.setPalette(palette)

        self.details: UsageDetails | None = None

        self.frame_width = QApplication.style().pixelMetric(QStyle.PM_DefaultFrameWidth)
        self.frame = frame and self.frame_width

        height = self.dc.storage_height
        if self.frame:
            self.midPen = paletteMidPen()
            self.container_vertical_scrollbar_visible = None
            height += self.frame_width * 2

        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)

        # TODO confirm this is the correct minimum width
        self.setMinimumWidth(self.dc.sampleWidth())

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter()
        painter.begin(self)

        x = 0
        y = 0
        width = self.width()
        width -= self.dc.padding * 2 + 1

        standard_pen_color = painter.pen().color()

        if self.frame:
            rect = self.rect()
            painter.setPen(self.midPen)
            painter.drawLine(rect.bottomLeft(), rect.bottomRight())
            painter.drawLine(rect.topLeft(), rect.bottomLeft())
            if (
                self.container_vertical_scrollbar_visible is None
                or not self.container_vertical_scrollbar_visible
            ):
                painter.drawLine(rect.topRight(), rect.bottomRight())
            painter.setPen(standard_pen_color)
            x += self.frame_width
            y += self.frame_width
            width -= self.frame_width * 2

        x += self.dc.padding
        y += self.dc.vertical_padding
        d = self.details
        if d is None:
            painter.end()
            return

        painter.setRenderHint(QPainter.Antialiasing, False)

        painter.setFont(self.dc.deviceFont)

        device_size_x = x
        device_size_y = y + self.dc.standard_height - self.dc.padding

        text_rect = QRect(
            device_size_x, y - self.dc.padding, width, self.dc.standard_height
        )

        if self.rendering_destination:
            # bytes free of total size e.g. 123 MB free of 2 TB
            painter.drawText(text_rect, self.leftBottom, d.bytes_free_of_total)

            # Render the used space in the gradient bar before rendering the space
            # that will be taken by photos and videos
            comp1_file_size_sum = d.comp3_file_size_sum
            comp2_file_size_sum = d.comp1_file_size_sum
            comp3_file_size_sum = d.comp2_file_size_sum
            color1 = d.color3
            color2 = d.color1
            color3 = d.color2
        else:
            # Device size e.g. 32 GB
            painter.drawText(text_rect, self.leftBottom, d.bytes_total_text)
            # Percent used e.g. 79%
            painter.drawText(text_rect, self.rightBottom, d.percent_used_text)

            # Don't change the order
            comp1_file_size_sum = d.comp1_file_size_sum
            comp2_file_size_sum = d.comp2_file_size_sum
            comp3_file_size_sum = d.comp3_file_size_sum
            color1 = d.color1
            color2 = d.color2
            color3 = d.color3

        skip_comp1 = d.display_type == DisplayFileType.videos
        skip_comp2 = d.display_type == DisplayFileType.photos
        skip_comp3 = d.comp3_size_text == 0

        photos_g_x = device_size_x
        g_y = device_size_y + self.dc.padding
        if d.bytes_total:
            photos_g_width = comp1_file_size_sum / d.bytes_total * width
            linearGradient = QLinearGradient(
                photos_g_x, g_y, photos_g_x, g_y + self.dc.storage_use_bar_height
            )

        rect = QRectF(photos_g_x, g_y, width, self.dc.storage_use_bar_height)
        # Apply subtle shade to empty space
        painter.fillRect(rect, self.emptySpaceColor)

        # Storage Use Horizontal Bar
        # Shows space used by Photos, Videos, Other, and (sometimes) Excess.
        # ==========================================================================

        # Devices may not have photos or videos
        # Fill in storage bar with the size of the photos
        if comp1_file_size_sum and d.bytes_total:
            photos_g_rect = QRectF(
                photos_g_x, g_y, photos_g_width, self.dc.storage_use_bar_height
            )
            linearGradient.setColorAt(0.2, color1.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, color1.darker(self.shading_intensity))
            painter.fillRect(photos_g_rect, QBrush(linearGradient))
        else:
            photos_g_width = 0

        # Fill in storage bar with size of videos
        videos_g_x = photos_g_x + photos_g_width
        if comp2_file_size_sum and d.bytes_total:
            videos_g_width = comp2_file_size_sum / d.bytes_total * width
            videos_g_rect = QRectF(
                videos_g_x, g_y, videos_g_width, self.dc.storage_use_bar_height
            )
            linearGradient.setColorAt(0.2, color2.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, color2.darker(self.shading_intensity))
            painter.fillRect(videos_g_rect, QBrush(linearGradient))
        else:
            videos_g_width = 0

        # Fill in the storage bar with size of other files
        if comp3_file_size_sum and d.bytes_total:
            other_g_width = comp3_file_size_sum / d.bytes_total * width
            other_g_x = videos_g_x + videos_g_width
            other_g_rect = QRectF(
                other_g_x, g_y, other_g_width, self.dc.storage_use_bar_height
            )
            linearGradient.setColorAt(0.2, color3.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, color3.darker(self.shading_intensity))
            painter.fillRect(other_g_rect, QBrush(linearGradient))

        if d.comp4_file_size_sum and d.bytes_total:
            # Excess usage, only for download destinations
            color4 = QColor(CustomColors.color6.value)
            comp4_g_width = d.comp4_file_size_sum / d.bytes_total * width
            comp4_g_x = x + width - comp4_g_width
            comp4_g_rect = QRectF(
                comp4_g_x, g_y, comp4_g_width, self.dc.storage_use_bar_height
            )
            linearGradient.setColorAt(0.2, color4.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, color4.darker(self.shading_intensity))
            painter.fillRect(comp4_g_rect, QBrush(linearGradient))

        # Rectangle around spatial representation of sizes
        painter.setPen(self.storageBorderColor)
        painter.drawRect(rect)
        bottom = rect.bottom()

        details_y = bottom + self.dc.vertical_padding

        painter.setFont(self.dc.deviceFont)

        # Component 4 details
        # If excess is shown, it is shown first, before anything else.
        # Excess usage, only displayed if the storage space is not sufficient.
        # =====================================================================

        if d.comp4_file_size_sum:
            # Gradient
            comp4_g2_x = x
            comp4_g2_rect = QRectF(
                comp4_g2_x,
                details_y,
                self.dc.details_vertical_bar_width,
                self.dc.details_height,
            )
            linearGradient = QLinearGradient(
                comp4_g2_x, details_y, comp4_g2_x, details_y + self.dc.details_height
            )
            linearGradient.setColorAt(0.2, color4.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, color4.darker(self.shading_intensity))
            painter.fillRect(comp4_g2_rect, QBrush(linearGradient))
            painter.setPen(self.storageBorderColor)
            painter.drawRect(comp4_g2_rect)

            # Text
            comp4_x = comp4_g2_x + self.dc.details_vertical_bar_width + self.dc.spacer
            comp4_no_width = self.dc.deviceFontMetrics.boundingRect(
                d.comp4_text
            ).width()
            comp4_size_width = self.dc.deviceFontMetrics.boundingRect(
                d.comp4_size_text
            ).width()
            comp4_width = max(
                comp4_no_width,
                comp4_size_width,
                self.dc.sample_photos_width,
            )
            comp4_rect = QRectF(comp4_x, details_y, comp4_width, self.dc.details_height)

            painter.setPen(standard_pen_color)
            painter.drawText(comp4_rect, self.leftTop, d.comp4_text)
            painter.drawText(comp4_rect, self.leftBottom, d.comp4_size_text)
            photos_g2_x = comp4_rect.right() + 10
        else:
            photos_g2_x = x

        # Component 1 details
        # ===================

        if not skip_comp1:
            # Gradient
            photos_g2_rect = QRectF(
                photos_g2_x,
                details_y,
                self.dc.details_vertical_bar_width,
                self.dc.details_height,
            )
            linearGradient = QLinearGradient(
                photos_g2_x, details_y, photos_g2_x, details_y + self.dc.details_height
            )
            linearGradient.setColorAt(0.2, d.color1.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, d.color1.darker(self.shading_intensity))
            painter.fillRect(photos_g2_rect, QBrush(linearGradient))
            painter.setPen(self.storageBorderColor)
            painter.drawRect(photos_g2_rect)

            # Text
            photos_x = photos_g2_x + self.dc.details_vertical_bar_width + self.dc.spacer
            photos_no_width = self.dc.deviceFontMetrics.boundingRect(
                d.comp1_text
            ).width()
            photos_size_width = self.dc.deviceFontMetrics.boundingRect(
                d.comp1_size_text
            ).width()
            photos_width = max(
                photos_no_width,
                photos_size_width,
                self.dc.sample_photos_width,
            )
            photos_rect = QRectF(
                photos_x, details_y, photos_width, self.dc.details_height
            )

            painter.setPen(standard_pen_color)
            painter.drawText(photos_rect, self.leftTop, d.comp1_text)
            painter.drawText(photos_rect, self.leftBottom, d.comp1_size_text)
            videos_g2_x = photos_rect.right() + self.dc.inter_device_padding

        else:
            videos_g2_x = photos_g2_x

        # Component 2 details
        # ===================

        if not skip_comp2:
            # Gradient
            videos_g2_rect = QRectF(
                videos_g2_x,
                details_y,
                self.dc.details_vertical_bar_width,
                self.dc.details_height,
            )
            linearGradient.setColorAt(0.2, d.color2.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, d.color2.darker(self.shading_intensity))
            painter.fillRect(videos_g2_rect, QBrush(linearGradient))
            painter.setPen(self.storageBorderColor)
            painter.drawRect(videos_g2_rect)

            # Text
            videos_x = videos_g2_x + self.dc.details_vertical_bar_width + self.dc.spacer
            videos_no_width = self.dc.deviceFontMetrics.boundingRect(
                d.comp2_text
            ).width()
            videos_size_width = self.dc.deviceFontMetrics.boundingRect(
                d.comp2_size_text
            ).width()
            videos_width = max(
                videos_no_width,
                videos_size_width,
                self.dc.sample_videos_width,
            )
            videos_rect = QRectF(
                videos_x, details_y, videos_width, self.dc.details_height
            )

            painter.setPen(standard_pen_color)
            painter.drawText(videos_rect, self.leftTop, d.comp2_text)
            painter.drawText(videos_rect, self.leftBottom, d.comp2_size_text)

            other_g2_x = videos_rect.right() + self.dc.inter_device_padding
        else:
            other_g2_x = videos_g2_x

        if not skip_comp3 and (d.comp3_file_size_sum or self.rendering_destination):
            # Other details
            # =============

            # Gradient

            other_g2_rect = QRectF(
                other_g2_x,
                details_y,
                self.dc.details_vertical_bar_width,
                self.dc.details_height,
            )
            linearGradient.setColorAt(0.2, d.color3.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, d.color3.darker(self.shading_intensity))
            painter.fillRect(other_g2_rect, QBrush(linearGradient))
            painter.setPen(self.storageBorderColor)
            painter.drawRect(other_g2_rect)

            # Text
            other_x = other_g2_x + self.dc.details_vertical_bar_width + self.dc.spacer
            other_no_width = self.dc.deviceFontMetrics.boundingRect(
                d.comp3_text
            ).width()
            other_size_width = self.dc.deviceFontMetrics.boundingRect(
                d.comp3_size_text
            ).width()
            other_width = max(other_no_width, other_size_width)
            other_rect = QRectF(other_x, details_y, other_width, self.dc.details_height)

            painter.setPen(standard_pen_color)
            painter.drawText(other_rect, self.leftTop, d.comp3_text)
            painter.drawText(other_rect, self.leftBottom, d.comp3_size_text)

            final_g2_x = other_rect.right()
        else:
            final_g2_x = other_g2_x

        painter.end()
        self.dc.live_width = round(final_g2_x)


class InitialHeader(QLabel):
    def __init__(self, message: str, parent) -> None:
        super().__init__(parent)
        self.setText(message)
        font = self.font()
        font.setItalic(True)
        self.setFont(font)
        self.setAutoFillBackground(True)
        palette = QPalette()
        palette.setColor(QPalette.Window, device_name_highlight_color())
        self.setPalette(palette)
        self.setContentsMargins(
            DeviceDisplayPadding,
            DeviceDisplayVPadding,
            DeviceDisplayPadding,
            DeviceDisplayVPadding,
        )


class DeviceRows(QWidget):
    def __init__(
        self,
        device_row_item: DeviceRowItem,
        initial_header_message: str = "",
        file_type: FileType | None = None,
    ) -> None:
        super().__init__()

        self.device_row_item = device_row_item

        if DeviceRowItem.initial_header & device_row_item:
            self.initialHeader = InitialHeader(initial_header_message, self)

        if DeviceRowItem.icon & device_row_item:
            assert DeviceRowItem.header & device_row_item
            size = iconQSize()
            pixmap = darkModePixmap(path="icons/folder.svg", size=size)
        else:
            pixmap = None

        deviceLayout = QVBoxLayout()
        deviceLayout.setSpacing(0)
        deviceLayout.setContentsMargins(0, 0, 0, 0)

        is_source = bool(DeviceRowItem.source & device_row_item)

        if DeviceRowItem.header & device_row_item:
            self.headerWidget = IconLabelWidget(
                initial_text=initial_header_message,
                pixmap=pixmap,
                source=is_source,
                show_menu_button=bool(DeviceRowItem.drop_down_menu & device_row_item),
                folder_combo=bool(DeviceRowItem.folder_combo & device_row_item),
                file_type=file_type,
                parent=self,
            )
            deviceLayout.addWidget(self.headerWidget)

        self.warningWidget = WarningWidget(parent=self, device_row_item=device_row_item)

        deviceLayout.addWidget(self.warningWidget)

        if DeviceRowItem.usage0 & device_row_item:
            self.usage0Widget = UsageWidget(
                parent=self,
                is_source=is_source,
                frame=bool(DeviceRowItem.frame & device_row_item),
            )
            self.USEAGE_MAPPER = {0: self.usage0Widget}
            deviceLayout.addWidget(self.usage0Widget)

            if DeviceRowItem.usage1 & device_row_item:
                self.usage1Widget = UsageWidget(parent=self, is_source=is_source)
                self.USEAGE_MAPPER = {1: self.usage1Widget}
                deviceLayout.addWidget(self.usage1Widget)

        if DeviceRowItem.initial_header & device_row_item:
            layout = QVBoxLayout()
            layout.setSpacing(0)
            layout.setContentsMargins(0, 0, 0, 0)
            self.deviceWidget = QWidget()
            self.deviceWidget.setLayout(deviceLayout)

            self.stackedWidget = ResizableStackedWidget()
            self.stackedWidget.addWidget(self.initialHeader)
            self.stackedWidget.addWidget(self.deviceWidget)
            layout.addWidget(self.stackedWidget)
            self.setLayout(layout)
        else:
            self.setLayout(deviceLayout)

        if DeviceRowItem.dir_invalid & device_row_item:
            self.setDeviceDisplayStatus(DeviceDisplayStatus.valid)
        if DeviceRowItem.no_storage_space & device_row_item:
            self.setNoSpace(False)

    def setHeaderText(self, text: str) -> None:
        self.headerWidget.setPath(text)

    def setHeaderToolTip(self, text: str) -> None:
        self.headerWidget.setToolTip(text)

    def _emulateInitialState(self, emulate: bool) -> None:
        state=self.blockSignals(True)
        index = -1 if emulate else 0
        self.headerWidget.folderCombo.setCurrentIndex(index)
        self.blockSignals(state)
        self.headerWidget.folderCombo.initial_state = emulate
        self.headerWidget.iconLabel.setVisible(not emulate)
        self.usage0Widget.setVisible(not emulate)
        if DeviceRowItem.drop_down_menu & self.device_row_item:
            self.headerWidget.button.setVisible(not emulate)

    def setDeviceDisplayStatus(self, status: DeviceDisplayStatus) -> None:
        assert DeviceRowItem.initial_header & self.device_row_item
        match status:
            case DeviceDisplayStatus.unspecified_choices_available:
                assert DeviceRowItem.folder_combo & self.device_row_item
                self._emulateInitialState(True)
                self.stackedWidget.setCurrentIndex(1)
            case DeviceDisplayStatus.unspecified:
                self.stackedWidget.setCurrentIndex(0)
            case _:
                if DeviceRowItem.folder_combo & self.device_row_item:
                    self._emulateInitialState(False)
                self.stackedWidget.setCurrentIndex(1)
                self.warningWidget.setStatus(status)


    def setNoSpace(self, no_space: bool) -> None:
        self.warningWidget.setNoSpace(no_space)

    def setUsageVisible(self, visible: bool, usage_num: int = 0) -> None:
        self.USEAGE_MAPPER[usage_num].setVisible(visible)

    def setUsage(self, details: UsageDetails, usage_num: int = 0) -> None:
        widget = self.USEAGE_MAPPER[usage_num]
        widget.details = details
        widget.update()

    def setSourceWidgetVisible(self, visible: bool) -> None:
        self.headerWidget.setSourceWidgetVisible(visible)

    def setSourceWidget(self, sourceState: SourceState) -> None:
        self.headerWidget.setSourceWidget(sourceState)

    def menuButton(self) -> DropDownMenuButton:
        assert DeviceRowItem.drop_down_menu & self.device_row_item
        return self.headerWidget.button


class ThisComputerDeviceRows(DeviceRows):
    def __init__(self) -> None:
        super().__init__(
            initial_header_message=_("Select a source folder"),
            device_row_item=DeviceRowItem.initial_header
            | DeviceRowItem.header
            | DeviceRowItem.source
            | DeviceRowItem.icon
            | DeviceRowItem.dir_invalid
            | DeviceRowItem.folder_combo
            | DeviceRowItem.usage0,
        )


class PhotoOrVideoDestDeviceRows(DeviceRows):
    def __init__(self, file_type: FileType) -> None:
        super().__init__(
            initial_header_message=_("Select a destination folder"),
            device_row_item=DeviceRowItem.initial_header
            | DeviceRowItem.header
            | DeviceRowItem.icon
            | DeviceRowItem.dir_invalid
            | DeviceRowItem.no_storage_space
            | DeviceRowItem.folder_combo
            | DeviceRowItem.drop_down_menu
            | DeviceRowItem.usage0,
            file_type=file_type,
        )


class DeviceComponent(QObject):
    """
    Calculate Device, Destination and Backup Display component sizes
    """

    widthChanged = pyqtSignal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent=parent)
        style = QApplication.style()
        self.frame_width = style.pixelMetric(QStyle.PM_DefaultFrameWidth)
        self.scrollbar_width = style.pixelMetric(QStyle.PM_ScrollBarExtent)

        self.padding = DeviceDisplayPadding
        self.header_horizontal_padding = 8
        self.vertical_padding = 10
        self.menu_button_padding = 3
        self.inter_device_padding = 10
        self.spacer = 3

        standardFont = QFont()
        self.standard_height = QFontMetrics(standardFont).height()

        # Base height is when there is no storage space to display
        self.base_height = self.padding * 2 + self.standard_height

        self.icon_size = icon_size()
        self.icon_x_offset = 0

        # A small font used for all the text seen in the body
        self.deviceFont = QFont()
        self.deviceFont.setPointSize(standardFont.pointSize() - 2)
        self.deviceFontMetrics = QFontMetrics(self.deviceFont)

        # Storage Use Horizontal Bar
        self.storage_use_bar_height = self.standard_height

        # Storage Details, broken down by photo, video, and other files
        sample_number = thousands(9999)
        sample_no_photos = "{} {}".format(sample_number, _("Photos"))
        sample_no_videos = "{} {}".format(sample_number, _("Videos"))
        self.sample_photos_width = self.deviceFontMetrics.boundingRect(
            sample_no_photos
        ).width()
        self.sample_videos_width = self.deviceFontMetrics.boundingRect(
            sample_no_videos
        ).width()
        sample_comp3 = format_size_for_user(261780000)  # 261.78 MB
        self.sample_comp3_width = self.deviceFontMetrics.boundingRect(
            sample_comp3
        ).width()

        # Height of the details about the storage e.g., number of photos,
        # videos, etc.
        self.details_height = self.deviceFontMetrics.height() * 2 + 2
        self.details_vertical_bar_width = 10

        # Storage height is when there is storage space to display
        self.storage_height = (
            self.standard_height
            + self.padding
            + self.storage_use_bar_height
            + self.vertical_padding
            + self.details_height
            + self.padding * 2
        )

        # Height of the colored box that includes a device's icon & name,
        # and when a source device, the spinner/checkbox
        self.device_name_strip_height = device_name_height()
        self.device_name_height = device_header_row_height()

        # Track the width of the details components in real time
        self._live_width = 0

        self.warning_status_height = QFontMetrics(QFont()).height() + self.padding * 2

    def sampleWidth(self) -> int:
        width = (
            self.sample_photos_width
            + self.sample_videos_width
            + self.sample_comp3_width
            + self.details_vertical_bar_width * 3
            + self.spacer * 2
            + self.inter_device_padding * 2
            + self.padding * 2
        )
        return width

    def minimumWidth(self) -> int:
        if self.live_width:
            width = self.live_width + self.padding * 2
            return width
        else:
            return self.sampleWidth()

    @property
    def live_width(self) -> int:
        return self._live_width

    @live_width.setter
    def live_width(self, width: int):
        if width != self._live_width:
            self._live_width = width
            self.widthChanged.emit(self.minimumWidth())


class DeviceDisplay(QObject):
    """
    Graphically render the storage space, and photos and videos that
    are currently in it or will be downloaded into it.

    Used in list view by devices / this computer, and in destination
    custom widget.
    """

    shading_intensity = DeviceShadingIntensity
    widthChanged = pyqtSignal(int)

    def __init__(self, parent: QObject, menuButtonIcon: QIcon | None = None) -> None:
        super().__init__(parent)
        self.menuButtonIcon = menuButtonIcon

        self.rendering_destination = True

        self.dc = DeviceComponent()
        self.dc.widthChanged.connect(self._widthChanged)

        self.view_width = self.dc.sampleWidth()

        self.deviceNameHighlightColor = device_name_highlight_color()
        self.storageBorderColor = QColor("#bcbcbc")
        if is_dark_mode():
            self.menuHighlightColor = QPalette().color(QPalette.Highlight)
        else:
            self.menuHighlightColor = self.deviceNameHighlightColor.darker(115)

        self.emptySpaceColor = QColor("#f2f2f2")
        self.invalidColor = QColor(COLOR_RED_WARNING_HTML)

    @pyqtSlot(int)
    def _widthChanged(self, width) -> None:
        self.view_width = width
        self.widthChanged.emit(width)

    def width(self) -> int:
        return self.view_width

    def vAlignHeaderPixmap(self, y: int, pixmap_height: int) -> float:
        return y + (self.dc.device_name_strip_height / 2 - pixmap_height / 2)

    def paintHeader(
        self,
        painter: QPainter,
        x: int,
        y: int,
        width: int,
        display_name: str,
        icon: QPixmap,
        highlight_menu: bool = False,
    ) -> None:
        """
        Render the header portion, which contains the device / folder name, icon, and
        for download sources, a spinner or checkbox.

        If needed, draw a pixmap for a drop-down menu.
        """

        painter.setRenderHint(QPainter.Antialiasing, True)

        deviceNameRect = QRectF(x, y, width, self.dc.device_name_strip_height)
        painter.fillRect(deviceNameRect, self.deviceNameHighlightColor)

        icon_x = float(x + self.dc.padding + self.dc.icon_x_offset)
        icon_y = self.vAlignHeaderPixmap(y, self.dc.icon_size)

        icon = darkModePixmap(pixmap=icon, soften_regular_mode_color=True)

        # Cannot use icon size for the target, because icons can be scaled to
        # high resolution
        target = QRectF(icon_x, icon_y, self.dc.icon_size, self.dc.icon_size)
        source = QRectF(0, 0, icon.width(), icon.height())

        painter.drawPixmap(target, icon, source)

        text_x = target.right() + self.dc.header_horizontal_padding
        deviceNameRect.setLeft(text_x)
        painter.drawText(
            deviceNameRect, int(Qt.AlignLeft | Qt.AlignVCenter), display_name
        )

        if self.menuButtonIcon:
            size = icon_size()
            rect = self.menuButtonRect(x, y, width)
            if highlight_menu:
                painter.fillRect(rect, self.menuHighlightColor)
            button_x = rect.x() + self.dc.menu_button_padding
            button_y = rect.y() + self.dc.menu_button_padding
            pixmap = self.menuButtonIcon.pixmap(QSize(size, size))
            painter.drawPixmap(QPointF(button_x, button_y), pixmap)

    def menuButtonRect(self, x: int, y: int, width: int) -> QRectF:
        size = icon_size() + self.dc.menu_button_padding * 2
        button_x = x + width - size - self.dc.padding
        button_y = y + self.dc.device_name_strip_height / 2 - size / 2
        return QRectF(button_x, button_y, size, size)

    def paintWarning(
        self, painter: QPainter, x: int, y: int, width: int, text: str
    ) -> None:
        displayPen = painter.pen()

        statusRect = QRect(x, y, width, self.dc.warning_status_height)
        painter.fillRect(statusRect, self.invalidColor)

        text_height = QFontMetrics(QFont()).height()
        white = QColor(Qt.GlobalColor.white)

        iconRect = QRectF(
            float(self.dc.padding),
            float(y + self.dc.padding),
            float(text_height),
            float(text_height),
        )
        # exclamationRect = iconRect.adjusted(0.25, 1.0, 0.25, 1.0)
        textRect = QRectF(
            iconRect.right() + self.dc.padding,
            iconRect.top(),
            width - iconRect.right() - self.dc.padding,
            float(text_height),
        )

        painter.setPen(QPen(white))

        # Draw a triangle
        path = QPainterPath()
        triangle_center = iconRect.left() + iconRect.width() / 2
        path.moveTo(triangle_center, iconRect.top())
        path.lineTo(iconRect.bottomLeft())
        path.lineTo(iconRect.bottomRight())
        path.lineTo(triangle_center, iconRect.top())

        painter.fillPath(path, QBrush(white))

        # Draw an exclamation point
        pen = QPen(self.invalidColor)
        pen.setWidthF(1.5)
        painter.setPen(pen)

        vertical_padding = iconRect.height() / 3
        line_top = iconRect.top() + vertical_padding
        line_bottom = iconRect.bottom() - vertical_padding

        # Draw the top part of the exclamation point
        painter.drawLine(
            QPointF(triangle_center, line_top),
            QPointF(triangle_center, line_bottom),
        )
        # Draw the dot
        dot_y = vertical_padding / 2 + line_bottom
        painter.drawLine(
            QPointF(triangle_center, dot_y),
            QPointF(triangle_center, dot_y),
        )

        # Draw the warning
        displayFont = painter.font()
        warningFont = QFont()
        painter.setFont(warningFont)
        painter.setPen(QPen(white))
        painter.drawText(
            textRect,
            Qt.TextFlag.TextSingleLine | Qt.AlignmentFlag.AlignVCenter,
            text,
        )
        painter.setPen(displayPen)
        painter.setFont(displayFont)

    def paintBody(
        self, painter: QPainter, x: int, y: int, width: int, details: UsageDetails
    ) -> None:
        """
        Render the usage portion, which contains basic storage space information,
        a colored bar with a gradient that visually represents allocation of the
        storage space, and details about the size and number of photos / videos.

        For download destinations, also displays excess usage.
        """

        x = x + self.dc.padding
        y = y + self.dc.padding
        width = width - self.dc.padding * 2
        d = details

        painter.setRenderHint(QPainter.Antialiasing, False)

        painter.setFont(self.dc.deviceFont)

        standard_pen_color = painter.pen().color()

        device_size_x = x
        device_size_y = y + self.dc.standard_height - self.dc.padding

        text_rect = QRect(
            device_size_x, y - self.dc.padding, width, self.dc.standard_height
        )

        if self.rendering_destination:
            # bytes free of total size e.g. 123 MB free of 2 TB
            painter.drawText(
                text_rect, Qt.AlignLeft | Qt.AlignBottom, d.bytes_free_of_total
            )

            # Render the used space in the gradient bar before rendering the space
            # that will be taken by photos and videos
            comp1_file_size_sum = d.comp3_file_size_sum
            comp2_file_size_sum = d.comp1_file_size_sum
            comp3_file_size_sum = d.comp2_file_size_sum
            color1 = d.color3
            color2 = d.color1
            color3 = d.color2
        else:
            # Device size e.g. 32 GB
            painter.drawText(
                text_rect, Qt.AlignLeft | Qt.AlignBottom, d.bytes_total_text
            )
            # Percent used e.g. 79%
            painter.drawText(
                text_rect, Qt.AlignRight | Qt.AlignBottom, d.percent_used_text
            )

            # Don't change the order
            comp1_file_size_sum = d.comp1_file_size_sum
            comp2_file_size_sum = d.comp2_file_size_sum
            comp3_file_size_sum = d.comp3_file_size_sum
            color1 = d.color1
            color2 = d.color2
            color3 = d.color3

        skip_comp1 = d.display_type == DisplayFileType.videos
        skip_comp2 = d.display_type == DisplayFileType.photos
        skip_comp3 = d.comp3_size_text == 0

        photos_g_x = device_size_x
        g_y = device_size_y + self.dc.padding
        if d.bytes_total:
            photos_g_width = comp1_file_size_sum / d.bytes_total * width
            linearGradient = QLinearGradient(
                photos_g_x, g_y, photos_g_x, g_y + self.dc.storage_use_bar_height
            )

        rect = QRectF(photos_g_x, g_y, width, self.dc.storage_use_bar_height)
        # Apply subtle shade to empty space
        painter.fillRect(rect, self.emptySpaceColor)

        # Storage Use Horizontal Bar
        # Shows space used by Photos, Videos, Other, and (sometimes) Excess.
        # ==========================================================================

        # Devices may not have photos or videos
        # Fill in storage bar with the size of the photos
        if comp1_file_size_sum and d.bytes_total:
            photos_g_rect = QRectF(
                photos_g_x, g_y, photos_g_width, self.dc.storage_use_bar_height
            )
            linearGradient.setColorAt(0.2, color1.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, color1.darker(self.shading_intensity))
            painter.fillRect(photos_g_rect, QBrush(linearGradient))
        else:
            photos_g_width = 0

        # Fill in storage bar with size of videos
        videos_g_x = photos_g_x + photos_g_width
        if comp2_file_size_sum and d.bytes_total:
            videos_g_width = comp2_file_size_sum / d.bytes_total * width
            videos_g_rect = QRectF(
                videos_g_x, g_y, videos_g_width, self.dc.storage_use_bar_height
            )
            linearGradient.setColorAt(0.2, color2.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, color2.darker(self.shading_intensity))
            painter.fillRect(videos_g_rect, QBrush(linearGradient))
        else:
            videos_g_width = 0

        # Fill in the storage bar with size of other files
        if comp3_file_size_sum and d.bytes_total:
            other_g_width = comp3_file_size_sum / d.bytes_total * width
            other_g_x = videos_g_x + videos_g_width
            other_g_rect = QRectF(
                other_g_x, g_y, other_g_width, self.dc.storage_use_bar_height
            )
            linearGradient.setColorAt(0.2, color3.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, color3.darker(self.shading_intensity))
            painter.fillRect(other_g_rect, QBrush(linearGradient))

        if d.comp4_file_size_sum and d.bytes_total:
            # Excess usage, only for download destinations
            color4 = QColor(CustomColors.color6.value)
            comp4_g_width = d.comp4_file_size_sum / d.bytes_total * width
            comp4_g_x = x + width - comp4_g_width
            comp4_g_rect = QRectF(
                comp4_g_x, g_y, comp4_g_width, self.dc.storage_use_bar_height
            )
            linearGradient.setColorAt(0.2, color4.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, color4.darker(self.shading_intensity))
            painter.fillRect(comp4_g_rect, QBrush(linearGradient))

        # Rectangle around spatial representation of sizes
        painter.setPen(self.storageBorderColor)
        painter.drawRect(rect)
        bottom = rect.bottom()

        details_y = bottom + self.dc.vertical_padding

        painter.setFont(self.dc.deviceFont)

        # Component 4 details
        # If excess is shown, it is shown first, before anything else.
        # Excess usage, only displayed if the storage space is not sufficient.
        # =====================================================================

        if d.comp4_file_size_sum:
            # Gradient
            comp4_g2_x = x
            comp4_g2_rect = QRectF(
                comp4_g2_x,
                details_y,
                self.dc.details_vertical_bar_width,
                self.dc.details_height,
            )
            linearGradient = QLinearGradient(
                comp4_g2_x, details_y, comp4_g2_x, details_y + self.dc.details_height
            )
            linearGradient.setColorAt(0.2, color4.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, color4.darker(self.shading_intensity))
            painter.fillRect(comp4_g2_rect, QBrush(linearGradient))
            painter.setPen(self.storageBorderColor)
            painter.drawRect(comp4_g2_rect)

            # Text
            comp4_x = comp4_g2_x + self.dc.details_vertical_bar_width + self.dc.spacer
            comp4_no_width = self.dc.deviceFontMetrics.boundingRect(
                d.comp4_text
            ).width()
            comp4_size_width = self.dc.deviceFontMetrics.boundingRect(
                d.comp4_size_text
            ).width()
            comp4_width = max(
                comp4_no_width,
                comp4_size_width,
                self.dc.sample_photos_width,
            )
            comp4_rect = QRectF(comp4_x, details_y, comp4_width, self.dc.details_height)

            painter.setPen(standard_pen_color)
            painter.drawText(comp4_rect, Qt.AlignLeft | Qt.AlignTop, d.comp4_text)
            painter.drawText(
                comp4_rect, Qt.AlignLeft | Qt.AlignBottom, d.comp4_size_text
            )
            photos_g2_x = comp4_rect.right() + 10
        else:
            photos_g2_x = x

        # Component 1 details
        # ===================

        if not skip_comp1:
            # Gradient
            photos_g2_rect = QRectF(
                photos_g2_x,
                details_y,
                self.dc.details_vertical_bar_width,
                self.dc.details_height,
            )
            linearGradient = QLinearGradient(
                photos_g2_x, details_y, photos_g2_x, details_y + self.dc.details_height
            )
            linearGradient.setColorAt(0.2, d.color1.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, d.color1.darker(self.shading_intensity))
            painter.fillRect(photos_g2_rect, QBrush(linearGradient))
            painter.setPen(self.storageBorderColor)
            painter.drawRect(photos_g2_rect)

            # Text
            photos_x = photos_g2_x + self.dc.details_vertical_bar_width + self.dc.spacer
            photos_no_width = self.dc.deviceFontMetrics.boundingRect(
                d.comp1_text
            ).width()
            photos_size_width = self.dc.deviceFontMetrics.boundingRect(
                d.comp1_size_text
            ).width()
            photos_width = max(
                photos_no_width,
                photos_size_width,
                self.dc.sample_photos_width,
            )
            photos_rect = QRectF(
                photos_x, details_y, photos_width, self.dc.details_height
            )

            painter.setPen(standard_pen_color)
            painter.drawText(photos_rect, Qt.AlignLeft | Qt.AlignTop, d.comp1_text)
            painter.drawText(
                photos_rect, Qt.AlignLeft | Qt.AlignBottom, d.comp1_size_text
            )
            videos_g2_x = photos_rect.right() + self.dc.inter_device_padding

        else:
            videos_g2_x = photos_g2_x

        # Component 2 details
        # ===================

        if not skip_comp2:
            # Gradient
            videos_g2_rect = QRectF(
                videos_g2_x,
                details_y,
                self.dc.details_vertical_bar_width,
                self.dc.details_height,
            )
            linearGradient.setColorAt(0.2, d.color2.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, d.color2.darker(self.shading_intensity))
            painter.fillRect(videos_g2_rect, QBrush(linearGradient))
            painter.setPen(self.storageBorderColor)
            painter.drawRect(videos_g2_rect)

            # Text
            videos_x = videos_g2_x + self.dc.details_vertical_bar_width + self.dc.spacer
            videos_no_width = self.dc.deviceFontMetrics.boundingRect(
                d.comp2_text
            ).width()
            videos_size_width = self.dc.deviceFontMetrics.boundingRect(
                d.comp2_size_text
            ).width()
            videos_width = max(
                videos_no_width,
                videos_size_width,
                self.dc.sample_videos_width,
            )
            videos_rect = QRectF(
                videos_x, details_y, videos_width, self.dc.details_height
            )

            painter.setPen(standard_pen_color)
            painter.drawText(videos_rect, Qt.AlignLeft | Qt.AlignTop, d.comp2_text)
            painter.drawText(
                videos_rect, Qt.AlignLeft | Qt.AlignBottom, d.comp2_size_text
            )

            other_g2_x = videos_rect.right() + self.dc.inter_device_padding
        else:
            other_g2_x = videos_g2_x

        if not skip_comp3 and (d.comp3_file_size_sum or self.rendering_destination):
            # Other details
            # =============

            # Gradient

            other_g2_rect = QRectF(
                other_g2_x,
                details_y,
                self.dc.details_vertical_bar_width,
                self.dc.details_height,
            )
            linearGradient.setColorAt(0.2, d.color3.lighter(self.shading_intensity))
            linearGradient.setColorAt(0.8, d.color3.darker(self.shading_intensity))
            painter.fillRect(other_g2_rect, QBrush(linearGradient))
            painter.setPen(self.storageBorderColor)
            painter.drawRect(other_g2_rect)

            # Text
            other_x = other_g2_x + self.dc.details_vertical_bar_width + self.dc.spacer
            other_no_width = self.dc.deviceFontMetrics.boundingRect(
                d.comp3_text
            ).width()
            other_size_width = self.dc.deviceFontMetrics.boundingRect(
                d.comp3_size_text
            ).width()
            other_width = max(other_no_width, other_size_width)
            other_rect = QRectF(other_x, details_y, other_width, self.dc.details_height)

            painter.setPen(standard_pen_color)
            painter.drawText(other_rect, Qt.AlignLeft | Qt.AlignTop, d.comp3_text)
            painter.drawText(
                other_rect, Qt.AlignLeft | Qt.AlignBottom, d.comp3_size_text
            )

            final_g2_x = other_rect.right()
        else:
            final_g2_x = other_g2_x

        self.dc.live_width = round(final_g2_x)


class AdvancedDeviceDisplay(DeviceDisplay):
    """
    Subclass to handle header for download devices/ This Computer
    """

    def __init__(self, parent: QObject):
        super().__init__(parent=parent)

        self.rendering_destination = False

        self.checkboxStyleOption = QStyleOptionButton()
        self.checkboxRect: QRect = QApplication.style().subElementRect(
            QStyle.SE_CheckBoxIndicator, self.checkboxStyleOption, None
        )
        self.checkbox_right = self.checkboxRect.right()
        self.checkbox_y_offset = (
            self.dc.device_name_strip_height - self.checkboxRect.height()
        ) // 2

        # Spinner values
        self.spinner_color = QColor(Qt.black)
        self.spinner_roundness = 100.0
        self.spinner_min_trail_opacity = 0.0
        self.spinner_trail_fade_percent = 60.0
        self.spinner_line_length = max(self.dc.icon_size // 4, 4)
        self.spinner_line_width = self.spinner_line_length // 2
        self.spinner_inner_radius = self.dc.icon_size // 2 - self.spinner_line_length

        self.dc.icon_x_offset = self.dc.icon_size + self.dc.header_horizontal_padding

        self.downloaded_icon_size = 16
        self.downloadedIcon = scaledIcon(data_file_path("thumbnail/downloaded.svg"))
        self.downloadedWarningIcon = scaledIcon(
            data_file_path("thumbnail/downloaded-with-warning.svg")
        )
        self.downloadedErrorIcon = scaledIcon(
            data_file_path("thumbnail/downloaded-with-error.svg")
        )
        self.downloaded_icon_y = self.vAlignHeaderPixmap(0, self.downloaded_icon_size)

        palette = QGuiApplication.instance().palette()
        color = palette.highlight().color()
        self.progressBarPen = QPen(QBrush(color), 2.0)

    def paintHeader(
        self,
        painter: QPainter,
        x: int,
        y: int,
        width: int,
        display_name: str,
        icon: QPixmap,
        device_state: DeviceState,
        rotation: int,
        checked: bool,
        download_statuses: set[DownloadStatus],
        percent_complete: float,
    ) -> None:
        standard_pen_color = painter.pen().color()

        super().paintHeader(
            painter=painter, x=x, y=y, width=width, display_name=display_name, icon=icon
        )

        if device_state == DeviceState.finished:
            # indicate that no more files can be downloaded from the device, and if
            # there were any errors or warnings
            size = QSize(self.downloaded_icon_size, self.downloaded_icon_size)
            if download_statuses & DownloadFailure:
                pixmap = self.downloadedErrorIcon.pixmap(size)
            elif download_statuses & DownloadWarning:
                pixmap = self.downloadedWarningIcon.pixmap(size)
            else:
                pixmap = self.downloadedIcon.pixmap(size)
            painter.drawPixmap(
                QPointF(x + self.dc.padding, y + self.downloaded_icon_y), pixmap
            )

        elif device_state not in (DeviceState.scanning, DeviceState.downloading):
            checkboxStyleOption = QStyleOptionButton()
            if checked == Qt.Checked:
                checkboxStyleOption.state |= QStyle.State_On
            elif checked == Qt.PartiallyChecked:
                checkboxStyleOption.state |= QStyle.State_NoChange
            else:
                checkboxStyleOption.state |= QStyle.State_Off
            checkboxStyleOption.state |= QStyle.State_Enabled

            checkboxStyleOption.rect = self.getCheckBoxRect(x, y)

            QApplication.style().drawControl(
                QStyle.CE_CheckBox, checkboxStyleOption, painter
            )

        else:
            x = x + self.dc.padding
            y = y + self.dc.padding
            # Draw spinning widget
            # TODO use floating point
            painter.setPen(Qt.NoPen)
            for i in range(0, number_spinner_lines):
                painter.save()
                painter.translate(
                    x + self.spinner_inner_radius + self.spinner_line_length,
                    y + 1 + self.spinner_inner_radius + self.spinner_line_length,
                )
                rotateAngle = float(360 * i) / float(number_spinner_lines)
                painter.rotate(rotateAngle)
                painter.translate(self.spinner_inner_radius, 0)
                distance = self.lineCountDistanceFromPrimary(i, rotation)
                color = self.currentLineColor(distance)
                painter.setBrush(color)
                rect = QRectF(
                    0,
                    -self.spinner_line_width / 2,
                    self.spinner_line_length,
                    self.spinner_line_width,
                )
                painter.drawRoundedRect(
                    rect,
                    self.spinner_roundness,
                    self.spinner_roundness,
                    Qt.RelativeSize,
                )
                painter.restore()

            if percent_complete:
                painter.setPen(self.progressBarPen)
                x1 = x - self.dc.padding
                y = y - self.dc.padding + self.dc.device_name_strip_height - 1
                x2 = x1 + percent_complete * width
                painter.drawLine(QPointF(x1, y), QPointF(x2, y))

            painter.setPen(Qt.SolidLine)
            painter.setPen(standard_pen_color)

    def paintAlternate(self, painter: QPainter, x: int, y: int, text: str) -> None:
        standard_pen_color = painter.pen().color()

        painter.setPen(standard_pen_color)
        painter.setFont(self.dc.deviceFont)
        probing_y = y + self.dc.deviceFontMetrics.height()
        probing_x = x + self.dc.padding
        painter.drawText(probing_x, probing_y, text)

    def lineCountDistanceFromPrimary(self, current, primary):
        distance = primary - current
        if distance < 0:
            distance += number_spinner_lines
        return distance

    def currentLineColor(self, countDistance: int) -> QColor:
        color = QColor(self.spinner_color)
        if countDistance == 0:
            return color
        minAlphaF = self.spinner_min_trail_opacity / 100.0
        distanceThreshold = int(
            math.ceil(
                (number_spinner_lines - 1) * self.spinner_trail_fade_percent / 100.0
            )
        )
        if countDistance > distanceThreshold:
            color.setAlphaF(minAlphaF)
        else:
            alphaDiff = color.alphaF() - minAlphaF
            gradient = alphaDiff / float(distanceThreshold + 1)
            resultAlpha = color.alphaF() - gradient * countDistance
            # If alpha is out of bounds, clip it.
            resultAlpha = min(1.0, max(0.0, resultAlpha))
            color.setAlphaF(resultAlpha)
        return color

    def getLeftPoint(self, x: int, y: int) -> QPoint:
        return QPoint(x + self.dc.padding, y + self.checkbox_y_offset)

    def getCheckBoxRect(self, x: int, y: int) -> QRect:
        return QRect(self.getLeftPoint(x, y), self.checkboxRect.size())


class DeviceDelegate(QStyledItemDelegate):
    padding = DeviceDisplayPadding

    probing_text = _("Probing device...")

    shading_intensity = DeviceShadingIntensity

    widthChanged = pyqtSignal(int)

    def __init__(self, rapidApp, parent=None) -> None:
        super().__init__(parent)
        self.rapidApp = rapidApp

        self.deviceDisplay = AdvancedDeviceDisplay(parent=self)
        self.deviceDisplay.widthChanged.connect(self.widthChanged)

        self.contextMenu = QMenu()
        self.ignoreDeviceAct = self.contextMenu.addAction(
            _("Temporarily ignore this device")
        )
        self.ignoreDeviceAct.triggered.connect(self.ignoreDevice)
        self.blacklistDeviceAct = self.contextMenu.addAction(
            _("Permanently ignore this device")
        )
        self.blacklistDeviceAct.triggered.connect(self.blacklistDevice)
        self.rescanDeviceAct = self.contextMenu.addAction(_("Rescan"))
        self.rescanDeviceAct.triggered.connect(self.rescanDevice)
        # store the index in which the user right-clicked
        self.clickedIndex: QModelIndex | None = None

    @pyqtSlot()
    def ignoreDevice(self) -> None:
        index = self.clickedIndex
        if index:
            scan_id: int = index.data(Roles.scan_id)
            self.rapidApp.removeDevice(
                scan_id=scan_id, ignore_in_this_program_instantiation=True
            )
            self.clickedIndex = None

    @pyqtSlot()
    def blacklistDevice(self) -> None:
        index = self.clickedIndex
        if index:
            scan_id: int = index.data(Roles.scan_id)
            self.rapidApp.blacklistDevice(scan_id=scan_id)
            self.clickedIndex = None

    @pyqtSlot()
    def rescanDevice(self) -> None:
        index = self.clickedIndex
        if index:
            scan_id: int = index.data(Roles.scan_id)
            self.rapidApp.rescanDevice(scan_id=scan_id)
            self.clickedIndex = None

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        painter.save()

        x = option.rect.x()
        y = option.rect.y()
        width = option.rect.width()

        view_type: ViewRowType = index.data(Qt.DisplayRole)
        if view_type == ViewRowType.header:
            display_name, icon, device_state, rotation, percent_complete = index.data(
                Roles.device_details
            )
            if device_state == DeviceState.finished:
                download_statuses: set[DownloadStatus] = index.data(
                    Roles.download_statuses
                )
            else:
                download_statuses = set()

            if device_state not in (DeviceState.scanning, DeviceState.downloading):
                checked = index.model().data(index, Qt.CheckStateRole)
            else:
                checked = None

            self.deviceDisplay.paintHeader(
                painter=painter,
                x=x,
                y=y,
                width=width,
                rotation=rotation,
                icon=icon,
                device_state=device_state,
                display_name=display_name,
                checked=checked,
                download_statuses=download_statuses,
                percent_complete=percent_complete,
            )
            device_status = index.data(Roles.device_status)
            if device_status is not None:
                y_warning = (
                    y
                    - self.deviceDisplay.dc.padding
                    + self.deviceDisplay.dc.device_name_height
                )
                if device_status != DeviceDisplayStatus.valid:
                    self.deviceDisplay.paintWarning(
                        painter=painter,
                        x=x,
                        y=y_warning,
                        width=width,
                        text=DIR_PROBLEM_TEXT[device_status],
                    )

        else:
            assert view_type == ViewRowType.content

            device: Device
            storage_space: StorageSpace
            device, storage_space = index.data(Roles.storage)

            if storage_space is not None:
                details = usage_details(device, storage_space)
                self.deviceDisplay.paintBody(
                    painter=painter, x=x, y=y, width=width, details=details
                )

            else:
                assert len(device.storage_space) == 0
                # Storage space not available, which for cameras means libgphoto2 is
                # currently still trying to access the device
                if device.device_type == DeviceType.camera:
                    self.deviceDisplay.paintAlternate(
                        painter=painter, x=x, y=y, text=self.probing_text
                    )

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        view_type: ViewRowType = index.data(Qt.DisplayRole)
        if view_type == ViewRowType.header:
            height = self.deviceDisplay.dc.device_name_height
            device_status = index.data(Roles.device_status)
            if device_status is not None and device_status != DeviceDisplayStatus.valid:
                height += self.deviceDisplay.dc.warning_status_height
        else:
            device, storage_space = index.data(Roles.storage)

            if storage_space is None:
                height = self.deviceDisplay.dc.base_height
            else:
                height = self.deviceDisplay.dc.storage_height
        return QSize(self.deviceDisplay.view_width, height)

    def editorEvent(
        self,
        event: QEvent,
        model: QAbstractItemModel,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> bool:
        """
        Change the data in the model and the state of the checkbox
        if the user presses the left mousebutton or presses
        Key_Space or Key_Select and this cell is editable. Otherwise, do nothing.
        """

        if (
            event.type() == QEvent.MouseButtonRelease
            or event.type() == QEvent.MouseButtonDblClick
        ):
            if event.button() == Qt.RightButton:
                # Disable ignore and blacklist menus if the device is a "This Computer"
                # path

                self.clickedIndex = index

                scan_id = index.data(Roles.scan_id)
                device_type = index.data(Roles.device_type)
                downloading = self.rapidApp.devices.downloading

                self.ignoreDeviceAct.setEnabled(
                    device_type != DeviceType.path and scan_id not in downloading
                )
                self.blacklistDeviceAct.setEnabled(
                    device_type != DeviceType.path and scan_id not in downloading
                )
                self.rescanDeviceAct.setEnabled(scan_id not in downloading)

                view = self.rapidApp.mapView(scan_id)
                globalPos = view.viewport().mapToGlobal(event.pos())
                self.contextMenu.popup(globalPos)
                return False
            if (
                event.button() != Qt.LeftButton
                or not self.deviceDisplay.getCheckBoxRect(
                    option.rect.x(), option.rect.y()
                ).contains(event.pos())
            ):
                return False
            if event.type() == QEvent.MouseButtonDblClick:
                return True
        elif event.type() == QEvent.KeyPress:
            if event.key() != Qt.Key_Space and event.key() != Qt.Key_Select:
                return False
        else:
            return False

        # Change the checkbox-state
        self.setModelData(None, model, index)
        return True

    def setModelData(
        self, editor: QWidget | None, model: QAbstractItemModel, index: QModelIndex
    ) -> None:
        newValue = not (index.model().data(index, Qt.CheckStateRole))
        model.setData(index, newValue, Qt.CheckStateRole)
