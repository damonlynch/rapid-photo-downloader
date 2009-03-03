# Copyright (c) 2006, Daniel J. Popowich
# 
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# Send bug reports and contributions to:
#
#    dpopowich AT astro dot umass dot edu
#

'''
ValidatedEntry.py

Provides ValidatedEntry, a subclass of gtk.Entry which validates
input.

Usage: create an instance of ValidatedEntry, specifying the function
to validate input.  E.g.:

 :   def money(text):
 :       "validate input to be monetary value"
 :       ...
 :
 :   money_entry = ValidatedEntry(money)

Validation functions must accept one argument, the text to be
validated, and must return one of:

    1: the input is valid.
    0: the input is invalid and should not be displayed.
   -1: the input is partially valid and will be displayed (and by
       default with a different background color).

Three module-level variables are defined for the convenience of
validation function writers: VALID (1), INVALID (0), PARTIAL (-1).

There is one public method, isvalid(), which will return True if the
current text is valid.

Note: care should be taken when implementing validation functions to
allow empty strings to be VALID or at least PARTIAL.  An empty string
should never be INVALID.

Note: the hooks for calling the validation function are implemented by
connecting the object to handlers for the gtk.Editable "insert-text"
and "delete-text" signals.  These handlers are connected to instances
in the constructor, so will, by default, be called before other
handlers connected to the widgets for "*-text" signals.  When input is
INVALID, stop_emission() is called, so later handlers for "*-text"
signals will not be called.

See the doc string for ValidatedEntry.__init__ for more details.

'''

import pygtk
pygtk.require('2.0')

import gtk
import gtk.gdk

if gtk.gtk_version < (2, 8):
    import warnings

    msg ='''This module was developed and tested with version 2.8.9 of gtk.
You are using version %d.%d.%d.  Your milage may vary''' % gtk.gtk_version
    warnings.warn(msg)

# major, minor, patch
version = 1, 0, 4

PARTIAL, INVALID, VALID = range(-1,2)

class ValidatedEntry(gtk.Entry):

    white = gtk.gdk.color_parse('white')
    yellow = gtk.gdk.color_parse('yellow')

    def __init__(self, valid_func,
                 max=0,
                 use_bg=True, valid_bg=white, partial_bg=yellow,
                 error_func=None):
        '''
        Create instance of validating gtk.Entry.

        valid_func: the function to validate input.  See module doc
                    string for details.

        max: passed to gtk.Entry constructor. (default: 0)

        use_bg: if True (the default) set the base color of the
                widget to indicate validity; see valid_bg and partial_bg.

        valid_bg: a gtk.gdk.Color; the base color of the widget when
                  the input is valid. (default: white)

        partial_bg: a gtk.gdk.Color; the base color of the widget when
                    the input is partially valid. (default: yellow)

        error_func: a function to call (with no arguments) when
                    valid_func returns INVALID.  If None (the default)
                    the default action will be to emit a short beep.
        '''

        assert valid_func('') != INVALID, 'valid_func cannot return INVALID for an empty string'
        
        gtk.Entry.__init__(self, max)

        self.__valid_func = valid_func
        self.__use_bg = use_bg
        self.__valid_bg = valid_bg
        self.__partial_bg = partial_bg
        self.__error_func = (error_func or
                             gtk.gdk.display_get_default().beep)

        self.connect('insert-text', self.__insert_text_cb)
        self.connect('delete-text', self.__delete_text_cb)

        # bootstrap with an empty string (so the box will appear with
        # the partial_bg if an empty string is PARTIAL)
        self.insert_text('')

    def isvalid(self):
        return self.__isvalid

    def __insert_text_cb(self, entry, text, length, position):
        'callback for "insert-text" signal'

        # generate what the new text will be
        text = text[:length]
        pos = self.get_position()
        old = self.get_text()
        new = old[:pos] + text + old[pos:]

        # validate the new text
        self.__validate(new, 'insert-text')
        
    def __delete_text_cb(self, entry, start, end):
        'callback for "delete-text" signal'

        # generate what the new text will be
        old = self.get_text()
        new = old[:start] + old[end:]
        
        # validate the new text
        self.__validate(new, 'delete-text')

    def __validate(self, text, signal):
        'calls the user-provided validation function'
        
        # validate
        r = self.__valid_func(text)
        if r == VALID:
            self.__isvalid = True
            if self.__use_bg:
                self.modify_base(gtk.STATE_NORMAL, self.__valid_bg)
        elif r == PARTIAL:
            self.__isvalid = False
            if self.__use_bg:
                self.modify_base(gtk.STATE_NORMAL, self.__partial_bg)
        else:
            # don't set self.__isvalid: since we're not displaying the
            # new value, the validity should be whatever it was before
            self.stop_emission(signal)
            self.__error_func()


######################################################################
#            
# Sample validation functions to use with ValidatedEntry
#
######################################################################

import re


# STRING (non-empty after stripping)
def v_nonemptystring(value):
    '''
    VALID: non-empty string after stripping whitespace
    PARTAL: empty or all whitespace
    INVALID: N/A
    '''
    if value.strip():
        return VALID
    return PARTIAL

# INT
def v_int(value):
    '''
    VALID: any postive or negative integer
    PARTAL: empty or leading "-"
    INVALID: non-numeral
    '''
    v = value.strip()
    if not v or v == '-':
        return PARTIAL
    try:
        int(value)
        return VALID
    except:
        return INVALID

# FLOAT
def v_float(value):
    '''
    VALID: any postive or negative floating point
    PARTAL: empty or leading "-", "."
    INVALID: non-numeral
    '''
    v = value.strip()
    if not v or v in ('-', '.', '-.'):
        return PARTIAL
    try:
        float(value)
        return VALID
    except:
        return INVALID


# ISBN
_isbnpartial = re.compile('[0-9]{0,9}[0-9xX]?$')
def v_isbn(v):

    '''Validate ISBN input.

    From the isbn manual, section 4.4:
     
    The check digit is the last digit of an ISBN. It is calculated on
    a modulus 11 with weights 10-2, using X in lieu of 10 where ten
    would occur as a check digit.  This means that each of the first
    nine digits of the ISBN -- excluding the check digit itself -- is
    multiplied by a number ranging from 10 to 2 and that the resulting
    sum of the products, plus the check digit, must be divisible by 11
    without a remainder.'''

    
    if _isbnpartial.match(v):
        # isbn is ten characters in length
        if len(v) < 10:
            return PARTIAL

        s = 0

        for i, c in enumerate(v):
            s += (c in 'xX' and 10 or int(c)) * (10 - i)

        if s % 11 == 0:
            return VALID

    return INVALID

# MONEY
# re for (possibly negative) money
_money_re = re.compile('-?\d*(\.\d{1,2})?$')
# validation function for money
def v_money(value):
    '''
    VALID: any postive or negative floating point with at most two
           digits after the decimal point.
    PARTAL: empty or leading "-", "."
    INVALID: non-numeral or more than two digits after the decimal
             point.
    '''
    if not value or value == '-' or value[-1] == '.':
        return PARTIAL

    if _money_re.match(value):
        return VALID

    return INVALID

# PHONE
# the characters in a phone number
_phonechars = re.compile('[- 0-9]*$')
# valid phone number: [AC +]EXT-LINE
_phone = re.compile('([2-9][0-8][0-9]\s+)?[2-9][0-9]{2}-[0-9]{4}$')
def v_phone(value):
    '''
    VALID: any phone number of the form: EXT-LINE -or- AC EXT-LINE.
    PARTAL: any characters that make up a valid #.
    INVALID: characters that are not used in a phone #.
    '''
    if _phone.match(value):
	return VALID
    if _phonechars.match(value):
        return PARTIAL
    return INVALID

def empty_valid(vfunc):

    '''
    empty_valid is a factory function returning a validation function.
    All of the validation functions in this module return PARTIAL for
    empty strings which, in effect, forces non-empty input.  There may
    be a case where, e.g., you want money input to be optional, but
    v_money will not consider empty input VALID.  Instead of writing
    another validation function you can instead use empty_valid().  By
    wrapping a validation function with empty_valid(), input (after
    stripping), if empty, will be considered VALID.  E.g.:

        ventry = ValidatedEntry(empty_valid(v_money))

    It is recommended that all your validation functions treat empty
    input as PARTIAL, for consistency across all validation functions
    and for use with empty_valid().
    '''

    def validate(value):
        if not value.strip():
            return VALID
        return vfunc(value)

    return validate


def bounded(vfunc, conv, minv=None, maxv=None):

    '''
    bounded is a factory function returning a validation function
    providing bounded input.  E.g., you may want an entry that accepts
    integers, but within a range, say, a score on a test graded in
    whole numbers from 0 to 100:

        score_entry = ValidatedEntry(bounded(v_int, int, 0, 100))

    Arguments:

        vfunc: A validation function.
        conv: A callable that accepts a string argument (the text in
              the entry) and returns a value to be compared to minv
              and maxv.
        minv: None or a value of the same type returned by conv.  If
              None, there is no minimum value enforced.  If a value,
              it will be the minimum value considered VALID.
        maxv: None or a value of the same type returned by conv.  If
              None, there is no maximum value enforced.  If a value,
              it will be the maximum value considered VALID.

    One or both of minv/maxv must be specified.

    The function returned will call vfunc on entry input and if vfunc
    returns VALID, the input will be converted by conv and compared to
    minv/maxv.  If the converted value is within the bounds of
    minv/maxv then VALID will be returned, else PARTIAL will be
    returned.

    '''

    assert minv is not None or maxv is not None, \
           'One of minv/maxv must be specified'

    def F(value):

        r = vfunc(value)
        if r == VALID:
            v = conv(value)
            if minv is not None and v < minv:
                return PARTIAL
            if maxv is not None and v > maxv:
                return PARTIAL
        return r

    return F

            
