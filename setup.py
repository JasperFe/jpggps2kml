# -*- coding: utf-8 -*-
"""
Created on Mon Mar  7 18:43:27 2016

@author: russell
"""

from setuptools import setup, find_packages
import sys

if sys.version_info[0] < 3:
    print('python version: ' + sys.version_info)
    print('The jpggps2kml package is only compatible with Python version 3.n')
    sys.exit(-1)

setup(name='jpggps2kml',
      description='Generate a kml path from GPS info in a set of jpeg files',
      author='Russell O. Redman',
      author_email='russell@roredman.ca',
      install_requires=['pykml','pyexiftool'],
      packages=find_packages(exclude=['*.test']),
      entry_points = {'jpggps': ['jpggps = jpggps2kml/jpggps2kml:run']}
      )
