#!/usr/bin/env python
# -*- coding: latin1 -*-

from distutils.core import setup
from rapid.rapid import __version__ as version

package_data={'rapid': ['glade3/rapid.glade',  'glade3/rapid-photo-downloader-icon.png',]}

setup(name='rapid',
      version=version,
      description='Rapid Photo Downloader for Linux',
      license='GPL',
      author='Damon Lynch',
      author_email='damonlynch@gmail.com',
      url='http://www.damonlynch.net/rapid',
      packages = ['rapid'], 
      package_data=package_data, 
      scripts=['rapid-photo-downloader']
     )
