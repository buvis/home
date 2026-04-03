#!/bin/bash
# List available PRD files from wip and backlog directories

echo "=== PRDs in Progress (wip) ==="
if [ -d "dev/local/prds/wip" ] && [ "$(ls -A dev/local/prds/wip 2>/dev/null)" ]; then
    ls -1 dev/local/prds/wip/
else
    echo "(none)"
fi

echo ""
echo "=== PRDs in Backlog ==="
if [ -d "dev/local/prds/backlog" ] && [ "$(ls -A dev/local/prds/backlog 2>/dev/null)" ]; then
    ls -1 dev/local/prds/backlog/
else
    echo "(none)"
fi

echo ""
echo "=== Completed PRDs (done) ==="
if [ -d "dev/local/prds/done" ] && [ "$(ls -A dev/local/prds/done 2>/dev/null)" ]; then
    ls -1 dev/local/prds/done/
else
    echo "(none)"
fi
