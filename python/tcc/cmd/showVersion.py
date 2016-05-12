from __future__ import division, absolute_import

from RO.StringUtil import quoteStr

import tcc

__all__ = ["showVersion"]

def showVersion(tccActor, userCmd):
    """
    @param[in,out] tccActor  tcc actor
    @param[in,out] userCmd  user command
    """
    kwStr = 'Version=%s' % (quoteStr(tcc.__version__),)
    userCmd.setState(userCmd.Done, hubMsg=kwStr)
