from __future__ import division, absolute_import

import collections
import time

from RO.Comm.TwistedTimer import Timer
from RO.StringUtil import strFromException, degFromDMSStr

from twistedActor import TCPDevice, UserCmd, DevCmd, CommandQueue, log, expandUserCmd, LinkCommands

#TODO: Combine offset wait command and rotation offset wait commands.
# make queueDev command return a dev command rather than requiring one.
# creat a command list where subsequent commands are not sent if the previous is not successful
# i think this is handled easily by canceling all commands on the queue if the return value is not 0
# maybe we don't want this behavior in the case of the rotator, because we always want it
# to clamp!!!

SEC_TIMEOUT = 1.0

def tai():
    return time.time() - 36.

__all__ = ["TCSDevice"]
ForceSlew = "ForceSlew"

PollTimeRot = 0.5 # if rotator is slewing query frequently
PollTimeSlew = 2 #seconds, LCO says status is updated no more frequently that 5 times a second
PollTimeTrack = 5
PollTimeIdle = 10
# FocusPosTol = 0.001 # microns?
ArcSecPerDeg = 3600 # arcseconds per degree
MinRotOffset = 5 / ArcSecPerDeg # minimum commandable rotator offset
MaxRotOffset = 60 / ArcSecPerDeg # max commandable rotator offset
UnclampWaitTime = 7 # measured with a stopwatch to be 5 seconds listening to motors, add 2 extra secs buffer
ClampFudgeTime = 0.5 #seconds.  Time delay between perceived end of rotation and issuing "clamp"
RotSpeed = 1 # in degrees/second for setting timeout.

# DuPontLat = -1*(29 + 52.56 / float(ArcSecPerDeg))
# DuPontLong = 70 + 41.0 / 60. + 33.36 / float(ArcSecPerDeg)

Halted = "Halted"
Tracking = "Tracking"
Slewing = "Slewing"

CMDOFF = "OFFP"

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

def castClamp(lcoReply):
    """MRP command output:
    "%d %d %d %d %d", status.irclamped, status.mirrorexposed, status.mirrorcoveropen, status.mirrorcoverclosed, status.oilpump
    MRP
    1 0 0 1 3
    """
    return bool(lcoReply.split()[0])

class AxisState(object):
    def __init__(self, name, isStopped, isActive, isMoving, isTracking=False):
        """axisStatusStr str is output from TCS
        """
        self.name = name
        self.isStopped = bool(isStopped)
        self.isActive = bool(isActive)
        self.isMoving = bool(isMoving)
        self.isTracking = bool(isTracking)

    def __str__(self):
        return "%s: stop: %s, active: %s, moving: %s, tracking: %s"%(
            self.name.upper(), self.isStopped, self.isActive, self.isMoving, self.isTracking
            )

    def __repr__(self):
        return self.__str__()

def castAxis(lcoReply):
    """AXISSTATUS command output:

    reply.sprintf("%i %i %i %i %i %i %i %i %i %i %i",
        status.rstop, status.ractive, status.rmoving, status.rtracking,
        status.dstop, status.dactive, status.dmoving, status.dtracking,
        status.istop, status.iactive, status.imoving);
    """
    # ra axis
    flags = [bool(int(f)) for f in lcoReply.split()]
    raFlags = flags[0:4]
    decFlags = flags[4:8]
    rotFlags = flags[8:]
    axisDict = {
        "ra" : AxisState("ra", *raFlags),
        "dec" : AxisState("dec", *decFlags),
        "rot" :AxisState("rot", *rotFlags),
    }
    return axisDict



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
                # StatusField("focus", float),
                StatusField("ra", castHoursToDeg),
                StatusField("dec", degFromDMSStr),
                StatusField("inpra", castHoursToDeg),
                StatusField("inpdc", degFromDMSStr),
                StatusField("state", castTelState),
                StatusField("ha", castHoursToDeg),
                StatusField("telel", float), # I think degrees
                StatusField("telaz", float), # I think degrees
                StatusField("rot", float), # I think degrees
                # StatusField("had", float), # I think degrees, only for input?
                StatusField("epoch", float),
                StatusField("zd", float),
                StatusField("mrp", castClamp),
                StatusField("axisstatus", castAxis)
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
        self.rotOnTarg = 1 * ArcSecPerDeg # within 1 arcsec rot move is considered done
        self.statusFieldDict = collections.OrderedDict(( (x.cmdVerb, x) for x in StatusFieldList ))
        # self.focus = None
        # self.targFocus = None
        self.ra = None #unused?
        self.dec = None #unused?
        self.targRot = None
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
            "objSys": self.objSys(),
            # "secFocus": self.secFocus(),
            # "currArcOff": self.currArcOff(), 0.000000,0.000000,4947564013.2595177,0.000000,0.000000,4947564013.2595177
            # "objArcOff": self.objArcOff(), bjArcOff=0.000000,0.000000,4947564013.2595177,0.000000,0.000000,4947564013.2595177
            # TCCPos=68.361673,63.141087,nan; AxePos=68.393020,63.138022
        }

    def axisCmdStateList(self):
        axisCmdState = self.statusFieldDict["state"].value or "?"
        # check if we are really slewing instead of tracking (offsets don't trigger slew state)
        # so check manually
        ra, dec = [axisCmdState]*2
        rot = Halted if self.isClamped else Slewing
        raSlewing, decSlewing = self.axesSlewing()
        # force ra or dec slewing if true in axesSlewing
        if raSlewing:
            ra = Slewing
        if decSlewing:
            dec = Slewing
        return [ra, dec, rot]

    def axisCmdState(self):
        """Format the AxisCmdState keyword
        """
        return "AxisCmdState=%s"%(", ".join(self.axisCmdStateList()))


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

    def objSys(self):
        """@ LCOHACK: i think coords are always fk5?
        can only query tcs for epoch
        """
        epoch = self.statusFieldDict["epoch"].value
        epochStr = "%.2f"%epoch if epoch is not None else "NaN"
        return "ObjSys=FK5, %s"%epochStr

    def axePos(self):
        """Format the AxePos keyword (alt az rot)
        """
        azPos = self.statusFieldDict["telaz"].value
        altPos = self.statusFieldDict["telel"].value
        rotPos = self.statusFieldDict["rot"].value
        azStr = "%.4f"%azPos if azPos else "NaN"
        altStr = "%.4f"%altPos if altPos else "NaN"
        rotStr = "%.4f"%rotPos if altPos else "NaN"
        axePosStr = "AxePos=%s"%(", ".join([azStr, altStr, rotStr]))
        return axePosStr

    def utc_tai(self):
        return "UTC_TAI=%0.0f"%(-36.0,) # this value is usually gotten from coordConv/earthpred, I think, which we don't have implemented...

    # def secFocus(self):
    #     secFocus = self.statusFieldDict["focus"].value
    #     secFocus = "NaN" if secFocus is None else "%.4f"%secFocus
    #     return "SecFocus=%s"%secFocus

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

    @property
    def rotOnTarget(self):
        return abs(self.targRot - self.statusFieldDict["rot"].value)<self.rotOnTarg

    def setRotOffsetTarg(self, rotOffset):
        self.targRot = self.statusFieldDict["rot"].value + rotOffset

    def axesSlewing(self):
        if self.previousDec == ForceSlew:
            decSlewing = True
        else:
            decSlewing = abs(self.previousDec - self.statusFieldDict["dec"].value) > self.decOnTarg if self.previousDec is not None else False
        if self.previousRA == ForceSlew:
            raSlewing = True
        else:
            raSlewing = abs(self.previousRA - self.statusFieldDict["ra"].value) > self.raOnTarg if self.previousRA is not None else False
        return [raSlewing, decSlewing]

    @property
    def isClamped(self):
        return self.statusFieldDict["mrp"].value

    @property
    def rotMoving(self):
        rotMoving = self.statusFieldDict["axisstatus"].value["rot"].isMoving
        print('rotMoving', rotMoving)
        return rotMoving

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
            # if oldOutput != newOutput:
            if True:
                self.tccKWDict[kw] = newOutput
                kwOutputList.append(newOutput)
        return "; ".join(kwOutputList)


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

        self.waitRotCmd = UserCmd()
        self.waitRotCmd.setState(self.waitRotCmd.Done)

        # self.waitFocusCmd = UserCmd()
        # self.waitFocusCmd.setState(self.waitFocusCmd.Done)

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

    # @property
    # def atFocus(self):
    #     if self.status.statusFieldDict["focus"].value and abs(self.targFocus - self.status.statusFieldDict["focus"].value) < FocusPosTol:
    #         return True
    #     else:
    #         return False

    @property
    def isTracking(self):
        if not self.waitOffsetCmd.isDone:
            # offsets do not trigger tcs tracking state, so we fake it here
            return False
        return self.status.statusFieldDict["state"].value == Tracking

    @property
    def isSlewing(self):

        if not self.waitOffsetCmd.isDone or not self.status.isClamped:
            # if clamp is not on, then we are moving the rotator
            return True
        else:
            return False

    def init(self, userCmd=None, timeLim=None, getStatus=True):
        """Called automatically on startup after the connection is established.
        Only thing to do is query for status or connect if not connected
        """
        log.info("%s.init(userCmd=%s, timeLim=%s, getStatus=%s)" % (self, userCmd, timeLim, getStatus))
        # print("%s.init(userCmd=%s, timeLim=%s, getStatus=%s)" % (self, userCmd, timeLim, getStatus))
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
        if not self.status.isClamped:
            # rotator is moving, get status frequently
            pollTime = PollTimeRot
        elif self.isSlewing:
            # slewing, get status kinda frequently
            pollTime = PollTimeSlew
        elif self.isTracking:
            # tracking, get status less frequently
            pollTime = PollTimeTrack
        else:
            # idle, get status infrequently (as things shouldn't be changing fast)
            pollTime = PollTimeIdle
        self._statusTimer.start(pollTime, self.getStatus)
        return userCmd

    def _statusCallback(self, cmd):
        """! When status command is complete, send info to users, and check if any
        wait commands need to be set done
        """
        # print("tcs status callback", cmd)
        if cmd.isDone and not cmd.didFail:
            # do we want status output so frequently? probabaly not.
            # perhaps only write status if it has changed...
            statusStr = self.status.getStatusStr()
            if statusStr:
                self.writeToUsers("i", statusStr, cmd)

            if self.waitOffsetCmd.isActive and not True in self.status.axesSlewing():
                self.waitOffsetCmd.setState(self.waitOffsetCmd.Done)

            if self.waitRotCmd.isActive and self.status.rotOnTarget and not self.status.rotMoving:
                self.waitRotCmd.setState(self.waitRotCmd.Done)

    # focus will come back if focus functionality ever gets ported back to the TCS

    # def focus(self, focusValue, userCmd=None):
    #     """Command a new focus move

    #     @param[in] focusValue: int, focus value in microns
    #     @param[in] userCmd: a twistedActor BaseCommand
    #     """
    #     log.info("%s.focus(userCmd=%s, focusValue=%.2f)" % (self, userCmd, focusValue))
    #     userCmd = expandUserCmd(userCmd)
    #     if not self.conn.isConnected:
    #         userCmd.setState(userCmd.Failed, "Not Connected to TCS")
    #         return userCmd
    #     if not self.waitFocusCmd.isDone:
    #         self.waitFocusCmd.setState(self.waitFocusCmd.Cancelled, "Superseded by focus")
    #     self.targFocus = focusValue
    #     self.waitFocusCmd = UserCmd()
    #     # command stop first, always
    #     devCmdList = [DevCmd(cmdStr=cmdStr) for cmdStr in ["focus stop", "focus %.4f"%focusValue]]
    #     LinkCommands(userCmd, devCmdList + [self.waitFocusCmd])
    #     for devCmd in devCmdList:
    #         self.queueDevCmd(devCmd)
    #     return userCmd

    # def focusOffset(self, focusValue, userCmd=None):
    #     """Command an offset to the current focus value

    #     @param[in] focusValue: int, focus value in microns
    #     @param[in] userCmd: a twistedActor BaseCommand
    #     """
    #     log.info("%s.focusOffset(userCmd=%s, focusValue=%.2f)" % (self, userCmd, focusValue))
    #     userCmd = expandUserCmd(userCmd)
    #     if not self.conn.isConnected:
    #         userCmd.setState(userCmd.Failed, "Not Connected to TCS")
    #         return userCmd
    #     if not self.waitFocusCmd.isDone:
    #         self.waitFocusCmd.setState(self.waitFocusCmd.Cancelled, "Superseded by focus offset")
    #     self.targFocus += focusValue
    #     self.waitFocusCmd = UserCmd()
    #     # command stop first, always
    #     devCmdList = [DevCmd(cmdStr=cmdStr) for cmdStr in ["focus stop", "dfocus %.6f"%focusValue]]
    #     LinkCommands(userCmd, devCmdList + [self.waitFocusCmd])
    #     for devCmd in devCmdList:
    #         self.queueDevCmd(devCmd)
    #     return userCmd

    def target(self, ra, dec, userCmd=None):
        """Set coordinates for a slew.

        @param[in] ra: right ascension decimal degrees
        @param[in] dec: declination decimal degrees
        @param[in] userCmd: a twistedActor BaseCommand.
        """
        log.info("%s.slew(userCmd=%s, ra=%.2f, dec=%.2f)" % (self, userCmd, ra, dec))
        userCmd = expandUserCmd(userCmd)
        if not self.conn.isConnected:
            userCmd.setState(userCmd.Failed, "Not Connected to TCS")
            return userCmd
        enterRa = "RAD %.8f"%ra
        enterDec = "DECD %.8f"%dec
        enterEpoch = "MP %.2f"%2000 # LCO: HACK should coords always be 2000?
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

        @todo, consolidate similar code with self.target?
        """
        log.info("%s.slewOffset(userCmd=%s, ra=%.6f, dec=%.6f)" % (self, userCmd, ra, dec))
        userCmd = expandUserCmd(userCmd)
        # zero the delta computation so the offset isn't marked done immediately
        self.status.previousDec = ForceSlew
        self.status.previousRA = ForceSlew
        if not self.conn.isConnected:
            userCmd.setState(userCmd.Failed, "Not Connected to TCS")
            return userCmd
        if not self.waitOffsetCmd.isDone:
            self.waitOffsetCmd.setState(self.waitOffsetCmd.Cancelled, "Superseded by new offset")
        self.waitOffsetCmd = UserCmd()
        enterRa = "OFRA %.8f"%(-1.0*ra*ArcSecPerDeg) #LCO: HACK
        enterDec = "OFDC %.8f"%(-1.0*dec*ArcSecPerDeg)
        devCmdList = [DevCmd(cmdStr=cmdStr) for cmdStr in [enterRa, enterDec, CMDOFF]]
        # set userCmd done only when each device command finishes
        # AND the pending slew is also done.
        LinkCommands(userCmd, devCmdList + [self.waitOffsetCmd])
        for devCmd in devCmdList:
            self.queueDevCmd(devCmd)
        statusStr = self.status.getStatusStr()
        if statusStr:
            self.writeToUsers("i", statusStr, userCmd)
        return userCmd

    def rotOffset(self, rot, userCmd=None):
        """Offset telescope rotator.

        @param[in] rot: in decimal degrees
        @param[in] userCmd a twistedActor BaseCommand
        """
        log.info("%s.rotOffset(userCmd=%s, ra=%.6f)" % (self, userCmd, rot))
        userCmd = expandUserCmd(userCmd)
        # zero the delta computation so the offset isn't marked done immediately
        if not self.conn.isConnected:
            userCmd.setState(userCmd.Failed, "Not Connected to TCS")
            return userCmd
        if not self.waitRotCmd.isDone:
            # rotator is unclamped, a move is in progress
            userCmd.setState(userCmd.Failed, "Rotator is unclamped (already moving)")
            return userCmd
        if abs(rot) < MinRotOffset:
            # set command done, rotator offset is miniscule
            self.writeToUsers("w", "Rot offset less than min threshold", userCmd)
            userCmd.setState(userCmd.Done)
            return userCmd
        if abs(rot) > MaxRotOffset:
            # set command failed, rotator offset is too big
            self.writeToUsers("w", "Rot offset less than min threshold", userCmd)
            userCmd.setState(userCmd.Failed, "Rot offset %.4f > %.4f"%(rot, MaxRotOffset))
            return userCmd
        self.waitRotCmd = UserCmd()
        self.waitClampCmd = UserCmd()
        self.status.setRotOffsetTarg(rot)
        clamp = DevCmd(cmdStr="CLAMP")
        # unclamp done is finished on a 7 second timer
        # it will cause the queue to wait this long before
        # sending the dcir command.
        # this 'unclamp time' was measured with a stop watch
        # and listening to the motor...
        waitUnclampCmd = UserCmd()
        enterDCIR = DevCmd(cmdStr="DCIR %.8f"%(rot))
        unclamp = DevCmd(cmdStr="UNCLAMP")

        LinkCommands(userCmd, [unclamp, waitUnclampCmd, enterDCIR, self.waitRotCmd, clamp])
        def waitForUnclamp(unclampCmdVar):
            # when unclamp returns successfull
            # set the wait unclamp command done on a 7 second
            # timer.
            if unclampCmdVar.isDone:
                Timer(UnclampWaitTime, waitUnclampCmd.setState, waitUnclampCmd.Done)

        def sendRotOffset(waitUnclampCmdVar):
            # when we're done waiting for the unclamp, send the
            # delta rot
            if waitUnclampCmdVar.isDone:
                # self.waitRotCmd is set running when dcir is sent
                self.queueDevCmd(enterDCIR)
                self.writeToUsers("i", "text=Rotator DCIR %.4f sent"%rot)

        def sendClamp(waitRotCmdVar):
            if waitRotCmdVar.isDone:
                self.queueDevCmd(clamp)
                self.writeToUsers("i", "text=Rot move done, sending CLAMP")


        unclamp.addCallback(waitForUnclamp)
        waitUnclampCmd.addCallback(sendRotOffset)
        self.waitRotCmd.addCallback(sendClamp)
        # begin the dominos game
        self.queueDevCmd(unclamp)
        self.writeToUsers("i", "text=UNCLAMP sent, waiting %i seconds to open"%UnclampWaitTime)
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
            errorStr = "handleReply failed for %s with -1"%self.currDevCmdStr
            if self.waitOffsetCmd.isActive:
                self.waitOffsetCmd.setState(self.waitOffsetCmd.Failed, errorStr)
            if self.waitRotCmd.isActive:
                # note the clamp should still execute!!!!
                self.waitRotCmd.setState(self.waitRotCmd.Failed, errorStr)
            self.currExeDevCmd.setState(self.currExeDevCmd.Failed, errorStr)
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
            # all tcs commands return immediately so set a short timeout
            devCmd.setTimeLimit(SEC_TIMEOUT)
            devCmd.setState(devCmd.Running)
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
                if CMDOFF.upper() == devCmdStr:
                    self.waitOffsetCmd.setState(self.waitOffsetCmd.Running)
                elif "DCIR" in devCmdStr:
                    self.waitRotCmd.setState(self.waitRotCmd.Running)
                self.conn.writeLine(devCmdStr)
            else:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Not connected")
        except Exception as e:
            self.currExeDevCmd.setState(self.currExeDevCmd.Failed, textMsg=strFromException(e))





