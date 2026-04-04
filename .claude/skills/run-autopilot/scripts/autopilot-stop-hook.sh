#!/bin/bash
# Stop hook for autopilot session loop.
# When dev/local/autopilot/signal exists, autopilot is done with current PRD.
# Walks up process tree to find and SIGINT the claude process so the shell loop can restart.
if [ -f dev/local/autopilot/signal ]; then
  pid=$PPID
  while [ "$pid" -gt 1 ]; do
    if ps -p "$pid" -o comm= 2>/dev/null | grep -q claude; then
      kill -INT "$pid"
      exit 0
    fi
    pid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')
  done
fi
