from __future__ import division, absolute_import

from twistedActor import LinkCommands

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
            value += tccActor.measScaleDev.position
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
        threadCmd = tccActor.scaleDev.getStatus()
        encCmd = tccActor.measScaleDev.getStatus()
        LinkCommands(userCmd, [threadCmd, encCmd])
    elif "home" in parsedKeys:
        setCountCmd = tccActor.measScaleDev.setCountState()
        def zeroEncoders(_homeCmd):
            if _homeCmd.isDone:
                if _homeCmd.didFail:
                    userCmd.setState(userCmd.Failed, "Failed to move scaling ring to home position")
                else:
                    # set/get encoder readings
                    tccActor.measScaleDev.setHome(homePos=tccActor.scaleDev.status.homePosition, userCmd=userCmd)
        def homeThreadRing(_setCountCmd):
            if _setCountCmd.isDone:
                if _setCountCmd.didFail:
                    userCmd.setState(userCmd.Failed, "Failed to set Mitutoyo EV counter into counting state")
                else:
                    moveCmd = tccActor.scaleDev.move(tccActor.measScaleDev.zeroPoint)
                    moveCmd.addCallback(zeroEncoders)
        setCountCmd.addCallback(homeThreadRing)





