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
    read_and_parse(path) -> (raw_bytes, state)
        Read + parse with no lock and no validation. Public because
        cli/statectl.py's `get` verb and its shim re-export it; raises
        StateError so the exit-2 contract holds.
    atomic_write(path, data) -> None
        Same-dir temp file, fsynced, then os.replace. The fsync is what makes
        the rename safe: without it the directory entry can reach disk before
        the data, so a power loss leaves a renamed but empty state file.
        Public for the same reason, and
        because scripts/fablectl.py writes its own (non-state) ledger with
        it - so this one takes NO schema stamp and runs NO validator. Every
        state.json write goes through transaction(), never here directly.

StateError, StateExistsError, BackupError are the three exception classes.
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from . import schema


class StateError(Exception):
    """State file missing or corrupt."""


class StateExistsError(Exception):
    """init() called against a state file that already exists."""


class BackupError(Exception):
    """restore() found no usable `.bak`: missing, corrupt, or schema-invalid."""


class FutureSchemaError(StateError):
    """transaction() found schema_version newer than schema.SCHEMA_VERSION.

    Refused before fn runs and before anything durable is touched: an older
    autopilot writing a state a newer one already advanced past must not
    mutate it out from under the newer version's assumptions.
    """


def read_and_parse(path: Path) -> tuple[bytes, dict]:
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


def atomic_write(path: Path, data: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
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
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load(path: Path) -> tuple[dict, str]:
    """Read-only, lock-free load. Missing/corrupt file raises StateError."""
    _raw, state = read_and_parse(Path(path))
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
        raw, current = read_and_parse(path)
        if schema.version_status(current) == "future":
            stamp = current.get("schema_version")
            raise FutureSchemaError(
                f"future-schema state.json ({path}): "
                f"v{stamp} > v{schema.SCHEMA_VERSION}, refusing",
            )
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
        atomic_write(path, new_state)
    return new_state


def init(path: Path, initial: dict) -> None:
    """Create the state file when absent; raise StateExistsError otherwise.

    Stamps schema_version onto `initial` in place before writing, so callers
    holding a reference to the same dict see the stamp too.
    """
    path = Path(path)
    initial["schema_version"] = schema.SCHEMA_VERSION
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(initial, fh, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
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
    """Roll `<path>.bak` back over the state file, only if the backup is usable.

    Re-stamps the restored content to the current schema_version, but only
    when the file being replaced was itself already schema-aware (its own
    version_status is not "unstamped") - a restore over a never-touched
    legacy file must not be the operation that first imposes versioning on
    it.
    """
    path = Path(path)
    bak_path = Path(f"{path}.bak")
    lock_path = Path(f"{path}.lock")
    with open(lock_path, "w", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if not bak_path.exists():
            raise BackupError(f"no backup to restore: {bak_path}")
        try:
            _raw, parsed = read_and_parse(bak_path)
        except StateError as err:
            raise BackupError(str(err)) from err
        try:
            schema.validate(parsed)
        except schema.SchemaError as err:
            raise BackupError(
                f"backup fails schema validation ({bak_path}): {err}"
            ) from err
        try:
            _current_raw, current = read_and_parse(path)
        except StateError:
            current = {}
        if schema.version_status(current) != "unstamped":
            parsed["schema_version"] = schema.SCHEMA_VERSION
        atomic_write(path, parsed)
