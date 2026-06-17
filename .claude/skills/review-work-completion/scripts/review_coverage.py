#!/usr/bin/env python3
"""review_coverage.py - parse and gate review coverage blocks.

CLI:
    python3 review_coverage.py \
        --surface {work-completion|blindly|doubt} \
        --prd <path> \
        --diff-range <git-ref> \
        --reviewer-block <path> [--reviewer-block <path>...] \
        [--rubric <path>] \
        [--repo <path>] \
        [--write-aggregate <path>] \
        [--run-tests]

Exit 0 = coverage complete. Non-zero = gap found; stderr starts with gap kind.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

OPEN_DELIM = "---review-coverage---"
CLOSE_DELIM = "---end-review-coverage---"
REQUIRED_SECTIONS = {"files", "tests", "features", "rubric"}

VALID_FILE_VERDICTS_EXACT = {"reviewed"}
VALID_FEATURE_VERDICTS = {"verified", "reviewed", "failed"}
VALID_RUBRIC_VERDICTS = {"pass", "fail"}


def _fail(kind: str, detail: str) -> None:
    sys.stderr.write(f"{kind}: {detail}\n")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Block parsing
# ---------------------------------------------------------------------------

def _extract_block_text(text: str) -> str | None:
    """Return text between delimiters, or None if delimiters missing."""
    i = text.find(OPEN_DELIM)
    j = text.find(CLOSE_DELIM)
    if i == -1 or j == -1 or j < i:
        return None
    return text[i + len(OPEN_DELIM):j]


_CANONICAL_ORDER = ["files", "tests", "features", "rubric"]


def _parse_block(block_text: str) -> dict[str, dict[str, str]]:
    """Parse the interior of a coverage block into {section: {key: value}}.

    Raises ValueError with a descriptive message on malformed content.
    Sections must appear in canonical order (files, tests, features, rubric)
    with no duplicates.
    """
    sections: dict[str, dict[str, str]] = {}
    current: str | None = None
    last_section_index: int = -1

    for raw_line in block_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Section header: "files:", "tests:", "features:", "rubric:"
        if line.endswith(":") and " " not in line:
            name = line[:-1]
            if name not in REQUIRED_SECTIONS:
                raise ValueError(f"unknown section header: {line!r}")
            section_index = _CANONICAL_ORDER.index(name)
            if section_index <= last_section_index:
                raise ValueError(
                    f"section {name!r} appears out of order or is duplicated "
                    f"(canonical order: {', '.join(_CANONICAL_ORDER)})"
                )
            last_section_index = section_index
            current = name
            sections[current] = {}
            continue

        # Entry line: "  key: value". The features section splits on the LAST
        # colon: feature names may themselves contain colons (e.g.
        # "update-pidash-tasks.py::main()") while feature values are a
        # colon-free enum {verified, reviewed, failed}. Every other section's
        # value may contain colons (files' "n/a:<reason>") while its key cannot,
        # so they split on the FIRST colon.
        if ":" in line:
            if current is None:
                raise ValueError(f"entry before any section header: {line!r}")
            if current == "features":
                key, _, value = line.rpartition(":")
            else:
                key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            sections[current][key] = value
            continue

        raise ValueError(f"unparseable line: {line!r}")

    missing = REQUIRED_SECTIONS - set(sections)
    if missing:
        raise ValueError(f"missing required sections: {', '.join(sorted(missing))}")

    return sections


def _validate_verdicts(sections: dict[str, dict[str, str]]) -> None:
    """Validate verdict values in each dimension. Raises ValueError on bad values."""
    for fname, verdict in sections["files"].items():
        if verdict != "reviewed" and not verdict.startswith("n/a:"):
            raise ValueError(f"invalid files verdict for {fname!r}: {verdict!r}")

    for key, value in sections["tests"].items():
        if key == "none":
            if value != "diff touches no code":
                raise ValueError(f"invalid none sentinel value: {value!r}")
        elif key == "pending":
            if value != "filled by consolidation":
                raise ValueError(f"invalid pending sentinel value: {value!r}")
        else:
            if not re.match(r"^pass=\d+ fail=\d+ skip=\d+$", value):
                raise ValueError(f"invalid tests entry for {key!r}: {value!r}")

    for feat, verdict in sections["features"].items():
        if verdict not in VALID_FEATURE_VERDICTS:
            raise ValueError(f"invalid features verdict for {feat!r}: {verdict!r} — offending key: {feat}")

    for rule, verdict in sections["rubric"].items():
        if verdict not in VALID_RUBRIC_VERDICTS:
            raise ValueError(f"invalid rubric verdict for {rule!r}: {verdict!r} — offending key: {rule}")


def _load_block(path: Path) -> dict[str, dict[str, str]]:
    """Load and parse a reviewer-block file. Calls _fail on any problem."""
    text = path.read_text()
    block_text = _extract_block_text(text)
    if block_text is None:
        _fail("MISSING_REVIEW_BLOCK", str(path))
        return {}  # unreachable; satisfies type checker without suppression

    try:
        sections = _parse_block(block_text)
    except ValueError as exc:
        _fail("MALFORMED_BLOCK", str(exc))
        return {}  # unreachable

    try:
        _validate_verdicts(sections)
    except ValueError as exc:
        msg = str(exc)
        m = re.search(r"offending key: (.+)$", msg)
        detail = m.group(1) if m else msg
        _fail("MALFORMED_BLOCK", detail)
        return {}  # unreachable

    return sections


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

def _merge_blocks(blocks: list[dict[str, dict[str, str]]]) -> dict[str, dict[str, str]]:
    """Merge multiple parsed blocks into one aggregate."""
    merged: dict[str, dict[str, str]] = {s: {} for s in REQUIRED_SECTIONS}

    for block in blocks:
        for fname, verdict in block["files"].items():
            existing = merged["files"].get(fname)
            if existing == "reviewed" or verdict == "reviewed":
                merged["files"][fname] = "reviewed"
            else:
                merged["files"][fname] = verdict

        for key, value in block["tests"].items():
            merged["tests"][key] = value

        for feat, verdict in block["features"].items():
            existing = merged["features"].get(feat)
            if existing == "verified" or verdict == "verified":
                merged["features"][feat] = "verified"
            else:
                merged["features"][feat] = verdict

        for rule, verdict in block["rubric"].items():
            existing = merged["rubric"].get(rule)
            if existing == "pass" or verdict == "pass":
                merged["rubric"][rule] = "pass"
            else:
                merged["rubric"][rule] = verdict

    return merged


def _strip_reviewer_test_counts(tests: dict[str, str]) -> dict[str, str]:
    """Keep only the sentinel keys (`none`/`pending`). Reviewers never assert
    real test counts — those come solely from the consolidation test run — so a
    fabricated `pass=N fail=N skip=N` entry is discarded here."""
    return {k: v for k, v in tests.items() if k in ("none", "pending")}


# ---------------------------------------------------------------------------
# External data gathering
# ---------------------------------------------------------------------------

def _diff_files(diff_range: str, repo: Path) -> tuple[list[str], Path]:
    """Return (changed files, work-tree root the paths are relative to)."""
    result = subprocess.run(
        ["git", "diff", "--name-only", diff_range],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return [f for f in result.stdout.splitlines() if f.strip()], repo

    # Fallback for bare-repo work-trees (e.g. ~/.buvis-backed $HOME), where the
    # project root has no .git and a plain `git diff` from it fails.
    git_dir = os.environ.get("AUTOPILOT_GIT_DIR") or str(Path.home() / ".buvis")
    work_tree = os.environ.get("AUTOPILOT_GIT_WORK_TREE") or str(Path.home())
    # Both must be real directories before use: work_tree becomes the subprocess
    # cwd, so a path that is missing OR a non-directory would otherwise raise a
    # raw OSError instead of the clean DIFF_ERROR kind.
    if Path(git_dir).is_dir() and Path(work_tree).is_dir():
        fallback = subprocess.run(
            ["git", f"--git-dir={git_dir}", f"--work-tree={work_tree}",
             "diff", "--name-only", diff_range],
            cwd=work_tree,
            capture_output=True,
            text=True,
        )
        if fallback.returncode == 0:
            return [f for f in fallback.stdout.splitlines() if f.strip()], Path(work_tree)

    # DIFF_ERROR, not MISSING_FILES: an uncomputable diff is an infra failure
    # (wrong repo, bad SHA, no git), not evidence the reviewer skipped files.
    # Callers gate differently on the two kinds.
    _fail("DIFF_ERROR", f"git diff failed: {result.stderr.strip()}")
    return [], repo  # unreachable; satisfies type checker without suppression


# ---------------------------------------------------------------------------
# Native-test engine: declarative stack registry + per-stack command/parse
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Stack:
    name: str
    file_re: re.Pattern[str]
    markers: tuple[str, ...]
    build_cmd: Callable[[Path, Path, list[str]], list[str]]   # (work_tree, scope_dir, rel_targets) -> argv
    parse: Callable[[str, int], str | None]                   # (output, returncode) -> "pass=P fail=F skip=S" | None
    # True -> run the native command from scope_dir (the marker/module root):
    # go/npm need their package root. False (default) -> run from work_tree:
    # pytest needs a stable rootdir/config discovery (byte-for-byte parity) and
    # cargo is cwd-independent (--manifest-path is absolute).
    cwd_at_scope: bool = False


def _pytest_cmd(work_tree: Path, scope_dir: Path, rel_targets: list[str]) -> list[str]:
    """Quiet, scoped pytest argv targeting the changed test files (cwd = work_tree)."""
    abs_test_files = [str((work_tree / rel).resolve()) for rel in rel_targets]
    return [sys.executable, "-m", "pytest", *abs_test_files, "-q"]


def _parse_pytest(output: str, returncode: int) -> str | None:
    """Fold a pytest -q summary into 'pass=P fail=F skip=S' (errors count as fail).
    None when no test ran (all three counts zero)."""
    def count(pattern: str) -> int:
        m = re.search(pattern, output)
        return int(m.group(1)) if m else 0

    passed = count(r"(\d+) passed")
    failed = count(r"(\d+) failed") + count(r"(\d+) error(?:s)?")
    skipped = count(r"(\d+) skipped")
    if passed == 0 and failed == 0 and skipped == 0:
        return None
    return f"pass={passed} fail={failed} skip={skipped}"


def _cargo_cmd(work_tree: Path, scope_dir: Path, rel_targets: list[str]) -> list[str]:
    """Scoped cargo argv: --manifest-path pins the changed crate, --no-fail-fast
    runs every test so the summary reflects all failures (cwd-independent)."""
    return ["cargo", "test", "--manifest-path", str(scope_dir / "Cargo.toml"), "--no-fail-fast"]


def _parse_cargo(output: str, returncode: int) -> str | None:
    """Sum every libtest summary line across binaries into 'pass=P fail=F skip=S'
    (skip folds Rust's 'ignored'). None when no summary line is present OR the total
    is zero tests (fail-loud parity with the pytest 'no tests ran' contract)."""
    passed = failed = ignored = 0
    found = False
    for m in re.finditer(
        r"test result:\s+\w+\.\s+(\d+) passed;\s+(\d+) failed;\s+(\d+) ignored;",
        output,
    ):
        found = True
        passed += int(m.group(1))
        failed += int(m.group(2))
        ignored += int(m.group(3))
    if not found or (passed == 0 and failed == 0 and ignored == 0):
        return None
    return f"pass={passed} fail={failed} skip={ignored}"


def _go_cmd(work_tree: Path, scope_dir: Path, rel_targets: list[str]) -> list[str]:
    """`go test -json` scoped to the changed packages. Each changed file's package
    dir becomes a './pkg/...' pattern RELATIVE to the module root (scope_dir), which
    is the cwd the engine runs this from. Deduped, order-stable."""
    patterns: list[str] = []
    seen: set[str] = set()
    for rel in rel_targets:
        pkg_dir = (work_tree / rel).resolve().parent
        rel_pkg = str(pkg_dir.relative_to(scope_dir))
        pattern = "./..." if rel_pkg == "." else f"./{rel_pkg}/..."
        if pattern not in seen:
            seen.add(pattern)
            patterns.append(pattern)
    return ["go", "test", "-json", *patterns]


def _parse_go_json(output: str, returncode: int) -> str | None:
    """Parse `go test -json` newline-delimited JSON. Count terminal test-level
    actions (objects carrying a 'Test' key with Action in {pass,fail,skip});
    package-level events (no 'Test') and run/output actions are ignored. Non-JSON
    noise lines are skipped. None when no test-level action is present."""
    passed = failed = skipped = 0
    found = False
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if not isinstance(obj, dict) or "Test" not in obj:
            continue
        action = obj.get("Action")
        if action == "pass":
            passed += 1
            found = True
        elif action == "fail":
            failed += 1
            found = True
        elif action == "skip":
            skipped += 1
            found = True
    if not found:
        return None
    return f"pass={passed} fail={failed} skip={skipped}"


def _int_or_zero(pattern: str, text: str) -> int:
    """First capture group of pattern as int, or 0 when pattern does not match."""
    m = re.search(pattern, text)
    return int(m.group(1)) if m else 0


def _npm_cmd(work_tree: Path, scope_dir: Path, rel_targets: list[str]) -> list[str]:
    """JS/TS test argv, run from the package root (scope_dir, the engine's cwd).
    Detect the runner from scope_dir/package.json deps: vitest -> JSON reporter,
    jest -> --json, otherwise best-effort `npm test --prefix`."""
    deps: dict = {}
    try:
        data = json.loads((scope_dir / "package.json").read_text())
        deps = {**data.get("devDependencies", {}), **data.get("dependencies", {})}
    except (OSError, ValueError):
        deps = {}
    if "vitest" in deps:
        return ["npx", "vitest", "run", "--reporter=json"]
    if "jest" in deps:
        return ["npx", "jest", "--json"]
    return ["npm", "test", "--prefix", str(scope_dir)]


def _parse_jest_vitest(output: str, returncode: int) -> str | None:
    """Parse jest/vitest output. Prefer the machine JSON report (jest --json and
    vitest --reporter=json share numPassedTests/numFailedTests/numPendingTests),
    extracted even amid stderr noise; fall back to the human `Tests:` summary line.
    None when no counts are found or every count is zero (fail-loud parity)."""
    decoder = json.JSONDecoder()
    idx = output.find("{")
    while idx != -1:
        try:
            obj, _end = decoder.raw_decode(output[idx:])
        except ValueError:
            idx = output.find("{", idx + 1)
            continue
        if isinstance(obj, dict) and "numPassedTests" in obj:
            passed = int(obj.get("numPassedTests", 0))
            failed = int(obj.get("numFailedTests", 0))
            skipped = int(obj.get("numPendingTests", 0))
            if passed == 0 and failed == 0 and skipped == 0:
                return None
            return f"pass={passed} fail={failed} skip={skipped}"
        idx = output.find("{", idx + 1)
    m = re.search(r"Tests:.*", output)
    if m:
        passed = _int_or_zero(r"(\d+) passed", m.group(0))
        failed = _int_or_zero(r"(\d+) failed", m.group(0))
        skipped = _int_or_zero(r"(\d+) (?:skipped|todo|pending)", m.group(0))
        if passed or failed or skipped:
            return f"pass={passed} fail={failed} skip={skipped}"
    return None


STACKS: tuple[Stack, ...] = (
    Stack("pytest", re.compile(r"(^|/)(test_[^/]*\.py|[^/]*_test\.py)$"),
          ("pyproject.toml", "setup.py", "setup.cfg", "tox.ini"), _pytest_cmd, _parse_pytest),
    Stack("cargo", re.compile(r"\.rs$"), ("Cargo.toml",), _cargo_cmd, _parse_cargo),
    Stack("go", re.compile(r"\.go$"), ("go.mod",), _go_cmd, _parse_go_json,
          cwd_at_scope=True),
    Stack("npm", re.compile(r"\.(?:[cm]?jsx?|[cm]?tsx?)$"), ("package.json",),
          _npm_cmd, _parse_jest_vitest, cwd_at_scope=True),
)

# The markerless stack that owns .py. A changed .py NOT matching its file_re is a
# Python source change with no pytest run target; used below to fail loud rather
# than let a polyglot sibling stack mask an untested .py change green.
_PYTEST: Stack = next(s for s in STACKS if s.name == "pytest")

_NON_CODE_SUFFIXES = {
    ".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".toml", ".lock", ".cfg",
    ".ini", ".sh", ".bash", ".png", ".jpg", ".svg", ".gif", ".ico", ".csv",
    ".html", ".css",
}


def _run_cmd(argv: list[str], cwd: Path, timeout: int = 600) -> tuple[str, int]:
    """Run a native test command foreground with a finite timeout. Returns
    (combined stdout+stderr, returncode). Fails loud on timeout / missing binary."""
    try:
        result = subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        _fail("TEST_RUN_ERROR", f"command timed out after {timeout}s: {' '.join(argv)}")
        return "", 1  # unreachable
    except FileNotFoundError as exc:
        _fail("TEST_RUN_ERROR", str(exc))
        return "", 1  # unreachable
    return result.stdout + result.stderr, result.returncode


def _scope_dir_for(file_dir: Path, work_tree: Path, markers: tuple[str, ...]) -> Path | None:
    """Walk up from file_dir to work_tree for the nearest dir holding any marker."""
    current = file_dir
    while True:
        if any((current / m).exists() for m in markers):
            return current
        if current == work_tree:
            return None
        parent = current.parent
        if parent == current:
            return None
        current = parent


def _detect_active_stacks(
    diff_files: list[str], work_tree: Path
) -> tuple[list[tuple[Stack, Path, str]], list[str]]:
    """Match each changed file to a stack and resolve its scope dir. Returns
    (activated, unsupported): activated is [(stack, scope_dir, rel)]; unsupported
    is the changed paths in an unknown language or a marker-requiring language
    missing its marker. work_tree must already be resolved by the caller, so the
    scope walk compares resolved-to-resolved and terminates at the tree boundary."""
    activated: list[tuple[Stack, Path, str]] = []  # (stack, scope_dir, rel_target)
    unsupported: list[str] = []

    for path in diff_files:
        matched: Stack | None = None
        for stack in STACKS:
            if stack.file_re.search(path):
                matched = stack
                break

        if matched is not None:
            file_dir = (work_tree / path).resolve().parent
            scope_dir = _scope_dir_for(file_dir, work_tree, matched.markers)
            if scope_dir is None and matched.name == "pytest":
                scope_dir = work_tree  # pytest is markerless: fall back to root
            if scope_dir is None:
                unsupported.append(path)
            else:
                activated.append((matched, scope_dir, path))
            continue

        # No stack matched the filename.
        suffix = Path(path).suffix
        if suffix == ".py":
            continue  # recognized by pytest (markerless), but not a run target
        if suffix in _NON_CODE_SUFFIXES:
            continue  # code-free
        unsupported.append(path)

    return activated, unsupported


def _run_native_tests(diff_files: list[str], work_tree: Path) -> dict[str, str]:
    """Detect active (stack, scope_dir) pairs from the diff, run each once, and
    return {stack.name: 'pass=P fail=F skip=S'}. Fails loud (UNSUPPORTED_STACK)
    on an unknown-language code file or a marker-requiring language missing its
    marker; fails loud (EMPTY_TESTS, naming the stack) when an activated stack
    runs but its parser yields no counts. Returns {} for a code-free diff or one
    whose only code is recognized but has no runnable changed-test target."""
    work_tree = work_tree.resolve()  # resolve once so the scope walk terminates
    activated, unsupported = _detect_active_stacks(diff_files, work_tree)

    if unsupported:
        _fail(
            "UNSUPPORTED_STACK",
            f"{' '.join(unsupported)} — add a Stack entry to STACKS in review_coverage.py",
        )

    # Dedup activated pairs by (stack.name, scope_dir), collecting rel_targets.
    pairs: dict[tuple[str, Path], tuple[Stack, Path, list[str]]] = {}
    for stack, scope_dir, rel in activated:
        key = (stack.name, scope_dir)
        if key not in pairs:
            pairs[key] = (stack, scope_dir, [])
        pairs[key][2].append(rel)

    counts: dict[str, tuple[int, int, int]] = {}
    for stack in STACKS:
        for (name, _scope), (s, scope_dir, rel_targets) in pairs.items():
            if name != stack.name:
                continue
            argv = stack.build_cmd(work_tree, scope_dir, rel_targets)
            # go/npm run from their module root (scope_dir); pytest needs a stable
            # rootdir (work_tree) and cargo is cwd-independent (--manifest-path).
            cwd = scope_dir if stack.cwd_at_scope else work_tree
            out, rc = _run_cmd(argv, cwd)
            summary = stack.parse(out, rc)
            if summary is None:
                # Activated stack ran but produced no counts: fail loud naming it,
                # so a polyglot sibling that filled counts cannot mask the gap.
                _fail("EMPTY_TESTS", f"{stack.name} ran but produced no counts")
                continue  # unreachable; _fail exits, but narrows summary for mypy
            m = re.match(r"pass=(\d+) fail=(\d+) skip=(\d+)", summary)
            p, f, sk = int(m.group(1)), int(m.group(2)), int(m.group(3))
            cur = counts.get(stack.name, (0, 0, 0))
            counts[stack.name] = (cur[0] + p, cur[1] + f, cur[2] + sk)

    final = {
        name: f"pass={p} fail={f} skip={sk}"
        for name, (p, f, sk) in counts.items()
    }

    # Polyglot masking guard: a non-test .py SOURCE change activates no pytest run
    # target, so if a sibling stack filled counts it would otherwise green-gate the
    # untested Python change. Fail loud naming pytest. A pure non-test-.py diff
    # leaves `final` empty and is handled downstream by _check_empty_tests, so the
    # markerless pytest contract (returns {} -> generic EMPTY_TESTS) is preserved.
    py_source_no_target = any(
        Path(p).suffix == ".py" and not _PYTEST.file_re.search(p)
        for p in diff_files
    )
    if py_source_no_target and "pytest" not in counts and final:
        _fail(
            "EMPTY_TESTS",
            "pytest: a .py source file changed but no changed test file ran; "
            "a sibling stack filled counts (would otherwise mask the gap) — "
            "add or change a test_*.py covering the Python change",
        )

    return final


def _prd_features(prd: Path) -> list[str]:
    features = []
    for line in prd.read_text().splitlines():
        if line.startswith("#### Feature:"):
            features.append(line[len("#### Feature:"):].strip())
    return features


def _rubric_rules(rubric: Path) -> list[str]:
    rules = []
    for line in rubric.read_text().splitlines():
        m = re.match(r"^(R\d+):", line)
        if m:
            rules.append(m.group(1))
    return rules


# ---------------------------------------------------------------------------
# Gap checks
# ---------------------------------------------------------------------------

def _check_missing_files(merged: dict[str, dict[str, str]], diff_files: list[str]) -> None:
    covered = set(merged["files"].keys())
    missing = [f for f in diff_files if f not in covered]
    if missing:
        _fail("MISSING_FILES", " ".join(missing))


def _check_empty_tests(merged: dict[str, dict[str, str]]) -> None:
    tests = merged["tests"]
    has_reviewed = any(v == "reviewed" for v in merged["files"].values())
    if not has_reviewed:
        return

    has_real = any(
        re.match(r"^pass=\d+ fail=\d+ skip=\d+$", v) for v in tests.values()
    )
    if not has_real:
        _fail("EMPTY_TESTS", "diff contains reviewed code files but no real test counts were recorded")


def _check_unmapped_features(merged: dict[str, dict[str, str]], features: list[str]) -> None:
    covered = set(merged["features"].keys())
    missing = [f for f in features if f not in covered]
    if missing:
        _fail("UNMAPPED_FEATURE", " ".join(missing))


def _check_missing_rubric_rules(merged: dict[str, dict[str, str]], rules: list[str]) -> None:
    covered = set(merged["rubric"].keys())
    missing = [r for r in rules if r not in covered]
    if missing:
        _fail("MISSING_RUBRIC_RULE", " ".join(missing))


# ---------------------------------------------------------------------------
# Aggregate write
# ---------------------------------------------------------------------------

def _write_aggregate(merged: dict[str, dict[str, str]], out: Path) -> None:
    lines = [f"{OPEN_DELIM}\n"]
    for section in ("files", "tests", "features", "rubric"):
        lines.append(f"{section}:\n")
        for key, value in merged[section].items():
            lines.append(f"  {key}: {value}\n")
    lines.append(f"{CLOSE_DELIM}\n")
    out.write_text("".join(lines))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

SURFACE_RUBRIC_DEFAULTS: dict[str, Path] = {
    "work-completion": Path(__file__).parent / ".." / "references" / "rubric.md",
    "blindly": Path(__file__).parent / ".." / ".." / "review-blindly" / "references" / "rubric.md",
    "doubt": Path(__file__).parent / ".." / ".." / "run-autopilot" / "references" / "doubt-review-rubric.md",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Gate review coverage blocks.")
    parser.add_argument("--surface", required=True,
                        choices=["work-completion", "blindly", "doubt"])
    parser.add_argument("--prd", required=True, type=Path)
    parser.add_argument("--diff-range", required=True)
    parser.add_argument("--reviewer-block", required=True, action="append",
                        dest="reviewer_blocks", type=Path)
    parser.add_argument("--rubric", type=Path)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--write-aggregate", type=Path)
    parser.add_argument("--run-tests", action="store_true", default=False)
    args = parser.parse_args()

    if not args.prd.exists():
        _fail("MISSING_PRD", f"PRD file not found: {args.prd.name}")

    blocks = [_load_block(p) for p in args.reviewer_blocks]
    merged = _merge_blocks(blocks)

    diff, work_tree = _diff_files(args.diff_range, args.repo)
    features = _prd_features(args.prd)

    if args.run_tests:
        # Reviewers never assert test results: real counts come only from the
        # consolidation test run, so drop any non-sentinel reviewer entry first.
        merged["tests"] = _strip_reviewer_test_counts(merged["tests"])
        counts_by_stack = _run_native_tests(diff, work_tree)   # may _fail loud internally
        if counts_by_stack:
            merged["tests"].pop("pending", None)
            for stack_name, summary in counts_by_stack.items():
                merged["tests"][stack_name] = summary

    rubric_path: Path = args.rubric if args.rubric else SURFACE_RUBRIC_DEFAULTS[args.surface].resolve()
    if not rubric_path.exists():
        _fail("MISSING_RUBRIC_RULE", f"rubric file not found: {rubric_path}")
    rules = _rubric_rules(rubric_path)

    _check_missing_files(merged, diff)
    _check_empty_tests(merged)
    _check_unmapped_features(merged, features)
    _check_missing_rubric_rules(merged, rules)

    if args.write_aggregate:
        _write_aggregate(merged, args.write_aggregate)

    sys.exit(0)


if __name__ == "__main__":
    main()
