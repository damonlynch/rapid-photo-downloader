#!/usr/bin/env python3

# Copyright (C) 2010-2018 Damon Lynch <damonlynch@gmail.com>

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
# along with Rapid Photo Downloader. If not,
# see <http://www.gnu.org/licenses/>.


"""
Simple utility to update translations for Rapid Photo Downloader using
Launchpad translations tarball.

Not included in program tarball distributed to end users.
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2010-2018, Damon Lynch"


import tarfile
import tempfile
import os
import glob
import polib
import datetime


blacklist = ['gl', 'lt', 'fil', 'en_AU', 'en_GB', 'eo']
whitelist = [
    'ar', 'da', 'fr', 'it', 'fi', 'sk', 'ru', 'sr', 'es', 'pl', 'nl', 
    'sv', 'cs', 'hu', 'de', 'uk', 'zh_CN', 'pt_BR', 'tr', 'bg', 'ja', 'oc', 
    'fa', 'nn', 'nb', 'pt', 'hr', 'ro', 'id', 'kab', 'et', 'be', 'ca', 'el'
]


def get_lang(pofile):
    f = os.path.split(pofile)[1]
    lang = f[len('rapid-photo-downloader-'):-3]
    return lang


home = os.path.expanduser('~')
po_destination_dir = os.path.abspath(os.path.join(os.path.realpath(__file__), '../../po'))

po_backup_dir = '{}/backup.po'.format(home)
date_format = '%Y-%m-%d %H:%M'

translations_tar = os.path.join(home, 'launchpad-export.tar.gz')
backup_tar = os.path.join(po_backup_dir, 'launchpad-export.tar.gz')

tempdir = tempfile.mkdtemp()
po_dir = os.path.join(tempdir, 'po')

tar = tarfile.open(translations_tar)
tar.extractall(path=tempdir)

if os.path.exists(backup_tar):
    os.unlink(backup_tar)


updated_langs = []
unknown_langs = []
known_langs = []

for pofile in glob.iglob(os.path.join(po_dir, '*.po')):
    lang = get_lang(pofile)
    if (lang not in blacklist) and (lang not in whitelist):
        unknown_langs.append(lang)
    elif lang in whitelist:
        known_langs.append(pofile)

print("Working with {} translations".format(len(whitelist)))

if unknown_langs:
    print("WARNING: unrecognized languages are", unknown_langs)
    print("Add to whitelist or blacklist to proceed!")

else:
    for pofile in known_langs:
        lang = get_lang(pofile)
        po = polib.pofile(pofile)
        date = po.metadata['PO-Revision-Date'].split('+')[0]
        lang_english = po.metadata['Language-Team'].split()[0]
        if lang_english == 'Français':
            lang_english = 'French'
        elif lang_english == 'српски':
            lang_english = 'Serbian'
        # elif lang_english == ''
        #     lang_english = 'Brazilian Portuguese'
        print("Working with ", lang_english, pofile)
        dest_pofile = '{}.po'.format(os.path.join(po_destination_dir, lang))
        if not os.path.exists(dest_pofile):
            print('Added ', lang_english)
            os.rename(pofile, dest_pofile)
        else:
            dest_po = polib.pofile(dest_pofile)
            dest_date = dest_po.metadata['PO-Revision-Date'].split('+')[0]
            date_p = datetime.datetime.strptime(date, date_format)
            dest_date_p = datetime.datetime.strptime(dest_date, date_format)
            if date_p > dest_date_p:
                updated_langs.append(lang_english)
                backupfile = os.path.join(po_backup_dir, '%s.po' % lang)
                if os.path.exists(backupfile):
                    os.unlink(backupfile)
                os.rename(dest_pofile, backupfile)
                os.rename(pofile, dest_pofile)


    updated_langs.sort()
    updated_langs_english = ''
    for i in updated_langs[:-1]:
        updated_langs_english = updated_langs_english + ', %s' % i

    if len(updated_langs) > 1:
        updated_langs_english = updated_langs_english[2:] + ' and %s' % updated_langs[-1]

    print('Updated {} translations.\n'.format(updated_langs_english))

    if unknown_langs:
        print("WARNING: unrecognized languages are", unknown_langs)

    print("Backing up translations tar %s to %s" % (translations_tar, backup_tar))
    os.rename(translations_tar, backup_tar)


for f in os.listdir(po_dir):
    os.unlink(os.path.join(po_dir, f))
os.rmdir(po_dir)
os.rmdir(tempdir)
