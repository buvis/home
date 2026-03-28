#!/bin/bash
# Stop hook for autopilot session loop.
# When .local/autopilot/signal exists, autopilot is done with current PRD.
# Returns continue:false to exit the session so the shell loop can restart.
if [ -f .local/autopilot/signal ]; then
  echo '{"continue": false}'
  kill -INT $PPID 2>/dev/null
fi
