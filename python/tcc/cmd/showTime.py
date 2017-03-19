from __future__ import division, absolute_import
"""
From TCC documentation:
Returns the current time in several time systems. The time returned is the
time the command was parsed. There is not attempt to compensate for delays
in transmitting the time string. However, the various kinds of time returned
are consistent with each other. Note that there is a SET TIME command, but it
calibrates the TCC's clock from the observatory's time standard.

Returned keywords: TAI, UT1, LST, UTC_TAI.

    /**
    * Return the current TAI date (MJD seconds)
    *
    * @warning Assumes that the system clock is synchronized to TAI (not UTC, as is usually the case)!
    * Also assumes that the time function returns seconds since 1970-01-01 00:00:00 (true on unix and MacOS X).
    */
    double tai();
"""
from astropy.io import Time

__all__ = ["showTime"]

def showTime(tccActor, userCmd, setDone=True):
    """Implement the Show Time command

    @param[in,out] tccActor  tcc actor
    @param[in,out] userCmd  user command
    @param[in] setDone  set userCmd done? (ignored if userCmd is already done)
    """
    timeNow = Time.now()
    TAI = timeNow.tai.mjd*60*60*24
    UT1 = timeNow.ut1.mjd*60*60*24
    UTC = timeNow.mjd*60*60*24

    # LCOHACK! output bogus time (which shouldn't be used)
    # anywehre.  this is just to hide an error thrown
    # in accorkeys which tries to referesh time
    msgStrList = [
        "TAI=%0.3f" % (TAI,),
        # "LAST=%0.4f" % (currTAI,),
        "UT1=%0.3f" % (UT1,),
        "UTC_TAI=%0.0f" % (UTC-TAI,),
        "UT1_TAI=%0.3f" % (UT1-TAI,),
    ]
    msgStr = "; ".join(msgStrList)
    tccActor.writeToUsers('i', msgStr, cmd=userCmd)
    if setDone and not userCmd.isDone:
        userCmd.setState(userCmd.Done)
