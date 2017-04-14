from __future__ import division, absolute_import

__all__ = ["showScaleFactor"]

def showScaleFactor(tccActor, userCmd, setDone=True):
    """Implement the "show scalefactor" command

    @param[in] tccActor  tcc actor
    @param[in,out] userCmd  user command
    @param[in] setDone  set userCmd done when finished? (ignored if userCmd is already done)
    """
    # query device for status to show most up to date scale factor
    def showScaleAfterStatus(statusCmd):
        """@param[in] statusCmd, a twistedActor.UserCmd instance passed automatically via callback

        when the status is done show the current value to users
        then set the user command done.
        """
        scaleFacStr = "%.6f"%tccActor.currentScaleFactor if tccActor.currentScaleFactor is not None else "NaN"
        scaleRangeStr = "%.6f, %.6f"%(tccActor.MIN_SF, tccActor.MAX_SF)
        tccActor.status.updateKWs(
            {
            "scaleFac": scaleFacStr,
            "scaleFacRange": scaleRangeStr,
            },
            userCmd,
        )
        if setDone and not userCmd.isDone:
            userCmd.setState(userCmd.Done)

    statusCmd = tccActor.scaleDev.getStatus()
    statusCmd.addCallback(showScaleAfterStatus)