from __future__ import division, absolute_import
"""A command parser for DCL commands (VMS operating system), especially those used by the APO TCC.

@note:
* any parameter containing forward slashes (eg a file) must be quoted
* quotes are removed during parsing
* parameters cannot be negated

todo:
sort out default behavior when default is a list...
error handling
"""
import itertools
import collections

from RO.StringUtil import strFromException
from RO.StringUtil import unquoteStr
import RO.Alg.MatchList
import pyparsing as pp



class ParseError(Exception):
    pass

def getUniqueAbbrevIndex(keyword, matchList):
    """!Return the index of keyword in list allowing unique abbreviations and independent of case.

    @param[in] keyword  a possibly abbreviated Keyword
    @param[in] matchList  a list of strings to match Keyword to.

    @return integer, the index of the list holding the correct match
    """
    match = RO.Alg.MatchList(valueList=matchList).getUniqueMatch(keyword)
    return matchList.index(match)

def makeGenericCmd():
    """!Constructs a generic TCC command from pyparsing elements.
    Upon parsing, will find a command verb and collections of both
    qualifiers and parameters.
    """
    # Pyparsing Grammar
    point = pp.Literal( "." )
    e     = pp.CaselessLiteral( "E" )
    number = pp.Combine( pp.Word( "+-"+pp.nums, pp.nums ) +
        pp.Optional( point + pp.Optional( pp.Word( pp.nums ) ) ) +
        pp.Optional( e + pp.Word( "+-"+pp.nums, pp.nums ) ) )
    keyword = pp.Word(pp.alphas + pp.alphanums, pp.alphas + '_:.' + pp.alphanums) #
    ddQuoted = pp.Literal('"').suppress() + pp.dblQuotedString + pp.Literal('"').suppress() # double double quotes
    escQuoted = pp.Literal('\"').suppress() + pp.CharsNotIn('"') + pp.Literal('\"').suppress()
    enteredString = ddQuoted.setParseAction(pp.removeQuotes) | escQuoted # quotes removed!
    datum = pp.Group(enteredString) | pp.Group(number) | pp.Group(keyword)
    datumList = pp.delimitedList(datum)
    datumParList = pp.Literal("(").suppress() + datumList + pp.Literal(")").suppress()
    # try to parse with parentheses first, for cases like foo=(1,2,3), bar=1
    datumOptParList = datumParList | datumList
    # the command verb, may be ^Y, etc.
    cmdVerb = pp.Word(pp.alphas + '^').setResultsName('cmdVerb')
    # everything after a "!", is a comment
    comment = pp.Literal("!") + pp.restOfLine
    # qualifier specific parsing
    qualKey = pp.Literal("/").suppress() + keyword
    qualListValues = pp.Group(qualKey + pp.Literal("=").suppress() + pp.Group(datumOptParList))
    qualifier = qualListValues | (pp.Group(qualKey) + pp.Optional(pp.Literal("=") + pp.Literal("(") + pp.Literal(")"))) # incase of empty list...


    keywordValue = pp.Group(keyword + pp.Literal("=").suppress() + datum) # ::=> blah = 5
    keywordListValues = pp.Group(keyword + pp.Literal("=").suppress() \
        + pp.Group(datumOptParList) ) # ::=> blah = 5,4,3
    keywordForceParListVal = pp.Group(keyword + pp.Literal("=").suppress() \
        + datumParList)
    keyValPairList = pp.Group(pp.delimitedList(keywordValue ^ keywordForceParListVal))#::=> blah=5, blabber=(3,4), ...
    quotedStringParam = pp.Regex(r'"(?:\\\"|\\\\|[^"])*"') # to handle escaped quotes in broadcast/talk command
    param =  keyValPairList |  keywordListValues | pp.Group(quotedStringParam) | pp.Group(datumList) #^ keywordList ^ keywordListValues


    # everything together
    genericCmd = cmdVerb + pp.ZeroOrMore(qualifier.setResultsName("qualifiers", True) ^ \
        param.setResultsName('parameters', True))
    genericCmd.ignore(comment)

    return genericCmd


class CmdParser(object):
    """!A class that holds command definitions, and can parse tcc commands
    """
    def __init__(self, cmdDefList):
        """!Construct a CmdParser

        @param[in] cmdDefList  a list of command definititions
            (Command or CommandWrapper Objects defined in parseObjects),
            containing all commands to be recognized by this parser.
        """
        self.genericCmd = makeGenericCmd() # pyparsing
        # dict of cmd verb: cmd definition
#         self.checkDefaults(cmdDefList)
        self.cmdDefDict = dict((cmdDef.name.lower(), cmdDef) for cmdDef in cmdDefList)
        self.cmdMatchList = RO.Alg.MatchList(valueList=self.cmdDefDict.keys())

    def parseLine(self, inputLine):
        """!Parse an input line, return a ParsedCmd Object

        @param[in] inputLine  line to parse
        @return parsedCmd, a ParsedCmd object
        @throw ParseError if command cannot be parsed.
        """
        # try:
        # pyparsing, returns object with
        # verb, params, quals as previously defined attributes
        ppOut = self.genericCmd.parseString(inputLine, parseAll=True)
        # find correct command definition
        cmdNames = self.cmdMatchList.getAllMatches(ppOut.cmdVerb)
        if len(cmdNames) == 0:
            raise ParseError("Unrecognized command %r" % (ppOut.cmdVerb,))
        elif len(cmdNames) > 1:
            listStr = ", ".join(cmdNames)
            raise ParseError("%r not unique; could be any of %s" % (ppOut.cmdVerb, listStr))
        cmdName = cmdNames[0]

        cmdDef = self.cmdDefDict[cmdName]
        parsedCmd = ParsedCmd(cmdDef.name) # initialize

        if hasattr(cmdDef, "subCmdList"):
            # find the secondary command in the cmdList (the first name in the first slot)
            # alternate parsing enabled in this case
            secCmd = ppOut.parameters[0][0][0]
            # match with the name of the first parameter in the first slot
            ind = getUniqueAbbrevIndex(
                secCmd,
                [item.paramList[0].paramElementList[0].name for item in cmdDef.subCmdList]
            )
            # (re) set cmdDef to this and carry on
            cmdDef = cmdDef.subCmdList[ind]

        ################## add and validate qualifiers. #################
        # set value = None if no value was passed, values are always a list if not None
        for qual in ppOut.qualifiers:
            boolValue = True
            qualName = qual[0]
            try:
                # if a value was passed, it will be in index=1
                #qualVal = qual[1][0]
                qualVal = [q[0] for q in qual[1]]
            except IndexError:
                # there was no value passed
                qualVal = None
            try:
                ind = getUniqueAbbrevIndex(qualName, [item.name for item in cmdDef.qualifierList])
            except ValueError:
                # match wasn't found, try again using negated qualifiers (where allowed)
                nameList=[]
                for tempQual in cmdDef.qualifierList:
                    if tempQual.negatable:
                        nameList.append('No' + tempQual.name)
                    else:
                        nameList.append(tempQual.name)
                ind = getUniqueAbbrevIndex(qualName, nameList)
                boolValue = False # we just encountered a negated qualifier
            qualDef = cmdDef.qualifierList[ind]

            if qualDef.valType == None:
                # this is a flag-like qualifier with no values
                if qualVal != None:
                    raise ParseError('Expected no value for qualifier: %s' % (qualDef.name,))
                parsedCmd.addQual(qualDef.name, boolValue, boolValueDefaulted=False)
            elif callable(qualDef.valType):
                # this qualifier accepts a simple valueList of castable elements
                if qualVal == None:
                    # no value was passed, set the default (which may in fact be empty)...
                    parsedCmd.addQual(
                        qualDef.name,
                        boolValue,
                        boolValueDefaulted=False,
                        valueList = qualDef.defValueList,
                        valueListDefaulted = True ,
                    )
                else:
                    # values were passed with this qualifier...check they cast correctly
                    try:
                        valueList = [qualDef.valType(item) for item in qualVal]
                    except ValueError:
                        raise ParseError('Could not cast values %s to correct type %s' % \
                            (qualVal, qualDef.valType))
                    else:
                        # check if amount of values are allowed
                        if qualDef.numValueRange[1] == None:
                            if len(valueList) < qualDef.numValueRange[0]:
                                raise ParseError('Not Enough values for qualifer %s, got %i, expected at least %i' \
                                    % (qualDef.name, len(valueList), qualDef.numValueRange[0]))
                        else:
                            if not (qualDef.numValueRange[0] <= len(valueList) <= qualDef.numValueRange[1]):
                                raise ParseError('Invalid number of values for qualifier %s.' \
                                     'Got: %i, should be between %i and %i' % \
                                     (
                                        qualDef.name, len(valueList),
                                        qualDef.numValueRange[0],
                                        qualDef.numValueRange[1])
                                     )
                        # amount of values is ok
                        parsedCmd.addQual(
                            qualDef.name,
                            boolValue,
                            boolValueDefaulted=False,
                            valueList = valueList,
                            valueListDefaulted = False,
                        )
            else:
                # this qualifier has values that belong to a specific set of keywords
                if qualVal == None:
                    # no value was passed, add the default value list (which may be empty)
                    parsedCmd.addQual(
                        qualDef.name,
                        boolValue,
                        boolValueDefaulted=False,
                        valueList = qualDef.defValueList,
                        valueListDefaulted = True ,
                    )
                else:
                    # search each value for it's full (non-abbreviated) representation
                    # in the parsedCmd valType field
                    valueList = [RO.Alg.MatchList(valueList=qualDef.valType).getUniqueMatch(keyword) for keyword in qualVal]
                    # check if amount of values are allowed
                    if qualDef.numValueRange[1] == None:
                        if len(valueList) < qualDef.numValueRange[0]:
                            raise ParseError('Not Enough values for qualifer %s, got %i, expected at least %i' \
                                % (qualDef.name, len(valueList), qualDef.numValueRange[0]))
                    else:
                        if not (qualDef.numValueRange[0] <= len(valueList) <= qualDef.numValueRange[1]):
                            raise ParseError('Invalid number of values for qualifier %s. ' \
                                'Got: %i, should be between %i and %i' % \
                                (
                                    qualDef.name, len(valueList),
                                    qualDef.numValueRange[0],
                                    qualDef.numValueRange[1])
                                )
                    parsedCmd.addQual(
                        qualDef.name,
                        boolValue,
                        boolValueDefaulted=False,
                        valueList = valueList,
                        valueListDefaulted = False,
                    )

        # now append the remaining (un commanded) qualifiers
        for qual in cmdDef.qualifierList:
            if qual.name.lower() not in parsedCmd.qualDict:
                parsedCmd.addQual(
                    qual.name,
                    boolValue = qual.defBoolValue,
                    boolValueDefaulted = True,
                    valueList = qual.defValueList,
                    valueListDefaulted = True,
                )

        ############### add and validate parameters ######################
        if len(cmdDef.paramList) < len(ppOut.parameters):
            raise ParseError('Too many parameters for command %r' % (inputLine,))
        if len(ppOut.parameters) < cmdDef.minParAmt:
            raise ParseError('Too few parameters for command %r' % (inputLine,))
        for paramSlotDef, paramSlotGot in itertools.izip_longest(cmdDef.paramList, ppOut.parameters):
            paramSlotName = paramSlotDef.name
            paramList = []
            if not paramSlotGot:
            # if got no slot, look for a default
                if paramSlotDef.defaultParamList: # is not None:
                    for paramDef in paramSlotDef.defaultParamList: # default list may be empty
                        validatedName = paramDef.name # may be None, if not a keyword type parameter
                        valueList = paramDef.defValueList # may be None, if not specified in definitions
                        if validatedName:
                            # keyword type parameter
                            paramList.append(ParsedKeyword(validatedName, valueList, defaulted=True))
                            parsedCmd.addParam(paramSlotName, valueList = paramList, defaulted=True, boolValue=False)
                        elif valueList is not None:
                            # param is a simple value list
                            paramList = valueList
                            parsedCmd.addParam(paramSlotName, valueList = paramList, defaulted=True, boolValue=False)
                        else:
                            # no defaults were defined, do nothing
                            raise RuntimeError("Conor believes this is a bug, investigate")
                            #continue
                            #parsedCmd.addParam(paramSlotName, valueList=None)
                else:
                    # no defaults specified, add an empty entry in the parsed parameter dictionary
                    parsedCmd.addParam(paramSlotName, valueList=(), boolValue=False)
            elif paramSlotDef.matchList:
                # got a slot, and it is keywords parse it
                if paramSlotDef.numParamRange[1] == None:
                    # no upper bound on range
                    correctParamAmt = paramSlotDef.numParamRange[0] <= len(paramSlotGot)
                else:
                    # there is an upper bound
                    correctParamAmt = (paramSlotDef.numParamRange[0] <= len(paramSlotGot) <= paramSlotDef.numParamRange[1])
                if not correctParamAmt:
                    raise ParseError('Incorrect amount of parameters for command %r' % (inputLine,))
                for paramGot in paramSlotGot:
                    paramDef = paramSlotDef.paramElementList[getUniqueAbbrevIndex(paramGot.pop(0), paramSlotDef.matchList)]
                    validatedName = paramDef.name
                    # are values associated with this keyword? They will be left over in paramGot
                    if paramGot:
                        # values were passed by user in association with this keyword
                        if paramDef.numValueRange[1] == None:
                            # no upper value limit
                            correctValueAmt = paramDef.numValueRange[0] <= len(paramGot)
                        else:
                            # there is an upper limit
                            correctValueAmt = paramDef.numValueRange[0] <= len(paramGot) <= paramDef.numValueRange[1]
                        if not correctValueAmt:
                            raise ParseError('Incorrect amt of values passed for %s param. Commanded: %r ' % (paramDef.name, inputLine))
                        # zero (p[0]) index is a pyparsing definition, could figure out how to fix it...but for now it works
                        valueList = [paramDef.castVals(p[0]) for p in paramGot]
                    else:
                        # no values passed by user, but a default value list is
                        # defined for this parameter.
                        valueList = paramDef.defValueList # will be empty if no default list
                    defaulted = True if valueList else False
                    paramList.append(ParsedKeyword(validatedName, valueList, defaulted))
                parsedCmd.addParam(paramSlotName, valueList = paramList)
            else:
                # this is a simple value (non-keyword) parameter
                # treat this slot as a single list of values
                # do this because of pyparsing behavior doesn't wrap in an outer list
                # unless it is a list of keyword=valueList
                paramGot = paramSlotGot
                assert len(paramSlotDef.paramElementList) == 1
                paramDef = paramSlotDef.paramElementList[0]
                if paramDef.numValueRange[1] == None:
                    # no upper value limit
                    correctValueAmt = paramDef.numValueRange[0] <= len(paramGot)
                else:
                    # there is an upper limit
                    correctValueAmt = paramDef.numValueRange[0] <= len(paramGot) <= paramDef.numValueRange[1]
                if not correctValueAmt:
                    raise ParseError('Too many elements in parameter slot for command %r' % (inputLine,))
                validatedName = None
                if paramGot[0][0]=='"'==paramGot[0][-1]:
                    # special case, this parameter is a quoted string, only used in
                    # talk and broadcast commands; dequote and send along
                    paramList = [paramDef.castVals(unquoteStr(paramGot[0]))]

                else:
                    paramList = [paramDef.castVals(par) for par, in paramGot]
                parsedCmd.addParam(paramSlotName, valueList=paramList)

        parsedCmd.addCall(cmdDef.callFunc)
        return parsedCmd
        # except Exception as e:
        #     raise ParseError("Could not parse %r: %s" % (inputLine, strFromException(e)))

class ParsedCmd(object):
    def __init__(self, cmdVerb):
        """!A class for holding a parsed command.

        @param[in] cmdVerb  the command name, string.
        """
        self.qualDict = {} # dict of qual name (lowercase): Qualifier object
        self.paramDict = collections.OrderedDict()
        self.callFunc = None
        self.cmdVerb = cmdVerb

    def addCall(self, callFunc):
        """!Add a callable to be called after successful parsing

        @param[in] callFunc  a callable
        """
        self.callFunc = callFunc

    def addParam(self, name, valueList, defaulted=False, boolValue=True):
        """!Add a param to the current paramSlot.
        Inputs:
        name: a the param name
        valueList: the associated list of value
        defaulted: was the parameter defaulted?
        """
        # add in keword value functionality here
        param = ParsedPar(name, valueList, defaulted, boolValue)
        self.paramDict[name.lower()] = param

    def addQual(self,
            name,
            boolValue,
            boolValueDefaulted,
            valueList=None,
            valueListDefaulted=False
        ):
        """!Add a qualifier.
        @param[in] name  the qualifier name
        @param[in] boolValue  bool, was it commanded?
        @param[in] boolValueDefaulted  bool, was this passed explicitly by the user
            or added by default by the parser
        @param[in] valueList  any value list associated with this qualifier
        @param[in] valueListDefaulted  was the list explicitly passed by the user or did the parser
            read and apply this list as a default as indicated in a command definition.
        """
        qual = ParsedQual(name, boolValue, boolValueDefaulted, valueList, valueListDefaulted)
        self.qualDict[name.lower()] = qual

    def printData(self):
        """!Print contents of parsed command, for diagnostic purposes
        """
        print "Command: %s" % (self.cmdVerb,)
        print "  params:"
        for par in self.paramDict.itervalues():
            print "   ", par
        print "  quals:"
        qualNameList = sorted(self.qualDict.keys())
        for qualName in qualNameList:
            qual = self.qualDict[qualName]
            print "   ", qual

    def __str__(self):
        """!Bit of a hack...for now
        """
        self.printData()
        return ''

class ParsedQual(object):
    def __init__(self, name, boolValue, boolValueDefaulted, valueList=None, valueListDefaulted=False):
        """!A parsed qualifier object

        @param[in] name  the qualifier name
        @param[in] boolValue  bool, was it commanded?
        @param[in] boolValueDefaulted  if True the user did not specify this qualifier,
            so the boolValue of this qualifier is the default
        @param[in] valueList  any value list associated with this qualifier
        @param[in] valueListDefaulted  if True, the user did not specify values for this qualifier,
            so the valueList is the default
        """
        self.name = name
        self.boolValue = bool(boolValue)
        self.boolValueDefaulted = bool(boolValueDefaulted)
        self.valueList = valueList or []
        self.valueListDefaulted = bool(valueListDefaulted)

    def __repr__(self):
        return "%s(name=%s, boolValue=%s, valueList=%s, boolValueDefaulted=%s, valueListDefaulted=%s)" % \
            (type(self).__name__, self.name, self.boolValue, self.valueList, self.boolValueDefaulted, self.valueListDefaulted)


class ParsedKeyword(object):
    def __init__(self, keyword, valueList, defaulted=False):
        """!An object for holding parsed parameters that are of the form keyword=valueList

        @param[in] keyword  the keyword
        @param[in] valueList  the list of value(s)
        @param[in] defaulted  was the value list defaulted?

        note: add some interactivity to this to make it useful down the line?...
        """
        self.keyword = keyword
        self.valueList = valueList
        self.defaulted = defaulted

    def __repr__(self):
        return "%s(keyword=%r, valueList=%r, defaulted=%r)" % (type(self).__name__, self.keyword, self.valueList, self.defaulted)


class ParsedPar(object):
    def __init__(self, name, valueList, defaulted=False, boolValue=True):
        """!A parsed parameter object

        @param[in] name  paramName
        @param[in] valueList  any list of value(s) associated with this parameter
        @param[in] defaulted  boolean. Indicate whether this parameter was passed by default
        @param[in] boolValue  boolean. True if it was commanded (analogous to a qualifier)
        """
        self.name = name
        self.valueList = valueList
        self.defaulted = bool(defaulted)
        self.boolValue = bool(boolValue)

    def __repr__(self):
        return "%s(valueList=%r, defaulted=%r, boolValue=%r)" % (type(self).__name__, self.valueList, self.defaulted, self.boolValue)
