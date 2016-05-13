from __future__ import division, absolute_import

from twistedActor import LinkCommands, UserCmd

from .showScaleFactor import showScaleFactor

__all__ = ["setScaleFactor"]

# m2 and scale directions need to be determined.
UM_PER_MM = 1000.

def setScaleFactor(tccActor, userCmd):
    """Implement Set ScaleFactor

    @param[in,out] tccActor  tcc actor

    @param[in,out] userCmd  a twistedActor BaseCommand with parseCmd attribute

    Increasing scale decreses focal length.  Increasing scale moves M1 towards
    M2.  To maintain current focus the M2 must also move fractionally in the
    same direction
    """
    showScaleCmd = UserCmd() # to be set done when scale is shown
    def showScaleWhenDone(scaleCmd):
        """@param[in] scaleCmd, a twistedActor.UserCmd instance passed automatically via callback

        when the scale is done show the current value to users
        then set the user command done.
        """
        if scaleCmd.isDone:
            showScaleFactor(tccActor, showScaleCmd, setDone=True)

    valueList = userCmd.parsedCmd.paramDict["scalefactor"].valueList[0].valueList
    if valueList:
        scaleFac = valueList[0]
        mult = userCmd.parsedCmd.qualDict['multiplicative'].boolValue
        if mult:
            absPosMM = tccActor.scaleMult2mm(scaleFac)
        else:
            # an absolute move, convert scale to mm
            absPosMM = tccActor.scale2mm(scaleFac)
        # verify move is within limits:
        if mult:
            scaleFac = tccActor.currentScaleFactor * scaleFac
        if not (tccActor.MIN_SF <= scaleFac <= tccActor.MAX_SF):
            # scale factor out of range:
            userCmd.setState(userCmd.Failed, "Desired ScaleFactor out of range: %.6f"%scaleFac)
            return
        # check if M2 is moving, if not move that the desired amount
        if tccActor.secDev.isBusy:
            userCmd.setState(userCmd.Failed, "Cannot set scale, M2 is moving.")
            return
        # did scale increase or decrease?
        # careful with conventions
        newScale = tccActor.mm2scale(absPosMM)
        if newScale > tccActor.currentScaleFactor:
            # scale increases, focal lengh decreases,
            # M2 moves away from M1
            # as LCO greater increase focus moves away
            # from M2
            offsetDir = 1
        else:
            # move M2 other direction ...
            offsetDir = -1
        # determine magnitude of offset
        # convert to microns
        # apply scaling ratio
        # command M2 move
        focusOffset = offsetDir * (absPosMM - tccActor.scaleDev.status.position) * UM_PER_MM * tccActor.SCALE_RATIO
        focusCmd = tccActor.secDev.focus(focusOffset, offset=True)
        scaleCmd = tccActor.scaleDev.move(absPosMM)
        scaleCmd.addCallback(showScaleWhenDone) # showScale command sets done showScaleCmd
        # user cmd is not done until all three of the
        # commands below have finshied
        LinkCommands(userCmd, [scaleCmd, focusCmd, showScaleCmd])

    else:
        # no scale value received, just show current vale
        showScaleFactor(tccActor, userCmd, setDone=True)

