from __future__ import division, absolute_import

from twistedActor import CommandError

__all__ = ["target"]

# use track ra, dec icrs coords
# must we provide an equinox?


def target(tccActor, userCmd):
    """!Implement the target command, passing coords through to LCO TCS

    @param[in,out] tccActor  tcc actor;
    @param[in,out] userCmd  track command
    """
    parsedCmd = userCmd.parsedCmd
    coordSysParam = parsedCmd.paramDict["coordsys"]
    val = coordSysParam.valueList[0]
    name = val.keyword
    doHA = userCmd.parsedCmd.qualDict['ha'].boolValue
    if not name == "icrs":
        raise CommandError("%s coordSys not supported at LCO"%name)
    if val.valueList:
        raise CommandError("%s coordSys date input not supported at LCO"%str(val.valueList[0]))
    if not tccActor.scaleDev.status.loaded:
        raise CommandError("Cartridge not loaded")
    if not tccActor.scaleDev.status.locked:
        raise CommandError("Cartridge not locked")
    coordPair = parsedCmd.paramDict["coordpair"].valueList
    if len(coordPair) != 2:
        raise CommandError("Must specify coordPair of solely ra, dec")
    ra, dec = coordPair
    tccActor.tcsDev.target(float(ra), float(dec), doHA, userCmd)

