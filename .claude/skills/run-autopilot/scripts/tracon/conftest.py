"""Marker registration and machine-state isolation for tracon's test suite.

A conftest.py is collected per-directory regardless of pytest's rootdir, so
this registers the `ui` marker correctly whether pytest is invoked from
inside `tracon/` or from the parent `scripts/` directory (as the project's
full-suite command does).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from tracon import discovery


@pytest.fixture(autouse=True)
def isolated_loops_dir(tmp_path_factory, monkeypatch):
    """Point discovery.LOOPS_DIR at an empty dir for every test.

    discover_loops() and wrapper_alive() read the wrapper registry by
    default, so a real autoclaude loop running on the developer's machine
    would otherwise leak its root into any test asserting discover_loops()
    output. Tests that exercise the registry pass loops_dir explicitly and
    are unaffected.
    """
    monkeypatch.setattr(
        discovery, "LOOPS_DIR", tmp_path_factory.mktemp("empty-loops")
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "ui: Textual UI acceptance test (PRD 00061 Phase 2); requires the "
        "`textual` extra, run with `uv run --with textual --with rich "
        "--with pytest pytest .`",
    )
