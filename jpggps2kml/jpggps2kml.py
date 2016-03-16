#! /usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on Mon Mar  7 18:56:15 2016
Copyright (C) 2016 Russell O. Redman

Create a KML file based on exif data from a set of JPEG files contained in
a specified set of directories.

Requires exiftool to have been installed, as well as the pykml and pyexiftool
python packages.  It is also recommended that the jpegtrans package be
installed.  Note that exiftools and jpegtrans are C programs and must be
installed manually.

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.

@author: russell
@email: russell@roredman.ca
"""


from pykml.factory import KML_ElementMaker as KML
from pykml.factory import GX_ElementMaker as GX
from lxml import etree
import exiftool

import argparse
import configparser
import os
import os.path
import re
import subprocess
import sys

class jpggps2kml():
    """
    Reads EXIF data from JPEG files in the input set of directories.  
    Entry points are defined for the following operations:
    makegpx(): call exiftool to construct GPX files.
    editgps(): edit the EXIF GPS info in JPEG files for which it was not set
        correctly, using a specified GPX file.
    orient(): call jpegtrans to orient the files with pixel (0,0) in the
        top left corner.
    makekml(): make a KML file that displays tracks for each day and 
        placemarks along the track to display each JPEG image. 
    """
    def __init__(self):
        """
        Initialize a jpggps2kml object.
        """
        self.config = None # placeholder for ConfigParser object
        self.dirs = [] # placeholder for a list of directories
    
    def read_config(self):
        """
        Read configuration data from a config file or the command line.
        Command line arguments will override config file entries.
        """
        # Create a ConfigParser object to read the configuration file
        self.config = configparser.ConfigParser()
    
        # Set default argument values in config.  These can be overwritten
        # from both the config file and from the command line.
        # Do NOT set default values for command line arguments, since these
        # would always overwrite the values in the config file.
#        self.config['arguments'] = {}
        self.config.read_dict({'arguments': {'verbosity': 'normal',
                                             'dir': '.'}})
    
        # Create an ArgumentParser to read the command line.  Every argument
        # added to ap can have a corresponding entry in the [argument] section
        # of te config file, except for the config argument that must be 
        # supplied to locate the config file itself.
        ap = argparse.ArgumentParser()
        ap.add_argument('-c', '--config',
                        default='jpggps.config',
                        help='configuration file with values for arguments '\
                             'in the [arguments] section')
        ap.add_argument('-f', '--fmt',
                        help='GPX fmt file used in makegpx()')
        ap.add_argument('-g', '--gpx',
                        help='GPX directory used as ouput in makegpx() and '\
                             'as input in editgps()')
        ap.add_argument('-k', '--kml',
                        help='KML filename used in makekml()')
        ap.add_argument('-r', '--replace',
                        help='Replace dupicate Elements in an existing KML '
                             'file, otherwise skip the new item')
        ap.add_argument('-t', '--timezone',
                        help='timezone ofset from UTC in the format '\
                             '(+/-)hhmm, e.g. PST = -0800, PDT = -0700')
        ap.add_argument('-u', '--url',
                        help='''base url for files, e.g.
                            for disk files file:///absolute/path/to/directory/
                            for web files http://host.domain/path/to/dir/''')
        ap.add_argument('-v', '--verbosity',
                        choices=['none','normal','debug'],
                        help='verbosity message verbosity')
        ap.add_argument('dir', nargs='*',
                        help='directories to search for JPEG files')
        a = vars(ap.parse_args())
    
        if 'config' in a:
            configfile = os.path.expanduser(os.path.expandvars(a['config']))
            if os.path.exists(configfile):
                self.config.read(configfile)
            else:
                print('config file not found at ' + configfile, 
                      file=sys.stderr)
    
        # Override selected config values from the command line
        args = self.config['arguments']

        rawdirs = []
        if 'dir' in args and args['dir']:
            if ',' in args['dir']:
                rawdirs = args['dir'].split(',')
            else:
                rawdirs = [args['dir']]
        
        for key in a:
            if key == 'dir' and a[key]:
                rawdirs = a[key]
            elif a[key]:
                self.config['arguments'][key] = a[key]
        
        if rawdirs:        
            for d in rawdirs:
                absdir = os.path.abspath(
                    os.path.expanduser(
                        os.path.expandvars(d)))
                if os.path.isdir(absdir):
                    self.dirs.append(absdir)

        self.verbosity = 1
        if args['verbosity'] == 'quiet':
            self.verbosity = 0
        elif args['verbosity'] == 'debug':
            self.verbosity = 2
        
        # Check the specified directories to ensure that they are directories, 
        # and convert them to absolute paths.
        if not self.dirs:
            print('ERROR: no input directories specified', file=sys.stderr)
            sys.exit(-1)

    def colourStyle(self,
                   doc,
                   colourID,
                   colour_normal,
                   width_normal,
                   colour_highlight,
                   width_highlight):
        """
        Append line style elements to a KML document.
        Arguments:
        doc: KML document to hold the new styles
        colourID: the base ID for the styles
        colour_normal: normal colour for the line
        width_normal: normal width for the line
        colour_highlight: highlighted colour for the line
        width_highlight: highlighted width for the line
        """
        doc.append(
            KML.Style(
                KML.IconStyle(
                    KML.Icon(),
                    id="no_icon_n"
                ),
                KML.LineStyle(
                    KML.colour(colour_normal),
                    KML.width(width_normal)
                ),
                id=(colourID + '_n')
            )
        )
        doc.append(
            KML.Style(
                KML.IconStyle(
                    KML.Icon(),
                    id="no_icon_h"
                ),
                KML.LineStyle(
                    KML.colour(colour_highlight),
                    KML.width(width_highlight)
                ),
                id=(colourID + '_h')
            )
        )
        doc.append(
            KML.StyleMap(
                KML.Pair(
                    KML.key('normal'),
                    KML.styleUrl('#' + colourID + '_n')
                ),
                KML.Pair(
                    KML.key('highlight'),
                    KML.styleUrl('#' + colourID + '_h')
                ),
                id=colourID
            )
        )
        
    def makeKmlDoc(self):
        """
        """
        self.cdatatext = {}
        args = self.config['arguments']
        if self.config['arguments']['update']:
            with open(args['kml'], 'r') as f:
                doc = KML.parse(f)
            self.colourIndex = len(doc.findall(KML.Track))
        else:
            # create a new KML structure from scratch
            doc = KML.Document(
                      KML.description('Daily tracks and image placemarks'),
                      KML.visibility('1'),
                      KML.open('1'),
                      KML.name("Daily tracks and places")
                  )
    
            # Append a style for pictures using the camera icon
            doc.append(
                KML.Style(
                    KML.IconStyle(
                        KML.scale(1.0),
                        KML.Icon(
                            KML.href(
                                'http://maps.google.com/mapfiles/kml/'\
                                'shapes/camera.png'),
                        ),
                        id="picture_style"
                    ),
                    id='picture'
                )
            )
    
            # Append styles for lines in different colours
            colourSet = [['7fff0000', 6, 'ffff0000', 8],
                         ['7f00ff00', 6, 'ff00ff00', 8],
                         ['7f0000ff', 6, 'ff0000ff', 8],
                         ['7fffff00', 6, 'ffffff00', 8],
                         ['7fff00ff', 6, 'ffff00ff', 8],
                         ['7f00ffff', 6, 'ff00ffff', 8]]
            self.colourSetLen = len(colourSet)
            
            for colourIndex in range(len(colourSet)):
                normal, narrow, highlight, wide = colourSet[colourIndex]
                colourID = 'colour' + str(colourIndex)
                self.colourStyle(doc, 
                                 colourID, 
                                 normal, 
                                 narrow,
                                 highlight,
                                 wide)
            # This records the final colourIndex used in the file and should 
            # be set from an existing file by parsing the lineStyle arguments
            self.colourIndex = 0 
            
        return doc

    def appendTrackPlacemarks(self, doc, directory, et):
        """
        Append to the KML document doc a folder containing one or more tracks 
        for the JPEG files in directory, and a folder containing a set of 
        placemarks for each file.  A separate track will be generated for 
        each day, assigning colours in a cycle from the colourSet.
        
        Arguments:
        doc: the KML document to which the folder will be appended
        directory: the abspath to the directory containing the files
        et: an ExifTool object
        """
        # Extract time, orientation and GPS metadata from EXIF
        items = ['EXIF:DateTimeOriginal',
                 'EXIF:GPSStatus',
                 'EXIF:GPSMeasureMode',
                 'EXIF:GPSLongitude',
                 'EXIF:GPSLongitudeRef',
                 'EXIF:GPSLatitude',
                 'EXIF:GPSLatitudeRef',
                 'EXIF:GPSAltitude']
        basedir = os.path.basename(directory)

        # Gather JPEG metadata into places
        places = {}
        for f in os.listdir(directory):
            if self.verbosity > 0:
                print('search for JPEG files in ' + directory, 
                      file=sys.stderr)

            filebase, fileext = os.path.splitext(f)
            if fileext in ('.jpg', '.JPG', '.jpeg', '.JPEG'):
                filepath = os.path.join(directory, f)
                in_kml = ''

                tags = et.get_tags(items, filepath)
                if self.verbosity > 1:
                    for k in tags:
                        print(k, ' = ', tags[k], file=sys.stderr)

                if 'EXIF:GPSLongitude' in tags:
                    # GPS metadata id available
                    lat = lon = None
                    datestr = timestr = ''
                    alt = 0

                    if "EXIF:GPSLatitude" in tags:
                        lat = tags['EXIF:GPSLatitude']
                        if 'EXIF:GPSLatitudeRef' in tags and \
                           tags['EXIF:GPSLatitudeRef'] == 'S':

                            lat = -lat

                    if "EXIF:GPSLongitude" in tags:
                        lon = tags['EXIF:GPSLongitude']
                        if 'EXIF:GPSLongitudeRef' in tags and \
                           tags['EXIF:GPSLongitudeRef'] == 'W':

                            lon = -lon

                    if "EXIF:DateTimeOriginal" in tags:
                        m = re.match(r'\s*(\d+:\d+:\d+)\s+'
                                     r'(\d+:\d+:[\d.]+)\s*',
                                     tags['EXIF:DateTimeOriginal'])
                        datestr = re.sub(r':', '-', m.group(1))
                        timestr = m.group(2)

                    if "EXIF:GPSAltitude" in tags:
                        alt = tags['EXIF:GPSAltitude']

                    if self.verbosity > 1:
                        print(datestr,
                              timestr,
                              lat,
                              lon,
                              alt,
                              '\n',
                              file=sys.stderr)

                    if datestr and timestr and lat and lon:
                        in_kml = ' in kml'

                        if datestr not in places:
                            places[datestr] = {}
                        
                        timefile = timestr + filebase
                        if timefile not in places[datestr]:
                            places[datestr][timefile] = {}
                    
                        jpegmeta = places[datestr][timefile]
                        jpegmeta['filebase'] = filebase
                        jpegmeta['time'] = GX.when('T'.join(datestr, timestr))
                        jpegmeta['place'] = \
                            GX.coord('{0} {1} {2}'.format(lon, 
                                                          lat, 
                                                          alt))
                        jpegmeta['point'] = \
                            KML.Point(
                                KML.coordinates('{0},{1},{2}'.format\
                                                (lon, lat, 0)))
                        if self.config['arguments']['url']:
                            jpegmeta['fileurl'] = '/'.join(
                                self.config['arguments']['url'], basedir, f)
                        else:
                            jpegmeta['fileurl'] = '/'.join('file:/', filepath)

                if self.verbosity > 0:
                    print('    ' + f, in_kml, file=sys.stderr)

        # Build the track folder and placemark folder
        track_folder = KML.Folder()
        placemark_folder = KML.Folder()
        for datestr in sorted(places.keys()):
            colourID = '#colour' + str(self.colourIndex)
            placemark = KML.Placemark(
                KML.visibility('1'),
                KML.name(basedir),
                KML.description('Path taken at ' + basedir + ' on ' + 
                                datestr),
                KML.styleUrl(colourID)
                )
            self.colourIndex = (self.colourIndex + 1) % self.colourSetLen

            track = GX.Track(
                KML.altitudeMode('clampToGround')
                )
            for tf in sorted(places[datestr].keys()):
                # append when elements
                track.append(places[datestr][tf]['time'])
            for tf in sorted(places[datestr].keys()):
                # append coord elements
                track.append(jpegmeta[tf]['place'])
            placemark.append(track)
            track_folder.append(placemark)
            
            for tf in sorted(places[datestr].keys()):
                jpegmeta = places[datestr][tf]
                
                jpg = jpegmeta['filebase']
                cdatakey = 'CDATA' + directory + datestr + jpg
                self.cdatatext[cdatakey] = ('<![CDATA[<img src="' + 
                    jpegmeta['fileurl'] + ' width=400/><br/>' + 
                    'Taken at ' + directory + ' on ' + datestr + '<br/>]]>')
                placemark_folder.append( 
                    KML.Placemark(
                        KML.visibility('1'),
                        KML.styleUrl('#picture'),
                        KML.name(jpg),
                        KML.description(cdatakey),
                        jpegmeta['point']
                    )
                )

        doc.append(track_folder)
        doc.append(placemark_folder)
        

    def makekml(self):
        """
        Make a KML file that displays tracks for each day and 
            placemarks along the track to display each JPEG image. 
        """
        self.read_config()
        args = self.config['arguments']
        doc = self.makeKmlDoc()
        # For each directory, add a folder and append the track and images
        
        with exiftool.ExifTool() as et:
            for d in args['dir']:
                self.appendTrackPlacemarks(doc, d, et)
        
        kmlstr = str(etree.tostring(doc, pretty_print=True),
                     encoding='UTF-8') % self.cdatatext
    
        if 'kml' in args and args['kml']:
            kmlpath = os.path.abspath(
                          os.path.expanduser(
                              os.path.expandvars(args['kml'])))
            if (not os.path.isfile(kmlpath) or args['update', False]):
                with open(kmlpath, 'w') as OUT:            
                    print(kmlstr, file=OUT)
            else:
                print('ERROR: use --udate to overwrite ' + kmlpath)
                sys.exit(-1)
        else:
            print(kmlstr)

def makegpx():
    """
    Call exiftool to construct GPX files.  The output GPX file(s) are created
    with the name specified by the --gpx argument, which is mandatory for 
    this operation.  Also specify --update if the operation is intended to
    overwrite an existing file. 
    """
    jpggps = jpggps2kml()
    jpggps.read_config()
    args = jpggps.config['arguments']
    if 'gpx' not in args or not args['gpx']:
        if jpggps.verbosity > 1:
            for item in args:
                print(item + ' = ' +
                      args[item], file=sys.stderr)
        print('Required argument --gpx is not defined. This is the directory '
              'that will contain the output gpx files.', file=sys.stderr)
        sys.exit(-1)
    gpxabs = os.path.abspath(
        os.path.expanduser(
            os.path.expandvars(args['gpx'])))
    
    if 'fmt' not in args:
        print('Required argument --fmt is not defined. This is the name of a '
              'gpx format file like the one supplied in fmt_files/gpx.fmt in '
              'the ExifTool source directory', file=sys.stderr)
        sys.exit(-1)
    fmtabs = os.path.abspath(
        os.path.expanduser(
            os.path.expandvars(args['fmt'])))
    if not os.path.isfile(fmtabs):
        print('GPX format file does not exist: ' + fmtabs, file=sys.stderr)
        sys.exit(-1)
    
    for d in jpggps.dirs:
        basedir = os.path.basename(d)
        print('d = ' + d + '\ngpxabs = ' + gpxabs + '\nbasedir = ' + basedir)
        gpxpath = os.path.join(gpxabs, basedir + '.gpx') 
        if jpggps.verbosity > 0:
            print('Create a GPX file from the JPEG files in ' + basedir, 
                  file=sys.stderr)
        if os.path.isdir(gpxpath) and not args.get('update', False):
            print('WARNING: Set --update to replace existing file: ' + 
                  gpxpath, file=sys.stderr)

        exiftool_cmd = ("exiftool -r -if '$gpsdatetime' " +
                        '-fileOrder gpsdatetime -p ' + 
                        fmtabs + 
                        ' -d %Y-%m-%dT%H:%M:%SZ ' + d +
                        ' > ' + gpxpath)
        if jpggps.verbosity > 0:
            print('exiftool_cmd: ' + exiftool_cmd, 
                  file=sys.stderr)
        gpx = subprocess.call(exiftool_cmd, shell=True)
#        if gpx:
#            with open(gpxpath, 'w') as GPX:
#                GPX.write(gpx)
#        else:
#            print('WARNING: no output from exiftool_cmd: ' + exiftool_cmd,
#                  file=sys.stderr)

def editgps():
    """
    Edit the EXIF GPS info in JPEG files for which it was not set
        correctly, using a specified GPX file.
    """
    jpggps = jpggps2kml()
    jpggps.read_config()

def orient():
    """
    Call jpegtrans to orient the files with pixel (0,0) in the
        top left corner.
    This code has been cloned from the shell script provided by the 
    Independent JPEG Group at http://jpegclub.org/exif_orientation.html.
    This version should work for any OS and shell, provided exiftools and
    jpegtran are installed.
    """
    jpggps = jpggps2kml()
    jpggps.read_config()
    transform = ['',
                 '-flip horizontal',
                 '-rotate 180',
                 '-flip vertical',
                 '-transpose',
                 '-rotate 90',
                 '-transverse',
                 '-rotate 270']
    items = ['-EXIF:Orientation']
    with exiftool.ExifTool() as et:
        for d in jpggps.dirs:
            if jpggps.verbosity > 0:
                print('Orient JPEG files in ' + d, file=sys.stderr)
            for f in os.listdir(d):
                filebase, fileext = os.path.splitext(f)
                if fileext in ('.jpg', '.JPG', '.jpeg', '.JPEG'):
                    filepath = os.path.join(d, f)
                    tags = et.get_tags(items, filepath)
                    if jpggps.verbosity > 1:
                        for k in tags:
                            print(k, ' = ', tags[k], file=sys.stderr)
                    orient = int(tags['EXIF:Orientation'])
                    if orient:
                        jpegtran_cmd = ['jpegtran',
                                        '-copy all',
                                        transform[orient],
                                        filepath]
                        if jpggps.verbosity > 1:
                            print('jpegtran_cmd: ' + jpegtran_cmd.join(' '), 
                                  file=sys.stderr)
                        try:                    
                            output = subprocess.call(jpegtran_cmd)
                        except OSError:
                            print(output, file=sys.stderr)
                            print('Is jpegtran istalled?', file=sys.stderr)
                            raise

def makekml():
    """
    entry point for the method makekml
    """
    jpggps = jpggps2kml()
    jpggps.makekml()