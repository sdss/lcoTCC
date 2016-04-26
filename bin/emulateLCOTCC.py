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

from tcc.actor import TCCLCOActor
from tcc.dev import TCSDevice, ScaleDevice, M2Device, FakeScaleCtrl, FakeTCS, FakeM2Ctrl

UserPort = 25000

ScaleDevicePort = 26000
TCSDevicePort = 27000
M2DevicePort = 28000

print "Start fake LCO controllers"
fakeScaleController  = FakeScaleCtrl("fakeScale",  ScaleDevicePort)
fakeTCS = FakeTCS("mockTCSDevice", TCSDevicePort)
fakeM2Ctrl = FakeM2Ctrl("fakeM2", M2DevicePort)

def startTCCLCO(*args):
    try:
        tccActor = TCCLCOActor(
            name = "tcc",
            userPort = UserPort,
            tcsDev = TCSDevice("tcsDev", "localhost", TCSDevicePort),
            scaleDev = ScaleDevice("mockScale", "localhost", ScaleDevicePort),
            m2Dev = M2Device("mockM2", "localhost", M2DevicePort)
            )
    except Exception:
        print >>sys.stderr, "Error starting fake lcoTCC"
        traceback.print_exc(file=sys.stderr)


def checkFakesRunning(ignored):
    if fakeScaleController.isReady and fakeTCS.isReady and fakeM2Ctrl.isReady:
        startTCCLCO()

fakeScaleController.addStateCallback(checkFakesRunning)
fakeTCS.addStateCallback(checkFakesRunning)
fakeM2Ctrl.addStateCallback(checkFakesRunning)

reactor.run()

