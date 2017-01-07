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
Handle Job Code entry.
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2015-2016, Damon Lynch"

from PyQt5.QtCore import pyqtSlot
from PyQt5.QtWidgets import QDialog, QLabel, QComboBox, QCheckBox, QDialogButtonBox, QGridLayout

from gettext import gettext as _

class JobCodeDialog(QDialog):
    def __init__(self, parent, job_codes: list) -> None:
        super().__init__(parent)
        self.rapidApp = parent # type: 'RapidWindow'
        instructionLabel = QLabel(_('Enter a new Job Code, or select a previous one'))
        self.jobCodeComboBox = QComboBox()
        self.jobCodeComboBox.addItems(job_codes)
        self.jobCodeComboBox.setEditable(True)
        self.jobCodeComboBox.setInsertPolicy(QComboBox.InsertAtTop)
        jobCodeLabel = QLabel(_('&Job Code:'))
        jobCodeLabel.setBuddy(self.jobCodeComboBox)
        self.rememberCheckBox = QCheckBox(_("&Remember this choice"))
        self.rememberCheckBox.setChecked(parent.prefs.remember_job_code)
        buttonBox = QDialogButtonBox(QDialogButtonBox.Ok|
                                     QDialogButtonBox.Cancel)
        grid = QGridLayout()
        grid.addWidget(instructionLabel, 0, 0, 1, 2)
        grid.addWidget(jobCodeLabel, 1, 0)
        grid.addWidget(self.jobCodeComboBox, 1, 1)
        grid.addWidget(self.rememberCheckBox, 2, 0, 1, 2)
        grid.addWidget(buttonBox, 3, 0, 1, 2)
        grid.setColumnStretch(1, 1)
        self.setLayout(grid)
        self.setWindowTitle(_('Rapid Photo Downloader'))

        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

    @pyqtSlot()
    def accept(self):
        self.job_code = self.jobCodeComboBox.currentText()
        self.remember = self.rememberCheckBox.isChecked()
        self.rapidApp.prefs.remember_job_code = self.remember
        super().accept()


class JobCode:
    def __init__(self, parent):
        self.rapidApp = parent
        self.job_code = ''
        self.prompting_for_job_code = False

    @property
    def need_job_code_for_naming(self):
        return self.rapidApp.prefs.any_pref_uses_job_code()

    def get_job_code(self):
        if not self.prompting_for_job_code:
            self.prompting_for_job_code = True
            dialog = JobCodeDialog(self.rapidApp,
                                   self.rapidApp.prefs.job_codes)
            if dialog.exec():
                self.prompting_for_job_code = False
                job_code = dialog.job_code
                if job_code:
                    if dialog.remember:
                        # If the job code is already in the
                        # preference list, move it to the front
                        job_codes = self.rapidApp.prefs.job_codes.copy()
                        while job_code in job_codes:
                            job_codes.remove(job_code)
                        # Add the just chosen Job Code to the front
                        self.rapidApp.prefs.job_codes = [job_code] + job_codes
                    self.job_code = job_code
                    self.rapidApp.startDownload()
            else:
                self.prompting_for_job_code = False

    def need_to_prompt_on_auto_start(self):
        return not self.job_code and self.need_job_code_for_naming

    def need_to_prompt(self):
        return self.need_job_code_for_naming and not self.prompting_for_job_code
