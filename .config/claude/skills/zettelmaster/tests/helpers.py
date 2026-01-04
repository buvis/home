#!/usr/bin/env python3
"""Test helpers for constructing orchestrator instances."""

import tempfile
from pathlib import Path

from zettelmaster.simplified_orchestrator import SimplifiedOrchestrator


def build_temp_orchestrator() -> SimplifiedOrchestrator:
    """
    Create a SimplifiedOrchestrator with temporary inbox/synthetic/processed dirs.

    A reference to the underlying TemporaryDirectory is kept on the orchestrator
    to prevent premature cleanup while tests run.
    """
    temp_dir = tempfile.TemporaryDirectory()
    base = Path(temp_dir.name)

    inbox_dir = base / "inbox"
    synthetic_dir = base / "synthetic"
    processed_dir = base / "processed"

    inbox_dir.mkdir()
    synthetic_dir.mkdir()
    processed_dir.mkdir()

    orchestrator = SimplifiedOrchestrator(inbox_dir, synthetic_dir, processed_dir)
    orchestrator._temp_dir = temp_dir  # type: ignore[attr-defined]
    return orchestrator
