#!/usr/bin/env python2
from __future__ import division, absolute_import

import functools
import itertools

import numpy

from twisted.trial.unittest import TestCase
from twisted.internet.defer import gatherResults, Deferred
from twisted.internet import reactor

from tcc.actor import TCCLCODispatcherWrapper

from twistedActor import testUtils

testUtils.init(__file__)


"""todo, test slew and offset supersedes

test move / stop m2, scale device
test set scale factor, verify mirror moves
move m2, set scale, m2 move shoud fail?

test scale zeropoint current and number
should fail out of range

test target command
test target command with unsafe cart

test rotator move
min/max values

fake and test mirror moving states

test rotation triggers slewing state in rot axis

test timeouts

test mangled status
"""

"""
test these on tcc model:
        "ScaleState=%s, %.4f"%(self._state, timeRemaining)
        kwList.append("ThreadRingPos=%.4f"%self.position)
        kwList.append("ScaleZeroPos=%.4f"%self.scaleZero)
        kwList.append("ThreadRingSpeed%.4f"%self.speed)
        kwList.append("ThreadRingMaxSpeed%.4f"%self.maxSpeed)
        kwList.append("DesThreadRingPos=%.4f"%self.desPosition)
        kwList.append("CartID=%i"%self.cartID)
        kwList.append("CartLocked=%s"%(str(self.locked)))
        kwList.append("CartLoaded=%s"%(str(self.loaded)))

"""

class TestLCOCommands(TestCase):

    def setUp(self):
        """!Set up a test
        """
        self.dw = TCCLCODispatcherWrapper()
        # reset the global threadring position
        return self.dw.readyDeferred

    def tearDown(self):
        """!Tear down a test
        """
        delayedCalls = reactor.getDelayedCalls()
        for call in delayedCalls:
            call.cancel()
        return self.dw.close()

    @property
    def dispatcher(self):
        """!Return the actor dispatcher that talks to the mirror controller
        """
        return self.dw.dispatcher

    @property
    def actor(self):
        """!Return the tcc actor
        """
        return self.dw.actorWrapper.actor

    @property
    def model(self):
        """!Return the tcc model
        """
        return self.dw.dispatcher.model

    @property
    def cmdQueue(self):
        """!return the cmdQueue on the dispatcher wrapper
        """
        return self.dw.cmdQueue

    def queueCmd(self, cmdStr, callFunc):
        d1, cmd1 = self.dw.queueCmd(
            cmdStr,
            callFunc = callFunc,
            callCodes = ":>",
        )
        return d1

    def queueOffsetCmd(self, cmdStr, raVal, decVal):
        """TCS device sets track commands done instantly (eg before state=Tracking)
        return a deferred here that will only fire when state==Tracking
        """
        d = Deferred()
        def fireWhenTracking(keyVar):
            if keyVar.valueList[0] == "Tracking" and keyVar.valueList[1] == "Tracking":
                # telescope is tracking
                self.checkOffsetDone(raVal, decVal)
                d.callback(None)
        def removeCB(foo=None):
            self.model.axisCmdState.removeCallback(fireWhenTracking)
        d.addCallback(removeCB)
        self.model.axisCmdState.addCallback(fireWhenTracking)
        self.dw.queueCmd(cmdStr)
        return d

    def checkFocus(self, cmdVar, focusVal):
        """Check the actor, and the model, verify that the correct focus
        is present

        @param[in] cmdVar, passed automatically by callback framework
        @param[in] focusVal, the expected focus value
        """
        if cmdVar.isDone:
            self.assertFalse(cmdVar.didFail)
            self.assertAlmostEqual(float(focusVal), float(self.actor.secDev.status.secFocus))
            # tcs isn't used for focus
            # self.assertAlmostEqual(float(focusVal), float(self.actor.tcsDev.status.statusFieldDict["focus"].value))
            # model doesn't update very fast
            # self.assertAlmostEqual(float(focusVal), float(self.model.secFocus.valueList[0]))

    def checkScale(self, cmdVar, scaleVal):
        """Check the actor, and the model, verify that the correct scale
        is present

        @param[in] cmdVar, passed automatically by callback framework
        @param[in] scaleVal, the expected scale value
        """
        if cmdVar.isDone:
            print("threadpos", self.actor.scaleDev.status.position)
            print("measScale pos", self.actor.scaleDev.encPos)
            print("measScale encs", self.actor.measScaleDev.encPos)
            # self.assertAlmostEqual(float(scaleVal), float(self.actor.scaleDev.currentScaleFactor), msg="actor-current: %.6f, %.6f"%(float(scaleVal), float(self.actor.scaleDev.currentScaleFactor)))
            # self.assertAlmostEqual(float(scaleVal), float(self.actor.scaleDev.targetScaleFactor), msg="actor-target: %.6f, %.6f"%(float(scaleVal), float(self.actor.scaleDev.targetScaleFactor)))
            self.assertAlmostEqual(float(scaleVal), float(self.model.scaleFac.valueList[0]), msg="model: %.6f, %.6f"%(float(scaleVal), float(self.model.scaleFac.valueList[0])))

    def checkAxesState(self, axisStateList):
        assert len(axisStateList) == 3
        for axisState in axisStateList:
            assert axisState in ["Tracking", "Slewing", "Halted"]
        # model isn't always 100% reliable check the state on status instead
        #for desState, lastState in itertools.izip(axisStateList, self.model.axisCmdState.valueList):
        for desState, lastState in itertools.izip(axisStateList, self.actor.tcsDev.status.axisCmdStateList()):
            self.assertEqual(desState, lastState)

    def checkAxesPosition(self, raVal, decVal):
        raActorPos = self.actor.tcsDev.status.statusFieldDict["ra"].value
        decActorPos = self.actor.tcsDev.status.statusFieldDict["dec"].value
        # raModelPos, decModelPos, rotModelPos = self.model.axePos.valueList
        # if raModelPos is None or decModelPos is None:
        #     self.assertTrue(False, "No value on model!")
        self.assertAlmostEqual(float(raVal), float(raActorPos))
        self.assertAlmostEqual(float(decVal), float(decActorPos))
        # self.assertAlmostEqual(float(raVal), float(raModelPos))
        # self.assertAlmostEqual(float(decVal), float(decModelPos))

    def checkIsSlewing(self):
        self.checkAxesState(["Slewing"]*2 + ["Halted"])

    def checkOffsetDone(self, raVal, decVal):
        # how to verify position is correct?
        self.checkAxesState(["Tracking"]*2 + ["Halted"])
        self.checkAxesPosition(raVal, decVal) # Undo negative offsets!

    def testFocus(self):
        focusVal = 70
        return self.queueCmd(
            cmdStr = "set focus=%i"%focusVal,
            callFunc = functools.partial(self.checkFocus, focusVal=focusVal)
            )


    def testFocusList(self):
        focusCmdList = ["set focus=70", "set focus=100/incr", "set focus=-50/incr", "set focus=30.4", "set focus"]
        focusValList = [70, 170, 120, 30.4, 30.4]
        callFuncList = [functools.partial(self.checkFocus, focusVal=focusVal) for focusVal in focusValList]
        deferredList = [self.queueCmd(cmdStr, callFunc) for cmdStr, callFunc in itertools.izip(focusCmdList, callFuncList)]
        return gatherResults(deferredList)

   # LCO HACK: small focus moves are allowed, uncomment and rewrite tests when min threshold is implemented.

    # def testFocusSmall1(self):
    #     focusVal = self.actor.secDev.status.secFocus + 20
    #     # focus delta's less than 50 will return successfully
    #     # immediately
    #     return self.queueCmd(
    #         cmdStr = "set focus=%i"%focusVal,
    #         callFunc = functools.partial(self.checkFocus, focusVal=focusVal-20)
    #         )

    # def testFocusSmall2(self):
    #     focusValInc = 20
    #     # focus delta's less than 50 will return successfully
    #     # immediately
    #     focusVal = self.actor.secDev.status.secFocus
    #     return self.queueCmd(
    #         cmdStr = "set focus=%i/incr"%focusValInc,
    #         callFunc = functools.partial(self.checkFocus, focusVal=focusVal)
    #         )

    def testOffset(self):
        # self.checkAxesState("Idle")
        raVal, decVal = 5,5
        offsetCmd = "offset arc %i,%i"%(raVal, decVal)
        d = self.queueOffsetCmd(offsetCmd, raVal, decVal)
        reactor.callLater(0.1, self.checkIsSlewing)
        return d

    def testOffset2(self):
        # self.checkAxesState("Idle")
        raVal, decVal = 10.8,-5.2
        offsetCmd = "offset arc %.2f,%.2f"%(raVal, decVal)
        d = self.queueOffsetCmd(offsetCmd, raVal, decVal)
        reactor.callLater(0.1, self.checkIsSlewing)
        return d

    def _doubleOffset(self, raOff1, decOff1, raOff2, decOff2):
        returnD = Deferred()
        offsetCmd = "offset arc %.2f,%.2f"%(raOff1, decOff1)
        offsetCmd2 = "offset arc %.2f,%.2f"%(raOff2, decOff2)
        d1 = self.queueOffsetCmd(offsetCmd, raOff1, decOff1)
        reactor.callLater(0.1, self.checkIsSlewing)
        def sendNextOffset(*args):
            # only send offset once track is finished
            d2 = self.queueOffsetCmd(offsetCmd2, raOff1+raOff2, decOff1+decOff2)
            def setDone(callback):
                returnD.callback(None)
            d2.addCallback(setDone)
        d1.addCallback(sendNextOffset)
        return returnD

    def testDoubleOffset(self):
        return self._doubleOffset(5,6,7,8)

    def testDoubleOffset2(self):
        return self._doubleOffset(5.4, -3.6, 7.02, -8.2)

    def testScale1(self):
        scaleVal = 1
        def checkScaleAndMotorPos(cmdVar):
            self.checkScale(cmdVar, scaleVal=scaleVal)
            pos = self.actor.scaleDev.encPos
            zeropoint = self.actor.measScaleDev.zeroPoint
            self.assertAlmostEqual(float(pos), float(zeropoint), msg="pos: %.4f, zeropoint: %.4f"%(pos, zeropoint))
        return self.queueCmd(
            cmdStr = "set scale=%.6f"%scaleVal,
            callFunc = checkScaleAndMotorPos
            )

    def testScale(self):
        scaleVal = 1.00006
        return self.queueCmd(
            cmdStr = "set scale=%.6f"%scaleVal,
            callFunc = functools.partial(self.checkScale, scaleVal=scaleVal)
            )

    def testScale2(self):
        scaleVal = 0.9999
        return self.queueCmd(
            cmdStr = "set scale=%.6f"%scaleVal,
            callFunc = functools.partial(self.checkScale, scaleVal=scaleVal)
            )

    def testShowScale(self):
        def cb(cmdVar):
            self.assertTrue(cmdVar.isDone and not cmdVar.didFail)
        self.queueCmd("show scale", cb)

    def testScaleList(self):
        scaleVal1 = 1.00006
        scaleMult = 1.0004
        scaleCmdList = ["set scale=%.6f"%scaleVal1, "set scale=%.6f/mult"%scaleMult]
        scaleValList = [scaleVal1, scaleVal1*scaleMult]
        callFuncList = [functools.partial(self.checkScale, scaleVal=scaleVal) for scaleVal in scaleValList]
        deferredList = [self.queueCmd(cmdStr, callFunc) for cmdStr, callFunc in itertools.izip(scaleCmdList, callFuncList)]
        return gatherResults(deferredList)

    def testScaleCompRoundTrip(self):
        # test that there is no numerical issues with very small scale changes?
        scaleMults = numpy.linspace(0.999999, 1.000001, 10)
        # hand force very small offsets
        for pos in numpy.linspace(19.9999, 20.0001, 30):
            # set various zero poisitions
            self.actor.scaleDev.status._scaleZero = pos
            currScale = self.actor.currentScaleFactor
            for mult in scaleMults:
                mm1 = self.actor.scaleMult2mm(mult)
                mm2 = self.actor.scaleMult2mmStable(mult)
                self.assertAlmostEqual(mm1, mm2)
                s1 = self.actor.mm2scale(mm1)
                s2 = self.actor.mm2scale(mm2)
                self.assertAlmostEqual(s1, currScale * mult)
                self.assertAlmostEqual(s2, currScale * mult)

    def testThreadRingStatus(self):
        def cb(cmdVar):
            self.assertTrue(cmdVar.isDone and not cmdVar.didFail)
        return self.queueCmd("threadring status", cb)

    def testThreadRingStop(self):
        def cb(cmdVar):
            self.assertTrue(cmdVar.isDone and not cmdVar.didFail)
        return self.queueCmd("threadring stop", cb)

    def testThreadRingMove(self):
        position = self.actor.scaleDev.encPos + 5
        def cb(cmdVar):
            self.assertTrue(cmdVar.isDone and not cmdVar.didFail)
            self.assertEqual(self.actor.scaleDev.encPos, position)
        return self.queueCmd("threadring move %.4f"%position, cb)

    def testThreadRingHome(self):
        def cb(cmdVar):
            self.assertTrue(not cmdVar.didFail)
        return self.queueCmd("threadring home", cb)

    def testThreadRingMoveInc(self):
        posStart = self.actor.scaleDev.encPos
        incr = 5
        def cb(cmdVar):
            self.assertTrue(cmdVar.isDone and not cmdVar.didFail)
            self.assertEqual(self.actor.scaleDev.encPos, posStart+incr)
        return self.queueCmd("threadring move %.2f/incr"%incr, cb)

    def testThreadRingMoveStop(self):
        d = Deferred()
        def moveCB(cmdVar):
            self.assertTrue(cmdVar.didFail)
        def stopCB(cmdVar):
            self.assertTrue(cmdVar.isDone and not cmdVar.didFail)
            d.callback(None)
        position = self.actor.scaleDev.encPos + 5
        self.queueCmd("threadring move %.4f"%position, moveCB)
        cmd = self.actor.scaleDev.stop()
        cmd.addCallback(stopCB)
        return d

    def testThreadRingMoveStopWithDelay(self):
        d = Deferred()
        def moveCB(cmdVar):
            print(cmdVar)
            self.assertTrue(cmdVar.didFail)
        def stopCB(cmdVar):
            self.assertTrue(cmdVar.isDone and not cmdVar.didFail)
            d.callback(None)
        position = self.actor.scaleDev.encPos + 5
        self.queueCmd("threadring move %.4f"%position, moveCB)
        def callLater():
            cmd = self.actor.scaleDev.stop()
            cmd.addCallback(stopCB)
        reactor.callLater(0.5, callLater)
        return d

    def testThreadRingSpeed(self):
        speed = 0.1
        def cb(cmdVar):
            self.assertTrue(cmdVar.isDone and not cmdVar.didFail)
            self.assertEqual(self.actor.scaleDev.status.speed, speed)
        return self.queueCmd("threadring speed %.4f"%speed, cb)

    def testThreadRingSpeedMult(self):
        speedMult = 0.1
        prevSpeed = self.actor.scaleDev.status.speed
        def cb(cmdVar):
            self.assertTrue(cmdVar.isDone and not cmdVar.didFail)
            self.assertAlmostEqual(self.actor.scaleDev.status.speed, prevSpeed*speedMult)
        return self.queueCmd("threadring speed %.4f/mult"%speedMult, cb)

    # again command fails as expected but unit test sees
    # runtime error and fails?
    # def testThreadRingOverSpeed(self):
    #     speed = 1
    #     def cb(cmdVar):
    #         self.assertTrue(cmdVar.isDone and not cmdVar.didFail)
    #         self.assertEqual(self.actor.scaleDev.status.speed, speed)
    #     return self.queueCmd("threadring speed %.4f"%speed, cb)

    def testSecStatus(self):
        def cb(cmdVar):
            self.assertTrue(cmdVar.isDone and not cmdVar.didFail)
        return self.queueCmd("sec status", cb)

    def testSecStop(self):
        def cb(cmdVar):
            self.assertTrue(cmdVar.isDone and not cmdVar.didFail)
        return self.queueCmd("sec stop", cb)

    def testSecMove(self):
        position = self.actor.secDev.status.secFocus + 5
        def cb(cmdVar):
            self.assertTrue(cmdVar.isDone and not cmdVar.didFail)
            self.assertEqual(self.actor.secDev.status.secFocus, position)
        return self.queueCmd("sec move %.4f"%position, cb)

    def testSecMove2(self):
        position = self.actor.secDev.status.secFocus + 5
        tipx = 2
        newOrient = self.actor.secDev.status.orientation[:]
        newOrient[0] = position
        newOrient[1] = tipx
        def cb(cmdVar):
            self.assertTrue(cmdVar.isDone and not cmdVar.didFail)
            for x1, x2 in itertools.izip(self.actor.secDev.status.orientation, newOrient):
                self.assertEqual(x1, x2)
        return self.queueCmd("sec move %.4f, %.2f"%(position,tipx), cb)

    def testTarget(self):
        ra = 5
        dec = 6
        def cb(cmdVar):
            self.assertTrue(cmdVar.isDone and not cmdVar.didFail)
            self.assertTrue(self.actor.tcsDev.status.statusFieldDict["inpra"], ra)
            self.assertTrue(self.actor.tcsDev.status.statusFieldDict["inpdc"], dec)
            self.assertTrue(self.actor.tcsDev.status.statusFieldDict["ra"], ra)
            self.assertTrue(self.actor.tcsDev.status.statusFieldDict["dec"], dec)
        return self.queueCmd("target %.4f, %.2f icrs"%(ra, dec), cb)

    def testOffsetGuideMin(self):
        offset = 0.001 # below min threshold
        def cb(cmdVar):
            self.assertTrue(cmdVar.isDone and not cmdVar.didFail)
        return self.queueCmd("offset guide 0, 0, %.5f"%(offset), cb)

    def testOffsetGuideOverMax(self):
        offset = 0.5 # above max thresh
        def cb(cmdVar):
            self.assertTrue(cmdVar.isDone and not cmdVar.didFail)
        return self.queueCmd("offset guide 0, 0, %.5f"%(offset), cb)

    def testOffsetGuide(self):
        offset = 0.01
        def cb(cmdVar):
            self.assertTrue(cmdVar.isDone and not cmdVar.didFail)
        return self.queueCmd("offset guide 0, 0, %.5f"%(offset), cb)

    def testShowFocus(self):
        def cb(cmdVar):
            self.assertTrue(cmdVar.isDone and not cmdVar.didFail)
        return self.queueCmd("show focus", cb)

    def testShowStatus(self):
        def cb(cmdVar):
            self.assertTrue(cmdVar.isDone and not cmdVar.didFail)
        return self.queueCmd("show status", cb)

    def testInstrumentNum(self):
        def cb(cmdVar):
            self.assertTrue(cmdVar.isDone and not cmdVar.didFail)
            self.assertEqual(self.actor.scaleDev.status.cartID, 23)
        return self.queueCmd("thread status", cb)


    # def testOffsetGuideFail(self):
    #     offset = 0.001
    #     def cb(cmdVar):
    #         self.assertTrue(cmdVar.isDone and not cmdVar.didFail)
    #     return self.queueCmd("offset guide 0, 1, %.5f"%(offset), cb)

    # def testTargetUnsafe(self):
    #     self.actor.scaleDev.status.dict["lock_ring_axis"]["actual_position"]=50
    #     def cb(cmdVar):
    #         self.assertTrue(cmdVar.isDone and not cmdVar.didFail)
    #     return self.queueCmd("target %.4f, %.2f icrs"%(5,6), cb)

    #
    # def testTargetUnsafe2(self):
    #     self.actor.scaleDev.status.dict["pos_sw"][1]=0
    #     def cb(cmdVar):
    #         self.assertTrue(cmdVar.isDone and not cmdVar.didFail)
    #     return self.queueCmd("target %.4f, %.2f icrs"%(5,6), cb)

if __name__ == '__main__':
    from unittest import main
    main()

