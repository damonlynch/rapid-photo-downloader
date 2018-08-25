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
Launchpad translations tarball, which is expected to be in the home directory.

Not included in program tarball distributed to end users.
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2010-2018, Damon Lynch"


import tarfile
import tempfile
import os
import glob
import polib
import arrow
import re


blacklist = ['gl', 'lt', 'fil', 'en_AU', 'en_GB', 'eo', 'ku']
whitelist = [
    'ar', 'da', 'fr', 'it', 'fi', 'sk', 'ru', 'sr', 'es', 'pl', 'nl', 
    'sv', 'cs', 'hu', 'de', 'uk', 'zh_CN', 'pt_BR', 'tr', 'bg', 'ja', 'oc', 
    'fa', 'nn', 'nb', 'pt', 'hr', 'ro', 'id', 'kab', 'et', 'be', 'ca', 'el'
]


def get_lang(pofile_name):
    return os.path.basename(pofile_name)[len('rapid-photo-downloader-'):-3]


lang_english_re = re.compile('(.+)<.+>')

home = os.path.expanduser('~')
po_destination_dir = os.path.abspath(os.path.join(os.path.realpath(__file__), '../../po'))
print("Installing po files into", po_destination_dir)

po_backup_dir = '{}/backup.po'.format(home)
if not os.path.isdir(po_backup_dir):
    os.mkdir(po_backup_dir)

date_format = '%Y-%m-%d %H:%M'

translations_tar = os.path.join(home, 'launchpad-export.tar.gz')
backup_tar = os.path.join(po_backup_dir, 'launchpad-export.tar.gz')

tempdir = tempfile.mkdtemp()
source_po_dir = os.path.join(tempdir, 'po')

tar = tarfile.open(translations_tar)
tar.extractall(path=tempdir)

if os.path.exists(backup_tar):
    os.unlink(backup_tar)

updated_langs = []
unknown_langs = []
known_langs = []

for pofile in glob.iglob(os.path.join(source_po_dir, '*.po')):
    lang = get_lang(pofile)
    if (lang not in blacklist) and (lang not in whitelist):
        unknown_langs.append(lang)
    elif lang in whitelist:
        known_langs.append(pofile)

print("Working with {} translations\n".format(len(whitelist)))

if unknown_langs:
    print("WARNING: unrecognized languages are", unknown_langs)
    print("Add to whitelist or blacklist to proceed!")

else:
    known_langs.sort()
    for pofile in known_langs:
        lang = get_lang(pofile)
        po = polib.pofile(pofile)
        date = po.metadata['PO-Revision-Date']
        match = lang_english_re.search(po.metadata['Language-Team'])
        if match:
            lang_english = match.group(1).strip()
            if lang_english == 'Français':
                lang_english = 'French'
            elif lang_english == 'српски':
                lang_english = 'Serbian'
            elif lang_english == 'magyar':
                lang_english = 'Hungarian'
            dest_pofile = '{}.po'.format(os.path.join(po_destination_dir, lang))
            if not os.path.exists(dest_pofile):
                print('Added ', lang_english)
                os.rename(pofile, dest_pofile)
            else:
                dest_po = polib.pofile(dest_pofile)
                dest_date = dest_po.metadata['PO-Revision-Date']
                date_p = arrow.get(date)
                dest_date_p = arrow.get(dest_date)
                if date_p > dest_date_p:
                    print('{:21}: modified {}'.format(lang_english, date_p.humanize()))

                    updated_langs.append(lang_english)
                    backupfile = os.path.join(po_backup_dir, '%s.po' % lang)
                    if os.path.exists(backupfile):
                        os.unlink(backupfile)
                    os.rename(dest_pofile, backupfile)
                    os.rename(pofile, dest_pofile)
                else:
                    print(
                        '{:21}: no change (last modified {})'.format(
                            lang_english, date_p.humanize()
                        )
                    )

    print()
    if updated_langs:
        updated_langs.sort()
        if len(updated_langs) > 1:
            updated_langs_english = ', '.join(updated_langs[:-1])
            updated_langs_english = updated_langs_english + ' and %s' % updated_langs[-1]
            print('Updated {} translations.\n'.format(updated_langs_english))
        else:
            print('Updated {} translation.\n'.format(updated_langs[0]))
    else:
        print("No updated languages")

    if unknown_langs:
        print("WARNING: unrecognized languages are", unknown_langs)

    print("Backing up translations tar %s to %s" % (translations_tar, backup_tar))
    os.rename(translations_tar, backup_tar)


for f in os.listdir(source_po_dir):
    os.unlink(os.path.join(source_po_dir, f))
os.rmdir(source_po_dir)
os.rmdir(tempdir)
