# SPDX-FileCopyrightText: Copyright 2016-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Display an About window
"""

import re
from pathlib import Path

from PyQt5.QtCore import QSize, Qt, pyqtSlot
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import raphodo.__about__ as __about__
from raphodo.internationalisation.install import install_gettext
from raphodo.tools.utilities import data_file_path
from raphodo.ui.viewutils import translateDialogBoxButtons

install_gettext()


class AboutDialog(QDialog):
    """
    Display an About window
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)

        self.setObjectName("AboutDialog")
        png = data_file_path("splashscreen.png")
        url = Path(png).as_posix()
        self.setStyleSheet(f"QDialog#AboutDialog {{background-image: url({url});}}")

        pixmap = QPixmap(png)
        try:
            ratio = pixmap.devicePixelRatioF()
        except AttributeError:
            ratio = pixmap.devicePixelRatio()

        if ratio > 1.0:
            size = QSize(round(pixmap.width() / ratio), round(pixmap.height() / ratio))
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

        link_style = 'style="color: white;"'

        msg = f"""Copyright &copy; 2007-2024 Damon Lynch.<br><br>
        <a href="https://damonlynch.net/rapid" {link_style}>
        damonlynch.net/rapid</a><br><br>
        This program comes with absolutely no warranty.<br>
        See the <a href="http://www.gnu.org/copyleft/gpl.html" {link_style}>GNU 
        General Public License, version 3 or later</a> for details.
        """

        details = QLabel(msg)

        details_style_sheet = f"""QLabel {{
        color: white;
        background-color: {transparency};
        margin-left: 0px;
        padding-left: {left_margin}px;
        padding-top: 6px;
        padding-right: 6px;
        padding-bottom: 6px;
        }}"""

        details.setStyleSheet(details_style_sheet)
        details.setOpenExternalLinks(True)
        details.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        font: QFont = self.font()
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

        photolink = (
            '<a href="https://www.flickr.com/photos/damonlynch/13598615933/" '
            f"{link_style}>Afghan Men Pulling Heavy Load</a>"
        )
        artlink1 = (
            f'<a href="http://www.webalys.com" {link_style}">Vincent Le Moign</a>'
        )
        artlink2 = (
            '<a href="https://www.iconfinder.com/bluewolfski" '
            f"{link_style}>The Pictographers</a>"
        )
        artlink3 = (
            '<a href="https://www.iconfinder.com/Enesdal" ' f"{link_style}>Enes Dal</a>"
        )
        artlink4 = f'<a href="http://www.iconsolid.com/" {link_style}>Icons Solid</a>'
        artlink5 = f'<a href="https://sellfy.com/designcoon" {link_style}>Icon Coon</a>'
        artlink6 = (
            f'<a href="https://www.iconfinder.com/buninux" {link_style}>'
            "Dmitriy Bunin</a>"
        )
        artlink7 = (
            f'<a href="https://www.flaticon.com/authors/pixel-perfect" {link_style}>'
            f"Pixel perfect</a>"
        )

        credits_text = f"""
        Copyright © 2007-2024 Damon Lynch.
        Portions copyright © 2008-2015 Canonical Ltd.
        Portions copyright © 2013 Bernard Baeyens.
        Portions copyright © 2012-2015 Jim Easterbrook.
        Portions copyright © 2012 Sven Marnach.
        Portions copyright © 2015 Dmitry Shachnev.

        Photo {photolink} copyright © 2014-2018 Damon Lynch, all rights reserved.
        Camera icon courtesy {artlink1}.
        Video camera icon courtesy {artlink2}.
        Home icon courtesy {artlink3}.
        Speech bubble courtesy {artlink4}.
        Lightbulb icon courtesy {artlink5}.
        Double arrow icon courtesy {artlink6}.
        Clock icon courtesy {artlink7}.
        """

        credits_text = credits_text.replace("\n", "<br>\n")

        label_style_sheet = f"""QLabel {{
        background-color: rgba(0, 0, 0, 0);
        color: white;
        padding-left: {left_margin}px;
        padding-top: 6px;
        padding-right: 6px;
        padding-bottom: 6px;
        }}"""

        creditsLabel = QLabel(credits_text)
        creditsLabel.setFont(font)
        creditsLabel.setStyleSheet(label_style_sheet)
        creditsLabel.setOpenExternalLinks(True)

        credits = QScrollArea()
        credits.setWidget(creditsLabel)
        scroll_area_style_sheet = f"""QScrollArea {{
        background-color: {transparency};
        border: 0px;
        }}
        """
        credits.setStyleSheet(scroll_area_style_sheet)

        # Translators view

        translators_text = """
        <b>Albanian</b>
        Algent Albrahimi <algent@protonmail.com>

        <b>Belarusian</b>
        Ilya Tsimokhin <ilya@tsimokhin.com>

        <b>Brazilian Portuguese</b>
        Rubens Stuginski Jr <rubens.stuginski@gmail.com>

        <b>Catalan</b>
        Adolfo Jayme Barrientos <fitoschido@gmail.com>

        <b>Czech</b>
        Pavel Borecki <pavel.borecki@gmail.com>

        <b>Danish</b>
        Torben Gundtofte-Bruun <torben@g-b.dk>

        <b>Dutch</b>
        Nico Rikken <nico@nicorikken.eu>

        <b>Estonian</b>
        Tauno Erik <tauno.erik@gmail.com>

        <b>Finnish</b>
        Mikko Ruohola <mikko@ruohola.org>

        <b>French</b>
        Jean-Marc Lartigue <m.balthazar@posteo.net>

        <b>Greek</b>
        Dimitris Xenakis <dx@nkdx.gr>

        <b>Hungarian</b>
        László <mail@csordaslaszlo.hu>

        <b>Italian</b>
        Albano Battistella <albano_battistella@hotmail.com>
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
        Alain J. Baudrez <a.baudrez@gmail.com>
        Bert <crinbert@yahoo.com>
        Martin Dahl Moe
        Marco de Freitas <marcodefreitas@gmail.com>
        Martin Egger <martin.egger@gmx.net>
        Sergiy Gavrylov <sergiovana@bigmir.net>
        Emanuele Grande <caccolangrifata@gmail.com>
        Toni Lähdekorpi <toni@lygon.net>
        András Lőrincz <level.andrasnak@gmail.com>
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
        Ney Walens de Mesquita <walens@gmail.com>        
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
        closeButton: QPushButton = buttonBox.addButton(QDialogButtonBox.Close)
        translateDialogBoxButtons(buttonBox)
        self.creditsButton: QPushButton = buttonBox.addButton(
            _("Credits"), QDialogButtonBox.HelpRole
        )
        self.creditsButton.setDefault(False)
        self.creditsButton.setCheckable(True)
        self.translatorsButton: QPushButton = buttonBox.addButton(
            _("Translators"), QDialogButtonBox.ResetRole
        )
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
        }""" % dict(left_margin=left_margin)

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
