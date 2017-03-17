from __future__ import division, absolute_import

import numpy

from twistedActor import TCPDevice, log, DevCmd, expandUserCmd, CommandQueue, LinkCommands, UserCmd

from RO.StringUtil import strFromException
from RO.Comm.TwistedTimer import Timer


__all__ = ["FFDevice"]

I_SETPOINT = 4 # AMPS
V_SETPOINT = 12 # Volts
I_THRESH = 0.1 # determines 'close enough' amps
V_THRESH = 0.1 # determines 'close enough' volts

VSET = "VSET"
ISET = "ISET"
PWR = "PWR"
OFF = "OFF"
ON = "ON"
REMOTE = "REMOTE"
LOCAL = "LOCAL"
VREAD = "VREAD"
IREAD = "IREAD"

class FFDevice(TCPDevice):
    """!A Device for communicating flat field power supply."""
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

        self.PWR = None
        self.VSET = None
        self.ISET = None
        self.REMOTE = None
        self.VREAD = None
        self.IREAD = None
        self.waitPwrCmd = UserCmd()
        self.waitPwrCmd.setState(self.waitPwrCmd.Done)
        self.waitPwrCmd.pwrOn = None # set this attribute so we know if we're powering up or down
        self.statusTimer = Timer()
        self.devCmdQueue = CommandQueue({})

        TCPDevice.__init__(self,
            name = name,
            host = host,
            port = port,
            callFunc = callFunc,
            cmdInfo = (),
        )

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

    def getStatus(self, userCmd=None, timeLim=2):
        self.statusTimer.cancel()
        userCmd = expandUserCmd(userCmd)
        devCmdList = [DevCmd(cmdStr=cmdVerb) for cmdVerb in [REMOTE, PWR, ISET, VSET, VREAD, IREAD]]
        LinkCommands(userCmd, devCmdList)
        devCmdList[-1].addCallback(self._statusCallback)
        userCmd.setTimeLimit(timeLim)
        userCmd.setState(userCmd.Running)
        for devCmd in devCmdList:
            self.queueDevCmd(devCmd)
        return userCmd

    def powerOn(self, userCmd=None):
        """Command the power supply on, finish when the current is within threshold of set point
        """
        userCmd = expandUserCmd(userCmd)
        if not self.waitPwrCmd.isDone:
            power = "up" if self.waitPwrCmd.pwrOn else "down"
            userCmd.setState(userCmd.Cancelled, "Cannot power on, FF screen is currently powering %s"%power)
            return userCmd
        self.waitPwrCmd = userCmd()
        self.waitPwrCmd.setTimeLimit(10)
        self.waitPwrCmd.pwrOn = True
        devCmdStrs = ["%s %s"%(REMOTE, REMOTE), "%s %.4f"%(VSET, V_SETPOINT), "%s %.4f"%(ISET, I_SETPOINT), "%s %s"%(PWR, ON)]
        devCmdList = [DevCmd(cmdStr=cmdStr) for cmdStr in devCmdStrs]
        LinkCommands(userCmd, devCmdList+[self.waitPwrCmd])
        self.waitPwrCmd.setState(self.waitPwrCmd.Running)
        return userCmd

    def powerOff(self, userCmd=None):
        """Command the power supply off, finish when the current drops to 0
        """
        userCmd = expandUserCmd(userCmd)
        if not self.waitPwrCmd.isDone:
            power = "up" if self.waitPwrCmd.pwrOn else "down"
            userCmd.setState(userCmd.Cancelled, "Cannot power off, FF screen is currently powering %s"%power)
            return userCmd
        self.waitPwrCmd = userCmd()
        self.waitPwrCmd.setTimeLimit(10)
        self.waitPwrCmd.pwrOn = False
        devCmdStrs = ["%s %s"%(REMOTE, REMOTE), "%s %s"%(PWR, OFF)]
        devCmdList = [DevCmd(cmdStr=cmdStr) for cmdStr in devCmdStrs]
        LinkCommands(userCmd, devCmdList+[self.waitPwrCmd])
        self.waitPwrCmd.setState(self.waitPwrCmd.Running)
        return userCmd

    def _statusCallback(self, statusCmd):
        # if statusCmd.isActive:
        #     # not sure this is necessary
        #     # but ensures we get a 100% fresh status
        #     self.status.flushStatus()
        if statusCmd.isDone and not statusCmd.didFail:
            self.writeStatusToUsers(statusCmd.userCmd)
            # print("mig values,", self.encPos)
            # print("done reading migs")

    @property
    def iSetKW(self):
        return "ffSetCurrent=%4f"%self.ISET if self.ISET else "nan"

    @property
    def vSetKW(self):
        return "ffSetVoltage=%4f"%self.ISET if self.VSET else "nan"

    @property
    def iReadKW(self):
        return "ffCurrent=%4f"%self.IREAD if self.IREAD else "nan"

    @property
    def vReadKW(self):
        return "ffVoltage=%4f"%self.VREAD if self.VREAD else "nan"

    @property
    def pwrKW(self):
        if self.PWR == ON:
            pwrVal = "T"
        elif self.PWR == OFF:
            pwrVal = "F"
        else:
            pwrVal = "?"
        return "ffPower=%s"%pwrVal

    def writeStatusToUsers(self, userCmd=None):
        self.writeToUsers("i", self.iReadKW, userCmd)
        self.writeToUsers("i", self.vReadKW, userCmd)
        self.writeToUsers("i", self.iSetKW, userCmd)
        self.writeToUsers("i", self.vSetKW, userCmd)
        self.writeToUsers("i", self.pwrKW, userCmd)

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
        # only parse the first element of the replyStr in all cases
        replyStr = replyStr.split()[0]
        if PWR in self.currExeDevCmd.cmdStr:
            # parse pwr state
            if not replyStr in [ON, OFF]:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "FF power state: %s as ON or OFF."%replyStr)
            self.PWR = replyStr
            expectedVal = self.currExeDevCmd.cmdStr.split(PWR)[-1]
            if expectedVal and not expectedVal == self.PWR:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Returned PWR state doesn't match commanded [%.4f, %.4f]"%(expectedVal, self.PWR))
            self.writeToUsers("i", self.pwrKW, self.currExeDevCmd.userCmd)
        if REMOTE in self.currExeDevCmd.cmdStr:
            # parse pwr state
            if not replyStr in [LOCAL, REMOTE]:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "FF remote: %s as LOCAL or REMOTE."%replyStr)
            self.REMOTE = replyStr
            expectedVal = self.currExeDevCmd.cmdStr.split(REMOTE)[-1]
            if expectedVal and not expectedVal == self.REMOTE:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Returned REMOTE state doesn't match commanded [%.4f, %.4f]"%(expectedVal, self.REMOTE))
        elif ISET in self.currExeDevCmd.cmdStr:
            try:
                self.ISET = float(replyStr)
            except:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Failed to parse ff current setpoint: %s as a float."%replyStr)
            # if the state was set explicitly verify that it is at the correct value
            expectedVal = self.currExeDevCmd.cmdStr.split(ISET)[-1]
            if expectedVal and not float(expectedVal) == self.ISET:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Returned ISET point doesn't match commanded [%.4f, %.4f]"%(expectedVal, self.ISET))
            self.writeToUsers("i", self.iSetKW, self.currExeDevCmd.userCmd)
        elif VSET in self.currExeDevCmd.cmdStr:
            try:
                self.VSET = float(replyStr)
            except:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Failed to parse ff voltage setpoint: %s as a float."%replyStr)
            # if the state was set explicitly verify that it is at the correct value
            expectedVal = self.currExeDevCmd.cmdStr.split(VSET)[-1]
            if expectedVal and not float(expectedVal) == self.VSET:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Returned VSET point doesn't match commanded [%.4f, %.4f]"%(expectedVal, self.ISET))
            self.writeToUsers("i", self.vSetKW, self.currExeDevCmd.userCmd)
        elif VREAD in self.currExeDevCmd:
            try:
                self.VREAD = float(replyStr)
            except:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Failed to parse ff voltage state: %s as a float."%replyStr)
            self.writeToUsers("i", self.vReadKW, self.currExeDevCmd.userCmd)
        elif IREAD in self.currExeDevCmd:
            try:
                self.IREAD = float(replyStr)
            except:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Failed to parse ff current state: %s as a float."%replyStr)
            self.writeToUsers("i", self.iSetKW, self.currExeDevCmd.userCmd)
        if not self.currExeDevCmd.isDone:
            self.currExeDevCmd.setState(self.currExeDevCmd.Done)
        if not self.waitPwrCmd.isDone:
            # check if we are at the setpoint
            if self.waitPwrCmd.pwrOn:
                # desired current is setpoint
                desI = self.ISET
            else:
                # waiting to power down, desired current is 0
                desI = 0.
            if numpy.abs(desI-self.IREAD)<I_THRESH:
                # lamp is fully powered on/off
                self.waitPwrCmd.setState(self.waitPwrCmd.Done)
        # if the power command has not completed
        # query for status again .5 seconds
        self.statusTimer.start(0.5, self.getStatus)


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

