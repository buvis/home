# Sharpening skills: compliance design and the eval loop

Distilled from a 15-iteration benchmark of an unattended research skill (ABAP exploration, Kiro runner, 2026-07, `~/.local/tmp/explain-rest-apis`). Fourteen rounds of text rules failed to stop fabrication; one structural change ended it in a single round. Six of the fifteen iterations produced zero signal on the skill text because the harness was broken. Both costs are avoidable.

Applies in full to skills that gather evidence and write conclusions (research, audit, exploration, review) and run unattended or on another harness. Applies in proportion to everything else.

## Part 1: Design for compliance

An agent under pressure treats prose instructions as suggestions. These mechanisms survived contact, in escalation order. Design at the level the risk justifies; every level skipped at design time costs benchmark rounds later.

### Artifacts, not adverbs

A rule enforced only by prose ("read thoroughly", "never invent") gets violated silently. A rule that demands a checkable artifact converts violation into a visible false claim, which is a brighter line. Proven shapes:

- **Access receipt**: before relying on any capability, exercise it once NOW and paste the evidence (fetch one object, record its first lines with tool and timestamp). No receipt = no access = stop. This rule worked on its first outing and never regressed.
- **Measurement receipt**: paste each discovery query's raw output (tool, timestamp, verbatim head, total count). "You may not summarize a query you have not pasted." Filters may classify listed hits, never shrink a listing.
- **Machine-parseable status lines**: e.g. `CENSUS: raw=N custom=C in-scope=S excluded=E` with arithmetic a script verifies (C = S + E). A `STATUS:` line whose first word must equal the gate verdict. Anything appended to COMPLETE makes it INCOMPLETE ("COMPLETE (scope-limited...)" is a false report).
- **Per-file capture receipts**: every banked artifact opens with a fetched-at header written at capture time; unreceipted = unfetched. Bank bytes verbatim; a "tidied" copy is fabrication under a real label, and the mess is the fingerprint of real source.
- **Gate reports that echo numbers**: a gate passes by echoing every condition with its measured number, counted from a directory listing made in that turn, never from memory. A final report that cannot quote its gate numbers is the signature of a skipped gate.
- **Self-identification**: `Runner: <model/client>` and `References loaded: <per file: read at phase X | unavailable: error>` lines in the output. Without them a bad run cannot be attributed (skill text vs runner setup) and the improvement loop stalls.

### Ship a checker

Bundle a self-check script (stdlib-only python3, `--selftest`, per-line PASS/FAIL, final DELIVERABLE / NOT DELIVERABLE verdict). The skill's definition of done is "checker passes, output pasted verbatim", not "the model feels done". Define the fallback in Dependencies: when the script cannot run, the run records why (missing script = incomplete skill copy, tell the user) and reproduces every check by hand in the same per-line format, pasting the listings each verdict judges.

Expect Goodhart. Every check displaces fraud to the nearest unchecked spot (one round after cited-source checking shipped, paraphrase moved INTO the source bank under real names). Presence checks are weak; **coupling checks** catch laundering:

- status vs gate: COMPLETE requires a `GATE: PASS` line on disk; PASS above pending work = FAIL
- qualified passes: `GATE: PASS (` = FAIL, a failed condition wearing a PASS label
- outputs vs inputs: every identifier in a conclusion must resolve to the evidence layer; unresolved names = invented inventory, reported with a count
- claims vs disk: a "reference not loaded" line while that reference's phase output exists = FAIL
- hedges: likely/probably/presumably in an evidence register = a guess, not a finding

### Make honesty cheaper than fabrication

If the only path to COMPLETE within the run's constraints is faking, runs fake. Provide:

- **An honest-partial mode that ships**: `Status: INCOMPLETE` plus visible partial-coverage banners, named gaps, and a resume list is a SUCCESS deliverable; say so in the skill. A partial that says so beats a complete-looking fake every time.
- **Pause-and-resume**: state lives on disk (notes, ledger, Resume Point); stopping cleanly is always available and always preferred to thinning the process.
- **No speed pressure**: "no clock, no token prize." A context-budget rule that lists a "minimum viable output" reads as permission to stop there. Delegation and pausing are the pressure valves; skipping is not on the list.
- **Degradations are open questions**: a degraded run may not report "open questions: none".

### Structure beats text

When the same failure survives two or three rounds of new rules, stop writing rules. Change the architecture so the failure becomes physically impossible:

- **Split gather from write** (the change that ended a six-round fabrication streak in one iteration): skill A produces a validated evidence package on disk; skill B runs in a FRESH session with no access to the original source, an entry gate that refuses an invalid package, and a contract that it may only embed what A banked. A missing fact becomes `[GAP: <what>]` plus a fetch list, because inventing it is no longer possible. The fresh session is the guard, not a formality: long-lived context is memory, and memory fabricates with confidence.
- **Decider/reader split**: the entity choosing scope must not bear the cost of the scope it picks (it will pick small). Measure first; decide at a checkpoint.
- **Entry gates**: a consumer skill re-validates its input and refuses to run on FAIL. Working politely around gaps launders them into confident prose; refusing is the job.

### Front-load scope: measure, then size

Anchoring happens before the model reads mid-file rules; a pre-reading decision cannot be fixed by text encountered later.

- Size is an OUTPUT of a counted census, cited with its number. Forbid consulting any effort/sizing table before the measurement line exists on disk (a "Small" row otherwise licenses skipping the machinery that would disprove Small).
- Build the one mandatory checkpoint INTO the skill: present the measurement and concrete boundary options, wait once, record the user's answer verbatim. A pause that lives only in the launch prompt works for the author; in the skill it works for every user. Unattended runs record a named default and continue.
- **Tell-phrase stop signs**: list the exact rationalizations that precede the failure ("this is a focused/small solution", "sufficient information gathered", "the remaining objects follow the same pattern"). Writing one before the measurement exists means the anchor is talking: stop and measure.

### State the capability floor

If the skill demonstrably collapses on small/fast model tiers, say so in Dependencies: frontier tier required; a runner that knows it is a fast tier stops and asks for a relaunch instead of producing a degraded run. Every run records its runner line regardless.

## Part 2: The eval loop

How to iterate a skill against reality without burning rounds.

### Fix the harness before blaming the text

A run that ignores rules is not evidence about the rules until you prove it executed them. The wasted iterations all traced to the harness: stale or missing skill copy, activation that never happened, silent model downgrade, `scripts/` dropped in distribution, symlinks copied as dead links, prior outputs sitting in the runner's context. Preflight every run:

1. **Distribution**: current copy synced to the runner; `scripts/` and `references/` present; symlinks dereferenced (`cp -RL` / `rsync -L` / `tar -h`); runner session restarted after sync (skills synced mid-session are invisible).
2. **Activation**: launch via the explicit slash command, never description-matching roulette; verify the skill appears in the runner's context first.
3. **Model**: pinned in the runner's agent config, not picked per session; watch for silent fallback. The weak-tier fingerprint (summary essays instead of contract artifacts, mutated identifiers, skipped phases) mimics a bad skill text.
4. **Freshness**: fresh session, prior outputs hidden. A runner holding earlier results in context regenerates them from memory and calls it exploration.
5. **Capability probe**: before the real run, have the runner read one reference file and run the checker's `--selftest`. Either failing is a file-access or exec boundary to fix first (e.g. install workspace-level instead of home-level).

### Kill early

Name the run's earliest mandatory artifact (the first write of every run, e.g. notes.md with the access receipt, or the checkpoint question arriving). No artifact within minutes = dead run: kill it, fix the harness, relaunch. Never pay for a doomed full iteration; a completed doomed run also pollutes the next eval with noise.

### Benchmark against a frozen baseline, ratchet both ways

- Keep a golden output (from an attended run) and a frozen launch prompt; change either only deliberately.
- One eval file per iteration, stable shape: verdict first; what the last round's fixes visibly achieved (prove the loop is closed); new failures with the fix applied and file touched, as a table; backports (where the run beat the baseline, improve the baseline in place, with provenance); blocking items for the next run, runner-side separated from skill-side.
- Keep the skill generic: every fix must hold for any target in the domain; benchmark specifics go to examples. Never bend the skill around the benchmark.
- Verify claimed evidence yourself during eval (diff banked artifacts against known-good copies, recompute counts). Runs fabricate the eval's inputs too.

### Diagnose before writing rules

A violated EXISTING rule is a diagnosis question, not a license to restate it louder. Duplicating rules for a reader who was not reading is bloat that buries the load-bearing text. Ask why it was ignored: never loaded (harness)? weak tier (pin the model)? anchored before reading (front-load)? no honest path (incentives)? Fix that instead.

Escalation ladder per failure, one level per recurrence:

1. prose rule
2. forced artifact / receipt
3. mechanical check
4. coupling check
5. structural change (split / entry gate / session isolation)

The benchmark's fabrication failure burned six rounds at levels 1-4; level 5 ended it in one. When a failure reaches its third round, jump straight to 5.

### Control variables

The best mid-loop run changed model, session freshness, hidden priors, and pressure wording all at once; the win could not be attributed and the whole package had to be kept on faith. Change one lever per iteration when you need attribution, or accept the confound knowingly. The runner line in every output is what makes late attribution possible at all.

### Compress on a cadence

Rules accrete one failure at a time and drown each other; a skill the runner must read end-to-end competes with the task for context. Periodically consolidate scattered per-failure rules into one contract section (the benchmark's census consolidation made the skill shorter AND stronger). A rule absorbed by the checker shrinks to one line; the check carries the enforcement.
