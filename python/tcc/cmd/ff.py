from __future__ import division, absolute_import

__all__ = ["ff"]

def ff(tccActor, userCmd):
    """Controls the FF lamp via de TCS

    @param[in,out] tccActor  tcc actor

    @param[in,out] userCmd  a twistedActor BaseCommand with parseCmd attribute
    """
    params = userCmd.parsedCmd.paramDict
    action = params["action"].valueList[0].keyword
    if action == "off":
        tccActor.tcsDev.handleFFLamp(False, userCmd)
    elif action == "on":
        tccActor.tcsDev.handleFFLamp(True, userCmd)
    else:
        tccActor.tcsDev.getStatus(userCmd)
