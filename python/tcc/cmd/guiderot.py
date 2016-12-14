from __future__ import division, absolute_import

__all__ = ["guiderot"]


def guiderot(tccActor, userCmd):
    """adjust collimation parameters
    """
    parsedCmd = userCmd.parsedCmd
    toggle = parsedCmd.paramDict["toggle"].valueList[0].keyword.lower()
    if toggle == "on":
        tccActor.tcsDev.doGuideRot = True
    else:
        tccActor.tcsDev.doGuideRot = False
    userCmd.setState(userCmd.Done)

