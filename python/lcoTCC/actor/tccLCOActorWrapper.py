from __future__ import division, absolute_import

from twistedActor import ActorWrapper

from tcc.actor import TCCLCOActor
from tcc.lco import TCSDeviceWrapper, ScaleDeviceWrapper
# from tcc.axis import AxisDeviceWrapper
# from tcc.mir import MirrorDeviceWrapper

__all__ = ["TCCLCOActorWrapper"]

class TCCLCOActorWrapper(ActorWrapper):
    """!Unit test wrapper for a mock LCO TCC actor
    """
    def __init__(self,
        name = "mockTCCLCO",
        userPort = 0,
        udpPort = 0,
        debug = False,
    ):
        """!Construct a TCCLCOActorWrapper

        @param[in] name  a name to use for messages
        @param[in] userPort  port for actor server
        @param[in] udpPort  port for udp broadcasts, if 0 twisted will automatically select an open one
        @param[in] debug  print debug messages?
        """
        self.tcsWrapper = TCSDeviceWrapper(name="tcsWrapper", debug=debug)
        self.scaleWrapper = ScaleDeviceWrapper(name="scaleWrapper", debug=debug)
        deviceWrapperList = [self.tcsWrapper, self.scaleWrapper]
        ActorWrapper.__init__(self,
            deviceWrapperList = deviceWrapperList,
            name = name,
            userPort = userPort,
            debug = debug,
        )

    def _makeActor(self):
        self.debugMsg("_makeActor()")
        self.actor = TCCLCOActor(
            name = self.name,
            tcsDev = self.tcsWrapper.device,
            scaleDev = self.scaleWrapper.device,
            userPort = self._userPort,
        )
