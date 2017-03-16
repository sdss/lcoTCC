#!/usr/bin/env python
# encoding: utf-8
#
# ffs.py
#
# Created by José Sánchez-Gallego on 15 Feb 2017.


from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

import numpy
from scipy.interpolate import interp1d


ffs_alt_limit = 19.1  # flat field screen altutude limit
telescope_alt_limit = 45.7  # min telescope altitude at which the screen can be used


# Flat field screen model
# Telescope azimuth is S to E.
telescope_alt_az = numpy.array([[90, 0],
                                [80, 0],
                                [70, 0],
                                [60, 0],
                                [50, 0],
                                [80, 180],
                                [70, 180],
                                [60, 180],
                                [50, 180],
                                [80, 30],
                                [80, 90],
                                [80, 150],
                                [80, 210],
                                [80, 270]])

# Dome azimuth is N to E.
ffs_dome_alt_az = numpy.array([[64.2, 180.0],
                               [55.5, 180.0],
                               [47.0, 180.0],
                               [34.5, 180.0],
                               [25.6, 180.0],
                               [55.4, 358.8],
                               [46.7, 358.8],
                               [34.9, 358.8],
                               [24.0, 358.8],
                               [55.0, 150.0],
                               [55.3, 90.0],
                               [55.4, 24.8],
                               [55.0, 325.0],
                               [54.5, 268.0]])


# Creates a linear interpolation for altitude. At some point we may want to also include azimuth.
telescope_alt = numpy.append(telescope_alt_az[:, 0], 45.7)
ffs_alt = numpy.append(ffs_dome_alt_az[:, 0], ffs_alt_limit)
ffs_alt_interp = interp1d(telescope_alt, ffs_alt, kind='linear')


def get_ffs_altitude(tel_altitude):
    """Returns the FFS altitude to command for a certain telescope altitude.

    Returns a tuple with the FFS altitude and a boolean indicating if the screen is the minimum
    altitude.

    """

    if tel_altitude < telescope_alt_limit:
        return ffs_alt_limit, True

    return ffs_alt_interp(tel_altitude), False
