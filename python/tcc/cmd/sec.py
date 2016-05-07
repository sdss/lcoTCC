from __future__ import division, absolute_import

__all__ = ["sec"]

def sec(tccActor, userCmd):
    """Implement sec device commands

    @param[in,out] tccActor  tcc actor

    @param[in,out] userCmd  a twistedActor BaseCommand with parseCmd attribute
    """
    params = userCmd.parsedCmd.paramDict
    quals = userCmd.parsedCmd.qualDict
    parsedKeys = params.keys()
    if "stop" in parsedKeys:
        tccActor.secDev.stop(userCmd)
    elif "move" in parsedKeys:
        values = params["movevalue"].valueList
        offset = quals["incremental"].boolValue
        tccActor.secDev.move(values, offset, userCmd)
    elif "status" in parsedKeys:
        tccActor.secDev.getStatus(userCmd)

