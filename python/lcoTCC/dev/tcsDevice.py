from __future__ import division, absolute_import

import collections
import time

from RO.Comm.TwistedTimer import Timer
from RO.StringUtil import strFromException, degFromDMSStr

from twistedActor import TCPDevice, UserCmd, DevCmd, CommandQueue, log, expandUserCmd, LinkCommands

def tai():
    return time.time() - 36.

__all__ = ["TCSDevice"]

SlewTriggered = "SlewTriggered"

PollTimeSlew = 2 #seconds, LCO says status is updated no more frequently that 5 times a second
PollTimeTrack = 5
PollTimeIdle = 10
FocusPosTol = 0.001 # microns?
ArcSecPerDeg = 3600 # arcseconds per degree

# DuPontLat = -1*(29 + 52.56 / float(ArcSecPerDeg))
# DuPontLong = 70 + 41.0 / 60. + 33.36 / float(ArcSecPerDeg)

Halted = "Halted"
Tracking = "Tracking"
Slewing = "Slewing"

TelStateEnumNameDict = collections.OrderedDict((
    (1, Halted),
    (2, Tracking),
    (3, Slewing),
))

def castTelState(tcsStateResponse):
    """Convert the enumerated telescope state into a string
    """
    tcsIntResponse = int(tcsStateResponse)
    if tcsIntResponse == 4:
        # stop, same as halted
        tcsIntResponse = 1
    return TelStateEnumNameDict[tcsIntResponse]

def castHoursToDeg(tcsHourStr):
    tcsHours = degFromDMSStr(tcsHourStr)
    return tcsHours * 15.

class StatusField(object):
    def __init__(self, cmdVerb, castFunc):
        """A class defining an LCO Status Field intended to be queried for

        @param[in] cmdVerb: string to be sent to the LCO TCS server, requesting status
        @param[in] castFunc: a callable that parses LCO status output

        do we want to specify units?
        perhaps add in string key val format?
        """
        self.cmdVerb = cmdVerb
        self.castFunc = castFunc
        self.value = None

    def setValue(self, lcoReply):
        """Set the value attribute from the raw lco output
        """
        self.value = self.castFunc(lcoReply)

StatusFieldList = [
                StatusField("focus", float),
                StatusField("ra", castHoursToDeg),
                StatusField("dec", degFromDMSStr),
                StatusField("inpra", castHoursToDeg),
                StatusField("inpdc", degFromDMSStr),
                StatusField("state", castTelState),
                # StatusField("ha", castHoursToDeg),
                StatusField("telel", float), # I think degrees
                StatusField("telaz", float), # I think degrees
                StatusField("rot", float), # I think degrees
            ]

class Status(object):
    def __init__(self):
        """Container for holding current status of the TCS
        """
        # used to determine when offset is done, or AxisCmdState should be set to tracking/slewing.
        self.previousRA = None
        self.previousDec = None
        # on target when within 0:0:01 degrees dec
        # 0:0:0.2 seconds ra
        self.raOnTarg = castHoursToDeg("0:0:0.2")
        self.decOnTarg = degFromDMSStr("0:0:01")
        self.statusFieldDict = collections.OrderedDict(( (x.cmdVerb, x) for x in StatusFieldList ))
        self.focus = None
        self.targFocus = None
        self.ra = None
        self.dec = None
        self.targRA = None
        self.targDec = None
        self.offDec = None
        self.offRA = None
        self.telState = None
        self.tccKWDict = {
            "axisCmdState": self.axisCmdState(),
            "axePos": self.axePos(),
            "objNetPos": self.objNetPos(),
            "utc_tai": self.utc_tai(),
            "secFocus": self.secFocus(),
            # "currArcOff": self.currArcOff(), 0.000000,0.000000,4947564013.2595177,0.000000,0.000000,4947564013.2595177
            # "objArcOff": self.objArcOff(), bjArcOff=0.000000,0.000000,4947564013.2595177,0.000000,0.000000,4947564013.2595177
            # TCCPos=68.361673,63.141087,nan; AxePos=68.393020,63.138022
        }


    def axisCmdState(self):
        """Format the AxisCmdState keyword
        """
        axisCmdState = self.statusFieldDict["state"].value or "?"
        # check if we are really slewing instead of tracking (offsets don't trigger slew state)
        # so check manually
        axisCmdStateList = [axisCmdState, axisCmdState, "NotAvailable"]
        axisSlewingCheck = self.axisSlewing()
        for ii, manualCheck in enumerate(axisSlewingCheck):
            if manualCheck:
                # axis is moving, force it to report slewing
                axisCmdStateList[ii] = Slewing
        return "AxisCmdState=%s"%(", ".join(axisCmdStateList))


    def objNetPos(self):
        """Format the AxePos keyword (ra, dec)
        """
        raPos = self.statusFieldDict["ra"].value
        decPos = self.statusFieldDict["dec"].value
        raStr = "%.6f"%raPos if raPos else "NaN"
        decStr = "%.6f"%decPos if decPos else "NaN"
        taiSecs = "%.6f"%(tai())
        v = "%.6f"%0 # velocity always zero
        return "ObjNetPos=%s"%(",".join([raStr, v, taiSecs, decStr, v, taiSecs]))

    def axePos(self):
        """Format the AxePos keyword (alt az rot)
        """
        azPos = self.statusFieldDict["telaz"].value
        altPos = self.statusFieldDict["telel"].value
        rotPos = self.statusFieldDict["rot"].value
        azStr = "%.4f"%azPos if azPos else "NaN"
        altStr = "%.4f"%altPos if altPos else "NaN"
        rotStr = "%.4f"%rotPos if altPos else "NaN"
        return "AxePos=%s"%(", ".join([azStr, altStr, rotStr]))

    def utc_tai(self):
        return "UTC_TAI=%0.0f"%(-36.0,) # this value is usually gotten from coordConv/earthpred, I think, which we don't have implemented...

    def secFocus(self):
        secFocus = self.statusFieldDict["focus"].value
        secFocus = "NaN" if secFocus is None else "%.4f"%secFocus
        return "SecFocus=%s"%secFocus

    @property
    def arcOff(self):
        if None in [self.statusFieldDict["inpra"].value, self.statusFieldDict["ra"].value]:
            raOff = 0
        else:
            raOff = self.statusFieldDict["inpra"].value - self.statusFieldDict["ra"].value
        if None in [self.statusFieldDict["inpdc"].value, self.statusFieldDict["dec"].value]:
            decOff = 0
        else:
            decOff = self.statusFieldDict["inpdc"].value - self.statusFieldDict["dec"].value
        # return "%.6f, 0.0, 0.0, %.6f, 0.0, 0.0"%(raOff, decOff)
        return "%.6f, %.6f"%(raOff, decOff)

    def currArcOff(self):
        return "currArcOff=%s"%self.arcOff

    def objArcOff(self):
        return "objArcOff=%s"%self.arcOff

    def getStatusStr(self):
        """Grab and format tcc keywords, only output those which have changed
        """
        kwOutputList = []
        for kw in self.tccKWDict.iterkeys():
            oldOutput = self.tccKWDict[kw]
            newOutput = getattr(self, kw)()
            if kw == "axisCmdState":
                print ("old: %s,  new: %s"%(oldOutput, newOutput))
            if oldOutput != newOutput:
                self.tccKWDict[kw] = newOutput
                kwOutputList.append(newOutput)
        return "; ".join(kwOutputList)

    def axisSlewing(self):
        """Return a boolean for each axis
        """
        # if no target ra or dec entered axis is not slewing (eg startup)
        if self.previousDec == SlewTriggered:
            decMoving = True
        else:
            decMoving = abs(self.previousDec - self.statusFieldDict["dec"].value) > self.decOnTarg if self.previousDec is not None else False
        if self.previousRA == SlewTriggered:
            raMoving = True
        else:
            raMoving = abs(self.previousRA - self.statusFieldDict["ra"].value) > self.raOnTarg if self.previousRA is not None else False
        # note: figure out how to add rotator here
        return [raMoving, decMoving, False]

class TCSDevice(TCPDevice):
    """!A Device for communicating with the LCO TCS."""
    def __init__(self, name, host, port, callFunc=None):
        """!Construct a LCODevice

        Inputs:
        @param[in] name  name of device
        @param[in] host  host address of tcs controller
        @param[in] port  port of tcs controller
        @param[in] callFunc  function to call when state of device changes;
                note that it is NOT called when the connection state changes;
                register a callback with "conn" for that task.
        """
        self.status = Status()
        self._statusTimer = Timer()
        self.waitSlewCmd = UserCmd()
        self.waitSlewCmd.setState(self.waitSlewCmd.Done)
        self.waitFocusCmd = UserCmd()
        self.waitFocusCmd.setState(self.waitFocusCmd.Done)
        self.waitOffsetCmd = UserCmd()
        self.waitOffsetCmd.setState(self.waitOffsetCmd.Done)
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

    @property
    def atFocus(self):
        if self.status.statusFieldDict["focus"].value and abs(self.targFocus - self.status.statusFieldDict["focus"].value) < FocusPosTol:
            return True
        else:
            return False

    @property
    def isTracking(self):
        if not self.waitOffsetCmd.isDone:# or not self.waitSlewCmd.isDone:
            # slews finish immediately, don't need self.waitSlewCmd?
            # offsets do not trigger tcs tracking state, so we fake it here
            return False
        return self.status.statusFieldDict["state"].value == Tracking

    @property
    def isSlewing(self):
        return True in self.status.axisSlewing()

    def init(self, userCmd=None, timeLim=None, getStatus=True):
        """Called automatically on startup after the connection is established.
        Only thing to do is query for status or connect if not connected
        """
        log.info("%s.init(userCmd=%s, timeLim=%s, getStatus=%s)" % (self, userCmd, timeLim, getStatus))
        userCmd = expandUserCmd(userCmd)
        # if not self.isConnected:
        #     # time lim handled by lco.deviceCmd
        #     return self.connect(userCmd=userCmd)
        if getStatus:
            return self.getStatus(userCmd=userCmd)
        else:
            userCmd.setState(userCmd.Done)
            return userCmd

    def getStatus(self, userCmd=None):
        """Return current telescope status. Continuously poll.
        """
        log.info("%s.getStatus(userCmd=%s)" % (self, userCmd)) # logging this will flood the log
        userCmd = expandUserCmd(userCmd)
        if not self.conn.isConnected:
            userCmd.setState(userCmd.Failed, "Not Connected to TCS")
            return userCmd
        self._statusTimer.cancel() # incase a status is pending
        userCmd = expandUserCmd(userCmd)
        userCmd.addCallback(self._statusCallback)
        # record the present RA, DEC (for determining when offsets are done)
        self.status.previousRA = self.status.statusFieldDict["ra"].value
        self.status.previousDec = self.status.statusFieldDict["dec"].value
        # gather list of status elements to get
        devCmdList = [DevCmd(cmdStr=cmdVerb) for cmdVerb in self.status.statusFieldDict.keys()]
        LinkCommands(userCmd, devCmdList)
        for devCmd in devCmdList:
            self.queueDevCmd(devCmd)
        if self.isSlewing:
            pollTime = PollTimeSlew
        elif self.isTracking:
            pollTime = PollTimeTrack
        else:
            pollTime = PollTimeIdle
        self._statusTimer.start(pollTime, self.getStatus)
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

            if not self.waitSlewCmd.isDone and self.isTracking:
                self.waitSlewCmd.setState(self.waitSlewCmd.Done)
            if not self.waitFocusCmd.isDone and self.atFocus:
                self.waitFocusCmd.setState(self.waitFocusCmd.Done)
            if not self.waitOffsetCmd.isDone and not self.isSlewing:
                self.waitOffsetCmd.setState(self.waitOffsetCmd.Done)

    def focus(self, focusValue, userCmd=None):
        """Command a new focus move

        @param[in] focusValue: int, focus value in microns
        @param[in] userCmd: a twistedActor BaseCommand
        """
        log.info("%s.focus(userCmd=%s, focusValue=%.2f)" % (self, userCmd, focusValue))
        userCmd = expandUserCmd(userCmd)
        if not self.conn.isConnected:
            userCmd.setState(userCmd.Failed, "Not Connected to TCS")
            return userCmd
        if not self.waitFocusCmd.isDone:
            self.waitFocusCmd.setState(self.waitFocusCmd.Cancelled, "Superseded by focus")
        self.targFocus = focusValue
        self.waitFocusCmd = UserCmd()
        # command stop first, always
        devCmdList = [DevCmd(cmdStr=cmdStr) for cmdStr in ["focus stop", "focus %.4f"%focusValue]]
        LinkCommands(userCmd, devCmdList + [self.waitFocusCmd])
        for devCmd in devCmdList:
            self.queueDevCmd(devCmd)
        return userCmd

    def focusOffset(self, focusValue, userCmd=None):
        """Command an offset to the current focus value

        @param[in] focusValue: int, focus value in microns
        @param[in] userCmd: a twistedActor BaseCommand
        """
        log.info("%s.focusOffset(userCmd=%s, focusValue=%.2f)" % (self, userCmd, focusValue))
        userCmd = expandUserCmd(userCmd)
        if not self.conn.isConnected:
            userCmd.setState(userCmd.Failed, "Not Connected to TCS")
            return userCmd
        if not self.waitFocusCmd.isDone:
            self.waitFocusCmd.setState(self.waitFocusCmd.Cancelled, "Superseded by focus offset")
        self.targFocus += focusValue
        self.waitFocusCmd = UserCmd()
        # command stop first, always
        devCmdList = [DevCmd(cmdStr=cmdStr) for cmdStr in ["focus stop", "dfocus %.6f"%focusValue]]
        LinkCommands(userCmd, devCmdList + [self.waitFocusCmd])
        for devCmd in devCmdList:
            self.queueDevCmd(devCmd)
        return userCmd

    def slew(self, ra, dec, userCmd=None):
        """Slew telescope. If a slew is presently underway, cancel it.

        @param[in] ra: right ascension decimal degrees
        @param[in] dec: declination decimal degrees
        @param[in] userCmd: a twistedActor BaseCommand.
        """
        log.info("%s.slew(userCmd=%s, ra=%.2f, dec=%.2f)" % (self, userCmd, ra, dec))
        userCmd = expandUserCmd(userCmd)
        # zero the delta computation so the offset isn't marked done immediately
        self.status.previousDec = SlewTriggered
        self.status.previousRA = SlewTriggered
        if not self.conn.isConnected:
            userCmd.setState(userCmd.Failed, "Not Connected to TCS")
            return userCmd
        if not self.waitSlewCmd.isDone:
            self.waitSlewCmd(self.waitSlewCmd.Cancelled, "Superseded by new slew")
        self.waitSlewCmd = UserCmd()
        enterRa = "RAD %.8f"%ra
        enterDec = "DECD %.8f"%dec
        enterEpoch = "MP %.2f"%2000 # LCO: HACK
        # cmdSlew = "SLEW" # LCO: HACK operator commands slew don't send it!
        devCmdList = [DevCmd(cmdStr=cmdStr) for cmdStr in [enterRa, enterDec, enterEpoch]]#, cmdSlew]]
        # set userCmd done only when each device command finishes
        # AND the pending slew is also done.
        # when the last dev cmd is done (the slew), set axis cmd statue to slewing

        LinkCommands(userCmd, devCmdList) #LCO: HACK don't wait for a slew to finish + [self.waitSlewCmd])
        for devCmd in devCmdList:
            self.queueDevCmd(devCmd)
        statusStr = self.status.getStatusStr()
        if statusStr:
            self.writeToUsers("i", statusStr, userCmd)
        return userCmd

    def slewOffset(self, ra, dec, userCmd=None):
        """Offset telescope in right ascension and declination.

        @param[in] ra: right ascension in decimal degrees
        @param[in] dec: declination in decimal degrees
        @param[in] userCmd a twistedActor BaseCommand

        @todo, consolidate similar code with self.slew
        """
        log.info("%s.slewOffset(userCmd=%s, ra=%.6f, dec=%.6f)" % (self, userCmd, ra, dec))
        userCmd = expandUserCmd(userCmd)
        # zero the delta computation so the offset isn't marked done immediately
        self.status.previousDec = SlewTriggered
        self.status.previousRA = SlewTriggered
        if not self.conn.isConnected:
            userCmd.setState(userCmd.Failed, "Not Connected to TCS")
            return userCmd
        if not self.waitOffsetCmd.isDone:
            self.waitOffsetCmd.setState(self.waitOffsetCmd.Cancelled, "Superseded by new offset")
        self.waitOffsetCmd = UserCmd()
        enterRa = "OFRA %.8f"%(-1.0*ra*ArcSecPerDeg) #LCO: HACK
        enterDec = "OFDC %.8f"%(-1.0*dec*ArcSecPerDeg)
        cmdSlew = "OFFP"
        devCmdList = [DevCmd(cmdStr=cmdStr) for cmdStr in [enterRa, enterDec, cmdSlew]]
        # set userCmd done only when each device command finishes
        # AND the pending slew is also done.
        LinkCommands(userCmd, devCmdList + [self.waitOffsetCmd])
        for devCmd in devCmdList:
            self.queueDevCmd(devCmd)
        statusStr = self.status.getStatusStr()
        if statusStr:
            self.writeToUsers("i", statusStr, userCmd)
        return userCmd


    def handleReply(self, replyStr):
        """Handle a line of output from the device. Called whenever the device outputs a new line of data.

        @param[in] replyStr   the reply, minus any terminating \n

        Tasks include:
        - Parse the reply
        - Manage the pending commands
        - Output data to users
        - Parse status to update the model parameters
        - If a command has finished, call the appropriate command callback
        """
        log.info("%s read %r, currCmdStr: %s" % (self, replyStr, self.currDevCmdStr))
        replyStr = replyStr.strip()
        if replyStr == "-1":
            # error
            self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "handleReply failed for %s with -1"%self.currDevCmdStr)
            return
        statusField = self.status.statusFieldDict.get(self.currDevCmdStr, None)
        if statusField:
            # a piece of status was requested, parse it
            # how to check for error condition? parsing -1 as a float will still work.
            statusField.setValue(replyStr)
            self.currExeDevCmd.setState(self.currExeDevCmd.Done)
        elif replyStr == "0":
            # this was a command, a "0" is expected
            self.currExeDevCmd.setState(self.currExeDevCmd.Done)
        else:
            log.info("unexpected reply" % replyStr)
            #self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Unexpected reply %s for %s"%(replyStr, self.currDevCmdStr))


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
        devCmdStr = devCmdStr.upper() # lco uses all upper case
        log.info("%s.startDevCmd(%r)" % (self, devCmdStr))
        try:
            if self.conn.isConnected:
                log.info("%s writing %r" % (self, devCmdStr))
                self.conn.writeLine(devCmdStr)
            else:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Not connected")
        except Exception as e:
            self.currExeDevCmd.setState(self.currExeDevCmd.Failed, textMsg=strFromException(e))





