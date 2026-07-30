#!/usr/bin/env python3
"""state.py - the locked read-modify-write boundary for autopilot state.json.

Exposes:
    load(path) -> (state, version_status)
        Read-only, lock-free. For callers that only inspect. NEVER the read
        half of a read-modify-write - a load() outside the lock followed by a
        write inside one lets another writer's commit land in the gap and be
        silently overwritten.
    transaction(path, fn, *, validator=schema.validate) -> dict
        The one read-modify-write primitive. Runs under a single exclusive
        fcntl.flock on `<path>.lock`, held for the whole body (read included,
        for the reason above): read+parse, fn(state), validator(new), stamp
        schema_version, write `<path>.bak`, then atomically replace the state
        file. Returns the committed state.
    init(path, initial) -> None
        Create-only. Raises StateExistsError if the file already exists.
    restore(path) -> None
        Roll `<path>.bak` back over the state file, only after the backup
        parses AND passes schema.validate.

StateError, StateExistsError, BackupError are the three exception classes.
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from pathlib import Path
from typing import Callable

from . import schema


class StateError(Exception):
    """State file missing or corrupt."""


class StateExistsError(Exception):
    """init() called against a state file that already exists."""


class BackupError(Exception):
    """restore() found no usable `.bak`: missing, corrupt, or schema-invalid."""


def _read_and_parse(path: Path) -> tuple[bytes, dict]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError as err:
        raise StateError(f"state file not found: {path}") from err
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as err:
        raise StateError(f"state file is not valid JSON ({path}): {err}") from err
    if not isinstance(parsed, dict):
        raise StateError(
            f"state root must be a JSON object, got {type(parsed).__name__}: {path}"
        )
    return raw, parsed


def _atomic_write(path: Path, data: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load(path: Path) -> tuple[dict, str]:
    """Read-only, lock-free load. Missing/corrupt file raises StateError."""
    _raw, state = _read_and_parse(Path(path))
    return state, schema.version_status(state)


def transaction(
    path: Path,
    fn: Callable[[dict], dict],
    *,
    validator: Callable[[dict], None] = schema.validate,
) -> dict:
    """Read-modify-write `path` under one exclusive lock held for the whole body.

    fn and validator both run - and both may raise - before anything durable
    is touched. The `.bak` is written only after validation succeeds: writing
    it earlier (as scripts/statectl.py does, before mutating) would destroy
    the rollback point the moment a mutation raises.
    """
    path = Path(path)
    lock_path = Path(f"{path}.lock")
    with open(lock_path, "w", encoding="utf-8") as lock:
        # The lock spans the read, not just the write: a load() outside the
        # lock followed by a write inside it would let a concurrent writer's
        # commit land in the gap and get silently overwritten.
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        raw, current = _read_and_parse(path)
        new_state = fn(current)
        validator(new_state)
        new_state["schema_version"] = schema.SCHEMA_VERSION
        # Back up the raw pre-transaction BYTES, not a re-serialization of
        # `current`: if fn mutates its argument in place and returns it,
        # `new_state is current` and re-dumping `current` would silently
        # write the NEW state into `.bak`, destroying the rollback point.
        # Bytes read before fn ran can't be touched by fn, so this is
        # immune to that aliasing by construction.
        _atomic_write_bytes(Path(f"{path}.bak"), raw)
        _atomic_write(path, new_state)
    return new_state


def init(path: Path, initial: dict) -> None:
    """Create the state file when absent; raise StateExistsError otherwise."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(initial, fh, indent=2)
            fh.write("\n")
        try:
            # os.link, not os.replace: os.replace would silently clobber an
            # existing state file, destroying the exclusivity guarantee
            # init() exists to provide. os.link raises FileExistsError when
            # `path` already exists, giving the same exclusivity O_EXCL gave.
            os.link(tmp, path)
        except FileExistsError as err:
            raise StateExistsError(f"state file already exists: {path}") from err
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def restore(path: Path) -> None:
    """Roll `<path>.bak` back over the state file, only if the backup is usable."""
    path = Path(path)
    bak_path = Path(f"{path}.bak")
    lock_path = Path(f"{path}.lock")
    with open(lock_path, "w", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if not bak_path.exists():
            raise BackupError(f"no backup to restore: {bak_path}")
        try:
            _raw, parsed = _read_and_parse(bak_path)
        except StateError as err:
            raise BackupError(str(err)) from err
        try:
            schema.validate(parsed)
        except schema.SchemaError as err:
            raise BackupError(
                f"backup fails schema validation ({bak_path}): {err}"
            ) from err
        _atomic_write(path, parsed)
