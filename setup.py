#!/usr/bin/env python
# -*- coding: latin1 -*-

from distutils.core import setup
from rapid.config import version
import glob

package_data={'rapid': ['glade3/rapid.glade', 'glade3/rapid-photo-downloader-about.png']}

setup(name='rapid-photo-downloader',
      version=version,
      description='Rapid Photo Downloader for Linux',
      license='GPL',
      author='Damon Lynch',
      author_email='damonlynch@gmail.com',
      maintainer='Damon Lynch',
      url='http://www.damonlynch.net/rapid',
      long_description=
"""Rapid Photo Downloader is written by a photographer for
professional and amateur photographers, designed for use
on the GNOME 2 Desktop. It can download photos from multiple
memory cards and Portable Storage Devices simultaneously. It
provides many options for subfolder creation, image renaming
and backup.""",
      packages = ['rapid'], 
      package_data=package_data, 
      scripts=['rapid-photo-downloader'],
      platforms=['linux'],
      data_files=[
                  ('share/applications', ['data/rapid-photo-downloader.desktop']),
                  ('share/pixmaps', ['data/icons/48x48/apps/rapid-photo-downloader.png', 'data/icons/rapid-photo-downloader.xpm']),
                  ('share/icons/hicolor/scalable/apps', glob.glob('data/icons/scalable/apps/*.svg')),
                  ('share/icons/hicolor/16x16/apps', glob.glob('data/icons/16x16/apps/*.png')),
                  ('share/icons/hicolor/22x22/apps', glob.glob('data/icons/22x22/apps/*.png')),
                  ('share/icons/hicolor/24x24/apps', glob.glob('data/icons/24x24/apps/*.png')),
                  ('share/icons/hicolor/48x48/apps', glob.glob('data/icons/48x48/apps/*.png')),
                 ],      
     )
