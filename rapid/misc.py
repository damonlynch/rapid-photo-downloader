#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>

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

# modified by Damon Lynch 2009 to remove default bold formatting and alignment
"""Module of commonly used helper classes and functions

"""

import gtk

def run_dialog( text, secondarytext=None,  parent=None, messagetype=gtk.MESSAGE_WARNING, buttonstype=gtk.BUTTONS_OK, extrabuttons=[]):
    """Run a dialog with text 'text'.
       Extra buttons are passed as tuples of (button label, response id).
    """
    d = gtk.MessageDialog(None,
        gtk.DIALOG_DESTROY_WITH_PARENT,
        messagetype,
        buttonstype,
        text
        )
    if parent:
        d.set_transient_for(parent.widget.get_toplevel())
    for b,rid in extrabuttons:
        d.add_button(b,rid)
    d.vbox.set_spacing(12)
    d.format_secondary_text(secondarytext)
    ret = d.run()
    d.destroy()
    return ret
