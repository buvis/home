"""Tests for check_links.py (PRD 00081)."""
import json
import subprocess
import sys
from pathlib import Path

import check_links


def make_tree(root: Path) -> Path:
    dl = root / "dev/local"
    (dl / "prds/backlog").mkdir(parents=True)
    (dl / "prds/hold").mkdir()
    (dl / "discovery").mkdir()
    (dl / "notes").mkdir()
    (dl / ".trash/2026-01-01").mkdir(parents=True)
    (dl / "prds/backlog/00001-alpha-v1.md").write_text("# alpha\n")
    (dl / "prds/hold/00007-parked-v1.md").write_text("# parked\n")
    (dl / "discovery/00002-beta.md").write_text("# beta\n")
    (dl / "notes/real.md").write_text("# real\n")
    return dl


def scan(root, text, name="doc.md"):
    doc = root / "dev/local/notes" / name
    doc.write_text(text)
    findings, errors = check_links.run(root)
    return findings, errors


def test_resolving_references_are_clean(tmp_path):
    make_tree(tmp_path)
    findings, errors = scan(
        tmp_path,
        "see dev/local/notes/real.md and PRD 00001-alpha-v1.md, "
        "hold-parked 00007-parked-v1 counts too, discovery 00002-beta.md\n",
    )
    assert findings == [] and errors == []


def test_dangling_path_and_prd_reported_with_line(tmp_path):
    make_tree(tmp_path)
    findings, _ = scan(tmp_path, "gone: dev/local/notes/ghost.md\ncite 00099-nope-v1.md\n")
    targets = [f[2] for f in findings]
    assert "dev/local/notes/ghost.md" in targets
    assert any(t.startswith("00099-") for t in targets)
    # findings quote the citing line and carry file:line
    f = findings[0]
    assert f[1] == 1 and "ghost" in f[3]


def test_link_ok_waiver_exempts_the_line(tmp_path):
    make_tree(tmp_path)
    findings, _ = scan(
        tmp_path,
        "link-ok: dev/local/notes/removed.md was deleted on purpose\n"
        "but dev/local/notes/also-gone.md has no waiver\n",
    )
    assert len(findings) == 1
    assert findings[0][2] == "dev/local/notes/also-gone.md"


def test_memory_links_resolve_stem_and_frontmatter_name(tmp_path, monkeypatch):
    make_tree(tmp_path)
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "file-stem.md").write_text("---\nname: slug-name\n---\nbody\n")
    monkeypatch.setattr(check_links, "project_memory_dir", lambda _root: mem)
    findings, _ = scan(tmp_path, "[[file-stem]] [[slug-name]] [[ghost-memory]]\n")
    assert [f[2] for f in findings] == ["[[ghost-memory]] (no memory)"]


def test_memory_dir_scanned_as_source(tmp_path, monkeypatch):
    make_tree(tmp_path)
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "m.md").write_text("cites dev/local/notes/vanished.md\n")
    monkeypatch.setattr(check_links, "project_memory_dir", lambda _root: mem)
    findings, _ = check_links.run(tmp_path)
    assert any("vanished" in f[2] for f in findings)


def test_trash_and_placeholders_skipped(tmp_path):
    make_tree(tmp_path)
    (tmp_path / "dev/local/.trash/2026-01-01/old.md").write_text(
        "dev/local/notes/long-gone.md\n"
    )
    findings, _ = scan(
        tmp_path,
        "patterns dev/local/prds/*.md and dev/local/tmp/NNNNN-x.md and dev/local/... skip\n",
    )
    assert findings == []


def test_unreadable_file_is_a_scan_error(tmp_path):
    make_tree(tmp_path)
    bad = tmp_path / "dev/local/notes/locked.md"
    bad.write_text("secret\n")
    bad.chmod(0)
    try:
        findings, errors = check_links.run(tmp_path)
        assert len(errors) == 1 and "locked.md" in errors[0]
    finally:
        bad.chmod(0o644)


def test_cli_exit_codes_and_json(tmp_path):
    make_tree(tmp_path)
    script = Path(check_links.__file__)
    clean = subprocess.run(
        [sys.executable, str(script), "--root", str(tmp_path), "--json"],
        capture_output=True, text=True,
    )
    assert clean.returncode == 0
    assert json.loads(clean.stdout) == {"findings": [], "scan_errors": []}
    (tmp_path / "dev/local/notes/doc.md").write_text("dev/local/notes/ghost.md\n")
    dirty = subprocess.run(
        [sys.executable, str(script), "--root", str(tmp_path), "--json"],
        capture_output=True, text=True,
    )
    assert dirty.returncode == 1
    payload = json.loads(dirty.stdout)
    assert payload["findings"][0]["target"] == "dev/local/notes/ghost.md"
    assert payload["findings"][0]["citing_line"] == "dev/local/notes/ghost.md"
