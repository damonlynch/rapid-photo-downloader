
# Copyright (c) 2005 Antoon Pardon
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from threading import Lock
from thread import get_ident

from types import BooleanType as UnConnected

UnRegistered, Registered = False, True

class EOInformation(Exception):
    pass

class TubeAccess(Exception):
    pass

class Fifo:

    def __init__(self):
        self.fifo = []

    def put(self, item):
        self.fifo.append(item)

    def get(self):
        return self.fifo.pop(0)

    def size(self):
        return len(self.fifo)

class Tube:

    def __init__(self, maxsize, lck = Lock, container = None):
        if container is None:
            container = Fifo()
        self.readers = set()
        self.writers = set()
        self.container = container
        self.maxsize = maxsize
        self.cb_arglst = []
        self.cb_src = UnRegistered
        self.in_use = Lock()
        self.nowriter = lck()
        self.full = lck()
        self.empty = lck()
        self.empty.acquire()
        self.nowriter.acquire()

    def open(self, access = 'r', *to):
        thrd = get_ident()
        access = access.lower()
        self.in_use.acquire()
        if 'w' in access:
            if len(self.writers) == 0:
                for _ in self.readers:
                    self.nowriter.release()
            self.writers.add(thrd)
        if 'r' in access:
            self.readers.add(thrd)
            if len(self.writers) == 0:
                self.in_use.release()
                self.nowriter.acquire(*to)
            else:
                self.in_use.release()
        else:
            self.in_use.release()

    def close(self, access = 'rw'):
        thrd = get_ident()
        access = access.lower()
        self.in_use.acquire()
        if 'r' in access:
            self.readers.discard(thrd)
        if 'w' in access:
            self.writers.discard(thrd)
##            print "have", self.writers, "writers"
            if len(self.writers) == 0:
                if self.container.size() == 0:
##                    print "emptying container, as size is", self.container.size()
                    self.empty.release()
                    if self.cb_src is Registered and len(self.readers) > 0:
##                        print "adding callback"
                        self.cb_src = gob.idle_add(self._idle_callback)
##                else:
##                    print "container size not empty, is", self.container.size()
                for _ in self.readers:
##                    print "putting EOInformation"
                    self.container.put(EOInformation)
        self.in_use.release()

    def size(self):
        self.in_use.acquire()
        size = self.container.size()
        self.in_use.release()
        return size

    def get(self, *to):
        thrd = get_ident()
        if thrd not in self.readers:
            raise TubeAccess, "Thread has no read access for tube"
        self.empty.acquire(*to)
        self.in_use.acquire()
        size = self.container.size()
        if size == self.maxsize:
            self.full.release()
        item = self.container.get()
        if size != 1:
            self.empty.release()
        elif type(self.cb_src) is not UnConnected:
            gob.source_remove(self.cb_src)
            self.cb_src = Registered
        self.in_use.release()
        if item is EOInformation:
            raise EOInformation
        else:
            return item

    def put(self, item, *to):
        thrd = get_ident()
        if thrd not in self.writers:
            raise TubeAccess, "Thread has no write access for tube"
        if thrd in self.readers:
            self._put_rw(item)
        else:
            self._put_wo(item, *to)

    def _put_wo(self, item, *to):
        self.full.acquire(*to)
        self.in_use.acquire()
        size = self.container.size()
        if size == 0:
            self.empty.release()
            if self.cb_src is Registered:
                #gdk.threads_enter()
                self.cb_src = gob.idle_add(self._idle_callback)
                #gdk.threads_leave()
        self.container.put(item)
        if size + 1 < self.maxsize:
            self.full.release()
        self.in_use.release()

    def _put_rw(self, item):
        self.in_use.acquire()
        size = self.container.size()
        if size == 0:
            self.empty.release()
            if self.cb_src is Registered:
                self.cb_src = gob.idle_add(self._idle_callback)
        self.container.put(item)
        self.in_use.release()

    def _idle_callback(self):
        self.in_use.acquire()
        lst = self.cb_arglst.pop(0)
        self.in_use.release()
        func = lst[0]
        lst[0] = self
        ret_val = func(*lst)
        self.in_use.acquire()
        if ret_val:
            lst[0] = func
            self.cb_arglst.append(lst)
        elif self.cb_arglst == []:
            self.cb_src = UnRegistered
        self.in_use.release()
        return self.cb_src is not UnRegistered


def tube_add_watch(tube, callback, *args):

    global gob #, gdk
    import gobject as gob
    #import gtk.gdk as gdk

    tube.in_use.acquire()
    tube.cb_arglst.append([callback] + list(args))
    if tube.cb_src is UnRegistered:
        if tube.container.size() == 0:
            tube.cb_src = Registered
        else:
            tube.cb_src = gob.idle_add(tube._idle_callback)
    tube.in_use.release()

def tube_remove_watch(tube):
##    tube.in_use.acquire()
##    gob.source_remove(tube.cb_src)
##    tube._idle_callback.handler_block(tube.cb_src)
    pass
