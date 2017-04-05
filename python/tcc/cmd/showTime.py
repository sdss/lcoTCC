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

__all__ = ["showTime"]

def showTime(tccActor, userCmd, setDone=True):
    """Implement the Show Time command

    @param[in,out] tccActor  tcc actor
    @param[in,out] userCmd  user command
    @param[in] setDone  set userCmd done? (ignored if userCmd is already done)
    """
    tccActor.status.outputTimeKWs(userCmd)
    if setDone and not userCmd.isDone:
        userCmd.setState(userCmd.Done)
