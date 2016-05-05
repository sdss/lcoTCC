from __future__ import division, absolute_import
"""The TCC (telescope control code) interface shim for the Las Campanas Observatory du Pont telescope
"""
import sys
import traceback

from RO.StringUtil import strFromException

from twistedActor import CommandError, BaseActor, DeviceCollection

from .tccLCOCmdParser import TCCLCOCmdParser
from ..version import __version__

# tcsHost = "localhost"
# tcsPort = 0
# scaleHost = "localhost"
# scalePort = 1

__all__ = ["TCCLCOActor"]

"""
From Paul's email regarding scaling solution:

focal plane focal plane      focal      ratio           Scale
location        location        length                          Change
BFDr        BFDp                                                1 parts in
(inches)        (mm)        (mm)
10           993            18868.78
10.04        994                 18870.37       1.0000843    8.43e-5
9.96                 992            18867.18        0.9999152       -8.48e-5

So lets say that a scale change +8.45e05 as reported by the guider requires a plate motion of up by 1mm (towards the primary)
                 and  a scale change -8.45e05 as reported by the guider requires a plate motion of down by 1mm (away from the primary)
"""

class TCCLCOActor(BaseActor):
    """!TCC actor for the LCO telescope
    """
    SCALE_PER_MM = 8.45e-05
    MAX_SF = 1.0008 # max scale factor from tcc25m/inst/default.dat
    MIN_SF = 1./MAX_SF  # min scale factor
    def __init__(self,
        userPort,
        tcsDev,
        scaleDev,
        m2Dev,
        name = "tcc",
    ):
        """Construct a TCCActor

        @param[in] userPort  port on which to listen for users
        @param[in] tcsDev a TCSDevice instance
        @param[in] scaleDev  a ScaleDevice instance
        @param[in] m2Dev a M2Device instance
        @param[in] name  actor name; used for logging
        """
        self.tcsDev = tcsDev
        self.tcsDev.writeToUsers = self.writeToUsers
        self.scaleDev = scaleDev
        self.scaleDev.writeToUsers = self.writeToUsers
        self.m2Dev = m2Dev
        self.m2Dev.writeToUsers = self.writeToUsers
        self.dev = DeviceCollection([self.tcsDev, self.scaleDev, self.m2Dev]) # auto connection looks for self.dev
        # connect devices
        self.tcsDev.connect()
        self.scaleDev.connect()
        self.m2Dev.connect()
        self.cmdParser = TCCLCOCmdParser()
        BaseActor.__init__(self, userPort=userPort, maxUsers=1, name=name, version=__version__)
        # Actor.__init__(self, userPort=userPort, maxUsers=1, name=name, devs=(tcsDev, scaleDev), version=__version__)

    @property
    def currentScaleFactor(self):
        return self.mm2scale(self.scaleDev.status.position)

    def scale2mm(self, scaleValue):
        return scaleValue / self.SCALE_PER_MM + self.scaleDev.status.scaleZero

    def mm2scale(self, mm):
        return (mm - self.scaleDev.status.scaleZero) * self.SCALE_PER_MM

    def scaleMult2mm(self, multiplier):
        # avoid use of SCALE_PER_MM for numerical stability
        return (self.scaleDev.status.position - self.scaleDev.status.scaleZero)*float(multiplier) + self.scaleDev.status.scaleZero

    def parseAndDispatchCmd(self, cmd):
        """Dispatch the user command

        @param[in] cmd  user command (a twistedActor.UserCmd)
        """
        if not cmd.cmdBody:
            # echo to show alive
            self.writeToOneUser(":", "", cmd=cmd)
            return
        try:
            cmd.parsedCmd = self.cmdParser.parseLine(cmd.cmdBody)
        except Exception as e:
            cmd.setState(cmd.Failed, "Could not parse %r: %s" % (cmd.cmdBody, strFromException(e)))
            return

        #cmd.parsedCmd.printData()
        if cmd.parsedCmd.callFunc:
            cmd.setState(cmd.Running)
            try:
                cmd.parsedCmd.callFunc(self, cmd)
            except CommandError as e:
                cmd.setState("failed", textMsg=strFromException(e))
                return
            except Exception as e:
                sys.stderr.write("command %r failed\n" % (cmd.cmdStr,))
                sys.stderr.write("function %s raised %s\n" % (cmd.parsedCmd.callFunc, strFromException(e)))
                traceback.print_exc(file=sys.stderr)
                textMsg = strFromException(e)
                hubMsg = "Exception=%s" % (e.__class__.__name__,)
                cmd.setState("failed", textMsg=textMsg, hubMsg=hubMsg)
        else:
            raise RuntimeError("Command %r not yet implemented" % (cmd.parsedCmd.cmdVerb,))