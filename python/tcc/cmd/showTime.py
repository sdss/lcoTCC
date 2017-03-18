from __future__ import division, absolute_import
"""
From TCC documentation:
Returns the current time in several time systems. The time returned is the
time the command was parsed. There is not attempt to compensate for delays
in transmitting the time string. However, the various kinds of time returned
are consistent with each other. Note that there is a SET TIME command, but it
calibrates the TCC's clock from the observatory's time standard.

Returned keywords: TAI, UT1, LST, UTC_TAI.
"""
import time

__all__ = ["showTime"]

def showTime(tccActor, userCmd, setDone=True):
    """Implement the Show Time command

    @param[in,out] tccActor  tcc actor
    @param[in,out] userCmd  user command
    @param[in] setDone  set userCmd done? (ignored if userCmd is already done)
    """
    currTAI = time.time() - 36.

    # LCOHACK! output bogus time (which shouldn't be used)
    # anywehre.  this is just to hide an error thrown
    # in accorkeys which tries to referesh time
    msgStrList = [
        "TAI=%0.3f" % (currTAI,),
        "LAST=%0.4f" % (currTAI,),
        "UT1=%0.3f" % (currTAI,),
        "UTC_TAI=%0.0f" % (currTAI,),
        "UT1_TAI=%0.3f" % (currTAI,),
    ]
    msgStr = "; ".join(msgStrList)
    tccActor.writeToUsers('i', msgStr, cmd=userCmd)
    if setDone and not userCmd.isDone:
        userCmd.setState(userCmd.Done)
