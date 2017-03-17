from __future__ import division, absolute_import

from RO.Comm.TwistedTimer import Timer
from RO.Comm.TwistedSocket import TCPServer
from RO.StringUtil import dmsStrFromDeg
import numpy
import traceback
import sys

ArcsecPerDeg = 3600.
AxisVelocity = 1.25 # deg / sec
FocusVelocity = 100 # microns / sec
ScaleVelocity = 1 # mm /sec
RotVelocity = 0.5 # arcseconds per second
TimerDelay = 0.01 # seconds till next timer update
FocusStepSize = FocusVelocity * TimerDelay # microns
AxisStepSize = AxisVelocity * TimerDelay # deg
RotStepSize = RotVelocity * TimerDelay #deg
ScaleStepSize = ScaleVelocity * TimerDelay # deg

munge = 1

GlobalScalePosition = 20 # global variable for sharing scaling ring position between fake ScaleCtrl and fake ScaleMeas

__all__ = ["FakeScaleCtrl", "FakeTCS", "FakeM2Ctrl", "FakeMeasScaleCtrl"]

class FakeDev(TCPServer):
    """!A server that emulates an echoing device for testing
    """
    def __init__(self, name, port, doEcho=False):
        """!Construct a fake device controller

        @param[in] name  name of device controller
        @param[in] port  port on which to command device controller
        @param[in] doEcho  if True echo all incoming text
        """
        self.doEcho = doEcho
        TCPServer.__init__(self,
            port=port,
            stateCallback=self.stateCallback,
            sockReadCallback = self.sockReadCallback,
            sockStateCallback = self.sockStateCallback,
        )

    def sockReadCallback(self, sock):
        cmdStr = sock.readLine()
        if self.doEcho:
            sock.writeLine(cmdStr)
        self.parseCmdStr(cmdStr)

    def parseCmdStr(self, cmdStr):
        raise NotImplementedError

    def sockStateCallback(self, sock):
        if sock.state == sock.Connected:
            print("Client at %s connected" % (sock.host))
        elif sock.state == sock.Closed:
            print("Client at %s disconnected" % (sock.host))
        if sock.isReady:
            self.userSock = sock
        else:
            self.userSock = None

    def incrementPosition(self, desiredPosition, currentPosition, stepSize):
        """move position one stepSize towards desiredPosition but don't overshoot
        return the new position
        """
        moveDist = desiredPosition - currentPosition
        sign = 1
        if moveDist == 0:
            return currentPosition
        if moveDist < 0:
            sign = -1
        newPosition = currentPosition + sign * stepSize
        # check for overshoot
        if sign*(desiredPosition - newPosition) < 0:
            #overshot return the desiredPosition
            return desiredPosition
        return newPosition

class FakeScaleCtrl(FakeDev):
    """!A server that emulates the LCO scale
    """
    def __init__(self, name, port):
        """!Construct a fake LCO scale controller

        @param[in] name  name of scale controller
        @param[in] port  port on which to command scale controller
        """
        global GlobalScalePosition
        self.isMoving = False
        self.moveRange = [0., 40.]
        self.desPosition = GlobalScalePosition # wake up in mid travel
        self.position = GlobalScalePosition
        self.speed = 0.5
        self.moveTimer = Timer()
        self.posSw1, self.posSw2, self.posSw3 = (1, 1, 1)
        self.cartID = 0
        self.lockPos = 18
        # faults
        self.trOT = False
        self.trHWF, self.trIF = 0, 0
        self.lockHWF, self.lockIF = 0, 0
        self.winchHWF, self.winchIF = 0, 0
        self.positionTimer = Timer()
        self.userSock = None # created upon connection
        FakeDev.__init__(self,
            name = name,
            port = port,
            doEcho = True,
        )
        # self.sendPositionLoop()
        # self.moveLoop()

    def moveLoop(self):
        # loops always
        global GlobalScalePosition
        self.position = self.incrementPosition(self.desPosition, self.position, self.speed*TimerDelay)
        GlobalScalePosition = self.position
        if self.position == self.desPosition:
            # move is done, send OK
            self.userSock.writeLine("OK")
            self.isMoving = False
        else:
            # keep moving
            self.moveTimer.start(TimerDelay/10., self.moveLoop)

    def parseCmdStr(self, cmdStr):
        if "status" in cmdStr.lower():
            self.sendStatusAndOK()
        elif "move" in cmdStr.lower():
            desPos = float(cmdStr.split()[-1])
            if not self.moveRange[0] <= desPos <= self.moveRange[1]:
                self.userSock.writeLine("ERROR OUT_OF_RANGE")
                self.userSock.writeLine("OK")
            else:
                self.desPosition = desPos
                self.isMoving = True
                self.moveTimer.start(0, self.moveLoop)
                self.sendPositionLoop()
        elif "speed" in cmdStr.lower():
            self.speed = float(cmdStr.split()[-1])
            self.userSock.writeLine("OK")
        elif "stop" in cmdStr.lower():
            self.stop()
        else:
            # unrecognized command
            self.userSock.writeLine("ERROR INVALID_COMMAND")
            self.userSock.writeLine("OK")

    def stop(self):
        # moveLoop will send the ok
        self.desPosition = self.position
        self.moveTimer.start(0, self.moveLoop)

    def sendPositionLoop(self):
        # only write if we are "moving"
        if self.userSock is not None and self.isMoving == True:
            currPosStr = "__ACTUAL_POSITION %.6f"%self.position
            self.userSock.writeLine(currPosStr)
            self.positionTimer.start(TimerDelay, self.sendPositionLoop)

    # def sendStatusAndOK(self):
    #     statusLines = [
    #         "CURRENT_POSITION %.6f"%self.position,
    #         "TARGET_POSITION %.6f"%self.desPosition,
    #         "CARTRIDGE_ID 4",
    #         "DRIVE_SPEED 23",
    #         "DRIVE_ACCEL 3",
    #         "MOVE_RANGE %.1f - %.1f"%(self.moveRange[0], self.moveRange[1]),
    #         "HARDWARE FAULT NONE",
    #         "INSTRUCTION_FAULT NONE",
    #         "OK"
    #     ]
    #     for line in statusLines:
    #         self.userSock.writeLine(line)

    def sendStatusAndOK(self):
        # global munge
        # munge = munge*-1
        # if munge == 1:
        #
        # else:
        #     pos = "MUNGED"
        pos = "%.7f"%self.position
        statusLines = [
            "THREAD_RING_AXIS:",
            "__ACTUAL_POSITION %s"%pos,
            "__TARGET_POSITION 0.20000000",
            "__DRIVE_STATUS: OFF",
            "__MOTOR_CURRENT: -0.39443308",
            "__DRIVE_SPEED %.7f"%self.speed,
            "__DRIVE_ACCEL 20",
            "__DRIVE_DECEL 20",
            "__MOVE_RANGE %.4f - %.4f"%tuple(self.moveRange),
            "__HARDWARE_FAULT %i"%(self.trHWF),
            "__INSTRUCTION_FAULT %i"%(self.trIF),
            "__THREADRING_OVERTRAVEL_%s"%("ON" if bool(self.trOT) else "OFF"),
            "LOCK_RING_AXIS:",
            "__ACTUAL_POSITION %.7f"%(self.lockPos),
            "__TARGET_POSITION 18.0000000",
            "__OPEN_SETPOINT: 150.000000",
            "__LOCKED_SETPOINT: 18.0000000",
            "__DRIVE_STATUS: OFF",
            "__MOTOR_CURRENT: 0.0",
            "__DRIVE_SPEED 50.0000000",
            "__DRIVE_ACCEL 20",
            "__DRIVE_DECEL 20",
            "__MOVE_RANGE 0.0 - 152.399994",
            "__HARDWARE_FAULT %i"%(self.lockHWF),
            "__INSTRUCTION_FAULT %i"%(self.lockIF),
            "WINCH_AXIS:",
            "__ACTUAL_POSITION -1840.48157",
            "__TARGET_POSITION 1652.00000",
            "__UP_SETPOINT: 23.0000000",
            "__TO_CART_SETPOINT: 1560.00000",
            "__ON_CART_SETPOINT: 1652.00000",
            "__RELEASE_SETPOINT: 1695.00000",
            "__DRIVE_STATUS: OFF",
            "__MOTOR_CURRENT: -0.02553883",
            "__DRIVE_SPEED 50.0000000",
            "__DRIVE_ACCEL 2",
            "__DRIVE_DECEL 2",
            "__MOVE_RANGE 0.0 - 3000.00000",
            "__HARDWARE_FAULT %i"%self.winchHWF,
            "__INSTRUCTION_FAULT %i"%self.winchIF,
            "SCALE_1: 1.70607793",
            "SCALE 2: 1.66883636",
            "SCALE 3: -0.07550588",
            "CARTRIDGE_ID %i"%self.cartID,
            "__ID_SW: 0 1 2 3 4 5 6 7 8",
            "         0 1 1 0 1 1 0 1 1",
            "__POS_SW: 1 2 3",
            "          %i %i %i"%(self.posSw1, self.posSw2, self.posSw3),
            "GANG CONNECTOR SW: OFF",
            "GANG STOWED SW: ON",
            "WINCH_HOOK_SENSOR: OFF",
            "WINCH_ENCODER_1_POS: 0.0",
            "WINCH_ENCODER_2_POS: 0.0",
            "WINCH_ENCODER_3_POS: 0.0",
            "OK",
        ]
        for line in statusLines:
            self.userSock.writeLine(line)


    def stateCallback(self, server=None):
        if self.isReady:
            # self.readyDeferred.callback(None)
            print("Fake scale controller %s running on port %s" % (self.name, self.port))
        elif self.didFail and not self.readyDeferred.called:
            errMsg = "Fake scale controller %s failed to start on port %s" % (self.name, self.port)
            print(errMsg)
            # self.readyDeferred.errback(failure.Failure(RuntimeError(errMsg)))


class FakeTCS(FakeDev):
    """!A server that emulates the LCO TCS

    defined here: http://espejo.lco.cl/operations/TCS_communication.html
    """
    Idle = 1
    Tracking = 2
    Slewing = 3
    Stop = 4
    def __init__(self, name, port):
        """!Construct a fake LCO TCS

        @param[in] name  name of TCS controller
        @param[in] port  port on which to command TCS
        """
        self.rstop = 0
        self.ractive = 0
        self.rmoving = 0
        self.rtracking = 0
        self.dstop = 0
        self.dactive = 0
        self.dmoving = 0
        self.dtracking = 0
        self.istop = 0
        self.iactive = 0
        self.imoving = 0

        self.isClamped = 1
        self.targRot = 0.
        self.rot = 0.
        self.focus = 0.
        self.targFocus = 0.
        self.ra = 0.
        self.dec = 0.
        self.ha = 0.
        self.targRA = 0.
        self.inpScreen = 0.
        self.inpHA = 0.
        self.targDec = 0.
        self.offDec = 0.
        self.offRA = 0.
        self.epoch = 2000
        self.telState = self.Idle
        self.focusTimer = Timer()
        self.slewTimer = Timer()
        self.rotTimer = Timer()

        FakeDev.__init__(self,
            name = name,
            port = port,
        )

    @property
    def rerr(self):
        return self.targRA - self.ra

    @property
    def derr(self):
        return self.targDec - self.dec

    @property
    def onTarget(self):
        return self.targRA == self.ra and self.targDec == self.dec

    def parseCmdStr(self, cmdStr):
        """Parse an incoming command, make it somewhat
        like the way c100.cpp does things.

        how to offsets behave, are they sticky, not here
        """
        try:
            tokens = cmdStr.strip().split(" ")

            # status requests
            if tokens[0] == "RA" and len(tokens) == 1:
                # report ra in HMS
               self.userSock.writeLine(dmsStrFromDeg(self.ra / 15.))
            elif tokens[0] ==  "DEC" and len(tokens) == 1:
               self.userSock.writeLine(dmsStrFromDeg(self.dec))
            elif tokens[0] == "RERR" and len(tokens) == 1:
               self.userSock.writeLine("%.4f"%self.rerr)
            elif tokens[0] ==  "DERR" and len(tokens) == 1:
               self.userSock.writeLine("%.4f"%self.derr)
            elif tokens[0] ==  "HA" and len(tokens) == 1:
               self.userSock.writeLine(dmsStrFromDeg(self.ha))
            elif tokens[0] ==  "POS" and len(tokens) == 1:
               self.userSock.writeLine("%.4f %.4f"%(numpy.radians(self.ha), numpy.radians(self.dec)))
            elif tokens[0] ==  "MPOS" and len(tokens) == 1:
               self.userSock.writeLine("%.4f %.4f"%(numpy.radians(self.ra), numpy.radians(self.dec)))
            elif tokens[0] ==  "EPOCH" and len(tokens) == 1:
               self.userSock.writeLine("%.2f"%(2000))
            elif tokens[0] ==  "ZD" and len(tokens) == 1:
               self.userSock.writeLine("%.2f"%(80))
            elif tokens[0] == "STATE" and len(tokens) == 1:
               self.userSock.writeLine(str(self.telState))
            elif tokens[0] == "INPRA" and len(tokens) == 1:
               self.userSock.writeLine(str(self.targRA))
            elif tokens[0] == "INPDC" and len(tokens) == 1:
               self.userSock.writeLine(str(self.targDec))
            elif tokens[0] == "TELEL" and len(tokens) == 1:
                self.userSock.writeLine(str(85.2)) # placeholder
            elif tokens[0] == "TELAZ" and len(tokens) == 1:
                self.userSock.writeLine(str(40.6)) #placeholder
            elif tokens[0] == "ROT" and len(tokens) == 1:
                self.userSock.writeLine(str(30.6)) #placeholder
            elif tokens[0] == "MRP" and len(tokens) == 1:
                mrpLine = "%i 0 0 1 3"%(self.isClamped)
                self.userSock.writeLine(mrpLine)
            elif tokens[0] == "TEMPS" and len(tokens) == 1:
                self.userSock.writeLine("18.8 10.8 12.0 11.5 8.8 13.1 -273.1 -273.1")
            elif tokens[0] == "ST" and len(tokens) == 1:
                self.userSock.writeLine("06:59:29")
            elif tokens[0] == "TTRUSS" and len(tokens) == 1:
                self.userSock.writeLine("10.979")
            elif tokens[0] == "INPHA" and len(tokens) == 1:
                self.userSock.writeLine("0")
            elif tokens[0] == "RAWPOS" and len(tokens) == 1:
                self.userSock.writeLine("1 1 1 1 1")
            elif tokens[0] == "AXISSTATUS" and len(tokens) == 1:
                axisLine = "%i %i %i %i %i %i %i %i %i %i %i" % (
                    self.rstop, self.ractive, self.rmoving, self.rtracking,
                    self.dstop, self.dactive, self.dmoving, self.dtracking,
                    self.istop, self.iactive, self.imoving
                )
                self.userSock.writeLine(axisLine)

            # commands
            elif tokens[0] == "HAD":
                assert len(tokens) == 2, "Error Parsing HAD"
                self.inpHA = float(tokens[1])
                self.userSock.writeLine("0")
            elif tokens[0] == "INPS":
                assert len(tokens) == 2, "Error Parsing INPS"
                self.inpScreen = float(tokens[1])
                self.userSock.writeLine("0")
            elif tokens[0] == "RAD":
                assert len(tokens) == 2, "Error Parsing RAD"
                self.targRA = float(tokens[1])
                self.userSock.writeLine("0")
            elif tokens[0] == "DECD":
                assert len(tokens) == 2, "Error Parsing DECD"
                self.targDec = float(tokens[1])
                self.userSock.writeLine("0")
            elif tokens[0] == "OFDC":
                assert len(tokens) == 2, "Error Parsing OFDC"
                # convert from arcseconds to degrees
                self.offDec = float(tokens[1]) / ArcsecPerDeg
                self.userSock.writeLine("0")
            elif tokens[0] == "OFRA":
                assert len(tokens) == 2, "Error Parsing OFRA"
                # convert from arcseconds to degrees
                self.offRA = float(tokens[1]) / ArcsecPerDeg
                self.userSock.writeLine("0")
            elif tokens[0] == "OFFP":
                assert len(tokens) == 1, "Error Parsising Offset Execute"
                self.targRA += self.offRA
                self.targDec += self.offDec
                self.offRA, self.offDec = 0., 0.
                self.doSlew()
                self.userSock.writeLine("0")
            elif tokens[0] == "UNCLAMP":
                self.isClamped = 0
                self.userSock.writeLine("0")
            elif tokens[0] == "CLAMP":
                self.isClamped = 1
                self.userSock.writeLine("0")
            elif tokens[0] == "APGCIR":
                assert len(tokens) == 2, "Error Parsising APGCIR Execute"
                self.targRot = float(tokens[1])
                self.doRot()
                self.userSock.writeLine("0")
            elif tokens[0] == "DCIR":
                assert len(tokens) == 2, "Error Parsising DCIR Execute"
                assert self.isClamped == 0, "Rotator is clamped"
                self.targRot += float(tokens[1])
                self.doRot()
                self.userSock.writeLine("0")
            elif tokens[0] == "SLEW":
                raise RuntimeError("SLEWS NOT ALLOWED")
                # slew to target
                self.doSlew()
                self.userSock.writeLine("0")
            elif tokens[0] == "MP":
                # set epoch
                self.MP = float(tokens[1])
                self.userSock.writeLine("0")
            elif tokens[0] == "FOCUS":
                raise RuntimeError("DON'T USE TCS FOR FOCUS!")
                if len(tokens) == 1:
                   self.userSock.writeLine(str(self.focus))
                else:
                    assert len(tokens) == 2, "Error Parsing Focus"
                    focusArg = tokens[1].upper()
                    if focusArg == "STOP":
                        self.doFocus(stop=True)
                    elif focusArg == "GO":
                        self.doFocus()
                    else:
                        # input new desired focus value and move
                        self.targFocus = float(focusArg)
                        self.doFocus()
                    self.userSock.writeLine("0")
            elif tokens[0] == "DFOCUS":
                assert len(tokens) == 2, "Error Parsing DFocus"
                # input new desired focus value and move
                self.targFocus += float(tokens[1])
                self.doFocus()
                self.userSock.writeLine("0")

            else:
                # unknown command?
                raise RuntimeError("Unknown Command: %s"%cmdStr)
        except Exception as e:
            self.userSock.writeLine("-1") # error!
            print("Error: ", e)
            traceback.print_exc(file=sys.stdout)

    def doSlew(self, offset=False):
        if not offset:
            # offset doesn't trigger slewing state
            self.telState = self.Slewing
        self.dec = self.incrementPosition(self.targDec, self.dec, AxisStepSize)
        self.ra = self.incrementPosition(self.targRA, self.ra, AxisStepSize)
        if self.onTarget:
            # slew done!
            self.telState = self.Tracking
        else:
            self.slewTimer.start(TimerDelay, self.doSlew)

    def doRot(self):
        self.rot = self.incrementPosition(self.targRot, self.rot, RotStepSize)
        if self.rot != self.targRot:
            self.rotTimer.start(TimerDelay, self.doRot)

    def doFocus(self, stop=False):
        """stop: halt focus at it's current location
        """
        if stop:
            self.focusTimer.cancel()
            return
        self.focus = self.incrementPosition(self.targFocus, self.focus, FocusStepSize)
        if self.focus != self.targFocus:
            # continue moving
            self.focusTimer.start(TimerDelay, self.doFocus)


    def stateCallback(self, server=None):
        if self.isReady:
            # self.readyDeferred.callback(None)
            print("Fake TCS controller %s running on port %s" % (self.name, self.port))
        elif self.didFail and not self.readyDeferred.called:
            errMsg = "Fake TCS controller %s failed to start on port %s" % (self.name, self.port)
            print(errMsg)
            # self.readyDeferred.errback(failure.Failure(RuntimeError(errMsg)))


class FakeM2Ctrl(FakeDev):
    """!A server that emulates the LCO M2 Controller
    """
    Done = "DONE"
    Error = "ERROR"
    Moving = "MOVING"
    On = "on"
    Off = "off"
    def __init__(self, name, port):
        """!Construct a fake LCO M2

        @param[in] name  name of M2 controller
        @param[in] port  port on which to command M2

        State=DONE Ori=12500.0,70.0,-12.0,-600.1,925.0 Lamps=off Galil=off
        """
        self.orientation = [15,70.0,-12.0,-600.1,925.0]
        self.targOrientation = [15,70.0,-12.0,-600.1,925.0]
        self.moveState = self.Done
        self.lamps = self.Off
        self.galil = self.Off
        self.speed = 25.0
        self.moveTimer = Timer()
        self.galilTimer = Timer()

        FakeDev.__init__(self,
            name = name,
            port = port,
        )

    def statusStr(self):
        return "State=%s Ori=%s Lamps=%s Galil=%s"%(
                self.moveState,
                ",".join(["%.2f"%val for val in self.orientation]),
                self.lamps,
                self.galil
            )

    def parseCmdStr(self, cmdStr):
        """Parse an incoming command, make it somewhat
        like the way c100.cpp does things.

        how to offsets behave, are they sticky, not here
        """
        try:
            tokens = cmdStr.strip().split(" ")

            # status requests
            if tokens[0].lower() == "status":
                # status
               self.userSock.writeLine(self.statusStr())
            elif tokens[0].lower() == "speed":
                self.userSock.writeLine("%.1f"%self.speed)
            elif tokens[0].lower() in ["move", "offset"] and len(tokens)==1:
                self.userSock.writeLine(" ".join(["%.2f"%val for val in self.orientation]))
            elif tokens[0].lower() in ["focus", "dfocus"] and len(tokens)==1:
                self.userSock.writeLine("%.1f"%self.orientation[0])

            # commands
            elif tokens[0].lower() == "stop":
                self.doMove(stop=True)
                self.userSock.writeLine("OK")
            elif tokens[0].lower() in ["move", "focus", "offset", "dfocus"]:
                isOffset = tokens[0].lower() in ["offset", "dfocus"]
                for ind, value in enumerate(tokens[1:]):
                    if isOffset:
                        self.targOrientation[ind] += float(value)
                    else:
                        self.targOrientation[ind] = float(value)
                self.doMove()
                self.userSock.writeLine("OK")
            elif tokens[0].lower() == "galil":
                if tokens[1].lower() == "on":
                    self.powerup()
                else:
                    self.powerdown()
                self.userSock.writeLine("OK")


            else:
                # unknown command?
                raise RuntimeError("Unknown Command: %s"%cmdStr)
        except Exception as e:
            self.userSock.writeLine("-1") # error!
            print("Error: ", e)

    def powerdown(self):
        self.galil = self.Off

    def powerup(self, doMove=False):
        self.moveState = self.Moving
        self.galilTimer.start(2., self.setDone, doMove)

    def setDone(self, doMove=False):
        self.galil = self.On
        if doMove:
            self.doMove()
        else:
            self.moveState = self.Done

    def doMove(self, stop=False):
        """stop: halt focus at it's current location
        """
        if stop:
            self.moveTimer.cancel()
            self.moveState = self.Done
            self.galil = self.Off
            return
        if not self.galil == self.On:
            # simulate power up time
            self.powerup(doMove=True)
            # move will start after powerup
            return
        self.moveState = self.Moving
        focus = self.incrementPosition(self.targOrientation[0], self.orientation[0], FocusStepSize)
        self.orientation[0] = focus
        if focus != self.targOrientation[0]:
            # continue moving
            self.moveTimer.start(TimerDelay, self.doMove)
        else:
            self.orientation = self.targOrientation[:] # copy is necessary!!!
            self.moveState = self.Done

    def stateCallback(self, server=None):
        if self.isReady:
            # self.readyDeferred.callback(None)
            print("Fake M2 controller %s running on port %s" % (self.name, self.port))
        elif self.didFail and not self.readyDeferred.called:
            errMsg = "Fake M2 controller %s failed to start on port %s" % (self.name, self.port)
            print(errMsg)
            # self.readyDeferred.errback(failure.Failure(RuntimeError(errMsg)))


class FakeMeasScaleCtrl(FakeDev):
    """!A server that emulates the Mitutoyo EV-Counter Serial interface
    """
    def __init__(self, name, port):
        """!Construct a fake MeasController

        @param[in] name  name of M2 controller
        @param[in] port  port on which to command M2
        """

        FakeDev.__init__(self,
            name = name,
            port = port,
        )

    def measResponse(self):
        # get mig position with some noise
        measPosStr = ""
        for ii in range(6):
            meas = GlobalScalePosition - 20.0
            if meas > 0:
                sign = "+"
            else:
                sign = "-"
            measPosStr += "GN0%i,%s%.3f\n"%(ii+1, sign, abs(meas))
        return measPosStr

    def parseCmdStr(self, cmdStr):
        """Parse an incoming command
        """
        cmdStr = cmdStr.strip()
        if not cmdStr:
            return
        if cmdStr == "GA00":
            self.userSock.writeLine(self.measResponse())
        elif cmdStr == "CS00":
            self.userSock.writeLine("CH00")
        elif cmdStr == "CN00":
            self.userSock.writeLine("CH00")
        elif cmdStr == "CR00":
            self.userSock.writeLine("CH00")
        else:
            # unknown command?
            self.userSock.writeLine("ERROR") # error!

    def stateCallback(self, server=None):
        if self.isReady:
            # self.readyDeferred.callback(None)
            print("Fake Meas Scale controller %s running on port %s" % (self.name, self.port))
        elif self.didFail and not self.readyDeferred.called:
            errMsg = "Fake Meas Scale controller %s failed to start on port %s" % (self.name, self.port)
            print(errMsg)
            # self.readyDeferred.errback(failure.Failure(RuntimeError(errMsg)))

class FakeFFPowerSuply(FakeDev):

    def __init__(self, name, port):
        """!Construct a fake MeasController

        @param[in] name  name of M2 controller
        @param[in] port  port on which to command M2
        """
        self.PWR = "OFF"
        self.IMAX = 37
        self.VMAX = 12
        self.ISET = 4
        self.VSET = 12
        self.IREAD = 4
        self.VREAD = 12
        self.iTimer = Timer()
        FakeDev.__init__(self,
            name = name,
            port = port,
        )

    def parseCmdStr(self, cmdStr):
        """Parse an incoming command
        """
        cmdTokens = cmdStr.strip().split()
        if not cmdTokens:
            return
        if len(cmdTokens)==2:
            value = cmdTokens[1]
        else:
            value = None
        cmdStr = cmdTokens[0]
        if cmdStr == "PWR":
            if value:
                self.PWR = value
            # set the current in 2 seconds
            if self.PWR == "ON":
                iValue = self.ISET
            else:
                iValue = 0.
            self.iTimer.start(2, self.setI, iValue)
            self.userSock.writeLine(self.PWR)
        elif cmdStr == "VMAX":
            self.userSock.writeLine("%4f"%self.VMAX)
        elif cmdStr == "IMAX":
            self.userSock.writeLine("%4f"%self.IMAX)
        elif cmdStr == "ISET":
            if value:
                self.ISET = float(value)
            self.userSock.writeLine("%4f A"%self.ISET)
        elif cmdStr == "VSET":
            if value:
                self.VSET = float(value)
            self.userSock.writeLine("%4f V {#Hdb8d=56205 raw}"%self.VSET)
        elif cmdStr == "VREAD":
            self.userSock.writeLine("%4f V {#Hdb8d=56205 raw}"%self.VSET)
        elif cmdStr == "IREAD":
            self.userSock.writeLine("%4f A"%self.IREAD)
        else:
            # unknown command?
            self.userSock.writeLine("ERROR") # error!

    def setI(self, iValue):
        self.IREAD = iValue
