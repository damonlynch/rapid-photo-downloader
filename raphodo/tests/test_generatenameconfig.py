#!/usr/bin/python3

# SPDX-FileCopyrightText: Copyright 2007-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later


import unittest
import generatenameconfig
import generatename


class PreferenceTest(unittest.TestCase):
    photo_test = ([generatenameconfig.TEXT, '', ''],
                  [generatenameconfig.DATE_TIME, generatenameconfig.IMAGE_DATE,
                   'YYYYMMDD'],
                  [generatenameconfig.METADATA, generatenameconfig.APERTURE,
                   ''],
                  [generatenameconfig.FILENAME,
                   generatenameconfig.NAME_EXTENSION,
                   generatenameconfig.UPPERCASE],
                  )
    subfolder_test = ([generatenameconfig.TEXT, '', ''],
                      [generatenameconfig.DATE_TIME,
                       generatenameconfig.IMAGE_DATE, 'HHMM'],
                      [generatenameconfig.METADATA,
                       generatenameconfig.SHORT_CAMERA_MODEL_HYPHEN,
                       generatenameconfig.LOWERCASE],
                      [generatenameconfig.SEPARATOR, '', ''],
                      [generatenameconfig.FILENAME,
                       generatenameconfig.EXTENSION,
                       generatenameconfig.LOWERCASE]
                      )

    video_name_test = (
        [generatenameconfig.DATE_TIME, generatenameconfig.VIDEO_DATE,
         'HHMMSS'],
        [generatenameconfig.METADATA, generatenameconfig.CODEC,
         generatenameconfig.LOWERCASE],
        [generatenameconfig.METADATA, generatenameconfig.FPS, ''],
    )

    video_name_test2 = (
        [generatenameconfig.DATE_TIME, generatenameconfig.VIDEO_DATE, 'HHMMSS',
         generatenameconfig.METADATA, generatenameconfig.CODEC,
         generatenameconfig.LOWERCASE,
         generatenameconfig.METADATA, generatenameconfig.FPS, ''],
    )

    video_name_test3 = (
        [generatenameconfig.FILENAME, generatenameconfig.VIDEO_NUMBER,
         generatenameconfig.IMAGE_NUMBER_4,
         generatenameconfig.FILENAME, generatenameconfig.NAME_EXTENSION,
         generatenameconfig.LOWERCASE,
         generatenameconfig.METADATA, generatenameconfig.FPS, ''],
    )

    video_subfolder_test = (
        [generatenameconfig.DATE_TIME, generatenameconfig.TODAY, 'HHMMSS',
         generatenameconfig.SEPARATOR, '', '',
         generatenameconfig.METADATA, generatenameconfig.WIDTH, ''],
    )

    trueMetadataTest = (
        [generatenameconfig.FILENAME, generatenameconfig.EXTENSION,
         generatenameconfig.LOWERCASE, generatenameconfig.TEXT, '', '',
         generatenameconfig.METADATA, generatenameconfig.APERTURE, ''],
        [generatenameconfig.METADATA, generatenameconfig.APERTURE, '',
         generatenameconfig.TEXT, '', '', generatenameconfig.FILENAME,
         generatenameconfig.EXTENSION, generatenameconfig.LOWERCASE],)

    falseMetadataTest = (
        [generatenameconfig.FILENAME, generatenameconfig.EXTENSION,
         generatenameconfig.LOWERCASE, generatenameconfig.METADATA,
         generatenameconfig.APERTURE, '', generatenameconfig.FILENAME,
         generatenameconfig.NAME,
         generatenameconfig.LOWERCASE],
        [generatenameconfig.FILENAME, generatenameconfig.NAME,
         generatenameconfig.LOWERCASE, generatenameconfig.FILENAME,
         generatenameconfig.EXTENSION, generatenameconfig.LOWERCASE],
        [generatenameconfig.FILENAME, generatenameconfig.NAME_EXTENSION,
         generatenameconfig.LOWERCASE, generatenameconfig.FILENAME,
         generatenameconfig.EXTENSION, generatenameconfig.LOWERCASE],
        [generatenameconfig.FILENAME, generatenameconfig.NAME,
         generatenameconfig.LOWERCASE, generatenameconfig.FILENAME,
         generatenameconfig.METADATA, generatenameconfig.EXPOSURE_TIME, '',
         generatenameconfig.IMAGE_NUMBER, generatenameconfig.IMAGE_NUMBER_ALL,
         generatenameconfig.FILENAME, generatenameconfig.EXTENSION,
         generatenameconfig.LOWERCASE],)

    sequences_test = (
    [generatenameconfig.SEQUENCES, generatenameconfig.SESSION_SEQ_NUMBER,
     generatenameconfig.SEQUENCE_NUMBER_3],
    [generatenameconfig.FILENAME, generatenameconfig.NAME,
     generatenameconfig.LOWERCASE, generatenameconfig.SEQUENCES,
     generatenameconfig.DOWNLOAD_SEQ_NUMBER,
     generatenameconfig.SEQUENCE_NUMBER_1,
     generatenameconfig.FILENAME, generatenameconfig.EXTENSION,
     generatenameconfig.UPPERCASE],
    [generatenameconfig.METADATA, generatenameconfig.APERTURE, '',
     generatenameconfig.SEQUENCES, generatenameconfig.STORED_SEQ_NUMBER,
     generatenameconfig.SEQUENCE_NUMBER_5,
     generatenameconfig.FILENAME, generatenameconfig.EXTENSION,
     generatenameconfig.UPPERCASE],)

    def testPrefImageList(self):
        for pref in self.photo_test:
            result = generatenameconfig.check_pref_valid(
                generatenameconfig.DICT_IMAGE_RENAME_L0, pref)
            self.assertEqual(result, True)

    def testPrefVideoList(self):
        for pref in self.video_name_test:
            result = generatenameconfig.check_pref_valid(
                generatenameconfig.DICT_VIDEO_RENAME_L0, pref)
            self.assertEqual(result, True)
        for pref in self.video_name_test2:
            result = generatenameconfig.check_pref_valid(
                generatenameconfig.DICT_VIDEO_RENAME_L0, pref)
            self.assertEqual(result, True)
        for pref in self.video_name_test3:
            result = generatenameconfig.check_pref_valid(
                generatenameconfig.DICT_VIDEO_RENAME_L0, pref)
            self.assertEqual(result, True)

    def testSequencesList(self):
        for pref in self.sequences_test:
            result = generatenameconfig.check_pref_valid(
                generatenameconfig.DICT_IMAGE_RENAME_L0, pref)
            self.assertEqual(result, True)

    def testLargePrefList(self):
        prefList = []
        for pref in self.photo_test:
            for l in pref:
                prefList.append(l)

        result = generatenameconfig.check_pref_valid(
            generatenameconfig.DICT_IMAGE_RENAME_L0, prefList)
        self.assertEqual(result, True)

    def testPrefSubfolderList(self):
        for pref in self.subfolder_test:
            result = generatenameconfig.check_pref_valid(
                generatenameconfig.DICT_SUBFOLDER_L0, pref)
            self.assertEqual(result, True)

    def testPrefVideoSubfolderList(self):
        for pref in self.video_subfolder_test:
            result = generatenameconfig.check_pref_valid(
                generatenameconfig.DICT_VIDEO_SUBFOLDER_L0, pref)
            self.assertEqual(result, True)

    def testDateTimeL2Length(self):
        self.assertEqual(len(generatenameconfig.LIST_DATE_TIME_L2),
                         len(generatenameconfig.DATE_TIME_CONVERT))

    def testDateTimeL2Conversion(self):
        self.assertEqual(generatename.convert_date_for_strftime('YY'), '%y')


class BadPreferences(unittest.TestCase):
    bad_image_key = ([generatenameconfig.TEXT, '', '',
                      generatenameconfig.DATE_TIME,
                      generatenameconfig.IMAGE_DATE, 'YYYYMMDD',
                      generatenameconfig.METADATA, generatenameconfig.APERTURE,
                      '',
                      generatenameconfig.FILENAME,
                      generatenameconfig.NAME_EXTENSION,
                      generatenameconfig.UPPERCASE,
                      'Filename2', generatenameconfig.NAME_EXTENSION,
                      generatenameconfig.UPPERCASE],
                     )
    bad_image_value = ([generatenameconfig.DATE_TIME, generatenameconfig.TODAY,
                        generatenameconfig.IMAGE_NUMBER_ALL],
                       [generatenameconfig.METADATA,
                        generatenameconfig.CAMERA_MAKE,
                        generatenameconfig.IMAGE_NUMBER_4],
                       [generatenameconfig.DATE_TIME,
                        generatenameconfig.IMAGE_DATE, None],
                       [generatenameconfig.DATE_TIME,
                        generatenameconfig.IMAGE_DATE, ''],
                       [generatenameconfig.DATE_TIME, None, None],
                       [generatenameconfig.DATE_TIME, '', ''],
                       )

    bad_image_key2 = (
        [generatenameconfig.FILENAME, generatenameconfig.VIDEO_NUMBER,
         generatenameconfig.IMAGE_NUMBER_4,
         generatenameconfig.FILENAME, generatenameconfig.NAME_EXTENSION,
         generatenameconfig.LOWERCASE,
         generatenameconfig.METADATA, generatenameconfig.APERTURE, ''],
    )

    bad_subfolder_key = (
    [generatenameconfig.FILENAME, generatenameconfig.NAME_EXTENSION,
     generatenameconfig.UPPERCASE],)

    bad_subfolder_key2 = ([generatenameconfig.TEXT, '', '',
                           generatenameconfig.DATE_TIME,
                           generatenameconfig.IMAGE_DATE, 'HHMM',
                           generatenameconfig.METADATA,
                           generatenameconfig.SHORT_CAMERA_MODEL_HYPHEN,
                           generatenameconfig.LOWERCASE,
                           generatenameconfig.SEPARATOR, '', '',
                           'Filename-bad', generatenameconfig.EXTENSION,
                           generatenameconfig.LOWERCASE],
                          )

    bad_subfolder_value = ([generatenameconfig.FILENAME, None, None],
                           [generatenameconfig.FILENAME, '', ''],)

    bad_length = ([], [generatenameconfig.DATE_TIME, generatenameconfig.TODAY],
                  [generatenameconfig.DATE_TIME])

    bad_dt_conversion = ('HHYY', 'YYSS')

    bad_subfolder_combos = ([generatenameconfig.SEPARATOR, '', ''],
                            [generatenameconfig.FILENAME,
                             generatenameconfig.EXTENSION,
                             generatenameconfig.UPPERCASE,
                             generatenameconfig.SEPARATOR, '', ''],
                            [generatenameconfig.FILENAME,
                             generatenameconfig.EXTENSION,
                             generatenameconfig.UPPERCASE,
                             generatenameconfig.SEPARATOR, '', '',
                             generatenameconfig.SEPARATOR, '', '',
                             generatenameconfig.FILENAME,
                             generatenameconfig.EXTENSION,
                             generatenameconfig.UPPERCASE
                             ],
                            [generatenameconfig.SEPARATOR, '', '',
                             generatenameconfig.SEPARATOR, '', '',
                             generatenameconfig.SEPARATOR, '', '',
                             generatenameconfig.SEPARATOR, '', ''
                             ]
                            )

    def testBadImageKey(self):
        for pref in self.bad_image_key:
            self.assertRaises(generatenameconfig.PrefKeyError,
                              generatenameconfig.check_pref_valid,
                              generatenameconfig.DICT_IMAGE_RENAME_L0,
                              pref)
        for pref in self.bad_image_key2:
            self.assertRaises(generatenameconfig.PrefKeyError,
                              generatenameconfig.check_pref_valid,
                              generatenameconfig.DICT_IMAGE_RENAME_L0,
                              pref)

    def testBadImageValue(self):
        for pref in self.bad_image_value:
            self.assertRaises(generatenameconfig.PrefValueInvalidError,
                              generatenameconfig.check_pref_valid,
                              generatenameconfig.DICT_IMAGE_RENAME_L0,
                              pref)

    def testBadSubfolderKey(self):
        for pref in self.bad_subfolder_key:
            self.assertRaises(generatenameconfig.PrefKeyError,
                              generatenameconfig.check_pref_valid,
                              generatenameconfig.DICT_SUBFOLDER_L0,
                              pref)

        for pref in self.bad_subfolder_key2:
            self.assertRaises(generatenameconfig.PrefKeyError,
                              generatenameconfig.check_pref_valid,
                              generatenameconfig.DICT_SUBFOLDER_L0,
                              pref)

    def testBadSubfolderValue(self):
        for pref in self.bad_subfolder_value:
            self.assertRaises(generatenameconfig.PrefValueInvalidError,
                              generatenameconfig.check_pref_valid,
                              generatenameconfig.DICT_SUBFOLDER_L0,
                              pref)

    def testBadLength(self):
        for pref in self.bad_length:
            self.assertRaises(generatenameconfig.PrefLengthError,
                              generatenameconfig.check_pref_valid,
                              generatenameconfig.DICT_IMAGE_RENAME_L0,
                              pref)

    def testBadDTConversion(self):
        for pref in self.bad_dt_conversion:
            self.assertRaises(generatenameconfig.PrefValueInvalidError,
                              generatename.convert_date_for_strftime,
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
