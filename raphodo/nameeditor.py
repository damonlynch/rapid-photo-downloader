#!/usr/bin/env python3
# Copyright (C) 2016-2021 Damon Lynch <damonlynch@gmail.com>

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
Dialog for editing download subfolder structure and file renaming
"""

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2016-2021, Damon Lynch"

from typing import Dict, Union, Sequence
import webbrowser
import datetime
import copy
import logging


from PyQt5.QtWidgets import (
    QTextEdit,
    QApplication,
    QComboBox,
    QPushButton,
    QLabel,
    QDialog,
    QDialogButtonBox,
    QVBoxLayout,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QScrollArea,
    QWidget,
    QFrame,
    QStyle,
    QSizePolicy,
    QLineEdit,
    QMessageBox,
)
from PyQt5.QtGui import (
    QTextCharFormat,
    QFont,
    QTextCursor,
    QMouseEvent,
    QSyntaxHighlighter,
    QTextDocument,
    QBrush,
    QColor,
    QFontMetrics,
    QKeyEvent,
    QResizeEvent,
    QStandardItem,
    QWheelEvent,
)
from PyQt5.QtCore import Qt, pyqtSlot, QSignalMapper, QSize, pyqtSignal

from sortedcontainers import SortedList

from raphodo.generatenameconfig import *
import raphodo.generatename as gn
from raphodo.constants import (
    CustomColors,
    PrefPosition,
    NameGenerationType,
    PresetPrefType,
    PresetClass,
)
from raphodo.rpdfile import SamplePhoto, SampleVideo, Photo, Video, FileType
from raphodo.prefs.preferences import DownloadsTodayTracker, Preferences, match_pref_list
from raphodo.utilities import remove_last_char_from_list_str
from raphodo.ui.messagewidget import MessageWidget
from raphodo.ui.viewutils import (
    translateDialogBoxButtons,
    standardMessageBox,
    translateMessageBoxButtons,
)


class PrefEditor(QTextEdit):
    """
    File renaming and subfolder generation preference editor
    """

    prefListGenerated = pyqtSignal()

    def __init__(self, subfolder: bool, parent=None) -> None:
        """
        :param subfolder: if True, the editor is for editing subfolder generation
        """

        super().__init__(parent)
        self.subfolder = subfolder

        self.user_pref_list = []  # type: List[str]
        self.user_pref_colors = []  # type: List[str]

        self.heightMin = 0
        self.heightMax = 65000
        # Start out with about 4 lines in height:
        self.setMinimumHeight(QFontMetrics(self.font()).lineSpacing() * 5)
        self.document().documentLayout().documentSizeChanged.connect(
            self.wrapHeightToContents
        )

    def wrapHeightToContents(self) -> None:
        """
        Adjust the text area size to show contents without vertical scrollbar

        Derived from:
        http://stackoverflow.com/questions/11851020/a-qwidget-like-qtextedit-that-wraps-its-height-automatically-to-its-contents/11858803#11858803
        """

        docHeight = self.document().size().height() + 5
        if (
            self.heightMin <= docHeight <= self.heightMax
            and docHeight > self.minimumHeight()
        ):
            self.setMinimumHeight(docHeight)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        Automatically select a pref value if it was clicked in
        :param event:  the mouse event
        """

        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            position = self.textCursor().position()
            pref_pos, start, end, left_start, left_end = self.locatePrefValue(position)

            if pref_pos == PrefPosition.on_left:
                start = left_start
                end = left_end
            if pref_pos != PrefPosition.not_here:
                cursor = self.textCursor()
                cursor.setPosition(start)
                cursor.setPosition(end + 1, QTextCursor.KeepAnchor)
                self.setTextCursor(cursor)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """
        Automatically select pref values when navigating through the document.

        Suppress the return / enter key.

        :param event: the key press event
        """

        key = event.key()
        if key in (Qt.Key_Enter, Qt.Key_Return, Qt.Key_Tab):
            return

        cursor = self.textCursor()  # type: QTextCursor

        if cursor.hasSelection() and key in (Qt.Key_Left, Qt.Key_Right):
            # Pass the key press on and let the selection deselect
            pass
        elif key in (
            Qt.Key_Left,
            Qt.Key_Right,
            Qt.Key_Home,
            Qt.Key_End,
            Qt.Key_PageUp,
            Qt.Key_PageDown,
            Qt.Key_Up,
            Qt.Key_Down,
        ):
            # Navigation key was pressed

            # Was ctrl key pressed too?
            ctrl_key = event.modifiers() & Qt.ControlModifier

            selection_start = selection_end = -1

            # This event is called before the cursor is moved, so
            # move the cursor as if it would be moved
            if key == Qt.Key_Right and not cursor.atEnd():
                if ctrl_key:
                    cursor.movePosition(QTextCursor.WordRight)
                else:
                    cursor.movePosition(QTextCursor.Right)
            elif key == Qt.Key_Left and not cursor.atStart():
                if ctrl_key:
                    cursor.movePosition(QTextCursor.WordLeft)
                else:
                    cursor.movePosition(QTextCursor.Left)
            elif key == Qt.Key_Up:
                cursor.movePosition(QTextCursor.Up)
            elif key == Qt.Key_Down:
                cursor.movePosition(QTextCursor.Down)
            elif key in (Qt.Key_Home, Qt.Key_PageUp):
                if ctrl_key or key == Qt.Key_PageUp:
                    cursor.movePosition(QTextCursor.StartOfBlock)
                else:
                    cursor.movePosition(QTextCursor.StartOfLine)
            elif key in (Qt.Key_End, Qt.Key_PageDown):
                if ctrl_key or key == Qt.Key_PageDown:
                    cursor.movePosition(QTextCursor.EndOfBlock)
                else:
                    cursor.movePosition(QTextCursor.EndOfLine)

            # Get position of where the cursor would move to
            position = cursor.position()

            # Determine if there is a pref value to the left or at that position
            pref_pos, start, end, left_start, left_end = self.locatePrefValue(position)
            if pref_pos == PrefPosition.on_left:
                selection_start = left_start
                selection_end = left_end + 1
            elif pref_pos == PrefPosition.at:
                selection_start = end + 1
                selection_end = start
            elif pref_pos == PrefPosition.positioned_in:
                if key == Qt.Key_Left or key == Qt.Key_Home:
                    # because moving left, position the cursor on the left
                    selection_start = end + 1
                    selection_end = start
                else:
                    # because moving right, position the cursor on the right
                    selection_start = start
                    selection_end = end + 1

            if selection_end >= 0 and selection_start >= 0:
                cursor.setPosition(selection_start)
                cursor.setPosition(selection_end, QTextCursor.KeepAnchor)
                self.setTextCursor(cursor)
                return

        super().keyPressEvent(event)

    def locatePrefValue(self, position: int) -> Tuple[PrefPosition, int, int, int, int]:
        """
        Determine where pref values are relative to the position passed.

        :param position: some position in text, e.g. cursor position
        :return: enum indicating where prefs are found and their start and end
         positions. Return positions are -1 if not found.
        """

        start = end = -1
        left_start = left_end = -1
        pref_position = PrefPosition.not_here
        b = self.highlighter.boundaries
        if not (len(b)):
            return (pref_position, start, end, left_start, left_end)

        index = b.bisect_left((position, 0))
        # Special cases
        if index == 0:
            # At or to the left of the first pref value
            if b[0][0] == position:
                pref_position = PrefPosition.at
                start, end = b[0]
        elif index == len(b):
            # To the right of or in the last pref value
            if position <= b[-1][1]:
                start, end = b[-1]
                pref_position = PrefPosition.positioned_in
            elif b[-1][1] == position - 1:
                left_start, left_end = b[-1]
                pref_position = PrefPosition.on_left
        else:
            left = b[index - 1]
            right = b[index]

            at = right[0] == position
            to_left = left[1] == position - 1
            if at and to_left:
                pref_position = PrefPosition.on_left_and_at
                start, end = right
                left_start, left_end = left
            elif at:
                pref_position = PrefPosition.at
                start, end = right
            elif to_left:
                pref_position = PrefPosition.on_left
                left_start, left_end = left
            elif position <= left[1]:
                pref_position = PrefPosition.positioned_in
                start, end = b[index - 1]

        return (pref_position, start, end, left_start, left_end)

    def displayPrefList(self, pref_list: Sequence[str]) -> None:
        p = pref_list
        values = []
        for i in range(0, len(pref_list), 3):
            try:
                value = "<{}>".format(self.pref_mapper[(p[i], p[i + 1], p[i + 2])])
            except KeyError:
                if p[i] == SEPARATOR:
                    value = SEPARATOR
                else:
                    assert p[i] == TEXT
                    value = p[i + 1]
            values.append(value)

        self.document().clear()
        cursor = self.textCursor()  # type: QTextCursor
        cursor.insertText("".join(values))

    def insertPrefValue(self, pref_value: str) -> None:
        cursor = self.textCursor()  # type: QTextCursor
        cursor.insertText("<{}>".format(pref_value))

    def _setHighlighter(self) -> None:
        self.highlighter = PrefHighlighter(
            list(self.string_to_pref_mapper.keys()), self.pref_color, self.document()
        )

        # when color coding of text in the editor is complete,
        # generate the preference list
        self.highlighter.blockHighlighted.connect(self.generatePrefList)

    def setPrefMapper(
        self, pref_mapper: Dict[Tuple[str, str, str], str], pref_color: Dict[str, str]
    ) -> None:
        self.pref_mapper = pref_mapper
        self.string_to_pref_mapper = {value: key for key, value in pref_mapper.items()}

        self.pref_color = pref_color
        self._setHighlighter()

    def _parseTextFragment(self, text_fragment) -> None:
        if self.subfolder:
            text_fragments = text_fragment.split(os.sep)
            for index, text_fragment in enumerate(text_fragments):
                if text_fragment:
                    self.user_pref_list.extend([TEXT, text_fragment, ""])
                    self.user_pref_colors.append("")
                if index < len(text_fragments) - 1:
                    self.user_pref_list.extend([SEPARATOR, "", ""])
                    self.user_pref_colors.append("")
        else:
            self.user_pref_list.extend([TEXT, text_fragment, ""])
            self.user_pref_colors.append("")

    def _addColor(self, pref_defn: str) -> None:
        self.user_pref_colors.append(self.pref_color[pref_defn])

    @pyqtSlot()
    def generatePrefList(self) -> None:
        """
        After syntax highlighting has completed, use its findings
        to generate the user's pref list
        """

        text = self.document().toPlainText()
        b = self.highlighter.boundaries

        self.user_pref_list = pl = []  # type: List[str]
        self.user_pref_colors = []  # type: List[str]

        # Handle any text at the very beginning
        if b and b[0][0] > 0:
            text_fragment = text[: b[0][0]]
            self._parseTextFragment(text_fragment)

        if len(b) > 1:
            for index, item in enumerate(b[1:]):
                start, end = b[index]
                # Add + 1 to start to remove the opening <
                pl.extend(self.string_to_pref_mapper[text[start + 1 : end]])
                # Add + 1 to start to include the closing >
                self._addColor(text[start : end + 1])

                text_fragment = text[b[index][1] + 1 : item[0]]
                self._parseTextFragment(text_fragment)

        # Handle the final pref value
        if b:
            start, end = b[-1]
            # Add + 1 to start to remove the opening <
            pl.extend(self.string_to_pref_mapper[text[start + 1 : end]])
            # Add + 1 to start to include the closing >
            self._addColor(text[start : end + 1])
            final = end + 1
        else:
            final = 0

        # Handle any remaining text at the very end (or the complete string if there are
        # no pref definition values)
        if final < len(text):
            text_fragment = text[final:]
            self._parseTextFragment(text_fragment)

        assert len(self.user_pref_colors) == len(self.user_pref_list) / 3
        self.prefListGenerated.emit()


class PrefHighlighter(QSyntaxHighlighter):
    """
    Highlight non-text preference values in the editor
    """

    blockHighlighted = pyqtSignal()

    def __init__(
        self,
        pref_defn_strings: List[str],
        pref_color: Dict[str, str],
        document: QTextDocument,
    ) -> None:
        super().__init__(document)

        # Where detected preference values start and end:
        # [(start, end), (start, end), ...]
        self.boundaries = SortedList()

        pref_defns = ("<{}>".format(pref) for pref in pref_defn_strings)
        self.highlightingRules = []
        for pref in pref_defns:
            format = QTextCharFormat()
            format.setForeground(QBrush(QColor(pref_color[pref])))
            self.highlightingRules.append((pref, format))

    def find_all(self, text: str, pref_defn: str):
        """
        Find all occurrences of a preference definition in the text
        :param text: text to search
        :param pref_defn: the preference definition
        :return: yield the position in the document's text
        """
        if not len(pref_defn):
            return  # do not use raise StopIteration as it is Python 3.7 incompatible
        start = 0
        while True:
            start = text.find(pref_defn, start)
            if start == -1:
                # do not use raise StopIteration as it is Python 3.7 incompatible
                return
            yield start
            start += len(pref_defn)

    def highlightBlock(self, text: str) -> None:

        # Recreate the preference value from scratch
        self.boundaries = SortedList()

        for expression, format in self.highlightingRules:
            for index in self.find_all(text, expression):
                length = len(expression)
                self.setFormat(index, length, format)
                self.boundaries.add((index, index + length - 1))

        self.blockHighlighted.emit()


def make_subfolder_menu_entry(prefs: Tuple[str]) -> str:
    """
    Create the text for a menu / combobox item

    :param prefs: single pref item, with title and elements
    :return: item text
    """

    desc = prefs[0]
    elements = prefs[1:]
    # Translators: this text appears in menus and combo boxes. It displays the
    # description of an item, and its elements.
    # Translators: %(variable)s represents Python code, not a plural of the term
    # variable. You must keep the %(variable)s untranslated, or the program will
    # crash.
    return _("%(description)s - %(elements)s") % dict(
        description=desc, elements=os.sep.join(elements)
    )


def make_rename_menu_entry(prefs: Tuple[str]) -> str:
    """
    Create the text for a menu / combobox item

    :param prefs: single pref item, with title and elements
    :return: item text
    """

    desc = prefs[0]
    elements = prefs[1]
    # Translators: this text appears in menus and combo boxes. It displays the
    # description of an item, and its elements.
    # Translators: %(variable)s represents Python code, not a plural of the term
    # variable. You must keep the %(variable)s untranslated, or the program will
    # crash.
    return _("%(description)s - %(elements)s") % dict(
        description=desc, elements=elements
    )


class PresetComboBox(QComboBox):
    """
    Combox box displaying built-in presets, custom presets,
    and some commands relating to preset management.

    Used in in dialog window used to edit name generation and
    also in the rename files panel.
    """

    def __init__(
        self,
        prefs: Preferences,
        preset_names: List[str],
        preset_type: PresetPrefType,
        edit_mode: bool,
        parent=None,
    ) -> None:
        """
        :param prefs: program preferences
        :param preset_names: list of custom preset names
        :param preset_type: one of photo rename, video rename,
         photo subfolder, or video subfolder
        :param edit_mode: if True, the combo box is being displayed
         in an edit dialog window, else it's being displayed in the
         file rename panel
        :param parent: parent widget
        """

        super().__init__(parent)
        self.edit_mode = edit_mode
        self.prefs = prefs

        self.preset_edited = False
        self.new_preset = False

        self.preset_type = preset_type

        if preset_type == PresetPrefType.preset_photo_subfolder:
            self.builtin_presets = PHOTO_SUBFOLDER_MENU_DEFAULTS
        elif preset_type == PresetPrefType.preset_video_subfolder:
            self.builtin_presets = VIDEO_SUBFOLDER_MENU_DEFAULTS
        elif preset_type == PresetPrefType.preset_photo_rename:
            self.builtin_presets = PHOTO_RENAME_MENU_DEFAULTS
        else:
            assert preset_type == PresetPrefType.preset_video_rename
            self.builtin_presets = VIDEO_RENAME_MENU_DEFAULTS

        self._setup_entries(preset_names)

    def _setup_entries(self, preset_names: List[str]) -> None:

        idx = 0

        if self.edit_mode:
            for pref in self.builtin_presets:
                self.addItem(make_subfolder_menu_entry(pref), PresetClass.builtin)
                idx += 1
        else:
            for pref in self.builtin_presets:
                self.addItem(pref[0], PresetClass.builtin)
                idx += 1

        if not len(preset_names):
            # preset_separator bool is used to indicate the existence of
            # a separator in the combo box that is used to distinguish
            # custom from built-in prests
            self.preset_separator = False
        else:
            self.preset_separator = True

            self.insertSeparator(idx)
            idx += 1

            for name in preset_names:
                self.addItem(name, PresetClass.custom)
                idx += 1

        self.insertSeparator(idx)

        if self.edit_mode:
            self.addItem(_("Save New Custom Preset..."), PresetClass.new_preset)
            self.addItem(_("Remove All Custom Presets..."), PresetClass.remove_all)
            self.setRemoveAllCustomEnabled(bool(len(preset_names)))
        else:
            self.addItem(_("Custom..."), PresetClass.start_editor)

    def resetEntries(self, preset_names: List[str]) -> None:
        assert not self.edit_mode
        self.clear()
        self._setup_entries(preset_names)

    def addCustomPreset(self, text: str) -> None:
        """
        Adds a new custom preset name to the comboxbox and sets the
        combobox to display it.

        :param text: the custom preset name
        """

        assert self.edit_mode
        if self.new_preset or self.preset_edited:
            self.resetPresetList()
        if not self.preset_separator:
            self.insertSeparator(len(self.builtin_presets))
            self.preset_separator = True
        idx = len(self.builtin_presets) + 1
        self.insertItem(idx, text, PresetClass.custom)
        self.setCurrentIndex(idx)

    def removeAllCustomPresets(self, no_presets: int) -> None:
        assert self.edit_mode
        assert self.preset_separator
        start = len(self.builtin_presets)
        if self.new_preset:
            start += 2
        elif self.preset_edited:
            self.resetPresetList()
        end = start + no_presets
        for row in range(end, start - 1, -1):
            self.removeItem(row)
        self.preset_separator = False

    def setPresetNew(self) -> None:
        assert self.edit_mode
        assert not self.preset_edited
        if self.new_preset:
            return
        item_text = _("(New Custom Preset)")
        self.new_preset = True
        self.insertItem(0, item_text, PresetClass.edited)
        self.insertSeparator(1)
        self.setCurrentIndex(0)

    def setPresetEdited(self, text: str) -> None:
        """
        Adds a new entry at the top of the combobox indicating that the current
        preset has been edited.

        :param text: the preset name to use
        """

        assert self.edit_mode
        assert not self.new_preset
        assert not self.preset_edited
        item_text = _("%s (edited)") % text
        self.insertItem(0, item_text, PresetClass.edited)
        self.insertSeparator(1)
        self.addItem(_('Update Custom Preset "%s"') % text, PresetClass.update_preset)
        self.preset_edited = True
        self.setCurrentIndex(0)

    def resetPresetList(self) -> None:
        """
        Removes the combo box first line 'Preset name (edited)' or '(New Custom Preset)',
        and its separator
        """

        assert self.edit_mode
        assert self.new_preset or self.preset_edited
        # remove combo box first line 'Preset name (edited)' or '(New Custom Preset)'
        self.removeItem(0)
        # remove separator
        self.removeItem(0)
        # remove Update Preset
        if self.preset_edited:
            index = self.count() - 1
            self.removeItem(index)
        self.preset_edited = self.new_preset = False

    def _setRowEnabled(self, enabled: bool, offset: int) -> None:
        assert self.edit_mode
        # Our big assumption here is that the model is a QStandardItemModel
        model = self.model()
        count = self.count()
        if self.preset_edited:
            row = count - offset - 1
        else:
            row = count - offset
        item = model.item(row, 0)  # type: QStandardItem
        if not enabled:
            item.setFlags(Qt.NoItemFlags)
        else:
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

    def setRemoveAllCustomEnabled(self, enabled: bool) -> None:
        self._setRowEnabled(enabled=enabled, offset=1)

    def setSaveNewCustomPresetEnabled(self, enabled: bool) -> None:
        self._setRowEnabled(enabled=enabled, offset=2)

    def getComboBoxIndex(self, preset_index: int) -> int:
        """
        Calculate the index into the combo box list allowing for the separator
        and other elements in the list of entries the user sees

        :param preset_index: the preset index (built-in & custom)
        :return: the index into the actual combobox entries including
         any separators etc.
        """

        if self.edit_mode and (self.new_preset or self.preset_edited):
            preset_index += 2
        if preset_index < len(self.builtin_presets):
            return preset_index
        else:
            assert self.preset_separator
            return preset_index + 1

    def getPresetIndex(self, combobox_index: int) -> int:
        """
        Opposite of getComboBoxIndex: calculates the preset index based on the
        given combo box index (which includes separators etc.)
        :param combobox_index: the index into the combobox entries the user sees
        :return: the index into the presets (built-in & custom)
        """

        if self.edit_mode and (self.new_preset or self.preset_edited):
            combobox_index -= 2
        if combobox_index < len(self.builtin_presets):
            return combobox_index
        else:
            assert self.preset_separator
            return combobox_index - 1


class CreatePreset(QDialog):
    """
    Very simple dialog window that allows user entry of new preset name.

    Save button is disabled when the current name entered equals an existing
    preset name or is empty.
    """

    def __init__(self, existing_custom_names: List[str], parent=None) -> None:
        super().__init__(parent)

        self.existing_custom_names = existing_custom_names

        self.setModal(True)

        title = _("Save New Custom Preset - Rapid Photo Downloader")
        self.setWindowTitle(title)

        self.name = QLineEdit()
        metrics = QFontMetrics(QFont())
        self.name.setMinimumWidth(metrics.width(title))
        self.name.textEdited.connect(self.nameEdited)
        flayout = QFormLayout()
        flayout.addRow(_("Preset Name:"), self.name)

        buttonBox = QDialogButtonBox()
        buttonBox.addButton(QDialogButtonBox.Cancel)  # type: QPushButton
        self.saveButton = buttonBox.addButton(
            QDialogButtonBox.Save
        )  # type: QPushButton
        self.saveButton.setEnabled(False)
        translateDialogBoxButtons(buttonBox)
        buttonBox.rejected.connect(self.reject)
        buttonBox.accepted.connect(self.accept)

        layout = QVBoxLayout()
        layout.addLayout(flayout)
        layout.addWidget(buttonBox)

        self.setLayout(layout)

    @pyqtSlot(str)
    def nameEdited(self, name: str):
        enabled = False
        if len(name) > 0:
            enabled = name not in self.existing_custom_names
        self.saveButton.setEnabled(enabled)

    def presetName(self) -> str:
        """
        :return: the name of the name the user wants to save the preset as
        """

        return self.name.text()


def make_sample_rpd_file(
    sample_job_code: str,
    prefs: Preferences,
    generation_type: NameGenerationType,
    sample_rpd_file: Optional[Union[Photo, Video]] = None,
) -> Union[Photo, Video]:
    """
    Create a sample_rpd_file used for displaying to the user an example of their
    file renaming preference in action on a sample file.

    :param sample_job_code: sample of a Job Code
    :param prefs: user preferences
    :param generation_type: one of photo/video filenames/subfolders
    :param sample_rpd_file: sample RPDFile that will possibly be overwritten
     with new values
    :return: sample RPDFile
    """

    downloads_today_tracker = DownloadsTodayTracker(
        day_start=prefs.day_start, downloads_today=prefs.downloads_today
    )
    sequences = gn.Sequences(downloads_today_tracker, prefs.stored_sequence_no)
    if sample_rpd_file is not None:
        if sample_rpd_file.metadata is None:
            logging.error(
                "Sample file %s is missing its metadata", sample_rpd_file.full_file_name
            )
            sample_rpd_file = None
        else:
            sample_rpd_file.sequences = sequences
            sample_rpd_file.download_start_time = datetime.datetime.now()

    if sample_rpd_file is None:
        if generation_type in (
            NameGenerationType.photo_name,
            NameGenerationType.photo_subfolder,
        ):
            sample_rpd_file = SamplePhoto(sequences=sequences)
        else:
            sample_rpd_file = SampleVideo(sequences=sequences)

    sample_rpd_file.job_code = sample_job_code
    sample_rpd_file.strip_characters = prefs.strip_characters
    if sample_rpd_file.file_type == FileType.photo:
        sample_rpd_file.generate_extension_case = prefs.photo_extension
    else:
        sample_rpd_file.generate_extension_case = prefs.video_extension

    return sample_rpd_file


class EditorCombobox(QComboBox):
    """
    Regular combobox, but ignores the mouse wheel
    """

    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()


class PrefDialog(QDialog):
    """
    Dialog window to allow editing of file renaming and subfolder generation
    """

    def __init__(
        self,
        pref_defn: OrderedDict,
        user_pref_list: List[str],
        generation_type: NameGenerationType,
        prefs: Preferences,
        sample_rpd_file: Optional[Union[Photo, Video]] = None,
        max_entries=0,
        parent=None,
    ) -> None:
        """
        Set up dialog to display all its controls based on the preference
        definition being used.

        :param pref_defn: definition of possible preference choices, i.e.
         one of DICT_VIDEO_SUBFOLDER_L0, DICT_SUBFOLDER_L0, DICT_VIDEO_RENAME_L0
         or DICT_IMAGE_RENAME_L0
        :param user_pref_list: the user's actual rename / subfolder generation
         preferences
        :param generation_type: enum specifying what kind of name is being edited
         (one of photo filename, video filename, photo subfolder, video subfolder)
        :param prefs: program preferences
        :param exiftool_process: daemon exiftool process
        :param sample_rpd_file: a sample photo or video, whose contents will be
         modified (i.e. don't pass a live RPDFile)
        :param max_entries: maximum number of entries that will be displayed
         to the user (in a menu, for example)
        """

        super().__init__(parent)

        self.setModal(True)

        self.generation_type = generation_type
        if generation_type == NameGenerationType.photo_subfolder:
            self.setWindowTitle(_("Photo Subfolder Generation Editor"))
            self.preset_type = PresetPrefType.preset_photo_subfolder
            self.builtin_pref_lists = PHOTO_SUBFOLDER_MENU_DEFAULTS_CONV
            self.builtin_pref_names = [
                make_subfolder_menu_entry(pref)
                for pref in PHOTO_SUBFOLDER_MENU_DEFAULTS
            ]
        elif generation_type == NameGenerationType.video_subfolder:
            self.setWindowTitle(_("Video Subfolder Generation Editor"))
            self.preset_type = PresetPrefType.preset_video_subfolder
            self.builtin_pref_lists = VIDEO_SUBFOLDER_MENU_DEFAULTS_CONV
            self.builtin_pref_names = [
                make_subfolder_menu_entry(pref)
                for pref in VIDEO_SUBFOLDER_MENU_DEFAULTS
            ]
        elif generation_type == NameGenerationType.photo_name:
            self.setWindowTitle(_("Photo Renaming Editor"))
            self.preset_type = PresetPrefType.preset_photo_rename
            self.builtin_pref_lists = PHOTO_RENAME_MENU_DEFAULTS_CONV
            self.builtin_pref_names = [
                make_rename_menu_entry(pref) for pref in PHOTO_RENAME_MENU_DEFAULTS
            ]
        else:
            self.setWindowTitle(_("Video Renaming Editor"))
            self.preset_type = PresetPrefType.preset_video_rename
            self.builtin_pref_lists = VIDEO_RENAME_MENU_DEFAULTS_CONV
            self.builtin_pref_names = [
                make_rename_menu_entry(pref) for pref in VIDEO_RENAME_MENU_DEFAULTS
            ]

        self.prefs = prefs
        self.max_entries = max_entries

        # Cache custom preset name and pref lists
        self.updateCachedPrefLists()

        self.current_custom_name = None

        # Setup values needed for name generation

        self.sample_rpd_file = make_sample_rpd_file(
            sample_rpd_file=sample_rpd_file,
            sample_job_code=self.prefs.most_recent_job_code(missing=_("Job Code")),
            prefs=self.prefs,
            generation_type=generation_type,
        )

        # Setup widgets and helper values

        # Translators: please do not modify or leave out html formatting tags like <i> and
        # <b>. These are used to format the text the users sees
        warning_msg = _(
            '<b><font color="red">Warning:</font></b> <i>There is insufficient data to '
            'fully generate the name. Please use other renaming options.</i>'
        )

        self.is_subfolder = generation_type in (
            NameGenerationType.photo_subfolder,
            NameGenerationType.video_subfolder,
        )

        if self.is_subfolder:
            # Translators: please do not modify, change the order of or leave out html
            # formatting tags like <i> and <b>. These are used to format the text the
            # users sees. In this case, the </i> really is supposed to come before the
            # <i>.
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            subfolder_msg = _(
                "The character</i> %(separator)s <i>creates a new subfolder level."
            ) % dict(separator=os.sep)
            # Translators: please do not modify, change the order of or leave out html
            # formatting tags like <i> and <b>. These are used to format the text the
            # users sees In this case, the </i> really is supposed to come before the
            # <i>.
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            subfolder_first_char_msg = _(
                "There is no need start or end with the folder separator </i> "
                "%(separator)s<i>, because it is added automatically."
            ) % dict(separator=os.sep)
            messages = (warning_msg, subfolder_msg, subfolder_first_char_msg)
        else:
            # Translators: please do not modify or leave out html formatting tags like
            # <i> and <b>. These are used to format the text the users sees
            unique_msg = _(
                '<b><font color="red">Warning:</font></b> <i>Unique filenames may not '
                'be generated. Make filenames unique by using Sequence values.</i>'
            )
            messages = (warning_msg, unique_msg)

        self.messageWidget = MessageWidget(messages=messages)

        self.editor = PrefEditor(subfolder=self.is_subfolder)
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        sizePolicy.setVerticalStretch(1)
        self.editor.setSizePolicy(sizePolicy)

        self.editor.prefListGenerated.connect(self.updateExampleFilename)

        # Generated subfolder / file name example
        self.example = QLabel()

        # Combobox with built-in and user defined presets
        self.preset = PresetComboBox(
            prefs=prefs,
            preset_names=self.preset_names,
            preset_type=self.preset_type,
            edit_mode=True,
        )
        self.preset.activated.connect(self.presetComboItemActivated)

        glayout = QGridLayout()
        presetLabel = QLabel(_("Preset:"))
        exampleLabel = QLabel(_("Example:"))

        glayout.addWidget(presetLabel, 0, 0)
        glayout.addWidget(self.preset, 0, 1)
        glayout.addWidget(exampleLabel, 1, 0)
        glayout.addWidget(self.example, 1, 1)
        glayout.setColumnStretch(1, 10)

        layout = QVBoxLayout()
        self.setLayout(layout)

        layout.addLayout(glayout)
        layout.addSpacing(int(QFontMetrics(QFont()).height() / 2))
        layout.addWidget(self.editor)
        layout.addWidget(self.messageWidget)

        self.area = QScrollArea()
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        sizePolicy.setVerticalStretch(10)
        self.area.setSizePolicy(sizePolicy)
        self.area.setFrameShape(QFrame.NoFrame)
        layout.addWidget(self.area)

        gbSizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        areaWidget = QWidget()
        areaLayout = QVBoxLayout()
        areaWidget.setLayout(areaLayout)
        areaWidget.setSizePolicy(gbSizePolicy)

        self.area.setWidget(areaWidget)
        self.area.setWidgetResizable(True)

        areaLayout.setContentsMargins(0, 0, 0, 0)

        self.pushButtonSizePolicy = QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.mapper = QSignalMapper(self)
        self.widget_mapper = dict()  # type: Dict[str, Union[QComboBox, QLabel]]
        self.pref_mapper = dict()  # type: Dict[Tuple[str, str, str], str]
        self.pref_color = dict()  # type: Dict[str, str]

        titles = [title for title in pref_defn if title not in (TEXT, SEPARATOR)]
        pref_colors = {title: color.value for title, color in zip(titles, CustomColors)}
        self.filename_pref_color = pref_colors[FILENAME]

        for title in titles:
            title_i18n = _(title)
            color = pref_colors[title]
            level1 = pref_defn[title]
            gb = QGroupBox(title_i18n)
            gb.setSizePolicy(gbSizePolicy)
            gb.setFlat(True)
            areaLayout.addWidget(gb)
            gLayout = QGridLayout()
            gb.setLayout(gLayout)
            if level1 is None:
                assert title == JOB_CODE
                widget1 = QLabel(" " + title_i18n)
                widget2 = self.makeInsertButton()
                self.widget_mapper[title] = widget1
                self.mapper.setMapping(widget2, title)
                self.pref_mapper[(title, "", "")] = title_i18n
                self.pref_color["<{}>".format(title_i18n)] = color
                gLayout.addWidget(self.makeColorCodeLabel(color), 0, 0)
                gLayout.addWidget(widget1, 0, 1)
                gLayout.addWidget(widget2, 0, 2)
            elif title == METADATA:
                elements = []
                data = []
                for element in level1:
                    element_i18n = _(element)
                    level2 = level1[element]
                    if level2 is None:
                        elements.append(element_i18n)
                        data.append([METADATA, element, ""])
                        self.pref_mapper[(METADATA, element, "")] = element_i18n
                        self.pref_color["<{}>".format(element_i18n)] = color
                    else:
                        for e in level2:
                            e_i18n = _(e)
                            # Translators: appears in a combobox, e.g. Image Date (YYYY)
                            item = _("{choice} ({variant})").format(
                                choice=element_i18n, variant=e_i18n
                            )
                            elements.append(item)
                            data.append([METADATA, element, e])
                            self.pref_mapper[(METADATA, element, e)] = item
                            self.pref_color["<{}>".format(item)] = color
                widget1 = EditorCombobox()
                for element, data_item in zip(elements, data):
                    widget1.addItem(element, data_item)
                widget2 = self.makeInsertButton()
                widget1.currentTextChanged.connect(self.mapper.map)
                self.mapper.setMapping(widget2, title)
                self.mapper.setMapping(widget1, title)
                self.widget_mapper[title] = widget1
                gLayout.addWidget(self.makeColorCodeLabel(color), 0, 0)
                gLayout.addWidget(widget1, 0, 1)
                gLayout.addWidget(widget2, 0, 2)
            else:
                for row, level1 in enumerate(pref_defn[title]):
                    widget1 = EditorCombobox()
                    level1_i18n = _(level1)
                    items = (
                        _("{choice} ({variant})").format(
                            choice=level1_i18n, variant=_(element)
                        )
                        for element in pref_defn[title][level1]
                    )
                    data = (
                        [title, level1, element] for element in pref_defn[title][level1]
                    )
                    for item, data_item in zip(items, data):
                        widget1.addItem(item, data_item)
                        self.pref_mapper[tuple(data_item)] = item
                        self.pref_color["<{}>".format(item)] = color
                    widget2 = self.makeInsertButton()
                    widget1.currentTextChanged.connect(self.mapper.map)

                    self.mapper.setMapping(widget2, level1)
                    self.mapper.setMapping(widget1, level1)
                    self.widget_mapper[level1] = widget1
                    gLayout.addWidget(self.makeColorCodeLabel(color), row, 0)
                    gLayout.addWidget(widget1, row, 1)
                    gLayout.addWidget(widget2, row, 2)

        self.mapper.mapped[str].connect(self.choiceMade)

        buttonBox = QDialogButtonBox(
            QDialogButtonBox.Cancel | QDialogButtonBox.Ok | QDialogButtonBox.Help
        )
        self.helpButton = buttonBox.button(QDialogButtonBox.Help)  # type: QPushButton
        self.helpButton.clicked.connect(self.helpButtonClicked)
        self.helpButton.setToolTip(_("Get help online..."))
        translateDialogBoxButtons(buttonBox)

        buttonBox.rejected.connect(self.reject)
        buttonBox.accepted.connect(self.accept)

        layout.addWidget(buttonBox)

        self.editor.setPrefMapper(self.pref_mapper, self.pref_color)
        self.editor.displayPrefList(user_pref_list)

        self.show()
        self.setWidgetSizes()

    def helpButtonClicked(self) -> None:
        if self.generation_type in (
            NameGenerationType.photo_name,
            NameGenerationType.video_name,
        ):
            location = "#rename"
        else:
            location = "#subfoldergeneration"
        webbrowser.open_new_tab(
            "http://www.damonlynch.net/rapid/documentation/{}".format(location)
        )

    def makeInsertButton(self) -> QPushButton:
        w = QPushButton(_("Insert"))
        w.clicked.connect(self.mapper.map)
        w.setSizePolicy(self.pushButtonSizePolicy)
        return w

    def setWidgetSizes(self) -> None:
        """
        Resize widgets for enhanced visual layout
        """

        # Set the widths of the comboboxes and labels to the width of the
        # longest control
        width = max(widget.width() for widget in self.widget_mapper.values())
        for widget in self.widget_mapper.values():
            widget.setMinimumWidth(width)

        # Set the scroll area to be big enough to eliminate the horizontal scrollbar
        scrollbar_width = self.style().pixelMetric(QStyle.PM_ScrollBarExtent)
        self.area.setMinimumWidth(self.area.widget().width() + scrollbar_width)

    @pyqtSlot(str)
    def choiceMade(self, widget: str) -> None:
        """
        User has pushed one of the "Insert" buttons or selected a new value in one
        of the combo boxes.

        :param widget: widget's name, which uniquely identifies it
        """

        if widget == JOB_CODE:
            pref_value = _(JOB_CODE)
        else:
            combobox = self.widget_mapper[widget]  # type: QComboBox
            pref_value = combobox.currentText()

        self.editor.insertPrefValue(pref_value)

        # Set focus not on the control that was just used, but the editor
        self.editor.setFocus(Qt.OtherFocusReason)

    def makeColorCodeLabel(self, color: str) -> QLabel:
        """
        Generate a colored square to show beside the combo boxes / label
        :param color: color to use, e.g. #7a9c38
        :return: the square in form of a label
        """

        colorLabel = QLabel(" ")
        colorLabel.setStyleSheet("QLabel {background-color: %s;}" % color)
        size = QFontMetrics(QFont()).height()
        colorLabel.setFixedSize(QSize(size, size))
        return colorLabel

    def updateExampleFilename(self) -> None:

        user_pref_list = self.editor.user_pref_list
        self.user_pref_colors = self.editor.user_pref_colors

        if not self.is_subfolder:
            self.user_pref_colors.append(self.filename_pref_color)

        self.messageWidget.setCurrentIndex(0)

        if self.is_subfolder:
            if user_pref_list:
                try:
                    user_pref_list.index(SEPARATOR)
                except ValueError:
                    # Inform the user that a subfolder separator (os.sep) is used to
                    # create subfolder levels
                    self.messageWidget.setCurrentIndex(2)
                else:
                    if (
                        user_pref_list[0] == SEPARATOR
                        or user_pref_list[-3] == SEPARATOR
                    ):
                        # inform the user that there is no need to start or finish
                        # with a subfolder separator (os.sep)
                        self.messageWidget.setCurrentIndex(3)
            else:
                # Inform the user that a subfolder separator (os.sep) is used to create
                # subfolder levels
                self.messageWidget.setCurrentIndex(2)

            changed, user_pref_list, self.user_pref_colors = filter_subfolder_prefs(
                user_pref_list, self.user_pref_colors
            )
        else:
            try:
                user_pref_list.index(SEQUENCES)
            except ValueError:
                # Inform the user that sequences can be used to make filenames unique
                self.messageWidget.setCurrentIndex(2)

        if self.generation_type == NameGenerationType.photo_name:
            self.name_generator = gn.PhotoName(user_pref_list)
        elif self.generation_type == NameGenerationType.video_name:
            self.name_generator = gn.VideoName(user_pref_list)
        elif self.generation_type == NameGenerationType.photo_subfolder:
            self.name_generator = gn.PhotoSubfolder(user_pref_list)
        else:
            assert self.generation_type == NameGenerationType.video_subfolder
            self.name_generator = gn.VideoSubfolder(user_pref_list)

        self.name_parts = self.name_generator.generate_name(
            self.sample_rpd_file, parts=True
        )
        self.showExample()
        self.updateComboBoxCurrentIndex()

    def updateComboBoxCurrentIndex(self) -> None:
        """
        Sets the combo value to match the current preference value
        """

        combobox_index, pref_list_index = self.getPresetMatch()
        if pref_list_index >= 0:
            # the editor contains an existing preset
            self.preset.setCurrentIndex(combobox_index)
            if self.preset.preset_edited or self.preset.new_preset:
                self.preset.resetPresetList()
                self.preset.setSaveNewCustomPresetEnabled(enabled=False)
            if pref_list_index >= len(self.builtin_pref_names):
                self.current_custom_name = self.preset.currentText()
            else:
                self.current_custom_name = None
        elif not (self.preset.new_preset or self.preset.preset_edited):
            if self.current_custom_name is None:
                self.preset.setPresetNew()
            else:
                self.preset.setPresetEdited(self.current_custom_name)
            self.preset.setSaveNewCustomPresetEnabled(enabled=True)
        else:
            self.preset.setCurrentIndex(0)

    def showExample(self) -> None:
        """
        Insert text into example widget, eliding it if necessary
        """

        user_pref_colors = self.user_pref_colors

        parts = copy.copy(self.name_parts)
        metrics = QFontMetrics(self.example.font())
        width = self.example.width() - metrics.width("…")

        # Cannot elide rich text using Qt code. Thus, elide the plain text.
        plain_text_name = "".join(parts)

        if self.is_subfolder:
            plain_text_name = self.name_generator.filter_subfolder_characters(
                plain_text_name
            )
        elided_text = metrics.elidedText(plain_text_name, Qt.ElideRight, width)
        elided = False

        while plain_text_name != elided_text:
            elided = True
            parts = remove_last_char_from_list_str(parts)
            plain_text_name = "".join(parts)
            if self.is_subfolder:
                plain_text_name = self.name_generator.filter_subfolder_characters(
                    plain_text_name
                )
            elided_text = metrics.elidedText(plain_text_name, Qt.ElideRight, width)

        colored_parts = [
            '<span style="color: {};">{}</span>'.format(color, part) if color else part
            for part, color in zip(parts, user_pref_colors)
        ]

        name = "".join(colored_parts)
        if elided:
            name = "{}&hellip;".format(name)

        if self.is_subfolder:
            name = self.name_generator.filter_subfolder_characters(name)

        if self.sample_rpd_file.name_generation_problem:
            self.messageWidget.setCurrentIndex(1)

        self.example.setTextFormat(Qt.RichText)
        self.example.setText(name)

    def resizeEvent(self, event: QResizeEvent) -> None:
        if self.example.text():
            self.showExample()
        super().resizeEvent(event)

    def getPrefList(self) -> List[str]:
        """
        :return: the pref list the user has specified
        """

        return self.editor.user_pref_list

    @pyqtSlot(int)
    def presetComboItemActivated(self, index: int) -> None:
        """
        Respond to user activating the Preset combo box.

        :param index: index of the item activated
        """

        preset_class = self.preset.currentData()
        if preset_class == PresetClass.new_preset:
            createPreset = CreatePreset(existing_custom_names=self.preset_names)
            if createPreset.exec():
                # User has created a new preset
                preset_name = createPreset.presetName()
                assert preset_name not in self.preset_names
                self.current_custom_name = preset_name
                self.preset.addCustomPreset(preset_name)
                self.saveNewPreset(preset_name=preset_name)
                if len(self.preset_names) == 1:
                    self.preset.setRemoveAllCustomEnabled(True)
                self.preset.setSaveNewCustomPresetEnabled(enabled=False)
            else:
                # User cancelled creating a new preset
                self.updateComboBoxCurrentIndex()
        elif preset_class in (PresetClass.builtin, PresetClass.custom):
            index = self.combined_pref_names.index(self.preset.currentText())
            pref_list = self.combined_pref_lists[index]
            self.editor.displayPrefList(pref_list=pref_list)
            if index >= len(self.builtin_pref_names):
                self.movePresetToFront(index=len(self.builtin_pref_names) - index)
        elif preset_class == PresetClass.remove_all:
            self.preset.removeAllCustomPresets(no_presets=len(self.preset_names))
            self.clearCustomPresets()
            self.preset.setRemoveAllCustomEnabled(False)
            self.updateComboBoxCurrentIndex()
        elif preset_class == PresetClass.update_preset:
            self.updateExistingPreset()
            self.updateComboBoxCurrentIndex()

    def updateExistingPreset(self) -> None:
        """
        Updates (saves) an existing preset (assumed to be self.current_custom_name)
        with the new user_pref_list found in the editor.

        Assumes cached self.preset_names and self.preset_pref_lists represent
        current save preferences. Will update these and overwrite the relevant
        preset preference.
        """

        preset_name = self.current_custom_name
        user_pref_list = self.editor.user_pref_list
        index = self.preset_names.index(preset_name)
        self.preset_pref_lists[index] = user_pref_list
        if index > 0:
            self.movePresetToFront(index=index)
        else:
            self._updateCombinedPrefs()
            self.prefs.set_preset(
                preset_type=self.preset_type,
                preset_names=self.preset_names,
                preset_pref_lists=self.preset_pref_lists,
            )

    def movePresetToFront(self, index: int) -> None:
        """
        Extracts the preset from the current list of presets and moves it
        to the front if not already there.

        Assumes cached self.preset_names and self.preset_pref_lists represent
        current save preferences. Will update these and overwrite the relevant
        preset preference.

        :param index: index into self.preset_pref_lists / self.preset_names of
         the item to move
        """

        if index == 0:
            return
        preset_name = self.preset_names.pop(index)
        pref_list = self.preset_pref_lists.pop(index)
        self.preset_names.insert(0, preset_name)
        self.preset_pref_lists.insert(0, pref_list)
        self._updateCombinedPrefs()
        self.prefs.set_preset(
            preset_type=self.preset_type,
            preset_names=self.preset_names,
            preset_pref_lists=self.preset_pref_lists,
        )

    def saveNewPreset(self, preset_name: str) -> None:
        """
        Saves the current user_pref_list (retrieved from the editor) and
        saves it in the program preferences.

        Assumes cached self.preset_names and self.preset_pref_lists represent
        current save preferences. Will update these and overwrite the relevant
        preset preference.

        :param preset_name: name for the new preset
        """

        user_pref_list = self.editor.user_pref_list
        self.preset_names.insert(0, preset_name)
        self.preset_pref_lists.insert(0, user_pref_list)
        self._updateCombinedPrefs()
        self.prefs.set_preset(
            preset_type=self.preset_type,
            preset_names=self.preset_names,
            preset_pref_lists=self.preset_pref_lists,
        )

    def clearCustomPresets(self) -> None:
        """
        Deletes all of the custom presets.

        Assumes cached self.preset_names and self.preset_pref_lists represent
        current save preferences. Will update these and overwrite the relevant
        preset preference.
        """
        self.preset_names = []
        self.preset_pref_lists = []
        self.current_custom_name = None
        self._updateCombinedPrefs()
        self.prefs.set_preset(
            preset_type=self.preset_type,
            preset_names=self.preset_names,
            preset_pref_lists=self.preset_pref_lists,
        )

    def updateCachedPrefLists(self) -> None:
        self.preset_names, self.preset_pref_lists = self.prefs.get_preset(
            preset_type=self.preset_type
        )
        self._updateCombinedPrefs()

    def _updateCombinedPrefs(self):
        self.combined_pref_names = self.builtin_pref_names + self.preset_names
        self.combined_pref_lists = self.builtin_pref_lists + tuple(
            self.preset_pref_lists
        )

    def getPresetMatch(self) -> Tuple[int, int]:
        """
        :return: Tuple of the Preset combobox index and the combined pref/name list index,
        if the current user pref list matches an entry in it. Else Tuple of (-1, -1).
        """

        index = match_pref_list(
            pref_lists=self.combined_pref_lists,
            user_pref_list=self.editor.user_pref_list,
        )
        if index >= 0:
            combobox_name = self.combined_pref_names[index]
            return self.preset.findText(combobox_name), index
        return -1, -1

    @pyqtSlot()
    def accept(self) -> None:
        """
        Slot called when the okay button is clicked.

        If there are unsaved changes, query the user if they want their changes
        saved as a new preset or if the existing preset should be updated
        """

        if self.preset.preset_edited or self.preset.new_preset:
            title = _("Save Preset - Rapid Photo Downloader")
            if self.preset.new_preset:

                message = _(
                    "<b>Do you want to save the changes in a new custom preset?</b>"
                    "<br><br>"
                    "Creating a custom preset is not required, but can help you keep "
                    "organized.<br><br>"
                    "The changes to the preferences will still be applied regardless "
                    "of whether you create a new custom preset or not."
                )
                msgBox = standardMessageBox(
                    standardButtons=QMessageBox.Yes | QMessageBox.No,
                    title=title,
                    rich_text=True,
                    message=message,
                )
                updateButton = newButton = None
            else:
                assert self.preset.preset_edited
                msgBox = QMessageBox()
                msgBox.setTextFormat(Qt.RichText)
                msgBox.setIcon(QMessageBox.Question)
                msgBox.setWindowTitle(title)
                message = _(
                    "<b>Do you want to save the changes in a custom preset?</b><br><br>"
                    "If you like, you can create a new custom preset or update the "
                    "existing custom preset.<br><br>"
                    "The changes to the preferences will still be applied regardless "
                    "of whether you save a custom preset or not."
                )
                msgBox.setText(message)
                msgBox.addButton(QMessageBox.No)
                translateMessageBoxButtons(msgBox)
                updateButton = msgBox.addButton(
                    _('Update Custom Preset "%s"') % self.current_custom_name,
                    QMessageBox.YesRole,
                )
                newButton = msgBox.addButton(
                    _("Save New Custom Preset"), QMessageBox.YesRole
                )

            choice = msgBox.exec()
            save_new = update = False
            if self.preset.new_preset:
                save_new = choice == QMessageBox.Yes
            else:
                if msgBox.clickedButton() == updateButton:
                    update = True
                elif msgBox.clickedButton() == newButton:
                    save_new = True

            if save_new:
                createPreset = CreatePreset(existing_custom_names=self.preset_names)
                if createPreset.exec():
                    # User has created a new preset
                    preset_name = createPreset.presetName()
                    assert preset_name not in self.preset_names
                    self.saveNewPreset(preset_name=preset_name)
            elif update:
                self.updateExistingPreset()

        # Check to make sure that in menus (which have a limited number of menu items)
        # that our chosen entry is displayed
        if self.max_entries:
            combobox_index, pref_list_index = self.getPresetMatch()
            if pref_list_index >= self.max_entries:
                self.updateExistingPreset()

        # Regardless of any user actions, close the dialog box
        super().accept()


if __name__ == "__main__":

    # Application development test code:

    app = QApplication([])

    app.setOrganizationName("Rapid Photo Downloader")
    app.setOrganizationDomain("damonlynch.net")
    app.setApplicationName("Rapid Photo Downloader")

    prefs = Preferences()

    # prefDialog = PrefDialog(DICT_IMAGE_RENAME_L0, PHOTO_RENAME_MENU_DEFAULTS_CONV[1],
    #                         NameGenerationType.photo_name, prefs)
    # prefDialog = PrefDialog(DICT_VIDEO_RENAME_L0, VIDEO_RENAME_MENU_DEFAULTS_CONV[1],
    #                         NameGenerationType.video_name, prefs)
    prefDialog = PrefDialog(
        DICT_SUBFOLDER_L0,
        PHOTO_SUBFOLDER_MENU_DEFAULTS_CONV[2],
        NameGenerationType.photo_subfolder,
        prefs,
        max_entries=10,
    )
    # prefDialog = PrefDialog(
    #     DICT_VIDEO_SUBFOLDER_L0, VIDEO_SUBFOLDER_MENU_DEFAULTS_CONV[2],
    #     NameGenerationType.video_subfolder, prefs, max_entries=10
    # )
    prefDialog.show()
    app.exec_()
