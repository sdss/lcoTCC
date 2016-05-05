from __future__ import division, absolute_import

from .showScaleFactor import showScaleFactor

__all__ = ["setScaleFactor"]

def setScaleFactor(tccActor, userCmd):
    """Implement Set ScaleFactor

    @param[in,out] tccActor  tcc actor

    @param[in,out] userCmd  a twistedActor BaseCommand with parseCmd attribute
    """
    def showScaleWhenDone(scaleCmd):
        """@param[in] scaleCmd, a twistedActor.UserCmd instance passed automatically via callback

        when the scale is done show the current value to users
        then set the user command done.
        """
        setDone = True
        if scaleCmd.isDone:
            if scaleCmd.didFail:
                userCmd.setState(userCmd.Failed, scaleCmd.textMsg)
                setDone=False
            showScaleFactor(tccActor, userCmd, setDone=setDone)
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
        scaleCmd = tccActor.scaleDev.move(absPosMM)
        scaleCmd.addCallback(showScaleWhenDone)
    else:
        # no scale value received, just show current vale
        showScaleFactor(tccActor, userCmd, setDone=True)

