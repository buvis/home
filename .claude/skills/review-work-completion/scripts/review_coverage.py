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
import os
import re
import subprocess
import sys
from pathlib import Path

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

        # Entry line: "  key: value" (may contain colons in value)
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if current is None:
                raise ValueError(f"entry before any section header: {line!r}")
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
    # Require work_tree to exist before using it as cwd: a bad override would
    # otherwise raise a raw OSError instead of the clean MISSING_FILES gap kind.
    if Path(git_dir).exists() and Path(work_tree).exists():
        fallback = subprocess.run(
            ["git", f"--git-dir={git_dir}", f"--work-tree={work_tree}",
             "diff", "--name-only", diff_range],
            cwd=work_tree,
            capture_output=True,
            text=True,
        )
        if fallback.returncode == 0:
            return [f for f in fallback.stdout.splitlines() if f.strip()], Path(work_tree)

    _fail("MISSING_FILES", f"git diff failed: {result.stderr.strip()}")
    return [], repo  # unreachable; satisfies type checker without suppression


def _run_changed_tests(diff_files: list[str], work_tree: Path) -> str | None:
    """Run changed test files under pytest and return a 'pass=P fail=F skip=S'
    summary, or None when no changed file is a test file."""
    test_paths = []
    for f in diff_files:
        base = Path(f).name
        if re.match(r"^test_.*\.py$", base) or re.match(r"^.*_test\.py$", base):
            abs_path = (work_tree / f).resolve()
            if abs_path.exists():
                test_paths.append(str(abs_path))

    if not test_paths:
        return None

    result = subprocess.run(
        [sys.executable, "-m", "pytest", *test_paths, "-q"],
        cwd=str(work_tree),
        capture_output=True,
        text=True,
    )
    out = result.stdout + result.stderr

    def count(pattern: str) -> int:
        m = re.search(pattern, out)
        return int(m.group(1)) if m else 0

    passed = count(r"(\d+) passed")
    failed = count(r"(\d+) failed") + count(r"(\d+) error(?:s)?")
    skipped = count(r"(\d+) skipped")
    if passed == 0 and failed == 0 and skipped == 0:
        # pytest collected/ran nothing (exit 5, "no tests ran"). A changed test
        # file that executes zero tests is not coverage — leave the dimension
        # unfilled so _check_empty_tests fails loud rather than green-gating.
        return None
    return f"pass={passed} fail={failed} skip={skipped}"


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
        # Reviewers never assert test results. In the --run-tests path (the
        # consolidation/production path) real counts come only from the test
        # run below, so drop any reviewer-supplied non-sentinel `tests` entry —
        # otherwise a fabricated `pass=N fail=N skip=N` would satisfy
        # _check_empty_tests on a diff whose changed files include no test file.
        merged["tests"] = {
            k: v for k, v in merged["tests"].items() if k in ("none", "pending")
        }
        summary = _run_changed_tests(diff, work_tree)
        if summary is not None:
            merged["tests"].pop("pending", None)
            merged["tests"]["pytest"] = summary

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
