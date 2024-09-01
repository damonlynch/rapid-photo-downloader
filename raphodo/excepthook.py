# SPDX-FileCopyrightText: Copyright 2016-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

import io
import logging
import os
import traceback

from PyQt5.QtWidgets import QApplication, QMessageBox

from raphodo.internationalisation.install import install_gettext
from raphodo.iplogging import full_log_file_path
from raphodo.prefs.preferences import Preferences
from raphodo.storage.storage import get_uri
from raphodo.tools.utilities import bug_report_full_tar_path, create_bugreport_tar
from raphodo.ui.viewutils import standardMessageBox

install_gettext()

message_box_displayed = False
exceptions_notified = set()

# Translators: do not translate the HTML tags such as  <a> or <br>, or the Python
# string formatting tags such as website.
please_report_problem_body = _(
    'Please report the problem at <a href="{website}">{website}</a>.<br><br>'
    "In your bug report describe what you expected to happen, and what you observed "
    "happening.<br><br>"
    "The bug report must also include the program settings and log files. To create a "
    "file with this additional information, click Save."
)

tar_created_title = _("Additional Information Saved")

# Translators: do not translate the HTML tags such as <pre>, <a>, or <br>, or the Python
# string formatting tags tarfile and uri.
tar_created_body = _(
    "The additional bug report information was created in your home directory in "
    "a tar file: <pre>{tarfile}</pre>"
    "You need to attach this file to the bug report yourself. It will not be "
    "automatically attached.<br><br>"
    'Click <a href="{uri}">here</a> to see the file in your file manager.'
)

tar_error_title = _("Error Creating Additional Information")

tar_error_header = _(
    "The additional bug report information was not created. Please file a bug report "
    "anyway."
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
    'Upgrading to the <a href="{website}">latest version</a> will allow you to '
    "determine if the problem you encountered has already been fixed."
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
        full_tar_name=bug_report_full_tar,
        log_path=log_path,
        full_config_file=config_file,
    ):
        body = tar_created_body.format(
            tarfile=os.path.split(bug_report_full_tar)[1],
            uri=get_uri(full_file_name=bug_report_full_tar),
        )
        messagebox = standardMessageBox(
            message=body,
            rich_text=True,
            title=tar_created_title,
            standardButtons=QMessageBox.Ok,
        )
        messagebox.exec_()
    else:
        # There was some kind of problem generating the tar file, e.g. no free space
        log_uri = get_uri(log_path)
        config_path, config_file = os.path.split(config_file)
        config_uri = get_uri(path=config_path)

        body = tar_error_body.format(
            log_path=log_uri,
            log_file=log_file,
            config_path=config_uri,
            config_file=config_file,
        )
        message = f"<b>{tar_error_header}</b><br><br>{body}"
        messageBox = standardMessageBox(
            message=message,
            rich_text=True,
            title=tar_error_title,
            standardButtons=QMessageBox.Ok,
        )
        messageBox.exec_()


def excepthook(exception_type, exception_value, traceback_object) -> None:
    """
    Global function to catch unhandled exceptions.

    Inspired by function of the same name in the Eric project, but subsequently heavily
    modified.
    """

    if traceback_object is not None:
        frame = traceback_object.tb_frame
        filename = frame.f_code.co_filename
        lineno = traceback_object.tb_lineno
    else:
        lineno = -1
        filename = "unknown"
    key = f"{filename}{lineno}"

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
            header = _("A problem occurred in Rapid Photo Downloader")

            only_notification = _(
                "If the same problem occurs again before the program exits, this is "
                "the only notification about it."
            )

            body = please_report_problem_body.format(
                website="https://bugs.rapidphotodownloader.com"
            )

            message = f"<b>{header}</b><br><br>{body}<br><br>{only_notification}"

            errorbox = standardMessageBox(
                message=message,
                rich_text=True,
                title=title,
                standardButtons=QMessageBox.Save | QMessageBox.Cancel,
                defaultButton=QMessageBox.Save,
            )
            errorbox.setDetailedText(traceback_info)
            if errorbox.exec_() == QMessageBox.Save:
                save_bug_report_tar(
                    config_file=prefs.settings_path(),
                    full_log_file_path=full_log_file_path(),
                )
        message_box_displayed = False
