#!/usr/bin/env python2
from __future__ import division, absolute_import

from twisted.trial.unittest import TestCase

from tcc.actor import TCCLCOActorWrapper

from twistedActor import testUtils
testUtils.init(__file__)

class TestTCCLCOActorCtrlWrapper(TestCase):
    """Test basics of TCCLCOActorCtrlWrapper
    """
    def setUp(self):
        self.aw = TCCLCOActorWrapper()
        return self.aw.readyDeferred

    def tearDown(self):
        self.aw.actor.collimateStatusTimer.cancel()
        return self.aw.close()

    def testSetUpTearDown(self):
        self.assertFalse(self.aw.didFail)
        self.assertFalse(self.aw.isDone)
        self.assertTrue(self.aw.isReady)


if __name__ == '__main__':
    from unittest import main
    main()
