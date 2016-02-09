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
import xml.etree.ElementTree as ET
from setuptools import setup

install_error_message = "This program requires {}.\nPlease install it using your distribution's " \
                        "standard installation tools."

try:
    import PyQt5
except ImportError:
    sys.stderr.write(install_error_message.format('PyQt5'))
try:
    from gi.repository import GUdev
except ImportError:
    sys.stderr.write(install_error_message.format('GUdev from gi.repository'))
try:
    from gi.repository import UDisks
except ImportError:
    sys.stderr.write(install_error_message.format('UDisks from gi.repository'))
try:
    from gi.repository import GLib
except ImportError:
    sys.stderr.write(install_error_message.format('GLib from gi.repository'))
try:
    from gi.repository import GExiv2
except ImportError:
    sys.stderr.write(install_error_message.format('GExiv2 from gi.repository'))
if  shutil.which('exiftool') is None:
    sys.stderr.write(install_error_message.format('ExifTool'))

base_dir = os.path.dirname(__file__)

with open(os.path.join(base_dir, "rapid", "__about__.py")) as f:
    about = {}
    exec(f.read(), about)

tree = ET.parse(os.path.join(base_dir, 'linux', 'rapid-photo-downloader.appdata.xml'))
root = tree.getroot()
paragraphs = root.find('description').getchildren()
long_description = '\n\n'.join(([' '.join(p.text.split()) for p in paragraphs]))

if sys.version_info < (3,5):
    additional_requires = ['scandir', 'typing']
else:
    additional_requires = []

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
                      ] + additional_requires,
    packages = ['rapid'],
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
        ]

)
