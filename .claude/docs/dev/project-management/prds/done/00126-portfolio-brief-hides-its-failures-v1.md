# The portfolio brief renders its own failures as clean negatives

Source: agoge product-QA run, `dev/local/audit-results/agoge-2026-08-17.md`, findings 3 (HIGH,
raised independently by heidi, walter and judy), 11 (HIGH), 13 (MEDIUM), 15 and 16 (MEDIUM,
accepted as one cluster) and 30 (MEDIUM), all accepted in the 2026-08-17 walkthrough.

**Standing decision from that walkthrough:** `skills/brief-portfolio` is treated as a live
product, not as code awaiting the `postup` rewrite. That port is seven unstarted PRDs in the
gems backlog (`00063`-`00068`, `00070`), so these fixes land here.

## Overview

### Problem Statement

The dashboard exists so the operator trusts it instead of checking 26 repos by hand. Five
defects each turn a failure into a reassuring answer:

1. **A repo that fails collection vanishes, and the run reports "0 with warnings."** On the
   real registry, `collect.py` warned that `doogat/jink` was skipped, then closed with
   `25 repos, 0 with warnings`. `data.json` holds 25 repos; the built page contains no
   occurrence of `jink`, `skip` or `warn` anywhere across all 7 tabs, and the header reads
   `25 REPOS`. In a sandbox where both repos failed: exit 0, `0 repos, 0 with warnings`,
   `repos: []`. `collect_repo` returns `None` (line 322-323), `main` filters it (line 394),
   `len(failed)` (line 424) counts only repos that survived far enough to record an error, and
   `build.py` never reads `errors`.
2. **A total `gh` failure is written as "you have no open PRs."** With `gh` unauthenticated,
   `main` (line 403-405) caught `Exception` and wrote `external: {review_requested: [],
   authored: []}` with no marker — so the dashboard says nothing needs your attention.
3. **One hung `git fetch` aborts the whole run.** Line 328 catches only `RuntimeError`;
   `subprocess.run(timeout=180)` raises `TimeoutExpired`, so one bad remote costs the entire
   brief after a 3-minute wait, with a traceback and no `data.json`.
4. **Re-running destroys the "Since last brief" baseline.** Lines 410-413 rotate
   `data.json` → `data-prev.json` unconditionally, so a re-run 48 seconds later leaves the
   "previous brief" 48 seconds old. `SKILL.md:36-39` says never delete those two files; the
   tool deletes one itself.
5. **`--no-fetch` still makes 7 GitHub API calls per repo** — about 184 live requests and 327
   `git` spawns at real registry size. It suppresses exactly `git fetch`.
6. **"copy open as markdown" fails silently from `file://`**, which is how these artifacts are
   opened.

### Target Users

The operator reading the weekly brief, and any unattended run that trusts `--no-fetch` to be
offline — one did, and spent ~370 live GitHub API calls on 2026-08-17.

### Success Metrics

- A registry containing one unresolvable repo produces `26 repos, 1 skipped` and a page that
  names the skipped repo.
- With `gh` unauthenticated, the page shows an error state for the external section, never an
  empty one.
- One repo whose fetch times out costs that repo only; `data.json` is still written.
- Two collects 48 seconds apart leave the baseline from the earlier brief intact.
- The offline flag makes zero network calls, counted with a recorder stub.
- Clicking copy from a `file://` page either copies or says it could not.

## Functional Decomposition

### Capability: a failure appears in the artifact (findings 3, 15, 16)

Accepted options: `collect_repo` returns a `{owner, name, skipped: reason}` stub instead of
`None`, the summary counts skips, and the page renders "n not collected" by the repo count;
`external` carries `{"error": "<msg>"}` rather than empty lists, rendered as an error row; and
line 328's catch widens to `(RuntimeError, subprocess.SubprocessError, OSError)`.

### Capability: the baseline survives a re-run (finding 13)

Rotate only when the existing `data.json`'s `generated_at` is older than a threshold.

### Capability: an offline flag that is offline (finding 30)

Add a real `--offline` that short-circuits `gh_json` to the cached `data.json`, and rename the
existing flag `--no-git-fetch`. Both behaviours exist and are honestly named; update the
skill's own docs and every caller, including the agoge strategy profile's mocking advice.

### Capability: copy tells you what happened (finding 11)

Port `debrief-meeting/app/src/components/CopyButton.svelte:19-21`'s try/catch and
`execCommand` fallback into `Todos.svelte`, plus a "copy failed" label when the fallback also
throws.

## Structural Decomposition

- `skills/brief-portfolio/scripts/collect.py` — findings 3, 13, 15, 16, 30
- `skills/brief-portfolio/scripts/build.py` — the `errors`/`skipped` payload
- `skills/brief-portfolio/app/src/components/Brief.svelte` — the skipped-repo note
- `skills/brief-portfolio/app/src/components/Todos.svelte` — finding 11
- `skills/brief-portfolio/SKILL.md` — the flag rename, the baseline rule

## Implementation Phases

### Phase 1: collector truth (findings 3, 15, 16)

1. Stub-instead-of-`None`, skip counting in the summary, `errors`/`skipped` in the payload.
2. `external` error object.
3. Widen the per-repo exception catch.
4. Render all three in the SPA.

### Phase 2: flags and baseline (findings 13, 30)

5. Threshold-gated rotation.
6. `--offline` plus the `--no-git-fetch` rename, docs and callers updated.

### Phase 3: the copy button (finding 11)

7. Port the try/catch and fallback; label the failure.

*Acceptance:* the reproductions below run green after each phase, and the page is re-driven
for phases 1 and 3 — the SPA half is the part no unit test covers.

## Test Strategy

Verbatim from the run:

```
stderr: collecting 26 repos (days=7, fetch=False)
stderr: WARN /Users/bob/git/src/github.com/doogat/jink: skipped (git remote: error: No such remote 'origin')
stdout: wrote /tmp/j2/data.json ...; 25 repos, 0 with warnings
$ jq -r '.repos | length' /tmp/j2/data.json      -> 25
$ rg -c "jink" /tmp/j2/brief.html                -> no match (rc 1)
```

```
WARN external: gh search: To get started with GitHub CLI, please run:  gh auth login
"external": {"review_requested": [], "authored": [], "claude_maintenance_last": null}
```

```
PROBE: git fetch TIMES OUT for a github repo
  RAISED OUT OF collect_repo: TimeoutExpired "... timed out after 180 seconds"
PROBE: same through ThreadPoolExecutor with a healthy sibling repo
  WHOLE RUN DIED: TimeoutExpired
control: git absent from PATH -> raw FileNotFoundError, EXIT 1, data.json written? False
```

```
run 1 at 2026-08-16T22:56:37Z, run 2 at 2026-08-16T22:57:25Z
$ diff <(jq -S 'del(.generated_at)' data-prev.json) <(jq -S 'del(.generated_at)' data.json)
470c470
<         "dirty": 16,
>         "dirty": 18,
```

```
4 repos: {"git": 50, "gh": 30}   -> 7.5 gh/repo
8 repos: {"git": 101, "gh": 58}  -> 7.2 gh/repo      (exactly 7 x repos + 2)
```

```
console: pageerror: Failed to execute 'writeText' on 'Clipboard': Write permission denied.
copy_btn_text_before: "copy open as markdown"
copy_btn_text_150ms:  "copy open as markdown"
main_text_changed: false    live_regions: []
```

## Risks

- **The `skipped` stub and `external` error object change the data shape**, so any consumer
  assuming every `repos` entry is complete, or that `external` keys are list-shaped, breaks.
- **The rotation threshold is invented.** A wrong value gives a subtler version of the same
  bug, and a legitimate same-day second brief will not rotate.
- **The flag rename breaks existing invocations**, including the skill's docs and the agoge
  profile. Every caller must be updated in the same change.
- **The ported copy fallback uses deprecated `execCommand`**, so it has a shelf life, and the
  component is now duplicated in two apps that share no package.
- **All of this lands in a skill with a scheduled replacement.** Accepted deliberately on
  2026-08-17; the fixes also serve as requirements for the postup rewrite.
