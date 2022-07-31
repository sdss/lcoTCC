#!/usr/bin/env python
from __future__ import division, absolute_import
"""Run the TCC LCO actor
"""
import sys
import traceback
import os
import datetime

from twisted.internet import reactor
# from twistedActor import startSystemLogging
from twistedActor import startFileLogging

from tcc.actor.tccLCOActor import TCCLCOActor
from tcc.dev import TCSDevice, M2Device

rolloverDatetime = datetime.time(hour=13, minute=0, second=0)

# log to directory $HOME/tcclogs/
logPath = "/data/logs/actors/tcc"
if not os.path.exists(logPath):
    os.makedirs(logPath)

startFileLogging(os.path.join(logPath, "tcc"), rotate=rolloverDatetime)

UserPort = 25000

TCSHost = "c100tcs"#.lco.cl
TCSDevicePort = 4242
M2DeviceHost = "vinchuca"
M2DevicePort = 52001


def startTCCLCO(*args):
    try:
        tccActor = TCCLCOActor(
            name = "tcc",
            userPort = UserPort,
            tcsDev = TCSDevice("tcsDev", TCSHost, TCSDevicePort),
            m2Dev = M2Device("m2Dev", M2DeviceHost, M2DevicePort),
            )
    except Exception:
        print >>sys.stderr, "Error lcoTCC"
        traceback.print_exc(file=sys.stderr)

def runTCC():
    startTCCLCO()
    reactor.run()

if __name__ == "__main__":
    runTCC()
