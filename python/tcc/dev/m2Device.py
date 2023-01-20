from __future__ import division, absolute_import

import numpy

from RO.Comm.TwistedTimer import Timer
from RO.StringUtil import strFromException

from twistedActor import TCPDevice, DevCmd, CommandQueue, log, expandCommand
from twisted.internet.task import LoopingCall

__all__ = ["M2Device"]

#TODO: fix move timeout, timeout should be set on device
# commands, currently it is on the UserCmd

PollTime = 0.5 # polling frequency during a move, seconds, LCO says status is updated no more frequently that 5 times a second
StatusCheckTime = 5 # query for status frequency automatically
# PollTime = 1
# Speed = 25.0 # microns per second for focus
DefaultTimeout = 2 # seconds
RelayPosM2 = 5 # our FF lamp is wired to the 5th relay on the du Pont M2

Done = "Done"
Moving = "Moving"
# Error = "ERROR"
Failed = "Failed"
On = "on"
Off = "off"
validMotionStates = [Done, Moving, Failed]
validStates = [On, Off]


class Status(object):
    def __init__(self):
        """Container for holding current status of the m2

        this is the status string State=DONE Ori=12500.0,-0.0,-0.0,-0.0,0.0 Lamps=off Galil=off
        """
        self.speed = None
        self.state = None
        self.orientation = [None]*5
        self.desOrientation = [None]*5
        self.lamps = None
        self.galil = None
        self._moveTimeTotal = 0.

    @property
    def moveTimeRemaining(self):
        if self.state == Done:
            return 0
        else:
            if not None in self.orientation and not None in self.desOrientation and self.speed is not None:
                maxDist = numpy.max(numpy.abs(numpy.subtract(self.desOrientation, self.orientation)))
                return maxDist/self.speed
            else:
                return 0

    @property
    def moveTimeTotal(self):
        if self.state == Done:
            return 0
        else:
            return self._moveTimeTotal

    @property
    def desFocus(self):
        return self.desOrientation[0]

    @property
    def secFocus(self):
        return self.orientation[0]

    def secFocusStr(self):
        secFocus = "NaN" if self.secFocus is None else "%.2f"%self.secFocus
        return "%s"%secFocus

    def galilStr(self):
        galil = "?" if self.galil is None else "%s"%self.galil
        return "%s"%galil

    def ffPowerStr(self):
        if self.lamps is None:
            val = "?"
        elif self.lamps.lower() == "on":
            val = "T"
        else:
            val = "F"
        return "%s"%val

    def _getOrientStr(self, orientation):
        orientStrs = []
        # add an aditional 0 for rotation about z to
        # keep actorkeys consistent between apo and lco
        for orient in orientation + [0]:
            orientStr = "NaN" if orient is None else "%.2f"%orient
            orientStrs.append(orientStr)
        return ", ".join(orientStrs)

    def secOrientStr(self):
        return "%s"%self._getOrientStr(self.orientation)

    def secDesOrientStr(self):
        return "%s"%self._getOrientStr(self.desOrientation)


    def secStateStr(self):
        # secState [Moving, Done, Homing, Failed, NotHomed]
        #   current iteration
        #   max iterations
        #   remaining time
        #   total time
        currIter = 1 # no meaning at LCO
        maxIter = 1 # no meaning at LCO
        return "%s, %i, %i, %.2f, %.2f"%(
            self.state, currIter, maxIter, self.moveTimeRemaining, self.moveTimeTotal
            )

    def getStatusDict(self):
        """Grab and format tcc keywords, only output those which have changed
        """
        statusDict = {
            "secState": self.secStateStr(),
            "secFocus": self.secFocusStr(),
            "Galil": self.galilStr(),
            "secOrient": self.secOrientStr(),
            "secDesOrient": self.secDesOrientStr(),
            "ffPower": self.ffPowerStr(),
        }
        return statusDict

    def parseStatus(self, replyStr):
        """Parse replyString (as returned from the M2 tcp/ip server) and set values

        this is the status string State=DONE Ori=12500.0, -0.0, -0.0, -0.0, 0.0 Lamps=off Galil=off
        """
        # lowerify everything
        replyStr = replyStr.lower()
        for statusBit in replyStr.split():
            key, val = statusBit.split("=")
            if key == "state":
                if val == "error":
                    val = "Failed" # failed fits with teh secState keyword, Error doesn't
                else:
                    val = val.title()
                assert val in validMotionStates, "%s, %s"%(val, str(validMotionStates))
            elif key == "ori":
                key = "orientation"
                val = [float(x) for x in val.split(",")]
                assert len(val) == 5
            elif key == "galil":
                assert val in validStates
            elif key == "lamps":
                if val != "off":
                    val = "on"
            # set the status values as attrs on this
            # object
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
        self.tccStatus = None # set by lcoTCCActor
        self.status = Status()
        self._statusTimer = Timer()
        self.waitMoveCmd = expandCommand()
        self.waitMoveCmd.setState(self.waitMoveCmd.Done)
        priorityDict = {
            "status": 1,
            "speed": 1,
            "stop": 1,
            "move": 1,
            "galil": 1,
            "offset": 1,
        }

        self.devCmdQueue = CommandQueue(priorityDict) # all commands of equal priority

        TCPDevice.__init__(self,
            name = name,
            host = host,
            port = port,
            callFunc = callFunc,
            cmdInfo = (),
        )

        # begin automatically asking for status
        loop = LoopingCall(self.continuousStatusLoop)
        loop.start(StatusCheckTime)

    @property
    def isBusy(self):
        return self.status.state == Moving

    @property
    def isOff(self):
        return self.status.galil == Off

    @property
    def isDone(self):
        # only done when state=done and galil=off
        return not self.isBusy
        #return not self.isBusy and self.isOff

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
        # print("%s.init(userCmd=%s, timeLim=%s, getStatus=%s)" % (self, userCmd, timeLim, getStatus))
        userCmd = expandCommand(userCmd)
        # if not self.isConnected:
        #     return self.connect(userCmd=userCmd)
        # get the speed on startup
        # ignore getStatus flag, just do it always
        speedCmd = DevCmd("speed")
        statusCmd = DevCmd("status")
        devCmds = [speedCmd, statusCmd]
        userCmd.linkCommands(devCmds)
        for cmd in devCmds:
            self.queueDevCmd(cmd)
        return userCmd

    def continuousStatusLoop(self):
        print("calling status loop m2")
        if self._statusTimer.isActive:
            return  # do nothing, status already running
        if not self.conn.isConnected:
            return  # do nothing, not connected to M2
        self.getStatus()

    def getStatus(self, userCmd=None):
        """Return current telescope status. Continuously poll.
        """
        # log.info("%s.getStatus(userCmd=%s)" % (self, userCmd)) # logging this will flood the log
        # print("%s.getStatus(userCmd=%s)" % (self, userCmd))
        userCmd = expandCommand(userCmd)
        if not self.conn.isConnected:
            userCmd.setState(userCmd.Failed, "Not Connected to M2")
            return userCmd
        self._statusTimer.cancel() # incase a status is pending
        # userCmd.addCallback(self._statusCallback)
        # gather list of status elements to get
        statusCmd = DevCmd("status")
        userCmd.linkCommands([statusCmd])
        self.queueDevCmd(statusCmd)
        print("queued status command")
        return userCmd

    def processStatus(self, replyStr):
        # print("procesStatus", replyStr)
        self.status.parseStatus(replyStr)
        # do we want status output so frequently? probabaly not.
        # perhaps only write status if it has changed...
        # but so far status is a small amount of values
        # so its probably ok
        statusDict = self.status.getStatusDict()
        if self.tccStatus is not None:
            self.tccStatus.updateKWs(statusDict, self.currExeDevCmd)
        if self.waitMoveCmd.isActive:
            if not self.isBusy:
                # move is done
                # no longer send galil off
                self.waitMoveCmd.setState(self.waitMoveCmd.Done)

                # if not self.isOff:
                #     # move just finished but galil is not off, turn it off
                #     self.queueDevCmd(DevCmd("galil off"))
                # else:
                #     # move is done and galil is off, set wait move command as done
                #     self.waitMoveCmd.setState(self.waitMoveCmd.Done)

        if not self.isDone:
            # keep polling until done
            self._statusTimer.start(PollTime, self.getStatus)

    def stop(self, userCmd=None):
        userCmd = expandCommand(userCmd)
        if not self.waitMoveCmd.isDone:
            self.waitMoveCmd.setState(self.waitMoveCmd.Cancelled, "Stop commanded")
        #print("sec stop commanded")
        devCmdList = [
            DevCmd("stop"),
            DevCmd("galil off"),
            DevCmd("status"),
            DevCmd("status2"),
        ]
        userCmd.linkCommands(devCmdList)
        for devCmd in devCmdList:
            self.queueDevCmd(devCmd)
        return userCmd

    def focus(self, focusValue, offset=False, userCmd=None):
        """Command an offset or absolute focus move

        @param[in] focusValue: float, focus value in microns
        @param[in] offset, if true this is offset, else absolute
        @param[in] userCmd: a twistedActor BaseCommand

        WARNING!!!
        At APO increasing focus corresponds to decreasing M1-M2 dist.
        The mirror controller at LCO convention is the opposite.
        """
        log.info("%s.focus(userCmd=%s, focusValue=%.2f, offset=%s)" % (self, userCmd, focusValue, str(bool(offset))))
        # if this focus value is < 50 microns
        userCmd = expandCommand(userCmd)
        # focusDir = 1 # use M2's natural coordinates
        # focusDir = -1 # use convention at APO
        return self.move(valueList=[focusValue], offset=offset, userCmd=userCmd)

    def move(self, valueList, offset=False, userCmd=None):
        """Command an offset or absolute orientation move

        @param[in] valueList: list of 1 to 5 values specifying pistion(um), tiltx("), tilty("), transx(um), transy(um)
        @param[in] offset, if true this is offset, else absolute
        @param[in] userCmd: a twistedActor BaseCommand

        Note: increasing distance eg pistion means increasing spacing between primary and
        secondary mirrors.
        """
        log.info("%s.move(userCmd=%s, valueList=%s, offset=%s)" % (self, userCmd, str(valueList), str(bool(offset))))
        userCmd = expandCommand(userCmd)
        if not self.waitMoveCmd.isDone:
            userCmd.setState(userCmd.Failed, "Mirror currently moving")
            return userCmd
        if not 1<=len(valueList)<=5:
            userCmd.setState(userCmd.Failed, "Must specify 1 to 5 numbers for a move")
            return userCmd
        self.waitMoveCmd = expandCommand()
        self.waitMoveCmd.userCmd = userCmd # for write to users
        self.status.desOrientation = self.status.orientation[:]
        if offset:
            # if offset is specified, offset from current value
            for ii, value in enumerate(valueList):
                self.status.desOrientation[ii] += value
        else:
            # if absolute is wanted, overwrite all those
            # specified
            for ii, value in enumerate(valueList):
                self.status.desOrientation[ii] = value
        cmdType = "offset" if offset else "move"
        strValList = " ".join(["%.2f"%val for val in valueList])
        cmdStr = "%s %s"%(cmdType, strValList)
        moveCmd = DevCmd(cmdStr)
        statusCmd = DevCmd("status")
        galilOverHead = 2 # galil take roughly 2 secs to boot up.
        extraOverHead = 2 #
        self.status._moveTimeTotal = self.getTimeForMove()
        timeout = self.status._moveTimeTotal+galilOverHead+extraOverHead
        userCmd.setTimeLimit(timeout*3) # triple the time out time
        userCmd.linkCommands([moveCmd, statusCmd, self.waitMoveCmd])
        for cmd in [moveCmd, statusCmd]:
            self.queueDevCmd(cmd)
        # status immediately to see moving state
        # determine total time for move
        # just use focus distance as proxy (ignore)


        return userCmd

    def getTimeForMove(self):
        dist2Move = numpy.max(numpy.abs(numpy.subtract(self.status.desOrientation, self.status.orientation)))
        time4Move = dist2Move / self.status.speed
        return time4Move

    def lampOn(self, userCmd=None):
        """Toggle power to the ff lamp (the 5th relay at the M2 position)
        """
        log.info("%s.lampOn(userCmd=%s)" % (self, userCmd))
        userCmd = expandCommand(userCmd)
        userCmd.setTimeLimit(2)
        lampCmd = DevCmd("lamp %i 1"%RelayPosM2)
        userCmd.linkCommands([lampCmd])
        self.queueDevCmd(lampCmd)
        return userCmd

    def lampOff(self, userCmd=None):
        """Toggle power to the ff lamp (the 5th relay at the M2 position)
        """
        log.info("%s.lampOff(userCmd=%s)" % (self, userCmd))
        userCmd = expandCommand(userCmd)
        lampCmd = DevCmd("lamp %i 0"%RelayPosM2)
        userCmd.linkCommands([lampCmd])
        self.queueDevCmd(lampCmd)
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
        # print("%s read %r, currCmdStr: %s" % (self, replyStr, self.currDevCmdStr))
        replyStr = replyStr.strip()
        if not replyStr:
            return
        if self.currExeDevCmd.isDone:
            # ignore unsolicited ouput
            return
        if "error" in replyStr.lower():
            # error
            errStr = "Error in M2 reply: %s, current cmd: %s"%(replyStr, self.currExeDevCmd.cmdStr)
            log.info(errStr)
            self.currExeDevCmd.writeToUsers("w", errStr)
        # if this was a speed command, set it
        if self.currDevCmdStr.lower() == "speed":
            self.status.speed = float(replyStr)
        elif self.currDevCmdStr.lower() == "status":
            self.processStatus(replyStr)
        # only one line is ever returned after a request
        # so if we got one, then the request is done
        self.currExeDevCmd.setState(self.currExeDevCmd.Done)


    def queueDevCmd(self, devCmd):
        """Add a device command to the device command queue

        @param[in] cmdStr, string to send to the device.
        """
        cmdStr = devCmd.cmdStr
        log.info("%s.queueDevCmd(cmdStr=%r, cmdQueue: %r"%(self, cmdStr, self.devCmdQueue))
        # print("%s.queueDevCmd(devCmd=%r, devCmdStr=%r, cmdQueue: %r"%(self, devCmd, devCmd.cmdStr, self.devCmdQueue))
        # append a cmdVerb for the command queue (other wise all get the same cmdVerb and cancel eachother)
        # could change the default behavior in CommandQueue?
        devCmd.cmdVerb = cmdStr.split()[0]
        def queueFunc(devCmd):
            self.startDevCmd(devCmd)
        self.devCmdQueue.addCmd(devCmd, queueFunc)
        return devCmd


    def startDevCmd(self, devCmd):
        """
        @param[in] devCmdStr a line of text to send to the device
        """
        devCmdStr = devCmd.cmdStr.lower() # m2 uses all lower case
        log.info("%s.startDevCmd(%r)" % (self, devCmdStr))
        try:
            if self.conn.isConnected:
                log.info("%s writing %r" % (self, devCmdStr))
                # set move command to running now. Bug if set earlier race condition
                # with status
                if "move" in devCmdStr.lower() or "offset" in devCmdStr.lower():
                    self.waitMoveCmd.setState(self.waitMoveCmd.Running)
                    self.status.state = Moving
                    if self.tccStatus is not None:
                        self.tccStatus.updateKW("secState", self.status.secStateStr(), devCmd)
                # if "galil" in devCmdStr.lower():
                #     self.waitGalilCmd.setState(self.waitGalilCmd.Running)
                self.conn.writeLine(devCmdStr)
            else:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Not connected to M2")
        except Exception as e:
            self.currExeDevCmd.setState(self.currExeDevCmd.Failed, textMsg=strFromException(e))





