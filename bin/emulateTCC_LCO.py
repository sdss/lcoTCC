#!/usr/bin/env python2
from __future__ import division, absolute_import

from twisted.internet import reactor
from twistedActor import startFileLogging

from lcoTCC.actor import TCCLCOActorWrapper

UserPort = 26000

try:
    startFileLogging("emulateLCOTCC")
except KeyError:
   # don't start logging
   pass


if __name__ == "__main__":
    wrapper = TCCLCOActorWrapper(name="lcoWrapper", userPort = UserPort)
    reactor.run()
