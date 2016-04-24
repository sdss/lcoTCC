#!/usr/bin/env python
from __future__ import division, absolute_import
"""Start a faked LCO TCC actor

"""
import sys
import traceback
# import Tkinter

import RO.Comm.Generic
RO.Comm.Generic.setFramework("twisted")
from twisted.internet import reactor
# import twisted.internet.tksupport
from twistedActor import startFileLogging
# import RO.Wdg

try:
    startFileLogging("emulateTCCLCO")
except KeyError:
   # don't start logging
   pass

from lcoTCC.actor import TCCLCOActor
from lcoTCC.dev import TCSDevice, ScaleDevice, FakeScaleCtrl, FakeTCS

UserPort = 25000

ScaleDevicePort = 26000
TCSDevicePort = 27000

print "Start fake LCO controllers"
fakeScaleController  = FakeScaleCtrl("fakeScale",  ScaleDevicePort)
fakeTCS = FakeTCS("mockTCSDevice", TCSDevicePort)

def startTCCLCO(*args):
    try:
        tccActor = TCCLCOActor(
            name = "tccLCOActor",
            userPort = UserPort,
            tcsDev = TCSDevice("tcsDev", "localhost", TCSDevicePort),
            scaleDev = ScaleDevice("mockScale", "localhost", ScaleDevicePort),
            )
    except Exception:
        print >>sys.stderr, "Error starting fake lcoTCC"
        traceback.print_exc(file=sys.stderr)


def checkFakesRunning(ignored):
    if fakeScaleController.isReady and fakeTCS.isReady:
        startTCCLCO()

fakeScaleController.addStateCallback(checkFakesRunning)
fakeTCS.addStateCallback(checkFakesRunning)

reactor.run()

