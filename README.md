# Rapid Photo Downloader

[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

Rapid Photo Downloader is a Linux desktop application that imports photos 
and videos from cameras, phones, memory cards, and other devices at high 
speed. It is written by a [photographer](https://damonlynch.net) for 
professional and amateur photographers. 

![Main window screenshot](.github/mainwindow.png)

## Personal Note From the Developer

This project has only ever had one software developer. I developed a hand 
injury from typing while working on the code in early 2022. Code development 
has slowed considerably as I seek to recover from this serious injury. To 
work around the injury, fortunately I am able to use the JetBrains editor 
PyCharm in conjunction with the voice recognition tools Talon and Dragon 
NaturallySpeaking on Windows / WSL2. While my ability to test the code 
remains limited, at least I can write it.

I want to thank JetBrains for allowing me to use PyCharm Professional For 
free under their [open source developer program](https://www.jetbrains.com/community/opensource/#support). 

## Removal of the Install Script

Due to my hand injury (see above), I cannot maintain a custom `install.py` 
script that I used to provide &mdash; testing the script in the variety of 
Linux distributions it supports requires a lot of typing. The script is 
therefore removed.


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

Install the program using your Linux distribution's standard tools,
e.g., apt, dnf, or zypper.

The program is currently not available as a Snap or flatpak because to
interact with cameras it requires being able to break out of the 
confinement Snap and flatpak enforce. This may change in future if 
there are workarounds for this confinement.

Advanced users may install the program using pip. Please note doing so
requires satisfying dependencies that cannot be satisfied with pip alone.

### Software Requirements

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
