#!/usr/bin/env python3
"""statectl.py - the json-path state mutator, over the validated boundary.

Relocated from `scripts/statectl.py` by PRD 00089, which left that path a
re-export shim. The move is the point: statectl used to carry its OWN
read/lock/backup/write, which made it a second writer of `state.json` -
atomic and locked, but schema-unvalidated, so a malformed field value reached
disk unchallenged. `mutate()` now runs on `state.transaction`, so there is one
validated writer and no second implementation to drift.

CLI:
    python3 statectl.py <state-path> get|set|append|del <json-path> [value]
    python3 statectl.py <state-path> task-start <task-id>
    python3 statectl.py <state-path> task-done <task-id> <attempt-json-file>
    python3 statectl.py <state-path> set-contract-card <file>
    python3 statectl.py <state-path> task-add <task-json-file>
    python3 statectl.py <state-path> task-set-body <task-id> <body-file>
    python3 statectl.py <state-path> task-set-meta <task-id> <meta-json-file>
    python3 statectl.py <state-path> task-set-status <task-id> <status>
    python3 statectl.py <state-path> tasks-clear
    python3 statectl.py <state-path> complete-prd <prd-filename>

`get` prints the JSON value at <json-path> to stdout. Every other verb mutates
the file under an exclusive advisory lock, preserving every sibling field,
writing one rotating `<state-path>.bak` and replacing the file atomically. A
missing or corrupt file exits 2 without touching it; a bad argument, an
unsupported json-path, or a value the schema rejects exits 1; a future-schema
state file exits 6, unchanged.

The three task/card verbs are compound: each lands every field effect of one
transition inside a single locked read-modify-write, so a crash cannot leave
half a transition on disk. They also resolve tasks by `tasks[].id` rather than
array position, which the `tasks[N]` json-paths could not do.

Two behaviors changed with the move, both deliberate and both loud:

- The `.bak` is written AFTER the mutation validates, not before. The old
  order destroyed the rollback point the moment a mutation raised.
- A mutation whose OWN field value is malformed is rejected (exit 1) and the
  file is left byte-unchanged. Validation is scoped to the fields the
  mutation touched, so an unrelated pre-existing odd field - the kind a
  forensic hand-edit leaves - still blocks nothing.
"""

from __future__ import annotations

import copy
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import render_report, schema, state

# statectl's exit-2 contract is state.StateError's: same class, not a parallel
# one, so `except StateError` in main() cannot miss a boundary failure.
StateError = state.StateError

# read_and_parse and atomic_write live on the boundary now. They are named
# here so the shim re-exports one implementation rather than a copy.
read_and_parse = state.read_and_parse
atomic_write = state.atomic_write

Token = str | int


class UsageError(Exception):
    """Bad arguments or unsupported json-path grammar (exit 1)."""


def parse_path(path: str) -> list[Token]:
    """Parse `a.b[0].c` into keys (str) and indices (int).

    Grammar: dot-separated keys, each optionally followed by `[int]` indices.
    Indices may be negative (`[-1]` = last element, Python-style) so the skill
    prose can target `tasks[i].attempts[-1]` directly. A non-integer index,
    malformed brackets, or an empty/misplaced segment raises UsageError - the
    grammar is reported unsupported, never guessed past.
    """
    if not path:
        raise UsageError("empty json-path")
    tokens: list[Token] = []
    i, n = 0, len(path)
    while i < n:
        if path[i] == "[":
            close = path.find("]", i)
            if close == -1:
                raise UsageError(f"unclosed '[' in json-path: {path!r}")
            inner = path[i + 1 : close]
            digits = inner.removeprefix("-")
            if not digits.isdigit():
                raise UsageError(f"non-numeric index in json-path: {path!r}")
            tokens.append(int(inner))
            i = close + 1
        elif path[i] == ".":
            raise UsageError(f"unexpected '.' in json-path: {path!r}")
        else:
            j = i
            while j < n and path[j] not in ".[":
                j += 1
            tokens.append(path[i:j])
            i = j
        if i < n and path[i] == ".":
            i += 1
            if i >= n:
                raise UsageError(f"trailing '.' in json-path: {path!r}")
    return tokens


def _descend(cur: Any, tokens: list[Token], *, create: bool) -> Any:
    """Walk into `cur` following `tokens`, returning the reached value/container.

    With create=True, an absent string key becomes an empty dict so set/append
    can build intermediates. Missing indices or type mismatches raise UsageError.
    """
    for tok in tokens:
        if isinstance(tok, str):
            if not isinstance(cur, dict):
                raise UsageError(f"cannot descend key {tok!r} into non-object")
            if tok not in cur:
                if not create:
                    raise UsageError(f"json-path key not found: {tok!r}")
                cur[tok] = {}
            cur = cur[tok]
        else:
            if not isinstance(cur, list):
                raise UsageError(f"cannot index [{tok}] into non-array")
            try:
                cur = cur[tok]
            except IndexError as err:
                raise UsageError(f"json-path index out of range: [{tok}]") from err
    return cur


def get_value(data: Any, tokens: list[Token]) -> Any:
    return _descend(data, tokens, create=False)


def _assign(parent: Any, tok: Token, value: Any) -> None:
    if isinstance(tok, str):
        if not isinstance(parent, dict):
            raise UsageError("set parent is not an object")
        parent[tok] = value
    else:
        if not isinstance(parent, list):
            raise UsageError("set parent is not an array")
        try:
            parent[tok] = value
        except IndexError as err:
            raise UsageError(f"set index out of range: [{tok}]") from err


def do_set(data: Any, tokens: list[Token], value: Any) -> None:
    parent = _descend(data, tokens[:-1], create=True)
    _assign(parent, tokens[-1], value)


def do_append(data: Any, tokens: list[Token], value: Any) -> None:
    parent = _descend(data, tokens[:-1], create=True)
    last = tokens[-1]
    if isinstance(last, str):
        if not isinstance(parent, dict):
            raise UsageError("append parent is not an object")
        arr = parent.setdefault(last, [])
    else:
        if not isinstance(parent, list):
            raise UsageError("append parent is not an array")
        try:
            arr = parent[last]
        except IndexError as err:
            raise UsageError(f"append index out of range: [{last}]") from err
    if not isinstance(arr, list):
        raise UsageError(f"append target is not an array: {last!r}")
    arr.append(value)


def do_del(data: Any, tokens: list[Token]) -> None:
    parent = _descend(data, tokens[:-1], create=False)
    last = tokens[-1]
    try:
        del parent[last]
    except (KeyError, IndexError, TypeError) as err:
        raise UsageError(f"cannot delete {last!r}: {err}") from err


def _find_task(data: Any, task_id: str) -> dict[str, Any]:
    """Return the `tasks[]` entry whose `id` matches, comparing as strings.

    Resolves by id, never by array position: `state.tasks` is not guaranteed to
    be ordered by id (rework appends `[D{cycle}]` follow-ups), so the `tasks[N]`
    json-path form silently targeted the wrong task once the arrays diverged.
    """
    tasks = data.get("tasks") if isinstance(data, dict) else None
    if not isinstance(tasks, list):
        raise UsageError("state has no tasks array")
    for entry in tasks:
        if isinstance(entry, dict) and str(entry.get("id")) == task_id:
            return entry
    raise UsageError(f"no task with id {task_id!r}")


def _recount_completed(data: dict[str, Any]) -> None:
    """Recompute `tasks_completed` from the task array itself.

    Derived, never caller-supplied: the count and the statuses drifted apart
    whenever a caller set one without the other.
    """
    data["tasks_completed"] = sum(
        1
        for entry in data["tasks"]
        if isinstance(entry, dict) and entry.get("status") == "completed"
    )


def do_task_start(data: Any, task_id: str) -> None:
    _find_task(data, task_id)["status"] = "in_progress"


def do_task_done(data: Any, task_id: str, attempt: Any) -> None:
    """Mark a task completed, append its attempt record, recount - atomically."""
    task = _find_task(data, task_id)
    attempts = task.setdefault("attempts", [])
    if not isinstance(attempts, list):
        raise UsageError(f"task {task_id!r} attempts is not an array")
    task["status"] = "completed"
    attempts.append(attempt)
    _recount_completed(data)


def do_append_attempt(data: Any, task_id: str, attempt: Any) -> None:
    """Append an attempt record WITHOUT completing the task.

    The abort and escalate-away paths record an attempt while the task stays
    open, so unlike `task-done` this moves neither `status` nor the derived
    `tasks_completed`. It resolves by id for the same reason `task-done` does:
    once rework appends `[D{cycle}]` follow-ups, array position stops matching
    id and an index path appends to the wrong task.
    """
    task = _find_task(data, task_id)
    attempts = task.setdefault("attempts", [])
    if not isinstance(attempts, list):
        raise UsageError(f"task {task_id!r} attempts is not an array")
    attempts.append(attempt)


def do_set_contract_card(data: Any, text: str) -> None:
    if not isinstance(data, dict):
        raise UsageError("state root is not an object")
    # Trailing newlines are stripped deliberately: the card is re-injected as
    # additionalContext by the SessionStart hook, which supplies its own
    # framing, so a trailing blank line is noise in the stored string. The
    # file's own bytes are otherwise preserved exactly.
    data["contract_card"] = text.rstrip("\n")


def do_task_add(data: Any, task_json: dict[str, Any]) -> str:
    """Append a pending task, returning the id assigned to it.

    The id is the highest numeric `tasks[].id` plus one, not `len(tasks) + 1`
    and not the last entry's id plus one: rework appends leave `tasks[]` out of
    id order, so both shortcuts hand out an id that is already taken.

    `name` is required: /work renders its dispatch subject from it, so a
    nameless task surfaces as a blank prompt rather than as an error here.
    """
    name = task_json.get("name")
    if not isinstance(name, str) or not name:
        raise UsageError("task-add payload requires a non-empty 'name' string")
    tasks = data.setdefault("tasks", [])
    highest_id = max(
        (
            int(entry["id"])
            for entry in tasks
            if isinstance(entry, dict) and str(entry.get("id", "")).isdigit()
        ),
        default=0,
    )
    task_id = str(highest_id + 1)
    # The payload passes through whole rather than field by field: /work renders
    # its dispatch from these keys, and an allowlist silently drops the ones a
    # later caller adds. An absent optional field stays absent - never a null,
    # which every consumer would read as a real value.
    tasks.append({**task_json, "id": task_id, "status": "pending"})
    data["tasks_total"] = len(tasks)
    return task_id


def do_task_set_body(data: Any, task_id: str, body_text: str) -> None:
    """Replace a task's description with raw file bytes, newline and all.

    Unlike `set-contract-card` the trailing newline survives: nothing
    downstream of `description` re-frames it, so the file is stored verbatim.
    """
    _find_task(data, task_id)["description"] = body_text


def do_task_set_meta(data: Any, task_id: str, meta: dict[str, Any]) -> None:
    """Merge `meta`'s keys onto the task entry; a null value deletes its key.

    Flattened onto the entry, not nested under a `metadata` key, because every
    reader of these fields (model, estimates, qwen gating) reads them off the
    task itself. Keys the payload omits are left untouched, and `status` never
    moves here, so the derived count is not recomputed.

    `id` and `status` are verb-owned, exactly as they are in `task-add`, and a
    payload carrying either is rejected rather than stripped: `id` would put two
    entries under one id (making the first unreachable), and `status` would move
    a status past both the enum check and the `tasks_completed` recount.
    """
    for reserved in ("id", "status"):
        if reserved in meta:
            raise UsageError(
                f"task-set-meta cannot set {reserved!r}"
                " - use task-add or task-set-status",
            )
    task = _find_task(data, task_id)
    for key, value in meta.items():
        if value is None:
            task.pop(key, None)
        else:
            task[key] = value


_TASK_STATUSES = ("pending", "in_progress", "completed")


def do_task_set_status(data: Any, task_id: str, status: str) -> None:
    """Set a task's status, with no attempt record - that is `task-done`'s job."""
    if status not in _TASK_STATUSES:
        raise UsageError(f"invalid status: {status!r}")
    _find_task(data, task_id)["status"] = status
    _recount_completed(data)


def do_tasks_clear(data: Any) -> None:
    """Empty the task array and zero both counts in one write.

    Scoped to exactly those three fields: `tasks`, `tasks_total` and
    `tasks_completed`. `rework_task_ids`/`task_aborts` and the rest of the
    batch record outlive a replan.
    """
    data.update({"tasks": [], "tasks_total": 0, "tasks_completed": 0})


def _completed_prd_record(data: dict[str, Any]) -> dict[str, Any]:
    """Compute the closing PRD's `batch.completed_prds` entry from `data`.

    `autonomous_decisions` counts with `render_report.is_autonomous_row`, the
    same predicate the Autonomous Decisions table draws rows with.
    `escalated_decisions` counts with `render_report.is_escalated_row`, the
    same predicate the Escalated Decisions table draws rows with: a dict
    entry whose `status` is anything OTHER than `"pending"` or `"deferred"`
    (non-dict entries are tolerated and excluded). Both source arrays may be
    absent, counting as 0. `cycle`,
    `tasks_completed` and `tasks_total` may also be absent - the transition
    table leaves them unset on a PRD that never rewrites them - so they fall
    back to their own writers' defaults (1 for `cycle`, matching
    `transitions._rework`; 0 for the task counts).
    """
    autonomous = data.get("autonomous_decisions") or []
    deferred = data.get("deferred_decisions") or []
    escalated = sum(1 for entry in deferred if render_report.is_escalated_row(entry))
    return {
        "filename": data.get("prd"),
        "cycles": data.get("cycle", 1),
        "autonomous_decisions": sum(
            1 for entry in autonomous if render_report.is_autonomous_row(entry)
        ),
        "escalated_decisions": escalated,
        "tasks_completed": data.get("tasks_completed", 0),
        "tasks_total": data.get("tasks_total", 0),
    }


def do_complete_prd(data: Any, prd_filename: str) -> None:
    """Append the closing PRD's record to `batch.completed_prds` and reset
    `batch.parks_consecutive` to 0 - atomically, in the same write.

    `filename` is read off `data["prd"]`, never the caller-passed
    `prd_filename`; the two must match or UsageError is raised, since a
    divergence means the wrong state file or the wrong PRD name reached this
    call. The record's counts share the renderer's predicates and its absent
    keys default (cycle 1, task counts 0) - see `_completed_prd_record`.
    """
    state_prd = data.get("prd")
    if state_prd != prd_filename:
        raise UsageError(
            f"complete-prd {prd_filename!r} does not match state.prd {state_prd!r}",
        )
    batch = data.setdefault("batch", {})
    batch.setdefault("completed_prds", []).append(_completed_prd_record(data))
    batch["parks_consecutive"] = 0


def mutate(state_path: Path, apply: Callable[[Any], Any]) -> Any:
    """Read-modify-write `state_path` through the validated boundary.

    `apply` mutates the parsed state IN PLACE - the signature every existing
    call site already uses - so the pre-state is deep-copied before it runs.
    That copy is what makes "which fields did this write touch?" answerable:
    without it, an in-place mutation leaves nothing to compare against and the
    validator would have to fall back to whole-state validation, where one
    pre-existing odd field wedges every later write.

    `apply` may make several changes; they all land in the one atomic replace,
    which is what makes the compound task verbs crash-safe. A missing or
    corrupt file raises StateError before anything is written, and a mutation
    whose own field value is malformed raises schema.SchemaError with the file
    byte-unchanged.

    Whatever `apply` returns is returned back, so a verb that assigns something
    (`task-add`'s new id) can report it without a second read. Every other
    `apply` returns None implicitly, so nothing else sees a change.
    """
    before: dict = {}
    outcome: Any = None

    def fn(current: dict) -> dict:
        nonlocal outcome
        before.update(copy.deepcopy(current))
        outcome = apply(current)
        return current

    state.transaction(
        Path(state_path),
        fn,
        validator=lambda new_state: schema.validate_changed(before, new_state),
    )
    return outcome


USAGE = (
    "usage: statectl.py <state-path> get|set|append|del <json-path> [value]\n"
    "       statectl.py <state-path> task-start <task-id>\n"
    "       statectl.py <state-path> task-done <task-id> <attempt-json-file>\n"
    "       statectl.py <state-path> append-attempt <task-id> <attempt-json-file>\n"
    "       statectl.py <state-path> set-contract-card <file>\n"
    "       statectl.py <state-path> task-add <task-json-file>\n"
    "       statectl.py <state-path> task-set-body <task-id> <body-file>\n"
    "       statectl.py <state-path> task-set-meta <task-id> <meta-json-file>\n"
    "       statectl.py <state-path> task-set-status <task-id> "
    "pending|in_progress|completed\n"
    "       statectl.py <state-path> tasks-clear\n"
    "       statectl.py <state-path> complete-prd <prd-filename>"
)

_PATH_VERBS = ("get", "set", "append", "del")
_TASK_VERBS = (
    "task-start",
    "task-done",
    "append-attempt",
    "set-contract-card",
    "task-add",
    "task-set-body",
    "task-set-meta",
    "task-set-status",
    "tasks-clear",
    "complete-prd",
)


def _read_json_file(path_str: str) -> Any:
    """Load a JSON payload from a file (never an inline shell argument).

    File-borne payloads exist because inline JSON in a shell argument kept
    failing on quoting - an attempt record and a contract card both carry
    quotes, newlines and `$`.
    """
    try:
        raw = Path(path_str).read_text(encoding="utf-8")
    except OSError as err:
        raise UsageError(f"cannot read {path_str}: {err}") from err
    try:
        return json.loads(raw)
    except json.JSONDecodeError as err:
        raise UsageError(f"{path_str} is not valid JSON: {err}") from err


def _read_text_file(path_str: str) -> str:
    """Load raw text from a file, wrapping a read failure as UsageError."""
    try:
        return Path(path_str).read_text(encoding="utf-8")
    except OSError as err:
        raise UsageError(f"cannot read {path_str}: {err}") from err


def _build_apply(verb: str, arg: str, rest: list[str]) -> Callable[[Any], Any]:
    """Return the mutation `mutate()` should apply for a non-`get` verb."""
    if verb in _PATH_VERBS:
        tokens = parse_path(arg)
        if verb == "del":
            return lambda data: do_del(data, tokens)
        if not rest:
            raise UsageError(f"{verb} requires a JSON value argument")
        try:
            value = json.loads(rest[0])
        except json.JSONDecodeError as err:
            raise UsageError(f"value is not valid JSON: {err}") from err
        if verb == "set":
            return lambda data: do_set(data, tokens, value)
        return lambda data: do_append(data, tokens, value)

    return _build_task_apply(verb, arg, rest)


def _build_task_apply(verb: str, arg: str, rest: list[str]) -> Callable[[Any], Any]:
    """Return the mutation `mutate()` should apply for a task verb.

    Delegates verbs that carry a task id in `arg` to `_build_task_id_apply`;
    the three verbs handled here take their whole payload in `arg` instead.
    """
    if verb == "set-contract-card":
        # The file is argv[2] here - this verb takes no task id.
        text = _read_text_file(arg)
        return lambda data: do_set_contract_card(data, text)

    if verb == "tasks-clear":
        return do_tasks_clear

    if verb == "task-add":
        # The file is argv[2] here - this verb takes no task id either.
        payload = _read_json_file(arg)
        if not isinstance(payload, dict):
            raise UsageError(f"{arg} is not a JSON object")
        return lambda data: do_task_add(data, payload)

    return _build_task_id_apply(verb, arg, rest)


def _build_task_id_apply(verb: str, arg: str, rest: list[str]) -> Callable[[Any], Any]:
    """Return the mutation for a task verb that takes a task id in `arg`."""
    if verb == "task-set-body":
        if not rest:
            raise UsageError("task-set-body requires a body-file argument")
        body = _read_text_file(rest[0])
        return lambda data: do_task_set_body(data, arg, body)

    if verb == "task-set-meta":
        if not rest:
            raise UsageError("task-set-meta requires a meta-json-file argument")
        meta = _read_json_file(rest[0])
        if not isinstance(meta, dict):
            raise UsageError(f"{rest[0]} is not a JSON object")
        return lambda data: do_task_set_meta(data, arg, meta)

    if verb == "task-set-status":
        if not rest:
            raise UsageError("task-set-status requires a status argument")
        return lambda data: do_task_set_status(data, arg, rest[0])

    if verb == "task-start":
        return lambda data: do_task_start(data, arg)

    if verb == "complete-prd":
        return lambda data: do_complete_prd(data, arg)

    if verb == "append-attempt":
        if not rest:
            raise UsageError("append-attempt requires an attempt-json-file argument")
        return lambda data: do_append_attempt(data, arg, _read_json_file(rest[0]))

    if not rest:
        raise UsageError("task-done requires an attempt-json-file argument")
    attempt = _read_json_file(rest[0])
    return lambda data: do_task_done(data, arg, attempt)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    # `tasks-clear` is the one verb that takes no third argv entry; every other
    # verb still needs its own, so the relaxation is named rather than general.
    if len(argv) < 2 or (len(argv) < 3 and argv[1] != "tasks-clear"):
        print(USAGE, file=sys.stderr)
        return 1
    state_path = Path(argv[0])
    verb = argv[1]
    arg = argv[2] if len(argv) > 2 else ""
    rest = argv[3:]

    if verb not in _PATH_VERBS + _TASK_VERBS:
        print(f"unsupported verb: {verb!r}", file=sys.stderr)
        return 1

    try:
        if verb == "get":
            _raw, data = read_and_parse(state_path)
            print(json.dumps(get_value(data, parse_path(arg))))
        else:
            result = mutate(state_path, _build_apply(verb, arg, rest))
            if result is not None:
                # task-add is the only mutating verb that answers today:
                # callers need the id it assigned. Every other verb's apply
                # returns None, so it stays silent on success.
                print(result)
    except state.FutureSchemaError as err:
        print(f"autopilot: {err}", file=sys.stderr)
        return 6
    except StateError as err:
        print(str(err), file=sys.stderr)
        return 2
    except schema.SchemaError as err:
        # A malformed value for the field this mutation targets. Exit 1, the
        # bad-argument code, because that is what it is.
        print(f"rejected: {err}", file=sys.stderr)
        return 1
    except UsageError as err:
        print(str(err), file=sys.stderr)
        return 1
    return 0
