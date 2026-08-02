#!/usr/bin/env python3
"""statectl.py - atomic, advisory-locked JSON-state mutator.

CLI:
    python3 statectl.py <state-path> get|set|append|del <json-path> [value]
    python3 statectl.py <state-path> task-start <task-id>
    python3 statectl.py <state-path> task-done <task-id> <attempt-json-file>
    python3 statectl.py <state-path> set-contract-card <file>

`get` prints the JSON value at <json-path> to stdout. Every other verb mutates
the file under an exclusive advisory lock, preserving every sibling field,
writing one rotating `<state-path>.bak` before the change and replacing the
file atomically. A missing or corrupt file exits 2 without touching it; a bad
argument or unsupported json-path exits 1.

The three task/card verbs are compound: each lands every field effect of one
transition inside a single locked read-modify-write, so a crash cannot leave
half a transition on disk. They also resolve tasks by `tasks[].id` rather than
array position, which the `tasks[N]` json-paths could not do.
"""

from __future__ import annotations

import fcntl
import json
import os
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

Token = str | int


class UsageError(Exception):
    """Bad arguments or unsupported json-path grammar (exit 1)."""


class StateError(Exception):
    """State file missing or corrupt (exit 2)."""


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


def do_set_contract_card(data: Any, text: str) -> None:
    if not isinstance(data, dict):
        raise UsageError("state root is not an object")
    data["contract_card"] = text.rstrip("\n")


def read_and_parse(state_path: Path) -> tuple[bytes, Any]:
    """Return (raw_bytes, parsed). A missing or corrupt file raises StateError.

    Returns the raw on-disk bytes alongside the parsed value so the caller can
    write a byte-for-byte `.bak`, and raises StateError to drive the exit-2
    contract. Not a generic loader - it is coupled to statectl's backup + exit
    codes, so it stays local rather than importing a parser that hides them.
    """
    try:
        raw = state_path.read_bytes()
    except FileNotFoundError as err:
        raise StateError(f"state file not found: {state_path}") from err
    try:
        return raw, json.loads(raw)
    except json.JSONDecodeError as err:
        raise StateError(
            f"state file is not valid JSON ({state_path}): {err}",
        ) from err


def atomic_write(state_path: Path, data: Any) -> None:
    """Write `data` as JSON via a same-dir temp file + os.replace (atomic on POSIX).

    indent=2 + trailing newline keeps state.json human-readable - operators and
    forensics read this file directly, and it was pretty-printed before statectl
    became its sole writer.
    """
    fd, tmp = tempfile.mkstemp(dir=str(state_path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, state_path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def mutate(state_path: Path, apply: Callable[[Any], None]) -> None:
    """Read-modify-write `state_path` under an exclusive advisory lock.

    Reads the current bytes, writes one rotating `<state>.bak`, calls `apply` on
    the parsed data, and replaces the file atomically. A missing or corrupt file
    raises StateError before any backup or write happens. `apply` may make
    several changes - they all land in the one atomic replace, which is what
    makes the compound task verbs crash-safe.
    """
    lock_path = Path(f"{state_path}.lock")
    with open(lock_path, "w", encoding="utf-8") as lock:
        # ponytail: fcntl.flock(LOCK_EX) on a sidecar <state>.lock serializes the
        # whole read -> backup -> modify -> atomic-write, so two racing `append`s
        # can't drop an update - the second blocks, then reads the first's result
        # before appending. The lock releases when this `with` closes the fd.
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        raw, data = read_and_parse(state_path)
        Path(f"{state_path}.bak").write_bytes(raw)
        apply(data)
        atomic_write(state_path, data)


USAGE = (
    "usage: statectl.py <state-path> get|set|append|del <json-path> [value]\n"
    "       statectl.py <state-path> task-start <task-id>\n"
    "       statectl.py <state-path> task-done <task-id> <attempt-json-file>\n"
    "       statectl.py <state-path> set-contract-card <file>"
)

_PATH_VERBS = ("get", "set", "append", "del")
_TASK_VERBS = ("task-start", "task-done", "set-contract-card")


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


def _build_apply(verb: str, arg: str, rest: list[str]) -> Callable[[Any], None]:
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

    if verb == "set-contract-card":
        # The file is argv[2] here - this verb takes no task id.
        try:
            text = Path(arg).read_text(encoding="utf-8")
        except OSError as err:
            raise UsageError(f"cannot read {arg}: {err}") from err
        return lambda data: do_set_contract_card(data, text)

    if verb == "task-start":
        return lambda data: do_task_start(data, arg)

    if not rest:
        raise UsageError("task-done requires an attempt-json-file argument")
    attempt = _read_json_file(rest[0])
    return lambda data: do_task_done(data, arg, attempt)


def main() -> int:
    argv = sys.argv[1:]
    if len(argv) < 3:
        print(USAGE, file=sys.stderr)
        return 1
    state_path = Path(argv[0])
    verb = argv[1]
    arg = argv[2]
    rest = argv[3:]

    if verb not in _PATH_VERBS + _TASK_VERBS:
        print(f"unsupported verb: {verb!r}", file=sys.stderr)
        return 1

    try:
        if verb == "get":
            _raw, data = read_and_parse(state_path)
            print(json.dumps(get_value(data, parse_path(arg))))
        else:
            mutate(state_path, _build_apply(verb, arg, rest))
    except StateError as err:
        print(str(err), file=sys.stderr)
        return 2
    except UsageError as err:
        print(str(err), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
