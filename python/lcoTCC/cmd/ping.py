from __future__ import division, absolute_import

__all__ = ["ping"]

def ping(tccActor, cmd):
    """Verify that actor is alive
    @param[in,out] tccActor  tcc actor
    @param[in,out] userCmd  ping command
    """
    cmd.setState(cmd.Done, textMsg="muahahahaha")
