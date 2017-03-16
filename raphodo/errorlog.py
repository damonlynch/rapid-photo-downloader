#!/usr/bin/env python3

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
# along with Rapid Photo Downloader. If not,
# see <http://www.gnu.org/licenses/>.

"""
Error log window for Rapid Photo Downloader
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2017, Damon Lynch"

import logging
import shlex
import subprocess
import math
from collections import deque, namedtuple
from typing import Optional
from gettext import gettext as _

from PyQt5.QtWidgets import (QTextEdit, QDialog, QDialogButtonBox, QLineEdit, QVBoxLayout,
                             QHBoxLayout, QApplication, QPushButton, QLabel, QTextBrowser,
                             QStyle, QFrame)
from PyQt5.QtGui import (QPalette, QIcon, QFontMetrics, QFont, QColor, QKeyEvent, QKeySequence,
                         QTextDocument, QTextCursor, QPaintEvent, QPainter, QPen, QMouseEvent,
                         QShowEvent)
from PyQt5.QtCore import Qt, pyqtSlot, QSize, QUrl, QTimer, QRect, pyqtSignal, QEvent

import raphodo.qrc_resources as qrc_resources
from raphodo.constants import ErrorType
from raphodo.rpdfile import RPDFile


ErrorLogMessage = namedtuple('ErrorLogMessage', 'title body name uri')


class QFindLineEdit(QLineEdit):
    """
    LineEdit to be used for search, as in Firefox in page search.
    """


    def __init__(self, find_text='', parent=None) -> None:
        super().__init__(parent=parent)
        if not find_text:
            self.find_text = _('Find')
        else:
            self.find_text = find_text

        self.noTextPalette = QPalette()
        self.noTextPalette.setColor(QPalette.Text, Qt.gray)

        self.setEmptyState()

        self.cursorPositionChanged.connect(self.onCursorPositionChanged)
        self.textEdited.connect(self.onTextEdited)

    def setEmptyState(self) -> None:
        self.empty = True
        self.setText(self.find_text)
        self.setCursorPosition(0)
        self.setPalette(self.noTextPalette)

    @pyqtSlot(str)
    def onTextEdited(self, text: str) -> None:
        if not text:
            self.setEmptyState()
        elif self.empty:
            self.empty = False
            self.setPalette(QPalette())
            self.setText(text[:-len(self.find_text)])

    @pyqtSlot(int, int)
    def onCursorPositionChanged(self, old: int, new: int) -> None:
        if self.empty:
            self.blockSignals(True)
            self.setCursorPosition(0)
            self.blockSignals(False)

    def getText(self) -> str:
        if self.empty:
            return ''
        else:
            return self.text()


class ErrorLog(QDialog):
    """
    Display error messages from the download in a dialog.

    Search/find feature is live, like Firefox. However it's pretty slow
    with a large amount of data, so don't initiate a new search each
    and every time data is appended to the log window. Instead, if a search
    is active, wait for one second after text has been appended before
    doing the search.
    """

    dialogShown = pyqtSignal()
    dialogActivated = pyqtSignal()

    def __init__(self, rapidApp, parent=None) -> None:
        super().__init__(parent=parent)

        self.setModal(False)
        self.setSizeGripEnabled(True)

        self.search_pending = False
        self.add_queue = deque()

        self.rapidApp = rapidApp

        layout = QVBoxLayout()
        self.setWindowTitle(_('Rapid Photo Downloader Error Log'))

        self.log = QTextBrowser()
        self.log.setReadOnly(True)

        self.highlightColor = QColor('#cb1dfa')
        self.textHighlightColor = QColor(Qt.white)

        self.noFindPalette = QPalette()
        self.noFindPalette.setColor(QPalette.WindowText, QPalette().color(QPalette.Mid))
        self.foundPalette = QPalette()
        self.foundPalette.setColor(QPalette.WindowText, QPalette().color(QPalette.WindowText))

        self.find_cursors = []
        self.current_find_index = -1

        self.log.anchorClicked.connect(self.anchorClicked)
        self.log.setOpenLinks(False)

        self.defaultFont = QFont()
        self.defaultFont.setPointSize(QFont().pointSize() - 1)
        self.log.setFont(self.defaultFont)
        self.log.textChanged.connect(self.textChanged)

        message = _('Find in error log')
        self.find = QFindLineEdit(find_text=message)
        self.find.textEdited.connect(self.onFindChanged)
        style = self.find.style()  # type: QStyle
        frame_width = style.pixelMetric(QStyle.PM_DefaultFrameWidth)
        button_margin = style.pixelMetric(QStyle.PM_ButtonMargin)
        spacing = (frame_width + button_margin) * 2 + 8

        self.find.setMinimumWidth(QFontMetrics(QFont()).boundingRect(message).width() + spacing)

        font_height = QFontMetrics(self.font()).height()
        size = QSize(font_height, font_height)

        self.up = QPushButton()
        self.up.setIcon(QIcon(':/icons/up.svg'))
        self.up.setIconSize(size)
        self.up.clicked.connect(self.upClicked)
        self.up.setToolTip(_('Find the previous occurrence of the phrase'))
        self.down = QPushButton()
        self.down.setIcon(QIcon(':/icons/down.svg'))
        self.down.setIconSize(size)
        self.down.clicked.connect(self.downClicked)
        self.down.setToolTip(_('Find the next occurrence of the phrase'))

        self.highlightAll = QPushButton(_('&Highlight All'))
        self.highlightAll.setToolTip(_('Highlight all occurrences of the phrase'))
        self.matchCase = QPushButton(_('&Match Case'))
        self.matchCase.setToolTip(_('Search with case sensitivity'))
        self.wholeWords = QPushButton(_('&Whole Words'))
        self.wholeWords.setToolTip(_('Search whole words only'))
        for widget in (self.highlightAll, self.matchCase, self.wholeWords):
            widget.setCheckable(True)
            widget.setFlat(True)
        self.highlightAll.toggled.connect(self.highlightAllToggled)
        self.matchCase.toggled.connect(self.matchCaseToggled)
        self.wholeWords.toggled.connect(self.wholeWordsToggled)

        self.findResults = QLabel()
        self.findResults.setMinimumWidth(QFontMetrics(QFont()).boundingRect(
                _('%s of %s matches') % (1000, 1000)).width() + spacing)

        findLayout = QHBoxLayout()
        findLayout.setSpacing(0)
        spacing = 8
        findLayout.addWidget(self.find)
        findLayout.addWidget(self.up)
        findLayout.addWidget(self.down)
        findLayout.addSpacing(spacing)
        findLayout.addWidget(self.highlightAll)
        findLayout.addSpacing(spacing)
        findLayout.addWidget(self.matchCase)
        findLayout.addSpacing(spacing)
        findLayout.addWidget(self.wholeWords)
        findLayout.addSpacing(spacing)
        findLayout.addWidget(self.findResults)


        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.clear = buttons.addButton(_('Clear'), QDialogButtonBox.ActionRole)  # type: QPushButton
        buttons.rejected.connect(self.reject)
        self.clear.clicked.connect(self.clearClicked)
        self.clear.setEnabled(False)

        layout.addWidget(self.log)
        layout.addLayout(findLayout)
        layout.addSpacing(6)
        layout.addWidget(buttons)

        self.setLayout(layout)

        self.onFindChanged('')

        self.textColor = QPalette().color(QPalette.Text)
        self.criticalColor = QColor(Qt.red)

    @pyqtSlot()
    def textChanged(self) -> None:
        self.clear.setEnabled(bool(self.log.document().characterCount()))

    @pyqtSlot(QUrl)
    def anchorClicked(self, url: QUrl) -> None:
        if self.rapidApp.file_manager:
            uri = bytes(url.toEncoded()).decode()
            cmd = '{} {}'.format(self.rapidApp.file_manager, uri)
            logging.debug("Launching: %s", cmd)
            args = shlex.split(cmd)
            subprocess.Popen(args)

    def _makeFind(self, back: bool=False) -> int:
        flags = QTextDocument.FindFlags()
        if self.matchCase.isChecked():
            flags |= QTextDocument.FindCaseSensitively
        if self.wholeWords.isChecked():
            flags |= QTextDocument.FindWholeWords
        if back:
            flags |= QTextDocument.FindBackward
        return flags

    def _clearSearch(self) -> None:
        cursor = self.log.textCursor()  # type: QTextCursor
        if cursor.hasSelection():
            cursor.clearSelection()
            self.log.setTextCursor(cursor)
        self.find_cursors = []
        self.log.setExtraSelections([])

    @pyqtSlot()
    def _doFind(self) -> None:
        """
        Do the find / search.

        If text needs to be appended, delay the search for one second.
        """

        if self.add_queue:
            while self.add_queue:
                severity, rpd_file = self.add_queue.popleft()
                self._addMessage(severity, rpd_file)
            QTimer.singleShot(1000, self._doFind)
            return

        cursor = self.log.textCursor()  # type: QTextCursor
        text = self.find.getText()
        highlight = self.highlightAll.isChecked()

        if self.find.empty or not text:
            self._clearSearch()
            self.findResults.setText('')
            return

        initial_position = cursor.selectionStart()  # type: int

        self.log.moveCursor(QTextCursor.Start)

        flags = self._makeFind()
        extraSelections = deque()

        count = 0
        index = None
        self.find_cursors = []

        while self.log.find(text, flags):
            cursor = self.log.textCursor()  # type: QTextCursor
            self.find_cursors.append(cursor)

            if index is None and cursor.selectionStart() >= initial_position:
                index = count
            count += 1

            if highlight:
                extra = QTextEdit.ExtraSelection()
                extra.format.setBackground(self.highlightColor)
                extra.format.setForeground(self.textHighlightColor)
                extra.cursor = cursor
                extraSelections.append(extra)

        self.log.setExtraSelections(extraSelections)

        if index is None:
            index = len(self.find_cursors) - 1

        if not self.find_cursors:
            cursor.setPosition(initial_position)
            self.log.setTextCursor(cursor)
            if not self.find.empty:
                self.findResults.setText(_('Phrase not found'))
                self.findResults.setPalette(self.noFindPalette)

        else:
            self.goToMatch(index=index)

        self.search_pending = False

    def goToMatch(self, index: int) -> None:
        if self.find_cursors:
            cursor = self.find_cursors[index]
            self.current_find_index = index
            self.log.setTextCursor(cursor)
            self.findResults.setText(_('%s of %s matches') % (index + 1, len(self.find_cursors)))
            self.findResults.setPalette(self.foundPalette)

    @pyqtSlot(bool)
    def upClicked(self, checked: bool) -> None:
        if self.current_find_index >= 0:
            if self.current_find_index == 0:
                index = len(self.find_cursors) - 1
            else:
                index = self.current_find_index - 1
            self.goToMatch(index=index)

    @pyqtSlot(bool)
    def downClicked(self, checked: bool) -> None:
        if self.current_find_index >= 0:
            if self.current_find_index == len(self.find_cursors) - 1:
                index = 0
            else:
                index = self.current_find_index + 1
            self.goToMatch(index=index)

    @pyqtSlot(str)
    def onFindChanged(self, text: str) -> None:
        self.up.setEnabled(not self.find.empty)
        self.down.setEnabled(not self.find.empty)

        self._doFind()

    @pyqtSlot(bool)
    def highlightAllToggled(self, toggled: bool) -> None:
        if self.find_cursors:
            extraSelections = deque()
            if self.highlightAll.isChecked():
                for cursor in self.find_cursors:
                    extra = QTextEdit.ExtraSelection()
                    extra.format.setBackground(self.highlightColor)
                    extra.format.setForeground(self.textHighlightColor)
                    extra.cursor = cursor
                    extraSelections.append(extra)
            self.log.setExtraSelections(extraSelections)

    @pyqtSlot(bool)
    def matchCaseToggled(self, toggled: bool) -> None:
        self._doFind()

    @pyqtSlot(bool)
    def wholeWordsToggled(self, toggled: bool) -> None:
        self._doFind()

    @pyqtSlot(bool)
    def clearClicked(self, toggled: bool) -> None:
        self.log.clear()
        self.clear.setEnabled(False)
        self._doFind()

    def _addMessage(self, severity: ErrorType,
                    rpd_file: RPDFile,
                    other_error: Optional[ErrorLogMessage]) -> None:

        if other_error is None:
            title = rpd_file.problem.get_title()
            name = rpd_file.get_current_name()
            uri = rpd_file.get_uri(desktop_environment=True)
            body = rpd_file.problem.get_problems()
        else:
            title = other_error.title
            name = other_error.name
            uri = other_error.uri
            body = other_error.body

        if severity == ErrorType.critical_error:
            self.log.setTextColor(self.criticalColor)
        self.log.setFontWeight(QFont.Bold)
        self.log.append(title)
        self.log.setFontWeight(QFont.Normal)
        if severity == ErrorType.critical_error:
            self.log.setTextColor(self.textColor)

        href = '<a href="{}">{}</a>'.format(uri, name)
        self.log.append(href)

        self.log.append(body + '<br>')

    def addMessage(self, severity: ErrorType,
                   rpd_file: RPDFile,
                   other_error: Optional[ErrorLogMessage]) -> None:
        if not self.find.empty and self.find_cursors:
            self._clearSearch()

        if not self.find.empty and self.search_pending:
            self.add_queue.append((severity, rpd_file, other_error))
        else:
            self._addMessage(severity, rpd_file, other_error)

        if not self.find.empty and not self.search_pending:
            self.search_pending = True
            self.findResults.setText(_('Search pending...'))
            self.findResults.setPalette(self.noFindPalette)
            QTimer.singleShot(1000, self._doFind)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.matches(QKeySequence.Find):
            self.find.setFocus()
        else:
            super().keyPressEvent(event)

    @pyqtSlot()
    def activate(self) -> None:
        self.setVisible(True)
        self.activateWindow()
        self.raise_()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.dialogShown.emit()

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.ActivationChange and self.isActiveWindow():
            self.dialogActivated.emit()
        super().changeEvent(event)


class SpeechBubble(QLabel):

    """
    Display a speech bubble with a counter in it, that when clicked
    emits a signal and resets.

    Bubble displayed only when counter is > 0.
    """

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rapidApp = parent
        self.image = QIcon(':/speech-bubble.svg')
        self._count = 0
        self.fillColor = QPalette().color(QPalette.Window)
        self.counterFont = QFont()
        self.counterFont.setPointSize(QFont().pointSize() - 1)
        self.custom_height = max(math.ceil(QFontMetrics(self.counterFont).height() * 1.7), 24)
        self.counterPen = QPen(QColor(Qt.white))
        self.setStyleSheet("QLabel {border: 0px;}")
        self.click_tooltip = _('The number of new entries added to the Error Log since it was last '
                               'open. Click to open the Error Log.')

    @property
    def count(self) -> int:
        return self._count

    @count.setter
    def count(self, value) -> None:
        self._count = value
        if value > 0:
            self.setToolTip(self.click_tooltip)
        self.update()

    def incrementCounter(self) -> None:
        self._count += 1
        self.setToolTip(self.click_tooltip)
        self.update()

    def paintEvent(self, event: QPaintEvent ):

        painter = QPainter()
        painter.begin(self)

        height = self.height()

        rect = self.rect()  # type: QRect
        if not self._count:
            painter.fillRect(rect, self.fillColor)
        else:
            painter.drawPixmap(0, 0, height, height, self.image.pixmap(height, height))
            painter.setFont(self.counterFont)
            painter.setPen(self.counterPen)
            if self._count > 9:
                value = '9+'
            else:
                value = str(self._count)
            painter.drawText(rect, Qt.AlignCenter, value)
        painter.end()

    def sizeHint(self) -> QSize:
        return QSize(self.custom_height, self.custom_height)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.clicked.emit()
        self.reset()

    @pyqtSlot()
    def reset(self) -> None:
        self.count = 0
        self.setToolTip('')


if __name__ == '__main__':

    # Application development test code:

    app = QApplication([])

    log = ErrorLog(None)
    log.show()
    app.exec_()