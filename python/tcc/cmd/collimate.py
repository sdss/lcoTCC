from __future__ import division, absolute_import


__all__ = ["collimate"]


class CollimationModel(object):
    def __init__(self):
        self.file = "collimationFile"
        self.doCollimate = False
        self.collimateInterval = 30.
        self.reload()

    def reload(self):
        # read the file, create a model
        pass

    def apply(self, ha, dec, temp=None):
        """Return the desired M2
        collimation pistion, tiltx, tilty, transx, transy
        for a given ha, dec, and temperature
        """
        return tuple(1, 1, 1, 1, 1)




def collimate(tccActor, userCmd):
    """adjust collimation parameters
    """
    params = userCmd.parsedCmd.paramDict
    # quals = userCmd.parsedCmd.qualDict
    parsedKeys = params.keys()
    if "stop" in parsedKeys:
        tccActor.collimationModel.doCollimate = False
        tccActor.collimateTimer.cancel()
        userCmd.setState(userCmd.Done)
    elif "start" in parsedKeys:
        tccActor.collimationModel.doCollimate = True
        tccActor.updateCollimation(userCmd)
    elif "reload" in parsedKeys:
        tccActor.collimationModel.reload()
        tccActor.updateCollimation(userCmd)

