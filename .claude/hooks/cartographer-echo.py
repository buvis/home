#!/usr/bin/env python3
"""PreToolUse hook — Cartographer Phase 1 (Echo) duplicate-detection gate.

Reads a single JSON payload from stdin, dispatches on `tool_name`, and emits
an audit event for every decision (allow/deny/skip). At this scaffolding
phase (PRD 00010 Task 1) only the skip rules are wired; symbol extraction,
match search, and the deny envelope are added in later tasks.

Allow path: exit 0 with empty stdout (mirrors gateguard-fact-force.py).
Deny path: exit 0 with a `hookSpecificOutput.permissionDecision = "deny"`
JSON envelope on stdout (added in later tasks).

Stdlib-only. Optional `tree_sitter_language_pack` accessed lazily via
`_lib_cartographer.try_import_tree_sitter`. Python 3.10+.
"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

# Reuse the shared cartographer substrate (project hash, audit, session-state,
# tree-sitter wrapper). The hooks/ directory is on sys.path when invoked via
# subprocess from settings.json; for completeness, prepend it explicitly so
# `python3 cartographer-echo.py` from any cwd resolves the lib.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib_cartographer as lib  # noqa: E402

# --- constants ---

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go"}
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
    {"Function", "Method", "Class", "Struct", "Enum", "Type", "Trait", "Interface"}
)

# Low-signal names dropped before match scoring. The duplicate-prone verbs
# (`format`/`parse`/`validate`/`normalize`/`serialize`/`transform`) are
# deliberately ABSENT from this list (PRD success metric).
_STOPWORDS: frozenset[str] = frozenset(
    {
        "__init__", "__main__", "main", "init", "setup", "run", "start", "stop",
        "new", "default", "clone", "eq", "hash", "to_string", "from_string",
        # Generic names defined across many files; collisions are not duplicates.
        # Added 2026-05-31 from audit-echo (top recurring deny symbols).
        "create", "setUp", "Result",
    }
)
_MIN_SYMBOL_LEN: int = 4  # drop length <= 3

# 500 KB cap on `tool_input.content` (Write/Edit reconstructed). Files bigger
# than this are common in generated/minified bundles; tree-sitter parsing
# them blows the latency budget. Skip + audit instead.
LARGE_CONTENT_BYTES: int = 500_000

CLAUDE_SETTINGS_RE = re.compile(r"(^|/)\.claude/settings(?:\.[^/]+)?\.json$")

# Test-file path patterns. Matched as substrings (segments) or filename
# suffixes; tests in the project's `tests/` or `test/` dirs, `*_test.go`
# (Go convention), and `*.test.{ts,tsx,js,jsx}` (JS/TS convention).
_TEST_DIR_SEGMENTS: tuple[str, ...] = ("/tests/", "/test/")
_TEST_FILE_SUFFIXES: tuple[str, ...] = (
    "_test.go",
    "_test.py",
    ".test.ts",
    ".test.tsx",
    ".test.js",
    ".test.jsx",
)

# Tools Echo gates. Other tool names pass through with no audit event.
_TARGETED_TOOLS: frozenset[str] = frozenset(
    {"Edit", "Write", "MultiEdit", "Bash"}
)


# --- helpers ---


def is_claude_settings_path(file_path: str) -> bool:
    """Match any `.claude/settings*.json` path (mirrors gateguard convention)."""
    if not file_path:
        return False
    return bool(CLAUDE_SETTINGS_RE.search(file_path.replace("\\", "/")))


def is_test_file_path(file_path: str) -> bool:
    if not file_path:
        return False
    norm = file_path.replace("\\", "/")
    if any(seg in norm for seg in _TEST_DIR_SEGMENTS):
        return True
    if any(norm.endswith(suffix) for suffix in _TEST_FILE_SUFFIXES):
        return True
    # pytest prefix convention: test_*.py
    base = norm.rsplit("/", 1)[-1]
    return base.startswith("test_") and base.endswith(".py")


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


def content_size(tool_input: dict) -> int:
    """Best-effort size estimate from `tool_input.content` or Edit strings."""
    content = tool_input.get("content")
    if isinstance(content, str):
        return len(content)
    new_string = tool_input.get("new_string")
    if isinstance(new_string, str):
        return len(new_string)
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        total = 0
        for ed in edits:
            if isinstance(ed, dict):
                ns = ed.get("new_string")
                if isinstance(ns, str):
                    total += len(ns)
        if total:
            return total
    return 0


def target_file_path(tool_name: str, tool_input: dict) -> str:
    """Extract the target file path for the supported write tools."""
    if tool_name in ("Edit", "Write", "MultiEdit"):
        fp = tool_input.get("file_path")
        if isinstance(fp, str):
            return fp
    return ""


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


def _walk_structure(items, kinds: frozenset[str], collected: list[str], seen: set[str]) -> None:
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
    except Exception as exc:  # noqa: BLE001
        # Parsing fails on syntactically invalid content; record a warn and
        # treat as no symbols (the host write proceeds).
        lib.append_audit({"event": "tree_sitter_parse_failed", "language": lang, "error": str(exc)})
        return []

    collected: list[str] = []
    seen: set[str] = set()
    _walk_structure(getattr(result, "structure", None) or [], _SYMBOL_KINDS, collected, seen)
    # Also merge in top-level `symbols` (some grammars — e.g. go's
    # `type` declarations — surface only here, not in `structure`).
    for s in getattr(result, "symbols", None) or []:
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
    r"\s+([A-Za-z_]\w*)"
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
                if curr[j] > best:
                    best = curr[j]
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
    symbols: list[str], candidate_groups: dict[str, list[dict]]
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
                    }
                )
    return ("deny" if blocking else "allow", blocking)


# --- ripgrep candidate search ---

_RG_TIMEOUT_SEC: float = 1.0
_RG_MAX_HITS_PER_SYMBOL: int = 5  # hits handed to scoring
_RG_SCAN_LIMIT: int = 50  # hits collected per symbol before definition-first ranking
_RG_BATCH_SCAN_LIMIT: int = 500  # total rg output lines parsed per batch (bounds attribution)
_RG_EXCLUDE_GLOBS: tuple[str, ...] = (
    "!.git", "!node_modules", "!vendor", "!dist", "!build",
    "!__pycache__", "!target", "!.venv",
)


def _parse_rg_line(line: str) -> tuple[str, int, str] | None:
    """Split an `rg -n` line `<file>:<lineno>:<snippet>` -> (file, lineno, snippet)."""
    first = line.find(":")
    if first <= 0:
        return None
    second = line.find(":", first + 1)
    if second <= 0:
        return None
    try:
        lineno = int(line[first + 1 : second])
    except ValueError:
        return None
    return line[:first], lineno, line[second + 1 :].strip()


def search_candidates_batch(
    symbols: list[str], root: Path, target_file: Path
) -> dict[str, list[dict]]:
    """One rg over an alternation of ALL symbols -> `{sym: hits}` (PRD 00088 R3).

    Replaces one rg spawn per symbol (which blew the 5s hook budget on
    symbol-dense files) with a single subprocess. Each group holds up to 5 hits
    `{"file", "line", "snippet"}`, excluding `target_file` and build dirs.
    Attribution is by literal substring, mirroring the per-symbol regex's
    unanchored substring match for identifiers: a line carrying two searched
    symbols lands in both groups, exactly as two separate rg runs would find it.
    On timeout, missing binary, or non-zero rg exit other than 1 (no match):
    returns empty groups and appends a `ripgrep_*` audit-warn event.
    """
    uniq = [s for s in dict.fromkeys(symbols) if s]
    groups: dict[str, list[dict]] = {s: [] for s in uniq}
    if not uniq or not root.exists():
        return groups
    pattern = "|".join(re.escape(s) for s in uniq)
    args = ["rg", "-n", "--max-count", str(_RG_MAX_HITS_PER_SYMBOL * len(uniq))]
    for g in _RG_EXCLUDE_GLOBS:
        args.extend(["--glob", g])
    args.extend(["-e", pattern, "--", str(root)])
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=_RG_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        lib.append_audit({"event": "ripgrep_timeout", "symbols": len(uniq)})
        return groups
    except FileNotFoundError:
        lib.append_audit({"event": "ripgrep_missing"})
        return groups

    if proc.returncode not in (0, 1):
        lib.append_audit({"event": "ripgrep_error", "code": proc.returncode, "stderr": proc.stderr[:200]})
        return groups

    try:
        target_abs = str(target_file.resolve())
    except OSError:
        target_abs = str(target_file)

    scanned = 0
    for line in proc.stdout.splitlines():
        if scanned >= _RG_BATCH_SCAN_LIMIT:
            break
        parsed = _parse_rg_line(line)
        if parsed is None:
            continue
        file_part, lineno, snippet = parsed
        try:
            cand_abs = str(Path(file_part).resolve())
        except OSError:
            cand_abs = file_part
        if cand_abs == target_abs:
            continue
        scanned += 1
        hit = {"file": file_part, "line": lineno, "snippet": snippet}
        for s in uniq:
            if s in snippet and len(groups[s]) < _RG_SCAN_LIMIT:
                groups[s].append(hit)

    # Only definition lines can block, so rank them ahead of usage sites before
    # truncating: a stable sort keeps rg's order within each group, so the hit
    # cap never drops the duplicate definition behind unrelated call sites.
    for s in uniq:
        groups[s].sort(key=lambda c: _defined_name(c["snippet"]) is None)
        groups[s] = groups[s][:_RG_MAX_HITS_PER_SYMBOL]
    return groups


def search_candidates(symbol: str, root: Path, target_file: Path) -> list[dict]:
    """ripgrep for a single `symbol` — the one-symbol case of
    `search_candidates_batch` (kept for its focused tests and any single-symbol
    caller). Returns up to 5 hits, or [] on rg failure."""
    return search_candidates_batch([symbol], root, target_file).get(symbol, [])


def filter_stopwords(symbols: list[str], file_path: str) -> list[str]:
    """Drop low-signal symbols. Returns [] when `file_path` is a test file.

    Test-file detection: any path containing `/tests/` or `/test/`, or
    ending with `_test.go`, `_test.py`, `.test.{ts,tsx,js,jsx}`. Echo
    intentionally never gates writes to test files (those write paths are
    where duplicate-detection produces the most false positives).
    """
    if is_test_file_path(file_path):
        return []
    out: list[str] = []
    for name in symbols:
        if not isinstance(name, str) or not name:
            continue
        if len(name) < _MIN_SYMBOL_LEN:
            continue
        if name in _STOPWORDS:
            continue
        out.append(name)
    return out


def _resolve_project_root(file_path: str) -> Path:
    """Find the git toplevel containing `file_path`, falling back to its parent.

    Echo searches across the project, so the root MUST be a real directory.
    `_lib_cartographer.project_hash` returns identity tuples (hash, name,
    remote), not a path, so we don't reuse it here.
    """
    parent = Path(file_path).parent if file_path else Path.cwd()
    try:
        proc = subprocess.run(
            ["git", "-C", str(parent), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=2,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return Path(proc.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return parent if parent.exists() else Path.cwd()


# --- Bash bypass pattern detection ---

_BASH_SOURCE_EXTENSIONS: frozenset[str] = frozenset(
    {".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go", ".md", ".yaml", ".yml", ".json", ".toml"}
)

_BASH_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("cat-redirect", re.compile(r"\bcat\s*>>?\s*(\S+)")),
    ("tee", re.compile(r"\btee\b[^|;]*?(\S+\.[A-Za-z0-9]+)")),
    (
        "python-open-write",
        re.compile(r"python3?\s+-c\s+[\"'][^\"']*\bopen\s*\(\s*[\"']([^\"']+)[\"']\s*,\s*[\"']w[\"']"),
    ),
    ("sed-inplace", re.compile(r"\bsed\s+-i\b[^|;\n]*?\s(\S+\.[A-Za-z0-9]+)(?:\s|$)")),
)


def _resolve_within_cwd(raw_path: str, cwd: Path) -> Path | None:
    """Resolve `raw_path` against `cwd`. Return Path if it stays within cwd, else None."""
    raw = raw_path.strip().rstrip("'\"").lstrip("'\"")
    if not raw:
        return None
    try:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = (cwd / candidate)
        resolved = candidate.resolve()
        cwd_resolved = cwd.resolve()
        resolved.relative_to(cwd_resolved)
        return resolved
    except (OSError, ValueError):
        return None


def _find_redirect_targets(command: str) -> list[str]:
    """Targets of real (unquoted) `>` / `>>` operators, via shlex tokenization.

    A `>` inside quotes dequotes into an ordinary token, so literal text like
    `"<prd>-review-<n>.md"` or regex arguments can never read as a redirect.
    """
    lex = shlex.shlex(command, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    try:
        tokens = list(lex)
    except ValueError:
        # Unparseable (heredoc body, unbalanced quotes) — fail open; the
        # cat-redirect regex still covers the heredoc form.
        return []
    targets = []
    for i, tok in enumerate(tokens[:-1]):
        if tok in (">", ">>") and not (i > 0 and tokens[i - 1].isdigit()):
            # ponytail: isdigit guard skips fd redirects (2> err.md) but also
            # `echo 2 > x.md`; acceptable, Echo is a soft nudge.
            targets.append(tokens[i + 1])
    return targets


def _check_target(target: str, cwd: Path) -> Path | None:
    """Apply the source-path heuristic to one candidate target path."""
    resolved = _resolve_within_cwd(target, cwd)
    if resolved is None:
        return None
    ext = "." + resolved.name.rsplit(".", 1)[-1].lower() if "." in resolved.name else ""
    if ext not in _BASH_SOURCE_EXTENSIONS:
        return None
    if is_claude_settings_path(str(resolved)):
        return None
    return resolved


def detect_bash_bypass(command: str, cwd: Path) -> tuple[str, str] | None:
    """Detect code-writing Bash patterns. Return `(pattern_name, resolved_path_str)` or None.

    Source-path heuristic: the target path resolves under `cwd` AND has an
    extension in `_BASH_SOURCE_EXTENSIONS`. Skips writes to
    `~/.claude/settings.json` so gateguard's own rules govern there.
    """
    if not command or not isinstance(command, str):
        return None
    for name, pat in _BASH_PATTERNS:
        for m in pat.finditer(command):
            target = m.group(1)
            if not target:
                continue
            resolved = _check_target(target, cwd)
            if resolved is None:
                continue
            return (name, str(resolved))
    for target in _find_redirect_targets(command):
        resolved = _check_target(target, cwd)
        if resolved is not None:
            return ("redirect-source", str(resolved))
    return None


# --- two-attempt deny gate ---

_ECHO_NAMESPACE: str = "echo"


def deny_key(file_path: str, symbols: list[str]) -> str:
    """`sha256(file_path + "|" + "|".join(sorted(symbols)))[:24]`."""
    payload = file_path + "|" + "|".join(sorted(symbols))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


_RATIONALIZATIONS_PATH: Path = Path.home() / ".claude" / "rules-library" / "rationalizations.md"

# Verbs whose presence in a symbol name triggers the "Couldn't find existing
# helper" rationalization (Echo's highest-leverage scenario per PRD).
_HELPER_VERBS: tuple[str, ...] = (
    "format", "parse", "validate", "normalize", "serialize", "transform",
    "decode", "encode", "stringify", "render",
)

_RATIONALIZATIONS_CACHE: dict[str, tuple[str, str]] | None = None


def _load_rationalizations() -> dict[str, tuple[str, str]]:
    """Parse rules-library/rationalizations.md into {excuse: (why, counter)} once per process."""
    global _RATIONALIZATIONS_CACHE
    if _RATIONALIZATIONS_CACHE is not None:
        return _RATIONALIZATIONS_CACHE

    out: dict[str, tuple[str, str]] = {}
    try:
        text = _RATIONALIZATIONS_PATH.read_text(encoding="utf-8")
    except OSError:
        _RATIONALIZATIONS_CACHE = out
        return out

    header_re = re.compile(r"^###\s+\"([^\"]+)\"\s*$", re.MULTILINE)
    why_re = re.compile(r"-\s*\*\*Why it's wrong\*\*:\s*(.+?)(?:\n-|\n\n|\Z)", re.DOTALL)
    counter_re = re.compile(r"-\s*\*\*Counter-action\*\*:\s*(.+?)(?:\n-|\n\n|\Z)", re.DOTALL)

    matches = list(header_re.finditer(text))
    for i, m in enumerate(matches):
        excuse = m.group(1).strip()
        section_start = m.end()
        section_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section = text[section_start:section_end]
        why_m = why_re.search(section)
        counter_m = counter_re.search(section)
        if why_m and counter_m:
            out[excuse] = (
                " ".join(why_m.group(1).split()),
                " ".join(counter_m.group(1).split()),
            )

    _RATIONALIZATIONS_CACHE = out
    return out


def _pick_rationalization(symbols: list[str]) -> tuple[str, str, str] | None:
    """Return (excuse, why, counter) — heuristic excuse choice based on symbol verbs."""
    rats = _load_rationalizations()
    if not rats:
        return None
    for sym in symbols:
        low = sym.lower()
        if any(v in low for v in _HELPER_VERBS):
            entry = rats.get("Couldn't find existing helper")
            if entry:
                return ("Couldn't find existing helper", *entry)
            break
    entry = rats.get("Quick fix, skip atlas")
    if entry:
        return ("Quick fix, skip atlas", *entry)
    k, (w, c) = next(iter(rats.items()))
    return (k, w, c)


_DENY_REASON_CAP: int = 1500
_RATIONALIZATION_EXCERPT_CAP: int = 400


def build_deny_envelope(matches: list[dict]) -> dict:
    """Compose the gateguard-format deny envelope with a rationalization excerpt."""
    if not matches:
        reason = "Echo: duplicate-detection deny — retry to override."
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }

    strongest = next((m for m in matches if m.get("score") == "strong"), None)
    if strongest is None:
        strongest = next((m for m in matches if m.get("score") == "medium"), matches[0])

    sym = strongest.get("symbol", "?")
    fp = strongest.get("file", "?")
    ln = strongest.get("line", 0)

    symbols_in_play = sorted({m.get("symbol", "") for m in matches if m.get("symbol")})
    rationalization = _pick_rationalization(symbols_in_play)

    parts = [
        f"Echo: `{sym}` likely duplicates `{fp}:{ln}`.",
        "",
        f"Existing implementation is at `{fp}:{ln}` — import it instead of writing a parallel one.",
    ]
    if rationalization is not None:
        excuse, why, counter = rationalization
        excerpt = f"\"{excuse}\". Why it's wrong: {why} Counter-action: {counter}"
        if len(excerpt) > _RATIONALIZATION_EXCERPT_CAP:
            excerpt = excerpt[: _RATIONALIZATION_EXCERPT_CAP - 1].rstrip() + "…"
        parts.extend(
            [
                "",
                "Rationalization (`rules-library/rationalizations.md`):",
                "> " + excerpt,
            ]
        )

    parts.extend(["", "If this is genuinely new, retry — the second attempt will pass."])
    reason = "\n".join(parts)
    if len(reason) > _DENY_REASON_CAP:
        reason = reason[: _DENY_REASON_CAP - 1].rstrip() + "…"

    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


# --- audit emission ---


def audit_event(
    *,
    session: str,
    tool: str,
    file: str,
    decision: str,
    reason: str,
    symbols: list[str] | None = None,
    matches: list[dict] | None = None,
) -> None:
    """Append one audit event with the Echo schema (PRD 00010 §Audit)."""
    event = {
        "session": session,
        "tool": tool,
        "file": file,
        "decision": decision,
        "reason": reason,
        "symbols": symbols or [],
        "matches": matches or [],
        "phase": "echo",
    }
    lib.append_audit(event)


# --- skip evaluation ---


def evaluate_skip(tool_name: str, tool_input: dict) -> tuple[str, str] | None:
    """Return `(decision, reason)` for a skip case, or None to continue.

    Order matters: settings check runs before extension check so the
    audit log records the *primary* skip reason consistently.
    """
    file_path = target_file_path(tool_name, tool_input)

    if file_path and is_claude_settings_path(file_path):
        return ("skip", "settings")

    if content_size(tool_input) > LARGE_CONTENT_BYTES:
        return ("skip", "large-file")

    if file_path and is_test_file_path(file_path):
        return ("skip", "test-file")

    if file_path and not has_supported_extension(file_path):
        return ("skip", "unsupported-ext")

    # tree-sitter availability is checked last because the import is cached
    # process-wide and emits its own `tree_sitter_missing` audit on first
    # failure. We still record a skip:no-tree-sitter so audit-echo can
    # surface the rate.
    if lib.try_import_tree_sitter() is None:
        return ("skip", "no-tree-sitter")

    return None


# --- main dispatch ---


def handle(data: dict) -> None:
    tool_name = data.get("tool_name") or ""
    tool_input = data.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}

    if tool_name not in _TARGETED_TOOLS and not tool_name.startswith("mcp__serena__"):
        # Echo does not gate this tool; emit no audit event.
        return

    session = lib.resolve_session_key(data)
    file_path = target_file_path(tool_name, tool_input)

    # PRD 00049: stamp "this session edited files in this repo" once, so the
    # cartographer-stop nudge can scope itself to sessions that touched it.
    if file_path and tool_name != "Bash":
        try:
            repo_hash, _, _ = lib.project_hash()
            if not lib.is_checked(session, "survey-edits", repo_hash):
                lib.mark_checked(session, "survey-edits", repo_hash)
        except Exception:
            pass

    skip = evaluate_skip(tool_name, tool_input)
    if skip is not None:
        decision, reason = skip
        audit_event(
            session=session,
            tool=tool_name,
            file=file_path,
            decision=decision,
            reason=reason,
        )
        return

    if tool_name == "Bash":
        cmd = tool_input.get("command")
        if not isinstance(cmd, str) or not cmd.strip():
            return
        hit = detect_bash_bypass(cmd, Path.cwd())
        if hit is None:
            audit_event(
                session=session, tool=tool_name, file="",
                decision="allow", reason="bash-clean",
            )
            return
        pattern_name, resolved_path = hit
        key = hashlib.sha256(
            ("bash:" + pattern_name + ":" + resolved_path).encode("utf-8")
        ).hexdigest()[:24]
        if lib.is_checked(session, _ECHO_NAMESPACE, key):
            audit_event(
                session=session, tool=tool_name, file=resolved_path,
                decision="allow", reason="second-attempt",
                matches=[{"pattern": pattern_name}],
            )
            return
        lib.mark_checked(session, _ECHO_NAMESPACE, key)
        reason_text = (
            f"Echo: this Bash command writes source code via `{pattern_name}`. "
            f"Use the Write tool — Echo cannot inspect content written through "
            f"shell redirects.\n\nDetected target: `{resolved_path}`.\n\n"
            f"If you must use shell, retry — the second attempt will pass."
        )
        envelope = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason_text,
            }
        }
        sys.stdout.write(json.dumps(envelope))
        audit_event(
            session=session, tool=tool_name, file=resolved_path,
            decision="deny", reason="bash-bypass",
            matches=[{"pattern": pattern_name}],
        )
        return

    if tool_name.startswith("mcp__serena__"):
        # MCP serena tools shadow file writes but with tool-specific input
        # shapes. Surface them in the audit log so audit-echo can flag the
        # coverage gap; do not gate.
        audit_event(
            session=session, tool=tool_name, file=file_path,
            decision="skip", reason="mcp-unsupported",
        )
        return

    if tool_name in ("Edit", "Write", "MultiEdit"):
        content = extract_content(tool_name, tool_input)
        ext = file_extension(file_path)
        raw_symbols = extract_symbols(content, ext)
        symbols = filter_stopwords(raw_symbols, file_path)

        if not symbols:
            audit_event(
                session=session, tool=tool_name, file=file_path,
                decision="allow", reason="no-symbols",
            )
            return

        # Resolve project root. lib.project_hash returns (hash, name, remote)
        # — the remote_url, not a usable path. Use git toplevel when in a
        # repo; otherwise fall back to the target file's parent directory.
        project_root = _resolve_project_root(file_path)
        # One rg over an alternation of all symbols (PRD 00088 R3) — not one
        # spawn per symbol, which blew the 5s hook budget on symbol-dense files.
        candidate_groups = search_candidates_batch(symbols, project_root, Path(file_path))

        decision, matches = decide(symbols, candidate_groups)

        if decision == "allow":
            audit_event(
                session=session, tool=tool_name, file=file_path,
                decision="allow", reason="weak-only" if any(candidate_groups.values()) else "no-matches",
                symbols=symbols, matches=matches,
            )
            return

        # Two-attempt gate.
        key = deny_key(file_path, symbols)
        if lib.is_checked(session, _ECHO_NAMESPACE, key):
            audit_event(
                session=session, tool=tool_name, file=file_path,
                decision="allow", reason="second-attempt",
                symbols=symbols, matches=matches,
            )
            return
        lib.mark_checked(session, _ECHO_NAMESPACE, key)
        envelope = build_deny_envelope(matches)
        sys.stdout.write(json.dumps(envelope))
        # Audit reason matches the strongest hit's score.
        strongest_score = matches[0]["score"] if matches else "unknown"
        audit_event(
            session=session, tool=tool_name, file=file_path,
            decision="deny", reason=f"{strongest_score}-match",
            symbols=symbols, matches=matches,
        )
        return

    return


def main() -> int:
    if sys.stdin.isatty():
        return 0
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    if not isinstance(data, dict):
        return 0
    try:
        handle(data)
    except Exception as exc:  # noqa: BLE001
        # Hooks must never crash the host tool. Surface to stderr and exit
        # 0 so the Edit/Write proceeds.
        print(f"[cartographer-echo] handle failed: {exc}", file=sys.stderr)
    return 0


def run(payload):
    """Dispatcher entry point (hooks/dispatch.py). The handler owns its own
    capture: `capture_main` feeds `payload` as stdin, captures stdout/stderr and
    maps main()'s exit, so run() RETURNS the (exit_code, stdout, stderr) triple
    the dispatcher surfaces unchanged. `_common` is imported here, not at module
    scope, so the standalone `__main__` path is unaffected."""
    from _common import capture_main

    return capture_main(main, payload)


if __name__ == "__main__":
    sys.exit(main())
