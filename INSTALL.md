# Installing Rapid Photo Downloader from Source

Installation requires Python package dependencies that themselves depend on 
non-python programs to function. For example, `python-gphoto2` requires  
`libgphoto2`.

## Runtime dependencies

 - Python 3.10 or newer, and its development headers
 - [PyQt 5](https://riverbankcomputing.com/software/pyqt/intro)
 - [Qt 5](https://www.qt.io/)
 - [Qt5 plugin for reading TIFF images](http://doc.qt.io/qt-5/qtimageformats-index.html)
 - Qt5 plugin for rendering SVG
 - [setuptools](https://pypi.org/project/setuptools/)
 - [python-gphoto2 1.8.0](https://github.com/jim-easterbrook/python-gphoto2) or newer
 - [show-in-file-manager 1.1.2](https://github.com/damonlynch/showinfilemanager) or newer
 - [packaging](https://packaging.pypa.io/en/stable/)
 - [pyzmq](https://github.com/zeromq/pyzmq)
 - [tornado](http://www.tornadoweb.org/)
 - [psutil](https://github.com/giampaolo/psutil) 3.4.2 or newer
 - [pyxdg](https://www.freedesktop.org/wiki/Software/pyxdg/)
 - [Arrow](https://github.com/crsmithdev/arrow)
 - [dateutil](https://labix.org/python-dateutil) 2.2 or newer
 - [exiv2](http://www.exiv2.org/)
 - [ExifTool](http://www.sno.phy.queensu.ca/~phil/exiftool/)
 - [Colour](https://github.com/vaab/colour)
 - [pymediainfo](https://github.com/sbraz/pymediainfo)
 - [SortedContainers](http://www.grantjenks.com/docs/sortedcontainers/)
 - [Requests](http://docs.python-requests.org/)
 - [Tenacity](https://github.com/jd/tenacity)
 - [intltool](https://freedesktop.org/wiki/Software/intltool/)
 - [Babel](http://babel.pocoo.org/en/latest/)
 - [fuse](https://www.kernel.org/doc/html/latest/filesystems/fuse.html)
 - [imobiledevice-tools](https://libimobiledevice.org/)
 - [ifuse](https://libimobiledevice.org/)
 - [Python gobject introspection modules](https://wiki.gnome.org/action/show/Projects/PyGObject):
    - GUdev 1.0
    - UDisks 2.0
    - GLib 2.0
    - GExiv2 0.10
    - Gst 1.0
    - Notify 0.7
        
Recommended, optional dependencies:

 - [colorlog](https://github.com/borntyping/python-colorlog): generates coloured program output when
   running Rapid Photo Downloader from the terminal.
 - [pyheif](https://github.com/david-poirier-csn/pyheif): generate 
   thumbnails for HEIF / HEIC files (currently broken with recent releases 
   of [libheif](https://github.com/strukturag/libheif)).
 - [pillow](https://github.com/python-pillow/Pillow): work with HEIF / HEIC files

## Build dependencies

 - [Hatch](https://github.com/pypa/hatch)
 - [Hatch-gettext](https://github.com/damonlynch/hatch-gettext)
 - [Hatch-argparse-manpage](https://github.com/damonlynch/hatch-argparse-manpage)
 - `intltool`

## Building Rapid Photo Downloader

Run:
```bash
hatch build -t sdist
```

Running the build creates desktop integration files in the `share` folder 
(localization files do not need to be installed system-wide).  
