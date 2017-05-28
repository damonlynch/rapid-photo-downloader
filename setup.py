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

# Copyright 2009-2016 Damon Lynch
# Contains portions Copyright 2014 Donald Stufft
# Contains portions Copyright 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012, Canonical Ltd

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2009-2016, Damon Lynch"

import os
import sys
import shutil
import os.path
from glob import glob
from distutils.version import StrictVersion
from distutils.command.clean import clean
from setuptools import setup, Command
from setuptools.command.install import install
from DistUtilsExtra.command  import *  # build_extra, build_i18n, build_icons, clean_i18n


here = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(here, "raphodo", "__about__.py")) as f:
    about = {}
    exec(f.read(), about)


class build_extra(build_extra.build):
    """
    Taken from the Canonical project 'germinate'
    """
    def __init__(self, dist):
        super().__init__(dist)
        self.user_options.extend([('pod2man', None, 'use pod2man')])

    def initialize_options(self):
        super().initialize_options()
        self.pod2man = False

    def finalize_options(self):
        def has_pod2man(command):
            return self.pod2man == 'True'

        super().finalize_options()
        self.sub_commands.append(('build_pod2man', has_pod2man))


class build_pod2man(Command):
    """
    Based on code in the Canonical project 'germinate'
    """
    description = "build POD manual pages"

    user_options = [('pod-files=', None, 'POD files to build')]

    def initialize_options(self):
        self.pod_files = []

    def finalize_options(self):
        pass

    def run(self):
        for pod_file in glob('doc/*.1.pod'):
            name = os.path.basename(pod_file)[:-6].upper()
            build_path =  os.path.join('build', os.path.splitext(pod_file)[0])
            if not os.path.isdir(os.path.join('build', 'doc')):
                os.mkdir(os.path.join('build', 'doc'))
            self.spawn(['pod2man', '--section=1', '--release={}'.format(about["__version__"]),
                    "--center=General Commands Manual", '--name="{}"'.format(name),
                    pod_file, build_path])


class clean_extra(clean):
    def run(self):
        clean.run(self)

        for path, dirs, files in os.walk('.'):
            for i in reversed(range(len(dirs))):
                if dirs[i].startswith('.') or dirs[i] == 'debian':
                    del dirs[i]
                elif dirs[i] == '__pycache__' or dirs[i].endswith('.egg-info'):
                    self.spawn(['rm', '-r', os.path.join(path, dirs[i])])
                    del dirs[i]

            for f in files:
                f = os.path.join(path, f)
                if f.endswith('.pyc'):
                    self.spawn(['rm', f])
                elif f.startswith('./debhelper') and f.endswith('.1'):
                    self.spawn(['rm', f])


with open(os.path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name=about["__title__"],
    version=about["__version__"],

    description=about["__summary__"],
    long_description=long_description,
    license=about["__license__"],
    url=about["__uri__"],

    author=about["__author__"],
    author_email=about["__email__"],
    zip_safe=False,
    install_requires=['gphoto2',
                      'pyzmq',
                      'psutil',
                      'pyxdg',
                      'arrow',
                      'python-dateutil',
                      'colorlog',
                      'pyprind',
                      'rawkit',
                      'easygui',
                      'colour',
                      'pymediainfo',
                      'sortedcontainers'
                      ],
    extras_require={':python_version == "3.4"': ['scandir', 'typing']},
    include_package_data = False,
    data_files = [
        ('share/man/man1', ['build/doc/rapid-photo-downloader.1',
                            'build/doc/analyze-pv-structure.1']),
        ('share/applications', ['build/share/applications/rapid-photo-downloader.desktop']),
        ('share/solid/actions', ['build/share/solid/actions/rapid-photo-downloader.desktop'],),
        ('share/appdata', ['build/share/appdata/rapid-photo-downloader.appdata.xml'])
    ],
    packages = ['raphodo'],
    entry_points={
        'gui_scripts': [
            'rapid-photo-downloader=raphodo.rapid:main',
        ],
        'console_scripts': [
            'analyze-pv-structure=raphodo.analyzephotos:main'
        ]
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: X11 Applications :: Qt',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: Multimedia :: Graphics',
        'Topic :: Multimedia :: Video'
        ],
    keywords='photo, video, download, ingest, import, camera, phone, backup, rename, photography,' \
             ' photographer, transfer, copy, raw, cr2, nef, arw',
    cmdclass={
        'build': build_extra,
        'build_pod2man': build_pod2man,
        "build_icons" : build_icons.build_icons,
        'install': install,
        'clean': clean_extra,
        "build_i18n": build_i18n.build_i18n,
    },
)
