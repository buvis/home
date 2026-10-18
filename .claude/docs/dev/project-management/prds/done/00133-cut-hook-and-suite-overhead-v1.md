# Hook and test-suite overhead grows with things that only go up

Source: agoge product-QA run, `dev/local/audit-results/agoge-2026-08-17.md`, findings 29
(MEDIUM), 41, 42 and 43 (LOW), each accepted in the 2026-08-17 walkthrough. Found by peggy, who
measured rather than estimated.

**Read this first: nothing here breaches a budget.** Every number below is a small fraction of its
cap. The reason these were accepted is shape, not pain: each cost grows with something that only
increases — session length, skill count, tool calls per session — and the suite one is a tax on
how often the safety net gets run.

## Overview

### Problem Statement

1. **Every turn's Stop hook re-reads the whole transcript twice.** `track_cost` and
   `track_skills` each read the entire file and parse every line, once per Stop, so cost is
   O(turns × final size). One real 64-stop session re-read **827.6 MiB** of a 14.94 MiB file —
   55.4x a single read. Largest real transcript costs 35.6 ms against a 10 s per-handler cap
   (0.36%).
2. **Editing any SKILL.md reads every other SKILL.md on the machine.** 67 reads, 595,786 bytes
   per edit, linear in the whole corpus (264 skills → 265 reads). 27.1 ms against a 5 s cap
   (0.54%). A skill-authoring session saving 20 times reads ~11.6 MB.
3. **Hook dispatch costs ~85 ms per Edit and ~62 ms per Bash**, almost entirely process startup.
   Inside one dispatcher process, three separate `git` calls resolve the same repo root. Worst
   handler is 0.62% of its cap; the whole `pre` event is 0.3% of its 20 s budget.
4. **Four tests are 39% of the 69-second hooks suite** (26.99 s) because each builds a real git
   repo and makes ~50 real commits — about 460 `git` processes at ~65 ms. That runtime is a tax on
   how often the suite runs, and the suite is what would have caught a red matcher test 14 days
   earlier than it was caught.

### Target Users

Every session (items 1-3), and the maintainer deciding whether running the suite is worth the
wait (item 4).

### Success Metrics

- The Stop path reads the transcript **once** per stop, not twice.
- A SKILL.md edit does not read the whole corpus on every save.
- An Edit's dispatch makes **one** repo-root resolution, not three.
- The hooks suite completes in appreciably under 69 s with every boundary assertion intact.

## Functional Decomposition

Accepted options, per finding:

- **29:** parse once per Stop and share the rows between the two handlers.
- **41:** cache the phrase→owner index, keyed on the max mtime of the two globs, following
  `observe_tool`'s existing `.cwd-cache.json` pattern. **Note:** peggy recommended *against* this
  (0.54% of cap, and a cache is a new thing that can be stale); the operator chose it anyway on
  2026-08-17. Build it with invalidation as the review-critical part.
- **42:** memoize `(dir -> toplevel)` per dispatcher process.
- **43:** rewrite the four boundary tests against a lowered commit threshold, reusing the
  per-repo override that `test_per_repo_override_lowers_commit_threshold` already exercises with
  `max_commits: 10`.

## Structural Decomposition

- `hooks/track_cost.py`, `hooks/track_skills.py` — the shared parse (29)
- `hooks/dispatch.py` — the shared/memoized repo-root resolution (29, 42)
- `hooks/check_skill_triggers.py` — the cached index (41)
- `hooks/cartographer-echo.py`, `hooks/enforce_prd_location.py` — the three `git` calls (42)
- `hooks/tests/test_cartographer_stop.py` — `_add_commits()` at line 46 and the four boundary
  tests (43)

## Implementation Phases

### Phase 1: the suite (finding 43)

1. Lower the threshold in the four boundary tests via the existing per-repo override. Do this
   first: everything else is verified by running the suite, so make the suite cheap first.

### Phase 2: per-event sharing (findings 29, 42)

2. Parse the transcript once per Stop, shared between both handlers.
3. Memoize the repo-root resolution for the life of one dispatcher process.

### Phase 3: the cached index (finding 41)

4. Cache the phrase→owner index keyed on the globs' max mtime, with an invalidation test that
   proves a newly-added colliding trigger is still detected.

*Acceptance:* the suite is faster with the same assertions; a Stop with a 15 MiB transcript
performs one read; an Edit's dispatch spawns one `git rev-parse` instead of three; adding a
colliding trigger phrase is still caught with a warm cache.

## Test Strategy

Verbatim measurements:

```
transcript  0.50 MiB   track_cost  1.5 ms   read_text=1
transcript 15.00 MiB   track_cost 49.3 ms   read_text=1
REAL 14.94 MiB transcript: track_cost 35.6/31.1 ms, track_skills 35.3/29.8 ms
session 71f5d3ab ran the Stop hook 64 times
sum of transcript size across stops: 413.8 MiB
bytes re-read by the Stop path (2 reads/stop): 827.6 MiB   -> 55.4x one read
```

```
check_skill_triggers  median=18.5ms / 27.1ms   read_text=67   bytes_read=595,786
 33 skills -> read_text=34   bytes=269,115     7.26 ms
264 skills -> read_text=265  bytes=2,097,480  13.90 ms
```

```
python3 -c pass            median=  8.8 ms   (startup floor)
dispatch.py pre  (Write)   median= 49.0 ms
dispatch.py pre  (Edit .py) median= 59.2 ms   3 spawns:
  git rev-parse --show-toplevel, git remote get-url origin, git rev-parse --show-toplevel
```

```
7.09s test_flag_set_when_commit_threshold_exceeded
6.72s test_no_flag_when_below_commit_threshold
6.68s test_no_flag_at_exactly_commit_threshold
6.50s test_flag_not_created_at_boundary_below_commit_threshold
Top 4 = 26.99 s of 69.06 s (39%)
```

Counting tests beat timing tests here: assert one `read_text` per Stop and one `git rev-parse`
per Edit, rather than asserting a duration.

## Risks

- **Sharing parsed rows couples two handlers through dispatcher state**, weakening the isolation
  the dispatcher deliberately has — the same trade in findings 29 and 42.
- **A cache that goes stale breaks collision detection**, which is a correctness regression bought
  for 20 ms. This is why peggy advised against item 41; the invalidation test is the whole defence.
- **Lowering the commit threshold moves boundary tests off the production default**, and boundary
  tests are precisely where the exact number matters. Keep one test at the real threshold if it
  can be made cheap.
- **A memo inside a long-lived process would resolve the wrong repo.** The dispatcher process is
  per-event, which bounds it, but any future change to that lifetime breaks the assumption.
- **All of this optimises fractions of a percent of budget.** If a phase turns out to be more
  invasive than measured, dropping it costs nothing real — say so rather than pushing through.
