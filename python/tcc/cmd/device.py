from __future__ import division, absolute_import
"""For LCO TCC Device command
"""

__all = ["device"]

# a mapping between command parameter string and
# method to be called on the device
devMethodDict = {
    "initialize": "init",
    "status": "getStatus",
    "connect": "connect",
    "disconnect": "disconnect",
}

def device(tccActor, userCmd):
    """Execute the device command (LCO only)

    @param[in,out] tccActor  tcc actor
    @param[in,out] userCmd  device command (twistedActor command)
    """
    cmdVerb = userCmd.parsedCmd.paramDict['command'].valueList[0].keyword.lower()
    devNameList = [devCmd.keyword.lower() for devCmd in userCmd.parsedCmd.paramDict['device'].valueList]
    devDict = {
        "tcs": tccActor.tcsDev,
        "scale": tccActor.scaleDev,
        "sec": tccActor.secDev,
        # "lamp": tccActor.ffDev,
        "measscale": tccActor.measScaleDev,
    }
    if "all" in devNameList:
        devNameList = devDict.keys()

    # scale device explicitly get status from meas scale
    # so if this is status and both those devs are present
    # remove the meas scale
    if cmdVerb == "status" and "measscale" in devNameList and "scale" in devNameList:
        print("removing measscale from devNameList")
        devNameList = list(set(devNameList) - set(["measscale"]))
        print("devNameList", devNameList)

    # was a time limit specified?
    if userCmd.parsedCmd.qualDict['timelimit'].boolValue:
        userCmd.setTimeLimit(userCmd.parsedCmd.qualDict['timelimit'].valueList[0])
    devCmds = []
    devAttr = devMethodDict[cmdVerb]
    for devName in devNameList:
        dev = devDict[devName]
        devCmds.append(getattr(dev, devAttr)())
    userCmd.linkCommands(devCmds)
    return True
