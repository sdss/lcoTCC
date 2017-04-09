from __future__ import division, absolute_import

__all__ = ["lamp"]

def lamp(tccActor, userCmd):
    """Implement direct ff lamp command

    @param[in,out] tccActor  tcc actor

    @param[in,out] userCmd  a twistedActor BaseCommand with parseCmd attribute
    """
    params = userCmd.parsedCmd.paramDict
    action = params["action"].valueList[0].keyword
    if action == "off":
        tccActor.ffDev.powerOff(userCmd)
    elif action == "on":
        tccActor.ffDev.powerOn(userCmd)
    else:
        tccActor.ffDev.getStatus(userCmd)





