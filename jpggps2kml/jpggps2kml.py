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


import exiftool
from lxml import etree
from pykml.factory import KML_ElementMaker as KML
from pykml.factory import GX_ElementMaker as GX

import argparse
import configparser
import datetime
import glob
import os
import os.path
import re
import subprocess
import sys

class beginenditem():
    """
    A class for tuples of begin, end, item lists
    """
    def __init__(self, begin, end, item, nextitem):
        """
        Create the tuple
        """
        self.begin = begin
        self.end =  end
        self.item = item
        self.next = nextitem

class sorteditems():
    """
    A sorted, linked list of begin, end items
    """
    def __init__(self):
        """
        Initialize a sorted linked list of beginenditems 
        """
        self.first = None
    
    def add(self, begin, end, item):
        """
        Add a new beginenditem to the linked list.  The new item will be 
        initialized and inserted into the correct place.  It is an error
        if the open interval (begin, end) overlaps an existing interval.
        """
        bgi = self.first
        while bgi:
            if begin > bgi.end and bgi.next:
                # Not at an insertion point
                bgi = bgi.next
            elif bgi.next:
                if end > bgi.next.begin:
                    print('cannot create "(' + begin + ', ' + end +
                          ', ' + item + ') because it overlaps an existing '
                          'interval:', file=sys.stderr)
                    bgierr = self.first
                    while bgierr:
                        print(' (' + bgierr.begin + ', ' + bgierr.end +
                              ', ' + bgierr.item + ')', file=sys.stderr)
                        bgierr = bgierr.next
                    sys.exit(-1)
                else:
                    # Insert a new beginenditem between bgi and bgi.next
                    bginew = beginenditem(begin, end, item, bgi.next)
                    bgi.next = bginew
                    break
            else:
                # Append the new beginenditem at the end of the linked list
                bginew = beginenditem(begin, end, bginew, None)
                bgi.next = bginew
                break
    
    def find(self, here):
        """
        Return the corresponding item if begin <= here <= end else None 
        """
        bgi = self.first
        while bgi.end < here:
            if bgi.next:
                bgi = bgi.next
            else:
                break
        if bgi.begin <= here and bgi.end <= here:
            return bgi.item
        else:
            return None
            
    
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
        self.files = [] # placeholder for a list of files
    
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
                        help='configuration file with values for arguments '\
                             'in the [arguments] section')
        ap.add_argument('-f', '--fmt',
                        help='GPX fmt file used in makegpx()')
        ap.add_argument('--geosync',
                        help='offset to be added to DateTimeOriginal '
                             'to compute UTC, in the format +/-HH:MM:SS')
        ap.add_argument('-g', '--gpx',
                        help='directory containing GPX files')
        ap.add_argument('-o', '--out',
                        help='output filename')
        ap.add_argument('-r', '--replace',
                        help='Replace dupicate Elements in an existing KML '
                             'file, otherwise skip the new item')
        ap.add_argument('-u', '--url',
                        help='''base url for files, e.g.
                            for disk files file:///absolute/path/to/directory/
                            for web files http://host.domain/path/to/dir/''')
        ap.add_argument('--utc',
                        help='UTC date time (findoffset) or offset (editgps)')
        ap.add_argument('-v', '--verbosity',
                        choices=['none','normal','debug'],
                        help='verbosity message verbosity')
        ap.add_argument('dir', nargs='*',
                        help='directories to search for JPEG files')
        self.a = vars(ap.parse_args())
    
        if 'config' in self.a and self.a['config']:
            configfile = os.path.expanduser(
                             os.path.expandvars(self.a['config']))
            if os.path.exists(configfile):
                self.config.read(configfile)
            else:
                print('config file not found at ' + configfile, 
                      file=sys.stderr)
                sys.exit(-1)
    
        # Override selected config values from the command line
        args = self.config['arguments']

        rawdirs = []
        for key in self.a:
            if key == 'dir' and self.a[key]:
                # if dir is supplied from the command line, use it
                rawdirs = self.a[key]
                args['dir'] = ''
            elif self.a[key]:
                self.config['arguments'][key] = self.a[key]
        
        if not rawdirs and 'dir' in args and args['dir']:
            # if dir not supplied on the command line, but a default is
            # supplied in the configuration file, use it.
            if ',' in args['dir']:
                dirset = args['dir'].split(',')
            else:
                dirset = [args['dir']]

            # Glob wildcards are allowed in the configuration file
            # Expand user, environment variables and wildcards
            for d in dirset:
                rawdir = os.path.abspath(
                             os.path.expanduser(
                                 os.path.expandvars(d)))
                rawdirs.extend(glob.glob(rawdir))
        
        # Check the specified directories to ensure that they are directories, 
        # and convert them to absolute paths.
        if rawdirs:        
            for d in rawdirs:
                absdir = os.path.abspath(
                             os.path.expanduser(
                                 os.path.expandvars(d)))
                if os.path.isdir(absdir):
                    self.dirs.append(absdir)
                elif os.path.isfile(absdir):
                    self.files.append(absdir)

        # Expand --gpx argument if supplied
        if 'gpx' in args and args['gpx']:
            args['gpx'] = os.path.abspath(
                              os.path.expanduser(
                                  os.path.expandvars(args['gpx'])))
        
        # Expand --out argument if supplied
        if 'out' in args and args['out']:
            args['out'] = os.path.abspath(
                              os.path.expanduser(
                                  os.path.expandvars(args['out'])))

        self.verbosity = 1
        if args['verbosity'] == 'quiet':
            self.verbosity = 0
        elif args['verbosity'] == 'debug':
            self.verbosity = 2
        
        if not self.dirs and not self.files:
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
                    KML.color(colour_normal),
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
                    KML.color(colour_highlight),
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
        
    def gpxfiles(self):
        """
        Returns a list of (abspath, basename) tuples of GPX files in --gpx 
        """
        args = self.config['arguments']
        gpxlist = []
        
        # if --gpx was specified, search there for GX files and ignore any
        # found in dirs.  Otherwise search for all GPX files in dirs.
        if 'gpx' in args and args['gpx']:
            gpxdirs = [args['gpx']]
        else:
            gpxdirs = self.dirs
        
        for gpxdir in gpxdirs:
            for f in os.listdir(gpxdir):
                fbase, fext = os.path.splitext(f)
                
                if fext in ('.gpx', '.GPX'):
                    gpxlist.append((os.path.join(gpxdir, f), fbase))
        
        # If a GPX file is specified on the command line, include it
        for f in self.files:
            fbase, fext = os.path.split(f)
            fbase = os.path.basename(fbase)
            if fext in ('.gpx', '.GPX') and os.path.isfile(f):
                gpxlist.append((f, fbase))
        
        if self.verbosity > 1:
            print(repr(gpxlist), file=sys.stderr)
        
        return gpxlist

    def read_track_from_gpx(self, 
                            filepath, 
                            filebase, 
                            trackfolder,
                            colourIndex):
        """
        Read a single GPX file and extract the track(s), converting them to a 
        list of KML tracks.  Append or replace each track in the trackfolder.
        This fills the trackfolder in makekml.
        
        Arguments:
        filepath: the full path to the GPX file
        filebase: the basename of the GPX file, used to name the KML tracks
        trackfolder: a KML.Folder to hold track Placemarks
        colourIndex: the next colourIndex to use when creating a linestyle
        
        On successful exit, trackfolder and colourIndex will have been updated.
        """
        args = self.config['arguments']
        gpxtree = etree.parse(filepath).getroot()        
        namespace = gpxtree.nsmap[None]
        if self.verbosity > 1:
            print('namespace for ' + filepath + ': ' + namespace, 
                  file=sys.stderr)
        
        print('{%s}trk' % namespace, file=sys.stderr)
        print(namespace + 'trk', file=sys.stderr)
        for gpxtrack in gpxtree.getiterator('{%s}trk' % namespace):
            print('got here', file=sys.stderr)
            # Extract the track name from the GPX track
            try:
                trackname = gpxtrack.find('{%s}name' % namespace).text
            except:
                print('track does not have name in ' + filepath, 
                      file=sys.stderr)
                trackname = filebase
            print('trackname = ' + trackname, file=sys.stderr)

            # does a Placemark already exist with this name?
            placemark = None
            for pm in trackfolder.findall('GX.Placemark'):
                if pm.find('KML.name').text == trackname:
                    placemark = pm
                    break
            if 'replace' in args and args['replace']:
                trackfolder.drop(placemark)
                placemark = None
            
            if not placemark:
                # Create a new Placemark to hold the KML track(s)
                colourID = '#colour' + str(self.colourIndex)
                self.colourIndex = (self.colourIndex + 1) % self.colourSetLen

                placemark = KML.Placemark(
                    KML.visibility('1'),
                    KML.name(trackname),
                    KML.description(trackname + ' from ' + filebase),
                    KML.styleUrl(colourID)
                    )
                trackfolder.append(placemark)

                tracklist = []
                for gpxtrkseg in gpxtrack.getiterator('{%s}trkseg' % namespace):
                    # A GPX trkseg translates into aGX.track
                    kmltrack = GX.Track(
                        KML.altitudeMode('clampToGround')
                        )
                    whenlist = []
                    coordlist = []
                    for gpxtrkpoint in gpxtrkseg:
                        lat = gpxtrkpoint.attrib['lat']
                        lon = gpxtrkpoint.attrib['lon']
                        alt = gpxtrkpoint.find('{%s}ele'% namespace).text
                        time = gpxtrkpoint.find('{%s}time'% namespace).text
                        
                        whenlist.append(GX.when(time))
                        coordlist.append(GX.coord('{0} {1} {2}'.format(lon, 
                                                                       lat, 
                                                                       alt)))
                    for w in whenlist:
                        kmltrack.append(w)
                    for c in coordlist:
                        kmltrack.append(c)
                    tracklist.append(kmltrack)
                
                if tracklist:
                    if len(tracklist) > 1:
                        multitrack = GX.MultiTrack()
                        for t in tracklist:
                            multitrack.append(t)
                        placemark.append(multitrack)
                    else:
                        placemark.append(tracklist[0])
                else:
                    print('no tracks found in ' + filepath, file=sys.stderr)
        
    def read_image_placemarks_from_jpeg(self, 
                                        jpegdisk,
                                        jpegrooted,
                                        jpegbase, 
                                        imagefolder,
                                        et):
        """
        Read a JPEG file and extract the GPS location, if present. Create a 
        Placemark for the image and append or replace it in the imagefolder.  
        This fills the imagefolder in makekml.
        
        Arguments:
        jpegdisk: the full path to the JPEG file on the disk
        jpegrooted: the path to the JPEG file relative to the root 
        jpegbase: the basename of the JPEG file, used as an image label
        imagefolder: a KML.Folder to hold image Placemarks
        et: an existing ExifTool object
        
        On successful exit, imagefolder will have been updated.
        
        If the path on disk for the file is like
            jpegdisk = /path/to/root/relative/to/root
        then
            jpegrooted = relative/to/root
        and the full url to locate the image in the KML file will be
            '/'.join(self.url, jpegrooted)
        """
        args = self.config['arguments']
        
        # Does a placemark for this image already exist in the imagefolder?
        for pm in imagefolder:
            name = pm.find('Name')
            if name and name.text == jpegbase:
                if self.verbosity > 1:
                    print(jpegbase,'found in imagefolder', file=sys.stderr)
                
                # image already present
                if 'replace' in args and args['replace']:
                    # replace the image by dropping the existing copy
                    if self.verbosity > 1:
                        print('replace ' + jpegbase, file=sys.stderr)
                    imagefolder.drop(pm)
                else:
                    # keep the image, so bail from further processing
                    if self.verbosity > 1:
                        print('retain existing ' + jpegbase, file=sys.stderr)
                    return
        
        # Get here only if we need to generate a new Placemark        
        tags = et.get_tags(self.items, jpegdisk)
        if self.verbosity > 1:
            for k in tags:
                if k in self.items:
                    print(k, ' = ', tags[k], file=sys.stderr)

        lat = lon = None
        datestr = timestr = ''
        alt = 0

        if "EXIF:GPSLatitude" in tags:
            lat = tags['EXIF:GPSLatitude']
            if ('EXIF:GPSLatitudeRef' in tags and 
                tags['EXIF:GPSLatitudeRef'] == 'S'):

                lat = -lat

        if "EXIF:GPSLongitude" in tags:
            lon = tags['EXIF:GPSLongitude']
            if ('EXIF:GPSLongitudeRef' in tags and 
                tags['EXIF:GPSLongitudeRef'] == 'W'):

                lon = -lon

        if "EXIF:GPSAltitude" in tags:
            alt = tags['EXIF:GPSAltitude']

        if "EXIF:DateTimeOriginal" in tags:
            m = re.match(r'\s*(\d+:\d+:\d+)\s+'
                         r'(\d+:\d+:[\d.]+)\s*',
                         tags['EXIF:DateTimeOriginal'])
            datestr = re.sub(r':', '-', m.group(1))
            timestr = m.group(2)

        if self.verbosity > 1:
            print(datestr,
                  timestr,
                  lat,
                  lon,
                  alt,
                  '\n',
                  file=sys.stderr)

        in_kml = ''
        if datestr and timestr and lat and lon:
            in_kml = ' in kml'

            if 'url' in args and args['url']:
                jpegurl = '/'.join([self.config['arguments']['url'], 
                                    jpegrooted])
            else:
                jpegurl = '/'.join(['file:/', jpegdisk])
            
 #           cdatakey = 'CDATA' + jpegrooted + datestr + jpegbase
            cdatakey = datestr + jpegbase
            self.cdatatext[cdatakey] = ('<![CDATA[<img src="' + 
                jpegurl + '" width=400/><br/>' + 
                'in ' + os.path.dirname(jpegrooted) + 
                ' at ' + timestr +
                ' on ' + datestr + '<br/>]]>')
            
            
            imagefolder.append( 
                KML.Placemark(
                    KML.visibility('1'),
                    KML.styleUrl('#picture'),
                    KML.name(jpegbase),
                    KML.description('{' + cdatakey + '}'),
                    KML.Point(KML.coordinates('{0},{1},{2}'.format(lon, 
                                                                   lat, 
                                                                   alt)))
                    )
                )

        if self.verbosity > 0:
            print('    ' + jpegrooted, in_kml, file=sys.stderr)
            

    def makeKmlDoc(self):
        """
        """
        self.cdatatext = {}
        args = self.config['arguments']
        
        trackfolder = imagefolder = None
        self.colourIndex = 0
        
        if ('update' in self.config['arguments'] and 
            self.config['arguments']['update']):
            
            with open(args['out'], 'r') as f:
                doc = KML.parse(f)
            # Find a folder that contains a Name with the text "tracks"
            trackfolder = doc.find('./Folder/[Name="tracks"]/..')
            # Find a folder that contains a Name with the text "tracks"
            imagefolder = doc.find('./Folder/[Name="images"]/..')

            if trackfolder:
                self.colourIndex = \
                    ((len(trackfolder.findall(KML.PlaceMark)) - 1) % 
                      self.colourSetLen)
        else:
            # create a new KML structure from scratch
            doc = KML.Document(
                      KML.description('Tracks and image placemarks'),
                      KML.visibility('1'),
                      KML.open('1'),
                      KML.name("Tracks and Images")
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
            
            trackfolder = KML.Folder(
                              KML.Name('tracks')
                              )
            doc.append(trackfolder)
            
            imagefolder = KML.Folder(
                              KML.Name('images')
                              )
            doc.append(imagefolder)

        return (doc, trackfolder, imagefolder)

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
        image_folder = KML.Folder()
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
                image_folder.append( 
                    KML.Placemark(
                        KML.visibility('1'),
                        KML.styleUrl('#picture'),
                        KML.name(jpg),
                        KML.description('{' + cdatakey + '}'),
                        jpegmeta['point']
                    )
                )

        doc.append(track_folder)
        doc.append(image_folder)
        
    def makekml(self):
        """
        Make a KML file that displays tracks for each day and 
            placemarks along the track to display each JPEG image. 
        """
        self.read_config()
        args = self.config['arguments']
        if not ('out' in args and args['out']):
            print('--out is required for makekml', file=sys.stderr)
            sys.exit(-1)
        
        self.items = ['EXIF:DateTimeOriginal',
                      'EXIF:GPSStatus',
                      'EXIF:GPSMeasureMode',
                      'EXIF:GPSLongitude',
                      'EXIF:GPSLongitudeRef',
                      'EXIF:GPSLatitude',
                      'EXIF:GPSLatitudeRef',
                      'EXIF:GPSAltitude']

        # Get the KML documant, or make a new one        
        doc, trackfolder, imagefolder = self.makeKmlDoc()
                
        # Read tracks from GPX files into the KML file
        for gpx, gpxbase in self.gpxfiles():
            self.read_track_from_gpx(gpx,
                                     gpxbase,
                                     trackfolder,
                                     self.colourIndex)
        
        # Create Placemarks for each JPEG image in self.dirs
        with exiftool.ExifTool() as et:
            for d in self.dirs:
                for f in os.listdir(d):
                    jpegbase, jpegext = os.path.splitext(f)
                    if jpegext in ('.jpg', '.JPG', '.jpeg', '.JPEG'):
                        jpegpath = os.path.join(d, f)
                        jpegrooted = os.path.join(os.path.basename(d), f)
                        
                        self.read_image_placemarks_from_jpeg(jpegpath,
                                                             jpegrooted,
                                                             jpegbase,
                                                             imagefolder,
                                                             et)
        
        kmlstr = str(etree.tostring(doc, pretty_print=True),
                     encoding='UTF-8').format_map(self.cdatatext)
    
        if 'out' in args and args['out']:
            kmlpath = os.path.abspath(
                          os.path.expanduser(
                              os.path.expandvars(args['out'])))
            if (not os.path.isfile(kmlpath) or 
                'update' not in args or
                not args['update']):
                
                with open(kmlpath, 'w') as OUT:            
                    print(kmlstr, file=OUT)
            else:
                print('ERROR: use --update to overwrite ' + kmlpath,
                      file=sys.stderr)
                sys.exit(-1)
        else:
            print(kmlstr)

def jpegiter(jpggps):
    """
    Iterator over the JPEG files found in jpggps.files and in jpggps.dirs
    """
    for f in jpggps.files:
        fb, fe = os.path.splitext(f)
        fe = fe.lower()
        fb = os.path.basename(fb)
        if fe in ('.jpg', '.jpeg'):
            yield (f, fb)
        
    for d in jpggps.dirs:
        for f in os.listdir(d):
            fp = os.path.join(d, f)
            fb, fe = os.path.splitext(f)
            fe = fe.lower()
            if fe in ('.jpg', '.jpeg'):
                yield (fp, fb)
                
def offset_to_string(offset):
    """
    Format an offset in seconds as the '-AllDates+/-=offset' string for use 
    as an argument for exiftool. 
    """
    sign = '+'
    if offset < 0:
        sign = '-'
        offset = -offset
    
    hrs = offset // 3600
    mins = (offset - 3600 * hrs) // 60
    secs = offset - 3600 * hrs - 60 * mins
    return ('-AllDates' + sign + 
            '={:02d}:{:02d}:{:02d}'.format(hrs, mins, secs))
    
def findoffset():
    """
    Read the DateTimeOriginal from a specified file and the actual UTC time
    from the command line. Report the difference to sys.stdout in the format
    offset = +/-[[HH:]MM:]SS, e.g. offset = +07:00:00.  This is similar to
    the timezone identifier -/+HH:MM but has the offosite sign and includes
    seconds.  This can be passed through the --geosync argument to editgps.
    
    A single image file name must be entered on the command line and will be 
    stored in the dir argument.  The --utc argument is mandatory and must
    contain the UTC) datetime at which the image was taken in ISO 8601 format.
    
    An easy way to determine the time is to take a picture of a display 
    showing the UTC date and time, such as a world clock on a cell phone.  The 
    DateTimeOriginal EXIF header will record the camera's clock time while the
    image itself records the UTC date time at that moment.
    """
    jpggps = jpggps2kml()
    jpggps.read_config()
    args = jpggps.config['arguments']
    
    if not jpggps.files and not jpggps.dirs:
        print('Required positional argument dir is not defined', 
              file=sys.stderr)
        sys.exit(-1)

    tags = {}
    iso8601 = ('(\d{4})[-:](\d{2})[-:](\d{2})[ Tt]'
               '(\d{2}):(\d{2}):(\d{2})')
    offset_distribution = {}
    
    for (f, fb) in jpegiter(jpggps):
        if jpggps.verbosity > 1:
            print('fileabs = ' + f, file=sys.stderr)

        with exiftool.ExifTool() as et:
            items = ['EXIF:DateTimeOriginal',
                     'EXIF:GPSStatus',
                     'EXIF:GPSDateStamp',
                     'EXIF:GPSTimeStamp']
            tags = et.get_tags(items, f)

            if not tags:
                print('could not read EXIF metadata from ' + f,
                      file=sys.stderr)
                sys.exit(-1)
            
            thisutc = None
            mutc = None
            if 'utc' in args and args['utc']:
                # --utc is available, so get the UTC from there
                if jpggps.verbosity > 1:
                    print('UTC from --utc = ' + args['utc'], file=sys.stderr)
                mutc = re.match(iso8601, args['utc'])
            elif 'EXIF:GPSStatus' in tags and tags['EXIF:GPSStatus'] == 'A':
                # Try to extract UTC from GPSTimeStamp
                if jpggps.verbosity > 1:
                    print('GPSStatus = ' + 
                          tags['EXIF:GPSStatus'], file=sys.stderr)
                    print('UTC from GPSTimeStamp = ' + 
                          tags['EXIF:GPSTimeStamp'], file=sys.stderr)
                mutc = re.match(iso8601, tags['EXIF:GPSDateStamp'] + ' ' +
                                         tags['EXIF:GPSTimeStamp'])
            else:
                # UTC not available
                if jpggps.verbosity > 1:
                    print('tags = ' + repr(tags), file=sys.stderr)
                mutc = None
            
            if jpggps.verbosity > 1:
                print('mutc = ' + repr(mutc), file=sys.stderr)
            if mutc:
                gutc = mutc.groups()
                if jpggps.verbosity > 1:
                    print('--utc', file=sys.stderr)
                    for k in gutc:
                        print(k, file=sys.stderr)
                thisutc = datetime.datetime(int(gutc[0]),
                                            int(gutc[1]),
                                            int(gutc[2]),
                                            int(gutc[3]),
                                            int(gutc[4]),
                                            int(gutc[5]))
            else:
                # Skip processing for this file
                if jpggps.verbosity > 1:
                    print('no UTC available for ' + fb, file=sys.stderr)
                continue
            
            mlocal = re.match(iso8601, tags['EXIF:DateTimeOriginal'])
            if mlocal:
                local = mlocal.groups()
                if jpggps.verbosity > 1:
                    print('EXIF:DateTimeOriginal', file=sys.stderr)
                    for k in local:
                        print(k, file=sys.stderr)
                localtime = datetime.datetime(int(local[0]),
                                             int(local[1]),
                                             int(local[2]),
                                             int(local[3]),
                                             int(local[4]),
                                             int(local[5]))
            if thisutc and localtime:
                offset = localtime - thisutc
                
                offset_secs = 86400*offset.days + offset.seconds
                
                if offset_secs <= -86400 or offset_secs > 86400:
                    print('WARNING: abs(offset) = > 1 day')
                else:
                    if offset_secs in offset_distribution:
                        offset_distribution[offset_secs] += 1
                    else:
                        offset_distribution[offset_secs] = 1
                            
            if 'utc' in args and args['utc']:
                # if --utc was supplied, process only one file
                break

    # All JPEG files have been processed.  If there is only one entry in
    # offset_distribution, report that value.  Otherwise, find the mode and
    # the most negative values and report them.
    if len(offset_distribution) == 1:
        offset = list(offset_distribution.keys())[0]
        print('most negative = ' + offset_to_string(offset))
    else:
        offsets = sorted(offset_distribution.keys())
        most_negative = offsets[0]
        mode = most_negative
        mode_number = offset_distribution[most_negative]
        for offset in offsets:
            count = offset_distribution[offset]
            print('count(' + str(offset) + ') = ' + str(count))
            if count > mode_number:
                mode = offset
                mode_number = count
        print('most negative = ' + offset_to_string(most_negative))
        print('mode = ' + offset_to_string(mode))

def makegpx():
    """
    Call exiftool to construct GPX files from the EXIF:GPS metadata from JPEG
    files the directories listed in the dir argument. The output GPX file(s) 
    are created in the directory specified by the mandatory --gpx argument.  
    The mandatory --fmt argument gives a path to the format file used by 
    exiftool to create the GPX file.  A suitable example can be found in 
    the exiftool source directory in fmt_files/gpx.fmt.  Specify --update 
    if the operation is  intended to overwrite existing files. 
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
        if jpggps.verbosity > 0:
            print('processing dir = ' + d + '\ngpxabs = ' + gpxabs + 
                  '\nbasedir = ' + basedir, file=sys.stderr)
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
        subprocess.call(exiftool_cmd, shell=True)
#        if gpx:
#            with open(gpxpath, 'w') as GPX:
#                GPX.write(gpx)
#        else:
#            print('WARNING: no output from exiftool_cmd: ' + exiftool_cmd,
#                  file=sys.stderr)

def editgps():
    """
    Edit the EXIF GPS info in JPEG files for which it was not set
        correctly, using the set of GPX files in --gpx.
    """
    jpggps = jpggps2kml()
    jpggps.read_config()
    # args =  jpggps.config['arguments']
    
    # Read all the GPX files in --gpx, ordering them by their earliest and 
    # latest GPSDateStamp times.
    sortedgpx = sorteditems()
    
    for gpx, gpxbase in jpggps.gpxfiles():
        gpxtree = etree.parse(gpx).getroot()
        namespace = gpxtree.attrib('xmlns')
        if jpggps.verbosity > 1:
            print(gpx + ': ' + namespace, file=sys.stderr)
        
        for gpxtrack in gpxtree.getiterator(namespace + ':trk'):
            begin = end = ''
            for trkseg in gpxtrack.getiterator(namespace + ':trkseg'):
                for trkpt in trkseg.getiterator(namespace + ':trkpt'):
                    thistime = trkpt.find('time')
                    
                    if not begin or begin > thistime:
                        begin = thistime
                    if not end or end < thistime:
                        end = thistime
        
        if begin and end:
            sortedgpx.add(begin, end, gpx)
            
    # find all the JPEG files in dir, calling exiftool to update the EXIF:GPS
    # metadata as required.
    with exiftool.ExifTool() as et:
        items = ['EXIF:DateTimeOriginal',
                 'EXIF:GPSStatus',
                 'EXIF:GPSMeasureMode']
        
        for d in jpggps.dir:
            for f in os.listdir(d):
                fbase, fext = os.path.splitext(f)
                if fext in ('.jpg', '.JPG', '.jpeg', '.JPEG'):
                    fabs = os.path.join(d, f)
                    tags = et.get_tags(items, fabs)
                    if jpggps.verbosity > 1:
                        for k in tags:
                            print(k, ' = ', tags[k], file=sys.stderr)
    
                    # GPS metadata id available
                    datestr = timestr = ''

                    if "EXIF:DateTimeOriginal" in tags:
                        m = re.match(r'\s*(\d+:\d+:\d+)\s+'
                                     r'(\d+:\d+:[\d.]+)\s*',
                                     tags['EXIF:DateTimeOriginal'])
                        datestr = re.sub(r':', '-', m.group(1))
                        timestr = m.group(2)
                        print(datestr, timestr)
                
                    # EXIF:GPS metadata should be updated from GPX if
                    # --force was specified, or
                    # EXIF:GPSStatus is not in tags, or
                    # EXIF:GPSStatus is in tags with the value 0, or
                    # EXIFMeasureMode is in tags with a value < 2                      
            
    

def orientjpeg():
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
    transform = [[],
                 ['-flip horizontal'],
                 ['-rotate', '180'],
                 ['-flip', 'vertical'],
                 ['-transpose'],
                 ['-rotate', '90'],
                 ['-transverse'],
                 ['-rotate', '270']
                ]
    items = ['EXIF:Orientation']
    with exiftool.ExifTool() as et:
        for d in jpggps.dirs:
            if jpggps.verbosity > 0:
                print('Orient JPEG files in ' + d, file=sys.stderr)
            for f in os.listdir(d):
                newf = 'new' + f
                filebase, fileext = os.path.splitext(f)
                if fileext in ('.jpg', '.JPG', '.jpeg', '.JPEG'):
                    filepath = os.path.join(d, f)
                    newfilepath = os.path.join(d, newf)
                    tags = et.get_tags(items, filepath)
                    if jpggps.verbosity > 1:
                        for k in tags:
                            print(k, ' = ', tags[k], file=sys.stderr)
                    orient = int(tags['EXIF:Orientation'])
                    if orient:
                        jpegtran_cmd = (['jpegtran', '-copy', 'all'] +
                                        transform[orient - 1] +
                                        ['-outfile', newfilepath, filepath])
                        if jpggps.verbosity > 1:
                            print('jpegtran_cmd: ' + ' '.join(jpegtran_cmd), 
                                  file=sys.stderr)
                        try:                    
                            output = subprocess.call(jpegtran_cmd)
                            if not output:
                                os.remove(filepath)
                                os.rename(newfilepath, filepath)
                                
                        except OSError:
                            print(output, file=sys.stderr)
                            print('Is jpegtran installed?', file=sys.stderr)
                            raise

def makekml():
    """
    entry point for the method makekml
    """
    jpggps = jpggps2kml()
    jpggps.makekml()