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
from RO.Astro.Sph.AzAltFromHADec import azAltFromHADec
from RO.StringUtil import degFromDMSStr
import numpy
# from scipy.interpolate import interp1d
# import matplotlib.pyplot as plt

# ffs_alt_limit = 19.1  # flat field screen altutude limit
# telescope_alt_limit = 45.7  # min telescope altitude at which the screen can be used

ffs_alt_limit = 18
telescope_alt_limit = 49.2

LAT = -29
degPerHour = 15.0


#--------------------- joses shit ---------------------------
# Flat field screen model
# Telescope azimuth is S to E.
telescope_alt_az_jose = numpy.array([[90, 0],
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
ffs_dome_alt_az_jose = numpy.array([[64.2, 180.0],
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
# telescope_alt = numpy.append(telescope_alt_az[:, 0], 45.7)
# ffs_alt = numpy.append(ffs_dome_alt_az[:, 0], ffs_alt_limit)
# ffs_alt_interp = interp1d(telescope_alt, ffs_alt, kind='linear')

# --------------------- Juan's shit ----------------------------------------


haDecJuanCmd = numpy.array([
    [60, -30],
    [45, -30],
    [30, -30],
    [15, -30],
    [-30, -30],
    [-45, -30],
    [-15, -30],
    [-15, 0],
    [-30, 0],
    [0,0],
    [15,0],
    [30,0],
    [-45,-60],
    [-30,-60],
    [-15,-60],
    [0,-60],
    [15,-60],
    [30,-60],
    [45,60],
    [60,-60],
    [-60,60]
])


altAzJuanFix = numpy.array([
    azAltFromHADec([degFromDMSStr("3:07:54")*degPerHour, degFromDMSStr("-29:09:56")], LAT)[0][::-1], # FIXED, below limit
    azAltFromHADec([degFromDMSStr("2:59:54")*degPerHour, degFromDMSStr("-30:09:44")], LAT)[0][::-1],
    azAltFromHADec([degFromDMSStr("1:59:56")*degPerHour, degFromDMSStr("-30:08:46")], LAT)[0][::-1],
    azAltFromHADec([degFromDMSStr("0:59:56")*degPerHour, degFromDMSStr("-30:02:28")], LAT)[0][::-1],
    azAltFromHADec([degFromDMSStr("-2:00:00")*degPerHour, degFromDMSStr("-30:00:55")], LAT)[0][::-1],
    azAltFromHADec([degFromDMSStr("-2:59:59")*degPerHour, degFromDMSStr("-30:00:55")], LAT)[0][::-1],
    azAltFromHADec([degFromDMSStr("-1:00:01")*degPerHour, degFromDMSStr("-30:03:44")], LAT)[0][::-1],
    azAltFromHADec([degFromDMSStr("-1:00:04")*degPerHour, degFromDMSStr("-00:03:20")], LAT)[0][::-1],
    azAltFromHADec([degFromDMSStr("-2:00:03")*degPerHour, degFromDMSStr("-00:01:39")], LAT)[0][::-1],
    azAltFromHADec([degFromDMSStr("-00:00:04")*degPerHour, degFromDMSStr("-00:04:29")], LAT)[0][::-1],
    azAltFromHADec([degFromDMSStr("00:59:55")*degPerHour, degFromDMSStr("-00:05:52")], LAT)[0][::-1],
    azAltFromHADec([degFromDMSStr("1:59:55")*degPerHour, degFromDMSStr("-00:07:01")], LAT)[0][::-1],
    azAltFromHADec([degFromDMSStr("-2:19:45")*degPerHour, degFromDMSStr("-60:03:03")], LAT)[0][::-1], #FIXED
    azAltFromHADec([degFromDMSStr("-1:59:46")*degPerHour, degFromDMSStr("-60:03:26")], LAT)[0][::-1],
    azAltFromHADec([degFromDMSStr("-0:59:49")*degPerHour, degFromDMSStr("-60:04:54")], LAT)[0][::-1],
    azAltFromHADec([degFromDMSStr("0:00:08")*degPerHour, degFromDMSStr("-60:06:14")], LAT)[0][::-1],
    azAltFromHADec([degFromDMSStr("1:00:05")*degPerHour, degFromDMSStr("-60:07:31")], LAT)[0][::-1],
    azAltFromHADec([degFromDMSStr("2:00:03")*degPerHour, degFromDMSStr("-60:08:38")], LAT)[0][::-1],
    azAltFromHADec([degFromDMSStr("2:27:01")*degPerHour, degFromDMSStr("-60:08:55")], LAT)[0][::-1], #FIXED
    azAltFromHADec([degFromDMSStr("2:30:01")*degPerHour, degFromDMSStr("-58:32:36")], LAT)[0][::-1], #FIXED
    azAltFromHADec([degFromDMSStr("-2:21:46")*degPerHour, degFromDMSStr("-58:25:13")], LAT)[0][::-1], #FIXED
])


domeScreenJuanFix = numpy.array([
    [253.8, 19.1],
    [252.7, 20.8],
    [254.9, 34.5],
    [253.7, 48.5],
    [101.1, 34.0],
    [103.4, 19.9],
    [101.8, 47.0],
    [29.7, 29.2],
    [50.5, 19.3],
    [360.0, 33.0],
    [329.1, 28.8],
    [307.8, 20.1],
    [153.3, 18.9],
    [155.6, 20.6],
    [165.6, 25.3],
    [177.9, 26.9],
    [190.7, 25.8],
    [201.1, 21.1],
    [204.8, 18.9],
    [207, 19.5],
    [151.1, 19.5],
    ])

screenJuanFix = domeScreenJuanFix[:,1].flatten()


# ------------------------------ sergio's shit -----------------------------

altAzSergio = numpy.array([
    azAltFromHADec([degFromDMSStr("-00:50:00")*degPerHour, degFromDMSStr("-39:30:01")], LAT)[0][::-1],
    azAltFromHADec([degFromDMSStr("00:07:00")*degPerHour, degFromDMSStr("-50:38:22.9")], LAT)[0][::-1],
    # outlier azAltFromHADec([degFromDMSStr("-01:41:00")*degPerHour, degFromDMSStr("-56:02:12")], LAT)[0][::-1],
    azAltFromHADec([degFromDMSStr("00:58:00")*degPerHour, degFromDMSStr("-26:49:50")], LAT)[0][::-1],
    azAltFromHADec([degFromDMSStr("00:18:00")*degPerHour, degFromDMSStr("-49:55:43")], LAT)[0][::-1],
    # outlier azAltFromHADec([degFromDMSStr("00:01:00")*degPerHour, degFromDMSStr("-02:09:04")], LAT)[0][::-1],
])

screenSergio = numpy.asarray([
    47.1,
    39,
    #23, outlier
    49,
    38,
    #29 outlier
])


# ------------------------------- Richard carla ------------------------#
#HAasked      decasked     HAreal      decreal      screenalt    comment
#-----------------------------------------------------------------------
richard = numpy.array([
[22.59027778,  -22.6766667 , 22.5875    , -22.6594166 , 39.1],
[23.856944  ,  -09.1475    , 23.85      , -09.12625   , 31.1],
[16.275     ,  -15.9255555 , 16.2708333 , -15.912806  , 40.0],
[02.2958333 ,  -48.672777  , 02.3125    , -48.6761944 , 38.2],
[23.288611  ,  -26.048333  , 23.2833333 , -26.0322222 , 39.1],
[00.757777  ,  -29.3636111 , 00.7583333 , -29.3721666 , 57.8],
[00.666944  ,  -34.113888  , 00.6708333 , -34.1255556 , 53.0],
[01.3525    ,  -21.545833  , 01.3916667 , -21.5551944 , 53.0],
[22.93333   ,  -18.783333  , 22.9291667 , -18.7698055 , 38.2],
[-20.566667 ,  -1.2        , -20.566667 , -1.24411111 , 26.4],  #Off centre by +6deg in az
[-22.5      ,  -31.433333  , -22.4875   , -31.4911111 , 40.1],     #Off centre by +5deg in az
[-23.2916667,  -11.6416667 , -23.2975   , -11.6983333 , 32.0],     #Off centre by +5deg in az
[-23.366667 ,  -24.0333333 , -23.358333 , -24.0945556 , 39.0],     #Off centre by +5deg in az
[-23.975    ,  -18.4583333 , -23.966667 , -18.521     , 36.0],     #Off centre by +5deg in az
[-23.308333 ,  -33.5583333 , -23.295833 , -33.6247778 , 39.2],     #Off centre by +5deg in az
[-23.9069444,  -27.1083333 , -23.895833 , -27.1772222 , 37.1],     #Off centre by +5deg in az
[-23.9666667,  -04.2583333 , -23.9625   , -04.3231944 , 26.7],     #Off centre by +5deg in az
[-23.5963889,  -28.0416667 , -23.583333 , -28.1136944 , 39.2],     #Off centre by +5deg in az
[-00.5      ,  -36.0000000 , -00.4875   , -36.0385    , 51.0],
[-00.5      ,  -26.0000000 , -00.495833 , -26.0388055 , 57.8],
])

altAzRicahrd = []
for hadec in richard[:,2:4]:
    # print(hadec)
    altAzRicahrd.append(azAltFromHADec(hadec, LAT)[0][::-1])
altAzRichard = numpy.asarray(altAzRicahrd)

richardScreen = richard[:,-1].flatten()
# --------------------------- plot shit ---------------------------------------

# plt.figure()
# plt.plot(telescope_alt_az_jose[:, 0], ffs_dome_alt_az_jose[:, 0], "ok")
# plt.plot(altAzJuanFix[:, 0], screenJuanFix, "or")
# plt.plot(altAzSergio[:,0], screenSergio, "og")
# plt.plot(altAzRichard[:,0], richardScreen, "ob")
# plt.ylabel("screen alt")
# plt.xlabel("telescope alt")
# plt.show()




# Creates a linear interpolation for altitude. At some point we may want to also include azimuth.
# telescope_alt = numpy.append(telescope_alt_az[:, 0], 45.7)
# ffs_alt = numpy.append(ffs_dome_alt_az[:, 0], ffs_alt_limit)
#ffs_alt_interp = interp1d(telescope_alt_az_jose[:,0], ffs_dome_alt_az_jose[:,0], kind='linear')
#pfitJ = numpy.polyfit(telescope_alt_az_jose[:,0], ffs_dome_alt_az_jose[:,0], 1)

allAltAz = numpy.vstack([
    altAzJuanFix,
    altAzSergio,
    altAzRichard,
    ])

allScreen = numpy.hstack([screenJuanFix, screenSergio, richardScreen])

# filter for telesope alt > 55 (looks linear here)
allAltCutInds = allAltAz[:,0]>55
allAltCut = allAltAz[allAltCutInds]
allScreenCut = allScreen[allAltCutInds]

allAltCutIndsJ = telescope_alt_az_jose[:, 0]>55
allAltCutJ =  telescope_alt_az_jose[allAltCutIndsJ]
allScreenCutJ = ffs_dome_alt_az_jose[allAltCutIndsJ]

# plt.figure()
# plt.plot(allAltCut[:,0], allScreenCut, 'ok')
# plt.plot(allAltCutJ[:, 0], allScreenCutJ[:, 0], 'or')
# plt.show()

pfitJose = numpy.polyfit(allAltCutJ[:,0], allScreenCutJ[:,0], 1)
pfitRest = numpy.polyfit(allAltCut[:,0], allScreenCut, 1)

# find screen offset between jose's measurements and teh most recent ones

joseOffset = pfitJose[-1] - pfitRest[-1]
# adjust jose's screen measurements
ffs_dome_alt_az_jose[:,0] = ffs_dome_alt_az_jose[:,0] - joseOffset

# plt.figure()
# plt.plot(allAltAz[:,0], allScreen, 'ok')
# plt.plot(telescope_alt_az_jose[:, 0], ffs_dome_alt_az_jose[:, 0], 'or')
# plt.show()

# combine all
allTelAlt = numpy.hstack((allAltAz[:,0].flatten(), telescope_alt_az_jose[:, 0].flatten()))
allScreenAlt = numpy.hstack((allScreen, ffs_dome_alt_az_jose[:, 0].flatten()))

pfitAll = numpy.polyfit(allTelAlt, allScreenAlt, 2)

def get_ffs_altitude(tel_altitude):
    if tel_altitude < telescope_alt_limit:
        return ffs_alt_limit, True
    out = 0
    pfitRev = reversed(pfitAll)
    for ii, coeff in enumerate(pfitRev):
        out += x**ii*coeff
    return out, False

# x = numpy.arange(min(allTelAlt), max(allTelAlt), 1)
# y = applyFit(x)

# plt.figure()
# plt.plot(x,y,'r')
# plt.plot(allTelAlt, allScreenAlt, 'ok')
# plt.show()

# plt.figure()
# plt.plot(allTelAlt, allScreenAlt - applyFit(allTelAlt), 'ok')
# plt.ylim([-3,3])
# plt.xlim([45, 90])
# plt.show()
#

def get_ffs_altitude_previous(tel_altitude):
    """Returns the FFS altitude to command for a certain telescope altitude.

    Returns a tuple with the FFS altitude and a boolean indicating if the screen is the minimum
    altitude.

    """

    if tel_altitude < telescope_alt_limit:
        return ffs_alt_limit, True

    # -4 reported by obsevers to be usual required offset from model
    return ffs_alt_interp(tel_altitude)-4, False
