#!/bin/bash

PID=""
pid=$(/bin/ps -e -ww -o pid,user,command | egrep -v 'awk|grep' | awk "/python runLCOTCC.py/ {print \$1}")
PID=$pid
echo $PID
kill -9 $PID

sleep 2

python runLCOTCC.py &