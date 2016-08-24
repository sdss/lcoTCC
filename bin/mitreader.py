import sys
import numpy
from twisted.internet.protocol import Protocol, ClientFactory
from twisted.protocols.basic import LineReceiver
from twisted.internet.endpoints import TCP4ClientEndpoint
from twisted.internet import defer
from twisted.internet import task
from twisted.internet import reactor
import datetime
import time
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

global mitProtocol
global motorProtocol
# global scanFile
global startTime
global motorStartTime
channels = ["GN0%i"%ii for ii in range(1,7)]

class Mit(LineReceiver):

    def lineReceived(self, line):
        line = line.strip()
        # global scanFile
        print("got line", line)
        global startTime
        if line.startswith("GN0"):
            chKey, val = line.split(",")
            val = float(val) / 2.
            timestamp = time.time() - startTime
            self.values[chKey].append([timestamp, val])
        # scanFile.write("%.4f %s\r\n"%(time.time()-startTime, str(data)))
        # sys.stdout.write(data)

    def readMits(self):
        print("readMits")
        self.transport.write("GA00\r\n")

    def zeroMits(self):
        self.values = {}
        for ch in channels:
            self.values[ch] = []

        self.transport.write("CR00\r\n")
        reactor.callLater(0.1, self.transport.write, "CN00\r\n")

class MitFactory(ClientFactory):
    def connectionMade(self):
        # self.transport.write("GA00")
        print("mit connection made")
        # self.transport.loseConnection()

    def startedConnecting(self, connector):
        print('Started to connect.')

    def buildProtocol(self, addr):
        print('Connected.')
        return Mit()

    def clientConnectionLost(self, connector, reason):
        print('Lost connection.  Reason:', reason)

    def clientConnectionFailed(self, connector, reason):
        print('Connection failed. Reason:', reason)

class Motor(LineReceiver):
    def lineReceived(self, line):
        global startTime
        if "ACTUAL_POSITION" in line and hasattr(self, "motorPos"):
            line = line.strip()
            garbage, value = line.split()
            value = float(value)
            self.motorPos.append([time.time()-startTime, value])
        sys.stdout.write(line)

    def move(self, pos):
        global motorStartTime
        global startTime
        motorStartTime = time.time() - startTime
        self.motorPos = []
        self.transport.write("move %.4f\r\n"%pos)

class MotorFactory(ClientFactory):
    def startedConnecting(self, connector):
        print('Started to connect.')

    def buildProtocol(self, addr):
        print('Connected.')
        return Motor()

    def clientConnectionLost(self, connector, reason):
        print('Lost connection.  Reason:', reason)

    def clientConnectionFailed(self, connector, reason):
        print('Connection failed. Reason:', reason)


if __name__ == "__main__":
    moveFromPos = float(sys.argv[1])
    moveToPos = float(sys.argv[2])
    motorSpeed = 0.1
    startTime = None
    # scanFile = open("scanFile-%s.mits"%datetime.datetime.now().isoformat(), "w")
    # scanFile.write("move from %.4f to %.4f\r\n"%(moveFromPos, moveToPos))
    mitProtocol = None
    motorProtocol = None

    def gotMitProtocol(p):
        print("got mit protocol")
        global mitProtocol
        # global scanFile
        global startTime
        mitProtocol = p
        mitProtocol.zeroMits() #

    def gotMotorProtocol(p):
        print("got motor protocol")
        global motorProtocol
        motorProtocol = p
        p.transport.write("STATUS\r\n")

    def startMits():
        print("start mits")
        global mitProtocol
        l = task.LoopingCall(mitProtocol.readMits)
        l.start(.2)

    def beginScan(cbVal):
        print("begin scan")
        global startTime
        global motorProtocol
        startTime = time.time() + 0.4
        reactor.callLater(0.5, motorProtocol.move, moveToPos)
        reactor.callLater(0.4, startMits)

    def plot():
        global mitProtocol
        global motorProtocol
        global motorStartTime
        fig = plt.figure(figsize=((30,30)))
        pltList = []
        for ch in channels:
            # convert time to motor position
            val = numpy.asarray(mitProtocol.values[ch])
            mitReadings = val[:,1] + moveFromPos
            motorDirection = numpy.sign(moveToPos - moveFromPos)
            motorPos = moveFromPos + (val[:,0] - motorStartTime) * motorDirection * motorSpeed
            pltList.append(plt.plot(val[:,0], mitReadings)[0])
        # plt.legend()
        motorVals = numpy.asarray(motorProtocol.motorPos)
        keith, = plt.plot(motorVals[:,0], motorVals[:,1], "o-k")
        plt.legend(
            pltList+[keith],
            channels + ["keith"],
            # fontsize=30,
            # loc = "upper center",
            )
        plt.xlabel("time (sec)")
        plt.ylabel("motor pos (mm)")
        plt.xlim([min(val[:,0]), max(val[:,0]+5)])
        fig.savefig(datetime.datetime.now().isoformat()+".png"); plt.close(fig)

    def killMe():
        print("killing process")
        # scanFile.close()
        reactor.stop()
        plot()

    point1 = TCP4ClientEndpoint(reactor, "10.1.1.41", 10001)
    point2 = TCP4ClientEndpoint(reactor, "10.1.1.30", 15000)
    d1 = point1.connect(MitFactory())
    d2 = point2.connect(MotorFactory())
    d1.addCallback(gotMitProtocol)
    d2.addCallback(gotMotorProtocol)

    d3 = defer.gatherResults([d1, d2], consumeErrors=True)
    d3.addCallback(beginScan)
    # wait for both protocols to be ready
    timeForMove = abs(moveFromPos-moveToPos)/motorSpeed + 2
    reactor.callLater(timeForMove, killMe)
    reactor.run()



