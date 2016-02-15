#!/usr/bin/python3

# Copyright (C) 2009-2016 Damon Lynch <damonlynch@gmail.com>

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

# Contains some elements Copyright 2014 Donald Stufft

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2009-2016, Damon Lynch"

import os
import sys
import shutil
from setuptools import setup
# from DistUtilsExtra.auto import *
# from DistUtilsExtra.command import *

install_error_message = "This program requires {}.\nPlease install it using your distribution's " \
                        "standard installation tools.\n"

try:
    import PyQt5
except ImportError:
    sys.stderr.write(install_error_message.format('PyQt5'))
import gi

try:
    gi.require_version('GUdev', '1.0')
except ValueError:
    sys.stderr.write(install_error_message.format('GUdev 1.0 from gi.repository'))

try:
    gi.require_version('UDisks', '2.0')
except ValueError:
     sys.stderr.write(install_error_message.format('UDisks 2.0 from gi.repository'))
try:
     gi.require_version('GLib', '2.0')
except ValueError:
    sys.stderr.write(install_error_message.format('GLib 2.0 from gi.repository'))
try:
    gi.require_version('GExiv2', '0.10')
except ValueError:
    sys.stderr.write(install_error_message.format('GExiv2 0.10 from gi.repository'))
try:
    gi.require_version('Gst', '1.0')
except ValueError:
    sys.stderr.write(install_error_message.format('Gst 1.0 from gi.repository'))
try:
    gi.require_version('Notify', '0.7')
except ValueError:
    sys.stderr.write(install_error_message.format('Notify 0.7 from gi.repository'))

if  shutil.which('exiftool') is None:
    sys.stderr.write(install_error_message.format('ExifTool'))

here = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(here, "raphodo", "__about__.py")) as f:
    about = {}
    exec(f.read(), about)

with open(os.path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

#TODO generate helpful automatically, and install it
#TODO ensure icons are installed

setup(
    name=about["__title__"],
    version=about["__version__"],

    description=about["__summary__"],
    long_description=long_description,
    license=about["__license__"],
    url=about["__uri__"],

    author=about["__author__"],
    author_email=about["__email__"],

    install_requires=['gphoto2',
                      'pyzmq',
                      'psutil',
                      'sortedcontainers',
                      'pyxdg',
                      'arrow',
                      'python-dateutil',
                      ],
    extras_require={':python_version == "3.4"': ['scandir', 'typing']},
    #include_package_data = True,
    exclude_package_data = {'rapid-photo-downloader': ['doc/rapid-photo-downloader.pod']},
    packages = ['raphodo'],
    entry_points={
        'gui_scripts': [
            'rapid-photo-downloader=rapid.rapid:main',
        ]
    },
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: X11 Applications :: Qt',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Topic :: Multimedia :: Graphics',
        'Topic :: Multimedia :: Video'
        ],
    keywords='photo, video, download, ingest, import, camera, phone, backup, rename, photography,' \
             ' photographer, transfer, copy, raw, cr2, nef, arw',

)
