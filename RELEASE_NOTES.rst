Release Notes for Rapid Photo Downloader 0.9.19
===============================================

 - To be able to download HEIF / HEIC files, ExifTool 10.63 or newer is
   required. To be able to view their thumbnails, a version of Debian / Ubuntu
   or Fedora / CentOS that is is new enough to provide HEIF support libraries is
   required. Currently thumbnails for 10 bit HEIF files fail to render, but
   future releases of libheif and its Python module pyheif will support them.

   **Note:** HEIF / HEIC support is installed only if installing the program
   using the install.py script. If you have upgraded Rapid Photo Downloader from
   an earlier version using the program's builtin updater, HEIF / HEIC support
   will not be installed.

 - The install script and the the builtin program updater now automatically
   update pip, setuptools and wheel to the latest versions, but only for your
   user (i.e., not system-wide). They are updated because the latest versions
   are necessary to install PyQt5. If you previously relied on the system pip
   for your user, you can revert back to it with the following command (do not
   run as sudo):

   python3 -m pip uninstall --user pip

 - On high resolution screens (i.e. those with a high DPI setting) with screen
   scaling enabled, Rapid Photo Downloader will detect if special environment
   variables have been set that instruct Qt5 applications to scale their
   display. These environment variables are:

   - QT_SCALE_FACTOR
   - QT_SCREEN_SCALE_FACTORS
   - QT_AUTO_SCREEN_SCALE_FACTOR (Qt versions older than 5.14)
   - QT_ENABLE_HIGHDPI_SCALING (Qt versions 5.14 or newer)

   If none of these environment variables are set, Rapid Photo Downloader will
   automatically enable high DPI scaling. If they are set, Rapid Photo
   Downloader will do as they instruct. If for some reason you do not want this,
   set one of these variables before starting Rapid Photo Downloader.
   For details, consult:

   https://doc.qt.io/qt-5/highdpi.html#high-dpi-support-in-qt

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
