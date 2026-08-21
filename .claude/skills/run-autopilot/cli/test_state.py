#!/usr/bin/env python3
"""Tests for cli/state.py: the locked read-modify-write boundary for state.json.

state.py exposes:
  - load(path) -> tuple[dict, str]: read-only, lock-free. Missing/corrupt
    file raises StateError. Never the read half of a read-modify-write.
  - transaction(path, fn, *, validator=schema.validate) -> dict: the ONE
    read-modify-write primitive. Under a single exclusive fcntl.flock on the
    `<path>.lock` sidecar, held for the whole body: read+parse, fn(state),
    validator(new), stamp schema_version, write `<path>.bak` atomically,
    then atomically replace the state file. Returns the committed state.
  - init(path, initial: dict) -> None: create-only. Raises StateExistsError
    if the file already exists.
  - restore(path) -> None: roll `<path>.bak` back over the state file, after
    validating the backup parses AND passes schema.validate. Raises
    BackupError rather than restoring a corrupt backup.
  - StateError, StateExistsError, BackupError: the three exception classes.

These tests bind only the public contract described in the task brief.
state.py was not read (it does not exist yet); schema.py was read only as
the dependency whose public surface (SCHEMA_VERSION, SchemaError, validate,
version_status) the contract requires.
"""

from __future__ import annotations

import json
import multiprocessing
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cli import schema, state


class _FnBoom(Exception):
    """Distinct exception type for fn-raises tests, to check propagation."""


class _ValidatorBoom(Exception):
    """Distinct exception type for validator-raises tests, to check propagation."""


def _bak_path(path: Path) -> Path:
    return Path(f"{path}.bak")


def _lock_path(path: Path) -> Path:
    return Path(f"{path}.lock")


def _write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def _concurrent_append_worker(path_str: str, barrier, entry: str) -> None:
    """multiprocessing.Process target: must be module-level to be picklable.

    Waits at the barrier so both worker processes attempt their transaction
    at roughly the same time, contending for the lock. An implementation
    that reads the file outside the lock would drop one entry.
    """
    path = Path(path_str)

    def fn(current: dict) -> dict:
        new = dict(current)
        items = list(new.get("items", []))
        items.append(entry)
        new["items"] = items
        return new

    barrier.wait()
    state.transaction(path, fn)


class _TempDirTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.path = self.dir / "state.json"


class LoadTest(_TempDirTestCase):
    def test_returns_parsed_state_and_version_status_for_well_formed_file(self) -> None:
        _write_json(
            self.path,
            {"schema_version": schema.SCHEMA_VERSION, "phase": "build"},
        )
        loaded, version_status = state.load(self.path)
        self.assertEqual(
            loaded,
            {"schema_version": schema.SCHEMA_VERSION, "phase": "build"},
        )
        self.assertEqual(version_status, "current")

    def test_raises_state_error_for_missing_file(self) -> None:
        with self.assertRaises(state.StateError):
            state.load(self.dir / "nope.json")

    def test_raises_state_error_for_invalid_json(self) -> None:
        self.path.write_text("{not valid json", encoding="utf-8")
        with self.assertRaises(state.StateError):
            state.load(self.path)

    def test_raises_state_error_for_non_dict_root(self) -> None:
        self.path.write_text("[]", encoding="utf-8")
        with self.assertRaises(state.StateError):
            state.load(self.path)

    def test_does_not_create_lock_or_bak_files_as_a_side_effect(self) -> None:
        _write_json(self.path, {"phase": "build"})
        state.load(self.path)
        self.assertFalse(_lock_path(self.path).exists())
        self.assertFalse(_bak_path(self.path).exists())


class TransactionMissingFileTest(_TempDirTestCase):
    def test_transaction_on_missing_file_raises_state_error(self) -> None:
        def fn(current: dict) -> dict:
            return dict(current)

        with self.assertRaises(state.StateError):
            state.transaction(self.path, fn)


class TransactionCommitTest(_TempDirTestCase):
    def test_successful_transaction_commits_fns_result(self) -> None:
        _write_json(self.path, {"phase": "build", "cycle": 1})

        def fn(current: dict) -> dict:
            new = dict(current)
            new["cycle"] = 2
            return new

        state.transaction(self.path, fn)

        committed, _ = state.load(self.path)
        self.assertEqual(committed["cycle"], 2)
        self.assertEqual(committed["phase"], "build")

    def test_returns_committed_state_matching_what_landed_on_disk(self) -> None:
        _write_json(self.path, {"phase": "build", "cycle": 1})

        def fn(current: dict) -> dict:
            new = dict(current)
            new["cycle"] = 2
            return new

        returned = state.transaction(self.path, fn)
        on_disk, _ = state.load(self.path)
        self.assertEqual(returned, on_disk)


class TransactionSchemaVersionStampTest(_TempDirTestCase):
    def test_stamps_schema_version_even_when_fn_omits_it(self) -> None:
        _write_json(self.path, {"phase": "build"})

        def fn(current: dict) -> dict:
            new = dict(current)
            new["phase"] = "review"
            return new

        returned = state.transaction(self.path, fn)
        self.assertEqual(returned["schema_version"], schema.SCHEMA_VERSION)

        on_disk, _ = state.load(self.path)
        self.assertEqual(on_disk["schema_version"], schema.SCHEMA_VERSION)


class TransactionAtomicityOnFailureTest(_TempDirTestCase):
    """fn raising and validator raising must both leave nothing written.

    This is the regression guard for the real defect in the sibling
    scripts/statectl.py: writing the backup BEFORE mutating destroys the
    rollback point when the mutation raises. Here the .bak must already
    exist (from one prior successful transaction) and must be untouched by
    the failing transaction, byte for byte -- as must the state file.
    """

    def test_raising_fn_leaves_state_and_bak_byte_unchanged(self) -> None:
        _write_json(self.path, {"phase": "build", "cycle": 1})

        def bump(current: dict) -> dict:
            new = dict(current)
            new["cycle"] = 2
            return new

        state.transaction(self.path, bump)  # commits once, so .bak now exists
        state_before = self.path.read_bytes()
        bak_before = _bak_path(self.path).read_bytes()

        def boom(current: dict) -> dict:
            raise _FnBoom("fn exploded")

        with self.assertRaises(_FnBoom):
            state.transaction(self.path, boom)

        self.assertEqual(self.path.read_bytes(), state_before)
        self.assertEqual(_bak_path(self.path).read_bytes(), bak_before)

    def test_fn_exception_propagates_unchanged(self) -> None:
        _write_json(self.path, {"phase": "build"})

        def boom(current: dict) -> dict:
            raise _FnBoom("specific message")

        with self.assertRaises(_FnBoom) as ctx:
            state.transaction(self.path, boom)
        self.assertEqual(str(ctx.exception), "specific message")

    def test_raising_validator_leaves_state_and_bak_byte_unchanged(self) -> None:
        _write_json(self.path, {"phase": "build", "cycle": 1})

        def bump(current: dict) -> dict:
            new = dict(current)
            new["cycle"] = 2
            return new

        state.transaction(self.path, bump)  # commits once, so .bak now exists
        state_before = self.path.read_bytes()
        bak_before = _bak_path(self.path).read_bytes()

        def ok_fn(current: dict) -> dict:
            new = dict(current)
            new["cycle"] = 3
            return new

        def boom_validator(new_state: dict) -> None:
            raise _ValidatorBoom("validator exploded")

        with self.assertRaises(_ValidatorBoom):
            state.transaction(self.path, ok_fn, validator=boom_validator)

        self.assertEqual(self.path.read_bytes(), state_before)
        self.assertEqual(_bak_path(self.path).read_bytes(), bak_before)

    def test_validator_exception_propagates_unchanged(self) -> None:
        _write_json(self.path, {"phase": "build"})

        def fn(current: dict) -> dict:
            return dict(current)

        def boom_validator(new_state: dict) -> None:
            raise _ValidatorBoom("specific validator message")

        with self.assertRaises(_ValidatorBoom) as ctx:
            state.transaction(self.path, fn, validator=boom_validator)
        self.assertEqual(str(ctx.exception), "specific validator message")


class TransactionFutureSchemaTest(_TempDirTestCase):
    """A schema_version newer than schema.SCHEMA_VERSION must be refused by
    transaction() before the caller's mutation function ever runs, and must
    leave the state file (and any pre-existing `.bak`) byte-unchanged.
    """

    def test_raises_future_schema_error_when_schema_version_exceeds_current(
        self,
    ) -> None:
        _write_json(
            self.path,
            {"schema_version": schema.SCHEMA_VERSION + 1, "phase": "build"},
        )

        def fn(current: dict) -> dict:
            return dict(current)

        with self.assertRaises(state.FutureSchemaError):
            state.transaction(self.path, fn)

    def test_future_schema_error_is_a_state_error_subclass(self) -> None:
        self.assertTrue(issubclass(state.FutureSchemaError, state.StateError))

    def test_does_not_call_fn_when_schema_version_is_future(self) -> None:
        _write_json(self.path, {"schema_version": 999, "phase": "build", "cycle": 3})
        calls = []

        def fn(current: dict) -> dict:
            calls.append(current)
            return dict(current)

        with self.assertRaises(state.FutureSchemaError):
            state.transaction(self.path, fn)

        self.assertEqual(calls, [], "fn must not run when the schema is future")

    def test_leaves_state_file_byte_unchanged_when_schema_version_is_future(
        self,
    ) -> None:
        _write_json(self.path, {"schema_version": 999, "phase": "build", "cycle": 3})
        before = self.path.read_bytes()

        def fn(current: dict) -> dict:
            new = dict(current)
            new["phase"] = "review"
            return new

        with self.assertRaises(state.FutureSchemaError):
            state.transaction(self.path, fn)

        self.assertEqual(self.path.read_bytes(), before)

    def test_does_not_write_a_bak_file_when_none_existed_and_schema_version_is_future(
        self,
    ) -> None:
        _write_json(self.path, {"schema_version": 999, "phase": "build"})

        with self.assertRaises(state.FutureSchemaError):
            state.transaction(self.path, lambda current: dict(current))

        self.assertFalse(_bak_path(self.path).exists())

    def test_does_not_touch_an_existing_bak_file_when_schema_version_is_future(
        self,
    ) -> None:
        _write_json(_bak_path(self.path), {"phase": "old-backup"})
        bak_before = _bak_path(self.path).read_bytes()
        _write_json(self.path, {"schema_version": 999, "phase": "build"})

        with self.assertRaises(state.FutureSchemaError):
            state.transaction(self.path, lambda current: dict(current))

        self.assertEqual(_bak_path(self.path).read_bytes(), bak_before)

    def test_future_schema_error_message_names_both_versions_and_refuses(
        self,
    ) -> None:
        # There are two writers of state.json refusing a future schema with
        # exit code 6; they must print the SAME message. This pins the
        # correct wording (the one cli/__main__.py's _schema_version_preflight
        # already uses) onto transaction()'s own FutureSchemaError.
        _write_json(self.path, {"schema_version": 999, "phase": "build"})

        with self.assertRaises(state.FutureSchemaError) as ctx:
            state.transaction(self.path, lambda current: dict(current))

        # Exact, not substring: the finding asked for the message to be
        # asserted exactly, and substring checks would still pass on a
        # message with the right pieces in the wrong order or padded with
        # noise -- which is the failure mode that let the two writers
        # diverge in the first place.
        self.assertEqual(
            str(ctx.exception),
            f"future-schema state.json ({self.path}): "
            f"v999 > v{schema.SCHEMA_VERSION}, refusing",
        )


class TransactionNonFutureSchemaUnaffectedTest(_TempDirTestCase):
    """Absent, current, or older schema_version must be completely unaffected
    by the future-schema guard: no FutureSchemaError, and a normal mutation
    lands on disk exactly as it did before this change.
    """

    def test_absent_schema_version_does_not_raise_future_schema_error(self) -> None:
        _write_json(self.path, {"phase": "build"})

        def fn(current: dict) -> dict:
            new = dict(current)
            new["phase"] = "review"
            return new

        state.transaction(self.path, fn)

        committed, _ = state.load(self.path)
        self.assertEqual(committed["phase"], "review")

    def test_current_schema_version_does_not_raise_future_schema_error(self) -> None:
        _write_json(
            self.path,
            {"schema_version": schema.SCHEMA_VERSION, "phase": "build"},
        )

        def fn(current: dict) -> dict:
            new = dict(current)
            new["phase"] = "review"
            return new

        state.transaction(self.path, fn)

        committed, _ = state.load(self.path)
        self.assertEqual(committed["phase"], "review")

    def test_older_schema_version_does_not_raise_future_schema_error(self) -> None:
        # SCHEMA_VERSION is currently 1, so 0 is the only strictly-older,
        # still-valid (non-negative) value available to exercise "old".
        _write_json(self.path, {"schema_version": 0, "phase": "build"})

        def fn(current: dict) -> dict:
            new = dict(current)
            new["phase"] = "review"
            return new

        state.transaction(self.path, fn)

        committed, _ = state.load(self.path)
        self.assertEqual(committed["phase"], "review")
        self.assertEqual(committed["schema_version"], schema.SCHEMA_VERSION)


class CorruptBytesTest(_TempDirTestCase):
    """Invalid UTF-8 must surface as the module's own exceptions.

    Found by the task-3 review, 2026-07-30. `json.loads(bytes)` decodes before
    parsing, so malformed bytes raise UnicodeDecodeError -- NOT
    JSONDecodeError. A truncated or partially-overwritten state file therefore
    escaped as a raw UnicodeDecodeError, past the StateError/BackupError
    contract that callers branch on.
    """

    def test_load_raises_state_error_on_invalid_utf8(self) -> None:
        self.path.write_bytes(b'{"phase": "\xff\xfe build"}')
        with self.assertRaises(state.StateError):
            state.load(self.path)

    def test_transaction_raises_state_error_on_invalid_utf8(self) -> None:
        self.path.write_bytes(b'{"phase": "\xff\xfe build"}')
        with self.assertRaises(state.StateError):
            state.transaction(self.path, lambda s: s)

    def test_restore_raises_backup_error_on_invalid_utf8_backup(self) -> None:
        _write_json(self.path, {"phase": "build"})
        _bak_path(self.path).write_bytes(b'{"phase": "\xff\xfe build"}')
        before = self.path.read_bytes()
        with self.assertRaises(state.BackupError):
            state.restore(self.path)
        self.assertEqual(self.path.read_bytes(), before)


class InitFailureTest(_TempDirTestCase):
    """A failed init() must leave NO file behind.

    Found by the task-3 review, 2026-07-30. init() used O_CREAT|O_EXCL and
    then wrote in place, so a serialization failure left a truncated file on
    disk -- and StateExistsError then refused every later init(), permanently
    wedging the loop's ability to bootstrap its own state.
    """

    def test_failed_init_leaves_no_file_and_allows_retry(self) -> None:
        with self.assertRaises(Exception):
            state.init(self.path, {"unserializable": object()})
        self.assertFalse(
            self.path.exists(),
            "a failed init must not leave a partial file; StateExistsError "
            "would then block every retry and the loop could never bootstrap",
        )
        state.init(self.path, {"phase": "build"})
        self.assertEqual(
            json.loads(self.path.read_text(encoding="utf-8"))["phase"],
            "build",
        )


class TransactionBackupAliasingTest(_TempDirTestCase):
    """The backup must capture the PRE-transaction state even when `fn`
    mutates its argument in place and returns the same object.

    Found by the task-3 review, 2026-07-30. Nothing in the contract requires
    `fn` to copy, and mutate-and-return-self is ordinary Python. When it
    happens, a naive implementation writes the ALREADY-MUTATED dict to `.bak`,
    so the backup holds the new state and `restore()` becomes a no-op -- the
    same destroyed-rollback-point failure this module exists to fix in
    scripts/statectl.py, arriving by a different route. Every other test in
    this file copies inside `fn`, so only this one can catch it.
    """

    def test_bak_holds_previous_state_when_fn_mutates_in_place(self) -> None:
        _write_json(self.path, {"phase": "build", "cycle": 1})

        def bump_in_place(current: dict) -> dict:
            current["cycle"] = 2
            return current

        state.transaction(self.path, bump_in_place)

        committed = json.loads(self.path.read_text(encoding="utf-8"))
        backed_up = json.loads(_bak_path(self.path).read_text(encoding="utf-8"))
        self.assertEqual(committed["cycle"], 2, "the new state must be committed")
        self.assertEqual(
            backed_up["cycle"],
            1,
            "the .bak must hold the PREVIOUS state; got the mutated one, so the "
            "rollback point was destroyed and restore() would be a no-op",
        )

    def test_restore_recovers_previous_state_after_in_place_mutation(self) -> None:
        # The consequence, stated as behavior rather than as file content.
        _write_json(self.path, {"phase": "build", "cycle": 1})

        def bump_in_place(current: dict) -> dict:
            current["cycle"] = 2
            return current

        state.transaction(self.path, bump_in_place)
        state.restore(self.path)

        recovered = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(recovered["cycle"], 1)


class TransactionBackupOrderingTest(_TempDirTestCase):
    def test_bak_holds_the_state_from_before_the_transaction(self) -> None:
        _write_json(self.path, {"phase": "build", "cycle": 1})
        before, _ = state.load(self.path)

        def fn(current: dict) -> dict:
            new = dict(current)
            new["cycle"] = 2
            return new

        state.transaction(self.path, fn)

        bak_content = json.loads(_bak_path(self.path).read_text(encoding="utf-8"))
        self.assertEqual(bak_content, before)

    def test_bak_is_one_step_behind_after_two_successive_transactions(self) -> None:
        _write_json(self.path, {"phase": "build", "cycle": 1})

        def bump(current: dict) -> dict:
            new = dict(current)
            new["cycle"] = current.get("cycle", 0) + 1
            return new

        first_committed = state.transaction(self.path, bump)
        state.transaction(self.path, bump)

        bak_content = json.loads(_bak_path(self.path).read_text(encoding="utf-8"))
        self.assertEqual(bak_content, first_committed)


class TransactionValidatorTest(_TempDirTestCase):
    def test_custom_validator_is_honored_and_commits_what_default_would_reject(
        self,
    ) -> None:
        _write_json(self.path, {"phase": "build"})

        def fn(current: dict) -> dict:
            new = dict(current)
            new["phase"] = "nonsense"
            return new

        def permissive(new_state: dict) -> None:
            return None

        # sanity: the default validator really would reject this state.
        with self.assertRaises(schema.SchemaError):
            schema.validate({"phase": "nonsense"})

        state.transaction(self.path, fn, validator=permissive)

        committed, _ = state.load(self.path)
        self.assertEqual(committed["phase"], "nonsense")

    def test_default_validator_rejects_schema_invalid_state_and_writes_nothing(
        self,
    ) -> None:
        _write_json(self.path, {"phase": "build"})
        state_before = self.path.read_bytes()

        def fn(current: dict) -> dict:
            new = dict(current)
            new["phase"] = "nonsense"
            return new

        with self.assertRaises(schema.SchemaError):
            state.transaction(self.path, fn)

        self.assertEqual(self.path.read_bytes(), state_before)


class TransactionOutputFormatTest(_TempDirTestCase):
    def test_output_is_two_space_indented_and_ends_with_a_newline(self) -> None:
        _write_json(self.path, {"phase": "build"})

        def fn(current: dict) -> dict:
            new = dict(current)
            new["cycle"] = 1
            return new

        state.transaction(self.path, fn)

        text = self.path.read_text(encoding="utf-8")
        self.assertTrue(text.endswith("\n"))
        parsed = json.loads(text)
        # Re-dumping the parsed content with indent=2 only reproduces the
        # original text if the file actually used 2-space indentation.
        self.assertEqual(text.rstrip("\n"), json.dumps(parsed, indent=2))

    def test_output_key_order_is_preserved_not_alphabetically_sorted(self) -> None:
        # "zeta" precedes "alpha" in insertion order but not alphabetically;
        # sort_keys=True would flip them.
        _write_json(self.path, {"zeta": 1, "alpha": 2})

        def fn(current: dict) -> dict:
            return dict(current)

        state.transaction(self.path, fn)

        keys = list(json.loads(self.path.read_text(encoding="utf-8")).keys())
        self.assertLess(keys.index("zeta"), keys.index("alpha"))


class TransactionConcurrencyTest(_TempDirTestCase):
    def test_two_concurrent_transactions_both_land(self) -> None:
        _write_json(self.path, {"items": []})

        barrier = multiprocessing.Barrier(2)
        p1 = multiprocessing.Process(
            target=_concurrent_append_worker,
            args=(str(self.path), barrier, "a"),
        )
        p2 = multiprocessing.Process(
            target=_concurrent_append_worker,
            args=(str(self.path), barrier, "b"),
        )
        p1.start()
        p2.start()
        p1.join(timeout=15)
        p2.join(timeout=15)

        for p in (p1, p2):
            if p.is_alive():
                p.terminate()
                p.join()

        self.assertEqual(p1.exitcode, 0, "worker process 1 did not exit cleanly")
        self.assertEqual(p2.exitcode, 0, "worker process 2 did not exit cleanly")

        committed, _ = state.load(self.path)
        self.assertEqual(sorted(committed["items"]), ["a", "b"])


class InitTest(_TempDirTestCase):
    def test_creates_file_with_given_content_when_absent_and_it_round_trips(
        self,
    ) -> None:
        initial = {"phase": "build", "cycle": 0}
        state.init(self.path, initial)

        loaded, _ = state.load(self.path)
        self.assertEqual(loaded, initial)

    def test_raises_state_exists_error_when_file_already_exists(self) -> None:
        state.init(self.path, {"phase": "build"})
        before = self.path.read_bytes()

        with self.assertRaises(state.StateExistsError):
            state.init(self.path, {"phase": "review"})

        self.assertEqual(self.path.read_bytes(), before)

    def test_created_file_is_valid_json_and_human_readable(self) -> None:
        state.init(self.path, {"zeta": 1, "alpha": 2})

        text = self.path.read_text(encoding="utf-8")
        self.assertTrue(text.endswith("\n"))
        parsed = json.loads(text)
        self.assertEqual(text.rstrip("\n"), json.dumps(parsed, indent=2))


class InitSchemaVersionStampTest(_TempDirTestCase):
    def test_stamps_schema_version_when_initial_omits_it(self) -> None:
        state.init(self.path, {"phase": "build"})

        on_disk, _ = state.load(self.path)
        self.assertEqual(
            on_disk,
            {"phase": "build", "schema_version": schema.SCHEMA_VERSION},
        )

    def test_initial_already_at_current_version_is_unchanged(self) -> None:
        initial = {"phase": "build", "schema_version": schema.SCHEMA_VERSION}
        state.init(self.path, initial)

        on_disk, _ = state.load(self.path)
        self.assertEqual(on_disk, initial)


class RestoreTest(_TempDirTestCase):
    def test_rolls_a_good_bak_back_over_a_changed_state_file(self) -> None:
        good = {"phase": "build", "cycle": 1}
        _write_json(_bak_path(self.path), good)
        _write_json(self.path, {"phase": "review", "cycle": 99})

        state.restore(self.path)

        restored, _ = state.load(self.path)
        self.assertEqual(restored, good)

    def test_raises_backup_error_when_no_bak_exists_and_leaves_state_untouched(
        self,
    ) -> None:
        _write_json(self.path, {"phase": "build"})
        before = self.path.read_bytes()

        with self.assertRaises(state.BackupError):
            state.restore(self.path)

        self.assertEqual(self.path.read_bytes(), before)

    def test_raises_backup_error_when_bak_is_not_valid_json_and_leaves_state_untouched(
        self,
    ) -> None:
        _write_json(self.path, {"phase": "build"})
        before = self.path.read_bytes()
        _bak_path(self.path).write_text("{not valid json", encoding="utf-8")

        with self.assertRaises(state.BackupError):
            state.restore(self.path)

        self.assertEqual(self.path.read_bytes(), before)

    def test_raises_backup_error_when_bak_fails_schema_validate_and_leaves_state_untouched(
        self,
    ) -> None:
        _write_json(self.path, {"phase": "build"})
        before = self.path.read_bytes()
        _write_json(_bak_path(self.path), {"phase": "nonsense"})

        with self.assertRaises(state.BackupError):
            state.restore(self.path)

        self.assertEqual(self.path.read_bytes(), before)


class RestoreSchemaVersionStampTest(_TempDirTestCase):
    def test_restore_stamps_current_schema_version_even_when_bak_is_unstamped(
        self,
    ) -> None:
        _write_json(_bak_path(self.path), {"phase": "build", "cycle": 1})
        _write_json(
            self.path,
            {"phase": "review", "cycle": 99, "schema_version": schema.SCHEMA_VERSION},
        )

        state.restore(self.path)

        restored, _ = state.load(self.path)
        self.assertEqual(restored["schema_version"], schema.SCHEMA_VERSION)
        self.assertEqual(restored["cycle"], 1)


class DurabilityBeforePublishTest(_TempDirTestCase):
    """Every write path fsyncs its payload before the rename publishes it.

    Regression for #111. os.replace makes the swap atomic against a *crash*,
    but not against power loss: the directory entry can reach disk before the
    file's data, leaving a renamed but empty state.json and a loop that
    resumes from nothing. The fsync must land while the temp fd is still open,
    so the assertion is on ordering, not merely on fsync being called.
    """

    def _publish_order(self, write, publisher: str) -> list[str]:
        """Run `write` and return the fsync/publish call sequence it produced."""
        calls: list[str] = []
        real_fsync = os.fsync
        real_publish = getattr(os, publisher)

        def spy_fsync(fd: int) -> None:
            calls.append("fsync")
            real_fsync(fd)

        def spy_publish(src, dst) -> None:
            calls.append(publisher)
            real_publish(src, dst)

        with (
            mock.patch.object(os, "fsync", spy_fsync),
            mock.patch.object(os, publisher, spy_publish),
        ):
            write()
        return calls

    def test_atomic_write_fsyncs_payload_before_replacing_the_target(self) -> None:
        calls = self._publish_order(
            lambda: state.atomic_write(self.path, {"phase": "build"}),
            "replace",
        )
        self.assertEqual(calls, ["fsync", "replace"])

    def test_transaction_fsyncs_both_the_backup_and_the_state_before_each_replace(
        self,
    ) -> None:
        _write_json(
            self.path,
            {"phase": "build", "schema_version": schema.SCHEMA_VERSION},
        )

        calls = self._publish_order(
            lambda: state.transaction(
                self.path,
                lambda current: {**current, "cycle": 2},
            ),
            "replace",
        )

        # .bak first, then the state file; neither may be published unsynced.
        self.assertEqual(calls, ["fsync", "replace", "fsync", "replace"])

    def test_init_fsyncs_payload_before_linking_the_new_state_file(self) -> None:
        calls = self._publish_order(
            lambda: state.init(self.path, {"phase": "build"}),
            "link",
        )
        self.assertEqual(calls, ["fsync", "link"])


if __name__ == "__main__":
    unittest.main()
