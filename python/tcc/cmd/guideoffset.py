from __future__ import division, absolute_import

__all__ = ["guideoffset"]
# m2 and scale directions need to be determined.
UM_PER_MM = 1000.


def guideoffset(tccActor, userCmd):
    """adjust collimation parameters
    """
    parsedCmd = userCmd.parsedCmd
    offRA, offDec, offRot, offFocus, multScale = parsedCmd.paramDict["offsets"].valueList
    cmdList = []
    if offRA != 0 or offDec != 0:
        # ra dec offset wanted
        cmdList.append(tccActor.tcsDev.slewOffset(offRA, offDec))
    if offRot != 0:
        cmdList.append(tccActor.tcsDev.rotOffset(offRot))
    if multScale !=0:
        # move scale, and update the focus offset
        absPosMM = tccActor.scaleMult2mm(multScale)
        extraFocusOffset = (absPosMM - tccActor.scaleDev.encPos) * UM_PER_MM * tccActor.SCALE_RATIO * -1
        offFocus += extraFocusOffset
        cmdList.append(tccActor.scaleDev.move(absPosMM))
    if offFocus != 0:
        cmdList.append(tccActor.secDev.focus(offFocus, offset=True))
    if not cmdList:
        tccActor.writeToUsers("w", "text='guideoffset command all zeros?'")
        userCmd.setState(userCmd.Done)
    else:
        userCmd.linkCommands(cmdList)

