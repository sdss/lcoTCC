from __future__ import division, absolute_import

from twistedActor import DeviceWrapper

from .ffDevice import FFDevice
from .fakeLCODevs import FakeFFPowerSuply

__all__ = ["FFDeviceWrapper"]

class FFDeviceWrapper(DeviceWrapper):
    """!A wrapper for an AxisDevice talking to a fake axis controller
    """
    def __init__(self,
        name,
        stateCallback = None,
        port = 0,
        debug = False,
        logReplies = False,
    ):
        """!Construct a FFDeviceWrapper that manages its fake axis controller

        @param[in] name  a string
        @param[in] stateCallback  function to call when connection state of hardware controller or device changes;
            receives one argument: this device wrapper
        @param[in] port  port for device; 0 to assign a free port
        @param[in] debug  if True, print debug messages
        @param[in] logReplies  should the FakeAxisCtrl print replies to stdout?
        """
        controller = FakeFFPowerSuply(
            name = name,
            port = port,
        )
        DeviceWrapper.__init__(self, name=name, stateCallback=stateCallback, controller=controller, debug=debug)

    def _makeDevice(self):
        port = self.port
        if port is None:
            raise RuntimeError("Controller port is unknown")
        self.device = FFDevice(
            name=self.name,
            host="localhost",
            port=port,
        )

