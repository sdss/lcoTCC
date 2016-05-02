from __future__ import division, absolute_import

from RO.Comm.TwistedTimer import Timer
from RO.StringUtil import strFromException

from twistedActor import TCPDevice, UserCmd, DevCmd, CommandQueue, log, expandUserCmd, LinkCommands

__all__ = ["M2Device"]

PollTime = 0.5 #seconds, LCO says status is updated no more frequently that 5 times a second
PollTime = 1
# Speed = 25.0 # microns per second for focus

Done = "done"
Moving = "moving"
Error = "error"
On = "on"
Off = "off"
validMotionStates = [Done, Moving, Error]
validGalilStates = [On, Off]

class Status(object):
    def __init__(self):
        """Container for holding current status of the m2

        this is the status string State=DONE Ori=12500.0,-0.0,-0.0,-0.0,0.0 Lamps=off Galil=off
        """
        self.speed = None
        self.state = None
        self.orientation = [None]*5
        self.lamps = None
        self.galil = None

    @property
    def secFocus(self):
        return self.orientation[0]

    def secFocusStr(self):
        secFocus = "NaN" if self.secFocus is None else "%.2f"%self.secFocus
        return "SecFocus=%s"%secFocus

    def getStatusStr(self):
        """Grab and format tcc keywords, only output those which have changed
        """
        kwOutputList = [self.secFocusStr()]
        # add mirror moving times, and actuator positions?
        # eg colimation
        return "; ".join(kwOutputList)

    def parseStatus(self, replyStr):
        """Parse replyString (as returned from the M2 tcp/ip server) and set values

        this is the status string State=DONE Ori=12500.0, -0.0, -0.0, -0.0, 0.0 Lamps=off Galil=off
        """
        # lowerify everything
        replyStr = replyStr.lower()
        for statusBit in replyStr.split():
            key, val = statusBit.split("=")
            if key == "state":
                val = val.lower()
                assert val in validMotionStates
            elif key == "ori":
                key = "orientation"
                val = [float(x) for x in val.split(",")]
                assert len(val) == 5
            elif key == "galil":
                assert val in validGalilStates
            # note don't really care about lamps
            assert key in dir(self)
            setattr(self, key, val)

class M2Device(TCPDevice):
    """!A Device for communicating with the M2 process."""
    def __init__(self, name, host, port, callFunc=None):
        """!Construct a LCODevice

        Inputs:
        @param[in] name  name of device
        @param[in] host  host address of m2 controller
        @param[in] port  port of m2 controller
        @param[in] callFunc  function to call when state of device changes;
                note that it is NOT called when the connection state changes;
                register a callback with "conn" for that task.
        """
        self.status = Status()
        self._statusTimer = Timer()
        self.waitMoveCmd = UserCmd()
        self.waitMoveCmd.setState(self.waitMoveCmd.Done)
        self.waitGalilCmd = UserCmd()
        self.waitGalilCmd.setState(self.waitGalilCmd.Done)
        self.devCmdQueue = CommandQueue({}) # all commands of equal priority

        TCPDevice.__init__(self,
            name = name,
            host = host,
            port = port,
            callFunc = callFunc,
            cmdInfo = (),
        )

    @property
    def isDone(self):
        return self.status.state == Done

    @property
    def currExeDevCmd(self):
        return self.devCmdQueue.currExeCmd.cmd

    @property
    def currDevCmdStr(self):
        return self.currExeDevCmd.cmdStr

    # @property
    # def atFocus(self):
    #     if self.status.statusFieldDict["focus"].value and abs(self.targFocus - self.status.statusFieldDict["focus"].value) < FocusPosTol:
    #         return True
    #     else:
    #         return False

    def init(self, userCmd=None, timeLim=None, getStatus=True):
        """Called automatically on startup after the connection is established.
        Only thing to do is query for status or connect if not connected
        """
        log.info("%s.init(userCmd=%s, timeLim=%s, getStatus=%s)" % (self, userCmd, timeLim, getStatus))
        userCmd = expandUserCmd(userCmd)
        # if not self.isConnected:
        #     return self.connect(userCmd=userCmd)
        # get the speed on startup
        # ignore getStatus flag, just do it always
        self.queueDevCmd(DevCmd(cmdStr="speed"))
        return self.getStatus(userCmd=userCmd)
        # userCmd.setState(userCmd.Done)
        # return userCmd

    def getStatus(self, userCmd=None):
        """Return current telescope status. Continuously poll.
        """
        log.info("%s.getStatus(userCmd=%s)" % (self, userCmd)) # logging this will flood the log
        userCmd = expandUserCmd(userCmd)
        if not self.conn.isConnected:
            userCmd.setState(userCmd.Failed, "Not Connected to M2")
            return userCmd
        self._statusTimer.cancel() # incase a status is pending
        userCmd = expandUserCmd(userCmd)
        userCmd.addCallback(self._statusCallback)
        # gather list of status elements to get
        statusCmd = DevCmd(cmdStr="status")
        LinkCommands(userCmd, [statusCmd])
        self.queueDevCmd(statusCmd)
        if not self.isDone:
            # only poll if moving
            self._statusTimer.start(PollTime, self.getStatus)
        return userCmd

    def _statusCallback(self, cmd):
        """! When status command is complete, send info to users, and check if any
        wait commands need to be set done
        """
        if cmd.isDone:
            # do we want status output so frequently? probabaly not.
            # perhaps only write status if it has changed...
            statusStr = self.status.getStatusStr()
            if statusStr:
                self.writeToUsers("i", statusStr, cmd)
            # update delta ra and decs

            if not self.waitMoveCmd.isDone and self.isDone:
                # move is done, power off galil
                self.queueDevCmd(DevCmd(cmdStr="galil off"))
                self.waitMoveCmd.setState(self.waitMoveCmd.Done)
            if not self.waitGalilCmd.isDone and not self.isDone:
                self.waitGalilCmd.setState(self.waitGalilCmd.Done)

    def stop(self, userCmd=None):
        userCmd = expandUserCmd(userCmd)
        if not self.waitMoveCmd.isDone:
            self.waitMoveCmd.setState(self.waitMoveCmd.Cancelled, "Stop commanded")
        stopCmd = DevCmd(cmdStr="stop")
        self.queueDevCmd(stopCmd)
        LinkCommands(userCmd, [stopCmd])
        return userCmd

    def focus(self, focusValue, offset=False, userCmd=None):
        """Command an offset or absolute focus move

        @param[in] focusValue: float, focus value in microns
        @param[in] offset, if true this is offset, else absolute
        @param[in] userCmd: a twistedActor BaseCommand
        """
        """Command an offset to the current focus value

        @param[in] focusValue: float, focus value in microns
        @param[in] userCmd: a twistedActor BaseCommand
        """
        log.info("%s.focus(userCmd=%s, focusValue=%.2f, offset=%s)" % (self, userCmd, focusValue, str(bool(offset))))
        return self.move(valueList=[focusValue], offset=offset, userCmd=userCmd)

    def move(self, valueList, offset=False, userCmd=False):
        """Command an offset or absolute focus move

        @param[in] valueList: list of 1 to 5 values specifying focus(um), tiltx("), tilty("), transx(um), transy(um)
        @param[in] offset, if true this is offset, else absolute
        @param[in] userCmd: a twistedActor BaseCommand
        """
        log.info("%s.move(userCmd=%s, valueList=%s, offset=%s)" % (self, userCmd, str(valueList), str(bool(offset))))
        userCmd = expandUserCmd(userCmd)
        if not self.waitMoveCmd.isDone:
            userCmd.setState(userCmd.Failed, "Mirror currently moving")
            return userCmd
        if not 1<=len(valueList)<=5:
            userCmd.setState(userCmd.Failed, "Must specify 1 to 5 numbers for a move")
            return userCmd
        self.waitMoveCmd = UserCmd()
        cmdType = "offset" if offset else "move"
        strValList = ", ".join(["%.2f"%val for val in valueList])
        cmdStr = "%s %s"%(cmdType, strValList)
        moveCmd = DevCmd(cmdStr=cmdStr)
        statusCmd = DevCmd(cmdStr="status")
        # status immediately to see moving state
        devCmdList = [moveCmd, statusCmd]
        LinkCommands(userCmd, devCmdList + [self.waitMoveCmd])
        for devCmd in devCmdList:
            self.queueDevCmd(devCmd)
        # begin polling status
        def startStatusLoop(*arg):
            self.getStatus()
        statusCmd.addCallback(startStatusLoop) # begin polling
        return userCmd

    def handleReply(self, replyStr):
        """Handle a line of output from the device. Called whenever the device outputs a new line of data.

        @param[in] replyStr   the reply, minus any terminating \n

        Tasks include:
        - Parse the reply
        - Manage the pending commands
        - Parse status to update the model parameters
        """
        log.info("%s read %r, currCmdStr: %s" % (self, replyStr, self.currDevCmdStr))
        print(replyStr)
        replyStr = replyStr.strip()
        if not replyStr:
            return
        if self.currExeDevCmd.isDone:
            # ignore unsolicited ouput
            return
        if "error" in replyStr.lower():
            # error
            self.writeToUsers("w", "Error in M2 reply: %s, current cmd: %s"%(replyStr, self.currExeDevCmd.cmdStr))
        # if this was a speed command, set it
        if self.currDevCmdStr.lower() == "speed":
            self.status.speed = float(replyStr)
        elif self.currDevCmdStr.lower() == "status":
            self.status.parseStatus(replyStr)
        # only one line is ever returned after a request
        # so if we got one, then the request is done
        self.currExeDevCmd.setState(self.currExeDevCmd.Done)


    def queueDevCmd(self, devCmd):
        """Add a device command to the device command queue

        @param[in] devCmd: a twistedActor DevCmd.
        """
        log.info("%s.queueDevCmd(devCmd=%r, devCmdStr=%r, cmdQueue: %r"%(self, devCmd, devCmd.cmdStr, self.devCmdQueue))
        # append a cmdVerb for the command queue (other wise all get the same cmdVerb and cancel eachother)
        # could change the default behavior in CommandQueue?
        devCmd.cmdVerb = devCmd.cmdStr
        def queueFunc(devCmd):
            self.startDevCmd(devCmd.cmdStr)
        self.devCmdQueue.addCmd(devCmd, queueFunc)


    def startDevCmd(self, devCmdStr):
        """
        @param[in] devCmdStr a line of text to send to the device
        """
        devCmdStr = devCmdStr.lower() # m2 uses all lower case
        log.info("%s.startDevCmd(%r)" % (self, devCmdStr))
        try:
            if self.conn.isConnected:
                log.info("%s writing %r" % (self, devCmdStr))
                self.conn.writeLine(devCmdStr)
            else:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Not connected")
        except Exception as e:
            self.currExeDevCmd.setState(self.currExeDevCmd.Failed, textMsg=strFromException(e))





