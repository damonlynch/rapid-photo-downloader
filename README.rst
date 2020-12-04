Rapid Photo Downloader
======================

Contents
--------

- `Description`_
- `Install on Ubuntu, openSUSE, Debian, Fedora, and CentOS 8`_
- `Install on CentOS 7.5`_
- `Supported Linux Versions`_
- `Software Requirements and Program Installation on Other Systems`_
    - `Satisfying Software Requirements`_
    - `Installation`_
    - `Uninstallation`_
    - `Installation into a Virtual Environment`_

Description
===========

Rapid Photo Downloader imports photos and videos from cameras, phones,
memory cards and other devices at high speed. It can be configured to
rename photos and videos with meaningful filenames you specify. It can also
back up photos and videos as they are downloaded. It downloads from and backs
up to multiple devices simultaneously.

Unique to Rapid Photo Downloader is its Timeline, which groups photos and
videos based on how much time elapsed between consecutive shots. Use it to
identify photos and videos taken at different periods in a single day or
over consecutive days.

Written by a photographer_ for professional and amateur photographers, Rapid
Photo Downloader is easy to configure and use. Program preferences are
configured without the need for complicated codes. Common tasks can be
automated, such as unmounting a memory card when the download is complete.

A helper command-line program accompanying Rapid Photo Downloader is
``analyze_pv_structure``, which analyzes photos and videos to help determine
how much of a file needs to be read to extract its metadata and thumbnail.

Rapid Photo Downloader currently runs only on Linux. Theoretically it could be
ported to both Mac and Windows with minimal effort. The one gotcha is that
that Windows lacks gphoto2, meaning when run under Windows, it could not
download directly from cameras unless it used something else.

The program is licensed under the GPL3_ or later.

Install on Ubuntu, openSUSE, Debian, Fedora, and CentOS 8
=========================================================

To install Rapid Photo Downloader, run as your regular user (i.e. *without*
sudo):

``python3 install.py``

The program sudo may prompt for your administrator (root) password during the
install process, if required.

For a list of optional commands you can give the insaller, run:

``python3 install.py --help``

Finally, to uninstall:

``python3 -m pip uninstall rapid-photo-downloader``

If you installed the man pages, they are found in ``/usr/local/share/man/man1``.

Install on CentOS 7.5
=====================

Consult the online documentation for additional steps to take prior to running
the installation script. Once completed, the steps are the same as above,
except the command ``python3`` is replaced by ``python3.6``

Supported Linux Versions
========================

 - Ubuntu 16.04 or newer
 - LinuxMint 18 or newer
 - Debian 9, unstable or testing
 - Fedora 32 or newer
 - openSUSE Leap 15.1 or newer
 - CentOS 7.5 or 8
 - Any distribution meeting the software requirements below

Software Requirements and Program Installation on Other Systems
===============================================================

The program is installed using the Python tool pip_, which automates almost
all aspects of the program's installation by using PyPi_ to download Python
modules.

Rapid Photo Downloader requires:

 - Python 3.5 or greater, and its development headers
 - PyQt_ 5.4 or greater
 - Qt_ 5.4 or greater
 - `Python gobject introspection`_ modules:
    - GUdev 1.0
    - UDisks 2.0
    - GLib 2.0
    - GExiv2 0.10
    - Gst 1.0
    - Notify 0.7
 - `python-gphoto2`_ 1.4.0 or newer
 - pyzmq_
 - tornado_
 - psutil_ 3.4.2 or newer
 - pyxdg_
 - Arrow_
 - dateutil_ 2.2 or newer
 - exiv2_
 - ExifTool_
 - EasyGUI_ 0.97.4 or older (0.98 has a critical bug)
 - Colour_
 - pymediainfo_
 - SortedContainers_
 - rawkit_: renders thumbnails from RAW images from which a thumbnail cannot be
   extracted using libraw_, which is especially useful when downloading DNG
   files from Android phones or working with old RAW formats.
 - `Qt5 plugin for reading TIFF images`_
 - Requests_
 - Tenacity_
 - intltool_
 - Babel_

Highly recommended, optional dependencies:

 - colorlog_: generates coloured program output when running Rapid Photo
   Downloader from the terminal.
 - pyprind_: shows a progress bar on the command line while running the program
   ``analyze_pv_structure``.
 - pyheif_: open HEIF / HEIC files (requires Python 3.6 or above)
 - pillow_: work with HEIF / HEIC files

Satisfying Software Requirements
--------------------------------

While Rapid Photo Downloader's installer will automatically download and install
most required Python modules not already found on your system, there are some it
cannot install. You must install these Python modules and a few other programs
prior to installing Rapid Photo Downloader. The Python module requirements are
the Python 3 versions of:

 - PyQt_ 5.4 or greater
 - All `Python gobject introspection`_ modules listed above

The non-Python programs required are:

 - ExifTool_
 - exiv2_
 - Given `python-gphoto2`_ will almost certainly be installed from PyPi_, the
   development packages for libgphoto2 and Python3 must be installed first,
   e.g. libgphoto2-dev and python3-dev
 - Likewise, given pymediainfo_ will almost certainly be installed from PyPi_,
   the package libmediainfo must be installed.
 - If installing pyzmq_ from PyPi_, you must first install the development
   packages for libzmq3 and Python3, e.g. libzmq3-dev and python3-dev
 - Qt5 plugin for reading TIFF images
 - If installing rawkit_ from PyPi_, libraw is required, e.g. libraw10 or
   libraw15.
 - If installing EasyGUI_ from PyPi_, ensure the Tkinter package for Python 3 is
   installed.

Installation
------------

After `satisfying software requirements`_ using your Linux distribution's
standard package installation tools, you should install Rapid Photo Downloader
using the following steps.

First, you may need to update your user's copy of pip and setuptools:

``python3 -m pip install --user --upgrade pip``

``python3 -m pip install --user --upgrade setuptools wheel``

The following command will install all required and optional Python modules not
already installed on your system, with the exception of those specified above
in `satisfying software requirements`_:

``python3 install.py``

**Caution:** *untarring the archive, building it and installing it using*
``sudo python3 setup.py install`` *is* **not** *supported, and* **not**
*recommended.*

Uninstallation
--------------

Assuming you installed using the instructions above, run:

``python3 -m pip uninstall rapid-photo-downloader``

If you installed the man pages, they are found in ``/usr/local/share/man/man1``.

Installation into a Virtual Environment
---------------------------------------

Rapid Photo Downloader can be installed into a virtual environment, allowing you
to isolate the Python packages it needs from other programs on your system.

Virtual environments created with the --system-site-packages option are not
supported. An Intel or AMD 64 bit platform is required.

To install Rapid Photo Downloader into a Python virtual environment, create the
virtual environment (naming it whatever you like):

``python3 -m venv myenv``

Activate the virtual environment:

``source myenv/bin/activate``

Then run the installer, passing the command line option telling the script to
install Rapid Photo Downloader into the virtual environment:

``python install.py --virtual-env``

Once the program is installed, you can then deactivate the virtual environment
with the deactivate command:

``deactivate``

Rapid Photo Downloader can be started without activating the virtual environment
by running

``myenv/bin/rapid-photo-downloader``

To uninstall from the virtual environment, simply delete the virtual
environment's directory.



.. _website: http://damonlynch.net/rapid
.. _Python gobject introspection: https://wiki.gnome.org/action/show/Projects/PyGObject
.. _python-gphoto2: https://github.com/jim-easterbrook/python-gphoto2
.. _pyzmq: https://github.com/zeromq/pyzmq
.. _psutil: https://github.com/giampaolo/psutil
.. _pyxdg: https://www.freedesktop.org/wiki/Software/pyxdg/
.. _Arrow: https://github.com/crsmithdev/arrow
.. _dateutil: https://labix.org/python-dateutil
.. _typing: https://pypi.python.org/pypi/typing
.. _scandir: https://github.com/benhoyt/scandir
.. _colorlog: https://github.com/borntyping/python-colorlog
.. _rawkit: https://github.com/photoshell/rawkit
.. _pyprind: https://github.com/rasbt/pyprind
.. _exiv2: http://www.exiv2.org/
.. _ExifTool: http://www.sno.phy.queensu.ca/~phil/exiftool/
.. _PyPi: https://pypi.python.org/pypi
.. _GPL3: http://www.gnu.org/licenses/gpl-3.0.en.html
.. _photographer: http://www.damonlynch.net
.. _pip: https://pip.pypa.io/en/stable/
.. _libraw: http://www.libraw.org/
.. _PyQt: https://riverbankcomputing.com/software/pyqt/intro
.. _EasyGUI: https://github.com/robertlugg/easygui
.. _Colour: https://github.com/vaab/colour
.. _intltool: https://freedesktop.org/wiki/Software/intltool/
.. _Tkinter: https://wiki.python.org/moin/TkInter
.. _`Qt5 plugin for reading TIFF images`: http://doc.qt.io/qt-5/qtimageformats-index.html
.. _pymediainfo: https://github.com/sbraz/pymediainfo
.. _Qt: https://www.qt.io/
.. _SortedContainers: http://www.grantjenks.com/docs/sortedcontainers/
.. _Requests: http://docs.python-requests.org/
.. _tornado: http://www.tornadoweb.org/
.. _Tenacity: https://github.com/jd/tenacity
.. _pyheif: https://github.com/david-poirier-csn/pyheif
.. _pillow: https://github.com/python-pillow/Pillow
.. _Babel: http://babel.pocoo.org/en/latest/