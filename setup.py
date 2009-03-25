#!/usr/bin/env python
# -*- coding: latin1 -*-

from distutils.core import setup
from rapid.rapid import __version__ as version

package_data={'rapid': ['glade3/rapid.glade',  'glade3/rapid-photo-downloader-icon.png',]}

setup(name='rapid-photo-downloader',
      version=version,
      description='Rapid Photo Downloader for Linux',
      license='GPL',
      author='Damon Lynch',
      author_email='damonlynch@gmail.com',
      maintainer='Damon Lynch',
      url='http://www.damonlynch.net/rapid',
      long_description='Rapid Photo Downloader is written by a photographer for professional and amateur photographers, designed for use on the GNOME 2 Desktop. It can download photos from multiple memory cards and Portable Storage Devices simultaneously. It provides a variety of options for subfolder creation, image renaming and backup.',
      packages = ['rapid'], 
      package_data=package_data, 
      scripts=['rapid-photo-downloader'],
      platforms=['linux'],
     )
