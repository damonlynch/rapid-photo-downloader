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
# import glob
# import re
import os.path
from distutils.version import StrictVersion
from setuptools import setup, Command
from setuptools.command.install import install
# import distutils.cmd
from DistUtilsExtra.command  import * #build_extra, build_i18n, build_icons, clean_i18n

def install_instructions():
    debian = 'On an Ubuntu or Debian-like system, the following command will install all ' \
             'necessary requirements:\nsudo apt-get install ' \
             'libimage-exiftool-perl python3-pyqt5 ' \
             'python3-distutils-extra gir1.2-gexiv2-0.10 python3-gi gir1.2-gudev-1.0 ' \
             'gir1.2-udisks-2.0 gir1.2-notify-0.7 gir1.2-glib-2.0 gir1.2-gstreamer-1.0 ' \
             'libgphoto2-dev libzmq3\n'
    if os.path.isfile('/etc/os-release'):
        with open('/etc/os-release', 'r') as f:
            for line in f:
                if line.startswith('ID_LIKE='):
                    if line.find('debian' , 7) >= 0:
                        sys.stderr.write(debian)
                    break

def check_package_import_requirements():

    import_msgs = []

    try:
        import PyQt5
    except ImportError:
        import_msgs.append('python3 PyQt5')
    try:
        import gi
    except ImportError:
        import_msgs.append('python3 gobject introspection')
    try:
        gi.require_version('GUdev', '1.0')
    except ValueError:
        import_msgs.append('GUdev 1.0 from gi.repository')
    try:
        gi.require_version('UDisks', '2.0')
    except ValueError:
        import_msgs.append('UDisks 2.0 from gi.repository')
    try:
         gi.require_version('GLib', '2.0')
    except ValueError:
        import_msgs.append('GLib 2.0 from gi.repository')
    try:
        gi.require_version('GExiv2', '0.10')
    except ValueError:
        import_msgs.append('GExiv2 0.10 from gi.repository')
    try:
        gi.require_version('Gst', '1.0')
    except ValueError:
        import_msgs.append('Gst 1.0 from gi.repository')
    try:
        gi.require_version('Notify', '0.7')
    except ValueError:
        import_msgs.append('Notify 0.7 from gi.repository')
    if shutil.which('exiftool') is None:
        import_msgs.append('ExifTool')
    if len(import_msgs):
        install_error_message = "This program requires:\n{}\nPlease install them " \
                                "using your distribution's standard installation tools.\n"
        sys.stderr.write(install_error_message.format('\n'.join(s for s in import_msgs)))
        install_instructions()
        sys.exit(1)
    try:
        import gphoto2
        try:
            if StrictVersion(gphoto2.__version__) < StrictVersion('1.3.3'):
                raise ImportError
        except:
            raise ImportError
    except ImportError:
        sys.stderr.write('Warning: the development files for libgphoto2 are required to install or '
                         'upgrade python gphoto2 (https://pypi.python.org/pypi/gphoto2/).\n')
        install_instructions()

check_package_import_requirements()

here = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(here, "raphodo", "__about__.py")) as f:
    about = {}
    exec(f.read(), about)


class build_extra(build_extra.build):
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
    description = "build POD manual pages"

    user_options = [('pod-files=', None, 'POD files to build')]

    def initialize_options(self):
        self.pod_files = []

    def finalize_options(self):
        pass

    def run(self):
        for pod_file in ('doc/rapid-photo-downloader.1.pod',):
            if not os.path.exists(pod_file):
                sys.stderr.write('Warning: could not locate {}\n'.format(pod_file))
                continue
            name = os.path.basename(pod_file)[:-6].upper()
            self.spawn(['pod2man', '--section=1', '--release={}'.format(about["__version__"]),
                    "--center=General Commands Manual", '--name="{}"'.format(name),
                    pod_file, os.path.splitext(pod_file)[0]])


with open(os.path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

#TODO generate help file automatically, and install it
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
    include_package_data = True,
    exclude_package_data = {'rapid-photo-downloader': ['doc/rapid-photo-downloader.pod']},
    data_files = [
        ('/usr/share/man/man1', ['doc/rapid-photo-downloader.1',])
    ],
    packages = ['raphodo'],
    entry_points={
        'gui_scripts': [
            'rapid-photo-downloader=raphodo.rapid:main',
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

    cmdclass={
        'build': build_extra,
        'build_pod2man': build_pod2man,
        'install': install,
        # 'clean': clean_extra,
        },
)
