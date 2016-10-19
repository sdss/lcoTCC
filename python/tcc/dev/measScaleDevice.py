from __future__ import division, absolute_import

import numpy

from twistedActor import TCPDevice, log, DevCmd, expandUserCmd, CommandQueue, LinkCommands

from RO.StringUtil import strFromException


__all__ = ["MeasScaleDevice"]

READ_ENC = "GA00"
COUNTING_STATE = "CS00"
DISPLAY_CURR = "CN00" # all axes to display current value (not max, etc)
ZERO_SET = "CR00"
SUCESS = "CH00"
ENCVAL_PREFIX = "GN0"

class MeasScaleDevice(TCPDevice):
    """!A Device for communicating with the LCO Scaling ring."""
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
        # the mitutoyos will be zeroed when the scaling ring is moved to 20
        # so this zero point keep track fo the offset.
        # if I could preset the mitutoyo's this would be unnecessary
        # the preset command "CP**" doesn't seem to work.
        self.zeroPoint = 20.0 # mm.  Position where scale = 1
        self.encPos = [None]*6

        self.devCmdQueue = CommandQueue({})

        TCPDevice.__init__(self,
            name = name,
            host = host,
            port = port,
            callFunc = callFunc,
            cmdInfo = (),
        )

    @property
    def position(self):
        # return the average value of all encoder positions
        # with respect to the zeroPoint
        # this is used for servoing the scaling ring
        return numpy.mean(self.encPos) + self.zeroPoint

    @property
    def isHomed(self):
        if None in self.encPos:
            return False
        else:
            return True

    @property
    def currExeDevCmd(self):
        return self.devCmdQueue.currExeCmd.cmd

    @property
    def currDevCmdStr(self):
        return self.currExeDevCmd.cmdStr


    def init(self, userCmd=None, timeLim=3, getStatus=True):
        """Called automatically on startup after the connection is established.
        Only thing to do is query for status or connect if not connected

        getStatus ignored?
        """
        log.info("%s.init(userCmd=%s, timeLim=%s, getStatus=%s)" % (self, userCmd, timeLim, getStatus))
        userCmd = expandUserCmd(userCmd)
        self.getStatus(userCmd) # status links the userCmd
        return userCmd

    def getStatus(self, userCmd=None, timeLim=1, linkState=True):
        """!Read all enc positions 1-6 channels, 3 physical gauges.
        """
        # first flush the current status to ensure we don't
        # have stale values
        print("reading migs!")
        userCmd = expandUserCmd(userCmd)
        self.encPos = [None]*6
        statusDevCmd = self.queueDevCmd(READ_ENC, userCmd)
        statusDevCmd.addCallback(self._statusCallback)
        statusDevCmd.setTimeLimit(timeLim)
        if linkState:
            LinkCommands(userCmd, [statusDevCmd])
            return userCmd
        else:
            # return the device command to be linked outside
            return statusDevCmd

    def setCountState(self, userCmd=None, timeLim=1):
        """!Set the Mitutoyo EV counter into the counting state,
        this is required after a power cycle
        """
        userCmd = expandUserCmd(userCmd)
        countDevCmd = self.queueDevCmd(COUNTING_STATE, userCmd)
        currValDevCmd = self.queueDevCmd(DISPLAY_CURR, userCmd)
        currValDevCmd.addCallback(self._statusCallback)
        countDevCmd.setTimeLimit(timeLim)
        currValDevCmd.setTimeLimit(timeLim)
        LinkCommands(userCmd, [countDevCmd, currValDevCmd])
        return userCmd

    def setZero(self, userCmd=None, timeLim=1):
        """!Set the Mitutoyo EV counter into the counting state,
        this is required after a power cycle
        """
        userCmd = expandUserCmd(userCmd)
        zeroDevCmd = self.queueDevCmd(ZERO_SET, userCmd)
        zeroDevCmd.setTimeLimit(timeLim)
        LinkCommands(userCmd, [zeroDevCmd])
        return userCmd

    def _statusCallback(self, statusCmd):
        # if statusCmd.isActive:
        #     # not sure this is necessary
        #     # but ensures we get a 100% fresh status
        #     self.status.flushStatus()
        if statusCmd.isDone and not statusCmd.didFail:
            self.writeStatusToUsers(statusCmd.userCmd)
            print("mig values,", self.encPos)
            print("done reading migs")

    def writeStatusToUsers(self, userCmd=None):
        self.writeToUsers("i", "ScaleZeroPos=%.4f"%self.zeroPoint)
        self.writeToUsers("i", self.encPosKWStr, userCmd)
        severity = "i"
        if not self.isHomed:
            severity = "w"
        self.writeToUsers(severity, self.encHomedKWStr, userCmd)


    @property
    def encPosKWStr(self):
        encPosStr = []
        for encPos in self.encPos[:3]:
            if encPos is None:
                encPosStr.append("?")
            else:
                encPos += self.zeroPoint
                encPosStr.append("%.3f"%encPos)
        return "ScaleEncPos=" + ", ".join(encPosStr[:3])

    @property
    def encHomedKWStr(self):
        homedInt = 1 if self.isHomed else 0
        return "ScaleEncHomed=%i"%homedInt

    def setEncValue(self, serialStr):
        """Figure out which gauge this line corresponds to and set the value
        """
        gaugeStr, gaugeVal = serialStr.split(",")
        if "error" in gaugeVal.lower():
            gaugeVal = None
        else:
            gaugeVal = float(gaugeVal)
        gaugeInd = int(gaugeStr.strip("GN0")) - 1
        self.encPos[gaugeInd] = gaugeVal

    def handleReply(self, replyStr):
        """Handle a line of output from the device.

        @param[in] replyStr   the reply, minus any terminating \n
        """
        log.info("%s.handleReply(replyStr=%s)" % (self, replyStr))
        replyStr = replyStr.strip()
        # print(replyStr, self.currExeDevCmd.cmdStr)
        if not replyStr:
            return
        if self.currExeDevCmd.isDone:
            # ignore unsolicited output?
            log.info("%s usolicited reply: %s for done command %s" % (self, replyStr, str(self.currExeDevCmd)))
            self.writeToUsers("i", "%s usolicited reply: %s for done command %s" % (self, replyStr, str(self.currExeDevCmd)))
            return

        if "error 15" in replyStr.lower():
            self.writeToUsers("w", "Mitutoyo Error 15, not in counting state (was it power cycled?). Homing necessary.")
            self.encPos = [None]*6

        elif "error" in replyStr.lower():
            # some other error?
            self.writeToUsers("w", "Mitutoyo EV counter Error output: " + replyStr)

        if self.currExeDevCmd.cmdStr == READ_ENC:
            # all encoders values have been read
            # set command done
            self.setEncValue(replyStr)
            # was this the 6th value read? if so we are done
            if replyStr.startswith(ENCVAL_PREFIX+"%i"%6):
                self.currExeDevCmd.setState(self.currExeDevCmd.Done)
        if self.currExeDevCmd.cmdStr in [COUNTING_STATE, ZERO_SET, DISPLAY_CURR]:
            if replyStr == SUCESS:
                # successful set into counting state
                self.currExeDevCmd.setState(self.currExeDevCmd.Done)


    def queueDevCmd(self, devCmdStr, userCmd):
        """Add a device command to the device command queue

        @param[in] devCmdStr: a command string to send to the device.
        @param[in] userCmd: a UserCmd associated with this device (probably but
                                not necessarily linked.  Used here for writeToUsers
                                reference.
        """
        log.info("%s.queueDevCmd(devCmdStr=%r, cmdQueue: %r"%(self, devCmdStr, self.devCmdQueue))
        #print("%s.queueDevCmd(devCmdStr=%r, cmdQueue: %r"%(self, devCmdStr, self.devCmdQueue))
        # append a cmdVerb for the command queue (otherwise all get the same cmdVerb and cancel eachother)
        # could change the default behavior in CommandQueue?
        devCmd = DevCmd(cmdStr=devCmdStr)
        devCmd.userCmd = userCmd
        devCmd.cmdVerb = devCmdStr
        self.devCmdQueue.addCmd(devCmd, self.startDevCmd)
        return devCmd


    def startDevCmd(self, devCmd):
        """
        @param[in] devCmd a dev command
        """
        log.info("%s.startDevCmd(%r)" % (self, devCmd.cmdStr))
        #print("%s.startDevCmd(%r)" % (self, devCmd.cmdStr))
        try:
            if self.conn.isConnected:
                log.info("%s writing %r" % (self, devCmd.cmdStr))
                devCmd.setState(devCmd.Running)
                self.conn.writeLine(devCmd.cmdStr)
            else:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Not connected")
        except Exception as e:
            self.currExeDevCmd.setState(self.currExeDevCmd.Failed, textMsg=strFromException(e))

