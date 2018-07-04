from __future__ import absolute_import, division


__all__ = ["guideoffset"]
# m2 and scale directions need to be determined.
UM_PER_MM = 1000.


def guideoffset(tccActor, userCmd):
    """adjust collimation parameters
    """
    parsedCmd = userCmd.parsedCmd
    offRA, offDec, offRot, offFocus, multScale = parsedCmd.paramDict["offsets"].valueList
    cmdList = []
    if offRA or offDec:
        # ra dec offset wanted
        cmdList.append(tccActor.tcsDev.slewOffset(offRA, offDec))
    if offRot:
        cmdList.append(tccActor.tcsDev.rotOffset(offRot))
    if multScale != 1:
        # move scale, and update the focus offset
        absPosMM = tccActor.scaleMult2mm(multScale)
        extraFocusOffset = (absPosMM - tccActor.scaleDev.motorPos) * UM_PER_MM * tccActor.SCALE_RATIO * -1
        offFocus += extraFocusOffset
        cmdList.append(tccActor.scaleDev.move(absPosMM))
    if offFocus:
        cmdList.append(tccActor.secDev.focus(offFocus, offset=True))
    if not cmdList:
        userCmd.writeToUsers("w", "text='guideoffset command all zeros?'")
        userCmd.setState(userCmd.Done)
    else:
        userCmd.linkCommands(cmdList)
