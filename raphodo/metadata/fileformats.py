# SPDX-FileCopyrightText: Copyright 2011-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import os
import subprocess

from packaging.version import parse as parse_version

import raphodo.programversions as programversions
from raphodo.constants import FileExtension, FileType
from raphodo.metadata.fileextensions import (
    AUDIO_EXTENSIONS,
    EXIFTOOL_ONLY_EXTENSIONS_STRINGS_AND_PREVIEWS,
    HEIF_EXTENTIONS,
    JPEG_EXTENSIONS,
    OTHER_PHOTO_EXTENSIONS,
    PHOTO_EXTENSIONS_SCAN,
    RAW_EXTENSIONS,
    VIDEO_EXTENSIONS,
)


def exiftool_capabilities() -> tuple[bool, bool]:
    """
    Determine if ExifTool can be used to read cr3 and heif/heic files
    """

    v = "unknown"
    try:
        if programversions.EXIFTOOL_VERSION is not None:
            v = parse_version(programversions.EXIFTOOL_VERSION)
            cr3 = v >= parse_version("10.87")
            heif = v >= parse_version("10.63")
            return cr3, heif
        return False, False
    except Exception:
        logging.error("Unable to compare ExifTool version number: %s", v)
        return False, False


_exiftool_cr3, _exiftool_heif = exiftool_capabilities()


def exiv2_cr3() -> bool:
    """
    Determine if exiv2 can be used to read cr3 files.
    """

    try:
        v = subprocess.check_output(["exiv2", "-V", "-v"]).strip().decode()
        return v.find("enable_bmff=1\n") >= 0
    except (OSError, subprocess.CalledProcessError):
        return False


_exiv2_cr3 = exiv2_cr3()


def cr3_capable() -> bool:
    """
    :return: True if either ExifTool or exiv2 can read CR3 files
    """
    return _exiftool_cr3 or _exiv2_cr3


def heif_capable() -> bool:
    return _exiftool_heif


if cr3_capable():
    RAW_EXTENSIONS.append("cr3")

RAW_EXTENSIONS.sort()

if not _exiv2_cr3 and _exiftool_cr3:
    EXIFTOOL_ONLY_EXTENSIONS_STRINGS_AND_PREVIEWS.append("cr3")

if heif_capable():
    OTHER_PHOTO_EXTENSIONS.extend(HEIF_EXTENTIONS)

VIDEO_EXTENSIONS.sort()


def use_exiftool_on_photo(extension: str, preview_extraction_irrelevant: bool) -> bool:
    """
    Determine if the file extension indicates its exif information
    must be extracted using ExifTool and not Exiv2.

    :param extension: lower case, no leading period
    :param preview_extraction_irrelevant: if True, return True only taking into
     account the exif string data, not the exif preview data
    """

    if extension in HEIF_EXTENTIONS:
        # Until ExifTool supports thumbnail extraction from HEIF files, we need to
        # load HEIF / HEIC files directly
        return preview_extraction_irrelevant

    return extension in EXIFTOOL_ONLY_EXTENSIONS_STRINGS_AND_PREVIEWS


def extract_extension(file_name) -> str | None:
    r"""
    Extract the file extension in the format the rest of the code expects:
    no leading period, lower case

    :param file_name: file name, irrelevant if path included or not
    :return: extension

    >>> print(extract_extension('myphoto.cr2'))
    cr2
    >>> print(extract_extension('myphoto.CR3'))
    cr3
    >>> print(extract_extension('/home/damon/myphoto.AVI'))
    avi
    >>> print(extract_extension('/home/damon/randomfile'))
    <BLANKLINE>
    """
    return os.path.splitext(file_name)[1][1:].lower()


def file_type(file_extension: str) -> FileType | None:
    r"""
    Check the file extension to determine if it is a photo or video

    :param file_extension: file extension in all lower case without leading period
    :return: file type (photo/video), or None if it's neither.

    >>> print(file_type('cr2'))
    FileType.photo
    >>> print(file_type('avi'))
    FileType.video
    >>> print(file_type('.AVI'))
    None
    >>> print(file_type('.cr2'))
    None
    >>> print(file_type('heif'))
    FileType.photo
    """

    if file_extension in PHOTO_EXTENSIONS_SCAN:
        return FileType.photo
    elif file_extension in VIDEO_EXTENSIONS:
        return FileType.video
    return None


def file_type_from_splitext(
    file_extension: str | None = None, file_name: str | None = None
) -> FileType | None:
    r"""
    Check file extension to determine if photo or video.

    Specify file_extension or file_name.

    :param file_extension: file extension as output by os.path.splitext()[1], i.e. with
     leading period and unknown case
    :param file_name: if not specifying the extension, the file's name
    :return: file type (photo/video), or None if it's neither.

    >>> print(file_type_from_splitext(file_extension='.CR2'))
    FileType.photo
    >>> print(file_type_from_splitext(file_extension='.avi'))
    FileType.video
    >>> print(file_type_from_splitext(file_extension='avi'))
    None
    >>> print(file_type_from_splitext(file_name='video.avi'))
    FileType.video
    >>> print(file_type_from_splitext(file_name='photo.CR2'))
    FileType.photo
    >>> print(file_type_from_splitext(file_name='photo.cr2'))
    FileType.photo
    >>> print(file_type_from_splitext(file_name='invalid_photo.XYZ'))
    None
    """

    if file_extension is not None:
        return file_type(file_extension[1:].lower())
    else:
        return file_type(extract_extension(file_name))


def extension_type(file_extension: str) -> FileExtension:
    """
    Returns the type of file as indicated by the filename extension.

    :param file_extension: lowercase filename extension
    :return: Enum indicating file type
    """
    if file_extension in RAW_EXTENSIONS:
        return FileExtension.raw
    elif file_extension in JPEG_EXTENSIONS:
        return FileExtension.jpeg
    elif file_extension in HEIF_EXTENTIONS:
        return FileExtension.heif
    elif file_extension in OTHER_PHOTO_EXTENSIONS:
        return FileExtension.other_photo
    elif file_extension in VIDEO_EXTENSIONS:
        return FileExtension.video
    elif file_extension in AUDIO_EXTENSIONS:
        return FileExtension.audio
    else:
        return FileExtension.unknown
