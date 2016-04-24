from __future__ import division, absolute_import

from twistedActor import ActorWrapper, DispatcherWrapper

from .tccLCOActor import TCCLCOActor
from ..dev import TCSDeviceWrapper, ScaleDeviceWrapper

__all__ = ["TCCLCOActorWrapper", "TCCLCODispatcherWrapper"]

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

class TCCLCODispatcherWrapper(DispatcherWrapper):
    """!Wrapper for an ActorDispatcher talking to a mock LCO TCC talking to mock controllers

    The wrapper manages everything: starting up fake TCS and scale controllers
    on automatically chosen ports, constructing devices that talk to them, constructing
    a TCC actor the specified port, and constructing and connecting the dispatcher.
    """
    def __init__(self, userPort=0):
        """!Construct a TCCLCODispatcherWrapper

        @param[in] userPort  port for mock LCO controller; 0 to chose a free port
        """
        actorWrapper = TCCLCOActorWrapper(
            name = "mockTCCLCO",
            userPort = userPort,
        )
        DispatcherWrapper.__init__(self,
            name = "tccLCOClient",
            actorWrapper = actorWrapper,
            dictName = "tcc",
        )
