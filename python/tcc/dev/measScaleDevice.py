from __future__ import division, absolute_import

import re

import numpy

from twistedActor import TCPDevice, log, DevCmd, CommandQueue, expandCommand

from RO.StringUtil import strFromException

__all__ = ["MeasScaleDevice"]

READ_PREFIX = "GA0"
READ_ENC1 = "GA01"
READ_ENC2 = "GA02"
READ_ENC3 = "GA03"
COUNTING_STATE = "CS00"
DISPLAY_CURR = "CN00" # all axes to display current value (not max, etc)
ZERO_SET = "CR00"
SUCCESS = "CH00"
# ENCVAL_PREFIX = "GN"

gaugeRE = re.compile("GN0(?P<gauge>[1-6]),(?P<value>[+-]?([0-9]*[.])?[0-9]+)")

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
        self.encPos = [None]*3
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
        #self.getStatus(userCmd) # status links the userCmd
        return userCmd

    def getStatus(self, userCmd=None, timeLim=2):
        """!Read all enc positions 1-6 channels, 3 physical gauges.
        """
        # print("getStatus measScaleDev")
        # first flush the current status to ensure we don't
        # have stale values
        # print("reading migs!")
        userCmd = expandCommand(userCmd)
        readGauge1 = DevCmd(cmdStr=READ_ENC1)
        readGauge2 = DevCmd(cmdStr=READ_ENC2)
        readGauge3 = DevCmd(cmdStr=READ_ENC3)
        readDevCmds = [readGauge1, readGauge2, readGauge3]
        # statusDevCmd.addCallback(self._statusCallback)
        userCmd.linkCommands(readDevCmds)
        for devCmd in readDevCmds:
            devCmd.setTimeLimit(timeLim)
            self.queueDevCmd(devCmd)
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
            print("unsolicited!")
            log.info("%s usolicited reply: %s for done command %s" % (self, replyStr, str(self.currExeDevCmd)))
            return

        if self.currExeDevCmd.cmdStr in [COUNTING_STATE, ZERO_SET, DISPLAY_CURR]:
            if SUCCESS in replyStr:
                # successful set into counting state
                # check for CHOO in the line (saw one instance of it getting appended)
                # to a previous output to a GAOO command which contained an error 15
                # so mark any of these commands as done if CHOO is in the line,
                # regardless of if there is an error in it
                # any error without
                self.currExeDevCmd.setState(self.currExeDevCmd.Done)
                return

        if "error" in replyStr.lower():
            self.encPos = [None]*3

            if "error 15" in replyStr.lower():
                self.currExeDevCmd.writeToUsers("w", "Mitutoyo Error 15, not in counting state (was it power cycled?). Homing threadring necessary.")
            else:
                # some other error?
                self.currExeDevCmd.writeToUsers("w", "Mitutoyo EV counter Error output: " + replyStr)
            if not self.currExeDevCmd.isDone:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Error from Mitutoyos, homing threadring probably necessary.")
            return

        if self.currExeDevCmd.cmdStr.startswith(READ_PREFIX):
            # check that the expected prefix is seen
            # if not we are not in the 'current value state probably'
            # try to match a gauge value
            gaugeMatch = gaugeRE.search(replyStr)
            if gaugeMatch is None:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Failed to match mitutoyo output: %s. Are they in counting state? Homing may be necessary."%replyStr)
            else:
                # match was successful
                gaugeNumber = int(gaugeMatch.group("gauge")) - 1 # zero index gauges
                gaugeValue = float(gaugeMatch.group("value"))
                self.encPos[gaugeNumber] = gaugeValue


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
                print("meas scale writing", devCmd.cmdStr)
                devCmd.setState(devCmd.Running)
                self.conn.writeLine(devCmd.cmdStr)
            else:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Not connected")
        except Exception as e:
            self.currExeDevCmd.setState(self.currExeDevCmd.Failed, textMsg=strFromException(e))

