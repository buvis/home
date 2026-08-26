"""Tests for audit_qwen.py (PRD 00112). Run: uv run --with pytest pytest."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import audit_qwen as aq

FIXTURES = Path(__file__).parent / "fixtures"
LEDGER_PRD = "00905-fixture-ledger-v1.md"


def make_repo(
    tmp_path: Path,
    name: str,
    reports: tuple = (),
    state: str | None = None,
) -> Path:
    repo = tmp_path / name
    auto = repo / "dev" / "local" / "autopilot"
    (auto / "reports").mkdir(parents=True)
    for fixture in reports:
        shutil.copy(
            FIXTURES / fixture,
            auto / "reports" / f"20260812000{len(fixture)}-report.md",
        )
    if state:
        shutil.copy(FIXTURES / state, auto / "state.json")
    return repo


def agg_for_verdict(
    passed=0,
    failed=0,
    unclassified=0,
    report_qwen=0,
    plan=None,
) -> dict:
    return {
        "state_qwen": passed + failed + unclassified,
        "ledger_qwen": 0,
        "report_qwen": report_qwen,
        "eligible": 0,
        "gate": {"passed": passed, "failed": failed, "unclassified": unclassified},
        "preflight": {},
        "plan": plan or {},
        "dispatch": {},
        "batch_rows": [],
        "superseded": 0,
    }


# --- Phase 0: parsing -------------------------------------------------------


def test_modern_report_parses_mix_preflight_and_split_exclusions():
    parsed = aq.parse_report(FIXTURES / "report-modern.md")
    assert parsed["unparsed"] is None
    alpha, beta, gamma = parsed["sections"]
    assert alpha["prd"] == "00801-fixture-alpha-v1.md" and not alpha["stalled"]
    assert alpha["mix"]["attempts"] == {"claude": 2, "qwen": 3}
    assert alpha["mix"]["preflight"] == {"healthy": 2, "completion_failed": 1}
    assert alpha["mix"]["plan"] == {"ui": 2, "tier": 1}
    assert alpha["mix"]["dispatch"] == {"memory_pressure": 1}
    assert beta["mix"]["attempts"] == {}  # "no implementor data"
    assert gamma["stalled"]


def test_prose_era_exclusion_line_counts_as_plan_time():
    plan, dispatch = aq.parse_exclusion_line(
        "tier 1, files 1, docs-judgment 2, backend_down 4",
    )
    assert plan == {"tier": 1, "files": 1, "docs-judgment": 2, "backend_down": 4}
    assert dispatch == {}


def test_code_era_exclusion_line_none_variants():
    plan, dispatch = aq.parse_exclusion_line(
        "none (plan-time); dispatch-time reroutes: memory_pressure 1",
    )
    assert plan == {} and dispatch == {"memory_pressure": 1}
    plan, dispatch = aq.parse_exclusion_line(
        "ui 2 (plan-time); dispatch-time reroutes: none",
    )
    assert plan == {"ui": 2} and dispatch == {}


def test_legacy_report_is_legacy_not_unparsed():
    parsed = aq.parse_report(FIXTURES / "report-legacy.md")
    assert parsed["unparsed"] is None
    assert parsed["sections"][0]["mix"] is None


def test_renamed_mix_heading_lands_in_unparsed(tmp_path):
    repo = make_repo(tmp_path, "drifty", reports=("report-drifted.md",))
    record = aq.scan_repo(repo)
    assert record["reports"] == []
    assert len(record["unparsed"]) == 1
    path, why = record["unparsed"][0]
    assert "report.md" in path and "format drift" in why


def test_undecodable_report_lands_in_unparsed_not_a_crash(tmp_path):
    repo = make_repo(tmp_path, "latin")
    (
        repo / "dev" / "local" / "autopilot" / "reports" / "202601010000-report.md"
    ).write_bytes(
        b"# Autopilot Batch Report\xff\xfe broken bytes",
    )
    record = aq.scan_repo(repo)
    assert record["reports"] == []
    assert any("unreadable" in why for _, why in record["unparsed"])


def test_batch_rows_carry_per_batch_detail_notes(tmp_path):
    repo = make_repo(
        tmp_path,
        "detail",
        reports=("report-modern.md",),
        state="state-chains.json",
    )
    rows = aq.compute([aq.scan_repo(repo)])["batch_rows"]
    notes = {row[3]: row[5] for row in rows}
    assert notes["00901-fixture-prd-v1.md"] == (
        "preflight: healthy 3, pi_missing 1; excluded: ui 1; reroutes: memory_pressure 1"
    )
    assert notes["00801-fixture-alpha-v1.md"] == (
        "preflight: completion_failed 1, healthy 2; excluded: tier 1, ui 2;"
        " reroutes: memory_pressure 1"
    )
    assert notes["00802-fixture-beta-v1.md"] == "no implementor data"


def test_malformed_state_lands_in_unparsed(tmp_path):
    repo = make_repo(tmp_path, "broken", state="state-malformed.json")
    record = aq.scan_repo(repo)
    assert record["states"] == []
    assert any("state.json" in path for path, _ in record["unparsed"])


def test_repo_without_autopilot_dir_is_a_quiet_no_data_row(tmp_path):
    (tmp_path / "bare").mkdir()
    record = aq.scan_repo(tmp_path / "bare")
    assert record == {
        "repo": "bare",
        "reports": [],
        "states": [],
        "ledger": [],
        "archived": 0,
        "unparsed": [],
    }


# --- Phase 0/1: state chains ------------------------------------------------


def test_state_chain_counts_flow_into_aggregate(tmp_path):
    repo = make_repo(tmp_path, "chains", state="state-chains.json")
    agg = aq.compute([aq.scan_repo(repo)])
    assert agg["state_qwen"] == 4
    assert agg["eligible"] == 5
    assert agg["plan"] == {"ui": 1}
    assert agg["dispatch"] == {"memory_pressure": 1}
    assert agg["preflight"] == {"healthy": 3, "pi_missing": 1}
    assert agg["gate"] == {"passed": 2, "failed": 1, "unclassified": 1}


def test_gate_classification_rules():
    # The PRD's attribution scenario: qwen attempt then claude attempt on the
    # same task in the same pass is encoded post-00065 as outcome "escalated"
    # (and usually qwen_gate_failed) on the qwen entry.
    assert aq.classify_gate({"outcome": "escalated"}) == "failed"
    assert (
        aq.classify_gate({"qwen_gate_failed": True, "outcome": "completed"}) == "failed"
    )
    # Review-driven rework is the non-rework carve-out: the gate PASSED.
    assert aq.classify_gate({"outcome": "review_flagged"}) == "passed"
    assert aq.classify_gate({"outcome": "rework_failed"}) == "passed"
    assert aq.classify_gate({"outcome": "completed"}) == "passed"
    assert aq.classify_gate({"outcome": "aborted"}) == "unclassified"
    assert aq.classify_gate({}) == "unclassified"


# --- Phase 1: verdict thresholds -------------------------------------------


def test_verdict_holds_under_ten_attempts():
    word, reason = aq.verdict(agg_for_verdict(passed=9))
    assert word == "HOLD" and "insufficient data: 9" in reason


def test_verdict_widens_at_080_over_ten_and_ranks_fences():
    agg = agg_for_verdict(passed=9, failed=1, plan={"ui": 5, "tier": 7})
    word, reason = aq.verdict(agg)
    assert word == "WIDEN"
    assert "0.90" in reason
    assert reason.index("tier (7 tasks)") < reason.index("ui (5 tasks)")
    assert "CAVEAT" not in reason  # a recorded failure proves failures are recordable


def test_widen_with_zero_recorded_failures_carries_unfalsifiability_caveat():
    word, reason = aq.verdict(agg_for_verdict(passed=10))
    assert word == "WIDEN"
    assert "CAVEAT: zero gate failures" in reason


def test_verdict_narrows_under_050_over_six():
    agg = agg_for_verdict(passed=2, failed=4, report_qwen=5)
    word, reason = aq.verdict(agg)
    assert word == "NARROW" and "0.33" in reason


def test_verdict_holds_in_the_middle_band():
    word, reason = aq.verdict(agg_for_verdict(passed=7, failed=3))
    assert word == "HOLD" and "no threshold met" in reason


def test_verdict_holds_when_attempts_lack_chains():
    word, reason = aq.verdict(agg_for_verdict(report_qwen=13))
    assert word == "HOLD" and "0 are gate-classifiable" in reason


# --- Phase 1: attempt ledger ------------------------------------------------


def ledger_row(task_id: str, prd: str = LEDGER_PRD, **attempt) -> str:
    """One complete-prd row in the shape plugin PRD 00143 froze."""
    return json.dumps(
        {
            "batch_id": "202608260000",
            "prd": prd,
            "task_id": task_id,
            "task_name": f"task {task_id}",
            "task_model": attempt.get("implementor", "qwen"),
            "qwen_eligible": True,
            "recorded_at": "2026-08-26T10:00:00Z",
            "attempt": {"implementor": "qwen", "outcome": "completed", **attempt},
        },
    )


def write_ledger(repo: Path, *rows: str) -> Path:
    path = repo / "dev" / "local" / "autopilot" / "ledger" / "attempts.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def test_absent_ledger_reads_as_empty_and_leaves_the_card_unchanged(tmp_path):
    repo = make_repo(tmp_path, "noledger", state="state-chains.json")
    auto = repo / "dev" / "local" / "autopilot"
    assert aq.read_attempt_ledger(auto / "ledger" / "attempts.jsonl") == []
    record = aq.scan_repo(repo)
    assert record["ledger"] == [] and record["archived"] == 0
    records = [record]
    agg = aq.compute(records)
    assert agg["ledger_qwen"] == 0
    assert agg["state_qwen"] == 4  # unchanged from the state-only aggregate
    assert "| ledger |" not in aq.render(records, agg, "")


def test_ledger_rows_feed_implementor_and_gate_histograms(tmp_path):
    repo = make_repo(tmp_path, "ledgered")
    write_ledger(
        repo,
        ledger_row("t1", preflight_outcome="healthy"),
        ledger_row("t2", outcome="escalated", preflight_outcome="healthy"),
        ledger_row("t3", implementor="claude"),
    )
    records = [aq.scan_repo(repo)]
    assert records[0]["archived"] == 3
    agg = aq.compute(records)
    assert agg["ledger_qwen"] == 2  # the claude attempt is not a qwen attempt
    assert agg["gate"] == {"passed": 1, "failed": 1, "unclassified": 0}
    assert agg["preflight"] == {"healthy": 2}
    assert agg["eligible"] == 3
    card = aq.render(records, agg, "")
    assert "| 202608260000 | ledgered | ledger | " + LEDGER_PRD + " | 2 |" in card
    assert "| ledgered | 0 | 0 | 3 | ok |" in card


def test_ledger_eligible_counts_tasks_not_rows(tmp_path):
    repo = make_repo(tmp_path, "retried")
    write_ledger(repo, ledger_row("t1", outcome="escalated"), ledger_row("t1"))
    agg = aq.compute([aq.scan_repo(repo)])
    assert agg["eligible"] == 1  # one task, two attempts
    assert agg["ledger_qwen"] == 2


def test_malformed_ledger_row_is_skipped_loud_not_fatal(tmp_path, capsys):
    repo = make_repo(tmp_path, "torn")
    write_ledger(repo, ledger_row("t1"), "{not json", "[]", ledger_row("t2"))
    rows = aq.read_attempt_ledger(
        repo / "dev" / "local" / "autopilot" / "ledger" / "attempts.jsonl",
    )
    assert [r["task_id"] for r in rows] == ["t1", "t2"]
    err = capsys.readouterr().err
    assert ":2: skipped malformed row" in err
    assert ":3: skipped non-object row" in err


def test_numeric_batch_id_does_not_crash_the_group_sort(tmp_path):
    # The ledger is written by another repo; a JSON number where a string was
    # expected must not take the whole card down.
    repo = make_repo(tmp_path, "typedrift")
    numeric = json.loads(ledger_row("t1"))
    numeric["batch_id"] = 202608260001
    write_ledger(repo, json.dumps(numeric), ledger_row("t2"))
    agg = aq.compute([aq.scan_repo(repo)])
    assert agg["ledger_qwen"] == 2
    assert {row[0] for row in agg["batch_rows"]} == {"202608260001", "202608260000"}


def test_ledger_group_superseded_by_live_state_for_same_prd(tmp_path):
    repo = make_repo(tmp_path, "both", state="state-chains.json")
    write_ledger(repo, ledger_row("t1", prd="00901-fixture-prd-v1.md"))
    agg = aq.compute([aq.scan_repo(repo)])
    assert agg["ledger_qwen"] == 0
    assert agg["state_qwen"] == 4
    assert agg["superseded"] == 1


# --- dedup + render ---------------------------------------------------------


def test_report_section_superseded_by_state_for_same_prd(tmp_path):
    repo = tmp_path / "overlap"
    auto = repo / "dev" / "local" / "autopilot"
    (auto / "reports").mkdir(parents=True)
    (auto / "reports" / "202608140000-report.md").write_text(
        "# Autopilot Batch Report 202608140000\n\n"
        "## 00901-fixture-prd-v1.md\n\n"
        "### Implementor Mix\n\n"
        "| Implementor | Attempts |\n|---|---|\n| qwen | 5 |\n",
        encoding="utf-8",
    )
    shutil.copy(FIXTURES / "state-chains.json", auto / "state.json")
    agg = aq.compute([aq.scan_repo(repo)])
    assert agg["state_qwen"] == 4
    assert agg["report_qwen"] == 0
    assert agg["superseded"] == 1


def test_render_names_dropped_quinn_metric_and_legacy_rows(tmp_path):
    repo = make_repo(
        tmp_path,
        "mixed",
        reports=("report-legacy.md",),
        state="state-chains.json",
    )
    records = [aq.scan_repo(repo)]
    card = aq.render(records, aq.compute(records), "")
    assert "Quinn precision: **not computable**" in card
    assert "legacy (no mix data)" in card
    assert "**HOLD**" in card  # 4 attempts < 10


def test_main_writes_output_file_and_exits_zero(tmp_path):
    repo = make_repo(tmp_path, "solo", state="state-chains.json")
    out = tmp_path / "card.md"
    rc = aq.main(["--repo", str(repo), "--output", str(out)])
    assert rc == 0
    assert "Qwen Utilization Report Card" in out.read_text(encoding="utf-8")
