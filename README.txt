# -*- coding: utf-8 -*-
"""
Created on Tue Mar 15 16:22:30 2016

@author: russell
"""
INTRODUCTION
============

The jpggps2kml package provides a set of tools to help create kml files
for import into Google Maps and Google Earth to display images taken during
a trip and the path followed each day.

INTENDED WORKFLOW
=================

The intended workflow is as follows:

1) For each day (local time) a GPX file showing where the camera was taken 
will be generated.  This can be done using the gpx file generated using the
makegpx command, by downloading a GPX file from a GPS aware cellphone, or some 
other GPS device.

2) A selection of location or event specific JPEG files is copied to a new 
set of directories.  These may be on disk, or in a disk-based staging area
in preparation for upload to a web-accessible file server like Google Drive.

3) JPEG files in the staging area (not the original archive copies of the 
images) that do not already have accurate GPS locations will be editted 
from the available GPX files to include the  required EXIF GPS headers, using 
the editgps command.

4) Optionally, the orientjpeg command can be used to standardize the 
orientation of the images so that the (0, 0) pixel is in the top left of the 
image (EXIF:Orientation = 1).  All web browsers, including Google Earth, will 
display such images the same way, although other orientations may also be 
displayed properly if the browser supports the EXIF:Orientation header.  
Google Earth currently does not.

5) Optionally, the directories including the JPEG files from teh staging area
can be copied to the web-accesible file server, maintaining the directory 
structure and generating a URL for the root of the new set of directories.

6) A KML file will be generated using makekml that contains track for each 
GPX file and placemarks at the (nominal, interpolated) locations of each JPEG 
file.  Clicking on the placemark icon will display the corresponding image.  

EXTERNAL PACKAGES
=================
Two additional tools should be installed manually, Phil Harvey's exiftool and 
jpegtran from the Independent JPEG Group.  Exiftool is necessary for this
package and must be installed.  Jpegtran provides a convenient mechanism to
adjust the orientation of the images so the (0,0) pixel is always in the
top left corner.  Some, but not all, browsers do this automatically; Google 
Earth in particular does not, so it is necessary to edit the images before
Google Earth can display them properly. 

These packages are not written in Python and cannot be installed by the Python 
distribution tools.  They are available from:
  exiftool: http://www.sno.phy.queensu.ca/~phil/exiftool/
  jpegtran: http://www.ijg.org/
Note that exiftool has a Python wrapper pyexiftool that must also be 
installed, but the Python distribution should be able to find and install
this by itself. 

Exiftool documentation can be found at: 
  http://www.sno.phy.queensu.ca/~phil/exiftool/exiftool_pod.html
A useful list of GPSInfo headers that may be present can be found at:
  http://www.opanda.com/en/pe/help/gps.html

FILE AND DIRECTORY CONVENTIONS
==============================
My tools assume that all the images are JPEG files organized into directories
following some simple and common conventions. 

Pictures taken each day will normally be downloaded from the camera into a 
trip-specific directory with separate subdirectories for each day, e.g.
   ../trip
        /2016-01-02
        /2016-01-03
        /2016-01-03

Note that I have named the daily directories using ISO 8601 conventions.  I
similarly name the gpx tracks for each day with the same kind of convention,
e.g. 2016-01-02.gpx, so that the correct gpx file can be identified from the
EXIF tag OriginalDateTime.

These directories are intended to hold raw images with minimal or no editing.
If the camera clock was set incorrectly, it may be desirable to correct the 
recorded times using exiftool commands like:
   cd trip/2016-01-02
   exiftool -alldates+=1 -if '$CreateDate le "2016:01:02 09:10:00"' dir

Files intended for display will normally be copied into a location or event
specific directory (or set of directories) and may be processed and renamed.
Web accessible images will be copied into a staging directory before being
uploaded to a file server.  The directory structures should normally be the 
same in the staging area and on the web server.

These tools will also use several auxiliary files (config and gpx files, for 
example) that should be kept with the images on disk.  This suggests a 
directory structure like:
   ../aux
   ../staging
        /trip
           /locationA
           /locationB
           /locationC
where the aux directory holds the auxiliary files and the selected images 
have in this example been sorted by location.

COMMANDS SUPPLIED BY JPGGPS2KML
===============================

This package implements four commands that can be executed on the command line.
  makegpx: extracts GPS locations from JPEG files, recording them in gpx files
  editgps: uses gpx files to edit GPS positions into JPEG files
  orientjpeg: rotates/flips images so that 0,0 pixel is in the upper left
  makekml: reads EXIF tags and gpx files to create a KML file for the
           display of tracks and placemarks.

STANDARD CONFIGURATION FILE
===========================

All four commands can be configured using command line arguments together
with a configuration file.  The same set of arguments are defined 
for all four commands.  

A configuration file can be used to set default values for the command line 
arguments.  Unused arguments are ignored. so the same configuration file can 
be used for all four commands.  

The path to the configuration file is set using the --config arguement 
(which can be abbreviated as -c).  This is the only command line argument that 
cannot have a default set in the config file.

The configuration file has the form:

  [arguments]
  fmt = FMT # path to the gpx template found at $(EXIFTOOL}/fmt_files.gpx.fmt
  gpx = GPX # path to the directory containing gpx files
  out = OUT # path to a single output file
  replace = True/False # replace duplicates items
  timezone = +HH:MM[:SS] # Offset from UTC for camera local time
  url = URL # URL to access installed images
  utc = YYYY[-:]MM[-:]DD[T ]HH:MM:SS
  verbosity = quiet/normal/debug # verbosity of progress messages
  dir = dir1,...,dirN # comma separated list of directories for JPEG files

The more detailed interpretation of each argument will be discussed for each
command in the appropriate section below.  

Note that the dir argument is a positional argument that absorbs all tokens
at the end of the command line. The program expands the user and OS variables
and converts the tokens into absolute paths, then sorts these into two lists 
holding files and directories.  For most of the commands, dir on the command 
line will be a whitespace separated list of directories, perhaps generated 
with a globbing wildcard like "~/trip/*".  The configparser module expects a 
single string with no spaces as the value of each argument, so in the 
configuration file the dir argument must be supplied as a comma-separated 
list of directories. Globbing wildcards, user (~/) and environment variable 
expansion are all supported in the configuration file, so ~/trip/* is still a 
valid directory specification.

It will normally be useful to store track logs, such as GPX files, in the 
same directory as the images, or in a dedicated directory nearby on the disk.
The following commands will search for such files in the directory specified
by the --gpx argument, if supplied, or in the same directories as the image
files.   

USING findoffset TO FIND THE OFFSET OF THE CAMERA CLOCK FROM UTC
================================================================
GPX and KML files record positions along tracks as a function of UTC, but 
cameras have internal clocks that may or may not be set correctly, and the
image files may or may not record the timezone correctly.  Except when the 
time or timezone is set in the camera, the offset from camera time to UTC 
should be nearly constant, affected mostly by the very slow drift of the 
camera clock.

For example the Sony Alpha 55 records the DateTimeOriginal and when the GPS 
is Active stores the UTC time from the satellites in the GPSInfo header
GPSTimeStamp.  The camera knows the timezone and whether Daylight Savings is 
in effect, both of which are set through the menu manually, but does not 
record either in the EXIF headers.  

Similarly, the Nikon D7000 records to record the camera time and timezone 
offset from UTC in the headers EXIF:DateTimeOriginal and MakerNotes:Timezone
respectively.  The Nikon download software running on a storage host will 
synchronize the camera clock with the host system clock each time the camera 
is connected to the host, but the system clock on the host may or may not be 
correct for the local timezone, and MakerNotes:Timezone will be left unchanged. 

A useful way to determine the exact UTC corresponding to the DateTimeOriginal 
is to take a picture of the UTC supplied by the device that collected the 
GPS positions in the GPX file.  The time recorded in a GPX or KML file is 
always UTC, so the device nominally knows the conversion to UTC.  For example,
if a smart phone was used to record a GPX track, a world clock widget can be 
used to  display the UTC date and time (with seconds).  Taking a picture of
that display will record the correct UTC in the image for comparison with the 
EXIF DateTimeOriginal header from the camera.  

This command uses the --utc and dir arguments. 

The --utc argument specifies the UTC in one of two formats:
  ISO 8601: YYYY-MM-DDTHH:MM:SS
  EXIF: YYYY:MM:DD HH:MM:SS
Note that the EXIF format must be protected with single quotes to keep it as a 
single token, e.g. --utc='2016:01:20 10:25:02'.  When the --utc argument is 
supplied, the positional argument dir must be the path to a single JPEG file 
from which the DateTimeOriginal will be read for comparison with the value of 
UTC specified with the --utc argument.  

If --utc is omitted and GPSStatus is 1 (Active), the GPSTimeStamp will be used
to set the UTC datetime.  In this case, dir can be set of paths to JPEG files
and or a set of directories containing JPEG files.  The program will iterate 
over all of the JPEG files, printing to stdout the offset calculated for each 
file that has GPSStatus Active. 

If only one value of the offset is found (no matter whether from a single JPEG
file or several) the output written to stdout will have the form
  most negative = -AllDates-=07:00:02
where the string starting "-AllDates" can be cut and pasted into a config file
as the --offset argument.

It will often be the case when the offset is determinded from the GPSTimeStamp
header that several different values will be computed.  The GPSTimeStamp, as 
its name indicates, records the UTC when the last GPS Time was measured from 
the satellites, which may have been be several seconds prior to the moment the 
picture was taken.  Since the camera clock will have advanced while the 
GPSTimeStamp was frozen, the difference DateTimeOriginal - GPSTimeStamp will 
be more positive than the actual difference DateTimeOriginal - UTC. If
more than one value of the offset was measured, the output written to stdout 
will report the distribution of offsets as a count of measured values for
each offset in seconds.  The bias discussed above is always positive, so the 
best estimate of the actual offset will normally be the most negative offset,
but if the distribution does not peak strongly near the most negative offset,
the mode (most common value) of the offset might be a better estimate. 
  
USING makegpx TO EXTRACT GPX TRACKS
===================================
The Sony Alpha55 records GPS locations when enough GPS satellites are 
available but not every image has such a position and many other cameras do 
not record GPS data at all.  

Exiftool can be used to extract a track stored in a GPX file 
from the JPEG files for each day.  The command is somewhat fussy, so this 
package provides the command "makegpx" to read the format and dispatch the
command.

This command uses the --fmt, --out, --replace and --verbosity and dir 
arguments. 

The --fmt argument is required, and specifies the path to the GPX format file
to be used by exiftool.  A suitable example is supplied in the exiftool
source directories at fmt_files/gpx.fmt.  This argument is best set in a 
configuration file.  

The --out argument is required and specifies the path to the output GPX file.  

The --replace argument if True instructs makegpx to replace existing gpx
files if new files are generated.  Otherwise, the old file will be retained
and the generation of a new file will be skipped.

The --verbosity argument is optional and defaults to normal if omitted.  This
should be correct and would not normally be given a default value in the
configuration file unless quiet operation is required.

The dir argument is positional and absorbs the list of token at the end of 
the command, interpreting them as directories to be searched for JPEG files.
 
The remaining arguments are ignored.
 
Thus the command
   makegpx \
      --fmt=gpx.fmt \
      --out=/Users/russell/aux/2016-01-02.gpx \
      --replace=True \
      --verbosity=quiet \
      ~/Pictures/2016-01-02
will store new gpx files in /Users/russell/aux using the template gpx.fmt from
the current directory and searching for GPS position in JPEG files in the 
directory ~/Pictures/2016-01-02. It will replace old GPX files if necessary, 
and will run quietly with no progress messages.  

With the configuration file gpx.config in the current directory containing
  [arguments]
  fmt = gpx.fmt
  out = /Users/rusell/aux/2016-01-02.gpx
  replace = True
  timezone = -08:00
  verbosity = quiet
  dir = ~/staging/2016-01-02
the command
   makegpx -c gpx.config
would do the same thing.  Note that the timezone and dir arguments from the 
configuration file are ignored, the value of timezone because makegpx does not 
use the argument and the value of dir because it is overridden by the pair of 
directories supplied on the command line.  

USING editgps to SET GPS EXIF HEADERS
=====================================

The editgps command edits GPS EXIF headers in the JPEG files in a set of 
directories, using the GPX files in the directory specified by the --gpx 
argument to interpolate nominal GPS locations based on the OriginalDateTime.

The command uses the --gpx, --timezone, --verbosity and dir arguments.

The --gpx argument is optional and specifies the directory to search for 
GPX files.  If not specified, the program will search for gpx files in the 
directories listed in the dir argument.  The editgps program will read each 
GPX file, extracting the earliest and latest datetimes that will be recorded 
in a list of GPX files.  It is an error for GPX files in the --gpx directory 
to have overlapping ranges of datetime.  When editting a JPEG file, the 
OriginalDateTime header will be translated into UTC (see the --timezone 
argument) and used to search for a matching GPX file.  If OriginalDateTime 
falls within the range of any of one of the GPX files, an exiftool command 
will be executed to interpolate a GPS position and edit the EXIF GPS headers 
for the JPEG file.

The --timezone argument gives the offset from UTC for the local time used in 
the camera, which need not be a standard timezone, in the format +/-HH:MM[:SS].
This allows the correct UTC time to be determined even if the clock in the 
camera was set incorrectly.  The seconds part of the offset is optional and 
can be used to correct any difference noted between the GPSDateStamp and 
OriginalDateTime headers.  If --timezone=auto, an attempt will be made to set 
this value automatically from JPEG files for which GPSStatus == 1 (Active).

The --verbosity argument is optional and defaults to normal if omitted.  This
should be correct and would not normally be given a default value in the
configuration file unless quiet operation is required.

The dir argument is positional and absorbs the list of tokens at the end of 
the command, interpreting them as directories to be searched for JPEG files.

There are two cautions to note with this command:

1) This command edits the GPS header in the EXIF extension of the JPEG files
and CAN CORRUPT the JPEG files.  Never do this to the original JPEG files, but 
only to copies that can be easily restored.

2) This edits GPS headers, not the gpx files, so the command is editgps, 
not editgpx.

For example, the command
  editgps -c gpx.config
where gpx.config is the same config file used for the makegpx example above,
will edit all JPEG files in ~/Pictures/2016-01-02 and ~/Pictures/2016-01-03
that do not already have EXIF:GPSStatus == 1 (Active) and 
EXIF:GPSMeasureMode > 1 (longitude and latitude are measured) to set GPS 
locations interpolated from the GPX files for their dates.  Note that in this
example, the values of the timezone and dir arguments are taken from the 
configuration file.

USING orientjpeg TO STANDARDIZE THE ORIENTATION OF JPEG IMAGES
==============================================================

The orientjpeg command rotates/flips the image in a JPEG file so that the 
(0, 0) pixel is in the upper left corner, the standard orientation of most 
images.  This corresponds to the tag EXIF:Orientation = 1.  

This command is a thin wrapper around the jpegtran command, following the 
algorithm of the IJG shell script exifautotran supplied by IJG at:
  http://jpegclub.org/exif_orientation.html
This implementation is written in Python and should be more portable than the 
shell script supplied by IJG.

USING makekml TO CREATE A KML FILE DISPLAYING THE GPX TRACKS AND IMAGES
=======================================================================

The makekml command creates a KML file that contains copies of the tracks 
from each GPX file and a list of placemarks for each JPEG image that has GPS
coordinates in its header.  The KML file can be imported into Google Earth or 
Google Maps for viewing.  The placemark for each JPEG image will pop up the
image when selected.  The KML file can be built up incrementally, adding 
tracks and placemarks from different directories on each invocation.

This command uses the --gpx, --out, --replace, --url, --verbosity, and dir 
arguments.

The --gpx argument specifies the path to a directory containing GPX files
from which a set of tracks will be read.  Track names in the KML file will be 
the same as the GPX file basename.  If --gpx is not specified, the directories 
listed in the dir argument will be searched for gpx files.

The --out argument specifies the path to the output KML file and is required.

The --replace argument is a boolean that indicates whether duplicate entries
(tracks or placemarks) should be skipped or replaced in the KML file.
 
The --url argument specifies a base URL where Google Earth and Google Maps
can look for the image to display.  If the files reside on a set of 
directories on disk, the URL should look like:
  --url='file:///path/to/root/directory'
If the files are accessible on the Internet, the URL might look like:
  --url='http://storage.node/path/to/root'

The --verbosity argument is optional and defaults to normal if omitted.  This
should be correct and would not normally be given a default value in the
configuration file unless quiet operation is required.

The dir argument is positional and absorbs the list of tokens at the end of 
the command, interpreting them as directories to be searched for JPEG files.

