Release Notes for Rapid Photo Downloader 0.9.36
===============================================

 - To run Rapid Photo Downloader under WSLg on Windows 11, using the 
   [Windows Subsystem for Linux Preview](https://aka.ms/wslstorepage) from 
   the Microsoft Store is *strongly recommended*. Using the version of WSL that
   comes installed with Windows 11 can cause severe usability issues while 
   running programs like Rapid Photo Downloader. Read the documentation on Rapid
   Photo Downloader and WSL on the
   [program website](https://https://damonlynch.net/rapid/documentation/#wsl).

 - Rapid Photo Downloader 0.9.35 requires Python 3.10 or newer.

 - Rapid Photo Downloader 0.9.19 introduced support for HEIF / HEIC files. The 
   [documentation](https://damonlynch.net/rapid/documentation/#heifheic) 
   goes into details.

 - Version 0.9.19 also introduced much improved support for high-resolution
   displays. Consult the [documentation](https://damonlynch.net/rapid/documentation/#highdpi)
   to learn more.

 - If thumbnailing fails to finish but no error is reported, that could indicate
   Exiv2 has crashed. See the 
   [documentation]( https://damonlynch.net/rapid/documentation/#miscellaneousnpreferences)
   for how to resolve the problem:
 
 - On some systems, Rapid Photo Downloader cannot use gstreamer to generate
   video thumbnails for all common video files. Install the good and libav
   plugins for gstreamer to solve this problem. In Debian and Ubuntu-like
   systems, the packages are gstreamer1.0-libav gstreamer1.0-plugins-good
   On Fedora, the packages are gstreamer1-plugins-good and gstreamer1-libav.
   Fedora users can enable the rpmfusion.org free repository to be able to
   install gstreamer1-libav.
