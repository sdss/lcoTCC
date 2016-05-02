#!/usr/bin/env python2
from __future__ import division, absolute_import

import functools
import itertools

from twisted.trial.unittest import TestCase
from twisted.internet.defer import gatherResults, Deferred
from twisted.internet import reactor

from tcc.actor import TCCLCODispatcherWrapper
from twistedActor import testUtils
testUtils.init(__file__)


"""todo, test slew and offset supersedes
"""

class TestLCOCommands(TestCase):

    def setUp(self):
        """!Set up a test
        """
        self.dw = TCCLCODispatcherWrapper()
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
            self.assertAlmostEqual(float(focusVal), float(self.actor.m2Dev.status.secFocus))
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
            self.assertAlmostEqual(float(scaleVal), float(self.actor.scaleDev.currentScaleFactor), msg="actor-current: %.6f, %.6f"%(float(scaleVal), float(self.actor.scaleDev.currentScaleFactor)))
            self.assertAlmostEqual(float(scaleVal), float(self.actor.scaleDev.targetScaleFactor), msg="actor-target: %.6f, %.6f"%(float(scaleVal), float(self.actor.scaleDev.targetScaleFactor)))
            self.assertAlmostEqual(float(scaleVal), float(self.model.scaleFac.valueList[0]), msg="model: %.6f, %.6f"%(float(scaleVal), float(self.model.scaleFac.valueList[0])))

    def checkAxesState(self, axisState):
        assert axisState in ["Tracking", "Slewing", "Halted"]
        axisStateList = [axisState, axisState, "NotAvailable"] # rotator is not available
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
            self.checkAxesState("Slewing")

    def checkOffsetDone(self, raVal, decVal):
        # how to verify position is correct?
        self.checkAxesState("Tracking")
        self.checkAxesPosition(-1*raVal, -1*decVal) # offsets are applied negatively (Du Pont TCS convention)

    def testFocus(self):
        focusVal = 10
        return self.queueCmd(
            cmdStr = "set focus=%i"%focusVal,
            callFunc = functools.partial(self.checkFocus, focusVal=focusVal)
            )

    def testFocusList(self):
        focusCmdList = ["set focus=10", "set focus=10/incr", "set focus=-5/incr", "set focus=10.4", "set focus"]
        focusValList = [10, 20, 15, 10.4, 10.4]
        callFuncList = [functools.partial(self.checkFocus, focusVal=focusVal) for focusVal in focusValList]
        deferredList = [self.queueCmd(cmdStr, callFunc) for cmdStr, callFunc in itertools.izip(focusCmdList, callFuncList)]
        return gatherResults(deferredList)

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

    def testScaleList(self):
        scaleVal = 1.00006
        scaleMult = 1.0004
        scaleCmdList = ["set scale=%.6f"%scaleVal, "set scale=%.6f/mult"%scaleMult]
        scaleValList = [scaleVal, scaleVal*scaleMult]
        callFuncList = [functools.partial(self.checkScale, scaleVal=scaleVal) for scaleVal in scaleValList]
        deferredList = [self.queueCmd(cmdStr, callFunc) for cmdStr, callFunc in itertools.izip(scaleCmdList, callFuncList)]
        return gatherResults(deferredList)

if __name__ == '__main__':
    from unittest import main
    main()

