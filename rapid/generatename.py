#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2011 Damon Lynch <damonlynch@gmail.com>

### This program is free software; you can redistribute it and/or modify
### it under the terms of the GNU General Public License as published by
### the Free Software Foundation; either version 2 of the License, or
### (at your option) any later version.

### This program is distributed in the hope that it will be useful,
### but WITHOUT ANY WARRANTY; without even the implied warranty of
### MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
### GNU General Public License for more details.

### You should have received a copy of the GNU General Public License
### along with this program; if not, write to the Free Software
### Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

"""
Generates names for files and folders.

Runs a daemon process.
"""

import os

import gio, glib
import multiprocessing
import logging
logger = multiprocessing.get_logger()


import rpdmultiprocessing as rpdmp

def generate_folder(rpd_file):
    return '/home/damon/photos'

class GenerateName(multiprocessing.Process):
    def __init__(self, results_pipe, task_queue, run_event):
        multiprocessing.Process.__init__(self)
        self.daemon = True
        self.results_pipe = results_pipe
        self.run_event = run_event
        self.task_queue = task_queue
        
    def run(self):
        while True:
            task = self.task_queue.get()
            full_file_name, file_type, rename = task
            generated_folder = '/home/damon/photos'
            generated_name = 'sample.cr2'
            self.results_pipe.send((generated_folder, generated_name))
