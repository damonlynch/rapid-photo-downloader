Release Notes for Rapid Photo Downloader 0.9.27b2
=================================================

 - To run Rapid Photo Downloader under WSLg on Windows 11, using the 
   [Windows Subsystem for Linux Preview](https://aka.ms/wslstorepage) from 
   the Microsoft Store is *strongly recommended*. Using the version of WSL that
   comes installed with Windows 11 can cause severe usability issues while 
   running programs like Rapid Photo Downloader. Read the documentation on Rapid
   Photo Downloader and WSL on the
   [program website](https://https://damonlynch.net/rapid/documentation/#wsl).

 - Rapid Photo Downloader 0.9.27b2 is the minimum version required to work with 
   Python 3.10. Earlier versions will not run properly, or more commonly will 
   not run at all.

 - PyQt5 5.15.6 is the minimum version required to work with Python 3.10. If 
   an older version is installed, Rapid Photo Downloader will run, but 
   thumbnails will not be generated.

 - Rapid Photo Downloader 0.9.19 introduced support for HEIF / HEIC files. The 
   documentation goes into details:

   https://damonlynch.net/rapid/documentation/#heifheic

 - Version 0.9.19 also introduced much improved support for high resolution
   displays. Consult the documentation to learn more:

   https://damonlynch.net/rapid/documentation/#highdpi

 - If thumbnailing fails to finish but no error is reported, that could indicate
   Exiv2 has crashed. See the documentation for how to resolve the problem:

   https://damonlynch.net/rapid/documentation/#miscellaneousnpreferences

 - Canon's latest RAW file format CR3 is supported on systems that have
   ExifTool 10.87 or newer. Some Linux distributions ship an older version
   of ExifTool. If you need to, it is fortunately easy to install ExifTool
   yourself. See:

   https://www.sno.phy.queensu.ca/~phil/exiftool/install.html

   Note: program performance with CR3 files is notably slower than other photo
   file formats. Other photo file formats are read using the high performance
   library Exiv2 to read metadata and extract thumbnails. Unfortunately Exiv2
   does not yet support the CR3 format. A future version of Exiv2 will support
   the CR3 format.

 - On some systems, Rapid Photo Downloader cannot use gstreamer to generate
   video thumbnails for all common video files. Install the good and libav
   plugins for gstreamer to solve this problem. In Debian and Ubuntu-like
   systems, the packages are gstreamer1.0-libav gstreamer1.0-plugins-good
   On Fedora, the packages are gstreamer1-plugins-good and gstreamer1-libav.
   Fedora users can enable the rpmfusion.org free repository to be able to
   install gstreamer1-libav.
