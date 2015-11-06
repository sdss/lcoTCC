from __future__ import division, absolute_import
"""The TCC (telescope control code) for the Apache Point Observatory 2.5m telescope
"""
import syslog

from twistedActor import Actor

from .tccLCOCmdParser import TCCLCOCmdParser
from ..version import __version__

tcsHost = "localhost"
tcsPort = 0
scaleHost = "localhost"
scalePort = 1


class TCCLCOActor(Actor):
    """!TCC actor for the LCO telescope
    """
    Facility = syslog.LOG_LOCAL1
    def __init__(self,
        userPort,
        tcsDev,
        scaleDev,
        name = "TCCLCOActor",
    ):
        """Construct a TCCActor

        @param[in] userPort  port on which to listen for users
        @param[in] tcsDev a LCODevice instance
        @param[in] scaleDev  a ScaleDevice instance
        @param[in] name  actor name; used for logging
        """
        self.tcsDev = tcsDev
        self.scaleDev = scaleDev
        self.cmdParser = TCCLCOCmdParser()
        Actor.__init__(self, userPort=userPort, maxUsers=1, name=name, devs=(tcsDev, scaleDev), version=__version__)
