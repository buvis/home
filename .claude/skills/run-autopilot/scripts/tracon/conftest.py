"""Marker registration for tracon's test suite.

A conftest.py is collected per-directory regardless of pytest's rootdir, so
this registers the `ui` marker correctly whether pytest is invoked from
inside `tracon/` or from the parent `scripts/` directory (as the project's
full-suite command does).
"""

from __future__ import annotations


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "ui: Textual UI acceptance test (PRD 00061 Phase 2); requires the "
        "`textual` extra, run with `uv run --with textual --with rich "
        "--with pytest pytest .`",
    )
