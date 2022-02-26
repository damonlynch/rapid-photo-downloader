#!/usr/bin/env python3

# Copyright (C) 2011-2021 Damon Lynch <damonlynch@gmail.com>

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

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2011-2021, Damon Lynch"

import datetime
import logging
from typing import Optional

import arrow.arrow
from arrow.arrow import Arrow

from raphodo.programversions import EXIFTOOL_VERSION
import raphodo.metadata.exiftool as exiftool
import raphodo.metadata.metadataexiftool as metadataexiftool
from raphodo.utilities import datetime_roughly_equal, arrow_shift_support
from raphodo.constants import FileType

try:
    import pymediainfo

    have_pymediainfo = True
    pymedia_library_file = "libmediainfo.so.0"
except ImportError:
    have_pymediainfo = False
    libmediainfo_missing = None

if have_pymediainfo:
    libmediainfo_missing = False
    try:
        if not pymediainfo.MediaInfo.can_parse(library_file=pymedia_library_file):
            # attempt to work around MediaInfoLib issue #695:
            # 'SONAME is different when compiling with CMake and autotools'
            pymedia_library_file = "libmediainfo.so.17"
            if not pymediainfo.MediaInfo.can_parse(library_file=pymedia_library_file):
                have_pymediainfo = False
                libmediainfo_missing = True
    except TypeError:
        # older versions of pymediainfo do not have the library_file option
        pymedia_library_file = None
        if not pymediainfo.MediaInfo.can_parse():
            have_pymediainfo = False
            libmediainfo_missing = True
    except AttributeError:
        try:
            # Attempt to parse null... it will fail if libmediainfo is not present,
            # which is what we want to check
            pymediainfo.MediaInfo.parse("/dev/null")
        except OSError:
            have_pymediainfo = False
            libmediainfo_missing = True
            pymedia_library_file = None


def pymedia_version_info() -> Optional[str]:
    if have_pymediainfo:
        if pymedia_library_file == "libmediainfo.so.0":
            return pymediainfo.__version__
        else:
            return "{} (using {})".format(pymediainfo.__version__, pymedia_library_file)
    else:
        return None


class MetaData(metadataexiftool.MetadataExiftool):
    def __init__(
        self,
        full_file_name: str,
        et_process: exiftool.ExifTool,
        file_type: Optional[FileType] = FileType.video,
    ):
        """
        Get video metadata using Exiftool or pymediainfo

        :param filename: the file from which to get metadata
        :param et_process: instance of ExifTool class, which allows
        calling ExifTool without it exiting with each call
        :param file_type
        """

        super().__init__(
            full_file_name=full_file_name, et_process=et_process, file_type=file_type
        )
        if have_pymediainfo:
            if pymedia_library_file is not None:
                self.media_info = pymediainfo.MediaInfo.parse(
                    filename=full_file_name, library_file=pymedia_library_file
                )  # type: pymediainfo.MediaInfo
            else:
                self.media_info = pymediainfo.MediaInfo.parse(
                    filename=full_file_name
                )  # type: pymediainfo.MediaInfo
        else:
            self.media_info = None

    def date_time(
        self, missing: Optional[str] = "", ignore_file_modify_date: bool = False
    ) -> datetime.datetime:
        """
        Use pymediainfo (if present) to extract file encoding date.

        Also use ExifTool if appropriate.

        :param ignore_file_modify_date: if True, don't return the file
        modification date
        :return  python datetime format the date and time the video was
        recorded, else missing
        """

        if have_pymediainfo:
            try:
                d = self.media_info.to_data()["tracks"][0]["encoded_date"]  # type: str
            except KeyError:
                logging.debug(
                    "Failed to extract date time from %s using pymediainfo: trying "
                    "ExifTool",
                    self.full_file_name,
                )
                return super().date_time(
                    missing=missing, ignore_file_modify_date=ignore_file_modify_date
                )
            else:
                # format of date string is something like:
                # UTC 2016-05-09 03:28:03
                try:
                    if d.startswith("UTC"):
                        u = d[4:]
                        a = arrow.get(u, "YYYY-MM-DD HH:mm:ss")  # type: Arrow
                        dt_mi = a.to("local")
                        dt = dt_mi.datetime  # type: datetime.datetime

                        # Compare the value returned by mediainfo against that
                        # returned by ExifTool, if and only if there is a time zone
                        # setting in the video file that ExifTool can extract
                        tz = self._get("TimeZone", None)
                        if tz is None:
                            logging.debug(
                                "Using pymediainfo datetime (%s), because ExifTool did "
                                "not detect a time zone in %s",
                                dt_mi,
                                self.full_file_name,
                            )
                        if tz is not None:
                            dt_et = super().date_time(
                                missing=None, ignore_file_modify_date=True
                            )
                            if dt_et is not None:
                                hour = tz // 60 * -1
                                minute = tz % 60 * -1
                                if arrow_shift_support:
                                    adjusted_dt_mi = dt_mi.shift(
                                        hours=hour, minutes=minute
                                    ).naive
                                else:
                                    adjusted_dt_mi = dt_mi.replace(
                                        hours=hour, minutes=minute
                                    ).naive
                                if datetime_roughly_equal(adjusted_dt_mi, dt_et):
                                    logging.debug(
                                        "Favoring ExifTool datetime metadata (%s) "
                                        "over mediainfo (%s) for %s, because it "
                                        "includes a timezone",
                                        dt_et,
                                        adjusted_dt_mi,
                                        self.full_file_name,
                                    )
                                    dt = dt_et
                                else:
                                    logging.debug(
                                        "Although ExifTool located a time zone"
                                        "in %s's metadata, using the mediainfo result, "
                                        "because the two results are different. "
                                        "Mediainfo: %s / %s (before / after). "
                                        " ExifTool: %s. Time zone: %s",
                                        self.full_file_name,
                                        dt,
                                        adjusted_dt_mi,
                                        dt_et,
                                        tz,
                                    )

                    else:
                        dt = datetime.datetime.strptime(d, "%Y-%m-%d %H:%M:%S")
                except (ValueError, OverflowError):
                    logging.warning(
                        "Error parsing date time metadata %s for video %s. Will try "
                        "ExifTool.",
                        d,
                        self.full_file_name,
                    )
                    return super().date_time(missing)
                except arrow.arrow.parser.ParserError:
                    logging.warning(
                        "Error parsing date time metadata using Arrow %s for video %s. "
                        "Will try ExifTool.",
                        d,
                        self.full_file_name,
                    )
                    return super().date_time(missing)
                except Exception as e:
                    logging.error(
                        "Unknown error parsing date time metadata %s for video %s. %s. "
                        "Will try ExifTool.",
                        d,
                        self.full_file_name,
                        e,
                    )
                    return super().date_time(missing)
                except:
                    logging.error(
                        "Unknown error parsing date time metadata %s for video %s. "
                        "Will try ExifTool.",
                        d,
                        self.full_file_name,
                    )
                    return super().date_time(missing)
                else:
                    return dt

        else:
            return super().date_time(missing)


class DummyMetaData:
    """
    Class which gives metadata values for an imaginary video.

    Useful for displaying in preference examples etc. when no video is ready to
    be downloaded.
    """

    def __init__(self, filename, et_process):
        pass

    def date_time(self, missing=""):
        return datetime.datetime.now()

    def codec(self, stream=0, missing=""):
        return "H.264 AVC"

    def length(self, missing=""):
        return "57"

    def width(self, stream=0, missing=""):
        return "1920"

    def height(self, stream=0, missing=""):
        return "1080"

    def frames_per_second(self, stream=0, missing=""):
        return "24"

    def fourcc(self, stream=0, missing=""):
        return "AVC1"


if __name__ == "__main__":
    import sys

    with exiftool.ExifTool() as et_process:
        if len(sys.argv) != 2:
            print("Usage: " + sys.argv[0] + " path/to/video/containing/metadata")
        else:
            file = sys.argv[1]

            print("ExifTool", EXIFTOOL_VERSION)
            m = MetaData(file, et_process)
            dt = m.date_time()
            print(dt)
            print("%sx%s" % (m.width(), m.height()))
            print("Length:", m.length())
            print("FPS: ", m.frames_per_second())
            print("Codec:", m.codec())
