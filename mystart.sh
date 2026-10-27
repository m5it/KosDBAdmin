#!/bin/bash
# Script to start program trough .venv. It also check if .venv exists.
# Link to ex.: /usr/local/bin/kdba
# Ex. link: ln -s $(pwd)/mystart.sh /usr/local/bin/kdba
# Then you can run like:
# xenco -h

RP=$(which $0)
RP=$(readlink -f $RP)
RP=$(dirname $RP)
#
if [[ ! -d $RP"/.venv" ]]; then
	echo "Required to install requirements.txt to .venv directory"
	exit 1
fi

#
$RP/.venv/bin/python $RP/main.py $@
