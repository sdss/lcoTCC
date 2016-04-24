from __future__ import division, absolute_import
"""The TCC (telescope control code) interface shim for the Las Campanas Observatory du Pont telescope
"""
import sys
import traceback

from RO.StringUtil import strFromException

from twistedActor import CommandError, BaseActor

from .tccLCOCmdParser import TCCLCOCmdParser
from ..version import __version__

tcsHost = "localhost"
tcsPort = 0
scaleHost = "localhost"
scalePort = 1


class TCCLCOActor(BaseActor):
    """!TCC actor for the LCO telescope
    """
    def __init__(self,
        userPort,
        tcsDev,
        scaleDev,
        name = "TCCLCOActor",
    ):
        """Construct a TCCActor

        @param[in] userPort  port on which to listen for users
        @param[in] tcsDev a TCSDevice instance
        @param[in] scaleDev  a ScaleDevice instance
        @param[in] name  actor name; used for logging
        """
        self.tcsDev = tcsDev
        self.tcsDev.writeToUsers = self.writeToUsers
        self.scaleDev = scaleDev
        self.scaleDev.writeToUsers = self.writeToUsers
        self.cmdParser = TCCLCOCmdParser()
        BaseActor.__init__(self, userPort=userPort, maxUsers=1, name=name, version=__version__)
        # Actor.__init__(self, userPort=userPort, maxUsers=1, name=name, devs=(tcsDev, scaleDev), version=__version__)

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