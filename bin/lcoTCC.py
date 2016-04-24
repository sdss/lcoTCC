#!/usr/bin/env python2
from __future__ import division, absolute_import
"""Run the TCC LCO actor
"""
import sys
import traceback
import os

from twisted.internet import reactor
# from twistedActor import startSystemLogging
from twistedActor import startFileLogging

from lcoTCC.actor.tccLCOActor import TCCLCOActor
from lcoTCC.dev import TCSDevice, ScaleDevice, FakeScaleCtrl, FakeTCS

# log to directory $HOME/tcclogs/
homeDir = os.path.expanduser("~")
logPath = os.path.join(homeDir, "tcclogs")
if not os.path.exists(logPath):
    os.makedirs(logPath)

startFileLogging(os.path.join(logPath, "tcc"))
# startSystemLogging(TCC25mActor.Facility)

UserPort = 25000
UDPPort = 25010

ScaleDevicePort = 26000
TCSDevicePort = 4242

print "Start fake LCO controllers"
fakeScaleController  = FakeScaleCtrl("fakeScale",  ScaleDevicePort)
# fakeTCS = FakeTCS("mockTCSDevice", TCSDevicePort)

def startTCCLCO(*args):
    try:
        tccActor = TCCLCOActor(
            name = "tccLCOActor",
            userPort = UserPort,
            udpPort = UDPPort,
            tcsDev = TCSDevice("tcsDev", "c100tcs.lco.cl", TCSDevicePort),
            scaleDev = ScaleDevice("mockScale", "localhost", ScaleDevicePort),
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
