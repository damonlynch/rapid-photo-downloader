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


from PyQt5.QtCore import pyqtSlot, QSize, Qt, QSettings, QUrl
from PyQt5.QtGui import (
    QPixmap, QIcon, QFontMetrics, QFont, QCloseEvent, QShowEvent, QTextCursor,
)
from PyQt5.QtWidgets import (
    QDialog, QCheckBox, QLabel, QVBoxLayout, QPushButton, QHBoxLayout, QApplication,
    QDialogButtonBox, QTextBrowser
)

from gettext import gettext as _

import raphodo.qrc_resources as qrc_resources
from raphodo.preferences import Preferences
from raphodo.viewutils import translateButtons

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
            "checkbox was clicked, regardless of whether they previously had a "
            "checkmark or not."
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
            "After a download finishes, an icon replaces the thumbnail's checkbox. The icon's "
            "color indicates whether the download was successful (green), had file renaming "
            "problems (yellow/orange), or failed (red)."
        ),
        'downloaded.png'
    ),
    (
        _(
            """
            In case of any problems, a red icon will appear at the bottom of the window
            indicating how many error reports there are. Clicking on it opens the Error Report 
            window.
            """
        ),
        'errorreporticon.png',
        _(
            """
            The Error Report window lists any problems encountered before, during or after the 
            download. An orange triangle represents a warning, a red circle indicates a failure, 
            and a black circle indicates more serious failures. You can click on the hyperlinks to 
            open its file or device in a file manager. You can also search the reports using the 
            search box in the lower left of the Error Report window.
            """
        ),
        'errorreport.png',
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
            "The <b>Timeline</b> groups photos and videos based on how much "
            "time elapsed between "
            "consecutive shots. Use it to identify photos and videos taken at different periods "
            "in a single day or over consecutive days."
        ),
        'timeline.png',
        _(
            """
<p>In the illustration above, the first row of the Timeline is black because all the files on 
that date had been previously downloaded.</p>
<p>The Timeline's slider adjusts the time elapsed between consecutive shots that is used to build 
the Timeline:</p>
            """
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
<li><b>Modification Time:</b> when the file was last modified, according to its metadata (where 
 available) or according to the filesystem (as a fallback).</li>
<li><b>Checked State:</b> whether the file is marked for download.</li>
<li><b>Filename:</b> the full filename, including extension.</li>
<li><b>Extension:</b> the filename's extension. You can use this to group jpeg and raw images, for 
instance.</li>
<li><b>File Type:</b> photo or video.</li>
<li><b>Device:</b> name of the device the photos and videos are being downloaded from.</li>
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
&quot;Videos&quot;. This directory should already exist on your computer. In the illustration 
below, the destination folders are &quot;Pictures&quot; and &quot;Videos&quot;. The
name of the destination folder is displayed in the grey bar directly above the folder tree, 
with a folder icon to its left and a gear icon to its far right.</li>
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
            "generated subfolders if need be. A common scheme is to create a year "
            "subfolder and then a series of year-month-day subfolders within it."
        ),
        'downloadsubfolders.png',

    ),
    (
        _(
            """
Whenever possible, the program previews the download subfolders of photos and videos to download:
<ol>
<li>The destination folder tree shows the download subfolders already on your computer (those in 
    a regular, non-italicized font), and the subfolders that will be created during the download 
    (those whose names are italicized).</li>
<li>The folder tree also shows into which subfolders the files will be downloaded (those colored 
    black).</li>
</ol>
            """
        ),
        'downloadsubfolders.png',
    ),
    (
        _(
            """
Download subfolder names are typically generated using some or all of the following elements:
<ol>
<li><b>File metadata</b>, very often including the date the photo or video was created, but might 
also 
include the camera model name, camera serial number, or file extension e.g. JPG or CR2.</li>
<li>A <b>Job Code</b>, which is free text you specify at the time the download occurs, such as the
name of an event or location.</li>
<li><b>Text</b> which you want to appear every time, such as a hyphen or a space.</li>
</ol>
Naming subfolders with the year, followed by the month and finally the day in numeric format makes 
it easy to keep them sorted in a file manager, which is why it's the default option:
            """
        ),
        'downloadsubfolders.png',
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
            "It's easy to download raw images into one folder, and jpeg images into another. "
            "Simply use the <b>Filename Extension</b> as part of your download subfolder "
            "generation scheme:"
        ),
        'subfoldergenerationext.png',
        _('This illustration shows a saved custom preset named &quot;My custom preset&quot;.'),
    ),
    (
        _(
            """
You do not have to create nested download subfolders. This illustration shows 
the generation of download subfolders that contain only the date the photos were taken and a 
Job Code:
            """
        ),
        'subfoldergeneration.png'
    ),
    (
        _(
            """
Although there are many built-in date/time naming options, you may find that you 
need something different. It's no problem to create your own. You can combine date/time choices to
generate new combinations. Supposing you wanted a date format that combines year (YYYY), a hyphen, 
and month (MM) to form YYYY-MM. You can create it like this (note the red circle around the hyphen):
            """
        ),
        'customdate.png',
        _(
            """
Read more about all the ways you can generate download subfolder names and file names in the <a 
href="http://damonlynch.net/rapid/documentation/#renamedateandtime">online documentation</a>.
            """
        )
    ),
    (
        _(
            """
<b>Job Codes</b> let you easily enter text that describes sets of photos and videos. You can 
use them in subfolder and file names. In this illustration, some files have had the Job Code
&quot;Street&quot; applied to them, and the selected files are about to get the Job Code 
&quot;Green Bazaar&quot;: 
"""
        ),
        'jobcodes.png',
        _(
            """
You can apply new or existing Job Codes before you start a download. If there are any 
files in the download that have not yet had a Job Code applied to them, you'll be prompted to enter 
a Job Code for them before the download begins.
            """
        )
    ),
    (
        _(
            "Look for hints to guide you when working with Job Codes:"
        ),
        'jobcodehint.png',
        _(
            "Hints will vary depending on the context, such as when the mouse is hovering over a "
            "button."
        )
    ),
    (
        _(
            """
When you give your photos and videos unique filenames, you'll never be confused as to 
which file is which. Using <b>sequence numbers</b> to make filenames unique is highly 
recommended!
            """
        ),
        'photoeditordefault.png',
        _(
            """
<p>Four types of sequence values are available to help you assign unique names to your photos and 
videos:
<ol>
<li><b>Downloads today</b>: tracks downloads completed during that day.</li>
<li><b>Stored number</b>: similar to Downloads today, but it is remembered from the last time the  
program was run.</li>
<li><b>Session number</b>: reset each time the program is run.</li>
<li><b>Sequence letter</b>: like session numbers, but uses letters.</li>
</ol></p>
<p>
Read more about sequence numbers in the <a 
href="http://damonlynch.net/rapid/documentation/#sequencenumbers">online documentation</a>.</p>
            """
        ),
    ),
    (
        _(
            """
The <b>Rename</b> panel allows you to configure file renaming. To rename your files, you can choose
from among existing renaming presets or define your own.              
            """
        ),
        'renameoptions.png',
        _(
            """
<p>The <b>Synchronize RAW + JPEG</b> option is useful if you use the RAW + JPEG feature on your 
camera and you use sequence numbers in your photo renaming. Enabling this option 
will cause the program to detect matching pairs of RAW and JPEG photos, and when they are detected,
the same sequence numbers will be applied to both photo names. Furthermore, sequences will be 
updated as if the photos were one.</p>
<p>
Read more about file renaming in the <a 
href="http://damonlynch.net/rapid/documentation/#rename">online documentation</a>.</p>
            """
        )
    ),
    (
        _(
            """
You can have your photos and videos backed up to multiple locations as they are downloaded, such as 
external hard drives or network shares. Backup devices can be automatically detected, or exact 
backup locations specified.
            """
        ),
        'backup.png',
        _(
            "In this example, the drive <b>photobackup</b> does not contain a folder named "
            "<tt>Videos</tt>, so videos will not be backed up to it."
        )
    ),
    (
        _(
            """
Several of the program's preferences can be set from the command line, including download 
sources, destinations, and backups. Additionally, settings can be reset to their 
default state, and caches and remembered files cleared.            
            """
        ) + _("You can also import program preferences from the older 0.4 version."),
        'commandline.png'
    ),
    (
        _(
            """
Rapid Photo Downloader deals with three types of cache:
<ol>
<li>A <b>thumbnail cache</b> whose sole purpose is to store thumbnails of files from your cameras, 
memory cards, and other devices.</li>
<li>A <b>temporary cache</b> of files downloaded from a camera, one for photos and another for 
videos. They are located in temporary subfolders in the download destination.</li>
<li>The <b>desktop's thumbnail cache</b>, in which Rapid Photo Downloader stores thumbnails of 
RAW and TIFF photos once they have been downloaded. File browsers like Gnome Files use this cache 
as well, meaning they too will display thumbnails for those files. 
</li>
</ol>
Read more about these caches and their effect on download performance in the <a 
href="http://damonlynch.net/rapid/documentation/#caches">online documentation</a>.
            """
        ),
    )
)


# To add, possibly:
# Ignoring Devices
# Don't access camera from another program
# Device Scanning prefs
# Ignored Paths
# Automation
# Error Handling Preferences
# Miscellaneous Preferences


class Tips:
    def __getitem__(self, item) -> str:
        if 0 > item >= len(tips):
            item = 0
        tip = tips[item]
        text = ''
        for idx, value in enumerate(tip):
            if idx % 2 == 0:
                if not value.startswith('<p>'):
                    text = '{}<p>{}</p><p></p>'.format(text, value)
                else:
                    text = '{}{}<p></p>'.format(text, value)
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

        self.setSizeGripEnabled(True)

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

        self.text = QTextBrowser()
        self.text.setOpenExternalLinks(True)
        self.text.setViewportMargins(10, 10, 10, 10)
        self.text.setStyleSheet("""
        QTextEdit { background: palette(base); }
        """)

        self.text.document().setDefaultStyleSheet(
            """
            b {color: grey;}
            tt {color: darkRed; font-weight: bold;}
            """
        )

        self.tips = Tips()

        self.showTips = QCheckBox(_('Show tips on startup'))
        self.showTips.setChecked(self.prefs.did_you_know_on_startup)
        self.showTips.stateChanged.connect(self.showTipsChanged)

        self.nextButton = QPushButton(_('&Next'))
        self.previousButton = QPushButton(_('&Previous'))

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        translateButtons(buttons)
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

    @pyqtSlot()
    def activate(self) -> None:
        self.showTip()
        self.setVisible(True)
        self.activateWindow()
        self.raise_()

    def reject(self) -> None:
        """
        Called when user hits escape key
        """

        self.saveSettings()
        if self.rapidApp is None:
            super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.saveSettings()
        if self.rapidApp is None:
            event.accept()
        else:
            event.ignore()
            self.hide()

    def saveSettings(self) -> None:
        self.incrementTip()
        settings = QSettings()
        settings.beginGroup("DidYouKnowWindow")
        settings.setValue("windowSize", self.size())
        settings.endGroup()


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
