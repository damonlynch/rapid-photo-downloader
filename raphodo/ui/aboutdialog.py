# Copyright (C) 2016-2022 Damon Lynch <damonlynch@gmail.com>

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

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2016-2022, Damon Lynch"

import re

from PyQt5.QtCore import Qt, pyqtSlot, QSize
from PyQt5.QtGui import QPixmap, QFont

from PyQt5.QtWidgets import (
    QDialog,
    QLabel,
    QVBoxLayout,
    QDialogButtonBox,
    QSizePolicy,
    QHBoxLayout,
    QStackedWidget,
    QWidget,
    QScrollArea,
    QPushButton,
)

import raphodo.__about__ as __about__
from raphodo.ui.viewutils import translateDialogBoxButtons


class AboutDialog(QDialog):
    """
    Display an About window
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)

        self.setObjectName("AboutDialog")
        self.setStyleSheet(
            "QDialog#AboutDialog {background-image: url(:/splashscreen.png);}"
        )
        pixmap = QPixmap(":/splashscreen.png")
        try:
            ratio = pixmap.devicePixelRatioF()
        except AttributeError:
            ratio = pixmap.devicePixelRatio()

        if ratio > 1.0:
            size = QSize(pixmap.width() / ratio, pixmap.height() / ratio)
        else:
            size = pixmap.size()

        self.setFixedSize(size)

        # These values are derived from the splash screen image contents.
        # If the image changes, so should these
        white_box_height = 80
        title_bottom = 45
        left_margin = 16

        transparency = "rgba(0, 0, 0, 130)"

        # Standard About view

        msg = """Copyright &copy; 2007-2022 Damon Lynch.<br><br>
        <a href="https://damonlynch.net/rapid" %(link_style)s>
        damonlynch.net/rapid</a><br><br>
        This program comes with absolutely no warranty.<br>
        See the <a href="http://www.gnu.org/copyleft/gpl.html" %(link_style)s>GNU 
        General Public License, version 3 or later</a> for details.
        """ % dict(
            link_style='style="color: white;"'
        )

        details = QLabel(msg)

        details_style_sheet = """QLabel {
        color: white;
        background-color: %(transparency)s;
        margin-left: 0px;
        padding-left: %(left_margin)dpx;
        padding-top: 6px;
        padding-right: 6px;
        padding-bottom: 6px;
        }""" % dict(
            left_margin=left_margin, transparency=transparency
        )

        details.setStyleSheet(details_style_sheet)
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
        Copyright © 2007-2022 Damon Lynch.
        Portions copyright © 2008-2015 Canonical Ltd.
        Portions copyright © 2013 Bernard Baeyens.
        Portions copyright © 2012-2015 Jim Easterbrook.
        Portions copyright © 2012 Sven Marnach.
        Portions copyright © 2015 Dmitry Shachnev.

        Photo %(photolink)s copyright © 2014-2018 Damon Lynch, all rights reserved.
        Camera icon courtesy %(artlink1)s.
        Video camera icon courtesy %(artlink2)s.
        Home icon courtesy %(artlink3)s.
        Speech bubble courtesy %(artlink4)s.
        Lightbulb icon courtesy %(artlink5)s.
        Double arrow icon courtesy %(artlink6)s.
        Clock icon courtesy %(artlink7)s.
        """

        credits_text = credits_text.replace("\n", "<br>\n")

        credits_text = credits_text % dict(
            photolink="""<a href="https://500px.com/photo/246096445/afghan-men-pulling-heavy-load-
            by-damon-lynch" style="color: white;">Afghan Men Pulling Heavy Load</a>""",
            artlink1='<a href="http://www.webalys.com" style="color: white;">Vincent Le Moign</a>',
            artlink2="""<a href="https://www.iconfinder.com/bluewolfski" style="color: white;">The
                 Pictographers</a>""",
            artlink3='<a href="https://www.iconfinder.com/Enesdal" style="color: white;">Enes'
            " Dal</a>",
            artlink4='<a href="http://www.iconsolid.com/" style="color: white;">Icons Solid</a>',
            artlink5='<a href="https://sellfy.com/designcoon" style="color: white;">Icon Coon</a>',
            artlink6='<a href="https://www.iconfinder.com/buninux" style="color: '
            'white;"> Dmitriy Bunin</a>',
            artlink7='<a href="https://www.flaticon.com/authors/pixel-perfect" style="color: '
            'white;">Pixel perfect</a>',
        )

        label_style_sheet = """QLabel {
        background-color: rgba(0, 0, 0, 0);
        color: white;
        padding-left: %(left_margin)dpx;
        padding-top: 6px;
        padding-right: 6px;
        padding-bottom: 6px;
        }""" % dict(
            left_margin=left_margin
        )

        creditsLabel = QLabel(credits_text)
        creditsLabel.setFont(font)
        creditsLabel.setStyleSheet(label_style_sheet)
        creditsLabel.setOpenExternalLinks(True)

        credits = QScrollArea()
        credits.setWidget(creditsLabel)
        scroll_area_style_sheet = """QScrollArea {
        background-color: %(transparency)s;
        border: 0px;
        }
        """ % dict(
            transparency=transparency
        )
        credits.setStyleSheet(scroll_area_style_sheet)

        # Translators view

        translators_text = """
        <b>Albanian</b>
        Algent Albrahimi <algent@protonmail.com>

        <b>Belarusian</b>
        Ilya Tsimokhin <ilya@tsimokhin.com>

        <b>Brazilian Portuguese</b>
        Ney Walens de Mesquita <walens@gmail.com>
        Rubens Stuginski Jr <rubens.stuginski@gmail.com>

        <b>Catalan</b>
        Adolfo Jayme Barrientos <fitoschido@gmail.com>

        <b>Czech</b>
        Pavel Borecki <pavel.borecki@gmail.com>

        <b>Danish</b>
        Torben Gundtofte-Bruun <torben@g-b.dk>

        <b>Dutch</b>
        Alain J. Baudrez <a.baudrez@gmail.com>

        <b>Estonian</b>
        Tauno Erik <tauno.erik@gmail.com>

        <b>Finnish</b>
        Mikko Ruohola <mikko@ruohola.org>

        <b>French</b>
        Jean-Marc Lartigue <m.balthazar@posteo.net>

        <b>Greek</b>
        Dimitris Xenakis <dx@nkdx.gr>

        <b>Hungarian</b>
        László <csola48@gmail.com>
        András Lőrincz <level.andrasnak@gmail.com>

        <b>Italian</b>
        Matteo Carotta <matteo.carotta@gmail.com>
        Milo Casagrande <milo.casagrande@gmail.com>

        <b>Japanese</b>
        Koji Yokota <yokota6@gmail.com>

        <b>Kabyle</b>
        Mohammed Belkacem <belkacem77@gmail.com>

        <b>Norwegian Bokmal</b>
        Harlad H <haarektrans@gmail.com>
        Rudolf Maurer <rudolf.maurer@googlemail.com>

        <b>Norwegian Nynorsk</b>
        Kevin Brubeck Unhammer <unhammer@fsfe.org>
        Harlad H <haarektrans@gmail.com>

        <b>Polish</b>
        Michal Predotka <mpredotka@googlemail.com>

        <b>Russian</b>
        Evgeny Kozlov <evgeny.kozlov.mailbox@gmail.com>

        <b>Serbian</b>
        Мирослав Николић <miroslavnikolic@rocketmail.com>

        <b>Slovak</b>
        Robert Valik <robert@valik.sk>

        <b>Spanish</b>
        Adolfo Jayme Barrientos <fitoschido@gmail.com>
        Jose Luis Tirado <joseluis.tirado@gmail.com>

        <b>Swedish</b>
        Joachim Johansson <joachim.j@gmail.com>

        <b>Turkish</b>
        Ilker Alp <ilkeryus@gmail.com>

        <b>Previous translators</b>
        Anton Alyab'ev <subeditor@dolgopa.org>
        Michel Ange <michelange@wanadoo.fr>
        Tobias Bannert <tobannert@gmail.com>
        Bert <crinbert@yahoo.com>
        Martin Dahl Moe
        Marco de Freitas <marcodefreitas@gmail.com>
        Martin Egger <martin.egger@gmx.net>
        Sergiy Gavrylov <sergiovana@bigmir.net>
        Emanuele Grande <caccolangrifata@gmail.com>
        Toni Lähdekorpi <toni@lygon.net>
        Miroslav Matejaš <silverspace@ubuntu-hr.org>
        Erik M
        Frederik Müller <spheniscus@freenet.de>
        Jose Luis Navarro <jlnavarro111@gmail.com>
        Tomas Novak <kuvaly@seznam.cz>
        Abel O'Rian <abel.orian@gmail.com>
        Balazs Oveges <ovegesb@freemail.hu>
        Daniel Paessler <daniel@paessler.org>
        Miloš Popović <gpopac@gmail.com>
        Ye Qing <allen19920930@gmail.com>
        Luca Reverberi <thereve@gmail.com>
        Ahmed Shubbar <ahmed.shubbar@gmail.com>
        Sergei Sedov <sedov@webmail.perm.ru>
        Marco Solari <marcosolari@gmail.com>
        Ulf Urdén <ulf.urden@purplescout.com>
        Julien Valroff <julien@kirya.net>
        Aron Xu <happyaron.xu@gmail.com>
        Nicolás M. Zahlut <nzahlut@live.com>
        梁其学 <yalongbay@gmail.com>
        """

        # Replace < and > in email addresses
        translators_text = re.sub(
            r"<(.+)@(.+)>", r"&lt;\1@\2&gt;", translators_text, flags=re.MULTILINE
        )
        translators_text = translators_text.replace("\n", "<br>\n")

        translatorsLabel = QLabel(translators_text)
        translatorsLabel.setFont(font)
        translatorsLabel.setStyleSheet(label_style_sheet)

        translators = QScrollArea()
        translators.setWidget(translatorsLabel)
        translators.setStyleSheet(scroll_area_style_sheet)

        mainLayout = QVBoxLayout()

        self.stack = QStackedWidget()
        self.stack.addWidget(about)
        self.stack.addWidget(credits)
        self.stack.addWidget(translators)
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        buttonBox = QDialogButtonBox()
        closeButton = buttonBox.addButton(QDialogButtonBox.Close)  # type: QPushButton
        translateDialogBoxButtons(buttonBox)
        self.creditsButton = buttonBox.addButton(
            _("Credits"), QDialogButtonBox.HelpRole
        )  # type: QPushButton
        self.creditsButton.setDefault(False)
        self.creditsButton.setCheckable(True)
        self.translatorsButton = buttonBox.addButton(
            _("Translators"), QDialogButtonBox.ResetRole
        )  # type: QPushButton
        self.translatorsButton.setDefault(False)
        self.translatorsButton.setCheckable(True)
        closeButton.setDefault(True)

        buttonLayout = QVBoxLayout()
        buttonLayout.addWidget(buttonBox)
        buttonLayout.setContentsMargins(
            left_margin, left_margin, left_margin, left_margin
        )

        mainLayout.setContentsMargins(0, 0, 0, 0)

        version = QLabel(__about__.__version__)
        version.setFixedHeight(white_box_height - title_bottom)

        version_style_sheet = """QLabel {
        padding-left: %(left_margin)dpx;
        }""" % dict(
            left_margin=left_margin
        )

        version.setStyleSheet(version_style_sheet)

        mainLayout.addSpacing(title_bottom)
        mainLayout.addWidget(version)
        mainLayout.addWidget(self.stack)
        mainLayout.addLayout(buttonLayout)

        self.setLayout(mainLayout)

        buttonBox.rejected.connect(self.reject)
        self.creditsButton.clicked.connect(self.creditsButtonClicked)
        self.translatorsButton.clicked.connect(self.translatorsButtonClicked)

        closeButton.setFocus()

    @pyqtSlot()
    def creditsButtonClicked(self) -> None:
        self.translatorsButton.setChecked(False)
        self.showStackItem()

    @pyqtSlot()
    def translatorsButtonClicked(self) -> None:
        self.creditsButton.setChecked(False)
        self.showStackItem()

    @pyqtSlot()
    def showStackItem(self) -> None:
        if self.creditsButton.isChecked():
            self.stack.setCurrentIndex(1)
        elif self.translatorsButton.isChecked():
            self.stack.setCurrentIndex(2)
            self.creditsButton.setChecked(False)
        else:
            self.stack.setCurrentIndex(0)
