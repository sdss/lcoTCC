from __future__ import division, absolute_import

__all__ = ["sec"]

def sec(tccActor, userCmd):
    """Implement sec device commands

    @param[in,out] tccActor  tcc actor

    @param[in,out] userCmd  a twistedActor BaseCommand with parseCmd attribute
    """
    parsedKeys = userCmd.parsedCmd.paramDict.keys()
    if "stop" in parsedKeys:
        tccActor.secDev.stop(userCmd)
    elif "move" in parsedKeys:
        value = userCmd.parsedKeys.paramDict["movevalue"]
        offset = userCmd.parsedCmd.qualDict["incremental"].boolValue
        tccActor.secDev.move(value, offset, userCmd)
    elif "status" in parsedKeys:
        tccActor.secDev.getStatus(userCmd)

