#!/usr/bin/env python3
"""statectl.py - atomic, advisory-locked JSON-state mutator.

CLI:
    python3 statectl.py <state-path> get|set|append|del <json-path> [value]

`get` prints the JSON value at <json-path> to stdout. `set`, `append`, and
`del` mutate the file under an exclusive advisory lock, preserving every
sibling field, writing one rotating `<state-path>.bak` before the change and
replacing the file atomically. A missing or corrupt file exits 2 without
touching it; a bad argument or unsupported json-path exits 1.
"""

from __future__ import annotations

import fcntl
import json
import os
import sys
import tempfile
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
    A non-numeric index, malformed brackets, or an empty/misplaced segment
    raises UsageError - the grammar is reported unsupported, never guessed past.
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
            if not inner.isdigit():
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
            f"state file is not valid JSON ({state_path}): {err}"
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


def mutate(state_path: Path, verb: str, tokens: list[Token], value: Any) -> None:
    """Read-modify-write `state_path` under an exclusive advisory lock.

    Reads the current bytes, writes one rotating `<state>.bak`, applies the
    mutation in memory, and replaces the file atomically. A missing or corrupt
    file raises StateError before any backup or write happens.
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
        if verb == "set":
            do_set(data, tokens, value)
        elif verb == "append":
            do_append(data, tokens, value)
        else:
            do_del(data, tokens)
        atomic_write(state_path, data)


def main() -> int:
    argv = sys.argv[1:]
    if len(argv) < 3:
        print(
            "usage: statectl.py <state-path> get|set|append|del <json-path> [value]",
            file=sys.stderr,
        )
        return 1
    state_path = Path(argv[0])
    verb = argv[1]
    path_str = argv[2]
    rest = argv[3:]

    if verb not in ("get", "set", "append", "del"):
        print(f"unsupported verb: {verb!r}", file=sys.stderr)
        return 1

    value: Any = None
    if verb in ("set", "append"):
        if not rest:
            print(f"{verb} requires a JSON value argument", file=sys.stderr)
            return 1
        try:
            value = json.loads(rest[0])
        except json.JSONDecodeError as err:
            print(f"value is not valid JSON: {err}", file=sys.stderr)
            return 1

    try:
        tokens = parse_path(path_str)
        if verb == "get":
            _raw, data = read_and_parse(state_path)
            print(json.dumps(get_value(data, tokens)))
        else:
            mutate(state_path, verb, tokens, value)
    except StateError as err:
        print(str(err), file=sys.stderr)
        return 2
    except UsageError as err:
        print(str(err), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
