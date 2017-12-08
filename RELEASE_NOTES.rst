Release Notes for Rapid Photo Downloader 0.9.6
==============================================

 - If you installed Rapid Photo Downloader using the install script, you can
   update it one of two ways: using the install script again, or using the
   built-in update procedure. The built-in update procedure is very
   convenient, but somtimes is limited in terms of what it can update. If you
   use the install script to update the program, it can update more supporting
   packages, which can sometimes prove helpful.

 - On some systems, Rapid Photo Downloader cannot use gstreamer to generate
   video thumbnails for all common video files. Install the good and libav
   plugins for gstreamer to solve this problem. In Debian and Ubuntu-like
   systems, the packages are gstreamer1.0-libav gstreamer1.0-plugins-good
   On Fedora, the packages are gstreamer1-plugins-good and gstreamer1-libav.
   Fedora users can enable the rpmfusion.org free repository to be able to
   install gstreamer1-libav.

 - With rawkit being updated to 0.6.0, and the addition of extra plugins to
   gstreamer, many photos and videos whose thumbnail could not previously be
   displayed now can be. However, to view those thumbnails for those files
   that have been previously scanned, purging the thumbnail cache is needed.
   You can purge the thumbnail cache via the Preferences dialog, accessed via
   the main menu.

 - For systems running Python 3.6, the recommended pyzmq version is now 16.0.2
   or newer. If xterm or lxterminal are installed on systems with Python 3.6,
   the automatic upgrade procedure will attempt to upgrade pymzq if necessary.
   On Python 3.6 systems lacking either of these terminals, using the
   install.py script will upgrade pyzmq. Alternatively, the following command
   will upgrade pyzmq:

   /usr/bin/python3 -m pip install -U --user --disable-pip-version-check pyzmq


