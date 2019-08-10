Release Notes for Rapid Photo Downloader 0.9.16
===============================================

 - Most photo thumbnails are generated using exiv2. Very rarely, exiv2 can
   cause a segfault (crash) while extracting a thumbnail. If exiv2 does
   segfault, currently Rapid Photo Downloader will currently fail to complete
   thumbnailing (the progress bar will never reach 100%) and will not report
   an error. A future release will address this problem. If you encounter
   such a situation, report a bug and if at all possible include a test photo
   that demonstrates the problem.

 - Canon's latest RAW file format CR3 is supported on systems that have
   ExifTool 10.87 or newer. Many Linux distributions ship an older version
   of ExifTool. If you need to, it is fortunately easy to install ExifTool
   yourself. See:

   https://www.sno.phy.queensu.ca/~phil/exiftool/install.html

   Note: program performance with CR3 files is notably slower than other photo
   file formats. Other photo file formats are read using the high performance
   library exiv2 to read metadata and extract thumbnails. Unfortunately exiv2
   does not yet support the CR3 format. Exiv2 0.28 will support the CR3 format.

 - If you installed Rapid Photo Downloader using the install script, you can
   update it one of two ways: using the install script again, or using the
   in-program update procedure. The in-program update procedure is very
   convenient, but faces limitations in terms of updating some of the software
   the program needs. If you use the install script to update the program, it
   can update more supporting packages, which can sometimes prove helpful.

 - On some systems, Rapid Photo Downloader cannot use gstreamer to generate
   video thumbnails for all common video files. Install the good and libav
   plugins for gstreamer to solve this problem. In Debian and Ubuntu-like
   systems, the packages are gstreamer1.0-libav gstreamer1.0-plugins-good
   On Fedora, the packages are gstreamer1-plugins-good and gstreamer1-libav.
   Fedora users can enable the rpmfusion.org free repository to be able to
   install gstreamer1-libav.

 - The Python library rawkit may not work with very recent versions of libraw.
   Rawkit uses libraw to generate thumbnails for RAW files from which a
   thumbnail cannot be extracted.

 - For systems running Python 3.6 or newer, the recommended pyzmq version is
   now 16.0.2 or newer. If xterm or lxterminal are installed on systems with
   Python 3.6 or newer, the automatic upgrade procedure will attempt to upgrade
   pymzq if necessary. On Python 3.6 or newer systems lacking either of these
   terminals, using the install.py script will upgrade pyzmq. Alternatively,
   the following command will upgrade pyzmq:

   /usr/bin/python3 -m pip install -U --user --disable-pip-version-check pyzmq

 - To install Rapid Photo Downloader on CentOS 7.5, first install Python 3.6
   from the  IUS Community repository:

   sudo yum -y install yum-utils
   sudo yum -y install https://centos7.iuscommunity.org/ius-release.rpm
   sudo yum -y install python36u python36u-setuptools

   Then run the install.py script:

   python3.6 install.py
