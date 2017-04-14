from __future__ import division, absolute_import
import numpy

__all__ = ["collimate"]


class CollimationModel(object):
    def __init__(self):
        self.file = "collimationFile"
        self.doCollimate = False
        self.collimateInterval = 30.
        # trans y, trans x, tip, tilt
        # for focus:
        # 5.894 meters m2 vertex to focal plate
        # 70.7 microns per degree C
        self.minTrans = 10. # microns
        self.minTilt = 0.5 # arcseconds
        self.minFocus = 10 # microns

        # values used December Eng Run 2016 and previously
        # transX = 200.
        # transY = 0.
        # tiltX = 45.
        # tiltY = 6.

        # values from Francesco/Povilas 12/12/2016
        # transX = -1420.
        # transY = -106.
        # tiltX = 7. # known as tip in povilas's terms
        # tiltY = -52. # known as tilt in povilas's terms

        # values from April 5 2017
        #transX = -1918.2
        #transY = 615.5
        #tiltX = -100
        #tiltY = -450

        # April on sky with povilas, on axis camera work
        transX = -616.51
        transY = -536.59
        tiltX = -100
        tiltY = -565

        self.baseOrientation = numpy.asarray([tiltX, tiltY, transX, transY])
        self.baseFocus = None
        self.baseTrussTemp = None

    def getFocus(self, trussTemp):
        """Return the desired focus value from trussTemp

        @raise runtime error if no focus baseline has been set
        """
        if None in [self.baseFocus, self.baseTrussTemp]:
            raise RuntimeError("No baseline set for focus-collimation model")
        # temperature decreases, dist between m2 and m1 shrinks,
        # correct by moving them apart.
        dtemp = self.baseTrussTemp - trussTemp
        # if dtemp is positive, temperature has lowered
        # focal length is longer than self.baseFocus
        # command m2 to a higher focus value than self.baseFocus
        # focus model is 70 microns/degC
        return self.baseFocus + dtemp*70.

    def setFocus(self, focusVal, trussTemp):
        self.baseFocus = focusVal
        self.baseTrussTemp = trussTemp


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

        # new model with updated CY

        a cross term in y helps the fit and some systematics

                vec          cy          cx         ctp         ctl

                 ONE      -272.9      -300.8       1.143       6.453
                  sd         679      -132.1       29.03      -13.56
                  cd       407.8       182.3       9.868      -4.282
                  sh      -39.71      -589.6     -0.4648        4.84
                  ch      -334.7       141.1      -10.21      -1.095
                sdch       833.6
                cdch       153.1

        rms                  58          63          4            3.

        """
        haRad = numpy.radians(ha)
        decRad = numpy.radians(dec+29)

        sinDec = numpy.sin(decRad)
        cosDec = numpy.cos(decRad)
        sinHA = numpy.sin(haRad)
        cosHA = numpy.cos(haRad)
        sinDecCosHA = numpy.sin(decRad)*numpy.cos(haRad)
        cosDecSinHA = numpy.cos(decRad)*numpy.sin(haRad)

        # old, Povilas updated such that zero points are easier?
        # transY = -272.9 + 679*sinDec + 407.8*cosDec + -39.71*sinHA + -334.7*cosHA + 833.6*sinDecCosHA + 153.1*cosDecSinHA

        # # transY = -2.141 + 1413*sinDec + 386.7*cosDec + -49.3*sinHA + -487.1*cosHA
        # transX = -300.8 + -132.1*sinDec + 182.3*cosDec + -589.6*sinHA + 141.1*cosHA
        # tiltX = 1.14 + 29.03*sinDec + 9.86*cosDec + -0.46*sinHA + -10.21*cosHA
        # tiltY = 6.45 + -13.56*sinDec + -4.28*cosDec + 4.84*sinHA + -1.09*cosHA

        transY = 679*sinDec + 407.8*(cosDec-1.) + -39.71*sinHA + -334.7*(cosHA-1) + 833.6*sinDecCosHA + 153.1*cosDecSinHA
        transX = -132.1*sinDec + 182.3*(cosDec-1.) + -589.6*sinHA + 141.1*(cosHA-1.)
        tiltX =  29.03*sinDec + 9.86*(cosDec-1.) + -0.46*sinHA + -10.21*(cosHA-1.)
        tiltY = -13.56*sinDec + -4.28*(cosDec-1) + 4.84*sinHA + -1.09*(cosHA-1.)

        flexTerms = self.baseOrientation - numpy.asarray([tiltX, tiltY, transX, transY])
        focus = None if temp is None else self.getFocus(temp)
        # multiply by -1 (orentation to move to to remove the flex)
        return [focus] + list(flexTerms)


def collimate(tccActor, userCmd):
    """adjust collimation parameters
    """
    params = userCmd.parsedCmd.paramDict
    # quals = userCmd.parsedCmd.qualDict
    param = params["type"].valueList[0].keyword
    if param == "stopTimer":
        tccActor.collimationModel.doCollimate = False
        tccActor.collimateTimer.cancel()
        userCmd.setState(userCmd.Done)
    elif param == "startTimer":
        tccActor.collimationModel.doCollimate = True
        tccActor.updateCollimation(userCmd)
    elif param == "force":
        tccActor.updateCollimation(userCmd, force=True)


