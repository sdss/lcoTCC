from __future__ import division, absolute_import

from twistedActor import CommandError, expandCommand


__all__ = ["target"]

# use track ra, dec icrs coords
# must we provide an equinox?


def target(tccActor, userCmd):
    """!Implement the target command, passing coords through to LCO TCS

    @param[in,out] tccActor  tcc actor;
    @param[in,out] userCmd  track command
    """
    parsedCmd = userCmd.parsedCmd
    posAngle = None
    if userCmd.parsedCmd.qualDict['posAngle'].boolValue:
        posAngle = float(userCmd.parsedCmd.qualDict['posAngle'].valueList[0])
    doHA = userCmd.parsedCmd.qualDict['ha'].boolValue
    doScreen = userCmd.parsedCmd.qualDict['screen'].boolValue
    abort = userCmd.parsedCmd.qualDict['abort'].boolValue
    #doBlock = userCmd.parsedCmd.qualDict['block'].boolValue

    if abort:
        tcsCmd = expandCommand()
        tccActor.tcsDev.abort_slews(tcsCmd)
        userCmd.setState(userCmd.Done)
        return

    coordPair = parsedCmd.paramDict["coordpair"].valueList
    if len(coordPair) != 2:
        raise CommandError("Must specify coordPair of solely ra, dec")
    ra, dec = coordPair
    # if do screen, turn on the FF lamp
    # else turn it off
    tcsCmd = expandCommand()
    # ffCmd = expandCommand()
    # userCmd.linkCommands([tcsCmd, ffCmd])
    tccActor.tcsDev.target(float(ra), float(dec), posAngle, doHA, doScreen, userCmd)

    # if doScreen:
    #     tccActor.secDev.lampOn(ffCmd)
    # else:
    #     tccActor.secDev.lampOff(ffCmd)
