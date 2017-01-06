from __future__ import division, absolute_import

__all__ = ["help"]


def help(tccActor, userCmd):
    """adjust collimation parameters
    """
    for cmd, cmdObj in tccActor.cmdParser.cmdDefDict.iteritems():
        helpList = cmdObj.getFullHelp()
        for helpStr in helpList:
            tccActor.writeToUsers("i", helpStr, userCmd)
        tccActor.writeToUsers("i", "-----", userCmd)
    userCmd.setState(userCmd.Done)

