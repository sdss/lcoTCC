from __future__ import division, absolute_import
"""A collection of structures for building python representations of parsed TCC commands.


note:
Currently negation mixing for parameters can happen eg: 'Axis Init Azimuth, NoAltitude' is allowed.
This will have to be handled outside the parser.  The parser sees Azimuth and NoAzimuth as
distinct keywords (not a negation of a single one).  This choice simplifies the code because
I believe the only command with negatable parameters is Axis...but I could be wrong
"""

__all__ = ["Qualifier", "Keyword", "Command", "SubCommand", "CommandWrapper"]

class CmdDefError(Exception):
    pass


class Qualifier(object):
    """!Used to define a qualifier (which may have values associated).
    """
    def __init__(self,
        name,
        valType = None,
        numValueRange = [0,0],
        defValueList = None,
        help = '',
        negatable = False,
        defBoolValue = False,
    ):
        """
        @param[in] name  string name of qualifier
        @param[in] valType  One of
            1) None - in which case this is strictly a flag-type qualifier with no values
            2) a callable function - which will cast any values to the
                correct type for this qualifier
            3) a list of strings - in which case this qualifier expects only values
                    belonging to this specific list.
        @param[in] numValueRange  [min, max] amount of values that may be associated
        @param[in] defValueList  if no values are explicitly indicated at parse time,
            use these instead (must match valType!)
        @param[in] help  a help string
        @param[in] negatable  boolean. Whether or not a preceeding No is allowed when
            specifying this qualifer. eg /Collimate vs. /NoCollimate
        @param[in] defBoolValue  boolean. If this qualifier is omitted by the user,
            the resulting ParsedQualifier object will contain this boolean value (and
            will additionally have the boolValueDefaulted flag set to True...).
        """
        self.name = name
        self.negatable = bool(negatable)
        self.defBoolValue = bool(defBoolValue)
        self._help = help
        defValueList = defValueList or []
        try:
            assert len(numValueRange) == 2
            if numValueRange[1] != None:
                numValueRange = [int(val) for val in numValueRange]
                assert numValueRange[0] <= numValueRange[1]
            else:
                int(numValueRange[0])
            if valType == None:
                # strictly a flag-type qualifier, no values...
                assert numValueRange == [0,0]
                assert defValueList == []
            elif callable(valType):
                # qualifier has values of type valType, verify that defaults are
                # property castable, and cast them
                defValueList = [valType(val) for val in defValueList]
            else:
                # qualifier must have values specific to list of valType
                for keyword in valType:
                    keyword.lower() # must be a string
                for val in defValueList:
                    # default values must be members of valType (a list in this case)
                    assert val in valType
        except Exception as e:
            raise CmdDefError('Poorly formed Qualifer construction: %s' % (e,))
        self.defValueList = defValueList
        self.numValueRange = numValueRange
        self.valType = valType

    @property
    def argList(self):
        if self.valType != None:
            # determine if values are basic (cast) types,
            # or a keyword type (eg from a list of allowed keywords)
            if callable(self.valType):
                strType = str(self.valType).split("'")[1]
            else:
                strType = 'keyword'
            minArgs = ', '.join([strType]*self.numValueRange[0])# for x in range(self.numValueRange[0])])
            if self.numValueRange[1] != None:
                maxArgs = ', '.join([strType]*(self.numValueRange[1]-self.numValueRange[0])) #for x in range(self.numValueRange[1]-self.numValueRange[0])])
            else:
                maxArgs = '%s, *'%strType
            if minArgs and maxArgs:
                # more than zero of them
                argList = ' = (%s [,%s])' % (minArgs, maxArgs)
            elif maxArgs:
                # only optional args
                if self.numValueRange[1] == 1:
                    argList = ' [= %s]' % maxArgs
                else:
                    argList = ' [= (%s)]' % maxArgs
            else:
                # only mandatory args
                if self.numValueRange[0] == 1:
                    argList = ' = %s' % minArgs
                else:
                    argList = ' = (%s)' % minArgs

            return argList
        else:
            # no args
            return ''

    @property
    def help(self):
        """!Print a help string
        """
        helpList = []
        helpList.append('/%s%s' % (self.name, self.argList))
        if self.defValueList:
            helpList.append('   default: %s' % str(self.defValueList))
        nlSplit = ['   ' + x.strip() for x in self._help.split('\n')]
        helpList += nlSplit
        if hasattr(self.valType, 'pop'):
            helpList.append('   Valid Keywords:')
            for kw in self.valType:
                helpList.append('      %s' % kw)
        return helpList

class ParamElement(object):
    """!A param is ultimately defined using a list of one or more of these
    """
    def __init__(self,
        name = None,
        castVals = None,
        numValueRange = None,
        defValueList = None,
        passMeByDefault=False,
        help = ''
    ):
        """
        @param[in] name  a string, will be used for unique abbreviation matching if not None
        @param[in] castVals  a callable, will cast any passed values to the correct type
        @param[in] numValueRange  [int, int] or [int, None]. Describes the max/min amount of acceptable values in valueList. If None, any amount of values are allowed
        @param[in] defValueList  a (possible empty) list of basic values to be passed by default if none were specified during parsing
        @param[in] passMeByDefault  a boolean. If True this param will be passed if a default is wanted
        """
        self.name = name
        if numValueRange != None:
            try:
                assert len(numValueRange) == 2
                if numValueRange[1] != None:
                    numValueRange = [int(val) for val in numValueRange]
                    assert numValueRange[0] <= numValueRange[1]
                else:
                    int(numValueRange[0])
            except:
                raise CmdDefError('numValueRange must be a 2 item list of integers ordered [low, high or None]')
            try:
                if numValueRange != [0,0]:
                # expect values, check for cast
                    assert callable(castVals)
            except:
                raise CmdDefError('a cast function must be defined for values.')
        self.castVals = castVals
        self.numValueRange = numValueRange
        self.passMeByDefault = bool(passMeByDefault)
        if defValueList != None:
            # test that values are cast correctly
            try:
                self.defValueList = [self.castVals(val) for val in defValueList]
            except:
                raise CmdDefError('Default value list cannot be casted correctly')
            try:
                if self.numValueRange[1] == None:
                    assert self.numValueRange[0] <= len(self.defValueList)
                else:
                    assert self.numValueRange[0] <= len(self.defValueList) <= self.numValueRange[1]
            except:
                raise CmdDefError('Default value list outside allowed range of number of values')
        else:
            #self.defValueList = [] # to allow [] to be a specified default value as in CoordSet
            self.defValueList = None
        self.help = help

    def __str__(self):
        return 'name: ' + self.name + ' numValueRange: ' + str(self.numValueRange)

class Keyword(ParamElement):
    """!For defining a single Keyword
    """
    def __init__(self,
        name,
        castVals = None,
        numValueRange = None,
        defValueList = None,
        passMeByDefault = False,
        help = '',
        ):
        """
        @param[in] name  a string, will be used for unique abbreviation matching if not None
        @param[in] castVals  a callable, will cast any passed values to the correct type
        @param[in] numValueRange  [int, int] or [int, None]. Describes the max/min amount of acceptable values in valueList. If None, any amount of values are allowed
        @param[in] defValueList  a (possible empty) list of basic values to be passed by default if none were specified during parsing
        @param[in] passMeByDefault  a boolean. If True this param will be passed if a default is wanted
        @param[in] help  a help string
        """
        ParamElement.__init__(self,
            name = name,
            castVals = castVals,
            numValueRange = numValueRange,
            defValueList = defValueList,
            passMeByDefault = passMeByDefault,
            help = help,
            )

class ParamBase(object):
    """!One piece of a command that has been split on whitespace (and not commas nor equals sign..)
    """
    def __init__(self,
        name,
        paramElementList,
        numParamRange = [1, 1] ,
        help = '',
    ):
        """
        @param[in] name  a name for this param, used to index the parsed param dictionary
            to be constructed at the time this is parsed.
        @param[in] paramElementList  a list of ParamElement objects
        @param[in] numParamRange  [int, int] or [int, None]. Describes the max/min amount
            of acceptable params in paramList. If None,
            any amount of params are allowed
        @param[in] help  a help string describing this parameter
        """
        self.name = name
        try:
            assert len(numParamRange) == 2
            if numParamRange[1] != None:
                numParamRange = [int(val) for val in numParamRange]
                assert numParamRange[0] <= numParamRange[1]
            else:
                int(numParamRange[0])
        except:
            raise CmdDefError('numParamRange must be a 2 item list of integers ordered [low, high or None]')
        self.numParamRange = numParamRange
        # name (used for matching) must be specified on all or none of params in paramList
        uniqueNames = [par.name for par in paramElementList]
        if None in uniqueNames:
            # make sure they are all None
            try:
                for name in uniqueNames:
                    assert name == None
            except:
                raise CmdDefError('For a given parameter, all values must either be named or not named; a mix is unacceptable.')
            self.matchList = None
        else:
            self.matchList = uniqueNames
        self.paramElementList = paramElementList
        self._help = help

    @property
    def defaultParamList(self):
        """!Which params to pass by default for this slot?
        """
        return [p for p in self.paramElementList if p.passMeByDefault]


    @property
    def help(self):
        raise NotImplementedError('subclasses must override')

class KeywordParam(ParamBase):
    """!For defining a param slot expecting keywords and optionally values
    """
    def __init__(self, name, keywordDefList, numParamRange = [1,1], help=''):
        """ @param[in] name  a name for this param
            @param[in] keywordDefList  a list of Keyword objects, be sure to specify any
                wanted as defaults specifically
            @param[in] numParamRange  number of keywords that may be passed jointly
            @param[in] help  a help string
        """
        ParamBase.__init__(self,
            name = name,
            paramElementList = keywordDefList,
            numParamRange = numParamRange,
            help = help,
        )

    def getArgs(self, strType, valRange):
        minArgs = ', '.join([strType]*valRange[0])# for x in range(valRange[0])])
        if valRange[1] != None:
            maxArgs = ', '.join([strType]*(valRange[1]-valRange[0])) # for x in range(valRange[1]-valRange[0])])
        else:
            maxArgs = '%s, *'%strType
        if minArgs and maxArgs:
            # more than zero of them
            argList = '%s [,%s]' % (minArgs, maxArgs)
        elif maxArgs:
            # only optional args
            argList = '[%s]' % maxArgs
        else:
            # only mandatory args
            argList = '%s' % minArgs
        return argList

    @property
    def argList(self):
        return self.getArgs(strType='keyword', valRange = self.numParamRange)

    @property
    def help(self):
        helpList = []
        helpList.append('%s: %s' % (self.name, self.argList))
        nlSplit = [x.strip() for x in self._help.split('\n')]
        # indent remaining
        nlSplit = ['   ' + x for x in nlSplit]
        helpList += nlSplit
        if self.defaultParamList:
            helpList.append('   Default: %s' % str([x.name for x in self.defaultParamList]))
        helpList.append('   Valid Keywords:')
        for kw in self.paramElementList:
            kwHelp = []
            kwName = kw.name
            if kw.castVals != None:
                strType = str(kw.castVals).split("'")[1]
                kwArgs = self.getArgs(strType = strType, valRange = kw.numValueRange)
                kwHelp.append('      %s = %s'%(kwName, kwArgs))
            else:
                # no args
                kwHelp.append('      %s' % kwName)
            if kw.defValueList:
                kwHelp.append('         default: %s'% str(kw.defValueList))
            if kw.help:
                kwHelp.append('         %s'% str(kw.help))
            helpList += kwHelp
        return helpList


class ValueParam(ParamBase):
    """!Represents a list of type castVals
    """
    def __init__(self, name, castVals, numValueRange=[1,1], defValueList = None, help = 'help'):
        """
        @param[in] name  a name for this param
        @param[in] castVals  a callable, will cast any passed values to the correct type
        @param[in] numValueRange  [int, int] or [int, None]. Describes the max/min amount of acceptable values in valueList. If None, any amount of values are allowed
        @param[in] defValueList  a (possible empty) list of basic values to be passed by default if none were specified during parsing
        @param[in] help  a help string
        """
        passMeByDefault = True if defValueList is not None else False
        paramElementList = [ParamElement(
            name = None,
            castVals = castVals,
            numValueRange = numValueRange,
            defValueList = defValueList,
            passMeByDefault = passMeByDefault,
        )]
        ParamBase.__init__(self,
            name = name,
            paramElementList = paramElementList,
            help = help,
            )

    @property
    def argList(self):
        valType = str(self.paramElementList[0].castVals).split("'")[1]
        valRange = self.paramElementList[0].numValueRange
        minArgs = ', '.join([valType]*valRange[0])# for x in range(valRange[0])])
        if valRange[1] != None:
            maxArgs = ', '.join([valType]*(valRange[1]-valRange[0]))# for x in range(valRange[1]-valRange[0])])
        else:
            maxArgs = '%s, *'%valType
        if minArgs and maxArgs:
            # more than zero of them
            argList = '%s [,%s]' % (minArgs, maxArgs)
        elif maxArgs:
            # only optional args
            argList = '[%s]' % maxArgs
        else:
            # only mandatory args
            argList = '%s' % minArgs
        return argList

    @property
    def help(self):
        helpList = []
        helpList.append('%s: %s' % (self.name, self.argList))
        nlSplit = [x.strip() for x in self._help.split('\n')]
        # indent remaining
        nlSplit = ['   ' + x for x in nlSplit]
        helpList += nlSplit
        if self.defaultParamList:
            helpList.append('   Default: %s' % str(self.defaultParamList[0].defValueList))
        return helpList

class Command(object):
    """!For defining a command
    """
    def __init__(self, name, paramList=None, qualifierList=None, help='', callFunc=None, minParAmt=0):
        """!Inputs
        @param[in] name  command name
        @param[in] paramList  list of parameters (ParamBase objects) in the expected order, or None if no parameters
        @param[in] qualifierList  list of qualifiers (Qualifier objects), or None if no qualifiers
        @param[in] help  help string
        @param[in] callFunc  function to call that takes parsed command as an argument
        @param[in] minParAmt  the minimum number of arguments requried for this command
        """
        self.name = name
        self.paramList = paramList or []
        self.qualifierList = qualifierList or []
        self.help = help
        self.callFunc = callFunc
        self.minParAmt = int(minParAmt)

    def getFullHelp(self):
        """!Return full help as a list of strings
        """
        #paramNames = " ".join(param.name for param in self.paramList)
        dataList = self.getBriefHelp()
        if self.paramList:
            dataList.append('')
            dataList.append("Parameters:")
            for param in self.paramList:
                for helpLine in param.help:
                    dataList.append("   %s" % (helpLine,))
        if self.qualifierList:
            dataList.append('')
            dataList.append("Qualifiers:")
            for qual in self.qualifierList:
                for helpLine in qual.help:
                    dataList.append("   %s" % (helpLine))
        return dataList

    def getBriefHelp(self):
        """!Return brief help as a list of strings
        """
        dataList = []
        line1 = ''
        if self.name != None: # subcommands will have a name == None.
            line1 += self.name.upper() + ' '
        line1 += ' '.join([x.name for x in self.paramList])
        dataList.append(line1)
        dataList.append('   ' + self.help)
        #paramNames = " ".join(param.name for param in self.paramList)
        return dataList


class SubCommand(Command):
    """!First paramSlot has the name of this subcommand.  Used for cases where sub commands
    of a command require unique parsing.
    """
    def __init__(self,
        selfKeyword,
        paramList = None,
        qualifierList = None,
        help = '',
        callFunc = None,
        minParAmt = 0,
    ):
        """!Inputs
        @param[in] selfKeyword  a Keyword object
        @param[in] paramList  list of any additional parameters (ParamBase objects) in the expected order, or None if no parameters
        @param[in] qualifierList  list of qualifiers (Qualifier objects), or None if no qualifiers
        @param[in] help  help string
        @param[in] callFunc  function to call that takes parsed command as an argument
        @param[in] minParAmt  the minimum number of arguments requried for this command
        """
        minParAmt += 1 # the selfKeyword is (under the hood) a required parameter
        # not including it in the minParAmt because this is command-like...
        paramList = paramList or []
        # generate a self-param unit, since this sub-command is both a parameter and a command
        paramList = [KeywordParam(name = selfKeyword.name, keywordDefList=[selfKeyword])] + paramList
        self.subCommandName = selfKeyword.name # for help to print correctly
        Command.__init__(self,
            name = None, # must be None for nice help printing.
            paramList = paramList,
            qualifierList = qualifierList,
            help = help,
            callFunc = callFunc,
            minParAmt = minParAmt,
        )


class CommandWrapper(object):
    """!An outer wrapper for commands with alternate parsing syntaxes, eg 'SET'
    """
    def __init__(self,
        name,
        subCmdList = None,
        help = '',
    ):
        """!Inputs
        @param[in] name  command name (eg 'set')
        @param[in] subCmdList  a list of SubCommand objects providing definitions for alternate command
            validation.
        @param[in] help  help string
        """
        self.name = name
        #self.name = name # hack for now, for help printing
        self.subCmdList = subCmdList or []
        self.help = help

    def getFullHelp(self):
        """!Return full help as a list of strings
        """
        dataList = []
        for subCmd in self.subCmdList:
            subList = subCmd.getFullHelp()
            subList[0] = self.name.upper() + " " + subList[0]
            dataList += subList
        return dataList

    def getBriefHelp(self):
        """!Return brief help as a list of strings
        """
        dataList = []
        for subCmd in self.subCmdList:
            subList = subCmd.getBriefHelp()
            subList[0] = self.name.upper() + " " + subList[0]
            dataList += subList
        return dataList
