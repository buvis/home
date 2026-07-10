# Review File Format (PRD 00016)

The consolidated review file at `dev/local/reviews/<prd-base>-review-<N>.md`
is the review cycle's durable artifact. `check_review_file.py` validates its
shape — three regex-checked elements, nothing else. No `---review-coverage---`
blocks, no files/features dimensions, no aggregate merging: those conventions
were retired (their operational record was false blocks, not caught defects).

## Required shape

1. **Frontmatter** with at least:
   - `head_sha: <sha>` — HEAD at review time (next cycle scopes its diff from it)
   - `reviewers: alice,blake,bob[,carl][,quinn][,eve]` — comma-separated
     lowercase names of every reviewer that actually RAN this cycle
   - `codex_thread_id: <id>` — optional; present when Bob ran on codex
2. **One `## <Name>` section per launched reviewer**, non-empty: the
   reviewer's findings, or a one-line all-clear. Bob's section keeps his
   `R{n}: pass|fail` doubt-rubric lines (consolidation parses them into
   `state.doubts_rubric_verdicts`).
3. **A verdict line** (at column 0, normally at the end):
   `Verdict: converged` or `Verdict: N findings`
4. **A tests line**:
   `Tests: N passed, M failed, K skipped` (free text allowed after the
   passed count) or `Tests: none (docs-only)` when the diff touches no code.

## Gate contract

```
python3 ~/.claude/skills/review-work-completion/scripts/check_review_file.py \
  --review-file <path> [--reviewers alice,bob,...]
```

- exit 0: shape holds (with `--reviewers` omitted, the frontmatter list is used)
- exit 1: one-line gap description on stderr (missing file, missing/empty
  reviewer section, missing verdict or tests line)
- unreadable file (I/O error): exit 0 with a loud stderr note — an
  infrastructure error must not masquerade as a coverage gap
