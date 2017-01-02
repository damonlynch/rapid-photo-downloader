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
Display, edit and apply Job Codes.
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2017, Damon Lynch"

from typing import Optional, Dict, Tuple, Union
import logging
from gettext import gettext as _


from PyQt5.QtCore import (Qt, pyqtSlot, QTime)
from PyQt5.QtWidgets import (QWidget, QSizePolicy, QComboBox, QFormLayout,
                             QVBoxLayout, QLabel, QSpinBox, QTimeEdit, QCheckBox, QGroupBox,
                             QScrollArea, QFrame, QGridLayout)
from PyQt5.QtGui import (QColor, QPalette)


from raphodo.constants import (PresetPrefType, NameGenerationType,
                               ThumbnailBackgroundName, PresetClass)
from raphodo.viewutils import QFramedWidget
from raphodo.panelview import QPanelView
from raphodo.preferences import Preferences, DownloadsTodayTracker


class JobCodeOptionsWidget(QFramedWidget):
    """
    Display and allow editing of Job Codes.
    """

    def __init__(self, prefs: Preferences, parent) -> None:
        super().__init__(parent)

        self.prefs = prefs

        self.setBackgroundRole(QPalette.Base)
        self.setAutoFillBackground(True)

        jobcodeLayout = QGridLayout()
        layout = QVBoxLayout()
        layout.addLayout(jobcodeLayout)
        self.setLayout(layout)

        explanation = QLabel(_("A Job Code is text to help describe sets of photos and videos. "
                               "Job Codes can be used in subfolder and file names."))
        explanation.setWordWrap(True)

        explanation_not_done = QLabel(_("<i>This part of the user interface will be "
                                        "implemented in a forthcoming alpha release.</i>"))
        explanation_not_done.setWordWrap(True)


        jobcodeLayout.addWidget(explanation, 0, 0, 1, 4)
        jobcodeLayout.addWidget(explanation_not_done, 1, 0, 1, 4)

        layout.addStretch()

        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)


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

        self.backupOptionsPanel = QPanelView(label=_('Job Codes'),
                                       headerColor=QColor(ThumbnailBackgroundName),
                                       headerFontColor=QColor(Qt.white))

        self.backupOptions = JobCodeOptionsWidget(prefs=self.prefs, parent=self)
        self.backupOptionsPanel.addWidget(self.backupOptions)

        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        widget.setLayout(layout)
        layout.addWidget(self.backupOptionsPanel)
        self.setWidget(widget)
        self.setWidgetResizable(True)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)





