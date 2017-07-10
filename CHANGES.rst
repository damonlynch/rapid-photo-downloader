Changelog for Rapid Photo Downloader
====================================

0.9.1 (2017-07-10)
------------------

 - Add support for downloading, renaming and backing up log files, which can
   be associated with videos made using Magic Lantern.

 - Updated program AppData, renaming .desktop and .appdata.xml files to
   conform to reversed fully qualified domain name requirements.

 - Fixed bug in checking for new stable version.

 - Rearranged order of startup tasks to avoid rare bug where the user
   interface is not initialized before devices are handled.

 - Updated install script to automatically download latest version and
   run interactively only if asked to.

 - Updated install.py script to allow installation on Debian buster/sid.

 - Install PyQt5 from PyPi on x86_64 platforms with Python 3.5 or 3.6,
   avoiding segfaults on exit in Fedora and missing program icons in some
   Linux distributions.

 - To be able to generate video thumbnails for a wider range of video formats,
   on Debian-like Linux distributions and Fedora, where possible the
   install.py script installs the packages gstreamer-libav and
   gstreamer-plugins-good.

 - With rawkit 0.6.0 now supporting libraw 0.18, recent Linux distributions
   like Fedora 26 and Ubuntu 17.04 / 17.10 can now render thumbnails from
   raw files like DNG files produced by Android phones.

 - Updated Czech, French, German, Slovak and Spanish translations.

0.9.0 (2017-07-03)
------------------

 - Include additional programs in detailed version output.

 - Updated Turkish translation.

0.9.0b7 (2017-06-21)
--------------------

 - Don't attempt to download photos or videos of zero bytes length.

 - Updated Czech, French, Norwegian Bokmal, Japanese, Polish, Serbian, and
   Spanish translations.

0.9.0b6 (2017-06-13)
--------------------

 - Don't allow entry of illegal filename characters in Job Codes, such as
   / (forward slash).

 - Handle cameras that are mounted using libgphoto2's legacy connection method
   usbscsi.

 - Added warning message when ExifTool is not working.

 - Added GalliumOS to the list of Linux distros supported by the install.py.

 - Fixed bug where "Select a source folder" was displayed after rescanning
   a folder on This Computer.

 - Removed DistUtilsExtra from the list of dependencies by copying its
   core functionality into the setup.py file. This should make creating
   a Snap / AppImage / Flatpak easier.

 - Updated Arabic, Brazilian Portuguese, Catalan, Chinese, Czech, Danish,
   Dutch, French, Italian, Japanese, Kabyle, Norwegian Bokmal, Serbian,
   Slovak, Spanish, Swedish, and Ukrainian translations.

0.9.0b5 (2017-05-10)
--------------------

 - Added a Tip of the Day dialog.

 - Fixed bug where rendering destination storage space would crash when the
   destination device's storage space is reported as zero bytes in size.

 - Fixed bug where install.py could get into an infinitely recurring state
   when the Linux distribution is is Linux Mint, but /etc/os-release wrongly
   identifies it as Ubuntu.

0.9.0b4 (2017-05-04)
--------------------

 - Added Help buttons to Program Preferences and File Renaming and Download
   Subfolder Generator editors that open the online documentation.

 - Added command line option to dump to the terminal basic information about
   attached cameras, which is useful for diagnosing potential problems with
   libgphoto2 and python-gphoto2.

 - Added dialog to inform user if the scan process had an unexpected fatal
   problem.

 - Added link to Changelog in dialog window notifying a new release is
   available.

 - Fixed bug on systems using Python 3.4 (such as openSUSE Leap 42.2) when
   creating a temporary directory during program upgrade.

 - Fixed bug where exception would occur when auto exit after download was
   activated.

 - Re-scan download sources after relevant program preference changes.

0.9.0b3 (2017-04-15)
--------------------

 - Fixed bug where a warning dialog window could be wrongly issued about a
   backup destination not being writable even though it though it is.

 - Fixed bug where tracking of bytes downloaded could occasionally fail when
   file copy errors were encountered.

 - Improved logging of file copy problems.

 - Fixed some translation bugs. Thanks to Jose Luis Tirado for pointing them
   out.

 - Updated Spanish and Czech translations, by Jose Luis Tirado and Pavel
   Borecki.

0.9.0b2 (2017-04-04)
--------------------

 - Fixed bug where installer would crash on Ubuntu when the Universe
   repository was not enabled.

 - Fixed bug to allow the error report window to run on versions of PyQt5
   older than 5.6.

 - Implemented workarounds for several bugs in openSUSE GExiv2 introspection.

 - Fixed bug when comparing Enums on Python 3.4.

 - Fixed bug when reporting a file renaming problem in the error reporting
   window.

 - When running on the Unity 7 desktop, show count and download progress
   regardless of whether the .desktop file has hyphens or underscores.

0.9.0b1 (2017-04-01)
--------------------

 - Improved install.py script, adding openSUSE and the Fedora derivative
   Korora to list of supported distros. Moreover, the script now installs
   all program requirements without having to be manually restarted.

 - Implemented error report window. Error reports are now grouped by task:
   scanning a device, copying from a device, finalizing download subfolder and
   filenames, and backing up. Furthermore, reports now contain hyperlinks to
   the files on the filesystem and/or cameras, allowing easy access to them
   using a file manager.

 - A message dialog window is now displayed if back ups will not occur or if
   the download destinations have a problem.

 - Added 'Program Warnings' section to the preferences dialog window.

 - Optimized icon sizes in dialog windows.

 - Check for new version using secure connection.

 - Added an option to issue a warning if a file type unknown to the program is
   found on a download device.

 - Added an option to program preferences dialog to ignore DNG date/time
   metadata when downloading from MTP devices (like cellphones and tablets).
   When it is ignored, the DNG file's modification time is used instead. Many
   (if not all) Android 6 and 7 devices create bogus DNG metadata values.
   Since the first alpha release, by default the program ignores the DNG
   date/time metadata when downloading from MTP devices.

 - Changed the count that appears above the program's icon when running on the
   Unity desktop to show how many files are checked for download, instead of
   how many new files are available for download.

 - Fixed a bug where device scan would indicate a device was empty when the
   preference value 'Ignored Paths on Devices' contained no paths to ignore.

 - Fixed a bug where opening a file on an MTP device in a file browser would
   sometimes fail when the storage name component of the path was incorrectly
   identified.

 - Fixed bug where the case of the extension for XMP files, THM files and WAV
   files was not matching file renaming preferences.

0.9.0a11 (2017-03-08)
---------------------

 - Added dialog to configure program preferences.

 - Added progress bar to splash screen.

 - Fixed bug where URIs with spaces were not opening in the system file
   browser.

 - Minimized width required by Job Code and Backup, and Rename configuration
   panels.

 - Fixed detection of Unity desktop environment when desktop environment
   variable is set to 'Unity:Unity7'

 - Disabled the use of the scrollwheel to insert preference values in the file
   and subfolder name editors.

0.9.0a10 (2017-03-02)
---------------------

 - Implement the user interface to enter Job Codes. Job Codes are now easier
   to assign compared to previous versions of Rapid Photo Downloader. You can
   assign Job Codes to sets of photos and/or videos before starting the
   download. That way you can efficiently apply a variety of Job Codes to
   different sets of photos and videos in the same download. Job codes are
   shown in the upper portion of each thumbnail.

 - Added Run button to upgrade dialog window that is shown when the program
   was successfully upgraded.

 - Fixed bug where a crash would occur after using the "Clear Completed
   Downloads" menu option.

 - Fixed bug where selecting a different part of the timeline did not
   always update which thumbnails should be selected. (The values in the Photo
   and Video "Select All" check boxes at the bottom right of the main window
   determine if a thumbnail should be selected or not).

 - Fixed bug in file renaming and subfolder name editors when running
   under PyQt 5.8 / Qt 5.8.

 - In systems where ExifTool is not installed, inform user via
   error message at startup, and abort.

 - In systems where libmediainfo is not installed, a warning message is
   displayed after program startup.

 - Added preliminary Greek translation, thanks to Dimitris Xenakis.

0.9.0a9 (2017-02-21)
--------------------

 - Fix bug #1665879: Work-around an unexpected signal/slot problem with Qt on
   Fedora 25.

0.9.0a8 (2017-02-16)
--------------------

 - Display projected backup storage use in the Backup configuration panel, for
   each backup device (partition). If backing up to the same device as the
   download, the space taken by both the download and the backup is displayed.
   For example, supposing you are downloading 100 photos that use 2,000 MB of
   storage space to /home/user/Pictures, and you are backing them up to
   another folder in the same partition, the projected backup storage use for
   that partition will display 100 photos totalling 4,000 MB, because the
   partition will contain two copies of each photo. Likewise, the projected
   storage use in the download destinations is similarly adjusted.

 - Renamed 'Storage Space' in Destination configuration panel to 'Projected
   Storage Use', thereby more accurately describing what it displays.

 - Disallow download if there is insufficient space on any of the backup
   devices, like is already done for the download destinations.

 - Added right-click context menu to file system tree views with the option
   to open the file browser at the path that was right-clicked on.

 - Fixed a bug in the subfolder and file renaming editors to the stop the
   message area being scrolled out of view.

 - Fixed a bug where backup worker processes were never stopped until program
   exit.

 - Fixed a bug where pausing and resuming a download was not updated to match
   changes to threading made in version 0.9.0a7.

 - Updated install script to allow for quirks in LinuxMint and KDE Neon.

 - Updated Spanish, French and Italian translations.


0.9.0a7 (2017-01-31)
--------------------

 - Added backup configuration to the user interface. A future alpha release
   will show the backup destinations like they are shown in the Destinations
   tab.

 - A check for a new version is run at program startup. If the program was
   installed using python's packaging system pip, and the latest version can
   be upgraded without new system dependencies, the program offers to download
   the new version and install it with minimal user intervention.

 - The graphical user interface is considerably more responsive when the
   program is under heavy load because of changes made in the ways helper
   threads are handled by the main window. Long-term program stability will
   also be improved, although in the short-term some bugs may have snuck in
   due to the threading changes.

 - Prompt for Job Code when file and folder naming preferences are changed to
   include it. Thanks to Monty Taylor for the fix.

 - Fixed bug #1656932: in certain circumstances the scan process could crash
   when trying to determine device time zones when examining sample photos and
   videos.

 - Fixed a bug too small of a portion of a .mov or .avi file from a camera or
   phone was being extracted in order to read video metadata.

 - Fixed a bug where thumbnails were not being rendered in the main window
   when the thumbnail was originally sourced from the Freedesktop.org
   thumbnail cache.

 - Disallow the running of the program as the root user.

 - Updated program installer to stop installation on Fedora 23 and Debian
   Jessie.

 - Corrected error in Spanish translation that caused crash when download
   started.

 - Refined detection of directory in which media are mounted (/media or
   /run/media).

0.9.0a6 (2016-12-10)
--------------------

 - Modified installation script to fix installation problems on Fedora 25 and
   LinuxMint 18. In all other respects the release is identical to version
   0.9.0a5.

0.9.0a5 (2016-11-14)
--------------------

 - Implemented photo and video file renaming preference configuration. Job code
   configuration will be implemented in a future alpha release.

 - Fixed crash when running on PyQt 5.7.

 - Added option to uninstall previous version of the program if running the
   install script on Debian/Ubuntu or Fedora like Linux distributions.

 - Added .m2ts video extension to supported video files.

 - Added tooltip to clarify meaning of storage space usage.

 - Added g++ to list of installation dependencies when installing on Debian
   derived distributions.

 - Only enable right-click menu option 'Open in File Browser...' when default
   file manager is known.

 - Handle use case where the path from which to download is passed on the
   command line without a command line switch, such as when Gnome launches the 
   program in response to a device like a memory card containing photos being 
   inserted.

 - Fixed bug where volumes where not correctly added to device white and 
   blacklists.

 - Fixed bug where download conflict resolution preference value was being
   incorrectly set when importing preferences from version 0.4.11 or earlier.

 - Fixed bug where generating thumbnails for backed up files caused the backup 
   process to crash.

 - Fixed crash where the library libmediainfo is not installed but the python 
   package pymediainfo is.

 - Fixed generation of error message when there is an error copying file to a 
   backup destination.

 - Fixed crash at startup bug when the Pictures or Videos XDG special directory 
   was not set.

 - Fixed bug when selecting custom subfolder name generation preset from menu.

 - Fixed bug where ExifTool daemon processes were not always being terminated.

 - Added minimum size in bytes to read a variety of RAW and video metadata tags 
   to analyze-pv-structure analysis.

 - Fixed bug where QFileSystemWatcher.removePaths() could be called with an 
   empty directory list.

 - Fixed crash when cleaning generated video subfolder previews at program exit.

 - Updated Spanish translation, courtesy of Jose Luis Tirado. Also updated 
   Catalan, Chinese, Croatian, Czech, French, German, Polish and Serbian 
   translations.

0.9.0a4 (2016-06-22)
--------------------

 - Implemented photo and video subfolder generation preference configuration.

 - Fixed bug where translation of user interface into non-English languages was
   not occurring.

 - Fixed bug where input/output exception not being handled when probing mounts.

 - Fixed bug where crashed on startup when no desktop environment variable was 
   set.

 - Fixed bug where crashed on startup when attempting to import the broken 
   Python package EasyGui 0.98.

0.9.0a3 (2016-05-27)
--------------------

 - Selecting items in the Timeline or showing only new files can result in
   situations where there are files that have been checked for download that are
   not currently being displayed. In such a situation, when a download is 
   started, a dialog will be displayed to warn that *all* checked files will be 
   downloaded, not merely those currently displayed.

 - Changed heading of destination storage space to show projected bytes free
   instead of percent used.

 - Fixed bug where thumbnails might not be displayed for files that had
   already been downloaded during a previous progarm invocation.

 - If the environment variable RPD_SCAN_DEBUG is set to any value, the
   program's scan operation will output voluminous debug information to stdout.

 - Added support for PyQt 5.6, namely its stricter rules regarding signal type
   matching.

 - Fixed bug when reporting inability to extract metadata from scan when not
   downloading from a camera

0.9.0a2 (2016-05-16)
--------------------

 - Added command line option to import preferences from from an old program
   version (0.4.11 or earlier).

 - Implemented auto unmount using GIO (which is used on most Linux desktops) and
   UDisks2 (all those desktops that don't use GIO, e.g. KDE).

 - Fixed bug while logging processes being forcefully terminated.

 - Fixed bug where stored sequence number was not being correctly used when
   renaming files.

 - Fixed bug where download would crash on Python 3.4 systems due to use of 
   Python 3.5 only math.inf

0.9.0a1 (2016-05-14)
--------------------

 - New features compared to the previous release, version 0.4.11:

   - Every aspect of the user interface has been revised and modernized.

   - Files can be downloaded from all cameras supported by gPhoto2,
     including smartphones. Unfortunately the previous version could download
     from only some cameras.

   - Files that have already been downloaded are remembered. You can still
     select previously downloaded files to download again, but they are
     unchecked by default, and their thumbnails are dimmed so you can 
     differentiate them from files that are yet to be downloaded.

   - The thumbnails for previously downloaded files can be hidden.

   - Unique to Rapid Photo Downloader is its Timeline, which groups photos and
     videos based on how much time elapsed between consecutive shots. Use it
     to identify photos and videos taken at different periods in a single day
     or over consecutive days. A slider adjusts the time elapsed between
     consecutive shots that is used to build the Timeline. Time periods can be
     selected to filter which thumbnails are displayed.

   - Thumbnails are bigger, and different file types are easier to
     distinguish.

   - Thumbnails can be sorted using a variety of criteria, including by device
     and file type.

   - Destination folders are previewed before a download starts, showing which
     subfolders photos and videos will be downloaded to. Newly created folders
     have their names italicized.

   - The storage space used by photos, videos, and other files on the devices
     being downloaded from is displayed for each device. The projected storage
     space on the computer to be used by photos and videos about to be
     downloaded is also displayed.

   - Downloading is disabled when the projected storage space required is more
     than the capacity of the download destination.

   - When downloading from more than one device, thumbnails for a particular
     device are briefly highlighted when the mouse is moved over the device.

   - The order in which thumbnails are generated prioritizes representative
     samples, based on time, which is useful for those who download very large
     numbers of files at a time.

   - Thumbnails are generated asynchronously and in parallel, using a load
     balancer to assign work to processes utilizing up to 4 CPU cores.
     Thumbnail generation is faster than the 0.4 series of program
     releases, especially when reading from fast memory cards or SSDs.
     (Unfortunately generating thumbnails for a smartphone's photos is painfully
     slow. Unlike photos produced by cameras, smartphone photos do not contain
     embedded preview images, which means the entire photo must be downloaded
     and cached for its thumbnail to be generated. Although Rapid Photo 
     Downloader does this for you, nothing can be done to speed it up).

   - Thumbnails generated when a device is scanned are cached, making thumbnail
     generation quicker on subsequent scans.

   - Libraw is used to render RAW images from which a preview cannot be 
     extracted, which is the case with Android DNG files, for instance.

   - Freedesktop.org thumbnails for RAW and TIFF photos are generated once they
     have been downloaded, which means they will have thumbnails in programs
     like Gnome Files, Nemo, Caja, Thunar, PCManFM and Dolphin. If the path 
     files are being downloaded to contains symbolic links, a thumbnail will be 
     created for the path with and without the links. While generating these 
     thumbnails does slow the download process a little, it's a worthwhile
     tradeoff because Linux desktops typically do not generate thumbnails for 
     RAW images, and thumbnails only for small TIFFs.

   - The program can now handle hundreds of thousands of files at a time.
     
   - Tooltips display information about the file including name, modification
     time, shot taken time, and file size.
     
   - Right click on thumbnails to open the file in a file browser or copy the
     path.
     
   - When downloading from a camera with dual memory cards, an emblem beneath
     the thumbnail indicates which memory cards the photo or video is on

   - Audio files that accompany photos on professional cameras like the Canon
     EOS-1D series of cameras are now also downloaded. XMP files associated with
     a photo or video on any device are also downloaded.

   - Comprehensive log files are generated that allow easier diagnosis of
     program problems in bug reports. Messages optionally logged to a
     terminal window are displayed in color.

   - When running under Ubuntu's Unity desktop, a progress bar and count of 
     files available for download is displayed on the program's launcher.

   - Status bar messages have been significantly revamped.

   - Determining a video's  correct creation date and time has  been improved,
     using a combination of the tools MediaInfo and ExifTool. Getting the right 
     date and time is trickier than it might appear. Depending on the video file
     and the camera that produced it, neither MediaInfo nor ExifTool always give
     the correct result. Moreover some cameras always use the UTC time zone when
     recording the creation date and time in the video's metadata, whereas other
     cameras use the time zone the video was created in, while others ignore
     time zones altogether.

   - The time remaining until a download is complete (which is shown in the 
     status bar) is more stable and more accurate. The algorithm is modelled on 
     that used by Mozilla Firefox.

   - The installer has been totally rewritten to take advantage of Python's
     tool pip, which installs Python packages. Rapid Photo Downloader can now
     be easily installed and uninstalled. On Ubuntu, Debian and Fedora-like
     Linux distributions, the installation of all dependencies is automated.
     On other Linux distrubtions, dependency installation is partially
     automated.

   - When choosing a Job Code, whether to remember the choice or not can be
     specified.

 - Removed feature:
 
   - Rotate Jpeg images - to apply lossless rotation, this feature requires the
     program jpegtran. Some users reported jpegtran corrupted their jpegs' 
     metadata -- which is bad under any circumstances, but terrible when applied
     to the only copy of a file. To preserve file integrity under all 
     circumstances, unfortunately the rotate jpeg option must therefore be 
     removed.
   
 - Under the hood, the code now uses:

   - PyQt 5.4 +

   - gPhoto2 to download from cameras

   - Python 3.4 +

   - ZeroMQ for interprocess communication

   - GExiv2 for photo metadata

   - Exiftool for video metadata

   - Gstreamer for video thumbnail generation

 - Please note if you use a system monitor that displays network activity,
   don't be alarmed if it shows increased local network activity while the
   program is running. The program uses ZeroMQ over TCP/IP for its
   interprocess messaging. Rapid Photo Downloader's network traffic is
   strictly between its own processes, all running solely on your computer.
   
 - Missing features, which will be implemented in future releases:
  
   - Components of the user interface that are used to configure file
     renaming, download subfolder generation, backups, and miscellaneous
     other program preferences. While they can be configured by manually
     editing the program's configuration file, that's far from easy and is
     error prone. Meanwhile, some options can be configured using the command
     line.

   - There are no full size photo and video previews.
   
   - There is no error log window.

   - Some main menu items do nothing.

   - Files can only be copied, not moved.

0.4.11 (2015-10-22)
-------------------

 - Updated Brazilian, Catalan, Croatian, Czech, German, Japanese, Norwegian, 
   Polish, Portuguese and Swedish translations.
   
 - Fixed crash on systems using the library Pillow 3.0.
   
 - Updated AppData file.

0.4.10 (2014-02-23)
-------------------

 - Updated Catalan and Portuguese translations.
   
 - Fixed bug in translations for term "Back up".

0.4.9 (2014-01-21)
------------------

 - Updated Catalan and Spanish translations.
   
 - Fixed occasional incorrect use of term "backup".

0.4.9b3 (2014-01-20)
--------------------

 - Fixed packaging bug.

0.4.9b2 (2014-01-20)
--------------------

 - Added file verification of downloaded and backed up files.
   
 - Updated Dutch, Hungarian, Italian, Polish, Serbian, Spanish and Swedish 
   translations. Added Catalan translation.

0.4.9b1 (2014-01-16)
--------------------

 - Fixed bugs #1025908 and #1186955: Finalize fix for severe performance 
   problems and crashes that arose from the combination of Gnome's GIO file
   functionality and python's multiprocessing. The solution was to remove GIO 
   and replace it with regular python file processing. A nice side effect is 
   that the program now runs faster than ever before.
   
 - Fixed bug #1268291: Handle cases where filesystem metadata (e.g. file 
   permissions) could not be copied when writing to certain file systems such as
   NTFS. The program will now consider a file is copied succesfully even if the
   filesystem metadata could not be updated.
   
 - Fixed bug #1269032: When Sync RAW + JPEG sequence numbers is enabled, the 
   program fails to properly deal with photos with corrupt EXIF metadata.
   
 - Fixed bug #1269079: Download failure when folder exists for only one of photo
   or video on auto detected back devices. 
   
 - Updated Norwegian and Serbian translations.

0.4.8 (2013-12-31)
------------------

 - Fixed bug #1263237: Added support for MPO files (3D images). Thanks to Jan 
   Kaluza for reporting it.
   
 - Fixed bug #1263483: Some terms in the user interface are not being 
   translated. Thanks to Jose Luis Tirado for alerting me to the problem, which 
   has probably existed for some time.
   
 - Updated Dutch, French Italian, Polish and Spanish translations.

0.4.7 (2013-10-19)
------------------

 - Added feature to download audio files that are associated with photos such as
   those created by the Canon 1D series of cameras.
   
 - Fixed bug #1242119: Choosing a new folder does not work in Ubuntu 13.10. In
   Ubuntu 13.10, choosing a destination or source folder from its bookmark does 
   not work. The correct value is displayed in the file chooser button, but this
   value is not used by Rapid Photo Downloader.
   
 - Fixed bug #1206853: Crashes when system message notifications not functioning
   properly.
   
 - Fixed bug #909405: Allow selections by row (and not GTK default by square) 
   when user is dragging the mouse or using the keyboard to select. Thank you to
   user 'Salukibob' for the patch.
   
 - Added a KDE Solid action. Solid is KDE4's hardware-related framework. It 
   detects when the user connects a new device and display a list of related 
   actions. Thanks to dju` for the patch.
   
 - Added Belarusian translation -- thanks go to Ilya Tsimokhin. Updated Swedish 
   and Ukrainian translations.

0.4.6 (2013-01-22)
------------------

 - Fixed bug #1083756: Application shows duplicate sources.

 - Fixed bug #1093330: Photo rename ignores SubSeconds when 00.
   
 - Added extra debugging output to help trace program execution progress.
   
 - Updated German and Spanish translations.

0.4.6b1 (2012-11-26)
--------------------

 - Fixed bug #1023586: Added RAW file support for Nikon NRW files. Rapid Photo
   Downloader uses the exiv2 program to read a photo's metadata. Although the 
   NRW format is not officially supported by exiv2, it appears to work. If you 
   have NRW files and Rapid Photo Downloader crashes while reading this files, 
   please file a bug report.
   
 - Preliminary and tentative fix for bug #1025908: Application freezes under
   Ubuntu 12.10. This fix should not be considered final, and needs further 
   testing.
   
 - Added Arabic translation. Updated Czech, Danish, French, Italian, Norwegian, 
   Russian, Serbian, Spanish and Swedish translations.
   
 - Fixed missing dependencies on python-dbus and exiv2 in Debian/control file.
   
 - Added extra debugging output to help trace program execution progress.

0.4.5 (2012-06-24)
------------------

 - Updated Dutch, Estonian, German, Italian, Norwegian and Polish translations.
   
 - Updated man page.

0.4.5b1 (2012-06-17)
--------------------

 - To increase performance, thumbnails are now no longer displayed until all 
   devices have finished being scanned. To indicate the scan is occurring, the
   progress bar now pulses and it displays a running total of the number of 
   photos and videos found. If scanning a very large number of files from a fast
   device, the progress bar may pause. If this happens, just wait for the scan 
   to complete.
   
 - Fixed bug #1014203: Very poor program performance after download device 
   changed. The program now displays the results of scanning files much quicker 
   if the program's download device preferences are changed and a scan begins of
   a new device. 
   
 - You can now specify via the command line whether you would like to 
   automatically detect devices from which to download, or manually specify the 
   path of the device. If specified, the option will overwrite the existing 
   program preferences.
   
 - Added extra information to debugging output.
   
 - Fixed bug #1014219: File Modify process crashes if program exits during 
   download. 

0.4.4 (2012-05-30)
------------------

 - Fixed bug #998320: Applied patch from Dmitry Kazimirov for option to have 
   subfolder generation and file renaming use a month in text format. Thanks
   Dmitry!
   
 - Fixed bug #986681: Crash when showing question dialog on some non-Gnome 
   systems. Thanks go to Liudas Ališauskas for the suggested fix.
   
 - Fixed bug #995769: The Help button in the preferences dialog does not work.
   
 - Fixed bug #996613: Updated Free Software Foundation address.
   
 - Added Estonian translation. Updated Brazilian, Dutch, French, German, 
   Norwegian Bokmal, Polish, Spanish and Russian translations.

0.4.3 (2012-01-07)
------------------

 - ExifTool is now a required dependency for Rapid Photo Downloader. ExifTool
   can be used to help download videos on Linux distributions that have not
   packaged hachoir-metadata, such as Fedora.
   
 - Exiftran is another new dependency. It is used to automatically rotate 
   JPEG images. 
   
 - Fixed bug #704482: Delete photos option should be easily accessible -
   
 - Added a toolbar at the top of the main program window, which gives immediate
   access to the most commonly changed configuration options: where files will
   be transferred from, whether they will be copied or moved, and where they 
   will be transferred to.
   
 - Please when the move option is chosen, all files in the download from a 
   device are first copied before any are deleted. In other words, only once all
   source files have been successfully copied from a device to their destination
   are the source files deleted from that device.
   
 - Fixed bug #754531: extract Exif.CanonFi.FileNumber metadata -
   
 - Added FileNumber metadata renaming option, which is a Canon-specific Exif 
   value in the form xxx-yyyy, where xxx is the folder number and yyyy is the 
   image number. Uses ExifTool. Thanks go to Etieene Charlier for researching 
   the fix and contributing code to get it implemented.
   
 - Fixed bug #695517: Added functionality to download MTS video files. There is
   currently no python based library to read metadata from MTS files, but 
   ExifTool works. 
   
 - Fixed bug #859998: Download THM video thumbnail files -
   
 - Some video files have THM video thumbnail files associated with them. Rapid 
   Photo Downloader now downloads them and renames them to match the name of the
   video it is associated with.
   
 - Fixed bug #594533: Lossless JPEG rotation based on EXIF data after picture 
   transfer -
   
 - There is now an option to automatically rotate JPEG photos as they are
   downloaded. The program exiftran is used to do the rotation. The feature is
   turned on default. 
   
 - Fixed bug #859012: Confirm if really want to download from /home, /media or / 
   
 - It is possible for the program's preferences to be set to download from 
   /home, /media or / (the root of the file system). This can result in the 
   program scanning a very large number of files, possibly causing the system to 
   become unresponsive. The program now queries the user before commencing this 
   scan to confirm if this is really what they want to do.
   
 - Fixed bug #792228: clear all thumbnails when refresh command issued.
   
 - Fixed bug #890949: Panasonic MOD format and duplicate filename issue
   
 - Fixed a bug where the device progress bar would occasionally disappear when 
   the download device was changed. 
   
 - Fixed a bug where the file extensions the program downloads could not be
   displayed from the command line.
   
 - Fixed a bug where the program would crash when trying to convert a malformed
   thumbnail from one image mode to another.
   
 - Updated Czech, Danish, Dutch, French, German, Hungarian, Italian, Norwegian,
   Polish, Serbian, Slovak, Spanish and Swedish translations.

0.4.2 (2011-10-01)
------------------

 - Added feature in Preferences window to remove any paths that have previously
   been marked to always be scanned or ignored. These paths can be specified 
   when automatic detection of Portable Storage Devices is enabled.
   
 - Fixed bug #768026: added option to ignore paths from which to download - 
   
 - You can now specify paths never to scan for photos or videos. By default, any 
   path ending in .Trash or .thumbnails is ignored.  Advanced users can specify
   paths to never scan using python-style regular expressions.
   
 - Fixed bug #774488: added manual back up path for videos, in addition to 
   photos
   
 - You can now manually specify a path specifically in which to back up videos. 
   This can be the same as or different than the path in which to back up 
   photos.
   
 - Fixed bug #838722: wrong file types may be backed up to external devices
   
 - Fixed a bug when auto detection of backup devices is enabled, files of the
   wrong type might be backed up. For instance, if the backup device is only 
   meant to store videos, and the download contains photos, photos would 
   incorrectly be backed up to the device in addition to videos.
   
 - Fixed bug #815727: Back up errors and warnings incorrectly displayed in log 
   window -
   
 - Fixed a bug that occurred when backing up errors are encountered, the log 
   window did not display them correctly, although they were correctly outputted
   to the terminal window. This only occurred when more than one back up device 
   was being used during a download.
   
 - Fixed bug #859242: Crash when displaying a preview of file without an 
   extracted thumbnail.
   
 - Fixed bug #810559: Crash when generating thumbnail images
   
 - Fixed bug #789995: crash when --reset-settings option is given on the command 
   line.
   
 - Fixed bugs #795446 and #844714: small errors in translation template.
   
 - Fixed a bug in the Swedish translation. 
   
 - Added Danish translation, by Torben Gundtofte-Bruun. Updated Brazilian, 
   Czech, Dutch, French, German, Hungarian, Italian, Japanese, Norwegian, 
   Polish, Russian,  Serbian, Slovak, Spanish, Swedish and Turkish translations.

0.4.1 (2011-05-19)
------------------

 - Added exif Artist and Copyright metadata options to file and subfolder name
   generation.
   
 - Fixed bug #774476: thumbnails occasionally not sorted by file modification
   time.
   
 - Fixed bug #784399: job code not prompted for after preference change.
   
 - Fixed bug #778085: crash when trying to scan inaccessible files on mounted
   camera.
   
 - Relaxed startup test to check whether pynotify is working. On some systems,
   pynotify reports it is not working even though it is.
   
 - Added the start of an Indonesian translation. Updated Brazilian, Dutch, 
   French, German, Hungarian, Italian, Polish, Russian, Spanish and Ukrainian 
   translations.

0.4.0 (2011-04-28)
------------------

 - Features added since Release Candidate 1:
   
   * Allow multiple selection of files to check or uncheck for downloading.
   * Automation feature to delete downloaded files from a device.
   
 - Bug fix: translation fixes.
   
 - Bug fix: don't crash when completing download with backups enabled and no 
   backup devices detected.
   
 - Updated Dutch, French, German, Polish, Russian, Serbian and Spanish 
   translations.

0.4.0rc1 (2011-04-21)
---------------------

 - Features added since beta 1:
   
    - Backups have been implemented. If you are backing up to more than one 
      device, Rapid Photo Downloader will backup to each device simultaneously 
      instead of one after the other.
      
    - When clicking the Download button before thumbnails are finished 
      generating, the download proceeds immediately and the thumbnails remaining
      to be generated will rendered during the download itself.
      
    - Added preferences option to disable thumbnail generation. When auto start 
      is enabled, this can speed-up transfers when downloading from high-speed 
      devices.
      
    - Access to the preferences window is now disabled while a download is
      occurring, as changing preferences when files are being download can cause
      problems.
      
 - Bug fix: don't crash when downloading some files after having previously 
   downloaded some others in the same session.
   
 - Updated Brazilian, Dutch, German and Russian translations.

0.4.0b1 (2011-04-10)
--------------------

 - Features added since alpha 4:
   
   - Job Code functionality, mimicking that found in version 0.2.3.

   - Eject device button for each unmountable device in main window.

   - When not all files have been downloaded from a device, the number remaining
     is displayed in the device's progress bar

   - Overall download progress is displayed in progress bar at bottom of window

   - Time remaining and download speed are displayed in the status bar

   - System notification messages

   - Automation features:

       - Automatically start a download at program startup or when a device is
         inserted. When this is enabled, to optimize performance instead of
         thumbnails being generated before the files are downloaded, they are
         generated during the download.

       - Eject a device when all files have been downloaded from it.

       - Exit when all files have been downloaded.
   
 - The automation feature to delete downloaded files from a device will be added 
   only when the non-alpha/beta of version 0.4.0 is released.
   
 - The major feature currently not implemented is backups.
   
 - Note: if videos are downloaded, the device may not be able to be unmounted
   until Rapid Photo Downloader is exited. See bug #744012 for details.
   
 - Bug fix: adjust vertical pane position when additional devices are inserted

 - Bug fix: display file and subfolder naming warnings in error log
  
 - Updated Czech, French and Russian translations.

0.3.6 (2011-04-05)
------------------

 - This release contains a minor fix to allow program preferences to be changed
   on upcoming Linux distributions like Ubuntu 11.04 and Fedora 15. 
   
 - It also contains a minor packaging change so it can be installed in Ubuntu 
   11.04.

0.4.0a4 (2011-04-04)
--------------------

 - Fixed bug #750808: errorlog.ui not included in setup.py.

0.4.0a3 (2011-04-04)
--------------------

 - Features added since alpha 2:
   
    - Error log window to display download warnings and errors.
    
    - Synchronize RAW + JPEG Sequence values.
   
 - Fixed bug #739021: unable to set subfolder and file rename preferences on 
   alpha and beta Linux distributions such as Ubuntu 11.04 or Fedora 15.
   
 - Updated Brazilian, Dutch, French, German and Spanish translations. 

0.4.0a2 (2011-03-31)
--------------------

 - Features added since alpha 1:
   
   - Sample file names and subfolders are now displayed in the preferences 
     dialog window.
   - The option to add a unique identifier to a filename if a file with the same
     name already exists
   
 - Other changes:

   - Updated INSTALL file to match new package requirements.
   
   - Added program icon to main window.
   
   - Bug fix: leave file preview mode when download devices are changed in the 
     preferences.
   
   - Bug fix: don't crash on startup when trying to display free space and photo
     or video download folders do not exist.

0.4.0a1 (2011-03-24)
--------------------

 - Rapid Photo Downloader is much faster and sports a new user interface. It is
   about 50 times faster in tasks like scanning photos and videos before the 
   download. It also performs the actual downloads quicker. It will use
   multiple CPU cores if they are available. 
   
 - Rapid Photo Downloader now requires version 0.3.0 or newer of pyexiv2. It 
   also requires Python Imaging (PIL) to run. It will only run on recent Linux
   distributions such as Ubuntu 10.04 or newer. It has been tested on Ubuntu 
   10.04, 10.10 and 11.04, as well as Fedora 14. (There is currently an unusual
   bug adjusting some preferences when running Ubuntu 11.04. See bug #739021).
   
 - This is an alpha release because it is missing features that are present in 
   version 0.3.5. Missing features include:
   
   - System Notifications of download completion

   - Job Codes

   - Backups as you download

   - Automation features, e.g. automatically start download at startup

   - Error log window (currently you must check the command line for error 
     output)

   - Time remaining status messages

   - Synchronize RAW + JPEG Sequence Numbers

   - Add unique identifier to a filename if a file with the same name already
     exists

   - Sample file names and subfolders are not displayed in the preferences 
     window
   
 - These missing features will be added in subsequent alpha and beta releases.
   
 - Kaa-metadata is no longer required to download videos. However, if you 
   want to use Frames Per Second or Codec metadata information in subfolder or
   video file names, you must ensure it is installed. This is no longer checked 
   at program startup. 
   
 - Thanks go to Robert Park for refreshing the translations code.
   
 - Added Romanian translation.

0.3.5 (2011-03-23)
------------------

 - The primary purpose of this release is update translations and fix bug 
   #714039, where under certain circumstances the program could crash while 
   downloading files. 
   
 - This is intended to be the last release in the 0.3.x series. In the upcoming 
   version 0.4.0, Rapid Photo Downloader is much faster and sports a new user 
   interface.
   
 - Added Romanian translation. Updated Brazilian, Chinese, Croatian, Czech, 
   Dutch, Finnish, German, Italian, Polish and Russian translations.

0.3.4 (2010-12-31)
------------------

 - You can now change the size of the preview image by zooming in and out using 
   a slider. The maximum size is double that of the previous fixed size, which 
   was 160px. On computers with small screens such as netbooks, the maximum
   preview image size is the same as the previous fixed size. Please note that 
   Rapid Photo Downloader only extracts thumbnails of photos; for performance 
   reasons, it does not create them. This means for some file formats, the 
   thumbnails will contain jpeg artifacts when scaled up (this is particularly 
   true when using a version of pyexiv2 < 0.2.0). For users who require larger 
   preview images, this will be of little consequence.
   
 - When the "Strip compatible characters" feature is enabled in the Preferences 
   (which is the default), any white space (e.g. spaces) beginning or ending a
   folder name will now be removed.
   
 - Bug fix: camera serial numbers are now stripped of any spaces preceding or
   following the actual value.
   
 - Fixed bug #685335: inaccurate description of python packages required for 
   downloading videos.
   
 - Added Croatian translation. Updated French, Norwegian Bokmal, Polish and 
   Russian translations.

0.3.3 (2010-10-24)
------------------

 - Added support for mod, tod and 3gp video files. 
   
 - Hachoir-metadata is now used to extract selected metadata from video files. 
   It has less bugs than kaa-metadata, and is better maintained. One benefit of 
   this change is that more video file types can have their metadata extracted. 
   Another is that the video creation date is now correctly read (the creation 
   time read by kaa metadata was sometimes wrong by a few hours). Kaa-metadata 
   is still used to extract some the codec, fourcc and frames per second (FPS) 
   metadata.
   
 - Fixed bug #640722: Added preliminary support for Samsung SRW files. Current
   versions of Exiv2 and pyexiv2 can read some but not all metadata from this 
   new RAW format. If you try to use metadata that cannot be extracted, Rapid 
   Photo Downloader will issue a warning.
   
 - Fixed bug #550883: Generation of subfolders and filenames using the time a
   download was started. 
   
 - Fixed bugs related to missing video download directory at program startup.
   
 - Added command line option to output to the terminal information useful for 
   debugging.
   
 - Added Norwegian Bokmal and Portuguese translations. Updated Brazilian 
   Portuguese, Dutch, Finnish, German, Hungarian, Italian, Norwegian Nynorsk, 
   Polish, Russian, Serbian, Slovak and Ukrainian translations.

0.3.2 (2010-09-12)
------------------

 - Added Norwegian Nynorsk translation. Updated Chinese, Finnish, Hungarian, 
   Dutch, Occitan (post 1500), Polish, Brazilian Portuguese, and Russian 
   translations.
   
 - Fixed crash on startup when checking for free space, and the download folder 
   does not exist.

0.3.1 (2010-08-13)
------------------

 - The main window now works more effectively on tiny screens, such as those 
   found on netbooks. If the screen height is less than or equal to 650 pixels, 
   elements in the preview pane are removed, and the spacing is tightened.
   
 - The amount of free space available on the file-system where photos are to be
   downloaded is now displayed in the status bar. (Note this is only the case on
   moderately up-to-date Linux distributions that use GVFS, such as Ubuntu 8.10 
   or higher).
   
 - Add Chinese (simplified) translation. A big thanks goes out to the Ubuntu 
   Chinese translation team. Partial translations of Bulgarian, Japanese, 
   Occitan (post 1500), Persian, Portuguese (Brazilian), and Turkish have been 
   added. In the past only translations that were largely finished were added, 
   but hopefully adding incomplete translations will speed up their completion. 
   Updated Finnish,  French, Hungarian, Russian, Serbian and Spanish 
   translations.

0.3.0 (2010-07-10)
------------------

 - The major new feature of this release is the generation of previews before
   a download takes place. You can now select which photos and videos you wish 
   to download.
   
 - You can now assign different Job Codes to photos and videos in the same 
   download. Simply select photos and videos, and from the main window choose a 
   Job Code for them. You can select a new Job Code,or enter a new one (press 
   Enter to apply it). 
   
 - The errors and warnings reported have been completely overhauled, and are now
   more concise.
   
 - Now that you can select photos and videos to download, the "Report an error" 
   option in case of filename conflicts has been removed. If you try to download
   a photo or video that already exists, an error will be reported. If you 
   backup a photo or video that already exists in the backup location, a warning
   will be reported (regardless of whether overwriting or skipping of backups 
   with conflicting filenames is chosen). 
   
 - Likewise, the option of whether to report an error or warning in case of 
   missing backup devices has been removed. If you have chosen to backup your 
   photos and videos, and a backup device or location is not found, the files 
   will be downloaded with warnings.
   
 - For each device in the main window, the progress bar is now updated much more
   smoothly than before. This is useful when downloading and backing up large 
   files such as videos. (Note this is only the case on moderately up-to-date
   Linux distributions that use GVFS, such as Ubuntu 8.10 or higher).
   
 - The minimum version of python-gtk2 (pygtk) required to run the program is now
   2.12. This will affect only outdated Linux distributions.

0.3.0b6 (2010-07-06)
--------------------

 - Fixed bug #598736: don't allow file to jump to the bottom when it has a Job 
   Code assigned to it.
   
 - Fixed bug #601993: don't prompt for a Job Code when downloading file of one
   type (photo or video), and it's only a file of the other type that needs it.
   
 - Log error messages are now cleaned up where a file already exists and there 
   were problems generating the file / subfolder name.
   
 - Fixed crash on startup when using an old version of GIO.
   
 - Fix crash in updating the time remaining in when downloading from extremely
   slow devices.
   
 - Set the default height to be 50 pixels taller.
   
 - Bug fix: don't download from device that has been inserted after program 
   starts unless device auto detection is enabled.
   
 - Updated German translation.

0.3.0b5 (2010-07-04)
--------------------

 - Added warning dialog if attempting to download directly from a camera.
   
 - Add backup errors details to error log window.
   
 - Fixed program notifications.
   
 - Fixed corner cases with problematic file and subfolder names.
   
 - Disabled Download All button if all files that have not been downloaded have
   errors. 
   
 - Enabled and disabled Download All button, depending on status, after 
   subfolder or filename preferences are modified after device has been scanned. 
   
 - Don't stop a file being downloaded if a valid subfolder or filename can be
   generated using a Job Code.
   
 - Bug fix: don't automatically exit if there were errors or warnings and a 
   download was occurring from more than one device.
   
 - Auto start now works correctly again.
   
 - Job Codes are now assigned correctly when multiple downloads occur. 
   
 - Default column sorting is by date, unless a warning or error occurs when 
   doing the initial scan of the devices, in which case it is set to status 
   (unless you have already clicked on a column heading yourself, in which case 
   it will not change).
   
 - Use the command xdg-user-dir to get default download directories.
   
 - Updated Czech, Dutch, Finnish, French, Italian, Polish, Russian and Ukrainian
   translations.
 
0.3.0b4 (2010-06-25)
--------------------

 - Fixed bug in Job Code addition in the preferences window.
  
 - Made Job Code entry completion case insensitive.
  
 - Update preview to be the most recently selected photo / video when 
   multiple files are selected.
  
 - Don't crash when user selects a row that has its status set to be 
   download pending.
  
 - Improve error log status messages and problem notifications.

0.3.0b3 (2010-06-23)
--------------------

 - First beta release of 0.3.0. 

0.2.3 (2010-06-23)
------------------

 - Updated Hungarian, Russian, Swedish and Ukrainian translations.
  
 - Fixed bug #590725: don't crash if the theme does not associate an icon with 
   the detected device.
  
 - Bug fix: update example filenames and folders when Job codes are manually 
   modified in the preferences window.
  
 - This is the final release before 0.3.0, which will be a major update.

0.2.2 (2010-06-06)
------------------

 - Added Ukrainian translation by Sergiy Gavrylov.
  
 - Bug fix: in systems where exiv2 is not installed, don't crash on startup.

0.2.1 (2010-06-05)
------------------

 - Bug fix: display sample photo and video names in preferences dialog using
   first photo and video found on download device, where possible. This used to
   work but was inadvertently disabled in a recent release.
  
 - Bug fix: prompt for Job code when only video names or video subfolder names
   use a job code.
  
 - Bug fix: filter out Null bytes from Exif string values. These can occur when
   the Exif data is corrupted.
  
 - Updated Spanish, Russian and Finnish translations.

0.2.0 (2010-05-30)
------------------

 - Videos can now be downloaded in much the same way photos can. 
  
 - The package kaa metadata is required to download videos. ffmpegthumbnailer is
   used to display thumbnail images of certain types of videos as the download
   occurs. 
  
 - kaa metadata and ffmpegthumbnailer are optional. The program will run without
   them. See the INSTALL file for details.
  
 - If a THM file with the same name as the video is present, it will be used to 
   generate a thumbnail for the video. If not, if ffmpegthumbnailer is 
   installed,  Rapid Photo Downloader will use it to attempt to extract a 
   thumbnail from the video. THM files are not downloaded.
  
 - For now, sequence values are shared between the downloads of videos and 
   photos. There may be an option to have two sets of sequence numbers in a 
   future release.
  
 - Due to the number of changes in the code, it is possible that regressions in
   the photo downloading code may have been introduced. 
  
 - This is the first release to use version 0.2.x of the pyexiv2 library.  The 
   most immediate benefit of this change is that thumbnail images from Nikon and 
   other brand cameras can be displayed. This fixes bugs #369640 and #570378.
  
 - Please note pyexiv2 0.2.x requires exiv2 0.1.9 or above.
  
 - Rapid Photo Downloader will still work with pyexiv2 0.1.x. However it will 
   not be able to display the thumbnails of some brands of camera.
  
 - If Rapid Photo Downloader detects version 0.18.1 or higher of the exiv2
   library, it will download Panasonic's RW2 files. If it detects version 0.18.0
   or higher of the exiv2 library, it will download Mamiya's MEF files. For 
   Rapid Photo Downloader to be able to detect which version of the exiv2 
   library your system has, it must either be running pyexiv2 >= 0.2.0, or have 
   exiv2 installed.
  
 - Fixed bug #483222: sometimes images could not be downloaded to NTFS 
   partitions. This fix was a welcome side effect of using GIO to copy images,
   instead of  relying on the python standard library.
  
 - Error message headings in the Error Log are now displayed in a red font.
  
 - Program settings and preferences can be reset using a new command line 
   option.
  
 - Program preferences are now more thoroughly checked for validity when the
   program starts. 
  
 - Further work was done to fix bug #505492, to handle cases where the system
   notification system is not working properly.

0.1.3 (2010-01-22)
------------------

 - Fixed bug #509348: When both the backup and "Delete images from image device 
   upon download completion" options are selected, the program will only delete 
   an image from the image device if it was both downloaded to the download 
   folder and backed up. Previously it did not check to ensure it was backed up 
   correctly too.
  
 - Fixed bug #505492: Program failed to start in environments where the 
   notification system has problems.
  
 - Fixed bug #508304: User is now prompted to confirm if they really want to 
   remove all of their Job Codes after clicking on "Remove All" in the 
   preferences dialog window.
  
 - Fixed bug #510484: Crashes when fails to create temporary download directory.
  
 - Fixed bug #510516: Program now checks to see if the download folder exists 
   and is writable. If automatic detection of image devices is not enabled, it
   checks to see if the image location path exists.
  
 - Updated Czech, Dutch, Finnish, French, German, Hungarian, Italian, Polish, 
   Russian, Serbian, Spanish and Swedish translations.

0.1.2 (2010-01-16)
------------------

 - New feature: photographers using RAW + JPEG mode now have the option to 
   synchronize sequence numbers for the matching pair of images. This option is
   useful if you use the RAW + JPEG feature on your camera and you use sequence
   numbers or letters in your image renaming. Enabling this option will cause 
   the program to detect matching pairs of RAW and JPEG images, and when they 
   are detected, the same sequence numbers and letters will be applied to both 
   image names. Furthermore, sequences will be updated as if the images were 
   one. For example, if 200 RAW images and 200 matching JPEG images are 
   downloaded, the value of Downloads today will be incremented by 200, and not 
   400. The same goes for the rest of the sequence values, including the Stored 
   number sequence number. Images are detected by comparing filename, as well as
   the exif value for the date and time the image was created (including sub 
   seconds when the camera records this value). This option will take effect
   regardless of whether the RAW and JPEG images are stored on different memory 
   cards or the same memory card. Furthermore, if they are stored on separate 
   memory cards, you can download from them simultaneously or one after the 
   other. The only requirement is to download the images in the same session--in 
   other words, for the feature to work, use as many memory cards as you need, 
   but do not exit the program between downloads of the matching sets of images.
  
 - Increased maximum sequence number length to seven digits by user request.
  
 - Fixed bug #503704: changes in values for downloads today and stored number 
   not updated when changed via program preferences while a download is ready to 
   begin.
  
 - Fixed a rare startup bug, where the program could crash when starting a 
   thread.
  
 - Added Serbian translation by Milos Popovic. Updated Czech, Dutch, Finnish,
   French, German, Hungarian, Italian, Polish, Russian, Slovak, Spanish and 
   Swedish translations. 

0.1.1 (2010-01-05)
------------------

 - Added auto delete feature. When enabled, upon the completion of a download,
   images that were successfully downloaded will be deleted from the image 
   device they were downloaded from. Images that were not downloaded
   successfully will not be deleted. 
  
 - Added keyboard accelerators for Preferences and Help.
  
 - Added Dutch translation by Alian J. Baudrez. Updated Czech, French, German, 
   Hungarian, Italian, Polish, Slovak and Spanish translations.

0.1.0 (2009-12-07)
------------------

 - Added icons to notification messages.
  
 - Updated Czech, French, German, Hungarian, Polish, Russian, Slovak, Spanish 
   and Swedish translations.
  
 - Bug fix: properly handle devices being unmounted, fixing a bug introduced in
   Version 0.0.9 beta 2.
  
 - Bug fix: When program preferences are changed, image and backup devices are 
   now refreshed only when the preferences dialog window is closed.
  
 - Bug fix: Minutes component of image and folder renaming had the same code as 
   months.

0.1.0b2 (2009-11-22)
--------------------

 - New feature: when detection of portable storage devices is selected, the 
   program will prompt you whether or not to download from each device it
   automatically detects. You can choose whether the program should remember the
   choice you make every time it runs. This fixes bug #376020.
  
 - Fixed bug #484432: error in adding job codes via the preferences dialog.
  
 - Fixed bug #486886: Job code prompt can appear multiple times.
  
 - Updated Hungarian and French translations.

0.1.0b1 (2009-11-14)
--------------------

 - This code is ready for full release, but given the magnitude of changes, a 
   beta seems like a good idea, simply to catch any undetected bugs.
  
 - Added a "Job codes" option. Like the "text" option in image and subfolder 
   name generation, this allows you to specify text that will be placed into the
   file and subfolder names. However, unlike the "text" option, which requires 
   that the text be directly entered via the program preferences, when using the
   "Job code" option, the program will prompt for it each time a download 
   begins. 
  
 - Made Download button the default button. Hitting enter while the main window
   has focus will now start the download.
  
 - Fixed bug #387002: added dependency in Ubuntu packages for librsvg2-common. 
   Thanks go to user hasp for this fix.
  
 - Fixed bug #478620: problem with corrupted image files. Thanks go to user 
   Katrin Krieger for tracking this one down.
  
 - Fixed bug #479424: some camera model names do not have numbers, but it still
   makes sense to return a shortened name. Thanks go to user Wesley Harp for 
   highlighting this problem.
  
 - Fixed bug #482831: program no longer crashes when auto-download is off, and a 
   device is inserted before another download has completed.
   
 - Added Czech translation by Tomas Novak.
  
 - Added French translation by Julien Valroff, Michel Ange, and Cenwen.
  
 - Added Hungarian translation by Balazs Oveges and Andras Lorincz.
  
 - Added Slovak translation by Tomas Novak.
  
 - Added Swedish translation by Ulf Urden and Michal Predotka.
  
 - Added dependency on gnome-icon-theme in Ubuntu packages.
  
 - Added additional hour, minute and second options in image renaming and 
   subfolder creation. Thanks to Art Zemon for the patch.
  
 - Malformed image date time exif values have are minimally checked to see if 
   they can still be used for subfolder and image renaming. Some software 
   programs seem to make a mess of them.
  
 - Updated man page, including a bug fix by Julien Valroff.
  
0.0.10 (2009-06-05)
-------------------

 - Updated Russian translation by Sergei Sedov.
  
 - Fixed bug #383028: program would crash when using an automatically configured 
   backup device and gvfs.
  
0.0.9 (2009-06-02)
------------------

 - Added Italian translation by Marco Solari and Luca Reverberi.
  
 - Added German translation by Martin Egger and Daniel Passler.
  
 - Added Russian translation by Sergei Sedov.
  
 - Added Finnish translation by Mikko Ruohola.
  
 - A Help button has been added to Preferences dialog window. Clicking it takes
   you to the documentation found online at the program's website. This 
   documentation is now complete.
  
 - The Preferences Dialog Window is now navigated using a list control, as it 
   was in early versions of the program. This change was necessary because with 
   some translations, the dialog window was becoming too wide with the normal 
   tab layout. Usability of the preferences dialog is improved: it will now 
   resize itself based on its content.
  
 - Better integration with Nautilus is now possible through the setting of 
   MimeType=x-content/image-dcf in the program's .desktop file.

0.0.9b4 (2009-05-26)
--------------------

 - Added Spanish translation by Jose Luis Navarro and Abel O'Rian.
  
 - Whenever subfolder preferences are modified in the Preferences Dialog window,
   they are now checked to see if they contain any extraneous entries. If 
   necessary, any entries like this are removed when the dialog window is 
   closed.
  
 - Bug fix: Changes in preferences should be applied to devices that have 
   already been scanned, but their images not yet downloaded. This bug was 
   introduced in beta 2 when fixing bug #368098.
  
 - Bug fix: check subfolder preferences for validity before beginning download. 
   While image rename preferences were checked, this check was neglected.
  
 - Bug fix: do not allow automatic downloading when there is an error in the
   preferences.

0.0.9b3 (2009-05-25)
--------------------

 - Added command line options for controlling verbosity, displaying which image
   file types are recognized, and printing the program version.
  
 - Updated man page to reflect recent program changes and new command line 
   options.
  
 - Prepared program for translation into other languages. Thanks go to Mark 
   Mruss and his blog http://www.learningpython.com for code examples and 
   explanations.
  
 - Polish translation by Michal Predotka. Coming soon: French, German and
   Spanish translations.
  
 - To install the program using python setup.py, the program msgfmt must now be
   present. On most Linux distributions, this is found in the package gettext.
  
 - Updated INSTALL file to reflect minimum version of pyexiv2 needed, and 
   included information about handling any error related to msgfmt not being 
   installed.
  
 - Minor fixes to logic that checks whether the Download button should be
   disabled or not. This should now be more reliable.
  
 - Bug fix: error log window can now be reopened after being closed with the "x" 
   button. Thanks go to ESR and his Python FAQ entry for this fix.
  
 - Bug fix: example of subfolder name now has word wrap. Thanks go to Michal
   Predotka for reporting this.
  
 - Bug fix: don't crash when a thumbnail image is missing and the 'orientation'
   variable has not yet been assigned.

0.0.9b2 (2009-05-12)
--------------------

 - By popular demand, allow direct downloading from cameras. This support is
   experimental and may not work with your camera. This is possible through the 
   use of the new gvfs service, provided by GIO, that exists in recent versions 
   of Linux. A recent version of Linux is a must. The camera must also be 
   supported by libgphoto2 in combination with gvfs. If you cannot browse the 
   camera's contents in a file manager (e.g. Nautilus), the camera download will
   not work until the gvfs support is improved.
  
 - Although this is a popular request, the reality is that downloading images
   directly from the camera is often extremely slow in comparison to popping the
   memory card into a card reader and downloading from that. 
  
 - Fix bug #368098: the program now starts more quickly and does not become
   unresponsive when scanning devices with a large number of images. This will
   hardly be noticeable by users that download from memory cards, but for those
   who download from hard drives with hundreds of GBs of files -- they'll notice
   a big difference.
  
 - Fix bug #372284: for image renaming, the "image number" component is more 
   robust. Now, only the series of digits at the end of a filename are 
   recognized as the image number (obviously the file's extension is not 
   included as being part of the filename in this case). This allows takes in 
   account files from cameras like the Canon 1D series, which can have filenames
   like VD1D7574.CR2.
  
 - Bug fix: don't download from volumes mounted while the program is already 
   running unless auto detection is specified. This bug could occur when auto
   detection was enabled, then disabled, and then a volume was mounted.

0.0.8 (2009-05-01)
------------------

 - Added stored and downloads today sequence numbers:
  
   - The stored sequence number is remembered each time the program is run.
  
   - Downloads today tracks how many downloads are made on a given day. The time
     a day "starts" is set via a new preference value, day start. This is useful
     if you often photograph something late at night (e.g. concerts) and want a 
     new day to "start" at 3am, for instance.
  
 - Make estimate of time remaining to download images much more accurate.
  
 - Display download speed in status bar.
  
 - Reorganized sequence number/letter selection in preferences.
  
 - Add feature to detect change in program version, upgrading preferences where
   necessary.
  
 - Only allow one instance of the program to be run -- raise existing window if 
   it is run again. This is very useful when Rapid Photo Downloader is set to 
   run automatically upon insertion of a memory card.
  
 - Add "exit at end of successful download" automation feature.
  
 - When an image's download is skipped, the thumbnail is now lightened.
  
 - Show a missing image icon if the thumbnail cannot be displayed for some 
   reason. (See bug #369640 for why thumbnail images from certain RAW files are 
   not displayed).
  
 - Resize main window when an image device is inserted -- it now expands to show
   each device that is inserted.
  
 - Do not proceed with download if there is an error in the image rename or
   download subfolder preferences. Instead, indicate a download error.
  
 - Allow version 0.1.1 of pyexiv2 to be used (an older version of the library 
   code that is used to get information on the images, found in distributions 
   like Ubuntu 8.04 Hardy Heron).
  
 - In cases where image rename or download subfolder preferences are invalid, 
   more helpful information is printed to the console output.
  
 - Bug fix: better handle automated shortening Canon names like 'Canon 5D Mark 
   II'. It is now shortened to '5DMkII' instead of merely '5D'.
  
 - Bug fix: re-enable example of image renaming and subfolder name generation by
   using first image from the first available download device. This was
   inadvertently disabled in an earlier beta.
  
 - Bug fix: make default download subfolder YYYY/YYYYMMDD again. It was
   inadvertently set to DDMMYYYY/YYYYMMDD in beta 6.
  
 - Bug fix: don't change download button label to "pause" when "Start 
   downloading on program startup" is set to true.
  
 - Bug fix: implement code to warn / give error about missing backup devices.
  
 - Bug fix: reset progress bar after completion of successful download.
  
 - Fix bug #317404 when clearing completed downloads.

0.0.8b7 (2009-04-07)
--------------------

 - Added serial number metadata option for select Nikon, Canon, Olympus, Fuji, 
   Panasonic, and Kodak cameras.

 - Added shutter count metadata option for select Nikon cameras, e.g. Nikon 
   D300, D3 etc.

 - Add owner name metadata option for select Canon cameras, e.g. 5D Mk II etc.

0.0.8b6 (2009-03-31)
--------------------

 - Add YYYY-MM-DD and YY-MM-DD options in date time renaming, suggested by
   Andreas F.X. Siegert and Paul Gear.

 - Fix bug #352242 where image has no metadata.

 - Handle images with corrupt metadata more gracefully.

0.0.8b5 (2009-03-30)
--------------------

 - Reduce console output.


0.0.8b4 (2009-03-25)
--------------------

 - Updated Ubuntu package.

0.0.8b3 (2009-03-25)
--------------------

 - Updated Ubuntu package.

0.0.8b2 (2009-03-25)
--------------------

 - First Ubuntu package.

 - Rename tarball package to suit package name.

 - Updated README.

0.0.8b1 (2009-03-20)
--------------------

 - Make file renaming thread safe, fixing a long-standing (if difficult to 
   activate) bug.

 - Implement add unique identifier when file name is not unique.

 - Added "Report a Problem", "Get Help Online", "Make a Donation" to Help menu.

 - Implemented "Clear completed downloads" menu item.

 - Download images in order they were taken (checked by time they modified).

 - Fixed bug where choosing text as the first item in a download subfolder 
   caused a crash.

 - Fixed bug where date and time choices based on when image is downloaded 
   caused a crash.

 - Initial code to show error message when image renaming preferences have an 
   error.

 - Fixed bug where some invalid preferences were not being caught.

 - Run default python, not one specified in env, as per recommendations in 
   Debian Python Policy.

 - Remove initial period from filename extension when generating a subfolder 
   name (or else the folder will be hidden).

 - Check to see if metadata is essential to generate image names is now more 
   robust.

 - Remove list control from preferences, reverting to normal tabbed preferences, 
   as the window was becoming too wide.

 - Show notifications via libnotify.

 - Error and warning icons can now be clicked on to open log window.

 - Finally, last but certainly not least--implemented sequence number and 
   sequence letter generation:

   - session sequence number

   - sequence letter

 - Coming soon:

   - downloads today sequence number

   - subfolder sequence number

   - stored sequence number
 
0.0.7 (2009-01-13)
------------------

 - Implemented option for automatic detection of Portal Storage Devices. 

0.0.6 (2009-01-11)
------------------

 - Fixed extremely annoying bug where memory cards could not be unmounted.

 - Made sample image selection for preferences more robust.

 - Added license details to about dialog.

 - Fix bug where image rename preferences entry boxes vertically expanded, 
   looking very ugly indeed.

 - Wrap new filename in image rename preferences when it becomes too long.

 - Make default download folder selection more robust.

 - Remove sequence number and sequence letter from list of choices for image 
   rename (not yet implemented).

 - Bug #314825: fix by not calling gnomevfs.get_local_path_from_uri() unless 
   strictly necessary.

0.0.5 (2009-01-09)
------------------

 - Implement auto download on device insertion, and auto download on program
   startup.

 - Increase default width of preferences dialog box.

 - Add vertical scrollbar to image rename preferences.

 - Fixes for bugs #313463 & #313462.

0.0.4 (2009-01-06)
------------------

 - Bug #314284: Implement backup functionality.

 - Bug #314285: Insert debugging code to help determine the cause of this bug.

0.0.3 (2009-01-03)
------------------

 - Bug #313398: Fix bug where application needed to be restarted for new
   preferences to take effect.

 - Added setup.py installer.

0.0.2 (2007)
------------

 - Updated metadata code to reflect changes in pyexiv library.

 - Pyexiv 0.1.2.

0.0.1 (2007)
------------

 - Initial release.
