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

_SOURCE_ROUTE = routing.route


class _ProviderStream:
    """Relabel inherited lifecycle prose without altering upstream policy."""

    def __init__(self, stream: Any) -> None:
        self._stream = stream

    def write(self, value: str) -> int:
        value = value.replace("autoclaude", "autocodex").replace(
            "claude → /autopilot:run-autopilot",
            "codex → read ~/.config/autocodex/host.md for interactive recovery",
        )
        return self._stream.write(value)

    def flush(self) -> None:
        self._stream.flush()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)


def codex_route(phase: str, autopilot_dir: Path, env: dict | None = None) -> Any:
    """Translate inherited logical tiers before the loop renders or records them."""
    effective_env = dict(os.environ) if env is None else env
    source = _SOURCE_ROUTE(phase, autopilot_dir, env=effective_env)
    model = driver.coordinator_model(source.model, effective_env)
    return routing.Route(
        model=model,
        effort=driver.codex_effort(phase, model, effective_env),
        cap_secs=source.cap_secs,
    )


# The inherited loop prints and records Route before _launch(). Adapt it at that
# boundary so user-visible main-session labels always name the actual provider.
routing.route = codex_route


def read_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def convergence_gap(state: dict, snapshot: dict, cwd: Path, review: Path) -> str | None:
    """Allow only the source's completed, append-only post-convergence sweep.

    Original review receipts stay bound to the reviewed snapshot. The companion
    audit records sweep provenance; it is not another completion review. Task
    completion remains the source work pipeline's verification/review boundary.
    """
    current = driver.implementation_snapshot(state)
    if current == snapshot:
        return None
    refused = "implementation changed since the converged review"
    reviewed_ids = {task["id"] for task in snapshot["tasks"]}
    current_ids = [task["id"] for task in current["tasks"]]
    if len(reviewed_ids) != len(snapshot["tasks"]) or len(set(current_ids)) != len(
        current_ids
    ):
        return refused + ": duplicate task IDs"
    original = {
        **current,
        "tasks": [t for t in current["tasks"] if t["id"] in reviewed_ids],
    }
    if original != snapshot:
        return refused + ": reviewed tasks or cycle/work identity changed"
    added = [task for task in state["tasks"] if task["id"] not in reviewed_ids]
    if not added:
        return refused
    batches = state.get("applied_review_batches") or []
    if any(
        f"{review.resolve()}::{batch}" not in batches
        for batch in ("decision-gate", "tail-sweep")
    ):
        return refused + ": missing current review tail-sweep batch"
    if any(task.get("status") != "completed" for task in state["tasks"]):
        return refused + ": incomplete tasks"
    for task in added:
        attempts = task.get("attempts") or []
        if (
            not task.get("name", "").startswith(f"[D{state['cycle']}] Tail sweep: ")
            or not attempts
            or attempts[-1].get("outcome") != "completed"
            or any(
                attempt.get("review_cycle") != state["cycle"] for attempt in attempts
            )
        ):
            return refused + ": added task is not a completed current-cycle tail sweep"
    audit_path = (
        cwd
        / "docs/dev/project-management/autopilot/reports"
        / f"{Path(state['prd']).stem}-tail-sweep-models.json"
    )
    try:
        driver.audited_review_providers(state, cwd, audit_path=audit_path)
    except (ValueError, OSError, KeyError, IndexError, TypeError) as error:
        return f"tail-sweep model audit: {error}"
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
    gap = gate.check(text, ["alice", "blake", "bob"], require_codex_guard=False)
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
    try:
        audit_path = (
            cwd
            / "docs/dev/project-management/autopilot/reports"
            / f"{Path(state['prd']).stem}-implementation-models.json"
        )
        snapshot = json.loads(audit_path.read_text())["snapshot"]
        if (
            snapshot.get("cycle") != cycle
            or snapshot.get("prd") != state.get("prd")
            or snapshot.get("work_start_sha") != state.get("work_start_sha")
        ):
            return "review audit belongs to another PRD, cycle or work range"
        providers = driver.audited_review_providers(snapshot, cwd)
        if state.get("phase") == "done":
            gap = convergence_gap(state, snapshot, cwd, path)
            if gap:
                return gap
    except (ValueError, OSError, KeyError, IndexError, TypeError) as error:
        return f"review provider routing: {error}"
    if not re.search(r"^provider_review_guard: satisfied$", text, re.MULTILINE):
        return "missing model-provider review guard"
    for provider in providers:
        for lens in ("alice", "blake", "bob"):
            gap = bob_gap(
                text,
                cwd,
                cycle,
                state.get("prd", ""),
                lens,
                provider,
                driver.implementation_fingerprint(snapshot),
            )
            if gap:
                return gap
    verdicts = state.get("doubts_rubric_verdicts") or []
    ids = {item.get("rule_id") for item in verdicts if isinstance(item, dict)}
    if not {f"D{n}" for n in range(1, 6)}.issubset(ids):
        return "state lacks the complete Bob doubt rubric"
    return None


def stall_snapshot_path(state: dict, cwd: Path) -> Path:
    """Locate the one immutable receipt for this PRD's capped review cycle."""
    prd = state["prd"]
    if not isinstance(prd, str) or Path(prd).name != prd or not prd:
        raise ValueError("invalid stall PRD")
    return (cwd / "docs/dev/project-management/autopilot/reports"
            / f"{Path(prd).stem}-cycle-{state['cycle']}-cap-regression-boundary.json")


def _deferred_ledger(ap_dir: Path, batch: str) -> dict:
    if not isinstance(batch, str) or not batch or "/" in batch or ".." in batch:
        raise ValueError("invalid stall batch")
    path = ap_dir / "deferred" / f"{batch}-deferred.json"
    content = json.loads(path.read_text()) if path.exists() else {"batch_id": batch, "items": []}
    if (content.get("batch_id") != batch or not isinstance(content.get("items"), list)
            or not all(isinstance(row, dict) for row in content["items"])):
        raise ValueError("invalid deferred ledger")
    return content


def capture_stall_review(root: Path, cwd: Path) -> Path:
    """Preserve verified review evidence before the source's destructive reset."""
    ap_dir = cwd / "docs/dev/project-management/autopilot"
    state, _ = state_mod.load(ap_dir / "state.json")
    schema.validate(state)
    gap = review_gap(state, root, cwd, state["cycle"])
    if gap:
        raise ValueError(f"review stall snapshot refused: {gap}")
    driver.audited_review_providers(state, cwd)
    if state["cycle"] < state.get("rework_cap", 3):
        raise ValueError("review stall snapshot requires the existing rework cap")
    if not any(row.get("type") == "cap-overflow" for row in state.get("deferred_decisions", [])):
        raise ValueError("record cap-overflow decisions before the stall snapshot")
    path = stall_snapshot_path(state, cwd)
    review = cwd / state["review_cycles"][-1]["review_file"]
    prd = cwd / "docs/dev/project-management/prds/wip" / state["prd"]
    payload = {
        "state": state,
        "review_sha256": hashlib.sha256(review.read_bytes()).hexdigest(),
        "prd_sha256": hashlib.sha256(prd.read_bytes()).hexdigest(),
        "deferred_before": _deferred_ledger(ap_dir, state["batch"]["id"]),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.exists():
            if json.loads(path.read_text()) != payload:
                raise ValueError(f"stall snapshot already exists with different evidence: {path}")
        else:
            state_mod.atomic_write(path, payload)
    return path


def stall_review_gap(state: dict, before: dict, root: Path, cwd: Path) -> str | None:
    """Validate only a real cap_regression stall, without bypassing review gates."""
    from cli import custody, records, triage

    try:
        receipt = json.loads(stall_snapshot_path(before, cwd).read_text())
        reviewed = receipt["state"]
        if (driver.implementation_snapshot(reviewed) != driver.implementation_snapshot(before)
                or reviewed.get("batch") != before.get("batch")
                or reviewed.get("rework_cap", 3) != before.get("rework_cap", 3)):
            return "stall snapshot differs from launched PRD, cycle, batch or implementation"
        driver.audited_review_providers(reviewed, cwd)
        gap = review_gap(reviewed, root, cwd, before["cycle"])
        if gap:
            return gap
        review = cwd / reviewed["review_cycles"][-1]["review_file"]
        if hashlib.sha256(review.read_bytes()).hexdigest() != receipt["review_sha256"]:
            return "review changed after stall snapshot"
        if reviewed["cycle"] < reviewed.get("rework_cap", 3):
            return "stall snapshot is below the existing rework cap"
        if not any(row.get("type") == "cap-overflow" for row in reviewed.get("deferred_decisions", [])):
            return "stall snapshot has no cap-overflow decisions"
        ap_dir = cwd / "docs/dev/project-management/autopilot"
        prds = cwd / "docs/dev/project-management/prds"
        held = prds / "hold" / reviewed["prd"]
        if ((prds / "wip" / reviewed["prd"]).exists()
                or hashlib.sha256(held.read_bytes()).hexdigest() != receipt["prd_sha256"]):
            return "stall PRD did not move intact to hold"
        batch_id = reviewed["batch"]["id"]
        ledger = _deferred_ledger(ap_dir, batch_id)
        prior = receipt["deferred_before"]
        prefix = prior["items"]
        if prior.get("batch_id") != batch_id or ledger["items"][:len(prefix)] != prefix:
            return "prior deferred ledger changed"
        added = ledger["items"][len(prefix):]
        if not added:
            return "no new canonical stall record"
        stall = added[0]
        if (stall.get("type") != "stall" or stall.get("site") != "cap_regression"
                or stall.get("prd") != reviewed["prd"] or not stall.get("detail")
                or not isinstance(stall.get("op_id"), str) or not stall["op_id"]
                or any(row.get("op_id") == stall["op_id"] for row in prefix)):
            return "deferred record is not a fresh cap_regression stall"
        expected_rows = custody.migration_records(reviewed, stall["op_id"], reviewed["prd"])
        if added != [stall, *expected_rows]:
            return "canonical stall deferral migration differs"
        expected = records.reset_prd_fields(reviewed)
        expected["batch"] = {**expected["batch"], "parks_consecutive": 0}
        expected.pop("stall_op", None)
        # The source mint-stubs call may append batch bookkeeping after reset.
        old_stubs = reviewed["batch"].get("minted_stubs", [])
        new_stubs = state.get("batch", {}).get("minted_stubs", old_stubs)
        if new_stubs[:len(old_stubs)] != old_stubs or len(set(new_stubs)) != len(new_stubs):
            return "minted stub history changed"
        for name in new_stubs[len(old_stubs):]:
            if not isinstance(name, str) or Path(name).name != name:
                return "invalid minted stub path"
            stub = (prds / "hold" / name).read_text()
            if not any(
                triage.qualifies(row) and triage.finding_text(row) is not None
                and stub == triage.render_stub(row, batch_id, triage.ledger_key(triage.finding_text(row)))
                for row in ledger["items"]
            ):
                return "minted stub does not match canonical deferred evidence"
        if "minted_stubs" in state.get("batch", {}):
            expected["batch"]["minted_stubs"] = new_stubs
        candidate = dict(state)
        # The canonical contract card is handoff prose, outside review provenance.
        if "contract_card" in candidate:
            if not isinstance(candidate["contract_card"], str):
                return "invalid post-stall contract card"
            candidate.pop("contract_card")
        if candidate != expected:
            return "post-stall state differs from the canonical per-PRD reset"
    except (ValueError, OSError, KeyError, IndexError, TypeError, AttributeError) as error:
        return f"invalid cap_regression stall evidence: {error}"
    return None


def bob_gap(
    text: str,
    cwd: Path,
    cycle: int,
    prd: str,
    lens: str = "bob",
    provider: str | None = None,
    fingerprint: str | None = None,
) -> str | None:
    key = f"autocodex_{lens}_{provider}_receipt" if provider else "autocodex_bob_receipt"
    match = re.search(rf"^{key}: (.+)$", text, re.MULTILINE)
    if not match:
        return f"missing {key}"
    try:
        receipt = json.loads((cwd / match[1].strip()).read_text())
        raw = Path(receipt["output"]).read_bytes()
        if fingerprint is not None and receipt.get("implementation_fingerprint") != fingerprint:
            return "review receipt belongs to a different implementation snapshot"
        if (
            receipt["provider"]
            not in ({"codex"} if provider == "openai" else {"claude", "kiro", "copilot"})
            or (
                provider is not None
                and (
                    receipt.get("lens") != lens
                    or driver.model_provider_for_review(receipt["model"]) != provider
                )
            )
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
        events = driver.Events(receipt["provider"])
        for line in captured.splitlines():
            events.accept(line)
        if receipt["provider"] == "kiro":
            stderr = Path(receipt["raw"]).with_suffix(".stderr").read_bytes()
            if (receipt.get("stderr_sha256") is not None
                    and hashlib.sha256(stderr).hexdigest() != receipt["stderr_sha256"]):
                return "review stderr evidence changed after dispatch"
            driver.check_permission_stderr(events, stderr)
        if receipt["provider"] in {"kiro", "copilot"} and (
            events.models != {receipt["model"]}
            or events.efforts != {"xhigh"}
            or receipt.get("effort") != "xhigh"
        ):
            return "review model/effort evidence does not match receipt"
        if events.permission_denied or not events.success or events.text.encode() != raw:
            return "review output does not match a successful provider result"
        for rule in driver.review_rules(lens):
            if not re.search(rf"^{rule}: (?:pass|fail)\b", raw.decode(), re.MULTILINE):
                return f"{lens} missing {rule}"
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
        self.out = _ProviderStream(self.out)
        self.err = _ProviderStream(self.err)
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
        path = self.cwd / "docs/dev/project-management/autopilot"
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
            state = routing._load_json(ap_dir / "state.json") or {}
            next_phase = state.get("next_phase") or "none"
            print(
                "\nautocodex: stopping because --once is active; workflow state "
                "advanced, but no new session will start. "
                f"Next phase queued: {next_phase}. Run plain 'autocodex' to continue.",
                file=self.out,
            )
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
                self._print_pause_help(state, path)
                return 1
            if state.get("phase") == "done" and state.get("next_phase") == "":
                print("autocodex: batch already drained", file=self.out)
                return 0
        return super()._schema_gate(ap_dir)

    def _print_pause_help(self, state: dict, state_path: Path) -> None:
        detail = loop.pause_detail(state) or "operator attention required"
        print(f"autocodex: paused: {detail}", file=self.err)

        prd = state.get("prd")
        prd_name = prd if isinstance(prd, str) else ""
        wip = self.cwd / "docs/dev/project-management/prds/wip" / prd_name
        done = self.cwd / "docs/dev/project-management/prds/done" / prd_name
        if prd_name and done.is_file() and not wip.exists():
            preserved = (
                f"docs/dev/project-management/autopilot-{Path(prd_name).stem}-paused-preserved"
            )
            print(
                f"\nThis state belongs to completed PRD {prd_name}; do not resume its findings.\n"
                "Preserve and detach it before starting the current WIP PRD:\n\n"
                f"  mv docs/dev/project-management/autopilot {preserved}\n"
                "  autocodex --once --scope <handoff.md>\n\n"
                f"State: {state_path}",
                file=self.err,
            )
            return

        cap = state.get("cap_pause_reason")
        findings = cap.get("unresolved_findings") if isinstance(cap, dict) else None
        for finding in findings or []:
            if not isinstance(finding, dict):
                continue
            severity = finding.get("severity") or "?"
            consensus = finding.get("consensus") or "?"
            issue = str(finding.get("issue") or "")
            print(f"  - [{severity}; {consensus}] {issue}", file=self.err)

        if isinstance(cap, dict):
            print(
                "\nThis is a deliberate review gate. Resolve it interactively:\n\n"
                "  1. codex\n"
                "  2. Ask Codex to read ~/.config/autocodex/host.md and follow\n"
                "     its interactive recovery instructions.\n"
                "  3. Choose Resume and optionally raise the rework cap.\n"
                "  4. Exit Codex, then run autocodex again.\n\n"
                "Do not edit state.json directly.",
                file=self.err,
            )
        else:
            print(
                "\nInspect the recorded reason, then take over interactively:\n\n"
                "  autocodex status\n"
                "  codex\n\n"
                "Ask Codex to read ~/.config/autocodex/host.md and follow\n"
                "its interactive recovery instructions.\n\n"
                "After resolving the pause, run autocodex again.",
                file=self.err,
            )
        print(f"\nState: {state_path}", file=self.err)

    def _launch(self, plan: Any, ap_dir: Path, phase: str) -> float:
        self._before = read_bytes(ap_dir / "state.json")
        self._before_state = json.loads(self._before) if self._before else {}
        phase = self._before_state.get("next_phase", "")
        self._actual_model = driver.coordinator_model(plan.model, self.env)
        effort = driver.codex_effort(phase, self._actual_model, self.env)
        prompt = driver.host_prompt(self.root, self.cwd, phase, self._scope, env=self.env)
        stem = ap_dir / "autocodex-sessions" / uuid.uuid4().hex
        stem.parent.mkdir(parents=True, exist_ok=True)
        stem.with_suffix(".prompt.md").write_text(prompt)
        self._started = time.time()
        ts_start = self._clock()
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
            self._int("AUTOCODEX_STALL_TIMEOUT", 1800),
            provider="codex",
        )
        (ap_dir / "last-session.log").write_bytes(self._result.log.read_bytes())
        return ts_start

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
            decision["next"] == "done"
            or (not decision["next"] and state.get("prd") and not self._parked(state["prd"]))
        ):
            decision.update(signal="paused", detail="build skipped the fresh review handoff")
            return decision
        if self._before_state.get("next_phase") == "review":
            if state.get("phase") == "build" and state.get("next_phase") == "build":
                gap = stall_review_gap(state, self._before_state, self.root, self.cwd)
            else:
                gap = review_gap(state, self.root, self.cwd, self._before_state.get("cycle", 1))
            if gap:
                decision.update(signal="paused", detail=f"review boundary refused: {gap}")
                return decision
        self._died_retries = 0
        self._limit_started = None
        decision["signal"] = "continue" if decision["next"] else "done"
        return decision

    def _parked(self, prd: Any) -> bool:
        """A build session drains legitimately once its PRD sits in hold/ (the
        source's oversized_task / loop-mode stall parks it there and the
        ("build", "drained") transition empties next_phase): nothing is in
        flight to review. Anywhere else an empty next_phase from build means
        the fresh review handoff was skipped."""
        return (
            isinstance(prd, str)
            and bool(prd)
            and (self.cwd / "docs/dev/project-management/prds/hold" / prd).is_file()
        )

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
        effort: str,
        launched_prd: str = "",
    ) -> None:
        row = {
            "ts_start": ts_start,
            "ts_end": ts_end,
            "wall_secs": ts_end - ts_start,
            "provider": "codex",
            "model": self._actual_model,
            "effort": effort,
            "phase_launched": phase_launched,
            "phase_end": decision["phase_end"],
            "signal": decision["signal"],
            "prd": launched_prd or decision["prd"],
            "prd_end": decision["prd"],
            "batch": decision["batch"],
        }
        if self._result:
            row.update(
                raw=str(self._result.log),
                returncode=self._result.returncode,
                stalled=self._result.stalled,
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
        self._print_pause_help(routing._load_json(state_path) or {}, state_path)
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
