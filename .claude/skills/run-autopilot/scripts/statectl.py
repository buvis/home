#!/usr/bin/env python3
"""statectl.py - re-export shim over cli/statectl.py (PRD 00089).

The implementation moved to the `cli/` package so `state.json` has ONE
validated writer. This path stays because ~100 call sites name it: the skill
prose, the gate files, `scripts/fablectl.py`, and two test suites that must
keep passing unmodified.

Everything below is the same object as its `cli.statectl` counterpart, not a
copy - `StateError` raised inside the package is the `StateError` an importer
of this module catches.

CLI and exit codes are unchanged:
    python3 statectl.py <state-path> get|set|append|del <json-path> [value]
    python3 statectl.py <state-path> task-start <task-id>
    python3 statectl.py <state-path> task-done <task-id> <attempt-json-file>
    python3 statectl.py <state-path> append-attempt <task-id> <attempt-json-file>
    python3 statectl.py <state-path> set-contract-card <file>
    python3 statectl.py <state-path> task-add <task-json-file>
    python3 statectl.py <state-path> task-set-body <task-id> <body-file>
    python3 statectl.py <state-path> task-set-meta <task-id> <meta-json-file>
    python3 statectl.py <state-path> task-set-status <task-id> pending|in_progress|completed
    python3 statectl.py <state-path> tasks-clear
    python3 statectl.py <state-path> complete-prd <prd-filename>

    0  ok
    1  bad argument, unsupported json-path, or a value the schema rejects
    2  state file missing or corrupt

See `cli/statectl.py`'s docstring for the two behaviors the move changed.
"""

from __future__ import annotations

import sys
from pathlib import Path

# FRONT of sys.path, unconditionally, mirroring cli/__main__.py's bootstrap: a
# decoy top-level `cli/` package elsewhere on sys.path (e.g. the invoking
# process's cwd) must never shadow the real one this script belongs to. The
# import below has to follow it, exactly as it does in __main__.py.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli.statectl import (
    USAGE,
    StateError,
    Token,
    UsageError,
    atomic_write,
    do_append,
    do_append_attempt,
    do_complete_prd,
    do_del,
    do_set,
    do_set_contract_card,
    do_task_add,
    do_task_done,
    do_task_set_body,
    do_task_set_meta,
    do_task_set_status,
    do_task_start,
    do_tasks_clear,
    get_value,
    main,
    mutate,
    parse_path,
    read_and_parse,
)

__all__ = [
    "USAGE",
    "StateError",
    "Token",
    "UsageError",
    "atomic_write",
    "do_append",
    "do_append_attempt",
    "do_complete_prd",
    "do_del",
    "do_set",
    "do_set_contract_card",
    "do_task_add",
    "do_task_done",
    "do_task_set_body",
    "do_task_set_meta",
    "do_task_set_status",
    "do_task_start",
    "do_tasks_clear",
    "get_value",
    "main",
    "mutate",
    "parse_path",
    "read_and_parse",
]


if __name__ == "__main__":
    sys.exit(main())
