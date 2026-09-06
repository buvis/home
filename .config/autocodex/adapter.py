"""Reuse autoclaude's lifecycle policy with Codex process and review boundaries."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from cli import loop, routing, schema
from cli import state as state_mod

import driver


def read_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def review_gap(state: dict, root: Path, cwd: Path, cycle: int) -> str | None:
    from cli import gate

    cycles = state.get("review_cycles") or []
    if not cycles or not isinstance(cycles[-1], dict):
        return "review has no recorded cycle artifact"
    if cycles[-1].get("cycle") != cycle:
        return "review artifact belongs to another cycle"
    path = cwd / cycles[-1].get("review_file", "")
    try:
        text = path.read_text()
    except OSError as error:
        return f"review artifact unreadable: {error}"
    gap = gate.check(text, ["alice", "blake", "bob"], require_codex_guard=True)
    if gap:
        return gap
    for persona, rubric in (
        ("Alice", root.parent / "review-work-completion/references/rubric.md"),
        ("Blake", root.parent / "review-blindly/references/rubric.md"),
    ):
        rules = re.findall(r"^([RB]\d+):", rubric.read_text(), re.MULTILINE)
        section = re.search(
            rf"^## {persona}\b[^\n]*\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL
        )
        if not section or any(
            not re.search(rf"^{rule}: (?:pass|fail)\b", section[1], re.MULTILINE) for rule in rules
        ):
            return f"{persona} lacks the complete source rubric"
    gap = bob_gap(text, cwd, cycle, state.get("prd", ""))
    if gap:
        return gap
    verdicts = state.get("doubts_rubric_verdicts") or []
    ids = {item.get("rule_id") for item in verdicts if isinstance(item, dict)}
    if not {f"D{n}" for n in range(1, 6)}.issubset(ids):
        return "state lacks the complete Bob doubt rubric"
    return None


def bob_gap(text: str, cwd: Path, cycle: int, prd: str) -> str | None:
    match = re.search(r"^autocodex_bob_receipt: (.+)$", text, re.MULTILINE)
    if not match:
        return "missing Claude Bob receipt"
    try:
        receipt = json.loads((cwd / match[1].strip()).read_text())
        raw = Path(receipt["output"]).read_bytes()
        if (
            receipt["provider"] != "claude"
            or receipt["cycle"] != cycle
            or receipt["prd"] != prd
            or receipt["root"] != str(cwd.resolve())
        ):
            return "Bob receipt is stale or names the wrong provider"
        if hashlib.sha256(raw).hexdigest() != receipt["sha256"]:
            return "Bob output changed after dispatch"
        captured = Path(receipt["raw"]).read_bytes()
        if hashlib.sha256(captured).hexdigest() != receipt["raw_sha256"]:
            return "Bob raw evidence changed after dispatch"
        events = driver.Events("claude")
        for line in captured.splitlines():
            events.accept(line)
        if not events.success or events.text.encode() != raw:
            return "Bob output does not match a successful Claude result"
        for n in range(1, 6):
            if not re.search(rf"^D{n}: (?:pass|fail)\b", raw.decode(), re.MULTILINE):
                return f"Bob missing D{n}"
    except (OSError, ValueError, KeyError, TypeError) as error:
        return f"invalid Bob receipt: {error}"
    return None


class CodexLoop(loop.Loop):
    def __init__(
        self, root: Path, cwd: Path, scope: Path | None, once: bool, **kwargs: Any
    ) -> None:
        self.root, self.once = root, once
        env = dict(os.environ, _AUTOPILOT_LOOP=str(os.getpid()))
        super().__init__(cwd=cwd, env=env, runner_bin="codex", **kwargs)
        self._lock: Any = None
        self._result: driver.Result | None = None
        self._before: bytes | None = None
        self._before_state: dict = {}
        self._started = 0.0
        self._actual_model = ""
        self._launched = 0
        self._limit_started: float | None = None
        self._scope = scope.read_text() if scope else ""

    def _resolve_ap_dir(self) -> Path:
        path = self.cwd / "dev/local/autopilot"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _register(self, ap_dir: Path) -> int | None:
        if self._lock is None:
            self._lock = (ap_dir / "autocodex.lock").open("a+")
            try:
                fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("autocodex: another autocodex loop owns this project", file=self.err)
                self._lock.close()
                self._lock = None
                return 1
        return super()._register(ap_dir)

    def _schema_gate(self, ap_dir: Path) -> int | None:
        if self.once and self._launched:
            return 0
        path = ap_dir / "state.json"
        if path.exists():
            try:
                state, _ = state_mod.load(path)
                schema.validate(state)
            except (state_mod.StateError, schema.SchemaError) as error:
                print(f"autocodex: state refused: {error}", file=self.err)
                return 1
            if loop.pause_detail(state):
                print(f"autocodex: paused: {loop.pause_detail(state)}", file=self.err)
                return 1
            if state.get("phase") == "done" and state.get("next_phase") == "":
                print("autocodex: batch already drained", file=self.out)
                return 0
        return super()._schema_gate(ap_dir)

    def _launch(self, plan: Any, ap_dir: Path) -> None:
        self._before = read_bytes(ap_dir / "state.json")
        self._before_state = json.loads(self._before) if self._before else {}
        phase = self._before_state.get("next_phase", "")
        self._actual_model = driver.codex_model(plan.model, self.env)
        effort = driver.codex_effort(phase, self._actual_model, self.env)
        prompt = driver.host_prompt(self.root, self.cwd, phase, self._scope)
        stem = ap_dir / "autocodex-sessions" / uuid.uuid4().hex
        stem.parent.mkdir(parents=True, exist_ok=True)
        stem.with_suffix(".prompt.md").write_text(prompt)
        self._started = time.time()
        self._launched += 1
        print(
            f"autocodex: {self._actual_model}/{effort}; fresh {phase or 'build'} session",
            flush=True,
        )
        self._result = driver.run_process(
            driver.codex_argv(
                self.env.get("AUTOCODEX_BIN", "codex"), self._actual_model, effort, self.cwd
            ),
            prompt,
            self.cwd,
            self.env,
            stem,
            plan.cap_secs,
            provider="codex",
        )
        (ap_dir / "last-session.log").write_bytes(self._result.log.read_bytes())

    def _observed_state(self, ap_dir: Path) -> tuple[bytes | None, dict, str]:
        current = read_bytes(ap_dir / "state.json")
        state = routing._load_json(ap_dir / "state.json") or {}
        try:
            if current is not None and not isinstance(json.loads(current), dict):
                raise ValueError("state root must be an object")
            schema.validate(state)
        except (ValueError, schema.SchemaError) as error:
            return current, {}, str(error)
        return current, state, ""

    def _decide(self, ap_dir: Path, ts_start: float) -> dict:
        current, state, state_error = self._observed_state(ap_dir)
        changed = current is not None and current != self._before
        decision = {
            "signal": "",
            "detail": "",
            "next": state.get("next_phase", ""),
            "phase_end": state.get("next_phase", ""),
            "prd": state.get("prd", ""),
            "batch": (state.get("batch") or {}).get("id", ""),
            "limit_wait": None,
            "state_touched": changed,
        }
        if (ap_dir / "state-write-failed").exists():
            decision.update(signal="state_write_failed", detail="state-write-failed marker present")
            return decision
        if state_error:
            decision.update(signal="state_write_failed", detail=state_error)
            return decision
        if loop.pause_detail(state):
            decision.update(signal="paused", detail=loop.pause_detail(state))
            return decision
        if (
            changed
            and (not self._result or not self._result.ok)
            and (decision["next"] != (self._before_state.get("next_phase") or "build"))
        ):
            decision.update(
                signal="paused",
                detail="state changed during a failed session; inspect its raw result",
            )
            return decision
        if not self._result or not self._result.ok or not changed:
            return self._failed(decision, ap_dir)
        if self._before_state.get("next_phase", "build") in ("", "build") and (
            decision["next"] == "done" or (not decision["next"] and state.get("prd"))
        ):
            decision.update(signal="paused", detail="build skipped the fresh review handoff")
            return decision
        if self._before_state.get("next_phase") == "review":
            gap = review_gap(state, self.root, self.cwd, self._before_state.get("cycle", 1))
            if gap:
                decision.update(signal="paused", detail=f"review boundary refused: {gap}")
                return decision
        self._died_retries = 0
        self._limit_started = None
        decision["signal"] = "continue" if decision["next"] else "done"
        return decision

    def _failed(self, decision: dict, ap_dir: Path) -> dict:
        reason = loop.pause.stand_down_reason(ap_dir, self._started)
        if reason is not None:
            decision.update(signal="paused", detail=reason, stood_down=reason)
            return decision
        self._died_retries += 1
        retry = self._died_retries <= self._int("_AUTOPILOT_DIED_RETRIES_MAX", 1)
        error = self._result.events.error if self._result else "no session result"
        if re.search(r"usage.?limit|rate.?limit|quota", error, re.IGNORECASE):
            self._limit_started = self._limit_started or time.monotonic()
            remaining = self._int("_AUTOPILOT_LIMIT_WAIT_MAX", 21600) - (
                time.monotonic() - self._limit_started
            )
            if remaining > 0:
                decision.update(
                    signal="continue",
                    detail="Codex usage limit; bounded polling",
                    limit_wait=min(self._int("AUTOCODEX_LIMIT_POLL", 300), max(1, int(remaining))),
                )
                self._died_retries -= 1
                return decision
        detail = error or "session failed or made no committed progress"
        decision.update(signal="continue" if retry else "died", detail=detail)
        if retry:
            self._sleep(self._int("AUTOCODEX_RETRY_DELAY", 15))
        return decision

    def _append_metrics(
        self,
        ap_dir: Path,
        ts_start: float,
        ts_end: float,
        decision: dict,
        phase_launched: str,
        model: str,
    ) -> None:
        row = {
            "ts_start": ts_start,
            "ts_end": ts_end,
            "wall_secs": ts_end - ts_start,
            "provider": "codex",
            "model": self._actual_model,
            "phase_launched": phase_launched,
            "phase_end": decision["phase_end"],
            "signal": decision["signal"],
            "prd": decision["prd"],
            "batch": decision["batch"],
        }
        if self._result:
            row.update(
                raw=str(self._result.log),
                returncode=self._result.returncode,
                capped=self._result.capped,
                usage=self._result.events.usage,
                thread_id=self._result.events.thread_id,
            )
        try:
            with (ap_dir / "autocodex-metrics.jsonl").open("a") as file:
                file.write(json.dumps(row) + "\n")
        except OSError as error:
            print(f"autocodex: metrics write failed: {error}", file=self.err)

    def _act_done(self, decision: dict, ap_dir: Path) -> int:
        # Same batch reset as autoclaude; keep every session's raw evidence.
        reports = ap_dir / "reports"
        reports.mkdir(exist_ok=True)
        (ap_dir / "state.json").replace(reports / f"autocodex-{uuid.uuid4().hex}-state-final.json")
        print("autocodex: backlog drained", file=self.out)
        return 0

    def _act_paused(self, decision: dict, state_path: Path) -> int:
        if not loop.pause_detail(routing._load_json(state_path) or {}):
            state_mod.transaction(
                state_path,
                lambda state: {
                    **state,
                    "phase": "paused",
                    "next_phase": "paused",
                    "pause_reason": {
                        "site": "autocodex_boundary",
                        "detail": decision["detail"],
                    },
                },
            )
        print(f"autocodex: paused: {decision['detail']}\nState: {state_path}", file=self.err)
        return 1

    def _teardown(self) -> None:
        super()._teardown()
        if self._lock is not None:
            self._lock.close()
            self._lock = None

    def run(self) -> int:
        try:
            return super().run()
        finally:
            self._teardown()
