# Copyright (C) 2015-2021 Damon Lynch <damonlynch@gmail.com>

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
Class to handle exceptions related to camera access via gPhoto2 and libimobiledevice
"""

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2015-2021, Damon Lynch."

from typing import Optional

import gphoto2 as gp

from raphodo.constants import CameraErrorCode


class CameraError(Exception):
    def __init__(self, code: CameraErrorCode) -> None:
        self.code = code

    def __repr__(self) -> str:
        return self.code.name

    def __str__(self) -> str:
        if self.code == CameraErrorCode.inaccessible:
            return "The camera is inaccessible"
        elif self.code == CameraErrorCode.locked:
            return "The camera is locked"


class CameraProblemEx(CameraError):
    """Handle gPhoto2 errors"""

    def __init__(
        self,
        code: CameraErrorCode,
        gp_exception: Optional[gp.GPhoto2Error] = None,
        py_exception: Optional[Exception] = None,
    ) -> None:
        super().__init__(code)
        if gp_exception is not None:
            self.gp_code = gp_exception.code
        else:
            self.gp_code = None
        self.py_exception = py_exception

    def __repr__(self) -> str:
        if self.code == CameraErrorCode.read:
            return "read error"
        elif self.code == CameraErrorCode.write:
            return "write error"
        else:
            return repr(super())

    def __str__(self) -> str:
        if self.code == CameraErrorCode.read:
            return "Could not read file from camera"
        elif self.code == CameraErrorCode.write:
            return "Could not write file from camera"
        else:
            return str(super())


class iOSDeviceError(CameraError):
    """Handle iOS Device errors"""

    def __init__(
        self,
        code: CameraErrorCode,
        imobile_error: int,
        imobile_error_output: str,
        udid: str,
        display_name: str,
    ) -> None:
        super().__init__(code)
        self.imobile_error = imobile_error
        self.imobile_error_output = imobile_error_output
        self.udid = udid
        self.display_name = display_name

    def __str__(self) -> str:

        if self.code in (
            CameraErrorCode.pair,
            CameraErrorCode.mount,
            CameraErrorCode.devicename,
        ):
            message = self.imobile_error_output.replace(
                self.udid, "'{}'".format(self.display_name)
            )
            if message.startswith("ERROR: "):
                message = message[7:]
            return message
        else:
            return str(super())
