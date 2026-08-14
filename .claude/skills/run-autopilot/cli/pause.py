"""cli/pause.py - the operator pause marker (PRD 00106).

Ports the wrapper's pause branch (PRD 00014): `touch
<ap_dir>/pause-requested` is the sanctioned "let me in" signal, honored
at the next session boundary. The marker is consumed so a later loop
run starts normally; the loop then prints the resume runbook, notifies
once, and exits 0 (stall-not-pause policy, PRD 00017 - the loop stops
spawning without wedging).
"""

from __future__ import annotations

from pathlib import Path

MARKER = "pause-requested"


def consume_pause(autopilot_dir: Path) -> bool:
    """True when the pause marker existed; it is removed either way."""
    try:
        (autopilot_dir / MARKER).unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False
