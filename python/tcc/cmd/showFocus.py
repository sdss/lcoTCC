from __future__ import division, absolute_import

__all__ = ["showFocus"]

def showFocus(tccActor, userCmd, setDone=True):
    """Show the focus offset for the secondary mirror

    If not offset is specified, simply trigger a collimation update

    @param[in] tccActor  tcc actor
        reads tccActor.inst
    @param[in,out] userCmd  user command
    @param[in] setDone  set userCmd done when finished? (ignored if userCmd is already done)
    """
    focusVal = tccActor.tcsDev.status.statusFieldDict["focus"].value
    focusStr = "%0.4f"%focusVal if focusVal else "NaN"
    kwStr = "SecFocus=%s" % (focusStr,)
    tccActor.writeToUsers('i', kwStr, cmd=userCmd)
    if setDone and not userCmd.isDone:
        userCmd.setState(userCmd.Done)




