"""Fail-first tests for audit-recon report.py (PRD 00046).

Pins the aggregate contract: verbatim section titles plus counts computed
from a small fixture audit.jsonl. Run: python3 -m pytest test_report.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parent / "report.py"


def _event(ts, decision, repo, size=0, stale=False):
    return {
        "ts": ts,
        "session": "s",
        "phase": "recon",
        "decision": decision,
        "repo_hash": repo,
        "atlas_excerpt_bytes": size,
        "stale": stale,
    }


FIXTURE_EVENTS = [
    # repo aaa: double-inject on 07-01 (accepted race), one stale inject 07-02
    _event("2026-07-01T08:00:00+00:00", "inject", "aaa111", size=512),
    _event("2026-07-01T09:00:00+00:00", "inject", "aaa111", size=600),
    _event("2026-07-02T08:00:00+00:00", "inject", "aaa111", size=1024, stale=True),
    # repo bbb: single inject at the cap
    _event("2026-07-03T08:00:00+00:00", "inject", "bbb222", size=1024),
    # repo ccc: atlas missing twice
    _event("2026-07-01T08:00:00+00:00", "atlas-missing", "ccc333"),
    _event("2026-07-04T08:00:00+00:00", "atlas-missing", "ccc333"),
    # unrelated phase must be ignored
    {"ts": "2026-07-01T08:00:00+00:00", "phase": "echo", "decision": "allow"},
]


class AuditReconReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / "audit.jsonl"

    def _write_fixture(self, extra_lines: list[str] | None = None) -> None:
        lines = [json.dumps(e) for e in FIXTURE_EVENTS]
        if extra_lines:
            lines.extend(extra_lines)
        self.log.write_text("\n".join(lines) + "\n")

    def _run(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(self.log)],
            capture_output=True,
            text=True,
        )

    def test_sections_and_counts(self) -> None:
        self._write_fixture(extra_lines=["{not json"])
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout
        for title in (
            "Inject uniqueness (repo x day)",
            "Missing-atlas repos",
            "Stale-at-inject rate",
            "Excerpt-size distribution",
        ):
            self.assertIn(title, out)
        self.assertIn("malformed: 1", out)
        self.assertIn("inject events: 4", out)
        self.assertIn("atlas-missing events: 2", out)
        # aaa111 x 2026-07-01 is the double-inject group
        self.assertIn("aaa111", out)
        self.assertIn("2026-07-01", out)
        self.assertIn("double-inject groups: 1", out)
        # stale rate: 1 of 4 injects
        self.assertIn("stale_pct: 25.0%", out)
        # excerpt sizes over injects: 512,600,1024,1024
        self.assertIn("min: 512", out)
        self.assertIn("max: 1024", out)
        self.assertIn("at 1024-byte cap: 2", out)

    def test_empty_log_prints_sections_with_zero_counts(self) -> None:
        self.log.write_text("")
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("no recon events", proc.stdout)
        for title in (
            "Inject uniqueness (repo x day)",
            "Missing-atlas repos",
            "Stale-at-inject rate",
            "Excerpt-size distribution",
        ):
            self.assertIn(title, proc.stdout)

    def test_missing_log_exits_zero(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(self.log.parent / "absent.jsonl")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("no recon events", proc.stdout)


if __name__ == "__main__":
    unittest.main()
