# Copyright (C) 2016-2018 Damon Lynch <damonlynch@gmail.com>

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
Display file renaming preferences, including sequence numbers
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2016-2018, Damon Lynch"

from typing import Optional, Dict, Tuple, Union
import logging
from gettext import gettext as _


from PyQt5.QtCore import Qt, pyqtSlot, QTime
from PyQt5.QtWidgets import (
    QWidget, QSizePolicy, QComboBox, QFormLayout, QVBoxLayout, QLabel, QSpinBox, QTimeEdit,
    QCheckBox, QGroupBox, QScrollArea, QFrame
)
from PyQt5.QtGui import (QColor, QPalette)


from raphodo.constants import (
    PresetPrefType, NameGenerationType, ThumbnailBackgroundName, PresetClass, FileType
)
from raphodo.utilities import platform_c_maxint
from raphodo.rpdfile import Photo, Video
from raphodo.nameeditor import PrefDialog, make_sample_rpd_file, PresetComboBox
import raphodo.exiftool as exiftool
import raphodo.generatename as gn
from raphodo.generatenameconfig import *
from raphodo.viewutils import QFramedWidget
from raphodo.panelview import QPanelView
from raphodo.preferences import Preferences, DownloadsTodayTracker


class RenameWidget(QFramedWidget):
    """
    Display combo boxes for file renaming and file extension case handling, and
    an example file name
    """

    def __init__(self, preset_type: PresetPrefType,
                 prefs: Preferences,
                 exiftool_process: exiftool.ExifTool,
                 parent) -> None:
        super().__init__(parent)
        self.setBackgroundRole(QPalette.Base)
        self.setAutoFillBackground(True)
        self.exiftool_process = exiftool_process
        self.prefs = prefs
        self.preset_type = preset_type
        if preset_type == PresetPrefType.preset_photo_rename:
            self.file_type = FileType.photo
            self.pref_defn = DICT_IMAGE_RENAME_L0
            self.generation_type = NameGenerationType.photo_name
            self.index_lookup = self.prefs.photo_rename_index
            self.pref_conv = PHOTO_RENAME_MENU_DEFAULTS_CONV
            self.generation_type = NameGenerationType.photo_name
        else:
            self.file_type = FileType.video
            self.pref_defn = DICT_VIDEO_RENAME_L0
            self.generation_type = NameGenerationType.video_name
            self.index_lookup = self.prefs.video_rename_index
            self.pref_conv = VIDEO_RENAME_MENU_DEFAULTS_CONV
            self.generation_type = NameGenerationType.video_name

        self.sample_rpd_file = make_sample_rpd_file(
            sample_job_code=self.prefs.most_recent_job_code(missing=_('Job Code')),
            prefs=self.prefs, generation_type=self.generation_type
        )

        layout = QFormLayout()
        self.setLayout(layout)

        self.getCustomPresets()

        self.renameCombo = PresetComboBox(
            prefs=self.prefs, preset_names=self.preset_names, preset_type=preset_type,
            parent=self, edit_mode=False
        )
        self.setRenameComboIndex()
        self.renameCombo.activated.connect(self.renameComboItemActivated)

        # File extensions
        self.extensionCombo = QComboBox()
        self.extensionCombo.addItem(_(ORIGINAL_CASE), ORIGINAL_CASE)
        self.extensionCombo.addItem(_(UPPERCASE), UPPERCASE)
        self.extensionCombo.addItem(_(LOWERCASE), LOWERCASE)
        if preset_type == PresetPrefType.preset_photo_rename:
            pref_value =  self.prefs.photo_extension
        else:
            pref_value = self.prefs.video_extension
        try:
            index = [ORIGINAL_CASE, UPPERCASE, LOWERCASE].index(pref_value)
        except ValueError:
            if preset_type == PresetPrefType.preset_photo_rename:
                t = 'Photo'
            else:
                t = 'Video'
            logging.error('%s extension case value is invalid. Resetting to lower case.', t)
            index = 2
        self.extensionCombo.setCurrentIndex(index)
        self.extensionCombo.currentIndexChanged.connect(self.extensionChanged)

        self.example = QLabel()
        self.updateExampleFilename()

        layout.addRow(_('Preset:'), self.renameCombo)
        layout.addRow(_('Extension:'), self.extensionCombo)
        layout.addRow(_('Example:'), self.example)

        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)

    def setRenameComboIndex(self) -> None:
        """
        Set the value being displayed in the combobox to reflect the
        current renaming preference.

        Takes into account built-in renaming presets and custom presets.
        """

        index = self.index_lookup(self.preset_pref_lists)
        if index == -1:
            # Set to the "Custom..." value
            cb_index = self.renameCombo.count() - 1
        else:
            # Set to appropriate combobox idex, allowing for possible separator
            cb_index = self.renameCombo.getComboBoxIndex(index)
        logging.debug(
            "Setting %s combobox chosen value to %s", self.file_type.name,
            self.renameCombo.itemText(cb_index)
        )
        self.renameCombo.setCurrentIndex(cb_index)

    def pref_list(self) -> List[str]:
        """
        :return: the user's file naming preference according to whether
         this widget is handling photos or videos
        """
        if self.preset_type == PresetPrefType.preset_photo_rename:
            return self.prefs.photo_rename
        else:
            return self.prefs.video_rename

    @pyqtSlot(int)
    def renameComboItemActivated(self, index: int) -> None:
        """
        Respond to user activating the Rename preset combo box.

        :param index: index of the item activated
        """

        user_pref_list = None

        preset_class =  self.renameCombo.currentData()
        if preset_class == PresetClass.start_editor:

            prefDialog = PrefDialog(
                self.pref_defn, self.pref_list(), self.generation_type, self.prefs,
                self.sample_rpd_file
            )

            if prefDialog.exec():
                user_pref_list = prefDialog.getPrefList()
                if not user_pref_list:
                    user_pref_list = None

            # Regardless of whether the user clicked OK or cancel, refresh the rename combo
            # box entries
            self.getCustomPresets()
            self.renameCombo.resetEntries(self.preset_names)
            self.setUserPrefList(user_pref_list=user_pref_list)
            self.setRenameComboIndex()
        else:
            assert preset_class == PresetClass.custom or preset_class == PresetClass.builtin
            index = self.renameCombo.getPresetIndex(self.renameCombo.currentIndex())
            user_pref_list = self.combined_pref_lists[index]
            self.setUserPrefList(user_pref_list=user_pref_list)

        self.updateExampleFilename()

    def getCustomPresets(self) -> None:
        """
        Get the custom presets from the user preferences and store them in lists
        """

        self.preset_names, self.preset_pref_lists = self.prefs.get_preset(
            preset_type=self.preset_type)
        self.combined_pref_lists = self.pref_conv + tuple(self.preset_pref_lists)

    def setUserPrefList(self, user_pref_list: List[str]) -> None:
        """
        Update the user preferences with a new preference value
        :param user_pref_list: the photo or video rename preference list
        """

        if user_pref_list is not None:
            logging.debug("Setting new %s rename preference value", self.file_type.name)
            if self.preset_type == PresetPrefType.preset_photo_rename:
                self.prefs.photo_rename = user_pref_list
            else:
                self.prefs.video_rename = user_pref_list

    def updateExampleFilename(self, downloads_today: Optional[List[str]]=None,
                              stored_sequence_no: Optional[int]=None) -> None:
        """
        Update filename shown to user that serves as an example of the
        renaming rule in practice on sample data.

        :param downloads_today: if specified, update the downloads today value
        :param stored_sequence_no: if specified, update the stored sequence value
        """

        if downloads_today:
            self.sample_rpd_file.sequences.downloads_today_tracker.downloads_today = downloads_today
        if stored_sequence_no is not None:
            self.sample_rpd_file.sequences.stored_sequence_no = stored_sequence_no

        if self.preset_type == PresetPrefType.preset_photo_rename:
            self.name_generator = gn.PhotoName(self.prefs.photo_rename)
            logging.debug("Updating example photo name in rename panel")
        else:
            self.name_generator = gn.VideoName(self.prefs.video_rename)
            logging.debug("Updating example video name in rename panel")

        self.example.setText(self.name_generator.generate_name(self.sample_rpd_file))

    def updateSampleFile(self, sample_rpd_file: Union[Photo, Video]) -> None:
        self.sample_rpd_file = make_sample_rpd_file(
            sample_rpd_file=sample_rpd_file,
            sample_job_code=self.prefs.most_recent_job_code(missing=_('Job Code')),
            prefs=self.prefs,
            generation_type=self.generation_type
        )
        self.updateExampleFilename()

    @pyqtSlot(int)
    def extensionChanged(self, index: int) -> None:
        """
        Respond to user changing the case of file extensions in file name generation.

        Save new preference value, and update example file name.
        """

        value = self.extensionCombo.currentData()
        if self.preset_type == PresetPrefType.preset_photo_rename:
            self.prefs.photo_extension = value
        else:
            self.prefs.video_extension = value
        self.sample_rpd_file.generate_extension_case = value
        self.updateExampleFilename()


class RenameOptionsWidget(QFramedWidget):
    """
    Display and allow editing of preference values for Downloads today
    and Stored Sequence Number and associated options, as well as
    the strip incompatible characters option.
    """

    def __init__(self, prefs: Preferences,
                 photoRenameWidget: RenameWidget,
                 videoRenameWidget: RenameWidget,
                 parent) -> None:
        super().__init__(parent)

        self.prefs = prefs
        self.photoRenameWidget = photoRenameWidget
        self.videoRenameWidget = videoRenameWidget

        self.setBackgroundRole(QPalette.Base)
        self.setAutoFillBackground(True)

        compatibilityLayout = QVBoxLayout()
        layout = QVBoxLayout()
        self.setLayout(layout)

        # QSpinBox cannot display values greater than this value
        self.c_maxint = platform_c_maxint()

        tip = _('A counter for how many downloads occur on each day')
        self.downloadsTodayLabel = QLabel(_('Downloads today:'))
        self.downloadsToday = QSpinBox()
        self.downloadsToday.setMinimum(0)
        # QSpinBox defaults to a maximum of 99
        self.downloadsToday.setMaximum(self.c_maxint)
        self.downloadsToday.setToolTip(tip)

        # This instance of the downloads today tracker is secondary to the
        # instance in the rename files process. That process automatically
        # updates the value and then once a download is complete, the
        # downloads today value here is overwritten.
        self.downloads_today_tracker = DownloadsTodayTracker(
            day_start=self.prefs.day_start,
            downloads_today=self.prefs.downloads_today)

        downloads_today = self.downloads_today_tracker.get_or_reset_downloads_today()
        if self.prefs.downloads_today != self.downloads_today_tracker.downloads_today:
            self.prefs.downloads_today = self.downloads_today_tracker.downloads_today

        self.downloadsToday.setValue(downloads_today)
        self.downloadsToday.valueChanged.connect(self.downloadsTodayChanged)

        tip = _('A counter that is remembered each time the program is run ')
        self.storedNumberLabel = QLabel(_('Stored number:'))
        self.storedNumberLabel.setToolTip(tip)
        self.storedNumber = QSpinBox()
        self.storedNumberLabel.setBuddy(self.storedNumber)
        self.storedNumber.setMinimum(0)
        self.storedNumber.setMaximum(self.c_maxint)
        self.storedNumber.setToolTip(tip)

        self.storedNumber.setValue(self.stored_sequence_no)
        self.storedNumber.valueChanged.connect(self.storedNumberChanged)

        tip = _('The time at which the <i>Downloads today</i> sequence number should be reset')
        self.dayStartLabel = QLabel(_('Day start:'))
        self.dayStartLabel.setToolTip(tip)

        self.dayStart = QTimeEdit()
        self.dayStart.setToolTip(tip)
        self.dayStart.setTime(self.prefs.get_day_start_qtime())
        self.dayStart.timeChanged.connect(self.timeChanged)
        # 24 hour format, if wanted in a future release:
        # self.dayStart.setDisplayFormat('HH:mm:ss')

        self.sync = QCheckBox(_('Synchronize RAW + JPEG'))
        self.sync.setChecked(self.prefs.synchronize_raw_jpg)
        self.sync.stateChanged.connect(self.syncChanged)
        tip = _(
            'Synchronize sequence numbers for matching RAW and JPEG pairs.\n\n'
            'See the online documentation for more details.'
        )
        self.sync.setToolTip(tip)

        self.sequences = QGroupBox(_('Sequence Numbers'))

        sequencesLayout = QFormLayout()

        sequencesLayout.addRow(self.storedNumberLabel, self.storedNumber)
        sequencesLayout.addRow(self.downloadsTodayLabel, self.downloadsToday)
        sequencesLayout.addRow(self.dayStartLabel, self.dayStart)
        sequencesLayout.addRow(self.sync)

        self.sequences.setLayout(sequencesLayout)

        self.stripCharacters  = QCheckBox(_('Strip incompatible characters'))
        self.stripCharacters.setChecked(self.prefs.strip_characters)
        self.stripCharacters.stateChanged.connect(self.stripCharactersChanged)
        self.stripCharacters.setToolTip(
            _(
                'Whether photo, video and folder names should have any characters removed that '
                'are not allowed by other operating systems'
            )
        )
        self.compatibility =  QGroupBox(_('Compatibility'))
        self.compatibility.setLayout(compatibilityLayout)
        compatibilityLayout.addWidget(self.stripCharacters)

        layout.addWidget(self.sequences)
        layout.addWidget(self.compatibility)
        layout.addStretch()
        layout.setSpacing(18)

        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)

    @property
    def stored_sequence_no(self) -> int:
        try:
            stored_value = int(self.prefs.stored_sequence_no) + 1
            assert 0 <= stored_value <= self.c_maxint
        except (ValueError, AssertionError):
            stored_value = 0
            logging.error("Resetting invalid stored sequence number to 0")
            self.prefs.stored_sequence_no = -1
        return stored_value

    @stored_sequence_no.setter
    def stored_sequence_no(self, value: int) -> None:
        logging.debug("Setting stored sequence no to %d", value)
        self.prefs.stored_sequence_no = value - 1

    @pyqtSlot(QTime)
    def timeChanged(self, time: QTime) -> None:
        hour = time.hour()
        minute = time.minute()
        self.prefs.day_start = '{}:{}'.format(hour, minute)
        logging.debug("Setting day start to %s", self.prefs.day_start)
        self.downloads_today_tracker.set_day_start(hour=hour, minute=minute)

    @pyqtSlot(int)
    def downloadsTodayChanged(self, value: int) -> None:
        self.downloads_today_tracker.reset_downloads_today(value=value)
        dt = self.downloads_today_tracker.downloads_today
        logging.debug("Setting downloads today value to %s %s", dt[0], dt[1])
        self.prefs.downloads_today = dt
        if self.prefs.photo_rename_pref_uses_downloads_today():
            self.photoRenameWidget.updateExampleFilename(downloads_today=dt)
        if self.prefs.video_rename_pref_uses_downloads_today():
            self.videoRenameWidget.updateExampleFilename(downloads_today=dt)

    @pyqtSlot(int)
    def storedNumberChanged(self, value: int) -> None:
        self.stored_sequence_no = value
        if self.prefs.photo_rename_pref_uses_stored_sequence_no():
            self.photoRenameWidget.updateExampleFilename(stored_sequence_no=value - 1)
        if self.prefs.video_rename_pref_uses_stored_sequence_no():
            self.videoRenameWidget.updateExampleFilename(stored_sequence_no=value - 1)

    @pyqtSlot(int)
    def syncChanged(self, state: int) -> None:
        sync = state == Qt.Checked
        logging.debug("Setting synchronize RAW + JPEG sequence values to %s", sync)
        self.prefs.synchronize_raw_jpg = sync

    @pyqtSlot(int)
    def stripCharactersChanged(self, state: int) -> None:
        strip = state == Qt.Checked
        logging.debug("Setting strip incompatible characers to %s", strip)
        self.prefs.strip_characters = strip


class RenamePanel(QScrollArea):
    """
    Renaming preferences widget, for photos, videos, and general
    renaming options.
    """

    def __init__(self,  parent) -> None:
        super().__init__(parent)
        if parent is not None:
            self.rapidApp = parent
            self.prefs = self.rapidApp.prefs
        else:
            self.prefs = None

        self.setFrameShape(QFrame.NoFrame)

        self.photoRenamePanel = QPanelView(
            label=_('Photo Renaming'), headerColor=QColor(ThumbnailBackgroundName),
            headerFontColor=QColor(Qt.white)
        )
        self.videoRenamePanel = QPanelView(
            label=_('Video Renaming'), headerColor=QColor(ThumbnailBackgroundName),
            headerFontColor=QColor(Qt.white)
        )
        self.renameOptionsPanel = QPanelView(
            label=_('Renaming Options'), headerColor=QColor(ThumbnailBackgroundName),
            headerFontColor=QColor(Qt.white)
        )
        self.photoRenameWidget = RenameWidget(
            preset_type=PresetPrefType.preset_photo_rename, prefs=self.prefs, parent=self,
            exiftool_process=self.rapidApp.exiftool_process
        )
        self.photoRenamePanel.addWidget(self.photoRenameWidget)
        self.videoRenameWidget = RenameWidget(
            preset_type=PresetPrefType.preset_video_rename, prefs=self.prefs, parent=self,
            exiftool_process=self.rapidApp.exiftool_process
        )
        self.videoRenamePanel.addWidget(self.videoRenameWidget)

        self.renameOptions = RenameOptionsWidget(
            prefs=self.prefs, parent=self, photoRenameWidget=self.photoRenameWidget,
            videoRenameWidget=self.videoRenameWidget
        )
        self.renameOptionsPanel.addWidget(self.renameOptions)

        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        widget.setLayout(layout)
        layout.addWidget(self.photoRenamePanel)
        layout.addWidget(self.videoRenamePanel)
        layout.addWidget(self.renameOptionsPanel)
        self.setWidget(widget)
        self.setWidgetResizable(True)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

    def updateSequences(self, downloads_today: List[str], stored_sequence_no: int) -> None:
        """
        Update the value displayed in the display to reflect any values changed after
        the completion of a download.

        :param downloads_today: new downloads today value
        :param stored_sequence_no: new stored sequence number value
        """

        self.renameOptions.downloadsToday.setValue(int(downloads_today[1]))
        self.renameOptions.downloads_today_tracker.downloads_today = downloads_today
        self.renameOptions.storedNumber.setValue(stored_sequence_no + 1)

    def setSamplePhoto(self, sample_photo: Photo) -> None:
        self.photoRenameWidget.updateSampleFile(sample_rpd_file=sample_photo)

    def setSampleVideo(self, sample_video: Video) -> None:
        self.videoRenameWidget.updateSampleFile(sample_rpd_file=sample_video)



