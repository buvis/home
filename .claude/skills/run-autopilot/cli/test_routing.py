"""Port of the `test_autoclaude_build_model.sh` contract (PRD 00106).

Every unit scenario from the bash suite lands here with its rationale
compressed into the test name; the bash e2e rows (launch-line --model
assertions through a real `autoclaude` run) are re-expressed against
the loop driver in test_loop.py. The bash suite's stdout/stderr/exit-0
rows become "returns a string, never raises" by construction.

Contract pinned:
* target PRD = lowest 00XXX- basename in wip/, else backlog/ - never
  state.prd, which between PRDs still names the FINISHED one;
* OPUS when ANY of: (1) target frontmatter default_model: opus,
  (2) state.replan_count > 0, (3a) state.stall_reason != null,
  (3b) a type:"stall" item naming the target in the 2 NEWEST
  deferred logs by FILENAME, (4) state.cap_rotations non-empty,
  (5) a ledger key equal to the target; 2/3a/4 fire ONLY when
  state.prd == target;
* loop metrics are IGNORED (signal 6 retired, PRD 00111);
* promotion is recomputed every call - no latch.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cli.routing import OPUS, SONNET, Route, build_model, build_target, route


def _box(tmp_path: Path) -> Path:
    for sub in ("prds/wip", "prds/backlog", "prds/done", "prds/hold", "deferred"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    (tmp_path / "ledger.json").write_text("{}\n")
    return tmp_path


def _write_prd(path: Path, default_model: str | None = None) -> None:
    text = ""
    if default_model is not None:
        text = (
            "---\ncatchup: skip\nrework_cap: 3\n"
            f"default_model: {default_model}\ndesign: skip\n---\n"
        )
    text += f"\n# {path.name}\n\n## Problem\n\nFixture PRD.\n"
    path.write_text(text)


def _write_prd_fm(path: Path, body: str) -> None:
    path.write_text(f"---\n{body}\n---\n\n# {path.name}\n\nFixture PRD.\n")


def _state(box: Path, prd: str, **overrides) -> None:
    state = {
        "prd": prd,
        "next_phase": "build",
        "replan_count": 0,
        "cap_rotations": [],
        "stall_reason": None,
        "batch": {"id": "20260701-a"},
    }
    state.update(overrides)
    (box / "state.json").write_text(json.dumps(state))


def _model(box: Path) -> str:
    return build_model(
        box / "state.json",
        box / "prds",
        box / "ledger.json",
        box / "deferred",
    )


def test_no_signals_routes_sonnet(tmp_path):
    # Fields present and EXPLICITLY ZERO - presence-testing routes every
    # session to Opus, the regression PRD 00076 exists to stop. The
    # ledger holds a DIFFERENT PRD's key: signal 5 is target-keyed.
    box = _box(tmp_path)
    prd = "00021-rotate-session-logs-v1.md"
    _write_prd(box / "prds/wip" / prd)
    _state(box, prd)
    (box / "ledger.json").write_text(
        json.dumps({"00097-unrelated-rescue-v1.md": {"status": "approved"}}),
    )
    assert _model(box) == SONNET


def test_finished_prds_scratch_never_promotes_the_next_prd(tmp_path):
    # PRD-to-PRD launch: state.json still describes the DONE PRD (replan,
    # rotation, stall, ledger key, deferred stall, opus frontmatter).
    # None of it may promote the fresh backlog PRD.
    box = _box(tmp_path)
    done, nxt = "00034-purge-orphan-worktrees-v1.md", "00035-stamp-release-notes-v1.md"
    _write_prd(box / "prds/done" / done, "opus")
    _write_prd(box / "prds/backlog" / nxt)
    _state(
        box,
        done,
        replan_count=1,
        cap_rotations=[{"task_id": "task-2", "cycle": 1}],
        stall_reason={"stalled": "oversized_task", "detail": "task-2 overflowed"},
    )
    (box / "ledger.json").write_text(json.dumps({done: {"status": "consumed"}}))
    (box / "deferred" / "20260701-b-deferred.json").write_text(
        json.dumps({"items": [{"type": "stall", "site": "x", "prd": done}]}),
    )
    assert _model(box) == SONNET


def test_a_wip_siblings_scratch_never_promotes_the_target(tmp_path):
    # The .prd guard with BOTH PRDs in wip/: the scratch belongs to the
    # higher-numbered sibling state.json names, not to the target.
    box = _box(tmp_path)
    target = "00037-trim-the-boot-scan-v1.md"
    sibling = "00039-cache-the-catchup-capsule-v1.md"
    _write_prd(box / "prds/wip" / target)
    _write_prd(box / "prds/wip" / sibling, "opus")
    _state(
        box,
        sibling,
        replan_count=2,
        cap_rotations=[{"task_id": "task-5", "cycle": 1}],
        stall_reason={"stalled": "oversized_task", "detail": "sibling overflowed"},
    )
    assert _model(box) == SONNET


def test_lowest_wip_prd_wins_over_backlog_and_higher_wip(tmp_path):
    box = _box(tmp_path)
    _write_prd(box / "prds/wip" / "00048-rehome-the-cache-dir-v1.md", "opus")
    _write_prd(box / "prds/wip" / "00061-split-render-stream-v1.md", "sonnet")
    _write_prd(box / "prds/backlog" / "00012-fix-the-banner-typo-v1.md", "sonnet")
    _state(box, "")
    assert _model(box) == OPUS


def test_done_and_hold_are_not_candidates(tmp_path):
    box = _box(tmp_path)
    done = "00071-ship-the-marketplace-v1.md"
    _write_prd(box / "prds/done" / done, "opus")
    _write_prd(box / "prds/hold" / "00072-park-the-design-gate-v1.md", "opus")
    _state(box, done)
    assert _model(box) == SONNET
    assert build_target(box / "prds") is None


def test_signal1_frontmatter_opus_promotes(tmp_path):
    box = _box(tmp_path)
    prd = "00007-emit-the-batch-summary-v1.md"
    _write_prd(box / "prds/wip" / prd, "opus")
    _state(box, prd)
    assert _model(box) == OPUS


def test_signal1_body_mention_is_not_frontmatter(tmp_path):
    # The BODY quotes "default_model: opus" (PRDs about model routing
    # really do); only the frontmatter block counts.
    box = _box(tmp_path)
    prd = "00082-tune-the-echo-stopwords-v1.md"
    path = box / "prds/wip" / prd
    _write_prd(path, "sonnet")
    path.write_text(path.read_text() + "\n## Notes\n\n    default_model: opus\n")
    _state(box, prd)
    assert _model(box) == SONNET


def test_signal1_no_frontmatter_at_all_ignores_body(tmp_path):
    # No block to find: taking the FIRST default_model: line anywhere in
    # the file wrongly promotes here.
    box = _box(tmp_path)
    prd = "00019-widen-the-qwen-gate-v1.md"
    path = box / "prds/wip" / prd
    _write_prd(path)
    path.write_text(path.read_text() + "\nBody prose:\n\n    default_model: opus\n")
    _state(box, prd)
    assert _model(box) == SONNET


@pytest.mark.parametrize(
    ("label", "want", "body"),
    [
        (
            "no space after colon",
            OPUS,
            "catchup: skip\ndefault_model:opus\ndesign: skip",
        ),
        (
            "whitespace around key and value",
            OPUS,
            "catchup: skip\n  default_model  :  opus  \ndesign: skip",
        ),
        ("double-quoted", OPUS, 'catchup: skip\ndefault_model: "opus"\ndesign: skip'),
        ("single-quoted", OPUS, "catchup: skip\ndefault_model: 'opus'\ndesign: skip"),
        ("letter suffix", SONNET, "catchup: skip\ndefault_model: opusX\ndesign: skip"),
        (
            "word suffix",
            SONNET,
            "catchup: skip\ndefault_model: opus-extra\ndesign: skip",
        ),
        ("any suffix", SONNET, "catchup: skip\ndefault_model: opusy\ndesign: skip"),
        (
            "commented no indent",
            SONNET,
            "catchup: skip\n# default_model: opus\ndesign: skip",
        ),
        (
            "commented indented",
            SONNET,
            "catchup: skip\n  # default_model: opus\ndesign: skip",
        ),
        (
            "trailing comment on another key",
            SONNET,
            "catchup: skip # default_model: opus\ndesign: skip",
        ),
        (
            "mismatched quotes",
            SONNET,
            "catchup: skip\ndefault_model: \"opus'\ndesign: skip",
        ),
        (
            "real sonnet beside a commented opus decoy",
            SONNET,
            "catchup: skip\ndefault_model: sonnet\n# default_model: opus\ndesign: skip",
        ),
        (
            "glued hash is part of the value",
            SONNET,
            "catchup: skip\ndefault_model: opus#suffix\ndesign: skip",
        ),
        (
            "glued hash repeating the word",
            SONNET,
            "catchup: skip\ndefault_model: opus#opus\ndesign: skip",
        ),
        (
            "whitespace-preceded inline comment",
            OPUS,
            "catchup: skip\ndefault_model: opus  # rationale\ndesign: skip",
        ),
    ],
)
def test_signal1_frontmatter_edge_grammar(tmp_path, label, want, body):
    box = _box(tmp_path)
    prd = "00001-sigfm-edge-case-v1.md"
    _write_prd_fm(box / "prds/wip" / prd, body)
    _state(box, prd)
    assert _model(box) == want, label


def test_signal2_replan_count_promotes(tmp_path):
    box = _box(tmp_path)
    prd = "00015-cap-the-review-cycles-v1.md"
    _write_prd(box / "prds/wip" / prd)
    _state(box, prd, replan_count=1)
    assert _model(box) == OPUS


def test_signal3a_stall_reason_promotes(tmp_path):
    box = _box(tmp_path)
    prd = "00023-guard-the-park-loop-v1.md"
    _write_prd(box / "prds/wip" / prd)
    _state(box, prd, stall_reason={"stalled": "escalation_exhausted", "detail": "x"})
    assert _model(box) == OPUS


def test_signal3b_stall_in_two_newest_deferred_by_filename(tmp_path):
    # The stall sits in the 2nd-newest file BY FILENAME while the mtimes
    # DISAGREE (the stall file is the oldest on disk): an mtime-ordered
    # window drops it.
    import os

    box = _box(tmp_path)
    prd = "00044-tier-the-work-pipeline-v1.md"
    _write_prd(box / "prds/wip" / prd)
    _state(box, prd)
    old = box / "deferred" / "202605120000-deferred.json"
    mid = box / "deferred" / "202606180000-deferred.json"
    new = box / "deferred" / "202607040000-deferred.json"
    old.write_text(json.dumps({"items": [{"type": "deferred-finding", "prd": "x"}]}))
    mid.write_text(
        json.dumps(
            {
                "items": [
                    {"type": "deferred_decision", "prd": "00041-y-v1.md"},
                    {"type": "stall", "site": "wrapper_died", "prd": prd},
                ],
            },
        ),
    )
    new.write_text(json.dumps({"items": [{"type": "doubt", "prd": "z"}]}))
    os.utime(mid, (1, 1))
    os.utime(new, (2_000_000_000, 2_000_000_000))
    os.utime(old, (2_100_000_000, 2_100_000_000))
    assert _model(box) == OPUS


def test_signal3b_a_lone_deferred_log_is_still_scanned(tmp_path):
    # The 2-newest window must be a bounds-safe positive offset; the
    # negative-slice form returns ZERO elements on a 1-element array.
    box = _box(tmp_path)
    prd = "00046-catch-the-one-file-window-v1.md"
    _write_prd(box / "prds/wip" / prd)
    _state(box, prd)
    (box / "deferred" / "202607060000-deferred.json").write_text(
        json.dumps({"items": [{"type": "stall", "site": "design_gate", "prd": prd}]}),
    )
    assert _model(box) == OPUS


def test_signal3b_stall_outside_the_window_does_not_promote(tmp_path):
    # The target's stall exists only in the 3rd-newest file by name -
    # and that file is the NEWEST on disk, so an mtime window pulls it
    # in and wrongly promotes.
    import os

    box = _box(tmp_path)
    prd = "00052-fold-metrics-into-the-ledger-v1.md"
    _write_prd(box / "prds/wip" / prd)
    _state(box, prd)
    oldest = box / "deferred" / "202604010000-deferred.json"
    mid = box / "deferred" / "202605020000-deferred.json"
    newest = box / "deferred" / "202606030000-deferred.json"
    oldest.write_text(
        json.dumps({"items": [{"type": "stall", "site": "design_gate", "prd": prd}]}),
    )
    mid.write_text(
        json.dumps({"items": [{"type": "stall", "site": "c", "prd": "00050-o-v1.md"}]}),
    )
    newest.write_text(
        json.dumps({"items": [{"type": "deferred-finding", "prd": prd}]}),
    )
    os.utime(oldest, (2_100_000_000, 2_100_000_000))
    os.utime(mid, (1, 1))
    os.utime(newest, (2, 2))
    assert _model(box) == SONNET


def test_signal3b_type_and_prd_must_match_on_the_same_item(tmp_path):
    # The newest file holds a stall (another PRD) and a non-stall entry
    # naming the target: per-FILE matching wrongly promotes.
    box = _box(tmp_path)
    prd = "00058-stamp-the-work-start-sha-v1.md"
    _write_prd(box / "prds/wip" / prd)
    _state(box, prd)
    (box / "deferred" / "202606100000-deferred.json").write_text(
        json.dumps({"items": []}),
    )
    (box / "deferred" / "202607150000-deferred.json").write_text(
        json.dumps(
            {
                "items": [
                    {"type": "stall", "site": "design_gate", "prd": "00057-g-v1.md"},
                    {"type": "deferred-finding", "prd": prd},
                ],
            },
        ),
    )
    assert _model(box) == SONNET


def test_signal4_cap_rotation_promotes(tmp_path):
    box = _box(tmp_path)
    prd = "00056-rotate-on-the-context-cap-v1.md"
    _write_prd(box / "prds/wip" / prd)
    _state(box, prd, cap_rotations=[{"task_id": "task-7", "cycle": 2}])
    assert _model(box) == OPUS


def test_signal5_ledger_key_any_status_promotes(tmp_path):
    box = _box(tmp_path)
    prd = "00076-rescue-the-ladder-with-fable-v1.md"
    _write_prd(box / "prds/wip" / prd)
    _state(box, prd)
    (box / "ledger.json").write_text(
        json.dumps(
            {
                "00075-gate-on-memory-pressure-v1.md": {"status": "approved"},
                prd: {"status": "rejected"},
            },
        ),
    )
    assert _model(box) == OPUS


def test_signal5_target_as_a_value_never_promotes(tmp_path):
    # A KEY lookup, not a substring scan of the file.
    box = _box(tmp_path)
    prd = "00081-prevent-the-defect-class-v1.md"
    _write_prd(box / "prds/wip" / prd)
    _state(box, prd)
    (box / "ledger.json").write_text(
        json.dumps({"00080-diagnose-v1.md": {"status": "approved", "supersedes": prd}}),
    )
    assert _model(box) == SONNET


def test_promote_then_clear_never_latches(tmp_path):
    # PRD 00111's decay acceptance as three consecutive calls on one box:
    # signal-free -> Sonnet; rotation -> Opus; cleared -> Sonnet again.
    box = _box(tmp_path)
    prd = "00031-promote-then-clear-v1.md"
    _write_prd(box / "prds/wip" / prd)
    _state(box, prd)
    assert _model(box) == SONNET
    _state(box, prd, cap_rotations=[{"task_id": "t-3", "cycle": 1}])
    assert _model(box) == OPUS
    _state(box, prd)
    assert _model(box) == SONNET


def test_no_state_json_is_not_fatal_and_lowest_backlog_wins(tmp_path):
    box = _box(tmp_path)
    _write_prd(box / "prds/backlog" / "00003-register-the-running-loop-v1.md")
    _write_prd(box / "prds/backlog" / "00009-escalate-the-model-ladder-v1.md", "opus")
    assert _model(box) == SONNET


def test_no_state_json_still_evaluates_frontmatter_of_lowest(tmp_path):
    box = _box(tmp_path)
    _write_prd(box / "prds/backlog" / "00004-pin-the-plugin-versions-v1.md", "opus")
    _write_prd(box / "prds/backlog" / "00011-render-the-brief-v1.md", "sonnet")
    assert _model(box) == OPUS


def test_malformed_state_and_ledger_json_route_sonnet(tmp_path):
    # The bash contract: never fatal, nothing on stderr. Malformed
    # sidecars are false signals, not crashes.
    box = _box(tmp_path)
    prd = "00060-tolerate-garbage-v1.md"
    _write_prd(box / "prds/wip" / prd)
    (box / "state.json").write_text("{not json")
    (box / "ledger.json").write_text("[]not json")
    (box / "deferred" / "202601010000-deferred.json").write_text("{broken")
    assert _model(box) == SONNET


# ── route(): the per-phase case table ────────────────────────────────────────


def _route(phase: str, tmp_path: Path, env: dict | None = None) -> Route:
    ap_dir = tmp_path / "dev/local/autopilot"
    ap_dir.mkdir(parents=True, exist_ok=True)
    return route(phase, ap_dir, env=env or {})


def test_route_build_defaults_to_sonnet_xhigh_7200(tmp_path):
    got = _route("build", tmp_path)
    assert got == Route(model=SONNET, effort="xhigh", cap_secs=7200)


def test_route_absent_phase_is_a_build_launch(tmp_path):
    assert _route("", tmp_path).model == SONNET


def test_route_build_kill_switch_wins_over_routing(tmp_path):
    got = _route("build", tmp_path, {"_AUTOPILOT_MODEL_BUILD": OPUS})
    assert got.model == OPUS
    assert got.effort == "xhigh"


def test_route_review_is_opus_xhigh_10800(tmp_path):
    assert _route("review", tmp_path) == Route(
        model=OPUS,
        effort="xhigh",
        cap_secs=10800,
    )


def test_route_done_is_sonnet_medium_7200(tmp_path):
    assert _route("done", tmp_path) == Route(
        model=SONNET,
        effort="medium",
        cap_secs=7200,
    )


def test_route_unknown_phase_fails_expensive(tmp_path):
    # Opus xhigh, and deliberately NO env model override on this branch.
    got = _route("mystery", tmp_path, {"_AUTOPILOT_MODEL_REVIEW": SONNET})
    assert got == Route(model=OPUS, effort="xhigh", cap_secs=7200)


def test_route_env_caps_and_efforts_apply(tmp_path):
    got = _route(
        "review",
        tmp_path,
        {"_AUTOPILOT_SESSION_MAX_REVIEW": "60", "_AUTOPILOT_EFFORT_REVIEW": "high"},
    )
    assert got.cap_secs == 60
    assert got.effort == "high"


def test_route_build_reads_the_real_signal_paths(tmp_path):
    # route() wires build_model to the wrapper's exact sidecar paths:
    # ledger/fable-requests.json under the autopilot dir, prds beside it.
    ap_dir = tmp_path / "dev/local/autopilot"
    (ap_dir / "ledger").mkdir(parents=True)
    prds = tmp_path / "dev/local/prds/wip"
    prds.mkdir(parents=True)
    prd = "00013-route-from-the-ledger-v1.md"
    _write_prd(prds / prd)
    (ap_dir / "ledger" / "fable-requests.json").write_text(
        json.dumps({prd: {"status": "approved"}}),
    )
    assert route("build", ap_dir, env={}).model == OPUS
