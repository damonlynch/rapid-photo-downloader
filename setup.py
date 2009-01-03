#!/usr/bin/env python
# -*- coding: latin1 -*-

from distutils.core import setup

package_data={'rapid': ['glade3/rapid.glade',  'glade3/rapid-photo-downloader-icon.png',]}

setup(name='rapid',
      version='0.0.3',
      description='Rapid Photo Downloader for Linux',
      license='GPL',
      author='Damon Lynch',
      author_email='damonlynch@gmail.com',
      url='https://launchpad.net/rapid',
      packages = ['rapid'], 
      package_data=package_data, 
      scripts=['rapid-photo-downloader']
     )
