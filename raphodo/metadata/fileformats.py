#  SPDX-FileCopyrightText: 2011-2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: GPL-3.0-or-later

import os

from raphodo.constants import FileExtension, FileType

RAW_EXTENSIONS = [
    "3fr",
    "arw",
    "dcr",
    "cr2",
    "cr3",
    "crw",
    "dng",
    "fff",
    "iiq",
    "mos",
    "mef",
    "mrw",
    "nef",
    "nrw",
    "orf",
    "ori",
    "pef",
    "raf",
    "raw",
    "rw2",
    "sr2",
    "srw",
    "x3f",
]

RAW_EXTENSIONS.sort()

EXIFTOOL_ONLY_EXTENSIONS_STRINGS_AND_PREVIEWS = ["mos", "mrw", "x3f"]

HEIF_EXTENSIONS = ["heif", "heic", "hif"]
# Synchronize with the value OTHER_PHOTO_EXTENSIONS in argumentsparse.py
OTHER_PHOTO_EXTENSIONS = ["tif", "tiff", "mpo"]

VIDEO_EXTENSIONS = [
    "3gp",
    "avi",
    "lrv",
    "m2t",
    "m2ts",
    "mov",
    "mp4",
    "mpeg",
    "mpg",
    "mod",
    "tod",
    "mts",
    "nev",
    "braw",
    "crm",
]
VIDEO_EXTENSIONS.sort()


JPEG_EXTENSIONS = ["jpg", "jpe", "jpeg"]
NON_RAW_IMAGE_EXTENSIONS = JPEG_EXTENSIONS + HEIF_EXTENSIONS + OTHER_PHOTO_EXTENSIONS
PHOTO_EXTENSIONS = RAW_EXTENSIONS + NON_RAW_IMAGE_EXTENSIONS
PHOTO_EXTENSIONS_WITHOUT_OTHER = RAW_EXTENSIONS + JPEG_EXTENSIONS + HEIF_EXTENSIONS
PHOTO_EXTENSIONS_SCAN = PHOTO_EXTENSIONS
AUDIO_EXTENSIONS = ["wav", "mp3"]
VIDEO_THUMBNAIL_EXTENSIONS = ["thm"]
ALL_USER_VISIBLE_EXTENSIONS = PHOTO_EXTENSIONS + VIDEO_EXTENSIONS + ["xmp", "log"]
ALL_KNOWN_EXTENSIONS = (
    ALL_USER_VISIBLE_EXTENSIONS + AUDIO_EXTENSIONS + VIDEO_THUMBNAIL_EXTENSIONS
)


def use_exiftool_on_photo(extension: str, preview_extraction_irrelevant: bool) -> bool:
    """
    Determine if the file extension indicates its exif information
    must be extracted using ExifTool and not Exiv2.

    :param extension: lower case, no leading period
    :param preview_extraction_irrelevant: if True, return True only taking into
     account the exif string data, not the exif preview data
    """

    if extension in HEIF_EXTENSIONS:
        # Until ExifTool supports thumbnail extraction from HEIF files, we need to
        # load HEIF / HEIC files directly
        return preview_extraction_irrelevant

    return extension in EXIFTOOL_ONLY_EXTENSIONS_STRINGS_AND_PREVIEWS


def extract_extension(file_name: str) -> str:
    """
    Extract the file extension in the format the rest of the code expects:
    no leading period, lower case

    :param file_name: file name, irrelevant if path included or not
    :return: extension, or "" if there is no extension

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
    """
    Check the file extension to determine if it is a photo or video

    :param file_extension: file extension in all lower case without leading period
    :return: file type (photo/video), or None if it's neither.

    >>> file_type('cr2').name
    'photo'
    >>> file_type('avi').name
    'video'
    >>> file_type('.AVI') is None
    True
    >>> file_type('.cr2') is None
    True
    >>> file_type('heif').name
    'photo'
    """

    if file_extension in PHOTO_EXTENSIONS_SCAN:
        return FileType.photo
    elif file_extension in VIDEO_EXTENSIONS:
        return FileType.video
    return None


def file_type_from_splitext(
    file_extension: str | None = None, file_name: str | None = None
) -> FileType | None:
    """
    Check file extension to determine if photo or video.

    Specify file_extension or file_name.

    :param file_extension: file extension as output by os.path.splitext()[1], i.e. with
     leading period and unknown case
    :param file_name: if not specifying the extension, the file's name
    :return: file type (photo/video), or None if it is neither.

    >>> file_type_from_splitext(file_extension='.CR2').name
    'photo'
    >>> file_type_from_splitext(file_extension='.avi').name
    'video'
    >>> file_type_from_splitext(file_extension='avi') is None
    True
    >>> file_type_from_splitext(file_name='video.avi').name
    'video'
    >>> file_type_from_splitext(file_name='photo.CR2').name
    'photo'
    >>> file_type_from_splitext(file_name='photo.cr2').name
    'photo'
    >>> file_type_from_splitext(file_name='invalid_photo.XYZ') is None
    True
    """

    if file_extension is not None:
        return file_type(file_extension[1:].lower())
    if file_name is not None:
        return file_type(extract_extension(file_name))
    return None


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
    elif file_extension in HEIF_EXTENSIONS:
        return FileExtension.heif
    elif file_extension in OTHER_PHOTO_EXTENSIONS:
        return FileExtension.other_photo
    elif file_extension in VIDEO_EXTENSIONS:
        return FileExtension.video
    elif file_extension in AUDIO_EXTENSIONS:
        return FileExtension.audio
    return FileExtension.unknown
