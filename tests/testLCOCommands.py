#!/usr/bin/env python2
from __future__ import division, absolute_import

import os
import functools
import itertools

from twisted.trial.unittest import TestCase
from twisted.internet.defer import gatherResults
from twisted.internet import reactor

from tcc.actor import TCCLCODispatcherWrapper
from tcc.base import testUtils
testUtils.init(__file__)


runAllTests = True

DataDir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "data")

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

    def checkFocus(self, cmdVar, focusVal):
        """Check the actor, and the model, verify that the correct focus
        is present

        @param[in] cmdVar, passed automatically by callback framework
        @param[in] focusVal, the expected focus value
        """
        if cmdVar.isDone:
            self.assertFalse(cmdVar.didFail)
            self.assertAlmostEqual(float(focusVal), float(self.actor.tcsDev.status.statusFieldDict["focus"].value))
            self.assertAlmostEqual(float(focusVal), float(self.model.secFocus.valueList[0]))

    def checkScale(self, cmdVar, scaleVal):
        """Check the actor, and the model, verify that the correct scale
        is present

        @param[in] cmdVar, passed automatically by callback framework
        @param[in] scaleVal, the expected scale value
        """
        if cmdVar.isDone:
            self.assertFalse(cmdVar.didFail)
            self.assertAlmostEqual(float(scaleVal), float(self.actor.scaleDev.currentScaleFactor), msg="actor-current")
            self.assertAlmostEqual(float(scaleVal), float(self.actor.scaleDev.targetScaleFactor), msg="actor-target")
            self.assertAlmostEqual(float(scaleVal), float(self.model.scaleFac.valueList[0]), msg="model")

    def checkAxesState(self, axisState):
        assert axisState in ["Tracking", "Slewing", "Halted"]
        axisStateList = [axisState, axisState, "NotAvailable"] # rotator is not available
        for desState, lastState in itertools.izip(axisStateList, self.model.axisCmdState.valueList):
            self.assertEqual(desState, lastState)

    def checkAxesPosition(self, raVal, decVal):
        raActorPos = self.actor.tcsDev.status.statusFieldDict["ra"].value
        decActorPos = self.actor.tcsDev.status.statusFieldDict["dec"].value
        raModelPos, decModelPos, rotModelPos = self.model.axePos.valueList
        self.assertAlmostEqual(float(raVal), float(raActorPos))
        self.assertAlmostEqual(float(decVal), float(decActorPos))
        self.assertAlmostEqual(float(raVal), float(raModelPos))
        self.assertAlmostEqual(float(decVal), float(decModelPos))

    def checkIsSlewing(self):
            self.checkAxesState("Slewing")

    def checkTrackDone(self, cmdVar, raVal, decVal):
        if cmdVar.isDone:
            # how to verify position is correct?
            self.checkAxesState("Tracking")
            self.checkAxesPosition(raVal, decVal)

    def testFocus(self):
        focusVal = 10
        return self.queueCmd(
            cmdStr = "set focus=%i"%focusVal,
            callFunc = functools.partial(self.checkFocus, focusVal=focusVal)
            )

    def testFocusList(self):
        focusCmdList = ["set focus=10", "set focus=10/incr", "set focus=10.4", "set focus"]
        focusValList = [10, 20, 10.4, 10.4]
        callFuncList = [functools.partial(self.checkFocus, focusVal=focusVal) for focusVal in focusValList]
        deferredList = [self.queueCmd(cmdStr, callFunc) for cmdStr, callFunc in itertools.izip(focusCmdList, callFuncList)]
        return gatherResults(deferredList)

    def testTrack(self):
        # self.checkAxesState("Idle")
        raVal, decVal = 5,5
        trackCmd = "track %i,%i icrs"%(raVal, decVal)
        d = self.queueCmd(trackCmd, functools.partial(self.checkTrackDone, raVal=raVal, decVal=decVal))
        reactor.callLater(2, self.checkIsSlewing)
        return d

    def testTrack2(self):
        # self.checkAxesState("Idle")
        raVal, decVal = 10.8,-5.2
        trackCmd = "track %.2f,%.2f icrs"%(raVal, decVal)
        d = self.queueCmd(trackCmd, functools.partial(self.checkTrackDone, raVal=raVal, decVal=decVal))
        reactor.callLater(2, self.checkIsSlewing)
        return d

    def testTrackAndOffset(self):
        # self.checkAxesState("Idle")
        raVal, decVal = 5,6
        raOff, decOff = 7,8
        trackCmd = "track %.2f,%.2f icrs"%(raVal, decVal)
        offsetCmd = "offset arc %.2f,%.2f"%(raOff, decOff)
        d1 = self.queueCmd(trackCmd, functools.partial(self.checkTrackDone, raVal=raVal, decVal=decVal))
        reactor.callLater(2, self.checkIsSlewing)
        d2 = self.queueCmd(offsetCmd, functools.partial(self.checkTrackDone, raVal=raVal+raOff, decVal=decVal+decOff))
        return gatherResults([d1, d2])

    def testTrackAndOffset2(self):
        # self.checkAxesState("Idle")
        raVal, decVal = 5.4,-3.6
        raOff, decOff = 7.02,-8.2
        trackCmd = "track %.2f,%.2f icrs"%(raVal, decVal)
        offsetCmd = "offset arc %.2f,%.2f"%(raOff, decOff)
        d1 = self.queueCmd(trackCmd, functools.partial(self.checkTrackDone, raVal=raVal, decVal=decVal))
        reactor.callLater(2, self.checkIsSlewing)
        d2 = self.queueCmd(offsetCmd, functools.partial(self.checkTrackDone, raVal=raVal+raOff, decVal=decVal+decOff))
        return gatherResults([d1, d2])


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

