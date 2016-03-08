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
from pykml.factory import ATOM_ElementMaker as ATOM
from pykml.factory import GX_ElementMaker as GX
from lxml import etree
import exiftool

import argparse
import configparser
from datetime import datetime
import os
import os.path
import re
import sys
import time

def run():
    """
    Parse command line arguments
    For each directory find the list of JPEG file and GPX files
        Extract EXIF metadata from each JPEG file

    """
    ap = argparse.ArgumentParser()
    ap.add_argument('-c', '--config',
                    default='jpggps.config',
                    help='configuration file with values for arguments in the [arguments] section')
    ap.add_argument('-t', '--timezone',
                    help='timezone ofset from UTC in the format (+/-)hhmm, eg. PST = -0800, PDT = -0700')
    ap.add_argument('-o', '--output',
                    help='output filename')
    ap.add_argument('-u', '--url',
                    help='''base url for files, e.g.
                               for disk files file:///absolute/path/to/directory/
                               for files on the web http://host.domain/path/to/dir/''')
    ap.add_argument('-p', '--progress',
                    choices=['none','normal','debug'],
                    help='progress message detail')
    ap.add_argument('dir', nargs='*',
                    help='directories to search for JPEG files')
    a = vars(ap.parse_args())

    # Read default config values from the configuration file
    config = configparser.ConfigParser()

    # Set default argument values
    config['arguments'] = {}
    args = config['arguments']
    args['dir'] = ['.']
    args['progress'] = 'normal'

    if 'config' in a:
        configfile = os.path.expanduser(os.path.expandvars(a['config']))
        if os.path.exists(configfile):
            config.read(configfile)
        else:
            print('config file not found at ' + configfile, file=sys.stderr)

    # Override selected config values from the command line
    for key in a:
        if a[key]:
            args[key] = a[key]

    if args['output']:
        OUT = open(args['output'], 'w')
    else:
        OUT = sys.stdout

    if args['dir']:
        args['dir'] = os.path.expanduser(os.path.expandvars(args['dir']))

    verbosity = 1
    if args['progress'] == 'quiet':
        verbosity = 0
    elif args['progress'] == 'debug':
        verbosity = 2

    CDATAPREFIX = ''
    CDATASUFFIX = ''
    if args['url']:
        CDATAPREFIX = '<![CDATA[<img src="' + args['url']
        CDATASUFFIX = '" width=400/><br/>Test caption<br/>]]>'

    dirlist = []
    for d in args['dir']:
        dd = os.path.abspath(os.path.expanduser(os.path.expandvars(d)))
        if not os.path.isdir(dd):
            print(dd + ' is not a directory', file=sys.stderr)
            sys.exit(-1)
        dirlist.append(dd)

    with exiftool.ExifTool() as et:
        # Extract time, orientation and GPS metadata from EXIF
        items = ['EXIF:DateTimeOriginal',
                 'EXIF:GPSStatus',
                 'EXIF:GPSMeasureMode',
                 'EXIF:GPSLongitude',
                 'EXIF:GPSLongitudeRef',
                 'EXIF:GPSLatitude',
                 'EXIF:GPSLatitudeRef',
                 'EXIF:GPSAltitude']

        places = {}
        for d in dirlist:
            for root, dirs, files in os.walk(d):
                basedir = os.path.basename(root)
                if not re.match(r'\d{4}.*', basedir):
                    print('skipping ' + root, file=sys.stderr)
                    continue
                if verbosity > 0:
                    print('search for JPEG files in ' + root, file=sys.stderr)

                if basedir not in places:
                    places[basedir] = {}
                for f in files:
                    filebase, fileext = os.path.splitext(f)
                    if fileext in ('.jpg', '.JPG', '.jpeg', '.JPEG'):
                        filepath = os.path.join(root, f)
                        in_kml = ''

                        tags = et.get_tags(items, filepath)
                        if verbosity > 1:
                            for k in tags:
                                print(k, ' = ', tags[k], file=sys.stderr)

                        if 'EXIF:GPSLongitude' in tags:
                            # GPS metadata id available
                            lat = lon = date = None
                            alt = 0
                            active = full = False
                            picture_time = ''
                            picture_place = ''

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
                                datetimestr = datestr + 'T' + m.group(2)

                            if "EXIF:GPSStatus" in tags and \
                               'A' == tags['EXIF:GPSStatus']:

                                active = True

                            if "EXIF:GPSMeasureMode" in tags and \
                               int(tags['EXIF:GPSMeasureMode']) > 1:

                                full = True

                            if "EXIF:GPSAltitude" in tags:
                                alt = tags['EXIF:GPSAltitude']

                            if verbosity > 1:
                                print(active,
                                      full,
                                      datestr,
                                      datetimestr,
                                      lat,
                                      lon,
                                      alt,
                                      '\n',
                                      file=sys.stderr)

                            if active and full and datetimestr and lat and lon:
                                in_kml = ' in kml'
                                places[basedir][filebase] = {}
                                places[basedir][filebase]['date'] = datestr
                                places[basedir][filebase]['time'] = \
                                    GX.when(datetimestr)
                                places[basedir][filebase]['place'] = \
                                    GX.coord('{0} {1} {2}'.format(lon, lat, alt))
                                places[basedir][filebase]['point'] = \
                                    KML.Point(
                                        KML.coordinates('{0},{1},{2}'.format\
                                                        (lon, lat, 0)))
                                places[basedir][filebase]['filename'] = f

                        if verbosity > 0:
                            print('    ' + f, in_kml, file=sys.stderr)

            colorIndex = 0
            # Define a cycle of line styles that can be assigned to
            # successive tracks
            colorSet = ('bfff3f3f',
                        '7f00ff00',
                        '7f0000ff',
                        '7fffff00',
                        '7fff00ff',
                        '7f00ffff')

            track_folder = KML.Folder()
            placemark_folder = KML.Folder()
            for dir in sorted(places.keys()):
                colorStyle = '#color' + str(colorIndex)
                placemark = KML.Placemark(
                    KML.visibility('1'),
                    KML.name(dir),
                    KML.description('Displays the path taken to acquire the '
                                    'pictures in ' + dir),
                    KML.styleUrl(colorStyle)
                    )
                colorIndex = (colorIndex + 1) % len(colorSet)

                track = GX.Track(
                    KML.altitudeMode('clampToGround')
                    )
                for jpg in sorted(places[dir].keys()):
                    # append when elements
                    track.append(places[dir][jpg]['time'])
                for jpg in sorted(places[dir].keys()):
                    # append coord elements
                    track.append(places[dir][jpg]['place'])
                placemark.append(track)
                track_folder.append(placemark)

                for jpg in sorted(places[dir].keys()):
                    placemark_folder.append( KML.Placemark(
                        KML.visibility('1'),
                        KML.styleUrl('#picture'),
                        KML.name(jpg),
                        KML.description('CDATAPREFIX' + \
                                        places[dir][jpg]['filename'] + \
                                        'CDATASUFFIX'),
                        places[dir][jpg]['point']
                    ))

            doc = KML.Document(
                      KML.description('Tracks derived from Exif GPS in ' + \
                                      os.path.basename(d)),
                      KML.visibility('1'),
                      KML.open('1'),
                      KML.name("JPEG GPS Position track")
                  )

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

            for colorIndex in range(len(colorSet)):
                normal = colorSet[colorIndex]
                highlight = 'ff' + normal[2:]
                colorName = 'color' + str(colorIndex)

                doc.append(
                    KML.Style(
                        KML.IconStyle(
                            KML.Icon(),
                            id="no_icon_n"
                        ),
                        KML.LineStyle(
                            KML.color(normal),
                            KML.width('6')
                        ),
                        id=(colorName + '_n')
                    )
                )
                doc.append(
                    KML.Style(
                        KML.IconStyle(
                            KML.Icon(),
                            id="no_icon_h"
                        ),
                        KML.LineStyle(
                            KML.color(highlight),
                            KML.width('8')
                        ),
                        id=(colorName + '_h')
                    )
                )
                doc.append(
                    KML.StyleMap(
                        KML.Pair(
                            KML.key('normal'),
                            KML.styleUrl('#' + colorName + '_n')
                        ),
                        KML.Pair(
                            KML.key('highlight'),
                            KML.styleUrl('#' + colorName + '_h')
                        ),
                        id=colorName
                    )
                )

            doc.append(track_folder)
            doc.append(placemark_folder)
            kml = KML.kml(doc)
            kmlstr = str(etree.tostring(kml, pretty_print=True),
                         encoding='UTF-8')
            kmlstr = re.sub(r'CDATAPREFIX', CDATAPREFIX, kmlstr)
            kmlstr = re.sub(r'CDATASUFFIX', CDATASUFFIX, kmlstr)

            print(kmlstr, file=OUT)
            if OUT is not sys.stdout:
                OUT.close()
