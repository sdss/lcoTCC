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
        tccActor.secDev.lampOff(userCmd)
    elif action == "on":
        tccActor.secDev.lampOn(userCmd)
    else:
        tccActor.secDev.getStatus(userCmd)





