"""Parity between the two halves of the autopilot write-scope fence (PRD 00145).

hooks/enforce_write_scope.py gates Edit/Write/MultiEdit/NotebookEdit; the
warden plugin (claude-warden src/write-scope.ts) gates Bash. Both derive one
root set from the session cwd and refuse with one reason line. This suite
drives the LIVE warden hook (the installed plugin's dist/index.cjs; override
with WARDEN_HOOK_BIN while developing) and the Python hook against the same
fixture, and fails when they disagree: the split-brain guard the two-point
design needs. A missing warden binary fails loudly here, never skips.

Both sides run under a sandbox HOME so the root floor and `~` are under test
control and warden's real audit log and notifier stay untouched; the real
warden.yaml is copied into the sandbox with audit and notifications forced off,
so the in-scope corpus is judged by the rules a batch really runs under.
"""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HOOKS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOOKS_DIR))

_SPEC = importlib.util.spec_from_file_location(
    "enforce_write_scope",
    HOOKS_DIR / "enforce_write_scope.py",
)
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)

REAL_HOME = Path.home()
CLAUDE_REPO = HOOKS_DIR.parent
RULES_FILE = CLAUDE_REPO / "rules" / "claude-tooling.md"
ROOTS_RE = re.compile(r"allowed scope \((.*?)\)\. Write inside")


def _warden_hook() -> Path:
    override = os.environ.get("WARDEN_HOOK_BIN")
    if override:
        return Path(override)
    registry = json.loads(
        (REAL_HOME / ".claude" / "plugins" / "installed_plugins.json").read_text(),
    )
    install = registry["plugins"]["warden@buvis-plugins"][0]["installPath"]
    return Path(install) / "dist" / "index.cjs"


WARDEN_HOOK = _warden_hook()
NODE = shutil.which("node")


def _warden_has_fence() -> bool:
    """True when the resolved warden hook carries the Bash write-scope fence.

    The installed plugin lags the source until it is released and updated
    (`/plugin update warden@buvis-plugins`); an older binary has no fence, so an
    armed out-of-scope write returns `allow`. Probing once lets the suite SKIP
    with a pointed message instead of failing confusingly, while a WARDEN_HOOK_BIN
    override (the dev build) and a freshly-installed plugin both run it for real.
    """
    if not (WARDEN_HOOK.is_file() and NODE):
        return False
    with tempfile.TemporaryDirectory() as d:
        home = Path(d) / "home"
        (home / ".claude").mkdir(parents=True)
        payload = {
            "session_id": "probe",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": f"echo x > {d}/out-of-scope.txt"},
            "cwd": str(home),
            "permission_mode": "auto",
        }
        proc = subprocess.run(
            [NODE, str(WARDEN_HOOK)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=30,
            env={
                **os.environ,
                "HOME": str(home),
                "TMPDIR": str(Path(d) / "tmp"),
                "WARDEN_YOLO": "",
                "CLAUDE_UNATTENDED": "1",
                "_AUTOPILOT_WRITE_SCOPE": "",
                "_AUTOPILOT_WRITE_SCOPE_EXTRA": "",
            },
        )
        return "write-scope fence" in (proc.stdout + proc.stderr)


WARDEN_HAS_FENCE = _warden_has_fence()
SKIP_REASON = (
    f"the resolved warden hook ({WARDEN_HOOK}) predates the Bash write-scope "
    "fence; release warden and run `/plugin update warden@buvis-plugins`, or set "
    "WARDEN_HOOK_BIN to the built dist, then this parity gate runs for real"
)


def roots_in(reason: str) -> list[str]:
    """The root list a fence reason names, in order."""
    match = ROOTS_RE.search(reason)
    assert match, f"no root list in reason: {reason!r}"
    return [root.strip("'") for root in match.group(1).split(", ")]


class ParityCase(unittest.TestCase):
    def setUp(self) -> None:
        if not WARDEN_HAS_FENCE:
            self.skipTest(SKIP_REASON)
        self.assertTrue(WARDEN_HOOK.is_file(), f"warden hook missing: {WARDEN_HOOK}")
        self.assertIsNotNone(NODE, "node not on PATH (mise reshim?)")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(os.path.realpath(tmp.name))
        self.repo = self.base / "repo"
        (self.repo / "dev" / "local" / "autopilot").mkdir(parents=True)
        (self.repo / "sub").mkdir()
        (self.repo / "src").mkdir()
        self.tmpdir = self.base / "tmproot"
        self.tmpdir.mkdir()
        self.home = self.base / "home"
        (self.home / ".claude").mkdir(parents=True)
        self.outside = self.base / "other-repo"
        self.outside.mkdir()
        config = (REAL_HOME / ".claude" / "warden.yaml").read_text()
        config = re.sub(
            r"(?m)^(notifyOnAsk|notifyOnDeny|auditAllowDecisions|audit):.*$",
            r"\1: false",
            config,
        )
        (self.home / ".claude" / "warden.yaml").write_text(config + "\naudit: false\n")

    def env(self, **overrides: str) -> dict[str, str]:
        env = {
            "HOME": str(self.home),
            "TMPDIR": str(self.tmpdir),
            "CLAUDE_UNATTENDED": "1",
            "_AUTOPILOT_WRITE_SCOPE": "",
            "_AUTOPILOT_WRITE_SCOPE_EXTRA": "",
        }
        env.update(overrides)
        return env

    def warden(self, command: str, cwd: Path, **overrides: str) -> tuple[str, str, str]:
        """(decision, reason, stderr) from the live warden hook for one Bash call."""
        payload = {
            "session_id": "write-scope-parity",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "cwd": str(cwd),
            "permission_mode": "auto",
        }
        proc = subprocess.run(
            [NODE, str(WARDEN_HOOK)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "WARDEN_YOLO": "", **self.env(**overrides)},
        )
        out = json.loads(proc.stdout) if proc.stdout.strip() else {}
        specific = out.get("hookSpecificOutput", {})
        return (
            specific.get("permissionDecision", ""),
            specific.get("permissionDecisionReason", ""),
            proc.stderr,
        )

    def hook(self, target: str, cwd: Path, **overrides: str) -> tuple[int, str]:
        """(exit code, stderr) from the Python hook for one Write of `target`."""
        payload = {
            "tool_name": "Write",
            "tool_input": {"file_path": target},
            "cwd": str(cwd),
        }
        with patch.dict(os.environ, self.env(**overrides), clear=True):
            with patch.object(mod, "TMP_ROOTS", ("/tmp",)):
                code, _out, err = mod.run(payload)
        return code, err

    def warden_roots(self, cwd: Path, **overrides: str) -> list[str]:
        decision, reason, _err = self.warden(
            f"echo x > {self.outside / 'probe.txt'}",
            cwd,
            **overrides,
        )
        self.assertEqual(decision, "deny", reason)
        return roots_in(reason)

    def hook_roots(self, cwd: Path, **overrides: str) -> list[str]:
        code, err = self.hook(str(self.outside / "probe.txt"), cwd, **overrides)
        self.assertEqual(code, 2, err)
        return roots_in(err)


class TestSharedRootSet(ParityCase):
    def test_both_enforcement_points_compute_one_root_set(self) -> None:
        cwd = self.repo / "sub"
        expected = [
            str(self.repo),
            str(self.repo / "dev" / "local"),
            str(self.tmpdir),
            os.path.realpath("/tmp"),
        ]
        self.assertEqual(self.hook_roots(cwd), expected)
        self.assertEqual(self.warden_roots(cwd), expected)

    def test_extra_roots_widen_both_points_alike(self) -> None:
        extra = self.base / "extra"
        extra.mkdir()
        widened = {"_AUTOPILOT_WRITE_SCOPE_EXTRA": f"~/notes:{extra}"}
        (self.home / "notes").mkdir()
        self.assertEqual(
            self.hook_roots(self.repo, **widened),
            self.warden_roots(self.repo, **widened),
        )
        self.assertIn(str(extra), self.warden_roots(self.repo, **widened))

    def test_parity_check_bites_on_a_deliberate_skew(self) -> None:
        # Widen warden alone: the comparison the two tests above rely on must
        # report the difference, or a real drift would pass unnoticed.
        extra = self.base / "extra"
        extra.mkdir()
        skewed = self.warden_roots(self.repo, _AUTOPILOT_WRITE_SCOPE_EXTRA=str(extra))
        self.assertNotEqual(self.hook_roots(self.repo), skewed)
        self.assertEqual(skewed[:-1], self.hook_roots(self.repo))


class TestSharedCorpus(ParityCase):
    def test_out_of_scope_writes_are_denied_by_both_points(self) -> None:
        target = self.outside / "file.py"
        bash_corpus = [
            f"echo x > {target}",
            "echo x > /tmp/../etc/out-of-scope.txt",
            "sed -i '' s/a/b/ ../../other-repo/file.py",
            f"cp src/foo.py {target}",
            f"mv src/foo.py {target}",
            f"tee {target}",
            f"install -m 644 src/foo.py {target}",
            f"dd if=/dev/zero of={target} count=1",
            f"mkdir -p {self.outside / 'new'}",
            f"touch {target}",
            f"bash -c 'echo x > {target}'",
            f"cd {self.outside} && echo x > file.py",
            "echo x > ~/notes/x.md",
        ]
        cwd = self.repo / "sub"
        for command in bash_corpus:
            with self.subTest(command=command):
                decision, reason, err = self.warden(command, cwd)
                self.assertEqual(decision, "deny", f"{command}: {reason}")
                self.assertIn("BLOCKED: autopilot write-scope fence:", reason)
                self.assertIn("BLOCKED: autopilot write-scope fence:", err)
        for edit_target in (
            str(target),
            "/tmp/../etc/out-of-scope.txt",
            "../../other-repo/file.py",
            "~/notes/x.md",
        ):
            with self.subTest(edit_target=edit_target):
                code, err = self.hook(edit_target, cwd)
                self.assertEqual(code, 2, err)

    def test_in_scope_batch_corpus_stays_allowed(self) -> None:
        # Real commands from batch transcripts (warden audit log, 2026-08),
        # judged from the real ~/.claude session repo whose dev/local is a
        # symlink: every one must resolve inside the scope. A false deny here
        # is the failure mode that stalls a batch with nobody watching.
        claude_dev = os.path.realpath(CLAUDE_REPO / "dev" / "local")
        corpus = [
            "uv run --with pytest --with tree-sitter-language-pack pytest "
            "/Users/bob/.claude/hooks/tests/ -q --no-header -p no:cacheprovider "
            ">/tmp/final-suite-cycle1.txt",
            "uv run --with pytest pytest /Users/bob/.claude/skills/run-autopilot/cli -q "
            '> /tmp/final-cli.txt; echo "rc=$?"',
            "uv run --with pytest --with rich --with textual pytest "
            "/Users/bob/.claude/skills/run-autopilot -q > /tmp/pytest-runautopilot.log 2>&1; "
            'echo "rc=$?"',
            "python3 -m unittest discover -s /Users/bob/.claude/skills/run-autopilot/scripts "
            "-p 'test_*.py' > /tmp/testrun-scripts.txt; echo \"rc=$?\"",
            "python3 /Users/bob/.claude/skills/review-prd-backlog/scripts/check_links.py "
            "--root /Users/bob/.claude --json > /private/tmp/claude-501/-Users-bob--claude/"
            "644fc591-a465-43af-9133-a91c69f1fa12/scratchpad/check-links.json",
            "sed -n '1,$p' /tmp/review-00132-c1-context.md >> /tmp/bob-prompt-00132-c1.md",
            "sed -n '1000,1115p' /Users/bob/.claude/skills/run-autopilot/cli/test_loop.py "
            "> /Users/bob/.claude/dev/local/tmp/tess-3-sample-tests.py",
            "sed -n 'p' /Users/bob/.claude/skills/review-work-completion/references/rubric.md "
            ">> /tmp/carl-prompt-00127-c1.md",
            "sed -i '' 's|~/\\.claude/metrics|~/.local/share/agents/metrics|g' "
            "/Users/bob/.claude/hooks/track_cost.py /Users/bob/.claude/hooks/track_skills.py",
            f"touch {claude_dev}/designs/00029-cartographer-evaluate-phase-4-6-reactivation-v1-design.md",
            "rm -rf /tmp/blake-f17 && mkdir -p /tmp/blake-f17",
            "rm -rf /tmp/csl_repro && mkdir -p /tmp/csl_repro && cp -r "
            "/Users/bob/git/src/github.com/buvis/claude-autopilot/skills /tmp/csl_repro/skills "
            "&& echo copied",
            # Was skills/brief-portfolio/app/node_modules until that skill became
            # a braid link into the agent-skills repo (2026-08-25); writes through
            # the link farm are out of scope by design, so the fixture moved to a
            # directory that stays inside the repo.
            "test -d /Users/bob/.claude/hooks/tests/node_modules && echo EXISTS "
            "|| mkdir -p /Users/bob/.claude/hooks/tests/node_modules",
            "wc -c /Users/bob/.claude/hooks/_common.py",
            'rg -n "def run" /Users/bob/.claude/hooks/dispatch.py',
            "engram query --scope repo 'bim split the cli.py god registry' -k 5",
            "git --git-dir=/Users/bob/.buvis --work-tree=/Users/bob log --oneline -3",
            "mkdir -p dev/local/tmp",
            "echo x > dev/local/tmp/x.txt",
            "tee dev/local/tmp/dispatch-ivan-1.txt",
            "mv dev/local/prds/backlog/00145-close-bash-hole-in-write-fence-v1.md "
            "dev/local/prds/wip/00145-close-bash-hole-in-write-fence-v1.md",
            "cp /Users/bob/.claude/hooks/_common.py /tmp/review-00145/_common.py",
            "cat /etc/hosts",
            "rg foo /etc/hosts",
            "ls /Users/bob/.claude/dev/local/prds/backlog",
        ]
        self.assertGreaterEqual(len(corpus), 20)
        for command in corpus:
            with self.subTest(command=command):
                decision, reason, err = self.warden(command, CLAUDE_REPO)
                self.assertEqual(decision, "allow", f"{command}: {reason} {err}")

    def test_kill_switch_disarms_both_points_and_both_say_so(self) -> None:
        target = self.outside / "x.txt"
        decision, _reason, err = self.warden(
            f"echo x > {target}",
            self.repo,
            _AUTOPILOT_WRITE_SCOPE="off",
        )
        self.assertEqual(decision, "allow")
        self.assertIn("write-scope fence disarmed by _AUTOPILOT_WRITE_SCOPE=off", err)
        code, err = self.hook(str(target), self.repo, _AUTOPILOT_WRITE_SCOPE="off")
        self.assertEqual(code, 0)
        self.assertIn("disarmed by _AUTOPILOT_WRITE_SCOPE=off", err)

    def test_unarmed_session_sees_neither_point(self) -> None:
        target = self.outside / "x.txt"
        decision, _reason, err = self.warden(
            f"echo x > {target}",
            self.repo,
            CLAUDE_UNATTENDED="",
        )
        self.assertEqual(decision, "allow")
        self.assertEqual(err, "")
        code, err = self.hook(str(target), self.repo, CLAUDE_UNATTENDED="")
        self.assertEqual((code, err), (0, ""))


class TestRulesDocument(unittest.TestCase):
    def test_rules_file_names_both_enforcement_points(self) -> None:
        text = RULES_FILE.read_text()
        self.assertIn("hooks/enforce_write_scope.py", text)
        self.assertIn("claude-warden/src/write-scope.ts", text)
        self.assertIn("test_write_scope_parity.py", text)


if __name__ == "__main__":
    unittest.main()
