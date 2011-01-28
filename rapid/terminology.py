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

from common import Configi18n
global _
_ = Configi18n._

def file_types_by_number(noImages, noVideos):
    """ 
    returns a string to be displayed to the user that can be used
    to show if a value refers to photos or videos or both, or just one
    of each
    """
    if (noVideos > 0) and (noImages > 0):
        v = _('photos and videos')
    elif (noVideos == 0) and (noImages == 0):
        v = _('photos or videos')
    elif noVideos > 0:
        if noVideos > 1:
            v = _('videos')
        else:
            v = _('video')
    else:
        if noImages > 1:
            v = _('photos')
        else:
            v = _('photo')
    return v
