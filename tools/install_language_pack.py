#!/usr/bin/env python3

# Copyright (C) 2020-2024 Damon Lynch <damonlynch@gmail.com>

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
Utility to generate command line to install on a Debian like system all
language packs needed to test Rapid Photo Downloader translations
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2020-2024, Damon Lynch"
__title__ = __file__
__description__ = 'Install language packs for Rapid Photo Downloader testing.'

import glob
import os

import apt

apt_cache = apt.Cache()

blacklist = ['gl', 'lt', 'fil', 'en_AU', 'en_GB', 'eo', 'ku']
whitelist = [
    'ar', 'da', 'fr', 'it', 'fi', 'sk', 'ru', 'sr', 'es', 'pl', 'nl',
    'sv', 'cs', 'hu', 'de', 'uk', 'zh_CN', 'pt_BR', 'tr', 'bg', 'ja', 'oc',
    'fa', 'nn', 'nb', 'pt', 'hr', 'ro', 'id', 'kab', 'et', 'be', 'ca', 'el', 'sq'
]

hunspell_convert = dict(
    pt_BR='pt-br',
    fa='',
    fi='',
    kab='',
    nn='no',
    nb='',
    de='de-de',
    ja='',
    pt='pt-pt',
    zh_CN='',
    et='',
    sq=''
)

lang_pack_convert = dict(
    pt_BR='',
    zh_CN='zh-hans zh-hant',
    kab='',
)

unknown_langs = []
wrong_package_name = []
install_lang_pack = []
install_hunspell = []


def get_lang(pofile_name:str) -> str:
    return os.path.splitext(os.path.split(pofile_name)[1])[0]


po_dir = os.path.abspath(os.path.join(os.path.realpath(__file__), '../../po'))

for pofile in glob.iglob(os.path.join(po_dir, '*.po')):
    lang = get_lang(pofile)
    if (lang not in blacklist) and (lang not in whitelist):
        unknown_langs.append(lang)
    elif lang in whitelist:
        lp = lang_pack_convert.get(lang, lang)
        if lp:
            for i in lp.split():
                package = f'language-pack-{i}'
                if package in apt_cache:
                    install_lang_pack.append(package)
                else:
                    wrong_package_name.append(package)

        h = hunspell_convert.get(lang, lang)
        if h:
            package = f'hunspell-{h}'
            if package in apt_cache:
                install_hunspell.append(package)
            else:
                wrong_package_name.append(package)


language_packs = ' '.join(install_lang_pack)
hunspell_packs = ' '.join(install_hunspell)

if unknown_langs:
    print("Unknown langauges:")
    print('\n'.join(unknown_langs))
elif wrong_package_name:
    print("Unknown packages:")
    print('\n'.join(wrong_package_name))
else:
    print('#!/bin/sh')
    for package_list in (language_packs, hunspell_packs):
        command = f'sudo apt -y install {package_list}'
        print(command)
