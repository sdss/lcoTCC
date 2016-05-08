from __future__ import division, absolute_import

from twistedActor import CommandError


__all__ = ["offset"]

# offset arc ra, dec
# offset guide?
# do we want calib offsets?

def offset(tccActor, userCmd):
    """!Implement the offset command for the LCO TCS

    @param[in,out] tccActor  tcc actor;
    @param[in,out] userCmd  track command
    """
    parsedCmd = userCmd.parsedCmd
    offsetType = parsedCmd.paramDict["type"].valueList[0].keyword.lower()
    if offsetType not in  ["arc", "guide"]:
        raise CommandError("offset type of %s not supported for LCO"%offsetType)
    coordSet = parsedCmd.paramDict["coordset"].valueList
    if offsetType == "arc":
        if len(coordSet) != 2:
            raise CommandError("Must specify coordSet of solely ra, dec")
        ra, dec = coordSet
        tccActor.tcsDev.slewOffset(ra, dec, userCmd)
    else:
        if not coordSet[0] == coordSet[1] == 0 or len(coordSet) != 3:
            raise CommandError("Guide offset must be solely in rotation")
        offsetRot = coordSet[-1]

