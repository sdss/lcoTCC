from __future__ import division, absolute_import

__all__ = ["showScaleFactor"]

def showScaleFactor(tccActor, userCmd, setDone=True):
    """Implement the "show scalefactor" command

    @param[in] tccActor  tcc actor
        read tccActor.inst.maxScaleFac
    @param[in,out] userCmd  user command
    @param[in] setDone  set userCmd done when finished? (ignored if userCmd is already done)
    """
    kwStr = 'ScaleFac=%0.6f; ScaleFacRange=%0.6f, %0.6f' % (tccActor.scaleDev.currentScaleFactor, tccActor.scaleDev.minSF, tccActor.scaleDev.maxSF)
    tccActor.writeToUsers('i', kwStr, userCmd)
    if setDone and not userCmd.isDone:
        userCmd.setState(userCmd.Done)
