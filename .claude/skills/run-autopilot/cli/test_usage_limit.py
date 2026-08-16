"""Tests for cli/usage_limit.py's loop-side wait decision (PRD 00106).

Detection itself is covered by scripts/test_detect_usage_limit.py, which
loads scripts/detect_usage_limit.py by path — now a re-export shim over
this module, so that whole suite exercises the absorbed implementation.
Here: the branch-5 arithmetic the wrapper used to do inline, plus the
shim's same-object guarantee.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from cli import usage_limit


def test_wait_is_reset_minus_now_plus_margin():
    assert usage_limit.wait_decision(1000, now=400, max_wait_secs=21600) == 720


def test_wait_floors_at_sixty_seconds():
    # A reset that just passed still sleeps the minimum, never 0 or negative.
    assert usage_limit.wait_decision(1000, now=1500, max_wait_secs=21600) == 60


def test_wait_at_the_cap_boundary_still_waits():
    # Bash used -le: a wait exactly equal to the cap is honored.
    assert usage_limit.wait_decision(1000, now=880, max_wait_secs=240) == 240


def test_wait_beyond_cap_is_refused():
    assert usage_limit.wait_decision(100000, now=0, max_wait_secs=21600) is None


def test_scripts_shim_reexports_the_same_objects():
    shim_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "detect_usage_limit.py"
    )
    spec = importlib.util.spec_from_file_location("detect_usage_limit_shim", shim_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.detect_from_log is usage_limit.detect_from_log
    assert module.detect is usage_limit.detect
