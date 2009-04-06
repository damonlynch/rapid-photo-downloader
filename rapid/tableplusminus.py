#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2007, 2008, 2009 Damon Lynch <damonlynch@gmail.com>

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
            self.extraCols = 2 # representing minus and plus buttons
        else:            
            gtk.Table.__init__(self, rows, columns + 3, homogeneous)
            self.extraCols = 3 # representing minus and plus buttons, and info label

        # no of columns NOT including the + and - buttons
        self.pm_noColumns = columns  
        # how many rows there are in the gtk.Table
        self.pm_noRows = rows
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

    def _setMinusButtonSensitivity(self):
        button = self.pm_rows[0][self.pm_noColumns]
        if len(self.pm_rows) == 1:
            button.set_sensitive(False)
        else:
            button.set_sensitive(True)

    def _createMinusPlusButtons(self, rowPosition):
        plus_button = gtk.Button()
        plus_button.set_image(gtk.image_new_from_stock(gtk.STOCK_ADD, gtk.ICON_SIZE_MENU))
        self._createCallback(plus_button, rowPosition, 'clicked', self.on_plus_button_clicked)
        minus_button = gtk.Button()
        minus_button.set_image(gtk.image_new_from_stock(gtk.STOCK_REMOVE, gtk.ICON_SIZE_MENU))
        self._createCallback(minus_button, rowPosition, 'clicked', self.on_minus_button_clicked)

        return minus_button, plus_button

            
        
    def append(self, row):
        self.insertAfter(len(self.pm_rows)-1, row)


    def _getMinusAndPlusButtonsForRow(self, rowPosition):
        """
        Return as a tuple minus and plus buttons for the row specified by rowPosition
        """
        return (self.pm_rows[rowPosition][self.pm_noColumns], self.pm_rows[rowPosition][self.pm_noColumns+1])

    def removeRow(self, rowPosition):
        # remove widgets from table
        for col in range(self.pm_noColumns + self.extraCols):
            widget = self.pm_rows[rowPosition][col]
            if widget:
                self.remove(widget)
                if self.pm_callbacks.has_key(widget):
                    widget.disconnect(self.pm_callbacks[widget])
                    del self.pm_callbacks[widget]


        # reposition existing rows in gtk.Table
        self._moveRows(-1, rowPosition + 1)
        # remove row from list of rows
        del self.pm_rows[rowPosition]

        self._setMinusButtonSensitivity()
        self.pm_noRows -= 1
        self.resize(self.pm_noRows, self.pm_noColumns + self.extraCols)
        self._printDebugInfo()


    def _createCallback(self, widget, rowPosition, callbackType = None, callbackMethod=None):
        if callbackType:
            self.pm_callbacks[widget] = widget.connect(callbackType, callbackMethod, rowPosition)
        else:
            name = widget.get_name()
            if name == 'GtkComboBox':
                self.pm_callbacks[widget] = widget.connect("changed", self.on_combobox_changed, rowPosition)
            elif name == 'GtkEntry':
                self.pm_callbacks[widget] = widget.connect("changed", self.on_entry_changed, rowPosition)
            
    
    def _moveRows(self, adjustment, startRow, endRow = -1):
        """
        Moves gtk.Table rows up or down according to adjustment (which MUST be -1 or 1).

        Starts at row startRow and ends at row endRow.  If endRow == -1, then goes to last row in table.
        Readjusts callbacks.
        """
        if endRow == -1:
            endRow = len(self.pm_rows)
        for r in range(startRow, endRow):
            if self.debug:
                print "Row %s becomes row %s" % (self.pm_rows[r][self.pm_noColumns + 2].get_label(), r + adjustment)
                self.pm_rows[r][self.pm_noColumns + 2].set_label(str(r + adjustment))

            for col in range(self.pm_noColumns + self.extraCols):
                widget = self.pm_rows[r][col]
                if widget:
                    self.remove(widget)
                    widget.disconnect(self.pm_callbacks[widget])
                    self.attach(widget, col, col+1, r + adjustment, r  + adjustment + 1)
                    if col == self.pm_noColumns:
                        self._createCallback(widget, r + adjustment, 'clicked', self.on_minus_button_clicked)
                    elif col == self.pm_noColumns + 1:
                        self._createCallback(widget, r + adjustment, 'clicked', self.on_plus_button_clicked)
                    else:
                        self._createCallback(widget, r + adjustment)


    def _printDebugInfo(self):
        if self.debug:
            print "\nRows in internal list: %s\nTable rows: %s" % \
                       (len(self.pm_rows), self.pm_noRows)

            if len(self.pm_rows) <> self.pm_noRows:
                print "|\n\\\n --> Unequal no. of rows"



    def attach(self, child, left_attach, right_attach, top_attach, bottom_attach, xoptions=gtk.EXPAND|gtk.FILL, 
                        yoptions=gtk.SHRINK, xpadding=0, ypadding=0):
        """
        Override base class attach method, to allow automatic shrinking of minus and plus buttons
        """
        if left_attach >= self.pm_noColumns and left_attach <= self.pm_noColumns + 1:
            # since we are adding plus or minus button, shrink the button
            gtk.Table.attach(self, child, left_attach, right_attach, top_attach, bottom_attach, gtk.SHRINK, gtk.SHRINK, xpadding, ypadding)
        else:
            gtk.Table.attach(self, child, left_attach, right_attach, top_attach, bottom_attach, xoptions, yoptions, xpadding, ypadding)


    def insertAfter(self, rowPosition, row):
        """
        Inserts row into the table at row following rowPosition
        """


        #is table big enough?
        self.checkTableRowsAndAdjust()

        #move (reattach) other widgets & readjust connect
        self._moveRows(1, rowPosition + 1)

        # insert row
        for col in range(self.pm_noColumns):
            widget = row[col]
            if widget:
                self._createCallback(widget, rowPosition+1)
                self.attach(widget, col, col+1, rowPosition+1, rowPosition+2)
                
        minus_button, plus_button = self._createMinusPlusButtons(rowPosition+1)

        row.append(minus_button)
        row.append(plus_button)
        self.attach(minus_button, self.pm_noColumns, self.pm_noColumns+1, rowPosition+1, rowPosition+2)
        self.attach(plus_button, self.pm_noColumns+1, self.pm_noColumns+2, rowPosition+1, rowPosition+2)

        if self.debug:
            label = gtk.Label(str(rowPosition+1))
            self.attach(label, self.pm_noColumns+2, self.pm_noColumns+3, rowPosition+1, rowPosition+2)
            row.append(label)

        
        for widget in row:
            if widget:
                widget.show()

        #adjust internal reference table

        self.pm_rows.insert(rowPosition + 1, row)

        self._setMinusButtonSensitivity()

        self._printDebugInfo()

    def checkTableRowsAndAdjust(self, noRowsToAdd=1, adjustRows=True):
        noRowsOk = True
        if len(self.pm_rows) + noRowsToAdd > self.pm_noRows:
            if adjustRows:
                extraRowsToAdd = len(self.pm_rows) + noRowsToAdd - self.pm_noRows
                self.pm_noRows += extraRowsToAdd
                self.resize(self.pm_noRows, self.pm_noColumns + self.extraCols)
            else:
                noRowsOk = False
        return noRowsOk

    def getDefaultRow(self):
        """
        Returns a list of default widgets to insert as a row into the table.

        Expected to be implemented in derived class.
        """
    
        return [None] * self.pm_noColumns

    def on_combobox_changed(self, widget, rowPosition):
        """
        Callback for combobox that is expected to be implemented in derived class
        """
        pass
        
    def on_entry_changed(self, widget, rowPosition):
        """
        Callback for entry that is expected to be implemented in derived class
        """
        pass

    def _debugButtonPressed(self, buttonText, rowPosition):
        if self.debug:
            t = datetime.datetime.now().strftime("%H:%M:%S")
            print "\n****\n%s\n\n%s clicked at %s" %(t, buttonText, rowPosition)

    def on_minus_button_clicked(self, widget, rowPosition):
        self._debugButtonPressed("Minus", rowPosition)
        self.removeRow(rowPosition)
        self.on_rowDeleted(rowPosition)        

    def on_plus_button_clicked(self, widget, rowPosition):
        self._debugButtonPressed("Plus", rowPosition)
        self.insertAfter(rowPosition, self.getDefaultRow())
        self.on_rowAdded(rowPosition)
        
    def on_rowAdded(self, rowPosition):
        """
        Expected to be implemented in derived class
        """
        pass

    def on_rowDeleted(self, rowPosition):
        """
        Expected to be implemented in derived class
        """
        pass
        
