from __future__ import division, absolute_import

from .showFocus import showFocus

__all__ = ["setFocus"]

def setFocus(tccActor, userCmd):
    """Set the focus offset for the secondary mirror via the LCO TCS

    @param[in,out] tccActor  tcc actor
    @param[in,out] userCmd  user command
    """
    def showFocusWhenDone(focusCmd):
        """@param[in] focusCmd, a twistedActor.UserCmd instance passed automatically via callback

        when the focus is done show the current value to users
        then set the user command done.
        """
        setDone = True
        if focusCmd.isDone:
            if focusCmd.didFail:
                userCmd.setState(userCmd.Failed, focusCmd.textMsg)
                setDone=False
            showFocus(tccActor, userCmd, setDone=setDone)
    valueList = userCmd.parsedCmd.paramDict["focus"].valueList[0].valueList
    if valueList is not None:
        value = valueList[0]
        if userCmd.parsedCmd.qualDict['incremental'].boolValue:
            focusCmd = tccActor.tcsDev.focusOffset(value)
        else:
            focusCmd = tccActor.tcsDev.focus(value)
        focusCmd.addCallback(showFocusWhenDone)
    else:
        # no focus value was received, just show current value
        showFocus(tccActor, userCmd, setDone=True)
