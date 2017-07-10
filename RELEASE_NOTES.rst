Release Notes for Rapid Photo Downloader 0.9.1
==============================================

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

