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

    select, frontmatter, phase-done, resume-target, check-plan and other
    subcommands are deferred to later PRDs (00052/00053/00089); the
    subcommand registry below is where they get added.

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
    6   reserved (unused by this PRD)
    7   state file already exists (init)
    8   backup refused: missing or corrupt .bak (restore)
    9   deferred-record I/O failed (defer, or stall/park's inner append)
    10  stall_op conflict (stall/park)
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

from cli import records, schema, state

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


def _add_init(subparsers) -> None:
    p = subparsers.add_parser("init")
    p.add_argument("--state")
    p.add_argument("--prd", required=True)


def _run_init(args: argparse.Namespace) -> int:
    state_path = _resolve_state_path(args.state)
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
    autopilot_dir = (
        Path(args.autopilot_dir) if args.autopilot_dir is not None else state_path.parent
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
    try:
        state.transaction(state_path, records.reset_prd_fields, validator=_validate_reset_prd)
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


def _add_restore(subparsers) -> None:
    p = subparsers.add_parser("restore")
    p.add_argument("--state")


def _run_restore(args: argparse.Namespace) -> int:
    state_path = _resolve_state_path(args.state)
    try:
        state.restore(state_path)
    except state.BackupError:
        return 8
    except OSError as err:
        print(f"autopilot: restore failed: {err}", file=sys.stderr)
        return 2
    return 0


# Registry, not an if/elif chain over sys.argv: PRDs 00052/00053 add entries
# here (an (add_parser_fn, run_fn) pair per subcommand name).
_SUBCOMMANDS: dict[str, tuple] = {
    "init": (_add_init, _run_init),
    "stall": (_add_stall, _run_stall),
    "park": (_add_park, _run_park),
    "reset-prd": (_add_reset_prd, _run_reset_prd),
    "defer": (_add_defer, _run_defer),
    "restore": (_add_restore, _run_restore),
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
