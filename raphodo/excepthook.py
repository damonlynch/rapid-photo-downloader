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
# along with Rapid Photo Downloader. If not,
# see <http://www.gnu.org/licenses/>.

import logging
import traceback
import io
import os
from urllib.request import pathname2url
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMessageBox, QApplication
from PyQt5.QtGui import QPixmap
try:
    from easygui import codebox
    have_easygui = True
except:
    # if import failed for any reason, ignore it
    have_easygui = False

from gettext import gettext as _
import raphodo.qrc_resources as qrc_resources

from raphodo.iplogging import full_log_file_path

message_box_displayed = False
exceptions_notified = set()


def excepthook(exception_type, exception_value, traceback_object) -> None:
    """
    Global function to catch unhandled exceptions.

    Inspired by function of the same name in the Eric project.
    """

    if traceback_object is not None:
        frame = traceback_object.tb_frame
        filename = frame.f_code.co_filename
        lineno = traceback_object.tb_lineno
    else:
        lineno = -1
        filename = 'unknown'
    key = '{}{}'.format(filename, lineno)

    global message_box_displayed

    tb_file = io.StringIO()
    traceback.print_exception(exception_type, exception_value, traceback_object,
                              limit=None, file=tb_file)
    tb_file.seek(0)
    traceback_info = tb_file.read()

    logging.error("An unhandled exception occurred")
    logging.error(traceback_info)

    if not message_box_displayed and key not in exceptions_notified:
        message_box_displayed = True
        exceptions_notified.add(key)

        log_path, log_file = os.path.split(full_log_file_path())
        log_uri = pathname2url(log_path)

        title = _("Problem in Rapid Photo Downloader")

        if QApplication.instance():

            message = _(r"""<b>A problem occurred in Rapid Photo Downloader</b><br><br>
    Please report the problem at <a href="{website}">{website}</a>.<br><br>
    Attach the log file <i>{log_file}</i> to your bug report (click
    <a href="{log_path}">here</a> to open the log directory).<br><br>If the same problem occurs
    again before the program exits, this is the only notification about it.
    """).format(website='https://bugs.launchpad.net/rapid', log_path=log_uri, log_file=log_file)

            icon = QPixmap(':/rapid-photo-downloader.svg')

            errorbox = QMessageBox()
            errorbox.setTextFormat(Qt.RichText)
            errorbox.setIconPixmap(icon)
            errorbox.setWindowTitle(title)
            errorbox.setText(message)
            errorbox.setDetailedText(traceback_info)
            errorbox.exec_()
        elif have_easygui:
            message = _('A problem occurred in Rapid Photo Downloader\n')
            prefix = _("""Please report the problem at {website}\n
    Attach the log file to your bug report, found at {log_path}\n\n""").format(
                website='https://bugs.launchpad.net/rapid', log_path=full_log_file_path())
            text = prefix + traceback_info
            codebox(msg=message, title=title, text=text)
        message_box_displayed = False

