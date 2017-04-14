from __future__ import division, absolute_import

__all__ = ["help"]


def help(tccActor, userCmd):
    """adjust collimation parameters
    """
    for cmd, cmdObj in tccActor.cmdParser.cmdDefDict.iteritems():
        helpList = cmdObj.getFullHelp()
        for helpStr in helpList:
            userCmd.writeToUsers("i", helpStr)
        userCmd.writeToUsers("i", "-----")
    userCmd.setState(userCmd.Done)

