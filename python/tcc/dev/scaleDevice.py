from __future__ import division, absolute_import

import time
import sys
import traceback

# from RO.StringUtil import strFromException
import numpy
from twisted.internet import reactor

from twistedActor import TCPDevice, log, DevCmd, expandUserCmd, CommandQueue, LinkCommands

from RO.StringUtil import strFromException

# tests:
# fault an axis
# overtravel an axis
# fault an axis during move
# connect/disconnect
# figure out which direction is towards the M2
# how do we find the scale zero point
# provide move in mm
# set timeouts for move command
# test incomplete status
# command out of limits scale factor
# repeatedly hammer status
# force move timeout--
# does scale device respond with current_position or actual_position?
# set max speed?
# test move stop

# add fiber plugged position in safe to slew?

# output keywords to add to actorkeys
# implement a queue? for commands?
"""
    "ScaleRingFaults=%s"%faultStr
    "ThreadRingPos=%.4f"%self.position
    "ScaleZeroPos=%.4f"%self.scaleZero
    "ThreadRingSpeed%.4f"%self.speed
    "DesThreadRingPos=%.4f"%self.desPosition
    "CartID=%i"%self.cartID
    "CartLocked=%s"%(str(self.locked))
    "CartLoaded=%s"%(str(self.loaded))
"""

__all__ = ["ScaleDevice"]

# M2 nominal speed is 25 um/sec
# so scale nominal speed should be 25 * 7 um/sec
# or 0.175 mm/sec
MAX_SPEED = 0.1
NOM_SPEED = 0.1
SEC_TIMEOUT = 2.0
MAX_ITER = 3
MOVE_TOL = 5 / 1000.0 # move tolerance (5 microns)

class MungedStatusError(Exception):
    """The scaling ring occassionally returns a Munged status
    """
    pass

class Status(object):
    # how close you must be to the locked setpoint to be considered "locked"
    LOCKED_TOL = 0.005 # mm
    Moving = "Moving"
    Done = "Done"
    def __init__(self):
        self.flushStatus() # sets self.dict and a few other attrs
        self._state = self.Done
        self._totalTime = 0
        self._timeStamp = 0
        self.maxIter = MAX_ITER
        self.moveTol = MOVE_TOL
        self.maxSpeed = MAX_SPEED
        self.currIter = 0

    def setState(self, state, currIter, totalTime=0):
        """Set the state

        @param[in] state: one of self.Moving or self.Done
        @param[in] totalTime: total time for this state, 0 for indefinite
        """
        assert state in [self.Moving, self.Done]
        self.currIter = currIter
        self._state = state
        self._totalTime = totalTime
        self._timeStamp = time.time()

    @property
    def moveRange(self):
        # in mm
        return self.dict["thread_ring_axis"]["move_range"]

    @property
    def speed(self):
        return self.dict["thread_ring_axis"]["drive_speed"]

    @property
    def position(self):
        return self.dict["thread_ring_axis"]["actual_position"]

    @property
    def desPosition(self):
        return self.dict["thread_ring_axis"]["target_position"]

    @property
    def cartID(self):
        #LCOHACK: hard code cart 20 to match Jose's db'
        # return 20
        return self.dict["cartridge_id"]

    @property
    def loaded(self):
        # all 3 position switches?
        sw = self.dict["pos_sw"]
        if sw is None:
            return False
        return not 0 in sw

    @property
    def locked(self):
        pos = self.dict["lock_ring_axis"]["actual_position"]
        if pos is None:
            return False
        lockedPos = self.dict["lock_ring_axis"]["locked_setpoint"]
        return abs(pos-lockedPos) < self.LOCKED_TOL

    @property
    def lockedAndLoaded(self):
        return self.locked and self.loaded

    def setCurrentAxis(self, axisName):
        """axisName is one of:
        "thread_ring_axis", "lock_ring_axis", or "winch_axis"
        """
        assert axisName in ["thread_ring_axis", "lock_ring_axis", "winch_axis"]
        self._currentAxis = axisName

    def setThreadAxisCurrent(self):
        self.setCurrentAxis("thread_ring_axis")

    def flushStatus(self):
        """Empty all status fields
        """
        self.dict = self._getEmptyStatusDict()
        # actual_position is output by move command
        # so currentAxis should be thread ring
        # unless a full status is being
        # parsed
        self.setThreadAxisCurrent()
        self.posSwNext = False
        self.nIter = 0
        self.maxIter = 4 # try at most status iterations before giving up

    def _getEmptyStatusDict(self):
        """Return an empty status dict to be popuated
        """
        return {
            "thread_ring_axis": {
                "actual_position": numpy.nan,
                "target_position": numpy.nan,
                "drive_speed": numpy.nan,
                "move_range": [numpy.nan, numpy.nan],
                "hardware_fault": None,
                "instruction_fault": None,
                "overtravel": None,
            },
            "lock_ring_axis": {
                "actual_position": numpy.nan,
                "target_position": numpy.nan,
                "open_setpoint": numpy.nan,
                "locked_setpoint": numpy.nan,
                "move_range": [numpy.nan, numpy.nan],
                "hardware_fault": None,
                "instruction_fault": None,
            },
            "winch_axis": {
                "actual_position": numpy.nan,
                "target_position": numpy.nan,
                "move_range": [numpy.nan, numpy.nan],
                "up_setpoint": numpy.nan,
                "hardware_fault": None,
                "instruction_fault": None,

            },
            "cartridge_id": None,
            "pos_sw": [None, None, None]
        }

    def checkFullStatus(self, statusDict=None, axis=None):
        """Verify that every piece of status we expect is found in
        statusDict
        """
        if statusDict is None:
            statusDict = self.dict
        for key, val in statusDict.iteritems():
            if hasattr(val, "iteritems"):
                # val is a dict
                self.checkFullStatus(statusDict=val, axis=key)
            else:
                if "range" in key:
                    # 2 element list
                    isEmpty = numpy.nan in val
                elif "pos_sw" == key:
                    isEmpty = None in val
                else:
                    # not a list
                    isEmpty = val is None or numpy.isnan(val)
                    # print("val", val, "isEmpty", isEmpty)

                if isEmpty:
                    errStr = "Status: %s not found"%(key)
                    if axis is not None:
                        errStr += " for %s"%axis
                    raise MungedStatusError(errStr)


    def parseStatusLine(self, line):
        """Return True if recognized and parsed,
        else return False
        """
        # see status example at below
        # some status lines include a colon, get rid of it, along with any leading underscores
        line = line.strip().strip("_").lower().replace(":", "")
        # print(line)
        # first look out for POS_SW
        # this is a weird one to parse because
        # it is of keyvalue type, but the key and value are on
        # different lines!
        if "pos_sw" in line:
            self.posSwNext = True
            return
        if self.posSwNext:
            # parse the 3 integers
            posSw = [int(x) for x in line.split()]
            assert len(posSw) == 3
            self.dict["pos_sw"] = posSw
            self.posSwNext = False
            return

        # the non-keyvalue type lines
        if "_axis" in line:
            self.setCurrentAxis(line)
            return
        if "overtravel" in line:
            self.dict[self._currentAxis]["overtravel"] = line.endswith("on")
            return
        # key value type lines
        key, value = line.split(None, 1)
        keyType = key.split("_")[-1]
        if keyType in ["position", "speed", "setpoint"]:
            # parse as float
            self.dict[self._currentAxis][key] = float(value)
        elif keyType == "fault":
            # parse as int
            self.dict[self._currentAxis][key] = int(value)
        elif keyType == "range":
            self.dict[self._currentAxis][key] = [float(x) for x in value.split("-")]
        elif "cartridge" in key:
            self.dict[key] =  int(value)
        else:
            return False
        return True

    def getStateKW(self):
        # determine time remaining in this state
        timeElapsed = time.time() - self._timeStamp
        # cannot have negative time remaining
        timeRemaining = max(0, self._totalTime - timeElapsed)
        return "ThreadringState=%s, %i, %i, %.2f, %.2f"%(
            self._state, self.currIter, self.maxIter, timeRemaining, self._totalTime
            )

    def getFaultStr(self):
        faultList = []
        for axis, val in self.dict.iteritems():
            if hasattr(val, "iteritems"):
                for key, value in val.iteritems():
                    if "_fault" in key and bool(value):
                        # fault value is non zero or not None
                        faultList.append("%s %s %i"%(axis, key, val))
        if not faultList:
            # no faults
            return None
        else:
            faultStr = ",".join(faultList)
            return "ScaleRingFaults=%s"%faultStr

    def statusStr(self):
        kwList = []
        kwList.append("ThreadRingPos=%.4f"%self.position)
        kwList.append("ThreadRingSpeed=%.4f"%self.speed)
        kwList.append("ThreadRingMaxSpeed=%.4f"%self.maxSpeed)
        kwList.append("DesThreadRingPos=%.4f"%self.desPosition)
        kwList.append("instrumentNum=%i; text='LCOHACK, cartNum is hardcoded in scaleDevice'"%20)#self.cartID) #LCOHACK hardcode to match cart info in db
        kwList.append("CartLocked=%s"%"T" if self.locked else "F")
        kwList.append("CartLoaded=%s"%"T" if self.loaded else "F")
        return "; ".join(kwList)

class ScaleDevice(TCPDevice):
    """!A Device for communicating with the LCO Scaling ring."""
    validCmdVerbs = ["move", "stop", "status", "speed"]
    def __init__(self, name, host, port, measScaleDevice=None, nomSpeed=NOM_SPEED, callFunc=None):
        """!Construct a ScaleDevice

        Inputs:
        @param[in] name  name of device
        @param[in] host  host address of scaling ring controller
        @param[in] port  port of scaling ring controller
        @param[in] measScaleDevice  instance of a MeasScaleDevice (access to the mitutoyos for servoing)
        @param[in] nom_speed nominal speed at which to move (this can be modified via the speed command)
        @param[in] callFunc  function to call when state of device changes;
                note that it is NOT called when the connection state changes;
                register a callback with "conn" for that task.
        """
        self.targetPos = None
        # holds a userCommand for "move"
        # set done only when move has reached maxIter
        # or is within tolerance
        self.iter = 0
        self.moveUserCmd = expandUserCmd(None)
        self.moveUserCmd
        self.nomSpeed = nomSpeed
        self.measScaleDevice = measScaleDevice
        self.status = Status()

        # all commands of equal priority
        # except stop kills a running (or pending move) move
        # priorityDict = {"stop": CommandQueue.Immediate}
        priorityDict = {
            "stop":1,
            "status":1,
            "move":1,
            "speed":1,
        }
        self.devCmdQueue = CommandQueue(
            priorityDict,
            killFunc = self.killFunc,
            )
        # stop will kill a running move
        # else everything queues with equal prioirty
        self.devCmdQueue.addRule(CommandQueue.KillRunning, ["stop"], ["move"])

        TCPDevice.__init__(self,
            name = name,
            host = host,
            port = port,
            callFunc = callFunc,
            cmdInfo = (),
        )

    def _addMeasScaleDev(self, measScaleDevice):
        """Add a way to add a measScaleDevice exposfacto,
        really this is only for use with the device wrappers.
        Any real use should specify measScaleDevice in __init__
        """
        self.measScaleDevice = measScaleDevice

    def killFunc(self, doomedCmd, killerCmd):
        doomedCmd.setState(doomedCmd.Failed, "Killed by %s"%(str(killerCmd)))

    @property
    def currExeDevCmd(self):
        return self.devCmdQueue.currExeCmd.cmd

    @property
    def currDevCmdStr(self):
        return self.currExeDevCmd.cmdStr

    @property
    def isMoving(self):
        return self.moveUserCmd.isActive

    def init(self, userCmd=None, timeLim=None, getStatus=False):
        """Called automatically on startup after the connection is established.
        Only thing to do is query for status or connect if not connected
        """
        log.info("%s.init(userCmd=%s, timeLim=%s, getStatus=%s)" % (self, userCmd, timeLim, getStatus))
        userCmd = expandUserCmd(userCmd)
        # stop, set speed, then status?
        stopCmd = self.queueDevCmd("stop", userCmd)
        speedCmd = self.queueDevCmd("speed %.4f"%self.nomSpeed, userCmd)
        statusCmd = self.queueDevCmd("status", userCmd)
        LinkCommands(userCmd, [stopCmd, speedCmd, statusCmd])
        return userCmd
        # if getStatus:
        #     return self.getStatus(userCmd=userCmd)
        # else:
        #     userCmd.setState(userCmd.Done)
        #     return userCmd

    def getStatus(self, userCmd=None, timeLim=None, linkState=True):
        """!Get status of the device.  If the device is
        busy (eg moving), send the cached status
        note that during moves the thread_ring_axis actual_position gets
        periodically output and thus updated in the status
        """
        userCmd = expandUserCmd(userCmd)
        if timeLim is None:
            timeLim = 2
        if self.isMoving:
            self.writeToUsers("i", "text=showing cached status", userCmd)
            self.writeStatusToUsers(userCmd)
            userCmd.setState(userCmd.Done)
        else:
            # get a completely fresh status from the device
            statusDevCmd = self.queueDevCmd("status", userCmd)
            # get encoder values too
            encStatusDevCmd = self.getStatus()
            statusDevCmd.addCallback(self._statusCallback)
            statusDevCmd.setTimeLimit(timeLim)
            if linkState:
                LinkCommands(userCmd, [statusDevCmd, encStatusDevCmd])
                return userCmd
            else:
                # return the device command to be linked outside
                return statusDevCmd

    def _statusCallback(self, statusCmd):
        # if statusCmd.isActive:
        #     # not sure this is necessary
        #     # but ensures we get a 100% fresh status
        #     self.status.flushStatus()
        if statusCmd.isDone and not statusCmd.didFail:
            # write the status we have to users
            # if this was a status, write output to users
            # and set the current axis back to the thread ring
            self.status.setThreadAxisCurrent()
            # full status is checked in handleReply, and
            # another status is commanded if the current status
            # is munged
            # statusError = self.status.checkFullStatus()
            # if statusError:
            #     print("status Error")
            #     self.writeToUsers("w", statusError, statusCmd.userCmd)
            self.writeStatusToUsers(statusCmd.userCmd)

    def writeStatusToUsers(self, userCmd=None):
        """Write the current status to all users
        """

        faultStr = self.status.getFaultStr()
        if faultStr is not None:
            self.writeToUsers("w", faultStr, userCmd)
        statusError = self.status.checkFullStatus()
        if statusError:
            self.writeToUsers("w", statusError)
        statusKWs = self.status.statusStr()
        self.writeToUsers("i", statusKWs, userCmd)
        self.writeState(userCmd)

    def writeState(self, userCmd=None):
        stateKW = self.status.getStateKW()
        self.writeToUsers("i", stateKW, userCmd)


    def speed(self, speedValue, userCmd=None):
        """Set the desired move speed for the thread ring
        @param[in] speedValue: a float, scale value to be converted to steps and sent to motor
        @param[in] userCmd: a twistedActor BaseCommand
        """
        speedValue = float(speedValue)
        userCmd = expandUserCmd(userCmd)
        if self.isMoving:
            userCmd.setState(userCmd.Failed, "Cannot set speed, device is busy moving")
            return userCmd
        elif float(speedValue) > self.status.maxSpeed:
            userCmd.setState(userCmd.Failed, "Max Speed Exceeded: %.4f > %.4f"%(speedValue, self.status.maxSpeed))
            return userCmd
        else:
            speedDevCmd = self.queueDevCmd("speed %.6f"%speedValue, userCmd)
            statusDevCmd = self.queueDevCmd("status", userCmd)
            statusDevCmd.addCallback(self._statusCallback)
            LinkCommands(userCmd, [speedDevCmd, statusDevCmd])
        return userCmd

    def getMoveCmdStr(self):
        """Determine difference between current and
        desired position and send move command as an
        offset.

        This is hacky.  I'm only allowed to command absolute positions
        on the scaling ring so i need to determine the absolute position wanted
        based on the offset I measure...gah.
        """
        offset = self.targetPos - self.measScaleDevice.position
        absMovePos = self.status.position + offset
        return "move %.6f"%(absMovePos)

    def move(self, position, userCmd=None):
        """!Move to a position

        @param[in] postion: a float, position to move to (mm)
        @param[in] userCmd: a twistedActor BaseCommand
        """
        log.info("%s.move(postion=%.6f, userCmd=%s)" % (self, position, userCmd))
        userCmd=expandUserCmd(userCmd)
        if self.isMoving:
            userCmd.setState(userCmd.Failed, "Cannot move, device is busy moving")
            return userCmd
        # verify position is in range
        minPos, maxPos = self.status.moveRange
        if not minPos<=position<=maxPos:
            userCmd.setState(userCmd.Failed, "Move %.6f not in range [%.4f, %.4f]"%(position, minPos, maxPos))
            return userCmd
        self.iter = 1
        self.targetPos = position
        self.moveUserCmd = userCmd
        if not self.moveUserCmd.isActive:
            self.moveUserCmd.setState(self.moveUserCmd.Running)
        self.writeToUsers("i", "DesThreadRingPos=%.4f"%self.targetPos)
        moveDevCmd = self.queueDevCmd(self.getMoveCmdStr(), self.moveUserCmd)
        moveDevCmd.addCallback(self._moveCallback)
        return userCmd

    def home(self, userCmd=None):
        log.info("%s.home(userCmd=%s)" % (self, userCmd))
        setCountCmd = self.measScaleDevice.setCountState()

        def finishHome(_zeroEncCmd):
            if _zeroEncCmd.didFail:
                userCmd.setState(userCmd.Failed, "Encoder zero failed.")
            elif _zeroEncCmd.isDone:
                userCmd.setState(userCmd.Done)

        def zeroEncoders(_moveCmd):
            if _moveCmd.didFail:
                userCmd.setState(userCmd.Failed, "Failed to move scaling ring to home position")
            elif _moveCmd.isDone:
                # zero the encoders in 1 second (give the ring a chance to stop)
                def zeroEm():
                    zeroEncCmd = self.measScaleDevice.setZero()
                    zeroEncCmd.addCallback(finishHome)
                reactor.callLater(1., zeroEm)

        def moveThreadRing(_setCountCmd):
            if _setCountCmd.didFail:
                userCmd.setState(userCmd.Failed, "Failed to set Mitutoyo EV counter into counting state")
            elif _setCountCmd.isDone:
                moveCmd = self.queueDevCmd("move %.6f"%self.measScaleDevice.zeroPoint, userCmd)
                moveCmd.addCallback(zeroEncoders)
        setCountCmd.addCallback(moveThreadRing)

    def _moveCallback(self, moveCmd):
        if moveCmd.isActive:
            self.status.setThreadAxisCurrent() # should already be there but whatever
            # set state to moving, compute time, etc
            time4move = abs(self.targetPos-self.status.position)/float(self.status.speed)
            # update command timeout
            moveCmd.setTimeLimit(time4move+2)
            self.status.setState(self.status.Moving, self.iter, time4move)
            self.writeState(self.moveUserCmd)
        if moveCmd.didFail:
            self.moveUserCmd.setState(self.moveUserCmd.Failed, "Failed to move scaling ring.")
        elif moveCmd.isDone:
            # get the status of the scaling ring
            moveStatusCmd = self.queueDevCmd("status", self.moveUserCmd)
            moveStatusCmd.addCallback(self._statusCallback)
            moveStatusCmd.addCallback(self._readEncs)

    def _readEncs(self, moveStatusCmd):
        if moveStatusCmd.didFail:
            self.moveUserCmd.setState(self.moveUserCmd.Failed, "Failed to get scaling ring status after move.")
        elif moveStatusCmd.isDone:
            # move's done, read the encoders
            # and get scaling ring status
            readEncCmd = self.measScaleDevice.getStatus()
            readEncCmd.addCallback(self._moveIter)

    def _moveIter(self, readEncCmd):
        """Encoders have been read, decide to move again or finish the user
        commanded move
        """
        if readEncCmd.didFail:
            self.moveUserCmd.setState(self.moveUserCmd.Failed, "Failed to read encoders after scaling ring move.")
        elif readEncCmd.isDone:
            atMaxIter = self.iter > self.status.maxIter
            withinTol = numpy.abs(self.targetPos - self.measScaleDevice.position) < self.status.moveTol
            if atMaxIter:
                self.writeToUsers("i", "text='Max iter reached for scaling ring move.'")
            if atMaxIter or withinTol:
                # the move is done
                self.iter = 0
                self.status.setState(self.status.Done, self.iter)
                self.writeState(self.moveUserCmd)
                self.moveUserCmd.setState(self.moveUserCmd.Done)
            else:
                # command another move iteration
                self.iter += 1
                self.writeToUsers("i", "text='Begining scaling ring move iteration %i'"%self.iter)
                moveDevCmd = self.queueDevCmd(self.getMoveCmdStr(), self.moveUserCmd)
                moveDevCmd.addCallback(self._moveCallback)


    def stop(self, userCmd=None):
        """Stop any scaling movement, cancelling any currently executing
        command and any commands waiting on queue

        @param[in] userCmd: a twistedActor BaseCommand
        """
        userCmd=expandUserCmd(userCmd)
        # kill any commands pending on the queue
        # nicely kill move command if it's running
        # if not self.currExeDevCmd.userCmd.isDone:
        #     self.currExeDevCmd.userCmd.setState(self.currExeDevCmd.userCmd.Failed, "Killed by stop")
        if self.moveUserCmd.isActive:
            self.moveUserCmd.setState(self.moveUserCmd.Cancelled, "Scaling ring move cancelled by stop command.")
        stopDevCmd = self.queueDevCmd("stop", userCmd)
        statusDevCmd = self.queueDevCmd("status", userCmd)
        statusDevCmd.addCallback(self._statusCallback)
        LinkCommands(userCmd, [stopDevCmd, statusDevCmd])
        return userCmd

    def handleReply(self, replyStr):
        """Handle a line of output from the device.

        @param[in] replyStr   the reply, minus any terminating \n
        """
        log.info("%s.handleReply(replyStr=%s)" % (self, replyStr))
        replyStr = replyStr.strip().lower()
        # print(replyStr, self.currExeDevCmd.cmdStr)
        if not replyStr:
            return
        if self.currExeDevCmd.isDone:
            # ignore unsolicited output?
            log.info("%s usolicited reply: %s for done command %s" % (self, replyStr, str(self.currExeDevCmd)))
            self.writeToUsers("i", "%s usolicited reply: %s for done command %s" % (self, replyStr, str(self.currExeDevCmd)))
            return
        if replyStr == "ok":
            # print("got ok", self.currExeDevCmd.cmdStr)
            if self.currExeDevCmd.cmdStr == "status":
                # if this is a status, verify it was not mangled before setting done
                # if it is mangled try again
                try:
                    statusError = self.status.checkFullStatus()
                except MungedStatusError as statusError:
                    # status was munged, try again
                    print("statusError", statusError)
                    self.writeToUsers("w", statusError, self.currExeDevCmd.userCmd)
                    self.status.nIter += 1
                    if self.status.nIter > self.status.maxIter:
                        self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Maximum status iter reached. Status output generally mangled?")
                    else:
                        self.writeToUsers("w", "scale status mangle trying again iter %i"%self.status.nIter, self.currExeDevCmd.userCmd)
                        print("status munged, rewriting status")
                        log.info("%s writing %r iter %i" % (self, "status", self.status.nIter))
                        self.conn.writeLine("status")
                    return
                print("status done and good")
            self.currExeDevCmd.setState(self.currExeDevCmd.Done)
        elif replyStr == self.currExeDevCmd.cmdStr:
            # command echo
            pass
        elif "error" in replyStr:
            self.currExeDevCmd.setState(self.currExeDevCmd.Failed, replyStr)
        elif self.currExeDevCmd.cmdStr == "status":
            # only parse lines if we asked for status
            try:
                parsed = self.status.parseStatusLine(replyStr)
            except Exception as e:
                errMsg = "Scale Device failed to parse: %s"%str(replyStr)
                print(traceback.print_exc(file=sys.stdout))
                log.error(errMsg)
                self.writeToUsers("w", errMsg)
            # if not parsed:
            #     print("%s.handleReply unparsed line: %s" % (self, replyStr))
            #     log.info("%s.handleReply unparsed line: %s" % (self, replyStr))


    # def sendCmd(self, devCmdStr, userCmd):
    #     """!Execute the command
    #     @param[in] devCmdStr  a string to send to the scale controller
    #     @param[in] userCmd  a user command
    #     """
    #     if not self.conn.isConnected:
    #         log.error("%s cannot write %r: not connected" % (self, userCmd.cmdStr))
    #         userCmd.setState(userCmd.Failed, "not connected")
    #         return
    #     if not self.currCmd.isDone:
    #         log.error("%s cannot write %r: existing command %r not finished" % (self, userCmd.cmdStr, self.currCmd.cmdStr))
    #         userCmd.setState(userCmd.Failed, "device is busy")
    #         return
    #     self.currCmd = userCmd
    #     self.currDevCmdStr = devCmdStr
    #     log.info("%s writing %s" % (self, devCmdStr))
    #     self.conn.writeLine(devCmdStr)

    def queueDevCmd(self, devCmdStr, userCmd):
        """Add a device command to the device command queue

        @param[in] devCmdStr: a command string to send to the device.
        @param[in] userCmd: a UserCmd associated with this device (probably but
                                not necessarily linked.  Used here for writeToUsers
                                reference.
        """
        log.info("%s.queueDevCmd(devCmdStr=%r, cmdQueue: %r"%(self, devCmdStr, self.devCmdQueue))
        # append a cmdVerb for the command queue (otherwise all get the same cmdVerb and cancel eachother)
        # could change the default behavior in CommandQueue?
        cmdVerb = devCmdStr.split()[0]
        assert cmdVerb in self.validCmdVerbs
        devCmd = DevCmd(cmdStr=devCmdStr)
        devCmd.cmdVerb = cmdVerb
        devCmd.userCmd = userCmd
        def queueFunc(devCmd):
            # when the command is ready run this
            # everything besides a move should return quickly
            devCmd.setTimeLimit(SEC_TIMEOUT)
            devCmd.setState(devCmd.Running)
            if cmdVerb == "status":
                # wipe status, to ensure we've
                # gotten a full status when done.
                self.status.flushStatus()
            self.startDevCmd(devCmd.cmdStr)
        self.devCmdQueue.addCmd(devCmd, queueFunc)
        return devCmd


    def startDevCmd(self, devCmdStr):
        """
        @param[in] devCmdStr a line of text to send to the device
        """
        devCmdStr = devCmdStr.lower()
        log.info("%s.startDevCmd(%r)" % (self, devCmdStr))
        try:
            if self.conn.isConnected:
                log.info("%s writing %r" % (self, devCmdStr))
                self.conn.writeLine(devCmdStr)
            else:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Not connected")
        except Exception as e:
            self.currExeDevCmd.setState(self.currExeDevCmd.Failed, textMsg=strFromException(e))

"""
Example status output:

THREAD_RING_AXIS:
__ACTUAL_POSITION 0.20000055
__TARGET_POSITION 0.20000000
__DRIVE_STATUS: OFF
__MOTOR_CURRENT: -0.39443308
__DRIVE_SPEED 0.05000000
__DRIVE_ACCEL 20
__DRIVE_DECEL 20
__MOVE_RANGE 0.0 - 40.0000000
__HARDWARE_FAULT 0
__INSTRUCTION_FAULT 0
__THREADRING_OVERTRAVEL_OFF
LOCK_RING_AXIS:
__ACTUAL_POSITION 18.0007000
__TARGET_POSITION 18.0000000
__OPEN_SETPOINT: 150.000000
__LOCKED_SETPOINT: 18.0000000
__DRIVE_STATUS: OFF
__MOTOR_CURRENT: 0.0
__DRIVE_SPEED 50.0000000
__DRIVE_ACCEL 20
__DRIVE_DECEL 20
__MOVE_RANGE 0.0 - 152.399994
__HARDWARE_FAULT 0
__INSTRUCTION_FAULT 0
WINCH_AXIS:
__ACTUAL_POSITION -1840.48157
__TARGET_POSITION 1652.00000
__UP_SETPOINT: 23.0000000
__TO_CART_SETPOINT: 1560.00000
__ON_CART_SETPOINT: 1652.00000
__RELEASE_SETPOINT: 1695.00000
__DRIVE_STATUS: OFF
__MOTOR_CURRENT: -0.02553883
__DRIVE_SPEED 50.0000000
__DRIVE_ACCEL 2
__DRIVE_DECEL 2
__MOVE_RANGE 0.0 - 3000.00000
__HARDWARE_FAULT 0
__INSTRUCTION_FAULT 0
SCALE_1: 1.70607793
SCALE 2: 1.66883636
SCALE 3: -0.07550588
CARTRIDGE_ID 0
__ID_SW: 0 1 2 3 4 5 6 7 8
         0 0 0 0 0 0 0 0 0
__POS_SW: 1 2 3
          0 0 0
WINCH_HOOK_SENSOR: OFF
WINCH_ENCODER_1_POS: 0.0
WINCH_ENCODER_2_POS: 0.0
WINCH_ENCODER_3_POS: 0.0
OK
"""

