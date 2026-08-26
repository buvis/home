"""
End-to-end behavioral tests for the survey brief generator (run.py).

All tests operate on real tmp-dir (git) repos and assert on the markdown brief
`run._survey` returns.  PRD 00138 retired the stored atlas: the brief is
ephemeral, so there is no atlas.json, no atlas.md, and no staleness flag to
assert on any more.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path.home() / ".claude" / "hooks"))
sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "survey" / "scripts"))

import run


# ---------------------------------------------------------------------------
# PRD-pinned constants — do NOT alter these strings
# ---------------------------------------------------------------------------

PRD_VALID_ERROR_STYLES = {"result", "exceptions", "mixed", "unknown"}

PRD_MD_SECTIONS = [
    "Where things live",
    "Naming conventions",
    "Error-handling style",
    "Existing implementations index",
    "Extension points",
]

TRUNCATION_FOOTER = "*brief truncated*"


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


@pytest.fixture()
def git_repo(tmp_path):
    """A fresh git repo with one committed Python file."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    return repo


def _section_body(content: str, header: str) -> str:
    """Return the text between `header` and the next ## heading (or EOF)."""
    start = content.find(f"## {header}")
    assert start != -1, f"Section '## {header}' not found in the brief"
    after = content.find("\n## ", start + 1)
    return content[start: after] if after != -1 else content[start:]


# ---------------------------------------------------------------------------
# R1: the brief is ephemeral — surveying writes nothing
# ---------------------------------------------------------------------------

def test_survey_writes_nothing_under_the_cartographer_tree(tmp_path, monkeypatch, capsys):
    """A full `main()` run must leave no cartographer store behind.

    This is the requirement PRD 00138 exists for: the map is generated and
    handed to the session, never stored. An implementation that writes an
    atlas.json, an atlas.md, or even an empty `projects/` dir fails here.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))

    prev = os.getcwd()
    try:
        os.chdir(repo)
        run.main()
    finally:
        os.chdir(prev)

    assert capsys.readouterr().out.strip(), "survey must print the brief to stdout"
    assert not (home / ".local" / "share" / "agents" / "cartographer").exists(), (
        "survey must not create anything under the cartographer tree"
    )


# ---------------------------------------------------------------------------
# Brief: error_style enum
# ---------------------------------------------------------------------------

def test_error_style_value_is_in_allowed_enum(git_repo):
    brief = run._survey(git_repo)
    match = re.search(r"Detected style: \*\*(\w+)\*\*", brief)
    assert match, f"brief must report a detected error style:\n{brief}"
    assert match.group(1) in PRD_VALID_ERROR_STYLES, \
        f"error_style {match.group(1)!r} must be one of {PRD_VALID_ERROR_STYLES}"


# ---------------------------------------------------------------------------
# Brief: naming structure
# ---------------------------------------------------------------------------

def test_naming_maps_layer_to_case_counts(git_repo):
    """Every naming line reports all three case counts for its layer."""
    section = _section_body(run._survey(git_repo), "Naming conventions")
    entries = [ln for ln in section.split("\n") if ln.startswith("- **")]
    assert entries, f"brief must list at least one layer's naming counts:\n{section}"
    for line in entries:
        assert re.match(
            r"^- \*\*[^*]+\*\*: \w+ \(camelCase=\d+, snake_case=\d+, PascalCase=\d+\)$",
            line,
        ), f"naming entry must carry all three case counts: {line!r}"


# ---------------------------------------------------------------------------
# Brief: size and sections
# ---------------------------------------------------------------------------

def test_brief_within_5120_byte_limit(git_repo):
    size = len(run._survey(git_repo).encode())
    assert size <= 5120, f"brief is {size} bytes, limit is 5120"


def test_brief_sections_present_in_correct_order(git_repo):
    content = run._survey(git_repo)
    positions = []
    for heading in PRD_MD_SECTIONS:
        pos = content.find(heading)
        assert pos != -1, f"Required section {heading!r} missing from the brief"
        positions.append(pos)
    assert positions == sorted(positions), "brief sections are not in the required order"


def test_brief_contains_real_surveyed_content(tmp_path):
    """Guard against the brief being rendered from an empty/default dict."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    (repo / "utils.py").write_text("def format_date(d):\n    return str(d)\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add utils"], cwd=repo, check=True, capture_output=True)

    content = run._survey(repo)
    assert len(content) > 300, \
        f"brief is suspiciously short ({len(content)} chars); likely rendered from empty data"


def test_survey_prints_the_brief_to_stdout(git_repo, capsys):
    """`main()` hands the brief to the session, not to a file."""
    prev = os.getcwd()
    try:
        os.chdir(git_repo)
        run.main()
    finally:
        os.chdir(prev)
    out = capsys.readouterr().out
    assert "## Where things live" in out, \
        f"main() must print the brief itself, not a status line:\n{out}"


# ---------------------------------------------------------------------------
# Truncation: >50 files per layer
# ---------------------------------------------------------------------------

def test_footer_visible_when_file_cap_hit(tmp_path):
    """Repo with >50 Python files: the truncation footer is visible in the brief."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)

    for i in range(60):
        (repo / f"mod_{i:03d}.py").write_text(f"def fn_{i}():\n    return {i}\n")

    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "many files"], cwd=repo, check=True, capture_output=True)

    md = run._survey(repo)
    assert TRUNCATION_FOOTER in md, \
        f"brief must contain the visible literal {TRUNCATION_FOOTER!r} when truncated"

    # Must not be hidden inside an HTML comment
    for segment in md.split("<!--"):
        if "-->" in segment:
            comment_body = segment.split("-->")[0]
            assert TRUNCATION_FOOTER not in comment_body, \
                f"{TRUNCATION_FOOTER} must not appear only inside an HTML comment"

    assert len(md.encode()) <= 5120, \
        f"brief must still be <=5120 bytes when truncated; got {len(md.encode())}"


# ---------------------------------------------------------------------------
# Truncation: byte budget exceeded (no per-layer file cap)
# ---------------------------------------------------------------------------

def test_small_repo_not_truncated(git_repo):
    """A small repo (brief well under 5120 bytes) must NOT carry the footer.

    Kills the always-truncate exploit: a correct _fit_to_budget returns content
    unchanged with was_truncated=False when it is under budget.
    """
    md = run._survey(git_repo)
    assert len(md.encode()) < 5120, (
        f"precondition failed: small git_repo brief is {len(md.encode())} bytes, "
        "expected well under 5120"
    )
    assert TRUNCATION_FOOTER not in md, (
        f"brief must NOT contain {TRUNCATION_FOOTER!r} for a small repo under the byte budget"
    )


def _repo_with_many_layers(tmp_path) -> Path:
    """A repo with 50 layers of 3 files each — over the byte budget, under the file cap."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)

    # The naming-conventions section alone emits ~60 bytes per layer; 50 layers
    # ~3000 bytes there plus "Where things live" and headers easily exceeds the
    # 5120-byte budget without any layer reaching the 50-file cap.
    for layer_idx in range(50):
        layer_dir = repo / f"layer_{layer_idx:02d}"
        layer_dir.mkdir()
        for file_idx in range(3):
            (layer_dir / f"module_{file_idx}.py").write_text(
                f"def function_in_layer_{layer_idx}_file_{file_idx}():\n    pass\n"
            )

    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "many layers"], cwd=repo, check=True, capture_output=True)
    return repo


def test_footer_present_when_byte_budget_exceeded(tmp_path):
    """The byte-budget truncation path fires independently of the file cap."""
    md = run._survey(_repo_with_many_layers(tmp_path))

    assert TRUNCATION_FOOTER in md, (
        f"brief must contain the visible literal {TRUNCATION_FOOTER!r} when byte budget exceeded"
    )
    assert len(md.encode()) <= 5120, (
        f"brief must still be <=5120 bytes after byte-budget truncation; got {len(md.encode())}"
    )


# A complete line the brief renderer can emit. Truncation must drop whole
# lines, so every surviving line (footer aside) must match one of these forms.
_COMPLETE_MD_LINE = re.compile(
    r"^(?:"
    r"|## .+"
    r"|Detected style: \*\*\w+\*\*"
    r"|- \*\*[^*]+\*\*: \d+ files"
    r"|- \*\*[^*]+\*\*: \w+ \(camelCase=\d+, snake_case=\d+, PascalCase=\d+\)"
    r"|- `[^`]+` \(\w+\) - .+:\d+"
    r"|_\([^)]+\)_"
    r"|_degraded: .+_"
    r")$"
)


def test_byte_budget_truncation_keeps_every_line_well_formed(tmp_path):
    """Per-section truncation must drop whole lines, never byte-chop mid-token.

    A raw UTF-8 byte slice cuts the rendered document at an arbitrary offset,
    leaving a final line cut mid-token (e.g. '- **layer_2'). Per-section
    truncation drops complete entries instead, so every surviving line stays a
    well-formed markdown line the renderer could have emitted.
    """
    md = run._survey(_repo_with_many_layers(tmp_path))

    # Precondition: this repo actually triggers truncation.
    assert TRUNCATION_FOOTER in md, "precondition: repo must exceed the 5120-byte budget"
    assert len(md.encode()) <= 5120

    body = md[: md.rindex(TRUNCATION_FOOTER)].rstrip("\n")
    for line in body.split("\n"):
        assert _COMPLETE_MD_LINE.match(line), (
            f"truncated brief has a line cut mid-token: {line!r}; per-section "
            "truncation must drop whole entries, not slice raw UTF-8 bytes"
        )

    # The highest-priority section must survive truncation.
    assert "## Where things live" in body, (
        "per-section truncation must keep the leading 'Where things live' section"
    )


# ---------------------------------------------------------------------------
# Tree-sitter symbol extraction + degraded gating
# ---------------------------------------------------------------------------

def test_degraded_not_reported_when_tree_sitter_available(git_repo):
    """The degraded note must be absent when tree-sitter is importable.

    Fails against an implementation that hardcodes degraded = True.
    """
    # try_import_tree_sitter is unpatched: tree_sitter_language_pack is installed.
    assert "_degraded:" not in run._survey(git_repo), \
        "brief must not claim a degraded run when tree-sitter is available"


def test_degraded_reported_when_tree_sitter_unavailable(git_repo, monkeypatch):
    """The degraded note appears exactly when tree-sitter cannot be imported."""
    monkeypatch.setattr(run, "try_import_tree_sitter", lambda: None)
    brief = run._survey(git_repo)
    assert "_degraded: tree-sitter unavailable" in brief, \
        f"brief must flag a degraded run when try_import_tree_sitter returns None:\n{brief}"


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
# Brief: implementations index uses file:line, not layer:line
# ---------------------------------------------------------------------------

def _make_repo_with_symbol(tmp_path, subdir: str, filename: str, symbol: str, line: int) -> tuple:
    """
    Create a git repo containing one Python file at `subdir/filename`.
    The file has `line - 1` blank lines then `def symbol():`.
    Returns (repo_path, relative_file_path).
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

    return repo, f"{subdir}/{filename}"


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

    Fails against a `layer:line` rendering: the bare layer directory (e.g.
    'handlers') must not be the only file reference; the actual filename
    (e.g. 'order_handler.py') must appear in the entry for the symbol.
    """
    repo, _rel_path = _make_repo_with_symbol(tmp_path, subdir, filename, symbol, sym_line)
    section = _section_body(run._survey(repo), "Existing implementations index")

    # The entry for this symbol must contain the actual filename
    assert filename in section, (
        f"the implementations index must reference the source file "
        f"'{filename}', not a bare layer name.\nSection:\n{section}"
    )

    # The line number must appear
    assert str(sym_line) in section, (
        f"the implementations index must include line number {sym_line} "
        f"for symbol '{symbol}'.\nSection:\n{section}"
    )

    # A bare layer-only reference (subdir + colon, no filename) must not be the
    # pattern used — the real path component must be the filename, not the dir.
    layer_only_pattern = f"{subdir}:{sym_line}"
    assert layer_only_pattern not in section, (
        f"the implementations index must not use the bare layer reference "
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

    section = _section_body(run._survey(repo), "Extension points")

    # The FULL nested path + line must be a single contiguous substring.
    full_path_ref = f"{subdir}/{filename}:{class_line}"
    assert full_path_ref in section, (
        f"extension points must contain the full nested path reference "
        f"'{full_path_ref}' as a contiguous substring. A layer/filename impl that "
        f"drops intermediate directories would fail this check.\nSection:\n{section}"
    )

    # The class-based extension point must appear in the section.
    assert class_name in section, (
        f"extension points must include the class/interface '{class_name}'."
        f"\nSection:\n{section}"
    )

    # The plain top-level function must NOT appear in the extension points section —
    # this confirms the kind filter (only interfaces/classes, not every function).
    assert plain_func not in section, (
        f"extension points must NOT include plain function '{plain_func}'; "
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

    repo, _rel_path = _make_repo_with_symbol(tmp_path, subdir, filename, symbol, sym_line)
    section = _section_body(run._survey(repo), "Existing implementations index")

    # The FULL nested path followed by the line number must appear as one contiguous
    # substring. Asserting directory and filename separately would allow an impl that
    # drops the intermediate 'domain/' segment (e.g. emitting core/aggregate_root.py)
    # to pass this test.
    full_path_ref = f"core/domain/aggregate_root.py:{sym_line}"
    assert full_path_ref in section, (
        f"the implementations index must contain the full path reference "
        f"'{full_path_ref}' as a contiguous substring. Asserting directory and filename "
        f"separately would allow a wrong impl (e.g. 'core/aggregate_root.py') to pass.\n"
        f"Section:\n{section}"
    )


def test_extracted_kinds_are_within_pinned_enum(git_repo):
    """Extracted kinds stay in the pinned enum AND expected symbols are present.

    The positive-content assertions ensure an extractor that returns [] (or
    drops the method) cannot pass this test by vacuous truth.
    """
    (git_repo / "extra.py").write_text(
        "class Box:\n"
        "    def open(self):\n"
        "        return 1\n"
    )
    syms = run._extract_file_symbols(git_repo / "extra.py")

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
