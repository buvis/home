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
import sys
import tempfile
import unittest
from pathlib import Path

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
        _write_json(self.path, {"schema_version": schema.SCHEMA_VERSION, "phase": "build"})
        loaded, version_status = state.load(self.path)
        self.assertEqual(loaded, {"schema_version": schema.SCHEMA_VERSION, "phase": "build"})
        self.assertEqual(version_status, "current")

    def test_raises_state_error_for_missing_file(self) -> None:
        with self.assertRaises(state.StateError):
            state.load(self.dir / "nope.json")

    def test_raises_state_error_for_invalid_json(self) -> None:
        self.path.write_text("{not valid json", encoding="utf-8")
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
    def test_custom_validator_is_honored_and_commits_what_default_would_reject(self) -> None:
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

    def test_default_validator_rejects_schema_invalid_state_and_writes_nothing(self) -> None:
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
            target=_concurrent_append_worker, args=(str(self.path), barrier, "a")
        )
        p2 = multiprocessing.Process(
            target=_concurrent_append_worker, args=(str(self.path), barrier, "b")
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
    def test_creates_file_with_given_content_when_absent_and_it_round_trips(self) -> None:
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


class RestoreTest(_TempDirTestCase):
    def test_rolls_a_good_bak_back_over_a_changed_state_file(self) -> None:
        good = {"phase": "build", "cycle": 1}
        _write_json(_bak_path(self.path), good)
        _write_json(self.path, {"phase": "review", "cycle": 99})

        state.restore(self.path)

        restored, _ = state.load(self.path)
        self.assertEqual(restored, good)

    def test_raises_backup_error_when_no_bak_exists_and_leaves_state_untouched(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
