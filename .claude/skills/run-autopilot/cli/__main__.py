#!/usr/bin/env python3
"""cli/__main__.py - argparse dispatch for the autopilot state CLI.

The `autopilot` bash function (development.plugin.bash) runs this file
directly: `python3 .../cli/__main__.py <subcommand> [flags...]`. It wraps
cli/state.py and cli/records.py as real CLI verbs - no library semantics
live here, only argument mapping, exit-code passthrough, and default
--state resolution.

Subcommands:
    init      --state --prd
        Create a fresh state.json ({"prd", "phase": "build",
        "next_phase": "build"}) via state.init().
    stall     --state --prd --site --detail --prds
        records.do_stall(); autopilot_dir is always the state file's own
        parent directory (no flag).
    park      --state --prds --autopilot-dir
        records.do_park().
    reset-prd --state
        One state.transaction() running records.reset_prd_fields under an
        owned-fields validator (the reset scalars only).
    defer     --state --prd --batch --json
        records.record_defer() with a JSON-parsed record payload.
    restore   --state
        state.restore(): rolls <state>.bak back over state.json.
    check-plan --state --ceiling
        policy.plan_over_ceiling(); exit 3 above the loop task ceiling.
    select    --prds
        selection.select() over the wip/ and backlog/ listings. Prints
        {"prd": ..., "source": "wip"|"backlog"|"drained"}. Decides only -
        the verified backlog->wip move stays with the caller.
    frontmatter --state --prd
        frontmatter.parse(), applied to state in ONE transaction and echoed
        as JSON; warnings go to stderr.
    phase-done --state --outcome
        transitions.apply(): the next phase AND every field effect the
        transition mandates, in one commit. The current phase comes from the
        state; there is no --phase flag and no per-effect flag.
    resume-target --state
        resume.resume_target(), after the schema-version preflight.
    gate      --review-file [--reviewers] [--require-codex-guard]
              [--assert-constraint-met]
        gate.run_gate() — the review-file shape gate (PRD 00107). Takes no
        --state and keeps the gate's own exit contract (0 pass / 1 shape gap
        / 2 constraint UNMET, see cli/gate.py), NOT the state-CLI codes below.
    render    {audit|report|metrics} --state [--stdout] [--now ISO]
              [--summary] [--stalled --site --detail] [--metrics PATH]
        The deterministic render surfaces (PRD 00107): `audit` writes
        <repo>/dev/local/reviews/<prd-base>-audit.md from the state decision
        arrays (preserving an existing file's Started: stamp); `report`
        appends the per-PRD section to reports/{batch_id}-report.md
        (creating it with the header), or the batch summary under --summary,
        or the short STALLED form under --stalled; `metrics` prints a
        per-PRD summary of loop-metrics.jsonl. --stdout prints instead of
        writing; --now pins the timestamp (tests/goldens).
    status    --state
        status.render_status(): a plain-text one-screen state view.
    loop
        loop.Loop().run() - loop-mode orchestration (PRD 00106): drives
        routed phase sessions over the decision table until drain,
        pause, halt, or an operator signal. Takes no flags; it anchors
        on cwd (walk-up) and the _AUTOPILOT_* env knobs, exactly as the
        bash wrapper loop did. Its exit code IS the loop outcome (0
        drained/paused-on-purpose, 1 halted, 130/143/129 on signals),
        not the state-CLI codes below.

--state, when omitted, resolves by walking up from cwd via
_walk_up.find_autopilot_dir() to <dir>/state.json. park's --autopilot-dir,
when omitted, defaults to the resolved --state path's parent directory (the
same rule stall and defer apply without a flag at all). stall/park's
--prds, when omitted, anchors on that same resolved autopilot dir (its
`.parent / "prds"`) rather than walking up from cwd independently - an
explicit --state pointed at a different tree carries --prds's default with
it, and an unresolved --state (no dev/local/autopilot ancestor) is what
leaves a bare --prds unresolved too.

Exit codes:
    0   ok
    1   usage error (unknown/missing subcommand, bad flags, malformed
        --json, --state unresolved - which also blocks --prds's default)
    2   state error (state.json missing or not valid JSON)
    3   no/ignored marker (park)
    4   move failed (stall/park's inner PRD move)
    5   systemic halt (park)
    6   future-schema state.json: refused before any effect (stall, park,
        reset-prd, restore)
    7   state file already exists (init)
    8   backup refused: missing or corrupt .bak (restore)
    9   deferred-record I/O failed (defer, or stall/park's inner append)
    10  stall_op conflict (stall/park)
    11  init's parent directory does not exist (init)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_CLI_DIR = Path(__file__).resolve().parent
_SKILL_ROOT = _CLI_DIR.parent
# FRONT of sys.path, unconditionally: a decoy top-level `cli/` package
# sitting anywhere else on sys.path (e.g. the invoking process's cwd) must
# never shadow the real one this script belongs to.
sys.path.insert(0, str(_SKILL_ROOT))

from cli import (
    frontmatter,
    gate,
    policy,
    records,
    render_audit,
    render_metrics,
    render_report,
    resume,
    schema,
    selection,
    state,
    status,
    transitions,
)

# Explicit guarded insert (mirrors records.py's own): no longer relies on
# importing cli.records having put scripts/ on sys.path as a side effect,
# so dropping `records` from the import above can't silently break this.
_SCRIPTS_DIR = _SKILL_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
import _walk_up


class _ArgumentParser(argparse.ArgumentParser):
    """Usage errors exit 1, not argparse's native 2 - exit 2 is reserved for
    state errors. Subparsers inherit this override too: add_subparsers()
    defaults parser_class to type(self)."""

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def _walk_up_or_exit(flag_name: str) -> Path:
    """Walk up from cwd via _walk_up.find_autopilot_dir(); exit 1 with a
    flag-specific message when no dev/local/autopilot ancestor is found."""
    autopilot_dir = _walk_up.find_autopilot_dir(Path.cwd())
    if autopilot_dir is None:
        print(
            f"autopilot: {flag_name} not given and no dev/local/autopilot found above cwd",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return autopilot_dir


def _resolve_state_path(raw: str | None) -> Path:
    if raw is not None:
        return Path(raw)
    return _walk_up_or_exit("--state") / "state.json"


def _schema_version_preflight(state_path: Path) -> int | None:
    """Warn/refuse based on `state_path`'s schema_version stamp, before a
    state-loading subcommand runs its effect. "old" warns on stderr and
    returns None (caller continues); "future" prints and returns 6 (caller
    must refuse before any effect); "unstamped"/"current" are silent (None).

    A load failure (missing/corrupt state) is not this function's concern:
    it returns None so the subcommand's own existing StateError handling
    takes over, rather than introducing a new failure mode here.
    """
    try:
        loaded, status = state.load(state_path)
    except state.StateError:
        return None
    if status == "old":
        version = loaded.get("schema_version")
        print(
            f"autopilot: old-schema state.json ({state_path}): "
            f"v{version} -> v{schema.SCHEMA_VERSION}, auto-upgrading",
            file=sys.stderr,
        )
        return None
    if status == "future":
        version = loaded.get("schema_version")
        print(
            f"autopilot: future-schema state.json ({state_path}): "
            f"v{version} > v{schema.SCHEMA_VERSION}, refusing",
            file=sys.stderr,
        )
        return 6
    return None


def _add_init(subparsers) -> None:
    p = subparsers.add_parser("init")
    p.add_argument("--state")
    p.add_argument("--prd", required=True)


def _run_init(args: argparse.Namespace) -> int:
    state_path = _resolve_state_path(args.state)
    if not state_path.parent.exists():
        print(
            f"autopilot: init failed: {state_path.parent} does not exist "
            "(Phase 0 creates the lifecycle dirs)",
            file=sys.stderr,
        )
        return 11
    initial = {"prd": args.prd, "phase": "build", "next_phase": "build"}
    try:
        state.init(state_path, initial)
    except state.StateExistsError:
        return 7
    except OSError as err:
        print(f"autopilot: init failed: {err}", file=sys.stderr)
        return 2
    return 0


def _resolve_prds_path(raw: str | None, autopilot_dir: Path) -> str:
    if raw is not None:
        return raw
    return str(autopilot_dir.parent / "prds")


def _add_stall(subparsers) -> None:
    p = subparsers.add_parser("stall")
    p.add_argument("--state")
    p.add_argument("--prd", required=True)
    p.add_argument("--site", required=True)
    p.add_argument("--detail", required=True)
    p.add_argument("--prds")


def _run_stall(args: argparse.Namespace) -> int:
    state_path = _resolve_state_path(args.state)
    refuse = _schema_version_preflight(state_path)
    if refuse is not None:
        return refuse
    prds_dir = _resolve_prds_path(args.prds, state_path.parent)
    return records.do_stall(
        state_path,
        prd=args.prd,
        site=args.site,
        detail=args.detail,
        prds_dir=prds_dir,
        autopilot_dir=state_path.parent,
    )


def _add_park(subparsers) -> None:
    p = subparsers.add_parser("park")
    p.add_argument("--state")
    p.add_argument("--prds")
    p.add_argument("--autopilot-dir")


def _run_park(args: argparse.Namespace) -> int:
    state_path = _resolve_state_path(args.state)
    refuse = _schema_version_preflight(state_path)
    if refuse is not None:
        return refuse
    autopilot_dir = (
        Path(args.autopilot_dir)
        if args.autopilot_dir is not None
        else state_path.parent
    )
    prds_dir = _resolve_prds_path(args.prds, autopilot_dir)
    return records.do_park(state_path, prds_dir=prds_dir, autopilot_dir=autopilot_dir)


def _validate_reset_prd(new_state: dict) -> None:
    """Owned-fields validator for reset-prd's single transaction: checks
    only the scalars records.reset_prd_fields assigns. Deliberately does not
    require stall_op absence (a bare reset-prd legitimately preserves an
    unrelated stall_op) and does not run whole-state schema.validate."""
    schema.require(new_state.get("phase"), str, "phase")
    schema.require(new_state.get("next_phase"), str, "next_phase")
    schema.require(new_state.get("phases_completed"), list, "phases_completed")
    for field in ("cycle", "tasks_total", "tasks_completed", "replan_count"):
        schema.require(new_state.get(field), int, field)


def _add_reset_prd(subparsers) -> None:
    p = subparsers.add_parser("reset-prd")
    p.add_argument("--state")


def _run_reset_prd(args: argparse.Namespace) -> int:
    state_path = _resolve_state_path(args.state)
    refuse = _schema_version_preflight(state_path)
    if refuse is not None:
        return refuse
    try:
        state.transaction(
            state_path,
            records.reset_prd_fields,
            validator=_validate_reset_prd,
        )
    except (state.StateError, OSError):
        return 2
    return 0


def _add_defer(subparsers) -> None:
    p = subparsers.add_parser("defer")
    p.add_argument("--state")
    p.add_argument("--prd", required=True)
    p.add_argument("--batch", required=True)
    p.add_argument("--json", required=True)


def _run_defer(args: argparse.Namespace) -> int:
    state_path = _resolve_state_path(args.state)
    try:
        record = json.loads(args.json)
    except json.JSONDecodeError as err:
        print(f"autopilot: defer --json is not valid JSON: {err}", file=sys.stderr)
        return 1
    if not isinstance(record, dict):
        print(
            f"autopilot: defer --json must be a JSON object, got {type(record).__name__}",
            file=sys.stderr,
        )
        return 1
    try:
        records.record_defer(state_path.parent, args.prd, args.batch, record)
    except (OSError, ValueError):
        return 9
    return 0


def _add_check_plan(subparsers) -> None:
    p = subparsers.add_parser("check-plan")
    p.add_argument("--state")
    p.add_argument("--ceiling", type=int, default=policy.LOOP_TASK_CEILING)
    # Deliberately no --count: the whole point of the gate is that the count
    # comes from the snapshot on disk, not from whoever wrote the plan.


def _run_check_plan(args: argparse.Namespace) -> int:
    state_path = _resolve_state_path(args.state)
    try:
        loaded, _version = state.load(state_path)
    except state.StateError as err:
        print(f"autopilot: check-plan failed: {err}", file=sys.stderr)
        return 2
    over, count = policy.plan_over_ceiling(loaded, args.ceiling)
    if over:
        print(
            f"autopilot: plan has {count} tasks, over the {args.ceiling}-task "
            f'loop ceiling. Loop mode: stall this PRD (site "oversized_plan"). '
            f"Interactive: this is a warning, continue.",
            file=sys.stderr,
        )
        return 3
    return 0


def _listdir(path: Path) -> list[str]:
    """Basenames in `path`, or [] when it does not exist.

    An absent lifecycle dir is not an error here: Phase 0's `mkdir -p` block
    runs before selection, and a directory that is missing anyway holds no
    PRDs, which is what "empty" already means.
    """
    try:
        return [entry.name for entry in path.iterdir()]
    except (FileNotFoundError, NotADirectoryError):
        return []


def _add_select(subparsers) -> None:
    p = subparsers.add_parser("select")
    p.add_argument("--prds")
    # Deliberately no --hold and no --include-parked: hold/ is unreachable
    # from selection.select() by construction, and a flag would make the
    # parked/deferred exclusion optional.


def _run_select(args: argparse.Namespace) -> int:
    if args.prds is not None:
        prds_dir = Path(args.prds)
    else:
        prds_dir = _walk_up_or_exit("--prds").parent / "prds"
    prd, source = selection.select(
        _listdir(prds_dir / "wip"),
        _listdir(prds_dir / "backlog"),
    )
    print(json.dumps({"prd": prd, "source": source}))
    # Exit 0 even when drained: nothing failed, and the caller branches on
    # "source", which cannot be confused with an error the way an exit code
    # shared with real failures could.
    return 0


def _add_frontmatter(subparsers) -> None:
    p = subparsers.add_parser("frontmatter")
    p.add_argument("--state")
    p.add_argument("--prd", required=True)


def _run_frontmatter(args: argparse.Namespace) -> int:
    prd_path = Path(args.prd)
    try:
        text = prd_path.read_text(encoding="utf-8")
    except OSError as err:
        print(f"autopilot: cannot read PRD {prd_path}: {err}", file=sys.stderr)
        return 1
    fields, warnings = frontmatter.parse(text)
    for line in warnings:
        print(line, file=sys.stderr)

    state_path = _resolve_state_path(args.state)
    refuse = _schema_version_preflight(state_path)
    if refuse is not None:
        return refuse

    before: dict = {}

    def apply(current: dict) -> dict:
        before.update(current)
        return {**current, **fields}

    try:
        state.transaction(
            state_path,
            apply,
            validator=lambda new_state: schema.validate(
                {key: value for key, value in new_state.items() if key in fields},
            ),
        )
    except (state.StateError, OSError) as err:
        print(f"autopilot: frontmatter write failed: {err}", file=sys.stderr)
        return 2

    for key, new_value in fields.items():
        if key in before and before[key] != new_value:
            print(
                f"autopilot: PRD frontmatter reset {key} {before[key]} -> {new_value}",
                file=sys.stderr,
            )
    print(json.dumps(fields, sort_keys=True))
    return 0


def _add_phase_done(subparsers) -> None:
    p = subparsers.add_parser("phase-done")
    p.add_argument("--state")
    p.add_argument("--outcome", required=True, choices=transitions.OUTCOMES)
    # Deliberately no --phase and no per-effect flags: the current phase comes
    # from the state, and every effect a transition mandates is the
    # transition's own, never something a caller can forget to pass.


def _run_phase_done(args: argparse.Namespace) -> int:
    state_path = _resolve_state_path(args.state)
    refuse = _schema_version_preflight(state_path)
    if refuse is not None:
        return refuse

    before: dict = {}

    def advance(current: dict) -> dict:
        before.update(current)
        return transitions.apply(current, args.outcome)

    try:
        committed = state.transaction(
            state_path,
            advance,
            validator=lambda new_state: schema.validate_changed(before, new_state),
        )
    except transitions.UnknownTransition as err:
        print(f"autopilot: {err}", file=sys.stderr)
        return 1
    except schema.SchemaError as err:
        print(f"autopilot: phase-done rejected: {err}", file=sys.stderr)
        return 1
    except (state.StateError, OSError) as err:
        print(f"autopilot: phase-done failed: {err}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "phase": committed.get("phase"),
                "next_phase": committed.get("next_phase"),
            },
        ),
    )
    return 0


def _add_resume_target(subparsers) -> None:
    p = subparsers.add_parser("resume-target")
    p.add_argument("--state")


def _run_resume_target(args: argparse.Namespace) -> int:
    state_path = _resolve_state_path(args.state)
    # The version signal comes BEFORE the target: an old or future state.json
    # must be surfaced rather than resumed blindly.
    refuse = _schema_version_preflight(state_path)
    if refuse is not None:
        return refuse
    try:
        loaded, _version = state.load(state_path)
    except state.StateError as err:
        print(f"autopilot: resume-target failed: {err}", file=sys.stderr)
        return 2
    print(resume.resume_target(loaded))
    return 0


def _add_gate(subparsers) -> None:
    p = subparsers.add_parser("gate")
    p.add_argument("--review-file", type=Path, required=True)
    p.add_argument("--reviewers", default=None)
    p.add_argument("--require-codex-guard", action="store_true", default=False)
    p.add_argument("--assert-constraint-met", action="store_true", default=False)


def _run_gate(args: argparse.Namespace) -> int:
    return gate.run_gate(
        args.review_file,
        args.reviewers,
        args.require_codex_guard,
        args.assert_constraint_met,
    )


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _add_render(subparsers) -> None:
    p = subparsers.add_parser("render")
    p.add_argument("surface", choices=["audit", "report", "metrics"])
    p.add_argument("--state")
    p.add_argument("--metrics")
    p.add_argument("--now")
    p.add_argument("--stdout", action="store_true", default=False)
    p.add_argument("--summary", action="store_true", default=False)
    p.add_argument("--stalled", action="store_true", default=False)
    p.add_argument("--site")
    p.add_argument("--detail")


def _load_state_or_exit(state_path: Path) -> dict | int:
    try:
        loaded, _version = state.load(state_path)
    except state.StateError as err:
        print(f"autopilot: cannot load state: {err}", file=sys.stderr)
        return 2
    return loaded


def _emit(
    text: str,
    out_path: Path,
    to_stdout: bool,
    append: bool,
    dedupe_heading: str | None = None,
) -> int:
    """Write a rendered block: print under --stdout, else create/append the
    target file with one blank line between blocks."""
    if to_stdout:
        print(text)
        return 0
    try:
        if append and out_path.exists():
            existing = out_path.read_text(encoding="utf-8")
            if dedupe_heading is not None:
                existing = render_report._replace_section(existing, dedupe_heading)
            merged = existing.rstrip("\n") + "\n\n" + text.rstrip("\n") + "\n"
        else:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            merged = text.rstrip("\n") + "\n"
        out_path.write_text(merged, encoding="utf-8")
    except OSError as err:
        print(f"autopilot: render write failed: {err}", file=sys.stderr)
        return 2
    print(str(out_path))
    return 0


def _run_render(args: argparse.Namespace) -> int:
    now = args.now or _utc_now()

    if args.surface == "metrics":
        if args.metrics is not None:
            metrics_path = Path(args.metrics)
        else:
            metrics_path = _resolve_state_path(args.state).parent / "loop-metrics.jsonl"
        print(render_metrics.render_metrics(render_metrics.load_rows(metrics_path)))
        return 0

    state_path = _resolve_state_path(args.state)
    loaded = _load_state_or_exit(state_path)
    if isinstance(loaded, int):
        return loaded
    autopilot_dir = state_path.parent

    if args.surface == "audit":
        prd = str(loaded.get("prd", ""))
        if not prd:
            print("autopilot: render audit needs state.prd", file=sys.stderr)
            return 2
        prd_base = prd.removesuffix(".md")
        # The reviews dir is derived by climbing to the repo root, so a
        # --state outside a dev/local/autopilot tree must refuse rather than
        # plant dev/local/reviews in whatever ancestor happens to be there.
        if autopilot_dir.parts[-3:] != ("dev", "local", "autopilot"):
            print(
                f"autopilot: render audit: {autopilot_dir} is not a "
                "dev/local/autopilot dir; cannot locate the repo's "
                "dev/local/reviews",
                file=sys.stderr,
            )
            return 2
        repo_root = autopilot_dir.parents[2]
        out_path = repo_root / "dev" / "local" / "reviews" / f"{prd_base}-audit.md"
        started = now
        if out_path.exists():
            try:
                started = (
                    render_audit.existing_started(out_path.read_text(encoding="utf-8"))
                    or now
                )
            except OSError:
                pass
        text = render_audit.render_audit(loaded, started, now)
        return _emit(text, out_path, args.stdout, append=False)

    # report
    batch_id = (loaded.get("batch") or {}).get("id")
    if not batch_id:
        print("autopilot: render report needs state.batch.id", file=sys.stderr)
        return 2
    metrics_path = (
        Path(args.metrics)
        if args.metrics is not None
        else autopilot_dir / "loop-metrics.jsonl"
    )
    rows = render_metrics.load_rows(metrics_path)
    if args.stalled:
        if not args.site or not args.detail:
            print("autopilot: --stalled needs --site and --detail", file=sys.stderr)
            return 1
        block = render_report.stalled_section(
            str(loaded.get("prd", "")),
            args.site,
            args.detail,
            now,
        )
        dedupe_heading = None
    elif args.summary:
        deferred_count = None
        deferred_path = autopilot_dir / "deferred" / f"{batch_id}-deferred.json"
        if deferred_path.exists():
            try:
                deferred_count = len(
                    json.loads(deferred_path.read_text(encoding="utf-8")).get(
                        "items",
                        [],
                    ),
                )
            except (OSError, json.JSONDecodeError, AttributeError):
                deferred_count = None
        block = render_report.batch_summary(loaded, rows, deferred_count)
        dedupe_heading = None
    else:
        prd_rows = render_metrics.matching_rows(
            rows,
            str(loaded.get("prd", "")),
            batch_id,
        )
        block = render_report.prd_section(loaded, prd_rows, now)
        dedupe_heading = f"## {loaded.get('prd', '')}"
    out_path = autopilot_dir / "reports" / f"{batch_id}-report.md"
    if not out_path.exists() and not args.stdout:
        started = render_report.batch_started(loaded, rows)
        block = render_report.header(batch_id, started) + "\n" + block.rstrip("\n") + "\n"
    return _emit(block, out_path, args.stdout, append=True, dedupe_heading=dedupe_heading)


def _add_loop(subparsers) -> None:
    subparsers.add_parser("loop")
    # Deliberately no flags: the loop anchors on cwd (walk-up) and reads
    # its knobs from the _AUTOPILOT_* environment, exactly as the bash
    # wrapper did. An explicit --state here would let loop-mode drive a
    # tree the pause/park markers don't live in.


def _run_loop_cmd(args: argparse.Namespace) -> int:
    # Imported here, not at module top: the loop pulls in urllib and the
    # runner stack, which the other verbs never need.
    from cli import loop

    return loop.Loop().run()


def _add_status(subparsers) -> None:
    p = subparsers.add_parser("status")
    p.add_argument("--state")


def _run_status(args: argparse.Namespace) -> int:
    state_path = _resolve_state_path(args.state)
    loaded = _load_state_or_exit(state_path)
    if isinstance(loaded, int):
        return loaded
    print(status.render_status(loaded))
    return 0


def _add_restore(subparsers) -> None:
    p = subparsers.add_parser("restore")
    p.add_argument("--state")


def _run_restore(args: argparse.Namespace) -> int:
    state_path = _resolve_state_path(args.state)
    refuse = _schema_version_preflight(state_path)
    if refuse is not None:
        return refuse
    try:
        state.restore(state_path)
    except state.BackupError:
        return 8
    except OSError as err:
        print(f"autopilot: restore failed: {err}", file=sys.stderr)
        return 2
    return 0


# Registry, not an if/elif chain over sys.argv: PRD 00106 adds entries here
# (an (add_parser_fn, run_fn) pair per subcommand name).
_SUBCOMMANDS: dict[str, tuple] = {
    "init": (_add_init, _run_init),
    "stall": (_add_stall, _run_stall),
    "park": (_add_park, _run_park),
    "reset-prd": (_add_reset_prd, _run_reset_prd),
    "defer": (_add_defer, _run_defer),
    "restore": (_add_restore, _run_restore),
    "check-plan": (_add_check_plan, _run_check_plan),
    "select": (_add_select, _run_select),
    "frontmatter": (_add_frontmatter, _run_frontmatter),
    "phase-done": (_add_phase_done, _run_phase_done),
    "resume-target": (_add_resume_target, _run_resume_target),
    "gate": (_add_gate, _run_gate),
    "render": (_add_render, _run_render),
    "status": (_add_status, _run_status),
    "loop": (_add_loop, _run_loop_cmd),
}


def _build_parser() -> _ArgumentParser:
    parser = _ArgumentParser(prog="autopilot")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for add_fn, _run_fn in _SUBCOMMANDS.values():
        add_fn(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    _, run_fn = _SUBCOMMANDS[args.command]
    return run_fn(args)


if __name__ == "__main__":
    sys.exit(main())
