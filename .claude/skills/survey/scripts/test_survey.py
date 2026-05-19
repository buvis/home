"""
End-to-end behavioral tests for the survey atlas generator (run.py).

All tests operate on real tmp-dir (git) repos and assert on the written
atlas.json / atlas.md.  No internal helpers are imported or patched.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path.home() / ".claude" / "hooks"))
sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "survey" / "scripts"))

import run


# ---------------------------------------------------------------------------
# PRD-pinned constants — do NOT alter these strings
# ---------------------------------------------------------------------------

PRD_REQUIRED_KEYS = {
    "surveyed_at", "layers", "forbidden_imports",
    "naming", "error_style", "dependency_edges",
}
PRD_OPTIONAL_KEYS = {"head_sha", "staleness", "[manual]", "truncated", "degraded"}
PRD_ALLOWED_KEYS = PRD_REQUIRED_KEYS | PRD_OPTIONAL_KEYS

PRD_LEGACY_KEYS = {"generated_at", "project_hash", "symbols", "naming_conventions", "error_handling"}

PRD_VALID_ERROR_STYLES = {"result", "exceptions", "mixed", "unknown"}

PRD_MD_SECTIONS = [
    "Where things live",
    "Naming conventions",
    "Error-handling style",
    "Existing implementations index",
    "Extension points",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init_git_repo(path: Path) -> str:
    """Init a git repo with one commit; return HEAD sha."""
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=path, check=True, capture_output=True)
    (path / "main.py").write_text("def hello():\n    return 'hello'\n")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _locate_atlas_json(home: Path) -> Path:
    paths = list((home / ".claude" / "cartographer" / "projects").glob("*/atlas.json"))
    assert len(paths) == 1, f"Expected exactly 1 atlas.json under {home}, found: {paths}"
    return paths[0]


def _locate_atlas_md(home: Path) -> Path:
    paths = list((home / ".claude" / "cartographer" / "projects").glob("*/atlas.md"))
    assert len(paths) == 1, f"Expected exactly 1 atlas.md under {home}, found: {paths}"
    return paths[0]


def _survey(repo: Path, home: Path, *, refresh: bool = False, if_missing: bool = False) -> None:
    prev = os.getcwd()
    try:
        os.chdir(repo)
        run.main(
            _args=argparse.Namespace(refresh=refresh, if_missing=if_missing),
            _home=home,
        )
    finally:
        os.chdir(prev)


@pytest.fixture()
def git_repo(tmp_path):
    """(repo_path, head_sha, home_path) for a fresh git repo."""
    repo = tmp_path / "repo"
    repo.mkdir()
    sha = _init_git_repo(repo)
    home = tmp_path / "home"
    home.mkdir()
    return repo, sha, home


# ---------------------------------------------------------------------------
# atlas.json: correct key set
# ---------------------------------------------------------------------------

def test_atlas_json_has_exact_prd_required_keys(git_repo):
    repo, _sha, home = git_repo
    _survey(repo, home)

    data = json.loads(_locate_atlas_json(home).read_text())
    actual = set(data.keys())
    assert PRD_REQUIRED_KEYS <= actual, f"Missing keys: {PRD_REQUIRED_KEYS - actual}"
    assert actual <= PRD_ALLOWED_KEYS, f"Unexpected keys: {actual - PRD_ALLOWED_KEYS}"


def test_atlas_json_contains_no_legacy_keys(git_repo):
    repo, _sha, home = git_repo
    _survey(repo, home)

    data = json.loads(_locate_atlas_json(home).read_text())
    found = set(data.keys()) & PRD_LEGACY_KEYS
    assert not found, f"Legacy keys present: {found}"


# ---------------------------------------------------------------------------
# atlas.json: surveyed_at
# ---------------------------------------------------------------------------

def test_surveyed_at_is_utc_iso8601_string(git_repo):
    repo, _sha, home = git_repo
    _survey(repo, home)

    ts = json.loads(_locate_atlas_json(home).read_text())["surveyed_at"]
    assert isinstance(ts, str)
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    assert dt.tzinfo is not None, "surveyed_at must include UTC timezone info"


# ---------------------------------------------------------------------------
# atlas.json: head_sha
# ---------------------------------------------------------------------------

def test_head_sha_equals_git_rev_parse_head(git_repo):
    repo, expected_sha, home = git_repo
    _survey(repo, home)

    data = json.loads(_locate_atlas_json(home).read_text())
    assert "head_sha" in data, "head_sha must be present for a git repo"
    assert data["head_sha"] == expected_sha


def test_head_sha_absent_for_non_git_directory(tmp_path):
    repo = tmp_path / "plain"
    repo.mkdir()
    (repo / "app.py").write_text("x = 1\n")
    home = tmp_path / "home"
    home.mkdir()
    _survey(repo, home)

    data = json.loads(_locate_atlas_json(home).read_text())
    assert "head_sha" not in data, "head_sha must be omitted for non-git directories"


# ---------------------------------------------------------------------------
# atlas.json: error_style enum
# ---------------------------------------------------------------------------

def test_error_style_value_is_in_allowed_enum(git_repo):
    repo, _sha, home = git_repo
    _survey(repo, home)

    style = json.loads(_locate_atlas_json(home).read_text())["error_style"]
    assert style in PRD_VALID_ERROR_STYLES, \
        f"error_style {style!r} must be one of {PRD_VALID_ERROR_STYLES}"


# ---------------------------------------------------------------------------
# atlas.json: naming structure
# ---------------------------------------------------------------------------

def test_naming_maps_layer_to_case_counts(git_repo):
    repo, _sha, home = git_repo
    _survey(repo, home)

    naming = json.loads(_locate_atlas_json(home).read_text())["naming"]
    assert isinstance(naming, dict)
    for layer, counts in naming.items():
        assert set(counts.keys()) == {"camelCase", "snake_case", "PascalCase"}, \
            f"naming[{layer!r}] must have exactly camelCase, snake_case, PascalCase"
        for k, v in counts.items():
            assert isinstance(v, int), f"naming[{layer!r}][{k!r}] must be int"


# ---------------------------------------------------------------------------
# atlas.md: both files created
# ---------------------------------------------------------------------------

def test_atlas_md_written_alongside_json(git_repo):
    repo, _sha, home = git_repo
    _survey(repo, home)
    assert _locate_atlas_md(home).exists()


# ---------------------------------------------------------------------------
# atlas.md: size and sections
# ---------------------------------------------------------------------------

def test_atlas_md_within_5120_byte_limit(git_repo):
    repo, _sha, home = git_repo
    _survey(repo, home)
    size = _locate_atlas_md(home).stat().st_size
    assert size <= 5120, f"atlas.md is {size} bytes, limit is 5120"


def test_atlas_md_sections_present_in_correct_order(git_repo):
    repo, _sha, home = git_repo
    _survey(repo, home)
    content = _locate_atlas_md(home).read_text()
    positions = []
    for heading in PRD_MD_SECTIONS:
        pos = content.find(heading)
        assert pos != -1, f"Required section {heading!r} missing from atlas.md"
        positions.append(pos)
    assert positions == sorted(positions), "atlas.md sections are not in the required order"


def test_atlas_md_contains_real_surveyed_content(tmp_path):
    """Guard against atlas.md being rendered from an empty/default dict."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    (repo / "utils.py").write_text("def format_date(d):\n    return str(d)\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add utils"], cwd=repo, check=True, capture_output=True)
    home = tmp_path / "home"
    home.mkdir()
    _survey(repo, home)
    content = _locate_atlas_md(home).read_text()
    assert len(content) > 300, \
        f"atlas.md is suspiciously short ({len(content)} chars); likely rendered from empty data"


# ---------------------------------------------------------------------------
# Atomic write: re-survey leaves a valid JSON file
# ---------------------------------------------------------------------------

def test_resurvey_produces_valid_json(git_repo):
    repo, _sha, home = git_repo
    _survey(repo, home)
    _survey(repo, home, refresh=True)
    data = json.loads(_locate_atlas_json(home).read_text())
    assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# [manual] block preserved across --refresh
# ---------------------------------------------------------------------------

def test_manual_block_preserved_on_resurvey(git_repo):
    repo, _sha, home = git_repo
    _survey(repo, home)

    atlas_path = _locate_atlas_json(home)
    data = json.loads(atlas_path.read_text())
    manual_payload = {"note": "keep this", "author": "bob"}
    data["[manual]"] = manual_payload
    atlas_path.write_text(json.dumps(data))

    _survey(repo, home, refresh=True)

    data2 = json.loads(_locate_atlas_json(home).read_text())
    assert "[manual]" in data2, "[manual] key must survive a --refresh re-survey"
    assert data2["[manual]"] == manual_payload, \
        f"[manual] content was altered: {data2['[manual]']!r}"


# ---------------------------------------------------------------------------
# --if-missing: no-op when atlas exists without staleness.flag
# ---------------------------------------------------------------------------

def test_if_missing_skips_existing_fresh_atlas(git_repo, capsys):
    repo, _sha, home = git_repo
    _survey(repo, home)
    atlas_path = _locate_atlas_json(home)
    mtime_before = atlas_path.stat().st_mtime

    _survey(repo, home, if_missing=True)

    assert atlas_path.stat().st_mtime == mtime_before, \
        "--if-missing must not rewrite atlas.json when it is fresh"
    out = capsys.readouterr().out
    assert out.strip(), "--if-missing skip must print an explicit skip reason to stdout"


def test_if_missing_surveys_when_atlas_absent(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    home = tmp_path / "home"
    home.mkdir()
    # No prior survey — atlas is absent
    _survey(repo, home, if_missing=True)
    assert _locate_atlas_json(home).exists(), \
        "--if-missing must create atlas.json when it does not yet exist"


# ---------------------------------------------------------------------------
# --if-missing: rebuilds when staleness.flag file is present on disk
# ---------------------------------------------------------------------------

def test_if_missing_rebuilds_when_staleness_flag_file_present(git_repo):
    repo, _sha, home = git_repo
    _survey(repo, home)
    atlas_path = _locate_atlas_json(home)
    flag_path = atlas_path.parent / "staleness.flag"

    # Create the empty marker file that signals the atlas is stale
    flag_path.touch()
    mtime_before = atlas_path.stat().st_mtime

    _survey(repo, home, if_missing=True)

    assert atlas_path.stat().st_mtime != mtime_before, \
        "--if-missing must rebuild atlas.json when staleness.flag is present"
    assert not flag_path.exists(), \
        "--if-missing must remove staleness.flag after a successful rebuild"


# ---------------------------------------------------------------------------
# --refresh: removes staleness.flag file on disk
# ---------------------------------------------------------------------------

def test_refresh_removes_staleness_flag_file(git_repo):
    repo, _sha, home = git_repo
    _survey(repo, home)
    atlas_path = _locate_atlas_json(home)
    flag_path = atlas_path.parent / "staleness.flag"

    flag_path.touch()

    _survey(repo, home, refresh=True)

    assert not flag_path.exists(), \
        "--refresh must remove staleness.flag after a successful rebuild"


# ---------------------------------------------------------------------------
# Bare invocation: no-op when atlas is fresh (no staleness.flag)
# ---------------------------------------------------------------------------

def test_bare_survey_is_a_noop_when_atlas_is_fresh(git_repo, capsys):
    """Bare /survey must not re-survey when atlas.json exists and staleness.flag is absent.

    A wrong implementation that always re-surveys would update surveyed_at,
    causing this test to fail.
    """
    repo, _sha, home = git_repo
    _survey(repo, home)
    capsys.readouterr()  # drain output from the first survey

    atlas_path = _locate_atlas_json(home)
    ts_before = json.loads(atlas_path.read_text())["surveyed_at"]

    _survey(repo, home)  # bare — no flags

    ts_after = json.loads(atlas_path.read_text())["surveyed_at"]
    assert ts_after == ts_before, \
        "bare /survey must not update surveyed_at when atlas is fresh (no staleness.flag)"

    out = capsys.readouterr().out
    assert out.strip(), "bare /survey skip must print an explicit skip reason to stdout"


def test_bare_survey_runs_when_staleness_flag_is_present(git_repo):
    """Bare /survey must re-survey when staleness.flag is present.

    A wrong implementation that skips unconditionally regardless of the flag
    would leave surveyed_at unchanged, causing this test to fail.
    """
    repo, _sha, home = git_repo
    _survey(repo, home)

    atlas_path = _locate_atlas_json(home)
    flag_path = atlas_path.parent / "staleness.flag"
    ts_before = json.loads(atlas_path.read_text())["surveyed_at"]
    flag_path.touch()

    _survey(repo, home)  # bare — staleness.flag present

    ts_after = json.loads(atlas_path.read_text())["surveyed_at"]
    assert ts_after != ts_before, \
        "bare /survey must re-survey (update surveyed_at) when staleness.flag is present"
    assert not flag_path.exists(), \
        "bare /survey must remove staleness.flag after a successful rebuild"


def test_bare_survey_runs_when_atlas_is_missing(tmp_path):
    """Bare /survey must run the survey when atlas.json does not exist.

    A wrong implementation that always skips would leave no atlas.json,
    causing _locate_atlas_json to raise.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    home = tmp_path / "home"
    home.mkdir()

    # No prior survey — atlas is absent
    _survey(repo, home)  # bare — no flags

    assert _locate_atlas_json(home).exists(), \
        "bare /survey must create atlas.json when it does not yet exist"


# ---------------------------------------------------------------------------
# --refresh: always re-surveys even on a fresh atlas
# ---------------------------------------------------------------------------

def test_refresh_resurveys_even_when_atlas_is_fresh(git_repo):
    """--refresh must re-survey regardless of whether atlas.json is fresh.

    A wrong implementation that honours the fresh-atlas skip for --refresh
    would leave surveyed_at unchanged, causing this test to fail.
    """
    repo, _sha, home = git_repo
    _survey(repo, home)

    atlas_path = _locate_atlas_json(home)
    flag_path = atlas_path.parent / "staleness.flag"
    # Ensure fresh: atlas exists, no staleness.flag
    assert not flag_path.exists(), "precondition: no staleness.flag after first survey"
    ts_before = json.loads(atlas_path.read_text())["surveyed_at"]

    _survey(repo, home, refresh=True)

    ts_after = json.loads(atlas_path.read_text())["surveyed_at"]
    assert ts_after != ts_before, \
        "--refresh must update surveyed_at even when the atlas was already fresh"


# ---------------------------------------------------------------------------
# Status line printed to stdout
# ---------------------------------------------------------------------------

def test_survey_prints_status_to_stdout(git_repo, capsys):
    repo, _sha, home = git_repo
    _survey(repo, home)
    out = capsys.readouterr().out
    assert out.strip(), "survey must print a status line to stdout"


# ---------------------------------------------------------------------------
# Truncation: >50 files per layer
# ---------------------------------------------------------------------------

def test_truncated_flag_set_and_footer_visible_when_cap_hit(tmp_path):
    """Repo with >50 Python files: truncated:true in JSON, *atlas truncated* visible in MD."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)

    for i in range(60):
        (repo / f"mod_{i:03d}.py").write_text(f"def fn_{i}():\n    return {i}\n")

    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "many files"], cwd=repo, check=True, capture_output=True)

    home = tmp_path / "home"
    home.mkdir()
    _survey(repo, home)

    data = json.loads(_locate_atlas_json(home).read_text())
    assert data.get("truncated") is True, \
        "atlas.json must have truncated:true when 50-file-per-layer cap is reached"

    md = _locate_atlas_md(home).read_text()
    assert "*atlas truncated*" in md, \
        "atlas.md must contain the visible literal '*atlas truncated*' when truncated"

    # Must not be hidden inside an HTML comment
    for segment in md.split("<!--"):
        if "-->" in segment:
            comment_body = segment.split("-->")[0]
            assert "*atlas truncated*" not in comment_body, \
                "*atlas truncated* must not appear only inside an HTML comment"

    assert len(md.encode()) <= 5120, \
        f"atlas.md must still be <=5120 bytes when truncated; got {len(md.encode())}"


# ---------------------------------------------------------------------------
# Truncation: atlas.md byte budget exceeded (no per-layer file cap)
# ---------------------------------------------------------------------------

def test_small_repo_not_truncated(git_repo):
    """A small repo (atlas.md well under 5120 bytes) must NOT be marked truncated.

    Kills the always-truncate exploit: a correct _fit_to_budget returns content
    unchanged with was_truncated=False when it is under budget.
    """
    repo, _sha, home = git_repo
    _survey(repo, home)

    data = json.loads(_locate_atlas_json(home).read_text())
    assert data.get("truncated") is not True, (
        "atlas.json must NOT have truncated:true for a small repo under the 5120-byte budget; "
        f"got truncated={data.get('truncated')!r}"
    )

    md = _locate_atlas_md(home).read_text()
    assert len(md.encode()) < 5120, (
        f"precondition failed: small git_repo atlas.md is {len(md.encode())} bytes, "
        "expected well under 5120"
    )
    assert "*atlas truncated*" not in md, (
        "atlas.md must NOT contain '*atlas truncated*' for a small repo under the byte budget"
    )


def test_truncated_flag_and_footer_when_byte_budget_exceeded(tmp_path):
    """Repo with many layers (each < 50 files) whose atlas.md exceeds 5120 bytes.

    This exercises the byte-budget truncation path (_fit_to_budget returns
    md_truncated=True) independently of the per-layer file cap.  Both
    atlas.json truncated:true and the visible *atlas truncated* footer must
    be present, and atlas.md must still be <=5120 bytes.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)

    # Create enough layers (each with a few files) to push atlas.md past 5120
    # bytes without hitting the 50-file-per-layer cap.  The naming-conventions
    # section alone emits ~60 bytes per layer; 50 layers ~ 3 000 bytes there
    # plus "Where things live" and headers easily exceeds the 5120-byte budget.
    for layer_idx in range(50):
        layer_dir = repo / f"layer_{layer_idx:02d}"
        layer_dir.mkdir()
        for file_idx in range(3):
            (layer_dir / f"module_{file_idx}.py").write_text(
                f"def function_in_layer_{layer_idx}_file_{file_idx}():\n    pass\n"
            )

    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "many layers"], cwd=repo, check=True, capture_output=True)

    home = tmp_path / "home"
    home.mkdir()
    _survey(repo, home)

    data = json.loads(_locate_atlas_json(home).read_text())
    assert data.get("truncated") is True, (
        "atlas.json must have truncated:true when atlas.md byte budget is exceeded"
    )

    md = _locate_atlas_md(home).read_text()
    assert "*atlas truncated*" in md, (
        "atlas.md must contain the visible literal '*atlas truncated*' when byte budget exceeded"
    )

    assert len(md.encode()) <= 5120, (
        f"atlas.md must still be <=5120 bytes after byte-budget truncation; got {len(md.encode())}"
    )


# ---------------------------------------------------------------------------
# Tree-sitter symbol extraction + degraded gating
# ---------------------------------------------------------------------------

def test_degraded_false_or_absent_when_tree_sitter_available(git_repo):
    """degraded must NOT be True when tree-sitter is importable.

    Fails against an implementation that hardcodes degraded = True.
    """
    repo, _sha, home = git_repo
    # try_import_tree_sitter is unpatched: tree_sitter_language_pack is installed.
    _survey(repo, home)

    data = json.loads(_locate_atlas_json(home).read_text())
    assert data.get("degraded") in (False, None), \
        f"degraded must be False/absent when tree-sitter is available, got {data.get('degraded')!r}"


def test_degraded_true_when_tree_sitter_unavailable(git_repo, monkeypatch):
    """degraded must be True exactly when tree-sitter cannot be imported."""
    repo, _sha, home = git_repo
    monkeypatch.setattr(run, "try_import_tree_sitter", lambda: None)
    _survey(repo, home)

    data = json.loads(_locate_atlas_json(home).read_text())
    assert data.get("degraded") is True, \
        "degraded must be True when try_import_tree_sitter returns None"


PINNED_KINDS = {"function", "class", "method", "type", "interface"}


# --- Python: indented method, kind 'method', computed line --------------------
# Each case: (class_name, method_name, leading_blank_lines). The class sits at
# line `blanks + 1`; the method at `blanks + 2`. Varying names AND blank-line
# count means no fixed if/else chain returning canned tuples can satisfy all
# cases — the expected line is computed from the input, never hardcoded.

@pytest.mark.parametrize(
    "class_name, method_name, blanks",
    [
        ("Service", "handle", 0),
        ("Repository", "find_by_id", 2),
        ("OrderBook", "settle", 5),
        ("Cache", "evict", 1),
    ],
)
def test_python_method_extracted_with_method_kind_and_computed_line(
    tmp_path, class_name, method_name, blanks
):
    """An indented method is extracted as kind 'method' at its real line.

    A naive ^def|^class regex misses indented methods and cannot tell method
    from function; a content-matching stub cannot enumerate these cases.
    """
    f = tmp_path / "svc.py"
    f.write_text(
        "\n" * blanks
        + f"class {class_name}:\n"
        + f"    def {method_name}(self, req):\n"
        + "        return req\n"
    )
    class_line = blanks + 1
    method_line = blanks + 2
    symbols = run._extract_file_symbols(f)

    assert (class_name, "class", class_line) in symbols, \
        f"class {class_name!r} must be kind 'class' at line {class_line}: {symbols}"
    assert (method_name, "method", method_line) in symbols, \
        f"method {method_name!r} must be kind 'method' at line {method_line}: {symbols}"


# --- Python: decorated function, extracted at its `def` line ------------------
# decorators is a tuple; the `def` sits at line `blanks + len(decorators) + 1`.

@pytest.mark.parametrize(
    "func_name, decorators, blanks",
    [
        ("fetch", ("@cache", "@retry(times=3)"), 0),
        ("load_config", ("@lru_cache",), 3),
        ("dispatch", ("@app.route('/x')", "@auth", "@trace"), 1),
        ("render", (), 4),
    ],
)
def test_python_decorated_function_extracted_at_def_line(
    tmp_path, func_name, decorators, blanks
):
    """A decorated function is extracted as a function at its `def` line.

    A regex anchored to ^def after decorator lines either misses it or reports
    the wrong line; the expected line is computed from blanks + decorator count.
    """
    f = tmp_path / "deco.py"
    f.write_text(
        "\n" * blanks
        + "".join(d + "\n" for d in decorators)
        + f"def {func_name}(url):\n"
        + "    return url\n"
    )
    def_line = blanks + len(decorators) + 1
    symbols = run._extract_file_symbols(f)

    assert (func_name, "function", def_line) in symbols, \
        f"function {func_name!r} must be kind 'function' at line {def_line}: {symbols}"


# --- TypeScript: interface, kind 'interface', computed line -------------------

@pytest.mark.parametrize(
    "iface_name, blanks",
    [
        ("User", 0),
        ("OrderRow", 2),
        ("ApiResponse", 5),
        ("Config", 1),
    ],
)
def test_typescript_interface_extracted_with_interface_kind(
    tmp_path, iface_name, blanks
):
    """A TypeScript interface is extracted with kind 'interface' at its line."""
    f = tmp_path / "model.ts"
    f.write_text(
        "\n" * blanks
        + f"export interface {iface_name} {{\n"
        + "  id: string;\n"
        + "}\n"
    )
    iface_line = blanks + 1
    symbols = run._extract_file_symbols(f)

    assert (iface_name, "interface", iface_line) in symbols, \
        f"TS interface {iface_name!r} must be kind 'interface' " \
        f"at line {iface_line}: {symbols}"


# --- Rust: trait + struct, pinned kinds, computed lines -----------------------
# trait at line `blanks + 1`; the struct follows the 3-line trait body plus one
# blank separator, at line `blanks + 5`.

@pytest.mark.parametrize(
    "trait_name, struct_name, blanks",
    [
        ("Greeter", "Robot", 0),
        ("Handler", "Server", 2),
        ("Codec", "GzipCodec", 4),
        ("Reader", "FileReader", 1),
    ],
)
def test_rust_struct_and_trait_extracted_with_pinned_kinds(
    tmp_path, trait_name, struct_name, blanks
):
    """Rust trait -> 'interface' and struct -> pinned enum, at computed lines.

    The kinds enum is {function, class, method, type, interface}; assert the
    extractor maps Rust constructs into that enum at the right lines.
    """
    f = tmp_path / "lib.rs"
    f.write_text(
        "\n" * blanks
        + f"pub trait {trait_name} {{\n"
        + "    fn greet(&self) -> String;\n"
        + "}\n"
        + "\n"
        + f"pub struct {struct_name};\n"
    )
    trait_line = blanks + 1
    struct_line = blanks + 5
    symbols = run._extract_file_symbols(f)
    kinds = {n: k for n, k, _ in symbols}
    lines = {n: ln for n, _, ln in symbols}

    assert trait_name in kinds, f"Rust trait {trait_name!r} not extracted: {symbols}"
    assert kinds[trait_name] == "interface", \
        f"Rust trait must be kind 'interface', got {kinds[trait_name]!r}"
    assert lines[trait_name] == trait_line, \
        f"trait {trait_name!r} must be at line {trait_line}, got {lines[trait_name]}"

    assert struct_name in kinds, f"Rust struct {struct_name!r} not extracted: {symbols}"
    assert kinds[struct_name] in ("type", "class"), \
        f"Rust struct kind must be in the pinned enum, got {kinds[struct_name]!r}"
    assert lines[struct_name] == struct_line, \
        f"struct {struct_name!r} must be at line {struct_line}, got {lines[struct_name]}"


# ---------------------------------------------------------------------------
# _extract_file_symbols: regex fallback when tree-sitter yields nothing
# ---------------------------------------------------------------------------

def test_regex_fallback_used_when_tree_sitter_extraction_returns_empty(
    tmp_path, monkeypatch
):
    """When tree-sitter is importable but _extract_tree_sitter yields no
    symbols for a file (e.g. a per-file parse failure), _extract_file_symbols
    must fall back to the regex extractor instead of dropping every symbol.
    """
    f = tmp_path / "svc.py"
    f.write_text("def handler(req):\n    return req\n")

    # tree-sitter stays importable, but extraction yields nothing for this file.
    monkeypatch.setattr(run, "_extract_tree_sitter", lambda *a, **k: [])

    symbols = run._extract_file_symbols(f)
    names = {n for n, _, _ in symbols}
    assert "handler" in names, (
        "regex fallback must recover symbols when tree-sitter extraction "
        f"returns empty; got {symbols}"
    )


# ---------------------------------------------------------------------------
# atlas.md: implementations index uses file:line, not layer:line
# ---------------------------------------------------------------------------

def _section_body(content: str, header: str) -> str:
    """Return the text between `header` and the next ## heading (or EOF)."""
    start = content.find(f"## {header}")
    assert start != -1, f"Section '## {header}' not found in atlas.md"
    after = content.find("\n## ", start + 1)
    return content[start: after] if after != -1 else content[start:]


def _make_repo_with_symbol(tmp_path, subdir: str, filename: str, symbol: str, line: int) -> tuple:
    """
    Create a git repo containing one Python file at `subdir/filename`.
    The file has `line - 1` blank lines then `def symbol():`.
    Returns (repo_path, home_path, relative_file_path).
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)

    layer_dir = repo / subdir
    layer_dir.mkdir(parents=True, exist_ok=True)

    src_file = layer_dir / filename
    src_file.write_text("\n" * (line - 1) + f"def {symbol}():\n    pass\n")

    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add symbol"], cwd=repo, check=True, capture_output=True)

    home = tmp_path / "home"
    home.mkdir()
    return repo, home, f"{subdir}/{filename}"


@pytest.mark.parametrize(
    "subdir, filename, symbol, sym_line",
    [
        ("handlers", "order_handler.py", "process_order", 3),
        ("services", "user_svc.py", "create_user", 5),
    ],
)
def test_implementations_index_uses_file_path_not_layer_name(
    tmp_path, subdir, filename, symbol, sym_line
):
    """Implementations index must show the source file path, not a bare layer name.

    Fails against the current `layer:line` rendering: the bare layer directory
    (e.g. 'handlers') must not be the only file reference; the actual filename
    (e.g. 'order_handler.py') must appear in the entry for the symbol.
    """
    repo, home, rel_path = _make_repo_with_symbol(tmp_path, subdir, filename, symbol, sym_line)
    _survey(repo, home)

    content = _locate_atlas_md(home).read_text()
    section = _section_body(content, "Existing implementations index")

    # The entry for this symbol must contain the actual filename
    assert filename in section, (
        f"atlas.md implementations index must reference the source file "
        f"'{filename}', not a bare layer name.\nSection:\n{section}"
    )

    # The line number must appear
    assert str(sym_line) in section, (
        f"atlas.md implementations index must include line number {sym_line} "
        f"for symbol '{symbol}'.\nSection:\n{section}"
    )

    # A bare layer-only reference (subdir + colon, no filename) must not be
    # the pattern used — the real path component must be the filename, not the dir.
    # We check that the filename itself (not just the directory) is present,
    # which the assertion above already covers.  Additionally assert no entry
    # looks like "`symbol` (function) - subdir:line" (layer-only format).
    layer_only_pattern = f"{subdir}:{sym_line}"
    assert layer_only_pattern not in section, (
        f"atlas.md implementations index must not use the bare layer reference "
        f"'{layer_only_pattern}'; it must show the actual file path.\nSection:\n{section}"
    )


@pytest.mark.parametrize(
    "subdir, filename, class_name, class_line, plain_func, func_line",
    [
        ("ports/payment", "payment_port.py", "PaymentPort", 1, "helper_util", 5),
        ("adapters/email", "email_adapter.py", "EmailAdapter", 1, "build_headers", 5),
    ],
)
def test_extension_points_uses_file_path_not_layer_name(
    tmp_path, subdir, filename, class_name, class_line, plain_func, func_line
):
    """Extension points section: full file path shown and kind filter enforced.

    Two requirements in one fixture:
    1. The FULL nested relative path (e.g. ports/payment/payment_port.py:1) must
       appear as one contiguous substring — not just the filename alone, which would
       allow a layer/filename impl (dropping intermediate dirs) to pass.
    2. A class-based extension point IS present in the section; a plain top-level
       function in the same file is NOT — confirming the kind filter (interface/class
       only, not every function).
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)

    layer_dir = repo / subdir
    layer_dir.mkdir(parents=True, exist_ok=True)

    src_file = layer_dir / filename
    # class at line 1, plain function at line 5 (3 blank lines of separation)
    src_file.write_text(
        f"class {class_name}:\n"
        "    pass\n"
        "\n"
        "\n"
        f"def {plain_func}():\n"
        "    pass\n"
    )

    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add ext point"], cwd=repo, check=True, capture_output=True)

    home = tmp_path / "home"
    home.mkdir()
    _survey(repo, home)

    content = _locate_atlas_md(home).read_text()
    section = _section_body(content, "Extension points")

    # The FULL nested path + line must be a single contiguous substring.
    full_path_ref = f"{subdir}/{filename}:{class_line}"
    assert full_path_ref in section, (
        f"atlas.md extension points must contain the full nested path reference "
        f"'{full_path_ref}' as a contiguous substring. A layer/filename impl that "
        f"drops intermediate directories would fail this check.\nSection:\n{section}"
    )

    # The class-based extension point must appear in the section.
    assert class_name in section, (
        f"atlas.md extension points must include the class/interface '{class_name}'."
        f"\nSection:\n{section}"
    )

    # The plain top-level function must NOT appear in the extension points section —
    # this confirms the kind filter (only interfaces/classes, not every function).
    assert plain_func not in section, (
        f"atlas.md extension points must NOT include plain function '{plain_func}'; "
        f"extension points are for interfaces/abstractions, not every function."
        f"\nSection:\n{section}"
    )


def test_implementations_index_file_path_includes_relative_directory(tmp_path):
    """The file reference in the implementations index must be the full relative path.

    Uses a file nested two levels deep (core/domain/aggregate_root.py) so an impl
    that drops intermediate directories (emitting core/aggregate_root.py) also fails.
    The complete path must appear as one contiguous substring, not directory and
    filename asserted separately.
    """
    subdir = "core/domain"
    filename = "aggregate_root.py"
    symbol = "apply_event"
    sym_line = 6

    repo, home, rel_path = _make_repo_with_symbol(tmp_path, subdir, filename, symbol, sym_line)
    _survey(repo, home)

    content = _locate_atlas_md(home).read_text()
    section = _section_body(content, "Existing implementations index")

    # The FULL nested path followed by the line number must appear as one contiguous
    # substring. Asserting directory and filename separately would allow an impl that
    # drops the intermediate 'domain/' segment (e.g. emitting core/aggregate_root.py)
    # to pass this test.
    full_path_ref = f"core/domain/aggregate_root.py:{sym_line}"
    assert full_path_ref in section, (
        f"atlas.md implementations index must contain the full path reference "
        f"'{full_path_ref}' as a contiguous substring. Asserting directory and filename "
        f"separately would allow a wrong impl (e.g. 'core/aggregate_root.py') to pass.\n"
        f"Section:\n{section}"
    )


def test_extracted_kinds_are_within_pinned_enum(git_repo):
    """Extracted kinds stay in the pinned enum AND expected symbols are present.

    The positive-content assertions ensure an extractor that returns [] (or
    drops the method) cannot pass this test by vacuous truth.
    """
    repo, _sha, home = git_repo
    (repo / "extra.py").write_text(
        "class Box:\n"
        "    def open(self):\n"
        "        return 1\n"
    )
    syms = run._extract_file_symbols(repo / "extra.py")

    for name, kind, line in syms:
        assert kind in PINNED_KINDS, \
            f"symbol {name!r} has kind {kind!r} not in {PINNED_KINDS}"
        assert isinstance(line, int) and line >= 1, \
            f"symbol {name!r} has invalid line number {line!r}"

    assert ("Box", "class", 1) in syms, \
        f"expected class 'Box' at line 1 to be extracted: {syms}"
    assert ("open", "method", 2) in syms, \
        f"expected method 'open' at line 2 to be extracted: {syms}"


# ---------------------------------------------------------------------------
# _compute_dep_edges: import-only matching
# ---------------------------------------------------------------------------

def test_dep_edges_absent_when_other_layer_named_only_in_comment(tmp_path):
    """A file that mentions another layer only in a comment must NOT produce a dep edge.

    A wrong impl that does bare-word search on the full file text would find the
    layer name inside the comment and emit a spurious edge — this test catches that.
    """
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    db_dir = tmp_path / "db"
    db_dir.mkdir()

    # "db" appears only in a comment and a string literal — no import
    (ui_dir / "view.py").write_text(
        "# TODO: do not import from db directly\n"
        "x = 'the db layer is off-limits'\n"
        "def render():\n"
        "    return None\n"
    )
    (db_dir / "models.py").write_text("def query(): pass\n")

    layers = {"ui": [ui_dir / "view.py"], "db": [db_dir / "models.py"]}
    edges = run._compute_dep_edges(layers)

    ui_to_db = [e for e in edges if e["from_layer"] == "ui" and e["to_layer"] == "db"]
    assert not ui_to_db, (
        "dep edge ui->db must NOT be produced when 'db' appears only in a comment/string; "
        f"got edges: {edges}"
    )


def test_dep_edges_present_when_file_imports_other_layer(tmp_path):
    """A file that imports from another layer MUST produce a dep edge to that layer.

    A wrong impl that strips all edges (or only matches bare-word occurrences
    outside imports) would return no edges and fail this test.
    """
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    db_dir = tmp_path / "db"
    db_dir.mkdir()

    # Actual Python import of the "db" layer
    (ui_dir / "view.py").write_text(
        "from db import models\n"
        "\n"
        "def render():\n"
        "    return models.query()\n"
    )
    (db_dir / "models.py").write_text("def query(): pass\n")

    layers = {"ui": [ui_dir / "view.py"], "db": [db_dir / "models.py"]}
    edges = run._compute_dep_edges(layers)

    ui_to_db = [e for e in edges if e["from_layer"] == "ui" and e["to_layer"] == "db"]
    assert ui_to_db, (
        "dep edge ui->db must be produced when ui/view.py imports from 'db'; "
        f"got edges: {edges}"
    )
    assert ui_to_db[0]["count"] >= 1, (
        f"dep edge ui->db count must be >= 1, got {ui_to_db[0]['count']}"
    )


def test_dep_edges_absent_when_import_targets_different_layer(tmp_path):
    """Only imports whose path matches the layer name should produce an edge.

    Guards against an impl that fires on any import line regardless of target.
    'ui' imports 'services', not 'db' — no ui->db edge must appear.
    """
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    svc_dir = tmp_path / "services"
    svc_dir.mkdir()

    (ui_dir / "view.py").write_text(
        "import services\n"
        "# db is mentioned here but not imported\n"
        "def render():\n"
        "    return services.get()\n"
    )
    (db_dir / "models.py").write_text("def query(): pass\n")
    (svc_dir / "api.py").write_text("def get(): pass\n")

    layers = {
        "ui": [ui_dir / "view.py"],
        "db": [db_dir / "models.py"],
        "services": [svc_dir / "api.py"],
    }
    edges = run._compute_dep_edges(layers)

    ui_to_db = [e for e in edges if e["from_layer"] == "ui" and e["to_layer"] == "db"]
    assert not ui_to_db, (
        "dep edge ui->db must NOT appear when ui only imports 'services', not 'db'; "
        f"got edges: {edges}"
    )
    ui_to_svc = [e for e in edges if e["from_layer"] == "ui" and e["to_layer"] == "services"]
    assert ui_to_svc, (
        "dep edge ui->services must be present since ui imports 'services'; "
        f"got edges: {edges}"
    )


# ---------------------------------------------------------------------------
# _compute_dep_edges: import-block matching, not bare line-leading strings
# ---------------------------------------------------------------------------

def test_dep_edges_absent_for_line_leading_string_outside_import(tmp_path):
    """A line-leading quoted string naming a layer (e.g. a list entry
    "db/replica",) outside any import block must NOT produce a dep edge.

    The Go import-block alternative of _import_pattern previously matched any
    line-leading string literal containing a layer name, not only entries
    inside an `import (...)` block — emitting spurious edges.
    """
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    db_dir = tmp_path / "db"
    db_dir.mkdir()

    # "db/replica" is a line-leading string in a slice literal, not an import.
    (ui_dir / "routes.go").write_text(
        "package ui\n"
        "\n"
        "var paths = []string{\n"
        '\t"db/replica",\n'
        '\t"cache/local",\n'
        "}\n"
    )
    (db_dir / "models.go").write_text("package db\n")

    layers = {"ui": [ui_dir / "routes.go"], "db": [db_dir / "models.go"]}
    edges = run._compute_dep_edges(layers)

    ui_to_db = [e for e in edges if e["from_layer"] == "ui" and e["to_layer"] == "db"]
    assert not ui_to_db, (
        "dep edge ui->db must NOT be produced from a line-leading string literal "
        f"outside an import block; got edges: {edges}"
    )


def test_dep_edges_present_for_go_grouped_import_block(tmp_path):
    """A Go file importing another layer inside an `import (...)` block MUST
    still produce a dep edge — restricting to import blocks must not break
    grouped-import matching."""
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    db_dir = tmp_path / "db"
    db_dir.mkdir()

    (ui_dir / "view.go").write_text(
        "package ui\n"
        "\n"
        "import (\n"
        '\t"fmt"\n'
        '\t"myrepo/db"\n'
        ")\n"
    )
    (db_dir / "models.go").write_text("package db\n")

    layers = {"ui": [ui_dir / "view.go"], "db": [db_dir / "models.go"]}
    edges = run._compute_dep_edges(layers)

    ui_to_db = [e for e in edges if e["from_layer"] == "ui" and e["to_layer"] == "db"]
    assert ui_to_db, (
        "dep edge ui->db must be produced for a Go grouped import of 'db'; "
        f"got edges: {edges}"
    )


# ---------------------------------------------------------------------------
# _compute_dep_edges: non-Python import syntax (Gap 1)
# ---------------------------------------------------------------------------

def test_dep_edges_present_for_rust_use_statement(tmp_path):
    """A Rust file using `use db::models;` MUST produce a dep edge to the 'db' layer.

    A wrong impl that only scans Python `import`/`from` lines would miss Rust
    `use` syntax and return no edges — this test forces non-Python import handling.
    """
    api_dir = tmp_path / "api"
    api_dir.mkdir()
    db_dir = tmp_path / "db"
    db_dir.mkdir()

    (api_dir / "handler.rs").write_text(
        "use db::models;\n"
        "\n"
        "pub fn handle() -> db::models::User {\n"
        "    db::models::User::default()\n"
        "}\n"
    )
    (db_dir / "models.rs").write_text("pub struct User;\n")

    layers = {"api": [api_dir / "handler.rs"], "db": [db_dir / "models.rs"]}
    edges = run._compute_dep_edges(layers)

    api_to_db = [e for e in edges if e["from_layer"] == "api" and e["to_layer"] == "db"]
    assert api_to_db, (
        "dep edge api->db must be produced when api/handler.rs uses `use db::models;`; "
        f"got edges: {edges}"
    )
    assert api_to_db[0]["count"] >= 1, (
        f"dep edge api->db count must be >= 1, got {api_to_db[0]['count']}"
    )


# ---------------------------------------------------------------------------
# _compute_error_style: Go support
# ---------------------------------------------------------------------------

def test_go_idiomatic_error_handling_classifies_as_result(tmp_path):
    """A Go-only repo using idiomatic if-err-nil style must classify as 'result'.

    A wrong impl with no Go branch returns 'unknown' — this test catches that.
    Returning 'mixed' or 'exceptions' would also fail.
    """
    go_dir = tmp_path / "cmd"
    go_dir.mkdir()

    (go_dir / "main.go").write_text(
        'package main\n\n'
        'import (\n'
        '    "errors"\n'
        '    "fmt"\n'
        ')\n\n'
        'func run() error {\n'
        '    if err := doWork(); err != nil {\n'
        '        return fmt.Errorf("run failed: %w", err)\n'
        '    }\n'
        '    return nil\n'
        '}\n\n'
        'func doWork() error {\n'
        '    if false {\n'
        '        return errors.New("something went wrong")\n'
        '    }\n'
        '    if err := validate(); err != nil {\n'
        '        return err\n'
        '    }\n'
        '    return nil\n'
        '}\n\n'
        'func validate() error { return nil }\n'
    )

    layers = {"cmd": [go_dir / "main.go"]}
    style = run._compute_error_style(layers)

    assert style == "result", (
        f"Go-only repo with idiomatic if-err-nil / errors.New / fmt.Errorf must classify "
        f"as 'result', got {style!r}. A missing Go branch returns 'unknown'."
    )


def test_go_panic_error_handling_classifies_as_exceptions(tmp_path):
    """A Go-only repo using panic() for errors (no if-err-nil) must classify as 'exceptions'.

    A wrong impl that returns 'result' whenever the substring 'err' appears
    (even in a comment) would fail here — the word 'err' exists only in a comment,
    while the actual error handling is panic-style.
    """
    go_dir = tmp_path / "cmd"
    go_dir.mkdir()

    (go_dir / "main.go").write_text(
        'package main\n\n'
        '// Note: we do not use err return values here; panics signal failure.\n'
        'func mustOpen(path string) []byte {\n'
        '    data, ok := readFile(path)\n'
        '    if !ok {\n'
        '        panic("failed to open " + path)\n'
        '    }\n'
        '    return data\n'
        '}\n\n'
        'func readFile(path string) ([]byte, bool) {\n'
        '    if path == "" {\n'
        '        return nil, false\n'
        '    }\n'
        '    return []byte(path), true\n'
        '}\n'
    )

    layers = {"cmd": [go_dir / "main.go"]}
    style = run._compute_error_style(layers)

    assert style == "exceptions", (
        f"Go-only repo that uses panic() (no if-err-nil, 'err' only in a comment) "
        f"must classify as 'exceptions', got {style!r}. "
        f"A wrong impl keying on bare 'err' substring would return 'result'."
    )
