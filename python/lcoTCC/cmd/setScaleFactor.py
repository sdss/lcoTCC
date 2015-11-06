from __future__ import division, absolute_import

from .showScaleFactorLCO import showScaleFactor

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
        if userCmd.parsedCmd.qualDict['multiplicative'].boolValue:
            scaleFac *= tccActor.scaleDev.currentScaleFactor
        if not (tccActor.scaleDev.minSF <= scaleFac <= tccActor.scaleDev.maxSF):
            userCmd.setState(userCmd.Failed,
                textMsg="Scale factor %0.6f invalid; must be in range [%0.6f, %0.6f]" % (scaleFac, tccActor.scaleDev.minSF, tccActor.scaleDev.maxSF),
            )
            return

        scaleCmd = tccActor.scaleDev.move(scaleFac)
        scaleCmd.addCallback(showScaleWhenDone)
    else:
        # no scale value received, just show current vale
        showScaleFactor(tccActor, userCmd, setDone=True)

