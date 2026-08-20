"""cli/loop.py - the autopilot loop driver (PRD 00106).

Replaces the bash `autoclaude()` loop body: read state through the
00051 core, decide over the PRD-00014 decision table, spawn the routed
phase runner, act on the branch. One session = one `claude -p` turn =
one process that exits at turn end; the decision is made from
state.json after exit, never from the session's words.

Signals, in decision order (one per session):
    state_write_failed  the 00051 marker survives past state.json and
                        wins over an otherwise-continue state
    paused              a human is needed (pause_reason / review cap)
    continue            next phase queued (also: replan, limit wait,
                        network restored, died-retry)
    done                backlog drained (next_phase empty)
    died                no progress and no scheduling explanation
    park                died past the retry budget, or the
                        no-progress fingerprint bound fired

state_touched guards the no-progress branch: a healthy session ALWAYS
writes state at its hand-off, so an untouched state.json means this
session made no progress (limit-hit at start, crash, cap-kill) -
without the mtime check a mid-batch limit hit would relaunch into the
same banner in a tight loop.

Everything the wrapper accreted rides along: memory circuit-breaker
(2026-06-25 RAM lockout), loop registry + duplicate guard, plugin-pin
preflight (PRD 00086 R3), usage-limit wait (bounded), network-outage
poll (bounded, retry-capped), died-retry + park marker with its
unconsumed-marker bounds (PRD 00066), progress-fingerprint bound
(2026-07-14), per-session metrics with the GC-exempt ledger mirror,
and the drained-path purge + agoge QA run (PRD 00102).
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import signal as signal_mod
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from cli import notify_out, pause, routing, runner, usage_limit
from cli import state as state_mod
from cli.routing import _load_json
from cli.watchdog import Watchdog

_SKILL_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _SKILL_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
import _walk_up

DEFAULT_LOOPS_DIR = Path.home() / ".claude" / "autopilot-loops"
PURGE_SCRIPT = (
    Path.home()
    / ".claude"
    / "skills"
    / "purge-devlocal"
    / "scripts"
    / "purge_devlocal.py"
)

_CONNECTION_FAIL = re.compile(
    r"unable to connect|connection ?(refused|reset|error)|econn|etimedout"
    r"|enotfound|eai_again|network is unreachable|fetch failed",
    re.IGNORECASE,
)

_API_PROBE_URL = "https://api.anthropic.com"


class _Terminated(Exception):
    def __init__(self, code: int) -> None:
        self.code = code


# ── small pure ports ─────────────────────────────────────────────────────────


def died_next(prd: str, retries: int, retries_max: int) -> str:
    """Branch 5's final else as a pure decision: retry|park|die. Empty
    prd (bootstrap - nothing selected yet) always halts loud; otherwise
    retry until the budget is exhausted, then park."""
    if not prd:
        return "die"
    if retries < retries_max:
        return "retry"
    return "park"


def _tostring(value) -> str:
    """jq `tostring`: strings stay bare, everything else is its JSON."""
    if isinstance(value, str):
        return value
    return json.dumps(value, separators=(",", ":"))


def pause_detail(state: dict) -> str:
    """The wrapper's one-line pause summary. cap_pause_reason is
    summarized rather than dumped - raw findings JSON buried the resume
    runbook at the operator (2026-07-19); the full findings stay in
    state.json."""
    reason = state.get("pause_reason")
    if state.get("phase") != "paused" and reason in (None, False, ""):
        return ""
    value = None
    if isinstance(reason, dict):
        value = reason.get("detail")
        if value is None:
            value = reason
    elif reason is not None:
        value = reason
    if value is None:
        cap = state.get("cap_pause_reason")
        if isinstance(cap, dict) and "cycle" in cap:
            count = len(cap.get("unresolved_findings") or [])
            value = f"review cap hit: cycle {cap.get('cycle')}/{cap.get('cap')} · {count} unresolved findings"
        else:
            value = cap
    if value is None:
        value = "paused"
    return _tostring(value)


def _jq_or(state: dict, key: str, default):
    """jq's `//`: the default replaces null and false, not just absence.
    Identity checks, not `in (None, False)` - Python equates 0 == False
    and jq's // must NOT replace a legitimate 0."""
    value = state.get(key)
    return default if value is None or value is False else value


def fingerprint(state: dict) -> str:
    """The fields that must move for the batch to progress."""
    rotations = _jq_or(state, "cap_rotations", [])
    parts = [
        _tostring(state.get("prd")),
        _tostring(state.get("next_phase")),
        _tostring(_jq_or(state, "tasks_completed", -1)),
        _tostring(_jq_or(state, "review_cycles", -1)),
        _tostring(_jq_or(state, "cycle", -1)),
        _tostring(len(rotations) if isinstance(rotations, (list, dict)) else 0),
        _tostring(_jq_or(state, "replan_count", -1)),
    ]
    return "|".join(parts)


def plugin_drift(state: dict, installed: dict) -> str | None:
    """PRD 00086 R3: a plugin pinned at batch selection that differs
    from what is installed now. None when every pin matches or no pin
    was recorded (an unpinned batch is never blocked)."""
    pins = (state.get("batch") or {}).get("plugin_versions")
    if not isinstance(pins, dict):
        return None
    for name, pin in pins.items():
        current = "MISSING"
        entries = (installed.get("plugins") or {}).get(name)
        if isinstance(entries, list) and entries and isinstance(entries[0], dict):
            version = entries[0].get("version")
            if version is not None:
                current = _tostring(version)
        if _tostring(pin) != current:
            return f"{name} pinned={_tostring(pin)} now={current}"
    return None


def last_result_field(log_path: Path, field: str, error_only: bool = False):
    """The LAST result event's `field` from the session log, or None.
    Sessions re-invoked by background-task notifications emit one result
    event PER re-invoke - the final one wins (2026-07-13)."""
    value = None
    try:
        with open(log_path, "rb") as fh:
            for raw in fh:
                try:
                    entry = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(entry, dict) or entry.get("type") != "result":
                    continue
                if error_only and entry.get("is_error") is not True:
                    continue
                got = entry.get(field)
                if got is not None:
                    value = got
    except OSError:
        return None
    return value


def _mtime(path: Path) -> int | None:
    try:
        return int(path.stat().st_mtime)
    except OSError:
        return None


def _utcnow_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── registry (loop singleton per repo) ───────────────────────────────────────


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True  # EPERM etc.: it exists, we just can't signal it
    return True


def _child_pids(pid: int) -> list[str]:
    try:
        out = subprocess.run(
            ["pgrep", "-P", str(pid)],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [token for token in out.split() if token.isdigit()]


def _pid_tagged(pid: int, tag_pid: int) -> bool:
    """The recycled-pid guard: a live pid counts as a loop only when its
    ps env - or a direct child's - carries its own _AUTOPILOT_LOOP=<pid>
    tag. Children count because ps reports the EXEC-time environment: the
    tracon front-end forks the loop shell (whose pid the registry stores,
    since killpg needs the group leader) and exports the tag only after
    that fork, so the tag shows up on the exec'd driver beneath it and
    never on the shell itself. Checking the shell alone swept live loops
    out of the registry, blinding tracon to them."""
    pids = [str(pid), *_child_pids(pid)]
    try:
        out = subprocess.run(
            ["ps", "ewww", "-p", ",".join(pids), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return re.search(rf"_AUTOPILOT_LOOP={tag_pid}( |$)", out, re.MULTILINE) is not None


def prune_registry(loops_dir: Path, own_pid: int) -> None:
    """Sweep stale entries: dead pid, alive-but-untagged (recycled), or
    malformed - none can denote a live loop. Never touches the CURRENT
    process's own entry. An unreadable entry (OSError, e.g. permission
    denied) means "couldn't check this", not "this is garbage" - it is
    left alone rather than swept."""
    try:
        entries = list(loops_dir.glob("*.json"))
    except OSError:
        return
    for path in entries:
        try:
            raw = path.read_bytes()
        except OSError:
            continue  # unreadable (permission/ownership) - leave alone, not corrupt
        try:
            data = json.loads(raw.decode("utf-8"))
        except ValueError:
            data = None  # unparseable/undecodable - garbage, not unreadable
        pid = data.get("pid") if isinstance(data, dict) else None
        if pid == own_pid:
            continue
        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or not _pid_alive(pid)
            or not _pid_tagged(pid, pid)
        ):
            try:
                path.unlink()
            except OSError:
                pass


def live_wrapper_pid(root: Path, loops_dir: Path) -> int | None:
    """The incumbent loop's pid for this repo root, else None. Same
    contract as tracon.discovery.live_wrapper_pid, applied to an
    explicit loops dir. A pid that is alive but never carries its own
    _AUTOPILOT_LOOP tag (per _pid_tagged) is a recycled/borrowed pid,
    not an incumbent. An unreadable entry (OSError) means "couldn't
    check this" - it is skipped (unresolvable until readable again),
    never deleted."""
    resolved = root.resolve()
    try:
        entries = list(loops_dir.glob("*.json"))
    except OSError:
        return None
    for path in entries:
        data = _load_json(path)
        if not isinstance(data, dict):
            continue
        pid, reg_root = data.get("pid"), data.get("root")
        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or not isinstance(reg_root, str)
        ):
            continue
        try:
            if (
                Path(reg_root).resolve() == resolved
                and _pid_alive(pid)
                and _pid_tagged(pid, pid)
            ):
                return pid
        except OSError:
            continue
    return None


# ── drained-path helpers ─────────────────────────────────────────────────────


def run_purge(repo: Path) -> None:
    """`purge_devlocal.py --repo <repo> --apply || true`."""
    try:
        subprocess.run(
            [sys.executable, str(PURGE_SCRIPT), "--repo", str(repo), "--apply"],
        )
    except (OSError, subprocess.SubprocessError):
        pass


def run_agoge(
    ap_dir: Path,
    batch: str,
    drained,
    env: dict,
    out,
    claude_bin: str = "claude",
) -> None:
    """One product-QA run over a batch that actually completed work
    (PRD 00102). Once per batch. A batch that drained nothing gets a
    skip line and no run. Failure is recorded and swallowed, and a
    wall-clock cap bounds a hung run: a QA pass must never turn a
    successful drain into a failed or unfinished one.

    --authorized arms the runtime-security lane (PRD 00117): pointing
    this loop at a repo IS the operator's authorization - it already
    grants autonomous edit-and-commit rights, strictly more than
    probing. _AUTOPILOT_AGOGE_AUTHORIZED=0 is a brake on that
    default-on assertion, not an alternative way to make it (R5)."""
    if drained in (None, "", "null", 0, "0"):
        print("agoge: skipped — the batch drained no PRDs.", file=out)
        return
    stamp = batch or _dt.datetime.now().strftime("%Y%m%d%H%M")
    log_path = ap_dir / "reports" / f"{stamp}-agoge.log"
    print(f"agoge: product QA over the drained batch (log: {log_path})…", file=out)
    prompt = f"/run-agoge {Path.cwd()}"
    if env.get("_AUTOPILOT_AGOGE_AUTHORIZED") != "0":
        prompt += " --authorized autoclaude-drain"
    cap = routing._env_int(env, "_AUTOPILOT_AGOGE_CAP", 3600)
    rc = 0
    try:
        with open(log_path, "wb") as log:
            proc = subprocess.Popen(
                [claude_bin, "-p", "--permission-mode", "auto", prompt],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                env={**env, **runner.LAUNCH_ENV},
            )
            dog = Watchdog(proc, cap_secs=cap, grace_secs=20).start()
            rc = proc.wait()
            dog.cancel()
    except (OSError, subprocess.SubprocessError):
        rc = 1
    if rc == 0:
        print(
            "agoge: packets written to dev/local/audit-results/; walkthrough pending.",
            file=out,
        )
    else:
        print(
            f"agoge: run failed (rc {rc}). The drain is unaffected; see {log_path}",
            file=sys.stderr,
        )


# ── the driver ───────────────────────────────────────────────────────────────


def _read_memory_pressure() -> int | None:
    """macOS memorystatus level: 1 normal, 2 warning, 4 critical.
    None where the sysctl does not exist."""
    try:
        out = subprocess.run(
            ["sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        return int(out) if out else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _probe_api() -> bool:
    try:
        urllib.request.urlopen(_API_PROBE_URL, timeout=5)
        return True
    except urllib.error.HTTPError:
        return True  # an HTTP status IS connectivity (curl -s exits 0 too)
    except (OSError, ValueError):
        return False


class Loop:
    """One `autopilot loop` invocation: drives sessions until drain,
    pause, halt, or an operator signal. Collaborators are injectable so
    the decision table and every act branch are testable without a real
    claude, notifier, network, or clock."""

    def __init__(
        self,
        cwd: Path | None = None,
        env: dict | None = None,
        *,
        spawn_fn=runner.spawn,
        notify_fn=notify_out.notify,
        sleep_fn=time.sleep,
        pressure_fn=_read_memory_pressure,
        probe_fn=_probe_api,
        detect_limit_fn=usage_limit.detect_from_log,
        clock=time.time,
        out=None,
        err=None,
        runner_bin: str = "claude",
    ) -> None:
        self.cwd = Path.cwd() if cwd is None else cwd
        self.env = dict(os.environ) if env is None else env
        self._spawn = spawn_fn
        self._notify = notify_fn
        self._sleep = sleep_fn
        self._pressure = pressure_fn
        self._probe = probe_fn
        self._detect_limit = detect_limit_fn
        self._clock = clock
        self.out = out if out is not None else sys.stdout
        self.err = err if err is not None else sys.stderr
        self.runner_bin = runner_bin

        raw_tag = self.env.get("_AUTOPILOT_LOOP", "")
        self.loop_pid = int(raw_tag) if raw_tag.isdigit() else os.getpid()
        # Children must inherit the tag (orphan cleanup and the recycled-pid
        # guard both grep for it), exactly as the bash export did.
        self.env["_AUTOPILOT_LOOP"] = str(self.loop_pid)

        self._reg: Path | None = None
        self._net_retries = 0
        self._died_retries = 0
        self._park_relaunches = 0
        self._fp_prev = ""
        self._fp_repeats = 0
        self._proc_slot: list = [None]
        self._warned_schema = False

    # ── env knobs ──
    def _int(self, key: str, default: int) -> int:
        return routing._env_int(self.env, key, default)

    # ── plumbing ──
    def _repo_name(self) -> str:
        return self.cwd.name

    def _teardown(self) -> None:
        proc = self._proc_slot[0]
        if proc is not None and proc.poll() is None:
            proc.terminate()
        self._cleanup_orphans()
        if self._reg is not None:
            try:
                self._reg.unlink()
            except OSError:
                pass

    def _cleanup_orphans(self) -> None:
        """HUP orphaned (PPID=1) processes tagged with our marker, so
        shells propagate the signal to their children. One ps over all
        candidates (the bash loop ran ps per pid; launchd parents
        hundreds of user processes, so per-pid probing is seconds of
        work per session)."""
        try:
            out = subprocess.run(
                ["pgrep", "-u", os.environ.get("USER", ""), "-P", "1"],
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            return
        pids = [token for token in out.split() if token.isdigit()]
        if not pids:
            return
        try:
            ps_out = subprocess.run(
                ["ps", "ewww", "-p", ",".join(pids), "-o", "pid=,command="],
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            return
        tag = re.compile(rf"_AUTOPILOT_LOOP={self.loop_pid}( |$)")
        for line in ps_out.splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) == 2 and parts[0].isdigit() and tag.search(parts[1]):
                try:
                    os.kill(int(parts[0]), signal_mod.SIGHUP)
                except OSError:
                    pass

    def _resolve_ap_dir(self) -> Path:
        ap_dir = _walk_up.find_autopilot_dir(self.cwd)
        if ap_dir is None:
            # walk-up miss = no dir exists yet (normal on a fresh repo), not a failure
            print(
                f"autoclaude: no existing autopilot dir found (fresh start); creating {self.cwd}/dev/local/autopilot",
                file=self.err,
            )
            ap_dir = self.cwd / "dev" / "local" / "autopilot"
        try:
            ap_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        return ap_dir

    # ── preflights ──
    def _memory_gate(self) -> int | None:
        """None to proceed; an exit code to stop the loop."""
        level = self._pressure()
        if level is None or level < 2:
            return None
        print(
            f"\nautoclaude: memory pressure (level {level}); waiting for it to clear before launching next session.",
            file=self.err,
        )
        self._notify(
            f"autopilot ⏳ {self._repo_name()}",
            f"Waiting: memory pressure (level {level}).",
        )
        max_wait = self._int("_AUTOPILOT_MEM_WAIT_MAX", 3600)
        poll = self._int("_AUTOPILOT_MEM_POLL_SECS", 60)
        deadline = self._clock() + max_wait
        while self._clock() < deadline:
            self._sleep(poll)
            level = self._pressure()
            if level is None or level < 2:
                break
        if level is not None and level >= 2:
            print(
                f"\nautoclaude: memory pressure still elevated (level {level}) "
                f"after {max_wait}s; stopping loop. Free RAM, then re-run.",
                file=self.err,
            )
            self._notify(
                f"autopilot ⚠️ {self._repo_name()}",
                f"Stopped: memory pressure (level {level}) did not clear "
                f"within {max_wait}s. Free RAM, then re-run autoclaude.",
            )
            return 1
        print(
            f"\nautoclaude: memory pressure cleared (level {level}); resuming.",
            file=self.err,
        )
        return None

    def _register(self, ap_dir: Path) -> int | None:
        """Registry + duplicate-loop guard, once per loop. None to
        proceed; an exit code to refuse."""
        if self._reg is not None:
            return None
        loops_dir = Path(self.env.get("_AUTOPILOT_LOOPS_DIR") or DEFAULT_LOOPS_DIR)
        self.env["_AUTOPILOT_LOOPS_DIR"] = str(loops_dir)
        try:
            loops_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        prune_registry(loops_dir, self.loop_pid)
        root_str = str(ap_dir)
        suffix = "/dev/local/autopilot"
        root = Path(root_str[: -len(suffix)]) if root_str.endswith(suffix) else ap_dir
        incumbent = live_wrapper_pid(root, loops_dir)
        # An incumbent carrying OUR OWN pid is this shell's earlier loop
        # that died without teardown (SIGKILL of the python driver leaves
        # the entry naming the still-alive shell). The bash loop could
        # never reach this state - killing the loop killed the shell - so
        # prune's own-pid skip was enough there; here the stale self-entry
        # must be overwritten, never treated as a live duplicate.
        if incumbent is not None and incumbent != self.loop_pid:
            print(
                f"autoclaude: a loop is already running for {root} "
                f"(pid {incumbent}). Refusing to start a second loop on the "
                "same repo.",
                file=self.err,
            )
            return 1
        reg = loops_dir / f"{self.loop_pid}.json"
        entry = {
            "pid": self.loop_pid,
            "root": str(root),
            "ap_dir": str(ap_dir),
            "started_at": _utcnow_iso(),
        }
        tmp = loops_dir / f"{reg.name}.tmp.{self.loop_pid}"
        try:
            tmp.write_text(json.dumps(entry))
            tmp.replace(reg)
            self._reg = reg
        except OSError:
            try:
                tmp.unlink()
            except OSError:
                pass
            print(
                "autoclaude: registry write failed; running unregistered.",
                file=self.err,
            )
        return None

    def _plugin_gate(self, ap_dir: Path) -> int | None:
        state_path = ap_dir / "state.json"
        plugins_json = Path(
            self.env.get("_AUTOPILOT_PLUGINS_JSON")
            or Path.home() / ".claude" / "plugins" / "installed_plugins.json",
        )
        if not state_path.is_file() or not plugins_json.is_file():
            return None
        state = _load_json(state_path)
        installed = _load_json(plugins_json)
        if not isinstance(state, dict) or not isinstance(installed, dict):
            return None
        drift = plugin_drift(state, installed)
        if drift is None:
            return None
        print(
            f"\nautoclaude: plugin version drift ({drift}) — enforcement code "
            "rotated mid-batch. Stopping so the batch never runs on unpinned "
            "enforcement code. Re-pin state.batch.plugin_versions or "
            "investigate, then relaunch.",
            file=self.err,
        )
        self._notify(
            f"autopilot ⚠️ {self._repo_name()}",
            f"Plugin drift ({drift}); halted.",
        )
        return 1

    def _schema_gate(self, ap_dir: Path) -> int | None:
        """PRD 00106 acceptance: a resumed batch whose state schema this
        CLI does not understand is detected before any spawn. future →
        refuse loud; old/unstamped → warn once and continue."""
        try:
            loaded, status = state_mod.load(ap_dir / "state.json")
        except state_mod.StateError:
            return None
        if status == "future":
            version = loaded.get("schema_version")
            print(
                f"autoclaude: state.json carries schema v{version}, newer than "
                "this CLI understands; refusing to drive it. Update the CLI or "
                "restore the matching state.",
                file=self.err,
            )
            self._notify(
                f"autopilot ⚠️ {self._repo_name()}",
                f"Future-schema state.json (v{version}); halted.",
            )
            return 1
        if status in ("old", "unstamped") and not self._warned_schema:
            self._warned_schema = True
            print(
                f"autoclaude: state.json schema status '{status}' — a "
                "pre-cutover batch; the state CLI upgrades it on its next "
                "transaction.",
                file=self.err,
            )
        return None

    # ── decision table ──
    def _decide(self, ap_dir: Path, ts_start: float) -> dict:
        decision = {
            "signal": "",
            "detail": "",
            "next": "",
            "phase_end": "",
            "prd": "",
            "batch": "",
            "limit_wait": None,
        }
        state_path = ap_dir / "state.json"
        marker = ap_dir / "state-write-failed"
        if marker.is_file():
            decision["signal"] = "state_write_failed"
            data = _load_json(marker)
            detail = data.get("detail") if isinstance(data, dict) else None
            decision["detail"] = detail or "state write failed"

        state_touched = False
        mtime = _mtime(state_path)
        if mtime is not None and mtime >= int(ts_start):
            state_touched = True
        if state_touched:
            self._net_retries = 0
            self._died_retries = 0
        decision["state_touched"] = state_touched

        state = _load_json(state_path) if decision["signal"] == "" else None
        if isinstance(state, dict):
            decision["prd"] = state.get("prd") or ""
            decision["batch"] = (state.get("batch") or {}).get("id") or ""
            decision["phase_end"] = state.get("next_phase") or ""
            decision["next"] = decision["phase_end"]
            detail = pause_detail(state)
            stalled = None
            stall = state.get("stall_reason")
            if isinstance(stall, dict):
                stalled = stall.get("stalled")
            if detail:
                decision["signal"] = "paused"
                decision["detail"] = detail
            elif stalled == "subagent_prompt_overrun":
                decision["signal"] = "continue"
                decision["detail"] = "replan"
            elif not decision["next"]:
                decision["signal"] = "done"
            elif state_touched:
                decision["signal"] = "continue"

        if decision["signal"] == "":
            self._decide_no_progress(decision, ap_dir, state_path)
        return decision

    def _decide_no_progress(
        self, decision: dict, ap_dir: Path, state_path: Path
    ) -> None:
        """Branch 5: limit-hit is scheduling, network outage is
        infrastructure, anything else died."""
        reset = self._detect_limit(ap_dir / "last-session.log")
        if isinstance(reset, int):
            wait = usage_limit.wait_decision(
                reset,
                now=self._clock(),
                max_wait_secs=self._int("_AUTOPILOT_LIMIT_WAIT_MAX", 21600),
            )
            if wait is not None:
                stamp = _dt.datetime.fromtimestamp(reset).strftime("%H:%M")
                decision["signal"] = "continue"
                decision["detail"] = f"usage-limit; resuming ~{stamp}"
                decision["limit_wait"] = wait
            else:
                decision["signal"] = "died"
                decision["detail"] = (
                    "usage-limit reset beyond _AUTOPILOT_LIMIT_WAIT_MAX "
                    f"({self._int('_AUTOPILOT_LIMIT_WAIT_MAX', 21600)}s)"
                )
            return

        api_fail = last_result_field(
            ap_dir / "last-session.log",
            "result",
            error_only=True,
        )
        if isinstance(api_fail, str) and _CONNECTION_FAIL.search(api_fail):
            retries_max = self._int("_AUTOPILOT_NET_RETRIES_MAX", 3)
            if self._net_retries < retries_max:
                self._net_retries += 1
                net_max = self._int("_AUTOPILOT_NET_WAIT_MAX", 1800)
                deadline = self._clock() + net_max
                print(
                    f"\nautoclaude: API unreachable ({api_fail}). Polling "
                    f"connectivity, max {net_max}s (retry {self._net_retries}"
                    f"/{retries_max})…",
                    file=self.err,
                )
                ok = False
                while True:
                    if self._probe():
                        ok = True
                        break
                    if self._clock() >= deadline:
                        break
                    self._sleep(30)
                if ok:
                    decision["signal"] = "continue"
                    decision["detail"] = f"network restored (retry {self._net_retries})"
                else:
                    decision["signal"] = "died"
                    decision["detail"] = f"API unreachable for {net_max}s"
            else:
                decision["signal"] = "died"
                decision["detail"] = (
                    f"repeated API connection failures ({retries_max} relaunches)"
                )
            return

        verdict = died_next(
            decision["prd"],
            self._died_retries,
            self._int("_AUTOPILOT_DIED_RETRIES_MAX", 1),
        )
        if verdict == "retry":
            self._died_retries += 1
            decision["signal"] = "continue"
            decision["detail"] = (
                f"session died; retry {self._died_retries}/{self._int('_AUTOPILOT_DIED_RETRIES_MAX', 1)}"
            )
        elif verdict == "park":
            decision["signal"] = "park"
            decision["detail"] = (
                f"died after {self._died_retries} retries; parking {decision['prd']}"
            )
        else:
            decision["signal"] = "died"
            if not state_path.is_file():
                decision["detail"] = "no state.json"
            elif _load_json(state_path) is not None:
                decision["detail"] = "session made no progress (state.json untouched)"
            else:
                decision["detail"] = "state.json unreadable"

    def _fingerprint_bound(self, decision: dict, state_path: Path) -> None:
        """N identical progress fingerprints in a row = the loop is
        burning sessions on nothing. Cap deliberately generous
        (default 5); any progress resets it."""
        if (
            decision["signal"] == "continue"
            and decision.get("state_touched")
            and decision["detail"] != "replan"
        ):
            state = _load_json(state_path)
            fp = fingerprint(state) if isinstance(state, dict) else ""
            if fp and fp == self._fp_prev:
                self._fp_repeats += 1
                if self._fp_repeats >= self._int("_AUTOPILOT_PHASE_REPEATS_MAX", 5):
                    if decision["prd"]:
                        decision["signal"] = "park"
                        decision["detail"] = (
                            f"no progress across {self._fp_repeats} sessions; parking {decision['prd']}"
                        )
                    else:
                        decision["signal"] = "paused"
                        decision["detail"] = (
                            f"no measurable progress across {self._fp_repeats} "
                            f"consecutive sessions (fingerprint {fp}); "
                            "inspect state.json"
                        )
            else:
                self._fp_repeats = 0
            self._fp_prev = fp
        else:
            self._fp_repeats = 0
            self._fp_prev = ""

    def _append_metrics(
        self,
        ap_dir: Path,
        ts_start: float,
        ts_end: float,
        decision: dict,
        phase_launched: str,
        model: str,
    ) -> None:
        """One JSONL line per session, after the decision and before any
        exit path. Observation only - the append can never block or fail
        the loop (the one sanctioned silent failure, scoped to itself)."""
        try:
            line = {
                "ts_start": int(ts_start),
                "ts_end": int(ts_end),
                "wall_secs": int(ts_end) - int(ts_start),
                "prd": decision["prd"],
                "batch": decision["batch"],
                "phase_launched": phase_launched,
                "phase_end": decision["phase_end"],
                "signal": decision["signal"],
                "model": model,
            }
            cost = last_result_field(ap_dir / "last-session.log", "total_cost_usd")
            if isinstance(cost, (int, float)) and not isinstance(cost, bool):
                line["cost_usd"] = cost
            usage = last_result_field(ap_dir / "last-session.log", "usage")
            tokens = usage.get("output_tokens") if isinstance(usage, dict) else None
            if isinstance(tokens, int) and not isinstance(tokens, bool):
                line["tokens_out"] = tokens
            encoded = json.dumps(line, separators=(",", ":"))
            with open(ap_dir / "loop-metrics.jsonl", "a", encoding="utf-8") as fh:
                fh.write(encoded + "\n")
            ledger_dir = ap_dir / "ledger"
            ledger_dir.mkdir(parents=True, exist_ok=True)
            with open(ledger_dir / "loop-metrics.jsonl", "a", encoding="utf-8") as fh:
                fh.write(encoded + "\n")
        except (OSError, ValueError, TypeError):
            pass

    # ── act branches ──
    def _act_paused(self, decision: dict, state_path: Path) -> int:
        print(
            f"\n\033[1;33m⏸ autoclaude: session paused ON PURPOSE — {decision['detail']}\033[0m",
            file=self.err,
        )
        state = _load_json(state_path)
        if isinstance(state, dict):
            cap = state.get("cap_pause_reason")
            findings = cap.get("unresolved_findings") if isinstance(cap, dict) else None
            for finding in findings or []:
                if isinstance(finding, dict):
                    severity = finding.get("severity") or "?"
                    issue = (finding.get("issue") or "")[:90]
                    print(f"  · [{severity}] {issue}", file=self.err)
        print(
            "\n\n\033[1;36mTo resume (re-running autoclaude now would just pause again):\033[0m\n",
            file=self.err,
        )
        print(
            "  1. claude            # interactive session in this repo", file=self.err
        )
        print(
            "  2. /run-autopilot    # resumes from state.json; blockers become questions",
            file=self.err,
        )
        print(
            "  3. autoclaude        # after the decision, to continue unattended",
            file=self.err,
        )
        self._notify(
            f"autopilot ⚠️ {self._repo_name()}",
            f"Paused: {decision['detail']}",
        )
        return 1

    def _act_done(self, decision: dict, ap_dir: Path) -> int:
        reports = ap_dir / "reports"
        try:
            reports.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        state_path = ap_dir / "state.json"
        state = _load_json(state_path)
        prds_done = None
        if isinstance(state, dict):
            # jq's `.batch.completed_prds | length` yields 0 for missing
            # keys, so a parsed state always counts; only an unreadable
            # one omits the count (and the agoge decision) entirely.
            completed = (state.get("batch") or {}).get("completed_prds")
            prds_done = len(completed) if isinstance(completed, list) else 0
        stamp = decision["batch"] or _dt.datetime.now().strftime("%Y%m%d%H%M")
        try:
            state_path.replace(reports / f"{stamp}-state-final.json")
        except OSError:
            pass
        suffix = f" {prds_done} PRDs completed." if prds_done is not None else ""
        print(f"\nBacklog drained.{suffix}", file=self.out)
        self._notify(
            f"autopilot ✅ {self._repo_name()}",
            f"Backlog drained.{suffix}",
        )
        run_purge(self.cwd)
        run_agoge(
            ap_dir,
            decision["batch"],
            prds_done,
            self.env,
            self.out,
            claude_bin=self.runner_bin,
        )
        return 0

    def _act_park(self, decision: dict, ap_dir: Path) -> int | None:
        """None to relaunch (marker written or preserved); an exit code
        to halt."""
        marker = ap_dir / "park-requested"
        if marker.is_file():
            self._park_relaunches += 1
            marker_mtime = _mtime(marker)
            age = (
                0 if marker_mtime is None else max(0, int(self._clock()) - marker_mtime)
            )
            stale_max = max(
                self._int("_AUTOPILOT_SESSION_MAX", 7200),
                self._int("_AUTOPILOT_SESSION_MAX_REVIEW", 10800),
            )
            if (
                self._park_relaunches > self._int("_AUTOPILOT_DIED_RETRIES_MAX", 1)
                or age >= stale_max
            ):
                print(
                    f"\nautoclaude: park-requested unconsumed "
                    f"({self._park_relaunches} relaunches, {age}s) — halting "
                    "(systemic).",
                    file=self.err,
                )
                self._notify(
                    f"autopilot ⚠️ {self._repo_name()}",
                    "Park marker unconsumed; halting.",
                )
                return 1
            print(
                f"\nautoclaude: park-requested pending (relaunch "
                f"{self._park_relaunches}); backing off then relaunching.",
                file=self.err,
            )
            self._sleep(self._int("_AUTOPILOT_PARK_BACKOFF", 30))
            return None
        self._park_relaunches = 0
        try:
            marker.write_text(
                json.dumps({"prd": decision["prd"], "reason": decision["detail"]}),
            )
            written = marker.stat().st_size > 0
        except OSError:
            written = False
        if not written:
            print(
                f"\nautoclaude: park-requested write failed for {decision['prd']} — halting (cannot hand off).",
                file=self.err,
            )
            self._notify(
                f"autopilot ⚠️ {self._repo_name()}",
                "Park marker write failed; halting.",
            )
            try:
                marker.unlink()
            except OSError:
                pass
            return 1
        print(
            f"\nautoclaude: parking {decision['prd']} ({decision['detail']}); continuing batch.",
            file=self.out,
        )
        self._notify(
            f"autopilot ⏭ {self._repo_name()}",
            f"Parking {decision['prd']}.",
        )
        return None

    # ── run ──
    def run(self) -> int:
        def _on_term(signum, frame):
            raise _Terminated(128 + signum)

        old_handlers = {}
        for sig in (signal_mod.SIGTERM, signal_mod.SIGHUP):
            try:
                old_handlers[sig] = signal_mod.signal(sig, _on_term)
            except (ValueError, OSError):
                pass  # not the main thread (tests) - handlers stay default
        try:
            return self._run_loop()
        except KeyboardInterrupt:
            self._teardown()
            return 130
        except _Terminated as term:
            self._teardown()
            return term.code
        finally:
            for sig, handler in old_handlers.items():
                try:
                    signal_mod.signal(sig, handler)
                except (ValueError, OSError):
                    pass

    def _run_loop(self) -> int:
        while True:
            code = self._memory_gate()
            if code is not None:
                self._teardown()
                return code

            ap_dir = self._resolve_ap_dir()

            code = self._register(ap_dir)
            if code is not None:
                self._teardown()
                return code

            if pause.consume_pause(ap_dir):
                pause.stamp_paused(ap_dir)
                # NOT the _act_paused runbook: that exit leaves a paused
                # state that re-pauses the loop, so its interactive step is
                # mandatory. Here the marker is consumed and nothing blocks,
                # so autoclaude alone resumes - name that first, and keep the
                # take-over path for the operator who paused to intervene.
                print(
                    "\n\033[1;33m⏸ autoclaude: paused by operator ON "
                    "PURPOSE.\033[0m State intact.\n"
                    "Resume unattended: autoclaude\n"
                    "To take over first: claude → /run-autopilot, then autoclaude",
                    file=self.out,
                )
                self._notify(
                    f"autopilot ⏸ {self._repo_name()}",
                    "Paused by operator at a session boundary. State intact.",
                )
                self._teardown()
                return 0

            pause.clear_paused(ap_dir)  # past the pause branch: this loop runs

            code = self._plugin_gate(ap_dir)
            if code is not None:
                self._teardown()
                return code

            code = self._schema_gate(ap_dir)
            if code is not None:
                self._teardown()
                return code

            ts_start = self._clock()
            state = _load_json(ap_dir / "state.json")
            phase_launched = ""
            prd_launched = ""
            if isinstance(state, dict):
                phase_launched = state.get("next_phase") or ""
                prd_launched = state.get("prd") or ""

            plan = routing.route(phase_launched, ap_dir, env=self.env)
            stamp = _dt.datetime.now().strftime("%H:%M:%S")
            print(
                f"\n━━ {stamp} · phase {phase_launched or 'bootstrap'} · prd "
                f"{prd_launched or 'no-prd'} · {plan.model}/{plan.effort} ━━",
                file=self.out,
            )

            self._spawn(
                plan.model,
                plan.effort,
                cap_secs=plan.cap_secs,
                autopilot_dir=ap_dir,
                env=self.env,
                runner_bin=self.runner_bin,
                proc_slot=self._proc_slot,
            )
            self._proc_slot[0] = None
            self._cleanup_orphans()

            decision = self._decide(ap_dir, ts_start)
            self._fingerprint_bound(decision, ap_dir / "state.json")
            ts_end = self._clock()
            self._append_metrics(
                ap_dir,
                ts_start,
                ts_end,
                decision,
                phase_launched,
                plan.model,
            )

            branch = decision["signal"]
            if branch == "state_write_failed":
                print(
                    "\nautoclaude: state-write-failed marker present — halting "
                    f"(broken state boundary): {decision['detail']}",
                    file=self.err,
                )
                self._notify(
                    f"autopilot ⚠️ {self._repo_name()}",
                    f"State write failed: {decision['detail']}",
                )
                self._teardown()
                return 1
            if branch == "continue":
                if decision["limit_wait"] is not None:
                    print(
                        f"\nautoclaude: usage limit hit; waiting "
                        f"{decision['limit_wait'] // 60} min "
                        f"({decision['detail']}).",
                        file=self.out,
                    )
                    self._notify(
                        f"autopilot ⏳ {self._repo_name()}",
                        f"Usage limit; {decision['detail']}.",
                    )
                    self._sleep(decision["limit_wait"])
                elif decision["detail"] == "replan":
                    print(
                        "\nWork task prompt overran budget; PRD will be replanned. Continuing…",
                        file=self.out,
                    )
                else:
                    print(
                        f"\nContinuing (next phase: {decision['next']})…",
                        file=self.out,
                    )
                continue
            if branch == "paused":
                code = self._act_paused(decision, ap_dir / "state.json")
                self._teardown()
                return code
            if branch == "done":
                code = self._act_done(decision, ap_dir)
                self._teardown()
                return code
            if branch == "died":
                print(
                    f"\nautoclaude: session died ({decision['detail']}). "
                    f"Backlog NOT drained. Check {ap_dir}/state.json and "
                    f"{ap_dir}/last-session.log.",
                    file=self.err,
                )
                self._notify(
                    f"autopilot ⚠️ {self._repo_name()}",
                    f"Stopped: {decision['detail']}. Needs attention.",
                )
                self._teardown()
                return 1
            if branch == "park":
                code = self._act_park(decision, ap_dir)
                if code is not None:
                    self._teardown()
                    return code
                continue
            print(
                f"\nautoclaude: unknown decision signal '{branch}'; halting.",
                file=self.err,
            )
            self._teardown()
            return 1


def main(argv: list[str] | None = None) -> int:
    return Loop().run()
