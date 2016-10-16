from __future__ import division, absolute_import

from twistedActor import ActorWrapper, DispatcherWrapper

from .tccLCOActor import TCCLCOActor
from ..dev import TCSDeviceWrapper, ScaleDeviceWrapper, M2DeviceWrapper, MeasScaleDeviceWrapper

__all__ = ["TCCLCOActorWrapper", "TCCLCODispatcherWrapper"]

class TCCLCOActorWrapper(ActorWrapper):
    """!Unit test wrapper for a mock LCO TCC actor
    """
    def __init__(self,
        name = "mockTCCLCO",
        userPort = 0,
        debug = False,
    ):
        """!Construct a TCCLCOActorWrapper

        @param[in] name  a name to use for messages
        @param[in] userPort  port for actor server
        @param[in] debug  print debug messages?
        """
        self.tcsWrapper = TCSDeviceWrapper(name="tcsWrapper", debug=debug)
        self.scaleWrapper = ScaleDeviceWrapper(name="scaleWrapper", debug=debug)
        self.m2Wrapper = M2DeviceWrapper(name="m2Wrapper", debug=debug)
        self.measScaleWrapper = MeasScaleDeviceWrapper(name="measScaleWrapper", debug=debug)
        deviceWrapperList = [self.tcsWrapper, self.scaleWrapper, self.m2Wrapper, self.measScaleWrapper]
        ActorWrapper.__init__(self,
            deviceWrapperList = deviceWrapperList,
            name = name,
            userPort = userPort,
            debug = debug,
        )

    def _makeActor(self):
        self.debugMsg("_makeActor()")
        # give scaleDevice access to the measScaleDevice
        self.scaleWrapper.device._addMeasScaleDev(self.measScaleWrapper.device)
        self.actor = TCCLCOActor(
            name = self.name,
            tcsDev = self.tcsWrapper.device,
            scaleDev = self.scaleWrapper.device,
            m2Dev = self.m2Wrapper.device,
            measScaleDev = self.measScaleWrapper.device,
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
