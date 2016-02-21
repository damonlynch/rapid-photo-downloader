Rapid Photo Downloader
======================

Rapid Photo Downloader imports photos and videos from cameras, phones,
memory cards and other devices at high speed. It can be configured to
rename photos and videos with meaningful filenames you specify. It can also
back up photos and videos as they are downloaded. It downloads from and backs
up to multiple devices simultaneously.

Unique to Rapid Photo Downloader is its timeline feature, allowing you to
group photos and videos based on how much time elapsed between consecutive
shots. You can use this to quickly identify photos and videos taken at
different periods in a single day or over consecutive days.

Written by a photographer for professional and amateur photographers, Rapid
Photo Downloader is easy to configure and use. Program preferences are
configured without the need for complicated codes. Common tasks can be
automated, such as unmounting a memory card when the download is complete.

For more information, see the project website_.

It currently only runs on Linux. Theoretically it could be ported to both Mac and Windows
with minimal effort (apart from the fact that Windows does not have gphoto2, meaning the program
could not download directly from cameras).

Installation
------------

To be installed, Rapid Photo Downloader requires:
 - Python 3.4 or greater
 - PyQt 5.4 or greater
 - `Python gobject introspection`_
 - `python-gphoto2`_
    - If installing python-gphoto2 from PyPi, you must first install
      the development packages for libgphoto2, e.g. libgphoto2-dev
 - pyzmq_
    - If installing pyzmq from PyPi, you must first install the development
      packages for libzmq3, e.g. libzmq3-dev
 - psutil_
 - sortedcontainers_
 - pyxdg_
 - Arrow_
 - dateutil_ 2.0 or greater
 - Qt5 plugin for reading TIFF images
 - If using Python 3.4, these additional modules:
    - typing_
    - scandir_

The following command will install all necessary requirements that can be satisified with the
built-in distribution packages on Ubuntu or Debian-like systems:

``sudo apt-get install libimage-exiftool-perl python3-pyqt5 python3-pip
python3-distutils-extra gir1.2-gexiv2-0.10 python3-gi gir1.2-gudev-1.0 gir1.2-udisks-2.0
gir1.2-notify-0.7 gir1.2-glib-2.0 gir1.2-gstreamer-1.0 libgphoto2-dev python3-sortedcontainers
python3-arrow python3-psutil qt5-image-formats-plugins python3-zmq exiv2``

After satisfying as many requirements as you can using your Linux distribution's standard package
installation tools, you may install Rapid Photo Downloader using the following steps, assuming
you use sudo to get super-user (root) access.

First, you may need to update your system's copy of pip and setuptools (optional):

``sudo python3 -m pip install --upgrade pip``

``sudo python3 -m pip install --upgrade setuptools``

**Caution:** the previous two steps will update pip and setuptools system-wide. This could
negatively affect the installation of other, older Python packages. If you don't want to do update
these two packages, and you are using Python 3.4 without a recent version of pip and setuptools,
you must manually install  python's typing and scandir modules:

``sudo python3 -m pip install typing scandir``

Be sure to have satisfied the build requirements listed above before running the following
command, substituting the name of the correct compressed tar file:

``sudo python3 -m pip install rapid-photo-downloader-0.9.0a1.tar.gz``

*Note: untarring the archive, building it and installing it using* ``sudo python3 setup.py
install`` *is not supported, and not recommended.*

Uninstalling
------------

Assuming you installed using the instructions above, run:

``sudo python3 -m pip uninstall rapid-photo-downloader``




.. _website: http://damonlynch.net/rapid
.. _Python gobject introspection: https://wiki.gnome.org/action/show/Projects/PyGObject
.. _python-gphoto2: https://github.com/jim-easterbrook/python-gphoto2
.. _pyzmq: https://github.com/zeromq/pyzmq
.. _psutil: https://github.com/giampaolo/psutil
.. _sortedcontainers: http://www.grantjenks.com/docs/sortedcontainers/
.. _pyxdg: https://www.freedesktop.org/wiki/Software/pyxdg/
.. _Arrow: https://github.com/crsmithdev/arrow
.. _dateutil: https://labix.org/python-dateutil
.. _typing: https://pypi.python.org/pypi/typing
.. _scandir: https://github.com/benhoyt/scandir



