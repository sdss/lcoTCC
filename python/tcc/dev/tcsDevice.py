from __future__ import division, absolute_import

import collections
import time
import numpy

from RO.Comm.TwistedTimer import Timer
from RO.Astro.Sph.AzAltFromHADec import azAltFromHADec
from RO.Astro.Sph.HADecFromAzAlt import haDecFromAzAlt
from RO.StringUtil import strFromException, degFromDMSStr

from twistedActor import TCPDevice, UserCmd, DevCmd, CommandQueue, log, expandUserCmd, LinkCommands

#TODO: Combine offset wait command and rotation offset wait commands.
# make queueDev command return a dev command rather than requiring one.
# creat a command list where subsequent commands are not sent if the previous is not successful
# i think this is handled easily by canceling all commands on the queue if the return value is not 0
# maybe we don't want this behavior in the case of the rotator, because we always want it
# to clamp!!!

SEC_TIMEOUT = 1.0
LCO_LATITUDE = -29.0146
# WS_ALT_LIMIT = 32.9 # windscreen altutude limit  # Old value
WS_ALT_LIMIT = 19.0  # windscreen altutude limit
# windscreen model
# telescope altitude measurements
# altArray = numpy.array([89.9, 79.9, 57.0, 64.0, 69.0, 74.0, 78.9, 83.9, 88.9])  # Old values
altArray = numpy.array([90, 70, 50])
# windscreen measurements
# wsArray = numpy.array([68, 57, 32.9, 40.5, 46.5, 51, 56, 61.2, 66.2])  # Old values
wsArray = numpy.array([64.2, 47., 25.6])
# ws coeffs
order = 1
WS_COEFFS = numpy.polyfit(altArray, wsArray, order)

def tai():
    return time.time() - 36.

__all__ = ["TCSDevice"]
ForceSlew = "ForceSlew"

#### telescope parameters found in c100.ini file in tcs source code #####
# Hour angle encoder scale (encoder counts / degree)
HASCALE=89978
# Hour angle maximum speed (motor encoder counts / sec)
HASP=175000
# Declination encoder scale (encoder counts / degree)
DECSCALE=-89909
# Declination maximum speed (motor encoder counts / sec)
DECSP=225000
# IR Scale - encoder counts per degree
IRSCALE = -0.00015263375
# IR Offset - encoder counts, to match mechanical readout
IROFFSET = 405.447
# IR motor steps per encoder count
IRSCALE = -0.00015263375
# IR acceleration (motor encoder counts / sec2)
IRAC=1000
# IR deceleration (motor encoder counts / sec2)
IRDC=1000
# IR fast speed (motor encoder counts / sec)
IRFASTSP=2000
# IR slow speed (motor encoder counts / sec)
IRSLOWSP=53

def encCounts2Deg(encCounts):
    """
    for converting rotator enc counts to degree position.
    this is more accurate than the TCS reported rot pos
    """
    return IROFFSET + IRSCALE * encCounts

def SlewTimeRA(deg):
    return deg * HASCALE / float(HASP)

def SlewTimeDec(deg):
    return deg * DECSCALE / float(DECSP)

PollTimeRot = 0.5 # if rotator is slewing query frequently
PollTimeSlew = 2 #seconds, LCO says status is updated no more frequently that 5 times a second
PollTimeTrack = 5
PollTimeIdle = 10
# FocusPosTol = 0.001 # microns?
ArcSecPerDeg = 3600 # arcseconds per degree
MinRotOffset = 2 / ArcSecPerDeg # minimum commandable rotator offset
# MaxRotOffset = 60 / ArcSecPerDeg # max commandable rotator offset
MaxRotOffset = 1000 / ArcSecPerDeg
UnclampWaitTime = 7 # measured with a stopwatch to be 5 seconds listening to motors, add 2 extra secs buffer
ClampFudgeTime = 0.5 #seconds.  Time delay between perceived end of rotation and issuing "clamp"
# RotSpeed = 1 # in degrees/second for setting timeout.

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

tempKeys = [
        "outsidetemp", "insidetemp", "primarytemp", "celltemp",
        "floortemp", "xyztemp", "trusstemp", "reservedtemp"
        ]

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

def castPos(tcsPosStr):
    return [numpy.degrees(float(x)) for x in tcsPosStr.split()]

def castClamp(lcoReply):
    """MRP command output:
    "%d %d %d %d %d", status.irclamped, status.mirrorexposed, status.mirrorcoveropen, status.mirrorcoverclosed, status.oilpump
    MRP
    1 0 0 1 3
    """
    return bool(int(lcoReply.split()[0]))

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

def castTemps(lcoReply):
    """Temps output
    reply.sprintf("%0.1f %0.1f %0.1f %0.1f %0.1f %0.1f %0.1f %0.1f",
                  status.outsidetemp, status.insidetemp, status.primarytemp, status.celltemp,
                  status.floortemp, status.xyztemp, status.trusstemp, status.reservedtemp);
    """
    values = [float(temp) for temp in lcoReply.split()]
    return dict(zip(tempKeys,values))

def castRawPos(lcoReply):
    items = lcoReply.split()
    # rotator encoder counts is the last element
    # in this list
    encCounts = int(items[-1])
    deg = encCounts2Deg(encCounts)
    return deg


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
                StatusField("inpha", degFromDMSStr),
                StatusField("state", castTelState),
                StatusField("st", castHoursToDeg),
                StatusField("ha", castHoursToDeg),
                StatusField("pos", castPos), #ha, dec to degrees
                StatusField("mpos", castPos), #ra, dec to degrees
                StatusField("telel", float), # I think degrees
                StatusField("telaz", float), # I think degrees
                StatusField("rot", float), # I think degrees
                # StatusField("had", float), # I think degrees, only for input?
                StatusField("epoch", float),
                StatusField("zd", float),
                StatusField("mrp", castClamp),
                StatusField("axisstatus", castAxis), #unhack this!
                StatusField("temps", castTemps),
                StatusField("ttruss", float),
                StatusField("rawpos", castRawPos),
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
        # self.rotOnTarg = 1 * ArcSecPerDeg # within 1 arcsec rot move is considered done
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
            "tccPos": self.tccPos(),
            "objNetPos": self.objNetPos(),
            "utc_tai": self.utc_tai(),
            "objSys": self.objSys(),
            "secTrussTemp": self.secTrussTemp(),
            "tccHA": self.tccHA(),
            "tccTemps": self.tccTemps(),
            # "secFocus": self.secFocus(),
            # "currArcOff": self.currArcOff(), 0.000000,0.000000,4947564013.2595177,0.000000,0.000000,4947564013.2595177
            # "objArcOff": self.objArcOff(), bjArcOff=0.000000,0.000000,4947564013.2595177,0.000000,0.000000,4947564013.2595177
            # TCCPos=68.361673,63.141087,nan; AxePos=68.393020,63.138022
        }

    def tccHA(self):
        ha = self.statusFieldDict["ha"].value
        if ha is None:
            haStr = "NaN"
        else:
            haStr = "%.6f"%ha
        return "tccHA=%s"%haStr

    def tccPos(self):
        # raPos = self.statusFieldDict["inpra"].value
        # decPos = self.statusFieldDict["inpdc"].value
        # rotPos = self.rotPos
        # raStr = "%.4f"%raPos if raPos else "NaN"
        # decStr = "%.4f"%decPos if decPos else "NaN"
        # rotStr = "%.4f"%rotPos if decPos else "NaN"
        # return "TCCPos=%s"%(", ".join([raStr, decStr, rotStr]))

        elPos = self.statusFieldDict["telel"].value
        azPos = self.statusFieldDict["telaz"].value
        rotPos = self.rotPos
        elStr = "%.4f"%elPos if elPos else "NaN"
        azStr = "%.4f"%azPos if azPos else "NaN"
        rotStr = "%.4f"%rotPos if rotPos else "NaN"
        return "TCCPos=%s"%(", ".join([azStr, elStr, rotStr]))

    def tccTemps(self):
        tempsDict = self.statusFieldDict["temps"].value
        if tempsDict is None:
            tempsStr = ",".join(["NaN"]*len(tempKeys))
        else:
            tempsStr = ",".join(["%.2f"%tempsDict[temp] for temp in tempKeys])
        return "TCCTemps=%s"%tempsStr

    def secTrussTemp(self):
        trussTempStr = "%.2f"%self.trussTemp if self.trussTemp is not None else "NaN"
        return "SecTrussTemp=%s"%(trussTempStr)

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
        if self.statusFieldDict["mpos"].value is None:
            raPos, decPos = None, None
        else:
            raPos = self.statusFieldDict["mpos"].value[0]
            decPos = self.statusFieldDict["mpos"].value[1]
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
        raPos = self.statusFieldDict["ra"].value
        decPos = self.statusFieldDict["dec"].value
        rotPos = self.rotPos
        raStr = "%.4f"%raPos if raPos else "NaN"
        decStr = "%.4f"%decPos if decPos else "NaN"
        rotStr = "%.4f"%rotPos if decPos else "NaN"
        axePosStr = "AxePos=%s"%(", ".join([raStr, decStr, rotStr]))
        return axePosStr

    def utc_tai(self):
        return "UTC_TAI=%0.0f"%(-36.0,) # this value is usually gotten from coordConv/earthpred, I think, which we don't have implemented...

    # def secFocus(self):
    #     secFocus = self.statusFieldDict["focus"].value
    #     secFocus = "NaN" if secFocus is None else "%.4f"%secFocus
    #     return "SecFocus=%s"%secFocus

    @property
    def rotPos(self):
        return self.statusFieldDict["rawpos"].value

    @property
    def arcOff(self):
        if None in [self.statusFieldDict["inpra"].value, self.statusFieldDict["mpos"].value[0]]:
            raOff = 0
        else:
            raOff = self.statusFieldDict["inpra"].value - self.statusFieldDict["mpos"].value[0]
        if None in [self.statusFieldDict["inpdc"].value, self.statusFieldDict["mpos"].value[1]]:
            decOff = 0
        else:
            decOff = self.statusFieldDict["inpdc"].value - self.statusFieldDict["mpos"].value[1]
        # return "%.6f, 0.0, 0.0, %.6f, 0.0, 0.0"%(raOff, decOff)
        return "%.6f, %.6f"%(raOff, decOff)

    # @property
    # def rotOnTarget(self):
    #     return abs(self.targRot - self.rotPos)<self.rotOnTarg

    def setRotOffsetTarg(self, rotOffset):
        self.targRot = self.rotPos + rotOffset

    def axesSlewing(self):
        if self.previousDec == ForceSlew:
            decSlewing = True
        else:
            decSlewing = abs(self.previousDec - self.statusFieldDict["mpos"].value[1]) > self.decOnTarg if self.previousDec is not None else False
        if self.previousRA == ForceSlew:
            raSlewing = True
        else:
            raSlewing = abs(self.previousRA - self.statusFieldDict["mpos"].value[0]) > self.raOnTarg if self.previousRA is not None else False
        return [raSlewing, decSlewing]

    @property
    def trussTemp(self):
        return self.statusFieldDict["ttruss"].value

    @property
    def isClamped(self):
        return self.statusFieldDict["mrp"].value

    @property
    def rotMoving(self):
        rotMoving = self.statusFieldDict["axisstatus"].value["rot"].isMoving
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
        self.waitRotTimer = Timer()

        # self.waitFocusCmd = UserCmd()
        # self.waitFocusCmd.setState(self.waitFocusCmd.Done)

        self.waitOffsetCmd = UserCmd()
        self.waitOffsetCmd.setState(self.waitOffsetCmd.Done)
        self.waitOffsetTimer = Timer()
        self.rotDelay = False

        self.devCmdQueue = CommandQueue({}) # all commands of equal priority

        self.lastGuideRotApplied = None

        self.doGuideRot = True

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
            userCmd.setState(userCmd.Failed, "Not Connected to TCS: try reconnecting (is the APOGEE TCS running!?)")
            return userCmd
        self._statusTimer.cancel() # incase a status is pending
        userCmd = expandUserCmd(userCmd)
        userCmd.addCallback(self._statusCallback)
        # record the present RA, DEC (for determining when offsets are done)
        # self.status.previousRA = self.status.statusFieldDict["ra"].value
        # self.status.previousDec = self.status.statusFieldDict["dec"].value
        if self.status.statusFieldDict["mpos"].value is None:
            self.status.previousRA, self.status.previousDec = None, None
        else:
            self.status.previousRA = self.status.statusFieldDict["mpos"].value[0]
            self.status.previousDec = self.status.statusFieldDict["mpos"].value[1]
        # gather list of status elements to get
        devCmdList = [DevCmd(cmdStr=cmdVerb) for cmdVerb in self.status.statusFieldDict.keys()]
        LinkCommands(userCmd, devCmdList)
        for devCmd in devCmdList:
            self.queueDevCmd(devCmd)
        if not self.status.isClamped or self.rotDelay:
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

            if self.waitRotCmd.isActive and not self.rotDelay and self.status.isClamped: #not self.status.rotMoving: #and self.status.rotOnTarget :
                print("set rot command done", self.rotDelay, self.status.isClamped, self.status.rotMoving)
                self.waitRotCmd.setState(self.waitRotCmd.Done)


    def target(self, ra, dec, doHA, doScreen, userCmd=None):
        """Set coordinates for a slew.

        @param[in] ra: right ascension decimal degrees
        @param[in] dec: declination decimal degrees
        @param[in] doHA: if True, use degrees in hour angle rather than ra.
        @param[in] userCmd: a twistedActor BaseCommand.
        """
        log.info("%s.slew(userCmd=%s, ra=%.2f, dec=%.2f)" % (self, userCmd, ra, dec))
        userCmd = expandUserCmd(userCmd)
        screenPos = None
        if not self.conn.isConnected:
            userCmd.setState(userCmd.Failed, "Not Connected to TCS")
            return userCmd
        if doScreen:
            # check telescope altitude, if too low,
            # increase declination until the screen can reach!
            if doHA:
                ha = ra
            else:
                ha = self.status.statusFieldDict["st"].value - ra
            (az, alt), atPole = azAltFromHADec([ha,dec], LCO_LATITUDE)
            if alt < WS_ALT_LIMIT:
                # modify declination
                # find declination that will be above the
                # windscreen limit for this az
                alt = WS_ALT_LIMIT+0.1
                (ha, dec), atPole = haDecFromAzAlt([az, alt], LCO_LATITUDE)
                # move to this ha,dec instead
                doHA = True
                self.writeToUsers("w", 'text="target postion below windscreen, modified target coords HA=%.4f, DEC=%.4f"%(ha, dec)"', userCmd)
                ra = ha
            # determine the screen position based on the model fit
            screenPos = WS_COEFFS[0]*alt + WS_COEFFS[1]
            self.writeToUsers("i", 'text="setting windscreen target to %.2f"'%screenPos)
        if doHA:
            enterRa = "HAD %.8f"%ra
        else:
            enterRa = "RAD %.8f"%ra
        enterDec = "DECD %.8f"%dec
        enterEpoch = "MP %.2f"%2000 # LCO: HACK should coords always be 2000?
        devCmdList = [DevCmd(cmdStr=cmdStr) for cmdStr in [enterRa, enterDec, enterEpoch]]#, cmdSlew]]
        if screenPos is not None:
            # add the screen position to the device command list
            devCmdList += [DevCmd(cmdStr="INPS %.2f"%screenPos)]
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
        waitOffsetCmd = UserCmd()
        self.waitOffsetCmd = waitOffsetCmd
        enterRa = "OFRA %.8f"%(ra*ArcSecPerDeg)
        enterDec = "OFDC %.8f"%(dec*ArcSecPerDeg) #lcohack
        devCmdList = [DevCmd(cmdStr=cmdStr) for cmdStr in [enterRa, enterDec, CMDOFF]]
        # set userCmd done only when each device command finishes
        # AND the pending slew is also done.
        # set an offset done after 6 seconds no matter what
        def setWaitOffsetCmdDone(aWaitingOffsetCmd):
            print("wait offset command state", aWaitingOffsetCmd.state)
            if not aWaitingOffsetCmd.isDone:
                print("Wait offset timed out!!!!")
                self.writeToUsers("w", "Text=OFFSET SET DONE ON TIMER.")
                aWaitingOffsetCmd.setState(aWaitingOffsetCmd.Done, "offset set done on a timer")
        self.waitOffsetTimer.start(8, setWaitOffsetCmdDone, waitOffsetCmd)
        # self.waitOffsetCmd.setTimeLimit(6)
        LinkCommands(userCmd, devCmdList + [self.waitOffsetCmd])
        for devCmd in devCmdList:
            self.queueDevCmd(devCmd)
        statusStr = self.status.getStatusStr()
        if statusStr:
            self.writeToUsers("i", statusStr, userCmd)
        return userCmd

    def rotOffset(self, rot, userCmd=None, force=False):
        """Offset telescope rotator.  USE APGCIR cmd
        which holds current

        @param[in] rot: in decimal degrees
        @param[in] userCmd a twistedActor BaseCommand
        """
        # LCOHACK: allow offsets only if over 5 arcseconds!

        # if True:
        #     #! lupton!
        #     userCmd = expandUserCmd(userCmd)
        #     self.writeToUsers("w", "Rotator offset %.6f bypassed"%rot)
        #     userCmd.setState(userCmd.Done)
        #     return userCmd
        userCmd = expandUserCmd(userCmd)
        if not self.conn.isConnected:
            userCmd.setState(userCmd.Failed, "Not Connected to TCS")
            return userCmd
        if not self.waitRotCmd.isDone:
            # rotator is unclamped, a move is in progress
            userCmd.setState(userCmd.Failed, "Rotator is unclamped (already moving?)")
            return userCmd
        # if abs(rot) < MinRotOffset and not force:
        if not self.doGuideRot:
            # set command done, rotator offset is miniscule
            self.writeToUsers("w", "Guide rot not enabled, not applying", userCmd)
            userCmd.setState(userCmd.Done)
            return userCmd
        if abs(rot) > MaxRotOffset:
            # set command failed, rotator offset is too big
            self.writeToUsers("w", "Rot offset greater than max threshold", userCmd)
            userCmd.setState(userCmd.Failed, "Rot offset %.4f > %.4f"%(rot, MaxRotOffset))
            return userCmd
        ### print time since last rot applied from guider command
        if not force:
            if self.lastGuideRotApplied is None:
                self.lastGuideRotApplied = time.time()
            else:
                tnow = time.time()
                infoStr = "time since last guide rot update: %.2f"%(tnow-self.lastGuideRotApplied)
                print(infoStr)
                log.info(infoStr)
                self.lastGuideRotApplied = tnow

        # apgcir requires absolute position, calculate it
        # first get status
        newPos = self.status.rotPos - rot
        # rotStart = time.time()
        # def printRotSlewTime(aCmd):
        #     if aCmd.isDone:
        #         rotTime = time.time() - rotStart
        #         print("rot: off, time, speed: %.5f %.5f %5f"%(newPos, rotTime, newPos/rotTime))
        waitRotCmd = UserCmd()
        self.waitRotCmd = waitRotCmd
        # calculate time limit for rot move:
        rotTimeLimBuffer = 2 # check for clamp after 4 seconds
        self.rotDelay = True
        print("setting rot delay true")
        def setRotBufferOff():
            print("setting rot delay false")
            print("rot buffer Off (clamped?)", self.status.isClamped)
            self.rotDelay = False
        self.waitRotTimer.start(rotTimeLimBuffer, setRotBufferOff)
        self.waitOffsetCmd.setTimeLimit(rotTimeLimBuffer + 20)
        self.status.setRotOffsetTarg(rot)
        enterAPGCIR = DevCmd(cmdStr="APGCIR %.8f"%(newPos))
        LinkCommands(userCmd, [enterAPGCIR, self.waitRotCmd])
        # begin the dominos game
        self.queueDevCmd(enterAPGCIR)
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
                elif "CIR" in devCmdStr:
                    self.waitRotCmd.setState(self.waitRotCmd.Running)
                self.conn.writeLine(devCmdStr)
            else:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Not connected to TCS")
        except Exception as e:
            self.currExeDevCmd.setState(self.currExeDevCmd.Failed, textMsg=strFromException(e))
