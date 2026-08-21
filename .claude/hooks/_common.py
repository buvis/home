"""Shared helpers for Claude Code hooks under ~/.claude/hooks/.

Stdlib only. Python 3.10+. Safe to import from any PreToolUse / PostToolUse /
Notification / Stop hook script.

Conventions
-----------
- Hooks read a single JSON object from stdin and signal allow/block via exit
  code: 0 = allow, 2 = block (with a human-readable reason on stderr).
- Gateguard-style hooks that emit a JSON envelope on stdout instead of exiting
  with code 2 do not use this module's `block()` helper.
"""

import io
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Callable, NoReturn


def read_input() -> dict[str, Any]:
    """Parse stdin as JSON. Return {} on empty input or parse failure.

    Hooks must remain non-fatal on bad input so a malformed payload never
    blocks an otherwise-valid tool call.
    """
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def block(reason: str) -> NoReturn:
    """Print reason to stderr and exit 2 (block the tool call)."""
    print(reason, file=sys.stderr)
    sys.exit(2)


def allow() -> NoReturn:
    """Exit 0 (allow the tool call)."""
    sys.exit(0)


def log_path(name: str) -> Path:
    """Resolve a log file under ~/.claude/hooks/."""
    return Path.home() / ".claude" / "hooks" / name


def secret_path(name: str) -> Path:
    """Resolve a secret file under ~/.claude/secrets/."""
    return Path.home() / ".claude" / "secrets" / name


_TOPLEVEL_CACHE: dict[str, str | None] = {}


def resolve_toplevel(path: str) -> str | None:
    """Resolve the git toplevel containing `path` via `git rev-parse
    --show-toplevel`.

    Memoized per process by the nearest existing ancestor directory of
    `path` (PRD 00133 finding 42), so hooks that independently need the
    toplevel for the same tool call - e.g. enforce_prd_location.py and
    cartographer-echo.py, both invoked with the same payload in the same
    dispatcher process - spawn `git` at most once between them. `path`
    itself need not exist; the walk finds the nearest existing ancestor
    directory first.
    """
    resolved = str(Path(path).resolve())
    probe = resolved
    while probe and probe != "/" and not os.path.isdir(probe):
        probe = os.path.dirname(probe)
    if not probe or not os.path.isdir(probe):
        return None
    if probe in _TOPLEVEL_CACHE:
        return _TOPLEVEL_CACHE[probe]
    try:
        result = subprocess.run(
            ["git", "-C", probe, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        root = result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        root = None
    root = root or None
    _TOPLEVEL_CACHE[probe] = root
    return root


def append_jsonl_row(path: Path, row: str) -> None:
    """Append `row` as a new row to a JSONL file, creating it if needed.

    If the file already has content whose last byte isn't a newline (e.g. a
    partial write before a crash), a leading newline is written first so the
    new row still lands on its own line. Appends via mode="a" (POSIX
    O_APPEND), writing once inside the `with` block per this codebase's
    JSONL/log-append convention.
    """
    needs_leading_newline = False
    if path.exists() and path.stat().st_size > 0:
        with path.open("rb") as fh:
            fh.seek(-1, io.SEEK_END)
            needs_leading_newline = fh.read(1) != b"\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(("\n" if needs_leading_newline else "") + row + "\n")


_TRANSCRIPT_CACHE: dict[Path, list[dict[str, Any]]] = {}


def parse_transcript_entries(path: Path) -> list[dict[str, Any]]:
    """Parse a transcript JSONL file into a list of dict entries.

    Cached per path so track_cost.py and track_skills.py, which both parse
    the same Stop-hook transcript in-process, read the file at most once.
    Skips malformed JSON lines and non-dict JSON values. A missing file
    returns an empty list without raising.
    """
    if path in _TRANSCRIPT_CACHE:
        return _TRANSCRIPT_CACHE[path]
    entries: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        _TRANSCRIPT_CACHE[path] = entries
        return entries
    for raw in text.splitlines():
        if not raw.strip():
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    _TRANSCRIPT_CACHE[path] = entries
    return entries


class HandlerTimeout(BaseException):
    """Raised by the dispatcher's SIGALRM handler.

    Subclasses BaseException (NOT Exception) so a handler's own `except
    Exception` - and capture_main's isolation `except Exception` - cannot
    swallow the wall-clock cap. Only the dispatcher's `_invoke` catches it.
    """


def capture_main(fn: Callable[[], Any], payload: dict) -> tuple[int, str, str]:
    """Run `fn()` with `payload` fed as stdin JSON, capturing stdout/stderr.

    Swaps sys.stdin/stdout/stderr/argv for the call and restores all four in a
    `finally`. Returns (exit_code, captured_stdout, captured_stderr).

    Exit code:
    - `fn()` returns int -> that int, else 0.
    - SystemExit -> its int code, 0 when None, 1 otherwise.
    - any other Exception -> 0, with the traceback appended to captured stderr
      (handler isolation). HandlerTimeout (BaseException) is NOT caught here, so
      the dispatcher's wall-clock cap propagates; streams are restored first.
    """
    old_stdin, old_stdout, old_stderr, old_argv = (
        sys.stdin,
        sys.stdout,
        sys.stderr,
        sys.argv,
    )
    cap_out, cap_err = io.StringIO(), io.StringIO()
    sys.stdin = io.StringIO(json.dumps(payload))
    sys.stdout = cap_out
    sys.stderr = cap_err
    sys.argv = [old_argv[0]]
    code = 0
    try:
        try:
            ret = fn()
            code = ret if isinstance(ret, int) and not isinstance(ret, bool) else 0
        except SystemExit as exc:
            if isinstance(exc.code, int) and not isinstance(exc.code, bool):
                code = exc.code
            elif exc.code is None:
                code = 0
            else:
                code = 1
        except Exception:
            code = 0
            cap_err.write(traceback.format_exc())
    finally:
        sys.stdin = old_stdin
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        sys.argv = old_argv
    return code, cap_out.getvalue(), cap_err.getvalue()
