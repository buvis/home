"""Parity tests for the in-process `run(payload)` entry point on 12 hook handlers.

CONTRACT under test (PRD 00071, feature "run() interface"): each handler exposes
`run(payload: dict) -> tuple[int, str, str]`. For a given JSON payload, calling
that entry point DIRECTLY - no outer capture_main, the handler owns its own
capture -

    code, out, err = mod.run(payload)

MUST produce the SAME exit_code and the SAME stdout as running that handler as a
standalone subprocess:

    subprocess.run([sys.executable, handler], input=json.dumps(payload), ...)

Exit code and stdout are the HARD contract. stderr is asserted ONLY for the
`enforce_prd_location` block, whose message is fully deterministic static text.

Isolation (the central hazard). Several handlers write state as a side effect
(per-session throttle stores, append-only logs, cartographer stores). If both
legs shared one environment, the first leg's writes could change the second
leg's output (e.g. a once-per-session injection becomes throttled) and forge a
false mismatch. So each leg gets its OWN fresh, identically-clean temp HOME and
cwd: subprocess via `env=`/`cwd=`; in-process via monkeypatching `Path.home` +
`HOME` and `monkeypatch.chdir`. No handler emits its HOME/cwd (or any timestamp,
uuid, pid) to STDOUT, so the two legs' different temp paths never break stdout
parity. The one exception is the read-only `validate_state_json_hook`
discriminator, which shares a single temp dir because its payload names an
absolute file path that must resolve identically for both legs (it performs no
writes, so there is nothing to cross-contaminate).

Because strunk/echo bind `Path.home()`-derived paths at import time, each handler
module is loaded fresh AFTER home is patched, so its module-level constants
resolve under the temp HOME.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from .dispatch_test_helpers import require_in_process_work

# Derived from THIS file, never hardcoded: an absolute `/Users/bob/.claude/hooks`
# would make the suite load and subprocess whatever is INSTALLED there, so in a
# git worktree it would pass no matter how broken the checkout under test is.
HOOKS_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = HOOKS_DIR.parent / "skills" / "run-autopilot" / "scripts"

# Both dirs on sys.path so the test's `import _common` AND the handlers' own
# sibling imports (`_common`, `_lib_cartographer`, `_walk_up`) resolve during an
# in-process exec — including for handlers that self-insert only the WRONG dir
# under a patched HOME (cartographer-stop) or insert nothing (the two _walk_up
# importers in scripts/).
for _d in (HOOKS_DIR, SCRIPTS_DIR):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

# Env markers that flip autopilot/nested handlers OFF their benign early-return
# path. Stripped in BOTH legs so the two runs observe identical, quiescent state
# regardless of what the pytest process inherited.
_STRIP_ENV = ("_AUTOPILOT_LOOP", "CLAUDE_NESTED", "CLAUDE_SESSION_NAME")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _purge_sibling_modules() -> None:
    """Drop cached sibling libraries (`_common`, `_walk_up`, `_lib_cartographer`)
    so the next handler load re-executes their bodies under the CURRENT temp HOME.

    Some of them create their store directory at IMPORT time from `Path.home()`.
    Left cached from an EARLIER test's temp HOME, that mkdir never re-runs, and a
    later handler's append then fails with ENOENT under the current HOME
    (measured: cartographer-stop's audit.jsonl, once cartographer-echo has
    imported the shared library first). That is a cross-test artifact, not a
    handler defect, and it would forge a file-tree mismatch below.

    Scoped to underscore-prefixed modules living DIRECTLY in the two handler
    dirs - the documented sibling set plus this file's own `_hook_*` loads - so
    `dispatch` (imported at the real HOME by the sibling test module) is left
    alone.
    """
    roots = {str(HOOKS_DIR), str(SCRIPTS_DIR)}
    for name, mod in list(sys.modules.items()):
        file = getattr(mod, "__file__", None)
        if name.startswith("_") and file and str(Path(file).parent) in roots:
            del sys.modules[name]


def _load_handler(path: str):
    """Import a handler by absolute path under a UNIQUE module name.

    A fresh name per load guarantees the module body re-executes, so its
    module-level `Path.home()` constants (strunk/echo) bind to whatever HOME is
    patched at load time. Sibling imports resolve via sys.path, independent of
    this name.
    """
    _purge_sibling_modules()
    stem = Path(path).stem
    name = f"_hook_{stem}_{uuid4().hex[:8]}"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _fresh_env(base: Path, tag: str) -> tuple[Path, Path]:
    """A clean, empty temp HOME + cwd under `base/tag`."""
    home = base / tag / "home"
    cwd = base / tag / "cwd"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    cwd.mkdir(parents=True, exist_ok=True)
    return home, cwd


def _nonempty(path: Path) -> bool:
    """True iff `path` is a regular file with content (a no-op leaves it absent)."""
    return path.is_file() and path.stat().st_size > 0


def _glob_nonempty(root: Path, pattern: str) -> bool:
    """True iff any file matching `root/pattern` exists and is non-empty."""
    return any(_nonempty(p) for p in root.glob(pattern))


def _tree(home: Path) -> list[str]:
    """The relative, sorted shape of everything a leg wrote under its HOME."""
    return sorted(str(p.relative_to(home)) for p in home.rglob("*"))


def _last_json_row(path: Path) -> dict:
    """Parse the last non-empty JSONL line of `path` (the row just appended)."""
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines, f"{path} has no rows"
    return json.loads(lines[-1])


def _one_nonempty_glob(root: Path, pattern: str) -> Path:
    """Return the single non-empty file matching `root/pattern`."""
    matches = [p for p in root.glob(pattern) if _nonempty(p)]
    assert matches, f"no non-empty file at {root}/{pattern}"
    return matches[0]


def _run_subprocess(path: str, payload: dict, home: Path, cwd: Path, env_extra=None):
    env = dict(os.environ)
    env["HOME"] = str(home)
    for k in _STRIP_ENV:
        env.pop(k, None)
    if env_extra:
        env.update(env_extra)  # applied AFTER the strip so a case may re-set one
    proc = subprocess.run(
        [sys.executable, path],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd),
        timeout=30,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _run_in_process(path: str, payload: dict, home: Path, cwd: Path, monkeypatch, env_extra=None):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.setenv("HOME", str(home))
    for k in _STRIP_ENV:
        monkeypatch.delenv(k, raising=False)
    if env_extra:
        for k, v in env_extra.items():
            monkeypatch.setenv(k, v)  # mirror the subprocess env for parity
    monkeypatch.chdir(cwd)
    mod = _load_handler(path)  # loaded AFTER HOME is patched
    # Requirement (a): a real, callable module-level run(payload) must exist.
    # Asserted BEFORE the call so a missing run fails loudly here instead of
    # being swallowed into a false (0, "") that would spuriously match a benign
    # subprocess run.
    assert hasattr(mod, "run") and callable(mod.run), (
        f"{Path(path).name}: module-level run(payload) is missing or not callable"
    )
    name = Path(path).name
    # Requirement (b): run(payload) is called DIRECTLY. The handler owns its own
    # capture and RETURNS (exit_code, stdout, stderr); wrapping it in an outer
    # capture_main here would map that triple to a bogus (0, "", "") and make
    # every leg of this parity suite agree on nothing.
    # Requirement (c): it does that work IN-PROCESS. See require_in_process_work:
    # a run() that re-execs its own script passes every parity assertion in this
    # file by construction, so the witness - not the comparison - is what catches it.
    try:
        with require_in_process_work(mod, name) as fired:
            result = mod.run(payload)
    except SystemExit as exc:
        pytest.fail(
            f"{name}: run(payload) exited (SystemExit {exc.code!r}) instead of "
            f"returning (exit_code, stdout, stderr)"
        )
    except Exception as exc:
        # e.g. a handler that still reads the real sys.stdin: run() must feed
        # `payload` itself, not lean on a caller to swap the stream.
        pytest.fail(
            f"{name}: run(payload) raised {type(exc).__name__}: {exc}; it must "
            f"return (exit_code, stdout, stderr)"
        )
    assert fired, (
        f"{name}: run(payload) returned without ever entering the module's own "
        f"work function IN THIS PROCESS. A re-exec (any shape: [sys.executable, "
        f"__file__], a renamed interpreter, a /bin/sh shim, os.posix_spawn) runs "
        f"the work in a CHILD, which cannot touch this module object; a no-op "
        f"`return (0, \"\", \"\")` never enters it at all. Both reproduce a benign "
        f"parity result while doing none of the handler's work in-process."
    )
    assert isinstance(result, tuple) and len(result) == 3, (
        f"{name}: run(payload) must return a 3-tuple (exit_code, stdout, stderr), "
        f"got {type(result).__name__} ({result!r})"
    )
    code, out, err = result
    assert isinstance(code, int) and not isinstance(code, bool), (
        f"{name}: exit code must be an int, got {type(code).__name__} ({code!r})"
    )
    assert isinstance(out, str) and isinstance(err, str), (
        f"{name}: stdout/stderr must be str, got "
        f"{type(out).__name__}/{type(err).__name__}"
    )
    return code, out, err


# --------------------------------------------------------------------------- #
# The 12 handlers, each with a payload that runs deterministically in a clean
# temp env. enforce_prd_location carries the Bash-lifecycle BLOCK payload, so
# its parity case is itself a discriminator (subprocess exits 2 -> a `(0, "")`
# stub run() fails parity). The rest ride benign, empty-stdout, exit-0 paths.
#
# This parametrized suite is the EXISTENCE + parity floor. Seven handlers ALSO
# get a dedicated STRONG discriminator below (a distinguishing exit / stdout /
# side-effect a no-op or unconditional stub cannot fake):
#   enforce_prd_location (block AND allow), validate_state_json_hook (reject AND
#   accept), track_cost / track_skills / observe_tool (pinned side-effect file),
#   review_coverage_hook (exit 2), autopilot_context_cap_hook (rotation stdout).
# The remaining FIVE are EXISTENCE-ONLY here (benign parity + run-exists): they
# need external state this parity test must not fabricate hermetically -
#   cartographer-echo / cartographer-stop  (tree-sitter/atlas + real repo corpus)
#   strunk-ruling-inject                   (installed strunk plugin cache)
#   notify                                 (real desktop/network presence probes)
#   analyze-instincts                      (a prior observation corpus)
# Their functional behavior is covered by each handler's OWN test suite; here
# they only prove run() exists and does not diverge from the subprocess. See
# ASSUMPTIONS.
# --------------------------------------------------------------------------- #
_HANDLERS = [
    pytest.param(
        str(HOOKS_DIR / "enforce_prd_location.py"),
        {"tool_name": "Bash", "tool_input": {"command": "ls backlog/"}},
        id="enforce_prd_location",
    ),
    pytest.param(
        str(HOOKS_DIR / "cartographer-echo.py"),
        {"tool_name": "Read", "tool_input": {"file_path": "/tmp/x.py"}, "session_id": "s"},
        id="cartographer-echo",
    ),
    pytest.param(
        str(HOOKS_DIR / "strunk-ruling-inject.py"),
        {"tool_name": "Read", "tool_input": {"file_path": "/tmp/notes.txt"}, "session_id": "s"},
        id="strunk-ruling-inject",
    ),
    pytest.param(
        str(HOOKS_DIR / "observe_tool.py"),
        {
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/x"},
            "tool_response": "ok",
            "session_id": "s",
            "cwd": "/tmp",
        },
        id="observe_tool",
    ),
    pytest.param(
        str(HOOKS_DIR / "notify.py"),
        {
            "hook_event_name": "Stop",
            "background_tasks": [{"status": "running"}],
            "cwd": "/tmp",
            "session_id": "s",
        },
        id="notify",
    ),
    pytest.param(
        str(HOOKS_DIR / "track_cost.py"),
        {"session_id": "s"},
        id="track_cost",
    ),
    pytest.param(
        str(HOOKS_DIR / "track_skills.py"),
        {"session_id": "s"},
        id="track_skills",
    ),
    pytest.param(
        str(HOOKS_DIR / "analyze-instincts.py"),
        {"session_id": "s"},
        id="analyze-instincts",
    ),
    pytest.param(
        str(HOOKS_DIR / "cartographer-stop.py"),
        {"session_id": "s"},
        id="cartographer-stop",
    ),
    pytest.param(
        str(SCRIPTS_DIR / "autopilot_context_cap_hook.py"),
        {"session_id": "s", "transcript_path": "/tmp/does-not-exist.jsonl"},
        id="autopilot_context_cap_hook",
    ),
    pytest.param(
        str(SCRIPTS_DIR / "validate_state_json_hook.py"),
        {"tool_input": {"file_path": "/tmp/not-a-state-file.txt"}},
        id="validate_state_json_hook",
    ),
    pytest.param(
        str(SCRIPTS_DIR / "review_coverage_hook.py"),
        {"session_id": "s"},
        id="review_coverage_hook",
    ),
]


@pytest.mark.integration
@pytest.mark.parametrize("path,payload", _HANDLERS)
def test_run_parity_matches_subprocess(path, payload, tmp_path, monkeypatch):
    """In-process run(payload) must match the subprocess run in (exit_code, stdout).

    Each leg runs in its OWN clean temp HOME + cwd so neither leg's side-effect
    writes can perturb the other. For benign handlers both legs agree at
    (0, "") - a valid but weak parity check; for enforce_prd_location both legs
    agree at (2, "") - a case a trivial `(0, "")` stub cannot fake.

    The FILE-TREE assertion carries the rest of the weight, with no per-handler
    fixture: whatever the subprocess wrote under its HOME, the in-process leg
    must have written too. A no-op `run()` leaves an empty tree, so notify
    (notify.log), cartographer-stop and analyze-instincts (their stores) and
    observe_tool (its observation row) all fail on it. Verified deterministic:
    running each handler twice under different HOMEs and cwds yields identical
    trees for all twelve, so nothing here needs normalizing.
    """
    sub_home, sub_cwd = _fresh_env(tmp_path, "sub")
    code_sub, out_sub, _ = _run_subprocess(path, payload, sub_home, sub_cwd)

    in_home, in_cwd = _fresh_env(tmp_path, "inproc")
    code_in, out_in, _ = _run_in_process(path, payload, in_home, in_cwd, monkeypatch)

    assert (code_in, out_in) == (code_sub, out_sub), (
        f"{Path(path).name}: in-process {(code_in, out_in)!r} != "
        f"subprocess {(code_sub, out_sub)!r}"
    )
    assert _tree(in_home) == _tree(sub_home), (
        f"{Path(path).name}: the two legs wrote different file trees under HOME - "
        f"in-process {_tree(in_home)!r} != subprocess {_tree(sub_home)!r}. run() "
        f"must perform the handler's side effects, not just return its exit code."
    )


# --------------------------------------------------------------------------- #
# Devon-proof discriminator 1: enforce_prd_location BLOCKS a repo-root
# lifecycle-dir Bash command. Payload-only (no fs/git/config), so the effect is
# deterministic in any clean temp env. Asserts the concrete effect (exit 2,
# empty stdout, BLOCKED message on stderr in BOTH legs) on top of parity.
# --------------------------------------------------------------------------- #
@pytest.mark.integration
@pytest.mark.parametrize(
    "command",
    ["ls backlog/", "cat done/report.md", "mv wip/a wip/b"],
    ids=["backlog", "done", "wip"],
)
def test_enforce_prd_location_bash_block_exit_2(command, tmp_path, monkeypatch):
    path = str(HOOKS_DIR / "enforce_prd_location.py")
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}

    sub_home, sub_cwd = _fresh_env(tmp_path, "sub")
    code_sub, out_sub, err_sub = _run_subprocess(path, payload, sub_home, sub_cwd)

    in_home, in_cwd = _fresh_env(tmp_path, "inproc")
    code_in, out_in, err_in = _run_in_process(path, payload, in_home, in_cwd, monkeypatch)

    # Parity of the hard contract.
    assert (code_in, out_in) == (code_sub, out_sub)
    # Concrete deterministic effect a `(0, "")` stub cannot satisfy.
    assert code_in == 2, f"{command!r} references a repo-root lifecycle dir; must BLOCK"
    assert out_in == "" and out_sub == ""
    # The block message is fully deterministic static text -> safe to assert on
    # stderr in both legs (no paths/tracebacks in this branch).
    assert "BLOCKED" in err_in
    assert "BLOCKED" in err_sub


# --------------------------------------------------------------------------- #
# Devon-proof discriminator 2: validate_state_json_hook REJECTS an invalid
# state.json with exit 2. The handler is read-only (no writes), so both legs
# share one temp dir - the payload's absolute file path then resolves
# identically for subprocess and in-process.
# --------------------------------------------------------------------------- #
@pytest.mark.integration
def test_validate_state_json_invalid_json_exit_2(tmp_path, monkeypatch):
    path = str(SCRIPTS_DIR / "validate_state_json_hook.py")
    home, cwd = _fresh_env(tmp_path, "shared")
    state = cwd / "dev" / "local" / "autopilot" / "state.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text("this is not valid json {{{")
    payload = {"tool_input": {"file_path": str(state)}}

    code_sub, out_sub, _ = _run_subprocess(path, payload, home, cwd)
    code_in, out_in, _ = _run_in_process(path, payload, home, cwd, monkeypatch)

    assert (code_in, out_in) == (code_sub, out_sub)
    assert code_in == 2, "an invalid state.json write must be rejected (exit 2)"
    assert out_in == "" and out_sub == ""


# --------------------------------------------------------------------------- #
# ALLOW-PATH discriminators. The block/reject cases above pass even for a stub
# that blocks/rejects EVERYTHING; these pin the opposite branch so an
# unconditional-block or suffix-only stub diverges from the real handler.
# --------------------------------------------------------------------------- #
@pytest.mark.integration
@pytest.mark.parametrize(
    "command",
    ["ls /tmp", "ls backlogged/"],
    ids=["plain", "substring-boundary"],
)
def test_enforce_prd_location_allows_benign_command(command, tmp_path, monkeypatch):
    """A Bash command that names no repo-root lifecycle dir must be ALLOWED
    (exit 0). `ls /tmp` kills a `print('BLOCKED'); return 2` block-everything
    stub; `ls backlogged/` kills a sloppy SUBSTRING matcher (it contains
    'backlog' but not the `backlog/` segment the anchored matcher requires)."""
    path = str(HOOKS_DIR / "enforce_prd_location.py")
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}

    sub_home, sub_cwd = _fresh_env(tmp_path, "sub")
    code_sub, out_sub, _ = _run_subprocess(path, payload, sub_home, sub_cwd)

    in_home, in_cwd = _fresh_env(tmp_path, "inproc")
    code_in, out_in, _ = _run_in_process(path, payload, in_home, in_cwd, monkeypatch)

    assert (code_in, out_in) == (code_sub, out_sub)
    assert code_in == 0, f"{command!r} names no lifecycle dir; must be allowed (exit 0)"
    assert out_in == "" and out_sub == ""


@pytest.mark.integration
def test_validate_state_json_valid_json_allowed(tmp_path, monkeypatch):
    """VALID JSON at a state.json path must be ALLOWED (exit 0). Kills a
    suffix-only stub (`return 2 if path.endswith('state.json')`) that never
    parses content - the invalid-JSON case above cannot see it, this does.
    Read-only handler, so both legs share one temp dir (absolute path in the
    payload must resolve identically for subprocess and in-process)."""
    path = str(SCRIPTS_DIR / "validate_state_json_hook.py")
    home, cwd = _fresh_env(tmp_path, "shared")
    state = cwd / "dev" / "local" / "autopilot" / "state.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"phase": "build", "prd": "00099-demo.md"}))
    payload = {"tool_input": {"file_path": str(state)}}

    code_sub, out_sub, _ = _run_subprocess(path, payload, home, cwd)
    code_in, out_in, _ = _run_in_process(path, payload, home, cwd, monkeypatch)

    assert (code_in, out_in) == (code_sub, out_sub)
    assert code_in == 0, "well-formed state.json must be allowed (exit 0)"
    assert out_in == "" and out_sub == ""


# --------------------------------------------------------------------------- #
# SIDE-EFFECT-FILE discriminators for the metrics/observation writers. Their
# benign parity case is (0, "") both legs, which a no-op `run()` fakes. Here a
# crafted payload makes the REAL handler append a row to a pinned file under its
# temp HOME; a no-op writes nothing, so the in-process file stays absent -> the
# non-empty assertion catches it. Each leg keeps its own HOME (isolation); the
# transcript is shared (read-only, so no cross-leg contamination).
# --------------------------------------------------------------------------- #
@pytest.mark.integration
def test_track_cost_writes_costs_row(tmp_path, monkeypatch):
    path = str(HOOKS_DIR / "track_cost.py")
    transcript = tmp_path / "cost-transcript.jsonl"
    transcript.write_text(json.dumps({
        "type": "assistant",
        "message": {
            "id": "m1",
            "model": "claude-sonnet-4",
            "usage": {
                "input_tokens": 1000, "output_tokens": 200,
                "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
            },
        },
    }) + "\n")
    payload = {"session_id": "s", "transcript_path": str(transcript)}

    sub_home, sub_cwd = _fresh_env(tmp_path, "sub")
    code_sub, out_sub, _ = _run_subprocess(path, payload, sub_home, sub_cwd)
    in_home, in_cwd = _fresh_env(tmp_path, "inproc")
    code_in, out_in, _ = _run_in_process(path, payload, in_home, in_cwd, monkeypatch)

    assert (code_in, out_in) == (code_sub, out_sub) == (0, "")
    assert _nonempty(sub_home / ".claude" / "metrics" / "costs.jsonl")
    assert _nonempty(in_home / ".claude" / "metrics" / "costs.jsonl"), (
        "run() must append a cost row under HOME; a no-op leaves it empty"
    )
    # Pin the MEANING: the row must reflect the crafted transcript, not arbitrary
    # bytes (kills a garbage-writing stub). Keys per track_cost.py build_row: the
    # in/out token sums and the model string.
    for home in (sub_home, in_home):
        row = _last_json_row(home / ".claude" / "metrics" / "costs.jsonl")
        assert row["in"] == 1000 and row["out"] == 200, row
        assert row["model"] == "claude-sonnet-4", row


@pytest.mark.integration
def test_track_skills_writes_skills_row(tmp_path, monkeypatch):
    path = str(HOOKS_DIR / "track_skills.py")
    transcript = tmp_path / "skills-transcript.jsonl"
    transcript.write_text(json.dumps({
        "type": "assistant",
        "message": {
            "content": [
                {"type": "tool_use", "name": "Skill", "id": "t1",
                 "input": {"skill": "brush"}},
            ],
        },
    }) + "\n")
    payload = {"session_id": "s", "transcript_path": str(transcript)}

    sub_home, sub_cwd = _fresh_env(tmp_path, "sub")
    code_sub, out_sub, _ = _run_subprocess(path, payload, sub_home, sub_cwd)
    in_home, in_cwd = _fresh_env(tmp_path, "inproc")
    code_in, out_in, _ = _run_in_process(path, payload, in_home, in_cwd, monkeypatch)

    assert (code_in, out_in) == (code_sub, out_sub) == (0, "")
    assert _nonempty(sub_home / ".claude" / "metrics" / "skills.jsonl")
    assert _nonempty(in_home / ".claude" / "metrics" / "skills.jsonl"), (
        "run() must append a skill row under HOME; a no-op leaves it empty"
    )
    # Pin the MEANING: the row must name the skill from the crafted transcript
    # (kills a garbage-writing stub). Key per track_skills.py.
    for home in (sub_home, in_home):
        row = _last_json_row(home / ".claude" / "metrics" / "skills.jsonl")
        assert row["skill"] == "brush", row


@pytest.mark.integration
def test_observe_tool_writes_observation_row(tmp_path, monkeypatch):
    path = str(HOOKS_DIR / "observe_tool.py")
    # A non-empty tool_name on a non-automated session appends one observation
    # under HOME/.claude/instincts/projects/<hash>/observations.jsonl. cwd is a
    # non-git temp dir so project detection is deterministic; the exact <hash>
    # (git-detected or the "global" fallback) is irrelevant - glob catches it.
    payload = {
        "tool_name": "Read",
        "tool_input": {"file_path": "/tmp/x"},
        "tool_response": "ok",
        "session_id": "s",
        "cwd": "/tmp",
    }

    sub_home, sub_cwd = _fresh_env(tmp_path, "sub")
    code_sub, out_sub, _ = _run_subprocess(path, payload, sub_home, sub_cwd)
    in_home, in_cwd = _fresh_env(tmp_path, "inproc")
    code_in, out_in, _ = _run_in_process(path, payload, in_home, in_cwd, monkeypatch)

    assert (code_in, out_in) == (code_sub, out_sub) == (0, "")
    obs = "instincts/projects/*/observations.jsonl"
    assert _glob_nonempty(sub_home / ".claude", obs)
    assert _glob_nonempty(in_home / ".claude", obs), (
        "run() must append an observation under HOME; a no-op leaves none"
    )
    # Pin the MEANING: the row must record the tool and session from the payload
    # (kills a garbage-writing stub). Keys per observe_tool.py.
    for home in (sub_home, in_home):
        row = _last_json_row(_one_nonempty_glob(home / ".claude", obs))
        assert row["tool"] == "Read" and row["sid"] == "s", row


# --------------------------------------------------------------------------- #
# AUTOPILOT-GATED discriminators. Both are gated by $_AUTOPILOT_LOOP (set here,
# in BOTH legs) and locate their autopilot dir by walking up from cwd, so each
# leg gets its own temp cwd carrying dev/local/autopilot/state.json. A no-op
# run() takes neither the exit-2 nor the stdout path.
# --------------------------------------------------------------------------- #
@pytest.mark.integration
def test_review_coverage_hook_blocks_missing_review_exit_2(tmp_path, monkeypatch):
    """phase 'done' hand-off with no review file on disk -> exit 2 (block).
    A no-op run() returns 0, diverging from the subprocess."""
    path = str(SCRIPTS_DIR / "review_coverage_hook.py")
    payload = {"session_id": "s"}
    loop = {"_AUTOPILOT_LOOP": "1"}

    def prep(tag):
        home, cwd = _fresh_env(tmp_path, tag)
        state = cwd / "dev" / "local" / "autopilot" / "state.json"
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(json.dumps({"phase": "done", "prd": "00099-demo.md"}))
        return home, cwd

    sub_home, sub_cwd = prep("sub")
    code_sub, out_sub, _ = _run_subprocess(path, payload, sub_home, sub_cwd, env_extra=loop)
    in_home, in_cwd = prep("inproc")
    code_in, out_in, _ = _run_in_process(path, payload, in_home, in_cwd, monkeypatch, env_extra=loop)

    assert (code_in, out_in) == (code_sub, out_sub)
    assert code_in == 2, "done-phase handoff with no review file must block (exit 2)"
    assert out_in == "" and out_sub == ""


@pytest.mark.integration
def test_autopilot_context_cap_hook_emits_rotation_envelope(tmp_path, monkeypatch):
    """build phase + a transcript whose latest usage total exceeds the cap ->
    a deterministic non-empty rotation envelope on stdout. A no-op run() emits
    nothing, diverging from the subprocess."""
    path = str(SCRIPTS_DIR / "autopilot_context_cap_hook.py")
    transcript = tmp_path / "cap-transcript.jsonl"
    transcript.write_text(json.dumps({
        "message": {"usage": {
            "input_tokens": 600000,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        }},
    }) + "\n")
    payload = {"session_id": "s", "transcript_path": str(transcript)}
    loop = {"_AUTOPILOT_LOOP": "1"}

    def prep(tag):
        home, cwd = _fresh_env(tmp_path, tag)
        state = cwd / "dev" / "local" / "autopilot" / "state.json"
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(json.dumps({"phase": "build", "tasks": []}))
        return home, cwd

    sub_home, sub_cwd = prep("sub")
    code_sub, out_sub, _ = _run_subprocess(path, payload, sub_home, sub_cwd, env_extra=loop)
    in_home, in_cwd = prep("inproc")
    code_in, out_in, _ = _run_in_process(path, payload, in_home, in_cwd, monkeypatch, env_extra=loop)

    # Envelope text is static (limit//1000 == "500K", no task_id/timestamp), so
    # the two legs' stdout are byte-identical.
    assert (code_in, out_in) == (code_sub, out_sub)
    assert out_in != "", "a cap breach must emit a non-empty rotation envelope"
    assert "Context cap reached" in out_in and "Context cap reached" in out_sub
    assert code_in == 0
    # Pin the REAL rotation side effect (kills an emit-envelope-without-rotating
    # stub): state.json must gain a cap_rotations entry and next_phase == build.
    for state_cwd in (sub_cwd, in_cwd):
        st = json.loads((state_cwd / "dev" / "local" / "autopilot" / "state.json").read_text())
        assert st.get("cap_rotations"), "rotation must be recorded in state.cap_rotations"
        assert st.get("next_phase") == "build", st


@pytest.mark.integration
def test_review_coverage_hook_allows_valid_review_exit_0(tmp_path, monkeypatch):
    """OPPOSITE branch of the exit-2 gate: in-loop, phase 'done', AND a passing
    review file present on disk -> exit 0 (allow). Kills a stub that returns 2
    whenever `_AUTOPILOT_LOOP` is set regardless of review state. The review file
    is the minimal shape check_review_file.py accepts (no reviewers named ->
    only a Verdict line and a Tests line are required)."""
    path = str(SCRIPTS_DIR / "review_coverage_hook.py")
    payload = {"session_id": "s"}
    loop = {"_AUTOPILOT_LOOP": "1"}

    def prep(tag):
        home, cwd = _fresh_env(tmp_path, tag)
        ap = cwd / "dev" / "local" / "autopilot"
        ap.mkdir(parents=True, exist_ok=True)
        (ap / "state.json").write_text(json.dumps({"phase": "done", "prd": "00099-demo.md"}))
        reviews = cwd / "dev" / "local" / "reviews"
        reviews.mkdir(parents=True, exist_ok=True)
        # prd_base '00099-demo' + '-review-<n>.md'; body passes the shape check.
        (reviews / "00099-demo-review-1.md").write_text(
            "Verdict: converged\nTests: none (docs-only)\n"
        )
        return home, cwd

    sub_home, sub_cwd = prep("sub")
    code_sub, out_sub, _ = _run_subprocess(path, payload, sub_home, sub_cwd, env_extra=loop)
    in_home, in_cwd = prep("inproc")
    code_in, out_in, _ = _run_in_process(path, payload, in_home, in_cwd, monkeypatch, env_extra=loop)

    assert (code_in, out_in) == (code_sub, out_sub)
    assert code_in == 0, "a passing review file must allow the hand-off (exit 0)"
    assert out_in == "" and out_sub == ""


@pytest.mark.integration
def test_enforce_prd_location_file_mode_blocks_lifecycle_path(tmp_path, monkeypatch):
    """FILE-MODE half (Write/Edit/MultiEdit), which the Bash cases never exercise:
    a Write whose file_path is a repo-root PRD lifecycle dir (`<repo>/backlog/..`)
    must BLOCK (exit 2). File-mode is read-only (it only inspects the path and
    runs `git rev-parse`), so both legs share one git repo; the payload's absolute
    path then resolves identically for subprocess and in-process."""
    path = str(HOOKS_DIR / "enforce_prd_location.py")
    repo = tmp_path / "repo"
    repo.mkdir()
    init = subprocess.run(
        ["git", "init", str(repo)], capture_output=True, text=True, timeout=30
    )
    assert init.returncode == 0, f"git init failed: {init.stderr}"
    blocked = repo / "backlog" / "0001-feature.md"  # dir need not exist
    payload = {"tool_name": "Write", "tool_input": {"file_path": str(blocked)}}

    home, cwd = _fresh_env(tmp_path, "shared")
    code_sub, out_sub, err_sub = _run_subprocess(path, payload, home, cwd)
    code_in, out_in, err_in = _run_in_process(path, payload, home, cwd, monkeypatch)

    assert (code_in, out_in) == (code_sub, out_sub)
    assert code_in == 2, "a repo-root backlog/ file path must BLOCK (exit 2)"
    assert out_in == "" and out_sub == ""
    assert "BLOCKED" in err_in and "BLOCKED" in err_sub
