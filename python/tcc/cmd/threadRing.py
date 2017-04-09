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
            value += tccActor.scaleDev.encPos
        tccActor.scaleDev.move(value, userCmd)

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






