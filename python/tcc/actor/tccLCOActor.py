from __future__ import division, absolute_import
"""The TCC (telescope control code) interface shim for the Las Campanas Observatory du Pont telescope
"""
import sys
import traceback

from RO.StringUtil import strFromException
from RO.Comm.TwistedTimer import Timer

import numpy
from astropy.time import Time

from twistedActor import CommandError, BaseActor, DeviceCollection, expandCommand

from .tccLCOCmdParser import TCCLCOCmdParser
from ..version import __version__

from ..cmd.collimate import CollimationModel

# tcsHost = "localhost"
# tcsPort = 0

__all__ = ["TCCLCOActor"]

"""
From Paul's email regarding scaling solution:

focal plane focal plane      focal      ratio           Scale
location        location        length                          Change
BFDr        BFDp                                                1 parts in
(inches)        (mm)        (mm)
10           993            18868.78
10.04        994                 18870.37       1.0000843    8.43e-5
9.96                 992            18867.18        0.9999152       -8.48e-5

So lets say that a scale change +8.45e05 as reported by the guider requires a plate motion of up by 1mm (towards the primary)
                 and  a scale change -8.45e05 as reported by the guider requires a plate motion of down by 1mm (away from the primary)
"""

# timeNow = Time.now()
# TAI = timeNow.tai.mjd*60*60*24
# UT1 = timeNow.ut1.mjd*60*60*24
# UTC = timeNow.mjd*60*60*24

# output TAI on a timer?

class TCCStatus(object):
    def __init__(self):
        self.tccKWs = [
            "SecFocus",
            "ffSetCurrent", # FFS KWS
            "ffSetVoltage",
            "ffCurrent",
            "ffVoltage",
            "ffPower",
            "secOrient", # M2 KWS
            "secDesOrient",
            "secState",
            "SecFocus",
            "Galil",
            "instrumentNum",
            "CartLocked",
            "CartLoaded",
            "ApogeeGang",
            "ThreadringState",
            "axisCmdState",
            "axePos",
            "tccPos",
            "objNetPos",
            "objSys",
            "secTrussTemp",
            "tccHA",
            "tccTemps",
            "airmass",
            "pleaseSlew",
            "TAI",
            "UTC_TAI",
            "axisErr",
            "screenPos"
        ]
        self.kwDict = {}
        for kw in self.tccKWs:
            self.kwDict[kw.lower()] = None

    def outputTimeKWs(self, userCmd):
        timeNow = Time.now()
        TAI = timeNow.tai.mjd*60*60*24
        # UT1 = timeNow.ut1.mjd*60*60*24
        UTC = timeNow.mjd*60*60*24
        timeDict = {
            "TAI": TAI,
            "UTC_TAI": UTC-TAI,
        }
        self.updateKWs(timeDict, userCmd)

    def updateKW(self, kw, valueStr, userCmd, level=None, forceOutput=False):
        #if no userCmd is associated
        # output the keyword as debug level
        # but only if it has changed since last
        # output, else don't output.
        # if a userCmd is assocated,
        # output no matter what with info
        #level
        assert level in [None, "i", "w", "d"]
        level = level
        didChange = valueStr != self.kwDict[kw.lower()]
        self.kwDict[kw.lower()] = valueStr
        output = False
        if userCmd is not None and userCmd.eldestParentCmd.userCommanded:
            output = True
            level = "i" if level is None else level
        elif didChange:
            level = "d" if level is None else level
            output = True
        elif level == "w":
            output = True
        if forceOutput:
            output = True
            level = "d" if level is None else level

        if output:
            userCmd.writeToUsers(level, "%s=%s"%(kw, self.kwDict[kw.lower()]))


    def updateKWs(self, keyValDict, userCmd, forceOutput=False):
        for key, val in keyValDict.iteritems():
            self.updateKW(key, val, userCmd, forceOutput=forceOutput)


class TCCLCOActor(BaseActor):
    """!TCC actor for the LCO telescope
    """

    def __init__(self,
        userPort,
        tcsDev,
        m2Dev,
        name = "tcc",
    ):
        """Construct a TCCActor

        @param[in] userPort  port on which to listen for users
        @param[in] tcsDev a TCSDevice instance
        @param[in] m2Dev a M2Device instance
        @param[in] name  actor name; used for logging
        """
        devices = {
            "tcsDev": tcsDev,
            "secDev": m2Dev,
        }

        self.status = TCCStatus()
        for devName, device in devices.iteritems():
            setattr(self, devName, device)
            device.tccStatus = self.status
            device.connect()

        self.dev = DeviceCollection(devices.values())

        self.cmdParser = TCCLCOCmdParser()
        self.collimationModel = CollimationModel()
        self.collimateTimer = Timer(0, self.updateCollimation)
        self.collimateStatusTimer = Timer()
        self.collimateStatusTimer.start(5, self.collimateStatus) #give things a chance to boot up

        BaseActor.__init__(self, userPort=userPort, name=name, version=__version__)

    def parseAndDispatchCmd(self, cmd):
        """Dispatch the user command

        @param[in] cmd  user command (a twistedActor.UserCmd)
        """
        if not cmd.cmdBody:
            # echo to show alive
            self.writeToOneUser(":", "", cmd=cmd)
            return
        try:
            cmd.parsedCmd = self.cmdParser.parseLine(cmd.cmdBody)
        except Exception as e:
            cmd.setState(cmd.Failed, "Could not parse %r: %s" % (cmd.cmdBody, strFromException(e)))
            return

        #cmd.parsedCmd.printData()
        if cmd.parsedCmd.callFunc:
            cmd.setState(cmd.Running)
            try:
                cmd.parsedCmd.callFunc(self, cmd)
            except CommandError as e:
                cmd.setState("failed", textMsg=strFromException(e))
                return
            except Exception as e:
                sys.stderr.write("command %r failed\n" % (cmd.cmdStr,))
                sys.stderr.write("function %s raised %s\n" % (cmd.parsedCmd.callFunc, strFromException(e)))
                traceback.print_exc(file=sys.stderr)
                textMsg = strFromException(e)
                hubMsg = "Exception=%s" % (e.__class__.__name__,)
                cmd.setState("failed", textMsg=textMsg, hubMsg=hubMsg)
        else:
            raise RuntimeError("Command %r not yet implemented" % (cmd.parsedCmd.cmdVerb,))

    def updateCollimation(self, cmd=None, force=False):
        """

        LCO HACK!!! clean this stuff up!!!!
        """
        cmd = expandCommand(cmd)
        if not self.collimationModel.doCollimate and not force:
            cmd.setState(cmd.Failed, "collimation is disabled")
            return
        if "Halted" in self.tcsDev.status.statusFieldDict["state"].value[:2]:
            # either RA or Dec axis is halted
            cmd.setState(cmd.Canceled("RA or Dec axis halted, not applying collimation."))
            return
        self.collimateTimer.cancel() # incase one is pending
        # query for current telescope coords
        statusCmd = self.tcsDev.getStatus()
        # when status returns determine current coords
        def moveMirrorCallback(statusCmd):
            if statusCmd.didFail:
                cmd.setState(cmd.Failed, "status command failed")
            elif statusCmd.isDone:
                # ha = self.tcsDev.status.statusFieldDict["ha"].value
                # dec = self.tcsDev.status.statusFieldDict["dec"].value
                # if an axis is slewing collimate to the target
                if "Slewing" in self.tcsDev.status.statusFieldDict["state"].value[:2]:
                    # ra or dec is slewing
                    # get target coords
                    # st and ra in degrees
                    st = self.tcsDev.status.statusFieldDict["st"].value
                    ra = self.tcsDev.status.statusFieldDict["inpra"].value
                    ha = st - ra
                    dec = self.tcsDev.status.statusFieldDict["inpdc"].value
                    self.writeToUsers("i", "collimate for target ha=%.2f, dec=%.2f"%(ha, dec), cmd)
                else:
                    # get current coords
                    ha, dec = self.tcsDev.status.statusFieldDict["pos"].value
                    self.writeToUsers("i", "collimate for current ha=%.2f, dec=%.2f"%(ha, dec), cmd)
                # self.writeToUsers("i", "pos collimate for ha=%.2f, dec=%.2f"%(pos[0], pos[1]))

                newOrient = self.collimationModel.getOrientation(ha, dec)
                orient = self.secDev.status.orientation[:]
                # check if mirror move is wanted based on tolerances
                dFocus = None if newOrient[0] is None else newOrient[0]-orient[0]
                dtiltX = newOrient[1]-orient[1]
                dtiltY = newOrient[2]-orient[2]
                dtransX = newOrient[3]-orient[3]
                dtransY = newOrient[4]-orient[4]
                doFlex = numpy.max(numpy.abs([dtiltX, dtiltY])) > self.collimationModel.minTilt or numpy.max(numpy.abs([dtransX, dtransY])) > self.collimationModel.minTrans

                if force:
                    self.writeToUsers("i", "collimation update forced", cmd)
                if not doFlex and not force:
                    self.writeToUsers("i", "collimation flex update too small: dTiltX=%.2f, dTiltY=%.2f, dTransX=%.2f, dTransY=%.2f"%(dtiltX, dtiltY, dtransX, dtransY))
                    cmd.setState(cmd.Done)
                else:
                    # update flex values
                    orient[1:] = newOrient[1:] # keep existing focus
                    self.writeToUsers("i", "collimation update: Focus=%.2f, TiltX=%.2f, TiltY=%.2f, TransX=%.2f, TransY=%.2f"%tuple(orient), cmd=cmd)
                    self.secDev.move(orient, userCmd=cmd)


        statusCmd.addCallback(moveMirrorCallback)

        # remove timer for now
        if self.collimationModel.doCollimate:
            self.collimateTimer.start(self.collimationModel.collimateInterval, self.updateCollimation)
        else:
            self.collimateTimer.cancel()

    def collimateStatus(self):
        if not self.collimateTimer.isActive and (self.tcsDev.isTracking or self.tcsDev.isSlewing):
            self.writeToUsers("w", "Text=Collimation is NOT active!!!")
        self.collimateStatusTimer.start(5, self.collimateStatus)
