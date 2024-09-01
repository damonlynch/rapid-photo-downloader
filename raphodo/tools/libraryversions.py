# SPDX-FileCopyrightText: Copyright 2011-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later


import contextlib
import importlib.metadata
import os
import platform
import sys

import arrow
import dateutil
import gi
import psutil
import zmq
from PyQt5 import QtCore, sip
from showinfm import linux_desktop, linux_desktop_humanize

from raphodo import __about__ as __about__
from raphodo.camera import gphoto2_version, python_gphoto2_version
from raphodo.constants import ScalingAction, ScalingDetected
from raphodo.heif import have_heif_module, libheif_version, pyheif_version
from raphodo.metadata import fileformats as fileformats
from raphodo.metadata.metadatavideo import pymedia_version_info
from raphodo.programversions import EXIFTOOL_VERSION, exiv2_version, gexiv2_version
from raphodo.storage import storageidevice as storageidevice
from raphodo.storage.storage import get_desktop_environment
from raphodo.thumbnailextractor import gst_version
from raphodo.tools.packageutils import installed_using_pip, python_package_source
from raphodo.tools.utilities import format_size_for_user


def get_versions(
    file_manager: str | None,
    scaling_action: ScalingAction,
    scaling_detected: ScalingDetected,
    xsetting_running: bool,
    force_wayland: bool,
    platform_selected: str | None,
) -> list[str]:
    pyzmq_backend = "cython" if "cython" in zmq.zmq_version_info.__module__ else "cffi"
    try:
        ram = psutil.virtual_memory()
        total = format_size_for_user(ram.total)
        used = format_size_for_user(ram.used)
    except Exception:
        total = used = "unknown"

    rpd_pip_install = installed_using_pip("rapid-photo-downloader")

    versions = [
        f"Rapid Photo Downloader: {__about__.__version__}",
        f"Platform: {platform.platform()}",
        f"Memory: {used} used of {total}",
        "Installed using pip: {}".format("yes" if rpd_pip_install else "no"),
        f"Python: {platform.python_version()}",
        f"Python executable: {sys.executable}",
        f"Qt: {QtCore.QT_VERSION_STR}",
        f"PyQt: {QtCore.PYQT_VERSION_STR} {python_package_source('PyQt5')}",
        f"SIP: {sip.SIP_VERSION_STR}",
        f"ZeroMQ: {zmq.zmq_version()}",
        f"Python ZeroMQ: {zmq.pyzmq_version()} ({pyzmq_backend} backend)",
        f"gPhoto2: {gphoto2_version()}",
        "Python gPhoto2: "
        f"{python_gphoto2_version()} {python_package_source('gphoto2')}",
        f"ExifTool: {EXIFTOOL_VERSION}",
        f"pymediainfo: {pymedia_version_info()}",
        f"GExiv2: {gexiv2_version()}",
        f"Gstreamer: {gst_version()}",
        f"PyGObject: {'.'.join(map(str, gi.version_info))}",
        f"psutil: {'.'.join(map(str, psutil.version_info))}",
        f'Show in File Manager: {importlib.metadata.version("show-in-file-manager")}',
    ]
    v = exiv2_version()
    if v:
        cr3 = "CR3 support enabled" if fileformats.exiv2_cr3() else "no CR3 support"
        versions.append(f"Exiv2: {v} ({cr3})")
    with contextlib.suppress(Exception):
        versions.append("{}: {}".format(*platform.libc_ver()))
    with contextlib.suppress(AttributeError):
        versions.append(f"Arrow: {arrow.__version__} {python_package_source('arrow')}")
        versions.append(f"dateutil: {dateutil.__version__}")
    with contextlib.suppress(ImportError):
        import tornado

        versions.append(f"Tornado: {tornado.version}")
    versions.append(
        f"Can read HEIF/HEIC metadata: {'yes' if fileformats.heif_capable() else 'no'}"
    )
    if have_heif_module:
        versions.append(f"Pyheif: {pyheif_version()}")
        v = libheif_version()
        if v:
            versions.append(f"libheif: {v}")
    versions.append(
        "iOS support: {}".format("yes" if storageidevice.utilities_present() else "no")
    )
    for display in ("XDG_SESSION_TYPE", "WAYLAND_DISPLAY"):
        session = os.getenv(display, "")
        if session.find("wayland") >= 0:
            wayland_platform = os.getenv("QT_QPA_PLATFORM", "")
            if (
                platform_selected == "wayland"
                or (platform_selected != "xcb" and wayland_platform == "wayland")
                or force_wayland
            ):
                session = "wayland desktop (with wayland enabled)"
                break
            elif platform_selected == "xcb" or wayland_platform == "xcb":
                session = "wayland desktop (with XWayland)"
                break
            else:
                session = "wayland desktop (XWayland use undetermined)"
        elif session:
            break
    if session:
        versions.append(f"Session: {session}")

    versions.append("Desktop scaling: {}".format(scaling_action.name.replace("_", " ")))
    versions.append(
        "Desktop scaling detection: {}{}".format(
            scaling_detected.name.replace("_", " "),
            "" if xsetting_running else " (xsetting not running)",
        )
    )

    try:
        desktop = linux_desktop_humanize(linux_desktop())
    except Exception:
        desktop = "Unknown"

    with contextlib.suppress(Exception):
        versions.append(f"Desktop: {get_desktop_environment()} ({desktop})")

    file_manager_details = f"{file_manager}" if file_manager else "Unknown"

    versions.append(f"Default file manager: {file_manager_details}")

    return versions
