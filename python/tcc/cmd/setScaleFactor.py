from __future__ import division, absolute_import

from twistedActor import UserCmd

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
    motionCmd = UserCmd() # to be set done when scale move is done
    showScaleCmd = UserCmd() # to be set done when show scale is done

    def showScaleWhenDone(motionCmd):
        """@param[in] motionCmd, a twistedActor.UserCmd instance passed automatically via callback

        when the scale is done show the current value to users
        then set the user command done.
        """
        if motionCmd.isDone:
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

        focusOffset = (absPosMM - tccActor.scaleDev.encPos) * UM_PER_MM * tccActor.SCALE_RATIO * -1
        focusCmd = tccActor.secDev.focus(focusOffset, offset=True)
        scaleCmd = tccActor.scaleDev.move(absPosMM)
        userCmd.linkCommands([motionCmd, showScaleCmd])
        motionCmd.addCallback(showScaleWhenDone)
        motionCmd.linkCommands([scaleCmd, focusCmd])


    else:
        # no scale value received, just show current vale
        showScaleFactor(tccActor, userCmd, setDone=True)

