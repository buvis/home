#!/usr/bin/env bash

function convert-time()
{
    local FROMTIME=$1
    local FROMTZ=$2
    local TOTZ=$3
    local TOTIME=$(TZ=$TOTZ date --date="TZ=\"$FROMTZ\" $FROMTIME")
    echo "$FROMTIME $FROMTZ is $TOTIME $TOTZ"
}
