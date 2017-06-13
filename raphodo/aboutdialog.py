# Copyright (C) 2016-2017 Damon Lynch <damonlynch@gmail.com>

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
Display an About window
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2016-2017, Damon Lynch"

from gettext import gettext as _

from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QPixmap,  QFont

from PyQt5.QtWidgets import (QDialog, QLabel, QVBoxLayout, QDialogButtonBox, QSizePolicy,
                             QHBoxLayout, QStackedWidget, QWidget, QScrollArea, QPushButton)

import raphodo.qrc_resources
import raphodo.__about__ as __about__


class AboutDialog(QDialog):
    """
    Display an About window
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)

        self.setObjectName('AboutDialog')
        self.setStyleSheet('QDialog#AboutDialog {background-image: url(:/splashscreen.png);}')
        pixmap = QPixmap(':/splashscreen.png')
        self.setFixedSize(pixmap.size())

        # These values are derived from the splash screen image contents.
        # If the image changes, so should these
        white_box_height = 80
        title_bottom = 45
        left_margin = 16

        transparency = "rgba(0, 0, 0, 200)"

        # Standard About view

        msg = """Copyright &copy; 2007-2017 Damon Lynch.<br><br>
        <a href="http://www.damonlynch.net/rapid" %(link_style)s>
        www.damonlynch.net/rapid</a><br><br>
        This program comes with absolutely no warranty.<br>
        See the <a href="http://www.gnu.org/copyleft/gpl.html" %(link_style)s>GNU General
        Public License,
        version 3 or later</a> for details.
        """ % dict(link_style='style="color: white;"')

        details = QLabel(msg)

        style_sheet = """QLabel {
        color: white;
        background-color: %(transparency)s;
        margin-left: 0px;
        padding-left: %(left_margin)dpx;
        padding-top: 6px;
        padding-right: 6px;
        padding-bottom: 6px;
        }""" % dict(left_margin=left_margin, transparency=transparency)

        details.setStyleSheet(style_sheet)
        details.setOpenExternalLinks(True)
        details.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        font = self.font()  # type: QFont
        font_size = font.pointSize() - 2
        font.setPointSize(font_size)
        details.setFont(font)

        aboutLayout = QVBoxLayout()
        aboutLayout.setContentsMargins(0, 0, 0, 0)
        aboutLayout.addSpacing(150)
        detailsLayout = QHBoxLayout()
        detailsLayout.setContentsMargins(0, 0, 0, 0)
        detailsLayout.addWidget(details)
        detailsLayout.addStretch(10)
        aboutLayout.addLayout(detailsLayout)
        aboutLayout.addStretch(10)

        about = QWidget()
        about.setLayout(aboutLayout)

        # Credits view

        credits_text = """
        Copyright © 2007-2017 Damon Lynch.
        Portions copyright © 2008-2015 Canonical Ltd.
        Portions copyright © 2013 Bernard Baeyens.
        Portions copyright © 2012-2015 Jim Easterbrook.
        Portions copyright © 2012 Sven Marnach.

        Photo %(photolink)s copyright © 2014 Damon Lynch, all rights reserved.
        Camera icon courtesy %(artlink1)s.
        Video camera icon courtesy %(artlink2)s.
        Home icon courtesy %(artlink3)s.
        Speech bubble courtesy %(artlink4)s.
        Lightbulb icon courtesy %(artlink5)s.

        Translators:

        Anton Alyab'ev <subeditor@dolgopa.org>
        Lőrincz András <level.andrasnak@gmail.com>
        Michel Ange <michelange@wanadoo.fr>
        Tobias Bannert <tobannert@gmail.com>
        Adolfo Jayme Barrientos <fitoschido@gmail.com>
        Alain J. Baudrez <a.baudrez@gmail.com>
        Mohammed Belkacem <belkacem77@gmail.com>
        Kevin Brubeck Unhammer <unhammer@fsfe.org>
        Pavel Borecki <pavel.borecki@gmail.com>
        Bert <crinbert@yahoo.com>
        Martin Dahl Moe
        Marco de Freitas <marcodefreitas@gmail.com>
        Martin Egger <martin.egger@gmx.net>
        Tauno Erik <tauno.erik@gmail.com>
        Sergiy Gavrylov <sergiovana@bigmir.net>
        Emanuele Grande <caccolangrifata@gmail.com>
        Torben Gundtofte-Bruun <torben@g-b.dk>
        Мирослав Николић <miroslavnikolic@rocketmail.com>
        Joachim Johansson <joachim.j@gmail.com>
        Jean-Marc Lartigue <m.balthazar@orange.fr>
        Miroslav Matejaš <silverspace@ubuntu-hr.org>
        Nicolás M. Zahlut <nzahlut@live.com>
        Erik M
        Toni Lähdekorpi <toni@lygon.net>
        Jose Luis Navarro <jlnavarro111@gmail.com>
        Tomas Novak <kuvaly@seznam.cz>
        Abel O'Rian <abel.orian@gmail.com>
        Balazs Oveges <ovegesb@freemail.hu>
        Daniel Paessler <daniel@paessler.org>
        Miloš Popović <gpopac@gmail.com>
        Michal Predotka <mpredotka@googlemail.com>
        Ye Qing <allen19920930@gmail.com>
        Luca Reverberi <thereve@gmail.com>
        Mikko Ruohola <polarfox@polarfox.net>
        Ahmed Shubbar <ahmed.shubbar@gmail.com>
        Sergei Sedov <sedov@webmail.perm.ru>
        Marco Solari <marcosolari@gmail.com>
        Jose Luis Tirado <joseluis.tirado@gmail.com>
        Ilya Tsimokhin <ilya@tsimokhin.com>
        Ulf Urdén <ulf.urden@purplescout.com>
        Julien Valroff <julien@kirya.net>
        Dimitris Xenakis <dx@nkdx.gr>
        Aron Xu <happyaron.xu@gmail.com>
        Koji Yokota <yokota6@gmail.com>
        梁其学 <yalongbay@gmail.com>
        """

        for i, j in (('<', '&lt;'), ('>', '&gt;'), ('\n', '<br>\n')):
            credits_text = credits_text.replace(i, j)

        credits_text = credits_text % dict(
            photolink="""<a href="https://500px.com/photo/65727425/afghan-men-pulling-heavy-load-by
            -damon-lynch" style="color: white;">Afghan Men Pulling Heavy Load</a>""",
            artlink1='<a href="http://www.webalys.com" style="color: white;">Vincent Le Moign</a>',
            artlink2="""<a href="https://www.iconfinder.com/bluewolfski" style="color: white;">The
                 Pictographers</a>""",
            artlink3='<a href="https://www.iconfinder.com/Enesdal" style="color: white;">Enes'
                     ' Dal</a>',
            artlink4='<a href="http://www.iconsolid.com/" style="color: white;">Icons Solid</a>',
            artlink5='<a href="https://sellfy.com/designcoon" style="color: white;">Icon Coon</a>'
        )

        style_sheet = """QLabel {
        background-color: rgba(0, 0, 0, 0);
        color: white;
        padding-left: %(left_margin)dpx;
        padding-top: 6px;
        padding-right: 6px;
        padding-bottom: 6px;
        }""" % dict(left_margin=left_margin)

        creditsLabel = QLabel(credits_text)
        creditsLabel.setFont(font)
        creditsLabel.setStyleSheet(style_sheet)
        creditsLabel.setOpenExternalLinks(True)

        credits  = QScrollArea()
        credits.setWidget(creditsLabel)
        style_sheet = """QScrollArea {
        background-color: %(transparency)s;
        border: 0px;
        }
        """ % dict(transparency=transparency)
        credits.setStyleSheet(style_sheet)

        mainLayout = QVBoxLayout()

        self.stack = QStackedWidget()
        self.stack.addWidget(about)
        self.stack.addWidget(credits)
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        buttonBox = QDialogButtonBox()
        closeButton = buttonBox.addButton(QDialogButtonBox.Close)  # type: QPushButton
        self.creditsButton = buttonBox.addButton(_('Credits'), QDialogButtonBox.HelpRole)  # type: QPushButton
        self.creditsButton.setDefault(False)
        self.creditsButton.setCheckable(True)
        closeButton.setDefault(True)

        buttonLayout = QVBoxLayout()
        buttonLayout.addWidget(buttonBox)
        buttonLayout.setContentsMargins(left_margin, left_margin, left_margin, left_margin)

        mainLayout.setContentsMargins(0, 0, 0, 0)

        version = QLabel(__about__.__version__)
        version.setFixedHeight(white_box_height-title_bottom)

        style_sheet = """QLabel {
        padding-left: %(left_margin)dpx;
        }""" % dict(left_margin=left_margin)

        version.setStyleSheet(style_sheet)

        mainLayout.addSpacing(title_bottom)
        mainLayout.addWidget(version)
        mainLayout.addWidget(self.stack)
        mainLayout.addLayout(buttonLayout)

        self.setLayout(mainLayout)

        buttonBox.rejected.connect(self.reject)
        buttonBox.helpRequested.connect(self.showCredits)

        closeButton.setFocus()

    @pyqtSlot()
    def showCredits(self) -> None:
        if self.creditsButton.isChecked():
            self.stack.setCurrentIndex(1)
        else:
            self.stack.setCurrentIndex(0)


