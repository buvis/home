"""cli/notify_out.py - loop-exit notifications (PRD 00106).

Self-contained: nothing here imports from ~/.claude/hooks/. Delivery
shells to the same `notify.py --send <title> <body>` command the bash
wrapper used, so channel routing and its fallbacks stay in one place;
this module only guarantees the loop-side contract - a notification can
NEVER block or fail the loop (stderr suppressed, exit status ignored,
and a hard timeout so a wedged notifier cannot hold the loop open; the
bash call had no timeout, which was a latent hang).

Notification sites are the loop's exit and wait branches exactly as in
bash (⏳ mem/limit waits, ⏸ operator pause, ⚠️ paused/died/drift/park
guard, ⏭ park, ✅ drained) - once per event, never per phase (the
notify race class, PRD 00106 risk list).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

NOTIFY_SCRIPT = Path.home() / ".claude" / "hooks" / "notify.py"
TIMEOUT_SECS = 30


def notify(title: str, body: str, script: Path | None = None) -> None:
    if script is None:
        script = NOTIFY_SCRIPT
    try:
        subprocess.run(
            [sys.executable, str(script), "--send", title, body],
            stderr=subprocess.DEVNULL,
            timeout=TIMEOUT_SECS,
        )
    except (OSError, subprocess.SubprocessError):
        pass
