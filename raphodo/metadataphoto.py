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

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2007-2018, Damon Lynch"

import re
import datetime
import subprocess
from typing import Optional, Union, Any, Tuple
import logging

import gi
gi.require_version('GExiv2', '0.10')
from gi.repository import GExiv2

import raphodo.exiftool as exiftool


def gexiv2_version() -> str:
    """
    :return: version number of GExiv2
    """
    # GExiv2.get_version() returns an integer XXYYZZ, where XX is the
    # major version, YY is the minor version, and ZZ is the micro version
    v = '{0:06d}'.format(GExiv2.get_version())
    return '{}.{}.{}'.format(v[0:2], v[2:4], v[4:6]).replace('00', '0')


def exiv2_version() -> Optional[str]:
    """
    :return: version number of exiv2, if available, else None
    """

    # exiv2 outputs a verbose version string, e.g. the first line is
    # 'exiv2 0.24 001800 (64 bit build)'
    # followed by the copyright & GPL
    try:
        v = subprocess.check_output(['exiv2', '-V', '-v']).strip().decode()
        v = re.search('exiv2=([0-9\.]+)\n', v)
        if v:
            return v.group(1)
        else:
            return None
    except (OSError, subprocess.CalledProcessError):
        return None


VENDOR_SERIAL_CODES = (
    'Exif.Photo.BodySerialNumber',
    'Exif.Canon.SerialNumber',
    'Exif.Nikon3.SerialNumber',
    'Exif.OlympusEq.SerialNumber',
    'Exif.Olympus.SerialNumber',
    'Exif.Olympus.SerialNumber2',
    'Exif.Panasonic.SerialNumber',
    'Exif.Fujifilm.SerialNumber',
    'Exif.Image.CameraSerialNumber',
)

VENDOR_SHUTTER_COUNT = (
    'Exif.Nikon3.ShutterCount',
    'Exif.Canon.FileNumber',
    'Exif.Canon.ImageNumber',
)


class MetaData(GExiv2.Metadata):
    """
    Provide abstracted access to photo metadata
    """

    def __init__(self, full_file_name: Optional[str]=None,
                 raw_bytes: Optional[bytearray]=None,
                 app1_segment: Optional[bytearray]=None,
                 et_process: exiftool.ExifTool=None)  -> None:
        """
        Use GExiv2 to read the photograph's metadata.

        :param full_file_name: full path of file from which file to read
         the metadata.
        :param raw_bytes: portion of a non-jpeg file from which the
         metadata can be extracted
        :param app1_segment: the app1 segment of a jpeg file, from which
         the metadata can be read
        :param et_process: optional deamon exiftool process
        """

        if full_file_name:
            super().__init__()
            self.open_path(full_file_name)
        else:
            super().__init__()
            if raw_bytes is not None:
                self.open_buf(raw_bytes)
            else:
                assert app1_segment is not None
                self.from_app1_segment(app1_segment)

        self.et_process = et_process
        self.rpd_full_file_name = full_file_name

    def _get_rational_components(self, tag: str) -> Optional[Tuple[Any, Any]]:
        try:
            x = self.get_exif_tag_rational(tag)
        except Exception:
            return (None, None)

        try:
            return x.numerator, x.denominator
        except AttributeError:
            try:
                return x.nom, x.den
            except Exception:
                return (None, None)

    def _get_rational(self, tag: str) -> Optional[float]:
        x, y = self._get_rational_components(tag)
        if x is not None and y is not None:
            return float(x) / float(y)

    def aperture(self, missing='') -> Union[str, Any]:
        """
        Returns in string format the floating point value of the image's
        aperture.

        Returns missing if the metadata value is not present.
        """
        a = self._get_rational("Exif.Photo.FNumber")

        if a is None:
            return missing
        else:
            return "%.1f" % a

    def iso(self, missing='') -> Union[str, Any]:
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
        except Exception:
            return missing

    def exposure_time(self, alternativeFormat=False, missing=''):
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

        e0, e1 = self._get_rational_components("Exif.Photo.ExposureTime")
        if e0 is not None and e1 is not None:

            e0 = int(e0)
            e1 = int(e1)

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

    def focal_length(self, missing=''):
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

    def camera_make(self, missing=''):
        """
        Returns in string format the camera make (manufacturer) used to
        record the image.

        Returns missing if the metadata value is not present.
        """
        try:
            return self.get_tag_string("Exif.Image.Make").strip()
        except Exception:
            return missing

    def camera_model(self, missing=''):
        """
        Returns in string format the camera model used to record the image.

        Returns missing if the metadata value is not present.
        """
        try:
            return self.get_tag_string("Exif.Image.Model").strip()
        except Exception:
            return missing

    def _fetch_vendor(self, vendor_codes, missing=''):
        for key in vendor_codes:
            try:
                return self.get_tag_string(key).strip()
            except (KeyError, AttributeError):
                pass
        return missing

    def camera_serial(self, missing=''):
        return self._fetch_vendor(VENDOR_SERIAL_CODES, missing)

    def shutter_count(self, missing=''):
        shutter = self._fetch_vendor(VENDOR_SHUTTER_COUNT, missing)
        if shutter != missing:
            return shutter

        if self.camera_make().lower() == 'sony':
            try:
                ic = self.et_process.get_tags(['ImageCount'], self.rpd_full_file_name)
            except (ValueError, TypeError):
                return missing
            if ic:
                return ic['ImageCount']

        return missing

    def file_number(self, missing=''):
        """
        Returns Exif.CanonFi.FileNumber, not to be confused with
        Exif.Canon.FileNumber.

        Uses ExifTool to extract the value, because the exiv2
        implementation is currently problematic

        See:
        https://bugs.launchpad.net/rapid/+bug/754531
        """
        if 'Exif.CanonFi.FileNumber' in self:
            assert self.et_process is not None
            try:
                fn = self.et_process.get_tags(['FileNumber'], self.rpd_full_file_name)
            except (ValueError, TypeError):
                return missing

            if fn:
                return fn['FileNumber']
            else:
                return missing
        else:
            return missing

    def owner_name(self, missing=''):
        try:
            return self.get_tag_string('Exif.Canon.OwnerName').strip()
        except KeyError:
            return missing

    def copyright(self, missing=''):
        try:
            return self.get_tag_string('Exif.Image.Copyright').strip()
        except KeyError:
            return missing

    def artist(self, missing=''):
        try:
            return self.get_tag_string('Exif.Image.Artist').strip()
        except KeyError:
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

    def date_time(self, missing: Optional[str]='') -> datetime.datetime:
        """
        Returns in python datetime format the date and time the image was
        recorded.

        Tries these tags, in order:
        Exif.Photo.DateTimeOriginal
        Exif.Image.DateTimeOriginal
        Exif.Image.DateTime

        :return: metadata value, or missing if value is not present.
        """

        dt = None
        try:
            dt = self.get_date_time()
        except:
            pass

        if dt:
            return dt

        # get_date_time() seems to try only one key, Exif.Photo.DateTimeOriginal
        # Try other keys too, and with a more flexible datetime parser.
        # For example some or maybe all Android 6.0 DNG files use Exif.Image.DateTimeOriginal

        for tag in ('Exif.Photo.DateTimeOriginal', 'Exif.Image.DateTimeOriginal',
                    'Exif.Image.DateTime'):
            try:
                dt_string = self.get_tag_string(tag)
            except:
                pass
            else:
                if dt_string is None:
                    continue

                # ignore all zero values, e.g. '0000:00:00 00:00:00'
                try:
                    digits = int(''.join(c for c in dt_string if c.isdigit()))
                except ValueError:
                    logging.warning('Unexpected malformed date time metadata value %s for photo %s',
                                        dt_string, self.rpd_full_file_name )
                else:
                    if not digits:
                        logging.debug('Ignoring date time metadata value %s for photo %s',
                                            dt_string, self.rpd_full_file_name )
                    else:
                        try:
                            return  datetime.datetime.strptime(dt_string, "%Y:%m:%d %H:%M:%S")
                        except (ValueError, OverflowError):
                            logging.warning('Error parsing date time metadata %s for photo %s',
                                            dt_string, self.rpd_full_file_name )
        return missing

    def timestamp(self, missing='') -> Union[float, Any]:
        dt = self.date_time(missing=None)
        if dt is not None:
            try:
                ts = float(dt.timestamp())
            except:
                ts = missing
        else:
            ts = missing
        return ts

    def sub_seconds(self, missing='00') -> Union[str, Any]:
        """
        Returns the subsecond the image was taken, as recorded by the
        camera
        """

        try:
            return self.get_tag_string("Exif.Photo.SubSecTimeOriginal")
        except:
            return missing

    def orientation(self, missing='') -> Union[int, Any]:
        """
        Returns the orientation of the image, as recorded by the camera
        Return type int
        """

        try:
            return int(self.get_orientation())
        except:
            return missing


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

    def aperture(self, missing=''):
        return "2.0"

    def iso(self, missing=''):
        return "100"

    def exposure_time(self, alternativeFormat=False, missing=''):
        if alternativeFormat:
            return "4000"
        else:
            return "1/4000"

    def focal_length(self, missing=''):
        return "135"

    def camera_make(self, missing=''):
        return "Canon"

    def camera_model(self, missing=''):
        return "Canon EOS 5D"

    def short_camera_model(self, includeCharacters='', missing=''):
        return "5D"

    def camera_serial(self, missing=''):
        return '730402168'

    def shutter_count(self, missing=''):
        return '387'

    def owner_name(self, missing=''):
        return 'Photographer Name'

    def date_time(self, missing=''):
        return datetime.datetime.now()

    def subSeconds(self, missing='00'):
        return '57'

    def orientation(self, missing=''):
        return 1

    def file_number(self, missing=''):
        return '428'


if __name__ == '__main__':
    import sys

    if (len(sys.argv) != 2):
        print('Usage: ' + sys.argv[0] + ' path/to/photo/containing/metadata')
        m = DummyMetaData()

    else:
        m = MetaData(full_file_name=sys.argv[1])

    print("f" + m.aperture('missing '))
    print("ISO " + m.iso('missing '))
    print(m.exposure_time(missing='missing ') + " sec")
    print(m.exposure_time(alternativeFormat=True, missing='missing '))
    print(m.focal_length('missing ') + "mm")
    print(m.camera_make())
    print(m.camera_model())
    print(m.short_camera_model())
    print(m.short_camera_model(includeCharacters="\-"))
    print(m.date_time())
    print(m.orientation())
    print('Serial number:', m.camera_serial(missing='missing'))
    print('Shutter count:', m.shutter_count())
    print('Subseconds:', m.sub_seconds(), type(m.sub_seconds()))
