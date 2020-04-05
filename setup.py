#!/usr/bin/python3

# Copyright (C) 2009-2020 Damon Lynch <damonlynch@gmail.com>

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

# Copyright 2009-2020 Damon Lynch
# Contains portions Copyright 2014 Donald Stufft
# Contains portions Copyright 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012, Canonical Ltd

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2009-2020, Damon Lynch. Copyright 2004-2012 Canonical Ltd. " \
                "Copyright 2014 Donald Stufft."

import os
from glob import glob
from distutils.command.build import build
from setuptools import setup, Command
from setuptools.command.sdist import sdist


here = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(here, "raphodo", "__about__.py")) as f:
    about = {}
    exec(f.read(), about)


class build_translations(Command):
    """
    Adapted from DistutilsExtra.

    March, 2020: delete setup.cfg, place options here. Cut out extraneous code from
    DistutilsExtra we do not need.
    """

    description = "integrate the gettext framework"

    user_options = [
        ('desktop-files=', None, '.desktop.in files that should be merged'),
        ('xml-files=', None, '.xml.in files that should be merged'),
        ('domain=', 'd', 'gettext domain'),
        ('merge-po', 'm', 'merge po files against template'),
        ('po-dir=', 'p', 'directory that holds the i18n files'),
        ('bug-contact=', None, 'contact address for msgid bugs')
    ]

    boolean_options = ['merge-po']

    def initialize_options(self):
        self.desktop_files = [
            ("share/applications", ("data/net.damonlynch.rapid_photo_downloader.desktop.in",)),
            ("share/solid/actions", ("data/kde/net.damonlynch.rapid_photo_downloader.desktop.in",))
        ]
        self.xml_files = [
            ("share/metainfo", ("data/net.damonlynch.rapid_photo_downloader.metainfo.xml.in",))
        ]

        self.domain = 'rapid-photo-downloader'
        self.merge_po = False
        self.bug_contact = 'damonlynch@gmail.com'
        self.po_dir = 'po'

    def finalize_options(self):
        if self.domain is None:
            self.domain = self.distribution.metadata.name
        if self.po_dir is None:
            self.po_dir = "po"

    def run(self):
        """
        Update the language files, generate mo files and add them
        to the to be installed files
        """
        if not os.path.isdir(self.po_dir):
            return

        data_files = self.distribution.data_files

        os.environ["XGETTEXT_ARGS"] = "--msgid-bugs-address=%s " % self.bug_contact

        # If there is a po/LINGUAS file, or the LINGUAS environment variable
        # is set, only compile the languages listed there.
        selected_languages = None
        linguas_file = os.path.join(self.po_dir, "LINGUAS")
        if os.path.isfile(linguas_file):
            selected_languages = open(linguas_file).read().split()
        if "LINGUAS" in os.environ:
            selected_languages = os.environ["LINGUAS"].split()

        # Update po(t) files and print a report
        # We have to change the working dir to the po dir for intltool
        cmd = ["intltool-update", (self.merge_po and "-r" or "-p"), "-g", self.domain]
        wd = os.getcwd()
        os.chdir(self.po_dir)
        self.spawn(cmd)
        os.chdir(wd)
        max_po_mtime = 0
        for po_file in glob("%s/*.po" % self.po_dir):
            lang = os.path.basename(po_file[:-3])
            if selected_languages and not lang in selected_languages:
                continue
            mo_dir =  os.path.join("build", "mo", lang, "LC_MESSAGES")
            mo_file = os.path.join(mo_dir, "%s.mo" % self.domain)
            if not os.path.exists(mo_dir):
                os.makedirs(mo_dir)
            cmd = ["msgfmt", po_file, "-o", mo_file]
            po_mtime = os.path.getmtime(po_file)
            mo_mtime = os.path.exists(mo_file) and os.path.getmtime(mo_file) or 0
            if po_mtime > max_po_mtime:
                max_po_mtime = po_mtime
            if po_mtime > mo_mtime:
                self.spawn(cmd)

            targetpath = os.path.join("share/locale", lang, "LC_MESSAGES")
            data_files.append((targetpath, (mo_file,)))

        # merge .in with translation
        for (file_set, switch) in ((self.xml_files, "-x"), (self.desktop_files, "-d")):
            for (target, files) in file_set:
                build_target = os.path.join("build", target)
                if not os.path.exists(build_target):
                    os.makedirs(build_target)
                files_merged = []
                for file in files:
                    if file.endswith(".in"):
                        file_merged = os.path.basename(file[:-3])
                    else:
                        file_merged = os.path.basename(file)
                    file_merged = os.path.join(build_target, file_merged)
                    cmd = ["intltool-merge", switch, self.po_dir, file, file_merged]
                    mtime_merged = os.path.exists(file_merged) and \
                                   os.path.getmtime(file_merged) or 0
                    mtime_file = os.path.getmtime(file)
                    if mtime_merged < max_po_mtime or mtime_merged < mtime_file:
                        # Only build if output is older than input (.po,.in)
                        self.spawn(cmd)
                    files_merged.append(file_merged)
                data_files.append((target, files_merged))


class build_icons(Command):
    """
    Automatically include icon files without having to list them individually

    Based on DistutilsExtra code.
    """

    description = "build icons"
    user_options= [('icon-dir=', 'i', 'icon directory of the source tree')]

    def initialize_options(self):
        self.icon_dir = None

    def finalize_options(self):
        if self.icon_dir is None:
            self.icon_dir = os.path.join("data", "icons")

    def run(self):
        data_files = self.distribution.data_files

        for size in glob(os.path.join(self.icon_dir, "*")):
            for category in glob(os.path.join(size, "*")):
                icons = []
                for icon in glob(os.path.join(category,"*")):
                    if not os.path.islink(icon):
                        icons.append(icon)
                if icons:
                    data_files.append(
                        (
                            "share/icons/hicolor/%s/%s" % (
                                os.path.basename(size), os.path.basename(category)
                            ), icons
                        )
                    )


class build_man_page(Command):
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
            self.spawn(
                [
                    'pod2man', '--section=1', '--release={}'.format(about["__version__"]),
                    "--center=General Commands Manual", '--name="{}"'.format(name),
                    pod_file, build_path
                ]
            )


class raphodo_build(build):
    sub_commands = build.sub_commands + [
        ('build_man_page', None), ('build_icons', None), ('build_translations', None),
    ]

    def run(self):
        if not os.path.isdir('build'):
            os.mkdir('build')
        build.run(self)


class raphodo_sdist(sdist):
    def run(self):
        self.run_command('build_man_page')
        self.run_command('build_icons')
        self.run_command('build_translations')
        sdist.run(self)


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

    install_requires=[
        'gphoto2',
        'pyzmq',
        'psutil',
        'pyxdg',
        'arrow',
        'python-dateutil',
        'colour',
        'rawkit',
        'easygui',
        'pymediainfo',
        'sortedcontainers',
        'tornado',
        'scandir;python_version<"3.5"',
        'typing;python_version<"3.5"',
        'PyGObject',
        'PyQt5',
        'babel',
    ],
    extras_require={
        'color_ouput': ['colorlog',],
        'progress_bar': ['pyprind',]
    },
    include_package_data=False,
    data_files=[
        (
            'share/man/man1', [
                'build/doc/rapid-photo-downloader.1', 'build/doc/analyze-pv-structure.1'
            ]
        ),
        (
            'share/applications', [
                'build/share/applications/net.damonlynch.rapid_photo_downloader.desktop'
            ]
        ),
        (
            'share/solid/actions', [
                'build/share/solid/actions/net.damonlynch.rapid_photo_downloader.desktop'
            ],
        ),
        (
            'share/metainfo', [
                'build/share/metainfo/net.damonlynch.rapid_photo_downloader.metainfo.xml'
            ]
        )
    ],
    packages=['raphodo'],
    python_requires='>=3.4.*, <4',
    entry_points={
        'gui_scripts': ['rapid-photo-downloader=raphodo.rapid:main'],
        'console_scripts': ['analyze-pv-structure=raphodo.analyzephotos:main']
    },
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: X11 Applications :: Qt',
        'Operating System :: POSIX :: Linux',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Topic :: Multimedia :: Graphics',
        'Topic :: Multimedia :: Video'
    ],
    keywords='photo video download ingest import camera phone backup rename photography '
             'photographer transfer copy raw cr2 cr3 nef arw dng',
    project_urls={
        'Bug Reports': 'https://bugs.launchpad.net/rapid',
        'Source': 'https://code.launchpad.net/~dlynch3/rapid/zeromq_pyqt',
    },
    cmdclass={
        'build_man_page': build_man_page,
        'build_icons': build_icons,
        'build_translations': build_translations,
        'build': raphodo_build,
        'sdist': raphodo_sdist,
    }
)
