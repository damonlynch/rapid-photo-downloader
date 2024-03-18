Release Notes for Rapid Photo Downloader 0.9.36
===============================================

 - Rapid Photo Downloader 0.9.37 switches from `setuptools` and an old-school
   `setup.py` to using [Hatch](https://github.com/pypa/hatch).
   As part of this switch, localisation files are generated differently:
   - `.desktop` and `metainfo.xml` files are now generated at build time into 
     subfolders within the `share` folder.
   - `.mo` files are now generated within the folder `raphodo/locale`; they
      should not be copied to `/usr/share/locale`. Any 
     `rapid-photo-downloader.mo` files in `/usr/share/locale` should be 
     deleted. 

 - Further packaging changes include:
   - `pyrcc` is no longer used to generate images for the Qt resource system.
     Instead, images are stored in a new `raphodo/data` directory and loaded 
     using the Python resource system.
   - All source code now uses SPDX identifiers for copyright and licensing.  

 - Rapid Photo Downloader 0.9.35 requires Python 3.10 or newer.

 - To run Rapid Photo Downloader under WSLg on Windows 11, using the 
   [Windows Subsystem for Linux Preview](https://aka.ms/wslstorepage) from 
   the Microsoft Store is *strongly recommended*. Using the version of WSL that
   comes installed with Windows 11 can cause severe usability issues while 
   running programs like Rapid Photo Downloader. Read the documentation on Rapid
   Photo Downloader and WSL on the
   [program website](https://https://damonlynch.net/rapid/documentation/#wsl).

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
