#!/usr/bin/env python3
"""Personal Codex host adapter for the installed autoclaude workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
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


def model_provider(model: object) -> str:
    """Resolve model origin, never launcher identity or an ambiguous tier alias."""
    if not isinstance(model, str):
        raise ValueError("missing actual model evidence")
    value = model.lower()
    if re.fullmatch(r"(?:openai[/.])?gpt-[a-z0-9][a-z0-9._/-]*", value):
        return "openai"
    if re.fullmatch(
        r"(?:(?:us\.|eu\.|global\.)?anthropic[/.])?claude-[a-z0-9][a-z0-9._:/\[\]-]*", value
    ):
        return "anthropic"
    raise ValueError(f"unrecognized actual model evidence: {model!r}")


def review_providers(state: dict) -> list[str]:
    """All contributing attempts count, including earlier attempts and repairs."""
    providers = set()
    tasks = state.get("tasks") or []
    if not tasks:
        raise ValueError("missing task model evidence; inspect implementation logs")
    for task in tasks:
        attempts = task.get("attempts") or []
        if not attempts:
            raise ValueError(f"missing model evidence for task {task.get('id')}")
        for attempt in attempts:
            provider = model_provider(attempt.get("actual_model"))
            recorded = attempt.get("actual_provider")
            if recorded is not None and recorded != provider:
                raise ValueError(f"conflicting model/provider evidence for task {task.get('id')}")
            providers.add(provider)
    return sorted({"openai" if item == "anthropic" else "anthropic" for item in providers})


def implementation_snapshot(state: dict) -> dict:
    """Keep only provenance inputs, independent of later review annotations."""
    data = {key: state.get(key) for key in ("prd", "cycle", "work_start_sha")}
    data["tasks"] = [
        {
            "id": task["id"],
            "attempts": [
                {
                    key: attempt.get(key)
                    for key in (
                        "attempt",
                        "actual_model",
                        "actual_provider",
                        "implementor",
                        "outcome",
                    )
                }
                for attempt in task.get("attempts", [])
            ],
        }
        for task in state.get("tasks", [])
    ]
    return data


def implementation_fingerprint(state: dict) -> str:
    return hashlib.sha256(
        json.dumps(implementation_snapshot(state), sort_keys=True).encode()
    ).hexdigest()


def audited_review_providers(state: dict, cwd: Path) -> list[str]:
    """Check the coordinator's log audit; never mine arbitrary prose for models."""
    path = (
        cwd
        / "docs/dev/project-management/autopilot/reports"
        / f"{Path(state['prd']).stem}-implementation-models.json"
    )
    audit = json.loads(path.read_text())
    if audit.get("fingerprint") != implementation_fingerprint(state):
        raise ValueError("stale implementation model audit; inspect current attempt logs")
    providers = set(review_providers(state))
    covered = set()
    entries = audit.get("evidence") or []
    for entry in entries:
        if entry.get("role") != "implementation":
            raise ValueError(
                "reviewer/coordinator evidence cannot establish implementation provider"
            )
        source = (cwd / entry["path"]).resolve()
        source.relative_to(cwd.resolve())
        line = source.read_bytes().splitlines()[entry["line"] - 1]
        if entry["line"] < 1 or hashlib.sha256(line).hexdigest() != entry["sha256"]:
            raise ValueError("implementation model log evidence changed")
        model = entry["model"]
        if model not in line.decode():
            raise ValueError("model missing from cited implementation log")
        provider = model_provider(model)
        providers.add("openai" if provider == "anthropic" else "anthropic")
        covered.add(str(entry["task"]))
    if covered != {str(task["id"]) for task in state["tasks"]}:
        raise ValueError("implementation model audit must cover every task")
    return sorted(providers)


def review_rules(lens: str) -> list[str]:
    if lens == "bob":
        return [f"D{n}" for n in range(1, 6)]
    relative = {
        "alice": "review-work-completion/references/rubric.md",
        "blake": "review-blindly/references/rubric.md",
    }[lens]
    return re.findall(r"^([RB]\d+):", (skill_root().parent / relative).read_text(), re.MULTILINE)


def codex_model(model: str, env: dict[str, str]) -> str:
    for tier, default in (
        ("sonnet", "gpt-6.1-sol"),
        ("opus", "gpt-6.1-sol"),
        ("haiku", "gpt-6-luna"),
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


def role_effort(role: str, env: dict[str, str]) -> str:
    if env.get("AUTOCODEX_EFFORT"):
        raise ValueError(
            "AUTOCODEX_EFFORT is no longer supported; use AUTOCODEX_COORDINATOR_EFFORT "
            "and role-specific AUTOCODEX_<ROLE>_EFFORT settings"
        )
    defaults = {
        "coordinator": "low",
        "haiku": "low",
        "sonnet": "medium",
        "opus": "high",
        "review": "high",
        "escalation": "high",
    }
    effort = env.get(f"AUTOCODEX_{role.upper()}_EFFORT") or defaults[role]
    if effort not in {"low", "medium", "high", "xhigh", "max"}:
        raise ValueError(f"invalid {role} effort: {effort!r}")
    return effort


def coordinator_model(source_model: str, env: dict[str, str]) -> str:
    # Explicit provider-native phase overrides remain deliberate overrides.
    return env.get("AUTOCODEX_COORDINATOR_MODEL") or (
        source_model if source_model.startswith("gpt-") else "gpt-6.1-sol"
    )


def codex_effort(phase: str, model: str, env: dict[str, str]) -> str:
    """Main-session effort is independent of phase, worker tier, and model."""
    return role_effort("coordinator", env)


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
    quota_reset: float | None = None
    api_status: int | None = None

    def accept(self, line: bytes) -> bool:
        try:
            event = json.loads(line)
        except (ValueError, UnicodeError):
            return False
        if not isinstance(event, dict):
            return False
        kind = event.get("type")
        if self.provider == "claude":
            if kind == "rate_limit_event":
                info = event.get("rate_limit_info")
                self.quota_reset = None
                if isinstance(info, dict) and info.get("status") == "rejected":
                    reset = info.get("resetsAt")
                    if isinstance(reset, (int, float)) and not isinstance(reset, bool):
                        try:
                            reset = float(reset)
                        except OverflowError:
                            return True
                        if math.isfinite(reset) and reset > 0:
                            self.quota_reset = reset
            if kind == "result":
                self.success = event.get("is_error") is False
                self.text = str(event.get("result") or "")
                self.error = "" if self.success else self.text
                self.thread_id = str(event.get("session_id") or "")
                self.usage = event.get("usage") or {}
                self.api_status = event.get("api_error_status")
            return True
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
        return substantive_event(event)


def substantive_event(event: dict[str, Any]) -> bool:
    kind = event.get("type")
    if kind in {"thread.started", "turn.started", "turn.completed", "turn.failed", "error"}:
        return True
    if not isinstance(kind, str) or not kind.startswith("item."):
        return False
    item = event.get("item")
    return not (
        isinstance(item, dict)
        and item.get("type") == "collab_tool_call"
        and item.get("tool") == "wait"
    )


@dataclass(frozen=True)
class Result:
    returncode: int
    log: Path
    events: Events
    stalled: bool

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and self.events.success and not self.stalled


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


_IGNORED_WORKSPACE_DIRS = frozenset(
    {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "__pycache__", "node_modules"}
)


def workspace_stamp(cwd: Path, ignored_paths: set[Path]) -> bytes:
    digest = hashlib.blake2b(digest_size=16)
    for directory, dirnames, filenames in os.walk(cwd, onerror=lambda _error: None):
        dirnames[:] = sorted(name for name in dirnames if name not in _IGNORED_WORKSPACE_DIRS)
        root = Path(directory)
        for name in sorted(filenames):
            path = root / name
            if path in ignored_paths:
                continue
            try:
                status = path.stat(follow_symlinks=False)
                relative = path.relative_to(cwd)
            except (OSError, ValueError):
                continue
            digest.update(os.fsencode(relative))
            digest.update(f"\0{status.st_mtime_ns}\0{status.st_size}\0".encode())
    return digest.digest()


def collect(
    proc: subprocess.Popen[bytes],
    raw: Any,
    events: Events,
    stall_timeout: float,
    grace: float,
    cwd: Path,
    ignored_paths: set[Path],
) -> bool:
    assert proc.stdout is not None
    if not math.isfinite(stall_timeout) or stall_timeout <= 0:
        raise ValueError("stall timeout must be a positive finite number")
    now = time.monotonic()
    last_progress, heartbeat = now, now + 60
    probe_interval = min(30.0, max(0.05, stall_timeout / 4))
    next_probe = now + probe_interval
    stamp = workspace_stamp(cwd, ignored_paths)
    pending = b""
    with selectors.DefaultSelector() as selector:
        selector.register(proc.stdout, selectors.EVENT_READ)
        while selector.get_map() or proc.poll() is None:
            now = time.monotonic()
            if now >= next_probe or now - last_progress >= stall_timeout:
                current = workspace_stamp(cwd, ignored_paths)
                if current != stamp:
                    stamp = current
                    last_progress = now
                next_probe = now + probe_interval
            if now - last_progress >= stall_timeout:
                events.error = f"no substantive activity for {stall_timeout:g} seconds"
                stop_group(proc, grace)
                return True
            wake_at = min(last_progress + stall_timeout, next_probe, heartbeat)
            for key, _ in selector.select(timeout=min(1, max(0, wake_at - now))):
                block = os.read(key.fd, 65536)
                if not block:
                    selector.unregister(key.fileobj)
                    continue
                raw.write(block)
                raw.flush()
                pending += block
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    if events.accept(line):
                        last_progress = time.monotonic()
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
    stall_timeout: float,
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
            stalled = collect(
                proc,
                raw,
                events,
                stall_timeout,
                grace,
                cwd,
                {log, stem.with_suffix(".stderr")},
            )
            return Result(proc.wait(), log, events, stalled)
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


def wait_for_reviewer_quota(result: Result, cwd: Path, deadline: float) -> bool:
    reset = result.events.quota_reset
    if result.ok or result.stalled or result.events.api_status != 429 or reset is None:
        return False
    delay = reset - time.time()
    # Do not spin on stale resets, infer timestamps from prose, or retry early.
    if delay <= 0 or delay + 5 >= deadline - time.monotonic():
        return False
    target = time.monotonic() + delay + 5
    reset_label = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(reset))
    print(
        f"autocodex: Claude quota exhausted; waiting until {reset_label} + 5s; raw={result.log}",
        flush=True,
    )
    pause = cwd / "docs/dev/project-management/autopilot/pause-requested"
    while True:
        if pause.exists() or time.monotonic() >= deadline:
            return False
        remaining = target - time.monotonic()
        if remaining <= 0:
            return True
        time.sleep(min(60, remaining))


def run_reviewer(prompt: str, output: Path, model: str, cwd: Path, binary: str) -> Result:
    env = reviewer_env(dict(os.environ))
    stall_timeout = float(
        env.get("AUTOCODEX_REVIEWER_STALL_TIMEOUT", env.get("AUTOCODEX_STALL_TIMEOUT", "1800"))
    )
    wait_deadline = time.monotonic() + int(env.get("_AUTOPILOT_LIMIT_WAIT_MAX", "21600"))
    while True:
        stem = output.parent / f"{output.stem}-{uuid.uuid4().hex}"
        result = run_process(
            (
                codex_argv(binary, model, role_effort("review", env), cwd)
                if model_provider_for_review(model) == "openai"
                else claude_argv(binary, model)
            ),
            prompt,
            cwd,
            env,
            stem,
            stall_timeout,
            provider="codex" if model_provider_for_review(model) == "openai" else "claude",
        )
        if model_provider_for_review(model) == "openai" or not wait_for_reviewer_quota(
            result, cwd, wait_deadline
        ):
            return result
        print("autocodex: Claude quota reset reached; retrying reviewer", flush=True)


def model_provider_for_review(model: str) -> str:
    # Explicit Claude CLI tier selection is allowed for reviewers only.
    return "anthropic" if model in {"opus", "sonnet", "haiku"} else model_provider(model)


def review(
    prompt: Path, output: Path, model: str, cwd: Path, binary: str, lens: str = "bob"
) -> int:
    started = time.time()
    result = run_reviewer(prompt.read_text(), output, model, cwd, binary)
    missing = [
        rule
        for rule in review_rules(lens)
        if not re.search(rf"^{rule}: (?:pass|fail)\b", result.events.text, re.MULTILINE)
    ]
    if not result.ok or missing or not result.events.text.strip():
        print(f"autocodex: review failed; missing={missing}; raw={result.log}", file=sys.stderr)
        return 1
    # A previous cycle's output must never silently become this cycle's result.
    with output.open("x") as file:
        file.write(result.events.text)
    receipt = {
        "provider": result.events.provider,
        "model_provider": model_provider_for_review(model),
        "lens": lens,
        "model": model,
        "started": started,
        "completed": time.time(),
        "output": str(output.resolve()),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "raw": str(result.log),
        "raw_sha256": hashlib.sha256(result.log.read_bytes()).hexdigest(),
        "thread_id": result.events.thread_id,
    }
    state_path = cwd / "docs/dev/project-management/autopilot/state.json"
    context = json.loads(state_path.read_text()) if state_path.exists() else {}
    receipt.update(
        root=str(cwd.resolve()),
        prd=context.get("prd", ""),
        cycle=context.get("cycle", 1),
        implementation_fingerprint=implementation_fingerprint(context),
    )
    with Path(str(output) + ".receipt.json").open("x") as file:
        json.dump(receipt, file, indent=2)
    print(f"autocodex: review saved to {output}")
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


def host_prompt(
    root: Path, cwd: Path, phase: str, extra: str = "", env: dict[str, str] | None = None
) -> str:
    effective_env = dict(os.environ) if env is None else env
    mapping = "; ".join(
        f"{tier} = {codex_model(tier, effective_env)} / {role_effort(tier, effective_env)}"
        for tier in ("haiku", "sonnet", "opus")
    )
    review = (
        f"{effective_env.get('AUTOCODEX_REVIEW_MODEL') or 'gpt-6.1-sol'} / "
        f"{role_effort('review', effective_env)}"
    )
    escalation = (
        f"{effective_env.get('AUTOCODEX_ESCALATION_MODEL') or 'gpt-6-astra'} / "
        f"{role_effort('escalation', effective_env)}"
    )
    return (HERE / "host.md").read_text().replace("{ROLE_MAPPING}", mapping).replace(
        "{REVIEW_ROLE}", review
    ).replace("{ESCALATION_ROLE}", escalation).replace(
        "{PLUGIN_ROOT}", str(root.parent.parent)
    ).replace("{DRIVER}", str(HERE / "driver.py")).replace("{CWD}", str(cwd)).replace(
        "{PHASE}", phase or "build (bootstrap)"
    ) + ("\n\nUser scope:\n" + extra if extra else "")


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
    sub.add_parser("review-route", help="resolve reviewer providers from recorded actual models")
    sub.add_parser("pause", help="request a stop after the current phase session")
    reviewer = sub.add_parser(
        "reviewer", help="run an isolated reviewer with raw evidence and a receipt"
    )
    reviewer.add_argument("--lens", choices=("alice", "blake", "bob"), default="bob")
    reviewer.add_argument("-f", "--prompt", type=Path, required=True)
    reviewer.add_argument("-o", "--output", type=Path, required=True)
    reviewer.add_argument(
        "-m", "--model", default=os.environ.get("AUTOCODEX_REVIEWER_MODEL", "opus")
    )
    return result


def is_fast_track_handoff(path: Path | None) -> bool:
    return path is not None and "fast-track-handoffs" in path.parts


def lifecycle_command(args: argparse.Namespace, cwd: Path, root: Path) -> int | None:
    ap_dir = cwd / "docs/dev/project-management/autopilot"
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
    ap_dir = cwd / "docs/dev/project-management/autopilot"
    state = routing._load_json(ap_dir / "state.json") or {}
    phase = state.get("next_phase", "")
    plan = routing.route(phase, ap_dir, env=dict(os.environ))
    model = coordinator_model(plan.model, dict(os.environ))
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
    if args.command == "review-route":
        state_path = cwd / "docs/dev/project-management/autopilot/state.json"
        try:
            providers = audited_review_providers(json.loads(state_path.read_text()), cwd)
        except (ValueError, OSError, KeyError, IndexError, TypeError) as error:
            print(f"autocodex: review routing paused: {error}", file=sys.stderr)
            return 1
        print(json.dumps({"review_providers": providers}))
        return 0
    if args.command == "reviewer":
        provider = model_provider_for_review(args.model)
        return review(
            args.prompt.resolve(),
            args.output.resolve(),
            args.model,
            cwd,
            os.environ.get("AUTOCODEX_CODEX_BIN", "codex")
            if provider == "openai"
            else os.environ.get("AUTOCODEX_CLAUDE_BIN", "claude"),
            args.lens,
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
    if is_fast_track_handoff(args.scope) and not args.once:
        print("autocodex: fast-track handoff detected; running one fresh session (--once)")
        args.once = True
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
