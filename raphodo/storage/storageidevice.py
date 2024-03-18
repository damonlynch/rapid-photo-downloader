# SPDX-FileCopyrightText: Copyright 2022-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Utility functions that use subprocess to call primarily libimobiledevice utilities
to handle iOS devices.

There is a Python binding to libimobiledevice, but at the time of writing it is
undocumented and very difficult to use.
"""

import logging
import os
import shutil
import subprocess

from raphodo.cameraerror import iOSDeviceError
from raphodo.constants import CameraErrorCode
from raphodo.tools.utilities import create_temp_dir

# Utilities for identifying, pairing, and mounting iOS devices
# Called every time on import into a new process, but not much we can do about that
# without a bunch of extra optimization steps
idevice_helper_apps = ("idevicename", "idevicepair", "ifuse", "fusermount")
ios_helper_cmds = [shutil.which(cmd) for cmd in idevice_helper_apps]
idevicename_cmd, idevicepair_cmd, ifuse_cmd, fusermount_cmd = ios_helper_cmds


def utilities_present() -> bool:
    """
    :return: True if all iOS helper utility applications are present on the system
    """
    return None not in ios_helper_cmds


def ios_missing_programs() -> list[str]:
    """
    :return: a list of missing helper programs to allow iOS device access
    """
    return [
        idevice_helper_apps[i]
        for i in range(len(ios_helper_cmds))
        if ios_helper_cmds[i] is None
    ]


def idevice_serial_to_udid(serial: str) -> str:
    """
    Generate udid for imobiledevice utilities from serial number

    There appear to be two (or more?) formats for iOS device serial numbers
    as reported by udev.

    :param serial: udev device serial number
    :return: udid suitable for imobiledevice utilities
    """

    if len(serial) == 24:
        return f"{serial[:8]}-{serial[8:]}"
    else:
        if len(serial) != 40:
            logging.warning(
                "Unexpected serial number length for iOS device: %s", serial
            )
        return serial


def idevice_run_command(
    command: str,
    udid: str,
    argument_before_option: str | None = "",
    argument: str | None = "",
    display_name: str | None = "",
    warning_only: bool | None = False,
    supply_udid_as_arg: bool | None = True,
    camera_error_code: CameraErrorCode | None = CameraErrorCode.pair,
) -> str:
    """
    Run a command and raise an error if it fails

    :param command: command to run, e.g. idevicename_cmd
    :param udid: iOS device udid, used to perform operations on specific device
    :param argument_before_option: argument to pass command before any '-u udid'
     argument
    :param argument: argument to pass command after any '-u udid' argument
    :param display_name: iOS name for use in error messages
    :param warning_only: do not raise an error, but instead log a warning
    :param supply_udid_as_arg: if True, add '-u udid' argument to command
    :param camera_error_code: error code to raise when something goes wrong
    :return: command's stdout / stderr
    """

    cmd = [command]
    if command == fusermount_cmd:
        cmd.append(
            "-u"
        )  # Note: nothing to to with udid. Simply instructs fusermount to unmount.
    if argument_before_option:
        cmd.append(argument_before_option)
    if supply_udid_as_arg:
        cmd.append("-u")
        cmd.append(udid)
    if argument:
        cmd.append(argument)

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        if warning_only:
            logging.warning(
                "Error running %s for %s. %s: %s",
                command,
                display_name or udid,
                e.returncode,
                e.stdout.decode().strip(),
            )
            return ""
        else:
            raise iOSDeviceError(
                camera_error_code, e.returncode, e.output.decode(), udid, display_name
            )
    return result.stdout.decode()


def idevice_get_name(udid: str) -> str:
    """
    Determine name of idevice using its udid

    :param udid: Apple device udid in format used by imobiledevice utilities
    :return: output of idevicename
    """

    return idevice_run_command(
        udid=udid,
        command=idevicename_cmd,
        warning_only=True,
        camera_error_code=CameraErrorCode.devicename,
    ).strip()


def idevice_run_idevicepair_command(udid: str, display_name: str, argument: str) -> str:
    """
    Run idevicepair with argument and return result
    :param udid: iOS device udid, used to perform operations on specific device
    :param display_name: iOS name for use in error messages
    :param argument: idevicepair argument to run
    :return: command's stdout / stderr
    """

    assert argument in ("validate", "list", "pair")
    return idevice_run_command(
        udid=udid, display_name=display_name, command=idevicepair_cmd, argument=argument
    )


def idevice_in_pairing_list(udid: str, display_name: str) -> bool:
    """Check if iOS device is in list of paired devices"""

    logging.debug(
        "Checking if '%s' is already in iOS device pairing list", display_name
    )
    result = idevice_run_idevicepair_command(
        udid=udid, display_name=display_name, argument="list"
    )
    return udid in result


def idevice_validate_pairing(udid: str, display_name: str):
    """
    Validate if iOS device has already been paired.
    Raises error on failure.
    """

    idevice_run_idevicepair_command(
        udid=udid, display_name=display_name, argument="validate"
    )
    logging.info("Successfully validated pairing of '%s'", display_name)


def idevice_pair(udid: str, display_name: str):
    """Pair iOS device"""

    idevice_run_idevicepair_command(
        udid=udid, display_name=display_name, argument="pair"
    )
    logging.debug("Successfully paired '%s'", display_name)


def idevice_do_mount(udid: str, display_name: str) -> str:
    """
    Mount an iOS device that has already been paired.
    :param udid: iOS device udid, used to perform operations on specific device
    :param display_name: display_name: iOS name for use in error messages
    :return: FUSE mount point
    """

    logging.info("Mounting iOS device '%s' using FUSE", display_name)

    mount_point = idevice_generate_mount_point(udid=udid)

    idevice_run_command(
        udid=udid,
        command=ifuse_cmd,
        display_name=display_name,
        argument_before_option=mount_point,
        camera_error_code=CameraErrorCode.mount,
    )
    return mount_point


def idevice_do_unmount(udid: str, display_name: str, mount_point: str):
    """
    Unmount an iOS device that was mounted using FUSE, and remove the directory.
    :param udid: iOS device udid, used to perform operations on specific device
    :param display_name: display_name: iOS name for use in error messages
    :return: FUSE mount point
    """

    logging.info("Unmounting iOS device '%s' from FUSE mount", display_name)

    try:
        idevice_run_command(
            udid=udid,
            command=fusermount_cmd,
            display_name=display_name,
            argument=mount_point,
            camera_error_code=CameraErrorCode.mount,
            supply_udid_as_arg=False,
        )
    except iOSDeviceError as e:
        logging.error(
            "Error unmounting iOS device '%s'. %s: %s",
            e.display_name,
            e.imobile_error,
            e.imobile_error_output,
        )
    if os.path.isdir(mount_point):
        try:
            os.rmdir(mount_point)
        except OSError:
            logging.exception(f"Failed to remove temporary directory {mount_point}")


def idevice_generate_mount_point(udid: str) -> str:
    """
    Create a temporary directory in which to mount iOS device using FUSE
    :param udid: iOS device udid, used to perform operations on a specific device
    :return: full path to the temp dir
    """

    # Make the temp directory have the iOS serial number so that when thumbnails are
    # saved by path, the path will be the same each time the device is inserted

    temp_dir = create_temp_dir(temp_dir_name=f"rpd-tmp-{udid}")
    assert temp_dir is not None
    logging.debug("Created temp mount point %s", temp_dir)
    return temp_dir
