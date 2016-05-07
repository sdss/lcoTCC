from __future__ import division, absolute_import


__all__ = ["threadRing"]

def threadRing(tccActor, userCmd):
    """Implement direct thread ring commands

    @param[in,out] tccActor  tcc actor

    @param[in,out] userCmd  a twistedActor BaseCommand with parseCmd attribute
    """
    params = userCmd.parsedCmd.paramDict
    quals = userCmd.parsedCmd.qualDict
    parsedKeys = params.keys()
    if "stop" in parsedKeys:
        tccActor.scaleDev.stop(userCmd)
    elif "move" in parsedKeys:
        value = params["movevalue"].valueList[0]
        offset = quals["incremental"].boolValue
        if offset:
            value += tccActor.scaleDev.status.position
        tccActor.scaleDev.move(value, userCmd)
    elif "speed" in parsedKeys:
        value = params["speedvalue"].valueList[0]
        mult = quals["multiplicative"].boolValue
        if mult:
            value *= tccActor.scaleDev.status.speed
        tccActor.scaleDev.speed(value, userCmd)
    elif "zero" in parsedKeys:
        if "zerovalue" in parsedKeys and params["zerovalue"].valueList:
            value = params["zerovalue"].valueList[0]
        else:
            # set current position as zero point
            value = None
        tccActor.scaleDev.setScaleZeroPoint(value, userCmd)
    elif "status" in parsedKeys:
        tccActor.scaleDev.getStatus(userCmd)

