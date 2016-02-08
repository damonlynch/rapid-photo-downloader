#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2007-2012 Damon Lynch <damonlynch@gmail.com>

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
### Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301
### USA

# import gtk.gdk as gdk
import sys
try: 
    import pygtk 
    pygtk.require("2.0") 
except: 
    pass 
try: 
    import gtk 
except: 
    sys.exit(1)
    
import higdefaults as hd

class TablePlusMinus(gtk.Table): 
    """
    A regular gtk table which allows users to add and delete rows to the table.
    
    Users add and delete rows by using plus and minus buttons.
    The buttons (minus first) are in the two rightmost colums.
    The user can never delete a table so it has no rows.
    """
    
    debug = False # if True, then debugging info for the developer is displayed
    def __init__(self, rows=1, columns=1, homogeneous=False):
        if not self.debug:
            gtk.Table.__init__(self, rows, columns + 2, homogeneous)
            self.extra_cols = 2 # representing minus and plus buttons
        else:            
            gtk.Table.__init__(self, rows, columns + 3, homogeneous)
            self.extra_cols = 3 # representing minus and plus buttons, and info label

        # no of columns NOT including the + and - buttons
        self.pm_no_columns = columns  
        # how many rows there are in the gtk.Table
        self.pm_no_rows = rows
        # list of widgets in the gtk.Table
        self.pm_rows = []
        # dict of callback ids for minus and plus buttons
        self.pm_callbacks = {}

        #spacing of controls
        for i in range(columns-1):
            self.set_col_spacing(i, hd.CONTROL_IN_TABLE_SPACE)
        self.set_col_spacing(columns-1, hd.CONTROL_IN_TABLE_SPACE*2)
        self.set_col_spacing(columns, hd.CONTROL_IN_TABLE_SPACE)
        if self.debug:
            self.set_col_spacing(columns+1, hd.CONTROL_IN_TABLE_SPACE)
        self.set_row_spacings(hd.CONTROL_IN_TABLE_SPACE)

    def _set_minus_button_sensitivity(self):
        button = self.pm_rows[0][self.pm_no_columns]
        if len(self.pm_rows) == 1:
            button.set_sensitive(False)
        else:
            button.set_sensitive(True)

    def _create_minus_plus_buttons(self, row_position):
        plus_button = gtk.Button()
        plus_button.set_image(gtk.image_new_from_stock(gtk.STOCK_ADD, gtk.ICON_SIZE_MENU))
        self._create_callback(plus_button, row_position, 'clicked', self.on_plus_button_clicked)
        minus_button = gtk.Button()
        minus_button.set_image(gtk.image_new_from_stock(gtk.STOCK_REMOVE, gtk.ICON_SIZE_MENU))
        self._create_callback(minus_button, row_position, 'clicked', self.on_minus_button_clicked)

        return minus_button, plus_button

            
        
    def append(self, row):
        self.insert_after(len(self.pm_rows)-1, row)


    def _get_minus_and_plus_buttons_for_row(self, row_position):
        """
        Return as a tuple minus and plus buttons for the row specified by row_position
        """
        return (self.pm_rows[row_position][self.pm_no_columns], self.pm_rows[row_position][self.pm_no_columns+1])

    def remove_row(self, row_position):
        # remove widgets from table
        for col in range(self.pm_no_columns + self.extra_cols):
            widget = self.pm_rows[row_position][col]
            if widget:
                self.remove(widget)
                if self.pm_callbacks.has_key(widget):
                    widget.disconnect(self.pm_callbacks[widget])
                    del self.pm_callbacks[widget]


        # reposition existing rows in gtk.Table
        self._move_rows(-1, row_position + 1)
        # remove row from list of rows
        del self.pm_rows[row_position]

        self._set_minus_button_sensitivity()
        self.pm_no_rows -= 1
        self.resize(self.pm_no_rows, self.pm_no_columns + self.extra_cols)
        self._print_debug_info()


    def _create_callback(self, widget, row_position, callback_type = None, callbackMethod=None):
        if callback_type:
            self.pm_callbacks[widget] = widget.connect(callback_type, callbackMethod, row_position)
        else:
            name = widget.get_name()
            if name == 'GtkComboBox':
                self.pm_callbacks[widget] = widget.connect("changed", self.on_combobox_changed, row_position)
            elif name == 'GtkEntry':
                self.pm_callbacks[widget] = widget.connect("changed", self.on_entry_changed, row_position)
            
    
    def _move_rows(self, adjustment, start_row, end_row = -1):
        """
        Moves gtk.Table rows up or down according to adjustment (which MUST be -1 or 1).

        Starts at row start_row and ends at row end_row.  If end_row == -1, then goes to last row in table.
        Readjusts callbacks.
        """
        if end_row == -1:
            end_row = len(self.pm_rows)
        for r in range(start_row, end_row):
            if self.debug:
                print "Row %s becomes row %s" % (self.pm_rows[r][self.pm_no_columns + 2].get_label(), r + adjustment)
                self.pm_rows[r][self.pm_no_columns + 2].set_label(str(r + adjustment))

            for col in range(self.pm_no_columns + self.extra_cols):
                widget = self.pm_rows[r][col]
                if widget:
                    self.remove(widget)
                    widget.disconnect(self.pm_callbacks[widget])
                    self.attach(widget, col, col+1, r + adjustment, r  + adjustment + 1)
                    if col == self.pm_no_columns:
                        self._create_callback(widget, r + adjustment, 'clicked', self.on_minus_button_clicked)
                    elif col == self.pm_no_columns + 1:
                        self._create_callback(widget, r + adjustment, 'clicked', self.on_plus_button_clicked)
                    else:
                        self._create_callback(widget, r + adjustment)


    def _print_debug_info(self):
        if self.debug:
            print "\nRows in internal list: %s\nTable rows: %s" % \
                       (len(self.pm_rows), self.pm_no_rows)

            if len(self.pm_rows) <> self.pm_no_rows:
                print "|\n\\\n --> Unequal no. of rows"



    def attach(self, child, left_attach, right_attach, top_attach, bottom_attach, xoptions=gtk.EXPAND|gtk.FILL, 
                        yoptions=gtk.SHRINK, xpadding=0, ypadding=0):
        """
        Override base class attach method, to allow automatic shrinking of minus and plus buttons
        """
        if left_attach >= self.pm_no_columns and left_attach <= self.pm_no_columns + 1:
            # since we are adding plus or minus button, shrink the button
            gtk.Table.attach(self, child, left_attach, right_attach, top_attach, bottom_attach, gtk.SHRINK, gtk.SHRINK, xpadding, ypadding)
        else:
            gtk.Table.attach(self, child, left_attach, right_attach, top_attach, bottom_attach, xoptions, yoptions, xpadding, ypadding)


    def insert_after(self, row_position, row):
        """
        Inserts row into the table at row following row_position
        """


        #is table big enough?
        self.check_table_rows_and_adjust()

        #move (reattach) other widgets & readjust connect
        self._move_rows(1, row_position + 1)

        # insert row
        for col in range(self.pm_no_columns):
            widget = row[col]
            if widget:
                self._create_callback(widget, row_position+1)
                self.attach(widget, col, col+1, row_position+1, row_position+2)
                
        minus_button, plus_button = self._create_minus_plus_buttons(row_position+1)

        row.append(minus_button)
        row.append(plus_button)
        self.attach(minus_button, self.pm_no_columns, self.pm_no_columns+1, row_position+1, row_position+2)
        self.attach(plus_button, self.pm_no_columns+1, self.pm_no_columns+2, row_position+1, row_position+2)

        if self.debug:
            label = gtk.Label(str(row_position+1))
            self.attach(label, self.pm_no_columns+2, self.pm_no_columns+3, row_position+1, row_position+2)
            row.append(label)

        
        for widget in row:
            if widget:
                widget.show()

        #adjust internal reference table

        self.pm_rows.insert(row_position + 1, row)

        self._set_minus_button_sensitivity()

        self._print_debug_info()

    def check_table_rows_and_adjust(self, no_rows_to_add=1, adjust_rows=True):
        no_rows_ok = True
        if len(self.pm_rows) + no_rows_to_add > self.pm_no_rows:
            if adjust_rows:
                extra_rows_to_add = len(self.pm_rows) + no_rows_to_add - self.pm_no_rows
                self.pm_no_rows += extra_rows_to_add
                self.resize(self.pm_no_rows, self.pm_no_columns + self.extra_cols)
            else:
                no_rows_ok = False
        return no_rows_ok

    def get_default_row(self):
        """
        Returns a list of default widgets to insert as a row into the table.

        Expected to be implemented in derived class.
        """
    
        return [None] * self.pm_no_columns

    def on_combobox_changed(self, widget, row_position):
        """
        Callback for combobox that is expected to be implemented in derived class
        """
        pass
        
    def on_entry_changed(self, widget, row_position):
        """
        Callback for entry that is expected to be implemented in derived class
        """
        pass

    def _debug_button_pressed(self, buttonText, row_position):
        if self.debug:
            t = datetime.datetime.now().strftime("%H:%M:%S")
            print "\n****\n%s\n\n%s clicked at %s" %(t, buttonText, row_position)

    def on_minus_button_clicked(self, widget, row_position):
        self._debug_button_pressed("Minus", row_position)
        self.remove_row(row_position)
        self.on_row_deleted(row_position)        

    def on_plus_button_clicked(self, widget, row_position):
        self._debug_button_pressed("Plus", row_position)
        self.insert_after(row_position, self.get_default_row())
        self.on_row_added(row_position)
        
    def on_row_added(self, row_position):
        """
        Expected to be implemented in derived class
        """
        pass

    def on_row_deleted(self, row_position):
        """
        Expected to be implemented in derived class
        """
        pass
        
