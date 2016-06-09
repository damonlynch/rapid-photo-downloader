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

def install_instructions():
    debian = 'On an Ubuntu or Debian-like system, the following command will install ' \
             'the base installation requirements:\nsudo apt-get install '\
             'libimage-exiftool-perl python3-pyqt5 python3-pip python3-setuptools python3-dev ' \
             'python3-distutils-extra gir1.2-gexiv2-0.10 python3-gi gir1.2-gudev-1.0 ' \
             'gir1.2-udisks-2.0 gir1.2-notify-0.7 gir1.2-glib-2.0 gir1.2-gstreamer-1.0 '\
             'libgphoto2-dev python3-arrow python3-psutil '\
             'qt5-image-formats-plugins python3-zmq exiv2 python3-colorlog libraw-bin ' \
             'python3-easygui libmediainfo0v5 python3-sortedcontainers\n'
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
        have_gi = True
    except ImportError:
        import_msgs.append('python3 gobject introspection')
        have_gi = False
    if have_gi:
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
            if StrictVersion(gphoto2.__version__) < StrictVersion('1.3.4'):
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
        "build_icons" : build_icons.build_icons,
        'install': install,
        'clean': clean_extra,
        "build_i18n": build_i18n.build_i18n,
    },
)
