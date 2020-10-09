# Copyright (C) 2017-2020 Damon Lynch <damonlynch@gmail.com>

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
Display, edit and apply Job Codes.
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2017-2020, Damon Lynch"

from typing import Optional, Dict, Tuple, Union, List
import logging

from PyQt5.QtCore import (Qt, pyqtSlot, QRegularExpression)
from PyQt5.QtWidgets import (
    QWidget, QSizePolicy, QMessageBox, QVBoxLayout, QLabel, QScrollArea, QFrame, QGridLayout,
    QAbstractItemView, QListWidgetItem, QHBoxLayout, QDialog, QDialogButtonBox, QCheckBox,
    QComboBox
)
from PyQt5.QtGui import (
    QColor, QPalette, QFont, QRegularExpressionValidator, QIcon, QShowEvent
)


from raphodo.constants import (JobCodeSort, ThumbnailBackgroundName)
from raphodo.viewutils import (
    QFramedWidget, QNarrowListWidget, standardIconSize, translateDialogBoxButtons,
    standardMessageBox
)
from raphodo.panelview import QPanelView
from raphodo.preferences import Preferences
from raphodo.messagewidget import MessageWidget, MessageButton
from raphodo.chevroncombo import ChevronCombo


class JobCodeDialog(QDialog):
    def __init__(self, parent, on_download: bool, job_codes: List[str]) -> None:
        """
        Prompt user to enter a Job Code, either at the time a download starts,
        or to zero or more selected files before the download begins.

        :param parent: rapidApp main window
        :param on_download: if True, dialog is being prompted for before a download starts.
        :param job_codes:
        """

        super().__init__(parent)
        self.rapidApp = parent  # type: 'RapidWindow'
        self.prefs = self.rapidApp.prefs  # type: Preferences
        thumbnailModel = self.rapidApp.thumbnailModel

        # Whether the user has opened this dialog before a download starts without having
        # selected any files first
        no_selection_made = None  # type: Optional[bool]

        if on_download:
            directive = _('Enter a new Job Code, or select a previous one')

            file_types = thumbnailModel.getNoFilesJobCodeNeeded()
            details = file_types.file_types_present_details(title_case=False)
            if sum(file_types.values()) == 1:
                # Translators: the value substituted will be something like '1 photo'.
                file_details = _(
                    'The Job Code will be applied to %s that does not yet have a Job Code.'
                ) % details
            else:
                # Translators: the value substituted will be something like '85 photos and 5
                # videos'.
                file_details = _(
                    'The Job Code will be applied to %s that do not yet have a Job Code.'
                ) % details

            hint = '<b>Hint:</b> To assign Job Codes before the download begins, select ' \
                   'photos or videos and apply a new or existing Job Code to them via the Job Code panel.'
            file_details = '{}<br><br><i>{}</i>'.format(file_details, hint)

            title = _('Apply Job Code to Download')
        else:
            directive = _('Enter a new Job Code')

            file_types = thumbnailModel.getNoFilesSelected()
            no_selection_made = sum(file_types.values()) == 0
            if no_selection_made:
                file_details = '<i>' + _(
                    '<b>Hint:</b> Select photos or videos before entering a new Job Code to '
                    'have the Job Code applied to them.'
                ) + '</i>'

                _('')
            else:
                details = file_types.file_types_present_details(title_case=False)
                # Translators: the value substituted will be something like '100 photos and 5
                # videos'.
                file_details = '<i>' + _('The new Job Code will be applied to %s.') % details \
                               + '</i>'

            title = _('New Job Code')

        instructionLabel = QLabel('<b>%s</b><br><br>%s<br>' % (directive, file_details))
        instructionLabel.setWordWrap(True)

        self.jobCodeComboBox = QComboBox()
        self.jobCodeComboBox.addItems(job_codes)
        self.jobCodeComboBox.setEditable(True)

        if not self.prefs.strip_characters:
            exp = "[^/\\0]+"
        else:
            exp = '[^\\:\*\?"<>|\\0/]+'

        self.jobCodeExp = QRegularExpression()
        self.jobCodeExp.setPattern(exp)
        self.jobCodeValidator = QRegularExpressionValidator(self.jobCodeExp, self.jobCodeComboBox)
        self.jobCodeComboBox.setValidator(self.jobCodeValidator)

        if not on_download:
            self.jobCodeComboBox.clearEditText()

        if self.prefs.job_code_sort_key == 0:
            if self.prefs.job_code_sort_order == 0:
                self.jobCodeComboBox.setInsertPolicy(QComboBox.InsertAtTop)
            else:
                self.jobCodeComboBox.setInsertPolicy(QComboBox.InsertAtBottom)
        else:
            self.jobCodeComboBox.setInsertPolicy(QComboBox.InsertAlphabetically)

        icon = QIcon(':/rapid-photo-downloader.svg').pixmap(standardIconSize())
        iconLabel = QLabel()
        iconLabel.setPixmap(icon)
        iconLabel.setAlignment(Qt.AlignTop|Qt.AlignLeft)
        iconLabel.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)

        jobCodeLabel = QLabel(_('&Job Code:'))
        jobCodeLabel.setBuddy(self.jobCodeComboBox)

        if on_download or not no_selection_made:
            self.rememberCheckBox = QCheckBox(_("&Remember this Job Code"))
            self.rememberCheckBox.setChecked(parent.prefs.remember_job_code)

        buttonBox = QDialogButtonBox(QDialogButtonBox.Ok| QDialogButtonBox.Cancel)
        translateDialogBoxButtons(buttonBox)

        grid = QGridLayout()
        grid.addWidget(iconLabel, 0, 0, 4, 1)
        grid.addWidget(instructionLabel, 0, 1, 1, 2)
        grid.addWidget(jobCodeLabel, 1, 1)
        grid.addWidget(self.jobCodeComboBox, 1, 2)

        if hasattr(self, 'rememberCheckBox'):
            grid.addWidget(self.rememberCheckBox, 2, 1, 1, 2)
            grid.addWidget(buttonBox, 3, 0, 1, 3)
        else:
            grid.addWidget(buttonBox, 2, 0, 1, 3)

        grid.setColumnStretch(2, 1)
        self.setLayout(grid)
        self.setWindowTitle(title)

        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

    @pyqtSlot()
    def accept(self) -> None:
        self.job_code = self.jobCodeComboBox.currentText()
        if hasattr(self, 'rememberCheckBox'):
            self.remember = self.rememberCheckBox.isChecked()
            self.rapidApp.prefs.remember_job_code = self.remember
        else:
            self.remember = True
        super().accept()


class JobCodeOptionsWidget(QFramedWidget):
    """
    Display and allow editing of Job Codes.
    """

    def __init__(self, prefs: Preferences, rapidApp, parent) -> None:
        super().__init__(parent)

        self.rapidApp = rapidApp
        self.prefs = prefs

        self.setBackgroundRole(QPalette.Base)
        self.setAutoFillBackground(True)

        self.file_selected = False
        self.prompting_for_job_code = False

        jobCodeLayout = QGridLayout()
        layout = QVBoxLayout()
        layout.addLayout(jobCodeLayout)
        self.setLayout(layout)

        self.messageWidget = MessageWidget((
            _('Select photos and videos to be able to apply a new or existing Job Code to them.'),
            _('The new Job Code will be applied to all selected photos and/or videos.'),
            _(
                'Click the Apply button to apply the current Job Code to all selected '
                'photos and/or videos. You can also simply double click the Job Code.'
            ),
            _(
                'Removing a Job Code removes it only from the list of saved Job Codes, '
                'not from any photos or videos that it may have been applied to.'
            ),
            _(
                'If you want to use Job Codes, configure file renaming or destination subfolder '
                'names to use them.')
        ))

        self.setDefaultMessage()

        self.sortCombo = ChevronCombo(in_panel=True)
        self.sortCombo.addItem(_("Last Used"), JobCodeSort.last_used)
        self.sortCombo.addItem(_("Job Code"), JobCodeSort.code)
        if self._sort_index_valid(self.prefs.job_code_sort_key):
            self.sortCombo.setCurrentIndex(self.prefs.job_code_sort_key)
        self.sortCombo.currentIndexChanged.connect(self.sortComboChanged)
        self.sortLabel= self.sortCombo.makeLabel(_("Job Code Sort:"))

        self.sortOrder = ChevronCombo(in_panel=True)
        self.sortOrder.addItem(_("Ascending"), Qt.AscendingOrder)
        self.sortOrder.addItem(_("Descending"), Qt.DescendingOrder)
        if self._sort_index_valid(self.prefs.job_code_sort_order):
            self.sortOrder.setCurrentIndex(self.prefs.job_code_sort_order)
        self.sortOrder.currentIndexChanged.connect(self.sortOrderChanged)

        font = self.font()  # type: QFont
        font.setPointSize(font.pointSize() - 2)
        for widget in (self.sortLabel, self.sortCombo, self.sortOrder):
            widget.setFont(font)

        self.newButton = MessageButton(_("&New..."))
        self.newButton.isActive.connect(self.newButtonActive)
        self.newButton.isInactive.connect(self.setDefaultMessage)
        self.newButton.clicked.connect(self.newButtonClicked)
        self.applyButton = MessageButton(_("&Apply"))
        self.applyButton.isActive.connect(self.applyButtonActive)
        self.applyButton.isInactive.connect(self.setDefaultMessage)
        self.applyButton.clicked.connect(self.applyButtonClicked)
        self.removeButton = MessageButton(_("&Remove"))
        self.removeButton.isActive.connect(self.removeButtonActive)
        self.removeButton.isInactive.connect(self.setDefaultMessage)
        self.removeButton.clicked.connect(self.removeButtonClicked)
        self.removeAllButton = MessageButton(_("Remove All"))
        self.removeAllButton.isActive.connect(self.removeButtonActive)
        self.removeAllButton.isInactive.connect(self.setDefaultMessage)
        self.removeAllButton.clicked.connect(self.removeAllButtonClicked)

        self.jobCodesWidget = QNarrowListWidget()
        self.jobCodesWidget.currentRowChanged.connect(self.rowChanged)
        self.jobCodesWidget.itemDoubleClicked.connect(self.rowDoubleClicked)
        self.jobCodesWidget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.jobCodesWidget.setSizePolicy(
            QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding
        )

        if self.prefs.list_not_empty('job_codes'):
            self._insertJobCodes(job_code=self.prefs.job_codes[0], clear=False)

        sortLayout = QHBoxLayout()
        sortLayout.addWidget(self.sortLabel)
        sortLayout.addWidget(self.sortCombo)
        sortLayout.addWidget(self.sortOrder)
        sortLayout.addStretch()

        jobCodeLayout.addWidget(self.jobCodesWidget, 0, 0, 1, 2)
        jobCodeLayout.addLayout(sortLayout, 1, 0, 1, 2)
        jobCodeLayout.addWidget(self.messageWidget, 2, 0, 1, 2)
        jobCodeLayout.addWidget(self.newButton, 3, 0, 1, 1)
        jobCodeLayout.addWidget(self.applyButton, 3, 1, 1, 1)
        jobCodeLayout.addWidget(self.removeButton, 4, 0, 1, 1)
        jobCodeLayout.addWidget(self.removeAllButton, 4, 1, 1, 1)

        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Expanding)

        self.setWidgetStates()

    def _sort_index_valid(self, index: int) -> bool:
        return index in (0, 1)

    def _jobCodes(self) -> List[str]:
        """
        :return: list of job codes sorted according to user-specified
         criteria
        """
        reverse = self.sortOrder.currentIndex() == 1
        if self.sortCombo.currentIndex() == 1:
            return sorted(self.prefs.job_codes, key=str.lower, reverse=reverse)
        if reverse:
            return list(reversed(self.prefs.job_codes))
        return self.prefs.job_codes

    def _insertJobCodes(self, job_code: str=None, clear=True) -> None:
        """
        Insert job codes into list widget according to the sort order
        specified by the user.

        If no job codes exist, does nothing.

        Alternative to clearing the widget and using python to sort the
        list of job codes would be to implement __lt__ in QListWidgetItem,
        and turn on QListWidget sorting. The code as implemented strikes
        me as simpler.

        :param job_code: job_code to set current row to. If not specified,
         the current row is used.
        :param clear:
        :return:
        """
        if not self.prefs.list_not_empty('job_codes'):
            return

        if job_code is None:
            row = self.jobCodesWidget.currentRow()
            if row >= 0:
                job_code = self.jobCodesWidget.item(row).text()

        if clear:
            self.jobCodesWidget.clear()

        logging.debug("Inserting %s job codes into job code widget", len(self.prefs.job_codes))
        job_codes = self._jobCodes()
        self.jobCodesWidget.insertItems(0, job_codes)

        if job_code is not None:
            self.jobCodesWidget.setCurrentRow(job_codes.index(job_code))
        else:
            self.jobCodesWidget.setCurrentRow(0)

    @pyqtSlot(int)
    def sortComboChanged(self, index: int) -> None:
        if index >= 0:
            self._insertJobCodes()
            self.prefs.job_code_sort_key = index

    @pyqtSlot(int)
    def sortOrderChanged(self, index: int) -> None:
        if index >= 0:
            self._insertJobCodes()
            self.prefs.job_code_sort_order = index

    @pyqtSlot()
    def newButtonActive(self) -> None:
        if self.prefs.any_pref_uses_job_code():
            if self.file_selected:
                self.messageWidget.setCurrentIndex(2)
            else:
                self.messageWidget.setCurrentIndex(1)

    @pyqtSlot()
    def applyButtonActive(self) -> None:
        if self.prefs.any_pref_uses_job_code():
            if self.file_selected:
                self.messageWidget.setCurrentIndex(3)
            else:
                self.messageWidget.setCurrentIndex(1)

    @pyqtSlot()
    def removeButtonActive(self) -> None:
        if self.prefs.any_pref_uses_job_code():
            self.messageWidget.setCurrentIndex(4)

    @pyqtSlot()
    def setDefaultMessage(self) -> None:
        if self.prefs.any_pref_uses_job_code():
            if not self.file_selected:
                self.messageWidget.setCurrentIndex(1)
            else:
                self.messageWidget.setCurrentIndex(0)
        else:
            self.messageWidget.setCurrentIndex(5)

    @pyqtSlot(int)
    def rowChanged(self, row: int) -> None:
        self.setWidgetStates()

    @pyqtSlot(QListWidgetItem)
    def rowDoubleClicked(self, item: QListWidgetItem) -> None:
        if self.file_selected:
            assert self.applyButton.isEnabled()
            self.applyButtonClicked()

    @pyqtSlot()
    def setWidgetStates(self) -> None:
        """
        Set buttons enable or disable depending on selections, and updates
        the message widget contents.
        """

        job_code_selected = self.jobCodesWidget.currentRow() >= 0
        self.file_selected = self.rapidApp.anyFilesSelected()

        self.newButton.setEnabled(True)
        self.applyButton.setEnabled(job_code_selected and self.file_selected)
        self.removeButton.setEnabled(job_code_selected)
        self.removeAllButton.setEnabled(self.prefs.list_not_empty('job_codes'))
        self.setDefaultMessage()

    @pyqtSlot()
    def applyButtonClicked(self) -> None:
        row = self.jobCodesWidget.currentRow()
        if row < 0:
            logging.error(
                "Did not expect Apply Job Code button to be enabled when no Job Code is selected."
            )
            return

        try:
            job_code = self.jobCodesWidget.item(row).text()
        except:
            logging.exception(
                "Job Code did not exist when obtaining its value from the list widget"
            )
            return

        self.rapidApp.applyJobCode(job_code=job_code)

        try:
            self.prefs.del_list_value(key='job_codes', value=job_code)
        except KeyError:
            logging.exception(
                "Attempted to delete non existent value %s from Job Codes while in process of "
                "moving it to the front of the list", job_code
            )
        self.prefs.add_list_value(key='job_codes', value=job_code)

        if self.sortCombo.currentIndex() != 1:
            self._insertJobCodes(job_code=job_code)

    @pyqtSlot()
    def removeButtonClicked(self) -> None:
        row = self.jobCodesWidget.currentRow()
        item = self.jobCodesWidget.takeItem(row)  # type: QListWidgetItem
        try:
            self.prefs.del_list_value(key='job_codes', value=item.text())
        except KeyError:
            logging.exception(
                "Attempted to delete non existent value %s from Job Codes", item.text()
            )

    @pyqtSlot()
    def removeAllButtonClicked(self) -> None:
        message = _('Do you really want to remove all the Job Codes?')
        msgBox = standardMessageBox(
            parent=self, title=_('Remove all Job Codes'), message=message, rich_text=False,
            standardButtons=QMessageBox.Yes | QMessageBox.No,
        )
        if msgBox.exec() == QMessageBox.Yes:
            # Must clear the job codes before adjusting the qlistwidget,
            # or else the Remove All button will not be disabled.
            self.prefs.job_codes = ['']
            self.jobCodesWidget.clear()

    @pyqtSlot()
    def newButtonClicked(self) -> None:
        self.getJobCode(on_download=False)

    def getJobCode(self, on_download: bool) -> bool:
        if not self.prompting_for_job_code:
            logging.debug("Prompting for job code")
            self.prompting_for_job_code = True
            dialog = JobCodeDialog(
                self.rapidApp, on_download=on_download, job_codes=self._jobCodes()
            )
            if dialog.exec():
                self.prompting_for_job_code = False
                logging.debug("Job code entered / selected")
                job_code = dialog.job_code
                if job_code:
                    if dialog.remember:
                        # If the job code is already in the
                        # preference list, delete it
                        job_codes = self.rapidApp.prefs.job_codes.copy()
                        while job_code in job_codes:
                            job_codes.remove(job_code)
                        # Add the just chosen / entered Job Code to the front
                        self.rapidApp.prefs.job_codes = [job_code] + job_codes
                        self._insertJobCodes(job_code=job_code)
                    if not on_download:
                        self.rapidApp.applyJobCode(job_code=job_code)
                    else:
                        self.rapidApp.thumbnailModel.assignJobCodesToMarkedFilesWithNoJobCode(
                            job_code=job_code
                        )
                    return True
            else:
                self.prompting_for_job_code = False
                logging.debug("No job code entered or selected")
        else:
            logging.debug("Not prompting for job code, because already doing so")
        return False


class JobCodePanel(QScrollArea):
    """
    JobCode preferences widget
    """

    def __init__(self,  parent) -> None:
        super().__init__(parent)
        if parent is not None:
            self.rapidApp = parent
            self.prefs = self.rapidApp.prefs
        else:
            self.prefs = None

        self.setFrameShape(QFrame.NoFrame)

        self.jobCodePanel = QPanelView(
            label=_('Job Codes'),
            headerColor=QColor(ThumbnailBackgroundName),
            headerFontColor=QColor(Qt.white)
        )

        self.jobCodeOptions = JobCodeOptionsWidget(
            prefs=self.prefs, rapidApp=self.rapidApp, parent=self
        )
        self.jobCodePanel.addWidget(self.jobCodeOptions)

        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        widget.setLayout(layout)
        layout.addWidget(self.jobCodePanel)
        self.setWidget(widget)
        self.setWidgetResizable(True)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        if parent is not None:
            self.rapidApp.thumbnailView.selectionModel().selectionChanged.connect(
                self.jobCodeOptions.setWidgetStates
            )
            self.rapidApp.thumbnailModel.selectionReset.connect(self.jobCodeOptions.setWidgetStates)

    def needToPromptForJobCode(self) -> bool:
        return self.prefs.any_pref_uses_job_code() and self.rapidApp.thumbnailModel.jobCodeNeeded()

    def getJobCodeBeforeDownload(self) -> bool:
        """
        :return: True if job code was entered and applied
        """
        return self.jobCodeOptions.getJobCode(on_download=True)

    def updateDefaultMessage(self) -> None:
        self.jobCodeOptions.setDefaultMessage()
