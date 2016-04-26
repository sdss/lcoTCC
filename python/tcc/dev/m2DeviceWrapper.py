from __future__ import division, absolute_import

from twistedActor import DeviceWrapper

from .m2Device import M2Device
from .fakeLCODevs import FakeM2Ctrl

__all__ = ["M2DeviceWrapper"]

class M2DeviceWrapper(DeviceWrapper):
    """!A wrapper for an AxisDevice talking to a fake axis controller
    """
    def __init__(self,
        name,
        stateCallback = None,
        port = 0,
        debug = False,
        logReplies = False,
    ):
        """!Construct a M2DeviceWrapper that manages its fake axis controller

        @param[in] name  a string
        @param[in] stateCallback  function to call when connection state of hardware controller or device changes;
            receives one argument: this device wrapper
        @param[in] port  port for device; 0 to assign a free port
        @param[in] debug  if True, print debug messages
        @param[in] logReplies  should the FakeAxisCtrl print replies to stdout?
        """
        controller = FakeM2Ctrl(
            name = name,
            port = port,
        )
        DeviceWrapper.__init__(self, name=name, stateCallback=stateCallback, controller=controller, debug=debug)

    def _makeDevice(self):
        port = self.port
        if port is None:
            raise RuntimeError("Controller port is unknown")
        self.device = M2Device(
            name=self.name,
            host="localhost",
            port=port,
        )

    def _basicClose(self):
        """Explicitly kill all timers, to keep twisted dirty reactor
        errors showing up during tests.
        """
        self.controller.focusTimer.cancel()
        self.controller.slewTimer.cancel()
        self.device._statusTimer.cancel()
        return DeviceWrapper._basicClose(self)
