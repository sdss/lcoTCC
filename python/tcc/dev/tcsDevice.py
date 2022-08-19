from __future__ import division, absolute_import

import collections
import time
import numpy

from RO.Comm.TwistedTimer import Timer
from RO.Astro.Sph.AzAltFromHADec import azAltFromHADec
from RO.Astro.Sph.HADecFromAzAlt import haDecFromAzAlt
from RO.StringUtil import strFromException, degFromDMSStr

from twistedActor import TCPDevice, DevCmd, CommandQueue, log, expandCommand

from tcc.utils.ffs import get_ffs_altitude, telescope_alt_limit

from twisted.internet import reactor
#TODO: Combine offset wait command and rotation offset wait commands.
# make queueDev command return a dev command rather than requiring one.
# creat a command list where subsequent commands are not sent if the previous is not successful
# i think this is handled easily by canceling all commands on the queue if the return value is not 0
# maybe we don't want this behavior in the case of the rotator, because we always want it
# to clamp!!!

SEC_TIMEOUT = 2.0
MAX_OFFSET_WAIT = 60.0
LCO_LATITUDE = -29.0146

def tai():
    return time.time() - 36.

__all__ = ["TCSDevice"]
# ForceSlew = "ForceSlew"

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
# IROFFSET = 405.447
IROFFSET = 408.653
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

## slew on target thresholds from updatethread.cpp (TCS)
# MD_TRACKING_STABILITY_THRESHOLD = 0.5 # Tracking is declared stable when error is below this threshold in arc-seconds
MD_FINE_CORRECTION_TARGET = 0.1 #Target error before completing move in arc-seconds
# RADEC_ERR_THRES = 0.04 # arcseconds, when stable here, offset is done

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
PollTimeSlew = 0.5 #seconds, LCO says status is updated no more frequently that 5 times a second
PollTimeTrack = 2
PollTimeIdle = 5
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

def castScreenPos(lcoReply):
    try:
        items = lcoReply.split()
        screenPos = items[6].strip()
        return float(screenPos)
    except:
        print("error parsing lco screen pos: ", screenPos)
        return 0


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
                StatusField("rerr", float),
                StatusField("derr", float),
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
                StatusField("airmass", float),
                StatusField("lplc", castScreenPos)
            ]

class Status(object):
    def __init__(self, tcsDevice):
        """Container for holding current status of the TCS

        @param[in] tcsDevice, for access to various states of the tcs
        """
        self.tcsDevice = tcsDevice
        # used to determine when offset is done, or AxisCmdState should be set to tracking/slewing.


        # for new axis state handling
        self.errBufferLen = 2
        self.rerrQueue = collections.deque(maxlen=self.errBufferLen)
        self.derrQueue = collections.deque(maxlen=self.errBufferLen)
        self.wsPosQueue = collections.deque(maxlen=self.errBufferLen)


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

    def getTCCKWDict(self):
        return {
            "axisCmdState": self.axisCmdState(),
            "axePos": self.axePos(),
            "tccPos": self.tccPos(),
            "objNetPos": self.objNetPos(),
            # "utc_tai": self.utc_tai(),
            "objSys": self.objSys(),
            "secTrussTemp": self.secTrussTemp(),
            "tccHA": self.tccHA(),
            "tccTemps": self.tccTemps(),
            "airmass": self.airmass(),
            "axisErr": self.axisErr(),
        }

    def axisErr(self):
        rerr = self.statusFieldDict["rerr"].value
        derr = self.statusFieldDict["derr"].value
        errStrs = []
        for err in [rerr, derr]:
            if err is None:
                errStrs.append("NaN")
            else:
                errStrs.append("%.4f"%err)
        return "%s"%(",".join(errStrs))

    def airmass(self):
        airmass = self.statusFieldDict["airmass"].value
        if airmass is None:
            airmassStr = "NaN"
        else:
            airmassStr = "%.2f"%airmass
        return "%s"%airmassStr

    def tccHA(self):
        ha = self.statusFieldDict["ha"].value
        if ha is None:
            haStr = "NaN"
        else:
            haStr = "%.6f"%ha
        return "%s"%haStr

    def azAltStr(self):
        elPos = self.statusFieldDict["telel"].value
        azPos = self.statusFieldDict["telaz"].value
        rotPos = self.rotPos
        elStr = "%.4f"%elPos if elPos else "NaN"
        azStr = "%.4f"%azPos if azPos else "NaN"
        rotStr = "%.8f"%rotPos if rotPos else "NaN"
        return ", ".join([azStr, elStr, rotStr])

    def tccPos(self):
        return "%s"%(self.azAltStr())

    def tccTemps(self):
        tempsDict = self.statusFieldDict["temps"].value
        if tempsDict is None:
            tempsStr = ",".join(["NaN"]*len(tempKeys))
        else:
            tempsStr = ",".join(["%.2f"%tempsDict[temp] for temp in tempKeys])
        return "%s"%tempsStr

    def secTrussTemp(self):
        trussTempStr = "%.2f"%self.trussTemp if self.trussTemp is not None else "NaN"
        return "%s"%(trussTempStr)

    # def axisCmdStateList(self):
    #     axisCmdState = self.statusFieldDict["state"].value or "?"
    #     # check if we are really slewing instead of tracking (offsets don't trigger slew state)
    #     # so check manually
    #     ra, dec = [axisCmdState]*2
    #     rot = Halted if self.isClamped else Slewing
    #     raSlewing, decSlewing = self.axesSlewing()
    #     # force ra or dec slewing if true in axesSlewing
    #     if raSlewing:
    #         ra = Slewing
    #     if decSlewing:
    #         dec = Slewing
    #     return [ra, dec, rot]

    def axisCmdState(self):
        """Format the AxisCmdState keyword
        """
        return "%s"%(", ".join(self.axisStatus))


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
        return "%s"%(",".join([raStr, v, taiSecs, decStr, v, taiSecs]))

    def objSys(self):
        """@ LCOHACK: i think coords are always fk5?
        can only query tcs for epoch
        """
        epoch = self.statusFieldDict["epoch"].value
        epochStr = "%.2f"%epoch if epoch is not None else "NaN"
        return "FK5, %s"%epochStr

    def axePos(self):
        """Format the AxePos keyword (alt az rot)
        """
        return "%s"%(self.azAltStr())

    def utc_tai(self):
        return "UTC_TAI=%0.0f"%(-36.0,) # this value is usually gotten from coordConv/earthpred, I think, which we don't have implemented...

    # def secFocus(self):
    #     secFocus = self.statusFieldDict["focus"].value
    #     secFocus = "NaN" if secFocus is None else "%.4f"%secFocus
    #     return "SecFocus=%s"%secFocus

    @property
    def wsMoving(self):
        """ return true if ws is moving"""
        if len(self.wsPosQueue) < self.errBufferLen and numpy.all(self.wsPosQueue):
            print("ws moving")
            return True
        else:
            print("ws stationary")
            return False

    def onTarget(self, errorBuffer):
        """Look at an error buffer and decide if the telescope is on target (for offests)
        """
        if len(errorBuffer) < self.errBufferLen:
            # requre a full buffer before deciding if we're on target or not
            return False
        elif True in (numpy.abs(numpy.asarray(errorBuffer)) > MD_FINE_CORRECTION_TARGET):
            # buffer is full but not all are below threshold.
            return False
        else:
            # the buffer is full and errors are under the threshold
            return True

    @property
    def raOnTarget(self):
        """Return True if the rerr buffer is full and all values are under the threshold
        """
        return self.onTarget(self.rerrQueue)

    @property
    def decOnTarget(self):
        """Return True if the derr buffer is full and all values are under the threshold
        """
        return self.onTarget(self.derrQueue)

    @property
    def axesOnTarget(self):
        """Return true if ra and dec are both on target.
        """
        return self.raOnTarget and self.decOnTarget

    @property
    def rotPos(self):
        return self.statusFieldDict["rawpos"].value


    # @property
    # def rotOnTarget(self):
    #     return abs(self.targRot - self.rotPos)<self.rotOnTarg

    def setRotOffsetTarg(self, rotOffset):
        self.targRot = self.rotPos + rotOffset

    @property
    def rotAxisStatus(self):
        """Return Halted, Slewing or Tracking
        """
        # if unclamped return slewing
        if self.tcsDevice.waitRotCmd.isActive:
            return Slewing
        if self.raDecAxisState in [Slewing, Tracking]:
            # if ra, or dec are tracking or slewing, report tracking
            return Tracking
        else:
            # telescope is idle, report this axis as halted
            return Halted

    @property
    def raDecAxisState(self):
        if self.tcsDevice.waitOffsetCmd.isActive:
            return Slewing
        if self.statusFieldDict["state"].value is None:
            return "?"
        else:
            return self.statusFieldDict["state"].value

    @property
    def axisStatus(self):
        """Return Halted, Slewing or Tracking for ra, dec, rot axes
        """
        return [self.raDecAxisState]*2 + [self.rotAxisStatus]

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

    # def currArcOff(self):
    #     return "currArcOff=%s"%self.arcOff

    # def objArcOff(self):
    #     return "objArcOff=%s"%self.arcOff

    def updateTCCStatus(self, userCmd=None):
        """Grab and format tcc keywords, only output those which have changed
        """
        if self.tcsDevice.tccStatus is not None:
            self.tcsDevice.tccStatus.updateKWs(self.getTCCKWDict(), userCmd)


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
        self.tccStatus = None # set by the tccLCOActort
        self._statusTimer = Timer()

        self.waitRotCmd = expandCommand()
        self.waitRotCmd.setState(self.waitRotCmd.Done)
        self.waitRotTimer = Timer()

        # self.waitFocusCmd = expandCommand()
        # self.waitFocusCmd.setState(self.waitFocusCmd.Done)

        self.waitOffsetCmd = expandCommand()
        self.waitOffsetCmd.setState(self.waitOffsetCmd.Done)

        self.waitSlewCmd = expandCommand()
        self.waitSlewCmd.setState(self.waitSlewCmd.Done)
        # self.waitOffsetTimer = Timer()
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
        self.status = Status(self)

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

    @property
    def pollTime(self):
        if self.isSlewing:
            # slewing, get status kinda frequently
            pollTime = PollTimeSlew
        elif self.isTracking:
            # tracking, get status less frequently
            pollTime = PollTimeTrack
        else:
            # idle, get status infrequently (as things shouldn't be changing fast)
            pollTime = PollTimeIdle
        return pollTime

    def init(self, userCmd=None, timeLim=None, getStatus=True):
        """Called automatically on startup after the connection is established.
        Only thing to do is query for status or connect if not connected
        """
        log.info("%s.init(userCmd=%s, timeLim=%s, getStatus=%s)" % (self, userCmd, timeLim, getStatus))
        # print("%s.init(userCmd=%s, timeLim=%s, getStatus=%s)" % (self, userCmd, timeLim, getStatus))
        userCmd = expandCommand(userCmd)
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
        userCmd = expandCommand(userCmd)
        if not self.conn.isConnected:
            userCmd.setState(userCmd.Failed, "Not Connected to TCS: try reconnecting (is the APOGEE TCS running!?)")
            return userCmd
        self._statusTimer.cancel() # incase a status is pending
        statusCmd = expandCommand()
        userCmd.linkCommands([statusCmd])
        statusCmd.addCallback(self._statusCallback)

        # gather list of status elements to get
        devCmdList = [DevCmd(cmdStr=cmdVerb) for cmdVerb in self.status.statusFieldDict.keys()]
        statusCmd.linkCommands(devCmdList)
        for devCmd in devCmdList:
            self.queueDevCmd(devCmd)
        return userCmd

    def _statusCallback(self, cmd):
        """! When status command is complete, send info to users, and check if any
        wait commands need to be set done
        """
        if cmd.isDone and not cmd.didFail:
            # do we want status output so frequently? probabaly not.
            # perhaps only write status if it has changed...
            # append ra and dec errors to the queues
            self.status.rerrQueue.append(self.status.statusFieldDict["rerr"].value)
            self.status.derrQueue.append(self.status.statusFieldDict["derr"].value)
            self.status.wsPosQueue.append(self.status.statusFieldDict["lplc"].value)

            if self.waitOffsetCmd.isActive and self.status.axesOnTarget:
                self.waitOffsetCmd.setState(self.waitOffsetCmd.Done)

            if not self.waitSlewCmd.isDone and self.status.statusFieldDict["state"].value==Slewing:
                self.waitSlewCmd.setState(self.waitSlewCmd.Running)

            if (self.waitSlewCmd.isActive and
                    self.status.statusFieldDict["state"].value in [Tracking, Halted] and
                    not self.status.wsMoving):
                self.waitSlewCmd.setState(self.waitSlewCmd.Done)

            if self.waitRotCmd.isActive and not self.rotDelay and self.status.isClamped: #not self.status.rotMoving: #and self.status.rotOnTarget :
                # print("set rot command done", self.rotDelay, self.status.isClamped, self.status.rotMoving)
                self.waitRotCmd.setState(self.waitRotCmd.Done)

        self.status.updateTCCStatus(cmd)
        self._statusTimer.start(self.pollTime, self.getStatus)

    def abort_slews(self, userCmd=None):
        """Aborts any slew running."""

        userCmd = expandCommand(userCmd)

        if not self.waitSlewCmd.isDone:
            self.waitSlewCmd.setState(self.waitSlewCmd.Done, 'Aborted slew.')
        else:
            userCmd.writeToUsers('w', 'there are not slews to abort or all slews are done.')

        # self.status.updateTCCStatus(userCmd)
        userCmd.setState(userCmd.Done, 'Done aborting slews.')

        return

    def target(self, ra, dec, posAngle, doHA, doScreen, userCmd=None):
        """Set coordinates for a slew.

        @param[in] ra: right ascension decimal degrees
        @param[in] dec: declination decimal degrees
        @param[in] posAngle: desired position angle for observation in degrees
        @param[in] doHA: if True, use degrees in hour angle rather than ra.
        @param[in] doBlock: if True, do not set the userCmd done until the telescope is in place.
        @param[in] userCmd: a twistedActor BaseCommand.
        """

        log.info("%s.slew(userCmd=%s, ra=%.2f, dec=%.2f)" % (self, userCmd, ra, dec))
        userCmd = expandCommand(userCmd)
        ffs_altitude = None
        ipa_position = None
        if posAngle is not None:
            ipa_position = (90.064 - posAngle)%360

        if not self.conn.isConnected:
            userCmd.setState(userCmd.Failed, "Not Connected to TCS")
            return userCmd

        if doScreen:

            # If we command to move the flat field screen (FFS),  calculates at which altitude
            # we should move it to be in front of the telescope. If the position to which we
            # have commanded the telescope to go is too low, slews the telescope to that minimum
            # positoin.

            if doHA:
                ha = ra
            else:
                ha = self.status.statusFieldDict['st'].value - ra

            (az, alt), atPole = azAltFromHADec([ha, dec], LCO_LATITUDE)

            # Uses a FFS pointing model to determine the altitude of the FFS for this
            # telescope altitude
            ffs_altitude, is_ffs_at_minimum = get_ffs_altitude(alt)

            if is_ffs_at_minimum:

                # If the telescope is below telescope_alt_limit, the FFS cannot go any lower.

                ffs_altitude += 0.1
                alt = telescope_alt_limit + 0.1

                (ha, dec), atPole = haDecFromAzAlt([az, alt], LCO_LATITUDE)

                doHA = True
                ra = ha

                userCmd.writeToUsers(
                    'w', 'text="target postion below flat field screen, '
                         'modified target coords HA=%.4f, DEC=%.4f"' % (ha, dec))

            userCmd.writeToUsers(
                'i', 'text="setting FFS target to altitude %.2f deg"' % (ffs_altitude))

        if doHA:
            enterRa = 'HAD %.8f' % ra
        else:
            enterRa = 'RAD %.8f' % ra

        enterDec = 'DECD %.8f' % dec
        enterEpoch = 'MP %.2f' % 2000  # LCO: HACK should coords always be 2000?
        devCmdList = [DevCmd(cmdStr=cmdStr) for cmdStr in [enterRa, enterDec, enterEpoch]]
        #             , cmdSlew]]

        if ffs_altitude is not None:
            # add the screen position to the device command list
            devCmdList += [DevCmd(cmdStr='INPS %.2f' % ffs_altitude)]
        # set userCmd done only when each device command finishes
        # AND the pending slew is also done.
        # when the last dev cmd is done (the slew), set axis cmd statue to slewing

        if not self.waitSlewCmd.isDone:
            self.waitSlewCmd.setState(self.waitSlewCmd.Cancelled, "Superseded by new slew")
        self.waitSlewCmd = expandCommand()

        # if rotation is wanted move the rotator
        if ipa_position is not None:
            rotCmd = self.rotOffset(ipa_position, absolute=True)
        else:
            rotCmd = expandCommand()
            rotCmd.setState(rotCmd.Done)

        userCmd.linkCommands(devCmdList + [self.waitSlewCmd, rotCmd])

        for devCmd in devCmdList:
            self.queueDevCmd(devCmd)

        self.status.updateTCCStatus(userCmd)

        # output please slew announce in stui
        if self.tccStatus is not None:
            self.tccStatus.updateKW("pleaseSlew", "T", userCmd) # for outputting slew sound in stui
            self.tccStatus.updateKW("pleaseSlew", "F", userCmd)
        return userCmd

    def slewOffset(self, ra, dec, userCmd=None, waitForComplete=True):
        """Offset telescope in right ascension and declination.

        @param[in] ra: right ascension in decimal degrees
        @param[in] dec: declination in decimal degrees
        @param[in] userCmd a twistedActor BaseCommand
        @param[in] waitForComplete if True wait until telescope settles before finishing command.

        @todo, consolidate similar code with self.target?
        """
        log.info("%s.slewOffset(userCmd=%s, ra=%.6f, dec=%.6f)" % (self, userCmd, ra, dec))
        userCmd = expandCommand(userCmd)
        # zero the delta computation so the offset isn't marked done immediately

        if not self.conn.isConnected:
            userCmd.setState(userCmd.Failed, "Not Connected to TCS")
            return userCmd
        if not self.waitOffsetCmd.isDone:
            self.waitOffsetCmd.setState(self.waitOffsetCmd.Cancelled, "Superseded by new offset")
        # clear the target error buffers
        self.status.rerrQueue.clear()
        self.status.derrQueue.clear()
        waitOffsetCmd = expandCommand()
        self.waitOffsetCmd = waitOffsetCmd
        if not waitForComplete:
            self.waitOffsetCmd.setState(self.waitOffsetCmd.Done)
        enterRa = "OFRA %.8f"%(ra*ArcSecPerDeg)
        enterDec = "OFDC %.8f"%(dec*ArcSecPerDeg) #lcohack
        devCmdList = [DevCmd(cmdStr=cmdStr) for cmdStr in [enterRa, enterDec, CMDOFF]]


        def forceOffsetDone(waitOffsetCmd):
            if not waitOffsetCmd.isDone:
                userCmd.writeToUsers("w", "Forcing offset done after %.2f seconds"%MAX_OFFSET_WAIT)
                waitOffsetCmd.setState(waitOffsetCmd.Done, "Forcing offset done after %.2f seconds"%MAX_OFFSET_WAIT)

        reactor.callLater(MAX_OFFSET_WAIT, forceOffsetDone, waitOffsetCmd)

        userCmd.linkCommands(devCmdList + [self.waitOffsetCmd])
        for devCmd in devCmdList:
            self.queueDevCmd(devCmd)
        self.status.updateTCCStatus(userCmd)
        return userCmd

    def rotOffset(self, rot, userCmd=None, force=False, absolute=False):
        """Offset telescope rotator.  USE APGCIR cmd
        which holds current

        @param[in] rot: in decimal degrees
        @param[in] userCmd a twistedActor BaseCommand
        @param[in] force not really sure what this does
        @param[in] absolute if true command an absolute motion
        """

        userCmd = expandCommand(userCmd)
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
            userCmd.writeToUsers("w", "Guide rot not enabled, not applying")
            userCmd.setState(userCmd.Done)
            return userCmd
        # if abs(rot) > MaxRotOffset:
        #     # set command failed, rotator offset is too big
        #     userCmd.writeToUsers("w", "Rot offset greater than max threshold")
        #     userCmd.setState(userCmd.Failed, "Rot offset %.4f > %.4f"%(rot, MaxRotOffset))
        #     return userCmd
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
        if absolute:
            newPos = rot % 360
        else:
            newPos = self.status.rotPos - rot

        # check that rotator command is within the duPont limits.  if it isn't, fail the command
        if newPos < 90 or newPos > 270:
            userCmd.setState(userCmd.Failed, "Rotator command out of limits")
            return userCmd
        # rotStart = time.time()
        # def printRotSlewTime(aCmd):
        #     if aCmd.isDone:
        #         rotTime = time.time() - rotStart
        #         print("rot: off, time, speed: %.5f %.5f %5f"%(newPos, rotTime, newPos/rotTime))
        waitRotCmd = expandCommand()
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
        #### should this be waitRotCmd ?!!?
        # self.waitOffsetCmd.setTimeLimit(rotTimeLimBuffer + 20)
        self.waitRotCmd.setTimeLimit(rotTimeLimBuffer + 20)
        self.status.setRotOffsetTarg(rot)
        enterAPGCIR = DevCmd(cmdStr="APGCIR %.8f"%(newPos))
        userCmd.linkCommands([enterAPGCIR, self.waitRotCmd])
        # begin the dominos game
        self.queueDevCmd(enterAPGCIR)
        self.status.updateTCCStatus(userCmd)
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
        # log.info("%s read %r, currCmdStr: %s" % (self, replyStr, self.currDevCmdStr))
        replyStr = replyStr.strip()
        log.info("%s read %s" % (self,replyStr))
        if replyStr == "-1":
            # error
            errorStr = "handleReply failed for %s with -1"%self.currDevCmdStr
            if self.waitOffsetCmd.isActive:
                self.waitOffsetCmd.setState(self.waitOffsetCmd.Failed, errorStr)
            if self.waitSlewCmd.isActive:
                self.waitSlewCmd.setState(self.waitSlewCmd.Failed, errorStr)
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
            log.info("%s unexpected reply: %s" % (self,replyStr))
            #self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Unexpected reply %s for %s"%(replyStr, self.currDevCmdStr))


    def queueDevCmd(self, devCmd):
        """Add a device command to the device command queue

        @param[in] devCmd: a twistedActor DevCmd.
        """
        # log.info("%s.queueDevCmd(devCmd=%r, devCmdStr=%r, cmdQueue: %r"%(self, devCmd, devCmd.cmdStr, self.devCmdQueue))
        # append a cmdVerb for the command queue (other wise all get the same cmdVerb and cancel eachother)
        # could change the default behavior in CommandQueue?
        devCmd.cmdVerb = devCmd.cmdStr

        def forceMPDone(mpDevCmd):
            # mp command occasionally times out for some reason.  i don't want this to
            # be a failure in the target command so just set it done rather than timeout
            if not mpDevCmd.isDone:
                log.info("Forcing MP done")
                mpDevCmd.setState(mpDevCmd.Done,"forcing MP done")

        def queueFunc(devCmd):
            # all tcs commands return immediately so set a short timeout
            if "MP" in devCmd.cmdStr:
                reactor.callLater(2.0, forceMPDone, devCmd)
            else:
                devCmd.setTimeLimit(SEC_TIMEOUT)
            devCmd.setState(devCmd.Running)
            self.startDevCmd(devCmd.cmdStr)
        self.devCmdQueue.addCmd(devCmd, queueFunc)


    def startDevCmd(self, devCmdStr):
        """
        @param[in] devCmdStr a line of text to send to the device
        """
        devCmdStr = devCmdStr.upper() # lco uses all upper case
        # log.info("%s.startDevCmd(%r)" % (self, devCmdStr))
        try:
            if self.conn.isConnected:
                log.info("%s writing %r" % (self, devCmdStr))
                if CMDOFF.upper() == devCmdStr and not self.waitOffsetCmd.Running:
                    self.waitOffsetCmd.setState(self.waitOffsetCmd.Running)
                elif "CIR" in devCmdStr:
                    self.waitRotCmd.setState(self.waitRotCmd.Running)
                self.conn.writeLine(devCmdStr)
            else:
                self.currExeDevCmd.setState(self.currExeDevCmd.Failed, "Not connected to TCS")
        except Exception as e:
            self.currExeDevCmd.setState(self.currExeDevCmd.Failed, textMsg=strFromException(e))
