# Rapid Photo Downloader

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Rapid Photo Downloader is a Linux desktop application that imports photos 
and videos from cameras, phones, memory cards, and other devices at high 
speed. It is written by a [photographer](https://damonlynch.net) for 
professional and amateur photographers. 

![Main window screenshot](.github/mainwindow.png)

## Personal Note From the Developer

This project has only ever had one software developer. I developed a hand 
injury from typing while working on the code in early 2022. As such code
development has slowed considerably as I seek to recover from this serious 
injury. To work around the injury, I am using the JetBrains editor PyCharm 
in conjunction with the voice recognition tools Talon and Dragon 
NaturallySpeaking on Windows / WSL2. While this  notably restricts my 
ability to test the code, at least I can write it.

I want to thank JetBrains for allowing me to use PyCharm Professional For 
free under their [open source developer program](https://www.jetbrains.com/community/opensource/#support). 

## Depreciation of the Install Script

I cannot maintain the `install.py` script due to my hand injury (see above)
&mdash; testing the script in the variety of Linux distributions it supports
requires a lot of typing. The script is therefore depreciated and I do not 
recommend its use, especially on recent Linux distributions.


## User Survey 

If you have any experience with Rapid Photo Downloader at all, including if 
you no longer use it, please join hundreds of others by taking this survey: 

[Survey of past, current, and potential users](https://survey.rapidphotodownloader.com/)

The responses are already making a real difference to the program’s future 
development. The program collects no analytics whatsoever, so a survey like 
this is truly helpful. Thank you in advance.

## Program Features

 - Rename photos and videos with meaningful filenames you specify.
 - Download vast numbers of photos and videos with minimum fuss.
 - Back up photos and videos as they are downloaded.
 - Downloads from and backs up to multiple devices simultaneously.
 - Easy to configure and use.
 - Configure program preferences without the need for complicated codes.
 - Automate common tasks, such as unmounting a memory card when the download 
   is complete. 

[Read more about its features at the program website](https://damonlynch.net/rapid/features.html).

  
## Documentation

[Full documentation is available at the program website](https://damonlynch.net/rapid/documentation/).


## Program Design

Rapid Photo Downloader is coded in Python. To get the best performance using 
Python on modern multi-core computers, the program uses multiple OS-level 
processes that communicate with each other using the messaging library 
[0MQ](https://zeromq.org/).

[Learn more about the program's architecture](https://damonlynch.net/rapid/design.html).
  

## Issue Reporting

Report new issues on the
[developer's GitHub repository](https://github.com/damonlynch/rapid-photo-downloader/issues).

Historic issues are at the previous code repository,
[Launchpad](https://bugs.launchpad.net/rapid). 


## Releases

All project releases are hosted on the 
[project's Launchpad repository](https://launchpad.net/rapid/+download).


## Support

Get support at the [Pixls.us discussion forum](https://discuss.pixls.us/).


## Installation

An `install.py` script has been available for the past six years to install 
the latest version of the program. As discussed above, unfortunately I can no 
longer maintain this script.

The script is therefore depreciated and I do not recommend its use on 
anything but old Linux distributions.

Instead of using the depreciated `install.py` script, I recommend installing 
the program using your Linux distribution's standard repositories.

To consult the legacy instructions for using the depreciated `install.py` 
script, see the 
[documentation at the program's website](https://damonlynch.net/rapid/documentation/#installation).

### Software Requirements

 - Python 3.6 or newer, and its development headers
 - [PyQt 5](https://riverbankcomputing.com/software/pyqt/intro)
 - [Qt 5](https://www.qt.io/)
 - [Qt5 plugin for reading TIFF images](http://doc.qt.io/qt-5/qtimageformats-index.html)
 - Qt5 plugin for rendering SVG
 - [setuptools](https://pypi.org/project/setuptools/)
 - [python-gphoto2 1.4.0](https://github.com/jim-easterbrook/python-gphoto2) or newer
 - [show-in-file-manager 1.1.2](https://github.com/damonlynch/showinfilemanager) or newer
 - [importlib_metadata](https://github.com/python/importlib_metadata) on Python versions older than 3.8
 - [pyzmq](https://github.com/zeromq/pyzmq)
 - [tornado](http://www.tornadoweb.org/)
 - [psutil](https://github.com/giampaolo/psutil) 3.4.2 or newer
 - [pyxdg](https://www.freedesktop.org/wiki/Software/pyxdg/)
 - [Arrow](https://github.com/crsmithdev/arrow)
 - [dateutil](https://labix.org/python-dateutil) 2.2 or newer
 - [exiv2](http://www.exiv2.org/)
 - [ExifTool](http://www.sno.phy.queensu.ca/~phil/exiftool/)
 - [EasyGUI](https://github.com/robertlugg/easygui)  
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
        
Highly recommended, optional dependencies:

 - [colorlog](https://github.com/borntyping/python-colorlog): generates coloured program output when
   running Rapid Photo Downloader from the terminal.
 - [pyprind](https://github.com/rasbt/pyprind): shows a progress bar on the command line while 
   running the program analyze_pv_structure.
 - [pyheif](https://github.com/david-poirier-csn/pyheif): open HEIF / HEIC files
 - [pillow](https://github.com/python-pillow/Pillow): work with HEIF / HEIC files

## License

[GPL3 or later](https://choosealicense.com/licenses/gpl-3.0/).
