from __future__ import division, absolute_import

from twistedActor import CommandError
import coordConv

__all__ = ["getCoordSys", "makeCoordSys", "OldCoordSysCodeNameDict", "CoordCmdNameDict"]

SecPerYear = coordConv.SecPerDay * coordConv.DaysPerYear

# dict of lowercase TCC coordsys name: (coordConv coordsys name, default date)
# for coordinate systems supported by coordConv (see _OtherCoordSysSet for the others)
_CoordSysDict = dict(
    icrs = ("icrs", 0),
    fk5 = ("fk5", 2000.0),
    fk4 = ("fk4", 1950.0),
    galactic = ("gal", 0),
    geocentric = ("appgeo", 0),
    topocentric = ("apptopo", 0),
    observed = ("obs", 0),
    none = ("none", 0),
)

# set of acceptable other TCC coordinate system names (lowercase)
_OtherCoordSysSet = set(("mount", "instrument", "gimage", "gprobe", "ptcorr", "rotator"))

# dict of coordSys TCC command name (lowercase): coordConv coordSys name
CoordCmdNameDict = dict((key, val[0]) for key, val in _CoordSysDict.iteritems())
for name in _OtherCoordSysSet:
    CoordCmdNameDict[name] = name

def getCoordSys(param):
    """!Obtain a coordinate system from a parsed parameter
    
    @param[in] param  the parsed parameter
    @return a coordinate system as a shared_ptr to a subclass of coordConv.CoordSys, or None if not present
        (returning a shared_ptr allows the result to be used to set Obj.userSys)
    
    @throw twistedActor.CommandError if the coordinate system is unrecognized
    """
    if not param.boolValue:
        # no coordinate system specified
        return None
    if len(param.valueList) != 1:
        raise RuntimeError("Bug: expected one coordSys keyword for /%s but got %s" % (param.name, param.valueList))
    
    val = param.valueList[0]
    name = val.keyword

    if val.valueList:
        date = val.valueList[0]
    else:
        date = 0

    name = val.keyword
    return makeCoordSys(name=name, date=date)

def makeCoordSys(name, date):
    """!Make a coordinate system from its name and date

    Unlike coordConv.makeCoordSys this supports focal plane coordinate systems

    @param[in] name  coordinate system name used by the command parser (case insensitive)
    @param[in] date  coordinate system date, or None for default date
    """
    lcName = name.lower()
    if lcName in _OtherCoordSysSet:
        if name.lower() in ("gimage", "gprobe") and date is None:
            raise CommandError("Must specify guide probe number for %s coordinates" % (name,))
        return coordConv.OtherCoordSys(lcName, date or 0).clone() # clone to get shared_ptr
    try:
        ccName, defDate = _CoordSysDict[lcName]
    except KeyError:
        raise RuntimeError("Unrecognized coordSys %r" % (name,))
    if date is None:
        date = defDate
    return coordConv.makeCoordSys(ccName, date)

# dict of old TCC coordinate system code: coordinate system name used by the command parser
# warning: the new TCC does not have Physical coordinates and the old TCC does not have PtCorr coordinates
OldCoordSysCodeNameDict = {
    -9: "GImage",
    -8: "GProbe",
    -7: "Rotator",
    -6: "Instrument",

    -5: "Mount",
    #-4: "Physical", # the new TCC does not support physical coordinates

    -3: "Observed",
    -2: "Topocentric",
    -1: "Geocentric",

    0: "None",

    1: "FK4",
    2: "FK5",
    3: "Galactic",
    4: "ICRS",
}

