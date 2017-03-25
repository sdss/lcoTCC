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
import datetime

rotateTime = datetime.datetime.now() + datetime.timedelta(seconds=10)

startFileLogging("emulateTCCLCO", rotate=rotateTime)


from tcc.actor import TCCLCOActor
from tcc.dev import TCSDevice, ScaleDevice, M2Device, FakeScaleCtrl, FakeTCS, FakeM2Ctrl, MeasScaleDevice, FakeMeasScaleCtrl, FFDevice, FakeFFPowerSuply

UserPort = 25000

ScaleDevicePort = 26000
MeasScaleDevicePort = 26500
MeasScaleDevicePort = 10001
TCSDevicePort = 27000
M2DevicePort = 28000
FFDevicePort = 29000


print("Start fake LCO controllers")
fakeScaleController  = FakeScaleCtrl("fakeScale",  ScaleDevicePort)
fakeTCS = FakeTCS("mockTCSDevice", TCSDevicePort)
fakeM2Ctrl = FakeM2Ctrl("fakeM2", M2DevicePort)
fakeFFDev = FakeFFPowerSuply("fakeFF", FFDevicePort)
fakeMeasScaleDev = FakeMeasScaleCtrl("fakeMeasScale", MeasScaleDevicePort)

measScaleDev = MeasScaleDevice("measScaleDev", "localhost", MeasScaleDevicePort)
tcsDev = TCSDevice("tcsDev", "localhost", TCSDevicePort)
scaleDev = ScaleDevice("mockScale", "localhost", ScaleDevicePort, measScaleDev)
m2Dev = M2Device("m2Dev", "localhost", M2DevicePort)

#ffDev = FFDevice("ffDev", "139.229.101.122", 23)
ffDev = FFDevice("ffDev", "localhost", FFDevicePort)

def startTCCLCO(*args):
    try:
        tccActor = TCCLCOActor(
            name = "tcc",
            userPort = UserPort,
            tcsDev = tcsDev,
            scaleDev = scaleDev,
            m2Dev = m2Dev,
            measScaleDev = measScaleDev,
            ffDev = ffDev,
            )
    except Exception:
        print >>sys.stderr, "Error starting fake lcoTCC"
        traceback.print_exc(file=sys.stderr)


def checkFakesRunning(ignored):
    if fakeScaleController.isReady and fakeTCS.isReady and fakeM2Ctrl.isReady and fakeFFDev.isReady and fakeMeasScaleDev.isReady:
        startTCCLCO()

fakeScaleController.addStateCallback(checkFakesRunning)
fakeTCS.addStateCallback(checkFakesRunning)
fakeM2Ctrl.addStateCallback(checkFakesRunning)
fakeFFDev.addStateCallback(checkFakesRunning)
fakeMeasScaleDev.addStateCallback(checkFakesRunning)

reactor.run()

