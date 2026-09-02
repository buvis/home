"""Symbol extraction and match scoring for the Echo duplicate-detection gate.

Extracted from `cartographer-echo.py` (`# --- content reconstruction & symbol
extraction ---` and `# --- match scoring ---`, PRD 00158): reconstruct the
content a write tool is about to land, pull the defined symbol names out of it
with tree-sitter, and classify ripgrep candidates against those symbols. The
extension helpers live here because the language map does.

Stdlib only; `tree_sitter_language_pack` reached lazily through
`_lib_cartographer.try_import_tree_sitter`. Python 3.10+.
"""

from __future__ import annotations

import re

import _lib_cartographer as lib

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go"},
)

# Map dotted extension -> tree_sitter_language_pack language name. `.jsx`
# uses the javascript grammar (no dedicated jsx grammar in the pack).
_LANG_BY_EXT: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".rs": "rust",
    ".go": "go",
}

# StructureItem kinds we treat as name-bearing symbols worth duplicate-
# checking. `process()` returns kinds as enums whose `str()` is the variant
# name (e.g. "Function", "Method"). Compare via string.
_SYMBOL_KINDS: frozenset[str] = frozenset(
    {"Function", "Method", "Class", "Struct", "Enum", "Type", "Trait", "Interface"},
)


def file_extension(file_path: str) -> str:
    """Return the dotted extension (`.py`, `.ts`, …) or `""` if none."""
    if not file_path:
        return ""
    name = file_path.replace("\\", "/").rsplit("/", 1)[-1]
    if "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[-1].lower()


def has_supported_extension(file_path: str) -> bool:
    return file_extension(file_path) in SUPPORTED_EXTENSIONS


# --- content reconstruction & symbol extraction ---


def extract_content(tool_name: str, tool_input: dict) -> str:
    """Best-effort assembly of the new content to scan.

    Write: `content` directly.
    Edit: `new_string` (treats the diff fragment as the scan target; this
    intentionally over-scans for the substring being added, which keeps
    Echo's symbol coverage on small edits).
    MultiEdit: concatenate all `new_string` values.
    """
    if tool_name == "Write":
        c = tool_input.get("content")
        return c if isinstance(c, str) else ""
    if tool_name == "Edit":
        ns = tool_input.get("new_string")
        return ns if isinstance(ns, str) else ""
    if tool_name == "MultiEdit":
        edits = tool_input.get("edits")
        if isinstance(edits, list):
            parts = []
            for ed in edits:
                if isinstance(ed, dict):
                    ns = ed.get("new_string")
                    if isinstance(ns, str):
                        parts.append(ns)
            return "\n".join(parts)
    return ""


def _walk_structure(
    items,
    kinds: frozenset[str],
    collected: list[str],
    seen: set[str],
) -> None:
    """Depth-first walk over `process(...).structure`, collecting named items.

    Anonymous items (`name is None` or empty) are skipped — they cannot be
    matched as duplicates by name. De-dup preserves first-seen order.
    """
    if not items:
        return
    for it in items:
        name = getattr(it, "name", None)
        kind = str(getattr(it, "kind", ""))
        if name and kind in kinds and name not in seen:
            seen.add(name)
            collected.append(name)
        children = getattr(it, "children", None)
        if children:
            _walk_structure(children, kinds, collected, seen)


def extract_symbols(content: str, ext: str) -> list[str]:
    """Extract defined symbol names from `content` for the given extension.

    Returns [] when the extension is unsupported, content is empty, the
    tree-sitter pack is unavailable, or parsing fails. Never raises.
    """
    if not content:
        return []
    lang = _LANG_BY_EXT.get(ext.lower())
    if lang is None:
        return []
    mod = lib.try_import_tree_sitter()
    if mod is None:
        return []
    try:
        config = mod.ProcessConfig(language=lang, symbols=True, structure=True)
        result = mod.process(content, config)
    except Exception as exc:
        # Deliberately broad: the parser is third-party code and fails on
        # syntactically invalid content; record a warn and treat as no symbols
        # (the host write proceeds).
        lib.append_audit(
            {"event": "tree_sitter_parse_failed", "language": lang, "error": str(exc)},
        )
        return []

    # tree-sitter-language-pack >= 1.16 returns a dict; older releases an object.
    if isinstance(result, dict):
        structure, symbols = result.get("structure"), result.get("symbols")
    else:
        structure = getattr(result, "structure", None)
        symbols = getattr(result, "symbols", None)

    collected: list[str] = []
    seen: set[str] = set()
    _walk_structure(structure or [], _SYMBOL_KINDS, collected, seen)
    # Also merge in top-level `symbols` (some grammars — e.g. go's
    # `type` declarations — surface only here, not in `structure`).
    for s in symbols or []:
        name = getattr(s, "name", None)
        kind = str(getattr(s, "kind", ""))
        if name and kind in _SYMBOL_KINDS and name not in seen:
            seen.add(name)
            collected.append(name)
    return collected


# --- match scoring ---

_LEVENSHTEIN_MEDIUM: int = 2
_WEAK_OVERLAP_MIN: int = 6
_SNIPPET_AUDIT_CAP: int = 200  # max chars of candidate snippet stored per match

# A blocking (strong/medium) match requires the candidate snippet to DEFINE a
# same- or near-named symbol, not merely mention it. Without this gate every
# usage site (`-> Result`, `create(x)`, a type annotation) scores "strong" and
# denies; the 2026-05 audit showed those denies were overridden ~99% of the
# time. Captures the declared identifier after a definition keyword, allowing
# leading visibility/async modifiers and an optional Go method receiver.
_DEF_NAME_RE = re.compile(
    r"^\s*"
    r"(?:export\s+|default\s+|pub(?:\([^)]*\))?\s+|public\s+|private\s+"
    r"|protected\s+|static\s+|async\s+|abstract\s+|final\s+|unsafe\s+)*"
    r"(?:def|class|fn|func|struct|enum|trait|interface|type|union|function"
    r"|const|let|var)\b"
    r"(?:\s+\([^)]*\))?"  # optional Go method receiver: func (r *T) Name
    r"\s+([A-Za-z_]\w*)",
)


def _defined_name(snippet: str) -> str | None:
    """Return the identifier a snippet defines, or None if it is not a definition."""
    match = _DEF_NAME_RE.match(snippet)
    return match.group(1) if match else None


def _levenshtein(a: str, b: str) -> int:
    """Classic DP Levenshtein distance. O(len(a)*len(b)) time, O(min) space."""
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]


def _longest_common_substring_len(a: str, b: str) -> int:
    """Return the length of the longest common contiguous substring (case-insensitive)."""
    a, b = a.lower(), b.lower()
    if not a or not b:
        return 0
    # DP table is `len(b)+1` wide per row; track only previous row.
    prev = [0] * (len(b) + 1)
    best = 0
    for ca in a:
        curr = [0] * (len(b) + 1)
        for j, cb in enumerate(b, 1):
            if ca == cb:
                curr[j] = prev[j - 1] + 1
                best = max(best, curr[j])
        prev = curr
    return best


def score_match(symbol: str, candidate: dict) -> str | None:
    """Classify a ripgrep candidate against `symbol`. Returns score or None.

    Strong/medium (the blocking tiers) require the snippet to DEFINE the symbol
    (exact name) or a near name (Levenshtein <= _LEVENSHTEIN_MEDIUM). A bare
    mention at a usage site can only ever score "weak" (non-blocking).
    """
    snippet = candidate.get("snippet") or ""
    defined = _defined_name(snippet)
    if defined is not None:
        if defined == symbol:
            return "strong"
        # Near-name definition (typo/variant duplicate).
        if (
            abs(len(defined) - len(symbol)) <= _LEVENSHTEIN_MEDIUM
            and _levenshtein(symbol, defined) <= _LEVENSHTEIN_MEDIUM
        ):
            return "medium"
    # Weak: shared contiguous substring of ≥6 chars anywhere in the snippet.
    if _longest_common_substring_len(symbol, snippet) >= _WEAK_OVERLAP_MIN:
        return "weak"
    return None


def decide(
    symbols: list[str],
    candidate_groups: dict[str, list[dict]],
) -> tuple[str, list[dict]]:
    """Block on strong or medium hits, allow otherwise.

    Returns `(decision, matches)` where `matches` is the list of blocking
    scored matches (empty when allowed). Each match is
    `{"symbol", "file", "line", "score", "snippet"}`. The snippet (capped) is
    recorded so the audit log carries the evidence a deny fired on, making
    matcher tuning data-driven instead of inferred.
    """
    blocking: list[dict] = []
    for sym in symbols:
        for cand in candidate_groups.get(sym, []):
            score = score_match(sym, cand)
            if score in ("strong", "medium"):
                blocking.append(
                    {
                        "symbol": sym,
                        "file": cand.get("file", ""),
                        "line": cand.get("line", 0),
                        "score": score,
                        "snippet": (cand.get("snippet") or "")[:_SNIPPET_AUDIT_CAP],
                    },
                )
    return ("deny" if blocking else "allow", blocking)
