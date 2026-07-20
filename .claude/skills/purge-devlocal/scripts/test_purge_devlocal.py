"""Tests for purge_devlocal.py, one per retention rule."""
import os
import time
from pathlib import Path

import purge_devlocal as gc

NOW = time.time()


def touch(path: Path, days_old: float = 10) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")
    ts = NOW - days_old * gc.DAY
    os.utime(path, (ts, ts))


def make_store(root: Path) -> Path:
    store = root / "dev" / "local"
    for bucket in ("backlog", "wip", "done"):
        (store / "prds" / bucket).mkdir(parents=True)
    return store


def run(store: Path, *extra: str) -> int:
    return gc.main(["--repo", str(store), *extra])


def manifest(store: Path) -> str:
    p = store / gc.TRASH_DIR / "manifest.tsv"
    return p.read_text() if p.exists() else ""


def test_trashes_design_of_done_prd(tmp_path):
    store = make_store(tmp_path)
    touch(store / "prds" / "done" / "00042-foo.md")
    touch(store / "designs" / "00042-foo-v1-design.md")
    assert run(store, "--apply") == 0
    assert not (store / "designs" / "00042-foo-v1-design.md").exists()
    assert "done-linked\tdesigns/00042-foo-v1-design.md" in manifest(store)


def test_keeps_satellites_of_live_prds(tmp_path):
    store = make_store(tmp_path)
    touch(store / "prds" / "backlog" / "00050-a.md")
    touch(store / "prds" / "wip" / "00051-b.md")
    touch(store / "designs" / "00050-a-v1-design.md", days_old=90)
    touch(store / "tmp" / "coverage-00051c1.md", days_old=90)
    run(store, "--apply")
    assert (store / "designs" / "00050-a-v1-design.md").exists()
    assert (store / "tmp" / "coverage-00051c1.md").exists()


def test_min_age_guard_keeps_fresh_files(tmp_path):
    store = make_store(tmp_path)
    touch(store / "prds" / "done" / "00042-foo.md")
    touch(store / "designs" / "00042-foo-v1-design.md", days_old=1)
    run(store, "--apply")
    assert (store / "designs" / "00042-foo-v1-design.md").exists()


def test_stale_unlinkable_tmp_uses_tmp_rule_not_missing_prd(tmp_path):
    store = make_store(tmp_path)
    touch(store / "tmp" / "review-context-1781034671-89877.md", days_old=10)
    touch(store / "tmp" / "review-diff-1781034671-89877.diff", days_old=2)
    run(store, "--apply")
    assert not (store / "tmp" / "review-context-1781034671-89877.md").exists()
    assert (store / "tmp" / "review-diff-1781034671-89877.diff").exists()
    assert "stale-tmp\ttmp/review-context-1781034671-89877.md" in manifest(store)
    assert "missing-prd" not in manifest(store)


def test_never_touches_prds_or_keepers(tmp_path):
    store = make_store(tmp_path)
    touch(store / "prds" / "done" / "00042-foo.md", days_old=300)
    touch(store / "project-capsule.md", days_old=300)
    touch(store / "ecc-cursor", days_old=300)
    run(store, "--apply")
    assert (store / "prds" / "done" / "00042-foo.md").exists()
    assert (store / "project-capsule.md").exists()
    assert (store / "ecc-cursor").exists()


def test_flags_discovery_of_missing_prd_without_moving(tmp_path, capsys):
    store = make_store(tmp_path)
    touch(store / "discovery" / "00099-idea.md", days_old=30)
    run(store, "--apply")
    assert (store / "discovery" / "00099-idea.md").exists()
    assert "FLAG (prd gone, kept): discovery/00099-idea.md" in capsys.readouterr().out


def test_trashes_missing_prd_design(tmp_path):
    store = make_store(tmp_path)
    touch(store / "designs" / "00777-ghost-v1-design.md", days_old=30)
    run(store, "--apply")
    assert not (store / "designs" / "00777-ghost-v1-design.md").exists()
    assert "missing-prd" in manifest(store)


def test_stale_autopilot_and_root_log_ages(tmp_path):
    store = make_store(tmp_path)
    touch(store / "autopilot" / "old-report.md", days_old=20)
    touch(store / "autopilot" / "state.json", days_old=2)
    touch(store / "alice.log", days_old=10)
    touch(store / "fresh.log", days_old=1)
    touch(store / "notes-kept.md", days_old=200)
    run(store, "--apply")
    assert not (store / "autopilot" / "old-report.md").exists()
    assert (store / "autopilot" / "state.json").exists()
    assert not (store / "alice.log").exists()
    assert (store / "fresh.log").exists()
    assert (store / "notes-kept.md").exists()  # unclassified stays


def test_numbered_drain_workspace_dies_with_prd_and_dirs_pruned(tmp_path):
    store = make_store(tmp_path)
    touch(store / "prds" / "done" / "00014-overhaul.md")
    touch(store / "00014-drain-repo" / "tmp" / "a.md", days_old=10)
    touch(store / "00014-run-drain.sh", days_old=10)
    run(store, "--apply")
    assert not (store / "00014-drain-repo").exists()
    assert not (store / "00014-run-drain.sh").exists()


def test_dry_run_moves_nothing(tmp_path, capsys):
    store = make_store(tmp_path)
    touch(store / "prds" / "done" / "00042-foo.md")
    touch(store / "designs" / "00042-foo-v1-design.md")
    run(store)
    assert (store / "designs" / "00042-foo-v1-design.md").exists()
    assert not (store / gc.TRASH_DIR).exists()
    assert "DRY-RUN" in capsys.readouterr().out


def test_second_run_is_idempotent(tmp_path, capsys):
    store = make_store(tmp_path)
    touch(store / "prds" / "done" / "00042-foo.md")
    touch(store / "designs" / "00042-foo-v1-design.md")
    run(store, "--apply")
    capsys.readouterr()
    run(store, "--apply")
    assert "trash=0" in capsys.readouterr().out


def test_ledger_is_exempt_from_autopilot_age(tmp_path):
    store = make_store(tmp_path)
    touch(store / "autopilot" / "ledger" / "loop-metrics.jsonl", days_old=200)
    touch(store / "autopilot" / "old-report.md", days_old=20)
    run(store, "--apply")
    assert (store / "autopilot" / "ledger" / "loop-metrics.jsonl").exists()
    assert not (store / "autopilot" / "old-report.md").exists()


def test_trashed_review_verdicts_land_in_ledger(tmp_path):
    store = make_store(tmp_path)
    touch(store / "prds" / "done" / "00042-foo.md")
    review = store / "reviews" / "00042-foo-alice.md"
    touch(review)
    review.write_text("---\nreviewers: alice\n---\nVerdict: APPROVED\nTests: pass\n")
    ts = NOW - 10 * gc.DAY
    os.utime(review, (ts, ts))
    run(store, "--apply")
    assert not review.exists()
    row = (store / "autopilot" / "ledger" / "review-verdicts.jsonl").read_text()
    assert '"prd": "00042"' in row
    assert "APPROVED" in row
    assert '"reviewers": "alice"' in row


def test_review_without_verdict_trashes_without_ledger_row(tmp_path):
    store = make_store(tmp_path)
    touch(store / "prds" / "done" / "00042-foo.md")
    touch(store / "reviews" / "00042-notes.md", days_old=10)
    run(store, "--apply")
    assert not (store / "reviews" / "00042-notes.md").exists()
    assert not (store / "autopilot" / "ledger" / "review-verdicts.jsonl").exists()


# --- PRD 00082: four blind spots the 2026-07-14 manual audit caught ---

def test_root_stray_unnumbered_is_flagged_not_kept_silently(tmp_path, capsys):
    """Class 1: un-numbered root files (blake-*.md, probe scripts, test-run.log)
    must FLAG, not classify unclassified->keep. Root holds named keepers only."""
    store = make_store(tmp_path)
    touch(store / "blake-notes.md", days_old=10)
    touch(store / "probe.py", days_old=10)
    touch(store / "test-run.log", days_old=1)  # fresh: not yet stale-log
    touch(store / "project-capsule.md", days_old=200)  # keeper: never flagged
    run(store, "--apply")
    out = capsys.readouterr().out
    assert "FLAG (root-stray, kept): blake-notes.md" in out
    assert "FLAG (root-stray, kept): probe.py" in out
    assert "FLAG (root-stray, kept): test-run.log" in out
    assert "project-capsule.md" not in out  # keeper stays silent
    # flagged, never trashed
    assert (store / "blake-notes.md").exists()
    assert (store / "test-run.log").exists()


def test_done_linked_root_debris_trashes_when_past_min_age(tmp_path):
    """Class 2: numbered root debris tied to a DONE prd trashes once older than
    --min-age-days. The 2026-07-14 survivors survived only because the same-day
    manual sweep left them fresher than the guard (documented, not a bug)."""
    store = make_store(tmp_path)
    touch(store / "prds" / "done" / "00054-x.md", days_old=30)
    touch(store / "alice_00054_gate.py", days_old=20)  # old: trashes
    touch(store / "beta_00054_gate.py", days_old=1)    # fresh: guarded
    run(store, "--apply")
    assert not (store / "alice_00054_gate.py").exists()
    assert "done-linked\talice_00054_gate.py" in manifest(store)
    assert (store / "beta_00054_gate.py").exists()  # min-age guard, the July cause


def test_colliding_trash_names_get_dedupe_suffix(tmp_path):
    """Class 3: a name collision inside the day's batch gets a -N suffix, never a
    failed move. Two shapes: (A) the dest file already exists, (B) a parent
    component already exists as a FILE (the 2026-07-14 00017-drain-repo failure)."""
    store = make_store(tmp_path)
    batch = time.strftime("%Y-%m-%d")
    # Case A: dest file pre-exists in the batch
    pre = store / gc.TRASH_DIR / batch / "designs" / "00054-a-v1-design.md"
    pre.parent.mkdir(parents=True)
    pre.write_text("earlier")
    touch(store / "prds" / "done" / "00054-a.md")
    touch(store / "designs" / "00054-a-v1-design.md", days_old=10)
    # Case B: a parent path exists as a file, blocking the dir nest
    (store / gc.TRASH_DIR / batch / "00017-drain-repo").write_text("was a root file")
    touch(store / "prds" / "done" / "00017-x.md")
    touch(store / "00017-drain-repo" / "inner.py", days_old=10)
    run(store, "--apply")
    # A: original + suffixed sibling both present, source gone
    dests = sorted(p.name for p in (store / gc.TRASH_DIR / batch / "designs").iterdir())
    assert dests == ["00054-a-v1-design.md", "00054-a-v1-design.md-2"]
    assert not (store / "designs" / "00054-a-v1-design.md").exists()
    # B: the file-parent survives, the dir member lands under a suffixed dir
    assert (store / gc.TRASH_DIR / batch / "00017-drain-repo").is_file()
    assert (store / gc.TRASH_DIR / batch / "00017-drain-repo-2" / "inner.py").is_file()
    assert not (store / "00017-drain-repo").exists()
    mani = manifest(store)
    assert "00054-a-v1-design.md-2" in mani and "00017-drain-repo-2/inner.py" in mani


def test_autopilot_deferred_and_reports_age_out(tmp_path):
    """Class 4: autopilot/deferred/** and autopilot/reports/** age out under
    --autopilot-age-days like the rest of autopilot/**; ledger/** stays exempt."""
    store = make_store(tmp_path)
    touch(store / "autopilot" / "deferred" / "00099-old.json", days_old=15)
    touch(store / "autopilot" / "reports" / "old-report.md", days_old=15)
    touch(store / "autopilot" / "deferred" / "fresh.json", days_old=2)
    touch(store / "autopilot" / "ledger" / "loop-metrics.jsonl", days_old=200)
    run(store, "--apply")
    assert not (store / "autopilot" / "deferred" / "00099-old.json").exists()
    assert not (store / "autopilot" / "reports" / "old-report.md").exists()
    assert (store / "autopilot" / "deferred" / "fresh.json").exists()  # min-age
    assert (store / "autopilot" / "ledger" / "loop-metrics.jsonl").exists()  # exempt


def test_manifest_readers_tolerate_unknown_rule_tags(tmp_path):
    """A manual-sweep row (rule tag the script never emits) must not break the
    idempotent second run or empty_old_trash."""
    store = make_store(tmp_path)
    mani = store / gc.TRASH_DIR / "manifest.tsv"
    mani.parent.mkdir(parents=True)
    mani.write_text("2026-07-14\tmanual-sweep\tblake-x.md\t2026-07-14/blake-x.md\n")
    # a normal run appends without choking on the pre-existing unknown-tag row
    touch(store / "prds" / "done" / "00042-foo.md")
    touch(store / "designs" / "00042-foo-v1-design.md", days_old=10)
    assert run(store, "--apply") == 0
    assert "manual-sweep" in manifest(store)
    assert "done-linked" in manifest(store)


def test_empty_trash_ages_out_old_batches_only(tmp_path):
    store = make_store(tmp_path)
    old = store / gc.TRASH_DIR / "2020-01-01" / "x.md"
    old.parent.mkdir(parents=True)
    old.write_text("x")
    today = time.strftime("%Y-%m-%d", time.localtime(NOW))
    recent = store / gc.TRASH_DIR / today / "y.md"
    recent.parent.mkdir(parents=True)
    recent.write_text("y")
    run(store, "--apply")
    assert not (store / gc.TRASH_DIR / "2020-01-01").exists()
    assert recent.exists()
