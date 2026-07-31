"""Halt-guarantee tests for autopilot_context_cap_hook.py (task D1).

The cap hook's "broken writer stops the loop" guarantee: when the cli/state
transaction boundary is broken in ANY way, the hook must never raise into
the harness and must always write the last-resort state-write-failed halt
marker so the loop wrapper stops loudly. Today this is proven only for the
ImportError case; these tests widen the pin to:

  1. `_import_cli_state` surviving a NON-ImportError exception at import
     time (a syntax-broken cli/state.py, an AttributeError mid-import, ...).
  2. `_set_oversized_stall` writing the marker and returning False on BOTH
     of its failure branches (cli boundary unimportable; boundary imports
     fine but the locked transaction itself raises).
  3. `_set_oversized_stall`'s failure-path diagnostic naming the
     oversized-stall operation specifically, not the stale "rotation
     envelope" phrasing that belongs to the rotation path.

Written without having seen the implementation. Follows the importlib-by-
path loader and sys.modules-poisoning conventions from
test_autopilot_cap_rotation.py's StateWriteFailedMarkerTests.
"""

import importlib.util
import io
import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

HOOK_PATH = Path(__file__).resolve().parent / "autopilot_context_cap_hook.py"


def _load_hook_module_for_test():
    """Load autopilot_context_cap_hook.py fresh, by file path (same idiom as
    test_autopilot_cap_rotation.py's _load_hook_module_for_test)."""
    spec = importlib.util.spec_from_file_location(
        "autopilot_context_cap_hook_under_test", HOOK_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_and_assert_marker(autopilot_dir: Path) -> dict:
    """Shared marker-shape assertion, reused by both test classes below:
    exactly one line of JSON, site == "statectl_fail", non-empty detail."""
    marker_path = autopilot_dir / "state-write-failed"
    assert marker_path.exists(), "state-write-failed marker was not written"
    lines = marker_path.read_text(encoding="utf-8").strip("\n").splitlines()
    assert len(lines) == 1, f"marker must be exactly one line, got {lines!r}"
    payload = json.loads(lines[0])
    assert payload.get("site") == "statectl_fail", payload
    detail = payload.get("detail")
    assert isinstance(detail, str) and detail != "", payload
    return payload


class _RaisingMetaPathFinder:
    """A meta path finder that raises a chosen exception the moment anything
    tries to import one of `target_fullnames`, simulating a NON-ImportError
    failure at import time (e.g. a syntax-broken module, or an AttributeError
    surfacing mid-import). Exceptions raised from find_spec propagate
    straight through the `import`/`from ... import ...` statement unwrapped
    - unlike the sys.modules-poisoning trick (`sys.modules["cli"] = None`),
    which the import system hardcodes to always raise ImportError."""

    def __init__(self, target_fullnames, exc: BaseException) -> None:
        self._targets = set(target_fullnames)
        self._exc = exc

    def find_spec(self, fullname, path, target=None):
        if fullname in self._targets:
            raise self._exc
        return None


class ImportCliStateNonImportErrorTests(unittest.TestCase):
    """`_import_cli_state` must uphold the halt guarantee for ANY exception
    at import time, not just ImportError (which existing tests already
    cover)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.autopilot_dir = Path(self._tmp.name) / "autopilot"
        self.autopilot_dir.mkdir(parents=True)

        # Evict any cached "cli"/"cli.state" modules so a poisoned meta path
        # finder is actually consulted, and restore whatever was cached
        # afterward so this test cannot poison later tests in the suite.
        saved = {
            name: sys.modules.pop(name)
            for name in ("cli", "cli.state")
            if name in sys.modules
        }
        self.addCleanup(sys.modules.update, saved)
        for name in ("cli", "cli.state"):
            sys.modules.pop(name, None)

    def _poison(self, exc: BaseException) -> None:
        finder = _RaisingMetaPathFinder({"cli", "cli.state"}, exc)
        sys.meta_path.insert(0, finder)
        self.addCleanup(sys.meta_path.remove, finder)

    def test_attribute_error_at_import_returns_none_and_writes_marker(self) -> None:
        """An AttributeError raised while importing cli/state.py (e.g. the
        module body references a name that no longer exists) must not
        propagate: _import_cli_state returns None and the halt marker is
        written, exactly as the ImportError case already does."""
        self._poison(AttributeError("cli.state has no attribute 'transaction'"))
        module = _load_hook_module_for_test()

        result = module._import_cli_state("cap_hook_test", self.autopilot_dir)

        self.assertIsNone(result)
        _read_and_assert_marker(self.autopilot_dir)

    def test_attribute_error_at_import_prints_stderr_warning(self) -> None:
        self._poison(AttributeError("cli.state has no attribute 'transaction'"))
        module = _load_hook_module_for_test()

        with unittest.mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            module._import_cli_state("cap_hook_test", self.autopilot_dir)

        self.assertNotEqual(stderr.getvalue().strip(), "")

    def test_syntax_error_at_import_also_returns_none_and_writes_marker(self) -> None:
        """The guard must be exception-type-agnostic, not hardcoded to
        AttributeError: a SyntaxError (the shape a syntax-broken
        cli/state.py actually raises) gets the same treatment."""
        self._poison(SyntaxError("invalid syntax in cli/state.py"))
        module = _load_hook_module_for_test()

        result = module._import_cli_state("cap_hook_test", self.autopilot_dir)

        self.assertIsNone(result)
        _read_and_assert_marker(self.autopilot_dir)


class SetOversizedStallMarkerTests(unittest.TestCase):
    """`_set_oversized_stall`'s two failure branches (cli boundary
    unimportable; boundary imports fine but the locked transaction raises)
    must each write the halt marker and return False, and the marker/stderr
    diagnostic must name the oversized-stall operation - not the stale
    "rotation envelope" phrasing that belongs to _append_rotation_to_state."""

    def _write_state(self, autopilot_dir: Path, text: str) -> Path:
        autopilot_dir.mkdir(parents=True, exist_ok=True)
        state_path = autopilot_dir / "state.json"
        state_path.write_text(text, encoding="utf-8")
        return state_path

    def test_cli_unimportable_writes_marker_naming_oversized_stall(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            autopilot_dir = Path(tmp) / "autopilot"
            self._write_state(autopilot_dir, json.dumps({"cycle": 1}))

            module = _load_hook_module_for_test()
            with unittest.mock.patch.dict(
                sys.modules, {"cli": None, "cli.state": None}
            ):
                with unittest.mock.patch(
                    "sys.stderr", new_callable=io.StringIO
                ) as stderr:
                    ok = module._set_oversized_stall(autopilot_dir, "task-x", 700_000)

            self.assertFalse(ok)
            payload = _read_and_assert_marker(autopilot_dir)
            detail_lower = payload["detail"].lower()
            self.assertIn("oversized", detail_lower)
            self.assertNotIn("rotation envelope", detail_lower)
            stderr_lower = stderr.getvalue().lower()
            self.assertIn("oversized", stderr_lower)
            self.assertNotIn("rotation envelope", stderr_lower)

    def test_transaction_failure_on_corrupt_state_writes_marker_naming_oversized_stall(
        self,
    ) -> None:
        """No import poisoning: state.json itself is invalid JSON, so the
        cli boundary imports fine but the locked transaction raises."""
        with tempfile.TemporaryDirectory() as tmp:
            autopilot_dir = Path(tmp) / "autopilot"
            self._write_state(autopilot_dir, "{not valid")

            module = _load_hook_module_for_test()
            with unittest.mock.patch(
                "sys.stderr", new_callable=io.StringIO
            ) as stderr:
                ok = module._set_oversized_stall(autopilot_dir, "task-x", 700_000)

            self.assertFalse(ok)
            payload = _read_and_assert_marker(autopilot_dir)
            detail_lower = payload["detail"].lower()
            self.assertIn("oversized", detail_lower)
            self.assertNotIn("rotation envelope", detail_lower)
            stderr_lower = stderr.getvalue().lower()
            self.assertIn("oversized", stderr_lower)
            self.assertNotIn("rotation envelope", stderr_lower)

    def test_transaction_failure_on_missing_state_file_writes_marker(self) -> None:
        """Missing state.json (not merely corrupt) is the other named
        trigger for the transaction-raises branch."""
        with tempfile.TemporaryDirectory() as tmp:
            autopilot_dir = Path(tmp) / "autopilot"
            autopilot_dir.mkdir(parents=True)
            # No state.json written at all.

            module = _load_hook_module_for_test()
            ok = module._set_oversized_stall(autopilot_dir, "task-x", 700_000)

            self.assertFalse(ok)
            payload = _read_and_assert_marker(autopilot_dir)
            self.assertIn("oversized", payload["detail"].lower())


if __name__ == "__main__":
    unittest.main()
