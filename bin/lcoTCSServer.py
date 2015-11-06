"""Useful links:
http://twistedmatrix.com/documents/13.0.0/core/howto/servers.html
http://twistedmatrix.com/documents/13.0.0/core/howto/clients.html
http://twistedmatrix.com/trac/wiki/FrequentlyAskedQuestions#HowdoImakeinputononeconnectionresultinoutputonanother
http://stackoverflow.com/questions/10807656/twisted-server-client-data-sharing
"""
from __future__ import absolute_import, division

from twisted.protocols.basic import LineReceiver
from twisted.internet.protocol import Factory, ClientFactory
from twisted.internet.endpoints import TCP4ServerEndpoint, TCP4ClientEndpoint
from twisted.internet import reactor

UserPort = 50016
TCSPort = 25000
TCSHost = "localhost"

# this dictionary will get populated when buildProtocol is called on each Factory as it starts up
ProtocolSwapper = {}

class ForwardToUser(LineReceiver):
    """This Protocol receives lines from the du Pont TCS and forwards them along to the user
    via the BackdoorServer
    """
    forwardingProtocol = None # set set below
    def lineReceived(self, line):
        """
        Return this line coming from the TCS to the user.
        """
        print "%s received line"%self
        proto = ProtocolSwapper.get(self.forwardingProtocol, None) # get access to the other protocols sendLine method
        if proto is None:
            print "couldn't access user forwarding protocol"
        else:
            proto.sendLine(line)

class ForwardToTCS(LineReceiver):
    """This Protocol receives lines from the user and forwards them to the du Pont TCS
    """
    forwardingProtocol = None # set below
    def lineReceived(self, line):
        """
        !!!! parser goes here !!!!

        You may want to add some command parser here to check or
        reject any commands you don't want to be sent to the TCS


        """
        print "%s received line"%self

        proto = ProtocolSwapper.get(self.forwardingProtocol, None) # get access to the other protocols sendLine method
        if proto is None:
            print "couldn't access TCS forwarding protocol"
        else:
            proto.sendLine(line)

    def connectionMade(self):
        print "%s Connection made"%self

class TCSClientFactory(ClientFactory):
    def buildProtocol(self, addr):
        print "%s.buildProtocol."%self
        proto = ForwardToUser()
        ProtocolSwapper[ForwardToUser] = proto
        return proto

    def startedConnecting(self, connector):
        print '%s Started to connect.'%self

    def clientConnectionLost(self, connector, reason):
        print '%s Lost connection.  Reason:'%self, reason

    def clientConnectionFailed(self, connector, reason):
        print '%s Connection failed. Reason:'%self, reason

class BackdoorServerFactory(Factory):
    def buildProtocol(self, addr):
        print "%s.buildProtocol."%self
        proto = ForwardToTCS()
        ProtocolSwapper[ForwardToTCS] = proto
        return proto

TCSClientFactory.forwardingProtocol = ForwardToUser
BackdoorServerFactory.forwardingProtocol = ForwardToTCS

# initialize swapper
ProtocolSwapper[ForwardToUser] = None
ProtocolSwapper[ForwardToTCS]= None


if __name__ == "__main__":
    # fire everything up!
    tcsClientFactory = TCSClientFactory()
    backdoorServerFactory = BackdoorServerFactory()
    serverEndpoint = TCP4ServerEndpoint(reactor, UserPort)
    clientEndpoint = TCP4ClientEndpoint(reactor, TCSHost, TCSPort)
    deferred1 = clientEndpoint.connect(tcsClientFactory)
    deferred2 = serverEndpoint.listen(backdoorServerFactory)
    reactor.run()

