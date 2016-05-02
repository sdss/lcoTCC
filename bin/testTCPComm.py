#!/usr/bin/env python2
from __future__ import division, absolute_import

import time

from twisted.internet.protocol import Factory, Protocol
from twisted.protocols.basic import LineReceiver
from twisted.internet.endpoints import TCP4ClientEndpoint, TCP4ServerEndpoint
from twisted.internet import reactor

from tcc.dev import M2DeviceWrapper

import numpy

PORT = 16007
class Pong(Protocol):
    def dataReceived(self, line):
        # if a ping is received, reply with pong
        if line.strip().lower() == "ping":
            # print("saw ping")
            # print("sending pong")
            self.transport.write("pong")

class PongFactory(Factory):
    def buildProtocol(self, addr):
        return Pong()

class Ping(Protocol):
    def __init__(self):
        self.responseTimes = []
        self.sentTime = None
        self.printEvery = 10000 # every 100 pings print stats

    @property
    def nPings(self):
        return len(self.responseTimes)

    def ping(self):
        # print("sending ping")
        self.sentTime = time.time()
        self.transport.write("ping")

    def dataReceived(self, line):
        # if a ping is received, reply with pong
        if line.strip().lower() == "pong":
            self.responseTimes.append(time.time()-self.sentTime)
            self.sentTime = None
            if self.nPings % self.printEvery == 0:
                self.printStats()
            self.ping()

    def meanTimes(self):
        return numpy.mean(self.responseTimes)

    def stdDevTimes(self):
        return numpy.std(self.responseTimes)

    def printStats(self):
        print("%.6f (%.6f)"%(self.meanTimes(), self.stdDevTimes()))

class PingFactory(Factory):
    def buildProtocol(self, addr):
        return Ping()

def pingPongRawTwisted():
    pongFactory = PongFactory()
    pingFactory = PingFactory()
    t1 = time.time()

    def playPingPong(protocol):
        global t1
        print("client startup took", time.time()-t1)
        print("playPingPong")
        protocol.ping()


    def startClient(port):
        global t1
        print("server startup took", time.time()-t1)
        t1 = time.time()
        print("starting client")
        point = TCP4ClientEndpoint(reactor, "localhost", PORT)
        d = point.connect(pingFactory)
        # when the client has started
        # begin continuously playing ping pong
        d.addCallback(playPingPong)

    def startServer():
        print("starting server")
        # first start the pong server listening
        endpoint = TCP4ServerEndpoint(reactor, PORT)
        d = endpoint.listen(pongFactory)
        # when the server is ready start the ping client
        d.addCallback(startClient)

    startServer()
    reactor.run()

class ActorPing(M2DeviceWrapper):
    def __init__(self, *args, **kwargs):
        self.responseTimes = []
        self.sentTime = None
        self.printEvery = 10000 # every 100 pings print stats
        M2DeviceWrapper.__init__(self, *args, **kwargs)

    @property
    def nPings(self):
        return len(self.responseTimes)

    def ping(self):
        # print("sending ping")
        self.sentTime = time.time()
        cmd = self.device.getStatus()
        cmd.addCallback(self.pingDone)

    def pingDone(self, callbackCmd):
        if callbackCmd.isDone:
            self.responseTimes.append(time.time()-self.sentTime)
            self.sentTime = None
            if self.nPings % self.printEvery == 0:
                self.printStats()
            self.ping()

    def meanTimes(self):
        return numpy.mean(self.responseTimes)

    def stdDevTimes(self):
        return numpy.std(self.responseTimes)

    def printStats(self):
        print("%.6f (%.6f)"%(self.meanTimes(), self.stdDevTimes()))


def pingPongTwistedActor():
    def ping(device):
        if device.isReady:
            print("ping!")
            device.ping()
    m2Wrapper = ActorPing(name="pinger", stateCallback=ping)
    reactor.run()



if __name__ == '__main__':
    pingPongTwistedActor()



