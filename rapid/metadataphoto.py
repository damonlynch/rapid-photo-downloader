#!/usr/bin/python3

# Copyright (C) 2007-2015 Damon Lynch <damonlynch@gmail.com>

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

import re
import datetime
import sys
import config
import types
import time


try:
    from gi.repository import GExiv2
except ImportError:
    sys.stderr.write("You need to install GExiv2, the python binding for "
                     "exiv2, to run this program.\n")
    sys.exit(1)

import metadatavideo


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
    Class providing human readable access to image metadata
    """

    def __init__(self, full_file_name):
        GExiv2.Metadata.__init__(self, full_file_name)
        self.rpd_metadata_exiftool = None
        self.rpd_full_file_name = full_file_name

    def _load_exiftool(self):
        if self.rpd_metadata_exiftool is None:
            self.rpd_metadata_exiftool = metadatavideo.ExifToolMetaData(
                self.rpd_full_file_name)

    def aperture(self, missing=''):
        """
        Returns in string format the floating point value of the image's
        aperture.

        Returns missing if the metadata value is not present.
        """
        try:
            a = self.get_exif_tag_rational("Exif.Photo.FNumber")

            a = float(a.numerator) / float(a.denominator)
            return "%.1f" % a
        except:
            return missing

    def iso(self, missing=''):
        """
        Returns in string format the integer value of the image's ISO.

        Returns missing if the metadata value is not present.
        """
        try:
            return self.get_tag_interpreted_string(
                "Exif.Photo.ISOSpeedRatings")
        except:
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
        try:
            e = self.get_exif_tag_rational("Exif.Photo.ExposureTime")

            e0 = int(e.numerator)
            e1 = int(e.denominator)

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
        except:
            return missing

    def focal_length(self, missing=''):
        """
        Returns in string format the focal length of the lens used to record
        the image.

        Returns missing if the metadata value is not present.
        """
        try:
            f = self.get_exif_tag_rational("Exif.Photo.FocalLength")
            f0 = float(f.numerator)
            f1 = float(f.denominator)

            return "%.0f" % (f0 / f1)
        except:
            return missing

    def camera_make(self, missing=''):
        """
        Returns in string format the camera make (manufacturer) used to
        record the image.

        Returns missing if the metadata value is not present.
        """
        try:
            return self["Exif.Image.Make"].strip()
        except:
            return missing

    def camera_model(self, missing=''):
        """
        Returns in string format the camera model used to record the image.

        Returns missing if the metadata value is not present.
        """
        try:
            return self["Exif.Image.Model"].strip()
        except:
            return missing

    def _fetch_vendor(self, vendor_codes, missing=''):
        for key in vendor_codes:
            try:
                return self[key].strip()
            except KeyError:
                pass
        return missing

    def camera_serial(self, missing=''):
        return self._fetch_vendor(VENDOR_SERIAL_CODES, missing)

    def shutter_count(self, missing=''):
        return self._fetch_vendor(VENDOR_SHUTTER_COUNT, missing)

    def file_number(self, missing=''):
        """Returns Exif.CanonFi.FileNumber, not to be confused with
        Exif.Canon.FileNumber"""
        try:
            if 'Exif.CanonFi.FileNumber' in self:
                self._load_exiftool()
                return self.rpd_metadata_exiftool.file_number(missing)
            else:
                return missing
        except:
            return missing

    def owner_name(self, missing=''):
        try:
            return self['Exif.Canon.OwnerName'].strip()
        except KeyError:
            return missing

    def copyright(self, missing=''):
        try:
            return self['Exif.Image.Copyright'].strip()
        except KeyError:
            return missing

    def artist(self, missing=''):
        try:
            return self['Exif.Image.Artist'].strip()
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

    def date_time(self, missing=''):
        """
        Returns in python datetime format the date and time the image was
        recorded.

        Trys to get value from exif key "Exif.Photo.DateTimeOriginal".
        If that does not exist, trys key "Exif.Image.DateTime"

        Returns missing either metadata value is not present.
        """
        return self.get_date_time() or missing

    def time_stamp(self, missing=''):
        dt = self.date_time(missing=None)
        if dt is not None:
            try:
                t = dt.timetuple()
                ts = time.mktime(t)
            except:
                ts = missing
        else:
            ts = missing
        return ts

    def sub_seconds(self, missing='00'):
        """Returns the subsecond the image was taken, as recorded by the
        camera"""
        try:
            return self["Exif.Photo.SubSecTimeOriginal"]
        except:
            return missing

    def orientation(self, missing=''):
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
    Class which gives metadata values for an imaginary image.

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


if __name__ == '__main__':
    import sys

    if (len(sys.argv) != 2):
        print('Usage: ' + sys.argv[0] + ' path/to/photo/containing/metadata')
        m = DummyMetaData()

    else:
        m = MetaData(sys.argv[1])

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
    print('Subseconds:', m.sub_seconds())
