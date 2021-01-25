# Copyright (C) 2021 Damon Lynch <damonlynch@gmail.com>

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
Handle Apple devices using Apple File Conduit (AFC) via libimobiledevice
"""

__autho__ = 'Damon Lynch'
__copyright__ = 'Copyright 2021, Damon Lynch'

import logging
from enum import IntEnum
from typing import List
import sys

from imobiledevice import (
    iDevice, iDeviceError, LockdownClient, LockdownError, get_device_list, AfcClient,
    LockdownServiceDescriptor
)


# libimobiledevice.h
class iDeviceErrorCode(IntEnum):
    IDEVICE_E_SUCCESS = 0
    IDEVICE_E_INVALID_ARG = -1
    IDEVICE_E_UNKNOWN_ERROR = -2
    IDEVICE_E_NO_DEVICE = -3
    IDEVICE_E_NOT_ENOUGH_DATA = -4
    IDEVICE_E_SSL_ERROR = -6
    IDEVICE_E_TIMEOUT = -7


# lockdown.h
class LockDownErrorCode(IntEnum):
    LOCKDOWN_E_SUCCESS = 0,
    LOCKDOWN_E_INVALID_ARG = -1,
    LOCKDOWN_E_INVALID_CONF = -2,
    LOCKDOWN_E_PLIST_ERROR = -3,
    LOCKDOWN_E_PAIRING_FAILED = -4,
    LOCKDOWN_E_SSL_ERROR = -5,
    LOCKDOWN_E_DICT_ERROR = -6,
    LOCKDOWN_E_RECEIVE_TIMEOUT = -7,
    LOCKDOWN_E_MUX_ERROR = -8,
    LOCKDOWN_E_NO_RUNNING_SESSION = -9,
    LOCKDOWN_E_INVALID_RESPONSE = -10,
    LOCKDOWN_E_MISSING_KEY = -11,
    LOCKDOWN_E_MISSING_VALUE = -12,
    LOCKDOWN_E_GET_PROHIBITED = -13,
    LOCKDOWN_E_SET_PROHIBITED = -14,
    LOCKDOWN_E_REMOVE_PROHIBITED = -15,
    LOCKDOWN_E_IMMUTABLE_VALUE = -16,
    LOCKDOWN_E_PASSWORD_PROTECTED = -17,
    LOCKDOWN_E_USER_DENIED_PAIRING = -18,
    LOCKDOWN_E_PAIRING_DIALOG_RESPONSE_PENDING = -19,
    LOCKDOWN_E_MISSING_HOST_ID = -20,
    LOCKDOWN_E_INVALID_HOST_ID = -21,
    LOCKDOWN_E_SESSION_ACTIVE = -22,
    LOCKDOWN_E_SESSION_INACTIVE = -23,
    LOCKDOWN_E_MISSING_SESSION_ID = -24,
    LOCKDOWN_E_INVALID_SESSION_ID = -25,
    LOCKDOWN_E_MISSING_SERVICE = -26,
    LOCKDOWN_E_INVALID_SERVICE = -27,
    LOCKDOWN_E_SERVICE_LIMIT = -28,
    LOCKDOWN_E_MISSING_PAIR_RECORD = -29,
    LOCKDOWN_E_SAVE_PAIR_RECORD_FAILED = -30,
    LOCKDOWN_E_INVALID_PAIR_RECORD = -31,
    LOCKDOWN_E_INVALID_ACTIVATION_RECORD = -32,
    LOCKDOWN_E_MISSING_ACTIVATION_RECORD = -33,
    LOCKDOWN_E_SERVICE_PROHIBITED = -34,
    LOCKDOWN_E_ESCROW_LOCKED = -35,
    LOCKDOWN_E_PAIRING_PROHIBITED_OVER_THIS_CONNECTION = -36,
    LOCKDOWN_E_FMIP_PROTECTED = -37,
    LOCKDOWN_E_MC_PROTECTED = -38,
    LOCKDOWN_E_MC_CHALLENGE_REQUIRED = -39,
    LOCKDOWN_E_UNKNOWN_ERROR = -256


def get_idevice_list_uuids() -> List[bytes]:
    try:
        idevices = get_device_list()
    except iDeviceError as e:
        idevices = []
        if e.code == iDeviceErrorCode.IDEVICE_E_NO_DEVICE:
            logging.debug("No Apple idevices detected")
        else:
            logging.exception(e)
    return idevices


no_devices = len(get_idevice_list_uuids())
print('Detected {} Apple devices'.format(no_devices))

if no_devices:
    # libimobiledevice 1.3 has a bug that means a UDID cannot be passed to the iDevice class, and there
    # is no way to specify it afterwards
    i = iDevice()
    udid = i.udid.decode()

    lc = LockdownClient(i)
    while True:
        try:
            lc.pair()
            break
        except LockdownError as e:
            if e.code == LockDownErrorCode.LOCKDOWN_E_PASSWORD_PROTECTED:
                print(
                    "A passcode is set on device {}. Please enter the passcode on the device and "
                    "retry.".format(udid)
                )
            elif e.code == LockDownErrorCode.LOCKDOWN_E_PAIRING_DIALOG_RESPONSE_PENDING:
                print("Please accept the trust dialog on the screen of device {}".format(udid))
            elif e.code == LockDownErrorCode.LOCKDOWN_E_INVALID_ARG:
                print("No device appears to be present")
            elif e.code == LockDownErrorCode.LOCKDOWN_E_PLIST_ERROR:
                print("pair_record certificates are wrong")
            elif e.code == LockDownErrorCode.LOCKDOWN_E_PAIRING_FAILED:
                print("pairing failed")
            elif e.code == LockDownErrorCode.LOCKDOWN_E_INVALID_HOST_ID:
                print("The device does not know the caller's host id")
            else:
                print(e)
            k = input('Press any key to continue or e to exit')
            if k == 'e':
                sys.exit(0)

    print("Device {} is paired".format(udid))
    # afc = lc.get_service_client(AfcClient)
    afc = AfcClient(i)
    # afc.get_device_info()
    print(afc.read_directory(b'/DCIM'))
    k = input('Press any key to continue or e to exit')
    if k == 'e':
        sys.exit(0)
    lc.unpair()
    print("Device {} is unpaired".format(udid))
