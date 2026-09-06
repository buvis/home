#!/usr/bin/env python3
"""Personal Codex host adapter for the installed autoclaude workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import selectors
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def codex_model(model: str, env: dict[str, str]) -> str:
    for tier, default in (
        ("sonnet", "gpt-5.6-sol"),
        ("opus", "gpt-6-astra"),
        ("haiku", "gpt-5.6-luna"),
    ):
        if model == tier or model.startswith(f"claude-{tier}-"):
            return env.get(f"AUTOCODEX_{tier.upper()}_MODEL", default)
    if model.startswith("gpt-"):
        return model
    raise ValueError(f"no Codex mapping for {model!r}; configure an explicit supported model")


def codex_argv(binary: str, model: str, effort: str, cwd: Path) -> list[str]:
    return [
        binary,
        "exec",
        "--json",
        "--approve-for-me",
        "--cd",
        str(cwd),
        "--model",
        model,
        "-c",
        f"model_reasoning_effort={json.dumps(effort)}",
        "-",
    ]


def codex_effort(phase: str, model: str, env: dict[str, str]) -> str:
    return env.get("AUTOCODEX_EFFORT") or (
        "medium" if phase == "done" else "xhigh" if "astra" in model else "high"
    )


def claude_argv(binary: str, model: str) -> list[str]:
    return [
        binary,
        "--print",
        "--model",
        model,
        "--effort",
        "xhigh",
        "--permission-mode",
        "auto",
        "--permission-prompts",
        "none",
        "--tools=Read,Glob,Grep,Bash",
        "--output-format",
        "stream-json",
        "--verbose",
    ]


@dataclass
class Events:
    provider: str
    success: bool = False
    text: str = ""
    error: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    thread_id: str = ""

    def accept(self, line: bytes) -> None:
        try:
            event = json.loads(line)
        except (ValueError, UnicodeError):
            return
        if not isinstance(event, dict):
            return
        kind = event.get("type")
        if self.provider == "claude":
            if kind == "result":
                self.success = event.get("is_error") is False
                self.text = str(event.get("result") or "")
                self.error = "" if self.success else self.text
                self.thread_id = str(event.get("session_id") or "")
                self.usage = event.get("usage") or {}
            return
        if kind == "thread.started":
            self.thread_id = str(event.get("thread_id") or "")
        elif kind == "turn.started":
            self.success = False
        elif kind == "turn.completed":
            self.success = True
            self.error = ""
            self.usage = event.get("usage") or {}
        elif kind in ("turn.failed", "error"):
            self.success = False
            self.error = json.dumps(event.get("error") or event.get("message") or event)
        elif kind == "item.completed":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                self.text = str(item.get("text") or "")


@dataclass(frozen=True)
class Result:
    returncode: int
    log: Path
    events: Events
    capped: bool

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and self.events.success and not self.capped


def signal_group(pid: int, sig: int) -> None:
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        pass
    except PermissionError:
        # Darwin can return EPERM for an orphan group containing only zombies.
        # Do not mask a denial involving any live process.
        listing = subprocess.run(
            ["ps", "-ax", "-o", "pgid=,stat="], check=True, capture_output=True, text=True
        )
        members = [
            line.split()[1]
            for line in listing.stdout.splitlines()
            if len(line.split()) == 2 and line.split()[0] == str(pid)
        ]
        if any(not status.startswith("Z") for status in members):
            raise


def stop_group(proc: subprocess.Popen[bytes], grace: float) -> None:
    signal_group(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        pass
    # Descendants may remain after their parent has exited.
    signal_group(proc.pid, signal.SIGKILL)
    proc.wait()


def collect(
    proc: subprocess.Popen[bytes], raw: Any, events: Events, cap: float, grace: float
) -> bool:
    assert proc.stdout is not None
    deadline, heartbeat = time.monotonic() + cap, time.monotonic() + 60
    pending = b""
    with selectors.DefaultSelector() as selector:
        selector.register(proc.stdout, selectors.EVENT_READ)
        while selector.get_map() or proc.poll() is None:
            if time.monotonic() >= deadline:
                stop_group(proc, grace)
                return True
            for key, _ in selector.select(timeout=min(1, max(0, deadline - time.monotonic()))):
                block = os.read(key.fd, 65536)
                if not block:
                    selector.unregister(key.fileobj)
                    continue
                raw.write(block)
                raw.flush()
                pending += block
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    events.accept(line)
            if time.monotonic() >= heartbeat:
                print(f"autocodex: {events.provider} running; raw output: {raw.name}", flush=True)
                heartbeat = time.monotonic() + 60
        if pending:
            events.accept(pending)
    return False


def run_process(
    argv: list[str],
    prompt: str,
    cwd: Path,
    env: dict[str, str],
    stem: Path,
    cap: float,
    *,
    provider: str,
    grace: float = 5,
) -> Result:
    stem.parent.mkdir(parents=True, exist_ok=True)
    log = stem.with_suffix(".jsonl")
    events = Events(provider)
    # A file avoids a large stdin prompt blocking while stdout fills a pipe.
    with (
        tempfile.TemporaryFile() as stdin,
        log.open("xb") as raw,
        stem.with_suffix(".stderr").open("xb") as stderr,
    ):
        stdin.write(prompt.encode())
        stdin.seek(0)
        proc = subprocess.Popen(
            argv,
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=stderr,
            cwd=cwd,
            env=env,
            start_new_session=True,
        )
        try:
            capped = collect(proc, raw, events, cap, grace)
            return Result(proc.wait(), log, events, capped)
        finally:
            stop_group(proc, grace)
            assert proc.stdout is not None
            proc.stdout.close()


def reviewer_env(env: dict[str, str]) -> dict[str, str]:
    result = dict(env)
    # Same isolation as sonnet-run.sh: parent loop hooks must not consume a
    # reviewer's exit. Preserve all dispatch-depth and host nesting guards.
    result.pop("_AUTOPILOT_LOOP", None)
    result.update(CLAUDE_NESTED="1", _CLAUDE_NOTIFY_QUIET="1", WARDEN_UNATTENDED="1")
    return result


def review(prompt: Path, output: Path, model: str, cwd: Path, binary: str) -> int:
    stem = output.parent / f"{output.stem}-{uuid.uuid4().hex}"
    started = time.time()
    result = run_process(
        claude_argv(binary, model),
        prompt.read_text(),
        cwd,
        reviewer_env(dict(os.environ)),
        stem,
        10800,
        provider="claude",
    )
    missing = [
        f"D{n}"
        for n in range(1, 6)
        if not re.search(rf"^D{n}: (?:pass|fail)\b", result.events.text, re.MULTILINE)
    ]
    if not result.ok or missing or not result.events.text.strip():
        print(
            f"autocodex: Claude review failed; missing={missing}; raw={result.log}", file=sys.stderr
        )
        return 1
    # A previous cycle's output must never silently become this cycle's result.
    with output.open("x") as file:
        file.write(result.events.text)
    receipt = {
        "provider": "claude",
        "model": model,
        "started": started,
        "completed": time.time(),
        "output": str(output.resolve()),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "raw": str(result.log),
        "raw_sha256": hashlib.sha256(result.log.read_bytes()).hexdigest(),
        "thread_id": result.events.thread_id,
    }
    state_path = cwd / "dev/local/autopilot/state.json"
    context = json.loads(state_path.read_text()) if state_path.exists() else {}
    receipt.update(
        root=str(cwd.resolve()), prd=context.get("prd", ""), cycle=context.get("cycle", 1)
    )
    with Path(str(output) + ".receipt.json").open("x") as file:
        json.dump(receipt, file, indent=2)
    print(f"autocodex: Claude review saved to {output}")
    return 0


def skill_root() -> Path:
    override = os.environ.get("AUTOCODEX_SKILL_ROOT") or os.environ.get("_AUTOPILOT_SKILL_ROOT")
    if override:
        root = Path(override).expanduser().resolve()
    else:
        cache = Path.home() / ".claude/plugins/cache/buvis-plugins/autopilot"
        versions = [p for p in cache.glob("*") if re.fullmatch(r"\d+\.\d+\.\d+", p.name)]
        versions.sort(key=lambda p: tuple(int(n) for n in p.name.split(".")))
        if not versions:
            raise ValueError(
                "autopilot plugin missing; set AUTOCODEX_SKILL_ROOT to its skills/run-autopilot"
            )
        root = versions[-1] / "skills/run-autopilot"
    for relative in ("SKILL.md", "cli/loop.py", "cli/state.py"):
        if not (root / relative).is_file():
            raise ValueError(f"missing autopilot dependency: {root / relative}")
    return root


def host_prompt(root: Path, cwd: Path, phase: str, extra: str = "") -> str:
    return (HERE / "host.md").read_text().replace("{PLUGIN_ROOT}", str(root.parent.parent)).replace(
        "{DRIVER}", str(HERE / "driver.py")
    ).replace("{CWD}", str(cwd)).replace("{PHASE}", phase or "build (bootstrap)") + (
        "\n\nUser scope:\n" + extra if extra else ""
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--dry-run", action="store_true", help="print routing and prompt without starting a session"
    )
    result.add_argument(
        "--once", action="store_true", help="run one phase session, then stop at its boundary"
    )
    result.add_argument(
        "--scope", type=Path, help="additional user constraints applied to every fresh session"
    )
    result.add_argument("--cd", type=Path, default=Path.cwd())
    sub = result.add_subparsers(dest="command")
    sub.add_parser("status")
    sub.add_parser("pause", help="request a stop after the current phase session")
    reviewer = sub.add_parser("reviewer", help="run the former Codex doubt lane on Claude")
    reviewer.add_argument("-f", "--prompt", type=Path, required=True)
    reviewer.add_argument("-o", "--output", type=Path, required=True)
    reviewer.add_argument(
        "-m", "--model", default=os.environ.get("AUTOCODEX_REVIEWER_MODEL", "opus")
    )
    return result


def lifecycle_command(args: argparse.Namespace, cwd: Path, root: Path) -> int | None:
    ap_dir = cwd / "dev/local/autopilot"
    if args.command not in ("status", "pause"):
        return None
    if not ap_dir.is_dir():
        raise ValueError(f"no autopilot directory at {ap_dir}")
    if args.command == "status":
        return subprocess.call(
            [
                sys.executable,
                str(root / "cli/__main__.py"),
                "status",
                "--state",
                str(ap_dir / "state.json"),
            ]
        )
    (ap_dir / "pause-requested").write_text(json.dumps({"reason": "autocodex pause"}))
    return 0


def print_dry_run(args: argparse.Namespace, cwd: Path, root: Path, routing: Any) -> int:
    ap_dir = cwd / "dev/local/autopilot"
    state = routing._load_json(ap_dir / "state.json") or {}
    phase = state.get("next_phase", "")
    plan = routing.route(phase, ap_dir, env=dict(os.environ))
    model = codex_model(plan.model, dict(os.environ))
    payload = {
        "state": str(ap_dir / "state.json"),
        "phase": phase or "bootstrap",
        "argv": codex_argv("codex", model, codex_effort(phase, model, dict(os.environ)), cwd),
        "reviewer": claude_argv("claude", "opus"),
    }
    print(json.dumps(payload, indent=2))
    print(host_prompt(root, cwd, phase, args.scope.read_text() if args.scope else ""))
    return 0


def main() -> int:
    args = parser().parse_args()
    cwd = args.cd.resolve()
    if args.command == "reviewer":
        return review(
            args.prompt.resolve(),
            args.output.resolve(),
            args.model,
            cwd,
            os.environ.get("AUTOCODEX_CLAUDE_BIN", "claude"),
        )
    root = skill_root()
    sys.path.insert(0, str(root))
    from cli import routing

    from adapter import CodexLoop

    outcome = lifecycle_command(args, cwd, root)
    if outcome is not None:
        return outcome
    if args.dry_run:
        return print_dry_run(args, cwd, root, routing)
    if os.environ.get("_AUTOPILOT_LOOP") and os.environ.get("AUTOCODEX_OWNER") != str(os.getpid()):
        raise ValueError("a parent autopilot loop is active; nested loops are refused")
    # Direct exec starts with this tag, so the shared registry can identify us.
    if os.environ.get("AUTOCODEX_OWNER") != str(os.getpid()):
        env = dict(os.environ, AUTOCODEX_OWNER=str(os.getpid()), _AUTOPILOT_LOOP=str(os.getpid()))
        os.execve(sys.executable, [sys.executable, str(HERE / "driver.py"), *sys.argv[1:]], env)
    return CodexLoop(root, cwd, args.scope, args.once).run()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"autocodex: {error}", file=sys.stderr)
        raise SystemExit(1) from error
