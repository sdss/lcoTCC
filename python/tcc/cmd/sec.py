from __future__ import division, absolute_import

__all__ = ["sec"]

def sec(tccActor, userCmd):
    """Implement m2 device commands

    @param[in,out] tccActor  tcc actor

    @param[in,out] userCmd  a twistedActor BaseCommand with parseCmd attribute
    """
    import pdb; pdb.set_trace()




    # valueList = userCmd.parsedCmd.paramDict["scalefactor"].valueList[0].valueList
    # if valueList:
    #     scaleFac = valueList[0]
    #     mult = userCmd.parsedCmd.qualDict['multiplicative'].boolValue
    #     if mult:
    #         absPosMM = tccActor.scaleMult2mm(scaleFac)
    #     else:
    #         # an absolute move, convert scale to mm
    #         absPosMM = tccActor.scale2mm(scaleFac)
    #     # verify move is within limits:
    #     if mult:
    #         scaleFac = tccActor.currentScaleFactor * scaleFac
    #     if not (tccActor.MIN_SF <= scaleFac <= tccActor.MAX_SF):
    #         # scale factor out of range:
    #         userCmd.setState(userCmd.Failed, "Desired ScaleFactor out of range: %.6f"%scaleFac)
    #         return
    #     scaleCmd = tccActor.scaleDev.move(absPosMM)
    #     scaleCmd.addCallback(showScaleWhenDone)
    # else:
    #     # no scale value received, just show current vale
    #     showScaleFactor(tccActor, userCmd, setDone=True)

