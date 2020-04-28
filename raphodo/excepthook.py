# Copyright (C) 2016-2020 Damon Lynch <damonlynch@gmail.com>

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


__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2016-2020, Damon Lynch"


import logging
import traceback
import io
import os
from PyQt5.QtWidgets import QMessageBox, QApplication
try:
    from easygui import codebox
    have_easygui = True
except:
    # if import failed for any reason, ignore it
    have_easygui = False


import raphodo.qrc_resources as qrc_resources

from raphodo.iplogging import full_log_file_path
from raphodo.storage import get_uri
from raphodo.preferences import Preferences
from raphodo.utilities import create_bugreport_tar, bug_report_full_tar_path
from raphodo.viewutils import standardMessageBox

message_box_displayed = False
exceptions_notified = set()

# Translators: do not translate the HTML tags such as  <a> or <br>, or the Python
# string formatting tags such as website.
please_report_problem_body = _(
    'Please report the problem at <a href="{website}">{website}</a>.<br><br>'
    'In your bug report describe what you expected to happen, and what you observed ' 
    'happening.<br><br>'
    "The bug report must also include the program settings and log files. To create a file with "
    "this additional information, click Save."
)

tar_created_title = _('Additional Information Saved')

# Translators: do not translate the HTML tags such as <pre>, <a>, or <br>, or the Python
# string formatting tags tarfile and uri.
tar_created_body = _(
    'The additional bug report information was created in your home directory in '
    'a tar file: <pre>{tarfile}</pre>'
    'You need to attach this file to the bug report yourself. It will not be automatically '
    'attached.<br><br>'
    'Click <a href="{uri}">here</a> to see the file in your file manager.'
)

tar_error_title = _('Error Creating Additional Information')

tar_error_header = _(
    'The additional bug report information was not created. Please file a bug report anyway.'
)

# Translators: do not translate the HTML tags such as <i>, <a>, or <br>, or the Python
# string formatting tags log_file, etc.
tar_error_body = _(
    "Include in your bug report the program's log files. The bug report must include "
    "<i>{log_file}</i>, but attaching the other log files is often helpful.<br><br>" 
    "If possible, please also include the program's configuration file "
    "<i>{config_file}</i>.<br><br>" 
    'Click <a href="{log_path}">here</a> to open the log directory, and ' 
    '<a href="{config_path}">here</a> to open the configuration directory.'
)

upgrade_message = _(
    'Upgrading to the <a href="{website}">latest version</a> will allow you to determine if the '
    "problem you encountered has already been fixed."
)


def save_bug_report_tar(config_file: str, full_log_file_path: str) -> None:
    """
    Save a tar file in the user's home directory with logging files and config file.
    Inform the user of the result using QMessageBox.

    :param config_file: full path to the config file
    :param full_log_file_path: full path to the directory with the log files
    """

    bug_report_full_tar = bug_report_full_tar_path()

    logging.info("Creating bug report tar file %s", bug_report_full_tar)
    log_path, log_file = os.path.split(full_log_file_path)
    if create_bugreport_tar(
            full_tar_name=bug_report_full_tar, log_path=log_path,
            full_config_file=config_file):

        body = tar_created_body.format(
            tarfile=os.path.split(bug_report_full_tar)[1],
            uri=get_uri(full_file_name=bug_report_full_tar)
        )
        messagebox = standardMessageBox(
            message=body, rich_text=True, title=tar_created_title,
            standardButtons=QMessageBox.Ok
        )
        messagebox.exec_()
    else:
        # There was some kind of problem generating the tar file, e.g. no free space
        log_uri = get_uri(log_path)
        config_path, config_file = os.path.split(config_file)
        config_uri = get_uri(path=config_path)

        body = tar_error_body.format(
            log_path=log_uri, log_file=log_file,
            config_path=config_uri, config_file=config_file
        )
        message = '<b>{header}</b><br><br>{body}'.format(
            header=tar_error_header, body=body
        )
        messageBox = standardMessageBox(
            message=message, rich_text=True, title=tar_error_title,
            standardButtons=QMessageBox.Ok
        )
        messageBox.exec_()


def excepthook(exception_type, exception_value, traceback_object) -> None:
    """
    Global function to catch unhandled exceptions.

    Inspired by function of the same name in the Eric project, but subsequently heavily modified.
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
    traceback.print_exception(
        exception_type, exception_value, traceback_object, limit=None, file=tb_file
    )
    tb_file.seek(0)
    traceback_info = tb_file.read()

    logging.error("An unhandled exception occurred")
    logging.error(traceback_info)

    if not message_box_displayed and key not in exceptions_notified:
        message_box_displayed = True
        exceptions_notified.add(key)

        prefs = Preferences()

        title = _("Problem in Rapid Photo Downloader")

        if QApplication.instance():

            header = _('A problem occurred in Rapid Photo Downloader')

            only_notification = _(
                "If the same problem occurs again before the program exits, this is the "
                "only notification about it."
            )

            body = please_report_problem_body.format(website='https://bugs.launchpad.net/rapid')

            message = "<b>{}</b><br><br>{}<br><br>{}".format(
                header, body, only_notification
            )

            errorbox = standardMessageBox(
                message=message, rich_text=True, title=title,
                standardButtons=QMessageBox.Save | QMessageBox.Cancel,
                defaultButton=QMessageBox.Save
            )
            errorbox.setDetailedText(traceback_info)
            if errorbox.exec_() == QMessageBox.Save:
                save_bug_report_tar(
                    config_file=prefs.settings_path(),
                    full_log_file_path=full_log_file_path()
                )

        elif have_easygui:
            message = _('A problem occurred in Rapid Photo Downloader\n')
            prefix = _(
                "Please report the problem at {website}\n"
                "Attach the log file to your bug report, found at {log_path}\n\n"
            ).format(website='https://bugs.launchpad.net/rapid', log_path=full_log_file_path())
            text = prefix + traceback_info
            codebox(msg=message, title=title, text=text)
        message_box_displayed = False

