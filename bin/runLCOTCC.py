#!/usr/bin/env python
from __future__ import division, absolute_import
"""Run the TCC LCO actor
"""
import sys
import traceback
import os

from twisted.internet import reactor
# from twistedActor import startSystemLogging
from twistedActor import startFileLogging

from tcc.actor.tccLCOActor import TCCLCOActor
from tcc.dev import TCSDevice, ScaleDevice, M2Device, FakeScaleCtrl, FakeTCS, FakeM2Ctrl

# log to directory $HOME/tcclogs/
homeDir = os.path.expanduser("~")
logPath = os.path.join(homeDir, "tcclogs")
if not os.path.exists(logPath):
    os.makedirs(logPath)

startFileLogging(os.path.join(logPath, "tcc"))
# startSystemLogging(TCC25mActor.Facility)

UserPort = 25000
UDPPort = 25010

ScaleDeviceHost = "localhost"
ScaleDevicePort = 26000
TCSHost = "c100tcs"#.lco.cl
TCSDevicePort = 4242
M2DeviceHost = "vinchuca"
M2DevicePort = 52001

print "Start fake LCO controllers"
fakeScaleController  = FakeScaleCtrl("fakeScale",  ScaleDevicePort)
# fakeTCS = FakeTCS("mockTCSDevice", TCSDevicePort)

def startTCCLCO(*args):
    try:
        tccActor = TCCLCOActor(
            name = "tcc",
            userPort = UserPort,
            tcsDev = TCSDevice("tcsDev", TCSHost, TCSDevicePort),
            scaleDev = ScaleDevice("mockScale", ScaleDeviceHost, ScaleDevicePort),
            m2Dev = M2Device("m2Dev", M2DeviceHost, M2DevicePort),
            )
    except Exception:
        print >>sys.stderr, "Error lcoTCC"
        traceback.print_exc(file=sys.stderr)

def checkFakesRunning(ignored):
    if fakeScaleController.isReady:# and fakeTCS.isReady:
        startTCCLCO()

fakeScaleController.addStateCallback(checkFakesRunning)
# fakeTCS.addStateCallback(checkFakesRunning)


reactor.run()
