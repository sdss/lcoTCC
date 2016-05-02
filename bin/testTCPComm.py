#!/usr/bin/env python2
from __future__ import division, absolute_import

import time

from twisted.internet.protocol import Factory, Protocol
from twisted.protocols.basic import LineReceiver
from twisted.internet.endpoints import TCP4ClientEndpoint, TCP4ServerEndpoint
from twisted.internet import reactor

import numpy

PORT = 8007

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
        self.printEvery = 100 # every 100 pings print stats

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


if __name__ == '__main__':
    pongFactory = PongFactory()
    pingFactory = PingFactory()

    def playPingPong(protocol):
        print("playPingPong")
        protocol.ping()


    def startClient(port):
        print("starting client")
        print(port)
        print(dir(port))
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
