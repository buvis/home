#!/usr/bin/env python3
"""fablectl.py - sole writer of the Fable rescue ledger.

CLI:
    python3 fablectl.py <ledger> request <prd> <task_id> <task_name> <batch_id> <json>
    python3 fablectl.py <ledger> decide  <prd> approved|rejected
    python3 fablectl.py <ledger> consume <prd>
    python3 fablectl.py <ledger> show    <prd>

One request per PRD, ever. The transition table is requested -> approved or
rejected, and approved -> consumed; every other mutation is refused with exit 3
and leaves the ledger byte identical. A bad argument exits 1, a ledger that is
present but unreadable exits 2. An ABSENT ledger is not damage - it means no
request has been filed yet, so `show` answers {} and the mutating verbs refuse.
"""

from __future__ import annotations

import datetime
import fcntl
import json
import sys
from pathlib import Path
from typing import Any

from statectl import atomic_write

TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
JUSTIFICATION_FIELDS = ("problem", "attempts", "impact")
ARITY = {"request": 5, "decide": 2, "consume": 1, "show": 1}
USAGE = (
    "usage: fablectl.py <ledger> "
    "request <prd> <task_id> <task_name> <batch_id> <json>"
    " | decide <prd> approved|rejected | consume <prd> | show <prd>"
)


class BadArgument(Exception):
    """Bad arguments (exit 1)."""


class LedgerError(Exception):
    """Ledger present but unreadable (exit 2)."""


class RefusedError(Exception):
    """Mutation outside the transition table (exit 3)."""


def now_stamp() -> str:
    """UTC, explicitly - a naive now() is only right on a UTC host."""
    return datetime.datetime.now(datetime.timezone.utc).strftime(TS_FORMAT)


def read_ledger(ledger_path: Path) -> tuple[bytes | None, dict[str, Any]]:
    """Return (raw_bytes, entries); an absent ledger is (None, {}), not an error.

    Raw bytes come back alongside the parsed entries so a mutation can write a
    byte-for-byte `.bak`. Anything present but unusable - undecodable bytes, bad
    JSON, a non-object top level, an entry that is not an object or carries no
    string status - raises LedgerError to drive the exit-2 contract.
    """
    try:
        raw = ledger_path.read_bytes()
    except FileNotFoundError:
        return None, {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as err:
        raise LedgerError(f"ledger is not valid JSON ({ledger_path}): {err}") from err
    if not isinstance(data, dict):
        raise LedgerError(f"ledger is not a JSON object: {ledger_path}")
    for prd, entry in data.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("status"), str):
            raise LedgerError(f"ledger entry is damaged ({ledger_path}): {prd}")
    return raw, data


def parse_justification(raw: str) -> dict[str, Any]:
    """Parse the justification argument: an object with three prose fields."""
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as err:
        raise BadArgument(f"justification is not valid JSON: {err}") from err
    if not isinstance(value, dict):
        raise BadArgument("justification must be a JSON object")
    for field in JUSTIFICATION_FIELDS:
        if not isinstance(value.get(field), str):
            raise BadArgument(f"justification.{field} must be a string")
    return value


def build_entry(rest: list[str]) -> dict[str, Any]:
    """Build the new entry from `request`'s own argv, before any file is touched."""
    _prd, task_id, task_name, batch_id, justification = rest
    return {
        "status": "requested",
        "task_id": task_id,
        "task_name": task_name,
        "requested_at": now_stamp(),
        "batch_id": batch_id,
        "justification": parse_justification(justification),
        "decided_at": None,
        "consumed_at": None,
    }


def apply_verb(entries: dict[str, Any], verb: str, prd: str, payload: Any) -> None:
    """Apply one transition in memory, refusing anything outside the table."""
    entry = entries.get(prd)
    if verb == "request":
        if entry is not None:
            raise RefusedError(f"a request already exists for {prd}")
        entries[prd] = payload
    elif verb == "decide":
        if entry is None or entry["status"] != "requested":
            raise RefusedError(f"no requested entry to decide for {prd}")
        entries[prd] = dict(entry, status=payload, decided_at=now_stamp())
    else:
        if entry is None or entry["status"] != "approved":
            raise RefusedError(f"no approved entry to consume for {prd}")
        entries[prd] = dict(entry, status="consumed", consumed_at=now_stamp())


def write_transition(ledger_path: Path, verb: str, prd: str, payload: Any) -> None:
    """Read-modify-write the ledger under an exclusive advisory lock.

    Refusals raise before the backup, so a rejected transition leaves both the
    ledger and its `.bak` untouched.
    """
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = Path(f"{ledger_path}.lock")
    with open(lock_path, "w", encoding="utf-8") as lock:
        # fcntl.flock(LOCK_EX) on a sidecar <ledger>.lock serializes the whole
        # read -> backup -> modify -> atomic-write, so two requests racing for
        # different PRDs cannot drop a write - the second blocks, then reads the
        # first's result. `lock` stays referenced for the whole block: a
        # collected file object would close the fd and release the lock.
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        raw, entries = read_ledger(ledger_path)
        apply_verb(entries, verb, prd, payload)
        if raw is not None:
            Path(f"{ledger_path}.bak").write_bytes(raw)
        atomic_write(ledger_path, entries)


def main() -> int:
    argv = sys.argv[1:]
    if len(argv) < 2:
        print(USAGE, file=sys.stderr)
        return 1
    ledger_path = Path(argv[0])
    verb = argv[1]
    rest = argv[2:]
    if verb not in ARITY:
        print(f"unsupported verb: {verb!r}", file=sys.stderr)
        return 1
    if len(rest) != ARITY[verb]:
        print(f"{verb} takes exactly {ARITY[verb]} arguments", file=sys.stderr)
        return 1
    prd = rest[0]
    if not prd.strip():
        print("prd must not be blank", file=sys.stderr)
        return 1

    try:
        if verb == "show":
            _raw, entries = read_ledger(ledger_path)
            print(json.dumps(entries.get(prd, {})))
        elif verb == "request":
            write_transition(ledger_path, verb, prd, build_entry(rest))
        elif verb == "decide":
            if rest[1] not in ("approved", "rejected"):
                raise BadArgument(f"unknown status: {rest[1]!r}")
            write_transition(ledger_path, verb, prd, rest[1])
        else:
            write_transition(ledger_path, verb, prd, None)
    except BadArgument as err:
        print(str(err), file=sys.stderr)
        return 1
    except LedgerError as err:
        print(str(err), file=sys.stderr)
        return 2
    except RefusedError as err:
        print(str(err), file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
