#!/usr/bin/env python3

# Copyright (C) 2017 Damon Lynch <damonlynch@gmail.com>

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
# along with Rapid Photo Downloader. If not,
# see <http://www.gnu.org/licenses/>.

"""
Create a data blob of locale mo files and insert it into install.py
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2017, Damon Lynch"


from glob import glob
import os
import subprocess
import tempfile
import shutil
import base64

po_dir = '../po'
domain = 'rapid-photo-downloader'
install_script = '../install.py'
install_backup = '../install.bak'
line_length=100

temp_dir = tempfile.mkdtemp()

# create the .mo files in the temporary directory using the same subfolder
# structure gettext() expects
for po_file in glob("{}/*.po".format(po_dir)):
    lang = os.path.basename(po_file[:-3])
    if not lang.startswith('en'):
        mo_dir = os.path.join(temp_dir, "locale", lang, "LC_MESSAGES")
        mo_file = os.path.join(mo_dir, "%s.mo" % domain)
        if not os.path.exists(mo_dir):
            os.makedirs(mo_dir)
        cmd = ["msgfmt", po_file, "-o", mo_file]
        subprocess.check_call(cmd)

# base name for the zip file
zip_base = os.path.join(temp_dir, 'mo_files')
# add the extension
zip = zip_base + '.zip'

# create the zip file, with the zip's root directory being 'locale'
shutil.make_archive(zip_base, 'zip', temp_dir, 'locale')

# turn the zip file into UTF-8 text
with open(zip, 'rb') as myzip:
    zip_text = base64.b85encode(myzip.read()).decode()

# we're done with the temp dir
shutil.rmtree(temp_dir)

# grab install.py script
with open(install_script, 'rt') as install_py:
    code = install_py.read()

# locate the binary blob contents
mo_files_start = 'MO_FILES_ZIP=b"""'
mo_files_end = '"""'

start = code.find(mo_files_start) + len(mo_files_start)
end = code.find(mo_files_end, start)

# add the blob, breaking up each line at 100 characters length
blocks = (zip_text[s:s + line_length] for s in range(0, len(zip_text), line_length))
# insert the blob
new_code = "{}\n{}\n{}".format(code[:start], '\n'.join(blocks), code[end:])

# backup the existing script
shutil.copy2(install_script, install_backup)

# write out the updated script
with open(install_script, 'wt') as install_py:
    install_py.write(new_code)
