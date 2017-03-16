from __future__ import division, absolute_import

import datetime
import telnetlib
import os
import time

tcsHost = "c100tcs"
tcsPort = 4243
statusRefreshRate = 0.25 # seconds
filename = "errorlog.txt"
TN = telnetlib.Telnet(tcsHost, tcsPort)

stateMap = {1: "TS_IDLE", 2: "TS_TRACKING", 3: "TS_SLEWING", 4: "TS_STOP"}

statusPieces = ["RERR", "DERR", "STATE", "HA", "DEC"]

def initFile():
    if not os.path.exists("./%s"%filename):
        with open(filename, "w") as f:
            f.write("Timestamp RERR DERR STATE HA DEC\n")


def queryTCS():
    """Query the TCS record stuff
    """
    timestamp = datetime.datetime.now().isoformat()
    values = []
    for statusPiece in statusPieces:
        TN.write(statusPiece+"\r\n")
        value = TN.read_until("\n", 0.5)
        value = value.strip()
        if not value:
            value = "?"
        values.append(value)
    if values[2] == "?" or int(values[2]) != 2:
        return # only record if in tracking state
    with open(filename, "a") as f:
        f.write("%s %s %s %s %s %s\n"%tuple([timestamp]+values))

if __name__ == "__main__":
    initFile()
    while True:
        queryTCS()
        time.sleep(statusRefreshRate)
