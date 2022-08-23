from __future__ import absolute_import, division


__all__ = ["guideoffset"]
# m2 and scale directions need to be determined.
UM_PER_MM = 1000.


def guideoffset(tccActor, userCmd):
    """adjust collimation parameters
    """
    parsedCmd = userCmd.parsedCmd
    offRA, offDec, offRot, offFocus = parsedCmd.paramDict["offsets"].valueList
    if userCmd.parsedCmd.qualDict['waittime'].boolValue:
        waitTime = float(userCmd.parsedCmd.qualDict['waittime'].valueList[0])
    else:
        waitTime=None
    if offRot and waitTime is not None:
        userCmd.writeToUsers("w", "text=waittime is ignored for rotator corrections")
        waitTime=None
    cmdList = []
    if offRA or offDec:
        # ra dec offset wanted
        cmdList.append(tccActor.tcsDev.slewOffset(offRA, offDec, waitTime=waitTime))
    if offRot:
        cmdList.append(tccActor.tcsDev.rotOffset(offRot))
    if offFocus:
        cmdList.append(tccActor.secDev.focus(offFocus, offset=True))
    if not cmdList:
        userCmd.writeToUsers("w", "text='guideoffset command all zeros?'")
        userCmd.setState(userCmd.Done)
    else:
        userCmd.linkCommands(cmdList)
