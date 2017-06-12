from __future__ import division, absolute_import


__all__ = ["threadRing"]
UM_PER_MM = 1000.

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
        doSec = quals["secondary"].boolValue
        if offset:
            value += tccActor.scaleDev.encPos
        if not doSec:
            tccActor.scaleDev.move(value, userCmd)
        else:
            # move M2 to maintain current focus
            scaleCmd = tccActor.scaleDev.move(value)
            focusOffset = (value - tccActor.scaleDev.encPos) * UM_PER_MM * tccActor.SCALE_RATIO * -1
            focusCmd = tccActor.secDev.focus(focusOffset, offset=True)
            userCmd.linkCommands([focusCmd, scaleCmd])

    elif "speed" in parsedKeys:
        value = params["speedvalue"].valueList[0]
        mult = quals["multiplicative"].boolValue
        if mult:
            value *= tccActor.scaleDev.status.speed
        tccActor.scaleDev.speed(value, userCmd)


    elif "status" in parsedKeys:
        # what do do here? both write to users should get same
        # user command but I don't want the command to be set done!
        tccActor.scaleDev.getStatus(userCmd)

    elif "home" in parsedKeys:
        tccActor.scaleDev.home(userCmd)






