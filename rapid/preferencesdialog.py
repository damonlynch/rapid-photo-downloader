#!/usr/bin/python
# -*- coding: latin1 -*-

### Copyright (C) 2007 - 2011 Damon Lynch <damonlynch@gmail.com>

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


import datetime

import gtk

import datetime
import multiprocessing
import logging
logger = multiprocessing.get_logger()

import ValidatedEntry
import misc

import config
import paths
import rpdfile
import higdefaults as hd
import metadataphoto
import metadatavideo
import tableplusminus as tpm

import utilities

import generatename as gn
from generatenameconfig import *
import problemnotification as pn

from prefsrapid import format_pref_list_for_pretty_print, DownloadsTodayTracker

from gettext import gettext as _

class PrefError(Exception):
    """ base class """
    def unpackList(self, l):
        """
        Make the preferences presentable to the user
        """
        
        s = ''
        for i in l:
            if i <> ORDER_KEY:
                s += "'" + i + "', "
        return s[:-2]

    def __str__(self): 
        return self.msg
        
class PrefKeyError(PrefError):
    def __init__(self, error):
        value = error[0]
        expectedValues = self.unpackList(error[1])
        self.msg = "Preference key '%(key)s' is invalid.\nExpected one of %(value)s" % {
                            'key': value, 'value': expectedValues}


class PrefValueInvalidError(PrefKeyError):
    def __init__(self, error):
        value = error[0]
        self.msg = "Preference value '%(value)s' is invalid" % {'value': value}
        
class PrefLengthError(PrefError):
    def __init__(self, error):
        self.msg = "These preferences are not well formed:" + "\n %s" % self.unpackList(error)
        
class PrefValueKeyComboError(PrefError):
    def __init__(self, error):    
        self.msg = error


def check_pref_valid(pref_defn, prefs, modulo=3):
    """
    Checks to see if prefs are valid according to definition.

    prefs is a list of preferences.
    pref_defn is a Dict specifying what is valid.
    modulo is how many list elements are equivalent to one line of preferences.

    Returns True if prefs match with pref_defn,
    else raises appropriate error.
    """

    if (len(prefs) % modulo <> 0) or not prefs:
        raise PrefLengthError(prefs)
    else:
        for i in range(0,  len(prefs),  modulo):
            _check_pref_valid(pref_defn, prefs[i:i+modulo])
               
    return True

def _check_pref_valid(pref_defn, prefs):

    key = prefs[0]
    value = prefs[1]


    if pref_defn.has_key(key):
        
        next_pref_defn = pref_defn[key]
        
        if value == None:
            # value should never be None, at any time
            raise PrefValueInvalidError((None, next_pref_defn))

        if next_pref_defn and not value:
            raise gn.PrefValueInvalidError((value, next_pref_defn))
                    
        if type(next_pref_defn) == type({}):
            return _check_pref_valid(next_pref_defn, prefs[1:])
        else:
            if type(next_pref_defn) == type([]):
                result = value in next_pref_defn
                if not result:
                    raise gn.PrefValueInvalidError((value, next_pref_defn))
                return True
            elif not next_pref_defn:
                return True
            else:
                result = next_pref_defn == value
                if not result:
                    raise gn.PrefKeyValue((value, next_pref_defn))
                return True
    else:
        raise PrefKeyError((key, pref_defn[ORDER_KEY]))


def filter_subfolder_prefs(pref_list):
    """
    Filters out extraneous preference choices
    """
    prefs_changed = False
    continue_check = True
    while continue_check and pref_list:
        continue_check = False
        if pref_list[0] == SEPARATOR:
            # subfolder preferences should not start with a /
            pref_list = pref_list[3:]
            prefs_changed = True
            continue_check = True
        elif pref_list[-3] == SEPARATOR:
            # subfolder preferences should not end with a /
            pref_list = pref_list[:-3]
            continue_check = True
            prefs_changed = True
        else:
            for i in range(0, len(pref_list) - 3, 3):
                if pref_list[i] == SEPARATOR and pref_list[i+3] == SEPARATOR:
                    # subfolder preferences should not contain two /s side by side
                    continue_check = True
                    prefs_changed = True
                    # note we are messing with the contents of the pref list,
                    # must exit loop and try again
                    pref_list = pref_list[:i] + pref_list[i+3:]
                    break
                    
    return (prefs_changed,  pref_list)

class Comboi18n(gtk.ComboBox):
    """ very simple i18n version of the venerable combo box 
    with one column displayed to the user.
    
    This combo box has two columns:
    1. the first contains the actual value and is invisible
    2. the second contains the translation of the first column, and this is what
        the users sees
    """
    def __init__(self):
        liststore = gtk.ListStore(str, str)
        gtk.ComboBox.__init__(self,  liststore)
        cell = gtk.CellRendererText()
        self.pack_start(cell,  True)
        self.add_attribute(cell, 'text', 1)
        # must name the combo box on pygtk used in Ubuntu 11.04, Fedora 15, etc.
        self.set_name('GtkComboBox') 
        
    def append_text(self,  text):
        model = self.get_model()
        model.append((text, _(text)))
        
    def get_active_text(self):
        model = self.get_model()
        active = self.get_active()
        if active < 0:
            return None
        return model[active][0] 
        
class PreferenceWidgets:
    
    def __init__(self, default_row, default_prefs, pref_defn_L0, pref_list):
        self.default_row = default_row
        self.default_prefs = default_prefs
        self.pref_defn_L0 = pref_defn_L0
        self.pref_list = pref_list
        
    def _create_combo(self, choices):
        combobox = Comboi18n()
        for text in choices:
            combobox.append_text(text)
        return combobox
        
    def get_default_row(self):
        """ 
        returns a list of default widgets
        """
        return self.get_widgets_based_on_user_selection(self.default_row)

    def _get_pref_widgets(self, pref_definition, prefs, widgets):
        key = prefs[0]
        value = prefs[1]
        
        # supply a default value if the user has not yet chosen a value!
        if not key:
            key = pref_definition[ORDER_KEY][0]
            
        if not key in pref_definition:
            raise gn.PrefKeyError((key, pref_definition.keys()))


        list0 = pref_definition[ORDER_KEY]

        # the first widget will always be a combo box
        widget0 = self._create_combo(list0)
        widget0.set_active(list0.index(key))
        
        widgets.append(widget0)
        
        if key == TEXT:
            widget1 = gtk.Entry()
            widget1.set_text(value)
            
            widgets.append(widget1)
            widgets.append(None)
            return
        elif key in [SEPARATOR, JOB_CODE]:
            widgets.append(None)
            widgets.append(None)
            return
        else:
            next_pref_definition = pref_definition[key]
            if type(next_pref_definition) == type({}):
                return self._get_pref_widgets(next_pref_definition, 
                                            prefs[1:], 
                                            widgets)
            else:
                if type(next_pref_definition) == type([]):
                    widget1 = self._create_combo(next_pref_definition)
                    if not value:
                        value = next_pref_definition[0]
                    try:
                        widget1.set_active(next_pref_definition.index(value))
                    except:
                        raise gn.PrefValueInvalidError((value, next_pref_definition))
                    
                    widgets.append(widget1)
                else:
                    widgets.append(None)
                    
    def _get_values_from_list(self):
        for i in range(0, len(self.pref_list), 3):
            yield (self.pref_list[i], self.pref_list[i+1], self.pref_list[i+2])                    
    
    def get_widgets_based_on_prefs(self):
        """ 
        Yields a list of widgets and their callbacks based on the users preferences.
       
        This list is equivalent to one row of preferences when presented to the 
        user in the Plus Minus Table.
        """
        
        for L0, L1, L2 in self._get_values_from_list():
            prefs = [L0, L1, L2]
            widgets = []
            self._get_pref_widgets(self.pref_defn_L0, prefs, widgets)
            yield widgets
        

    def get_widgets_based_on_user_selection(self, selection):
        """
        Returns a list of widgets and their callbacks based on what the user has selected.
        
        Selection is the values the user has chosen thus far in comboboxes.
        It determines the contents of the widgets returned.
        It should be a list of three values, with None for values not chosen.
        For values which are None, the first value in the preferences
        definition is chosen.
        
        """
        widgets = []
            
        self._get_pref_widgets(self.pref_defn_L0, selection, widgets)
        return widgets
        
    def check_prefs_for_validity(self):
        """
        Checks preferences validity
        """
        
        return check_pref_valid(self.pref_defn_L0, self.pref_list)        

class PhotoNamePrefs(PreferenceWidgets):
    def __init__(self, pref_list):
        PreferenceWidgets.__init__(self, 
            default_row = [FILENAME, NAME_EXTENSION, ORIGINAL_CASE],
            default_prefs = [FILENAME, NAME_EXTENSION, ORIGINAL_CASE],
            pref_defn_L0 = DICT_IMAGE_RENAME_L0,
            pref_list = pref_list)

class VideoNamePrefs(PreferenceWidgets):
    def __init__(self, pref_list):
        PreferenceWidgets.__init__(self,
            default_row = [FILENAME, NAME_EXTENSION, ORIGINAL_CASE],
            default_prefs = [FILENAME, NAME_EXTENSION, ORIGINAL_CASE],
            pref_defn_L0 = DICT_VIDEO_RENAME_L0,
            pref_list = pref_list)
                

class PhotoSubfolderPrefs(PreferenceWidgets):
    def __init__(self, pref_list):
        
        PreferenceWidgets.__init__(self,
            default_row = [DATE_TIME, IMAGE_DATE, LIST_DATE_TIME_L2[0]],
            default_prefs = DEFAULT_SUBFOLDER_PREFS,
            pref_defn_L0 = DICT_SUBFOLDER_L0,
            pref_list = pref_list)

    def filter_preferences(self):
        filtered,  pref_list = filter_subfolder_prefs(self.pref_list)
        if filtered:
            self.pref_list = pref_list
            
    def check_prefs_for_validity(self):
        """
        Checks subfolder preferences validity above and beyond image name checks.
        
        See parent method for full description.
        
        Subfolders have additional requirments to that of file names.
        """
        v = PreferenceWidgets.check_prefs_for_validity(self)
        if v:
            # peform additional checks:
            # 1. do not start with a separator
            # 2. do not end with a separator
            # 3. do not have two separators in a row
            # these three rules will ensure something else other than a 
            # separator is specified
            L1s = []
            for i in range(0, len(self.pref_list), 3):
                L1s.append(self.pref_list[i])

            if L1s[0] == SEPARATOR:
                raise PrefValueKeyComboError(_("Subfolder preferences should not start with a %s") % os.sep)
            elif L1s[-1] == SEPARATOR:
                raise PrefValueKeyComboError(_("Subfolder preferences should not end with a %s") % os.sep)
            else:
                for i in range(len(L1s) - 1):
                    if L1s[i] == SEPARATOR and L1s[i+1] == SEPARATOR:
                        raise PrefValueKeyComboError(_("Subfolder preferences should not contain two %s one after the other") % os.sep)
        return v

class VideoSubfolderPrefs(PhotoSubfolderPrefs):
    def __init__(self, pref_list):
        PreferenceWidgets.__init__(self, 
            default_row = [DATE_TIME, VIDEO_DATE, LIST_DATE_TIME_L2[0]],
            default_prefs = DEFAULT_VIDEO_SUBFOLDER_PREFS,
            pref_defn_L0 = DICT_VIDEO_SUBFOLDER_L0,
            pref_list = pref_list)

class RemoveAllJobCodeDialog(gtk.Dialog):
    def __init__(self, parent_window, post_choice_callback):
        gtk.Dialog.__init__(self, _('Remove all Job Codes?'), None,
                   gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                   (gtk.STOCK_NO, gtk.RESPONSE_CANCEL, 
                   gtk.STOCK_YES, gtk.RESPONSE_OK))
                        
        self.post_choice_callback = post_choice_callback        
        self.set_icon_from_file(paths.share_dir('glade3/rapid-photo-downloader.svg'))
        
        prompt_hbox = gtk.HBox()
        
        icontheme = gtk.icon_theme_get_default()
        icon = icontheme.load_icon('gtk-dialog-question', 36, gtk.ICON_LOOKUP_USE_BUILTIN)        
        if icon:
            image = gtk.Image()
            image.set_from_pixbuf(icon)
            prompt_hbox.pack_start(image, False, False, padding = 6)
            
        prompt_label = gtk.Label(_('Should all Job Codes be removed?'))
        prompt_label.set_line_wrap(True)
        prompt_hbox.pack_start(prompt_label, False, False, padding=6)
                    
        self.vbox.pack_start(prompt_hbox, padding=6)

        self.set_border_width(6)
        self.set_has_separator(False)   
        
        self.set_default_response(gtk.RESPONSE_OK)
      
       
        self.set_transient_for(parent_window)
        self.show_all()

        
        self.connect('response', self.on_response)
        
    def on_response(self,  device_dialog, response):
        user_selected = response == gtk.RESPONSE_OK
        self.post_choice_callback(self, user_selected)

class PhotoRenameTable(tpm.TablePlusMinus):

    def __init__(self, preferencesdialog, adjust_scroll_window):
  
        tpm.TablePlusMinus.__init__(self, 1, 3)
        self.preferencesdialog = preferencesdialog
        self.adjust_scroll_window = adjust_scroll_window
        if not hasattr(self, "error_title"):
            self.error_title = _("Error in Photo Rename preferences")
                    
        self.table_type = self.error_title[len("Error in "):]
        self.i = 0

        if adjust_scroll_window:
            self.scroll_bar = self.adjust_scroll_window.get_vscrollbar()
            #this next line does not work on early versions of pygtk :(
            self.scroll_bar.connect('visibility-notify-event', self.scrollbar_visibility_change)
            self.connect("size-request", self.size_adjustment)
            self.connect("add",  self.size_adjustment)
            self.connect("remove",  self.size_adjustment)

            # get scrollbar thickness from parent app scrollbar - very hackish, but what to do??
            self.bump = 16# self.preferencesdialog.parentApp.image_scrolledwindow.get_hscrollbar().allocation.height
            self.have_vertical_scrollbar = False


        self.get_preferencesdialog_prefs()
        self.setup_prefs_factory()
        
        try:
            self.prefs_factory.check_prefs_for_validity()
            
        except (PrefValueInvalidError, PrefLengthError, 
                PrefValueKeyComboError,  PrefKeyError),  e:

            logger.error(self.error_title)
            logger.error("Sorry, these preferences contain an error:")
            logger.error(format_pref_list_for_pretty_print(self.prefs_factory.pref_list))
            
            # the preferences were invalid
            # reset them to their default

            self.pref_list = self.prefs_factory.default_prefs
            self.setup_prefs_factory()
            self.update_parentapp_prefs()

            msg = "%s.\n" % e
            msg += "Resetting to default values."
            logger.error(msg)
            
            
            misc.run_dialog(self.error_title, msg, 
                preferencesdialog,
                gtk.MESSAGE_ERROR)
        
        for row in self.prefs_factory.get_widgets_based_on_prefs():
            self.append(row)
                      
    def update_preferences(self):
        pref_list = []
        for row in self.pm_rows:                
            for col in range(self.pm_no_columns):
                widget = row[col]
                if widget:
                    name = widget.get_name()
                    if name == 'GtkComboBox':
                        value = widget.get_active_text()
                    elif name == 'GtkEntry':
                        value = widget.get_text()
                    else:
                        logger.critical("Program error: Unknown preference widget!")
                        value = ''
                else:
                    value = ''
                pref_list.append(value)

        self.pref_list = pref_list
        self.update_parentapp_prefs()
        self.prefs_factory.pref_list = pref_list
        self.update_example()
            
    
    def scrollbar_visibility_change(self, widget, event):
        if event.state == gtk.gdk.VISIBILITY_UNOBSCURED:
            self.have_vertical_scrollbar = True
            self.adjust_scroll_window.set_size_request(self.adjust_scroll_window.allocation.width + self.bump, -1)

            
    def size_adjustment(self, widget, arg2):
        """
        Adjust scrolledwindow width in preferences dialog to reflect width of image rename table
        
        The algorithm is complicated by the need to take into account the presence of a vertical scrollbar,
        which might be added as the user adds more rows
        
        The pygtk code behaves inconsistently depending on the pygtk version
        """
        
        if self.adjust_scroll_window:
            self.have_vertical_scrollbar = self.scroll_bar.allocation.width > 1 or self.have_vertical_scrollbar
            if not self.have_vertical_scrollbar:
                if self.allocation.width > self.adjust_scroll_window.allocation.width:
                    self.adjust_scroll_window.set_size_request(self.allocation.width, -1)
            else:
                if self.allocation.width > self.adjust_scroll_window.allocation.width - self.bump:
                    self.adjust_scroll_window.set_size_request(self.allocation.width + self.bump, -1)
                    self.bump = 0
       
    def get_preferencesdialog_prefs(self):
        self.pref_list = self.preferencesdialog.prefs.image_rename
        
    
    def setup_prefs_factory(self):
        self.prefs_factory = PhotoNamePrefs(self.pref_list)
        
    def update_parentapp_prefs(self):
        self.preferencesdialog.prefs.image_rename = self.pref_list
        
    def update_example_job_code(self):
        job_code = self.preferencesdialog.prefs.get_sample_job_code()
        if not job_code:
            job_code = _('Job code')
        #~ self.prefs_factory.setJobCode(job_code)
        
    def update_example(self):
        self.preferencesdialog.update_photo_rename_example()
    
    def get_default_row(self):
        return self.prefs_factory.get_default_row()
        
    def on_combobox_changed(self, widget, row_position):
        
        for col in range(self.pm_no_columns):
            if self.pm_rows[row_position][col] == widget:
                break
        selection = []
        for i in range(col + 1):
            # ensure it is a combo box we are getting the value from
            w = self.pm_rows[row_position][i]
            name = w.get_name()
            if name == 'GtkComboBox':
                selection.append(w.get_active_text())
            else:
                selection.append(w.get_text())
                
        for i in range(col + 1, self.pm_no_columns):
            selection.append('')
            
        if col <> (self.pm_no_columns - 1):
            widgets = self.prefs_factory.get_widgets_based_on_user_selection(selection)
            
            for i in range(col + 1, self.pm_no_columns):
                old_widget = self.pm_rows[row_position][i]
                if old_widget:
                    self.remove(old_widget)
                    if old_widget in self.pm_callbacks:
                        del self.pm_callbacks[old_widget]
                new_widget = widgets[i]
                self.pm_rows[row_position][i] = new_widget
                if new_widget:
                    self._create_callback(new_widget, row_position)
                    self.attach(new_widget, i, i+1, row_position, row_position + 1)
                    new_widget.show()
        self.update_preferences()

        
    def on_entry_changed(self, widget, row_position):
        self.update_preferences()

    def on_row_added(self, row_position):
        """
        Update preferences, as a row has been added
        """
        self.update_preferences()
        
        # if this was the last row or 2nd to last row, and another has just been added, move vertical scrollbar down
        if row_position in range(self.pm_no_rows - 3,  self.pm_no_rows - 2):
            adjustment = self.preferencesdialog.rename_scrolledwindow.get_vadjustment()
            adjustment.set_value(adjustment.upper)
        

    def on_row_deleted(self, row_position):
        """
        Update preferences, as a row has been deleted
        """
        self.update_preferences()        

class VideoRenameTable(PhotoRenameTable):
    def __init__(self, preferencesdialog, adjust_scroll_window):    
        self.error_title = _("Error in Video Rename preferences")
        PhotoRenameTable.__init__(self, preferencesdialog, adjust_scroll_window)

    def get_preferencesdialog_prefs(self):
        self.pref_list = self.preferencesdialog.prefs.video_rename
    
    def setup_prefs_factory(self):
        self.prefs_factory = VideoNamePrefs(self.pref_list)
        
    def update_parentapp_prefs(self):
        self.preferencesdialog.prefs.video_rename = self.pref_list

    def update_example(self):
        self.preferencesdialog.update_video_rename_example()

class SubfolderTable(PhotoRenameTable):
    """
    Table to display photo download subfolder preferences as part of preferences
    dialog window.
    """
    def __init__(self, preferencesdialog, adjust_scroll_window):    
        self.error_title = _("Error in Photo Download Subfolders preferences")
        PhotoRenameTable.__init__(self, preferencesdialog, adjust_scroll_window)

    def get_preferencesdialog_prefs(self):
        self.pref_list = self.preferencesdialog.prefs.subfolder
    
    def setup_prefs_factory(self):
        self.prefs_factory = PhotoSubfolderPrefs(self.pref_list)
        
    def update_parentapp_prefs(self):
        self.preferencesdialog.prefs.subfolder = self.pref_list

    def update_example(self):
        self.preferencesdialog.update_photo_download_folder_example()
        
class VideoSubfolderTable(PhotoRenameTable):
    def __init__(self, preferencesdialog, adjust_scroll_window): 
        self.error_title = _("Error in Video Download Subfolders preferences")
        PhotoRenameTable.__init__(self, preferencesdialog, adjust_scroll_window)

    def get_preferencesdialog_prefs(self):
        self.pref_list = self.preferencesdialog.prefs.video_subfolder
    
    def setup_prefs_factory(self):
        self.prefs_factory = VideoSubfolderPrefs(self.pref_list)
        
    def update_parentapp_prefs(self):
        self.preferencesdialog.prefs.video_subfolder = self.pref_list

    def update_example(self):
        self.preferencesdialog.update_video_download_folder_example()        

class RemoveAllJobCodeDialog(gtk.Dialog):
    def __init__(self, parent_window, post_choice_callback):
        gtk.Dialog.__init__(self, _('Remove all Job Codes?'), None,
                   gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                   (gtk.STOCK_NO, gtk.RESPONSE_CANCEL, 
                   gtk.STOCK_YES, gtk.RESPONSE_OK))
                        
        self.post_choice_callback = post_choice_callback        
        self.set_icon_from_file(paths.share_dir('glade3/rapid-photo-downloader.svg'))
        
        prompt_hbox = gtk.HBox()
        
        icontheme = gtk.icon_theme_get_default()
        icon = icontheme.load_icon('gtk-dialog-question', 36, gtk.ICON_LOOKUP_USE_BUILTIN)        
        if icon:
            image = gtk.Image()
            image.set_from_pixbuf(icon)
            prompt_hbox.pack_start(image, False, False, padding = 6)
            
        prompt_label = gtk.Label(_('Should all Job Codes be removed?'))
        prompt_label.set_line_wrap(True)
        prompt_hbox.pack_start(prompt_label, False, False, padding=6)
                    
        self.vbox.pack_start(prompt_hbox, padding=6)

        self.set_border_width(6)
        self.set_has_separator(False)   
        
        self.set_default_response(gtk.RESPONSE_OK)
      
        self.set_transient_for(parent_window)
        self.show_all()

        self.connect('response', self.on_response)
        
    def on_response(self, device_dialog, response):
        user_selected = response == gtk.RESPONSE_OK
        self.post_choice_callback(self, user_selected)

class JobCodeDialog(gtk.Dialog):
    """ Dialog prompting for a job code"""
    
    def __init__(self, parent_window, job_codes,  default_job_code, post_job_code_entry_callback, entry_only):
        # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#jobcode
        gtk.Dialog.__init__(self,  _('Enter a Job Code'), None,
                   gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                   (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, 
                   gtk.STOCK_OK, gtk.RESPONSE_OK))
                        
        
        self.set_icon_from_file(paths.share_dir('glade3/rapid-photo-downloader.svg'))
        self.post_job_code_entry_callback = post_job_code_entry_callback
        
        self.combobox = gtk.combo_box_entry_new_text()
        for text in job_codes:
            self.combobox.append_text(text)
            
        self.job_code_hbox = gtk.HBox(homogeneous = False)
        
        if len(job_codes) and not entry_only:
            # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#jobcode
            task_label = gtk.Label(_('Enter a new Job Code, or select a previous one'))
        else:
            # Translators: for an explanation of what this means, see http://damonlynch.net/rapid/documentation/index.html#jobcode
            task_label = gtk.Label(_('Enter a new Job Code'))            
        task_label.set_line_wrap(True)
        task_hbox = gtk.HBox()
        task_hbox.pack_start(task_label, False, False, padding=6)

        label = gtk.Label(_('Job Code:'))
        self.job_code_hbox.pack_start(label, False, False, padding=6)
        self.job_code_hbox.pack_start(self.combobox, True, True, padding=6)
        
        self.set_border_width(6)
        self.set_has_separator(False)

        # make entry box have entry completion
        self.entry = self.combobox.child
        
        completion = gtk.EntryCompletion()
        completion.set_match_func(self.match_func)
        completion.connect("match-selected",
                             self.on_completion_match)
        completion.set_model(self.combobox.get_model())
        completion.set_text_column(0)
        self.entry.set_completion(completion)
        
        # when user hits enter, close the dialog window
        self.set_default_response(gtk.RESPONSE_OK)
        self.entry.set_activates_default(True)

        if default_job_code:
            self.entry.set_text(default_job_code)
        
        self.vbox.pack_start(task_hbox, False, False, padding = 6)
        self.vbox.pack_start(self.job_code_hbox, False, False, padding=12)
        
        self.set_transient_for(parent_window)
        self.show_all()
        self.connect('response', self.on_job_code_resp)
            
    def match_func(self, completion, key, iter):
         model = completion.get_model()
         return model[iter][0].lower().startswith(self.entry.get_text().lower())
         
    def on_completion_match(self, completion, model, iter):
         self.entry.set_text(model[iter][0])
         self.entry.set_position(-1)

    def get_job_code(self):
        return self.combobox.child.get_text()
        
    def on_job_code_resp(self,  jc_dialog, response):
        user_chose_code = False
        if response == gtk.RESPONSE_OK:
            user_chose_code = True
            logger.debug("Job Code entered")
        else:
            logger.debug("Job Code not entered")
        self.post_job_code_entry_callback(self, user_chose_code, self.get_job_code())
        

class PreferencesDialog():
    """
    Dialog window to show Rapid Photo Downloader preferences.
    
    Is tightly integrated into main Rapid Photo Downloader window, i.e.
    directly access members in class RapidApp.
    """
    
    def __init__(self, rapidapp):

        self.builder = gtk.Builder()
        self.builder.set_translation_domain(config.APP_NAME)
        self.builder.add_from_file(paths.share_dir("glade3/prefs.ui"))
        self.builder.connect_signals(self)
        
        self.dialog = self.preferencesdialog
        self.widget = self.dialog
        self.dialog.set_transient_for(rapidapp.rapidapp)
        self.prefs = rapidapp.prefs
        
        rapidapp.preferences_dialog_displayed = True
        
        self.pref_dialog_startup = True
        
        self.rapidapp = rapidapp

        self._setup_tab_selector()
        
        self._setup_control_spacing()
        
        if metadatavideo.DOWNLOAD_VIDEO:
            self.file_types = _("photos and videos")
        else:
            self.file_types = _("photos")

        self._setup_sample_names()
        
        # setup tabs
        self._setup_photo_download_folder_tab()
        self._setup_image_rename_tab()
        self._setup_video_download_folder_tab()
        self._setup_video_rename_tab()                
        self._setup_rename_options_tab()
        self._setup_job_code_tab()
        self._setup_device_tab()
        self._setup_backup_tab()
        self._setup_miscellaneous_tab()
        self._setup_error_tab()
        
        if not metadatavideo.DOWNLOAD_VIDEO:
            self.disable_video_controls()

        self.dialog.realize()
        
        #set the width of the left column for selecting values
        #note: this must be called after self.dialog.realize(), or else the width calculation will fail
        width_of_widest_sel_row = self.treeview.get_background_area(1, self.treeview_column)[2]
        self.scrolled_window.set_size_request(width_of_widest_sel_row + 2, -1)

        #set the minimum width of the scolled window holding the photo rename table
        if self.rename_scrolledwindow.get_vscrollbar():
            extra = self.rename_scrolledwindow.get_vscrollbar().allocation.width + 10
        else:
            extra = 10
        self.rename_scrolledwindow.set_size_request(self.rename_table.allocation.width + extra,   -1)

        self.dialog.show()
        
        self.pref_dialog_startup = False

    def __getattr__(self, key):
        """Allow builder widgets to be accessed as self.widgetname
        """
        widget = self.builder.get_object(key)
        if widget: # cache lookups
            setattr(self, key, widget)
            return widget
        raise AttributeError(key)
        
    def on_preferencesdialog_destroy(self,  widget):
        """ Delete variables from memory that cause a file descriptor to be created on a mounted media"""
        logger.debug("Preference window closing")
        
    def _setup_tab_selector(self):
        self.notebook.set_show_tabs(0)
        self.model = gtk.ListStore(type(""))
        column = gtk.TreeViewColumn()
        rentext = gtk.CellRendererText()
        column.pack_start(rentext, expand=0)
        column.set_attributes(rentext, text=0)
        self.treeview_column = column
        self.treeview.append_column(column)
        self.treeview.props.model = self.model
        for c in self.notebook.get_children():
            label = self.notebook.get_tab_label(c).get_text()
            if not label.startswith("_"):
                self.model.append( (label,) )
        

        # select the first value in the list store
        self.treeview.set_cursor(0,column)
    
    def on_download_folder_filechooser_button_selection_changed(self, widget):
        self.prefs.download_folder = widget.get_current_folder()
        self.update_photo_download_folder_example()
        
    def on_video_download_folder_filechooser_button_selection_changed(self, widget):
        self.prefs.video_download_folder = widget.get_current_folder()
        self.update_video_download_folder_example()
    
    def on_backup_folder_filechooser_button_selection_changed(self, widget):
        self.prefs.backup_location = widget.get_current_folder()
        self.update_backup_example()
        
    def on_device_location_filechooser_button_selection_changed(self, widget):
        self.prefs.device_location = widget.get_current_folder()
    
    def _setup_sample_names(self, use_dummy_data = False):
        """
        If use_dummy_data is True, then samples will not attempt to get
        data from actual download files
        """
        job_code = self.prefs.most_recent_job_code()
        if job_code is None:
            job_code = _("Job Code")
        self.downloads_today_tracker = DownloadsTodayTracker(
                                    day_start = self.prefs.day_start,
                                    downloads_today = self.prefs.downloads_today[1],
                                    downloads_today_date = self.prefs.downloads_today[0])
        self.sequences = gn.Sequences(self.downloads_today_tracker, 
                                      self.prefs.stored_sequence_no)
                                      
        # get example photo and video data
        if use_dummy_data:
            self.sample_photo = None
        else:
            self.sample_photo = self.rapidapp.thumbnails.get_sample_file(rpdfile.FILE_TYPE_PHOTO)
            if self.sample_photo is not None:
                # try to load metadata from the file returned
                # if it fails, give up with this sample file
                if not self.sample_photo.load_metadata():
                    self.sample_photo = None
                else:
                    self.sample_photo.sequences = self.sequences
                    self.sample_photo.download_start_time = datetime.datetime.now()
                
        if self.sample_photo is None:
            self.sample_photo = rpdfile.SamplePhoto(sequences=self.sequences)
            
        self.sample_photo.job_code = job_code
        
        self.sample_video = None
        if metadatavideo.DOWNLOAD_VIDEO:
            if not use_dummy_data:
                self.sample_video = self.rapidapp.thumbnails.get_sample_file(rpdfile.FILE_TYPE_VIDEO)
                if self.sample_video is not None:
                    self.sample_video.load_metadata()
                    self.sample_video.sequences = self.sequences
                    self.sample_video.download_start_time = datetime.datetime.now()                
            if self.sample_video is None:
                self.sample_video = rpdfile.SampleVideo(sequences=self.sequences)
            self.sample_video.job_code = job_code


    
    def _setup_control_spacing(self):
        """
        set spacing of some but not all controls
        """
        
        self._setup_table_spacing(self.download_folder_table) 
        self._setup_table_spacing(self.video_download_folder_table) 
        self.download_folder_table.set_row_spacing(2, 
                                hd.VERTICAL_CONTROL_SPACE)
        self.video_download_folder_table.set_row_spacing(2, 
                                hd.VERTICAL_CONTROL_SPACE)
        self._setup_table_spacing(self.rename_example_table)
        self._setup_table_spacing(self.video_rename_example_table)
        self.devices_table.set_col_spacing(0, hd.NESTED_CONTROLS_SPACE)
        self.automation_table.set_col_spacing(0, hd.NESTED_CONTROLS_SPACE)
      
        self._setup_table_spacing(self.backup_table)
        self.backup_table.set_col_spacing(1, hd.NESTED_CONTROLS_SPACE)
        self.backup_table.set_col_spacing(2, hd.CONTROL_LABEL_SPACE)
        self._setup_table_spacing(self.compatibility_table)
        self.compatibility_table.set_row_spacing(0, 
                                            hd.VERTICAL_CONTROL_LABEL_SPACE)                                                    
        self._setup_table_spacing(self.error_table)
    
    
    def _setup_table_spacing(self, table):
        table.set_col_spacing(0, hd.NESTED_CONTROLS_SPACE)
        table.set_col_spacing(1, hd.CONTROL_LABEL_SPACE)

    def _setup_subfolder_table(self):
        self.subfolder_table = SubfolderTable(self, None)
        self.subfolder_vbox.pack_start(self.subfolder_table)
        self.subfolder_table.show_all()
        
    def _setup_video_subfolder_table(self):
        self.video_subfolder_table = VideoSubfolderTable(self, None)
        self.video_subfolder_vbox.pack_start(self.video_subfolder_table)
        self.video_subfolder_table.show_all()

    def _setup_photo_download_folder_tab(self):
        self.download_folder_filechooser_button = gtk.FileChooserButton(
                            _("Select a folder to download photos to"))
        self.download_folder_filechooser_button.set_current_folder(
                            self.prefs.download_folder)
        self.download_folder_filechooser_button.set_action(
                            gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER)
        self.download_folder_filechooser_button.connect("selection-changed", 
                    self.on_download_folder_filechooser_button_selection_changed)
                            
        self.download_folder_table.attach(
                            self.download_folder_filechooser_button, 
                            2, 3, 2, 3, yoptions = gtk.SHRINK)
        self.download_folder_filechooser_button.show()        

        self._setup_subfolder_table()
        self.update_photo_download_folder_example()
        
    def _setup_video_download_folder_tab(self):
        self.video_download_folder_filechooser_button = gtk.FileChooserButton(
                            _("Select a folder to download videos to"))
        self.video_download_folder_filechooser_button.set_current_folder(
                            self.prefs.video_download_folder)
        self.video_download_folder_filechooser_button.set_action(
                            gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER)
        self.video_download_folder_filechooser_button.connect("selection-changed", 
                    self.on_video_download_folder_filechooser_button_selection_changed)
                            
        self.video_download_folder_table.attach(
                            self.video_download_folder_filechooser_button, 
                            2, 3, 2, 3, yoptions = gtk.SHRINK)
        self.video_download_folder_filechooser_button.show()        
        self._setup_video_subfolder_table()
        self.update_video_download_folder_example()        
    
    def _setup_image_rename_tab(self):

        self.rename_table = PhotoRenameTable(self, self.rename_scrolledwindow)
        self.rename_table_vbox.pack_start(self.rename_table)
        self.rename_table.show_all()
        self._setup_photo_original_name()
        self.update_photo_rename_example()

    def _setup_photo_original_name(self):
        self.original_name_label.set_markup("<i>%s</i>" % self.sample_photo.display_name)
    
    def _setup_video_rename_tab(self):

        self.video_rename_table = VideoRenameTable(self, self.video_rename_scrolledwindow)
        self.video_rename_table_vbox.pack_start(self.video_rename_table)
        self.video_rename_table.show_all()
        self._setup_video_original_name()
        self.update_video_rename_example()
        
    def _setup_video_original_name(self):
        if self.sample_video is not None:
            self.video_original_name_label.set_markup("<i>%s</i>" % self.sample_video.display_name)
        else:
            self.video_original_name_label.set_markup("")        
                
    def _setup_rename_options_tab(self):
        
        # sequence numbers
        self.downloads_today_entry = ValidatedEntry.ValidatedEntry(ValidatedEntry.bounded(ValidatedEntry.v_int, int, 0))
        self.stored_number_entry = ValidatedEntry.ValidatedEntry(ValidatedEntry.bounded(ValidatedEntry.v_int, int, 1))
        self.downloads_today_entry.connect('changed', self.on_downloads_today_entry_changed)
        self.stored_number_entry.connect('changed', self.on_stored_number_entry_changed)
        v = self.rapidapp.downloads_today_tracker.get_and_maybe_reset_downloads_today()
        self.downloads_today_entry.set_text(str(v))
        # make the displayed value of stored sequence no 1 more than actual value
        # so as not to confuse the user
        self.stored_number_entry.set_text(str(self.prefs.stored_sequence_no+1))
        self.sequence_vbox.pack_start(self.downloads_today_entry, expand=True, fill=True)
        self.sequence_vbox.pack_start(self.stored_number_entry, expand=False)
        self.downloads_today_entry.show()
        self.stored_number_entry.show()
        hour, minute = self.rapidapp.downloads_today_tracker.get_day_start()
        self.hour_spinbutton.set_value(float(hour))
        self.minute_spinbutton.set_value(float(minute))

        self.synchronize_raw_jpg_checkbutton.set_active(
                            self.prefs.synchronize_raw_jpg)
        
        #compatibility
        self.strip_characters_checkbutton.set_active(
                            self.prefs.strip_characters)
        
    def _setup_job_code_tab(self):
        self.job_code_liststore = gtk.ListStore(str)
        column = gtk.TreeViewColumn()
        rentext = gtk.CellRendererText()
        rentext.connect('edited', self.on_job_code_edited)
        rentext .set_property('editable', True)

        column.pack_start(rentext, expand=0)
        column.set_attributes(rentext, text=0)
        self.job_code_treeview_column = column
        self.job_code_treeview.append_column(column)
        self.job_code_treeview.props.model = self.job_code_liststore
        for code in self.prefs.job_codes:
            self.job_code_liststore.append((code, ))
            
        # set multiple selections
        self.job_code_treeview.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
        
        self.remove_all_job_code_button.set_image(gtk.image_new_from_stock(
                                                gtk.STOCK_CLEAR,
                                                gtk.ICON_SIZE_BUTTON))  
    def _setup_device_tab(self):

        self.device_location_filechooser_button = gtk.FileChooserButton(
                            _("Select a folder containing %(file_types)s") % {'file_types':self.file_types})
        self.device_location_filechooser_button.set_current_folder(
                            self.prefs.device_location)
        self.device_location_filechooser_button.set_action(
                            gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER)
                            
        self.device_location_filechooser_button.connect("selection-changed", 
                    self.on_device_location_filechooser_button_selection_changed)

        self.devices2_table.attach(self.device_location_filechooser_button,
                            1, 2, 1, 2, xoptions = gtk.EXPAND|gtk.FILL,  yoptions = gtk.SHRINK)
        self.device_location_filechooser_button.show()
        self.autodetect_device_checkbutton.set_active(
                            self.prefs.device_autodetection)
        self.autodetect_psd_checkbutton.set_active(
                            self.prefs.device_autodetection_psd)
                            
        self.update_device_controls()
        

    def _setup_backup_tab(self):
        self.backup_folder_filechooser_button = gtk.FileChooserButton(
                            _("Select a folder in which to backup %(file_types)s") % {'file_types':self.file_types})
        self.backup_folder_filechooser_button.set_current_folder(
                            self.prefs.backup_location)
        self.backup_folder_filechooser_button.set_action(
                            gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER)
        self.backup_folder_filechooser_button.connect("selection-changed", 
                    self.on_backup_folder_filechooser_button_selection_changed)
        self.backup_table.attach(self.backup_folder_filechooser_button,
                            3, 4, 8, 9, yoptions = gtk.SHRINK)
        self.backup_folder_filechooser_button.show()
        self.backup_identifier_entry.set_text(self.prefs.backup_identifier)
        self.video_backup_identifier_entry.set_text(self.prefs.video_backup_identifier)
        
        #setup controls for manipulating sensitivity
        self._backup_controls0 = [self.auto_detect_backup_checkbutton]
        self._backup_controls1 = [self.backup_identifier_explanation_label,
                                self.backup_identifier_label,
                                self.backup_identifier_entry,
                                self.example_backup_path_label,
                                self.backup_example_label,]
        self._backup_controls2 = [self.backup_location_label,
                                self.backup_folder_filechooser_button,
                                self.backup_location_explanation_label]
        self._backup_controls = self._backup_controls0 + self._backup_controls1 + \
                                self._backup_controls2
                                
        self._backup_video_controls = [self.video_backup_identifier_label,
                                self.video_backup_identifier_entry]
        
        #assign values to checkbuttons only when other controls
        #have been setup, because their toggle signal is activated
        #when a value is assigned
        
        self.backup_checkbutton.set_active(self.prefs.backup_images)
        self.auto_detect_backup_checkbutton.set_active(
                            self.prefs.backup_device_autodetection)
        self.update_backup_controls()
        self.update_backup_example()
    
    def _setup_miscellaneous_tab(self):
        self.auto_startup_checkbutton.set_active(
                        self.prefs.auto_download_at_startup)
        self.auto_insertion_checkbutton.set_active(
                        self.prefs.auto_download_upon_device_insertion)
        self.auto_unmount_checkbutton.set_active(
                        self.prefs.auto_unmount)
        self.auto_exit_checkbutton.set_active(
                        self.prefs.auto_exit)
        self.auto_exit_force_checkbutton.set_active(
                        self.prefs.auto_exit_force)
        self.auto_delete_checkbutton.set_active(
                        self.prefs.auto_delete)
        self.generate_thumbnails_checkbutton.set_active(
                        self.prefs.generate_thumbnails)
                        
        self.update_misc_controls()

        
    def _setup_error_tab(self):
        if self.prefs.download_conflict_resolution == config.SKIP_DOWNLOAD:
            self.skip_download_radiobutton.set_active(True)
        else:
            self.add_identifier_radiobutton.set_active(True)
            
        if self.prefs.backup_duplicate_overwrite:
            self.backup_duplicate_overwrite_radiobutton.set_active(True)
        else:
            self.backup_duplicate_skip_radiobutton.set_active(True)

    
    def update_example_file_name(self, display_table, rename_table, sample_rpd_file, generator, example_label):
        if hasattr(self, display_table) and sample_rpd_file is not None:
            sample_rpd_file.download_folder = self.prefs.get_download_folder_for_file_type(sample_rpd_file.file_type)
            sample_rpd_file.strip_characters = self.prefs.strip_characters
            sample_rpd_file.initialize_problem() 
            name = generator.generate_name(sample_rpd_file)
        else:
            name = ''
            
        # since this is markup, escape it
        text = "<i>%s</i>" % utilities.escape(name)
        
        if sample_rpd_file is not None:
            if sample_rpd_file.has_problem():
                text += "\n"
                # Translators: please do not modify or leave out html formatting tags like <i> and <b>. These are used to format the text the users sees
                text += _("<i><b>Warning:</b> There is insufficient metadata to fully generate the name. Please use other renaming options.</i>")

        example_label.set_markup(text)        
    
    def update_photo_rename_example(self):
        """ 
        Displays example image name to the user 
        """
        generator = gn.PhotoName(self.prefs.image_rename)
        self.update_example_file_name('rename_table', self.rename_table, 
                                      self.sample_photo, generator, 
                                      self.new_name_label)

        
    def update_video_rename_example(self):
        """
        Displays example video name to the user
        """
        if self.sample_video is not None:
            generator = gn.VideoName(self.prefs.video_rename)
        else:
            generator = None
        self.update_example_file_name('video_rename_table', 
                                      self.video_rename_table, 
                                      self.sample_video, generator, 
                                      self.video_new_name_label)
            
    def update_download_folder_example(self, display_table, subfolder_table, 
                                       download_folder, sample_rpd_file, 
                                       generator,
                                       example_download_path_label, 
                                       subfolder_warning_label):
        """ 
        Displays example subfolder name(s) to the user 
        """
        
        if hasattr(self, display_table) and sample_rpd_file is not None:
            #~ subfolder_table.update_example_job_code()
            sample_rpd_file.strip_characters = self.prefs.strip_characters
            sample_rpd_file.initialize_problem()
            path = generator.generate_name(sample_rpd_file)
        else:
            path = ''
            
        text = os.path.join(download_folder, path)
        # since this is markup, escape it
        path = utilities.escape(text)

        warning = ""
        if sample_rpd_file is not None:
            if sample_rpd_file.has_problem():
                warning = _("<i><b>Warning:</b> There is insufficient metadata to fully generate subfolders. Please use other subfolder naming options.</i>" )

        # Translators: you should not modify or leave out the %s. This is a code used by the programming language python to insert a value that thes user will see
        example_download_path_label.set_markup(_("<i>Example: %s</i>") % text)
        subfolder_warning_label.set_markup(warning)
        
    def update_photo_download_folder_example(self):
        if hasattr(self, 'subfolder_table'):
            generator = gn.PhotoSubfolder(self.prefs.subfolder)
            self.update_download_folder_example('subfolder_table', 
                            self.subfolder_table, self.prefs.download_folder,
                            self.sample_photo, generator, 
                            self.example_photo_download_path_label, 
                            self.photo_subfolder_warning_label)
        
    def update_video_download_folder_example(self):
        if hasattr(self, 'video_subfolder_table'):
            if self.sample_video is not None:
                generator = gn.VideoSubfolder(self.prefs.video_subfolder)
            else:
                generator = None
            self.update_download_folder_example('video_subfolder_table', 
                        self.video_subfolder_table,
                        self.prefs.video_download_folder,
                        self.sample_video, generator, 
                        self.example_video_download_path_label, 
                        self.video_subfolder_warning_label)
        
    def on_hour_spinbutton_value_changed(self, spinbutton):
        hour = spinbutton.get_value_as_int()
        minute = self.minute_spinbutton.get_value_as_int()
        self.rapidapp.downloads_today_tracker.set_day_start(hour, minute)
        self.on_downloads_today_entry_changed(self.downloads_today_entry)
        
    def on_minute_spinbutton_value_changed(self, spinbutton):
        hour = self.hour_spinbutton.get_value_as_int()
        minute = spinbutton.get_value_as_int()
        self.rapidapp.downloads_today_tracker.set_day_start(hour, minute)
        self.on_downloads_today_entry_changed(self.downloads_today_entry)

    def on_downloads_today_entry_changed(self, entry):
        # do not update value if a download is occurring - it will mess it up!
        if self.rapidapp.download_is_occurring():
            logger.info("Downloads today value not updated, as a download is currently occurring")
        else:            
            v = entry.get_text()
            try:
                v = int(v)
            except:
                v = 0
            if v < 0:
                v = 0
            self.rapidapp.downloads_today_tracker.reset_downloads_today(v)
            self.rapidapp.refresh_downloads_today = True
            self.update_photo_rename_example()
        
    def on_stored_number_entry_changed(self, entry):
        # do not update value if a download is occurring - it will mess it up!        
        if self.rapidapp.download_is_occurring():
            logger.info("Stored number value not updated, as a download is currently occurring")
        else:
            v = entry.get_text()
            try:
                # the displayed value of stored sequence no 1 more than actual value
                # so as not to confuse the user
                v = int(v) - 1
            except:
                v = 0
            if v < 0:
                v = 0
            self.prefs.stored_sequence_no = v
            self.update_photo_rename_example()

    def _update_subfolder_pref_on_error(self, new_pref_list):
        self.prefs.subfolder = new_pref_list

    def _update_video_subfolder_pref_on_error(self, new_pref_list):
        self.prefs.video_subfolder = new_pref_list
        
    
    def check_subfolder_values_valid_on_exit(self, users_pref_list, update_pref_function, filetype, default_pref_list):
        """
        Checks that the user has not entered in any inappropriate values
        
        If they have, filters out bad values and warns the user 
        """
        filtered, pref_list = filter_subfolder_prefs(users_pref_list)
        if filtered:
            logger.info("The %(filetype)s subfolder preferences had some unnecessary values removed.", {'filetype': filetype})
            if pref_list:
                update_pref_function(pref_list)
            else:
                #Preferences list is now empty
                msg = _("The %(filetype)s subfolder preferences entered are invalid and cannot be used.\nThey will be reset to their default values.") % {'filetype': filetype}
                sys.stderr.write(msg + "\n")
                misc.run_dialog(PROGRAM_NAME, msg)
                update_pref_function(self.prefs.get_default(default_pref_list))
    
    def on_preferencesdialog_response(self, dialog, arg):
        if arg == gtk.RESPONSE_HELP:
            webbrowser.open("http://www.damonlynch.net/rapid/documentation")
        else:
            # arg==gtk.RESPONSE_CLOSE, or the user hit the 'x' to close the window
            self.prefs.backup_identifier = self.backup_identifier_entry.get_property("text")
            self.prefs.video_backup_identifier = self.video_backup_identifier_entry.get_property("text")
            
            #check subfolder preferences for bad values
            self.check_subfolder_values_valid_on_exit(self.prefs.subfolder, self._update_subfolder_pref_on_error, _("photo"), "subfolder")
            self.check_subfolder_values_valid_on_exit(self.prefs.video_subfolder, self._update_video_subfolder_pref_on_error, _("video"), "video_subfolder")
                    
            self.dialog.destroy()
            self.rapidapp.preferences_dialog_displayed = False
            self.rapidapp.post_preference_change()
            



    def on_add_job_code_button_clicked(self,  button):
        j = JobCodeDialog(parent_window = self.dialog,
                    job_codes = self.prefs.job_codes,
                    default_job_code = None, 
                    post_job_code_entry_callback=self.add_job_code,
                    entry_only = True)

    def add_job_code(self, dialog, user_chose_code, job_code):
        dialog.destroy()
        if user_chose_code:
            if job_code and job_code not in self.prefs.job_codes:
                self.job_code_liststore.prepend((job_code,  ))
                self.update_job_codes()
                selection = self.job_code_treeview.get_selection()
                selection.unselect_all()
                selection.select_path((0, ))
                #scroll to the top
                adjustment = self.job_code_scrolledwindow.get_vadjustment()
                adjustment.set_value(adjustment.lower)

    def on_remove_job_code_button_clicked(self,  button):
        """ remove selected job codes (can be multiple selection)"""
        selection = self.job_code_treeview.get_selection()
        model, selected = selection.get_selected_rows()
        iters = [model.get_iter(path) for path in selected]
        # only delete if a jobe code is selected
        if iters:
            no = len(iters)
            path = None
            for i in range(0, no):
                iter = iters[i]
                if i == no - 1:
                    path = model.get_path(iter) 
                model.remove(iter)
            
            # now that we removed the selection, play nice with 
            # the user and select the next item
            selection.select_path(path)
            
            #  if there was no selection that meant the user
            # removed the last entry, so we try to select the 
            # last item
            if not selection.path_is_selected(path):
                 row = path[0]-1
                 # test case for empty lists
                 if row >= 0:
                    selection.select_path((row,))

        self.update_job_codes()
        self.update_photo_rename_example()
        self.update_video_rename_example()
        self.update_photo_download_folder_example()
        self.update_video_download_folder_example()
        
    def on_remove_all_job_code_button_clicked(self,  button):
        j = RemoveAllJobCodeDialog(self.dialog, self.remove_all_job_code)
        
    def remove_all_job_code(self, dialog, user_selected):
        dialog.destroy()
        if user_selected:
            self.job_code_liststore.clear()
            self.update_job_codes()
            self.update_photo_rename_example()
            self.update_video_rename_example()
            self.update_photo_download_folder_example()
            self.update_video_download_folder_example()
        
    def on_job_code_edited(self,  widget,  path,  new_text):
        iter = self.job_code_liststore.get_iter(path)
        self.job_code_liststore.set_value(iter,  0,  new_text)
        self.update_job_codes()
        self.update_photo_rename_example()
        self.update_video_rename_example()
        self.update_photo_download_folder_example()
        self.update_video_download_folder_example()

    def update_job_codes(self):
        """ update preferences with list of job codes"""
        job_codes = []
        for row in self.job_code_liststore:
            job_codes.append(row[0])
        self.prefs.job_codes = job_codes
        
    def on_auto_startup_checkbutton_toggled(self, checkbutton):
        self.prefs.auto_download_at_startup = checkbutton.get_active()
        
    def on_auto_insertion_checkbutton_toggled(self, checkbutton):
        self.prefs.auto_download_upon_device_insertion = checkbutton.get_active()
        
    def on_auto_unmount_checkbutton_toggled(self, checkbutton):
        self.prefs.auto_unmount = checkbutton.get_active()
        

    def on_auto_delete_checkbutton_toggled(self, checkbutton):
        self.prefs.auto_delete = checkbutton.get_active()

    def on_auto_exit_checkbutton_toggled(self, checkbutton):
        active = checkbutton.get_active()
        self.prefs.auto_exit = active
        if not active:
            self.prefs.auto_exit_force = False
            self.auto_exit_force_checkbutton.set_active(False)
        self.update_misc_controls()
        
    def on_auto_exit_force_checkbutton_toggled(self, checkbutton):
        self.prefs.auto_exit_force = checkbutton.get_active()
    
    def on_autodetect_device_checkbutton_toggled(self, checkbutton):
        self.prefs.device_autodetection = checkbutton.get_active()
        self.update_device_controls()

    def on_autodetect_psd_checkbutton_toggled(self, checkbutton):
        self.prefs.device_autodetection_psd = checkbutton.get_active()
        
    def on_generate_thumbnails_checkbutton_toggled(self, checkbutton):
        self.prefs.generate_thumbnails = checkbutton.get_active()
        
    def on_backup_duplicate_overwrite_radiobutton_toggled(self,  widget):
        self.prefs.backup_duplicate_overwrite = widget.get_active()
            
    def on_backup_duplicate_skip_radiobutton_toggled(self,  widget):
        self.prefs.backup_duplicate_overwrite = not widget.get_active()
    
    def on_treeview_cursor_changed(self, tree):
        path, column = tree.get_cursor()
        self.notebook.set_current_page(path[0])

    def on_synchronize_raw_jpg_checkbutton_toggled(self, check_button):
        self.prefs.synchronize_raw_jpg = check_button.get_active()
        
    def on_strip_characters_checkbutton_toggled(self, check_button):
        self.prefs.strip_characters = check_button.get_active()
        self.update_photo_rename_example()
        self.update_photo_download_folder_example()
        self.update_video_download_folder_example()
        
    def on_add_identifier_radiobutton_toggled(self, widget):
        if widget.get_active():
            self.prefs.download_conflict_resolution = config.ADD_UNIQUE_IDENTIFIER
        else:
            self.prefs.download_conflict_resolution = config.SKIP_DOWNLOAD
            

    def update_device_controls(self):
        """
        Sets sensitivity of image device controls
        """

        controls = [self.device_location_explanation_label,
                    self.device_location_label,
                    self.device_location_filechooser_button]

        if self.prefs.device_autodetection:
            for c in controls:
                c.set_sensitive(False)
            self.autodetect_psd_checkbutton.set_sensitive(True)
            self.autodetect_image_devices_label.set_sensitive(True)
        else:
            for c in controls:
                c.set_sensitive(True)
            self.autodetect_psd_checkbutton.set_sensitive(False)
            self.autodetect_image_devices_label.set_sensitive(False)
            
        if not self.pref_dialog_startup:
            logger.debug("Resetting sample file photo and video files")
            self._setup_sample_names(use_dummy_data = True)
            self._setup_photo_original_name()
            self.update_photo_download_folder_example()
            self.update_photo_rename_example()
            self.update_video_download_folder_example()
            self._setup_video_original_name()
            self.update_video_rename_example()
    
    def update_misc_controls(self):
        """
        Sets sensitivity of miscillaneous controls
        """
        
        self.auto_exit_force_checkbutton.set_sensitive(self.prefs.auto_exit)
            
    
    def update_backup_controls(self):
        """
        Sets sensitivity of backup related widgets
        """
        
        if not self.backup_checkbutton.get_active():
            for c in self._backup_controls + self._backup_video_controls:
                c.set_sensitive(False)

        else:
            for c in self._backup_controls0:
                c.set_sensitive(True)
            self.update_backup_controls_auto()

    def update_backup_controls_auto(self):
        """
        Sets sensitivity of subset of backup related widgets
        """

        if self.auto_detect_backup_checkbutton.get_active():
            for c in self._backup_controls1:
                c.set_sensitive(True)
            for c in self._backup_controls2:
                c.set_sensitive(False)
            for c in self._backup_video_controls:
                c.set_sensitive(False)
            if metadatavideo.DOWNLOAD_VIDEO:
                for c in self._backup_video_controls:
                    c.set_sensitive(True)
        else:
            for c in self._backup_controls1:
                c.set_sensitive(False)
            for c in self._backup_controls2:
                c.set_sensitive(True)
            if metadatavideo.DOWNLOAD_VIDEO:
                for c in self._backup_video_controls:
                    c.set_sensitive(False)                
            
    def disable_video_controls(self):
        """
        Disables video preferences if video downloading is disabled
        (probably because the appropriate libraries to enable
        video metadata extraction are not installed)
        """        
        controls = [self.example_video_filename_label, 
                    self.original_video_filename_label,
                    self.new_video_filename_label,
                    self.video_new_name_label,
                    self.video_original_name_label,
                    self.video_rename_scrolledwindow,
                    self.video_folders_hbox,
                    self.video_backup_identifier_label,
                    self.video_backup_identifier_entry
                    ]
        for c in controls:
            c.set_sensitive(False)
            
        self.videos_cannot_be_downloaded_label.show()
        self.folder_videos_cannot_be_downloaded_label.show()
        self.folder_videos_cannot_be_downloaded_hbox.show()
    
    def on_auto_detect_backup_checkbutton_toggled(self, widget):
        self.prefs.backup_device_autodetection = widget.get_active()
        self.update_backup_controls_auto()
        
    def on_backup_checkbutton_toggled(self, widget):
        self.prefs.backup_images = self.backup_checkbutton.get_active()
        self.update_backup_controls()

    def on_backup_identifier_entry_changed(self, widget):
        self.update_backup_example()
        #~ self.prefs.
    
    def on_video_backup_identifier_entry_changed(self, widget):
        self.update_backup_example()

    def on_backup_scan_folder_on_entry_changed(self, widget):
        self.update_backup_example()        

    def update_backup_example(self):
        # Translators: this value is used as an example device when automatic backup device detection is enabled. You should translate this.
        drive1 = os.path.join(config.MEDIA_LOCATION, _("externaldrive1"))
        # Translators: this value is used as an example device when automatic backup device detection is enabled. You should translate this.
        drive2 = os.path.join(config.MEDIA_LOCATION, _("externaldrive2"))

        path = os.path.join(drive1, self.backup_identifier_entry.get_text())
        path2 = os.path.join(drive2, self.backup_identifier_entry.get_text())
        path3 = os.path.join(drive2, self.video_backup_identifier_entry.get_text())
        path = utilities.escape(path)
        path2 = utilities.escape(path2)
        path3 = utilities.escape(path3)
        if metadatavideo.DOWNLOAD_VIDEO:
            example = "<i>%s</i>\n<i>%s</i>\n<i>%s</i>" % (path, path2, path3)
        else:
            example = "<i>%s</i>\n<i>%s</i>" % (path, path2)
        self.example_backup_path_label.set_markup(example)
