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
Show 'Did you know?' dialog at start up
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2017, Damon Lynch"

from PyQt5.QtCore import pyqtSlot, QSize, Qt, QSettings
from PyQt5.QtGui import (
    QPixmap, QIcon, QFontMetrics, QFont, QCloseEvent, QShowEvent, QPalette, QTextCursor, QColor
)
from PyQt5.QtWidgets import (
    QDialog, QCheckBox, QLabel, QVBoxLayout, QPushButton, QHBoxLayout, QApplication,
    QDialogButtonBox, QTextEdit
)

from gettext import gettext as _

import raphodo.qrc_resources as qrc_resources
from raphodo.preferences import Preferences

tips = (
    (
        _(
            "Click on a file's checkbox to mark or unmark it for download."
        ),
        'marksingle.png',
    ),
    (
        _(
            "Files that have already been downloaded are remembered. You can still "
            "mark previously downloaded files to download again, but they are "
            "unchecked by default, and their thumbnails are dimmed so you can "
            "differentiate them from files that are yet to be downloaded."
        ),
        'previouslydownloaded.png'
    ),
    (
        _(
            "If more than one file is selected, they'll all take the mark of the file whose "
            "checkbox was clicked, regardless of their existing checkmark."
        ),
        'markmany.png'
    ),
    (
        _(
            "Click on a device's checkbox to quickly mark or unmark all its files for "
            "downloading."
        ),
        'markall.png'
    ),
    (
        _(
            "You can simultaneously download from multiple cameras, smartphones, memory cards, "
            "and hard drives&mdash;as many devices as your computer can handle at one time."
        ),
        'multipledevices.png'
    ),
    (
        _(
            "The Timeline groups photos and videos based on how much time elapsed between "
            "consecutive shots. Use it to identify photos and videos taken at different periods "
            "in a single day or over consecutive days."
        ),
        'timeline.png',
        _(
            "The Timeline's slider adjusts the time elapsed between consecutive shots that is "
            "used to build the Timeline."
        ),
        'timelineadjust.png'
    ),
    (
        _(
            "To view photos and videos for a particular time range, use the mouse (optionally in "
            "combination with the <tt>Shift</tt> or <tt>Ctrl</tt> keys) to select time periods. "
            "When a time range is selected, the Timeline button on the left side of the main "
            "window will be highlighted."
        ),
        'timelineselect.png',
        _(
            "A download always includes all files that are checked for download, including those "
            "that are not currently displayed because the Timeline is being used."
        )
    ),

    (
        _(
            "You can hide or display the download sources by clicking on the name of "
            "the device you're downloading from at the top left of the program window."
        ),
        'deviceshidden.png'
    ),
    (
      _(
          """
          Thumbnails can be sorted using a variety of criteria:
<ol>
<li><i>Modification Time:</i> when the file was last modified, according to its metadata (where 
 available) or according to the filesystem (as a fallback).</li>
<li><i>Checked State:</i> whether the file is marked for download.</li>
<li><i>Filename:</i> the full filename, including extension.</li>
<li><i>Extension:</i> the filename's extension. You can use this to group jpeg and raw images, for 
instance.</li>
<li><i>File Type:</i> photo or video.</li>
<li><i>Device:</i> name of the device the photos and videos are being downloaded from.</li>
</ol> """
        ),
        'thumbnailsort.png'
    ),
    (
        _(
            "One of Rapid Photo Downloader's most useful features is its ability to automatically "
            "generate download subfolders and rename files as it downloads, using a scheme of your "
            "choosing."
        ),
        'downloadwhereandrename.png',
        _(
            "To specify where you want your files downloaded and how you want them named, open the "
            "appropriate panel on the right-side of the application window: "
            "<b>Destination</b>, <b>Rename</b>, or <b>Job Code</b>."
        ),
    ),
    (
        _(
            """
When thinking about your download directory structure, keep in mind two different types
of directory:
<ol>
<li>The <b>destination folder</b>, e.g. &quot;Pictures&quot;, &quot;Photos&quot;, or
&quot;Videos&quot;. This directory should already exist on your computer.</li>
<li>The <b>download subfolders</b>, which are directories that will be automatically generated 
by Rapid Photo Downloader. They need not already exist on your computer, but it's okay if they do.
They will be generated under the destination folder.</li>
</ol>
            """
        ),
        'defaultdownloaddirectory.png',
        _(
            """
You can download photos and videos to the same destination folder, or specify a different 
destination folder for each. The same applies to the download subfolders for photos and 
videos&mdash;download photos and videos to the same subfolders, or use a different scheme for each 
type.            
            """
        )
    ),
    (
        _(
            "Automatically generated download subfolders can contain further automatically "
            "generated subfolders if need be. For example, a common scheme is to create a year "
            "subfolder and then a series of year-month-day subfolders within it."
        ),
        'downloadsubfolders.png',
        _(
            """
This illustration demonstrates several useful attributes:
<ol>
<li>The destination folder is in this instance &quot;Pictures&quot;. The name of the destination 
folder is 
    displayed in the grey bar directly above the tree, with a folder icon to its left and a gear 
    icon to its far right.</li>
<li>The destination folder tree shows the download subfolders already on your computer (those in 
    a regular, non-italicized font), and the subfolders that will be created during the download 
    (those whose names are italicized).</li>
<li>The folder tree also shows into which subfolders the files will be downloaded (those colored 
    black).</li>
</ol>
            """
        )
    ),
    (
        _(
            """
Download subfolder names are typically generated using some or all of the following elements:
<ol>
<li><b>File metadata</b>, very often including the date the photo or video was created, but might 
also 
include the camera model name, camera serial number, or file extension e.g. JPG or CR2. Naming 
subfolders with the year, followed by the month and finally the day in numeric format makes 
it easy to keep them sorted in a file manager.</li>
<li>A <b>Job Code</b>, which is free text you specify at the time the download occurs, such as the
name of an event or location.</li>
<li><b>Text</b> which you want to appear every time, such as a hyphen or a space.</li>
</ol>
            """
        ),
    ),
    (
        _(
            """
To automatically create download subfolders as you download, 
you can use one of Rapid Photo Downloader's built-in presets, or create a custom preset. Click on 
the gear icon to bring up a drop-down menu:            
            """
        ),
        'subfoldermenu.png',
        _(
            """
Using the drop-down menu, select a built-in preset or click on <b>Custom</b> to configure your own 
scheme. You create your own schemes using the Photo or Video Subfolder Generation Editor:             
            """
        ),
        'subfoldergeneration.png',

    ),
    (
        _(
            "It's easy to download raw images into one folder, and jpeg images into another. Simply "
            "use the <b>Filename Extension</b> as part of your download subfolder generation "
            "scheme:"
        ),
        'subfoldergenerationext.png',
        _('This illustration shows a saved custom preset named &quot;My custom preset&quot;.'),
    )
)


# To add:
# Ignoring Devices
# Don't access camera from another program
# The Download Directory Structure
# Designing a Good Download Directory Structure
# Using Presets to Configure Directory Structure Schemes
# Photo or Video Subfolder Generation Editor
# JPG vs raw
# Renaming Files
# Sequence numbers
# Sequence Number Options - time start
# Synchronize RAW + JPEG
# Backups
# Program Caches explanation - Thumbnail Cache and Program Performance
# Device Scanning prefs
# Ignored Paths
# Automation
# Error Handling Preferences
# Miscellaneous Preferences
# Command Line Options


class Tips:
    def __getitem__(self, item) -> str:
        if 0 > item >= len(tips):
            item = 0
        tip = tips[item]
        text = ''
        for idx, value in enumerate(tip):
            if idx % 2 == 0:
                text = '{}<p>{}</p><p></p>'.format(text, value)
            else:
                text = '{}<img src=":/tips/{}">'.format(text, value)
        return text

    def __len__(self):
        return len(tips)


class DidYouKnowDialog(QDialog):

    def __init__(self, prefs: Preferences, parent=None) -> None:

        super().__init__(parent)
        self.rapidApp = parent
        self.prefs = prefs

        self.setWindowTitle(_("Tip of the Day"))

        titleFont = QFont()
        titleFont.setPointSize(titleFont.pointSize() + 3)
        pixsize = int(QFontMetrics(QFont()).height() * 1.75)

        title = QLabel(_('Did you know...?'))
        title.setFont(titleFont)
        pixmap = QIcon(':/did-you-know.svg').pixmap(QSize(pixsize, pixsize))  # type: QPixmap

        icon = QLabel()
        icon.setPixmap(pixmap)
        titleLayout = QHBoxLayout()
        titleLayout.addWidget(icon)
        titleLayout.addWidget(title)
        titleLayout.addStretch()

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setViewportMargins(10, 10, 10, 10)
        self.text.setStyleSheet("QTextEdit { background: palette(base); }")

        self.tips = Tips()

        self.showTips = QCheckBox(_('Show Tips on Startup'))
        self.showTips.setChecked(self.prefs.did_you_know_on_startup)
        self.showTips.stateChanged.connect(self.showTipsChanged)

        self.nextButton = QPushButton(_('&Next'))
        self.previousButton = QPushButton(_('&Previous'))

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.addButton(self.previousButton, QDialogButtonBox.ActionRole)
        buttons.addButton(self.nextButton, QDialogButtonBox.ActionRole)
        self.previousButton.clicked.connect(self.previousButtonClicked)
        self.nextButton.clicked.connect(self.nextButtonClicked)
        buttons.rejected.connect(self.close)

        layout = QVBoxLayout()
        self.setLayout(layout)

        layout.addLayout(titleLayout)
        layout.addWidget(self.text)
        layout.addWidget(self.showTips)
        layout.addWidget(buttons)

        settings = QSettings()
        settings.beginGroup("DidYouKnowWindow")

        default_width = 570
        default_height = 350

        size = settings.value("windowSize", QSize(default_width, default_height))

        settings.endGroup()
        self.resize(size)

        self.showTip()

    def incrementTip(self) -> None:
        if self.prefs.did_you_know_index + 1 == len(self.tips):
            self.prefs.did_you_know_index = 0
        else:
            self.prefs.did_you_know_index = self.prefs.did_you_know_index + 1

    def decrementTip(self) -> None:
        if self.prefs.did_you_know_index == 0:
            self.prefs.did_you_know_index = len(self.tips) - 1
        else:
            self.prefs.did_you_know_index = self.prefs.did_you_know_index - 1

    def showTip(self) -> None:
        self.text.clear()
        self.text.append(self.tips[self.prefs.did_you_know_index])
        self.text.moveCursor(QTextCursor.Start)

    def showEvent(self, event: QShowEvent) -> None:
        self.nextButton.setDefault(True)
        self.nextButton.setFocus(Qt.OtherFocusReason)
        event.accept()

    @pyqtSlot(int)
    def showTipsChanged(self, state: int) -> None:
        self.prefs.did_you_know_on_startup = state == Qt.Checked

    @pyqtSlot()
    def nextButtonClicked(self) -> None:
        self.incrementTip()
        self.showTip()

    @pyqtSlot()
    def previousButtonClicked(self) -> None:
        self.decrementTip()
        self.showTip()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.incrementTip()

        settings = QSettings()
        settings.beginGroup("DidYouKnowWindow")
        settings.setValue("windowSize", self.size())
        settings.endGroup()
        event.accept()



if __name__ == '__main__':

    # Application development test code:

    app = QApplication([])

    app.setOrganizationName("Rapid Photo Downloader")
    app.setOrganizationDomain("damonlynch.net")
    app.setApplicationName("Rapid Photo Downloader")

    prefs = Preferences()

    dialog = DidYouKnowDialog(prefs=prefs)
    dialog.show()
    app.exec_()
