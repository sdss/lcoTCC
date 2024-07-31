from __future__ import absolute_import, division
import numpy


__all__ = ["guideoffset"]
# m2 and scale directions need to be determined.
UM_PER_MM = 1000.


def guideoffset(tccActor, userCmd):
    """adjust collimation parameters
    """
    parsedCmd = userCmd.parsedCmd
    offRA, offDec, offRot, offFocus = parsedCmd.paramDict["offsets"].valueList
    if userCmd.parsedCmd.qualDict['waittime'].boolValue:
        userCmd.writeToUsers("w", "text=waittime is now an ignored parameter for guide offsets")

    # if userCmd.parsedCmd.qualDict['waittime'].boolValue:
    #     userCmd.writeToUsers("w", "text=waittime is now an ignored parameter")
    #     waitTime = float(userCmd.parsedCmd.qualDict['waittime'].valueList[0])
    # else:
    #     waitTime=None
    # if offRot and waitTime is not None:
    #     userCmd.writeToUsers("w", "text=waittime is ignored for rotator corrections")
    #     waitTime=None

    cmdList = []
    if offRot:
        cmdList.append(tccActor.tcsDev.rotOffset(offRot))
    if offRA or offDec:
        # ra dec offset wanted
        # calculate correct time to wait for an ra/dec offset
        # based on eyeballing various offsets in both axes with high frequency
        # telemetry.
        waitTime = 0

        # convert to absolute arcsecs from degrees
        # based on offset testing using felipe's
        # galil telemetry to measure offset times
        # as a function of offset size...
        absOffDec = numpy.abs(offDec) * 3600
        absOffRA = numpy.abs(offRA) * 3600

        if bool(absOffDec) and (absOffDec < 0.1):
            waitTime = 1.5
        if bool(absOffRA) and (absOffRA < 0.1):
            waitTime = 3
        if absOffDec >= 0.1:
            _wt = 0.5 + 1.078 + 0.074 * absOffDec
            if _wt > waitTime:
                waitTime = _wt
        if absOffRA >= 0.1:
            _wt = 0.5 + 2.5 + 0.097 * absOffRA
            if _wt > waitTime:
                waitTime = _wt

        cmdList.append(tccActor.tcsDev.slewOffset(offRA, offDec, waitTime=waitTime))
    if offFocus:
        cmdList.append(tccActor.secDev.focus(offFocus, offset=True))
    if not cmdList:
        userCmd.writeToUsers("w", "text='guideoffset command all zeros?'")
        userCmd.setState(userCmd.Done)
    else:
        userCmd.linkCommands(cmdList)
