# -*- coding: utf-8 -*-
"""
Created on Tue Mar 15 16:22:30 2016

@author: russell
"""
INTENDED USAGE
==============
The jpggps2kml package provides a set of tools to help create kml files
for import into Google Maps and Google Earth to display images taken during
a trip and the path followed each day.

EXTERNAL PACKAGES
=================
Two additional tools should be installedmanually, Phil Harvey's exiftool and 
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
(abbreviated as -c).  This is the only command line argument that cannot 
have a default set in the config file.

The configuration file has the form:

[arguments]
fmt = FMT # path to the gpx template found at $(EXIFTOOL}/fmt_files.gpx.fmt
gpx = GPX # path to the directory containing gpx files
kml = KML # path to the kml output file
replace = True/False # replace duplicates items
timezone = +HH:MM # Offset from UTC for camera local time
url = URL # URL to access installed images
verbosity = quiet/normal/debug # verbosity of progress messages
dir = dir1,...,dirN # comma separated list of directories containing JPEG files

The detailed interpretation of each argument will be discussed in the 
appropriate section below.  

Note that the dir argument is a positional argument that absorbs all tokens
at the end of te command line, checking that they are directories before use.
The configparser module expects a single string as the value of each argument,
so in the configuration file the dir argument must be supplied as a comma-
separated list of directories.

EXTRACTION OF GPX TRACKS WITH makegpx
=====================================
My Sony Alpha55 records GPS locations when enough GPS satellites are available
but not every image has such a position and many other cameras do not record 
GPS data at all.  

Exiftool can be used to extract a track stored in a GPX file 
from the JPEG files for each day.  The command is somewhat fussy, so this 
package provides the command "makegpx" to read the format and dispatch the
command.

This command uses the --fmt, --gpx, --replace and --verbosity and dir 
arguments. 

The --fmt argument is required, and specifies the path to the GPX format file
to be used by exiftool.  A suitable example is supplied in the exiftool
source directories at fmt_files/gpx.fmt.  This argument is best set in a 
configuration file.  

The --gpx argument is optional and defaults to '.' (current directory) if not 
specified.  For the makegpx command, --gpx specifies the output directory to 
hold new GPX files.  It avoid unexpected overwrites, it should normally be 
set as an absolute path in the configuration file. 

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
      --gpx=/Users/russell/aux \
      --replace=True \
      --verbosity=quiet \
      ~/Pictures/2016-01-02 ~/Pictures/2016-01-03
will store new gpx files in /Users/russell/aux using the template gpx.fmt from
the current directory and searching for GPS position in JPEG files in the 
directories ~/Pictures/2016-01-02 and ~/Pictures/2016-01-03. It willreplace 
old GPX files if necessary, and will run quietly with no progress messages.  

With the configuration file gpx.config in the current directory containing
  [arguments]
  fmt = gpx.fmt
  gpx = /Users/rusell/aux
  replace = True
  verbosity = quiet
  dir = ~/Pictures/2016-01-02,~/Pictures/2016-01-03
the command
   makegpx -c gpx.config
would do the same thing.

EDIT GPS EXIF HEADERS WITH editgps
==================================

This command edits GPS EXIF headers in the JPEG files in a set of 
directories, using the GPX files in the directory specified by the --gpx 
argument.

The command uses the --gpx, --timezone, --verbosity and dir arguments.

The --gpx argument specifies the directory to search for gpx files, which
must have names of the form YYYY-MM-DD.gpx so that editgps can identify the
correct gpx file to use for each JPEG file from the date part of the standard 
OriginalDateTime EXIF header.

The --timezone argument gives the offset from UTC for the local time used in 
the camera, which need not be a standard timezone, in the format +/-HH:MM:SS.
This allows the correct GPS time (very close to UTC) to be determined even if 
the clock in the camera was set incorrectly.

The --verbosity argument is optional and defaults to normal if omitted.  This
should be correct and would not normally be given a default value in the
configuration file unless quiet operation is required.

The dir argument is positional and absorbs the list of token at the end of 
the command, interpreting them as directories to be searched for JPEG files.

There are two cautions to note with this command:
1) This command edits the GPS header in the EXIF extension of the JPEG files
and CAN CORRUPT the JPEG files.  Never do this to the original JPEG files, but 
only to copies that can be easily restored.
2) This edits GPS headers,not the gpx files, so the command is editgps, 
not editgpx.

