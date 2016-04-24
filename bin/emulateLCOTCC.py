#!/usr/bin/env python2
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
UDPPort = 25010

ScaleDevicePort = 26000
TCSDevicePort = 27000

# root = Tkinter.Tk()
# root.geometry("900x400+200+50")
# twisted.internet.tksupport.install(root)
# root.wm_withdraw()


# RO.Wdg.stdBindings(root)

# class MockTCCLCOActor(TCCLCOActor):
#     def __init__(self):
#         self.name = "mockTCCLCO"
#         TCCLCOActor.__init__(self,
#             name = self.name,
#             userPort = UserPort,
#             udpPort = UDPPort,
#             tcsDev = TCSDevice("mockTCS", "localhost", TCSDevicePort),
#             scaleDev = ScaleDevice("mockScale", "localhost", ScaleDevicePort),
#         )
#         self.server.addStateCallback(self._serverStateCallback)
#         self.actorClientWdg = None

#     def _serverStateCallback(self, sock):
#         """Actor server state callback; use to construct a client window
#         """
#         if sock.isReady:
#             tccTopLevel = RO.Wdg.Toplevel(
#                 master = root,
#                 title = self.name,
#                 geometry = "1000x500+300+200",
#             )
#             self.actorClientWdg = ActorClientWdg(
#                 master = tccTopLevel,
#                 name = "tcc", # name of keyword dictionary
#                 host = "localhost",
#                 port = UserPort,
#             )
#             self.actorClientWdg.pack(fill="both", expand=True)

print "Start fake LCO controllers"
fakeScaleController  = FakeScaleCtrl("fakeScale",  ScaleDevicePort)
fakeTCS = FakeTCS("mockTCSDevice", TCSDevicePort)

def startTCCLCO(*args):
    try:
        tccActor = TCCLCOActor(
            name = "tccLCOActor",
            userPort = UserPort,
            udpPort = UDPPort,
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

