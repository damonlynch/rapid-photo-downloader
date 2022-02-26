#!/usr/bin/env python3

# Copyright (C) 2007-2021 Damon Lynch <damonlynch@gmail.com>

# This file is part of Rapid Photo Downloader.
#
# Rapid Photo Downloader is free software: you can redistribute it and/or
# modify
# it under the terms of the GNU General Public License as published by
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
__copyright__ = "Copyright 2007-2021, Damon Lynch"

import datetime
from typing import Optional, Union, Any, Tuple
import logging

import gi

gi.require_version("GExiv2", "0.10")
from gi.repository import GExiv2
from PyQt5.QtCore import QSize

import raphodo.metadata.exiftool as exiftool
import raphodo.metadata.metadataexiftool as metadataexiftool
from raphodo.utilities import flexible_date_time_parser, image_large_enough_fdo
from raphodo.constants import FileType


VENDOR_SERIAL_CODES = (
    "Exif.Photo.BodySerialNumber",
    "Exif.Canon.SerialNumber",
    "Exif.Nikon3.SerialNumber",
    "Exif.OlympusEq.SerialNumber",
    "Exif.Olympus.SerialNumber",
    "Exif.Olympus.SerialNumber2",
    "Exif.Panasonic.SerialNumber",
    "Exif.Fujifilm.SerialNumber",
    "Exif.Image.CameraSerialNumber",
)

VENDOR_SHUTTER_COUNT = (
    "Exif.Nikon3.ShutterCount",
    "Exif.Canon.FileNumber",
    "Exif.Canon.ImageNumber",
)


def photo_date_time(
    metadata: GExiv2.Metadata,
    full_file_name: Optional[str] = None,
    file_type: Optional[FileType] = None,
) -> Union[datetime.datetime, Any]:
    """
    Returns in python datetime format the date and time the image was
    recorded.

    Tries these tags, in order:
    Exif.Photo.DateTimeOriginal
    Exif.Image.DateTimeOriginal
    Exif.Image.DateTime

    :return: metadata value, or None if value is not present.
    """

    # GExiv2.Metadata used to provide get_date_time(), but as of version
    # 0.10.09 it appears to have been removed!

    # In any case, get_date_time() seems to have tried only one key,
    # Exif.Photo.DateTimeOriginal
    # Try other keys too, and with a more flexible datetime parser.
    # For example some or maybe all Android 6.0 DNG files use
    # Exif.Image.DateTimeOriginal

    do_log = full_file_name is not None and file_type is not None

    for tag in (
        "Exif.Photo.DateTimeOriginal",
        "Exif.Image.DateTimeOriginal",
        "Exif.Image.DateTime",
    ):
        try:
            dt_string = metadata.get_tag_string(tag)
        except Exception:
            pass
        else:
            if dt_string is None:
                continue

            # ignore all zero values, e.g. '0000:00:00 00:00:00'
            try:
                digits = int("".join(c for c in dt_string if c.isdigit()))
            except ValueError:
                if do_log:
                    logging.warning(
                        "Unexpected malformed date time metadata value %s for photo %s",
                        dt_string,
                        full_file_name,
                    )
            else:
                if not digits:
                    if do_log:
                        logging.debug(
                            "Ignoring date time metadata value %s for photo %s",
                            dt_string,
                            full_file_name,
                        )
                else:
                    try:
                        return datetime.datetime.strptime(
                            dt_string, "%Y:%m:%d %H:%M:%S"
                        )
                    except (ValueError, OverflowError):
                        if do_log:
                            logging.debug(
                                "Error parsing date time metadata %s for photo %s; "
                                "attempting flexible approach",
                                dt_string,
                                full_file_name,
                            )
                        try:
                            dtr, fs = flexible_date_time_parser(dt_string.strip())
                            if do_log:
                                logging.debug(
                                    "Extracted photo time %s using flexible approach",
                                    dtr.strftime(fs),
                                )
                            return dtr
                        except AssertionError:
                            if do_log:
                                logging.warning(
                                    "Error extracting date time metadata '%s' for "
                                    "%s %s",
                                    dt_string,
                                    file_type,
                                    full_file_name,
                                )
                        except (ValueError, OverflowError):
                            if do_log:
                                logging.warning(
                                    "Error parsing date time metadata '%s' for %s %s",
                                    dt_string,
                                    file_type,
                                    full_file_name,
                                )
                        except Exception:
                            if do_log:
                                logging.error(
                                    "Unknown error parsing date time metadata '%s' "
                                    "for %s %s",
                                    dt_string,
                                    file_type,
                                    full_file_name,
                                )
    return None


class MetaData(metadataexiftool.MetadataExiftool, GExiv2.Metadata):
    """
    Provide abstracted access to photo metadata
    """

    def __init__(
        self,
        et_process: exiftool.ExifTool,
        full_file_name: Optional[str] = None,
        raw_bytes: Optional[bytearray] = None,
        app1_segment: Optional[bytearray] = None,
    ) -> None:
        """
        Use GExiv2 to read the photograph's metadata.

        :param et_process: deamon exiftool process
        :param full_file_name: full path of file from which file to read
         the metadata.
        :param raw_bytes: portion of a non-jpeg file from which the
         metadata can be extracted
        :param app1_segment: the app1 segment of a jpeg file, from which
         the metadata can be read
        """

        super().__init__(full_file_name, et_process, FileType.photo)

        self.et_process = et_process

        if full_file_name:
            self.open_path(full_file_name)
        else:
            if raw_bytes is not None:
                self.open_buf(raw_bytes)
            else:
                assert app1_segment is not None
                self.from_app1_segment(app1_segment)

    def _get_rational_components(self, tag: str) -> Optional[Tuple[Any, Any]]:
        try:
            x = self.get_exif_tag_rational(tag)
        except Exception:
            return None, None

        try:
            return x.numerator, x.denominator
        except AttributeError:
            try:
                return x.nom, x.den
            except Exception:
                return None, None

    def _get_rational(self, tag: str) -> Optional[float]:
        x, y = self._get_rational_components(tag)
        if x is not None and y is not None:
            return float(x) / float(y)

    def aperture(self, missing="") -> Union[str, Any]:
        """
        Returns in string format the floating point value of the image's
        aperture.

        Returns missing if the metadata value is not present.
        """

        a = self._get_rational("Exif.Photo.FNumber")

        if a is None:
            return missing
        else:
            return "{:.1f}".format(a)

    def iso(self, missing="") -> Union[str, Any]:
        """
        Returns in string format the integer value of the image's ISO.

        Returns missing if the metadata value is not present.
        """

        try:
            v = self.get_tag_interpreted_string("Exif.Photo.ISOSpeedRatings")
            if v:
                return v
            else:
                return missing
        except (KeyError, AttributeError):
            return missing

    def _exposure_time_rational(self) -> Tuple[Any, Any]:
        return self._get_rational_components("Exif.Photo.ExposureTime")

    def focal_length(self, missing=""):
        """
        Returns in string format the focal length of the lens used to record
        the image.

        Returns missing if the metadata value is not present.
        """

        f = self._get_rational("Exif.Photo.FocalLength")
        if f is not None:
            return "%.0f" % f
        else:
            return missing

    def camera_make(self, missing=""):
        """
        Returns in string format the camera make (manufacturer) used to
        record the image.

        Returns missing if the metadata value is not present.
        """

        try:
            return self.get_tag_string("Exif.Image.Make").strip()
        except (KeyError, AttributeError):
            return missing

    def camera_model(self, missing=""):
        """
        Returns in string format the camera model used to record the image.

        Returns missing if the metadata value is not present.
        """

        try:
            return self.get_tag_string("Exif.Image.Model").strip()
        except (KeyError, AttributeError):
            return missing

    def _fetch_vendor(self, vendor_codes, missing=""):
        for key in vendor_codes:
            try:
                return self.get_tag_string(key).strip()
            except (KeyError, AttributeError):
                pass
        return missing

    def camera_serial(self, missing=""):
        return self._fetch_vendor(VENDOR_SERIAL_CODES, missing)

    def shutter_count(self, missing=""):
        shutter = self._fetch_vendor(VENDOR_SHUTTER_COUNT, missing)
        if shutter != missing:
            return shutter

        if self.full_file_name is None:
            return missing

        if self.camera_make().lower() == "sony":
            try:
                ic = self.et_process.get_tags(["ImageCount"], self.full_file_name)
            except (ValueError, TypeError):
                return missing
            if ic:
                return ic.get("ImageCount", missing)

        return missing

    def file_number(self, missing=""):
        """
        Returns Exif.CanonFi.FileNumber, not to be confused with
        Exif.Canon.FileNumber.

        Uses ExifTool to extract the value, because the exiv2
        implementation is currently problematic

        See:
        https://bugs.launchpad.net/rapid/+bug/754531
        """
        if "Exif.CanonFi.FileNumber" in self and self.full_file_name is not None:
            assert self.et_process is not None
            return super().file_number(missing)

    def owner_name(self, missing=""):
        try:
            return self.get_tag_string("Exif.Canon.OwnerName").strip()
        except (KeyError, AttributeError):
            return missing

    def copyright(self, missing=""):
        try:
            return self.get_tag_string("Exif.Image.Copyright").strip()
        except (KeyError, AttributeError):
            return missing

    def artist(self, missing=""):
        try:
            return self.get_tag_string("Exif.Image.Artist").strip()
        except (KeyError, AttributeError):
            return missing

    def date_time(
        self,
        missing: Optional[str] = "",
        ignore_file_modify_date: Optional[bool] = False,
    ) -> Union[datetime.datetime, Any]:
        """
        Returns in python datetime format the date and time the image was
        recorded.

        Tries these tags, in order:
        Exif.Photo.DateTimeOriginal
        Exif.Image.DateTimeOriginal
        Exif.Image.DateTime

        :return: metadata value, or missing if value is not present.
        """

        dt = photo_date_time(
            metadata=self, full_file_name=self.full_file_name, file_type=self.file_type
        )

        if dt is None:
            return missing
        else:
            return dt

    def sub_seconds(self, missing="00") -> Union[str, Any]:
        """
        Returns the subsecond the image was taken, as recorded by the
        camera
        """

        try:
            return self.get_tag_string("Exif.Photo.SubSecTimeOriginal")
        except (KeyError, AttributeError):
            return missing

    def orientation(self, missing="") -> Union[str, Any]:
        """
        Returns the orientation of the image, as recorded by the camera
        Return type int
        """

        try:
            return self.get_tag_string("Exif.Image.Orientation")
        except (KeyError, AttributeError):
            return missing

    def get_small_thumbnail(self) -> bytes:
        """
        Get the small thumbnail image (if it exists)
        :return: thumbnail image in raw bytes (could be zero bytes)
        """

        return self.get_exif_thumbnail()

    def get_indexed_preview(self) -> Optional[bytes]:
        """
        Extract preview image from the metadata

        :param preview_number: which preview to get
        :return: preview image in raw bytes, if found, else None
        """

        previews = self.get_preview_properties()
        if previews:
            # In every RAW file I've analyzed, the smallest preview is always first
            for preview in previews:
                data = self.get_preview_image(preview).get_data()
                if data:
                    return data
        logging.warning("Photo %s has no image previews", self.full_file_name)
        return None

    def get_small_thumbnail_or_first_indexed_preview(self) -> Optional[bytes]:
        """
        First attempt to get the small thumbnail image. If it does not exist,
        extract the smallest preview image from the metadata

        :return: thumbnail / preview image in raw bytes, if found, else None
        """

        # Look for Thumbnail Image if the file format supports it
        if self.ext not in self.preview_smallest or self.ext in self.may_have_thumbnail:
            thumbnail = self.get_small_thumbnail()
            if thumbnail:
                return thumbnail

        # Otherwise look for the smallest preview image for this format
        return self.get_indexed_preview()

    def get_preview_256(self) -> Optional[bytes]:
        """
        :return: if possible, return a preview image that is preferrably larger than
         256 pixels, else the smallest preview if it exists
        """

        previews = self.get_preview_properties()
        if not previews:
            return None

        for preview in previews:
            if image_large_enough_fdo(QSize(preview.get_width(), preview.get_height())):
                if not (
                    self.ext in self.ignore_tiff_preview_256
                    and preview.get_mime_type() == "image/tiff"
                ):
                    break

        # At this point we have a preview that may or may not be bigger than 160x120.
        # On older RAW files, no. On newer RAW files, yes.
        return self.get_preview_image(preview).get_data()


class DummyMetaData(MetaData):
    """
    Class which gives metadata values for an imaginary photo.

    Useful for displaying in preference examples etc. when no image is ready to
    be downloaded.

    See MetaData class for documentation of class methods.
    """

    def __init__(self):
        pass

    def readMetadata(self):
        pass

    def aperture(self, missing=""):
        return "2.0"

    def iso(self, missing=""):
        return "100"

    def exposure_time(self, alternativeFormat=False, missing=""):
        if alternativeFormat:
            return "4000"
        else:
            return "1/4000"

    def focal_length(self, missing=""):
        return "135"

    def camera_make(self, missing=""):
        return "Canon"

    def camera_model(self, missing=""):
        return "Canon EOS 5D"

    def short_camera_model(self, includeCharacters="", missing=""):
        return "5D"

    def camera_serial(self, missing=""):
        return "730402168"

    def shutter_count(self, missing=""):
        return "387"

    def owner_name(self, missing=""):
        return "Photographer Name"

    def date_time(self, missing="", ignore_file_modify_date=False):
        return datetime.datetime.now()

    def subSeconds(self, missing="00"):
        return "57"

    def orientation(self, missing=""):
        return 1

    def file_number(self, missing=""):
        return "428"


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: " + sys.argv[0] + " path/to/photo/containing/metadata")
        m = DummyMetaData()
        et_process = None
    else:
        et_process = exiftool.ExifTool()
        et_process.start()
        m = MetaData(full_file_name=sys.argv[1], et_process=et_process)

    print("f" + m.aperture("missing "))
    print("ISO " + m.iso("missing "))
    print(m.exposure_time(missing="missing ") + " sec")
    print(m.exposure_time(alternativeFormat=True, missing="missing "))
    print(m.focal_length("missing ") + "mm")
    print(m.camera_make())
    print(m.camera_model())
    print(m.short_camera_model())
    print(m.short_camera_model(includeCharacters="\-"))
    print(m.date_time())
    print(m.orientation())
    print("Serial number:", m.camera_serial(missing="missing"))
    print("Shutter count:", m.shutter_count())
    print("Subseconds:", m.sub_seconds(), type(m.sub_seconds()))
    print("File number:", m.file_number())
    preview = m.get_small_thumbnail_or_first_indexed_preview()
    if m is not None:
        print("Preview size", len(preview))
    else:
        print("Preview not availabe")

    if et_process is not None:
        et_process.terminate()
