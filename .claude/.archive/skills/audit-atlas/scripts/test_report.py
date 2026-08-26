"""Fail-first tests for audit-atlas report.py (PRD 00046).

Pins the aggregate contract: verbatim section titles plus counts computed
from a fixture projects dir. Run: python3 -m pytest test_report.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT = Path(__file__).parent / "report.py"


class AuditAtlasReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.projects = Path(self.tmp.name) / "projects"
        self.projects.mkdir()
        self.instincts = Path(self.tmp.name) / "projects.json"

    def _atlas(
        self,
        name: str,
        age_days: int,
        flag: bool = False,
        md_bytes: int = 100,
        layers: dict | None = None,
        degraded: bool = False,
        enriched: bool = True,
    ) -> None:
        d = self.projects / name
        d.mkdir()
        surveyed = datetime.now(timezone.utc) - timedelta(days=age_days)
        data = {
            "head_sha": "abc",
            "surveyed_at": surveyed.isoformat(),
            "layers": layers if layers is not None else {"core": {"files": ["a.py"]}},
            "forbidden_imports": ["x"] if enriched else [],
            "naming": {"style": "snake"} if enriched else {},
            "error_style": "exceptions" if enriched else "",
            "dependency_edges": [["a", "b"]] if enriched else [],
        }
        if degraded:
            data["degraded"] = True
        (d / "atlas.json").write_text(json.dumps(data))
        (d / "atlas.md").write_text("x" * md_bytes)
        if flag:
            (d / "staleness.flag").touch()

    def _run(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(self.projects), str(self.instincts)],
            capture_output=True,
            text=True,
        )

    def test_sections_and_counts(self) -> None:
        # fresh + enriched + populated
        self._atlas("fresh1", age_days=2)
        # stale (flag + old), over budget, degraded, unenriched, empty layer
        self._atlas(
            "stale1",
            age_days=20,
            flag=True,
            md_bytes=6000,
            layers={"core": {"files": []}},
            degraded=True,
            enriched=False,
        )
        active = [
            {"hash": "fresh1", "path": "/x", "last_active": datetime.now(timezone.utc).isoformat()},
            {"hash": "stale1", "path": "/y", "last_active": datetime.now(timezone.utc).isoformat()},
        ]
        self.instincts.write_text(json.dumps(active))

        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout
        for title in (
            "Fresh-atlas coverage",
            "Staleness distribution",
            "Atlas size",
            "Layer population",
        ):
            self.assertIn(title, out)
        self.assertIn("total atlases: 2", out)
        self.assertIn("fresh: 1", out)
        self.assertIn("stale: 1", out)
        self.assertIn("active_fresh_pct: 50.0%", out)
        self.assertIn("over 5KB budget: 1", out)
        self.assertIn("degraded (tree-sitter fallback): 1", out)
        self.assertIn("under-enriched: 1", out)
        # stale1's single layer has no files -> 0% populated flagged
        self.assertIn("stale1", out)

    def test_empty_projects_dir_prints_sections(self) -> None:
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("no atlases found", proc.stdout)
        for title in (
            "Fresh-atlas coverage",
            "Staleness distribution",
            "Atlas size",
            "Layer population",
        ):
            self.assertIn(title, proc.stdout)

    def test_malformed_atlas_counted_not_fatal(self) -> None:
        d = self.projects / "broken"
        d.mkdir()
        (d / "atlas.json").write_text("{not json")
        self._atlas("fresh1", age_days=1)
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("malformed: 1", proc.stdout)
        self.assertIn("total atlases: 1", proc.stdout)


if __name__ == "__main__":
    unittest.main()
