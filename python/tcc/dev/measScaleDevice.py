from __future__ import division, absolute_import

import numpy

from twistedActor import TCPDevice, log, DevCmd, CommandQueue, expandCommand

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
        self.tccStatus = None # set by tccLCOActor
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
        if not self.isHomed:
            return None
        else:
            return numpy.mean(self.encPos)

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
        userCmd = expandCommand(userCmd)
        self.getStatus(userCmd) # status links the userCmd
        return userCmd

    def getStatus(self, userCmd=None, timeLim=2):
        """!Read all enc positions 1-6 channels, 3 physical gauges.
        """
        # first flush the current status to ensure we don't
        # have stale values
        # print("reading migs!")
        userCmd = expandCommand(userCmd)
        statusDevCmd = DevCmd(cmdStr=READ_ENC)
        # statusDevCmd.addCallback(self._statusCallback)
        statusDevCmd.setTimeLimit(timeLim)
        userCmd.linkCommands([statusDevCmd])
        self.queueDevCmd(statusDevCmd)
        return userCmd

    def setCountState(self, userCmd=None, timeLim=1):
        """!Set the Mitutoyo EV counter into the counting state, and the
        current display state, this is required after a power cycle
        """
        userCmd = expandCommand(userCmd)
        devCmdList = [DevCmd(cmdStr=cmdStr) for cmdStr in [COUNTING_STATE, DISPLAY_CURR]]
        userCmd.linkCommands(devCmdList)
        for devCmd in devCmdList:
            devCmd.setTimeLimit(timeLim)
            self.queueDevCmd(devCmd)
        return userCmd

    def setZero(self, userCmd=None, timeLim=1):
        """!Zero set the mitutoyo gauges
        """
        userCmd = expandCommand(userCmd)
        zeroDevCmd = DevCmd(cmdStr=ZERO_SET)
        zeroDevCmd.setTimeLimit(timeLim)
        userCmd.linkCommands([zeroDevCmd])
        self.queueDevCmd(zeroDevCmd)
        return userCmd

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
        print("%s.handleReply(replyStr=%s)" % (self, replyStr))
        replyStr = replyStr.strip()
        if not replyStr:
            return
        if self.currExeDevCmd.isDone:
            # ignore unsolicited output?
            log.info("%s usolicited reply: %s for done command %s" % (self, replyStr, str(self.currExeDevCmd)))
            return

        if "error 15" in replyStr.lower():
            self.currExeDevCmd.writeToUsers("w", "Mitutoyo Error 15, not in counting state (was it power cycled?). Homing necessary.")
            self.encPos = [None]*6

        elif "error" in replyStr.lower():
            # some other error?
            self.currExeDevCmd.writeToUsers("w", "Mitutoyo EV counter Error output: " + replyStr)

        if self.currExeDevCmd.cmdStr == READ_ENC:
            # check that the expected prefix is seen
            # if not we are not in the 'current value state probably'
            if not replyStr.startswith(ENCVAL_PREFIX):
                self.encPos = [None]*6
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Mitutoyo gauges not in expected read state.  Homing necessary.")
            else:
                self.setEncValue(replyStr)
                # was this the 6th value read? if so we are done
                if replyStr.startswith(ENCVAL_PREFIX+"%i"%6):
                    self.currExeDevCmd.setState(self.currExeDevCmd.Done)
        if self.currExeDevCmd.cmdStr in [COUNTING_STATE, ZERO_SET, DISPLAY_CURR]:
            if replyStr == SUCESS:
                # successful set into counting state
                self.currExeDevCmd.setState(self.currExeDevCmd.Done)


    def queueDevCmd(self, devCmd):
        """Add a device command to the device command queue

        @param[in] devCmdStr: a command string to send to the device.
        @param[in] userCmd: a UserCmd associated with this device (probably but
                                not necessarily linked.  Used here for writeToUsers
                                reference.
        """
        devCmdStr = devCmd.cmdStr
        log.info("%s.queueDevCmd(devCmdStr=%r, cmdQueue: %r"%(self, devCmdStr, self.devCmdQueue))
        # print("%s.queueDevCmd(devCmdStr=%r, cmdQueue: %r"%(self, devCmdStr, self.devCmdQueue))
        # append a cmdVerb for the command queue (otherwise all get the same cmdVerb and cancel eachother)
        # could change the default behavior in CommandQueue?
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

