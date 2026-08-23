"""Tests for hooks/enforce_write_scope.py, the autopilot write-scope fence.

Incident-bound (batch 202608180438, 2026-08-18): an unattended subagent edited
/Users/bob/bim/inbox/dmz/debrief-meeting/debrief-meeting/app/smoke.test.js in
the user's zettelkasten vault, which a sync daemon auto-committed and pushed.

Fixtures deliberately sit OUTSIDE every allowed root. Each case neutralizes the
static temp roots (patch.object(mod, "TMP_ROOTS", ())) and points TMPDIR at a
dedicated fixture subdirectory, so roots 1 and 2 (the repo and its dev/local) do
the discriminating work. Without that seam a fixture built under the machine's
TMPDIR is allowed by root 3 outright and the whole suite goes tautological.
Cases 7 and 8 are the only ones that exercise a temp root, one root each. The
one subprocess case cannot patch a module global and does not need to: it only
asserts a denial, and the seam guards allow-tautologies.
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _common

HOOKS_DIR = Path(__file__).resolve().parents[1]

_SPEC = importlib.util.spec_from_file_location(
    "enforce_write_scope", HOOKS_DIR / "enforce_write_scope.py"
)
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)

MARKER_ENV = "CLAUDE_UNATTENDED"
KILL_SWITCH_ENV = "_AUTOPILOT_WRITE_SCOPE"
EXTRA_ROOTS_ENV = "_AUTOPILOT_WRITE_SCOPE_EXTRA"

VAULT_PATH = (
    "/Users/bob/bim/inbox/dmz/debrief-meeting/debrief-meeting/app/smoke.test.js"
)
IN_REPO_PATH = "/Users/bob/.claude/skills/debrief-meeting/app/smoke.test.js"
OUT_OF_SCOPE = "/Users/bob/bim/x.js"


class WriteScopeCase(unittest.TestCase):
    """Fixture repo and helpers shared by every case."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        # realpath'd so fixture paths compare equal to the hook's realpath'd roots
        self.base = Path(os.path.realpath(tmp.name))
        self.repo = self.base / "repo"
        (self.repo / "dev" / "local" / "autopilot").mkdir(parents=True)
        self.tmpdir = self.base / "tmproot"
        self.tmpdir.mkdir()
        # Contract order: repo root, its dev/local, TMPDIR. Every case that
        # neither widens nor narrows the scope must see exactly this list.
        self.default_roots = [self.repo, self.repo / "dev" / "local", self.tmpdir]

    def env(self, **overrides: str | None) -> dict[str, str]:
        """Env for one run(); pass Name=None to drop a default key."""
        env: dict[str, str | None] = {
            "HOME": str(Path.home()),
            "TMPDIR": str(self.tmpdir),
            MARKER_ENV: "1",
        }
        env.update(overrides)
        return {k: v for k, v in env.items() if v is not None}

    def call(
        self,
        payload: dict,
        env: dict[str, str],
        tmp_roots: tuple[str, ...] = (),
    ) -> tuple[int, str, str]:
        with patch.dict(os.environ, env, clear=True):
            with patch.object(mod, "TMP_ROOTS", tmp_roots):
                return mod.run(payload)

    def allowed_roots(self, cwd: Path | str, env: dict[str, str]) -> list[Path]:
        """The scope the fence builds for `cwd`, under the same seams as call()."""
        with patch.dict(os.environ, env, clear=True):
            with patch.object(mod, "TMP_ROOTS", ()):
                return mod._allowed_roots(str(cwd), env)

    def reason_for(self, resolved: str, roots: list[Path]) -> str:
        """The contract's one-line block reason, byte for byte."""
        return (
            f"BLOCKED: autopilot write-scope fence: {resolved!r} is outside the "
            f"allowed scope ({', '.join(repr(str(r)) for r in roots)}). "
            "Write inside the session's repo, its dev/local, or a temp dir; "
            "add a root via _AUTOPILOT_WRITE_SCOPE_EXTRA, or set "
            "_AUTOPILOT_WRITE_SCOPE=off to disarm."
        )

    def write_payload(self, target: str, cwd: Path | str) -> dict:
        return {
            "tool_name": "Write",
            "tool_input": {"file_path": target},
            "cwd": str(cwd),
        }

    def assertAllowed(self, result: tuple[int, str, str], note: str = "") -> None:
        code, out, err = result
        self.assertEqual(
            err,
            "",
            f"an allowed call must stay silent; stderr was {err!r} {note}",
        )
        # The dispatcher merges handler stdout envelopes: the fence writes none.
        self.assertEqual(out, "", f"nothing may reach stdout; got {out!r} {note}")
        self.assertEqual(code, 0, f"expected exit 0, got {code} {note}")

    def assertDenied(
        self, result: tuple[int, str, str], resolved: str | None = None
    ) -> str:
        code, out, err = result
        self.assertEqual(code, 2, f"expected a block, got exit {code}; stderr {err!r}")
        self.assertIn("BLOCKED: autopilot write-scope fence:", err)
        self.assertEqual(err.count("\n"), 1, f"reason must be one line: {err!r}")
        # A stdout allow-envelope alongside exit 2 would be merged by the
        # dispatcher and undo the block; the fence writes nothing to stdout.
        self.assertEqual(out, "", f"a block must not write stdout; got {out!r}")
        if resolved is not None:
            self.assertIn(repr(resolved), err)
        return err


class TestIncidentRegressions(WriteScopeCase):
    def test_denies_incident_vault_path_under_marker(self) -> None:
        resolved = os.path.realpath(VAULT_PATH)
        code, _out, err = self.call(
            self.write_payload(VAULT_PATH, self.repo), self.env()
        )
        self.assertEqual(code, 2)
        self.assertEqual(
            err.rstrip("\n"), self.reason_for(resolved, self.default_roots)
        )

    def test_allows_the_in_repo_file_the_subagent_should_have_edited(self) -> None:
        # Real ~/.claude repo, temp roots neutralized: only roots 1 and 2 can allow.
        self.assertAllowed(
            self.call(
                self.write_payload(IN_REPO_PATH, Path.home() / ".claude"),
                self.env(TMPDIR=None),
            )
        )

    def test_allows_out_of_scope_target_when_marker_absent(self) -> None:
        self.assertAllowed(
            self.call(
                self.write_payload(VAULT_PATH, self.repo),
                self.env(**{MARKER_ENV: None}),
            )
        )

    def test_denies_vault_path_as_a_real_subprocess_with_inherited_env(self) -> None:
        # Everything else runs under patched globals and a replaced os.environ.
        # This one is a plain interpreter with the machine's own environment, so
        # an implementation that keys off the fixture (a PATH sniff, a patched
        # attribute) rather than the target path is caught here.
        proc = subprocess.run(
            [sys.executable, str(HOOKS_DIR / "enforce_write_scope.py")],
            input=json.dumps(self.write_payload(VAULT_PATH, self.repo)),
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, MARKER_ENV: "1", "TMPDIR": str(self.tmpdir)},
        )
        self.assertEqual(proc.returncode, 2, f"stderr was {proc.stderr!r}")
        self.assertIn("BLOCKED: autopilot write-scope fence:", proc.stderr)
        self.assertEqual(proc.stdout, "", "the fence writes nothing to stdout")

    def test_denies_symlink_inside_cwd_that_points_out_of_scope(self) -> None:
        outside = self.base / "outside"
        outside.mkdir()
        os.symlink(outside, self.repo / "escape")
        target = str(self.repo / "escape" / "smoke.test.js")
        self.assertDenied(
            self.call(self.write_payload(target, self.repo), self.env()),
            str(outside / "smoke.test.js"),
        )


class TestArmingAndNormalization(WriteScopeCase):
    def test_stays_off_when_only_a_live_autopilot_loop_pid_is_set(self) -> None:
        env = self.env(**{MARKER_ENV: None, "_AUTOPILOT_LOOP": str(os.getpid())})
        self.assertAllowed(self.call(self.write_payload(VAULT_PATH, self.repo), env))

    def test_stays_off_unless_marker_is_exactly_one(self) -> None:
        for value in ("0", "true"):
            with self.subTest(marker=value):
                self.assertAllowed(
                    self.call(
                        self.write_payload(VAULT_PATH, self.repo),
                        self.env(**{MARKER_ENV: value}),
                    ),
                    f"(marker={value!r})",
                )

    def test_kill_switch_off_allows_and_reports_the_disarm_on_stderr(self) -> None:
        code, _out, err = self.call(
            self.write_payload(VAULT_PATH, self.repo),
            self.env(**{KILL_SWITCH_ENV: "off"}),
        )
        self.assertEqual(code, 0)
        self.assertIn(
            "enforce_write_scope: disarmed by _AUTOPILOT_WRITE_SCOPE=off", err
        )
        self.assertNotIn("BLOCKED", err)

    def test_stays_armed_unless_the_kill_switch_is_exactly_off(self) -> None:
        for value in ("on", "1", ""):
            with self.subTest(kill_switch=value):
                self.assertDenied(
                    self.call(
                        self.write_payload(VAULT_PATH, self.repo),
                        self.env(**{KILL_SWITCH_ENV: value}),
                    )
                )

    def test_denies_out_of_scope_write_from_a_repo_without_dev_local(self) -> None:
        # No dev/local anywhere above this cwd - the shape of most repos on
        # disk. A fence that arms only where it finds one is off almost
        # everywhere, and every other denial case here would still pass.
        plain = self.base / "plain"
        plain.mkdir()
        self.assertDenied(
            self.call(self.write_payload(VAULT_PATH, plain), self.env()),
            os.path.realpath(VAULT_PATH),
        )

    def test_denies_tilde_target_that_expands_out_of_scope(self) -> None:
        # Without expanduser this anchors at cwd, lands inside root 1, and passes.
        self.assertDenied(
            self.call(self.write_payload("~/bim/x.js", self.repo), self.env()),
            str(Path.home() / "bim" / "x.js"),
        )

    def test_anchors_relative_targets_at_the_payload_cwd(self) -> None:
        escaping = self.base.parent / "bim" / "x.js"
        self.assertDenied(
            self.call(self.write_payload("../../bim/x.js", self.repo), self.env()),
            str(escaping),
        )
        # Anchored at the hook subprocess's cwd instead, this one leaves the repo.
        self.assertAllowed(
            self.call(
                self.write_payload("dev/local/tmp/attempt-task-1.json", self.repo),
                self.env(),
            )
        )

    def test_allows_repo_write_when_session_cwd_is_a_subdirectory(self) -> None:
        sub = self.repo / "sub"
        sub.mkdir()
        env = self.env()
        target = str(self.repo / "dev" / "local" / "autopilot" / "state.json")
        self.assertAllowed(self.call(self.write_payload(target, sub), env))
        # The walk-up widens the scope to the repo, not to the whole disk: the
        # same basename outside the repo, from the same cwd, still breaches.
        sibling = str(self.base / "sibling" / "state.json")
        code, _out, err = self.call(self.write_payload(sibling, sub), env)
        self.assertEqual(code, 2, f"sibling of the repo must be denied; got {err!r}")
        self.assertEqual(
            err.rstrip("\n"),
            self.reason_for(os.path.realpath(sibling), self.default_roots),
        )
        # Containment is component-wise, not a string prefix: a neighbour whose
        # name merely EXTENDS a root's name is outside it. One per root spelling
        # that a prefix test would hand over - the repo and TMPDIR.
        adjacent = str(self.base / (self.repo.name + "-evil") / "x.js")
        self.assertDenied(self.call(self.write_payload(adjacent, sub), env), adjacent)
        stolen = str(self.tmpdir.parent / (self.tmpdir.name + "-stolen") / "x.js")
        self.assertDenied(self.call(self.write_payload(stolen, sub), env), stolen)
        self.assertEqual(self.allowed_roots(sub, env), self.default_roots)

    def test_walks_up_to_the_autopilot_repo_past_a_decoy_dev_local(self) -> None:
        sub = self.repo / "sub"
        (sub / "dev" / "local").mkdir(parents=True)  # decoy: no autopilot/ inside
        env = self.env()
        target = str(self.repo / "dev" / "local" / "tmp" / "dispatch-ivan-1.txt")
        self.assertAllowed(self.call(self.write_payload(target, sub), env))
        # Stopping at the decoy would shrink the scope to `sub`. The same
        # dispatch filename outside the repo must still be denied, against the
        # outer repo's roots: location decides, never the basename.
        sibling = str(self.base / "sibling" / "dispatch-ivan-1.txt")
        code, _out, err = self.call(self.write_payload(sibling, sub), env)
        self.assertEqual(code, 2, f"sibling of the repo must be denied; got {err!r}")
        self.assertEqual(
            err.rstrip("\n"),
            self.reason_for(os.path.realpath(sibling), self.default_roots),
        )
        self.assertEqual(self.allowed_roots(sub, env), self.default_roots)

    def test_drops_a_dev_local_root_that_resolves_to_home(self) -> None:
        home = self.base / "home"
        home.mkdir()
        symrepo = self.base / "symrepo"
        (symrepo / "dev").mkdir(parents=True)
        os.symlink(home, symrepo / "dev" / "local")
        err = self.assertDenied(
            self.call(
                self.write_payload("~/bim/x.js", symrepo),
                self.env(HOME=str(home)),
            ),
            str(home / "bim" / "x.js"),
        )
        self.assertNotIn(repr(str(home)), err)

    def test_denies_every_write_when_the_floor_empties_the_root_list(self) -> None:
        home = self.base / "home"
        (home / "dev").mkdir(parents=True)
        os.symlink(home, home / "dev" / "local")
        code, _out, err = self.call(
            self.write_payload(str(home / "notes" / "x.md"), home),
            self.env(HOME=str(home), TMPDIR=None),
        )
        self.assertEqual(code, 2, f"must fail closed; stderr {err!r}")
        self.assertIn(
            "enforce_write_scope: no usable write scope (every candidate root was "
            "$HOME or above); refusing all writes",
            err,
        )

    def test_repo_root_walk_up_stops_below_home(self) -> None:
        home = self.base / "home"
        (home / "dev" / "local" / "autopilot").mkdir(parents=True)
        nested = home / "proj"  # no dev/local/autopilot of its own
        nested.mkdir()
        self.assertAllowed(
            self.call(
                self.write_payload(str(nested / "src" / "foo.py"), nested),
                self.env(HOME=str(home)),
            )
        )

    def test_cwd_itself_is_not_an_allowed_root(self) -> None:
        # cwd is $HOME here, so the floor drops it from the root list. TMPDIR
        # stays set, so the list is non-empty and the fail-closed branch does
        # not fire: the only way this passes is if cwd itself never grants
        # scope. Every other case has cwd sitting inside root 1, which hides it.
        home = self.base / "home"
        home.mkdir()
        target = str(home / "notes" / "x.md")
        self.assertDenied(
            self.call(
                self.write_payload(target, home),
                self.env(HOME=str(home)),
            ),
            target,
        )

    def test_extra_roots_variable_widens_the_scope(self) -> None:
        first = self.base / "extra-one"
        second = self.base / "extra-two"
        first.mkdir()
        second.mkdir()
        joined = f"{first}:{second}"  # the contract pins ':'-joined splitting
        for extra in (first, second):
            target = str(extra / "out.txt")
            with self.subTest(extra=str(extra)):
                self.assertAllowed(
                    self.call(
                        self.write_payload(target, self.repo),
                        self.env(**{EXTRA_ROOTS_ENV: joined}),
                    )
                )
                self.assertDenied(
                    self.call(self.write_payload(target, self.repo), self.env()),
                    target,
                )

    def test_extra_roots_variable_cannot_readmit_home(self) -> None:
        home = self.base / "home"
        home.mkdir()
        # The floor drops $HOME itself AND every strict ancestor of it. Naming
        # only $HOME leaves the knob able to readmit the whole disk with
        # _AUTOPILOT_WRITE_SCOPE_EXTRA=/ , which is the same vacuous scope.
        for extra in (home, self.base):
            with self.subTest(extra=str(extra)):
                self.assertDenied(
                    self.call(
                        self.write_payload("~/bim/x.js", self.repo),
                        self.env(HOME=str(home), **{EXTRA_ROOTS_ENV: str(extra)}),
                    ),
                    str(home / "bim" / "x.js"),
                )

    def test_denies_tmp_target_when_the_temp_root_seam_is_empty(self) -> None:
        # Fails the moment patch.object(mod, "TMP_ROOTS", ()) stops taking effect.
        self.assertDenied(
            self.call(
                self.write_payload("/tmp/review-prompt.txt", self.repo),
                self.env(TMPDIR=None),
            ),
            os.path.realpath("/tmp/review-prompt.txt"),
        )


class TestLegitimateWrites(WriteScopeCase):
    def test_allows_dispatch_file_through_a_symlinked_dev_local(self) -> None:
        symrepo = self.base / "symrepo"
        external = self.base / "claude-dev"
        (external / "autopilot").mkdir(parents=True)
        (symrepo / "dev").mkdir(parents=True)
        os.symlink(external, symrepo / "dev" / "local")
        target = str(symrepo / "dev" / "local" / "tmp" / "dispatch-ivan-1.txt")
        self.assertAllowed(self.call(self.write_payload(target, symrepo), self.env()))

    def test_allows_the_work_skill_dev_local_write_locations(self) -> None:
        dev_local = self.repo / "dev" / "local"
        targets = [
            dev_local / "autopilot" / "state.json",
            dev_local / "autopilot" / "contract-card.md",
            dev_local / "assumptions.md",
            dev_local / "prds" / "wip" / "00136-block-out-of-scope-writes.md",
            dev_local / "reviews" / "00136-review-1.md",
        ]
        for target in targets:
            with self.subTest(target=str(target)):
                self.assertAllowed(
                    self.call(self.write_payload(str(target), self.repo), self.env())
                )

    def test_allows_write_under_tmpdir(self) -> None:
        # Temp roots empty: only root 3 (TMPDIR) can allow this one.
        self.assertAllowed(
            self.call(
                self.write_payload(str(self.tmpdir / "review-prompt.txt"), self.repo),
                self.env(),
            )
        )

    def test_allows_write_under_the_static_temp_roots(self) -> None:
        # No TMPDIR: only root 4 (TMP_ROOTS) can allow these.
        scratchpad = (
            "/private/tmp/claude-501/-Users-bob--claude/"
            "9dccb85f-699b-45fc-881a-8f90e2d7a123/scratchpad/notes.md"
        )
        for target in ("/tmp/review-prompt.txt", scratchpad):
            with self.subTest(target=target):
                self.assertAllowed(
                    self.call(
                        self.write_payload(target, self.repo),
                        self.env(TMPDIR=None),
                        tmp_roots=("/tmp",),
                    )
                )

    def test_allows_an_ordinary_in_repo_source_file(self) -> None:
        self.assertAllowed(
            self.call(
                self.write_payload(str(self.repo / "src" / "foo.py"), self.repo),
                self.env(),
            )
        )


class TestPayloadShapes(WriteScopeCase):
    def test_denies_out_of_scope_edit_and_unknown_tool_names(self) -> None:
        # Targets come out of tool_input whatever the tool is called - the
        # dispatch matcher owns tool filtering. "Edit" is the tool the incident
        # actually used, and no other denial case here names it.
        for tool_name in ("Edit", "SomeFutureWriteTool"):
            with self.subTest(tool_name=tool_name):
                payload = {
                    "tool_name": tool_name,
                    "tool_input": {"file_path": VAULT_PATH},
                    "cwd": str(self.repo),
                }
                self.assertDenied(
                    self.call(payload, self.env()), os.path.realpath(VAULT_PATH)
                )

    def test_denies_out_of_scope_target_when_payload_has_no_cwd(self) -> None:
        # cwd falls back to os.getcwd(); an absolute out-of-scope target must
        # be denied under any fallback, so a missing key cannot disarm the
        # fence. Every other payload here carries "cwd".
        payload = {"tool_name": "Write", "tool_input": {"file_path": VAULT_PATH}}
        self.assertDenied(self.call(payload, self.env()), os.path.realpath(VAULT_PATH))

    def test_denies_out_of_scope_notebook_path(self) -> None:
        payload = {
            "tool_name": "NotebookEdit",
            "tool_input": {"notebook_path": "/Users/bob/bim/inbox/notes.ipynb"},
            "cwd": str(self.repo),
        }
        self.assertDenied(
            self.call(payload, self.env()),
            os.path.realpath("/Users/bob/bim/inbox/notes.ipynb"),
        )

    def test_denies_out_of_scope_file_path_inside_multiedit_edits(self) -> None:
        in_repo = str(self.repo / "src" / "foo.py")
        # Every target is checked, not just one position in the list: the
        # escaping path is last in the first shape and first in the second, so
        # a fence looking only at targets[-1] or targets[0] fails one of them.
        tool_inputs = [
            {
                "file_path": in_repo,
                "edits": [
                    {"old_string": "a", "new_string": "b"},
                    {
                        "file_path": OUT_OF_SCOPE,
                        "old_string": "c",
                        "new_string": "d",
                    },
                ],
            },
            {
                "file_path": OUT_OF_SCOPE,
                "edits": [
                    {"file_path": in_repo, "old_string": "a", "new_string": "b"},
                    {"file_path": in_repo, "old_string": "c", "new_string": "d"},
                ],
            },
        ]
        for tool_input in tool_inputs:
            with self.subTest(file_path=tool_input["file_path"]):
                payload = {
                    "tool_name": "MultiEdit",
                    "tool_input": tool_input,
                    "cwd": str(self.repo),
                }
                self.assertDenied(
                    self.call(payload, self.env()), os.path.realpath(OUT_OF_SCOPE)
                )

    def test_allows_payloads_that_carry_no_usable_target(self) -> None:
        payloads = [
            {"tool_name": "Write", "cwd": str(self.repo)},
            {"tool_name": "Write", "tool_input": {}, "cwd": str(self.repo)},
            {
                "tool_name": "Write",
                "tool_input": {"content": "hello"},
                "cwd": str(self.repo),
            },
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                self.assertAllowed(self.call(payload, self.env()))

    def test_reports_a_degraded_hook_and_allows_when_it_crashes(self) -> None:
        def _boom(*_args: object, **_kwargs: object) -> list:
            raise RuntimeError("kaboom")

        with patch.object(mod, "_allowed_roots", _boom):
            code, _out, err = self.call(
                self.write_payload(VAULT_PATH, self.repo), self.env()
            )
        self.assertEqual(code, 0, "a crashing fence must not block the tool call")
        self.assertIn("policy hook degraded: enforce_write_scope", err)
        self.assertIn("kaboom", err)
        self.assertNotIn("Traceback", err)


class TestContractSeams(WriteScopeCase):
    """The helpers the contract names, driven directly rather than through run()."""

    def test_main_blocks_the_incident_path_when_driven_standalone(self) -> None:
        # run() delegates to capture_main(main, payload), so main() alone must
        # produce the same denial; a stubbed main with the logic in run() fails.
        with patch.dict(os.environ, self.env(), clear=True):
            with patch.object(mod, "TMP_ROOTS", ()):
                code, _out, err = _common.capture_main(
                    mod.main, self.write_payload(VAULT_PATH, self.repo)
                )
        self.assertEqual(code, 2, f"main() must block on its own; stderr {err!r}")
        self.assertEqual(
            err.rstrip("\n"),
            self.reason_for(os.path.realpath(VAULT_PATH), self.default_roots),
        )

    def test_repo_root_walks_up_to_the_autopilot_directory(self) -> None:
        deeper = self.repo / "sub" / "deeper"
        deeper.mkdir(parents=True)
        with patch.dict(os.environ, self.env(), clear=True):
            self.assertEqual(mod._repo_root(deeper), self.repo)

    def test_repo_root_returns_cwd_when_the_walk_up_stops_at_home(self) -> None:
        home = self.base / "home"
        (home / "dev" / "local" / "autopilot").mkdir(parents=True)
        proj = home / "proj"  # nothing below $HOME qualifies
        proj.mkdir()
        with patch.dict(os.environ, self.env(HOME=str(home)), clear=True):
            self.assertEqual(mod._repo_root(proj), proj)

    def test_resolve_expands_a_tilde_before_realpathing(self) -> None:
        with patch.dict(os.environ, self.env(), clear=True):
            self.assertEqual(
                mod._resolve("~/bim/x.js", str(self.repo)),
                os.path.realpath(os.path.expanduser("~/bim/x.js")),
            )

    def test_resolve_anchors_a_relative_target_at_the_given_cwd(self) -> None:
        with patch.dict(os.environ, self.env(), clear=True):
            self.assertEqual(
                mod._resolve("rel/x.js", str(self.repo)),
                os.path.realpath(str(self.repo / "rel" / "x.js")),
            )

    def test_breach_is_decided_by_containment_not_by_the_path_text(self) -> None:
        # The same relative subpath inside and outside the root: no table of
        # path fragments can separate these two, only containment can.
        roots = [self.repo]
        with patch.dict(os.environ, self.env(), clear=True):
            self.assertIsNone(
                mod._breach(str(self.repo / "zzz" / "f.txt"), roots, str(self.repo))
            )
            self.assertIsNotNone(
                mod._breach(str(self.base / "zzz" / "f.txt"), roots, str(self.repo))
            )


if __name__ == "__main__":
    unittest.main()
