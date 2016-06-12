# Copyright (C) 2016 Damon Lynch <damonlynch@gmail.com>

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

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2016, Damon Lynch"

from typing import Dict, Optional, List, Union, Tuple
import datetime
import copy

from gettext import gettext as _

from PyQt5.QtWidgets import (QTextEdit, QApplication, QComboBox, QPushButton, QLabel, QDialog,
    QDialogButtonBox, QVBoxLayout, QFormLayout,  QGridLayout, QGroupBox, QScrollArea, QWidget,
                             QFrame, QStyle, QSizePolicy, QStackedWidget)
from PyQt5.QtGui import (QTextCharFormat, QFont, QTextCursor, QMouseEvent, QSyntaxHighlighter,
                         QTextDocument, QBrush, QColor, QFontMetrics, QKeyEvent, QResizeEvent)
from PyQt5.QtCore import (Qt, pyqtSlot, QSignalMapper, QSize, pyqtSignal)

from sortedcontainers import SortedList

from raphodo.generatenameconfig import *
import raphodo.generatename as gn
from raphodo.constants import CustomColors, PrefPosition, NameGenerationType
from raphodo.rpdfile import SamplePhoto, SampleVideo, RPDFile, Photo, Video, FileType
from raphodo.preferences import DownloadsTodayTracker, Preferences
import raphodo.exiftool as exiftool
from raphodo.utilities import remove_last_char_from_list_str

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
        self.document().documentLayout().documentSizeChanged.connect(self.wrapHeightToContents)

    def wrapHeightToContents(self) -> None:
        """
        Adjust the text area size to show contents without vertical scrollbar

        Derived from:
        http://stackoverflow.com/questions/11851020/a-qwidget-like-qtextedit-that-wraps-its-height-
        automatically-to-its-contents/11858803#11858803
        """

        docHeight = self.document().size().height() + 5
        if self.heightMin <= docHeight <= self.heightMax and docHeight > self.minimumHeight():
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
        elif key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Home, Qt.Key_End, Qt.Key_PageUp,
                   Qt.Key_PageDown, Qt.Key_Up, Qt.Key_Down):
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
        if not(len(b)):
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
            left = b[index -1]
            right = b[index]

            at = right[0] == position
            to_left = left[1] == position -1
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

    def displayPrefList(self, pref_list) -> None:
        p = pref_list
        values = []
        for i in range(0, len(pref_list), 3):
            try:
                value = '<{}>'.format(self.pref_mapper[(p[i], p[i+1], p[i+2])])
            except KeyError:
                if p[i] == SEPARATOR:
                    value = SEPARATOR
                else:
                    assert p[i] == TEXT
                    value = p[i+1]
            values.append(value)

        cursor = self.textCursor()  # type: QTextCursor
        cursor.insertText(''.join(values))

    def insertPrefValue(self, pref_value: str) -> None:
        cursor = self.textCursor()  # type: QTextCursor
        cursor.insertText('<{}>'.format(pref_value))

    def _setHighlighter(self) -> None:
        self.highlighter = PrefHighlighter(list(self.string_to_pref_mapper.keys()),
                                           self.pref_color,
                                           self.document())

        self.highlighter.blockHighlighted.connect(self.generatePrefList)

    def setPrefMapper(self, pref_mapper: Dict[Tuple[str, str, str], str],
                      pref_color: Dict[str, str]) -> None:
        self.pref_mapper = pref_mapper
        self.string_to_pref_mapper = {value: key for key, value in pref_mapper.items()}

        self.pref_color = pref_color
        self._setHighlighter()

    def _parseTextFragment(self, text_fragment) -> List[str]:
        if self.subfolder:
            text_fragments = text_fragment.split(os.sep)
            for index, text_fragment in enumerate(text_fragments):
                if text_fragment:
                    self.user_pref_list.extend([TEXT, text_fragment, ''])
                    self.user_pref_colors.append('')
                if index < len(text_fragments) - 1:
                    self.user_pref_list.extend([SEPARATOR, '', ''])
                    self.user_pref_colors.append('')
        else:
            self.user_pref_list.extend([TEXT, text_fragment, ''])
            self.user_pref_colors.append('')

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
            text_fragment = text[:b[0][0]]
            self._parseTextFragment(text_fragment)

        if len(b) > 1:
            for index, item in enumerate(b[1:]):
                start, end = b[index]
                # Add + 1 to start to remove the opening <
                pl.extend(self.string_to_pref_mapper[text[start + 1: end]])
                # Add + 1 to start to include the closing >
                self._addColor(text[start: end + 1])

                text_fragment = text[b[index][1] + 1:item[0]]
                self._parseTextFragment(text_fragment)

        # Handle the final pref value
        if b:
            start, end = b[-1]
            # Add + 1 to start to remove the opening <
            pl.extend(self.string_to_pref_mapper[text[start + 1: end]])
            # Add + 1 to start to include the closing >
            self._addColor(text[start: end + 1])
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

    def __init__(self, pref_defn_strings: List[str],
                 pref_color: Dict[str, str],
                 document: QTextDocument) -> None:
        super().__init__(document)

        # Where detected preference values start and end:
        # [(start, end), (start, end), ...]
        self.boundaries = SortedList()

        pref_defns = ('<{}>'.format(pref) for pref in pref_defn_strings)
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
            raise StopIteration
        start = 0
        while True:
            start = text.find(pref_defn, start)
            if start == -1:
                raise StopIteration
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

class PrefDialog(QDialog):
    """
    Dialog window to allow editing of file renaming and subfolder generation
    """

    def __init__(self, pref_defn: OrderedDict,
                 user_pref_list: List[str],
                 generation_type: NameGenerationType,
                 prefs: Preferences,
                 exiftool_process: exiftool.ExifTool,
                 sample_rpd_file: Optional[Union[Photo, Video]]=None,
                 parent=None) -> None:
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
        """

        super().__init__(parent)

        self.generation_type = generation_type

        # Setup values needed for name generation

        self.exiftool_process = exiftool_process

        self.prefs = prefs

        self.downloads_today_tracker = DownloadsTodayTracker(
            day_start=self.prefs.day_start,
            downloads_today=self.prefs.downloads_today)

        self.sequences = gn.Sequences(self.downloads_today_tracker,
                                      self.prefs.stored_sequence_no)

        self.sample_rpd_file = sample_rpd_file
        if sample_rpd_file is not None:
            # TODO handle sample file from camera?
            full_file_name = sample_rpd_file.full_file_name
            if not sample_rpd_file.load_metadata(full_file_name=full_file_name,
                                                 et_process=self.exiftool_process):
                self.sample_rpd_file = None
            else:
                self.sample_rpd_file.sequences = self.sequences
                self.sample_photo.download_start_time = datetime.datetime.now()

        if self.sample_rpd_file is None:
            if generation_type in (NameGenerationType.photo_name,
                                   NameGenerationType.photo_subfolder):
                self.sample_rpd_file = SamplePhoto(sequences=self.sequences)
            else:
                self.sample_rpd_file = SampleVideo(sequences=self.sequences)

        self.sample_rpd_file.job_code = self.prefs.most_recent_job_code(missing=_('Job Code'))
        self.sample_rpd_file.strip_characters = self.prefs.strip_characters
        if self.sample_rpd_file.file_type == FileType.photo:
            self.sample_rpd_file.generate_extension_case = self.prefs.photo_extension
        else:
            self.sample_rpd_file.generate_extension_case = self.prefs.video_extension

        # Setup widgets and helper values

        # Display messages using a stacked widget

        self.messageWidget = QStackedWidget()
        self.messageWidget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        # For some obscure reason, must set the label types for all labels in the stacked
        # widget to have the same properties, or else the stacked layout size goes bonkers.
        # Must make the empty lable contain *something*, too.
        blank = QLabel(' ')
        blank.setWordWrap(True)
        blank.setTextFormat(Qt.RichText)
        self.messageWidget.addWidget(blank)

        # Translators: please do not modify or leave out html formatting tags like <i> and
        # <b>. These are used to format the text the users sees
        warning_msg = _(
            "<i><b>Warning:</b> There is insufficient metadata to fully generate the name. "
            "Please use other renaming options.</i>")

        self.is_subfolder = generation_type in (NameGenerationType.photo_subfolder,
                                                NameGenerationType.video_subfolder)

        self.warningLabel = QLabel(warning_msg)
        self.warningLabel.setWordWrap(True)
        self.warningLabel.setAlignment(Qt.AlignTop|Qt.AlignLeft)

        self.editor = PrefEditor(subfolder=self.is_subfolder)
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        sizePolicy.setVerticalStretch(1)
        self.editor.setSizePolicy(sizePolicy)

        self.editor.prefListGenerated.connect(self.updateExampleFilename)

        # Generated subfolder / file name example
        self.example = QLabel()

        flayout = QFormLayout()
        flayout.addRow(_('Example:'), self.example)

        layout = QVBoxLayout()
        self.setLayout(layout)

        layout.addLayout(flayout)
        layout.addSpacing(QFontMetrics(QFont()).height() / 2)
        layout.addWidget(self.editor)

        self.messageWidget.addWidget(self.warningLabel)

        if self.is_subfolder:
            subfolder_msg = _(
                "<i><b>Hint:</b> The character</i> %(separator)s <i>creates a new subfolder "
                "level.</i>"
            ) % dict(separator=os.sep)
            self.subfolderSeparatorLabel = QLabel(subfolder_msg)
            self.subfolderSeparatorLabel.setWordWrap(True)
            self.subfolderSeparatorLabel.setAlignment(Qt.AlignTop|Qt.AlignLeft)
            self.messageWidget.addWidget(self.subfolderSeparatorLabel)

            subfolder_first_char_msg = _(
                "<i><b>Hint:</b> There is no need start or end with the folder separator </i> %("
                "separator)s<i>, because it is added automatically.</i>"
            ) % dict(separator=os.sep)
            self.subfolderPointlessCharLabel = QLabel(subfolder_first_char_msg)
            self.subfolderPointlessCharLabel.setWordWrap(True)
            self.subfolderPointlessCharLabel.setAlignment(Qt.AlignTop|Qt.AlignLeft)
            self.messageWidget.addWidget(self.subfolderPointlessCharLabel)

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

        areaLayout.addWidget(self.messageWidget)
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
            areaLayout.addWidget(gb)
            gLayout = QGridLayout()
            gb.setLayout(gLayout)
            if level1 is None:
                assert title == JOB_CODE
                widget1 = QLabel(' ' + title_i18n)
                widget2 = self.makeInsertButton()
                self.widget_mapper[title] = widget1
                self.mapper.setMapping(widget2, title)
                self.pref_mapper[(title, '', '')] = title_i18n
                self.pref_color['<{}>'.format(title_i18n)] = color
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
                        data.append([METADATA, element, ''])
                        self.pref_mapper[(METADATA, element, '')] = element_i18n
                        self.pref_color['<{}>'.format(element_i18n)] = color
                    else:
                        for e in level2:
                            e_i18n = _(e)
                            # Translators: appears in a combobox, e.g. Image Date (YYYY)
                            item = _('{choice} ({variant})').format(choice=element_i18n,
                                                                    variant=e_i18n)
                            elements.append(item)
                            data.append([METADATA, element, e])
                            self.pref_mapper[(METADATA, element, e)] = item
                            self.pref_color['<{}>'.format(item)] = color
                widget1 = QComboBox()
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
                    widget1 = QComboBox()
                    level1_i18n = _(level1)
                    items = (_('{choice} ({variant})').format(
                             choice=level1_i18n, variant=_(element))
                             for element in pref_defn[title][level1])
                    data = ([title, level1, element] for element in pref_defn[title][level1])
                    for item, data_item in zip(items, data):
                        widget1.addItem(item, data_item)
                        self.pref_mapper[tuple(data_item)] = item
                        self.pref_color['<{}>'.format(item)] = color
                    widget2 =  self.makeInsertButton()
                    widget1.currentTextChanged.connect(self.mapper.map)

                    self.mapper.setMapping(widget2, level1)
                    self.mapper.setMapping(widget1, level1)
                    self.widget_mapper[level1] = widget1
                    gLayout.addWidget(self.makeColorCodeLabel(color), row, 0)
                    gLayout.addWidget(widget1, row, 1)
                    gLayout.addWidget(widget2, row, 2)

        self.mapper.mapped[str].connect(self.choiceMade)
        self.editor.setPrefMapper(self.pref_mapper, self.pref_color)

        buttonBox = QDialogButtonBox()
        buttonBox.addButton(QDialogButtonBox.Cancel)  # type: QPushButton
        buttonBox.addButton(QDialogButtonBox.Ok)  # type: QPushButton
        buttonBox.rejected.connect(self.reject)
        buttonBox.accepted.connect(self.accept)

        layout.addWidget(buttonBox)

        self.editor.setPrefMapper(self.pref_mapper, self.pref_color)
        self.editor.displayPrefList(user_pref_list)

    def makeInsertButton(self) -> QPushButton:
        w = QPushButton(_('Insert'))
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

        colorLabel = QLabel(' ')
        colorLabel.setStyleSheet('QLabel {background-color: %s;}' % color)
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
                    self.messageWidget.setCurrentIndex(2)
                else:
                    if user_pref_list[0] == SEPARATOR or user_pref_list[-3] == SEPARATOR:
                        self.messageWidget.setCurrentIndex(3)
            else:
                self.messageWidget.setCurrentIndex(2)

            changed, user_pref_list, self.user_pref_colors = filter_subfolder_prefs(
                user_pref_list, self.user_pref_colors)

        if self.generation_type == NameGenerationType.photo_name:
            self.name_generator = gn.PhotoName(user_pref_list)
        elif self.generation_type == NameGenerationType.video_name:
            self.name_generator = gn.VideoName(user_pref_list)
        elif self.generation_type == NameGenerationType.photo_subfolder:
            self.name_generator = gn.PhotoSubfolder(user_pref_list)
        else:
            assert self.generation_type == NameGenerationType.video_subfolder
            self.name_generator = gn.VideoSubfolder(user_pref_list)

        self.sample_rpd_file.initialize_problem()

        self.name_parts = self.name_generator.generate_name(self.sample_rpd_file, parts=True)
        self.showExample()

    def showExample(self) -> None:
        """
        Insert text into example widget, eliding it if necessary
        """

        user_pref_colors = self.user_pref_colors

        parts = copy.copy(self.name_parts)
        metrics = QFontMetrics(self.example.font())
        width = self.example.width() - metrics.width('…')

        # Cannot elide rich text using Qt code. Thus, elide the plain text.
        plain_text_name = ''.join(parts)

        if self.is_subfolder:
            plain_text_name = self.name_generator.filter_subfolder_characters(plain_text_name)
        elided_text = metrics.elidedText(plain_text_name, Qt.ElideRight, width)
        elided = False

        while plain_text_name != elided_text:
            elided = True
            parts = remove_last_char_from_list_str(parts)
            plain_text_name = ''.join(parts)
            if self.is_subfolder:
                plain_text_name = self.name_generator.filter_subfolder_characters(plain_text_name)
            elided_text = metrics.elidedText(plain_text_name, Qt.ElideRight, width)

        colored_parts = ['<span style="color: {};">{}</span>'.format(color, part) if color else part
                         for part, color in zip(parts, user_pref_colors)]

        name = ''.join(colored_parts)
        if elided:
            name = '{}&hellip;'.format(name)

        if self.is_subfolder:
            name = self.name_generator.filter_subfolder_characters(name)

        if self.sample_rpd_file.has_problem():
            self.messageWidget.setCurrentIndex(1)

        self.example.setTextFormat(Qt.RichText)
        self.example.setText(name)

    def resizeEvent(self, event: QResizeEvent) -> None:
        if self.example.text():
            self.showExample()
        super().resizeEvent(event)

if __name__ == '__main__':

    # Application development test code:

    app = QApplication([])

    app.setOrganizationName("Rapid Photo Downloader")
    app.setOrganizationDomain("damonlynch.net")
    app.setApplicationName("Rapid Photo Downloader")

    prefs = Preferences()

    with exiftool.ExifTool() as exiftool_process:

        prefDialog = PrefDialog(DICT_IMAGE_RENAME_L0, PHOTO_RENAME_COMPLEX,
                                NameGenerationType.photo_name, prefs, exiftool_process)
        # prefDialog = PrefDialog(DICT_SUBFOLDER_L0, PHOTO_SUBFOLDER_MENU_DEFAULTS_CONV[2],
        #                         NameGenerationType.photo_subfolder, prefs, exiftool_process)
        prefDialog.show()
        prefDialog.setWidgetSizes()
        app.exec_()

