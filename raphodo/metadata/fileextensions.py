# SPDX-FileCopyrightText: Copyright 2011-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later


RAW_EXTENSIONS = [
    "3fr",
    "arw",
    "dcr",
    "cr2",
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
HEIF_EXTENTIONS = ["heif", "heic", "hif"]
EXIFTOOL_ONLY_EXTENSIONS_STRINGS_AND_PREVIEWS = ["mos", "mrw", "x3f"]
JPEG_EXTENSIONS = ["jpg", "jpe", "jpeg"]
JPEG_TYPE_EXTENSIONS = ["jpg", "jpe", "jpeg", "mpo"]
OTHER_PHOTO_EXTENSIONS = ["tif", "tiff", "mpo"]
NON_RAW_IMAGE_EXTENSIONS = JPEG_EXTENSIONS + OTHER_PHOTO_EXTENSIONS
PHOTO_EXTENSIONS = RAW_EXTENSIONS + NON_RAW_IMAGE_EXTENSIONS
PHOTO_EXTENSIONS_WITHOUT_OTHER = RAW_EXTENSIONS + JPEG_EXTENSIONS
PHOTO_EXTENSIONS_SCAN = PHOTO_EXTENSIONS
AUDIO_EXTENSIONS = ["wav", "mp3"]
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
]
VIDEO_THUMBNAIL_EXTENSIONS = ["thm"]
ALL_USER_VISIBLE_EXTENSIONS = PHOTO_EXTENSIONS + VIDEO_EXTENSIONS + ["xmp", "log"]
ALL_KNOWN_EXTENSIONS = (
    ALL_USER_VISIBLE_EXTENSIONS + AUDIO_EXTENSIONS + VIDEO_THUMBNAIL_EXTENSIONS
)
