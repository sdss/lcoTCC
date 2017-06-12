from __future__ import division, absolute_import

import time
import sys
import traceback
from collections import Counter

# from RO.StringUtil import strFromException
import numpy
from twisted.internet import reactor

from twistedActor import TCPDevice, log, DevCmd, CommandQueue, expandCommand

from RO.StringUtil import strFromException
from RO.Comm.TwistedTimer import Timer

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
MOVE_TOL = 10 / 1000.0 # move tolerance (5 microns)
POLL_TIME_IDLE = 4.
POLL_TIME_MOVING = 1.
ZERO_POINT = 20 # scale zeropoint

class MungedStatusError(Exception):
    """The scaling ring occassionally returns a Munged status
    """
    pass

class Status(object):
    # how close you must be to the locked setpoint to be considered "locked"
    LOCKED_TOL = 0.1 # mm
    Moving = "Moving"
    Done = "Done"
    Homing = "Homing"
    NotHomed = "NotHomed"
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
        assert state in [self.Moving, self.Done, self.Homing, self.NotHomed]
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
        # a decision was made to use the 9 id switch values
        # in sets of 3 so that there is some redundancy in cart determination
        # if a single switch is not made.  So if two of the three agree
        # then use that value, otherwise return a value of -1 (for unknown)
        id1 = self.dict["id_sw"][:3]
        id2 = self.dict["id_sw"][3:6]
        id3 = self.dict["id_sw"][6:]
        # determine the integer value (from 3 binary bits) for the set of 3 in theory they should all match
        intVals = []
        for switchSet in [id1, id2, id3]:
            intVal = int("%i%i%i"%tuple(switchSet), 2)
            intVals.append(intVal)
        counter = Counter(intVals)
        if len(counter) == 3:
            # none agree!
            cartID = -1
        else:
            # take the most common number
            cartID = counter.most_common()[0][0]

            if cartID > 0:
                # add 20 because cart IDs at LCO start at 20
                cartID += 20

        return cartID

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
        self.idSwNext = False
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
            "pos_sw": [None, None, None],
            "id_sw": [None, None, None, None, None, None, None, None, None],
            "gang connector sw": None,
            "gang stowed sw": None,
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
                elif "id_sw" == key:
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
            self.posSwNext = False
            posSw = [int(x) for x in line.split()]
            assert len(posSw) == 3
            self.dict["pos_sw"] = posSw
            return

        if "id_sw" in line:
            self.idSwNext = True
            return
        if self.idSwNext:
            self.idSwNext = False
            # parse the 3 integers
            idSw = [int(x) for x in line.split()]
            assert len(idSw) == 9
            self.dict["id_sw"] = idSw
            return

        # the non-keyvalue type lines
        if "_axis" in line:
            self.setCurrentAxis(line)
            return
        if "overtravel" in line:
            self.dict[self._currentAxis]["overtravel"] = line.endswith("on")
            return
        # gang connector switch lines
        # (annoying because they have spaces)
        # these gang connector sw status lines were added later
        # and don't parse nicely because they have spaces
        # they are still key value types
        if "gang" in line:
            key = line.strip("on").strip("off").strip()
            value = line.endswith("on")
            self.dict[key] = value
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

class ScaleDevice(TCPDevice):
    """!A Device for communicating with the LCO Scaling ring."""
    validCmdVerbs = ["move", "stop", "status", "speed", "home"]
    def __init__(self, name, host, port, measScaleDev=None, nomSpeed=NOM_SPEED, callFunc=None):
        """!Construct a ScaleDevice

        Inputs:
        @param[in] name  name of device
        @param[in] host  host address of scaling ring controller
        @param[in] port  port of scaling ring controller
        @param[in] measScaleDev  instance of a MeasScaleDev (access to the mitutoyos for servoing)
        @param[in] nom_speed nominal speed at which to move (this can be modified via the speed command)
        @param[in] callFunc  function to call when state of device changes;
                note that it is NOT called when the connection state changes;
                register a callback with "conn" for that task.
        """
        self.tccStatus = None # set by tccLCOActor
        self.targetPos = None
        # holds a userCommand for "move"
        # set done only when move has reached maxIter
        # or is within tolerance
        self.iter = 0
        self.waitMoveCmd = expandCommand()
        self.waitMoveCmd.setState(self.waitMoveCmd.Done)
        self.nomSpeed = nomSpeed
        self.measScaleDev = measScaleDev
        self.status = Status()
        self._statusTimer = Timer()
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

    def _addMeasScaleDev(self, measScaleDev):
        """Add a way to add a measScaleDev exposfacto,
        really this is only for use with the device wrappers.
        Any real use should specify measScaleDev in __init__
        """
        self.measScaleDev = measScaleDev

    def killFunc(self, doomedCmd, killerCmd):
        doomedCmd.setState(doomedCmd.Failed, "Killed by %s"%(str(killerCmd)))

    @property
    def motorPos(self):
        """Position reported by the motor (Keithly)
        """
        return self.status.position

    @property
    def encPos(self):
        """Average position of the 3 mitutoyo encoders
        """
        return self.measScaleDev.position

    @property
    def scaleZeroPos(self):
        return ZERO_POINT

    @property
    def currExeDevCmd(self):
        return self.devCmdQueue.currExeCmd.cmd

    @property
    def isHomed(self):
        isHomed = self.measScaleDev.isHomed
        return self.measScaleDev.isHomed

    @property
    def encHomedStr(self):
        homedInt = 1 if self.isHomed else 0
        return "%i"%homedInt


    @property
    def encPosStr(self):
        encPosStr = []
        for encPos in self.measScaleDev.encPos[:3]:
            if encPos is None:
                encPosStr.append("?")
            else:
                encPos += self.scaleZeroPos
                encPosStr.append("%.3f"%encPos)
        return ", ".join(encPosStr[:3])

    @property
    def currDevCmdStr(self):
        return self.currExeDevCmd.cmdStr

    @property
    def isMoving(self):
        return self.waitMoveCmd.isActive

    def init(self, userCmd=None, timeLim=None, getStatus=False):
        """Called automatically on startup after the connection is established.
        Only thing to do is query for status or connect if not connected
        """
        log.info("%s.init(userCmd=%s, timeLim=%s, getStatus=%s)" % (self, userCmd, timeLim, getStatus))
        userCmd = expandCommand(userCmd)
        # stop, set speed, then status?
        devCmds = [DevCmd(cmdStr=cmdStr) for cmdStr in ["stop", "speed %.4f"%self.nomSpeed, "status"]]
        userCmd.linkCommands(devCmds)
        for devCmd in devCmds:
            self.queueDevCmd(devCmd)
        return userCmd
        # if getStatus:
        #     return self.getStatus(userCmd=userCmd)
        # else:
        #     userCmd.setState(userCmd.Done)
        #     return userCmd

    def getStatus(self, userCmd=None, timeLim=None):
        """!Get status of the device.  If the device is
        busy (eg moving), send the cached status
        note that during moves the thread_ring_axis actual_position gets
        periodically output and thus updated in the status
        """

        # note measScaleDevice could be read even if
        # scaling ring is moving.  do this at somepoint?
        print("scaleDev get status.")
        userCmd = expandCommand(userCmd)
        self._statusTimer.cancel() # incase a status is pending
        if timeLim is None:
            timeLim = 2
        if self.isMoving:
            # userCmd.writeToUsers("i", "text=showing cached status", userCmd)
            encStatusDevCmd = self.measScaleDev.getStatus()
            encStatusDevCmd.addCallback(self._statusCallback)
            userCmd.linkCommands([encStatusDevCmd])
            return userCmd
        else:
            # get a completely fresh status from the device
            statusDevCmd = DevCmd(cmdStr="status")
            # get encoder values too
            encStatusDevCmd = self.measScaleDev.getStatus()
            statusDevCmd.addCallback(self._statusCallback)
            statusDevCmd.setTimeLimit(timeLim)
            userCmd.linkCommands([statusDevCmd, encStatusDevCmd])
            self.queueDevCmd(statusDevCmd)
            return userCmd

    def _statusCallback(self, statusCmd):
        if statusCmd.isDone:
            self.status.setThreadAxisCurrent()
            if self.waitMoveCmd.isActive:
                self._statusTimer.start(POLL_TIME_MOVING, self.getStatus)
                # moving write to this command
                self.writeStatusToUsers(self.waitMoveCmd)
            else:
                self._statusTimer.start(POLL_TIME_IDLE, self.getStatus)
                self.writeStatusToUsers(statusCmd)


    def getStateVal(self):
        # determine time remaining in this state
        timeElapsed = time.time() - self.status._timeStamp
        # cannot have negative time remaining
        timeRemaining = max(0, self.status._totalTime - timeElapsed)
        return "%s, %i, %i, %.2f, %.2f"%(
            self.status._state, self.status.currIter, self.status.maxIter, timeRemaining, self.status._totalTime
            )

    # def getStateKW(self):
    #     # determine time remaining in this state
    #     timeElapsed = time.time() - self.status._timeStamp
    #     # cannot have negative time remaining
    #     timeRemaining = max(0, self.status._totalTime - timeElapsed)
    #     return "ThreadringState=%s, %i, %i, %.2f, %.2f"%(
    #         self.status._state, self.status.currIter, self.status.maxIter, timeRemaining, self.status._totalTime
    #         )

    def getFaultStr(self):
        faultList = []
        for axis, val in self.status.dict.iteritems():
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

    def gangVal(self):
        onCart = self.status.dict["gang connector sw"]
        atBoom = self.status.dict["gang stowed sw"]
        if onCart and not atBoom:
            # plugged into cart
            val = 2
        elif atBoom and not onCart:
            val = 1
        else:
            #unknown
            val = 0
        return "%i"%val


    def statusDict(self):
        desThreadRingPos = "%.4f"%self.targetPos if self.targetPos is not None else "NaN"
        threadRingPos = "%.4f"%self.encPos if self.encPos is not None else "NaN"
        cartLoaded = "T" if self.status.loaded else "F"
        cartLocked = "T" if self.status.locked else "F"
        return {
            "ThreadRingMotorPos": "%.4f"%self.motorPos,
            "ThreadRingEncPos": "%s"%threadRingPos,
            "ThreadRingSpeed": "%.4f"%self.status.speed,
            "ThreadRingMaxSpeed": "%.4f"%self.status.maxSpeed,
            "DesThreadRingPos": "%s"%desThreadRingPos,
            "ScaleZeroPos": "%.4f"%self.scaleZeroPos,
            "instrumentNum": "%i"%self.status.cartID,
            "CartLocked": cartLoaded,
            "CartLoaded": cartLocked,
            "apogeeGang": self.gangVal(),
            "ThreadRingState": self.getStateVal(),
            "ScaleEncPos": "%s"%self.encPosStr,
            "ScaleEncHomed": "%s"%self.encHomedStr,
        }

    def writeStatusToUsers(self, userCmd):
        """Write the current status to all users
        """
        print("writeStatusToUsers")
        faultStr = self.getFaultStr()
        if faultStr is not None:
            userCmd.writeToUsers("w", faultStr)
        if self.tccStatus is not None:
            self.tccStatus.updateKWs(self.statusDict(), userCmd)
        # output measScale KWs too
        # self.measScaleDev.writeStatusToUsers(userCmd)

    def writeState(self, userCmd=None):
        if self.tccStatus is not None:
            print("scale dev write state", self.getStateVal())
            self.tccStatus.updateKW("ThreadRingState", self.getStateVal(), userCmd)


    def speed(self, speedValue, userCmd=None):
        """Set the desired move speed for the thread ring
        @param[in] speedValue: a float, scale value to be converted to steps and sent to motor
        @param[in] userCmd: a twistedActor BaseCommand
        """
        speedValue = float(speedValue)
        userCmd = expandCommand(userCmd)
        if self.isMoving:
            userCmd.setState(userCmd.Failed, "Cannot set speed, device is busy moving")
            return userCmd
        elif float(speedValue) > self.status.maxSpeed:
            userCmd.setState(userCmd.Failed, "Max Speed Exceeded: %.4f > %.4f"%(speedValue, self.status.maxSpeed))
            return userCmd
        else:
            devCmds = [DevCmd(cmdStr=cmdStr) for cmdStr in ["speed %.6f"%speedValue, "status"]]
            devCmds[-1].addCallback(self._statusCallback)
            userCmd.linkCommands(devCmds)
            for devCmd in devCmds:
                self.queueDevCmd(devCmd)
        return userCmd

    def getMoveCmdStr(self):
        """Determine difference between current and
        desired position and send move command as an
        offset.

        This is hacky.  I'm only allowed to command absolute positions
        on the scaling ring so i need to determine the absolute position wanted
        based on the offset I measure...gah.
        """
        offset = self.targetPos - self.encPos
        absMovePos = self.status.position + offset
        return "move %.6f"%(absMovePos)

    def home(self, userCmd=None):
        log.info("%s.home(userCmd=%s)" % (self, userCmd))
        setCountCmd = self.measScaleDev.setCountState()

        def finishHome(_statusCmd):
            if _statusCmd.didFail:
                userCmd.setState(userCmd.Failed, "status failed.")
            elif _statusCmd.isDone:
                # assert that the encoders are really reading
                # zeros
                if not numpy.all(numpy.abs(self.measScaleDev.encPos) < 0.001):
                    userCmd.setState(userCmd.Failed, "zeros failed to set: %s"%str(self.measScaleDev.encPos))
                else:
                    userCmd.setState(userCmd.Done)

        def getStatus(_zeroEncCmd):
            if _zeroEncCmd.didFail:
                userCmd.setState(userCmd.Failed, "Encoder zero failed.")
            elif _zeroEncCmd.isDone:
                statusCmd = self.getStatus()
                statusCmd.addCallback(finishHome)

        def zeroEncoders(_homeCmd):
            if _homeCmd.isDone:
                self.status.setState(self.status.Done, 0)
                self.writeState(userCmd)
                print("thread home done")
            if _homeCmd.didFail:
                userCmd.setState(userCmd.Failed, "Failed to move scaling ring to home position")
            elif _homeCmd.isDone:
                # zero the encoders in 1 second (give the ring a chance to stop)
                def zeroEm():
                    print("setting zeros")
                    zeroEncCmd = self.measScaleDev.setZero()
                    zeroEncCmd.addCallback(getStatus)
                reactor.callLater(2., zeroEm)

        def homeThreadRing(_setCountCmd):
            if _setCountCmd.didFail:
                userCmd.setState(userCmd.Failed, "Failed to set Mitutoyo EV counter into counting state")
            elif _setCountCmd.isDone:
                moveHome = DevCmd(cmdStr="home")
                self.queueDevCmd(moveHome)
                moveHome.addCallback(zeroEncoders)
                self.status.setState(self.status.Homing, 0)
                self.writeState(userCmd)
        setCountCmd.addCallback(homeThreadRing)

    def move(self, position, userCmd=None):
        """!Move to a position

        @param[in] postion: a float, position to move to (mm)
        @param[in] userCmd: a twistedActor BaseCommand
        """
        log.info("%s.move(postion=%.6f, userCmd=%s)" % (self, position, userCmd))
        userCmd=expandCommand(userCmd)
        if not self.isHomed:
            userCmd.setState(userCmd.Failed, "Scaling ring not homed.  Issue threadring home.")
            return userCmd
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
        self.waitMoveCmd = expandCommand()
        self.waitMoveCmd.setState(self.waitMoveCmd.Running)
        print("moving threadring to: ", self.targetPos)
        if self.tccStatus is not None:
            self.tccStatus.updateKW("DesThreadRingPos", self.targetPos, userCmd)
        moveDevCmd = DevCmd(cmdStr=self.getMoveCmdStr())
        self.queueDevCmd(moveDevCmd)
        moveDevCmd.addCallback(self._moveCallback)
        userCmd.linkCommands([self.waitMoveCmd, moveDevCmd])
        return userCmd

    def _moveCallback(self, moveCmd):
        if moveCmd.isActive:
            self.status.setThreadAxisCurrent() # should already be there but whatever
            # set state to moving, compute time, etc
            time4move = abs(self.targetPos-self.status.position)/float(self.status.speed)
            # update command timeout
            moveCmd.setTimeLimit(time4move+2)
            self.status.setState(self.status.Moving, self.iter, time4move)
            self.writeState(self.waitMoveCmd)
        elif moveCmd.isDone and not moveCmd.didFail:
            # get the status of the scaling ring
            moveStatusCmd = DevCmd(cmdStr="status")
            self.queueDevCmd(moveStatusCmd)
            moveStatusCmd.addCallback(self._statusCallback)
            moveStatusCmd.addCallback(self._readEncs)

    def _readEncs(self, moveStatusCmd):
        if moveStatusCmd.didFail:
            self.waitMoveCmd.setState(self.waitMoveCmd.Failed, "Failed to get scaling ring status after move.")
        elif moveStatusCmd.isDone:
            # move's done, read the encoders
            # and get scaling ring status
            readEncCmd = self.measScaleDev.getStatus()
            readEncCmd.addCallback(self._moveIter)

    def _moveIter(self, readEncCmd):
        """Encoders have been read, decide to move again or finish the user
        commanded move
        """
        if readEncCmd.didFail:
            self.waitMoveCmd.setState(self.waitMoveCmd.Failed, "Failed to read encoders after scaling ring move.")
        elif readEncCmd.isDone:
            atMaxIter = self.iter > self.status.maxIter
            withinTol = numpy.abs(self.targetPos - self.encPos) < self.status.moveTol
            if atMaxIter:
                self.waitMoveCmd.writeToUsers("i", "text='Max iter reached for scaling ring move.'")
            if atMaxIter or withinTol:
                # the move is done
                self.iter = 0
                self.status.setState(self.status.Done, self.iter)
                self.writeState(self.waitMoveCmd)
                self.waitMoveCmd.setState(self.waitMoveCmd.Done)
            else:
                # command another move iteration
                self.iter += 1
                self.waitMoveCmd.writeToUsers("i", "text='Begining scaling ring move iteration %i'"%self.iter)
                moveDevCmd = DevCmd(cmdStr=self.getMoveCmdStr())
                self.queueDevCmd(moveDevCmd)
                moveDevCmd.addCallback(self._moveCallback)


    def stop(self, userCmd=None):
        """Stop any scaling movement, cancelling any currently executing
        command and any commands waiting on queue

        @param[in] userCmd: a twistedActor BaseCommand
        """
        userCmd=expandCommand(userCmd)
        if self.waitMoveCmd.isActive:
            self.waitMoveCmd.setState(self.waitMoveCmd.Cancelled, "Scaling ring move cancelled by stop command.")
        devCmds = [DevCmd(cmdStr=cmdStr) for cmdStr in ["stop", "status"]]
        devCmds[-1].addCallback(self._statusCallback)
        userCmd.linkCommands(devCmds)
        for cmd in devCmds:
            self.queueDevCmd(cmd)
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
            return
        if replyStr == "ok":
            # print("got ok", self.currExeDevCmd.cmdStr)
            if self.currExeDevCmd.cmdStr == "status":
                # if this is a status, verify it was not mangled before setting done
                # if it is mangled try again
                try:
                    self.status.checkFullStatus()
                except MungedStatusError as statusError:
                    # status was munged, try again
                    print("statusError", statusError)
                    self.status.nIter += 1
                    if self.status.nIter > self.status.maxIter:
                        self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "%s status mangled"%str(self))
                    else:
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
                self.status.parseStatusLine(replyStr)
            except:
                errMsg = "Scale Device failed to parse: %s"%str(replyStr)
                print("Exception parsing line in scaling ring (this is ok the code will try again if it's and important piece of status:")
                print(traceback.print_exc(file=sys.stdout))
                log.error(errMsg)


    def queueDevCmd(self, devCmd):
        """Add a device command to the device command queue

        @param[in] devCmdStr: a command string to send to the device.
        """
        devCmdStr = devCmd.cmdStr
        log.info("%s.queueDevCmd(devCmdStr=%r, cmdQueue: %r"%(self, devCmdStr, self.devCmdQueue))
        # append a cmdVerb for the command queue (otherwise all get the same cmdVerb and cancel eachother)
        # could change the default behavior in CommandQueue?
        cmdVerb = devCmdStr.split()[0]
        assert cmdVerb in self.validCmdVerbs
        devCmd.cmdVerb = cmdVerb
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
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Not connected to Scale Controller")
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
