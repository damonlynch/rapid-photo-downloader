#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2010 Damon Lynch <damonlynch@gmail.com>

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
Adds a filmstrip to the left and right of a file
"""

import gtk


xpm_data = [
"12 10 27 1",
"   c #000000",
".  c #232323",
"+  c #7A7A7A",
"@  c #838383",
"#  c #8C8C8C",
"$  c #909090",
"%  c #8E8E8E",
"&  c #525252",
"*  c #6E6E6E",
"=  c #939393",
"-  c #A3A3A3",
";  c #ABABAB",
">  c #A8A8A8",
",  c #9B9B9B",
"'  c #727272",
")  c #A4A4A4",
"!  c #BBBBBB",
"~  c #C4C4C4",
"{  c #C1C1C1",
"]  c #AFAFAF",
"^  c #3E3E3E",
"/  c #A6A6A6",
"(  c #BEBEBE",
"_  c #C8C8C8",
":  c #070707",
"<  c #090909",
"[  c #0A0A0A",
"            ",
"            ",
"            ",
"    .+@#$%& ",
"    *@=-;>, ",
"    '%)!~{] ",
"    ^$/(_~% ",
"     :<[[[  ",
"            ",
"            "]


def add_filmstrip(pixbuf):
    """
    Adds a filmstrip to the left and right of a pixbuf
    
    Returns a pixbuf
    
    """    
    filmstrip = gtk.gdk.pixbuf_new_from_xpm_data(xpm_data)
    filmstrip_width = filmstrip.get_width()
    filmstrip_height = filmstrip.get_height()
    filmstrip_right = filmstrip.flip(True)


    original = pixbuf
    original_height = original.get_height()
    thumbnail_width = original.get_width() + filmstrip_width * 2
    thumbnail_right_col = original.get_width() + filmstrip_width

    thumbnail = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False, 8, thumbnail_width, original.get_height())

    #add filmstrips to left and right
    for i in range(original_height / filmstrip_height):
        filmstrip.copy_area(0, 0, filmstrip_width, filmstrip_height, thumbnail, 0, i * filmstrip_height)
        filmstrip_right.copy_area(0, 0, filmstrip_width, filmstrip_height, thumbnail, thumbnail_right_col, i * filmstrip_height)
        
    #now do the remainder, at the bottom
    remaining_height = original_height % filmstrip_height
    if remaining_height:
        filmstrip.copy_area(0, 0, filmstrip_width, remaining_height, thumbnail, 0, original_height-remaining_height)
        filmstrip_right.copy_area(0, 0, filmstrip_width, remaining_height, thumbnail, thumbnail_right_col, original_height-remaining_height)

    if original.get_has_alpha():
        thumbnail = thumbnail.add_alpha(False, 0,0,0)
    #copy in the original image
    original.copy_area(0, 0, original.get_width(), original_height, thumbnail, filmstrip_width, 0)
    
    return thumbnail

    
if __name__ == '__main__':
    import sys
    
    
    if (len(sys.argv) != 2):
        print 'Usage: ' + sys.argv[0] + ' path/to/photo/image'

    else:
        p = gtk.gdk.pixbuf_new_from_file(sys.argv[1])
        p2 = add_filmstrip(p)
        p2.save('testing.png', 'png')
