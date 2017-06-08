from __future__ import division, absolute_import

import numpy

from twistedActor import TCPDevice, log, DevCmd, CommandQueue, expandCommand

from RO.StringUtil import strFromException
from RO.Comm.TwistedTimer import Timer

__all__ = ["FFDevice"]

I_SETPOINT = 3.2 # AMPS
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
        self.tccStatus = None # set by tccLCOActor
        self.PWR = None
        self.VSET = None
        self.ISET = None
        self.REMOTE = None
        self.VREAD = None
        self.IREAD = None
        self.waitPwrCmd = expandCommand()
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
        userCmd = expandCommand(userCmd)
        self.getStatus(userCmd) # status links the userCmd
        return userCmd

    def getStatus(self, userCmd=None, timeLim=2):
        userCmd = expandCommand(userCmd)
        if not self.conn.isConnected:
            userCmd.setState(userCmd.Failed, "Not Connected to FF Lamp: is it on? try reconnecting")
            return userCmd
        self.statusTimer.cancel()
        devCmdList = [DevCmd(cmdStr=cmdVerb) for cmdVerb in [REMOTE, PWR, ISET, VSET, VREAD, IREAD]]
        if not userCmd.isDone:
            userCmd.linkCommands(devCmdList)
        # devCmdList[-1].addCallback(self._statusCallback)
        userCmd.setTimeLimit(timeLim)
        userCmd.setState(userCmd.Running)
        for devCmd in devCmdList:
            self.queueDevCmd(devCmd)
        return userCmd

    def powerOn(self, userCmd=None):
        """Command the power supply on, finish when the current is within threshold of set point
        """
        userCmd = expandCommand(userCmd)
        if not self.waitPwrCmd.isDone:
            power = "up" if self.waitPwrCmd.pwrOn else "down"
            userCmd.setState(userCmd.Cancelled, "Cannot power on, FF screen is currently powering %s"%power)
            return userCmd
        self.waitPwrCmd = expandCommand()
        self.waitPwrCmd.setTimeLimit(10)
        self.waitPwrCmd.pwrOn = True
        devCmdStrs = ["%s %s"%(REMOTE, REMOTE), "%s %.4f"%(VSET, V_SETPOINT), "%s %.4f"%(ISET, I_SETPOINT), "%s %s"%(PWR, ON)]
        devCmdList = [DevCmd(cmdStr=cmdStr) for cmdStr in devCmdStrs]
        userCmd.linkCommands(devCmdList+[self.waitPwrCmd])
        self.waitPwrCmd.setState(self.waitPwrCmd.Running)
        for devCmd in devCmdList:
            self.queueDevCmd(devCmd)
        return userCmd

    def powerOff(self, userCmd=None):
        """Command the power supply off, finish when the current drops to 0
        """
        userCmd = expandCommand(userCmd)
        if not self.waitPwrCmd.isDone:
            power = "up" if self.waitPwrCmd.pwrOn else "down"
            userCmd.setState(userCmd.Cancelled, "Cannot power off, FF screen is currently powering %s"%power)
            return userCmd
        self.waitPwrCmd = expandCommand()
        self.waitPwrCmd.setTimeLimit(10)
        self.waitPwrCmd.pwrOn = False
        devCmdStrs = ["%s %s"%(REMOTE, REMOTE), "%s %.4f"%(VSET, V_SETPOINT), "%s %.4f"%(ISET, I_SETPOINT), "%s %s"%(PWR, OFF)]
        devCmdList = [DevCmd(cmdStr=cmdStr) for cmdStr in devCmdStrs]
        userCmd.linkCommands(devCmdList+[self.waitPwrCmd])
        self.waitPwrCmd.setState(self.waitPwrCmd.Running)
        for devCmd in devCmdList:
            self.queueDevCmd(devCmd)
        return userCmd

    @property
    def iSet(self):
        strVal = "%4f"%self.ISET if self.ISET is not None else "nan"
        return "%s"%strVal

    @property
    def vSet(self):
        strVal = "%.4f"%self.VSET if self.VSET is not None else "nan"
        return "%s"%strVal

    @property
    def iRead(self):
        strVal = "%.4f"%self.IREAD if self.IREAD is not None else "nan"
        return "%s"%strVal

    @property
    def vRead(self):
        strVal = "%.4f"%self.VREAD if self.VREAD is not None else "nan"
        return "%s"%strVal

    @property
    def pwr(self):
        if self.PWR == ON:
            pwrVal = "T"
        elif self.PWR == OFF:
            pwrVal = "F"
        else:
            pwrVal = "?"
        return "%s"%pwrVal

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
            return
        # only parse the first element of the replyStr in all cases
        replyStr = replyStr.split()[0]
        if PWR in self.currExeDevCmd.cmdStr:
            # parse pwr state
            if not replyStr in [ON, OFF]:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "FF power state: %s as ON or OFF."%replyStr)
            self.PWR = replyStr
            expectedVal = self.currExeDevCmd.cmdStr.split(PWR)[-1].strip()
            if expectedVal and not expectedVal == self.PWR:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Returned PWR state doesn't match commanded [%s, %s]"%(expectedVal, self.PWR))
            if self.tccStatus is not None:
                self.tccStatus.updateKW("ffPower", self.pwr, self.currExeDevCmd)
        if REMOTE in self.currExeDevCmd.cmdStr:
            # parse pwr state
            if not replyStr in [LOCAL, REMOTE]:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "FF remote: %s as LOCAL or REMOTE."%replyStr)
            self.REMOTE = replyStr
            expectedVal = self.currExeDevCmd.cmdStr.split(REMOTE)[-1].strip()
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
            if self.tccStatus is not None:
                self.tccStatus.updateKW("ffSetCurrent", self.iSet, self.currExeDevCmd)
        elif VSET in self.currExeDevCmd.cmdStr:
            try:
                self.VSET = float(replyStr)
            except:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Failed to parse ff voltage setpoint: %s as a float."%replyStr)
            # if the state was set explicitly verify that it is at the correct value
            expectedVal = self.currExeDevCmd.cmdStr.split(VSET)[-1]
            if expectedVal and not float(expectedVal) == self.VSET:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Returned VSET point doesn't match commanded [%.4f, %.4f]"%(expectedVal, self.ISET))
            if self.tccStatus is not None:
                self.tccStatus.updateKW("ffSetVoltage", self.vSet, self.currExeDevCmd)
        elif VREAD in self.currExeDevCmd.cmdStr:
            try:
                self.VREAD = float(replyStr)
            except:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Failed to parse ff voltage state: %s as a float."%replyStr)
            if self.tccStatus is not None:
                self.tccStatus.updateKW("ffVoltage", self.vRead, self.currExeDevCmd)
        elif IREAD in self.currExeDevCmd.cmdStr:
            try:
                self.IREAD = float(replyStr)
            except:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Failed to parse ff current state: %s as a float."%replyStr)
            if self.tccStatus is not None:
                self.tccStatus.updateKW("ffCurrent", self.iRead, self.currExeDevCmd)
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
        if not self.waitPwrCmd.isDone:
            self.statusTimer.start(0.5, self.getStatus)


    def queueDevCmd(self, devCmd):
        """Add a device command to the device command queue

        @param[in] devCmd: a deviceCommand.
        @param[in] userCmd: a UserCmd associated with this device (probably but
                                not necessarily linked.  Used here for writeToUsers
                                reference.
        """
        log.info("%s.queueDevCmd(devCmdStr=%r, cmdQueue: %r"%(self, devCmd.cmdStr, self.devCmdQueue))
        #print("%s.queueDevCmd(devCmdStr=%r, cmdQueue: %r"%(self, devCmdStr, self.devCmdQueue))
        # append a cmdVerb for the command queue (otherwise all get the same cmdVerb and cancel eachother)
        # could change the default behavior in CommandQueue?
        devCmd.cmdVerb = devCmd.cmdStr
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
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Not connected to FF power supply")
        except Exception as e:
            self.currExeDevCmd.setState(self.currExeDevCmd.Failed, textMsg=strFromException(e))

