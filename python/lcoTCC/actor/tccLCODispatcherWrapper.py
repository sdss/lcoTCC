from __future__ import division, absolute_import

from twistedActor import DispatcherWrapper
from .tccLCOActorWrapper import TCCLCOActorWrapper

__all__ = ["TCCLCODispatcherWrapper"]

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
