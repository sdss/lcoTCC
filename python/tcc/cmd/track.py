# from __future__ import division, absolute_import

# from twistedActor import CommandError

# __all__ = ["track"]

# use track ra, dec icrs coords
# must we provide an equinox?


# def track(tccActor, userCmd):
#     """!Implement the track command, pass through to LCO TCS

#     @param[in,out] tccActor  tcc actor;
#     @param[in,out] userCmd  track command
#     """
#     parsedCmd = userCmd.parsedCmd
#     coordSysParam = parsedCmd.paramDict["coordsys"]
#     val = coordSysParam.valueList[0]
#     name = val.keyword
#     if not name == "icrs":
#         raise CommandError("%s coordSys not supported at LCO"%name)
#     if val.valueList:
#         raise CommandError("%s coordSys date input not supported at LCO"%str(val.valueList[0]))
#     coordPair = parsedCmd.paramDict["coordpair"].valueList
#     if len(coordPair) != 2:
#         raise CommandError("Must specify coordPair of solely ra, dec")
#     ra, dec = coordPair
#     tccActor.tcsDev.slew(float(ra), float(dec), userCmd)

