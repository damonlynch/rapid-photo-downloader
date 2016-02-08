__author__ = 'Damon Lynch'

from setuptools import setup

import rapid.constants

setup(
    name = "rapid-photo-downloader",
    version = rapid.constants.version,
    author='Damon Lynch',
    author_email='damonlynch@gmail.com',
    license="GPL",
    url='http://www.damonlynch.net/rapid',
    description='Rapid Photo Downloader for Linux',
    long_description=
"""Rapid Photo Downloader is written by a photographer for professional and
amateur photographers. It can  download photos and videos from multiple
cameras and other devices simultaneously. It provides many flexible,
user-defined options for subfolder creation, photo and video renaming,
and backup.
""",
    packages = ['rapid'],
    entry_points={
        'gui_scripts': [
            'rapid-photo-downloader=rapid.rapid:main',
        ]
    }
)
