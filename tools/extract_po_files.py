#!/usr/bin/env python3

# Copyright (C) 2010-2024 Damon Lynch <damonlynch@gmail.com>

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

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2010-2024, Damon Lynch"


import argparse
import glob
import os
import pickle
import re
import tarfile
import tempfile
import warnings
from collections import namedtuple

import arrow
import polib
import sortedcontainers
from launchpadlib.launchpad import Launchpad
from packaging.version import parse

arrow_version = parse(arrow.__version__)
# Suppress parsing warnings for 0.14.3 <= Arrow version < 0.15
if arrow_version >= parse("0.14.3") and arrow_version < parse("0.15.0"):
    from arrow.factory import ArrowParseWarning

    warnings.simplefilter("ignore", ArrowParseWarning)

blacklist = [
    "gl",
    "lt",
    "fil",
    "en_AU",
    "en_GB",
    "en_US",
    "en_CA",
    "eo",
    "ku",
    "fa",
    "gd",
    "cy",
]
whitelist = [
    "ar",
    "da",
    "fr",
    "it",
    "fi",
    "sk",
    "ru",
    "sr",
    "es",
    "pl",
    "nl",
    "sv",
    "cs",
    "hu",
    "de",
    "uk",
    "zh_CN",
    "pt_BR",
    "tr",
    "bg",
    "ja",
    "oc",
    "nn",
    "nb",
    "pt",
    "hr",
    "ro",
    "id",
    "kab",
    "et",
    "be",
    "ca",
    "el",
    "sq",
]

language_name_substitutions = dict(
    Français="French",
    српски="Serbian",
    magyar="Hungarian",
)
language_name_substitutions["Norwegian Bokmal"] = "Norwegian Bokmål"


class bcolors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


details = namedtuple("details", "release_date url bare_url")

home = os.path.expanduser("~")
cachedir = os.path.join(home, ".launchpadlib/cache/")
releases_cache = os.path.join(cachedir, "releases_cache")


def parser_options(formatter_class=argparse.HelpFormatter):
    parser = argparse.ArgumentParser(
        prog="Extract po files",
        description="Update translations from launchpad",
        formatter_class=formatter_class,
    )

    parser.add_argument(
        "-d", "--dry-run", action="store_true", help="Simulate translation update."
    )

    return parser


def get_lang(pofile_name):
    return os.path.basename(pofile_name)[len("rapid-photo-downloader-") : -3]


def get_latest_release_date():
    if os.path.exists(releases_cache):
        with open(releases_cache, "rb") as f:
            cache = pickle.load(f)
    else:
        cache = dict()

    print("Logging in to launchpad to get latest release details...")
    launchpad = Launchpad.login_anonymously("latest-version", "production", cachedir)
    print("Accessing project...")
    p = launchpad.projects["rapid"]
    print("Finding releases...")
    releases = p.releases

    stable_releases = sortedcontainers.SortedDict()
    dev_releases = sortedcontainers.SortedDict()

    for lang in releases:
        if str(lang) not in cache:
            release_date = arrow.get(lang.date_released)
            for t in lang.files:
                # print(t.lp_attributes)
                # print(t.lp_entries)
                if str(t).find("tar.gz") >= 0:
                    t_name = str(t)
                    # t: e.g. https://api.edge.launchpad.net/beta/rapid/0.1.0/0.0.8beta2/+file/rapid-photo-downloader-0.0.8~b2.tar.gz
                    # want: <a href="http://launchpad.net/rapid/0.1.0/0.0.8beta2/+download/rapid-photo-downloader-0.0.8~b2.tar.gz">

                    i = t_name.find("rapid")
                    j = t_name.find("+file")

                    package = t_name[j + 6 :]
                    parsed_version = package[: package.find("tar") - 1]

                    first_digit = re.search("\d", parsed_version)
                    if first_digit.start():
                        version_raw = parsed_version[first_digit.start() :]
                        version_number = version_raw.replace("~", "")
                        version = parse(version_number)
                        bare_link = (
                            "https://launchpad.net/" + t_name[i:j] + "+download/"
                        )
                        link = bare_link + package
                        print("Processing version", version)

                        detail = details(release_date, link, bare_link)
                        if version.is_prerelease:
                            dev_releases[version] = detail
                        else:
                            stable_releases[version] = detail

                        cache[str(lang)] = (
                            str(version),
                            str(release_date),
                            link,
                            bare_link,
                        )
                        break
        else:
            version_number, release_date, link, bare_link = cache[str(lang)]
            version = parse(version_number)
            release_date = arrow.get(release_date)
            detail = details(release_date, link, bare_link)
            if version.is_prerelease:
                dev_releases[version] = detail
            else:
                stable_releases[version] = detail

    stable_version, detail = stable_releases.peekitem()
    stable_release_date, stable_url, stable_base_url = detail

    stable_version_hr = str(stable_version)
    stable_date_hr = str(stable_release_date)

    dev_version, detail = dev_releases.peekitem()
    if dev_version > stable_version:
        message = (
            "Development version is latest release. Use development "
            "instead of stable release date? [y/N]"
        )
        use_devel = input(message).lower()[0] == "y"

    else:
        use_devel = False

    if use_devel:
        dev_release_date, dev_url, dev_base_url = detail
        latest_release_date = dev_release_date
    else:
        dev_release_date, dev_url, dev_base_url = stable_releases.peekitem()[1]
        dev_version = stable_version
        latest_release_date = stable_release_date

    dev_version_hr = str(dev_version)
    dev_date_hr = str(dev_release_date)

    print("latest stable release is", stable_version_hr, "released", stable_date_hr)
    if dev_version > stable_version:
        print("latest dev release is", dev_version_hr, "released", dev_date_hr)

    with open(releases_cache, "wb") as f:
        pickle.dump(cache, f, pickle.HIGHEST_PROTOCOL)

    return latest_release_date


parser = parser_options()
args = parser.parse_args()

dry_run = args.dry_run
os.makedirs(cachedir, exist_ok=True)

latest_release_date = get_latest_release_date()

lang_english_re = re.compile("(.+)<.+>")

po_destination_dir = os.path.abspath(
    os.path.join(os.path.realpath(__file__), "../../po")
)
print("\nInstalling po files into", po_destination_dir)

po_backup_dir = f"{home}/backup.po"
if not os.path.isdir(po_backup_dir):
    os.mkdir(po_backup_dir)

date_format = "%Y-%m-%d %H:%M"

translations_tar = os.path.join(home, "launchpad-export.tar.gz")
backup_tar = os.path.join(po_backup_dir, "launchpad-export.tar.gz")

tempdir = tempfile.mkdtemp(dir=home)
source_po_dir = os.path.join(tempdir, "po")

tar = tarfile.open(translations_tar)
tar.extractall(path=tempdir)

if os.path.exists(backup_tar):
    os.unlink(backup_tar)

updated_langs = []
unknown_langs = []
known_langs = []

for pofile in glob.iglob(os.path.join(source_po_dir, "*.po")):
    lang = get_lang(pofile)
    if (lang not in blacklist) and (lang not in whitelist):
        unknown_langs.append(lang)
    elif lang in whitelist:
        known_langs.append(pofile)

print(f"Working with {len(whitelist)} translations\n")

if unknown_langs:
    print("WARNING: unrecognized languages are", unknown_langs)
    print("Add to whitelist or blacklist to proceed!")

else:
    known_langs.sort()
    for pofile in known_langs:
        lang = get_lang(pofile)
        po = polib.pofile(pofile)
        date = po.metadata["PO-Revision-Date"]
        last_modified_by = po.metadata["Last-Translator"]
        last_modified_by_lp = (
            last_modified_by.find("Launchpad Translations Administrators") >= 0
        )
        re_match = lang_english_re.search(po.metadata["Language-Team"])
        if re_match:
            lang_english = re_match.group(1).strip()
            lang_english = language_name_substitutions.get(lang_english) or lang_english
            dest_pofile = f"{os.path.join(po_destination_dir, lang)}.po"
            if not os.path.exists(dest_pofile):
                print("Added ", lang_english)
                os.rename(pofile, dest_pofile)
            else:
                dest_po = polib.pofile(dest_pofile)
                dest_date = dest_po.metadata["PO-Revision-Date"]
                date_p = arrow.get(date)
                dest_date_p = arrow.get(dest_date)
                if not last_modified_by_lp:
                    if date_p > latest_release_date:
                        # This po file contains real changes since the last release
                        print(
                            "{}{:21}: modified {}{}".format(
                                bcolors.OKGREEN,
                                lang_english,
                                date_p.humanize(),
                                bcolors.ENDC,
                            )
                        )
                        updated_langs.append(lang_english)
                    else:
                        print(f"{lang_english:21}: updating local copy from launchpad")
                    if not dry_run:
                        backupfile = os.path.join(po_backup_dir, "%s.po" % lang)
                        if os.path.exists(backupfile):
                            os.unlink(backupfile)
                        os.rename(dest_pofile, backupfile)
                        os.rename(pofile, dest_pofile)
                else:
                    print(f"{lang_english:21}: no change")

    print()
    if updated_langs:
        updated_langs.sort()
        if len(updated_langs) > 1:
            updated_langs_english = ", ".join(updated_langs[:-1])
            updated_langs_english = (
                updated_langs_english + " and %s" % updated_langs[-1]
            )
            print(f"Update {updated_langs_english} translations\n")
        else:
            print(f"Update {updated_langs[0]} translation\n")
    else:
        print("No language updates")

    if unknown_langs:
        print("WARNING: unrecognized languages are", unknown_langs)

    if not dry_run:
        print(f"Backing up translations tar {translations_tar} to {backup_tar}")
        os.rename(translations_tar, backup_tar)


for f in os.listdir(source_po_dir):
    os.unlink(os.path.join(source_po_dir, f))
os.rmdir(source_po_dir)
os.rmdir(tempdir)
