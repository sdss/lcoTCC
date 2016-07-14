from __future__ import division, absolute_import
import numpy

__all__ = ["collimate"]


class CollimationModel(object):
    def __init__(self):
        self.file = "collimationFile"
        self.doCollimate = False
        self.collimateInterval = 30.
        self.reload()

    def getOrientation(self, ha, dec, temp=None):
        """Return the desired M2
        collimation pistion, tiltx, tilty, transx, transy
        for a given ha(deg), dec(deg), and temperature

        tip = rotation about x (star moves in y)
        tilt = rotation about y (star moves in x)

        tip and tilt are right hand rotations

        Hi,
        Here is a first pass at a full flexure model

                        CY         CX         CTP         CTL
                           microns                 arcsec
             1        -2.1      -300.8        1.14       6.45
        sin(dec+29) 1413        -132.1       29.03     -13.56
        cos(dec+29)  386.7       182.3        9.86      -4.28
        sin(ha)      -49.3      -589.6       -0.46       4.84
        cos(ha)     -487.1       141.1      -10.21      -1.09

        rms error    107         63          4           3

        -Povilas

        """
        haRad = numpy.radians(ha)
        decRad = numpy.radians(dec+29)

        sinDec = numpy.sin(decRad)
        cosDec = numpy.cos(decRad)
        sinHA = numpy.sin(haRad)
        cosHA = numpy.cos(haRad)

        transY = -2.141 + 1413*sinDec + 386.7*cosDec + -49.3*sinHA + -487.1*cosHA
        transX = -300.8 + -132.1*sinDec + 182.3*cosDec + -589.6*sinHA + 141.1*cosHA
        tipAboutX = 1.14 + 29.03*sinDec + 9.86*cosDec + -0.46*sinHA + -10.21*cosHA
        tiltAboutY = 6.45 + -13.56*sinDec + -4.28*cosDec + 4.84*sinHA + -1.09*cosHA

        # multiply by -1 (orentation to move to to remove the flex)
        return numpy.asarray([tipAboutX, tiltAboutY, transX, transY]) * -1




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

