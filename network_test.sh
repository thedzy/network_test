#!/usr/bin/env bash

/usr/bin/tput reset
printf '\e[3J'

##########################################################################################
# network_test.sh
# Author: Shane Young
# Date: 2025-02-11
# Revision:	1.0
# Platform: MacOS
#
# Description
# Simple webcrawler to see if communication is interrupted
#
# Versions
# 1. Crawl a site and report
#
##########################################################################################
#
# Exit Codes
#
##########################################################################################

##########################################################################################
# Environment setup
################

# Global Variables
BASEPATH="$(dirname $0)"
BASENAME="$(basename $0)"

# Create temporary and working directory
WRKDIR="$TMPDIR"
TMPDIR="/tmp/$BASENAME."$(openssl rand -hex 12)
/bin/mkdir -p -m 777 "$TMPDIR"

# Turn off line wrapping:
#printf '\033[?7l'
# Turn on  line wrapping:
#printf '\033[?7h'

# Set window size ex. 100w x 40h
#printf '\033[8;40;100t'

# Set window Title
printf "\033]0;${BASENAME%%.*}\007"

# Hide the cursor for the run of the script
/usr/bin/tput civis

##########################################################################################
# Traps
################

function exit_trap() {
    printf '\n\n'
    kill $WGET_PID 2>/dev/null && echo Killed wget
    kill $TAIL_PID1 2>/dev/null && echo Killed tailing of log
    kill $TAIL_PID2 2>/dev/null && echo Killed tailing of error log
    /usr/bin/tput cnorm
}
trap exit_trap TERM INT

##########################################################################################
# Functions
################

# Function to print text in colour
function colour() {
    local DATE=$(/bin/date)
    local COLOUR_CODE="$1"
    shift
    local LEVEL="$1"
    shift
    local MESSAGE="$*"
    printf "\033[%sm%s [ %-8s] %s\033[0m\n" "${COLOUR_CODE}" "$DATE" "${LEVEL}" "$MESSAGE"
}

# Function for logging
function logging.debug() {
    colour "90" DEBUG $*
}

function logging.info() {
    colour "92" INFO $*
}

function logging.warning() {
    colour "93" WARNING $*
}

function logging.error() {
    colour "91" ERROR $*
}

function logging.critical() {
    colour "97;41" CRITICAL $*
}

function echo() {
    logging.info "$@"
}

##########################################################################################
# Main
################

WEBSITE=${1-https://www.apple.com}
LOGFILE=/tmp/wget.log
REJECTED_LOGFILE=/tmp/wget_rejected.log

# Clean up file/folders
[ -e $LOGFILE ] && echo /bin/rm $LOGFILE
[ -e $REJECTED_LOFFILE ] && echo /bin/rm $REJECTED_LOGFILE

logging.info "Downloading $WEBSITE"

logging.info wget --keep-session-cookies --wait=1 --random-wait --limit-rate=50k -nd --delete-after -r -np -nc -l 1000 -o $LOGFILE -P $TMPDIR/ --rejected-log=$REJECTED_LOGFILE $WEBSITE &
/opt/homebrew/bin/wget --keep-session-cookies --wait=1 --random-wait --limit-rate=50k -nd --delete-after -r -np -nc -l 1000 -o $LOGFILE -P $TMPDIR/ --rejected-log=$REJECTED_LOGFILE $WEBSITE &
WGET_PID=$!

sleep 1
#/usr/bin/tail -f "$LOGFILE" | /usr/bin/egrep '^--.*$|^HTTP request sent.*$'
/usr/bin/tail -f "$LOGFILE" | /usr/bin/egrep --line-buffered '^--.*$|^HTTP request sent.*$' | while read -r line; do
    if echo "$line" | /usr/bin/egrep -q "\.\.\.\s+4[0-9]{2}"; then
        logging.error "$line" # 4xx errors
    else
        logging.info "$line"
    fi
done

wait

echo 0
