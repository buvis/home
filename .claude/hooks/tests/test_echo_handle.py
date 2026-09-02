"""In-process tests for hooks/cartographer-echo.py's `handle()` and `main()`
(the subprocess-driven end-to-end tests live in test_cartographer_echo.py),
plus the real-dispatch regression that pins one `git rev-parse` spawn per
PreToolUse Edit.

The hook is loaded by path with HOME redirected to tmp_path through
`echo_test_helpers.isolate_hook_for_direct_call`.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from .echo_test_helpers import HOOK, isolate_hook_for_direct_call, read_audit

# --- Direct-call coverage (handle / main bypass subprocess for line coverage) ---


def test_handle_direct_call_unknown_tool_no_audit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    mod = isolate_hook_for_direct_call(monkeypatch, tmp_path)
    mod.handle(
        {"tool_name": "Read", "tool_input": {"file_path": "/tmp/x"}, "session_id": "s"},
    )
    events = read_audit(tmp_path)
    assert all(e.get("tool") != "Read" for e in events)


def test_handle_direct_call_edit_skip_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    mod = isolate_hook_for_direct_call(monkeypatch, tmp_path)
    mod.handle(
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(tmp_path / ".claude" / "settings.json"),
                "old_string": "x",
                "new_string": "y",
            },
            "session_id": "s",
        },
    )
    events = read_audit(tmp_path)
    assert any(e.get("reason") == "settings" for e in events)


def test_handle_direct_call_bash_clean(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    mod = isolate_hook_for_direct_call(monkeypatch, tmp_path)
    mod.handle(
        {"tool_name": "Bash", "tool_input": {"command": "ls -la"}, "session_id": "s"},
    )
    events = read_audit(tmp_path)
    assert any(e.get("reason") == "bash-clean" for e in events)


def test_handle_direct_call_write_no_symbols(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    mod = isolate_hook_for_direct_call(monkeypatch, tmp_path)
    iso = tmp_path / "iso"
    iso.mkdir()
    mod.handle(
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(iso / "x.py"),
                "content": "# comment only\n",
            },
            "session_id": "s",
        },
    )
    events = read_audit(tmp_path)
    assert any(e.get("reason") == "no-symbols" for e in events)


def test_handle_direct_call_bash_bypass_deny_and_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys,
) -> None:
    mod = isolate_hook_for_direct_call(monkeypatch, tmp_path)
    (tmp_path / "src").mkdir()
    monkeypatch.chdir(tmp_path)
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "cat > src/util.py <<EOF\ndef foo(): pass\nEOF"},
        "session_id": "s-bash-direct",
    }
    mod.handle(payload)
    out = capsys.readouterr().out
    assert out.strip(), "expected deny envelope"
    env = json.loads(out)
    assert env["hookSpecificOutput"]["permissionDecision"] == "deny"
    # Second call → allow.
    mod.handle(payload)
    out2 = capsys.readouterr().out
    if out2.strip():
        env2 = json.loads(out2)
        assert env2["hookSpecificOutput"]["permissionDecision"] != "deny"


def test_handle_direct_call_edit_deny_and_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys,
) -> None:
    mod = isolate_hook_for_direct_call(monkeypatch, tmp_path)
    root = tmp_path / "proj"
    root.mkdir()
    (root / "lib.py").write_text("def formatPrice(p):\n    return p\n")
    monkeypatch.chdir(root)
    payload = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(root / "price.py"),
            "content": "def formatPrice(p):\n    return f'${p}'\n",
        },
        "session_id": "s-edit-direct",
    }
    mod.handle(payload)
    out = capsys.readouterr().out
    env = json.loads(out)
    assert env["hookSpecificOutput"]["permissionDecision"] == "deny"
    # Retry → allow.
    mod.handle(payload)
    out2 = capsys.readouterr().out
    if out2.strip():
        env2 = json.loads(out2)
        assert env2["hookSpecificOutput"]["permissionDecision"] != "deny"


def test_main_function_parses_stdin(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Cover main()'s json parse + handle() dispatch + exception path."""
    mod = isolate_hook_for_direct_call(monkeypatch, tmp_path)
    payload = {"tool_name": "Bash", "tool_input": {"command": "ls"}, "session_id": "s"}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    assert mod.main() == 0


@pytest.mark.parametrize("stdin_text", ["", "{ not json", "[1, 2, 3]"])
def test_main_tolerates_empty_malformed_and_non_dict_stdin(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stdin_text: str,
) -> None:
    mod = isolate_hook_for_direct_call(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin_text))
    assert mod.main() == 0


# --- Real dispatch regression: one PreToolUse Edit costs one git spawn ---
#
# NARROWED, and honestly so: this used to prove the spawn was shared ACROSS two
# in-process handlers, enforce_prd_location and cartographer-echo, via
# `_common._TOPLEVEL_CACHE`. enforce_prd_location is now a separate hook process
# registered by the autopilot plugin, so it cannot share that cache at all and
# spawns its own `git rev-parse` per tool call. cartographer-echo is the only
# `resolve_toplevel` consumer left on this route, so what remains here is the
# weaker single-handler claim: it resolves once, not per file. The cross-handler
# guarantee finding 42 secured is gone, not merely untested.
#
# Scoped to `-C`-shaped calls: cartographer-echo's handler also spawns a
# separate, out-of-scope `git rev-parse --show-toplevel` (no `-C`, cwd-relative)
# via `_cartographer_identity.project_hash()`.


def _git_toplevel_call_counter(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Patch subprocess.run to count resolve_toplevel-shaped
    (`-C <dir> rev-parse --show-toplevel`) spawns into a mutable counter."""
    calls = [0]
    original_run = subprocess.run

    def counting_run(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args")
        if cmd and "-C" in cmd and "rev-parse" in cmd and "--show-toplevel" in cmd:
            calls[0] += 1
        return original_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", counting_run)
    return calls


def _prepare_edit_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Prepare one PreToolUse Edit dispatch and return its JSON payload.

    Side effects beyond building the payload: points HOME at tmp_path,
    inserts the hooks dir onto sys.path so handler modules can import their
    siblings, git-inits a fresh temp repo, and clears the shared
    `_common._TOPLEVEL_CACHE` so the dispatch under test starts cold.
    """
    hooks_dir = HOOK.parent
    monkeypatch.setenv("HOME", str(tmp_path))
    if str(hooks_dir) not in sys.path:
        sys.path.insert(0, str(hooks_dir))

    import _common

    _common._TOPLEVEL_CACHE.clear()

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(repo)],
        check=True,
        capture_output=True,
    )
    target = repo / "src" / "widget.py"  # parent dir does not exist yet
    payload = {
        "session_id": "sess-shared-toplevel",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(target),
            "old_string": "pass",
            "new_string": "def widgetFactory():\n    pass\n",
        },
    }
    return json.dumps(payload)


def _invoked_route_names(monkeypatch: pytest.MonkeyPatch, dispatch) -> list[str]:
    """Patch dispatch._invoke to record each route name it actually runs, so
    the test can positively confirm both target handlers were dispatched."""
    names: list[str] = []
    original_invoke = dispatch._invoke

    def recording_invoke(route, payload):
        names.append(route.name)
        return original_invoke(route, payload)

    monkeypatch.setattr(dispatch, "_invoke", recording_invoke)
    return names


def test_single_edit_dispatch_spawns_git_rev_parse_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    """One PreToolUse Edit dispatched through dispatch.main("pre") -- which
    runs every ROUTES handler matching Edit|Write|MultiEdit, each isolated by
    dispatch's own per-handler `_invoke` -- must spawn `_common.
    resolve_toplevel`'s `git -C <dir> rev-parse --show-toplevel` at most once
    total (PRD 00133 finding 42). Also asserts cartographer-echo was actually
    dispatched and did not fault -- a crash is caught and swallowed by
    `_invoke` per handler, so a naive spawn-count check alone would stay green
    even if cartographer-echo crashed before resolving."""
    import dispatch

    stdin_json = _prepare_edit_dispatch(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin_json))
    calls = _git_toplevel_call_counter(monkeypatch)
    invoked = _invoked_route_names(monkeypatch, dispatch)

    with pytest.raises(SystemExit):
        dispatch.main("pre")

    assert calls[0] == 1, (
        f"expected exactly one _common.resolve_toplevel git spawn across "
        f"all dispatched handlers, got {calls[0]}"
    )
    assert "cartographer-echo" in invoked, (
        f"expected cartographer-echo to actually be dispatched, got {invoked}"
    )
    assert "enforce_prd_location" not in invoked, (
        f"enforce_prd_location is the autopilot plugin's hook now; routing it "
        f"here as well would fire it twice per tool call, got {invoked}"
    )
    out, err = capsys.readouterr()
    combined = out + err
    assert "Traceback" not in combined, combined
    assert "[dispatch] cartographer-echo:" not in combined, combined
