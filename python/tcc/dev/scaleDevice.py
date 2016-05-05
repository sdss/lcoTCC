from __future__ import division, absolute_import

import time

# from RO.StringUtil import strFromException
import numpy

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
    "ScaleState=%s, %.4f"%(self._state, timeRemaining)
"""

__all__ = ["ScaleDevice"]


class Status(object):
    # how close you must be to the locked setpoint to be considered "locked"
    LOCKED_TOL = 0.005 # mm
    Moving = "Moving"
    Idle = "Idle"
    def __init__(self):
        self.flushStatus() # sets self.dict and a few other attrs
        self._scaleZero = None
        self._state = self.Idle
        self._timeRemaining = 0
        self._timeStamp = 0

    def setState(self, state, timeRem=0):
        """Set the state

        @param[in] state: one of self.Moving or self.Idle
        @param[in] timeRem: time remaining in this state, 0 for indefinite
        """
        assert state in [self.Moving, self.Idle]
        self._state = state
        self._timeRemaining = timeRem
        self._timeStamp = time.time()

    def getStateKW(self):
        # determine time remaining in this state
        timeElapsed = time.time() - self._timeStamp
        # cannot have negative time remaining
        timeRemaining = max(0, self._timeRemaining - timeElapsed)
        return "ScaleState=%s, %.4f"%(self._state, timeRemaining)

    @property
    def moveRange(self):
        return self.dict["thread_ring_axis"]["move_range"]

    @property
    def scaleZero(self):
        # defines the scale zeropoint in mm
        if self._scaleZero is not None:
            return self._scaleZero
        else:
            return numpy.mean(self.moveRange)

    @property
    def speed(self):
        return self.dict["thread_ring_axis"]["speed"]

    @property
    def position(self):
        return self.dict["thread_ring_axis"]["actual_position"]

    @property
    def desPosition(self):
        return self.dict["thread_ring_axis"]["target_position"]

    @property
    def cartID(self):
        return self.dict["cartridge_id"]

    @property
    def loaded(self):
        # all 3 position switches?
        sw = self.dict["pos_sw"]
        if sw is None:
            return False
        return not False in [bool(sw) for x in sw]

    @property
    def locked(self):
        # all 3 position switches?
        pos = self.dict["lock_ring_axis"]["actual_potition"]
        if pos is None:
            return False
        lockedPos = self.dict["lock_ring_axis"]["locked_setpoint"]
        return abs(pos-lockedPos) > self.LOCKED_TOL

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

    def _getEmptyStatusDict(self):
        """Return an empty status dict to be popuated
        """
        return {
            "thread_ring_axis": {
                "actual_position": None,
                "target_position": None,
                "drive_speed": None,
                "move_range": None,
                "hardware_fault": None,
                "instruction_fault": None,
                "overtravel": None,
            },
            "lock_ring_axis": {
                "actual_position": None,
                "target_position": None,
                "open_setpoint": None,
                "locked_setpoint": None,
                "move_range": None,
                "hardware_fault": None,
                "instruction_fault": None,
            },
            "winch_axis": {
                "actual_position": None,
                "target_position": None,
                "move_range": None,
                "up_setpoint": None,
                "hardware_fault": None,
                "instruction_fault": None,

            },
            "cartridge_id": None,
            "pos_sw": None
        }

    def checkFullStatus(self, statusDict, axis=None):
        """Verify that every piece of status we expect is found in
        statusDict
        """
        for key, val in statusDict.iteritems():
            if hasattr(val, "iteritems"):
                # val is a dict
                self.assertFullStatus(val, axis=key)
            else:
                if val is None:
                    errStr = "Status: %s not found"%(key)
                    if axis is not None:
                        errStr += " for %s"%axis
                    return errStr
        return "" # return empty string if no status missing

    def parseStatusLine(self, line):
        # see status example at below
        # some status lines include a colon, get rid of it, along with any leading underscores
        line = line.strip().strip("_").lower().replace(":", "")
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
        kwList.append("ScaleZeroPos=%.4f"%self.scaleZero)
        kwList.append("ThreadRingSpeed%.4f"%self.speed)
        kwList.append("DesThreadRingPos=%.4f"%self.desPosition)
        kwList.append("CartID=%i"%self.cartID)
        kwList.append("CartLocked=%s"%(str(self.locked)))
        kwList.append("CartLoaded=%s"%(str(self.loaded)))
        return "; ".join([kwList])

class ScaleDevice(TCPDevice):
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
        self.targetPos = None
        self.status = Status()

        # self.currCmd = UserCmd()
        # self.currCmd.setState(self.currCmd.Done)
        # self.currDevCmdStr = ""

        self.devCmdQueue = CommandQueue({}) # all commands of equal priority

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

    # @property
    # def currCmdVerb(self):
    #     return self.currDevCmdStr.split()[0]

    @property
    def targetScaleFactor(self):
        return self.mm2scale(self.targetPos)

    @property
    def currentScaleFactor(self):
        return self.mm2scale(self.status.position)

    @property
    def isMoving(self):
        return self.status._state == self.status.Moving

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
        """!Get status of the device.  If the device is
        busy (eg moving), send the cached status
        note that during moves the thread_ring_axis actual_position gets
        periodically output and thus updated in the status
        """
        userCmd = expandUserCmd(userCmd)
        if self.isMoving:
            self.writeStatusToUsers(userCmd)
            self.userCmd.setState(self.userCmd.Done)
        else:
            # get a completely fresh status from the device
            statusDevCmd = self.queueCmd("status", userCmd)
            statusDevCmd.addCallback(self._statusCallback)
            LinkCommands(userCmd, [statusDevCmd])
        return userCmd

    def _statusCallback(self, statusCmd):
        if statusCmd.isActive:
            # not sure this is necessary
            # but ensures we get a 100% fresh status
            self.status.flushStatus()
        elif statusCmd.isDone:
            # write the status we have to users
            # if this was a status, write output to users
            # and set the current axis back to the thread ring
            self.status.setThreadAxisCurrent()
            statusError = self.status.checkFullStatus()
            if statusError:
                self.writeToUsers("w", statusError)
            self.writeStatusToUsers(cmd=statusCmd.currCmd)

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

    def setScaleZeroPoint(self, zeroPoint, userCmd=None):
        """Set the scale zero point (in mm)

        @param[in] zeroPoint: the value in mm to set as scale zero point
        @param[in] userCmd: a twistedActor BaseCommand
        """
        zeroPoint = float(zeroPoint)
        minScale, maxScale = self.status.moveRange
        if not (minScale<=zeroPoint<=maxScale):
            # zero point is outside the vaild move range
            userCmd.setState(userCmd.Failed, "%.4f is outside vaild thread ring range: [%.2f, %.2f]"%(zeroPoint, minScale, maxScale))
        else:
            self.status._scaleZero = zeroPoint
            userCmd.setState(userCmd.Done)
        return userCmd

    def speed(self, speedValue, userCmd=None):
        """Set the desired move speed for the thread ring
        @param[in] speedValue: a float, scale value to be converted to steps and sent to motor
        @param[in] userCmd: a twistedActor BaseCommand
        """
        pass

    def move(self, position, userCmd=None):
        """!Move to a position

        @param[in] postion: a float, position to move to (mm)
        @param[in] userCmd: a twistedActor BaseCommand
        """
        log.info("%s.move(postion=%.6f, userCmd=%s)" % (self, position, userCmd))
        userCmd=expandUserCmd(userCmd)
        # verify position is in range
        moveCmdStr = "move %.6f"%(position)
        # status output from move corresponds to threadring
        # after a status command the winch axis is the current axis
        self.status.setThreadAxisCurrent() # should already be there but whatever
        self.sendCmd(moveCmdStr, userCmd)
        # start a timer
        return userCmd

    def _moveCallback(self, moveCmd):
        pass

    def moveCmd(self, devCmd):
        # stop a timer?
        pass

    def stop(self, userCmd=None):
        """Stop any scaling movement, cancelling any currently executing
        move

        @param[in] userCmd: a twistedActor BaseCommand
        """
        userCmd=expandUserCmd(userCmd)
        if self.isMoving:
            self.currCmd.setState(self.currCmd.Cancelled, "Move Stopped")
        self.sendCmd("stop", userCmd)
        return userCmd

    def handleReply(self, replyStr):
        """Handle a line of output from the device.

        @param[in] replyStr   the reply, minus any terminating \n
        """
        log.info("%s.handleReply(replyStr=%s)" % (self, replyStr))
        replyStr = replyStr.strip().lower()
        if not replyStr:
            return
        # check if this is an ok
        commandFinished = False
        if replyStr == "ok":
            commandFinished = True
        if "error" in replyStr:
            self.currCmd.setState(self.currCmd.Failed, replyStr)
            return
        if self.currDevCmdStr == "status":
            self.status.parseStatusLine(replyStr)
        elif "move" in self.currDevCmdStr and "actual_position" in replyStr:
            # will update thread_ring_axis actual_position in status
            self.status.parseStatusLine(replyStr)

        if commandFinished:
            # ok may have come even if the last command failed
            if self.currCmd.didFail:
                # some error, cmd state set to failed
                pass
            elif self.currCmd.isDone:
                raise RuntimeError("Got OK for an already done command: %r"%self.currCmd)
            else:
                # if self.currDevCmdStr == "status":
                #     # if this was a status, write output to users
                #     # and set the current axis back to the thread ring
                #     self.status.setThreadAxisCurrent()
                #     statusError = self.status.checkFullStatus()
                #     if statusError:
                #         self.currCmd.setState(self.currCmd.Failed, statusError)
                #         return
                #     self.writeStatusToUsers(cmd=self.currCmd)
                # if "move" in self.currDevCmdStr:
                #     self.moveFinished()
                self.currCmd.setState(self.currCmd.Done)

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
        devCmd = DevCmd(cmdStr=devCmdStr)
        devCmd.cmdVerb = devCmd.cmdStr
        devCmd.userCmd = userCmd
        def queueFunc(devCmd):
            # when the command is ready run this
            self.startDevCmd(devCmd.cmdStr)
        self.devCmdQueue.addCmd(devCmd, queueFunc)
        return devCmd


    def startDevCmd(self, devCmdStr):
        """
        @param[in] devCmdStr a line of text to send to the device
        """
        devCmdStr = devCmdStr.lower() # lco uses all upper case
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

