"""PRD 00150: the buvis shell front-end (`autopilot`, `autoclaude`, `tracon`,
the Fable verbs in ~/.config/bash/plugins/development.plugin.bash) must locate
the autopilot skill inside the INSTALLED plugin cache, not the
`~/.claude/skills/run-autopilot` path the 2026-08-25 extraction removed.

Drives the real plugin file through `bash -c` with `HOME` pointed at a temp
dir holding a fake plugin cache. `cite`/`about-plugin` (bash-it) are stubbed
the way the plugin repo's own bash suites stub them.

Stdlib-only unittest; runs under the hooks suite's usual
`uv run --with pytest --with tree-sitter-language-pack pytest hooks/tests`.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

_PLUGIN = Path.home() / ".config" / "bash" / "plugins" / "development.plugin.bash"
_CACHE_REL = Path(".claude") / "plugins" / "cache" / "buvis-plugins" / "autopilot"


def _run(home: Path, body: str, **env_extra: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "_AUTOPILOT_SKILL_ROOT"}
    env["HOME"] = str(home)
    env.update(env_extra)
    script = f"cite() {{ :; }}; about-plugin() {{ :; }}; source '{_PLUGIN}'; {body}"
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def _install(home: Path, version: str, with_cli: bool = True) -> Path:
    skill = home / _CACHE_REL / version / "skills" / "run-autopilot"
    (skill / "scripts").mkdir(parents=True)
    if with_cli:
        (skill / "cli").mkdir()
        (skill / "cli" / "__main__.py").write_text("")
    return skill


class SkillRootResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_picks_the_highest_version_numerically(self) -> None:
        _install(self.home, "0.1.2")
        expected = _install(self.home, "0.1.10")
        proc = _run(self.home, "_autopilot_skill_root")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), str(expected))

    def test_skips_a_version_dir_without_the_cli(self) -> None:
        expected = _install(self.home, "0.1.2")
        _install(self.home, "0.2.0", with_cli=False)
        proc = _run(self.home, "_autopilot_skill_root")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), str(expected))

    def test_empty_cache_fails_with_one_stderr_line_and_no_stdout(self) -> None:
        proc = _run(self.home, "_autopilot_skill_root")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "")
        self.assertIn("no autopilot plugin installed", proc.stderr)
        self.assertEqual(len(proc.stderr.strip().splitlines()), 1)

    def test_legacy_skill_path_is_used_only_when_no_plugin_is_installed(self) -> None:
        legacy = self.home / ".claude" / "skills" / "run-autopilot"
        (legacy / "cli").mkdir(parents=True)
        (legacy / "cli" / "__main__.py").write_text("")
        proc = _run(self.home, "_autopilot_skill_root")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), str(legacy))

    def test_installed_plugin_shadows_the_legacy_skill_path(self) -> None:
        legacy = self.home / ".claude" / "skills" / "run-autopilot"
        (legacy / "cli").mkdir(parents=True)
        (legacy / "cli" / "__main__.py").write_text("")
        expected = _install(self.home, "0.1.2")
        proc = _run(self.home, "_autopilot_skill_root")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), str(expected))

    def test_override_wins_without_consulting_the_cache(self) -> None:
        proc = _run(self.home, "_autopilot_skill_root", _AUTOPILOT_SKILL_ROOT="/x")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "/x")

    def test_autopilot_verb_fails_cleanly_without_a_plugin(self) -> None:
        proc = _run(self.home, "autopilot status")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("no autopilot plugin installed", proc.stderr)
        self.assertNotIn("can't open file", proc.stderr)
        self.assertNotIn("skills/run-autopilot/cli", proc.stderr)


if __name__ == "__main__":
    unittest.main()
