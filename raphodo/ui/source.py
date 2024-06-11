# SPDX-FileCopyrightText: Copyright 2016-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from PyQt5.QtGui import QColor

from raphodo.constants import CustomColors, DeviceType, DisplayFileType, FileType
from raphodo.customtypes import UsageDetails
from raphodo.devices import Device
from raphodo.internationalisation.utilities import thousands
from raphodo.rpdfile import make_key
from raphodo.storage.storage import StorageSpace
from raphodo.tools.utilities import format_size_for_user


def usage_details(device: Device, storage_space: StorageSpace) -> UsageDetails:
    if device.device_type == DeviceType.camera:
        photo_key = make_key(FileType.photo, storage_space.path)
        video_key = make_key(FileType.video, storage_space.path)
        sum_key = storage_space.path
    else:
        photo_key = FileType.photo
        video_key = FileType.video
        sum_key = None

    # Translators: %(variable)s represents Python code, not a plural of the
    # term variable. You must keep the %(variable)s untranslated, or the
    # program will crash.
    photos = _("%(no_photos)s Photos") % {
        "no_photos": thousands(device.file_type_counter[photo_key])
    }
    # Translators: %(variable)s represents Python code, not a plural of the
    # term variable. You must keep the %(variable)s untranslated, or the
    # program will crash.
    videos = _("%(no_videos)s Videos") % {
        "no_videos": thousands(device.file_type_counter[video_key])
    }
    photos_size = format_size_for_user(device.file_size_sum[photo_key])
    videos_size = format_size_for_user(device.file_size_sum[video_key])

    if storage_space.bytes_total:
        other_bytes = (
            storage_space.bytes_total
            - device.file_size_sum.sum(sum_key)
            - storage_space.bytes_free
        )
        other_size = format_size_for_user(other_bytes)
        bytes_total_text = format_size_for_user(
            storage_space.bytes_total, no_decimals=0
        )
        bytes_used = storage_space.bytes_total - storage_space.bytes_free
        percent_used = f"{bytes_used / storage_space.bytes_total:.0%}"
        # Translators: percentage full e.g. 75% full
        percent_used = _("%s full") % percent_used
        bytes_total = storage_space.bytes_total
    else:
        percent_used = _("Device size unknown")
        bytes_total = device.file_size_sum.sum(sum_key)
        other_bytes = 0
        bytes_total_text = format_size_for_user(bytes_total, no_decimals=0)
        other_size = "0"

    return UsageDetails(
        bytes_total_text=bytes_total_text,
        bytes_total=bytes_total,
        percent_used_text=percent_used,
        bytes_free_of_total="",
        comp1_file_size_sum=device.file_size_sum[photo_key],
        comp2_file_size_sum=device.file_size_sum[video_key],
        comp3_file_size_sum=other_bytes,
        comp4_file_size_sum=0,
        comp1_text=photos,
        comp2_text=videos,
        comp3_text=_("Other"),
        comp4_text="",
        comp1_size_text=photos_size,
        comp2_size_text=videos_size,
        comp3_size_text=other_size,
        comp4_size_text="",
        color1=QColor(CustomColors.color1.value),
        color2=QColor(CustomColors.color2.value),
        color3=QColor(CustomColors.color3.value),
        display_type=DisplayFileType.photos_and_videos,
    )
