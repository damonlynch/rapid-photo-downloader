#!/usr/bin/env python3

# Copyright (C) 2007-2018 Damon Lynch <damonlynch@gmail.com>

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

"""
Read photo and video metadata using ExifTool daemon process.
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2007-2018, Damon Lynch"

import datetime
import re
import logging
from typing import Optional, Union, Any, Tuple, List
from collections import OrderedDict

import raphodo.exiftool as exiftool
from raphodo.utilities import flexible_date_time_parser
from raphodo.constants import FileType
import raphodo.programversions as programversions
import raphodo.fileformats as fileformats


# Turned into an OrderedDict below
_index_preview = {
            0: 'PreviewImage',
            1: 'OtherImage',
            2: 'JpgFromRaw',
            3: 'PreviewTIFF',
            4: 'ThumbnailTIFF'
}

class MetadataExiftool():
    """
    Read photo and video metadata using exiftool daemon process.
    """

    def __init__(self, full_file_name: str,
                 et_process: exiftool.ExifTool,
                 file_type: Optional[FileType]=None) -> None:
        """
        Get photo and video metadata using Exiftool

        :param filename: the file from which to get metadata
        :param et_process: instance of ExifTool class, which allows
        calling EXifTool without it exiting with each call
        :param file_type: photo or video. If not specified, will be determined
         using file extension
        """

        super().__init__()

        self.full_file_name = full_file_name
        if full_file_name is not None:
            self.ext = fileformats.extract_extension(full_file_name)
        else:
            self.ext = None
        self.metadata = dict()
        self.metadata_string_format = dict()
        self.et_process = et_process
        if file_type is None and full_file_name is not None:
            file_type = fileformats.file_type_from_splitext(file_name=full_file_name)
        assert file_type is not None
        self.file_type = file_type

        # All the names of the preview images we know about (there may be more, perhaps)
        # Synchronize with preview_smallest and preview256 dicts below
        self.index_preview = OrderedDict(sorted(_index_preview.items(), key=lambda t: t[0]))

        # If extension is not in dict preview_smallest, that means the file
        # format always contains a "ThumbnailImage"
        self.preview_smallest = dict(
            crw=(2, ),
            dng=(4, 3, 0),
            fff=(3, ),
            iiq=(4, ),
            mrw=(0, ),
            nef=(4, 3),
            raw=(2, ),
        )
        self.preview_smallest['3fr'] = 3, 4

        self.may_have_thumbnail = ('crw', 'mrw', 'orf', 'raw', 'x3f')

        self.preview256 = dict(
            arw=(0, ),
            cr2=(0, ),
            cr3=(0, ),
            crw=(2, ),
            dng=(0, 3),
            fff=(3, ),
            iiq=(4, ),
            mrw=(0, ),
            nef=(0, 4, 2, 3),  # along with DNG quite possibly the most inconsistent format
            nrw=(0, 1),
            orf=(0, ),
            pef=(0, ),
            raf=(0, ),
            raw=(2, ),
            rw2=(2, ),
            sr2=(0, ),
            srw=(0, ),
            x3f=(0, 2),
        )
        self.preview256['3fr'] = 3, 4

        self.ignore_tiff_preview_256 = ('cr2', )

    def _get(self, key, missing):
        if key in ("VideoStreamType", "FileNumber", "ExposureTime"):
            # special cases: want ExifTool's string formatting
            # i.e. no -n tag
            if not self.metadata_string_format:
                try:
                    self.metadata_string_format = \
                        self.et_process.execute_json_no_formatting(self.full_file_name)
                except ValueError:
                    return missing
            try:
                return self.metadata_string_format[0][key]
            except:
                return missing

        elif not self.metadata:
            try:
                self.metadata = self.et_process.get_metadata(self.full_file_name)
            except ValueError:
                return missing

        return self.metadata.get(key, missing)

    def date_time(self, missing: Optional[str]='',
                            ignore_file_modify_date: bool = False) -> Union[datetime.datetime, Any]:
        """
        Tries to get value from key "DateTimeOriginal"
        If that fails, tries "CreateDate", and then finally
        FileModifyDate

        :param ignore_file_modify_date: if True, don't return the file
        modification date
        :return  python datetime format the date and time the video or photo was
        recorded, else missing
        """

        d = self._get('DateTimeOriginal', None)
        if d is None:
            d = self._get('CreateDate', None)
        if d is None and not ignore_file_modify_date:
            d = self._get('FileModifyDate', None)
        if d is not None:
            d = d.strip()
            try:
                dt, fs = flexible_date_time_parser(d)
                logging.debug(
                    "Extracted %s time %s using ExifTool", self.file_type.name, dt.strftime(fs)
                )

            except AssertionError:
                logging.warning(
                    "Error extracting date time metadata '%s' for %s %s",
                    d, self.file_type.name, self.full_file_name
                )
                return missing

            except (ValueError, OverflowError):
                logging.warning(
                    "Error parsing date time metadata '%s' for %s %s",
                    d, self.file_type.name, self.full_file_name
                )
                return missing
            except Exception:
                logging.error(
                    "Unknown error parsing date time metadata '%s' for %s %s",
                    d, self.file_type.name, self.full_file_name
                )
                return missing

            return dt
        else:
            return missing

    def timestamp(self, missing='') -> Union[float, Any]:
        """
        Photo and Video
        :return: a float value representing the time stamp, if it exists
        """

        dt = self.date_time(missing=None)
        if dt is not None:
            try:
                ts = dt.timestamp()
                ts = float(ts)
            except:
                ts = missing
        else:
            ts = missing
        return ts

    def file_number(self, missing='') -> Union[str, Any]:
        """
        Photo and video
        :return: a string value representing the File number, if it exists
        """

        v = self._get("FileNumber", None)
        if v is not None:
            return str(v)
        else:
            return missing

    def width(self, missing='') -> Union[str, Any]:
        v = self._get('ImageWidth', None)
        if v is not None:
            return str(v)
        else:
            return missing

    def height(self, missing='') -> Union[str, Any]:
        v = self._get('ImageHeight', None)
        if v is not None:
            return str(v)
        else:
            return missing

    def length(self, missing='') -> Union[str, Any]:
        """
        return the duration (length) of the video, rounded to the nearest second, in string format
        """
        v = self._get("Duration", None)
        if v is not None:
            try:
                v = float(v)
                v = "%0.f" % v
            except:
                return missing
            return v
        else:
            return missing

    def frames_per_second(self, missing='') -> Union[str, Any]:
        v = self._get("FrameRate", None)
        if v is None:
            v = self._get("VideoFrameRate", None)

        if v is None:
            return missing
        try:
            v = '%.0f' % v
        except:
            return missing
        return v

    def codec(self, missing='') -> Union[str, Any]:
        v = self._get("VideoStreamType", None)
        if v is None:
            v = self._get("VideoCodec", None)
        if v is not None:
            return v
        return missing

    def fourcc(self, missing='') -> Union[str, Any]:
        return self._get("CompressorID", missing)

    def rotation(self, missing=0) -> Union[int, Any]:
        v = self._get("Rotation", None)
        if v is not None:
            return v
        return missing

    def aperture(self, missing='') -> Union[str, Any]:
        """
        Returns in string format the floating point value of the image's
        aperture.

        Returns missing if the metadata value is not present.
        """
        v = self._get('FNumber', None)
        try:
            v = float(v)
        except (ValueError, TypeError):  # TypeError catches None
            return missing

        if v is not None:
            return "{:.1f}".format(v)
        return missing

    def iso(self, missing='') -> Union[str, Any]:
        """
        Returns in string format the integer value of the image's ISO.

        Returns missing if the metadata value is not present.
        """
        v = self._get('ISO', None)
        if v:
            return str(v)
        return missing


    def _exposure_time_rational(self, missing=None) -> Tuple[Any, Any]:
        """
        Split exposure time value into fraction for further processing
        :param missing:
        :return: tuple of exposure time e.g. '1', '320' (for 1/320 sec)
          or '2.5', 1 (for 2.5 secs)
        """

        v = self._get('ExposureTime', None)
        if v is None:
            return missing, missing
        v = str(v)

        # ExifTool returns two distinct types values e.g.:
        # '1/125' fraction (string)
        # '2.5' floating point

        # fractional format
        if v.find('/') > 0:
            return tuple(v.split('/')[:2])

        # already in floating point format
        return v, 1

    def exposure_time(self, alternativeFormat=False, missing='') -> Union[str, Any]:
        """
        Returns in string format the exposure time of the image.

        Returns missing if the metadata value is not present.

        alternativeFormat is useful if the value is going to be  used in a
        purpose where / is an invalid character, e.g. file system names.

        alternativeFormat is False:
        For exposures less than one second, the result is formatted as a
        fraction e.g. 1/125
        For exposures greater than or equal to one second, the value is
        formatted as an integer e.g. 30

        alternativeFormat is True:
        For exposures less than one second, the result is formatted as an
        integer e.g. 125
        For exposures less than one second but more than or equal to
        one tenth of a second, the result is formatted as an integer
        e.g. 3 representing 3/10 of a second
        For exposures greater than or equal to one second, the value is
        formatted as an integer with a trailing s e.g. 30s
        """

        e0, e1 = self._exposure_time_rational()

        if e0 is not None and e1 is not None:

            if str(e0).find('.') > 0:
                try:
                    assert e1 == 1
                except AssertionError as e:
                    logging.exception('{}: {}, {}'.format(self.full_file_name, e0, e1))
                    raise AssertionError from e
                e0 = float(e0)
            else:
                try:
                    e0 = int(e0)
                    e1 = int(e1)
                except ValueError as e:
                    logging.exception('{}: {}, {}'.format(self.full_file_name, e0, e1))
                    raise ValueError from e

            if e1 > e0:
                if alternativeFormat:
                    if e0 == 1:
                        return str(e1)
                    else:
                        return str(e0)
                else:
                    return "%s/%s" % (e0, e1)
            elif e0 > e1:
                e = float(e0) / e1
                if alternativeFormat:
                    return "%.0fs" % e
                else:
                    return "%.0f" % e
            else:
                return "1s"
        else:
            return missing

    def focal_length(self, missing='') -> Union[str, Any]:
        v = self._get('FocalLength', None)
        if v is not None:
            return str(v)
        return missing

    def camera_make(self, missing='') -> Union[str, Any]:
        v = self._get('Make', None)
        if v is not None:
            return str(v)
        return missing

    def camera_model(self, missing='') -> Union[str, Any]:
        v = self._get('Model', None)
        if v is not None:
            return str(v)
        return missing

    def short_camera_model(self, includeCharacters='', missing=''):
        """
        Returns in shorterned string format the camera model used to record
        the image.

        Returns missing if the metadata value is not present.

        The short format is determined by the first occurrence of a digit in
        the
        camera model, including all alphaNumeric characters before and after
        that digit up till a non-alphanumeric character, but with these
        interventions:

        1. Canon "Mark" designations are shortened prior to conversion.
        2. Names like "Canon EOS DIGITAL REBEL XSi" do not have a number and
        must
            and treated differently (see below)

        Examples:
        Canon EOS 300D DIGITAL -> 300D
        Canon EOS 5D -> 5D
        Canon EOS 5D Mark II -> 5DMkII
        NIKON D2X -> D2X
        NIKON D70 -> D70
        X100,D540Z,C310Z -> X100
        Canon EOS DIGITAL REBEL XSi -> XSi
        Canon EOS Digital Rebel XS -> XS
        Canon EOS Digital Rebel XTi -> XTi
        Canon EOS Kiss Digital X -> Digital
        Canon EOS Digital Rebel XT -> XT
        EOS Kiss Digital -> Digital
        Canon Digital IXUS Wireless -> Wireless
        Canon Digital IXUS i zoom -> zoom
        Canon EOS Kiss Digital N -> N
        Canon Digital IXUS IIs -> IIs
        IXY Digital L -> L
        Digital IXUS i -> i
        IXY Digital -> Digital
        Digital IXUS -> IXUS

        The optional includeCharacters allows additional characters to appear
        before and after the digits.
        Note: special includeCharacters MUST be escaped as per syntax of a
        regular expressions (see documentation for module re)

        Examples:

        includeCharacters = '':
        DSC-P92 -> P92
        includeCharacters = '\-':
        DSC-P92 -> DSC-P92

        If a digit is not found in the camera model, the last word is returned.

        Note: assume exif values are in ENGLISH, regardless of current platform
        """
        m = self.camera_model()
        m = m.replace(' Mark ', 'Mk')
        if m:
            s = r"(?:[^a-zA-Z0-9%s]?)(?P<model>[a-zA-Z0-9%s]*\d+[" \
                r"a-zA-Z0-9%s]*)" \
                % (includeCharacters, includeCharacters, includeCharacters)
            r = re.search(s, m)
            if r:
                return r.group("model")
            else:
                head, space, model = m.strip().rpartition(' ')
                return model
        else:
            return missing

    def camera_serial(self, missing='') -> Union[str, Any]:
        v = self._get('SerialNumber', None)
        if v is not None:
            return str(v)
        return missing

    def shutter_count(self, missing='') -> Union[str, Any]:
        v = self._get('ShutterCount', None)
        if v is None:
            v = self._get('ImageNumber', None)

        if v is not None:
            return str(v)
        return missing

    def owner_name(self, missing='') -> Union[str, Any]:

        # distinct from CopyrightOwnerName
        v = self._get('OwnerName', None)
        if v is not None:
            return str(v)
        return missing

    def copyright(self, missing='') -> Union[str, Any]:
        v = self._get('Copyright', None)
        if v is not None:
            return str(v)
        return missing

    def artist(self, missing=''):
        v = self._get('Artist', None)
        if v is not None:
            return str(v)
        return missing

    def sub_seconds(self, missing='00') -> Union[str, Any]:
        v = self._get('SubSecTime', None)
        if v is not None:
            return str(v)
        return missing

    def orientation(self, missing='') -> Union[str, Any]:
        v = self._get('Orientation', None)
        if v is not None:
            return str(v)
        return missing

    def _get_binary(self, key: str) -> Optional[bytes]:
        return self.et_process.execute_binary("-{}".format(key), self.full_file_name)

    def get_small_thumbnail(self) -> Optional[bytes]:
        """
        Get the small thumbnail image (if it exists)
        :return: thumbnail image in raw bytes
        """

        return self._get_binary("ThumbnailImage")

    def get_indexed_preview(self, preview_number: int=0, force: bool=False) -> Optional[bytes]:
        """
        Extract preview image from the metadata
        If initial preview number does not work, tries others

        :param preview_number: which preview to get
        :param force: if True, get only that preview. Otherwise, take a flexible approach
         where every preview is tried image, in order found in index_preview
        :return: preview image in raw bytes, if found, else None
        """

        key = self.index_preview[preview_number]
        b = self._get_binary(key)
        if b:
            return b
        if force:
            return None

        logging.debug(
            "Attempt to extract %s using ExifTool from %s failed. Trying flexible approach.",
            key, self.full_file_name
        )

        assert not force
        untried_indexes = (
            index for index in self.index_preview.keys() if index != preview_number
        )

        valid_untried_indexes = [
            index for index in untried_indexes if self.index_preview[index] in self.metadata
        ]
        if valid_untried_indexes:
            for index in valid_untried_indexes:
                key = self.index_preview[index]
                logging.debug("Attempting %s on %s...", key, self.full_file_name)
                b = self._get_binary(key)
                if b:
                    logging.debug("...attempt successful from %s", self.full_file_name)
                    return b
                logging.debug("...attempt failed on %s", self.full_file_name)
        else:
            logging.debug(
                "No other preview image indexes remain to be tried on %s", self.full_file_name
            )

        logging.warning("ExifTool could not extract a preview image from %s", self.full_file_name)
        return None

    def get_small_thumbnail_or_first_indexed_preview(self) -> Optional[bytes]:
        """
        First attempt to get the small thumbnail image. If it does not exist,
        extract the smallest preview image from the metadata

        :return: thumbnail / preview image in raw bytes, if found, else None
        """

        # Look for "ThumbnailImage" if the file format supports it
        if self.ext not in self.preview_smallest or self.ext in self.may_have_thumbnail:
            thumbnail = self.get_small_thumbnail()
            if thumbnail is not None:
                return thumbnail

        # Otherwise look for the smallest preview image for this format
        if self.ext in self.preview_smallest:
            for index in self.preview_smallest[self.ext]:
                thumbnail = self.get_indexed_preview(preview_number=index, force=True)
                if thumbnail:
                    return thumbnail

        # If that fails, take a flexible approach
        return self.get_indexed_preview(force=False)

    def get_preview_256(self) -> Optional[bytes]:
        """
        :return: if possible, return a preview image that is preferrably larger than 256 pixels,
         else the smallest preview if it exists
        """

        # look for the smallest preview
        if self.ext in self.preview256:
            for index in self.preview256[self.ext]:
                thumbnail = self.get_indexed_preview(preview_number=index, force=True)
                if thumbnail is not None:
                    return thumbnail

        # If that fails, take a flexible approach
        return self.get_indexed_preview(force=False)

    def preview_names(self) -> Optional[List[str]]:
        """
        Names of preview image located in the file, including the tag ThumbnailImage

        :return None if unsuccessful, else names of preview images
        """

        if not self.metadata:
            try:
                self.metadata = self.et_process.get_metadata(self.full_file_name)
            except ValueError:
                return None

        return [v for v in self.index_preview.values() if v in self.metadata]

if __name__ == '__main__':
    import sys

    with exiftool.ExifTool() as et_process:
        if (len(sys.argv) != 2):
            print('Usage: ' + sys.argv[0] + ' path/to/video/containing/metadata')
        else:
            file = sys.argv[1]

            print("ExifTool", programversions.exiftool_version_info())
            file_type = fileformats.file_type_from_splitext(file_name=file)
            if file_type is None:
                print("Unsupported file type")
                sys.exit(1)
            m = MetadataExiftool(file, et_process, file_type)
            print(m.date_time())
            print("f" + m.aperture('missing '))
            print("ISO " + m.iso('missing '))
            print(m.exposure_time(missing='missing ') + " sec")
            print(m.exposure_time(alternativeFormat=True, missing='missing '))
            print(m.focal_length('missing ') + "mm")
            print(m.camera_make())
            print(m.camera_model())
            print('Serial number:', m.camera_serial(missing='missing'))
            print('Shutter count:', m.shutter_count())
            print('Owner name:', m.owner_name())
            print('Copyright:', m.copyright())
            print('Artist', m.artist())
            print('Subseconds:', m.sub_seconds())
            print('Orientation:', m.orientation())


            # print("%sx%s" % (m.width(), m.height()))
            # print("Length:", m.length())
            # print("FPS: ", m.frames_per_second())
            # print("Codec:", m.codec())