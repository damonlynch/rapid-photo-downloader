Release Notes for Rapid Photo Downloader 0.9.1
==============================================

 - On some systems, Rapid Photo Downloader cannot use gstreamer to generate
   video thumbnails for all common video files. Install the good and libav
   plugins for gstreamer to solve this problem. In Debian and Ubuntu-like
   systems, the packages are gstreamer1.0-libav gstreamer1.0-plugins-good
   On Fedora, the packages are gstreamer1-plugins-good and gstreamer1-libav.
   Fedora users can enable the rpmfusion.org free repository to be able to
   install gstreamer1-libav.

 - On systems with version 0.18 of libraw, Rapid Photo Downloader cannot
   render thumbnails for raw images that don't have embedded thumbnails,
   such as DNG files from Android phones. Rapid Photo Downloader uses rawkit
   to interface with libraw, and rawkit 0.5.0 is incompatible with libraw
   0.18.

