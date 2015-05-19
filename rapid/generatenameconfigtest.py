#!/usr/bin/python3
__author__ = 'Damon Lynch'

# Copyright (C) 2007-2015 Damon Lynch <damonlynch@gmail.com>

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

import unittest

from generatenameconfig import *
from generatename import convert_date_for_strftime


class PreferenceTest(unittest.TestCase):
    photo_test = ( [TEXT, '', ''],
                   [DATE_TIME, IMAGE_DATE, 'YYYYMMDD'],
                   [METADATA, APERTURE, ''],
                   [FILENAME, NAME_EXTENSION, UPPERCASE],
                   )
    subfolder_test = ( [TEXT, '', ''],
                       [DATE_TIME, IMAGE_DATE, 'HHMM'],
                       [METADATA, SHORT_CAMERA_MODEL_HYPHEN,
                        LOWERCASE],
                       [SEPARATOR, '', ''],
                       [FILENAME, EXTENSION, LOWERCASE]
                       )

    video_name_test = (
        [DATE_TIME, VIDEO_DATE, 'HHMMSS'],
        [METADATA, CODEC, LOWERCASE],
        [METADATA, FPS, ''],
    )

    video_name_test2 = (
        [DATE_TIME, VIDEO_DATE, 'HHMMSS',
         METADATA, CODEC, LOWERCASE,
         METADATA, FPS, ''],
    )

    video_name_test3 = (
        [FILENAME, VIDEO_NUMBER, IMAGE_NUMBER_4,
         FILENAME, NAME_EXTENSION, LOWERCASE,
         METADATA, FPS, ''],
    )

    video_subfolder_test = (
        [DATE_TIME, TODAY, 'HHMMSS',
         SEPARATOR, '', '',
         METADATA, WIDTH, ''],
    )

    trueMetadataTest = (
    [FILENAME, EXTENSION, LOWERCASE, TEXT, '', '', METADATA, APERTURE, ''],
    [METADATA, APERTURE, '', TEXT, '', '', FILENAME, EXTENSION, LOWERCASE],  )

    falseMetadataTest = (
    [FILENAME, EXTENSION, LOWERCASE, METADATA, APERTURE, '', FILENAME, NAME,
     LOWERCASE],
    [FILENAME, NAME, LOWERCASE, FILENAME, EXTENSION, LOWERCASE],
    [FILENAME, NAME_EXTENSION, LOWERCASE, FILENAME, EXTENSION, LOWERCASE],
    [FILENAME, NAME, LOWERCASE, FILENAME, METADATA, EXPOSURE_TIME, '',
     IMAGE_NUMBER, IMAGE_NUMBER_ALL, FILENAME, EXTENSION, LOWERCASE], )

    sequences_test = ([SEQUENCES, SESSION_SEQ_NUMBER, SEQUENCE_NUMBER_3],
                      [FILENAME, NAME, LOWERCASE, SEQUENCES,
                       DOWNLOAD_SEQ_NUMBER, SEQUENCE_NUMBER_1,
                       FILENAME, EXTENSION, UPPERCASE],
                      [METADATA, APERTURE, '', SEQUENCES, STORED_SEQ_NUMBER,
                       SEQUENCE_NUMBER_5,
                       FILENAME, EXTENSION, UPPERCASE], )

    def testPrefImageList(self):
        for pref in self.photo_test:
            result = check_pref_valid(DICT_IMAGE_RENAME_L0, pref)
            self.assertEqual(result, True)

    def testPrefVideoList(self):
        for pref in self.video_name_test:
            result = check_pref_valid(DICT_VIDEO_RENAME_L0, pref)
            self.assertEqual(result, True)
        for pref in self.video_name_test2:
            result = check_pref_valid(DICT_VIDEO_RENAME_L0, pref)
            self.assertEqual(result, True)
        for pref in self.video_name_test3:
            result = check_pref_valid(DICT_VIDEO_RENAME_L0, pref)
            self.assertEqual(result, True)

    def testSequencesList(self):
        for pref in self.sequences_test:
            result = check_pref_valid(DICT_IMAGE_RENAME_L0, pref)
            self.assertEqual(result, True)

    def testLargePrefList(self):
        prefList = []
        for pref in self.photo_test:
            for l in pref:
                prefList.append(l)

        result = check_pref_valid(DICT_IMAGE_RENAME_L0, prefList)
        self.assertEqual(result, True)

    def testPrefSubfolderList(self):
        for pref in self.subfolder_test:
            result = check_pref_valid(DICT_SUBFOLDER_L0, pref)
            self.assertEqual(result, True)

    def testPrefVideoSubfolderList(self):
        for pref in self.video_subfolder_test:
            result = check_pref_valid(DICT_VIDEO_SUBFOLDER_L0, pref)
            self.assertEqual(result, True)

    def testDateTimeL2Length(self):
        self.assertEqual(len(LIST_DATE_TIME_L2), len(DATE_TIME_CONVERT))

    def testDateTimeL2Conversion(self):
        self.assertEqual(convert_date_for_strftime('YY'), '%y')


class BadPreferences(unittest.TestCase):
    bad_image_key = ( [TEXT, '', '',
                       DATE_TIME, IMAGE_DATE, 'YYYYMMDD',
                       METADATA, APERTURE, '',
                       FILENAME, NAME_EXTENSION, UPPERCASE,
                       'Filename2', NAME_EXTENSION, UPPERCASE],
                      )
    bad_image_value = ( [DATE_TIME, TODAY, IMAGE_NUMBER_ALL],
                        [METADATA, CAMERA_MAKE, IMAGE_NUMBER_4],
                        [DATE_TIME, IMAGE_DATE, None],
                        [DATE_TIME, IMAGE_DATE, ''],
                        [DATE_TIME, None, None],
                        [DATE_TIME, '', ''],
                        )

    bad_image_key2 = (
        [FILENAME, VIDEO_NUMBER, IMAGE_NUMBER_4,
         FILENAME, NAME_EXTENSION, LOWERCASE,
         METADATA, APERTURE, ''],
    )

    bad_subfolder_key = ([FILENAME, NAME_EXTENSION, UPPERCASE],)

    bad_subfolder_key2 = ( [TEXT, '', '',
                            DATE_TIME, IMAGE_DATE, 'HHMM',
                            METADATA, SHORT_CAMERA_MODEL_HYPHEN,
                            LOWERCASE,
                            SEPARATOR, '', '',
                            'Filename-bad', EXTENSION, LOWERCASE],
                           )

    bad_subfolder_value = ( [FILENAME, None, None],
                            [FILENAME, '', ''],)

    bad_length = ([], [DATE_TIME, TODAY], [DATE_TIME])

    bad_dt_conversion = ('HHYY', 'YYSS')

    bad_subfolder_combos = ([SEPARATOR, '', ''],
                            [FILENAME, EXTENSION, UPPERCASE,
                             SEPARATOR, '', ''],
                            [FILENAME, EXTENSION, UPPERCASE,
                             SEPARATOR, '', '',
                             SEPARATOR, '', '',
                             FILENAME, EXTENSION, UPPERCASE
                             ],
                            [SEPARATOR, '', '',
                             SEPARATOR, '', '',
                             SEPARATOR, '', '',
                             SEPARATOR, '', ''
                             ]
                            )

    def testBadImageKey(self):
        for pref in self.bad_image_key:
            self.assertRaises(PrefKeyError, check_pref_valid,
                              DICT_IMAGE_RENAME_L0,
                              pref)
        for pref in self.bad_image_key2:
            self.assertRaises(PrefKeyError, check_pref_valid,
                              DICT_IMAGE_RENAME_L0,
                              pref)


    def testBadImageValue(self):
        for pref in self.bad_image_value:
            self.assertRaises(PrefValueInvalidError, check_pref_valid,
                              DICT_IMAGE_RENAME_L0,
                              pref)


    def testBadSubfolderKey(self):
        for pref in self.bad_subfolder_key:
            self.assertRaises(PrefKeyError, check_pref_valid,
                              DICT_SUBFOLDER_L0,
                              pref)

        for pref in self.bad_subfolder_key2:
            self.assertRaises(PrefKeyError, check_pref_valid,
                              DICT_SUBFOLDER_L0,
                              pref)


    def testBadSubfolderValue(self):
        for pref in self.bad_subfolder_value:
            self.assertRaises(PrefValueInvalidError, check_pref_valid,
                              DICT_SUBFOLDER_L0,
                              pref)

    def testBadLength(self):
        for pref in self.bad_length:
            self.assertRaises(PrefLengthError, check_pref_valid,
                              DICT_IMAGE_RENAME_L0,
                              pref)

    def testBadDTConversion(self):
        for pref in self.bad_dt_conversion:
            self.assertRaises(PrefValueInvalidError, convert_date_for_strftime,
                              pref)

    # def testBadSubfolderCombo(self):
    #
    #     for pref in self.bad_subfolder_combos:
    #         s = PhotoSubfolder(pref, self)
    #         self.assertRaises(PrefValueKeyComboError, s.checkPrefsForValidity)
    #
    # def testBadVideoSubfolderCombo(self):
    #
    #     for pref in self.bad_subfolder_combos:
    #         s = VideoSubfolder(pref, self)
    #         self.assertRaises(PrefValueKeyComboError, s.checkPrefsForValidity)


if __name__ == "__main__":
    unittest.main() 
