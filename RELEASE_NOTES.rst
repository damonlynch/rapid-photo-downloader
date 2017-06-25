Release Notes for Rapid Photo Downloader 0.9.0
==============================================

 - On certain Linux distributions the program's icons may be missing,
   including icons for menus. To resolve this problem, from the command line
   issue the following command:

   python3 -m pip install --user PyQt5

   This command will upgrade the version of PyQt and Qt for your user (the
   rest of the system will be unaffected). When Rapid Photo Downloader is next
   run, the icons should be displayed.

 - On some systems, Rapid Photo Downloader cannot use gstreamer to generate
   video thumbnails. These systems include Fedora 24 and Fedora 25, Ubuntu
   16.10 and 17.04, LinuxMint 18.1, and openSUSE 42.2 and openSUSE Tumbleweed.

 - On systems with version 0.18 of libraw, Rapid Photo Downloader cannot
   render thumbnails for raw images that don't have embedded thumbnails,
   such as DNG files from Android phones. Rapid Photo Downloader uses rawkit
   to interface with libraw, and rawkit 0.5.0 is incompatible with libraw
   0.18.

 - When running the program from the command line, if you see a message
   something like this:

   You are using pip version 8.1.1, however version 9.0.1 is available.
   You should consider upgrading via the 'pip install --upgrade pip' command.

   This message can be ignored. However, if you do want to upgrade pip, the
   safest way to upgrade is like this:

   python3 -m pip install --upgrade --user pip
