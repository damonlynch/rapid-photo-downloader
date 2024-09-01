# SPDX-FileCopyrightText: Copyright 2007-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Commandline argument parser for Rapid Photo Downloader
"""

import builtins
import platform
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from pathlib import Path

try:
    from raphodo import __about__ as __about__
    from raphodo.internationalisation.install import install_gettext
    from raphodo.internationalisation.utilities import make_internationalized_list
    from raphodo.metadata.fileextensions import OTHER_PHOTO_EXTENSIONS

    install_gettext()
except ImportError:
    # The script is being run at build time
    # Module imports are unavailable

    def no_translation_performed(s: str) -> str:
        return s

    builtins.__dict__["_"] = no_translation_performed

    here = Path(__file__).parent
    with open(here / "__about__.py") as f:
        about = {}
        exec(f.read(), about)

    # Convert about dictionary to class
    class About:
        pass
    __about__ = About()
    __about__.__dict__.update(about)

    with open(here / "metadata/fileextensions.py") as f:
        file_extensions = {}
        exec(f.read(), file_extensions)
        OTHER_PHOTO_EXTENSIONS = file_extensions["OTHER_PHOTO_EXTENSIONS"]
    with open(here / "internationalisation/utilities.py") as f:
        utilities = {}
        exec(f.read(), utilities)
        make_internationalized_list = utilities["make_internationalized_list"]


def get_parser(formatter_class=RawDescriptionHelpFormatter) -> ArgumentParser:
    parser = ArgumentParser(
        prog=__about__.__title__,
        description=__about__.__summary__,
        epilog=__about__.__help_epilog__,
        formatter_class=formatter_class,
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__about__.__version__}",
    )
    parser.add_argument(
        "--detailed-version",
        action="store_true",
        help=_("Show version numbers of program and its libraries and exit."),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        dest="verbose",
        help=_("Display program information when run from the command line."),
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        dest="debug",
        help=_("Display debugging information when run from the command line."),
    )
    parser.add_argument(
        "-e",
        "--extensions",
        action="store_true",
        dest="extensions",
        help=_("List photo and video file extensions the program recognizes and exit."),
    )
    parser.add_argument(
        "--photo-renaming",
        choices=["on", "off"],
        dest="photo_renaming",
        help=_("Turn on or off the the renaming of photos."),
    )
    parser.add_argument(
        "--video-renaming",
        choices=["on", "off"],
        dest="video_renaming",
        help=_("Turn on or off the the renaming of videos."),
    )
    parser.add_argument(
        "-a",
        "--auto-detect",
        choices=["on", "off"],
        dest="auto_detect",
        help=_(
            "Turn on or off the automatic detection of devices from which to download."
        ),
    )
    parser.add_argument(
        "-t",
        "--this-computer",
        choices=["on", "off"],
        dest="this_computer_source",
        help=_("Turn on or off downloading from this computer."),
    )
    parser.add_argument(
        "--this-computer-location",
        type=str,
        metavar=_("PATH"),
        dest="this_computer_location",
        help=_("The PATH on this computer from which to download."),
    )
    parser.add_argument(
        "--photo-destination",
        type=str,
        metavar=_("PATH"),
        dest="photo_location",
        help=_("The PATH where photos will be downloaded to."),
    )
    parser.add_argument(
        "--video-destination",
        type=str,
        metavar=_("PATH"),
        dest="video_location",
        help=_("The PATH where videos will be downloaded to."),
    )
    parser.add_argument(
        "-b",
        "--backup",
        choices=["on", "off"],
        dest="backup",
        help=_("Turn on or off the backing up of photos and videos while downloading."),
    )
    parser.add_argument(
        "--backup-auto-detect",
        choices=["on", "off"],
        dest="backup_auto_detect",
        help=_("Turn on or off the automatic detection of backup devices."),
    )
    parser.add_argument(
        "--photo-backup-identifier",
        type=str,
        metavar=_("FOLDER"),
        dest="photo_backup_identifier",
        help=_(
            "The FOLDER in which backups are stored on the automatically detected "
            "photo backup device, with the folder's name being used to identify "
            "whether or not the device is used for backups. For each device you wish "
            "to use for backing photos up to, create a folder on it with this name."
        ),
    )
    parser.add_argument(
        "--video-backup-identifier",
        type=str,
        metavar=_("FOLDER"),
        dest="video_backup_identifier",
        help=_(
            "The FOLDER in which backups are stored on the automatically detected "
            "video backup device, with the folder's name being used to identify "
            "whether or not the device is used for backups. For each device you wish "
            "to use for backing up videos to, create a folder on it with this name."
        ),
    )
    parser.add_argument(
        "--photo-backup-location",
        type=str,
        metavar=_("PATH"),
        dest="photo_backup_location",
        help=_(
            "The PATH where photos will be backed up when automatic detection of "
            "backup devices is turned off."
        ),
    )
    parser.add_argument(
        "--video-backup-location",
        type=str,
        metavar=_("PATH"),
        dest="video_backup_location",
        help=_(
            "The PATH where videos will be backed up when automatic detection of "
            "backup devices is turned off."
        ),
    )
    parser.add_argument(
        "--ignore-other-photo-file-types",
        action="store_true",
        dest="ignore_other",
        help=_("Ignore photos with the following extensions: %s")
        % make_internationalized_list([s.upper() for s in OTHER_PHOTO_EXTENSIONS]),
    )
    parser.add_argument(
        "--auto-download-startup",
        dest="auto_download_startup",
        choices=["on", "off"],
        help=_(
            "Turn on or off starting downloads as soon as the program itself starts."
        ),
    )
    parser.add_argument(
        "--auto-download-device-insertion",
        dest="auto_download_insertion",
        choices=["on", "off"],
        help=_("Turn on or off starting downloads as soon as a device is inserted."),
    )
    parser.add_argument(
        "--thumbnail-cache",
        dest="thumb_cache",
        choices=["on", "off"],
        help=_(
            "Turn on or off use of the Rapid Photo Downloader Thumbnail Cache. "
            "Turning it off does not delete existing cache contents."
        ),
    )
    parser.add_argument(
        "--delete-thumbnail-cache",
        dest="delete_thumb_cache",
        action="store_true",
        help=_(
            "Delete all thumbnails in the Rapid Photo Downloader Thumbnail Cache, "
            "and exit."
        ),
    )
    parser.add_argument(
        "--forget-remembered-files",
        dest="forget_files",
        action="store_true",
        help=_("Forget which files have been previously downloaded, and exit."),
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        dest="reset",
        help=_(
            "Reset all program settings to their default values, delete all thumbnails "
            "in the Thumbnail cache, forget which files have been previously "
            "downloaded, and exit."
        ),
    )
    parser.add_argument(
        "--log-gphoto2",
        action="store_true",
        help=_("Include gphoto2 debugging information in log files."),
    )

    parser.add_argument(
        "--camera-info",
        action="store_true",
        help=_("Print information to the terminal about attached cameras and exit."),
    )

    parser.add_argument(
        "--force-system-theme",
        action="store_true",
        default=False,
        help=_("Use the system Qt theme instead of the built-in theme"),
    )

    parser.add_argument(
        "path",
        nargs="?",
        # Translators: this string appears when running the program from the command
        # line using the --help option, and refers to the optional PATH option.
        help=_(
            "Optional value that when specified, is parsed to determine if it "
            "represents an automatically detected device or a path on this computer. "
            "If the PATH represents an automatically detected device, automatic "
            "detection of devices is turned on, as in the '--auto-detect option'. "
            "Furthermore, downloading from a manually specified path as in the "
            "'--this-computer-location' option is turned off. "
            "Otherwise, the PATH is assumed to be a manually specified path as in the "
            "'--this-computer-location' option, in which case downloading from this "
            "computer is turned on and downloading from automatically detected devices "
            "is turned off."
        ),
    )

    if platform.system() == "Linux":
        parser.add_argument(
            "-platform",
            type=str,
            choices=["wayland", "xcb"],
            help=_("Run this program in wayland or regular X11"),
        )

    return parser
