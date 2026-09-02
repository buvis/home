"""Tests for hooks/_echo_symbols.py — content reconstruction, tree-sitter
symbol extraction, and definition-aware match scoring for the Echo gate.

`hooks/` is on sys.path via the tests package (`tests/__init__.py`), so the
module imports by bare name; patches on shared objects go through monkeypatch.
"""

from __future__ import annotations

import types

import pytest

import _echo_symbols as symbols

# --- Extension helpers ---


def test_file_extension_lowercases_and_handles_missing_dot() -> None:
    assert symbols.file_extension("/p/Widget.PY") == ".py"
    assert symbols.file_extension("/p/Makefile") == ""
    assert symbols.file_extension("") == ""


def test_has_supported_extension_matches_the_language_map() -> None:
    assert symbols.has_supported_extension("/p/x.rs") is True
    assert symbols.has_supported_extension("/p/x.md") is False
    assert set(symbols._LANG_BY_EXT) == set(symbols.SUPPORTED_EXTENSIONS)


# --- Content reconstruction ---


def test_extract_content_multiedit() -> None:
    out = symbols.extract_content(
        "MultiEdit",
        {
            "edits": [
                {"new_string": "def foo(): pass"},
                {"new_string": "def bar(): pass"},
            ],
        },
    )
    assert "foo" in out and "bar" in out


def test_extract_content_unknown_tool_empty() -> None:
    assert symbols.extract_content("Unknown", {"content": "x"}) == ""


# --- Symbol extraction ---


@pytest.mark.parametrize(
    "ext, content, expected_subset",
    [
        (
            ".py",
            "def format_price():\n    pass\n\nclass Pricing:\n    def parse(self):\n        pass\n",
            {"format_price", "Pricing", "parse"},
        ),
        (
            ".ts",
            "export function formatPrice(): number { return 1; }\n"
            "export class Widget { parseAmount() {} normalize() {} }\n",
            {"formatPrice", "Widget", "parseAmount", "normalize"},
        ),
        (
            ".tsx",
            "function App() { return null; }\nclass Card { format() {} }\n",
            {"App", "Card", "format"},
        ),
        (
            ".js",
            "function transform(x) { return x; }\nclass Box { serialize() {} }\n",
            {"transform", "Box", "serialize"},
        ),
        (
            ".jsx",
            "function Hello() { return null; }\n",
            {"Hello"},
        ),
        (
            ".rs",
            "fn validate() {}\n"
            "struct Order { id: u32 }\n"
            "impl Order { fn parse(&self) {} }\n"
            "enum Status { Open, Closed }\n",
            {"validate", "parse", "Status"},
        ),
        (
            ".go",
            "package main\nfunc Format() {}\ntype Order struct{ ID int }\n",
            {"Format", "Order"},
        ),
    ],
)
def test_extract_symbols_per_language(
    ext: str,
    content: str,
    expected_subset: set[str],
) -> None:
    syms = set(symbols.extract_symbols(content, ext))
    missing = expected_subset - syms
    assert not missing, f"missing expected symbols for {ext}: {missing} (got {syms})"


def test_extract_symbols_unsupported_extension_returns_empty() -> None:
    assert symbols.extract_symbols("anything at all", ".md") == []
    assert symbols.extract_symbols("anything", ".unknown") == []


def test_extract_symbols_empty_content_returns_empty() -> None:
    assert symbols.extract_symbols("", ".py") == []


def test_extract_symbols_dedupes_preserving_order() -> None:
    content = "def foo():\n    pass\n\ndef foo():\n    pass\n\ndef bar():\n    pass\n"
    out = symbols.extract_symbols(content, ".py")
    assert out.count("foo") == 1
    assert out.index("foo") < out.index("bar")


def test_extract_symbols_anonymous_arrow_not_included() -> None:
    content = "const x = () => 1;\nfunction named() {}\n"
    syms = symbols.extract_symbols(content, ".js")
    assert "named" in syms
    # Anonymous functions (no identifier) must not contribute symbols.
    assert all(s and isinstance(s, str) for s in syms)


def test_extract_symbols_reads_dict_results_from_pack_1_16(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """tree-sitter-language-pack >= 1.16 returns `process()` results as a dict;
    older releases returned an object with attributes. Both shapes must yield
    the same symbols. Before the fix the dict shape silently produced []."""
    func = types.SimpleNamespace(kind="Function", name="format_price", children=[])
    typ = types.SimpleNamespace(kind="Type", name="Order")
    fake = types.SimpleNamespace(
        ProcessConfig=lambda **_kw: None,
        process=lambda _content, _config: {"structure": [func], "symbols": [typ]},
    )
    monkeypatch.setattr(symbols.lib, "try_import_tree_sitter", lambda: fake)
    out = symbols.extract_symbols("def format_price():\n    pass\n", ".py")
    assert out == ["format_price", "Order"]


def test_extract_symbols_parse_failure_audits_and_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A parser exception is recorded as `tree_sitter_parse_failed`, never raised."""

    def boom(_content, _config):
        raise ValueError("bad grammar")

    fake = types.SimpleNamespace(ProcessConfig=lambda **_kw: None, process=boom)
    monkeypatch.setattr(symbols.lib, "try_import_tree_sitter", lambda: fake)
    audit: list[dict] = []
    monkeypatch.setattr(symbols.lib, "append_audit", audit.append)
    assert symbols.extract_symbols("def x(): pass\n", ".py") == []
    assert audit and audit[0]["event"] == "tree_sitter_parse_failed"


# --- Match scoring ---


def test_score_match_strong_exact_token() -> None:
    cand = {"file": "u.py", "line": 1, "snippet": "def formatPrice(p):"}
    assert symbols.score_match("formatPrice", cand) == "strong"


def test_score_match_strong_distinguishes_substring() -> None:
    """Substring-only matches must NOT be classified as strong."""
    cand = {"file": "u.py", "line": 1, "snippet": "def formatPriceTag(p):"}
    assert symbols.score_match("formatPrice", cand) != "strong"


def test_score_match_medium_levenshtein_within_2() -> None:
    cand = {"file": "u.py", "line": 1, "snippet": "def formatPric(p):"}  # distance 1
    assert symbols.score_match("formatPrice", cand) == "medium"


def test_score_match_weak_long_substring_overlap() -> None:
    # The snippet shares the case-insensitive contiguous run "format" (6 chars).
    cand = {"file": "u.py", "line": 1, "snippet": "def priceformatter(p):"}
    assert symbols.score_match("formatPrice", cand) == "weak"


def test_score_match_none_when_no_overlap() -> None:
    cand = {"file": "u.py", "line": 1, "snippet": "def xyz(): return 1"}
    assert symbols.score_match("formatPrice", cand) is None


def test_decide_blocks_on_strong() -> None:
    groups = {
        "formatPrice": [{"file": "u.py", "line": 1, "snippet": "def formatPrice(p):"}],
    }
    decision, matches = symbols.decide(["formatPrice"], groups)
    assert decision == "deny"
    assert matches and matches[0]["score"] == "strong"
    assert matches[0]["symbol"] == "formatPrice"


def test_decide_blocks_on_medium() -> None:
    groups = {
        "formatPrice": [{"file": "u.py", "line": 1, "snippet": "def formatPric(p):"}],
    }
    decision, matches = symbols.decide(["formatPrice"], groups)
    assert decision == "deny"
    assert matches[0]["score"] == "medium"


def test_decide_allows_on_weak_only() -> None:
    groups = {
        "formatPrice": [
            {"file": "u.py", "line": 1, "snippet": "def priceformatter(p):"},
        ],
    }
    decision, matches = symbols.decide(["formatPrice"], groups)
    assert decision == "allow"
    # Weak matches are NOT included in deny matches list (which is for the envelope).
    assert matches == []


# --- Definition-aware matching: a usage site must NOT block (audit 2026-05) ---


def test_score_match_usage_site_not_strong() -> None:
    """A call/usage of the exact name is not a duplicate definition -> not blocking."""
    cand = {"file": "u.py", "line": 1, "snippet": "total = formatPrice(item)"}
    assert symbols.score_match("formatPrice", cand) != "strong"
    assert symbols.score_match("formatPrice", cand) != "medium"


def test_score_match_type_annotation_not_strong() -> None:
    """Exact name in a type position (e.g. `-> Result`) must not block."""
    cand = {"file": "u.rs", "line": 1, "snippet": "pub fn run() -> Result<(), Error> {"}
    assert symbols.score_match("Result", cand) != "strong"
    assert symbols.score_match("Result", cand) != "medium"


def test_score_match_strong_rust_fn() -> None:
    cand = {"file": "u.rs", "line": 1, "snippet": "pub fn formatPrice(p: i32) -> i32 {"}
    assert symbols.score_match("formatPrice", cand) == "strong"


def test_score_match_strong_go_method_receiver() -> None:
    cand = {
        "file": "u.go",
        "line": 1,
        "snippet": "func (s *Svc) formatPrice(p int) int {",
    }
    assert symbols.score_match("formatPrice", cand) == "strong"


def test_decide_allows_usage_site_only() -> None:
    groups = {
        "aggregate_query": [
            {
                "file": "a.rs",
                "line": 1,
                "snippet": "let rows = aggregate_query(&pool);",
            },
        ],
    }
    decision, matches = symbols.decide(["aggregate_query"], groups)
    assert decision == "allow"
    assert matches == []


def test_defined_name_extracts_declared_identifier() -> None:
    assert symbols._defined_name("def foo(x):") == "foo"
    assert symbols._defined_name("class Bar:") == "Bar"
    assert symbols._defined_name("pub fn baz() {") == "baz"
    assert symbols._defined_name("func (r *T) Qux() {") == "Qux"
    assert symbols._defined_name("    x = foo()") is None
    assert symbols._defined_name("return formatPrice(a)") is None


def test_decide_match_records_snippet() -> None:
    """Blocking matches carry the snippet so the audit log holds the evidence."""
    groups = {
        "formatPrice": [{"file": "u.py", "line": 1, "snippet": "def formatPrice(p):"}],
    }
    _decision, matches = symbols.decide(["formatPrice"], groups)
    assert matches[0]["snippet"] == "def formatPrice(p):"


def test_decide_match_snippet_capped() -> None:
    long_snippet = "def formatPrice(" + "x" * 500 + "):"
    groups = {"formatPrice": [{"file": "u.py", "line": 1, "snippet": long_snippet}]}
    _decision, matches = symbols.decide(["formatPrice"], groups)
    assert len(matches[0]["snippet"]) == symbols._SNIPPET_AUDIT_CAP
