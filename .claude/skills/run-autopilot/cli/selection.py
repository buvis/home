#!/usr/bin/env python3
"""selection.py - which PRD the autopilot picks next.

PURE: takes directory LISTINGS, never paths, so the decision is testable
without a filesystem and the caller owns the I/O.

    sequence(name)            -> the `00XXX-` prefix as an int, or None
    selectable(names)         -> the selectable subset, lowest sequence first
    select(wip, backlog)      -> (basename, source)

`hold/` is absent from the signature ON PURPOSE - that IS the parked/deferred
exclusion. A function that cannot see `hold/` cannot pick from it, which is a
stronger guarantee than a rule saying it must not.

Two kinds of name are skipped rather than ordered last:

- Anything not ending `.md`.
- Anything without a `00XXX-` prefix. `dev/local/prds/FASTTRACK-PLAN-v5.md` is
  unnumbered precisely so "no PRD picker ever selects it"; honoring that is the
  documented contract, not an accident.

A six-digit prefix does not match either, so it is skipped rather than
silently truncated to five and mis-ordered.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

_SEQUENCE_RE = re.compile(r"^(\d{5})-")


def sequence(name: str) -> int | None:
    """Return the `00XXX-` prefix of `name` as an int, or None if it has none."""
    match = _SEQUENCE_RE.match(name)
    return int(match.group(1)) if match else None


def selectable(names: Iterable[str]) -> list[str]:
    """Return the selectable entries of `names`, lowest sequence number first.

    Ties on sequence (two PRDs sharing a number) break on the full name, so
    the order is total and two calls on the same directory agree.
    """
    picks = [n for n in names if n.endswith(".md") and sequence(n) is not None]
    return sorted(picks, key=lambda n: (sequence(n) or 0, n))


def select(wip: Iterable[str], backlog: Iterable[str]) -> tuple[str | None, str]:
    """Return (basename, source) for the next PRD.

    `source` is "wip" (resume in place), "backlog" (needs the verified move to
    `wip/`), or "drained" with a None basename when neither holds a selectable
    PRD. wip wins whole, not per-number: an in-progress PRD is finished before
    a lower-numbered backlog one is started.
    """
    in_wip = selectable(wip)
    if in_wip:
        return in_wip[0], "wip"
    in_backlog = selectable(backlog)
    if in_backlog:
        return in_backlog[0], "backlog"
    return None, "drained"
