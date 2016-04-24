from __future__ import division, absolute_import

# from RO.StringUtil import strFromException

from twistedActor import TCPDevice, log, UserCmd, expandUserCmd

__all__ = ["ScaleDevice"]


class ScaleDevice(TCPDevice):
    """!A Device for communicating with the LCO Scaling ring."""
    maxSF = 1.0008 # max scale factor from tcc25m/inst/default.dat
    minSF = 1./maxSF  # min scale factor
    MMPerScaleRange = 50 / float((maxSF - minSF)) # update this with a real number
    def __init__(self, name, host, port, callFunc=None):
        """!Construct a ScaleDevice

        Inputs:
        @param[in] name  name of device
        @param[in] host  host address of scaling ring controller
        @param[in] port  port of scaling ring controller
        @param[in] callFunc  function to call when state of device changes;
                note that it is NOT called when the connection state changes;
                register a callback with "conn" for that task.
        """
        self.currentPos = None
        self.targetPos = None
        self.currCmd = UserCmd()
        self.currCmd.setState(self.currCmd.Done)
        self.currDevCmdStr = ""

        TCPDevice.__init__(self,
            name = name,
            host = host,
            port = port,
            callFunc = callFunc,
            cmdInfo = (),
        )

    @property
    def currCmdVerb(self):
        return self.currDevCmdStr.split()[0]

    @property
    def targetScaleFactor(self):
        return self.mm2scale(self.targetPos)

    @property
    def currentScaleFactor(self):
        return self.mm2scale(self.currentPos)

    def scale2mm(self, scaleValue):
        # choose 100 steps range, centered at 50 for scale=1
        return (scaleValue - self.minSF) * self.MMPerScaleRange + 50

    def mm2scale(self, mm):
        return (mm - 50) / float(self.MMPerScaleRange) + self.minSF

    def init(self, userCmd=None, timeLim=None, getStatus=False):
        """Called automatically on startup after the connection is established.
        Only thing to do is query for status or connect if not connected
        """
        log.info("%s.init(userCmd=%s, timeLim=%s, getStatus=%s)" % (self, userCmd, timeLim, getStatus))
        userCmd = expandUserCmd(userCmd)
        if getStatus:
            return self.getStatus(userCmd=userCmd)
        else:
            userCmd.setState(userCmd.Done)
            return userCmd

    def getStatus(self, userCmd=None, timeLim=None):
        """!Get status of the device
        """
        userCmd = expandUserCmd(userCmd)
        self.sendCmd("status", userCmd)
        return userCmd

    def handleReply(self, replyStr):
        """Handle a line of output from the device.

        @param[in] replyStr   the reply, minus any terminating \n
        """
        log.info("%s.handleReply(replyStr=%s)" % (self, replyStr))
        replyStr = replyStr.strip()
        if not replyStr:
            return
        # check if this is an ok
        gotOK = False
        if replyStr == "OK":
            gotOK = True
        elif replyStr.endswith(" OK"):
            gotOK = True
            replyStr.strip(" OK")
        if "ERROR" in replyStr:
            self.currCmd.setState(self.currCmd.Failing, replyStr)
            return
        if "HARDWARE_FAULT" in replyStr:
            faultCode = replyStr.split()[-1]
            if faultCode != "NONE":
                self.currCmd.setState(self.currCmd.Failed, replyStr)
                return
        if "INSTRUCTION_FAULT" in replyStr:
            faultCode = replyStr.split()[-1]
            if faultCode != "NONE":
                self.currCmd.setState(self.currCmd.Failed, replyStr)
                return
        if "CURRENT_POSITION" in replyStr:
            self.currentPos = float(replyStr.split()[-1])
        if "TARGET_POSITION" in replyStr:
            self.targetPos = float(replyStr.split()[-1])
        if gotOK:
            if self.currCmd.isDone:
                raise RuntimeError("Got OK for an already done command: %r"%self.currCmd)
            if self.currCmd.state == self.currCmd.Failing:
                # got the ok, fully fail the command now
                self.currCmd.setState(self.currCmd.Failed, self.currCmd.textMsg)
            else:
                self.currCmd.setState(self.currCmd.Done)


    def sendCmd(self, devCmdStr, userCmd):
        """!Execute the command
        @param[in] devCmdStr  a string to send to the scale controller
        @param[in] userCmd  a user command
        """
        # use try/except here?
        if not self.conn.isConnected:
            log.error("%s cannot write %r: not connected" % (self, userCmd.cmdStr))
            userCmd.setState(userCmd.Failed, "not connected")
            return
        if not self.currCmd.isDone:
            log.error("%s cannot write %r: existing command %r not finished" % (self, userCmd.cmdStr, self.currCmd.cmdStr))
            userCmd.setState(userCmd.Failed, "device is busy")
            return
        self.currCmd = userCmd
        self.currDevCmdStr = devCmdStr
        log.info("%s writing %s" % (self, devCmdStr))
        self.conn.writeLine(devCmdStr)

    def move(self, scaleFactor, userCmd=None):
        """Set the scale factor, move the scaling ring
        set userCmd to done when the scaling ring is in place

        @param[in] scaleFactor: a float, scale value to be converted to steps and sent to motor
        @param[in] userCmd: a twistedActor BaseCommand
        """
        log.info("%s.move(scaleFactor=%.6f, userCmd=%s)" % (self, scaleFactor, userCmd))
        userCmd=expandUserCmd(userCmd)
        targetPos = self.scale2mm(scaleFactor)
        moveCmdStr = "move %.8f"%(targetPos)
        self.sendCmd(moveCmdStr, userCmd)
        return userCmd

    def stop(self, userCmd=None):
        """Stop any scaling movement, cancelling any currently executing
        move

        @param[in] userCmd: a twistedActor BaseCommand
        """
        userCmd=expandUserCmd(userCmd)
        if self.currDevCmdStr == "move" and not self.currCmd.isDone:
            self.currCmd.setState(self.currCmd.Cancelled, "Move Stopped")
        self.sendCmd("stop", userCmd)
        return userCmd



