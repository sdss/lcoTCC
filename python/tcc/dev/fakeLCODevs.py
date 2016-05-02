from __future__ import division, absolute_import

from RO.Comm.TwistedTimer import Timer
from RO.Comm.TwistedSocket import TCPServer
from RO.StringUtil import dmsStrFromDeg

ArcsecPerDeg = 3600.
AxisVelocity = 1.25 # deg / sec
FocusVelocity = 100 # microns / sec
ScaleVelocity = 10 # mm /sec
TimerDelay = 0.01 # seconds till next timer update
FocusStepSize = FocusVelocity * TimerDelay # microns
AxisStepSize = AxisVelocity * TimerDelay # deg
ScaleStepSize = ScaleVelocity * TimerDelay # deg

__all__ = ["FakeScaleCtrl", "FakeTCS", "FakeM2Ctrl"]

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
        self.isMoving = False
        self.moveRange = [0., 100.]
        self.desPosition = 50
        self.position = 50
        self.moveTimer = Timer()
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
        self.position = self.incrementPosition(self.desPosition, self.position, 1)
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
            currPosStr = "CURRENT_POSITION %.6f"%self.position
            self.userSock.writeLine(currPosStr)
            self.positionTimer.start(TimerDelay, self.sendPositionLoop)

    def sendStatusAndOK(self):
        statusLines = [
            "CURRENT_POSITION %.6f"%self.position,
            "TARGET_POSITION %.6f"%self.desPosition,
            "CARTRIDGE_ID 4",
            "DRIVE_SPEED 23",
            "DRIVE_ACCEL 3",
            "MOVE_RANGE %.1f - %.1f"%(self.moveRange[0], self.moveRange[1]),
            "HARDWARE FAULT NONE",
            "INSTRUCTION_FAULT NONE",
            "OK"
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
        self.focus = 0.
        self.targFocus = 0.
        self.ra = 0.
        self.dec = 0.
        self.targRA = 0.
        self.targDec = 0.
        self.offDec = 0.
        self.offRA = 0.
        self.epoch = 2000
        self.telState = self.Idle
        self.focusTimer = Timer()
        self.slewTimer = Timer()

        FakeDev.__init__(self,
            name = name,
            port = port,
        )

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

            # commands
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
            elif tokens[0] == "SLEW":
                # slew to target
                self.doSlew()
                self.userSock.writeLine("0")
            elif tokens[0] == "MP":
                # slew to target
                # LCO: HACK, set slewing after MP is seen (this is not true TCS behavior but convenient for testing because)
                # we are not allowed to send the actual SLEW command (the operator must do that)
                self.MP = float(tokens[1])
                self.doSlew()
                self.userSock.writeLine("0")
            elif tokens[0] == "FOCUS":
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
            print "Error: ", e

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
            elif tokens[0].lower() in ["move", "focus", "offset", "dfocus"]:
                isOffset = tokens[0].lower() in ["offset", "dfocus"]
                print("isOffset", isOffset)
                for ind, value in enumerate(tokens[1:]):
                    print("value", float(value))
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
            print "Error: ", e

    def powerdown(self):
        self.galil = self.Off

    def powerup(self, doMove=False):
        self.moveState = self.Moving
        self.galilTimer.start(2., self.setDone, doMove)

    def setDone(self, doMove=False):
        if not doMove:
            self.moveState = self.Done
        self.galil = self.On
        if doMove:
            self.doMove()

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