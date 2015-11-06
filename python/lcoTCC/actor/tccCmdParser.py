from __future__ import division, absolute_import
"""!TCC command parser
"""
import tcc.parse.parseDefs as parseDefs
from tcc.parse.cmdParse import CmdParser
import tcc.cmd
from tcc.cmd.broadcast import MsgTypeCodeDict

__all__ = ["TCCCmdParser", "TCCCmdList"]

# list of coordinate system keyword
_CoordSysList = (
    parseDefs.Keyword(
        name = "icrs",
        help = "ICRS RA, Dec (deg); date is Julian date (years) of observation and defaults to 2000",
        numValueRange = [0,1],
        castVals=float,
    ),
    parseDefs.Keyword(
        name = "fk5",
        help = "FK5 RA, Dec (deg); date is Julian date (years) of equinox and of observation and defaults to 2000",
        numValueRange = [0,1],
        castVals=float,
        defValueList=[2000.0],
    ),
    parseDefs.Keyword(
        name = "fk4",
        help = "FK4 RA, Dec (deg); date is Besselian date (years) of equinox and of observation and defaults to 1950",
        numValueRange = [0,1],
        castVals=float,
        defValueList=[1950.0],
    ),
    parseDefs.Keyword(
        name = "galactic",
        help = "IAU 1958 galactic long, lat (deg); date is Julian date (years) of observation and defaults to the current date",
        numValueRange = [0,1],
        castVals=float,
    ),
    parseDefs.Keyword(
        name = "geocentric",
        help="apparent geocentric RA, Dec (deg); date is Julian date (years) and defaults to the current date",
        numValueRange = [0,1],
        castVals=float,
    ),
    parseDefs.Keyword(
        name = "topocentric",
        help="Apparent topocentric az, alt (deg) without correction for atmospheric refraction; " +
            "date is TAI (MJD, sec) and defaults to the current date.",
        numValueRange = [0,1],
        castVals=float,
    ),
    parseDefs.Keyword(
        name = "observed",
        help="Refracted apparent topocentric az, alt (deg); date is TAI (MJD, sec) and defaults to the current date.",
        numValueRange = [0,1],
        castVals=float,
    ),
    parseDefs.Keyword(
        name = "mount",
        help="Mount coordinates (az, alt deg); note that azimuth is used as given; it is never wrapped).",
        numValueRange = [0,0],
    ),
    parseDefs.Keyword(
        name = "none",
        help="No object; do not track.",
        numValueRange = [0,0],
    ),
    parseDefs.Keyword(
        name = "instrument",
        help="Instrument focal plane coordinates (x, y deg, i.e. relative to nominal center of instrument).",
        numValueRange = [0,0],
    ),
    parseDefs.Keyword(
        name = "gImage",
        help="Guide image focal plane coordinates (x, y unbinned pixels, " +
            "where 0.5, 0.5 is the center of the lower left pixel of the CCD); " +
            "accepts one value: the guide probe number, which defaults to 0",
        numValueRange = [1,1],
        defValueList = [1],
        castVals=int,
    ),
    parseDefs.Keyword(
        name = "gProbe",
        help="Guide probe focal plane coordinates (x, y deg, i.e. relative to nominal center of guide problem); " +
            "accepts one value: the guide probe number, which defaults to 0",
        numValueRange = [1,1],
        defValueList = [1],
        castVals=int,
    ),
    parseDefs.Keyword(
        name = "ptCorr",
        help="Pointing correction (x, y deg): the same as rotator x, y except that x is along the direction of increasing az",
        numValueRange = [0,0],
    ),
    parseDefs.Keyword(
        name = "rotator",
        help="Rotator focal plane coordinates (x, y deg). 0,0 is the center of rotation and should be the optical axis. " +
            "Rotator coordinates have a fixed offset and rotation angle with respect to the instrument; " +
            "these are specified in the Inst block.",
        numValueRange = [0,0],
    ),
)

########################### MULTI-USE QUALIFIERS ################################
TimeLimit = parseDefs.Qualifier("TimeLimit", numValueRange=[1,1], valType=float,
    help = "Specify timeout time for communication with controllers.",
)

class RestartQual(parseDefs.Qualifier):
    def __init__(self, defValueList, helpIfOmitted):
        """Construct a Restart qualifier.

        @param[in] helpIfOmitted  describe what happens if you omit /Restart, e.g. "all axes are restarted"
        """
        axisList = ["all", "azimuth", "altitude", "rotator", "tel1", "tel2"]
        fullAxisList = axisList + ["no" + axis for axis in axisList]
        fullAxisStr = ", ".join(fullAxisList)

        parseDefs.Qualifier.__init__(self,
            name = "restart",
            negatable = True,
            valType = fullAxisList,
            numValueRange = [0, None],
            defValueList = defValueList,
            defBoolValue = True,
            help = """Restart one or more axes.
  * If omitted, %s
  * Valid values are {%s},
    where All restarts all axes that are not explicitly negated
  * /Restart restarts all axes that exist
  * /NoRestart restarts no axes
  * If you specify one or more axes (Azimuth, Altitude and/or Rotator), only those are restarted
  * If you specify one or more negated axes (NoAzimuth, NoAltitude and/or NoRotator)
    those are left halted, and the other axes are restarted as per the rules above
  * If there is no instrument rotator, Rotator is silently ignored
  * Conflicts such as /Restart=(Az, NoAz) are prohibited (but All is acceptable with negated axes)
  * Examples:
    /Restart or /Restart=All: restart all axes
    /Restart=Az: restart only azimuth
    /Restart=NoRot: restart the default axes, excluding the rotator
    /NoRestart: restart no axes""" % (helpIfOmitted, fullAxisStr),
        )

Perfect = parseDefs.Qualifier(
    name = "perfect",
    help = "Prevents the requested move from happening unless all axes can be moved.",
)

class AbsRefCorrect(parseDefs.Qualifier):
    def __init__(self, defBoolValue):
        parseDefs.Qualifier.__init__(self,
            name = "absRefCorrect",
            negatable = True,
            help = "Specifies whether or not to apply absolute encoder corrections during a move.",
            defBoolValue = defBoolValue,
        )

class RefCoefficients(parseDefs.Qualifier):
    def __init__(self, defBoolValue):
        parseDefs.Qualifier.__init__(self,
            name = "refCoefficients",
            negatable = True,
            help = "Specifies whether to update the refraction coefficients in the obj and/or gs block.",
            defBoolValue=defBoolValue,
        )

class Collimate(parseDefs.Qualifier):
    def __init__(self, defBoolValue):
        parseDefs.Qualifier.__init__(self,
            name = "collimate",
            negatable = True,
            help = "Specifies whether to update the position of the mirrors to maintain " \
                "collimation as a function of temperature and altitude position.",
            defBoolValue=defBoolValue,
        )

Stop = parseDefs.Qualifier(
    name = "stop",
    help = "The instrument rotator will be gently stopped.",
)

class WrapPref(parseDefs.Qualifier):
    def __init__(self, name, axisName, defValue):
        parseDefs.Qualifier.__init__(self,
            name = name,
            valType = ["nearest", "middle", "negative", "positive"],
            numValueRange = [1, 1],
            defValueList = (defValue,),
            help = """Specify the desired wrap for the %s; valid values are:
- Nearest: use the angle nearest to the current position. This is the default for /AzWrap and is also used for all offsets (except for offsets in mount coordinates, of course).
- Middle: use the angle nearest the center of the range of motion. For example, if the range of motion is -190 to +370, the middle wrap range is -90 to +270. This is the default for /RotWrap (except during offsets), to reduce the odds that an exposure will be halted because the rotator hits a limit.
- Negative use the smaller angle. For example, if the range of motion is -190 to +370, the wrap range is -190 to +170. See the notes for details.
- Positive: use the larger angle. For example, if the range of motion is -190 to +370, the positive wrap range is 10 to 370. See the notes for details.

Notes:
- Nearest is the only wrap preference that pays any attention to the current position.
- The positive and negative wrap ranges are as follows:
- If range of motion < 720 degrees then postive/negative wrap extends from the forward/reverse limit through -/+ 360 degrees.
- If range of motion > 720 degrees then positive/negative wrap extends from the center of the range of motion through +/- 360 degrees.
""" % (axisName,),
        )

RotWrap = WrapPref(name="rotWrap", axisName="instrument rotator", defValue="middle")

AzWrap = WrapPref(name="azWrap", axisName="azimuth axis", defValue="nearest")

Input = parseDefs.Qualifier(
    name = "input",
    numValueRange = [1,1],
    valType=str,
    help = "The specified file is used for input.",
)

NoRead = parseDefs.Qualifier(
    name = "noRead",
    negatable = False,
    help = "Ignore existing values",
)

Name = parseDefs.Qualifier(
    name = "name",
    valType = str,
    numValueRange = [1,1],
    help = "The name of the object.",
)

Magnitude = parseDefs.Qualifier(
    name = "magnitude",
    numValueRange = [1,1],
    valType = float,
    defValueList = ('NaN',),
    help = "Object brightness.",
)

Distance = parseDefs.Qualifier(
    name = "distance",
    numValueRange = [1,1],
    valType = float,
    help = "distance to object in au.",
)

PM = parseDefs.Qualifier(
    name = "pm",
    numValueRange = [2,2],
    valType = float,
    defValueList = (0,0),
    help = "Proper motion in arcseconds/century. Equatorial proper motion is dEquatAng/dt, " + \
        "so it gets large near the pole",
)

Px = parseDefs.Qualifier(
    name = "px",
    numValueRange = [1,1],
    valType = float,
    defValueList = (0,),
    help = "Parallax in arcseconds.",
)

RV = parseDefs.Qualifier(
    name = "rv",
    numValueRange = [1,1],
    valType = float,
    defValueList = (0,),
    help = "Radial velocity in km/s, positive receding.",
)

Output = parseDefs.Qualifier(
    name = "output",
    numValueRange = [1,1],
    valType = str,
    help = "The specified file is used for output.",
)

Full = parseDefs.Qualifier(
    name = "Full",
    help = "Certain items return more information if /Full is used."
)
######################## Standard Parameters ###########################
class CoordSet(parseDefs.ValueParam):
    def __init__(self, name, defValueList=(), help=""):
        parseDefs.ValueParam.__init__(self,
            name=name,
            castVals=float,
            numValueRange=(0, None),
            defValueList=defValueList,
            help=help,
        )

class CoordPair(CoordSet):
    def __init__(self, name, extraHelp=""):
        helpList = ["""equatPos, polarPos [, equatVel, polarVel [, tai]]
                Specifies equatorial position and, optionally, velocity and time, where:
                - position is in degrees
                - velocity is in degrees/sec; default is 0
                - tai is TAI (MJD, seconds); default is the current TAI"""]
        if extraHelp:
            helpList.append(extraHelp)
        CoordSet.__init__(self,
            name=name,
            help="\n".join(helpList),
        )

class CoordSys(parseDefs.KeywordParam):
    def __init__(self, name, help, omit=()):
        """Construct a CoordSys keyword parameter

        @param[in] name  name of parameter
        @param[in] help  help string for parameter
        @paramm[in] omit: list of coordinate systems to omit (case blind)
        """
        omitSet = frozenset(str.lower() for str in omit)
        parseDefs.KeywordParam.__init__(self,
            name = name,
            help = help,
            keywordDefList = [kwd for kwd in _CoordSysList if kwd.name.lower() not in omitSet],
        )

blockName = parseDefs.KeywordParam(
    name = 'blockName',
    keywordDefList = [
        parseDefs.Keyword(name="AxeLim", help="axis limits and status bit flags"),
        parseDefs.Keyword(name="Earth", help="earth orientation predictions"),
        parseDefs.Keyword(name="Inst", help="instrument, rotator, guider and collimation parameters"),
        parseDefs.Keyword(name="Obj", help="object (target) data, including position, " \
            "offsets, refraction correction wavelength (both for the object and guiding) " \
            "and computed values through mount position"),
        parseDefs.Keyword(name="TelMod", help="telescope pointing model; warning: " \
            "this uses a special format required by TPOINT"),
        parseDefs.Keyword(name="Tune", help="performance tuning parameters"),
        parseDefs.Keyword(name="Weath", help="weather data"),
    ],
    help = "Name of block (data structure)",
)


######################## Command Definitions ###########################

TCCCmdList = (

    parseDefs.Command(
        name = "axis",
        minParAmt = 1,
        help = "Command one or more axis controllers.",
        callFunc = tcc.cmd.axis,
        paramList = [
            parseDefs.KeywordParam(
                name = 'command',
                keywordDefList = (
                    parseDefs.Keyword(name = "initialize", help = "Reconnect (if disconnected) and initialize the axis controller. " + \
                        "Initializing an axis halts it and puts it into a state in which it can be slewed, if possible."),
                    parseDefs.Keyword(name = "status", help = "Get axis status"),
                    parseDefs.Keyword(name = "stop", help = "Stop the axis"),
                    parseDefs.Keyword(name = "connect", help = "Connect to the axis controller"),
                    parseDefs.Keyword(name = "disconnect", help = "Disconnect from the axis controller"),
                ),
                help = "What to do with the axis controller."
            ),
            parseDefs.KeywordParam(
                name = 'axes',
                keywordDefList = [parseDefs.Keyword(name = item) for item in [
                    "azimuth", "altitude", "rotator", "tel1", "tel2",
                    "noAzimuth", "noAltitude", "noRotator", "noTel1", "noTel2"]
                ] + [parseDefs.Keyword(name = "all", passMeByDefault=True)],
                numParamRange = [0, None],
                help = "Which axes? If omitted then all axes. tel1/tel2 is a synonym for azimuth/altitude.",
            ),
        ],
        qualifierList = [
            parseDefs.Qualifier(
                name = "noCheck",
                help = "Send the command to all specified controllers, without checking to see if they exist.",
            ),
            TimeLimit,
        ],

    ),

    parseDefs.Command(
        name = "broadcast",
        minParAmt = 1,
        help = "Broadcast a message to all users.",
        callFunc = tcc.cmd.broadcast,
        paramList = [
            parseDefs.ValueParam(
                name = "message",
                castVals = str,
                numValueRange=(1, 1),
                help = "Message to broadcast (a quoted string)",
            ),
        ],
        qualifierList = [
            parseDefs.Qualifier(
                name = "type",
                valType = MsgTypeCodeDict.keys(),
                numValueRange = [1, 1],
                defValueList = ("information",),
                defBoolValue = True,
                help = "Message type (default is Information).",
            ),
        ],
    ),

    parseDefs.Command(
        name = "convert",
        callFunc = tcc.cmd.convert,
        minParAmt = 2,
        paramList = [
            CoordPair(name = 'fromCoords'),
            CoordSys(
                name = 'fromSys',
                help = "Coordinate system from which to convert; Mount and None are not supported; " \
                    + "default date is computed from 'fromCoords' time",
                omit = ("Mount", "None"),
            ),
            CoordSys(
                name = 'toSys',
                help = "Coordinate system to which to convert; Mount and None are not supported; " \
                    + "default date is computed from 'fromCoords' time",
                omit = ("Mount", "None"),
            ),
        ],
        qualifierList = [
            Distance, PM, Px, RV,
            parseDefs.Qualifier(
                name = "zpm",
                help = "Remove the effects of proper motion, radial velocity, and parallax to the current date " \
                    + " (zpm stands for zero proper motion).",
            ),
            parseDefs.Qualifier(
                name = "useGSWavelength",
                help = "Use the guide star wavelength instead of the object wavelength for refraction correction.",
            )
        ],
        help = "Convert a position from one coordinate system to another." \
    ),

    parseDefs.Command(
        name = "exit",
        callFunc = tcc.cmd.exit,
        help = "Exit from the TCC command interpreter.",
    ),

    parseDefs.Command(
        name = "help",
        help = "Print help",
        callFunc = tcc.cmd.help,
        paramList = [
            parseDefs.ValueParam(
                name = 'command',
                castVals=str,
                help = "command for which you want detailed help",
            ),
            parseDefs.ValueParam(
                name = 'subcommand',
                castVals=str,
                help = "subcommand for which you want detailed help",
            ),
        ],
        qualifierList = [
            parseDefs.Qualifier(
                name = "full",
                help = "print full help about every command",
            )
        ],
    ),

    parseDefs.Command(
        name = "mirror",
        help = "Command one or more mirror controllers.",
        callFunc = tcc.cmd.mirror,
        minParAmt = 1,
        paramList = [
            parseDefs.KeywordParam(
                name = 'command',
                help = "Mirror command",
                keywordDefList = [
                    parseDefs.Keyword(name = "status", help = "Return controller status"),
                    parseDefs.Keyword(name = "initialize", help = "Reconnect (if disconnected) and initialize the mirror controller. " \
                        "Initializing aborts the current command (if any) and stops motion (if any)."),
                    parseDefs.Keyword(name = "connect", help = "Connect to the mirror controller"),
                    parseDefs.Keyword(name = "disconnect", help = "Disconnect from the mirror controller"),
                ],
            ),
            parseDefs.KeywordParam(
                name = 'mirrors',
                help = "Which mirror(s) to command",
                keywordDefList = [parseDefs.Keyword(name = item)
                    for item in ['primary', 'secondary', 'tertiary']] \
                    + [parseDefs.Keyword(name = 'all', passMeByDefault = True)],
                numParamRange = [0, None],
            )
        ],
        qualifierList = [TimeLimit],
    ),

    parseDefs.Command(
        name = "offset",
        minParAmt = 1,
        help = "Offsets the telescope in various ways in position and velocity.",
        callFunc = tcc.cmd.offset,
        paramList = [
            parseDefs.KeywordParam(
                name = 'type',
                keywordDefList = [
                    parseDefs.Keyword(name = "arc", help = "Offset along great circle on sky (coordSys axis 1, 2, e.g. RA, Dec)."),
                    parseDefs.Keyword(name = "boresight", help = "Specify position of object on the " \
                        "instrument (in x-y axes of the instrument) (instrument x,y)."),
                    parseDefs.Keyword(name = "instPlane", help = "Old term for Boresight (instrument x,y)"),
                    parseDefs.Keyword(name = "rotator", help = "Rotator offset (1 axis)"),
                    parseDefs.Keyword(name = "calibration", help = "Local pointing correction (az, alt, rot)."),
                    parseDefs.Keyword(name = "guideCorrection", help = "Changes the guiding correction (az, alt, rot)."),
                    parseDefs.Keyword(name = "gCorrection", help = "Old term for GuideCorrection (az, alt, rot).")
                ],
            ),
            CoordSet(
                name='coordset',
                help="""position and optionally velocity and TAI date (optional);
                    the format depends on the offset (because of varying #s of axes):
                    arc and boresight (aka instPlane) offsets have 2 axes:
                        pos1, pos2 [, vel1, vel2, [, TAI]]]
                    rotator offsets have 1 axis:
                        rotPos [, rotVel [, TAI]]
                    calibration and gCorrection offsets have 3 axes, though rotator is optional:
                        azPos, altPos [, rotPos [, azVel, altVel, [rotVel [, TAI]]]]
                    where:
                    - position is in degrees; default is 0
                    - velocity is in degrees/sec; default is 0
                    - TAI is TAI date (MJD, seconds); default is the current date""",
            ),
        ],
        qualifierList = [
            parseDefs.Qualifier(
                "pAbsolute", help = "position is absolute",
            ),
            parseDefs.Qualifier(
                "pIncremental", help = "position is incremental (the default)",
            ),
            parseDefs.Qualifier(
                "vIncremental", help = "velocity is incremental",
            ),
            parseDefs.Qualifier(
                "vAbsolute", help = "velocity is absolute (the default)",
            ),
            parseDefs.Qualifier(
                "computed", help = "offset using a computed slew (safer for long offsets)",
                negatable = True,
            ),
            # parseDefs.Qualifier( # discontinued
            #     "TDICorrection", help = "Specifies that the arc offset " \
            #     "velocity should be adjusted for drift scanning.",
            # ), # need NoComputed?
            # restart defaults to none
            RestartQual(defValueList=(), helpIfOmitted="do not restart any axes"),
            Perfect,
            AbsRefCorrect(defBoolValue=False),
            RefCoefficients(defBoolValue=False),
            Collimate(defBoolValue=False),
        ],
    ),

    parseDefs.Command(
        name = "ping",
        callFunc = tcc.cmd.ping,
        help = "test if actor is alive",
    ),

    parseDefs.Command(
        name = "process",
        callFunc = tcc.cmd.process,
        minParAmt = 1,
        help = "Disable, enable or show the state of various background processes.",
        paramList = [
            parseDefs.KeywordParam(
                name = 'command',
               keywordDefList = [parseDefs.Keyword(name = item) for item in ['Disable', 'Enable', 'Status']],
            ),
            parseDefs.KeywordParam(
                name = 'procNames',
                numParamRange = [0, None],
                keywordDefList = [
                    parseDefs.Keyword(name = "BrdTelPos",
                        help = "Broadcasts telescope position as UDP packets.",
                    ),
                    parseDefs.Keyword(name = "Collimate",
                        help = "Controls the mirrors to adjust focus, collimation and scale.",
                    ),
                    parseDefs.Keyword(name = "Status", help = "Regularly displays status.")
                ],
            ),
        ],
    ),

    parseDefs.Command(
        name = "ptCorr",
        callFunc = tcc.cmd.ptCorr,
        minParAmt = 2,
        paramList = [
            CoordPair(name = "predCoords"),
            CoordSys(
                name = "predCoordSys",
                help = "coordinate system from which to convert; Mount and None are not accepted",
                omit = ("Mount", "None"),
            ),
            CoordPair(name = "MeasCoords"),
            CoordSys(
                name = "measCoordSys",
                help = "coordinate system to which to convert; Mount and None are not accepted",
                omit = ("Mount", "None"),
            ),
        ],
        qualifierList = [
            Distance, PM, Px, RV,
            parseDefs.Qualifier(
                name = "useGSWavelength",
                help = "Use the guide star wavelength instead of the object wavelength for refraction correction.",
            )
        ],
        help = "Compute pointing correction from predicted and measured star position.\n\n" +
            "Typical usage is to specify the predicted position in ICRS or similar " +
            "and the measured position in GuideImage, GuideProbe or Instrument coordinates. " +
            "Allowed coordinate systems include all except Mount and None.\n\n" +
            "The time at which the conversion is performed is the time of MeasCoords," +
            "which should be the time at the middle of the exposure",
    ),

    parseDefs.Command(
        name = "queue",
        callFunc = tcc.cmd.queue,
        minParAmt = 1,
        help = "Start or stop a batch job (e.g. snow). Warning: only one batch job may run at a time",
        paramList = [
            parseDefs.KeywordParam(
                name = 'command',
                keywordDefList = [
                    parseDefs.Keyword(name = "run", numValueRange=[1,1], castVals = str,
                        help = "Start the specified batch job.",
                    ),
                    parseDefs.Keyword(name = "stop", help = "Stop the current batch job."),
                    parseDefs.Keyword(name = "status", help = "Show batch queue status."),
                    parseDefs.Keyword(name = "list", help = "List the batch jobs you can run."),
                ],
            ),
        ],
    ),

    parseDefs.Command(
        name = "quit",
        callFunc = tcc.cmd.exit,
        help = "Disconnect from the TCC (a synonym for exit).",
    ),

    parseDefs.Command(
        name = "rotate",
        callFunc = tcc.cmd.rotate,
        minParAmt = 0,
        help = "Make the instrument rotator track the object, horizon, etc.",
        paramList = [
            parseDefs.ValueParam(
                name = 'rotAngle',
                numValueRange = [0,3],
                castVals=float,
                #defValueList = [0,0],
                defValueList = (),
                help = "Rotator angle as pos [, vel [, time]], where pos is in degrees, vel in deg/sec and time is TAI (MJD seconds)",
            ),
            parseDefs.KeywordParam(
                name = 'rotType',
                keywordDefList = [
                    parseDefs.Keyword(name = "None", help = "No rotation.", passMeByDefault=True),
                    parseDefs.Keyword(name = "Object",
                        help = "rotAngle is the orientation of the object with respect to the instrument."),
                    parseDefs.Keyword(name = "Horizon",
                        help = "rotAngle is the angle of the horizon with respect to the instrument."),
                    parseDefs.Keyword(name = "Mount",
                        help = "rotAngle is the angle of the rotator in the coordinate system used by the rotator controller. "\
                        "Wrap preference is ignored (unlike other rotatation types)."),
                ],
            ),
        ],
        qualifierList = [
            Stop,
            AbsRefCorrect(defBoolValue=False),
            Collimate(defBoolValue=True),
            Perfect,
            RefCoefficients(defBoolValue=False),
            RestartQual(defValueList=('rotator',), helpIfOmitted = "restart the rotator"),
            RotWrap,
        ]
    ),

    parseDefs.CommandWrapper(
        name = "set",
        subCmdList = [
            parseDefs.SubCommand(
                parseDefs.Keyword(name="block"),
                callFunc = tcc.cmd.setBlock,
                minParAmt = 1,
                paramList = [blockName],
                qualifierList = [Input, NoRead],
                help = """Set data in a block (data structure).

You may set the block from a file (using /input) or set individual entries from the command line.
All blocks except TelMod use the following standard format:
fieldName one-or-more-spaces-separated-values\n" \
where fieldName is not case sensitive. Leading whitespace is ignored and lines that begin with # are ignored as comments""",
            ),
            parseDefs.SubCommand(
                parseDefs.Keyword(
                                name="focus",
                                castVals = float,
                                numValueRange = [0,1],
                            ),
                callFunc = tcc.cmd.setFocus,
                qualifierList = [
                    parseDefs.Qualifier(
                        name = "incremental",
                        help = "Add the new focus offset to the existing focus offset, rather than replacing it.",
                    ),
                ],
                help = "Changes the user-settable focus offset for the " \
                    "secondary mirror (microns), if a new value is specified. " \
                    "Then updates collimation (if tracking or slewing).",
            ),
            parseDefs.SubCommand(
                parseDefs.Keyword(
                    name = "imcenter",
                    castVals = float,
                    numValueRange = [2,2],
                ),
                callFunc = tcc.cmd.setImCenter,
                help="Set a new image center (specified in unbinned pixels) and adjust the pointing " + \
                    "of the telescope accordingly (by shifting the boresight). " + \
                    "The new center will persist until the next Set Instrument command.\n\n" + \
                    "Warning: if the new center is out of bounds (off the instrument)  " + \
                    "then the command is rejected.\n\n" + \
                    "This command is intended for spectrographs whose slit positions are not repeatable. " + \
                    "Use Set ImCenter to set the center of the image to the center of the slit. " + \
                    "That way objects will be properly centered on the slit.\n\n" + \
                    "If the slit position is repeatable and you have multiple slits with different centers, " + \
                    "it is may be easier to set up a view data file for each slit and use " + \
                    "Set Instrument/GCView whenever you change slits.",
            ),
            parseDefs.SubCommand(
                parseDefs.Keyword(
                    name = "instrument",
                    castVals = str,
                    numValueRange = [0,1],
                    help = "Name of instrument (the current instrument if omitted)",
                ),
                callFunc = tcc.cmd.setInstrument,
                qualifierList = [
                    parseDefs.Qualifier(
                        name = "gcView",
                        numValueRange = [1,1],
                        valType = str,
                        help = "Specify the guide camera view (none if omitted)."
                    ),
                    parseDefs.Qualifier(
                        name = "keep",
                        valType = ['scaleFac', 'secFocus'],
                        numValueRange = [1,3],
                        help = """Specify which items to retain during the instrument change; omitted items are nulled. Valid values:
                        * SecFocus: focus offset for the secondary mirror
                        * ScaleFac: scale factor""",
                    ),
                    AzWrap,
                    RotWrap,
                ],
                help = "Set the instrument: load new instrument data and adjust pointing accordingly. " + \
                    "If this command changes the current instrument then the rotator is halted.",
            ),
            parseDefs.SubCommand(
                parseDefs.Keyword(
                    name="ptErrProbe",
                    castVals = int,
                    numValueRange = [0,1],
                ),
                callFunc = tcc.cmd.setPtErrProbe,
                help = "Specifies the guide probe to use for pointing error correction.",
            ),
            parseDefs.SubCommand(
                parseDefs.Keyword(
                    name="maxUsers",
                    castVals = int,
                    numValueRange = [0,1],
                ),
                callFunc = tcc.cmd.setMaxUsers,
                help = "Set the maximum number of users of the command interpreter." + \
                    " Warning: the limit is only checked when a user connects."
            ),
            parseDefs.SubCommand(
                parseDefs.Keyword(
                    name="scaleFactor",
                    castVals = float,
                    numValueRange = [0,1],
                ),
                qualifierList = [
                    parseDefs.Qualifier(
                        "multiplicative",
                        help = "If specified then new scale factor = old scale factor * value.",
                    )
                ],
                callFunc = tcc.cmd.setScaleFactor,
                help = "Set the desired scale factor.",
            ),
            parseDefs.SubCommand(
                parseDefs.Keyword(
                    name="stInterval",
                    castVals = float,
                    numValueRange = [3,3],
                ),
                callFunc = tcc.cmd.setStInterval,
                help = "Set the intervals between status updates "\
                    "during tracking, slewing and when the telescope is doing neither.",
            ),
            parseDefs.SubCommand(
                parseDefs.Keyword(
                    name="time",
                ),
                callFunc = tcc.cmd.setTime,
                help = "Load earth orientation predictions from the current earth orientation prediction file.",
            ),
            parseDefs.SubCommand(
                parseDefs.Keyword(
                    name="wavelength",
                ),
                paramList = [
                    parseDefs.KeywordParam(
                        name = 'items',
                        keywordDefList = [
                            parseDefs.Keyword(name = "obj", numValueRange = [1,1], castVals=float),
                            parseDefs.Keyword(name = "gStars", numValueRange = [1,1], castVals=float)
                        ],
                        numParamRange = [0, None],
                    )
                ],
                minParAmt = 0,
                callFunc = tcc.cmd.setWavelength,
                help = '',
            ),
            parseDefs.SubCommand(
                parseDefs.Keyword(
                    name="weather",
                ),
                paramList = [
                    parseDefs.KeywordParam(
                        name = 'items',
                        keywordDefList = [
                            parseDefs.Keyword(name = "airTemp", numValueRange = [1,1], castVals=float,
                                help = "Outside air temperature, in C."),
                            parseDefs.Keyword(name ="secTrussTemp", numValueRange = [1,1], castVals=float,
                                help = "Secondary truss temperature, in C."),
                            parseDefs.Keyword(name ="primF_BFTemp", numValueRange = [2,2], castVals=float, # maxVals=2?
                                help = "Two measures of primary mirror temperature: " \
                                    "Front temperature, back - front temperature difference, in C"),
                            parseDefs.Keyword(name ="secF_BFTemp", numValueRange = [2,2], castVals=float,
                                help = "Two measures of secondary mirror temperature: " \
                                    "Front temperature, back - front temperature difference, in C"),
                            parseDefs.Keyword(name ="pressure", numValueRange = [1,1], castVals=float,
                                help = "Pressure in Pascals"),
                            parseDefs.Keyword(name ="humidity", numValueRange = [1,1], castVals=float,
                                help = "Fractional humidity (e.g. 0.2 for 20%)"),
                            parseDefs.Keyword(name ="tLapse", numValueRange = [1,1], castVals=float,
                                help = "Temperature lapse rate, in C/km"),
                            parseDefs.Keyword(name ="wSpeed", numValueRange = [1,1], castVals=float,
                                help = "Wind speed in m/s"),
                            parseDefs.Keyword(name ="wDirection", numValueRange = [1,1], castVals=float,
                                help = "Wind direction in degrees: S = 0, E = 90")
                        ],
                        numParamRange = [0, None],
                    ),
                ],
                qualifierList = [RefCoefficients(defBoolValue=True), Collimate(defBoolValue=True)],
                callFunc=tcc.cmd.setWeather
            ),
        ],
    ),

    parseDefs.CommandWrapper(
        name = "show",
        subCmdList = [
            parseDefs.SubCommand(
                parseDefs.Keyword(name="focus"),
                qualifierList = [Full],
                callFunc = tcc.cmd.showFocus,
                help = "Show secondary focus offset.",
            ),

            parseDefs.SubCommand(
                parseDefs.Keyword(name="block"),
                callFunc = tcc.cmd.showBlock,
                minParAmt = 1,
                help = "Show the specified block.",
                paramList = [
                    blockName,
                ],
                qualifierList = [Output, NoRead],
            ),

            parseDefs.SubCommand(
                parseDefs.Keyword(name="axisConfig"),
                callFunc = tcc.cmd.showAxisConfig,
                help = "Display config info about the axis controllers.",
                qualifierList = [Full],
            ),

            parseDefs.SubCommand(
                parseDefs.Keyword(name="instrument"),
                callFunc = tcc.cmd.showInstrument,
                help = "Display information about the current instrument.",
                qualifierList = [Full],
            ),

            parseDefs.SubCommand(
                parseDefs.Keyword(name="maxUsers"),
                callFunc = tcc.cmd.showMaxUsers,
                help = "Display the maximum number of users.",
                qualifierList = [Full],
            ),

            parseDefs.SubCommand(
                parseDefs.Keyword(name="mount"),
                callFunc = tcc.cmd.showMount,
                help = "Display the mount position of the main axes.",
                qualifierList = [Full],
            ),

            parseDefs.SubCommand(
                parseDefs.Keyword(name="myNumber"),
                callFunc = tcc.cmd.showMyNumber,
                help = "Display your user ID number.",
                qualifierList = [Full],
            ),

            parseDefs.SubCommand(
                parseDefs.Keyword(name="object"),
                callFunc = tcc.cmd.showObject,
                help = "Display user-specified object position and related parameters.",
                qualifierList = [Full],
            ),

            parseDefs.SubCommand(
                parseDefs.Keyword(name="physical"),
                callFunc = tcc.cmd.showPhysical,
                help = "Display the physical position of the main axes.",
                qualifierList = [Full],
            ),

            parseDefs.SubCommand(
                parseDefs.Keyword(name="ptErrProbe"),
                callFunc = tcc.cmd.showPtErrProbe,
                help = "Display the guide probe used for pointing error correction.",
                qualifierList = [Full],
            ),

            parseDefs.SubCommand(
                parseDefs.Keyword(name="scaleFactor"),
                callFunc = tcc.cmd.showScaleFactor,
                help = "Display the current scale factor.",
                qualifierList = [Full],
            ),

            parseDefs.SubCommand(
                parseDefs.Keyword(name="status"),
                callFunc = tcc.cmd.showStatus,
                help = "Display information about the state of the TCC.",
                qualifierList = [Full],
            ),

            parseDefs.SubCommand(
                parseDefs.Keyword(name="stInterval"),
                callFunc = tcc.cmd.showStInterval,
                help = "Display the interval between status updates.",
                qualifierList = [Full],
            ),

            parseDefs.SubCommand(
                parseDefs.Keyword(name="time"),
                callFunc = tcc.cmd.showTime,
                help = "Display the current time in several time systems.",
                qualifierList = [Full],
            ),

            parseDefs.SubCommand(
                parseDefs.Keyword(name="users"),
               callFunc = tcc.cmd.showUsers,
                help = "Display information about connected users.",
                qualifierList = [Full],
            ),

            parseDefs.SubCommand(
                parseDefs.Keyword(name="version"),
                callFunc = tcc.cmd.showVersion,
                help = "Display the version of the TCC control system software.",
                qualifierList = [Full],
            ),

            parseDefs.SubCommand(
                parseDefs.Keyword(name="wavelength"),
                callFunc = tcc.cmd.showWavelength,
                help = "Display the central wavelength for refraction correction for the object and the guide star.",
                qualifierList = [Full],
            ),

            parseDefs.SubCommand(
                parseDefs.Keyword(name="weather"),
                callFunc = tcc.cmd.showWeather,
                help = "Display weather information.",
                qualifierList = [Full],
            ),
        ],
    ),

    parseDefs.Command(
        name = "talk",
        minParAmt = 2,
        help = "Send a command directly to an axis or mirror controller.",
        callFunc = tcc.cmd.talk,
        paramList = [
            parseDefs.ValueParam(
                name = "device",
                castVals = str,
                numValueRange=(1, 1),
                help = "Device: one of az, alt, rot (axis controllers), prim, sec, tert (mirror controllers).",
            ),
            parseDefs.ValueParam(
                name = "command",
                castVals = str,
                numValueRange=(1, 1),
                help = "The command to send. It must be in double quotes if it includes spaces."
            ),
        ],
        qualifierList = [
            TimeLimit,
        ],
    ),

    parseDefs.Command(
        name = "track",
        help = "Make the telescope to slew to and track an object.",
        callFunc = tcc.cmd.track,
        paramList = [
            CoordPair(
                name = 'coordPair',
                extraHelp =  "Nonzero velocity specifies dEquatAng/dt, dPolarAng/dt; " \
                    "to track along a great circle specify /ScanVelocity or, " \
                    "equivalently, specify an arc offset with nonzero velocity.",
                ),
            CoordSys(
                name = 'coordSys',
                help = "Coordinate system and date",
                omit = ("Instrument", "GProbe", "GImage", "PtCorr", "Rotator"),
            ),
        ],
        minParAmt = 0,
        qualifierList = [
            Stop,
            Name,
            Magnitude,
            Distance,
            PM,
            Px,
            RV,
            parseDefs.Qualifier(
                "rotType",
                valType = ["object", "horizon", "physical", "mount", "none"],
                numValueRange = [1,1],
                help = """Type of rotation; choices are:
* Object: rotate with the object. The rotator angle is the angle of the coordinate system of the object
with respect to instrument x,y. For example if the object is specified in an RA/Dec coordinate system
then at 0 degrees east will be along the x axis of the instrument, and at 90 degrees east will be along y
(because east is the direction of increasing coordinate system axis 1).
Warning: the orientation is specified at the un-arc-offset position (without arc offset taken into account);
this allows drift-scanning to work, but may have surprising (not necessarily bad, just surprising)
effects if you are using arc offsets for other purposes.
* Horizon: rotate with the horizon. The rotator angle is the angle of the horizon with respect to the instrument.
At 0 the horizon (direction of increasing azimuth) lies along the x axis of the instrument;
at 90 the horizon lies along the y axis. Obtaining good results while rotating with the horizon
equires great care: read the note for details. Note: unlike object rotation,
horizon rotation is specified at the net object position, with arc offsets included.
* Mount: the rotator angle is directly sent to the instrument rotator. No wrap is applied.
Use Mount rotation to put the instrument rotator to a known position.
* Physical: similar to mount but wrap may be applied, and there may be difference in scale or offset.
Physical is deprecated.
* None: do not rotate.""",
            ),
            parseDefs.Qualifier(
                "rotAngle", numValueRange = [1,3],
                valType = float, help = "Set the angle of rotation: pos [vel [TAI]].",
            ),
            AzWrap,
            RotWrap,
            AbsRefCorrect(defBoolValue=True),
            Collimate(defBoolValue=True),
            Perfect,
            RefCoefficients(defBoolValue=True),
            RestartQual(defValueList=("all",), helpIfOmitted="restart all axes"),
            parseDefs.Qualifier(
                name = "keep",
                valType = [
                    'arcOffset', 'boresight', 'gCorrection', 'calibration',
                    'noArcOffset', 'noBoresight', 'noGCorrection', 'noCalibration',
                ],
                numValueRange = [1, None],
                help = """Retain the specified offsets or zero them?
* /Keep=<OffsetName> keeps the offset (both position and velocity)
* /Keep=No<OffsetName> zeros the offset (both position and velocity)
Valid offset names are:
* ArcOffset: object arc offset
* Boresight: boresight offset (also known as instrument plane offset)
* GCCorrection: net guiding correction
* Calibration: calibration offset
The default behavior for all offsets except calibration is to zero them if a new object is specified, else keep them.
The default behavior for calibration offsets is to keep the position component and zero the velocity component
(which is almost always 0 anyway), regardless of whether a new object is specified.""",
            ),
            parseDefs.Qualifier(
                "ptError",
                numValueRange = [0, None],
                valType = [
                    "noFindReference",
                    "noRefSlew",
                    "objSlew",
                ],
                help = """Start or end a pointing error sequence; the default behavior is to
save the current target, find a position reference star near the target, and slew to center the reference star
in the pointing error guide probe (as designated in the inst block). The following options can alter
this behavior:
* NoFindReference: use the target as the position reference star instead of finding one in the position reference catalog
* NoRefSlew: do not slew to the reference star
* ObjSlew: slew back to the target that was saved by the last Track/PtErr command (and the saved target
is cleared). This option may not be specified with NoFindReference or NoRefSlew.
""",
            ),
            parseDefs.Qualifier(
                "magRange",
                numValueRange = [2, 2],
                valType = float,
                help = """magnitude range for reference stars found with Track/Pterr. The order of the two values doesn't matter
                (in order to avoid confusion between smaller values and fainter stars).
                If omitted, then defaults to target magnitude +/- 2, if known, else (3, 7).
                """,
            ),
            parseDefs.Qualifier(
                "scanVelocity",
                numValueRange = [2, 3],
                valType = float,
                help = "Scan along a great circle. Values are equatSkyVel, polarVel [, TAI], " + \
                    "where equatSkyVel is velocity on the sky (dEquatPos/dt * cos(polarPos)) " + \
                    "and tai defaults to the current date (or to the date of coordPair, if specified). " + \
                    "Works by setting arc offset to 0, 0, equatSkyVel, polarVel, tai; " + \
                    "thus if /scanVelocity is specified, /keep=[no]arcOffset is ignored.",
            ),
            parseDefs.Qualifier(
                "chebyshev", numValueRange = [1,1], valType = str,
                help = "Track an object whose position is specified by Chebyshev " +
                    "polynomials of the first kind, as a function of TAI date.",
            ),
        ],
    ),
)

class TCCCmdParser(CmdParser):
    """!TCC command parser
    """
    def __init__(self):
        """!Construct a tccCmdParser
        """
        CmdParser.__init__(self, TCCCmdList)
