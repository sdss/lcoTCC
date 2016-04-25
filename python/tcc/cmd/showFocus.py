from __future__ import division, absolute_import

__all__ = ["showFocus"]

def showFocus(tccActor, userCmd, setDone=True):
    """Show the focus for the secondary mirror

    @param[in] tccActor  tcc actor
    @param[in,out] userCmd  user command
    @param[in] setDone  set userCmd done when finished? (ignored if userCmd is already done)
    """
    def showFocusAfterStatus(statusCmd):
        """@param[in] statusCmd, a twistedActor.UserCmd instance passed automatically via callback

        when the status is done show the current value to users
        then set the user command done.
        """
        focusVal = tccActor.tcsDev.status.statusFieldDict["focus"].value
        focusStr = "%0.4f"%focusVal if focusVal else "NaN"
        kwStr = "SecFocus=%s" % (focusStr,)
        tccActor.writeToUsers('i', kwStr, cmd=userCmd)
        if setDone and not userCmd.isDone:
            userCmd.setState(userCmd.Done)

    statusCmd = tccActor.tcsDev.getStatus()
    statusCmd.addCallback(showFocusAfterStatus)


